# ==========================================================================
# TEST cho "đóng dữ liệu cuối" 2026-07-17 tối, mục 1-2: một file BCTC hỏng schema (thiếu cột
# kỳ/giá trị — trường hợp thật: data_bctc/BIO_balance_sheet.csv, xem diagnostic
# reports/bctc_quarantine_latest.json) KHÔNG được chặn xử lý các ticker hợp lệ khác.
#
# Test tích hợp trên DỮ LIỆU THẬT của repo (BIO là ví dụ có sẵn, tự nhiên, không cần fixture bịa)
# — cùng phong cách test_financial_mapping.py/test_snapshot_rebuild.py: gọi process_data() trực
# tiếp, không qua subprocess, không ghi đè financial_snapshot.csv/parquet thật (chỉ nhận về
# DataFrame trong bộ nhớ).
# ==========================================================================

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bctc_processor as processor  # noqa: E402
from source_schema_guards import SourceSchemaError  # noqa: E402

KNOWN_BAD_TICKER = "BIO"   # thiếu cột kỳ/giá trị ở CẢ HAI file balance_sheet — xem mục 1 báo cáo
KNOWN_GOOD_TICKER = "HPG"


def _bio_source_exists() -> bool:
    return (ROOT / "data_bctc" / "BIO_balance_sheet.csv").exists()


@unittest.skipUnless(_bio_source_exists(), "data_bctc/BIO_balance_sheet.csv không có trên máy này")
class SchemaErrorIsolationTests(unittest.TestCase):
    """process_data(schema_error_policy='quarantine') phải cô lập BIO mà không chặn HPG."""

    @classmethod
    def setUpClass(cls):
        cls.diagnostics: list[dict[str, object]] = []
        cls.result = processor.process_data(
            tickers_filter=[KNOWN_BAD_TICKER, KNOWN_GOOD_TICKER],
            schema_error_policy="quarantine",
            source_diagnostics=cls.diagnostics,
        )

    def test_bad_ticker_is_recorded_in_diagnostics_not_silently_dropped(self):
        tickers_quarantined = {item["ticker"] for item in self.diagnostics}
        self.assertIn(KNOWN_BAD_TICKER, tickers_quarantined)
        entry = next(item for item in self.diagnostics if item["ticker"] == KNOWN_BAD_TICKER)
        self.assertEqual(entry["reason"], "source_schema_mismatch")
        self.assertIn("period/value", entry["missing_fields"])

    def test_bad_ticker_produces_no_fabricated_rows(self):
        # Không được có bất kỳ dòng nào của BIO trong kết quả — không bịa số thay chỗ thiếu.
        self.assertNotIn(KNOWN_BAD_TICKER, set(self.result.get("ticker", [])))

    def test_good_ticker_is_still_processed_despite_bad_ticker_in_same_run(self):
        self.assertIn(KNOWN_GOOD_TICKER, set(self.result["ticker"]))
        hpg_rows = self.result[self.result["ticker"] == KNOWN_GOOD_TICKER]
        self.assertGreater(len(hpg_rows), 0)
        # Dữ liệu HPG phải là dữ liệu thật (có revenue một vài kỳ), không phải khung rỗng.
        self.assertTrue(hpg_rows["revenue"].notna().any())

    def test_result_is_not_empty_overall(self):
        self.assertFalse(self.result.empty)


@unittest.skipUnless(_bio_source_exists(), "data_bctc/BIO_balance_sheet.csv không có trên máy này")
class StrictModeStillRaisesTests(unittest.TestCase):
    """Đối chứng: chính sách mặc định của process_data() ('raise') KHÔNG đổi hành vi cũ — chỉ
    main() (CLI) đổi mặc định sang quarantine. Test này giữ nguyên bất biến API của process_data()."""

    def test_raise_policy_propagates_schema_error_for_bad_ticker(self):
        with self.assertRaises(SourceSchemaError) as ctx:
            processor.process_data(
                tickers_filter=[KNOWN_BAD_TICKER], schema_error_policy="raise")
        self.assertIn("period/value", ctx.exception.missing_fields)

    def test_default_policy_is_still_raise_when_unspecified(self):
        # Bất biến quan trọng: KHÔNG đổi default của process_data() (chỉ đổi ở main()) — mọi
        # consumer khác (test_financial_mapping.py, test_snapshot_rebuild.py, snapshot_rebuild.py
        # khi reuse_next=False không truyền policy...) không bị đổi hành vi ngầm.
        with self.assertRaises(SourceSchemaError):
            processor.process_data(tickers_filter=[KNOWN_BAD_TICKER])


class InvalidPolicyValueTests(unittest.TestCase):
    def test_unknown_policy_value_rejected(self):
        with self.assertRaises(ValueError):
            processor.process_data(tickers_filter=["HPG"], schema_error_policy="ignore")


if __name__ == "__main__":
    unittest.main()
