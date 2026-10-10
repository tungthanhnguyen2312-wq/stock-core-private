"""Portable integration of real engines with explicitly fictitious research inputs."""
import copy
import hashlib
import json

import pytest

from _research_case_fixture import (
    T0, TICKERS, create_fixture_case, fixture_draft, fixture_update_kwargs,
    fixture_workbench, reviewed_fixture, workflow_inputs,
)
from stocklookup_core.research.evidence_gated_research_decision_workflow import build
from stocklookup_core.research.evidence_bound_ai_research_human_review import (
    build_ai_input_collection, validate_ai_draft,
)
from stocklookup_core.research.analyst_research_workbench import AnalystResearchWorkbench
from stocklookup_core.research.durable_prospective_research_case_store import (
    DurableCaseStoreError, DurableProspectiveResearchCaseStore,
)
from stocklookup_core.research.prospective_research_case_learning_ledger import (
    build_case_update, build_learning_ledger,
)
from tools import run_evidence_gated_research_decision_workflow as retained_decision
from tools import run_evidence_bound_ai_research_human_review as retained_ai


@pytest.fixture(autouse=True)
def forbid_retained_default_loaders(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("portable acceptance must not invoke retained default loaders")
    monkeypatch.setattr(retained_decision, "inputs", forbidden)
    monkeypatch.setattr(retained_decision, "run", forbidden)
    monkeypatch.setattr(retained_ai, "run", forbidden)


def test_packet_pipeline_is_deterministic_preserves_inputs_and_exposes_gaps():
    inputs = workflow_inputs()
    original = copy.deepcopy(inputs)
    first, second = build(**inputs), build(**workflow_inputs())
    assert inputs == original and first == second
    assert first["as_of"]["membership_count"] == 15
    assert first["coverage"]["official_financial_evidence_presence"] == {"BLOCKED": 2, "ELIGIBLE": 13}
    collection = build_ai_input_collection(first)
    assert collection == build_ai_input_collection(second)
    assert collection["coverage"]["model_draft_pending_count"] == 15
    for packet in collection["packets"]:
        assert packet["analytical_eligibility"]["liquidity_readiness"]["eligibility"] == "BLOCKED"
        assert packet["analytical_eligibility"]["historical_pit_readiness"]["eligibility"] == "BLOCKED"
        assert packet["analytical_eligibility"]["valuation_research"]["eligibility"] == "UNKNOWN"
        assert packet["unknown_or_missing_evidence"]
        assert all(identity.startswith("TEST_FIXTURE:") for identity in
                   packet["evidence_inventory"]["source_artifact_identities"].values())
        assert packet["authority_boundary"]["ai_is_not_factual_or_numerical_authority"]
    bank = next(packet for packet in collection["packets"] if packet["ticker"] == TICKERS[1])
    assert bank["analytical_eligibility"]["sector_model_applicability"]["details"]["not_applicable_metric_ids"] == ["fixture:corporate_metric"]
    provider = next(packet for packet in collection["packets"] if packet["ticker"] == TICKERS[-1])
    assert provider["analytical_eligibility"]["financial_evidence_depth"]["eligibility"] == "BLOCKED"
    assert any("NO_RETAINED_EVENT_EVIDENCE_NOT_NO_EVENT_RISK" in item["reason_codes"]
               for item in provider["unknown_or_missing_evidence"])


@pytest.mark.parametrize("mutation,reason", [
    ("artifact_session", "SESSION_MISMATCH:eligibility"),
    ("row_session", "SESSION_MISMATCH:event_context"),
    ("bundle_session", "SESSION_MISMATCH:mva_bundle"),
    ("duplicate_member", "INVALID_DAILY_COHORT"),
    ("missing_member", "COHORT_MEMBERSHIP_MISMATCH:strategy_eligibility"),
    ("extra_scenario", "COHORT_MEMBERSHIP_MISMATCH:scenario"),
    ("panel_count", "OFFICIAL_FINANCIAL_PANEL_COVERAGE_MISMATCH"),
    ("panel_membership", "OFFICIAL_FINANCIAL_PANEL_MEMBERSHIP_MISMATCH"),
])
def test_decision_packet_refuses_mixed_or_malformed_cohorts(mutation, reason):
    inputs = workflow_inputs()
    if mutation == "artifact_session":
        inputs["eligibility"]["research_session"] = "2026-01-07"
    elif mutation == "row_session":
        inputs["events"]["records"][0]["research_session"] = "2026-01-07"
    elif mutation == "bundle_session":
        inputs["mva_bundle"]["records"][0]["session"] = "2026-01-07"
    elif mutation == "duplicate_member":
        inputs["product"]["stock_research"].append(copy.deepcopy(inputs["product"]["stock_research"][0]))
    elif mutation == "missing_member":
        inputs["eligibility"]["records"].pop()
    elif mutation == "extra_scenario":
        inputs["scenarios"]["scenarios"][0]["ticker"] = "FIX_OUTSIDE_COHORT"
    elif mutation == "panel_count":
        inputs["official_financial_panel"]["before_after_comparison"]["fundamental_readiness_status"]["after"]["PARTIAL"] = 14
    else:
        inputs["product"]["stock_research"][0]["research_summary"]["fundamental_authority"] = "PROVIDER_RESEARCH"
    with pytest.raises(ValueError, match=reason):
        build(**inputs)


@pytest.mark.parametrize("mutation,reason", [
    ("source", "SOURCE_AI_INPUT_IDENTITY_MISMATCH"),
    ("authority", "AUTHORITY_ESCALATION_OR_UNSUPPORTED_CLAIM"),
    ("unknown_evidence", "CLAIM_REFERENCES_UNKNOWN_EVIDENCE"),
    ("numeric", "UNSUPPORTED_NUMERIC_CLAIM"),
    ("recommendation", "FORBIDDEN_INVESTMENT_OR_EXECUTION_OUTPUT"),
    ("valuation", "VALUATION_PROXY_PRESENTED_AS_AUTHORITATIVE"),
    ("counter", "MATERIAL_COUNTER_EVIDENCE_SUPPRESSED"),
    ("dimension", "DIMENSION_STATE_NOT_PRESERVED"),
    ("human_gate", "HUMAN_REVIEW_GATE_MISSING"),
    ("section", "REQUIRED_DRAFT_SECTION_MISSING"),
    ("duplicate_claim", "CLAIM_ID_INVALID_OR_DUPLICATE"),
    ("missing_fact", "FACT_WITHOUT_QUALIFIED_EVIDENCE"),
    ("blocked_fact", "BLOCKED_DIMENSION_PRESENTED_AS_FACT"),
])
def test_untrusted_draft_cannot_remove_evidence_or_gain_authority(mutation, reason):
    workbench = fixture_workbench()
    packet = workbench.build_ai_input(TICKERS[0])["ai_input"]
    draft = fixture_draft(packet)
    assert validate_ai_draft(packet, draft)["validation_status"] == "VALID"
    if mutation == "source":
        draft["source_ai_input_identity"] = "TEST_FIXTURE:wrong-packet"
    elif mutation == "authority":
        draft["claims"][0]["authority_class"] = "PIT_QUALIFIED"
    elif mutation == "unknown_evidence":
        draft["claims"][0]["supporting_evidence_ids"] = ["TEST_FIXTURE:unknown-evidence"]
    elif mutation == "numeric":
        draft["claims"][0]["claim_text"] = "Synthetic estimate is 123."
    elif mutation == "recommendation":
        draft["claims"][0]["claim_text"] = "BUY this synthetic security."
    elif mutation == "valuation":
        draft["claims"][0]["claim_text"] = "The valuation is authoritative."
    elif mutation == "counter":
        assert packet["mandatory_counter_evidence_ids"]
        for claim in draft["claims"]:
            claim["section"] = "THESIS"
    elif mutation == "dimension":
        draft["dimension_interpretations"]["liquidity_readiness"] = "ELIGIBLE"
    elif mutation == "human_gate":
        draft["human_review_required"] = False
    elif mutation == "section":
        draft["sections"].pop("RISKS")
    elif mutation == "duplicate_claim":
        draft["claims"].append(copy.deepcopy(draft["claims"][0]))
    elif mutation == "missing_fact":
        claim = next(item for item in draft["claims"] if item["authority_class"] == "MISSING")
        claim["claim_type"] = "FACT"
    else:
        draft["claims"][0].update(claim_type="FACT", referenced_dimension="liquidity_readiness")
    result = workbench.validate_ai_draft(TICKERS[0], draft)["validation"]
    assert result["validation_status"] == "REJECTED" and reason in result["reason_codes"]
    assert workbench.get_cohort_resolution()["coverage"]["case_creation_ready"] == 0


@pytest.mark.parametrize("mutation,reason", [
    ("identity", "WORKBENCH_AI_INPUT_DECISION_IDENTITY_MISMATCH"),
    ("cohort", "WORKBENCH_COHORT_MEMBERSHIP_MISMATCH"),
    ("as_of", "WORKBENCH_AS_OF_MISMATCH"),
])
def test_workbench_admission_requires_matching_packet_lineage(mutation, reason):
    decision = build(**workflow_inputs())
    collection = build_ai_input_collection(decision)
    if mutation == "identity":
        collection["source_decision_workflow_identity"] = "TEST_FIXTURE:wrong"
    elif mutation == "cohort":
        collection["packets"].pop()
    else:
        collection["as_of"] = {"research_session": "2026-01-07"}
    with pytest.raises(ValueError, match=reason):
        AnalystResearchWorkbench.from_artifacts(decision, collection)


@pytest.mark.parametrize("review_state", ["NEEDS_MORE_EVIDENCE", "APPROVED_FOR_INTERNAL_RESEARCH"])
def test_local_case_requires_validation_then_recorded_review_and_preserves_edits(review_state):
    workbench = fixture_workbench()
    assert workbench.get_cohort_resolution()["coverage"]["existing_local_case_count"] == 0
    draft, validation, review = reviewed_fixture(workbench, review_state=review_state)
    assert workbench.get_cohort_resolution()["coverage"]["case_creation_ready"] == 1
    case = workbench.create_case(TICKERS[0], draft, validation, review, created_at=T0, known_at=T0)["case"]
    assert case["ai_human_provenance"]["human_review_state"] == review_state
    assert case["ai_human_provenance"]["human_modifications"][0]["origin"] == "HUMAN_EDIT"
    assert case["blocked_capabilities"]["liquidity_readiness"]["eligibility"] == "BLOCKED"
    assert case["authority_boundary"]["portfolio_sizing_execution"] == "NOT_EMITTED"
    case["ticker"] = "TEST_FIXTURE:mutated-return-value"
    assert workbench.get_case(case["case_id"])["case"]["ticker"] == TICKERS[0]


@pytest.mark.parametrize("mutation,reason", [
    ("fresh_session", "CASE_REQUIRES_CURRENT_VALIDATED_AI_DRAFT"),
    ("unrecorded_review", "CASE_REQUIRES_RECORDED_HUMAN_REVIEW_STATE"),
    ("rejected_review", "CASE_REQUIRES_RECORDED_HUMAN_REVIEW_STATE"),
    ("different_packet", "CASE_HUMAN_REVIEW_LINEAGE_MISMATCH"),
    ("known_at", "CASE_CREATED_AT_MUST_EQUAL_KNOWN_AT"),
])
def test_case_gate_refuses_replayed_or_nonqualifying_review(mutation, reason):
    workbench = fixture_workbench()
    draft, validation, review = reviewed_fixture(workbench)
    known_at = T0
    if mutation == "fresh_session":
        workbench = fixture_workbench()
    elif mutation == "unrecorded_review":
        review["review_packet_identity"] = "TEST_FIXTURE:unrecorded-review"
    elif mutation == "rejected_review":
        draft, validation, review = reviewed_fixture(workbench, review_state="REJECTED")
    elif mutation == "different_packet":
        review["source_ai_input_identity"] = "TEST_FIXTURE:other-packet"
    else:
        known_at = "2026-01-06T10:00:00+07:00"
    with pytest.raises(ValueError, match=reason):
        workbench.create_case(TICKERS[0], draft, validation, review, created_at=T0, known_at=known_at)
    assert workbench.get_cohort_resolution()["coverage"]["existing_local_case_count"] == 0


@pytest.mark.parametrize("mutation", ["draft_after_review", "revalidated_draft_after_review", "reviewer_payload"])
def test_case_gate_binds_the_exact_draft_and_recorded_review_payload(mutation):
    workbench = fixture_workbench()
    draft, validation, review = reviewed_fixture(workbench)
    if mutation == "reviewer_payload":
        review["reviewer"]["identity"] = "TEST_FIXTURE:unrecorded-reviewer"
    else:
        draft["claims"][0]["claim_text"] = "A different synthetic material interpretation."
        if mutation == "revalidated_draft_after_review":
            validation = workbench.validate_ai_draft(TICKERS[0], draft)["validation"]
            assert validation["validation_status"] == "VALID"
    with pytest.raises(ValueError):
        workbench.create_case(TICKERS[0], draft, validation, review, created_at=T0, known_at=T0)
    assert workbench.get_cohort_resolution()["coverage"]["existing_local_case_count"] == 0


def test_frozen_t0_cannot_change_when_the_caller_mutates_source_objects():
    workbench = fixture_workbench()
    draft, validation, review = reviewed_fixture(workbench)
    case = workbench.create_case(TICKERS[0], draft, validation, review, created_at=T0, known_at=T0)["case"]
    original = copy.deepcopy(case)
    draft["claims"][0]["claim_text"] = "A later caller edit must not rewrite frozen history."
    workbench.decision_artifact["as_of"]["membership_count"] = 999
    assert workbench.get_case(case["case_id"])["case"] == original


def test_changed_draft_can_create_a_case_after_a_fresh_recorded_review():
    workbench = fixture_workbench()
    draft, validation, old_review = reviewed_fixture(workbench)
    draft["claims"][0]["claim_text"] = "A revised synthetic interpretation for a fresh review."
    validation = workbench.validate_ai_draft(TICKERS[0], draft)["validation"]
    with pytest.raises(ValueError):
        workbench.create_case(TICKERS[0], draft, validation, old_review, created_at=T0, known_at=T0)
    fresh_review = workbench.record_human_review(
        TICKERS[0], draft, reviewer_identity="TEST_FIXTURE:fresh-reviewer",
        review_timestamp="2026-01-06T08:59:00+07:00", review_state="NEEDS_MORE_EVIDENCE",
    )["human_review"]
    case = workbench.create_case(TICKERS[0], draft, validation, fresh_review, created_at=T0, known_at=T0)["case"]
    assert case["original_claims"][0]["claim_text"] == draft["claims"][0]["claim_text"]
    assert case["ai_human_provenance"]["human_review_identity"] == fresh_review["review_packet_identity"]
    assert fresh_review["review_packet_identity"] != old_review["review_packet_identity"]


def test_readiness_requires_a_fresh_review_after_revalidating_a_changed_draft():
    workbench = fixture_workbench()
    draft, _, _ = reviewed_fixture(workbench)
    assert workbench.get_cohort_resolution()["coverage"]["case_creation_ready"] == 1
    draft["claims"][0]["claim_text"] = "A revised synthetic interpretation needs another review."
    workbench.validate_ai_draft(TICKERS[0], draft)
    resolution = workbench.get_cohort_resolution()
    assert resolution["coverage"]["case_creation_ready"] == 0
    assert resolution["coverage"]["qualifying_human_review_available"] == 0
    workbench.record_human_review(
        TICKERS[0], draft, reviewer_identity="TEST_FIXTURE:fresh-reviewer",
        review_timestamp="2026-01-06T08:59:00+07:00", review_state="NEEDS_MORE_EVIDENCE",
    )
    assert workbench.get_cohort_resolution()["coverage"]["case_creation_ready"] == 1


def test_durable_restart_preserves_t0_updates_trace_and_excludes_fixture_learning(tmp_path):
    root = tmp_path / "fixture-store"
    store = DurableProspectiveResearchCaseStore(root)
    workbench = fixture_workbench(case_store=store)
    cases = [create_fixture_case(workbench, ticker) for ticker in (TICKERS[0], TICKERS[1], TICKERS[-1])]
    case = cases[0]
    frozen = copy.deepcopy(case)
    restarted = fixture_workbench(case_store=DurableProspectiveResearchCaseStore(root))
    update = restarted.append_case_update(case["case_id"], **fixture_update_kwargs(case))["update"]
    third = DurableProspectiveResearchCaseStore(root)
    replay = third.replay_case(case["case_id"])
    assert replay == DurableProspectiveResearchCaseStore(root).replay_case(case["case_id"])
    assert replay["history"]["case"] == frozen
    assert replay["history"]["updates"] == [update]
    restored = fixture_workbench(case_store=third)
    trace = restored.get_claim_trace(case["case_id"], case["original_claims"][0]["claim_id"])
    assert trace["later_observations"][0]["update_identity"] == update["update_identity"]
    assert third.live_readiness()["current_durable_case_count"] == 3
    assert third.live_readiness()["current_non_fixture_case_count"] == 0
    assert third.build_learning_ledger()["case_history_count"] == 0
    descriptive = build_learning_ledger([replay["history"]])
    assert descriptive["production_observation_summary"]["resolved_claim_count"] == 0
    assert descriptive["patterns"]["fixture_update_count_excluded_from_learning"] == 1
    assert not (root / ".writer.lock").exists()


@pytest.mark.parametrize("mutation,reason", [
    ("same_time", "UPDATE_TEMPORAL_ORDER_INVALID"),
    ("known_before_observed", "UPDATE_TEMPORAL_ORDER_INVALID"),
    ("unregistered", "UPDATE_EVIDENCE_IDENTITY_NOT_REGISTERED"),
    ("fixture_label", "FIXTURE_UPDATE_MUST_BE_EXPLICITLY_TEST_FIXTURE"),
    ("fixture_identity", "TEST_FIXTURE_EVIDENCE_IDENTITY_REQUIRED"),
    ("unknown_claim", "UPDATE_CLAIM_RELATION_INVALID"),
    ("invalid_scenario", "SCENARIO_OR_CATALYST_UPDATE_INVALID"),
])
def test_later_update_refuses_lookahead_or_misdeclared_sources(mutation, reason, tmp_path):
    store = DurableProspectiveResearchCaseStore(tmp_path / "fixture-store")
    workbench = fixture_workbench(case_store=store)
    case = create_fixture_case(workbench)
    before = store.replay_case(case["case_id"])
    args = fixture_update_kwargs(case)
    if mutation == "same_time":
        args.update(observed_at=T0, known_at=T0)
    elif mutation == "known_before_observed":
        args["known_at"] = T0
    elif mutation == "unregistered":
        args.update(fixture=False, evidence_kind="OFFICIAL_DOCUMENT", source_evidence_identity="TEST_FIXTURE:unregistered")
    elif mutation == "fixture_label":
        args["evidence_kind"] = "OFFICIAL_DOCUMENT"
    elif mutation == "fixture_identity":
        args["source_evidence_identity"] = "TEST_FIXTURE:incorrect-update-prefix"
    elif mutation == "unknown_claim":
        args["relationships"][0]["original_claim_id"] = "TEST_FIXTURE:unknown-claim"
    else:
        args["scenario_updates"] = [{"original_evidence_id": case["original_evidence_ids"][0], "state": "INVENTED"}]
    with pytest.raises(ValueError, match=reason):
        workbench.append_case_update(case["case_id"], **args)
    assert store.replay_case(case["case_id"]) == before


def test_market_price_movement_cannot_be_used_as_thesis_proof():
    case = create_fixture_case(fixture_workbench())
    args = fixture_update_kwargs(case)
    args.pop("lifecycle_state")
    args.update(evidence_kind="MARKET_OBSERVATION", fixture=False)
    args["relationships"][0].update(relationship="SUPPORTS", claim_outcome="SUPPORTED")
    with pytest.raises(ValueError, match="PRICE_MOVEMENT_CANNOT_PROVE_OR_REFUTE_THESIS"):
        build_case_update(case, **args)


def test_durable_update_order_remains_strict_after_a_restart(tmp_path):
    root = tmp_path / "fixture-store"
    store = DurableProspectiveResearchCaseStore(root)
    workbench = fixture_workbench(case_store=store)
    case = create_fixture_case(workbench)
    workbench.append_case_update(case["case_id"], **fixture_update_kwargs(case))
    before = store.replay_case(case["case_id"])
    restarted = fixture_workbench(case_store=DurableProspectiveResearchCaseStore(root))
    earlier = fixture_update_kwargs(case)
    earlier.update(observed_at="2026-01-06T11:00:00+07:00", known_at="2026-01-06T12:00:00+07:00",
                   source_evidence_identity="fixture:out-of-order")
    with pytest.raises(ValueError, match="CASE_UPDATE_OBSERVED_ORDER_INVALID"):
        restarted.append_case_update(case["case_id"], **earlier)
    assert store.replay_case(case["case_id"]) == before


@pytest.mark.parametrize("case_request", ["unknown_ticker", "later_session"])
def test_workbench_never_substitutes_a_different_ticker_or_session(case_request):
    workbench = fixture_workbench()
    with pytest.raises(ValueError):
        if case_request == "unknown_ticker":
            workbench.get_research_state("FIX_OUTSIDE_COHORT")
        else:
            workbench.get_research_state(TICKERS[0], as_of="2026-01-07")


@pytest.mark.parametrize("mutation,reason", [
    ("case_content", "CASE_CONTENT_IDENTITY_INVALID"),
    ("case_envelope", "CASE_ENVELOPE_CONTENT_IDENTITY_INVALID"),
    ("duplicate_case", "DUPLICATE_CONTENT_INSERTION"),
    ("duplicate_update", "CASE_UPDATE_ALREADY_APPENDED"),
    ("writer_lock", "STORE_WRITER_LOCKED"),
    ("event_content", "EVENT_CONTENT_IDENTITY_INVALID"),
    ("event_parent", "EVENT_PRIOR_LINK_UNKNOWN"),
])
def test_durable_store_refuses_mutation_duplicate_writes_and_broken_event_chain(mutation, reason, tmp_path):
    store = DurableProspectiveResearchCaseStore(tmp_path / "fixture-store")
    workbench = fixture_workbench(case_store=store)
    case = create_fixture_case(workbench)
    envelope = store.load_case_envelope(case["case_id"])
    if mutation == "case_content":
        changed = copy.deepcopy(case)
        changed["ticker"] = "TEST_FIXTURE:changed"
        with pytest.raises(DurableCaseStoreError, match=reason):
            store.persist_case(changed, envelope["ai_draft"], envelope["validation"], envelope["human_review"])
    elif mutation in ("duplicate_case", "writer_lock"):
        if mutation == "writer_lock":
            store.lock_path.write_text("TEST_FIXTURE:other-writer", encoding="utf-8")
        with pytest.raises(DurableCaseStoreError, match=reason):
            store.persist_case(case, envelope["ai_draft"], envelope["validation"], envelope["human_review"])
    elif mutation == "case_envelope":
        path = next(store.cases_dir.glob("*.json"))
        envelope["case"]["ticker"] = "TEST_FIXTURE:changed"
        path.write_text(json.dumps(envelope), encoding="utf-8")
        with pytest.raises(DurableCaseStoreError, match=reason):
            store.load_case_envelope(case["case_id"])
    else:
        update = workbench.append_case_update(case["case_id"], **fixture_update_kwargs(case))["update"]
        if mutation == "duplicate_update":
            with pytest.raises(DurableCaseStoreError, match=reason):
                store.append_case_update(case["case_id"], update, lifecycle_state="ACTIVE")
        else:
            path = next(store.events_dir.glob("*.json"))
            event = json.loads(path.read_text(encoding="utf-8"))
            if mutation == "event_content":
                event["actor_or_source"] = "TEST_FIXTURE:tampered"
            else:
                # An adversary can recompute a public content hash; chain linkage must still reject it.
                event.pop("event_id")
                event.pop("content_identity")
                event["prior_event_id"] = "TEST_FIXTURE:missing-parent"
                digest = hashlib.sha256(json.dumps(event, ensure_ascii=False, sort_keys=True,
                                                    separators=(",", ":")).encode("utf-8")).hexdigest()
                event["event_id"] = event["content_identity"] = "durable_research_case_event:" + digest
            path.write_text(json.dumps(event), encoding="utf-8")
            with pytest.raises(DurableCaseStoreError, match=reason):
                store.replay_case(case["case_id"])
