"""Materialize the Dashboard runtime input contract from retained canonical evidence.

This is deliberately a small producer-side projection.  It never acquires data and it
does not call any legacy indicator or scoring program.  A release is assembled in a
sibling staging directory, validated through ``release_session_contract``, then its
governed files are atomically promoted with the authority manifest last.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from atomic_io import atomic_copy_file, atomic_write_file, atomic_write_json, validate_csv_file
from daily_research_session_operations import load_registry
import release_session_contract
import dashboard_home_summary
import investment_decision_workspace_projection as workspace_contract
import screener_master_projection as screener_contract

CONTRACT_VERSION = "canonical_dashboard_runtime_release/v1"
REQUIRED_INPUTS = ("descriptive", "screening", "tactical", "triage", "official_universe")
RELEASE_FILES = ("screen_snapshot.csv", "screen_snapshot_live.csv", "market_breadth.csv",
                 "analysis_latest.json", "data/investment_decision_workspace.json",
                 "data/screener_master_projection.json", "data/dashboard_home_summary.json",
                 "bundle_manifest.json")
RELEASE_SESSION_FILES = ("screen_snapshot.csv", "market_breadth.csv", "analysis_latest.json",
                         "screen_snapshot_live.csv")

# Preserve the established screener column surface.  Fields which the retained canonical
# contract does not support are emitted blank, never copied from an older runtime release.
SNAPSHOT_FIELDS = (
    "ticker", "date", "close", "chg_today_pct", "gtgd20_ty", "rel_vol", "rsi14", "macd_hist",
    "bb_pctb", "atr_pct", "above_sma50", "above_sma200", "golden_cross", "pct_from_52w_high",
    "near_52w_high", "pct_above_52w_low", "ret_1m", "ret_3m", "ret_6m", "ret_12m", "structure",
    "dist_swing_low_pct", "source_generated_at", "exchange", "industry", "foreign_room_pct", "pe",
    "pb", "roe", "free_float_est", "margin_status", "latest_price_date", "reference_market_date",
    "days_stale", "instrument_type", "listing_exchange", "listing_source", "listing_snapshot_hash",
    "live_universe_status", "live_universe_reason", "is_live", "rs_rating",
    "canonical_observation_status", "canonical_price_basis", "canonical_field_availability",
)


class CanonicalRuntimeReleaseError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CanonicalRuntimeReleaseError(f"RETAINED_SOURCE_UNREADABLE:{path}") from exc
    if not isinstance(value, dict):
        raise CanonicalRuntimeReleaseError(f"RETAINED_SOURCE_NOT_OBJECT:{path}")
    return value


def _exchange(value: object) -> str:
    normalized = str(value or "").strip().upper()
    return {"HOSE": "HSX", "HCM": "HSX", "HNX": "HNX", "UPCOM": "UPCOM", "UPX": "UPCOM"}.get(normalized, "DELISTED")


def _source_paths(root: Path, session: str) -> tuple[dict[str, tuple[Path, dict[str, Any]]], dict[str, Any]]:
    registry = load_registry(root)
    completed = (registry.get("completed_sessions") or {}).get(session)
    if not isinstance(completed, Mapping) or completed.get("status") != "COMPLETED_RETAINED_EVIDENCE":
        raise CanonicalRuntimeReleaseError(f"SESSION_NOT_COMPLETED_RETAINED_EVIDENCE:{session}")
    entries = (registry.get("sessions") or {}).get(session)
    if not isinstance(entries, Mapping):
        raise CanonicalRuntimeReleaseError(f"SESSION_REGISTRY_ENTRY_MISSING:{session}")
    result: dict[str, tuple[Path, dict[str, Any]]] = {}
    for name in REQUIRED_INPUTS:
        entry = entries.get(name)
        if not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str):
            raise CanonicalRuntimeReleaseError(f"REQUIRED_CANONICAL_SOURCE_MISSING:{name}")
        path = root / str(entry["path"])
        source = _load(path)
        expected = entry.get("artifact_identity")
        if not expected or source.get("artifact_identity") != expected:
            raise CanonicalRuntimeReleaseError(f"CANONICAL_SOURCE_IDENTITY_MISMATCH:{name}")
        if name in ("descriptive", "screening", "tactical") and source.get("session") != session:
            raise CanonicalRuntimeReleaseError(f"CANONICAL_SOURCE_SESSION_MISMATCH:{name}")
        result[name] = (path, source)
    return result, registry


def _producer_run(
    root: Path, session: str, sources: Mapping[str, tuple[Path, dict[str, Any]]], *, run_identity: str | None = None,
) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for manifest_path in (root / "operations-review" / "daily-producer-runs-v1" / session).glob("*/run_manifest.json"):
        manifest = _load(manifest_path)
        if manifest.get("target_market_session") == session:
            candidates.append((manifest_path, manifest))
    if run_identity is not None:
        candidates = [(path, manifest) for path, manifest in candidates if manifest.get("run_identity") == run_identity]
    if len(candidates) != 1:
        suffix = f":run_identity={run_identity}" if run_identity is not None else ""
        raise CanonicalRuntimeReleaseError(f"DAILY_PRODUCER_RUN_AMBIGUOUS_OR_MISSING:{session}:count={len(candidates)}{suffix}")
    manifest_path, manifest = candidates[0]
    for name in ("descriptive", "screening", "tactical", "triage"):
        actual = ((manifest.get("upstream_artifact_identities") or {}).get(name) or {}).get("artifact_identity")
        expected = sources[name][1].get("artifact_identity")
        if actual != expected:
            raise CanonicalRuntimeReleaseError(f"DAILY_PRODUCER_LINEAGE_MISMATCH:{name}")
    bundle_path = manifest_path.parent / "ai_research_session_bundle.json"
    bundle = _load(bundle_path)
    if bundle.get("session") != session:
        raise CanonicalRuntimeReleaseError("DAILY_PRODUCER_BUNDLE_SESSION_MISMATCH")
    expected_hash = ((manifest.get("ai_delivery") or {}).get("ai_research_session_bundle.json") or {}).get("sha256")
    if expected_hash and expected_hash != _sha256(bundle_path):
        raise CanonicalRuntimeReleaseError("DAILY_PRODUCER_BUNDLE_HASH_MISMATCH")
    return manifest_path, manifest, bundle_path, bundle


def _p3_snapshot(root: Path, session: str, sources: Mapping[str, tuple[Path, dict[str, Any]]]) -> dict[str, Any]:
    """Resolve P3F9B under the frozen descriptive input's own live-acquisition attempt root when
    one exists; otherwise fall back to the exact session-derived retained scaleout directory that
    a reused-retained-evidence session (never a live attempt) still deterministically produces.
    Both roots are narrowed to one session-identity-verified file -- never a latest-mtime or
    cross-session glob.
    """
    descriptive_path = sources["descriptive"][0]
    attempt_root = next((parent for parent in descriptive_path.parents if parent.name.startswith("post-close-attempt-")), None)
    search_root = attempt_root or (root / "operations-review" / f"p3f9b-market-wide-exact-session-scaleout-{session.replace('-', '')}")
    if not search_root.is_dir():
        raise CanonicalRuntimeReleaseError("FROZEN_DESCRIPTIVE_ATTEMPT_ROOT_MISSING")
    candidates = []
    for path in search_root.glob("**/p3f9b_mva_exact_session_snapshot.json"):
        source = _load(path)
        if source.get("resolved_completed_session") == session and source.get("retained_snapshot_session") == session:
            candidates.append(source)
    if len(candidates) != 1:
        raise CanonicalRuntimeReleaseError(f"EXACT_SESSION_SNAPSHOT_AMBIGUOUS_OR_MISSING:{session}:count={len(candidates)}")
    return candidates[0]


def _verify_retained_tier_lineage(root: Path, session: str, run_manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    """Cross-check an already-completed tier handoff when replaying a retained session.

    Future one-command runs materialize before tier construction, so absence is valid there;
    a present handoff is nevertheless governed evidence and must agree exactly.
    """
    path = root / "operations-review" / "canonical-post-close-v1" / session / "session_handoff_bundle.json"
    if not path.is_file():
        return None
    handoff = _load(path)
    if handoff.get("session") != session or (handoff.get("market_session_proof") or {}).get("resolved_completed_session") != session:
        raise CanonicalRuntimeReleaseError("TIER_HANDOFF_SESSION_MISMATCH")
    # A normal Daily invocation deliberately creates a new immutable Producer run
    # for the same retained session.  The older tier handoff is therefore context,
    # not the runtime release's Producer-run authority.  It remains usable only
    # when every required upstream evidence identity agrees with the exact current
    # run; otherwise a historical handoff could silently mix source inputs.
    handoff_sources = handoff.get("upstream_evidence_identities") or {}
    run_sources = run_manifest.get("upstream_artifact_identities") or {}
    for name in ("descriptive", "screening", "tactical", "triage"):
        observed = (handoff_sources.get(name) or {}).get("artifact_identity")
        expected = (run_sources.get(name) or {}).get("artifact_identity")
        if not expected or observed != expected:
            raise CanonicalRuntimeReleaseError(f"TIER_HANDOFF_SOURCE_LINEAGE_MISMATCH:{name}")
    return {"sha256": _sha256(path), "path": str(path.relative_to(root)),
            "retained_daily_producer_run_identity": (handoff.get("daily_producer") or {}).get("run_identity"),
            "runtime_daily_producer_run_identity": run_manifest.get("run_identity"),
            "source_lineage_status": "PASS",
            "current_research_packet_identity": handoff.get("current_research_packet_identity"),
            "prospective_cohort_snapshot_identity": handoff.get("prospective_cohort_snapshot_identity")}


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    # csv.writer provides deterministic quoting and Windows-safe newline control.
    import io
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write_file(path, buffer.getvalue(), validator=lambda candidate: validate_csv_file(candidate, fields))


def _stage_workspace(root: Path, session: str, staging: Path, run_manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Bind only the selected Producer run's retained operation; never rebuild semantics."""
    operation = run_manifest.get("daily_session_operation") or {}
    directory, operation_identity = operation.get("directory"), operation.get("identity")
    if not isinstance(directory, str) or not directory or not operation_identity:
        raise CanonicalRuntimeReleaseError("WORKSPACE_OPERATION_LINEAGE_MISSING")
    operation_dir = root / directory
    operation_manifest_path = operation_dir / "run_manifest.json"
    operation_manifest = _load(operation_manifest_path)
    if operation_manifest.get("operation_identity") != operation_identity:
        raise CanonicalRuntimeReleaseError("WORKSPACE_OPERATION_IDENTITY_MISMATCH")
    if operation_manifest.get("market_session") != session:
        raise CanonicalRuntimeReleaseError("WORKSPACE_OPERATION_SESSION_MISMATCH")
    projections = run_manifest.get("current_product_projections") or {}
    declared = projections.get("workspace") or {}
    if projections.get("status") != "MATERIALIZED" or projections.get("session") != session:
        raise CanonicalRuntimeReleaseError("WORKSPACE_PRODUCER_MATERIALIZATION_UNAVAILABLE")
    source = operation_dir / "investment_decision_workspace_projection.json"
    if not source.is_file():
        raise CanonicalRuntimeReleaseError(f"WORKSPACE_EXACT_SESSION_PROJECTION_MISSING:{source}")
    # Validate the staged bytes, so the bytes checked are exactly those promoted.
    target = staging / "data/investment_decision_workspace.json"
    atomic_copy_file(source, target)
    payload = _load(target)
    if payload.get("schema_version") != workspace_contract.SCHEMA_VERSION:
        raise CanonicalRuntimeReleaseError("WORKSPACE_SCHEMA_VERSION_MISMATCH")
    if payload.get("contract_version") != workspace_contract.CONTRACT_VERSION:
        raise CanonicalRuntimeReleaseError("WORKSPACE_CONTRACT_VERSION_MISMATCH")
    if payload.get("as_of_session") != session or declared.get("as_of_session") != session:
        raise CanonicalRuntimeReleaseError("WORKSPACE_SESSION_MISMATCH")
    cards, coverage = payload.get("cards"), payload.get("coverage")
    if not isinstance(cards, dict) or not cards:
        raise CanonicalRuntimeReleaseError("WORKSPACE_EMPTY_CORPUS")
    if (not isinstance(coverage, dict) or type(coverage.get("ticker_denominator")) is not int
            or coverage["ticker_denominator"] != len(cards)
            or declared.get("ticker_denominator") != len(cards)
            or coverage.get("zero_silent_ticker_drops") is not True):
        raise CanonicalRuntimeReleaseError("WORKSPACE_DENOMINATOR_OR_SILENT_DROP_VIOLATION")
    try:
        identity = workspace_contract.content_identity(payload)
    except (TypeError, ValueError) as exc:
        raise CanonicalRuntimeReleaseError("WORKSPACE_CONTENT_IDENTITY_INVALID") from exc
    if (payload.get("artifact_identity") != identity["artifact_identity"]
            or payload.get("artifact_sha256") != identity["artifact_sha256"]
            or declared.get("artifact_identity") != identity["artifact_identity"]):
        raise CanonicalRuntimeReleaseError("WORKSPACE_CONTENT_IDENTITY_MISMATCH")
    return {"path": source.relative_to(root).as_posix() if source.is_relative_to(root) else str(source),
            "sha256": _sha256(target), **identity,
            "session": session, "operation_identity": operation_identity,
            "operation_manifest_sha256": _sha256(operation_manifest_path),
            "producer_run_identity": run_manifest.get("run_identity"),
            "ticker_denominator": len(cards), "zero_silent_ticker_drops": True}


def _stage_screener_master_projection(
    root: Path, session: str, staging: Path, run_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind the selected Producer run's exact Screener product bytes to the runtime release.

    ``publish_dashboard.py`` validates this projection against the market session before it
    writes the Dashboard.  Keeping it in the same staged release as the Workspace projection
    prevents a previous runtime Screener artifact from being silently reused.
    """
    operation = run_manifest.get("daily_session_operation") or {}
    directory, operation_identity = operation.get("directory"), operation.get("identity")
    if not isinstance(directory, str) or not directory or not operation_identity:
        raise CanonicalRuntimeReleaseError("SCREENER_OPERATION_LINEAGE_MISSING")
    operation_dir = root / directory
    operation_manifest_path = operation_dir / "run_manifest.json"
    operation_manifest = _load(operation_manifest_path)
    if operation_manifest.get("operation_identity") != operation_identity:
        raise CanonicalRuntimeReleaseError("SCREENER_OPERATION_IDENTITY_MISMATCH")
    if operation_manifest.get("market_session") != session:
        raise CanonicalRuntimeReleaseError("SCREENER_OPERATION_SESSION_MISMATCH")
    projections = run_manifest.get("current_product_projections") or {}
    declared = projections.get("screener_master_projection") or {}
    if projections.get("status") != "MATERIALIZED" or projections.get("session") != session:
        raise CanonicalRuntimeReleaseError("SCREENER_PRODUCER_MATERIALIZATION_UNAVAILABLE")
    source = operation_dir / "screener_master_projection.json"
    if not source.is_file():
        raise CanonicalRuntimeReleaseError(f"SCREENER_EXACT_SESSION_PROJECTION_MISSING:{source}")
    target = staging / "data/screener_master_projection.json"
    atomic_copy_file(source, target)
    payload = _load(target)
    if payload.get("schema_version") != screener_contract.SCHEMA_VERSION:
        raise CanonicalRuntimeReleaseError("SCREENER_SCHEMA_VERSION_MISMATCH")
    if payload.get("contract_version") != screener_contract.CONTRACT_VERSION:
        raise CanonicalRuntimeReleaseError("SCREENER_CONTRACT_VERSION_MISMATCH")
    if payload.get("as_of_session") != session or declared.get("as_of_session") != session:
        raise CanonicalRuntimeReleaseError("SCREENER_SESSION_MISMATCH")
    cards, coverage = payload.get("cards"), payload.get("coverage")
    if not isinstance(cards, dict) or not cards:
        raise CanonicalRuntimeReleaseError("SCREENER_EMPTY_CORPUS")
    if (not isinstance(coverage, dict) or type(coverage.get("ticker_denominator")) is not int
            or coverage["ticker_denominator"] != len(cards)
            or (declared.get("denominator") or {}).get("ticker_count") != len(cards)
            or coverage.get("zero_silent_drops") is not True):
        raise CanonicalRuntimeReleaseError("SCREENER_DENOMINATOR_OR_SILENT_DROP_VIOLATION")
    try:
        identity = screener_contract.content_identity(payload)
    except (TypeError, ValueError) as exc:
        raise CanonicalRuntimeReleaseError("SCREENER_CONTENT_IDENTITY_INVALID") from exc
    if (payload.get("artifact_identity") != identity["artifact_identity"]
            or payload.get("artifact_sha256") != identity["artifact_sha256"]
            or declared.get("artifact_identity") != identity["artifact_identity"]):
        raise CanonicalRuntimeReleaseError("SCREENER_CONTENT_IDENTITY_MISMATCH")
    return {"path": source.relative_to(root).as_posix() if source.is_relative_to(root) else str(source),
            "sha256": _sha256(target), **identity,
            "session": session, "operation_identity": operation_identity,
            "operation_manifest_sha256": _sha256(operation_manifest_path),
            "producer_run_identity": run_manifest.get("run_identity"),
            "ticker_denominator": len(cards), "zero_silent_ticker_drops": True}


def _stage_dashboard_home_summary(
    root: Path, session: str, staging: Path, run_manifest: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Bind the selected Producer run's exact Home-summary bytes to the runtime release.

    Mirrors ``_stage_screener_master_projection`` exactly (same operation-lineage,
    session, and content-identity checks): a stale/mismatched Home summary must never
    silently ride along in a release for a different session's Screener projection.

    Returns ``None`` (no lineage, nothing staged, home summary simply absent from this
    release) only for the one genuine backward-compatibility case: a retained Producer
    run manifest from BEFORE DASHBOARD_HOME_SUMMARY_AND_CACHE_BUSTING_V1 existed, whose
    ``current_product_projections`` never declares a ``dashboard_home_summary`` key at
    all. A manifest that DOES declare this axis (any status) is held to the same
    fail-closed bar as every other axis here -- a declared-but-broken summary is a real
    defect, never silently dropped.
    """
    operation = run_manifest.get("daily_session_operation") or {}
    directory, operation_identity = operation.get("directory"), operation.get("identity")
    if not isinstance(directory, str) or not directory or not operation_identity:
        raise CanonicalRuntimeReleaseError("HOME_SUMMARY_OPERATION_LINEAGE_MISSING")
    operation_dir = root / directory
    operation_manifest_path = operation_dir / "run_manifest.json"
    operation_manifest = _load(operation_manifest_path)
    if operation_manifest.get("operation_identity") != operation_identity:
        raise CanonicalRuntimeReleaseError("HOME_SUMMARY_OPERATION_IDENTITY_MISMATCH")
    if operation_manifest.get("market_session") != session:
        raise CanonicalRuntimeReleaseError("HOME_SUMMARY_OPERATION_SESSION_MISMATCH")
    projections = run_manifest.get("current_product_projections") or {}
    if "dashboard_home_summary" not in projections:
        return None
    declared = projections.get("dashboard_home_summary") or {}
    if projections.get("status") != "MATERIALIZED" or projections.get("session") != session:
        raise CanonicalRuntimeReleaseError("HOME_SUMMARY_PRODUCER_MATERIALIZATION_UNAVAILABLE")
    if declared.get("status") != "MATERIALIZED":
        raise CanonicalRuntimeReleaseError("HOME_SUMMARY_NOT_MATERIALIZED")
    source = operation_dir / "dashboard_home_summary.json"
    if not source.is_file():
        raise CanonicalRuntimeReleaseError(f"HOME_SUMMARY_EXACT_SESSION_ARTIFACT_MISSING:{source}")
    target = staging / "data/dashboard_home_summary.json"
    atomic_copy_file(source, target)
    payload = _load(target)
    if payload.get("schema_version") != dashboard_home_summary.SCHEMA_VERSION:
        raise CanonicalRuntimeReleaseError("HOME_SUMMARY_SCHEMA_VERSION_MISMATCH")
    if payload.get("contract_version") != dashboard_home_summary.CONTRACT_VERSION:
        raise CanonicalRuntimeReleaseError("HOME_SUMMARY_CONTRACT_VERSION_MISMATCH")
    if payload.get("as_of_session") != session or declared.get("as_of_session") != session:
        raise CanonicalRuntimeReleaseError("HOME_SUMMARY_SESSION_MISMATCH")
    if not isinstance(payload.get("denominator"), int) or payload["denominator"] <= 0:
        raise CanonicalRuntimeReleaseError("HOME_SUMMARY_EMPTY_DENOMINATOR")
    try:
        identity = dashboard_home_summary.content_identity(payload)
    except (TypeError, ValueError) as exc:
        raise CanonicalRuntimeReleaseError("HOME_SUMMARY_CONTENT_IDENTITY_INVALID") from exc
    if (payload.get("artifact_identity") != identity["artifact_identity"]
            or payload.get("artifact_sha256") != identity["artifact_sha256"]
            or declared.get("artifact_identity") != identity["artifact_identity"]):
        raise CanonicalRuntimeReleaseError("HOME_SUMMARY_CONTENT_IDENTITY_MISMATCH")
    # The Home summary's own bound source (the Screener Master Projection it was derived
    # from, same run) must be the exact same artifact this release already staged above --
    # never a Home summary left over from a different Screener projection.
    screener_lineage_identity = (run_manifest.get("current_product_projections") or {}) \
        .get("screener_master_projection", {}).get("artifact_identity")
    if payload.get("source_artifact_identity") != screener_lineage_identity:
        raise CanonicalRuntimeReleaseError("HOME_SUMMARY_SOURCE_SCREENER_IDENTITY_MISMATCH")
    return {"path": source.relative_to(root).as_posix() if source.is_relative_to(root) else str(source),
            "sha256": _sha256(target), **identity,
            "session": session, "operation_identity": operation_identity,
            "operation_manifest_sha256": _sha256(operation_manifest_path),
            "producer_run_identity": run_manifest.get("run_identity"),
            "denominator": payload["denominator"], "source_artifact_identity": payload.get("source_artifact_identity")}


def _build_release(root: Path, session: str, staging: Path, *, producer_run_identity: str | None = None) -> dict[str, Any]:
    sources, _registry = _source_paths(root, session)
    run_path, run_manifest, bundle_path, producer_bundle = _producer_run(root, session, sources, run_identity=producer_run_identity)
    workspace_lineage = _stage_workspace(root, session, staging, run_manifest)
    screener_lineage = _stage_screener_master_projection(root, session, staging, run_manifest)
    home_summary_lineage = _stage_dashboard_home_summary(root, session, staging, run_manifest)
    tier_lineage = _verify_retained_tier_lineage(root, session, run_manifest)
    snapshot = _p3_snapshot(root, session, sources)
    descriptive = sources["descriptive"][1]
    tactical_records = sources["tactical"][1].get("records") or {}
    official_records = sources["official_universe"][1].get("records") or {}
    exact_records = snapshot.get("records") or {}
    if not isinstance(descriptive.get("records"), Mapping) or not isinstance(exact_records, Mapping):
        raise CanonicalRuntimeReleaseError("CANONICAL_RECORDS_MISSING")

    rows: list[dict[str, Any]] = []
    live_rows: list[dict[str, Any]] = []
    for ticker in sorted(descriptive["records"]):
        exact = exact_records.get(ticker) or {}
        observations = [x for x in (exact.get("observations") or []) if isinstance(x, Mapping) and x.get("session") == session]
        if len(observations) > 1:
            raise CanonicalRuntimeReleaseError(f"MULTIPLE_EXACT_OBSERVATIONS:{ticker}")
        observation = observations[0] if observations else None
        official = official_records.get(ticker) or {}
        tactical = tactical_records.get(ticker) or {}
        row: dict[str, Any] = {field: "" for field in SNAPSHOT_FIELDS}
        row.update({
            "ticker": ticker, "exchange": _exchange(official.get("exchange_or_market")),
            "industry": (descriptive["records"][ticker].get("sector_classification") or {}).get("entity_class") or "",
            "listing_exchange": official.get("exchange_or_market") or "",
            "listing_source": official.get("official_source") or "",
            "instrument_type": official.get("instrument_class_status") or "",
            "live_universe_status": official.get("current_universe_status") or "",
            "is_live": "true" if observation else "false",
            "canonical_observation_status": "EXACT_SESSION_RETAINED" if observation else "UNAVAILABLE_NO_EXACT_SESSION_OBSERVATION",
            "canonical_field_availability": "DIRECT_CANONICAL_MAPPING" if observation else "UNAVAILABLE",
            "structure": tactical.get("ticker_structure_state") or "",
        })
        if observation:
            row.update({
                "date": session, "latest_price_date": session, "reference_market_date": session,
                "close": observation.get("close", ""), "canonical_price_basis": observation.get("price_basis") or "",
                "source_generated_at": observation.get("retrieved_at") or "", "days_stale": 0,
                "chg_today_pct": (tactical.get("signals") or {}).get("return_1d", ""),
            })
            live_rows.append(row.copy())
        rows.append(row)
    if not live_rows:
        raise CanonicalRuntimeReleaseError("NO_EXACT_SESSION_RUNTIME_ROWS")
    _write_csv(staging / "screen_snapshot.csv", SNAPSHOT_FIELDS, rows)
    _write_csv(staging / "screen_snapshot_live.csv", SNAPSHOT_FIELDS, live_rows)

    breadth = descriptive.get("market_breadth") or {}
    required_breadth = ("advancing", "declining", "unchanged")
    if breadth.get("session") != session or any(not isinstance(breadth.get(k), int) for k in required_breadth):
        raise CanonicalRuntimeReleaseError("CANONICAL_BREADTH_UNAVAILABLE_OR_SESSION_MISMATCH")
    _write_csv(staging / "market_breadth.csv", ("group", "date", "n_symbols", "n_up", "n_down", "n_flat", "advance_ratio", "availability"), [{
        "group": "ALL", "date": session, "n_symbols": int(breadth.get("same_session_technical_feature_available_count") or 0),
        "n_up": breadth["advancing"], "n_down": breadth["declining"], "n_flat": breadth["unchanged"],
        "advance_ratio": breadth.get("advance_ratio", ""), "availability": "DIRECT_CANONICAL_MAPPING",
    }])

    lineage = {name: {"artifact_identity": data.get("artifact_identity"), "sha256": _sha256(path), "path": str(path.relative_to(root))}
               for name, (path, data) in sources.items()}
    lineage["daily_producer_run"] = {"run_identity": run_manifest.get("run_identity"), "sha256": _sha256(run_path), "path": str(run_path.relative_to(root))}
    lineage["daily_producer_bundle"] = {"sha256": _sha256(bundle_path), "path": str(bundle_path.relative_to(root))}
    lineage["investment_decision_workspace"] = workspace_lineage
    lineage["screener_master_projection"] = screener_lineage
    if home_summary_lineage is not None:
        lineage["dashboard_home_summary"] = home_summary_lineage
    if tier_lineage:
        lineage["retained_tier_handoff"] = tier_lineage
    analysis = {
        "schema_version": CONTRACT_VERSION, "summary": {"session_date": session, "generated_at": session,
            "n_stocks_live": len(live_rows), "regime": "UNAVAILABLE_CANONICAL_REGIME_NOT_MATERIALIZED",
            "pct_above_ma200": None, "availability": "DIRECT_CANONICAL_MAPPING_WITH_EXPLICIT_UNAVAILABLE_LEGACY_FIELDS"},
        "market": {"breadth": {"n_up": breadth["advancing"], "n_down": breadth["declining"], "n_flat": breadth["unchanged"],
                                    "availability": "DIRECT_CANONICAL_MAPPING"}},
        "scores": {}, "top_stocks": [], "strategies": {},
        "authority_boundary": producer_bundle.get("authority_boundary"), "blocked_dimensions": run_manifest.get("blocked_dimensions"),
        "lineage": lineage,
    }
    atomic_write_json(staging / "analysis_latest.json", analysis)
    # RELEASE_FILES lists every file a NORMAL release stages; dashboard_home_summary is the
    # one entry that can legitimately be absent (a retained pre-migration Producer run -- see
    # _stage_dashboard_home_summary's own None-return contract), so the manifest's own
    # "release_files" record reflects what THIS release actually staged, not the static list.
    staged_release_files = [name for name in RELEASE_FILES if (staging / name).is_file()]
    manifest = {"schema_version": CONTRACT_VERSION, "freshness": {"reference_session": session, "status": "fresh", "blocked": False},
        "release_contract": {"source": "retained_canonical_daily_producer", "session": session,
            "unavailable_legacy_fields": ["historical_indicator_suite", "strict_valuation", "liquidity_sizing_execution", "macro_optional", "explicit_portfolio"]},
        "lineage": lineage, "release_files": staged_release_files}
    atomic_write_json(staging / "bundle_manifest.json", manifest)
    return {"session": session, "lineage": lineage, "live_count": len(live_rows), "snapshot_count": len(rows)}


def materialize_canonical_runtime_release(
    root: Path, runtime_root: Path, session: str, *, producer_run_identity: str | None = None,
) -> dict[str, Any]:
    """Build and validate a retained session release, then promote only governed files.

    No network client is imported or invoked.  A staging failure occurs before any runtime
    write.  Promotion writes the manifest last; if a promotion write fails, backups are
    restored so the runtime is never left as a durable mixed-session release.
    """
    root, runtime_root = Path(root).resolve(), Path(runtime_root).resolve()
    if not session or len(session) != 10:
        raise CanonicalRuntimeReleaseError("EXPLICIT_YYYY_MM_DD_SESSION_REQUIRED")
    runtime_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".canonical-runtime-stage-", dir=runtime_root.parent))
    backup = Path(tempfile.mkdtemp(prefix=".canonical-runtime-backup-", dir=runtime_root.parent))
    try:
        build_kwargs = {"producer_run_identity": producer_run_identity} if producer_run_identity is not None else {}
        result = _build_release(root, session, staging, **build_kwargs)
        report = release_session_contract.resolve_release_session(staging, RELEASE_SESSION_FILES, today=session)
        if not report.ready or report.session != session:
            raise CanonicalRuntimeReleaseError(f"STAGED_RELEASE_SESSION_CONTRACT_FAILED:{report.render()}")
        for name in RELEASE_FILES:
            target = runtime_root / name
            if target.exists():
                (backup / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup / name)
        try:
            for name in (*RELEASE_FILES[:-1], RELEASE_FILES[-1]):
                if not (staging / name).is_file():
                    # Only dashboard_home_summary can legitimately be absent here (a
                    # retained pre-migration Producer run -- see
                    # _stage_dashboard_home_summary's None-return contract). Whatever the
                    # runtime already has for this optional file, if anything, is left
                    # untouched rather than silently dropped or backdated.
                    continue
                validator = validate_csv_file if name.endswith(".csv") else None
                atomic_copy_file(staging / name, runtime_root / name, validator=validator)
        except Exception:
            for name in RELEASE_FILES:
                old = backup / name
                target = runtime_root / name
                if old.exists():
                    atomic_copy_file(old, target)
                elif target.exists():
                    target.unlink()
            raise
        result["release_session_report"] = {"session": report.session, "ready": report.ready, "authority": report.authority}
        return result
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)


HOME_SUMMARY_RESTAGE_DERIVATION = "dashboard_home_summary.build_home_summary(restaged_presentation_screener)"


class _RestageRefused(Exception):
    """Internal: a proposed presentation replacement failed validation -- restage is SKIPPED."""


def _patch_runtime_manifest_after_restage(
    manifest_path: Path, *, session: str,
    workspace_identity: Mapping[str, Any], workspace_sha256: str,
    screener_identity: Mapping[str, Any] | None, screener_sha256: str | None,
    home_summary: Mapping[str, Any] | None = None, home_summary_sha256: str | None = None,
) -> str:
    """Keep ``bundle_manifest.json``'s own lineage record coherent with the just-restaged
    runtime bytes -- see CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1
    section 2: the runtime must never be left with served files whose identity disagrees with
    what its own manifest declares. Additive: the sealed baseline identities are preserved under
    a new ``lineage.presentation_projection`` block rather than silently discarded (and are
    carried forward, never overwritten by restaged ones, when the same session is restaged
    again). Never raises; an unreadable/missing manifest degrades to a reported status.
    """
    if not manifest_path.is_file():
        return "MANIFEST_MISSING"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "MANIFEST_UNREADABLE"
    if not isinstance(manifest, dict):
        return "MANIFEST_NOT_OBJECT"
    lineage = dict(manifest.get("lineage") or {})
    sealed_workspace = dict(lineage.get("investment_decision_workspace") or {})
    sealed_screener = dict(lineage.get("screener_master_projection") or {})
    sealed_home_summary = dict(lineage.get("dashboard_home_summary") or {})
    prior = lineage.get("presentation_projection")
    prior = prior if isinstance(prior, Mapping) and prior.get("session") == session else {}

    def _sealed(key: str, entry: Mapping[str, Any]) -> Any:
        return prior[key] if key in prior else entry.get("artifact_identity")

    restaged_home_summary_identity = (home_summary or {}).get("artifact_identity") or prior.get(
        "restaged_dashboard_home_summary_artifact_identity")
    lineage["presentation_projection"] = {
        "session": session,
        "sealed_workspace_artifact_identity": _sealed("sealed_workspace_artifact_identity", sealed_workspace),
        "sealed_screener_master_projection_artifact_identity": _sealed(
            "sealed_screener_master_projection_artifact_identity", sealed_screener),
        "sealed_dashboard_home_summary_artifact_identity": _sealed(
            "sealed_dashboard_home_summary_artifact_identity", sealed_home_summary),
        "restaged_workspace_artifact_identity": workspace_identity.get("artifact_identity"),
        "restaged_screener_master_projection_artifact_identity": (screener_identity or {}).get("artifact_identity"),
        "restaged_dashboard_home_summary_artifact_identity": restaged_home_summary_identity,
    }
    new_workspace_entry = dict(sealed_workspace)
    new_workspace_entry.update({**workspace_identity, "sha256": workspace_sha256})
    lineage["investment_decision_workspace"] = new_workspace_entry
    if screener_identity is not None and screener_sha256 is not None:
        new_screener_entry = dict(sealed_screener)
        new_screener_entry.update({**screener_identity, "sha256": screener_sha256})
        lineage["screener_master_projection"] = new_screener_entry
    if home_summary is not None and home_summary_sha256 is not None:
        new_home_summary_entry = dict(sealed_home_summary)
        new_home_summary_entry.update({
            "artifact_identity": home_summary["artifact_identity"],
            "artifact_sha256": home_summary["artifact_sha256"],
            "sha256": home_summary_sha256,
            "session": session,
            "denominator": home_summary["denominator"],
            "source_artifact_identity": home_summary["source_artifact_identity"],
            "derivation": HOME_SUMMARY_RESTAGE_DERIVATION,
        })
        lineage["dashboard_home_summary"] = new_home_summary_entry
    manifest["lineage"] = lineage
    try:
        tmp = manifest_path.with_name(manifest_path.name + ".tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(manifest_path)
    except OSError:
        return "MANIFEST_WRITE_FAILED"
    return "PATCHED"


def _validate_presentation_screener(
    payload: Any, *, session: str, runtime_screener: Mapping[str, Any], declared_identity: Any,
) -> dict[str, str]:
    """Same bar ``_stage_screener_master_projection`` holds the sealed Screener to, plus: the
    restaged corpus must keep the runtime's own ticker denominator (a presentation overlay never
    changes the universe) and, when the presentation result declares its Screener identity, the
    bytes on disk must be exactly that artifact."""
    if not isinstance(payload, dict):
        raise _RestageRefused("PRESENTATION_SCREENER_NOT_OBJECT")
    if payload.get("schema_version") != screener_contract.SCHEMA_VERSION:
        raise _RestageRefused("PRESENTATION_SCREENER_SCHEMA_VERSION_MISMATCH")
    if payload.get("contract_version") != screener_contract.CONTRACT_VERSION:
        raise _RestageRefused("PRESENTATION_SCREENER_CONTRACT_VERSION_MISMATCH")
    if payload.get("as_of_session") != session:
        raise _RestageRefused("PRESENTATION_SCREENER_SESSION_MISMATCH")
    cards, coverage = payload.get("cards"), payload.get("coverage")
    if not isinstance(cards, dict) or not cards:
        raise _RestageRefused("PRESENTATION_SCREENER_EMPTY_CORPUS")
    if (not isinstance(coverage, dict) or type(coverage.get("ticker_denominator")) is not int
            or coverage["ticker_denominator"] != len(cards) or coverage.get("zero_silent_drops") is not True):
        raise _RestageRefused("PRESENTATION_SCREENER_DENOMINATOR_OR_SILENT_DROP_VIOLATION")
    if (runtime_screener.get("coverage") or {}).get("ticker_denominator") != len(cards):
        raise _RestageRefused("PRESENTATION_SCREENER_DENOMINATOR_DIVERGES_FROM_RUNTIME")
    try:
        identity = screener_contract.content_identity(payload)
    except (TypeError, ValueError) as exc:
        raise _RestageRefused("PRESENTATION_SCREENER_CONTENT_IDENTITY_INVALID") from exc
    if (payload.get("artifact_identity") != identity["artifact_identity"]
            or payload.get("artifact_sha256") != identity["artifact_sha256"]):
        raise _RestageRefused("PRESENTATION_SCREENER_CONTENT_IDENTITY_MISMATCH")
    if declared_identity is not None and declared_identity != identity["artifact_identity"]:
        raise _RestageRefused("PRESENTATION_SCREENER_IDENTITY_DIVERGES_FROM_PRESENTATION_RESULT")
    return identity


def _derive_restaged_home_summary(
    screener: Mapping[str, Any], *, session: str, fallback_requested_at: Any,
) -> dict[str, Any]:
    """Re-derive the Home summary from the exact restaged Screener through the one governed pure
    builder -- never copy the sealed summary forward past a Screener change. ``requested_at``
    follows the Screener's own (identity-excluded) request timestamp, exactly as the Producer's
    own derivation does, falling back to the baseline summary's only when the Screener has none."""
    requested_at = screener.get("requested_at") or fallback_requested_at
    if not isinstance(requested_at, str) or not requested_at:
        raise _RestageRefused("HOME_SUMMARY_REQUESTED_AT_UNAVAILABLE")
    try:
        summary = dashboard_home_summary.build_home_summary(screener, requested_at=requested_at)
    except Exception as exc:  # noqa: BLE001 - any derivation failure refuses the whole restage
        raise _RestageRefused(f"HOME_SUMMARY_DERIVATION_FAILED:{type(exc).__name__}:{exc}") from exc
    if (not isinstance(summary, dict)
            or summary.get("schema_version") != dashboard_home_summary.SCHEMA_VERSION
            or summary.get("contract_version") != dashboard_home_summary.CONTRACT_VERSION):
        raise _RestageRefused("HOME_SUMMARY_DERIVED_CONTRACT_MISMATCH")
    if summary.get("as_of_session") != session:
        raise _RestageRefused("HOME_SUMMARY_DERIVED_SESSION_MISMATCH")
    if (not isinstance(summary.get("denominator"), int) or summary["denominator"] <= 0
            or summary["denominator"] != len(screener.get("cards") or {})):
        raise _RestageRefused("HOME_SUMMARY_DERIVED_DENOMINATOR_INVALID")
    identity = dashboard_home_summary.content_identity(summary)
    if (summary.get("artifact_identity") != identity["artifact_identity"]
            or summary.get("artifact_sha256") != identity["artifact_sha256"]):
        raise _RestageRefused("HOME_SUMMARY_DERIVED_CONTENT_IDENTITY_MISMATCH")
    if summary.get("source_artifact_identity") != screener.get("artifact_identity"):
        raise _RestageRefused("HOME_SUMMARY_DERIVED_SOURCE_SCREENER_IDENTITY_MISMATCH")
    return summary


def _restore_runtime_bytes(backups: Mapping[Path, bytes | None]) -> None:
    for target, data in backups.items():
        if data is None:
            if target.exists():
                target.unlink()
            continue
        tmp = target.with_name(target.name + ".restore.tmp")
        tmp.write_bytes(data)
        tmp.replace(target)


def restage_runtime_with_presentation_projection(
    runtime_root: Path, root: Path, presentation_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Additively overlay the already-promoted runtime-served Workspace/Screener bytes with the
    post-handoff presentation projection's enriched bytes (same-session Signal Velocity /
    Flow-Price now populated), after ``materialize_canonical_runtime_release`` has already
    promoted the sealed (pre-handoff) copies -- see
    CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1.

    Never touches sealed Producer evidence (the operation/run directories) -- only the
    runtime-served copies under ``runtime_root/data/``. No-op unless the presentation projection
    both succeeded and lineage-verified against the sealed Producer Workspace, and every
    replacement independently re-validates -- any other outcome degrades to SKIPPED and leaves the
    sealed bytes exactly as they were. Never raises.

    The runtime's presentation dependency graph moves as ONE unit
    (DASHBOARD_PRESENTATION_RESTAGE_HOME_SUMMARY_COHERENCE_V1): when the Screener changes, the
    Home summary bound to it is re-derived from that exact Screener, and the whole replacement
    set (Workspace, Screener, Home summary) is fully validated before the first runtime write.
    The manifest lineage is then patched and the result proven coherent; any failure after the
    first write restores every touched runtime file, so the runtime can never be left with an
    enriched Workspace beside a stale Screener, an enriched Screener beside a Home summary bound
    to the sealed one, or bytes disagreeing with ``bundle_manifest.json``.
    """
    if not isinstance(presentation_result, Mapping) or (
        presentation_result.get("status") != "COLLECTED"
        or presentation_result.get("lineage_status") != "VERIFIED_AGAINST_SEALED_PRODUCER_WORKSPACE"
    ):
        return {"status": "SKIPPED", "reason": "PRESENTATION_PROJECTION_UNAVAILABLE_OR_UNVERIFIED"}
    session = presentation_result.get("session")
    path = presentation_result.get("path")
    if not isinstance(path, str) or not path:
        return {"status": "SKIPPED", "reason": "PRESENTATION_PROJECTION_PATH_MISSING"}
    try:
        source_workspace = (Path(root) / path).resolve()
        source_screener = source_workspace.parent / "screener_master_projection.json"
        target_workspace = Path(runtime_root) / "data" / "investment_decision_workspace.json"
        target_screener = Path(runtime_root) / "data" / "screener_master_projection.json"
        target_home_summary = Path(runtime_root) / "data" / "dashboard_home_summary.json"
        manifest_path = Path(runtime_root) / "bundle_manifest.json"
        if not source_workspace.is_file() or not target_workspace.is_file():
            return {"status": "SKIPPED", "reason": "SOURCE_OR_TARGET_WORKSPACE_MISSING"}
        new_payload = json.loads(source_workspace.read_text(encoding="utf-8"))
        current_target_payload = json.loads(target_workspace.read_text(encoding="utf-8"))
        if (new_payload.get("as_of_session") != session
                or current_target_payload.get("as_of_session") != session
                or new_payload.get("contract_version") != workspace_contract.CONTRACT_VERSION):
            return {"status": "SKIPPED", "reason": "SESSION_OR_CONTRACT_MISMATCH"}
        identity = workspace_contract.content_identity(new_payload)
        if new_payload.get("artifact_identity") != identity["artifact_identity"]:
            return {"status": "SKIPPED", "reason": "WORKSPACE_CONTENT_IDENTITY_MISMATCH"}

        # Validate the complete replacement set before the first runtime write.
        screener_status, home_summary_status = "SKIPPED", "BASELINE_PRESERVED"
        screener_identity: dict[str, Any] | None = None
        home_summary: dict[str, Any] | None = None
        if source_screener.is_file() and target_screener.is_file():
            new_screener = json.loads(source_screener.read_text(encoding="utf-8"))
            current_screener = json.loads(target_screener.read_text(encoding="utf-8"))
            screener_identity = _validate_presentation_screener(
                new_screener, session=session, runtime_screener=current_screener if isinstance(current_screener, dict) else {},
                declared_identity=presentation_result.get("screener_master_projection_artifact_identity"),
            )
            screener_status = "RESTAGED"
            if target_home_summary.is_file():
                current_home_summary = json.loads(target_home_summary.read_text(encoding="utf-8"))
                current_home_summary = current_home_summary if isinstance(current_home_summary, dict) else {}
                if (current_home_summary.get("source_artifact_identity") == screener_identity["artifact_identity"]
                        and current_home_summary.get("as_of_session") == session):
                    home_summary_status = "ALREADY_BOUND_TO_RESTAGED_SCREENER"
                else:
                    home_summary = _derive_restaged_home_summary(
                        new_screener, session=session,
                        fallback_requested_at=current_home_summary.get("requested_at"),
                    )
                    home_summary_status = "RESTAGED"
            else:
                home_summary_status = "ABSENT"

        touched = [target_workspace, manifest_path]
        if screener_status == "RESTAGED":
            touched.append(target_screener)
        if home_summary is not None:
            touched.append(target_home_summary)
        backups = {target: (target.read_bytes() if target.is_file() else None) for target in touched}
        try:
            atomic_copy_file(source_workspace, target_workspace)
            if screener_status == "RESTAGED":
                atomic_copy_file(source_screener, target_screener)
            if home_summary is not None:
                atomic_write_json(target_home_summary, home_summary)
            manifest_status = _patch_runtime_manifest_after_restage(
                manifest_path, session=session,
                workspace_identity=identity, workspace_sha256=_sha256(target_workspace),
                screener_identity=screener_identity,
                screener_sha256=_sha256(target_screener) if screener_status == "RESTAGED" else None,
                home_summary=home_summary,
                home_summary_sha256=_sha256(target_home_summary) if home_summary is not None else None,
            )
            if manifest_status != "PATCHED":
                raise _RestageRefused(f"RUNTIME_MANIFEST_{manifest_status}")
            _verify_runtime_manifest_coherence(runtime_root)
        except BaseException as exc:
            _restore_runtime_bytes(backups)
            reason = str(exc) if isinstance(exc, (_RestageRefused, CanonicalRuntimeReleaseError)) else f"{type(exc).__name__}:{exc}"
            return {"status": "SKIPPED", "reason": f"{reason}:RUNTIME_RESTORED"}
        return {
            "status": "RESTAGED", "session": session,
            "workspace_artifact_identity": identity["artifact_identity"],
            "screener_master_projection_status": screener_status,
            "screener_master_projection_artifact_identity": (screener_identity or {}).get("artifact_identity"),
            "dashboard_home_summary_status": home_summary_status,
            "dashboard_home_summary_artifact_identity": (home_summary or {}).get("artifact_identity"),
            "runtime_manifest_status": manifest_status,
        }
    except _RestageRefused as exc:
        return {"status": "SKIPPED", "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001 - this overlay must never block or fail core Daily
        return {"status": "SKIPPED", "reason": f"{type(exc).__name__}:{exc}"}


_COHERENCE_ARTIFACTS = (
    ("investment_decision_workspace", "data/investment_decision_workspace.json", "WORKSPACE"),
    ("screener_master_projection", "data/screener_master_projection.json", "SCREENER"),
    ("dashboard_home_summary", "data/dashboard_home_summary.json", "HOME_SUMMARY"),
)


def _verify_runtime_manifest_coherence(runtime_root: Path) -> None:
    """After a successful restage, fail loudly (never silently) if any served presentation
    artifact and the manifest's own declared identity for it have drifted apart, or if the served
    Home summary is bound to a Screener other than the one actually served -- the exact
    incoherences CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1 section 2 and
    DASHBOARD_PRESENTATION_RESTAGE_HOME_SUMMARY_COHERENCE_V1 exist to close. The Workspace is
    required; the Screener and Home summary are checked whenever the runtime serves them."""
    manifest = _load(Path(runtime_root) / "bundle_manifest.json")
    lineage = manifest.get("lineage") or {}
    served: dict[str, dict[str, Any]] = {}
    for key, relative, label in _COHERENCE_ARTIFACTS:
        path = Path(runtime_root) / relative
        if key != "investment_decision_workspace" and not path.is_file():
            continue
        payload = _load(path)
        declared = lineage.get(key) or {}
        if declared.get("artifact_identity") != payload.get("artifact_identity"):
            raise CanonicalRuntimeReleaseError(f"RUNTIME_MANIFEST_{label}_IDENTITY_INCOHERENT_AFTER_RESTAGE")
        if "sha256" in declared and declared["sha256"] != _sha256(path):
            raise CanonicalRuntimeReleaseError(f"RUNTIME_MANIFEST_{label}_SHA256_INCOHERENT_AFTER_RESTAGE")
        served[key] = payload
    home_summary, screener = served.get("dashboard_home_summary"), served.get("screener_master_projection")
    if home_summary is not None and screener is not None and (
            home_summary.get("source_artifact_identity") != screener.get("artifact_identity")):
        raise CanonicalRuntimeReleaseError("RUNTIME_HOME_SUMMARY_SOURCE_SCREENER_IDENTITY_INCOHERENT_AFTER_RESTAGE")


def materialize_release_ready_runtime(
    root: Path, runtime_root: Path, session: str, *,
    producer_run_identity: str | None = None,
    presentation_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The one governed boundary that produces a release-ready runtime: sealed Producer baseline
    materialization, then -- when an exact-session, identity-verified post-handoff presentation
    projection is available -- its additive overlay. Reused by BOTH normal owner publication and
    completed-session replay (``tools/run_owner_daily.publish_dashboard_release``), so neither
    route can leave the runtime on sealed (pre-handoff) bytes after a same-session overlay was
    already produced, and neither can leave `bundle_manifest.json` disagreeing with the bytes it
    describes. See CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1 section 2.

    ``presentation_source`` is the exact ``run_post_handoff_presentation_projection`` result to
    restage from; when omitted, the dedicated ``post_handoff_presentation_attestation`` artifact
    for ``(root, session)`` is consulted, if one was retained. Absence of either is not a
    failure: baseline materialization alone is a complete, valid (if presentation-unenriched)
    release -- exactly the pre-fix behavior for a session that never went through this milestone.
    """
    baseline = materialize_canonical_runtime_release(
        root, runtime_root, session, producer_run_identity=producer_run_identity,
    )
    source = presentation_source
    if source is None:
        from post_handoff_presentation_attestation import read_attestation
        attestation = read_attestation(root, session)
        if attestation is not None:
            source = attestation.get("presentation_projection")
    restage = (
        restage_runtime_with_presentation_projection(runtime_root, root, source)
        if isinstance(source, Mapping) else {"status": "SKIPPED", "reason": "NO_PRESENTATION_SOURCE_AVAILABLE"}
    )
    if restage.get("status") == "RESTAGED":
        _verify_runtime_manifest_coherence(runtime_root)
    baseline["presentation_restage"] = restage
    return baseline
