import os
import sys
import time
import sqlite3
import random
import argparse
from datetime import datetime
import pandas as pd

# Console Windows mặc định cp1252 -> vỡ khi in tên ngành/cổ đông tiếng Việt
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==========================================
# LỚP METADATA (CƠ BẢN + LUẬT) — chân kiềng số 2
# ==========================================
# [!] TUYỆT ĐỐI KHÔNG ĐỤNG bảng `meta` — đó là bảng TIẾN ĐỘ BACKFILL của vn_stock_pipeline.py
#     (trùng tên dễ nhầm). File này chỉ đọc/ghi bảng `metadata` (khóa chính ticker).
#
# [BẪY POINT-IN-TIME] Bảng `metadata` là snapshot "HÔM NAY" (room ngoại, P/E, free-float,
# margin_status...). JOIN các cột này vào giá QUÁ KHỨ để backtest là SAI HOÀN TOÀN:
# dính survivorship bias (mã hủy niêm yết không còn metadata) + lookahead bias
# (P/E hôm nay không tồn tại tại thời điểm quá khứ). CHỈ DÙNG ĐỂ LỌC LIVE.

DB_PATH = "vn_stock.db"
BLACKLIST_FILE = "blacklist.csv"
INDEX_SYMBOLS = ["VNINDEX", "HNXINDEX", "UPCOMINDEX"]   # chỉ số, không có metadata doanh nghiệp

EXCHANGE_ALIASES = {
    "HSX": "HSX", "HOSE": "HSX", "HCM": "HSX",
    "HNX": "HNX", "UPCOM": "UPCOM", "DELISTED": "DELISTED",
}


def normalize_exchange(value):
    """Quy về nhãn nội bộ ổn định; không có ngoại lệ theo ticker."""
    raw = str(value or "").strip().upper()
    return EXCHANGE_ALIASES.get(raw, raw or None)

REQUEST_DELAY = 1.1        # ~55 req/phút TỔNG -> mỗi nguồn (VCI/KBS) luôn dưới 60 req/phút
MAX_RETRY = 3
BACKOFF_BASE = 5           # lỗi mạng: 5/10/15s
BACKOFF_RATE = 15          # rate-limit: 15/30/45s (cửa sổ quota 60s trượt — chờ ngắn là phí lượt)
PRICE_BOARD_BATCH = 50     # price_board nhận LIST -> batch 50 mã/request, KHÔNG gọi từng mã
ICB_LEVEL = 2              # ngành ICB cấp 2 (~19 nhóm) — đủ mịn cho độ rộng thị trường,
                           # đổi 3 nếu muốn ~40 nhóm chi tiết hơn

NET_FAIL = "NET_FAIL"      # sentinel: lỗi mạng sau MAX_RETRY -> lần chạy sau thử lại

# ==========================================
# CÔNG CỤ CHUNG
# ==========================================
def init_metadata(conn):
    # Bảng MỚI `metadata` — không liên quan bảng tiến độ `meta` của file giá
    conn.execute("""CREATE TABLE IF NOT EXISTS metadata(
        ticker TEXT PRIMARY KEY,
        exchange TEXT,              -- nhãn VCI: HSX (= HOSE), HNX, UPCOM, DELISTED
        industry TEXT,              -- tên ngành ICB cấp ICB_LEVEL (nguồn VCI)
        foreign_room_pct REAL,      -- %% ROOM NGOẠI CÒN TRỐNG = current_room/total_room*100
                                    -- (100 = ngoại chưa mua gì, 0 = kín room)
        pe REAL,                    -- P/E quý mới nhất (lần) — nguồn KBS
        pb REAL,                    -- P/B quý mới nhất (lần) — nguồn KBS
        roe REAL,                   -- ROE trailing 4 quý gần nhất, ĐƠN VỊ %% — nguồn KBS
        market_cap REAL,            -- vốn hóa, ĐƠN VỊ: ĐỒNG (VND). Ví dụ SSI ~ 6.8e13 = 68 nghìn tỷ
        shares_outstanding REAL,    -- số CP đang lưu hành (issue_share từ VCI overview)
        free_float_est REAL,        -- PROXY free-float 0..1 (xem est_free_float, KHÔNG phải số FTSE)
        dividend_yield REAL,        -- tỷ suất cổ tức trailing, ĐƠN VỊ %% (KBS trả phân số 0.08 -> lưu 8.0)
        margin_status TEXT,         -- cờ từ blacklist.csv: margin_cut/warning/control/suspend
        updated TEXT)               -- CHỈ phần per-ticker ghi cột này -> làm mốc resume
        """)
    # DB cũ tạo trước khi có cột dividend_yield -> tự migrate
    cols = [r[1] for r in conn.execute("PRAGMA table_info(metadata)")]
    if "dividend_yield" not in cols:
        conn.execute("ALTER TABLE metadata ADD COLUMN dividend_yield REAL")
    conn.commit()

def get_universe(conn):
    """Universe = mã đã có dữ liệu giá trong ohlcv (đồng bộ với vn_indicators.py), bỏ chỉ số.
    Không đọc tickers.txt để khỏi cào metadata cho mã chưa từng có giá."""
    rows = conn.execute("SELECT DISTINCT ticker FROM ohlcv ORDER BY ticker").fetchall()
    return [r[0] for r in rows if r[0] not in INDEX_SYMBOLS]

def call_api(fn, label):
    """Gọi API với delay/retry/backoff GIỐNG HỆT cơ chế của vn_stock_pipeline.py.
    Trả về: DataFrame nếu OK | None nếu nguồn xác nhận rỗng (mã hủy NY, thiếu BCTC...)
            | NET_FAIL nếu lỗi mạng/rate-limit sau MAX_RETRY (để lần chạy sau thử lại)."""
    for attempt in range(1, MAX_RETRY + 1):
        try:
            res = fn()
            time.sleep(REQUEST_DELAY)
            if res is None or len(res) == 0:
                return None
            return res
        except Exception as e:
            # KBS bọc lỗi gốc trong RetryError (tenacity) -> bóc ra mới phân loại đúng;
            # "Dữ liệu trống..." = nguồn xác nhận không có dữ liệu, không phải lỗi hệ thống
            inner = getattr(getattr(e, "last_attempt", None), "exception", lambda: None)()
            m = str(inner if inner is not None else e).lower()
            if any(k in m for k in ("dữ liệu trống", "no data", "empty")):
                return None
            is_rate_limit = any(k in m for k in ("rate", "429", "quá nhiều", "too many"))
            is_network_err = any(k in m for k in ("timeout", "connection", "disconnected", "reset", "502", "503", "504"))
            if is_rate_limit or is_network_err:
                wait = (BACKOFF_RATE if is_rate_limit else BACKOFF_BASE) * attempt + random.uniform(0, 2)
                lbl = "Rate-Limit" if is_rate_limit else "Lỗi Mạng Tạm Thời"
                print(f"   [{lbl}] {label} - Thử lại sau {wait:.1f}s (Lần {attempt}/{MAX_RETRY})")
                time.sleep(wait)
            else:
                # lỗi dữ liệu (mã không tồn tại, nguồn không hỗ trợ...) -> coi như không có
                print(f"   [Lỗi Hệ Thống] {label}: {str(inner if inner is not None else e)[:70]}")
                return None
    return NET_FAIL

# ==========================================
# PHA 1 — BULK (rẻ, chạy lại mỗi lần): sàn + ngành + room ngoại
# ==========================================
def sync_exchange_industry(conn, universe):
    """2 request cho TOÀN BỘ thị trường (ưu tiên bulk để tiết kiệm quota)."""
    from vnstock.api.listing import Listing
    uni = set(universe)

    ex = call_api(lambda: Listing(source="VCI", random_agent=True).symbols_by_exchange(),
                  "Listing.symbols_by_exchange")
    if isinstance(ex, pd.DataFrame):
        ex = ex.copy()
        ex["symbol"] = ex["symbol"].astype(str).str.upper()
        ex = ex[ex["symbol"].isin(uni)].drop_duplicates(subset="symbol")
        conn.executemany("""INSERT INTO metadata(ticker, exchange) VALUES(?,?)
            ON CONFLICT(ticker) DO UPDATE SET exchange=excluded.exchange""",
            [(symbol, normalize_exchange(exchange))
             for symbol, exchange in zip(ex["symbol"], ex["exchange"])])
        conn.commit()
        print(f" [bulk] exchange: {len(ex)} mã (1 request)")

    ind = call_api(lambda: Listing(source="VCI", random_agent=True).symbols_by_industries(),
                   "Listing.symbols_by_industries")
    if isinstance(ind, pd.DataFrame):
        ind = ind.copy()
        # mỗi mã có nhiều dòng theo icb_level (1..4) -> chỉ giữ cấp ICB_LEVEL
        ind = ind[pd.to_numeric(ind["icb_level"], errors="coerce") == ICB_LEVEL]
        ind["symbol"] = ind["symbol"].astype(str).str.upper()
        ind = ind[ind["symbol"].isin(uni)].drop_duplicates(subset="symbol")
        conn.executemany("""INSERT INTO metadata(ticker, industry) VALUES(?,?)
            ON CONFLICT(ticker) DO UPDATE SET industry=excluded.industry""",
            list(zip(ind["symbol"], ind["icb_name"].astype(str))))
        conn.commit()
        print(f" [bulk] industry (ICB cấp {ICB_LEVEL}): {len(ind)} mã (1 request)")

def sync_foreign_room(conn, tickers):
    """price_board nhận LIST -> batch {PRICE_BOARD_BATCH} mã/request thay vì 1686 request lẻ."""
    from vnstock.api.trading import Trading
    n_ok = 0
    for i in range(0, len(tickers), PRICE_BOARD_BATCH):
        chunk = tickers[i:i + PRICE_BOARD_BATCH]
        pb = call_api(lambda c=chunk: Trading(source="VCI", random_agent=True).price_board(c),
                      f"price_board[{i}:{i+len(chunk)}]")
        if not isinstance(pb, pd.DataFrame):
            continue
        # price_board VCI trả cột MultiIndex (nhóm listing/match/bid_ask)
        sym = pb[("listing", "symbol")].astype(str).str.upper()
        cur = pd.to_numeric(pb[("match", "current_room")], errors="coerce")
        tot = pd.to_numeric(pb[("match", "total_room")], errors="coerce")
        # %% room ngoại CÒN TRỐNG; NULL nếu nguồn không có số room
        pct = (cur / tot * 100).where(tot > 0)
        rows = [(t, round(float(p), 2) if pd.notna(p) else None) for t, p in zip(sym, pct)]
        conn.executemany("""INSERT INTO metadata(ticker, foreign_room_pct) VALUES(?,?)
            ON CONFLICT(ticker) DO UPDATE SET foreign_room_pct=excluded.foreign_room_pct""", rows)
        conn.commit()
        n_ok += len(rows)
        print(f"   [room] {min(i + len(chunk), len(tickers))}/{len(tickers)} mã")
    print(f" [bulk] foreign_room_pct: {n_ok} mã ({-(-len(tickers) // PRICE_BOARD_BATCH)} request)")

# ==========================================
# PHA 2 — PER-TICKER (nặng, ~3 request/mã): pe/pb/roe + vốn hóa + free-float proxy
# ==========================================
def parse_ratio(r):
    """Lấy cột quý MỚI NHẤT từ KBS ratio (định dạng dọc item/item_id, cột quý xếp MỚI -> CŨ).
    Dùng KBS vì VCI ratio bản free chỉ trả về năm CŨ NHẤT (2018) — vô dụng cho quý hiện tại.
    roe = item `roe_trailling` (ROE 4 quý gần nhất, %%) — so sánh được giữa các mã;
    item `roe` đơn lẻ của KBS là ROE MỘT quý nên không dùng."""
    data_cols = [c for c in r.columns if c not in ("item", "item_id")]
    if not data_cols:
        return {}
    x = r.drop_duplicates(subset="item_id").set_index("item_id")[data_cols[0]]

    def g(key):
        v = pd.to_numeric(x.get(key), errors="coerce")
        return float(v) if pd.notna(v) else None

    dv = g("dividend_yield")   # KBS trả PHÂN SỐ (0.08 = 8%%) -> quy về %% cho đồng bộ với roe
    return {"pe": g("pe_ratio"), "pb": g("pb_ratio"), "roe": g("roe_trailling"),
            "dividend_yield": round(dv * 100, 2) if dv is not None else None}

def est_free_float(sh, state_pct):
    """PROXY free-float = 1 − (tổng tỷ lệ cổ đông lớn ≥5%%) − phần sở hữu Nhà nước chưa nằm
    trong nhóm đó. [!] Đây là PROXY tự tính, KHÔNG phải free-float chính thức kiểu FTSE/HOSE:
    không trừ được cổ đông nội bộ <5%%, ESOP bị khóa, cổ đông chiến lược bị hạn chế chuyển
    nhượng... Chỉ dùng để ước lượng thanh khoản tiềm năng, đừng coi là số chuẩn."""
    pct = pd.to_numeric(sh["share_own_percent"], errors="coerce").fillna(0)
    big = pct[pct >= 0.05]
    locked = float(big.sum())
    # tránh đếm trùng: nếu cổ đông Nhà nước đã lộ diện trong nhóm ≥5%% thì không cộng thêm
    names = sh["share_holder"].astype(str)
    state_mask = names.str.contains(
        "Nhà nước|SCIC|Ủy ban nhân dân|UBND|Bộ Tài chính|Kinh doanh vốn", case=False, regex=True)
    state_in_big = float(pct[(pct >= 0.05) & state_mask].sum())
    if state_pct and state_pct > state_in_big:
        locked += state_pct - state_in_big
    return round(max(0.0, min(1.0, 1.0 - locked)), 4)

def sync_fundamentals(conn, tickers, refresh=False):
    """Phần NẶNG: ~3 request/mã x ~1686 mã ≈ 2 giờ. Resumable: bỏ qua mã đã có `updated`
    (trừ khi --refresh). Metadata cơ bản đổi chậm -> chạy lại MỖI QUÝ là đủ."""
    from vnstock.api.financial import Finance
    from vnstock.api.company import Company

    done = {r[0] for r in conn.execute("SELECT ticker FROM metadata WHERE updated IS NOT NULL")}
    todo = tickers if refresh else [t for t in tickers if t not in done]
    est_min = len(todo) * 3 * (REQUEST_DELAY + 0.4) / 60
    print(f"[fund] Cào {len(todo)}/{len(tickers)} mã (bỏ qua {len(tickers) - len(todo)} đã có; ước tính ~{est_min:.0f} phút)")

    for i, tk in enumerate(todo, 1):
        vals = {"pe": None, "pb": None, "roe": None, "dividend_yield": None,
                "market_cap": None, "shares_outstanding": None, "free_float_est": None}
        got_any, net_fail = False, False

        # 1) P/E, P/B, ROE — KBS (per-ticker, không có API bulk)
        r = call_api(lambda: Finance(source="KBS", symbol=tk).ratio(period="quarter"),
                     f"{tk}@KBS.ratio")
        if isinstance(r, pd.DataFrame):
            vals.update(parse_ratio(r)); got_any = True
        elif r is NET_FAIL:
            net_fail = True

        # 2) Vốn hóa + số CP lưu hành — VCI overview. market_cap ĐƠN VỊ ĐỒNG (VND).
        state_pct = 0.0
        ov = call_api(lambda: Company(source="VCI", symbol=tk, random_agent=True).overview(),
                      f"{tk}@VCI.overview")
        if isinstance(ov, pd.DataFrame):
            o = ov.iloc[0]
            mc = pd.to_numeric(o.get("market_cap"), errors="coerce")
            shr = pd.to_numeric(o.get("issue_share"), errors="coerce")
            st = pd.to_numeric(o.get("state_percentage"), errors="coerce")
            vals["market_cap"] = float(mc) if pd.notna(mc) else None
            vals["shares_outstanding"] = float(shr) if pd.notna(shr) else None
            state_pct = float(st) if pd.notna(st) else 0.0
            got_any = True
        elif ov is NET_FAIL:
            net_fail = True

        # 3) Free-float PROXY — VCI shareholders (xem cảnh báo trong est_free_float)
        sh = call_api(lambda: Company(source="VCI", symbol=tk, random_agent=True).shareholders(),
                      f"{tk}@VCI.shareholders")
        if isinstance(sh, pd.DataFrame) and "share_own_percent" in sh.columns:
            vals["free_float_est"] = est_free_float(sh, state_pct); got_any = True
        elif sh is NET_FAIL:
            net_fail = True

        if not got_any and net_fail:
            # toàn lỗi mạng -> KHÔNG ghi `updated` để lần chạy sau tự thử lại (resume)
            print(f" {i:>4}/{len(todo)} {tk:<10} -> THẤT BẠI mạng, sẽ thử lại lần chạy sau")
            continue

        conn.execute("""INSERT INTO metadata(ticker, pe, pb, roe, dividend_yield, market_cap,
                shares_outstanding, free_float_est, updated) VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ticker) DO UPDATE SET pe=excluded.pe, pb=excluded.pb, roe=excluded.roe,
                dividend_yield=excluded.dividend_yield,
                market_cap=excluded.market_cap, shares_outstanding=excluded.shares_outstanding,
                free_float_est=excluded.free_float_est, updated=excluded.updated""",
            (tk, vals["pe"], vals["pb"], vals["roe"], vals["dividend_yield"], vals["market_cap"],
             vals["shares_outstanding"], vals["free_float_est"],
             datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()

        def _f(v, nd=2):
            return "-" if v is None else f"{v:.{nd}f}"
        print(f" {i:>4}/{len(todo)} {tk:<10} pe={_f(vals['pe'])} pb={_f(vals['pb'])} "
              f"roe%={_f(vals['roe'], 1)} ff={_f(vals['free_float_est'])} "
              f"mc={_f((vals['market_cap'] or 0) / 1e9, 0)}tỷ")

def sync_ratio_only(conn, tickers, limit=0):
    """Backfill RIÊNG phần KBS ratio (pe/pb/roe/dividend_yield) — 1 request/mã thay vì 3.
    Dùng khi thêm cột mới (dividend_yield) mà không muốn --refresh toàn bộ.
    Resume tự nhiên: chỉ cào mã dividend_yield còn NULL."""
    from vnstock.api.financial import Finance
    todo = [r[0] for r in conn.execute(
        "SELECT ticker FROM metadata WHERE updated IS NOT NULL AND dividend_yield IS NULL")]
    todo = [t for t in todo if t in set(tickers)]
    if limit:
        todo = todo[:limit]
    print(f"[ratio-only] Backfill {len(todo)} mã (~{len(todo) * 1.6 / 60:.0f} phút; resume tự động nếu đứt)")
    for i, tk in enumerate(todo, 1):
        r = call_api(lambda: Finance(source="KBS", symbol=tk).ratio(period="quarter"),
                     f"{tk}@KBS.ratio")
        if r is NET_FAIL:
            print(f" {i:>4}/{len(todo)} {tk:<10} -> THẤT BẠI mạng, chạy lại sau"); continue
        vals = parse_ratio(r) if isinstance(r, pd.DataFrame) else {}
        # mã không có BCTC: ghi -1 làm mốc "đã thử, nguồn không có" để resume không cào lại mãi
        dv = vals.get("dividend_yield")
        conn.execute("""UPDATE metadata SET pe=COALESCE(?, pe), pb=COALESCE(?, pb),
                roe=COALESCE(?, roe), dividend_yield=? WHERE ticker=?""",
            (vals.get("pe"), vals.get("pb"), vals.get("roe"),
             dv if dv is not None else -1, tk))
        conn.commit()
        print(f" {i:>4}/{len(todo)} {tk:<10} yield={'-' if dv is None else f'{dv:.1f}%'}")

# ==========================================
# PHA 3 — BLACKLIST (nhập tay từ HOSE/HNX, xem blacklist.csv)
# ==========================================
def apply_blacklist(conn):
    """Merge blacklist.csv vào cột margin_status. CHỈ GẮN CỜ, không xóa dữ liệu mã nào.
    Reset toàn bộ cờ trước khi gắn lại -> mã được gỡ khỏi blacklist tự sạch cờ."""
    valid = {"margin_cut", "warning", "control", "suspend"}
    conn.execute("UPDATE metadata SET margin_status=NULL")
    if not os.path.exists(BLACKLIST_FILE):
        conn.commit()
        print(f" [blacklist] Không thấy {BLACKLIST_FILE} -> bỏ qua (margin_status để trống)")
        return
    bl = pd.read_csv(BLACKLIST_FILE, comment="#")
    n = 0
    for _, row in bl.iterrows():
        tk = str(row["ticker"]).strip().upper()
        st = str(row["status"]).strip().lower()
        if st not in valid:
            print(f" [blacklist] Cảnh báo: status lạ '{st}' của {tk} (hợp lệ: {'/'.join(sorted(valid))})")
        conn.execute("UPDATE metadata SET margin_status=? WHERE ticker=?", (st, tk))
        n += 1
    conn.commit()
    print(f" [blacklist] Gắn cờ margin_status cho {n} mã từ {BLACKLIST_FILE}")

# ==========================================
# ĐIỀU KHIỂN
# ==========================================
def main():
    ap = argparse.ArgumentParser(description="Đồng bộ lớp metadata (cơ bản + luật) vào bảng `metadata` của vn_stock.db")
    ap.add_argument("--limit", type=int, default=0, help="chỉ xử lý N mã đầu (để test)")
    ap.add_argument("--refresh", action="store_true", help="cào lại cả mã đã có (mặc định: resume, bỏ qua mã đã xong)")
    ap.add_argument("--skip-bulk", action="store_true", help="bỏ qua pha bulk sàn/ngành/room (khi chỉ muốn chạy tiếp phần per-ticker)")
    ap.add_argument("--blacklist-only", action="store_true", help="chỉ merge blacklist.csv vào metadata (0 request API — dùng sau khi chạy blacklist_sync.py)")
    ap.add_argument("--ratio-only", action="store_true", help="chỉ backfill pe/pb/roe/dividend_yield từ KBS (1 request/mã, resume tự động)")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    init_metadata(conn)

    if args.ratio_only:
        sync_ratio_only(conn, get_universe(conn), limit=args.limit)
        n = conn.execute("SELECT COUNT(*) FROM metadata WHERE dividend_yield IS NOT NULL AND dividend_yield >= 0").fetchone()[0]
        print(f"[meta_sync] Xong: {n} mã có dividend_yield trong metadata")
        conn.close()
        return

    if args.blacklist_only:
        apply_blacklist(conn)
        n = conn.execute("SELECT COUNT(*) FROM metadata WHERE margin_status IS NOT NULL").fetchone()[0]
        print(f"[meta_sync] Xong: {n} mã đang mang cờ margin_status trong metadata")
        conn.close()
        return

    universe = get_universe(conn)
    subset = universe[:args.limit] if args.limit else universe
    print(f"[meta_sync] Universe {len(universe)} mã" + (f" | test --limit {args.limit}" if args.limit else ""))

    if not args.skip_bulk:
        sync_exchange_industry(conn, universe)   # luôn full: chỉ tốn 2 request
        sync_foreign_room(conn, subset)          # theo subset khi --limit để đỡ tốn quota lúc test
    sync_fundamentals(conn, subset, refresh=args.refresh)
    apply_blacklist(conn)

    total = conn.execute("SELECT COUNT(*) FROM metadata").fetchone()[0]
    filled = conn.execute("SELECT COUNT(*) FROM metadata WHERE updated IS NOT NULL").fetchone()[0]
    print(f"\n[meta_sync] Bảng metadata: {total} dòng | per-ticker hoàn tất: {filled}")
    sample = pd.read_sql(
        "SELECT * FROM metadata WHERE updated IS NOT NULL ORDER BY updated DESC, ticker LIMIT 15", conn)
    if len(sample):
        print("\n== 15 dòng metadata mẫu ==")
        print(sample.to_string(index=False))
    conn.close()

if __name__ == "__main__":
    main()
