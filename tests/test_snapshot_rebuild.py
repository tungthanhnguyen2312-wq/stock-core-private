"""Phase 9 validation of the locally rebuilt schema-v2 snapshot."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "financial_snapshot.csv"
REPORT = ROOT / "reports" / "financial_snapshot_rebuild.json"


class SnapshotRebuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = pd.read_csv(SNAPSHOT)
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_rebuilt_snapshot_contains_advanced_metrics(self):
        required = {
            "ebit", "ebit_status", "ebit_formula", "ebit_source", "ebit_period",
            "ebitda", "ebitda_status", "ebitda_formula", "ebitda_source", "ebitda_period",
            "interest_expense", "interest_expense_status", "retained_earnings",
            "retained_earnings_status", "depreciation", "amortization",
            "depreciation_and_amortization", "selling_expense", "general_admin_expense",
            "sga", "sga_status",
        }
        self.assertFalse(required - set(self.frame.columns))

    def test_pan_snapshot_values_after_rebuild(self):
        row = self.frame[(self.frame.ticker == "PAN") & (self.frame.period == "2026-Q1")].iloc[0]
        self.assertEqual(row.ebit, 600_682_628_000)
        self.assertEqual(row.ebit_status, "derived")
        self.assertEqual(row.ebit_formula, "profit_before_tax + interest_expense")
        self.assertEqual(row.sga, 353_782_849_000)
        self.assertEqual(row.sga_status, "derived")
        self.assertEqual(row.retained_earnings, 2_618_950_443_317)
        self.assertEqual(row.retained_earnings_status, "reported")
        self.assertEqual(row.ebitda_status, "insufficient_periods")

    def test_rebuilt_snapshot_contains_data_contract_hardening_columns(self):
        required = {
            "statement_currency", "statement_scale", "unit_status", "unit_evidence",
            "roe_status", "roe_canonical_metric",
            "roe_quarter", "roe_quarter_status", "roe_quarter_unit", "roe_quarter_basis",
            "roe_fy", "roe_fy_status",
            "roe_ttm", "roe_ttm_status", "roe_ttm_basis",
            "shares_period_end", "shares_period_end_status",
            "eps_calc_status", "book_value_status",
            "revenue_growth_yoy_status", "revenue_growth_yoy_reason", "revenue_growth_yoy_comparison_period",
            "profit_growth_yoy_status", "profit_growth_yoy_reason",
            "current_ratio_status", "quick_ratio_status", "cash_ratio_status", "inventory_turnover_status",
        }
        self.assertFalse(required - set(self.frame.columns))

    def test_statement_currency_declared_check_passes(self):
        self.assertTrue(self.report["validation"]["checks"]["statement_currency_declared"])

    def test_evf_representative_ticker_is_finance_company_and_passes(self):
        evf = self.report["validation"]["representative_ticker_validation"]["EVF"]
        self.assertTrue(evf["passed"])
        self.assertEqual(evf["entity_type"], "finance_company")
        self.assertTrue(evf["non_corporate_ebit_ebitda_ok"])
        self.assertIn(evf["advanced_statuses"]["ebit"], ("reported", "derived", "not_applicable"))

    def test_snapshot_duplicate_keys(self):
        self.assertEqual(int(self.frame.duplicated(["ticker", "period"]).sum()), 0)

    def test_snapshot_schema_version(self):
        self.assertEqual(set(self.frame.schema_version.astype(str)), {"2.0"})

    def test_snapshot_rebuild_report_passed(self):
        self.assertTrue(self.report["validation"]["passed"])
        self.assertEqual(self.report["replacement_status"], "replaced")
        self.assertTrue(all(self.report["validation"]["checks"].values()))
        # Rebuild may legitimately add rows when new source data appeared since the
        # last rebuild (e.g. a fresh BCTC scrape surfacing new periods); the
        # contract validated by row_count_not_reduced is "not reduced", not "unchanged".
        self.assertGreaterEqual(self.report["new_snapshot"]["row_count"], self.report["old_snapshot"]["row_count"])

    def test_unknown_unit_is_explicit_not_vnd(self):
        unknown = self.frame[self.frame.operating_cash_flow_normalized_unit == "unknown"]
        self.assertGreater(len(unknown), 0)
        self.assertEqual(set(unknown.operating_cash_flow_unit_status), {"unit_unknown"})
        self.assertEqual(set(unknown.operating_cash_flow_unit_multiplier), {1.0})

    def test_non_corporate_sga_not_applicable(self):
        for ticker in ("VCB", "SSI", "BVH"):
            rows = self.frame[self.frame.ticker == ticker]
            self.assertTrue(rows.sga.isna().all(), ticker)
            self.assertEqual(set(rows.sga_status), {"not_applicable"}, ticker)


if __name__ == "__main__":
    unittest.main()
