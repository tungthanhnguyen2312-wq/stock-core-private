"""Compact security_decision_context/v1 — research support, not execution authority.

Reuses the existing shadow-recommendation stance vocabulary and the tactical
entry_state / entry_action fields. Exact ADTV20, PIT, and execution-capacity
blocks never force WAIT.
"""
from __future__ import annotations

from typing import Any, Mapping

from shadow_security_recommendation import LABELS
from watchlist_tactical_entry_classifier import ENTRY_ACTION_BY_ENTRY_STATE

CONTRACT_VERSION = "security_decision_context/v1"
INITIATE = "INITIATE_RESEARCH_CANDIDATE"
ACCUMULATE = "ACCUMULATE_RESEARCH_CANDIDATE"
WAIT_FOR_CONFIRMATION = "WAIT_FOR_CONFIRMATION"
HIGH_RISK = "HIGH_RISK_SPECULATION_ONLY"
AVOID_NEW_ENTRY = "AVOID_NEW_ENTRY"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
CONSTRUCTIVE = frozenset({"BREAKOUT_READY", "EARLY_REVERSAL_CANDIDATE", "UPTREND_CONFIRMED", "BASE_BUILDING"})
ADVERSE = frozenset({"DOWNTREND", "BREAKDOWN_RISK", "DISTRIBUTION_RISK"})
# Missing/unusable fundamental evidence (axis not usable, or the specific profitability read is
# itself indeterminate) is NOT an observed negative signal. It must never be conflated with a
# genuinely observed weak/loss reading when choosing between HIGH_RISK and INSUFFICIENT_EVIDENCE.
FUNDAMENTAL_EVIDENCE_MISSING_STATES = frozenset({"INSUFFICIENT_DATA", "UNAVAILABLE"})
FUNDAMENTAL_OBSERVED_WEAK_STATES = frozenset({"LOSS_MAKING", "BREAK_EVEN"})
FUNDAMENTAL_OBSERVED_DETERIORATION_TRAJECTORY = frozenset({"TURNED_TO_LOSS", "LOSS_WIDENED"})
_BREADTH_CONSTRUCTIVE = frozenset({"BROAD_PARTICIPATION"})
_BREADTH_ADVERSE = frozenset({"DETERIORATING_BREADTH"})
_SECTOR_LEADERSHIP_CONSTRUCTIVE = frozenset({"LEADING"})
_SECTOR_LEADERSHIP_ADVERSE = frozenset({"WEAKENING"})
_SETUP_TAGS_ADVERSE = frozenset({"TECHNICAL_DETERIORATION", "PRICE_VOLUME_DISTRIBUTION_RISK"})
# A stance with no long thesis (AVOID_NEW_ENTRY) has nothing bullish for its technical boundary to
# invalidate -- that boundary is honestly a reconsideration watch, not a thesis invalidation.
STANCE_RECONSIDERATION_WATCH = "STANCE_RECONSIDERATION_WATCH"
THESIS_INVALIDATION = "THESIS_INVALIDATION"


def _triggered(boundary: Mapping[str, Any] | None) -> bool:
    if not isinstance(boundary, Mapping):
        return False
    return boundary.get("current_trigger_state") == "TRIGGERED" or boundary.get("status") == "TRIGGERED"


def _trigger_state(boundary: Mapping[str, Any] | None) -> str:
    """Actual confirmation trigger state, kept distinct from the boundary's own ``status``.

    ``status == READY`` only means a single clean numeric trigger has been instrumented (a real
    baseline value/operator/metric) -- it is never itself evidence that the trigger has fired.
    """
    if not isinstance(boundary, Mapping):
        return "NOT_AVAILABLE"
    if _triggered(boundary):
        return "TRIGGERED"
    if boundary.get("current_trigger_state") is not None:
        return str(boundary["current_trigger_state"])
    return "NOT_AVAILABLE"


def _axis_evidence_tags(opportunity: Mapping[str, Any]) -> dict[str, list[str]]:
    """Deterministic evidence tags already present on the record, split by whether each
    materially supports (``constructive``) or conflicts with (``adverse``) a constructive
    research stance. Reuses existing governed vocabulary verbatim; computes nothing new."""
    fundamental = opportunity.get("fundamental") or {}
    tactical = opportunity.get("tactical") or {}
    valuation = opportunity.get("valuation") or {}
    market = opportunity.get("market_sector") or {}
    catalyst = opportunity.get("catalyst") or {}
    constructive: list[str] = []
    adverse: list[str] = []

    fund_usable = bool(fundamental.get("research_usable"))
    profit_state = fundamental.get("state") if fund_usable else None
    if profit_state == "PROFITABLE":
        constructive.append("PROFITABLE_FUNDAMENTAL")
    elif profit_state in FUNDAMENTAL_OBSERVED_WEAK_STATES:
        adverse.append(profit_state)
    trajectory = fundamental.get("trajectory") if fund_usable else None
    if trajectory in FUNDAMENTAL_OBSERVED_DETERIORATION_TRAJECTORY:
        adverse.append(trajectory)

    relative = (valuation.get("peer_relative_context") or {}).get("relative_research_state")
    if relative == "ATTRACTIVE_RELATIVE_RESEARCH":
        constructive.append("ATTRACTIVE_RELATIVE_RESEARCH")
    elif relative == "EXPENSIVE_RELATIVE_RESEARCH":
        adverse.append("EXPENSIVE_RELATIVE_RESEARCH")
    if valuation.get("earnings_state") == "TURNAROUND_CONTEXT":
        adverse.append("TURNAROUND_CONTEXT")

    setup_tags = set(tactical.get("setup_tags") or [])
    for tag in sorted(setup_tags & _SETUP_TAGS_ADVERSE):
        adverse.append(tag)

    if catalyst.get("status") == "QUALIFIED_CATALYST" or catalyst.get("qualified_current_catalysts"):
        constructive.append("QUALIFIED_CATALYST_PRESENT")

    breadth = market.get("breadth_regime")
    if breadth in _BREADTH_CONSTRUCTIVE:
        constructive.append(f"MARKET_BREADTH_{breadth}")
    elif breadth in _BREADTH_ADVERSE:
        adverse.append(f"MARKET_BREADTH_{breadth}")

    leadership = (market.get("sector_relative_context") or {}).get("leadership_state")
    if leadership in _SECTOR_LEADERSHIP_CONSTRUCTIVE:
        constructive.append(f"SECTOR_LEADERSHIP_{leadership}")
    elif leadership in _SECTOR_LEADERSHIP_ADVERSE:
        adverse.append(f"SECTOR_LEADERSHIP_{leadership}")

    return {"constructive": constructive, "adverse": adverse}


def _infer_stance_dict(opportunity: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic research stance from usable current axes. Liquidity/PIT never force WAIT."""
    fundamental = opportunity.get("fundamental") or {}
    tactical = opportunity.get("tactical") or {}
    valuation = opportunity.get("valuation") or {}
    liquidity = opportunity.get("liquidity") or {}
    downside = opportunity.get("downside_invalidation") or {}
    reasons: list[str] = []
    warnings: list[str] = []

    if liquidity.get("exact_execution_capacity_status") == "EXECUTION_CAPACITY_EXACT_BLOCKED":
        warnings.append("EXECUTION_CAPACITY_EXACT_BLOCKED_NOT_A_STANCE_GATE")
    if (valuation.get("share_basis") or "").endswith("PROXY") or valuation.get("share_basis") == "CURRENT_SHARE_RESEARCH_PROXY":
        warnings.append("SHARE_BASIS_RESEARCH_PROXY")
    if valuation.get("earnings_state"):
        warnings.append(str(valuation["earnings_state"]))

    fund_usable = bool(fundamental.get("research_usable"))
    tac_usable = bool(tactical.get("research_usable"))
    entry_state = tactical.get("primary_entry_state") if tac_usable else None
    entry_action = tactical.get("entry_action") if tac_usable else None
    confirmation = (tactical.get("confirmation") or {}) if tac_usable else {}
    profit_state = fundamental.get("state") if fund_usable else None
    # Missing (axis unusable, or profitability itself indeterminate) is kept strictly separate
    # from an observed weak/loss/deteriorating reading -- see the module-level constants' docstring.
    fundamental_missing = (not fund_usable) or profit_state in FUNDAMENTAL_EVIDENCE_MISSING_STATES
    fundamental_observed_weak = fund_usable and (
        profit_state in FUNDAMENTAL_OBSERVED_WEAK_STATES
        or fundamental.get("trajectory") in FUNDAMENTAL_OBSERVED_DETERIORATION_TRAJECTORY
    )

    technical = downside.get("technical") or {}
    fundamental_inv = downside.get("fundamental") or {}
    if _triggered(technical) or _triggered(fundamental_inv):
        warnings.append("INVALIDATION_TRIGGER_PRESENT")
    if downside.get("thesis_conflict"):
        warnings.append("COUNTER_THESIS_PRESENT")

    if not fund_usable and not tac_usable:
        return _stance(INSUFFICIENT_EVIDENCE, ["NO_USABLE_FUNDAMENTAL_OR_TACTICAL_AXIS"], warnings, entry_state, entry_action)

    if entry_state in ADVERSE:
        reasons.append("ADVERSE_TACTICAL_ENTRY_STATE")
        return _stance(AVOID_NEW_ENTRY, reasons, warnings, entry_state, entry_action)

    if entry_state in CONSTRUCTIVE and fundamental_observed_weak:
        reasons.append("CONSTRUCTIVE_TACTICAL_WITH_OBSERVED_WEAK_OR_LOSS_FUNDAMENTAL")
        return _stance(HIGH_RISK, reasons, warnings, entry_state, entry_action)

    if entry_state in CONSTRUCTIVE and fundamental_missing:
        # Constructive tactical evidence with fundamental evidence merely unavailable is not a
        # speculation signal -- it is an evidence gap. Reserve HIGH_RISK for an actually observed
        # weak/loss/deteriorating fundamental read (handled above).
        reasons.append("CONSTRUCTIVE_TACTICAL_WITH_FUNDAMENTAL_EVIDENCE_UNAVAILABLE")
        return _stance(INSUFFICIENT_EVIDENCE, reasons, warnings, entry_state, entry_action)

    if entry_state == "EARLY_REVERSAL_CANDIDATE":
        reasons.append("EARLY_REVERSAL_CANDIDATE")
        return _stance(INITIATE, reasons, warnings, entry_state, entry_action)

    if entry_state == "BREAKOUT_READY":
        # confirmation["status"] == READY means the boundary is instrumented (a real baseline
        # value/operator/metric exists) -- it is not evidence the trigger has actually fired.
        # Only an actual TRIGGERED trigger state may promote to INITIATE; a merely-instrumented
        # boundary preserves the existing WAIT_FOR_CONFIRMATION path.
        if _triggered(confirmation):
            reasons.append("BREAKOUT_READY_CONFIRMATION_TRIGGERED")
            return _stance(INITIATE, reasons, warnings, entry_state, entry_action)
        reasons.append("BREAKOUT_READY_AWAITING_CONFIRMATION")
        return _stance(WAIT_FOR_CONFIRMATION, reasons, warnings, entry_state, entry_action)

    if entry_state in {"BASE_BUILDING", "UPTREND_CONFIRMED"} and fund_usable:
        reasons.append("CONSTRUCTIVE_NON_BREAKOUT_WITH_USABLE_FUNDAMENTAL")
        return _stance(ACCUMULATE, reasons, warnings, entry_state, entry_action)

    if entry_state in {"SELLING_PRESSURE_EASING", "SIDEWAYS_NEUTRAL"}:
        reasons.append("TACTICAL_STATE_AWAITING_CONFIRMATION")
        return _stance(WAIT_FOR_CONFIRMATION, reasons, warnings, entry_state, entry_action)

    if not tac_usable and fund_usable:
        # Usable fundamental evidence with the tactical axis simply not current is research
        # monitoring, not INSUFFICIENT_EVIDENCE -- it is not permission to enter either.
        reasons.append("TACTICAL_AXIS_NOT_CURRENT")
        return _stance(WAIT_FOR_CONFIRMATION, reasons, warnings, None, None)

    reasons.append("NO_MAPPED_RESEARCH_STANCE")
    return _stance(INSUFFICIENT_EVIDENCE, reasons, warnings, entry_state, entry_action)


def infer_research_stance(opportunity: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic research stance, upgraded with multi-axis WHY / counter-thesis /
    counterbalancing-context evidence already present on the record (see
    ``_axis_evidence_tags``). The stance label itself comes from ``_infer_stance_dict`` alone."""
    stance = _infer_stance_dict(opportunity)
    axis_tags = _axis_evidence_tags(opportunity)
    downside = opportunity.get("downside_invalidation") or {}
    label = stance["research_stance"]

    counter_thesis = list(downside.get("thesis_conflict") or [])
    for tag in axis_tags["adverse"]:
        if tag not in counter_thesis:
            counter_thesis.append(tag)
    stance["counter_thesis"] = counter_thesis

    # Positive evidence on an adverse stance is shown as counterbalancing context, distinct from
    # the tactical-veto reason itself -- it never dilutes or overrides the veto.
    stance["counterbalancing_context"] = list(axis_tags["constructive"]) if label in {AVOID_NEW_ENTRY, HIGH_RISK} else []

    if label in {WAIT_FOR_CONFIRMATION, INSUFFICIENT_EVIDENCE}:
        extra = axis_tags["adverse"] + axis_tags["constructive"]
    elif label in {INITIATE, ACCUMULATE}:
        extra = axis_tags["constructive"]
    else:
        extra = []
    stance["reasons"] = stance["reasons"] + [tag for tag in extra if tag not in stance["reasons"]]
    return stance


def _stance(label: str, reasons: list[str], warnings: list[str], entry_state: str | None,
            entry_action: str | None) -> dict[str, Any]:
    if label not in LABELS:
        raise ValueError(f"RESEARCH_STANCE_NOT_IN_GOVERNED_VOCABULARY:{label}")
    readiness = "RESEARCH_CONDITIONAL"
    if label == INSUFFICIENT_EVIDENCE:
        readiness = "RESEARCH_NOT_READY"
    elif label in {INITIATE, ACCUMULATE, HIGH_RISK, AVOID_NEW_ENTRY}:
        readiness = "RESEARCH_READY_CONDITIONAL"
    return {
        "research_stance": label,
        "research_stance_readiness": readiness,
        "reasons": reasons,
        "warnings": warnings,
        "entry_state": entry_state,
        "entry_action": entry_action if entry_action is not None else (
            ENTRY_ACTION_BY_ENTRY_STATE.get(entry_state) if entry_state else None
        ),
        "liquidity_or_pit_did_not_force_wait": True,
    }


def build_ticker_decision(opportunity: Mapping[str, Any]) -> dict[str, Any]:
    inference = infer_research_stance(opportunity)
    tactical = opportunity.get("tactical") or {}
    valuation = opportunity.get("valuation") or {}
    fundamental = opportunity.get("fundamental") or {}
    catalyst = opportunity.get("catalyst") or {}
    liquidity = opportunity.get("liquidity") or {}
    downside = opportunity.get("downside_invalidation") or {}
    confirmation = tactical.get("confirmation") or {}
    # Boundary availability/status (the pre-existing "status" field) and the actual trigger state
    # are exposed as distinct sibling fields -- never collapsed into one signal.
    confirmation_boundary = {**confirmation, "confirmation_trigger_state": _trigger_state(confirmation)}
    financial = _financial_analysis_annotation(opportunity.get("financial_analysis"))
    technical_invalidation = (tactical.get("invalidation") if tactical.get("research_usable") else None) \
        or downside.get("technical") or {"status": "UNAVAILABLE"}
    technical_invalidation = {
        **technical_invalidation,
        "semantic": STANCE_RECONSIDERATION_WATCH if inference["research_stance"] == AVOID_NEW_ENTRY else THESIS_INVALIDATION,
    }
    return {
        "ticker": opportunity["ticker"],
        "as_of_session": opportunity["as_of_session"],
        "entry_state": inference["entry_state"],
        "entry_action": inference["entry_action"],
        "research_stance": inference["research_stance"],
        "research_stance_readiness": inference["research_stance_readiness"],
        "factual_axes": {
            "fundamental_state": fundamental.get("state"),
            "fundamental_readiness": fundamental.get("readiness"),
            "fundamental_freshness": (fundamental.get("freshness") or {}).get("freshness_status"),
            "valuation_relative_state": (valuation.get("peer_relative_context") or {}).get("relative_research_state"),
            "valuation_share_basis": valuation.get("share_basis"),
            "tactical_entry_state": tactical.get("primary_entry_state"),
            "tactical_freshness": (tactical.get("freshness") or {}).get("freshness_status"),
            "catalyst_status": catalyst.get("status"),
            "liquidity_research_proxy": liquidity.get("readiness"),
            "execution_capacity_exact": liquidity.get("exact_execution_capacity_status"),
            "portfolio_availability": (opportunity.get("portfolio_availability") or {}).get("status"),
        },
        "deterministic_research_inference": {
            "research_stance": inference["research_stance"],
            "reasons": inference["reasons"],
            "confirmation_status": confirmation.get("status"),
            "confirmation_trigger_state": confirmation_boundary["confirmation_trigger_state"],
            "relative_valuation": (valuation.get("peer_relative_context") or {}).get("relative_research_state"),
        },
        "warnings_counter_thesis": {
            "warnings": [*inference["warnings"], *financial["warnings"]],
            "counter_thesis": [*inference["counter_thesis"], *financial["counter_thesis"]],
        },
        "counterbalancing_context": inference["counterbalancing_context"],
        "confirmation_boundary": confirmation_boundary,
        "technical_invalidation": technical_invalidation,
        "fundamental_invalidation": downside.get("fundamental") or {"status": "UNAVAILABLE"},
        "key_counter_thesis": [*inference["counter_thesis"], *financial["counter_thesis"]],
        "financial_analysis": financial,
        "per_axis_freshness": (opportunity.get("data_authority") or {}).get("per_axis_freshness") or {},
        "authority_boundary": {
            "is_actionable": False, "research_support_not_execution": True,
            "no_score": True, "no_rank": True, "no_probability": True, "no_target_price": True,
            "security_attractiveness_separate_from_portfolio_fit": True,
            "exact_execution_capacity_is_not_a_wait_gate": True,
            "historical_pit_is_not_a_wait_gate": True,
        },
    }


def _financial_analysis_annotation(context: Mapping[str, Any] | None) -> dict[str, Any]:
    """Fixed V2 explanatory templates; this deliberately does not infer stance."""
    if not isinstance(context, Mapping):
        return {"status": "NOT_SUPPLIED", "supporting": [], "counter_thesis": [], "warnings": [],
                "missing_dimensions": [], "current_financial_weakness": [],
                "future_financial_invalidation_watch": [], "compact": None, "is_actionable": False}
    if context.get("status") == "ABSENT":
        return {"status": "ABSENT", "supporting": [], "counter_thesis": [], "warnings": ["FA_V2_CONTEXT_ABSENT"],
                "missing_dimensions": ["FA_V2_CONTEXT_ABSENT"], "current_financial_weakness": [],
                "future_financial_invalidation_watch": [], "compact": dict(context), "is_actionable": False}
    supporting, counter, missing, weakness, watches = [], [], [], [], []
    state_map = {
        "profitability_state": ("PROFITABLE", "FA_V2_PROFITABLE", "LOSS_MAKING", "FA_V2_LOSS_MAKING", "OBSERVED_LOSS_MAKING", "PROFITABILITY_REVERSAL_WATCH"),
        "margin_state": ("MARGIN_EXPANDING", "FA_V2_MARGIN_EXPANDING", "MARGIN_COMPRESSING", "FA_V2_MARGIN_COMPRESSING", "OBSERVED_MARGIN_COMPRESSING", "MARGIN_COMPRESSION_TRANSITION_WATCH"),
        "balance_sheet_state": ("STRENGTHENING", "FA_V2_BALANCE_SHEET_STRENGTHENING", "DETERIORATING", "FA_V2_BALANCE_SHEET_DETERIORATING", "OBSERVED_EQUITY_ASSETS_DETERIORATING", "EQUITY_ASSETS_DETERIORATION_WATCH"),
    }
    for key, (positive, positive_id, negative, negative_id, weakness_id, watch_id) in state_map.items():
        value = context.get(key)
        if value == positive:
            supporting.append(positive_id)
        elif value == negative:
            counter.append(negative_id); weakness.append(weakness_id); watches.append(watch_id)
    # Cash conversion is a V2 proxy.  It can describe an observed counter-thesis,
    # but is never recast as READY supporting evidence.
    if context.get("cash_conversion_state") == "WEAK":
        counter.append("FA_V2_CASH_CONVERSION_WEAK"); weakness.append("OBSERVED_CASH_CONVERSION_WEAK"); watches.append("CASH_CONVERSION_DETERIORATION_WATCH")
    elif context.get("cash_conversion_state") == "HEALTHY":
        missing.append("FA_V2_CASH_CONVERSION_PROXY_NOT_READY")
    if context.get("profitability_state") == "PROFITABLE" and context.get("cash_conversion_state") == "WEAK":
        counter.append("FA_V2_PROFIT_CASH_CONFLICT"); weakness.append("OBSERVED_PROFIT_CASH_CONFLICT")
    if context.get("growth_state") == "CONTRACTING":
        weakness.append("OBSERVED_GROWTH_CONTRACTING")
    if context.get("profitability_state") == "TURNAROUND_CONTEXT":
        watches.append("TURNAROUND_FAILURE_WATCH")
    if context.get("capital_efficiency_state") in {None, "UNAVAILABLE"}:
        missing.append("FA_V2_CAPITAL_EFFICIENCY_UNAVAILABLE")
    if any("DEBT_EVIDENCE_UNAVAILABLE" in str(item) for item in context.get("warnings") or []):
        missing.append("FA_V2_DEBT_EVIDENCE_UNAVAILABLE")
    return {"status": "AVAILABLE", "supporting": supporting, "counter_thesis": counter,
            "warnings": list(context.get("warnings") or []), "missing_dimensions": missing,
            "current_financial_weakness": weakness, "future_financial_invalidation_watch": watches,
            "compact": dict(context), "is_actionable": False,
            "turnaround_state": "FA_V2_TURNAROUND_CONTEXT" if context.get("profitability_state") == "TURNAROUND_CONTEXT" else None}


def compact_decision(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ticker": record["ticker"], "as_of_session": record["as_of_session"],
        "entry_state": record["entry_state"], "entry_action": record["entry_action"],
        "research_stance": record["research_stance"],
        "research_stance_readiness": record["research_stance_readiness"],
        "factual_axes": record["factual_axes"],
        "deterministic_research_inference": record["deterministic_research_inference"],
        "warnings": record["warnings_counter_thesis"]["warnings"],
        "counterbalancing_context": record.get("counterbalancing_context") or [],
        "confirmation_status": (record.get("confirmation_boundary") or {}).get("status"),
        "confirmation_trigger_state": (record.get("confirmation_boundary") or {}).get("confirmation_trigger_state"),
        "technical_invalidation_status": (record.get("technical_invalidation") or {}).get("status"),
        "fundamental_invalidation_status": (record.get("fundamental_invalidation") or {}).get("status"),
        "counter_thesis_present": bool(record.get("key_counter_thesis")),
        "portfolio_availability": record["factual_axes"].get("portfolio_availability"),
        "authority_boundary": record["authority_boundary"],
    }
