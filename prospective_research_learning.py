"""Immutable prospective research snapshots and later exact-session attribution.

This is shadow prospective learning, never historical PIT backtesting.
"""
from __future__ import annotations
import copy,hashlib,json
import statistics
from pathlib import Path
from typing import Any,Mapping
from prospective_research_context_extension import ATTRIBUTION_SAFE_SUCCESSOR_ID,SUPERSEDED_LEGACY_EXTENSION_ID
def _canon(x:Any):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def _hash(x:Any):return hashlib.sha256(_canon(x).encode()).hexdigest()


OPPORTUNITY_DECISION_FREEZE_CONTRACT = 'prospective_research_learning/opportunity_decision_freeze/v1'


def _opportunity_decision_freeze_identity(payload: Mapping[str, Any]) -> str:
 body = copy.deepcopy(dict(payload)); body.pop('snapshot_id', None)
 return 'prospective_research_snapshot:' + _hash(body)


def freeze_opportunity_decision_context(*, manifest: Mapping[str, Any], opportunity: Mapping[str, Any], decision_queue: Mapping[str, Any], strategy: Mapping[str, Any], source_file_hashes: Mapping[str, str]) -> dict[str, Any]:
 """Freeze a completed session's opportunity, queue, and recorded selection state.

 This is intentionally a new additive snapshot rather than a rewrite of the
 session-operation context.  It permits later attribution to compare the three
 decision layers independently without deriving a human-selection policy from
 any deterministic research or review queue.
 """
 session = opportunity.get('research_session')
 outputs = manifest.get('outputs') or {}
 if manifest.get('contract_version') != 'daily_research_session_operation/v1' or not isinstance(session, str) or not session:
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_SESSION_CONTRACT_INVALID')
 if manifest.get('market_session') != session or decision_queue.get('research_session') != session or strategy.get('session') != session:
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_SESSION_MISMATCH')
 if outputs.get('opportunity_prioritization') != opportunity.get('artifact_identity') or outputs.get('daily_opportunity_decision_queue') != decision_queue.get('artifact_identity') or outputs.get('strategy_classification') != strategy.get('artifact_identity'):
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_MANIFEST_LINEAGE_MISMATCH')
 if decision_queue.get('source_artifact_identities', {}).get('opportunity') != opportunity.get('artifact_identity'):
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_QUEUE_LINEAGE_MISMATCH')
 if opportunity.get('contract_version') != 'current_opportunity_prioritization/v1' or decision_queue.get('contract_version') != 'daily_opportunity_decision_queue/v1' or strategy.get('contract_version') != 'polymorphic_current_strategy_classification/v1':
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_SOURCE_CONTRACT_MISMATCH')
 if set(source_file_hashes) != {'run_manifest.json', 'ai_research_session_bundle.json', 'opportunity_prioritization_artifact.json', 'daily_opportunity_decision_queue_artifact.json', 'strategy_classification_artifact.json'} or any(not isinstance(value, str) or len(value) != 64 for value in source_file_hashes.values()):
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_SOURCE_HASH_BINDING_INVALID')
 opportunity_records, queue_records, strategy_records = opportunity.get('records') or {}, decision_queue.get('records') or {}, strategy.get('records') or {}
 if not opportunity_records or set(opportunity_records) != set(queue_records) or not set(opportunity_records).issubset(strategy_records):
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_COHORT_MISMATCH')
 if opportunity.get('coverage', {}).get('current_official_universe') != len(opportunity_records):
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_DENOMINATOR_MISMATCH')
 opportunity_rows, queue_rows = [], []
 for ticker in sorted(opportunity_records):
  opportunity_row, queue_row, strategy_row = opportunity_records[ticker], queue_records[ticker], strategy_records[ticker]
  if opportunity_row.get('priority_tier') != queue_row.get('research_priority_tier'):
   raise ValueError('OPPORTUNITY_DECISION_FREEZE_PRIORITY_MISMATCH:' + ticker)
  if list(opportunity_row.get('eligible_strategies') or []) != list(strategy_row.get('eligible_strategy_ids') or []):
   raise ValueError('OPPORTUNITY_DECISION_FREEZE_STRATEGY_MEMBERSHIP_MISMATCH:' + ticker)
  opportunity_rows.append({
   'ticker': ticker,
   'governed_universe_status': opportunity_row.get('official_current_universe_status'),
   'research_priority_tier': opportunity_row.get('priority_tier'),
   'eligible_strategy_ids': list(opportunity_row.get('eligible_strategies') or []),
   'lane_specific_priority': copy.deepcopy(opportunity_row.get('lane_priority') or {}),
   'strategy_record_state': strategy_row.get('record_strategy_state'),
   'strategy_record_identity': strategy_row.get('strategy_record_id'),
   'opportunity_record_identity': opportunity_row.get('content_identity'),
   'source_input_identities': copy.deepcopy(opportunity_row.get('source_input_identities') or {}),
   'eligibility_and_blockers': {'blocking_reasons': list(opportunity_row.get('blocking_reasons') or []), 'data_quality_status': opportunity_row.get('data_quality_status'), 'scenario_status': opportunity_row.get('scenario_status'), 'event_context_status': opportunity_row.get('event_context_status'), 'fundamental_context_status': opportunity_row.get('fundamental_context_status'), 'invalidation_or_context_warnings': list(opportunity_row.get('invalidation_or_context_warnings') or []), 'is_actionable': opportunity_row.get('is_actionable'), 'position_sizing_status': opportunity_row.get('position_sizing_status'), 'is_full_position_ready': opportunity_row.get('is_full_position_ready')},
  })
  queue_rows.append({
   'ticker': ticker,
   'research_priority_tier': queue_row.get('research_priority_tier'),
   'entry_relevant': queue_row.get('entry_relevant'),
   'entry_action': queue_row.get('entry_action'),
   'tactical_state': queue_row.get('tactical_state'),
   'scenario_status': queue_row.get('scenario_status'),
   'eligible_strategy_ids': list(queue_row.get('eligible_strategies') or []),
   'lane_specific_priority': copy.deepcopy(queue_row.get('lane_specific_priority') or {}),
   'queue_record_identity': queue_row.get('content_identity'),
   'opportunity_record_identity': queue_row.get('opportunity_record_content_identity'),
   'source_input_identities': copy.deepcopy(queue_row.get('source_input_identities') or {}),
   'action_and_eligibility_warnings': {'authority_note': queue_row.get('authority_note'), 'blocking_reasons': list(queue_row.get('blocking_reasons') or []), 'invalidation_or_context_warnings': list(queue_row.get('invalidation_or_context_warnings') or []), 'is_actionable': queue_row.get('is_actionable')},
  })
 payload = {
  'schema_version': '1.0.0', 'contract_version': OPPORTUNITY_DECISION_FREEZE_CONTRACT,
  'research_session': session,
  'governed_session': {'operation_identity': manifest.get('operation_identity'), 'generation_commit': manifest.get('producer_head'), 'source_file_sha256': dict(sorted(source_file_hashes.items()))},
  'layers': {
   'opportunity_signal_state': {'record_count': len(opportunity_rows), 'governed_universe': {'denominator_semantics': 'current_official_universe', 'coverage': copy.deepcopy(opportunity.get('coverage') or {})}, 'source_artifact_identities': {'opportunity': opportunity.get('artifact_identity'), 'strategy_classification': strategy.get('artifact_identity'), **copy.deepcopy(opportunity.get('source_artifact_identities') or {})}, 'lane_coverage': copy.deepcopy(opportunity.get('lane_coverage') or {}), 'authority_boundary': copy.deepcopy(opportunity.get('authority_boundary')), 'records': opportunity_rows},
   'daily_decision_queue': {'record_count': len(queue_rows), 'artifact_identity': decision_queue.get('artifact_identity'), 'artifact_sha256': decision_queue.get('artifact_sha256'), 'source_artifact_identities': copy.deepcopy(decision_queue.get('source_artifact_identities') or {}), 'entry_relevant_summary': copy.deepcopy(decision_queue.get('entry_relevant_summary') or {}), 'full_priority_now': list(decision_queue.get('full_priority_now') or []), 'lane_queues': copy.deepcopy(decision_queue.get('lane_queues') or {}), 'multi_strategy': copy.deepcopy(decision_queue.get('multi_strategy') or {}), 'legacy_comparison': copy.deepcopy(decision_queue.get('legacy_comparison') or {}), 'deterministic_review_queue': copy.deepcopy(decision_queue.get('primary_review_candidates') or {}), 'authority_boundary': copy.deepcopy(decision_queue.get('authority_boundary') or {}), 'records': queue_rows},
   'human_review_selection': {'status': 'ABSENT_NOT_RECORDED', 'selection_count': 0, 'selection_tickers': [], 'provenance': {'reason': 'NO_EXPLICIT_FINAL_HUMAN_SELECTION_ARTIFACT_OR_STATE_RECORDED_FOR_GOVERNED_SESSION', 'checked_governed_sources': ['run_manifest.json', 'ai_research_session_bundle.json', 'daily_opportunity_decision_queue_artifact.json'], 'operation_identity': manifest.get('operation_identity')}, 'semantic_boundary': 'NOT_INFERRED_FROM_FULL_PRIORITY_NOW_ENTRY_RELEVANT_DETERMINISTIC_REVIEW_QUEUE_OR_STRATEGY_LANE_QUEUE'},
  },
  'future_outcomes': 'PENDING_FUTURE_OBSERVATION',
  'authority_boundaries': ['OPPORTUNITY_SIGNAL_STATE_SEPARATE_FROM_DAILY_DECISION_QUEUE', 'DAILY_RESEARCH_PRIORITY_NOT_ENTRY_ACTION_NOT_SIZING_AUTHORITY', 'HUMAN_SELECTION_SEPARATE_AND_NOT_INFERRED', 'NOT_OUTCOME_NOT_BACKTEST_NOT_PREDICTIVE_NOT_RECOMMENDATION_NOT_SIZING_NOT_EXECUTION'],
 }
 payload['snapshot_id'] = _opportunity_decision_freeze_identity(payload)
 return payload


def replay_opportunity_decision_context(snapshot: Mapping[str, Any]) -> None:
 if snapshot.get('contract_version') != OPPORTUNITY_DECISION_FREEZE_CONTRACT or snapshot.get('snapshot_id') != _opportunity_decision_freeze_identity(snapshot):
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_IDENTITY_MISMATCH')
 layers = snapshot.get('layers') or {}
 opportunity, queue, human = layers.get('opportunity_signal_state') or {}, layers.get('daily_decision_queue') or {}, layers.get('human_review_selection') or {}
 if opportunity.get('record_count') != len(opportunity.get('records') or []) or queue.get('record_count') != len(queue.get('records') or []) or opportunity.get('record_count') != queue.get('record_count'):
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_RECORD_COUNT_MISMATCH')
 if human.get('status') != 'ABSENT_NOT_RECORDED' or human.get('selection_count') != 0 or human.get('selection_tickers') != []:
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_HUMAN_SELECTION_SEMANTICS_INVALID')
 if any('outcome' in key.lower() or key.lower() in {'future_price', 'realized_return', 'hit_rate', 'calibration'} for row in list(opportunity.get('records') or []) + list(queue.get('records') or []) for key in row):
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_HINDSIGHT_FIELD_PRESENT')
def freeze(product:Mapping[str,Any], analyst:Mapping[str,Any])->dict[str,Any]:
 records={x['ticker']:x for x in product['stock_research']}; briefs={x['ticker']:x for x in analyst['stock_briefs']}; frozen=[]
 for ticker in sorted(records):
  r=records[ticker];f=r['ai_ready_brief']['facts'];frozen.append({'ticker':ticker,'attention_descriptors':r['research_summary']['attention_descriptors'],'queue_member':any(x['ticker']==ticker for x in analyst['research_queue']),'market_technical_state':{'trend_state':r['research_summary']['trend_state'],'momentum_20d':f['momentum_20d'],'volatility_20d':f['volatility_20d'],'relative_volume_provider_scoped':f['relative_volume_provider_scoped']},'fundamental_authority':r['research_summary']['fundamental_authority'],'warnings':r['warnings'],'ai_brief_hash':_hash(briefs[ticker]) if ticker in briefs else None})
 a={'schema_version':'1.0.0','contract_version':'prospective_research_learning/v1','authority':'PROSPECTIVE_RESEARCH_LEARNING_NOT_HISTORICAL_PIT_BACKTEST','research_session':product['daily_market_research']['session'],'source_artifact_identities':{'daily_product':product['artifact_identity'],'analyst':analyst['artifact_identity']},'frozen_records':frozen,'cohort_count':len(frozen),'queue_count':sum(x['queue_member'] for x in frozen),'future_outcomes':'PENDING_FUTURE_OBSERVATION'};a['snapshot_id']='prospective_research_snapshot:'+_hash(a);return a

def freeze_current_decision_surface(tactical: Mapping[str,Any], triage: Mapping[str,Any], fundamental: Mapping[str,Any], valuation: Mapping[str,Any]) -> dict[str,Any]:
 """Seal additive current-decision descriptors; never overwrite an older snapshot."""
 session=str(tactical.get('session') or '')
 if not session or triage.get('source_market_session') != session or valuation.get('valuation_session') != session:
  raise ValueError('CURRENT_DECISION_SURFACE_SESSION_MISMATCH')
 triage_rows={r['ticker']:r for rows in (triage.get('all_entry_relevant_records') or {}).values() for r in rows}
 fund=fundamental.get('records') or {}; val=valuation.get('records') or {}; rows=[]
 for ticker,t in sorted((tactical.get('records') or {}).items()):
  tr=triage_rows.get(ticker,{}); f=fund.get(ticker,{}); v=val.get(ticker,{})
  trajectory=(f.get('fundamental_trajectory_context') or tr.get('fundamental_trajectory_context') or {})
  shadow=(v.get('shadow_proxy_valuation') or {}); shadow_metrics=shadow.get('metrics') or {}
  dimensions={'tactical':{'ticker_structure_state':t.get('ticker_structure_state'),'entry_state':t.get('entry_state'),'entry_action':t.get('entry_action'),'confirmation_trigger_identity':_hash(t.get('confirmation_trigger')) if t.get('confirmation_trigger') else None,'invalidation_identity':_hash(t.get('invalidation')) if t.get('invalidation') else None,'data_quality':t.get('data_quality')},
   'relative_context':{'market_relative_bucket':(tr.get('market_relative_context') or {}).get('momentum_bucket'),'sector_relative_bucket':(tr.get('sector_relative_context') or {}).get('momentum_bucket'),'provider_relative_volume_bucket':(tr.get('current_return_volume_evidence') or {}).get('relative_volume_bucket'),'volatility_regime':(tr.get('current_return_volume_evidence') or {}).get('volatility_regime_vs_market_median')},
   'fundamental':{'entity_class':f.get('entity_class') or tr.get('entity_class'),'authority_tier':f.get('authority_tier') or tr.get('fundamental_authority_tier'),'revenue_direction':trajectory.get('revenue_direction'),'earnings_direction':trajectory.get('earnings_direction'),'revenue_vs_earnings_alignment':trajectory.get('revenue_vs_earnings_alignment'),'assets_direction':trajectory.get('assets_direction'),'equity_direction':trajectory.get('equity_direction'),'operating_cash_flow_direction':trajectory.get('operating_cash_flow_direction'),'trajectory_status':trajectory.get('trajectory_status') or ('AVAILABLE' if trajectory else 'UNAVAILABLE'),'limitations':trajectory.get('data_limitations') or tr.get('fundamental_limitations') or []},
   'valuation':{'authoritative_current_valuation_available':any(x.get('status')=='READY' for x in (v.get('metrics') or {}).values()),'shadow_proxy_valuation_available':any(x.get('status')=='SHADOW_PROXY_READY' for x in shadow_metrics.values()),'proxy_share_status':(shadow.get('source_observation') or {}).get('status'),'proxy_share_freshness':(shadow.get('source_observation') or {}).get('freshness_state'),'available_proxy_metric_ids':sorted(k for k,x in shadow_metrics.items() if x.get('status')=='SHADOW_PROXY_READY')}}
  rows.append({'ticker':ticker,'research_session':session,'decision_surface':dimensions,'tactical_record_identity':_hash(t),'fundamental_record_identity':f.get('ticker') and _hash(f),'valuation_record_identity':v.get('content_identity')})
 payload={'schema_version':'2.0.0','contract_version':'prospective_research_learning/current_decision_surface/v1','authority':'PROSPECTIVE_RESEARCH_NOT_BACKTEST_NOT_PREDICTIVE','research_session':session,'source_artifact_identities':{'tactical':tactical.get('artifact_identity'),'triage':triage.get('artifact_identity'),'fundamental':fundamental.get('artifact_identity'),'valuation':valuation.get('artifact_identity')},'frozen_records':rows,'cohort_count':len(rows),'future_outcomes':'PENDING_FUTURE_OBSERVATION','authority_boundaries':['NOT_RECOMMENDATION_AUTHORITY','NOT_POSITION_SIZING_AUTHORITY','SHADOW_VALUATION_NON_AUTHORITATIVE']}
 payload['snapshot_id']='prospective_research_snapshot:'+_hash(payload);return payload
def write_immutable(path:Path,snapshot:Mapping[str,Any])->None:
 payload=_canon(snapshot)+'\n'
 if path.exists() and path.read_text(encoding='utf-8')!=payload:raise ValueError('IMMUTABLE_SNAPSHOT_CONTENT_CONFLICT')
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(payload,encoding='utf-8')
def attribute(snapshot:Mapping[str,Any],later:Mapping[str,Any]|None=None)->dict[str,Any]:
 # No row from a later session is consulted unless it is strictly later than the frozen session.
 if not later or str(later.get('session',''))<=str(snapshot['research_session']):return {'snapshot_id':snapshot['snapshot_id'],'outcome_status':'PENDING_FUTURE_OBSERVATION','eligible_count':len(snapshot['frozen_records']),'attribution_groups':[]}
 return {'snapshot_id':snapshot['snapshot_id'],'outcome_status':'UNAVAILABLE','eligible_count':len(snapshot['frozen_records']),'attribution_groups':[]}

def context_extension_dimensions(snapshot:Mapping[str,Any], extension:Mapping[str,Any])->dict[str,Any]:
 """Prepare frozen grouping dimensions for a later strict-future attribution run."""
 if extension.get('original_snapshot_identity') != snapshot.get('snapshot_id') or extension.get('research_session') != snapshot.get('research_session'):
  raise ValueError('PROSPECTIVE_CONTEXT_EXTENSION_SNAPSHOT_MISMATCH')
 if extension.get('extension_content_identity') != ATTRIBUTION_SAFE_SUCCESSOR_ID or extension.get('attribution_eligibility') != 'SAFE_SUCCESSOR_FOR_FIRST_ATTRIBUTION' or extension.get('predecessor_extension_identity') != SUPERSEDED_LEGACY_EXTENSION_ID or extension.get('supersession',{}).get('status') != 'SUPERSEDED_FOR_FUTURE_ATTRIBUTION':raise ValueError('PROSPECTIVE_CONTEXT_EXTENSION_NOT_ATTRIBUTION_SAFE')
 if extension.get('seal',{}).get('future_outcomes') != 'PENDING_FUTURE_OBSERVATION':raise ValueError('PROSPECTIVE_CONTEXT_EXTENSION_NOT_PRE_OUTCOME')
 frozen={row['ticker'] for row in snapshot['frozen_records']}; rows={row['ticker']:row for row in extension.get('records',[])}
 if frozen != set(rows):raise ValueError('PROSPECTIVE_CONTEXT_EXTENSION_COHORT_MISMATCH')
 if any(row.get('research_session') != snapshot.get('research_session') for row in rows.values()):raise ValueError('PROSPECTIVE_CONTEXT_EXTENSION_SESSION_MISMATCH')
 return {'snapshot_id':snapshot['snapshot_id'],'extension_content_identity':extension['extension_content_identity'],'research_session':snapshot['research_session'],'outcome_status':'PENDING_FUTURE_OBSERVATION','dimensions':[{'ticker':ticker,'cohort_keys':rows[ticker]['prospective_cohort_keys'],'setup_identity':rows[ticker]['setup']['source_identity'],'market_context_reference':rows[ticker]['market_context_reference']} for ticker in sorted(rows)]}

def _identity_is_valid(payload: Mapping[str, Any], field: str, prefix: str) -> bool:
    body = dict(payload); actual = body.pop(field, None)
    return actual == prefix + _hash(body)

def _outcome_summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    observed = [row for row in rows if row['outcome_status'] == 'OBSERVED_EXACT_FUTURE_SESSION']
    returns = [row['observed_return'] for row in observed]
    return {
        'frozen_cohort_size': len(rows),
        'observed_future_coverage': len(observed),
        'missing_future_observations': len(rows) - len(observed),
        'positive': sum(row.get('direction') == 'POSITIVE' for row in observed),
        'negative': sum(row.get('direction') == 'NEGATIVE' for row in observed),
        'unchanged': sum(row.get('direction') == 'UNCHANGED' for row in observed),
        'mean_observed_return': sum(returns) / len(returns) if returns else None,
        'median_observed_return': statistics.median(returns) if returns else None,
    }

def _group_summaries(rows: list[Mapping[str, Any]], groups: Mapping[str, set[str]]) -> list[dict[str, Any]]:
    return [dict({'group': name}, **_outcome_summary([row for row in rows if row['ticker'] in members]))
            for name, members in sorted(groups.items())]

def _session_observation(record: Mapping[str, Any] | None, session: str, required_disposition: bool) -> Mapping[str, Any] | None:
    if not record or (required_disposition and record.get('disposition') != 'EXACT_SESSION_RETAINED'):
        return None
    matches = [item for item in record.get('observations', []) if item.get('session') == session]
    return matches[0] if len(matches) == 1 and isinstance(matches[0].get('close'), (int, float)) else None

def first_real_observation(snapshot: Mapping[str, Any], extension: Mapping[str, Any],
                           t_exact_snapshot: Mapping[str, Any], future_scaleout: Mapping[str, Any],
                           future_exact_snapshot: Mapping[str, Any], future_bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Join the frozen cohort to a retained, exact, strictly later close only.

    This intentionally has no fallback to a refreshed cohort, an older bar, or an
    intraday observation.  It is descriptive prospective learning, not a backtest.
    """
    dimensions = context_extension_dimensions(snapshot, extension)
    if not _identity_is_valid(snapshot, 'snapshot_id', 'prospective_research_snapshot:'):
        raise ValueError('FROZEN_SNAPSHOT_IDENTITY_INVALID')
    if not _identity_is_valid(extension, 'extension_content_identity', 'prospective_research_context_extension:'):
        raise ValueError('CORRECTED_EXTENSION_IDENTITY_INVALID')
    future_session = future_scaleout.get('resolved_session', {}).get('resolved_completed_session')
    if not isinstance(future_session, str) or future_session <= snapshot['research_session']:
        raise ValueError('FUTURE_SESSION_NOT_STRICTLY_LATER')
    required_future = {
        'artifact_identity': 'p3f9b_market_wide_exact_session_scaleout:1c0f9600e9a3143efea5794add12d17cacb227bc1a4764402dc9ac90cf2a0421',
        'snapshot_identity': 'p3f9_exact_session_snapshot:477eabbdfa3c304b6e7b0c208eba56f315cf99b7517013c64342e561069a1614',
    }
    if any(future_scaleout.get(key) != value for key, value in required_future.items()):
        raise ValueError('FUTURE_RETAINED_SOURCE_IDENTITY_MISMATCH')
    resolved = future_scaleout.get('resolved_session', {})
    if (resolved.get('retained_snapshot_session') != future_session or
        resolved.get('exact_session_equality') is not True or
        resolved.get('incomplete_intraday_used') is not False or
        future_scaleout.get('exact_session_dispositions', {}).get('exact_session_retained_count') != 960 or
        future_exact_snapshot.get('snapshot_identity') != future_scaleout.get('snapshot_identity') or
        future_exact_snapshot.get('resolved_completed_session') != future_session or
        future_exact_snapshot.get('retained_snapshot_session') != future_session):
        raise ValueError('FUTURE_EXACT_SESSION_PRECONDITION_NOT_MET')
    t_session = snapshot['research_session']
    frozen = {row['ticker']: row for row in snapshot['frozen_records']}
    if len(frozen) != snapshot.get('cohort_count') or len(frozen) != 523:
        raise ValueError('FROZEN_COHORT_INVALID')
    extension_rows = {row['ticker']: row for row in extension['records']}
    if set(frozen) != set(extension_rows):
        raise ValueError('FROZEN_EXTENSION_COHORT_MISMATCH')
    future_members = set(future_bundle.get('empirical_active_cohort', {}).get('members', []))
    if (future_scaleout.get('empirical_active_cohort', {}).get('member_count') != 524 or
        len(future_members) != 524):
        raise ValueError('FUTURE_EMPIRICAL_COHORT_NOT_EXPECTED')
    rows = []
    for ticker in sorted(frozen):
        t_obs = _session_observation(t_exact_snapshot.get('records', {}).get(ticker), t_session, True)
        future_record = future_exact_snapshot.get('records', {}).get(ticker)
        future_obs = _session_observation(future_record, future_session, True)
        base = {
            'ticker': ticker, 't_session': t_session, 'future_session': future_session,
            'frozen_source_identity': t_exact_snapshot.get('snapshot_identity'),
            'future_source_identity': future_exact_snapshot.get('snapshot_identity'),
            'frozen_context_record_identity': extension_rows[ticker].get('context_record_content_identity'),
            'frozen_cohort_keys': extension_rows[ticker]['prospective_cohort_keys'],
            'attention_descriptors': frozen[ticker]['attention_descriptors'],
            'queue_member': frozen[ticker]['queue_member'],
            'evidence_authority': frozen[ticker]['fundamental_authority'],
            'future_empirical_cohort_member': ticker in future_members,
        }
        if not t_obs:
            base.update({'outcome_status': 'MISSING_FUTURE_OBSERVATION', 'missing_state_reason': 'MISSING_FROZEN_EXACT_T_OBSERVATION'})
        elif not future_obs:
            base.update({'outcome_status': 'MISSING_FUTURE_OBSERVATION', 't_close': t_obs['close'],
                         'missing_state_reason': 'FUTURE_' + str((future_record or {}).get('disposition', 'RECORD_MISSING'))})
        else:
            change = future_obs['close'] - t_obs['close']; observed_return = change / t_obs['close']
            direction = 'POSITIVE' if change > 0 else 'NEGATIVE' if change < 0 else 'UNCHANGED'
            future_features = next((row.get('market_features', {}) for row in future_bundle.get('records', [])
                                    if row.get('identity', {}).get('canonical_ticker') == ticker), None)
            base.update({'outcome_status': 'OBSERVED_EXACT_FUTURE_SESSION', 't_close': t_obs['close'],
                         'future_close': future_obs['close'], 'observed_price_change': change,
                         'observed_return': observed_return, 'direction': direction,
                         't_observation_identity': 'exact_session_observation:' + _hash(t_obs),
                         'future_observation_identity': 'exact_session_observation:' + _hash(future_obs),
                         'future_deterministic_technical_state': future_features,
                         'thesis_continuity': 'UNRESOLVED'})
        rows.append(base)
    if any(row['ticker'] not in frozen for row in rows) or len(rows) != 523:
        raise ValueError('FUTURE_COHORT_LEAKAGE')
    group_keys: dict[str, set[str]] = {}
    for row in rows:
        for key in row['frozen_cohort_keys']:
            group_keys.setdefault(key, set()).add(row['ticker'])
        for descriptor in row['attention_descriptors']:
            group_keys.setdefault('attention:' + descriptor, set()).add(row['ticker'])
        group_keys.setdefault('queue:FROZEN_25_NAME_QUEUE' if row['queue_member'] else 'queue:FROZEN_NON_QUEUE', set()).add(row['ticker'])
    setup_groups = {key: members for key, members in group_keys.items() if key.startswith('setup:')}
    no_setup = {row['ticker'] for row in rows if not any(key.startswith('setup:') for key in row['frozen_cohort_keys'])}
    setup_groups['setup:NO_DISTINCT_SETUP'] = no_setup
    report = {
        'schema_version': '1.0.0', 'contract_version': 'first_real_prospective_attribution/v1',
        'authority': 'FIRST_PROSPECTIVE_OBSERVATION_DESCRIPTIVE_ONLY_NOT_HISTORICAL_PIT_BACKTEST',
        'disposition': 'FIRST_REAL_PROSPECTIVE_ATTRIBUTION_COMPLETE',
        'precondition': {'t_session': t_session, 'future_session': future_session,
                         'future_is_strictly_later': True, 'future_scaleout_identity': future_scaleout['artifact_identity'],
                         'future_snapshot_identity': future_exact_snapshot['snapshot_identity'],
                         'corrected_extension_identity': extension['extension_content_identity'],
                         'superseded_extension_rejected': True},
        'cohort_reconciliation': {'frozen_t_cohort_size': 523, 'future_refreshed_empirical_cohort_size': 524,
                                  'future_only_members_not_added_to_t': sorted(future_members - set(frozen)),
                                  'frozen_members_not_in_refreshed_future_cohort': sorted(set(frozen) - future_members),
                                  'attributed_tickers': [row['ticker'] for row in rows]},
        'overall': _outcome_summary(rows), 'setup_attribution': _group_summaries(rows, setup_groups),
        'queue_attribution': _group_summaries(rows, {key: members for key, members in group_keys.items() if key.startswith('queue:')}),
        'downside_and_structure_attribution': _group_summaries(rows, {key: members for key, members in group_keys.items() if key.startswith(('downside:', 'price_structure:'))}),
        'market_and_relative_context': _group_summaries(rows, {key: members for key, members in group_keys.items() if key.startswith(('market:', 'relative_authority:'))}),
        'evidence_state_attribution': _group_summaries(rows, {key: members for key, members in group_keys.items() if key.startswith('authority:')}),
        'attention_attribution': _group_summaries(rows, {key: members for key, members in group_keys.items() if key.startswith('attention:')}),
        'thesis_continuity': _group_summaries(rows, {'thesis:UNRESOLVED': {row['ticker'] for row in rows}}),
        'temporal_safety': {'no_future_values_in_frozen_t_fields': True, 'ticker_session_cross_leakage': False,
                            'missing_observations_remain_missing': True, 'frozen_cohort_not_replaced': True,
                            'historical_raw_as_traded_or_pit_promoted': False}, 'outcomes': rows,
    }
    report['artifact_identity'] = 'first_real_prospective_attribution:' + _hash(report)
    return report
