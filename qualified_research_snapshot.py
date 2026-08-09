"""Immutable, explicit snapshot retention and replay for qualified research briefs.

This is a deliberately small archive boundary.  It never selects a "latest" snapshot,
never reads the clock, and never modifies runtime artifacts.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from atomic_io import atomic_write_file, validate_json_file
from qualified_research_delta import compare


SCHEMA_VERSION = "1.0.0"
SNAPSHOT_PREFIX = "qrs-"
PILOT_TICKERS = ("HPG", "VNM", "VCB")
_NORMALIZED_PILOT_TICKERS = tuple(sorted(PILOT_TICKERS))
_ID_RE = re.compile(r"^qrs-[0-9a-f]{64}$")


class SnapshotIntegrityError(ValueError):
    """A snapshot is malformed, tampered with, or not self-contained."""


class SnapshotCollisionError(SnapshotIntegrityError):
    """An immutable snapshot directory already exists but is not the same snapshot."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _canonical_file(value: Any) -> bytes:
    return _canonical(value) + b"\n"


def _sha_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_root(root: str | Path) -> Path:
    return Path(root).expanduser().resolve()


def _safe_snapshot_dir(root: str | Path, snapshot_id: str) -> Path:
    if not isinstance(snapshot_id, str) or not _ID_RE.fullmatch(snapshot_id):
        raise SnapshotIntegrityError("invalid_snapshot_id")
    safe_root = _safe_root(root)
    candidate = (safe_root / snapshot_id).resolve()
    if candidate.parent != safe_root:
        raise SnapshotIntegrityError("snapshot_path_outside_store_root")
    return candidate


def _brief_metadata(ticker: str, brief: Mapping[str, Any]) -> dict[str, Any]:
    if brief.get("ticker") != ticker:
        raise SnapshotIntegrityError(f"brief_ticker_mismatch:{ticker}")
    if brief.get("analysis_mode") != "historical_only_qualified_data" or brief.get("historical_only") is not True or brief.get("is_actionable") is not False:
        raise SnapshotIntegrityError(f"brief_contract_invalid:{ticker}")
    if not isinstance(brief.get("entity_type"), str) or not brief.get("entity_type"):
        raise SnapshotIntegrityError(f"brief_entity_type_missing:{ticker}")
    if not isinstance(brief.get("schema_version"), str) or not brief.get("schema_version"):
        raise SnapshotIntegrityError(f"brief_analysis_version_missing:{ticker}")
    identity = _mapping(brief.get("identity"))
    periods = identity.get("periods")
    if not isinstance(periods, list):
        raise SnapshotIntegrityError(f"brief_qualified_periods_missing:{ticker}")
    payload = dict(brief)
    content = _canonical_file(payload)
    return {"ticker": ticker, "file": f"{ticker}.qualified_research_brief.json", "entity_type": brief["entity_type"],
            "qualified_periods": sorted(str(period) for period in periods if period is not None),
            "analysis_version": brief["schema_version"], "historical_only": True, "is_actionable": False,
            "brief_sha256": _sha_bytes(_canonical(payload)), "file_sha256": _sha_bytes(content), "content": content}


def validate_source_bundle(bundle_path: str | Path, manifest_path: str | Path, tickers: tuple[str, ...] = PILOT_TICKERS) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate an explicit bundle and its matching manifest without touching runtime."""
    bundle_file, manifest_file = Path(bundle_path).resolve(), Path(manifest_path).resolve()
    try:
        bundle, source_manifest = json.loads(bundle_file.read_text(encoding="utf-8")), json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotIntegrityError(f"source_bundle_or_manifest_unreadable:{exc}") from exc
    bundle_sha = _sha_file(bundle_file)
    trusted = _mapping(_mapping(source_manifest).get("trusted_subset"))
    if trusted.get("bundle_filename") != bundle_file.name or trusted.get("bundle_sha256") != bundle_sha:
        raise SnapshotIntegrityError("source_manifest_bundle_hash_mismatch")
    entries = _mapping(_mapping(bundle).get("tickers"))
    normalized = tuple(sorted({str(ticker).upper() for ticker in tickers}))
    if not normalized:
        raise SnapshotIntegrityError("snapshot_ticker_set_empty")
    briefs: dict[str, Any] = {}
    for ticker in normalized:
        entry, brief = _mapping(entries.get(ticker)), _mapping(_mapping(entries.get(ticker)).get("qualified_research_brief"))
        if not entry or not brief:
            raise SnapshotIntegrityError(f"qualified_research_brief_missing:{ticker}")
        briefs[ticker] = dict(brief)
    return {"bundle_sha256": bundle_sha, "bundle_manifest_sha256": _sha_file(manifest_file),
            "source_manifest_schema_version": source_manifest.get("schema_version"), "briefs": briefs}, source_manifest


def _identity(source: Mapping[str, Any], records: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {"snapshot_schema_version": SCHEMA_VERSION, "source_analysis_bundle_sha256": source["bundle_sha256"],
            "source_bundle_manifest_sha256": source["bundle_manifest_sha256"], "source_manifest_schema_version": source.get("source_manifest_schema_version"),
            "captured_tickers": [record["ticker"] for record in records],
            "brief_hashes": [{"ticker": record["ticker"], "brief_sha256": record["brief_sha256"]} for record in records]}


def _build_manifest(source: Mapping[str, Any], tickers: tuple[str, ...]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records = [_brief_metadata(ticker, _mapping(source["briefs"].get(ticker))) for ticker in sorted(tickers)]
    identity = _identity(source, records)
    snapshot_id = SNAPSHOT_PREFIX + _sha_bytes(_canonical(identity))
    return {"schema_version": SCHEMA_VERSION, "snapshot_id": snapshot_id, "identity": identity,
            "source": {"analysis_bundle_sha256": source["bundle_sha256"], "bundle_manifest_sha256": source["bundle_manifest_sha256"],
                       "bundle_manifest_schema_version": source.get("source_manifest_schema_version")},
            "captured_tickers": [record["ticker"] for record in records],
            "briefs": [{key: value for key, value in record.items() if key != "content"} for record in records]}, records


def _validate_manifest_shape(manifest: Mapping[str, Any]) -> None:
    identity = _mapping(manifest.get("identity"))
    expected = SNAPSHOT_PREFIX + _sha_bytes(_canonical(identity))
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("snapshot_id") != expected or not _ID_RE.fullmatch(expected):
        raise SnapshotIntegrityError("snapshot_manifest_identity_invalid")
    briefs = manifest.get("briefs")
    tickers = manifest.get("captured_tickers")
    if not isinstance(briefs, list) or not isinstance(tickers, list) or tickers != sorted(tickers) or tickers != list(_NORMALIZED_PILOT_TICKERS):
        raise SnapshotIntegrityError("snapshot_manifest_ticker_set_invalid")
    if [item.get("ticker") for item in briefs if isinstance(item, Mapping)] != tickers:
        raise SnapshotIntegrityError("snapshot_manifest_brief_order_invalid")
    if identity.get("captured_tickers") != tickers:
        raise SnapshotIntegrityError("snapshot_manifest_identity_ticker_mismatch")


def validate_snapshot(store_root: str | Path, snapshot_id: str) -> dict[str, Any]:
    """Validate only self-contained files named by an explicit, safe snapshot ID."""
    snapshot_dir = _safe_snapshot_dir(store_root, snapshot_id)
    manifest_path = snapshot_dir / "snapshot_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotIntegrityError(f"snapshot_manifest_missing_or_invalid:{exc}") from exc
    _validate_manifest_shape(_mapping(manifest))
    if manifest.get("snapshot_id") != snapshot_id:
        raise SnapshotIntegrityError("snapshot_id_manifest_mismatch")
    for record in manifest["briefs"]:
        if not isinstance(record, Mapping):
            raise SnapshotIntegrityError("snapshot_brief_record_invalid")
        ticker, filename = record.get("ticker"), record.get("file")
        if filename != f"{ticker}.qualified_research_brief.json" or not isinstance(ticker, str):
            raise SnapshotIntegrityError("snapshot_brief_path_invalid")
        path = (snapshot_dir / filename).resolve()
        if path.parent != snapshot_dir or not path.is_file() or _sha_file(path) != record.get("file_sha256"):
            raise SnapshotIntegrityError(f"snapshot_brief_file_hash_mismatch:{ticker}")
        try:
            brief = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SnapshotIntegrityError(f"snapshot_brief_json_invalid:{ticker}") from exc
        actual = _brief_metadata(ticker, _mapping(brief))
        for field in ("brief_sha256", "entity_type", "qualified_periods", "analysis_version", "historical_only", "is_actionable"):
            if actual[field] != record.get(field):
                raise SnapshotIntegrityError(f"snapshot_brief_metadata_mismatch:{ticker}:{field}")
    return dict(manifest)


def retain(bundle_path: str | Path, manifest_path: str | Path, store_root: str | Path, tickers: tuple[str, ...] = PILOT_TICKERS) -> dict[str, Any]:
    """Retain a new immutable snapshot, or validate an already-retained identical one."""
    normalized = tuple(sorted({str(ticker).upper() for ticker in tickers}))
    if normalized != _NORMALIZED_PILOT_TICKERS:
        raise SnapshotIntegrityError("snapshot_ticker_set_must_be_hpg_vnm_vcb")
    source, _ = validate_source_bundle(bundle_path, manifest_path, normalized)
    manifest, records = _build_manifest(source, normalized)
    snapshot_dir = _safe_snapshot_dir(store_root, manifest["snapshot_id"])
    root = _safe_root(store_root)
    root.mkdir(parents=True, exist_ok=True)
    try:
        snapshot_dir.mkdir()
    except FileExistsError:
        try:
            existing = validate_snapshot(root, manifest["snapshot_id"])
        except SnapshotIntegrityError as exc:
            raise SnapshotCollisionError(f"immutable_snapshot_collision:{manifest['snapshot_id']}:{exc}") from exc
        if _canonical(existing) != _canonical(manifest):
            raise SnapshotCollisionError(f"immutable_snapshot_collision:{manifest['snapshot_id']}:manifest_content_differs")
        return {"status": "snapshot_already_retained", "snapshot_id": manifest["snapshot_id"], "manifest": existing}
    try:
        for record in records:
            atomic_write_file(snapshot_dir / record["file"], record["content"], validator=validate_json_file)
        # The manifest is deliberately written last: its presence makes this set visible/valid.
        atomic_write_file(snapshot_dir / "snapshot_manifest.json", _canonical_file(manifest), validator=validate_json_file)
        validated = validate_snapshot(root, manifest["snapshot_id"])
    except Exception:
        # Leave an incomplete directory without a manifest rather than deleting evidence or overwriting it.
        raise
    return {"status": "snapshot_retained", "snapshot_id": manifest["snapshot_id"], "manifest": validated}


def snapshot_as_bundle(store_root: str | Path, snapshot_id: str) -> dict[str, Any]:
    """Load a validated snapshot into the bundle shape consumed by Phase 5D attachment."""
    manifest = validate_snapshot(store_root, snapshot_id)
    snapshot_dir = _safe_snapshot_dir(store_root, snapshot_id)
    return {"tickers": {record["ticker"]: {"qualified_research_brief": json.loads((snapshot_dir / record["file"]).read_text(encoding="utf-8"))} for record in manifest["briefs"]}}


def replay(snapshot_store_root: str | Path, snapshot_id: str, current_bundle_path: str | Path, current_manifest_path: str | Path) -> dict[str, Any]:
    """Replay one explicit snapshot against one explicit current bundle using Phase 5D."""
    previous = snapshot_as_bundle(snapshot_store_root, snapshot_id)
    current, _ = validate_source_bundle(current_bundle_path, current_manifest_path)
    deltas = {ticker: compare(_mapping(_mapping(previous["tickers"].get(ticker)).get("qualified_research_brief")), current["briefs"][ticker]) for ticker in _NORMALIZED_PILOT_TICKERS}
    return {"schema_version": SCHEMA_VERSION, "previous_snapshot_id": snapshot_id, "current_bundle_sha256": current["bundle_sha256"], "deltas": deltas}


def main() -> int:
    parser = argparse.ArgumentParser(description="Immutable qualified-research snapshot retention and explicit replay.")
    commands = parser.add_subparsers(dest="command", required=True)
    retain_p = commands.add_parser("retain"); retain_p.add_argument("--bundle", required=True); retain_p.add_argument("--bundle-manifest", required=True); retain_p.add_argument("--store-root", required=True)
    validate_p = commands.add_parser("validate"); validate_p.add_argument("--snapshot-id", required=True); validate_p.add_argument("--store-root", required=True)
    replay_p = commands.add_parser("replay"); replay_p.add_argument("--snapshot-id", required=True); replay_p.add_argument("--store-root", required=True); replay_p.add_argument("--current-bundle", required=True); replay_p.add_argument("--current-bundle-manifest", required=True)
    args = parser.parse_args()
    if args.command == "retain": result = retain(args.bundle, args.bundle_manifest, args.store_root)
    elif args.command == "validate": result = validate_snapshot(args.store_root, args.snapshot_id)
    else: result = replay(args.store_root, args.snapshot_id, args.current_bundle, args.current_bundle_manifest)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
