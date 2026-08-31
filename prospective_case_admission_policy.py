"""Deterministic admission of current Decision Workspace records as durable T0 cases."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping, Sequence

from durable_prospective_research_case_store import DurableProspectiveResearchCaseStore


CONTRACT_VERSION = "prospective_case_admission_policy/v1"
ADMISSIBLE = frozenset({"INITIATE_RESEARCH_CANDIDATE", "ACCUMULATE_RESEARCH_CANDIDATE", "WAIT_FOR_CONFIRMATION", "HIGH_RISK_SPECULATION_ONLY", "AVOID_NEW_ENTRY"})
ROLE_BY_STANCE = {
    "INITIATE_RESEARCH_CANDIDATE": "ACTIVE_RESEARCH_THESIS",
    "ACCUMULATE_RESEARCH_CANDIDATE": "ACTIVE_RESEARCH_THESIS",
    "WAIT_FOR_CONFIRMATION": "WATCH_FOR_CONFIRMATION",
    "HIGH_RISK_SPECULATION_ONLY": "SPECULATIVE_RESEARCH_THESIS",
    "AVOID_NEW_ENTRY": "NEW_ENTRY_VETO_OBSERVATION",
}


class AdmissionPolicyError(ValueError):
    pass


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _identity(payload: dict[str, Any], prefix: str, field: str) -> dict[str, Any]:
    payload[field] = prefix + _hash(payload)
    return payload


def _semantic(card: Mapping[str, Any], role: str) -> dict[str, Any]:
    confirmation = card.get("confirmation") or {}
    invalidation = card.get("invalidation") or {}
    technical = invalidation.get("technical") if isinstance(invalidation, Mapping) else None
    fundamental = invalidation.get("fundamental") if isinstance(invalidation, Mapping) else None
    valuation = card.get("valuation") or {}
    fundamental_state = card.get("fundamental") or {}
    liquidity = card.get("liquidity") or {}
    return {
        "case_role": role, "research_stance": card.get("research_stance"), "research_stance_readiness": card.get("research_stance_readiness"),
        "entry_state": card.get("entry_state"), "entry_action": card.get("entry_action"), "setup_tags": sorted(card.get("setup_tags") or []),
        "confirmation": {key: confirmation.get(key) for key in ("status", "boundary_type", "source_rule", "source_metric", "comparison_operator", "value")},
        "technical_invalidation": {key: (technical or {}).get(key) for key in ("status", "boundary_type", "source_rule", "source_metric", "comparison_operator", "value")},
        "fundamental_invalidation_status": (fundamental or {}).get("status"),
        "valuation": {key: valuation.get(key) for key in ("readiness", "relative_research_state", "supporting_methods", "share_basis")},
        "fundamental": {key: fundamental_state.get(key) for key in ("readiness", "state", "trajectory", "research_fitness")},
        "liquidity": {key: liquidity.get(key) for key in ("readiness", "descriptive_research_state", "exact_execution_capacity_status")},
    }


def material_decision_state_signature(card: Mapping[str, Any], role: str) -> str:
    """Stable T0 semantic state; wording and source formatting are intentionally absent."""
    return "material_decision_state:" + _hash(_semantic(card, role))


def _boundary(kind: str, value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping) or value.get("status") not in {"READY", "CONDITIONAL"}:
        return None
    condition = None
    operator, threshold = value.get("comparison_operator"), value.get("value")
    if isinstance(threshold, (int, float)) and operator in {">=", ">", "<=", "<", "=="}:
        condition = {"field": "close", "operator": operator, "value": threshold}
    return {"role": kind, "kind": "technical", "boundary_identity": "workspace_boundary:" + _hash({k: value.get(k) for k in ("source_rule", "source_metric", "comparison_operator", "value", "boundary_type")}), "condition": condition,
            "source_rule": value.get("source_rule"), "source_metric": value.get("source_metric"), "status": value.get("status")}


def _t0(card: Mapping[str, Any], *, session: str, workspace_identity: str, price: Mapping[str, Any]) -> dict[str, Any]:
    inv = card.get("invalidation") or {}
    return {
        "completed_session": session, "close": dict(price), "research_stance": card.get("research_stance"),
        "entry_state": card.get("entry_state"), "entry_action": card.get("entry_action"), "setup_tags": list(card.get("setup_tags") or []),
        "fundamental_state": dict(card.get("fundamental") or {}), "valuation_state": dict(card.get("valuation") or {}),
        "confirmation_boundary": _boundary("confirmation", card.get("confirmation")),
        "invalidation_boundary": _boundary("invalidation", inv.get("technical") if isinstance(inv, Mapping) else None),
        "market_sector_context": dict(card.get("market_sector") or {}), "catalyst_context": dict(card.get("catalyst") or {}),
        "liquidity_research_state": dict(card.get("liquidity") or {}), "lineage": dict(card.get("lineage") or {}),
        "workspace_projection_identity": workspace_identity,
    }


def _case(card: Mapping[str, Any], *, session: str, admitted_at: str, workspace_identity: str, price: Mapping[str, Any], role: str, signature: str) -> dict[str, Any]:
    t0 = _t0(card, session=session, workspace_identity=workspace_identity, price=price)
    t0["case_role"] = role; t0["material_decision_state_signature"] = signature
    body = {
        "schema_version": "1.0.0", "contract_version": "prospective_research_case_learning_ledger/v1/case", "ticker": card["ticker"],
        "created_at": admitted_at, "known_at": admitted_at, "as_of": session, "source_decision_workflow_identity": workspace_identity,
        "source_ai_input_identity": None, "frozen_universe": session, "frozen_strategy_research_lanes": {}, "frozen_scenario_axis": {},
        "frozen_catalyst_evidence": dict(card.get("catalyst") or {}), "frozen_risks": [], "unresolved_questions": [], "blocked_capabilities": [],
        "original_evidence": [], "original_evidence_ids": [], "original_claims": [], "thesis_claim_ids": [], "counter_thesis_claim_ids": [],
        "ai_human_provenance": {"draft_identity": None, "validation_identity": None, "human_review_identity": None, "human_review_state": "NOT_APPLICABLE_DETERMINISTIC_POLICY_ADMISSION", "human_reviewer": None, "human_modifications": []},
        "lifecycle_state": "OPEN", "outcome_measurement_t0": t0,
        "authority_boundary": {"research_snapshot_not_recommendation": True, "no_historical_pit_backfill": True, "price_movement_is_not_thesis_proof": True, "portfolio_sizing_execution": "NOT_EMITTED", "deterministic_policy_admission": True},
    }
    case_id = "prospective_research_case:" + _hash(body)
    body["case_id"] = case_id; body["case_content_identity"] = case_id
    return body


def _active_signatures(store: DurableProspectiveResearchCaseStore | None) -> set[tuple[str, str, str]]:
    if store is None: return set()
    rows = set()
    for case_id in store.list_case_ids():
        replay = store.replay_case(case_id)
        if replay.get("current_lifecycle_state") in {"THESIS_INVALIDATED", "CLOSED_INCONCLUSIVE", "CLOSED_RESEARCH_COMPLETE"}: continue
        t0 = replay["case"].get("outcome_measurement_t0") or {}
        if t0.get("case_role") and t0.get("material_decision_state_signature"):
            rows.add((replay["case"]["ticker"], t0["case_role"], t0["material_decision_state_signature"]))
    return rows


def apply_admission_policy(workspace: Mapping[str, Any], *, latest_qualified_completed_session: str, price_evidence: Mapping[str, Mapping[str, Any]], admitted_at: str, store: DurableProspectiveResearchCaseStore | None = None) -> dict[str, Any]:
    if workspace.get("contract_version") != "investment_decision_workspace_projection/v1":
        raise AdmissionPolicyError("NO_CURRENT_DECISION_PROJECTION")
    if workspace.get("as_of_session") != latest_qualified_completed_session:
        raise AdmissionPolicyError("DECISION_SESSION_NOT_LATEST_COMPLETED")
    identity = workspace.get("artifact_identity")
    cards = workspace.get("cards")
    if not isinstance(identity, str) or not isinstance(cards, Mapping) or not cards:
        raise AdmissionPolicyError("INPUT_IDENTITY_MISMATCH")
    existing = _active_signatures(store)
    decisions = []
    for ticker, card in sorted(cards.items()):
        if not isinstance(card, Mapping) or card.get("ticker") != ticker:
            decisions.append({"ticker": ticker, "admission_status": "MALFORMED_CASE", "reason": "DECISION_RECORD_MALFORMED"}); continue
        stance = card.get("research_stance")
        if stance == "INSUFFICIENT_EVIDENCE":
            decisions.append({"ticker": ticker, "admission_status": "INSUFFICIENT_EVIDENCE_NOT_ADMITTED", "reason": "NO_EVALUABLE_RESEARCH_THESIS"}); continue
        if stance not in ADMISSIBLE:
            decisions.append({"ticker": ticker, "admission_status": "MALFORMED_CASE", "reason": "UNSUPPORTED_RESEARCH_STANCE"}); continue
        role = ROLE_BY_STANCE[stance]; signature = material_decision_state_signature(card, role); price = price_evidence.get(ticker)
        if not isinstance(price, Mapping) or not isinstance(price.get("close"), (int, float)) or not price.get("price_basis_identity") or not price.get("source_identity"):
            decisions.append({"ticker": ticker, "admission_status": "MALFORMED_CASE", "reason": "T0_CLOSE_PRICE_BASIS_NOT_RETAINED", "case_role": role, "material_decision_state_signature": signature}); continue
        key = (ticker, role, signature)
        if key in existing:
            decisions.append({"ticker": ticker, "admission_status": "CASE_ALREADY_ACTIVE", "case_role": role, "material_decision_state_signature": signature}); continue
        case = _case(card, session=latest_qualified_completed_session, admitted_at=admitted_at, workspace_identity=identity, price=price, role=role, signature=signature)
        admission = {"contract_version": CONTRACT_VERSION, "admission_status": "ADMITTED", "case_id": case["case_id"], "ticker": ticker, "case_role": role, "material_decision_state_signature": signature, "workspace_projection_identity": identity, "latest_qualified_completed_session": latest_qualified_completed_session, "admitted_at": admitted_at}
        _identity(admission, "prospective_case_admission:", "admission_identity")
        decisions.append({**admission, "case": case})
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "latest_qualified_completed_session": latest_qualified_completed_session, "workspace_projection_identity": identity, "decisions": decisions,
                "coverage": {"decision_denominator": len(cards), "stance_distribution": dict(sorted(Counter(str(card.get("research_stance")) for card in cards.values()).items())), "admission_status": dict(sorted(Counter(item["admission_status"] for item in decisions).items())), "case_role": dict(sorted(Counter(item.get("case_role") for item in decisions if item.get("case_role")).items()))},
                "authority_boundary": {"no_cherry_picking": True, "no_retroactive_case_creation": True, "no_probability_score_or_retuning": True, "exact_execution_capacity_not_admission_gate": True}}
    return _identity(artifact, "prospective_case_admission_artifact:", "artifact_identity")


def retain_admitted_cases(artifact: Mapping[str, Any], store: DurableProspectiveResearchCaseStore) -> dict[str, Any]:
    retained, errors = [], []
    for decision in artifact.get("decisions") or []:
        if decision.get("admission_status") != "ADMITTED": continue
        try:
            envelope = store.persist_policy_admitted_case(decision["case"], decision)
            retained.append({"ticker": decision["ticker"], "case_id": decision["case_id"], "store_envelope_identity": envelope["content_identity"]})
        except Exception as exc:
            errors.append({"ticker": decision.get("ticker"), "status": "T0_RETENTION_FAILED", "reason": str(exc)})
    return _identity({"contract_version": CONTRACT_VERSION + "/retention", "admission_artifact_identity": artifact.get("artifact_identity"), "retained": retained, "errors": errors, "store_contract_identity": store._contract()["store_contract_identity"]}, "prospective_case_retention:", "retention_identity")
