import os
import sys
import time
import sqlite3
import random
import json
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import pandas as pd
import requests

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


def _env_number(name, default, cast, minimum):
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = cast(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} phải là số hợp lệ") from exc
    if value < minimum:
        raise ValueError(f"{name} phải >= {minimum}")
    return value


# Cấu hình request tập trung. Default đủ ngắn để source outage không treo pipeline,
# nhưng vẫn có thể override theo process bằng biến môi trường khi thật sự cần.
CONNECT_TIMEOUT = _env_number("VNSTOCK_PIPELINE_CONNECT_TIMEOUT", 5.0, float, 0.1)
READ_TIMEOUT = _env_number("VNSTOCK_PIPELINE_READ_TIMEOUT", 12.0, float, 0.1)
MAX_RETRY = _env_number("VNSTOCK_PIPELINE_MAX_ATTEMPTS", 2, int, 1)
BACKOFF_BASE = _env_number("VNSTOCK_PIPELINE_BACKOFF_BASE", 1.0, float, 0.0)
BACKOFF_MAX = _env_number("VNSTOCK_PIPELINE_BACKOFF_MAX", 10.0, float, 0.0)
BACKOFF_JITTER = _env_number("VNSTOCK_PIPELINE_BACKOFF_JITTER", 0.25, float, 0.0)
RETRY_AFTER_MAX = _env_number("VNSTOCK_PIPELINE_RETRY_AFTER_MAX", 30.0, float, 0.0)
SOURCE_FAILURE_BUDGET = _env_number("VNSTOCK_PIPELINE_SOURCE_FAILURE_BUDGET", 3, int, 1)

TRANSIENT_HTTP_STATUS = {408, 429, 500, 502, 503, 504}
PROVIDER_ENDPOINT_HINT = {
    "VCI": "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",
    "KBS": "https://kbbuddywts.kbsec.com.vn/iis-server/investment/history",
}

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_PARTIAL = 2
EXIT_SOURCE_UNAVAILABLE = 3

BATCH_SIZE = 300

INDEX_SYMBOLS = ["VNINDEX", "HNXINDEX", "UPCOMINDEX"]
USE_FILE = True
TICKERS_FILE = "tickers.txt"
WATCHLIST = ["SSI", "EVF", "PAN", "HPG", "FPT", "PVD", "QNS", "VNM", "POW", "PDR", "NLG"]

# ==========================================
# CÔNG CỤ XỬ LÝ & ĐỒNG BỘ DỮ LIỆU
# ==========================================
class PipelineRequestError(Exception):
    """Lỗi request đã được phân loại mà không mang header/payload/response body."""

    def __init__(self, kind, endpoint, elapsed, status_code=None, retry_after=None):
        super().__init__(kind)
        self.kind = kind
        self.endpoint = endpoint
        self.elapsed = elapsed
        self.status_code = status_code
        self.retry_after = retry_after


class TransientRequestError(PipelineRequestError):
    pass


class PermanentRequestError(PipelineRequestError):
    pass


@dataclass
class FetchOutcome:
    status: str
    data: object = None
    errors: list = field(default_factory=list)
    transient_failure: bool = False


def _safe_endpoint(url):
    parts = urlsplit(str(url))
    if parts.scheme and parts.hostname:
        host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
        try:
            port = f":{parts.port}" if parts.port is not None else ""
        except ValueError:
            port = ""
        return f"{parts.scheme}://{host}{port}{parts.path}"
    return parts.path or "provider-history"


def _retry_after_seconds(response):
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _bounded_send_request_direct(
    url, headers, method="GET", params=None, payload=None, timeout=30, proxies=None
):
    """Transport thay thế process-local cho vnstock, với timeout connect/read riêng."""
    del timeout  # Không dùng timeout đơn của package; dùng cấu hình tập trung ở trên.
    endpoint = _safe_endpoint(url)
    started = time.monotonic()
    timeout_pair = (CONNECT_TIMEOUT, READ_TIMEOUT)
    try:
        if method.upper() == "GET":
            response = requests.get(
                url, headers=headers, params=params, timeout=timeout_pair, proxies=proxies
            )
        else:
            if payload is not None and not isinstance(payload, (dict, str)):
                raise PermanentRequestError(
                    "invalid_payload", endpoint, time.monotonic() - started
                )
            data_arg = json.dumps(payload) if isinstance(payload, dict) else payload
            response = requests.post(
                url, headers=headers, data=data_arg, timeout=timeout_pair, proxies=proxies
            )
    except requests.exceptions.ConnectTimeout as exc:
        raise TransientRequestError(
            "connect_timeout", endpoint, time.monotonic() - started
        ) from exc
    except requests.exceptions.ReadTimeout as exc:
        raise TransientRequestError(
            "read_timeout", endpoint, time.monotonic() - started
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise TransientRequestError("timeout", endpoint, time.monotonic() - started) from exc
    except requests.exceptions.ConnectionError as exc:
        raise TransientRequestError(
            "connection_error", endpoint, time.monotonic() - started
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise PermanentRequestError(
            "request_error", endpoint, time.monotonic() - started
        ) from exc

    elapsed = time.monotonic() - started
    if response.status_code != 200:
        error_type = TransientRequestError if response.status_code in TRANSIENT_HTTP_STATUS else PermanentRequestError
        raise error_type(
            "http_status",
            endpoint,
            elapsed,
            status_code=response.status_code,
            retry_after=_retry_after_seconds(response),
        )
    try:
        return response.json()
    except ValueError as exc:
        raise PermanentRequestError("invalid_json", endpoint, elapsed) from exc


def _install_bounded_http():
    """Patch đúng transport hook mà VCI/KBS dùng; không sửa package trong .venv."""
    import vnstock.core.utils.client as client

    if client.send_request_direct is not _bounded_send_request_direct:
        client.send_request_direct = _bounded_send_request_direct


def _quote(symbol, source):
    _install_bounded_http()
    from vnstock.api.quote import Quote

    # Gọi provider trực tiếp để chỉ pipeline kiểm soát retry. Quote.history() của
    # adapter đã có Tenacity retry 3 lần; gọi qua adapter sẽ tạo retry lồng nhau.
    return Quote(symbol=symbol, source=source, random_agent=True).provider

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

def _request_log(ticker, source, attempt, result, elapsed, error=None, wait=None):
    endpoint = error.endpoint if error else PROVIDER_ENDPOINT_HINT.get(source, "provider-history")
    fields = [
        "[request]",
        f"provider={source}",
        f"endpoint={endpoint}",
        f"ticker={ticker}",
        f"attempt={attempt}/{MAX_RETRY}",
        f"result={result}",
        f"elapsed={elapsed:.2f}s",
        f"connect_timeout={CONNECT_TIMEOUT:.1f}s",
        f"read_timeout={READ_TIMEOUT:.1f}s",
    ]
    if error:
        fields.append(f"error={error.kind}")
        if error.status_code is not None:
            fields.append(f"http_status={error.status_code}")
    if wait is not None:
        fields.append(f"wait={wait:.2f}s")
    print(" ".join(fields), flush=True)


def _retry_delay(attempt, error):
    delay = min(BACKOFF_MAX, BACKOFF_BASE * (2 ** (attempt - 1)))
    if error.retry_after is not None:
        delay = max(delay, min(error.retry_after, RETRY_AFTER_MAX))
    return delay + random.uniform(0, BACKOFF_JITTER)


def _unwrap_retry_error(error):
    inner = getattr(getattr(error, "last_attempt", None), "exception", lambda: None)()
    return inner if inner is not None else error


def _legacy_request_error(error, source):
    """Phân loại lỗi package cũ nếu lỗi xảy ra ngoài transport hook."""
    message = f"{type(error).__name__} {error}".lower()
    endpoint = PROVIDER_ENDPOINT_HINT.get(source, "provider-history")
    if isinstance(error, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)) or any(
        k in message
        for k in ("timeout", "connection", "disconnected", "reset", "502", "503", "504", "429")
    ):
        return TransientRequestError(type(error).__name__, endpoint, 0.0)
    return PermanentRequestError(type(error).__name__, endpoint, 0.0)


def fetch_one(ticker, start, end):
    empty_source_count = 0
    errors = []
    saw_transient = False
    saw_permanent = False
    for source in (PRIMARY_SRC, FAILOVER_SRC):
        for attempt in range(1, MAX_RETRY + 1):
            started = time.monotonic()
            try:
                raw = _quote(ticker, source).history(start=start, end=end, interval=INTERVAL)
                if raw is None or len(raw) == 0:
                    empty_source_count += 1
                    _request_log(ticker, source, attempt, "empty", time.monotonic() - started)
                    break  # nguồn này xác nhận rỗng -> sang nguồn dự phòng
                df = normalize(raw, ticker, source)
                if df is not None and len(df):
                    _request_log(ticker, source, attempt, "success", time.monotonic() - started)
                    return FetchOutcome("success", data=df)
                saw_permanent = True
                errors.append(f"{source}:invalid_schema")
                _request_log(
                    ticker,
                    source,
                    attempt,
                    "failed",
                    time.monotonic() - started,
                    PermanentRequestError(
                        "invalid_schema", PROVIDER_ENDPOINT_HINT.get(source, "provider-history"), 0.0
                    ),
                )
                break
            except Exception as e:
                inner = _unwrap_retry_error(e)
                message = str(inner).lower()
                if any(k in message for k in ("dữ liệu trống", "không tìm thấy dữ liệu", "no data", "empty")):
                    empty_source_count += 1
                    _request_log(ticker, source, attempt, "empty", time.monotonic() - started)
                    break  # nguồn này xác nhận không có dữ liệu -> sang nguồn dự phòng
                error = inner if isinstance(inner, PipelineRequestError) else _legacy_request_error(inner, source)
                errors.append(
                    f"{source}:{error.kind}"
                    + (f":{error.status_code}" if error.status_code is not None else "")
                )
                if isinstance(error, TransientRequestError):
                    saw_transient = True
                    if attempt >= MAX_RETRY:
                        _request_log(ticker, source, attempt, "failed", time.monotonic() - started, error)
                        break
                    wait = _retry_delay(attempt, error)
                    _request_log(ticker, source, attempt, "retry", time.monotonic() - started, error, wait)
                    time.sleep(wait)
                else:
                    saw_permanent = True
                    _request_log(ticker, source, attempt, "failed", time.monotonic() - started, error)
                    break
    if empty_source_count == 2:
        return FetchOutcome("empty")
    return FetchOutcome(
        "failed",
        errors=errors,
        # Chỉ cần một provider gặp lỗi transient và toàn bộ failover đều không thành công
        # thì mã này vẫn tính vào failure budget. Điều này tránh bỏ lọt outage của VCI
        # khi KBS đồng thời trả lỗi cố định/không hỗ trợ riêng cho mã đó.
        transient_failure=saw_transient,
    )

# ==========================================
# HỆ THỐNG LỆNH ĐIỀU KHIỂN
# ==========================================
def _result_exit_code(completed_count, failed_count, source_unavailable=False):
    if source_unavailable:
        return EXIT_SOURCE_UNAVAILABLE
    if failed_count == 0:
        return EXIT_SUCCESS
    if completed_count > 0:
        return EXIT_PARTIAL
    return EXIT_FAILURE


def cmd_backfill(mode="pending"):
    today = datetime.now().strftime("%Y-%m-%d")
    universe = get_universe()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        init_db(conn)
        meta = dict(conn.execute("SELECT ticker, status FROM meta").fetchall())

    if mode == "failed":
        todo = [t for t in universe if meta.get(t) == "failed"]
    else:
        todo = [t for t in universe if meta.get(t) not in ("done", "empty")]

    total_left = len(todo)
    if BATCH_SIZE > 0:
        todo = todo[:BATCH_SIZE]
    print(f"[backfill: {mode}] Xử lý {len(todo)}/{total_left} mã còn lại (Tổng Universe: {len(universe)})")

    success_count = 0
    empty_count_run = 0
    failed_count = 0
    consecutive_transient = 0
    source_unavailable = False
    for i, tk in enumerate(todo, 1):
        # Không giữ SQLite connection/transaction trong lúc chờ network.
        outcome = fetch_one(tk, START_DATE, today)
        with closing(sqlite3.connect(DB_PATH)) as conn:
            init_db(conn)
            if outcome.status == "success":
                upsert(conn, outcome.data)
                set_meta(conn, tk, "done", len(outcome.data))
                success_count += 1
                consecutive_transient = 0
                print(
                    f" {i:>4}/{len(todo)} {tk:<10} +{len(outcome.data):>5} dòng giá "
                    f"({outcome.data['source'].iloc[0]})"
                )
            elif outcome.status == "empty":
                set_meta(conn, tk, "empty", 0)
                empty_count_run += 1
                consecutive_transient = 0
                print(f" {i:>4}/{len(todo)} {tk:<10} -> TRỐNG/HỦY NIÊM YẾT (loại trừ vĩnh viễn)")
            else:
                set_meta(conn, tk, "failed", 0)
                failed_count += 1
                consecutive_transient = (
                    consecutive_transient + 1 if outcome.transient_failure else 0
                )
                print(f" {i:>4}/{len(todo)} {tk:<10} -> THẤT BẠI ({','.join(outcome.errors)})")
        if consecutive_transient >= SOURCE_FAILURE_BUDGET:
            source_unavailable = True
            print(
                f" [circuit-breaker] Dừng sau {consecutive_transient} mã lỗi transient liên tiếp; "
                "nguồn dữ liệu có thể đang gián đoạn.",
                flush=True,
            )
            break
        if i < len(todo):
            time.sleep(REQUEST_DELAY)

    with closing(sqlite3.connect(DB_PATH)) as conn:
        done_count = conn.execute("SELECT COUNT(*) FROM meta WHERE status='done'").fetchone()[0]
        empty_count = conn.execute("SELECT COUNT(*) FROM meta WHERE status='empty'").fetchone()[0]
    print(f"[backfill] Tiến độ: Done={done_count} | Empty={empty_count} | Còn lại={total_left - len(todo)}")
    return _result_exit_code(success_count + empty_count_run, failed_count, source_unavailable)

def cmd_update():
    today = datetime.now().strftime("%Y-%m-%d")
    with closing(sqlite3.connect(DB_PATH)) as conn:
        init_db(conn)
        last = dict(conn.execute("SELECT ticker, MAX(date) FROM ohlcv GROUP BY ticker").fetchall())
    universe = [t for t in get_universe() if t in last]
    print(f" [update] Quét phần bù hằng ngày cho {len(universe)} mã hoạt động -> {today}")
    ok_count = 0
    empty_count = 0
    failed_count = 0
    consecutive_transient = 0
    source_unavailable = False
    for i, tk in enumerate(universe, 1):
        start = last[tk]
        if start >= today:
            continue
        outcome = fetch_one(tk, start, today)
        if outcome.status == "success":
            with closing(sqlite3.connect(DB_PATH)) as conn:
                init_db(conn)
                upsert(conn, outcome.data)
            ok_count += 1
            consecutive_transient = 0
            print(f" {i:>4}/{len(universe)} {tk:<10} +{len(outcome.data)} dòng mới (Từ {start})")
        elif outcome.status == "empty":
            empty_count += 1
            consecutive_transient = 0
        else:
            failed_count += 1
            consecutive_transient = (
                consecutive_transient + 1 if outcome.transient_failure else 0
            )
            print(f" {i:>4}/{len(universe)} {tk:<10} -> THẤT BẠI ({','.join(outcome.errors)})")
        if consecutive_transient >= SOURCE_FAILURE_BUDGET:
            source_unavailable = True
            print(
                f" [circuit-breaker] Dừng sau {consecutive_transient} mã lỗi transient liên tiếp; "
                "nguồn dữ liệu có thể đang gián đoạn.",
                flush=True,
            )
            break
        if i < len(universe):
            time.sleep(REQUEST_DELAY)
    print(
        f" [update] Hoàn tất: success={ok_count} | empty={empty_count} | failed={failed_count}."
    )
    return _result_exit_code(ok_count + empty_count, failed_count, source_unavailable)

def cmd_status():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        init_db(conn)
        total = len(get_universe())
        rows = dict(conn.execute("SELECT status, COUNT(*) FROM meta GROUP BY status").fetchall())
        bars = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
    print(f"[status] Done={rows.get('done',0)} | Empty={rows.get('empty',0)} | Failed={rows.get('failed',0)}")
    print(f"         Chưa xử lý={total - sum(rows.values())} | Tổng kho={bars:,} dòng giá.")
    return EXIT_SUCCESS

def cmd_export():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        df = pd.read_sql("SELECT * FROM ohlcv ORDER BY ticker, date", conn)
    if df.empty:
        print(" [export] Kho dữ liệu rỗng.")
        return EXIT_SUCCESS
    pq_path = os.path.join(OUT_DIR, "ohlcv_flat.parquet")
    csv_path = os.path.join(OUT_DIR, "ohlcv_flat.csv")
    df.to_parquet(pq_path, index=False)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f" [export] {len(df):,} dòng / {df['ticker'].nunique()} mã -> {pq_path}")
    return EXIT_SUCCESS

def upsert(conn, df):
    with conn:
        conn.executemany("""INSERT INTO ohlcv VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(ticker, date) DO UPDATE SET
            open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
            volume=excluded.volume, source=excluded.source""", df.itertuples(index=False, name=None))

def set_meta(conn, ticker, status, rows):
    with conn:
        conn.execute("""INSERT INTO meta VALUES(?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET
            status=excluded.status, rows=excluded.rows, updated=excluded.updated""",
            (ticker, status, rows, datetime.now().strftime("%Y-%m-%d %H:%M")))

CMDS = {"universe": load_full_universe, "backfill": cmd_backfill, "update": cmd_update,
        "status": cmd_status, "export": cmd_export}

def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "status"
    if cmd not in CMDS:
        print("Lệnh khả dụng:", " | ".join(CMDS.keys()))
        return EXIT_FAILURE
    if cmd == "backfill":
        return cmd_backfill(args[1] if len(args) > 1 else "pending")
    result = CMDS[cmd]()
    return result if isinstance(result, int) else EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
