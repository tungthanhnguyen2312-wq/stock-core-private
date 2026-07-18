from __future__ import annotations

import csv
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))

import bctc_processor as processor  # noqa: E402
from financial_mapping import get_default_registry  # noqa: E402
from news_ticker_mapping import Alias, TickerAliasRegistry, map_article, summarize_news  # noqa: E402
from shareholder_pipeline import (  # noqa: E402
    ShareholderSourceAdapter, build_shareholder_summary, provider_parser, run_source_chain,
)


NOW = datetime(2026, 7, 13, tzinfo=timezone.utc)


def advanced(**values):
    idx = pd.MultiIndex.from_tuples([("PAN", "2025-Q4")], names=["ticker", "period"])
    return processor.materialize_advanced_financial_metrics(pd.DataFrame([values], index=idx)).iloc[0]


class MutationAndGoldenTests(unittest.TestCase):
    def test_mutation_news_alias_removed(self):
        article = {"title": "PAN Group announces results"}
        self.assertTrue(map_article(article, TickerAliasRegistry([Alias("PAN", "PAN Group", "company_name")]))["accepted"])
        self.assertFalse(map_article(article, TickerAliasRegistry())["accepted"])

    def test_mutation_ocf_identifier_and_label_changed(self):
        mapped = get_default_registry().map_financial_item(
            "VCI", "corporate", "cash_flow", "mutated_ocf", "Mutated cash line"
        )
        self.assertIsNone(mapped)

    def test_mutation_interest_sign_rejected(self):
        row = advanced(profit_before_tax=100.0, interest_expense=-10.0)
        self.assertEqual(row["ebit_reason"], "interest_expense_sign_not_normalized")

    def test_mutation_missing_quarter_blocks_ttm(self):
        rows = pd.DataFrame([{
            "ticker": "PAN", "period": p, "item_id": "operating_cash_flow", "value": v,
            "ocf_basis": "quarter", "mapping_priority": 1, "mapping_confidence": 1.0,
            "source": "fixture", "statement_scope": "consolidated", "audit_status": "audited",
            "raw_unit": "VND", "normalized_unit": "VND", "effective_unit_multiplier": 1.0,
            "unit_status": "normalized",
        } for p, v in {"2025-Q1": 1, "2025-Q2": 2, "2025-Q4": 4}.items()])
        result = processor.build_ocf_period_metrics(rows)
        self.assertTrue(result["operating_cash_flow_ttm"].isna().all())

    def test_mutation_unit_drift_is_explicit(self):
        result = processor.normalize_ocf_unit(10.0, "bags")
        self.assertEqual(result["unit_status"], "unit_unknown")

    def test_mutation_latest_null_does_not_win(self):
        result = processor.select_latest_non_null_reported_value([
            {"period": "2025-Q4", "operating_cash_flow": 10},
            {"period": "2026-Q1", "operating_cash_flow": None},
        ])
        self.assertEqual(result["period"], "2025-Q4")

    def test_mutation_shareholder_empty_is_not_zero(self):
        adapter = ShareholderSourceAdapter("VCI", lambda _: [], provider_parser("VCI"), "fixture://vci")
        summary = build_shareholder_summary(run_source_chain("PAN", [adapter], NOW))
        self.assertIsNone(summary["major_shareholders_count"])

    def test_mutation_shareholder_malformed_is_parse_failed(self):
        adapter = ShareholderSourceAdapter("VCI", lambda _: [{"bad": 1}], provider_parser("VCI"), "fixture://vci")
        summary = build_shareholder_summary(run_source_chain("PAN", [adapter], NOW))
        self.assertEqual(summary["status"], "parse_failed")

    def test_pan_financial_golden(self):
        expected = json.loads((FIXTURES / "expected" / "pan_financial_metrics.json").read_text(encoding="utf-8"))
        with (FIXTURES / "regression" / "entity_financial_rows.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        pbt = float(next(row["value"] for row in rows if row["ticker"] == "PAN" and row["item_id"] == "profit_before_tax"))
        interest = float(next(row["value"] for row in rows if row["ticker"] == "PAN" and row["item_id"] == "interest_expense"))
        ebit = advanced(profit_before_tax=pbt, interest_expense=interest)
        ocf_rows = [row for row in rows if row["ticker"] == "PAN" and row["item_id"] == "operating_cash_flow"]
        usable = [row for row in ocf_rows if row["value"]]
        normalized = processor.normalize_ocf_unit(float(usable[0]["value"]), usable[0]["raw_unit"])
        actual = {
            "ebit": ebit["ebit"], "ebit_formula": ebit["ebit_formula"],
            "ebit_inputs": json.loads(ebit["ebit_inputs"]),
            "operating_cash_flow": normalized["value"],
            "operating_cash_flow_basis": usable[0]["period_type"],
            "selected_period": usable[0]["period"],
        }
        self.assertEqual(actual, expected)

    def test_pan_news_golden(self):
        articles = json.loads((FIXTURES / "regression" / "news_articles.json").read_text(encoding="utf-8"))
        registry = TickerAliasRegistry.from_csv(FIXTURES / "regression" / "ticker_aliases.csv")
        summary = summarize_news("PAN", articles, registry, now=NOW)
        actual = {key: summary[key] for key in ("status", "company_news_count", "market_news_count", "mapping_version")}
        expected = json.loads((FIXTURES / "expected" / "pan_news_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)

    def test_pan_shareholder_golden(self):
        payloads = json.loads((FIXTURES / "regression" / "shareholder_payloads.json").read_text(encoding="utf-8"))
        adapter = ShareholderSourceAdapter("VCI", lambda _: payloads["source_empty"], provider_parser("VCI"), "fixture://vci")
        summary = build_shareholder_summary(run_source_chain("PAN", [adapter], NOW))
        keys = ("ticker", "status", "reason", "major_shareholders_count", "raw_record_count", "parsed_record_count")
        actual = {key: summary[key] for key in keys}
        expected = json.loads((FIXTURES / "expected" / "pan_shareholder_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)

    def test_entity_profile_fixture_expectations(self):
        expectations = json.loads(
            (FIXTURES / "regression" / "entity_validation_expectations.json").read_text(encoding="utf-8")
        )
        with (FIXTURES / "regression" / "entity_financial_rows.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual({row["ticker"] for row in rows}, set(expectations))
        self.assertEqual(
            {row["ticker"]: row["entity_type"] for row in rows},
            {ticker: item["entity_type"] for ticker, item in expectations.items()},
        )
        bank = processor.materialize_advanced_financial_metrics(
            pd.DataFrame(
                [{"selling_expense": 40.0, "general_admin_expense": 60.0}],
                index=pd.MultiIndex.from_tuples([("VCB", "2025-Q4")], names=["ticker", "period"]),
            )
        ).iloc[0]
        self.assertEqual(bank["sga_status"], expectations["VCB"]["sga_status"])


if __name__ == "__main__":
    unittest.main()
