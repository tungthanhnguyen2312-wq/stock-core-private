from __future__ import annotations

import inspect

import fundamental_market_opportunity_ranking as ranking
import market_wide_current_fundamental_research as consumer


def _axis(score: float | None):
    return {"axis_status": "READY_RESEARCH_ONLY" if score is not None else "INSUFFICIENT_INPUTS", "score": score}


def _fundamental(*, entity_class="corporate", quality=0.9, growth=None, confidence=0.1):
    return {
        "entity_class": entity_class,
        "axes": {
            "PROFITABILITY_QUALITY": _axis(quality),
            "CAPITAL_EFFICIENCY": _axis(quality),
            "BALANCE_SHEET_TRAJECTORY": _axis(quality),
            "GROWTH_MOMENTUM": _axis(growth),
        },
        "data_confidence": {"status": "READY_RESEARCH_ONLY", "score": confidence},
    }


def _market():
    return {"session": "2026-08-25", "records": {
        "GOOD": {"trend_state": "ABOVE_MA20", "technical_features": {"status": "SHADOW_ONLY", "is_current_session": True, "feature_as_of_session": "2026-08-25", "values": {"momentum_20d": 0.1}}},
        "WEAK": {"trend_state": "AT_OR_BELOW_MA20", "technical_features": {"status": "SHADOW_ONLY", "is_current_session": True, "feature_as_of_session": "2026-08-25", "values": {"momentum_20d": -0.1}}},
        "BANK": {"trend_state": "ABOVE_MA20", "technical_features": {"status": "SHADOW_ONLY", "is_current_session": True, "feature_as_of_session": "2026-08-25", "values": {"momentum_20d": 0.1}}},
        "LOW": {"trend_state": "ABOVE_MA20", "technical_features": {"status": "SHADOW_ONLY", "is_current_session": True, "feature_as_of_session": "2026-08-25", "values": {"momentum_20d": 0.1}}},
    }}


def _tactical():
    return {"session": "2026-08-25", "records": {
        "GOOD": {"entry_state": "BREAKOUT_READY", "ticker_structure_state": "ABOVE_MA20_MOMENTUM_POSITIVE", "rule_id": "R2"},
        "WEAK": {"entry_state": "DOWNTREND", "ticker_structure_state": "BELOW_MA20_MOMENTUM_NEGATIVE", "rule_id": "R7"},
        "BANK": {"entry_state": "BREAKOUT_READY", "ticker_structure_state": "ABOVE_MA20_MOMENTUM_POSITIVE", "rule_id": "R2"},
        "LOW": {"entry_state": "BREAKOUT_READY", "ticker_structure_state": "ABOVE_MA20_MOMENTUM_POSITIVE", "rule_id": "R2"},
    }}


def _valuation():
    return {"records": {
        "GOOD": {"price_session": "2026-08-21", "relative_value_axis": {"axis_status": "READY_RESEARCH_ONLY", "score": 0.8}, "market_cap_size_context": {"status": "READY"}, "enterprise_value_size_context": {"status": "INSUFFICIENT_INPUTS"}, "metrics": {}},
        "WEAK": {"price_session": "2026-08-21", "relative_value_axis": {"axis_status": "INSUFFICIENT_INPUTS", "score": None}, "market_cap_size_context": {"status": "READY"}, "enterprise_value_size_context": {"status": "READY"}, "metrics": {}},
    }}


def _artifact():
    return ranking.build_artifact(
        fundamental={"records": {"GOOD": _fundamental(growth=None, confidence=0.05), "WEAK": _fundamental(growth=None, confidence=0.99), "BANK": _fundamental(entity_class="bank"), "LOW": _fundamental(quality=0.1), "MID": _fundamental(quality=0.5)}},
        market=_market(), tactical=_tactical(), valuation=_valuation(),
    )


def test_optional_valuation_and_growth_do_not_block_or_impute_neutral():
    record = _artifact()["records"]["WEAK"]
    assert record["fundamental_quality"]["status"] == "READY_RESEARCH_ONLY"
    assert record["fundamental_quality"]["rank"] == 0.9
    assert record["relative_value"]["status"] == "INSUFFICIENT_INPUTS"
    assert record["relative_value"]["relative_value_rank"] is None
    assert "RELATIVE_VALUE" in record["missing_dimensions"]


def test_high_quality_weak_market_is_distinct_and_negative_state_is_preserved():
    records = _artifact()["records"]
    assert records["GOOD"]["opportunity_research_priority"]["bucket"] == "HIGH_QUALITY_STRONG_SETUP"
    assert records["WEAK"]["opportunity_research_priority"]["bucket"] == "HIGH_QUALITY_WEAK_SETUP"
    assert records["WEAK"]["tactical_setup"]["state"] == "DOWNTREND"


def test_confidence_and_size_context_do_not_raise_relative_value_or_bucket():
    records = _artifact()["records"]
    assert records["WEAK"]["data_confidence"]["score"] > records["GOOD"]["data_confidence"]["score"]
    assert records["WEAK"]["relative_value"]["relative_value_rank"] is None
    assert records["WEAK"]["opportunity_research_priority"]["bucket"] == "HIGH_QUALITY_WEAK_SETUP"
    assert "VALUE_WITH_CONFIRMATION" in records["GOOD"]["opportunity_lanes"]
    assert "VALUE_WITH_CONFIRMATION" not in records["WEAK"]["opportunity_lanes"]
    assert records["GOOD"]["fundamental_quality"]["axes_used"] == [
        "PROFITABILITY_QUALITY", "CAPITAL_EFFICIENCY", "BALANCE_SHEET_TRAJECTORY"
    ]


def test_sector_gate_session_guard_determinism_and_residual():
    artifact = _artifact()
    assert artifact == _artifact()
    assert artifact["denominator"] == 5 and artifact["residual"] == 0
    assert "CORPORATE_FUNDAMENTAL_COMPARISON_NOT_APPLICABLE" in artifact["records"]["BANK"]["warnings"]
    tactical = _tactical(); tactical["session"] = "2026-08-26"
    try:
        ranking.build_artifact(fundamental={"records": {}}, market=_market(), tactical=tactical, valuation={"records": {}})
    except ValueError as error:
        assert str(error) == "MARKET_TACTICAL_SESSION_MISMATCH"
    else:
        raise AssertionError("expected session mismatch to fail closed")


def test_consumer_attachment_is_optional_and_backward_compatible():
    parameter = inspect.signature(consumer.build_artifact).parameters["opportunity_research_by_ticker"]
    assert parameter.default is None


def test_output_contains_research_buckets_not_actions_or_forecasts():
    serialized = str(_artifact()["records"])
    for prohibited in ("BUY", "SELL", "ACCUMULATE", "target", "probability", "position_size"):
        assert prohibited not in serialized


def test_actual_comparable_cohort_labels_are_explicit_and_warning_only():
    records = _artifact()["records"]
    super_setup = records["GOOD"]["research_classifications"]["SUPER_SETUP_RESEARCH"]
    high_risk = records["LOW"]["research_classifications"]["HIGH_RISK_SPECULATION"]
    assert super_setup["status"] == "PRESENT"
    assert super_setup["ranking_basis"] == "CORPORATE_VALID_FUNDAMENTAL_QUALITY_COHORT_EMPIRICAL_PERCENTILE/v1"
    assert super_setup["comparable_cohort_size"] == 4
    assert high_risk["status"] == "RESEARCH_WARNING"
    assert high_risk["portfolio_action"] == "NOT_EMITTED"
    assert records["BANK"]["research_classifications"]["SUPER_SETUP_RESEARCH"]["status"] == "INSUFFICIENT_INPUTS"
