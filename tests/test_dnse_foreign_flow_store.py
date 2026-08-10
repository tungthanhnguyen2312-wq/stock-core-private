from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dnse_foreign_flow_capability import normalize_record
from dnse_foreign_flow_store import (
    STATUS_AVAILABLE,
    STATUS_MISSING,
    VALUE_QUALIFICATION_STATUS,
    DnseForeignFlowStoreError,
    build_series,
    read_observations,
    write_observations,
)

# Shape-matched real samples (values from the retained 2026-08-10 pilot evidence,
# operations-review/dnse-foreign-value-integration-20260810/probe_results.json).
def _raw(session_date: str, time_str: str, ticker: str = "HPG",
         buy: int = 47907362050, sell: int = 20350730400) -> dict:
    return {
        "boardId": "G4", "buyTradedAmount": 2232050, "buyVolume": 101,
        "foreignerBuyPossibleQuantity": 3727215320, "foreignerOrderLimitQuantity": 3478309257,
        "marketId": "STO", "sellTradedAmount": 7490400, "sellVolume": 339,
        "symbol": ticker, "time": f"{session_date} {time_str}",
        "totalBuyTradedAmount": buy, "totalBuyVolume": 2173801,
        "totalSellTradedAmount": sell, "totalSellVolume": 920939, "tradingSessionId": "99",
    }


def _normalized(session_date: str, time_str: str = "15:33:11.407", ticker: str = "HPG",
                 buy: int = 47907362050, sell: int = 20350730400) -> dict:
    return normalize_record(_raw(session_date, time_str, ticker, buy, sell),
                             source_endpoint="/price/HPG/foreign-trading")


def _make_runtime_with_ohlcv(tmp_dir: str, ticker: str, dates: list[str]) -> Path:
    """A minimal vn_stock.db stand-in: just enough schema/rows for
    dnse_foreign_flow_store's trading-date gap detection to work against."""
    root = Path(tmp_dir)
    conn = sqlite3.connect(root / "vn_stock.db")
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, "
                 "low REAL, close REAL, volume INTEGER, source TEXT)")
    conn.executemany("INSERT INTO ohlcv (ticker, date, open, high, low, close, volume, source) "
                      "VALUES (?, ?, 1, 1, 1, 1, 1, 'VCI')", [(ticker, d) for d in dates])
    conn.commit()
    conn.close()
    return root


class WriteObservationsTests(unittest.TestCase):
    def test_qualified_buy_sell_values_normalize_to_vnd(self):
        obs = _normalized("2026-08-07")
        self.assertEqual(47907362050, obs["foreign_buy_value"])
        self.assertEqual(20350730400, obs["foreign_sell_value"])

    def test_deterministic_net_derivation(self):
        obs = _normalized("2026-08-07")
        self.assertEqual(47907362050 - 20350730400, obs["foreign_net_value"])

    def test_missing_one_side_blocks_net(self):
        raw = _raw("2026-08-07", "15:33:11.407")
        del raw["totalSellTradedAmount"]
        obs = normalize_record(raw, source_endpoint="x")
        self.assertIsNone(obs["foreign_sell_value"])
        self.assertIsNone(obs["foreign_net_value"])

    def test_write_rejects_ticker_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = _normalized("2026-08-07", ticker="HPG")
            with self.assertRaises(DnseForeignFlowStoreError):
                write_observations(tmp, "VNM", [obs])  # scope mismatch: HPG data under VNM

    def test_write_rejects_observation_without_session_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = dict(_normalized("2026-08-07"))
            del obs["session_date"]
            with self.assertRaises(DnseForeignFlowStoreError):
                write_observations(tmp, "HPG", [obs])

    def test_exact_session_date_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_observations(tmp, "HPG", [_normalized("2026-08-07")])
            stored = read_observations(tmp, "HPG")
            self.assertEqual(1, len(stored))
            self.assertEqual("2026-08-07", stored[0]["session_date"])

    def test_provenance_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_observations(tmp, "HPG", [_normalized("2026-08-07")])
            stored = read_observations(tmp, "HPG")
            self.assertEqual("/price/HPG/foreign-trading", stored[0]["provenance"]["source_endpoint"])

    def test_no_secret_or_auth_fields_serialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_observations(tmp, "HPG", [_normalized("2026-08-07")])
            content = (Path(tmp) / "data" / "dnse-foreign-flow" / "observations" / "HPG.json").read_text()
            for forbidden in ("token", "secret", "signature", "authorization", "x-api-key", "cookie"):
                self.assertNotIn(forbidden, content.lower())

    def test_multi_session_ordering_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            unordered = [_normalized("2026-08-05"), _normalized("2026-08-03"), _normalized("2026-08-04")]
            write_observations(tmp, "HPG", unordered)
            stored = read_observations(tmp, "HPG")
            self.assertEqual(["2026-08-03", "2026-08-04", "2026-08-05"],
                              [o["session_date"] for o in stored])

    def test_reingesting_same_session_overwrites_not_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_observations(tmp, "HPG", [_normalized("2026-08-07", buy=1, sell=1)])
            write_observations(tmp, "HPG", [_normalized("2026-08-07", buy=2, sell=1)])
            stored = read_observations(tmp, "HPG")
            self.assertEqual(1, len(stored))
            self.assertEqual(2, stored[0]["foreign_buy_value"])

    def test_byte_identical_on_repeated_write_of_identical_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_observations(tmp, "HPG", [_normalized("2026-08-07")])
            path = Path(tmp) / "data" / "dnse-foreign-flow" / "observations" / "HPG.json"
            first_bytes = path.read_bytes()
            write_observations(tmp, "HPG", [_normalized("2026-08-07")])
            self.assertEqual(first_bytes, path.read_bytes())


class BuildSeriesTests(unittest.TestCase):
    def test_missing_ticker_reports_missing_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_series(tmp, "NOPE")
            self.assertEqual(STATUS_MISSING, result["status"])
            self.assertEqual([], result["observations"])
            self.assertIsNone(result["cumulative_net_value_vnd"])

    def test_missing_session_is_not_forward_filled(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
            _make_runtime_with_ohlcv(tmp, "HPG", dates)
            # Deliberately skip 2026-08-05 -- a real gap.
            write_observations(tmp, "HPG", [_normalized("2026-08-03"), _normalized("2026-08-04"),
                                             _normalized("2026-08-06"), _normalized("2026-08-07")])
            result = build_series(tmp, "HPG")
            self.assertEqual(4, result["qualified_session_count"])
            self.assertNotIn("2026-08-05", [o["session_date"] for o in result["observations"]])

    def test_incomplete_5_session_window_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
            _make_runtime_with_ohlcv(tmp, "HPG", dates)
            write_observations(tmp, "HPG", [_normalized(d) for d in dates[:3]])  # only 3 of 5
            result = build_series(tmp, "HPG")
            summary = result["window_summaries"]["5_session"]
            self.assertEqual("incomplete", summary["coverage"])
            self.assertIsNone(summary["cumulative_net_value_vnd"])

    def test_5_session_window_with_a_gap_fails_closed_even_at_five_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 6 real trading dates in vn_stock.db; observations skip one in the middle,
            # so 5 *retained* observations still span a gap and must not be "complete".
            dates = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07", "2026-08-10"]
            _make_runtime_with_ohlcv(tmp, "HPG", dates)
            skip_gap = ["2026-08-03", "2026-08-04", "2026-08-06", "2026-08-07", "2026-08-10"]
            write_observations(tmp, "HPG", [_normalized(d) for d in skip_gap])
            result = build_series(tmp, "HPG")
            summary = result["window_summaries"]["5_session"]
            self.assertEqual("incomplete", summary["coverage"])
            self.assertIn("gap", summary["reason"])

    def test_complete_5_session_summary_computed_correctly(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
            _make_runtime_with_ohlcv(tmp, "HPG", dates)
            write_observations(tmp, "HPG", [_normalized(d, buy=100, sell=40) for d in dates])
            result = build_series(tmp, "HPG")
            summary = result["window_summaries"]["5_session"]
            self.assertEqual("complete", summary["coverage"])
            self.assertEqual(5 * (100 - 40), summary["cumulative_net_value_vnd"])
            self.assertEqual(5 * 100, summary["buy_value_vnd"])
            self.assertEqual(5, result["positive_session_count"])
            self.assertEqual(5, result["current_consecutive_net_buy_sessions"])

    def test_unqualified_foreign_volume_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_observations(tmp, "HPG", [_normalized("2026-08-07")])
            result = build_series(tmp, "HPG")
            dumped = json.dumps(result)
            for forbidden in ("foreign_buy_volume", "foreign_sell_volume", "foreign_net_volume"):
                self.assertNotIn(forbidden, dumped)

    def test_foreign_room_does_not_appear_as_interpreted_ownership_data(self):
        # "warnings"/"limitations" legitimately *name* foreign_room/free_float in prose
        # (that IS the warning) -- so this checks only the data-bearing fields
        # (observations, latest_session, cumulative/window figures), never the standing
        # warning text, for the actual room data: raw DNSE field names and their values.
        with tempfile.TemporaryDirectory() as tmp:
            write_observations(tmp, "HPG", [_normalized("2026-08-07")])
            result = build_series(tmp, "HPG")
            data_only = {k: v for k, v in result.items() if k not in ("warnings", "limitations")}
            dumped = json.dumps(data_only)
            for forbidden in ("foreignerBuyPossibleQuantity", "foreignerOrderLimitQuantity",
                               "3727215320", "3478309257", "ownership_pct", "free_float", "foreign_room"):
                self.assertNotIn(forbidden, dumped)

    def test_is_actionable_always_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_observations(tmp, "HPG", [_normalized("2026-08-07")])
            self.assertIs(False, build_series(tmp, "HPG")["is_actionable"])

    def test_qualification_status_is_value_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_observations(tmp, "HPG", [_normalized("2026-08-07")])
            result = build_series(tmp, "HPG")
            self.assertEqual(VALUE_QUALIFICATION_STATUS, result["observations"][0]["qualification_status"])
            self.assertEqual(STATUS_AVAILABLE, result["status"])


class FreshnessTests(unittest.TestCase):
    """The production freshness contract: exact trading-session comparison against the
    caller's own reference session, never calendar-day arithmetic and never a fabricated
    current value for a session that was never retained."""

    def test_no_reference_session_date_reports_unknown_not_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_observations(tmp, "HPG", [_normalized("2026-08-07")])
            result = build_series(tmp, "HPG")  # existing 2-arg call form, unchanged
            self.assertEqual("unknown", result["freshness"]["status"])
            self.assertIsNone(result["freshness"]["sessions_behind"])

    def test_missing_ticker_with_reference_session_is_not_applicable(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_series(tmp, "NOPE", reference_session_date="2026-08-07")
            self.assertEqual("not_applicable", result["freshness"]["status"])
            self.assertIsNone(result["freshness"]["latest_qualified_session_date"])

    def test_latest_session_equal_to_reference_is_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
            _make_runtime_with_ohlcv(tmp, "HPG", dates)
            write_observations(tmp, "HPG", [_normalized(d) for d in dates])
            result = build_series(tmp, "HPG", reference_session_date="2026-08-07")
            freshness = result["freshness"]
            self.assertEqual("current", freshness["status"])
            self.assertEqual(0, freshness["sessions_behind"])
            self.assertEqual("2026-08-07", freshness["reference_session_date"])
            self.assertEqual("2026-08-07", freshness["latest_qualified_session_date"])
            self.assertIsNone(freshness["reason"])

    def test_stale_lag_is_counted_in_exact_trading_sessions_not_calendar_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 2026-08-08/09 are a real weekend -- only 2026-08-10 is a further trading day,
            # so a naive calendar-day count (3 days) must NOT be what sessions_behind reports.
            dates = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07",
                     "2026-08-10"]
            _make_runtime_with_ohlcv(tmp, "HPG", dates)
            write_observations(tmp, "HPG", [_normalized(d) for d in dates if d != "2026-08-10"])
            result = build_series(tmp, "HPG", reference_session_date="2026-08-10")
            freshness = result["freshness"]
            self.assertEqual("stale", freshness["status"])
            self.assertEqual(1, freshness["sessions_behind"])
            self.assertEqual("2026-08-07", freshness["latest_qualified_session_date"])

    def test_stale_without_a_trading_date_reference_still_reports_stale_not_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            # No vn_stock.db ohlcv rows retained for this ticker at all.
            write_observations(tmp, "HPG", [_normalized("2026-08-05")])
            result = build_series(tmp, "HPG", reference_session_date="2026-08-07")
            freshness = result["freshness"]
            self.assertEqual("stale", freshness["status"])
            self.assertIsNone(freshness["sessions_behind"])

    def test_retained_session_after_reference_fails_closed_as_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-08-03", "2026-08-04"]
            _make_runtime_with_ohlcv(tmp, "HPG", dates)
            write_observations(tmp, "HPG", [_normalized(d) for d in dates])
            result = build_series(tmp, "HPG", reference_session_date="2026-08-03")
            self.assertEqual("unknown", result["freshness"]["status"])

    def test_freshness_never_fabricates_a_value_for_the_reference_session(self):
        """A stale result must still expose only the actually-retained latest session --
        never a synthesized observation for the reference date itself."""
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-08-03", "2026-08-06", "2026-08-07"]
            _make_runtime_with_ohlcv(tmp, "HPG", dates)
            write_observations(tmp, "HPG", [_normalized("2026-08-03")])
            result = build_series(tmp, "HPG", reference_session_date="2026-08-07")
            self.assertEqual(1, len(result["observations"]))
            self.assertEqual("2026-08-03", result["observations"][0]["session_date"])
            self.assertEqual("stale", result["freshness"]["status"])


if __name__ == "__main__":
    unittest.main()
