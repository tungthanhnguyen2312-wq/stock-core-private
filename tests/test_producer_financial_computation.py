"""Exact accepted-source financial outputs and bounded computation regressions."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from stocklookup_core.financial import financial_analysis_engine_v2 as engine
from stocklookup_core.financial import market_wide_fundamental_feature_store as store
from stocklookup_core.financial import market_wide_fundamental_features as quarterly
from stocklookup_core.financial import fundamental_cross_sectional_scoring as scoring
from stocklookup_core.financial import fundamental_market_opportunity_ranking as ranking
from stocklookup_core.valuation import current_research_valuation_context as valuation


METRICS = ('revenue', 'net_income', 'gross_profit', 'profit_before_tax', 'operating_cash_flow',
           'total_assets', 'shareholders_equity', 'cash_and_cash_equivalents',
           'short_term_borrowings', 'long_term_borrowings', 'current_assets', 'current_liabilities')

def _fixture_rows(quarters=40):
    result = []
    for quarter in range(quarters):
        period = f'{2016 + quarter // 4}-Q{quarter % 4 + 1}'
        for metric_index, metric in enumerate(METRICS):
            flow = metric_index < 5
            result.append(dict(ticker='AAA', canonical_metric=metric, reported_value=(quarter + 5) * (metric_index + 2),
                native_period_label=period, period_end=period,
                period_semantic_state='STANDALONE_QUARTER' if flow else 'POINT_IN_TIME_BALANCE_SHEET',
                statement_family='income_statement' if metric_index < 4 else 'cash_flow' if flow else 'balance_sheet',
                source_status='provider_reported', lineage_complete=True, source_conflicts=[],
                statement_scope='consolidated', normalized_candidate_unit={'currency':'VND', 'scale':'units'},
                metadata_missing={'unit':False}, source_lineage={'provider':'KBS', 'source_file':'issuer-native',
                'source_sha256':'retained-sha', 'fact_id':f'{metric}-{period}', 'raw_item_id':metric}))
    return result

def _fixture_scoring_base(count=1507):
    names = ('net_margin_period', 'roa_eop_proxy', 'roe_eop_proxy', 'asset_turnover_eop_proxy',
             'total_assets_same_period_yoy', 'shareholders_equity_same_period_yoy',
             'revenue_same_period_yoy', 'net_income_same_period_yoy')
    return {'operational_proxy': {'records': {f'T{i:04}': {'entity_type':'corporate',
        'fundamental_features': {name:{'research_eligible':i % 17 != 0, 'value':(i % 43 - 20) / (j + 1)}
                                for j, name in enumerate(names)},
        'tier_counts':{'OPERATIONAL_PROXY':1}, 'facts':[{'source':'retained'}]}
        for i in range(count)}}}

def _fixture_legacy_record():
    return {'entity_type':'corporate', 'facts':[
        {'reporting_period':r['native_period_label'], 'provider_raw_value':r['reported_value'],
         'fitness_for_use':{'research_eligible':True}, 'provider':'KBS', 'statement_scope':'consolidated',
         'canonical_metric':r['canonical_metric'], 'evidence_tier':'OPERATIONAL_PROXY'} for r in _fixture_rows(8)]}

def _fixture_peer_rows(count=1507):
    return {f'T{i:04}': {'entity_class':'corporate', 'usable_relative_method_count':1,
        'methods': {'P/E': {'method_id':'P/E', 'applicability':'APPLICABLE', 'status':'READY',
        'value':float(i % 43 + 1), 'share_basis':'PROVIDER_REFERENCE', 'period_basis':'2025',
        'statement_scope':'consolidated'}}} for i in range(count)}

def _fixture_cases():
    base = _fixture_rows(8)
    duplicate = copy.deepcopy(base)
    duplicate.append(copy.deepcopy(duplicate[-1]))
    duplicate[-1]['source_lineage']['fact_id'] = '000-equal'
    conflict = copy.deepcopy(duplicate)
    conflict[-1]['reported_value'] += 1
    mixed = copy.deepcopy(base)
    for i, row in enumerate(mixed):
        if i % 7 == 0: row['lineage_complete'] = 1
        if i % 11 == 0: row['source_lineage']['source_sha256'] = None
        if i % 13 == 0: row['normalized_candidate_unit']['currency'] = 'USD'
        if i % 19 == 0: row['period_semantic_state'] = 'UNKNOWN_DURATION'
        if i % 23 == 0: row['source_conflicts'] = ['CONFLICT']
    return {'engine': [{'rows':r, 'entity':entity} for r in (base, list(reversed(base)), duplicate, conflict, mixed)
                       for entity in ('corporate', 'bank', 'securities')],
            'store': [base, list(reversed(base)), duplicate, conflict, mixed],
            'quarterly': [_fixture_legacy_record(), {'entity_type':'bank', 'facts':[]}],
            'scoring': [_fixture_scoring_base(31), _fixture_scoring_base(0)],
            'peers': [_fixture_peer_rows(31), _fixture_peer_rows(2)]}

def _fixture_inputs():
    inputs = _fixture_cases()
    for kind, names in [('fundamental_peers', valuation.FUNDAMENTAL_PEER_FEATURES),
                        ('engine_peers', valuation.ENGINE_PEER_FEATURES)]:
        inputs[kind] = []
        for count in (31, 2):
            records = {}
            for i in range(count):
                features = {name: {'status':'READY_RESEARCH_PROXY', 'fitness':'READY', 'value':float(i % 7 - 3),
                    'method':'qualified-native-v1', 'compatibility_class':'SAME_NATIVE_SERIES_RESEARCH_COMPATIBLE',
                    'input_periods':['2025-Q4'], 'period_identity':['2025-Q4'], 'scope':['consolidated'],
                    'currency':'VND', 'scale':'units', 'period_semantics':['STANDALONE_QUARTER'],
                    'provider_source_provenance':[{'provider':'KBS'}]} for name in names}
                records[f'T{i:04}'] = {'issuer_type':'corporate', 'entity_type':'corporate', 'features':features}
            inputs[kind].append(records)
    return inputs

BASELINE = json.loads((Path(__file__).parent / 'fixtures/producer_financial_computation_baseline.json').read_text(encoding='utf-8'))
BASELINE['inputs'] = _fixture_inputs()

def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

def _evaluate(kind, value):
    if kind == 'engine':
        return engine.build_ticker_context('AAA', value['rows'], issuer_type=value['entity'], source_identities={'retained':'same'})
    if kind == 'store':
        return store.build_ticker_record('AAA', value, {'AAA':'corporate'})
    if kind == 'quarterly':
        return quarterly.build_ticker_features(value)
    if kind == 'scoring':
        return scoring.build_artifact(base=value)
    if kind == 'ranking':
        return ranking.build_artifact(fundamental=scoring.build_artifact(base=value), market={'session':'2026-10-14'},
                                      tactical={'session':'2026-10-14'}, valuation={})
    if kind == 'peers':
        return valuation.attach_peer_relative(value)
    if kind == 'fundamental_peers':
        return valuation.attach_fundamental_peers(value, {})
    return valuation.attach_engine_fundamental_peers(value)

CASES = [(kind, i) for kind, outputs in BASELINE['expected_output_sha256'].items() for i in range(len(outputs))]

@pytest.mark.parametrize('kind,index', CASES)
def test_outputs_match_exact_accepted_source(kind, index):
    input_kind = 'scoring' if kind == 'ranking' else kind
    value = copy.deepcopy(BASELINE['inputs'][input_kind][index])
    original = copy.deepcopy(value)
    output = _evaluate(kind, value)
    assert _digest(output) == BASELINE['expected_output_sha256'][kind][index]
    # The valuation method join intentionally enriches its existing row objects.
    if kind != 'peers':
        assert value == original

def test_engine_qualifies_rows_in_two_passes_without_stale_cache(monkeypatch):
    rows = copy.deepcopy(BASELINE['inputs']['engine'][0]['rows'])
    calls = 0
    original = engine._row_usable
    def count(row, semantic=None):
        nonlocal calls
        calls += 1
        return original(row, semantic)
    monkeypatch.setattr(engine, '_row_usable', count)
    first = engine.build_ticker_context('AAA', rows, issuer_type='corporate', source_identities={})
    assert calls <= 2 * len(rows)
    for row in rows:
        if row['canonical_metric'] == 'revenue': row['reported_value'] *= 2
    second = engine.build_ticker_context('AAA', rows, issuer_type='corporate', source_identities={})
    assert first['features']['net_margin']['value'] != second['features']['net_margin']['value']

def test_store_qualifies_each_row_once_with_distinct_truthy_gate(monkeypatch):
    rows = copy.deepcopy(BASELINE['inputs']['store'][0])
    calls = 0
    original = store._usable
    def count(row, semantic=None):
        nonlocal calls
        calls += 1
        return original(row, semantic)
    monkeypatch.setattr(store, '_usable', count)
    store.build_ticker_record('AAA', rows, {'AAA':'corporate'})
    assert calls == len(rows)

@pytest.mark.parametrize('metric,semantic', [('revenue','UNKNOWN_DURATION'), ('unused_metric','STANDALONE_QUARTER')])
def test_unqueried_large_numeric_observation_keeps_blocked_context(metric, semantic):
    row = copy.deepcopy(BASELINE['inputs']['engine'][0]['rows'][0])
    row.update(canonical_metric=metric, period_semantic_state=semantic, reported_value=10 ** 400)
    result = engine.build_ticker_context('AAA', [row], issuer_type='corporate', source_identities={})
    assert result['features']['revenue_ttm']['fitness'] == 'BLOCKED_BY_EVIDENCE'
    assert result['current_research_ready'] is False
    assert result['pit_authority'] == 'NOT_GRANTED'

@pytest.mark.parametrize('values', [[-2.0,-0.0,0,2.0,2.0], [float('nan'),-1.0,1.0], [float('-inf'),0,float('inf')]])
def test_percentile_preparation_preserves_ties_and_nonfinite_comparisons(values):
    ordered, _, usable = valuation._peer_pool(values)
    for subject in values:
        expected = (sum(x < subject for x in values) + .5 * sum(x == subject for x in values)) / len(values)
        assert valuation._percentile(ordered, subject, ordered=usable) == expected

def test_scoring_and_ranking_nonfinite_pools_keep_original_comparison_semantics():
    base = copy.deepcopy(BASELINE['inputs']['scoring'][0])
    names = list(scoring.AXES['PROFITABILITY_QUALITY'])
    record = base['operational_proxy']['records']['T0001']
    record['fundamental_features'][names[0]]['value'] = float('nan')
    artifact = scoring.build_artifact(base=base)
    assert artifact['records']['T0001']['feature_percentiles'][names[0]] == 0
    assert artifact['authority_boundary']['authoritative_counts_before'] == artifact['authority_boundary']['authoritative_counts_after'] == 13
    assert artifact['authority_boundary']['valuation_promoted'] is False
    pool = [float('nan'),1.0,float('inf')]
    assert ranking._cohort_percentile(pool, 1.0) == 1 / 3

def test_active_quarterly_features_have_one_builder_and_retain_existing_labels():
    import ast
    tree = ast.parse(Path(quarterly.__file__).read_text(encoding='utf-8'))
    assert sum(isinstance(n, ast.FunctionDef) and n.name == 'build_ticker_features' for n in tree.body) == 1
    assert not hasattr(quarterly, '_annual')
    assert 'revenue_same_period_yoy' in quarterly.FEATURES
    assert 'revenue_cagr_5y' not in quarterly.FEATURES
    value = quarterly.build_ticker_features(BASELINE['inputs']['quarterly'][0])
    assert value['ttm']['status'] == 'BLOCKED_DURATION_UNKNOWN'
    assert value['piotroski_standard_score']['score'] is None


def test_fixture_recipe_reproduces_accepted_input_bytes():
    assert _digest(BASELINE['inputs']) == BASELINE['input_sha256']
