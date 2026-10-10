"""Research overlap only. No sizing and no ticker-specific branches."""
from __future__ import annotations

import pytest

import stocklookup_core.portfolio.portfolio_research_decision_workbench as workbench


def test_concentration_overlap_and_explicit_rank_are_not_allocation():
    built = workbench.build_workbench([
        {"ticker": "hpg", "sector": "materials", "style": "cyclical", "thesis_ids": ["steel"], "event_ids": [], "liquidity_context": "TRADED", "measurements": {"research_priority": 2}},
        {"ticker": "hsg", "sector": "materials", "style": "cyclical", "thesis_ids": ["steel"], "event_ids": ["e1"], "liquidity_context": "TRADED", "measurements": {"research_priority": 5}},
        {"ticker": "fpt", "sector": "technology", "style": "growth", "thesis_ids": ["software"], "event_ids": ["e1"], "measurements": {}},
    ], objective="research_priority")
    assert built["sector_concentration"]["counts"]["materials"] == 2
    assert built["overlaps"]["shared_thesis_ids"]["steel"] == ["HPG", "HSG"]
    assert built["overlaps"]["shared_event_ids"]["e1"] == ["FPT", "HSG"]
    assert built["ranking"]["ordered_tickers"] == ["HSG", "HPG"]
    assert built["ranking"]["measurement_missing"] == ["FPT"]
    assert built["ranking"]["is_capital_allocation"] is False
    assert built["position_size"] is None
    assert built["order"] is None
    assert built["is_actionable"] is False


def test_correlation_requires_aligned_current_series():
    built = workbench.build_workbench([
        {"ticker": "AAA", "current_returns": [0.01, 0.02, -0.01, 0.00]},
        {"ticker": "BBB", "current_returns": [0.02, 0.01, -0.02, 0.01]},
        {"ticker": "CCC", "current_returns": [0.01, 0.02]},
    ])
    by_pair = {(item["left"], item["right"]): item for item in built["current_correlation"]["pairs"]}
    assert by_pair[("AAA", "BBB")]["status"] == "CURRENT_RESEARCH_ONLY"
    assert by_pair[("AAA", "BBB")]["authority"] == "CURRENT_RESEARCH_ONLY_NOT_PIT"
    assert by_pair[("AAA", "CCC")]["status"] == "NOT_COMPARABLE"
    assert built["ranking"]["status"] == "OBJECTIVE_NOT_SUPPLIED"


def test_duplicate_ticker_collapses_and_size_is_rejected():
    built = workbench.build_workbench([
        {"ticker": "PNJ", "sector": "retail"},
        {"ticker": "pnj", "sector": "retail"},
    ])
    assert built["member_count"] == 1
    assert built["duplicate_tickers_collapsed"] == ["PNJ"]
    with pytest.raises(ValueError):
        workbench.build_workbench([{"ticker": "PNJ", "position_size": 10}])


def test_identity_is_stable():
    rows = [{"ticker": "QNS", "sector": "food"}, {"ticker": "PAN", "sector": "food"}]
    assert workbench.build_workbench(rows)["workbench_identity"] == workbench.build_workbench(list(reversed(rows)))["workbench_identity"]


def test_concentration_counts_opportunities_not_owner_exposure():
    built = workbench.build_workbench([{"ticker": "AAA", "sector": "materials"}, {"ticker": "BBB", "sector": "materials"}])
    assert built["sector_concentration"]["basis"] == workbench.OPPORTUNITY_COUNT_BASIS
    assert built["style_concentration"]["basis"] == workbench.OPPORTUNITY_COUNT_BASIS


def test_correlation_is_comparable_only_on_shared_dates():
    dates = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06"]
    built = workbench.build_workbench([
        {"ticker": "AAA", "current_returns": [0.01, 0.02, -0.01, 0.00], "current_return_dates": dates},
        {"ticker": "BBB", "current_returns": [0.02, -0.02, 0.01], "current_return_dates": dates[1:]},
        {"ticker": "CCC", "current_returns": [0.01, 0.02, -0.01, 0.00]},
        {"ticker": "DDD", "current_returns": [0.01, 0.02, 0.03], "current_return_dates": ["2026-10-01", "2026-10-01", "2026-10-02"]},
    ])
    by_pair = {(item["left"], item["right"]): item for item in built["current_correlation"]["pairs"]}
    aligned = by_pair[("AAA", "BBB")]
    assert aligned["comparable"] is True
    assert aligned["aligned_points"] == 3
    assert aligned["date_alignment"] == workbench.ALIGNMENT_VERIFIED
    assert by_pair[("AAA", "CCC")]["status"] == "NOT_COMPARABLE"
    assert by_pair[("AAA", "CCC")]["date_alignment"] == "DATES_ONE_SIDED"
    assert by_pair[("AAA", "DDD")]["date_alignment"] == "DATES_DUPLICATED"
    assert by_pair[("AAA", "DDD")]["comparable"] is False
