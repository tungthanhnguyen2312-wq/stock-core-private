import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.diagnostics.missing_data_audit import build_audit  # noqa: E402


class TestPanMissingDataAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        required = [
            ROOT / "data_bctc" / "PAN_cash_flow_quarter.csv",
            ROOT / "financial_snapshot.csv",
            ROOT / "vn_stock.db",
            ROOT.parent / "AI ANALYZE" / "exports" / "context_packages" / "PAN_context.json",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise unittest.SkipTest("Live PAN diagnostic sources are unavailable: " + ", ".join(missing))
        cls.audit = build_audit()

    def test_pan_ocf_raw_data_detection(self):
        ocf = self.audit["metrics"]["operating_cash_flow"]
        self.assertTrue(ocf["raw_data_found"])
        self.assertTrue(ocf["mapping_found"])
        self.assertEqual(ocf["latest_non_null_snapshot"]["period"], "2025-Q4")
        self.assertEqual(ocf["latest_non_null_snapshot"]["value"], -2885506210000)

    def test_pan_latest_null_period_is_diagnosed(self):
        ocf = self.audit["metrics"]["operating_cash_flow"]
        # 2026-Q1 (kỳ mới nhất trong snapshot) không tự có OCF -> reason vẫn đúng mô tả điều đó.
        self.assertEqual(ocf["selected_period"], "2026-Q1")
        self.assertEqual(ocf["reason"], "latest_period_value_null_no_non_null_fallback")
        # Nhưng context package (build_ticker_context.py) CHỦ Ý fallback về kỳ có số gần nhất
        # thay vì null (hành vi P0-4 đã thống nhất, có provenance đầy đủ) -> context_value KHÔNG
        # còn None. Test phải xác nhận fallback đúng giá trị/kỳ nguồn VÀ không bị giả mạo thành
        # dữ liệu của kỳ hiện tại (2026-Q1).
        self.assertIsNotNone(ocf["latest_non_null_snapshot"])
        self.assertEqual(ocf["context_value"], ocf["latest_non_null_snapshot"]["value"])
        self.assertIsNotNone(ocf["context_meta"])
        self.assertEqual(ocf["context_meta"]["period"], ocf["latest_non_null_snapshot"]["period"])
        self.assertNotEqual(ocf["context_meta"]["period"], ocf["selected_period"])
        self.assertTrue(ocf["context_meta"]["details"]["selected_latest_non_null_reported"])
        self.assertEqual(ocf["context_meta"]["details"]["financial_latest_period"], ocf["selected_period"])

    def test_advanced_metrics_have_specific_raw_mapping_diagnostics(self):
        for metric in ("interest_expense", "retained_earnings"):
            with self.subTest(metric=metric):
                item = self.audit["metrics"][metric]
                self.assertTrue(item["raw_data_found"])
                self.assertTrue(item["mapping_found"])
                self.assertIsNone(item["reason"])
                self.assertEqual(item["snapshot_status"], "reported")
        depreciation = self.audit["metrics"]["depreciation"]
        self.assertTrue(depreciation["raw_data_found"])
        self.assertTrue(depreciation["mapping_found"])
        self.assertEqual(depreciation["snapshot_status"], "source_empty")
        self.assertEqual(depreciation["reason"], "reported_depreciation_not_available")
        self.assertEqual(self.audit["metrics"]["ebit"]["snapshot_status"], "derived")
        self.assertIsNone(self.audit["metrics"]["ebit"]["reason"])
        self.assertEqual(self.audit["metrics"]["ebitda"]["snapshot_status"], "insufficient_periods")
        self.assertEqual(self.audit["metrics"]["ebitda"]["reason"], "missing_ebit_or_complete_da_inputs")
        self.assertEqual(self.audit["metrics"]["sga"]["snapshot_status"], "derived")
        self.assertIsNone(self.audit["metrics"]["sga"]["reason"])
        ebitda_inputs = self.audit["metrics"]["ebitda"]["derivation_input_evidence"]
        self.assertTrue(ebitda_inputs["depreciation"])
        self.assertFalse(ebitda_inputs["amortization"])

    def test_news_alias_mapping_distinguishes_no_company_news(self):
        news = self.audit["metrics"]["news_summary"]
        self.assertTrue(news["raw_data_found"])
        self.assertNotIn("ticker", news["raw_schema"])
        self.assertTrue(news["mapping_found"])
        self.assertEqual(news["mapping_method"], "canonical_alias_registry")
        self.assertEqual(news["company_news_count"], 0)
        self.assertGreater(news["market_news_count"], 0)
        self.assertEqual(news["reason"], "no_company_specific_news")

    def test_pan_shareholders_not_queried_is_not_source_empty(self):
        shareholders = self.audit["metrics"]["shareholder_summary"]
        self.assertFalse(shareholders["raw_data_found"])
        self.assertIsNone(shareholders["progress"])
        self.assertEqual(shareholders["reason"], "ticker_not_queried")

    def test_audit_is_strict_json_serializable(self):
        payload = json.dumps(self.audit, ensure_ascii=False, allow_nan=False)
        self.assertIn('"ticker": "PAN"', payload)


if __name__ == "__main__":
    unittest.main()
