"""Append-only prospective research cases and observational learning ledger.

Cases freeze the actual decision/AI/human packet supplied at known-at time.
They are not recommendations and they never upgrade historical PIT, RAW_AS_TRADED,
liquidity, valuation, sizing, portfolio, or execution authority.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from typing import Any, Mapping, Sequence


METHOD = "prospective_research_case_learning_ledger/v1"
LIFECYCLE_STATES = frozenset({"OPEN", "ACTIVE", "NEEDS_MORE_EVIDENCE", "THESIS_STRENGTHENED", "THESIS_WEAKENED", "THESIS_INVALIDATED", "CLOSED_INCONCLUSIVE", "CLOSED_RESEARCH_COMPLETE"})
OUTCOME_STATES = frozenset({"UNRESOLVED", "SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "INVALIDATED_BY_NEW_EVIDENCE", "NOT_TESTABLE", "NOT_APPLICABLE"})
RELATIONSHIPS = frozenset({"SUPPORTS", "CONTRADICTS", "RESOLVES", "DOES_NOT_ADDRESS"})
SCENARIO_CATALYST_STATES = frozenset({"NOT_OBSERVED", "EMERGING", "OBSERVED", "FAILED_TO_MATERIALIZE", "INVALIDATED", "UNKNOWN"})


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_ISO_TIMESTAMP") from exc


def _identity(payload: Mapping[str, Any], field: str, prefix: str) -> bool:
    body = dict(payload)
    return body.pop(field, None) == prefix + _hash(body)


def _case_identity(case: Mapping[str, Any]) -> bool:
    """Validate the frozen content identity without treating it as mutable state."""
    body = dict(case)
    case_id = body.pop("case_id", None)
    content_identity = body.pop("case_content_identity", None)
    expected = "prospective_research_case:" + _hash(body)
    return case_id == expected and content_identity == expected


def _record(decision_artifact: Mapping[str, Any], ticker: str) -> Mapping[str, Any]:
    record = next((row for row in decision_artifact["records"] if row["ticker"] == ticker), None)
    if record is None:
        raise ValueError("TICKER_NOT_IN_DECISION_WORKFLOW")
    return record


def case_readiness(decision_artifact: Mapping[str, Any], ai_input_collection: Mapping[str, Any]) -> dict[str, Any]:
    """Assess createability without persisting or backfilling a case."""
    if ai_input_collection["source_decision_workflow_identity"] != decision_artifact["artifact_identity"]:
        raise ValueError("AI_INPUT_DECISION_WORKFLOW_IDENTITY_MISMATCH")
    packets = {row["ticker"]: row for row in ai_input_collection["packets"]}
    records = {row["ticker"]: row for row in decision_artifact["records"]}
    if set(packets) != set(records):
        raise ValueError("CASE_READINESS_COHORT_MISMATCH")
    rows = []
    for ticker in sorted(records):
        record = records[ticker]
        reasons = [name for name, value in record["analytical_eligibility"].items()
                   if value["eligibility"] in ("BLOCKED", "UNKNOWN")]
        rows.append({"ticker": ticker, "readiness": "CASE_CREATABLE", "reason_codes": reasons,
                     "ai_input_identity": packets[ticker]["ai_input_identity"],
                     "human_review_state": record["human_review"]["workflow_state"],
                     "model_draft_state": "MODEL_DRAFT_PENDING"})
    artifact = {"schema_version": "1.0.0", "contract_version": METHOD + "/readiness",
                "as_of": decision_artifact["as_of"], "source_decision_workflow_identity": decision_artifact["artifact_identity"],
                "source_ai_input_collection_identity": ai_input_collection["artifact_identity"], "records": rows,
                "coverage": {"cohort_count": len(rows), "CASE_CREATABLE": len(rows), "NEEDS_MORE_EVIDENCE": 0, "NOT_CREATABLE": 0,
                             "material_gap_dimension_counts": dict(sorted(Counter(reason for row in rows for reason in row["reason_codes"]).items())),
                             "model_draft_pending_count": len(rows)},
                "authority_boundary": {"readiness_is_not_investment_eligibility": True, "no_cases_persisted_by_readiness": True,
                                       "historical_backfill": "NOT_PERFORMED"},
                "verdict": "PROSPECTIVE_CASE_READINESS_READY"}
    artifact["artifact_identity"] = "prospective_case_readiness:" + _hash(artifact)
    return artifact


def create_research_case(decision_artifact: Mapping[str, Any], ai_input: Mapping[str, Any], *,
                         created_at: str, known_at: str, validated_draft: Mapping[str, Any] | None = None,
                         validation: Mapping[str, Any] | None = None, human_review: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Freeze a prospective T0 case from already-qualified packet identities."""
    if _time(created_at) != _time(known_at):
        raise ValueError("CASE_CREATED_AT_MUST_EQUAL_KNOWN_AT")
    ticker = ai_input["ticker"]
    record = _record(decision_artifact, ticker)
    if ai_input["source_decision_workflow_identity"] != decision_artifact["artifact_identity"]:
        raise ValueError("CASE_AI_INPUT_DECISION_IDENTITY_MISMATCH")
    if ai_input["as_of"] != decision_artifact["as_of"]:
        raise ValueError("CASE_AS_OF_MISMATCH")
    if validated_draft is not None:
        if not validation or validation.get("validation_status") != "VALID" or validation.get("source_ai_input_identity") != ai_input["ai_input_identity"]:
            raise ValueError("CASE_DRAFT_NOT_VALIDATED")
        if validated_draft.get("source_ai_input_identity") != ai_input["ai_input_identity"]:
            raise ValueError("CASE_DRAFT_AI_INPUT_MISMATCH")
        if human_review is not None and (
            human_review.get("source_ai_input_identity") != ai_input["ai_input_identity"]
            or human_review.get("validation_identity") != validation["validation_identity"]
        ):
            raise ValueError("CASE_HUMAN_REVIEW_PROVENANCE_MISMATCH")
        claims = list(validated_draft["claims"])
        ai_provenance = {"draft_identity": validated_draft["draft_identity"], "validation_identity": validation["validation_identity"],
                         "human_review_identity": human_review.get("review_packet_identity") if human_review else None,
                         "human_review_state": human_review.get("review_state") if human_review else "HUMAN_REVIEW_REQUIRED",
                         "human_reviewer": dict(human_review.get("reviewer", {})) if human_review else None,
                         "human_modifications": list(human_review.get("human_modifications", [])) if human_review else []}
    else:
        claims = [{"claim_id": item["evidence_id"], "claim_type": item["classification"], "section": item["section"],
                   "authority_class": item["authority"], "supporting_evidence_ids": [item["evidence_id"]], "origin": "DETERMINISTIC_DECISION_EVIDENCE"}
                  for item in ai_input["evidence"]]
        ai_provenance = {"draft_identity": None, "validation_identity": None, "human_review_identity": None,
                         "human_review_state": "HUMAN_REVIEW_REQUIRED", "human_reviewer": None, "human_modifications": []}
    lifecycle = "NEEDS_MORE_EVIDENCE" if ai_input["blocked_dimensions"] else "OPEN"
    case = {"schema_version": "1.0.0", "contract_version": METHOD + "/case", "ticker": ticker,
            "created_at": created_at, "known_at": known_at, "as_of": decision_artifact["as_of"],
            "source_decision_workflow_identity": decision_artifact["artifact_identity"], "source_ai_input_identity": ai_input["ai_input_identity"],
            "frozen_universe": decision_artifact["as_of"], "frozen_strategy_research_lanes": record["strategy_research_lanes"],
            "frozen_scenario_axis": record["scenario_axis"], "frozen_catalyst_evidence": ai_input["catalyst_event_state"],
            "frozen_risks": ai_input["risks"], "unresolved_questions": ai_input["unknown_or_missing_evidence"],
            "blocked_capabilities": ai_input["blocked_dimensions"], "original_evidence": ai_input["evidence"],
            "original_evidence_ids": [item["evidence_id"] for item in ai_input["evidence"]], "original_claims": claims,
            "thesis_claim_ids": [claim["claim_id"] for claim in claims if claim.get("section") == "THESIS"],
            "counter_thesis_claim_ids": [claim["claim_id"] for claim in claims if claim.get("section") == "COUNTER_THESIS"],
            "ai_human_provenance": ai_provenance, "lifecycle_state": lifecycle,
            "authority_boundary": {"research_snapshot_not_recommendation": True, "no_historical_pit_backfill": True,
                                   "price_movement_is_not_thesis_proof": True, "portfolio_sizing_execution": "NOT_EMITTED"}}
    case["case_id"] = "prospective_research_case:" + _hash(case)
    case["case_content_identity"] = case["case_id"]
    return case


def build_case_update(case: Mapping[str, Any], *, observed_at: str, known_at: str, source_evidence_identity: str,
                      evidence_kind: str, relationships: Sequence[Mapping[str, Any]],
                      scenario_updates: Sequence[Mapping[str, Any]] = (), catalyst_updates: Sequence[Mapping[str, Any]] = (),
                      human_review_identity: str | None = None, fixture: bool = False) -> dict[str, Any]:
    """Create a later immutable update. Fixture updates are never production learning."""
    if _time(observed_at) <= _time(case["known_at"]) or _time(known_at) < _time(observed_at):
        raise ValueError("UPDATE_TEMPORAL_ORDER_INVALID")
    if not source_evidence_identity:
        raise ValueError("UPDATE_SOURCE_EVIDENCE_IDENTITY_REQUIRED")
    original_claims = {claim["claim_id"] for claim in case["original_claims"]}
    for relation in relationships:
        if relation.get("original_claim_id") not in original_claims or relation.get("relationship") not in RELATIONSHIPS or relation.get("claim_outcome") not in OUTCOME_STATES:
            raise ValueError("UPDATE_CLAIM_RELATION_INVALID")
        if evidence_kind == "MARKET_OBSERVATION" and relation["relationship"] != "DOES_NOT_ADDRESS":
            raise ValueError("PRICE_MOVEMENT_CANNOT_PROVE_OR_REFUTE_THESIS")
    if fixture and evidence_kind != "TEST_FIXTURE":
        raise ValueError("FIXTURE_UPDATE_MUST_BE_EXPLICITLY_TEST_FIXTURE")
    for update in list(scenario_updates) + list(catalyst_updates):
        if update.get("state") not in SCENARIO_CATALYST_STATES or update.get("original_evidence_id") not in case["original_evidence_ids"]:
            raise ValueError("SCENARIO_OR_CATALYST_UPDATE_INVALID")
    update = {"schema_version": "1.0.0", "contract_version": METHOD + "/case_update", "case_id": case["case_id"],
              "observed_at": observed_at, "known_at": known_at, "source_evidence_identity": source_evidence_identity,
              "evidence_kind": evidence_kind, "relationships": [dict(item) for item in relationships],
              "scenario_updates": [dict(item) for item in scenario_updates], "catalyst_updates": [dict(item) for item in catalyst_updates],
              "human_review_identity": human_review_identity, "fixture": fixture,
              "relationship_boundary": "DESCRIPTIVE_EVIDENCE_RELATION_NOT_INVESTMENT_PERFORMANCE",
              "lifecycle_transition_basis": "DETERMINISTIC_EVIDENCE_UPDATE" if not human_review_identity else "HUMAN_REVIEWED_EVIDENCE_UPDATE"}
    update["update_identity"] = "prospective_case_update:" + _hash(update)
    return update


def append_case_update(case: Mapping[str, Any], prior_updates: Sequence[Mapping[str, Any]], update: Mapping[str, Any], *, lifecycle_state: str) -> dict[str, Any]:
    if not _case_identity(case):
        raise ValueError("CASE_CONTENT_IDENTITY_INVALID")
    if lifecycle_state not in LIFECYCLE_STATES or update.get("case_id") != case.get("case_id"):
        raise ValueError("CASE_UPDATE_LIFECYCLE_INVALID")
    if not _identity(update, "update_identity", "prospective_case_update:"):
        raise ValueError("CASE_UPDATE_IDENTITY_INVALID")
    if any(item.get("case_id") != case.get("case_id") or not _identity(item, "update_identity", "prospective_case_update:") for item in prior_updates):
        raise ValueError("PRIOR_CASE_UPDATE_IDENTITY_INVALID")
    if any(item.get("update_identity") == update.get("update_identity") for item in prior_updates):
        raise ValueError("CASE_UPDATE_ALREADY_APPENDED")
    if prior_updates and _time(update["observed_at"]) <= _time(prior_updates[-1]["observed_at"]):
        raise ValueError("CASE_UPDATE_OBSERVED_ORDER_INVALID")
    ordered = list(prior_updates) + [dict(update)]
    if any(_time(item["observed_at"]) <= _time(case["known_at"]) for item in ordered):
        raise ValueError("CASE_HISTORY_LOOKAHEAD_VIOLATION")
    history = {"schema_version": "1.0.0", "contract_version": METHOD + "/case_history", "case": dict(case),
               "updates": ordered, "lifecycle_state": lifecycle_state,
               "authority_boundary": {"original_case_immutable": True, "updates_append_only": True,
                                      "price_movement_not_thesis_proof": True, "investment_authority": "NOT_EMITTED"}}
    history["case_history_identity"] = "prospective_case_history:" + _hash(history)
    return history


def build_learning_ledger(histories: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate observations only; fixture updates are separately counted, never learned from."""
    production_relationships = []
    fixture_updates = 0; blocker_counts: Counter[str] = Counter(); lane_gap_counts: Counter[str] = Counter(); human_edit_count = 0
    for history in histories:
        if not _identity(history, "case_history_identity", "prospective_case_history:"):
            raise ValueError("CASE_HISTORY_IDENTITY_INVALID")
        case = history["case"]
        if not _case_identity(case):
            raise ValueError("CASE_CONTENT_IDENTITY_INVALID")
        blocker_counts.update(case["blocked_capabilities"])
        lane_gap_counts.update(name for name, value in case["frozen_strategy_research_lanes"].items() if value["eligibility"] in ("BLOCKED", "UNKNOWN"))
        human_edit_count += len(case["ai_human_provenance"]["human_modifications"])
        for update in history["updates"]:
            if not _identity(update, "update_identity", "prospective_case_update:"):
                raise ValueError("CASE_UPDATE_IDENTITY_INVALID")
            if update["fixture"]:
                fixture_updates += 1
            else:
                production_relationships.extend(update["relationships"])
    ledger = {"schema_version": "1.0.0", "contract_version": METHOD + "/learning_ledger", "case_history_count": len(histories),
              "production_observation_summary": {"claim_outcome_counts": dict(sorted(Counter(item["claim_outcome"] for item in production_relationships).items())),
                                                   "relationship_counts": dict(sorted(Counter(item["relationship"] for item in production_relationships).items())),
                                                   "resolved_claim_count": sum(item["claim_outcome"] != "UNRESOLVED" for item in production_relationships)},
              "patterns": {"authority_blocker_counts": dict(sorted(blocker_counts.items())), "strategy_lane_gap_counts": dict(sorted(lane_gap_counts.items())),
                           "human_edit_count": human_edit_count, "fixture_update_count_excluded_from_learning": fixture_updates},
              "authority_boundary": {"observational_learning_only": True, "fixture_updates_excluded": True,
                                     "no_automatic_model_rule_or_authority_promotion": True, "recommendation_weights_execution": "NOT_EMITTED"},
              "verdict": "PROSPECTIVE_RESEARCH_CASE_LEARNING_LEDGER_READY"}
    ledger["ledger_identity"] = "prospective_research_case_learning_ledger:" + _hash(ledger)
    return ledger
