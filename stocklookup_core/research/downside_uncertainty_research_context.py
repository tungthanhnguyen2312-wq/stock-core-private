"""Versioned downside/uncertainty contexts; V1 core is immutable from price structure."""
from __future__ import annotations
import hashlib, json
from collections import Counter
from typing import Any, Mapping

METHOD_V1='downside_uncertainty_research_context/v1'; METHOD_V2='downside_uncertainty_research_context/v2'
def _canon(x:Any)->str:return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def _hash(x:Any)->str:return hashlib.sha256(_canon(x).encode()).hexdigest()
def _domain(status,authority,reasons,values,source):return {'status':status,'authority_tier':authority,'reason_codes':reasons,'relevant_values':values,'source_identity':source}

def build(product:Mapping[str,Any],market:Mapping[str,Any],relative:Mapping[str,Any],eligibility:Mapping[str,Any],scenarios:Mapping[str,Any],events:Mapping[str,Any],dossiers:Mapping[str,Any],tasks:Mapping[str,Any],review_pack:Mapping[str,Any],price_context:Mapping[str,Any]|None=None,*,contract_version:str=METHOD_V2)->dict[str,Any]:
 if contract_version not in (METHOD_V1,METHOD_V2):raise ValueError('UNSUPPORTED_DOWNSIDE_CONTRACT_VERSION')
 daily={x['ticker']:x for x in product['stock_research']};rel={x['ticker']:x for x in relative['records']};scen={x['ticker']:x for x in scenarios['scenarios']};ev={x['ticker']:x for x in events['records']};lenses={x['ticker']:x for x in eligibility['records']};price={x['ticker']:x for x in (price_context or {'records':[]})['records']};p75=market['breadth']['volatility']['p75'];rows=[]
 for ticker,r in sorted(daily.items()):
  facts=r['ai_ready_brief']['facts'];trend=r['research_summary']['trend_state'];mom=facts.get('momentum_20d');vol=facts.get('volatility_20d');relative_metric=next((m for m in rel[ticker]['relative_metrics'] if m['metric_identity']=='momentum_20d' and m['status']=='AVAILABLE'),None);core=[]
  if trend=='AT_OR_BELOW_MA20':core.append('AT_OR_BELOW_MA20')
  if isinstance(mom,(int,float)) and mom<0:core.append('NEGATIVE_20D_MOMENTUM')
  if isinstance(vol,(int,float)) and vol>p75:core.append('UPPER_CROSS_SECTIONAL_VOLATILITY_GROUP')
  if relative_metric and relative_metric.get('descriptive_bucket')=='LOWER_QUARTILE':core.append('LOWER_QUARTILE_RELATIVE_MOMENTUM')
  technical=_domain('OBSERVED_ADVERSE_TECHNICAL_CONTEXT' if core else 'NO_OBSERVED_ADVERSE_TECHNICAL_CONDITION','SHADOW_ONLY',core,{'trend_state':trend,'momentum_20d':mom,'volatility_20d':vol,'volatility_p75':p75,'relative_momentum_bucket':relative_metric.get('descriptive_bucket') if relative_metric else None},product['artifact_identity'])
  structure=price.get(ticker,{});state=structure.get('structure_status');price_reasons=[]
  if contract_version==METHOD_V2:
   if state=='BREAKDOWN_CONFIRMED_BY_RULE':price_reasons.append('BREAKDOWN_CONFIRMED_BY_PRICE_STRUCTURE_RULE')
   if state=='NEAR_RECENT_SUPPORT':price_reasons.append('NEAR_RECENT_SUPPORT_PRICE_STRUCTURE_CONTEXT')
  price_domain=_domain('PRICE_STRUCTURE_DOWNSIDE_CONTEXT_PRESENT' if price_reasons else 'NO_PRICE_STRUCTURE_DOWNSIDE_CONTEXT','SHADOW_ONLY',price_reasons,{'price_structure_state':state},price_context.get('artifact_identity') if price_context else None)
  scenario=scen.get(ticker);bear=scenario['scenarios']['BEAR'] if scenario else None;scenario_domain=_domain('SCENARIO_DOWNSIDE_AVAILABLE' if bear else 'SCENARIO_DOWNSIDE_UNAVAILABLE','RESEARCH_SHADOW',['BEAR_DRIVERS_RETAINED'] if bear else ['NO_RETAINED_SCENARIO_FOR_TICKER'],{'bear_driver_count':len(bear['drivers']) if bear else 0,'invalidation_status':bear['invalidation_or_reversal_conditions'][0]['status'] if bear else None,'counter_thesis_hash':dossiers[ticker]['counter_thesis_hash']},scenario['scenario_content_identity'] if scenario else None)
  auth=r['research_summary']['fundamental_authority'];uncertainty=[]
  if auth=='PROVIDER_RESEARCH':uncertainty.append('PROVIDER_RESEARCH_FUNDAMENTAL_CONTEXT')
  if not scenario:uncertainty.append('SCENARIO_CONTEXT_UNAVAILABLE')
  if not ev[ticker]['event_facts']:uncertainty.append('NO_RETAINED_EVENT_EVIDENCE_NOT_NO_EVENT_RISK')
  if any(x['eligibility']=='BLOCKED' for x in lenses[ticker]['lenses'].values()):uncertainty.append('BLOCKED_RESEARCH_LENSES_PRESENT')
  evidence=_domain('EVIDENCE_UNCERTAINTY_HIGHER' if uncertainty else 'EVIDENCE_UNCERTAINTY_LOWER','PROVIDER_RESEARCH' if auth=='PROVIDER_RESEARCH' else 'OFFICIAL_QUALIFIED',uncertainty,{'fundamental_authority':auth,'open_task_count':sum(x['ticker']==ticker for x in tasks.values())},dossiers[ticker]['dossier_identity']);event_facts=ev[ticker]['event_facts'];event=_domain('NO_RETAINED_EVENT_EVIDENCE' if not event_facts else 'EVIDENCED_EVENT_CONTEXT','OFFICIAL_QUALIFIED' if event_facts else 'MISSING',['EVENT_ABSENCE_NOT_EVENT_RISK'] if not event_facts else [],{'event_count':len(event_facts),'temporal_states':[x['temporal_state'] for x in event_facts]},ev[ticker]['event_context_identity']);execution=_domain('EXECUTION_RISK_NOT_ASSESSABLE','BLOCKED',['QUALIFIED_LIQUIDITY_TRADED_VALUE_SEMANTICS_UNAVAILABLE'],{},'strategy_eligibility')
  domains={'TECHNICAL_DOWNSIDE_CONTEXT':technical,'MARKET_CONTEXT_EXPOSURE':_domain(market['breadth']['trend']['descriptor']['descriptor'],'EMPIRICAL_ACTIVE_SHADOW_ONLY',['CONTEMPORANEOUS_EMPIRICAL_COHORT_ONLY'],{'momentum_breadth':market['breadth']['momentum']['descriptor']['descriptor']},market['artifact_identity']),'SCENARIO_DOWNSIDE_CONTEXT':scenario_domain,'EVIDENCE_UNCERTAINTY':evidence,'EXECUTION_RISK_STATUS':execution,'EVENT_VISIBILITY':event}
  if contract_version==METHOD_V2:domains['PRICE_STRUCTURE_DOWNSIDE_CONTEXT']=price_domain
  reasons=list(core)+(price_reasons if contract_version==METHOD_V2 else [])+(['SCENARIO_BEAR_DRIVER_REVIEW'] if bear else [])
  rows.append({'ticker':ticker,'research_session':facts['session'],'domains':domains,'human_downside_review_required':bool(reasons),'human_downside_review_reasons':reasons})
 review={x['ticker'] for x in review_pack['owner_review_queue']};counts=Counter((name,domain['status']) for row in rows for name,domain in row['domains'].items())
 artifact={'schema_version':'1.0.0','contract_version':contract_version,'research_session':product['daily_market_research']['session'],'cohort':{'member_count':len(rows),'authority':'EMPIRICAL_ACTIVE_SHADOW_ONLY'},'source_artifact_identities':{'daily':product['artifact_identity'],'market':market['artifact_identity'],'relative':relative['artifact_identity'],'eligibility':eligibility['artifact_identity'],'scenario':scenarios['artifact_identity'],'event':events['artifact_identity'],'price_structure':price_context.get('artifact_identity') if contract_version==METHOD_V2 and price_context else None},'records':rows,'coverage':{'records':len(rows),'domain_status_counts':{f'{k[0]}:{k[1]}':v for k,v in counts.items()},'core_observed_adverse_technical_count':sum(x['domains']['TECHNICAL_DOWNSIDE_CONTEXT']['status']=='OBSERVED_ADVERSE_TECHNICAL_CONTEXT' for x in rows),'price_structure_downside_context_count':sum(x['domains'].get('PRICE_STRUCTURE_DOWNSIDE_CONTEXT',{}).get('status')=='PRICE_STRUCTURE_DOWNSIDE_CONTEXT_PRESENT' for x in rows),'human_downside_review_required_count':sum(x['human_downside_review_required'] for x in rows),'review_pack_count':len(review),'review_pack_downside_review_count':sum(x['human_downside_review_required'] for x in rows if x['ticker'] in review)},'authority_boundary':{'core_v1_technical_state_excludes_price_structure':True,'near_support_not_core_adverse':True,'event_absence_not_no_event_risk':True,'execution_risk_unassessable_not_high_or_low':True,'evidence_uncertainty_not_economic_risk':True,'no_composite_risk_score_or_rank':True,'no_var_probability_expected_loss_or_recommendation':True},'verdict':'DOWNSIDE_UNCERTAINTY_RESEARCH_V1_RESTORED' if contract_version==METHOD_V1 else 'DOWNSIDE_UNCERTAINTY_RESEARCH_V2_READY'}
 artifact['artifact_sha256']=_hash(artifact);artifact['artifact_identity']='downside_uncertainty_research_context:'+artifact['artifact_sha256'];return artifact
def build_v1(*args,**kwargs):return build(*args,price_context=None,contract_version=METHOD_V1,**kwargs)
def build_v2(*args,**kwargs):return build(*args,contract_version=METHOD_V2,**kwargs)
def review_overlay(context:Mapping[str,Any],review_pack:Mapping[str,Any])->dict[str,Any]:
 by={x['ticker']:x for x in context['records']};out={'schema_version':'1.0.0','contract_version':'downside_uncertainty_review_overlay/v2','downside_context_identity':context['artifact_identity'],'entries':[{'ticker':x['ticker'],'domains':by[x['ticker']]['domains'],'human_downside_review_required':by[x['ticker']]['human_downside_review_required'],'human_downside_review_reasons':by[x['ticker']]['human_downside_review_reasons']} for x in review_pack['owner_review_queue']]};out['artifact_identity']='downside_uncertainty_review_overlay:'+_hash(out);return out
