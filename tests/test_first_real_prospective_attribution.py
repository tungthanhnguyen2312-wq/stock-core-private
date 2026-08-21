import copy
from run_first_real_prospective_attribution import run
from prospective_research_learning import first_real_observation

def test_first_real_observation_is_strict_and_replayable():
    first = run(); second = run()
    assert first == second
    assert first['disposition'] == 'FIRST_REAL_PROSPECTIVE_ATTRIBUTION_COMPLETE'
    assert first['overall']['frozen_cohort_size'] == 523
    assert first['overall']['observed_future_coverage'] + first['overall']['missing_future_observations'] == 523
    assert first['precondition']['corrected_extension_identity'].endswith('6cc76efaaf55b4262b6d94d53abda75dc1a0289d17c7d195014e11a07e987807')
    assert first['cohort_reconciliation']['future_refreshed_empirical_cohort_size'] == 524
    assert first['cohort_reconciliation']['future_only_members_not_added_to_t'] == ['HMS', 'VPS', 'VTC']
    assert len(first['cohort_reconciliation']['frozen_members_not_in_refreshed_future_cohort']) == 2
    assert not set(first['cohort_reconciliation']['future_only_members_not_added_to_t']) & set(first['cohort_reconciliation']['attributed_tickers'])
    assert {group['group'] for group in first['queue_attribution']} == {'queue:FROZEN_25_NAME_QUEUE', 'queue:FROZEN_NON_QUEUE'}

def test_future_session_and_identity_are_fail_closed(monkeypatch):
    import run_first_real_prospective_attribution as runner
    original = runner._load
    def altered(path):
        value = original(path)
        if path.endswith('scaleout_artifact.json'):
            value = copy.deepcopy(value); value['resolved_session']['incomplete_intraday_used'] = True
        return value
    monkeypatch.setattr(runner, '_load', altered)
    try:
        runner.run()
    except ValueError as error:
        assert str(error) == 'FUTURE_EXACT_SESSION_PRECONDITION_NOT_MET'
    else:
        raise AssertionError('future exact-session guard did not fail closed')
