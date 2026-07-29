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
from atomic_io import atomic_write_json
try:
    from observability_events import (
        EventOutcome,
        EventStage,
        build_observability_event,
        emit_observability_event,
    )
except ImportError:
    from stock_core_private.observability_events import (
        EventOutcome,
        EventStage,
        build_observability_event,
        emit_observability_event,
    )
try:
    from price_basis_contract import (
        PriceBasis,
        VolumeBasis,
        qualify_price_basis,
        qualify_volume_basis,
    )
except ImportError:
    from stock_core_private.price_basis_contract import (
        PriceBasis,
        VolumeBasis,
        qualify_price_basis,
        qualify_volume_basis,
    )
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from shareholder_pipeline import DONE, calculate_major_shareholder_delta
from live_universe import summary as live_universe_summary
from freshness_history import evaluate_analysis_readiness, freshness_envelope
from financial_canonicalization import canonicalize_financial_rows
from official_evidence import load_cited_financial_records
from financial_identity import empty_identity_export
from corporate_actions_export import build_corporate_actions_section
from financial_observations import canonical_records, store_path
from semantic_evidence_bridge import enrich_canonical_records, reconcile_metric_identities, load_verified_share_basis, latest_share_basis, load_verified_market_price, load_verified_ebitda_components, derive_ebitda
from financial_mapping import get_default_registry
from fundamental_quality import evaluate_fundamental_quality
from relative_valuation import evaluate_relative_valuation
from intrinsic_valuation import evaluate_intrinsic_valuation
from scenario_analysis import evaluate_scenario_analysis
from opportunity_ranking import evaluate_opportunity, rank_opportunities
from risk_liquidity import evaluate_market_risk

# Console Windows mặc định cp1252 -> vỡ khi in tiếng Việt (cùng vá như candle_scan.py dòng 14).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent


def ai_runtime_root() -> Path:
    """Locate the AI runtime in the new layout, with legacy-layout fallbacks."""
    candidates = (
        SCRIPT_DIR.parent / "ai-runtime",
        SCRIPT_DIR.parent / "AI ANALYZE",
        SCRIPT_DIR.parent.parent / "AI ANALYZE",
    )
    return next((path.resolve() for path in candidates if path.exists()), candidates[0].resolve())


AI_RUNTIME_ROOT = ai_runtime_root()
CONTEXT_PACKAGES_DIR = AI_RUNTIME_ROOT / "exports" / "context_packages"

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
RUNTIME_ROOT_ENV = "STOCK_LOOKUP_RUNTIME_ROOT"
AI_RUNTIME_ROOT_ENV = "STOCK_LOOKUP_AI_RUNTIME_ROOT"
CONTEXT_PACKAGES_DIR_ENV = "STOCK_LOOKUP_CONTEXT_PACKAGES_DIR"


def runtime_root() -> Path:
    """Return the runtime-data root, preserving the legacy CWD default."""
    configured = os.environ.get(RUNTIME_ROOT_ENV)
    return Path(configured) if configured else Path(".")


def context_packages_dir() -> Path:
    """Resolve context packages explicitly for an isolated pilot when requested.

    The legacy/default path is intentionally unchanged.  A caller must set this
    variable explicitly; there is no discovery of a production runtime path.
    """
    explicit_packages = os.environ.get(CONTEXT_PACKAGES_DIR_ENV)
    if explicit_packages:
        return Path(explicit_packages)
    configured = os.environ.get(AI_RUNTIME_ROOT_ENV)
    root = Path(configured) if configured else AI_RUNTIME_ROOT
    return root / "exports" / "context_packages"

def runtime_path(relative_path: str) -> Path:
    """Resolve a runtime artifact without changing its legacy relative-path default."""
    return runtime_root() / relative_path

def output_path(relative_path: str) -> Path:
    """Resolve generated output in the active runtime (or an absolute test override)."""
    path = Path(relative_path)
    return path if path.is_absolute() else runtime_path(relative_path)


def context_package_reference(ticker: str) -> str:
    """Return a manifest path relative to the active dashboard runtime root."""
    path = context_packages_dir() / f"{ticker}_context.json"
    try:
        return Path(os.path.relpath(path, start=runtime_root().resolve())).as_posix()
    except ValueError:
        return path.as_posix()

DEFAULT_TICKERS = ["POW", "SSI", "HPG", "EVF", "PAN"]
OHLCV_RECENT_N = 30
MAX_TICKERS = 20

# Contract for the basis of prices used by OHLCV-derived metrics.  This is deliberately
# independent of a provider name, endpoint, or column spelling: none of those proves
# whether a series has been adjusted for corporate actions.  Until a producer supplies
# verified metadata, the bundle must communicate ``unknown`` rather than guessing.
PRICE_BASIS_VALUES = frozenset({"raw", "adjusted", "unknown"})
PRICE_BASIS_UNVERIFIED_CODE = "price_basis_unverified"

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


def normalize_price_basis(value: object = None, verified: object = False) -> tuple[str, bool]:
    """Return the safe canonical OHLCV price-basis pair.

    ``raw`` and ``adjusted`` are accepted only with an explicit verified boolean.  Old
    inputs without these fields, invalid values, and unverified claims all normalize to
    ``("unknown", False)``.  This prevents a missing field from silently becoming an
    adjusted-price assertion.
    """
    basis = str(value).strip().lower() if value is not None else ""
    is_verified = verified is True
    if is_verified and basis in {"raw", "adjusted"}:
        return basis, True
    return "unknown", False


def build_price_basis_contract(metadata: dict | None = None) -> dict:
    """Build complete price-basis & volume-basis provenance contract for bundle outputs."""
    metadata = metadata or {}
    p_contract = qualify_price_basis(
        metadata.get("price_basis"),
        verified=metadata.get("price_basis_verified") is True,
        adjustment_source=metadata.get("adjustment_source"),
        effective_date=metadata.get("effective_date"),
    )
    v_contract = qualify_volume_basis(
        metadata.get("volume_basis", VolumeBasis.RAW_SHARES_TRADED.value),
        verified=metadata.get("volume_basis_verified") is not False,
    )
    return {
        "price_basis": p_contract["price_basis"],
        "price_basis_verified": p_contract["price_basis_verified"],
        "is_actionable": p_contract["is_actionable"],
        "volume_basis": v_contract["volume_basis"],
        "volume_basis_verified": v_contract["volume_basis_verified"],
        "adjustment_source": p_contract["adjustment_source"],
        "effective_date": p_contract["effective_date"],
        "limitations": p_contract["limitations"],
        "source": metadata.get("source") if p_contract["price_basis_verified"] else "no_verified_price_basis_metadata",
    }


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
    path = runtime_path(SNAPSHOT_LIVE_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"Không thấy {path} — chạy `python vn_indicators.py` trước để sinh bản live.")
    df = pd.read_csv(path, encoding="utf-8-sig")
    if "live_universe_status" not in df.columns:
        if "is_live" in df.columns and df["is_live"].astype(str).str.lower().eq("true").all():
            df["live_universe_status"] = "live"
            df["live_universe_reason"] = "legacy_live_snapshot"
        else:
            raise ValueError("screen_snapshot_live.csv lacks live-universe contract")
    if not df["live_universe_status"].astype(str).eq("live").all():
        raise ValueError("screen_snapshot_live.csv violates live-universe contract")
    by_ticker = {tk: (row_to_dict(df[df["ticker"] == tk].iloc[0])
                      if (df["ticker"] == tk).any() else None) for tk in tickers}
    info = {
        "file": path.name, "rows": int(len(df)),
        "data_date": str(df["date"].max()) if len(df) else None,
        "sha256": sha256_file(path), "mtime": _mtime_epoch(path), "mtime_iso": _mtime_iso(path),
        "live_universe": live_universe_summary(
            pd.read_csv(runtime_path(SNAPSHOT_PATH), encoding="utf-8-sig")
            if runtime_path(SNAPSHOT_PATH).exists() else df,
            source=SNAPSHOT_PATH if runtime_path(SNAPSHOT_PATH).exists() else SNAPSHOT_LIVE_PATH,
        ),
    }
    return by_ticker, info


def load_ta_signal_rows(tickers: list[str]) -> tuple[dict, dict]:
    path = runtime_path(TA_SIGNALS_PATH)
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
    path = runtime_path(ANALYSIS_PATH)
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
    path = runtime_path(FINANCIAL_SNAPSHOT_PATH)
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


def load_financial_canonical(tickers: list[str]) -> dict[str, dict]:
    """Additive canonical records; legacy financial_latest remains unchanged."""
    df = pd.read_parquet(runtime_path(FINANCIAL_SNAPSHOT_PATH))
    observation_records = canonical_records(store_path(runtime_root()), {ticker: get_default_registry().entity_type_for(ticker) for ticker in tickers})
    observation_records = enrich_canonical_records(observation_records, runtime_root())
    observation_records = reconcile_metric_identities(observation_records)
    # Standalone PDF-cited facts (profit_before_tax, interest_expense,
    # depreciation_and_amortization), same pattern as share_basis_citations.jsonl --
    # none of these is part of a retained VCI raw observation. See
    # docs/hpg_fy2024_ebitda_qualification.md for the formula and its evidence.
    verified_ebitda_components = load_verified_ebitda_components(runtime_root())
    result = {}
    for ticker in tickers:
        canonical = canonicalize_financial_rows(df, ticker)
        evidence = load_cited_financial_records(runtime_root(), ticker)
        ebitda_record = derive_ebitda(verified_ebitda_components["by_key"], ticker)
        extra_records = [ebitda_record] if ebitda_record is not None else []
        canonical["records"] = sorted(
            canonical["records"] + evidence["records"] + observation_records.get(ticker, []) + extra_records,
            key=lambda record: (record["canonical_metric"], (record.get("period_identity") or {}).get("period", ""),
                                record["statement_scope"], record["source"]),
        )
        canonical["official_evidence"] = {"status": evidence["status"], "reason": evidence["reason"],
                                            "record_count": len(evidence["records"])}
        result[ticker] = canonical
    return result


def load_ohlcv_recent(conn: sqlite3.Connection, ticker: str, n: int = OHLCV_RECENT_N) -> list[dict]:
    rows = conn.execute(
        "SELECT date, open, high, low, close, volume FROM ohlcv WHERE ticker=? "
        "ORDER BY date DESC LIMIT ?", (ticker, n)).fetchall()
    cols = ["date", "open", "high", "low", "close", "volume"]
    return [{c: clean(v) for c, v in zip(cols, r)} for r in reversed(rows)]


# ===========================================================================
# CORPORATE INTELLIGENCE (read-only, source-scoped snapshot export)
# ===========================================================================

def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _json_object(value: object) -> dict | None:
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _corporate_status(items: list[dict]) -> str:
    if not items:
        return "missing"
    valid = sum(item["status"] == "available" for item in items)
    return "available" if valid == len(items) else ("partial" if valid else "malformed")


def _corporate_overall_status(*sections: dict) -> str:
    statuses = [section["status"] for section in sections]
    if "available" in statuses:
        return "available" if all(status == "available" for status in statuses) else "partial"
    return "malformed" if "malformed" in statuses else "missing"


def _snapshot_envelope(row: tuple) -> dict:
    return {
        "snapshot_id": row[0], "schema_version": row[1], "source_name": row[2],
        "source_reference": row[3], "snapshot_date": row[4], "raw_hash": row[5],
        "record_count": row[6], "snapshot_status": row[7], "is_complete": row[8],
    }


def _latest_rows_by_source(conn: sqlite3.Connection, table: str, ticker: str) -> list[tuple]:
    rows = conn.execute(
        f"SELECT snapshot_id,schema_version,source_name,source_reference,fetched_at,raw_hash,record_count,status,is_complete,raw_payload_json "
        f"FROM {table} WHERE ticker=? ORDER BY source_name, fetched_at DESC, snapshot_id DESC", (ticker,)
    ).fetchall()
    latest: dict[str, tuple] = {}
    for row in rows:
        latest.setdefault(row[2], row)
    return list(latest.values())


def _load_profile_intelligence(conn: sqlite3.Connection, ticker: str) -> dict:
    if not (_table_exists(conn, "company_profile_snapshots") and _table_exists(conn, "company_profile_records")):
        return {"status": "missing", "reason": "snapshot_tables_unavailable", "sources": []}
    sources = []
    for row in _latest_rows_by_source(conn, "company_profile_snapshots", ticker):
        item = _snapshot_envelope(row)
        records = conn.execute(
            "SELECT provider_identity,identity_basis,qualified_fields_json,raw_record_json,provenance_json "
            "FROM company_profile_records WHERE snapshot_id=?", (row[0],)
        ).fetchall()
        if row[7] != "complete_response" or row[8] != 1 or row[6] != 1 or len(records) != 1 or _json_object(row[9]) is None:
            item.update({"status": "malformed_snapshot", "reason": "manifest_or_record_count_invalid"})
        else:
            record = records[0]
            qualified, raw, provenance = (_json_object(value) for value in record[2:])
            if not all((qualified, raw, provenance)):
                item.update({"status": "malformed_snapshot", "reason": "record_json_invalid"})
            else:
                item.update({"status": "available", "record": {
                    "provider_identity": record[0], "identity_basis": record[1],
                    "qualified_fields": qualified, "raw_record": raw, "provenance": provenance,
                }})
        sources.append(item)
    return {"status": _corporate_status(sources), "sources": sources}


def _load_collection_intelligence(conn: sqlite3.Connection, ticker: str, *, table: str, record_table: str,
                                  field_names: list[str]) -> dict:
    if not (_table_exists(conn, table) and _table_exists(conn, record_table)):
        return {"status": "missing", "reason": "snapshot_tables_unavailable", "sources": []}
    columns = ["source_record_identity", *field_names, "raw_record_json", "provenance_json"]
    sources = []
    for row in _latest_rows_by_source(conn, table, ticker):
        item = _snapshot_envelope(row)
        records = conn.execute(f"SELECT {','.join(columns)} FROM {record_table} WHERE snapshot_id=?", (row[0],)).fetchall()
        if row[7] != "complete_response" or row[8] != 1 or row[6] != len(records) or _json_object(row[9]) is None:
            item.update({"status": "malformed_snapshot", "reason": "manifest_or_record_count_invalid"})
        else:
            output, malformed = [], False
            for record in records:
                raw, provenance = _json_object(record[-2]), _json_object(record[-1])
                if raw is None or provenance is None:
                    malformed = True
                    break
                output.append({"source_record_identity": record[0], "fields": dict(zip(field_names, record[1:-2])),
                               "raw_record": raw, "provenance": provenance})
            if malformed:
                item.update({"status": "malformed_snapshot", "reason": "record_json_invalid"})
            else:
                item.update({"status": "available", "records": output})
        sources.append(item)
    return {"status": _corporate_status(sources), "sources": sources}


def _major_records_for_snapshot(conn: sqlite3.Connection, snapshot: tuple) -> list[dict]:
    rows = conn.execute(
        "SELECT ticker,holder_name,normalized_holder_name,shares,ownership_pct,as_of_date,source_name,source_reference,"
        "record_origin,reconciliation_status,provenance_json FROM shareholder_records_v2 "
        "WHERE ticker=? AND as_of_date=? AND source_name=? AND source_reference IS ? AND record_origin='api'",
        (snapshot[2], snapshot[3], snapshot[4], snapshot[6]),
    ).fetchall()
    records = []
    for row in rows:
        try:
            provenance = json.loads(row[10])
        except (TypeError, ValueError):
            return []
        records.append({
            "ticker": row[0], "holder_name": row[1], "normalized_holder_name": row[2], "shares": row[3],
            "ownership_pct": row[4], "as_of_date": row[5], "source_name": row[6], "source_reference": row[7],
            "record_origin": row[8], "reconciliation_status": row[9], "provenance": provenance,
        })
    return records


def _load_major_shareholders_intelligence(conn: sqlite3.Connection, ticker: str) -> dict:
    if not (_table_exists(conn, "major_shareholder_snapshots") and _table_exists(conn, "shareholder_records_v2")):
        return {"status": "missing", "reason": "snapshot_tables_unavailable", "sources": []}
    rows = conn.execute(
        "SELECT snapshot_id,schema_version,ticker,as_of_date,source_name,record_origin,source_reference,fetched_at,record_count,status,is_complete "
        "FROM major_shareholder_snapshots WHERE ticker=? AND status=? AND is_complete=1 AND record_origin='api' "
        "ORDER BY source_name, source_reference, as_of_date DESC, fetched_at DESC", (ticker, DONE),
    ).fetchall()
    latest: dict[tuple, tuple] = {}
    for row in rows:
        latest.setdefault((row[4], row[6]), row)
    sources = []
    for current in latest.values():
        records = _major_records_for_snapshot(conn, current)
        item = {
            "snapshot_id": current[0], "schema_version": current[1], "source_name": current[4],
            "source_reference": current[6], "snapshot_date": current[3], "fetched_at": current[7],
            "record_count": current[8], "snapshot_status": current[9], "is_complete": current[10],
        }
        if len(records) != current[8] or not records:
            item.update({"status": "malformed_snapshot", "reason": "manifest_or_record_count_invalid"})
        else:
            previous = conn.execute(
                "SELECT snapshot_id,schema_version,ticker,as_of_date,source_name,record_origin,source_reference,fetched_at,record_count,status,is_complete "
                "FROM major_shareholder_snapshots WHERE ticker=? AND source_name=? AND source_reference IS ? "
                "AND status=? AND is_complete=1 AND record_origin='api' AND as_of_date<? "
                "ORDER BY as_of_date DESC, fetched_at DESC LIMIT 1",
                (ticker, current[4], current[6], DONE, current[3]),
            ).fetchone()
            if previous is None:
                delta = {"status": "missing_prior_snapshot", "reason": "no_prior_comparable_snapshot", "changes": []}
            else:
                previous_records = _major_records_for_snapshot(conn, previous)
                previous_manifest = {
                    "snapshot_id": previous[0], "ticker": previous[2], "as_of_date": previous[3],
                    "source_name": previous[4], "record_origin": previous[5], "source_reference": previous[6],
                    "status": previous[9], "is_complete": previous[10],
                }
                current_manifest = {
                    "snapshot_id": current[0], "ticker": current[2], "as_of_date": current[3],
                    "source_name": current[4], "record_origin": current[5], "source_reference": current[6],
                    "status": current[9], "is_complete": current[10],
                }
                delta = calculate_major_shareholder_delta(previous_manifest, previous_records, current_manifest, records)
            item.update({"status": "available", "records": records, "delta": delta})
        sources.append(item)
    return {"status": _corporate_status(sources), "sources": sources}



def _load_corporate_events_intelligence(conn: sqlite3.Connection, ticker: str) -> dict:
    """Export bounded VCI observations without asserting complete event history."""
    tables = ("corporate_event_records", "corporate_event_observations", "corporate_event_ingestion_runs")
    if not all(_table_exists(conn, table) for table in tables):
        return {"status": "missing", "reason": "forward_observation_tables_unavailable", "sources": []}
    record_columns = {row[1] for row in conn.execute("PRAGMA table_info(corporate_event_records)")}
    action_fields = "action_type_vi,action_type_en," if {"action_type_vi", "action_type_en"} <= record_columns else "NULL AS action_type_vi,NULL AS action_type_en,"
    rows = conn.execute(
        "SELECT record_id,provider,provider_event_id,event_code,category,event_name_vi,event_name_en,event_title_vi,event_title_en,"
        "display_date1,display_date2,public_date,record_date,exright_date,issue_date,start_date,end_date," + action_fields +
        "payout_date,listing_date,exercise_ratio,value_per_share,last_observed_at,revision_status,coverage_status "
        "FROM corporate_event_records WHERE ticker=? ORDER BY provider,provider_event_id", (ticker,),
    ).fetchall()
    if not rows:
        return {"status": "missing", "reason": "no_forward_event_observations", "sources": []}
    records = []
    for row in rows:
        observation = conn.execute(
            "SELECT raw_payload_hash,retrieved_at,vnstock_version,endpoint,parameters_json,coverage_status "
            "FROM corporate_event_observations WHERE record_id=? ORDER BY retrieved_at DESC,observation_id DESC LIMIT 1", (row[0],),
        ).fetchone()
        parameters = _json_object(observation[4]) if observation else None
        if observation is None or parameters is None or row[1] != "VCI" or not row[2] or row[25] != "partial_unqualified_50_row_cap":
            return {"status": "malformed", "reason": "forward_event_record_invalid", "sources": []}
        fields = dict(zip([
            "event_code", "category", "event_name_vi", "event_name_en", "event_title_vi", "event_title_en",
            "display_date1", "display_date2", "public_date", "record_date", "exright_date", "issue_date",
            "start_date", "end_date", "action_type_vi", "action_type_en", "payout_date", "listing_date", "exercise_ratio", "value_per_share",
        ], row[3:23]))
        records.append({"provider_event_id": row[2], "fields": fields, "provenance": {
            "provider": row[1], "raw_payload_hash": observation[0], "retrieved_at": observation[1],
            "vnstock_version": observation[2], "endpoint": observation[3], "parameters": parameters,
            "coverage_status": observation[5], "revision_status": row[24],
        }})
    coverage = "partial_unqualified_50_row_cap"
    return {"status": "partial", "reason": "forward_observations_not_complete_history", "coverage_status": coverage,
            "warnings": ["VCI public events are bounded observations (50-row cap); not complete history or lifecycle status."],
            "sources": [{"source_name": "VCI", "coverage_status": coverage, "record_count": len(records), "records": records}]}

def load_corporate_intelligence(conn: sqlite3.Connection, ticker: str) -> dict:
    """Load latest provider snapshots without merging source semantics."""
    profile = _load_profile_intelligence(conn, ticker)
    subsidiaries = _load_collection_intelligence(
        conn, ticker, table="company_subsidiary_snapshots", record_table="company_subsidiary_records",
        field_names=["provider_record_id", "organization_name", "relationship_type", "ownership_percent",
                     "ownership_unit", "charter_capital", "currency", "provider_update_date"],
    )
    ownership = _load_collection_intelligence(
        conn, ticker, table="ownership_structure_snapshots", record_table="ownership_structure_records",
        field_names=["owner_type", "ownership_percentage", "shares_owned", "update_date"],
    )
    events = _load_corporate_events_intelligence(conn, ticker)
    return {
        "status": _corporate_overall_status(profile, subsidiaries, ownership),
        "company_profile": profile,
        "company_subsidiaries": subsidiaries,
        "ownership_structure": ownership,
        "major_shareholders": _load_major_shareholders_intelligence(conn, ticker),
        "corporate_events": events,
        "corporate_actions": build_corporate_actions_section(events),
    }


def load_focus_analysis_info() -> dict:
    path = runtime_path(FOCUS_ANALYSIS_PATH)
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
    """Đọc chéo sang AI runtime (CHỈ ĐỌC) — lấy metadata (ngày/sha256) cho freshness gate.
    Nội dung TOÀN VĂN chỉ được nhúng vào analysis_bundle.json (không phải focus_extract.json,
    xem load_context_package_full)."""
    result = {}
    for tk in tickers:
        path = context_packages_dir() / f"{tk}_context.json"
        if not path.exists():
            result[tk] = {"exists": False, "data_date": None, "sha256": None}
            continue
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        generated_at = payload.get("generated_at")
        result[tk] = {
            "exists": True, "file": context_package_reference(tk), "generated_at": generated_at,
            "data_date": generated_at[:10] if generated_at else None,
            "sha256": sha256_file(path), "mtime": _mtime_epoch(path), "mtime_iso": _mtime_iso(path),
        }
    return result


def load_context_package_full(tk: str) -> dict | None:
    """Nội dung TOÀN VĂN context package cho 1 mã — chỉ dùng cho analysis_bundle.json (bundle lớn,
    dành cho công cụ đọc file trực tiếp). KHÔNG dùng cho focus_extract.json (giữ nhỏ theo thiết kế
    gốc chống truncation)."""
    path = context_packages_dir() / f"{tk}_context.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_market_breadth() -> tuple[list[dict] | None, dict]:
    path = runtime_path(MARKET_BREADTH_PATH)
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
    path = runtime_path(MACRO_SNAPSHOT_PATH)
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
                             artifact_order_violations: list[dict],
                             price_basis: dict | None = None) -> list[dict]:
    flags: list[dict] = []
    price_basis = price_basis or build_price_basis_contract()
    if not price_basis["price_basis_verified"]:
        flags.append(_make_flag(
            scope="pipeline", ticker=None, code=PRICE_BASIS_UNVERIFIED_CODE, severity="warning",
            detail="OHLCV price basis is unknown because no verified provider contract or metadata is available; "
                   "do not assume prices or derived return/MA/RS metrics are corporate-action adjusted.",
            metric="price_basis", evidence=price_basis,
            consumer_action="Treat OHLCV-derived metrics as basis-unverified until a verified raw or adjusted "
                            "price-basis contract is supplied.",
        ))
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

# Higher wins when two "available" records compete for the same canonical_metric
# name (e.g. the exact, per-item-cited observation-store pipeline vs. the
# narrative annual-report bridge in official_evidence.py, which may cover a
# different period). Explicit and deterministic -- never an accident of
# whatever order canonical["records"] happens to be sorted in.
_SOURCE_RIGOR = {"financial_observation_store": 2, "official_evidence": 1}


def _financial_input(canonical: dict | None) -> dict[str, dict]:
    """Reshape additive canonical records into the {metric: record} form that
    relative_valuation/intrinsic_valuation expect. Excludes placeholder records
    with no value or no real period identity -- they can never satisfy a
    downstream gate and their period_identity=None shape crashes
    intrinsic_valuation's unguarded .get("period_identity", {}) chain, which was
    never exercised while every call site passed financial={}."""
    records = (canonical or {}).get("records", []) if isinstance(canonical, dict) else []
    by_metric: dict[str, dict] = {}
    for record in records:
        metric = record.get("canonical_metric")
        if metric is None or record.get("value") is None or not isinstance(record.get("period_identity"), dict):
            continue
        candidate_rank = (record.get("quality_state") == "available", _SOURCE_RIGOR.get(record.get("source"), 0))
        current = by_metric.get(metric)
        current_rank = (current.get("quality_state") == "available", _SOURCE_RIGOR.get(current.get("source"), 0)) if current else (False, -1)
        if candidate_rank > current_rank:
            by_metric[metric] = record
    return by_metric


def _net_net_share_count(tk: str) -> dict | None:
    """A period-end share count for Net-Net, cited to the audited statement notes.

    Returns None (Net-Net's share_count input is simply omitted) when no
    verified period-end citation exists for this ticker -- never a
    weighted-average or live/valuation-date count substituted in its place.
    """
    verified = load_verified_share_basis(runtime_root())
    entry = latest_share_basis(verified["by_identity"], tk, "period_end_shares_outstanding")
    if entry is None:
        return None
    return {
        "value": entry["value"],
        "semantics": "period_end",
        "period_identity": {"period": entry["reporting_period"], "period_type": entry["reporting_frequency"]},
        "source": "share_basis_evidence",
        "evidence": {"evidence_id": entry["evidence_id"], "citation_id": entry["citation_id"], "citation": entry["citation"]},
    }


def _relative_valuation_period_end_share_count(tk: str) -> dict | None:
    """The same period-end share-count identity as _net_net_share_count, shaped for
    relative_valuation's P/B and historical market-cap reconstruction. Kept as its
    own function (rather than sharing Net-Net's) so Net-Net's wiring is never
    touched by this milestone; never a weighted-average or live count."""
    verified = load_verified_share_basis(runtime_root())
    entry = latest_share_basis(verified["by_identity"], tk, "period_end_shares_outstanding")
    if entry is None:
        return None
    return {
        "value": entry["value"],
        "semantics": "period_end",
        "period_identity": {"period": entry["reporting_period"], "period_type": entry["reporting_frequency"]},
        "source": "share_basis_evidence",
        "evidence": {"evidence_id": entry["evidence_id"], "citation_id": entry["citation_id"], "citation": entry["citation"]},
    }


def _relative_valuation_weighted_average_share_count(tk: str) -> dict | None:
    """A weighted-average basic share count cited to the audited statement notes,
    for relative_valuation's P/E only -- never substituted with the period-end count
    above, even where their values happen to be equal for a given period."""
    verified = load_verified_share_basis(runtime_root())
    entry = latest_share_basis(verified["by_identity"], tk, "weighted_average_basic_shares_outstanding")
    if entry is None:
        return None
    return {
        "value": entry["value"],
        "semantics": "weighted_average_basic",
        "period_identity": {"period": entry["reporting_period"], "period_type": entry["reporting_frequency"]},
        "source": "share_basis_evidence",
        "evidence": {"evidence_id": entry["evidence_id"], "citation_id": entry["citation_id"], "citation": entry["citation"]},
    }


def _historical_relative_valuation_price(tk: str) -> dict | None:
    """A cited historical closing price for relative_valuation's P/E, P/B, P/S, and
    EV/Sales. Never the live snapshot price used elsewhere in this exporter --
    this milestone evaluates one historical FY2024 valuation date, not a current one.
    Returns None (the whole relative_valuation call correctly fails closed) when no
    verified price citation exists for this ticker."""
    verified = load_verified_market_price(runtime_root())
    candidates = [entry for (ticker, _trading_date), entry in verified["by_ticker_date"].items() if ticker == tk]
    if not candidates:
        return None
    entry = max(candidates, key=lambda e: e["trading_date"])
    return {
        "value": entry["value"],
        "as_of_date": entry["trading_date"],
        "financial_period": entry["financial_period"],
        "source": f"{entry['provider']}:{entry['source_table']}",
        "is_actionable": True,
        "evidence": {"citation_id": entry["citation_id"], "adjustment_status": entry["adjustment_status"]},
    }


def build_ticker_entry(tk, conn, snapshot_rows, ta_rows, score_rows, score_session,
                       financial_rows, financial_canonical, snapshot_info, ta_info, reference_at) -> dict:
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
    corporate = load_corporate_intelligence(conn, tk)
    snapshot_freshness = freshness_envelope(domain="daily_market", as_of_date=(snapshot_rows.get(tk) or {}).get("date"), generated_at=(snapshot_rows.get(tk) or {}).get("date"), source=SNAPSHOT_LIVE_PATH, reference_at=reference_at)
    technical_freshness = freshness_envelope(domain="technical", as_of_date=(ta_rows.get(tk) or {}).get("date"), generated_at=(ta_rows.get(tk) or {}).get("date"), source=TA_SIGNALS_PATH, reference_at=reference_at, dependency=snapshot_freshness)
    financial_freshness = freshness_envelope(domain="financial_quarterly", as_of_date=fin.get("period_used"), generated_at=fin.get("row", {}).get("generated_at") if fin.get("row") else None, source=FINANCIAL_SNAPSHOT_PATH, reference_at=reference_at)
    for name, section in corporate.items():
        if not isinstance(section, dict):
            continue
        coverage = section.get("coverage_status") or section.get("status")
        source_date = section.get("fetched_at") or section.get("snapshot_date") or section.get("as_of_date")
        source_name = section.get("source") or section.get("provider")
        if not source_date and isinstance(section.get("sources"), list):
            provenance_dates = []
            for source_item in section["sources"]:
                if not isinstance(source_item, dict):
                    continue
                source_name = source_name or source_item.get("source_name")
                for record in source_item.get("records", []) if isinstance(source_item.get("records"), list) else []:
                    provenance = record.get("provenance") if isinstance(record, dict) else None
                    if isinstance(provenance, dict) and provenance.get("retrieved_at"):
                        provenance_dates.append(provenance["retrieved_at"])
                source_date = source_date or source_item.get("snapshot_date")
            source_date = max(provenance_dates) if provenance_dates else source_date
        section["freshness"] = freshness_envelope(domain="corporate_events" if name == "corporate_events" else "corporate_snapshot", as_of_date=source_date, generated_at=source_date, source=source_name, reference_at=reference_at, completeness=coverage)
    freshness = {
        "daily_prices": snapshot_freshness, "technical_signals": technical_freshness,
        "ai_report": freshness_envelope(domain="ai_report", as_of_date=score_session.get("session_date"), generated_at=score_session.get("generated_at"), source=ANALYSIS_PATH, reference_at=reference_at, dependency=snapshot_freshness),
        "financial_statements": financial_freshness,
    }
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
        "financial_canonical": financial_canonical.get(tk, {"status": "missing", "records": []}),
        "financial_identity": empty_identity_export(),
        "fundamental_quality": evaluate_fundamental_quality(financial_canonical.get(tk), get_default_registry().entity_type_for(tk)),
        # Existing snapshot P/E/P/B and metadata fields still lack qualified denominator,
        # share-basis, and enterprise-value semantics -- do not pass them as inputs. The
        # observation-store canonical records below are additive and only ever carry
        # quality_state="available" where an exact evidence citation verified them. FCFF
        # still requires externally-sourced WACC/growth/forecast assumptions this exporter
        # does not fabricate. Net-Net's share_count is a cited period-end count (or None,
        # never a weighted-average/live count substituted in its place).
        "intrinsic_valuation": evaluate_intrinsic_valuation({"entity_type": get_default_registry().entity_type_for(tk), "financial": _financial_input(financial_canonical.get(tk)), "share_count": _net_net_share_count(tk), "current_price_actionable": snapshot_freshness.get("is_actionable")}, reference_at=reference_at.isoformat()),
        # No source-owned scenario evidence mapping is qualified yet; do not infer one here.
        "scenario_analysis": evaluate_scenario_analysis({}, reference_at=reference_at.isoformat()),
        "risk_analysis": evaluate_market_risk({"ohlcv": ohlcv, "price_adjustment": "qualified" if build_price_basis_contract().get("price_basis_verified") else "unknown", "volume_units": "qualified" if build_price_basis_contract().get("volume_basis_verified") else "unknown", "volume_basis": build_price_basis_contract().get("volume_basis"), "current_actionable": snapshot_freshness.get("is_actionable")}, reference_at=reference_at.isoformat()),
        # This is a historical FY2024 valuation-date snapshot, never a current one: the
        # price is a cited 2024-12-31 close (see docs/historical_relative_valuation_snapshot.md),
        # not the live snapshot_rows price used elsewhere in this exporter. P/E reads a
        # weighted-average share count; P/B and the market-cap reconstruction P/S/EV-Sales
        # share read a period-end count -- two distinct identities, never aliased even
        # though their values happen to be equal for HPG FY2024. Either input is simply
        # omitted (fails closed) when no citation exists for this ticker.
        "relative_valuation": evaluate_relative_valuation({
            "entity_type": get_default_registry().entity_type_for(tk),
            "current_price": _historical_relative_valuation_price(tk),
            "share_count_weighted_average_basic": _relative_valuation_weighted_average_share_count(tk),
            "share_count_period_end": _relative_valuation_period_end_share_count(tk),
            "financial": _financial_input(financial_canonical.get(tk)),
        }, reference_at=reference_at.isoformat()),
        "ohlcv_recent": ohlcv,
        "ohlcv_recent_count": len(ohlcv),
        "corporate_intelligence": corporate,
        "freshness": freshness,
        "analysis_readiness": evaluate_analysis_readiness(freshness=freshness, corporate_intelligence=corporate, reference_at=reference_at),
        "warnings": warnings,
    }


def build_focus_extract(tickers, conn, snapshot_rows, ta_rows, score_rows, score_session,
                        financial_rows, financial_canonical, snapshot_info, ta_info, reference_at):
    return {tk: build_ticker_entry(tk, conn, snapshot_rows, ta_rows, score_rows, score_session,
                                   financial_rows, financial_canonical, snapshot_info, ta_info, reference_at)
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
            "file": ctx.get("file", context_package_reference(tk)),
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
    parser.add_argument("--evaluation-at", help="Explicit ISO evaluation timestamp for deterministic freshness envelopes")
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
        mismatches = verify_manifest(manifest_path, runtime_root())
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
        financial_canonical = load_financial_canonical(tickers)
        focus_analysis_info = load_focus_analysis_info()
        context_info = load_context_package_info(tickers)
        breadth_records, breadth_info = load_market_breadth()
        macro_records, macro_info = load_macro_snapshot()
        conn = _connect_db_readonly(runtime_path(DB_PATH))
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
        order_violations = check_artifact_order(runtime_root())
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

        reference_at = datetime.fromisoformat(args.evaluation_at.replace("Z", "+00:00")) if args.evaluation_at else datetime.now(timezone.utc)
        if reference_at.tzinfo is None:
            reference_at = reference_at.replace(tzinfo=timezone.utc)
        entries = build_focus_extract(tickers, conn, snapshot_rows, ta_rows, score_rows,
                                      score_session, financial_rows, financial_canonical, snapshot_info, ta_info, reference_at)
        for ticker, entry in entries.items():
            entity_type = get_default_registry().entity_type_for(ticker)
            entry["entity_type"] = entity_type
            opportunity = evaluate_opportunity(entry, ticker=ticker, entity_type=entity_type)
            entry["opportunity_ranking"] = opportunity
            entry["scenario_analysis"] = evaluate_scenario_analysis({
                "freshness": entry.get("freshness"),
                "readiness": (entry.get("analysis_readiness") or {}).get("domains"),
                "corporate_intelligence": entry.get("corporate_intelligence"),
                "corporate_events": (entry.get("corporate_intelligence") or {}).get("corporate_events"),
                "technical": {"above_sma50": (entry.get("ta_signal") or {}).get("above_sma50")},
                "opportunity": opportunity,
            }, reference_at=reference_at.isoformat())
        opportunity_ranking = rank_opportunities(entries)
    finally:
        conn.close()

    generated_at = reference_at.isoformat(timespec="seconds")
    price_basis = build_price_basis_contract()
    breadth_freshness = freshness_envelope(domain="daily_market", as_of_date=breadth_info.get("data_date"), generated_at=breadth_info.get("data_date"), source=MARKET_BREADTH_PATH, reference_at=reference_at)
    macro_freshness = {}
    if isinstance(macro_records, dict):
        for series, record in macro_records.items():
            if not isinstance(record, dict):
                continue
            frequency = str(record.get("expected_frequency") or record.get("freq") or "").lower()
            domain = "macro_weekly" if "week" in frequency or "tu?n" in frequency else "macro_monthly" if "month" in frequency or "th?ng" in frequency else "macro_quarterly" if "quarter" in frequency or "qu?" in frequency else "macro_daily"
            macro_freshness[series] = freshness_envelope(domain=domain, as_of_date=record.get("date"), generated_at=record.get("as_of") or record.get("date"), source=record.get("source") or series, reference_at=reference_at)
    data_quality_flags = build_data_quality_flags(tickers, entries, order_violations, price_basis)

    # ---------------------------------------------------------------- focus_extract.json (nhỏ)
    focus_extract = {
        "schema_version": "1.1.0",
        "generated_at": generated_at,
        "reference_session_date": latest_session,
        "tickers_requested": tickers,
        "freshness": freshness,
        "live_universe": snapshot_info["live_universe"],
        "canonical_sources": {"rs_rating": CANONICAL_RS_RATING_SOURCE},
        "price_basis": price_basis["price_basis"],
        "price_basis_verified": price_basis["price_basis_verified"],
        "is_actionable": price_basis["is_actionable"],
        "volume_basis": price_basis["volume_basis"],
        "volume_basis_verified": price_basis["volume_basis_verified"],
        "price_basis_provenance": price_basis,
        "tickers": entries,
        "opportunity_ranking": opportunity_ranking,
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
    output_dir = output_path(OUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / 'focus_extract.json'
    atomic_write_json(out_path, focus_extract)
    emit_observability_event(build_observability_event(
        EventStage.ARTIFACT_GENERATION,
        EventOutcome.SUCCESS,
        artifact_filename="focus_extract.json",
        sha256=sha256_file(out_path),
        size_bytes=out_path.stat().st_size if out_path.exists() else None,
        price_basis=price_basis["price_basis"],
        volume_basis=price_basis["volume_basis"],
        is_actionable=price_basis["is_actionable"],
        target_path=out_path,
    ), output_dir / "observability_events.jsonl")

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
        "live_universe": snapshot_info["live_universe"],
        "canonical_sources": {"rs_rating": CANONICAL_RS_RATING_SOURCE},
        "price_basis": price_basis["price_basis"],
        "price_basis_verified": price_basis["price_basis_verified"],
        "is_actionable": price_basis["is_actionable"],
        "volume_basis": price_basis["volume_basis"],
        "volume_basis_verified": price_basis["volume_basis_verified"],
        "price_basis_provenance": price_basis,
        "market_breadth": breadth_records,
        "market_breadth_freshness": breadth_freshness,
        "macro_snapshot": macro_records,
        "macro_freshness": macro_freshness,
        "tickers": bundle_entries,
        "opportunity_ranking": opportunity_ranking,
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
    bundle_path = output_dir / 'analysis_bundle.json'
    atomic_write_json(bundle_path, analysis_bundle)
    emit_observability_event(build_observability_event(
        EventStage.ARTIFACT_GENERATION,
        EventOutcome.SUCCESS,
        artifact_filename="analysis_bundle.json",
        sha256=sha256_file(bundle_path),
        size_bytes=bundle_path.stat().st_size if bundle_path.exists() else None,
        price_basis=price_basis["price_basis"],
        volume_basis=price_basis["volume_basis"],
        is_actionable=price_basis["is_actionable"],
        target_path=bundle_path,
    ), output_dir / "observability_events.jsonl")

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
        "live_universe": snapshot_info["live_universe"],
        "price_basis": price_basis["price_basis"],
        "price_basis_verified": price_basis["price_basis_verified"],
        "is_actionable": price_basis["is_actionable"],
        "volume_basis": price_basis["volume_basis"],
        "volume_basis_verified": price_basis["volume_basis_verified"],
        "price_basis_provenance": price_basis,
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

    manifest_path = output_dir / 'bundle_manifest.json'
    atomic_write_json(manifest_path, manifest)
    emit_observability_event(build_observability_event(
        EventStage.MANIFEST_VERIFICATION,
        EventOutcome.SUCCESS,
        artifact_filename="bundle_manifest.json",
        sha256=sha256_file(manifest_path),
        size_bytes=manifest_path.stat().st_size if manifest_path.exists() else None,
        price_basis=price_basis["price_basis"],
        volume_basis=price_basis["volume_basis"],
        is_actionable=price_basis["is_actionable"],
        target_path=manifest_path,
    ), output_dir / "observability_events.jsonl")

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
