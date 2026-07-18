import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from candlestick_patterns import (
    PATTERN_REGISTRY,
    TIMEFRAMES,
    atomic_write_snapshot,
    build_snapshot,
    detect_patterns,
    resample_ohlcv,
    sanitize_json,
)


def bars(rows, start="2026-01-02"):
    return pd.DataFrame(
        [{"date": date, "open": o, "high": h, "low": l, "close": c, "volume": v}
         for date, (o, h, l, c, v) in zip(pd.bdate_range(start, periods=len(rows)), rows)]
    )


def down_prefix():
    return [(15.1, 15.3, 14.7, 15.0, 1000), (14.1, 14.3, 13.7, 14.0, 1000),
            (13.1, 13.3, 12.7, 13.0, 1000), (12.1, 12.3, 11.7, 12.0, 1000),
            (11.1, 11.3, 10.7, 11.0, 1000), (10.1, 10.3, 9.7, 10.0, 1000)]


def up_prefix():
    return [(9.9, 10.3, 9.7, 10.0, 1000), (10.9, 11.3, 10.7, 11.0, 1000),
            (11.9, 12.3, 11.7, 12.0, 1000), (12.9, 13.3, 12.7, 13.0, 1000),
            (13.9, 14.3, 13.7, 14.0, 1000), (14.9, 15.3, 14.7, 15.0, 1000)]


def detected(key, rows):
    _, matrix = detect_patterns(bars(rows))
    return bool(matrix[key].iloc[-1])


class ImportantPatternTests(unittest.TestCase):
    def assert_pattern(self, key, positive, negative):
        self.assertTrue(detected(key, positive), key)
        self.assertFalse(detected(key, negative), key + " negative")

    def test_bullish_engulfing(self):
        positive = down_prefix() + [(10.2, 10.3, 9.3, 9.5, 1000), (9.4, 10.5, 9.2, 10.4, 1600)]
        negative = positive[:-1] + [(9.6, 10.1, 9.4, 10.0, 1600)]
        self.assert_pattern("bullish_engulfing", positive, negative)

    def test_bearish_engulfing(self):
        positive = up_prefix() + [(14.8, 15.7, 14.7, 15.5, 1000), (15.6, 15.8, 14.5, 14.6, 1600)]
        negative = positive[:-1] + [(15.4, 15.6, 14.9, 15.0, 1600)]
        self.assert_pattern("bearish_engulfing", positive, negative)

    def test_hammer(self):
        positive = down_prefix() + [(10.1, 10.2, 8.8, 9.9, 1400)]
        negative = down_prefix() + [(9.8, 10.3, 9.4, 10.1, 1400)]
        self.assert_pattern("hammer", positive, negative)

    def test_hanging_man(self):
        positive = up_prefix() + [(15.1, 15.2, 13.8, 14.9, 1400)]
        negative = down_prefix() + [(10.1, 10.2, 8.8, 9.9, 1400)]
        self.assert_pattern("hanging_man", positive, negative)

    def test_shooting_star(self):
        positive = up_prefix() + [(14.9, 16.2, 14.8, 15.1, 1400)]
        negative = up_prefix() + [(14.9, 15.5, 14.6, 15.2, 1400)]
        self.assert_pattern("shooting_star", positive, negative)

    def test_bullish_harami(self):
        positive = down_prefix() + [(10.2, 10.3, 8.8, 9.0, 1000), (9.3, 9.9, 9.2, 9.8, 1300)]
        negative = positive[:-1] + [(8.8, 10.4, 8.7, 10.3, 1300)]
        self.assert_pattern("bullish_harami", positive, negative)

    def test_bearish_harami(self):
        positive = up_prefix() + [(14.8, 16.2, 14.7, 16.0, 1000), (15.7, 15.8, 15.1, 15.2, 1300)]
        negative = positive[:-1] + [(16.2, 16.3, 14.6, 14.7, 1300)]
        self.assert_pattern("bearish_harami", positive, negative)

    def test_morning_star(self):
        positive = down_prefix() + [(10.2, 10.3, 8.7, 9.0, 1000), (9.05, 9.3, 8.9, 9.15, 800), (9.2, 10.1, 9.1, 9.9, 1600)]
        negative = positive[:-1] + [(9.2, 9.6, 9.1, 9.5, 1600)]
        self.assert_pattern("morning_star", positive, negative)

    def test_evening_star(self):
        positive = up_prefix() + [(14.8, 16.3, 14.7, 16.0, 1000), (15.9, 16.2, 15.8, 16.0, 800), (15.9, 16.0, 14.9, 15.1, 1600)]
        negative = positive[:-1] + [(15.9, 16.0, 15.4, 15.5, 1600)]
        self.assert_pattern("evening_star", positive, negative)

    def test_doji(self):
        self.assert_pattern("doji", down_prefix() + [(10.0, 11.0, 9.0, 10.05, 1000)],
                            down_prefix() + [(10.0, 11.0, 9.0, 10.5, 1000)])

    def test_dragonfly_doji(self):
        self.assert_pattern("dragonfly_doji", down_prefix() + [(10.0, 10.1, 8.5, 10.02, 1000)],
                            down_prefix() + [(10.0, 10.5, 8.5, 10.02, 1000)])

    def test_gravestone_doji(self):
        self.assert_pattern("gravestone_doji", up_prefix() + [(15.0, 16.5, 14.9, 14.98, 1000)],
                            up_prefix() + [(15.0, 16.5, 14.5, 14.98, 1000)])

    def test_three_white_soldiers(self):
        positive = down_prefix() + [(9.7, 10.5, 9.6, 10.4, 1200), (10.1, 11.0, 10.0, 10.9, 1300), (10.6, 11.6, 10.5, 11.5, 1500)]
        negative = positive[:-1] + [(10.6, 11.2, 10.4, 10.8, 1500)]
        self.assert_pattern("three_white_soldiers", positive, negative)

    def test_three_black_crows(self):
        positive = up_prefix() + [(15.3, 15.4, 14.5, 14.6, 1200), (14.9, 15.0, 14.0, 14.1, 1300), (14.4, 14.5, 13.4, 13.5, 1500)]
        negative = positive[:-1] + [(14.4, 14.8, 14.0, 14.6, 1500)]
        self.assert_pattern("three_black_crows", positive, negative)

    def test_rising_three_methods(self):
        prefix = down_prefix()
        positive = prefix + [(10.0, 12.2, 9.9, 12.0, 1800), (11.8, 11.9, 11.0, 11.2, 700),
                             (11.3, 11.6, 10.8, 11.0, 700), (11.1, 11.5, 10.7, 11.3, 700),
                             (11.4, 12.8, 11.3, 12.6, 1900)]
        negative = positive[:-1] + [(11.4, 12.1, 11.3, 12.0, 1900)]
        self.assert_pattern("rising_three_methods", positive, negative)

    def test_falling_three_methods(self):
        prefix = up_prefix()
        positive = prefix + [(15.0, 15.1, 12.8, 13.0, 1800), (13.2, 14.0, 13.1, 13.8, 700),
                             (13.7, 14.2, 13.3, 13.9, 700), (13.8, 14.3, 13.4, 14.0, 700),
                             (13.7, 13.8, 12.2, 12.4, 1900)]
        negative = positive[:-1] + [(13.7, 13.8, 12.9, 13.0, 1900)]
        self.assert_pattern("falling_three_methods", positive, negative)

    def test_inside_bar(self):
        positive = down_prefix() + [(10.0, 11.0, 9.0, 9.5, 1000), (9.6, 10.5, 9.2, 10.0, 1000)]
        negative = positive[:-1] + [(9.6, 11.2, 9.2, 10.0, 1000)]
        self.assert_pattern("inside_bar", positive, negative)

    def test_missing_and_zero_range_never_raise_or_false_match(self):
        frame = bars(down_prefix() + [(10, 10, 10, 10, 0), (10, 11, 9, 10, 1000)])
        frame.loc[2, "close"] = np.nan
        features, matrix = detect_patterns(frame)
        self.assertFalse(bool(matrix.iloc[-2].any()))
        self.assertFalse(np.isinf(features.select_dtypes(include="number")).any().any())

    def test_tweezer_tolerance_scales_with_price(self):
        close = down_prefix() + [(10.2, 10.3, 9.001, 9.4, 1000), (9.3, 10.0, 9.010, 9.8, 1200)]
        far = close[:-1] + [(9.3, 10.0, 9.20, 9.8, 1200)]
        self.assertTrue(detected("tweezer_bottom", close))
        self.assertFalse(detected("tweezer_bottom", far))


class ResampleAndOutputTests(unittest.TestCase):
    def setUp(self):
        self.daily = pd.DataFrame({
            "date": pd.to_datetime(["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02", "2026-07-06", "2026-07-08"]),
            "open": [10, 11, 12, 13, 14, 15], "high": [12, 13, 14, 15, 16, 17],
            "low": [9, 10, 11, 12, 13, 14], "close": [11, 12, 13, 14, 15, 16],
            "volume": [100, 200, 300, 400, 0, 600],
        })

    def test_week_resample_holiday_and_ohlcv_rules(self):
        weekly = resample_ohlcv(self.daily, "1W", datetime(2026, 7, 8, 10, 0))
        first = weekly.iloc[0]
        self.assertEqual(first.open, 10)
        self.assertEqual(first.high, 15)
        self.assertEqual(first.low, 9)
        self.assertEqual(first.close, 14)
        self.assertEqual(first.volume, 1000)
        self.assertTrue(bool(first.is_complete))
        self.assertFalse(bool(weekly.iloc[-1].is_complete))

    def test_month_resample_and_incomplete_month(self):
        monthly = resample_ohlcv(self.daily, "1M", datetime(2026, 7, 14, 16, 0))
        self.assertEqual(monthly.iloc[0].open, 10)
        self.assertEqual(monthly.iloc[0].close, 12)
        self.assertEqual(monthly.iloc[0].volume, 300)
        self.assertTrue(bool(monthly.iloc[0].is_complete))
        self.assertFalse(bool(monthly.iloc[-1].is_complete))
        completed = resample_ohlcv(self.daily, "1M", datetime(2026, 8, 1, 9, 0))
        self.assertTrue(bool(completed.iloc[-1].is_complete))

    def test_duplicate_unsorted_and_null_volume(self):
        duplicate = pd.concat([self.daily.iloc[::-1], self.daily.iloc[[0]]], ignore_index=True)
        duplicate["volume"] = duplicate["volume"].astype(float)
        duplicate.loc[:, "volume"] = np.nan
        weekly = resample_ohlcv(duplicate, "1W", datetime(2026, 8, 1))
        self.assertEqual(len(weekly), 2)
        self.assertTrue(pd.isna(weekly.iloc[0].volume))

    def test_daily_is_always_completed(self):
        daily = resample_ohlcv(self.daily, "1D", datetime(2026, 7, 8, 10, 0))
        self.assertTrue(daily.is_complete.all())

    def test_snapshot_schema_scores_and_serialization(self):
        raw = bars(down_prefix() + [(10.2, 10.3, 9.3, 9.5, 1000), (9.4, 10.5, 9.2, 10.4, 1600)])
        raw.insert(0, "ticker", "TST")
        snapshot = build_snapshot(raw, scan_date="2026-01-13", generated_at=datetime(2026, 2, 1), min_confidence=0)
        self.assertEqual(snapshot["timeframes"], list(TIMEFRAMES))
        self.assertTrue(snapshot["patterns"])
        for row in snapshot["patterns"]:
            self.assertIn(row["timeframe"], TIMEFRAMES)
            self.assertGreaterEqual(row["bars_ago"], 0)
            self.assertGreaterEqual(row["confidence_score"], 0)
            self.assertLessEqual(row["confidence_score"], 100)
            self.assertIn(row["confidence_stars"], range(4))
        json.dumps(snapshot, allow_nan=False)

    def test_stale_ticker_is_kept_but_warned(self):
        raw = bars(down_prefix() + [(10.2, 10.3, 9.3, 9.5, 1000), (9.4, 10.5, 9.2, 10.4, 1600)])
        raw.insert(0, "ticker", "OLD")
        snapshot = build_snapshot(raw, scan_date="2026-02-20", generated_at=datetime(2026, 2, 20), min_confidence=0)
        self.assertTrue(snapshot["patterns"])
        self.assertTrue(all("stale_ticker_data" in row["warnings"] for row in snapshot["patterns"]))

    def test_sanitize_and_atomic_json_js_use_same_payload(self):
        payload = sanitize_json({"ok": 1, "nan": np.nan, "inf": np.inf})
        self.assertIsNone(payload["nan"])
        self.assertIsNone(payload["inf"])
        with tempfile.TemporaryDirectory() as directory:
            json_path, js_path = Path(directory) / "x.json", Path(directory) / "x.js"
            atomic_write_snapshot(payload, json_path, js_path)
            parsed = json.loads(json_path.read_text(encoding="utf-8"))
            script = js_path.read_text(encoding="utf-8")
            self.assertEqual(parsed, payload)
            self.assertIn(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), script)

    def test_registry_has_docstrings_and_required_patterns(self):
        required = {"bullish_engulfing", "bearish_engulfing", "hammer", "hanging_man", "shooting_star",
                    "bullish_harami", "bearish_harami", "morning_star", "evening_star", "doji",
                    "dragonfly_doji", "gravestone_doji", "three_white_soldiers", "three_black_crows",
                    "rising_three_methods", "falling_three_methods", "inside_bar"}
        self.assertTrue(required.issubset(PATTERN_REGISTRY))
        self.assertGreaterEqual(len(PATTERN_REGISTRY), 20)


if __name__ == "__main__":
    unittest.main()
