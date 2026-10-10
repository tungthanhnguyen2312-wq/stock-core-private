import pytest

import technical_structure_context as structure
import stocklookup_core.tactical.market_structure_breakout_product_projection as projection
import stocklookup_core.decision.integrated_investment_decision_product as product
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery


def projected(prior, current, *, market_structure="UPTREND"):
    pivot = {"status": "AVAILABLE", "pivot_price": 100.0}
    breakout = structure._breakout_state_v3([prior, current], pivot)
    bos = {"bos_state": "NO_BOS_DETECTED"}
    return projection._project_ticker("TEST", {
        "eligibility": {"status": "ELIGIBLE"},
        "swing_structure": {"market_structure_state": market_structure},
        "breakout_state_v3": breakout, "bos_context": bos, "pivot_context": pivot,
        "trigger_context": structure._trigger_v3([prior, current], breakout, bos, pivot),
        "invalidation_context": {"status": "AVAILABLE", "invalidation_level": 90.0,
            "invalidation_method": "CONFIRMED_SWING_LOW_BY_RULE_OR_V1_SUPPORT_FALLBACK",
            "distance_to_invalidation_pct": current / 90.0 - 1},
    }, "2026-09-30")


def decision(record):
    return product.build_ticker_integrated_decision(ticker="TEST", as_of_session="2026-09-30",
        tactical_record=record, financial_record=None, valuation_record=None,
        relative_volume_record=None, market_sector_record=None,
        technical_coverage_disposition_record={"has_exact_session_bar": True, "is_current_session": True,
            "feature_as_of_session": "2026-09-30", "disposition": "SAME_SESSION_TECHNICAL_COVERED"},
        structural_condition_source_identity="structure:verified")


@pytest.mark.parametrize("prior", [99.0, 100.0])
def test_approaching_resistance_is_not_a_retest_of_broken_support(prior):
    record = projected(prior, 99.5)
    result = decision(record)
    assert record["breakout_state_v3"] == "TESTING_PIVOT"
    assert record["pivot_retest_confirmed"] is False
    assert result["tactical_phase"] == "BREAKOUT_SETUP"
    assert result["research_action_posture"] == "EARLY_WATCH"
    assert result["trigger"]["condition"]["reference_level"] == 100.0
    assert result["trigger"]["condition"]["operator"] == ">"
    assert result["invalidation"]["condition"]["reference_level"] == 90.0
    assert result["research_action_posture"] != "AVOID"
    assert project_integrated_decision_for_ai_delivery(result)["tactical_phase"] == "BREAKOUT_SETUP"


def test_witnessed_breakout_can_have_a_bounded_retest_with_missing_fundamentals():
    record = projected(101.0, 99.5)
    result = decision(record)
    assert record["pivot_retest_confirmed"] is True
    assert result["tactical_phase"] == "RETEST_AFTER_BREAKOUT"
    assert result["research_action_posture"] == "ACCUMULATE_ON_RETEST"
    assert result["fundamental_state"] == "INSUFFICIENT"


def test_failed_breakout_is_not_a_constructive_retest():
    record = projected(101.0, 95.0)
    result = decision(record)
    assert record["breakout_state_v3"] == "FAILED_BREAKOUT"
    assert record["pivot_retest_confirmed"] is False
    assert result["tactical_phase"] == "DISTRIBUTION_RISK"
    assert result["research_action_posture"] == "WAIT_FOR_CONFIRMATION"


def test_missing_prior_witness_cannot_be_replaced_by_a_trigger_name():
    record = projected(99.0, 99.5)
    record.pop("pivot_retest_confirmed")
    record["trigger_type"] = "RETEST_BROKEN_PIVOT"
    assert decision(record)["tactical_phase"] == "BREAKOUT_SETUP"
    assert decision(record)["research_action_posture"] == "EARLY_WATCH"


def test_downtrend_with_a_recent_pivot_test_does_not_gain_accumulation_authority():
    assert decision(projected(101.0, 99.5, market_structure="DOWNTREND"))["research_action_posture"] == "AVOID"


@pytest.mark.parametrize("prior", [None, False, "True"])
def test_projection_requires_a_qualified_boolean_witness(prior):
    record = projection._project_ticker("TEST", {"breakout_state_v3": {
        "status": "AVAILABLE", "breakout_state": "TESTING_PIVOT", "prior_close_above_pivot": prior}}, "2026-09-30")
    assert record["pivot_retest_confirmed"] is False


def test_bearish_bos_trigger_is_opposing_evidence_not_breakout_support():
    record = projected(99.0, 95.0, market_structure="DOWNTREND")
    record.update(bos_state="BEARISH_BOS_DETECTED_BY_RULE", trigger_type="CONFIRMED_BOS_TRIGGER", trigger_state="TRIGGERED")
    result = decision(record)
    axis = result["evidence_axes"]["TACTICAL_STRUCTURE"]
    assert "TRIGGER_FIRED_CONFIRMED_BOS_TRIGGER" not in axis["supporting_reason_codes"]
    assert "BEARISH_BOS_TRIGGER_FIRED" in axis["contradicting_reason_codes"]
    assert "BEARISH_BOS_TRIGGER_FIRED" in result["counter_thesis"]
    assert result["research_action_posture"] == "AVOID"
    assert project_integrated_decision_for_ai_delivery(result)["counter_thesis"] == result["counter_thesis"]


def test_bullish_bos_trigger_retains_its_positive_support():
    record = projected(99.0, 100.0)
    record.update(bos_state="BULLISH_BOS_DETECTED_BY_RULE", trigger_type="CONFIRMED_BOS_TRIGGER", trigger_state="TRIGGERED")
    phase, support, counter = product.evaluate_tactical_phase(record)
    assert phase == "BREAKOUT_CONFIRMED"
    assert "TRIGGER_FIRED_CONFIRMED_BOS_TRIGGER" in support
    assert "BEARISH_BOS_TRIGGER_FIRED" not in counter
