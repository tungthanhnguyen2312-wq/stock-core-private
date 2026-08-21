from run_research_setup_classification import run


def test_setup_classification_is_deterministic_multilabel_and_authority_bound():
    first, daily, review, scenario, downside = run()
    second, _, _, _, _ = run()
    assert first['artifact_identity'] == second['artifact_identity']
    assert first['cohort']['member_count'] == 523
    assert first['coverage']['active_setup_counts']['BREAKOUT_CONTEXT'] == 19
    assert first['coverage']['active_setup_counts']['NEAR_SUPPORT_CONTEXT'] == 115
    assert first['coverage']['active_setup_counts']['RANGE_COMPRESSION_CONTEXT'] == 47
    assert first['coverage']['active_setup_counts']['BREAKDOWN_CONTEXT'] == 20
    assert first['coverage']['active_setup_counts']['TREND_CONTINUATION_CONTEXT'] == 193
    assert first['coverage']['record_setup_state_counts']['NO_DISTINCT_SETUP'] > 0
    assert first['coverage']['record_setup_state_counts']['MULTI_LABEL_SETUP_CONTEXT'] > 0
    assert len(daily['records']) == 523
    assert len(review['entries']) == 25
    assert len(scenario['entries']) == 25
    assert len(downside['entries']) == 523
    for record in first['records']:
        assert record['research_session'] == '2026-08-20'
        assert len(record['setup_evaluations']) == len(first['registry'])
        for setup in record['setup_evaluations']:
            assert setup['setup_content_identity'].startswith('research_setup:')
            assert setup['qualification_state'] in first['qualification_state_vocabulary']
            assert setup['source_artifact_identities']['price_structure'] == first['source_artifact_identities']['price_structure']
    provider = [setup for record in first['records'] for setup in record['setup_evaluations']
                if setup['setup_id'] == 'RELATIVE_STRENGTH_CONTEXT' and setup['qualification_state'] == 'QUALIFIED_LOWER_AUTHORITY']
    assert provider and all(setup['authority_ceiling'] == 'PROVIDER_DESCRIPTIVE_CLASSIFICATION' for setup in provider)
    assert first['authority_boundary']['not_signal_ranking_recommendation_or_expected_return']
