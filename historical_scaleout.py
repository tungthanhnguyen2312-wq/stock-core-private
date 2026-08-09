"""Legacy Phase 5A bounded cohort selection and research-brief projection.

New Pillar A work must use ``research_financial_fact_projection`` plus the ticker capability
matrix as its eligibility authority.  This module remains for explicit backward-compatible
Phase 5A invocations; it is not called by the Pillar A adapter and must not become a second
market-wide selection path.
"""
from __future__ import annotations
from typing import Any, Mapping
from historical_decision_analysis import PILOT_TICKERS, evaluate_historical_decision_analysis
from portfolio_risk_analysis import evaluate_portfolio_risk_analysis

def _m(v:Any)->Mapping[str,Any]: return v if isinstance(v,Mapping) else {}
def _qualified(entry:Mapping[str,Any])->bool:
 c=_m(entry.get("financial_canonical"));return c.get("status")=="available" and any(isinstance(r,Mapping) and r.get("quality_state")=="available" and r.get("value") is not None for r in (c.get("records") or []))
def select(entries:Mapping[str,Any],limit:int=10)->list[dict[str,Any]]:
 out=[]
 for ticker in sorted(entries):
  e=_m(entries[ticker]); entity=e.get("entity_type")
  reasons=[]
  if ticker in PILOT_TICKERS: reasons.append("existing_phase_4_pilot_excluded")
  elif entity not in {"corporate","bank"}: reasons.append("entity_type_unknown_or_unsupported")
  elif not _qualified(e): reasons.append("qualified_canonical_facts_missing")
  status="eligible" if not reasons else "blocked"
  out.append({"ticker":ticker,"status":status,"reason_codes":reasons,"entity_type":entity})
 eligible=[x for x in out if x["status"]=="eligible"][:limit]
 selected={x["ticker"] for x in eligible}
 return [dict(x,selected=x["ticker"] in selected,reason_codes=x["reason_codes"] if x["ticker"] not in selected else ["qualified_canonical_and_known_archetype"]) for x in out]
def attach(entries:dict[str,dict],basis:Mapping[str,Any],limit:int=10)->dict[str,Any]:
 matrix=select(entries,limit);selected={x["ticker"] for x in matrix if x["selected"]}
 for ticker in sorted(selected):
  e=entries[ticker];e["historical_decision_analysis"]=evaluate_historical_decision_analysis(ticker,e,allow_scaleout=True);e["portfolio_risk_analysis"]=evaluate_portfolio_risk_analysis(ticker,e,basis,allow_scaleout=True)
  d=_m(e["historical_decision_analysis"]);p=_m(e["portfolio_risk_analysis"])
  e["historical_research_brief"]={"ticker":ticker,"eligibility":d.get("eligibility"),"historical_conclusion":d.get("historical_conclusion"),"quality_assessment":d.get("quality_assessment"),"risks":d.get("risks"),"catalysts":d.get("catalysts"),"scenarios":d.get("scenarios"),"invalidation_conditions":d.get("invalidation_conditions"),"fundamental_risk":p.get("fundamental_risk"),"liquidity":p.get("liquidity"),"portfolio_context":_m(p.get("portfolio_considerations")).get("actual_portfolio_fit"),"allocation_eligibility":p.get("allocation_eligibility"),"historical_only":True,"is_actionable":False}
 return {"schema_version":"1.0.0","selection_limit":limit,"matrix":matrix,"selected_tickers":sorted(selected),"historical_only":True,"is_actionable":False}
