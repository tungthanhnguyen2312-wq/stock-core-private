import os
import sys
import time
import sqlite3
import random
from datetime import datetime
import pandas as pd

# ==========================================
# CẤU HÌNH HỆ THỐNG
# ==========================================
DB_PATH = "vn_stock.db"
OUT_DIR = "."
START_DATE = "2015-01-01"
INTERVAL = "1D"

PRIMARY_SRC = "VCI"    # Trả về đơn vị nghìn (K-VND)
# [FIX 2026-07-10] Quote của vnstock v4 chỉ nhận source: kbs/vci/msn/dnse/bina -> TCBS bị loại,
# fallback đổi sang KBS. Đã kiểm chứng: KBS cũng trả giá đơn vị NGHÌN (HPG close 23.2 = 23.200đ).
FAILOVER_SRC = "KBS"
SOURCE_SCALES = {"VCI": 1000, "KBS": 1000}   # map đơn vị giá theo nguồn (kiểm chứng 2026-07)

REQUEST_DELAY = 1.1
MAX_RETRY = 3
BACKOFF_BASE = 5        # lỗi mạng: chờ 5/10/15s
BACKOFF_RATE = 15       # rate-limit: chờ 15/30/45s — cửa sổ đếm quota là 60 GIÂY trượt,
                        # chờ ngắn hơn thì retry vẫn dính cửa sổ cũ, phí lượt
BATCH_SIZE = 300

INDEX_SYMBOLS = ["VNINDEX", "HNXINDEX", "UPCOMINDEX"]
USE_FILE = True
TICKERS_FILE = "tickers.txt"
WATCHLIST = ["SSI", "EVF", "PAN", "HPG", "FPT", "PVD", "QNS", "VNM", "POW", "PDR", "NLG"]

# ==========================================
# CÔNG CỤ XỬ LÝ & ĐỒNG BỘ DỮ LIỆU
# ==========================================
def _quote(symbol, source):
    from vnstock.api.quote import Quote
    return Quote(symbol=symbol, source=source, random_agent=True)

def get_universe():
    if USE_FILE and os.path.exists(TICKERS_FILE):
        with open(TICKERS_FILE, encoding="utf-8") as f:
            base = [ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")]
    else:
        base = WATCHLIST
    return INDEX_SYMBOLS + [t for t in base if t not in INDEX_SYMBOLS]

def load_full_universe():
    from vnstock.api.listing import Listing
    df = Listing(source="VCI").symbols_by_exchange()
    tcol = next((c for c in df.columns if "type" in c.lower()), None)
    if tcol:
        df = df[df[tcol].astype(str).str.upper().isin(["STOCK", "CS"])]
    scol = next(c for c in df.columns if "symbol" in c.lower() or "ticker" in c.lower())
    tickers = sorted(df[scol].astype(str).str.upper().unique())
    with open(TICKERS_FILE, "w", encoding="utf-8") as f:
        f.write("# Mã cổ phiếu 3 sàn (tự sinh). Thêm mã hủy niêm yết vào cuối file nếu cần.\n")
        f.write("\n".join(tickers))
    print(f" [universe] {len(tickers)} mã -> {TICKERS_FILE}")
    return tickers

def init_db(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS ohlcv(
        ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
        volume INTEGER, source TEXT, PRIMARY KEY(ticker, date))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON ohlcv(date)")
    conn.execute("""CREATE TABLE IF NOT EXISTS meta(
        ticker TEXT PRIMARY KEY, status TEXT, rows INTEGER, updated TEXT)""")
    conn.commit()

def resolve_scale(ticker, source, med_close):
    """Scale giá: TIN MAP NGUỒN là chính; median chỉ là backstop cho lỗi thô.
    - Chỉ số (VNINDEX...) tính bằng ĐIỂM -> không bao giờ scale.
    - <50đ sau scale: không tồn tại trên TTCK VN (tick tối thiểu 100đ) -> chắc chắn thiếu x1000.
    - >1.5 triệu đồng/cp sau scale: không tồn tại -> chắc chắn double-scale.
    - Vùng 50đ..1000đ là mơ hồ (penny thật vs lệch chuẩn) -> GIỮ THEO MAP + in cảnh báo."""
    if ticker.upper() in INDEX_SYMBOLS:
        return 1
    scale = SOURCE_SCALES.get(source.upper(), 1)
    if pd.isna(med_close):
        return scale
    sm = med_close * scale
    if sm < 50:
        print(f"   [scale] {ticker}@{source}: median {med_close:.3f} quá nhỏ -> ép x1000")
        return 1000
    if sm > 1_500_000:
        print(f"   [scale] {ticker}@{source}: median {sm:,.0f} quá lớn -> hạ về x1")
        return 1
    if sm < 1000:
        print(f"   [cảnh báo] {ticker}@{source}: trung vị {sm:,.0f}đ — penny thật hay lệch scale? nên kiểm tra tay")
    return scale

def normalize(df, ticker, source):
    if df is None or len(df) == 0:
        return None
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    tcol = next((c for c in ("time", "tradingdate", "date") if c in df.columns), None)
    if tcol is None:
        return None

    date = pd.to_datetime(df[tcol]).dt.strftime("%Y-%m-%d")
    out = pd.DataFrame({c: (df[c] if c in df.columns else pd.NA) for c in ("open", "high", "low", "close", "volume")})
    out["date"], out["ticker"], out["source"] = date.values, ticker, source

    # Lọc dòng thiếu giá / phiên volume=0 (lễ, đình chỉ GD) / trùng ngày
    out = out.dropna(subset=["close"])
    out = out[out["volume"].fillna(0) > 0].drop_duplicates(subset=["date"], keep="last")
    if len(out) == 0:
        return None

    for c in ("open", "high", "low", "close"):
        out[c] = pd.to_numeric(out[c], errors="coerce")

    # --- FIX BẪY 1 + BẪY PENNY: scale theo nguồn, median chỉ là backstop ---
    scale = resolve_scale(ticker, source, out["close"].median())
    for c in ("open", "high", "low", "close"):
        out[c] = out[c] * scale

    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0).astype("int64")
    return out[["ticker", "date", "open", "high", "low", "close", "volume", "source"]]

def fetch_one(ticker, start, end):
    empty_source_count = 0
    for source in (PRIMARY_SRC, FAILOVER_SRC):
        for attempt in range(1, MAX_RETRY + 1):
            try:
                raw = _quote(ticker, source).history(start=start, end=end, interval=INTERVAL)
                if raw is None or len(raw) == 0:
                    empty_source_count += 1
                    break  # nguồn này xác nhận rỗng -> sang nguồn dự phòng
                df = normalize(raw, ticker, source)
                if df is not None and len(df):
                    return df
                break
            except Exception as e:
                # --- FIX 2026-07-10: KBS bọc lỗi gốc trong RetryError (tenacity) nên message
                # đọc được chỉ là "RetryError[<Future...>]" -> phải bóc last_attempt.exception()
                # ra mới phân loại đúng. VD lỗi gốc "Dữ liệu trống cho mã ARM" = mã không có
                # nến trong khoảng (KBS NÉM lỗi thay vì trả rỗng như VCI) -> là RỖNG, không phải lỗi.
                inner = getattr(getattr(e, "last_attempt", None), "exception", lambda: None)()
                m = str(inner if inner is not None else e).lower()
                if any(k in m for k in ("dữ liệu trống", "no data", "empty")):
                    empty_source_count += 1
                    break  # nguồn này xác nhận không có dữ liệu -> sang nguồn dự phòng
                is_rate_limit = any(k in m for k in ("rate", "429", "quá nhiều", "too many"))
                is_network_err = any(k in m for k in ("timeout", "connection", "disconnected", "reset", "502", "503", "504"))
                # --- FIX BẪY 3: retry mọi lỗi mạng tạm thời ---
                if is_rate_limit or is_network_err:
                    wait = (BACKOFF_RATE if is_rate_limit else BACKOFF_BASE) * attempt + random.uniform(0, 2)
                    lbl = "Rate-Limit" if is_rate_limit else "Lỗi Mạng Tạm Thời"
                    print(f"   [{lbl}] {ticker}@{source} - Thử lại sau {wait:.1f}s (Lần {attempt}/{MAX_RETRY})")
                    time.sleep(wait)
                else:
                    print(f"   [Lỗi Hệ Thống] {ticker}@{source}: {str(inner if inner is not None else e)[:70]}")
                    break
    if empty_source_count == 2:
        return "EMPTY_DATA"
    return None

# ==========================================
# HỆ THỐNG LỆNH ĐIỀU KHIỂN
# ==========================================
def cmd_backfill(mode="pending"):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH); init_db(conn)
    universe = get_universe()
    meta = dict(conn.execute("SELECT ticker, status FROM meta").fetchall())

    if mode == "failed":
        todo = [t for t in universe if meta.get(t) == "failed"]
    else:
        todo = [t for t in universe if meta.get(t) not in ("done", "empty")]

    total_left = len(todo)
    if BATCH_SIZE > 0:
        todo = todo[:BATCH_SIZE]
    print(f"[backfill: {mode}] Xử lý {len(todo)}/{total_left} mã còn lại (Tổng Universe: {len(universe)})")

    for i, tk in enumerate(todo, 1):
        df = fetch_one(tk, START_DATE, today)
        if df is not None:
            if isinstance(df, str) and df == "EMPTY_DATA":
                set_meta(conn, tk, "empty", 0)
                print(f" {i:>4}/{len(todo)} {tk:<10} -> TRỐNG/HỦY NIÊM YẾT (loại trừ vĩnh viễn)")
            else:
                upsert(conn, df)
                set_meta(conn, tk, "done", len(df))
                print(f" {i:>4}/{len(todo)} {tk:<10} +{len(df):>5} dòng giá ({df['source'].iloc[0]})")
        else:
            set_meta(conn, tk, "failed", 0)
            print(f" {i:>4}/{len(todo)} {tk:<10} -> THẤT BẠI (lỗi kết nối, chạy `backfill failed` để thử lại)")
        time.sleep(REQUEST_DELAY)

    done_count = conn.execute("SELECT COUNT(*) FROM meta WHERE status='done'").fetchone()[0]
    empty_count = conn.execute("SELECT COUNT(*) FROM meta WHERE status='empty'").fetchone()[0]
    conn.close()
    print(f"[backfill] Tiến độ: Done={done_count} | Empty={empty_count} | Còn lại={total_left - len(todo)}")

def cmd_update():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH); init_db(conn)
    last = dict(conn.execute("SELECT ticker, MAX(date) FROM ohlcv GROUP BY ticker").fetchall())
    universe = [t for t in get_universe() if t in last]
    print(f" [update] Quét phần bù hằng ngày cho {len(universe)} mã hoạt động -> {today}")
    ok_count = 0
    for i, tk in enumerate(universe, 1):
        start = last[tk]
        if start >= today:
            continue
        df = fetch_one(tk, start, today)
        if df is not None and not isinstance(df, str):
            upsert(conn, df); ok_count += 1
            print(f" {i:>4}/{len(universe)} {tk:<10} +{len(df)} dòng mới (Từ {start})")
        time.sleep(REQUEST_DELAY)
    conn.close()
    print(f" [update] Hoàn tất: {ok_count} mã có dữ liệu mới.")

def cmd_status():
    conn = sqlite3.connect(DB_PATH); init_db(conn)
    total = len(get_universe())
    rows = dict(conn.execute("SELECT status, COUNT(*) FROM meta GROUP BY status").fetchall())
    bars = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
    conn.close()
    print(f"[status] Done={rows.get('done',0)} | Empty={rows.get('empty',0)} | Failed={rows.get('failed',0)}")
    print(f"         Chưa xử lý={total - sum(rows.values())} | Tổng kho={bars:,} dòng giá.")

def cmd_export():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM ohlcv ORDER BY ticker, date", conn); conn.close()
    if df.empty:
        print(" [export] Kho dữ liệu rỗng."); return
    pq_path = os.path.join(OUT_DIR, "ohlcv_flat.parquet")
    csv_path = os.path.join(OUT_DIR, "ohlcv_flat.csv")
    df.to_parquet(pq_path, index=False)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f" [export] {len(df):,} dòng / {df['ticker'].nunique()} mã -> {pq_path}")

def upsert(conn, df):
    conn.executemany("""INSERT INTO ohlcv VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(ticker, date) DO UPDATE SET
        open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
        volume=excluded.volume, source=excluded.source""", df.itertuples(index=False, name=None))
    conn.commit()

def set_meta(conn, ticker, status, rows):
    conn.execute("""INSERT INTO meta VALUES(?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET
        status=excluded.status, rows=excluded.rows, updated=excluded.updated""",
        (ticker, status, rows, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()

CMDS = {"universe": load_full_universe, "backfill": cmd_backfill, "update": cmd_update,
        "status": cmd_status, "export": cmd_export}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd not in CMDS:
        print("Lệnh khả dụng:", " | ".join(CMDS.keys())); sys.exit(1)
    if cmd == "backfill":
        cmd_backfill(sys.argv[2] if len(sys.argv) > 2 else "pending")
    else:
        CMDS[cmd]()
