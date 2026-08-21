import copy
import pytest
from prospective_daily_rollforward import HORIZONS, build_learning_ledger, latest_exact_session
from run_prospective_daily_rollforward import run

def test_daily_rollforward_is_deterministic_and_preserves_pending_horizons():
    first_snapshot, first_ledger = run(); second_snapshot, second_ledger = run()
    assert first_snapshot == second_snapshot and first_ledger == second_ledger
    assert first_snapshot['research_session'] == '2026-08-21'
    assert first_snapshot['cohort']['member_count'] == 524
    assert first_snapshot['cohort']['membership_change_vs_prior_t_state']['entered_tickers'] == ['HMS', 'VPS', 'VTC']
    assert len(first_snapshot['cohort']['membership_change_vs_prior_t_state']['exited_tickers']) == 2
    assert first_snapshot['components']['setup_price_market_relative_downside'].startswith('UNAVAILABLE')
    assert first_ledger['rows'][0]['horizons']['H1']['status'] == 'OBSERVED'
    assert first_ledger['rows'][1]['horizons']['H1']['status'] == 'PENDING_FUTURE_OBSERVATION'
    assert all(row['horizons'][name]['status'] == 'PENDING_FUTURE_OBSERVATION' for row in first_ledger['rows'] for name in ('H3', 'H5'))
    assert HORIZONS == {'H1': 1, 'H3': 3, 'H5': 5}

def test_latest_exact_session_rejects_intraday_or_nonexact_sources():
    snapshot, _ = run()
    source = {'artifact_type': 'P3F9B_MARKET_WIDE_EXACT_SESSION_SCALEOUT', 'resolved_session': {
        'resolved_completed_session': snapshot['research_session'], 'retained_snapshot_session': snapshot['research_session'],
        'exact_session_equality': True, 'incomplete_intraday_used': True}}
    with pytest.raises(ValueError, match='NO_RETAINED_EXACT_COMPLETED_SESSION'):
        latest_exact_session([source])
