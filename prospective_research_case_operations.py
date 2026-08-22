"""Deterministic operating manifest for the first real prospective research queue.

This is an operational consumer of the completed workbench.  It selects real
retained packets, prepares the existing AI-input handoff, and records the
human gate without generating a model draft, human decision, durable case, or
future observation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from analyst_research_workbench import CURRENT_RETAINED_SNAPSHOT, AnalystResearchWorkbench


METHOD = "prospective_research_case_operations/v1"
COHORT = (
    ("HPG", 1, "CORPORATE_OFFICIAL_FINANCIAL_AND_NON_AUTHORITATIVE_VALUATION_PROXY"),
    ("VCB", 2, "BANK_OFFICIAL_FINANCIAL_WITH_CORPORATE_ACTION_BLOCKED_VALUATION"),
    ("SSI", 3, "SECURITIES_OFFICIAL_FINANCIAL_WITH_SECTOR_METHOD_NOT_APPLICABLE"),
    ("AAN", 4, "SCENARIO_COVERED_CORPORATE_WITH_RETAINED_EVIDENCE_GAPS"),
    ("AAA", 5, "LOW_OFFICIAL_EVIDENCE_CONTRAST_CASE"),
)


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _future_update_readiness(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Declare possible future evidence relationships without acquiring/observing anything."""
    return [
        {"observation_category": "NEW_FINANCIAL_EVIDENCE", "status": "AWAITING_FUTURE_RETAINED_EVIDENCE",
         "existing_reference_ids": [item["source_artifact_identity"] for item in packet["positive_evidence"] if item["classification"] == "OFFICIAL_FINANCIAL_EVIDENCE"],
         "permitted_relationships": ["SUPPORTS", "CONTRADICTS", "RESOLVES", "DOES_NOT_ADDRESS"]},
        {"observation_category": "CATALYST_OR_EVENT_EVIDENCE", "status": "AWAITING_FUTURE_RETAINED_EVIDENCE",
         "existing_reference_ids": [item["evidence_id"] for item in packet["catalyst_event_state"]],
         "permitted_relationships": ["SUPPORTS", "CONTRADICTS", "RESOLVES", "DOES_NOT_ADDRESS"]},
        {"observation_category": "SCENARIO_RELEVANT_EVIDENCE", "status": "AWAITING_FUTURE_RETAINED_EVIDENCE",
         "existing_reference_ids": [packet["scenario_axis"].get("scenario_content_identity")],
         "permitted_relationships": ["SUPPORTS", "CONTRADICTS", "RESOLVES", "DOES_NOT_ADDRESS"]},
        {"observation_category": "CORPORATE_ACTION_EVIDENCE", "status": "AWAITING_FUTURE_RETAINED_EVIDENCE",
         "existing_reference_ids": [item["evidence_id"] for item in packet["unknown_or_missing_evidence"] if item["classification"] == "EVENT_EVIDENCE"],
         "permitted_relationships": ["SUPPORTS", "CONTRADICTS", "RESOLVES", "DOES_NOT_ADDRESS"]},
        {"observation_category": "SUBSEQUENT_DESCRIPTIVE_MARKET_OBSERVATION", "status": "AWAITING_FUTURE_RETAINED_EVIDENCE",
         "existing_reference_ids": [], "permitted_relationships": ["DOES_NOT_ADDRESS"],
         "boundary": "PRICE_MOVEMENT_CANNOT_PROVE_OR_REFUTE_THESIS"},
    ]


def _known_at(as_of: Mapping[str, Any]) -> dict[str, Any]:
    """Retain exact session identity without inventing an unavailable wall-clock timestamp."""
    return {
        "status": "SESSION_BOUND_KNOWN_AT", "research_session": as_of["research_session"],
        "exact_timestamp": "NOT_RETAINED", "universe_identity": as_of["universe_identity"],
        "reason_code": "NO_EXACT_DECISION_TIME_TIMESTAMP_IN_RETAINED_PACKET",
    }


def build_operating_manifest(workbench: AnalystResearchWorkbench) -> dict[str, Any]:
    """Prepare the real retained cohort for human review without creating cases."""
    records = []
    review_queue = []
    for ticker, priority, rationale in COHORT:
        state = workbench.get_research_state(ticker, as_of=CURRENT_RETAINED_SNAPSHOT)
        handoff = workbench.build_ai_input(ticker, as_of=CURRENT_RETAINED_SNAPSHOT)
        packet = handoff["ai_input"]
        create_gate = state["operation_gates"]["operations"]["CREATE_CASE"]
        if state["as_of"] != packet["as_of"] or state["source_decision_workflow_identity"] != packet["source_decision_workflow_identity"]:
            raise ValueError("OPERATING_MANIFEST_UPSTREAM_IDENTITY_MISMATCH")
        if (create_gate["status"] != "CASE_CREATION_NOT_READY"
                or create_gate["validated_draft_available_count"] != 0
                or create_gate["qualifying_human_review_available_count"] != 0):
            raise ValueError("OPERATING_MANIFEST_REQUIRES_FRESH_UNREVIEWED_COHORT")
        blockers = {
            name: {"eligibility": value["eligibility"], "reason_codes": list(value["reason_codes"])}
            for name, value in packet["blocked_dimensions"].items()
        }
        record = {
            "ticker": ticker, "selection_rationale": rationale, "known_at": _known_at(state["as_of"]),
            "as_of": state["as_of"], "research_state_identity": state["research_state_identity"],
            "source_decision_workflow_identity": state["source_decision_workflow_identity"],
            "ai_input_identity": packet["ai_input_identity"], "model_draft_status": "MODEL_DRAFT_PENDING",
            "validator_status": "NOT_RUN_NO_REAL_MODEL_DRAFT", "human_review_status": "HUMAN_REVIEW_REQUIRED",
            "durable_case_status": "NOT_CREATED_NO_REAL_VALIDATED_DRAFT_AND_QUALIFYING_HUMAN_REVIEW",
            "next_required_action": "HUMAN_REVIEW_OF_REAL_AI_RESEARCH_DRAFT_AFTER_AUTHORIZED_MODEL_OR_ANALYST_DRAFT_INPUT",
            "evidence_inventory": state["evidence_inventory"], "strategy_research_lanes": state["strategy_research_lanes"],
            "scenario_state": state["scenario_axis"], "valuation_state": state["valuation_context"],
            "catalyst_event_state": state["catalyst_event_state"], "positive_evidence": state["positive_evidence"],
            "negative_evidence": state["negative_evidence"], "conflicting_evidence": state["conflicting_evidence"],
            "unresolved_questions": state["unresolved_questions"], "blocked_dimensions": blockers,
            "ai_research_input": packet, "future_update_readiness": _future_update_readiness(packet),
        }
        records.append(record)
        review_queue.append({
            "priority": priority, "ticker": ticker, "priority_basis": "EVIDENCE_AND_AUTHORITY_PATTERN_DIVERSITY_NOT_INVESTMENT_ATTRACTIVENESS",
            "evidence_completeness": {"evidence_item_count": len(packet["evidence"]), "blocked_dimension_count": len(packet["blocked_dimensions"]),
                                      "financial_evidence_status": packet["analytical_eligibility"]["financial_evidence_depth"]["eligibility"]},
            "key_thesis_evidence": packet["positive_evidence"], "counter_evidence": packet["negative_evidence"] + packet["conflicting_evidence"],
            "scenario_availability": packet["scenario_axis"]["qualification_status"],
            "valuation_authority": packet["analytical_eligibility"]["valuation_research"]["authority_ceiling"],
            "valuation_status": packet["analytical_eligibility"]["valuation_research"]["eligibility"],
            "unresolved_questions": packet["unknown_or_missing_evidence"],
            "blocked_dimensions": blockers, "model_draft_status": "MODEL_DRAFT_PENDING",
            "case_creation_prerequisites": ["REAL_AI_RESEARCH_DRAFT", "DETERMINISTIC_VALIDATION_VALID", "QUALIFYING_RECORDED_HUMAN_REVIEW", "EXPLICIT_DURABLE_STORE_ROOT"],
            "required_human_action": "INSPECT_EVIDENCE_AND_COUNTER_EVIDENCE_THEN_RECORD_A_REAL_REVIEW_ONLY_IF_A_REAL_DRAFT_IS_SUPPLIED",
        })
    if len({record["ticker"] for record in records}) != len(COHORT):
        raise ValueError("OPERATING_MANIFEST_DUPLICATE_TICKER")
    learning = workbench.get_learning_summary()
    manifest = {
        "schema_version": "1.0.0", "contract_version": METHOD,
        "cohort": {"cohort_name": "FIRST_REAL_PROSPECTIVE_RESEARCH_OPERATING_COHORT", "tickers": [item[0] for item in COHORT],
                   "selection_basis": "RETAINED_EVIDENCE_AND_AUTHORITY_PATTERN_DIVERSITY", "member_count": len(records),
                   "source_as_of": records[0]["as_of"], "source_decision_workflow_identity": records[0]["source_decision_workflow_identity"]},
        "prompt_contract": handoff["prompt_contract"], "records": records, "human_review_queue": review_queue,
        "learning_baseline": {"real_durable_case_count": 0, "real_reviewed_case_count": 0, "real_human_edit_count": 0,
                             "real_claim_outcome_counts": {}, "real_scenario_or_catalyst_outcomes": {},
                             "reason_code": "NO_REAL_VALIDATED_DRAFT_OR_HUMAN_REVIEW_HAS_BEEN_RECORDED", "workbench_learning_summary": learning},
        "durable_creation_gate": {"status": "HUMAN_REVIEW_REQUIRED", "real_cases_created": 0,
                                  "prohibited_shortcut": "TEST_FIXTURE_OR_IMPLEMENTATION_APPROVAL_CANNOT_CREATE_A_REAL_CASE"},
        "authority_boundary": {"model_drafts_not_fabricated": True, "human_reviews_not_fabricated": True,
                               "no_background_monitoring": True, "recommendation_portfolio_execution": "NOT_EMITTED",
                               "historical_pit_liquidity_valuation_authority": "UNCHANGED"},
        "verdict": "PROSPECTIVE_RESEARCH_CASE_OPERATIONS_READY_FOR_HUMAN_REVIEW",
    }
    manifest["manifest_identity"] = "prospective_research_case_operating_manifest:" + _hash(manifest)
    return manifest
