"""Build the exact-session trusted subset from retained canonical + statement evidence.

This adapter does not call ``export_ai_bundle.py``.  That exporter is bound to the
legacy VCI market-data chain (``vn_stock.db`` OHLCV calendar, ``ta_signals.csv``,
``live_universe_status=live``).  The canonical 2026-08-26 runtime has none of those
on-session, and this milestone must not re-run DNSE or candle_scan.

Sidecar construction reuses ``statement_taxonomy_sidecar.build_sidecar`` against
retained ``data_bctc/*_balance_sheet_quarter.parquet`` payloads.  Those payloads are
provider-research statement vocabularies (source remains VCI); they are never
relabelled as official and never copied from a previous session's sidecar JSON.

``session_identity`` on the sidecar is packaging: ``records_fingerprint`` excludes it.
A new market session therefore requires a rebuild with the new envelope, not a field
stamp on yesterday's bytes.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping

from altman_applicability import evaluate_altman_applicability
from atomic_io import atomic_copy_file, atomic_write_json
from canonical_dashboard_runtime_release import (
    CanonicalRuntimeReleaseError,
    _source_paths,
)
from export_ai_bundle import (
    DEFAULT_TICKERS,
    PRODUCER_BUNDLE_CONTRACT_VERSION,
    TRUSTED_ARTIFACT_NAMESPACE,
    TRUSTED_SUBSET_SCHEMA_VERSION,
    build_trusted_subset_proof,
)
from financial_entity_applicability import load_entity_profiles
from statement_taxonomy_sidecar import (
    SIDECAR_FILENAME,
    build_sidecar,
    resolve_entity_authority,
    sidecar_provenance,
    resolve_taxonomy,
)
from trusted_subset_contract import TRUSTED_SUBSET_ARTIFACTS, sha256_file, verify_trusted_subset

CONTRACT_VERSION = "canonical_trusted_subset_release/v1"
TRUSTED_FILES = tuple(TRUSTED_SUBSET_ARTIFACTS)
SELF_UNHASHABLE = "bundle_manifest.json"
PERIOD_RE = re.compile(r"^(\d{4})(?:-Q([1-4]))?$")


class CanonicalTrustedSubsetError(RuntimeError):
    pass


def _session_generated_at(session: str) -> str:
    return f"{session}T00:00:00+00:00"


def _parse_session(session: str) -> date:
    try:
        return date.fromisoformat(session)
    except ValueError as exc:
        raise CanonicalTrustedSubsetError(f"EXPLICIT_YYYY_MM_DD_SESSION_REQUIRED:{session}") from exc


def reporting_period_end(period: str) -> date | None:
    match = PERIOD_RE.fullmatch(str(period or "").strip())
    if not match:
        return None
    year = int(match.group(1))
    quarter = match.group(2)
    if quarter is None:
        return date(year, 12, 31)
    month = int(quarter) * 3
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def load_live_rows(runtime_root: Path) -> dict[str, dict[str, str]]:
    path = runtime_root / "screen_snapshot_live.csv"
    if not path.is_file():
        raise CanonicalTrustedSubsetError("LIVE_SNAPSHOT_MISSING")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise CanonicalTrustedSubsetError("LIVE_SNAPSHOT_EMPTY")
    by_ticker: dict[str, dict[str, str]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker:
            by_ticker[ticker] = row
    return by_ticker


def _require_canonical_session(producer_root: Path, runtime_root: Path, session: str) -> dict[str, Any]:
    _parse_session(session)
    try:
        _source_paths(producer_root, session)
    except CanonicalRuntimeReleaseError as exc:
        raise CanonicalTrustedSubsetError(str(exc)) from exc
    manifest_path = runtime_root / SELF_UNHASHABLE
    if not manifest_path.is_file():
        raise CanonicalTrustedSubsetError("CANONICAL_RUNTIME_MANIFEST_MISSING")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CanonicalTrustedSubsetError("CANONICAL_RUNTIME_MANIFEST_UNREADABLE") from exc
    freshness = (manifest.get("freshness") or {}).get("reference_session")
    if freshness != session:
        raise CanonicalTrustedSubsetError(
            f"MARKET_SESSION_MISMATCH:manifest={freshness!r} expected={session!r}"
        )
    analysis = json.loads((runtime_root / "analysis_latest.json").read_text(encoding="utf-8"))
    observed = (analysis.get("summary") or {}).get("session_date")
    if observed != session:
        raise CanonicalTrustedSubsetError(
            f"MARKET_SESSION_MISMATCH:analysis_latest={observed!r} expected={session!r}"
        )
    return manifest


def _reject_relabeled_sidecar(existing: Mapping[str, Any] | None, session: str, generated_at: str) -> None:
    if not isinstance(existing, Mapping):
        return
    if existing.get("session_identity") == session and existing.get("generated_at") != generated_at:
        raise CanonicalTrustedSubsetError(
            "SIDECAR_RELABEL_REJECTED:existing sidecar claims this session without a rebuild envelope"
        )


def _assert_no_lookahead(sidecar: Mapping[str, Any], session: str) -> None:
    boundary = _parse_session(session)
    for record in sidecar.get("records") or []:
        if not isinstance(record, Mapping):
            raise CanonicalTrustedSubsetError("SIDECAR_RECORD_MALFORMED")
        for period in record.get("observed_period_range") or []:
            end = reporting_period_end(str(period))
            if end is None:
                raise CanonicalTrustedSubsetError(f"UNPARSEABLE_REPORTING_PERIOD:{period}")
            if end > boundary:
                raise CanonicalTrustedSubsetError(
                    f"LOOKAHEAD_FINANCIAL_EVIDENCE:{record.get('ticker')}:{period}"
                )


def _assert_required_taxonomy(sidecar: Mapping[str, Any], tickers: list[str]) -> None:
    present = {str(record.get("ticker") or "").upper() for record in sidecar.get("records") or []}
    missing = [ticker for ticker in tickers if ticker not in present]
    if missing:
        raise CanonicalTrustedSubsetError(
            "MISSING_REQUIRED_TAXONOMY_EVIDENCE:" + ",".join(missing)
        )


def _distress(entity_type: str | None, industry: str | None, taxonomy: str | None) -> dict[str, Any]:
    applicability = evaluate_altman_applicability(entity_type, industry, taxonomy)
    status = applicability["applicability"]
    if status == "eligible":
        status = "insufficient_evidence"
    payload: dict[str, Any] = {
        "status": status,
        "score": None,
        "zone": None,
        "applicability": {"reason": applicability.get("reason")},
    }
    if status == "insufficient_evidence":
        payload["missing_inputs"] = ["qualified_official_financial_identities"]
    return payload


def _snapshot(row: Mapping[str, str], session: str) -> dict[str, Any]:
    observed = str(row.get("date") or "").strip()
    if observed != session:
        raise CanonicalTrustedSubsetError(
            f"MARKET_SESSION_MISMATCH:snapshot={observed!r} ticker={row.get('ticker')!r}"
        )
    return {
        "date": session,
        "ticker": str(row.get("ticker") or "").upper(),
        "close": row.get("close"),
        "exchange": row.get("exchange"),
        "industry": row.get("industry"),
        "canonical_observation_status": row.get("canonical_observation_status"),
        "canonical_price_basis": row.get("canonical_price_basis"),
        "canonical_field_availability": row.get("canonical_field_availability"),
    }


def _build_entries(
    tickers: list[str],
    live_rows: Mapping[str, Mapping[str, str]],
    sidecar: Mapping[str, Any],
    session: str,
    profiles: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        row = live_rows.get(ticker)
        if row is None:
            entries[ticker] = {"snapshot": None, "warnings": ["snapshot_missing"]}
            continue
        taxonomy = resolve_taxonomy(sidecar, ticker)
        entity_type = profiles.get(ticker)
        authority = resolve_entity_authority(entity_type, taxonomy)
        entries[ticker] = {
            "entity_type": entity_type,
            "snapshot": _snapshot(row, session),
            "ta_signal": None,
            "warnings": ["canonical_trusted_subset:legacy_ta_signals_not_on_session"],
            "statement_taxonomy_evidence": {
                "authority_level": "generated_evidence",
                "statement_taxonomy": taxonomy,
                "entity_type_authority": authority["authority"],
                "resolved_entity_type": authority["entity_type"],
                "resolution_reason": authority["reason"],
                "record": sidecar_provenance(sidecar, ticker),
                "limitations": [
                    "Generated statement taxonomy observes the reporting TEMPLATE a filing uses; "
                    "it is not a manually verified issuer_entity_type.",
                    "Retained data_bctc payloads remain provider-research (VCI) statement "
                    "vocabularies; they are not promoted to official financial fact authority.",
                ],
            },
            "financial_distress_evidence": _distress(entity_type, row.get("industry"), taxonomy),
            "relative_valuation": {"methods": {}},
        }
    return entries


def _write_trusted_files(
    staging: Path,
    *,
    session: str,
    generated_at: str,
    tickers: list[str],
    entries: Mapping[str, dict[str, Any]],
    sidecar: Mapping[str, Any],
    canonical_manifest: Mapping[str, Any],
) -> dict[str, str]:
    bundle = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "reference_session_date": session,
        "tickers_requested": list(tickers),
        "price_basis": "unknown",
        "price_basis_verified": False,
        "volume_basis": "unknown",
        "volume_basis_verified": False,
        "is_actionable": False,
        "freshness": {
            "reference_session": session,
            "status": "fresh",
            "blocked": False,
            "stale": [],
            "unknown": [],
            "allow_stale": False,
        },
        "canonical_sources": {
            "contract_version": CONTRACT_VERSION,
            "runtime_release": canonical_manifest.get("release_contract"),
        },
        "tickers": dict(entries),
    }
    focus = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "reference_session_date": session,
        "tickers_requested": list(tickers),
        "price_basis": "unknown",
        "price_basis_verified": False,
        "volume_basis": "unknown",
        "volume_basis_verified": False,
        "is_actionable": False,
        "tickers": {ticker: {"snapshot": (entries[ticker].get("snapshot"))} for ticker in tickers},
    }
    atomic_write_json(staging / "analysis_bundle.json", bundle)
    atomic_write_json(staging / "focus_extract.json", focus)
    atomic_write_json(staging / SIDECAR_FILENAME, sidecar)
    artifacts = {
        "analysis_bundle.json": sha256_file(staging / "analysis_bundle.json"),
        "focus_extract.json": sha256_file(staging / "focus_extract.json"),
        SIDECAR_FILENAME: sha256_file(staging / SIDECAR_FILENAME),
    }
    payload = json.loads((staging / "analysis_bundle.json").read_text(encoding="utf-8"))
    proof = build_trusted_subset_proof(
        tickers, session, generated_at, artifacts["analysis_bundle.json"], payload.get("tickers") or {},
        {"price_basis": "unknown", "price_basis_verified": False,
         "volume_basis": "unknown", "volume_basis_verified": False},
        session_artifacts={
            "focus_extract.json": artifacts["focus_extract.json"],
            SIDECAR_FILENAME: artifacts[SIDECAR_FILENAME],
        },
    )
    if proof is None:
        raise CanonicalTrustedSubsetError("TRUSTED_SUBSET_PROOF_EMPTY")
    manifest = {
        "schema_version": TRUSTED_SUBSET_SCHEMA_VERSION,
        "producer_contract_version": PRODUCER_BUNDLE_CONTRACT_VERSION,
        "trusted_artifact_namespace": list(TRUSTED_ARTIFACT_NAMESPACE),
        "statement_taxonomy_sidecar": {
            "present": True,
            "records_fingerprint": sidecar.get("records_fingerprint"),
            "input_fingerprint": sidecar.get("input_fingerprint"),
            "session_identity": sidecar.get("session_identity"),
            "authority_level": "generated_evidence",
        },
        "generated_at": generated_at,
        "tickers": list(tickers),
        "freshness": {
            "reference_session": session,
            "status": "fresh",
            "blocked": False,
            "stale": [],
            "unknown": [],
            "allow_stale": False,
        },
        "price_basis": "unknown",
        "price_basis_verified": False,
        "is_actionable": False,
        "volume_basis": "unknown",
        "volume_basis_verified": False,
        "trusted_subset": proof,
        "canonical_runtime_release": {
            "release_contract": canonical_manifest.get("release_contract"),
            "lineage": canonical_manifest.get("lineage"),
        },
    }
    atomic_write_json(staging / SELF_UNHASHABLE, manifest)
    artifacts[SELF_UNHASHABLE] = sha256_file(staging / SELF_UNHASHABLE)
    return artifacts


def _verify_consumer(staging: Path, consumer_root: Path) -> None:
    if str(consumer_root) not in __import__("sys").path:
        __import__("sys").path.insert(0, str(consumer_root))
    from builders.build_ticker_context import verify_exact_session_bundle

    bundle_path = staging / "analysis_bundle.json"
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    manifest = json.loads((staging / SELF_UNHASHABLE).read_text(encoding="utf-8"))
    ok, reason = verify_exact_session_bundle(bundle_path, payload, manifest)
    if not ok:
        raise CanonicalTrustedSubsetError(f"CONSUMER_EXACT_SESSION_REJECTED:{reason}")


def materialize_canonical_trusted_subset(
    producer_root: Path,
    runtime_root: Path,
    session: str,
    *,
    output_root: Path | None = None,
    consumer_root: Path | None = None,
    tickers: list[str] | None = None,
) -> dict[str, Any]:
    producer_root = Path(producer_root).resolve()
    runtime_root = Path(runtime_root).resolve()
    output_root = Path(output_root or runtime_root).resolve()
    consumer_root = Path(consumer_root or producer_root.parent / "ai-core-private").resolve()
    names = list(tickers or DEFAULT_TICKERS)
    generated_at = _session_generated_at(session)

    canonical_manifest = _require_canonical_session(producer_root, runtime_root, session)
    live_rows = load_live_rows(runtime_root)
    proven = [ticker for ticker in names if ticker in live_rows]
    if not proven:
        raise CanonicalTrustedSubsetError("NO_CURRENT_SESSION_SNAPSHOTS")
    for ticker in proven:
        observed = str(live_rows[ticker].get("date") or "")
        if observed != session:
            raise CanonicalTrustedSubsetError(
                f"MARKET_SESSION_MISMATCH:live={observed!r} ticker={ticker}"
            )

    existing_sidecar_path = output_root / SIDECAR_FILENAME
    existing = None
    if existing_sidecar_path.is_file():
        try:
            existing = json.loads(existing_sidecar_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = None
    _reject_relabeled_sidecar(existing, session, generated_at)

    if not (runtime_root / "data_bctc").is_dir():
        raise CanonicalTrustedSubsetError("STATEMENT_PAYLOAD_ROOT_MISSING")
    sidecar = build_sidecar(
        runtime_root,
        generated_at=generated_at,
        session_identity=session,
        producer_contract_version=PRODUCER_BUNDLE_CONTRACT_VERSION,
    )
    if not sidecar["reconciliation"]["inputs_fully_accounted"]:
        raise CanonicalTrustedSubsetError("SIDECAR_INPUTS_NOT_ACCOUNTED")
    _assert_no_lookahead(sidecar, session)
    _assert_required_taxonomy(sidecar, proven)

    profiles = load_entity_profiles(producer_root / "config" / "ticker_entity_profiles.csv")
    entries = _build_entries(names, live_rows, sidecar, session, profiles)

    staging = Path(tempfile.mkdtemp(prefix=".canonical-trusted-stage-", dir=output_root.parent))
    backup = Path(tempfile.mkdtemp(prefix=".canonical-trusted-backup-", dir=output_root.parent))
    try:
        artifacts = _write_trusted_files(
            staging,
            session=session,
            generated_at=generated_at,
            tickers=names,
            entries=entries,
            sidecar=sidecar,
            canonical_manifest=canonical_manifest,
        )
        report = verify_trusted_subset(staging)
        if not report.ready:
            raise CanonicalTrustedSubsetError("TRUSTED_SUBSET_HASH_MISMATCH:" + ";".join(report.problems))
        _verify_consumer(staging, consumer_root)
        output_root.mkdir(parents=True, exist_ok=True)
        for name in TRUSTED_FILES:
            target = output_root / name
            if target.exists():
                shutil.copy2(target, backup / name)
        try:
            for name in TRUSTED_FILES:
                atomic_copy_file(staging / name, output_root / name)
        except Exception:
            for name in TRUSTED_FILES:
                old = backup / name
                target = output_root / name
                if old.exists():
                    atomic_copy_file(old, target)
                elif target.exists():
                    target.unlink()
            raise
        final = verify_trusted_subset(output_root)
        if not final.ready:
            raise CanonicalTrustedSubsetError("PROMOTED_TRUSTED_SUBSET_HASH_MISMATCH:" + ";".join(final.problems))
        return {
            "session": session,
            "generated_at": generated_at,
            "contract_version": CONTRACT_VERSION,
            "tickers": names,
            "sidecar_records": len(sidecar.get("records") or []),
            "records_fingerprint": sidecar.get("records_fingerprint"),
            "artifacts": artifacts,
            "trusted_subset_ready": True,
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
