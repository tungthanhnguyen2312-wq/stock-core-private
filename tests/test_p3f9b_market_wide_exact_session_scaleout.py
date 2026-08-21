"""Tests for P3-F9B: Market-Wide Exact-Session Snapshot Scale-Out."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
from typing import Any

import mva_exact_session_snapshot as m

VN = timezone(timedelta(hours=7))


def mock_fetcher_mixed(_capability: str, **kwargs: Any) -> dict[str, Any]:
    target = datetime(2026, 8, 20, 9, tzinfo=VN)
    previous = target - timedelta(days=1)
    symbol = kwargs.get("query", {}).get("symbol")
    if symbol == "GOOD":
        return {
            "ok": True,
            "endpoint": "/price/ohlc",
            "body": {
                "t": [int(previous.timestamp()), int(target.timestamp())],
                "o": [10.0, 10.5],
                "h": [10.2, 11.0],
                "l": [9.8, 10.2],
                "c": [10.0, 10.8],
                "v": [1000, 2000],
            },
        }
    if symbol == "MISSING_EXACT":
        return {
            "ok": True,
            "endpoint": "/price/ohlc",
            "body": {
                "t": [int(previous.timestamp())],
                "o": [10.0],
                "h": [10.2],
                "l": [9.8],
                "c": [10.0],
                "v": [1000],
            },
        }
    if symbol == "MALFORMED":
        return {"ok": True, "endpoint": "/price/ohlc", "body": {"t": [], "c": []}}
    if symbol == "REJECTED":
        return {"ok": False, "endpoint": "/price/ohlc", "error_code": "http_status_400"}
    if symbol == "TRANSPORT_ERR":
        return {"ok": False, "endpoint": "/price/ohlc", "error_code": "request_failed_connection_timeout"}
    return {"ok": False, "endpoint": "/price/ohlc", "error_code": "http_status_404"}


class TestP3F9BMarketWideScaleout(unittest.TestCase):
    def test_full_candidate_disposition_reconciliation(self):
        candidates = ["GOOD", "MISSING_EXACT", "MALFORMED", "REJECTED", "TRANSPORT_ERR"]
        snap = m.materialize_snapshot(
            candidates=candidates,
            requested_at=datetime(2026, 8, 20, 16, tzinfo=VN),
            api_key="k",
            api_secret="s",
            fetcher=mock_fetcher_mixed,
            workers=2,
        )
        self.assertEqual("2026-08-20", snap["resolved_completed_session"])
        self.assertEqual("2026-08-20", snap["retained_snapshot_session"])
        self.assertEqual(5, snap["candidate_count"])
        self.assertEqual(5, snap["attempted_candidate_count"])
        self.assertEqual(1, snap["exact_session_observed_count"])
        self.assertEqual(4, snap["missing_current_session_count"])
        self.assertEqual(0, snap["unattempted_without_explicit_disposition"])

        # Dispositions
        self.assertEqual("EXACT_SESSION_RETAINED", snap["records"]["GOOD"]["disposition"])
        self.assertEqual("SESSION_MISSING", snap["records"]["MISSING_EXACT"]["disposition"])
        self.assertEqual("MALFORMED", snap["records"]["MALFORMED"]["disposition"])
        self.assertEqual("PROVIDER_REJECTED", snap["records"]["REJECTED"]["disposition"])
        self.assertEqual("TRANSPORT_FAILED", snap["records"]["TRANSPORT_ERR"]["disposition"])

        # Count reconciliation
        counts = snap["disposition_counts"]
        self.assertEqual(1, counts["EXACT_SESSION_RETAINED"])
        self.assertEqual(1, counts["SESSION_MISSING"])
        self.assertEqual(1, counts["MALFORMED"])
        self.assertEqual(1, counts["PROVIDER_REJECTED"])
        self.assertEqual(1, counts["TRANSPORT_FAILED"])
        self.assertEqual(0, counts["NOT_ATTEMPTED"])
        self.assertEqual(sum(counts.values()), snap["candidate_count"])

    def test_pre_classification_contract(self):
        candidates = ["AAA", "BBB", "CCC"]
        snap = m.materialize_snapshot(
            candidates=candidates,
            requested_at=datetime(2026, 8, 20, 16, tzinfo=VN),
            api_key="k",
            api_secret="s",
            fetcher=mock_fetcher_mixed,
            workers=1,
        )
        pre = snap["candidate_pre_classification"]
        self.assertEqual(3, pre["ATTEMPT_ELIGIBLE"])
        self.assertEqual(0, pre["NOT_APPLICABLE"])
        self.assertEqual(0, pre["INSTRUMENT_UNRESOLVED"])
        self.assertEqual(0, pre["EXPLICITLY_EXCLUDED_BY_EXISTING_CONTRACT"])

    def test_zero_ticker_specific_branch_and_authority_boundary(self):
        snap = m.materialize_snapshot(
            candidates=["GOOD"],
            requested_at=datetime(2026, 8, 20, 16, tzinfo=VN),
            api_key="k",
            api_secret="s",
            fetcher=mock_fetcher_mixed,
            workers=1,
        )
        self.assertEqual("DESCRIPTIVE_QUALIFIED_ONLY", snap["authority_boundary"]["CURRENT_MARKET"])
        self.assertEqual("NOT_PROMOTED", snap["authority_boundary"]["RAW_AS_TRADED"])
        self.assertEqual("BLOCKED", snap["authority_boundary"]["HISTORICAL_PIT"])
        self.assertFalse(snap["authority_boundary"]["runtime_database_mutated"])
        self.assertFalse(snap["is_actionable_for_execution"])
        self.assertFalse(snap["pit_backtest_eligible"])
        self.assertEqual("BLOCKED", snap["liquidity_sizing_authority"])
        self.assertEqual("CURRENT_DESCRIPTIVE_ONLY", snap["valuation_scope"])

    def test_snapshot_keeps_close_in_a_different_numeric_representation_than_ohl(self):
        snap = m.materialize_snapshot(
            candidates=["GOOD"], requested_at=datetime(2026, 8, 20, 16, tzinfo=VN),
            api_key="k", api_secret="s", fetcher=mock_fetcher_mixed, workers=1,
        )
        row = next(row for row in snap["records"]["GOOD"]["observations"] if row["session"] == "2026-08-20")
        self.assertEqual((10.5, 11.0, 10.2), (row["open"], row["high"], row["low"]))
        self.assertEqual(10800.0, row["close"])


if __name__ == "__main__":
    unittest.main()
