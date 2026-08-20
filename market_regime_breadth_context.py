"""Contemporaneous empirical-cohort breadth context; not a market forecast or timing model."""
from __future__ import annotations
import hashlib, json
from statistics import median
from typing import Any, Mapping

METHOD = "market_regime_breadth_context/v1"; THRESHOLD = 0.60
def _canon(x: Any) -> str: return json.dumps(x, ensure_ascii=False,sort_keys=True,separators=(',',':'))
def _hash(x: Any) -> str: return hashlib.sha256(_canon(x).encode()).hexdigest()
def _share(n:int,d:int)->float|None:return n/d if d else None
def _descriptor(positive:int, negative:int, denominator:int, *, prefix:str)->dict[str,Any]:
    ps,ns=_share(positive,denominator),_share(negative,denominator)
    value=f'{prefix}_MIXED'
    if ps is not None and ps>=THRESHOLD:value=f'{prefix}_POSITIVE'
    elif ns is not None and ns>=THRESHOLD:value=f'{prefix}_NEGATIVE'
    return {'descriptor':value,'rule_identity':METHOD,'threshold':THRESHOLD,'input_statistics':{'positive_count':positive,'negative_count':negative,'denominator':denominator,'positive_share':ps,'negative_share':ns}}
def build(product:Mapping[str,Any], screener:Mapping[str,Any], review_pack:Mapping[str,Any])->dict[str,Any]:
    rows=product['stock_research']; n=len(rows); trend=[r['research_summary']['trend_state'] for r in rows]; momentum=[r['ai_ready_brief']['facts'].get('momentum_20d') for r in rows]; volatility=[r['ai_ready_brief']['facts'].get('volatility_20d') for r in rows]; rv=[r['ai_ready_brief']['facts'].get('relative_volume_provider_scoped') for r in rows]
    above=trend.count('ABOVE_MA20'); below=trend.count('AT_OR_BELOW_MA20'); tu=n-above-below
    pos=sum(isinstance(x,(int,float)) and x>0 for x in momentum); neg=sum(isinstance(x,(int,float)) and x<0 for x in momentum); mv=[x for x in momentum if isinstance(x,(int,float))]; vv=sorted(x for x in volatility if isinstance(x,(int,float)))
    trend_descriptor=_descriptor(above,below,n-tu,prefix='BREADTH')
    momentum_descriptor=_descriptor(pos,neg,len(mv),prefix='MOMENTUM_BREADTH')
    participation='EMPIRICAL_COHORT_TREND_PARTICIPATION_MIXED'
    if _share(above,n-tu)>=THRESHOLD: participation='EMPIRICAL_COHORT_TREND_PARTICIPATION_BROAD'
    elif _share(above,n-tu)<=1-THRESHOLD: participation='EMPIRICAL_COHORT_TREND_PARTICIPATION_NARROW'
    vol={'available_count':len(vv),'unavailable_count':n-len(vv),'median':median(vv) if vv else None,'p25':vv[int(.25*(len(vv)-1))] if vv else None,'p75':vv[int(.75*(len(vv)-1))] if vv else None,'descriptor':'CROSS_SECTIONAL_VOLATILITY_AVAILABLE' if len(vv)==n else 'CROSS_SECTIONAL_VOLATILITY_PARTIAL','authority_tier':'SHADOW_ONLY','warning':'CONTEMPORANEOUS_CROSS_SECTION_ONLY_NOT_HISTORICAL_REGIME'}
    presets={x['query_name']:x['result_count'] for x in screener['presets']}
    review={x['ticker']:x for x in review_pack['owner_review_queue']}
    overlay=[]
    for ticker in sorted(review):
        record=next(x for x in rows if x['ticker']==ticker)
        overlay.append({'ticker':ticker,'candidate_trend_state':record['research_summary']['trend_state'],'candidate_momentum_20d':record['ai_ready_brief']['facts'].get('momentum_20d'),'context_authority':'EMPIRICAL_ACTIVE_SHADOW_ONLY','limitations':['NOT_AUTHORITATIVE_ACTIVE_UNIVERSE','NOT_MARKET_TIMING_OR_FORECAST']})
    artifact={'schema_version':'1.0.0','contract_version':METHOD,'research_session':product['daily_market_research']['session'],'cohort':{'authority':'EMPIRICAL_ACTIVE_SHADOW_ONLY','member_count':n,'missing_or_excluded_count':0,'cohort_identity':'daily_product:'+product['artifact_identity']},'source_artifact_identities':{'daily_product':product['artifact_identity'],'screener':screener['artifact_identity'],'review_pack':review_pack['artifact_identity']},'breadth':{'trend':{'above_ma20_count':above,'above_ma20_share':_share(above,n-tu),'at_or_below_ma20_count':below,'at_or_below_ma20_share':_share(below,n-tu),'unavailable_count':tu,'descriptor':trend_descriptor},'momentum':{'positive_count':pos,'positive_share':_share(pos,len(mv)),'negative_count':neg,'negative_share':_share(neg,len(mv)),'zero_count':sum(x==0 for x in mv),'unavailable_count':n-len(mv),'median':median(mv) if mv else None,'descriptor':momentum_descriptor},'volatility':vol,'provider_relative_volume':{'available_count':sum(isinstance(x,(int,float)) for x in rv),'unavailable_count':sum(not isinstance(x,(int,float)) for x in rv),'authority_tier':'DERIVED_PROXY','warning':'NOT_LIQUIDITY_OR_TURNOVER'}},'descriptors':[trend_descriptor,momentum_descriptor,{'descriptor':participation,'rule_identity':METHOD,'threshold':THRESHOLD,'input_statistics':{'above_ma20_share':_share(above,n-tu),'eligible_count':n-tu}}],'research_participation':{'positive_trend_research_count':presets.get('POSITIVE_TREND_RESEARCH'),'weak_trend_research_count':presets.get('WEAK_TREND_RESEARCH'),'relative_context_available_count':presets.get('ANY_RELATIVE_CONTEXT_AVAILABLE'),'scenario_review_cohort_count':presets.get('SCENARIO_REVIEW_COHORT'),'definition_note':'POSITIVE_TREND_RESEARCH additionally requires positive momentum; weak trend is an OR predicate.'},'review_pack_overlay':overlay,'authority_boundary':{'not_authoritative_market_universe':True,'not_bull_bear_call_forecast_or_timing':True,'no_eligibility_mutation':True,'no_historical_volatility_regime':True,'no_liquidity_or_valuation_authority':True},'verdict':'MARKET_REGIME_BREADTH_CONTEXT_V1_READY'}
    artifact['artifact_sha256']=_hash(artifact);artifact['artifact_identity']='market_regime_breadth_context:'+artifact['artifact_sha256']
    return artifact

def review_overlay(context: Mapping[str, Any]) -> dict[str, Any]:
    output={'schema_version':'1.0.0','contract_version':'market_regime_breadth_review_overlay/v1','market_context_identity':context['artifact_identity'],'entries':context['review_pack_overlay']}
    output['artifact_sha256']=_hash(output);output['artifact_identity']='market_regime_breadth_review_overlay:'+output['artifact_sha256']
    return output
