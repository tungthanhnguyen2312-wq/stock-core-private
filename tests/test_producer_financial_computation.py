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

BASELINE = json.loads((Path(__file__).parent / 'fixtures/producer_financial_computation_baseline.json').read_text(encoding='utf-8'))

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
