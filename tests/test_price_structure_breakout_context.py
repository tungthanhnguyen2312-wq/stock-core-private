import json
from pathlib import Path

from run_price_structure_breakout_context import ROOT, run


def test_price_structure_is_deterministic_close_only_and_excludes_current_bar():
    first, daily, review, scenario = run()
    second, _, _, _ = run()
    assert first['artifact_identity'] == second['artifact_identity']
    assert first['cohort']['member_count'] == 523
    assert first['coverage']['usable_history_count'] == 523
    assert first['coverage']['insufficient_history_count'] == 0
    assert first['coverage']['rolling_50_session_available_count'] == 0
    assert len(daily['records']) == 523
    assert len(review['entries']) == 25
    assert len(scenario['entries']) == 25
    snapshot = json.loads((ROOT / 'operations-review/p3f9b-market-wide-exact-session-scaleout-20260820/'
                           'p3f9b_mva_exact_session_snapshot.json').read_text(encoding='utf8'))
    record = first['records'][0]
    source = snapshot['records'][record['ticker']]['observations']
    assert record['levels']['prior_19_session_close_resistance']['value'] == max(float(x['close']) for x in source[:-1])
    assert record['levels']['prior_19_session_close_support']['value'] == min(float(x['close']) for x in source[:-1])
    assert record['method']['current_bar_excluded_from_prior_levels'] is True
    assert record['method']['level_series'].startswith('close_only')
    assert record['authority_tier'] == 'SHADOW_ONLY'
    assert 'PROVIDER_RELATIVE_VOLUME_PROXY_NOT_LIQUIDITY' in record['warnings']
    assert first['authority_boundary']['not_signal_recommendation_or_expected_return']
