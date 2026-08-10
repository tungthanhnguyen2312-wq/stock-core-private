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
from typing import Any, Iterable, Mapping

import pandas as pd
from shareholder_pipeline import DONE, calculate_major_shareholder_delta
from live_universe import summary as live_universe_summary
from freshness_history import evaluate_analysis_readiness, freshness_envelope, parse_timestamp
from financial_canonicalization import canonicalize_financial_rows
from official_evidence import load_cited_financial_records
from financial_identity import empty_identity_export
from corporate_actions_export import build_corporate_actions_section
from financial_observations import canonical_records, read_observations, store_path
from semantic_evidence_bridge import enrich_canonical_records, reconcile_metric_identities, load_verified_share_basis, latest_share_basis, load_verified_market_price, load_verified_ebitda_components, latest_ebitda_component, derive_ebitda, load_verified_citations, load_verified_financial_identities, latest_financial_identity
from altman_z_score import evaluate_altman_z_score
from financial_mapping import get_default_registry
from fundamental_quality import evaluate_fundamental_quality, reconcile_legacy_fundamental_quality_with_qualified_evidence
from relative_valuation import evaluate_relative_valuation
from intrinsic_valuation import evaluate_intrinsic_valuation
from scenario_analysis import evaluate_scenario_analysis
from historical_decision_analysis import evaluate_historical_decision_analysis, PILOT_TICKERS
from qualified_historical_fundamental_analytics import build_comparative_matrix, merge_official_annual_facts
from qualified_cohort_comparison import build as build_qualified_cohort_comparison
from portfolio_risk_analysis import evaluate_portfolio_risk_analysis
from historical_scaleout import attach as attach_historical_scaleout
from qualified_research_brief import build as build_qualified_research_brief
from qualified_research_delta import attach as attach_qualified_research_delta
from qualified_research_snapshot import snapshot_as_bundle
from qualified_research_snapshot_v2 import build as build_research_snapshot_v2
from qualified_research_change_events import build_v2 as build_research_change_events_v2
from opportunity_ranking import evaluate_opportunity, rank_opportunities
from risk_liquidity import evaluate_market_risk
from qualified_market_observations import evaluate as evaluate_qualified_market_observations
from analysis_lane_eligibility import evaluate_ticker_lanes
from ticker_capability import build_ticker_capability_matrix
from market_basis_capability_registry import MARKET_DATA_SOURCE_AUTHORITY_SELECTION
from research_financial_fact_projection import (
    build_projection as build_research_financial_fact_projection,
    coverage_summary as research_financial_coverage_summary,
    select_research_source,
)
from canonical_financial_qualification_policy import load_evidence_index
from canonical_conflict_decomposition import coverage_summary as canonical_conflict_coverage_summary
from distribution_evidence import build_distribution_evidence_for_ticker
from dnse_foreign_flow_store import build_series as build_dnse_foreign_flow_series
from dnse_current_state_market_risk import build_current_state_market_risk_from_evidence_store
from fundamental_quality_evidence import (
    build_fundamental_quality_evidence_for_ticker,
    build_historical_fundamental_brief,
    build_historical_capital_structure_analysis,
)
from statement_taxonomy_sidecar import (
    SIDECAR_FILENAME as TAXONOMY_SIDECAR_FILENAME,
    load_sidecar as load_taxonomy_sidecar,
    resolve_entity_authority,
    resolve_taxonomy,
    sidecar_path as taxonomy_sidecar_path,
    sidecar_provenance,
)

# Console Windows mặc định cp1252 -> vỡ khi in tiếng Việt (cùng vá như candle_scan.py dòng 14).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent


def ai_runtime_root() -> Path:
    """Locate the AI runtime in the new layout, with legacy-layout fallbacks.

    `ai-core-private` is checked FIRST because it is where the Consumer's
    `builders/build_ticker_context.py` actually writes context packages today.
    `ai-runtime/exports/context_packages` still exists in this workspace but is an
    out-of-band copy that stopped being refreshed, so preferring it silently fed the
    bundle context packages several sessions older than the ones just built -- which the
    export's own session-scoped freshness gate then correctly refused. The directory is
    only preferred when it really holds context packages, so a workspace that still uses
    the legacy layout is unaffected.
    """
    consumer = SCRIPT_DIR.parent / "ai-core-private"
    if (consumer / "exports" / "context_packages").is_dir():
        return consumer.resolve()
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


def resolve_output_dir(explicit: str | None = None) -> Path:
    """Keep the legacy runtime destination unless an explicit shadow destination is supplied."""
    return output_path(explicit if explicit is not None else OUT_DIR)


def context_package_reference(ticker: str) -> str:
    """Return a manifest path relative to the active dashboard runtime root."""
    path = context_packages_dir() / f"{ticker}_context.json"
    try:
        return Path(os.path.relpath(path, start=runtime_root().resolve())).as_posix()
    except ValueError:
        return path.as_posix()

# Canonical production cohort for the P1.5 capability-matrix attachment.  VCB remains
# test-only here; it is intentionally not reintroduced into the live export universe.
DEFAULT_TICKERS = ["POW", "SSI", "HPG", "EVF", "PAN", "PNJ", "FPT", "QNS", "VNM", "PVD", "NVL"]
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


# Exact-session bundle contract. Bumped whenever the manifest/proof shape or any
# verification rule changes: the Consumer pins this exact value, so a bundle emitted by an
# older Producer can never be presented as current trusted output.
PRODUCER_BUNDLE_CONTRACT_VERSION = "stocklookup-producer/2026.08.03"
TRUSTED_SUBSET_SCHEMA_VERSION = "1.1.0"
# The complete namespace of filenames that carry export-session trust. A Consumer scans
# exactly these names next to the bundle; anything present here but not declared in the
# manifest is an unexpected trusted artifact and fails closed.
TRUSTED_ARTIFACT_NAMESPACE = (
    "analysis_bundle.json", "bundle_manifest.json", "focus_extract.json",
    TAXONOMY_SIDECAR_FILENAME,
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_trusted_subset_proof(tickers: list[str], session_identity: str | None,
                               generated_at: str, bundle_sha256: str,
                               entries: Mapping[str, Any], basis: Mapping[str, Any],
                               session_artifacts: Mapping[str, str] | None = None) -> dict | None:
    """Return the additive exact-session proof for this export.

    Schema 1.1.0 covers EVERY exported ticker, not only the historical HPG/VNM subset: a
    bundle with no proof at all is a bundle the Consumer cannot verify, so restricting the
    proof to two tickers left every production export unverifiable. `tickers` is the set
    the proof actually covers (one current-session snapshot each); everything else is
    listed under `unproven_tickers` with a reason and is never exact-session trusted.

    Schema 1.1.0 also adds everything a Consumer needs to prove that a manifest describes
    THIS export session and no other, rather than merely being structurally well-formed:

      producer_contract_version    -- the Producer contract that emitted the proof.
      bundle_reference_session_date / bundle_generated_at
                                   -- copied from the bundle body, so a manifest paired
                                      with a different bundle body is detectable even when
                                      that body hashes correctly against its own manifest.
      required_artifacts           -- filename + sha256 for every artifact written in this
                                      session (bundle_manifest.json excluded: it cannot
                                      hash itself).
      expected_artifact_filenames  -- the exact trusted-artifact set for this session. A
                                      Consumer rejects a trusted artifact present on disk
                                      but absent here.

    `session_artifacts` maps filename -> sha256 for the session outputs other than
    bundle_manifest.json; analysis_bundle.json is always included from `bundle_sha256`.
    """
    if not tickers:
        return None
    if not session_identity:
        raise ValueError("trusted_subset_missing_session")
    per_ticker: dict[str, dict[str, Any]] = {}
    unproven: list[dict[str, Any]] = []
    for ticker in sorted(tickers):
        entry = entries.get(ticker)
        snapshot = (entry or {}).get("snapshot") if isinstance(entry, Mapping) else None
        session = snapshot.get("date") if isinstance(snapshot, Mapping) else None
        if session != session_identity:
            # Not a hard export failure: a symbol with no current-session snapshot (an
            # index row, a halted or delisted ticker) must not abort the whole bundle. It
            # is excluded from the proven set instead, with an explicit reason, and the
            # Consumer refuses to treat it as exact-session trusted.
            unproven.append({
                "ticker": ticker,
                "observed_session_identity": session,
                "reason": ("snapshot_missing" if snapshot is None
                           else "snapshot_session_differs_from_reference_session"),
            })
            continue
        per_ticker[ticker] = {
            "session_identity": session,
            "required_current_fields_qualified": bool(snapshot),
            "warnings": list((entry or {}).get("warnings") or []),
        }
    if not per_ticker:
        return None
    artifacts = dict(session_artifacts or {})
    artifacts["analysis_bundle.json"] = bundle_sha256
    required_artifacts = [{"file": name, "sha256": artifacts[name]} for name in sorted(artifacts)]
    expected_filenames = sorted(set(artifacts) | {"bundle_manifest.json"})
    return {
        "schema_version": TRUSTED_SUBSET_SCHEMA_VERSION,
        "producer_contract_version": PRODUCER_BUNDLE_CONTRACT_VERSION,
        "tickers": sorted(per_ticker),
        "unproven_tickers": unproven,
        "bundle_ticker_set": sorted(tickers),
        "trust_state": "exact_session_qualified" if basis.get("price_basis_verified") is True and basis.get("volume_basis_verified") is True else "untrusted_basis",
        "session_identity": session_identity, "generated_at": generated_at,
        "bundle_filename": "analysis_bundle.json", "bundle_sha256": bundle_sha256,
        "bundle_reference_session_date": session_identity,
        "bundle_generated_at": generated_at,
        "required_artifacts": required_artifacts,
        "expected_artifact_filenames": expected_filenames,
        "per_ticker": per_ticker,
        "price_basis": {"state": basis.get("price_basis", "unknown"), "verified": basis.get("price_basis_verified") is True},
        "volume_basis": {"state": basis.get("volume_basis", "unknown"), "verified": basis.get("volume_basis_verified") is True},
    }


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
        metadata.get("volume_basis", VolumeBasis.UNKNOWN.value),
        verified=metadata.get("volume_basis_verified") is True,
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


def retained_source_timestamp(row: dict | None) -> object | None:
    """Return only an explicit retained source timestamp; a session date is not one."""
    if not isinstance(row, dict):
        return None
    for key in ("source_generated_at", "generated_at", "retrieved_at"):
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def common_retained_source_timestamp(rows: list[dict]) -> object | None:
    values = {retained_source_timestamp(row) for row in rows}
    values.discard(None)
    return next(iter(values)) if len(values) == 1 else None

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


def build_analysis_score_contract(values: dict | None, session_info: dict) -> dict:
    """Xây dựng hợp đồng an toàn ngữ nghĩa cho analysis_score."""
    if not isinstance(values, dict):
        return {
            "session_date": session_info.get("session_date"),
            "regime": session_info.get("regime"),
            "values": None,
            "risk_semantics": None,
        }

    risk_val = values.get("risk")
    risk_semantics = None
    if risk_val is not None:
        risk_semantics = {
            "legacy_field": "risk",
            "legacy_field_ambiguity": "The field name 'risk' is legacy nomenclature and must not be interpreted as higher-means-more-risk.",
            "polarity": "higher_is_safer",
            "score_value": risk_val,
            "interpretation": "100 means no configured penalty flags were triggered (maximum configured safety score). 0 means all penalty flags were triggered.",
            "limitations": [
                "100 means no configured penalty flags were triggered; it is not a calibrated probability of loss.",
                "It is not an investment-attractiveness score.",
            ],
            "is_actionable": False,
        }

    return {
        "session_date": session_info.get("session_date"),
        "regime": session_info.get("regime"),
        "values": values,
        "risk_semantics": risk_semantics,
    }


def build_opportunity_ranking_contract(ranking: dict | None) -> dict | None:
    """Xây dựng hợp đồng an toàn ngữ nghĩa cho opportunity_ranking."""
    if not isinstance(ranking, dict) or not ranking:
        return None

    out = dict(ranking)
    out["ordering_basis"] = "evidence_availability"
    out["ranking_type"] = "evidence_availability_ordering_only"
    out.setdefault("ranking_kind", "evidence_availability_ordering_only")
    out["is_investment_ranking"] = False
    out["is_actionable"] = False

    existing_limits = list(ranking.get("interpretation_limits") or [])
    required_limits = [
        "Dimensions are evidence availability states, not an investment-attractiveness score, expected return, conviction, or portfolio priority.",
        "No composite magic score, recommendation, probability, target price, or portfolio sizing.",
    ]
    for limit in required_limits:
        if limit not in existing_limits:
            existing_limits.append(limit)
    out["interpretation_limits"] = existing_limits
    out["limitations"] = existing_limits
    return out


def build_ta_signal_semantics(ta_row: dict | None) -> dict:
    """Xây dựng hợp đồng an toàn ngữ nghĩa cho ta_signal."""
    if isinstance(ta_row, dict):
        return {
            "coverage_status": "available",
            "evaluation_status": "record_available",
            "reason": None,
            "presence_interpretation": "Presence of a TA signal record indicates signal availability, not an investment action or complete technical conclusion.",
            "null_interpretation": None,
            "is_no_signal_claim": False,
            "is_actionable": False,
        }
    return {
        "coverage_status": "missing",
        "evaluation_status": "unqualified",
        "reason": "absent_from_ta_signals_csv",
        "presence_interpretation": None,
        "null_interpretation": "null indicates absence from TA signals scan output, not a confirmed no-signal claim or neutral conclusion.",
        "is_no_signal_claim": False,
        "is_actionable": False,
    }


def build_news_window_semantics(news_data: dict | None) -> dict | None:
    """Xây dựng hợp đồng an toàn ngữ nghĩa cho news_related / cutoff window."""
    if not isinstance(news_data, dict):
        return None

    cutoff_val = news_data.get("cutoff")

    semantics = {
        "cutoff_semantics": "lookback_window_start",
        "cutoff_timestamp": cutoff_val,
        "cutoff_interpretation": "cutoff represents the start of the lookback window, not the latest news update or article publication time.",
        "mapping_coverage_status": "unqualified",
        "is_no_relevant_news_claim": False,
        "is_actionable": False,
        "interpretation_limits": [
            "cutoff is the start of the lookback window, not the latest news update or retrieval time.",
            "zero mapped articles does not prove that no relevant company news exists.",
            "ticker alias linkage coverage is unqualified and not guaranteed to be complete.",
        ],
    }

    if "retrieved_at" in news_data:
        semantics["retrieved_at"] = news_data["retrieved_at"]
    if "fetched_at" in news_data:
        semantics["fetched_at"] = news_data["fetched_at"]
    if "latest_published_utc" in news_data:
        semantics["latest_published_utc"] = news_data["latest_published_utc"]

    return semantics


# ==========================================================================
# Phase 5C — generic verified financial-period resolver
# ==========================================================================
# Generalizes the Phase 5B (commit e8a351c) HPG/FY2024-hardcoded resolver into a fully
# data-driven one. Links the already fully fail-closed load_verified_citations()/
# read_observations() resolvers (existing, extensively tested in
# semantic_evidence_bridge.py / financial_observations.py, and already used elsewhere
# for per-metric EBITDA/valuation qualification) to financial_period_coverage at the
# (ticker, reporting_period, reporting_frequency) level. Contains no ticker, period,
# frequency, or scope literal anywhere in its logic -- every candidate is derived
# entirely from what load_verified_citations()/read_observations() already return.
# The existing `official_evidence.status == "verified"` check path remains unreachable
# today (financial_canonicalization.py never sets that key, and the separate
# official_evidence.py pilot module only ever returns status values of
# missing/malformed/unavailable/available, never "verified") -- unaffected by this change.

def resolve_verified_financial_periods(runtime_root_dir: Path) -> dict[str, dict[str, Any]]:
    """Return, for every ticker with at least one fully evidence-verified reporting
    period, a descriptor for its single latest such period: {ticker: {"ticker",
    "period", "period_type", "statement_scope", "observation_ids"}}.

    A (ticker, reporting_period, reporting_frequency) candidate qualifies only when:
    every verified citation covering it (via load_verified_citations(), which already
    hash-verifies the source document against the manifest, cross-checks the exact
    observation_id against the current retained observation store, and reconciles the
    observation's raw value against the citation's official value) agrees on a single,
    supported statement_scope ("consolidated") -- a period with zero verified
    citations, with citations naming conflicting scopes, or citing a document that
    itself carries no citations (e.g. one retained only for scope disambiguation) never
    qualifies, since it is structurally absent from load_verified_citations()'s output
    or excluded by the scope-agreement check below. Nothing here infers a period from
    a filename, infers scope from value similarity, infers annual frequency from a
    date's shape, infers completeness from citation count, or picks a "latest" period
    by calendar order among unverified candidates -- "latest" here only ever compares
    periods that already independently qualified.

    Deterministic and read-only: makes no network call, writes nothing, and returns the
    same result for the same retained inputs."""
    verified = load_verified_citations(runtime_root_dir)
    by_observation_id = verified.get("by_observation_id") or {}
    if not by_observation_id:
        return {}
    observations_by_id = {row["observation_id"]: row for row in read_observations(store_path(runtime_root_dir))}

    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for obs_id, citation in by_observation_id.items():
        observation = observations_by_id.get(obs_id)
        if observation is None:
            continue
        ticker = observation.get("ticker")
        period = observation.get("reporting_period")
        frequency = observation.get("reporting_frequency")
        scope = citation.get("statement_scope")
        if not ticker or not period or not frequency or not scope:
            continue
        key = (ticker, period, frequency)
        bucket = groups.setdefault(key, {"scopes": set(), "observation_ids": [], "temporal_sources": {}})
        bucket["scopes"].add(scope)
        bucket["observation_ids"].append(obs_id)
        evidence_id = citation.get("evidence_id")
        if evidence_id:
            bucket["temporal_sources"][evidence_id] = {
                "publication_date": citation.get("publication_date"),
                "retrieved_at": citation.get("retrieved_at"),
                "document_sha256": citation.get("document_sha256"),
                "source_url": citation.get("source_url"),
            }

    qualified: dict[tuple[str, str, str], dict[str, Any]] = {}
    for (ticker, period, frequency), bucket in groups.items():
        if len(bucket["scopes"]) != 1:
            continue  # conflicting scope asserted for the same period -- fail closed, no inference
        scope = next(iter(bucket["scopes"]))
        if scope not in _SUPPORTED_STATEMENT_SCOPES:
            continue
        period_type = _FREQUENCY_TO_PERIOD_TYPE.get(frequency)
        if period_type is None:
            continue
        descriptor = {
            "ticker": ticker,
            "period": period,
            "period_type": period_type,
            "statement_scope": scope,
            "observation_ids": sorted(bucket["observation_ids"]),
        }
        temporal_sources = bucket["temporal_sources"]
        if temporal_sources:
            publication_dates = {item.get("publication_date") for item in temporal_sources.values() if parse_timestamp(item.get("publication_date"))}
            retrieval_dates = {item.get("retrieved_at") for item in temporal_sources.values() if parse_timestamp(item.get("retrieved_at"))}
            publication_qualified = len(publication_dates) == 1 and len(publication_dates) == len(temporal_sources)
            descriptor["financial_temporal"] = {
                "period_end": f"{period}-12-31" if period_type == "annual" and str(period).isdigit() and len(str(period)) == 4 else None,
                "publication_date": next(iter(publication_dates)) if publication_qualified else None,
                "retrieved_at": next(iter(retrieval_dates)) if len(retrieval_dates) == 1 else None,
                "publication_timestamp_qualified": publication_qualified,
                "citation_ids": sorted(citation.get("citation_id") for obs_id, citation in by_observation_id.items() if obs_id in bucket["observation_ids"] and citation.get("citation_id")),
                "evidence_ids": sorted(temporal_sources),
                "document_sha256": sorted({item.get("document_sha256") for item in temporal_sources.values() if item.get("document_sha256")}),
                "source_urls": sorted({item.get("source_url") for item in temporal_sources.values() if item.get("source_url")}),
                "warnings": [] if publication_qualified else ["financial_publication_timestamp_missing_or_conflicting"],
            }
        qualified[(ticker, period, frequency)] = descriptor

    by_ticker: dict[str, dict[str, Any]] = {}
    for (ticker, period, _frequency), descriptor in qualified.items():
        current = by_ticker.get(ticker)
        if current is None or _period_key(period) > _period_key(current["period"]):
            by_ticker[ticker] = descriptor
    return by_ticker


# Mirrors load_verified_citations()'s own _SUPPORTED_SCOPES ({"consolidated"}) -- kept
# as a separate constant here rather than imported, since it is a property of what this
# resolver accepts as unambiguous, not a re-export of semantic_evidence_bridge's
# internal name. Frequency values are exactly what financial_observations.py's
# observations_from_frame() already writes onto every observation ("annual"/"quarterly").
_SUPPORTED_STATEMENT_SCOPES = {"consolidated"}
_FREQUENCY_TO_PERIOD_TYPE = {"annual": "annual", "quarterly": "quarterly"}


def build_financial_freshness(
    fin_entry: Mapping[str, Any] | None,
    verified_evidence_period: Mapping[str, Any] | None,
    reference_at: datetime,
) -> dict[str, Any]:
    """Use only hash-verified retained-document temporal metadata for FY freshness."""
    temporal = verified_evidence_period.get("financial_temporal") if isinstance(verified_evidence_period, Mapping) else None
    if isinstance(temporal, Mapping):
        envelope = freshness_envelope(
            domain="financial_quarterly",
            as_of_date=temporal.get("publication_date"),
            generated_at=temporal.get("retrieved_at"),
            source=(temporal.get("source_urls") or [None])[0],
            reference_at=reference_at,
        )
        envelope.update({
            "financial_period": verified_evidence_period.get("period"),
            "financial_period_end": temporal.get("period_end"),
            "source_publication_timestamp": temporal.get("publication_date"),
            "source_retrieval_timestamp": temporal.get("retrieved_at"),
            "publication_timestamp_qualified": temporal.get("publication_timestamp_qualified") is True,
            "provenance": {
                "citation_ids": temporal.get("citation_ids", []),
                "evidence_ids": temporal.get("evidence_ids", []),
                "document_sha256": temporal.get("document_sha256", []),
                "source_urls": temporal.get("source_urls", []),
            },
            "warnings": list(temporal.get("warnings") or []),
        })
        return envelope
    return freshness_envelope(
        domain="financial_quarterly",
        as_of_date=(fin_entry or {}).get("period_used"),
        generated_at=((fin_entry or {}).get("row") or {}).get("generated_at"),
        source=FINANCIAL_SNAPSHOT_PATH,
        reference_at=reference_at,
    )

# Phase 5C rollout scope only -- not a qualification rule. Every ticker present in
# resolve_verified_financial_periods()'s return value has already, identically, passed
# the same generic evidence checks; this milestone deliberately surfaces at most one
# additional ticker beyond HPG (Phase 5B) rather than every ticker the data happens to
# support today. VNM is included (signed issuer document with official source
# corroboration, evidence_acceptance rule "signed_issuer_document_with_official_source_
# corroboration_v1"). VCB is excluded from this milestone's rollout even though its
# FY2024 consolidated evidence also independently passes every check in the resolver
# above -- its only recorded citations trace to the third-party-mirrored, unsigned
# document (evidence_acceptance rule "third_party_mirrored_unsigned_audited_issuer_
# document_v1"), which the retained manifest record itself flags:
# "third_party_mirror_hosting_is_weaker_than_issuer_hosted_evidence". Expanding rollout
# to VCB (or any other ticker the resolver already supports) is a future milestone's
# decision, not a resolver limitation.
_PHASE_5C_ENABLED_TICKERS = frozenset({"HPG", "VNM"})
_LEGACY_QUALIFIED_RESEARCH_TICKERS = frozenset({"HPG", "VNM", "PAN", "PVD", "NVL"})


def _financial_period_coverage_verified_override(
    tk: str, verified_evidence_period: Mapping[str, Any] | None,
) -> tuple[bool, str | None]:
    """Defense in depth: re-validate verified_evidence_period against this exact ticker
    even though the resolver above is already hardcoded to one scope -- a future wiring
    change must not silently apply HPG's verified period to a different ticker."""
    if (
        isinstance(verified_evidence_period, Mapping)
        and verified_evidence_period.get("ticker") == tk
        and verified_evidence_period.get("statement_scope") == "consolidated"
        and verified_evidence_period.get("observation_ids")
    ):
        return True, verified_evidence_period.get("period")
    return False, None


def build_financial_period_coverage_contract(
    tk: str,
    fin_entry: dict | None,
    canonical_entry: dict | None = None,
    verified_evidence_period: Mapping[str, Any] | None = None,
) -> dict:
    """Xây dựng hợp đồng an toàn ngữ nghĩa cho per-ticker financial period coverage."""
    evidence_verified, evidence_verified_period = _financial_period_coverage_verified_override(tk, verified_evidence_period)

    if not isinstance(fin_entry, dict) or not fin_entry.get("row"):
        return {
            "ticker": tk,
            "latest_raw_period": None,
            "latest_calendar_eligible_period": None,
            "latest_verified_period": evidence_verified_period if evidence_verified else None,
            "latest_complete_period": None,
            "period_type": "unknown",
            "statement_coverage": "missing",
            "canonical_coverage": "missing" if not canonical_entry else canonical_entry.get("status", "missing"),
            "coverage_status": "verified_only" if evidence_verified else "unavailable",
            "limitations": [
                "No financial snapshot records exist for this ticker.",
                "Global maximum financial dates must never populate missing ticker coverage.",
            ],
            "is_actionable": False,
        }

    row = fin_entry.get("row") or {}
    period_used = fin_entry.get("period_used")
    excluded = fin_entry.get("excluded_unverified_periods") or []
    is_incomparable = fin_entry.get("warning") == "conflicting_period_identities"

    if excluded:
        all_periods = sorted([period_used] + excluded, key=_period_key) if period_used else sorted(excluded, key=_period_key)
        latest_raw_period = all_periods[-1]
    else:
        latest_raw_period = period_used

    latest_calendar_eligible_period = period_used

    source_verified = False
    verified_period_value = None
    if isinstance(row, dict) and row.get("source_verified") is True:
        source_verified = True
        verified_period_value = period_used
    elif isinstance(canonical_entry, dict) and (canonical_entry.get("official_evidence") or {}).get("status") == "verified":
        source_verified = True
        verified_period_value = period_used
    elif evidence_verified:
        source_verified = True
        verified_period_value = evidence_verified_period

    latest_verified_period = verified_period_value if source_verified else None

    ref_period = latest_calendar_eligible_period or latest_raw_period
    if ref_period and "-Q" in str(ref_period):
        period_type = "quarterly"
    elif ref_period and len(str(ref_period)) == 4 and str(ref_period).isdigit():
        period_type = "annual"
    elif ref_period and "TTM" in str(ref_period).upper():
        period_type = "ttm"
    else:
        period_type = "unknown"

    has_rev = row.get("revenue") is not None and not pd.isna(row.get("revenue")) if "revenue" in row else False
    has_np = row.get("net_profit") is not None and not pd.isna(row.get("net_profit")) if "net_profit" in row else False
    statement_coverage = "partial" if (has_rev or has_np) else "missing"

    canonical_status = "missing"
    if isinstance(canonical_entry, dict):
        canonical_status = canonical_entry.get("status") or ("available" if canonical_entry.get("records") else "missing")

    latest_complete_period = None

    if is_incomparable:
        coverage_status = "incomparable"
    elif latest_verified_period:
        coverage_status = "verified_only"
    elif latest_calendar_eligible_period:
        coverage_status = "calendar_eligible_only"
    elif latest_raw_period:
        coverage_status = "raw_only"
    else:
        coverage_status = "unavailable"

    limitations = [
        "Raw period presence does not imply calendar eligibility.",
        "calendar eligibility is not source verification",
        "verified period identity does not imply full 3-statement audit completeness",
        "completeness criteria are unqualified in current repository store; latest_complete_period remains null",
        "global maximum financial dates must never populate missing or lower-period ticker coverage",
    ]

    return {
        "ticker": tk,
        "latest_raw_period": latest_raw_period,
        "latest_calendar_eligible_period": latest_calendar_eligible_period,
        "latest_verified_period": latest_verified_period,
        "latest_complete_period": latest_complete_period,
        "period_type": period_type,
        "statement_coverage": statement_coverage,
        "canonical_coverage": canonical_status,
        "coverage_status": coverage_status,
        "limitations": limitations,
        "is_actionable": False,
    }


def build_valuation_namespaces_contract(
    tk: str,
    snapshot_row: dict | None,
    relative_val: dict | None,
    financial_coverage: dict | None = None,
) -> dict:
    """Xây dựng hợp đồng an toàn ngữ nghĩa cho valuation_namespaces và comparability."""
    live_pe_val = snapshot_row.get("pe") if isinstance(snapshot_row, dict) else None
    live_pb_val = snapshot_row.get("pb") if isinstance(snapshot_row, dict) else None
    obs_date = snapshot_row.get("date") if isinstance(snapshot_row, dict) else None
    provider_name = (snapshot_row.get("source") if isinstance(snapshot_row, dict) else None) or "unknown_vendor"

    live_pe_obj = {
        "value": live_pe_val,
        "price_date": obs_date,
        "denominator_measure": "vendor_unspecified",
        "financial_period": "vendor_unspecified",
        "share_basis": "vendor_unspecified",
        "method": "vendor_snapshot",
        "provider": provider_name,
        "provenance": "live_market_snapshot",
        "limitations": [
            "Live vendor P/E denominator, earnings period, share basis, and calculation method are unqualified in retained snapshot evidence.",
        ],
    }

    live_pb_obj = {
        "value": live_pb_val,
        "price_date": obs_date,
        "denominator_measure": "vendor_unspecified",
        "financial_period": "vendor_unspecified",
        "share_basis": "vendor_unspecified",
        "method": "vendor_snapshot",
        "provider": provider_name,
        "provenance": "live_market_snapshot",
        "limitations": [
            "Live vendor P/B denominator, equity period, share basis, and calculation method are unqualified in retained snapshot evidence.",
        ],
    }

    live_vendor = {
        "metrics": {
            "pe": live_pe_obj,
            "pb": live_pb_obj,
        },
        "observed_at": obs_date,
        "provider": provider_name,
    }

    hist_pe_val = None
    hist_pb_val = None
    price_date = None
    fin_period = None
    share_basis_pe = None
    share_basis_pb = None
    if isinstance(relative_val, dict):
        methods = relative_val.get("methods")
        if isinstance(methods, dict):
            pe_m = methods.get("pe") if isinstance(methods.get("pe"), dict) else {}
            if pe_m.get("state") == "available":
                hist_pe_val = pe_m.get("observed_multiple")
                price_date = pe_m.get("price_as_of_date")
                fin_p = pe_m.get("financial_period")
                if isinstance(fin_p, dict):
                    fin_period = fin_p.get("period")
                prov = pe_m.get("provenance") if isinstance(pe_m.get("provenance"), dict) else {}
                sh_wa = prov.get("share_count_weighted_average_basic") if isinstance(prov.get("share_count_weighted_average_basic"), dict) else {}
                share_basis_pe = sh_wa.get("semantics")

            pb_m = methods.get("pb") if isinstance(methods.get("pb"), dict) else {}
            if pb_m.get("state") == "available":
                hist_pb_val = pb_m.get("observed_multiple")
                price_date = price_date or pb_m.get("price_as_of_date")
                fin_p = pb_m.get("financial_period")
                if isinstance(fin_p, dict):
                    fin_period = fin_period or fin_p.get("period")
                prov = pb_m.get("provenance") if isinstance(pb_m.get("provenance"), dict) else {}
                sh_pe = prov.get("share_count_period_end") if isinstance(prov.get("share_count_period_end"), dict) else {}
                share_basis_pb = sh_pe.get("semantics")

        inputs = relative_val.get("inputs") or {}
        if isinstance(inputs, dict):
            curr_price = inputs.get("current_price") or {}
            price_date = price_date or (curr_price.get("evidence") or {}).get("trading_date") or curr_price.get("as_of_date")
            sh_wa = inputs.get("share_count_weighted_average_basic") or {}
            share_basis_pe = share_basis_pe or sh_wa.get("semantics")
            sh_pe = inputs.get("share_count_period_end") or {}
            share_basis_pb = share_basis_pb or sh_pe.get("semantics")
            fin_inp = inputs.get("financial") or {}
            fin_period = fin_period or (fin_inp.get("period_identity") or {}).get("period")

    hist_pe_obj = {
        "value": hist_pe_val,
        "price_date": price_date,
        "denominator_measure": "audited_net_profit",
        "financial_period": fin_period or "FY2024",
        "share_basis": share_basis_pe or "weighted_average_basic",
        "method": "point_in_time_historical_valuation",
        "provider": "observation_store_audited",
        "provenance": "audited_financial_note_citation",
        "limitations": [
            "Valuation date uses historical FY2024 closing price (e.g. 2024-12-31), not live market price.",
            "P/E uses audited weighted-average basic share count.",
        ],
    }

    hist_pb_obj = {
        "value": hist_pb_val,
        "price_date": price_date,
        "denominator_measure": "audited_total_equity",
        "financial_period": fin_period or "FY2024",
        "share_basis": share_basis_pb or "period_end",
        "method": "point_in_time_historical_valuation",
        "provider": "observation_store_audited",
        "provenance": "audited_financial_note_citation",
        "limitations": [
            "Valuation date uses historical FY2024 closing price (e.g. 2024-12-31), not live market price.",
            "P/B uses audited period-end share count.",
        ],
    }

    historical_calculated = {
        "metrics": {
            "pe": hist_pe_obj,
            "pb": hist_pb_obj,
        },
        "calculation_date": price_date,
    }

    def _evaluate_metric_comparability(live_obj: dict, hist_obj: dict, metric_name: str) -> dict:
        v_live = live_obj.get("value")
        v_hist = hist_obj.get("value")

        if v_live is None and v_hist is None:
            return {
                "status": "not_available",
                "reasons": [f"No {metric_name.upper()} metric value is available in either live_vendor or historical_calculated."],
                "is_actionable": False,
            }
        if v_live is None or v_hist is None:
            return {
                "status": "insufficient_identity",
                "reasons": [f"{metric_name.upper()} value missing from one valuation namespace."],
                "is_actionable": False,
            }

        reasons = []
        p_date_live = live_obj.get("price_date")
        p_date_hist = hist_obj.get("price_date")
        if p_date_live != p_date_hist:
            reasons.append(f"Price date mismatch ({p_date_live} vs {p_date_hist}).")

        sh_live = live_obj.get("share_basis")
        sh_hist = hist_obj.get("share_basis")
        if sh_live != sh_hist:
            reasons.append(f"Share basis mismatch ({sh_live} vs {sh_hist}).")

        den_live = live_obj.get("denominator_measure")
        den_hist = hist_obj.get("denominator_measure")
        if den_live != den_hist:
            reasons.append(f"Denominator measure mismatch ({den_live} vs {den_hist}).")

        m_live = live_obj.get("method")
        m_hist = hist_obj.get("method")
        if m_live != m_hist:
            reasons.append(f"Calculation method mismatch ({m_live} vs {m_hist}).")

        if len(reasons) > 0:
            return {
                "status": "incomparable",
                "reasons": reasons,
                "is_actionable": False,
            }

        return {
            "status": "comparable",
            "reasons": [],
            "is_actionable": False,
        }

    comparability = {
        "metrics": {
            "pe": _evaluate_metric_comparability(live_pe_obj, hist_pe_obj, "pe"),
            "pb": _evaluate_metric_comparability(live_pb_obj, hist_pb_obj, "pb"),
        },
        "disclaimer": "Valuation metrics from live_vendor and historical_calculated namespaces must not be compared as direct metric changes unless temporal, financial, and share-basis alignment is proven.",
        "is_actionable": False,
    }

    return {
        "ticker": tk,
        "live_vendor": live_vendor,
        "historical_calculated": historical_calculated,
        "comparability": comparability,
    }


def build_share_basis_identities_contract(
    tk: str,
    snapshot_row: dict | None,
    runtime_root_dir: Path | None = None,
) -> dict:
    """Xây dựng hợp đồng an toàn ngữ nghĩa cho dated share-basis identities và comparability."""
    if runtime_root_dir is None:
        runtime_root_dir = runtime_root()

    curr_val = None
    curr_obs_at = None
    curr_source = None
    if isinstance(snapshot_row, dict):
        curr_val = snapshot_row.get("shares_outstanding")
        curr_obs_at = snapshot_row.get("date")
        curr_source = snapshot_row.get("source") or "live_market_snapshot"

    current_market = {
        "value": curr_val,
        "effective_date": curr_obs_at,
        "observed_at": curr_obs_at,
        "basis_type": "current_market_shares_outstanding",
        "source": curr_source,
        "provenance": "live_market_snapshot",
        "qualification_status": "unverified" if curr_val is not None else "missing",
        "limitations": [
            "Current market shares outstanding are live/vendor provided without primary-source audit citation.",
            "Market capitalization confirmation for current price does not validate historical or period-end share bases.",
        ],
    }

    pe_entry = None
    wa_entry = None
    try:
        verified = load_verified_share_basis(runtime_root_dir)
        pe_entry = latest_share_basis(verified["by_identity"], tk, "period_end_shares_outstanding")
        wa_entry = latest_share_basis(verified["by_identity"], tk, "weighted_average_basic_shares_outstanding")
    except Exception:
        pass

    if pe_entry:
        pe_val = pe_entry.get("value")
        pe_period = pe_entry.get("reporting_period")
        pe_source = "share_basis_evidence"
        pe_status = "verified"
    else:
        pe_val = None
        pe_period = None
        pe_source = None
        pe_status = "missing"

    def _share_provenance(entry: Mapping[str, Any] | None) -> dict | None:
        if not entry:
            return None
        return {
            "evidence_id": entry.get("evidence_id"),
            "citation_id": entry.get("citation_id"),
            "citation": entry.get("citation"),
            "document_sha256": entry.get("document_sha256"),
            "source_url": entry.get("source_url"),
            "publication_date": entry.get("publication_date"),
            "retrieved_at": entry.get("retrieved_at"),
        }

    financial_period_end = {
        "value": pe_val,
        "financial_period": pe_period,
        "effective_date": f"{pe_period}-12-31" if pe_entry and pe_entry.get("reporting_frequency") == "annual" else None,
        "basis_type": "period_end_shares_outstanding",
        "unit": pe_entry.get("unit") if pe_entry else None,
        "share_class": pe_entry.get("share_class") if pe_entry else None,
        "source": pe_source,
        "provenance": _share_provenance(pe_entry),
        "qualification_status": pe_status,
        "limitations": [
            "Period-end shares outstanding reflect exact balance-sheet date counts, not weighted-average or current counts.",
        ],
    }

    if wa_entry:
        wa_val = wa_entry.get("value")
        wa_period = wa_entry.get("reporting_period")
        wa_source = "share_basis_evidence"
        wa_status = "verified"
    else:
        wa_val = None
        wa_period = None
        wa_source = None
        wa_status = "missing"

    weighted_average = {
        "value": wa_val,
        "financial_period": wa_period,
        "effective_date": None,
        "basis_type": "weighted_average_basic_shares_outstanding",
        "unit": wa_entry.get("unit") if wa_entry else None,
        "share_class": wa_entry.get("share_class") if wa_entry else None,
        "source": wa_source,
        "provenance": _share_provenance(wa_entry),
        "qualification_status": wa_status,
        "limitations": [
            "Weighted-average shares reflect time-weighted basic shares used for E.P.S. calculations, not point-in-time counts.",
        ],
    }

    def _evaluate_share_pair_comparability(obj_a: dict, obj_b: dict, pair_label: str) -> dict:
        val_a = obj_a.get("value")
        val_b = obj_b.get("value")

        if val_a is None and val_b is None:
            return {
                "status": "not_available",
                "reasons": [f"Both share identities in {pair_label} are missing."],
                "is_actionable": False,
            }
        if val_a is None or val_b is None:
            return {
                "status": "insufficient_identity",
                "reasons": [f"One share identity in {pair_label} is missing."],
                "is_actionable": False,
            }

        reasons = []
        basis_a = obj_a.get("basis_type")
        basis_b = obj_b.get("basis_type")
        if basis_a != basis_b:
            reasons.append(f"Basis type mismatch ({basis_a} vs {basis_b}).")

        date_a = obj_a.get("effective_date")
        date_b = obj_b.get("effective_date")
        if date_a != date_b:
            reasons.append(f"Effective date/period mismatch ({date_a} vs {date_b}).")

        if len(reasons) > 0:
            return {
                "status": "incomparable",
                "reasons": reasons,
                "is_actionable": False,
            }

        return {
            "status": "comparable",
            "reasons": [],
            "is_actionable": False,
        }

    comparability = {
        "pairs": {
            "current_vs_period_end": _evaluate_share_pair_comparability(current_market, financial_period_end, "current_vs_period_end"),
            "current_vs_weighted_average": _evaluate_share_pair_comparability(current_market, weighted_average, "current_vs_weighted_average"),
            "period_end_vs_weighted_average": _evaluate_share_pair_comparability(financial_period_end, weighted_average, "period_end_vs_weighted_average"),
        },
        "disclaimer": "Share counts from different effective dates or basis types (current live market vs audited period-end vs time-weighted basic) must not be treated as interchangeable.",
        "is_actionable": False,
    }

    def _missing_identity(identity_type: str, reason: str) -> dict:
        return {
            "value": None,
            "effective_date": None,
            "basis_type": identity_type,
            "unit": "shares",
            "qualification_status": "missing",
            "limitations": [reason],
        }

    return {
        "ticker": tk,
        "current_market": current_market,
        "financial_period_end": financial_period_end,
        "weighted_average": weighted_average,
        "weighted_average_diluted": _missing_identity(
            "weighted_average_diluted_shares_outstanding",
            "No retained, hash-verified FY2024 diluted weighted-average share citation exists.",
        ),
        "treasury_shares": _missing_identity(
            "treasury_shares_outstanding",
            "No retained, hash-verified FY2024 treasury-share citation exists; issued shares are not substituted.",
        ),
        "issued_shares": _missing_identity(
            "issued_shares",
            "No retained, hash-verified FY2024 issued-share citation exists; outstanding shares are not substituted.",
        ),
        "comparability": comparability,
    }


def build_earnings_anomaly_contract(
    tk: str,
    fin_entry: dict | None,
    canonical_entry: dict | None = None,
) -> dict:
    """Xây dựng hợp đồng an toàn ngữ nghĩa cho earnings relationship anomalies (vd NVL PAT > Revenue)."""
    if not isinstance(fin_entry, dict) or not fin_entry.get("row"):
        return {
            "ticker": tk,
            "status": "not_available",
            "trigger": None,
            "period": None,
            "observed_relationships": {},
            "decomposition": {
                "operating_profit": None,
                "financial_income": None,
                "other_profit": None,
                "availability_status": "unavailable",
            },
            "explanation_status": "insufficient_statement_detail",
            "recurrence_status": "unproven_single_period",
            "data_quality_status": "source_values_observed_verification_unavailable",
            "limitations": [
                "No financial statement records are available for this ticker.",
                "Source values remain unverified unless explicit primary-source verification exists.",
            ],
            "is_actionable": False,
        }

    row = fin_entry.get("row") or {}
    period = fin_entry.get("period_used") or row.get("period")

    rev = row.get("revenue")
    pat = row.get("net_profit")

    has_rev = rev is not None and not pd.isna(rev)
    has_pat = pat is not None and not pd.isna(pat)

    rev_val = float(rev) if has_rev else None
    pat_val = float(pat) if has_pat else None

    is_anomaly = False
    if rev_val is not None and pat_val is not None and rev_val > 0 and pat_val > rev_val:
        is_anomaly = True

    if not is_anomaly:
        return {
            "ticker": tk,
            "status": "not_observed",
            "trigger": None,
            "period": period,
            "observed_relationships": {
                "revenue": rev_val,
                "net_profit": pat_val,
                "relationship_type": "standard_operating_relationship",
            },
            "decomposition": {
                "operating_profit": row.get("operating_profit"),
                "financial_income": row.get("financial_income"),
                "other_profit": row.get("other_profit"),
                "availability_status": "standard",
            },
            "explanation_status": "not_applicable",
            "recurrence_status": "not_applicable",
            "data_quality_status": "source_values_observed_verification_unavailable",
            "limitations": [
                "Source values remain unverified unless explicit primary-source verification exists.",
            ],
            "is_actionable": False,
        }

    ratio = pat_val / rev_val if rev_val and rev_val > 0 else None

    op_prof = row.get("operating_profit")
    fin_inc = row.get("financial_income")
    oth_prof = row.get("other_profit")

    has_decomp = (op_prof is not None) or (fin_inc is not None) or (oth_prof is not None)
    decomp_status = "partially_available" if has_decomp else "unavailable"
    exp_status = "decomposition_available_unreconciled" if has_decomp else "insufficient_statement_detail"

    limitations = [
        "The relationship PAT > revenue exists in current retained payload and is not automatically a data error.",
        "Source values remain unverified unless explicit primary-source verification exists.",
        "Do not interpret PAT > revenue or ratio_pat_to_revenue as an operating margin, profitability margin, or sustainable margin.",
        "Non-operating income, financial income, disposal gains, or accounting reversals require detailed line-item audit.",
        "Single-period relationship does not establish multi-period recurring earnings quality.",
    ]

    return {
        "ticker": tk,
        "status": "anomaly_observed",
        "trigger": "profit_after_tax_exceeds_revenue",
        "period": period,
        "observed_relationships": {
            "revenue": rev_val,
            "net_profit": pat_val,
            "ratio_pat_to_revenue": ratio,
            "relationship_type": "pat_exceeds_revenue",
        },
        "decomposition": {
            "operating_profit": op_prof,
            "financial_income": fin_inc,
            "other_profit": oth_prof,
            "availability_status": decomp_status,
        },
        "explanation_status": exp_status,
        "recurrence_status": "unproven_single_period",
        "data_quality_status": "source_values_observed_verification_unavailable",
        "limitations": limitations,
        "is_actionable": False,
    }


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


def load_ohlcv_provider_purity(conn: sqlite3.Connection, ticker: str, n: int = OHLCV_RECENT_N) -> dict:
    """Which provider retained the same window ``load_ohlcv_recent`` returns, or an explicit
    refusal when it is not one provider.

    ``ohlcv.source`` is never added to ``ohlcv_recent`` itself -- that field's shape is
    depended on elsewhere and stays untouched. This is a separate, compact provenance
    summary for callers (``qualified_market_observations.py``) that need to know whether a
    provider-scoped verdict may be applied to the retained window at all. A window with more
    than one source, or no rows, is not "pure" -- it is refused rather than assigned to
    whichever provider happened to source the most rows.
    """
    # Same window-selection as load_ohlcv_recent (most recent n by date) so the provenance
    # this returns always describes the exact rows that function returned.
    rows = conn.execute(
        "SELECT source FROM ohlcv WHERE ticker=? ORDER BY date DESC LIMIT ?", (ticker, n)).fetchall()
    sources = sorted({str(r[0]).strip().upper() for r in rows if r[0] is not None})
    pure = len(rows) > 0 and len(sources) == 1
    return {
        "ticker": ticker,
        "session_count": len(rows),
        "sources_seen": sources,
        "pure": pure,
        "provider": sources[0] if pure else None,
    }


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
            "data_date": context_package_session_date(payload),
            "sha256": sha256_file(path), "mtime": _mtime_epoch(path), "mtime_iso": _mtime_iso(path),
        }
    return result


def context_package_session_date(payload: Mapping[str, Any] | None) -> str | None:
    """The market session a context package DESCRIBES, not the time it was BUILT.

    `generated_at` is a build timestamp. Using its date as the package's session identity
    conflated two different facts and only ever agreed by accident, on days when the
    package happened to be rebuilt before the next session. Rebuilding a package for the
    2026-07-30 session on 2026-08-03 then failed the session-scoped freshness gate as
    "context_package: 2026-08-03 (needs 2026-07-30)" -- the package was correct and the
    label was wrong.

    The Consumer already records the session explicitly under `latest_available_dates`
    (`price`/`technical`, both sourced from the same snapshot the bundle anchors on).
    `generated_at` remains the fallback for a legacy package that predates that field.
    """
    if not isinstance(payload, Mapping):
        return None
    latest = payload.get("latest_available_dates")
    if isinstance(latest, Mapping):
        for key in ("price", "technical"):
            value = latest.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:10]
    technical = payload.get("technical_summary")
    if isinstance(technical, Mapping):
        for key in ("screen_snapshot_date", "latest_signal_date"):
            value = technical.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:10]
    generated_at = payload.get("generated_at")
    return generated_at[:10] if isinstance(generated_at, str) and generated_at else None


def load_context_package_full(tk: str) -> dict | None:
    """Nội dung TOÀN VĂN context package cho 1 mã — chỉ dùng cho analysis_bundle.json (bundle lớn,
    dành cho công cụ đọc file trực tiếp). KHÔNG dùng cho focus_extract.json (giữ nhỏ theo thiết kế
    gốc chống truncation)."""
    path = context_packages_dir() / f"{tk}_context.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def context_package_basis_conflicts(
    context_package: Mapping[str, Any] | None,
    canonical_basis: Mapping[str, Any],
) -> list[str]:
    """Return every embedded basis path that contradicts the current bundle contract.

    Context packages are generated independently and may pre-date the bundle being
    exported.  They must never re-introduce a basis claim that the current canonical
    build has already kept unknown or unverified.
    """
    if not isinstance(context_package, Mapping):
        return []
    fields = (
        "price_basis",
        "price_basis_verified",
        "volume_basis",
        "volume_basis_verified",
    )
    expected = {field: canonical_basis.get(field) for field in fields}
    conflicts: list[str] = []
    price_summary = context_package.get("price_summary")
    if not isinstance(price_summary, Mapping):
        conflicts.append("context_package.price_summary:missing_or_malformed")
    else:
        for field in fields:
            if field not in price_summary:
                conflicts.append(f"context_package.price_summary.{field}:missing")

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for field in fields:
                if field in value and value.get(field) != expected[field]:
                    conflicts.append(f"{path}.{field}")
            for key, child in value.items():
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(context_package, "context_package")
    return sorted(set(conflicts))


def load_market_breadth() -> tuple[list[dict] | None, dict]:
    path = runtime_path(MARKET_BREADTH_PATH)
    if not path.exists():
        return None, {"file": MARKET_BREADTH_PATH, "exists": False, "sha256": None}
    df = pd.read_csv(path, encoding="utf-8-sig")
    records = [row_to_dict(r) for _, r in df.iterrows()]
    info = {
        "file": path.name, "exists": True, "rows": int(len(df)),
        "data_date": str(df["date"].max()) if len(df) and "date" in df.columns else None,
        "source_generated_at": common_retained_source_timestamp(records),
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


DEFAULT_SESSION_SCOPED_CATEGORIES = {
    "screen_snapshot_live",
    "ta_signals",
    "analysis_latest",
    "focus_analysis",
    "context_package",
}


def check_freshness(
    categories: dict,
    prior_session: str,
    reference_session: str | None = None,
    session_scoped_categories: set[str] | list[str] | None = None,
) -> dict:
    """categories: {tên_nhóm: ngày_hoặc_None}.

    Nhóm session-scoped yêu cầu ngày == reference_session.
    Thiếu ngày (None) cho nhóm session-scoped -> fail closed (blocked).
    Nhóm non-session (cadence khác) giữ nguyên ngày < prior_session.
    """
    scoped = set(session_scoped_categories) if session_scoped_categories is not None else DEFAULT_SESSION_SCOPED_CATEGORIES
    target_session = reference_session or prior_session
    stale, unknown = [], []

    for name, date_str in categories.items():
        if date_str is None:
            unknown.append(name)
            if name in scoped or reference_session is not None:
                stale.append({
                    "category": name,
                    "date": None,
                    "prior_session_required": prior_session,
                    "reference_session_required": target_session,
                    "reason": "missing_session_identity",
                })
            continue

        if name in scoped and reference_session is not None:
            if date_str != reference_session:
                stale.append({
                    "category": name,
                    "date": date_str,
                    "prior_session_required": prior_session,
                    "reference_session_required": reference_session,
                    "reason": "session_mismatch",
                })
        else:
            if date_str < prior_session:
                stale.append({
                    "category": name,
                    "date": date_str,
                    "prior_session_required": prior_session,
                    "reference_session_required": target_session,
                    "reason": "older_than_prior_session",
                })

    res = {
        "prior_session": prior_session,
        "stale": stale,
        "unknown": unknown,
        "blocked": bool(stale),
    }
    if reference_session is not None:
        res["reference_session"] = reference_session
    return res


def check_artifact_order(root: Path, graph: dict[str, list[str]] | None = None) -> list[dict]:
    """Nâng cấp freshness gate (mục 4): downstream KHÔNG được có mtime CŨ HƠN bất kỳ upstream nào
    nó phụ thuộc (ARTIFACT_DEPENDENCY_GRAPH) — nếu có, downstream nhiều khả năng đang mang số liệu
    sinh ra TRƯỚC lần chạy mới nhất của upstream (ví dụ thực tế: ta_signals.csv sinh trước lần
    vn_indicators.py rerun gần nhất -> rs_rating trong đó lệch canonical, xem reconcile_rs_rating).
    Chỉ so sánh các cặp mà CẢ HAI file đều tồn tại (file chưa từng sinh thì bỏ qua, không đánh giá
    được thứ tự).

    This is a build-ordering signal derived from filesystem mtime, never a generation timestamp
    or data_as_of -- see release_session_contract.py's module docstring, which documents that
    this function deliberately keeps mtime scoped to "was downstream generated after upstream"
    and never uses it as a stand-in for session identity. The `*_mtime` fields below are raw
    filesystem mtimes, not artifact generation instants."""
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
                "downstream": downstream, "downstream_mtime": _mtime_iso(root / downstream),
                "upstream": up, "upstream_mtime": _mtime_iso(root / up),
                "gap_seconds": round(u_mtime - d_mtime, 1),
                "detail": (f"{downstream} có mtime {_mtime_iso(root / downstream)}, TRƯỚC "
                          f"{up} (mtime {_mtime_iso(root / up)}) — {downstream} có thể đang chứa "
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
            scope="pipeline", ticker=None, code="artifact_mtime_before_upstream", severity="warning",
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
                       financial_rows, financial_canonical, snapshot_info, ta_info, reference_at,
                       price_basis, verified_periods_by_ticker=None) -> dict:
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
    ohlcv_provider_provenance = load_ohlcv_provider_purity(conn, tk)
    rs_reconciliation = reconcile_rs_rating(tk, snapshot_rows, ta_rows, snapshot_info, ta_info)
    corporate = load_corporate_intelligence(conn, tk)
    snapshot_row = snapshot_rows.get(tk) or {}
    technical_row = ta_rows.get(tk) or {}
    snapshot_freshness = freshness_envelope(domain="daily_market", as_of_date=snapshot_row.get("date"), generated_at=retained_source_timestamp(snapshot_row), source=SNAPSHOT_LIVE_PATH, reference_at=reference_at)
    technical_freshness = freshness_envelope(domain="technical", as_of_date=technical_row.get("date"), generated_at=retained_source_timestamp(technical_row), source=TA_SIGNALS_PATH, reference_at=reference_at, dependency=snapshot_freshness)
    verified_evidence_period = (verified_periods_by_ticker or {}).get(tk)
    financial_freshness = build_financial_freshness(fin, verified_evidence_period, reference_at)
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
    current_price_actionable = snapshot_freshness.get("is_actionable") is True and price_basis.get("price_basis_verified") is True
    relative_val = evaluate_relative_valuation({
        "entity_type": get_default_registry().entity_type_for(tk),
        "current_price": _historical_relative_valuation_price(tk),
        "share_count_weighted_average_basic": _relative_valuation_weighted_average_share_count(tk),
        "share_count_period_end": _relative_valuation_period_end_share_count(tk),
        "financial": _financial_input(financial_canonical.get(tk)),
    }, reference_at=reference_at.isoformat())
    return {
        "snapshot": snapshot_rows.get(tk),
        "canonical_rs_rating": rs_reconciliation["canonical_rs_rating"],
        "rs_rating_reconciliation": rs_reconciliation,
        "ta_signal": ta_rows.get(tk),
        "ta_signal_semantics": build_ta_signal_semantics(ta_rows.get(tk)),
        "analysis_score": build_analysis_score_contract(score_rows.get(tk), score_session),
        "financial_latest": fin.get("row"),
        "financial_period_used": fin.get("period_used"),
        "financial_latest_quality": {
            "excluded_unverified_periods": fin.get("excluded_unverified_periods", []),
        },
        "financial_period_coverage": build_financial_period_coverage_contract(tk, fin, financial_canonical.get(tk), verified_evidence_period),
        "earnings_anomaly": build_earnings_anomaly_contract(tk, fin, financial_canonical.get(tk)),
        "financial_canonical": financial_canonical.get(tk, {"status": "missing", "records": []}),
        "financial_identity": empty_identity_export(),
        "fundamental_quality": evaluate_fundamental_quality(financial_canonical.get(tk), get_default_registry().entity_type_for(tk)),
        "intrinsic_valuation": evaluate_intrinsic_valuation({"entity_type": get_default_registry().entity_type_for(tk), "financial": _financial_input(financial_canonical.get(tk)), "share_count": _net_net_share_count(tk), "current_price_actionable": current_price_actionable}, reference_at=reference_at.isoformat()),
        "scenario_analysis": evaluate_scenario_analysis({}, reference_at=reference_at.isoformat()),
        "risk_analysis": evaluate_market_risk({"ticker": tk, "ohlcv": ohlcv, "price_adjustment": "qualified" if price_basis.get("price_basis_verified") else "unknown", "volume_units": "qualified" if price_basis.get("volume_basis_verified") else "unknown", "volume_basis": price_basis.get("volume_basis"), "current_actionable": current_price_actionable}, reference_at=reference_at.isoformat(), runtime_root=runtime_root),
        "relative_valuation": relative_val,
        "valuation_namespaces": build_valuation_namespaces_contract(tk, snapshot_rows.get(tk), relative_val, fin),
        "share_basis_identities": build_share_basis_identities_contract(tk, snapshot_rows.get(tk), runtime_root()),
        "ohlcv_recent": ohlcv,
        "ohlcv_recent_count": len(ohlcv),
        "ohlcv_provider_provenance": ohlcv_provider_provenance,
        "corporate_intelligence": corporate,
        "freshness": freshness,
        "analysis_readiness": evaluate_analysis_readiness(freshness=freshness, corporate_intelligence=corporate, reference_at=reference_at, price_basis_provenance=price_basis),
        "warnings": warnings,
    }


def build_focus_extract(tickers, conn, snapshot_rows, ta_rows, score_rows, score_session,
                        financial_rows, financial_canonical, snapshot_info, ta_info, reference_at):
    # Computed once for the whole bundle (not per ticker): resolve_verified_financial_periods()
    # scans the entire retained citation/observation store, which would otherwise be redundant
    # work repeated for every ticker. Filtered to this milestone's rollout scope -- see
    # _PHASE_5C_ENABLED_TICKERS above for why VCB's independently-qualifying evidence is not
    # surfaced yet.
    verified_periods_by_ticker = {
        tk: v for tk, v in resolve_verified_financial_periods(runtime_root()).items()
        if tk in _PHASE_5C_ENABLED_TICKERS
    }
    price_basis = build_price_basis_contract()
    return {tk: build_ticker_entry(tk, conn, snapshot_rows, ta_rows, score_rows, score_session,
                                   financial_rows, financial_canonical, snapshot_info, ta_info, reference_at,
                                   price_basis, verified_periods_by_ticker)
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
# Phase 5D — opt-in distribution evidence wiring (disabled by default)
# ==========================================================================
# Reuses the exact Phase 5A opt-in flag (--include-analysis-lane-eligibility); no new
# CLI surface. distribution_evidence.py is never called unless that flag is set, and this
# section never recalculates coverage, derives yield/payout/CAGR/return, or reclassifies
# cash vs non-cash -- the complete builder result is attached unmodified. Runs before
# attach_analysis_lane_eligibility() so tickers[ticker].distribution_evidence is already
# present on entry when the lane evaluator reads it.

def build_distribution_evidence_for_ticker_safe(ticker: str, root: Path) -> dict[str, Any] | None:
    """Fail-closed wrapper: a local build failure for this ticker returns None (so no
    distribution_evidence key is attached for it) and never raises into the caller's
    per-ticker loop or corrupts any other field on this or any other ticker's entry."""
    try:
        return build_distribution_evidence_for_ticker(root, ticker)
    except Exception:
        return None


def attach_distribution_evidence(
    bundle_entries: dict[str, dict], root: Path, include: bool,
) -> dict[str, dict]:
    """Disabled-by-default opt-in (default include=False): when include is False,
    build_distribution_evidence_for_ticker() is never called and no distribution_evidence
    key is ever added -- current default bundle behavior is preserved exactly. When True,
    attaches the complete builder result per ticker; a ticker whose build fails closed is
    simply skipped, never corrupting any other ticker's fields."""
    if not include:
        return bundle_entries
    for tk, entry in bundle_entries.items():
        result = build_distribution_evidence_for_ticker_safe(tk, root)
        if result is not None:
            entry["distribution_evidence"] = result
    return bundle_entries


# ==========================================================================
# DNSE foreign-flow VALUE integration — opt-in (disabled by default)
# ==========================================================================
# New dedicated flag (--include-dnse-foreign-flow): unrelated to lane eligibility,
# so it does not reuse --include-analysis-lane-eligibility. dnse_foreign_flow_store.py
# is never called unless the flag is set, and this section never derives an
# ownership/free-float percentage, a flow/trading-value ratio, or promotes foreign
# volume/room -- those stay unqualified by contract (see dnse_foreign_flow_capability.py
# and dnse_foreign_flow_store.py). The complete builder result -- including its
# per-ticker freshness verdict against this export's own reference session -- is
# attached unmodified.

def build_dnse_foreign_flow_for_ticker_safe(
    ticker: str, root: Path, reference_session_date: str | None,
) -> dict[str, Any] | None:
    """Fail-closed wrapper: a local build failure for this ticker returns None (so no
    foreign_flow key is attached for it) and never raises into the caller's per-ticker
    loop or corrupts any other field on this or any other ticker's entry."""
    try:
        return build_dnse_foreign_flow_series(root, ticker, reference_session_date=reference_session_date)
    except Exception:
        return None


def attach_dnse_foreign_flow(
    bundle_entries: dict[str, dict], root: Path, include: bool,
    reference_session_date: str | None = None,
) -> dict[str, dict]:
    """Disabled-by-default opt-in (default include=False): when include is False,
    build_dnse_foreign_flow_series() is never called and no foreign_flow key is ever
    added -- current default bundle behavior is preserved exactly. When True, attaches
    the complete builder result per ticker (status="missing" for a ticker with no
    retained DNSE observations, not an absent key -- the caller can always tell
    "not asked" (key absent, include=False) from "asked, nothing retained yet"
    (key present, status="missing")).

    `reference_session_date` is this export's own already-resolved exact session
    identity (the same value that becomes the bundle's `reference_session_date`), passed
    straight through so each ticker's `foreign_flow.freshness` compares against the
    release session actually being built -- never a wall-clock read, never invented."""
    if not include:
        return bundle_entries
    for tk, entry in bundle_entries.items():
        result = build_dnse_foreign_flow_for_ticker_safe(tk, root, reference_session_date)
        if result is not None:
            entry["foreign_flow"] = result
    return bundle_entries


# ==========================================================================
# Current-state market risk (HPG x VNINDEX) — opt-in (disabled by default)
# ==========================================================================
# New dedicated flag (--include-current-state-market-risk). Delegates all
# qualification and beta/correlation math to dnse_current_state_market_risk.py
# -- this attach layer never recomputes a formula, only shapes the already-
# complete contract result and adds a bundle-common "status" convenience
# field (available/not_qualified), the same vocabulary used elsewhere in this
# module. Offline: reads ONLY the durable, runtime-root-backed
# dnse_market_risk_evidence_store.py via
# build_current_state_market_risk_from_evidence_store() -- never the
# workspace-relative operations-review/ path, never a live network call, so
# this reproduces identically wherever the runtime root travels (including a
# clean release checkout that never had operations-review/ as a sibling).
# Deliberately a separate top-level key from
# tickers[ticker].risk_analysis.market_risk (risk_liquidity.py's
# point-in-time-labelled section, untouched) -- current_state_market_risk
# uses a different name specifically so PIT=false is unambiguous.

def build_current_state_market_risk_for_ticker_safe(
    ticker: str, root: Path, reference_session_date: str | None = None,
) -> dict[str, Any] | None:
    """Fail-closed wrapper: a local build failure for this ticker returns None
    (so no current_state_market_risk key is attached for it) and never raises
    into the caller's per-ticker loop or corrupts any other field on this or
    any other ticker's entry. In practice
    build_current_state_market_risk_from_evidence_store() itself already
    never raises (missing/malformed durable evidence resolves to an explicit
    not-qualified result) -- this try/except is defense in depth, matching
    every sibling attach-layer wrapper in this module."""
    try:
        result = build_current_state_market_risk_from_evidence_store(
            ticker, "VNINDEX", runtime_root=root, reference_session_date=reference_session_date,
        )
        result["status"] = (
            "available" if result.get("qualification_status") == "CURRENT_STATE_BETA_CORRELATION_QUALIFIED"
            else "not_qualified"
        )
        # Unconditional, never derived from qualification: this is a descriptive
        # analytical capability, never a trading signal, regardless of whether a
        # real beta/correlation was computed for this ticker.
        result["is_actionable"] = False
        # Top-level convenience copies of values already present inside
        # aligned_sessions/beta -- re-exposed, never recomputed, so a bundle
        # reader does not have to know the shadow contract's own nesting to
        # find paired_return_count's companions or the shared sample_adequacy
        # verdict (identical on beta and correlation by construction).
        aligned = result.get("aligned_sessions") or {}
        result["stock_return_count"] = aligned.get("stock_return_count")
        result["benchmark_return_count"] = aligned.get("benchmark_return_count")
        result["dropped_stock_sessions"] = aligned.get("dropped_stock_sessions")
        result["dropped_benchmark_sessions"] = aligned.get("dropped_benchmark_sessions")
        result["sample_adequacy"] = (result.get("beta") or {}).get("sample_adequacy")
        return result
    except Exception:
        return None


def attach_current_state_market_risk(
    bundle_entries: dict[str, dict], root: Path, include: bool,
    reference_session_date: str | None = None,
) -> dict[str, dict]:
    """Disabled-by-default opt-in (default include=False): when include is
    False, dnse_current_state_market_risk.py is never called and no
    current_state_market_risk key is ever added -- current default bundle
    behavior is preserved exactly. When True, attaches a
    current_state_market_risk entry to every ticker: HPG resolves
    status="available" with real beta/correlation; every other ticker
    resolves status="not_qualified" (the underlying contract's own honest
    fail-closed result -- never a fabricated zero beta/correlation). A ticker
    whose build raises unexpectedly is skipped entirely (key absent), never
    corrupting any other ticker's fields.

    `reference_session_date` is this export's own already-resolved exact
    session identity (the same value that becomes the bundle's
    `reference_session_date`, and the same one `attach_dnse_foreign_flow`
    already receives), passed straight through so `current_state_market_risk`
    freshness compares against the release actually being built -- never a
    wall-clock read, never invented."""
    if not include:
        return bundle_entries
    for tk, entry in bundle_entries.items():
        result = build_current_state_market_risk_for_ticker_safe(tk, root, reference_session_date)
        if result is not None:
            entry["current_state_market_risk"] = result
    return bundle_entries


# ==========================================================================
# P1E — opt-in market-wide canonical financial facts (disabled by default)
# ==========================================================================
# New dedicated flag (--include-canonical-financial-facts). Reads the layer-3 store under
# <runtime_root>/data/canonical-financial-facts/ and attaches one additive key,
# tickers[ticker].canonical_financial_facts. It never reads or writes financial_canonical,
# fundamental_quality, financial_period_coverage or any other pre-existing field, so both the
# default bundle and every existing consumer are unaffected regardless of the flag's state.


def attach_canonical_financial_facts(bundle_entries: dict[str, dict], root: Path,
                                     include: bool, *, session_date: str | None = None,
                                     price_basis_verified: bool = False) -> dict[str, dict]:
    """Disabled-by-default opt-in; see canonical_financial_bundle_section.attach.

    `session_date` is the session the rest of this export is anchored to. The section resolves
    a share count and a price for that session, so it has to be told which one; left to a
    default it stamped one session's shares onto every export.
    """
    from canonical_financial_bundle_section import attach

    return attach(bundle_entries, root, include, session_date=session_date,
                  price_basis_verified=price_basis_verified)


def attach_pillar_a_research_projection(bundle_entries: dict[str, dict], root: Path,
                                        include: bool) -> dict[str, Any] | None:
    """Attach the read-only Pillar A research projection and deterministic coverage.

    It uses the existing canonical shard store directly; no fact is copied into a new store,
    no provider is queried, and no existing trusted ``financial_canonical`` input is replaced.
    """
    if not include:
        return None
    from canonical_fact_store import _load_state, read_facts
    from official_annual_financial_fact_projection import facts_for_ticker
    from financial_entity_applicability import load_entity_profiles

    state = _load_state(root)
    records = {str(record.get("ticker")): record for record in state.get("tickers") or []}
    if not records:
        return None
    profiles = load_entity_profiles(Path(__file__).with_name("config") / "ticker_entity_profiles.csv")
    evidence_index = load_evidence_index(root)
    def _facts_with_unstored_official(ticker: str) -> list[dict[str, Any]]:
        """Avoid treating a governed canonical promotion as a conflicting duplicate."""
        canonical = read_facts(root, ticker)
        identities = {str(fact.get("fact_id")) for fact in canonical if fact.get("fact_id")}
        return [*canonical, *(fact for fact in facts_for_ticker(root, ticker)
                              if str(fact.get("fact_id")) not in identities)]
    for ticker, entry in bundle_entries.items():
        record = records.get(str(ticker).upper())
        if record is None:
            continue
        entity_type = record.get("issuer_entity_type") or profiles.get(str(ticker).upper())
        entity_authority = record.get("archetype_authority")
        if entity_type and entity_authority in (None, "unknown"):
            entity_authority = "manual_profile"
        projection = build_research_financial_fact_projection(
            ticker, _facts_with_unstored_official(ticker), entity_type=entity_type,
            entity_authority=entity_authority, evidence_index=evidence_index,
        )
        entry["research_financial_fact_projection"] = projection
        entry["research_financial_source_selection"] = select_research_source(entry, projection)
    records = state.get("tickers") or []
    coverage_records = [{**record,
                         "issuer_entity_type": record.get("issuer_entity_type") or profiles.get(str(record.get("ticker")).upper()),
                         "archetype_authority": record.get("archetype_authority") or (
                             "manual_profile" if profiles.get(str(record.get("ticker")).upper()) else "unknown")}
                        for record in state.get("tickers") or []]
    coverage = research_financial_coverage_summary(
        coverage_records, _facts_with_unstored_official, evidence_index=evidence_index,
    )
    # A summary only: facts remain in their original shards and are never rewritten by export.
    coverage["conflict_decomposition"] = canonical_conflict_coverage_summary(
        records, lambda ticker: read_facts(root, ticker),
    )
    return coverage


# ==========================================================================
# Phase 6A — opt-in fundamental quality evidence wiring (disabled by default)
# ==========================================================================
# New dedicated flag (--include-fundamental-quality-evidence), independent of the Phase
# 5A/5D flag. tickers[ticker].fundamental_quality_evidence is a distinct key from the
# pre-existing, always-on tickers[ticker].fundamental_quality field -- this section never
# reads or writes that field, so the default bundle (and every existing fundamental_quality
# consumer) is unaffected regardless of this new flag's state.

def build_fundamental_quality_evidence_for_ticker_safe(ticker: str, entry: Mapping[str, Any], root: Path) -> dict[str, Any] | None:
    """Fail-closed wrapper: a local build failure for this ticker returns None (so no
    fundamental_quality_evidence key is attached for it) and never raises into the caller's
    per-ticker loop or corrupts any other field on this or any other ticker's entry."""
    try:
        return build_fundamental_quality_evidence_for_ticker(
            ticker,
            entity_type=entry.get("entity_type"),
            financial_canonical=((entry.get("research_financial_source_selection") or {}).get("financial_canonical")
                                 or entry.get("financial_canonical")),
            financial_period_coverage=entry.get("financial_period_coverage"),
            runtime_root=root,
        )
    except Exception:
        return None


def attach_fundamental_quality_evidence(
    bundle_entries: dict[str, dict], root: Path, include: bool,
    taxonomy_sidecar: Mapping[str, Any] | None = None,
) -> dict[str, dict]:
    """Disabled-by-default opt-in (default include=False): when include is False,
    build_fundamental_quality_evidence_for_ticker() is never called and no
    fundamental_quality_evidence key is ever added -- current default bundle behavior
    (including the pre-existing fundamental_quality field) is preserved exactly. When True,
    attaches the complete builder result per ticker; a ticker whose build fails closed is
    simply skipped, never corrupting any other ticker's fields."""
    if not include:
        return bundle_entries
    for tk, entry in bundle_entries.items():
        result = build_fundamental_quality_evidence_for_ticker_safe(tk, entry, root)
        if result is not None:
            entry["fundamental_quality_evidence"] = result
        research_financial = ((entry.get("research_financial_source_selection") or {}).get("financial_canonical")
                              or entry.get("financial_canonical"))
        entry["historical_capital_structure"] = build_historical_capital_structure_analysis(
            tk, entry.get("entity_type"), research_financial,
            entry.get("financial_period_coverage"), (entry.get("freshness") or {}).get("financial_statements"), root,
        )
        entry["historical_fundamental_brief"] = build_historical_fundamental_brief(
            tk, result, entry["historical_capital_structure"],
        )
        # Generated statement-taxonomy evidence, resolved under the fixed authority order:
        # the manual profile always wins; the generated taxonomy can only withhold the
        # corporate model; an unknown taxonomy never defaults to corporate. The full
        # generated record is attached as provenance and is explicitly labelled
        # generated_evidence -- never as a manually verified issuer type.
        taxonomy = resolve_taxonomy(taxonomy_sidecar, tk)
        authority = resolve_entity_authority(entry.get("entity_type"), taxonomy)
        entry["statement_taxonomy_evidence"] = {
            "authority_level": "generated_evidence",
            "statement_taxonomy": taxonomy,
            "entity_type_authority": authority["authority"],
            "resolved_entity_type": authority["entity_type"],
            "resolution_reason": authority["reason"],
            "record": sidecar_provenance(taxonomy_sidecar, tk),
            "limitations": [
                "Generated statement taxonomy observes the reporting TEMPLATE a filing uses;"
                " it is not a manually verified issuer_entity_type and carries lower authority"
                " than config/ticker_entity_profiles.csv.",
            ],
        }
        entry["financial_distress_evidence"] = build_financial_distress_evidence_for_ticker(
            tk, entry.get("entity_type"), entry.get("financial_canonical"), root,
            statement_taxonomy=taxonomy,
        )
    return bundle_entries


# Altman Z' identity sourcing. Deliberately reuses the Phase 6A opt-in flag rather than
# adding a new CLI surface: Z' is a fundamental-quality/distress model over the same
# already-qualified FY2024 evidence, so it belongs on the same switch. Default bundle
# output is unchanged while that flag is off.
# Altman identity name -> the canonical_metric already present on the entry's
# financial_canonical records. `total_equity` (not `shareholders_equity`) is X4's
# numerator: Z' uses total book equity including non-controlling interests, matching the
# statement's own 400 = 410 subtotal and the 440 = 300 + 400 identity.
_ALTMAN_FROM_CANONICAL = {
    "current_assets": "current_assets", "total_assets": "total_assets",
    "total_liabilities": "total_liabilities", "net_sales": "revenue", "owners_equity": "total_equity",
}


def _altman_identity(entry: Mapping[str, Any], extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    identity = {"value": entry["value"], "period": entry["reporting_period"],
                "statement_scope": entry["statement_scope"], "currency": entry["currency"],
                "unit_scale": entry["unit_scale"], "citation_id": entry["citation_id"]}
    if extra:
        identity.update(extra)
    return identity


def _retained_industry(ticker: str, root: Path) -> str | None:
    """The retained ICB-style industry label for `ticker`, or None.

    Read-only and fail-quiet: an unreadable metadata table simply yields None, and the
    Altman applicability gate then blocks on a missing industry rather than assuming one.
    """
    try:
        connection = sqlite3.connect(f"file:{(root / 'vn_stock.db').as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        row = connection.execute("SELECT industry FROM metadata WHERE ticker = ?", (ticker,)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    return str(row[0]) if row and row[0] and str(row[0]).strip() else None


def build_financial_distress_evidence_for_ticker(ticker: str, entity_type: Any,
                                                  financial_canonical: Mapping[str, Any] | None,
                                                  root: Path,
                                                  statement_taxonomy: Any = None) -> dict[str, Any]:
    """Assemble Altman Z' inputs from already-qualified evidence only, then evaluate.

    Never reads a price, a current-session field, or an unqualified provider row. The two
    distress-specific identities come from financial_identity_citations.jsonl and choose
    the reporting period; the five balance-sheet/income-statement identities are then taken
    from the entry's own already-enriched canonical records, accepted only at
    quality_state == "available" and only at that exact same period/scope/currency/scale.
    EBIT is derived from the already-qualified EBITDA components. Any absence simply leaves
    that identity out and evaluate_altman_z_score() fails closed naming it; this function
    never raises into the caller's per-ticker loop.
    """
    identities: dict[str, dict[str, Any]] = {}
    try:
        financial_identities = load_verified_financial_identities(root).get("by_key") or {}
        for metric in ("current_liabilities", "retained_earnings"):
            found = latest_financial_identity(financial_identities, ticker, metric)
            if found is not None:
                identities[metric] = _altman_identity(found)

        anchor = next(iter(identities.values()), None)
        if anchor is not None:
            records = (financial_canonical or {}).get("records") or []
            for name, canonical_metric in _ALTMAN_FROM_CANONICAL.items():
                for record in records:
                    if (record.get("canonical_metric") == canonical_metric
                            and record.get("quality_state") == "available"
                            and (record.get("period_identity") or {}).get("period") == anchor["period"]
                            and record.get("statement_scope") == anchor["statement_scope"]
                            and record.get("currency") == anchor["currency"]
                            and record.get("unit_scale") == anchor["unit_scale"]
                            and record.get("value") is not None):
                        identities[name] = {"value": record["value"], "period": anchor["period"],
                                             "statement_scope": record["statement_scope"],
                                             "currency": record["currency"], "unit_scale": record["unit_scale"],
                                             "canonical_metric": canonical_metric,
                                             "source": record.get("source")}
                        break

        components = load_verified_ebitda_components(root).get("by_key") or {}
        pbt = latest_ebitda_component(components, ticker, "profit_before_tax")
        interest = latest_ebitda_component(components, ticker, "interest_expense")
        if (pbt is not None and interest is not None
                and pbt["reporting_period"] == interest["reporting_period"]
                and pbt["statement_scope"] == interest["statement_scope"]
                and pbt["currency"] == interest["currency"] and pbt["unit_scale"] == interest["unit_scale"]):
            identities["ebit"] = _altman_identity(pbt, {
                "value": pbt["value"] + interest["value"],
                "derivation": "profit_before_tax + interest_expense",
                "citation_id": [pbt["citation_id"], interest["citation_id"]]})
    except Exception:
        pass
    # entity_type is passed through as-is, never coerced to a default: an absent value is
    # a distinct third state and evaluate_altman_z_score() blocks on it rather than
    # assuming the corporate archetype. industry is required too -- Z' keeps the
    # industry-sensitive X5 term, so a confirmed non-financial issuer in a
    # non-manufacturing industry is still withheld. statement_taxonomy is generated
    # evidence of the reporting *template* only: it can withhold Z' for a specialized
    # financial filer whose entity type is unresolved, and can never grant eligibility.
    return evaluate_altman_z_score(identities, entity_type=entity_type,
                                    industry=_retained_industry(ticker, root),
                                    statement_taxonomy=statement_taxonomy)


# ==========================================================================
# Phase 5A — opt-in analysis-lane eligibility wiring (disabled by default)
# ==========================================================================
# Same disabled-by-default style as sector_aware_downstream_facts.py: the evaluator in
# analysis_lane_eligibility.py is never called unless a caller explicitly opts in. This
# section does not alter that module's semantics -- it only assembles the already-built
# per-ticker contracts (plus the bundle-level price/volume basis) into the exact keyword
# arguments evaluate_ticker_lanes() expects, and attaches the complete, unmodified result
# to tickers[ticker].analysis_lane_eligibility when enabled.

def _lane_eval_risk_semantics(entry: Mapping[str, Any] | None) -> dict | None:
    """Canonical nested analysis_score.risk_semantics, legacy top-level risk_semantics
    fallback only when canonical is absent -- mirrors the Consumer-side resolution in
    ai-core-private/builders/build_ticker_context.py::risk_semantics_contract (commit
    21a3731), so the opt-in wiring sources risk_semantics the same way end to end."""
    if not isinstance(entry, dict):
        return None
    analysis_score = entry.get("analysis_score")
    canonical = analysis_score.get("risk_semantics") if isinstance(analysis_score, dict) else None
    return canonical if canonical is not None else entry.get("risk_semantics")


def _lane_eval_news_window_semantics(entry: Mapping[str, Any] | None) -> dict | None:
    if not isinstance(entry, dict):
        return None
    news_related = entry.get("news_related")
    return news_related.get("news_window_semantics") if isinstance(news_related, dict) else None


def build_analysis_lane_eligibility_for_ticker(
    ticker: str, entry: Mapping[str, Any], price_basis_provenance: Mapping[str, Any] | None,
) -> list[dict[str, Any]] | None:
    """Evaluate one ticker's analysis-lane eligibility from its already-built bundle
    contracts. Does not alter evaluate_ticker_lanes()'s existing semantics: no scores, no
    ticker/lane ranking, no recommendations, no scenario probabilities, no target prices,
    no cross-lane suppression -- the complete evaluator result is returned unmodified.

    A local evaluation failure for this ticker fails closed (returns None, so no
    analysis_lane_eligibility key is attached for it) and never raises into the caller's
    per-ticker loop or corrupts any other field on this or any other ticker's entry."""
    try:
        return evaluate_ticker_lanes(
            ticker,
            entity_type=entry.get("entity_type"),
            financial_period_coverage=entry.get("financial_period_coverage"),
            valuation_namespaces=entry.get("valuation_namespaces"),
            share_basis_identities=entry.get("share_basis_identities"),
            earnings_anomaly=entry.get("earnings_anomaly"),
            risk_semantics=_lane_eval_risk_semantics(entry),
            opportunity_ranking=entry.get("opportunity_ranking"),
            ta_signal_semantics=entry.get("ta_signal_semantics"),
            news_window_semantics=_lane_eval_news_window_semantics(entry),
            price_basis_provenance=price_basis_provenance,
            distribution_evidence=entry.get("distribution_evidence"),
        )
    except Exception:
        return None


def attach_analysis_lane_eligibility(
    bundle_entries: dict[str, dict], price_basis_provenance: Mapping[str, Any] | None, include: bool,
) -> dict[str, dict]:
    """Disabled-by-default opt-in (default include=False), same style as
    sector_aware_downstream_facts: when include is False, evaluate_ticker_lanes() is never
    called and no analysis_lane_eligibility key is ever added -- current default bundle
    behavior is preserved exactly. When True, attaches the complete evaluator result per
    ticker; a ticker whose evaluation fails closed is simply skipped, never corrupting any
    other ticker's fields."""
    if not include:
        return bundle_entries
    for tk, entry in bundle_entries.items():
        result = build_analysis_lane_eligibility_for_ticker(tk, entry, price_basis_provenance)
        if result is not None:
            entry["analysis_lane_eligibility"] = result
    return bundle_entries


PORTFOLIO_RISK_PILOT_TICKERS = frozenset({"HPG", "VNM", "VCB"})


def attach_historical_decision_analysis(bundle_entries: dict[str, dict], include: bool,
                                        additional_tickers: Iterable[str] = (), *,
                                        runtime_root_path: Path | None = None) -> dict[str, dict]:
    """Add qualified historical-only analysis for the approved corporate cohort.

    The feature is opt-in so legacy bundle bytes remain unchanged.  Only the pilot set is
    evaluated; non-pilot tickers receive no fabricated section.
    """
    if not include:
        return bundle_entries
    from official_annual_financial_fact_projection import facts_for_ticker
    allowed = set(PILOT_TICKERS) | {str(ticker).upper() for ticker in additional_tickers}
    for ticker in sorted(allowed):
        entry = bundle_entries.get(ticker)
        if isinstance(entry, dict):
            selected = ((entry.get("research_financial_source_selection") or {}).get("financial_canonical")
                        or entry.get("financial_canonical"))
            official = facts_for_ticker(runtime_root_path, ticker) if runtime_root_path is not None else []
            research_entry = {**entry, "financial_canonical": merge_official_annual_facts(selected, official)}
            entry["historical_decision_analysis"] = evaluate_historical_decision_analysis(
                ticker, research_entry, allow_scaleout=ticker not in PILOT_TICKERS,
            )
    cohort_tickers = tuple(ticker for ticker in sorted(allowed) if isinstance(bundle_entries.get(ticker), dict))
    cohort = {
        ticker: (bundle_entries.get(ticker, {}).get("historical_decision_analysis") or {}).get("fundamental_analytics", {})
        for ticker in cohort_tickers
    }
    if len(cohort_tickers) >= 2:
        comparative = build_comparative_matrix(cohort)
        qualified_cohort = build_qualified_cohort_comparison(cohort, cohort_tickers=cohort_tickers)
        for ticker in cohort:
            bundle_entries[ticker]["historical_fundamental_comparative_matrix"] = comparative
            bundle_entries[ticker]["qualified_cohort_comparison"] = qualified_cohort
    return bundle_entries

def attach_portfolio_risk_analysis(bundle_entries: dict[str, dict], price_basis: Mapping[str, Any], include: bool) -> dict[str, dict]:
    if not include: return bundle_entries
    for ticker in sorted(PORTFOLIO_RISK_PILOT_TICKERS):
        if isinstance(bundle_entries.get(ticker),dict): bundle_entries[ticker]["portfolio_risk_analysis"]=evaluate_portfolio_risk_analysis(ticker,bundle_entries[ticker],price_basis)
    return bundle_entries


def attach_qualified_market_observations(bundle_entries: dict[str, dict], include: bool) -> dict[str, dict]:
    """Add provider-scoped descriptive/technical market observations for every ticker.

    Unlike the historical-decision/portfolio-risk lane above, this is **not** restricted to
    ``PILOT_TICKERS``: it depends only on a single-provider retained OHLCV window (see
    ``load_ohlcv_provider_purity``), which every production ticker has, not on the
    fundamental-evidence pilot set. Opt-in so legacy bundle bytes remain unchanged; a ticker
    whose window is missing, mixed-provider or too short gets an explicit ``unavailable``
    record from ``qualified_market_observations.evaluate`` rather than no key at all.
    """
    if not include:
        return bundle_entries
    for ticker, entry in bundle_entries.items():
        if isinstance(entry, dict):
            entry["qualified_market_observations"] = evaluate_qualified_market_observations(ticker, entry)
    return bundle_entries


def attach_ticker_capability_matrix(bundle_entries: dict[str, dict]) -> dict[str, dict]:
    """Attach the P1.5 capability projection to every retained ticker entry.

    This is deliberately unconditional once a bundle is being built: missing optional
    upstream contracts are represented as unavailable by the projection rather than being
    rerun or silently omitted.  It changes no legacy field and performs no provider, DB, or
    evidence work.
    """
    for ticker, entry in bundle_entries.items():
        if isinstance(entry, dict):
            entry["ticker_capability_matrix"] = build_ticker_capability_matrix(
                ticker, entry, market_authority=MARKET_DATA_SOURCE_AUTHORITY_SELECTION,
            )
    return bundle_entries


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
    parser.add_argument("--output-dir", help="Explicit output directory for an isolated/shadow export")
    parser.add_argument("--allow-stale", action="store_true",
                        help="Vẫn xuất bundle dù nguồn lệch phiên/lệch thứ tự tạo artifact"
                             " (ghi cảnh báo rõ vào manifest)")
    parser.add_argument("--include-analysis-lane-eligibility", action="store_true",
                        help="Opt-in, disabled by default (Phase 5A): attach"
                             " tickers[ticker].analysis_lane_eligibility from"
                             " analysis_lane_eligibility.evaluate_ticker_lanes() per ticker."
                             " Not enabled in any default/production invocation.")
    parser.add_argument("--include-dnse-foreign-flow", action="store_true",
                        help="Opt-in, disabled by default: attach tickers[ticker].foreign_flow"
                             " from the retained DNSE foreign-investor VALUE store"
                             " (dnse_foreign_flow_store.build_series()) -- qualified"
                             " foreign_buy_value_vnd/foreign_sell_value_vnd/foreign_net_value_vnd"
                             " per session, plus fail-closed multi-session summaries. Foreign"
                             " volume and foreign room are never included (unqualified by"
                             " contract). Currently retained for HPG,VNM,QNS only; other"
                             " tickers report status=\"missing\". Not enabled in any"
                             " default/production invocation.")
    parser.add_argument("--include-current-state-market-risk", action="store_true",
                        help="Opt-in, disabled by default: attach"
                             " tickers[ticker].current_state_market_risk from"
                             " dnse_current_state_market_risk.py -- HPG-vs-VNINDEX"
                             " current-state (never point-in-time) beta/correlation,"
                             " reusing the two already-retained DNSE probe-evidence"
                             " files (no live network call, no formula recomputed"
                             " here). Currently qualified for HPG only; every other"
                             " ticker reports status=\"not_qualified\", never a"
                             " fabricated beta/correlation. Distinct from the"
                             " pre-existing tickers[ticker].risk_analysis.market_risk"
                             " (point-in-time). Not enabled in any default/production"
                             " invocation.")
    parser.add_argument("--include-canonical-financial-facts", action="store_true",
                        help="Opt-in, disabled by default (P1E): attach"
                             " tickers[ticker].canonical_financial_facts from the market-wide"
                             " canonical fact store, with per-metric status, provenance,"
                             " period, scope, unit, basis and limitations, plus EBITDA/EV/"
                             "EV-EBITDA/P-E/P-B/ROE readiness. Additive only; no legacy field"
                             " is read or written. Not enabled in any default/production"
                             " invocation.")
    parser.add_argument("--include-pillar-a-research-projection", action="store_true",
                        help="Opt-in: project existing Pillar A canonical facts into the historical"
                             " research source-selection contract. Requires no provider call and admits"
                             " only the existing fully-qualified corporate metric set; provider_reported"
                             " and conflicted facts remain non-research evidence.")
    parser.add_argument("--include-fundamental-quality-evidence", action="store_true",
                        help="Opt-in, disabled by default (Phase 6A): attach"
                             " tickers[ticker].fundamental_quality_evidence from"
                             " fundamental_quality_evidence.build_fundamental_quality_evidence_for_ticker()"
                             " per ticker. Distinct from the pre-existing, always-on"
                             " tickers[ticker].fundamental_quality field. Not enabled in any"
                             " default/production invocation.")
    parser.add_argument("--include-historical-decision-analysis", action="store_true",
                        help="Opt-in, disabled by default (Phase 4B): attach deterministic historical-only"
                             " decision analysis for HPG, VNM, and VCB from existing qualified/canonical"
                             " bundle sections. No valuation, recommendation, ranking, or market claim.")
    parser.add_argument("--include-portfolio-risk-analysis", action="store_true", help="Opt-in Phase 4C historical risk/liquidity/portfolio-fit gate for the three pilots; requires --include-historical-decision-analysis.")
    parser.add_argument("--include-historical-scaleout", action="store_true", help="Opt-in Phase 5A bounded deterministic qualified cohort scale-out.")
    parser.add_argument("--include-qualified-research-brief", action="store_true", help="Opt-in Phase 5B compact Producer-owned brief for HPG,VNM,VCB.")
    parser.add_argument("--include-qualified-research-delta", action="store_true", help="Opt-in Phase 5D deterministic comparison against the explicit --qualified-research-delta-previous bundle; no live data or filesystem-time selection.")
    parser.add_argument("--qualified-research-delta-previous", metavar="BUNDLE_PATH", help="Explicit frozen previous analysis_bundle.json used only with --include-qualified-research-delta.")
    parser.add_argument("--previous-qualified-research-snapshot", metavar="SNAPSHOT_ID", help="Explicit immutable Phase 5E previous snapshot ID; never selects a latest snapshot.")
    parser.add_argument("--research-changes-v2-baseline", metavar="PATH", help="Explicit previous-served V2 snapshot; attaches only deterministic Producer research changes.")
    parser.add_argument("--include-qualified-market-observations", action="store_true",
                        help="Opt-in: attach provider-scoped descriptive/technical price and volume"
                             " observations (qualified_market_observations) for every ticker with a"
                             " single-provider retained OHLCV window, gated through"
                             " market_basis_capability_registry. Always historical_only,"
                             " is_actionable=False, liquidity_actionable=False; never a generic price"
                             " or volume basis claim. Not restricted to the fundamental-evidence pilot set.")
    parser.add_argument("--qualified-research-snapshot-store-root", metavar="PATH", help="Store root required only with --previous-qualified-research-snapshot.")
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

        freshness = check_freshness(categories, prior_session, reference_session=latest_session)
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
                req_sess = item.get("reference_session_required") or item.get("prior_session_required")
                print(f"   - lệch phiên: {item['category']}: {item['date']}"
                     f" (cần {req_sess})", file=sys.stderr)
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
        opportunity_ranking = build_opportunity_ranking_contract(rank_opportunities(entries))
    finally:
        conn.close()

    generated_at = reference_at.isoformat(timespec="seconds")
    price_basis = build_price_basis_contract()
    breadth_freshness = freshness_envelope(domain="daily_market", as_of_date=breadth_info.get("data_date"), generated_at=breadth_info.get("source_generated_at"), source=MARKET_BREADTH_PATH, reference_at=reference_at)
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
    output_dir = resolve_output_dir(args.output_dir)
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
        context_package = load_context_package_full(tk)
        basis_conflicts = context_package_basis_conflicts(context_package, price_basis)
        if basis_conflicts:
            entry["context_package"] = None
            entry.setdefault("warnings", []).append(
                "context_package_basis_mismatch_fail_closed:" + ",".join(basis_conflicts)
            )
        else:
            entry["context_package"] = context_package
        raw_news = (
            (entry["context_package"] or {}).get("news_summary")
            if entry["context_package"] else None
        )
        if isinstance(raw_news, dict):
            news_related = dict(raw_news)
            news_related["news_window_semantics"] = build_news_window_semantics(raw_news)
            entry["news_related"] = news_related
        else:
            entry["news_related"] = None
        if entry["context_package"] is None:
            entry.setdefault("warnings", []).append(
                "khong_co_context_package (chưa build_ticker_context.py cho mã này -> thiếu"
                " news_related/shareholder/valuation_inputs chi tiết)")
        bundle_entries[tk] = entry

    # Generated statement-taxonomy sidecar: read-only, and optional by construction. A
    # missing, malformed, or session-mismatched sidecar yields no taxonomy evidence at all,
    # which leaves the Altman gate on insufficient_evidence rather than on an assumed
    # archetype. A stale sidecar is treated as absent rather than silently bound into the
    # session proof -- an exact-session artifact set must not carry a previous session's
    # generated evidence.
    taxonomy_sidecar = load_taxonomy_sidecar(runtime_root())
    if taxonomy_sidecar is not None:
        sidecar_session = str(taxonomy_sidecar.get("session_identity") or "")
        if sidecar_session != str(latest_session):
            data_quality_flags = data_quality_flags + [_make_flag(
                scope="pipeline", ticker=None, severity="warning",
                code="statement_taxonomy_sidecar_session_mismatch",
                detail=(f"{TAXONOMY_SIDECAR_FILENAME} is bound to session {sidecar_session!r}"
                        f" but this export references session {latest_session!r}; the sidecar"
                        " was ignored and no generated taxonomy evidence was applied."),
                metric="statement_taxonomy", evidence={"sidecar_session_identity": sidecar_session,
                                                       "export_session_identity": latest_session},
                consumer_action=("Rebuild the sidecar for the current session with"
                                 " tools/build_statement_taxonomy_sidecar.py, then re-export."),
            )]
            taxonomy_sidecar = None
    attach_distribution_evidence(bundle_entries, runtime_root(), args.include_analysis_lane_eligibility)
    # Own dedicated flag, not reused from an unrelated concept -- unlike distribution_evidence
    # this does not need to run before any other attach step; order relative to the others
    # does not matter since nothing else reads tickers[ticker].foreign_flow.
    attach_dnse_foreign_flow(bundle_entries, runtime_root(), args.include_dnse_foreign_flow,
                             reference_session_date=latest_session)
    # Own dedicated flag; order relative to the others does not matter since
    # nothing else reads tickers[ticker].current_state_market_risk.
    attach_current_state_market_risk(bundle_entries, runtime_root(), args.include_current_state_market_risk,
                                     reference_session_date=latest_session)
    attach_analysis_lane_eligibility(bundle_entries, price_basis, args.include_analysis_lane_eligibility)
    # P1E: opt-in market-wide canonical financial facts, disabled by default. With the flag
    # unset nothing is read from the canonical fact store and no key is added, so the default
    # bundle -- and therefore the exact-session proof that hash-binds it -- is unchanged.
    attach_canonical_financial_facts(bundle_entries, runtime_root(),
                                     args.include_canonical_financial_facts or args.include_pillar_a_research_projection,
                                     session_date=latest_session,
                                     price_basis_verified=price_basis.get("price_basis_verified") is True)
    pillar_a_research_coverage = attach_pillar_a_research_projection(
        bundle_entries, runtime_root(), args.include_pillar_a_research_projection,
    )
    pillar_a_eligible_tickers = [
        ticker for ticker, entry in bundle_entries.items()
        if isinstance(entry, Mapping)
        and isinstance(entry.get("research_financial_fact_projection"), Mapping)
        and entry["research_financial_fact_projection"].get("research_eligible") is True
    ]
    attach_fundamental_quality_evidence(bundle_entries, runtime_root(),
                                        args.include_fundamental_quality_evidence or args.include_pillar_a_research_projection,
                                        taxonomy_sidecar=taxonomy_sidecar)
    attach_historical_decision_analysis(bundle_entries,
                                        args.include_historical_decision_analysis or args.include_pillar_a_research_projection,
                                        additional_tickers=set(pillar_a_eligible_tickers) | _LEGACY_QUALIFIED_RESEARCH_TICKERS,
                                        runtime_root_path=runtime_root())
    attach_portfolio_risk_analysis(bundle_entries, price_basis, args.include_portfolio_risk_analysis)
    attach_qualified_market_observations(bundle_entries, args.include_qualified_market_observations)
    scaleout_coverage = attach_historical_scaleout(bundle_entries, price_basis) if args.include_historical_scaleout else None
    if args.include_qualified_research_brief or args.include_qualified_research_delta or args.include_pillar_a_research_projection:
        brief_tickers = (set(_LEGACY_QUALIFIED_RESEARCH_TICKERS) | set(pillar_a_eligible_tickers)) & set(bundle_entries)
        for ticker in sorted(brief_tickers):
            entry = bundle_entries.get(ticker)
            eligibility = ((entry or {}).get("historical_decision_analysis") or {}).get("eligibility", {})
            if isinstance(entry, dict) and eligibility.get("status") in {"eligible", "partially_eligible"}:
                entry["qualified_research_brief"] = build_qualified_research_brief(ticker, entry)
    if args.include_qualified_research_delta:
        if bool(args.qualified_research_delta_previous) == bool(args.previous_qualified_research_snapshot):
            parser.error("--include-qualified-research-delta requires exactly one explicit previous bundle or previous snapshot ID")
        if args.previous_qualified_research_snapshot:
            if not args.qualified_research_snapshot_store_root:
                parser.error("--previous-qualified-research-snapshot requires --qualified-research-snapshot-store-root")
            try:
                previous_bundle = snapshot_as_bundle(args.qualified_research_snapshot_store_root, args.previous_qualified_research_snapshot)
            except (OSError, ValueError) as exc:
                parser.error(f"cannot load explicit previous research snapshot: {exc}")
        else:
            previous_path = Path(args.qualified_research_delta_previous)
            try:
                previous_bundle = json.loads(previous_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                parser.error(f"cannot load explicit previous research snapshot: {exc}")
            if not isinstance(previous_bundle, Mapping) or not isinstance(previous_bundle.get("tickers"), Mapping):
                parser.error("explicit previous research snapshot is not an analysis bundle with tickers")
        attach_qualified_research_delta(bundle_entries, previous_bundle, True)
    # Phase 6B: reconcile the legacy fundamental_quality.models.earnings_quality subsection
    # against fundamental_quality_evidence when both are present on the same entry. A no-op
    # (adds one informational limitation only) whenever the opt-in evidence contract was not
    # computed this run -- unconditional so every invocation gets the same honest labeling.
    for entry in bundle_entries.values():
        reconcile_legacy_fundamental_quality_with_qualified_evidence(entry)

    # P1.5 is a retained-contract projection.  Attach only after every optional Producer
    # contract selected for this export has been attached, so no matrix field is computed
    # twice or allowed to promote an omitted contract.
    attach_ticker_capability_matrix(bundle_entries)

    research_changes = None
    if args.research_changes_v2_baseline:
        try:
            previous_v2 = json.loads(Path(args.research_changes_v2_baseline).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"cannot load V2 research-change baseline: {exc}")
        current_v2 = build_research_snapshot_v2({"tickers": bundle_entries}, source_identity={
            "reference_session_date": latest_session, "bundle_generation": "export_ai_bundle"})
        research_changes = build_research_change_events_v2(previous_v2, current_v2)

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
        **({"research_changes": research_changes} if research_changes is not None else {}),
        **({"pillar_a_research_coverage": pillar_a_research_coverage}
           if pillar_a_research_coverage is not None else {}),
        **({"historical_scaleout_coverage": scaleout_coverage} if scaleout_coverage is not None else {}),
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
    # Session artifact set: every trusted artifact this export actually produced or is
    # binding itself to, other than bundle_manifest.json (which cannot hash itself).
    session_artifacts = {"focus_extract.json": sha256_file(out_path)}
    sidecar_file = taxonomy_sidecar_path(runtime_root())
    if taxonomy_sidecar is not None and sidecar_file.exists():
        sidecar_sha256 = sha256_file(sidecar_file)
        session_artifacts[TAXONOMY_SIDECAR_FILENAME] = sidecar_sha256
        manifest_files = manifest_files + [{
            "file": TAXONOMY_SIDECAR_FILENAME, "role": "generated_evidence",
            "row_or_record_count": len(taxonomy_sidecar.get("records") or []),
            "count_basis": "tickers_classified",
            "data_date": taxonomy_sidecar.get("session_identity"),
            "sha256": sidecar_sha256,
        }]
    trusted_subset = build_trusted_subset_proof(
        tickers, latest_session, generated_at, sha256_file(bundle_path), bundle_entries, price_basis,
        session_artifacts=session_artifacts,
    )
    manifest = {
        "schema_version": "1.1.0",
        "producer_contract_version": PRODUCER_BUNDLE_CONTRACT_VERSION,
        "trusted_artifact_namespace": list(TRUSTED_ARTIFACT_NAMESPACE),
        "statement_taxonomy_sidecar": {
            "present": taxonomy_sidecar is not None,
            "records_fingerprint": (taxonomy_sidecar or {}).get("records_fingerprint"),
            "input_fingerprint": (taxonomy_sidecar or {}).get("input_fingerprint"),
            "session_identity": (taxonomy_sidecar or {}).get("session_identity"),
            "authority_level": "generated_evidence",
        },
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
        "trusted_subset": trusted_subset,
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
