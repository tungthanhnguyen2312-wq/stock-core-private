"""Compact deterministic AI research brief projected from Phase 4B/4C truth."""
from __future__ import annotations
from typing import Any,Mapping
def m(v:Any)->Mapping[str,Any]:return v if isinstance(v,Mapping) else {}
def build(ticker:str,entry:Mapping[str,Any])->dict[str,Any]:
 d=m(entry.get("historical_decision_analysis"));p=m(entry.get("portfolio_risk_analysis"));facts=list(m(d.get("provenance")).get("qualified_fact_references") or [])[:8]
 return {"schema_version":"1.0.0","ticker":ticker,"analysis_mode":"historical_only_qualified_data","entity_type":entry.get("entity_type"),"is_actionable":False,"historical_only":True,
 "identity":{"periods":d.get("data_periods_used",[]),"eligibility":d.get("eligibility",{})},"qualified_facts":facts,"quality":d.get("quality_assessment",{}),"risks":{"phase_4b":d.get("risks",[]),"phase_4c":m(p.get("fundamental_risk"))},"catalysts":d.get("catalysts",[]),"scenarios":d.get("scenarios",{}),"invalidation_conditions":d.get("invalidation_conditions",[]),"historical_conclusion":d.get("historical_conclusion",{}),"missing_evidence":d.get("missing_evidence",[]),"portfolio_risk_boundary":{"liquidity":p.get("liquidity",{}),"portfolio_context":m(p.get("portfolio_considerations")).get("actual_portfolio_fit",{}),"allocation":p.get("allocation_eligibility",{})},"prohibited_claims":["current_valuation","target_price","buy_hold_sell","ranking","sizing","current_market_liquidity","expected_return","portfolio_allocation"]}
