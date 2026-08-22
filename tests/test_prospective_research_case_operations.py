import pytest

from analyst_research_workbench import build_current_workbench
from prospective_research_case_operations import COHORT, build_operating_manifest
from tools.run_prospective_research_case_operations import run


def test_real_retained_operating_cohort_is_deterministic_and_stops_at_human_gate():
    first, second = run(), run()
    assert first["manifest_identity"] == second["manifest_identity"]
    assert first["cohort"]["tickers"] == ["HPG", "VCB", "SSI", "AAN", "AAA"]
    assert first["cohort"]["member_count"] == 5
    assert first["cohort"]["source_as_of"]["research_session"] == "2026-08-20"
    assert first["cohort"]["source_as_of"]["membership_count"] == 523
    assert first["durable_creation_gate"] == {
        "status": "HUMAN_REVIEW_REQUIRED", "real_cases_created": 0,
        "prohibited_shortcut": "TEST_FIXTURE_OR_IMPLEMENTATION_APPROVAL_CANNOT_CREATE_A_REAL_CASE",
    }
    assert first["learning_baseline"]["real_durable_case_count"] == 0
    assert first["learning_baseline"]["real_claim_outcome_counts"] == {}


def test_each_real_packet_has_exact_known_at_ai_input_queue_and_future_readiness_without_draft_fabrication():
    manifest = run()
    assert [item["priority"] for item in manifest["human_review_queue"]] == [1, 2, 3, 4, 5]
    for record in manifest["records"]:
        assert record["known_at"]["status"] == "SESSION_BOUND_KNOWN_AT"
        assert record["known_at"]["exact_timestamp"] == "NOT_RETAINED"
        assert record["ai_research_input"]["ai_input_identity"] == record["ai_input_identity"]
        assert record["model_draft_status"] == "MODEL_DRAFT_PENDING"
        assert record["validator_status"] == "NOT_RUN_NO_REAL_MODEL_DRAFT"
        assert record["human_review_status"] == "HUMAN_REVIEW_REQUIRED"
        assert record["durable_case_status"].startswith("NOT_CREATED")
        assert all(item["status"] == "AWAITING_FUTURE_RETAINED_EVIDENCE" for item in record["future_update_readiness"])
        assert record["future_update_readiness"][-1]["permitted_relationships"] == ["DOES_NOT_ADDRESS"]
        assert record["blocked_dimensions"]
    assert manifest["records"][0]["ticker"] == "HPG"
    assert manifest["records"][1]["ticker"] == "VCB"
    assert manifest["records"][2]["ticker"] == "SSI"
    assert manifest["records"][3]["ticker"] == "AAN"
    assert manifest["records"][4]["ticker"] == "AAA"


def test_selection_diversity_and_authority_boundaries_are_explicit_not_investment_ranking():
    manifest = build_operating_manifest(build_current_workbench())
    rationales = {ticker: rationale for ticker, _, rationale in COHORT}
    assert "OFFICIAL_FINANCIAL" in rationales["HPG"]
    assert "BANK" in rationales["VCB"]
    assert "SECURITIES" in rationales["SSI"]
    assert "SCENARIO" in rationales["AAN"]
    assert "LOW_OFFICIAL_EVIDENCE" in rationales["AAA"]
    assert all(item["priority_basis"] == "EVIDENCE_AND_AUTHORITY_PATTERN_DIVERSITY_NOT_INVESTMENT_ATTRACTIVENESS" for item in manifest["human_review_queue"])
    assert manifest["authority_boundary"]["model_drafts_not_fabricated"]
    assert manifest["authority_boundary"]["human_reviews_not_fabricated"]
    assert manifest["authority_boundary"]["recommendation_portfolio_execution"] == "NOT_EMITTED"
    assert manifest["prompt_contract"]["output_schema"]["claims"] == "list[claim]"


def test_operating_manifest_rejects_nonfresh_reviewed_workbench_state():
    workbench = build_current_workbench()
    workbench._validated_drafts["HPG"] = {"synthetic": {}}
    with pytest.raises(ValueError, match="OPERATING_MANIFEST_REQUIRES_FRESH_UNREVIEWED_COHORT"):
        build_operating_manifest(workbench)
