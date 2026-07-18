"""Phase 5 canonical news ticker mapping tests."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from news_ticker_mapping import (  # noqa: E402
    Alias,
    TickerAliasRegistry,
    deduplicate_articles,
    map_article,
    summarize_news,
)


class NewsTickerMappingPhase5Tests(unittest.TestCase):
    def setUp(self):
        self.registry = TickerAliasRegistry.from_csv(ROOT / "config" / "ticker_aliases.csv")

    def test_pan_company_name_maps_to_pan(self):
        result = map_article({"title": "Tập đoàn PAN mở rộng vùng nguyên liệu"}, self.registry)
        self.assertEqual(result["accepted"][0]["ticker"], "PAN")
        self.assertEqual(result["accepted"][0]["match_method"], "exact_company_name")
        self.assertGreaterEqual(result["accepted"][0]["confidence"], 0.9)

    def test_pan_legal_name_maps_to_pan(self):
        result = map_article(
            {"title": "Công ty Cổ phần Tập đoàn PAN công bố nghị quyết"}, self.registry
        )
        self.assertEqual(result["accepted"][0]["ticker"], "PAN")
        self.assertEqual(result["accepted"][0]["match_method"], "exact_legal_name")
        self.assertEqual(result["accepted"][0]["confidence"], 1.0)

    def test_generic_uppercase_token_not_mapped_as_ticker(self):
        registry = TickerAliasRegistry()
        registry.add_metadata_aliases([{"ticker": "PAN"}])
        result = map_article({"title": "PAN là giải pháp xử lý dữ liệu phổ biến"}, registry)
        self.assertEqual(result["accepted"], [])
        self.assertEqual(result["candidates"], [])

    def test_one_article_can_map_multiple_tickers(self):
        registry = TickerAliasRegistry([
            Alias("PAN", "PAN Group", "registered_alias", 90),
            Alias("HPG", "Tập đoàn Hòa Phát", "company_name", 95),
        ])
        result = map_article(
            {"title": "PAN Group ký thỏa thuận với Tập đoàn Hòa Phát"}, registry
        )
        self.assertEqual({item["ticker"] for item in result["accepted"]}, {"PAN", "HPG"})

    def test_low_confidence_match_is_not_auto_accepted(self):
        registry = TickerAliasRegistry([Alias("PAN", "La Vie", "brand", 80)])
        result = map_article({"title": "La Vie ra mắt sản phẩm mới"}, registry)
        self.assertEqual(result["accepted"], [])
        self.assertEqual(result["candidates"][0]["ticker"], "PAN")
        self.assertLess(result["candidates"][0]["confidence"], 0.9)

    def test_no_company_news_returns_explicit_status(self):
        summary = summarize_news(
            "PAN",
            [{
                "published_utc": "2026-07-12T10:00:00Z",
                "region": "vn",
                "source": "Example",
                "title": "Thị trường chứng khoán điều chỉnh",
                "link": "https://example.com/market",
            }],
            self.registry,
            now=datetime(2026, 7, 13, tzinfo=timezone.utc),
        )
        self.assertEqual(summary["status"], "no_company_specific_news")
        self.assertEqual(summary["company_news_count"], 0)
        self.assertEqual(summary["market_news_count"], 1)
        self.assertEqual(summary["items"], [])

    def test_articles_are_deduplicated_by_canonical_link(self):
        articles = [
            {"title": "A", "link": "https://example.com/a?utm=1"},
            {"title": "A copy", "link": "https://example.com/a?utm=2"},
        ]
        self.assertEqual(len(deduplicate_articles(articles)), 1)


if __name__ == "__main__":
    unittest.main()
