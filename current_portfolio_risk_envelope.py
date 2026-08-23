"""Current explicit-portfolio concentration envelope; never infers holdings or sizing."""
from __future__ import annotations
import copy
from collections import Counter,defaultdict
from typing import Any,Mapping
from field_temporal_contract import stable_id
CONTRACT_VERSION='current_portfolio_risk_envelope/v1'
def identity(a:Mapping[str,Any]):
 p=copy.deepcopy(dict(a));p.pop('artifact_identity',None);p.pop('artifact_sha256',None);h=stable_id(p);return {'artifact_sha256':h,'artifact_identity':'current_portfolio_risk_envelope:'+h}
def _sum(rows,key):
 groups=defaultdict(list)
 for row in rows: groups[row[key]].append(row)
 return dict(sorted((k,round(sum(x['weight'] for x in values),10)) for k,values in groups.items()))
def build(*,portfolio:Mapping[str,Any],descriptive:Mapping[str,Any],tactical:Mapping[str,Any],peer_relative:Mapping[str,Any],fundamental:Mapping[str,Any],valuation:Mapping[str,Any],scenario:Mapping[str,Any],strategy:Mapping[str,Any],corporate_intelligence:Mapping[str,Any])->dict[str,Any]:
 if not portfolio.get('portfolio_id') or not isinstance(portfolio.get('positions'),list) or not portfolio['positions']: raise ValueError('EXPLICIT_PORTFOLIO_POSITIONS_REQUIRED')
 if portfolio.get('as_of_session')!=descriptive.get('session'): raise ValueError('PORTFOLIO_SESSION_MISMATCH')
 prices=descriptive.get('records',{}); rows=[]
 for p in portfolio['positions']:
  t=str(p.get('ticker') or '').upper(); weight=p.get('explicit_weight'); value=p.get('explicit_market_value'); tech=(prices.get(t) or {}).get('technical_features') or {}
  if weight is not None: exposure=float(weight);basis='USER_SUPPLIED_EXPOSURE'
  elif value is not None: exposure=float(value);basis='USER_SUPPLIED_EXPOSURE'
  elif p.get('quantity') is not None and tech.get('is_current_session') and tech.get('values',{}).get('close') is not None: exposure=float(p['quantity'])*float(tech['values']['close']);basis='CURRENT_PRICE_DERIVED_EXPOSURE'
  else: raise ValueError('POSITION_EXPOSURE_UNAVAILABLE:'+t)
  rows.append({'ticker':t,'raw_exposure':exposure,'exposure_basis':basis,'price_identity':tech.get('feature_as_of_session'),'position_input_identity':'portfolio_position:'+stable_id(p),'input':dict(p)})
 total=sum(x['raw_exposure'] for x in rows)
 if total<=0: raise ValueError('PORTFOLIO_TOTAL_EXPOSURE_NONPOSITIVE')
 for x in rows:
  t=x['ticker'];x['weight']=x['raw_exposure']/total;pe=peer_relative.get('records',{}).get(t) or {};fu=fundamental.get('records',{}).get(t) or {};st=strategy.get('records',{}).get(t) or {};sc=scenario.get('records',{}).get(t) or {};ci=corporate_intelligence.get('records',{}).get(t) or {};ta=tactical.get('records',{}).get(t) or {}
  alignment=(fu.get('fundamental_trajectory_context') or {}).get('revenue_vs_earnings_alignment',{}); alignment=alignment.get('status','UNAVAILABLE') if isinstance(alignment,Mapping) else str(alignment)
  x.update({'entity_class':fu.get('entity_class','unknown'),'strategy_state':st.get('record_strategy_state','DATA_LIMITED'),'strategies':st.get('eligible_strategy_ids',[]),'tactical_state':ta.get('entry_state','UNAVAILABLE'),'scenario_state':sc.get('scenario_disposition','UNAVAILABLE'),'fundamental_authority':fu.get('authority_tier','UNAVAILABLE'),'fundamental_alignment':alignment,'event_state':'CURRENT_EVENT' if (ci.get('catalyst_research') or {}).get('recent_material_events') else 'HISTORICAL_OR_PENDING_EVENT' if ci.get('events') else 'NO_RETAINED_INTELLIGENCE','technical_quality':'CURRENT_TECHNICAL' if (ta.get('data_quality') or {}).get('technical_eligible') else 'TECHNICAL_DATA_GAP','volatility':(ta.get('signals') or {}).get('volatility_20d')})
 limits=portfolio.get('risk_limits') or {}; breaches=[]
 def check(name,value,limit):
  if limit is not None: breaches.append({'limit_id':name,'status':'LIMIT_BREACH' if value>float(limit) else 'WITHIN_LIMIT','observed':value,'limit':float(limit)})
 single={x['ticker']:x['weight'] for x in rows}; entity=_sum(rows,'entity_class'); tactical_s=_sum(rows,'tactical_state'); strategy_cov={s:round(sum(x['weight'] for x in rows if s in x['strategies']),10) for s in strategy['strategy_registry']}
 check('max_single_name_weight',max(single.values()),limits.get('max_single_name_weight'))
 for k,v in entity.items(): check('max_sector_weight:'+k,v,limits.get('max_sector_weight'))
 for k,v in strategy_cov.items(): check('max_strategy_exposure:'+k,v,(limits.get('max_strategy_exposure') or {}).get(k))
 check('max_distribution_risk_weight',sum(x['weight'] for x in rows if x['tactical_state'] in {'DISTRIBUTION_RISK','BREAKDOWN_RISK','DOWNTREND'}),limits.get('max_distribution_risk_weight'))
 blocked={k:{'status':'BLOCKED' if k not in {'leverage'} else 'NOT_EVALUATED','reason':'QUALIFIED_LIQUIDITY_PIT_OR_POLICY_INPUTS_NOT_AVAILABLE'} for k in ('liquidity','days_to_liquidate','portfolio_volatility','correlation','VaR','CVaR','position_sizing','leverage','execution')}
 a={'schema_version':'1.0.0','contract_version':CONTRACT_VERSION,'portfolio_id':portfolio['portfolio_id'],'portfolio_kind':portfolio.get('portfolio_kind','EXPLICIT_USER_PORTFOLIO'),'base_currency':portfolio.get('base_currency','UNSPECIFIED'),'session':descriptive['session'],'input_identity':'portfolio_input:'+stable_id(portfolio),'source_artifact_identities':{'descriptive':descriptive.get('artifact_identity'),'tactical':tactical.get('artifact_identity'),'peer_relative':peer_relative.get('artifact_identity'),'fundamental':fundamental.get('artifact_identity'),'valuation':valuation.get('artifact_identity'),'scenario':scenario.get('artifact_identity'),'strategy':strategy.get('artifact_identity'),'corporate_intelligence':corporate_intelligence.get('artifact_identity')},'positions':rows,'total_evaluable_exposure':total,'unevaluable_exposure':0,'concentration':{'single_name':single,'entity_class':entity,'strategy_coverage':strategy_cov,'strategy_overlap_state':_sum(rows,'strategy_state'),'tactical_state':tactical_s},'scenario_risk':_sum(rows,'scenario_state'),'fundamental_context':{'authority':_sum(rows,'fundamental_authority'),'alignment':_sum(rows,'fundamental_alignment')},'event_context':_sum(rows,'event_state'),'data_quality_context':_sum(rows,'technical_quality'),'descriptive_volatility_context':{'weighted_average_descriptive_volatility':sum(x['weight']*x['volatility'] for x in rows if isinstance(x['volatility'],(int,float))),'status':'DESCRIPTIVE_NOT_PORTFOLIO_VOLATILITY'},'user_limit_results':breaches,'blocked_risk_dimensions':blocked,'position_sizing_status':'BLOCKED','portfolio_fit_contract':{'status':'AVAILABLE','method':'candidate sector/strategy/tactical overlap only; no candidate weight or recommendation'},'authority_boundary':{'explicit_holdings_required':True,'watchlist_not_portfolio':True,'no_sizing_or_optimal_allocation':True,'probability_weighted_risk_not_emitted':True},'is_actionable':False};a.update(identity(a));return a
def portfolio_fit(artifact:Mapping[str,Any],candidate:Mapping[str,Any])->dict[str,Any]:
 rows=artifact['positions'];return {'ticker':candidate['ticker'],'same_entity_class_exposure':artifact['concentration']['entity_class'].get(candidate.get('entity_class','unknown'),0),'same_strategy_exposure':{s:artifact['concentration']['strategy_coverage'].get(s,0) for s in candidate.get('eligible_strategy_ids',[])},'same_tactical_state_exposure':artifact['concentration']['tactical_state'].get(candidate.get('tactical_state'),0),'status':'PORTFOLIO_FIT_DATA_LIMITED' if candidate.get('strategy_state')=='DATA_LIMITED' else 'ADDS_SECTOR_CONCENTRATION' if artifact['concentration']['entity_class'].get(candidate.get('entity_class','unknown'),0)>0 else 'LOW_INCREMENTAL_DIVERSIFICATION','is_actionable':False}
