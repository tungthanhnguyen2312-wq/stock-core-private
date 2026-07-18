"""Tests for macro_sync.py's per-series freshness (item H, Data Contract Hardening v1.1).

make_snapshot() writes macro_snapshot.csv, the file export_ai_bundle.py actually loads into
analysis_bundle.json.macro_snapshot. Before this change it had no freshness fields at all;
freshness_for() already existed correctly but only fed the unrelated web-dashboard JSON path
(data/macro_snapshot.json via build_web_snapshot()). These tests cover the CSV-facing path.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import macro_sync as ms  # noqa: E402


def _make_conn(rows: list[tuple[str, str, float]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    ms.init_db(conn)
    for series, date, value in rows:
        conn.execute("INSERT INTO macro VALUES(?,?,?)", (series, date, value))
    conn.commit()
    return conn


class FreshnessForTests(unittest.TestCase):
    """Pre-existing pure function — confirms the semantics make_snapshot() now relies on."""

    FIXED_NOW = datetime(2026, 7, 17, 12, 0, 0, tzinfo=ms.VN_TZ)

    def test_current_within_stale_after_days(self):
        result = ms.freshness_for("2026-07-16", "ngày", self.FIXED_NOW)
        self.assertEqual(result["status"], "current")
        self.assertEqual(result["age_days"], 1)

    def test_stale_beyond_stale_after_days(self):
        result = ms.freshness_for("2026-01-01", "ngày", self.FIXED_NOW)
        self.assertEqual(result["status"], "stale")
        self.assertGreater(result["age_days"], result["stale_after_days"])

    def test_unparseable_period_is_unknown_not_silently_current(self):
        result = ms.freshness_for("not-a-date", "ngày", self.FIXED_NOW)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["age_days"])


class MakeSnapshotFreshnessTests(unittest.TestCase):
    """Integration: make_snapshot() must call freshness_for() per series and expose the
    result as expected_frequency/age_days/freshness_status/as_of/freshness_reason columns —
    not a single freshness verdict for the whole file."""

    FIXED_NOW = datetime(2026, 7, 17, 12, 0, 0, tzinfo=ms.VN_TZ)

    def test_fresh_daily_series_is_current_with_no_reason(self):
        conn = _make_conn([("dxy", "2026-07-17", 100.0), ("dxy", "2026-07-16", 99.5)])
        snap = ms.make_snapshot(conn, generated_at=self.FIXED_NOW)
        row = snap[snap["series"] == "dxy"].iloc[0]
        self.assertEqual(row["expected_frequency"], "daily")
        self.assertEqual(row["age_days"], 0)
        self.assertEqual(row["freshness_status"], "current")
        self.assertIsNone(row["freshness_reason"])
        self.assertEqual(row["as_of"], self.FIXED_NOW.isoformat(timespec="seconds"))
        # "date" (series' own observation date) must stay distinct from "as_of" (pipeline run time).
        self.assertNotEqual(row["date"], row["as_of"])

    def test_stale_daily_series_reports_explicit_reason(self):
        conn = _make_conn([("dxy", "2026-01-01", 100.0)])
        snap = ms.make_snapshot(conn, generated_at=self.FIXED_NOW)
        row = snap[snap["series"] == "dxy"].iloc[0]
        self.assertEqual(row["freshness_status"], "stale")
        self.assertEqual(row["freshness_reason"], "age_days_exceeds_stale_after_days_for_daily")

    def test_annual_series_is_not_falsely_stale_at_an_age_that_would_stale_a_daily_series(self):
        # Same absolute age (~200 days) would be "stale" for a daily series but must stay
        # "current" for an annual one (stale_after_days=550) — per-series freshness, not a
        # single file-wide verdict.
        conn = _make_conn([("vn_gdp_yoy", "2026-01-01", 6.0)])
        snap = ms.make_snapshot(conn, generated_at=self.FIXED_NOW)
        row = snap[snap["series"] == "vn_gdp_yoy"].iloc[0]
        self.assertEqual(row["expected_frequency"], "annual")
        self.assertEqual(row["freshness_status"], "current")

    def test_every_series_gets_its_own_freshness_columns(self):
        conn = _make_conn([
            ("dxy", "2026-07-17", 100.0),
            ("vn_gdp_yoy", "2025-12-31", 6.0),
            ("us_fedfunds", "2026-06-15", 5.25),
        ])
        snap = ms.make_snapshot(conn, generated_at=self.FIXED_NOW)
        for column in ("expected_frequency", "age_days", "freshness_status", "as_of", "freshness_reason"):
            self.assertIn(column, snap.columns)
        self.assertEqual(len(snap), 3)
        self.assertEqual(set(snap["freshness_status"]), {"current"})


if __name__ == "__main__":
    unittest.main()
