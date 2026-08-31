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
WEAK_FUNDAMENTAL = frozenset({"LOSS_MAKING", "BREAK_EVEN", "INSUFFICIENT_DATA", "UNAVAILABLE"})


def _triggered(boundary: Mapping[str, Any] | None) -> bool:
    if not isinstance(boundary, Mapping):
        return False
    return boundary.get("current_trigger_state") == "TRIGGERED" or boundary.get("status") == "TRIGGERED"


def infer_research_stance(opportunity: Mapping[str, Any]) -> dict[str, Any]:
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
    relative = (valuation.get("peer_relative_context") or {}).get("relative_research_state")
    profit_state = fundamental.get("state") if fund_usable else None
    weak_fundamental = (not fund_usable) or profit_state in WEAK_FUNDAMENTAL or fundamental.get("trajectory") in {
        "TURNED_TO_LOSS", "LOSS_WIDENED",
    }

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

    if entry_state in CONSTRUCTIVE and weak_fundamental:
        reasons.append("CONSTRUCTIVE_TACTICAL_WITH_WEAK_OR_LOSS_FUNDAMENTAL")
        return _stance(HIGH_RISK, reasons, warnings, entry_state, entry_action)

    if entry_state == "EARLY_REVERSAL_CANDIDATE":
        reasons.append("EARLY_REVERSAL_CANDIDATE")
        if relative == "ATTRACTIVE_RELATIVE_RESEARCH":
            reasons.append("ATTRACTIVE_RELATIVE_RESEARCH")
        return _stance(INITIATE, reasons, warnings, entry_state, entry_action)

    if entry_state == "BREAKOUT_READY":
        if confirmation.get("status") == "READY":
            reasons.append("BREAKOUT_READY_CONFIRMATION_READY")
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
        reasons.append("TACTICAL_AXIS_NOT_CURRENT")
        return _stance(INSUFFICIENT_EVIDENCE, reasons, warnings, None, None)

    reasons.append("NO_MAPPED_RESEARCH_STANCE")
    return _stance(INSUFFICIENT_EVIDENCE, reasons, warnings, entry_state, entry_action)


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
            "relative_valuation": (valuation.get("peer_relative_context") or {}).get("relative_research_state"),
        },
        "warnings_counter_thesis": {
            "warnings": inference["warnings"],
            "counter_thesis": downside.get("thesis_conflict") or [],
        },
        "confirmation_boundary": confirmation,
        "technical_invalidation": (tactical.get("invalidation") if tactical.get("research_usable") else None)
            or downside.get("technical") or {"status": "UNAVAILABLE"},
        "fundamental_invalidation": downside.get("fundamental") or {"status": "UNAVAILABLE"},
        "key_counter_thesis": downside.get("thesis_conflict") or [],
        "per_axis_freshness": (opportunity.get("data_authority") or {}).get("per_axis_freshness") or {},
        "authority_boundary": {
            "is_actionable": False, "research_support_not_execution": True,
            "no_score": True, "no_rank": True, "no_probability": True, "no_target_price": True,
            "security_attractiveness_separate_from_portfolio_fit": True,
            "exact_execution_capacity_is_not_a_wait_gate": True,
            "historical_pit_is_not_a_wait_gate": True,
        },
    }


def compact_decision(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ticker": record["ticker"], "as_of_session": record["as_of_session"],
        "entry_state": record["entry_state"], "entry_action": record["entry_action"],
        "research_stance": record["research_stance"],
        "research_stance_readiness": record["research_stance_readiness"],
        "factual_axes": record["factual_axes"],
        "deterministic_research_inference": record["deterministic_research_inference"],
        "warnings": record["warnings_counter_thesis"]["warnings"],
        "confirmation_status": (record.get("confirmation_boundary") or {}).get("status"),
        "technical_invalidation_status": (record.get("technical_invalidation") or {}).get("status"),
        "fundamental_invalidation_status": (record.get("fundamental_invalidation") or {}).get("status"),
        "counter_thesis_present": bool(record.get("key_counter_thesis")),
        "portfolio_availability": record["factual_axes"].get("portfolio_availability"),
        "authority_boundary": record["authority_boundary"],
    }
