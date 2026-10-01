import copy
import pytest
import fundamental_signal_consumption_contract as contract
import integrated_investment_decision_product as product
import financial_analysis_product_projection as projection
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery
from test_integrated_fundamental_state_consumption import _compact

SESSION='2026-09-30'

def compact(**states):
    row=_compact(**states)
    row['source_context_identity']='financial_analysis_context/v2:fixture'
    for name,fitness in row['feature_fitness'].items():
        fitness['source_feature_context']={'feature_id':name,'value':None,'method':'same_provider_fixture/v2',
            'scope':['consolidated'],'period_semantics':['STANDALONE_QUARTER'],
            'period_identity':['2025-Q2','2026-Q2'],'source_context_identity':row['source_context_identity'],
            'source_fact_refs':[{'provider':'KBS','fact_id':'fact:fixture','source_sha256':'retained-sha'}]}
    row['feature_fitness']['cfo_to_net_income_ttm']['fitness']='BLOCKED'
    return row

def synthesis(row):return contract.evaluate(row,decision_session=SESSION)

def decision(row,technical=None):
    return product.build_ticker_integrated_decision(ticker='HPG',as_of_session=SESSION,
        financial_record=row,tactical_record=technical,valuation_record=None,
        relative_volume_record=None,market_sector_record=None)

def test_divergent_revenue_and_earnings_measurements_remain_independent_without_consensus_vote():
    row=compact(growth_state='UNAVAILABLE')
    row['feature_fitness']['revenue_qoq']['source_feature_context']['value']=.2
    row['feature_fitness']['net_income_qoq']['source_feature_context']['value']=-.2
    result=synthesis(row)
    observations=result['thesis_context']['feature_observations']
    assert observations['revenue_qoq']['source_feature_context']['value']==.2
    assert observations['net_income_qoq']['source_feature_context']['value']==-.2
    assert 'REVENUE_CONTRACTION' not in result['contradicting_reason_codes']
    assert 'GROWTH.DIRECTION' not in result['derivation']['favorable_votes']

def test_qualified_weak_cash_conversion_opposes_observed_accounting_profitability():
    result=synthesis(compact(profitability_state='PROFITABLE',cash_conversion_state='WEAK'))
    context=result['thesis_context']
    assert 'profitability_level' in context['supporting_evidence_ids']
    assert 'cash_conversion_level' in context['opposing_evidence_ids']
    assert context['relationships'][0]['reason_code']=='QUALIFIED_FUNDAMENTAL_DIMENSIONS_DIVERGE'

def test_cash_flow_amount_proxy_does_not_become_quality_counter():
    result=synthesis(compact(profitability_state='PROFITABLE',free_cash_flow_proxy_direction_state='WORSENING'))
    assert 'free_cash_flow_proxy_direction' in result['thesis_context']['descriptive_evidence_ids']
    assert 'free_cash_flow_proxy_direction' not in result['thesis_context']['opposing_evidence_ids']
    assert result['fundamental_state']==contract.FUNDAMENTAL_STABLE

def test_margin_deterioration_keeps_its_own_context_with_no_peer_reclassification():
    result=synthesis(compact(profitability_state='PROFITABLE',margin_state='MARGIN_COMPRESSING'))
    assert 'net_margin_direction' in result['thesis_context']['opposing_evidence_ids']
    assert result['thesis_context']['evidence']['net_margin_direction']['fitness']['source_feature_context']['net_margin_direction']['method']=='same_provider_fixture/v2'

def test_absence_is_an_uncertainty_without_negative_evidence():
    record=decision({'status':'ABSENT'})
    assert 'FUNDAMENTAL_CONTEXT_ABSENT' not in record['counter_thesis']
    assert 'FUNDAMENTAL_CONTEXT_ABSENT' in record['material_uncertainties']
    assert record['evidence_axes']['FUNDAMENTAL']['blocker_reason_codes']==['FUNDAMENTAL_CONTEXT_ABSENT']

@pytest.mark.parametrize('family,issuer',[('BANK_SPECIALIST_CONTEXT','bank'),('SECURITIES_SPECIALIST_CONTEXT','securities'),('UNSUPPORTED_ENTITY_CONTEXT','insurance')])
def test_industrial_direction_never_leaks_into_specialist_entity(family,issuer):
    row=compact(growth_state='CONTRACTING',margin_state='MARGIN_COMPRESSING',analysis_family=family,issuer_type=issuer)
    result=synthesis(row)
    assert 'growth_direction' not in result['thesis_context']['opposing_evidence_ids']
    assert 'net_margin_direction' not in result['thesis_context']['opposing_evidence_ids']

def test_stale_negative_margin_is_history_beside_current_profitability():
    row=compact(profitability_state='PROFITABLE',margin_state='MARGIN_COMPRESSING')
    row['feature_fitness']['net_margin']['as_of_period']='2024-Q4'
    result=synthesis(row)
    assert 'net_margin_direction' in result['thesis_context']['historical_evidence_ids']
    assert 'MARGIN_COMPRESSION' not in result['contradicting_reason_codes']
    assert 'profitability_level' in result['thesis_context']['supporting_evidence_ids']

def test_unknown_duration_and_incompatible_source_status_do_not_gain_authority():
    row=compact()
    row['feature_fitness']['revenue_qoq'].update(fitness='BLOCKED',reason_codes=['INCOMPATIBLE_PROVIDER_PERIODS'])
    row['feature_fitness']['net_income_qoq']['source_feature_context']['period_semantics']=[]
    result=synthesis(row)
    assert 'revenue_qoq' not in result['thesis_context']['feature_observations']
    assert result['thesis_context']['feature_observations']['net_income_qoq']['source_feature_context']['period_semantics']==[]

def test_future_feature_remains_blocked_source_observation():
    row=compact()
    row['feature_fitness']['revenue_qoq']['as_of_period']='2027-Q1'
    result=synthesis(row)
    assert result['thesis_context']['feature_observations']['revenue_qoq']['use']=='BLOCKED_SOURCE_OBSERVATION'

def test_projection_keeps_reference_provenance_without_raw_statement_labels():
    engine={'artifact_identity':'engine:fixture'}
    row={'features':{'net_income_sign':{'feature_id':'ni','value':1,'fitness':'RESEARCH_PROXY',
          'method':'same_native_sign','period_identity':['2026-Q2'],'scope':['unknown'],
          'period_semantics':['STANDALONE_QUARTER'],'provider_source_provenance':[
            {'provider':'VCI','fact_id':'fact:1','source_sha256':'sha','raw_label_vi':'private label'}]}}}
    compacted=projection._compact(engine,'HPG',row)
    metadata=compacted['feature_fitness']['net_income_sign']['source_feature_context']
    assert metadata['source_fact_refs'][0]['provider']=='VCI'
    assert 'raw_label_vi' not in metadata['source_fact_refs'][0]
    assert compacted['feature_fitness']['net_income_sign']['fitness']=='RESEARCH_PROXY'

def test_shared_delivery_preserves_all_thesis_roles_and_risk_verbatim():
    row=compact(profitability_state='PROFITABLE',cash_conversion_state='WEAK',margin_state='MARGIN_COMPRESSING')
    original=copy.deepcopy(row)
    record=decision(row)
    view=project_integrated_decision_for_ai_delivery(record)
    assert view['evidence_axes']['FUNDAMENTAL']['context']['thesis_context']==record['fundamental_synthesis']['thesis_context']
    assert view['is_actionable'] is False
    assert row==original


@pytest.mark.parametrize('states,technical', [
    ({'status':'ABSENT'}, {'eligible':True,'market_structure_state':'UPTREND','breakout_state_v3':'BREAKOUT','trigger_state':'TRIGGERED','trigger_type':'PIVOT_BREAKOUT_TRIGGER'}),
    ({'profitability_state':'LOSS_MAKING','growth_state':'CONTRACTING','margin_state':'MARGIN_COMPRESSING'}, {'eligible':True,'market_structure_state':'EARLY_BULLISH_REVERSAL','choch_state':'BULLISH_CHOCH_DETECTED_BY_RULE'}),
    ({'profitability_state':'PROFITABLE','growth_state':'GROWING'}, {'eligible':True,'market_structure_state':'UPTREND','breakout_state_v3':'FAILED_BREAKOUT'})])
def test_explanation_provenance_does_not_change_existing_structural_policy(states,technical):
    rich=compact(**states)
    bare=copy.deepcopy(rich)
    for fitness in bare['feature_fitness'].values():
        fitness.pop('source_feature_context',None)
    before,after=decision(bare,technical),decision(rich,technical)
    assert before['research_action_posture']==after['research_action_posture']
    assert before['fundamental_state']==after['fundamental_state']
    assert before['counter_thesis']==after['counter_thesis']
