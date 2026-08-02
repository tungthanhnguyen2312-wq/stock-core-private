import os
import sys
import json
import sqlite3
import argparse
from datetime import timedelta
import numpy as np
import pandas as pd

from candlestick_patterns import atomic_write_snapshot, build_snapshot
from runtime_paths import runtime_root
from source_timestamp import resolve_source_datetime, source_timestamp

# Console Windows mặc định cp1252 -> vỡ khi in tiếng Việt
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==========================================
# CANDLE + SMC SCAN — quét mẫu nến & vùng SMC phiên MỚI NHẤT, xuất cho dashboard
# ==========================================
# Nguồn dữ liệu: 100%% CỤC BỘ (ohlcv + metadata trong vn_stock.db, screen_snapshot.csv).
# KHÔNG fetch mạng, KHÔNG TA-Lib/pandas-ta (không có TA-Lib thì pandas-ta chỉ nhận diện
# được Doji, các mẫu khác trả rỗng ÂM THẦM — đã kiểm chứng 2026-07-09).
#
# TÁI SỬ DỤNG từ pipeline (không tính lại): rs_rating/rel_vol/atr_pct/industry/margin_status
# lấy từ screen_snapshot.csv; ATR14 tuyệt đối suy từ atr_pct*close/100. Swing dùng ĐÚNG
# quy ước fractal n=2 (center) của vn_indicators.py — trễ xác nhận 2 nến là bản chất.
#
# [BẪY PHẢI NHỚ]
# - Mẫu nến/vùng SMC đứng một mình là NHIỄU — tín hiệu đáng xem nhất là CONFLUENCE
#   (nến đảo chiều + đang nằm trong/cạnh OB-FVG cùng hướng) TRÊN NỀN mã sạch, thanh khoản thật.
# - Định nghĩa OB/FVG bên dưới là CƠ HỌC THUẦN (không có yếu tố "cảm nến" của trader SMC);
#   ngưỡng là quy ước, chỉnh hằng số bên dưới.
# - Chỉ quét mã có nến ĐÚNG phiên quét (mã ngừng GD không vào kết quả).

def resolve_runtime_paths(cwd=None):
    """Return mutable candle-scan paths under the configured runtime root."""
    root = runtime_root(cwd or os.getcwd())
    data_dir = root / "data"
    return (
        root,
        root / "vn_stock.db",
        root / "ta_signals.csv",
        root / "ta_signals.json",
        root / "screen_snapshot.csv",
        root / "market_breadth.csv",
        data_dir,
        data_dir / "candlestick_patterns.json",
        data_dir / "candlestick_patterns.js",
    )


RUNTIME_ROOT, DB_PATH, OUT_CSV, OUT_JSON, SNAPSHOT_PATH, MARKET_BREADTH_PATH, DATA_DIR, PATTERN_OUT_JSON, PATTERN_OUT_JS = resolve_runtime_paths()
WATCHLIST = ["POW", "HPG", "SSI", "PAN", "EVF"]  # luôn có mặt trong dashboard, kể cả không tín hiệu
# [VÁ P1-3] POW thiếu khỏi WATCHLIST — đã ghi nhận ở STOCK_ANALYSIS_MASTER_PLAN.md mục 7 (P1-3).
INDEX_SYMBOLS = ["VNINDEX", "HNXINDEX", "UPCOMINDEX"]

LOOKBACK_CAL_DAYS = 40      # ~25 phiên: đủ cho mẫu 3 nến + swing + FVG/OB gần đây
MIN_BARS = 8

# --- Ngưỡng mẫu nến (quy ước, chỉnh tại đây) ---
DOJI_BODY_MAX = 0.10
PIN_SHADOW_RATIO = 2.0      # pinbar: bóng dài >= 2 lần thân
PIN_OTHER_MAX = 0.20        # ...và bóng còn lại <= 20% biên độ
STAR_BODY1_MIN = 0.60
STAR_BODY2_MAX = 0.40

# --- Ngưỡng SMC ---
OB_LOOKBACK = 10            # tìm nến Order Block trong 10 nến trước cú BOS
FVG_ATR_TOL = 1.0           # "gần FVG" = cách mép gap <= 1 x ATR14
DIV_YIELD_MIN = 7.0         # góc tích sản: tỷ suất cổ tức >= 7%/năm

# --- Ngưỡng S/R + volume confirmation (mục 5 nâng cấp workflow, 2026-07-17 — bỏ Gemini) ---
SR_TOUCH_TOLERANCE_ATR = 1.0   # 2 swing cùng "1 vùng" hỗ trợ/kháng cự nếu cách nhau <= 1 x ATR14
VOL_CONFIRM_MULT = 1.5         # KL phiên >= 1.5 x KL trung bình cửa sổ quét mới coi là "xác nhận"

PATTERN_DIRECTION = {
    "doji": 0, "inside_bar": 0,
    "hammer": 1, "bullish_engulfing": 1, "morning_star": 1,
    "shooting_star": -1, "bearish_engulfing": -1, "evening_star": -1,
}
BULL_PATTERNS = {"hammer", "bullish_engulfing", "morning_star"}
BEAR_PATTERNS = {"shooting_star", "bearish_engulfing", "evening_star"}

# ==========================================
# MẪU NẾN (vector hóa toàn thị trường)
# ==========================================
def detect_patterns(df):
    """Quy ước: thân=|close-open|; bóng trên=high-max(o,c); bóng dưới=min(o,c)-low."""
    g = df.groupby("ticker", sort=False)
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l

    o1, c1 = g["open"].shift(1), g["close"].shift(1)
    h1, l1 = g["high"].shift(1), g["low"].shift(1)
    o2, c2 = g["open"].shift(2), g["close"].shift(2)
    h2, l2 = g["high"].shift(2), g["low"].shift(2)
    body1 = (c1 - o1).abs()
    body2_ = (c2 - o2).abs()
    rng2 = (h2 - l2).replace(0, np.nan)

    down_before = g["close"].shift(1) < g["close"].shift(6)
    up_before = g["close"].shift(1) > g["close"].shift(6)
    down_before3 = g["close"].shift(3) < g["close"].shift(7)
    up_before3 = g["close"].shift(3) > g["close"].shift(7)

    bull, bear = c > o, c < o
    bull1, bear1 = c1 > o1, c1 < o1
    bear2, bull2 = c2 < o2, c2 > o2

    # Doji: thân <= 10% biên độ (do dự)
    df["doji"] = (body <= DOJI_BODY_MAX * rng).fillna(False)
    # Pinbar tăng (hammer): bóng dưới dài sau xu hướng giảm — từ chối giá thấp
    df["hammer"] = ((lower >= PIN_SHADOW_RATIO * body) & (upper <= PIN_OTHER_MAX * rng)
                    & (body > 0) & down_before).fillna(False)
    # Pinbar giảm (shooting star): bóng trên dài sau xu hướng tăng — từ chối giá cao
    df["shooting_star"] = ((upper >= PIN_SHADOW_RATIO * body) & (lower <= PIN_OTHER_MAX * rng)
                           & (body > 0) & up_before).fillna(False)
    # Inside bar: nến nằm trọn trong biên nến trước — nén tích lũy, trung tính
    df["inside_bar"] = ((h < h1) & (l > l1)).fillna(False)
    # Engulfing: thân nuốt trọn thân nến trước, hai nến ngược màu
    df["bullish_engulfing"] = (bear1 & bull & (o <= c1) & (c >= o1)
                               & (body > body1) & (body1 > 0)).fillna(False)
    df["bearish_engulfing"] = (bull1 & bear & (o >= c1) & (c <= o1)
                               & (body > body1) & (body1 > 0)).fillna(False)
    # Star 3 nến: quyết đoán -> do dự -> đảo chiều đóng quá nửa thân nến 1
    df["morning_star"] = (bear2 & (body2_ >= STAR_BODY1_MIN * rng2)
                          & (body1 <= STAR_BODY2_MAX * body2_)
                          & bull & (c > (o2 + c2) / 2) & down_before3).fillna(False)
    df["evening_star"] = (bull2 & (body2_ >= STAR_BODY1_MIN * rng2)
                          & (body1 <= STAR_BODY2_MAX * body2_)
                          & bear & (c < (o2 + c2) / 2) & up_before3).fillna(False)
    return df

# ==========================================
# SMC (chạy theo từng mã trên cửa sổ ~25 nến)
# ==========================================
def _fmt_date(d):
    """numpy.datetime64 hoặc str -> 'YYYY-MM-DD', an toàn cho cả 2 kiểu đầu vào của cột date."""
    if d is None:
        return None
    if isinstance(d, (bytes, str)):
        return str(d)[:10]
    return str(pd.Timestamp(d).date())


def smc_one(o, h, l, c, atr14, dates=None, volume=None):
    """Định nghĩa CƠ HỌC (không đổi phần lõi so với bản gốc):
    - FVG bull: low[i] > high[i-2] (gap 3 nến), vùng = [high[i-2], low[i]];
      chỉ giữ FVG MỚI NHẤT chưa bị lấp ĐẦY (low sau đó chưa xuyên thủng đáy vùng). Bear đối xứng.
    - BOS bull: close vượt lên swing high ĐÃ XÁC NHẬN gần nhất (fractal n=2 -> xác nhận trễ 2 nến).
    - Order Block bull: nến GIẢM cuối cùng trong {OB_LOOKBACK} nến trước cú BOS bull,
      vùng = [low, high] nến đó. Bear đối xứng.
    - "Gần vùng" (xét NẾN CUỐI): close nằm TRONG biên OB; hoặc nằm trong FVG / cách mép FVG <= 1xATR14.

    MỚI (nâng cấp workflow bỏ Gemini, mục 5 — biên + ngày FVG/OB, swing, S/R gần, volume
    confirmation; xem FINAL_STOCK_ANALYSIS_20260717.md mục 7 — trước đây các biên này được TÍNH
    RỒI VỨT, chỉ xuất nhãn chuỗi rỗng nghĩa "fvg_bear" không kèm biên giá/ngày hình thành):
    - swing_highs/swing_lows: mọi swing ĐÃ XÁC NHẬN trong cửa sổ quét, kèm ngày + giá + volume
      xác nhận tại phiên hình thành.
    - fvg_bull/fvg_bear/ob_bull/ob_bear: dict {low, high, formed_date, formed_index,
      volume_confirmed} thay vì chỉ 1 nhãn chuỗi.
    - nearest_support/nearest_resistance: vùng swing gần giá đóng cửa hiện tại nhất (dung sai
      SR_TOUCH_TOLERANCE_ATR x ATR14), kèm reaction_count = số swing khác rơi vào cùng vùng.
    - KHÔNG suy diễn khi thiếu dữ liệu: nếu không có swing nào xác nhận được trong cửa sổ (giá đi
      một mạch, không tạo pivot), nearest_support/nearest_resistance = None và
      insufficient_data=True kèm insufficient_reason — không tự bịa vùng.
    """
    n = len(c)
    last = n - 1
    tags = []
    has_dates = dates is not None
    has_volume = volume is not None
    avg_vol = float(np.mean(volume)) if has_volume and n else None

    def vol_confirmed(i):
        if not has_volume or not avg_vol or i is None:
            return None
        return bool(volume[i] >= VOL_CONFIRM_MULT * avg_vol)

    def date_at(i):
        return _fmt_date(dates[i]) if has_dates and i is not None else None

    # swing xác nhận — cùng quy ước fractal n=2 của vn_indicators.py
    sh = [i for i in range(2, n - 2) if h[i] == h[i-2:i+3].max()]
    sl = [i for i in range(2, n - 2) if l[i] == l[i-2:i+3].min()]
    swing_highs = [{"index": i, "date": date_at(i), "price": float(h[i]),
                    "volume_confirmed": vol_confirmed(i)} for i in sh]
    swing_lows = [{"index": i, "date": date_at(i), "price": float(l[i]),
                   "volume_confirmed": vol_confirmed(i)} for i in sl]

    fvg_bull = fvg_bear = None
    fvg_bull_i = fvg_bear_i = None
    for i in range(2, n):
        if l[i] > h[i-2]:
            zone = (h[i-2], l[i])
            if i == last or l[i+1:].min() > zone[0]:
                fvg_bull, fvg_bull_i = zone, i
        if h[i] < l[i-2]:
            zone = (h[i], l[i-2])
            if i == last or h[i+1:].max() < zone[1]:
                fvg_bear, fvg_bear_i = zone, i

    ob_bull = ob_bear = None
    ob_bull_i = ob_bear_i = None
    for i in range(1, n):
        prior_sh = [j for j in sh if j <= i - 3]   # j xác nhận tại j+2, cần trước phiên i
        if prior_sh:
            lvl = h[prior_sh[-1]]
            if c[i] > lvl and c[i-1] <= lvl:       # BOS tăng
                for j in range(i - 1, max(-1, i - 1 - OB_LOOKBACK), -1):
                    if c[j] < o[j]:
                        ob_bull, ob_bull_i = (l[j], h[j]), j; break
        prior_sl = [j for j in sl if j <= i - 3]
        if prior_sl:
            lvl = l[prior_sl[-1]]
            if c[i] < lvl and c[i-1] >= lvl:       # BOS giảm
                for j in range(i - 1, max(-1, i - 1 - OB_LOOKBACK), -1):
                    if c[j] > o[j]:
                        ob_bear, ob_bear_i = (l[j], h[j]), j; break

    cl = c[last]
    if ob_bull is not None and ob_bull[0] <= cl <= ob_bull[1]:
        tags.append("ob_bull")
    if ob_bear is not None and ob_bear[0] <= cl <= ob_bear[1]:
        tags.append("ob_bear")
    if fvg_bull is not None and (fvg_bull[0] <= cl <= fvg_bull[1]
            or min(abs(cl - fvg_bull[0]), abs(cl - fvg_bull[1])) <= atr14):
        tags.append("fvg_bull")
    if fvg_bear is not None and (fvg_bear[0] <= cl <= fvg_bear[1]
            or min(abs(cl - fvg_bear[0]), abs(cl - fvg_bear[1])) <= atr14):
        tags.append("fvg_bear")

    def zone_detail(zone, idx):
        if zone is None:
            return None
        return {"low": float(zone[0]), "high": float(zone[1]), "formed_date": date_at(idx),
                "formed_index": idx, "volume_confirmed": vol_confirmed(idx)}

    # Vùng hỗ trợ/kháng cự gần nhất — cụm swing trong dung sai SR_TOUCH_TOLERANCE_ATR x ATR14.
    tol = SR_TOUCH_TOLERANCE_ATR * atr14 if atr14 else 0
    nearest_support = nearest_resistance = None
    below = [s for s in swing_lows if s["price"] <= cl]
    above = [s for s in swing_highs if s["price"] >= cl]
    if below:
        base = max(below, key=lambda s: s["price"])
        cluster = [s for s in swing_lows if abs(s["price"] - base["price"]) <= tol] if tol else [base]
        nearest_support = {
            "price": round(float(np.mean([s["price"] for s in cluster])), 4),
            "reaction_count": len(cluster), "touches": cluster,
            "distance_pct": round((cl / base["price"] - 1) * 100, 2) if base["price"] else None,
        }
    if above:
        base = min(above, key=lambda s: s["price"])
        cluster = [s for s in swing_highs if abs(s["price"] - base["price"]) <= tol] if tol else [base]
        nearest_resistance = {
            "price": round(float(np.mean([s["price"] for s in cluster])), 4),
            "reaction_count": len(cluster), "touches": cluster,
            "distance_pct": round((base["price"] / cl - 1) * 100, 2) if cl else None,
        }
    insufficient = not swing_highs and not swing_lows
    insufficient_reason = (
        f"khong_tim_thay_swing_xac_nhan_trong_{n}_nen_quet (giá đi một mạch, không có pivot"
        " fractal n=2 nào được xác nhận trong cửa sổ)" if insufficient else None
    )

    return {
        "tags": tags,
        "swing_highs": swing_highs, "swing_lows": swing_lows,
        "fvg_bull": zone_detail(fvg_bull, fvg_bull_i), "fvg_bear": zone_detail(fvg_bear, fvg_bear_i),
        "ob_bull": zone_detail(ob_bull, ob_bull_i), "ob_bear": zone_detail(ob_bear, ob_bear_i),
        "nearest_support": nearest_support, "nearest_resistance": nearest_resistance,
        "insufficient_data": insufficient, "insufficient_reason": insufficient_reason,
    }

# ==========================================
# LẮP GHÉP
# ==========================================
def js_dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2,
                      default=lambda x: x.item() if hasattr(x, "item") else str(x))

def main():
    ap = argparse.ArgumentParser(description="Quét mẫu nến + SMC + cổ tức -> ta_signals.* và data/*.json cho dashboard")
    ap.add_argument("--date", default=None, help="quét phiên YYYY-MM-DD (mặc định: mới nhất trong DB)")
    ap.add_argument("--generated-at", help="ISO-8601 timezone-aware source generation timestamp")
    ap.add_argument("--limit", type=int, default=0, help="chỉ quét N mã đầu + watchlist (để test)")
    ap.add_argument("--pattern-lookback-1d", type=int, default=90, help="số nến 1D gần nhất để xuất mẫu")
    ap.add_argument("--pattern-lookback-1w", type=int, default=78, help="số nến 1W gần nhất để xuất mẫu")
    ap.add_argument("--pattern-lookback-1m", type=int, default=36, help="số nến 1M gần nhất để xuất mẫu")
    ap.add_argument("--pattern-min-confidence", type=int, default=40, choices=range(0, 101), metavar="0..100",
                    help="ngưỡng điểm tối thiểu cho snapshot mẫu nến (mặc định 40)")
    ap.add_argument("--pattern-max-results", type=int, default=3,
                    help="tối đa kết quả mỗi mã và timeframe")
    ap.add_argument("--pattern-workers", type=int, default=min(4, max(1, (os.cpu_count() or 2) - 1)),
                    help="số worker scan theo mã (mặc định tối đa 4)")
    args = ap.parse_args()
    generated_at = resolve_source_datetime(args.generated_at)
    generated_at_text = source_timestamp(generated_at)

    conn = sqlite3.connect(DB_PATH)
    cutoff = (generated_at - timedelta(days=LOOKBACK_CAL_DAYS)).strftime("%Y-%m-%d")
    df = pd.read_sql("SELECT ticker, date, open, high, low, close, volume FROM ohlcv "
                     "WHERE date >= ? ORDER BY ticker, date", conn, params=(cutoff,))
    # Một query lịch sử dùng chung cho 1D/1W/1M; cửa sổ 2.600 ngày đủ 60+ nến tháng,
    # 104+ nến tuần và warm-up SMA200 mà không phải query riêng từng mã.
    pattern_df = pd.read_sql(
        "SELECT ticker, date, open, high, low, close, volume FROM ohlcv "
        "WHERE date >= date((SELECT MAX(date) FROM ohlcv), '-2600 day') ORDER BY ticker, date",
        conn,
    )
    meta = pd.read_sql("SELECT ticker, dividend_yield, pe, pb, roe, industry AS meta_industry "
                       "FROM metadata", conn)
    conn.close()
    if df.empty:
        sys.exit("[Lỗi] Không có dữ liệu giá — chạy vn_stock_pipeline.py update trước.")

    bars = df.groupby("ticker")["date"].transform("count")
    df = df[bars >= MIN_BARS].copy()

    # Ngày quét = ngày MỚI NHẤT có >= 50% số mã giao dịch. Tránh bẫy: đang chạy
    # vn_stock_pipeline update dở dang thì DB có ngày mới nhưng chỉ vài chục mã -> quét sai.
    cnt = df.groupby("date")["ticker"].nunique()
    dscan = args.date or cnt[cnt >= cnt.max() * 0.5].index.max()
    if not args.date and df["date"].max() != dscan:
        print(f" [cảnh báo] DB có ngày {df['date'].max()} nhưng chỉ {cnt.get(df['date'].max(), 0)} mã "
              f"(update đang dở?) -> quét phiên đủ dữ liệu gần nhất: {dscan}")

    # ret 1 tuần (5 phiên) + giá mới nhất: tính trên TOÀN THỊ TRƯỜNG trước khi --limit,
    # vì heatmap ngành và góc cổ tức không được phép co theo tập test
    g = df.groupby("ticker")
    df["ret_1w"] = (df["close"] / g["close"].shift(5) - 1) * 100
    ret1w_full = df[df["date"] == dscan].set_index("ticker")["ret_1w"]
    last_close_full = df[df["date"] <= dscan].groupby("ticker")["close"].last()

    if args.limit:
        keep = sorted(df["ticker"].unique())[:args.limit]
        df = df[df["ticker"].isin(set(keep) | set(WATCHLIST))].copy()
    df = detect_patterns(df)

    # nền lọc tái sử dụng từ snapshot (không tính lại)
    snap_cols = ["ticker", "industry", "rs_rating", "rel_vol", "gtgd20_ty",
                 "margin_status", "atr_pct", "above_sma200", "chg_today_pct", "ret_1m"]
    if SNAPSHOT_PATH.exists():
        full_snap = pd.read_csv(SNAPSHOT_PATH)
        snap = full_snap[snap_cols]
    else:
        print(" [cảnh báo] Thiếu screen_snapshot.csv -> không có nền rs/rel_vol/industry")
        full_snap = pd.DataFrame()
        snap = pd.DataFrame(columns=snap_cols)

    today = df[df["date"] == dscan].merge(snap, on="ticker", how="left")
    names = list(PATTERN_DIRECTION.keys())

    # SMC từng mã (chỉ mã có nến phiên quét)
    smc_map = {}
    for tk, tdf in df[df["ticker"].isin(today["ticker"])].groupby("ticker"):
        row = today.loc[today["ticker"] == tk].iloc[0]
        # ATR14 tuyệt đối: ưu tiên atr_pct từ snapshot (Wilder hội tụ); thiếu thì xấp xỉ biên độ 14 nến
        atr14 = (row["atr_pct"] / 100 * row["close"]) if pd.notna(row.get("atr_pct")) \
                else float((tdf["high"] - tdf["low"]).tail(14).mean())
        smc_map[tk] = smc_one(tdf["open"].values, tdf["high"].values,
                              tdf["low"].values, tdf["close"].values, atr14,
                              dates=tdf["date"].values, volume=tdf["volume"].values)

    # Snapshot mẫu nến đa khung hoàn toàn tách khỏi candle_signals legacy.
    pattern_tickers = None
    if args.limit:
        pattern_tickers = set(keep) | set(WATCHLIST)
    print(f"[candlestick] Bắt đầu scan lịch sử 1D/1W/1M từ {len(pattern_df):,} dòng OHLCV...", flush=True)
    pattern_payload = build_snapshot(
        pattern_df,
        scan_date=str(dscan),
        generated_at=generated_at,
        market_snapshot=full_snap,
        smc_by_ticker=smc_map,
        lookbacks={"1D": args.pattern_lookback_1d, "1W": args.pattern_lookback_1w,
                   "1M": args.pattern_lookback_1m},
        min_confidence=args.pattern_min_confidence,
        max_results_per_ticker_timeframe=max(1, args.pattern_max_results),
        tickers=pattern_tickers,
        progress=lambda count: print(f"   [candlestick] đã xử lý {count:,} mã", flush=True),
        workers=max(1, args.pattern_workers),
    )
    atomic_write_snapshot(pattern_payload, PATTERN_OUT_JSON, PATTERN_OUT_JS)
    ps = pattern_payload["summary"]
    print(f"[candlestick] {ps['tickers_scanned']:,} mã | {ps['total_patterns']:,} mẫu "
          f"(1D={ps['by_timeframe']['1D']:,}, 1W={ps['by_timeframe']['1W']:,}, "
          f"1M={ps['by_timeframe']['1M']:,}) | {ps['runtime_seconds']:.2f}s")

    # smc_map[tk] giờ là dict chi tiết (tags/swing/S-R/FVG-OB kèm biên+ngày) — cột "smc" phẳng
    # dùng cho CSV/confluence/score chỉ cần list tag chuỗi như trước (tương thích ngược).
    today["smc"] = today["ticker"].map(smc_map).apply(
        lambda x: x["tags"] if isinstance(x, dict) else [])
    today["patterns"] = today[names].apply(lambda r: [n for n in names if r[n]], axis=1)

    def confluence(r):
        pats, tags = set(r["patterns"]), set(r["smc"])
        return bool((pats & BULL_PATTERNS and tags & {"ob_bull", "fvg_bull"})
                    or (pats & BEAR_PATTERNS and tags & {"ob_bear", "fvg_bear"}))
    today["confluence"] = today.apply(confluence, axis=1)

    score = sum(today[n] * d for n, d in PATTERN_DIRECTION.items()) \
        + today["smc"].apply(lambda t: ("ob_bull" in t) + ("fvg_bull" in t)
                             - ("ob_bear" in t) - ("fvg_bear" in t))
    today["direction"] = np.select([score > 0, score < 0], ["bullish", "bearish"], "neutral")

    has_sig = (today[names].any(axis=1) | today["smc"].astype(bool))
    sig = today[has_sig | today["ticker"].isin(WATCHLIST)].copy()
    sig = sig.sort_values(["confluence", "rs_rating"], ascending=[False, False])

    # ---------- 1) ta_signals.csv/json (giữ format cũ + cột smc/confluence) ----------
    sig["source_generated_at"] = generated_at_text
    flat = sig.copy()
    flat["patterns"] = flat["patterns"].apply(";".join)
    flat["smc"] = flat["smc"].apply(";".join)
    out_cols = ["ticker", "date", "source_generated_at", "close", "volume", "patterns", "smc", "confluence",
                "direction", "industry", "rs_rating", "rel_vol", "gtgd20_ty", "margin_status"]
    flat[out_cols].to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    os.makedirs(DATA_DIR, exist_ok=True)
    sig_records = [
        {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in r.items()}
        for r in sig[out_cols[:1] + out_cols[1:]].assign(
            patterns=sig["patterns"], smc=sig["smc"]).to_dict(orient="records")
    ]
    # smc_detail: biên giá + ngày hình thành FVG/OB, swing, S/R gần nhất, volume confirmation —
    # CHỈ ở JSON (CSV giữ nguyên cột "smc" phẳng để không phá tương thích ngược). Không tự bịa khi
    # thiếu dữ liệu: xem insufficient_data/insufficient_reason trong smc_one().
    for rec in sig_records:
        detail = smc_map.get(rec["ticker"])
        rec["smc_detail"] = {k: v for k, v in detail.items() if k != "tags"} if isinstance(detail, dict) else None
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        f.write(js_dump({"scan_date": str(dscan), "n_signals": len(sig_records),
                         "signals": sig_records}))

    # ---------- 2) Watchlist (luôn đủ mã trong WATCHLIST, kể cả không tín hiệu) ----------
    watch = []
    for tk in WATCHLIST:
        r = today[today["ticker"] == tk]
        if r.empty:
            watch.append({"ticker": tk, "has_signal": False, "note": "không có nến phiên quét"})
            continue
        r = r.iloc[0]
        detail = smc_map.get(tk)
        watch.append({"ticker": tk, "close": r["close"], "chg_pct": r.get("chg_today_pct"),
                      "patterns": r["patterns"], "smc": r["smc"],
                      "smc_detail": {k: v for k, v in detail.items() if k != "tags"}
                                    if isinstance(detail, dict) else None,
                      "confluence": bool(r["confluence"]), "direction": r["direction"],
                      "has_signal": bool(r["patterns"] or r["smc"])})

    # ---------- 3) Góc tích sản cổ tức (metadata.dividend_yield, đơn vị %) ----------
    # LUÔN tính toàn thị trường (không phụ thuộc --limit): giá lấy close mới nhất từ DB,
    # cờ margin lấy từ snapshot toàn thị trường
    n_cover = int((meta["dividend_yield"] >= 0).sum())
    div = meta[(meta["dividend_yield"] >= DIV_YIELD_MIN)].copy()
    div["close"] = div["ticker"].map(last_close_full)
    div = div.merge(snap[["ticker", "margin_status"]], on="ticker", how="left")
    div = div[div["margin_status"].isna() & div["close"].notna()] \
        .sort_values("dividend_yield", ascending=False)
    div_note = (f"{n_cover}/{len(meta)} mã đã có dữ liệu cổ tức"
                + ("" if n_cover > len(meta) * 0.9
                   else " — chạy `python meta_sync.py --ratio-only` để phủ nốt"))
    div_records = div[["ticker", "close", "dividend_yield", "pe", "pb", "roe",
                       "meta_industry"]].rename(columns={"meta_industry": "industry"}) \
        .replace({np.nan: None}).to_dict(orient="records")

    payload = {"generated_at": generated_at_text,
               "scan_date": str(dscan), "watchlist": watch,
               "signals": sig_records, "dividend_note": div_note,
               "dividend_investing": div_records}
    with open(os.path.join(DATA_DIR, "candle_signals.json"), "w", encoding="utf-8") as f:
        f.write(js_dump(payload))
    # bản .js để index.html mở bằng file:// vẫn chạy (fetch bị CORS chặn trên file://)
    with open(os.path.join(DATA_DIR, "candle_signals.js"), "w", encoding="utf-8") as f:
        f.write("window.CANDLE_SIGNALS = " + js_dump(payload) + ";")

    # ---------- 4) Heatmap ngành — LUÔN toàn thị trường từ snapshot (không phụ thuộc --limit) ----------
    hm_src = snap.dropna(subset=["industry"]).copy()
    hm_src["ret_1w"] = hm_src["ticker"].map(ret1w_full)
    hm = hm_src.groupby("industry").agg(
        n=("ticker", "count"),
        pct_above_ma200=("above_sma200", lambda s: round((s == True).mean() * 100, 1)),
        ret_1w=("ret_1w", lambda s: round(s.mean(), 2)),
        ret_1m=("ret_1m", lambda s: round(s.mean(), 2)),
        pct_up_today=("chg_today_pct", lambda s: round((s > 0).mean() * 100, 1)),
    ).reset_index()
    # điểm sức mạnh = trung bình percent-rank của 4 tiêu chí (0-100, quy ước)
    ranks = hm[["pct_above_ma200", "ret_1w", "ret_1m", "pct_up_today"]].rank(pct=True)
    hm["strength"] = (ranks.mean(axis=1) * 100).round(1)
    hm = hm.sort_values("strength", ascending=False)
    hm_payload = {"generated_at": generated_at_text,
                  "scan_date": str(dscan),
                  "sectors": hm.replace({np.nan: None}).to_dict(orient="records")}
    with open(os.path.join(DATA_DIR, "sector_heatmap.json"), "w", encoding="utf-8") as f:
        f.write(js_dump(hm_payload))
    with open(os.path.join(DATA_DIR, "sector_heatmap.js"), "w", encoding="utf-8") as f:
        f.write("window.SECTOR_HEATMAP = " + js_dump(hm_payload) + ";")

    # ---------- 5) Dữ liệu cho screener.html — bản .js để mở file:// vẫn chạy ----------
    # (trang screener tự fetch CSV khi chạy qua http/GitHub Pages; mở trực tiếp file://
    # thì fetch bị CORS chặn -> rơi về 2 biến global trong file .js này)
    snap_full = full_snap
    # Fallback giữ TOÀN BỘ field để giao diện card không mất chi tiết. Phiên lấy max
    # của mã đang niêm yết, không phụ thuộc thứ tự rows[0].
    scr = full_snap.replace({np.nan: None})
    breadth_js = pd.read_csv(MARKET_BREADTH_PATH).replace({np.nan: None}) \
        if MARKET_BREADTH_PATH.exists() else pd.DataFrame()
    active = full_snap[full_snap.get("exchange", "").astype(str).str.upper() != "DELISTED"]
    market_session = str(active["date"].dropna().max()) if len(active) else str(full_snap["date"].dropna().max())
    fallback_meta = {"schema_version": 1,
                     "generated_at": generated_at_text,
                     "market_session": market_session}
    with open(os.path.join(DATA_DIR, "screener_data.js"), "w", encoding="utf-8") as f:
        f.write("window.SCREENER_DATA_META = " + js_dump(fallback_meta) + ";\n")
        f.write("window.SCREEN_ROWS = " + js_dump(scr.to_dict(orient="records")) + ";\n")
        f.write("window.BREADTH_ROWS = " + js_dump(breadth_js.to_dict(orient="records")) + ";\n")

    # ---------- Báo cáo console ----------
    conf = sig[sig["confluence"]]
    print(f"[candle_scan] Phiên {dscan}: {today['ticker'].nunique()} mã | "
          f"{int(has_sig.sum())} có tín hiệu | {len(conf)} CONFLUENCE | cổ tức>= {DIV_YIELD_MIN}%: {len(div_records)} mã")
    print(f"   -> {OUT_CSV}, {OUT_JSON}, {DATA_DIR}/candle_signals.json(.js), {DATA_DIR}/sector_heatmap.json(.js)")
    print(f"   -> {PATTERN_OUT_JSON}, {PATTERN_OUT_JS}")
    if len(conf):
        show = conf[["ticker", "close", "direction", "rs_rating", "rel_vol", "margin_status"]].copy()
        show["patterns"] = conf["patterns"].apply(";".join)
        show["smc"] = conf["smc"].apply(";".join)
        print("\n== TÍN HIỆU HỢP LƯU (nến đảo chiều + vùng SMC cùng hướng) ==")
        print(show.head(15).to_string(index=False))
    print("\n== Watchlist ==")
    for w in watch:
        mark = "★CONFLUENCE" if w.get("confluence") else ("có tín hiệu" if w.get("has_signal") else "im ắng")
        print(f"   {w['ticker']:<5} close={w.get('close')} {w.get('direction', '')} "
              f"patterns={w.get('patterns') or []} smc={w.get('smc') or []} -> {mark}")

if __name__ == "__main__":
    main()
