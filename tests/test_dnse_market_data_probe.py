from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from dnse_market_data import MARKET_DATA_ENDPOINTS
from tools.dnse_market_data_probe import (
    CREDENTIAL_INJECTION_REQUIRED,
    CURRENT_STATE_TICKER,
    CURRENT_STATE_WINDOW,
    INDEX_RETURN_SERIES_BENCHMARK,
    INDEX_RETURN_SERIES_WINDOW,
    PRICE_BASIS_EVENTS,
    build_call_plan,
    build_current_state_call_plan,
    build_index_return_series_call_plan,
    build_price_basis_call_plan,
    main,
    run,
)


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class BuildCallPlanTests(unittest.TestCase):
    def test_every_planned_capability_is_on_the_allowlist(self):
        for entry in build_call_plan():
            self.assertIn(entry["capability"], MARKET_DATA_ENDPOINTS)

    def test_plan_is_bounded_not_a_broad_sweep(self):
        # Small explicit ticker/date allowlist, not hundreds of symbols.
        self.assertLess(len(build_call_plan()), 40)

    def test_plan_is_deterministic_in_shape_across_calls(self):
        first = [(e["capability"], e.get("symbol"), sorted(e.get("query", {}).keys())) for e in build_call_plan()]
        second = [(e["capability"], e.get("symbol"), sorted(e.get("query", {}).keys())) for e in build_call_plan()]
        self.assertEqual(first, second)


class BuildPriceBasisCallPlanTests(unittest.TestCase):
    def test_every_planned_capability_is_on_the_allowlist(self):
        for entry in build_price_basis_call_plan():
            self.assertIn(entry["capability"], MARKET_DATA_ENDPOINTS)

    def test_plan_is_bounded_exactly_one_auth_plus_one_call_per_event(self):
        plan = build_price_basis_call_plan()
        self.assertEqual(1 + len(PRICE_BASIS_EVENTS), len(plan))

    def test_resolution_is_exactly_1D_never_the_broken_D_token(self):
        """"D" is accepted by the endpoint but returns null/empty arrays
        (observed in the general qualification pass) -- an HTTP-200 silent
        failure, not an error. Every ohlc entry in this plan must use "1D",
        the only daily-bar token confirmed to return real rows."""
        ohlc_entries = [e for e in build_price_basis_call_plan() if e["capability"] == "ohlc"]
        self.assertEqual(len(PRICE_BASIS_EVENTS), len(ohlc_entries))
        for entry in ohlc_entries:
            self.assertEqual("1D", entry["query"]["resolution"])
            self.assertNotEqual("D", entry["query"]["resolution"])

    def test_plan_is_deterministic_in_shape_across_calls(self):
        first = [(e["capability"], e.get("symbol"), e.get("query")) for e in build_price_basis_call_plan()]
        second = [(e["capability"], e.get("symbol"), e.get("query")) for e in build_price_basis_call_plan()]
        self.assertEqual(first, second)

    def test_each_event_window_is_a_single_bounded_call_not_a_sweep(self):
        """One call per event covers its whole window (ohlc accepts a wide
        from/to range, unlike the same-day-only history endpoints) -- never
        one call per session."""
        ohlc_entries = [e for e in build_price_basis_call_plan() if e["capability"] == "ohlc"]
        tickers_called = {e["query"]["symbol"] for e in ohlc_entries}
        self.assertEqual({event["ticker"] for event in PRICE_BASIS_EVENTS}, tickers_called)
        self.assertEqual(len(PRICE_BASIS_EVENTS), len(ohlc_entries))


class BuildCurrentStateCallPlanTests(unittest.TestCase):
    """DNSE current-state price-analytics milestone (2026-08-10): exactly one
    bounded HPG ohlc call, resolution="1D", not overlapping the price-basis
    qualification's own HPG event window."""

    def test_every_planned_capability_is_on_the_allowlist(self):
        for entry in build_current_state_call_plan():
            self.assertIn(entry["capability"], MARKET_DATA_ENDPOINTS)

    def test_plan_is_bounded_exactly_one_auth_plus_one_ohlc_call(self):
        plan = build_current_state_call_plan()
        self.assertEqual(2, len(plan))

    def test_resolution_is_exactly_1D_never_the_broken_D_token(self):
        ohlc_entries = [e for e in build_current_state_call_plan() if e["capability"] == "ohlc"]
        self.assertEqual(1, len(ohlc_entries))
        self.assertEqual("1D", ohlc_entries[0]["query"]["resolution"])
        self.assertNotEqual("D", ohlc_entries[0]["query"]["resolution"])

    def test_ticker_is_hpg_only(self):
        ohlc_entries = [e for e in build_current_state_call_plan() if e["capability"] == "ohlc"]
        self.assertEqual({CURRENT_STATE_TICKER}, {e["query"]["symbol"] for e in ohlc_entries})
        self.assertEqual("HPG", CURRENT_STATE_TICKER)

    def test_window_does_not_overlap_the_price_basis_hpg_event_window(self):
        # The price-basis qualification's HPG window is 2026-05-15..2026-06-03
        # (the 10% stock dividend ex-date). This milestone's window must be a
        # separate, uneventful window, not a re-run of that qualification.
        price_basis_hpg_window = next(e for e in PRICE_BASIS_EVENTS if e["ticker"] == "HPG")
        self.assertGreater(CURRENT_STATE_WINDOW["from"], price_basis_hpg_window["window_to"])

    def test_plan_is_deterministic_in_shape_across_calls(self):
        first = [(e["capability"], e.get("symbol"), e.get("query")) for e in build_current_state_call_plan()]
        second = [(e["capability"], e.get("symbol"), e.get("query")) for e in build_current_state_call_plan()]
        self.assertEqual(first, second)

    def test_window_stays_under_the_evidence_redaction_truncation_cap(self):
        """Real trap hit during this milestone: dnse_market_data._bound_large_lists()
        replaces any response list longer than 20 items with a
        {"list_truncated": True, ...} summary in the *retained* evidence file
        (the live response itself is unaffected) -- a first attempt at a
        37-session window silently produced unusable truncated evidence. A
        calendar-day span alone cannot prove the session count stays under
        that cap (trading sessions are a subset of calendar days), so this
        checks the actual real vn_stock.db-confirmed session count for this
        exact window, not just that the dates look "modest"."""
        import sqlite3

        from runtime_paths import runtime_root

        db_path = runtime_root() / "vn_stock.db"
        if not db_path.exists():
            self.skipTest("vn_stock.db not available in this environment")
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            conn.execute("PRAGMA query_only = 1")
            count = conn.execute(
                "SELECT COUNT(DISTINCT date) FROM ohlcv WHERE ticker = ? AND date BETWEEN ? AND ?",
                (CURRENT_STATE_TICKER, CURRENT_STATE_WINDOW["from"], CURRENT_STATE_WINDOW["to"]),
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertGreater(count, 0, "expected at least one retained HPG session in this window")
        self.assertLessEqual(count, 20, "window session count must stay at/under the redaction truncation cap")


class BuildIndexReturnSeriesCallPlanTests(unittest.TestCase):
    """DNSE index return-series qualification milestone (2026-08-10): exactly
    2 *identical* bounded VNINDEX ohlc calls beyond the auth check -- same
    window requested twice, to test data-source determinism, not two
    different periods."""

    def test_every_planned_capability_is_on_the_allowlist(self):
        for entry in build_index_return_series_call_plan():
            self.assertIn(entry["capability"], MARKET_DATA_ENDPOINTS)

    def test_plan_is_bounded_exactly_one_auth_plus_two_ohlc_calls(self):
        plan = build_index_return_series_call_plan()
        self.assertEqual(3, len(plan))

    def test_resolution_is_exactly_1D_never_the_broken_D_token(self):
        ohlc_entries = [e for e in build_index_return_series_call_plan() if e["capability"] == "ohlc"]
        self.assertEqual(2, len(ohlc_entries))
        for entry in ohlc_entries:
            self.assertEqual("1D", entry["query"]["resolution"])
            self.assertNotEqual("D", entry["query"]["resolution"])

    def test_benchmark_is_vnindex_only_type_index(self):
        ohlc_entries = [e for e in build_index_return_series_call_plan() if e["capability"] == "ohlc"]
        self.assertEqual({INDEX_RETURN_SERIES_BENCHMARK}, {e["query"]["symbol"] for e in ohlc_entries})
        self.assertEqual("VNINDEX", INDEX_RETURN_SERIES_BENCHMARK)
        for entry in ohlc_entries:
            self.assertEqual("INDEX", entry["query"]["type"])

    def test_the_two_ohlc_calls_are_identical_by_design(self):
        ohlc_entries = [e for e in build_index_return_series_call_plan() if e["capability"] == "ohlc"]
        self.assertEqual(ohlc_entries[0]["query"], ohlc_entries[1]["query"])
        self.assertNotEqual(ohlc_entries[0]["pit_label"], ohlc_entries[1]["pit_label"])

    def test_window_matches_the_current_state_window_deliberately(self):
        self.assertEqual(CURRENT_STATE_WINDOW, INDEX_RETURN_SERIES_WINDOW)

    def test_plan_is_deterministic_in_shape_across_calls(self):
        first = [(e["capability"], e.get("symbol"), e.get("query")) for e in build_index_return_series_call_plan()]
        second = [(e["capability"], e.get("symbol"), e.get("query")) for e in build_index_return_series_call_plan()]
        self.assertEqual(first, second)


class DryRunTests(unittest.TestCase):
    def test_dry_run_makes_no_request_and_needs_no_credentials(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(output), patch(
            "dnse_market_data._default_request_get"
        ) as request:
            self.assertEqual(0, main([]))
        request.assert_not_called()
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["dry_run"])


class LiveModeTests(unittest.TestCase):
    def test_live_without_credentials_prints_sentinel_and_never_touches_secrets_env(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(output), patch(
            "dnse_market_data._default_request_get"
        ) as request:
            self.assertEqual(2, main(["--live"]))
        request.assert_not_called()
        self.assertIn(CREDENTIAL_INJECTION_REQUIRED, output.getvalue())

    def test_auth_probe_makes_exactly_one_call(self):
        calls = []

        def fake_get(*_a, **_k):
            calls.append(1)
            return _FakeResponse(200, {"date": "2026-08-10"})

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"DNSE_API_KEY": "k", "DNSE_API_SECRET": "s"}, clear=True
        ), patch("dnse_market_data._default_request_get", side_effect=fake_get):
            report = run("auth", out_dir=Path(tmp))
            self.assertTrue((Path(tmp) / "probe_results.json").exists())
        self.assertEqual(1, len(calls))
        self.assertEqual("DNSE_AUTHENTICATION_PASS", report["status"])

    def test_matrix_stops_after_failed_auth_check(self):
        calls = []

        def fake_get(*_a, **_k):
            calls.append(1)
            return _FakeResponse(401, {"message": "unauthorized"})

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"DNSE_API_KEY": "k", "DNSE_API_SECRET": "s"}, clear=True
        ), patch("dnse_market_data._default_request_get", side_effect=fake_get):
            report = run("matrix", out_dir=Path(tmp))
        self.assertEqual(1, len(calls), "matrix mode must not proceed past a failed auth check")
        self.assertEqual("DNSE_AUTHENTICATION_FAIL", report["status"])

    def test_matrix_runs_the_full_bounded_plan_when_auth_passes(self):
        calls = []

        def fake_get(*_a, **_k):
            calls.append(1)
            return _FakeResponse(200, {"date": "2026-08-10", "value": 1})

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"DNSE_API_KEY": "k", "DNSE_API_SECRET": "s"}, clear=True
        ), patch("dnse_market_data._default_request_get", side_effect=fake_get):
            report = run("matrix", out_dir=Path(tmp))
        self.assertEqual(len(build_call_plan()), len(calls))
        self.assertEqual(len(build_call_plan()), report["call_count"])
        self.assertEqual(report["call_count"], report["ok_count"])

    def test_current_state_probe_makes_exactly_two_calls_auth_plus_ohlc(self):
        calls = []

        def fake_get(*_a, **_k):
            calls.append(1)
            return _FakeResponse(200, {"date": "2026-08-10", "o": [1], "h": [1], "l": [1],
                                        "c": [1], "t": [1786000000], "v": [1]})

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"DNSE_API_KEY": "k", "DNSE_API_SECRET": "s"}, clear=True
        ), patch("dnse_market_data._default_request_get", side_effect=fake_get):
            report = run("current-state", out_dir=Path(tmp))
        self.assertEqual(len(build_current_state_call_plan()), len(calls))
        self.assertEqual(2, report["call_count"])
        self.assertEqual("DNSE_AUTHENTICATION_PASS", report["status"])

    def test_index_return_series_probe_makes_exactly_three_calls_auth_plus_two_ohlc(self):
        calls = []

        def fake_get(*_a, **_k):
            calls.append(1)
            return _FakeResponse(200, {"date": "2026-08-10", "o": [1], "h": [1], "l": [1],
                                        "c": [1], "t": [1786000000], "v": [1]})

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"DNSE_API_KEY": "k", "DNSE_API_SECRET": "s"}, clear=True
        ), patch("dnse_market_data._default_request_get", side_effect=fake_get):
            report = run("index-return-series", out_dir=Path(tmp))
        self.assertEqual(len(build_index_return_series_call_plan()), len(calls))
        self.assertEqual(3, report["call_count"])
        self.assertEqual("DNSE_AUTHENTICATION_PASS", report["status"])

    def test_evidence_file_never_contains_the_api_secret(self):
        def fake_get(*_a, **_k):
            return _FakeResponse(200, {"date": "2026-08-10", "leakTest": "should-not-appear-either"})

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"DNSE_API_KEY": "k", "DNSE_API_SECRET": "extremely-secret-hmac-value"}, clear=True
        ), patch("dnse_market_data._default_request_get", side_effect=fake_get):
            run("matrix", out_dir=Path(tmp))
            content = (Path(tmp) / "probe_results.json").read_text(encoding="utf-8")
        self.assertNotIn("extremely-secret-hmac-value", content)


if __name__ == "__main__":
    unittest.main()
