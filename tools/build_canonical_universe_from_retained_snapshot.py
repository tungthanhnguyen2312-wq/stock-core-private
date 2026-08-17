"""No-network integration adapter: retained DNSE security-master snapshot -> C.1 canonical
instrument artifact -> C.2 universe-tier/exclusion-ledger artifact.

This is deliberately the thinnest possible wiring over two already-existing, already-tested
builders (``canonical_instrument_reconciliation.build_from_retained_files`` and
``canonical_universe_tiers.build_from_explicit_artifacts``); it adds no new reconciliation or
tiering logic of its own. What it adds is explicit provenance binding: before either builder runs,
it verifies the given snapshot Parquet actually matches its own retained
``tools/discover_market_universe.py`` manifest (same ``discovered_count``), then carries that
manifest's ``snapshot_id``/``content_hash``/``retrieved_at``/``by_instrument_class`` forward into
one immutable, content-addressed integration-run summary alongside the resulting C.1/C.2 artifact
identities -- so a reader of the summary alone can tell exactly which retained snapshot produced a
given canonical-universe artifact pair without re-deriving it.

NEVER calls ``dnse_instrument_universe.discover_universe()`` or any other live provider entrypoint.
Reads only an already-retained snapshot Parquet and its already-retained manifest JSON, both
already written earlier by ``tools/discover_market_universe.py``.

Neither ``3,250``, ``1,660``, nor ``1,590`` is hardcoded anywhere in this module: every count in the
output summary is read back from the C.2 artifact this run itself produced from whatever snapshot
it was given. They are architecture-independent facts about one specific retained snapshot, not a
permanent invariant of this adapter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_json  # noqa: E402
import canonical_instrument_reconciliation as c1  # noqa: E402
import canonical_universe_tiers as c2  # noqa: E402

SCHEMA_VERSION = "1.0.0"
STORE_RELATIVE = Path("data") / "canonical_universe_retained_snapshot_integration" / "runs"


class RetainedSnapshotIntegrationError(ValueError):
    """The retained snapshot, its manifest, or this adapter's binding contract is invalid."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    if not path.is_file():
        raise RetainedSnapshotIntegrationError(f"required_retained_input_missing:{label}:{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetainedSnapshotIntegrationError(f"retained_input_not_valid_json:{label}:{path}") from exc
    if not isinstance(payload, Mapping):
        raise RetainedSnapshotIntegrationError(f"retained_input_not_a_mapping:{label}")
    return payload


def bind_snapshot_provenance(snapshot_path: Path, manifest_path: Path) -> dict[str, Any]:
    """Verify the retained manifest actually describes the retained Parquet file, and return the
    explicit provenance record every downstream artifact in this run gets bound to.

    This never re-fetches or re-derives the snapshot; it only checks the two retained files are
    mutually consistent (same row count) before trusting the manifest's identity/provenance
    fields, so a mismatched or stale manifest fails closed instead of silently mislabeling C.1/C.2
    output.
    """
    manifest = _load_json(manifest_path, "dnse_universe_snapshot_manifest")
    required_fields = ("snapshot_id", "provider", "dataset", "retrieved_at", "content_hash", "discovered_count")
    missing = [field for field in required_fields if field not in manifest]
    if missing:
        raise RetainedSnapshotIntegrationError(f"snapshot_manifest_missing_fields:{sorted(missing)}")
    if manifest.get("provider") != "DNSE" or manifest.get("dataset") != "instruments":
        raise RetainedSnapshotIntegrationError(
            f"snapshot_manifest_not_a_dnse_instruments_snapshot:provider={manifest.get('provider')}:"
            f"dataset={manifest.get('dataset')}"
        )
    if not snapshot_path.is_file():
        raise RetainedSnapshotIntegrationError(f"required_retained_input_missing:dnse_universe_snapshot:{snapshot_path}")
    frame = pd.read_parquet(snapshot_path)
    if len(frame) != manifest["discovered_count"]:
        raise RetainedSnapshotIntegrationError(
            f"snapshot_row_count_does_not_match_manifest:file_rows={len(frame)}:"
            f"manifest_discovered_count={manifest['discovered_count']}"
        )
    return {
        "snapshot_path": str(snapshot_path),
        "manifest_path": str(manifest_path),
        "snapshot_id": manifest["snapshot_id"],
        "content_hash": manifest["content_hash"],
        "provider": manifest["provider"],
        "dataset": manifest["dataset"],
        "source_reference": manifest.get("source_reference"),
        "retrieved_at": manifest["retrieved_at"],
        "declared_total": manifest.get("declared_total"),
        "discovered_count": manifest["discovered_count"],
        "by_instrument_class": dict(manifest.get("by_instrument_class") or {}),
    }


def _tier_snapshot(c2_result: Mapping[str, Any], tier: str) -> Mapping[str, Any]:
    return next(item for item in c2_result["snapshots"] if item["universe_tier"] == tier and item["tier_scope"] is None)


def _tier_summary(snapshot: Mapping[str, Any], *, with_reasons: bool = True) -> dict[str, Any]:
    summary = {
        "included": snapshot["included_count"], "excluded": snapshot["excluded_count"],
        "unknown": snapshot["unknown_count"], "not_applicable": snapshot["not_applicable_count"],
        "total": snapshot["total_count"],
    }
    if with_reasons:
        summary["excluded_by_reason"] = dict(snapshot["excluded_by_reason"])
        summary["unknown_by_reason"] = dict(snapshot["unknown_by_reason"])
    return summary


def build_from_retained_snapshot(
    *, dnse_universe_snapshot: Path | str, dnse_universe_manifest: Path | str, output_root: Path | str,
    as_of_session: str, generated_at: str,
) -> dict[str, Any]:
    """The whole adapter: bind provenance, run C.1, run C.2, summarize -- no network, no
    discover_universe(). Both builders are called exactly as their own CLIs already would be."""
    snapshot_path = Path(dnse_universe_snapshot)
    manifest_path = Path(dnse_universe_manifest)
    provenance = bind_snapshot_provenance(snapshot_path, manifest_path)

    c1_built = c1.build_from_retained_files(dnse_input=snapshot_path, output_root=output_root)
    c2_built = c2.build_from_explicit_artifacts(
        c1_artifact_path=Path(c1_built["artifact"]["path"]), output_root=output_root,
        as_of_session=as_of_session, generated_at=generated_at,
    )
    c2_result = c2_built["result"]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "canonical_universe_retained_snapshot_integration",
        "source_snapshot_provenance": provenance,
        "c1_artifact_id": c1_built["result"]["artifact_id"],
        "c1_content_hash": c1_built["result"]["content_hash"],
        "c1_artifact_path": c1_built["artifact"]["path"],
        "c2_artifact_id": c2_result["artifact_id"],
        "c2_content_hash": c2_result["content_hash"],
        "c2_artifact_path": c2_built["artifact"]["path"],
        "as_of_session": as_of_session,
        "generated_at": generated_at,
        "reconciliation_summary": {
            "master_observed": _tier_summary(_tier_snapshot(c2_result, c2.MASTER_OBSERVED), with_reasons=False),
            "listed_equity_candidate": _tier_summary(_tier_snapshot(c2_result, c2.LISTED_EQUITY_CANDIDATE)),
            "active_universe": _tier_summary(_tier_snapshot(c2_result, c2.ACTIVE_UNIVERSE)),
        },
    }
    content_hash = _hash(payload)
    result = {**payload, "content_hash": content_hash,
             "artifact_id": f"canonical-universe-retained-snapshot-integration:{content_hash}"}
    return {"result": result, "artifact": write_integration_summary(output_root, result),
           "c1": c1_built, "c2": c2_built}


def artifact_path(output_root: Path | str, content_hash: str) -> Path:
    return Path(output_root) / STORE_RELATIVE / f"{content_hash}.json"


def write_integration_summary(output_root: Path | str, result: Mapping[str, Any]) -> dict[str, Any]:
    expected = _hash({key: value for key, value in result.items() if key not in {"content_hash", "artifact_id"}})
    if result.get("content_hash") != expected:
        raise RetainedSnapshotIntegrationError("integration_summary_content_hash_invalid")
    path = artifact_path(output_root, expected)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing == dict(result):
            return {"path": str(path), "written": False, "reason": "already_present_identical", "content_hash": expected}
        raise RetainedSnapshotIntegrationError("content_addressed_artifact_collision")
    atomic_write_json(path, dict(result))
    return {"path": str(path), "written": True, "content_hash": expected}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dnse-universe-snapshot", type=Path, required=True,
                        help="Retained snapshot Parquet from tools/discover_market_universe.py. Never fetched here.")
    parser.add_argument("--dnse-universe-manifest", type=Path, required=True,
                        help="That snapshot's own retained .manifest.json (same run).")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--as-of-session", required=True)
    parser.add_argument("--generated-at", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    built = build_from_retained_snapshot(
        dnse_universe_snapshot=args.dnse_universe_snapshot, dnse_universe_manifest=args.dnse_universe_manifest,
        output_root=args.output_root, as_of_session=args.as_of_session, generated_at=args.generated_at,
    )
    print(_canonical_json(built["result"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
