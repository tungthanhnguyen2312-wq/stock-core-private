"""Annual, research-only features over existing operational-proxy facts."""
from __future__ import annotations
from collections import Counter
import math
import re
from typing import Any, Mapping

FEATURES = ("revenue_growth_yoy", "revenue_cagr_3y", "revenue_cagr_5y", "net_income_growth_yoy", "net_income_cagr_3y", "net_income_cagr_5y", "gross_margin", "gross_margin_change_yoy", "net_margin", "net_margin_change_yoy", "total_assets_growth_yoy", "shareholders_equity_growth_yoy", "debt_growth_yoy", "earnings_growth_consistency", "revenue_growth_consistency", "roa", "roe", "debt_to_equity", "operating_cash_flow_to_net_income", "asset_turnover", "equity_multiplier", "dupont_3_factor_roe", "piotroski")
_METRIC = {"revenue": "revenue", "net_income": "net_income", "gross_profit": "gross_profit", "assets": "total_assets", "equity": "shareholders_equity", "debt": "total_interest_bearing_debt", "ocf": "operating_cash_flow"}

def _ready(value, periods, inputs, tier="OPERATIONAL_PROXY"):
    return {"value": value, "status": "READY_RESEARCH_PROXY" if tier != "AUTHORITATIVE_EVIDENCE" else "READY", "method": "same_provider_same_scope_annual/v1", "periods_used": periods, "input_metric_identities": inputs, "input_evidence_tiers": [tier], "warnings": [], "comparability": "SAME_PROVIDER_SCOPE_ANNUAL", "research_eligible": True}
def _blocked(reason):
    return {"value": None, "status": reason, "method": "same_provider_same_scope_annual/v1", "periods_used": [], "input_metric_identities": [], "input_evidence_tiers": [], "warnings": [], "comparability": "UNAVAILABLE", "research_eligible": False}
def _annual(record):
    result = {}
    for f in record.get("facts", []):
        p=str(f.get("reporting_period")); v=f.get("provider_raw_value")
        if re.fullmatch(r"20\d{2}", p) and f.get("fitness_for_use",{}).get("research_eligible") and isinstance(v,(int,float)) and f.get("evidence_tier") in {"OPERATIONAL_PROXY","VERIFIED_RESEARCH_EVIDENCE"}:
            result.setdefault((f.get("provider"), f.get("statement_scope")),{}).setdefault(f.get("canonical_metric"),{})[int(p)] = (float(v),f.get("evidence_tier"))
    return result
def _series(groups, metric):
    best=max((g.get(metric,{}) for g in groups.values()),key=len,default={}); return best
def _growth(s):
    if len(s)<2:return _blocked("BLOCKED_PERIOD_GAP")
    y=max(s); prior=y-1
    if prior not in s or s[prior][0]==0:return _blocked("BLOCKED_PERIOD_GAP")
    return _ready(s[y][0]/s[prior][0]-1,[str(prior),str(y)],["annual_value"])
def _cagr(s,n):
    if not s:return _blocked("BLOCKED_MISSING_INPUT")
    y=max(s); prior=y-n
    if prior not in s or any(k not in s for k in range(prior,y+1)) or s[prior][0]<=0:return _blocked("BLOCKED_PERIOD_GAP")
    return _ready((s[y][0]/s[prior][0])**(1/n)-1,[str(prior),str(y)],["annual_value"])
def build_ticker_features(record: Mapping[str,Any]):
    if record.get("entity_type")!="corporate": return {name:_blocked("BLOCKED_ENTITY_CLASS") for name in FEATURES}
    g=_annual(record); rev=_series(g,_METRIC['revenue']); ni=_series(g,_METRIC['net_income']); gross=_series(g,_METRIC['gross_profit']); assets=_series(g,_METRIC['assets']); eq=_series(g,_METRIC['equity']); debt=_series(g,_METRIC['debt']); ocf=_series(g,_METRIC['ocf'])
    out={"revenue_growth_yoy":_growth(rev),"revenue_cagr_3y":_cagr(rev,3),"revenue_cagr_5y":_cagr(rev,5),"net_income_growth_yoy":_growth(ni),"net_income_cagr_3y":_cagr(ni,3),"net_income_cagr_5y":_cagr(ni,5),"total_assets_growth_yoy":_growth(assets),"shareholders_equity_growth_yoy":_growth(eq),"debt_growth_yoy":_growth(debt),"earnings_growth_consistency":_ready(sum(1 for y in sorted(ni)[1:] if y-1 in ni and ni[y][0]>ni[y-1][0]),[str(y) for y in sorted(ni)],["net_income"]) if len(ni)>1 else _blocked("BLOCKED_PERIOD_GAP"),"revenue_growth_consistency":_ready(sum(1 for y in sorted(rev)[1:] if y-1 in rev and rev[y][0]>rev[y-1][0]),[str(y) for y in sorted(rev)],["revenue"]) if len(rev)>1 else _blocked("BLOCKED_PERIOD_GAP")}
    def ratio(name,a,b):
        years=sorted(set(a)&set(b));
        return _ready(a[years[-1]][0]/b[years[-1]][0],[str(years[-1])],[name]) if years and b[years[-1]][0] else _blocked("BLOCKED_MISSING_INPUT")
    out.update({"gross_margin":ratio("gross_profit/revenue",gross,rev),"net_margin":ratio("net_income/revenue",ni,rev),"roa":ratio("net_income/assets",ni,assets),"roe":ratio("net_income/equity",ni,eq),"debt_to_equity":ratio("debt/equity",debt,eq),"operating_cash_flow_to_net_income":ratio("ocf/net_income",ocf,ni),"asset_turnover":ratio("revenue/assets",rev,assets),"equity_multiplier":ratio("assets/equity",assets,eq)})
    out["gross_margin_change_yoy"]=_growth({y: (gross[y][0]/rev[y][0],"OPERATIONAL_PROXY") for y in set(gross)&set(rev) if rev[y][0]})
    out["net_margin_change_yoy"]=_growth({y: (ni[y][0]/rev[y][0],"OPERATIONAL_PROXY") for y in set(ni)&set(rev) if rev[y][0]})
    d=out["roe"]; parts=[out[x] for x in ("net_margin","asset_turnover","equity_multiplier")]
    out["dupont_3_factor_roe"]=_ready(math.prod(x["value"] for x in parts),d["periods_used"],["net_margin","asset_turnover","equity_multiplier"]) if d["research_eligible"] and all(x["research_eligible"] for x in parts) else _blocked("BLOCKED_MISSING_INPUT")
    out["piotroski"]={**_blocked("BLOCKED_INCOMPLETE_INPUTS"),"criteria_available":0,"criteria_missing":9,"score":None,"piotroski_ready":False}
    return out
def summarize(records):
    c={f:Counter() for f in FEATURES}
    for r in records.values():
        for f,v in r["fundamental_features"].items(): c[f][v["status"]]+=1
    return {f:dict(x) for f,x in c.items()}

# Quarterly activation v1 deliberately overrides the annual-only builder above.
FEATURES = ("revenue_same_period_yoy", "net_income_same_period_yoy", "total_assets_same_period_yoy", "shareholders_equity_same_period_yoy", "debt_same_period_yoy", "gross_margin_period", "net_margin_period", "roa_eop_proxy", "roe_eop_proxy", "asset_turnover_eop_proxy", "equity_multiplier_eop_proxy", "dupont_roe_eop_proxy", "operating_cash_flow_to_net_income", "ttm", "piotroski_standard_score", "piotroski_evidence_profile")
_FLOW = {"revenue", "net_income", "gross_profit", "operating_cash_flow"}
_STOCK = {"total_assets", "shareholders_equity", "total_interest_bearing_debt"}
def _quarter_groups(record):
    groups={}
    for f in record.get("facts",[]):
        p=str(f.get("reporting_period")); v=f.get("provider_raw_value")
        if re.fullmatch(r"20\d{2}-Q[1-4]",p) and isinstance(v,(int,float)) and f.get("fitness_for_use",{}).get("research_eligible"):
            groups.setdefault((f.get("provider"),f.get("statement_scope")),{}).setdefault(f["canonical_metric"],{})[p]=(float(v),f.get("evidence_tier"))
    return groups
def _quarter_series(groups, metric): return max((x.get(metric,{}) for x in groups.values()),key=len,default={})
def _qyoy(series, metric):
    if not series:return _blocked("BLOCKED_MISSING_INPUT")
    p=max(series); prev=f"{int(p[:4])-1}{p[4:]}"
    if prev not in series or series[prev][0]==0:return _blocked("BLOCKED_PERIOD_GAP")
    old,new=series[prev][0],series[p][0]
    if metric=="net_income" and old<=0:
        state="TURNAROUND_TO_PROFIT" if old<0<new else "TURNED_TO_LOSS" if old>0>new else "LOSS_NARROWED" if old<0 and new>old else "LOSS_WIDENED" if old<0 else "ZERO_BASE"
        return {**_blocked(state),"semantic_transition":state,"periods_used":[prev,p],"method":"SAME_PERIOD_LABEL_YOY_PROXY"}
    return {**_ready(new/old-1,[prev,p],[metric]),"method":"SAME_PERIOD_LABEL_YOY_PROXY","duration_basis":"DURATION_UNKNOWN" if metric in _FLOW else "POINT_IN_TIME_STOCK"}
def build_ticker_features(record: Mapping[str,Any]):
    if record.get("entity_type")!="corporate": return {f:_blocked("BLOCKED_ENTITY_CLASS") for f in FEATURES}
    g=_quarter_groups(record); rev=_quarter_series(g,"revenue"); ni=_quarter_series(g,"net_income"); gross=_quarter_series(g,"gross_profit"); assets=_quarter_series(g,"total_assets"); eq=_quarter_series(g,"shareholders_equity"); debt=_quarter_series(g,"total_interest_bearing_debt"); ocf=_quarter_series(g,"operating_cash_flow")
    out={"revenue_same_period_yoy":_qyoy(rev,"revenue"),"net_income_same_period_yoy":_qyoy(ni,"net_income"),"total_assets_same_period_yoy":_qyoy(assets,"total_assets"),"shareholders_equity_same_period_yoy":_qyoy(eq,"shareholders_equity"),"debt_same_period_yoy":_qyoy(debt,"total_interest_bearing_debt")}
    def ratio(name,a,b):
        ps=set(a)&set(b)
        return {**_ready(a[max(ps)][0]/b[max(ps)][0],[max(ps)],[name]),"method":"SAME_PERIOD_RESEARCH_PROXY","duration_basis":"SAME_PERIOD_COMPATIBLE"} if ps and b[max(ps)][0] else _blocked("BLOCKED_MISSING_INPUT")
    out.update({"gross_margin_period":ratio("gross_profit/revenue",gross,rev),"net_margin_period":ratio("net_income/revenue",ni,rev),"roa_eop_proxy":ratio("net_income/assets_eop",ni,assets),"roe_eop_proxy":ratio("net_income/equity_eop",ni,eq),"asset_turnover_eop_proxy":ratio("revenue/assets_eop",rev,assets),"equity_multiplier_eop_proxy":ratio("assets/equity_eop",assets,eq),"operating_cash_flow_to_net_income":ratio("ocf/net_income",ocf,ni)})
    parts=[out[x] for x in ("net_margin_period","asset_turnover_eop_proxy","equity_multiplier_eop_proxy")]
    out["dupont_roe_eop_proxy"]={**_ready(math.prod(x["value"] for x in parts),parts[0]["periods_used"],["net_margin_period","asset_turnover_eop_proxy","equity_multiplier_eop_proxy"]),"method":"EOP_PROXY_IDENTICAL_COMPONENT_METHOD"} if all(x["research_eligible"] for x in parts) else _blocked("BLOCKED_MISSING_INPUT")
    out["ttm"]=_blocked("BLOCKED_DURATION_UNKNOWN")
    out["piotroski_standard_score"]={**_blocked("BLOCKED_INCOMPLETE_INPUTS"),"score":None}
    available=sum(v["research_eligible"] for v in out.values()); out["piotroski_evidence_profile"]={"value":None,"status":"PROFILE_AVAILABLE" if available else "BLOCKED_INCOMPLETE_INPUTS","criteria_available":available,"criteria_passed":None,"criteria_missing":9-available,"research_eligible":bool(available),"method":"DIAGNOSTIC_NOT_PARTIAL_SCORE","warnings":[]}
    return out
