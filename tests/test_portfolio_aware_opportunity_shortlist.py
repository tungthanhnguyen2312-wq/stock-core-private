from __future__ import annotations
import pytest
import portfolio_aware_opportunity_shortlist as shortlist

def _inputs(session="2026-09-09"):
    decisions = {"AAA": {"decision_identity": "d:AAA", "research_action_posture": "INITIATE_ON_BREAKOUT"}, "BBB": {"decision_identity": "d:BBB", "research_action_posture": "EARLY_WATCH"}, "CCC": {"decision_identity": "d:CCC", "research_action_posture": "ACCUMULATE_ON_RETEST"}}
    iid = {"contract_version": "integrated_investment_decision_product/v1", "session": session, "artifact_identity": "iid:x", "records": decisions}
    pad = {"contract_version": "portfolio_aware_decision/v1", "session": session, "artifact_identity": "pad:x", "source_artifact_identities": {"integrated_investment_decision_product_identity": "iid:x"}, "records": {
      "AAA": {"evidence_lineage": {"security_decision_identity": "d:AAA"}, "portfolio_action_research":"ADD_WITHIN_RISK_CEILING", "position_state":"NOT_HELD", "binding_constraint":"NONE", "portfolio_constraint_completeness":"FULL", "portfolio_risk_quantity_ceiling": 1, "execution_qualified_quantity":None, "execution_qualified_quantity_status":"NOT_QUALIFIED", "margin_economics": {"status":"NOT_EVALUATED"}},
      "BBB": {"evidence_lineage": {"security_decision_identity": "d:BBB"}, "portfolio_action_research":"PROBE_WITHIN_RISK_CEILING", "position_state":"NOT_HELD", "binding_constraint":"NONE", "portfolio_constraint_completeness":"FULL", "portfolio_risk_quantity_ceiling": 1, "execution_qualified_quantity":None, "execution_qualified_quantity_status":"NOT_QUALIFIED", "margin_economics": {"status":"NOT_EVALUATED"}},
      "CCC": {"evidence_lineage": {"security_decision_identity": "d:CCC"}, "portfolio_action_research":"OVER_LIMIT_REVIEW", "position_state":"HELD_ABOVE_POLICY_CAP", "binding_constraint":"SINGLE_POSITION", "portfolio_constraint_completeness":"FULL", "portfolio_risk_quantity_ceiling":None, "execution_qualified_quantity":None, "execution_qualified_quantity_status":"NOT_QUALIFIED", "margin_economics": {"status":"NOT_APPLICABLE"}}}}
    adr = {"contract_version":"asymmetric_dislocation_research/v1", "session":session, "artifact_identity":"adr:x", "source_integrated_decision_identity":"iid:x", "records": {t:{"source_decision_identity": f"d:{t}", "primary_research_state": s, "reason_codes": []} for t,s in {"AAA":"CYCLICAL_RECOVERY_FORMING","BBB":"NO_QUALIFIED_DISLOCATION","CCC":"VALUE_TRAP_RISK"}.items()}}
    return iid,pad,adr

def test_buckets_are_deterministic_and_asymmetric_never_overrides_block():
    artifact = shortlist.build_artifact(session="2026-09-09", integrated_decision=_inputs()[0], portfolio_aware_decision=_inputs()[1], asymmetric_dislocation=_inputs()[2])
    assert [r["bucket"] for r in artifact["records"]] == ["TACTICAL_ADD_CANDIDATE", "TACTICAL_PROBE_CANDIDATE", "RISK_REVIEW"]
    assert shortlist.build_artifact(session="2026-09-09", integrated_decision=_inputs()[0], portfolio_aware_decision=_inputs()[1], asymmetric_dislocation=_inputs()[2])["artifact_identity"] == artifact["artifact_identity"]

def test_cross_session_and_identity_fail_closed():
    iid,pad,adr = _inputs(); adr["session"] = "2026-09-08"
    with pytest.raises(shortlist.OpportunityShortlistError, match="CROSS_SESSION"):
        shortlist.build_artifact(session="2026-09-09", integrated_decision=iid, portfolio_aware_decision=pad, asymmetric_dislocation=adr)
    iid,pad,adr = _inputs(); adr["source_integrated_decision_identity"] = "wrong"
    with pytest.raises(shortlist.OpportunityShortlistError, match="ASYMMETRIC_INTEGRATED"):
        shortlist.build_artifact(session="2026-09-09", integrated_decision=iid, portfolio_aware_decision=pad, asymmetric_dislocation=adr)

def test_console_summary_is_aggregate_only():
    iid,pad,adr = _inputs(); out = shortlist.public_console_summary(shortlist.build_artifact(session="2026-09-09", integrated_decision=iid, portfolio_aware_decision=pad, asymmetric_dislocation=adr))
    assert "records" not in out and "portfolio_risk_quantity_ceiling" not in str(out)
