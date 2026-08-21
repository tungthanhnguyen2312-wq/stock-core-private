import pytest

from evidence_aware_candidate_comparison import build, validate_request
from run_evidence_aware_candidate_comparison import inputs, make, pilot_requests


def test_request_rejects_unknown_session_ticker_dimension_and_invalid_size():
    known = {'AAA', 'BBB'}
    base = {'research_session': '2026-08-20', 'tickers': ['AAA', 'BBB'], 'dimensions': ['CURRENT_OBSERVABLE_STATE']}
    assert validate_request(base, known, '2026-08-20') == ('AAA', 'BBB')
    for changed, code in (({'research_session': '2026-08-19'}, 'MIXED_OR_UNKNOWN_RESEARCH_SESSION'),
                          ({'tickers': ['AAA', 'ZZZ']}, 'UNKNOWN_TICKER'),
                          ({'dimensions': ['INVENTED']}, 'UNSUPPORTED_COMPARISON_DIMENSION'),
                          ({'tickers': ['AAA']}, 'INVALID_SHORTLIST_SIZE')):
        request = {**base, **changed}
        with pytest.raises(ValueError, match=code): validate_request(request, known, '2026-08-20')


def test_real_pilots_are_deterministic_and_do_not_force_semantic_comparison():
    source = inputs(); requests = pilot_requests(); first = [make(request, source) for request in requests]
    second = [make(request, source) for request in requests]
    assert [item['output_identity'] for item in first] == [item['output_identity'] for item in second]
    assert len(first[0]['ordered_tickers']) == 25
    assert all(item['authority_boundary']['not_ranking_or_recommendation'] for item in first)
    assert all(any(row['section'] == 'MARKET_CONTEXT' for row in item['matrix']) for item in first)
    assert all(any(row['section'] == 'DOWNSIDE_UNCERTAINTY' for row in item['matrix']) for item in first)
    for item in first:
        fundamental = next(row for row in item['matrix'] if row['dimension'] == 'individual_like_for_like_fundamental_values')
        assert fundamental['comparability'] == 'COMPARISON_UNAVAILABLE'
        relative = next(row for row in item['matrix'] if row['dimension'] == 'relative_context')
        assert relative['comparability'] in {'COMPARABLE', 'NOT_COMPARABLE_COHORT'}
