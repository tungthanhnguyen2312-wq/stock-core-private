"""Offline R7 acceptance. Exact hashed manifest inputs only; no acquisition or runtime writes.

The portable report contains counts/hashes, not price/holdings values. Optional row
output lives only in the worktree scratch directory. Existing source statuses are
preserved; absence of canonical capital is not an assertion about an owner's account.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import raw_pit_authority_matrix as authority
import stocklookup_core.decision.integrated_investment_decision_product as integrated
import stocklookup_core.portfolio.execution_capacity_research as capacity
from field_temporal_contract import stable_id
from stocklookup_core.portfolio.portfolio_aware_decision import governed_research_sizing
from stocklookup_core.portfolio.current_portfolio_risk_envelope import governed_portfolio_research
from stocklookup_core.portfolio.current_portfolio_risk_research import qualified_window_readiness


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def numeric(value, *, zero=False):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and (value >= 0 if zero else value > 0)


class Inputs:
    def __init__(self, manifest, roots):
        self.entries = sorted(manifest['inputs'], key=lambda e: e['id'])
        if len({e['id'] for e in self.entries}) != len(self.entries):
            raise ValueError('DUPLICATE_MANIFEST_INPUT_ID')
        self.paths = {}
        self.hashes = {}
        for entry in self.entries:
            root = roots[entry['root']].resolve()
            path = (root / entry['path']).resolve()
            if not path.is_relative_to(root):
                raise ValueError('INPUT_PATH_ESCAPES_ROOT')
            digest = file_hash(path)
            if digest != entry['sha256']:
                raise ValueError('RETAINED_INPUT_HASH_CHANGED:' + entry['path'])
            key = entry['root'] + ':' + entry['path']
            self.paths[entry['id']] = path
            self.hashes[key] = digest

    def load(self, name):
        return json.loads(self.paths[name].read_text(encoding='utf-8-sig'))

    def unchanged(self):
        for e in self.entries:
            if file_hash(self.paths[e['id']]) != e['sha256']:
                raise ValueError('SOURCE_MUTATED:' + e['path'])


def binding(feature, ticker, session, source_identity, basis_identity, *, fit='ELIGIBLE',
            use='CURRENT_RESEARCH', status='QUALIFIED', temporal='CURRENT_RESEARCH_ONLY', known=None, **kwargs):
    return dict(feature=feature, ticker=ticker, session=session, source_identity=source_identity,
                basis_identity=basis_identity, source_status=status, fitness={use: fit},
                temporal_semantics=temporal, knowledge_available_at=known, authority_tier='RETAINED_USE_SCOPED', **kwargs)


def build_acceptance(inputs, *, row_writer=None):
    current = inputs.load('current_integrated')
    snapshot = inputs.load('current_price')
    handoff = inputs.load('current_handoff')
    universe = inputs.load('current_universe')
    session = current['session']
    if session != '2026-10-01' or len(current['records']) != 1683 or snapshot['resolved_completed_session'] != session:
        raise ValueError('CURRENT_DENOMINATOR_OR_SESSION_MISMATCH')
    feature_counts = defaultdict(Counter)
    source_status_counts = defaultdict(Counter)
    use_counts = defaultdict(Counter)
    blockers = Counter()
    row_chain = hashlib.sha256()
    row_count = 0

    def emit(row):
        nonlocal row_count
        row_count += 1
        row_chain.update(row['row_identity'].encode())
        if row_writer:
            row_writer.write(json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n')

    def rows_for(evidence, ticker, at_session, *, cutoff=None, current_scope=False):
        for f in authority.FEATURES:
            row = authority.authority_row(feature=f, use_case='CURRENT_RESEARCH', ticker=ticker,
                    session=at_session, evidence=evidence.get(f))
            emit(row)
            if current_scope:
                feature_counts[f][row['fitness']] += 1
                source_status_counts[f][row['source_status']] += 1
        views = []
        for use in authority.USE_CASES:
            view = authority.use_case_readiness(use_case=use, ticker=ticker, session=at_session,
                                               evidence=evidence, knowledge_cutoff=cutoff)
            for row in view['required_rows']:
                emit(row)
            if current_scope:
                use_counts[use][view['state']] += 1
                blockers.update(view['blocker_reason_codes'])
            views.append(view)
        return views

    scopes = []
    after_records = {}
    deltas = Counter()
    numeric_denominator = machine_invalidation = 0
    risk_windows = qualified_window_readiness(price_snapshot=snapshot, tickers=list(current['records']))
    risk_counts = defaultdict(Counter)
    for ticker, record in sorted(current['records'].items()):
        source = snapshot['records'].get(ticker) or {}
        observations = [o for o in source.get('observations') or [] if o.get('session') == session]
        evidence = {}
        observation = observations[0] if len(observations) == 1 else {}
        for feature, field in [('CURRENT_PRICE', 'close'), ('CURRENT_VOLUME', 'volume')]:
            if numeric(observation.get(field), zero=field == 'volume') and observation.get('qualification') == 'CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY':
                evidence[feature] = binding(feature, ticker, session, snapshot['snapshot_identity'],
                    observation.get('price_basis') if field == 'close' else observation.get('dataset') + ':volume',
                    status=observation['qualification'], known=observation.get('retrieved_at'),
                    warnings=['DESCRIPTIVE_ONLY_SOURCE_MONETARY_UNIT_NOT_INFERRED'], unit=observation.get('price_unit') if field == 'close' else 'PROVIDER_REPORTED_VOLUME')
        dims = (record.get('current_research_decision_input') or {}).get('dimensions') or {}
        liq = dims.get('LIQUIDITY') or {}
        if (liq.get('research') or {}).get('state') == 'AVAILABLE':
            evidence['CURRENT_LIQUIDITY'] = binding('CURRENT_LIQUIDITY', ticker, session,
                current['source_artifacts'].get('liquidity_research'), 'CURRENT_SESSION_DESCRIPTIVE_COUNTERS_ONLY',
                status=liq['research']['disposition'], warnings=['NOT_EXECUTION_CAPACITY_NOT_ADTV_OR_ADV'])
        u = universe.get('records', {}).get(ticker) or {}
        if u.get('current_universe_status') == 'OFFICIAL_CURRENT_EXCHANGE_SECURITY' and u.get('exchange_or_market'):
            evidence['EXCHANGE_LISTING'] = binding('EXCHANGE_LISTING', ticker, session, universe['artifact_identity'],
                'CURRENT_EXCHANGE_MASTER_MEMBERSHIP_NOT_HISTORICAL_OR_PIT', status=u['qualification'], known=u.get('official_observed_at'),
                warnings=['ACTIVE_UNIVERSE_NOT_QUALIFIED', 'CURRENT_FACT_NOT_HISTORICAL_LISTING'])
        history = [o for o in source.get('observations') or [] if str(o.get('session', '')) < session]
        for feature, field in [('HISTORICAL_PRICE', 'close'), ('HISTORICAL_VOLUME', 'volume')]:
            if any(numeric(o.get(field), zero=field == 'volume') for o in history):
                evidence[feature] = binding(feature, ticker, session, snapshot['snapshot_identity'],
                    'ADJUSTED_RETROSPECTIVE_RESEARCH_HISTORY_NOT_RAW_OR_PIT' if field == 'close' else 'PROVIDER_REPORTED_HISTORICAL_VOLUME_NOT_CA_NORMALIZED',
                    fit='PARTIAL', status='RETAINED_RETROSPECTIVE_RESEARCH_SERIES', temporal='RETROSPECTIVE_RETRIEVAL',
                    warnings=['LATER_SERIES_NOT_T0_HISTORY', 'NOT_EXECUTION_AUTHORITY'])
        for lookback, window in risk_windows['records'][ticker].items():
            risk_counts[lookback][window['window_status']] += 1
        if risk_windows['records'][ticker]['20']['window_status'] == 'WINDOW_READY':
            evidence['VOLATILITY_CORRELATION'] = binding('VOLATILITY_CORRELATION', ticker, session,
                snapshot['snapshot_identity'], risk_windows['price_basis'], fit='PARTIAL', status='DESCRIPTIVE_VOLATILITY_WINDOW_READY',
                temporal='RETROSPECTIVE_RESEARCH_WINDOW', warnings=['VOLATILITY_INPUT_ONLY_CORRELATION_REQUIRES_QUALIFIED_COMMON_INTERSECTION', 'NOT_PORTFOLIO_VOLATILITY'])
        condition = (record.get('invalidation') or {}).get('condition') or {}
        level = (record.get('invalidation') or {}).get('invalidation_level')
        if condition.get('status') == 'MACHINE_EVALUABLE' and numeric(level):
            machine_invalidation += 1
            evidence['INVALIDATION'] = binding('INVALIDATION', ticker, session, condition['condition_identity'],
                condition.get('source_method'), status='MACHINE_EVALUABLE', warnings=['RESEARCH_BOUNDARY_NOT_STOP_ORDER'])
            if numeric(observation.get('close')) and level < observation['close']:
                numeric_denominator += 1
        scopes.extend(rows_for(evidence, ticker, session, current_scope=True))
        after = authority.attach_current_readiness(record)
        after_records[ticker] = after
        deltas['posture_changes'] += after['research_action_posture'] != record['research_action_posture']
        deltas['decision_identity_changes'] += integrated.decision_identity(after) != integrated.decision_identity(record)
        deltas['product_record_changes'] += stable_id(after) != stable_id(record)
        # Strip exactly the two documented additive fields. No other change is permitted.
        stripped = copy.deepcopy(after)
        stripped['portfolio_context'].pop('authority_readiness')
        if isinstance((stripped.get('evidence_axes') or {}).get('PORTFOLIO_FIT'), dict):
            stripped['evidence_axes']['PORTFOLIO_FIT'].pop('authority_readiness', None)
        deltas['unexplained_changes'] += stripped != record
    after_product = dict(current, records=after_records)
    product_before = integrated.content_identity(current)
    product_after = integrated.content_identity(after_product)
    del after_product, after_records

    # Independent older official liquidity window: never reused as current October 1.
    official = inputs.load('official_liquidity')
    older_liquidity = defaultdict(Counter)
    for ticker, record in sorted(official['records'].items()):
        at = official['resolved_completed_session']
        evidence = {}
        for feature, original, metric in [('CURRENT_LIQUIDITY', 'CURRENT_SESSION_LIQUIDITY_RESEARCH', None),
                                           ('ADTV', 'ADTV_RESEARCH', 'value_vnd'), ('ADV', 'ADV_VOLUME_RESEARCH', 'volume_shares')]:
            fit = record['fitness'][original]['state']
            evidence[feature] = binding(feature, ticker, at, official['artifact_identity'],
                'OFFICIAL_MATCHED_ALL_AS_TRADED_NOT_CA_NORMALIZED', fit=fit, status=fit,
                temporal='RETROSPECTIVE_RETRIEVAL_OF_OFFICIAL_POST_SESSION_PUBLICATION', metric=metric, ca_normalized=False,
                reason_codes=[record['fitness'][original].get('reason')] if fit == 'PARTIAL' else [])
            row = authority.authority_row(feature=feature, use_case='CURRENT_RESEARCH', ticker=ticker, session=at, evidence=evidence[feature])
            emit(row)
            older_liquidity[feature][fit] += 1
        envelope = capacity.build_envelope(ticker=ticker, session=at, official_liquidity_record=record, policy=capacity.canonical_unbound_policy())
        older_liquidity['CAPACITY_RESEARCH'][envelope['state']] += 1

    # Every retained snapshot row is evaluated, retaining each receipt's scope.
    snapshot_summary = defaultdict(Counter)
    historical_sessions = set()
    historical_scopes = set()
    stores = [('dnse_snapshots', None), ('hose_snapshots', None)]
    stores += [(e['id'], inputs.load(e['id'])['records']) for e in inputs.entries if e.get('kind') == 'prospective_session_manifest']
    for name, bound_records in stores:
        with inputs.paths[name].open(encoding='utf-8-sig') if bound_records is None else __import__('contextlib').nullcontext(bound_records) as handle:
            for line in handle:
                r = json.loads(line) if isinstance(line, str) else line
                ticker, at = r['instrument']['ticker'], r['trading_session']
                known = r['acquisition']['knowledge_available_at_utc']
                historical_sessions.add(at)
                historical_scopes.add((ticker, at))
                allowed = r['qualification']['allowed_uses']
                summary = snapshot_summary[name]
                summary['retained_rows'] += 1
                summary['prospective_as_known'] += 'PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE' in allowed
                summary['scoped_prospective_raw'] += 'PROSPECTIVE_RAW_AS_TRADED_PRICE' in allowed
                summary[r['qualification']['state']] += 1
                summary['historical_raw_allowed'] += 'HISTORICAL_RAW_AS_TRADED_PRICE' in allowed
                summary['pit_backtest_allowed'] += 'PIT_BACKTEST_ELIGIBILITY' in allowed
                summary['execution_replay_allowed'] += 'EXECUTION_REPLAY_ELIGIBILITY' in allowed
                e = binding('RAW_AS_TRADED', ticker, at, r['snapshot_identity'], stable_id(r['basis']),
                    fit='ELIGIBLE' if 'PROSPECTIVE_RAW_AS_TRADED_PRICE' in allowed else 'BLOCKED', status=r['qualification']['state'],
                    temporal=r['acquisition']['capture_timing'], known=known,
                    raw_basis_qualified='PROSPECTIVE_RAW_AS_TRADED_PRICE' in allowed,
                    evidence_kind='RETAINED_PRICE_OBSERVATION', source_allowed_uses=allowed,
                    capture_timing=r['acquisition']['capture_timing'])
                emit(authority.authority_row(feature='RAW_AS_TRADED', use_case='CURRENT_RESEARCH', ticker=ticker, session=at, evidence=e))
                # Use the historical session's close cutoff, not a later receipt/correction.
                for use in ('HISTORICAL_PIT_ANALYSIS', 'BACKTEST', 'EXECUTION_REPLAY'):
                    gate = authority.use_case_readiness(use_case=use, ticker=ticker, session=at, evidence={'RAW_AS_TRADED': e},
                        knowledge_cutoff=at + 'T15:00:00+07:00')
                    snapshot_summary[use][gate['state']] += 1
                    for row in gate['required_rows']: emit(row)

    # Retained newer price captures are selected by an exact source manifest, no directory scan.
    captures = {}
    for entry in sorted(inputs.entries, key=lambda e: e['id']):
        if entry.get('kind') != 'price_capture': continue
        s = inputs.load(entry['id'])
        at = s['resolved_completed_session']
        counts = Counter()
        sessions = set()
        for ticker, record in sorted(s['records'].items()):
            retained = [o for o in record.get('observations') or [] if o.get('session') and o['session'] <= at]
            # Scoped window rows cover every retained historical session while avoiding
            # millions of duplicated vintage rows. The producer denies stronger uses
            # for the whole series; no window is rewritten as a T0 series.
            for feature in ('HISTORICAL_PRICE', 'HISTORICAL_VOLUME'):
                e = binding(feature, ticker, at, s['snapshot_identity'],
                    'RETAINED_PROVIDER_SERIES_NOT_HISTORICAL_PIT_OR_CA_NORMALIZED', fit='PARTIAL',
                    status=record.get('status', 'UNKNOWN'), temporal='RETROSPECTIVE_RETRIEVAL',
                    known=max((o.get('retrieved_at') or '' for o in retained), default=None),
                    session_scope=sorted({o['session'] for o in retained}),
                    warnings=['WINDOW_SCOPE_ALL_RETAINED_SESSIONS_EXPLICITLY_DENIED_STRONGER_USE'])
                for use in sorted(authority.HISTORICAL_USES):
                    emit(authority.authority_row(feature=feature, use_case=use, ticker=ticker, session=at,
                        evidence=e, knowledge_cutoff=at + 'T15:00:00+07:00'))
            for o in record.get('observations') or []:
                if not o.get('session'): continue
                sessions.add(o['session'])
                historical_scopes.add((ticker, o['session']))
                counts['retained_price_rows'] += numeric(o.get('close'))
                counts['retained_volume_rows'] += numeric(o.get('volume'), zero=True)
                counts['exact_target_prices'] += o['session'] == at and numeric(o.get('close'))
                counts['basis:' + str(o.get('price_basis'))] += 1
                # This artifact explicitly denies historical PIT/execution authority.
                counts['pit_backtest_qualified'] += bool(s.get('pit_backtest_eligible'))
        historical_sessions.update(sessions)
        captures[entry['id']] = {'target_session': at, 'retained_session_count': len(sessions), 'counts': dict(sorted(counts.items())),
                                'source_identity': s['snapshot_identity'], 'temporal_use': 'RETROSPECTIVE_RESEARCH_SERIES_WITH_EXACT_SESSION_RECEIPTS_ONLY',
                                'stronger_use_blockers': ['ADJUSTED_RETROSPECTIVE_NOT_HISTORICAL_RAW', 'CA_FACTOR_LINEAGE_AND_PIT_UNIVERSE_NOT_QUALIFIED']}

    # Real CA outcome is inspected; synthetic mechanics never enter real authority counts.
    ca = inputs.load('real_ca_outcome')
    factor_status = Counter(e['factor_chain']['status'] for e in ca['event_outcomes'].values())
    ca_reasons = Counter(c for e in ca['event_outcomes'].values() for c in e['factor_chain'].get('reason_codes') or [])
    upstream_pit = inputs.load('raw_pit_authority')
    gap = inputs.load('factor_gap')
    eligible_pit = sum(v.get('PIT_USABLE', 0) for k,v in snapshot_summary.items() if k == 'HISTORICAL_PIT_ANALYSIS')
    eligible_replay = snapshot_summary['EXECUTION_REPLAY'].get('EXECUTION_USABLE', 0)
    dossier = authority.promotion_dossier(scopes)
    sizing = governed_research_sizing()
    portfolio = governed_portfolio_research(portfolio=None, contexts={})
    if any(deltas[k] for k in ('posture_changes', 'decision_identity_changes', 'unexplained_changes')):
        raise ValueError('ADDITIVE_INTEGRATION_INVARIANT_FAILED')
    inputs.unchanged()
    body = {'contract_version': 'portfolio_pit_execution_retained_acceptance/v1', 'stack_base': '938641cff02095f10db1658ad3134d71f871fcec',
        'session': session, 'current_denominator': 1683, 'source_file_count': len(inputs.hashes), 'source_hashes': dict(sorted(inputs.hashes.items())),
        'current_feature_coverage': {f: dict(sorted(feature_counts[f].items())) for f in authority.FEATURES},
        'original_status_distributions': {f: dict(sorted(source_status_counts[f].items())) for f in authority.FEATURES},
        'current_use_case_coverage': {u: dict(sorted(use_counts[u].items())) for u in authority.USE_CASES},
        'current_research_readiness_scope': 'CURRENT_PRICE_VOLUME_ONLY_NOT_GLOBAL_TICKER_REJECTION_OR_ACTION_POSTURE',
        'current_official_liquidity_component': handoff['enrichment_component_status']['official_liquidity_component'],
        'older_official_liquidity_session': official['resolved_completed_session'],
        'older_official_liquidity_coverage': {f: dict(sorted(c.items())) for f,c in sorted(older_liquidity.items())},
        'sizing_coverage': {'theoretical_risk_size_research': 0, 'execution_eligible_size': 0, 'canonical_capital_inputs': 0,
                           'machine_evaluable_invalidation': machine_invalidation, 'numeric_positive_long_risk_denominator_same_source_units': numeric_denominator,
                           'governed_comparable_monetary_risk_denominator': 0, 'runtime_sizing_readiness': sizing['theoretical_risk_size_research'],
                           'portfolio_runtime': portfolio},
        'risk_window_coverage': {k: dict(sorted(v.items())) for k,v in sorted(risk_counts.items())},
        'risk_window_method': 'EXISTING_DESCRIPTIVE_ADJUSTED_RETROSPECTIVE_PRICE_WINDOW_ENGINE_NOT_PIT_OR_PORTFOLIO_VOLATILITY',
        'retained_snapshot_coverage': {k: dict(sorted(v.items())) for k,v in sorted(snapshot_summary.items())},
        'historical_inventory': {'retained_sessions': sorted(historical_sessions), 'distinct_ticker_sessions': len(historical_scopes),
                                'price_captures': captures, 'corporate_action_real_outcome_identity': ca['artifact_identity'],
                                'corporate_action_terminal_disposition': ca['terminal_disposition'], 'factor_source_status_counts': dict(factor_status),
                                'ca_safe_pit_ticker_sessions': eligible_pit, 'pit_replay_eligible_ticker_sessions': eligible_replay,
                                'backtest_replay_eligible': eligible_replay, 'gross_return_capable': eligible_replay, 'net_return_capable': eligible_replay,
                                'ca_blocker_reason_codes': dict(ca_reasons), 'prior_factor_gap_identity': gap['artifact_identity'],
                                'existing_upstream_authority_matrix': upstream_pit['authority_matrix']['after'],
                                'reopen_gates': ['OFFICIAL_TERMS_EXPLICIT_EX_DATE_EXECUTED_LIFECYCLE_AND_QUALIFIED_KNOWLEDGE_CUTOFF',
                                    'PIT_UNIVERSE_LISTING_AND_FEATURE_VINTAGES', 'USE_QUALIFIED_RAW_AND_LIQUIDITY_WINDOWS',
                                    'EXPLICIT_CAPITAL_RISK_CONCENTRATION_AND_CAPACITY_POLICY', 'GOVERNED_LOT_BANDS_COST_IMPACT_AND_LEVERAGE_CONSTRAINTS']},
        'authority_matrix': {'row_count': row_count, 'identity_chain_sha256': row_chain.hexdigest()},
        'promotion_dossier': dossier, 'top_blocker_reason_codes': dict(blockers.most_common(12)),
        'before_after': {**dict(deltas), 'product_identity_before': product_before['artifact_identity'], 'product_identity_after': product_after['artifact_identity'],
                         'product_identity_change_reason': 'EXISTING_CONTENT_HASH_CONTRACT_TWO_ADDITIVE_NON_VOTING_PORTFOLIO_FIT_FIELDS',
                         'policy_changes': 0, 'evidence_class_changes': 0},
        'invariants': {'fabricated_portfolio_assumptions': 0, 'fabricated_execution_constraints': 0, 'future_information_leakage': 0,
                       'live_orders': 0, 'production_writes': 0, 'authority_promotions': 0, 'source_bytes_unchanged': True},
        'authority_effect': 'NONE', 'terminal_disposition': 'CAPABILITY_COMPLETE / AUTHORITY_PROMOTION_PENDING_EVIDENCE_OR_OWNER_APPROVAL'}
    return {**body, 'acceptance_identity': 'portfolio_pit_execution_retained_acceptance:' + stable_id(body)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    for alias in ('primary', 'raw_pit', 'liquidity'):
        parser.add_argument('--' + alias.replace('_', '-') + '-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--verify-determinism', action='store_true')
    parser.add_argument('--emit-rows', action='store_true')
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    if not destination.is_relative_to((ROOT / '.stocklookup/scratch').resolve()):
        raise ValueError('OUTPUT_MUST_BE_WORKTREE_SCRATCH_NOT_RUNTIME_OR_SOURCE')
    roots = {a: getattr(args, a + '_root') for a in ('primary', 'raw_pit', 'liquidity')}
    if any(destination.is_relative_to(root.resolve()) for root in roots.values()):
        raise ValueError('OUTPUT_CANNOT_BE_UNDER_SOURCE_ROOT')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    inputs = Inputs(manifest, roots)
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / 'authority_matrix.ndjson').open('w', encoding='utf-8') if args.emit_rows else __import__('contextlib').nullcontext(None) as writer:
        result = build_acceptance(inputs, row_writer=writer)
    if args.verify_determinism:
        reversed_manifest = dict(manifest, inputs=list(reversed(manifest['inputs'])))
        replay = build_acceptance(Inputs(reversed_manifest, roots))
        if result != replay: raise ValueError('NON_DETERMINISTIC_ACCEPTANCE')
    result['deterministic_replay'] = 'PASS' if args.verify_determinism else 'NOT_RUN'
    (destination / 'acceptance.json').write_text(json.dumps(result, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    (destination / 'promotion_dossier.json').write_text(json.dumps(result['promotion_dossier'], sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('acceptance_identity', 'current_denominator', 'current_use_case_coverage', 'sizing_coverage', 'authority_matrix', 'before_after', 'authority_effect')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
