"""Private owner review packet projected from a retained opportunity shortlist."""
from __future__ import annotations
import hashlib, json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

CONTRACT_VERSION = "private_portfolio_decision_packet/v1"
class PacketError(ValueError): pass
def _canon(x: Any) -> str: return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def _id(x: Mapping[str, Any]) -> dict[str,str]:
    d=hashlib.sha256(_canon({k:v for k,v in x.items() if k not in {"artifact_identity","artifact_sha256","requested_at"}}).encode()).hexdigest()
    return {"artifact_sha256":d,"artifact_identity":f"{CONTRACT_VERSION}:{d}"}
def _state(r: Mapping[str,Any]) -> str:
    b=r["bucket"]
    return {"CORE_POSITION_REVIEW":"HOLD_CORE_REVIEW","TACTICAL_ADD_CANDIDATE":"REVIEW_FOR_TACTICAL_ADD","TACTICAL_PROBE_CANDIDATE":"REVIEW_FOR_PROBE","NEW_POSITION_CANDIDATE":"REVIEW_FOR_NEW_POSITION","ASYMMETRIC_RECOVERY_WATCH":"MONITOR_ASYMMETRIC_RECOVERY","SIGNAL_VALID_BUT_PORTFOLIO_BLOCKED":"PORTFOLIO_BLOCKED","RISK_REVIEW":"RISK_REVIEW"}.get(b,"NO_ACTION")
def build_artifact(*, shortlist: Mapping[str,Any], integrated_decision: Mapping[str,Any]|None=None, portfolio_aware_decision: Mapping[str,Any]|None=None, asymmetric_dislocation: Mapping[str,Any]|None=None, requested_at: str|None=None) -> dict[str,Any]:
    if shortlist.get("contract_version")!="portfolio_aware_opportunity_shortlist/v1": raise PacketError("SHORTLIST_CONTRACT_MISMATCH")
    session=shortlist.get("session")
    if not session: raise PacketError("SHORTLIST_SESSION_MISSING")
    if integrated_decision is not None:
        if integrated_decision.get("session") != session or (shortlist.get("source_artifact_identities") or {}).get("integrated_investment_decision_product") != integrated_decision.get("artifact_identity"): raise PacketError("INTEGRATED_SOURCE_IDENTITY_OR_SESSION_MISMATCH")
    if portfolio_aware_decision is not None and (portfolio_aware_decision.get("session") != session or (shortlist.get("source_artifact_identities") or {}).get("portfolio_aware_decision") != portfolio_aware_decision.get("artifact_identity")): raise PacketError("PORTFOLIO_SOURCE_IDENTITY_OR_SESSION_MISMATCH")
    if asymmetric_dislocation is not None and (asymmetric_dislocation.get("session") != session or (shortlist.get("source_artifact_identities") or {}).get("asymmetric_dislocation_research") != asymmetric_dislocation.get("artifact_identity")): raise PacketError("ASYMMETRIC_SOURCE_IDENTITY_OR_SESSION_MISMATCH")
    rows=[]
    for source in shortlist.get("records") or []:
        if not isinstance(source,Mapping): raise PacketError("SHORTLIST_RECORD_INVALID")
        state=_state(source)
        if state=="NO_ACTION": continue
        ticker=source["ticker"]; decision=((integrated_decision or {}).get("records") or {}).get(ticker,{}) ; portfolio=((portfolio_aware_decision or {}).get("records") or {}).get(ticker,{}) ; asymmetric=((asymmetric_dislocation or {}).get("records") or {}).get(ticker,{})
        if integrated_decision is not None and ((portfolio.get("evidence_lineage") or {}).get("security_decision_identity") != decision.get("decision_identity") or asymmetric.get("source_decision_identity") != decision.get("decision_identity")): raise PacketError("PER_TICKER_DECISION_IDENTITY_MISMATCH:"+ticker)
        rows.append({"ticker":ticker,"session":session,"review_state":state,"shortlist_bucket":source["bucket"],"research_action_posture":source.get("research_action_posture"),"position_state":source.get("position_state"),"portfolio_action_research":source.get("portfolio_action_research"),"asymmetric_state":source.get("asymmetric_state"),"reason_codes":source.get("asymmetric_reason_codes",[]),"trigger":decision.get("trigger",{"status":"NOT_AVAILABLE_FROM_SOURCE_CONTRACT"}),"invalidation":decision.get("invalidation",{"status":"NOT_AVAILABLE_FROM_SOURCE_CONTRACT"}),"corporate_intelligence_context":decision.get("corporate_intelligence_context",{"status":"NOT_AVAILABLE_FROM_SOURCE_CONTRACT"}),"portfolio_constraint_completeness":source.get("portfolio_constraint_completeness"),"binding_constraint":source.get("binding_constraint"),"portfolio_risk_quantity_ceiling":source.get("portfolio_risk_quantity_ceiling"),"execution_qualified_quantity":source.get("execution_qualified_quantity"),"execution_qualified_quantity_status":source.get("execution_qualified_quantity_status"),"margin_economics":portfolio.get("margin_economics",{"status":source.get("margin_economics_status")}),"margin_economics_status":source.get("margin_economics_status"),"calibration_context":"NOT_TEMPORALLY_QUALIFIED_FOR_AUTOSOURCE","explicit_blockers":[source.get("binding_constraint")] if source.get("binding_constraint") not in (None,"NONE") else []})
    rows.sort(key=lambda r:(r["review_state"],r["ticker"]))
    states=Counter(r["review_state"] for r in rows); blockers=Counter(b for r in rows for b in r["explicit_blockers"]); margin=Counter(r["margin_economics_status"] for r in rows)
    out={"schema_version":"1.0.0","contract_version":CONTRACT_VERSION,"session":session,"requested_at":requested_at,"records":rows,"coverage":{"reviewable_count":len(rows),"review_state_counts":dict(sorted(states.items())),"blocker_counts":dict(sorted(blockers.items())),"margin_status_counts":dict(sorted(margin.items())),"calibration_context_counts":dict(sorted(Counter(r["calibration_context"] for r in rows).items())),"execution_qualified_count":sum(r["execution_qualified_quantity"] is not None for r in rows)},"source_artifact_identities":{"portfolio_aware_opportunity_shortlist":shortlist.get("artifact_identity"),**(shortlist.get("source_artifact_identities") or {})},"authority_boundary":{"private_local_only":True,"review_states_not_execution_instructions":True,"no_recomputation":True,"no_cost_basis_or_pnl_logic":True}}
    out.update(_id(out)); return out
def public_console_summary(a:Mapping[str,Any])->dict[str,Any]:
    c=a["coverage"]; return {"status":"PACKET_READY","session":a["session"],"private_portfolio_decision_packet_identity":a["artifact_identity"],"review_state_counts":c["review_state_counts"],"blocker_counts":c["blocker_counts"],"margin_status_counts":c["margin_status_counts"],"calibration_context_counts":c["calibration_context_counts"],"execution_qualified_count":c["execution_qualified_count"],"source_artifact_identities":a["source_artifact_identities"]}
def write_private_artifact(a:Mapping[str,Any],root:Path)->Path:
    p=root.expanduser().resolve()/"private_portfolio_decision_packets"/a["session"] / "private_portfolio_decision_packet_v1.json"; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(_canon(a)+"\n",encoding="utf-8"); return p
