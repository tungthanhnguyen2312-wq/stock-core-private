"""Current-universe port of the retained evidence-bound scenario contract.

It reuses the existing Bear/Base/Bull vocabulary from expectations_scenario_research;
every case is conditional and descriptive, never a forecast or recommendation.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Mapping

from field_temporal_contract import stable_id

CONTRACT_VERSION = "current_evidence_bound_scenario/v1"
WATCHLIST = ("EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM")
PREOPEN_47 = ("ABB", "ABS", "BCA", "BHN", "BSH", "BTH", "DCV", "DHB", "FDC", "GCF", "H11", "HCC", "KTL", "LMC", "LMH", "MEL", "MKV", "PJC", "POM", "PWA", "SHN", "SPM", "TH1", "TNI", "TTS", "VMS", "VQC", "VRC", "VSF", "VVS", "AGG", "AVC", "BMC", "BMP", "C47", "HD6", "SMC", "TDT", "VC3", "VCF", "VIC", "VNS", "VPL", "AAN", "ABW", "DHG", "HCM")
DRIVER_TYPES = ("MARKET_CONTEXT", "TECHNICAL", "TACTICAL", "PEER_RELATIVE", "FUNDAMENTAL", "VALUATION_CONTEXT", "CATALYST_OR_EVENT", "DATA_QUALITY")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact)); payload.pop("artifact_sha256", None); payload.pop("artifact_identity", None)
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": "current_evidence_bound_scenario:" + digest}


def _case_id(ticker: str, name: str, source_identities: Mapping[str, Any]) -> str:
    return "current_evidence_bound_scenario_case:" + stable_id({"ticker": ticker, "case": name, "sources": source_identities})


def _catalysts(catalyst: Mapping[str, Any] | None) -> dict[str, Any]:
    if not catalyst: return {"status": "NO_QUALIFIED_CATALYST_EVIDENCE", "events": [], "limitations": ["No retained catalyst record for ticker."]}
    events = catalyst.get("event_facts") or []
    return {"status": "OBSERVED_CATALYST" if events else "NO_QUALIFIED_CATALYST_EVIDENCE", "events": events, "source_session": catalyst.get("research_session"), "limitations": ["Observed event is not a price-impact or outcome claim."]}


def _driver(status: str, evidence: Any, limitations: list[str] | None = None) -> dict[str, Any]:
    return {"status": status, "evidence": evidence, "limitations": limitations or []}


def _drivers(tactical: Mapping[str, Any], peer: Mapping[str, Any] | None, fundamental: Mapping[str, Any] | None,
             valuation: Mapping[str, Any] | None, catalyst: Mapping[str, Any] | None) -> dict[str, Any]:
    technical_ready = bool((tactical.get("data_quality") or {}).get("technical_eligible"))
    entry_state = tactical.get("entry_state")
    peer_technical = (peer or {}).get("technical_peer_context") or {}
    fund_context = (fundamental or {}).get("fundamental_trajectory_context") or {}
    valuation_context = (peer or {}).get("valuation_peer_context") or {}
    return {
        "MARKET_CONTEXT": _driver("SUPPORTIVE" if tactical.get("market_state") else "UNAVAILABLE", {"market_state": tactical.get("market_state")}),
        "TECHNICAL": _driver("SUPPORTIVE" if technical_ready else "UNAVAILABLE", {"ticker_structure_state": tactical.get("ticker_structure_state"), "signals": tactical.get("signals")}, list((tactical.get("data_quality") or {}).get("warnings") or [])),
        "TACTICAL": _driver("SUPPORTIVE" if entry_state else "UNAVAILABLE", {"entry_state": entry_state, "confirmation_trigger": tactical.get("confirmation_trigger"), "invalidation": tactical.get("invalidation"), "rule_id": tactical.get("rule_id")}),
        "PEER_RELATIVE": _driver("SUPPORTIVE" if peer_technical.get("status") == "AVAILABLE" else "UNAVAILABLE", {"peer_membership": (peer or {}).get("peer_membership"), "technical_peer_context": peer_technical, "expectations_context": (peer or {}).get("expectations_context")}, list((peer or {}).get("data_gaps") or [])),
        "FUNDAMENTAL": _driver("SUPPORTIVE" if fund_context else "UNAVAILABLE", {"trajectory": fund_context, "authority_tier": (fundamental or {}).get("authority_tier")}, list(fund_context.get("data_limitations") or [])),
        "VALUATION_CONTEXT": _driver("UNAVAILABLE", {"strict_current_valuation": valuation or {}, "peer_valuation": valuation_context}, ["Strict current valuation is blocked or non-discriminating; shadow proxy is not target-price authority."]),
        "CATALYST_OR_EVENT": _driver("SUPPORTIVE" if catalyst and catalyst.get("status") == "OBSERVED_CATALYST" else "UNAVAILABLE", catalyst or {"status": "NO_QUALIFIED_CATALYST_EVIDENCE"}),
        "DATA_QUALITY": _driver("SUPPORTIVE" if technical_ready else "CONTRADICTORY", tactical.get("data_quality") or {}, list((tactical.get("data_quality") or {}).get("warnings") or [])),
    }


def _disposition(tactical: Mapping[str, Any], drivers: Mapping[str, Any]) -> str:
    if not tactical.get("entry_state") or drivers["TECHNICAL"]["status"] == "UNAVAILABLE": return "SCENARIO_INSUFFICIENT_DATA"
    if drivers["PEER_RELATIVE"]["status"] == "UNAVAILABLE" or drivers["FUNDAMENTAL"]["status"] == "UNAVAILABLE": return "SCENARIO_PARTIAL"
    return "SCENARIO_READY"


def _cases(ticker: str, disposition: str, tactical: Mapping[str, Any], drivers: Mapping[str, Any], source_ids: Mapping[str, Any]) -> dict[str, Any]:
    state, horizon = tactical.get("entry_state") or "NOT_AVAILABLE", tactical.get("horizon") or "UNSPECIFIED_CURRENT_HORIZON"
    confirmation, invalidation = tactical.get("confirmation_trigger"), tactical.get("invalidation")
    support, counter = tactical.get("evidence_for") or [], tactical.get("evidence_against") or []
    gaps = [name for name, value in drivers.items() if value["status"] == "UNAVAILABLE"]
    case_status = "CONDITIONAL" if disposition != "SCENARIO_INSUFFICIENT_DATA" else "INSUFFICIENT_EVIDENCE"
    common = {"case_status": case_status, "time_horizon": horizon, "probability_status": "UNKNOWN_UNCALIBRATED", "evidence_authority": "RETAINED_CURRENT_DETERMINISTIC_RESEARCH_ONLY", "data_gaps": gaps, "authority_limitations": ["Conditional scenario, not prediction or probability.", "No target, expected return, recommendation, ranking, or sizing."]}
    return {
        "BEAR": common | {"case_id": _case_id(ticker, "BEAR", source_ids), "observed_support": counter, "required_confirmations": [invalidation] if invalidation else [], "counter_evidence": support, "invalidation": invalidation, "case_conditions": ["Existing tactical invalidation or deterioration condition is met."], "driver_states": {name: value["status"] for name, value in drivers.items()}},
        "BASE": common | {"case_id": _case_id(ticker, "BASE", source_ids), "current_state": state, "continuation_conditions": [f"Current tactical state remains {state} without a new confirmation or invalidation."], "transition_to_bull_conditions": [confirmation] if confirmation else [], "transition_to_bear_conditions": [invalidation] if invalidation else [], "evidence_for": support, "evidence_against": counter, "limitations": ["Reference/current-continuation case; not most probable."]},
        "BULL": common | {"case_id": _case_id(ticker, "BULL", source_ids), "observed_support": support, "required_confirmations": [confirmation] if confirmation else [], "counter_evidence": counter, "invalidation": invalidation, "case_conditions": ["Existing tactical confirmation trigger is met.", "Any available peer/fundamental driver remains non-contradictory."], "driver_states": {name: value["status"] for name, value in drivers.items()}},
    }


def _detail(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: record[key] for key in ("ticker", "scenario_disposition", "current_state", "bear_case", "base_case", "bull_case", "key_driver_conflicts", "confirmation_trigger", "invalidation", "peer_context", "fundamental_context", "valuation_context", "catalyst_context", "time_horizon", "data_quality", "authority_limitations")}


def build(*, descriptive: Mapping[str, Any], tactical: Mapping[str, Any], peer_relative: Mapping[str, Any], fundamental: Mapping[str, Any], valuation: Mapping[str, Any], triage: Mapping[str, Any], catalyst: Mapping[str, Any] | None = None, screening: Mapping[str, Any] | None = None) -> dict[str, Any]:
    d, t, p, f, v = descriptive["records"], tactical["records"], peer_relative["records"], fundamental["records"], valuation["records"]
    catalyst_by_ticker = {row["ticker"]: row for row in (catalyst or {}).get("records", []) if isinstance(row, Mapping)}
    source_ids = {"descriptive": descriptive["artifact_identity"], "tactical": tactical["artifact_identity"], "peer_relative": peer_relative["artifact_identity"], "fundamental": fundamental["artifact_identity"], "valuation": valuation["artifact_identity"], "triage": triage["artifact_identity"], "catalyst": (catalyst or {}).get("artifact_identity"), "screening": (screening or {}).get("artifact_identity")}
    records: dict[str, Any] = {}
    for ticker in sorted(d):
        tactical_row, peer_row, fund_row, valuation_row = t.get(ticker) or {}, p.get(ticker), f.get(ticker), v.get(ticker)
        catalyst_context = _catalysts(catalyst_by_ticker.get(ticker)); drivers = _drivers(tactical_row, peer_row, fund_row, valuation_row, catalyst_context); disposition = _disposition(tactical_row, drivers); cases = _cases(ticker, disposition, tactical_row, drivers, source_ids)
        conflicts = [name for name, value in drivers.items() if value["status"] == "CONTRADICTORY"]
        records[ticker] = {"ticker": ticker, "scenario_disposition": disposition, "probability_status": "UNKNOWN_UNCALIBRATED", "current_state": {"market_state": tactical_row.get("market_state"), "ticker_structure_state": tactical_row.get("ticker_structure_state"), "entry_state": tactical_row.get("entry_state")}, "observed_facts": {"descriptive_activity": (d[ticker].get("activity_and_session_state")), "technical_current_session": ((d[ticker].get("technical_features") or {}).get("is_current_session")), "tactical_state": tactical_row.get("entry_state")}, "conditional_assumptions": ["Future conditions are not observed facts.", "Base means continuation/reference, not most likely."], "scenario_drivers": drivers, "bear_case": cases["BEAR"], "base_case": cases["BASE"], "bull_case": cases["BULL"], "key_driver_conflicts": conflicts, "confirmation_trigger": tactical_row.get("confirmation_trigger"), "invalidation": tactical_row.get("invalidation"), "peer_context": peer_row or {"status": "UNAVAILABLE"}, "fundamental_context": (fund_row or {}).get("fundamental_trajectory_context") or {"status": "UNAVAILABLE"}, "valuation_context": {"strict_status": (valuation_row or {}).get("status", "UNAVAILABLE"), "shadow_proxy": (valuation_row or {}).get("shadow_proxy_valuation"), "peer_status": ((peer_row or {}).get("valuation_peer_context") or {}).get("status")}, "catalyst_context": catalyst_context, "time_horizon": tactical_row.get("horizon"), "data_quality": tactical_row.get("data_quality") or {}, "authority_limitations": ["Current deterministic research only.", "No calibrated probabilities, targets, expected returns, ranking, recommendation, sizing, portfolio, execution, or outcomes."], "is_actionable": False}
    entry_source = triage.get("all_entry_relevant_records", {})
    entry_rows = [row for rows in entry_source.values() for row in rows] if isinstance(entry_source, Mapping) else entry_source
    entry_90 = [row["ticker"] for row in entry_rows if isinstance(row, Mapping)]
    representative = {}
    for state in ("EARLY_REVERSAL_CANDIDATE", "BASE_BUILDING", "BREAKOUT_READY", "UPTREND_CONFIRMED", "DISTRIBUTION_RISK", "DOWNTREND"):
        ticker = next((key for key, value in records.items() if value["current_state"]["entry_state"] == state), None)
        if ticker: representative[state] = _detail(records[ticker])
    counts = Counter(record["scenario_disposition"] for record in records.values()); patterns = Counter()
    for record in records.values():
        if record["bull_case"]["required_confirmations"]: patterns["BULL_CASE_REQUIRES_TECHNICAL_CONFIRMATION"] += 1
        if record["scenario_drivers"]["FUNDAMENTAL"]["status"] == "SUPPORTIVE": patterns["BULL_CASE_FUNDAMENTAL_SUPPORT_AVAILABLE"] += 1
        else: patterns["BULL_CASE_FUNDAMENTAL_UNCERTAINTY"] += 1
        if record["current_state"]["entry_state"] in {"DISTRIBUTION_RISK", "BREAKDOWN_RISK", "DOWNTREND"}: patterns["BEAR_CASE_DISTRIBUTION_RISK"] += 1
        if record["current_state"]["entry_state"] in {"BASE_BUILDING", "SIDEWAYS_NEUTRAL"}: patterns["BASE_CASE_CONTINUED_CONSOLIDATION"] += 1
        if record["key_driver_conflicts"]: patterns["CONFLICTED_SCENARIO_EVIDENCE"] += 1
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "session": descriptive["session"], "source_artifact_identities": source_ids, "records": records, "case_definitions": {"BEAR": "Conditional deterioration/invalidation case.", "BASE": "Current-continuation reference; not most probable.", "BULL": "Conditional confirmation case."}, "coverage": {"universe_count": len(records), "scenario_disposition_counts": dict(sorted(counts.items())), "driver_coverage": {name: sum(record["scenario_drivers"][name]["status"] != "UNAVAILABLE" for record in records.values()) for name in DRIVER_TYPES}, "scenario_pattern_counts": dict(sorted(patterns.items()))}, "validation": {"watchlist": [_detail(records[x]) for x in WATCHLIST if x in records], "preopen_47": [_detail(records[x]) for x in PREOPEN_47 if x in records], "entry_relevant_90": [_detail(records[x]) for x in entry_90 if x in records], "representative_scenarios": representative}, "authority_boundary": {"research_only": True, "probabilities": "UNKNOWN_UNCALIBRATED", "targets_expected_returns_recommendations_rankings_sizing": "NOT_EMITTED", "valuation_case_discrimination": "NOT_EMITTED", "outcomes_or_calibration": "NOT_EMITTED"}, "data_limitations": ["Missing inputs narrow dependent cases only.", "Catalyst artifact is retained earlier-session evidence where present.", "Valuation peer context is unavailable under current authority constraints."], "is_actionable": False}
    artifact.update(content_identity(artifact)); return artifact
