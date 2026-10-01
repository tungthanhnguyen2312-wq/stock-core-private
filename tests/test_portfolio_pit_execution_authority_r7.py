"""R7 synthetic adversarial cases; no actual holdings, provider or live execution."""
import copy
import socket

import pytest
import raw_pit_authority_matrix as a
import portfolio_aware_decision as p
import current_portfolio_risk_envelope as portfolio
import integrated_investment_decision_product as integrated
import vnm_shadow_backtest as replay
from current_portfolio_risk_research import qualified_window_readiness
from tools.run_portfolio_pit_execution_acceptance import Inputs

T0 = '2026-06-30'
CUTOFF = T0 + 'T16:00:00+07:00'


def evidence(feature, use='EXECUTION_REPLAY', session=T0):
    return dict(feature=feature, ticker='VNM', session=session, source_identity='synthetic:source:' + feature,
                basis_identity='synthetic:basis:' + feature, temporal_semantics='KNOWN_AT_DECISION_SESSION',
                knowledge_available_at=session + 'T15:00:00+07:00', authority_tier='SYNTHETIC_TEST_CONTRACT',
                source_status='QUALIFIED', fitness={use: 'ELIGIBLE'}, raw_basis_qualified=True,
                explicit_ex_date='2026-06-25', executed_lifecycle=True, qualified_factor_chain_identity='synthetic:chain',
                metric='volume_shares' if feature == 'ADV' else 'value_vnd' if feature == 'ADTV' else None,
                ca_normalized=True, policy_identity='synthetic:policy', lot_size=100, lower_price=50, upper_price=200,
                maximum_leverage=1, margin_eligible=True, borrow_available=True)


def gate_row(feature, e=None, use='EXECUTION_REPLAY'):
    return a.authority_row(feature=feature, use_case=use, ticker='VNM', session=T0,
                           evidence=e if e is not None else evidence(feature, use), knowledge_cutoff=CUTOFF)


def sizing():
    return dict(capital=10000, risk_budget_fraction=.01, entry_price=100, invalidation_price=90,
                input_identity='synthetic:portfolio', policy_identity='synthetic:policy', price_identity='synthetic:price',
                invalidation_identity='synthetic:stop', price_fitness='CURRENT_RESEARCH_ELIGIBLE',
                monetary_unit='VND', capital_unit='VND', price_unit='VND', invalidation_unit='VND')


@pytest.mark.parametrize('missing', ['capital', 'risk_budget_fraction', 'entry_price', 'invalidation_price', 'policy_identity', 'price_identity', 'invalidation_identity'])
def test_missing_governed_input_cannot_size(missing):
    i = sizing(); i.pop(missing)
    out = p.governed_research_sizing(i)
    assert out['theoretical_risk_size_research']['quantity'] is None
    assert out['execution_eligible_size']['quantity'] is None


@pytest.mark.parametrize('field,value', [('capital', True), ('capital', float('inf')), ('risk_budget_fraction', 2),
                                        ('invalidation_price', 100), ('invalidation_price', 110)])
def test_invalid_input_not_an_assumption(field, value):
    i = sizing(); i[field] = value
    assert p.governed_research_sizing(i)['theoretical_risk_size_research']['quantity'] is None


def test_reuses_engine_and_preserves_partial_execution_boundary():
    i = sizing()
    out = p.governed_research_sizing(i)
    assert out['risk_sizing'] == p._compute_risk_sizing(entry_price=100, invalidation_price=90, effective_nav=10000, risk_budget_fraction=.01)
    assert out['theoretical_risk_size_research'] == dict(state='PARTIAL', quantity=10, binding_constraint='RISK_CAP')
    assert out['execution_eligible_size']['quantity'] is None
    i['concentration_constraints'] = {'single_name': {'remaining_quantity': 3, 'policy_identity': i['policy_identity']}}
    assert p.governed_research_sizing(i)['theoretical_risk_size_research']['quantity'] == 3
    i['capital_unit'] = 'THOUSAND_VND'
    assert p.governed_research_sizing(i)['theoretical_risk_size_research']['quantity'] is None


def test_no_liquidity_only_fallback_can_claim_risk_size():
    i = sizing(); i.pop('invalidation_price')
    i['execution_capacity_research'] = {'state': 'PARTIAL', 'capacity_shares_lot_rounded': 20}
    assert p.governed_research_sizing(i)['theoretical_risk_size_research']['quantity'] is None


def test_research_liquidity_not_execution():
    e = evidence('CURRENT_LIQUIDITY', 'CURRENT_RESEARCH')
    assert gate_row('CURRENT_LIQUIDITY', e)['fitness'] == 'BLOCKED_BY_EVIDENCE'
    assert gate_row('CURRENT_LIQUIDITY', e, 'CURRENT_RESEARCH')['fitness'] == 'RESEARCH_USABLE'


@pytest.mark.parametrize('feature', ['CA_TIMING', 'CA_FACTOR_LINEAGE'])
@pytest.mark.parametrize('lifecycle', ['PLANNED', 'false', 1, ['EXECUTED']])
def test_truthy_lifecycle_is_not_executed_evidence(feature, lifecycle):
    e = evidence(feature); e['executed_lifecycle'] = lifecycle
    row = gate_row(feature, e)
    assert row['fitness'] == 'BLOCKED_BY_EVIDENCE'
    assert 'EXECUTED_LIFECYCLE_UNPROVEN_PLANS_NOT_EXECUTION' in row['blocker_reason_codes']


def test_adtv_not_adv_and_partial_preserves_source_status():
    e = evidence('ADV', 'CURRENT_RESEARCH'); e['metric'] = 'value_vnd'
    assert 'ADV_REQUIRES_SHARE_VOLUME_NOT_ADTV' in gate_row('ADV', e, 'CURRENT_RESEARCH')['blocker_reason_codes']
    e['metric'] = 'volume_shares'; e['fitness']['CURRENT_RESEARCH'] = 'PARTIAL'; e['source_status'] = 'PARTIAL'
    row = gate_row('ADV', e, 'CURRENT_RESEARCH')
    assert row['fitness'] == 'RESEARCH_USABLE' and row['source_status'] == 'PARTIAL'


def test_non_normalized_adv_never_becomes_normalized():
    e = evidence('CA_NORMALIZED_LIQUIDITY'); e['ca_normalized'] = False
    assert 'CA_NORMALIZATION_NOT_QUALIFIED' in gate_row('CA_NORMALIZED_LIQUIDITY', e)['blocker_reason_codes']


@pytest.mark.parametrize('feature', ['HISTORICAL_SHARES', 'EXCHANGE_LISTING', 'HISTORICAL_PRICE'])
def test_current_fact_cannot_become_historical(feature):
    e = evidence(feature); e['temporal_semantics'] = 'CURRENT_STATE_ONLY'
    assert 'CURRENT_OR_RETROSPECTIVE_FACT_NOT_HISTORICAL_PIT' in gate_row(feature, e)['blocker_reason_codes']


@pytest.mark.parametrize('known', ['2026-07-01T00:00:00Z', None, '2026-06-30T14:00:00'])
def test_future_unknown_and_naive_knowledge_fail_closed(known):
    e = evidence('HISTORICAL_PRICE'); e['knowledge_available_at'] = known
    assert gate_row('HISTORICAL_PRICE', e)['fitness'] == 'BLOCKED_BY_EVIDENCE'


def test_timezone_instant_and_later_provider_verdict():
    e = evidence('HISTORICAL_PRICE'); e['knowledge_available_at'] = '2026-06-30T09:01:00Z'
    assert 'FUTURE_KNOWN_EVIDENCE' in gate_row('HISTORICAL_PRICE', e)['blocker_reason_codes']
    e['knowledge_available_at'] = '2026-06-30T08:00:00Z'; e['basis_knowledge_available_at'] = '2026-07-01T00:00:00Z'
    assert 'FUTURE_OR_UNPROVEN_PROVIDER_BASIS_VERDICT' in gate_row('HISTORICAL_PRICE', e)['blocker_reason_codes']


def test_record_date_and_planned_issuance_are_not_ex_date_or_execution():
    e = evidence('CA_TIMING'); e.pop('explicit_ex_date'); e['record_date'] = T0
    e['executed_lifecycle'] = False; e['planned_shares'] = 100
    r = gate_row('CA_TIMING', e)
    assert 'EX_DATE_NOT_EXPLICIT_RECORD_DATE_NOT_SUBSTITUTE' in r['blocker_reason_codes']
    assert 'EXECUTED_LIFECYCLE_UNPROVEN_PLANS_NOT_EXECUTION' in r['blocker_reason_codes']


def test_r6_cannot_be_relabelled_backtest():
    e = evidence('PIT_KNOWLEDGE', 'BACKTEST'); e['evidence_kind'] = 'R6_PROSPECTIVE_OBSERVATION'
    assert 'PROSPECTIVE_OBSERVATION_NOT_BACKTEST' in gate_row('PIT_KNOWLEDGE', e, 'BACKTEST')['blocker_reason_codes']


def test_not_applicable_distinct_unknown_and_blocked():
    e = evidence('BORROW_SHORT'); e['fitness']['EXECUTION_REPLAY'] = 'NOT_APPLICABLE'
    assert gate_row('BORROW_SHORT', e)['fitness'] == 'NOT_APPLICABLE'
    assert gate_row('LOT_SIZE', {})['fitness'] == 'UNKNOWN_SEMANTICS'
    assert gate_row('CURRENT_PRICE', evidence('CURRENT_PRICE', 'CURRENT_RESEARCH'))['fitness'] == 'BLOCKED_BY_EVIDENCE'


def replay_inputs():
    ev = {f: evidence(f) for f in a.EXECUTION_REQUIRED_FEATURES}
    snapshot = dict(ticker='VNM', snapshot_id='synthetic:signal', knowledge_cutoff=CUTOFF, state='partial',
                    ranking={'dimensions': {'technical_current_market_readiness': {'state': 'available'}}},
                    scenarios={'records': {'bull': {'state': 'available'}}})
    rows = []
    for day, price in [('2026-07-01', 100), ('2026-07-02', 110)]:
        rows.append(dict(trading_date=day, raw_close=price, volume=10, price_basis='raw_historical',
                         volume_qualification='qualified', price_source_id='synthetic:p', citation_id='synthetic:c', source_hash='synthetic:h',
                         fill_knowledge_cutoff=day + 'T16:00:00+07:00',
                         authority_evidence={f: evidence(f, session=day) for f in a.EXECUTION_REQUIRED_FEATURES}))
    return dict(snapshot=snapshot, raw_sessions=rows, evidence=ev, max_holding_sessions=1)


def test_missing_cost_blocks_net_preserves_gross_and_no_network_or_live_orders(monkeypatch):
    def prohibited(*args, **kwargs): raise AssertionError('network/broker action prohibited')
    monkeypatch.setattr(socket.socket, 'connect', prohibited)
    i = replay_inputs(); original = copy.deepcopy(i)
    r = replay.run_authority_gated_replay(**i)
    assert r['gross_return'] == pytest.approx(.1) and r['net_return'] is None
    assert r['live_orders'] == 0 and r['authority_effect'] == 'NONE' and i == original


def test_explicit_governed_costs_use_existing_return_method():
    i = replay_inputs()
    i['evidence'].update({f: evidence(f) for f in ('FEES_TAXES', 'SLIPPAGE_IMPACT')})
    costs = dict(cost_model_version='1.0.0', commission_bps=5, tax_bps=0, slippage_bps=5, policy_identity='synthetic:policy')
    r = replay.run_authority_gated_replay(**i, costs=costs)
    assert r['net_return'] == replay.replay_return_semantics(100, 110, costs)['net_return']
    costs['policy_identity'] = 'wrong'
    assert replay.run_authority_gated_replay(**i, costs=costs)['net_return'] is None


@pytest.mark.parametrize('feature', ['CA_TIMING', 'CA_FACTOR_LINEAGE', 'LOT_SIZE', 'PRICE_BAND', 'LEVERAGE', 'RAW_AS_TRADED'])
def test_local_replay_prerequisite_gaps(feature):
    i = replay_inputs(); i['evidence'].pop(feature)
    assert replay.run_authority_gated_replay(**i)['gross_return'] is None
    assert gate_row('CURRENT_PRICE', evidence('CURRENT_PRICE', 'CURRENT_RESEARCH'), 'CURRENT_RESEARCH')['fitness'] == 'RESEARCH_USABLE'


def test_leverage_short_and_missing_fill_cutoff_block():
    i = replay_inputs()
    assert 'MARGIN' in replay.run_authority_gated_replay(**i, leveraged=True)['eligibility']['blocked_features']
    assert 'BORROW_SHORT' in replay.run_authority_gated_replay(**i, short=True)['eligibility']['blocked_features']
    i['raw_sessions'][0].pop('fill_knowledge_cutoff')
    assert replay.run_authority_gated_replay(**i)['gross_return'] is None


def test_deterministic_input_order_replay_and_duplicate_session():
    i = replay_inputs(); first = replay.run_authority_gated_replay(**i)
    i['raw_sessions'].reverse(); i['evidence'] = dict(reversed(list(i['evidence'].items())))
    assert replay.run_authority_gated_replay(**i) == first
    i['raw_sessions'].append(copy.deepcopy(i['raw_sessions'][0]))
    assert 'DUPLICATE_FILL_SESSION' in replay.run_authority_gated_replay(**i)['reason_codes']


def test_authority_matrix_cannot_self_promote():
    e = evidence('CURRENT_PRICE', 'LIVE_EXECUTION')
    before = copy.deepcopy(e)
    row = gate_row('CURRENT_PRICE', e, 'LIVE_EXECUTION')
    assert row['fitness'] == 'BLOCKED_BY_EVIDENCE' and e == before
    assert row['promotion_status'] == 'NOT_REQUESTED' and row['authority_effect'] == 'NONE'


def test_readiness_integration_is_additive_idempotent_and_non_voting():
    r = dict(ticker='VNM', as_of_session=T0, research_action_posture='WAIT_FOR_CONFIRMATION',
             portfolio_context={'status': 'NOT_PROVIDED'}, evidence_axes={'PORTFOLIO_FIT': {'state': 'NOT_PROVIDED'}})
    original = copy.deepcopy(r)
    d = integrated.decision_identity(r)
    result = a.attach_current_readiness(r)
    assert r == original and integrated.decision_identity(result) == d
    assert result['research_action_posture'] == r['research_action_posture']
    assert a.attach_current_readiness(result) == result


def test_portfolio_absence_and_qualified_explicit_aggregation_no_cash_default():
    assert portfolio.governed_portfolio_research(portfolio=None, contexts={})['metrics'] is None
    p = dict(portfolio_id='synthetic:portfolio', input_identity='synthetic:input', as_of_session=T0, monetary_unit='VND', capital=1000,
             positions=[dict(ticker='AAA', explicit_market_value=100, monetary_unit='VND', sector='S', sector_identity='synthetic:sector'),
                        dict(ticker='BBB', explicit_market_value=300, monetary_unit='VND', sector='S', sector_identity='synthetic:sector')])
    contexts = {k: {'records': {}} for k in ('tactical', 'peer_relative', 'fundamental', 'valuation', 'scenario', 'strategy', 'corporate_intelligence')}
    contexts['descriptive'] = {'session': T0, 'records': {}}
    contexts['strategy']['strategy_registry'] = {}
    r = portfolio.governed_portfolio_research(portfolio=p, contexts=contexts)
    assert r['metrics']['capital_usage'] == .4 and r['metrics']['cash'] is None
    assert r['metrics']['single_name_concentration'] == {'AAA': .25, 'BBB': .75}
    assert r['metrics']['sector_concentration'] == {'S': 1}
    assert r['volatility_correlation']['state'] == 'UNAVAILABLE'
    p['positions'].reverse()
    assert portfolio.governed_portfolio_research(portfolio=p, contexts=contexts) == r
    p['positions'][0]['monetary_unit'] = 'THOUSAND_VND'
    with pytest.raises(ValueError): portfolio.governed_portfolio_research(portfolio=p, contexts=contexts)


def test_retained_manifest_hash_and_path_escape_fail_before_consumption(tmp_path):
    path = tmp_path / 'a.json'; path.write_text('{}')
    manifest = {'inputs': [dict(id='x', root='root', path='a.json', sha256='wrong')]}
    with pytest.raises(ValueError, match='HASH_CHANGED'): Inputs(manifest, {'root': tmp_path})
    manifest['inputs'][0]['path'] = '../outside'
    with pytest.raises(ValueError, match='ESCAPES_ROOT'): Inputs(manifest, {'root': tmp_path})


def test_existing_research_window_engine_qualified_basis_and_missing_data():
    from test_current_portfolio_risk_research import _inputs
    source = _inputs()['price_snapshot']
    first = qualified_window_readiness(price_snapshot=source, tickers=['AAA', 'BBB'])
    assert first['records']['AAA']['20']['window_status'] == 'WINDOW_READY'
    source['records']['AAA']['observations'][0]['close'] = True
    second = qualified_window_readiness(price_snapshot=source, tickers=['BBB', 'AAA'])
    assert second['records']['AAA']['20']['window_status'] != 'WINDOW_READY'
    assert first['records']['BBB'] == second['records']['BBB']


def test_dossier_can_recommend_only_explicitly_qualified_scope_without_promotion():
    ev = {f: evidence(f) for f in a.EXECUTION_REQUIRED_FEATURES}
    ready = a.use_case_readiness(use_case='EXECUTION_REPLAY', ticker='VNM', session=T0, evidence=ev, knowledge_cutoff=CUTOFF)
    dossier = a.promotion_dossier([ready])
    row = next(r for r in dossier['use_cases'] if r['requested_use_case'] == 'EXECUTION_REPLAY')
    assert row['status'] == 'PROMOTION_CANDIDATE_REQUIRES_OWNER_APPROVAL'
    assert dossier['authority_effect'] == 'NONE' and dossier['owner_promotion_required']


def test_exact_feature_session_scope_and_adjusted_basis_do_not_grant_raw():
    e = evidence('RAW_AS_TRADED'); e['raw_basis_qualified'] = False
    assert 'RAW_BASIS_NOT_QUALIFIED' in gate_row('RAW_AS_TRADED', e)['blocker_reason_codes']
    e = evidence('LOT_SIZE', session='2026-07-01')
    assert 'FEATURE_OR_SCOPE_NOT_BOUND' in gate_row('LOT_SIZE', e)['blocker_reason_codes']


def test_missing_governed_constraint_values_and_outside_band_block_replay():
    for feature, key in [('LOT_SIZE', 'lot_size'), ('PRICE_BAND', 'lower_price'), ('LEVERAGE', 'maximum_leverage')]:
        e = evidence(feature); e.pop(key)
        assert gate_row(feature, e)['fitness'] == 'BLOCKED_BY_EVIDENCE'
    i = replay_inputs(); i['raw_sessions'][0]['raw_close'] = 201
    assert 'FILL_PRICE_OUTSIDE_QUALIFIED_SESSION_BAND' in replay.run_authority_gated_replay(**i)['reason_codes']
