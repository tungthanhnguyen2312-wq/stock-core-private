"""Coverage spine contracts. Fixtures are generic; focus tickers are labels only."""
from __future__ import annotations

from pathlib import Path

import pytest

import decision_intelligence_coverage_calibration as spine
import decision_outcome_calibration_review as review
import historical_temporal_research_panel as panel
import stocklookup_core.decision.human_ai_decision_evidence_packet as packet
import stocklookup_core.portfolio.portfolio_research_decision_workbench as workbench


def _member(ticker, **overrides):
    member = {
        "ticker": ticker,
        "universe": {"ticker": ticker, "activity_and_session_state": "ACTIVE_LISTED_OBSERVED"},
        "technical": {"is_current_session": True, "has_exact_session_bar": True, "technical_status": "SHADOW_ONLY"},
        "valuation": {},
        "corporate_intelligence": {},
        "events": [],
    }
    member.update(overrides)
    return member


def test_canonical_denominator_is_complete_and_stable():
    members = [_member(f"T{index:04d}") for index in range(spine.CANONICAL_DENOMINATOR)]
    built = spine.build_coverage_index("2026-10-06", members)
    spine.require_canonical_denominator(built)
    assert built["summary"]["denominator"] == 1683
    assert built["summary"]["counts"]["missing"] == 1683
    again = spine.build_coverage_index("2026-10-06", list(reversed(members)))
    assert built["index_identity"] == again["index_identity"]
    assert [row["ticker"] for row in built["rows"]] == sorted(row["ticker"] for row in built["rows"])


def test_denominator_cannot_shrink_to_the_supplied_subset():
    built = spine.build_coverage_index("2026-10-06", [_member("AAA"), _member("BBB")])
    assert built["denominator"] == 2
    assert built["canonical_denominator_met"] is False
    with pytest.raises(ValueError):
        spine.require_canonical_denominator(built)
    with pytest.raises(ValueError):
        spine.summarize_coverage(built["rows"], denominator=1507)


def test_stale_technical_is_not_labeled_current_and_absence_is_unknown():
    stale = spine.project_member("AAA", "2026-10-06", technical={"is_current_session": False, "feature_as_of_session": "2026-09-30"})
    absent = spine.project_member("BBB", "2026-10-06")
    assert stale["technical_status"] == "STALE"
    assert stale["price_evidence_status"] == "STALE"
    assert absent["corporate_intelligence_status"] == "UNKNOWN"
    assert absent["current_event_status"] == "UNKNOWN"
    assert absent["fundamental_evidence_status"] == "UNKNOWN"


def test_financial_and_event_dates_do_not_lookahead():
    assert spine.refuse_lookahead("2026-09-08", "2026-10-06") is True
    refused = spine.project_corporate_action({"knowledge_date": "2026-10-06", "lifecycle": "EXECUTED", "event_type": "ISSUANCE"}, "2026-09-08")
    assert refused["reason"] == "LOOKAHEAD_KNOWLEDGE_DATE"
    assert refused["executed"] is False
    planned = spine.project_corporate_action({"lifecycle": "PLANNED", "event_type": "ISSUANCE", "announcement_date": "2026-09-01", "ex_date": None}, "2026-09-08")
    assert planned["executed"] is False
    assert planned["planned_shares_converted_to_executed"] is False
    assert planned["ex_date_inferred"] is False
    assert planned["event_date"] is None


def test_share_basis_and_denominator_conflicts_stay_blocked():
    row = spine.project_member(
        "AAA",
        "2026-10-06",
        valuation={
            "entity_class": "securities",
            "financial_input": {"authority": "PROVIDER_RESEARCH"},
            "share_basis_input": {"status": "QUALIFIED_OFFICIAL", "authority": "qualified_official", "blocked_reasons": ["CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION"]},
            "metrics": {"P/E": {"status": "BLOCKED", "blocked_reasons": ["INCONSISTENT_DENOMINATOR"], "labels": ["CURRENT_RESEARCH_ONLY"]}},
        },
    )
    assert row["provider_research_financial"] is True
    assert row["official_current_financial"] is False
    assert row["share_basis_blocked"] is True
    assert row["denominator_conflict"] is True
    assert row["specialist_sector_status"] == "CURRENT"
    assert row["valuation_strict_ready"] is False
    assert "SPECIALIST_SECTOR_VALUATION_SEMANTICS" in spine.research_distinction(row)
    assert "SHARE_BASIS_CONFLICT_RETAINED" in spine.research_distinction(row)


def test_research_usable_multiple_is_not_strict():
    row = spine.project_member(
        "AAA",
        "2026-10-06",
        valuation={
            "entity_class": "corporate",
            "financial_input": {"authority": "OFFICIAL_QUALIFIED"},
            "metrics": {"P/E": {"status": "RESEARCH_USABLE", "financial_period": "2024", "labels": ["CURRENT_RESEARCH_ONLY"]}},
        },
    )
    assert row["valuation_research_usable"] is True
    assert row["valuation_strict_ready"] is False
    assert row["valuation_status"] == "PROXY"
    assert row["fundamental_evidence_status"] == "CURRENT"
    assert row["fundamental_knowledge_status"] == "UNKNOWN"


def test_old_t0_missing_axes_stay_distinct_from_retained_axes():
    missing = review.project_explanatory_axes({
        "evidence_axes": {"status": "FIELD_NOT_RETAINED_AT_T0", "axis_states": {}},
        "trigger": {"warning": "TRIGGER_IS_RESEARCH_MEASUREMENT_NOT_EXECUTION_AUTHORITY", "trigger_state": None},
        "invalidation": {"warning": "STRUCTURAL_INVALIDATION_LEVEL_NOT_A_STOP_LOSS"},
    })
    assert missing["retention"] == "FEATURES_NOT_RETAINED_AT_T0"
    assert missing["warning_codes"] is None
    assert missing["supportive_features_present"] is None
    assert missing["authority_disclaimer_codes"]
    retained = review.project_explanatory_axes({
        "market_sector_state": "MIXED_BREADTH",
        "evidence_axes": {"status": "RETAINED", "axis_states": {
            "MOMENTUM": {"state": "ELIGIBLE"},
            "TACTICAL_STRUCTURE": {"state": "DISTRIBUTION_RISK"},
        }},
        "feedback_taxonomy": {"confirmation_status": "BOUNDARY_NOT_EVALUABLE"},
        "trigger": {"trigger_state": "BELOW_TRIGGER", "warning": "TRIGGER_IS_RESEARCH_MEASUREMENT_NOT_EXECUTION_AUTHORITY"},
    })
    assert retained["retention"] == "RETAINED"
    assert retained["supportive_feature_families"] == ["MOMENTUM"]
    assert retained["adverse_feature_families"] == ["TACTICAL_STRUCTURE"]
    assert retained["warning_codes"] == ["TACTICAL_STRUCTURE"]
    assert "lineage" not in str(retained["axis_states"])


def test_outcome_namespace_does_not_rewrite_the_decision_outcome():
    observation = {"session": "2026-09-08", "ticker": "AAA", "tactical_state": "BASE_BUILDING", "semantic_tier": panel.RECONSTRUCTED_RESEARCH}
    built = panel.build_panel([observation])
    original_outcome = built["rows"][0]["fields"]["outcome"]["status"]
    overlay = {
        ("2026-09-08", "AAA"): {
            "decision": {"trigger": {"value": None, "tier": "UNKNOWN", "status": "NOT_RETAINED_AT_T0"}},
            "outcomes": [{"horizon": 5, "tier": "PROSPECTIVE_GENUINE", "forward_return": 0.02, "maturity_status": "MATURE"}],
        }
    }
    enriched = panel.enrich_panel(built, overlay)
    row = enriched["rows"][0]
    assert row["row_identity"] == built["rows"][0]["row_identity"]
    assert row["semantic_tier"] == panel.RECONSTRUCTED_RESEARCH
    assert row["fields"]["outcome"]["status"] == original_outcome
    assert row["fields"]["trigger"]["status"] == "NOT_RETAINED_AT_T0"
    assert row["outcome_namespace"]["outcomes"][0]["tier"] == "PROSPECTIVE_GENUINE"
    assert row["outcome_namespace"]["separated_from_decision"] is True


def test_matched_control_edge_waits_for_every_gate():
    rows = []
    for session_index in range(8):
        for item in range(40):
            rows.append({
                "population": review.PROSPECTIVE_GENUINE,
                "source_type": "IMMUTABLE_INTEGRATED_T0",
                "session": f"2026-08-{session_index+1:02d}",
                "ticker": f"S{session_index}-{item}",
                "posture": "EARLY_REVERSAL",
                "tactical_state": "EARLY_REVERSAL_CANDIDATE",
                "regime": "MIXED_BREADTH",
                "horizon": 5,
                "status": review.MATURE,
                "forward_return": 0.04,
                "mfe": 0.05,
                "mae": -0.01,
                "warnings": ["DISTRIBUTION_RISK"],
                "supportive_features_present": True,
            })
            rows.append({
                "population": review.PROSPECTIVE_GENUINE,
                "source_type": "IMMUTABLE_INTEGRATED_T0",
                "session": f"2026-08-{session_index+1:02d}",
                "ticker": f"C{session_index}-{item}",
                "posture": "WAIT",
                "tactical_state": "UNCLASSIFIED",
                "regime": "MIXED_BREADTH",
                "horizon": 5,
                "status": review.MATURE,
                "forward_return": 0.01,
                "warnings": [],
                "supportive_features_present": False,
            })
    built = review.review_observations(rows)
    setup = next(item for item in built["cohorts"] if item["posture"] == "EARLY_REVERSAL")
    assert setup["control_readiness"]["state"] == "CONTROL_READY"
    assert setup["control_readiness"]["edge"] == 0.03
    assert built["qualified_control_edges"] == 1
    withheld = review.review_observations([{
        "population": review.PROSPECTIVE_GENUINE,
        "source_type": "IMMUTABLE_INTEGRATED_T0",
        "session": "2026-09-03",
        "ticker": "AAA",
        "posture": "EARLY_REVERSAL",
        "tactical_state": "EARLY_REVERSAL_CANDIDATE",
        "regime": None,
        "horizon": 5,
        "status": review.MATURE,
        "forward_return": -0.02,
        "warnings": None,
        "supportive_features_present": None,
        "outcome_label": "FAILED_BREAKOUT",
    }])
    cohort = withheld["cohorts"][0]
    assert cohort["control_readiness"]["state"] == "FEATURES_NOT_RETAINED"
    assert cohort["control_readiness"]["edge"] is None
    assert withheld["explanation"]["false_positive_explainable"] == 0
    assert withheld["explanation"]["policy_threshold_introduced"] is False
    explained = dict(withheld["cohorts"][0])
    del explained
    positive = review.review_observations([{
        "population": review.PROSPECTIVE_GENUINE,
        "source_type": "IMMUTABLE_INTEGRATED_T0",
        "session": "2026-09-03",
        "ticker": "AAA",
        "posture": "EARLY_REVERSAL",
        "tactical_state": "EARLY_REVERSAL_CANDIDATE",
        "regime": "MIXED_BREADTH",
        "horizon": 5,
        "status": review.MATURE,
        "forward_return": -0.02,
        "mae": -0.04,
        "warnings": ["DISTRIBUTION_RISK"],
        "supportive_features_present": False,
        "outcome_label": "FAILED_BREAKOUT",
    }, {
        "population": review.PROSPECTIVE_GENUINE,
        "source_type": "IMMUTABLE_INTEGRATED_T0",
        "session": "2026-09-03",
        "ticker": "BBB",
        "posture": "WAIT",
        "tactical_state": "UNCLASSIFIED",
        "regime": "MIXED_BREADTH",
        "horizon": 5,
        "status": review.MATURE,
        "forward_return": 0.03,
        "mfe": 0.05,
        "warnings": [],
        "supportive_features_present": True,
    }])
    assert positive["explanation"]["false_positive_explainable"] == 1
    assert positive["explanation"]["false_negative_explainable"] == 1


def test_packet_states_the_missing_analogue_limitation_and_workbench_does_not_size():
    built = packet.build_packet(
        ticker="AAA",
        spine={"retention_limitation": spine.NO_ANALOGUE, "matched_control_readiness": "FEATURES_NOT_RETAINED", "sample_quality": "INSUFFICIENT"},
    )
    assert built["sections"]["history"]["fields"]["retention_limitation"]["value"] == spine.NO_ANALOGUE
    assert built["buy_score"] is None
    assert built["probability"] is None
    assert built["target_price"] is None
    compared = workbench.build_workbench([
        {"ticker": "AAA", "sector": "materials", "evidence_quality": "PARTIAL", "event_risk": "DILUTION_POSSIBLE", "analogue_quality": "NOT_RETAINED"},
        {"ticker": "BBB", "sector": "materials", "evidence_quality": "PARTIAL", "event_risk": "DILUTION_POSSIBLE", "analogue_quality": "RECONSTRUCTED_RESEARCH"},
    ])
    assert compared["evidence_comparison"]["weights"] is None
    assert compared["evidence_comparison"]["leverage"] is None
    assert compared["evidence_comparison"]["event_risk"]["counts"]["DILUTION_POSSIBLE"] == 2
    assert compared["position_size"] is None


def test_uptrend_is_not_relabeled_and_unicode_path_is_explicit(tmp_path: Path):
    row = spine.project_member("AAA", "2026-10-06", technical={"is_current_session": True, "has_exact_session_bar": True})
    row["technical_structure"] = "UPTREND"
    assert "UPTREND_NOT_RELABELED_BOTTOM_FISHING" in spine.research_distinction(row)
    missing = tmp_path / "phiên-bản" / "không-có.json"
    with pytest.raises(FileNotFoundError):
        spine._load_json(missing)


def test_non_recurring_flag_does_not_become_a_cheapness_claim():
    row = {"earnings_quality": "NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE", "valuation_research_usable": True}
    notes = spine.research_distinction(row)
    assert notes == ["NON_RECURRING_DOES_NOT_AUTHORIZE_RECURRING_CHEAPNESS"]
