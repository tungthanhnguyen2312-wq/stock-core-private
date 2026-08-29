"""Pure, non-executable shadow security recommendation packets."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any, Mapping


CONTRACT_VERSION = "shadow_security_recommendation/v1"
LABELS = (
    "INITIATE_RESEARCH_CANDIDATE", "ACCUMULATE_RESEARCH_CANDIDATE", "WAIT_FOR_CONFIRMATION",
    "HIGH_RISK_SPECULATION_ONLY", "AVOID_NEW_ENTRY", "INSUFFICIENT_EVIDENCE",
)
POSTURE_MAP = {
    "INITIATE_CANDIDATE": "INITIATE_RESEARCH_CANDIDATE",
    "ACCUMULATE_CANDIDATE": "ACCUMULATE_RESEARCH_CANDIDATE",
    "WAIT_FOR_CONFIRMATION_CANDIDATE": "WAIT_FOR_CONFIRMATION",
    "HIGH_RISK_SPECULATION_CANDIDATE": "HIGH_RISK_SPECULATION_ONLY",
    "AVOID_CANDIDATE": "AVOID_NEW_ENTRY",
    "INSUFFICIENT_ACTION_EVIDENCE": "INSUFFICIENT_EVIDENCE",
}
READINESS_MAP = {
    "READY_SHADOW": "RECOMMENDATION_READY", "CONDITIONAL_SHADOW": "RECOMMENDATION_CONDITIONAL",
    "NOT_READY_SHADOW": "RECOMMENDATION_NOT_READY",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"shadow_security_recommendation:{digest}"}


def _records(artifact: Mapping[str, Any] | None, name: str, required: bool = True) -> Mapping[str, Any]:
    records = (artifact or {}).get("records")
    if not isinstance(records, Mapping):
        if required:
            raise ValueError(f"{name}_RECORDS_INVALID")
        return {}
    return records


def _valuation_context(record: Mapping[str, Any] | None, as_of: str) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        return {"status": "ABSENT", "availability": "UNAVAILABLE", "price_session": None, "payload": None}
    axis = (record.get("relative_value_axis") or {}).get("axis_status")
    session = record.get("price_session")
    availability = "AVAILABLE" if axis == "READY_RESEARCH_ONLY" else "UNAVAILABLE"
    status = "STALE_RESEARCH_CONTEXT" if availability == "AVAILABLE" and isinstance(session, str) and session < as_of else availability
    return {"status": status, "availability": availability, "price_session": session,
            "temporally_compatible": session == as_of, "payload": dict(record)}


def _catalyst_context(case: Mapping[str, Any]) -> dict[str, Any]:
    catalysts, events = case.get("catalysts") or [], case.get("retained_event_context") or []
    state = "QUALIFIED_CATALYST" if catalysts else "RETAINED_EVENT_CONTEXT_ONLY" if events else "NO_QUALIFIED_CATALYST"
    return {"status": state, "qualified_catalysts": list(catalysts), "retained_event_context": list(events),
            "catalyst_is_optional": True}


def _monitoring(action: Mapping[str, Any], fundamental: Mapping[str, Any], catalyst: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, boundary, cadence in (
        ("MARKET_CONFIRMATION", action.get("entry_or_confirmation_boundary") or {}, "NEXT_COMPLETED_MARKET_SESSION"),
        ("TECHNICAL_INVALIDATION", action.get("technical_risk_boundary") or {}, "NEXT_COMPLETED_MARKET_SESSION"),
        ("FUNDAMENTAL_INVALIDATION", fundamental.get("fundamental_boundary") or {}, "NEXT_COMPATIBLE_FINANCIAL_OBSERVATION"),
        ("POSTURE_REVERSAL", action.get("posture_reversal_boundary") or {}, "NEXT_COMPLETED_MARKET_SESSION"),
    ):
        if boundary.get("status") != "UNAVAILABLE":
            rows.append({"monitor_category": name, "boundary_status": boundary.get("status"), "cadence_class": cadence,
                         "recompute_requirement": f"{name}_CHANGED"})
    if catalyst.get("status") != "NO_QUALIFIED_CATALYST":
        rows.append({"monitor_category": "EVENT_CONTEXT", "boundary_status": catalyst.get("status"), "cadence_class": "EVENT_DRIVEN",
                     "recompute_requirement": "RECOMMENDATION_REEVALUATION_REQUIRED"})
    return rows


def _packet(*, ticker: str, shadow: Mapping[str, Any], case: Mapping[str, Any], action: Mapping[str, Any],
            fundamental: Mapping[str, Any], risk: Mapping[str, Any] | None, valuation: Mapping[str, Any] | None,
            lineage: Mapping[str, Any]) -> dict[str, Any]:
    shadow_readiness = shadow.get("action_readiness_gate")
    readiness = READINESS_MAP.get(shadow_readiness)
    if readiness is None:
        raise ValueError("SHADOW_READINESS_UNMAPPED")
    label = "INSUFFICIENT_EVIDENCE" if readiness == "RECOMMENDATION_NOT_READY" else POSTURE_MAP.get(shadow.get("shadow_posture"))
    if label is None:
        raise ValueError("SHADOW_POSTURE_UNMAPPED")
    as_of = case.get("as_of_session")
    if not isinstance(as_of, str):
        raise ValueError("CASE_AS_OF_SESSION_MISSING")
    catalyst = _catalyst_context(case)
    valuation_context = _valuation_context(valuation, as_of)
    technical = dict(action.get("technical_risk_boundary") or {})
    fund = dict(fundamental.get("fundamental_boundary") or {})
    technical_trigger = technical.get("current_trigger_state", "UNKNOWN")
    fundamental_trigger = fund.get("current_trigger_state", "UNKNOWN")
    conflict = label in {"INITIATE_RESEARCH_CANDIDATE", "ACCUMULATE_RESEARCH_CANDIDATE"} and (
        technical_trigger == "TRIGGERED" or fundamental_trigger == "TRIGGERED"
    )
    if conflict:
        label, readiness = "INSUFFICIENT_EVIDENCE", "RECOMMENDATION_NOT_READY"
    reasons = list(shadow.get("shadow_posture_reason_codes") or []) + list(shadow.get("readiness_reason_codes") or [])
    record = {
        "ticker": ticker,
        "security_identity": {"ticker": ticker, "entity_class": case.get("entity_class"), "sector": case.get("sector")},
        "recommendation": {"recommendation_label": label, "recommendation_readiness": readiness,
                               "shadow_posture": shadow.get("shadow_posture"), "shadow_readiness": shadow_readiness,
                               "as_of_session": as_of, "recommendation_reason_codes": sorted(set(reasons)),
                               "research_action_state": "INSUFFICIENT" if readiness == "RECOMMENDATION_NOT_READY" else "MONITOR_ONLY" if label in {"WAIT_FOR_CONFIRMATION", "AVOID_NEW_ENTRY"} else "CURRENT_RESEARCH_STANCE"},
        "thesis_context": {"research_case_eligibility": case.get("terminal_case_disposition"), "thesis_archetype": case.get("thesis_archetype"),
                           "thesis_evidence": list(case.get("thesis_evidence") or []), "market_setup": dict(case.get("market_setup_context") or {}),
                           "material_warnings": list(case.get("warnings") or [])},
        "market_confirmation": dict(action.get("entry_or_confirmation_boundary") or {}),
        "technical_invalidation": {**technical, "current_trigger_state": technical_trigger},
        "fundamental_invalidation": {**fund, "current_trigger_state": fundamental_trigger},
        "catalyst_context": catalyst, "valuation_context": valuation_context,
        "risk_context": {"status": "AVAILABLE" if isinstance(risk, Mapping) else "ABSENT", "risk_artifact_identity": lineage.get("risk"),
                         "security_volatility_context": None if not isinstance(risk, Mapping) else risk.get("volatility_context"),
                         "sector": None if not isinstance(risk, Mapping) else risk.get("sector"),
                         "joint_risk_context_available": isinstance(risk, Mapping),
                         "risk_context_does_not_change_recommendation_label_v1": True},
        "monitoring_context": _monitoring(action, fundamental, catalyst),
        "temporal_context": {"as_of_session": as_of, "current_research_temporal_fitness": "CURRENT_SESSION_RESEARCH",
                             "close_price_execution_eligibility": "NOT_ESTABLISHED", "historical_pit_authority": "BLOCKED",
                             "historical_backtest_authority": "BLOCKED", "raw_as_traded": "NOT_PROMOTED",
                             "a1_bitemporal_identity": lineage.get("a1"), "a2_retention_identity": lineage.get("a2")},
        "authority_boundaries": {"shadow_research_recommendation_only": True, "personalized_advice_authority": False,
                                  "trade_execution_authority": False, "portfolio_allocation_authority": False,
                                  "position_sizing_authority": False, "liquidity_sizing_authority": False,
                                  "target_price_authority": False, "probability_authority": False,
                                  "historical_pit_authority": False, "historical_backtest_authority": False,
                                  "raw_as_traded_authority": False},
        "input_lineage": dict(lineage), "warnings": sorted(set((case.get("warnings") or []) + (action.get("warnings") or []) + (fundamental.get("warnings") or []))),
        "integrity_status": "RECOMMENDATION_POSTURE_TRIGGER_CONFLICT" if conflict else "COHERENT",
    }
    return record


def build_artifact(*, research_cases: Mapping[str, Any], shadow_readiness: Mapping[str, Any], action_instrumentation: Mapping[str, Any],
                   fundamental_invalidation: Mapping[str, Any], risk_research: Mapping[str, Any] | None = None,
                   valuation_research: Mapping[str, Any] | None = None, a1_temporal: Mapping[str, Any] | None = None,
                   a2_temporal: Mapping[str, Any] | None = None) -> dict[str, Any]:
    cases, shadows = _records(research_cases, "RESEARCH_CASE"), _records(shadow_readiness, "SHADOW")
    actions, fundamentals = _records(action_instrumentation, "ACTION"), _records(fundamental_invalidation, "FUNDAMENTAL")
    risk = ((risk_research or {}).get("ticker_risk_context") or {})
    if risk_research is not None and not isinstance(risk, Mapping):
        raise ValueError("RISK_RECORDS_INVALID")
    valuation = _records(valuation_research, "VALUATION", required=False)
    if set(cases) != set(shadows) or set(cases) != set(actions) or set(cases) != set(fundamentals):
        raise ValueError("MANDATORY_INPUT_DENOMINATOR_MISMATCH")
    lineage = {"research_cases": research_cases.get("artifact_identity"), "shadow_readiness": shadow_readiness.get("artifact_identity"),
               "action_instrumentation": action_instrumentation.get("artifact_identity"), "fundamental_invalidation": fundamental_invalidation.get("artifact_identity"),
               "risk": None if risk_research is None else risk_research.get("artifact_identity"), "valuation": None if valuation_research is None else valuation_research.get("artifact_identity") or valuation_research.get("artifact_sha256"),
               "a1": None if a1_temporal is None else a1_temporal.get("artifact_identity"), "a2": None if a2_temporal is None else a2_temporal.get("artifact_identity")}
    records = {ticker: _packet(ticker=ticker, shadow=shadows[ticker], case=cases[ticker], action=actions[ticker], fundamental=fundamentals[ticker],
                               risk=risk.get(ticker), valuation=valuation.get(ticker), lineage=lineage) for ticker in sorted(cases)}
    labels = Counter(record["recommendation"]["recommendation_label"] for record in records.values())
    readiness = Counter(record["recommendation"]["recommendation_readiness"] for record in records.values())
    technical = Counter(record["technical_invalidation"].get("status") for record in records.values())
    technical_trigger = Counter(record["technical_invalidation"].get("current_trigger_state") for record in records.values())
    fundamental = Counter(record["fundamental_invalidation"].get("status") for record in records.values())
    fundamental_trigger = Counter(record["fundamental_invalidation"].get("current_trigger_state") for record in records.values())
    for label in LABELS: labels.setdefault(label, 0)
    for state in READINESS_MAP.values(): readiness.setdefault(state, 0)
    if sum(labels.values()) != len(records) or sum(readiness.values()) != len(records): raise ValueError("RECOMMENDATION_RECONCILIATION_FAILED")
    ready_records = [record for record in records.values() if record["recommendation"]["recommendation_readiness"] == "RECOMMENDATION_READY"]
    conditional_accumulates = [record for record in records.values() if record["recommendation"]["recommendation_label"] == "ACCUMULATE_RESEARCH_CANDIDATE" and record["recommendation"]["recommendation_readiness"] == "RECOMMENDATION_CONDITIONAL"]
    wait_records = [record for record in records.values() if record["recommendation"]["recommendation_label"] == "WAIT_FOR_CONFIRMATION"]
    catalyst_states = Counter(record["catalyst_context"]["status"] for record in records.values())
    valuation_states = Counter(record["valuation_context"]["status"] for record in records.values())
    risk_lookbacks = {f"L{lookback}": sum(
        (record["risk_context"].get("security_volatility_context") or {}).get(f"L{lookback}", {}).get("status") == "VOLATILITY_READY"
        for record in ready_records
    ) for lookback in (20, 60, 120, 250)}
    representatives = {}
    for name, predicate in (
        ("ready_initiate", lambda r: r["recommendation"]["recommendation_label"] == "INITIATE_RESEARCH_CANDIDATE" and r["recommendation"]["recommendation_readiness"] == "RECOMMENDATION_READY"),
        ("ready_accumulate", lambda r: r["recommendation"]["recommendation_label"] == "ACCUMULATE_RESEARCH_CANDIDATE" and r["recommendation"]["recommendation_readiness"] == "RECOMMENDATION_READY"),
        ("conditional_accumulate", lambda r: r["recommendation"]["recommendation_label"] == "ACCUMULATE_RESEARCH_CANDIDATE" and r["recommendation"]["recommendation_readiness"] == "RECOMMENDATION_CONDITIONAL"),
        ("wait", lambda r: r["recommendation"]["recommendation_label"] == "WAIT_FOR_CONFIRMATION"),
        ("high_risk", lambda r: r["recommendation"]["recommendation_label"] == "HIGH_RISK_SPECULATION_ONLY"),
        ("avoid", lambda r: r["recommendation"]["recommendation_label"] == "AVOID_NEW_ENTRY"),
        ("insufficient", lambda r: r["recommendation"]["recommendation_label"] == "INSUFFICIENT_EVIDENCE"),
    ):
        row = next((records[ticker] for ticker in sorted(records) if predicate(records[ticker])), None)
        if row is not None:
            representatives[name] = {"ticker": row["ticker"], "label": row["recommendation"]["recommendation_label"],
                                     "readiness": row["recommendation"]["recommendation_readiness"],
                                     "technical_boundary": row["technical_invalidation"].get("status"),
                                     "fundamental_boundary": row["fundamental_invalidation"].get("status"),
                                     "risk_context": row["risk_context"]["status"]}
    artifact: dict[str, Any] = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION,
        "metadata": {"as_of_session": next(iter(records.values()))["recommendation"]["as_of_session"], "recommendation_vocabulary": list(LABELS),
                     "risk_context_is_optional": True, "risk_context_does_not_change_recommendation_label_v1": True},
        "denominator": len(records), "residual": 0, "input_lineage": lineage, "records": records,
        "validation": {"recommendation_counts": dict(sorted(labels.items())), "readiness_counts": dict(sorted(readiness.items())),
                       "technical_boundary_status": dict(sorted(technical.items())), "technical_trigger_state": dict(sorted(technical_trigger.items())),
                       "fundamental_boundary_status": dict(sorted(fundamental.items())), "fundamental_trigger_state": dict(sorted(fundamental_trigger.items())),
                       "posture_trigger_conflicts": sum(record["integrity_status"] != "COHERENT" for record in records.values()),
                       "risk_context_available": sum(record["risk_context"]["status"] == "AVAILABLE" for record in records.values()),
                       "risk_ready_cohort_volatility": risk_lookbacks, "valuation_available": sum(record["valuation_context"]["availability"] == "AVAILABLE" for record in records.values()),
                       "valuation_status_counts": dict(sorted(valuation_states.items())), "catalyst_status_counts": dict(sorted(catalyst_states.items())),
                       "conditional_accumulate_count": len(conditional_accumulates), "conditional_accumulate_blockers": dict(sorted(Counter(code for row in conditional_accumulates for code in row["recommendation"]["recommendation_reason_codes"]).items())),
                       "wait_blocker_distribution": dict(sorted(Counter(code for row in wait_records for code in row["recommendation"]["recommendation_reason_codes"]).items())),
                       "monitoring_available_count": sum(bool(record["monitoring_context"]) for record in records.values()), "representative_packets": representatives,
                       "SELL_FIELD_COUNT": 0, "EXIT_FIELD_COUNT": 0, "LIQUIDATE_FIELD_COUNT": 0, "POSITION_SIZE_FIELD_COUNT": 0,
                       "RISK_BUDGET_FIELD_COUNT": 0, "TARGET_PRICE_FIELD_COUNT": 0, "PROBABILITY_FIELD_COUNT": 0, "BUY_SELL_HOLD_LABEL_COUNT": 0},
        "authority_boundaries": {"shadow_research_recommendation_only": True, "no_buy_sell_hold_vocabulary": True,
                                  "no_portfolio_weights_or_sizing": True, "same_close_execution": "NOT_ESTABLISHED",
                                  "raw_as_traded": "NOT_PROMOTED", "historical_pit": "BLOCKED", "historical_backtest": "BLOCKED"}}
    return {**artifact, **content_identity(artifact)}
