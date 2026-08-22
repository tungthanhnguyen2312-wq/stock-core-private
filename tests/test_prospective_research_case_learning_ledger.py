import copy

import pytest

from evidence_bound_ai_research_human_review import apply_human_review, build_human_review_packet, validate_ai_draft
from prospective_research_case_learning_ledger import (
    append_case_update, build_case_update, build_learning_ledger, case_readiness, create_research_case,
)
from tools.run_evidence_bound_ai_research_human_review import run as ai_run
from tools.run_evidence_gated_research_decision_workflow import run as decision_run


SECTIONS = ("RESEARCH_CONTEXT", "THESIS", "COUNTER_THESIS", "CATALYSTS", "RISKS", "SCENARIO_INTERPRETATION", "VALUATION_CONTEXT", "MARKET_CONTEXT", "UNRESOLVED_QUESTIONS", "EVIDENCE_GAPS", "WHAT_WOULD_CHANGE_THE_VIEW", "HUMAN_REVIEW_REQUIRED")


def _draft(packet):
    claims = [{"claim_id": f"claim-{index}", "claim_type": "INFERENCE", "section": "COUNTER_THESIS" if item["evidence_id"] in packet["mandatory_counter_evidence_ids"] else "THESIS",
               "claim_text": "Retained evidence is available for prospective research.", "supporting_evidence_ids": [item["evidence_id"]],
               "conflicting_evidence_ids": [], "authority_class": item["authority"], "referenced_dimension": None, "numeric_evidence_ids": []}
              for index, item in enumerate(packet["evidence"])]
    draft = {"source_ai_input_identity": packet["ai_input_identity"], "claims": claims, "sections": {section: [] for section in SECTIONS},
             "dimension_interpretations": {name: item["eligibility"] for name, item in packet["analytical_eligibility"].items()}, "human_review_required": True}
    draft["sections"]["THESIS"] = [item["claim_id"] for item in claims if item["section"] == "THESIS"]
    draft["sections"]["COUNTER_THESIS"] = [item["claim_id"] for item in claims if item["section"] == "COUNTER_THESIS"]
    draft["draft_identity"] = "fixture_draft:" + packet["ai_input_identity"]
    return draft


def _case(ticker="HPG"):
    decision, collection = decision_run(), ai_run(); packet = next(item for item in collection["packets"] if item["ticker"] == ticker)
    draft = _draft(packet); validation = validate_ai_draft(packet, draft); assert validation["validation_status"] == "VALID"
    review = build_human_review_packet(packet, draft, validation)
    review = apply_human_review(review, reviewer_identity="fixture-reviewer", review_timestamp="2026-08-22T09:05:00+07:00",
                                review_state="NEEDS_MORE_EVIDENCE", reviewer_notes="Retain the blocked-capability boundary.",
                                material_claim_edits=[{"claim_id": draft["claims"][0]["claim_id"], "replacement_text": "Human review preserves the evidence boundary."}])
    return create_research_case(decision, packet, created_at="2026-08-22T09:00:00+07:00", known_at="2026-08-22T09:00:00+07:00", validated_draft=draft, validation=validation, human_review=review)


def test_full_cohort_readiness_is_deterministic_and_does_not_backfill_cases():
    decision, collection = decision_run(), ai_run(); first, second = case_readiness(decision, collection), case_readiness(decision, collection)
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["coverage"]["CASE_CREATABLE"] == 523
    assert first["coverage"]["NEEDS_MORE_EVIDENCE"] == first["coverage"]["NOT_CREATABLE"] == 0
    assert all(row["model_draft_state"] == "MODEL_DRAFT_PENDING" for row in first["records"])


def test_case_freezes_t0_and_updates_append_without_lookahead_or_mutation():
    case = _case(); frozen = copy.deepcopy(case)
    assert case["case_content_identity"] == _case()["case_content_identity"]
    relation = {"original_claim_id": case["original_claims"][0]["claim_id"], "relationship": "DOES_NOT_ADDRESS", "claim_outcome": "UNRESOLVED"}
    update = build_case_update(case, observed_at="2026-08-23T09:00:00+07:00", known_at="2026-08-23T10:00:00+07:00", source_evidence_identity="fixture:later-evidence", evidence_kind="TEST_FIXTURE", relationships=[relation],
                               scenario_updates=[{"original_evidence_id": case["original_evidence_ids"][0], "state": "EMERGING"}],
                               catalyst_updates=[{"original_evidence_id": case["original_evidence_ids"][0], "state": "NOT_OBSERVED"}], fixture=True)
    history = append_case_update(case, [], update, lifecycle_state="ACTIVE")
    assert case == frozen
    assert history["case"] == frozen and history["updates"][0]["observed_at"] > case["known_at"]
    assert history["updates"][0]["scenario_updates"][0]["state"] == "EMERGING"
    with pytest.raises(ValueError, match="UPDATE_TEMPORAL_ORDER_INVALID"):
        build_case_update(case, observed_at=case["known_at"], known_at=case["known_at"], source_evidence_identity="bad", evidence_kind="TEST_FIXTURE", relationships=[relation], fixture=True)
    with pytest.raises(ValueError, match="FIXTURE_UPDATE_MUST_BE_EXPLICITLY_TEST_FIXTURE"):
        build_case_update(case, observed_at="2026-08-24T09:00:00+07:00", known_at="2026-08-24T10:00:00+07:00", source_evidence_identity="fixture:bad-label", evidence_kind="OFFICIAL_DOCUMENT", relationships=[relation], fixture=True)
    later = build_case_update(case, observed_at="2026-08-24T09:00:00+07:00", known_at="2026-08-24T10:00:00+07:00", source_evidence_identity="fixture:later", evidence_kind="TEST_FIXTURE", relationships=[relation], fixture=True)
    with pytest.raises(ValueError, match="CASE_UPDATE_OBSERVED_ORDER_INVALID"):
        append_case_update(case, [later], update, lifecycle_state="ACTIVE")


def test_price_movement_is_not_claim_proof_and_fixture_learning_is_excluded():
    case = _case("VCB"); relation = {"original_claim_id": case["original_claims"][0]["claim_id"], "relationship": "SUPPORTS", "claim_outcome": "SUPPORTED"}
    with pytest.raises(ValueError, match="PRICE_MOVEMENT_CANNOT_PROVE_OR_REFUTE_THESIS"):
        build_case_update(case, observed_at="2026-08-23T09:00:00+07:00", known_at="2026-08-23T10:00:00+07:00", source_evidence_identity="fixture:price", evidence_kind="MARKET_OBSERVATION", relationships=[relation], fixture=True)
    fixture = build_case_update(case, observed_at="2026-08-23T09:00:00+07:00", known_at="2026-08-23T10:00:00+07:00", source_evidence_identity="fixture:review", evidence_kind="TEST_FIXTURE", relationships=[relation], fixture=True)
    history = append_case_update(case, [], fixture, lifecycle_state="THESIS_STRENGTHENED")
    ledger = build_learning_ledger([history])
    assert ledger["production_observation_summary"]["resolved_claim_count"] == 0
    assert ledger["patterns"]["fixture_update_count_excluded_from_learning"] == 1
    assert ledger["patterns"]["human_edit_count"] == 1
    assert ledger["ledger_identity"] == build_learning_ledger([history])["ledger_identity"]


def test_representative_real_packets_preserve_authority_and_ai_human_provenance():
    for ticker in ("HPG", "VCB", "SSI", "AAN", "AAA"):
        case = _case(ticker)
        assert case["frozen_universe"]["membership_count"] == 523
        assert case["authority_boundary"]["research_snapshot_not_recommendation"]
        assert case["authority_boundary"]["portfolio_sizing_execution"] == "NOT_EMITTED"
        assert case["ai_human_provenance"]["validation_identity"]
        assert case["ai_human_provenance"]["human_modifications"][0]["origin"] == "HUMAN_EDIT"
        assert case["ai_human_provenance"]["human_reviewer"]["notes"] == "Retain the blocked-capability boundary."
        assert case["blocked_capabilities"]["liquidity_readiness"]["eligibility"] == "BLOCKED"
    decision, _ = decision_run(), ai_run()
    hpg, vcb, ssi, aaa, aan = (next(row for row in decision["records"] if row["ticker"] == ticker) for ticker in ("HPG", "VCB", "SSI", "AAA", "AAN"))
    assert hpg["valuation_state"]["authority"] == "NON_AUTHORITATIVE_RESEARCH_PROXY"
    assert vcb["analytical_eligibility"]["valuation_research"]["eligibility"] == "BLOCKED"
    assert ssi["valuation_state"]["method_states"]["EV/EBITDA"]["status"] == "NOT_APPLICABLE"
    assert aaa["analytical_eligibility"]["financial_evidence_depth"]["eligibility"] == "BLOCKED"
    assert aan["scenario_axis"]["qualification_status"] == "PARTIAL_EVIDENCE_BOUND_SCENARIO"
