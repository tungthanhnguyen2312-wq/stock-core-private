import copy
import pytest
import integrated_investment_decision_product as product
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery

SESSION = '2026-09-30'


def source(regime='MIXED_BREADTH', sector='LEADING'):
    return {'session': SESSION, 'artifact_identity': 'retained-market:fixture',
            'input_lineage': {'official_universe_scope': 'CURRENT_EXCHANGE_MASTER_MEMBERSHIP_NOT_HISTORICAL_OR_PIT'},
            'market': {'session': SESSION, 'current_breadth_state': regime,
                       'official_universe_count': 100, 'exact_session_observed_count': 60,
                       'missing_current_session_count': 40, 'breadth_coverage_ratio': .6},
            'ticker_contexts': {'HPG': {'sector_leadership_context': {'status': 'AVAILABLE', 'leadership_state': sector}}}}


@pytest.mark.parametrize('field,value', [
    ('session', '2026-09-29'), ('session', '2026-10-01'), ('session', None),
    ('official_universe_count', None), ('official_universe_count', True),
    ('exact_session_observed_count', 0), ('missing_current_session_count', 41),
    ('status', 'UNKNOWN'), ('status', 'BLOCKED'), ('current_breadth_state', None)])
def test_invalid_breadth_keeps_observation_but_cannot_constrain(field, value):
    artifact = source('DETERIORATING_BREADTH')
    artifact['market'][field] = value
    view = product.evaluate_market_breadth(artifact, SESSION)
    assert view['status'] == 'BLOCKED'
    assert view['market_regime'] == 'UNKNOWN'
    assert view['observation'] == artifact['market']
    assert view['reason_codes']


@pytest.mark.parametrize('regime,sector', [('BROAD_PARTICIPATION','LAGGING'),
    ('DETERIORATING_BREADTH','LEADING'), ('BROAD_PARTICIPATION','LEADING'), ('MIXED_BREADTH','UNKNOWN')])
def test_independent_market_sector_context_survives_shared_delivery(regime,sector):
    artifact = source(regime,sector)
    original = copy.deepcopy(artifact)
    record = product.build_ticker_integrated_decision(ticker='HPG', as_of_session=SESSION,
        tactical_record={'eligible': False}, financial_record=None, valuation_record=None,
        relative_volume_record=None, market_sector_record=artifact)
    assert artifact == original
    context = record['market_sector_context']
    assert context['market_breadth']['status'] == 'PARTIAL'
    assert context['market_regime'] == regime
    assert context['sector_leadership'] == sector
    view = project_integrated_decision_for_ai_delivery(record)
    assert view['evidence_axes']['MARKET_SECTOR']['context']['market_breadth'] == context['market_breadth']
    assert view['current_research_decision_input']['dimensions']['MARKET']['market_breadth'] == context['market_breadth']
    assert record['trigger']['trigger_state'] != 'TRIGGERED'
    assert view['is_actionable'] is False


def test_stale_sector_cannot_be_current_leader():
    artifact = source()
    artifact['session'] = '2026-09-29'
    record = product.build_ticker_integrated_decision(ticker='HPG', as_of_session=SESSION,
        tactical_record=None, financial_record=None, valuation_record=None,
        relative_volume_record=None, market_sector_record=artifact)
    assert record['market_sector_context']['sector_leadership'] == 'UNKNOWN'
    assert record['market_sector_context']['sector_leadership_status'] == 'BLOCKED'


def test_provider_partial_and_narrow_cohort_never_become_full_coverage():
    artifact = source()
    artifact['market'].update(status='PARTIAL', exact_session_observed_count=5, missing_current_session_count=95)
    view = product.evaluate_market_breadth(artifact, SESSION)
    assert view['status'] == 'PARTIAL'
    assert view['observation']['exact_session_observed_count'] == 5
    assert 'PARTIAL_COHORT_NOT_ALL_MARKET' in view['limitations']
