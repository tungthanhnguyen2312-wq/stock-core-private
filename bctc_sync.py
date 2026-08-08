#!/usr/bin/env python3
"""Download quarterly financial statements (BCTC) via vnstock.

Nhánh BCTC của VNSTOCK (gộp từ dự án FINANCIAL_REPORT độc lập cũ, 2026-07-12).
Không dùng chung vn_stock.db, không ghi vào VNSTOCK/data/ (thư mục web publish).
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal
from vn_time import vn_now

import pandas as pd

# Console Windows mặc định cp1252 -> vỡ khi in tiếng Việt
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==========================================
# CẤU HÌNH HỆ THỐNG
# ==========================================
ROOT_DIR = Path(__file__).resolve().parent
OUT_DIR = ROOT_DIR / "data_bctc"
LOG_DIR = ROOT_DIR / "logs"
META_FILE = OUT_DIR / "scrape_meta.csv"
# [!] tickers_bctc.txt, KHÔNG PHẢI tickers.txt — trùng tên với universe giá của VNSTOCK
# (1.745 mã, dùng cho vn_stock_pipeline.py). 2 file hiện giống hệt nhau về nội dung
# (từng được copy từ tickers.txt lúc khởi tạo FINANCIAL_REPORT) nhưng tách tên để
# tránh 1 bên sửa mà bên kia không hay — xem VNSTOCK/NOTES_FOR_TUNG_MERGE.md.
TICKERS_FILE = ROOT_DIR / "tickers_bctc.txt"
CONFIG_FILE = ROOT_DIR / "config.json"

PRIMARY_SRC = "KBS"
FAILOVER_SRC = "VCI"
PERIOD = "quarter"

REQUEST_DELAY = 1.1
MAX_RETRY = 3
BACKOFF_BASE = 5
BACKOFF_RATE = 15

REPORT_TYPES: dict[str, tuple[str, str]] = {
    "balance": ("balance_sheet", "Bảng cân đối"),
    "income": ("income_statement", "KQKD"),
    "cashflow": ("cash_flow", "LCTT"),
}

NET_FAIL = "NET_FAIL"
EMPTY_DATA = "EMPTY_DATA"

ReportKey = Literal["balance", "income", "cashflow"]

# ==========================================
# LOGGING
# ==========================================
def setup_logging() -> logging.Logger:
    """Console + file log, cùng phong cách timestamp như VNSTOCK logs/."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("bctc_sync")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(LOG_DIR / "bctc_sync.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


log = setup_logging()

# ==========================================
# CÔNG CỤ CHUNG
# ==========================================
def load_config(path: Path | None = None) -> dict:
    """Đọc config.json nếu có; trả dict rỗng nếu không."""
    cfg_path = path or CONFIG_FILE
    if not cfg_path.exists():
        return {}
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f)


def _finance(symbol: str, source: str):
    from vnstock.api.financial import Finance

    return Finance(source=source, symbol=symbol)


def call_api(fn: Callable[[], pd.DataFrame | None], label: str):
    """Gọi API với delay/retry/backoff giống vn_stock_pipeline.py / meta_sync.py.

    Trả về:
        DataFrame nếu OK
        None nếu nguồn xác nhận rỗng
        NET_FAIL nếu lỗi mạng/rate-limit sau MAX_RETRY
    """
    for attempt in range(1, MAX_RETRY + 1):
        try:
            res = fn()
            time.sleep(REQUEST_DELAY)
            if res is None or len(res) == 0:
                return None
            return res
        except Exception as e:
            inner = getattr(getattr(e, "last_attempt", None), "exception", lambda: None)()
            msg = str(inner if inner is not None else e).lower()
            if any(k in msg for k in ("dữ liệu trống", "no data", "empty")):
                return None
            is_rate = any(k in msg for k in ("rate", "429", "quá nhiều", "too many"))
            is_net = any(k in msg for k in (
                "timeout", "connection", "disconnected", "reset", "502", "503", "504",
            ))
            if is_rate or is_net:
                wait = (BACKOFF_RATE if is_rate else BACKOFF_BASE) * attempt + random.uniform(0, 2)
                lbl = "Rate-Limit" if is_rate else "Lỗi Mạng Tạm Thời"
                print(f"   [{lbl}] {label} - Thử lại sau {wait:.1f}s (Lần {attempt}/{MAX_RETRY})")
                log.warning("%s %s attempt %s/%s", lbl, label, attempt, MAX_RETRY)
                time.sleep(wait)
            else:
                print(f"   [Lỗi Hệ Thống] {label}: {str(inner if inner is not None else e)[:70]}")
                log.error("Fatal %s: %s", label, inner if inner is not None else e)
                return None
    return NET_FAIL


def normalize_report(
    df: pd.DataFrame,
    ticker: str,
    report_type: str,
    source: str,
) -> pd.DataFrame:
    """Chuẩn hóa DataFrame trước khi lưu."""
    out = df.copy()
    out.columns = [str(c) for c in out.columns]
    out.insert(0, "ticker", ticker.upper())
    out.insert(1, "report_type", report_type)
    out.insert(2, "source", source)
    out.insert(3, "scraped_at", vn_now().strftime("%Y-%m-%d %H:%M"))
    return out


def output_paths(ticker: str, report_key: ReportKey, period_type: str) -> tuple[Path, Path]:
    """[VÁ P0-1 12/07/2026] Tên PHẢI chứa period_type — trước đây {TICKER}_{report_type}.parquet
    không phân biệt quarter/year nên `scrape --period year` XÓA MẤT dữ liệu quarter cùng tên
    (dù scrape_meta.csv vẫn ghi done). Đã migrate 3.580/3.582 file cũ sang tên mới (1 nhóm BIO
    không xác định được period_type từ nội dung — giữ nguyên tên cũ, xem NOTES_FOR_TUNG.md)."""
    method, _ = REPORT_TYPES[report_key]
    stem = f"{ticker.upper()}_{method}_{period_type}"
    return OUT_DIR / f"{stem}.parquet", OUT_DIR / f"{stem}.csv"


def save_report(df: pd.DataFrame, ticker: str, report_key: ReportKey, period_type: str) -> None:
    """Lưu Parquet + CSV (utf-8-sig) — cùng quy ước export của vn_stock_pipeline."""
    pq_path, csv_path = output_paths(ticker, report_key, period_type)
    df.to_parquet(pq_path, index=False)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")


def normalize_period_str(raw_period: str) -> str:
    """Normalize irregular period strings to a standard format (YYYY-QX or YYYY).
    
    Handles variations like:
      - 2025Q1, 2025Q1_1, 2025Q1.1, 2025Q1_2 -> 2025-Q1
      - 2025-Q1, 2025-Q1_1, 2025-Q1.1 -> 2025-Q1
      - 2025-Year, 2025Year, 2025_Year, 2025-Năm, 2025Năm -> 2025
      - 2025, 2025.1, 2025_1 -> 2025
    """
    p_clean = str(raw_period).strip().upper()
    
    # 1. Quarterly match
    q_match = re.match(r"^(\d{4})[-_.]?[Q](\d)(?:[._-]\d+)?$", p_clean)
    if q_match:
        year, quarter = q_match.group(1), q_match.group(2)
        return f"{year}-Q{quarter}"
        
    # 2. Yearly match
    y_match = re.match(r"^(\d{4})(?:[-_.]?(?:YEAR|NĂM))?(?:[._-]\d+)?$", p_clean)
    if y_match:
        return y_match.group(1)
        
    return p_clean.split("_")[0].split(".")[0].strip()


def load_meta() -> pd.DataFrame:
    cols = ["ticker", "report_type", "period_type", "status", "rows", "start_period", "end_period", "source", "updated"]
    if META_FILE.exists():
        df = pd.read_csv(META_FILE, dtype=str).fillna("")
        for col in cols:
            if col not in df.columns:
                df[col] = ""
        return df[cols]
    return pd.DataFrame(columns=cols)


def upsert_meta(
    ticker: str,
    report_key: ReportKey,
    period_type: str,
    status: str,
    rows: int,
    start_period: str = "",
    end_period: str = "",
    source: str = "",
) -> None:
    method, _ = REPORT_TYPES[report_key]
    meta = load_meta()
    row = {
        "ticker": ticker.upper(),
        "report_type": method,
        "period_type": period_type,
        "status": status,
        "rows": str(rows),
        "start_period": start_period,
        "end_period": end_period,
        "source": source,
        "updated": vn_now().strftime("%Y-%m-%d %H:%M"),
    }
    mask = (
        (meta["ticker"] == row["ticker"]) & 
        (meta["report_type"] == row["report_type"]) &
        (meta["period_type"] == row["period_type"])
    )
    meta = meta[~mask]
    meta = pd.concat([meta, pd.DataFrame([row])], ignore_index=True)
    meta.to_csv(META_FILE, index=False, encoding="utf-8-sig")


def is_done(ticker: str, report_key: ReportKey, period_type: str, refresh: bool) -> bool:
    """Resume: bỏ qua mã đã done/empty trừ khi --refresh."""
    if refresh:
        return False
    pq_path, _ = output_paths(ticker, report_key, period_type)
    if not pq_path.exists():
        return False
    meta = load_meta()
    method, _ = REPORT_TYPES[report_key]
    hit = meta[
        (meta["ticker"] == ticker.upper()) & 
        (meta["report_type"] == method) &
        (meta["period_type"] == period_type)
    ]
    if hit.empty:
        return False
    return hit.iloc[0]["status"] in ("done", "empty")


def fetch_report(ticker: str, report_key: ReportKey, period: str):
    """Tải một báo cáo; thử PRIMARY_SRC rồi FAILOVER_SRC."""
    method, _ = REPORT_TYPES[report_key]
    net_fail = False
    for source in (PRIMARY_SRC, FAILOVER_SRC):
        label = f"{ticker}@{source}.{method}"
        raw = call_api(
            lambda s=source: getattr(_finance(ticker, s), method)(period=period),
            label,
        )
        if raw is NET_FAIL:
            net_fail = True
            continue
        if isinstance(raw, pd.DataFrame):
            return normalize_report(raw, ticker, method, source), source
    if net_fail:
        return NET_FAIL, ""
    return EMPTY_DATA, ""


def read_ticker_file(path: Path) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")]


def load_tickers(args: argparse.Namespace) -> list[str]:
    """Ưu tiên: --tickers > --file > config.json > tickers.txt."""
    if args.tickers:
        return [t.strip().upper() for t in args.tickers if t.strip()]
    if args.file:
        path = Path(args.file)
        if path.exists():
            return read_ticker_file(path)
        raise SystemExit(f"Không tìm thấy file mã: {path}")
    cfg = load_config(Path(args.config) if args.config else CONFIG_FILE)
    if cfg.get("tickers"):
        return [str(t).strip().upper() for t in cfg["tickers"] if str(t).strip()]
    if TICKERS_FILE.exists():
        return read_ticker_file(TICKERS_FILE)
    raise SystemExit(
        "Không có mã — truyền --tickers, --file, config.json hoặc tickers_bctc.txt"
    )


def resolve_report_keys(args: argparse.Namespace) -> list[ReportKey]:
    if args.reports:
        return args.reports
    cfg = load_config(Path(args.config) if getattr(args, "config", None) else CONFIG_FILE)
    cfg_reports = cfg.get("reports")
    if cfg_reports:
        valid = set(REPORT_TYPES)
        return [r for r in cfg_reports if r in valid]
    return ["balance", "income", "cashflow"]


def resolve_period(args: argparse.Namespace) -> str:
    if getattr(args, "period", None):
        return args.period
    cfg = load_config(Path(args.config) if getattr(args, "config", None) else CONFIG_FILE)
    return cfg.get("period", PERIOD)


# ==========================================
# HỆ THỐNG LỆNH ĐIỀU KHIỂN
# ==========================================
def cmd_scrape(args: argparse.Namespace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tickers = load_tickers(args)
    if args.limit:
        tickers = tickers[: args.limit]
    report_keys = resolve_report_keys(args)
    period = resolve_period(args)

    total_jobs = len(tickers) * len(report_keys)
    print(
        f"[scrape] {len(tickers)} mã x {len(report_keys)} báo cáo "
        f"= {total_jobs} job | period={period}"
    )
    log.info("Start scrape: tickers=%s reports=%s period=%s", tickers, report_keys, period)

    job_i = 0
    for tk in tickers:
        for rk in report_keys:
            job_i += 1
            method, _ = REPORT_TYPES[rk]
            if is_done(tk, rk, period, args.refresh):
                print(f" {job_i:>4}/{total_jobs} {tk:<10} {method:<18} -> BỎ QUA (đã có)")
                continue

            result, source = fetch_report(tk, rk, period)
            if isinstance(result, str) and result == NET_FAIL:
                upsert_meta(tk, rk, period, "failed", 0)
                print(f" {job_i:>4}/{total_jobs} {tk:<10} {method:<18} -> THẤT BẠI mạng (N/A)")
            elif isinstance(result, str) and result == EMPTY_DATA:
                upsert_meta(tk, rk, period, "empty", 0)
                print(f" {job_i:>4}/{total_jobs} {tk:<10} {method:<18} -> TRỐNG (N/A)")
            else:
                save_report(result, tk, rk, period)
                # Quét các cột có chứa định dạng năm dùng str.match(r"^\d{4}")
                period_cols = result.columns[result.columns.astype(str).str.match(r"^\d{4}")]
                cleaned_periods = [normalize_period_str(c) for c in period_cols]
                cleaned_periods = [p for p in cleaned_periods if p]
                if cleaned_periods:
                    sorted_periods = sorted(cleaned_periods)
                    start_period = sorted_periods[0]
                    end_period = sorted_periods[-1]
                else:
                    start_period = ""
                    end_period = ""
                upsert_meta(tk, rk, period, "done", len(result), start_period=start_period, end_period=end_period, source=source)
                print(
                    f" {job_i:>4}/{total_jobs} {tk:<10} {method:<18} "
                    f"+{len(result):>4} dòng ({start_period} -> {end_period}) ({source})"
                )

            time.sleep(REQUEST_DELAY)

    done = len(list(OUT_DIR.glob("*.parquet")))
    print(f"[scrape] Hoàn tất. {done} file parquet trong {OUT_DIR.name}/")


def cmd_status(_args: argparse.Namespace) -> None:
    meta = load_meta()
    if meta.empty:
        print("[status] Chưa có dữ liệu. Chạy: python bctc_sync.py scrape --tickers HPG")
        return
    print("[status] Tiến độ scrape_meta.csv:")
    for st, n in meta["status"].value_counts().items():
        print(f"         {st}={n}")
    pq_count = len(list(OUT_DIR.glob("*.parquet")))
    csv_count = len(list(OUT_DIR.glob("*.csv"))) - (1 if META_FILE.exists() else 0)
    print(f"         parquet={pq_count} | csv={csv_count}")
    # Summary of stored period ranges
    valid_periods = [p for p in meta["start_period"].tolist() + meta["end_period"].tolist() if p]
    if valid_periods:
        sorted_p = sorted(list(set(valid_periods)))
        print(f"         Khoảng thời gian lưu trữ: {sorted_p[0]} -> {sorted_p[-1]}")


def cmd_failed(args: argparse.Namespace) -> None:
    """Chạy lại các job status=failed (giống backfill failed của pipeline giá)."""
    meta = load_meta()
    if meta.empty:
        print("[failed] Không có meta.")
        return
    failed = meta[meta["status"] == "failed"]
    if failed.empty:
        print("[failed] Không có job thất bại.")
        return
    rev = {v[0]: k for k, v in REPORT_TYPES.items()}
    tickers = sorted(failed["ticker"].unique())
    reports: list[ReportKey] = []
    for _, row in failed.iterrows():
        rk = rev.get(row["report_type"])
        if rk and rk not in reports:
            reports.append(rk)
    args.tickers = tickers
    args.reports = reports or None
    args.refresh = True
    cmd_scrape(args)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Tải BCTC quý (BCĐK / KQKD / LCTT) — nhánh BCTC của VNSTOCK",
    )
    ap.add_argument(
        "--config",
        default=str(CONFIG_FILE),
        help="đường dẫn config.json (mặc định: config.json trong thư mục project)",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_scrape = sub.add_parser("scrape", help="tải báo cáo tài chính")
    p_scrape.add_argument("--tickers", nargs="+", help="một hoặc nhiều mã, VD: HPG FPT")
    p_scrape.add_argument("--file", help="file danh sách mã (mỗi dòng một mã)")
    p_scrape.add_argument("--refresh", action="store_true", help="cào lại cả mã đã có")
    p_scrape.add_argument("--limit", type=int, default=0, help="chỉ xử lý N mã đầu (test)")
    p_scrape.add_argument(
        "--reports",
        nargs="+",
        choices=["balance", "income", "cashflow"],
        help="chọn loại báo cáo (mặc định: cả 3)",
    )
    p_scrape.add_argument(
        "--period",
        choices=["quarter", "year"],
        default=None,
        help="chu kỳ báo cáo (mặc định: quarter)",
    )
    p_scrape.set_defaults(func=cmd_scrape)

    p_status = sub.add_parser("status", help="xem tiến độ")
    p_status.set_defaults(func=cmd_status)

    p_failed = sub.add_parser("failed", help="thử lại các job thất bại")
    p_failed.add_argument("--limit", type=int, default=0)
    p_failed.set_defaults(func=cmd_failed)

    return ap


def main() -> None:
    ap = build_parser()
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
