import pytest
import stocklookup_core.decision.integrated_investment_decision_product as product


@pytest.mark.parametrize('phase', [product.TACTICAL_BREAKDOWN, product.TACTICAL_DISTRIBUTION_RISK])
@pytest.mark.parametrize('fundamental', [product.FUNDAMENTAL_STABLE, product.FUNDAMENTAL_IMPROVING, product.FUNDAMENTAL_TURNAROUND])
@pytest.mark.parametrize('confirmation', ['CONFIRMED', 'INSUFFICIENT_EVIDENCE'])
def test_bearish_structure_cannot_be_aligned_with_constructive_fundamentals(phase,fundamental,confirmation):
    axes = {'FUNDAMENTAL': {'state': fundamental},
            'TACTICAL_STRUCTURE': {'state': phase, 'fitness': 'AVAILABLE'},
            'PARTICIPATION_CONFIRMATION': {'state': confirmation,
                'context': {'structure_stance': 'BEARISH'}},
            'MARKET_SECTOR': {'context': {'market_regime': 'BROAD_PARTICIPATION', 'sector_leadership': 'LEADING'}}}
    view = product.evaluate_evidence_axis_coherence(axes)
    assert view['state'] == product.EVIDENCE_AXIS_COHERENCE_MIXED
    assert view['reason_codes'] == ['CONSTRUCTIVE_FUNDAMENTALS_WITH_ADVERSE_TECHNICAL_STRUCTURE']
    assert view['is_actionable'] is False


@pytest.mark.parametrize('status,supports,expected', [
    ('AVAILABLE', [], 'no observed participation contradiction'),
    ('NOT_AVAILABLE', [], 'participation evidence unavailable'),
    ('AVAILABLE', ['VOLUME_ACCELERATION_HIGH_1.80X'], 'supportive participation')])
def test_valid_breakout_retains_posture_without_inventing_participation_support(status,supports,expected):
    posture, why, effect, condition_class = product.decide_research_action_posture(ticker='HPG',
        fundamental_state=product.FUNDAMENTAL_STABLE, tactical_phase=product.TACTICAL_BREAKOUT_CONFIRMED,
        tactical_rec={'eligible': True, 'market_structure_state': 'UPTREND',
                      'breakout_state_v3': 'BREAKOUT', 'trigger_state': 'TRIGGERED',
                      'trigger_type': 'PIVOT_BREAKOUT_TRIGGER'},
        fund_supports=[],fund_counters=[],tac_supports=[],tac_counters=[],val_supports=[],val_counters=[],
        part_supports=supports,part_counters=[],participation_summary={'status': status},
        market_sector_summary={'market_regime':'MIXED_BREADTH','sector_leadership':'UNKNOWN'})
    assert posture == product.POSTURE_INITIATE_ON_BREAKOUT
    assert condition_class == 'FRESH_ENTRY_TRIGGER'
    assert expected in why
    if not supports:
        assert 'supportive participation' not in why


def test_bearish_confirmation_remains_its_source_observation():
    axes = {'FUNDAMENTAL': {'state': product.FUNDAMENTAL_STABLE},
            'TACTICAL_STRUCTURE': {'state': product.TACTICAL_BREAKDOWN, 'fitness': 'AVAILABLE'},
            'PARTICIPATION_CONFIRMATION': {'state':'CONFIRMED', 'supporting_reason_codes':['MOMENTUM_DIRECTION_ALIGNED']}}
    product.evaluate_evidence_axis_coherence(axes)
    assert axes['PARTICIPATION_CONFIRMATION']['state'] == 'CONFIRMED'
    assert axes['PARTICIPATION_CONFIRMATION']['supporting_reason_codes'] == ['MOMENTUM_DIRECTION_ALIGNED']


@pytest.mark.parametrize('sector,expected', [('LEADING','ALIGNED'),('MIXED','ALIGNED'),('WEAKENING','MIXED'),('DATA_LIMITED','PARTIALLY_ALIGNED'),('future_new_state','PARTIALLY_ALIGNED')])
def test_producer_sector_vocabulary_is_handled_explicitly(sector,expected):
    axes={'FUNDAMENTAL':{'state':product.FUNDAMENTAL_STABLE}, 'TACTICAL_STRUCTURE':{'fitness':'AVAILABLE','state':product.TACTICAL_BREAKOUT_CONFIRMED}, 'PARTICIPATION_CONFIRMATION':{'state':'CONFIRMED'}, 'MARKET_SECTOR':{'context':{'sector_leadership':sector}}}
    result=product.evaluate_evidence_axis_coherence(axes)
    assert result['state'] == expected
    if sector in ('DATA_LIMITED','future_new_state'):
        assert result['reason_codes'] == ['SECTOR_LEADERSHIP_UNKNOWN_OR_DATA_LIMITED']
