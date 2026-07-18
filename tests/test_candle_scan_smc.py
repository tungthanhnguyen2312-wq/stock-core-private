# ==========================================================================
# TEST cho nâng cấp workflow 2026-07-17 chiều (bỏ Gemini), mục 5: candle_scan.py:smc_one() phải
# trả biên giá + NGÀY hình thành cho FVG/Order Block, danh sách swing high/low, vùng hỗ trợ/kháng
# cự gần nhất kèm reaction_count, và volume confirmation — thay vì chỉ 1 nhãn chuỗi rỗng nghĩa như
# bản gốc. Không được tự bịa vùng khi không có swing nào xác nhận được (insufficient_data).
#
# Dùng mảng OHLCV DỰNG TAY (không phải dữ liệu thật) để kết quả xác định được chính xác bằng tay —
# xem chú thích tính tay ngay trong docstring từng test.
# ==========================================================================

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import candle_scan as cs  # noqa: E402


# 9 nến dựng tay: đúng 1 swing high (index 2, giá 108) và 1 swing low (index 5, giá 98) theo
# fractal n=2; đúng 1 FVG bull hình thành tại index 7 (vùng 103-105, chưa bị lấp bởi nến sau đó);
# không có OB (đã tính tay: BOS đầu tiên có thể xảy ra không thỏa điều kiện close > swing level ở
# mọi i trong cửa sổ này) — xem tính tay chi tiết trong PR/commit thêm test này.
OPEN = np.array([97, 99, 104, 103, 101, 100, 102, 106, 107], dtype=float)
HIGH = np.array([100, 102, 108, 106, 104, 103, 105, 110, 109], dtype=float)
LOW = np.array([95, 97, 103, 101, 99, 98, 100, 105, 104], dtype=float)
CLOSE = np.array([99, 101, 106, 102, 100, 101, 104, 108, 108], dtype=float)
DATES = np.array([f"2026-01-{d:02d}" for d in range(1, 10)])
VOLUME_FLAT = np.full(9, 1000.0)
VOLUME_SPIKE_AT_7 = VOLUME_FLAT.copy()
VOLUME_SPIKE_AT_7[7] = 5000.0   # >= 1.5x mean (~1444) -> volume_confirmed=True chỉ tại index 7

# Chuỗi TĂNG ĐƠN ĐIỆU: max/min của mọi cửa sổ 5 nến luôn nằm ở đầu mút, không có tâm nào là
# đỉnh/đáy cục bộ -> KHÔNG có swing nào được xác nhận (n=2 fractal, center=True).
MONOTONIC_HIGH = np.arange(100, 109, dtype=float)
MONOTONIC_LOW = np.arange(95, 104, dtype=float)
MONOTONIC_OPEN = MONOTONIC_LOW + 1
MONOTONIC_CLOSE = MONOTONIC_HIGH - 1


class SwingDetectionTests(unittest.TestCase):
    def test_finds_exactly_one_swing_high_and_low_with_correct_date_and_price(self):
        r = cs.smc_one(OPEN, HIGH, LOW, CLOSE, atr14=10.0, dates=DATES, volume=VOLUME_FLAT)
        self.assertEqual(len(r["swing_highs"]), 1)
        self.assertEqual(r["swing_highs"][0]["index"], 2)
        self.assertEqual(r["swing_highs"][0]["price"], 108.0)
        self.assertEqual(r["swing_highs"][0]["date"], "2026-01-03")
        self.assertEqual(len(r["swing_lows"]), 1)
        self.assertEqual(r["swing_lows"][0]["index"], 5)
        self.assertEqual(r["swing_lows"][0]["price"], 98.0)
        self.assertEqual(r["swing_lows"][0]["date"], "2026-01-06")

    def test_monotonic_series_has_no_swings_and_is_flagged_insufficient(self):
        r = cs.smc_one(MONOTONIC_OPEN, MONOTONIC_HIGH, MONOTONIC_LOW, MONOTONIC_CLOSE,
                       atr14=1.0, dates=DATES, volume=VOLUME_FLAT)
        self.assertEqual(r["swing_highs"], [])
        self.assertEqual(r["swing_lows"], [])
        self.assertTrue(r["insufficient_data"])
        self.assertIsNotNone(r["insufficient_reason"])
        # Không tự bịa vùng hỗ trợ/kháng cự khi thiếu swing xác nhận.
        self.assertIsNone(r["nearest_support"])
        self.assertIsNone(r["nearest_resistance"])


class FvgOrderBlockBoundaryTests(unittest.TestCase):
    """Mục 5 cốt lõi: FVG phải có biên [low, high] + ngày hình thành — không chỉ nhãn chuỗi."""

    def test_fvg_bull_has_boundaries_and_formation_date(self):
        r = cs.smc_one(OPEN, HIGH, LOW, CLOSE, atr14=10.0, dates=DATES, volume=VOLUME_FLAT)
        self.assertIsNotNone(r["fvg_bull"])
        self.assertEqual(r["fvg_bull"]["low"], 103.0)
        self.assertEqual(r["fvg_bull"]["high"], 105.0)
        self.assertEqual(r["fvg_bull"]["formed_date"], "2026-01-08")   # index 7 -> ngày thứ 8
        self.assertEqual(r["fvg_bull"]["formed_index"], 7)
        self.assertIsNone(r["fvg_bear"])

    def test_no_order_block_found_returns_none_not_fabricated(self):
        r = cs.smc_one(OPEN, HIGH, LOW, CLOSE, atr14=10.0, dates=DATES, volume=VOLUME_FLAT)
        self.assertIsNone(r["ob_bull"])
        self.assertIsNone(r["ob_bear"])

    def test_tags_list_still_flat_strings_for_backward_compatibility(self):
        """today['smc'] trong candle_scan.py vẫn cần list chuỗi phẳng — không phá tương thích."""
        r = cs.smc_one(OPEN, HIGH, LOW, CLOSE, atr14=10.0, dates=DATES, volume=VOLUME_FLAT)
        self.assertIsInstance(r["tags"], list)
        self.assertTrue(all(isinstance(t, str) for t in r["tags"]))
        self.assertIn("fvg_bull", r["tags"])   # close cuối (108) cách mép FVG 3 <= atr14 (10)


class VolumeConfirmationTests(unittest.TestCase):
    def test_volume_confirmed_true_only_at_spike_bar(self):
        r = cs.smc_one(OPEN, HIGH, LOW, CLOSE, atr14=10.0, dates=DATES, volume=VOLUME_SPIKE_AT_7)
        self.assertTrue(r["fvg_bull"]["volume_confirmed"])       # hình thành đúng tại index 7 (spike)
        self.assertFalse(r["swing_highs"][0]["volume_confirmed"])  # index 2, volume thường
        self.assertFalse(r["swing_lows"][0]["volume_confirmed"])   # index 5, volume thường

    def test_volume_confirmation_is_none_when_volume_not_provided(self):
        r = cs.smc_one(OPEN, HIGH, LOW, CLOSE, atr14=10.0, dates=DATES, volume=None)
        self.assertIsNone(r["fvg_bull"]["volume_confirmed"])


class NearestSupportResistanceTests(unittest.TestCase):
    def test_reaction_count_and_price_for_single_swing_each_side(self):
        r = cs.smc_one(OPEN, HIGH, LOW, CLOSE, atr14=10.0, dates=DATES, volume=VOLUME_FLAT)
        self.assertEqual(r["nearest_support"]["price"], 98.0)
        self.assertEqual(r["nearest_support"]["reaction_count"], 1)
        self.assertEqual(r["nearest_resistance"]["price"], 108.0)
        self.assertEqual(r["nearest_resistance"]["reaction_count"], 1)


if __name__ == "__main__":
    unittest.main()
