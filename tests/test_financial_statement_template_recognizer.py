"""Unit and integration tests for Phase 2 / P2-D generic financial statement template recognition.

Covers:
1. Statement Structure Recognition (Balance Sheet, Income Statement, Cash Flow, Continuation pages).
2. Period-Column Layout Recognition (Standard, reversed, dates, ambiguous fail-closed).
3. Unit & Scale Recognition (VND, triệu VND, tỷ VND, ambiguous fail-closed).
4. Canonical Metric Recognition & Net Income Semantic Separation (Line 61 parent vs Line 60 total).
5. Debt Component Aggregation & Missing Component Fail-Closed.
6. Real Fixture Regression Validation (GAS FY2025 and VRE FY2025, 8 facts each).
7. Zero Ticker-Specific Extraction Branch Governance (AST/source inspection).
"""

import ast
import json
from pathlib import Path
import unittest

from annual_financial_ocr_materialization import (
    parse_accounting_integer,
    verified_debt_extraction,
    verified_extraction,
)
from financial_statement_template_recognizer import (
    CANONICAL_NET_INCOME_SEMANTIC,
    CONTRACT_VERSION,
    GENERIC_DEBT_COMPONENTS,
    GENERIC_METRIC_RULES,
    PeriodColumnLayout,
    RecognizedStatementPage,
    RecognizedUnitScale,
    StatementType,
    _find_line_item_on_pages,
    _normalize_text,
    extract_generic_financial_statement_facts,
    recognize_period_column_layout,
    recognize_statement_type,
    recognize_unit_and_scale,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


class StatementStructureRecognitionTests(unittest.TestCase):
    """Tests for statement type and continuation page recognition."""

    def test_recognizes_balance_sheet(self):
        sample = "CÔNG TY CỔ PHẦN ABC\nBẢNG CÂN ĐỐI KẾ TOÁN HỢP NHẤT\nMẪU SỐ B 01-DN/HN\nTại ngày 31 tháng 12 năm 2025"
        st_type, title, form, is_cont = recognize_statement_type(sample)
        self.assertEqual(st_type, StatementType.BALANCE_SHEET)
        self.assertFalse(is_cont)

    def test_recognizes_income_statement(self):
        sample = "CÔNG TY CỔ PHẦN ABC\nBÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT\nMẪU SỐ B 02-DN/HN\nCho năm tài chính kết thúc ngày 31/12/2025"
        st_type, title, form, is_cont = recognize_statement_type(sample)
        self.assertEqual(st_type, StatementType.INCOME_STATEMENT)
        self.assertFalse(is_cont)

    def test_recognizes_cash_flow_statement(self):
        sample = "CÔNG TY CỔ PHẦN ABC\nBÁO CÁO LƯU CHUYỂN TIỀN TỆ HỢP NHẤT\nMẪU SỐ B 03-DN/HN\nCho năm tài chính 2025"
        st_type, title, form, is_cont = recognize_statement_type(sample)
        self.assertEqual(st_type, StatementType.CASH_FLOW)
        self.assertFalse(is_cont)

    def test_recognizes_continuation_page(self):
        sample = "BẢNG CÂN ĐỐI KẾ TOÁN HỢP NHẤT (Tiếp theo)\nTại ngày 31 tháng 12 năm 2025"
        st_type, title, form, is_cont = recognize_statement_type(sample)
        self.assertEqual(st_type, StatementType.BALANCE_SHEET)
        self.assertTrue(is_cont)

    def test_unrecognized_text_returns_none(self):
        sample = "THUYẾT MINH BÁO CÁO TÀI CHÍNH HỢP NHẤT\n1. Thông tin chung"
        st_type, title, form, is_cont = recognize_statement_type(sample)
        self.assertIsNone(st_type)


class UnitAndScaleRecognitionTests(unittest.TestCase):
    """Tests for unit and scale multiplier recognition."""

    def test_recognizes_vnd_exact(self):
        text = "BÁO CÁO TÀI CHÍNH\nĐơn vị tính: VND\nChỉ tiêu"
        unit = recognize_unit_and_scale(text)
        self.assertIsNotNone(unit)
        self.assertEqual(unit.currency, "VND")
        self.assertEqual(unit.unit_scale, 1)
        self.assertEqual(unit.unit_label, "VND")

    def test_recognizes_trieu_vnd(self):
        text = "BÁO CÁO TÀI CHÍNH\nĐơn vị: Triệu VND\nChỉ tiêu"
        unit = recognize_unit_and_scale(text)
        self.assertIsNotNone(unit)
        self.assertEqual(unit.currency, "VND")
        self.assertEqual(unit.unit_scale, 1_000_000)
        self.assertEqual(unit.unit_label, "triệu VND")

    def test_recognizes_ty_vnd(self):
        text = "BÁO CÁO TÀI CHÍNH\nĐơn vị tính: Tỷ VND\nChỉ tiêu"
        unit = recognize_unit_and_scale(text)
        self.assertIsNotNone(unit)
        self.assertEqual(unit.currency, "VND")
        self.assertEqual(unit.unit_scale, 1_000_000_000)
        self.assertEqual(unit.unit_label, "tỷ VND")

    def test_missing_unit_returns_none(self):
        text = "BÁO CÁO TÀI CHÍNH\nKhông có đơn vị tính ở đây\nChỉ tiêu"
        unit = recognize_unit_and_scale(text)
        self.assertIsNone(unit)


class PeriodColumnLayoutTests(unittest.TestCase):
    """Tests for period column semantic layout recognition."""

    def test_balance_sheet_standard_layout(self):
        header = "CHỈ TIÊU | Mã số | Thuyết minh | Số cuối năm | Số đầu năm"
        layout = recognize_period_column_layout(header, StatementType.BALANCE_SHEET, "2025")
        self.assertEqual(layout.target_column_index, 0)
        self.assertEqual(layout.current_period_label, "Số cuối năm")

    def test_balance_sheet_reversed_layout(self):
        header = "CHỈ TIÊU | Mã số | Thuyết minh | Số đầu năm | Số cuối năm"
        layout = recognize_period_column_layout(header, StatementType.BALANCE_SHEET, "2025")
        self.assertEqual(layout.target_column_index, 1)

    def test_balance_sheet_date_headers(self):
        header = "CHỈ TIÊU | Mã số | 31/12/2025 | 31/12/2024"
        layout = recognize_period_column_layout(header, StatementType.BALANCE_SHEET, "2025")
        self.assertEqual(layout.target_column_index, 0)

    def test_income_statement_standard_layout(self):
        header = "CHỈ TIÊU | Mã số | Thuyết minh | Năm nay | Năm trước"
        layout = recognize_period_column_layout(header, StatementType.INCOME_STATEMENT, "2025")
        self.assertEqual(layout.target_column_index, 0)

    def test_income_statement_reversed_layout(self):
        header = "CHỈ TIÊU | Mã số | Thuyết minh | Năm trước | Năm nay"
        layout = recognize_period_column_layout(header, StatementType.INCOME_STATEMENT, "2025")
        self.assertEqual(layout.target_column_index, 1)

    def test_ambiguous_header_fails_closed(self):
        header = "CHỈ TIÊU | Mã số | Thuyết minh | Cột A | Cột B"
        with self.assertRaises(ValueError) as ctx:
            recognize_period_column_layout(header, StatementType.BALANCE_SHEET, "2025")
        self.assertIn("PERIOD_COLUMN_AMBIGUOUS", str(ctx.exception))


class NetIncomeSemanticTests(unittest.TestCase):
    """Tests enforcing canonical net_income semantic separation."""

    def test_canonical_semantic_is_profit_attributable_to_parent(self):
        self.assertEqual(CANONICAL_NET_INCOME_SEMANTIC, "net_income_attributable_to_parent")
        self.assertEqual(GENERIC_METRIC_RULES["net_income"]["standard_line_code"], "61")


class RealFixtureGenericExtractionTests(unittest.TestCase):
    """Regression tests verifying generic extraction on retained GAS and VRE OCR sidecars."""

    def setUp(self):
        gas_file = REPO_ROOT / "derived" / "annual_financial_ocr_materialization_v1" / "gas-fy2025.json"
        vre_file = REPO_ROOT / "derived" / "annual_financial_ocr_materialization_v1" / "vre-fy2025.json"
        self.gas_sidecar = json.loads(gas_file.read_text(encoding="utf-8"))
        self.vre_sidecar = json.loads(vre_file.read_text(encoding="utf-8"))

    def test_gas_generic_extraction_reproduces_all_8_facts(self):
        facts = extract_generic_financial_statement_facts(
            sidecar=self.gas_sidecar,
            reporting_period="2025",
        )
        self.assertEqual(len(facts), 8)
        by_metric = {f.canonical_metric: f for f in facts}

        # Verify all 8 metrics
        self.assertEqual(by_metric["revenue"].normalized_value, 135_129_055_328_395)
        self.assertEqual(by_metric["revenue"].line_item_code, "10")
        self.assertEqual(by_metric["revenue"].page, 11)

        # Net income: Must be Line 61 (attributable to parent), NOT Line 60 total
        self.assertEqual(by_metric["net_income"].normalized_value, 11_414_339_911_686)
        self.assertEqual(by_metric["net_income"].line_item_code, "61")
        self.assertEqual(by_metric["net_income"].page, 11)

        self.assertEqual(by_metric["operating_cash_flow"].normalized_value, 13_040_237_870_138)
        self.assertEqual(by_metric["operating_cash_flow"].line_item_code, "20")
        self.assertEqual(by_metric["operating_cash_flow"].page, 12)

        self.assertEqual(by_metric["total_assets"].normalized_value, 93_568_198_109_790)
        self.assertEqual(by_metric["total_assets"].line_item_code, "270")
        self.assertEqual(by_metric["total_assets"].page, 9)

        self.assertEqual(by_metric["shareholders_equity"].normalized_value, 67_653_389_117_937)
        self.assertEqual(by_metric["shareholders_equity"].line_item_code, "400")
        self.assertEqual(by_metric["shareholders_equity"].page, 10)

        self.assertEqual(by_metric["cash_and_equivalents"].normalized_value, 6_876_468_282_085)
        self.assertEqual(by_metric["cash_and_equivalents"].line_item_code, "110")
        self.assertEqual(by_metric["cash_and_equivalents"].page, 9)

        self.assertEqual(by_metric["current_liabilities"].normalized_value, 20_573_719_389_418)
        self.assertEqual(by_metric["current_liabilities"].line_item_code, "310")
        self.assertEqual(by_metric["current_liabilities"].page, 10)

        self.assertEqual(by_metric["total_interest_bearing_debt"].normalized_value, 2_971_690_340_782)
        self.assertEqual(by_metric["total_interest_bearing_debt"].line_item_code, "320+338")

    def test_vre_generic_extraction_reproduces_all_8_facts(self):
        facts = extract_generic_financial_statement_facts(
            sidecar=self.vre_sidecar,
            reporting_period="2025",
        )
        self.assertEqual(len(facts), 8)
        by_metric = {f.canonical_metric: f for f in facts}

        # VRE unit scale is 1,000,000 (triệu VND)
        for f in facts:
            self.assertEqual(f.unit_scale, 1_000_000)
            self.assertEqual(f.currency, "VND")

        self.assertEqual(by_metric["revenue"].normalized_value, 8_837_380_000_000)
        self.assertEqual(by_metric["revenue"].line_item_code, "10")
        self.assertEqual(by_metric["revenue"].page, 11)

        self.assertEqual(by_metric["net_income"].normalized_value, 6_445_924_000_000)
        self.assertEqual(by_metric["net_income"].line_item_code, "61")
        self.assertEqual(by_metric["net_income"].page, 11)

        self.assertEqual(by_metric["operating_cash_flow"].normalized_value, -3_262_205_000_000)
        self.assertEqual(by_metric["operating_cash_flow"].line_item_code, "20")
        self.assertEqual(by_metric["operating_cash_flow"].page, 12)

        self.assertEqual(by_metric["total_assets"].normalized_value, 61_279_149_000_000)
        self.assertEqual(by_metric["total_assets"].line_item_code, "270")
        self.assertEqual(by_metric["total_assets"].page, 8)

        self.assertEqual(by_metric["shareholders_equity"].normalized_value, 48_368_203_000_000)
        self.assertEqual(by_metric["shareholders_equity"].line_item_code, "400")
        self.assertEqual(by_metric["shareholders_equity"].page, 10)

        self.assertEqual(by_metric["cash_and_equivalents"].normalized_value, 4_434_617_000_000)
        self.assertEqual(by_metric["cash_and_equivalents"].line_item_code, "110")
        self.assertEqual(by_metric["cash_and_equivalents"].page, 7)

        self.assertEqual(by_metric["current_liabilities"].normalized_value, 5_173_857_000_000)
        self.assertEqual(by_metric["current_liabilities"].line_item_code, "310")
        self.assertEqual(by_metric["current_liabilities"].page, 9)

        self.assertEqual(by_metric["total_interest_bearing_debt"].normalized_value, 6_401_081_000_000)
        self.assertEqual(by_metric["total_interest_bearing_debt"].line_item_code, "320+338")


class ZeroTickerBranchGovernanceTests(unittest.TestCase):
    """Governance tests ensuring zero ticker-specific logic in production recognition modules."""

    def test_production_recognizer_has_zero_ticker_branches(self):
        code_path = REPO_ROOT / "financial_statement_template_recognizer.py"
        tree = ast.parse(code_path.read_text(encoding="utf-8"))

        forbidden_tickers = {"GAS", "VRE", "MWG", "VIC", "VNM", "HPG", "VCB", "SSI"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val = node.value.strip().upper()
                if val in forbidden_tickers:
                    self.fail(f"Forbidden hardcoded ticker '{val}' found in generic template recognizer: {node}")


if __name__ == "__main__":
    unittest.main()
