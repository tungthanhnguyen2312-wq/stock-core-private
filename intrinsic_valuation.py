"""Fail-closed intrinsic valuation over explicitly qualified canonical inputs."""
from __future__ import annotations
import math
from typing import Any, Mapping
SCHEMA_VERSION=METHOD_VERSION="1.0.0"

def n(v):
 if v is None or isinstance(v,bool): return None
 try: v=float(v)
 except (TypeError,ValueError): return None
 return None if not math.isfinite(v) else (int(v) if v.is_integer() else v)
def out(name,state="unavailable",**kw):
 x={"method":name,"method_version":METHOD_VERSION,"state":state,"applicability":"unknown","valuation_date":None,"historical_input_periods":[],"statement_scope":None,"forecast_horizon":None,"assumptions":[],"required_inputs":[],"used_inputs":[],"missing_inputs":[],"scenario_name":None,"sensitivity_dimensions":[],"enterprise_value":None,"equity_value":None,"per_share_value":None,"warnings":[],"interpretation_limits":["No target price, recommendation, or forced model output."],"is_actionable":False};x.update(kw);return x
def q(r,metric):
 if not isinstance(r,Mapping) or r.get("canonical_metric")!=metric:return None,"required_canonical_input_missing"
 if r.get("quality_state")!="available" or r.get("statement_scope") not in {"consolidated","separate"}:return None,"canonical_scope_or_quality_unqualified"
 if not isinstance(r.get("period_identity"),Mapping):return None,"financial_period_missing"
 v=n(r.get("value"));return (v,None) if v is not None else (None,"canonical_value_missing_or_malformed")
def evaluate_intrinsic_valuation(inputs:Mapping[str,Any]|None,reference_at:str|None=None):
 d=inputs if isinstance(inputs,Mapping) else {}; fin=d.get("financial") if isinstance(d.get("financial"),Mapping) else {}; entity=str(d.get("entity_type") or "unknown"); methods={}
 # Both methods below are ordinary-corporate formulations: FCFF nets ordinary operating
 # cash flow, CapEx, and interest-bearing debt (a bank's funding is customer deposits
 # and interbank placements, never qualified here as total_debt); Net-Net nets
 # current_assets/inventory/receivables against total_liabilities, a classification a
 # bank's balance sheet does not use. Both are inapplicable to the bank archetype
 # itself, not merely missing inputs -- entity_type=="bank" only, never ticker-specific.
 if entity in {"bank", "securities"}:
  return {"schema_version":SCHEMA_VERSION,"reference_at":reference_at,"status":"unknown","methods":{
    "fcff_dcf": out("fcff_dcf","inapplicable",applicability="inapplicable",
        warnings=["fcff_ordinary_operating_cash_flow_capex_and_interest_bearing_debt_formulation_not_qualified_for_non_corporate_financial_archetype"]),
    "net_net": out("net_net","inapplicable",applicability="inapplicable",
        warnings=["net_net_current_assets_inventory_receivables_identity_not_qualified_for_non_corporate_financial_balance_sheet_structure"]),
   }, "warnings":["DDM, FCFE, RNAV, and SOTP are absent until their source contracts are qualified."]}
 # FCFF requires standalone compatible cash-flow components, explicit forecast and sourced WACC/terminal assumptions.
 vals={}; missing=[]
 for m in ("operating_cash_flow","capital_expenditure","total_debt","cash_and_equivalents"):
  vals[m],bad=q(fin.get(m),m)
  if bad:missing.append(bad+":"+m)
 periods=[fin.get(m,{}).get("period_identity",{}).get("period") for m in vals if isinstance(fin.get(m),Mapping)]
 scopes={fin.get(m,{}).get("statement_scope") for m in vals if isinstance(fin.get(m),Mapping)}
 assumptions=d.get("fcff_assumptions") if isinstance(d.get("fcff_assumptions"),Mapping) else {}
 assumption_ok=all(assumptions.get(k) is not None and isinstance(assumptions.get(k+"_source"),str) for k in ("wacc","terminal_growth","forecast_fcff"))
 if not missing and len(set(periods))==1 and len(scopes)==1 and assumption_ok and vals["capital_expenditure"]>=0:
  ev=assumptions["forecast_fcff"]/(assumptions["wacc"]-assumptions["terminal_growth"]) if assumptions["wacc"]>assumptions["terminal_growth"] else None
  methods["fcff_dcf"]=out("fcff_dcf","available" if ev is not None else "incomparable",applicability="applicable",valuation_date=reference_at,historical_input_periods=periods,statement_scope=scopes.pop(),forecast_horizon=assumptions.get("forecast_horizon"),assumptions=[{"name":k,"value":assumptions[k],"source":assumptions[k+"_source"]} for k in ("wacc","terminal_growth","forecast_fcff")],used_inputs=list(vals),sensitivity_dimensions=["wacc","terminal_growth"],enterprise_value=ev,warnings=[] if ev is not None else ["terminal_growth_must_be_below_wacc"])
 else: methods["fcff_dcf"]=out("fcff_dcf","unavailable",missing_inputs=missing+([] if assumption_ok else ["sourced_wacc_terminal_growth_and_forecast"]),warnings=["FCFF is not derived from unknown, cumulative, or incompatible cash flow."])
 # Net-Net needs qualified balance-sheet components and a share basis consistent with
 # them. "period_end" is the semantically correct identity here (equity-base
 # consistency with a balance-sheet snapshot); "basic"/"diluted" (weighted-average,
 # EPS-style) remain accepted for backward compatibility but are not what this
 # method's own documentation asks for. Never widened to accept an unrelated identity
 # such as a live/valuation-date share count, and never substituted from one to another.
 net={}; miss=[]
 for m in ("current_assets","cash_and_equivalents","receivables","inventory","total_liabilities"):
  net[m],bad=q(fin.get(m),m)
  if bad:miss.append(bad+":"+m)
 share=d.get("share_count") if isinstance(d.get("share_count"),Mapping) else {}; sv=n(share.get("value"))
 ps=[fin.get(m,{}).get("period_identity",{}).get("period") for m in net if isinstance(fin.get(m),Mapping)]; ss={fin.get(m,{}).get("statement_scope") for m in net if isinstance(fin.get(m),Mapping)}
 # If the share count declares its own period, it must match the balance-sheet
 # components' single common period; if it declares none, we don't retroactively
 # require one (legacy callers with no period_identity are unaffected).
 share_period=share.get("period_identity",{}).get("period") if isinstance(share.get("period_identity"),Mapping) else None
 share_period_ok=share_period is None or (len(ps)>0 and len(set(ps))==1 and share_period==ps[0])
 shareok=sv is not None and sv>0 and share.get("semantics") in {"basic","diluted","period_end"} and share_period_ok
 if not miss and len(set(ps))==1 and len(ss)==1 and shareok:
  equity=net["cash_and_equivalents"]+net["receivables"]+net["inventory"]-net["total_liabilities"]
  methods["net_net"]=out("net_net","available",applicability="applicable",valuation_date=reference_at,historical_input_periods=ps,statement_scope=ss.pop(),used_inputs=list(net)+["share_count"],equity_value=equity,per_share_value=equity/sv,is_actionable=bool(d.get("current_price_actionable") is True),warnings=[] if d.get("current_price_actionable") is True else ["current_price_not_actionable"])
 else: methods["net_net"]=out("net_net","unavailable",missing_inputs=miss+([] if shareok else ["qualified_share_count"]))
 return {"schema_version":SCHEMA_VERSION,"reference_at":reference_at,"status":"available" if any(x["state"]=="available" for x in methods.values()) else "unknown","methods":methods,"warnings":["DDM, FCFE, RNAV, and SOTP are absent until their source contracts are qualified."]}
