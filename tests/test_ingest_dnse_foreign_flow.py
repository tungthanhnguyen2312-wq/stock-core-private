from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from ingest_dnse_foreign_flow import extract_normalized_observations  # noqa: E402


def _ok_result(ticker: str, session_time: str, **overrides) -> dict:
    raw = {
        "boardId": "G1", "buyTradedAmount": 100, "buyVolume": 10,
        "foreignerBuyPossibleQuantity": 1000, "foreignerOrderLimitQuantity": 900,
        "marketId": "STO", "sellTradedAmount": 40, "sellVolume": 4,
        "symbol": ticker, "time": session_time, "totalBuyTradedAmount": 100,
        "totalBuyVolume": 10, "totalSellTradedAmount": 40, "totalSellVolume": 4,
        "tradingSessionId": "1",
    }
    raw.update(overrides)
    return {"capability": "foreign_trading", "ok": True, "endpoint": f"/price/{ticker}/foreign-trading",
            "query_sent": {"from": 1, "to": 2}, "body_redacted": {"foreigners": [raw]}}


class ExtractNormalizedObservationsTests(unittest.TestCase):
    def test_ok_result_normalizes_and_groups_by_ticker(self):
        evidence = {"results": [_ok_result("HPG", "2026-08-07 15:33:11.407")]}
        by_ticker = extract_normalized_observations(evidence)
        self.assertEqual(["HPG"], list(by_ticker.keys()))
        self.assertEqual(1, len(by_ticker["HPG"]))
        self.assertEqual(100, by_ticker["HPG"][0]["foreign_buy_value"])

    def test_failed_call_is_skipped_not_fabricated(self):
        evidence = {"results": [
            {"capability": "foreign_trading", "ok": False, "endpoint": "/price/HPG/foreign-trading",
             "error_code": "http_status_400"},
        ]}
        self.assertEqual({}, extract_normalized_observations(evidence))

    def test_empty_foreigners_list_is_skipped(self):
        evidence = {"results": [
            {"capability": "foreign_trading", "ok": True, "endpoint": "/price/HPG/foreign-trading",
             "body_redacted": {"foreigners": []}},
        ]}
        self.assertEqual({}, extract_normalized_observations(evidence))

    def test_non_foreign_trading_calls_ignored(self):
        evidence = {"results": [
            {"capability": "working_dates", "ok": True, "endpoint": "/market/working-dates",
             "body_redacted": {"workingDates": ["2026-08-10"]}},
        ]}
        self.assertEqual({}, extract_normalized_observations(evidence))

    def test_malformed_amount_unit_mismatch_is_skipped_not_fabricated(self):
        """A raw record whose amount field is not a valid non-negative number (a stand-in
        for a unit/type mismatch at the source) fails normalize_record() and is skipped
        entirely -- never coerced into a number, never silently zeroed."""
        evidence = {"results": [_ok_result("HPG", "2026-08-07 15:33:11.407", totalBuyTradedAmount=-1)]}
        self.assertEqual({}, extract_normalized_observations(evidence))

    def test_multiple_tickers_and_sessions_grouped_correctly(self):
        evidence = {"results": [
            _ok_result("HPG", "2026-08-03 15:33:11.000"),
            _ok_result("HPG", "2026-08-04 15:33:11.000"),
            _ok_result("VNM", "2026-08-03 15:33:11.000"),
        ]}
        by_ticker = extract_normalized_observations(evidence)
        self.assertEqual({"HPG", "VNM"}, set(by_ticker.keys()))
        self.assertEqual(2, len(by_ticker["HPG"]))
        self.assertEqual(1, len(by_ticker["VNM"]))


if __name__ == "__main__":
    unittest.main()
