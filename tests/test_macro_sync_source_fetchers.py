"""Offline tests for macro_sync.py's per-source fetchers (FRED/Yahoo/World Bank
success+failure), its delegation to the new first-party VCB/SJC adapters, and its atomic
snapshot-file write behavior (see docs/DECISIONS.md
MACRO_NETWORK_GOVERNANCE_AND_VNSTOCK_DECOUPLING_V1). No real network is used anywhere in this
file: `requests.get` and the adapter functions are monkeypatched.
"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import macro_sync as ms  # noqa: E402
import macro_sjc_adapter
import macro_vcb_adapter


class FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data

    def json(self):
        return self._json_data


def _quiet_sleep(cls):
    """Patch time.sleep and random.uniform so retry-bounded tests run instantly and
    deterministically."""
    cls.enterClassContext(mock.patch.object(ms.time, "sleep", lambda *_a, **_k: None))
    cls.enterClassContext(mock.patch.object(ms.random, "uniform", lambda *_a, **_k: 0))


class FredFetcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _quiet_sleep(cls)

    def test_success_parses_csv_rows(self):
        csv_text = "DATE,FEDFUNDS\n2026-09-08,5.25\n2026-09-09,5.25\n"
        with mock.patch.object(ms.requests, "get", return_value=FakeResponse(200, text=csv_text)):
            pairs = ms.fetch_fred("FEDFUNDS")
        self.assertEqual(pairs, [("2026-09-08", 5.25), ("2026-09-09", 5.25)])

    def test_dot_missing_marker_is_dropped_not_coerced_to_zero(self):
        csv_text = "DATE,FEDFUNDS\n2026-09-08,.\n2026-09-09,5.25\n"
        with mock.patch.object(ms.requests, "get", return_value=FakeResponse(200, text=csv_text)):
            pairs = ms.fetch_fred("FEDFUNDS")
        self.assertEqual(pairs, [("2026-09-09", 5.25)])

    def test_persistent_transport_failure_returns_empty_not_an_exception(self):
        with mock.patch.object(ms.requests, "get", side_effect=requests.ConnectionError("down")):
            pairs = ms.fetch_fred("FEDFUNDS")
        self.assertEqual(pairs, [])

    def test_bounded_retry_gives_up_after_max_retry_attempts(self):
        with mock.patch.object(ms.requests, "get", side_effect=requests.Timeout("t")) as get:
            ms.fetch_fred("FEDFUNDS")
        self.assertEqual(get.call_count, ms.MAX_RETRY)


class YahooFetcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _quiet_sleep(cls)

    def test_success_parses_chart_json(self):
        payload = {"chart": {"result": [{
            "timestamp": [1893456000, 1893542400],
            "indicators": {"quote": [{"close": [5000.1, 5010.2]}]},
        }]}}
        with mock.patch.object(ms.requests, "get", return_value=FakeResponse(200, json_data=payload)):
            pairs = ms.fetch_yahoo("^GSPC", "1y")
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0][1], 5000.1)

    def test_null_close_bar_is_skipped_not_coerced_to_zero(self):
        payload = {"chart": {"result": [{
            "timestamp": [1893456000, 1893542400],
            "indicators": {"quote": [{"close": [None, 5010.2]}]},
        }]}}
        with mock.patch.object(ms.requests, "get", return_value=FakeResponse(200, json_data=payload)):
            pairs = ms.fetch_yahoo("^GSPC", "1y")
        self.assertEqual(len(pairs), 1)

    def test_schema_change_is_reported_as_empty_not_an_exception(self):
        with mock.patch.object(ms.requests, "get", return_value=FakeResponse(200, json_data={"unexpected": True})):
            pairs = ms.fetch_yahoo("^GSPC", "1y")
        self.assertEqual(pairs, [])

    def test_transport_failure_returns_empty(self):
        with mock.patch.object(ms.requests, "get", side_effect=requests.ConnectionError("down")):
            pairs = ms.fetch_yahoo("^GSPC", "1y")
        self.assertEqual(pairs, [])


class WorldBankFetcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _quiet_sleep(cls)

    def test_success_sorts_ascending_and_reformats_year_as_date(self):
        payload = [{}, [{"date": "2025", "value": 3.2}, {"date": "2024", "value": 2.8}]]
        with mock.patch.object(ms.requests, "get", return_value=FakeResponse(200, json_data=payload)):
            pairs = ms.fetch_wb("FP.CPI.TOTL.ZG")
        self.assertEqual(pairs, [("2024-12-31", 2.8), ("2025-12-31", 3.2)])

    def test_null_value_year_is_excluded(self):
        payload = [{}, [{"date": "2025", "value": None}, {"date": "2024", "value": 2.8}]]
        with mock.patch.object(ms.requests, "get", return_value=FakeResponse(200, json_data=payload)):
            pairs = ms.fetch_wb("FP.CPI.TOTL.ZG")
        self.assertEqual(pairs, [("2024-12-31", 2.8)])

    def test_empty_series_returns_empty(self):
        with mock.patch.object(ms.requests, "get", return_value=FakeResponse(200, json_data=[{}, None])):
            pairs = ms.fetch_wb("FP.CPI.TOTL.ZG")
        self.assertEqual(pairs, [])

    def test_transport_failure_returns_empty(self):
        with mock.patch.object(ms.requests, "get", side_effect=requests.ConnectionError("down")):
            pairs = ms.fetch_wb("FP.CPI.TOTL.ZG")
        self.assertEqual(pairs, [])


class VcbSjcDelegationTests(unittest.TestCase):
    """fetch_vcb_today()/fetch_sjc_today() must delegate to the new first-party adapters
    (never to vnstock) and translate a non-OK adapter result into an empty pairs list without
    raising -- confirming macro remains non-blocking when either fails."""

    @classmethod
    def setUpClass(cls):
        _quiet_sleep(cls)

    def test_fetch_vcb_today_returns_adapter_pairs_on_success(self):
        ok = macro_vcb_adapter.MacroFetchResult([("2026-09-10", 26690.0)], "OK", None)
        with mock.patch.object(macro_vcb_adapter, "fetch_vcb_usd_sell_rate", return_value=ok):
            pairs = ms.fetch_vcb_today()
        self.assertEqual(pairs, [("2026-09-10", 26690.0)])

    def test_fetch_vcb_today_returns_empty_on_adapter_failure_without_raising(self):
        failed = macro_vcb_adapter.MacroFetchResult([], "REQUEST_FAILED", "TIMEOUT")
        with mock.patch.object(macro_vcb_adapter, "fetch_vcb_usd_sell_rate", return_value=failed):
            pairs = ms.fetch_vcb_today()
        self.assertEqual(pairs, [])

    def test_fetch_sjc_today_returns_adapter_pairs_on_success(self):
        ok = macro_sjc_adapter.MacroFetchResult([("2026-09-10", 82000000.0)], "OK", None)
        with mock.patch.object(macro_sjc_adapter, "fetch_sjc_gold_sell_price", return_value=ok):
            pairs = ms.fetch_sjc_today()
        self.assertEqual(pairs, [("2026-09-10", 82000000.0)])

    def test_fetch_sjc_today_returns_empty_on_adapter_failure_without_raising(self):
        failed = macro_sjc_adapter.MacroFetchResult([], "PARSE_FAILED", "SELL_VALUE_NOT_NUMERIC")
        with mock.patch.object(macro_sjc_adapter, "fetch_sjc_gold_sell_price", return_value=failed):
            pairs = ms.fetch_sjc_today()
        self.assertEqual(pairs, [])


class PartialSourceFailureUpsertTests(unittest.TestCase):
    """Multi-source partial-failure semantics at the acquisition/DB layer: a failed source
    contributes zero rows and never crashes the run; other sources' rows are retained
    independently (single-refresh-owner, per-series partial success, per docs/STATE.md)."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        ms.init_db(self.conn)

    def test_one_source_failing_leaves_others_populated(self):
        self.assertEqual(ms.upsert(self.conn, "us_fedfunds", [("2026-09-10", 5.25)]), 1)
        self.assertEqual(ms.upsert(self.conn, "usdvnd_vcb", []), 0)  # VCB failed this run
        total = self.conn.execute("SELECT COUNT(*) FROM macro").fetchone()[0]
        self.assertEqual(total, 1)

    def test_all_sources_failing_leaves_db_untouched_without_crashing(self):
        for series in ("us_fedfunds", "usdvnd_vcb", "gold_sjc"):
            self.assertEqual(ms.upsert(self.conn, series, []), 0)
        total = self.conn.execute("SELECT COUNT(*) FROM macro").fetchone()[0]
        self.assertEqual(total, 0)

    def test_vcb_and_sjc_failing_together_does_not_affect_unrelated_series(self):
        self.assertEqual(ms.upsert(self.conn, "usdvnd_vcb", []), 0)
        self.assertEqual(ms.upsert(self.conn, "gold_sjc", []), 0)
        self.assertEqual(ms.upsert(self.conn, "dxy", [("2026-09-10", 101.2)]), 1)
        rows = self.conn.execute("SELECT series FROM macro").fetchall()
        self.assertEqual(rows, [("dxy",)])


class AtomicSnapshotWriteTests(unittest.TestCase):
    def test_writer_output_is_committed_to_target_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "macro_snapshot.csv"
            ms.atomic_write_via(target, lambda p: Path(p).write_text("series,value\ndxy,100\n", encoding="utf-8"))
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "series,value\ndxy,100\n")

    def test_crash_during_write_never_leaves_a_partial_target_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "macro_snapshot.csv"
            target.write_text("series,value\ndxy,99\n", encoding="utf-8")  # pre-existing good file

            def boom(_path):
                raise RuntimeError("simulated crash mid-write")

            with self.assertRaises(RuntimeError):
                ms.atomic_write_via(target, boom)
            # The pre-existing retained snapshot must survive a crash untouched -- never a
            # half-written replacement masquerading as complete.
            self.assertEqual(target.read_text(encoding="utf-8"), "series,value\ndxy,99\n")

    def test_crash_during_write_leaves_no_stray_temp_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "macro_snapshot.csv"

            def boom(_path):
                raise RuntimeError("simulated crash mid-write")

            with self.assertRaises(RuntimeError):
                ms.atomic_write_via(target, boom)
            leftover = list(Path(tmp).glob(".*macro_snapshot.csv*.tmp"))
            self.assertEqual(leftover, [])


if __name__ == "__main__":
    unittest.main()
