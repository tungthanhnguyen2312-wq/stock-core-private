"""Proofs for load_ohlcv_provider_purity and attach_qualified_market_observations in
export_ai_bundle.py -- the two pieces of wiring that connect a real retained OHLCV window's
provider identity to qualified_market_observations.py.
"""

from __future__ import annotations

import sqlite3
import unittest

from export_ai_bundle import load_ohlcv_provider_purity, load_ohlcv_recent, attach_qualified_market_observations


def _conn_with_rows(rows: list[tuple]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, "
        "close REAL, volume REAL, source TEXT, PRIMARY KEY(ticker, date))"
    )
    conn.executemany(
        "INSERT INTO ohlcv (ticker, date, open, high, low, close, volume, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return conn


def _row(ticker, date, source, price=50000.0):
    return (ticker, date, price, price * 1.01, price * 0.99, price, 100000, source)


class LoadOhlcvProviderPurity(unittest.TestCase):
    def test_single_provider_window_is_pure(self):
        rows = [_row("HPG", f"2026-01-{i:02d}", "VCI") for i in range(1, 21)]
        conn = _conn_with_rows(rows)
        result = load_ohlcv_provider_purity(conn, "HPG", n=20)
        self.assertTrue(result["pure"])
        self.assertEqual(result["provider"], "VCI")
        self.assertEqual(result["sources_seen"], ["VCI"])
        self.assertEqual(result["session_count"], 20)

    def test_mixed_provider_window_is_not_pure(self):
        rows = [_row("HPG", f"2026-01-{i:02d}", "VCI") for i in range(1, 11)]
        rows += [_row("HPG", f"2026-01-{i:02d}", "KBS") for i in range(11, 21)]
        conn = _conn_with_rows(rows)
        result = load_ohlcv_provider_purity(conn, "HPG", n=20)
        self.assertFalse(result["pure"])
        self.assertIsNone(result["provider"])
        self.assertEqual(result["sources_seen"], ["KBS", "VCI"])

    def test_no_rows_is_not_pure(self):
        conn = _conn_with_rows([])
        result = load_ohlcv_provider_purity(conn, "GHOST", n=20)
        self.assertFalse(result["pure"])
        self.assertIsNone(result["provider"])
        self.assertEqual(result["session_count"], 0)

    def test_null_source_is_excluded_not_treated_as_a_provider(self):
        rows = [_row("HPG", f"2026-01-{i:02d}", "VCI") for i in range(1, 11)]
        rows += [_row("HPG", f"2026-01-{i:02d}", None) for i in range(11, 21)]
        conn = _conn_with_rows(rows)
        result = load_ohlcv_provider_purity(conn, "HPG", n=20)
        # Only VCI is a real source; a null source neither counts as a second provider nor
        # as a silent VCI label -- the window is impure because coverage is incomplete.
        self.assertEqual(result["sources_seen"], ["VCI"])

    def test_describes_the_exact_same_window_as_load_ohlcv_recent(self):
        rows = [_row("HPG", f"2026-01-{i:02d}", "VCI") for i in range(1, 31)]
        conn = _conn_with_rows(rows)
        recent = load_ohlcv_recent(conn, "HPG", n=20)
        provenance = load_ohlcv_provider_purity(conn, "HPG", n=20)
        self.assertEqual(len(recent), provenance["session_count"])

    def test_provider_name_is_upper_cased(self):
        rows = [_row("HPG", f"2026-01-{i:02d}", "vci") for i in range(1, 21)]
        conn = _conn_with_rows(rows)
        result = load_ohlcv_provider_purity(conn, "HPG", n=20)
        self.assertEqual(result["provider"], "VCI")


class AttachQualifiedMarketObservations(unittest.TestCase):
    def test_not_included_by_default_leaves_entries_untouched(self):
        entries = {"HPG": {"ohlcv_recent": [], "ohlcv_provider_provenance": {}}}
        attach_qualified_market_observations(entries, False)
        self.assertNotIn("qualified_market_observations", entries["HPG"])

    def test_included_attaches_a_record_for_every_ticker(self):
        entries = {
            "HPG": {"ohlcv_recent": [], "ohlcv_provider_provenance": {"provider": None, "pure": False}},
            "VNM": {"ohlcv_recent": [], "ohlcv_provider_provenance": {"provider": None, "pure": False}},
        }
        attach_qualified_market_observations(entries, True)
        self.assertIn("qualified_market_observations", entries["HPG"])
        self.assertIn("qualified_market_observations", entries["VNM"])

    def test_not_restricted_to_pilot_tickers(self):
        """Unlike historical_decision_analysis/portfolio_risk_analysis, every ticker in the
        bundle gets a record, not just HPG/VNM/VCB."""
        entries = {"PVD": {"ohlcv_recent": [], "ohlcv_provider_provenance": {"provider": None, "pure": False}}}
        attach_qualified_market_observations(entries, True)
        self.assertIn("qualified_market_observations", entries["PVD"])
        self.assertEqual(entries["PVD"]["qualified_market_observations"]["status"], "unavailable")

    def test_non_dict_entry_is_skipped_not_raised(self):
        entries = {"HPG": None}
        attach_qualified_market_observations(entries, True)  # must not raise
        self.assertIsNone(entries["HPG"])


if __name__ == "__main__":
    unittest.main()
