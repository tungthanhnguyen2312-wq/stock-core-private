"""Analyst-facing orchestration for existing evidence-bound research contracts.

This module is an in-memory operational boundary.  It reuses the decision,
AI/human-review, and prospective-case contracts; it neither recalculates their
analytics nor persists production/runtime data.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from evidence_bound_ai_research_human_review import (
    REVIEW_STATES,
    apply_human_review,
    build_human_review_packet,
    prompt_contract,
    validate_ai_draft as validate_external_ai_draft,
)
from prospective_research_case_learning_ledger import (
    append_case_update as append_immutable_case_update,
    build_case_update,
    build_learning_ledger,
    case_readiness,
    create_research_case,
)


METHOD = "analyst_research_workbench_and_case_operations/v1"
OPERATIONS = frozenset({
    "GET_RESEARCH_STATE", "BUILD_AI_INPUT", "VALIDATE_AI_DRAFT", "RECORD_HUMAN_REVIEW",
    "CREATE_CASE", "GET_CASE", "APPEND_CASE_UPDATE", "GET_CASE_HISTORY", "GET_CLAIM_TRACE",
    "GET_LEARNING_SUMMARY", "GET_COHORT_RESOLUTION",
})
CURRENT_RETAINED_SNAPSHOT = "CURRENT_RETAINED_DECISION_SNAPSHOT"
CASE_REVIEW_STATES = frozenset({"NEEDS_MORE_EVIDENCE", "APPROVED_FOR_INTERNAL_RESEARCH"})


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _with_identity(payload: dict[str, Any], field: str, prefix: str) -> dict[str, Any]:
    payload[field] = prefix + _hash(payload)
    return payload


@dataclass
class AnalystResearchWorkbench:
    """In-memory analyst session over one exact retained decision snapshot."""

    decision_artifact: Mapping[str, Any]
    ai_input_collection: Mapping[str, Any]
    readiness_artifact: Mapping[str, Any]
    case_store: Any | None = None
    _cases: dict[str, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)
    _histories: dict[str, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)
    _registered_update_evidence_identities: frozenset[str] = field(default_factory=frozenset, init=False, repr=False)
    _validated_drafts: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict, init=False, repr=False)
    _human_reviews: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict, init=False, repr=False)

    @classmethod
    def from_artifacts(cls, decision_artifact: Mapping[str, Any], ai_input_collection: Mapping[str, Any], *,
                       retained_update_evidence_identities: Sequence[str] = (), case_store: Any | None = None) -> "AnalystResearchWorkbench":
        if ai_input_collection.get("source_decision_workflow_identity") != decision_artifact.get("artifact_identity"):
            raise ValueError("WORKBENCH_AI_INPUT_DECISION_IDENTITY_MISMATCH")
        decision_tickers = {row["ticker"] for row in decision_artifact.get("records", [])}
        packet_tickers = {row["ticker"] for row in ai_input_collection.get("packets", [])}
        if not decision_tickers or decision_tickers != packet_tickers:
            raise ValueError("WORKBENCH_COHORT_MEMBERSHIP_MISMATCH")
        if decision_artifact.get("as_of") != ai_input_collection.get("as_of"):
            raise ValueError("WORKBENCH_AS_OF_MISMATCH")
        workbench = cls(decision_artifact, ai_input_collection, case_readiness(decision_artifact, ai_input_collection), case_store)
        if case_store is not None and not retained_update_evidence_identities:
            retained_update_evidence_identities = tuple(case_store.registered_update_evidence_identities)
        if case_store is not None and set(retained_update_evidence_identities) != set(case_store.registered_update_evidence_identities):
            raise ValueError("WORKBENCH_DURABLE_STORE_EVIDENCE_REGISTRATION_MISMATCH")
        if not all(isinstance(identity, str) and identity for identity in retained_update_evidence_identities):
            raise ValueError("INVALID_RETAINED_UPDATE_EVIDENCE_IDENTITY")
        workbench._registered_update_evidence_identities = frozenset(retained_update_evidence_identities)
        if case_store is not None:
            for case_id in case_store.list_case_ids():
                replay = case_store.replay_case(case_id)
                workbench._cases[case_id] = replay["case"]
                if replay["history"]["updates"]:
                    workbench._histories[case_id] = replay["history"]
        return workbench

    @property
    def workbench_identity(self) -> str:
        return "analyst_research_workbench:" + _hash({
            "contract_version": METHOD,
            "decision_identity": self.decision_artifact["artifact_identity"],
            "ai_input_identity": self.ai_input_collection["artifact_identity"],
            "readiness_identity": self.readiness_artifact["artifact_identity"],
        })

    def _resolve_ticker_as_of(self, ticker: str, as_of: str | Mapping[str, Any] | None) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        expected = self.decision_artifact["as_of"]
        session = expected["research_session"]
        if as_of not in (None, CURRENT_RETAINED_SNAPSHOT, session) and as_of != expected:
            raise ValueError("AS_OF_SNAPSHOT_UNAVAILABLE")
        record = next((row for row in self.decision_artifact["records"] if row["ticker"] == ticker), None)
        packet = next((row for row in self.ai_input_collection["packets"] if row["ticker"] == ticker), None)
        if record is None or packet is None:
            raise ValueError("TICKER_NOT_IN_CURRENT_RETAINED_DECISION_COHORT")
        return record, packet

    def _case_ids_for_ticker(self, ticker: str) -> list[str]:
        return sorted(case_id for case_id, case in self._cases.items() if case["ticker"] == ticker)

    def _operation_gates(self, ticker: str) -> dict[str, Any]:
        """Report current local-session action readiness without inventing inputs."""
        structural = next(item for item in self.readiness_artifact["records"] if item["ticker"] == ticker)
        validations = self._validated_drafts.get(ticker, {})
        reviews = self._human_reviews.get(ticker, {})
        qualifying_reviews = {
            identity: review for identity, review in reviews.items()
            if review["review_state"] in CASE_REVIEW_STATES and review["validation_identity"] in validations
        }
        case_ids = self._case_ids_for_ticker(ticker)
        create_reasons = []
        if not validations:
            create_reasons.append("NO_VALIDATED_AI_DRAFT_IN_LOCAL_SESSION")
        if not qualifying_reviews:
            create_reasons.append("NO_QUALIFYING_HUMAN_REVIEW_IN_LOCAL_SESSION")
        return {
            "structural_case_eligibility": {
                "status": "CASE_STRUCTURE_ELIGIBLE" if structural["readiness"] == "CASE_CREATABLE" else "CASE_STRUCTURE_NOT_ELIGIBLE",
                "source_prospective_readiness": structural["readiness"],
                "reason_codes": list(structural["reason_codes"]),
                "meaning": "UPSTREAM_DECISION_AND_AI_INPUT_SUPPORT_A_PROSPECTIVE_CASE_SHAPE_NOT_OPERATIONAL_CREATE_CASE_READINESS",
            },
            "operations": {
                "GET_RESEARCH_STATE": {"status": "AVAILABLE", "reason_codes": []},
                "BUILD_AI_INPUT": {"status": "AVAILABLE", "reason_codes": []},
                "VALIDATE_AI_DRAFT": {"status": "READY", "reason_codes": ["EXTERNAL_UNTRUSTED_DRAFT_REQUIRED"],
                                      "validated_draft_available_count": len(validations)},
                "RECORD_HUMAN_REVIEW": {"status": "READY" if validations else "NOT_READY",
                                        "reason_codes": [] if validations else ["NO_VALIDATED_AI_DRAFT_IN_LOCAL_SESSION"],
                                        "validated_draft_available_count": len(validations)},
                "CREATE_CASE": {"status": "CASE_CREATION_READY" if qualifying_reviews else "CASE_CREATION_NOT_READY",
                                "reason_codes": create_reasons, "validated_draft_available_count": len(validations),
                                "qualifying_human_review_available_count": len(qualifying_reviews)},
                "GET_CASE": {"status": "AVAILABLE" if case_ids else "NOT_READY",
                             "reason_codes": [] if case_ids else ["NO_LOCAL_CASE_IN_SESSION"], "local_case_ids": case_ids},
                "APPEND_CASE_UPDATE": {"status": ("READY" if case_ids and self._registered_update_evidence_identities else
                                                   "READY_FOR_TEST_FIXTURE_ONLY" if case_ids else "NOT_READY"),
                                       "reason_codes": ([] if case_ids and self._registered_update_evidence_identities else
                                                        (["NO_LOCAL_CASE_IN_SESSION"] if not case_ids else ["NO_REGISTERED_RETAINED_LATER_EVIDENCE_IDENTITY"])),
                                       "local_case_ids": case_ids},
                "GET_CASE_HISTORY": {"status": "AVAILABLE" if case_ids else "NOT_READY",
                                     "reason_codes": ([] if any(case_id in self._histories for case_id in case_ids) else
                                                      (["NO_UPDATES_RECORDED"] if case_ids else ["NO_LOCAL_CASE_IN_SESSION"]))},
                "GET_CLAIM_TRACE": {"status": "AVAILABLE" if case_ids else "NOT_READY",
                                    "reason_codes": [] if case_ids else ["NO_LOCAL_CASE_IN_SESSION"]},
                "GET_LEARNING_SUMMARY": {"status": "AVAILABLE", "reason_codes": [], "local_case_history_count": len(self._histories)},
            },
        }

    def get_research_state(self, ticker: str, *, as_of: str | Mapping[str, Any] | None = CURRENT_RETAINED_SNAPSHOT) -> dict[str, Any]:
        """Return a coherent, non-lossy state view for one exact cohort member."""
        record, packet = self._resolve_ticker_as_of(ticker, as_of)
        case_ids = self._case_ids_for_ticker(ticker)
        operation_gates = self._operation_gates(ticker)
        state = {
            "contract_version": METHOD + "/research_state", "operation": "GET_RESEARCH_STATE",
            "workbench_identity": self.workbench_identity, "ticker": ticker,
            "snapshot_selection": CURRENT_RETAINED_SNAPSHOT, "as_of": copy.deepcopy(self.decision_artifact["as_of"]),
            "universe_membership": copy.deepcopy(record["universe_membership"]),
            "source_decision_workflow_identity": self.decision_artifact["artifact_identity"],
            "ai_input_identity": packet["ai_input_identity"], "evidence_inventory": copy.deepcopy(record["evidence_inventory"]),
            "analytical_eligibility": copy.deepcopy(record["analytical_eligibility"]),
            "strategy_research_lanes": copy.deepcopy(record["strategy_research_lanes"]),
            "positive_evidence": copy.deepcopy(packet["positive_evidence"]),
            "negative_evidence": copy.deepcopy(packet["negative_evidence"]),
            "conflicting_evidence": copy.deepcopy(packet["conflicting_evidence"]),
            "scenario_axis": copy.deepcopy(packet["scenario_axis"]), "valuation_context": copy.deepcopy(packet["valuation_state"]),
            "catalyst_event_state": copy.deepcopy(packet["catalyst_event_state"]), "risks": copy.deepcopy(packet["risks"]),
            "unresolved_questions": copy.deepcopy(packet["unknown_or_missing_evidence"]),
            "blocked_capabilities": copy.deepcopy(packet["blocked_dimensions"]),
            "human_review_state": copy.deepcopy(packet["human_review"]),
            "prospective_case_state": {"state": "NO_LOCAL_CASE" if not case_ids else "LOCAL_CASE_RECORDED", "case_ids": case_ids},
            "operation_gates": operation_gates,
            "authority_limitations": copy.deepcopy(packet["authority_boundary"]),
            "snapshot_boundary": {"separate_2026_08_21_524_member_shadow_snapshot": "NOT_SUBSTITUTED_OR_MIXED", "selection_is_exact": True},
        }
        return _with_identity(state, "research_state_identity", "analyst_research_state:")

    def build_ai_input(self, ticker: str, *, as_of: str | Mapping[str, Any] | None = CURRENT_RETAINED_SNAPSHOT) -> dict[str, Any]:
        _, packet = self._resolve_ticker_as_of(ticker, as_of)
        result = {"contract_version": METHOD + "/ai_handoff", "operation": "BUILD_AI_INPUT", "workbench_identity": self.workbench_identity,
                  "ai_input": copy.deepcopy(packet), "prompt_contract": prompt_contract(),
                  "authority_boundary": {"live_model_call_required": False, "draft_must_be_validated_before_human_review": True}}
        return _with_identity(result, "ai_handoff_identity", "analyst_ai_handoff:")

    def validate_ai_draft(self, ticker: str, draft: Mapping[str, Any], *, as_of: str | Mapping[str, Any] | None = CURRENT_RETAINED_SNAPSHOT) -> dict[str, Any]:
        _, packet = self._resolve_ticker_as_of(ticker, as_of)
        validation = validate_external_ai_draft(packet, draft)
        if validation["validation_status"] == "VALID":
            self._validated_drafts.setdefault(ticker, {})[validation["validation_identity"]] = {
                "draft": copy.deepcopy(dict(draft)), "validation": copy.deepcopy(validation),
            }
        result = {"contract_version": METHOD + "/ai_validation", "operation": "VALIDATE_AI_DRAFT", "workbench_identity": self.workbench_identity,
                  "ticker": ticker, "source_ai_input_identity": packet["ai_input_identity"], "validation": validation}
        return _with_identity(result, "workbench_validation_identity", "analyst_ai_validation:")

    def record_human_review(self, ticker: str, draft: Mapping[str, Any], *, reviewer_identity: str, review_timestamp: str,
                            review_state: str, reviewer_notes: str | None = None,
                            material_claim_edits: Sequence[Mapping[str, Any]] | None = None,
                            as_of: str | Mapping[str, Any] | None = CURRENT_RETAINED_SNAPSHOT) -> dict[str, Any]:
        if review_state not in REVIEW_STATES - {"DRAFT", "HUMAN_REVIEW_REQUIRED"}:
            raise ValueError("INVALID_HUMAN_REVIEW_STATE")
        _, packet = self._resolve_ticker_as_of(ticker, as_of)
        validation_result = self.validate_ai_draft(ticker, draft, as_of=as_of)
        validation = validation_result["validation"]
        review_packet = build_human_review_packet(packet, draft, validation)
        review = apply_human_review(review_packet, reviewer_identity=reviewer_identity, review_timestamp=review_timestamp,
                                    review_state=review_state, reviewer_notes=reviewer_notes,
                                    material_claim_edits=list(material_claim_edits or []))
        self._human_reviews.setdefault(ticker, {})[review["review_packet_identity"]] = copy.deepcopy(review)
        result = {"contract_version": METHOD + "/human_review", "operation": "RECORD_HUMAN_REVIEW", "workbench_identity": self.workbench_identity,
                  "ticker": ticker, "validation": validation, "human_review": review}
        return _with_identity(result, "workbench_human_review_identity", "analyst_human_review:")

    def create_case(self, ticker: str, draft: Mapping[str, Any], validation_result: Mapping[str, Any], human_review: Mapping[str, Any], *,
                    created_at: str, known_at: str, as_of: str | Mapping[str, Any] | None = CURRENT_RETAINED_SNAPSHOT,
                    outcome_measurement_t0: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Create one local immutable case only from a validated reviewed draft."""
        _, packet = self._resolve_ticker_as_of(ticker, as_of)
        expected_validation = validate_external_ai_draft(packet, draft)
        local_validation = self._validated_drafts.get(ticker, {}).get(expected_validation["validation_identity"])
        if (validation_result.get("validation_identity") != expected_validation["validation_identity"]
                or expected_validation["validation_status"] != "VALID" or local_validation is None):
            raise ValueError("CASE_REQUIRES_CURRENT_VALIDATED_AI_DRAFT")
        if human_review.get("source_ai_input_identity") != packet["ai_input_identity"] or human_review.get("validation_identity") != expected_validation["validation_identity"]:
            raise ValueError("CASE_HUMAN_REVIEW_LINEAGE_MISMATCH")
        if human_review.get("review_state") not in CASE_REVIEW_STATES:
            raise ValueError("CASE_REQUIRES_RECORDED_HUMAN_REVIEW_STATE")
        if human_review.get("review_packet_identity") not in self._human_reviews.get(ticker, {}):
            raise ValueError("CASE_REQUIRES_RECORDED_HUMAN_REVIEW_STATE")
        case = create_research_case(self.decision_artifact, packet, created_at=created_at, known_at=known_at,
                                    validated_draft=draft, validation=expected_validation, human_review=human_review,
                                    outcome_measurement_t0=outcome_measurement_t0)
        if self.case_store is not None:
            self.case_store.persist_case(case, draft, expected_validation, human_review)
        self._cases.setdefault(case["case_id"], case)
        result = {"contract_version": METHOD + "/case_operation", "operation": "CREATE_CASE", "workbench_identity": self.workbench_identity,
                  "case": copy.deepcopy(self._cases[case["case_id"]]), "persistence_boundary": "IN_MEMORY_LOCAL_SESSION_ONLY"}
        return _with_identity(result, "case_operation_identity", "analyst_case_operation:")

    def get_case(self, case_id: str) -> dict[str, Any]:
        case = self._cases.get(case_id)
        if case is None:
            raise ValueError("CASE_NOT_FOUND_IN_LOCAL_WORKBENCH_SESSION")
        result = {"contract_version": METHOD + "/case_operation", "operation": "GET_CASE", "workbench_identity": self.workbench_identity,
                  "case": copy.deepcopy(case), "history_available": case_id in self._histories,
                  "persistence_boundary": "IN_MEMORY_LOCAL_SESSION_ONLY"}
        return _with_identity(result, "case_operation_identity", "analyst_case_operation:")

    def append_case_update(self, case_id: str, *, observed_at: str, known_at: str, source_evidence_identity: str,
                           evidence_kind: str, relationships: Sequence[Mapping[str, Any]], lifecycle_state: str,
                           scenario_updates: Sequence[Mapping[str, Any]] = (), catalyst_updates: Sequence[Mapping[str, Any]] = (),
                           human_review_identity: str | None = None, fixture: bool = False) -> dict[str, Any]:
        case = self._cases.get(case_id)
        if case is None:
            raise ValueError("CASE_NOT_FOUND_IN_LOCAL_WORKBENCH_SESSION")
        if fixture:
            if not source_evidence_identity.startswith("fixture:"):
                raise ValueError("TEST_FIXTURE_EVIDENCE_IDENTITY_REQUIRED")
        elif source_evidence_identity not in self._registered_update_evidence_identities:
            raise ValueError("UPDATE_EVIDENCE_IDENTITY_NOT_REGISTERED")
        update = build_case_update(case, observed_at=observed_at, known_at=known_at,
                                   source_evidence_identity=source_evidence_identity, evidence_kind=evidence_kind,
                                   relationships=relationships, scenario_updates=scenario_updates,
                                   catalyst_updates=catalyst_updates, human_review_identity=human_review_identity, fixture=fixture)
        if self.case_store is not None:
            history = self.case_store.append_case_update(case_id, update, lifecycle_state=lifecycle_state)
        else:
            prior = self._histories.get(case_id, {}).get("updates", [])
            history = append_immutable_case_update(case, prior, update, lifecycle_state=lifecycle_state)
        self._histories[case_id] = history
        result = {"contract_version": METHOD + "/case_operation", "operation": "APPEND_CASE_UPDATE", "workbench_identity": self.workbench_identity,
                  "case_id": case_id, "update": copy.deepcopy(update), "history_identity": history["case_history_identity"],
                  "persistence_boundary": "IN_MEMORY_LOCAL_SESSION_ONLY"}
        return _with_identity(result, "case_operation_identity", "analyst_case_operation:")

    def get_case_history(self, case_id: str) -> dict[str, Any]:
        case = self._cases.get(case_id)
        if case is None:
            raise ValueError("CASE_NOT_FOUND_IN_LOCAL_WORKBENCH_SESSION")
        if self.case_store is not None:
            history = self.case_store.replay_case(case_id)["history"]
            self._histories[case_id] = history
        else:
            history = self._histories.get(case_id)
        result = {"contract_version": METHOD + "/case_operation", "operation": "GET_CASE_HISTORY", "workbench_identity": self.workbench_identity,
                  "case_id": case_id, "history": copy.deepcopy(history), "history_state": "NO_UPDATES_RECORDED" if history is None else "APPEND_ONLY_UPDATES_RECORDED"}
        return _with_identity(result, "case_operation_identity", "analyst_case_operation:")

    def get_claim_trace(self, case_id: str, claim_id: str) -> dict[str, Any]:
        case = self._cases.get(case_id)
        if case is None:
            raise ValueError("CASE_NOT_FOUND_IN_LOCAL_WORKBENCH_SESSION")
        claim = next((item for item in case["original_claims"] if item["claim_id"] == claim_id), None)
        if claim is None:
            raise ValueError("CLAIM_NOT_IN_CASE")
        history = self._histories.get(case_id)
        observations = [] if history is None else [
            {"update_identity": update["update_identity"], "observed_at": update["observed_at"], "known_at": update["known_at"],
             "source_evidence_identity": update["source_evidence_identity"], "evidence_kind": update["evidence_kind"],
             "fixture": update["fixture"], "relationship": relation}
            for update in history["updates"] for relation in update["relationships"]
            if relation["original_claim_id"] == claim_id
        ]
        trace = {"contract_version": METHOD + "/claim_trace", "operation": "GET_CLAIM_TRACE", "workbench_identity": self.workbench_identity,
                 "case_id": case_id, "original_claim": copy.deepcopy(claim), "original_evidence_ids": list(claim["supporting_evidence_ids"]),
                 "ai_human_provenance": copy.deepcopy(case["ai_human_provenance"]), "later_observations": observations,
                 "trace_boundary": "LATER_OBSERVATIONS_ARE_NOT_INVESTMENT_PERFORMANCE"}
        return _with_identity(trace, "claim_trace_identity", "analyst_claim_trace:")

    def get_learning_summary(self) -> dict[str, Any]:
        ledger = self.case_store.build_learning_ledger() if self.case_store is not None else build_learning_ledger([self._histories[case_id] for case_id in sorted(self._histories)])
        result = {"contract_version": METHOD + "/learning_summary", "operation": "GET_LEARNING_SUMMARY", "workbench_identity": self.workbench_identity,
                  "local_case_count": len(self._cases), "local_case_history_count": len(self._histories), "learning_ledger": ledger,
                  "read_only_boundary": {"observational_only": True, "no_model_weights_rules_or_authority_promotion": True,
                                          "recommendation_portfolio_execution": "NOT_EMITTED"}}
        return _with_identity(result, "learning_summary_identity", "analyst_learning_summary:")

    def get_cohort_resolution(self) -> dict[str, Any]:
        rows = []
        for item in self.readiness_artifact["records"]:
            gates = self._operation_gates(item["ticker"])
            create = gates["operations"]["CREATE_CASE"]
            rows.append({"ticker": item["ticker"], "research_state": "AVAILABLE", "ai_input": "AVAILABLE",
                         "case_structure_eligibility": gates["structural_case_eligibility"]["status"],
                         "validated_ai_draft": "AVAILABLE" if create["validated_draft_available_count"] else "NOT_AVAILABLE",
                         "qualifying_human_review": "AVAILABLE" if create["qualifying_human_review_available_count"] else "NOT_AVAILABLE",
                         "case_creation_readiness": create["status"], "existing_local_case_count": len(self._case_ids_for_ticker(item["ticker"])),
                         "blocked_dimension_names": list(item["reason_codes"]), "not_ready_reason_codes": list(create["reason_codes"])})
        not_ready_reasons = Counter(reason for row in rows for reason in row["not_ready_reason_codes"])
        result = {"contract_version": METHOD + "/cohort_resolution", "operation": "GET_COHORT_RESOLUTION", "workbench_identity": self.workbench_identity,
                  "as_of": copy.deepcopy(self.decision_artifact["as_of"]), "records": rows,
                  "coverage": {"cohort_count": len(rows), "research_state_available": len(rows), "ai_input_available": len(rows),
                               "case_structure_eligible": sum(row["case_structure_eligibility"] == "CASE_STRUCTURE_ELIGIBLE" for row in rows),
                               "validated_ai_draft_available": sum(row["validated_ai_draft"] == "AVAILABLE" for row in rows),
                               "qualifying_human_review_available": sum(row["qualifying_human_review"] == "AVAILABLE" for row in rows),
                               "case_creation_ready": sum(row["case_creation_readiness"] == "CASE_CREATION_READY" for row in rows),
                               "existing_local_case_count": sum(row["existing_local_case_count"] for row in rows),
                               "case_creation_not_ready_reason_counts": dict(sorted(not_ready_reasons.items()))},
                  "authority_boundary": {"no_ai_drafts_or_cases_created_by_discovery": True, "readiness_not_investment_eligibility": True,
                                         "registered_later_evidence_identity_count": len(self._registered_update_evidence_identities)}}
        return _with_identity(result, "cohort_resolution_identity", "analyst_cohort_resolution:")


def build_current_workbench(*, case_store: Any | None = None, retained_update_evidence_identities: Sequence[str] = ()) -> AnalystResearchWorkbench:
    """Load the one retained 2026-08-20 decision snapshot for a local session."""
    from tools.run_evidence_bound_ai_research_human_review import run as ai_run
    from tools.run_evidence_gated_research_decision_workflow import run as decision_run

    return AnalystResearchWorkbench.from_artifacts(decision_run(), ai_run(), case_store=case_store,
                                                   retained_update_evidence_identities=retained_update_evidence_identities)
