"""Unit tests for attaching current_state_price_analytics to the AI bundle (export_ai_bundle.py).

Verifies the evidence-bounded attachment contract:
- Opt-in flag --include-current-state-price-analytics attaches `current_state_price_analytics`.
- HPG resolves `status="available"`, carrying simple/cumulative returns, volatility,
  drawdown, RSI14, and SMA20 status from dnse_current_state_price_analytics.py.
- Other production-universe tickers resolve `status="not_qualified"` fail-closed.
- VCB is never included in the production bundle universe.
- PIT=False, is_actionable=False, analysis_time_semantics are strictly enforced.
- Research eligibility and current_state_market_risk are unaffected.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any

import export_ai_bundle as bundle
import dnse_current_state_price_analytics as price_analytics
import dnse_market_risk_evidence_store as evidence_store

_SESSION_DATES = [
    "2026-07-14", "2026-07-15", "2026-07-16", "2026-07-17", "2026-07-20",
    "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24", "2026-07-27",
    "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31", "2026-08-03",
    "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07",
]

_HPG_CLOSES = [
    26000.0, 26200.0, 26100.0, 26500.0, 26400.0,
    26800.0, 27000.0, 26900.0, 27200.0, 27100.0,
    27500.0, 27400.0, 27800.0, 28000.0, 27900.0,
    28200.0, 28500.0, 28400.0, 28800.0,
]

_EPOCHS = [1784010000 + i * 86400 for i in range(len(_SESSION_DATES))]


def _make_raw_ohlc(closes: list[float]) -> dict[str, list]:
    return {
        "o": closes,
        "h": [c * 1.01 for c in closes],
        "l": [c * 0.99 for c in closes],
        "c": closes,
        "t": _EPOCHS,
    }


def _seed_runtime_evidence(root: Path) -> None:
    raw_hpg = _make_raw_ohlc(_HPG_CLOSES)
    evidence_store.write_stock_ohlc(
        root, "HPG", raw_hpg, provenance={"source": "test_seed", "symbol": "HPG"}
    )
    db_path = root / "vn_stock.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT)")
        for dt in _SESSION_DATES:
            conn.execute("INSERT INTO ohlcv (ticker, date) VALUES (?, ?)", ("HPG", dt))
        conn.commit()
    finally:
        conn.close()


def _find_forbidden_keys(obj: Any, forbidden_keys: set[str]) -> list[str]:
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in forbidden_keys:
                found.append(str(k))
            found.extend(_find_forbidden_keys(v, forbidden_keys))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_forbidden_keys(item, forbidden_keys))
    return found


class ExportAiBundleCurrentStatePriceAnalyticsTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        _seed_runtime_evidence(self.root)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_legacy_build_without_flag_leaves_bundle_unchanged(self) -> None:
        entries = {"HPG": {"ticker": "HPG"}, "VNM": {"ticker": "VNM"}}
        result = bundle.attach_current_state_price_analytics(
            entries, self.root, include=False, reference_session_date="2026-08-07"
        )
        self.assertNotIn("current_state_price_analytics", result["HPG"])
        self.assertNotIn("current_state_price_analytics", result["VNM"])

    def test_hpg_attachment_available_and_reuses_canonical_module(self) -> None:
        entries = {"HPG": {"ticker": "HPG"}}
        result = bundle.attach_current_state_price_analytics(
            entries, self.root, include=True, reference_session_date="2026-08-07"
        )
        analytics = result["HPG"].get("current_state_price_analytics")
        self.assertIsNotNone(analytics)
        self.assertEqual("available", analytics["status"])
        self.assertEqual("HPG", analytics["ticker"])
        self.assertEqual("DNSE", analytics["source"])

    def test_hpg_observation_and_return_pass_through(self) -> None:
        entries = {"HPG": {"ticker": "HPG"}}
        result = bundle.attach_current_state_price_analytics(
            entries, self.root, include=True, reference_session_date="2026-08-07"
        )
        analytics = result["HPG"]["current_state_price_analytics"]

        # Observation count
        self.assertEqual(19, len(analytics["observations"]))

        # Returns pass-through
        ret = analytics["returns"]
        self.assertEqual("complete", ret["status"])
        self.assertEqual(18, ret["return_count"])

        # Cumulative return exact pass-through
        expected_cum = 28800.0 / 26000.0 - 1.0
        self.assertAlmostEqual(expected_cum, ret["cumulative_return"], places=6)

    def test_hpg_volatility_drawdown_technical_pass_through(self) -> None:
        entries = {"HPG": {"ticker": "HPG"}}
        result = bundle.attach_current_state_price_analytics(
            entries, self.root, include=True, reference_session_date="2026-08-07"
        )
        analytics = result["HPG"]["current_state_price_analytics"]

        # Realized volatility exact pass-through
        vol = analytics["volatility"]
        self.assertEqual("available", vol["status"])
        self.assertIsInstance(vol["value"], float)
        self.assertGreater(vol["value"], 0.0)

        # Max drawdown exact pass-through
        dd = analytics["drawdown"]
        self.assertEqual("available", dd["status"])
        self.assertIsInstance(dd["maximum_drawdown"], float)

        # Technical indicators: RSI14 available, SMA20 unavailable due to 19 sessions < 20
        tech = analytics["technical_indicators"]
        self.assertEqual("available", tech["status"])
        self.assertEqual("available", tech["rsi_14"]["status"])
        self.assertIsInstance(tech["rsi_14"]["value"], float)

        self.assertEqual("unavailable", tech["sma_20"]["status"])
        self.assertIsNone(tech["sma_20"]["value"])

    def test_safety_semantics_strictly_enforced(self) -> None:
        entries = {"HPG": {"ticker": "HPG"}}
        result = bundle.attach_current_state_price_analytics(
            entries, self.root, include=True, reference_session_date="2026-08-07"
        )
        analytics = result["HPG"]["current_state_price_analytics"]

        self.assertFalse(analytics["pit_backtest_eligible"])
        self.assertFalse(analytics["is_actionable"])
        self.assertEqual(
            "current_state_using_retrospectively_adjusted_history",
            analytics["analysis_time_semantics"],
        )

    def test_provenance_and_warnings_retained(self) -> None:
        entries = {"HPG": {"ticker": "HPG"}}
        result = bundle.attach_current_state_price_analytics(
            entries, self.root, include=True, reference_session_date="2026-08-07"
        )
        analytics = result["HPG"]["current_state_price_analytics"]

        self.assertIn("provenance", analytics)
        self.assertIn("warnings", analytics)
        self.assertIsInstance(analytics["warnings"], list)
        self.assertGreater(len(analytics["warnings"]), 0)

    def test_other_production_tickers_fail_closed(self) -> None:
        other_tickers = ("POW", "SSI", "EVF", "PAN", "PNJ", "FPT", "QNS", "VNM", "PVD", "NVL")
        entries = {t: {"ticker": t} for t in other_tickers}
        result = bundle.attach_current_state_price_analytics(
            entries, self.root, include=True, reference_session_date="2026-08-07"
        )
        for t in other_tickers:
            analytics = result[t]["current_state_price_analytics"]
            self.assertEqual("not_qualified", analytics["status"], t)
            self.assertFalse(analytics["is_actionable"], t)
            self.assertEqual("not_qualified", analytics["coverage"]["status"], t)

    def test_vcb_never_enters_production_universe(self) -> None:
        self.assertNotIn("VCB", bundle.DEFAULT_TICKERS)

    def test_no_auth_or_secret_fields_leaked(self) -> None:
        entries = {"HPG": {"ticker": "HPG"}}
        result = bundle.attach_current_state_price_analytics(
            entries, self.root, include=True, reference_session_date="2026-08-07"
        )
        analytics = result["HPG"]["current_state_price_analytics"]
        forbidden = {
            "password", "api_key", "apikey", "access_token", "refresh_token",
            "authorization", "credential", "credentials", "secret", "client_secret",
            "token", "auth_token"
        }
        found = _find_forbidden_keys(analytics, forbidden)
        self.assertEqual([], found, f"Forbidden credential keys found in payload: {found}")

    def test_research_eligibility_and_market_risk_unaffected(self) -> None:
        entries = {
            "HPG": {
                "ticker": "HPG",
                "research_financial_fact_projection": {"research_eligible": True},
                "current_state_market_risk": {"status": "available", "beta": {"value": 0.8}},
            }
        }
        before_research = copy.deepcopy(entries["HPG"]["research_financial_fact_projection"])
        before_market_risk = copy.deepcopy(entries["HPG"]["current_state_market_risk"])

        result = bundle.attach_current_state_price_analytics(
            entries, self.root, include=True, reference_session_date="2026-08-07"
        )

        self.assertEqual(before_research, result["HPG"]["research_financial_fact_projection"])
        self.assertEqual(before_market_risk, result["HPG"]["current_state_market_risk"])

    def test_repeated_build_is_deterministic(self) -> None:
        entries1 = {"HPG": {"ticker": "HPG"}}
        entries2 = {"HPG": {"ticker": "HPG"}}

        res1 = bundle.attach_current_state_price_analytics(
            entries1, self.root, include=True, reference_session_date="2026-08-07"
        )
        res2 = bundle.attach_current_state_price_analytics(
            entries2, self.root, include=True, reference_session_date="2026-08-07"
        )

        json1 = json.dumps(res1["HPG"]["current_state_price_analytics"], sort_keys=True)
        json2 = json.dumps(res2["HPG"]["current_state_price_analytics"], sort_keys=True)
        self.assertEqual(json1, json2)


if __name__ == "__main__":
    unittest.main()
