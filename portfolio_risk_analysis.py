"""Phase 4C pure historical risk, liquidity-gate, and portfolio-fit contract."""
from __future__ import annotations
from typing import Any, Mapping

SCHEMA_VERSION="1.0.0"
PILOTS=frozenset({"HPG","VNM","VCB"})

def m(v:Any)->Mapping[str,Any]: return v if isinstance(v,Mapping) else {}
def paths(items): return sorted({str(x) for x in items if x})

def dim(name,status,*,applicability="applicable",direction="unknown",facts=None,reasons=None,uncertainty=None,invalidation=None):
    return {"dimension":name,"status":status,"applicability":applicability,"risk_direction":direction,
            "supporting_facts":facts or [],"provenance":[f"historical_decision_analysis.quality_assessment.{name}"],
            "reason_codes":paths(reasons or []),"uncertainty":uncertainty or "Historical-only; not a future outcome.",
            "change_conditions":invalidation or ["Later qualified reporting changes the supporting facts."]}

def _fundamental(ticker:str, phase4b:Mapping[str,Any], entity_type:str)->dict[str,Any]:
    qa=m(phase4b.get("quality_assessment")); risks=phase4b.get("risks") if isinstance(phase4b.get("risks"),list) else []
    risk_ids={str(m(x).get("risk_id")) for x in risks}
    result={}
    if entity_type=="bank":
        q=m(qa.get("bank_financial_quality")); result["bank_financial_quality"]=dim("bank_financial_quality",q.get("status","unavailable"),facts=q.get("supporting_facts") or [],reasons=q.get("reason_codes") or [])
        for name in ("capital_intensity","working_capital_sensitivity","corporate_leverage"):
            result[name]=dim(name,"not_applicable",applicability="not_applicable",reasons=["corporate_metric_not_applicable_to_bank"])
    else:
        for source,name in (("profitability_and_resilience","profitability_resilience"),("earnings_cash_conversion","cash_conversion"),("capital_structure","balance_sheet_pressure")):
            q=m(qa.get(source)); direction="elevated" if source=="capital_structure" and "positive_net_debt_observed" in risk_ids else "unknown"
            result[name]=dim(name,q.get("status","unavailable"),direction=direction,facts=q.get("supporting_facts") or [],reasons=q.get("reason_codes") or [],invalidation=q.get("warnings") or None)
        capex=[f for f in phase4b.get("provenance",{}).get("qualified_fact_references",[]) if m(f).get("canonical_metric")=="capital_expenditure"]
        result["capital_intensity"]=dim("capital_intensity","available" if capex else "unavailable",facts=capex,reasons=[] if capex else ["qualified_capital_expenditure_absent"])
    unavailable=[k for k,v in result.items() if v["status"]=="unavailable"]
    aggregate="insufficient_evidence" if unavailable else "elevated" if any(v["risk_direction"]=="elevated" for v in result.values()) else "moderate"
    return {"aggregate_posture":aggregate,"dimensions":result,"source_risk_ids":sorted(risk_ids),"missing_dimensions":unavailable}

def _liquidity(basis:Mapping[str,Any])->dict[str,Any]:
    price_verified=basis.get("price_basis_verified") is True; volume_verified=basis.get("volume_basis_verified") is True
    reasons=[]
    if not price_verified: reasons.append("PRICE_BASIS_UNQUALIFIED")
    if not volume_verified: reasons.append("VOLUME_BASIS_UNQUALIFIED")
    reasons.append("QUALIFIED_MARKET_LIQUIDITY_INPUT_ABSENT")
    return {"status":"available" if price_verified and volume_verified else "blocked","eligible":price_verified and volume_verified,
            "market_dependent":True,"market_dependent_use_permitted":False,"price_basis_status":"qualified" if price_verified else "unqualified",
            "volume_basis_status":"qualified" if volume_verified else "unqualified","required_inputs":["price_basis_verified","volume_basis_verified","qualified_market_composition"],
            "missing_or_unqualified_inputs":[x for x in ("price_basis_verified" if not price_verified else None,"volume_basis_verified" if not volume_verified else None,"qualified_market_composition") if x],
            "reason_codes":reasons,"metrics":{},"unlock_conditions":["Qualified price basis, volume basis, and market-composition contract."]}

def evaluate_portfolio_risk_analysis(ticker:str,entry:Mapping[str,Any]|None,price_basis:Mapping[str,Any]|None,*,allow_scaleout:bool=False)->dict[str,Any]:
    ticker=str(ticker).upper(); e=m(entry); phase=m(e.get("historical_decision_analysis")); basis=m(price_basis); entity=str(e.get("entity_type") or "unknown")
    blocked=[]
    if ticker not in PILOTS and not allow_scaleout: blocked.append("ticker_not_in_phase_4c_pilot")
    if phase.get("eligibility",{}).get("status") not in {"eligible","partially_eligible"}: blocked.append("phase_4b_not_eligible")
    if entity not in {"corporate","bank"}: blocked.append("entity_type_unsupported")
    fundamental=_fundamental(ticker,phase,entity) if not blocked else {"aggregate_posture":"insufficient_evidence","dimensions":{},"source_risk_ids":[],"missing_dimensions":[]}
    liquidity=_liquidity(basis)
    considerations={"status":"available" if not blocked else "unavailable","security_characteristics":[
        {"kind":"bank_specific_financial_exposure" if entity=="bank" else "corporate_fundamental_exposure","source":"fundamental_risk"},
        {"kind":"fundamental_uncertainty","dimensions":fundamental["missing_dimensions"]}],
        "actual_portfolio_fit":{"status":"blocked_input","reason_codes":["PORTFOLIO_CONTEXT_REQUIRED"],"portfolio_context":None},
        "is_allocation_advice":False}
    allocation={"status":"allocation_blocked","research_ready":not bool(blocked),"risk_profile_ready":not bool(blocked),
                "liquidity_status":liquidity["status"],"portfolio_context_status":"blocked_input","eligible":False,
                "reason_codes":paths(blocked+liquidity["reason_codes"]+["PORTFOLIO_CONTEXT_REQUIRED"]),"is_actionable":False}
    return {"schema_version":SCHEMA_VERSION,"ticker":ticker,"analysis_mode":"historical_only_qualified_data","historical_only":True,"market_dependent":False,"is_actionable":False,
            "phase_4b_provenance":{"eligibility":m(phase.get("eligibility")),"conclusion":m(phase.get("historical_conclusion")),"source_path":"historical_decision_analysis"},
            "fundamental_risk":fundamental,"liquidity":liquidity,"portfolio_considerations":considerations,"allocation_eligibility":allocation,
            "prohibited_output_boundary":["recommendation","target_price","current_valuation","ranking","position_size","portfolio_weight","market_return"]}
