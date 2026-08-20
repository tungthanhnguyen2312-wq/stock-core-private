"""Constrained deterministic research discovery filters; never a ranking engine."""
from __future__ import annotations
import hashlib,json
from typing import Any,Mapping

ALLOWED_FIELDS={'momentum_20d','volatility_20d','trend_state','fundamental_authority'}
def _hash(x:Any):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def _eval(p:Mapping[str,Any],r:Mapping[str,Any])->tuple[bool,dict]:
 t=p.get('type')
 if t=='field':
  f=p.get('field');op=p.get('operator');v=r['values'].get(f)
  if f not in ALLOWED_FIELDS:return False,{'predicate':p,'reason':'UNSUPPORTED_FIELD'}
  if v is None:return False,{'predicate':p,'reason':'MISSING_VALUE'}
  try: ok={'==':v==p['value'],'!=':v!=p['value'],'>':v>p['value'],'<':v<p['value'],'>=':v>=p['value'],'<=':v<=p['value']}[op]
  except (KeyError,TypeError):return False,{'predicate':p,'reason':'UNSUPPORTED_OPERATOR_OR_TYPE'}
  return ok,{'predicate':p,'value':v,'reason':'MATCHED' if ok else 'VALUE_NOT_MATCHED'}
 if t=='lens':
  lens=p.get('lens');states=p.get('states');v=r['lenses'].get(lens,{}).get('eligibility')
  if lens not in r['lenses'] or not isinstance(states,list):return False,{'predicate':p,'reason':'UNSUPPORTED_LENS'}
  return v in states,{'predicate':p,'value':v,'reason':'MATCHED' if v in states else 'LENS_STATE_NOT_MATCHED'}
 if t=='relative_available':
  v=r['relative_available'];return v is True,{'predicate':p,'value':v,'reason':'MATCHED' if v else 'RELATIVE_CONTEXT_UNAVAILABLE'}
 if t=='relative_provider_descriptive_available':
  v=r['relative_provider_descriptive_available'];return v is True,{'predicate':p,'value':v,'reason':'MATCHED' if v else 'PROVIDER_DESCRIPTIVE_RELATIVE_CONTEXT_UNAVAILABLE'}
 if t=='relative_any_available':
  v=r['relative_any_available'];return v is True,{'predicate':p,'value':v,'reason':'MATCHED' if v else 'RELATIVE_CONTEXT_UNAVAILABLE'}
 if t=='event_available':
  v=r['event_available'];return v is True,{'predicate':p,'value':v,'reason':'MATCHED' if v else 'NO_EVIDENCE_BACKED_EVENT'}
 if t=='upcoming_event':
  v=r['upcoming_event'];return v is True,{'predicate':p,'value':v,'reason':'MATCHED' if v else 'NO_UPCOMING_EVIDENCED_EVENT'}
 if t=='negative_event':
  v=r['negative_event'];return v is True,{'predicate':p,'value':v,'reason':'MATCHED' if v else 'NO_NEGATIVE_EVENT_CONTEXT'}
 if t=='and':
  x=[_eval(c,r) for c in p.get('clauses',[])];return bool(x) and all(i[0] for i in x),{'predicate':p,'children':[i[1] for i in x]}
 if t=='or':
  x=[_eval(c,r) for c in p.get('clauses',[])];return bool(x) and any(i[0] for i in x),{'predicate':p,'children':[i[1] for i in x]}
 if t=='not':
  ok,x=_eval(p.get('clause',{}),r);return not ok,{'predicate':p,'child':x}
 return False,{'predicate':p,'reason':'UNSUPPORTED_PREDICATE'}
def query(records:list[Mapping[str,Any]], spec:Mapping[str,Any], sources:Mapping[str,Any])->dict:
 rows=[];excluded=[]
 for r in records:
  ok,why=_eval(spec['predicate'],r)
  item={'ticker':r['ticker'],'dossier_identity':r['dossier_identity'],'matching_predicates':why,'values':r['values'],'relevant_lenses':r['lenses'],'authority':r['values']['fundamental_authority'],'warnings':r['warnings']}
  (rows if ok else excluded).append(item)
 a={'schema_version':'1.0.0','contract_version':'evidence_aware_research_screener/v1','query_name':spec['name'],'query_version':'v1','research_session':spec['research_session'],'predicate':spec['predicate'],'source_artifact_identities':sources,'result_count':len(rows),'results':rows,'excluded_count':len(excluded),'excluded_reason_sample':excluded[:5],'verdict':'RESEARCH_DISCOVERY_ONLY'};a['query_identity']='research_screener_query:'+_hash({'name':spec['name'],'predicate':spec['predicate'],'session':spec['research_session']});a['result_identity']='research_screener_result:'+_hash(a);return a
def _specs(session):return [
 {'name':'POSITIVE_TREND_RESEARCH','research_session':session,'predicate':{'type':'and','clauses':[{'type':'lens','lens':'TREND_MOMENTUM_RESEARCH','states':['ELIGIBLE']},{'type':'field','field':'trend_state','operator':'==','value':'ABOVE_MA20'},{'type':'field','field':'momentum_20d','operator':'>','value':0}]}},
 {'name':'WEAK_TREND_RESEARCH','research_session':session,'predicate':{'type':'or','clauses':[{'type':'field','field':'trend_state','operator':'==','value':'AT_OR_BELOW_MA20'},{'type':'field','field':'momentum_20d','operator':'<','value':0}]}},
 {'name':'FUNDAMENTAL_CONTEXT_AVAILABLE','research_session':session,'predicate':{'type':'lens','lens':'DESCRIPTIVE_FUNDAMENTAL_RESEARCH','states':['ELIGIBLE','ELIGIBLE_LOWER_AUTHORITY']}},
 {'name':'HIGHER_AUTHORITY_FUNDAMENTAL_RESEARCH','research_session':session,'predicate':{'type':'lens','lens':'OFFICIAL_FUNDAMENTAL_RESEARCH','states':['ELIGIBLE']}},
 {'name':'RELATIVE_CONTEXT_AVAILABLE','research_session':session,'predicate':{'type':'lens','lens':'RELATIVE_TECHNICAL_RESEARCH','states':['ELIGIBLE']}},
 {'name':'PROVIDER_DESCRIPTIVE_RELATIVE_CONTEXT_AVAILABLE','research_session':session,'predicate':{'type':'relative_provider_descriptive_available'}},
 {'name':'ANY_RELATIVE_CONTEXT_AVAILABLE','research_session':session,'predicate':{'type':'relative_any_available'}},
 {'name':'EVIDENCE_BACKED_EVENT_AVAILABLE','research_session':session,'predicate':{'type':'event_available'}},
 {'name':'UPCOMING_EVIDENCED_EVENT','research_session':session,'predicate':{'type':'upcoming_event'}},
 {'name':'NEGATIVE_EVENT_CONTEXT','research_session':session,'predicate':{'type':'negative_event'}},
 {'name':'CATALYST_RESEARCH_AVAILABLE','research_session':session,'predicate':{'type':'lens','lens':'CATALYST_RESEARCH','states':['ELIGIBLE']}},
 {'name':'SCENARIO_REVIEW_COHORT','research_session':session,'predicate':{'type':'lens','lens':'SCENARIO_RESEARCH','states':['PARTIAL','ELIGIBLE']}},
 {'name':'RESEARCHABLE_BUT_EXECUTION_BLOCKED','research_session':session,'predicate':{'type':'and','clauses':[{'type':'lens','lens':'TREND_MOMENTUM_RESEARCH','states':['ELIGIBLE']},{'type':'lens','lens':'LIQUIDITY_SENSITIVE_RESEARCH','states':['BLOCKED']}]}}
 ]
def build(product:Mapping[str,Any],eligibility:Mapping[str,Any],context:Mapping[str,Any],dossiers:Mapping[str,Any],event_context:Mapping[str,Any]|None=None)->dict:
 er={x['ticker']:x for x in eligibility['records']};cr={x['ticker']:x for x in context['records']};ev={x['ticker']:x for x in (event_context or {'records':[]})['records']}; rows=[]
 for r in product['stock_research']:
  t=r['ticker']; authority=cr[t].get('relative_context_authority'); event=ev.get(t,{}); facts=event.get('event_facts',[]);rows.append({'ticker':t,'dossier_identity':dossiers[t]['dossier_identity'],'values':{'momentum_20d':r['ai_ready_brief']['facts']['momentum_20d'],'volatility_20d':r['ai_ready_brief']['facts']['volatility_20d'],'trend_state':r['research_summary']['trend_state'],'fundamental_authority':r['research_summary']['fundamental_authority']},'lenses':er[t]['lenses'],'relative_available':cr[t]['context_status']=='AVAILABLE' and authority=='QUALIFIED_CLASSIFICATION','relative_provider_descriptive_available':cr[t]['context_status']=='AVAILABLE' and authority=='PROVIDER_DESCRIPTIVE_CLASSIFICATION','relative_any_available':cr[t]['context_status']=='AVAILABLE','relative_context_authority':authority,'event_available':bool(facts),'upcoming_event':any(x['temporal_state']=='ANNOUNCED_FUTURE' for x in facts),'negative_event':any(x.get('research_direction')=='NEGATIVE' for x in event.get('catalyst_interpretations',[])),'event_context_identity':event.get('event_context_identity'),'warnings':r['warnings']})
 sources={'daily_product':product['artifact_identity'],'eligibility':eligibility['artifact_identity'],'relative_context':context['artifact_identity'],'event_context':event_context.get('artifact_identity') if event_context else None}; presets=[query(rows,s,sources) for s in _specs(product['daily_market_research']['session'])];a={'schema_version':'1.0.0','contract_version':'evidence_aware_research_screener/v1','research_session':product['daily_market_research']['session'],'cohort_scope':'EMPIRICAL_ACTIVE_SHADOW_ONLY','source_artifact_identities':sources,'records':rows,'presets':presets,'verdict':'EVIDENCE_AWARE_RESEARCH_SCREENER_V1_READY'};a['artifact_sha256']=_hash(a);a['artifact_identity']='evidence_aware_research_screener:'+a['artifact_sha256'];return a
def review_overlay(pack:Mapping[str,Any],screen:Mapping[str,Any])->dict:
 matches={t:[] for t in [x['ticker'] for x in pack['owner_review_queue']]}
 for p in screen['presets']:
  for r in p['results']:
   if r['ticker'] in matches:matches[r['ticker']].append({'preset':p['query_name'],'query_identity':p['query_identity']})
 o={'schema_version':'1.0.0','contract_version':'screener_review_pack_overlay/v1','base_review_pack_identity':pack['artifact_identity'],'screener_identity':screen['artifact_identity'],'entries':[{'ticker':t,'matched_presets':x} for t,x in sorted(matches.items())]};o['artifact_sha256']=_hash(o);o['artifact_identity']='screener_review_pack_overlay:'+o['artifact_sha256'];return o
