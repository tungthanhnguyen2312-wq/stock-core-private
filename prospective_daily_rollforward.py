"""Offline, append-only prospective daily sealing and learning-ledger support."""
from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter
from typing import Any, Mapping, Sequence

HORIZONS = {'H1': 1, 'H3': 3, 'H5': 5}


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode('utf-8')).hexdigest()


def _with_identity(payload: dict[str, Any], prefix: str, field: str = 'snapshot_identity') -> dict[str, Any]:
    payload[field] = prefix + _hash(payload)
    return payload


def _valid_identity(payload: Mapping[str, Any], prefix: str, field: str) -> bool:
    body = dict(payload)
    return body.pop(field, None) == prefix + _hash(body)


def _members(snapshot: Mapping[str, Any]) -> set[str]:
    if 'frozen_records' in snapshot:
        return {row['ticker'] for row in snapshot['frozen_records']}
    return set(snapshot['cohort']['members'])


def latest_exact_session(scaleouts: Sequence[Mapping[str, Any]]) -> str:
    """Resolve only from retained exact-session scale-outs, never from a calendar."""
    sessions = []
    for artifact in scaleouts:
        resolved = artifact.get('resolved_session', {})
        session = resolved.get('resolved_completed_session')
        if (artifact.get('artifact_type') == 'P3F9B_MARKET_WIDE_EXACT_SESSION_SCALEOUT' and
                resolved.get('exact_session_equality') is True and
                resolved.get('retained_snapshot_session') == session and
                resolved.get('incomplete_intraday_used') is False and isinstance(session, str)):
            sessions.append(session)
    if not sessions:
        raise ValueError('NO_RETAINED_EXACT_COMPLETED_SESSION')
    return max(sessions)


def seal_daily_snapshot(scaleout: Mapping[str, Any], exact_snapshot: Mapping[str, Any],
                        daily_bundle: Mapping[str, Any], previous_snapshot: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Seal one new T-state using only the retained data of that exact session."""
    session = scaleout.get('resolved_session', {}).get('resolved_completed_session')
    resolved = scaleout.get('resolved_session', {})
    cohort = daily_bundle.get('empirical_active_cohort', {})
    members = list(cohort.get('members', []))
    if (not isinstance(session, str) or resolved.get('retained_snapshot_session') != session or
            resolved.get('exact_session_equality') is not True or resolved.get('incomplete_intraday_used') is not False or
            exact_snapshot.get('resolved_completed_session') != session or exact_snapshot.get('retained_snapshot_session') != session or
            daily_bundle.get('frozen_session', {}).get('session') != session or
            daily_bundle.get('frozen_session', {}).get('incomplete_intraday_used') is not False or
            len(members) != cohort.get('member_count')):
        raise ValueError('DAILY_SNAPSHOT_EXACT_SESSION_PRECONDITION_NOT_MET')
    records = {row['identity']['canonical_ticker']: row for row in daily_bundle.get('records', [])}
    if set(members) - set(records):
        raise ValueError('DAILY_SNAPSHOT_COHORT_RECORD_MISMATCH')
    daily_records = []
    for ticker in sorted(members):
        source = records[ticker]
        features = source['market_features']
        if features.get('status') != 'SHADOW_ONLY' or source.get('session') != session:
            raise ValueError('DAILY_SNAPSHOT_TECHNICAL_STATE_NOT_AS_OF_T')
        daily_records.append({
            'ticker': ticker,
            'research_session': session,
            'daily_technical_state': features,
            'exact_session_close': exact_snapshot['records'][ticker]['observations'][-1]['close'],
            'source_record_identity': 'daily_t_state_record:' + _hash(source),
            'research_attention_descriptors': {'status': 'UNAVAILABLE_NOT_MATERIALIZED_AS_OF_T'},
            'queue_state': {'status': 'UNAVAILABLE_NOT_MATERIALIZED_AS_OF_T'},
            'setup_price_market_relative_downside_context': {'status': 'UNAVAILABLE_NOT_MATERIALIZED_AS_OF_T'},
            'dossier_task_scenario_owner_ai_state': {'status': 'UNAVAILABLE_NOT_MATERIALIZED_AS_OF_T'},
            'fundamental_evidence_authority': {'status': 'UNAVAILABLE_NO_DAILY_AUTHORITY_CONTRACT_AS_OF_T'},
        })
    prior_members = _members(previous_snapshot) if previous_snapshot else set()
    current_members = set(members)
    payload = {
        'schema_version': '1.0.0', 'contract_version': 'prospective_daily_snapshot/v1',
        'authority': 'PROSPECTIVE_RESEARCH_SHADOW_T_STATE_NOT_HISTORICAL_PIT_BACKTEST',
        'research_session': session,
        'source_artifact_identities': {'exact_scaleout': scaleout['artifact_identity'], 'exact_snapshot': exact_snapshot['snapshot_identity'],
                                       'daily_research_bundle': daily_bundle['artifact_identity']},
        'cohort': {'identity': cohort['cohort_identity'], 'member_count': len(members), 'members': sorted(members),
                   'authority': cohort['authority'], 'membership_change_vs_prior_t_state': {
                       'prior_t_session': previous_snapshot.get('research_session') if previous_snapshot else None,
                       'entered_tickers': sorted(current_members - prior_members), 'exited_tickers': sorted(prior_members - current_members),
                       'retained_intersection': sorted(current_members & prior_members),
                       'not_authoritative_active_universe_change': True}},
        'seal': {'state': 'SEALED_PENDING_FUTURE_OBSERVATION', 'seal_timestamp': scaleout['execution_timestamp'],
                 'seal_timestamp_semantics': 'RETAINED_EXACT_SESSION_MATERIALIZATION_TIMESTAMP_NOT_SOFTWARE_CLOCK',
                 'research_observation_timestamp': scaleout['execution_timestamp'], 'sealed_before_later_retained_exact_session': True,
                 'future_outcomes': 'PENDING_FUTURE_OBSERVATION'},
        'components': {'daily_market_technical_state': 'AVAILABLE_AS_OF_T',
                       'setup_price_market_relative_downside': 'UNAVAILABLE_NOT_MATERIALIZED_AS_OF_T',
                       'research_attention_queue': 'UNAVAILABLE_NOT_MATERIALIZED_AS_OF_T',
                       'dossier_task_scenario_owner_ai': 'UNAVAILABLE_NOT_MATERIALIZED_AS_OF_T'},
        'records': daily_records,
        'authority_boundaries': {'no_network_acquisition': True, 'no_future_outcome_used': True,
                                 'no_prior_session_analytical_state_relabelled': True, 'no_pit_or_raw_as_traded_promotion': True},
    }
    return _with_identity(payload, 'prospective_daily_snapshot:')


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    observed = [row for row in rows if row.get('outcome_status') == 'OBSERVED_EXACT_FUTURE_SESSION']
    values = [row['observed_return'] for row in observed]
    return {'eligible_t_snapshot_count': len(rows), 'observed_sample_count': len(observed), 'missing_count': len(rows) - len(observed),
            'positive': sum(row.get('direction') == 'POSITIVE' for row in observed),
            'negative': sum(row.get('direction') == 'NEGATIVE' for row in observed),
            'unchanged': sum(row.get('direction') == 'UNCHANGED' for row in observed),
            'mean_observed_return': sum(values) / len(values) if values else None,
            'median_observed_return': statistics.median(values) if values else None}


def build_learning_ledger(snapshots: Sequence[Mapping[str, Any]], first_attribution: Mapping[str, Any],
                          retained_completed_sessions: Sequence[str]) -> dict[str, Any]:
    """Create an idempotent ledger. Horizons count retained sessions, not calendar dates."""
    if not _valid_identity(first_attribution, 'first_real_prospective_attribution:', 'artifact_identity'):
        raise ValueError('FIRST_ATTRIBUTION_IDENTITY_INVALID')
    sessions = sorted(set(retained_completed_sessions))
    rows = []
    for snapshot in sorted(snapshots, key=lambda item: item['research_session']):
        session = snapshot['research_session']
        later = [item for item in sessions if item > session]
        horizons = {}
        for label, required_count in HORIZONS.items():
            target = later[required_count - 1] if len(later) >= required_count else None
            completed = session == first_attribution['precondition']['t_session'] and target == first_attribution['precondition']['future_session'] and label == 'H1'
            horizons[label] = {'required_completed_future_sessions': required_count, 'resolved_future_session': target,
                               'status': 'OBSERVED' if completed else 'PENDING_FUTURE_OBSERVATION',
                               'attribution_identity': first_attribution['artifact_identity'] if completed else None}
        rows.append({'t_session': session, 'snapshot_identity': snapshot.get('snapshot_identity', snapshot.get('snapshot_id')),
                     'cohort_count': len(_members(snapshot)), 'horizons': horizons})
    observed_rows = first_attribution['outcomes']
    groups: dict[str, list[Mapping[str, Any]]] = {'overall': observed_rows}
    for row in observed_rows:
        labels = list(row.get('frozen_cohort_keys', []))
        labels += ['queue:FROZEN_25_NAME_QUEUE' if row.get('queue_member') else 'queue:FROZEN_NON_QUEUE']
        labels += ['attention:' + item for item in row.get('attention_descriptors', [])]
        for label in labels:
            groups.setdefault(label, []).append(row)
    aggregation = [{'group': label, **_summary(group_rows)} for label, group_rows in sorted(groups.items())]
    payload = {'schema_version': '1.0.0', 'contract_version': 'prospective_learning_ledger/v1',
               'authority': 'CUMULATIVE_DESCRIPTIVE_PROSPECTIVE_LEARNING_NOT_BACKTEST', 'rows': rows,
               'aggregation': {'horizon': 'H1', 'maturity_state': 'FIRST_OBSERVATION_ONLY', 'groups': aggregation,
                               'limitations': ['ONE_MATURE_T_SNAPSHOT_ONLY', 'OVERLAPPING_WINDOWS_AND_REPEATED_TICKERS_NOT_STATISTICALLY_INDEPENDENT',
                                               'NO_ALPHA_SIGNIFICANCE_EDGE_OR_CAUSAL_CLAIM']},
               'retained_completed_sessions': sessions, 'append_only': True}
    return _with_identity(payload, 'prospective_learning_ledger:', 'ledger_identity')
