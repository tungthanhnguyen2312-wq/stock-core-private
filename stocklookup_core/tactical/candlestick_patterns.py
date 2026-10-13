"""Multi-timeframe candlestick pattern engine for local OHLCV data.

The module deliberately uses only pandas/NumPy.  Every detector is evaluated
with information available at the candidate bar; rolling features are shifted
where they describe the preceding trend, so scanning historical bars does not
introduce look-ahead bias.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass, asdict
from datetime import datetime, time
from pathlib import Path
from typing import Callable, Iterable, Mapping

import numpy as np
import pandas as pd


TIMEFRAMES = ("1D", "1W", "1M")
LOOKBACKS = {"1D": 90, "1W": 78, "1M": 36}
MIN_LIQUIDITY_TY = 3.0
EPSILON = 1e-12


@dataclass(frozen=True)
class PatternMeta:
    key: str
    name: str
    name_vi: str
    direction: str
    category: str
    bars: int
    prior_trend: str | None
    description: str


Detector = Callable[[pd.DataFrame], pd.Series]


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide without creating infinity; zero denominators become NaN."""
    return numerator.div(denominator.where(denominator.abs() > EPSILON))


def real_body(df: pd.DataFrame) -> pd.Series:
    return (df["close"] - df["open"]).abs()


def candle_range(df: pd.DataFrame) -> pd.Series:
    return (df["high"] - df["low"]).clip(lower=0)


def upper_shadow(df: pd.DataFrame) -> pd.Series:
    return (df["high"] - df[["open", "close"]].max(axis=1)).clip(lower=0)


def lower_shadow(df: pd.DataFrame) -> pd.Series:
    return (df[["open", "close"]].min(axis=1) - df["low"]).clip(lower=0)


def body_ratio(df: pd.DataFrame) -> pd.Series:
    return safe_divide(real_body(df), candle_range(df))


def is_bullish(df: pd.DataFrame) -> pd.Series:
    return df["close"] > df["open"]


def is_bearish(df: pd.DataFrame) -> pd.Series:
    return df["close"] < df["open"]


def is_doji(df: pd.DataFrame, maximum_body_ratio: float = 0.10) -> pd.Series:
    return (body_ratio(df) <= maximum_body_ratio).fillna(False)


def average_true_range(df: pd.DataFrame, window: int = 14) -> pd.Series:
    previous_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window, min_periods=max(3, window // 3)).mean()


def average_volume(df: pd.DataFrame, window: int = 20) -> pd.Series:
    return df["volume"].rolling(window, min_periods=3).mean()


def price_tolerance(df: pd.DataFrame) -> pd.Series:
    """Adaptive tolerance: max(5% ATR, 0.15% price), never absolute-price based."""
    atr = df.get("atr14", average_true_range(df))
    return pd.concat([atr * 0.05, df["close"].abs() * 0.0015], axis=1).max(axis=1)


def rolling_trend(df: pd.DataFrame, periods: int = 5) -> tuple[pd.Series, pd.Series]:
    """Return down/up context ending one bar before the candidate bar."""
    prior = df["close"].shift(1)
    anchor = df["close"].shift(periods + 1)
    down = (prior < anchor) & (prior <= df["close"].shift(1).rolling(periods, min_periods=3).mean())
    up = (prior > anchor) & (prior >= df["close"].shift(1).rolling(periods, min_periods=3).mean())
    return down.fillna(False), up.fillna(False)


def prepare_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    """Clean, deduplicate and sort OHLCV without inventing missing prices or volume."""
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {', '.join(sorted(missing))}")
    df = frame.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for column in ("open", "high", "low", "close", "volume"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["date", "open", "high", "low", "close"])
    valid = (
        (df["high"] >= df[["open", "close", "low"]].max(axis=1))
        & (df["low"] <= df[["open", "close", "high"]].min(axis=1))
        & (df[["open", "high", "low", "close"]] >= 0).all(axis=1)
    )
    df = df.loc[valid].sort_values("date").drop_duplicates("date", keep="last")
    return df.reset_index(drop=True)


def _features(frame: pd.DataFrame, *, prepared: bool = False) -> pd.DataFrame:
    df = frame.copy().reset_index(drop=True) if prepared else prepare_ohlcv(frame)
    df["body"] = real_body(df)
    df["range"] = candle_range(df)
    df["upper"] = upper_shadow(df)
    df["lower"] = lower_shadow(df)
    df["body_ratio"] = safe_divide(df["body"], df["range"])
    df["bull"] = is_bullish(df)
    df["bear"] = is_bearish(df)
    df["doji_shape"] = is_doji(df)
    df["atr14"] = average_true_range(df)
    df["avg_volume20"] = average_volume(df)
    df["rel_vol_calc"] = safe_divide(df["volume"], df["avg_volume20"])
    df["gtgd20_ty_calc"] = (df["close"] * df["volume"]).rolling(20, min_periods=3).mean() / 1e9
    df["tolerance"] = price_tolerance(df)
    df["downtrend"], df["uptrend"] = rolling_trend(df)
    df["sma50"] = df["close"].rolling(50, min_periods=20).mean()
    df["sma200"] = df["close"].rolling(200, min_periods=50).mean()
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=5).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=5).mean()
    rs = safe_divide(gain, loss)
    df["rsi14"] = 100 - (100 / (1 + rs))
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    df["macd_hist"] = macd - macd.ewm(span=9, adjust=False).mean()
    middle = df["close"].rolling(20, min_periods=10).mean()
    std = df["close"].rolling(20, min_periods=10).std(ddof=0)
    df["bb_lower"], df["bb_upper"] = middle - 2 * std, middle + 2 * std
    df["change_pct"] = (df["close"] / df["close"].shift(1) - 1) * 100
    return df


def _false(df: pd.DataFrame) -> pd.Series:
    return pd.Series(False, index=df.index)


def bullish_engulfing(df: pd.DataFrame) -> pd.Series:
    """2 bars; after a decline, a bullish real body engulfs the prior bearish body."""
    p = df.shift(1)
    return (df["downtrend"] & p["bear"] & df["bull"] & (df["open"] <= p["close"])
            & (df["close"] >= p["open"]) & (df["body"] >= p["body"] * 1.05)
            & (p["body_ratio"] >= 0.15)).fillna(False)


def bearish_engulfing(df: pd.DataFrame) -> pd.Series:
    """2 bars; after an advance, a bearish real body engulfs the prior bullish body."""
    p = df.shift(1)
    return (df["uptrend"] & p["bull"] & df["bear"] & (df["open"] >= p["close"])
            & (df["close"] <= p["open"]) & (df["body"] >= p["body"] * 1.05)
            & (p["body_ratio"] >= 0.15)).fillna(False)


def bullish_harami(df: pd.DataFrame) -> pd.Series:
    """2 bars; after a decline, a small bullish body is contained in a large bearish body."""
    p = df.shift(1)
    return (df["downtrend"] & p["bear"] & df["bull"] & (p["body_ratio"] >= 0.5)
            & (df["body"] <= p["body"] * 0.6) & (df["open"] >= p["close"])
            & (df["close"] <= p["open"])).fillna(False)


def bearish_harami(df: pd.DataFrame) -> pd.Series:
    """2 bars; after an advance, a small bearish body is contained in a large bullish body."""
    p = df.shift(1)
    return (df["uptrend"] & p["bull"] & df["bear"] & (p["body_ratio"] >= 0.5)
            & (df["body"] <= p["body"] * 0.6) & (df["open"] <= p["close"])
            & (df["close"] >= p["open"])).fillna(False)


def bullish_harami_cross(df: pd.DataFrame) -> pd.Series:
    """2 bars; bullish-harami context with a doji second bar after a decline."""
    p = df.shift(1)
    lo, hi = p[["open", "close"]].min(axis=1), p[["open", "close"]].max(axis=1)
    return (df["downtrend"] & p["bear"] & (p["body_ratio"] >= 0.5) & df["doji_shape"]
            & (df[["open", "close"]].min(axis=1) >= lo)
            & (df[["open", "close"]].max(axis=1) <= hi)).fillna(False)


def bearish_harami_cross(df: pd.DataFrame) -> pd.Series:
    """2 bars; bearish-harami context with a doji second bar after an advance."""
    p = df.shift(1)
    lo, hi = p[["open", "close"]].min(axis=1), p[["open", "close"]].max(axis=1)
    return (df["uptrend"] & p["bull"] & (p["body_ratio"] >= 0.5) & df["doji_shape"]
            & (df[["open", "close"]].min(axis=1) >= lo)
            & (df[["open", "close"]].max(axis=1) <= hi)).fillna(False)


def hammer(df: pd.DataFrame) -> pd.Series:
    """1 bar plus context; small body, long lower/short upper shadow after a decline."""
    return (df["downtrend"] & (df["body"] > 0) & (df["lower"] >= 2 * df["body"])
            & (df["upper"] <= 0.20 * df["range"]) & (df["body_ratio"] <= 0.40)).fillna(False)


def hanging_man(df: pd.DataFrame) -> pd.Series:
    """1 bar plus context; hammer geometry after an advance, hence bearish classification."""
    return (df["uptrend"] & (df["body"] > 0) & (df["lower"] >= 2 * df["body"])
            & (df["upper"] <= 0.20 * df["range"]) & (df["body_ratio"] <= 0.40)).fillna(False)


def inverted_hammer(df: pd.DataFrame) -> pd.Series:
    """1 bar plus context; long upper/short lower shadow after a decline."""
    return (df["downtrend"] & (df["body"] > 0) & (df["upper"] >= 2 * df["body"])
            & (df["lower"] <= 0.20 * df["range"]) & (df["body_ratio"] <= 0.40)).fillna(False)


def shooting_star(df: pd.DataFrame) -> pd.Series:
    """1 bar plus context; long upper/short lower shadow after an advance."""
    return (df["uptrend"] & (df["body"] > 0) & (df["upper"] >= 2 * df["body"])
            & (df["lower"] <= 0.20 * df["range"]) & (df["body_ratio"] <= 0.40)).fillna(False)


def piercing_line(df: pd.DataFrame) -> pd.Series:
    """2 bars; after a decline, bullish close penetrates beyond half the prior bearish body."""
    p = df.shift(1)
    midpoint = (p["open"] + p["close"]) / 2
    return (df["downtrend"] & p["bear"] & df["bull"] & (p["body_ratio"] >= 0.45)
            & (df["open"] <= p["close"] + df["tolerance"])
            & (df["close"] > midpoint) & (df["close"] < p["open"])).fillna(False)


def dark_cloud_cover(df: pd.DataFrame) -> pd.Series:
    """2 bars; after an advance, bearish close penetrates beyond half the prior bullish body."""
    p = df.shift(1)
    midpoint = (p["open"] + p["close"]) / 2
    return (df["uptrend"] & p["bull"] & df["bear"] & (p["body_ratio"] >= 0.45)
            & (df["open"] >= p["close"] - df["tolerance"])
            & (df["close"] < midpoint) & (df["close"] > p["open"])).fillna(False)


def morning_star(df: pd.DataFrame) -> pd.Series:
    """3 bars; decline, long bearish candle, small body, then bullish close above midpoint."""
    a, b = df.shift(2), df.shift(1)
    return (df["downtrend"].shift(2).fillna(False) & a["bear"] & (a["body_ratio"] >= 0.5)
            & (b["body"] <= a["body"] * 0.45) & df["bull"]
            & (df["close"] > (a["open"] + a["close"]) / 2)).fillna(False)


def evening_star(df: pd.DataFrame) -> pd.Series:
    """3 bars; advance, long bullish candle, small body, then bearish close below midpoint."""
    a, b = df.shift(2), df.shift(1)
    return (df["uptrend"].shift(2).fillna(False) & a["bull"] & (a["body_ratio"] >= 0.5)
            & (b["body"] <= a["body"] * 0.45) & df["bear"]
            & (df["close"] < (a["open"] + a["close"]) / 2)).fillna(False)


def morning_doji_star(df: pd.DataFrame) -> pd.Series:
    """3 bars; Morning Star whose middle candle is a doji after a decline."""
    a, b = df.shift(2), df.shift(1)
    return (df["downtrend"].shift(2).fillna(False) & a["bear"] & (a["body_ratio"] >= 0.5)
            & b["doji_shape"] & df["bull"] & (df["close"] > (a["open"] + a["close"]) / 2)).fillna(False)


def evening_doji_star(df: pd.DataFrame) -> pd.Series:
    """3 bars; Evening Star whose middle candle is a doji after an advance."""
    a, b = df.shift(2), df.shift(1)
    return (df["uptrend"].shift(2).fillna(False) & a["bull"] & (a["body_ratio"] >= 0.5)
            & b["doji_shape"] & df["bear"] & (df["close"] < (a["open"] + a["close"]) / 2)).fillna(False)


def doji(df: pd.DataFrame) -> pd.Series:
    """1 bar; real body is at most 10% of a non-zero candle range."""
    return (df["doji_shape"] & (df["range"] > 0)).fillna(False)


def dragonfly_doji(df: pd.DataFrame) -> pd.Series:
    """1 bar; doji with long lower shadow and tiny upper shadow, preferably after weakness."""
    return (df["doji_shape"] & (df["lower"] >= 0.60 * df["range"])
            & (df["upper"] <= 0.12 * df["range"]) & df["downtrend"]).fillna(False)


def gravestone_doji(df: pd.DataFrame) -> pd.Series:
    """1 bar; doji with long upper shadow and tiny lower shadow, preferably after strength."""
    return (df["doji_shape"] & (df["upper"] >= 0.60 * df["range"])
            & (df["lower"] <= 0.12 * df["range"]) & df["uptrend"]).fillna(False)


def long_legged_doji(df: pd.DataFrame) -> pd.Series:
    """1 bar; doji with both shadows at least 35% of the range."""
    return (df["doji_shape"] & (df["upper"] >= 0.35 * df["range"])
            & (df["lower"] >= 0.35 * df["range"])).fillna(False)


def spinning_top(df: pd.DataFrame) -> pd.Series:
    """1 bar; small non-doji body with meaningful shadows on both sides."""
    return ((df["body_ratio"] > 0.10) & (df["body_ratio"] <= 0.35)
            & (df["upper"] >= df["body"] * 0.5) & (df["lower"] >= df["body"] * 0.5)).fillna(False)


def marubozu_bullish(df: pd.DataFrame) -> pd.Series:
    """1 bar; bullish body covers at least 85% of range with negligible shadows."""
    return (df["bull"] & (df["body_ratio"] >= 0.85)
            & (df["upper"] <= 0.08 * df["range"]) & (df["lower"] <= 0.08 * df["range"])).fillna(False)


def marubozu_bearish(df: pd.DataFrame) -> pd.Series:
    """1 bar; bearish body covers at least 85% of range with negligible shadows."""
    return (df["bear"] & (df["body_ratio"] >= 0.85)
            & (df["upper"] <= 0.08 * df["range"]) & (df["lower"] <= 0.08 * df["range"])).fillna(False)


def inside_bar(df: pd.DataFrame) -> pd.Series:
    """2 bars; current high-low range is strictly inside the prior range."""
    p = df.shift(1)
    return ((df["high"] < p["high"]) & (df["low"] > p["low"])).fillna(False)


def outside_bar(df: pd.DataFrame) -> pd.Series:
    """2 bars; current high-low range contains the prior range."""
    p = df.shift(1)
    return ((df["high"] > p["high"]) & (df["low"] < p["low"])).fillna(False)


def tweezer_bottom(df: pd.DataFrame) -> pd.Series:
    """2 bars; lows match within ATR/price tolerance after a decline and colors reverse."""
    p = df.shift(1)
    return (df["downtrend"] & p["bear"] & df["bull"]
            & ((df["low"] - p["low"]).abs() <= df["tolerance"])).fillna(False)


def tweezer_top(df: pd.DataFrame) -> pd.Series:
    """2 bars; highs match within ATR/price tolerance after an advance and colors reverse."""
    p = df.shift(1)
    return (df["uptrend"] & p["bull"] & df["bear"]
            & ((df["high"] - p["high"]).abs() <= df["tolerance"])).fillna(False)


def three_white_soldiers(df: pd.DataFrame) -> pd.Series:
    """3 bars; after weakness, three strong bullish candles close progressively higher."""
    a, b = df.shift(2), df.shift(1)
    return (df["downtrend"].shift(2).fillna(False) & a["bull"] & b["bull"] & df["bull"]
            & (a["body_ratio"] >= 0.45) & (b["body_ratio"] >= 0.45) & (df["body_ratio"] >= 0.45)
            & (b["close"] > a["close"]) & (df["close"] > b["close"])
            & (b["open"] >= a[["open", "close"]].min(axis=1)) & (b["open"] <= a["close"])
            & (df["open"] >= b[["open", "close"]].min(axis=1)) & (df["open"] <= b["close"])).fillna(False)


def three_black_crows(df: pd.DataFrame) -> pd.Series:
    """3 bars; after strength, three strong bearish candles close progressively lower."""
    a, b = df.shift(2), df.shift(1)
    return (df["uptrend"].shift(2).fillna(False) & a["bear"] & b["bear"] & df["bear"]
            & (a["body_ratio"] >= 0.45) & (b["body_ratio"] >= 0.45) & (df["body_ratio"] >= 0.45)
            & (b["close"] < a["close"]) & (df["close"] < b["close"])
            & (b["open"] <= a[["open", "close"]].max(axis=1)) & (b["open"] >= a["close"])
            & (df["open"] <= b[["open", "close"]].max(axis=1)) & (df["open"] >= b["close"])).fillna(False)


def rising_three_methods(df: pd.DataFrame) -> pd.Series:
    """5 bars; long bull, three contained pullback bars, then bullish breakout continuation."""
    a, b, c, d = df.shift(4), df.shift(3), df.shift(2), df.shift(1)
    contained = (pd.concat([b["high"], c["high"], d["high"]], axis=1).max(axis=1) < a["high"]) & (
        pd.concat([b["low"], c["low"], d["low"]], axis=1).min(axis=1) > a["low"])
    return (a["bull"] & (a["body_ratio"] >= 0.55) & contained & df["bull"]
            & (df["close"] > a["high"]) & (df["body_ratio"] >= 0.50)).fillna(False)


def falling_three_methods(df: pd.DataFrame) -> pd.Series:
    """5 bars; long bear, three contained rebound bars, then bearish breakdown continuation."""
    a, b, c, d = df.shift(4), df.shift(3), df.shift(2), df.shift(1)
    contained = (pd.concat([b["high"], c["high"], d["high"]], axis=1).max(axis=1) < a["high"]) & (
        pd.concat([b["low"], c["low"], d["low"]], axis=1).min(axis=1) > a["low"])
    return (a["bear"] & (a["body_ratio"] >= 0.55) & contained & df["bear"]
            & (df["close"] < a["low"]) & (df["body_ratio"] >= 0.50)).fillna(False)


def _meta(key: str, name: str, vi: str, direction: str, category: str, bars: int,
          trend: str | None, description: str) -> PatternMeta:
    return PatternMeta(key, name, vi, direction, category, bars, trend, description)


_DETECTORS: list[tuple[PatternMeta, Detector]] = [
    (_meta("bullish_engulfing", "Bullish Engulfing", "Nhấn chìm tăng", "bullish", "reversal", 2, "down", "Thân tăng bao trọn thân giảm trước đó."), bullish_engulfing),
    (_meta("bullish_harami", "Bullish Harami", "Harami tăng", "bullish", "reversal", 2, "down", "Thân tăng nhỏ nằm trong thân giảm lớn."), bullish_harami),
    (_meta("bullish_harami_cross", "Bullish Harami Cross", "Harami Cross tăng", "bullish", "reversal", 2, "down", "Doji nằm trong thân giảm lớn."), bullish_harami_cross),
    (_meta("hammer", "Hammer", "Búa", "bullish", "reversal", 1, "down", "Râu dưới dài sau nhịp giảm."), hammer),
    (_meta("inverted_hammer", "Inverted Hammer", "Búa ngược", "bullish", "reversal", 1, "down", "Râu trên dài sau nhịp giảm."), inverted_hammer),
    (_meta("piercing_line", "Piercing Line", "Đường xuyên tăng", "bullish", "reversal", 2, "down", "Nến tăng đóng quá nửa thân giảm trước."), piercing_line),
    (_meta("morning_star", "Morning Star", "Sao Mai", "bullish", "reversal", 3, "down", "Ba nến đảo chiều tăng thích ứng thị trường ít gap."), morning_star),
    (_meta("morning_doji_star", "Morning Doji Star", "Sao Mai Doji", "bullish", "reversal", 3, "down", "Morning Star với nến giữa là Doji."), morning_doji_star),
    (_meta("dragonfly_doji", "Dragonfly Doji", "Doji chuồn chuồn", "bullish", "reversal", 1, "down", "Doji râu dưới dài sau suy yếu."), dragonfly_doji),
    (_meta("tweezer_bottom", "Tweezer Bottom", "Đáy nhíp", "bullish", "reversal", 2, "down", "Hai đáy gần bằng nhau theo tolerance thích ứng."), tweezer_bottom),
    (_meta("three_white_soldiers", "Three White Soldiers", "Ba chàng lính trắng", "bullish", "reversal", 3, "down", "Ba nến tăng mạnh liên tiếp sau suy yếu."), three_white_soldiers),
    (_meta("bearish_engulfing", "Bearish Engulfing", "Nhấn chìm giảm", "bearish", "reversal", 2, "up", "Thân giảm bao trọn thân tăng trước đó."), bearish_engulfing),
    (_meta("bearish_harami", "Bearish Harami", "Harami giảm", "bearish", "reversal", 2, "up", "Thân giảm nhỏ nằm trong thân tăng lớn."), bearish_harami),
    (_meta("bearish_harami_cross", "Bearish Harami Cross", "Harami Cross giảm", "bearish", "reversal", 2, "up", "Doji nằm trong thân tăng lớn."), bearish_harami_cross),
    (_meta("hanging_man", "Hanging Man", "Người treo cổ", "bearish", "reversal", 1, "up", "Hình học búa sau nhịp tăng."), hanging_man),
    (_meta("shooting_star", "Shooting Star", "Sao băng", "bearish", "reversal", 1, "up", "Râu trên dài sau nhịp tăng."), shooting_star),
    (_meta("dark_cloud_cover", "Dark Cloud Cover", "Mây đen che phủ", "bearish", "reversal", 2, "up", "Nến giảm đóng quá nửa thân tăng trước."), dark_cloud_cover),
    (_meta("evening_star", "Evening Star", "Sao Hôm", "bearish", "reversal", 3, "up", "Ba nến đảo chiều giảm thích ứng thị trường ít gap."), evening_star),
    (_meta("evening_doji_star", "Evening Doji Star", "Sao Hôm Doji", "bearish", "reversal", 3, "up", "Evening Star với nến giữa là Doji."), evening_doji_star),
    (_meta("gravestone_doji", "Gravestone Doji", "Doji bia mộ", "bearish", "reversal", 1, "up", "Doji râu trên dài sau tăng."), gravestone_doji),
    (_meta("tweezer_top", "Tweezer Top", "Đỉnh nhíp", "bearish", "reversal", 2, "up", "Hai đỉnh gần bằng nhau theo tolerance thích ứng."), tweezer_top),
    (_meta("three_black_crows", "Three Black Crows", "Ba con quạ đen", "bearish", "reversal", 3, "up", "Ba nến giảm mạnh liên tiếp sau tăng."), three_black_crows),
    (_meta("doji", "Doji", "Doji", "neutral", "special", 1, None, "Thân rất nhỏ so với biên độ."), doji),
    (_meta("long_legged_doji", "Long-Legged Doji", "Doji chân dài", "neutral", "special", 1, None, "Doji có hai râu dài."), long_legged_doji),
    (_meta("spinning_top", "Spinning Top", "Con xoay", "neutral", "special", 1, None, "Thân nhỏ với hai râu đáng kể."), spinning_top),
    (_meta("marubozu_bullish", "Bullish Marubozu", "Marubozu tăng", "bullish", "continuation", 1, None, "Nến tăng gần như không có râu."), marubozu_bullish),
    (_meta("marubozu_bearish", "Bearish Marubozu", "Marubozu giảm", "bearish", "continuation", 1, None, "Nến giảm gần như không có râu."), marubozu_bearish),
    (_meta("inside_bar", "Inside Bar", "Nến trong", "neutral", "special", 2, None, "Biên nến nằm trong nến trước."), inside_bar),
    (_meta("outside_bar", "Outside Bar", "Nến ngoài", "neutral", "special", 2, None, "Biên nến bao nến trước."), outside_bar),
    (_meta("rising_three_methods", "Rising Three Methods", "Ba bước tăng", "bullish", "continuation", 5, None, "Năm nến tiếp diễn tăng."), rising_three_methods),
    (_meta("falling_three_methods", "Falling Three Methods", "Ba bước giảm", "bearish", "continuation", 5, None, "Năm nến tiếp diễn giảm."), falling_three_methods),
]

PATTERN_REGISTRY: dict[str, PatternMeta] = {meta.key: meta for meta, _ in _DETECTORS}
PATTERN_DETECTORS: dict[str, Detector] = {meta.key: detector for meta, detector in _DETECTORS}


def detect_patterns(frame: pd.DataFrame, *, prepared: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return enriched bars and a boolean matrix keyed by registered patterns."""
    features = _features(frame, prepared=prepared)
    detected = pd.DataFrame(index=features.index)
    valid_candle = features["range"] > 0
    for key, detector in PATTERN_DETECTORS.items():
        detected[key] = (detector(features) & valid_candle).fillna(False).astype(bool)
    return features, detected


def resample_ohlcv(frame: pd.DataFrame, timeframe: str, as_of: datetime | None = None,
                   *, prepared: bool = False) -> pd.DataFrame:
    """Resample daily bars to W-FRI or calendar month using first/max/min/last/sum.

    The representative date is the last actual trading date in the period.
    ``is_complete`` reflects the scheduled period boundary; a null-volume period
    remains null because volume uses ``sum(min_count=1)``.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    df = frame.copy().reset_index(drop=True) if prepared else prepare_ohlcv(frame)
    if df.empty:
        return df.assign(period_start=pd.NaT, period_end=pd.NaT, scheduled_period_end=pd.NaT, is_complete=False)
    if timeframe == "1D":
        out = df.copy()
        out["period_start"] = out["date"]
        out["period_end"] = out["date"]
        out["scheduled_period_end"] = out["date"]
        out["is_complete"] = True
        return out

    work = df.assign(_period=df["date"].dt.to_period("W-FRI" if timeframe == "1W" else "M"))
    grouped = work.groupby("_period", sort=True, observed=True)
    out = grouped.agg(
        date=("date", "last"), period_start=("date", "first"), period_end=("date", "last"),
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
    )
    out["volume"] = grouped["volume"].sum(min_count=1)
    out["scheduled_period_end"] = out.index.to_timestamp(how="end").normalize()
    out = out.reset_index(drop=True)
    now = as_of or datetime.now().astimezone()
    today = pd.Timestamp(now.date())
    boundary = pd.to_datetime(out["scheduled_period_end"])
    complete = boundary < today
    if timeframe == "1W":
        complete |= (boundary == today) & (now.time() >= time(15, 15))
    out["is_complete"] = complete.astype(bool)
    return out.reset_index(drop=True)


def _geometry_match(key: str, row: pd.Series, previous: pd.Series | None) -> float:
    ratio = float(row.get("body_ratio")) if pd.notna(row.get("body_ratio")) else 0.0
    if "doji" in key:
        return float(np.clip(1 - ratio / 0.10, 0.55, 1.0))
    if key in {"hammer", "hanging_man", "inverted_hammer", "shooting_star"}:
        long_shadow = row["lower"] if key in {"hammer", "hanging_man"} else row["upper"]
        return float(np.clip(0.60 + 0.10 * safe_number(long_shadow / max(row["body"], EPSILON)), 0.60, 1.0))
    if "engulfing" in key and previous is not None:
        return float(np.clip(0.65 + 0.20 * safe_number(row["body"] / max(previous["body"], EPSILON) - 1), 0.65, 1.0))
    if key in {"marubozu_bullish", "marubozu_bearish"}:
        return float(np.clip(ratio, 0.70, 1.0))
    return float(np.clip(0.65 + 0.25 * ratio, 0.65, 0.95))


def safe_number(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _score(meta: PatternMeta, row: pd.Series, previous: pd.Series | None, status: str,
           smc: Iterable[str], margin_status: object, rs_rating: object,
           ticker_stale: bool = False) -> tuple[int, int, dict, list[str], list[str]]:
    geometry = round(35 * _geometry_match(meta.key, row, previous), 1)
    trend = 20.0 if meta.prior_trend else 12.0
    confirmations: list[str] = []
    warnings: list[str] = []

    rel_vol = safe_number(row.get("rel_vol_calc"), default=float("nan"))
    if math.isfinite(rel_vol):
        volume = float(np.clip(6 + (rel_vol - 0.8) * 12, 0, 15))
        (confirmations if rel_vol >= 1.2 else warnings if rel_vol < 0.8 else confirmations).append(
            "volume_confirmation" if rel_vol >= 1.2 else "weak_volume" if rel_vol < 0.8 else "normal_volume"
        )
    else:
        volume = 4.0
        warnings.append("missing_volume_context")

    smc_set = set(smc)
    aligned = ({"ob_bull", "fvg_bull"} if meta.direction == "bullish" else {"ob_bear", "fvg_bear"}) & smc_set
    conflicting = ({"ob_bear", "fvg_bear"} if meta.direction == "bullish" else {"ob_bull", "fvg_bull"}) & smc_set
    context = 7.0
    for tag in sorted(aligned):
        confirmations.append("bullish_order_block" if tag == "ob_bull" else "bearish_order_block" if tag == "ob_bear" else "bullish_fvg" if tag == "fvg_bull" else "bearish_fvg")
    if aligned:
        context = 15.0
    if conflicting:
        warnings.append("conflicting_smc")
        context = 2.0
    close = safe_number(row.get("close"))
    if meta.direction == "bullish" and pd.notna(row.get("bb_lower")) and close <= safe_number(row["bb_lower"]) * 1.02:
        confirmations.append("bollinger_lower_band")
        context = max(context, 12.0)
    if meta.direction == "bearish" and pd.notna(row.get("bb_upper")) and close >= safe_number(row["bb_upper"]) * 0.98:
        confirmations.append("bollinger_upper_band")
        context = max(context, 12.0)

    gtgd = safe_number(row.get("gtgd20_ty_calc"), default=float("nan"))
    history_ok = pd.notna(row.get("atr14"))
    quality = 10.0 if history_ok else 5.0
    if math.isfinite(gtgd) and gtgd < MIN_LIQUIDITY_TY:
        warnings.append("low_liquidity")
        quality = min(quality, 3.0)
    if pd.isna(row.get("volume")) or safe_number(row.get("volume")) <= 0:
        warnings.append("zero_or_missing_volume")
        quality = min(quality, 4.0)
    if not history_ok:
        warnings.append("insufficient_history")
    if ticker_stale:
        warnings.append("stale_ticker_data")
        quality = min(quality, 2.0)

    higher = 2.0
    sma200 = row.get("sma200")
    if pd.notna(sma200):
        above = close >= safe_number(sma200)
        if meta.direction == "bullish" and above:
            confirmations.append("above_sma200")
            higher = 5.0
        elif meta.direction == "bearish" and not above:
            confirmations.append("below_sma200")
            higher = 5.0
        elif meta.direction == "bullish":
            warnings.append("below_sma200")
        elif meta.direction == "bearish":
            warnings.append("above_sma200_against_bearish_pattern")
    rsi = safe_number(row.get("rsi14"), default=float("nan"))
    if math.isfinite(rsi) and meta.direction == "bullish" and rsi <= 35:
        confirmations.append("rsi_oversold")
    if math.isfinite(rsi) and meta.direction == "bearish" and rsi >= 65:
        confirmations.append("rsi_overbought")
    macd = safe_number(row.get("macd_hist"), default=float("nan"))
    if math.isfinite(macd) and ((meta.direction == "bullish" and macd > 0) or (meta.direction == "bearish" and macd < 0)):
        confirmations.append("macd_confirmed")
    rs = safe_number(rs_rating, default=float("nan"))
    if math.isfinite(rs) and rs >= 80:
        confirmations.append("rs_strong")
        higher = min(5.0, higher + 1.0)
    if margin_status is not None and str(margin_status).strip() and str(margin_status).lower() != "nan":
        warnings.append("margin_warning")
    if status == "forming":
        warnings.extend(["incomplete_period", "unconfirmed_pattern"])

    breakdown = {
        "geometry": round(geometry, 1), "trend_context": round(trend, 1),
        "volume": round(volume, 1), "support_resistance_smc": round(context, 1),
        "liquidity_data_quality": round(quality, 1), "higher_timeframe_rs": round(higher, 1),
    }
    score = int(round(sum(breakdown.values()) - (5 if status == "forming" else 0)))
    score = max(0, min(100, score))
    stars = 3 if score >= 80 else 2 if score >= 60 else 1 if score >= 40 else 0
    return score, stars, breakdown, list(dict.fromkeys(confirmations)), list(dict.fromkeys(warnings))


def _iso(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def scan_timeframe(frame: pd.DataFrame, ticker: str, timeframe: str, *, as_of: datetime,
                   lookback: int, meta_row: Mapping[str, object] | None = None,
                   smc_latest: Iterable[str] = (), min_confidence: int = 40,
                   max_results: int = 12, market_scan_date: str | None = None) -> list[dict]:
    bars = resample_ohlcv(frame, timeframe, as_of, prepared=True)
    if bars.empty:
        return []
    ticker_stale = bool(market_scan_date and _iso(bars["date"].iloc[-1]) < str(market_scan_date))
    # Only the export window plus indicator warm-up can affect emitted rows.
    # This keeps SMA200/ATR/volume context intact without recomputing features
    # over every historical daily bar for all ~1,700 tickers.
    bars = bars.tail(lookback + 210).reset_index(drop=True)
    features, matrix = detect_patterns(bars, prepared=True)
    for column in ("period_start", "period_end", "scheduled_period_end", "is_complete"):
        features[column] = bars[column].values
    meta_row = dict(meta_row or {})
    results: list[dict] = []
    start = max(0, len(features) - lookback)
    for position in range(start, len(features)):
        active = [key for key in PATTERN_REGISTRY if bool(matrix.at[position, key])]
        if not active:
            continue
        row = features.iloc[position]
        previous = features.iloc[position - 1] if position else None
        status = "completed" if bool(row["is_complete"]) else "forming"
        is_latest = position == len(features) - 1
        current_smc = list(smc_latest) if is_latest else []
        snapshot_matches = is_latest and str(meta_row.get("date", ""))[:10] == _iso(row["date"])
        rs_rating = meta_row.get("rs_rating") if snapshot_matches else None
        for key in active:
            meta = PATTERN_REGISTRY[key]
            score, stars, breakdown, confirmations, warnings = _score(
                meta, row, previous, status, current_smc, meta_row.get("margin_status"), rs_rating,
                ticker_stale=ticker_stale,
            )
            if score < min_confidence:
                continue
            results.append({
                "ticker": str(ticker), "timeframe": timeframe, "pattern_key": key,
                "pattern_name": meta.name, "pattern_name_vi": meta.name_vi,
                "direction": meta.direction, "category": meta.category, "status": status,
                "detected_at": _iso(row["date"]), "period_start": _iso(row["period_start"]),
                "period_end": _iso(row["period_end"]),
                "scheduled_period_end": _iso(row["scheduled_period_end"]),
                "bars_ago": int(len(features) - 1 - position),
                "confidence_score": score, "confidence_stars": stars,
                "close": safe_nullable(row.get("close")), "change_pct": safe_nullable(row.get("change_pct"), 3),
                "volume": safe_nullable(row.get("volume"), 0),
                "industry": safe_nullable(meta_row.get("industry")), "exchange": safe_nullable(meta_row.get("exchange")),
                "rs_rating": safe_nullable(rs_rating, 1), "rel_vol": safe_nullable(row.get("rel_vol_calc"), 2),
                "gtgd20_ty": safe_nullable(row.get("gtgd20_ty_calc"), 2),
                "margin_status": safe_nullable(meta_row.get("margin_status")),
                "confirmations": confirmations, "warnings": warnings, "smc": current_smc,
                "score_breakdown": breakdown,
                "pattern_metadata": {"bars_required": meta.bars, "prior_trend": meta.prior_trend,
                                     "description": meta.description},
            })
    return sorted(results, key=lambda item: (item["bars_ago"], -item["confidence_score"], item["pattern_key"]))[:max_results]


def _scan_ticker_job(task: tuple) -> tuple[bool, list[dict]]:
    """Top-level process worker; receives only one ticker group, never the market DataFrame."""
    (ticker, group, generated_at, scan_date, lookbacks, meta_row, smc_latest,
     min_confidence, max_results_per_ticker_timeframe) = task
    daily = prepare_ohlcv(group)
    if len(daily) < 8:
        return False, []
    found: list[dict] = []
    for timeframe in TIMEFRAMES:
        found.extend(scan_timeframe(
            daily, str(ticker), timeframe, as_of=generated_at, lookback=lookbacks[timeframe],
            meta_row=meta_row, smc_latest=smc_latest, min_confidence=min_confidence,
            max_results=max_results_per_ticker_timeframe, market_scan_date=scan_date,
        ))
    return True, found


def safe_nullable(value: object, digits: int | None = None) -> object:
    if value is None or (not isinstance(value, (list, dict, str)) and pd.isna(value)):
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        if not math.isfinite(number):
            return None
        return round(number, digits) if digits is not None else number
    text = str(value).strip()
    return text or None


def build_snapshot(ohlcv: pd.DataFrame, *, scan_date: str, generated_at: datetime,
                   market_snapshot: pd.DataFrame | None = None,
                   smc_by_ticker: Mapping[str, Iterable[str]] | None = None,
                   lookbacks: Mapping[str, int] | None = None, min_confidence: int = 40,
                   max_results_per_ticker_timeframe: int = 3,
                   tickers: Iterable[str] | None = None,
                   progress: Callable[[int], None] | None = None,
                   workers: int = 1) -> dict:
    """Scan all tickers/timeframes and return one strict JSON-safe snapshot object."""
    started = datetime.now()
    lookbacks = {**LOOKBACKS, **dict(lookbacks or {})}
    smc_by_ticker = smc_by_ticker or {}
    allowed = set(tickers) if tickers is not None else None
    snapshot_map: dict[str, dict] = {}
    if market_snapshot is not None and not market_snapshot.empty and "ticker" in market_snapshot:
        snapshot_map = {str(row["ticker"]): row for row in market_snapshot.to_dict(orient="records")}
    patterns: list[dict] = []
    scanned = 0
    cleaned = ohlcv.copy()
    if "ticker" not in cleaned:
        raise ValueError("Missing ticker column")
    def task_stream():
        for ticker, group in cleaned.groupby("ticker", sort=True):
            ticker = str(ticker)
            if allowed is not None and ticker not in allowed:
                continue
            yield (ticker, group, generated_at, scan_date, lookbacks, snapshot_map.get(ticker),
                   list(smc_by_ticker.get(ticker, ())), min_confidence,
                   max_results_per_ticker_timeframe)

    tasks = iter(task_stream())
    workers = max(1, int(workers))
    if workers == 1:
        results = map(_scan_ticker_job, tasks)
        for did_scan, found in results:
            if not did_scan:
                continue
            scanned += 1
            patterns.extend(found)
            if progress is not None and scanned % 200 == 0:
                progress(scanned)
    else:
        # Bounded queue: do not materialize ~1,700 group DataFrames at once.
        with ProcessPoolExecutor(max_workers=workers) as executor:
            pending = set()
            for _ in range(workers * 2):
                try:
                    pending.add(executor.submit(_scan_ticker_job, next(tasks)))
                except StopIteration:
                    break
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    did_scan, found = future.result()
                    if did_scan:
                        scanned += 1
                        patterns.extend(found)
                        if progress is not None and scanned % 200 == 0:
                            progress(scanned)
                    try:
                        pending.add(executor.submit(_scan_ticker_job, next(tasks)))
                    except StopIteration:
                        pass
    patterns.sort(key=lambda item: (item["bars_ago"], -item["confidence_score"], item["ticker"], item["timeframe"]))
    summary = {"total_patterns": len(patterns)}
    for direction in ("bullish", "bearish", "neutral"):
        summary[direction] = sum(item["direction"] == direction for item in patterns)
    for status in ("forming", "completed"):
        summary[status] = sum(item["status"] == status for item in patterns)
    by_timeframe = {tf: sum(item["timeframe"] == tf for item in patterns) for tf in TIMEFRAMES}
    summary["by_timeframe"] = by_timeframe
    summary["tickers_scanned"] = scanned
    summary["runtime_seconds"] = round((datetime.now() - started).total_seconds(), 3)
    payload = {
        "schema_version": 1, "generated_at": generated_at.isoformat(), "scan_date": str(scan_date),
        "source_type": "local_pipeline", "timeframes": list(TIMEFRAMES), "summary": summary,
        "config": {"lookbacks": lookbacks, "min_confidence": min_confidence,
                   "max_results_per_ticker_timeframe": max_results_per_ticker_timeframe,
                   "workers": workers,
                   "forming_note": "Đang hình thành · Chưa xác nhận · Kỳ chưa đóng"},
        "registry": {key: asdict(meta) for key, meta in PATTERN_REGISTRY.items()},
        "patterns": patterns,
    }
    return sanitize_json(payload)


def sanitize_json(value: object) -> object:
    """Recursively convert NumPy/pandas values and replace non-finite numbers with null."""
    if isinstance(value, dict):
        return {str(key): sanitize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize_json(item) for item in value]
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def atomic_write_snapshot(payload: dict, json_path: str | os.PathLike[str],
                          js_path: str | os.PathLike[str]) -> None:
    """Atomically write JSON and file:// fallback from the exact same object."""
    serialized = json.dumps(
        sanitize_json(payload), ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )
    for path, content in ((Path(json_path), serialized),
                          (Path(js_path), "window.CANDLESTICK_PATTERNS = " + serialized + ";\n")):
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
