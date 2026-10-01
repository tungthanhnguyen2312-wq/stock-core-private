import copy
import pytest
import current_evidence_bound_scenario as scenario
from ai_research_session_delivery import _compact_context, project_current_scenario_for_ai_delivery


@pytest.mark.parametrize('state',['DOWNTREND','DISTRIBUTION_RISK','UPTREND_CONFIRMED','EARLY_REVERSAL_CANDIDATE','SIDEWAYS_NEUTRAL'])
def test_evidence_availability_is_not_positive_case_support(state):
    tactical={'entry_state':state,'market_state':'MIXED_NO_CLEAR_MARKET_REGIME','data_quality':{'technical_eligible':True}}
    drivers=scenario._drivers(tactical,{'technical_peer_context':{'status':'AVAILABLE'}},
        {'fundamental_trajectory_context':{'trajectory_status':'OFFICIAL_METRIC_CONTEXT_ONLY','available_dimension_count':0}},None,None,None)
    for name in ('MARKET_CONTEXT','TECHNICAL','TACTICAL','PEER_RELATIVE','FUNDAMENTAL','DATA_QUALITY'):
        assert drivers[name]['status']=='AVAILABLE_DESCRIPTIVE'


def test_missing_technical_evidence_is_a_gap_without_negative_conflict():
    drivers=scenario._drivers({'data_quality':{'technical_eligible':False}},None,None,None,None,None)
    assert drivers['DATA_QUALITY']['status']=='UNAVAILABLE'
    assert all(d['status']!='CONTRADICTORY' for d in drivers.values())


@pytest.mark.parametrize('status',['UNAVAILABLE',None,'UNRECOGNIZED'])
def test_explicit_unavailable_trajectory_remains_local_unavailable(status):
    drivers=scenario._drivers({'entry_state':'UPTREND_CONFIRMED','data_quality':{'technical_eligible':True}},
        {'technical_peer_context':{'status':'AVAILABLE'}},
        {'fundamental_trajectory_context':{'trajectory_status':status}},None,None,None)
    assert drivers['FUNDAMENTAL']['status']=='UNAVAILABLE'
    assert scenario._disposition({'entry_state':'UPTREND_CONFIRMED'},drivers)=='SCENARIO_PARTIAL'
    assert drivers['TECHNICAL']['status']=='AVAILABLE_DESCRIPTIVE'


@pytest.mark.parametrize('invalidation',['close below declared bullish support',None])
def test_same_condition_cannot_confirm_and_invalidate_bear_case(invalidation):
    tactical={'entry_state':'UPTREND_CONFIRMED','confirmation_trigger':'close above resistance','invalidation':invalidation}
    cases=scenario._cases('HPG','SCENARIO_READY',tactical,{}, {'tactical':'source:retained'})
    assert cases['BEAR']['invalidation'] is None
    assert cases['BEAR']['invalidation_status']=='BEAR_INVALIDATION_NOT_DECLARED_BY_SOURCE'
    assert cases['BEAR']['required_confirmations']==([invalidation] if invalidation else [])
    assert cases['BULL']['invalidation']==invalidation
    assert cases['BULL']['required_confirmations']==['close above resistance']


def test_shared_companion_preserves_case_conditions_and_explicit_bear_gap():
    tactical={'entry_state':'BREAKOUT_READY','confirmation_trigger':'source confirmation','invalidation':'source invalidation'}
    cases=scenario._cases('HPG','SCENARIO_PARTIAL',tactical,{}, {'tactical':'source:retained'})
    record={'ticker':'HPG','bear_case':cases['BEAR'],'base_case':cases['BASE'],'bull_case':cases['BULL'],
            'confirmation_trigger':tactical['confirmation_trigger'],'invalidation':tactical['invalidation'],
            'scenario_disposition':'SCENARIO_PARTIAL','probability_status':'UNKNOWN_UNCALIBRATED'}
    before=copy.deepcopy(record)
    operation={'scenario':{'artifact_identity':'scenario:source','records':{'HPG':record}}}
    delivered=_compact_context('HPG',operation,{})['scenario']
    for case in ('bear_case','base_case','bull_case'):
        assert delivered[case]==record[case]
    assert delivered['source_artifact_identity']=='scenario:source'
    assert delivered['is_actionable'] is False
    assert record==before


def test_unprovided_scenario_is_not_a_neutral_case():
    assert project_current_scenario_for_ai_delivery(None) is None
