from run_downside_uncertainty_research_context import run


def test_downside_vector_is_deterministic_and_preserves_unknowns():
    first, overlay = run(); second, _ = run()
    assert first['artifact_identity'] == second['artifact_identity']
    assert first['coverage']['records'] == 523
    assert first['screener_discovery_presets']['NEGATIVE_MOMENTUM_CONTEXT'] == 210
    assert first['screener_discovery_presets']['BELOW_MA20_CONTEXT'] == 304
    assert first['screener_discovery_presets']['ELEVATED_CROSS_SECTIONAL_VOLATILITY_CONTEXT'] == 131
    assert first['screener_discovery_presets']['EXECUTION_RISK_NOT_ASSESSABLE'] == 523
    assert len(overlay['entries']) == 25
    for row in first['records']:
        domains = row['domains']
        assert domains['EXECUTION_RISK_STATUS']['status'] == 'EXECUTION_RISK_NOT_ASSESSABLE'
        assert domains['EVENT_VISIBILITY']['status'] in {'NO_RETAINED_EVENT_EVIDENCE', 'EVIDENCED_EVENT_CONTEXT'}
        assert domains['EVIDENCE_UNCERTAINTY']['status'].startswith('EVIDENCE_UNCERTAINTY_')
    assert first['authority_boundary']['evidence_uncertainty_not_economic_risk']
    assert first['authority_boundary']['event_absence_not_no_event_risk']
