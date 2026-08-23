"""Deterministic, multi-strategy current research classification.

Strategy fit is intentionally independent from entry timing, scenario probability,
and portfolio action.  The registry is small but executable: each strategy has its
own declared requirements and each ticker receives independent requirement results.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Mapping

from field_temporal_contract import stable_id

CONTRACT_VERSION = "polymorphic_current_strategy_classification/v1"
STRATEGY_REGISTRY = {
    "TREND_MOMENTUM": {"strategy_version": "v1", "intended_horizon": "MULTI_WEEK_SWING", "required_features": ["CURRENT_TECHNICAL", "UPTREND_TACTICAL_STATE"], "optional_enriching_features": ["PEER_TECHNICAL_CONTEXT"], "allowed_authority": ["SHADOW_ONLY", "DERIVED_PROXY"], "forbidden_substitutes": ["UNQUALIFIED_LIQUIDITY", "HISTORICAL_PIT"], "eligibility_rule": "current technical features available AND entry_state == UPTREND_CONFIRMED", "evidence_for_rule": "reuse existing tactical evidence_for", "counter_evidence_rule": "reuse existing tactical evidence_against", "invalidating_evidence": "existing tactical invalidation"},
    "BREAKOUT": {"strategy_version": "v1", "intended_horizon": "SHORT_TERM_TO_MULTI_WEEK", "required_features": ["CURRENT_TECHNICAL", "BREAKOUT_TACTICAL_STATE"], "optional_enriching_features": ["PEER_TECHNICAL_CONTEXT", "RELATIVE_VOLUME_PROXY"], "allowed_authority": ["SHADOW_ONLY", "DERIVED_PROXY"], "forbidden_substitutes": ["QUALIFIED_LIQUIDITY_CLAIM", "PRICE_TARGET"], "eligibility_rule": "current technical features available AND entry_state == BREAKOUT_READY", "evidence_for_rule": "reuse existing tactical evidence_for", "counter_evidence_rule": "reuse existing tactical evidence_against", "invalidating_evidence": "existing tactical invalidation"},
    "EARLY_REVERSAL": {"strategy_version": "v1", "intended_horizon": "SHORT_TERM_FEW_SESSIONS", "required_features": ["CURRENT_TECHNICAL", "EARLY_REVERSAL_TACTICAL_STATE"], "optional_enriching_features": ["PEER_TECHNICAL_CONTEXT"], "allowed_authority": ["SHADOW_ONLY"], "forbidden_substitutes": ["CONFIRMED_TREND_ASSUMPTION"], "eligibility_rule": "current technical features available AND entry_state == EARLY_REVERSAL_CANDIDATE", "evidence_for_rule": "reuse existing tactical evidence_for", "counter_evidence_rule": "reuse existing tactical evidence_against", "invalidating_evidence": "existing tactical invalidation"},
    "BASE_ACCUMULATION": {"strategy_version": "v1", "intended_horizon": "MULTI_WEEK_SWING", "required_features": ["CURRENT_TECHNICAL", "BASE_TACTICAL_STATE"], "optional_enriching_features": ["PEER_TECHNICAL_CONTEXT"], "allowed_authority": ["SHADOW_ONLY"], "forbidden_substitutes": ["VOLUME_AS_LIQUIDITY"], "eligibility_rule": "current technical features available AND entry_state == BASE_BUILDING", "evidence_for_rule": "reuse existing tactical evidence_for", "counter_evidence_rule": "reuse existing tactical evidence_against", "invalidating_evidence": "existing tactical invalidation"},
    "FUNDAMENTAL_IMPROVEMENT": {"strategy_version": "v1", "intended_horizon": "MULTI_QUARTER_DESCRIPTIVE", "required_features": ["FUNDAMENTAL_TRAJECTORY", "FUNDAMENTAL_ALIGNMENT"], "optional_enriching_features": ["PEER_FUNDAMENTAL_CONTEXT"], "allowed_authority": ["OFFICIAL_QUALIFIED", "PROVIDER_RESEARCH"], "forbidden_substitutes": ["PROVIDER_ABSOLUTE_VALUE_AS_OFFICIAL", "VALUATION_CONCLUSION"], "eligibility_rule": "retained trajectory is available and revenue/earnings alignment is BOTH_EXPANDING", "evidence_for_rule": "reuse trajectory direction fields", "counter_evidence_rule": "reuse trajectory limitations and non-alignment", "invalidating_evidence": "later retained trajectory contradiction"},
    "EVENT_DRIVEN": {"strategy_version": "v1", "intended_horizon": "EVENT_SPECIFIC", "required_features": ["CURRENT_OFFICIAL_EVENT"], "optional_enriching_features": ["EVENT_EXECUTION_CONFIRMATION"], "allowed_authority": ["OFFICIAL_QUALIFIED"], "forbidden_substitutes": ["NEWS_DISCOVERY", "PLANNED_AS_EXECUTED"], "eligibility_rule": "a retained official current event exists", "evidence_for_rule": "reuse Corporate Intelligence event evidence", "counter_evidence_rule": "reuse lifecycle and freshness limitations", "invalidating_evidence": "later cancellation/amendment or loss of current relevance"},
    "VALUE": {"strategy_version": "v1", "intended_horizon": "MULTI_QUARTER", "required_features": ["AUTHORITATIVE_CURRENT_VALUATION"], "optional_enriching_features": [], "allowed_authority": ["OFFICIAL_QUALIFIED"], "forbidden_substitutes": ["SHADOW_ISSUED_SHARE_PROXY", "PROVIDER_RESEARCH_ABSOLUTE_FINANCIALS"], "eligibility_rule": "strict current valuation is authority-ready", "evidence_for_rule": "authoritative valuation metrics", "counter_evidence_rule": "strict valuation blockers", "invalidating_evidence": "valuation authority loss"},
}


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact)); payload.pop("artifact_sha256", None); payload.pop("artifact_identity", None)
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": "polymorphic_current_strategy_classification:" + digest}


def _requirement(feature_id: str, available: bool, status: str, method: str, quality: str, authority: str, allowed: bool, reason: str) -> dict[str, Any]:
    item = {"feature_id": feature_id, "availability": available, "status": status, "method": method, "quality": quality, "authority": authority, "allowed_for_strategy": allowed, "reason": reason}
    item["requirement_identity"] = "strategy_requirement:" + stable_id(item)
    return item


def _technical(tactical: Mapping[str, Any]) -> dict[str, Any]:
    quality = tactical.get("data_quality") or {}; ok = quality.get("technical_eligible") is True and quality.get("is_current_session") is True
    return _requirement("CURRENT_TECHNICAL", ok, "SATISFIED" if ok else "MISSING", "retained_current_technical_features", "CURRENT_SESSION_SHADOW", "SHADOW_ONLY", ok, "Current technical feature eligibility is retained." if ok else "CURRENT_TECHNICAL_FEATURES_UNAVAILABLE")


def _state_requirement(feature_id: str, tactical: Mapping[str, Any], expected: str) -> dict[str, Any]:
    actual = tactical.get("entry_state"); fit = actual == expected
    return _requirement(feature_id, actual is not None, "SATISFIED" if fit else "NOT_MET", "existing_tactical_classifier_state", "CURRENT_DETERMINISTIC_RESEARCH", "CURRENT_DETERMINISTIC_RESEARCH", True, f"entry_state={actual or 'UNAVAILABLE'}; strategy requires {expected}")


def _fundamental_requirements(fundamental: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    context = fundamental.get("fundamental_trajectory_context") or {}; authority = fundamental.get("authority_tier") or "UNAVAILABLE"
    available = context.get("trajectory_status") == "AVAILABLE" and authority in {"OFFICIAL_QUALIFIED", "PROVIDER_RESEARCH"}
    alignment = context.get("revenue_vs_earnings_alignment") or {}; aligned = alignment.get("status") == "BOTH_EXPANDING"
    trajectory = _requirement("FUNDAMENTAL_TRAJECTORY", available, "SATISFIED" if available else "MISSING", "retained_same_provider_trajectory", "DESCRIPTIVE_PROVIDER_OR_OFFICIAL", authority, available, "Retained fundamental trajectory is available." if available else "FUNDAMENTAL_TRAJECTORY_UNAVAILABLE")
    alignment_requirement = _requirement("FUNDAMENTAL_ALIGNMENT", alignment.get("status") is not None, "SATISFIED" if aligned else "NOT_MET" if alignment.get("status") else "MISSING", "retained_revenue_earnings_alignment", "DESCRIPTIVE_PROVIDER_OR_OFFICIAL", authority, available, "Revenue/earnings alignment is BOTH_EXPANDING." if aligned else f"revenue_earnings_alignment={alignment.get('status') or 'UNAVAILABLE'}")
    return trajectory, alignment_requirement


def _event_requirement(corporate: Mapping[str, Any]) -> dict[str, Any]:
    research = corporate.get("catalyst_research") or {}; events = research.get("recent_material_events") or []
    return _requirement("CURRENT_OFFICIAL_EVENT", bool(events), "SATISFIED" if events else "MISSING", "retained_corporate_intelligence_event", "SOURCE_LINKED_EVENT", "OFFICIAL_QUALIFIED" if events else "UNAVAILABLE", bool(events), "Current retained official event available." if events else "NO_CURRENT_RETAINED_OFFICIAL_EVENT")


def _valuation_requirement(valuation: Mapping[str, Any]) -> dict[str, Any]:
    ready = any(value.get("status") == "READY" for value in (valuation.get("metrics") or {}).values() if isinstance(value, Mapping))
    return _requirement("AUTHORITATIVE_CURRENT_VALUATION", ready, "SATISFIED" if ready else "BLOCKED", "strict_current_valuation_contract", "OFFICIAL_CURRENT_SHARE_AND_FINANCIAL_AUTHORITY", "OFFICIAL_QUALIFIED" if ready else "BLOCKED", ready, "Strict authoritative valuation is ready." if ready else "AUTHORITATIVE_CURRENT_VALUATION_CONTRACT_NOT_AVAILABLE; SHADOW_ISSUED_SHARE_PROXY_FORBIDDEN")


def _strategy(strategy_id: str, requirements: list[dict[str, Any]], tactical: Mapping[str, Any], scenario: Mapping[str, Any], peer: Mapping[str, Any], fundamental: Mapping[str, Any], corporate: Mapping[str, Any]) -> dict[str, Any]:
    statuses = {item["feature_id"]: item["status"] for item in requirements}
    if strategy_id == "VALUE": status = "ELIGIBLE" if statuses["AUTHORITATIVE_CURRENT_VALUATION"] == "SATISFIED" else "BLOCKED"
    elif strategy_id == "FUNDAMENTAL_IMPROVEMENT":
        status = "ELIGIBLE" if all(value == "SATISFIED" for value in statuses.values()) else "INSUFFICIENT_DATA" if statuses["FUNDAMENTAL_TRAJECTORY"] == "MISSING" else "PARTIAL"
    elif strategy_id == "EVENT_DRIVEN":
        historical = (corporate.get("catalyst_research") or {}).get("historical_context") or []
        pending = (corporate.get("catalyst_research") or {}).get("watch_for_execution") or []
        status = "ELIGIBLE" if statuses["CURRENT_OFFICIAL_EVENT"] == "SATISFIED" else "PARTIAL" if historical or pending else "INSUFFICIENT_DATA"
    else:
        status = "ELIGIBLE" if all(value == "SATISFIED" for value in statuses.values()) else "INSUFFICIENT_DATA" if statuses.get("CURRENT_TECHNICAL") == "MISSING" else "NOT_APPLICABLE"
    satisfied = [item for item in requirements if item["status"] == "SATISFIED"]
    missing = [item for item in requirements if item["status"] == "MISSING"]
    blocked = [item for item in requirements if item["status"] == "BLOCKED" or not item["allowed_for_strategy"]]
    evidence_for = list(tactical.get("evidence_for") or []) if strategy_id in {"TREND_MOMENTUM", "BREAKOUT", "EARLY_REVERSAL", "BASE_ACCUMULATION"} else []
    counter = list(tactical.get("evidence_against") or []) if strategy_id in {"TREND_MOMENTUM", "BREAKOUT", "EARLY_REVERSAL", "BASE_ACCUMULATION"} else []
    if strategy_id == "FUNDAMENTAL_IMPROVEMENT":
        context = fundamental.get("fundamental_trajectory_context") or {}; evidence_for = [f"{key}={context.get(key)}" for key in ("revenue_direction", "earnings_direction", "revenue_vs_earnings_alignment") if context.get(key)]
        counter = list(context.get("data_limitations") or [])
    if strategy_id == "EVENT_DRIVEN":
        evidence_for = [event["event_id"] for event in ((corporate.get("catalyst_research") or {}).get("recent_material_events") or [])]
        counter = [item["reason"] for item in requirements if item["status"] != "SATISFIED"]
    if strategy_id == "VALUE": counter = [item["reason"] for item in requirements]
    return {"strategy_id": strategy_id, "strategy_version": STRATEGY_REGISTRY[strategy_id]["strategy_version"], "status": status, "requirements": requirements, "satisfied_requirements": [item["requirement_identity"] for item in satisfied], "missing_requirements": [item["requirement_identity"] for item in missing], "blocked_requirements": [item["requirement_identity"] for item in blocked], "evidence_for": evidence_for, "evidence_against": counter, "authority_profile": {"allowed_authority": STRATEGY_REGISTRY[strategy_id]["allowed_authority"], "forbidden_substitutes": STRATEGY_REGISTRY[strategy_id]["forbidden_substitutes"]}, "data_quality": {"technical": (tactical.get("data_quality") or {}).get("technical_eligible"), "peer_context": ((peer.get("technical_peer_context") or {}).get("status")), "fundamental_authority": fundamental.get("authority_tier")}, "current_fit": "CURRENT_STRATEGY_FIT" if status == "ELIGIBLE" else "NOT_CURRENTLY_ELIGIBLE", "tactical_relationship": {"entry_state": tactical.get("entry_state"), "entry_action": tactical.get("entry_action"), "separate_from_strategy": True}, "scenario_relationship": {"scenario_disposition": scenario.get("scenario_disposition"), "probability_status": scenario.get("probability_status", "UNKNOWN_UNCALIBRATED"), "bull_case": (scenario.get("bull_case") or {}).get("case_status"), "separate_from_strategy": True}, "limitations": ["Strategy eligibility is not BUY, portfolio, sizing, or execution authority.", "Scenario probability remains UNKNOWN_UNCALIBRATED."]}


def build(*, descriptive: Mapping[str, Any], tactical: Mapping[str, Any], peer_relative: Mapping[str, Any], fundamental: Mapping[str, Any], valuation: Mapping[str, Any], scenario: Mapping[str, Any], corporate_intelligence: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(descriptive.get("records"), Mapping) or descriptive.get("session") != tactical.get("session") or scenario.get("session") != descriptive.get("session"):
        raise ValueError("STRATEGY_CLASSIFICATION_SESSION_OR_RECORDS_MISMATCH")
    sources = {"descriptive": descriptive["artifact_identity"], "tactical": tactical["artifact_identity"], "peer_relative": peer_relative["artifact_identity"], "fundamental": fundamental["artifact_identity"], "valuation": valuation["artifact_identity"], "scenario": scenario["artifact_identity"], "corporate_intelligence": corporate_intelligence["artifact_identity"]}
    records = {}
    for ticker in sorted(descriptive["records"]):
        t, p, f, v, s, c = tactical.get("records", {}).get(ticker) or {}, peer_relative.get("records", {}).get(ticker) or {}, fundamental.get("records", {}).get(ticker) or {}, valuation.get("records", {}).get(ticker) or {}, scenario.get("records", {}).get(ticker) or {}, corporate_intelligence.get("records", {}).get(ticker) or {}
        technical = _technical(t); trajectory, alignment = _fundamental_requirements(f); event, value = _event_requirement(c), _valuation_requirement(v)
        strategy_map = {
            "TREND_MOMENTUM": _strategy("TREND_MOMENTUM", [technical, _state_requirement("UPTREND_TACTICAL_STATE", t, "UPTREND_CONFIRMED")], t, s, p, f, c),
            "BREAKOUT": _strategy("BREAKOUT", [technical, _state_requirement("BREAKOUT_TACTICAL_STATE", t, "BREAKOUT_READY")], t, s, p, f, c),
            "EARLY_REVERSAL": _strategy("EARLY_REVERSAL", [technical, _state_requirement("EARLY_REVERSAL_TACTICAL_STATE", t, "EARLY_REVERSAL_CANDIDATE")], t, s, p, f, c),
            "BASE_ACCUMULATION": _strategy("BASE_ACCUMULATION", [technical, _state_requirement("BASE_TACTICAL_STATE", t, "BASE_BUILDING")], t, s, p, f, c),
            "FUNDAMENTAL_IMPROVEMENT": _strategy("FUNDAMENTAL_IMPROVEMENT", [trajectory, alignment], t, s, p, f, c),
            "EVENT_DRIVEN": _strategy("EVENT_DRIVEN", [event], t, s, p, f, c),
            "VALUE": _strategy("VALUE", [value], t, s, p, f, c),
        }
        eligible = [key for key, item in strategy_map.items() if item["status"] == "ELIGIBLE"]
        record = {"ticker": ticker, "research_session": descriptive["session"], "strategies": strategy_map, "eligible_strategy_ids": eligible, "record_strategy_state": "MULTI_STRATEGY_ELIGIBLE" if len(eligible) > 1 else "SINGLE_STRATEGY_ELIGIBLE" if eligible else "DATA_LIMITED" if any(item["status"] in {"INSUFFICIENT_DATA", "BLOCKED", "PARTIAL"} for item in strategy_map.values()) else "NO_CURRENT_STRATEGY_FIT", "tactical_context": {"entry_state": t.get("entry_state"), "entry_action": t.get("entry_action")}, "scenario_context": {"scenario_disposition": s.get("scenario_disposition"), "probability_status": s.get("probability_status")}, "fundamental_context": {"authority_tier": f.get("authority_tier"), "trajectory_status": (f.get("fundamental_trajectory_context") or {}).get("trajectory_status")}, "event_context": {"disposition": c.get("intelligence_disposition"), "event_ids": [event.get("event_id") for event in c.get("events") or []]}}
        record["strategy_record_id"] = "current_strategy_record:" + stable_id(record); records[ticker] = record
    status_counts = {strategy: Counter(record["strategies"][strategy]["status"] for record in records.values()) for strategy in STRATEGY_REGISTRY}
    blockers = {strategy: Counter(reason["reason"] for record in records.values() for reason in record["strategies"][strategy]["requirements"] if reason["status"] in {"MISSING", "BLOCKED"}) for strategy in STRATEGY_REGISTRY}
    coverage = {"universe_count": len(records), "any_strategy_eligible": sum(bool(record["eligible_strategy_ids"]) for record in records.values()), "multi_strategy_eligible": sum(len(record["eligible_strategy_ids"]) > 1 for record in records.values()), "no_strategy_eligible": sum(not record["eligible_strategy_ids"] for record in records.values()), "data_limited": sum(record["record_strategy_state"] == "DATA_LIMITED" for record in records.values()), "per_strategy_status_counts": {key: dict(sorted(value.items())) for key, value in status_counts.items()}, "top_blockers_by_strategy": {key: dict(value.most_common(5)) for key, value in blockers.items()}, "entity_class_coverage": dict(sorted(Counter((fundamental.get("records", {}).get(ticker) or {}).get("entity_class", "unknown") for ticker in records).items())), "tactical_state_intersections": {key: sum(key in record["eligible_strategy_ids"] for record in records.values()) for key in STRATEGY_REGISTRY}, "scenario_intersections": dict(sorted(Counter(f"{record['scenario_context'].get('scenario_disposition')}|{strategy}" for record in records.values() for strategy in record["eligible_strategy_ids"]).items()))}
    cohorts = {strategy + "_STRATEGY_ELIGIBLE": [ticker for ticker, record in sorted(records.items()) if strategy in record["eligible_strategy_ids"]] for strategy in STRATEGY_REGISTRY}
    cohorts["MULTI_STRATEGY_ELIGIBLE"] = [ticker for ticker, record in sorted(records.items()) if len(record["eligible_strategy_ids"]) > 1]
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "session": descriptive["session"], "strategy_registry": STRATEGY_REGISTRY, "strategy_status_vocabulary": ["ELIGIBLE", "PARTIAL", "BLOCKED", "NOT_APPLICABLE", "INSUFFICIENT_DATA"], "source_artifact_identities": sources, "records": records, "coverage": coverage, "research_cohorts": cohorts, "authority_boundary": {"strategy_not_tactical_entry": True, "strategy_not_scenario_probability": True, "strategy_not_portfolio_action": True, "no_best_strategy_or_composite_score": True, "value_requires_authoritative_current_valuation": True, "no_pit_raw_as_traded_or_liquidity_authority": True}, "is_actionable": False}
    artifact.update(content_identity(artifact)); return artifact


def prospective_context(artifact: Mapping[str, Any]) -> dict[str, Any]:
    rows = [{"ticker": ticker, "strategy_record_id": record["strategy_record_id"], "eligible_strategy_ids": record["eligible_strategy_ids"], "strategy_versions": {key: item["strategy_version"] for key, item in record["strategies"].items()}, "strategy_statuses": {key: item["status"] for key, item in record["strategies"].items()}, "tactical_state": record["tactical_context"]["entry_state"]} for ticker, record in sorted(artifact["records"].items())]
    payload = {"schema_version": "1.0.0", "contract_version": "prospective_research_learning/current_strategy_context/v1", "research_session": artifact["session"], "source_artifact_identities": {"strategy": artifact["artifact_identity"]}, "frozen_records": rows, "cohort_count": len(rows), "future_outcomes": "PENDING_FUTURE_OBSERVATION", "authority_boundary": "IDENTITY_FREEZE_ONLY_NOT_OUTCOME_OR_STRATEGY_PERFORMANCE"}
    payload["snapshot_id"] = "prospective_research_snapshot:" + stable_id(payload); return payload
