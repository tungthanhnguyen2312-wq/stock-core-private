"""Deterministic CURRENT RESEARCH scenario framework (CONSERVATIVE / BASE / SPECULATIVE).

This is an additive sibling of the existing Bear/Base/Bull evidence-bound overlay.  The
project scenario axes here are research/decision-condition axes, not price-direction
labels and not strategy lanes.  Status is derived by explicit rules over already-retained
current research contracts.  No probability, target, expected return, action, or size is
emitted, and no upstream decision surface is modified.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from typing import Any, Mapping

import current_official_market_universe as official_universe_module
import current_opportunity_prioritization as opportunity_module
import current_research_risk_register as risk_register_module
import watchlist_tactical_entry_classifier as tactical_module
from current_corporate_event_context import content_identity as event_content_identity
from current_financial_momentum_context import content_identity as financial_content_identity
from current_market_sector_leadership_context import content_identity as leadership_content_identity
from market_wide_current_valuation_input_scaleout import content_identity as valuation_content_identity
from market_wide_historical_research_context import content_identity as historical_content_identity


CONTRACT_VERSION = "current_research_scenario_context/v1"
ARTIFACT_TYPE = "CURRENT_RESEARCH_SCENARIO_CONTEXT"
MILESTONE = "CURRENT_RESEARCH_SCENARIO_FRAMEWORK_V1"

SCENARIO_AXES = ("CONSERVATIVE", "BASE", "SPECULATIVE")
SCENARIO_STATUSES = (
    "SUPPORTED", "CONDITIONALLY_SUPPORTED", "NOT_SUPPORTED", "DATA_LIMITED", "UNQUALIFIED",
)
STRATEGY_LANES = (
    "TREND_MOMENTUM", "BREAKOUT", "EARLY_REVERSAL", "BASE_ACCUMULATION",
    "FUNDAMENTAL_IMPROVEMENT", "EVENT_DRIVEN", "VALUE",
)
ENTRY_ACTIONS = ("EARLY_ENTRY", "BUY_ON_CONFIRMATION", "ACCUMULATE_IN_BASE", "WAIT", "AVOID")

CONFIRMED_CONSTRUCTIVE_STATES = frozenset({"UPTREND_CONFIRMED"})
UNCONFIRMED_EARLY_STATES = frozenset({
    "EARLY_REVERSAL_CANDIDATE", "SELLING_PRESSURE_EASING", "BREAKOUT_READY",
    "BASE_BUILDING", "DISTRIBUTION_RISK",
})
FINANCIAL_SUPPORT_STATES = frozenset({"BROAD_IMPROVEMENT", "EARNINGS_IMPROVING"})
FINANCIAL_OPPOSE_STATES = frozenset({"DETERIORATING", "LOSS_MAKING_OR_STRESSED"})
FINANCIAL_LIMITED_STATES = frozenset({"INSUFFICIENT_COMPARABLE_DATA", "NOT_APPLICABLE"})
WEAK_SECTOR_STATES = frozenset({"WEAKENING", "LAGGING"})
WEAK_RELATIVE_BUCKETS = frozenset({"LOWER_QUARTILE"})
HISTORICAL_EARLY_STATES = frozenset({"EARLY_REVERSAL"})
MATERIAL_RISK_BLOCKS_CONSERVATIVE_SUPPORTED = "MATERIAL_RISK_BLOCKS_CONSERVATIVE_SUPPORTED"

FORBIDDEN_USES = (
    "probability", "expected_return", "target_price", "upside_pct", "downside_pct",
    "payoff_ratio", "intrinsic_value", "recommendation", "position_size", "sizing",
    "strategy_eligibility", "research_priority", "entry_action", "daily_decision_queue",
    "VALUE", "RAW_AS_TRADED", "PIT", "backtest",
)
FORBIDDEN_PAYLOAD_TOKENS = (
    "target_price", "expected_return", "upside_pct", "downside_pct", "payoff_ratio",
    "win_rate", "most_likely", "60%", "20% Conservative", "80_PERCENT_CONFIDENCE",
    "VERY_LIKELY", "EXPECTED_WINNER", "position_size", "intrinsic_value",
)

PREFERRED_REPRESENTATIVES = {
    "conservative_supported": "AAM",
    "base_supported": "AAM",
    "speculative_supported": "HPG",
    "base_supported_while_wait": "ACE",
    "speculative_with_material_risks": "ABB",
    "strong_technical_weak_sector": "GIC",
    "improving_financials_weak_price_momentum": "HPG",
    "planned_event_not_executed": "VCB",
    "valuation_blocked_still_analyzable": "AAA",
    "data_limited": "ANI",
}

OFFICIAL_CURRENT_STATUSES = frozenset({
    official_universe_module.OFFICIAL_CURRENT_EXCHANGE_SECURITY,
    official_universe_module.OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE,
})


class CurrentResearchScenarioContextError(ValueError):
    """A source context was not the exact retained contract required by this framework."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact))
    payload.pop("artifact_sha256", None)
    payload.pop("artifact_identity", None)
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"current_research_scenario_context:{digest}"}


def _verify_identity(artifact: Mapping[str, Any], *, contract: str, identity, label: str) -> None:
    if artifact.get("contract_version") != contract:
        raise CurrentResearchScenarioContextError(f"{label}_CONTRACT_UNSUPPORTED")
    if artifact.get("artifact_sha256") != identity(artifact).get("artifact_sha256"):
        raise CurrentResearchScenarioContextError(f"{label}_IDENTITY_MISMATCH")


def _official_tickers(artifact: Mapping[str, Any]) -> list[str]:
    try:
        official_universe_module._verify(artifact, "CURRENT_OFFICIAL_MARKET_UNIVERSE")
    except Exception as exc:
        raise CurrentResearchScenarioContextError("OFFICIAL_UNIVERSE_IDENTITY_MISMATCH") from exc
    records = artifact.get("records")
    if not isinstance(records, Mapping):
        raise CurrentResearchScenarioContextError("OFFICIAL_UNIVERSE_RECORDS_INVALID")
    tickers = sorted(
        ticker for ticker, row in records.items()
        if isinstance(row, Mapping) and row.get("stocklookup_candidate") is True
        and row.get("current_universe_status") in OFFICIAL_CURRENT_STATUSES
    )
    if not tickers or artifact.get("reconciliation", {}).get("official_total_match") != len(tickers):
        raise CurrentResearchScenarioContextError("OFFICIAL_UNIVERSE_DENOMINATOR_MISMATCH")
    return tickers


def _condition(*, condition_id: str, domain: str, polarity: str, code: str,
               facts: Mapping[str, Any], authority_tier: str, source: str) -> dict[str, Any]:
    return {
        "condition_id": condition_id, "domain": domain, "polarity": polarity, "code": code,
        "facts": copy.deepcopy(dict(facts)), "authority_tier": authority_tier, "source_context": source,
    }


def _gate(*, status: str, reason: str, text: Any = None) -> dict[str, Any]:
    return {"status": status, "reason": reason, "text": text, "invented": False}


def _classified(tactical: Mapping[str, Any]) -> bool:
    return bool(tactical.get("entry_state")) and (tactical.get("data_quality") or {}).get("technical_eligible") is True


def _confirmation_gates(tactical: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if _classified(tactical) and tactical.get("confirmation_trigger"):
        confirmation = [_gate(status="AVAILABLE", reason="REUSED_EXISTING_TACTICAL_CONFIRMATION",
                              text=tactical.get("confirmation_trigger"))]
    else:
        confirmation = [_gate(status="UNAVAILABLE", reason="QUALIFIED_CONFIRMATION_CONDITION_UNAVAILABLE")]
    if _classified(tactical) and tactical.get("invalidation"):
        invalidation = [_gate(status="AVAILABLE", reason="REUSED_EXISTING_TACTICAL_INVALIDATION",
                              text=tactical.get("invalidation"))]
    else:
        invalidation = [_gate(status="UNAVAILABLE", reason="QUALIFIED_INVALIDATION_CONDITION_UNAVAILABLE")]
    return confirmation, invalidation


def _valuation_status_counts(row: Mapping[str, Any]) -> dict[str, int]:
    metrics = row.get("metrics") or {}
    return dict(sorted(Counter(
        metric.get("status") for metric in metrics.values() if isinstance(metric, Mapping)
    ).items()))


def collect_evidence(*, ticker: str, tactical: Mapping[str, Any], opportunity: Mapping[str, Any],
                     historical: Mapping[str, Any], leadership: Mapping[str, Any],
                     market: Mapping[str, Any], financial: Mapping[str, Any],
                     event: Mapping[str, Any], valuation: Mapping[str, Any],
                     risk_row: Mapping[str, Any], source_ids: Mapping[str, Any]) -> dict[str, Any]:
    supporting, opposing, limitations, unresolved = [], [], [], []
    classified = _classified(tactical)
    entry_state = tactical.get("entry_state")
    confirmation, invalidation = _confirmation_gates(tactical)
    material_risks = copy.deepcopy(list(risk_row.get("material_risks") or []))
    limitations.extend(copy.deepcopy(list(risk_row.get("data_authority_limitations") or [])))
    unresolved.extend(copy.deepcopy(list(risk_row.get("unresolved_conflicts") or [])))

    if classified:
        supporting.append(_condition(
            condition_id="TECHNICAL_CURRENT_STATE", domain="TECHNICAL", polarity="SUPPORT",
            code=f"ENTRY_STATE_{entry_state}", facts={"entry_state": entry_state, "entry_action": tactical.get("entry_action")},
            authority_tier="CURRENT_SESSION_DESCRIPTIVE", source=source_ids["tactical"],
        ))
        if entry_state in CONFIRMED_CONSTRUCTIVE_STATES:
            supporting.append(_condition(
                condition_id="TECHNICAL_CONFIRMED_TREND", domain="TECHNICAL", polarity="SUPPORT",
                code="CONFIRMED_CONSTRUCTIVE_STATE", facts={"entry_state": entry_state},
                authority_tier="CURRENT_SESSION_DESCRIPTIVE", source=source_ids["tactical"],
            ))
        if entry_state in UNCONFIRMED_EARLY_STATES:
            supporting.append(_condition(
                condition_id="TECHNICAL_UNCONFIRMED_EARLY_STATE", domain="TECHNICAL", polarity="SUPPORT",
                code="EXPLICIT_EARLY_OR_UNCONFIRMED_STATE", facts={"entry_state": entry_state},
                authority_tier="CURRENT_SESSION_DESCRIPTIVE", source=source_ids["tactical"],
            ))
    else:
        limitations.append(_condition(
            condition_id="TECHNICAL_UNCLASSIFIED", domain="DATA_AUTHORITY", polarity="LIMITATION",
            code="CURRENT_TECHNICAL_CLASSIFICATION_UNAVAILABLE",
            facts={"technical_eligible": (tactical.get("data_quality") or {}).get("technical_eligible"),
                   "entry_state": entry_state},
            authority_tier="CURRENT_SESSION_DESCRIPTIVE", source=source_ids["tactical"],
        ))

    liquidity = (tactical.get("data_quality") or {}).get("liquidity_status")
    if liquidity != "ELIGIBLE":
        limitations.append(_condition(
            condition_id="LIQUIDITY_NOT_SIZING_AUTHORITY", domain="DATA_AUTHORITY", polarity="LIMITATION",
            code="ADTV_OR_LIQUIDITY_DOES_NOT_BLOCK_SCENARIO_STATUS",
            facts={"liquidity_status": liquidity, "position_sizing_status": tactical.get("position_sizing_status")},
            authority_tier="DESCRIPTIVE_RESEARCH_ONLY", source=source_ids["tactical"],
        ))

    hist_ok = historical.get("is_current_session") is True and historical.get("context_status") in {"AVAILABLE", "PARTIAL"}
    structural = (historical.get("structural_state") or {}).get("value")
    if hist_ok:
        facts = {
            "context_status": historical.get("context_status"),
            "structural_state": structural,
            "volatility_regime": (historical.get("volatility_regime") or {}).get("regime"),
            "momentum_sign": (historical.get("momentum") or {}).get("sign"),
            "rarity_bucket": (historical.get("technical_state_frequency") or {}).get("rarity_bucket"),
            "probability_claim": (historical.get("technical_state_frequency") or {}).get("probability_claim") or "NONE",
        }
        if structural == "DETERIORATION":
            opposing.append(_condition(
                condition_id="HISTORICAL_STRUCTURAL_DETERIORATION", domain="HISTORICAL", polarity="OPPOSE",
                code="HISTORICAL_STRUCTURAL_STATE_DETERIORATION", facts=facts,
                authority_tier="RETROSPECTIVE_DESCRIPTIVE", source=source_ids["historical"],
            ))
        else:
            supporting.append(_condition(
                condition_id="HISTORICAL_WITHIN_TICKER_CONTEXT", domain="HISTORICAL", polarity="SUPPORT",
                code="HISTORICAL_DESCRIPTIVE_CONTEXT_AVAILABLE", facts=facts,
                authority_tier="RETROSPECTIVE_DESCRIPTIVE", source=source_ids["historical"],
            ))
        if structural in HISTORICAL_EARLY_STATES:
            supporting.append(_condition(
                condition_id="HISTORICAL_EARLY_REVERSAL_STATE", domain="HISTORICAL", polarity="SUPPORT",
                code="HISTORICAL_EARLY_REVERSAL_NOT_BACKTEST_PROBABILITY", facts={"structural_state": structural},
                authority_tier="RETROSPECTIVE_DESCRIPTIVE", source=source_ids["historical"],
            ))
    elif historical:
        limitations.append(_condition(
            condition_id="HISTORICAL_CONTEXT_LIMITED", domain="DATA_AUTHORITY", polarity="LIMITATION",
            code="HISTORICAL_CURRENT_SESSION_CONTEXT_UNAVAILABLE",
            facts={"context_status": historical.get("context_status"), "is_current_session": historical.get("is_current_session")},
            authority_tier="RETROSPECTIVE_DESCRIPTIVE", source=source_ids["historical"],
        ))

    market_state = market.get("current_breadth_state")
    if market_state and market_state != "BROAD_PARTICIPATION":
        target = limitations if market_state == "DATA_LIMITED" else opposing
        target.append(_condition(
            condition_id="MARKET_BREADTH_CONTEXT", domain="MARKET_BREADTH",
            polarity="LIMITATION" if market_state == "DATA_LIMITED" else "OPPOSE",
            code=f"MARKET_BREADTH_{market_state}", facts={"market_breadth_state": market_state},
            authority_tier="CURRENT_SESSION_DESCRIPTIVE", source=source_ids["leadership"],
        ))
    sector = leadership.get("sector_leadership_context") or {}
    sector_state = sector.get("leadership_state")
    if sector.get("status") == "AVAILABLE" and sector_state == "LEADING":
        supporting.append(_condition(
            condition_id="SECTOR_LEADING", domain="SECTOR_RELATIVE", polarity="SUPPORT",
            code="SECTOR_LEADING", facts={"leadership_state": sector_state, "group_key": sector.get("group_key")},
            authority_tier="CURRENT_SESSION_DESCRIPTIVE", source=source_ids["leadership"],
        ))
    elif sector_state in WEAK_SECTOR_STATES or sector_state == "MIXED":
        opposing.append(_condition(
            condition_id="SECTOR_NOT_LEADING", domain="SECTOR_RELATIVE", polarity="OPPOSE",
            code=f"SECTOR_{sector_state}", facts={"leadership_state": sector_state, "breadth_support_state": leadership.get("breadth_support_state")},
            authority_tier="CURRENT_SESSION_DESCRIPTIVE", source=source_ids["leadership"],
        ))
    elif sector.get("status") != "AVAILABLE":
        limitations.append(_condition(
            condition_id="SECTOR_CONTEXT_LIMITED", domain="DATA_AUTHORITY", polarity="LIMITATION",
            code=sector.get("reason") or "SECTOR_CONTEXT_UNAVAILABLE",
            facts={"sector_status": sector.get("status"), "reason": sector.get("reason")},
            authority_tier="CURRENT_SESSION_DESCRIPTIVE", source=source_ids["leadership"],
        ))
    relative = leadership.get("sector_relative_momentum") or {}
    if relative.get("momentum_bucket") in WEAK_RELATIVE_BUCKETS:
        opposing.append(_condition(
            condition_id="SECTOR_RELATIVE_WEAK", domain="SECTOR_RELATIVE", polarity="OPPOSE",
            code="SECTOR_RELATIVE_MOMENTUM_LOWER_QUARTILE",
            facts={"momentum_bucket": relative.get("momentum_bucket")},
            authority_tier="CURRENT_SESSION_DESCRIPTIVE", source=source_ids["leadership"],
        ))

    fin_state = financial.get("financial_momentum_state")
    fin_tier = financial.get("evidence_tier")
    contrast = (financial.get("price_momentum_context") or {}).get("contrast")
    fin_facts = {
        "financial_momentum_state": fin_state, "evidence_tier": fin_tier,
        "coverage_status": financial.get("coverage_status"), "price_contrast": contrast,
        "provider_research_is_not_official": fin_tier == "PROVIDER_RESEARCH",
    }
    if fin_state in FINANCIAL_SUPPORT_STATES:
        supporting.append(_condition(
            condition_id="FINANCIAL_IMPROVEMENT", domain="FINANCIAL", polarity="SUPPORT",
            code=str(financial.get("state_rule") or fin_state), facts=fin_facts,
            authority_tier=str(fin_tier), source=source_ids["financial"],
        ))
    elif fin_state in FINANCIAL_OPPOSE_STATES or fin_state == "MIXED":
        opposing.append(_condition(
            condition_id="FINANCIAL_NOT_IMPROVING", domain="FINANCIAL", polarity="OPPOSE",
            code=str(financial.get("state_rule") or fin_state), facts=fin_facts,
            authority_tier=str(fin_tier), source=source_ids["financial"],
        ))
    if fin_state in FINANCIAL_LIMITED_STATES or fin_tier in {"UNAVAILABLE", "BLOCKED", "PROVIDER_RESEARCH"}:
        limitations.append(_condition(
            condition_id="FINANCIAL_AUTHORITY_OR_COVERAGE_LIMITATION", domain="DATA_AUTHORITY", polarity="LIMITATION",
            code="FINANCIAL_EVIDENCE_TIER_PRESERVED", facts=fin_facts,
            authority_tier=str(fin_tier), source=source_ids["financial"],
        ))
    if contrast == "FINANCIAL_IMPROVEMENT_WITHOUT_PRICE_MOMENTUM":
        supporting.append(_condition(
            condition_id="FINANCIAL_WITHOUT_PRICE_MOMENTUM", domain="FINANCIAL", polarity="SUPPORT",
            code="FINANCIAL_IMPROVEMENT_WITHOUT_PRICE_MOMENTUM", facts=fin_facts,
            authority_tier=str(fin_tier), source=source_ids["financial"],
        ))

    planned = int(event.get("planned_unresolved_count") or 0)
    upcoming = int(event.get("confirmed_upcoming_count") or 0)
    executed = int(event.get("executed_count") or 0)
    if upcoming:
        supporting.append(_condition(
            condition_id="CONFIRMED_UPCOMING_EVENT", domain="CORPORATE_EVENT", polarity="SUPPORT",
            code="CONFIRMED_UPCOMING_EVENT_NO_PRICE_DIRECTION",
            facts={"confirmed_upcoming_count": upcoming, "does_not_assign_price_direction": True},
            authority_tier="OFFICIAL_QUALIFIED", source=source_ids["event"],
        ))
    if planned:
        supporting.append(_condition(
            condition_id="PLANNED_NOT_EXECUTED_EVENT", domain="CORPORATE_EVENT", polarity="SUPPORT",
            code="PLANNED_NOT_EXECUTED_PRESERVED",
            facts={"planned_unresolved_count": planned, "executed_count": executed, "planned_is_not_executed": True},
            authority_tier="OFFICIAL_QUALIFIED", source=source_ids["event"],
        ))
    if event.get("temporal_incomplete_count") or event.get("data_limited_count"):
        limitations.append(_condition(
            condition_id="EVENT_TEMPORAL_LIMITATION", domain="DATA_AUTHORITY", polarity="LIMITATION",
            code="EVENT_TEMPORAL_OR_EXECUTION_DETAILS_INCOMPLETE",
            facts={"temporal_incomplete_count": event.get("temporal_incomplete_count"),
                   "data_limited_count": event.get("data_limited_count")},
            authority_tier="OFFICIAL_SOURCE_TEMPORALLY_LIMITED", source=source_ids["event"],
        ))
    if event.get("conflicting_count"):
        unresolved.append(_condition(
            condition_id="EVENT_CONFLICT", domain="CORPORATE_EVENT", polarity="UNRESOLVED",
            code="CONFLICTING_EVIDENCE", facts={"conflicting_count": event.get("conflicting_count")},
            authority_tier="CONFLICTING_EVIDENCE", source=source_ids["event"],
        ))

    val_counts = _valuation_status_counts(valuation)
    if val_counts.get("BLOCKED") or val_counts.get("NOT_APPLICABLE") or not val_counts.get("READY"):
        limitations.append(_condition(
            condition_id="VALUATION_NOT_VALUE_AUTHORITY", domain="VALUATION_AUTHORITY", polarity="LIMITATION",
            code="VALUATION_BLOCKED_OR_NOT_READY_DOES_NOT_BLOCK_OTHER_AXES",
            facts={"metric_status_counts": val_counts, "does_not_establish_VALUE": True,
                   "does_not_create_price_target": True, "does_not_make_base_undervalued": True},
            authority_tier="CURRENT_VALUATION_RESEARCH", source=source_ids["valuation"],
        ))
    if val_counts.get("RESEARCH_USABLE"):
        limitations.append(_condition(
            condition_id="VALUATION_RESEARCH_USABLE_NOT_AUTHORITATIVE", domain="VALUATION_AUTHORITY", polarity="LIMITATION",
            code="RESEARCH_USABLE_IS_NOT_READY_OR_VALUE_AUTHORITY", facts={"metric_status_counts": val_counts},
            authority_tier="RESEARCH_USABLE", source=source_ids["valuation"],
        ))

    current_state_evidence = classified or hist_ok or fin_state not in FINANCIAL_LIMITED_STATES or upcoming or planned or executed
    explicit_speculative = (
        entry_state in UNCONFIRMED_EARLY_STATES
        or planned > 0
        or contrast == "FINANCIAL_IMPROVEMENT_WITHOUT_PRICE_MOMENTUM"
        or structural in HISTORICAL_EARLY_STATES
    )
    weak_sector = (
        sector_state in WEAK_SECTOR_STATES
        or sector_state == "MIXED"
        or relative.get("momentum_bucket") in WEAK_RELATIVE_BUCKETS
    )
    return {
        "ticker": ticker,
        "classified": classified,
        "entry_state": entry_state,
        "entry_action": opportunity.get("entry_action") or tactical.get("entry_action"),
        "research_priority": opportunity.get("priority_tier"),
        "eligible_strategy_lanes": list(opportunity.get("eligible_strategies") or []),
        "existing_evidence_bound_scenario_disposition": opportunity.get("scenario_status"),
        "supporting_conditions": supporting,
        "opposing_conditions": opposing,
        "confirmation_conditions": confirmation,
        "invalidation_conditions": invalidation,
        "material_risks": material_risks,
        "authority_limitations": limitations,
        "unresolved_questions": unresolved,
        "current_state_evidence": current_state_evidence,
        "explicit_speculative_evidence": explicit_speculative,
        "weak_sector": weak_sector,
        "sector_state": sector_state,
        "financial_state": fin_state,
        "financial_tier": fin_tier,
        "valuation_status_counts": val_counts,
        "confirmation_available": confirmation[0]["status"] == "AVAILABLE",
        "invalidation_available": invalidation[0]["status"] == "AVAILABLE",
        "liquidity_status": liquidity,
    }


def conservative_status(evidence: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    reasons = []
    if not evidence["classified"]:
        return "DATA_LIMITED", "CONSERVATIVE_REQUIRES_CLASSIFIED_TECHNICAL_CONFIRMATION", [
            "CONSERVATIVE_REQUIRES_CLASSIFIED_TECHNICAL_CONFIRMATION",
        ]
    if evidence["entry_state"] not in CONFIRMED_CONSTRUCTIVE_STATES:
        reasons.append("CONSERVATIVE_CONFIRMATION_BAR_NOT_MET")
        if evidence["entry_state"] == "BREAKOUT_READY":
            return "CONDITIONALLY_SUPPORTED", "CONSERVATIVE_REQUIRES_STRONGER_THAN_BREAKOUT_READY", [
                "CONSERVATIVE_REQUIRES_STRONGER_THAN_BREAKOUT_READY",
            ]
        return "NOT_SUPPORTED", "CONSERVATIVE_CONFIRMATION_BAR_NOT_MET", reasons
    if not evidence["confirmation_available"] or not evidence["invalidation_available"]:
        return "CONDITIONALLY_SUPPORTED", "CONSERVATIVE_CONFIRMATION_OR_INVALIDATION_UNAVAILABLE", [
            "CONSERVATIVE_CONFIRMATION_OR_INVALIDATION_UNAVAILABLE",
        ]
    if evidence["material_risks"]:
        return "CONDITIONALLY_SUPPORTED", MATERIAL_RISK_BLOCKS_CONSERVATIVE_SUPPORTED, [
            MATERIAL_RISK_BLOCKS_CONSERVATIVE_SUPPORTED,
        ]
    if evidence["weak_sector"]:
        return "CONDITIONALLY_SUPPORTED", "CONSERVATIVE_CONFIRMED_TREND_SECTOR_NOT_LEADING", [
            "CONSERVATIVE_CONFIRMED_TREND_SECTOR_NOT_LEADING",
        ]
    reasons.append("CONSERVATIVE_CONFIRMED_TREND_NO_MATERIAL_RISK")
    if evidence["sector_state"] == "LEADING":
        reasons.append("SECTOR_LEADING_SUPPORTS_CONSERVATIVE")
    return "SUPPORTED", "CONSERVATIVE_CONFIRMED_TREND_NO_MATERIAL_RISK", reasons


def base_status(evidence: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    if evidence["classified"]:
        return "SUPPORTED", "BASE_CURRENT_CLASSIFIED_STATE", [
            "BASE_CURRENT_CLASSIFIED_STATE", "BASE_IS_CURRENT_STATE_INTERPRETATION_NOT_MOST_LIKELY",
        ]
    if evidence["current_state_evidence"]:
        return "CONDITIONALLY_SUPPORTED", "BASE_PARTIAL_NONTECHNICAL_CURRENT_STATE", [
            "BASE_PARTIAL_NONTECHNICAL_CURRENT_STATE", "BASE_IS_CURRENT_STATE_INTERPRETATION_NOT_MOST_LIKELY",
        ]
    return "DATA_LIMITED", "BASE_NO_CURRENT_STATE_EVIDENCE", ["BASE_NO_CURRENT_STATE_EVIDENCE"]


def speculative_status(evidence: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    if evidence["explicit_speculative_evidence"]:
        reasons = ["SPECULATIVE_EXPLICIT_EARLY_OR_HIGHER_UNCERTAINTY_EVIDENCE", "SPECULATIVE_DOES_NOT_LOWER_EVIDENCE_AUTHORITY"]
        if evidence["material_risks"]:
            reasons.append("MATERIAL_RISKS_EXPLICIT_NOT_HIDDEN")
        return "SUPPORTED", "SPECULATIVE_EXPLICIT_EARLY_OR_HIGHER_UNCERTAINTY_EVIDENCE", reasons
    if not evidence["classified"] and not evidence["current_state_evidence"]:
        return "DATA_LIMITED", "SPECULATIVE_NO_EVIDENCE_TO_EVALUATE", ["SPECULATIVE_NO_EVIDENCE_TO_EVALUATE"]
    return "NOT_SUPPORTED", "NO_EXPLICIT_EARLY_OR_HIGHER_UNCERTAINTY_EVIDENCE", [
        "NO_EXPLICIT_EARLY_OR_HIGHER_UNCERTAINTY_EVIDENCE", "SPECULATIVE_DOES_NOT_FABRICATE_UPSIDE",
    ]


AXIS_STATUS = {
    "CONSERVATIVE": conservative_status,
    "BASE": base_status,
    "SPECULATIVE": speculative_status,
}


def _axis_record(axis: str, evidence: Mapping[str, Any], source_ids: Mapping[str, Any], as_of: Mapping[str, Any]) -> dict[str, Any]:
    status, rule, reasons = AXIS_STATUS[axis](evidence)
    confirmation = copy.deepcopy(evidence["confirmation_conditions"])
    invalidation = copy.deepcopy(evidence["invalidation_conditions"])
    if axis == "SPECULATIVE":
        # Evidence standards remain visible: unavailable gates stay unavailable.
        if confirmation[0]["status"] == "UNAVAILABLE":
            reasons = list(reasons) + ["SPECULATIVE_CONFIRMATION_REMAINS_UNAVAILABLE"]
        if invalidation[0]["status"] == "UNAVAILABLE":
            reasons = list(reasons) + ["SPECULATIVE_INVALIDATION_REMAINS_UNAVAILABLE"]
    return {
        "ticker": evidence["ticker"],
        "scenario_axis": axis,
        "scenario_status": status,
        "status_rule": rule,
        "status_reasons": list(reasons),
        "source_as_of": copy.deepcopy(dict(as_of)),
        "current_decision_context": {
            "research_priority": evidence["research_priority"],
            "entry_action": evidence["entry_action"],
            "entry_state": evidence["entry_state"],
            "eligible_strategy_lanes": list(evidence["eligible_strategy_lanes"]),
            "existing_evidence_bound_scenario_disposition": evidence["existing_evidence_bound_scenario_disposition"],
            "quoted_not_modified": True,
        },
        "eligible_strategy_lanes": list(evidence["eligible_strategy_lanes"]),
        "supporting_conditions": copy.deepcopy(evidence["supporting_conditions"]),
        "opposing_conditions": copy.deepcopy(evidence["opposing_conditions"]),
        "confirmation_conditions": confirmation,
        "invalidation_conditions": invalidation,
        "material_risks": copy.deepcopy(evidence["material_risks"]),
        "authority_limitations": copy.deepcopy(evidence["authority_limitations"]),
        "unresolved_questions": copy.deepcopy(evidence["unresolved_questions"]),
        "evidence_references": [{"source": name, "identity": identity} for name, identity in sorted(source_ids.items())],
        "allowed_uses": ["CURRENT_RESEARCH_CONTEXT"],
        "prohibited_uses": list(FORBIDDEN_USES),
        "base_is_not_most_likely": True if axis == "BASE" else None,
        "evidence_standard_lowered": False,
        "material_risk_rule": MATERIAL_RISK_BLOCKS_CONSERVATIVE_SUPPORTED if axis == "CONSERVATIVE" else "MATERIAL_RISK_LISTED_NOT_SCORED",
        "does_not_modify_research_priority": True,
        "does_not_modify_strategy_eligibility": True,
        "does_not_modify_entry_action": True,
    }


def _empty_counts() -> dict[str, int]:
    return {status: 0 for status in SCENARIO_STATUSES}


def _representative_predicates() -> dict[str, Any]:
    def axis_status(name, axis, status):
        return lambda rec: rec["axes"][axis]["scenario_status"] == status
    return {
        "conservative_supported": axis_status("c", "CONSERVATIVE", "SUPPORTED"),
        "base_supported": axis_status("b", "BASE", "SUPPORTED"),
        "speculative_supported": axis_status("s", "SPECULATIVE", "SUPPORTED"),
        "base_supported_while_wait": lambda rec: (
            rec["axes"]["BASE"]["scenario_status"] == "SUPPORTED"
            and rec["current_decision_context"]["entry_action"] == "WAIT"
        ),
        "speculative_with_material_risks": lambda rec: (
            rec["axes"]["SPECULATIVE"]["scenario_status"] == "SUPPORTED"
            and bool(rec["axes"]["SPECULATIVE"]["material_risks"])
        ),
        "strong_technical_weak_sector": lambda rec: (
            rec["current_decision_context"]["entry_state"] in {"UPTREND_CONFIRMED", "BREAKOUT_READY"}
            and any(item.get("condition_id") in {"SECTOR_NOT_LEADING", "SECTOR_RELATIVE_WEAK"}
                    for item in rec["axes"]["BASE"]["opposing_conditions"])
        ),
        "improving_financials_weak_price_momentum": lambda rec: any(
            item.get("code") == "FINANCIAL_IMPROVEMENT_WITHOUT_PRICE_MOMENTUM"
            for item in rec["axes"]["BASE"]["supporting_conditions"]
        ),
        "planned_event_not_executed": lambda rec: any(
            item.get("code") == "PLANNED_NOT_EXECUTED_PRESERVED"
            for item in rec["axes"]["SPECULATIVE"]["supporting_conditions"]
        ),
        "valuation_blocked_still_analyzable": lambda rec: (
            rec["axes"]["BASE"]["scenario_status"] in {"SUPPORTED", "CONDITIONALLY_SUPPORTED"}
            and any(item.get("code") == "VALUATION_BLOCKED_OR_NOT_READY_DOES_NOT_BLOCK_OTHER_AXES"
                    for item in rec["axes"]["BASE"]["authority_limitations"])
            and "VALUE" not in rec["current_decision_context"]["eligible_strategy_lanes"]
        ),
        "data_limited": lambda rec: rec["axes"]["BASE"]["scenario_status"] == "DATA_LIMITED",
    }


def _pick_representatives(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    predicates = _representative_predicates()
    selected: dict[str, Any] = {}
    for name, predicate in predicates.items():
        preferred = PREFERRED_REPRESENTATIVES.get(name)
        if preferred in records and predicate(records[preferred]):
            selected[name] = {"ticker": preferred, "present": True, "record": _slim_rep(records[preferred])}
            continue
        ticker = next((key for key in records if predicate(records[key])), None)
        selected[name] = (
            {"ticker": ticker, "present": True, "record": _slim_rep(records[ticker])}
            if ticker else {"ticker": None, "present": False, "record": None}
        )
    return selected


def _slim_rep(record: Mapping[str, Any]) -> dict[str, Any]:
    axes = {
        axis: {
            "scenario_axis": row["scenario_axis"], "scenario_status": row["scenario_status"],
            "status_rule": row["status_rule"], "status_reasons": row["status_reasons"],
            "confirmation_conditions": row["confirmation_conditions"],
            "invalidation_conditions": row["invalidation_conditions"],
            "material_risk_count": len(row["material_risks"]),
            "supporting_codes": [item.get("code") for item in row["supporting_conditions"]],
            "opposing_codes": [item.get("code") for item in row["opposing_conditions"]],
        }
        for axis, row in record["axes"].items()
    }
    return {
        "ticker": record["ticker"], "current_decision_context": record["current_decision_context"],
        "axes": axes,
    }


def build_artifact(*, current_official_universe: Mapping[str, Any], tactical: Mapping[str, Any],
                   opportunity: Mapping[str, Any], historical_context: Mapping[str, Any],
                   leadership_context: Mapping[str, Any], financial_context: Mapping[str, Any],
                   corporate_event_context: Mapping[str, Any], valuation_context: Mapping[str, Any],
                   risk_register: Mapping[str, Any]) -> dict[str, Any]:
    tickers = _official_tickers(current_official_universe)
    _verify_identity(tactical, contract="watchlist_tactical_entry_classifier/v1",
                     identity=tactical_module.content_identity, label="TACTICAL")
    _verify_identity(opportunity, contract="current_opportunity_prioritization/v1",
                     identity=opportunity_module.content_identity, label="OPPORTUNITY")
    _verify_identity(historical_context, contract="market_wide_historical_research_context/v1",
                     identity=historical_content_identity, label="HISTORICAL_CONTEXT")
    _verify_identity(leadership_context, contract="current_market_sector_leadership_context/v1",
                     identity=leadership_content_identity, label="LEADERSHIP_CONTEXT")
    _verify_identity(financial_context, contract="current_financial_momentum_context/v1",
                     identity=financial_content_identity, label="FINANCIAL_CONTEXT")
    _verify_identity(corporate_event_context, contract="current_corporate_event_context/v1",
                     identity=event_content_identity, label="EVENT_CONTEXT")
    _verify_identity(valuation_context, contract="market_wide_current_valuation/v1",
                     identity=valuation_content_identity, label="VALUATION_CONTEXT")
    _verify_identity(risk_register, contract="current_research_risk_register/v1",
                     identity=risk_register_module.content_identity, label="RISK_REGISTER")
    sources = {
        "official_universe": current_official_universe.get("artifact_identity"),
        "tactical": tactical.get("artifact_identity"),
        "opportunity": opportunity.get("artifact_identity"),
        "historical": historical_context.get("artifact_identity"),
        "leadership": leadership_context.get("artifact_identity"),
        "financial": financial_context.get("artifact_identity"),
        "event": corporate_event_context.get("artifact_identity"),
        "valuation": valuation_context.get("artifact_identity"),
        "risk_register": risk_register.get("artifact_identity"),
    }
    as_of = {
        "tactical": tactical.get("session"),
        "opportunity": opportunity.get("research_session"),
        "historical": historical_context.get("session"),
        "leadership": leadership_context.get("session"),
        "financial": financial_context.get("session"),
        "event": corporate_event_context.get("research_session"),
        "valuation": valuation_context.get("valuation_session"),
    }
    required = {
        "tactical": tactical.get("records"),
        "opportunity": opportunity.get("records"),
        "leadership": leadership_context.get("ticker_contexts"),
        "financial": financial_context.get("records"),
        "event": corporate_event_context.get("records"),
        "valuation": valuation_context.get("records"),
        "risk_register": risk_register.get("records"),
    }
    if any(not isinstance(rows, Mapping) for rows in required.values()):
        raise CurrentResearchScenarioContextError("SOURCE_RECORDS_INVALID")
    if any(ticker not in rows for rows in required.values() for ticker in tickers):
        raise CurrentResearchScenarioContextError("OFFICIAL_TICKER_MISSING_FROM_REQUIRED_SOURCE")
    historical_rows = historical_context.get("records") if isinstance(historical_context.get("records"), Mapping) else {}
    market = leadership_context.get("market") or {}
    records: dict[str, Any] = {}
    status_by_axis = {axis: _empty_counts() for axis in SCENARIO_AXES}
    lane_axis = {lane: {axis: _empty_counts() for axis in SCENARIO_AXES} for lane in STRATEGY_LANES}
    action_axis = {action: {axis: _empty_counts() for axis in SCENARIO_AXES} for action in ENTRY_ACTIONS}
    quoted_priority: dict[str, str | None] = {}
    quoted_action: dict[str, str | None] = {}
    quoted_lanes: dict[str, list[str]] = {}
    for ticker in tickers:
        evidence = collect_evidence(
            ticker=ticker, tactical=required["tactical"][ticker], opportunity=required["opportunity"][ticker],
            historical=historical_rows.get(ticker, {}), leadership=required["leadership"][ticker],
            market=market, financial=required["financial"][ticker], event=required["event"][ticker],
            valuation=required["valuation"][ticker], risk_row=required["risk_register"][ticker],
            source_ids=sources,
        )
        axes = {axis: _axis_record(axis, evidence, sources, as_of) for axis in SCENARIO_AXES}
        quoted_priority[ticker] = evidence["research_priority"]
        quoted_action[ticker] = evidence["entry_action"]
        quoted_lanes[ticker] = list(evidence["eligible_strategy_lanes"])
        action = evidence["entry_action"] if evidence["entry_action"] in action_axis else None
        records[ticker] = {
            "ticker": ticker,
            "current_decision_context": axes["BASE"]["current_decision_context"],
            "axes": axes,
            "source_as_of": copy.deepcopy(dict(as_of)),
            "blocked_outputs": {name: "NOT_EMITTED_OR_MODIFIED" for name in FORBIDDEN_USES},
        }
        for axis, row in axes.items():
            status_by_axis[axis][row["scenario_status"]] += 1
            if action:
                action_axis[action][axis][row["scenario_status"]] += 1
            for lane in evidence["eligible_strategy_lanes"]:
                if lane in lane_axis:
                    lane_axis[lane][axis][row["scenario_status"]] += 1
        if records[ticker]["current_decision_context"]["research_priority"] != required["opportunity"][ticker].get("priority_tier"):
            raise CurrentResearchScenarioContextError("RESEARCH_PRIORITY_MUTATION")
        if records[ticker]["current_decision_context"]["entry_action"] != required["opportunity"][ticker].get("entry_action"):
            raise CurrentResearchScenarioContextError("ENTRY_ACTION_MUTATION")
        if list(records[ticker]["current_decision_context"]["eligible_strategy_lanes"]) != list(
            required["opportunity"][ticker].get("eligible_strategies") or []
        ):
            raise CurrentResearchScenarioContextError("STRATEGY_ELIGIBILITY_MUTATION")
    coverage = {
        "official_universe_denominator": len(tickers),
        "ticker_coverage": len(records),
        "scenario_record_count": len(records) * len(SCENARIO_AXES),
        "status_distribution_by_axis": {axis: dict(counts) for axis, counts in status_by_axis.items()},
        "lane_axis_crosstab": {lane: {axis: dict(counts) for axis, counts in axes.items()} for lane, axes in lane_axis.items()},
        "action_axis_crosstab": {action: {axis: dict(counts) for axis, counts in axes.items()} for action, axes in action_axis.items()},
        "tickers_with_any_supported_axis": sum(
            any(row["scenario_status"] == "SUPPORTED" for row in record["axes"].values())
            for record in records.values()
        ),
        "value_eligible_count": sum("VALUE" in record["current_decision_context"]["eligible_strategy_lanes"] for record in records.values()),
        "main_data_authority_limitations": sorted({
            item.get("code") for record in records.values()
            for item in record["axes"]["BASE"]["authority_limitations"] if item.get("code")
        }),
    }
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "milestone": MILESTONE,
        "research_mode": "CURRENT_RESEARCH_SCENARIO_CONTEXT_ONLY",
        "scenario_axes": list(SCENARIO_AXES),
        "scenario_status_vocabulary": list(SCENARIO_STATUSES),
        "axis_definitions": {
            "CONSERVATIVE": "Requires stronger confirmation, stronger authority, or lower unresolved material risk. Not a bearish label.",
            "BASE": "Direct current-state interpretation supported by existing evidence. Not most-likely and not a probability.",
            "SPECULATIVE": "Earlier/higher-uncertainty hypothesis only when explicit evidence exists. Does not lower evidence standards and is not fabricated upside.",
        },
        "orthogonality": {
            "strategy_lane_is_not_scenario_axis": True,
            "scenario_axis_is_not_research_priority": True,
            "scenario_axis_is_not_entry_action": True,
            "scenario_axis_is_not_sizing_authority": True,
            "existing_bear_base_bull_overlay_is_not_replaced": True,
            "conservative_is_not_bearish": True,
            "speculative_is_not_bullish": True,
        },
        "official_universe_denominator": len(tickers),
        "records": records,
        "source_contexts": {
            name: {"artifact_identity": identity, "as_of": as_of.get(name) if name in as_of else None, "available": True}
            for name, identity in sources.items()
        },
        "coverage": coverage,
        "validation": {"representative_cases": _pick_representatives(records)},
        "quoted_decision_snapshot": {
            "research_priority": quoted_priority,
            "entry_action": quoted_action,
            "eligible_strategy_lanes": quoted_lanes,
        },
        "blocked_outputs": {name: "NOT_EMITTED_OR_MODIFIED" for name in FORBIDDEN_USES},
        "authority_boundary": {
            "is_actionable": False,
            "research_only": True,
            "no_probability": True,
            "no_expected_return": True,
            "no_target_price": True,
            "no_sizing": True,
            "no_recommendation": True,
            "does_not_modify_research_priority": True,
            "does_not_modify_strategy_eligibility": True,
            "does_not_modify_entry_action": True,
            "does_not_modify_daily_decision_queue": True,
            "does_not_replace_evidence_bound_bear_base_bull": True,
            "data_limitation_is_not_economic_risk": True,
            "material_risk_rule": MATERIAL_RISK_BLOCKS_CONSERVATIVE_SUPPORTED,
            "raw_as_traded": "NOT_PROMOTED",
            "pit": "BLOCKED",
            "backtest": "NOT_EMITTED",
        },
        "deterministic_rules": {
            "CONSERVATIVE": "SUPPORTED only for classified UPTREND_CONFIRMED with available confirmation/invalidation, no material risks, and non-weak sector; BREAKOUT_READY is CONDITIONALLY_SUPPORTED; unclassified is DATA_LIMITED; other classified states are NOT_SUPPORTED. Material risk never yields CONSERVATIVE SUPPORTED.",
            "BASE": "SUPPORTED when a classified current tactical state exists; CONDITIONALLY_SUPPORTED when only non-technical current-state evidence exists; DATA_LIMITED otherwise. BASE is never a most-likely claim.",
            "SPECULATIVE": "SUPPORTED only with explicit early/unconfirmed state, planned-not-executed event, financial-improvement-without-price-momentum, or historical early-reversal state. Evidence standards are not lowered. Absence of such evidence is NOT_SUPPORTED, not fabricated upside.",
        },
    }
    if any(token in json.dumps(artifact) for token in ("80_PERCENT_CONFIDENCE", "EXPECTED_WINNER", "VERY_LIKELY")):
        raise CurrentResearchScenarioContextError("FORBIDDEN_PROBABILITY_LABEL")
    artifact.update(content_identity(artifact))
    return artifact


def replay(artifact: Mapping[str, Any]) -> None:
    if artifact.get("contract_version") != CONTRACT_VERSION:
        raise CurrentResearchScenarioContextError("SCENARIO_CONTRACT_UNSUPPORTED")
    if artifact.get("artifact_sha256") != content_identity(artifact).get("artifact_sha256"):
        raise CurrentResearchScenarioContextError("SCENARIO_IDENTITY_MISMATCH")
    records = artifact.get("records") or {}
    if artifact.get("official_universe_denominator") != len(records):
        raise CurrentResearchScenarioContextError("SCENARIO_DENOMINATOR_MISMATCH")
    forbidden_record_keys = {
        "probability", "expected_return", "target_price", "upside_pct", "downside_pct",
        "payoff_ratio", "position_size", "intrinsic_value", "win_rate",
    }
    for record in records.values():
        for row in (record.get("axes") or {}).values():
            overlap = forbidden_record_keys.intersection(row)
            if overlap:
                raise CurrentResearchScenarioContextError("FORBIDDEN_FIELD:" + ",".join(sorted(overlap)))
            if row.get("scenario_status") in {"VERY_LIKELY", "EXPECTED_WINNER", "80_PERCENT_CONFIDENCE"}:
                raise CurrentResearchScenarioContextError("FORBIDDEN_STATUS_LABEL")
    snapshot = artifact.get("quoted_decision_snapshot") or {}
    for ticker, record in records.items():
        context = record.get("current_decision_context") or {}
        if context.get("research_priority") != snapshot.get("research_priority", {}).get(ticker):
            raise CurrentResearchScenarioContextError("RESEARCH_PRIORITY_DRIFT")
        if context.get("entry_action") != snapshot.get("entry_action", {}).get(ticker):
            raise CurrentResearchScenarioContextError("ENTRY_ACTION_DRIFT")
        if list(context.get("eligible_strategy_lanes") or []) != list(snapshot.get("eligible_strategy_lanes", {}).get(ticker) or []):
            raise CurrentResearchScenarioContextError("STRATEGY_ELIGIBILITY_DRIFT")
        for axis in SCENARIO_AXES:
            row = (record.get("axes") or {}).get(axis) or {}
            if row.get("scenario_axis") != axis:
                raise CurrentResearchScenarioContextError("AXIS_IDENTITY_DRIFT")
            if row.get("scenario_status") not in SCENARIO_STATUSES:
                raise CurrentResearchScenarioContextError("STATUS_NOT_IN_VOCABULARY")
            if row.get("evidence_standard_lowered") is True:
                raise CurrentResearchScenarioContextError("SPECULATIVE_LOWERED_EVIDENCE")
            for gate_name in ("confirmation_conditions", "invalidation_conditions"):
                for item in row.get(gate_name) or []:
                    if item.get("invented") is True:
                        raise CurrentResearchScenarioContextError("INVENTED_CONDITION")
