import os
import sys
import json
import argparse
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd
from runtime_paths import runtime_root

import vn_indicators as vi   # thư viện chỉ báo chính thức (Phase 1) — analyzer CHỈ TIÊU THỤ, không tự tính lại

# Console Windows mặc định cp1252 -> vỡ khi in tiếng Việt
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==========================================================================
# STOCK ANALYZER — công cụ phân tích offline, đọc dữ liệu có sẵn trong kho
# ==========================================================================
#   python stock_analyzer.py --tickers SSI PAN EVF POW HPG   -> Focus_Analysis.md
#   python stock_analyzer.py --scan-market                   -> Market_Scan.md + Market_Scan.csv
#   python stock_analyzer.py --strategy all                  -> chạy 10 chiến lược + chấm điểm 0-100
#                                                               -> analysis_latest.json + analysis_latest.md
#   python stock_analyzer.py --strategy value                -> chỉ chạy 1 chiến lược (vẫn ra 2 file trên)
#   python stock_analyzer.py --list-strategies               -> xem chiến lược + tình trạng nguồn
#   (các cờ kết hợp được với nhau)
#
# 10 chiến lược: value · canslim · momentum · ftse · fscore · smc · breakout ·
# turnaround · rs (relative strength) · sector (sector rotation).
# Báo cáo hợp nhất CHỈ 2 file (đủ nhẹ để upload cho AI / nhúng dashboard):
#   analysis_latest.json — máy đọc: summary/market/top_stocks/scores/strategies/risks/portfolio
#   analysis_latest.md   — người đọc, sinh từ chính payload JSON
#
# Đây là LỚP PHÂN TÍCH đọc output có sẵn của pipeline — KHÔNG thay thế pipeline,
# không gọi mạng, không tốn request nào. Ghi vào vn_stock.db DUY NHẤT bảng
# watchlist_history (top điểm mỗi phiên — nền cho backtest sau này); TUYỆT ĐỐI
# không đụng bảng nào khác của pipeline.
#
# LUỒNG PHASE 2 (tầng chỉ báo thư viện — vn_indicators Phần 1):
#   OHLCV thô (vn_stock.db) -> IndicatorEngine tính HÀNG LOẠT 1 lần (ADX/ROC/MFI/CMF/
#   OBV/MACD/Bollinger/Ichimoku/BOS/CHoCH/FVG/OB) -> 1 DataFrame live LÀM GIÀU
#   -> 10 chiến lược -> ScoreEngine -> ReportEngine. Chiến lược KHÔNG tự tính
#   chỉ báo riêng lẻ. Mã thiếu lịch sử/lỗi tính -> cột chỉ báo NaN (degraded):
#   filter thư viện tự cho qua (soft), điểm số rơi về công thức gốc — KHÔNG BAO GIỜ
#   dừng cả vòng phân tích (fixture selftest không có OHLCV chạy y hệt bản cũ).
#
# Nguồn dữ liệu (tự phát hiện — thiếu file nào thì bỏ qua phần đó, KHÔNG crash):
#   - screen_snapshot.csv : bảng lọc chính (chỉ báo + PE/PB/ROE + luật), sinh bởi vn_indicators.py
#   - market_breadth.csv  : độ rộng thị trường theo ngành
#   - macro_snapshot.csv  : vĩ mô thế giới + VN (trạng thái hôm nay)
#   - news_latest.csv     : ~100 tin mới nhất
#   - ta_signals.csv      : mẫu nến + SMC phiên mới nhất (candle_scan.py)
#   - ohlcv_flat.parquet  : lịch sử giá (chỉ nạp ĐÚNG các mã cần, không load cả 1,9tr dòng)
#   - vn_stock.db (read-only) : bảng metadata lấy dividend_yield + market_cap
#     (snapshot KHÔNG có 2 cột này — đừng bỏ bước join)
#
# Lưu ý kho (xem README.md mục 4):
#   - Kho CHƯA có ROA và số nợ (D/E) -> ROA ghi n/a; "Red Flags" dùng proxy:
#     lỗ (PE<=0) / ROE âm / dính án sàn (margin_status khác rỗng).
#   - dividend_yield: đơn vị %, giá trị -1 = "đã hỏi nguồn nhưng không có số" -> coi như NaN.
#   - Snapshot chứa cả mã đã chết với ngày cũ (VD ASA dừng từ 2022) -> mọi phép
#     scan toàn thị trường CHỈ tính trên các dòng có date = phiên mới nhất.
#   - Cột boolean lưu dạng chữ "True"/"False"; structure lưu chữ thường up/side/down.
# ==========================================================================

ROOT = str(runtime_root(os.path.dirname(os.path.abspath(__file__))))
SNAPSHOT_CSV = os.path.join(ROOT, "screen_snapshot.csv")
BREADTH_CSV = os.path.join(ROOT, "market_breadth.csv")
PARQUET = os.path.join(ROOT, "ohlcv_flat.parquet")
DB_FILE = os.path.join(ROOT, "vn_stock.db")
MACRO_CSV = os.path.join(ROOT, "macro_snapshot.csv")
NEWS_CSV = os.path.join(ROOT, "news_latest.csv")
SIGNALS_CSV = os.path.join(ROOT, "ta_signals.csv")

FOCUS_MD = os.path.join(ROOT, "Focus_Analysis.md")
SCAN_MD = os.path.join(ROOT, "Market_Scan.md")
SCAN_CSV = os.path.join(ROOT, "Market_Scan.csv")

# ==== NGƯỠNG QUY ƯỚC — chỉnh ở đây, không sửa trong logic ====
LIQ_MIN_TY = 3.0        # GTGD bq 20 phiên tối thiểu (tỷ/phiên) — lọc hàng lởm
GEM_DIV_MIN = 7.0       # cổ tức >= 7%/năm
GEM_PE_MAX = 12.0       # 0 < PE <= 12 coi là rẻ
GEM_PB_MAX = 2.0        # PB <= 2
GEM_ROE_MIN = 15.0      # ROE >= 15%
GEM_RS_MIN = 50         # RS không cần quá mạnh, chỉ cần không yếu
FTSE_CAP_MIN_TY = 10_000    # vốn hóa >= 10.000 tỷ đồng
FTSE_GTGD_MIN_TY = 30.0     # GTGD20 >= 30 tỷ/phiên
FTSE_FF_MIN = 0.15          # free float ước tính >= 15%
TOP_N_MD = 25               # số dòng tối đa mỗi bảng trong Market_Scan.md (CSV thì đủ hết)
PRICE_LOOKBACK = 280        # số phiên nạp từ parquet cho mỗi mã focus (đủ tính MA200)

# ---- ngưỡng cho 10 chiến lược (--strategy) ----
CANSLIM_RS_MIN = 80         # canslim: RS tối thiểu (đúng công thức FILTER trong README)
MOM_RS_MIN = 80             # momentum: RS tối thiểu
RS_ELITE_MIN = 90           # rs thuần: top ~10% thị trường
BRK_RS_MIN = 70             # breakout: RS tối thiểu
BRK_RELVOL_MIN = 1.5        # breakout: khối lượng >= 1.5x trung bình
TURN_RET3M_MIN = 10.0       # turnaround: 3 tháng hồi >= 10%
FSCORE_MIN = 7              # fscore proxy: đạt >= 7/9 tiêu chí
SMC_DISCOUNT_MAX = 10.0     # smc: cách swing low <= 10% (vùng discount)
SECTOR_TOP_N = 3            # sector rotation: lấy 3 ngành mạnh nhất
SECTOR_MIN_SYMBOLS = 8      # ...ngành phải có >= 8 mã mới xét (tránh ngành 2-3 mã nhiễu)

# ---- tầng chỉ báo thư viện (Phase 2 — tiêu thụ vn_indicators Phần 1) ----
ENRICH_BARS = 280           # số nến tối đa mỗi mã đưa vào tính chỉ báo (đủ Ichimoku 52+26 + nền squeeze)
ENRICH_MIN_BARS = 60        # dưới ngưỡng này mã bị degraded: cột chỉ báo NaN, điểm giữ công thức gốc
ENRICH_CUTOFF_DAYS = 450    # chỉ đọc OHLCV ~450 ngày lịch (~300 phiên) từ vn_stock.db cho nhẹ
SMC_RECENT_BARS = 10        # BOS/CHoCH/FVG/OB xảy ra trong N nến cuối được tính là "gần đây"
MOM_ADX_MIN = 20            # momentum: ADX tối thiểu — xu hướng phải CÓ LỰC (soft: thiếu dữ liệu cho qua)
TURN_CMF_MIN = -0.05        # turnaround: CMF20 không âm sâu — tiền còn RÚT mạnh thì chưa phải đảo chiều
LIB_BLEND = 0.20            # technical/momentum = (1-x)*điểm gốc + x*điểm thư viện KHI có enrichment

# ---- chấm điểm 0-100 + báo cáo hợp nhất ----
SCORE_WEIGHTS = {           # trọng số 6 cấu phần của điểm tổng (cộng = 1.0)
    "fundamental": 0.25, "technical": 0.20, "momentum": 0.20,
    "liquidity": 0.15, "macro": 0.10, "risk": 0.10}
STRAT_TOP_N = 10            # số mã mỗi chiến lược đưa vào báo cáo (giữ JSON nhẹ)
TOP_PICKS = 20              # số mã Top Stocks (kèm giải thích điểm) + lưu watchlist_history
PORT_N = 8                  # gợi ý danh mục: tối đa 8 mã
PORT_MAX_PER_IND = 2        # ...mỗi ngành tối đa 2 mã (ép đa dạng hóa)
PORT_RISK_MIN = 60          # ...chỉ nhận mã có điểm rủi ro >= 60 (100 = an toàn nhất)
REPORT_JSON = os.path.join(ROOT, "analysis_latest.json")
REPORT_MD = os.path.join(ROOT, "analysis_latest.md")

# ---- guard chống "sai âm thầm" (lớp bug HSX vs HOSE) ----
EXCHANGE_DOMAIN = {"HSX", "HNX", "UPCOM", "DELISTED"}   # giá trị hợp lệ của cột exchange (quy ước VCI)
EMPTY_WARN_MIN_UNIVERSE = 200   # universe >= ngưỡng này mà chiến lược trả 0 mã -> cảnh báo nghi filter hỏng
# Cột snapshot BẮT BUỘC -> thành phần nào cần nó. Thiếu cột = DỪNG với lỗi nêu đích danh,
# tuyệt đối không lọc tiếp trên dữ liệu thiếu (sẽ ra kết quả sai âm thầm).
REQUIRED_SNAPSHOT_COLS = {
    "ticker": "mọi thành phần", "date": "lọc phiên live", "close": "scan/scoring/watchlist",
    "chg_today_pct": "breakout", "gtgd20_ty": "base_ok/scoring", "margin_status": "base_ok/scoring",
    "rel_vol": "canslim/momentum/breakout/scoring", "rsi14": "focus/scoring", "atr_pct": "scoring",
    "above_sma50": "momentum/turnaround/scoring", "above_sma200": "canslim/fscore/sector/scoring",
    "golden_cross": "momentum/scoring", "near_52w_high": "breakout",
    "pct_from_52w_high": "canslim/scoring", "dist_swing_low_pct": "smc",
    "structure": "fscore/breakout/scoring",
    "ret_1m": "momentum/turnaround/scoring", "ret_3m": "momentum/turnaround/scoring",
    "ret_6m": "momentum/scoring", "ret_12m": "turnaround/focus",
    "rs_rating": "canslim/momentum/rs/sector/scoring", "exchange": "ftse",
    "industry": "value/sector/trung vị ngành", "foreign_room_pct": "ftse/scoring",
    "pe": "value/fscore/scoring", "pb": "value/fscore/scoring", "roe": "value/fscore/scoring",
    "free_float_est": "ftse/scoring",
}


# ==========================================================================
# TIỆN ÍCH
# ==========================================================================

LOG_FILE = os.path.join(ROOT, "logs", "stock_analyzer.log")


def log(msg: str) -> None:
    """In ra console (y hệt print) + ghi bản sao kèm timestamp vào logs/stock_analyzer.log
    — cùng quy ước với publish_log.txt. Log hỏng không được làm gãy việc chính."""
    print(msg)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except OSError:
        pass


def fmt(x, dec: int = 1, suffix: str = "") -> str:
    """Format số cho báo cáo — NaN/None ra 'n/a'."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "n/a"
    return f"{x:,.{dec}f}{suffix}"


def as_bool(series: pd.Series) -> pd.Series:
    """Cột boolean trong CSV có thể là bool thật hoặc chuỗi 'True'/'False' -> chuẩn hóa."""
    return series.map(lambda v: str(v).strip().lower() == "true")


def md_table(df: pd.DataFrame, cols: list, headers: list) -> str:
    """Xuất DataFrame ra bảng Markdown (không phụ thuộc tabulate)."""
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r.get(c, "")
            if v is None or (isinstance(v, float) and pd.isna(v)):
                cells.append("n/a")  # None (từ json_records) và NaN đều ra n/a
            elif isinstance(v, float):
                cells.append(f"{v:,.1f}")
            else:
                cells.append(str(v) if v == v else "n/a")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ==========================================================================
# NẠP DỮ LIỆU
# ==========================================================================

def load_snapshot(csv_path: str = SNAPSHOT_CSV, db_path: str = DB_FILE) -> pd.DataFrame:
    """Nạp snapshot + join dividend_yield/market_cap từ metadata (read-only).
    2 tham số đường dẫn CHỈ dành cho --selftest (trỏ vào fixture) — gọi không tham số = hành vi cũ."""
    if not os.path.exists(csv_path):
        log(f"[LỖI] Không thấy {os.path.basename(csv_path)} — chạy vn_indicators.py trước.")
        sys.exit(1)
    df = pd.read_csv(csv_path)

    # Guard 1 — schema: thiếu cột là DỪNG ngay, nêu đích danh cột + ai cần nó
    # (vn_indicators.py đổi format mà cứ lọc tiếp là ra kết quả sai âm thầm)
    missing = [c for c in REQUIRED_SNAPSHOT_COLS if c not in df.columns]
    if missing:
        log(f"[LỖI SCHEMA] {os.path.basename(csv_path)} thiếu {len(missing)} cột bắt buộc:")
        for c in missing:
            log(f"    - {c}  (cần cho: {REQUIRED_SNAPSHOT_COLS[c]})")
        log("    -> vn_indicators.py có thể đã đổi format. DỪNG để khỏi lọc sai âm thầm.")
        sys.exit(1)

    # Guard 2 — miền giá trị exchange: giá trị lạ chỉ CẢNH BÁO, không dừng (bài học HSX vs HOSE)
    strange = set(df["exchange"].dropna().astype(str).unique()) - EXCHANGE_DOMAIN
    if strange:
        log(f"[CẢNH BÁO] Cột exchange có giá trị lạ ngoài {sorted(EXCHANGE_DOMAIN)}: {sorted(strange)}"
            " — nguồn có thể đổi quy ước, các filter theo sàn (ftse...) cần kiểm tra lại.")

    df["ticker"] = df["ticker"].astype(str).str.upper()
    df["margin_status"] = df["margin_status"].fillna("").astype(str)
    for c in ("above_sma50", "above_sma200", "golden_cross", "near_52w_high"):
        if c in df.columns:
            df[c] = as_bool(df[c])
    df["structure"] = df["structure"].astype(str).str.lower()

    # metadata: dividend_yield (%, -1 = nguồn không có số) + market_cap (đồng)
    if os.path.exists(db_path):
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            meta = pd.read_sql(
                "SELECT ticker, dividend_yield, market_cap FROM metadata", con)
        finally:
            con.close()
        meta["ticker"] = meta["ticker"].astype(str).str.upper()
        meta.loc[meta["dividend_yield"] < 0, "dividend_yield"] = float("nan")
        meta["market_cap_ty"] = meta["market_cap"] / 1e9  # đồng -> tỷ đồng
        df = df.merge(meta[["ticker", "dividend_yield", "market_cap_ty"]],
                      on="ticker", how="left")
    else:
        log("[CẢNH BÁO] Không thấy vn_stock.db — thiếu cổ tức + vốn hóa, vẫn chạy tiếp.")
        df["dividend_yield"] = float("nan")
        df["market_cap_ty"] = float("nan")
    return df


def load_prices(tickers) -> pd.DataFrame:
    """Nạp lịch sử giá CHỈ của các mã cần từ parquet (lọc ngay lúc đọc, không load cả kho)."""
    if not os.path.exists(PARQUET):
        log("[CẢNH BÁO] Không thấy ohlcv_flat.parquet — bỏ qua phần xu hướng giá chi tiết.")
        return pd.DataFrame(columns=["ticker", "date", "close", "volume"])
    try:
        import pyarrow.dataset as ds
        dset = ds.dataset(PARQUET, format="parquet")
        tbl = dset.to_table(filter=ds.field("ticker").isin(list(tickers)),
                            columns=["ticker", "date", "close", "volume"])
        px = tbl.to_pandas()
    except ImportError:
        px = pd.read_parquet(PARQUET, columns=["ticker", "date", "close", "volume"])
        px = px[px["ticker"].isin(tickers)]
    px["ticker"] = px["ticker"].astype(str).str.upper()
    return px.sort_values(["ticker", "date"])


# ==========================================================================
# PHÂN TÍCH SÂU TỪNG MÃ  (--tickers)
# ==========================================================================

def trend_from_prices(px_one):
    """Tính MA + dòng tiền từ chuỗi giá 1 mã (đã sort theo date). Trả dict, thiếu dữ liệu ra NaN."""
    out = {}
    tail = px_one.tail(PRICE_LOOKBACK)
    close, vol = tail["close"], tail["volume"]
    last = close.iloc[-1] if len(close) else float("nan")
    for n in (20, 50, 200):
        # SMA lấy từ thư viện vn_indicators (thiếu dữ liệu tự ra NaN, không cần check len)
        ma = vi.sma(tail, n, "close").iloc[-1] if len(tail) else float("nan")
        out[f"ma{n}_gap_pct"] = (last / ma - 1) * 100 if pd.notna(ma) else float("nan")
    # Dòng tiền: GTGD bq 20 phiên so với 60 phiên — dương = tiền đang vào
    gt = (close * vol) / 1e9  # tỷ đồng/phiên
    gt20 = gt.tail(20).mean() if len(gt) >= 20 else float("nan")
    gt60 = gt.tail(60).mean() if len(gt) >= 60 else float("nan")
    out["gtgd20_ty"] = gt20
    out["moneyflow_pct"] = (gt20 / gt60 - 1) * 100 if pd.notna(gt20) and gt60 else float("nan")
    out["n_sessions"] = len(tail)
    out["last_date"] = tail["date"].iloc[-1] if len(tail) else "n/a"
    return out


def run_focus(df, tickers):
    tickers = [t.upper() for t in tickers]
    latest = df["date"].max()
    live = df[df["date"] == latest]
    # trung vị ngành tính trên phiên mới nhất, PE chỉ lấy mã có lãi
    ind_pe = live[live["pe"] > 0].groupby("industry")["pe"].median()
    ind_pb = live[live["pb"] > 0].groupby("industry")["pb"].median()
    ind_roe = live.groupby("industry")["roe"].median()

    log(f"Đang nạp lịch sử giá của {len(tickers)} mã từ parquet...")
    px = load_prices(tickers)
    # Phase 2: chỉ báo thư viện vn_indicators cho cả nhóm mã focus — tính 1 lần
    # (OHLCV đọc từ vn_stock.db; thiếu DB/lịch sử thì bảng dưới ghi n/a, không crash)
    ind = IndicatorEngine(DataHub()).enrich(tickers).set_index("ticker")

    parts = [f"# Phân tích sâu — {', '.join(tickers)}",
             f"\n*Sinh bởi `stock_analyzer.py` lúc {datetime.now():%Y-%m-%d %H:%M} · "
             f"phiên snapshot mới nhất: **{latest}** · nguồn: kho local, không gọi mạng.*",
             "\n> ROA và số nợ (D/E) **chưa có trong kho** — mục Sinh lời chỉ có ROE. "
             "Metadata (PE/PB/ROE/cổ tức) là trạng thái HÔM NAY, không dùng cho backtest.\n"]

    for tk in tickers:
        rows = df[df["ticker"] == tk]
        if rows.empty:
            parts.append(f"\n## {tk}\n\n⚠️ Không có trong snapshot — mã sai hoặc chưa backfill.\n")
            log(f"[CẢNH BÁO] {tk}: không có trong snapshot.")
            continue
        r = rows.iloc[0]
        t = trend_from_prices(px[px["ticker"] == tk])
        stale = r["date"] != latest

        parts.append(f"\n## {tk} · {r['exchange']} · {r['industry']}\n")
        parts.append(f"*Phiên dữ liệu: {r['date']}"
                     + (" ⚠️ **CŨ so với thị trường — mã có thể đã ngừng giao dịch**" if stale else "")
                     + f" · Giá đóng cửa: {fmt(r['close'], 0)}đ"
                     + f" · Vốn hóa: {fmt(r['market_cap_ty'], 0)} tỷ*\n")

        # --- Định giá ---
        pe_med, pb_med = ind_pe.get(r["industry"]), ind_pb.get(r["industry"])
        parts.append("### Định giá\n")
        parts.append(md_table(pd.DataFrame([
            {"c": "P/E", "v": fmt(r["pe"], 1), "m": fmt(pe_med, 1),
             "note": "lỗ (PE<=0)" if r["pe"] <= 0 else
                     ("rẻ hơn ngành" if pd.notna(pe_med) and r["pe"] < pe_med else "cao hơn/bằng ngành")},
            {"c": "P/B", "v": fmt(r["pb"], 2), "m": fmt(pb_med, 2),
             "note": "rẻ hơn ngành" if pd.notna(pb_med) and r["pb"] < pb_med else "cao hơn/bằng ngành"},
            {"c": "Cổ tức (%/năm, trailing)", "v": fmt(r["dividend_yield"], 1), "m": "—",
             "note": "cao" if pd.notna(r["dividend_yield"]) and r["dividend_yield"] >= GEM_DIV_MIN
                     else "nguồn không có số" if pd.isna(r["dividend_yield"]) else "thường"},
        ]), ["c", "v", "m", "note"], ["Chỉ tiêu", tk, "Trung vị ngành", "Nhận xét"]))

        # --- Sinh lời ---
        roe_med = ind_roe.get(r["industry"])
        parts.append("\n### Sinh lời\n")
        parts.append(md_table(pd.DataFrame([
            {"c": "ROE (%, trailing 4 quý)", "v": fmt(r["roe"], 1), "m": fmt(roe_med, 1),
             "note": "tốt (>=15%)" if r["roe"] >= GEM_ROE_MIN else
                     ("âm — đang lỗ" if r["roe"] < 0 else "trung bình")},
            {"c": "ROA", "v": "n/a", "m": "n/a", "note": "kho chưa có dữ liệu ROA"},
        ]), ["c", "v", "m", "note"], ["Chỉ tiêu", tk, "Trung vị ngành", "Nhận xét"]))

        # --- Dòng tiền & Xu hướng ---
        parts.append("\n### Dòng tiền & Xu hướng\n")
        mf = t.get("moneyflow_pct")
        parts.append(md_table(pd.DataFrame([
            {"c": "GTGD bq 20 phiên (tỷ)", "v": fmt(r["gtgd20_ty"], 1),
             "note": "đủ thanh khoản" if r["gtgd20_ty"] >= LIQ_MIN_TY else f"⚠️ dưới {LIQ_MIN_TY} tỷ — hàng kém thanh khoản"},
            {"c": "Dòng tiền 20p so 60p (%)", "v": fmt(mf, 1),
             "note": "tiền đang VÀO" if pd.notna(mf) and mf > 0 else
                     ("tiền đang RÚT" if pd.notna(mf) else "thiếu lịch sử giá")},
            {"c": "Khối lượng so bq (rel_vol)", "v": fmt(r["rel_vol"], 2),
             "note": "sôi động hơn bình thường" if r["rel_vol"] >= 1 else "trầm lắng"},
            {"c": "RS rating (0-99)", "v": fmt(r["rs_rating"], 0),
             "note": "mạnh hơn phần lớn thị trường" if r["rs_rating"] >= 80 else
                     ("yếu" if r["rs_rating"] < GEM_RS_MIN else "trung bình")},
            {"c": "Cấu trúc giá", "v": r["structure"].upper(),
             "note": {"up": "xu hướng tăng", "down": "xu hướng giảm"}.get(r["structure"], "đi ngang")},
            {"c": "Giá so MA20 / MA50 / MA200 (%)",
             "v": f"{fmt(t.get('ma20_gap_pct'))} / {fmt(t.get('ma50_gap_pct'))} / {fmt(t.get('ma200_gap_pct'))}",
             "note": "trên MA200 = xu hướng dài hạn tăng" if r["above_sma200"] else "⚠️ dưới MA200"},
            {"c": "Cách đỉnh 52 tuần (%)", "v": fmt(r["pct_from_52w_high"], 1),
             "note": "gần đỉnh (khỏe)" if r["pct_from_52w_high"] >= -15 else "xa đỉnh"},
            {"c": "Lợi nhuận 1m/3m/6m/12m (%)",
             "v": f"{fmt(r['ret_1m'])} / {fmt(r['ret_3m'])} / {fmt(r['ret_6m'])} / {fmt(r['ret_12m'])}",
             "note": ""},
            {"c": "RSI14", "v": fmt(r["rsi14"], 1),
             "note": "quá mua (>70)" if r["rsi14"] > 70 else ("quá bán (<30)" if r["rsi14"] < 30 else "vùng trung tính")},
        ]), ["c", "v", "note"], ["Chỉ tiêu", "Giá trị", "Nhận xét"]))

        # --- Chỉ báo thư viện (Phase 2 — vn_indicators) ---
        parts.append("\n### Chỉ báo thư viện (vn_indicators)\n")
        ir = ind.loc[tk] if tk in ind.index else pd.Series(dtype=float)
        if pd.isna(ir.get("adx14")):
            parts.append(f"*Không đủ lịch sử OHLCV trong vn_stock.db (cần >= {ENRICH_MIN_BARS} nến)"
                         " — bỏ qua phần này (degraded).*")
        else:
            trend_txt = {1.0: "TĂNG (phá vỡ gần nhất hướng lên)",
                         -1.0: "GIẢM (phá vỡ gần nhất hướng xuống)"}.get(ir["ms_trend"], "chưa rõ")
            parts.append(md_table(pd.DataFrame([
                {"c": "ADX14 (+DI / -DI)",
                 "v": f"{fmt(ir['adx14'], 0)} ({fmt(ir['di_plus14'], 0)} / {fmt(ir['di_minus14'], 0)})",
                 "note": ("xu hướng CÓ LỰC" if ir["adx14"] >= 25 else
                          "có xu hướng nhẹ" if ir["adx14"] >= MOM_ADX_MIN else "không có xu hướng rõ")
                         + (", phe mua thắng" if ir["di_plus14"] > ir["di_minus14"] else ", phe bán thắng")},
                {"c": "ROC20 (%)", "v": fmt(ir["roc20"], 1),
                 "note": "đà 20 phiên dương" if ir["roc20"] > 0 else "đà 20 phiên âm"},
                {"c": "MFI14 (RSI có volume)", "v": fmt(ir["mfi14"], 0),
                 "note": "quá nóng (>80)" if ir["mfi14"] > 80 else
                         ("quá bán (<20)" if ir["mfi14"] < 20 else "cân bằng")},
                {"c": "CMF20 (dòng tiền Chaikin)", "v": fmt(ir["cmf20"], 2),
                 "note": "tiền đang VÀO" if ir["cmf20"] > 0 else "tiền đang RÚT"},
                {"c": "OBV so nền 20 phiên", "v": "trên" if ir["obv_up"] == 1 else "dưới",
                 "note": "khối lượng tích lũy" if ir["obv_up"] == 1 else "khối lượng phân phối"},
                {"c": "Bollinger bandwidth (%)", "v": fmt(ir["bb_bw_pct"], 1),
                 "note": "nền SIẾT CHẶT (squeeze) — dễ có biến động mạnh" if ir["bb_squeeze"] == 1
                         else "band bình thường"},
                {"c": "Vị trí so mây Ichimoku", "v": "trên mây" if ir["ichi_above_cloud"] == 1
                                                     else ("dưới/trong mây" if pd.notna(ir["ichi_above_cloud"]) else "n/a"),
                 "note": "xu hướng dài hạn tích cực" if ir["ichi_above_cloud"] == 1 else "chưa xác nhận"},
                {"c": "Cấu trúc thị trường (SMC)", "v": trend_txt,
                 "note": "10 nến gần nhất: " + smc_lib_note(ir)},
            ]), ["c", "v", "note"], ["Chỉ tiêu", "Giá trị", "Nhận xét"]))

        # --- Cờ rủi ro ---
        flags = []
        if r["margin_status"]:
            flags.append(f"⚠️ **Dính án sàn: `{r['margin_status']}`** — không khuyến nghị mua.")
        if stale:
            flags.append("⚠️ Dữ liệu không phải phiên mới nhất — kiểm tra mã còn giao dịch không.")
        if r["gtgd20_ty"] < LIQ_MIN_TY:
            flags.append(f"⚠️ Thanh khoản dưới ngưỡng {LIQ_MIN_TY} tỷ/phiên.")
        if pd.notna(r["foreign_room_pct"]) and r["foreign_room_pct"] == 0:
            flags.append("⚠️ Kín room ngoại (foreign_room_pct = 0).")
        if r["pe"] <= 0 or r["roe"] < 0:
            flags.append("⚠️ Đang lỗ (PE<=0 hoặc ROE âm).")
        parts.append("\n### Cờ rủi ro\n")
        parts.append("\n".join(f"- {f}" for f in flags) if flags else "- Không có cờ rủi ro nào theo dữ liệu hiện có.")
        parts.append("")

    parts.append("\n---\n*Dữ liệu sinh tự động, chỉ mang tính tham khảo — không phải khuyến nghị đầu tư.*")
    with open(FOCUS_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    log(f"Phân tích xong {len(tickers)} mã. Đã lưu -> {os.path.basename(FOCUS_MD)}")


# ==========================================================================
# QUÉT TOÀN THỊ TRƯỜNG  (--scan-market)
# ==========================================================================

def run_scan(df):
    latest = df["date"].max()
    live = df[df["date"] == latest].copy()  # CHỈ mã có nến đúng phiên mới nhất — loại mã chết
    log(f"Quét {len(live)} mã có dữ liệu phiên {latest}...")

    clean = live["margin_status"] == ""  # không dính án sàn
    liquid = live["gtgd20_ty"] >= LIQ_MIN_TY

    # --- Top Gems: rẻ + sinh lời cao + cổ tức >= 7% + xu hướng không xấu ---
    gems = live[clean & liquid
                & (live["dividend_yield"] >= GEM_DIV_MIN)
                & (live["pe"] > 0) & (live["pe"] <= GEM_PE_MAX)
                & (live["pb"] > 0) & (live["pb"] <= GEM_PB_MAX)
                & (live["roe"] >= GEM_ROE_MIN)
                & live["above_sma200"]
                & (live["rs_rating"] >= GEM_RS_MIN)].copy()
    gems["reason"] = (f"div>={GEM_DIV_MIN}% · PE<={GEM_PE_MAX} · PB<={GEM_PB_MAX}"
                      f" · ROE>={GEM_ROE_MIN}% · trên MA200 · RS>={GEM_RS_MIN}")
    gems = gems.sort_values("dividend_yield", ascending=False)

    # --- Red Flags: lỗ / ROE âm / dính án — kho chưa có D/E nên KHÔNG lọc nợ trực tiếp ---
    rf = live[(live["pe"] <= 0) | (live["roe"] < 0) | ~clean].copy()

    def rf_reason(r):
        why = []
        if r["pe"] <= 0:
            why.append("lỗ (PE<=0)")
        if r["roe"] < 0:
            why.append("ROE âm")
        if r["margin_status"]:
            why.append(f"án sàn: {r['margin_status']}")
        return " · ".join(why)
    rf["reason"] = rf.apply(rf_reason, axis=1) if not rf.empty else ""
    # thanh khoản cao mà dính cờ mới là thứ đáng chú ý nhất -> sort theo GTGD
    rf = rf.sort_values("gtgd20_ty", ascending=False)

    # --- FTSE Candidates: logic chung với --strategy ftse (1 nguồn sự thật) ---
    ftse = ftse_candidates(live)
    ftse["reason"] = (f"HOSE · cap>={FTSE_CAP_MIN_TY:,.0f} tỷ · GTGD>={FTSE_GTGD_MIN_TY} tỷ"
                      f" · còn room · FF>={FTSE_FF_MIN:.0%}")
    ftse = ftse.sort_values("market_cap_ty", ascending=False)

    # --- Xuất Markdown (mỗi bảng tối đa TOP_N_MD dòng, CSV mới là bản đủ) ---
    def section(title, d, cols, headers, note):
        head = f"\n## {title} — {len(d)} mã\n\n{note}\n"
        if d.empty:
            return head + "\n*Không có mã nào đạt tiêu chí phiên này.*\n"
        body = md_table(d.head(TOP_N_MD), cols, headers)
        more = f"\n\n*...và {len(d) - TOP_N_MD} mã nữa — xem đủ trong Market_Scan.csv.*" if len(d) > TOP_N_MD else ""
        return head + "\n" + body + more + "\n"

    parts = [f"# Quét thị trường — phiên {latest}",
             f"\n*Sinh bởi `stock_analyzer.py` lúc {datetime.now():%Y-%m-%d %H:%M} · "
             f"{len(live)} mã live / {len(df)} mã trong snapshot · ngưỡng chỉnh ở đầu file script.*",
             "\n> Kho **chưa có số nợ (D/E)** — Red Flags dùng proxy lỗ/ROE âm/án sàn. "
             "Cổ tức đơn vị %/năm (trailing, KBS); mã nguồn không có số bị loại khỏi Top Gems.\n"]
    parts.append(section(
        "💎 Top Gems (rẻ + ROE cao + cổ tức cao + trend tốt)", gems,
        ["ticker", "industry", "close", "pe", "pb", "roe", "dividend_yield", "rs_rating", "gtgd20_ty"],
        ["Mã", "Ngành", "Giá", "PE", "PB", "ROE %", "Cổ tức %", "RS", "GTGD20 (tỷ)"],
        f"Tiêu chí: sạch án · GTGD>={LIQ_MIN_TY} tỷ · cổ tức>={GEM_DIV_MIN}% · 0<PE<={GEM_PE_MAX} · "
        f"PB<={GEM_PB_MAX} · ROE>={GEM_ROE_MIN}% · trên MA200 · RS>={GEM_RS_MIN}."))
    parts.append(section(
        "🚩 Red Flags (lỗ / ROE âm / dính án sàn)", rf,
        ["ticker", "industry", "close", "pe", "roe", "gtgd20_ty", "reason"],
        ["Mã", "Ngành", "Giá", "PE", "ROE %", "GTGD20 (tỷ)", "Lý do"],
        "Sắp theo thanh khoản giảm dần — mã dòng tiền lớn mà dính cờ là đáng chú ý nhất."))
    parts.append(section(
        "🌏 FTSE Candidates (vốn hóa lớn + thanh khoản cao)", ftse,
        ["ticker", "industry", "market_cap_ty", "gtgd20_ty", "foreign_room_pct", "free_float_est", "rs_rating"],
        ["Mã", "Ngành", "Vốn hóa (tỷ)", "GTGD20 (tỷ)", "Room ngoại %", "Free float", "RS"],
        f"Tiêu chí: {ftse['reason'].iloc[0] if len(ftse) else 'HOSE · vốn hóa + thanh khoản + room + free float'} "
        "(free_float_est là proxy tự tính, không phải số FTSE chính thức)."))
    parts.append("\n---\n*Dữ liệu sinh tự động, chỉ mang tính tham khảo — không phải khuyến nghị đầu tư.*")
    with open(SCAN_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))

    # --- Xuất CSV thô: đủ mọi dòng của 3 nhóm, thêm cột category + reason ---
    for d, cat in ((gems, "top_gem"), (rf, "red_flag"), (ftse, "ftse_candidate")):
        d["category"] = cat
    raw = pd.concat([gems, rf, ftse], ignore_index=True)
    front = ["category", "reason", "ticker", "date", "close", "pe", "pb", "roe",
             "dividend_yield", "market_cap_ty", "gtgd20_ty", "rs_rating", "structure",
             "exchange", "industry", "foreign_room_pct", "free_float_est", "margin_status"]
    raw = raw[front + [c for c in raw.columns if c not in front]]
    raw.to_csv(SCAN_CSV, index=False, encoding="utf-8-sig")  # BOM để Excel đọc tiếng Việt đúng

    log(f"Kết quả: {len(gems)} gems · {len(rf)} red flags · {len(ftse)} FTSE candidates.")
    log(f"Đã lưu -> {os.path.basename(SCAN_MD)} + {os.path.basename(SCAN_CSV)}")


# ==========================================================================
# KHUNG CHIẾN LƯỢC  (--strategy)
# ==========================================================================
# Mỗi chiến lược là 1 class kế thừa BaseStrategy, đăng ký trong STRATEGIES —
# thêm chiến lược mới = viết class mới + thêm vào registry, KHÔNG sửa CLI.
# DataHub gom mọi nguồn dữ liệu về một cửa: nạp lười + cache, thiếu file nào
# thì chiến lược cần nó bị bỏ qua kèm 1 dòng báo — KHÔNG BAO GIỜ crash.
# Kết quả các chiến lược KHÔNG ghi file riêng lẻ — tất cả đổ về ReportEngine
# để ra đúng 2 file: analysis_latest.json + analysis_latest.md.


def base_ok(live):
    """Bộ lọc nền dùng chung: sạch án sàn + đủ thanh khoản — mọi chiến lược đều nhân thêm."""
    return (live["margin_status"] == "") & (live["gtgd20_ty"] >= LIQ_MIN_TY)


def soft(cond: pd.Series, source: pd.Series) -> pd.Series:
    """Điều kiện 'mềm' trên cột chỉ báo enrichment: mã THIẾU dữ liệu (NaN) coi như ĐẠT.

    Chỉ dùng kiểu PHỦ QUYẾT — mã có dữ liệu chứng minh xấu mới bị loại; mã degraded
    (thiếu OHLCV, mã mới lên sàn) không bị phạt oan. Nhờ vậy fixture selftest
    (không có OHLCV) cho kết quả y hệt bản trước Phase 2."""
    return cond | source.isna()


def smc_lib_note(r) -> str:
    """Chuỗi tóm tắt xác nhận SMC từ thư viện cho 1 dòng đã enrichment (n/a nếu degraded)."""
    if pd.isna(r.get("ms_trend")) and pd.isna(r.get("bos_up_recent")):
        return "n/a"
    parts = []
    if r.get("ms_trend") == 1:
        parts.append("trend↑")
    elif r.get("ms_trend") == -1:
        parts.append("trend↓")
    if r.get("bos_up_recent") == 1:
        parts.append("BOS↑")
    if r.get("choch_up_recent") == 1:
        parts.append("CHoCH↑")
    if r.get("fvg_bull_recent") == 1:
        parts.append("FVG")
    if r.get("ob_bull_recent") == 1:
        parts.append("OB")
    return " ".join(parts) or "—"


def industry_median(live, col):
    """Trung vị NGÀNH của một cột (chỉ tính giá trị dương), trả Series thẳng hàng với live."""
    pos = live[live[col] > 0]
    return live["industry"].map(pos.groupby("industry")[col].median())


def ftse_candidates(live):
    """Bộ lọc ứng viên FTSE — nguồn sự thật DUY NHẤT, dùng chung cho
    --scan-market và FTSEStrategy (tránh 2 nơi 2 logic lệch nhau)."""
    # sàn TP.HCM trong kho ghi là "HSX" (nguồn VCI) — nhận cả 2 cách viết cho chắc
    return live[(live["margin_status"] == "")
                & live["exchange"].isin(("HSX", "HOSE"))
                & (live["market_cap_ty"] >= FTSE_CAP_MIN_TY)
                & (live["gtgd20_ty"] >= FTSE_GTGD_MIN_TY)
                & (live["foreign_room_pct"] > 0)
                & (live["free_float_est"] >= FTSE_FF_MIN)].copy()


def latest_breadth(hub):
    """(dòng ALL, bảng ngành) của phiên breadth mới nhất — (None, None) nếu thiếu nguồn."""
    b = hub.get("breadth")
    if b is None or b.empty:
        return None, None
    b = b[b["date"] == b["date"].max()]
    all_row = b[b["group"] == "ALL"]
    sectors = b[b["group"] != "ALL"].copy()
    return (all_row.iloc[0] if len(all_row) else None), sectors


def json_records(df, cols):
    """DataFrame -> list[dict] sạch cho JSON: NaN -> None, numpy -> kiểu Python thuần."""
    out = []
    for _, r in df.iterrows():
        rec = {}
        for c in cols:
            v = r.get(c)
            if isinstance(v, float):
                rec[c] = None if pd.isna(v) else round(float(v), 2)
            elif hasattr(v, "item"):
                rec[c] = v.item()
            else:
                rec[c] = None if v is None or v != v else v
        out.append(rec)
    return out


class DataHub:
    """Một cửa cho mọi nguồn dữ liệu của kho (đường dẫn khai báo trong FILES)."""

    FILES = {
        "snapshot": SNAPSHOT_CSV,   # bảng lọc chính — load_snapshot() join sẵn metadata
        "breadth": BREADTH_CSV,     # độ rộng thị trường theo ngành
        "macro": MACRO_CSV,         # vĩ mô thế giới + VN (trạng thái hôm nay)
        "news": NEWS_CSV,           # ~100 tin mới nhất
        "signals": SIGNALS_CSV,     # mẫu nến + SMC phiên mới nhất (candle_scan.py)
        "prices": PARQUET,          # lịch sử giá — CHỈ nạp theo mã qua prices()
        "db": DB_FILE,              # vn_stock.db read-only — truy vấn khi thật sự cần
    }

    def __init__(self):
        self._cache = {}
        self.enrich_stats = None    # IndicatorEngine điền sau khi enrich (độ phủ + thời gian)

    def path_ok(self, name):
        return os.path.exists(self.FILES[name])

    def available(self):
        """{tên nguồn: True/False} — dùng cho --list-strategies và kiểm tra REQUIRES."""
        return {n: self.path_ok(n) for n in self.FILES}

    def get(self, name):
        """DataFrame của nguồn dạng bảng, hoặc None nếu thiếu/hỏng — không bao giờ ném lỗi.
        'prices' và 'db' không nạp nguyên cục qua đây: dùng prices() / sqlite khi cần."""
        if name in self._cache:
            return self._cache[name]
        df = None
        try:
            if name == "snapshot" and self.path_ok(name):
                # truyền đường dẫn từ FILES để --selftest trỏ được vào fixture
                df = load_snapshot(self.FILES["snapshot"], self.FILES["db"])
            elif name in ("breadth", "macro", "news", "signals") and self.path_ok(name):
                df = pd.read_csv(self.FILES[name])
        except Exception as e:
            log(f"[CẢNH BÁO] Nạp nguồn '{name}' lỗi ({type(e).__name__}) — coi như thiếu.")
            df = None
        self._cache[name] = df
        return df

    def _live_base(self):
        """Bản gốc live trong cache — nội bộ, đừng trả ra ngoài (dùng live()/live_size())."""
        if "__live__" not in self._cache:
            df = self.get("snapshot")
            self._cache["__live__"] = None if df is None else df[df["date"] == df["date"].max()]
        return self._cache["__live__"]

    def live(self):
        """Snapshot đã lọc ĐÚNG phiên mới nhất (loại mã chết) — lọc 1 lần rồi cache;
        mỗi lần gọi trả BẢN SAO để chiến lược nào lỡ sửa cũng không vấy sang nhau."""
        base = self._live_base()
        return None if base is None else base.copy()

    def live_size(self):
        """Số mã trong phiên live (0 nếu thiếu snapshot) — phục vụ sentinel '0 mã' của run()."""
        base = self._live_base()
        return 0 if base is None else len(base)

    def prices(self, tickers):
        """Lịch sử giá các mã cần (DataFrame rỗng nếu thiếu parquet — load_prices tự xử lý)."""
        return load_prices(tickers)

    def enriched_live(self):
        """live() + cột chỉ báo thư viện (IndicatorEngine) — tính hàng loạt ĐÚNG 1 LẦN
        rồi cache, cả 10 chiến lược + ScoreEngine dùng chung 1 DataFrame làm giàu.
        Thiếu OHLCV -> các cột enrichment toàn NaN, mọi thứ vẫn chạy (degraded)."""
        if "__enriched__" not in self._cache:
            base = self._live_base()
            if base is None:
                self._cache["__enriched__"] = None
            else:
                ind = IndicatorEngine(self).enrich(base["ticker"].tolist())
                self._cache["__enriched__"] = base.merge(ind, on="ticker", how="left")
        e = self._cache["__enriched__"]
        return None if e is None else e.copy()


class IndicatorEngine:
    """Tầng làm giàu chỉ báo (Phase 2) — tính HÀNG LOẠT bằng thư viện vn_indicators.

    Luồng: OHLCV thô (đọc từ vn_stock.db — nguồn TƯƠI nhất, ohlcv_flat.parquet có thể
    cũ hơn snapshot vài phiên) -> tính chỉ báo 1 lần cho mọi mã -> 1 DataFrame
    (mỗi mã 1 dòng giá trị nến cuối) -> chiến lược + chấm điểm CHỈ TIÊU THỤ.
    Mã thiếu lịch sử (<ENRICH_MIN_BARS nến) hoặc lỗi tính -> dòng NaN (degraded),
    KHÔNG BAO GIỜ dừng cả vòng phân tích."""

    COLS = ["adx14", "di_plus14", "di_minus14", "roc20", "mfi14", "cmf20", "obv_up",
            "macd_hist_up", "bb_bw_pct", "bb_squeeze", "ichi_above_cloud", "ms_trend",
            "bos_up_recent", "choch_up_recent", "choch_down_recent",
            "fvg_bull_recent", "ob_bull_recent"]

    def __init__(self, hub):
        self.hub = hub

    def _load_ohlcv(self, tickers=None):
        """OHLCV ~ENRICH_CUTOFF_DAYS ngày gần nhất từ vn_stock.db (read-only).
        None nếu thiếu DB/bảng ohlcv (fixture selftest rơi vào nhánh này)."""
        db = self.hub.FILES["db"]
        if not os.path.exists(db):
            return None
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                dmax = con.execute("SELECT MAX(date) FROM ohlcv").fetchone()[0]
                if not dmax:
                    return None
                cut = (pd.Timestamp(dmax) - pd.Timedelta(days=ENRICH_CUTOFF_DAYS)).strftime("%Y-%m-%d")
                q = ("SELECT ticker, date, open, high, low, close, volume FROM ohlcv"
                     " WHERE date >= ?")
                params = [cut]
                if tickers is not None:     # chế độ focus: chỉ kéo đúng vài mã cần
                    q += " AND ticker IN (%s)" % ",".join("?" * len(tickers))
                    params += list(tickers)
                return pd.read_sql(q + " ORDER BY ticker, date", con, params=params)
            finally:
                con.close()
        except Exception as e:
            log(f"[CẢNH BÁO] Không đọc được OHLCV từ vn_stock.db ({type(e).__name__})"
                " — bỏ qua chỉ báo mở rộng, phân tích tiếp bằng snapshot (degraded).")
            return None

    def _one(self, g):
        """Chỉ báo thư viện cho 1 mã (g = OHLCV đã sort theo date) -> dict giá trị nến cuối."""
        g = g.tail(ENRICH_BARS).reset_index(drop=True)
        out = {}
        ax = vi.adx(g, 14)
        out["adx14"] = ax["adx"].iloc[-1]
        out["di_plus14"] = ax["plus_di"].iloc[-1]
        out["di_minus14"] = ax["minus_di"].iloc[-1]
        out["roc20"] = vi.roc(g, 20).iloc[-1]
        out["mfi14"] = vi.mfi(g, 14).iloc[-1]
        out["cmf20"] = vi.cmf(g, 20).iloc[-1]
        obv = vi.obv(g)
        obv_ma = obv.rolling(20).mean().iloc[-1]
        out["obv_up"] = float(obv.iloc[-1] > obv_ma) if pd.notna(obv_ma) else float("nan")
        hist = vi.macd(g)["macd_hist"]
        out["macd_hist_up"] = float(hist.iloc[-1] > hist.iloc[-2]) if len(hist) > 1 else float("nan")
        bw = vi.bollinger_bands(g)["bb_bandwidth"]
        out["bb_bw_pct"] = bw.iloc[-1]
        nen = bw.tail(120).dropna()   # squeeze = band hẹp nhất 20% trong ~6 tháng
        out["bb_squeeze"] = (float(bw.iloc[-1] <= nen.quantile(0.2))
                             if len(nen) >= 60 and pd.notna(bw.iloc[-1]) else float("nan"))
        ich = vi.ichimoku(g).iloc[-1]
        # cần ĐỦ cả 2 span mới kết luận mây (max(x, NaN) của Python trả x — không dùng được)
        sa_, sb_ = ich["senkou_a"], ich["senkou_b"]
        out["ichi_above_cloud"] = (float(g["close"].iloc[-1] > max(sa_, sb_))
                                   if pd.notna(sa_) and pd.notna(sb_) else float("nan"))
        ms = vi.market_structure(g, 2)
        out["ms_trend"] = ms["ms_trend"].iloc[-1]
        t = SMC_RECENT_BARS
        out["bos_up_recent"] = float(ms["bos_up"].tail(t).any())
        out["choch_up_recent"] = float(ms["choch_up"].tail(t).any())
        out["choch_down_recent"] = float(ms["choch_down"].tail(t).any())
        out["fvg_bull_recent"] = float(vi.fair_value_gap(g)["fvg_bull"].tail(t).any())
        out["ob_bull_recent"] = float(vi.order_block(g)["ob_bull"].tail(t).any())
        return out

    def enrich(self, tickers):
        """DataFrame cột ['ticker'] + COLS cho ĐỦ danh sách mã yêu cầu — mã thiếu
        dữ liệu là dòng NaN. Ghi độ phủ + thời gian vào hub.enrich_stats."""
        t0 = datetime.now()
        rows, n_err = {}, 0
        px = self._load_ohlcv(sorted(set(tickers)) if len(tickers) <= 50 else None)
        if px is not None and not px.empty:
            want = set(tickers)
            for tk, g in px.groupby("ticker", sort=False):
                if tk not in want or len(g) < ENRICH_MIN_BARS:
                    continue
                try:
                    rows[tk] = self._one(g)
                except Exception:   # 1 mã hỏng không được dừng cả vòng enrichment
                    n_err += 1
        out = pd.DataFrame.from_dict(rows, orient="index").reindex(columns=self.COLS)
        out = out.reindex(list(dict.fromkeys(tickers)))   # đủ mọi mã, giữ thứ tự, khử trùng lặp
        out.index.name = "ticker"
        dt = (datetime.now() - t0).total_seconds()
        n_ok = int(out["adx14"].notna().sum())
        self.hub.enrich_stats = {"n_ok": n_ok, "n_total": len(out),
                                 "seconds": round(dt, 1), "n_errors": n_err}
        if px is not None:
            log(f"[indicators] Làm giàu chỉ báo thư viện: {n_ok}/{len(out)} mã trong {dt:.1f}s"
                + (f" ({n_err} mã lỗi tính — degraded)" if n_err else "")
                + " — mã thiếu lịch sử dùng điểm công thức gốc.")
        return out.reset_index()


class BaseStrategy:
    """Lớp nền cho mọi chiến lược lọc.

    Lớp con khai báo NAME / DESC / REQUIRES và cài screen() trả về
    (df_kết_quả, ghi_chú_tiêu_chí, cols, headers). run() lo phần chung:
    kiểm tra nguồn -> screen -> trả dict kết quả gọn cho ReportEngine
    (KHÔNG ghi file riêng — báo cáo hợp nhất chỉ có 2 file analysis_latest.*).
    """
    NAME = "base"
    DESC = ""
    REQUIRES = ("snapshot",)   # nguồn bắt buộc (khóa trong DataHub.FILES)
    IMPLEMENTED = True

    def __init__(self, hub):
        self.hub = hub

    def live_snapshot(self):
        """Snapshot phiên mới nhất ĐÃ LÀM GIÀU chỉ báo thư viện (loại mã chết kiểu ASA).
        (Ủy quyền cho DataHub.enriched_live() — snapshot lọc 1 lần + enrichment tính
        1 lần, dùng chung cho cả 10 chiến lược và ScoreEngine; thiếu OHLCV thì các
        cột chỉ báo là NaN và mọi filter thư viện tự cho qua.)"""
        return self.hub.enriched_live()

    def screen(self):
        """-> (df, note, cols, headers). Lớp con bắt buộc cài."""
        raise NotImplementedError

    def run(self):
        """Chạy chiến lược, trả dict kết quả cho ReportEngine (None nếu bỏ qua/lỗi)."""
        missing = [n for n in self.REQUIRES if not self.hub.path_ok(n)]
        if missing:
            log(f"[BỎ QUA] '{self.NAME}': thiếu nguồn {', '.join(missing)} — chạy pipeline sinh file trước.")
            return None
        try:
            df, note, cols, headers = self.screen()
        except NotImplementedError:
            log(f"[CHƯA CÀI] '{self.NAME}' ({self.DESC}).")
            return None
        except Exception as e:  # 1 chiến lược hỏng không được kéo sập cả phiên chạy
            log(f"[LỖI] '{self.NAME}': {type(e).__name__}: {e} — bỏ qua chiến lược này.")
            return None
        # Guard 3 — sentinel "0 mã": universe đủ lớn mà không mã nào qua filter là dấu hiệu
        # kinh điển của filter sai cột/giá trị (bug HSX trả 0 mã trong im lặng suốt 2 ngày)
        if len(df) == 0 and self.hub.live_size() >= EMPTY_WARN_MIN_UNIVERSE:
            log(f"[CẢNH BÁO] Chiến lược '{self.NAME}' trả 0 mã dù universe có"
                f" {self.hub.live_size()} mã — nghi filter sai cột/giá trị"
                " (bài học HSX vs HOSE), kiểm tra ngưỡng + dữ liệu nguồn.")
        log(f"'{self.NAME}': {len(df)} mã đạt tiêu chí.")
        return {"name": self.NAME, "desc": self.DESC, "note": note,
                "count": int(len(df)), "cols": cols, "headers": headers,
                "picks": json_records(df.head(STRAT_TOP_N), cols),
                "all_tickers": df["ticker"].tolist()}


class ValueStrategy(BaseStrategy):
    """Đầu tư giá trị: rẻ so với NGÀNH chứ không rẻ tuyệt đối
    (PE 8 của thép khác PE 8 của ngân hàng) + chất lượng (ROE) + cổ tức thật.
    [Review Phase 2] Giữ nguyên thuần cơ bản — chỉ báo kỹ thuật không thuộc luận điểm
    value; phần kỹ thuật đã phản ánh qua ScoreEngine (blend thư viện) khi xếp hạng."""
    NAME = "value"
    DESC = "định giá rẻ so với ngành + sinh lời cao + có cổ tức"
    REQUIRES = ("snapshot", "db")

    def screen(self):
        live = self.live_snapshot()
        pe_nganh = industry_median(live, "pe")
        pb_nganh = industry_median(live, "pb")
        m = (base_ok(live)
             & (live["pe"] > 0) & (live["pe"] <= pe_nganh)
             & (live["pb"] > 0) & (live["pb"] <= pb_nganh)
             & (live["roe"] >= GEM_ROE_MIN)
             & (live["dividend_yield"] > 0))
        df = live[m].copy()
        df["pe_nganh"] = pe_nganh[m].round(1)
        df = df.sort_values("roe", ascending=False)
        note = (f"Sạch án · GTGD>={LIQ_MIN_TY} tỷ · 0<PE<=trung vị ngành · 0<PB<=trung vị ngành"
                f" · ROE>={GEM_ROE_MIN}% · có cổ tức. So PE/PB theo NGÀNH để khỏi so táo với cam.")
        cols = ["ticker", "industry", "close", "pe", "pe_nganh", "pb", "roe", "dividend_yield", "rs_rating"]
        headers = ["Mã", "Ngành", "Giá", "PE", "PE ngành", "PB", "ROE %", "Cổ tức %", "RS"]
        return df, note, cols, headers


class CANSLIMStrategy(BaseStrategy):
    """CANSLIM — đúng công thức FILTER trong README mục 2.4, cộng lọc luật
    (bài học ASA: RS 99 nhưng đang bị đình chỉ)."""
    NAME = "canslim"
    DESC = "cổ phiếu dẫn dắt kiểu CANSLIM (RS cao, gần đỉnh, có volume)"
    REQUIRES = ("snapshot",)

    def screen(self):
        live = self.live_snapshot()
        m = (base_ok(live)
             & (live["rs_rating"] >= CANSLIM_RS_MIN)
             & live["above_sma200"]
             & (live["pct_from_52w_high"] >= -15)
             & (live["rel_vol"] >= 1))
        df = live[m].sort_values("rs_rating", ascending=False).copy()
        # Phase 2 — cột thông tin tích lũy kiểu O'Neil (không lọc): OBV > SMA20 của OBV
        # nghĩa là khối lượng đang dồn về phe mua (Accumulation)
        df["obv_up"] = df["obv_up"].map({1.0: "có", 0.0: "—"}).fillna("n/a")
        note = (f"RS>={CANSLIM_RS_MIN} · trên MA200 · cách đỉnh 52T trong 15% · rel_vol>=1"
                f" · GTGD>={LIQ_MIN_TY} tỷ · sạch án — đúng công thức FILTER của README mục 2.4."
                " Cột 'OBV tích lũy' (vn_indicators) = khối lượng đang dồn phe mua.")
        cols = ["ticker", "industry", "close", "rs_rating", "pct_from_52w_high", "rel_vol",
                "gtgd20_ty", "structure", "obv_up"]
        headers = ["Mã", "Ngành", "Giá", "RS", "Cách đỉnh %", "Rel vol", "GTGD20 (tỷ)",
                   "Cấu trúc", "OBV tích lũy"]
        return df, note, cols, headers


class MomentumStrategy(BaseStrategy):
    """Momentum thuần: sức mạnh giá trên nhiều khung + xác nhận xu hướng.
    (Dòng tiền 20/60 phiên chi tiết đã có ở chế độ --tickers, không nạp parquet ở đây
    để quét toàn thị trường vẫn nhanh và nhẹ.)"""
    NAME = "momentum"
    DESC = "đà tăng giá + dòng tiền vào (RS, ret 1-3 tháng, golden cross)"
    REQUIRES = ("snapshot",)

    def screen(self):
        live = self.live_snapshot()
        m = (base_ok(live)
             & (live["rs_rating"] >= MOM_RS_MIN)
             & (live["ret_1m"] > 0) & (live["ret_3m"] > 0)
             & (live["golden_cross"] | live["above_sma50"])
             # Phase 2 — xác nhận bằng thư viện (soft: mã thiếu OHLCV cho qua):
             & soft(live["adx14"] >= MOM_ADX_MIN, live["adx14"])              # xu hướng phải CÓ LỰC
             & soft(live["di_plus14"] > live["di_minus14"], live["adx14"]))   # phe mua đang thắng (DMI)
        df = live[m].sort_values("ret_3m", ascending=False).copy()
        note = (f"RS>={MOM_RS_MIN} · ret 1 tháng VÀ 3 tháng cùng dương · golden cross HOẶC trên MA50"
                f" · ADX>={MOM_ADX_MIN} và +DI>-DI (xác nhận lực xu hướng, mã thiếu dữ liệu chỉ báo"
                " được cho qua) · nền sạch án + đủ thanh khoản.")
        cols = ["ticker", "industry", "close", "rs_rating", "ret_1m", "ret_3m", "ret_6m",
                "rel_vol", "adx14", "roc20"]
        headers = ["Mã", "Ngành", "Giá", "RS", "1 tháng %", "3 tháng %", "6 tháng %",
                   "Rel vol", "ADX", "ROC20 %"]
        return df, note, cols, headers


class FTSEStrategy(BaseStrategy):
    """Ứng viên FTSE: điều kiện investability — dùng chung bộ lọc ftse_candidates()
    với --scan-market (một nguồn sự thật, không lệch nhau).
    [Review Phase 2] Giữ nguyên — tiêu chí FTSE là vốn hóa/thanh khoản/room/free float,
    chỉ báo kỹ thuật không liên quan luận điểm này."""
    NAME = "ftse"
    DESC = "vốn hóa lớn + thanh khoản cao + còn room (ứng viên FTSE)"
    REQUIRES = ("snapshot", "db")

    def screen(self):
        live = self.live_snapshot()
        df = ftse_candidates(live).sort_values("market_cap_ty", ascending=False)
        df["free_float_pct"] = (df["free_float_est"] * 100).round(1)
        note = (f"HOSE · vốn hóa>={FTSE_CAP_MIN_TY:,.0f} tỷ · GTGD>={FTSE_GTGD_MIN_TY} tỷ/phiên"
                f" · còn room ngoại · free float>={FTSE_FF_MIN:.0%} · sạch án."
                " free_float_est là proxy tự tính, không phải số FTSE chính thức.")
        cols = ["ticker", "industry", "market_cap_ty", "gtgd20_ty", "foreign_room_pct", "free_float_pct", "rs_rating"]
        headers = ["Mã", "Ngành", "Vốn hóa (tỷ)", "GTGD20 (tỷ)", "Room ngoại %", "Free float %", "RS"]
        return df, note, cols, headers


class FScoreStrategy(BaseStrategy):
    """F-Score PROXY — KHÔNG phải Piotroski chuẩn: bản gốc cần BCTC nhiều kỳ
    (dòng tiền, biên lãi, đòn bẩy...) mà kho chỉ có ROE/PE/PB trailing một thời
    điểm, nên thay bằng 9 tiêu chí chất lượng + xác nhận của thị trường."""
    NAME = "fscore"
    DESC = "chấm điểm sức khỏe tài chính (bản proxy theo dữ liệu kho có)"
    REQUIRES = ("snapshot", "db")
    # [Review Phase 2] GIỮ NGUYÊN 9 tiêu chí — thang /9 là khế ước với fixture selftest
    # và người dùng; nhồi chỉ báo kỹ thuật vào F-Score làm loãng ý nghĩa "sức khỏe
    # tài chính". Phần kỹ thuật của mã đã có ScoreEngine (blend thư viện) lo.

    def screen(self):
        live = self.live_snapshot()
        f = ((live["roe"] > 0).astype(int)                                   # 1. có lãi
             + (live["roe"] >= GEM_ROE_MIN).astype(int)                      # 2. sinh lời cao
             + ((live["pe"] > 0) & (live["pe"] <= 15)).astype(int)           # 3. định giá hợp lý
             + ((live["pb"] > 0) & (live["pb"] <= GEM_PB_MAX)).astype(int)   # 4. không đắt theo sổ sách
             + (live["dividend_yield"] > 0).astype(int)                      # 5. có trả cổ tức thật
             + live["above_sma200"].astype(int)                              # 6. thị trường xác nhận dài hạn
             + (live["structure"] == "up").astype(int)                       # 7. cấu trúc giá tăng
             + (live["gtgd20_ty"] >= LIQ_MIN_TY).astype(int)                 # 8. đủ thanh khoản
             + (live["margin_status"] == "").astype(int))                    # 9. sạch án sàn
        df = live.copy()
        df["f_proxy"] = f
        # Nền sạch là điều kiện LOẠI THẲNG (đúng khế ước base_ok "mọi chiến lược đều nhân
        # thêm"), không chỉ trừ điểm — kẻo mã đình chỉ đạt 8/9 vẫn nằm trong danh sách "khỏe"
        df = df[base_ok(live) & (df["f_proxy"] >= FSCORE_MIN)].sort_values(
            ["f_proxy", "roe"], ascending=False)
        note = (f"Đạt >= {FSCORE_MIN}/9 tiêu chí proxy (lãi, ROE cao, PE<=15, PB<={GEM_PB_MAX},"
                " cổ tức, MA200, cấu trúc up, thanh khoản, sạch án) VÀ nền sạch (án sàn/kém"
                " thanh khoản bị loại thẳng, không chỉ trừ điểm). LƯU Ý: đây là bản PROXY,"
                " không phải Piotroski chuẩn — kho chưa có BCTC nhiều kỳ.")
        cols = ["ticker", "industry", "f_proxy", "roe", "pe", "pb", "dividend_yield", "structure"]
        headers = ["Mã", "Ngành", "F-proxy /9", "ROE %", "PE", "PB", "Cổ tức %", "Cấu trúc"]
        return df, note, cols, headers


class SMCStrategy(BaseStrategy):
    """Smart Money Concept: tín hiệu SMC bullish (FVG/OB/BOS) của candle_scan
    trên mã đang ở vùng discount. Nhớ README 4.3: mẫu nến là TRIGGER nhiễu cao —
    chỉ dùng làm điểm vào cho mã đã qua lọc nền."""
    NAME = "smc"
    DESC = "tín hiệu Smart Money (discount + FVG/OB/BOS từ candle_scan)"
    REQUIRES = ("snapshot", "signals")

    def screen(self):
        live = self.live_snapshot()
        sig = self.hub.get("signals")
        if sig is None or sig.empty:
            return live.iloc[0:0].copy(), "ta_signals.csv rỗng — chạy candle_scan.py trước.", ["ticker"], ["Mã"]
        sig = sig.copy()
        sig["ticker"] = sig["ticker"].astype(str).str.upper()
        sig = sig[(sig["direction"] == "bullish")
                  & sig["smc"].fillna("").str.contains("bull")]
        base = live[base_ok(live) & (live["dist_swing_low_pct"] <= SMC_DISCOUNT_MAX)
                    # Phase 2: cấu trúc VỪA gãy xuống (CHoCH↓ trong 10 nến, thư viện
                    # market_structure) thì đừng bắt dao rơi — NaN != 1 tự cho qua
                    & (live["choch_down_recent"] != 1)]
        df = base.merge(sig[["ticker", "patterns", "smc", "confluence"]], on="ticker", how="inner")
        df["confluence"] = as_bool(df["confluence"])
        # Phase 2: cột xác nhận từ thư viện (BOS↑/CHoCH↑/FVG/OB trên toàn bộ lịch sử giá,
        # không chỉ phiên cuối như candle_scan) — càng nhiều xác nhận xếp càng cao
        df["smc_lib"] = df.apply(smc_lib_note, axis=1)
        lib_n = ((df["bos_up_recent"] == 1).astype(int) + (df["choch_up_recent"] == 1).astype(int)
                 + (df["fvg_bull_recent"] == 1).astype(int) + (df["ob_bull_recent"] == 1).astype(int))
        df = df.assign(_lib_n=lib_n).sort_values(
            ["confluence", "_lib_n", "rs_rating"], ascending=False).drop(columns="_lib_n")
        note = (f"Vùng discount (cách swing low <= {SMC_DISCOUNT_MAX}%) + tín hiệu SMC bullish"
                " (FVG/OB/BOS) phiên mới nhất · KHÔNG có CHoCH↓ trong 10 nến (thư viện"
                " vn_indicators — tránh bắt dao rơi) · nền sạch án + đủ thanh khoản."
                " Cột 'SMC thư viện' = xác nhận cấu trúc từ vn_indicators."
                " Trigger nhiễu cao — không phải tín hiệu mua độc lập (README 4.3).")
        cols = ["ticker", "industry", "close", "dist_swing_low_pct", "smc", "smc_lib",
                "patterns", "confluence", "rs_rating"]
        headers = ["Mã", "Ngành", "Giá", "Cách swing low %", "SMC", "SMC thư viện",
                   "Mẫu nến", "Hội tụ", "RS"]
        return df, note, cols, headers


class BreakoutStrategy(BaseStrategy):
    """Phá đỉnh kiểu Darvas/O'Neil: sát đỉnh 52 tuần + khối lượng bùng nổ xác nhận."""
    NAME = "breakout"
    DESC = "sát đỉnh 52 tuần + khối lượng bùng nổ (rel_vol cao)"
    REQUIRES = ("snapshot",)

    def screen(self):
        live = self.live_snapshot()
        m = (base_ok(live)
             & live["near_52w_high"]
             & (live["rel_vol"] >= BRK_RELVOL_MIN)
             & (live["rs_rating"] >= BRK_RS_MIN)
             & (live["structure"] != "down"))
        df = live[m].sort_values("rel_vol", ascending=False).copy()
        # Phase 2 — bối cảnh CHẤT LƯỢNG breakout từ thư viện (thông tin, không lọc):
        # squeeze = Bollinger bandwidth hẹp nhất 20% trong ~6 tháng (nền chặt trước khi nổ);
        # BOS↑ = close đã phá swing high xác nhận (market_structure) trong 10 nến
        df["bb_squeeze"] = df["bb_squeeze"].map({1.0: "có", 0.0: "—"}).fillna("n/a")
        df["bos_up_recent"] = df["bos_up_recent"].map({1.0: "có", 0.0: "—"}).fillna("n/a")
        note = (f"Sát đỉnh 52T (near_52w_high) · rel_vol>={BRK_RELVOL_MIN} (khối lượng xác nhận)"
                f" · RS>={BRK_RS_MIN} · cấu trúc không giảm · nền sạch án + thanh khoản."
                " Cột Squeeze (nền Bollinger siết chặt) + BOS↑ (phá cấu trúc, vn_indicators)"
                " là bối cảnh chất lượng — squeeze 'có' thì breakout đáng tin hơn.")
        cols = ["ticker", "industry", "close", "chg_today_pct", "rel_vol", "rs_rating",
                "pct_from_52w_high", "gtgd20_ty", "bb_squeeze", "bos_up_recent"]
        headers = ["Mã", "Ngành", "Giá", "% Phiên", "Rel vol", "RS", "Cách đỉnh %",
                   "GTGD20 (tỷ)", "Squeeze", "BOS↑"]
        return df, note, cols, headers


class TurnaroundStrategy(BaseStrategy):
    """Đảo chiều: bị bán cả năm nhưng 3 tháng gần nhất hồi mạnh và đang có lãi —
    nhóm rủi ro cao hơn trung bình, vào thăm dò chứ đừng all-in."""
    NAME = "turnaround"
    DESC = "12 tháng giảm nhưng 3 tháng hồi mạnh + đang có lãi"
    REQUIRES = ("snapshot",)

    def screen(self):
        live = self.live_snapshot()
        m = (base_ok(live)
             & (live["ret_12m"] < 0)
             & (live["ret_3m"] >= TURN_RET3M_MIN)
             & live["above_sma50"]
             & (live["pe"] > 0)
             # Phase 2: CMF20 không âm sâu — đảo chiều thật phải có tiền quay lại,
             # tiền còn RÚT mạnh thì mới chỉ là hồi kỹ thuật (soft: thiếu dữ liệu cho qua)
             & soft(live["cmf20"] > TURN_CMF_MIN, live["cmf20"]))
        df = live[m].sort_values("ret_3m", ascending=False).copy()
        note = (f"ret 12 tháng < 0 (bị bán cả năm) NHƯNG ret 3 tháng >= {TURN_RET3M_MIN}%"
                f" · giá đã lấy lại MA50 · PE>0 (có lãi) · CMF20>{TURN_CMF_MIN} (dòng tiền"
                " Chaikin không còn rút mạnh, mã thiếu dữ liệu chỉ báo được cho qua)"
                " · nền sạch án + thanh khoản.")
        cols = ["ticker", "industry", "close", "ret_12m", "ret_3m", "ret_1m", "cmf20", "pe", "roe", "rs_rating"]
        headers = ["Mã", "Ngành", "Giá", "12 tháng %", "3 tháng %", "1 tháng %", "CMF20", "PE", "ROE %", "RS"]
        return df, note, cols, headers


class RelativeStrengthStrategy(BaseStrategy):
    """RS thuần: top ~10% mã mạnh nhất thị trường — RS cao không nói LÝ DO,
    nên đối chiếu thêm value/fscore trước khi xuống tiền."""
    NAME = "rs"
    DESC = "top sức mạnh giá tương đối (RS >= 90)"
    REQUIRES = ("snapshot",)

    def screen(self):
        live = self.live_snapshot()
        m = base_ok(live) & (live["rs_rating"] >= RS_ELITE_MIN)
        df = live[m].sort_values(["rs_rating", "gtgd20_ty"], ascending=False).copy()
        note = (f"RS>={RS_ELITE_MIN} · sạch án · GTGD>={LIQ_MIN_TY} tỷ."
                " Cột ADX (vn_indicators) cho biết đà có LỰC hay chỉ là RS ăn theo nền thấp."
                " RS cao không nói lý do — đối chiếu value/fscore trước khi mua.")
        cols = ["ticker", "industry", "close", "rs_rating", "adx14", "ret_1m", "ret_3m", "structure", "gtgd20_ty"]
        headers = ["Mã", "Ngành", "Giá", "RS", "ADX", "1 tháng %", "3 tháng %", "Cấu trúc", "GTGD20 (tỷ)"]
        return df, note, cols, headers


class SectorRotationStrategy(BaseStrategy):
    """Xoay ngành: tiền chảy theo ngành — chọn mã mạnh TRONG các ngành mạnh nhất
    (điểm ngành tính từ market_breadth.csv: % mã trên MA200 + RS trung bình).
    [Review Phase 2] Giữ nguyên — đơn vị phân tích là NGÀNH (breadth), chỉ báo
    theo mã không đổi được luận điểm; xếp hạng mã trong ngành đã có RS + ScoreEngine."""
    NAME = "sector"
    DESC = "mã RS cao trong các ngành mạnh nhất (sector rotation)"
    REQUIRES = ("snapshot", "breadth")

    def screen(self):
        live = self.live_snapshot()
        _, sectors = latest_breadth(self.hub)
        if sectors is None or sectors.empty:
            return live.iloc[0:0].copy(), "Thiếu market_breadth.csv.", ["ticker"], ["Mã"]
        s = sectors[sectors["n_symbols"] >= SECTOR_MIN_SYMBOLS].copy()
        s["sector_score"] = ((s["pct_above_ma200"] + s["avg_rs_rating"]) / 2).round(1)
        top = s.sort_values("sector_score", ascending=False).head(SECTOR_TOP_N)
        m = (base_ok(live)
             & live["industry"].isin(top["group"])
             & (live["rs_rating"] >= 70)
             & live["above_sma200"])
        df = live[m].merge(top[["group", "sector_score"]].rename(columns={"group": "industry"}),
                           on="industry", how="left")
        df = df.sort_values(["sector_score", "rs_rating"], ascending=False)
        names = " · ".join(f"{r.group} ({r.sector_score:.0f}đ)" for r in top.itertuples())
        note = (f"Top {SECTOR_TOP_N} ngành mạnh nhất (điểm ngành = trung bình của %mã trên MA200"
                f" và RS bq, chỉ xét ngành >= {SECTOR_MIN_SYMBOLS} mã): {names}."
                " Trong ngành lấy mã RS>=70 · trên MA200 · nền sạch.")
        cols = ["ticker", "industry", "sector_score", "close", "rs_rating", "ret_1m", "gtgd20_ty"]
        headers = ["Mã", "Ngành", "Điểm ngành", "Giá", "RS", "1 tháng %", "GTGD20 (tỷ)"]
        return df, note, cols, headers


# Registry — thêm class mới vào đây là tự xuất hiện trong CLI, không sửa main()
STRATEGIES = {c.NAME: c for c in (
    ValueStrategy, CANSLIMStrategy, MomentumStrategy, FTSEStrategy,
    FScoreStrategy, SMCStrategy, BreakoutStrategy, TurnaroundStrategy,
    RelativeStrengthStrategy, SectorRotationStrategy)}


def list_strategies():
    """In danh sách chiến lược + tình trạng nguồn dữ liệu (--list-strategies)."""
    hub = DataHub()
    avail = hub.available()
    log("Nguồn dữ liệu: " + " · ".join(
        f"{n}={'có' if ok else 'THIẾU'}" for n, ok in avail.items()))
    log("Chiến lược:")
    for name in sorted(STRATEGIES):
        cls = STRATEGIES[name]
        miss = [s for s in cls.REQUIRES if not avail.get(s, False)]
        impl = "đã cài" if cls.IMPLEMENTED else "chưa cài — phase sau"
        src = "nguồn đủ" if not miss else "THIẾU " + ", ".join(miss)
        log(f"  {name:<9} {cls.DESC}  [{impl} · {src}]")


# ==========================================================================
# CHẤM ĐIỂM 0-100  (ScoreEngine)
# ==========================================================================
# Điểm tổng = tổng có trọng số (SCORE_WEIGHTS) của 6 cấu phần, mỗi cấu phần 0-100:
#   fundamental : ROE theo bậc (tối đa 40đ) + PE 10/15/25 (30đ) + PB 1.5/3 (15đ) + cổ tức 7/3/0% (15đ)
#   technical   : GỐC = MA200 30đ + MA50 20đ + cấu trúc up 20đ (side 10đ) + gần đỉnh 52T 20đ
#                 + golden cross 10đ. Mã CÓ enrichment: 0.8*GỐC + 0.2*THƯ VIỆN, trong đó
#                 THƯ VIỆN = trên mây Ichimoku 40đ + cấu trúc thị trường tăng (ms_trend=+1) 35đ
#                 + BOS↑/CHoCH↑ trong 10 nến 25đ (vn_indicators).
#   momentum    : GỐC = RS/99*50đ + ret 1m>0 15đ + ret 3m>0 15đ + ret 6m>0 10đ + rel_vol>=1 10đ.
#                 Mã CÓ enrichment: 0.8*GỐC + 0.2*THƯ VIỆN, trong đó THƯ VIỆN = ADX bậc
#                 40/25/20 (40/30/15đ) + DMI phe mua thắng 20đ + MFI>=50 20đ + CMF>0 10đ
#                 + OBV tích lũy 10đ.
#   liquidity   : GTGD20 bậc 100/30/10/3/1 tỷ (50đ) + vốn hóa bậc 50k/10k/3k/1k tỷ (30đ)
#                 + còn room ngoại 10đ + free float 30%/15% (10đ)
#   macro       : 0.5*breadth thị trường + 0.3*breadth NGÀNH của mã + điểm VIX (tối đa 20đ)
#                 (mã cùng ngành có điểm macro giống nhau — đó là chủ ý)
#   risk        : 100 trừ dần: án sàn -60 · lỗ -20 · GTGD<3 tỷ -20 · penny<1.000đ -20
#                 · RSI>75 -10 · ATR>8% -10 · kín room -5 · CHoCH↓ 10 nến -10 · MFI>85 -5
#                 (2 khoản cuối chỉ trừ khi CÓ dữ liệu thư viện; 100 = an toàn nhất)
# DEGRADED: mã không đủ lịch sử OHLCV (hoặc lỗi tính chỉ báo) giữ NGUYÊN công thức GỐC
# — không cộng không trừ gì từ thư viện, không bao giờ vì thiếu chỉ báo mà mất điểm.
# Từng mã trong Top Stocks đều kèm chuỗi giải thích 6 cấu phần trong JSON/MD.


class ScoreEngine:
    """Chấm điểm 0-100 cho mọi mã live — công thức mô tả ở khối comment ngay trên."""

    COMPONENTS = ("fundamental", "technical", "momentum", "liquidity", "macro", "risk")

    def __init__(self, hub):
        self.hub = hub

    def market_context(self):
        """Bối cảnh chung 1 lần/phiên: regime + breadth + ngành + VIX (thiếu nguồn -> trung tính)."""
        all_row, sectors = latest_breadth(self.hub)
        breadth_pct = float(all_row["pct_above_ma200"]) if all_row is not None else float("nan")
        if pd.isna(breadth_pct):
            regime = "không rõ (thiếu breadth)"
        elif breadth_pct >= 55:
            regime = "tích cực"
        elif breadth_pct >= 35:
            regime = "trung tính"
        else:
            regime = "phòng thủ"
        vix_pts, macro_notes = 10, []   # thiếu VIX -> 10đ trung tính
        macro = self.hub.get("macro")
        if macro is not None and "series" in macro.columns:
            for _, r in macro.iterrows():
                sid = str(r["series"]).lower()
                if "vix" in sid and pd.notna(r["value"]):
                    v = float(r["value"])
                    vix_pts = 20 if v < 15 else (14 if v < 20 else (8 if v < 25 else 0))
                    macro_notes.insert(0, f"VIX {v:.1f}")
                elif any(k in sid for k in ("dxy", "10y", "brent", "gold", "usd_vnd")):
                    macro_notes.append(f"{r['name']}: {fmt(r['value'], 2)}")
        return {"regime": regime, "breadth_pct": breadth_pct, "all_row": all_row,
                "sectors": sectors, "vix_pts": vix_pts, "macro_notes": macro_notes}

    def score(self, live, hits):
        """Trả (DataFrame đã có 6 cột score_* + score + strategies, ctx bối cảnh)."""
        ctx = self.market_context()
        d = live.copy()
        roe, pe, pb, div = d["roe"], d["pe"], d["pb"], d["dividend_yield"]

        d["score_fundamental"] = (
            np.select([roe >= 20, roe >= GEM_ROE_MIN, roe >= 10, roe > 0], [40, 32, 24, 12], 0)
            + np.select([(pe > 0) & (pe <= 10), (pe > 0) & (pe <= 15), (pe > 0) & (pe <= 25)], [30, 22, 12], 0)
            + np.select([(pb > 0) & (pb <= 1.5), (pb > 0) & (pb <= 3)], [15, 8], 0)
            + np.select([div >= GEM_DIV_MIN, div >= 3, div > 0], [15, 10, 4], 0))

        base_tech = (
            d["above_sma200"].astype(int) * 30 + d["above_sma50"].astype(int) * 20
            + np.select([d["structure"] == "up", d["structure"] == "side"], [20, 10], 0)
            + np.select([d["pct_from_52w_high"] >= -15, d["pct_from_52w_high"] >= -30], [20, 10], 0)
            + d["golden_cross"].astype(int) * 10)

        base_mom = (
            d["rs_rating"].clip(0, 99) / 99 * 50
            + (d["ret_1m"] > 0).astype(int) * 15 + (d["ret_3m"] > 0).astype(int) * 15
            + (d["ret_6m"] > 0).astype(int) * 10 + (d["rel_vol"] >= 1).astype(int) * 10)

        # --- Phase 2: blend điểm thư viện vn_indicators KHI mã có enrichment ---
        # (NaN == x luôn False -> mã degraded có lib_* = 0 nhưng không dùng vì has_ind=False:
        #  giữ nguyên điểm GỐC, thiếu chỉ báo không bao giờ làm mất điểm)
        has_ind = d["adx14"].notna()
        lib_tech = (40 * (d["ichi_above_cloud"] == 1).astype(int)          # trên mây Ichimoku
                    + 35 * (d["ms_trend"] == 1).astype(int)                # cấu trúc thị trường tăng
                    + 25 * ((d["bos_up_recent"] == 1)                      # vừa phá cấu trúc lên
                            | (d["choch_up_recent"] == 1)).astype(int))
        lib_mom = (np.select([d["adx14"] >= 40, d["adx14"] >= 25, d["adx14"] >= MOM_ADX_MIN],
                             [40, 30, 15], 0)                              # lực xu hướng
                   + 20 * (d["di_plus14"] > d["di_minus14"]).astype(int)   # DMI phe mua thắng
                   + 20 * (d["mfi14"] >= 50).astype(int)                   # dòng tiền (MFI)
                   + 10 * (d["cmf20"] > 0).astype(int)                     # tích lũy Chaikin
                   + 10 * (d["obv_up"] == 1).astype(int))                  # OBV trên nền 20 phiên
        d["score_technical"] = np.where(has_ind, (1 - LIB_BLEND) * base_tech + LIB_BLEND * lib_tech,
                                        base_tech)
        d["score_momentum"] = np.where(has_ind, (1 - LIB_BLEND) * base_mom + LIB_BLEND * lib_mom,
                                       base_mom)

        g, cap = d["gtgd20_ty"], d["market_cap_ty"]
        d["score_liquidity"] = (
            np.select([g >= 100, g >= 30, g >= 10, g >= LIQ_MIN_TY, g >= 1], [50, 40, 30, 20, 10], 0)
            + np.select([cap >= 50_000, cap >= FTSE_CAP_MIN_TY, cap >= 3_000, cap >= 1_000, cap > 0],
                        [30, 25, 18, 10, 5], 0)
            + (d["foreign_room_pct"] > 0).astype(int) * 10
            + np.select([d["free_float_est"] >= 0.30, d["free_float_est"] >= FTSE_FF_MIN], [10, 5], 0))

        breadth_eff = 50.0 if pd.isna(ctx["breadth_pct"]) else ctx["breadth_pct"]
        sector_map = ({} if ctx["sectors"] is None else
                      dict(zip(ctx["sectors"]["group"], ctx["sectors"]["pct_above_ma200"])))
        sec_pct = d["industry"].map(sector_map).fillna(breadth_eff)
        d["score_macro"] = 0.5 * breadth_eff + 0.3 * sec_pct + ctx["vix_pts"]

        d["score_risk"] = (100
                           - (d["margin_status"] != "").astype(int) * 60
                           - ((d["pe"] <= 0) | (d["roe"] < 0)).astype(int) * 20
                           - (d["gtgd20_ty"] < LIQ_MIN_TY).astype(int) * 20
                           - (d["close"] < 1000).astype(int) * 20
                           - (d["rsi14"] > 75).astype(int) * 10
                           - (d["atr_pct"] > 8).astype(int) * 10
                           - (d["foreign_room_pct"] == 0).astype(int) * 5
                           # Phase 2 — chỉ trừ khi CÓ dữ liệu thư viện (NaN so sánh = False):
                           - (d["choch_down_recent"] == 1).astype(int) * 10   # cấu trúc vừa gãy xuống
                           - (d["mfi14"] > 85).astype(int) * 5)               # dòng tiền quá nóng

        for name in self.COMPONENTS:  # NaN (mã thiếu dữ liệu) -> 0, ép về khung 0-100
            c = f"score_{name}"
            d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0).clip(0, 100).round(0)
        d["score"] = sum(d[f"score_{k}"] * w for k, w in SCORE_WEIGHTS.items()).round(1)
        d["strategies"] = d["ticker"].map(lambda t: hits.get(t, []))
        return d, ctx

    @staticmethod
    def explain(r):
        """Chuỗi giải thích 6 cấu phần điểm của 1 mã (đưa vào Top Stocks của JSON/MD).
        Các chỉ báo thư viện chỉ xuất hiện khi mã CÓ dữ liệu enrichment."""
        tech = ", ".join(x for x, ok in [
            ("trên MA200", r["above_sma200"]), ("trên MA50", r["above_sma50"]),
            (f"cấu trúc {str(r['structure']).upper()}", True),
            (f"cách đỉnh 52T {fmt(r['pct_from_52w_high'])}%", True),
            ("golden cross", r["golden_cross"]),
            ("trên mây Ichimoku", r.get("ichi_above_cloud") == 1),
            ("BOS↑ gần đây", r.get("bos_up_recent") == 1),
            ("CHoCH↑ gần đây", r.get("choch_up_recent") == 1)] if ok)
        mom_lib = (f", ADX {fmt(r.get('adx14'), 0)}, MFI {fmt(r.get('mfi14'), 0)},"
                   f" CMF {fmt(r.get('cmf20'), 2)}"
                   if pd.notna(r.get("adx14")) else "")
        risk_lib = (", cấu trúc vừa gãy (CHoCH↓)" if r.get("choch_down_recent") == 1 else "")
        return {
            "fundamental": f"{r['score_fundamental']:.0f}đ — ROE {fmt(r['roe'])}%, PE {fmt(r['pe'])},"
                           f" PB {fmt(r['pb'], 2)}, cổ tức {fmt(r['dividend_yield'])}%",
            "technical": f"{r['score_technical']:.0f}đ — {tech}",
            "momentum": f"{r['score_momentum']:.0f}đ — RS {fmt(r['rs_rating'], 0)}, ret 1/3/6 tháng:"
                        f" {fmt(r['ret_1m'])}/{fmt(r['ret_3m'])}/{fmt(r['ret_6m'])}%" + mom_lib,
            "liquidity": f"{r['score_liquidity']:.0f}đ — GTGD20 {fmt(r['gtgd20_ty'])} tỷ, vốn hóa"
                         f" {fmt(r['market_cap_ty'], 0)} tỷ, room ngoại {fmt(r['foreign_room_pct'])}%",
            "macro": f"{r['score_macro']:.0f}đ — breadth thị trường + ngành {r['industry']} + mức VIX",
            "risk": f"{r['score_risk']:.0f}đ — "
                    + (f"án sàn {r['margin_status']}" if r["margin_status"] else "không án sàn")
                    + f", RSI {fmt(r['rsi14'])}, ATR {fmt(r['atr_pct'])}%" + risk_lib,
        }


# ==========================================================================
# BÁO CÁO HỢP NHẤT  (ReportEngine) — đúng 2 file: analysis_latest.json + .md
# ==========================================================================

class ReportEngine:
    """Gom kết quả chiến lược + điểm số thành analysis_latest.json (máy/AI đọc, đủ nhẹ
    để upload) + analysis_latest.md (người đọc, sinh từ chính payload JSON). Đồng thời
    lưu top điểm vào bảng watchlist_history của vn_stock.db (nền cho backtest sau)."""

    def __init__(self, hub, out_json: str = REPORT_JSON, out_md: str = REPORT_MD,
                 db_file: str = DB_FILE):
        # 3 đường dẫn tham số hóa CHỈ cho --selftest (ghi vào thư mục tạm) — mặc định = hành vi cũ
        self.hub = hub
        self.out_json = out_json
        self.out_md = out_md
        self.db_file = db_file

    def build(self, strategy_results):
        live = self.hub.enriched_live()   # snapshot + chỉ báo thư viện (cache — không tính lại)
        if live is None:
            log("[LỖI] Thiếu screen_snapshot.csv — không chấm điểm/báo cáo được.")
            return
        latest = live["date"].max()
        log(f"Đang chấm điểm 0-100 cho {len(live)} mã phiên {latest}...")

        # mã -> danh sách chiến lược bắt được (all_tickers chỉ dùng nội bộ, không vào JSON)
        hits = {}
        for res in strategy_results:
            for t in res.pop("all_tickers", []):
                hits.setdefault(t, []).append(res["name"])

        scored, ctx = ScoreEngine(self.hub).score(live, hits)
        scored = scored.sort_values(["score", "score_risk"], ascending=False)
        top = scored.head(TOP_PICKS)

        # --- top_stocks: điểm + 6 cấu phần + giải thích + chiến lược bắt được ---
        base_cols = ["ticker", "industry", "exchange", "close", "score", "score_fundamental",
                     "score_technical", "score_momentum", "score_liquidity", "score_macro", "score_risk"]
        top_stocks = json_records(top, base_cols)
        for rec, (_, r) in zip(top_stocks, top.iterrows()):
            rec["strategies"] = hits.get(rec["ticker"], [])
            rec["explain"] = ScoreEngine.explain(r)

        # --- scores: toàn bộ mã live, dạng gọn [điểm, cb, kt, đà, tk, vĩ mô, rủi ro] ---
        scores = {r.ticker: [round(float(r.score), 1)] + [int(getattr(r, f"score_{k}"))
                                                          for k in ScoreEngine.COMPONENTS]
                  for r in scored.itertuples()}

        # --- market ---
        sectors_json = []
        if ctx["sectors"] is not None and not ctx["sectors"].empty:
            s = ctx["sectors"].sort_values("pct_above_ma200", ascending=False)
            sectors_json = json_records(s, ["group", "n_symbols", "pct_above_ma200",
                                            "avg_rs_rating", "avg_ret_1m"])
        breadth_json = None
        if ctx["all_row"] is not None:
            arow = pd.DataFrame([ctx["all_row"]])
            breadth_json = json_records(arow, list(arow.columns))[0]
        market = {"regime": ctx["regime"], "breadth": breadth_json,
                  "sectors": sectors_json, "macro_highlights": ctx["macro_notes"][:8]}

        # --- risks (cấp thị trường) ---
        risks = []
        if not pd.isna(ctx["breadth_pct"]) and ctx["breadth_pct"] < 35:
            risks.append(f"Độ rộng yếu: chỉ {ctx['breadth_pct']:.1f}% mã trên MA200 —"
                         " chỉ số có thể bị vài trụ kéo, đa số mã vẫn trong xu hướng xuống.")
        if ctx["vix_pts"] == 0:
            risks.append("VIX > 25 — khẩu vị rủi ro toàn cầu xấu, cân nhắc giảm tỷ trọng.")
        flags = live[((live["pe"] <= 0) | (live["roe"] < 0) | (live["margin_status"] != ""))
                     & (live["gtgd20_ty"] >= 10)]
        if len(flags):
            tops = ", ".join(flags.sort_values("gtgd20_ty", ascending=False)["ticker"].head(5))
            risks.append(f"{len(flags)} mã thanh khoản cao (GTGD>=10 tỷ) dính cờ đỏ"
                         f" (lỗ/ROE âm/án sàn) — nổi bật: {tops}.")
        risks.append("Điểm số và metadata là point-in-time HÔM NAY — chỉ dùng lọc live,"
                     " không dùng backtest (README mục 4.2).")

        # --- gợi ý danh mục: cơ học theo điểm, ép đa dạng ngành, chặn mã rủi ro ---
        eq_pct = {"tích cực": 70, "trung tính": 50, "phòng thủ": 30}.get(ctx["regime"], 40)
        picks, per_ind = [], {}
        for _, r in scored.iterrows():
            if r["score_risk"] < PORT_RISK_MIN or per_ind.get(r["industry"], 0) >= PORT_MAX_PER_IND:
                continue
            picks.append(r)
            per_ind[r["industry"]] = per_ind.get(r["industry"], 0) + 1
            if len(picks) >= PORT_N:
                break
        tot = sum(float(p["score"]) for p in picks) or 1.0
        positions = [{"ticker": p["ticker"], "industry": p["industry"],
                      "weight_pct": round(float(p["score"]) / tot * eq_pct, 1),
                      "score": round(float(p["score"]), 1),
                      "strategies": hits.get(p["ticker"], [])} for p in picks]
        portfolio = {"regime": ctx["regime"], "equity_pct": eq_pct, "cash_pct": 100 - eq_pct,
                     "positions": positions,
                     "note": f"Phân bổ CƠ HỌC theo điểm: tối đa {PORT_MAX_PER_IND} mã/ngành,"
                             f" chỉ nhận mã có điểm rủi ro >= {PORT_RISK_MIN}, tỷ trọng tỷ lệ"
                             " với điểm tổng. Tham khảo — KHÔNG phải khuyến nghị đầu tư."}

        # --- summary + score_method ---
        stats = self.hub.enrich_stats
        summary = {"generated_at": f"{datetime.now():%Y-%m-%d %H:%M}",
                   "session_date": str(latest), "n_stocks_live": int(len(live)),
                   "regime": ctx["regime"],
                   "pct_above_ma200": None if pd.isna(ctx["breadth_pct"]) else round(ctx["breadth_pct"], 1),
                   "strategy_counts": {r["name"]: r["count"] for r in strategy_results},
                   "indicator_coverage": (f"{stats['n_ok']}/{stats['n_total']} mã có chỉ báo thư viện"
                                          f" ({stats['seconds']}s)" if stats
                                          else "0 mã — thiếu OHLCV, điểm dùng công thức gốc (degraded)"),
                   "top_ticker": top_stocks[0]["ticker"] if top_stocks else None}
        score_method = {
            "weights": SCORE_WEIGHTS,
            "scores_order": ["score"] + list(ScoreEngine.COMPONENTS),
            "components": {
                "fundamental": "ROE theo bậc 20/15/10/0% (tối đa 40đ) + PE 10/15/25 (30đ) + PB 1.5/3 (15đ) + cổ tức 7/3/0% (15đ)",
                "technical": "GỐC: MA200 30đ + MA50 20đ + cấu trúc up 20đ (side 10đ) + gần đỉnh 52T 15%/30%"
                             " (20/10đ) + golden cross 10đ. Có chỉ báo thư viện: 0.8*GỐC + 0.2*(mây Ichimoku"
                             " 40đ + cấu trúc tăng 35đ + BOS↑/CHoCH↑ 10 nến 25đ)",
                "momentum": "GỐC: RS/99*50đ + ret 1m>0 15đ + ret 3m>0 15đ + ret 6m>0 10đ + rel_vol>=1 10đ."
                            " Có chỉ báo thư viện: 0.8*GỐC + 0.2*(ADX 40/25/20 bậc 40/30/15đ + DMI mua 20đ"
                            " + MFI>=50 20đ + CMF>0 10đ + OBV tích lũy 10đ)",
                "liquidity": "GTGD20 bậc 100/30/10/3/1 tỷ (50đ) + vốn hóa bậc 50k/10k/3k/1k tỷ (30đ) + còn room 10đ + free float 30%/15% (10/5đ)",
                "macro": "0.5*breadth thị trường + 0.3*breadth ngành + VIX <15/<20/<25 (20/14/8đ) — mã cùng ngành điểm macro giống nhau",
                "risk": "100 trừ: án sàn 60 · lỗ 20 · GTGD<3 tỷ 20 · penny<1.000đ 20 · RSI>75 10 · ATR>8% 10"
                        " · kín room 5 · CHoCH↓ 10 nến 10 · MFI>85 5 (2 khoản cuối chỉ khi có chỉ báo;"
                        " 100 = an toàn nhất)",
            },
            "indicator_blend": f"Chỉ báo thư viện vn_indicators tính từ OHLCV vn_stock.db (>= {ENRICH_MIN_BARS}"
                               f" nến, tối đa {ENRICH_BARS} nến/mã). Mã thiếu dữ liệu giữ NGUYÊN công thức gốc"
                               " — degraded gracefully, không mất điểm vì thiếu chỉ báo.",
            "limits": "Kho chưa có ROA/D-E/BCTC nhiều kỳ; cấu phần cơ bản dựa trên số trailing"
                      " point-in-time — tuyệt đối không dùng điểm này để backtest.",
        }

        strategies_json = [{"name": r["name"], "desc": r["desc"], "criteria": r["note"],
                            "count": r["count"], "top_picks": r["picks"]} for r in strategy_results]
        payload = {"summary": summary, "market": market, "top_stocks": top_stocks,
                   "scores": scores, "strategies": strategies_json, "risks": risks,
                   "portfolio_suggestions": portfolio, "score_method": score_method}

        try:  # OneDrive sync có thể khóa file — mất 1 lần ghi không được mất cả phiên chạy
            with open(self.out_json, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
            self.write_md(payload, strategy_results)
        except OSError as e:
            log(f"[LỖI] Không ghi được báo cáo ({type(e).__name__}: {e}) — chờ OneDrive sync xong rồi chạy lại.")
            return
        self.save_watchlist(top, str(latest))
        kb_json = os.path.getsize(self.out_json) / 1024
        kb_md = os.path.getsize(self.out_md) / 1024
        log(f"Đã lưu -> {os.path.basename(self.out_json)} ({kb_json:.0f} KB)"
            f" + {os.path.basename(self.out_md)} ({kb_md:.0f} KB)")

    def write_md(self, p, strategy_results):
        """Sinh analysis_latest.md (người đọc) từ chính payload JSON — không tính lại gì."""
        s, mk = p["summary"], p["market"]
        parts = [f"# Báo cáo phân tích tổng hợp — phiên {s['session_date']}",
                 f"\n*Sinh bởi `stock_analyzer.py` lúc {s['generated_at']} · {s['n_stocks_live']} mã live"
                 f" · chế độ thị trường: **{s['regime']}**.*\n"]

        parts.append("## Tóm tắt\n")
        parts.append(f"- Độ rộng: **{fmt(s['pct_above_ma200'])}% mã trên MA200** → chế độ **{s['regime']}**.")
        parts.append("- Kết quả chiến lược: "
                     + " · ".join(f"{k} **{v}**" for k, v in s["strategy_counts"].items()) + " mã.")
        if p["top_stocks"]:
            t0 = p["top_stocks"][0]
            parts.append(f"- Điểm cao nhất: **{t0['ticker']} {t0['score']}đ** ({t0['industry']}).")

        parts.append("\n## Thị trường\n")
        if mk["breadth"]:
            b = mk["breadth"]
            parts.append(f"- Tăng/giảm/đứng: **{b.get('n_up')}/{b.get('n_down')}/{b.get('n_flat')}**"
                         f" · RS bq {b.get('avg_rs_rating')} · ret 1 tháng bq {b.get('avg_ret_1m')}%.")
        if mk["macro_highlights"]:
            parts.append("- Vĩ mô: " + " · ".join(str(x) for x in mk["macro_highlights"]) + ".")
        if mk["sectors"]:
            sec = pd.DataFrame(mk["sectors"])
            parts.append("\n**Ngành mạnh nhất / yếu nhất (% mã trên MA200):**\n")
            parts.append(md_table(pd.concat([sec.head(3), sec.tail(3)]),
                                  ["group", "n_symbols", "pct_above_ma200", "avg_rs_rating", "avg_ret_1m"],
                                  ["Ngành", "Số mã", "% trên MA200", "RS bq", "Ret 1m bq %"]))

        parts.append(f"\n## Top {len(p['top_stocks'])} cổ phiếu theo điểm tổng\n")
        parts.append(md_table(pd.DataFrame(p["top_stocks"]),
                              ["ticker", "industry", "score", "score_fundamental", "score_technical",
                               "score_momentum", "score_liquidity", "score_macro", "score_risk"],
                              ["Mã", "Ngành", "Điểm", "Cơ bản", "Kỹ thuật", "Đà", "Thanh khoản", "Vĩ mô", "Rủi ro"]))
        parts.append("\n### Giải thích điểm từng mã\n")
        for t in p["top_stocks"]:
            strats = f" _(bắt bởi: {', '.join(t['strategies'])})_" if t["strategies"] else ""
            parts.append(f"- **{t['ticker']} — {t['score']}đ**{strats}")
            for k, label in (("fundamental", "Cơ bản"), ("technical", "Kỹ thuật"),
                             ("momentum", "Đà tăng"), ("liquidity", "Thanh khoản"),
                             ("macro", "Vĩ mô"), ("risk", "Rủi ro")):
                parts.append(f"  - {label}: {t['explain'][k]}")

        parts.append(f"\n## Kết quả chiến lược ({len(strategy_results)} đã chạy)\n")
        for r in strategy_results:
            parts.append(f"\n### `{r['name']}` — {r['count']} mã\n\n{r['note']}\n")
            if r["picks"]:
                parts.append(md_table(pd.DataFrame(r["picks"]), r["cols"], r["headers"]))
                if r["count"] > len(r["picks"]):
                    parts.append(f"\n*Hiện {len(r['picks'])}/{r['count']} mã điểm cao nhất.*")

        parts.append("\n## Rủi ro\n")
        parts += [f"- {x}" for x in p["risks"]]

        po = p["portfolio_suggestions"]
        parts.append("\n## Gợi ý danh mục (cơ học)\n")
        parts.append(f"Chế độ **{po['regime']}** → cổ phiếu **{po['equity_pct']}%** · tiền mặt **{po['cash_pct']}%**.\n")
        if po["positions"]:
            pos = pd.DataFrame(po["positions"])
            pos["strategies"] = pos["strategies"].map(lambda v: " · ".join(v) if v else "—")
            parts.append(md_table(pos, ["ticker", "industry", "weight_pct", "score", "strategies"],
                                  ["Mã", "Ngành", "Tỷ trọng %", "Điểm", "Chiến lược bắt được"]))
        parts.append(f"\n*{po['note']}*")

        parts.append("\n## Cách chấm điểm\n")
        parts.append("Trọng số: " + " · ".join(f"{k} {v:.0%}" for k, v in SCORE_WEIGHTS.items()) + "\n")
        for k, v in p["score_method"]["components"].items():
            parts.append(f"- **{k}**: {v}")
        parts.append(f"\n> {p['score_method']['limits']}")
        parts.append("\n---\n*Dữ liệu sinh tự động, chỉ mang tính tham khảo — không phải khuyến nghị đầu tư.*")
        with open(self.out_md, "w", encoding="utf-8") as fh:
            fh.write("\n".join(parts))

    def save_watchlist(self, top, session_date):
        """Lưu TOP_PICKS vào bảng watchlist_history của vn_stock.db — bảng RIÊNG của analyzer,
        không đụng bảng nào của pipeline. Khóa (session_date, ticker) + INSERT OR REPLACE
        nên chạy lại cùng phiên không sinh bản ghi trùng. Đây là dữ liệu nền cho Backtester."""
        if not os.path.exists(self.db_file):
            log("[CẢNH BÁO] Không có vn_stock.db — bỏ qua lưu watchlist_history.")
            return
        con = None
        try:
            con = sqlite3.connect(self.db_file, timeout=10)
            con.execute("""CREATE TABLE IF NOT EXISTS watchlist_history(
                session_date TEXT NOT NULL, ticker TEXT NOT NULL, run_ts TEXT,
                score REAL, fundamental REAL, technical REAL, momentum REAL,
                liquidity REAL, macro REAL, risk REAL, close REAL, strategies TEXT,
                PRIMARY KEY(session_date, ticker))""")
            ts = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
            rows = [(session_date, r["ticker"], ts, float(r["score"]),
                     float(r["score_fundamental"]), float(r["score_technical"]),
                     float(r["score_momentum"]), float(r["score_liquidity"]),
                     float(r["score_macro"]), float(r["score_risk"]),
                     float(r["close"]), ", ".join(r["strategies"]))
                    for _, r in top.iterrows()]
            con.executemany("INSERT OR REPLACE INTO watchlist_history VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            con.commit()
            log(f"Đã lưu {len(rows)} mã vào watchlist_history (vn_stock.db).")
        except Exception as e:  # OneDrive lock/DB bận — báo cáo file vẫn đầy đủ, không crash
            log(f"[CẢNH BÁO] Không lưu được watchlist_history ({type(e).__name__}: {e}).")
        finally:
            if con is not None:
                con.close()


class Backtester:
    """KHUNG cho phase sau — CHƯA CÀI trong class này (chủ đích). Ý tưởng gốc ("mỗi lần chạy
    --strategy, top điểm lưu vào watchlist_history kèm giá close phiên ký; backtest = join bảng đó
    với ohlcv để đo hiệu suất T+N") đã được triển khai ở SCRIPT RIÊNG `watchlist_eval.py` (gốc repo,
    2026-07-17) thay vì trong class này — dùng `python watchlist_eval.py` để xem forward return
    T+5/T+20/T+60 + excess return so VN-Index, không look-ahead. Giữ class này làm điểm neo lịch sử
    trong stock_analyzer.py; không nhân đôi logic ở đây."""

    def __init__(self, hub):
        self.hub = hub

    def run(self):
        raise NotImplementedError(
            "Dùng `python watchlist_eval.py` (script riêng, đã cài) thay vì class này.")


def run_selftest() -> int:
    """--selftest: chạy unittest trên tests/ (fixture nhỏ, không đụng dữ liệu thật) —
    chốt chặn hồi quy lớp bug HSX. Exit 0 = pass, khác 0 = có test hỏng."""
    import unittest
    tests_dir = os.path.join(ROOT, "tests")
    if not os.path.isdir(tests_dir):
        log("[LỖI] Thiếu thư mục tests/ — repo không đầy đủ, không tự kiểm được.")
        return 1
    suite = unittest.defaultTestLoader.discover(tests_dir, pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    log(f"--selftest: {'PASS' if result.wasSuccessful() else 'FAIL'}"
        f" ({result.testsRun} test, {len(result.failures)} fail, {len(result.errors)} lỗi)")
    return 0 if result.wasSuccessful() else 1


# ==========================================================================
# MAIN
# ==========================================================================

def main():
    ap = argparse.ArgumentParser(
        description="Phân tích kho dữ liệu VNSTOCK offline (không gọi mạng, không tốn request).")
    ap.add_argument("--tickers", nargs="+", metavar="MÃ",
                    help="phân tích sâu các mã (VD: --tickers SSI PAN EVF POW HPG) -> Focus_Analysis.md")
    ap.add_argument("--scan-market", action="store_true",
                    help="quét toàn thị trường (gems / red flags / FTSE) -> Market_Scan.md + .csv")
    ap.add_argument("--strategy", choices=sorted(STRATEGIES) + ["all"], metavar="TÊN",
                    help="chạy chiến lược lọc + chấm điểm 0-100 (" + ", ".join(sorted(STRATEGIES))
                         + " hoặc all) -> analysis_latest.json + analysis_latest.md")
    ap.add_argument("--list-strategies", action="store_true",
                    help="liệt kê chiến lược + tình trạng nguồn dữ liệu rồi thoát")
    ap.add_argument("--selftest", action="store_true",
                    help="chạy test hồi quy trên fixture (tests/) — exit 0 nếu pass")
    args = ap.parse_args()
    if not (args.tickers or args.scan_market or args.strategy
            or args.list_strategies or args.selftest):
        ap.print_help()
        return 1

    if args.selftest:
        return run_selftest()

    if args.list_strategies:
        list_strategies()
        return 0

    # --- 2 chế độ cũ: giữ nguyên hành vi (tương thích ngược) ---
    if args.tickers or args.scan_market:
        log("Đang nạp dữ liệu (snapshot + metadata)...")
        df = load_snapshot()
        log(f"Snapshot: {len(df)} mã, phiên mới nhất {df['date'].max()}.")
        if args.tickers:
            run_focus(df, args.tickers)
        if args.scan_market:
            run_scan(df)

    # --- chế độ chiến lược: chạy các chiến lược rồi gom về 1 báo cáo hợp nhất ---
    if args.strategy:
        hub = DataHub()  # snapshot chỉ nạp 1 lần (cache) cho cả 10 chiến lược + chấm điểm
        names = sorted(STRATEGIES) if args.strategy == "all" else [args.strategy]
        results = [r for r in (STRATEGIES[n](hub).run() for n in names) if r]
        ReportEngine(hub).build(results)

    log("Hoàn tất.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
