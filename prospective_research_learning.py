"""Immutable prospective research snapshots and later exact-session attribution.

This is shadow prospective learning, never historical PIT backtesting.
"""
from __future__ import annotations
import copy,hashlib,json
import statistics
from datetime import date
from pathlib import Path
from typing import Any,Mapping
from field_temporal_contract import stable_id
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


PROSPECTIVE_RESEARCH_COHORT_SNAPSHOT_CONTRACT = 'prospective_research_learning/cohort_snapshot/v1'
ENTRY_RELEVANT_COHORT_STATES = ('BASE_BUILDING', 'BREAKOUT_READY', 'EARLY_REVERSAL_CANDIDATE')
_COHORT_ROW_KEYS = {
    'ticker', 'research_session', 'triage_state', 'cohort_admission', 'current_decision_context',
    'components', 'unresolved_components', 'authority_limitations', 'decision_packet_status',
    'decision_packet_identity',
}
# Exact dict-key match only -- never a substring scan over free-text values, which routinely
# *describe* these same words while disclaiming them (e.g. "No ... recommendation, sizing ...").
_COHORT_FORBIDDEN_CONTEXT_KEYS = {
    'recommendation', 'probability', 'expected_return', 'target_price', 'position_size', 'sizing',
    'realized_return', 'future_price', 'hit_rate', 'win_rate', 'score', 'calibration',
}


def resolve_entry_relevant_cohort(triage: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Deterministically derive the prospective-collection cohort from one triage artifact.

    This is the full BASE_BUILDING + BREAKOUT_READY + EARLY_REVERSAL_CANDIDATE membership --
    never narrowed to the high-priority review subset, which is retained only as descriptive
    per-ticker metadata so high-priority never doubles as the admission rule.
    """
    buckets = triage.get('all_entry_relevant_records') or {}
    cohort: dict[str, dict[str, Any]] = {}
    for state in ENTRY_RELEVANT_COHORT_STATES:
        for row in buckets.get(state) or []:
            ticker = row['ticker']
            if ticker in cohort:
                raise ValueError('PROSPECTIVE_COHORT_TICKER_IN_MULTIPLE_TRIAGE_STATES:' + ticker)
            cohort[ticker] = {
                'admission_state': state,
                'admission_reason': 'FULL_UNIVERSE_ENTRY_CANDIDATE_TRIAGE_ENTRY_RELEVANT_STATE',
                'high_priority_review_eligible': bool(row.get('high_priority_review_eligible')),
            }
    return cohort


def _cohort_component_view(ticker: str, packet_records: Mapping[str, Any]) -> dict[str, Any]:
    """Return a per-ticker decision-packet view that never raises.

    A single malformed or absent packet record degrades only that ticker's row to an
    explicit UNAVAILABLE/MALFORMED state; it never aborts the rest of the cohort snapshot.
    """
    packet_row = packet_records.get(ticker)
    if packet_row is None:
        return {'decision_context': {}, 'components': {}, 'unresolved_components': [],
                'authority_limitations': ['DECISION_PACKET_HAS_NO_RECORD_FOR_TICKER'],
                'decision_packet_status': 'UNAVAILABLE_NOT_IN_PACKET'}
    try:
        decision_context = copy.deepcopy(packet_row['current_decision_context'])
        components = copy.deepcopy(packet_row['components'])
        unresolved = [str(x) for x in packet_row['unresolved_components']]
        limitations = [str(x) for x in packet_row['authority_limitations']]
        status = packet_row['packet_status']
        if not isinstance(decision_context, Mapping) or not isinstance(components, Mapping) or not isinstance(status, str):
            raise TypeError('MALFORMED_PACKET_ROW_SHAPE')
    except (KeyError, TypeError):
        return {'decision_context': {}, 'components': {}, 'unresolved_components': [],
                'authority_limitations': ['DECISION_PACKET_ROW_MALFORMED_FOR_TICKER'],
                'decision_packet_status': 'MALFORMED'}
    return {'decision_context': decision_context, 'components': components,
            'unresolved_components': sorted(unresolved), 'authority_limitations': limitations,
            'decision_packet_status': status}


def freeze_prospective_research_cohort(*, session: str, triage: Mapping[str, Any],
                                       decision_packet: Mapping[str, Any] | None = None,
                                       registered_source_identities: Mapping[str, str] = {},
                                       full_universe_prospective_snapshot_id: str | None = None) -> dict[str, Any]:
    """Freeze an explicit-cohort, richer sibling to freeze_current_decision_surface.

    Scoped to the deterministic entry-relevant triage cohort (currently ~95 tickers, not the
    2-5 name pilots this program started with) rather than the full official universe. Where a
    same-session current_research_decision_packet is supplied and self-verifies, each row also
    retains its scenario/risk/financial/event/valuation/historical component identities and
    limitations; when it is not supplied (or one row is malformed), that record degrades to an
    explicit unavailable/malformed state rather than blocking the batch. This is additive: it
    never replaces or narrows freeze_current_decision_surface's full-universe lightweight freeze,
    which remains the broader observational layer and may be cross-linked by identity only.
    """
    if not isinstance(session, str) or not session or triage.get('source_market_session') != session:
        raise ValueError('PROSPECTIVE_COHORT_SNAPSHOT_SESSION_MISMATCH')
    cohort = resolve_entry_relevant_cohort(triage)
    if not cohort:
        raise ValueError('PROSPECTIVE_COHORT_SNAPSHOT_EMPTY_COHORT')
    packet_records: Mapping[str, Any] = {}
    packet_identity = None
    if decision_packet is not None:
        from current_research_decision_packet import replay as _replay_packet
        if decision_packet.get('research_session') != session:
            raise ValueError('PROSPECTIVE_COHORT_SNAPSHOT_DECISION_PACKET_INVALID_OR_SESSION_MISMATCH')
        _replay_packet(decision_packet)  # reuses the packet's own identity/coverage/forbidden-field gate
        packet_records = decision_packet.get('records') or {}
        packet_identity = decision_packet.get('artifact_identity')
    rows = []
    for ticker in sorted(cohort):
        admission = cohort[ticker]
        view = _cohort_component_view(ticker, packet_records)
        rows.append({
            'ticker': ticker, 'research_session': session, 'triage_state': admission['admission_state'],
            'cohort_admission': admission, 'current_decision_context': view['decision_context'],
            'components': view['components'], 'unresolved_components': view['unresolved_components'],
            'authority_limitations': view['authority_limitations'],
            'decision_packet_status': view['decision_packet_status'],
            'decision_packet_identity': packet_identity if view['decision_packet_status'] not in ('UNAVAILABLE_NOT_IN_PACKET',) else None,
        })
    payload = {
        'schema_version': '1.0.0', 'contract_version': PROSPECTIVE_RESEARCH_COHORT_SNAPSHOT_CONTRACT,
        'authority': 'PROSPECTIVE_RESEARCH_NOT_BACKTEST_NOT_PREDICTIVE', 'research_session': session,
        'cohort_definition': {'source': 'full_universe_entry_candidate_triage/v1',
                              'admission_states': list(ENTRY_RELEVANT_COHORT_STATES),
                              'admission_rule': 'MEMBERSHIP_IN_ANY_ENTRY_RELEVANT_STATE_NOT_HIGH_PRIORITY_SUBSET'},
        'source_artifact_identities': {'triage': triage.get('artifact_identity'), 'decision_packet': packet_identity,
                                       'full_universe_prospective_snapshot': full_universe_prospective_snapshot_id,
                                       'session_registered_inputs': dict(sorted(registered_source_identities.items()))},
        'frozen_records': rows, 'cohort_count': len(rows),
        'state_counts': {state: sum(1 for r in rows if r['triage_state'] == state) for state in ENTRY_RELEVANT_COHORT_STATES},
        'high_priority_review_eligible_count': sum(1 for r in rows if r['cohort_admission']['high_priority_review_eligible']),
        'decision_packet_coverage': {'available': sum(1 for r in rows if r['decision_packet_status'] not in ('UNAVAILABLE_NOT_IN_PACKET', 'MALFORMED')),
                                     'unavailable_or_malformed': sum(1 for r in rows if r['decision_packet_status'] in ('UNAVAILABLE_NOT_IN_PACKET', 'MALFORMED'))},
        'future_outcomes': 'PENDING_FUTURE_OBSERVATION',
        'authority_boundaries': ['NOT_RECOMMENDATION_AUTHORITY', 'NOT_POSITION_SIZING_AUTHORITY',
                                 'SHADOW_VALUATION_NON_AUTHORITATIVE', 'NOT_HISTORICAL_PIT_BACKTEST',
                                 'NO_SCORING_RANKING_OR_PROBABILITY_CALIBRATION'],
    }
    payload['snapshot_id'] = 'prospective_research_cohort_snapshot:' + _hash(payload)
    return payload


def replay_prospective_research_cohort_snapshot(snapshot: Mapping[str, Any]) -> None:
    body = copy.deepcopy(dict(snapshot)); recorded = body.pop('snapshot_id', None)
    if snapshot.get('contract_version') != PROSPECTIVE_RESEARCH_COHORT_SNAPSHOT_CONTRACT or recorded != 'prospective_research_cohort_snapshot:' + _hash(body):
        raise ValueError('PROSPECTIVE_COHORT_SNAPSHOT_IDENTITY_MISMATCH')
    rows = snapshot.get('frozen_records') or []
    if snapshot.get('cohort_count') != len(rows):
        raise ValueError('PROSPECTIVE_COHORT_SNAPSHOT_COUNT_MISMATCH')
    tickers = [row['ticker'] for row in rows]
    if len(set(tickers)) != len(tickers):
        raise ValueError('PROSPECTIVE_COHORT_SNAPSHOT_DUPLICATE_TICKER')
    if sorted(tickers) != tickers:
        raise ValueError('PROSPECTIVE_COHORT_SNAPSHOT_NOT_SORTED')
    counted = {state: sum(1 for row in rows if row['triage_state'] == state) for state in ENTRY_RELEVANT_COHORT_STATES}
    if snapshot.get('state_counts') != counted:
        raise ValueError('PROSPECTIVE_COHORT_SNAPSHOT_STATE_COUNT_MISMATCH')
    if snapshot.get('future_outcomes') != 'PENDING_FUTURE_OBSERVATION':
        raise ValueError('PROSPECTIVE_COHORT_SNAPSHOT_FUTURE_OUTCOME_NOT_PENDING')
    for row in rows:
        if set(row) != _COHORT_ROW_KEYS:
            raise ValueError('PROSPECTIVE_COHORT_SNAPSHOT_ROW_SCHEMA_MISMATCH:' + str(row.get('ticker')))
        ctx = row['current_decision_context']
        if any(key in ctx for key in _COHORT_FORBIDDEN_CONTEXT_KEYS):
            raise ValueError('PROSPECTIVE_COHORT_SNAPSHOT_HINDSIGHT_OR_SCORING_FIELD_PRESENT:' + str(row.get('ticker')))


PROSPECTIVE_RESEARCH_COHORT_FUTURE_ATTRIBUTION_CONTRACT = 'prospective_research_learning/cohort_future_attribution/v1'
COHORT_FUTURE_ATTRIBUTION_IDENTITY_PREFIX = 'prospective_research_cohort_future_attribution:'
OBSERVED_CHANGE_SEMANTICS = 'PROSPECTIVE_OBSERVED_CLOSE_TO_CLOSE_DESCRIPTIVE'
EXACT_SESSION_SCALEOUT_CONTRACT = 'p3f9b_market_wide_exact_session_scaleout/v1'
ALLOWED_CLOSE_REPRESENTATION = 'DNSE_PROVIDER_NATIVE_RAW'
ALLOWED_TRANSFORMATION_IDENTITY = 'identity_provider_numeric_ohlc/v1'
ALLOWED_PRICE_BASIS = 'CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED'
_ATTRIBUTION_FORBIDDEN_KEYS = frozenset({
    'win_rate', 'hit_rate', 'expected_return', 'probability', 'score', 'recommendation',
    'target_price', 'position_size', 'accuracy', 'edge', 'calibration', 'sizing',
})
_ATTRIBUTION_AUTHORITY_BOUNDARIES = (
    'PROSPECTIVE_DESCRIPTIVE_ATTRIBUTION_ONLY',
    'NOT_HISTORICAL_PIT_BACKTEST',
    'NOT_PREDICTIVE',
    'NOT_CALIBRATED',
    'NOT_RECOMMENDATION',
    'NOT_SIZING',
    'NOT_EXECUTION',
)


def _iso_session(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(label)
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(label) from exc
    return value


def _cohort_future_attribution_identity(payload: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(payload))
    body.pop('artifact_identity', None)
    return COHORT_FUTURE_ATTRIBUTION_IDENTITY_PREFIX + _hash(body)


def _walk_forbidden_keys(obj: Any) -> None:
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            if str(key) in _ATTRIBUTION_FORBIDDEN_KEYS:
                raise ValueError('COHORT_FUTURE_ATTRIBUTION_FORBIDDEN_FIELD:' + str(key))
            _walk_forbidden_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            _walk_forbidden_keys(item)


def _verify_p3f9_scaleout(scaleout: Mapping[str, Any], session: str, label: str) -> None:
    if scaleout.get('contract_version') != EXACT_SESSION_SCALEOUT_CONTRACT:
        raise ValueError(label + '_EXACT_SOURCE_CONTRACT_MISMATCH')
    body = dict(scaleout)
    recorded_id = body.pop('artifact_identity', None)
    recorded_sha = body.pop('artifact_sha256', None)
    digest = stable_id(body)
    if recorded_sha != digest or recorded_id != 'p3f9b_market_wide_exact_session_scaleout:' + digest:
        raise ValueError(label + '_EXACT_SOURCE_IDENTITY_MISMATCH')
    resolved = scaleout.get('resolved_session') or {}
    if (resolved.get('resolved_completed_session') != session or
            resolved.get('retained_snapshot_session') != session or
            resolved.get('mva_bundle_session') not in (session, None) or
            resolved.get('exact_session_equality') is not True or
            resolved.get('incomplete_intraday_used') is not False):
        raise ValueError(label + '_EXACT_SESSION_PRECONDITION_NOT_MET')


def _verify_p3f9_snapshot(snapshot: Mapping[str, Any], scaleout: Mapping[str, Any], session: str, label: str) -> None:
    body = dict(snapshot)
    recorded_id = body.pop('snapshot_identity', None)
    recorded_sha = body.pop('snapshot_sha256', None)
    digest = stable_id(body)
    if recorded_sha != digest or recorded_id != 'p3f9_exact_session_snapshot:' + digest:
        raise ValueError(label + '_EXACT_SOURCE_IDENTITY_MISMATCH')
    if snapshot.get('snapshot_identity') != scaleout.get('snapshot_identity'):
        raise ValueError(label + '_EXACT_SOURCE_IDENTITY_MISMATCH')
    if (snapshot.get('resolved_completed_session') != session or
            snapshot.get('retained_snapshot_session') != session):
        raise ValueError(label + '_EXACT_SESSION_PRECONDITION_NOT_MET')
    authority = snapshot.get('authority_boundary') or {}
    if authority.get('RAW_AS_TRADED') not in ('NOT_PROMOTED', None):
        raise ValueError(label + '_RAW_AS_TRADED_PROMOTION')


def _exact_session_observation(record: Mapping[str, Any] | None, session: str) -> tuple[Mapping[str, Any] | None, str | None]:
    """Return the exact-session bar only. Prior-session lookback rows never substitute."""
    if not isinstance(record, Mapping):
        return None, 'RECORD_MISSING'
    disposition = record.get('disposition')
    if disposition != 'EXACT_SESSION_RETAINED':
        return None, str(disposition or 'RECORD_MISSING')
    matches = [item for item in record.get('observations') or []
               if isinstance(item, Mapping) and item.get('session') == session]
    if len(matches) != 1:
        return None, 'EXACT_SESSION_OBSERVATION_MISSING' if not matches else 'EXACT_SESSION_OBSERVATION_AMBIGUOUS'
    return matches[0], None


def _numeric_close(observation: Mapping[str, Any] | None) -> float | None:
    if not isinstance(observation, Mapping):
        return None
    close = observation.get('close')
    if isinstance(close, bool) or not isinstance(close, (int, float)):
        return None
    value = float(close)
    if value != value or value == 0.0 or value in (float('inf'), float('-inf')):
        return None
    return value


def _representation_view(observation: Mapping[str, Any]) -> dict[str, Any]:
    field_repr = observation.get('field_representation') or {}
    return {
        'close_field_representation': field_repr.get('close'),
        'transformation_identity': observation.get('transformation_identity'),
        'price_basis': observation.get('price_basis'),
        'price_unit': observation.get('price_unit'),
        'qualification': observation.get('qualification'),
    }


def _representation_comparable(t_obs: Mapping[str, Any], future_obs: Mapping[str, Any]) -> bool:
    t_view, future_view = _representation_view(t_obs), _representation_view(future_obs)
    if t_view != future_view:
        return False
    if t_view['close_field_representation'] != ALLOWED_CLOSE_REPRESENTATION:
        return False
    if t_view['transformation_identity'] != ALLOWED_TRANSFORMATION_IDENTITY:
        return False
    if t_view['price_basis'] != ALLOWED_PRICE_BASIS:
        return False
    if t_view['price_basis'] == 'RAW_AS_TRADED' or future_view['price_basis'] == 'RAW_AS_TRADED':
        return False
    return True


def _cohort_attribution_summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    observed = [row for row in rows if row.get('outcome_status') == 'OBSERVED_EXACT_FUTURE_SESSION']
    returns = [row['observed_return'] for row in observed]
    return {
        'frozen_count': len(rows),
        'observed_count': len(observed),
        'missing_count': len(rows) - len(observed),
        'positive': sum(1 for row in observed if row.get('direction') == 'POSITIVE'),
        'negative': sum(1 for row in observed if row.get('direction') == 'NEGATIVE'),
        'unchanged': sum(1 for row in observed if row.get('direction') == 'UNCHANGED'),
        'mean_observed_return': (sum(returns) / len(returns)) if returns else None,
        'median_observed_return': statistics.median(returns) if returns else None,
    }


def _group_attribution_summaries(rows: list[Mapping[str, Any]], key_fn, names: list[str]) -> list[dict[str, Any]]:
    buckets: dict[str, list[Mapping[str, Any]]] = {name: [] for name in names}
    for row in rows:
        buckets.setdefault(key_fn(row), []).append(row)
    return [dict({'group': name}, **_cohort_attribution_summary(buckets.get(name, []))) for name in names]


def _future_descriptive_state(ticker: str, future_triage: Mapping[str, Any] | None,
                              future_tactical: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if future_triage is None and future_tactical is None:
        return None
    triage_state = 'NOT_IN_FUTURE_ENTRY_RELEVANT_COHORT'
    if isinstance(future_triage, Mapping):
        for state, members in (future_triage.get('all_entry_relevant_records') or {}).items():
            for member in members or []:
                if isinstance(member, Mapping) and member.get('ticker') == ticker:
                    triage_state = str(state)
                    break
    tactical_row = {}
    if isinstance(future_tactical, Mapping):
        records = future_tactical.get('records') or {}
        if isinstance(records, Mapping):
            tactical_row = records.get(ticker) or {}
    return {
        'status': 'DESCRIPTIVE_FUTURE_CONTEXT_ONLY',
        'future_triage_state': triage_state,
        'future_tactical_state': tactical_row.get('entry_state') if isinstance(tactical_row, Mapping) else None,
        'future_entry_action': tactical_row.get('entry_action') if isinstance(tactical_row, Mapping) else None,
        'not_outcome_success_or_failure': True,
    }


def attribute_prospective_research_cohort_first_future(
        *, snapshot: Mapping[str, Any], t_exact_snapshot: Mapping[str, Any],
        t_exact_scaleout: Mapping[str, Any], future_exact_snapshot: Mapping[str, Any],
        future_exact_scaleout: Mapping[str, Any], future_session: str,
        future_triage: Mapping[str, Any] | None = None,
        future_tactical: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Descriptive strictly-future join for prospective_research_learning/cohort_snapshot/v1.

    Sibling to first_real_observation(). It does not reuse that function's hard-coded
    523-member identities. Frozen T membership is never refreshed from the future session.
    """
    replay_prospective_research_cohort_snapshot(snapshot)
    t_session = _iso_session(snapshot.get('research_session'), 'COHORT_FUTURE_ATTRIBUTION_T_SESSION_INVALID')
    future_session = _iso_session(future_session, 'COHORT_FUTURE_ATTRIBUTION_FUTURE_SESSION_INVALID')
    if future_session <= t_session:
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_FUTURE_SESSION_NOT_STRICTLY_LATER')
    _verify_p3f9_scaleout(t_exact_scaleout, t_session, 'T')
    _verify_p3f9_snapshot(t_exact_snapshot, t_exact_scaleout, t_session, 'T')
    _verify_p3f9_scaleout(future_exact_scaleout, future_session, 'FUTURE')
    _verify_p3f9_snapshot(future_exact_snapshot, future_exact_scaleout, future_session, 'FUTURE')
    frozen_rows = list(snapshot.get('frozen_records') or [])
    frozen = {row['ticker']: row for row in frozen_rows}
    if len(frozen) != snapshot.get('cohort_count') or len(frozen) != len(frozen_rows):
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_FROZEN_COHORT_INVALID')
    future_members = set(future_exact_snapshot.get('records') or {})
    future_only = sorted(future_members - set(frozen))
    t_records = t_exact_snapshot.get('records') or {}
    future_records = future_exact_snapshot.get('records') or {}
    outcomes = []
    missing_state_counts: dict[str, int] = {}
    for ticker in sorted(frozen):
        frozen_row = frozen[ticker]
        t_obs, t_reason = _exact_session_observation(t_records.get(ticker), t_session)
        future_obs, future_reason = _exact_session_observation(future_records.get(ticker), future_session)
        t_close = _numeric_close(t_obs)
        future_close = _numeric_close(future_obs)
        row = {
            'ticker': ticker,
            't_session': t_session,
            'future_session': future_session,
            'frozen_triage_state': frozen_row.get('triage_state'),
            'frozen_high_priority_review_eligible': bool(
                (frozen_row.get('cohort_admission') or {}).get('high_priority_review_eligible')),
            'frozen_decision_packet_status': frozen_row.get('decision_packet_status'),
            'observed_change_semantics': OBSERVED_CHANGE_SEMANTICS,
        }
        context = _future_descriptive_state(ticker, future_triage, future_tactical)
        if context is not None:
            row['future_descriptive_state'] = context
        if t_obs is None:
            row.update({'outcome_status': 'MISSING_T_EXACT_OBSERVATION',
                        'missing_state_reason': 'T_' + str(t_reason)})
        elif t_close is None:
            row.update({'outcome_status': 'T_CLOSE_INVALID_OR_ZERO',
                        'missing_state_reason': 'T_CLOSE_INVALID_OR_ZERO',
                        't_price_representation': _representation_view(t_obs)})
        elif future_obs is None:
            row.update({'outcome_status': 'MISSING_FUTURE_EXACT_OBSERVATION',
                        'missing_state_reason': 'FUTURE_' + str(future_reason),
                        't_close': t_close,
                        't_price_representation': _representation_view(t_obs),
                        't_observation_identity': 'exact_session_observation:' + _hash(dict(t_obs))})
        elif future_close is None:
            row.update({'outcome_status': 'FUTURE_CLOSE_INVALID',
                        'missing_state_reason': 'FUTURE_CLOSE_INVALID',
                        't_close': t_close,
                        't_price_representation': _representation_view(t_obs),
                        'future_price_representation': _representation_view(future_obs)})
        elif not _representation_comparable(t_obs, future_obs):
            row.update({'outcome_status': 'PRICE_REPRESENTATION_COMPARISON_UNSAFE',
                        'missing_state_reason': 'PRICE_REPRESENTATION_COMPARISON_UNSAFE',
                        't_close': t_close, 'future_close': future_close,
                        't_price_representation': _representation_view(t_obs),
                        'future_price_representation': _representation_view(future_obs)})
        else:
            change = future_close - t_close
            observed_return = (future_close / t_close) - 1.0
            direction = 'POSITIVE' if change > 0 else 'NEGATIVE' if change < 0 else 'UNCHANGED'
            row.update({
                'outcome_status': 'OBSERVED_EXACT_FUTURE_SESSION',
                't_close': t_close, 'future_close': future_close,
                'observed_price_change': change, 'observed_return': observed_return,
                'direction': direction,
                't_price_representation': _representation_view(t_obs),
                'future_price_representation': _representation_view(future_obs),
                't_observation_identity': 'exact_session_observation:' + _hash(dict(t_obs)),
                'future_observation_identity': 'exact_session_observation:' + _hash(dict(future_obs)),
            })
        missing_state_counts[row['outcome_status']] = missing_state_counts.get(row['outcome_status'], 0) + 1
        outcomes.append(row)
    if any(row['ticker'] not in frozen for row in outcomes) or len(outcomes) != len(frozen):
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_FUTURE_COHORT_LEAKAGE')
    overall = _cohort_attribution_summary(outcomes)
    triage_summaries = _group_attribution_summaries(
        outcomes, lambda row: row['frozen_triage_state'], list(ENTRY_RELEVANT_COHORT_STATES))
    if sum(item['frozen_count'] for item in triage_summaries) != overall['frozen_count']:
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_GROUP_COUNT_MISMATCH')
    if overall['observed_count'] + overall['missing_count'] != overall['frozen_count']:
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_COVERAGE_MISMATCH')
    if overall['positive'] + overall['negative'] + overall['unchanged'] != overall['observed_count']:
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_DIRECTION_MISMATCH')
    payload = {
        'schema_version': '1.0.0',
        'contract_version': PROSPECTIVE_RESEARCH_COHORT_FUTURE_ATTRIBUTION_CONTRACT,
        'authority': 'PROSPECTIVE_DESCRIPTIVE_ATTRIBUTION_ONLY',
        'authority_boundaries': list(_ATTRIBUTION_AUTHORITY_BOUNDARIES),
        'authority_effect': 'NONE',
        'frozen_snapshot_identity': snapshot.get('snapshot_id'),
        't_session': t_session,
        'future_session': future_session,
        'future_is_strictly_later': True,
        'horizon': {
            'kind': 'FIRST_STRICTLY_LATER_COMPLETED_SESSION',
            't_session': t_session,
            'future_session': future_session,
            'later_sessions_not_materialized': True,
        },
        'source_artifact_identities': {
            'frozen_cohort_snapshot': snapshot.get('snapshot_id'),
            't_exact_session_snapshot': t_exact_snapshot.get('snapshot_identity'),
            't_exact_session_scaleout': t_exact_scaleout.get('artifact_identity'),
            'future_exact_session_snapshot': future_exact_snapshot.get('snapshot_identity'),
            'future_exact_session_scaleout': future_exact_scaleout.get('artifact_identity'),
            'future_triage': None if future_triage is None else future_triage.get('artifact_identity'),
            'future_tactical': None if future_tactical is None else future_tactical.get('artifact_identity'),
        },
        'frozen_cohort_definition': copy.deepcopy(snapshot.get('cohort_definition') or {}),
        'frozen_cohort_count': overall['frozen_count'],
        'frozen_state_counts': copy.deepcopy(snapshot.get('state_counts') or {}),
        'outcome_observation_coverage': {
            'observed_count': overall['observed_count'],
            'missing_count': overall['missing_count'],
            'missing_state_counts': {status: count for status, count in sorted(missing_state_counts.items())
                                     if status != 'OBSERVED_EXACT_FUTURE_SESSION'},
        },
        'overall': overall,
        'frozen_triage_state_summaries': triage_summaries,
        'high_priority_review_eligible_summaries': _group_attribution_summaries(
            outcomes,
            lambda row: 'high_priority_review_eligible:true' if row['frozen_high_priority_review_eligible']
            else 'high_priority_review_eligible:false',
            ['high_priority_review_eligible:true', 'high_priority_review_eligible:false'],
        ),
        'decision_packet_status_summaries': _group_attribution_summaries(
            outcomes, lambda row: str(row.get('frozen_decision_packet_status') or 'UNKNOWN'),
            sorted({str(row.get('frozen_decision_packet_status') or 'UNKNOWN') for row in outcomes}),
        ),
        'cohort_reconciliation': {
            'frozen_t_cohort_size': len(frozen),
            'attributed_tickers': [row['ticker'] for row in outcomes],
            'future_only_members_not_added_to_t': future_only,
            'frozen_members_not_in_future_snapshot_records': sorted(set(frozen) - future_members),
        },
        'price_representation': {
            'observed_change_semantics': OBSERVED_CHANGE_SEMANTICS,
            'arithmetic_comparison': 'SAME_REPRESENTATION_DESCRIPTIVE_ONLY',
            'raw_as_traded': 'NOT_PROMOTED',
            'transaction_costs': 'NONE',
            'dividends': 'NOT_APPLIED',
            'corporate_action_adjustment': 'NOT_INVENTED',
        },
        'temporal_safety': {
            'frozen_cohort_not_recomputed_from_future': True,
            'future_only_tickers_excluded_from_denominator': True,
            'missing_observations_remain_missing': True,
            'no_prior_session_substitution': True,
            'no_next_available_session_substitution': True,
            'no_intraday_substitution': True,
            'no_missing_as_zero': True,
            'future_descriptive_state_not_used_as_denominator': True,
            'historical_raw_as_traded_or_pit_promoted': False,
        },
        'outcomes': outcomes,
    }
    _walk_forbidden_keys(payload)
    payload['artifact_identity'] = _cohort_future_attribution_identity(payload)
    return payload


def replay_prospective_research_cohort_future_attribution(artifact: Mapping[str, Any]) -> None:
    if artifact.get('contract_version') != PROSPECTIVE_RESEARCH_COHORT_FUTURE_ATTRIBUTION_CONTRACT:
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_CONTRACT_MISMATCH')
    if artifact.get('artifact_identity') != _cohort_future_attribution_identity(artifact):
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_IDENTITY_MISMATCH')
    if artifact.get('authority') != 'PROSPECTIVE_DESCRIPTIVE_ATTRIBUTION_ONLY':
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_AUTHORITY_MISMATCH')
    if artifact.get('authority_effect') != 'NONE':
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_AUTHORITY_EFFECT_NOT_NONE')
    if artifact.get('future_is_strictly_later') is not True:
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_FUTURE_SESSION_NOT_STRICTLY_LATER')
    if str(artifact.get('future_session') or '') <= str(artifact.get('t_session') or ''):
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_FUTURE_SESSION_NOT_STRICTLY_LATER')
    rows = artifact.get('outcomes') or []
    if artifact.get('frozen_cohort_count') != len(rows):
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_COUNT_MISMATCH')
    tickers = [row['ticker'] for row in rows]
    if len(set(tickers)) != len(tickers) or sorted(tickers) != tickers:
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_TICKER_SET_INVALID')
    future_only = set((artifact.get('cohort_reconciliation') or {}).get('future_only_members_not_added_to_t') or [])
    if future_only & set(tickers):
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_FUTURE_COHORT_LEAKAGE')
    overall = artifact.get('overall') or {}
    expected = _cohort_attribution_summary(rows)
    if overall != expected:
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_OVERALL_SUMMARY_MISMATCH')
    if expected['observed_count'] + expected['missing_count'] != expected['frozen_count']:
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_COVERAGE_MISMATCH')
    if expected['positive'] + expected['negative'] + expected['unchanged'] != expected['observed_count']:
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_DIRECTION_MISMATCH')
    triage = artifact.get('frozen_triage_state_summaries') or []
    if [item.get('group') for item in triage] != list(ENTRY_RELEVANT_COHORT_STATES):
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_TRIAGE_GROUP_MISMATCH')
    if sum(item.get('frozen_count') or 0 for item in triage) != expected['frozen_count']:
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_GROUP_COUNT_MISMATCH')
    if (artifact.get('price_representation') or {}).get('raw_as_traded') != 'NOT_PROMOTED':
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_RAW_AS_TRADED_PROMOTION')
    if (artifact.get('price_representation') or {}).get('observed_change_semantics') != OBSERVED_CHANGE_SEMANTICS:
        raise ValueError('COHORT_FUTURE_ATTRIBUTION_CHANGE_SEMANTICS_MISMATCH')
    _walk_forbidden_keys(artifact)
