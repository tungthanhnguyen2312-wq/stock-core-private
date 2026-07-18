"""Cross-phase missing-data regressions; every input is an offline fixture."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))

import bctc_processor as processor  # noqa: E402
from financial_mapping import get_default_registry  # noqa: E402
from news_ticker_mapping import Alias, TickerAliasRegistry, map_article, summarize_news  # noqa: E402
from shareholder_pipeline import (  # noqa: E402
    ShareholderRecord, ShareholderSourceAdapter, build_shareholder_summary,
    load_manual_overrides, provider_parser, run_source_chain,
)


NOW = datetime(2026, 7, 13, tzinfo=timezone.utc)


def frame(ticker="PAN", **values):
    index = pd.MultiIndex.from_tuples([(ticker, "2025-Q4")], names=["ticker", "period"])
    return pd.DataFrame([values], index=index)


def ocf(values, basis="quarter", unit="VND"):
    return pd.DataFrame([{
        "ticker": "PAN", "period": period, "item_id": "operating_cash_flow",
        "value": value, "ocf_basis": basis, "mapping_priority": 100,
        "mapping_confidence": 1.0, "source": "fixture", "statement_scope": "consolidated",
        "audit_status": "audited", "raw_unit": unit, "normalized_unit": "VND",
        "effective_unit_multiplier": 1.0, "unit_status": "normalized",
    } for period, value in values.items()])


def adapter(payload):
    return ShareholderSourceAdapter("VCI", lambda _ticker: payload, provider_parser("VCI"), "fixture://vci")


class MissingDataRegressionTests(unittest.TestCase):
    def test_pan_ocf_not_overwritten_by_null_ttm(self):
        row = processor.build_ocf_period_metrics(ocf({"2025-Q4": -20.0}, "ytd")).iloc[0]
        self.assertTrue(pd.isna(row["operating_cash_flow_ttm"]))
        self.assertEqual(row["operating_cash_flow"], -20.0)

    def test_pan_latest_null_period_is_skipped(self):
        selected = processor.select_latest_non_null_reported_value([
            {"period": "2025-Q4", "operating_cash_flow": -20.0},
            {"period": "2026-Q1", "operating_cash_flow": None},
        ])
        self.assertEqual(selected["period"], "2025-Q4")

    def test_pan_ocf_ytd_not_mislabeled_as_quarter(self):
        row = processor.build_ocf_period_metrics(ocf({"2025-Q4": 120.0}, "ytd")).iloc[0]
        self.assertEqual(row["operating_cash_flow_basis"], "ytd")
        self.assertTrue(pd.isna(row["operating_cash_flow_quarter"]))

    def test_pan_ocf_unit_normalization(self):
        result = processor.normalize_ocf_unit(-2.88550621, "million VND")
        self.assertEqual(result["value"], -2_885_506.21)
        self.assertEqual(result["normalized_unit"], "VND")

    def test_pan_ebit_formula_and_provenance(self):
        row = processor.materialize_advanced_financial_metrics(
            frame(profit_before_tax=100.0, interest_expense=10.0)
        ).iloc[0]
        self.assertEqual(row["ebit"], 110.0)
        self.assertEqual(row["ebit_formula"], "profit_before_tax + interest_expense")
        self.assertEqual(json.loads(row["ebit_inputs"]), ["profit_before_tax", "interest_expense"])

    def test_pan_ebitda_insufficient_periods(self):
        row = processor.materialize_advanced_financial_metrics(frame(ebit=110.0, depreciation=10.0)).iloc[0]
        self.assertTrue(pd.isna(row["ebitda"]))
        self.assertEqual(row["ebitda_status"], "insufficient_periods")

    def test_financial_expense_not_used_as_interest_expense(self):
        mapped = get_default_registry().map_financial_item(
            "KBS", "corporate", "income_statement", "financial_expense", "Financial expense"
        )
        self.assertIsNone(mapped)

    def test_retained_earnings_mapping_is_stable(self):
        mapped = get_default_registry().map_financial_item(
            "VCI", "corporate", "balance_sheet", "current_period_undistributed_earnings", "Retained earnings"
        )
        self.assertEqual(mapped["canonical_metric"], "retained_earnings_current_year")

    def test_sga_not_applied_to_bank(self):
        row = processor.materialize_advanced_financial_metrics(
            frame("VCB", selling_expense=40.0, general_admin_expense=60.0)
        ).iloc[0]
        self.assertTrue(pd.isna(row["sga"]))
        self.assertEqual(row["sga_status"], "not_applicable")

    def test_pan_company_alias_maps_news(self):
        result = map_article({"title": "PAN Group announces results"}, TickerAliasRegistry([
            Alias("PAN", "PAN Group", "company_name", 100)
        ]))
        self.assertEqual(result["accepted"][0]["ticker"], "PAN")

    def test_generic_uppercase_token_not_mapped_as_ticker(self):
        result = map_article({"title": "PAN is a data processing method"}, TickerAliasRegistry([
            Alias("PAN", "PAN", "ticker", 50)
        ]))
        self.assertEqual(result, {"accepted": [], "candidates": []})

    def test_multi_ticker_news_mapping(self):
        registry = TickerAliasRegistry([
            Alias("PAN", "PAN Group", "company_name", 100),
            Alias("HPG", "Hoa Phat Group", "company_name", 100),
        ])
        result = map_article({"title": "PAN Group signs with Hoa Phat Group"}, registry)
        self.assertEqual({item["ticker"] for item in result["accepted"]}, {"PAN", "HPG"})

    def test_pan_no_company_news_has_explicit_status(self):
        summary = summarize_news(
            "PAN", [{"title": "Market closes lower", "published_utc": "2026-07-12T00:00:00Z"}],
            TickerAliasRegistry(), now=NOW,
        )
        self.assertEqual(summary["status"], "no_company_specific_news")

    def test_pan_shareholder_empty_has_reason(self):
        summary = build_shareholder_summary(run_source_chain("PAN", [adapter([])], NOW))
        self.assertEqual(summary["status"], "source_empty")
        self.assertEqual(summary["reason"], "configured_sources_returned_no_usable_records")

    def test_shareholder_parse_failure_is_not_source_empty(self):
        summary = build_shareholder_summary(run_source_chain("PAN", [adapter([{"unexpected": "payload"}])], NOW))
        self.assertEqual(summary["status"], "parse_failed")
        self.assertNotEqual(summary["status"], "source_empty")

    def test_shareholder_manual_override_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "manual.csv"
            path.write_text(
                "ticker,holder_name,shares,ownership_pct,as_of_date,source_name,source_reference,verified_at,note\n"
                "PAN,Verified Holder,100,25,2026-06-30,Filing,fixture://filing,2026-07-01T00:00:00Z,checked\n",
                encoding="utf-8",
            )
            manual = load_manual_overrides(path, "PAN")
        summary = build_shareholder_summary(run_source_chain("PAN", [], NOW), manual, today=date(2026, 7, 13))
        self.assertEqual(summary["records"][0]["source_reference"], "fixture://filing")
        self.assertEqual(summary["records"][0]["record_origin"], "manual")


if __name__ == "__main__":
    unittest.main()
