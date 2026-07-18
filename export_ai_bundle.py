# ==========================================================================
# export_ai_bundle.py — Đóng gói dữ liệu mã trọng điểm để gửi AI ngoài (Python + ChatGPT/Claude/Codex)
# ==========================================================================
# LỊCH SỬ: bản đầu (P0-2/P0-3, 2026-07-17 sáng) chỉ xuất focus_extract.json nhỏ — chống truncation
# sau sự cố Gemini (xem STOCK_ANALYSIS_MASTER_PLAN.md). Bản này (2026-07-17 chiều, workflow bỏ
# Gemini — xem FINAL_STOCK_ANALYSIS_20260717.md mục "hạn chế còn lại") THÊM analysis_bundle.json:
# bundle ĐẦY ĐỦ hơn (gộp market breadth + macro + context package + provenance + data-quality
# flags) dành cho công cụ đọc file trực tiếp (Claude Code, ChatGPT Code Interpreter, Codex) —
# KHÔNG thay thế focus_extract.json (vẫn giữ nguyên, nhỏ gọn, dùng khi phải dán tay vào khung chat
# dễ bị cắt ngắn).
#
# Script:
#   1. Trích focus_extract.json — extract NHỎ cho vài mã quan tâm (mặc định POW/SSI/HPG/EVF/PAN):
#      dòng screen_snapshot_live + dòng ta_signals + điểm analysis_latest + BCTC quý gần nhất có
#      số liệu (ĐÃ XÁC MINH theo lịch dương — P0-4) + 30 nến OHLCV gần nhất.
#   2. Trích analysis_bundle.json — bundle ĐẦY ĐỦ: mọi thứ trong focus_extract + market_breadth.csv
#      + macro_snapshot.csv + context package TOÀN VĂN (nếu có) + canonical_rs_rating (P0 mới) +
#      data_quality_flags + provenance nhúng sẵn.
#   3. Ghi bundle_manifest.json: tên file / số dòng-bản ghi / ngày dữ liệu / sha256 CỦA MỌI nguồn
#      đã dùng (kể cả 2 output) — để AI (hoặc người) tự đối chiếu "mình đọc đủ chưa".
#   4. Freshness gate (nâng cấp): (a) lệch ngày > 1 phiên giữa các category — như cũ; (b) THỨ TỰ
#      TẠO ARTIFACT — chặn nếu 1 file downstream (vd ta_signals.csv) có mtime CŨ HƠN 1 file nguồn
#      nó phụ thuộc (vd screen_snapshot.csv) — bắt đúng lớp lỗi "candle_scan.py chạy trước lần
#      vn_indicators.py mới nhất" đã tìm thấy 2026-07-17 (rs_rating ta_signals lệch canonical).
#
# Dùng:
#   python export_ai_bundle.py                              # 5 mã mặc định, xuất cả 2 bundle
#   python export_ai_bundle.py --tickers POW,SSI             # tùy chỉnh
#   python export_ai_bundle.py --allow-stale                 # bỏ qua gate, ghi cảnh báo vào manifest
#   python export_ai_bundle.py --verify bundle_manifest.json # KHÔNG xuất gì — chỉ so sha256 đã ghi
#                                                              # trong 1 manifest cũ với file hiện tại
#                                                              # ("checksum dependency", mục 4)
#
# Giả định CWD = thư mục VNSTOCK (như mọi script khác trong repo — xem VNSTOCK_GUIDE.md).
# KHÔNG sửa bất kỳ file nguồn nào (chỉ đọc: DB mở read-only, CSV/JSON/parquet chỉ đọc).
# KHÔNG gọi mạng/API — toàn bộ dữ liệu lấy từ file cục bộ đã sync sẵn.
# ==========================================================================

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# Console Windows mặc định cp1252 -> vỡ khi in tiếng Việt (cùng vá như candle_scan.py dòng 14).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
AI_ANALYZE_ROOT = (SCRIPT_DIR.parent / "AI ANALYZE").resolve()
CONTEXT_PACKAGES_DIR = AI_ANALYZE_ROOT / "exports" / "context_packages"

DB_PATH = "vn_stock.db"
OUT_DIR = "."
SNAPSHOT_PATH = "screen_snapshot.csv"
SNAPSHOT_LIVE_PATH = "screen_snapshot_live.csv"
TA_SIGNALS_PATH = "ta_signals.csv"
ANALYSIS_PATH = "analysis_latest.json"
FOCUS_ANALYSIS_PATH = "Focus_Analysis.md"
FINANCIAL_SNAPSHOT_PATH = "financial_snapshot.parquet"
MARKET_BREADTH_PATH = "market_breadth.csv"
MACRO_SNAPSHOT_PATH = "macro_snapshot.csv"

DEFAULT_TICKERS = ["POW", "SSI", "HPG", "EVF", "PAN"]
OHLCV_RECENT_N = 30
MAX_TICKERS = 20

FOCUS_DATE_RE = re.compile(r"phiên snapshot mới nhất:\s*\*\*(\d{4}-\d{2}-\d{2})\*\*")
FOCUS_TICKER_RE = re.compile(r"^## (\S+)", re.MULTILINE)
PERIOD_RE = re.compile(r"(\d{4})(?:-Q([1-4]))?")

# Nguồn TÍNH GỐC (không phải bản sao) của rs_rating — xem reconcile_rs_rating() bên dưới.
CANONICAL_RS_RATING_SOURCE = (
    "screen_snapshot_live.csv:rs_rating (tính 1 lần trong vn_indicators.py main(), "
    "percentile-rank chỉ trên tập mã LIVE — xem P0-1)."
)

# Dependency graph cho freshness gate nâng cấp (mục 4): downstream -> [upstream nó tái sử dụng số
# liệu]. candle_scan.py ghi rõ trong comment là "TÁI SỬ DỤNG rs_rating từ screen_snapshot.csv,
# KHÔNG tính lại" — nên nếu ta_signals.csv cũ hơn screen_snapshot.csv, nó đang mang một BẢN SAO
# rs_rating từ lần chạy vn_indicators.py TRƯỚC, không phải lần mới nhất. Đây CHÍNH XÁC là lỗi thực
# tế tìm thấy 2026-07-17 (ta_signals.csv 16:21 vs screen_snapshot.csv 19:28 cùng ngày).
#
# CHỈ liệt kê file PIPELINE mà export_ai_bundle.py KHÔNG tự sinh ra (screen_snapshot*, ta_signals,
# market_breadth, analysis_latest) — KHÔNG đưa focus_extract.json/analysis_bundle.json vào đây: đó
# là output của CHÍNH lần chạy này, so mtime BẢN CŨ của chúng với nguồn mới ngay trước khi ghi đè
# sẽ LUÔN tự chặn một cách vô nghĩa (script đang chạy chính là bước sẽ làm chúng mới lại).
ARTIFACT_DEPENDENCY_GRAPH: dict[str, list[str]] = {
    SNAPSHOT_LIVE_PATH: [SNAPSHOT_PATH],
    MARKET_BREADTH_PATH: [SNAPSHOT_PATH],
    TA_SIGNALS_PATH: [SNAPSHOT_PATH],
    ANALYSIS_PATH: [SNAPSHOT_LIVE_PATH, TA_SIGNALS_PATH],
}


# ==========================================================================
# TIỆN ÍCH CHUNG
# ==========================================================================

def normalize_tickers(raw: str | None) -> list[str]:
    """Chuẩn hóa danh sách --tickers: uppercase, khử trùng (giữ thứ tự), chặn mã rỗng/rác."""
    if not raw:
        return list(DEFAULT_TICKERS)
    seen: list[str] = []
    for item in raw.split(","):
        tk = item.strip().upper()
        if not tk:
            continue
        if not re.fullmatch(r"[A-Z0-9]{2,10}", tk):
            raise ValueError(f"Mã không hợp lệ: '{tk}'")
        if tk not in seen:
            seen.append(tk)
    if not seen:
        raise ValueError("Danh sách --tickers rỗng")
    if len(seen) > MAX_TICKERS:
        raise ValueError(f"Quá nhiều mã ({len(seen)}) — tối đa {MAX_TICKERS}/lần"
                         " (dùng screen_snapshot.csv cho quét toàn thị trường)")
    return seen


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clean(value):
    """NaN/NaT/pd.NA -> None (JSON chuẩn không có NaN); numpy scalar -> kiểu Python gốc."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def row_to_dict(row: pd.Series) -> dict:
    return {str(k): clean(v) for k, v in row.items()}


def _period_key(period) -> tuple[int, int]:
    m = PERIOD_RE.fullmatch(str(period or ""))
    return (int(m.group(1)), int(m.group(2) or 5)) if m else (-1, -1)


def _connect_db_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"Không thấy database: {path}")
    conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")   # khóa cứng: connection này không thể ghi
    return conn


def _mtime_epoch(path: Path) -> float | None:
    return path.stat().st_mtime if path.exists() else None


def _mtime_iso(path: Path) -> str | None:
    ts = _mtime_epoch(path)
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds") if ts else None


# ==========================================================================
# ĐỌC TỪNG NGUỒN (chỉ đọc — không sửa file nào)
# ==========================================================================

def load_live_snapshot_rows(tickers: list[str]) -> tuple[dict, dict]:
    path = Path(SNAPSHOT_LIVE_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"Không thấy {path} — chạy `python vn_indicators.py` trước để sinh bản live.")
    df = pd.read_csv(path, encoding="utf-8-sig")
    by_ticker = {tk: (row_to_dict(df[df["ticker"] == tk].iloc[0])
                      if (df["ticker"] == tk).any() else None) for tk in tickers}
    info = {
        "file": path.name, "rows": int(len(df)),
        "data_date": str(df["date"].max()) if len(df) else None,
        "sha256": sha256_file(path), "mtime": _mtime_epoch(path), "mtime_iso": _mtime_iso(path),
    }
    return by_ticker, info


def load_ta_signal_rows(tickers: list[str]) -> tuple[dict, dict]:
    path = Path(TA_SIGNALS_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Không thấy {path} — chạy `python candle_scan.py` trước.")
    df = pd.read_csv(path, encoding="utf-8-sig")
    by_ticker = {tk: (row_to_dict(df[df["ticker"] == tk].iloc[0])
                      if (df["ticker"] == tk).any() else None) for tk in tickers}
    info = {
        "file": path.name, "rows": int(len(df)),
        "data_date": str(df["date"].max()) if len(df) else None,
        "sha256": sha256_file(path), "mtime": _mtime_epoch(path), "mtime_iso": _mtime_iso(path),
    }
    return by_ticker, info


def load_analysis_scores(tickers: list[str]) -> tuple[dict, dict, dict]:
    path = Path(ANALYSIS_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Không thấy {path} — chạy `python stock_analyzer.py` trước.")
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    order = payload.get("score_method", {}).get("scores_order") or ["score"]
    scores_map = payload.get("scores", {})
    by_ticker = {}
    for tk in tickers:
        values = scores_map.get(tk)
        by_ticker[tk] = {k: clean(v) for k, v in zip(order, values)} if values else None
    session_info = {
        "session_date": payload.get("summary", {}).get("session_date"),
        "regime": payload.get("summary", {}).get("regime"),
        "generated_at": payload.get("summary", {}).get("generated_at"),
    }
    info = {
        "file": path.name, "records": len(scores_map),
        "data_date": session_info["session_date"],
        "sha256": sha256_file(path), "mtime": _mtime_epoch(path), "mtime_iso": _mtime_iso(path),
    }
    return by_ticker, session_info, info


def load_financial_latest(tickers: list[str]) -> tuple[dict, dict]:
    """Lấy dòng BCTC quý GẦN NHẤT CÓ SỐ (revenue/net_profit khác NaN) cho mỗi mã, ĐÃ LOẠI các kỳ
    chưa xác minh theo lịch dương (P0-4: fiscal_period_status == 'future_relative_to_calendar_
    quarter_end', do bctc_processor.py gắn — xem flag_fiscal_period_verification() ở đó). Nếu mọi
    kỳ đều rỗng hoặc chưa xác minh, vẫn trả kỳ mới nhất theo nhãn kèm cảnh báo rõ — không bịa số."""
    path = Path(FINANCIAL_SNAPSHOT_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Không thấy {path} — chạy `python bctc_processor.py` trước.")
    df = pd.read_parquet(path)
    has_fiscal_flag = "fiscal_period_status" in df.columns
    by_ticker = {}
    for tk in tickers:
        rows = df[df["ticker"] == tk].copy()
        if rows.empty:
            by_ticker[tk] = {"period_used": None, "row": None,
                             "warning": "ticker_missing_from_financial_snapshot",
                             "excluded_unverified_periods": []}
            continue
        rows["_key"] = rows["period"].map(_period_key)
        rows = rows.sort_values("_key")
        if has_fiscal_flag:
            is_unverified = rows["fiscal_period_status"] == "future_relative_to_calendar_quarter_end"
            verified, unverified = rows[~is_unverified], rows[is_unverified]
        else:
            verified, unverified = rows, rows.iloc[0:0]
        populated = verified[verified["revenue"].notna() | verified["net_profit"].notna()]
        chosen = (populated.iloc[-1] if len(populated)
                 else (verified.iloc[-1] if len(verified) else rows.iloc[-1]))
        warning = None if len(populated) else "no_populated_period_found_all_null"
        record = row_to_dict(chosen.drop(labels="_key"))
        excluded = sorted(unverified["period"].dropna().unique().tolist())
        by_ticker[tk] = {"period_used": record.get("period"), "row": record, "warning": warning,
                         "excluded_unverified_periods": excluded}
    latest_raw_fiscal_label = (
        sorted(df["period"].dropna().unique().tolist(), key=_period_key)[-1]
        if df["period"].notna().any() else None
    )

    # item G (Data Contract Hardening v1.1): the file-level "financial date" must never be the
    # max RAW fiscal label (e.g. "2026-Q4") across the whole snapshot — some tickers' labels
    # are unverified against the calendar (future-relative or unparseable), and a raw label is
    # not itself a date. data_date becomes a real, calendar-verified date (or None); the raw
    # label moves to its own honestly-named field so nobody mistakes it for a date again.
    if has_fiscal_flag:
        unique_period_status = df.drop_duplicates("period")["fiscal_period_status"]
        status_counts = unique_period_status.value_counts()
        verified_period_count = int(status_counts.get("calendar_aligned_or_past", 0))
        unverified_period_count = int(status_counts.get("unparseable_period_label", 0))
        future_relative_to_calendar_count = int(status_counts.get("future_relative_to_calendar_quarter_end", 0))
        verified_ends = pd.to_datetime(
            df.loc[df["fiscal_period_status"] == "calendar_aligned_or_past", "period_calendar_end"],
            errors="coerce",
        ).dropna()
        latest_verified_calendar_end = verified_ends.max().strftime("%Y-%m-%d") if len(verified_ends) else None
    else:
        verified_period_count = None
        unverified_period_count = None
        future_relative_to_calendar_count = None
        latest_verified_calendar_end = None

    info = {
        "file": path.name, "rows": int(len(df)), "data_date": latest_verified_calendar_end,
        "sha256": sha256_file(path), "mtime": _mtime_epoch(path), "mtime_iso": _mtime_iso(path),
        "has_fiscal_period_flag": has_fiscal_flag,
        "latest_verified_calendar_end": latest_verified_calendar_end,
        "latest_raw_fiscal_label": latest_raw_fiscal_label,
        "verified_period_count": verified_period_count,
        "unverified_period_count": unverified_period_count,
        "future_relative_to_calendar_count": future_relative_to_calendar_count,
        "note": "BCTC theo quý — KHÔNG nằm trong freshness gate theo phiên (cadence khác giá)."
                " data_date = latest_verified_calendar_end (ngày dương lịch đã xác minh), KHÔNG"
                " phải nhãn kỳ thô lớn nhất trong file — xem latest_raw_fiscal_label nếu cần nhãn gốc.",
    }
    return by_ticker, info


def load_ohlcv_recent(conn: sqlite3.Connection, ticker: str, n: int = OHLCV_RECENT_N) -> list[dict]:
    rows = conn.execute(
        "SELECT date, open, high, low, close, volume FROM ohlcv WHERE ticker=? "
        "ORDER BY date DESC LIMIT ?", (ticker, n)).fetchall()
    cols = ["date", "open", "high", "low", "close", "volume"]
    return [{c: clean(v) for c, v in zip(cols, r)} for r in reversed(rows)]


def load_focus_analysis_info() -> dict:
    path = Path(FOCUS_ANALYSIS_PATH)
    if not path.exists():
        return {"exists": False, "file": FOCUS_ANALYSIS_PATH, "data_date": None,
                "records": None, "sha256": None, "warning": "focus_analysis_missing"}
    text = path.read_text(encoding="utf-8")
    m = FOCUS_DATE_RE.search(text)
    tickers_found = FOCUS_TICKER_RE.findall(text)
    return {
        "exists": True, "file": path.name,
        "data_date": m.group(1) if m else None,
        "records": len(tickers_found), "tickers_covered": tickers_found,
        "sha256": sha256_file(path),
        "warning": None if m else "could_not_parse_session_date_from_focus_analysis",
    }


def load_context_package_info(tickers: list[str]) -> dict:
    """Đọc chéo sang AI ANALYZE (CHỈ ĐỌC) — lấy metadata (ngày/sha256) cho freshness gate.
    Nội dung TOÀN VĂN chỉ được nhúng vào analysis_bundle.json (không phải focus_extract.json,
    xem load_context_package_full)."""
    result = {}
    for tk in tickers:
        path = CONTEXT_PACKAGES_DIR / f"{tk}_context.json"
        if not path.exists():
            result[tk] = {"exists": False, "data_date": None, "sha256": None}
            continue
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        generated_at = payload.get("generated_at")
        # Phải relative tới SCRIPT_DIR (VNSTOCK, = cwd giả định của mọi script trong repo — xem
        # docstring đầu file), KHÔNG phải AI_ANALYZE_ROOT: verify_manifest() giải "file" trong
        # manifest bằng root=Path(".") (= VNSTOCK khi chạy đúng cwd), nên "file" ghi ở đây phải
        # resolve đúng từ ĐÓ, kể cả khi context package nằm ngoài cây thư mục VNSTOCK.
        try:
            rel = Path(os.path.relpath(path, start=SCRIPT_DIR)).as_posix()
        except ValueError:
            rel = path.as_posix()
        result[tk] = {
            "exists": True, "file": rel, "generated_at": generated_at,
            "data_date": generated_at[:10] if generated_at else None,
            "sha256": sha256_file(path), "mtime": _mtime_epoch(path), "mtime_iso": _mtime_iso(path),
        }
    return result


def load_context_package_full(tk: str) -> dict | None:
    """Nội dung TOÀN VĂN context package cho 1 mã — chỉ dùng cho analysis_bundle.json (bundle lớn,
    dành cho công cụ đọc file trực tiếp). KHÔNG dùng cho focus_extract.json (giữ nhỏ theo thiết kế
    gốc chống truncation)."""
    path = CONTEXT_PACKAGES_DIR / f"{tk}_context.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_market_breadth() -> tuple[list[dict] | None, dict]:
    path = Path(MARKET_BREADTH_PATH)
    if not path.exists():
        return None, {"file": MARKET_BREADTH_PATH, "exists": False, "sha256": None}
    df = pd.read_csv(path, encoding="utf-8-sig")
    records = [row_to_dict(r) for _, r in df.iterrows()]
    info = {
        "file": path.name, "exists": True, "rows": int(len(df)),
        "data_date": str(df["date"].max()) if len(df) and "date" in df.columns else None,
        "sha256": sha256_file(path), "mtime": _mtime_epoch(path), "mtime_iso": _mtime_iso(path),
    }
    return records, info


def load_macro_snapshot() -> tuple[dict | None, dict]:
    """Trả dict khóa theo `series` (dxy, us_fedfunds, vn_gdp_yoy...) — mỗi entry giữ nguyên
    `date` riêng của series đó (macro có nhiều tần suất khác nhau — xem MarketConvention.md,
    một số series như DXY có thể trễ hơn ngày phiên giá nhiều ngày; KHÔNG coi cả bảng là 1 ngày)."""
    path = Path(MACRO_SNAPSHOT_PATH)
    if not path.exists():
        return None, {"file": MACRO_SNAPSHOT_PATH, "exists": False, "sha256": None}
    df = pd.read_csv(path, encoding="utf-8-sig")
    records = {str(r["series"]): row_to_dict(r) for _, r in df.iterrows()}
    info = {
        "file": path.name, "exists": True, "rows": int(len(df)),
        "data_date": None,  # cố ý: xem docstring — mỗi series có ngày riêng, không gộp 1 ngày
        "sha256": sha256_file(path), "mtime": _mtime_epoch(path), "mtime_iso": _mtime_iso(path),
    }
    return records, info


# ==========================================================================
# CANONICAL RS RATING (khắc phục: 2 giá trị rs_rating khác nhau không lời giải thích)
# ==========================================================================

def reconcile_rs_rating(tk: str, snapshot_rows: dict, ta_rows: dict,
                        snapshot_info: dict, ta_info: dict) -> dict:
    """Chọn canonical_rs_rating = screen_snapshot_live.csv (CANONICAL_RS_RATING_SOURCE) — nguồn
    TÍNH GỐC. ta_signals.csv chỉ TÁI SỬ DỤNG (copy) giá trị này tại thời điểm candle_scan.py chạy
    (xem candle_scan.py dòng ~23, ~242-245) — có thể lệch nếu candle_scan.py chạy TRƯỚC lần
    vn_indicators.py mới nhất (xem ARTIFACT_DEPENDENCY_GRAPH/check_artifact_order). Hàm này KHÔNG
    bao giờ trả 2 số khác nhau mà không kèm lời giải thích — đây là hợp đồng dữ liệu bắt buộc cho
    MỌI consumer (export_ai_bundle.py, build_ticker_context.py) dùng CÙNG MỘT canonical_rs_rating."""
    snap = snapshot_rows.get(tk) or {}
    ta = ta_rows.get(tk) or {}
    canonical = clean(snap.get("rs_rating"))
    cached = clean(ta.get("rs_rating"))
    result: dict = {
        "canonical_rs_rating": canonical,
        "canonical_source": CANONICAL_RS_RATING_SOURCE,
        "canonical_as_of": snapshot_info.get("mtime_iso"),
        "ta_signals_cached_rs_rating": cached,
        "ta_signals_cached_as_of": ta_info.get("mtime_iso"),
    }
    if canonical is None or cached is None:
        result["matches_canonical"] = None
        result["explanation"] = "Thiếu ít nhất một trong hai giá trị (mã không live hoặc không có tín hiệu) — không so sánh được."
        return result
    if float(canonical) == float(cached):
        result["matches_canonical"] = True
        result["explanation"] = "Khớp — ta_signals.csv đang phản ánh đúng lần chạy vn_indicators.py gần nhất."
        return result
    result["matches_canonical"] = False
    gap_txt = ""
    if snapshot_info.get("mtime") is not None and ta_info.get("mtime") is not None:
        gap = snapshot_info["mtime"] - ta_info["mtime"]
        gap_txt = f" (chênh khoảng {gap / 3600:.1f} giờ)" if abs(gap) >= 3600 else f" (chênh {gap:.0f}s)"
    result["explanation"] = (
        f"KHÔNG khớp: ta_signals.csv ghi {cached} (sinh lúc {ta_info.get('mtime_iso')}) còn "
        f"screen_snapshot_live.csv ghi {canonical} (sinh lúc {snapshot_info.get('mtime_iso')}){gap_txt}. "
        "Nguyên nhân đã xác minh (2026-07-17): candle_scan.py TÁI SỬ DỤNG rs_rating từ "
        "screen_snapshot.csv tại thời điểm nó chạy, không tính lại — nếu vn_indicators.py được "
        "chạy lại SAU candle_scan.py trong cùng phiên, ta_signals.csv giữ giá trị cũ cho tới khi "
        "candle_scan.py chạy lại. DÙNG canonical_rs_rating cho mọi phân tích/so sánh; "
        "ta_signals_cached_rs_rating chỉ giữ lại để minh bạch, KHÔNG dùng làm căn cứ."
    )
    return result


# ==========================================================================
# FRESHNESS GATE
# ==========================================================================

def get_session_anchor_and_prior(conn: sqlite3.Connection, reference_date: str) -> tuple[str, str]:
    """Phiên tham chiếu = phiên mới nhất <= reference_date; phiên liền trước lấy từ chính
    ohlcv (DISTINCT date), không phải "trừ 1 ngày lịch" — tránh sai lệch quanh cuối tuần/lễ."""
    rows = conn.execute(
        "SELECT DISTINCT date FROM ohlcv WHERE date <= ? ORDER BY date DESC LIMIT 2",
        (reference_date,)).fetchall()
    if not rows:
        raise RuntimeError(f"Không tìm thấy phiên giao dịch nào <= {reference_date} trong ohlcv")
    latest = rows[0][0]
    prior = rows[1][0] if len(rows) > 1 else latest
    return latest, prior


def check_freshness(categories: dict, prior_session: str) -> dict:
    """categories: {tên_nhóm: ngày_hoặc_None}. Nhóm có ngày < phiên liền trước -> stale (chặn)."""
    stale, unknown = [], []
    for name, date_str in categories.items():
        if date_str is None:
            unknown.append(name)
            continue
        if date_str < prior_session:
            stale.append({"category": name, "date": date_str, "prior_session_required": prior_session})
    return {"prior_session": prior_session, "stale": stale, "unknown": unknown, "blocked": bool(stale)}


def check_artifact_order(root: Path, graph: dict[str, list[str]] | None = None) -> list[dict]:
    """Nâng cấp freshness gate (mục 4): downstream KHÔNG được có mtime CŨ HƠN bất kỳ upstream nào
    nó phụ thuộc (ARTIFACT_DEPENDENCY_GRAPH) — nếu có, downstream nhiều khả năng đang mang số liệu
    sinh ra TRƯỚC lần chạy mới nhất của upstream (ví dụ thực tế: ta_signals.csv sinh trước lần
    vn_indicators.py rerun gần nhất -> rs_rating trong đó lệch canonical, xem reconcile_rs_rating).
    Chỉ so sánh các cặp mà CẢ HAI file đều tồn tại (file chưa từng sinh thì bỏ qua, không đánh giá
    được thứ tự)."""
    graph = graph or ARTIFACT_DEPENDENCY_GRAPH
    violations = []
    for downstream, upstreams in graph.items():
        d_mtime = _mtime_epoch(root / downstream)
        if d_mtime is None:
            continue
        for up in upstreams:
            u_mtime = _mtime_epoch(root / up)
            if u_mtime is None or u_mtime <= d_mtime:
                continue
            violations.append({
                "downstream": downstream, "downstream_generated_at": _mtime_iso(root / downstream),
                "upstream": up, "upstream_generated_at": _mtime_iso(root / up),
                "gap_seconds": round(u_mtime - d_mtime, 1),
                "detail": (f"{downstream} được tạo lúc {_mtime_iso(root / downstream)}, TRƯỚC "
                          f"{up} (tạo lúc {_mtime_iso(root / up)}) — {downstream} có thể đang chứa "
                          f"số liệu cũ hơn chính nguồn của nó. Chạy lại bước sinh {downstream} SAU "
                          f"khi {up} đã cập nhật."),
            })
    return violations


def verify_manifest(manifest_path: Path, root: Path) -> list[dict]:
    """'Checksum dependency' (mục 4): so sha256 đã ghi trong 1 bundle_manifest.json CŨ với sha256
    CỦA FILE HIỆN TẠI trên đĩa. Lệch -> ít nhất 1 nguồn đã đổi kể từ khi bundle đó được sinh; bundle
    (và mọi phân tích dựa trên nó) không còn đáng tin cho tới khi export lại."""
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)
    mismatches = []
    for entry in manifest.get("files", []):
        fname = entry.get("file")
        expected_sha = entry.get("sha256")
        if not fname or expected_sha is None or entry.get("exists") is False:
            continue
        candidate = root / fname
        if not candidate.exists():
            mismatches.append({"file": fname, "issue": "file_no_longer_exists",
                               "manifest_sha256": expected_sha})
            continue
        current_sha = sha256_file(candidate)
        if current_sha != expected_sha:
            mismatches.append({"file": fname, "issue": "sha256_changed",
                               "manifest_sha256": expected_sha, "current_sha256": current_sha})
    return mismatches


# ==========================================================================
# DATA QUALITY FLAGS (tổng hợp — mục 2: "provenance và data-quality flags")
# ==========================================================================

def _make_flag(
    *, scope: str, ticker: str | None, code: str, severity: str, detail: str,
    metric: str | None = None, evidence: object = None, consumer_action: str | None = None,
) -> dict:
    """Chuẩn hóa 1 data-quality flag theo hợp đồng {code,severity,scope,ticker,metric,message,
    evidence,consumer_action} — mục F, Data Contract Hardening v1.1. `detail` giữ nguyên (mọi
    consumer cũ đọc field này không đổi); `message` là alias — cùng nội dung, tên mới."""
    return {
        "scope": scope, "ticker": ticker, "code": code, "severity": severity,
        "detail": detail, "message": detail,
        "metric": metric, "evidence": evidence, "consumer_action": consumer_action,
    }


def build_data_quality_flags(tickers: list[str], entries: dict,
                             artifact_order_violations: list[dict]) -> list[dict]:
    flags: list[dict] = []
    for v in artifact_order_violations:
        flags.append(_make_flag(
            scope="pipeline", ticker=None, code="artifact_created_before_upstream", severity="warning",
            detail=v["detail"], evidence=v,
            consumer_action="Re-run the downstream script after its upstream dependency, then rebuild the bundle.",
        ))
    for tk in tickers:
        e = entries.get(tk) or {}
        rs = e.get("rs_rating_reconciliation") or {}
        if rs.get("matches_canonical") is False:
            flags.append(_make_flag(
                scope="ticker", ticker=tk, code="rs_rating_mismatch", severity="info",
                detail=rs.get("explanation"), metric="rs_rating", evidence=rs,
                consumer_action="Use canonical_rs_rating for this ticker; do not use ta_signal.rs_rating.",
            ))
        excluded = (e.get("financial_latest_quality") or {}).get("excluded_unverified_periods") or []
        if excluded:
            flags.append(_make_flag(
                scope="ticker", ticker=tk, code="unverified_fiscal_period_excluded", severity="info",
                detail=f"{tk}: loại kỳ {excluded} khỏi lựa chọn 'kỳ mới nhất' vì ngày kết thúc"
                      " quý/năm dương lịch mà nhãn kỳ ngụ ý còn ở tương lai so với hôm nay"
                      " (dấu hiệu năm tài chính lệch hoặc lỗi nhãn nguồn — xem bctc_processor.py"
                      " flag_fiscal_period_verification).",
                metric="financial_latest", evidence=excluded,
                consumer_action="Do not reintroduce these periods as 'latest' without independently verifying calendar alignment.",
            ))
        for w in e.get("warnings", []):
            flags.append(_make_flag(
                scope="ticker", ticker=tk, code="extract_warning", severity="warning",
                detail=f"{tk}: {w}", evidence=w,
                consumer_action="Investigate the missing source before treating this ticker's data as complete.",
            ))
    return flags


# item F: metrics whose financial_summary.{metric}_meta.status can actually reach "stale" in
# build_ticker_context.py (must track FINANCIAL_CONTRACT_METRICS there) / "mapping_missing".
_STALE_PROMOTABLE_METRICS = (
    "operating_cash_flow", "ebit", "ebitda", "interest_expense", "retained_earnings",
    "depreciation", "sga",
)
_MAPPING_MISSING_PROMOTABLE_METRICS = ("ebit", "ebitda", "interest_expense", "retained_earnings")


def build_context_package_flags(tickers: list[str], bundle_entries: dict) -> list[dict]:
    """Đưa tín hiệu chất lượng dữ liệu đã có sẵn TRONG context_package (từng mã) lên root
    data_quality_flags — mục F, Data Contract Hardening v1.1. root data_quality_flags trước đây
    có thể rỗng dù context package mang cảnh báo thật vì build_data_quality_flags() ở trên chỉ
    nhìn vào `entries` (dựng trước khi context_package được gắn vào `bundle_entries`) — xem
    main() bên dưới cho điểm gọi đúng.

    Nguyên tắc chọn tín hiệu để promote (tránh ngập lụt false positive):
    - KHÔNG BAO GIỜ promote status not_applicable/reported/derived/proxy — đây là các trạng
      thái "đã xác nhận, không phải vấn đề" theo đúng hợp đồng missing_data_contract.
    - Chỉ promote khi một AI đọc RIÊNG data_quality_flags (không đọc hết context_package) có
      thể hành động sai/thiếu nếu không biết tín hiệu này.
    """
    flags: list[dict] = []
    for tk in tickers:
        package = (bundle_entries.get(tk) or {}).get("context_package")
        if not package:
            continue
        financial_summary = package.get("financial_summary") or {}
        for metric in _STALE_PROMOTABLE_METRICS:
            meta = financial_summary.get(f"{metric}_meta") or {}
            if meta.get("status") == "stale":
                flags.append(_make_flag(
                    scope="ticker", ticker=tk, code="financial_metric_stale", severity="warning",
                    detail=f"{tk}: {metric} status=stale — {meta.get('reason')}",
                    metric=metric, evidence=meta,
                    consumer_action="Do not treat this metric's value as current for the latest period;"
                                    " check its own period against financial_summary.latest_period before using it.",
                ))
            elif meta.get("status") == "mapping_missing" and metric in _MAPPING_MISSING_PROMOTABLE_METRICS:
                flags.append(_make_flag(
                    scope="ticker", ticker=tk, code="financial_metric_mapping_missing", severity="info",
                    detail=f"{tk}: {metric} status=mapping_missing — {meta.get('reason')}",
                    metric=metric, evidence=meta,
                    consumer_action="Not derivable from the current mapping registry for this ticker; do not infer a value.",
                ))

        roe_ttm_meta = financial_summary.get("roe_ttm_meta") or {}
        external_roe_meta = (package.get("valuation_inputs") or {}).get("roe_meta") or {}
        if roe_ttm_meta.get("status") == "insufficient_periods" and external_roe_meta.get("value") is not None:
            flags.append(_make_flag(
                scope="ticker", ticker=tk, code="roe_local_ttm_unavailable_external_roe_present", severity="info",
                detail=f"{tk}: financial_summary.roe_ttm is insufficient_periods while"
                      f" valuation_inputs.roe={external_roe_meta.get('value')} ({external_roe_meta.get('unit')},"
                      " external, different source/methodology) is available.",
                metric="roe_ttm", evidence={"roe_ttm_meta": roe_ttm_meta, "external_roe_meta": external_roe_meta},
                consumer_action="Do not substitute valuation_inputs.roe for financial_summary.roe_ttm or vice versa"
                                " — different source, different unit/basis.",
            ))

        share_reconciliation = package.get("share_reconciliation") or {}
        if share_reconciliation.get("status") in ("material_warning", "warning"):
            severity = "warning" if share_reconciliation["status"] == "material_warning" else "info"
            code = "share_count_material_mismatch" if share_reconciliation["status"] == "material_warning" else "share_count_mismatch"
            flags.append(_make_flag(
                scope="ticker", ticker=tk, code=code, severity=severity,
                detail=f"{tk}: shares_period_end vs shares_current differ by {share_reconciliation.get('mismatch_pct')}%.",
                metric="shares_outstanding", evidence=share_reconciliation,
                consumer_action=share_reconciliation.get("consumer_action"),
            ))

        section_coverage = (package.get("data_quality") or {}).get("section_coverage") or {}
        if (section_coverage.get("financial_summary") or {}).get("status") == "missing":
            flags.append(_make_flag(
                scope="ticker", ticker=tk, code="financial_summary_missing", severity="error",
                detail=f"{tk}: financial_summary has zero available metrics.",
                metric="financial_summary", evidence=section_coverage.get("financial_summary"),
                consumer_action="Do not report any financial figures for this ticker; the source data is entirely unavailable.",
            ))
        for section in ("news_summary", "shareholder_summary"):
            if (section_coverage.get(section) or {}).get("status") == "missing":
                flags.append(_make_flag(
                    scope="ticker", ticker=tk, code=f"{section}_missing", severity="warning",
                    detail=f"{tk}: {section} has zero available metrics.",
                    metric=section, evidence=section_coverage.get(section),
                    consumer_action=f"Do not claim {section.replace('_', ' ')} coverage for this ticker.",
                ))

        entity_type = (package.get("identity") or {}).get("entity_type")
        if entity_type == "unknown":
            flags.append(_make_flag(
                scope="ticker", ticker=tk, code="entity_type_unclassified", severity="info",
                detail=f"{tk}: entity_type is unknown — corporate-only ratios (ebit/ebitda/sga/liquidity)"
                       " were not derived because this ticker is not yet profiled in"
                       " ticker_entity_profiles.csv, not because they are confirmed inapplicable.",
                metric="entity_type", evidence={"entity_type": entity_type},
                consumer_action="Do not assume this is a corporate entity, and do not read its missing"
                                " ebit/ebitda/liquidity ratios as confirmed not_applicable.",
            ))
    return flags


# ==========================================================================
# LẮP GHÉP ENTRY 1 MÃ (dùng chung cho focus_extract.json VÀ analysis_bundle.json)
# ==========================================================================

def build_ticker_entry(tk, conn, snapshot_rows, ta_rows, score_rows, score_session,
                       financial_rows, snapshot_info, ta_info) -> dict:
    warnings = []
    if snapshot_rows.get(tk) is None:
        warnings.append("khong_co_trong_screen_snapshot_live (mã không live hoặc chưa sync)")
    if ta_rows.get(tk) is None:
        warnings.append("khong_co_trong_ta_signals")
    if score_rows.get(tk) is None:
        warnings.append("khong_co_diem_trong_analysis_latest")
    fin = financial_rows.get(tk) or {}
    if fin.get("warning"):
        warnings.append(f"financial_snapshot: {fin['warning']}")
    ohlcv = load_ohlcv_recent(conn, tk)
    if not ohlcv:
        warnings.append("khong_co_du_lieu_ohlcv")
    rs_reconciliation = reconcile_rs_rating(tk, snapshot_rows, ta_rows, snapshot_info, ta_info)
    return {
        "snapshot": snapshot_rows.get(tk),
        "canonical_rs_rating": rs_reconciliation["canonical_rs_rating"],
        "rs_rating_reconciliation": rs_reconciliation,
        "ta_signal": ta_rows.get(tk),
        "analysis_score": {
            "session_date": score_session["session_date"],
            "regime": score_session["regime"],
            "values": score_rows.get(tk),
        },
        "financial_latest": fin.get("row"),
        "financial_period_used": fin.get("period_used"),
        "financial_latest_quality": {
            "excluded_unverified_periods": fin.get("excluded_unverified_periods", []),
        },
        "ohlcv_recent": ohlcv,
        "ohlcv_recent_count": len(ohlcv),
        "warnings": warnings,
    }


def build_focus_extract(tickers, conn, snapshot_rows, ta_rows, score_rows, score_session,
                        financial_rows, snapshot_info, ta_info):
    return {tk: build_ticker_entry(tk, conn, snapshot_rows, ta_rows, score_rows, score_session,
                                   financial_rows, snapshot_info, ta_info)
           for tk in tickers}


def build_manifest_files(tickers, snapshot_info, ta_info, analysis_info, financial_info,
                         breadth_info, macro_info, focus_analysis_info, context_info) -> list[dict]:
    """Danh sách file nguồn + output dùng CHUNG cho bundle_manifest.json['files'] VÀ
    analysis_bundle.json['provenance'] — một nguồn duy nhất, tránh lặp lại lỗi "2 bản sao lệch
    nhau không giải thích" đã sửa ở canonical_rs_rating."""
    files = [
        {"file": snapshot_info["file"], "role": "source", "row_or_record_count": snapshot_info["rows"],
         "count_basis": "csv_rows", "data_date": snapshot_info["data_date"],
         "sha256": snapshot_info["sha256"], "generated_at": snapshot_info.get("mtime_iso")},
        {"file": ta_info["file"], "role": "source", "row_or_record_count": ta_info["rows"],
         "count_basis": "csv_rows", "data_date": ta_info["data_date"],
         "sha256": ta_info["sha256"], "generated_at": ta_info.get("mtime_iso")},
        {"file": analysis_info["file"], "role": "source", "row_or_record_count": analysis_info["records"],
         "count_basis": "json_ticker_scores", "data_date": analysis_info["data_date"],
         "sha256": analysis_info["sha256"], "generated_at": analysis_info.get("mtime_iso")},
        {"file": financial_info["file"], "role": "source_informational_not_in_gate",
         "row_or_record_count": financial_info["rows"], "count_basis": "parquet_rows",
         "data_date": financial_info["data_date"], "sha256": financial_info["sha256"],
         "generated_at": financial_info.get("mtime_iso"),
         "has_fiscal_period_flag": financial_info.get("has_fiscal_period_flag"),
         "latest_verified_calendar_end": financial_info.get("latest_verified_calendar_end"),
         "latest_raw_fiscal_label": financial_info.get("latest_raw_fiscal_label"),
         "verified_period_count": financial_info.get("verified_period_count"),
         "unverified_period_count": financial_info.get("unverified_period_count"),
         "future_relative_to_calendar_count": financial_info.get("future_relative_to_calendar_count"),
         "note": financial_info["note"]},
    ]
    if breadth_info.get("exists"):
        files.append({"file": breadth_info["file"], "role": "source",
                      "row_or_record_count": breadth_info["rows"], "count_basis": "csv_rows",
                      "data_date": breadth_info["data_date"], "sha256": breadth_info["sha256"],
                      "generated_at": breadth_info.get("mtime_iso")})
    else:
        files.append({"file": MARKET_BREADTH_PATH, "role": "source", "exists": False,
                      "warning": "market_breadth_missing"})
    if macro_info.get("exists"):
        files.append({"file": macro_info["file"], "role": "source",
                      "row_or_record_count": macro_info["rows"], "count_basis": "csv_rows_one_per_series",
                      "data_date": macro_info["data_date"], "sha256": macro_info["sha256"],
                      "generated_at": macro_info.get("mtime_iso")})
    else:
        files.append({"file": MACRO_SNAPSHOT_PATH, "role": "source", "exists": False,
                      "warning": "macro_snapshot_missing"})
    if focus_analysis_info["exists"]:
        files.append({
            "file": focus_analysis_info["file"], "role": "source",
            "row_or_record_count": focus_analysis_info["records"],
            "count_basis": "markdown_ticker_sections",
            "data_date": focus_analysis_info["data_date"], "sha256": focus_analysis_info["sha256"],
            "warning": focus_analysis_info["warning"],
        })
    else:
        files.append({"file": FOCUS_ANALYSIS_PATH, "role": "source", "exists": False,
                      "warning": "focus_analysis_missing"})
    for tk, ctx in context_info.items():
        files.append({
            "file": ctx.get("file", f"../AI ANALYZE/exports/context_packages/{tk}_context.json"),
            "role": "source_context_package", "ticker": tk, "exists": ctx["exists"],
            "row_or_record_count": None, "count_basis": "single_ticker_package",
            "data_date": ctx.get("data_date"), "sha256": ctx.get("sha256"),
            "generated_at": ctx.get("mtime_iso"),
        })
    return files


# ==========================================================================
# MAIN
# ==========================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Đóng gói focus_extract.json + analysis_bundle.json + bundle_manifest.json"
                    " cho vài mã quan tâm.")
    parser.add_argument("--tickers", help="Danh sách mã cách nhau bởi dấu phẩy"
                        " (mặc định POW,SSI,HPG,EVF,PAN)")
    parser.add_argument("--allow-stale", action="store_true",
                        help="Vẫn xuất bundle dù nguồn lệch phiên/lệch thứ tự tạo artifact"
                             " (ghi cảnh báo rõ vào manifest)")
    parser.add_argument("--verify", metavar="MANIFEST_PATH",
                        help="KHÔNG xuất gì — chỉ so sha256 trong 1 bundle_manifest.json cũ với"
                             " file hiện tại trên đĩa ('checksum dependency'); exit 0 nếu khớp"
                             " hết, 1 nếu có lệch.")
    args = parser.parse_args()

    if args.verify:
        manifest_path = Path(args.verify)
        if not manifest_path.exists():
            print(f"[export_ai_bundle] LỖI: không thấy manifest '{manifest_path}'", file=sys.stderr)
            return 2
        mismatches = verify_manifest(manifest_path, Path("."))
        if not mismatches:
            print(f"[export_ai_bundle] --verify OK: mọi sha256 trong {manifest_path} vẫn khớp file hiện tại.")
            return 0
        print(f"[export_ai_bundle] --verify LỆCH: {len(mismatches)} nguồn đã đổi kể từ khi"
             f" {manifest_path} được sinh:", file=sys.stderr)
        for m in mismatches:
            print(f"   - {m['file']}: {m['issue']}", file=sys.stderr)
        return 1

    try:
        tickers = normalize_tickers(args.tickers)
    except ValueError as exc:
        print(f"[export_ai_bundle] LỖI tham số: {exc}", file=sys.stderr)
        return 2

    try:
        snapshot_rows, snapshot_info = load_live_snapshot_rows(tickers)
        ta_rows, ta_info = load_ta_signal_rows(tickers)
        score_rows, score_session, analysis_info = load_analysis_scores(tickers)
        financial_rows, financial_info = load_financial_latest(tickers)
        focus_analysis_info = load_focus_analysis_info()
        context_info = load_context_package_info(tickers)
        breadth_records, breadth_info = load_market_breadth()
        macro_records, macro_info = load_macro_snapshot()
        conn = _connect_db_readonly(Path(DB_PATH))
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"[export_ai_bundle] LỖI: {exc}", file=sys.stderr)
        return 2

    try:
        reference_date = snapshot_info["data_date"]
        if not reference_date:
            print("[export_ai_bundle] LỖI: screen_snapshot_live.csv rỗng"
                 " — không xác định được phiên tham chiếu.", file=sys.stderr)
            return 2
        latest_session, prior_session = get_session_anchor_and_prior(conn, reference_date)

        categories = {
            "screen_snapshot_live": snapshot_info["data_date"],
            "ta_signals": ta_info["data_date"],
            "analysis_latest": analysis_info["data_date"],
            "focus_analysis": focus_analysis_info["data_date"],
        }
        context_dates = [v["data_date"] for v in context_info.values() if v.get("data_date")]
        categories["context_package"] = min(context_dates) if context_dates else None

        freshness = check_freshness(categories, prior_session)
        order_violations = check_artifact_order(Path("."))
        freshness["artifact_order_violations"] = order_violations
        freshness["blocked"] = bool(freshness["blocked"] or order_violations)
        freshness["reference_session"] = latest_session
        freshness["allow_stale"] = args.allow_stale
        freshness["categories_checked"] = categories
        freshness["context_package_coverage"] = {tk: v["exists"] for tk, v in context_info.items()}

        if freshness["blocked"] and not args.allow_stale:
            print("[export_ai_bundle] CHẶN: dữ liệu lệch phiên hoặc lệch thứ tự tạo artifact"
                 " — KHÔNG xuất bundle.", file=sys.stderr)
            for item in freshness["stale"]:
                print(f"   - lệch phiên: {item['category']}: {item['date']}"
                     f" (cần >= {item['prior_session_required']})", file=sys.stderr)
            for v in order_violations:
                print(f"   - lệch thứ tự artifact: {v['detail']}", file=sys.stderr)
            print("   Chạy lại với --allow-stale nếu cố tình muốn xuất"
                 " (sẽ ghi cảnh báo rõ vào manifest).", file=sys.stderr)
            return 1
        freshness["status"] = "stale_override" if freshness["blocked"] else "fresh"

        entries = build_focus_extract(tickers, conn, snapshot_rows, ta_rows, score_rows,
                                      score_session, financial_rows, snapshot_info, ta_info)
    finally:
        conn.close()

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    data_quality_flags = build_data_quality_flags(tickers, entries, order_violations)

    # ---------------------------------------------------------------- focus_extract.json (nhỏ)
    focus_extract = {
        "schema_version": "1.1.0",
        "generated_at": generated_at,
        "reference_session_date": latest_session,
        "tickers_requested": tickers,
        "freshness": freshness,
        "canonical_sources": {"rs_rating": CANONICAL_RS_RATING_SOURCE},
        "tickers": entries,
        "ai_instructions": [
            "Nếu một mã trong tickers_requested có warnings khác rỗng nghĩa là THIẾU dữ liệu phần đó"
            " — DỪNG và báo lại, TUYỆT ĐỐI không tự suy diễn/bịa số liệu kỹ thuật thay thế.",
            "Dùng canonical_rs_rating cho mọi phân tích/so sánh RS — KHÔNG dùng"
            " ta_signal.rs_rating (có thể là bản sao cũ hơn, xem rs_rating_reconciliation).",
            "financial_latest đã loại các kỳ CHƯA XÁC MINH theo lịch dương (xem"
            " financial_latest_quality.excluded_unverified_periods) — không tự thêm lại.",
            "Không dùng dữ liệu kỹ thuật/giá ngoài file này cho các mã trên; tin doanh nghiệp/vĩ mô"
            " từ nguồn ngoài phải kèm URL.",
            "Nếu freshness.status = stale_override, phải nêu rõ trong báo cáo là dữ liệu có phần cũ"
            " hơn 1 phiên hoặc lệch thứ tự tạo artifact (xem freshness.stale /"
            " freshness.artifact_order_violations).",
        ],
    }
    out_path = Path(OUT_DIR) / "focus_extract.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(focus_extract, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")

    # ---------------------------------------------------------- analysis_bundle.json (đầy đủ)
    bundle_entries = {}
    for tk in tickers:
        entry = dict(entries[tk])  # copy nông — không sửa entries gốc (focus_extract vẫn nhỏ)
        entry["context_package"] = load_context_package_full(tk)
        entry["news_related"] = (
            (entry["context_package"] or {}).get("news_summary")
            if entry["context_package"] else None
        )
        if entry["context_package"] is None:
            entry.setdefault("warnings", []).append(
                "khong_co_context_package (chưa build_ticker_context.py cho mã này -> thiếu"
                " news_related/shareholder/valuation_inputs chi tiết)")
        bundle_entries[tk] = entry

    # item F: bundle_entries[tk]["context_package"] only exists from this point on (it isn't
    # attached to the earlier `entries` build_data_quality_flags() already consumed above) —
    # this is the correct, and only correct, place to promote context-package-embedded
    # data-quality signals up to the bundle-level data_quality_flags root.
    data_quality_flags = data_quality_flags + build_context_package_flags(tickers, bundle_entries)

    manifest_files = build_manifest_files(tickers, snapshot_info, ta_info, analysis_info,
                                          financial_info, breadth_info, macro_info,
                                          focus_analysis_info, context_info)

    analysis_bundle = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "reference_session_date": latest_session,
        "tickers_requested": tickers,
        "freshness": freshness,
        "canonical_sources": {"rs_rating": CANONICAL_RS_RATING_SOURCE},
        "market_breadth": breadth_records,
        "macro_snapshot": macro_records,
        "tickers": bundle_entries,
        "data_quality_flags": data_quality_flags,
        "provenance": manifest_files,
        "ai_instructions": focus_extract["ai_instructions"] + [
            "market_breadth là TOÀN BỘ market_breadth.csv (ALL + từng ngành); macro_snapshot là"
            " TOÀN BỘ macro_snapshot.csv theo series — MỖI series có ngày dữ liệu RIÊNG (field"
            " 'date' trong từng entry), không suy ra cả bảng cùng 1 ngày.",
            "context_package (nếu khác null) là TOÀN VĂN context package AI ANALYZE cho mã đó —"
            " ưu tiên field trong context_package.technical_summary.rs_rating (đã đồng bộ canonical)"
            " thay vì tính lại.",
            "data_quality_flags liệt kê MỌI bất thường đã phát hiện tự động (rs_rating lệch, kỳ BCTC"
            " chưa xác minh bị loại, artifact tạo sai thứ tự...) — đọc hết trước khi phân tích,"
            " đừng chỉ đọc phần 'tickers'.",
        ],
    }
    bundle_path = Path(OUT_DIR) / "analysis_bundle.json"
    with bundle_path.open("w", encoding="utf-8") as f:
        json.dump(analysis_bundle, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")

    # ---------------------------------------------------------------- bundle_manifest.json
    manifest_files = manifest_files + [
        {"file": "focus_extract.json", "role": "output",
         "row_or_record_count": len(entries), "count_basis": "tickers_in_bundle",
         "data_date": latest_session, "sha256": sha256_file(out_path)},
        {"file": "analysis_bundle.json", "role": "output",
         "row_or_record_count": len(bundle_entries), "count_basis": "tickers_in_bundle",
         "data_date": latest_session, "sha256": sha256_file(bundle_path)},
    ]
    manifest = {
        "schema_version": "1.1.0",
        "generated_at": generated_at,
        "tickers": tickers,
        "freshness": freshness,
        "data_quality_flags": data_quality_flags,
        "files": manifest_files,
    }
    if freshness["status"] == "stale_override":
        manifest["STALE_DATA_WARNING"] = (
            "Bundle được xuất với --allow-stale dù có nguồn lệch quá 1 phiên giao dịch hoặc lệch"
            f" thứ tự tạo artifact so với phiên tham chiếu {latest_session}. Xem freshness.stale và"
            " freshness.artifact_order_violations để biết mã/nguồn cụ thể."
            " KHÔNG dùng làm căn cứ phân tích chính thức nếu không thực sự cần thiết."
        )

    manifest_path = Path(OUT_DIR) / "bundle_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")

    status_word = "CẢNH BÁO STALE (--allow-stale)" if freshness["status"] == "stale_override" else "OK"
    print(f"[export_ai_bundle] {status_word} — {len(tickers)} mã"
         f" -> {out_path.name} + {bundle_path.name} + {manifest_path.name}")
    print(f"   Phiên tham chiếu: {latest_session} · phiên liền trước: {prior_session}")
    if order_violations:
        print(f"   [CẢNH BÁO] {len(order_violations)} vi phạm thứ tự tạo artifact (xem manifest).")
    if data_quality_flags:
        print(f"   [data_quality_flags] {len(data_quality_flags)} cờ — xem bundle_manifest.json/analysis_bundle.json.")
    for tk in tickers:
        w = entries[tk]["warnings"]
        flag = f" (CẢNH BÁO: {'; '.join(w)})" if w else ""
        print(f"   - {tk}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
