"""Phase 4 advanced financial metric derivation and provenance tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bctc_processor as processor  # noqa: E402
from financial_mapping import get_default_registry  # noqa: E402


def _frame(ticker: str = "PAN", **values: float) -> pd.DataFrame:
    index = pd.MultiIndex.from_tuples([(ticker, "2026-Q1")], names=["ticker", "period"])
    return pd.DataFrame([values], index=index)


class AdvancedFinancialMetricsPhase4Tests(unittest.TestCase):
    def test_ebit_reported_priority(self):
        result = processor.materialize_advanced_financial_metrics(
            _frame(ebit=999.0, profit_before_tax=100.0, interest_expense=10.0)
        ).iloc[0]
        self.assertEqual(result["ebit"], 999.0)
        self.assertEqual(result["ebit_status"], "reported")
        self.assertIsNone(result["ebit_formula"])

    def test_ebit_derived_formula(self):
        result = processor.materialize_advanced_financial_metrics(
            _frame(profit_before_tax=100.0, interest_expense=10.0)
        ).iloc[0]
        self.assertEqual(result["ebit"], 110.0)
        self.assertEqual(result["ebit_status"], "derived")
        self.assertEqual(result["ebit_formula"], "profit_before_tax + interest_expense")
        self.assertEqual(json.loads(result["ebit_inputs"]), ["profit_before_tax", "interest_expense"])

    def test_ebit_interest_sign(self):
        result = processor.materialize_advanced_financial_metrics(
            _frame(profit_before_tax=100.0, interest_expense=-10.0)
        ).iloc[0]
        self.assertTrue(pd.isna(result["ebit"]))
        self.assertEqual(result["interest_expense_sign_convention"], "negative_unresolved")
        self.assertEqual(result["ebit_reason"], "interest_expense_sign_not_normalized")

    def test_ebitda_requires_complete_inputs(self):
        result = processor.materialize_advanced_financial_metrics(
            _frame(ebit=110.0, depreciation=10.0)
        ).iloc[0]
        self.assertTrue(pd.isna(result["ebitda"]))
        self.assertEqual(result["ebitda_status"], "insufficient_periods")
        self.assertEqual(result["ebitda_reason"], "missing_ebit_or_complete_da_inputs")

    def test_financial_expense_not_used_as_interest_expense(self):
        mapped = get_default_registry().map_financial_item(
            "KBS", "corporate", "income_statement",
            "financial_expense", "Chi phí tài chính",
        )
        self.assertIsNone(mapped)

    def test_retained_earnings_mapping(self):
        registry = get_default_registry()
        mapped = registry.map_financial_item(
            "VCI", "corporate", "balance_sheet",
            "current_period_undistributed_earnings", "LNST chưa phân phối kỳ này",
        )
        self.assertEqual(mapped["canonical_metric"], "retained_earnings_current_year")
        result = processor.materialize_advanced_financial_metrics(
            _frame(retained_earnings_prior_year=70.0, retained_earnings_current_year=30.0)
        ).iloc[0]
        self.assertEqual(result["retained_earnings_end_period"], 100.0)
        self.assertEqual(result["retained_earnings_status"], "derived")

    def test_depreciation_and_amortization_are_not_invented(self):
        result = processor.materialize_advanced_financial_metrics(
            _frame(ebit=100.0, depreciation_and_amortization=20.0)
        ).iloc[0]
        self.assertTrue(pd.isna(result["depreciation"]))
        self.assertTrue(pd.isna(result["amortization"]))
        self.assertEqual(result["ebitda"], 120.0)
        self.assertEqual(result["ebitda_formula"], "ebit + depreciation_and_amortization")

    def test_sga_sum(self):
        result = processor.materialize_advanced_financial_metrics(
            _frame(selling_expense=40.0, general_admin_expense=60.0)
        ).iloc[0]
        self.assertEqual(result["sga"], 100.0)
        self.assertEqual(result["sga_status"], "derived")
        self.assertEqual(result["sga_formula"], "selling_expense + general_admin_expense")

    def test_ebit_ebitda_not_applicable_for_confirmed_non_corporate(self):
        result = processor.materialize_advanced_financial_metrics(
            _frame(ticker="EVF", profit_before_tax=100.0, interest_expense=10.0)
        ).iloc[0]
        self.assertTrue(pd.isna(result["ebit"]))
        self.assertEqual(result["ebit_status"], "not_applicable")
        self.assertEqual(result["ebit_reason"], "corporate_ebit_structure_not_applicable")
        self.assertTrue(pd.isna(result["ebitda"]))
        self.assertEqual(result["ebitda_status"], "not_applicable")
        self.assertEqual(result["ebitda_reason"], "corporate_ebitda_structure_not_applicable")

    def test_ebit_ebitda_stay_insufficient_periods_for_unprofiled_unknown_entity(self):
        """Guard: entity_type=='unknown' (the ~1478 tickers with no profile row) must NOT be
        silently treated as confirmed-non-corporate — only reported/derived/insufficient_periods
        apply until the ticker is actually profiled."""
        result = processor.materialize_advanced_financial_metrics(
            _frame(ticker="ZZZZ", ebit=110.0, depreciation=10.0)
        ).iloc[0]
        self.assertTrue(pd.isna(result["ebitda"]))
        self.assertEqual(result["ebitda_status"], "insufficient_periods")
        self.assertEqual(result["ebitda_reason"], "missing_ebit_or_complete_da_inputs")

    def test_liquidity_ratios_not_applicable_for_evf_but_reported_for_hpg(self):
        result = processor.process_data(tickers_filter=["EVF", "HPG"])
        evf = result[result["ticker"] == "EVF"]
        hpg = result[result["ticker"] == "HPG"]
        for metric in ("current_ratio", "quick_ratio", "cash_ratio", "inventory_turnover"):
            self.assertTrue((evf[f"{metric}_status"] == "not_applicable").all())
            self.assertTrue(evf[metric].isna().all())
            self.assertTrue((hpg[f"{metric}_status"].isin(["derived", "source_empty"])).all())
        self.assertTrue(hpg["current_ratio"].notna().any())

    def test_shares_period_end_uses_charter_capital_fallback_for_bank_schema(self):
        result = processor.process_data(tickers_filter=["EVF"])
        latest = result[result["period"] == "2026-Q1"].iloc[0]
        self.assertFalse(pd.isna(latest["shares_period_end"]))
        self.assertEqual(latest["shares_period_end"], latest["shares_outstanding"])
        self.assertEqual(latest["shares_period_end_status"], "derived")

    def test_statement_unit_contract_defaults_to_unconfirmed_vnd(self):
        result = processor.process_data(tickers_filter=["PAN"])
        self.assertTrue((result["statement_currency"] == "VND").all())
        self.assertTrue((result["unit_status"] == "unit_unknown").all())
        self.assertTrue(result["statement_scale"].isna().all())
        self.assertTrue((result["unit_evidence"].str.len() > 0).all())

    def test_compute_roe_ttm_uses_boundary_average_equity_when_both_ends_available(self):
        profit_map = {
            ("X", "2026-Q1"): 10.0, ("X", "2025-Q4"): 10.0, ("X", "2025-Q3"): 10.0, ("X", "2025-Q2"): 10.0,
        }
        equity_map = {("X", "2026-Q1"): 220.0, ("X", "2025-Q1"): 180.0}
        result = processor.compute_roe_ttm("X", "2026-Q1", profit_map, equity_map)
        self.assertAlmostEqual(result["value"], 40.0 / 200.0)
        self.assertEqual(result["equity_basis"], "ttm_average_equity")

    def test_compute_roe_ttm_falls_back_to_ending_equity_when_boundary_missing(self):
        profit_map = {
            ("X", "2026-Q1"): 10.0, ("X", "2025-Q4"): 10.0, ("X", "2025-Q3"): 10.0, ("X", "2025-Q2"): 10.0,
        }
        equity_map = {("X", "2026-Q1"): 200.0}  # 2025-Q1 (boundary) missing
        result = processor.compute_roe_ttm("X", "2026-Q1", profit_map, equity_map)
        self.assertAlmostEqual(result["value"], 40.0 / 200.0)
        self.assertEqual(result["equity_basis"], "ttm_ending_equity_fallback")

    def test_compute_roe_ttm_requires_all_four_consecutive_quarters(self):
        # 2025-Q2 missing -> only 3 of 4 required quarters have net_profit.
        profit_map = {("X", "2026-Q1"): 10.0, ("X", "2025-Q4"): 10.0, ("X", "2025-Q3"): 10.0}
        equity_map = {("X", "2026-Q1"): 200.0, ("X", "2025-Q1"): 180.0}
        result = processor.compute_roe_ttm("X", "2026-Q1", profit_map, equity_map)
        self.assertIsNone(result["value"])
        self.assertIsNone(result["equity_basis"])

    def test_compute_roe_ttm_not_applicable_for_year_period_type(self):
        result = processor.compute_roe_ttm("X", "2026", {}, {})
        self.assertIsNone(result["value"])

    def test_pow_roe_quarter_matches_legacy_roe_with_explicit_unit_and_basis(self):
        """Real fixture for the exact trap named in the spec: POW 2026-Q1 financial_snapshot
        roe (0.017514, single-quarter ratio) vs metadata.roe (6.94, trailing %) must never be
        confusable — roe_quarter carries value/unit/basis/period/period_calendar_end/status
        so a consumer cannot mistake one for the other."""
        result = processor.process_data(tickers_filter=["POW"])
        latest = result[result["period"] == "2026-Q1"].iloc[0]
        self.assertAlmostEqual(latest["roe"], 0.017514, places=6)
        self.assertAlmostEqual(latest["roe_quarter"], latest["roe"], places=12)
        self.assertEqual(latest["roe_quarter_unit"], "ratio")
        self.assertEqual(latest["roe_quarter_basis"], "quarter_average_equity")
        self.assertEqual(latest["roe_quarter_period"], "2026-Q1")
        self.assertEqual(latest["roe_quarter_period_calendar_end"], "2026-03-31")
        self.assertEqual(latest["roe_quarter_status"], "derived")
        self.assertEqual(latest["roe_status"], "deprecated")
        self.assertEqual(latest["roe_canonical_metric"], "roe_quarter")

    def test_pow_roe_ttm_is_honestly_insufficient_not_fabricated(self):
        """POW only has 3 populated net_profit quarters (2025-Q3..2026-Q1) in current
        data_bctc — a true trailing-12-month figure is not computable locally, and must say
        so explicitly rather than silently mirror the external metadata.roe trailing %."""
        result = processor.process_data(tickers_filter=["POW"])
        latest = result[result["period"] == "2026-Q1"].iloc[0]
        self.assertTrue(pd.isna(latest["roe_ttm"]))
        self.assertEqual(latest["roe_ttm_status"], "insufficient_periods")
        self.assertEqual(
            latest["roe_ttm_reason"], "requires_four_consecutive_reported_quarters_and_ttm_window_equity"
        )

    def test_roe_fy_not_applicable_on_quarter_rows(self):
        result = processor.process_data(tickers_filter=["PAN"])
        self.assertTrue((result["roe_fy_status"] == "not_applicable").all())
        self.assertTrue(result["roe_fy"].isna().all())

    def test_eps_calc_and_book_value_are_proxy_not_canonical(self):
        result = processor.process_data(tickers_filter=["PAN"])
        latest = result[result["period"] == "2026-Q1"].iloc[0]
        self.assertFalse(pd.isna(latest["eps_calc"]))
        self.assertEqual(latest["eps_calc_status"], "proxy")
        self.assertNotEqual(latest["eps_calc_status"], "reported")
        self.assertFalse(pd.isna(latest["book_value"]))
        self.assertEqual(latest["book_value_status"], "proxy")

    def test_sga_not_applicable_for_bank(self):
        result = processor.materialize_advanced_financial_metrics(
            _frame("VCB", selling_expense=40.0, general_admin_expense=60.0)
        ).iloc[0]
        self.assertTrue(pd.isna(result["sga"]))
        self.assertEqual(result["sga_status"], "not_applicable")
        self.assertEqual(result["sga_reason"], "corporate_sga_structure_not_applicable")


if __name__ == "__main__":
    unittest.main()
