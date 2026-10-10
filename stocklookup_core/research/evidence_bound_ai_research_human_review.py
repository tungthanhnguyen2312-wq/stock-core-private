"""Evidence-bound AI draft and human-review contracts.

This module is a downstream consumer of the deterministic evidence-gated
decision workflow.  It neither calls a model nor grants data, recommendation,
portfolio, sizing, execution, liquidity, valuation, or PIT authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any, Mapping


METHOD = "evidence_bound_ai_research_human_review/v1"
CLAIM_TYPES = frozenset({"FACT", "DATA_WARNING", "INFERENCE", "HYPOTHESIS"})
REVIEW_STATES = frozenset({"DRAFT", "HUMAN_REVIEW_REQUIRED", "NEEDS_MORE_EVIDENCE", "APPROVED_FOR_INTERNAL_RESEARCH", "REJECTED"})
FORBIDDEN_OUTPUT_PATTERNS = (
    r"\bBUY\b", r"\bSELL\b", r"\bHOLD\b", r"target price", r"expected return",
    r"scenario probability", r"position size", r"execute(?:\s+a)?\s+trade",
)
NUMBER_RE = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?")


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _evidence_id(ticker: str, section: str, index: int) -> str:
    return f"decision_evidence:{ticker}:{section}:{index}"


def _flatten_case_evidence(record: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    evidence: list[dict[str, Any]] = []
    required_counter: list[str] = []
    for section in ("POSITIVE_EVIDENCE", "NEGATIVE_EVIDENCE", "CONFLICTING_EVIDENCE", "UNKNOWN_OR_MISSING", "CATALYST_EVIDENCE", "RISK_EVIDENCE"):
        for index, item in enumerate(record["research_case"][section]):
            evidence_id = _evidence_id(record["ticker"], section, index)
            evidence.append({"evidence_id": evidence_id, "section": section, "classification": item["classification"],
                             "observed_value": item["observed_value"], "authority": item["authority"],
                             "source_artifact_identity": item["source_artifact_identity"], "reason_codes": item["reason_codes"]})
            if section in ("NEGATIVE_EVIDENCE", "CONFLICTING_EVIDENCE"):
                required_counter.append(evidence_id)
    return evidence, required_counter


def build_ai_input_packet(decision_artifact: Mapping[str, Any], ticker: str) -> dict[str, Any]:
    """Content-address a whitelisted AI input; reject unknown tickers."""
    record = next((row for row in decision_artifact["records"] if row["ticker"] == ticker), None)
    if record is None:
        raise ValueError("TICKER_NOT_IN_DECISION_WORKFLOW")
    evidence, required_counter = _flatten_case_evidence(record)
    evidence_by_section = {section: [item for item in evidence if item["section"] == section] for section in
                           ("POSITIVE_EVIDENCE", "NEGATIVE_EVIDENCE", "CONFLICTING_EVIDENCE", "UNKNOWN_OR_MISSING", "CATALYST_EVIDENCE", "RISK_EVIDENCE")}
    blocked = {name: value for name, value in record["analytical_eligibility"].items()
               if value["eligibility"] in ("BLOCKED", "UNKNOWN", "NOT_APPLICABLE")}
    packet = {
        "schema_version": "1.0.0", "contract_version": METHOD + "/ai_input",
        "ticker": ticker, "as_of": decision_artifact["as_of"],
        "source_decision_workflow_identity": decision_artifact["artifact_identity"],
        "evidence_inventory": record["evidence_inventory"],
        "analytical_eligibility": record["analytical_eligibility"],
        "strategy_research_lanes": record["strategy_research_lanes"],
        "setup_context": record["setup_context"], "scenario_axis": record["scenario_axis"],
        "valuation_state": record["valuation_state"],
        "evidence": evidence, "evidence_by_section": evidence_by_section,
        "positive_evidence": evidence_by_section["POSITIVE_EVIDENCE"], "negative_evidence": evidence_by_section["NEGATIVE_EVIDENCE"],
        "conflicting_evidence": evidence_by_section["CONFLICTING_EVIDENCE"], "unknown_or_missing_evidence": evidence_by_section["UNKNOWN_OR_MISSING"],
        "catalyst_event_state": evidence_by_section["CATALYST_EVIDENCE"], "risks": evidence_by_section["RISK_EVIDENCE"],
        "mandatory_counter_evidence_ids": required_counter,
        "blocked_dimensions": blocked, "human_review": record["human_review"],
        "authority_boundary": {
            "ai_is_not_factual_or_numerical_authority": True,
            "must_preserve_unknown_blocked_partial_not_applicable": True,
            "forbidden_outputs": ["BUY_SELL_HOLD", "TARGET_PRICE", "EXPECTED_RETURN", "SCENARIO_PROBABILITY", "POSITION_SIZE", "EXECUTION"],
            "valuation_proxy_must_remain_non_authoritative": True,
        },
    }
    packet["ai_input_sha256"] = _hash(packet)
    packet["ai_input_identity"] = "evidence_bound_ai_input:" + packet["ai_input_sha256"]
    return packet


def build_ai_input_collection(decision_artifact: Mapping[str, Any]) -> dict[str, Any]:
    packets = [build_ai_input_packet(decision_artifact, row["ticker"]) for row in decision_artifact["records"]]
    artifact = {
        "schema_version": "1.0.0", "contract_version": METHOD + "/ai_input_collection",
        "source_decision_workflow_identity": decision_artifact["artifact_identity"], "as_of": decision_artifact["as_of"],
        "packets": packets,
        "coverage": {"cohort_membership_count": len(packets), "ai_input_ready_count": len(packets),
                     "review_draft_ready_count": 0, "evidence_insufficient_count": 0,
                     "model_draft_pending_count": len(packets), "validation_failures_by_reason": {}},
        "prompt_contract": prompt_contract(),
        "authority_boundary": {"live_model_call_required": False, "ai_output_must_pass_deterministic_validator": True,
                               "recommendations_targets_probabilities_sizing_execution": "NOT_EMITTED"},
        "verdict": "EVIDENCE_BOUND_AI_INPUT_COLLECTION_READY",
    }
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = "evidence_bound_ai_input_collection:" + artifact["artifact_sha256"]
    return artifact


def prompt_contract() -> dict[str, Any]:
    """A model-independent message payload, always subordinate to validation."""
    return {
        "contract_version": METHOD + "/prompt", "role": "research_draft_assistant",
        "instructions": [
            "Use only supplied evidence IDs for material factual or analytical claims.",
            "Label every claim FACT, DATA_WARNING, INFERENCE, or HYPOTHESIS.",
            "Preserve all supplied negative and conflicting evidence in COUNTER_THESIS.",
            "Keep UNKNOWN, BLOCKED, PARTIAL, and NOT_APPLICABLE exactly as supplied.",
            "Do not create numerical authority, probabilities, target prices, expected returns, recommendations, position sizes, or execution instructions.",
            "Describe valuation proxies only as NON_AUTHORITATIVE_RESEARCH_PROXY.",
            "Surface unresolved questions and evidence gaps rather than estimating missing values.",
        ],
        "required_sections": ["RESEARCH_CONTEXT", "THESIS", "COUNTER_THESIS", "CATALYSTS", "RISKS", "SCENARIO_INTERPRETATION",
                              "VALUATION_CONTEXT", "MARKET_CONTEXT", "UNRESOLVED_QUESTIONS", "EVIDENCE_GAPS", "WHAT_WOULD_CHANGE_THE_VIEW", "HUMAN_REVIEW_REQUIRED"],
        "output_schema": {"claims": "list[claim]", "sections": "mapping[str, list[claim_id]]", "dimension_interpretations": "mapping[dimension, eligibility]", "human_review_required": "bool"},
    }


def _draft_texts(draft: Mapping[str, Any]) -> list[str]:
    return [str(claim.get("claim_text", "")) for claim in draft.get("claims", []) if isinstance(claim, Mapping)]


def validate_ai_draft(ai_input: Mapping[str, Any], draft: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an untrusted model draft without interpreting its prose as authority."""
    errors: list[str] = []
    evidence = {item["evidence_id"]: item for item in ai_input["evidence"]}
    claims = draft.get("claims")
    if draft.get("source_ai_input_identity") != ai_input["ai_input_identity"]:
        errors.append("SOURCE_AI_INPUT_IDENTITY_MISMATCH")
    if not isinstance(claims, list):
        errors.append("CLAIMS_NOT_A_LIST"); claims = []
    sections = draft.get("sections")
    if not isinstance(sections, Mapping) or not set(prompt_contract()["required_sections"]).issubset(sections):
        errors.append("REQUIRED_DRAFT_SECTION_MISSING")
    seen_ids: set[str] = set(); counter_covered: set[str] = set()
    for claim in claims:
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id or claim_id in seen_ids:
            errors.append("CLAIM_ID_INVALID_OR_DUPLICATE")
        seen_ids.add(str(claim_id))
        claim_type = claim.get("claim_type")
        if claim_type not in CLAIM_TYPES:
            errors.append("CLAIM_TYPE_INVALID")
        supporting = claim.get("supporting_evidence_ids", [])
        conflicting = claim.get("conflicting_evidence_ids", [])
        if not isinstance(supporting, list) or not isinstance(conflicting, list):
            errors.append("CLAIM_EVIDENCE_IDS_INVALID"); continue
        unknown_ids = set(supporting + conflicting) - set(evidence)
        if unknown_ids:
            errors.append("CLAIM_REFERENCES_UNKNOWN_EVIDENCE")
        if claim_type == "FACT" and (not supporting or any(evidence.get(item, {}).get("authority") in ("MISSING", "BLOCKED", "UNKNOWN") for item in supporting)):
            errors.append("FACT_WITHOUT_QUALIFIED_EVIDENCE")
        if claim.get("authority_class") not in {evidence[item]["authority"] for item in supporting if item in evidence}:
            errors.append("AUTHORITY_ESCALATION_OR_UNSUPPORTED_CLAIM")
        if claim.get("section") == "COUNTER_THESIS":
            counter_covered.update(supporting + conflicting)
        if NUMBER_RE.search(str(claim.get("claim_text", ""))) and not claim.get("numeric_evidence_ids"):
            errors.append("UNSUPPORTED_NUMERIC_CLAIM")
        dimension = claim.get("referenced_dimension")
        if dimension in ai_input["blocked_dimensions"] and claim_type == "FACT":
            errors.append("BLOCKED_DIMENSION_PRESENTED_AS_FACT")
    for pattern in FORBIDDEN_OUTPUT_PATTERNS:
        if any(re.search(pattern, text, flags=re.IGNORECASE) for text in _draft_texts(draft)):
            errors.append("FORBIDDEN_INVESTMENT_OR_EXECUTION_OUTPUT")
            break
    if any("authoritative" in text.lower() and "valuation" in text.lower() for text in _draft_texts(draft)):
        errors.append("VALUATION_PROXY_PRESENTED_AS_AUTHORITATIVE")
    expected_dimensions = {name: item["eligibility"] for name, item in ai_input["analytical_eligibility"].items()}
    if draft.get("dimension_interpretations") != expected_dimensions:
        errors.append("DIMENSION_STATE_NOT_PRESERVED")
    if draft.get("human_review_required") is not True:
        errors.append("HUMAN_REVIEW_GATE_MISSING")
    if not set(ai_input["mandatory_counter_evidence_ids"]).issubset(counter_covered):
        errors.append("MATERIAL_COUNTER_EVIDENCE_SUPPRESSED")
    result = {"contract_version": METHOD + "/validator", "source_ai_input_identity": ai_input["ai_input_identity"],
              "draft_identity": draft.get("draft_identity"), "validation_status": "VALID" if not errors else "REJECTED",
              "reason_codes": sorted(set(errors)), "claim_count": len(claims),
              "mandatory_counter_evidence_count": len(ai_input["mandatory_counter_evidence_ids"]),
              "authority_boundary": {"validator_is_deterministic": True, "model_output_is_not_authority": True}}
    result["validation_identity"] = "ai_draft_validation:" + _hash(result)
    return result


def build_human_review_packet(ai_input: Mapping[str, Any], draft: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    if validation["validation_status"] != "VALID":
        raise ValueError("INVALID_AI_DRAFT_CANNOT_ENTER_HUMAN_REVIEW")
    packet = {"schema_version": "1.0.0", "contract_version": METHOD + "/human_review",
              "source_ai_input_identity": ai_input["ai_input_identity"], "source_draft_identity": draft["draft_identity"],
              "validation_identity": validation["validation_identity"], "ticker": ai_input["ticker"], "as_of": ai_input["as_of"],
              "review_state": "HUMAN_REVIEW_REQUIRED", "human_decision_required": True,
              "ai_research_draft": draft, "material_claims": draft["claims"], "evidence": ai_input["evidence"],
              "blocked_dimensions": ai_input["blocked_dimensions"], "unresolved_questions": [item for item in ai_input["evidence"] if item["section"] == "UNKNOWN_OR_MISSING"],
              "authority_warnings": ai_input["authority_boundary"], "reviewer": {"identity": None, "timestamp": None, "notes": None},
              "human_modifications": [], "approval_boundary": "INTERNAL_RESEARCH_ONLY_NOT_INVESTMENT_OR_EXECUTION_AUTHORITY"}
    packet["review_packet_identity"] = "evidence_bound_human_review:" + _hash(packet)
    return packet


def apply_human_review(review_packet: Mapping[str, Any], *, reviewer_identity: str, review_timestamp: str,
                       review_state: str, reviewer_notes: str | None = None,
                       material_claim_edits: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Append provenance-bearing human edits without rewriting machine claims."""
    if review_state not in REVIEW_STATES - {"DRAFT", "HUMAN_REVIEW_REQUIRED"}:
        raise ValueError("INVALID_HUMAN_REVIEW_STATE")
    claim_ids = {claim["claim_id"] for claim in review_packet["material_claims"]}
    edits = []
    for edit in material_claim_edits or []:
        if edit.get("claim_id") not in claim_ids or not edit.get("replacement_text"):
            raise ValueError("INVALID_HUMAN_CLAIM_EDIT")
        edits.append({"claim_id": edit["claim_id"], "replacement_text": edit["replacement_text"], "origin": "HUMAN_EDIT",
                      "reviewer_identity": reviewer_identity, "review_timestamp": review_timestamp})
    result = dict(review_packet)
    result.update({"review_state": review_state, "reviewer": {"identity": reviewer_identity, "timestamp": review_timestamp, "notes": reviewer_notes},
                   "human_modifications": edits, "prior_review_packet_identity": review_packet["review_packet_identity"]})
    result.pop("review_packet_identity", None)
    result["review_packet_identity"] = "evidence_bound_human_review:" + _hash(result)
    return result
