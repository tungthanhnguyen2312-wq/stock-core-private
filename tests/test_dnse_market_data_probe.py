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
    PRICE_BASIS_EVENTS,
    build_call_plan,
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
