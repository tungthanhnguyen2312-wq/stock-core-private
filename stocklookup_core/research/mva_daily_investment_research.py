"""Deterministic, non-actionable daily research product over P3-F18 synthesis."""
from __future__ import annotations
import hashlib,json
from typing import Any,Mapping
def _hash(x:Any):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def build(synthesis:Mapping[str,Any])->dict[str,Any]:
 records=[]
 for r in synthesis['records']:
  f=r['facts']; inf={x['category']:x['value'] for x in r['deterministic_inferences']}; reasons=[]
  if f.get('momentum_20d',0)>=.10: reasons.append('STRONG_20D_MOMENTUM')
  if f.get('momentum_20d',0)<=-.10: reasons.append('WEAK_20D_MOMENTUM')
  if inf.get('trend_state')=='ABOVE_MA20': reasons.append('ABOVE_MA20_TREND')
  if (f.get('relative_volume_provider_scoped') or 0)>=1.5: reasons.append('ELEVATED_PROVIDER_RELATIVE_VOLUME')
  if inf.get('fundamental_evidence')=='OFFICIAL_QUALIFIED': reasons.append('OFFICIAL_FUNDAMENTAL_CONTEXT_AVAILABLE')
  records.append({'ticker':r['ticker'],'research_summary':{'trend_state':inf.get('trend_state'),'momentum_20d':f.get('momentum_20d'),'volatility_20d':f.get('volatility_20d'),'provider_relative_volume':f.get('relative_volume_provider_scoped'),'fundamental_authority':inf.get('fundamental_evidence'),'attention_descriptors':reasons,'attention_is_recommendation':False},'warnings':r['data_warnings'],'ai_ready_brief':{'facts':f,'deterministic_inferences':r['deterministic_inferences'],'warnings':r['data_warnings'],'ai_must_not_create_numerical_authority':True}})
 attention=[r for r in records if r['research_summary']['attention_descriptors']]
 overview=synthesis['market_overview'];a={'schema_version':'1.0.0','contract_version':'mva_daily_investment_research/v1','daily_market_research':{'session':records[0]['ai_ready_brief']['facts']['session'],'breadth':overview['breadth'],'coverage':synthesis['coverage'],'market_warning':'EMPIRICAL_SHADOW_COHORT_NOT_ACTIVE_UNIVERSE'},'stock_research':records,'research_attention':attention,'representative_deep_dives':{'strong_momentum':next((r for r in records if 'STRONG_20D_MOMENTUM' in r['research_summary']['attention_descriptors']),None),'weak_momentum':next((r for r in records if 'WEAK_20D_MOMENTUM' in r['research_summary']['attention_descriptors']),None),'official_fundamentals':next((r for r in records if r['research_summary']['fundamental_authority']=='OFFICIAL_QUALIFIED'),None),'provider_descriptive':next((r for r in records if r['research_summary']['fundamental_authority']=='PROVIDER_RESEARCH'),None)},'safety':synthesis['safety_envelope'],'top_remaining_analytical_gaps':['authoritative current shares for broader valuation context','qualified liquidity/traded-value authority for investment implementation','historical PIT price and corporate-action authority'],'next_milestone':'MARKET-WIDE CURRENT SHARE AUTHORITY EVIDENCE SCALE-OUT','verdict':'MVA_DAILY_INVESTMENT_RESEARCH_V1_COMPLETE'};a['artifact_sha256']=_hash(a);a['artifact_identity']='mva_daily_investment_research:'+a['artifact_sha256'];return a
