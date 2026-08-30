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

CONTRACT_VERSION = "canonical_dashboard_runtime_release/v1"
REQUIRED_INPUTS = ("descriptive", "screening", "tactical", "triage", "official_universe")
RELEASE_FILES = ("screen_snapshot.csv", "screen_snapshot_live.csv", "market_breadth.csv",
                 "analysis_latest.json", "bundle_manifest.json")
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
    expected_run = run_manifest.get("run_identity")
    observed_run = (handoff.get("daily_producer") or {}).get("run_identity")
    if expected_run != observed_run:
        raise CanonicalRuntimeReleaseError("TIER_HANDOFF_DAILY_PRODUCER_LINEAGE_MISMATCH")
    return {"sha256": _sha256(path), "path": str(path.relative_to(root)),
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


def _build_release(root: Path, session: str, staging: Path, *, producer_run_identity: str | None = None) -> dict[str, Any]:
    sources, _registry = _source_paths(root, session)
    run_path, run_manifest, bundle_path, producer_bundle = _producer_run(root, session, sources, run_identity=producer_run_identity)
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
    manifest = {"schema_version": CONTRACT_VERSION, "freshness": {"reference_session": session, "status": "fresh", "blocked": False},
        "release_contract": {"source": "retained_canonical_daily_producer", "session": session,
            "unavailable_legacy_fields": ["historical_indicator_suite", "strict_valuation", "liquidity_sizing_execution", "macro_optional", "explicit_portfolio"]},
        "lineage": lineage, "release_files": list(RELEASE_FILES)}
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
                shutil.copy2(target, backup / name)
        try:
            for name in (*RELEASE_FILES[:-1], RELEASE_FILES[-1]):
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
