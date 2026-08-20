"""Versioned feature-to-research-lens eligibility; never a signal or recommendation."""
from __future__ import annotations
import hashlib, json
from collections import Counter
from typing import Any, Mapping

REGISTRY = {
 "TREND_MOMENTUM_RESEARCH": {"requires": ["close", "trend_state", "momentum_20d", "volatility_20d"], "ceiling": "SHADOW_ONLY"},
 "RELATIVE_TECHNICAL_RESEARCH": {"requires": ["TREND_MOMENTUM_RESEARCH", "qualified_same_session_cohort"], "ceiling": "SHADOW_ONLY"},
 "DESCRIPTIVE_FUNDAMENTAL_RESEARCH": {"requires": ["fundamental_context", "descriptive_only_contract"], "ceiling": "PROVIDER_RESEARCH"},
 "OFFICIAL_FUNDAMENTAL_RESEARCH": {"requires": ["OFFICIAL_QUALIFIED_fundamental_context"], "ceiling": "OFFICIAL_QUALIFIED"},
 "SCENARIO_RESEARCH": {"requires": ["scenario", "dossier", "task_lineage"], "ceiling": "RESEARCH_SHADOW"},
 "CATALYST_RESEARCH": {"requires": ["evidence_backed_catalyst"], "ceiling": "RESEARCH_SHADOW"},
 "LIQUIDITY_SENSITIVE_RESEARCH": {"requires": ["qualified_liquidity_traded_value"], "ceiling": "QUALIFIED_LIQUIDITY"},
 "VALUATION_RESEARCH": {"requires": ["authoritative_valuation_contract"], "ceiling": "OFFICIAL_QUALIFIED"},
 "HISTORICAL_PIT_STRATEGY_RESEARCH": {"requires": ["RAW_AS_TRADED", "historical_PIT"], "ceiling": "HISTORICAL_PIT"},
}
def _hash(x:Any): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def _v(lens,status,ceiling,reasons,inputs): return {"lens_identity":f"{lens}/v1","eligibility":status,"authority_ceiling":ceiling,"reason_codes":reasons,"observed_input_statuses":inputs}

def build(product:Mapping[str,Any], context:Mapping[str,Any], scenarios:Mapping[str,Any], event_context:Mapping[str,Any]|None=None)->dict[str,Any]:
 ctx={x['ticker']:x for x in context['records']}; sc={x['ticker']:x for x in scenarios['scenarios']}; ev={x['ticker']:x for x in (event_context or {'records':[]})['records']}; rows=[]
 for r in sorted(product['stock_research'],key=lambda x:x['ticker']):
  t=r['ticker']; f=r['ai_ready_brief']['facts']; a=r['research_summary']['fundamental_authority']; c=ctx[t]; s=sc.get(t); event=ev.get(t)
  trend_ok=all(f.get(k) is not None for k in ('close','momentum_20d','volatility_20d')) and r['research_summary']['trend_state'] is not None
  lenses={
   'TREND_MOMENTUM_RESEARCH':_v('TREND_MOMENTUM_RESEARCH','ELIGIBLE' if trend_ok else 'UNAVAILABLE','SHADOW_ONLY',[] if trend_ok else ['TECHNICAL_INPUT_MISSING'],{'exact_session':f.get('session'),'trend_state':r['research_summary']['trend_state']}),
   'RELATIVE_TECHNICAL_RESEARCH':_v('RELATIVE_TECHNICAL_RESEARCH',
      'ELIGIBLE' if c['context_status']=='AVAILABLE' and c.get('relative_context_authority')=='QUALIFIED_CLASSIFICATION' else
      'ELIGIBLE_LOWER_AUTHORITY' if c['context_status']=='AVAILABLE' and c.get('relative_context_authority')=='PROVIDER_DESCRIPTIVE_CLASSIFICATION' else 'BLOCKED',
      'SHADOW_ONLY', [] if c['context_status']=='AVAILABLE' else ['QUALIFIED_COMPARISON_COHORT_UNAVAILABLE'],
      {'relative_context_status':c['context_status'],'relative_context_authority':c.get('relative_context_authority','UNAVAILABLE'),'cohort_identity':c['cohort']['cohort_identity'] if c['cohort'] else None}),
   'DESCRIPTIVE_FUNDAMENTAL_RESEARCH':_v('DESCRIPTIVE_FUNDAMENTAL_RESEARCH','ELIGIBLE' if a=='OFFICIAL_QUALIFIED' else 'ELIGIBLE_LOWER_AUTHORITY' if a=='PROVIDER_RESEARCH' else 'UNAVAILABLE',a,['PROVIDER_FUNDAMENTALS_DESCRIPTIVE_ONLY'] if a=='PROVIDER_RESEARCH' else [],{'fundamental_authority':a}),
   'OFFICIAL_FUNDAMENTAL_RESEARCH':_v('OFFICIAL_FUNDAMENTAL_RESEARCH','ELIGIBLE' if a=='OFFICIAL_QUALIFIED' else 'UNAVAILABLE','OFFICIAL_QUALIFIED',[] if a=='OFFICIAL_QUALIFIED' else ['OFFICIAL_QUALIFIED_FUNDAMENTAL_CONTEXT_MISSING'],{'fundamental_authority':a}),
   'SCENARIO_RESEARCH':_v('SCENARIO_RESEARCH','PARTIAL' if s else 'UNAVAILABLE','RESEARCH_SHADOW',['SCENARIO_PARTIAL_EVIDENCE_BOUND'] if s else ['SCENARIO_OBJECT_NOT_RETAINED'],{'scenario_identity':s['scenario_content_identity'] if s else None}),
   'CATALYST_RESEARCH':_v('CATALYST_RESEARCH','ELIGIBLE' if event and event['event_facts'] else 'UNAVAILABLE','RESEARCH_SHADOW',[] if event and event['event_facts'] else ['NO_EVIDENCE_BACKED_CATALYST'],{'scenario_present':bool(s),'event_context_identity':event['event_context_identity'] if event else None,'event_fact_count':len(event['event_facts']) if event else 0}),
   'LIQUIDITY_SENSITIVE_RESEARCH':_v('LIQUIDITY_SENSITIVE_RESEARCH','BLOCKED','BLOCKED',['QUALIFIED_LIQUIDITY_INPUTS_NOT_AVAILABLE'],{'liquidity_sizing_authority':'BLOCKED'}),
   'VALUATION_RESEARCH':_v('VALUATION_RESEARCH','BLOCKED','BLOCKED',['AUTHORITATIVE_VALUATION_CONTRACT_NOT_AVAILABLE'],{'valuation_scope':'CURRENT_DESCRIPTIVE_ONLY'}),
   'HISTORICAL_PIT_STRATEGY_RESEARCH':_v('HISTORICAL_PIT_STRATEGY_RESEARCH','BLOCKED','BLOCKED',['RAW_AS_TRADED_NOT_PROMOTED','HISTORICAL_PIT_NOT_ELIGIBLE'],{'pit_backtest_eligible':False}),
  }
  rows.append({'ticker':t,'research_session':f['session'],'source_daily_record':product['artifact_identity'],'lenses':lenses,'scenario_support_lenses':[k for k in ('TREND_MOMENTUM_RESEARCH','RELATIVE_TECHNICAL_RESEARCH','DESCRIPTIVE_FUNDAMENTAL_RESEARCH') if lenses[k]['eligibility'] in ('ELIGIBLE','ELIGIBLE_LOWER_AUTHORITY')]})
 counts={}; reasons=Counter()
 for row in rows:
  for lens,v in row['lenses'].items():
   counts.setdefault(lens,Counter())[v['eligibility']]+=1; reasons.update(v['reason_codes'])
 artifact={'schema_version':'1.0.0','contract_version':'strategy_research_eligibility/v1','registry':REGISTRY,'research_session':product['daily_market_research']['session'],'cohort_scope':'EMPIRICAL_ACTIVE_SHADOW_ONLY','source_event_context_identity':event_context.get('artifact_identity') if event_context else None,'records':rows,'coverage':{'records':len(rows),'per_lens_status_counts':{k:dict(v) for k,v in counts.items()},'top_reason_counts':dict(reasons),'at_least_one_usable':sum(any(v['eligibility'] in ('ELIGIBLE','ELIGIBLE_LOWER_AUTHORITY','PARTIAL') for v in r['lenses'].values()) for r in rows),'multiple_complementary_lenses':sum(sum(v['eligibility'] in ('ELIGIBLE','ELIGIBLE_LOWER_AUTHORITY') for v in r['lenses'].values())>=2 for r in rows),'fully_blocked':sum(not any(v['eligibility'] in ('ELIGIBLE','ELIGIBLE_LOWER_AUTHORITY','PARTIAL') for v in r['lenses'].values()) for r in rows)},'authority_boundary':{'not_a_signal_or_recommendation':True,'ranking':'NOT_EMITTED','portfolio_execution':'NOT_EMITTED'},'verdict':'STRATEGY_RESEARCH_ELIGIBILITY_V1_READY'}; artifact['artifact_sha256']=_hash(artifact);artifact['artifact_identity']='strategy_research_eligibility:'+artifact['artifact_sha256'];return artifact
def review_overlay(pack:Mapping[str,Any], artifact:Mapping[str,Any])->dict[str,Any]:
 by={r['ticker']:r for r in artifact['records']}; entries=[]
 for q in pack['owner_review_queue']:
  r=by[q['ticker']]; ls=r['lenses']; entries.append({'ticker':q['ticker'],'base_review_pack_identity':pack['artifact_identity'],'usable_lenses':[f"{k}: {v['eligibility']} / {v['authority_ceiling']}" for k,v in ls.items() if v['eligibility'] in ('ELIGIBLE','ELIGIBLE_LOWER_AUTHORITY')],'partial_lenses':[f"{k}: PARTIAL" for k,v in ls.items() if v['eligibility']=='PARTIAL'],'materially_blocked_lenses':[{ 'lens':k,'reasons':v['reason_codes']} for k,v in ls.items() if v['eligibility']=='BLOCKED']})
 o={'schema_version':'1.0.0','contract_version':'strategy_research_eligibility_review_overlay/v1','base_review_pack_identity':pack['artifact_identity'],'eligibility_identity':artifact['artifact_identity'],'entries':entries};o['artifact_sha256']=_hash(o);o['artifact_identity']='strategy_research_eligibility_review_overlay:'+o['artifact_sha256'];return o
