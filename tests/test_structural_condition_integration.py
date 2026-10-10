import pytest

import stocklookup_core.decision.integrated_investment_decision_product as product
import stocklookup_core.tactical.market_structure_breakout_product_projection as projection
import prospective_decision_retention as retention
import prospective_decision_outcome_feedback as feedback
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery


def projected(*, bearish=False):
    return projection._project_ticker("TEST", {
        "eligibility": {"status": "ELIGIBLE"},
        "bos_context": {"bos_state": "BEARISH_BOS_DETECTED_BY_RULE" if bearish else "BULLISH_BOS_DETECTED_BY_RULE"},
        "trigger_context": {"status": "AVAILABLE", "trigger_type": "CONFIRMED_BOS_TRIGGER", "trigger_level": 100.0, "trigger_state": "TRIGGERED"},
        "invalidation_context": {"status": "AVAILABLE", "invalidation_level": 110.0 if bearish else 90.0,
                                 "invalidation_method": "CONFIRMED_SWING_HIGH_BY_RULE_OR_V1_RESISTANCE_FALLBACK" if bearish else "CONFIRMED_SWING_LOW_BY_RULE_OR_V1_SUPPORT_FALLBACK"},
    }, "2026-09-30")


@pytest.mark.parametrize("bearish,trigger_op,invalidation_op", [(False, ">", "<"), (True, "<", ">")])
def test_preserves_producer_direction_method_and_fixed_levels(bearish, trigger_op, invalidation_op):
    record = projected(bearish=bearish)
    for role, operator in [("trigger", trigger_op), ("invalidation", invalidation_op)]:
        condition = retention.serialize_structural_condition(record, role=role, session="2026-09-30", source_identity="projection:verified")
        assert condition["status"] == "MACHINE_EVALUABLE"
        assert condition["operator"] == operator
        assert condition["reference_level"] == record[f"{role}_level"]
        assert condition["source_strategy_identity"] == "projection:verified"
        assert condition["source_lineage"]["as_of_session"] == "2026-09-30"
    assert record["invalidation_method"] in retention.serialize_structural_condition(
        record, role="invalidation", session="2026-09-30", source_identity="projection:verified"
    )["source_boundary_type"]


@pytest.mark.parametrize("patch", [
    {"as_of_session": "2026-09-29"}, {"as_of_session": "2026-10-01"},
    {"eligible": False}, {"trigger_level": None}, {"trigger_level": float("nan")},
    {"trigger_level": float("inf")}, {"trigger_level": True}, {"trigger_level": -1},
    {"trigger_close_comparison_operator": None},
])
def test_unqualified_dependent_condition_fails_closed(patch):
    record = projected(); record.update(patch)
    condition = retention.serialize_structural_condition(record, role="trigger", session="2026-09-30", source_identity="projection:verified")
    assert condition["status"] == "NOT_MACHINE_EVALUABLE"
    assert condition["reference_level"] is None
    assert "STRUCTURAL_CONDITION_INPUT_UNQUALIFIED" in condition["reason_codes"]


def test_missing_identity_and_unknown_source_semantics_fail_closed():
    record = projected()
    assert retention.serialize_structural_condition(record, role="trigger", session="2026-09-30", source_identity=None)["status"] == "NOT_MACHINE_EVALUABLE"
    record["invalidation_close_comparison_operator"] = None
    assert retention.serialize_structural_condition(record, role="invalidation", session="2026-09-30", source_identity="projection:verified")["status"] == "NOT_MACHINE_EVALUABLE"


def test_watchlist_condition_cannot_replace_structural_level_or_posture():
    kwargs = dict(ticker="TEST", as_of_session="2026-09-30", tactical_record=projected(),
                  financial_record=None, valuation_record=None, relative_volume_record=None,
                  market_sector_record=None, producer_artifact_identities={"technical_structure": "projection:verified"},
                  structural_condition_source_identity="projection:verified")
    original = product.build_ticker_integrated_decision(**kwargs)
    boundary = {"status": "READY", "source_metric": "resistance", "comparison_operator": "FUTURE_CLOSE_GT_RESISTANCE_LEVEL", "baseline_value": 777.0}
    changed = product.build_ticker_integrated_decision(**kwargs, tactical_boundaries_record={"confirmation_boundary": boundary}, tactical_boundaries_identity="watchlist:verified")
    assert changed["trigger"]["condition"]["reference_level"] == changed["trigger"]["trigger_level"] == 100.0
    assert changed["trigger"]["watchlist_condition"]["reference_level"] == 777.0
    assert changed["research_action_posture"] == original["research_action_posture"]
    assert changed["trigger"]["condition"]["condition_identity"] == original["trigger"]["condition"]["condition_identity"]


def test_existing_close_evaluator_observes_bearish_direction_without_new_engine():
    condition = retention.serialize_structural_condition(projected(bearish=True), role="trigger", session="2026-09-30", source_identity="projection:verified")
    result = retention.evaluate_serialized_close_condition(condition=condition, ticker="TEST", start_session="2026-09-30",
        chain=["2026-09-30", "2026-10-01"], snapshots={"2026-10-01": {"records": {"TEST": {"observations": [{"session": "2026-10-01", "close": 99.0}]}}}})
    assert result["status"] == "SATISFIED"


@pytest.mark.parametrize("value", [True, False, float("inf"), float("-inf"), float("nan"), 0, -1])
def test_close_evaluator_rejects_unqualified_numeric_observations(value):
    condition = retention.serialize_structural_condition(projected(), role="trigger", session="2026-09-30", source_identity="projection:verified")
    result = retention.evaluate_serialized_close_condition(condition, ticker="TEST", start_session="2026-09-30",
        chain=["2026-09-30", "2026-10-01"], snapshots={"2026-10-01": {"records": {"TEST": {"observations": [{"session": "2026-10-01", "close": value}]}}}})
    assert result["status"] == "PRICE_SERIES_UNQUALIFIED"
    assert result["event_session"] is None


@pytest.mark.parametrize("value", [True, float("inf"), float("nan"), 0, -1])
def test_close_evaluator_does_not_trust_a_machine_evaluable_label(value):
    condition = retention.serialize_structural_condition(projected(), role="trigger", session="2026-09-30", source_identity="projection:verified")
    condition["reference_level"] = value
    result = retention.evaluate_serialized_close_condition(condition, ticker="TEST", start_session="2026-09-30",
        chain=["2026-09-30", "2026-10-01"], snapshots={})
    assert result["status"] == "NOT_MACHINE_EVALUABLE"
    legacy = retention.serialize_boundary_condition({"status": "READY", "source_metric": "resistance",
        "comparison_operator": "FUTURE_CLOSE_GT_RESISTANCE_LEVEL", "baseline_value": value},
        role="trigger", source_strategy_identity="watchlist:verified")
    assert legacy["status"] == "NOT_MACHINE_EVALUABLE"


@pytest.mark.parametrize("start", ["2026-09-29", "2026-10-01"])
def test_structural_condition_cannot_be_rebased_to_a_different_t0(start):
    condition = retention.serialize_structural_condition(projected(), role="trigger", session="2026-09-30", source_identity="projection:verified")
    result = retention.evaluate_serialized_close_condition(condition, ticker="TEST", start_session=start,
        chain=["2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"], snapshots={
            day: {"records": {"TEST": {"observations": [{"session": day, "close": 101.0}]}}}
            for day in ["2026-09-30", "2026-10-01", "2026-10-02"]})
    assert result["status"] == "TEMPORAL_PROVENANCE_UNQUALIFIED"
    assert result["reason_codes"] == ["STRUCTURAL_CONDITION_T0_SESSION_MISMATCH"]
    assert result["event_session"] is None


def test_invalid_close_blocks_only_that_observation():
    condition = retention.serialize_structural_condition(projected(), role="trigger", session="2026-09-30", source_identity="projection:verified")
    result = retention.evaluate_serialized_close_condition(condition, ticker="TEST", start_session="2026-09-30",
        chain=["2026-09-30", "2026-10-01", "2026-10-02"], snapshots={
            day: {"records": {"TEST": {"observations": [{"session": day, "close": close}]}}}
            for day, close in [("2026-10-01", float("inf")), ("2026-10-02", 101.0)]})
    assert result["status"] == "SATISFIED"
    assert result["event_session"] == "2026-10-02"


def test_feedback_preserves_temporal_blocker_without_an_outcome_event():
    condition = retention.serialize_structural_condition(projected(), role="trigger", session="2026-09-30", source_identity="projection:verified")
    result = feedback._trigger_invalidation({"ticker": "TEST", "as_of_session": "2026-09-29", "trigger": {"condition": condition}},
        chain=["2026-09-29", "2026-09-30"], snapshots={"2026-09-30": {"records": {"TEST": {"observations": [{"session": "2026-09-30", "close": 101.0}]}}}})
    assert result["trigger"]["status"] == "TEMPORAL_PROVENANCE_UNQUALIFIED"
    assert result["trigger"]["event_session"] is None
    assert result["invalidation"]["status"] == "NOT_MACHINE_EVALUABLE"
    assert result["authority_boundary"] == "SERIALIZED_EXISTING_STRATEGY_CONDITIONS_NOT_TRADE_EXECUTION"


@pytest.mark.parametrize("tamper", [None, "identity", "session", "contract"])
def test_artifact_qualification_blocks_only_structural_condition(tamper):
    source = {"contract_version": projection.CONTRACT_VERSION, "session": "2026-09-30", "records": {"TEST": projected()}}
    source.update(projection.content_identity(source))
    if tamper == "identity":
        source["records"]["TEST"]["trigger_level"] = 999.0
    elif tamper == "session":
        source["session"] = "2026-10-01"
        source.update(projection.content_identity(source))
    elif tamper == "contract":
        source["contract_version"] = "unqualified_provider_proxy/v1"
        source.update(projection.content_identity(source))
    result = product.build_artifact(session="2026-09-30", requested_at="fixed", technical_structure_artifact=source)
    assert set(result["records"]) == {"TEST"}
    condition = result["records"]["TEST"]["trigger"]["condition"]
    assert condition["status"] == ("MACHINE_EVALUABLE" if tamper is None else "NOT_MACHINE_EVALUABLE")
    assert result["records"]["TEST"]["exact_capabilities_unavailable"]


def test_unknown_invalidation_method_does_not_inherit_a_direction():
    record = projection._project_ticker("TEST", {
        "eligibility": {"status": "ELIGIBLE"},
        "invalidation_context": {"status": "AVAILABLE", "invalidation_level": 90.0, "invalidation_method": "UNKNOWN"},
    }, "2026-09-30")
    assert record["invalidation_level"] == 90.0
    assert record["invalidation_close_comparison_operator"] is None


@pytest.mark.parametrize("bearish", [False, True])
def test_delivery_preserves_conditions_and_non_evaluable_watchlist_verbatim(bearish):
    record = projected(bearish=bearish)
    decision = product.build_ticker_integrated_decision(
        ticker="TEST", as_of_session="2026-09-30", tactical_record=record,
        financial_record=None, valuation_record=None, relative_volume_record=None, market_sector_record=None,
        structural_condition_source_identity="projection:verified",
        tactical_boundaries_record={"confirmation_boundary": {"status": "CONDITIONAL", "warnings": ["MULTI_SIGNAL_RULE_NOT_REDUCED_TO_A_SINGLE_THRESHOLD"]}})
    view = project_integrated_decision_for_ai_delivery(decision, integrated_identity="product:verified")
    for role in ["trigger", "invalidation"]:
        assert view[role]["condition"] == decision[role]["condition"]
        assert view[role]["watchlist_condition"] == decision[role]["watchlist_condition"]
    assert view["trigger"]["watchlist_condition"]["status"] == "NOT_MACHINE_EVALUABLE"
    assert view["is_actionable"] is False
    view["trigger"]["condition"]["reason_codes"].append("local")
    assert "local" not in decision["trigger"]["condition"]["reason_codes"]
