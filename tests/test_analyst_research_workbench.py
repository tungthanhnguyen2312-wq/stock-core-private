import copy

import pytest

from analyst_research_workbench import CURRENT_RETAINED_SNAPSHOT, build_current_workbench
from evidence_bound_ai_research_human_review import apply_human_review, build_human_review_packet


SECTIONS = (
    "RESEARCH_CONTEXT", "THESIS", "COUNTER_THESIS", "CATALYSTS", "RISKS", "SCENARIO_INTERPRETATION",
    "VALUATION_CONTEXT", "MARKET_CONTEXT", "UNRESOLVED_QUESTIONS", "EVIDENCE_GAPS",
    "WHAT_WOULD_CHANGE_THE_VIEW", "HUMAN_REVIEW_REQUIRED",
)


def _draft(packet):
    claims = [
        {"claim_id": f"workbench-claim-{index}", "claim_type": "INFERENCE",
         "section": "COUNTER_THESIS" if item["evidence_id"] in packet["mandatory_counter_evidence_ids"] else "THESIS",
         "claim_text": "Retained evidence remains bounded for internal research review.",
         "supporting_evidence_ids": [item["evidence_id"]], "conflicting_evidence_ids": [],
         "authority_class": item["authority"], "referenced_dimension": None, "numeric_evidence_ids": []}
        for index, item in enumerate(packet["evidence"])
    ]
    draft = {"source_ai_input_identity": packet["ai_input_identity"], "claims": claims,
             "sections": {section: [] for section in SECTIONS},
             "dimension_interpretations": {name: item["eligibility"] for name, item in packet["analytical_eligibility"].items()},
             "human_review_required": True, "fixture": True,
             "draft_identity": "TEST_FIXTURE:workbench_draft:" + packet["ai_input_identity"]}
    draft["sections"]["THESIS"] = [claim["claim_id"] for claim in claims if claim["section"] == "THESIS"]
    draft["sections"]["COUNTER_THESIS"] = [claim["claim_id"] for claim in claims if claim["section"] == "COUNTER_THESIS"]
    return draft


def _reviewed_case(workbench, ticker="HPG"):
    handoff = workbench.build_ai_input(ticker)
    packet = handoff["ai_input"]
    draft = _draft(packet)
    validation = workbench.validate_ai_draft(ticker, draft)
    assert validation["validation"]["validation_status"] == "VALID"
    reviewed = workbench.record_human_review(
        ticker, draft, reviewer_identity="analyst:fixture", review_timestamp="2026-08-22T09:05:00+07:00",
        review_state="NEEDS_MORE_EVIDENCE", reviewer_notes="Keep all blocked dimensions visible.",
        material_claim_edits=[{"claim_id": draft["claims"][0]["claim_id"], "replacement_text": "Human edit retains the evidence boundary."}],
    )
    created = workbench.create_case(
        ticker, draft, validation["validation"], reviewed["human_review"],
        created_at="2026-08-22T09:00:00+07:00", known_at="2026-08-22T09:00:00+07:00",
    )
    return packet, draft, created["case"]


def test_ticker_as_of_state_resolves_exact_cohort_without_universe_substitution():
    workbench = build_current_workbench()
    state = workbench.get_research_state("HPG", as_of=CURRENT_RETAINED_SNAPSHOT)
    assert state["as_of"]["research_session"] == "2026-08-20"
    assert state["as_of"]["membership_count"] == 523
    assert state["snapshot_boundary"]["separate_2026_08_21_524_member_shadow_snapshot"] == "NOT_SUBSTITUTED_OR_MIXED"
    assert state["analytical_eligibility"]["liquidity_readiness"]["eligibility"] == "BLOCKED"
    assert state["authority_limitations"]["valuation_proxy_must_remain_non_authoritative"]
    assert state["operation_gates"]["structural_case_eligibility"]["status"] == "CASE_STRUCTURE_ELIGIBLE"
    assert state["operation_gates"]["operations"]["CREATE_CASE"]["status"] == "CASE_CREATION_NOT_READY"
    with pytest.raises(ValueError, match="AS_OF_SNAPSHOT_UNAVAILABLE"):
        workbench.get_research_state("HPG", as_of="2026-08-21")
    with pytest.raises(ValueError, match="TICKER_NOT_IN_CURRENT_RETAINED_DECISION_COHORT"):
        workbench.get_research_state("NOT_A_TICKER")


def test_ai_validation_precedes_review_and_preserves_human_provenance():
    workbench = build_current_workbench()
    packet = workbench.build_ai_input("HPG")["ai_input"]
    draft = _draft(packet)
    validation = workbench.validate_ai_draft("HPG", draft)
    assert validation["validation"]["source_ai_input_identity"] == packet["ai_input_identity"]
    assert workbench.get_research_state("HPG")["operation_gates"]["operations"]["RECORD_HUMAN_REVIEW"]["status"] == "READY"
    reviewed = workbench.record_human_review(
        "HPG", draft, reviewer_identity="analyst:fixture", review_timestamp="2026-08-22T09:05:00+07:00",
        review_state="APPROVED_FOR_INTERNAL_RESEARCH", reviewer_notes="Internal research only.",
        material_claim_edits=[{"claim_id": draft["claims"][0]["claim_id"], "replacement_text": "Human clarification."}],
    )
    assert reviewed["human_review"]["human_modifications"][0]["origin"] == "HUMAN_EDIT"
    assert reviewed["human_review"]["approval_boundary"].startswith("INTERNAL_RESEARCH_ONLY")
    bad = copy.deepcopy(draft)
    bad["claims"][0]["claim_text"] = "BUY at target price 123"
    with pytest.raises(ValueError, match="INVALID_AI_DRAFT_CANNOT_ENTER_HUMAN_REVIEW"):
        workbench.record_human_review("HPG", bad, reviewer_identity="analyst:fixture", review_timestamp="2026-08-22T09:06:00+07:00", review_state="REJECTED")


def test_case_creation_requires_registered_validation_and_qualifying_recorded_review():
    workbench = build_current_workbench()
    packet = workbench.build_ai_input("VCB")["ai_input"]
    draft = _draft(packet)
    validation = workbench.validate_ai_draft("VCB", draft)["validation"]
    unrecorded = apply_human_review(
        build_human_review_packet(packet, draft, validation), reviewer_identity="analyst:fixture",
        review_timestamp="2026-08-22T09:05:00+07:00", review_state="NEEDS_MORE_EVIDENCE",
    )
    with pytest.raises(ValueError, match="CASE_REQUIRES_RECORDED_HUMAN_REVIEW_STATE"):
        workbench.create_case("VCB", draft, validation, unrecorded, created_at="2026-08-22T09:00:00+07:00", known_at="2026-08-22T09:00:00+07:00")
    reviewed = workbench.record_human_review(
        "VCB", draft, reviewer_identity="analyst:fixture", review_timestamp="2026-08-22T09:05:00+07:00",
        review_state="NEEDS_MORE_EVIDENCE",
    )["human_review"]
    assert workbench.get_research_state("VCB")["operation_gates"]["operations"]["CREATE_CASE"]["status"] == "CASE_CREATION_READY"
    assert workbench.create_case("VCB", draft, validation, reviewed, created_at="2026-08-22T09:00:00+07:00", known_at="2026-08-22T09:00:00+07:00")["case"]["ticker"] == "VCB"


def test_end_to_end_case_update_history_claim_trace_and_read_only_learning():
    workbench = build_current_workbench()
    packet, _, case = _reviewed_case(workbench)
    claim = case["original_claims"][0]
    relation = {"original_claim_id": claim["claim_id"], "relationship": "DOES_NOT_ADDRESS", "claim_outcome": "UNRESOLVED"}
    appended = workbench.append_case_update(
        case["case_id"], observed_at="2026-08-23T09:00:00+07:00", known_at="2026-08-23T10:00:00+07:00",
        source_evidence_identity="fixture:workbench-later-evidence", evidence_kind="TEST_FIXTURE", relationships=[relation],
        scenario_updates=[{"original_evidence_id": case["original_evidence_ids"][0], "state": "EMERGING"}],
        catalyst_updates=[{"original_evidence_id": case["original_evidence_ids"][0], "state": "NOT_OBSERVED"}],
        lifecycle_state="ACTIVE", fixture=True,
    )
    assert appended["update"]["update_identity"]
    assert workbench.get_case(case["case_id"])["case"]["case_content_identity"] == case["case_content_identity"]
    assert workbench.get_research_state("HPG")["operation_gates"]["operations"]["APPEND_CASE_UPDATE"]["status"] == "READY_FOR_TEST_FIXTURE_ONLY"
    history = workbench.get_case_history(case["case_id"])
    assert history["history"]["case"] == case
    trace = workbench.get_claim_trace(case["case_id"], claim["claim_id"])
    assert trace["original_evidence_ids"] == claim["supporting_evidence_ids"]
    assert trace["later_observations"][0]["fixture"] is True
    learning = workbench.get_learning_summary()
    assert learning["learning_ledger"]["patterns"]["fixture_update_count_excluded_from_learning"] == 1
    assert learning["learning_ledger"]["production_observation_summary"]["resolved_claim_count"] == 0
    with pytest.raises(ValueError, match="PRICE_MOVEMENT_CANNOT_PROVE_OR_REFUTE_THESIS"):
        workbench.append_case_update(
            case["case_id"], observed_at="2026-08-24T09:00:00+07:00", known_at="2026-08-24T10:00:00+07:00",
            source_evidence_identity="fixture:price", evidence_kind="MARKET_OBSERVATION",
            relationships=[{"original_claim_id": claim["claim_id"], "relationship": "SUPPORTS", "claim_outcome": "SUPPORTED"}],
            lifecycle_state="THESIS_STRENGTHENED", fixture=True,
        )
    with pytest.raises(ValueError, match="TEST_FIXTURE_EVIDENCE_IDENTITY_REQUIRED"):
        workbench.append_case_update(
            case["case_id"], observed_at="2026-08-24T09:00:00+07:00", known_at="2026-08-24T10:00:00+07:00",
            source_evidence_identity="not-a-fixture", evidence_kind="TEST_FIXTURE", relationships=[relation], lifecycle_state="ACTIVE", fixture=True,
        )
    with pytest.raises(ValueError, match="UPDATE_EVIDENCE_IDENTITY_NOT_REGISTERED"):
        workbench.append_case_update(
            case["case_id"], observed_at="2026-08-24T09:00:00+07:00", known_at="2026-08-24T10:00:00+07:00",
            source_evidence_identity="unregistered:later-evidence", evidence_kind="OFFICIAL_DOCUMENT", relationships=[relation], lifecycle_state="ACTIVE",
        )
    with pytest.raises(ValueError, match="UPDATE_TEMPORAL_ORDER_INVALID"):
        workbench.append_case_update(
            case["case_id"], observed_at=case["known_at"], known_at=case["known_at"],
            source_evidence_identity="fixture:timestamp", evidence_kind="TEST_FIXTURE", relationships=[relation], lifecycle_state="ACTIVE", fixture=True,
        )
    assert packet["ticker"] == "HPG"


def test_representative_workflows_preserve_sector_proxy_scenario_and_evidence_states():
    workbench = build_current_workbench()
    states = {ticker: workbench.get_research_state(ticker) for ticker in ("HPG", "VCB", "SSI", "AAN", "AAA")}
    assert all(state["operation_gates"]["operations"]["CREATE_CASE"]["status"] == "CASE_CREATION_NOT_READY" for state in states.values())
    assert states["HPG"]["valuation_context"]["authority"] == "NON_AUTHORITATIVE_RESEARCH_PROXY"
    assert states["VCB"]["analytical_eligibility"]["valuation_research"]["eligibility"] == "BLOCKED"
    assert states["SSI"]["valuation_context"]["method_states"]["EV/EBITDA"]["status"] == "NOT_APPLICABLE"
    assert states["AAN"]["scenario_axis"]["qualification_status"] == "PARTIAL_EVIDENCE_BOUND_SCENARIO"
    assert states["AAA"]["analytical_eligibility"]["financial_evidence_depth"]["eligibility"] == "BLOCKED"
    for ticker in ("HPG", "VCB", "SSI", "AAN", "AAA"):
        _, _, case = _reviewed_case(workbench, ticker)
        assert case["ai_human_provenance"]["human_modifications"][0]["origin"] == "HUMAN_EDIT"


def test_full_cohort_resolution_is_deterministic_and_does_not_create_cases_or_drafts():
    first, second = build_current_workbench(), build_current_workbench()
    first_resolution, second_resolution = first.get_cohort_resolution(), second.get_cohort_resolution()
    assert first_resolution["cohort_resolution_identity"] == second_resolution["cohort_resolution_identity"]
    assert first_resolution["coverage"] == {
        "cohort_count": 523, "research_state_available": 523, "ai_input_available": 523,
        "case_structure_eligible": 523, "validated_ai_draft_available": 0,
        "qualifying_human_review_available": 0, "case_creation_ready": 0, "existing_local_case_count": 0,
        "case_creation_not_ready_reason_counts": {
            "NO_QUALIFYING_HUMAN_REVIEW_IN_LOCAL_SESSION": 523,
            "NO_VALIDATED_AI_DRAFT_IN_LOCAL_SESSION": 523,
        },
    }
    assert all(row["blocked_dimension_names"] for row in first_resolution["records"])
    assert first.get_learning_summary()["local_case_count"] == 0
