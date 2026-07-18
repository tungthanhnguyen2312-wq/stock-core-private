"""Phase 2 deterministic financial mapping registry tests."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bctc_processor as processor  # noqa: E402
from financial_mapping import (  # noqa: E402
    FinancialMappingRegistry,
    get_default_registry,
    normalize_label,
)


class RegistryMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = get_default_registry()

    def test_label_normalization_preserves_raw_while_matching_unicode(self):
        self.assertEqual(normalize_label("  CHI PHÍ   LÃI VAY  "), "chi phí lãi vay")
        self.assertEqual(normalize_label("Chi phí lãi vay", strip_accents=True), "chi phi lai vay")

    def test_exact_item_id_has_first_priority(self):
        result = self.registry.map_financial_item(
            "KBS", "corporate", "income_statement",
            "of_which_interest_expense", "một label không liên quan",
        )
        self.assertEqual(result["canonical_metric"], "interest_expense")
        self.assertEqual(result["match_method"], "item_id")
        self.assertEqual(result["mapping_rule_id"], "interest_corporate_income")

    def test_exact_source_field_precedes_label(self):
        result = self.registry.map_financial_item(
            "VCI", "corporate", "income_statement",
            "unknown", "không có label", source_field="interestExpense",
        )
        self.assertEqual(result["match_method"], "source_field")
        self.assertEqual(result["mapping_rule_id"], "interest_source_field")

    def test_exact_normalized_label(self):
        result = self.registry.map_financial_item(
            "KBS", "corporate", "income_statement", "unknown", "  Chi phí LÃI vay ",
        )
        self.assertEqual(result["match_method"], "exact_label")

    def test_regex_alias_without_fuzzy_matching(self):
        result = self.registry.map_financial_item(
            "KBS", "corporate", "cash_flow", "unknown", "Lưu chuyển tiền từ hoạt động kinh doanh",
        )
        self.assertEqual(result["canonical_metric"], "operating_cash_flow")
        self.assertEqual(result["match_method"], "regex")

    def test_financial_expense_is_not_interest_expense(self):
        result = self.registry.map_financial_item(
            "KBS", "corporate", "income_statement", "financial_expense", "Chi phí tài chính",
        )
        self.assertIsNone(result)

    def test_interest_paid_is_not_interest_expense(self):
        result = self.registry.map_financial_item(
            "KBS", "corporate", "cash_flow", "interest_paid", "Tiền lãi vay đã trả",
        )
        self.assertIsNone(result)

    def test_corporate_and_bank_profiles_are_separate(self):
        corporate = self.registry.map_financial_item(
            "KBS", "corporate", "income_statement", "selling_expenses", "Chi phí bán hàng",
        )
        bank = self.registry.map_financial_item(
            "KBS", "bank", "income_statement", "selling_expenses", "Chi phí bán hàng",
        )
        bank_interest = self.registry.map_financial_item(
            "KBS", "bank", "income_statement",
            "interest_expense_and_similar_expenses", "Chi phí lãi và tương tự",
        )
        self.assertEqual(corporate["canonical_metric"], "selling_expense")
        self.assertIsNone(bank)
        self.assertEqual(bank_interest["canonical_metric"], "interest_expense")

    def test_derivation_is_declared_but_not_available_for_bank(self):
        ebit = self.registry.derivation_for("ebit", "corporate")
        bank_sga = self.registry.derivation_for("sga", "bank")
        self.assertEqual(ebit["match_method"], "derived")
        self.assertEqual(ebit["derivation_rule"], "profit_before_tax + interest_expense")
        self.assertIsNone(bank_sga)

    def test_pan_profile_is_corporate_unknown_is_not_assumed(self):
        self.assertEqual(self.registry.entity_type_for("PAN"), "corporate")
        self.assertEqual(self.registry.entity_type_for("ZZZZ"), "unknown")

    def test_evf_profile_is_finance_company(self):
        self.assertEqual(self.registry.entity_type_for("EVF"), "finance_company")

    def test_finance_company_uses_bank_schema_item_ids(self):
        interest = self.registry.map_financial_item(
            "KBS", "finance_company", "income_statement",
            "interest_expense_and_similar_expenses", "Chi phí lãi và các chi phí tương tự",
        )
        retained = self.registry.map_financial_item(
            "VCI", "finance_company", "balance_sheet",
            "retained_earnings", "Lợi nhuận chưa phân phối",
        )
        self.assertEqual(interest["canonical_metric"], "interest_expense")
        self.assertEqual(interest["mapping_rule_id"], "interest_finance_company_income")
        self.assertEqual(retained["canonical_metric"], "retained_earnings")
        self.assertEqual(retained["mapping_rule_id"], "retained_finance_company")

    def test_sign_and_unit_multiplier_are_exposed(self):
        header = (
            "rule_id,canonical_metric,entity_type,report_type,source,item_id,source_field,"
            "normalized_label,label_regex,priority,sign_multiplier,unit_multiplier,"
            "derivation_rule,valid_from,valid_to\n"
        )
        row = "scaled,interest_expense,corporate,income_statement,KBS,x,,,,1,-1,1000,,,\n"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "map.csv"
            path.write_text(header + row, encoding="utf-8")
            registry = FinancialMappingRegistry(path)
            result = registry.map_financial_item("KBS", "corporate", "income_statement", "x", "x")
        self.assertEqual(result["sign_multiplier"], -1)
        self.assertEqual(result["unit_multiplier"], 1000)

    def test_higher_priority_rule_wins_and_validity_window_is_respected(self):
        header = (
            "rule_id,canonical_metric,entity_type,report_type,source,item_id,source_field,"
            "normalized_label,label_regex,priority,sign_multiplier,unit_multiplier,"
            "derivation_rule,valid_from,valid_to\n"
        )
        rows = (
            "old,old_metric,corporate,income_statement,KBS,x,,,,10,1,1,,2020-01-01,2025-12-31\n"
            "new,new_metric,corporate,income_statement,KBS,x,,,,20,1,1,,2026-01-01,\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "map.csv"
            path.write_text(header + rows, encoding="utf-8")
            registry = FinancialMappingRegistry(path)
            old = registry.map_financial_item(
                "KBS", "corporate", "income_statement", "x", "x", as_of="2025-06-30"
            )
            new = registry.map_financial_item(
                "KBS", "corporate", "income_statement", "x", "x", as_of="2026-06-30"
            )
        self.assertEqual(old["mapping_rule_id"], "old")
        self.assertEqual(new["mapping_rule_id"], "new")


class ProcessorRegistryIntegrationTests(unittest.TestCase):
    def test_melt_preserves_raw_and_mapping_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "PAN_income_statement_quarter.csv"
            path.write_text(
                "ticker,report_type,source,scraped_at,item,item_id,2026-Q1\n"
                "PAN,income_statement,KBS,2026-07-13,Trong đó: Chi phí đi vay,of_which_interest_expense,72858406000\n",
                encoding="utf-8",
            )
            melted = processor.load_and_melt_file(path)
        row = melted.iloc[0]
        self.assertEqual(row["raw_item_id"], "of_which_interest_expense")
        self.assertEqual(row["item_id"], "interest_expense")
        self.assertEqual(row["mapping_rule_id"], "interest_corporate_income")
        self.assertEqual(row["match_method"], "item_id")
        self.assertEqual(row["raw_label"], "Trong đó: Chi phí đi vay")

    def test_pan_registry_metrics_feed_phase4_derivations(self):
        result = processor.process_data(tickers_filter=["PAN"])
        latest = result[result["period"] == "2026-Q1"].iloc[0]
        q4 = result[result["period"] == "2025-Q4"].iloc[0]
        self.assertEqual(latest["profit_before_tax"], 527824222000)
        self.assertEqual(latest["interest_expense"], 72858406000)
        self.assertEqual(latest["retained_earnings"], 2618950443317)
        self.assertEqual(latest["selling_expense"], 140484426000)
        self.assertEqual(latest["general_admin_expense"], 213298423000)
        self.assertEqual(q4["operating_cash_flow"], -2885506210000)
        self.assertEqual(latest["ebit"], 600682628000)
        self.assertEqual(latest["ebit_status"], "derived")
        self.assertTrue(result["ebitda"].isna().all())
        self.assertEqual(latest["sga"], 353782849000)
        self.assertEqual(latest["sga_status"], "derived")

    def test_entity_profiles_do_not_apply_corporate_sga_to_bank_or_insurance(self):
        result = processor.process_data(tickers_filter=["HPG", "SSI", "VCB", "BVH"])
        hpg = result[result["ticker"] == "HPG"]
        ssi = result[result["ticker"] == "SSI"]
        vcb = result[result["ticker"] == "VCB"]
        bvh = result[result["ticker"] == "BVH"]
        self.assertTrue(hpg["selling_expense"].notna().any())
        self.assertTrue(hpg["general_admin_expense"].notna().any())
        self.assertTrue(vcb["interest_expense"].notna().any())
        self.assertTrue(vcb["selling_expense"].isna().all())
        self.assertTrue(ssi["depreciation_and_amortization"].notna().any())
        self.assertTrue(bvh["depreciation_and_amortization"].notna().any())
        self.assertTrue(bvh["selling_expense"].isna().all())

    def test_evf_finance_company_gets_bank_schema_mappings(self):
        result = processor.process_data(tickers_filter=["EVF"])
        latest = result[result["period"] == "2026-Q1"].iloc[0]
        self.assertEqual(latest["entity_type"], "finance_company")
        self.assertTrue(result["interest_expense"].notna().any())
        self.assertTrue(result["retained_earnings"].notna().any())
        self.assertTrue(result["selling_expense"].isna().all())


if __name__ == "__main__":
    unittest.main()
