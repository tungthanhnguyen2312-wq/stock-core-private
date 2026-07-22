import os
import sys
import time
import sqlite3
import random
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
import pandas as pd

from shareholder_pipeline import (
    DONE,
    MANUAL_OVERRIDE,
    NETWORK_FAILED,
    PARSE_FAILED,
    SOURCE_EMPTY,
    STALE,
    UNSUPPORTED,
    NetworkSourceError,
    ShareholderSourceAdapter,
    UnsupportedSourceError,
    build_shareholder_summary,
    build_major_shareholder_snapshot_manifest,
    load_config,
    load_manual_overrides,
    provider_parser,
    run_source_chain,
)

# Console Windows mặc định cp1252 -> vỡ khi in tên cổ đông tiếng Việt
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==========================================
# LỚP CỔ ĐÔNG — chân kiềng MỚI, độc lập với 8 module pipeline cũ
# ==========================================
# [!] TUYỆT ĐỐI KHÔNG ĐỤNG bảng ohlcv/meta (tiến độ giá)/metadata (cơ bản+luật)/macro/news.
# File này chỉ tạo và ghi 2 bảng MỚI: `shareholders` (dữ liệu) + `shareholders_progress`
# (tiến độ cào — pattern y hệt bảng `meta` của vn_stock_pipeline.py, đặt tên khác để khỏi
# trùng 2 bảng `meta`/`metadata` đã có sẵn, tránh đúng cái bẫy README mục 4.2 đã cảnh báo).
#
# [BẪY POINT-IN-TIME] Cơ cấu cổ đông là snapshot "lần cào gần nhất", không phải lịch sử theo
# ngày. Đừng backtest bằng bảng này — chỉ dùng để lọc/đọc bối cảnh sở hữu HIỆN TẠI.

DB_PATH = "vn_stock.db"
LOG_FILE = os.path.join("logs", "shareholders_sync.log")
ROOT = Path(__file__).resolve().parent
PIPELINE_CONFIG_PATH = ROOT / "config" / "shareholder_pipeline.json"

REQUEST_DELAY = 1.1        # ~55 req/phút TỔNG -> dưới trần 60 req/phút của quota vnstock
MAX_RETRY = 3
BACKOFF_BASE = 5           # lỗi mạng: chờ 5/10/15s
BACKOFF_RATE = 15          # rate-limit: chờ 15/30/45s (cửa sổ quota 60s trượt — chờ ngắn là phí lượt)

# VCI đầy đủ hơn hẳn (68 cổ đông/mã tại HPG, đã dùng làm free_float_est trong meta_sync.py)
# KBS chỉ trả cổ đông LỚN >=5% (2-3 dòng/mã) -> dùng làm failover khi VCI rỗng/lỗi.
# Cùng cặp nguồn PRIMARY_SRC/FAILOVER_SRC như vn_stock_pipeline.py dùng cho giá (dòng 17-20).
PRIMARY_SRC = "VCI"
FAILOVER_SRC = "KBS"

INDEX_SYMBOLS = ["VNINDEX", "HNXINDEX", "UPCOMINDEX"]   # chỉ số, không có cổ đông doanh nghiệp

NET_FAIL = "NET_FAIL"      # sentinel: lỗi mạng sau MAX_RETRY -> lần chạy sau thử lại


def log(msg: str) -> None:
    """In ra console (y hệt print) + ghi bản sao kèm timestamp vào logs/shareholders_sync.log
    — cùng quy ước với logs/stock_analyzer.log. Log hỏng không được làm gãy việc chính."""
    print(msg)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except OSError:
        pass


# ==========================================
# CÔNG CỤ CHUNG
# ==========================================
def init_db(conn):
    # Khóa: ticker + shareholder_name (1 cổ đông có thể xuất hiện nhiều mã, không dùng rowid đơn)
    conn.execute("""CREATE TABLE IF NOT EXISTS shareholders(
        ticker TEXT,
        shareholder_name TEXT,
        shares_owned REAL,         -- số cổ phần đang nắm giữ (đơn vị: cổ phiếu); NULL = nguồn không trả số này
        pct REAL,                  -- tỷ lệ sở hữu, ĐÃ QUY VỀ %% (0..100) cho đồng bộ với metadata.roe/dividend_yield
                                    -- Sentinel: NULL = cột chưa từng ghi (không nên xảy ra nếu có dòng);
                                    -- -1 = đã hỏi nguồn, nguồn trả tên cổ đông nhưng KHÔNG có số %% (giống dividend_yield)
        shareholder_type TEXT,     -- tổ chức/cá nhân/nhà nước/nước ngoài NẾU nguồn phân biệt được.
                                    -- shareholders() của cả VCI và KBS KHÔNG trả trường phân loại này
                                    -- -> LUÔN NULL ở thời điểm viết module, KHÔNG tự suy đoán từ tên.
        source TEXT,                -- VCI hoặc KBS — nguồn thực tế đã lấy được dòng này
        updated_at TEXT,            -- thời điểm lần cào gần nhất (mốc resume ở cấp bảng progress)
        PRIMARY KEY(ticker, shareholder_name))""")

    # Bảng TIẾN ĐỘ riêng — pattern y hệt bảng `meta` của vn_stock_pipeline.py
    # (ticker PRIMARY KEY, status, rows, updated) nhưng đặt tên KHÁC để không đụng bảng `meta`/`metadata` có sẵn.
    # Legacy progress row remains compact; Phase 6 writes the explicit status
    # contract and stores detailed attempts/reasons in the additive tables.
    # Ticker CHƯA từng xuất hiện trong bảng này = CHƯA CÀO (tương đương NULL cấp ticker).
    conn.execute("""CREATE TABLE IF NOT EXISTS shareholders_progress(
        ticker TEXT PRIMARY KEY, status TEXT, rows INTEGER, updated TEXT)""")

    # Phase 6 additive schema.  The legacy tables above remain untouched so
    # existing readers and old fixture databases continue to work.
    conn.execute("""CREATE TABLE IF NOT EXISTS shareholder_source_attempts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        source TEXT NOT NULL,
        status TEXT NOT NULL,
        error TEXT,
        reason TEXT,
        error_reason TEXT,
        record_count INTEGER NOT NULL,
        parsed_record_count INTEGER NOT NULL,
        request_timestamp TEXT NOT NULL,
        latest_as_of_date TEXT)""")
    attempt_columns = {row[1] for row in conn.execute("PRAGMA table_info(shareholder_source_attempts)")}
    for column in ("error", "reason"):
        if column not in attempt_columns:
            conn.execute(f"ALTER TABLE shareholder_source_attempts ADD COLUMN {column} TEXT")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_shareholder_attempts_ticker_time
        ON shareholder_source_attempts(ticker, request_timestamp DESC)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS shareholder_records_v2(
        record_key TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        holder_name TEXT NOT NULL,
        normalized_holder_name TEXT NOT NULL,
        shares REAL,
        ownership_pct REAL,
        as_of_date TEXT,
        source_name TEXT NOT NULL,
        source_reference TEXT,
        verified_at TEXT,
        fetched_at TEXT,
        note TEXT,
        record_origin TEXT NOT NULL,
        reconciliation_status TEXT NOT NULL,
        conflict_group TEXT,
        provenance_json TEXT NOT NULL)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_shareholder_records_v2_ticker_asof
        ON shareholder_records_v2(ticker, as_of_date DESC)""")
    # Forward-only manifest: existing record rows are intentionally not
    # backfilled because their historical completeness cannot be established.
    conn.execute("""CREATE TABLE IF NOT EXISTS major_shareholder_snapshots(
        snapshot_id TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        as_of_date TEXT NOT NULL,
        source_name TEXT NOT NULL,
        record_origin TEXT NOT NULL,
        source_reference TEXT,
        fetched_at TEXT NOT NULL,
        record_count INTEGER NOT NULL,
        status TEXT NOT NULL,
        is_complete INTEGER NOT NULL CHECK(is_complete IN (0, 1)),
        CHECK(record_origin = 'api'))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_major_shareholder_snapshots_scope_date
        ON major_shareholder_snapshots(ticker, source_name, record_origin, source_reference, as_of_date)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS shareholder_sync_runs(
        ticker TEXT PRIMARY KEY,
        final_status TEXT NOT NULL,
        reason TEXT NOT NULL,
        raw_record_count INTEGER NOT NULL,
        parsed_record_count INTEGER NOT NULL,
        deduplicated_record_count INTEGER NOT NULL,
        manual_override_count INTEGER NOT NULL,
        latest_as_of_date TEXT,
        freshness_json TEXT NOT NULL,
        updated TEXT NOT NULL)""")
    conn.commit()


def get_universe(conn):
    """Universe = mã đã có dữ liệu giá trong ohlcv (đồng bộ với meta_sync.py/vn_indicators.py),
    bỏ chỉ số. Không đọc tickers.txt để khỏi cào cổ đông cho mã chưa từng có giá."""
    rows = conn.execute("SELECT DISTINCT ticker FROM ohlcv ORDER BY ticker").fetchall()
    return [r[0] for r in rows if r[0] not in INDEX_SYMBOLS]


def call_api(fn, label):
    """Gọi API với delay/retry/backoff GIỐNG HỆT cơ chế của vn_stock_pipeline.py / meta_sync.py.
    Trả về: DataFrame nếu OK | None nếu nguồn xác nhận rỗng (mã không có cổ đông lớn công bố...)
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
                log(f"   [{lbl}] {label} - Thử lại sau {wait:.1f}s (Lần {attempt}/{MAX_RETRY})")
                time.sleep(wait)
            else:
                # lỗi dữ liệu (mã không tồn tại, nguồn không hỗ trợ...) -> coi như không có
                log(f"   [Lỗi Hệ Thống] {label}: {str(inner if inner is not None else e)[:70]}")
                return None
    return NET_FAIL


# ==========================================
# CHUẨN HÓA — VCI và KBS trả 2 layout cột khác nhau
# ==========================================
def normalize(df, ticker, source):
    """Chuẩn hóa DataFrame thô của shareholders() về schema chung.

    [BẪY ĐƠN VỊ — đã kiểm chứng ở AUDIT_REPORT.md §1.2a]
    VCI trả `share_own_percent` dạng PHÂN SỐ (0..1, VD 0.25796 = 25.796%%);
    KBS trả `ownership_percentage` dạng %% THẲNG (0..100, VD 25.8).
    Quy CẢ HAI về %% (0..100) để đồng bộ với quy ước roe/dividend_yield trong bảng metadata.
    """
    out = pd.DataFrame()
    if source == "VCI":
        out["shareholder_name"] = df["share_holder"].astype(str).str.strip()
        out["shares_owned"] = pd.to_numeric(df.get("quantity"), errors="coerce")
        pct = pd.to_numeric(df.get("share_own_percent"), errors="coerce") * 100.0
    else:  # KBS
        out["shareholder_name"] = df["name"].astype(str).str.strip()
        out["shares_owned"] = pd.to_numeric(df.get("shares_owned"), errors="coerce")
        pct = pd.to_numeric(df.get("ownership_percentage"), errors="coerce")

    # Sentinel giống quy ước dividend_yield: nguồn trả tên cổ đông nhưng KHÔNG có số %%
    # -> ghi -1 (đã hỏi, không có số), KHÔNG để NULL (NULL dành riêng cho "chưa từng cào").
    out["pct"] = pct.where(pct.notna(), -1.0)

    # shareholders() của cả 2 nguồn KHÔNG trả trường phân loại tổ chức/cá nhân/NN/nước ngoài
    # -> để NULL, TUYỆT ĐỐI không suy đoán từ tên (vd chuỗi "Nhà nước"/"SCIC"...).
    out["shareholder_type"] = None

    out["ticker"] = ticker.upper()
    out["source"] = source
    out["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    out = out[out["shareholder_name"].notna() & (out["shareholder_name"] != "")]
    out = out.drop_duplicates(subset="shareholder_name", keep="first")
    return out[["ticker", "shareholder_name", "shares_owned", "pct", "shareholder_type", "source", "updated_at"]]


def _provider_payload(ticker, source):
    """Fetch one provider payload while keeping unsupported/network distinct."""
    from vnstock.api.company import Company

    for attempt in range(1, MAX_RETRY + 1):
        try:
            payload = Company(source=source, symbol=ticker, random_agent=True).shareholders()
            time.sleep(REQUEST_DELAY)
            return payload
        except Exception as exc:
            inner = getattr(getattr(exc, "last_attempt", None), "exception", lambda: None)()
            actual = inner if inner is not None else exc
            message = str(actual).lower()
            if isinstance(actual, NotImplementedError) or any(
                key in message for key in ("not implemented", "not supported", "không hỗ trợ")
            ):
                raise UnsupportedSourceError(str(actual)) from exc
            if any(key in message for key in ("dữ liệu trống", "no data", "empty")):
                return None
            rate_limited = any(key in message for key in ("rate", "429", "quá nhiều", "too many"))
            network_error = any(
                key in message
                for key in ("timeout", "connection", "disconnected", "reset", "502", "503", "504")
            )
            if rate_limited or network_error:
                if attempt == MAX_RETRY:
                    raise NetworkSourceError(str(actual)) from exc
                wait = (BACKOFF_RATE if rate_limited else BACKOFF_BASE) * attempt + random.uniform(0, 2)
                log(f"   [retry] {ticker}@{source} after {wait:.1f}s ({attempt}/{MAX_RETRY})")
                time.sleep(wait)
                continue
            # An endpoint exception produced no parseable payload.  Keep it as
            # an explicit request failure instead of treating it as empty.
            raise NetworkSourceError(f"provider_request_failed: {actual}") from exc
    raise NetworkSourceError("provider_request_failed_after_retry")


def fetch_shareholder_summary(ticker):
    """Run configured source fallback and merge verified manual records."""
    config = load_config(PIPELINE_CONFIG_PATH)
    adapters = []
    for item in config["sources"]:
        if not item.get("enabled", True):
            continue
        source = str(item["name"]).upper()
        adapters.append(
            ShareholderSourceAdapter(
                source_name=source,
                fetcher=lambda tk, src=source: _provider_payload(tk, src),
                parser=provider_parser(source),
                source_reference=item.get("source_reference"),
            )
        )
    chain = run_source_chain(ticker, adapters)
    manual_path = ROOT / config.get("manual_override_path", "data/manual/shareholders_overrides.csv")
    manual = load_manual_overrides(manual_path, ticker=ticker)
    return build_shareholder_summary(
        chain,
        manual,
        freshness_threshold_days=config["freshness_threshold_days"],
    )


def fetch_shareholders(ticker):
    """Backward-compatible wrapper returning the former DataFrame tuple."""
    summary = fetch_shareholder_summary(ticker)
    api_records = [record for record in summary["records"] if record["record_origin"] == "api"]
    if api_records:
        rows = [
            {
                "ticker": record["ticker"],
                "shareholder_name": record["holder_name"],
                "shares_owned": record["shares"],
                "pct": -1.0 if record["ownership_pct"] is None else record["ownership_pct"],
                "shareholder_type": None,
                "source": record["source_name"],
                "updated_at": record["fetched_at"],
            }
            for record in api_records
        ]
        return pd.DataFrame(rows), api_records[0]["source_name"]
    if summary["status"] == NETWORK_FAILED:
        return NET_FAIL, ""
    return None, ""


# ==========================================
# GHI DB — xóa-rồi-chèn để cổ đông đã rớt khỏi danh sách không bị treo lại vĩnh viễn
# ==========================================
def set_progress(conn, ticker, status, rows):
    conn.execute("""INSERT INTO shareholders_progress VALUES(?,?,?,?)
        ON CONFLICT(ticker) DO UPDATE SET
        status=excluded.status, rows=excluded.rows, updated=excluded.updated""",
        (ticker, status, rows, datetime.now().strftime("%Y-%m-%d %H:%M")))


def apply_result(conn, ticker, df, status=DONE):
    """Ghi nguyên tử 1 mã: xóa toàn bộ cổ đông cũ của mã rồi chèn bộ mới (thay vì chỉ upsert)
    -> cổ đông đã bán hết/rớt khỏi top không bị treo lại trong DB vĩnh viễn.
    Bọc try/except: 1 mã lỗi ghi DB không được làm sập cả phiên (giống nguyên tắc backfill)."""
    try:
        conn.execute("DELETE FROM shareholders WHERE ticker=?", (ticker,))
        conn.executemany("""INSERT INTO shareholders
            (ticker, shareholder_name, shares_owned, pct, shareholder_type, source, updated_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(ticker, shareholder_name) DO UPDATE SET
                shares_owned=excluded.shares_owned, pct=excluded.pct,
                shareholder_type=excluded.shareholder_type, source=excluded.source,
                updated_at=excluded.updated_at""",
            df.itertuples(index=False, name=None))
        set_progress(conn, ticker, status, len(df))
        conn.commit()
        return True
    except sqlite3.Error as e:
        conn.rollback()
        log(f"   [Lỗi DB] {ticker}: {type(e).__name__}: {str(e)[:80]}")
        return False


def _record_key(record):
    identity = json.dumps(
        [
            record.get("ticker"), record.get("normalized_holder_name"), record.get("as_of_date"),
            record.get("source_name"), record.get("record_origin"), record.get("source_reference"),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def persist_summary(conn, summary):
    """Persist attempts and records without deleting older valid snapshots."""
    ticker = summary["ticker"]
    try:
        for attempt in summary["attempts"]:
            conn.execute(
                """INSERT INTO shareholder_source_attempts
                (ticker,source,status,error,reason,error_reason,record_count,parsed_record_count,request_timestamp,latest_as_of_date)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    ticker, attempt["source"], attempt["status"], attempt["error"], attempt["reason"], attempt["error_reason"],
                    attempt["record_count"], attempt["parsed_record_count"],
                    attempt["request_timestamp"], attempt["latest_as_of_date"],
                ),
            )
        for record in summary["records"]:
            conn.execute(
                """INSERT INTO shareholder_records_v2
                (record_key,ticker,holder_name,normalized_holder_name,shares,ownership_pct,as_of_date,
                 source_name,source_reference,verified_at,fetched_at,note,record_origin,
                 reconciliation_status,conflict_group,provenance_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(record_key) DO UPDATE SET
                    holder_name=excluded.holder_name,
                    shares=excluded.shares,
                    ownership_pct=excluded.ownership_pct,
                    verified_at=excluded.verified_at,
                    fetched_at=excluded.fetched_at,
                    note=excluded.note,
                    reconciliation_status=excluded.reconciliation_status,
                    conflict_group=excluded.conflict_group,
                    provenance_json=excluded.provenance_json""",
                (
                    _record_key(record), ticker, record["holder_name"], record["normalized_holder_name"],
                    record["shares"], record["ownership_pct"], record["as_of_date"],
                    record["source_name"], record["source_reference"], record["verified_at"],
                    record["fetched_at"], record["note"], record["record_origin"],
                    record["reconciliation_status"], record["conflict_group"],
                    json.dumps(record["provenance"], ensure_ascii=False, separators=(",", ":")),
                ),
            )
        manifest = build_major_shareholder_snapshot_manifest(summary)
        if manifest is not None:
            conn.execute(
                """INSERT INTO major_shareholder_snapshots
                (snapshot_id,schema_version,ticker,as_of_date,source_name,record_origin,source_reference,
                 fetched_at,record_count,status,is_complete)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    schema_version=excluded.schema_version,
                    fetched_at=excluded.fetched_at,
                    record_count=excluded.record_count,
                    status=excluded.status,
                    is_complete=excluded.is_complete""",
                (
                    manifest["snapshot_id"], manifest["schema_version"], manifest["ticker"],
                    manifest["as_of_date"], manifest["source_name"], manifest["record_origin"],
                    manifest["source_reference"], manifest["fetched_at"], manifest["record_count"],
                    manifest["status"], manifest["is_complete"],
                ),
            )
        conn.execute(
            """INSERT INTO shareholder_sync_runs
            (ticker,final_status,reason,raw_record_count,parsed_record_count,deduplicated_record_count,
             manual_override_count,latest_as_of_date,freshness_json,updated)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ticker) DO UPDATE SET
                final_status=excluded.final_status, reason=excluded.reason,
                raw_record_count=excluded.raw_record_count, parsed_record_count=excluded.parsed_record_count,
                deduplicated_record_count=excluded.deduplicated_record_count,
                manual_override_count=excluded.manual_override_count,
                latest_as_of_date=excluded.latest_as_of_date,
                freshness_json=excluded.freshness_json, updated=excluded.updated""",
            (
                ticker, summary["status"], summary["reason"], summary["raw_record_count"],
                summary["parsed_record_count"], summary["deduplicated_record_count"],
                summary["manual_override_count"], summary["latest_as_of_date"],
                json.dumps(summary["freshness"], ensure_ascii=False, separators=(",", ":")),
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            ),
        )

        api_records = [record for record in summary["records"] if record["record_origin"] == "api"]
        if api_records:
            legacy = pd.DataFrame(
                [
                    {
                        "ticker": record["ticker"],
                        "shareholder_name": record["holder_name"],
                        "shares_owned": record["shares"],
                        "pct": -1.0 if record["ownership_pct"] is None else record["ownership_pct"],
                        "shareholder_type": None,
                        "source": record["source_name"],
                        "updated_at": record["fetched_at"],
                    }
                    for record in api_records
                ]
            )
            # apply_result commits atomically and only runs for a valid payload.
            return apply_result(conn, ticker, legacy, status=summary["status"])

        # Empty/error/manual-only results never delete the legacy API snapshot.
        set_progress(conn, ticker, summary["status"], summary["deduplicated_record_count"])
        conn.commit()
        return True
    except sqlite3.Error as exc:
        conn.rollback()
        log(f"   [Lỗi DB Phase 6] {ticker}: {type(exc).__name__}: {str(exc)[:100]}")
        return False


# ==========================================
# ĐIỀU KHIỂN — chạy theo mã, resume qua bảng shareholders_progress
# ==========================================
def run_sync(conn, tickers, mode="pending"):
    """mode: 'pending' (mặc định, bỏ qua terminal records) | 'failed' (chỉ thử lại mã lỗi mạng)
    | 'force' (cào lại bất kể trạng thái — dùng cho --tickers/--refresh)."""
    progress = dict(conn.execute("SELECT ticker, status FROM shareholders_progress").fetchall())
    if mode == "failed":
        todo = [t for t in tickers if progress.get(t) in ("failed", NETWORK_FAILED)]
    elif mode == "force":
        todo = list(tickers)
    else:
        todo = [t for t in tickers if progress.get(t) not in (DONE, SOURCE_EMPTY, STALE, MANUAL_OVERRIDE)]

    log(f"[shareholders_sync: {mode}] Xử lý {len(todo)}/{len(tickers)} mã "
        f"(ước tính ~{len(todo) * 1.7 / 60:.0f} phút nếu chủ yếu dùng {PRIMARY_SRC})")

    for i, tk in enumerate(todo, 1):
        summary = fetch_shareholder_summary(tk)
        if not persist_summary(conn, summary):
            continue
        attempts = ", ".join(f"{item['source']}={item['status']}" for item in summary["attempts"])
        log(
            f" {i:>4}/{len(todo)} {tk:<10} -> {summary['status']} | "
            f"records={summary['deduplicated_record_count']} | attempts: {attempts}"
        )


def cmd_status(conn, universe):
    rows = dict(conn.execute("SELECT status, COUNT(*) FROM shareholders_progress GROUP BY status").fetchall())
    total_holders = conn.execute("SELECT COUNT(*) FROM shareholders").fetchone()[0]
    n_tickers_with_data = conn.execute("SELECT COUNT(DISTINCT ticker) FROM shareholders").fetchone()[0]
    ordered = (DONE, SOURCE_EMPTY, UNSUPPORTED, PARSE_FAILED, NETWORK_FAILED, STALE, MANUAL_OVERRIDE)
    counts = " | ".join(f"{status}={rows.get(status, 0)}" for status in ordered)
    legacy = rows.get("empty", 0) + rows.get("failed", 0)
    print(f"[status] {counts}" + (f" | legacy_empty_failed={legacy}" if legacy else ""))
    print(f"         Chưa xử lý={len(universe) - sum(rows.values())} "
          f"| Tổng dòng cổ đông={total_holders:,} ({n_tickers_with_data} mã)")
    sample = pd.read_sql(
        "SELECT * FROM shareholders ORDER BY updated_at DESC, ticker, pct DESC LIMIT 15", conn)
    if len(sample):
        print("\n== 15 dòng cổ đông mẫu (mới cào nhất) ==")
        print(sample.to_string(index=False))


def main():
    ap = argparse.ArgumentParser(
        description="Đồng bộ dữ liệu cổ đông lớn vào bảng `shareholders` của vn_stock.db")
    ap.add_argument("--tickers", nargs="+", metavar="TICKER",
                     help="chỉ xử lý các mã chỉ định (LUÔN cào lại, bỏ qua resume-check — dùng để test/debug)")
    ap.add_argument("--limit", type=int, default=0, help="chỉ xử lý N mã đầu của universe (để test; bỏ qua nếu dùng --tickers)")
    ap.add_argument("--resume", action="store_true", help="chỉ thử lại các mã đang ở trạng thái failed (giống `pipeline.py backfill failed`)")
    ap.add_argument("--refresh", action="store_true", help="cào lại cả mã đã done (mặc định: bỏ qua mã đã done/empty)")
    ap.add_argument("--status", action="store_true", help="chỉ in tiến độ hiện tại, 0 request")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    universe = get_universe(conn)

    if args.status:
        cmd_status(conn, universe)
        conn.close()
        return

    if args.tickers:
        target = sorted({t.strip().upper() for t in args.tickers if t.strip()})
        run_sync(conn, target, mode="force")
    elif args.resume:
        run_sync(conn, universe, mode="failed")
    else:
        subset = universe[:args.limit] if args.limit else universe
        run_sync(conn, subset, mode="force" if args.refresh else "pending")

    cmd_status(conn, universe)
    conn.close()


if __name__ == "__main__":
    main()
