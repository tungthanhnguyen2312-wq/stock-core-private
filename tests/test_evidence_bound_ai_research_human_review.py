import copy

import pytest

from evidence_bound_ai_research_human_review import (
    apply_human_review, build_ai_input_packet, build_human_review_packet, validate_ai_draft,
)
from tools.run_evidence_gated_research_decision_workflow import run as decision_run
from tools.run_evidence_bound_ai_research_human_review import run


def _packet(ticker="HPG"):
    return build_ai_input_packet(decision_run(), ticker)


def _draft(packet):
    claims = []
    for index, item in enumerate(packet["evidence"]):
        section = "COUNTER_THESIS" if item["evidence_id"] in packet["mandatory_counter_evidence_ids"] else "THESIS"
        claims.append({"claim_id": f"claim-{index}", "claim_type": "INFERENCE", "section": section,
                       "claim_text": "Retained evidence is available for analyst review.", "supporting_evidence_ids": [item["evidence_id"]],
                       "conflicting_evidence_ids": [], "authority_class": item["authority"], "referenced_dimension": None,
                       "numeric_evidence_ids": []})
    draft = {"schema_version": "1.0.0", "contract_version": "evidence_bound_ai_research_human_review/v1/draft",
             "source_ai_input_identity": packet["ai_input_identity"], "claims": claims,
             "sections": {section: [] for section in ("RESEARCH_CONTEXT", "THESIS", "COUNTER_THESIS", "CATALYSTS", "RISKS", "SCENARIO_INTERPRETATION",
                                                        "VALUATION_CONTEXT", "MARKET_CONTEXT", "UNRESOLVED_QUESTIONS", "EVIDENCE_GAPS", "WHAT_WOULD_CHANGE_THE_VIEW", "HUMAN_REVIEW_REQUIRED")},
             "dimension_interpretations": {name: item["eligibility"] for name, item in packet["analytical_eligibility"].items()},
             "human_review_required": True}
    draft["sections"]["THESIS"] = [claim["claim_id"] for claim in claims if claim["section"] == "THESIS"]
    draft["sections"]["COUNTER_THESIS"] = [claim["claim_id"] for claim in claims if claim["section"] == "COUNTER_THESIS"]
    draft["draft_identity"] = "synthetic_fixture_draft:" + str(len(claims)) + ":" + packet["ai_input_identity"]
    return draft


def test_full_cohort_ai_input_is_deterministic_and_not_model_dependent():
    first, second = run(), run()
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["coverage"] == {"cohort_membership_count": 523, "ai_input_ready_count": 523, "review_draft_ready_count": 0,
                                 "evidence_insufficient_count": 0, "model_draft_pending_count": 523, "validation_failures_by_reason": {}}
    assert all(packet["as_of"]["research_session"] == "2026-08-20" for packet in first["packets"])
    assert all(packet["human_review"]["human_decision_required"] for packet in first["packets"])


def test_real_packets_preserve_counter_evidence_proxy_and_blocked_states():
    for ticker in ("HPG", "VCB", "SSI", "AAN", "AAA"):
        packet = _packet(ticker)
        assert packet["evidence"]
        assert packet["authority_boundary"]["valuation_proxy_must_remain_non_authoritative"]
        assert packet["analytical_eligibility"]["liquidity_readiness"]["eligibility"] == "BLOCKED"
        assert packet["analytical_eligibility"]["historical_pit_readiness"]["eligibility"] == "BLOCKED"
    assert _packet("HPG")["mandatory_counter_evidence_ids"]
    assert _packet("VCB")["analytical_eligibility"]["financial_evidence_depth"]["eligibility"] == "ELIGIBLE"
    assert _packet("SSI")["valuation_state"]["method_states"]["EV/EBITDA"]["status"] == "NOT_APPLICABLE"


def test_validator_accepts_only_evidenced_draft_and_human_edits_remain_distinct():
    packet = _packet(); draft = _draft(packet); validation = validate_ai_draft(packet, draft)
    assert validation["validation_status"] == "VALID"
    hypothesis = copy.deepcopy(draft); hypothesis["claims"][0]["claim_type"] = "HYPOTHESIS"
    assert validate_ai_draft(packet, hypothesis)["validation_status"] == "VALID"
    review = build_human_review_packet(packet, draft, validation)
    edited = apply_human_review(review, reviewer_identity="analyst:example", review_timestamp="2026-08-20T16:00:00+07:00",
                                review_state="NEEDS_MORE_EVIDENCE", material_claim_edits=[{"claim_id": "claim-0", "replacement_text": "Human clarification."}])
    assert edited["human_modifications"][0]["origin"] == "HUMAN_EDIT"
    assert edited["approval_boundary"].startswith("INTERNAL_RESEARCH_ONLY")


def test_validator_rejects_unsupported_fact_authority_escalation_forbidden_output_and_missing_counter():
    packet = _packet(); draft = _draft(packet)
    bad = copy.deepcopy(draft)
    bad["claims"][0].update({"claim_type": "FACT", "supporting_evidence_ids": [], "authority_class": "OFFICIAL_QUALIFIED", "referenced_dimension": "liquidity_readiness", "claim_text": "BUY at target price 123 with authoritative valuation."})
    bad["claims"] = [claim for claim in bad["claims"] if claim["section"] != "COUNTER_THESIS"]
    result = validate_ai_draft(packet, bad)
    assert result["validation_status"] == "REJECTED"
    assert {"FACT_WITHOUT_QUALIFIED_EVIDENCE", "AUTHORITY_ESCALATION_OR_UNSUPPORTED_CLAIM", "UNSUPPORTED_NUMERIC_CLAIM", "FORBIDDEN_INVESTMENT_OR_EXECUTION_OUTPUT", "VALUATION_PROXY_PRESENTED_AS_AUTHORITATIVE", "BLOCKED_DIMENSION_PRESENTED_AS_FACT", "MATERIAL_COUNTER_EVIDENCE_SUPPRESSED"}.issubset(result["reason_codes"])
