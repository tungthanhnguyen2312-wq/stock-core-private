from run_market_regime_breadth_context import run
from run_evidence_aware_research_screener import run as screener_run
from market_regime_breadth_context import review_overlay


def test_market_context_reconciles_to_cohort_and_screener_without_changing_lenses():
    first = run(); second = run(); screen, _ = screener_run()
    assert first['artifact_identity'] == second['artifact_identity']
    assert first['cohort']['member_count'] == 523
    trend = first['breadth']['trend']; momentum = first['breadth']['momentum']
    assert trend['above_ma20_count'] + trend['at_or_below_ma20_count'] + trend['unavailable_count'] == 523
    assert momentum['positive_count'] + momentum['negative_count'] + momentum['zero_count'] + momentum['unavailable_count'] == 523
    assert first['breadth']['provider_relative_volume']['available_count'] == 523
    counts = {row['query_name']: row['result_count'] for row in screen['presets']}
    assert first['research_participation']['positive_trend_research_count'] == counts['POSITIVE_TREND_RESEARCH'] == 193
    assert first['research_participation']['weak_trend_research_count'] == counts['WEAK_TREND_RESEARCH'] == 320
    assert first['authority_boundary']['no_eligibility_mutation']
    overlay = review_overlay(first)
    assert len(overlay['entries']) == 25
    assert overlay['market_context_identity'] == first['artifact_identity']
