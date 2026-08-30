"""Research-only cross-sectional axes over retained quarterly feature proxies."""
from __future__ import annotations
from collections import Counter
import hashlib,json,statistics
from pathlib import Path
from typing import Any,Mapping
import market_wide_historical_fundamentals_scaleout as source
from fundamental_research_cohort_selection import resolve_current_fundamental_cohort

ROOT = Path(__file__).resolve().parent

AXES={"PROFITABILITY_QUALITY":("net_margin_period","roa_eop_proxy","roe_eop_proxy"),"CAPITAL_EFFICIENCY":("asset_turnover_eop_proxy",),"BALANCE_SHEET_TRAJECTORY":("total_assets_same_period_yoy","shareholders_equity_same_period_yoy"),"GROWTH_MOMENTUM":("revenue_same_period_yoy","net_income_same_period_yoy")}
def _pct(values,value):
    return sum(x<=value for x in values)/len(values) if values else None
def build_artifact(*,base:Mapping[str,Any]):
    records=base["operational_proxy"]["records"]; feature_values={}
    for name in {x for xs in AXES.values() for x in xs}:
        feature_values[name]=[r["fundamental_features"][name]["value"] for r in records.values() if r["fundamental_features"][name].get("research_eligible")]
    output={}; axis_coverage=Counter()
    for ticker,r in records.items():
        features=r["fundamental_features"]; axes={}
        for axis,names in AXES.items():
            vals=[features[n]["value"] for n in names if features[n].get("research_eligible")]
            if not vals: axes[axis]={"axis_status":"INSUFFICIENT_INPUTS","score":None,"rank":None,"features_used":[],"features_missing":list(names),"method":"AVAILABLE_FEATURE_PERCENTILE_MEAN/v1","warnings":["MISSING_NOT_NEUTRAL"]}; continue
            p=[_pct(feature_values[n],features[n]["value"]) for n in names if features[n].get("research_eligible")]
            axes[axis]={"axis_status":"READY_RESEARCH_ONLY","score":sum(p)/len(p),"rank":None,"features_used":[n for n in names if features[n].get("research_eligible")],"features_missing":[n for n in names if not features[n].get("research_eligible")],"method":"AVAILABLE_FEATURE_PERCENTILE_MEAN/v1","peer_universe":"CORPORATE_PROXY_COMPARABLE","evidence_tier":"OPERATIONAL_PROXY","warnings":[]}; axis_coverage[axis]+=1
        confidence=sum(r["tier_counts"].values())/max(1,len(r["facts"]))
        output[ticker]={"ticker":ticker,"entity_class":r["entity_type"],"feature_percentiles":{n:_pct(feature_values[n],features[n]["value"]) if features[n].get("research_eligible") else None for n in feature_values},"axes":axes,"data_confidence":{"status":"READY_RESEARCH_ONLY" if r["facts"] else "INSUFFICIENT_INPUTS","score":confidence,"method":"PROXY_FACT_COVERAGE_ONLY_NOT_INVESTMENT_QUALITY"},"warnings":[]}
    payload={"contract_version":"fundamental_cross_sectional_scoring_and_ranking/v1","denominator":len(records),"residual":0,"records":output,"coverage":{"axis_ready":dict(axis_coverage),"sector_relative_ranking":"NONE_INSUFFICIENT_RETAINED_COMPARABLE_SECTOR_COHORT","composite":"NONE"},"authority_boundary":{"research_only":True,"authoritative_counts_before":13,"authoritative_counts_after":13,"valuation_promoted":False,"recommendation_or_sizing":False,"network_ocr_pdf_vision":False}}
    payload["artifact_sha256"]=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest(); return payload
def execute(*, root: Path = ROOT, cohort_selector: str | None = None):
    """Resolve the versioned current cohort; legacy use requires an explicit selector."""
    return resolve_current_fundamental_cohort(root, selector=cohort_selector)["artifact"]
