import copy
import pytest
import integrated_investment_decision_product as product
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery

SESSION='2026-09-30'

def source(**changes):
    row=dict(session=SESSION,provider='DNSE',source_field='DNSE_OHLC.volume',status='READY',
        fitness='RESEARCH_DESCRIPTIVE_ONLY',percentile_status='READY',acceleration_status='READY',
        relative_volume_percentile=.9,volume_acceleration_ratio=1.8,cohort_denominator=853,
        valid_prior_completed_session_count=20,limitations=['not_adv_or_adtv','execution_capacity_blocked','position_sizing_blocked'])
    row.update(changes)
    return row

@pytest.mark.parametrize('session', [None,'2026-09-29','2026-10-01'])
def test_noncurrent_participation_cannot_support_or_contradict(session):
    view,supports,counters=product.evaluate_participation(None,source(session=session),session=SESSION)
    assert supports == counters == []
    assert view['status']=='NOT_AVAILABLE'
    assert view['source_observation']['session']==session

@pytest.mark.parametrize('value',[True,False,float('inf'),float('-inf'),float('nan'),-1,'1.8'])
def test_invalid_numeric_measurements_never_become_evidence(value):
    view,supports,counters=product.evaluate_participation({'relative_volume_provider_scoped':value},
        source(relative_volume_percentile=value,volume_acceleration_ratio=value),session=SESSION)
    assert supports == counters == []
    assert view['status']=='NOT_AVAILABLE'

@pytest.mark.parametrize('status',['UNKNOWN','UNAVAILABLE','BLOCKED'])
def test_unqualified_provider_status_has_no_numeric_effect(status):
    _,supports,counters=product.evaluate_participation(None,source(status=status),session=SESSION)
    assert supports == counters == []

@pytest.mark.parametrize('denominator',[None,0,True,-1])
def test_missing_percentile_denominator_blocks_only_that_measurement(denominator):
    view,supports,_=product.evaluate_participation(None,source(cohort_denominator=denominator),session=SESSION)
    assert view['relative_volume_percentile'] is None
    assert view['volume_acceleration_ratio']==1.8
    assert len(supports)==1

def test_current_partial_source_preserves_independent_ready_measurement():
    view,supports,_=product.evaluate_participation(None,
        source(status='PARTIAL',acceleration_status='UNAVAILABLE_INSUFFICIENT_HISTORY',volume_acceleration_ratio=10),session=SESSION)
    assert view['volume_acceleration_ratio'] is None
    assert len(supports)==1 and 'UPPER_QUARTILE' in supports[0]

def test_high_participation_preserves_blocked_execution_and_shared_provenance():
    row=source()
    before=copy.deepcopy(row)
    record=product.build_ticker_integrated_decision(ticker='HPG',as_of_session=SESSION,
        tactical_record=None,financial_record=None,valuation_record=None,relative_volume_record=row,market_sector_record=None)
    view=project_integrated_decision_for_ai_delivery(record)
    assert view['participation']['source_observation']==row==before
    assert view['no_position_size'] and not view['is_actionable']
    assert 'execution_capacity_blocked' in view['participation']['source_observation']['limitations']
    assert record['research_action_posture']==product.POSTURE_INSUFFICIENT
