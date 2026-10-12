"""Deterministic, non-ranking comparison of a bounded research shortlist."""
from __future__ import annotations
import hashlib, json
from typing import Any, Mapping, Sequence

TECHNICAL = ("close", "momentum_20d", "volatility_20d", "relative_volume_provider_scoped")
SUPPORTED = frozenset(("CURRENT_OBSERVABLE_STATE", "RELATIVE_CONTEXT", "FUNDAMENTAL_EVIDENCE",
                       "RESEARCH_LENS_AVAILABILITY", "SCENARIO_COUNTER_THESIS", "EVIDENCE_QUALITY"))

def _canon(x: Any) -> str: return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def _hash(x: Any) -> str: return hashlib.sha256(_canon(x).encode()).hexdigest()

def validate_request(request: Mapping[str, Any], known: set[str], session: str) -> tuple[str, ...]:
    tickers = tuple(str(x).upper() for x in request.get("tickers", ()))
    summary = request.get("mode") == "REVIEW_PACK_SUMMARY"
    if not (2 <= len(tickers) <= (25 if summary else 10)) or len(set(tickers)) != len(tickers): raise ValueError("INVALID_SHORTLIST_SIZE")
    if any(t not in known for t in tickers): raise ValueError("UNKNOWN_TICKER")
    if request.get("research_session") != session: raise ValueError("MIXED_OR_UNKNOWN_RESEARCH_SESSION")
    if not set(request.get("dimensions", ())).issubset(SUPPORTED): raise ValueError("UNSUPPORTED_COMPARISON_DIMENSION")
    return tickers

def _cell(value: Any, authority: str, lineage: str, verdict: str = "COMPARABLE") -> dict[str, Any]:
    return {"value": value, "authority_tier": authority, "evidence_lineage": lineage, "comparability": verdict}

def _technical(tickers: Sequence[str], daily: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows=[]
    for metric in TECHNICAL:
        cells={t:_cell(daily[t]["ai_ready_brief"]["facts"].get(metric), "DERIVED_PROXY" if metric=="relative_volume_provider_scoped" else "SHADOW_ONLY", f"daily_research.{t}.facts.{metric}", "MISSING_INPUT" if daily[t]["ai_ready_brief"]["facts"].get(metric) is None else "COMPARABLE") for t in tickers}
        rows.append({"dimension":metric,"section":"CURRENT_OBSERVABLE_STATE","metric_identity":metric,"method":"retained_daily_research/v1","session":daily[tickers[0]]["ai_ready_brief"]["facts"]["session"],"unit":"VND" if metric=="close" else "DECIMAL_OR_STATE","cells":cells,"comparability":"COMPARABLE" if all(c["comparability"]=="COMPARABLE" for c in cells.values()) else "MISSING_INPUT"})
    trend={t:_cell(daily[t]["research_summary"]["trend_state"],"SHADOW_ONLY",f"daily_research.{t}.trend_state") for t in tickers}
    rows.append({"dimension":"trend_state","section":"CURRENT_OBSERVABLE_STATE","cells":trend,"comparability":"COMPARABLE"})
    return rows

def _relative(tickers: Sequence[str], contexts: Mapping[str, Any]) -> list[dict[str, Any]]:
    source=[contexts[t] for t in tickers]; ids={x["cohort"]["cohort_identity"] for x in source if x.get("cohort") and x["context_status"]=="AVAILABLE"}
    verdict="COMPARABLE" if len(ids)==1 and len(source)==len(ids)*0+len(source) and all(x["context_status"]=="AVAILABLE" for x in source) else "NOT_COMPARABLE_COHORT"
    cells={}
    for t in tickers:
        row=contexts[t]; cells[t]=_cell(row.get("cohort",{}).get("cohort_identity"),row.get("relative_context_authority","UNAVAILABLE"),f"relative_context.{t}", verdict if row["context_status"]=="AVAILABLE" else "MISSING_INPUT")
    return [{"dimension":"relative_context","section":"RELATIVE_CONTEXT","comparability":verdict,"reason":"DIRECT_PERCENTILE_COMPARISON_REQUIRES_ONE_SHARED_COHORT_IDENTITY","cells":cells}]

def _fundamentals(tickers: Sequence[str], daily: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"dimension":"individual_like_for_like_fundamental_values","section":"FUNDAMENTAL_EVIDENCE","comparability":"COMPARISON_UNAVAILABLE","reason":"NO_INDIVIDUAL_LIKE_FOR_LIKE_FUNDAMENTAL_METRIC_RETAINED_IN_DAILY_RESEARCH","cells":{t:_cell(None,daily[t]["research_summary"]["fundamental_authority"],f"daily_research.{t}.fundamental_context","NOT_COMPARABLE_SEMANTICS") for t in tickers}}]

def _lenses(tickers: Sequence[str], eligibility: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows=[]
    for lens in sorted(next(iter(eligibility.values()))["lenses"]):
        rows.append({"dimension":lens,"section":"RESEARCH_LENS_AVAILABILITY","comparability":"COMPARABLE","cells":{t:_cell(eligibility[t]["lenses"][lens]["eligibility"],eligibility[t]["lenses"][lens]["authority_ceiling"],f"eligibility.{t}.{lens}") for t in tickers}})
    return rows

def _statements(tickers: Sequence[str], daily: Mapping[str, Any]) -> list[dict[str, Any]]:
    out=[]
    for left,right in zip(tickers,tickers[1:]):
        for metric,label in (("momentum_20d","20-day momentum"),("volatility_20d","observed volatility")):
            a,b=daily[left]["ai_ready_brief"]["facts"].get(metric),daily[right]["ai_ready_brief"]["facts"].get(metric)
            if isinstance(a,(int,float)) and isinstance(b,(int,float)) and a!=b:
                relation="higher" if a>b else "lower"; out.append({"classification":"FACT","statement":f"{left} has {relation} {label} than {right}.","fields":[f"daily_research.{left}.facts.{metric}",f"daily_research.{right}.facts.{metric}"]})
    return out

def build(request: Mapping[str, Any], *, product: Mapping[str, Any], relative: Mapping[str, Any], eligibility: Mapping[str, Any], scenarios: Mapping[str, Any], dossiers: Mapping[str, Any], tasks: Mapping[str, Any], events: Mapping[str, Any], screener: Mapping[str, Any], review_pack: Mapping[str, Any], market_context: Mapping[str, Any]|None=None, downside_context: Mapping[str, Any]|None=None, price_structure: Mapping[str, Any]|None=None, setup_context: Mapping[str, Any]|None=None) -> dict[str, Any]:
    daily={x["ticker"]:x for x in product["stock_research"]}; tickers=validate_request(request,set(daily),product["daily_market_research"]["session"])
    contexts={x["ticker"]:x for x in relative["records"]}; lenses={x["ticker"]:x for x in eligibility["records"]}; scen={x["ticker"]:x for x in scenarios["scenarios"]}; ev={x["ticker"]:x for x in events["records"]}
    matrix=[]
    dimensions=set(request["dimensions"])
    if "CURRENT_OBSERVABLE_STATE" in dimensions: matrix += _technical(tickers,daily)
    if "RELATIVE_CONTEXT" in dimensions: matrix += _relative(tickers,contexts)
    if "FUNDAMENTAL_EVIDENCE" in dimensions: matrix += _fundamentals(tickers,daily)
    if "RESEARCH_LENS_AVAILABILITY" in dimensions: matrix += _lenses(tickers,lenses)
    if "SCENARIO_COUNTER_THESIS" in dimensions:
        matrix.append({"dimension":"scenario_counter_thesis","section":"SCENARIO_COUNTER_THESIS","comparability":"COMPARABLE","cells":{t:_cell({"scenario_status":scen.get(t,{}).get("scenario_qualification_status","MISSING"),"counter_thesis":dossiers[t]["counter_thesis_hash"],"catalyst_status":ev[t]["catalyst_research_status"]},"RESEARCH_SHADOW",f"scenario_dossier_event.{t}","MISSING_INPUT" if t not in scen else "COMPARABLE") for t in tickers}})
    if "EVIDENCE_QUALITY" in dimensions:
        matrix.append({"dimension":"evidence_quality","section":"EVIDENCE_QUALITY","comparability":"COMPARABLE","cells":{t:_cell({"fundamental_authority":daily[t]["research_summary"]["fundamental_authority"],"warnings":daily[t]["warnings"],"open_task_count":sum(x["ticker"]==t for x in tasks.values())},daily[t]["research_summary"]["fundamental_authority"],f"dossier_task_daily.{t}") for t in tickers}})
    if market_context:
        matrix.append({"dimension":"shared_market_context","section":"MARKET_CONTEXT","comparability":"COMPARABLE","shared_context":True,"value":{"trend_descriptor":market_context['breadth']['trend']['descriptor']['descriptor'],"momentum_descriptor":market_context['breadth']['momentum']['descriptor']['descriptor'],"positive_trend_research_count":market_context['research_participation']['positive_trend_research_count'],"cohort_authority":market_context['cohort']['authority']},"authority_tier":"EMPIRICAL_ACTIVE_SHADOW_ONLY","evidence_lineage":market_context['artifact_identity']})
    if downside_context:
        by={x['ticker']:x for x in downside_context['records']}
        matrix.append({"dimension":"downside_uncertainty_vector","section":"DOWNSIDE_UNCERTAINTY","comparability":"COMPARABLE","cells":{t:_cell({'technical':by[t]['domains']['TECHNICAL_DOWNSIDE_CONTEXT']['status'],'evidence_uncertainty':by[t]['domains']['EVIDENCE_UNCERTAINTY']['status'],'execution':by[t]['domains']['EXECUTION_RISK_STATUS']['status'],'human_review_reasons':by[t]['human_downside_review_reasons']},'RESEARCH_SHADOW',by[t]['domains']['TECHNICAL_DOWNSIDE_CONTEXT']['source_identity']) for t in tickers}})
    if price_structure:
        by={x['ticker']:x for x in price_structure['records']}
        matrix.append({'dimension':'price_structure','section':'PRICE_STRUCTURE','comparability':'COMPARABLE','cells':{t:_cell({'state':by[t]['structure_status'],'range_position':by[t].get('range_position'),'resistance_distance':by[t]['levels']['prior_19_session_close_resistance']['distance_from_close'],'support_distance':by[t]['levels']['prior_19_session_close_support']['distance_from_close']},'SHADOW_ONLY',price_structure['artifact_identity']) for t in tickers}})
    if setup_context:
        by={x['ticker']:x for x in setup_context['records']}; shared=set.intersection(*(set(by[t]['active_setup_ids']) for t in tickers)) if tickers else set(); union=set.union(*(set(by[t]['active_setup_ids']) for t in tickers)) if tickers else set()
        matrix.append({'dimension':'setup_context','section':'SETUP_CONTEXT','comparability':'COMPARABLE','shared_active_setup_ids':sorted(shared),'differing_active_setup_ids':sorted(union-shared),'cells':{t:_cell({'active_setup_ids':by[t]['active_setup_ids'],'record_setup_state':by[t]['record_setup_state'],'active_setup_authorities':by[t]['active_setup_authorities'],'unavailable_setup_reasons':by[t]['unavailable_setup_reasons']},'RESEARCH_SHADOW',setup_context['artifact_identity']) for t in tickers}})
    sources={"daily_product":product["artifact_identity"],"relative":relative["artifact_identity"],"eligibility":eligibility["artifact_identity"],"scenario":scenarios["artifact_identity"],"event":events["artifact_identity"],"screener":screener["artifact_identity"],"review_pack":review_pack["artifact_identity"],"market_context":market_context.get('artifact_identity') if market_context else None,"downside_context":downside_context.get('artifact_identity') if downside_context else None,"price_structure":price_structure.get('artifact_identity') if price_structure else None,"setup_context":setup_context.get('artifact_identity') if setup_context else None}
    output={"schema_version":"1.0.0","contract_version":"evidence_aware_candidate_comparison/v1","comparison_request":dict(request),"research_session":request["research_session"],"ordered_tickers":list(tickers),"source_artifact_identities":sources,"matrix":matrix,"pairwise_observable_statements":_statements(tickers,daily),"questions_requiring_human_judgment":["Evidence provenance and missing capability are not measures of company quality or investment attractiveness."],"authority_boundary":{"not_ranking_or_recommendation":True,"no_composite_score_or_winner":True,"no_mutation_of_source_artifacts":True,"historical_pit_liquidity_sizing_valuation":"NOT_PROMOTED"}}
    output["comparison_identity"]="candidate_comparison:"+_hash({"request":request,"sources":sources,"matrix":matrix}); output["output_identity"]="candidate_comparison_output:"+_hash(output)
    return output
