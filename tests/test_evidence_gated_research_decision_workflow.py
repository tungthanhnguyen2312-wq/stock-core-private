import copy

import pytest

from tools.run_evidence_gated_research_decision_workflow import inputs, run
from evidence_gated_research_decision_workflow import build


def _record(artifact, ticker):
    return next(row for row in artifact["records"] if row["ticker"] == ticker)


def test_full_dated_cohort_is_deterministic_and_evidence_bound():
    first = run()
    second = run()
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["as_of"]["research_session"] == "2026-08-20"
    assert first["as_of"]["membership_count"] == 523
    assert first["coverage"]["membership_count"] == 523
    assert first["coverage"]["official_financial_evidence_presence"] == {"BLOCKED": 510, "ELIGIBLE": 13}
    assert first["coverage"]["fundamental_quality_eligibility"] == {"BLOCKED": 510, "PARTIAL": 13}
    assert first["coverage"]["sector_metric_not_applicable_counts"] == {"bank": 3, "securities": 3}
    assert first["coverage"]["valuation_method_not_applicable_counts"] == {"bank": 3, "securities": 3}
    assert first["coverage"]["by_analytical_dimension"]["liquidity_readiness"] == {"BLOCKED": 523}
    assert first["coverage"]["by_analytical_dimension"]["historical_pit_readiness"] == {"BLOCKED": 523}
    assert first["authority_boundary"]["missing_is_not_zero_or_absence"]
    assert first["authority_boundary"]["recommendation_target_probability_sizing_execution"] == "NOT_EMITTED"
    assert all(row["universe_membership"]["state"] == "INCLUDED" for row in first["records"])
    assert all(row["human_review"]["human_decision_required"] for row in first["records"])


def test_representative_real_cases_separate_evidence_presence_from_sector_applicability():
    artifact = run()
    hpg, ssi, vcb, aaa, fpt, pnj = (_record(artifact, ticker) for ticker in ("HPG", "SSI", "VCB", "AAA", "FPT", "PNJ"))
    assert hpg["analytical_eligibility"]["financial_evidence_depth"]["eligibility"] == "ELIGIBLE"
    assert hpg["analytical_eligibility"]["fundamental_quality"]["eligibility"] == "PARTIAL"
    assert hpg["analytical_eligibility"]["valuation_research"]["eligibility"] == "PARTIAL"
    assert hpg["valuation_state"]["authority"] == "NON_AUTHORITATIVE_RESEARCH_PROXY"
    assert hpg["valuation_state"]["prohibited_interpretation"] == "NOT_AUTHORITATIVE_MARKET_CAP_OR_MULTIPLE"
    assert hpg["research_case"]["CONFLICTING_EVIDENCE"]
    for intermediary in (vcb, ssi):
        assert intermediary["analytical_eligibility"]["financial_evidence_depth"]["eligibility"] == "ELIGIBLE"
        assert intermediary["analytical_eligibility"]["fundamental_quality"]["eligibility"] == "PARTIAL"
        assert intermediary["analytical_eligibility"]["sector_model_applicability"]["eligibility"] == "PARTIAL"
        assert set(intermediary["analytical_eligibility"]["sector_model_applicability"]["details"]["not_applicable_metric_ids"]) == {"cash_flow_to_earnings", "debt_to_equity", "net_debt"}
    assert ssi["valuation_state"]["method_states"]["EV/EBITDA"]["status"] == "NOT_APPLICABLE"
    assert vcb["analytical_eligibility"]["valuation_research"]["eligibility"] == "BLOCKED"
    assert "CORPORATE_ACTION_TIMING_OR_RESULT_UNRESOLVED" in vcb["analytical_eligibility"]["valuation_research"]["reason_codes"]
    for later_official in (fpt, pnj):
        assert later_official["evidence_inventory"]["fundamental_authority"] == "PROVIDER_RESEARCH"
        assert later_official["analytical_eligibility"]["financial_evidence_depth"]["eligibility"] == "ELIGIBLE"
        assert later_official["analytical_eligibility"]["fundamental_quality"]["eligibility"] == "PARTIAL"
    assert aaa["analytical_eligibility"]["financial_evidence_depth"]["eligibility"] == "BLOCKED"
    assert aaa["analytical_eligibility"]["sector_model_applicability"]["eligibility"] == "UNKNOWN"
    assert any(item["classification"] == "ANALYTICAL_DIMENSION_GAP" for item in aaa["research_case"]["UNKNOWN_OR_MISSING"])


def test_strategy_lanes_and_scenario_axis_are_orthogonal_and_forbidden_outputs_stay_forbidden():
    artifact = run()
    row = _record(artifact, "AAN")
    assert row["setup_context"]["orthogonal_to_strategy_lanes"]
    assert "SCENARIO_RESEARCH" not in row["strategy_research_lanes"]
    assert row["source_research_lenses_excluded_from_lane_classification"]["SCENARIO_RESEARCH"]["eligibility"] == "PARTIAL"
    assert row["scenario_axis"]["qualification_status"] == "PARTIAL_EVIDENCE_BOUND_SCENARIO"
    assert row["scenario_axis"]["probability_status"] == "UNQUALIFIED"
    assert "BUY_SELL_HOLD" in row["human_review"]["forbidden_authority"]
    assert "POSITION_SIZE" in row["human_review"]["forbidden_authority"]


def test_missing_evidence_is_not_converted_to_zero_and_session_mismatch_fails_closed():
    values = inputs()
    changed = copy.deepcopy(values)
    for row in changed["events"]["records"]:
        if row["ticker"] == "AAA":
            row["event_facts"] = []
    artifact = build(**changed)
    aaa = _record(artifact, "AAA")
    gap = next(item for item in aaa["research_case"]["UNKNOWN_OR_MISSING"] if item["classification"] == "EVENT_EVIDENCE")
    assert gap["observed_value"] == "UNKNOWN"
    assert "NO_RETAINED_EVENT_EVIDENCE_NOT_NO_EVENT_RISK" in gap["reason_codes"]
    changed = copy.deepcopy(values)
    changed["market"]["research_session"] = "2099-01-01"
    with pytest.raises(ValueError, match="SESSION_MISMATCH:market"):
        build(**changed)
    changed = copy.deepcopy(values)
    changed["official_financial_panel"]["before_after_comparison"]["fundamental_readiness_status"]["after"]["PARTIAL"] = 12
    with pytest.raises(ValueError, match="OFFICIAL_FINANCIAL_PANEL_COVERAGE_MISMATCH"):
        build(**changed)
