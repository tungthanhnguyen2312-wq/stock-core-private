"""Tests for tools/derive_dnse_trades_liquidity_basis.py.

Network calls are mocked throughout (matching this repository's existing
``tests/test_dnse_market_data_probe.py`` convention); no test makes a real HTTP request or reads
the owner's actual ``secrets.env``.
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from dnse_access import CREDENTIAL_ENV_PAIRS
from dnse_market_data import MARKET_DATA_ENDPOINTS
from tools.derive_dnse_trades_liquidity_basis import (
    CREDENTIAL_INJECTION_REQUIRED,
    CURRENT_SESSION_TICKERS,
    HISTORICAL_SESSION_DATE,
    HISTORICAL_TICKERS,
    PAGE_CAP,
    _retained_fhsc_context,
    build_call_plan,
    main,
    run_live,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: object):
        self.status_code = status_code
        self._payload = payload
        self.content = json.dumps(payload).encode("utf-8")

    def json(self):
        return self._payload


class BuildCallPlanTests(unittest.TestCase):
    def test_every_planned_capability_is_on_the_allowlist(self) -> None:
        plan = build_call_plan()
        capabilities = {plan["auth_check"]["capability"]}
        for leg in ("current_session_leg", "ohlc_leg", "historical_leg"):
            capabilities |= {entry["capability"] for entry in plan[leg]}
        self.assertTrue(capabilities.issubset(MARKET_DATA_ENDPOINTS))

    def test_plan_is_bounded_fixed_corpus_sizes(self) -> None:
        plan = build_call_plan()
        self.assertEqual(len(plan["current_session_leg"]), len(CURRENT_SESSION_TICKERS))
        self.assertEqual(len(plan["ohlc_leg"]), len(CURRENT_SESSION_TICKERS))
        self.assertEqual(len(plan["historical_leg"]), len(HISTORICAL_TICKERS))
        for entry in plan["historical_leg"]:
            self.assertEqual(entry["page_cap"], PAGE_CAP)
            self.assertEqual(entry["session_date"], HISTORICAL_SESSION_DATE)

    def test_plan_is_deterministic_in_shape_across_calls(self) -> None:
        self.assertEqual(build_call_plan(), build_call_plan())

    def test_dry_run_makes_no_request_and_needs_no_credentials(self) -> None:
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(output):
            exit_code = main([])
        self.assertEqual(exit_code, 0)
        self.assertIn("call_plan", output.getvalue())


class RetainedFhscContextTests(unittest.TestCase):
    def test_missing_artifact_fails_closed_not_crash(self) -> None:
        with patch("tools.derive_dnse_trades_liquidity_basis.RETAINED_FHSC_ARTIFACT", Path("does/not/exist.json")):
            result = _retained_fhsc_context("2026-08-14", ("HPG",))
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "retained_fhsc_artifact_not_found")

    def test_filters_by_session_and_ticker_from_a_fixture(self) -> None:
        fixture = {
            "artifact_identity": "dnse_fhsc_volume_basis_qualification:test",
            "reconciliation": {"matrix": [
                {"ticker": "HPG", "session": "2026-08-14", "fhsc_put_through_volume": 225000},
                {"ticker": "HPG", "session": "2026-08-17", "fhsc_put_through_volume": 0},
                {"ticker": "VNM", "session": "2026-08-14", "fhsc_put_through_volume": 1},
            ]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.json"
            path.write_text(json.dumps(fixture), encoding="utf-8")
            with patch("tools.derive_dnse_trades_liquidity_basis.RETAINED_FHSC_ARTIFACT", path):
                result = _retained_fhsc_context("2026-08-14", ("HPG",))
        self.assertTrue(result["available"])
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["rows"][0]["ticker"], "HPG")
        self.assertEqual(result["rows"][0]["session"], "2026-08-14")
        self.assertIn("no new FHSC call", result["note"])


class CredentialHandlingTests(unittest.TestCase):
    def test_run_live_reports_sentinel_and_touches_no_network_without_credentials(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "tools.derive_dnse_trades_liquidity_basis.dnse_secrets_env.ensure_credentials_loaded",
            return_value={"configured": False, "secrets_file_consulted": True, "secrets_file_found": False},
        ):
            report = run_live()
        self.assertEqual(report["status"], CREDENTIAL_INJECTION_REQUIRED)

    def test_partially_injected_env_is_cleared_even_when_no_valid_pair_is_found(self) -> None:
        """A file that only supplies one half of a pair must not leak that half past this call --
        the credential-clearing finally must cover the early no-credentials return too."""
        def fake_load_and_inject() -> dict:
            os.environ["DNSE_API_KEY"] = "half-a-pair"
            return {"configured": False, "secrets_file_consulted": True, "secrets_file_found": True}

        with patch.dict(os.environ, {}, clear=True), patch(
            "tools.derive_dnse_trades_liquidity_basis.dnse_secrets_env.ensure_credentials_loaded",
            side_effect=fake_load_and_inject,
        ):
            report = run_live()
        self.assertEqual(report["status"], CREDENTIAL_INJECTION_REQUIRED)
        for key1, key2 in CREDENTIAL_ENV_PAIRS:
            self.assertNotIn(key1, os.environ)
            self.assertNotIn(key2, os.environ)

    def test_credentials_cleared_after_a_full_mocked_successful_run(self) -> None:
        def fake_get(url, params=None, headers=None, timeout=None):
            if url.endswith("/market/working-dates"):
                return _FakeResponse(200, {"dates": []})
            if url.endswith("/trades/latest"):
                return _FakeResponse(200, {"trades": []})
            if url.endswith("/price/ohlc"):
                return _FakeResponse(200, {"t": [], "v": []})
            if url.endswith("/trades"):
                return _FakeResponse(200, {"trades": [], "nextPageToken": None})
            return _FakeResponse(404, {})

        with patch.dict(os.environ, {"DNSE_API_KEY": "k", "DNSE_API_SECRET": "s"}, clear=True), patch(
            "tools.derive_dnse_trades_liquidity_basis.dnse_secrets_env.ensure_credentials_loaded",
            return_value={"configured": True},
        ), patch("tools.derive_dnse_trades_liquidity_basis.requests.get", side_effect=fake_get), tempfile.TemporaryDirectory() as tmp:
            with patch("tools.derive_dnse_trades_liquidity_basis.RAW_DIR", Path(tmp) / "raw"):
                report = run_live()
        self.assertEqual(report["status"], "DNSE_AUTHENTICATION_PASS")
        for key1, key2 in CREDENTIAL_ENV_PAIRS:
            self.assertNotIn(key1, os.environ)
            self.assertNotIn(key2, os.environ)


if __name__ == "__main__":
    unittest.main()
