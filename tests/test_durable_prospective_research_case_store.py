import copy
import tempfile
from pathlib import Path

import pytest

from analyst_research_workbench import build_current_workbench
from durable_prospective_research_case_store import DurableCaseStoreError, DurableProspectiveResearchCaseStore


SECTIONS = (
    "RESEARCH_CONTEXT", "THESIS", "COUNTER_THESIS", "CATALYSTS", "RISKS", "SCENARIO_INTERPRETATION",
    "VALUATION_CONTEXT", "MARKET_CONTEXT", "UNRESOLVED_QUESTIONS", "EVIDENCE_GAPS",
    "WHAT_WOULD_CHANGE_THE_VIEW", "HUMAN_REVIEW_REQUIRED",
)


def _draft(packet):
    claims = [
        {"claim_id": f"durable-claim-{index}", "claim_type": "INFERENCE",
         "section": "COUNTER_THESIS" if item["evidence_id"] in packet["mandatory_counter_evidence_ids"] else "THESIS",
         "claim_text": "TEST_FIXTURE retains real packet evidence without an investment conclusion.",
         "supporting_evidence_ids": [item["evidence_id"]], "conflicting_evidence_ids": [],
         "authority_class": item["authority"], "referenced_dimension": None, "numeric_evidence_ids": []}
        for index, item in enumerate(packet["evidence"])
    ]
    draft = {"source_ai_input_identity": packet["ai_input_identity"], "claims": claims,
             "sections": {section: [] for section in SECTIONS}, "fixture": True,
             "dimension_interpretations": {name: item["eligibility"] for name, item in packet["analytical_eligibility"].items()},
             "human_review_required": True, "draft_identity": "TEST_FIXTURE:durable_draft:" + packet["ai_input_identity"]}
    draft["sections"]["THESIS"] = [item["claim_id"] for item in claims if item["section"] == "THESIS"]
    draft["sections"]["COUNTER_THESIS"] = [item["claim_id"] for item in claims if item["section"] == "COUNTER_THESIS"]
    return draft


def _create_case(workbench, ticker):
    packet = workbench.build_ai_input(ticker)["ai_input"]
    draft = _draft(packet)
    validation = workbench.validate_ai_draft(ticker, draft)["validation"]
    review = workbench.record_human_review(
        ticker, draft, reviewer_identity="analyst:fixture", review_timestamp="2026-08-22T08:55:00+07:00",
        review_state="NEEDS_MORE_EVIDENCE", reviewer_notes="Fixture review keeps all blockers.",
        material_claim_edits=[{"claim_id": draft["claims"][0]["claim_id"], "replacement_text": "TEST_FIXTURE human clarification."}],
    )["human_review"]
    return workbench.create_case(
        ticker, draft, validation, review, created_at="2026-08-22T09:00:00+07:00", known_at="2026-08-22T09:00:00+07:00",
    )["case"]


def test_restart_safe_replay_for_representative_real_packet_fixtures_and_fixture_exclusion():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "durable-case-store"
        first_store = DurableProspectiveResearchCaseStore(root)
        first_workbench = build_current_workbench(case_store=first_store)
        cases = {_ticker: _create_case(first_workbench, _ticker) for _ticker in ("HPG", "VCB", "SSI", "AAN", "AAA")}
        first_replay = first_store.replay_case(cases["HPG"]["case_id"])
        assert first_store.live_readiness()["verdict"] == "DURABLE_CASE_SYSTEM_READY"
        assert first_store.build_learning_ledger()["case_history_count"] == 0

        second_store = DurableProspectiveResearchCaseStore(root)
        second_workbench = build_current_workbench(case_store=second_store)
        assert second_workbench.get_case(cases["VCB"]["case_id"])["case"]["ticker"] == "VCB"
        claim = cases["HPG"]["original_claims"][0]
        second_workbench.append_case_update(
            cases["HPG"]["case_id"], observed_at="2026-08-23T09:00:00+07:00", known_at="2026-08-23T10:00:00+07:00",
            source_evidence_identity="fixture:durable-later-evidence", evidence_kind="TEST_FIXTURE",
            relationships=[{"original_claim_id": claim["claim_id"], "relationship": "DOES_NOT_ADDRESS", "claim_outcome": "UNRESOLVED"}],
            scenario_updates=[{"original_evidence_id": cases["HPG"]["original_evidence_ids"][0], "state": "EMERGING"}],
            catalyst_updates=[{"original_evidence_id": cases["HPG"]["original_evidence_ids"][0], "state": "NOT_OBSERVED"}],
            lifecycle_state="ACTIVE", fixture=True,
        )
        third_store = DurableProspectiveResearchCaseStore(root)
        third_replay = third_store.replay_case(cases["HPG"]["case_id"])
        fourth_replay = DurableProspectiveResearchCaseStore(root).replay_case(cases["HPG"]["case_id"])
        assert third_replay["history"]["updates"][0]["update_identity"]
        assert third_replay["history"]["case"] == first_replay["history"]["case"]
        assert third_replay["replay_identity"] == fourth_replay["replay_identity"]
        assert third_store.build_learning_ledger()["case_history_count"] == 0
        assert len(third_store.list_case_ids()) == 5


def test_durable_store_rejects_t0_mutation_duplicate_case_unknown_case_and_duplicate_event():
    with tempfile.TemporaryDirectory() as directory:
        store = DurableProspectiveResearchCaseStore(Path(directory) / "store")
        workbench = build_current_workbench(case_store=store)
        case = _create_case(workbench, "HPG")
        envelope = store.load_case_envelope(case["case_id"])
        mutated = copy.deepcopy(envelope["case"])
        mutated["ticker"] = "AAA"
        with pytest.raises(DurableCaseStoreError, match="CASE_CONTENT_IDENTITY_INVALID"):
            store.persist_case(mutated, envelope["ai_draft"], envelope["validation"], envelope["human_review"])
        with pytest.raises(DurableCaseStoreError, match="DUPLICATE_CONTENT_INSERTION"):
            store.persist_case(envelope["case"], envelope["ai_draft"], envelope["validation"], envelope["human_review"])
        claim = case["original_claims"][0]
        update = workbench.append_case_update(
            case["case_id"], observed_at="2026-08-23T09:00:00+07:00", known_at="2026-08-23T10:00:00+07:00",
            source_evidence_identity="fixture:duplicate-event", evidence_kind="TEST_FIXTURE",
            relationships=[{"original_claim_id": claim["claim_id"], "relationship": "DOES_NOT_ADDRESS", "claim_outcome": "UNRESOLVED"}],
            lifecycle_state="ACTIVE", fixture=True,
        )["update"]
        with pytest.raises(DurableCaseStoreError, match="CASE_UPDATE_ALREADY_APPENDED"):
            store.append_case_update(case["case_id"], update, lifecycle_state="ACTIVE")
        with pytest.raises(DurableCaseStoreError, match="CASE_NOT_FOUND"):
            store.append_case_update("prospective_research_case:unknown", update, lifecycle_state="ACTIVE")


def test_durable_store_rejects_unregistered_evidence_timestamp_reversal_and_tamper():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "store"
        store = DurableProspectiveResearchCaseStore(root)
        workbench = build_current_workbench(case_store=store)
        case = _create_case(workbench, "SSI")
        claim = case["original_claims"][0]
        with pytest.raises(ValueError, match="UPDATE_EVIDENCE_IDENTITY_NOT_REGISTERED"):
            workbench.append_case_update(
                case["case_id"], observed_at="2026-08-23T09:00:00+07:00", known_at="2026-08-23T10:00:00+07:00",
                source_evidence_identity="unregistered:evidence", evidence_kind="OFFICIAL_DOCUMENT",
                relationships=[{"original_claim_id": claim["claim_id"], "relationship": "DOES_NOT_ADDRESS", "claim_outcome": "UNRESOLVED"}], lifecycle_state="ACTIVE",
            )
        with pytest.raises(ValueError, match="UPDATE_TEMPORAL_ORDER_INVALID"):
            workbench.append_case_update(
                case["case_id"], observed_at=case["known_at"], known_at=case["known_at"],
                source_evidence_identity="fixture:bad-time", evidence_kind="TEST_FIXTURE",
                relationships=[{"original_claim_id": claim["claim_id"], "relationship": "DOES_NOT_ADDRESS", "claim_outcome": "UNRESOLVED"}], lifecycle_state="ACTIVE", fixture=True,
            )
        path = next(store.cases_dir.glob("*.json"))
        path.write_text('{"tampered":true}\n', encoding="utf-8")
        with pytest.raises(DurableCaseStoreError, match="CASE_ENVELOPE_CONTENT_IDENTITY_INVALID"):
            store.load_case_envelope(case["case_id"])
