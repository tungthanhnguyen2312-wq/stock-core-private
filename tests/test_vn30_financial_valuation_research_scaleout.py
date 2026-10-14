from copy import deepcopy
from decimal import Decimal

import pytest
from tests.financial_source_fixture import synthetic_retained_source_io  # noqa: F401

from stocklookup_core.financial import financial_analysis_engine_v2 as engine
from stocklookup_core.valuation import current_research_valuation_context as valuation
import canonical_daily_financial_v2_materialization as material
from tools.replay_vn30_financial_valuation_research_scaleout import validate_source_binding
from tests.test_current_financial_valuation_input_unlock import fact, raw, evaluate
from tests.test_financial_analysis_engine_v2 import row


def source_rows(record=None, income_value=10):
    source = evaluate([fact('net_income', income_value), fact('shareholders_equity', 200)], record)
    # Numeric-owner fixture: the shared fixture factory generates a separate synthetic
    # document per metric. Model the already-admitted same-filing envelope explicitly.
    # Real co-filing/source admission is checked by the retained replay, not these bytes.
    methods = source['methods']
    methods[valuation.PB_OFFICIAL_RESEARCH]['source_fact']['document_sha256'] = methods[valuation.PE_REPORTED_PERIOD]['source_fact']['document_sha256']
    return source


def projection(source=None, feature=None, session='2026-10-12'):
    record = engine.build_ticker_context('PNJ', [], issuer_type='corporate', source_identities={})
    if feature:
        record['features']['same_provider_roa_avg_assets'] = feature
    return valuation.build_metric_research_context(rows={'PNJ': source or source_rows()},
        engine_artifact={'artifact_identity': 'engine:test', 'records': {'PNJ': record}}, decision_session=session)


def test_reported_roe_reuses_ratio_owner_and_preserves_source_inputs(monkeypatch):
    source = source_rows()
    frozen = deepcopy(source)
    original = engine._ratio
    calls = []
    def observe(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(engine, '_ratio', observe)
    result = projection(source)['records']['PNJ']['metrics'][valuation.ROE_REPORTED_PERIOD]
    assert result['value'] == float(Decimal(10) / Decimal(200))
    assert result['fitness'] == 'RESEARCH_PROXY'
    assert result['period_identity'] == ['2026-H1', '2026-H1']
    assert result['denominator_method'] == 'END_PERIOD_BALANCE'
    assert result['currency'] == 'VND' and result['scale'] == 'units'
    assert result['share_basis'] == 'NOT_USED'
    assert result['operand_lineage']['net_income'] == source['methods'][valuation.PE_REPORTED_PERIOD]
    assert result['knowledge_time'] and result['observation_time']
    assert 'REPORTED_DURATION_NOT_ANNUALIZED_NOT_TTM' in result['limitations']
    assert sum(call[0] == valuation.ROE_REPORTED_PERIOD for call in calls) == 1 and source == frozen


@pytest.mark.parametrize('change,code', [
    ({'denominator_authority': 'UNAVAILABLE'}, 'OFFICIAL_RETURN_OPERAND_NOT_ADMITTED'),
    ({'denominator_metric': 'total_assets'}, 'OFFICIAL_RETURN_METRIC_IDENTITY_INCOMPATIBLE'),
    ({'statement_scope': 'separate'}, 'OFFICIAL_RETURN_SOURCE_SCOPE_CURRENCY_SCALE_INCOMPATIBLE'),
    ({'knowledge_cutoff': '2026-10-11T15:00:00+07:00'}, 'OFFICIAL_RETURN_SOURCE_SCOPE_CURRENCY_SCALE_INCOMPATIBLE'),
    ({'denominator_value_vnd': 0}, 'NON_POSITIVE_ENDING_EQUITY_RETURN_NOT_MEANINGFUL'),
    ({'denominator_value_vnd': -100}, 'NON_POSITIVE_ENDING_EQUITY_RETURN_NOT_MEANINGFUL'),
    ({'denominator_value_vnd': float('nan')}, 'OFFICIAL_RETURN_NONFINITE_OR_MISSING_OPERAND'),
])
def test_official_return_operand_fail_closed(change, code):
    methods = source_rows()['methods']
    income, balance = methods[valuation.PE_REPORTED_PERIOD], deepcopy(methods[valuation.PB_OFFICIAL_RESEARCH])
    balance.update(change)
    result = engine.reported_period_eop_return('ROE', income=income, balance=balance)
    assert result['value'] is None and result['fitness'] == 'BLOCKED_BY_EVIDENCE'
    assert result['reason_codes'] == [code]


@pytest.mark.parametrize('field,value', [('document_sha256', 'different-filing'), ('currency', 'USD'),
                                      ('unit_scale', 1000000), ('already_normalized', False)])
def test_join_does_not_mix_filing_currency_or_scale(field, value):
    methods = source_rows()['methods']
    income, balance = methods[valuation.PE_REPORTED_PERIOD], deepcopy(methods[valuation.PB_OFFICIAL_RESEARCH])
    balance['source_fact'][field] = value
    result = engine.reported_period_eop_return('ROE', income=income, balance=balance)
    assert result['value'] is None
    assert result['reason_codes'] == ['OFFICIAL_RETURN_SOURCE_SCOPE_CURRENCY_SCALE_INCOMPATIBLE']


def test_duration_cannot_join_another_ending_instant_or_average_by_assumption():
    methods = source_rows()['methods']
    balance = deepcopy(methods[valuation.PB_OFFICIAL_RESEARCH])
    balance['reporting_basis']['period_end'] = '2025-12-31'
    result = engine.reported_period_eop_return('ROE', income=methods[valuation.PE_REPORTED_PERIOD], balance=balance)
    assert result['reason_codes'] == ['OFFICIAL_RETURN_DURATION_ENDING_BALANCE_MISMATCH']
    metrics = projection()['records']['PNJ']['metrics']
    assert metrics['ROE_AVERAGE_BALANCE']['fitness'] == 'BLOCKED_BY_EVIDENCE'
    assert metrics[valuation.ROE_REPORTED_PERIOD]['fitness'] == 'RESEARCH_PROXY'
    assert metrics[valuation.PE_TTM]['value'] is None


def test_missing_shares_block_multiples_but_not_share_independent_return():
    record = raw()
    record['share_basis_input'] = {}
    record['metrics'] = {}
    source = source_rows(record)
    metrics = projection(source)['records']['PNJ']['metrics']
    assert metrics[valuation.PE_REPORTED_PERIOD]['fitness'] == 'BLOCKED_BY_EVIDENCE'
    assert metrics[valuation.PB_OFFICIAL_RESEARCH]['fitness'] == 'BLOCKED_BY_EVIDENCE'
    assert metrics[valuation.ROE_REPORTED_PERIOD]['value'] == pytest.approx(0.05)
    assert metrics[valuation.ROE_REPORTED_PERIOD]['fitness'] == 'RESEARCH_PROXY'


def test_negative_income_is_reported_return_and_not_a_positive_pe():
    source = source_rows(income_value=-10)
    metrics = projection(source)['records']['PNJ']['metrics']
    assert metrics[valuation.ROE_REPORTED_PERIOD]['value'] == pytest.approx(-0.05)
    assert metrics[valuation.PE_REPORTED_PERIOD]['value'] is None


@pytest.mark.parametrize('entity', ['bank', 'securities', 'insurance', 'unknown'])
def test_specialist_applicability_cannot_alias_corporate_return(entity):
    source = source_rows()
    source['entity_class'] = entity
    metrics = projection(source)['records']['PNJ']['metrics']
    for mid in (*valuation.RETURN_FEATURES, valuation.ROE_REPORTED_PERIOD):
        assert metrics[mid]['fitness'] == 'NOT_APPLICABLE'
        assert metrics[mid]['value'] is None


def test_average_balance_method_and_stale_inputs_are_not_relabelled_current():
    feature = engine.build_ticker_context('PNJ', [row('net_income', 10, '2024-Q2'),
        row('total_assets', 100, '2024-Q1', semantic=engine.PIT),
        row('total_assets', 300, '2024-Q2', semantic=engine.PIT)],
        issuer_type='corporate', source_identities={})['features']['same_provider_roa_avg_assets']
    result = projection(feature=feature)['records']['PNJ']['metrics']['ROA_AVERAGE_BALANCE']
    assert result['value'] == feature['value'] == pytest.approx(0.05)
    assert result['producer_fitness'] == 'READY'
    assert result['fitness'] == 'STALE_BUT_RESEARCH_USABLE'
    assert result['denominator_method'] == 'AVERAGE_PERIOD_BOUNDARIES'
    assert not result['freshness']['rewritten_as_current']


def test_future_feature_fails_closed_without_changing_engine():
    feature = {'fitness': 'READY', 'value': 0.1, 'method': 'future', 'period_identity': ['2027-Q1']}
    original = deepcopy(feature)
    result = projection(feature=feature)['records']['PNJ']['metrics']['ROA_AVERAGE_BALANCE']
    assert result['fitness'] == 'BLOCKED_BY_EVIDENCE' and result['value'] is None
    assert 'FINANCIAL_PERIOD_AFTER_DECISION_SESSION' in result['reason_codes']
    assert feature == original


def test_future_admission_blocks_reported_return_and_peer_eligibility():
    source = source_rows()
    for mid in (valuation.PE_REPORTED_PERIOD, valuation.PB_OFFICIAL_RESEARCH):
        source['methods'][mid]['knowledge_cutoff'] = '2026-10-13T10:00:00+07:00'
    result = projection(source, session='2026-10-12')['records']['PNJ']['metrics'][valuation.ROE_REPORTED_PERIOD]
    assert result['fitness'] == 'BLOCKED_BY_EVIDENCE' and result['value'] is None
    assert 'OPERAND_ADMISSION_AFTER_DECISION_SESSION' in result['reason_codes']
    assert result['peer_context']['status'] != 'READY_RESEARCH_ONLY'


def test_replay_requires_same_session_and_exact_raw_source_identity():
    evaluated = {'source_valuation_identity': 'raw:one'}
    raw_artifact = {'artifact_identity': 'raw:one', 'valuation_session': '2026-10-13'}
    validate_source_binding(evaluated, raw_artifact, '2026-10-13')
    with pytest.raises(ValueError, match='VALUATION_SESSION_MISMATCH'):
        validate_source_binding(evaluated, raw_artifact, '2026-10-12')
    with pytest.raises(ValueError, match='VALUATION_SOURCE_IDENTITY_MISMATCH'):
        validate_source_binding(evaluated, {**raw_artifact, 'artifact_identity': 'raw:other'}, '2026-10-13')


def test_cross_provider_unknown_scale_stays_restricted_proxy_and_not_comparable():
    record = engine.build_ticker_context('PNJ', [row('net_income', 10),
        row('total_assets', 100, semantic=engine.PIT, provider='VCI')],
        issuer_type='corporate', source_identities={})
    result = valuation.build_metric_research_context(rows={'PNJ': source_rows()},
        engine_artifact={'records': {'PNJ': record}}, decision_session='2026-10-12')['records']['PNJ']['metrics']['ROA_CROSS_PROVIDER_PROXY']
    assert result['value'] == 0.1 and result['fitness'] == 'RESEARCH_PROXY'
    assert result['currency'] is None and result['scale'] is None
    assert 'CROSS_PROVIDER_UNRESOLVED_SCALE' in result['reason_codes']
    assert result['peer_context']['status'] == 'NOT_COMPARABLE'


def test_same_method_peer_distribution_and_deterministic_identity():
    source = source_rows()
    inputs = {f'T{i}': {**deepcopy(source), 'ticker': f'T{i}'} for i in range(5)}
    first = valuation.build_metric_research_context(rows=inputs, engine_artifact={'records': {}}, decision_session='2026-10-12')
    second = valuation.build_metric_research_context(rows=dict(reversed(list(inputs.items()))), engine_artifact={'records': {}}, decision_session='2026-10-12')
    assert first == second
    peer = first['records']['T0']['metrics'][valuation.ROE_REPORTED_PERIOD]['peer_context']
    assert peer['status'] == 'READY_RESEARCH_ONLY' and peer['peer_count'] == 5
    assert peer['peer_median'] == pytest.approx(0.05)
    inputs['T0']['methods'][valuation.PE_REPORTED_PERIOD]['reporting_basis']['period_start'] = '2026-04-01'
    changed = valuation.build_metric_research_context(rows=inputs, engine_artifact={'records': {}}, decision_session='2026-10-12')
    assert changed['artifact_identity'] != first['artifact_identity']
    assert changed['records']['T1']['metrics'][valuation.ROE_REPORTED_PERIOD]['peer_context']['status'] == 'INSUFFICIENT_PEER_COUNT'


def test_opt_in_canonical_extension_preserves_default_artifact_and_every_old_field(monkeypatch):
    monkeypatch.setattr(material, '_official_equity_overlay', lambda root: [])
    args = dict(engine_artifact={'records': {}, 'artifact_identity': 'engine:test'},
        raw_valuation_artifact={'records': {'PNJ': raw()}, 'artifact_identity': 'valuation:test'},
        product_tickers=['PNJ'], requested_at='2026-10-12T16:00:00+07:00', decision_session='2026-10-12',
        official_financial_facts=[fact('net_income', 10), fact('shareholders_equity', 200)])
    before = material.build_evaluated_valuation_artifact(**args)
    after = material.build_evaluated_valuation_artifact(**args, include_metric_research=True)
    assert 'metric_research_context' not in before
    assert before['records'] == after['records']
    assert {k:v for k,v in after.items() if k not in ('metric_research_context','artifact_identity','artifact_sha256')} == {
        k:v for k,v in before.items() if k not in ('artifact_identity','artifact_sha256')}
    assert material._identity(before)['artifact_identity'] == before['artifact_identity']
    assert material._identity(after)['artifact_identity'] == after['artifact_identity']
    assert after['metric_research_context']['source_valuation_identity'] == before['artifact_identity']
