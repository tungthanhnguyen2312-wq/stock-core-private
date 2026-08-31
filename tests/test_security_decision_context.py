"""Focused tests for security_decision_context.py's decision-quality corrective pass:

confirmation trigger-state exposure, fundamental missing-vs-observed-weak routing, tactical
missingness routing, deterministic WHY / counter-thesis / counterbalancing-context composition,
and technical-invalidation semantic labeling for adverse (no-thesis) stances.
"""
from __future__ import annotations

from security_decision_context import build_ticker_decision, infer_research_stance

DECISION = "2026-08-28"


def _opportunity(**overrides):
    base = {
        "ticker": "AAA", "as_of_session": DECISION,
        "fundamental": {"research_usable": True, "state": "PROFITABLE", "trajectory": "PROFIT_GROWTH",
                        "readiness": "READY_RESEARCH_PROXY", "research_fitness": "READY", "freshness": {}},
        "tactical": {"research_usable": True, "primary_entry_state": "BREAKOUT_READY", "entry_action": None,
                    "confirmation": {"status": "READY", "boundary_type": "BREAKOUT_EXTENSION_CONFIRMATION",
                                      "comparison_operator": "FUTURE_CLOSE_GT_RESISTANCE_LEVEL", "value": 42.0,
                                      "source_metric": "resistance"},
                    "invalidation": {"status": "READY"}, "setup_tags": [], "freshness": {}},
        "valuation": {"peer_relative_context": {"relative_research_state": "ATTRACTIVE_RELATIVE_RESEARCH"},
                     "share_basis": "CURRENT_SHARE_RESEARCH_PROXY", "earnings_state": None},
        "liquidity": {"readiness": "LIQUIDITY_RESEARCH_PROXY", "exact_execution_capacity_status": "EXECUTION_CAPACITY_EXACT_BLOCKED"},
        "market_sector": {"breadth_regime": None, "sector_relative_context": {}},
        "catalyst": {"status": "NO_QUALIFIED_CATALYST"},
        "downside_invalidation": {"technical": {"status": "READY"}, "fundamental": {"status": "CONDITIONAL"}, "thesis_conflict": []},
        "data_authority": {"per_axis_freshness": {}},
    }
    for key, value in overrides.items():
        base[key] = {**base[key], **value} if isinstance(base.get(key), dict) and isinstance(value, dict) else value
    return base


# ---------------------------------------------------------------------------
# 1. Confirmation semantics: boundary availability/status vs. actual trigger state
# ---------------------------------------------------------------------------

def test_confirmation_boundary_exposes_status_and_trigger_state_as_distinct_fields():
    decision = build_ticker_decision(_opportunity())
    boundary = decision["confirmation_boundary"]
    assert boundary["status"] == "READY"  # instrumentation status, preserved verbatim
    assert boundary["confirmation_trigger_state"] == "NOT_AVAILABLE"  # no evidence the trigger fired
    assert decision["research_stance"] == "WAIT_FOR_CONFIRMATION"


def test_confirmation_boundary_preserves_existing_numeric_fields_verbatim():
    decision = build_ticker_decision(_opportunity())
    boundary = decision["confirmation_boundary"]
    assert boundary["comparison_operator"] == "FUTURE_CLOSE_GT_RESISTANCE_LEVEL"
    assert boundary["value"] == 42.0
    assert boundary["source_metric"] == "resistance"


def test_triggered_confirmation_boundary_reports_triggered_and_initiates():
    opportunity = _opportunity(tactical={"confirmation": {"status": "READY", "current_trigger_state": "TRIGGERED"}})
    decision = build_ticker_decision(opportunity)
    assert decision["confirmation_boundary"]["confirmation_trigger_state"] == "TRIGGERED"
    assert decision["research_stance"] == "INITIATE_RESEARCH_CANDIDATE"


def test_deterministic_research_inference_carries_trigger_state_alongside_status():
    decision = build_ticker_decision(_opportunity())
    inference = decision["deterministic_research_inference"]
    assert inference["confirmation_status"] == "READY"
    assert inference["confirmation_trigger_state"] == "NOT_AVAILABLE"


# ---------------------------------------------------------------------------
# 6b. Technical invalidation semantic: thesis invalidation vs. stance-reconsideration watch
# ---------------------------------------------------------------------------

def test_avoid_new_entry_technical_invalidation_is_labeled_reconsideration_watch_not_thesis_invalidation():
    opportunity = _opportunity(tactical={"primary_entry_state": "DOWNTREND", "research_usable": True,
                                          "invalidation": {"status": "READY"}, "confirmation": {"status": "UNAVAILABLE"}})
    decision = build_ticker_decision(opportunity)
    assert decision["research_stance"] == "AVOID_NEW_ENTRY"
    assert decision["technical_invalidation"]["semantic"] == "STANCE_RECONSIDERATION_WATCH"


def test_non_adverse_stance_technical_invalidation_stays_labeled_thesis_invalidation():
    decision = build_ticker_decision(_opportunity(tactical={"confirmation": {"status": "READY", "current_trigger_state": "TRIGGERED"}}))
    assert decision["research_stance"] == "INITIATE_RESEARCH_CANDIDATE"
    assert decision["technical_invalidation"]["semantic"] == "THESIS_INVALIDATION"


def test_technical_invalidation_boundary_status_preserved_alongside_new_semantic_field():
    decision = build_ticker_decision(_opportunity())
    assert decision["technical_invalidation"]["status"] == "READY"
    assert "semantic" in decision["technical_invalidation"]


# ---------------------------------------------------------------------------
# Counterbalancing context / counter-thesis at the full build_ticker_decision() record level
# ---------------------------------------------------------------------------

def test_full_record_avoid_stance_carries_counterbalancing_context_field():
    opportunity = _opportunity(tactical={"primary_entry_state": "DOWNTREND", "research_usable": True,
                                          "invalidation": {"status": "READY"}, "confirmation": {"status": "UNAVAILABLE"}})
    decision = build_ticker_decision(opportunity)
    # Base fixture is also ATTRACTIVE_RELATIVE_RESEARCH -- both constructive axes show up as
    # counterbalancing context on this tactical-only veto, never diluting the veto reason itself.
    assert decision["counterbalancing_context"] == ["PROFITABLE_FUNDAMENTAL", "ATTRACTIVE_RELATIVE_RESEARCH"]
    assert "PROFITABLE_FUNDAMENTAL" not in decision["deterministic_research_inference"]["reasons"]


def test_full_record_key_counter_thesis_matches_warnings_counter_thesis():
    opportunity = _opportunity(valuation={"peer_relative_context": {"relative_research_state": "EXPENSIVE_RELATIVE_RESEARCH"}},
                               tactical={"confirmation": {"status": "READY", "current_trigger_state": "TRIGGERED"}})
    decision = build_ticker_decision(opportunity)
    assert decision["research_stance"] == "INITIATE_RESEARCH_CANDIDATE"
    assert decision["key_counter_thesis"] == decision["warnings_counter_thesis"]["counter_thesis"]
    assert "EXPENSIVE_RELATIVE_RESEARCH" in decision["key_counter_thesis"]


def test_insufficient_evidence_reason_distinguishes_missing_from_observed_weak():
    missing = infer_research_stance(_opportunity(fundamental={"research_usable": False}))
    assert missing["research_stance"] == "INSUFFICIENT_EVIDENCE"
    assert "CONSTRUCTIVE_TACTICAL_WITH_FUNDAMENTAL_EVIDENCE_UNAVAILABLE" in missing["reasons"]

    observed_weak = infer_research_stance(_opportunity(fundamental={"state": "LOSS_MAKING"}))
    assert observed_weak["research_stance"] == "HIGH_RISK_SPECULATION_ONLY"
    assert "CONSTRUCTIVE_TACTICAL_WITH_OBSERVED_WEAK_OR_LOSS_FUNDAMENTAL" in observed_weak["reasons"]
