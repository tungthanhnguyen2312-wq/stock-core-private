"""No-network foundation for bounded current DNSE VALUE-flow retention."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import canonical_current_product_projections as projections
import current_official_market_universe as official
import current_research_official_universe_scope as scope
from dnse_foreign_flow_capability import assert_point_in_time_consistency, normalize_record
from dnse_foreign_flow_store import build_series, read_observations, write_observations
from dnse_foreign_trading_raw import canonical_json
from owner_research_focus import load_owner_research_focus

CONTRACT_VERSION = "current_foreign_flow_acquisition_manifest/v1"


def _identity(value: dict[str, Any]) -> dict[str, Any]:
    body = {key: item for key, item in value.items() if key not in {"artifact_identity", "artifact_sha256"}}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    value.update(artifact_sha256=digest, artifact_identity="current_foreign_flow_acquisition_manifest:" + digest)
    return value


def _focus_identity(focus: Mapping[str, Any]) -> str:
    return "owner_research_focus:" + hashlib.sha256(json.dumps(dict(focus), sort_keys=True, default=list, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def build_manifest(*, reference_session: str, owner_focus: Mapping[str, Any], official_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze a configured, pre-flow cohort; no price, Velocity, or ranking input."""
    official.verify_retained_artifact(official_artifact, label="FOREIGN_FLOW_OFFICIAL_UNIVERSE")
    resolved = scope.resolve_scope(official_artifact=official_artifact, research_session=reference_session)
    if not resolved.get("temporally_eligible"):
        raise ValueError("OFFICIAL_UNIVERSE_TEMPORALLY_INELIGIBLE")
    requested = tuple(owner_focus.get("broader_watchlist") or ())
    if not requested:
        raise ValueError("BROADER_WATCHLIST_REQUIRED")
    eligible_set = scope.eligible_ticker_set(resolved)
    rows = []
    for ticker in requested:
        ticker = str(ticker).upper()
        in_scope = ticker in eligible_set
        detail = (resolved.get("records") or {}).get(ticker) or {}
        rows.append({"ticker": ticker, "eligibility": "ELIGIBLE_PENDING_ACQUISITION" if in_scope else "EXCLUDED_OFFICIAL_RESEARCH_SCOPE", "reason": "IN_CURRENT_OFFICIAL_RESEARCH_SCOPE" if in_scope else detail.get("current_research_scope_state") or "NOT_GOVERNED_REFERENCE_MEMBER", "initial_acquisition_state": "PENDING" if in_scope else "NOT_REQUESTED"})
    manifest = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "reference_session": reference_session,
                "owner_focus": {"contract_version": owner_focus.get("schema_version"), "identity": _focus_identity(owner_focus), "requested_watchlist": list(requested)},
                "official_universe_artifact_identity": official_artifact.get("artifact_identity"),
                "official_scope_observed_at": resolved.get("official_snapshot_observed_at"), "records": rows,
                "eligible_tickers": [row["ticker"] for row in rows if row["eligibility"] == "ELIGIBLE_PENDING_ACQUISITION"],
                "excluded_tickers": [row["ticker"] for row in rows if row["eligibility"] != "ELIGIBLE_PENDING_ACQUISITION"],
                "cohort_count": sum(row["eligibility"] == "ELIGIBLE_PENDING_ACQUISITION" for row in rows),
                "authority_boundary": {"pre_flow_configured_scope_only": True, "no_velocity_price_or_ranking_input": True, "value_only_future_use": True, "is_actionable": False}}
    return _identity(manifest)


def build_manifest_from_root(root: str | Path, reference_session: str) -> dict[str, Any]:
    root = Path(root)
    artifact_path = root / projections.CURRENT_OFFICIAL_UNIVERSE_EVIDENCE_RELATIVE
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    official.verify_retained_artifact(artifact, label="FOREIGN_FLOW_OFFICIAL_UNIVERSE", expected_identity=projections.CURRENT_OFFICIAL_UNIVERSE_EVIDENCE_EXPECTED_IDENTITY)
    return build_manifest(reference_session=reference_session, owner_focus=load_owner_research_focus(), official_artifact=artifact)


def dry_run_plan(*, root: str | Path, runtime_root: str | Path, reference_session: str) -> dict[str, Any]:
    manifest = build_manifest_from_root(root, reference_session)
    current, pending = [], []
    for ticker in manifest["eligible_tickers"]:
        series = build_series(runtime_root, ticker, reference_session_date=reference_session)
        (current if (series.get("freshness") or {}).get("status") == "current" else pending).append(ticker)
    return {"dry_run": True, "network_calls": 0, "reference_session": reference_session,
            "manifest_identity": manifest["artifact_identity"], "cohort_count": manifest["cohort_count"],
            "already_retained_exact_session": current, "needs_acquisition": pending,
            "excluded_tickers": manifest["excluded_tickers"]}


def normalize_exact_raw_page(*, ticker: str, reference_session: str, page: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one retained root page then reuse the established VALUE normalizer."""
    ticker = ticker.upper(); payload = page.get("raw_payload") or page.get("body")
    if page.get("instrument") not in {None, ticker} or page.get("source_event_time") not in {None, reference_session}:
        raise ValueError("RAW_PAGE_TICKER_OR_REQUESTED_SESSION_MISMATCH")
    provenance = page.get("provenance") or {}; endpoint = provenance.get("endpoint") or page.get("endpoint")
    if endpoint != f"/price/{ticker}/foreign-trading": raise ValueError("RAW_PAGE_ENDPOINT_MISMATCH")
    if not isinstance(payload, Mapping) or not isinstance(payload.get("foreigners"), list) or not payload["foreigners"]:
        raise ValueError("RAW_PAGE_MALFORMED_OR_EMPTY")
    if payload.get("nextPageToken"):
        raise ValueError("RAW_PAGE_PAGINATION_NOT_COMPLETE")
    digest = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
    supplied = page.get("raw_sha256") or page.get("raw_payload_hash")
    if supplied is not None and supplied != digest: raise ValueError("RAW_PAGE_HASH_MISMATCH")
    records = payload["foreigners"]
    if any(not isinstance(row, Mapping) or str(row.get("symbol", "")).upper() != ticker for row in records):
        raise ValueError("RAW_PAGE_PROVIDER_TICKER_MISMATCH")
    assert_point_in_time_consistency(requested_session_date=reference_session, observations=[{"session_date": row.get("time", "").split(" ", 1)[0]} for row in records])
    query = provenance.get("request_parameters") or page.get("query_sent")
    observation = normalize_record(records[0], source_endpoint=endpoint, query_window=query)
    assert_point_in_time_consistency(requested_session_date=reference_session, observations=[observation])
    return observation


def write_exact_value_observation(runtime_root: str | Path, ticker: str, observation: Mapping[str, Any]) -> None:
    """Guard the store's historical last-write behavior against conflicting raw bytes."""
    provenance = observation.get("provenance") or {}
    value_only = {key: observation.get(key) for key in ("ticker", "session_date", "observed_at", "foreign_buy_value", "foreign_sell_value", "foreign_net_value", "source", "source_contract_version", "value_unit", "qualification_status", "warnings")}
    value_only["provenance"] = {key: provenance.get(key) for key in ("source_endpoint", "board_id", "exchange", "trading_session_id", "query_window")}
    existing = read_observations(runtime_root, ticker)
    same = [row for row in existing if row.get("session_date") == observation.get("session_date")]
    if same and json.dumps(same[0], sort_keys=True) != json.dumps(value_only, sort_keys=True):
        raise ValueError("CONFLICTING_RETAINED_EXACT_SESSION_VALUE_OBSERVATION")
    write_observations(runtime_root, ticker, [row for row in existing if row.get("session_date") != observation.get("session_date")] + [value_only])
