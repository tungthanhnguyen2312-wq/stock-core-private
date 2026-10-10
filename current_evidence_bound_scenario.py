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
DRIVER_TYPES = ("MARKET_CONTEXT", "MARKET_FLOW_CONTEXT", "MACRO_CONTEXT", "TECHNICAL", "TACTICAL", "PEER_RELATIVE", "FUNDAMENTAL", "VALUATION_CONTEXT", "CATALYST_OR_EVENT", "DATA_QUALITY")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact)); payload.pop("artifact_sha256", None); payload.pop("artifact_identity", None)
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": "current_evidence_bound_scenario:" + digest}


def _case_id(ticker: str, name: str, source_identities: Mapping[str, Any]) -> str:
    return "current_evidence_bound_scenario_case:" + stable_id({"ticker": ticker, "case": name, "sources": source_identities})


def _catalysts(catalyst: Mapping[str, Any] | None, corporate_intelligence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if corporate_intelligence:
        research = corporate_intelligence.get("catalyst_research") or {}
        events = research.get("recent_material_events") or []
        pending = research.get("watch_for_execution") or []
        return {"status": "OBSERVED_CATALYST_OR_EVENT" if events else "PENDING_OR_HISTORICAL_EVENT_CONTEXT" if pending or research.get("historical_context") else "NO_RETAINED_INTELLIGENCE", "events": events, "pending": pending, "historical_context": research.get("historical_context") or [], "data_gaps": research.get("data_gaps") or [], "source_record_identity": corporate_intelligence.get("corporate_intelligence_record_id"), "limitations": ["Corporate event relevance is neutral unless retained evidence states more."]}
    if not catalyst: return {"status": "NO_QUALIFIED_CATALYST_EVIDENCE", "events": [], "limitations": ["No retained catalyst record for ticker."]}
    events = catalyst.get("event_facts") or []
    return {"status": "OBSERVED_CATALYST" if events else "NO_QUALIFIED_CATALYST_EVIDENCE", "events": events, "source_session": catalyst.get("research_session"), "limitations": ["Observed event is not a price-impact or outcome claim."]}


def _driver(status: str, evidence: Any, limitations: list[str] | None = None) -> dict[str, Any]:
    return {"status": status, "evidence": evidence, "limitations": limitations or []}


def _drivers(tactical: Mapping[str, Any], peer: Mapping[str, Any] | None, fundamental: Mapping[str, Any] | None,
             valuation: Mapping[str, Any] | None, catalyst: Mapping[str, Any] | None, macro_context: Mapping[str, Any] | None, flow: Mapping[str, Any] | None = None) -> dict[str, Any]:
    technical_ready = bool((tactical.get("data_quality") or {}).get("technical_eligible"))
    entry_state = tactical.get("entry_state")
    peer_technical = (peer or {}).get("technical_peer_context") or {}
    fund_context = (fundamental or {}).get("fundamental_trajectory_context") or {}
    valuation_context = (peer or {}).get("valuation_peer_context") or {}
    relationships = (flow or {}).get("price_flow_relationships") or []
    flow_available = bool((flow or {}).get("coverage", {}).get("available_dimensions", 0))
    flow_status = "UNAVAILABLE" if not flow_available else "CONTRADICTORY" if any("DIVERGENCE" in item or "SELL_PRESSURE" in item for item in relationships) else "SUPPORTIVE" if any("CONFIRMATION" in item or "BUY_SUPPORT" in item for item in relationships) else "AVAILABLE"
    return {
        "MARKET_CONTEXT": _driver("AVAILABLE_DESCRIPTIVE" if tactical.get("market_state") else "UNAVAILABLE", {"market_state": tactical.get("market_state")}),
        "MARKET_FLOW_CONTEXT": _driver(flow_status, flow or {"status": "FLOW_UNAVAILABLE"}, ["Flow/positioning is provider-scoped descriptive context; it is not causality, intent, or execution evidence."]),
        "MACRO_CONTEXT": _driver("AVAILABLE" if (macro_context or {}).get("status") == "AVAILABLE" else "UNAVAILABLE", macro_context or {"status": "UNAVAILABLE"}, ["Macro is independent descriptive context, not causal proof or probability."]),
        "TECHNICAL": _driver("AVAILABLE_DESCRIPTIVE" if technical_ready else "UNAVAILABLE", {"ticker_structure_state": tactical.get("ticker_structure_state"), "signals": tactical.get("signals")}, list((tactical.get("data_quality") or {}).get("warnings") or [])),
        "TACTICAL": _driver("AVAILABLE_DESCRIPTIVE" if entry_state else "UNAVAILABLE", {"entry_state": entry_state, "confirmation_trigger": tactical.get("confirmation_trigger"), "invalidation": tactical.get("invalidation"), "rule_id": tactical.get("rule_id")}),
        "PEER_RELATIVE": _driver("AVAILABLE_DESCRIPTIVE" if peer_technical.get("status") == "AVAILABLE" else "UNAVAILABLE", {"peer_membership": (peer or {}).get("peer_membership"), "technical_peer_context": peer_technical, "expectations_context": (peer or {}).get("expectations_context")}, list((peer or {}).get("data_gaps") or [])),
        "FUNDAMENTAL": _driver("AVAILABLE_DESCRIPTIVE" if fund_context.get("trajectory_status") in {"AVAILABLE", "OFFICIAL_METRIC_CONTEXT_ONLY"} else "UNAVAILABLE", {"trajectory": fund_context, "authority_tier": (fundamental or {}).get("authority_tier")}, list(fund_context.get("data_limitations") or [])),
        "VALUATION_CONTEXT": _driver("UNAVAILABLE", {"strict_current_valuation": valuation or {}, "peer_valuation": valuation_context}, ["Strict current valuation is blocked or non-discriminating; shadow proxy is not target-price authority."]),
        "CATALYST_OR_EVENT": _driver("AVAILABLE" if catalyst and catalyst.get("status") in {"OBSERVED_CATALYST", "OBSERVED_CATALYST_OR_EVENT", "PENDING_OR_HISTORICAL_EVENT_CONTEXT"} else "UNAVAILABLE", catalyst or {"status": "NO_QUALIFIED_CATALYST_EVIDENCE"}),
        "DATA_QUALITY": _driver("AVAILABLE_DESCRIPTIVE" if technical_ready else "UNAVAILABLE", tactical.get("data_quality") or {}, list((tactical.get("data_quality") or {}).get("warnings") or [])),
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
        "BEAR": common | {"case_id": _case_id(ticker, "BEAR", source_ids), "observed_support": counter, "required_confirmations": [invalidation] if invalidation else [], "counter_evidence": support, "invalidation": None, "invalidation_status": "BEAR_INVALIDATION_NOT_DECLARED_BY_SOURCE", "case_conditions": ["Existing tactical invalidation or deterioration condition is met."], "driver_states": {name: value["status"] for name, value in drivers.items()}},
        "BASE": common | {"case_id": _case_id(ticker, "BASE", source_ids), "current_state": state, "continuation_conditions": [f"Current tactical state remains {state} without a new confirmation or invalidation."], "transition_to_bull_conditions": [confirmation] if confirmation else [], "transition_to_bear_conditions": [invalidation] if invalidation else [], "evidence_for": support, "evidence_against": counter, "limitations": ["Reference/current-continuation case; not most probable."]},
        "BULL": common | {"case_id": _case_id(ticker, "BULL", source_ids), "observed_support": support, "required_confirmations": [confirmation] if confirmation else [], "counter_evidence": counter, "invalidation": invalidation, "case_conditions": ["Existing tactical confirmation trigger is met.", "Any available peer/fundamental driver remains non-contradictory."], "driver_states": {name: value["status"] for name, value in drivers.items()}},
    }


def _detail(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: record[key] for key in ("ticker", "scenario_disposition", "current_state", "bear_case", "base_case", "bull_case", "key_driver_conflicts", "confirmation_trigger", "invalidation", "peer_context", "fundamental_context", "valuation_context", "catalyst_context", "time_horizon", "data_quality", "authority_limitations")}


def build(*, descriptive: Mapping[str, Any], tactical: Mapping[str, Any], peer_relative: Mapping[str, Any], fundamental: Mapping[str, Any], valuation: Mapping[str, Any], triage: Mapping[str, Any], catalyst: Mapping[str, Any] | None = None, screening: Mapping[str, Any] | None = None, corporate_intelligence: Mapping[str, Any] | None = None, macro_context: Mapping[str, Any] | None = None, market_flow_positioning: Mapping[str, Any] | None = None) -> dict[str, Any]:
    d, t, p, f, v = descriptive["records"], tactical["records"], peer_relative["records"], fundamental["records"], valuation["records"]
    catalyst_by_ticker = {row["ticker"]: row for row in (catalyst or {}).get("records", []) if isinstance(row, Mapping)}
    corporate_by_ticker = {row["ticker"]: row for row in (corporate_intelligence or {}).get("records", {}).values() if isinstance(row, Mapping)}
    source_ids = {"descriptive": descriptive["artifact_identity"], "tactical": tactical["artifact_identity"], "peer_relative": peer_relative["artifact_identity"], "fundamental": fundamental["artifact_identity"], "valuation": valuation["artifact_identity"], "triage": triage["artifact_identity"], "catalyst": (catalyst or {}).get("artifact_identity"), "corporate_intelligence": (corporate_intelligence or {}).get("artifact_identity"), "screening": (screening or {}).get("artifact_identity"), "macro": (macro_context or {}).get("macro_artifact_identity"), "market_flow_positioning": (market_flow_positioning or {}).get("artifact_identity")}
    records: dict[str, Any] = {}
    for ticker in sorted(d):
        tactical_row, peer_row, fund_row, valuation_row = t.get(ticker) or {}, p.get(ticker), f.get(ticker), v.get(ticker)
        catalyst_context = _catalysts(catalyst_by_ticker.get(ticker), corporate_by_ticker.get(ticker)); flow_row = (market_flow_positioning or {}).get("records", {}).get(ticker); drivers = _drivers(tactical_row, peer_row, fund_row, valuation_row, catalyst_context, macro_context, flow_row); disposition = _disposition(tactical_row, drivers); cases = _cases(ticker, disposition, tactical_row, drivers, source_ids)
        conflicts = [name for name, value in drivers.items() if value["status"] == "CONTRADICTORY"]
        records[ticker] = {"ticker": ticker, "scenario_disposition": disposition, "probability_status": "UNKNOWN_UNCALIBRATED", "current_state": {"market_state": tactical_row.get("market_state"), "ticker_structure_state": tactical_row.get("ticker_structure_state"), "entry_state": tactical_row.get("entry_state")}, "observed_facts": {"descriptive_activity": (d[ticker].get("activity_and_session_state")), "technical_current_session": ((d[ticker].get("technical_features") or {}).get("is_current_session")), "tactical_state": tactical_row.get("entry_state")}, "conditional_assumptions": ["Future conditions are not observed facts.", "Base means continuation/reference, not most likely."], "scenario_drivers": drivers, "market_flow_context": flow_row or {"status": "FLOW_UNAVAILABLE"}, "bear_case": cases["BEAR"], "base_case": cases["BASE"], "bull_case": cases["BULL"], "key_driver_conflicts": conflicts, "confirmation_trigger": tactical_row.get("confirmation_trigger"), "invalidation": tactical_row.get("invalidation"), "peer_context": peer_row or {"status": "UNAVAILABLE"}, "fundamental_context": (fund_row or {}).get("fundamental_trajectory_context") or {"status": "UNAVAILABLE"}, "valuation_context": {"strict_status": (valuation_row or {}).get("status", "UNAVAILABLE"), "shadow_proxy": (valuation_row or {}).get("shadow_proxy_valuation"), "peer_status": ((peer_row or {}).get("valuation_peer_context") or {}).get("status")}, "catalyst_context": catalyst_context, "time_horizon": tactical_row.get("horizon"), "data_quality": tactical_row.get("data_quality") or {}, "authority_limitations": ["Current deterministic research only.", "No calibrated probabilities, targets, expected returns, ranking, recommendation, sizing, portfolio, execution, or outcomes."], "is_actionable": False}
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
        else:
            patterns["BULL_CASE_FUNDAMENTAL_UNCERTAINTY"] += 1
            if record["scenario_drivers"]["FUNDAMENTAL"]["status"] == "AVAILABLE_DESCRIPTIVE":
                patterns["BULL_CASE_FUNDAMENTAL_DESCRIPTIVE_CONTEXT_AVAILABLE"] += 1
        if record["current_state"]["entry_state"] in {"DISTRIBUTION_RISK", "BREAKDOWN_RISK", "DOWNTREND"}: patterns["BEAR_CASE_DISTRIBUTION_RISK"] += 1
        if record["current_state"]["entry_state"] in {"BASE_BUILDING", "SIDEWAYS_NEUTRAL"}: patterns["BASE_CASE_CONTINUED_CONSOLIDATION"] += 1
        if record["key_driver_conflicts"]: patterns["CONFLICTED_SCENARIO_EVIDENCE"] += 1
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "session": descriptive["session"], "source_artifact_identities": source_ids, "records": records, "case_definitions": {"BEAR": "Conditional deterioration/invalidation case.", "BASE": "Current-continuation reference; not most probable.", "BULL": "Conditional confirmation case."}, "coverage": {"universe_count": len(records), "scenario_disposition_counts": dict(sorted(counts.items())), "driver_coverage": {name: sum(record["scenario_drivers"][name]["status"] != "UNAVAILABLE" for record in records.values()) for name in DRIVER_TYPES}, "scenario_pattern_counts": dict(sorted(patterns.items()))}, "validation": {"watchlist": [_detail(records[x]) for x in WATCHLIST if x in records], "preopen_47": [_detail(records[x]) for x in PREOPEN_47 if x in records], "entry_relevant_90": [_detail(records[x]) for x in entry_90 if x in records], "representative_scenarios": representative}, "authority_boundary": {"research_only": True, "probabilities": "UNKNOWN_UNCALIBRATED", "targets_expected_returns_recommendations_rankings_sizing": "NOT_EMITTED", "valuation_case_discrimination": "NOT_EMITTED", "outcomes_or_calibration": "NOT_EMITTED"}, "data_limitations": ["Missing inputs narrow dependent cases only.", "Catalyst artifact is retained earlier-session evidence where present.", "Valuation peer context is unavailable under current authority constraints."], "is_actionable": False}
    artifact.update(content_identity(artifact)); return artifact


# Offline opt-in only. The Daily build above retains its original contract.
INTEGRATED_BINDING_CONTRACT = "current_evidence_bound_scenario_integrated_binding/v1"
ENTRY_CLASSES = frozenset({"FRESH_ENTRY_TRIGGER", "CONFIRMED_RETEST_ENTRY"})
UNUSABLE_CLASSES = frozenset({"MISSING_CURRENT_EVIDENCE", "UNQUALIFIED_TACTICAL_STRUCTURE",
                             "UNQUALIFIED_TACTICAL_AND_FUNDAMENTAL"})
ADVERSE_CLASSES = frozenset({"BEARISH_STRUCTURE_ADVERSE", "DISTRIBUTION_OR_BREAKDOWN_WITH_DETERIORATION",
                            "FAILED_BREAKOUT_WITH_DETERIORATION"})


class IntegratedScenarioBindingError(ValueError):
    """A source, policy or binding invariant failed before interpretation."""


def _require_binding(condition: bool, reason: str) -> None:
    if not condition:
        raise IntegratedScenarioBindingError(reason)


def binding_content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = {k: v for k, v in artifact.items() if k not in {"artifact_identity", "artifact_sha256"}}
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": INTEGRATED_BINDING_CONTRACT + ":" + digest}


def validate_integrated_source(*, session: str, integrated_decision: Mapping[str, Any], tickers) -> dict[str, Any]:
    """Verify the whole streamed IID root and every record, not caller lens assertions."""
    import integrated_investment_decision_product as owner
    _require_binding(isinstance(session, str) and bool(session), "SESSION_REQUIRED")
    _require_binding(isinstance(integrated_decision, Mapping), "INTEGRATED_ARTIFACT_MISSING")
    _require_binding(integrated_decision.get("contract_version") == owner.CONTRACT_VERSION, "INTEGRATED_CONTRACT_MISMATCH")
    _require_binding(integrated_decision.get("research_action_policy_version") == "v2", "INTEGRATED_POLICY_EPOCH_MISMATCH")
    _require_binding(integrated_decision.get("session") == session, "INTEGRATED_SESSION_MISMATCH")
    _require_binding(not isinstance(tickers, (str, bytes)), "REQUESTED_TICKERS_INVALID")
    try:
        requested = list(tickers)
    except TypeError as exc:
        raise IntegratedScenarioBindingError("REQUESTED_TICKERS_INVALID") from exc
    _require_binding(bool(requested) and all(isinstance(t, str) and t and t == t.strip().upper() for t in requested), "REQUESTED_TICKERS_INVALID")
    _require_binding(len(requested) == len(set(requested)), "DUPLICATE_TICKER")
    records = integrated_decision.get("records")
    _require_binding(isinstance(records, Mapping) and bool(records), "INTEGRATED_RECORDS_MISSING")
    try:
        identity = owner.content_identity(integrated_decision)
    except (TypeError, ValueError, KeyError) as exc:
        raise IntegratedScenarioBindingError("INTEGRATED_CONTENT_INVALID") from exc
    _require_binding(all(integrated_decision.get(k) == v for k, v in identity.items()), "INTEGRATED_CONTENT_IDENTITY_MISMATCH")
    for ticker, record in records.items():
        _require_binding(isinstance(record, Mapping) and record.get("ticker") == ticker, "INTEGRATED_TICKER_MISMATCH")
        _require_binding(record.get("as_of_session") == session, "INTEGRATED_RECORD_SESSION_MISMATCH")
        _require_binding(record.get("research_action_policy_version") == "v2", "INTEGRATED_RECORD_POLICY_EPOCH_MISMATCH")
        try:
            owner.validate_posture_policy(record)
        except ValueError as exc:
            raise IntegratedScenarioBindingError("INTEGRATED_CLASS_POSTURE_CONFLICT") from exc
        _require_binding(record.get("decision_identity") == owner.decision_identity(record), "INTEGRATED_DECISION_IDENTITY_MISMATCH")
        currency = record.get("evidence_currency")
        _require_binding(owner.is_valid_evidence_currency(currency), "INTEGRATED_EVIDENCE_CURRENCY_INVALID")
        if currency == "NO_CURRENT_EVIDENCE":
            _require_binding(record.get("posture_condition_class") == "MISSING_CURRENT_EVIDENCE", "INTEGRATED_CURRENCY_CLASS_CONFLICT")
        else:
            _require_binding(record.get("posture_condition_class") != "MISSING_CURRENT_EVIDENCE", "INTEGRATED_CURRENCY_CLASS_CONFLICT")
        if currency.startswith("LAST_TRADE_AS_OF:"):
            _require_binding(currency.split(":", 1)[1] < session, "INTEGRATED_DATED_CURRENCY_INVALID")
        if record.get("posture_condition_class") not in UNUSABLE_CLASSES:
            fitness = ((record.get("evidence_axes") or {}).get("TACTICAL_STRUCTURE") or {}).get("fitness")
            _require_binding(fitness == "AVAILABLE", "INTEGRATED_TACTICAL_ELIGIBILITY_CONFLICT")
    _require_binding(set(requested) <= set(records), "REQUESTED_TICKER_MISSING")
    return {t: records[t] for t in sorted(requested)}


def _qualified_condition(record: Mapping[str, Any], role: str, session: str) -> bool:
    import math
    from bounded_artifact_stream import record_mapping_digest
    raw = record.get(role) or {}
    condition = raw.get("condition") or {}
    level = raw.get(role + "_level")
    body = {k: v for k, v in condition.items() if k != "condition_identity"}
    tactical_axis = (record.get("evidence_axes") or {}).get("TACTICAL_STRUCTURE") or {}
    source_identity = (tactical_axis.get("lineage") or {}).get("source_artifact_identity")
    return (condition.get("status") == "MACHINE_EVALUABLE"
            and condition.get("condition_version") == "retained_strategy_boundary_condition/v1"
            and condition.get("role") == role and condition.get("operator") in {"<", ">"}
            and condition.get("source_metric") == role + "_level"
            and condition.get("required_state") == raw.get("trigger_type" if role == "trigger" else "invalidation_method")
            and condition.get("condition_identity") == "retained_strategy_boundary_condition:" + record_mapping_digest(body)
            and condition.get("source_method") == "market_structure_breakout_product_projection/v1"
            and bool(condition.get("source_strategy_identity"))
            and condition.get("source_strategy_identity") == source_identity
            and (condition.get("source_lineage") or {}).get("as_of_session") == session
            and (condition.get("source_lineage") or {}).get("source_artifact_identity") == condition.get("source_strategy_identity")
            and isinstance(level, (int, float)) and not isinstance(level, bool)
            and math.isfinite(level) and level > 0 and condition.get("reference_level") == level)


def _context_specs():
    from current_market_flow_positioning import content_identity as flow_identity
    from current_market_sector_leadership_context import content_identity as sector_identity
    from current_financial_momentum_context import content_identity as financial_identity
    return {"flow": ("current_market_flow_positioning/v1", flow_identity, "records"),
             "market_sector": ("current_market_sector_leadership_context/v1", sector_identity, "ticker_contexts"),
             "financial": ("current_financial_momentum_context/v1", financial_identity, "records")}


def _context_sources(context, session: str) -> dict[str, Any]:
    """Verify roots once, retain admitted artifacts once for consumer replay.

    Unavailable sources retain only session diagnostics, never unqualified facts.
    """
    specs = _context_specs()
    sources = {}
    for name, artifact in (context or {}).items():
        if name not in specs or not isinstance(artifact, Mapping):
            sources[name] = None
            continue
        contract, identity, field = specs[name]
        qualified = False
        try:
            qualified = (artifact.get("session") == session and artifact.get("contract_version") == contract
                         and isinstance(artifact.get(field), Mapping)
                         and all(artifact.get(k) == v for k, v in identity(artifact).items()))
        except (TypeError, ValueError, KeyError, AttributeError):
            pass
        sources[name] = copy.deepcopy(dict(artifact)) if qualified else {"session": artifact.get("session") if isinstance(artifact.get("session"), str) else None}
    return sources


def _optional_context(context, session: str, ticker: str) -> dict[str, Any]:
    """Read only normalized, root-verified sources. No flow direction classifier."""
    result = {}
    specs = _context_specs()
    for name, (contract, identity, field) in specs.items():
        artifact = (context or {}).get(name)
        reason = "CONTEXT_UNQUALIFIED" if name in (context or {}) else "CONTEXT_NOT_SUPPLIED"
        row = None
        if isinstance(artifact, Mapping):
            reason = "CONTEXT_SESSION_MISMATCH" if artifact.get("session") != session else "CONTEXT_UNQUALIFIED"
            try:
                if artifact.get("session") == session and artifact.get("contract_version") == contract:
                    row = (artifact.get(field) or {}).get(ticker)
                    if not isinstance(row, Mapping):
                        row = None
                    if name == "market_sector" and (row or {}).get("status") not in {"AVAILABLE", "PARTIAL"}:
                        row = None
                    if name == "flow":
                        dimensions = (row or {}).get("coverage", {}).get("available_dimensions", 0)
                        sections = ("traded_value", "foreign_flow", "foreign_room", "proprietary_flow", "active_order_context")
                        qualified_count = sum((row or {}).get(k, {}).get("status") == "AVAILABLE" for k in sections)
                        if ((row or {}).get("session") != session or not isinstance(dimensions, int)
                                or isinstance(dimensions, bool) or dimensions <= 0 or qualified_count != dimensions):
                            row = None
            except (TypeError, ValueError, KeyError, AttributeError):
                row = None
        result[name] = {"status": "AVAILABLE_DESCRIPTIVE" if row else "UNAVAILABLE", "reason_code": "QUALIFIED_SAME_SESSION_CONTEXT" if row else reason,
                        "source_identity": artifact.get("artifact_identity") if row else None,
                        "use": "NON_VOTING_CONTEXT_ONLY", "payload": copy.deepcopy(row) if row else None}
    for name in sorted(set(context or {}) - set(specs)):
        result[name] = {"status": "UNAVAILABLE", "reason_code": "UNSUPPORTED_CONTEXT_CONTRACT",
                        "source_identity": None, "use": "NON_VOTING_CONTEXT_ONLY", "payload": None}
    return result


def _bound_record(record: Mapping[str, Any], source: str, session: str, context) -> dict[str, Any]:
    klass = record["posture_condition_class"]
    usable = klass not in UNUSABLE_CLASSES and record["evidence_currency"] != "NO_CURRENT_EVIDENCE"
    trigger_qualified = usable and _qualified_condition(record, "trigger", session)
    invalidation_qualified = usable and _qualified_condition(record, "invalidation", session)
    # Retest is admitted by the released class; the corresponding fixed structural
    # condition must still qualify. Watchlist prose never substitutes for it.
    entry = (klass in ENTRY_CLASSES and trigger_qualified
             and (record["trigger"].get("condition") or {}).get("operator") == ">")
    if klass == "FRESH_ENTRY_TRIGGER":
        entry = entry and record["trigger"].get("trigger_state") == "TRIGGERED" and record["trigger"].get("trigger_type") in {"PIVOT_BREAKOUT_TRIGGER", "CONFIRMED_BOS_TRIGGER"}
    elif klass == "CONFIRMED_RETEST_ENTRY":
        entry = (entry and record["trigger"].get("trigger_type") == "RETEST_BROKEN_PIVOT"
                 and (((record.get("evidence_axes") or {}).get("TACTICAL_STRUCTURE") or {}).get("context") or {}).get("pivot_retest_confirmed") is True)
    adverse = usable and klass in ADVERSE_CLASSES
    common = {"probability_status": "UNKNOWN_UNCALIBRATED", "is_actionable": False}
    copied = {k: copy.deepcopy(record.get(k)) for k in ("research_action_posture", "posture_condition_class", "research_action_policy_version",
              "decision_identity", "tactical_phase", "fundamental_state", "evidence_currency", "trigger", "invalidation")}
    axes = record.get("evidence_axes") or {}
    price_basis = {role: copy.deepcopy((record.get(role) or {}).get("price_basis") or ((record.get(role) or {}).get("condition") or {}).get("price_basis")) for role in ("trigger", "invalidation")}
    limitations = ["REFERENCE_CASE_NOT_MOST_PROBABLE", "RESEARCH_ONLY_NOT_EXECUTION"]
    if (not all(isinstance(v, Mapping) and v.get("price_basis_verified") is True for v in price_basis.values())
            or price_basis["trigger"] != price_basis["invalidation"]):
        limitations.append("PRICE_BASIS_UNVERIFIED_OR_MIXED")
    if not all((record.get(role) or {}).get("horizon") for role in ("trigger", "invalidation")):
        limitations.append("SOURCE_HORIZON_NOT_SUPPLIED")
    gaps = copy.deepcopy(record.get("material_uncertainties") or [])
    if record.get("fundamental_state") == "INSUFFICIENT":
        gaps.append("FUNDAMENTAL_STATE_INSUFFICIENT")
    return {"ticker": record["ticker"], "session": session, "integrated_artifact_identity": source, **copied, **common,
            "trigger_qualified": trigger_qualified, "invalidation_qualified": invalidation_qualified,
            "time_horizon": {role: (record.get(role) or {}).get("horizon") for role in ("trigger", "invalidation")}, "price_basis": price_basis, "limitations": limitations,
            "evidence_axis_coherence": copy.deepcopy(record.get("evidence_axis_coherence")),
            "integrated_context": {k: copy.deepcopy(v) for k, v in axes.items() if k != "PORTFOLIO_FIT"},
            "optional_context": _optional_context(context, session, record["ticker"]),
            "base_case": {**common, "case_status": "OBSERVED_REFERENCE", "reason_code": klass, "fundamental_gaps": gaps,
                          "current_state": {k: copied[k] for k in ("tactical_phase", "research_action_posture", "posture_condition_class", "fundamental_state", "evidence_currency")}},
            "bull_case": {**common, "case_status": "CONDITIONAL" if entry else "NOT_ADMITTED", "reason_code": "QUALIFIED_INTEGRATED_ENTRY_TRIGGER" if entry else "NO_QUALIFIED_ENTRY_TRIGGER",
                          "trigger": copy.deepcopy(record["trigger"]) if entry else None},
            "bear_case": {**common, "case_status": "CONDITIONAL" if invalidation_qualified or adverse else "INSUFFICIENT_EVIDENCE",
                          "reason_code": klass if adverse else "QUALIFIED_INTEGRATED_INVALIDATION" if invalidation_qualified else "NO_QUALIFIED_INVALIDATION_OR_ADVERSE_EVIDENCE",
                          "source_condition_class": klass,
                          "observed_adverse": adverse, "invalidation": copy.deepcopy(record["invalidation"]) if invalidation_qualified else None}}


def bind_integrated_scenarios(*, session: str, integrated_decision: Mapping[str, Any], tickers, optional_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    _require_binding(optional_context is None or isinstance(optional_context, Mapping), "OPTIONAL_CONTEXT_INVALID")
    _require_binding(all(isinstance(name, str) for name in (optional_context or {})), "OPTIONAL_CONTEXT_INVALID")
    records = validate_integrated_source(session=session, integrated_decision=integrated_decision, tickers=tickers)
    context_sources = _context_sources(optional_context, session)
    artifact = {"contract_version": INTEGRATED_BINDING_CONTRACT, "session": session, "research_action_policy_version": "v2",
                "integrated_artifact_identity": integrated_decision["artifact_identity"],
                "source_context_artifacts": context_sources,
                "records": {t: _bound_record(r, integrated_decision["artifact_identity"], session, context_sources) for t, r in records.items()},
                "probability_status": "UNKNOWN_UNCALIBRATED", "is_actionable": False}
    artifact.update(binding_content_identity(artifact))
    return artifact


def validate_binding_context(binding: Mapping[str, Any], *, session: str) -> dict[str, Any]:
    _require_binding(isinstance(binding.get("source_context_artifacts"), Mapping), "SCENARIO_CONTEXT_SOURCES_MISSING")
    sources = _context_sources(binding["source_context_artifacts"], session)
    _require_binding(sources == binding["source_context_artifacts"], "SCENARIO_CONTEXT_SOURCE_CONFLICT")
    for ticker, bound in (binding.get("records") or {}).items():
        _require_binding(bound.get("optional_context") == _optional_context(sources, session, ticker), "SCENARIO_CONTEXT_RECORD_CONFLICT")
    return sources


def validate_integrated_binding(binding: Mapping[str, Any], *, session: str, integrated_decision: Mapping[str, Any], tickers) -> None:
    records = validate_integrated_source(session=session, integrated_decision=integrated_decision, tickers=tickers)
    _require_binding(isinstance(binding, Mapping) and binding.get("contract_version") == INTEGRATED_BINDING_CONTRACT, "SCENARIO_BINDING_CONTRACT_MISMATCH")
    _require_binding(binding.get("session") == session and binding.get("research_action_policy_version") == "v2", "SCENARIO_BINDING_SESSION_OR_POLICY_MISMATCH")
    _require_binding(binding.get("integrated_artifact_identity") == integrated_decision["artifact_identity"], "SCENARIO_INTEGRATED_IDENTITY_MISMATCH")
    _require_binding(all(binding.get(k) == v for k, v in binding_content_identity(binding).items()), "SCENARIO_BINDING_IDENTITY_MISMATCH")
    _require_binding(set(binding.get("records") or {}) == set(records), "SCENARIO_BINDING_TICKER_SET_MISMATCH")
    context_sources = validate_binding_context(binding, session=session)
    for ticker, source_record in records.items():
        bound = binding["records"][ticker]
        expected = _bound_record(source_record, integrated_decision["artifact_identity"], session, context_sources)
        _require_binding(bound == expected, "SCENARIO_BINDING_RECORD_CONFLICT")
