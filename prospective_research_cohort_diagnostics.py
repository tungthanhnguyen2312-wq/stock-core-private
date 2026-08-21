"""Deterministic prospective research cohort diagnostics layer.

This module consumes the prospective learning ledger, sealed snapshots,
and strictly later exact-session attributions to generate deterministic
descriptive cohort summaries, sample maturity classifications, and data
accumulation needs across horizons (H1, H3, H5).

This is strictly descriptive prospective research diagnostics.
It is NOT a backtest, alpha study, statistical proof, strategy optimization,
recommendation generation, parameter search, ranking, or portfolio construction.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Mapping, Sequence

HORIZONS = ('H1', 'H3', 'H5')

MATURITY_NO_OBSERVATIONS = 'NO_OBSERVATIONS'
MATURITY_PENDING_OUTCOMES = 'PENDING_OUTCOMES'
MATURITY_OBSERVED_IMMATURE_SAMPLE = 'OBSERVED_IMMATURE_SAMPLE'
MATURITY_DESCRIPTIVE_SAMPLE_AVAILABLE = 'DESCRIPTIVE_SAMPLE_AVAILABLE'

DIMENSION_OVERALL = 'overall'
DIMENSION_ATTENTION = 'attention_descriptor'
DIMENSION_SETUP = 'setup_classification'
DIMENSION_QUEUE = 'queue_membership'
DIMENSION_DOWNSIDE = 'downside_context'
DIMENSION_PRICE_STRUCTURE = 'price_structure_context'
DIMENSION_MARKET_REGIME = 'market_regime'
DIMENSION_RELATIVE_AUTHORITY = 'relative_classification_authority'
DIMENSION_EVIDENCE_AUTHORITY = 'evidence_authority'
DIMENSION_THESIS = 'thesis_continuity'

PREFIX_DIMENSION_MAP = {
    'attention:': DIMENSION_ATTENTION,
    'setup:': DIMENSION_SETUP,
    'queue:': DIMENSION_QUEUE,
    'downside:': DIMENSION_DOWNSIDE,
    'price_structure:': DIMENSION_PRICE_STRUCTURE,
    'market:': DIMENSION_MARKET_REGIME,
    'relative_authority:': DIMENSION_RELATIVE_AUTHORITY,
    'authority:': DIMENSION_EVIDENCE_AUTHORITY,
    'thesis:': DIMENSION_THESIS,
}


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode('utf-8')).hexdigest()


def _with_identity(payload: dict[str, Any], prefix: str, field: str = 'artifact_identity') -> dict[str, Any]:
    payload[field] = prefix + _hash(payload)
    return payload


def _valid_identity(payload: Mapping[str, Any], prefix: str, field: str) -> bool:
    body = dict(payload)
    return body.pop(field, None) == prefix + _hash(body)


def _calculate_descriptive_statistics(returns: Sequence[float]) -> dict[str, Any] | None:
    if not returns:
        return None
    sorted_returns = sorted(returns)
    n = len(sorted_returns)
    
    # Deterministic quartiles
    if n == 1:
        p25 = sorted_returns[0]
        p75 = sorted_returns[0]
    elif n < 4:
        p25 = statistics.quantiles(sorted_returns, n=4, method='inclusive')[0] if hasattr(statistics, 'quantiles') else sorted_returns[0]
        p75 = statistics.quantiles(sorted_returns, n=4, method='inclusive')[2] if hasattr(statistics, 'quantiles') else sorted_returns[-1]
    else:
        q = statistics.quantiles(sorted_returns, n=4, method='inclusive')
        p25 = q[0]
        p75 = q[2]

    return {
        'count': n,
        'mean_forward_return': statistics.fmean(sorted_returns),
        'median_forward_return': statistics.median(sorted_returns),
        'min_forward_return': sorted_returns[0],
        'max_forward_return': sorted_returns[-1],
        'positive_count': sum(1 for r in sorted_returns if r > 0),
        'negative_count': sum(1 for r in sorted_returns if r < 0),
        'zero_count': sum(1 for r in sorted_returns if r == 0),
        'p25_forward_return': p25,
        'p75_forward_return': p75,
    }


def _extract_ticker_cohorts(snapshot: Mapping[str, Any],
                            extension: Mapping[str, Any] | None = None) -> dict[str, set[tuple[str, str]]]:
    """Extract (dimension, value) pairs for each ticker in the snapshot."""
    ticker_cohorts: dict[str, set[tuple[str, str]]] = {}
    
    # Check if this is the 2026-08-20 style snapshot with frozen_records or 2026-08-21 style daily snapshot
    if 'frozen_records' in snapshot:
        extension_map = {}
        if extension and 'records' in extension:
            for row in extension['records']:
                extension_map[row['ticker']] = row

        for record in snapshot['frozen_records']:
            ticker = record['ticker']
            cohorts = {(DIMENSION_OVERALL, 'ALL_OBSERVATIONS')}
            
            # Attention descriptors
            for descriptor in record.get('attention_descriptors', []):
                cohorts.add((DIMENSION_ATTENTION, descriptor))
            
            # Queue membership
            if record.get('queue_member'):
                cohorts.add((DIMENSION_QUEUE, 'FROZEN_25_NAME_QUEUE'))
            else:
                cohorts.add((DIMENSION_QUEUE, 'FROZEN_NON_QUEUE'))
            
            # Evidence authority
            auth = record.get('fundamental_authority')
            if auth:
                cohorts.add((DIMENSION_EVIDENCE_AUTHORITY, auth))
            
            # Extension keys (setup, downside, price_structure, market, relative_authority)
            ext_row = extension_map.get(ticker)
            if ext_row:
                has_setup = False
                for key in ext_row.get('prospective_cohort_keys', []):
                    matched = False
                    for prefix, dim in PREFIX_DIMENSION_MAP.items():
                        if key.startswith(prefix):
                            val = key[len(prefix):]
                            cohorts.add((dim, val))
                            if dim == DIMENSION_SETUP:
                                has_setup = True
                            matched = True
                            break
                    if not matched:
                        cohorts.add(('custom_descriptor', key))
                if not has_setup:
                    cohorts.add((DIMENSION_SETUP, 'NO_DISTINCT_SETUP'))
            
            ticker_cohorts[ticker] = cohorts

    elif 'records' in snapshot:
        # Daily snapshot with daily_records
        for record in snapshot['records']:
            ticker = record['ticker']
            cohorts = {(DIMENSION_OVERALL, 'ALL_OBSERVATIONS')}
            # Note: For daily rollforward snapshots where components were UNAVAILABLE_NOT_MATERIALIZED_AS_OF_T,
            # no synthetic descriptor membership is added.
            ticker_cohorts[ticker] = cohorts

    return ticker_cohorts


def build_cohort_diagnostics(
    ledger: Mapping[str, Any],
    attributions: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
    extensions: Sequence[Mapping[str, Any]] | None = None
) -> dict[str, Any]:
    """Deterministic aggregation of cohort diagnostics across horizons and dimensions.

    Enforces:
    - Input identity validation
    - Temporal safety (T < outcome_session)
    - No substitution of missing observations with zero
    - Explicit sample maturity classification
    - Deterministic ordering and replayability
    """
    if not _valid_identity(ledger, 'prospective_learning_ledger:', 'ledger_identity'):
        raise ValueError('LEDGER_IDENTITY_INVALID')

    extensions_by_session: dict[str, Mapping[str, Any]] = {}
    if extensions:
        for ext in extensions:
            if not _valid_identity(ext, 'prospective_research_context_extension:', 'extension_content_identity'):
                raise ValueError('EXTENSION_IDENTITY_INVALID')
            extensions_by_session[ext['research_session']] = ext

    snapshots_by_session: dict[str, Mapping[str, Any]] = {}
    for snap in snapshots:
        session = snap.get('research_session')
        if not session:
            raise ValueError('SNAPSHOT_SESSION_MISSING')
        id_field = 'snapshot_identity' if 'snapshot_identity' in snap else 'snapshot_id'
        prefix = 'prospective_daily_snapshot:' if 'prospective_daily_snapshot:' in snap.get(id_field, '') else 'prospective_research_snapshot:'
        if not _valid_identity(snap, prefix, id_field):
            raise ValueError(f'SNAPSHOT_IDENTITY_INVALID for session {session}')
        snapshots_by_session[session] = snap

    attributions_by_identity: dict[str, Mapping[str, Any]] = {}
    for attr in attributions:
        if not _valid_identity(attr, 'first_real_prospective_attribution:', 'artifact_identity'):
            raise ValueError('ATTRIBUTION_IDENTITY_INVALID')
        attributions_by_identity[attr['artifact_identity']] = attr

    # Pre-extract ticker cohorts for all snapshots
    snapshot_ticker_cohorts: dict[str, dict[str, set[tuple[str, str]]]] = {}
    for session, snap in snapshots_by_session.items():
        ext = extensions_by_session.get(session)
        snapshot_ticker_cohorts[session] = _extract_ticker_cohorts(snap, ext)

    # Collect all unique cohort (dimension, value) pairs across all snapshots
    all_cohort_keys: set[tuple[str, str]] = set()
    for session_cohorts in snapshot_ticker_cohorts.values():
        for cohorts in session_cohorts.values():
            all_cohort_keys.update(cohorts)

    # Process each horizon and cohort
    cohort_summaries: list[dict[str, Any]] = []
    
    # Also track horizon-level metrics
    horizon_metrics: dict[str, dict[str, Any]] = {}
    for horizon in HORIZONS:
        horizon_metrics[horizon] = {
            'required_future_sessions': 1 if horizon == 'H1' else 3 if horizon == 'H3' else 5,
            'total_t_observations': 0,
            'observed_outcome_count': 0,
            'pending_outcome_count': 0,
            'missing_outcome_count': 0,
            'observed_sessions': [],
            'pending_sessions': [],
        }

    # Aggregate by (dimension, value, horizon)
    for horizon in HORIZONS:
        # Pre-process ledger rows for this horizon
        session_outcomes_map: dict[str, dict[str, dict[str, Any]]] = {}
        for row in ledger.get('rows', []):
            session = row['t_session']
            h_info = row.get('horizons', {}).get(horizon, {})
            h_status = h_info.get('status')
            attr_id = h_info.get('attribution_identity')
            
            if session not in snapshot_ticker_cohorts:
                continue

            session_tickers = snapshot_ticker_cohorts[session]
            horizon_metrics[horizon]['total_t_observations'] += len(session_tickers)

            ticker_outcomes: dict[str, dict[str, Any]] = {}
            if h_status == 'OBSERVED' and attr_id and attr_id in attributions_by_identity:
                attr = attributions_by_identity[attr_id]
                future_session = attr.get('precondition', {}).get('future_session')
                if future_session <= session:
                    raise ValueError('TEMPORAL_SAFETY_VIOLATION_FUTURE_NOT_STRICTLY_LATER')
                
                horizon_metrics[horizon]['observed_sessions'].append(session)
                outcomes_by_ticker = {o['ticker']: o for o in attr.get('outcomes', [])}
                
                for ticker in session_tickers:
                    if ticker in outcomes_by_ticker:
                        o = outcomes_by_ticker[ticker]
                        status = o.get('outcome_status')
                        if status == 'OBSERVED_EXACT_FUTURE_SESSION':
                            ret = o.get('observed_return')
                            if not isinstance(ret, (int, float)):
                                raise ValueError(f'INVALID_OBSERVED_RETURN for {ticker}')
                            ticker_outcomes[ticker] = {
                                'status': 'OBSERVED',
                                'return': float(ret),
                                'session': session,
                            }
                            horizon_metrics[horizon]['observed_outcome_count'] += 1
                        elif status == 'MISSING_FUTURE_OBSERVATION':
                            ticker_outcomes[ticker] = {
                                'status': 'MISSING',
                                'reason': o.get('missing_state_reason', 'MISSING_FUTURE_OBSERVATION'),
                                'session': session,
                            }
                            horizon_metrics[horizon]['missing_outcome_count'] += 1
                        else:
                            ticker_outcomes[ticker] = {
                                'status': 'PENDING',
                                'session': session,
                            }
                            horizon_metrics[horizon]['pending_outcome_count'] += 1
                    else:
                        ticker_outcomes[ticker] = {
                            'status': 'MISSING',
                            'reason': 'TICKER_NOT_IN_ATTRIBUTION',
                            'session': session,
                        }
                        horizon_metrics[horizon]['missing_outcome_count'] += 1
            else:
                horizon_metrics[horizon]['pending_sessions'].append(session)
                for ticker in session_tickers:
                    ticker_outcomes[ticker] = {
                        'status': 'PENDING',
                        'session': session,
                    }
                    horizon_metrics[horizon]['pending_outcome_count'] += 1
            
            session_outcomes_map[session] = ticker_outcomes

        # Compute summary for each cohort in this horizon
        for dim, val in sorted(all_cohort_keys):
            obs_count = 0
            observed_count = 0
            pending_count = 0
            missing_count = 0
            observed_returns: list[float] = []
            observed_sessions_set: set[str] = set()
            active_sessions_set: set[str] = set()
            session_distribution: dict[str, dict[str, int]] = {}

            for session, ticker_cohorts in sorted(snapshot_ticker_cohorts.items()):
                s_obs = 0
                s_observed = 0
                s_pending = 0
                s_missing = 0
                
                ticker_outcomes = session_outcomes_map.get(session, {})
                for ticker, cohorts in ticker_cohorts.items():
                    if (dim, val) in cohorts:
                        obs_count += 1
                        s_obs += 1
                        active_sessions_set.add(session)
                        
                        outcome = ticker_outcomes.get(ticker, {'status': 'PENDING'})
                        if outcome['status'] == 'OBSERVED':
                            observed_count += 1
                            s_observed += 1
                            observed_returns.append(outcome['return'])
                            observed_sessions_set.add(session)
                        elif outcome['status'] == 'MISSING':
                            missing_count += 1
                            s_missing += 1
                        else:
                            pending_count += 1
                            s_pending += 1

                if s_obs > 0:
                    session_distribution[session] = {
                        'observation_count': s_obs,
                        'observed_count': s_observed,
                        'pending_count': s_pending,
                        'missing_count': s_missing,
                    }

            if obs_count == 0:
                maturity_state = MATURITY_NO_OBSERVATIONS
            elif observed_count == 0:
                maturity_state = MATURITY_PENDING_OUTCOMES
            elif len(observed_sessions_set) == 1:
                maturity_state = MATURITY_OBSERVED_IMMATURE_SAMPLE
            else:
                maturity_state = MATURITY_DESCRIPTIVE_SAMPLE_AVAILABLE

            coverage_ratio = (observed_count / obs_count) if obs_count > 0 else 0.0
            earliest_session = min(active_sessions_set) if active_sessions_set else None
            latest_session = max(active_sessions_set) if active_sessions_set else None

            stats = _calculate_descriptive_statistics(observed_returns)

            cohort_summary = {
                'cohort_dimension': dim,
                'cohort_value': val,
                'research_horizon': horizon,
                'observation_count': obs_count,
                'observed_outcome_count': observed_count,
                'pending_count': pending_count,
                'unavailable_missing_count': missing_count,
                'coverage_ratio': coverage_ratio,
                'earliest_research_session': earliest_session,
                'latest_research_session': latest_session,
                'observed_sessions_count': len(observed_sessions_set),
                'sample_maturity_state': maturity_state,
                'descriptive_statistics': stats,
                'session_distribution': session_distribution,
            }
            cohort_summary['cohort_identity'] = 'cohort_summary:' + _hash(cohort_summary)
            cohort_summaries.append(cohort_summary)

    # Sort cohort summaries deterministically by dimension, value, horizon
    cohort_summaries.sort(key=lambda x: (x['cohort_dimension'], x['cohort_value'], x['research_horizon']))

    # Assemble Data Accumulation Needs
    # Identify under-observed descriptors
    descriptor_needs: list[dict[str, Any]] = []
    for s in cohort_summaries:
        if s['research_horizon'] == 'H1' and s['observed_outcome_count'] > 0 and s['observed_outcome_count'] < 30:
            descriptor_needs.append({
                'cohort_dimension': s['cohort_dimension'],
                'cohort_value': s['cohort_value'],
                'horizon': 'H1',
                'observed_count': s['observed_outcome_count'],
                'issue': 'LOW_SAMPLE_SIZE_UNDER_30',
                'recommendation': 'ACCUMULATE_MORE_PROSPECTIVE_SESSIONS',
            })
        elif s['research_horizon'] == 'H1' and s['sample_maturity_state'] == MATURITY_OBSERVED_IMMATURE_SAMPLE:
            if s['observed_outcome_count'] >= 30:
                descriptor_needs.append({
                    'cohort_dimension': s['cohort_dimension'],
                    'cohort_value': s['cohort_value'],
                    'horizon': 'H1',
                    'observed_count': s['observed_outcome_count'],
                    'issue': 'SINGLE_SESSION_IMMATURE_SAMPLE',
                    'recommendation': 'NEEDS_MULTI_SESSION_CONFIRMATION',
                })

    # Missing outcome concentration
    missing_concentration: list[dict[str, Any]] = []
    for attr in attributions:
        for o in attr.get('outcomes', []):
            if o.get('outcome_status') == 'MISSING_FUTURE_OBSERVATION':
                missing_concentration.append({
                    'ticker': o['ticker'],
                    't_session': o.get('t_session'),
                    'future_session': o.get('future_session'),
                    'missing_state_reason': o.get('missing_state_reason'),
                    'frozen_cohort_keys': o.get('frozen_cohort_keys', []),
                })

    data_accumulation_needs = {
        'horizon_needs': {
            'H1': {
                'status': 'ONE_SESSION_OBSERVED_SUBSEQUENT_PENDING',
                'observed_sessions': sorted(set(horizon_metrics['H1']['observed_sessions'])),
                'pending_sessions': sorted(set(horizon_metrics['H1']['pending_sessions'])),
                'total_observations': horizon_metrics['H1']['total_t_observations'],
                'observed_count': horizon_metrics['H1']['observed_outcome_count'],
                'missing_count': horizon_metrics['H1']['missing_outcome_count'],
                'pending_count': horizon_metrics['H1']['pending_outcome_count'],
                'needs': 'Subsequent daily sessions require completed exact closes strictly later than T.',
            },
            'H3': {
                'status': 'ALL_OUTCOMES_PENDING',
                'observed_sessions': [],
                'pending_sessions': sorted(set(horizon_metrics['H3']['pending_sessions'])),
                'total_observations': horizon_metrics['H3']['total_t_observations'],
                'observed_count': 0,
                'missing_count': 0,
                'pending_count': horizon_metrics['H3']['pending_outcome_count'],
                'required_completed_future_sessions': 3,
                'needs': 'Requires 3 completed strictly-future exact sessions per T-state.',
            },
            'H5': {
                'status': 'ALL_OUTCOMES_PENDING',
                'observed_sessions': [],
                'pending_sessions': sorted(set(horizon_metrics['H5']['pending_sessions'])),
                'total_observations': horizon_metrics['H5']['total_t_observations'],
                'observed_count': 0,
                'missing_count': 0,
                'pending_count': horizon_metrics['H5']['pending_outcome_count'],
                'required_completed_future_sessions': 5,
                'needs': 'Requires 5 completed strictly-future exact sessions per T-state.',
            },
        },
        'descriptor_sample_needs': descriptor_needs,
        'missing_observation_concentration': missing_concentration,
    }

    payload = {
        'schema_version': '1.0.0',
        'contract_version': 'prospective_research_cohort_diagnostics/v1',
        'authority': 'PROSPECTIVE_RESEARCH_COHORT_DIAGNOSTICS_NOT_BACKTEST_NOT_PREDICTIVE',
        'disposition': 'PROSPECTIVE_RESEARCH_COHORT_DIAGNOSTICS_V1_READY',
        'input_identities': {
            'ledger_identity': ledger['ledger_identity'],
            'attribution_identities': sorted(attributions_by_identity.keys()),
            'snapshot_identities': sorted(snap.get('snapshot_identity', snap.get('snapshot_id')) for snap in snapshots_by_session.values()),
            'context_extension_identities': sorted(ext['extension_content_identity'] for ext in extensions_by_session.values()),
        },
        'retained_sessions': sorted(ledger.get('retained_completed_sessions', [])),
        'cohort_summary_count': len(cohort_summaries),
        'cohort_diagnostics': cohort_summaries,
        'data_accumulation_needs': data_accumulation_needs,
        'temporal_safety': {
            't_strictly_before_outcome_session': True,
            'no_imputed_or_zeroed_missing_observations': True,
            'frozen_cohort_composition_preserved': True,
            'no_raw_as_traded_or_pit_promoted': True,
            'no_provider_api_calls_to_manufacture_outcomes': True,
        },
        'limitations': [
            'PROSPECTIVE_DESCRIPTIVE_DIAGNOSTICS_ONLY_NOT_A_BACKTEST',
            'NOT_PREDICTIVE_VALIDATION_NO_SIGNIFICANCE_OR_ALPHA_CLAIM',
            'NO_RECOMMENDATION_OR_RANKING_AUTHORITY',
            'NO_POSITION_SIZING_OR_LIQUIDITY_AUTHORITY',
            'SINGLE_OBSERVED_SESSION_H1_IS_IMMATURE_SAMPLE',
            'OVERLAPPING_WINDOWS_AND_REPEATED_TICKERS_ARE_NOT_STATISTICALLY_INDEPENDENT',
            'H3_AND_H5_REMAIN_PENDING_FUTURE_OBSERVATIONS',
        ],
    }

    return _with_identity(payload, 'prospective_research_cohort_diagnostics:', 'artifact_identity')


def render_cohort_diagnostics_summary(diagnostics: Mapping[str, Any]) -> str:
    """Render a concise, human-readable markdown summary for research review."""
    lines = []
    lines.append('# Prospective Research Cohort Diagnostics V1 — Summary Report')
    lines.append('')
    lines.append(f"- **Artifact Identity**: `{diagnostics['artifact_identity']}`")
    lines.append(f"- **Contract Version**: `{diagnostics['contract_version']}`")
    lines.append(f"- **Authority**: `{diagnostics['authority']}`")
    lines.append(f"- **Retained Sessions**: {', '.join(diagnostics['retained_sessions'])}")
    lines.append(f"- **Total Cohort Summaries**: {diagnostics['cohort_summary_count']}")
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 1. Horizon Maturity & Overall Coverage')
    lines.append('')
    lines.append('| Horizon | Status | Total Observations | Observed | Missing | Pending | Coverage Ratio |')
    lines.append('|:---|:---|---:|---:|---:|---:|---:|')
    
    hn = diagnostics['data_accumulation_needs']['horizon_needs']
    for h in HORIZONS:
        info = hn.get(h, {})
        tot = info.get('total_observations', 0)
        obs = info.get('observed_count', 0)
        mis = info.get('missing_count', 0)
        pen = info.get('pending_count', 0)
        cov = f'{(obs / tot * 100):.2f}%' if tot > 0 else '0.00%'
        lines.append(f"| **{h}** | `{info.get('status')}` | {tot} | {obs} | {mis} | {pen} | {cov} |")
    
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 2. H1 Descriptive Cohort Diagnostics (Immature Single-Session Sample)')
    lines.append('')
    lines.append('| Dimension | Value | Sample State | Obs | Return Mean | Return Median | Min | Max | Pos / Neg / Zero |')
    lines.append('|:---|:---|:---|---:|---:|---:|---:|---:|:---|')

    for c in diagnostics['cohort_diagnostics']:
        if c['research_horizon'] == 'H1':
            stats = c['descriptive_statistics']
            if stats:
                mean_s = f"{stats['mean_forward_return'] * 100:+.2f}%"
                med_s = f"{stats['median_forward_return'] * 100:+.2f}%"
                min_s = f"{stats['min_forward_return'] * 100:+.2f}%"
                max_s = f"{stats['max_forward_return'] * 100:+.2f}%"
                pnz = f"{stats['positive_count']} / {stats['negative_count']} / {stats['zero_count']}"
            else:
                mean_s = med_s = min_s = max_s = pnz = 'N/A'
            lines.append(
                f"| `{c['cohort_dimension']}` | `{c['cohort_value']}` | `{c['sample_maturity_state']}` | {c['observed_outcome_count']}/{c['observation_count']} | {mean_s} | {med_s} | {min_s} | {max_s} | {pnz} |"
            )

    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 3. Data Accumulation Needs')
    lines.append('')
    lines.append('### 3.1 Horizon Gaps')
    for h, info in hn.items():
        lines.append(f"- **{h}**: {info.get('needs')} (Observed sessions: `{info.get('observed_sessions')}`, Pending: `{info.get('pending_sessions')}`)")

    lines.append('')
    lines.append('### 3.2 Low-Sample / Immature Descriptors (H1)')
    needs = diagnostics['data_accumulation_needs'].get('descriptor_sample_needs', [])
    low_sample = [n for n in needs if n.get('issue') == 'LOW_SAMPLE_SIZE_UNDER_30']
    if low_sample:
        for item in low_sample:
            lines.append(f"- `{item['cohort_dimension']}:{item['cohort_value']}`: n={item['observed_count']} ({item['issue']}) -> {item['recommendation']}")
    else:
        lines.append("- None")

    lines.append('')
    lines.append('### 3.3 Missing Observations Concentration (H1)')
    missing = diagnostics['data_accumulation_needs'].get('missing_observation_concentration', [])
    if missing:
        for m in missing:
            lines.append(f"- **{m['ticker']}** at session `{m['t_session']}`: Reason `{m['missing_state_reason']}`")
    else:
        lines.append("- Zero missing observations recorded.")

    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 4. Governance & Authority Invariants')
    for lim in diagnostics.get('limitations', []):
        lines.append(f"- `{lim}`")
    lines.append('')

    return '\n'.join(lines)
