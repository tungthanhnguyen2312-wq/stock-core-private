# ==========================================================================
# TEST cho watchlist_eval.py (mục 7, nâng cấp workflow 2026-07-17 chiều — bỏ Gemini).
# Trọng tâm: KHÔNG LOOK-AHEAD phải đúng ở biên (chưa đủ phiên tương lai -> None, không suy đoán;
# mã ngừng giao dịch đúng ngày mục tiêu -> None, không forward-fill giá gần nhất).
#
# Dùng DB sqlite trong bộ nhớ dựng tay (không phải vn_stock.db thật) để mọi con số kỳ vọng tính
# được chính xác bằng tay — xem bảng giá dựng sẵn ngay dưới đây.
# ==========================================================================

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import watchlist_eval as we  # noqa: E402

# Lịch 10 phiên D1..D10 (chuỗi ngày bất kỳ, chỉ cần tăng dần — không cần là ngày thật).
CALENDAR = [f"2026-01-{d:02d}" for d in range(1, 11)]
D1, D4, D9 = CALENDAR[0], CALENDAR[3], CALENDAR[8]

# VNINDEX trải đủ 10 phiên. ABC chỉ giao dịch D1..D7 rồi NGỪNG (mô phỏng đình chỉ/hủy niêm yết) —
# dùng để kiểm tra "không forward-fill" khi ngày mục tiêu đã qua nhưng mã không có nến đúng ngày đó.
# DEF giao dịch đủ 10 phiên — trường hợp "đánh giá được" bình thường.
VNINDEX_CLOSES = dict(zip(CALENDAR, [1000, 1010, 1005, 1020, 1015, 1030, 1025, 1040, 1050, 1045]))
ABC_CLOSES = dict(zip(CALENDAR[:7], [100, 101, 99, 105, 103, 104, 106]))
DEF_CLOSES = dict(zip(CALENDAR, [50, 51, 49, 53, 54, 55, 56, 57, 58, 59]))


def _build_memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, "
                "close REAL, volume REAL)")
    rows = []
    for series, closes in (("VNINDEX", VNINDEX_CLOSES), ("ABC", ABC_CLOSES), ("DEF", DEF_CLOSES)):
        for d, c in closes.items():
            rows.append((series, d, c, c, c, c, 1000))
    conn.executemany("INSERT INTO ohlcv VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


class NSessionsAfterTests(unittest.TestCase):
    def test_returns_nth_trading_date_after_start(self):
        self.assertEqual(we.n_sessions_after(CALENDAR, D1, 3), D4)

    def test_returns_none_when_not_enough_future_sessions_exist(self):
        # 15 phiên sau D1 vượt quá độ dài lịch 10 phiên -> chưa đủ dữ liệu, PHẢI là None,
        # tuyệt đối không ngoại suy/suy đoán một ngày trong tương lai không có trong lịch.
        self.assertIsNone(we.n_sessions_after(CALENDAR, D1, 15))

    def test_boundary_exact_end_of_calendar_is_evaluable(self):
        # phiên thứ 9 sau D1 = D10 (chỉ số cuối cùng) -> vẫn PHẢI trả về, không lùi 1 để "cho an toàn".
        self.assertEqual(we.n_sessions_after(CALENDAR, D1, 9), CALENDAR[9])

    def test_one_past_end_of_calendar_returns_none(self):
        self.assertIsNone(we.n_sessions_after(CALENDAR, D1, 10))


class EvaluateNoLookaheadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = _build_memory_db()
        history = pd.DataFrame([
            {"session_date": D1, "ticker": "ABC", "score": 75.0, "fundamental": 70, "technical": 80,
             "momentum": 70, "liquidity": 90, "macro": 60, "risk": 80, "close": 100.0, "strategies": "momentum"},
            {"session_date": D1, "ticker": "DEF", "score": 65.0, "fundamental": 60, "technical": 70,
             "momentum": 60, "liquidity": 80, "macro": 50, "risk": 70, "close": 50.0, "strategies": "rs, sector"},
        ])
        cls.result = we.evaluate(history, cls.conn, horizons=(3, 8, 15))

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def _row(self, ticker):
        return self.result[self.result["ticker"] == ticker].iloc[0]

    def test_evaluable_horizon_computes_correct_forward_and_excess_return(self):
        # ABC T+3 -> ngày mục tiêu D4: ABC 100->105 (+5.0%), VNINDEX 1000->1020 (+2.0%) -> excess +3.0
        row = self._row("ABC")
        self.assertTrue(row["evaluable_t3"])
        self.assertAlmostEqual(row["fwd_return_t3_pct"], 5.0, places=6)
        self.assertAlmostEqual(row["vnindex_return_t3_pct"], 2.0, places=6)
        self.assertAlmostEqual(row["excess_return_t3_pct"], 3.0, places=6)
        self.assertEqual(row["target_date_t3"], D4)

    def test_delisted_ticker_missing_target_date_is_none_not_forward_filled(self):
        # ABC T+8 -> ngày mục tiêu D9 tồn tại trong lịch VNINDEX nhưng ABC đã ngừng GD từ sau D7 ->
        # PHẢI là None (không lấy giá D7 gần nhất thay thế -> đó là forward-fill nhìn trước trá hình).
        row = self._row("ABC")
        self.assertEqual(row["target_date_t8"], D9)   # lịch chuẩn (VNINDEX) VẪN có ngày này
        self.assertFalse(row["evaluable_t8"])
        # None trong DataFrame numeric column pandas tự chuyển thành NaN — dùng pd.isna() thay vì
        # assertIsNone (không phải bug: NaN/None đều nghĩa "không đánh giá được" ở đây).
        self.assertTrue(pd.isna(row["fwd_return_t8_pct"]))
        self.assertTrue(pd.isna(row["excess_return_t8_pct"]))

    def test_horizon_beyond_calendar_length_is_none_for_every_ticker(self):
        for tk in ("ABC", "DEF"):
            row = self._row(tk)
            self.assertIsNone(row["target_date_t15"])
            self.assertFalse(row["evaluable_t15"])

    def test_fully_covered_ticker_is_evaluable_at_every_horizon_within_calendar(self):
        # DEF T+8 -> ngày mục tiêu thứ 8 sau D1 = D9 (index 8, 0-based) -> DEF close tại D9 = 58.
        row = self._row("DEF")
        self.assertTrue(row["evaluable_t3"])
        self.assertTrue(row["evaluable_t8"])
        self.assertEqual(row["target_date_t8"], D9)
        self.assertAlmostEqual(row["fwd_return_t8_pct"], (58.0 / 50.0 - 1) * 100, places=6)


class ScoreBucketTests(unittest.TestCase):
    def test_buckets_are_contiguous_and_correct(self):
        self.assertEqual(we.score_bucket(35), "<40")
        self.assertEqual(we.score_bucket(40), "40-50")
        self.assertEqual(we.score_bucket(59.9), "50-60")
        self.assertEqual(we.score_bucket(100), "80-100")

    def test_none_and_nan_return_none(self):
        self.assertIsNone(we.score_bucket(None))
        self.assertIsNone(we.score_bucket(float("nan")))


if __name__ == "__main__":
    unittest.main()
