# ==========================================================================
# Focused tests for tools/analysis_coverage_scan.py. Synthetic in-memory
# frames only -- no dashboard-runtime access, nothing written.
# Run: `python -m unittest tests.test_analysis_coverage_scan`
# ==========================================================================

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import analysis_coverage_scan as scan  # noqa: E402


def _frame():
    import pandas as pd
    return pd.DataFrame([
        # complete for liquidity + leverage
        {"ticker": "AAA", "period": "2025-Q4", "current_assets": 10.0, "current_liabilities": 5.0,
         "total_liabilities": 6.0, "equity": 4.0, "total_assets": 10.0, "retained_earnings": 1.0,
         "revenue": 20.0, "net_profit": 2.0, "operating_cash_flow": 3.0},
        # missing retained_earnings -> blocks altman only
        {"ticker": "BBB", "period": "2025-Q4", "current_assets": 8.0, "current_liabilities": 4.0,
         "total_liabilities": 5.0, "equity": 3.0, "total_assets": 8.0, "retained_earnings": None,
         "revenue": 15.0, "net_profit": 1.0, "operating_cash_flow": 2.0},
        # zero denominator -> excluded from leverage/altman despite being non-null
        {"ticker": "CCC", "period": "2025-Q4", "current_assets": 7.0, "current_liabilities": 3.0,
         "total_liabilities": 0.0, "equity": 0.0, "total_assets": 0.0, "retained_earnings": 1.0,
         "revenue": 9.0, "net_profit": 1.0, "operating_cash_flow": 1.0},
        # different period -> must not leak into the scanned period
        {"ticker": "DDD", "period": "2024-Q4", "current_assets": 1.0, "current_liabilities": 1.0,
         "total_liabilities": 1.0, "equity": 1.0, "total_assets": 1.0, "retained_earnings": 1.0,
         "revenue": 1.0, "net_profit": 1.0, "operating_cash_flow": 1.0},
    ])


class AnalysisCoverageScanTests(unittest.TestCase):
    def _scan(self, period="2025-Q4"):
        with patch.object(scan, "_load", return_value=_frame()):
            return scan.scan(Path("unused"), period)

    def test_universe_is_scoped_to_the_requested_period(self):
        self.assertEqual(self._scan()["universe_tickers"], 3)
        self.assertEqual(self._scan("2024-Q4")["universe_tickers"], 1)

    def test_runnable_counts_reflect_complete_inputs_only(self):
        models = self._scan()["models"]
        self.assertEqual(models["liquidity_screen"]["runnable_tickers"], 3)
        self.assertEqual(models["altman_z_prime"]["runnable_tickers"], 1)

    def test_non_positive_denominators_exclude_a_ticker(self):
        models = self._scan()["models"]
        self.assertEqual(models["leverage_screen"]["runnable_tickers"], 2,
                          "CCC has zero equity/total_assets and must not count as runnable")

    def test_blockers_are_attributed_to_named_inputs(self):
        altman = self._scan()["models"]["altman_z_prime"]
        self.assertIn("retained_earnings", altman["blocking_inputs"])
        self.assertEqual(altman["blocking_inputs"]["retained_earnings"], 1)

    def test_highest_impact_ranking_is_present_and_sorted(self):
        impact = self._scan()["highest_impact_missing_inputs"]
        self.assertTrue(impact)
        self.assertEqual(list(impact.values()), sorted(impact.values(), reverse=True))

    def test_result_declares_its_evidence_tier_and_limitations(self):
        report = self._scan()
        self.assertEqual(report["evidence_tier"], "provider_reported")
        self.assertTrue(report["tier_limitations"])

    def test_absent_column_is_reported_not_silently_zero(self):
        import pandas as pd
        frame = _frame().drop(columns=["retained_earnings"])
        with patch.object(scan, "_load", return_value=frame):
            altman = scan.scan(Path("unused"), "2025-Q4")["models"]["altman_z_prime"]
        self.assertEqual(altman["runnable_tickers"], 0)
        self.assertIn("retained_earnings", altman["blocking_inputs"])
        self.assertIn("note", altman)

    def test_scan_is_deterministic(self):
        self.assertEqual(self._scan(), self._scan())


if __name__ == "__main__":
    unittest.main()
