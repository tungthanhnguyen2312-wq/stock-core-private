"""Deterministic current peer-relative research; never a ranking or recommendation."""
from __future__ import annotations
import copy
from collections import Counter,defaultdict
from typing import Any,Mapping
from field_temporal_contract import stable_id

CONTRACT_VERSION='sector_aware_relative_research/v1'; MIN_COHORT=5
def content_identity(a:Mapping[str,Any])->dict[str,str]:
 p=copy.deepcopy(dict(a));p.pop('artifact_sha256',None);p.pop('artifact_identity',None);h=stable_id(p);return {'artifact_sha256':h,'artifact_identity':'sector_aware_relative_research:'+h}
def build(*,descriptive:Mapping[str,Any],tactical:Mapping[str,Any],fundamental:Mapping[str,Any],valuation:Mapping[str,Any])->dict[str,Any]:
 d=descriptive['records'];t=tactical['records'];f=fundamental['records'];v=valuation['records']; groups=defaultdict(list)
 for ticker,row in d.items():
  entity=(f.get(ticker) or {}).get('entity_class') or (row.get('sector_classification') or {}).get('entity_class') or 'unknown'
  groups[entity.upper()].append(ticker)
 records={}
 for ticker,row in sorted(d.items()):
  entity=(f.get(ticker) or {}).get('entity_class') or (row.get('sector_classification') or {}).get('entity_class') or 'unknown'; peers=sorted(groups[entity.upper()]); tech=(row.get('technical_features') or {});tr=t.get(ticker,{});fr=f.get(ticker,{});vr=v.get(ticker,{})
  align=(fr.get('fundamental_trajectory_context') or {}).get('revenue_vs_earnings_alignment');shadow=(vr.get('shadow_proxy_valuation') or {}).get('metrics') or {}
  eligible=[x for x in peers if (d[x].get('technical_features') or {}).get('is_current_session')]
  status='AVAILABLE' if len(peers)>=MIN_COHORT else 'INSUFFICIENT_COHORT'
  expectation=('MARKET_AND_FUNDAMENTALS_ALIGNED_POSITIVE' if tr.get('entry_state') in {'BREAKOUT_READY','UPTREND_CONFIRMED'} and align=='BOTH_EXPANDING' else 'TECHNICAL_RECOVERY_WITH_FUNDAMENTAL_UNCERTAINTY' if tr.get('entry_state')=='EARLY_REVERSAL_CANDIDATE' and not align else 'MIXED_OR_INSUFFICIENT_EVIDENCE')
  records[ticker]={'ticker':ticker,'peer_membership':{'peer_group_id':entity.upper(),'peer_group_label':entity,'candidate_count':len(peers),'status':status,'classification_source':(row.get('sector_classification') or fr.get('entity_class_provenance')),'membership_reason':'RETAINED_ENTITY_CLASS'},'technical_peer_context':{'eligible_count':len(eligible),'status':'AVAILABLE' if len(eligible)>=MIN_COHORT and tech.get('is_current_session') else 'INSUFFICIENT_COHORT_OR_METRIC_UNAVAILABLE','technical_state':tr.get('ticker_structure_state'),'entry_state':tr.get('entry_state')},'fundamental_peer_context':{'status':'AVAILABLE' if len(peers)>=MIN_COHORT and align else 'UNAVAILABLE','authority_tier':fr.get('authority_tier'),'alignment':align},'valuation_peer_context':{'status':'VALUATION_PEER_CONTEXT_UNAVAILABLE','shadow_proxy_available':any(x.get('status')=='SHADOW_PROXY_READY' for x in shadow.values())},'expectations_context':{'state':expectation,'descriptive_only':True},'is_actionable':False}
 artifact={'schema_version':'1.0.0','contract_version':CONTRACT_VERSION,'session':descriptive['session'],'source_artifacts':{'descriptive':descriptive['artifact_identity'],'tactical':tactical['artifact_identity'],'fundamental':fundamental['artifact_identity'],'valuation':valuation['artifact_identity']},'peer_groups':{k:{'member_count':len(x),'members':sorted(x),'status':'AVAILABLE' if len(x)>=MIN_COHORT else 'INSUFFICIENT_COHORT'} for k,x in sorted(groups.items())},'records':records,'coverage':{'candidate_universe':len(records),'peer_membership_available':sum(r['peer_membership']['status']=='AVAILABLE' for r in records.values()),'technical_peer_available':sum(r['technical_peer_context']['status']=='AVAILABLE' for r in records.values()),'fundamental_peer_available':sum(r['fundamental_peer_context']['status']=='AVAILABLE' for r in records.values()),'shadow_valuation_available':sum(r['valuation_peer_context']['shadow_proxy_available'] for r in records.values()),'expectations_counts':dict(Counter(r['expectations_context']['state'] for r in records.values()))},'authority_boundary':{'ranking':False,'recommendation':False,'target_price':False,'provider_absolute_fundamentals':False,'shadow_valuation_non_authoritative':True},'is_actionable':False};artifact.update(content_identity(artifact));return artifact
