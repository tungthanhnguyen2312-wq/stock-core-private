"""Fail-closed fundamental quality evaluation over canonical records only."""
from __future__ import annotations
from typing import Any
VERSION="1.0.0"
STATES={"available","partial","unavailable","inapplicable","incomparable","unknown"}
def _out(name,state,**kw): return {"model_name":name,"model_version":VERSION,"applicability_state":state,"result_state":state,"score_or_value":None,"component_results":{},"input_periods":[],"statement_scope":None,"required_inputs":[],"used_inputs":[],"missing_inputs":[],"provenance":"financial_canonical","warnings":[],"interpretation_limits":["Numeric result is not automatically actionable."],"is_actionable":False,**kw}
def _usable(records): return [r for r in records if r.get("quality_state")=="available" and r.get("value") is not None and r.get("statement_scope") in {"consolidated","separate"} and isinstance(r.get("period_identity"),dict)]
def _latest(records,metric,scope,kind):
 r=[x for x in records if x.get("canonical_metric")==metric and x.get("statement_scope")==scope and x["period_identity"].get("period_type")==kind]
 return sorted(r,key=lambda x:x["period_identity"]["period"])[-1] if r else None
def evaluate_fundamental_quality(canonical:dict|None, entity_type:str="unknown")->dict:
 records=(canonical or {}).get("records",[]) if isinstance(canonical,dict) else []
 if not records:return {"schema_version":VERSION,"entity_type":entity_type,"models":{"growth_profitability":_out("growth_profitability","unknown",warnings=["canonical_records_missing"]),"dupont_roe":_out("dupont_roe","unknown"),"earnings_quality":_out("earnings_quality","unknown"),"financial_strength":_out("financial_strength","unknown"),"piotroski_f_score":_out("piotroski_f_score","unknown"),"altman_z_score":_out("altman_z_score","unknown"),"beneish_m_score":_out("beneish_m_score","unknown")}}
 usable=_usable(records)
 if not usable:return {"schema_version":VERSION,"entity_type":entity_type,"models":{n:_out(n,"unknown",warnings=["no_compatible_known_scope_canonical_records"]) for n in ["growth_profitability","dupont_roe","earnings_quality","financial_strength","piotroski_f_score","altman_z_score","beneish_m_score"]}}
 scopes=sorted({r["statement_scope"] for r in usable}); scope=scopes[0]
 def model(name, required, calc=None):
  found={m:_latest(usable,m,scope,"annual") for m in required}; missing=[m for m,v in found.items() if v is None]
  if missing:return _out(name,"unavailable",statement_scope=scope,required_inputs=required,missing_inputs=missing)
  value,components=calc(found) if calc else (None,{})
  return _out(name,"available",statement_scope=scope,score_or_value=value,component_results=components,input_periods=[v["period_identity"] for v in found.values()],required_inputs=required,used_inputs=required)
 industrial=entity_type in {"corporate","industrial"}
 if not industrial:
  gate=lambda n:_out(n,"inapplicable" if entity_type!="unknown" else "unknown",warnings=["industrial_variant_not_qualified_for_entity_type"])
  return {"schema_version":VERSION,"entity_type":entity_type,"models":{"growth_profitability":gate("growth_profitability"),"dupont_roe":gate("dupont_roe"),"earnings_quality":gate("earnings_quality"),"financial_strength":gate("financial_strength"),"piotroski_f_score":gate("piotroski_f_score"),"altman_z_score":gate("altman_z_score"),"beneish_m_score":gate("beneish_m_score")}}
 growth=model("growth_profitability",["revenue","net_income"],lambda x:((x["net_income"]["value"]/x["revenue"]["value"]) if x["revenue"]["value"] else None,{"net_margin":None if not x["revenue"]["value"] else x["net_income"]["value"]/x["revenue"]["value"]}))
 dupont=model("dupont_roe",["net_income","revenue","total_assets","shareholders_equity"],lambda x:((x["net_income"]["value"]/x["revenue"]["value"])*(x["revenue"]["value"]/x["total_assets"]["value"])*(x["total_assets"]["value"]/x["shareholders_equity"]["value"]) if x["revenue"]["value"] and x["total_assets"]["value"] and x["shareholders_equity"]["value"] else None,{}))
 piotroski=model("piotroski_f_score",["net_income","operating_cash_flow","total_assets"],lambda x:(sum([x["net_income"]["value"]>0,x["operating_cash_flow"]["value"]>0,x["operating_cash_flow"]["value"]>x["net_income"]["value"]]),{}));piotroski["warnings"].append("Incomplete Piotroski criteria are not rescaled to nine points.")
 return {"schema_version":VERSION,"entity_type":entity_type,"models":{"growth_profitability":growth,"dupont_roe":dupont,"earnings_quality":model("earnings_quality",["operating_cash_flow","net_income"],lambda x:(x["operating_cash_flow"]["value"]-x["net_income"]["value"],{})),"financial_strength":model("financial_strength",["total_debt","cash_and_equivalents","shareholders_equity"],lambda x:(x["total_debt"]["value"]-x["cash_and_equivalents"]["value"],{})),"piotroski_f_score":piotroski,"altman_z_score":_out("altman_z_score","inapplicable",warnings=["qualified_altman_variant_not_available"]),"beneish_m_score":_out("beneish_m_score","unavailable",warnings=["exact_beneish_variables_not_available"])}}
