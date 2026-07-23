# ==========================================================================
# vn_indicators.py — THƯ VIỆN CHỈ BÁO KỸ THUẬT chính thức + mixer snapshot
# ==========================================================================
# PHẦN 1 — THƯ VIỆN CHỈ BÁO (Analyzer/Dashboard/AI import từ đây):
#     from vn_indicators import rsi, macd, ichimoku, zigzag, ...
#   Quy ước chung cho MỌI hàm chỉ báo:
#   - Nhận DataFrame có cột open/high/low/close/volume (KHÔNG phân biệt hoa thường).
#   - Trả về Series hoặc DataFrame CÙNG index, KHÔNG bao giờ drop dòng.
#   - Chia an toàn: mẫu số 0 -> NaN (không ZeroDivisionError, không inf).
#   - Vector hóa pandas/numpy toàn bộ. Ngoại lệ DUY NHẤT: zigzag() — pivot sau
#     phụ thuộc pivot trước (trạng thái theo đường đi) nên phải quét tuần tự.
# PHẦN 2 — PIPELINE (hành vi cũ giữ nguyên, chỉ CỘNG THÊM cột/file — không xóa/đổi cột cũ):
#     python vn_indicators.py         -> screen_snapshot.csv (+ is_live/days_stale; rs_rating chỉ
#                                          xếp hạng trong mã live) + screen_snapshot_live.csv (chỉ mã
#                                          có nến phiên mới nhất) + market_breadth.csv
#     python vn_indicators.py full    -> thêm ~130 chỉ báo pandas_ta (CHẬM)
# ==========================================================================

import os
import sys
import sqlite3
import warnings

import numpy as np
import pandas as pd
from runtime_paths import runtime_root
from live_universe import evaluate as evaluate_live_universe

warnings.filterwarnings("ignore")

RUNTIME_ROOT = runtime_root(os.getcwd())
DB_PATH = str(RUNTIME_ROOT / "vn_stock.db")
OUT_DIR = str(RUNTIME_ROOT)
INDEX_SYMBOLS = ["VNINDEX", "HNXINDEX", "UPCOMINDEX"]   # chỉ số: có trong DB nhưng KHÔNG vào bảng lọc
MIN_BARS = 60
FULL_TA = ("full" in sys.argv)          # `python vn_indicators.py full` -> tính thêm ~130 chỉ báo pandas_ta
WRITE_FULL_HISTORY = False              # True = ghi lịch sử đầy đủ ra thư mục indicators_full/
# LƯU Ý GIÁ ĐIỀU CHỈNH: nếu nguồn trả giá THÔ (chưa điều chỉnh cổ tức/chia tách), ret_12m & MA200
# sẽ gãy tại ngày chia. Kiểm tra tay 1 mã vừa chia tách gần đây để xác nhận nguồn đã adjust.

__all__ = [
    # Trend
    "sma", "ema", "wma", "vwma",
    # Momentum
    "rsi", "macd", "stochastic", "williams_r", "roc",
    # Volume
    "obv", "cmf", "mfi", "volume_oscillator",
    # Volatility
    "true_range", "atr", "bollinger_bands", "keltner_channel",
    # Trend strength
    "adx",
    # Hỗ trợ / kháng cự
    "fibonacci_retracement", "pivot_points",
    # Mây
    "ichimoku",
    # Smart Money (proxy)
    "fair_value_gap", "order_block", "market_structure",
    "break_of_structure", "change_of_character",
    # Mẫu hình
    "fractal", "zigzag", "elliott_wave_proxy",
    # Tiện ích
    "wilder",
]


# ==========================================================================
# PHẦN 1A — TIỆN ÍCH NỘI BỘ
# ==========================================================================

def _series(df: pd.DataFrame, col: str) -> pd.Series:
    """Lấy 1 cột KHÔNG phân biệt hoa thường ('close' hay 'Close' đều được).

    Raises:
        KeyError: nếu DataFrame không có cột yêu cầu.
    """
    if col in df.columns:
        return df[col]
    lower_map = {str(c).lower(): c for c in df.columns}
    key = col.lower()
    if key in lower_map:
        return df[lower_map[key]]
    raise KeyError(f"Thiếu cột '{col}' trong DataFrame (các cột hiện có: {list(df.columns)})")


def _ohlcv(df: pd.DataFrame) -> tuple:
    """Trả về tuple (open, high, low, close, volume) — mỗi phần tử 1 Series."""
    return (_series(df, "open"), _series(df, "high"), _series(df, "low"),
            _series(df, "close"), _series(df, "volume"))


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Chia an toàn: mẫu số = 0 -> NaN (giữ nguyên index, không raise, không inf)."""
    return numerator / denominator.where(denominator != 0)


def wilder(s: pd.Series, n: int) -> pd.Series:
    """RMA/SMMA của Wilder (khớp ta.rma TradingView, sai số hội tụ về 0 sau ~100 nến)."""
    return s.ewm(alpha=1 / n, adjust=False).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    """True Range = max(H-L, |H-C_trước|, |L-C_trước|). Nến đầu tiên = H-L."""
    _, h, l, c, _ = _ohlcv(df)
    pc = c.shift()
    return pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)


# ==========================================================================
# PHẦN 1B — TREND
# ==========================================================================

def sma(df: pd.DataFrame, window: int = 20, column: str = "close") -> pd.Series:
    """Simple Moving Average — trung bình cộng trượt `window` phiên."""
    return _series(df, column).rolling(window).mean().rename(f"sma{window}")


def ema(df: pd.DataFrame, window: int = 20, column: str = "close") -> pd.Series:
    """Exponential Moving Average — hệ số alpha = 2/(window+1), tính từ nến đầu
    (adjust=False, khớp TradingView; hội tụ sau ~3*window nến)."""
    return _series(df, column).ewm(span=window, adjust=False).mean().rename(f"ema{window}")


def wma(df: pd.DataFrame, window: int = 20, column: str = "close") -> pd.Series:
    """Weighted Moving Average — trọng số tuyến tính 1..window (nến mới nặng nhất).

    Vector hóa bằng sliding_window_view (dot product cả ma trận cửa sổ 1 lần);
    cửa sổ chứa NaN -> kết quả NaN (không âm thầm bỏ dòng).
    """
    s = _series(df, column)
    arr = s.to_numpy(dtype=float)
    out = np.full(len(arr), np.nan)
    if len(arr) >= window:
        weights = np.arange(1, window + 1, dtype=float)
        windows = np.lib.stride_tricks.sliding_window_view(arr, window)
        out[window - 1:] = windows @ weights / weights.sum()
    return pd.Series(out, index=s.index, name=f"wma{window}")


def vwma(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Volume Weighted Moving Average = sum(close*volume, n) / sum(volume, n).

    Cả cửa sổ không có giao dịch (tổng volume = 0) -> NaN (chia an toàn).
    """
    _, _, _, c, v = _ohlcv(df)
    pv = (c * v).rolling(window).sum()
    vv = v.rolling(window).sum()
    return _safe_div(pv, vv).rename(f"vwma{window}")


# ==========================================================================
# PHẦN 1C — MOMENTUM
# ==========================================================================

def rsi(df: pd.DataFrame, window: int = 14, column: str = "close") -> pd.Series:
    """Relative Strength Index — chuẩn Wilder (RMA), khớp TradingView.

    Dùng dạng đại số RSI = 100*up/(up+dn) thay vì 100-100/(1+RS):
    - dn = 0 (chuỗi chỉ tăng) -> RSI = 100 đúng giáo trình (bản cũ trả NaN);
    - up = dn = 0 (giá đứng im suốt) -> NaN (chia an toàn, không chia 0).
    """
    d = _series(df, column).diff()
    up = wilder(d.clip(lower=0), window)
    dn = wilder((-d).clip(lower=0), window)
    return _safe_div(100 * up, up + dn).rename(f"rsi{window}")


def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9,
         column: str = "close") -> pd.DataFrame:
    """MACD = EMA(fast) - EMA(slow); signal = EMA(signal) của MACD; hist = MACD - signal.

    Returns:
        DataFrame cột [macd, macd_signal, macd_hist].
    """
    c = _series(df, column)
    line = c.ewm(span=fast, adjust=False).mean() - c.ewm(span=slow, adjust=False).mean()
    sig = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


def stochastic(df: pd.DataFrame, k: int = 14, d: int = 3, smooth_k: int = 1) -> pd.DataFrame:
    """Stochastic Oscillator %K/%D.

    smooth_k=1 (mặc định) = Fast Stochastic, khớp mặc định TradingView và snapshot cũ;
    smooth_k=3 = Slow/Full Stochastic giáo trình (14,3,3).
    Cửa sổ phẳng tuyệt đối (max=min) -> NaN (chia an toàn).

    Returns:
        DataFrame cột [stoch_k, stoch_d].
    """
    _, h, l, c, _ = _ohlcv(df)
    ll = l.rolling(k).min()
    hh = h.rolling(k).max()
    raw = _safe_div(100 * (c - ll), hh - ll)
    k_line = raw.rolling(smooth_k).mean() if smooth_k > 1 else raw
    return pd.DataFrame({"stoch_k": k_line, "stoch_d": k_line.rolling(d).mean()})


def williams_r(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Williams %R = -100 * (HighestHigh - Close) / (HighestHigh - LowestLow).

    Thang [-100, 0]: > -20 quá mua, < -80 quá bán. Cửa sổ phẳng -> NaN.
    """
    _, h, l, c, _ = _ohlcv(df)
    hh = h.rolling(window).max()
    ll = l.rolling(window).min()
    return _safe_div(-100 * (hh - c), hh - ll).rename(f"williams_r{window}")


def roc(df: pd.DataFrame, window: int = 12, column: str = "close") -> pd.Series:
    """Rate of Change (%) = 100 * (close - close_n_trước) / close_n_trước.

    Giá gốc = 0 -> NaN (chia an toàn — theo yêu cầu chung của thư viện).
    """
    s = _series(df, column)
    prev = s.shift(window)
    return _safe_div(100 * (s - prev), prev).rename(f"roc{window}")


# ==========================================================================
# PHẦN 1D — VOLUME
# ==========================================================================

def obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume — cộng dồn volume theo dấu biến động close (đứng giá = 0)."""
    _, _, _, c, v = _ohlcv(df)
    return (np.sign(c.diff()).fillna(0) * v).cumsum().rename("obv")


def cmf(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Chaikin Money Flow = sum(MFV, n) / sum(volume, n), thang [-1, 1].

    MFV = volume * ((close-low)-(high-close))/(high-low).
    Nến phẳng high=low (trần/sàn cứng cả phiên — hay gặp ở VN) -> hệ số = 0
    theo quy ước chuẩn, KHÔNG NaN cả cửa sổ; tổng volume cửa sổ = 0 -> NaN.
    """
    _, h, l, c, v = _ohlcv(df)
    rng = h - l
    mult = _safe_div((c - l) - (h - c), rng).mask(rng == 0, 0.0)
    mfv = (mult * v).rolling(window).sum()
    return _safe_div(mfv, v.rolling(window).sum()).rename(f"cmf{window}")


def mfi(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Money Flow Index — "RSI có volume", thang [0, 100].

    Typical Price = (H+L+C)/3; Raw Money Flow = TP*V, tách dòng dương/âm theo
    chiều TP. Dạng đại số 100*pos/(pos+neg): cửa sổ chỉ toàn tăng -> 100,
    toàn giảm -> 0, đứng im hoàn toàn -> NaN (chia an toàn).
    """
    _, h, l, c, v = _ohlcv(df)
    tp = (h + l + c) / 3
    raw = tp * v
    d = tp.diff()
    pos = raw.where(d > 0, 0.0).where(d.notna())   # nến đầu chưa có chiều -> NaN, không tính vào cửa sổ
    neg = raw.where(d < 0, 0.0).where(d.notna())
    pos_sum = pos.rolling(window).sum()
    neg_sum = neg.rolling(window).sum()
    return _safe_div(100 * pos_sum, pos_sum + neg_sum).rename(f"mfi{window}")


def volume_oscillator(df: pd.DataFrame, fast: int = 5, slow: int = 10) -> pd.Series:
    """Volume Oscillator (%) = 100 * (EMA_vol(fast) - EMA_vol(slow)) / EMA_vol(slow).

    Khớp TradingView (EMA 5/10). Dương = dòng tiền ngắn hạn đang tăng tốc.
    """
    ema_fast = ema(df, fast, "volume")
    ema_slow = ema(df, slow, "volume")
    return _safe_div(100 * (ema_fast - ema_slow), ema_slow).rename(f"vo_{fast}_{slow}")


# ==========================================================================
# PHẦN 1E — VOLATILITY
# ==========================================================================

def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average True Range — làm mượt True Range bằng RMA Wilder (khớp TradingView)."""
    return wilder(true_range(df), window).rename(f"atr{window}")


def bollinger_bands(df: pd.DataFrame, window: int = 20, mult: float = 2.0,
                    column: str = "close") -> pd.DataFrame:
    """Bollinger Bands = SMA(n) ± mult * độ lệch chuẩn TỔNG THỂ (ddof=0).

    ddof=0 đúng sách John Bollinger và khớp ta.stdev TradingView
    (bản cũ dùng ddof=1 của pandas -> band hẹp hơn ~1.3% ở n=20).

    Returns:
        DataFrame cột [bb_mid, bb_up, bb_low, bb_pctb, bb_bandwidth]:
        bb_pctb = vị trí close trong band (0=đáy band, 1=đỉnh band);
        bb_bandwidth = độ rộng band / SMA * 100. Band phẳng -> NaN (chia an toàn).
    """
    c = _series(df, column)
    r = c.rolling(window)                       # tái dùng 1 rolling cho mean + std
    mid = r.mean()
    sd = r.std(ddof=0)
    up, low = mid + mult * sd, mid - mult * sd
    return pd.DataFrame({
        "bb_mid": mid, "bb_up": up, "bb_low": low,
        "bb_pctb": _safe_div(c - low, up - low),
        "bb_bandwidth": _safe_div(100 * (up - low), mid),
    })


def keltner_channel(df: pd.DataFrame, window: int = 20, atr_window: int = 10,
                    mult: float = 2.0) -> pd.DataFrame:
    """Keltner Channel = EMA(close, n) ± mult * ATR(atr_window). Mặc định khớp TradingView (20, 10, 2).

    Returns:
        DataFrame cột [kc_mid, kc_up, kc_low].
    """
    mid = ema(df, window)
    band = mult * atr(df, atr_window)
    return pd.DataFrame({"kc_mid": mid, "kc_up": mid + band, "kc_low": mid - band})


# ==========================================================================
# PHẦN 1F — TREND STRENGTH (ADX / DMI)
# ==========================================================================

def adx(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """ADX + DMI chuẩn Wilder.

    +DM = phần nhô lên của high (khi lớn hơn phần thụt xuống của low và > 0);
    -DM ngược lại. ±DI = 100*RMA(±DM)/RMA(TR); DX = 100*|+DI - -DI|/(+DI + -DI);
    ADX = RMA(DX). ADX > 25 thường coi là xu hướng có lực. +DI = -DI = 0 -> NaN.

    Returns:
        DataFrame cột [plus_di, minus_di, adx].
    """
    _, h, l, _, _ = _ohlcv(df)
    up_move = h.diff()
    down_move = -l.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    tr_smooth = wilder(true_range(df), window)
    plus_di = _safe_div(100 * wilder(plus_dm, window), tr_smooth)
    minus_di = _safe_div(100 * wilder(minus_dm, window), tr_smooth)
    dx = _safe_div(100 * (plus_di - minus_di).abs(), plus_di + minus_di)
    return pd.DataFrame({"plus_di": plus_di, "minus_di": minus_di, "adx": wilder(dx, window)})


# ==========================================================================
# PHẦN 1G — HỖ TRỢ / KHÁNG CỰ
# ==========================================================================

def fibonacci_retracement(df: pd.DataFrame, window: int = 252) -> pd.DataFrame:
    """Các mức Fibonacci hồi quy tính trên đỉnh/đáy TRƯỢT `window` phiên gần nhất.

    Mức r đo nhịp HỒI của xu hướng TĂNG trong cửa sổ: fib_r = high - r*(high-low)
    (fib_236 nông nhất, fib_786 sâu nhất). Với xu hướng giảm, nhịp hồi lên mức r
    chính là cột fib_(1-r) — ví dụ hồi 38.2% của sóng giảm = fib_618.

    Returns:
        DataFrame cột [fib_high, fib_low, fib_236, fib_382, fib_500, fib_618, fib_786].
    """
    _, h, l, _, _ = _ohlcv(df)
    hh = h.rolling(window).max()
    ll = l.rolling(window).min()
    rng = hh - ll
    out = pd.DataFrame({"fib_high": hh, "fib_low": ll})
    for r in (0.236, 0.382, 0.5, 0.618, 0.786):
        out[f"fib_{int(r * 1000)}"] = hh - r * rng
    return out


def pivot_points(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot Points cổ điển tính từ H/L/C của PHIÊN TRƯỚC (không nhìn tương lai).

    P = (H+L+C)/3; R1 = 2P-L; S1 = 2P-H; R2 = P+(H-L); S2 = P-(H-L);
    R3 = H+2(P-L); S3 = L-2(H-P). Nến đầu tiên chưa có phiên trước -> NaN.

    Returns:
        DataFrame cột [pivot, r1, s1, r2, s2, r3, s3].
    """
    _, h, l, c, _ = _ohlcv(df)
    ph, pl, pc = h.shift(), l.shift(), c.shift()
    p = (ph + pl + pc) / 3
    return pd.DataFrame({
        "pivot": p,
        "r1": 2 * p - pl, "s1": 2 * p - ph,
        "r2": p + (ph - pl), "s2": p - (ph - pl),
        "r3": ph + 2 * (p - pl), "s3": pl - 2 * (ph - p),
    })


# ==========================================================================
# PHẦN 1H — ICHIMOKU
# ==========================================================================

def ichimoku(df: pd.DataFrame, tenkan: int = 9, kijun: int = 26,
             senkou_b: int = 52) -> pd.DataFrame:
    """Ichimoku Kinko Hyo (9, 26, 52) — mọi đường đặt đúng dòng thời gian của nó.

    senkou_a/senkou_b đã shift(+kijun) tới trước (giá trị tại dòng t là mây
    VẼ CHO t, tính từ dữ liệu t-kijun trở về) -> so close với mây dùng trực tiếp.
    [CẢNH BÁO LOOKAHEAD] chikou = close.shift(-kijun): dòng t chứa close của
    t+kijun (tương lai). Đúng định nghĩa Ichimoku (đường trễ vẽ lùi) nhưng
    CẤM dùng cột này làm feature backtest tại t.

    Returns:
        DataFrame cột [tenkan, kijun, senkou_a, senkou_b, chikou].
    """
    _, h, l, c, _ = _ohlcv(df)

    def _mid(n: int) -> pd.Series:
        return (h.rolling(n).max() + l.rolling(n).min()) / 2

    tk, kj = _mid(tenkan), _mid(kijun)
    return pd.DataFrame({
        "tenkan": tk, "kijun": kj,
        "senkou_a": ((tk + kj) / 2).shift(kijun),
        "senkou_b": _mid(senkou_b).shift(kijun),
        "chikou": c.shift(-kijun),
    })


# ==========================================================================
# PHẦN 1I — SMART MONEY CONCEPTS (PROXY)
# Các hàm dưới đây là PROXY máy móc của khái niệm SMC vốn mang tính chủ quan.
# Giới hạn chung: 1 khung thời gian, không phân biệt vùng premium/discount,
# không theo dõi vùng đã bị "mitigate" — xem docstring từng hàm.
# ==========================================================================

def fair_value_gap(df: pd.DataFrame, min_gap_pct: float = 0.0) -> pd.DataFrame:
    """Fair Value Gap (FVG/imbalance) — mẫu 3 nến, cờ đặt tại nến THỨ BA (nến t).

    FVG tăng: low(t) > high(t-2) — khoảng trống giá chưa được lấp giữa 2 nến;
    FVG giảm: high(t) < low(t-2). `min_gap_pct` lọc gap nhỏ (% so với close).
    Không theo dõi gap đã lấp — người dùng tự so giá sau đó với biên gap.

    Returns:
        DataFrame cột [fvg_bull, fvg_bull_top, fvg_bull_bottom,
                       fvg_bear, fvg_bear_top, fvg_bear_bottom]
        (cờ bool; biên gap chỉ có giá trị tại nến cờ, còn lại NaN).
    """
    _, h, l, c, _ = _ohlcv(df)
    h2, l2 = h.shift(2), l.shift(2)
    gap_ok_bull = _safe_div(100 * (l - h2), c) >= min_gap_pct
    gap_ok_bear = _safe_div(100 * (l2 - h), c) >= min_gap_pct
    bull = (l > h2) & gap_ok_bull
    bear = (h < l2) & gap_ok_bear
    return pd.DataFrame({
        "fvg_bull": bull.fillna(False),
        "fvg_bull_top": l.where(bull), "fvg_bull_bottom": h2.where(bull),
        "fvg_bear": bear.fillna(False),
        "fvg_bear_top": l2.where(bear), "fvg_bear_bottom": h.where(bear),
    })


def order_block(df: pd.DataFrame, atr_window: int = 14, mult: float = 1.5) -> pd.DataFrame:
    """Order Block (PROXY) — nến ngược chiều cuối cùng trước 1 nến displacement.

    OB tăng: nến t-1 GIẢM (close<open), nến t có thân >= mult*ATR và close
    vượt high(t-1). Cờ đặt tại nến XÁC NHẬN t (không nhìn tương lai); vùng OB
    = high/low của nến t-1. OB giảm đối xứng.
    PROXY vì: SMC gốc còn đòi quét thanh khoản trước đó, OB chưa mitigated,
    và displacement tạo FVG — ở đây chỉ dùng ngưỡng thân nến theo ATR.

    Returns:
        DataFrame cột [ob_bull, ob_bull_top, ob_bull_bottom,
                       ob_bear, ob_bear_top, ob_bear_bottom].
    """
    o, h, l, c, _ = _ohlcv(df)
    body = c - o
    a = atr(df, atr_window)
    prev_down = c.shift() < o.shift()
    prev_up = c.shift() > o.shift()
    bull = prev_down & (body >= mult * a) & (c > h.shift())
    bear = prev_up & (-body >= mult * a) & (c < l.shift())
    return pd.DataFrame({
        "ob_bull": bull.fillna(False),
        "ob_bull_top": h.shift().where(bull), "ob_bull_bottom": l.shift().where(bull),
        "ob_bear": bear.fillna(False),
        "ob_bear_top": h.shift().where(bear), "ob_bear_bottom": l.shift().where(bear),
    })


def market_structure(df: pd.DataFrame, n: int = 2) -> pd.DataFrame:
    """Cấu trúc thị trường theo swing fractal: BOS + CHoCH (proxy SMC).

    Mức swing dùng để so là fractal ĐÃ XÁC NHẬN (trễ n nến — không lookahead,
    khác cột swing_high/swing_low center=True của snapshot). Phá vỡ tính bằng
    CLOSE vượt mức (body break, chuẩn "confirmed break", bỏ qua râu nến):
    - BOS  = phá vỡ THUẬN xu hướng hiện tại (tiếp diễn);
    - CHoCH = phá vỡ NGƯỢC xu hướng hiện tại (cảnh báo đảo chiều sớm).
    Phá vỡ đầu tiên khi chưa có xu hướng tính là BOS.

    Returns:
        DataFrame cột [bos_up, bos_down, choch_up, choch_down (bool),
                       ms_trend (+1/-1/NaN), swing_high_level, swing_low_level].
    """
    _, _, _, c, _ = _ohlcv(df)
    fr = fractal(df, n)
    # mức swing gần nhất ĐÃ BIẾT tại thời điểm t (pivot xác nhận trễ n nến)
    sh_level = fr["fractal_high"].shift(n).ffill()
    sl_level = fr["fractal_low"].shift(n).ffill()

    above = (c > sh_level).fillna(False)
    below = (c < sl_level).fillna(False)
    break_up = above & ~above.shift(fill_value=False)      # sự kiện: BẮT ĐẦU vượt đỉnh swing
    break_down = below & ~below.shift(fill_value=False)

    ev = pd.Series(0, index=df.index)
    ev[break_up] = 1
    ev[break_down & ~break_up] = -1
    trend = ev.replace(0, np.nan).ffill()                  # xu hướng SAU sự kiện của dòng t
    prev = trend.shift()                                   # xu hướng TRƯỚC sự kiện (NaN != x -> True)
    return pd.DataFrame({
        "bos_up": break_up & (prev != -1),
        "bos_down": break_down & (prev != 1),
        "choch_up": break_up & (prev == -1),
        "choch_down": break_down & (prev == 1),
        "ms_trend": trend,
        "swing_high_level": sh_level, "swing_low_level": sl_level,
    })


def break_of_structure(df: pd.DataFrame, n: int = 2) -> pd.DataFrame:
    """Break of Structure — lát cắt [bos_up, bos_down, ms_trend] của market_structure()."""
    return market_structure(df, n)[["bos_up", "bos_down", "ms_trend"]]


def change_of_character(df: pd.DataFrame, n: int = 2) -> pd.DataFrame:
    """Change of Character — lát cắt [choch_up, choch_down, ms_trend] của market_structure()."""
    return market_structure(df, n)[["choch_up", "choch_down", "ms_trend"]]


# ==========================================================================
# PHẦN 1J — MẪU HÌNH (FRACTAL / ZIGZAG / ELLIOTT PROXY)
# ==========================================================================

def fractal(df: pd.DataFrame, n: int = 2) -> pd.DataFrame:
    """Fractal Williams — đỉnh/đáy cục bộ giữa cửa sổ 2n+1 nến (center=True).

    [LOOKAHEAD] Pivot tại t chỉ XÁC NHẬN sau n nến (t+n). Screening live dùng
    trực tiếp được (đây là đỉnh/đáy hình học chuẩn); backtest BẮT BUỘC
    shift(n) trước khi mô phỏng. n nến cuối luôn NaN — là độ trễ tự nhiên.

    Returns:
        DataFrame cột [fractal_high, fractal_low] (giá tại pivot, còn lại NaN).
    """
    _, h, l, _, _ = _ohlcv(df)
    win = 2 * n + 1
    return pd.DataFrame({
        "fractal_high": h.where(h == h.rolling(win, center=True).max()),
        "fractal_low": l.where(l == l.rolling(win, center=True).min()),
    })


def zigzag(df: pd.DataFrame, pct: float = 5.0) -> pd.DataFrame:
    """ZigZag — pivot đỉnh/đáy xen kẽ, đảo chiều khi giá đi ngược >= pct% từ cực trị.

    Đỉnh dò trên HIGH, đáy dò trên LOW. Vòng lặp tuần tự là BẢN CHẤT của ZigZag
    (pivot sau phụ thuộc pivot trước) — không vector hóa trọn vẹn được; O(N) một
    lượt, chỉ dùng cho phân tích từng mã, không nằm trong pipeline quét toàn sàn.
    [LOOKAHEAD] Pivot tại t chỉ xác nhận khi giá ĐÃ đảo >= pct% (nhiều nến sau t)
    — cấm dùng làm tín hiệu vào lệnh tại t khi backtest. Chân cuối chưa xác nhận
    không được ghi nhận. Yêu cầu giá > 0 (ngưỡng phần trăm).

    Returns:
        DataFrame cột [zz_pivot (giá tại pivot, còn lại NaN), zz_dir (+1 đỉnh / -1 đáy)].
    """
    h = _series(df, "high").to_numpy(dtype=float)
    l = _series(df, "low").to_numpy(dtype=float)
    n = len(h)
    piv_i: list = []
    piv_v: list = []
    piv_d: list = []
    if n > 1:
        thr = pct / 100.0
        direction = 0                       # 0 chưa rõ, +1 đang dò đỉnh, -1 đang dò đáy
        hi_i, hi_v = 0, h[0]
        lo_i, lo_v = 0, l[0]
        for t in range(1, n):
            if direction == 0:
                if h[t] > hi_v:
                    hi_i, hi_v = t, h[t]
                if l[t] < lo_v:
                    lo_i, lo_v = t, l[t]
                if h[t] >= lo_v * (1 + thr):        # chân TĂNG đầu tiên xác nhận -> pivot đáy
                    piv_i.append(lo_i); piv_v.append(lo_v); piv_d.append(-1)
                    direction, hi_i, hi_v = 1, t, h[t]
                elif l[t] <= hi_v * (1 - thr):      # chân GIẢM đầu tiên xác nhận -> pivot đỉnh
                    piv_i.append(hi_i); piv_v.append(hi_v); piv_d.append(1)
                    direction, lo_i, lo_v = -1, t, l[t]
            elif direction == 1:
                if h[t] > hi_v:
                    hi_i, hi_v = t, h[t]
                elif l[t] <= hi_v * (1 - thr):      # đảo xuống đủ % -> chốt pivot đỉnh
                    piv_i.append(hi_i); piv_v.append(hi_v); piv_d.append(1)
                    direction, lo_i, lo_v = -1, t, l[t]
            else:
                if l[t] < lo_v:
                    lo_i, lo_v = t, l[t]
                elif h[t] >= lo_v * (1 + thr):      # đảo lên đủ % -> chốt pivot đáy
                    piv_i.append(lo_i); piv_v.append(lo_v); piv_d.append(-1)
                    direction, hi_i, hi_v = 1, t, h[t]
    zz = np.full(n, np.nan)
    zd = np.full(n, np.nan)
    if piv_i:
        zz[piv_i] = piv_v
        zd[piv_i] = piv_d
    return pd.DataFrame({"zz_pivot": zz, "zz_dir": zd}, index=df.index)


def elliott_wave_proxy(df: pd.DataFrame, pct: float = 5.0) -> pd.DataFrame:
    """Đếm sóng Elliott (PROXY THÔ) trên pivot ZigZag — chỉ nhận diện mẫu GẦN NHẤT.

    Impulse (6 pivot cuối, kiểm 3 luật cứng): sóng 2 không thủng gốc sóng 1;
    sóng 4 không chồng lấn đỉnh sóng 1; sóng 3 không phải sóng ngắn nhất
    (thêm: sóng 3 vượt đỉnh sóng 1, sóng 5 vượt đỉnh sóng 3 — bỏ qua truncation).
    Nếu không phải impulse: thử A-B-C trên 4 pivot cuối (B hồi <100% A,
    C vượt điểm cuối A).
    [GIỚI HẠN] Elliott thật cần đa khung thời gian, sóng lồng sóng, tỷ lệ Fib,
    và vốn dĩ chủ quan — proxy này chỉ là CỜ NGỮ CẢNH tham khảo, không phải
    tín hiệu giao dịch; kế thừa toàn bộ lookahead của zigzag().

    Returns:
        DataFrame cột [zz_pivot, zz_dir, ew_wave ("1".."5"/"A"/"B"/"C" tại pivot),
                       ew_phase ("impulse_up/down", "corrective_up/down",
                       "undetermined" — điền từ nến hoàn tất mẫu về sau)].
    """
    zz = zigzag(df, pct)
    idx = np.flatnonzero(zz["zz_dir"].notna().to_numpy())
    vals = zz["zz_pivot"].to_numpy()[idx]
    dirs = zz["zz_dir"].to_numpy()[idx]

    wave = np.full(len(df), None, dtype=object)
    phase = np.full(len(df), "undetermined", dtype=object)

    def _is_impulse(v: np.ndarray, sign: int) -> bool:
        w1, w3, w5 = sign * (v[1] - v[0]), sign * (v[3] - v[2]), sign * (v[5] - v[4])
        return (min(w1, w3, w5) > 0
                and sign * (v[2] - v[0]) > 0        # sóng 2 giữ trên gốc sóng 1
                and sign * (v[4] - v[1]) > 0        # sóng 4 không chồng lấn sóng 1
                and sign * (v[3] - v[1]) > 0        # sóng 3 vượt đỉnh sóng 1
                and sign * (v[5] - v[3]) > 0        # sóng 5 vượt đỉnh sóng 3
                and not (w3 < w1 and w3 < w5))      # sóng 3 không ngắn nhất

    label = None
    if len(idx) >= 6:
        v6, i6, sign = vals[-6:], idx[-6:], int(dirs[-1])   # kết thúc đỉnh -> impulse tăng
        if _is_impulse(v6, sign):
            label = "impulse_up" if sign == 1 else "impulse_down"
            for k, i in enumerate(i6[1:], start=1):
                wave[i] = str(k)
            phase[i6[-1]:] = label
    if label is None and len(idx) >= 4:
        v4, i4 = vals[-4:], idx[-4:]
        s_a = 1 if v4[1] > v4[0] else -1                    # hướng chân A
        if s_a * (v4[0] - v4[2]) > 0 and s_a * (v4[3] - v4[1]) > 0:  # B hồi <100% A, C vượt cuối A
            label = "corrective_up" if s_a == 1 else "corrective_down"
            for name, i in zip(("A", "B", "C"), i4[1:]):
                wave[i] = name
            phase[i4[-1]:] = label

    out = zz.copy()
    out["ew_wave"] = wave
    out["ew_phase"] = phase
    return out


# ==========================================================================
# PHẦN 2 — PIPELINE SNAPSHOT (hành vi & schema CSV giữ nguyên như bản cũ)
# ==========================================================================

def load(conn, ticker):
    df = pd.read_sql("SELECT date, open, high, low, close, volume FROM ohlcv WHERE ticker=? ORDER BY date",
                     conn, params=(ticker,))
    if len(df) < MIN_BARS:
        return None
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")

def ret(s, n):
    return (s / s.shift(n) - 1) * 100

def add_indicators(df):
    """Bộ chỉ báo cho snapshot — GỌI THƯ VIỆN Phần 1, tên cột giữ nguyên bản cũ."""
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]

    # Trend
    for n in (10, 20, 50, 200):
        df[f"sma{n}"] = sma(df, n)
        df[f"ema{n}"] = ema(df, n)

    # RSI(14) — chuẩn Wilder (RMA), khớp TradingView; mã chỉ-tăng ra 100 thay vì NaN
    df["rsi14"] = rsi(df, 14)

    # MACD(12,26,9)
    m = macd(df)
    df["macd"], df["macd_signal"], df["macd_hist"] = m["macd"], m["macd_signal"], m["macd_hist"]

    # Bollinger(20,2) — ddof=0 chuẩn sách/TradingView (bản cũ ddof=1 hơi hẹp band)
    bb = bollinger_bands(df, 20, 2.0)
    df["bb_up"], df["bb_low"], df["bb_pctb"] = bb["bb_up"], bb["bb_low"], bb["bb_pctb"]

    # ATR(14) — chuẩn Wilder (khớp TradingView)
    df["atr14"] = atr(df, 14)
    df["atr_pct"] = _safe_div(100 * df["atr14"], c)

    # Stochastic(14,3) — fast (%K thô, khớp mặc định TradingView và snapshot cũ)
    st_df = stochastic(df, 14, 3, smooth_k=1)
    df["stoch_k"], df["stoch_d"] = st_df["stoch_k"], st_df["stoch_d"]

    # Volume + THANH KHOẢN (GTGD bình quân 20 phiên, tỷ đồng) — lọc rác UPCoM
    df["vol_sma20"] = v.rolling(20).mean()
    df["rel_vol"] = _safe_div(v, df["vol_sma20"])
    df["obv"] = obv(df)
    df["gtgd20_ty"] = (c * v).rolling(20).mean() / 1e9

    # 52 tuần
    df["high_52w"] = h.rolling(252, min_periods=MIN_BARS).max()
    df["low_52w"] = l.rolling(252, min_periods=MIN_BARS).min()
    df["pct_from_52w_high"] = (c / df["high_52w"] - 1) * 100
    df["pct_above_52w_low"] = (c / df["low_52w"] - 1) * 100

    # Returns cho RS
    for n, nm in ((21, "1m"), (63, "3m"), (126, "6m"), (252, "12m")):
        df[f"ret_{nm}"] = ret(c, n)

    # =========================================================================
    # CẤU TRÚC SWING FRACTAL (center=True)
    # 1. LIVE SCREENING: center=True là ĐÚNG — đỉnh/đáy hình học chuẩn. Với n=2, hai dòng cuối
    #    (T, T-1) luôn NaN; structure() lấy swing ĐÃ XÁC NHẬN gần nhất (T-2) = độ trễ xác nhận
    #    tự nhiên, KHÔNG phải lỗi.
    # 2. BACKTEST: mang cột này đi backtest trực tiếp sẽ dính Lookahead Bias (tại t đã biết
    #    t+1, t+2). Bắt buộc shift trước khi mô phỏng: df["swing_high"].shift(2).
    # =========================================================================
    fr = fractal(df, 2)
    df["swing_high"] = fr["fractal_high"]
    df["swing_low"] = fr["fractal_low"]

    if FULL_TA:
        try:
            import pandas_ta as pta
            df.ta.strategy("all")   # ~130 chỉ báo; CHẬM: có thể mất nhiều GIỜ với toàn sàn
        except Exception as e:
            print(f" [pandas_ta] Bỏ qua: {str(e)[:60]}")
    return df

def load_metadata(conn):
    """Kéo lớp metadata (do meta_sync.py cào) để LEFT JOIN vào bảng lọc theo ticker.
    Mã chưa sync metadata sẽ là NaN — không loại mã nào.
    [BẪY POINT-IN-TIME] metadata là trạng thái HÔM NAY (room ngoại, P/E, margin_status...).
    CHỈ dùng cho lọc LIVE. JOIN các cột này vào giá QUÁ KHỨ để backtest là SAI
    (survivorship bias + lookahead bias)."""
    cols = ["ticker", "exchange", "industry", "foreign_room_pct", "pe", "pb", "roe",
            "free_float_est", "margin_status"]
    has = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadata'").fetchone()
    if not has:
        print(" [meta] Chưa có bảng metadata (chạy meta_sync.py trước) -> các cột metadata sẽ trống")
        return pd.DataFrame(columns=cols)
    metadata = pd.read_sql(f"SELECT {', '.join(cols)} FROM metadata", conn)
    # PK ticker đã ngăn trùng ở DB; vẫn phòng thủ khi đọc để merge không thể nhân đôi
    # snapshot nếu schema cũ/bản nhập tay từng tồn tại bản ghi lặp.
    metadata["ticker"] = metadata["ticker"].astype(str).str.upper().str.strip()
    metadata["exchange"] = metadata["exchange"].apply(normalize_exchange)
    return metadata.drop_duplicates(subset="ticker", keep="last")


EXCHANGE_ALIASES = {
    "HSX": "HSX", "HOSE": "HSX", "HCM": "HSX",
    "HNX": "HNX", "UPCOM": "UPCOM", "DELISTED": "DELISTED",
}


def normalize_exchange(value):
    if pd.isna(value):
        return value
    raw = str(value).strip().upper()
    return EXCHANGE_ALIASES.get(raw, raw or None)

def load_instrument_master(conn):
    """Latest complete forward-only listing snapshot, or empty (fail-closed)."""
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='instrument_master_records'").fetchone()
    if not exists:
        return pd.DataFrame(columns=["ticker", "instrument_type", "listing_exchange", "listing_source", "listing_snapshot_hash"])
    return pd.read_sql("""SELECT r.symbol AS ticker, r.instrument_type, r.exchange AS listing_exchange,
                         r.source_name AS listing_source, s.raw_hash AS listing_snapshot_hash
                  FROM instrument_master_records r JOIN instrument_master_snapshots s ON s.snapshot_id=r.snapshot_id
                  WHERE r.snapshot_id=(SELECT snapshot_id FROM instrument_master_snapshots
                                       WHERE is_complete=1 ORDER BY fetched_at DESC LIMIT 1)""", conn)
def market_breadth(s):
    """ĐỘ RỘNG THỊ TRƯỜNG tính từ chính DB, không cần nguồn ngoài.
    Chỉ đếm mã có nến ĐÚNG phiên gần nhất toàn thị trường (mã ngừng GD/dữ liệu cũ
    bị loại khỏi thống kê tăng/giảm để không làm nhiễu).
    Dòng đầu = ALL (toàn thị trường), các dòng sau = từng ngành (ICB từ metadata),
    xếp theo sức mạnh RS trung bình giảm dần."""
    dmax = s["date"].max()
    live = s[s["live_universe_status"] == "live"].copy()

    def one(g, name):
        chg = pd.to_numeric(g["chg_today_pct"], errors="coerce")
        ma = g["above_sma200"].dropna()
        rs = pd.to_numeric(g["rs_rating"], errors="coerce")
        return {"group": name, "date": dmax, "n_symbols": int(len(g)),
                "n_up": int((chg > 0).sum()), "n_down": int((chg < 0).sum()),
                "n_flat": int((chg == 0).sum()),
                "pct_above_ma200": round(float(ma.astype(bool).mean()) * 100, 1) if len(ma) else None,
                "avg_rs_rating": round(float(rs.mean()), 1) if rs.notna().any() else None,
                "avg_ret_1m": round(float(pd.to_numeric(g["ret_1m"], errors="coerce").mean()), 1)}

    rows = [one(live, "ALL")]
    live["industry"] = live["industry"].fillna("(chưa rõ ngành)")
    for name, g in live.groupby("industry"):
        rows.append(one(g, name))
    out = pd.DataFrame(rows)
    head, tail = out.iloc[:1], out.iloc[1:].sort_values("avg_rs_rating", ascending=False)
    return pd.concat([head, tail], ignore_index=True)

def structure(df):
    sh = df["swing_high"].dropna()
    sl = df["swing_low"].dropna()
    if len(sh) < 2 or len(sl) < 2:
        return "n/a", np.nan
    hh = sh.iloc[-1] > sh.iloc[-2]; hl = sl.iloc[-1] > sl.iloc[-2]
    lh = sh.iloc[-1] < sh.iloc[-2]; ll = sl.iloc[-1] < sl.iloc[-2]
    st = "up" if (hh and hl) else "down" if (lh and ll) else "side"
    dist = (df["close"].iloc[-1] / sl.iloc[-1] - 1) * 100   # % trên swing low hỗ trợ gần nhất
    return st, dist

def main():
    conn = sqlite3.connect(DB_PATH)
    tickers = [r[0] for r in conn.execute("SELECT DISTINCT ticker FROM ohlcv").fetchall()]
    print(f"[indicators] Tính cục bộ {len(tickers)} mã | FULL_TA={FULL_TA}")

    write_full = WRITE_FULL_HISTORY or FULL_TA   # full mà không ghi thì tính xong vứt -> vô nghĩa
    full_dir = os.path.join(OUT_DIR, "indicators_full")
    if write_full:
        os.makedirs(full_dir, exist_ok=True)

    snap = []
    for i, tk in enumerate(tickers, 1):
        if tk in INDEX_SYMBOLS:
            continue                              # chỉ số không phải cổ phiếu -> loại khỏi bảng lọc
        df = load(conn, tk)
        if df is None:
            continue
        df = add_indicators(df)
        last = df.iloc[-1]
        st, dist = structure(df)

        snap.append({
            "ticker": tk,
            "date": df.index[-1].strftime("%Y-%m-%d"),
            "close": last["close"],
            "chg_today_pct": round((last["close"] / df["close"].iloc[-2] - 1) * 100, 2),  # cho độ rộng thị trường
            "gtgd20_ty": round(last["gtgd20_ty"], 3) if pd.notna(last["gtgd20_ty"]) else None,
            "rel_vol": round(last["rel_vol"], 2) if pd.notna(last["rel_vol"]) else None,
            "rsi14": round(last["rsi14"], 1),
            "macd_hist": round(last["macd_hist"], 1),
            "bb_pctb": round(last["bb_pctb"], 2),
            "atr_pct": round(last["atr_pct"], 2),
            "above_sma50": bool(last["close"] > last["sma50"]) if pd.notna(last["sma50"]) else None,
            "above_sma200": bool(last["close"] > last["sma200"]) if pd.notna(last["sma200"]) else None,
            "golden_cross": bool(last["sma50"] > last["sma200"])
                            if pd.notna(last["sma50"]) and pd.notna(last["sma200"]) else None,
            "pct_from_52w_high": round(last["pct_from_52w_high"], 1),
            "near_52w_high": bool(last["pct_from_52w_high"] >= -3)
                             if pd.notna(last["pct_from_52w_high"]) else None,
            "pct_above_52w_low": round(last["pct_above_52w_low"], 1),
            "ret_1m": round(last["ret_1m"], 1),
            "ret_3m": round(last["ret_3m"], 1),
            "ret_6m": round(last["ret_6m"], 1),
            "ret_12m": round(last["ret_12m"], 1) if pd.notna(last["ret_12m"]) else None,
            "structure": st,
            "dist_swing_low_pct": round(dist, 1) if pd.notna(dist) else None
        })

        if write_full:
            # Mỗi mã 1 file parquet -> miễn nhiễm lệch schema giữa các mã; PQ đọc cả thư mục được
            df.reset_index().assign(ticker=tk).to_parquet(
                os.path.join(full_dir, f"{tk}.parquet"), index=False)

        if i % 100 == 0:
            print(f"   Đã xử lý: {i}/{len(tickers)} mã")
    meta_df = load_metadata(conn)   # lớp metadata của meta_sync.py (bảng `metadata`, KHÔNG phải `meta`)
    instrument_master = load_instrument_master(conn)
    conn.close()

    if not snap:
        print(" [Lỗi] Không có dữ liệu hợp lệ để xuất bảng."); return

    s = pd.DataFrame(snap)

    # LIVE = có nến đúng phiên gần nhất toàn hệ thống (cùng định nghĩa dùng trong market_breadth()).
    # Mã ngừng giao dịch/dữ liệu cũ vẫn giữ trong bảng đầy đủ (tương thích cũ) nhưng KHÔNG được xếp
    # hạng RS chung với mã live -> tránh "RS ảo" của mã chết chiếm đầu bảng khi sort theo rs_rating.
    s = s.merge(meta_df, on="ticker", how="left")
    s = evaluate_live_universe(s, instrument_master)
    dmax = s["reference_market_date"].dropna().max()

    # RS rating: percentile return có trọng số; mã mới <12m xếp tạm theo ret_3m (thay vì NaN).
    # CHỈ xếp hạng percentile trong tập LIVE — mã không live -> rs_rating để trống (NA), không tính.
    blend = (0.4 * s["ret_3m"] + 0.2 * s["ret_6m"] + 0.4 * s["ret_12m"])
    blend = blend.fillna(s["ret_3m"])
    s["rs_rating"] = pd.Series(pd.NA, index=s.index, dtype="Int64")
    live_idx = s.index[s["is_live"]]
    s.loc[live_idx, "rs_rating"] = (blend.loc[live_idx].rank(pct=True) * 98 + 1).round().astype("Int64")
    s = s.sort_values("rs_rating", ascending=False)

    # LEFT JOIN lớp metadata: mã bị blacklist CHỈ GẮN CỜ qua margin_status, KHÔNG xóa
    # (tự lọc khi dùng, không mất dữ liệu). Cảnh báo point-in-time: xem load_metadata().
    if s["ticker"].duplicated().any():
        dupes = s.loc[s["ticker"].duplicated(keep=False), "ticker"].unique().tolist()
        raise RuntimeError(f"Metadata merge tạo ticker trùng: {dupes[:20]}")
    # Sentinel dữ liệu công khai: đây là assertion pipeline, không phải ngoại lệ
    # hiển thị. Mọi mã vẫn đi qua cùng normalize_exchange ở trên.
    hpg = s[s["ticker"] == "HPG"]
    if len(hpg) != 1 or normalize_exchange(hpg.iloc[0]["exchange"]) != "HSX":
        raise RuntimeError("Sentinel HPG phải có đúng 1 dòng thuộc HSX/HOSE")

    out = os.path.join(OUT_DIR, "screen_snapshot.csv")
    s.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[indicators] Bảng lọc {len(s)} mã -> {out}")

    # Bản chỉ-live: nguồn AN TOÀN cho consumer bên ngoài (export_ai_bundle.py, AI ngoài, dashboard) —
    # không còn mã chết lẫn vào đầu bảng RS. screen_snapshot.csv vẫn giữ nguyên để tương thích cũ.
    live_out = os.path.join(OUT_DIR, "screen_snapshot_live.csv")
    s[s["is_live"]].to_csv(live_out, index=False, encoding="utf-8-sig")
    print(f"[indicators] Bảng lọc LIVE {int(s['is_live'].sum())}/{len(s)} mã (phiên {dmax}) -> {live_out}")

    breadth = market_breadth(s)
    out_b = os.path.join(OUT_DIR, "market_breadth.csv")
    breadth.to_csv(out_b, index=False, encoding="utf-8-sig")
    print(f"[indicators] Độ rộng thị trường ({len(breadth) - 1} ngành) -> {out_b}")
    print("  Lọc CANSLIM gợi ý: is_live & rs_rating>=80 & above_sma200 & pct_from_52w_high>=-15 & rel_vol>=1 & gtgd20_ty>=3")
    print("  Lọc luật gợi ý thêm: margin_status trống & foreign_room_pct>0")

if __name__ == "__main__":
    main()
