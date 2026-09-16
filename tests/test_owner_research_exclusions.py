from __future__ import annotations

from pathlib import Path

import pytest

import owner_research_exclusions as ore


def test_missing_file_is_the_honest_not_provided_default(tmp_path: Path):
    result = ore.load_research_exclusions(tmp_path)
    assert result["status"] == "NOT_PROVIDED"
    assert result["excluded_tickers"] == []
    assert ore.excluded_ticker_set(result) == frozenset()


def test_add_then_remove_round_trips_through_the_local_file(tmp_path: Path):
    ore.add_research_exclusion("DLQ", reason="DELISTED_HISTORICAL", excluded_since="2026-09-16", portfolio_root=tmp_path)
    result = ore.load_research_exclusions(tmp_path)
    assert result["status"] == "PROVIDED"
    assert ore.excluded_ticker_set(result) == frozenset({"DLQ"})
    entry = result["excluded_tickers"][0]
    assert entry == {"ticker": "DLQ", "reason": "DELISTED_HISTORICAL", "excluded_since": "2026-09-16"}

    ore.remove_research_exclusion("DLQ", portfolio_root=tmp_path)
    removed = ore.load_research_exclusions(tmp_path)
    assert removed["status"] == "NOT_PROVIDED"
    assert removed["excluded_tickers"] == []


def test_adding_the_same_ticker_twice_replaces_not_duplicates(tmp_path: Path):
    ore.add_research_exclusion("DLQ", reason="FIRST_REASON", portfolio_root=tmp_path)
    ore.add_research_exclusion("DLQ", reason="UPDATED_REASON", portfolio_root=tmp_path)
    result = ore.load_research_exclusions(tmp_path)
    assert len(result["excluded_tickers"]) == 1
    assert result["excluded_tickers"][0]["reason"] == "UPDATED_REASON"


def test_invalid_ticker_is_rejected_not_silently_dropped(tmp_path: Path):
    with pytest.raises(ore.OwnerResearchExclusionError):
        ore.add_research_exclusion("not a ticker!!", portfolio_root=tmp_path)


def test_the_file_never_stores_anything_beyond_ticker_reason_and_date(tmp_path: Path):
    ore.add_research_exclusion("DLQ", reason="DELISTED_HISTORICAL", excluded_since="2026-09-16", portfolio_root=tmp_path)
    path = ore.default_exclusions_path(tmp_path)
    raw = path.read_text(encoding="utf-8")
    assert "DLQ" in raw
    assert set(__import__("json").loads(raw)["excluded_tickers"][0].keys()) == {"ticker", "reason", "excluded_since"}
