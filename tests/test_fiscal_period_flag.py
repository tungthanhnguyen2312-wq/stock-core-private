# ==========================================================================
# TEST cho P0-4 (bctc_processor.py: flag_fiscal_period_verification) — nâng cấp workflow
# 2026-07-17 chiều, mục 6: gắn cờ kỳ BCTC chưa xác minh theo lịch dương, không coi nhãn kỳ
# '2026-Qx' là kỳ dương lịch tương lai đã có số liệu nếu chưa tới ngày kết thúc quý đó.
#
# Test THUẦN (fixture dựng tay, không phụ thuộc dữ liệu data_bctc/ thật) để xác định hành vi
# không đổi bất kể ngày chạy test hay dữ liệu BCTC hiện hành. Test tích hợp trên dữ liệu thật xem
# tests/test_export_ai_bundle.py::FiscalPeriodQualityIntegrationTests.
# ==========================================================================

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bctc_processor as bp  # noqa: E402


class CalendarPeriodEndTests(unittest.TestCase):
    def test_quarter_end_dates(self):
        self.assertEqual(bp.calendar_period_end("2026-Q1", "quarter"), pd.Timestamp("2026-03-31"))
        self.assertEqual(bp.calendar_period_end("2026-Q2", "quarter"), pd.Timestamp("2026-06-30"))
        self.assertEqual(bp.calendar_period_end("2026-Q3", "quarter"), pd.Timestamp("2026-09-30"))
        self.assertEqual(bp.calendar_period_end("2026-Q4", "quarter"), pd.Timestamp("2026-12-31"))

    def test_year_end_date(self):
        self.assertEqual(bp.calendar_period_end("2026", "year"), pd.Timestamp("2026-12-31"))

    def test_unparseable_returns_none(self):
        self.assertIsNone(bp.calendar_period_end("not-a-period", "quarter"))
        self.assertIsNone(bp.calendar_period_end("2026-Q1", "quarter_typo"))
        self.assertIsNone(bp.calendar_period_end(None, "quarter"))


class FlagFiscalPeriodVerificationTests(unittest.TestCase):
    """Ngày tham chiếu CỐ ĐỊNH (2026-07-17, cùng ngày dùng xuyên suốt các báo cáo phiên này) để
    test không đổi kết quả theo ngày chạy thật."""

    AS_OF = "2026-07-17"

    def _df(self, rows):
        return pd.DataFrame(rows)

    def test_past_and_present_quarters_are_verified(self):
        df = self._df([
            {"ticker": "HPG", "period": "2025-Q4", "period_type": "quarter"},
            {"ticker": "HPG", "period": "2026-Q1", "period_type": "quarter"},  # kết thúc 31/03, đã qua
            {"ticker": "HPG", "period": "2026-Q2", "period_type": "quarter"},  # kết thúc 30/06, đã qua
        ])
        out = bp.flag_fiscal_period_verification(df, as_of_date=self.AS_OF)
        self.assertTrue((out["fiscal_period_status"] == "calendar_aligned_or_past").all())
        self.assertTrue(out["period_verified"].all())

    def test_future_calendar_quarter_is_flagged_not_verified(self):
        # 2026-Q3 kết thúc 30/09/2026 — SAU ngày tham chiếu 17/07/2026 -> chưa thể có số liệu
        # dương lịch thật, dấu hiệu năm tài chính lệch (như HSG/CTD) hoặc lỗi nhãn nguồn.
        df = self._df([{"ticker": "CTD", "period": "2026-Q3", "period_type": "quarter"}])
        out = bp.flag_fiscal_period_verification(df, as_of_date=self.AS_OF)
        self.assertEqual(out.iloc[0]["fiscal_period_status"], "future_relative_to_calendar_quarter_end")
        self.assertFalse(out.iloc[0]["period_verified"])
        self.assertEqual(out.iloc[0]["period_calendar_end"], "2026-09-30")

    def test_boundary_quarter_ending_exactly_on_as_of_date_is_verified(self):
        # Biên: quý kết thúc ĐÚNG ngày tham chiếu phải coi là đã qua (<=), không phải tương lai.
        df = self._df([{"ticker": "X", "period": "2026-Q2", "period_type": "quarter"}])
        out = bp.flag_fiscal_period_verification(df, as_of_date="2026-06-30")
        self.assertEqual(out.iloc[0]["fiscal_period_status"], "calendar_aligned_or_past")

    def test_unparseable_period_label_is_flagged_separately_from_future(self):
        df = self._df([{"ticker": "Y", "period": "weird-label", "period_type": "quarter"}])
        out = bp.flag_fiscal_period_verification(df, as_of_date=self.AS_OF)
        self.assertEqual(out.iloc[0]["fiscal_period_status"], "unparseable_period_label")
        self.assertFalse(out.iloc[0]["period_verified"])

    def test_year_type_future_is_flagged(self):
        df = self._df([{"ticker": "Z", "period": "2027", "period_type": "year"}])
        out = bp.flag_fiscal_period_verification(df, as_of_date=self.AS_OF)
        self.assertEqual(out.iloc[0]["fiscal_period_status"], "future_relative_to_calendar_quarter_end")

    def test_does_not_mutate_input_frame(self):
        df = self._df([{"ticker": "HPG", "period": "2026-Q1", "period_type": "quarter"}])
        before_cols = set(df.columns)
        bp.flag_fiscal_period_verification(df, as_of_date=self.AS_OF)
        self.assertEqual(set(df.columns), before_cols, "Hàm phải trả bản copy, không sửa df gốc")


class FindYoyComparisonPeriodTests(unittest.TestCase):
    """item B (Data Contract Hardening v1.1): find_yoy_comparison_period phải khớp theo
    period_calendar_end (~12 tháng trước, có dung sai), không ghép nhãn 'YYYY-Qn' thuần túy,
    và chỉ chấp nhận candidate đã xác minh theo lịch dương."""

    AS_OF = "2026-07-17"

    def test_matches_same_label_prior_year_quarter(self):
        period, reason = bp.find_yoy_comparison_period(
            "2026-Q1", ["2025-Q1", "2025-Q4", "2026-Q1"], as_of_date=self.AS_OF
        )
        self.assertEqual(period, "2025-Q1")
        self.assertIsNone(reason)

    def test_matches_prior_fiscal_year_for_year_type_periods(self):
        period, reason = bp.find_yoy_comparison_period("2026", ["2025", "2024"], as_of_date=self.AS_OF)
        self.assertEqual(period, "2025")
        self.assertIsNone(reason)

    def test_no_candidate_within_tolerance_returns_explicit_reason(self):
        period, reason = bp.find_yoy_comparison_period(
            "2026-Q1", ["2026-Q2", "2026-Q3", "2026-Q4"], as_of_date=self.AS_OF
        )
        self.assertIsNone(period)
        self.assertEqual(reason, "no_period_within_12_month_tolerance")

    def test_never_crosses_quarter_and_year_period_types(self):
        period, reason = bp.find_yoy_comparison_period("2026-Q1", ["2025"], as_of_date=self.AS_OF)
        self.assertIsNone(period)
        self.assertEqual(reason, "no_period_within_12_month_tolerance")

    def test_ctd_style_fiscal_mismatch_candidate_not_yet_calendar_verified_is_rejected(self):
        """Mã năm tài chính lệch (CTD/HSG... theo VNSTOCK_GUIDE.md muc 6.2) có thể có dòng dữ
        liệu dưới nhãn kỳ mà, tính THEO LỊCH DƯƠNG thuần túy, chưa tới ngày kết thúc — một dict
        lookup nhãn thuần (get_yoy_period_str cũ) sẽ dùng ngay không kiểm tra; hàm mới phải từ
        chối và nêu lý do rõ thay vì trả một con số YoY dựa trên kỳ chưa xác minh."""
        period, reason = bp.find_yoy_comparison_period(
            "2026-Q1", ["2025-Q1"], as_of_date="2025-03-01",  # trước 2025-03-31 (kết thúc 2025-Q1)
        )
        self.assertIsNone(period)
        self.assertEqual(reason, "comparable_period_not_calendar_verified")

    def test_unparseable_current_period_returns_explicit_reason(self):
        period, reason = bp.find_yoy_comparison_period("weird-label", ["2025-Q1"], as_of_date=self.AS_OF)
        self.assertIsNone(period)
        self.assertEqual(reason, "current_period_calendar_end_unparseable")


class ProcessDataYoyGrowthIntegrationTests(unittest.TestCase):
    """Kiểm tra end-to-end trên dữ liệu BCTC thật (không fixture) rằng process_data() gắn đủ
    status/reason cho revenue_growth_yoy/profit_growth_yoy thay vì NaN trần."""

    @classmethod
    def setUpClass(cls):
        cls.result = bp.process_data(tickers_filter=["PAN", "HPG"])

    def test_growth_status_and_reason_columns_exist(self):
        for column in (
            "revenue_growth_yoy_status", "revenue_growth_yoy_reason", "revenue_growth_yoy_comparison_period",
            "profit_growth_yoy_status", "profit_growth_yoy_reason", "profit_growth_yoy_comparison_period",
        ):
            self.assertIn(column, self.result.columns)

    def test_no_growth_status_is_null(self):
        # Mọi dòng phải có status rõ ràng — không được để trống ngay cả khi giá trị NaN.
        self.assertFalse(self.result["revenue_growth_yoy_status"].isna().any())
        self.assertFalse(self.result["profit_growth_yoy_status"].isna().any())

    def test_derived_status_implies_non_null_value_and_reason_is_null(self):
        derived = self.result[self.result["revenue_growth_yoy_status"] == "derived"]
        if len(derived):
            self.assertTrue(derived["revenue_growth_yoy"].notna().all())
            self.assertTrue(derived["revenue_growth_yoy_reason"].isna().all())
            self.assertTrue(derived["revenue_growth_yoy_comparison_period"].notna().all())

    def test_missing_status_implies_reason_present(self):
        missing = self.result[self.result["revenue_growth_yoy_status"] != "derived"]
        if len(missing):
            self.assertTrue(missing["revenue_growth_yoy"].isna().all())
            self.assertTrue(missing["revenue_growth_yoy_reason"].notna().all())


if __name__ == "__main__":
    unittest.main()
