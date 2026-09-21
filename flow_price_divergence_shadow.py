"""Retained, non-causal foreign VALUE-flow / price-trajectory research shadow.

This module deliberately joins two already-governed contracts.  It neither fetches
flow data nor recreates technical evidence.  A relationship is current only when
the store's qualified VALUE observation and the V1.2 velocity record share the
same retained reference session.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from daily_session_completion_reference import registry_path as _session_registry_path
from dnse_foreign_flow_store import build_series, observations_root

CONTRACT_VERSION = "flow_price_divergence_shadow/v1"
VELOCITY_CONTRACT_VERSION = "multi_session_signal_velocity/v1.2"
RESEARCH_TIER = "RETAINED_VALUE_FLOW_PRICE_RELATIONSHIP_RESEARCH_ONLY"

def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

def _identity(payload: dict[str, Any], *, prefix: str, field: str) -> dict[str, Any]:
    body = {key: value for key, value in payload.items() if key not in {field, "artifact_sha256"}}
    digest = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    payload[field] = prefix + digest
    if field == "artifact_identity":
        payload["artifact_sha256"] = digest
    return payload

def _series_identity(series: Mapping[str, Any]) -> str:
    return "dnse_foreign_flow_series:" + hashlib.sha256(_canonical(series).encode("utf-8")).hexdigest()

def _flow(series: Mapping[str, Any]) -> dict[str, Any]:
    """Project existing store summaries; never read volume, room, or a denominator."""
    freshness = dict(series.get("freshness") or {})
    latest = dict(series.get("latest_session") or {})
    net = latest.get("foreign_net_value_vnd")
    windows = series.get("window_summaries") or {}
    five, ten = dict(windows.get("5_session") or {}), dict(windows.get("10_session") or {})
    base = {
        "latest_qualified_flow_session": freshness.get("latest_qualified_session_date"),
        "freshness": freshness,
        "window_sessions": {"5_session": five.get("sessions", []), "10_session": ten.get("sessions", [])},
        "window_completeness": {"5_session": five.get("coverage"), "10_session": ten.get("coverage")},
        "latest_qualified_net_value_vnd": net,
        "source_identity": _series_identity(series), "reason_codes": [],
    }
    if series.get("status") != "available":
        return {**base, "state": "FLOW_UNAVAILABLE", "persistence": "INSUFFICIENT_HISTORY", "reason_codes": ["NO_QUALIFIED_VALUE_FLOW_RETAINED"]}
    status = freshness.get("status")
    if status == "stale":
        return {**base, "state": "FLOW_STALE", "persistence": "INSUFFICIENT_HISTORY", "reason_codes": ["FLOW_NOT_CURRENT_FOR_REFERENCE_SESSION"]}
    if status != "current":
        return {**base, "state": "SEMANTICALLY_BLOCKED", "persistence": "INSUFFICIENT_HISTORY", "reason_codes": ["FLOW_FRESHNESS_NOT_EXACT_SESSION_CURRENT"]}
    if net is None:
        return {**base, "state": "FLOW_INCOMPLETE", "persistence": "INSUFFICIENT_HISTORY", "reason_codes": ["CURRENT_FLOW_NET_VALUE_NOT_QUALIFIED"]}
    state = "NET_FOREIGN_BUY" if net > 0 else "NET_FOREIGN_SELL" if net < 0 else "NEUTRAL_FOREIGN_FLOW"
    # A complete window is necessary but not sufficient for persistence: a sustained
    # label needs a same-direction streak, avoiding one extreme day dominating it.
    if state == "NET_FOREIGN_BUY" and five.get("coverage") == "complete" and series.get("current_consecutive_net_buy_sessions", 0) >= 5:
        persistence = "PERSISTENT_NET_BUY"
    elif state == "NET_FOREIGN_SELL" and five.get("coverage") == "complete" and series.get("current_consecutive_net_sell_sessions", 0) >= 5:
        persistence = "PERSISTENT_NET_SELL"
    elif state == "NET_FOREIGN_BUY" and five.get("coverage") == "complete" and (five.get("cumulative_net_value_vnd") or 0) < 0:
        persistence = "RECENT_BUY_REVERSAL"
    elif state == "NET_FOREIGN_SELL" and five.get("coverage") == "complete" and (five.get("cumulative_net_value_vnd") or 0) > 0:
        persistence = "RECENT_SELL_REVERSAL"
    elif state == "NEUTRAL_FOREIGN_FLOW":
        persistence = "NO_CLEAR_FLOW_DIRECTION"
    elif five.get("coverage") != "complete":
        persistence = "INSUFFICIENT_HISTORY"
    else:
        persistence = "MIXED_FLOW"
    return {**base, "state": state, "persistence": persistence}

def _price(record: Mapping[str, Any] | None, reference_session: str) -> dict[str, Any]:
    if not record:
        return {"state": "PRICE_EVIDENCE_INSUFFICIENT", "velocity_state": None, "participation_context": "PARTICIPATION_UNAVAILABLE", "market_support": None, "sector_support": None, "source_identity": None, "reason_codes": ["NO_V1_2_RECORD_FOR_SESSION"]}
    if record.get("session") != reference_session:
        return {"state": "PRICE_EVIDENCE_INSUFFICIENT", "velocity_state": record.get("overall_transition_state"), "participation_context": "PARTICIPATION_UNAVAILABLE", "market_support": None, "sector_support": None, "source_identity": record.get("source_snapshot_identity"), "reason_codes": ["VELOCITY_SESSION_MISMATCH"]}
    axes = record.get("axes") or {}
    structural, setup = (axes.get("structural_repair") or {}).get("state"), (axes.get("setup_maturation") or {}).get("state")
    participation, overall = (axes.get("participation_confirmation") or {}).get("state"), record.get("overall_transition_state")
    participation_context = "PARTICIPATION_CORROBORATES" if participation == "IMPROVING" else "PARTICIPATION_CONTRADICTS" if participation in {"DETERIORATING", "DIVERGENT"} else "PARTICIPATION_UNAVAILABLE" if participation in {None, "UNAVAILABLE"} else "PARTICIPATION_NEUTRAL"
    base = {"velocity_state": overall, "participation_context": participation_context, "market_support": (axes.get("market_support") or {}).get("state"), "sector_support": (axes.get("sector_support") or {}).get("state"), "source_identity": record.get("source_snapshot_identity"), "technical_source_identity": (axes.get("structural_repair") or {}).get("source_identity"), "reason_codes": []}
    if (record.get("evidence_quality") or {}).get("state") == "INSUFFICIENT_RETAINED_EVIDENCE":
        return {**base, "state": "PRICE_EVIDENCE_INSUFFICIENT", "reason_codes": ["VELOCITY_EVIDENCE_INSUFFICIENT"]}
    if structural == "ADVERSE" or setup == "INVALID": return {**base, "state": "PRICE_INVALID_OR_BREAKDOWN", "reason_codes": ["TECHNICAL_VETO"]}
    if overall == "DETERIORATING": return {**base, "state": "PRICE_DETERIORATING"}
    if overall == "PERSISTENT_IMPROVEMENT": return {**base, "state": "PRICE_PERSISTENTLY_IMPROVING"}
    if overall == "EARLY_IMPROVEMENT": return {**base, "state": "PRICE_IMPROVING"}
    if overall == "STABLE": return {**base, "state": "PRICE_RESILIENT_OR_STABLE"}
    if overall == "MIXED_TRANSITION": return {**base, "state": "PRICE_MIXED"}
    return {**base, "state": "PRICE_EVIDENCE_INSUFFICIENT", "reason_codes": ["VELOCITY_STATE_NOT_EVALUABLE"]}

def _alignment(flow: Mapping[str, Any], price: Mapping[str, Any], reference_session: str) -> str:
    latest = flow.get("latest_qualified_flow_session")
    if not latest or price.get("state") == "PRICE_EVIDENCE_INSUFFICIENT": return "UNAVAILABLE"
    if latest > reference_session: return "SESSION_MISMATCH"
    if flow.get("freshness", {}).get("status") != "current": return "STALE_NOT_COMPARABLE"
    if latest == reference_session: return "EXACT_SESSION_ALIGNED"
    return "FLOW_LAGGED_REFERENCE_ONLY"

def _relationship(flow: Mapping[str, Any], price: Mapping[str, Any], alignment: str) -> str:
    if price["state"] == "PRICE_EVIDENCE_INSUFFICIENT": return "PRICE_EVIDENCE_INSUFFICIENT"
    if flow["state"] in {"FLOW_UNAVAILABLE", "FLOW_STALE", "FLOW_INCOMPLETE", "SEMANTICALLY_BLOCKED"}: return "FLOW_UNAVAILABLE"
    if alignment != "EXACT_SESSION_ALIGNED": return "RELATIONSHIP_NOT_EVALUABLE"
    constructive = price["state"] in {"PRICE_PERSISTENTLY_IMPROVING", "PRICE_IMPROVING"}
    weak = price["state"] in {"PRICE_DETERIORATING", "PRICE_INVALID_OR_BREAKDOWN"}
    if flow["state"] == "NET_FOREIGN_SELL":
        if constructive: return "PERSISTENT_FOREIGN_SELLING_PRICE_RESILIENCE" if flow["persistence"] == "PERSISTENT_NET_SELL" else "FOREIGN_SELLING_PRICE_RESILIENCE"
        if weak: return "FOREIGN_SELLING_PRICE_WEAKNESS"
    elif flow["state"] == "NET_FOREIGN_BUY":
        if constructive: return "FOREIGN_BUYING_PRICE_CONFIRMATION"
        if weak: return "FOREIGN_BUYING_PRICE_WEAKNESS"
    elif flow["state"] == "NEUTRAL_FOREIGN_FLOW":
        if constructive: return "FLOW_NEUTRAL_PRICE_IMPROVING"
        if weak: return "FLOW_NEUTRAL_PRICE_DETERIORATING"
    return "FLOW_PRICE_MIXED"

def _quality(flow: Mapping[str, Any], price: Mapping[str, Any], alignment: str) -> str:
    if flow["state"] == "FLOW_STALE": return "LIMITED_STALE_FLOW_CONTEXT"
    if alignment != "EXACT_SESSION_ALIGNED" or price["state"] == "PRICE_EVIDENCE_INSUFFICIENT" or flow["state"] not in {"NET_FOREIGN_BUY", "NET_FOREIGN_SELL", "NEUTRAL_FOREIGN_FLOW"}: return "INSUFFICIENT_RETAINED_EVIDENCE"
    if flow["window_completeness"].get("5_session") != "complete" or price.get("participation_context") == "PARTICIPATION_UNAVAILABLE": return "PARTIAL_RETAINED_EVIDENCE"
    return "COMPLETE_RETAINED_EVIDENCE"

def _record(*, ticker: str, reference_session: str, series: Mapping[str, Any], velocity_record: Mapping[str, Any] | None) -> dict[str, Any]:
    flow, price = _flow(series), _price(velocity_record, reference_session)
    alignment = _alignment(flow, price, reference_session)
    value = {"ticker": ticker, "reference_session": reference_session, "flow": flow, "price": price, "price_velocity_session": velocity_record.get("session") if velocity_record else None, "session_alignment": {"state": alignment, "reference_session": reference_session, "latest_qualified_flow_session": flow["latest_qualified_flow_session"], "sessions_behind": flow["freshness"].get("sessions_behind"), "flow_window_sessions": flow["window_sessions"]}, "relationship": _relationship(flow, price, alignment), "evidence_quality": _quality(flow, price, alignment), "source_artifact_identities": {"foreign_flow_series": flow["source_identity"], "signal_velocity_snapshot": price["source_identity"]}, "limitations": ["QUALIFIED_FOREIGN_VALUE_ONLY", "NO_FLOW_NORMALIZATION", "NO_CAUSAL_OR_INTENT_INTERPRETATION", "NO_FORWARD_OUTCOME_CLAIM"], "authority_boundary": "DESCRIPTIVE_NON_CAUSAL_VALUE_FLOW_PRICE_RESEARCH_ONLY", "is_actionable": False}
    return _identity(value, prefix="flow_price_divergence_record:", field="record_identity")

def _validation(records: Sequence[Mapping[str, Any]], reference_session: str) -> dict[str, Any]:
    eligible = [r for r in records if r["session_alignment"]["state"] == "EXACT_SESSION_ALIGNED" and r["price"]["velocity_state"]]
    flow_states = Counter(r["flow"]["state"] for r in records)
    return {"reference_session": reference_session, "record_count": len(records), "current_exact_session_aligned_count": len(eligible), "stale_count": flow_states["FLOW_STALE"], "missing_count": flow_states["FLOW_UNAVAILABLE"], "five_session_complete_count": sum(r["flow"]["window_completeness"].get("5_session") == "complete" for r in records), "ten_session_complete_count": sum(r["flow"]["window_completeness"].get("10_session") == "complete" for r in records), "signal_velocity_coverage": sum(r["price"]["velocity_state"] is not None for r in records), "relationship_evaluable_count": sum(r["relationship"] not in {"FLOW_UNAVAILABLE", "PRICE_EVIDENCE_INSUFFICIENT", "RELATIONSHIP_NOT_EVALUABLE"} for r in records), "relationship_counts": dict(sorted(Counter(r["relationship"] for r in records).items())), "flow_velocity_crosstab": {"eligible_denominator": len(eligible), "counts": dict(sorted(Counter(f"{r['flow']['state']} × {r['price']['velocity_state']}" for r in eligible).items()))}}

def build_artifact(*, reference_session: str, flow_series: Mapping[str, Mapping[str, Any]], velocity_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic session-bound artifact from explicit retained inputs."""
    if velocity_artifact.get("contract_version") != VELOCITY_CONTRACT_VERSION: raise ValueError("REQUIRE_SIGNAL_VELOCITY_V1_2")
    velocity = {str(r.get("ticker")): r for r in velocity_artifact.get("records", []) if isinstance(r, Mapping) and r.get("session") == reference_session}
    records = [_record(ticker=ticker, reference_session=reference_session, series=flow_series.get(ticker, {}), velocity_record=velocity.get(ticker)) for ticker in sorted(set(flow_series) | set(velocity))]
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "research_tier": RESEARCH_TIER, "reference_session": reference_session, "source_artifact_identities": {"signal_velocity": velocity_artifact.get("artifact_identity")}, "records": records, "validation": _validation(records, reference_session), "authority_boundary": {"qualified_foreign_value_only": True, "no_volume_or_room": True, "no_normalized_flow_ratio": True, "no_causality_or_intent": True, "no_score_probability_recommendation_or_execution": True, "is_actionable": False}, "limitations": ["FLOW_STATE_IS_DESCRIPTIVE_NOT_DIRECTIONAL_AUTHORITY", "NO_HISTORICAL_PRICE_RECONSTRUCTION", "NO_FORWARD_OUTCOME_CONTRACT"]}
    return _identity(artifact, prefix="flow_price_divergence_shadow:", field="artifact_identity")

def write_immutable(path: str | Path, artifact: Mapping[str, Any]) -> Path:
    destination = Path(path); text = json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if destination.exists() and destination.read_text(encoding="utf-8") != text: raise ValueError("IMMUTABLE_ARTIFACT_CONFLICT:" + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True); destination.write_text(text, encoding="utf-8")
    return destination

def collect_from_retained_runtime(*, root: str | Path, runtime_root: str | Path, reference_session: str, velocity_artifact: Mapping[str, Any], series_builder: Callable[..., dict[str, Any]] = build_series) -> dict[str, Any]:
    """Read only the requested retained series; no provider/network operation exists here.

    `root` is the SOURCE checkout (distinct from `runtime_root`, the evidence root) --
    used only to resolve the one deterministic, explicit path to Daily's own
    config/daily_research_session_input_registry.json (see
    daily_session_completion_reference.py), never re-derived from CWD. Passing it to
    every `series_builder` call lets a ticker's window/streak continuity be proven by
    that non-exhaustive registry fallback whenever vn_stock.db has no OHLCV rows for
    it -- vn_stock.db-backed continuity (when available) is unaffected and unchanged.
    """
    runtime = Path(runtime_root)
    registry = _session_registry_path(root)
    velocity_tickers = {str(r.get("ticker")) for r in velocity_artifact.get("records", []) if isinstance(r, Mapping) and r.get("session") == reference_session}
    stored_tickers = {path.stem.upper() for path in observations_root(runtime).glob("*.json")} if observations_root(runtime).is_dir() else set()
    # Use the store contract for every declared Velocity ticker, including an
    # explicit missing result.  This keeps the per-ticker retained-series
    # identity and its own freshness/window semantics authoritative.
    series = {ticker: series_builder(runtime, ticker, reference_session_date=reference_session,
                                      qualified_session_registry_path=registry)
              for ticker in sorted(velocity_tickers | stored_tickers)}
    return build_artifact(reference_session=reference_session, flow_series=series, velocity_artifact=velocity_artifact)

def representative_cases(artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One deterministic compact trace per available class, never a ranking."""
    wanted = ("FOREIGN_SELLING_PRICE_RESILIENCE", "PERSISTENT_FOREIGN_SELLING_PRICE_RESILIENCE", "FOREIGN_SELLING_PRICE_WEAKNESS", "FOREIGN_BUYING_PRICE_CONFIRMATION", "FOREIGN_BUYING_PRICE_WEAKNESS", "FLOW_UNAVAILABLE", "FLOW_PRICE_MIXED")
    selected: list[dict[str, Any]] = []
    for relationship in wanted:
        row = next((r for r in artifact.get("records", []) if r.get("relationship") == relationship), None)
        if row: selected.append({key: row[key] for key in ("ticker", "flow", "price", "session_alignment", "relationship", "evidence_quality", "limitations")})
    return selected
