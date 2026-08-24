"""Current, provider-scoped market-flow and positioning research projection.

This is deliberately a *projection* of retained canonical observations, not a
new data lake or an authority promotion.  It keeps providers separate, fails
closed on an unavailable/conflicting field, and describes relationships only.
"""
from __future__ import annotations

import copy
from collections import Counter, defaultdict
from typing import Any, Mapping

from field_temporal_contract import stable_id

CONTRACT_VERSION = "current_market_flow_positioning/v1"
FLOW_USE = "flow_research"
DISPLAY_USE = "descriptive_research_display"
DISPOSITIONS = ("AVAILABLE", "MISSING", "PROVIDER_REJECTED", "RATE_LIMITED", "SESSION_MISMATCH", "SESSION_UNRESOLVED", "SEMANTIC_BLOCKED", "NOT_APPLICABLE")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact)); payload.pop("artifact_identity", None); payload.pop("artifact_sha256", None)
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": "current_market_flow_positioning:" + digest}


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _status(observations: list[Mapping[str, Any]]) -> str:
    statuses = {str(item.get("observation_status", "")) for item in observations}
    if any("RATE" in value or "BUDGET" in value for value in statuses): return "RATE_LIMITED"
    if any("REJECT" in value for value in statuses): return "PROVIDER_REJECTED"
    if any("SEMANTIC" in value or "CONFLICT" in value for value in statuses): return "SEMANTIC_BLOCKED"
    return "MISSING"


def _usable(observation: Mapping[str, Any], session: str) -> bool:
    provider_session = (observation.get("provenance") or {}).get("provider_session_date")
    return (observation.get("session") == session and provider_session == session and observation.get("observation_status") == "ACQUIRED"
            and observation.get("conflict_state", "CLEAN") in {"CLEAN", "NONE"}
            and bool((observation.get("downstream_eligibility") or {}).get(FLOW_USE)
                     or (observation.get("downstream_eligibility") or {}).get(DISPLAY_USE)))


def _entry(observation: Mapping[str, Any]) -> dict[str, Any]:
    return {"value": observation.get("canonical_value"), "unit": observation.get("canonical_unit"),
            "provider_native_value": observation.get("provider_native_value"), "provider_native_unit": observation.get("provider_native_unit"),
            "source": observation.get("source"), "endpoint_id": observation.get("endpoint_id"), "session": observation.get("session"), "provider_session_date": (observation.get("provenance") or {}).get("provider_session_date"),
            "retrieved_at": observation.get("retrieved_at"), "raw_sha256": observation.get("raw_sha256"),
            "observation_identity": "canonical_market_observation:" + stable_id({k: observation.get(k) for k in ("instrument", "session", "source", "endpoint_id", "semantic_identity", "raw_sha256")})}


def _source_values(observations: list[Mapping[str, Any]], names: tuple[str, ...], session: str) -> tuple[str | None, dict[str, dict[str, Any]], str]:
    by_source: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    all_matching = [item for item in observations if item.get("semantic_identity") in names]
    for item in all_matching:
        if _usable(item, session): by_source[str(item.get("source"))][str(item["semantic_identity"])] = _entry(item)
    candidates = [source for source, values in by_source.items() if all(name in values and _number(values[name]["value"]) for name in names)]
    # DNSE keeps its already-qualified foreign-value role; otherwise source ordering is deterministic.
    source = "DNSE" if "DNSE" in candidates and any(name.startswith("FOREIGN_") for name in names) else sorted(candidates)[0] if candidates else None
    return source, (by_source.get(source, {}) if source else {}), "AVAILABLE" if source else _status(all_matching)


def _traded(observations: list[Mapping[str, Any]], session: str) -> dict[str, Any]:
    names = ("MATCHED_TRADED_VALUE_VND", "PUT_THROUGH_TRADED_VALUE_VND", "TOTAL_TRADED_VALUE_VND")
    source, values, status = _source_values(observations, names, session)
    if not source: return {"status": status, "fields": {}, "state": "UNAVAILABLE", "limitations": ["No same-session eligible traded-value decomposition."]}
    matched, put_through, total = (values[name]["value"] for name in names)
    if matched + put_through != total: return {"status": "SEMANTIC_BLOCKED", "fields": values, "state": "UNAVAILABLE", "limitations": ["MATCHED_PLUS_PUT_THROUGH_TOTAL_INVARIANT_FAILED"]}
    share = put_through / total if total > 0 else None
    state = "NO_RECORDED_PUT_THROUGH" if put_through == 0 else "MATCHED_DOMINANT" if share < .20 else "MIXED_COMPOSITION" if share < .50 else "PUT_THROUGH_MATERIAL" if share < .75 else "PUT_THROUGH_DOMINANT"
    return {"status": "AVAILABLE", "source": source, "fields": values, "matched_share_of_total": matched / total if total > 0 else None, "put_through_share_of_total": share, "state": state, "threshold_version": "v1:0,.20,.50,.75", "limitations": ["Composition is not liquidity, executable depth, or capacity evidence."]}


def _flow(observations: list[Mapping[str, Any]], session: str, prefix: str, name: str) -> dict[str, Any]:
    names = (f"{prefix}_BUY_VALUE", f"{prefix}_SELL_VALUE", f"{prefix}_NET_VALUE")
    source, values, status = _source_values(observations, names, session)
    if not source: return {"status": status, "fields": {}, "state": f"{name}_UNAVAILABLE", "limitations": ["Missing is not semantic zero."]}
    net = values[names[-1]]["value"]
    state = f"NET_{name}_BUY" if net > 0 else f"NET_{name}_SELL" if net < 0 else "NEUTRAL_FLOW" if name == "FOREIGN" else "NO_RECORDED_PROP_ACTIVITY"
    # Volumes remain independent; never derive them from values.
    volume_names = (f"{prefix}_BUY_VOLUME", f"{prefix}_SELL_VOLUME", f"{prefix}_NET_VOLUME")
    _, volume_fields, _ = _source_values(observations, volume_names, session)
    return {"status": "AVAILABLE", "source": source, "fields": values | volume_fields, "state": state, "limitations": ["Recorded provider flow is descriptive and non-causal."]}


def _room(observations: list[Mapping[str, Any]], session: str) -> dict[str, Any]:
    names = ("FOREIGN_ROOM_MAX", "FOREIGN_ROOM_OWNED", "FOREIGN_ROOM_AVAILABLE")
    source, values, status = _source_values(observations, names, session)
    if not source: return {"status": status, "fields": {}, "state": "UNKNOWN", "limitations": ["Foreign-room fields unavailable or not eligible."]}
    maximum, owned, available = (values[name]["value"] for name in names)
    if owned + available != maximum: return {"status": "SEMANTIC_BLOCKED", "fields": values, "state": "UNKNOWN", "limitations": ["FOREIGN_ROOM_ARITHMETIC_INVARIANT_FAILED"]}
    utilization = owned / maximum if maximum > 0 else None
    state = "UNKNOWN" if utilization is None else "LOW_UTILIZATION" if utilization < .50 else "MODERATE_UTILIZATION" if utilization < .80 else "HIGH_UTILIZATION" if utilization < .95 else "NEAR_LIMIT"
    return {"status": "AVAILABLE", "source": source, "fields": values, "utilization": utilization, "state": state, "threshold_version": "v1:.50,.80,.95", "limitations": ["Room utilization is not a buy/sell signal."]}


def _active(observations: list[Mapping[str, Any]], session: str) -> dict[str, Any]:
    names = ("ACTIVE_BUY_VOLUME", "ACTIVE_SELL_VOLUME")
    source, values, status = _source_values(observations, names, session)
    count_source, counts, _ = _source_values(observations, ("ACTIVE_BUY_ORDER_COUNT", "ACTIVE_SELL_ORDER_COUNT"), session)
    if not source: return {"status": status, "fields": counts, "state": "UNAVAILABLE", "limitations": ["Active order fields are provider-defined context, not hidden-liquidity evidence."]}
    buy, sell = (values[name]["value"] for name in names); ratio = (buy - sell) / (buy + sell) if buy + sell > 0 else None
    state = "BALANCED_ACTIVE_FLOW" if ratio is None or abs(ratio) < .10 else "ACTIVE_BUY_SKEW" if ratio > 0 else "ACTIVE_SELL_SKEW"
    return {"status": "AVAILABLE", "source": source, "fields": values | counts, "active_net_volume": buy - sell, "active_net_ratio": ratio, "state": state, "threshold_version": "v1:abs(net_ratio)<.10", "limitations": ["Active-order context is not order-flow causality or execution evidence."]}


def _relationships(tactical: Mapping[str, Any], active: Mapping[str, Any], prop: Mapping[str, Any]) -> list[str]:
    state = tactical.get("entry_state") or ""; relationships: list[str] = []
    active_state, prop_state = active.get("state"), prop.get("state")
    if state in {"BREAKOUT_READY", "UPTREND_CONFIRMED"} and active_state == "ACTIVE_BUY_SKEW": relationships.append("BREAKOUT_WITH_FLOW_CONFIRMATION" if state == "BREAKOUT_READY" else "PRICE_UP_WITH_ACTIVE_BUY_SKEW")
    if state in {"BREAKOUT_READY", "UPTREND_CONFIRMED"} and active_state == "ACTIVE_SELL_SKEW": relationships.append("BREAKOUT_WITH_FLOW_DIVERGENCE" if state == "BREAKOUT_READY" else "PRICE_UP_WITH_ACTIVE_SELL_SKEW")
    if state == "EARLY_REVERSAL_CANDIDATE" and active_state == "ACTIVE_BUY_SKEW": relationships.append("EARLY_REVERSAL_WITH_ACTIVE_BUY_SUPPORT")
    if state == "EARLY_REVERSAL_CANDIDATE" and active_state == "ACTIVE_SELL_SKEW": relationships.append("EARLY_REVERSAL_WITH_ACTIVE_SELL_PRESSURE")
    if state in {"BREAKOUT_READY", "UPTREND_CONFIRMED"} and prop_state == "NET_PROP_BUY": relationships.append("MOMENTUM_WITH_PROP_NET_BUY")
    if state in {"BREAKOUT_READY", "UPTREND_CONFIRMED"} and prop_state == "NET_PROP_SELL": relationships.append("MOMENTUM_WITH_PROP_NET_SELL")
    return relationships


def build(*, canonical_integration: Mapping[str, Any], tactical: Mapping[str, Any] | None = None, sector_by_ticker: Mapping[str, str] | None = None, candidate_tickers: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    session = str(canonical_integration.get("session_date") or canonical_integration.get("session") or "")
    if not session: raise ValueError("FLOW_POSITIONING_SESSION_REQUIRED")
    by_ticker: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for observation in canonical_integration.get("observations", []):
        if isinstance(observation, Mapping) and observation.get("instrument"): by_ticker[str(observation["instrument"]).upper()].append(observation)
    tactical_records = (tactical or {}).get("records", {})
    records: dict[str, Any] = {}
    tickers = sorted(set(by_ticker) | {str(ticker).upper() for ticker in (candidate_tickers or []) if str(ticker).strip()})
    for ticker in tickers:
        observations = by_ticker[ticker]; traded = _traded(observations, session); foreign = _flow(observations, session, "FOREIGN", "FOREIGN"); room = _room(observations, session); prop = _flow(observations, session, "PROPRIETARY", "PROP"); active = _active(observations, session)
        relationships = _relationships(tactical_records.get(ticker) or {}, active, prop)
        sections = (traded, foreign, room, prop, active)
        record = {"ticker": ticker, "session": session, "traded_value": traded, "foreign_flow": foreign, "foreign_room": room, "proprietary_flow": prop, "active_order_context": active, "price_flow_relationships": relationships, "coverage": {"available_dimensions": sum(item["status"] == "AVAILABLE" for item in sections), "provider_disposition": _status(observations)}, "authority_boundaries": ["CURRENT_RESEARCH_ONLY", "NON_CAUSAL", "NOT_LIQUIDITY_OR_SIZING", "NOT_EXECUTION", "NOT_INSTITUTIONAL_INTENT"]}
        record["flow_positioning_record_id"] = "flow_positioning_record:" + stable_id(record); records[ticker] = record
    coverage = {"UNIVERSE_COUNT": len(records), "ANY_FLOW_CONTEXT": sum(r["coverage"]["available_dimensions"] > 0 for r in records.values()), "TRADED_VALUE_READY": sum(r["traded_value"]["status"] == "AVAILABLE" for r in records.values()), "FOREIGN_FLOW_READY": sum(r["foreign_flow"]["status"] == "AVAILABLE" for r in records.values()), "FOREIGN_ROOM_READY": sum(r["foreign_room"]["status"] == "AVAILABLE" for r in records.values()), "PROPRIETARY_FLOW_READY": sum(r["proprietary_flow"]["status"] == "AVAILABLE" for r in records.values()), "ACTIVE_ORDER_READY": sum(r["active_order_context"]["status"] == "AVAILABLE" for r in records.values()), "MULTI_DIMENSION_READY": sum(r["coverage"]["available_dimensions"] >= 2 for r in records.values())}
    eligible = [ticker for ticker, row in records.items() if row["traded_value"]["status"] == "AVAILABLE"]
    matched = sum(row["traded_value"].get("fields", {}).get("MATCHED_TRADED_VALUE_VND", {}).get("value", 0) for row in records.values() if row["traded_value"]["status"] == "AVAILABLE")
    put_through = sum(row["traded_value"].get("fields", {}).get("PUT_THROUGH_TRADED_VALUE_VND", {}).get("value", 0) for row in records.values() if row["traded_value"]["status"] == "AVAILABLE")
    market = {"status": "AVAILABLE" if len(eligible) >= 20 else "PARTIAL_COHORT_CONTEXT", "eligible_ticker_count": len(eligible), "eligible_cohort": eligible, "aggregate_matched_value": matched, "aggregate_put_through_value": put_through, "put_through_share": put_through / (matched + put_through) if matched + put_through > 0 else None, "foreign_net_buy_names": sum(row["foreign_flow"]["state"] == "NET_FOREIGN_BUY" for row in records.values()), "foreign_net_sell_names": sum(row["foreign_flow"]["state"] == "NET_FOREIGN_SELL" for row in records.values()), "prop_net_buy_names": sum(row["proprietary_flow"]["state"] == "NET_PROP_BUY" for row in records.values()), "prop_net_sell_names": sum(row["proprietary_flow"]["state"] == "NET_PROP_SELL" for row in records.values()), "active_buy_skew_names": sum(row["active_order_context"]["state"] == "ACTIVE_BUY_SKEW" for row in records.values()), "active_sell_skew_names": sum(row["active_order_context"]["state"] == "ACTIVE_SELL_SKEW" for row in records.values()), "cohort_note": "Aggregates cover only the named eligible cohort, not the whole market."}
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "session": session, "source_artifact_identities": {"canonical_integration": canonical_integration.get("integration_identity") or canonical_integration.get("artifact_identity"), "tactical": (tactical or {}).get("artifact_identity")}, "thresholds": {"traded_value": "v1:0,.20,.50,.75", "foreign_room": "v1:.50,.80,.95", "active_order": "v1:abs(net_ratio)<.10"}, "records": records, "coverage": coverage, "market_level_flow_context": market, "peer_relative_flow_context": {"status": "NOT_EMITTED", "reason": "Sector-comparable cohort minimum is not asserted by this artifact."}, "data_dispositions": dict(sorted(Counter(r["coverage"]["provider_disposition"] for r in records.values()).items())), "authority_boundary": {"current_research_only": True, "causal_or_intent_claims": "NOT_EMITTED", "liquidity_sizing_execution": "BLOCKED", "pit_backtest_raw_as_traded": "NOT_PROMOTED"}, "is_actionable": False}
    artifact.update(content_identity(artifact)); return artifact


def prospective_context(artifact: Mapping[str, Any]) -> dict[str, Any]:
    rows = [{"ticker": ticker, "flow_positioning_record_id": row["flow_positioning_record_id"], "foreign_flow_state": row["foreign_flow"]["state"], "proprietary_flow_state": row["proprietary_flow"]["state"], "active_order_state": row["active_order_context"]["state"], "traded_value_state": row["traded_value"]["state"], "price_flow_relationships": row["price_flow_relationships"]} for ticker, row in sorted(artifact["records"].items())]
    payload = {"schema_version": "1.0.0", "contract_version": "prospective_research_learning/current_market_flow_positioning/v1", "research_session": artifact["session"], "source_artifact_identities": {"flow_positioning": artifact["artifact_identity"]}, "frozen_records": rows, "future_outcomes": "PENDING_FUTURE_OBSERVATION", "authority_boundary": "IDENTITY_FREEZE_ONLY_NOT_OUTCOME_OR_PERFORMANCE"}
    payload["snapshot_id"] = "prospective_research_snapshot:" + stable_id(payload); return payload
