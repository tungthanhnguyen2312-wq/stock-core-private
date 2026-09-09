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
def build_artifact(*, shortlist: Mapping[str,Any], requested_at: str|None=None) -> dict[str,Any]:
    if shortlist.get("contract_version")!="portfolio_aware_opportunity_shortlist/v1": raise PacketError("SHORTLIST_CONTRACT_MISMATCH")
    session=shortlist.get("session")
    if not session: raise PacketError("SHORTLIST_SESSION_MISSING")
    rows=[]
    for source in shortlist.get("records") or []:
        if not isinstance(source,Mapping): raise PacketError("SHORTLIST_RECORD_INVALID")
        state=_state(source)
        if state=="NO_ACTION": continue
        rows.append({"ticker":source["ticker"],"session":session,"review_state":state,"shortlist_bucket":source["bucket"],"research_action_posture":source.get("research_action_posture"),"position_state":source.get("position_state"),"portfolio_action_research":source.get("portfolio_action_research"),"asymmetric_state":source.get("asymmetric_state"),"reason_codes":source.get("asymmetric_reason_codes",[]),"portfolio_constraint_completeness":source.get("portfolio_constraint_completeness"),"binding_constraint":source.get("binding_constraint"),"portfolio_risk_quantity_ceiling":source.get("portfolio_risk_quantity_ceiling"),"execution_qualified_quantity":source.get("execution_qualified_quantity"),"execution_qualified_quantity_status":source.get("execution_qualified_quantity_status"),"margin_economics_status":source.get("margin_economics_status"),"calibration_context":source.get("calibration_context"),"explicit_blockers":[source.get("binding_constraint")] if source.get("binding_constraint") not in (None,"NONE") else []})
    rows.sort(key=lambda r:(r["review_state"],r["ticker"]))
    states=Counter(r["review_state"] for r in rows); blockers=Counter(b for r in rows for b in r["explicit_blockers"]); margin=Counter(r["margin_economics_status"] for r in rows)
    out={"schema_version":"1.0.0","contract_version":CONTRACT_VERSION,"session":session,"requested_at":requested_at,"records":rows,"coverage":{"reviewable_count":len(rows),"review_state_counts":dict(sorted(states.items())),"blocker_counts":dict(sorted(blockers.items())),"margin_status_counts":dict(sorted(margin.items())),"calibration_context_counts":dict(sorted(Counter(r["calibration_context"] for r in rows).items())),"execution_qualified_count":sum(r["execution_qualified_quantity"] is not None for r in rows)},"source_artifact_identities":{"portfolio_aware_opportunity_shortlist":shortlist.get("artifact_identity"),**(shortlist.get("source_artifact_identities") or {})},"authority_boundary":{"private_local_only":True,"review_states_not_execution_instructions":True,"no_recomputation":True,"no_cost_basis_or_pnl_logic":True}}
    out.update(_id(out)); return out
def public_console_summary(a:Mapping[str,Any])->dict[str,Any]:
    c=a["coverage"]; return {"status":"PACKET_READY","session":a["session"],"private_portfolio_decision_packet_identity":a["artifact_identity"],"review_state_counts":c["review_state_counts"],"blocker_counts":c["blocker_counts"],"margin_status_counts":c["margin_status_counts"],"calibration_context_counts":c["calibration_context_counts"],"execution_qualified_count":c["execution_qualified_count"],"source_artifact_identities":a["source_artifact_identities"]}
def write_private_artifact(a:Mapping[str,Any],root:Path)->Path:
    p=root.expanduser().resolve()/"private_portfolio_decision_packets"/a["session"] / "private_portfolio_decision_packet_v1.json"; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(_canon(a)+"\n",encoding="utf-8"); return p
