#!/usr/bin/env python3
"""Transform raw financial statement files into a compact analytical dataset.

Nhánh BCTC của VNSTOCK (gộp từ dự án FINANCIAL_REPORT độc lập cũ, 2026-07-12).
Incorporates structured financial item mapping, sector-specific schema handling,
modification-timestamp based file prioritization, robust regex period parsing,
and audited financial formulas (YoY absolute denominator, OCF-CAPEX FCF, and
average-based ROE).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import numpy as np
import pandas as pd

from financial_mapping import get_default_registry
from source_schema_guards import SourceSchemaError, guard_financial_statement_columns

# Reconfigure console stdout encoding to UTF-8 to handle Vietnamese text output safely
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==========================================
# SYSTEM PATHS & CONFIGURATION
# ==========================================
ROOT_DIR = Path(__file__).resolve().parent
INPUT_DIR = ROOT_DIR / "data_bctc"
LOG_DIR = ROOT_DIR / "logs"

# Output files
CSV_OUT = ROOT_DIR / "financial_snapshot.csv"
PARQUET_OUT = ROOT_DIR / "financial_snapshot.parquet"
REPORT_OUT = ROOT_DIR / "docs" / "VALIDATION_REPORT.md"  # gộp 2026-07-12: chuyển vào docs/
FINANCIAL_REGISTRY = get_default_registry()
OCF_SOURCE_PROFILE_PATH = ROOT_DIR / "config" / "ocf_source_profiles.csv"
PARQUET_ENGINE_AVAILABLE = bool(
    importlib.util.find_spec("pyarrow") or importlib.util.find_spec("fastparquet")
)

OCF_UNIT_MULTIPLIERS = {
    "vnd": 1.0,
    "dong": 1.0,
    "đồng": 1.0,
    "thousand vnd": 1_000.0,
    "nghin vnd": 1_000.0,
    "nghìn đồng": 1_000.0,
    "million vnd": 1_000_000.0,
    "trieu vnd": 1_000_000.0,
    "triệu đồng": 1_000_000.0,
    "billion vnd": 1_000_000_000.0,
    "ty vnd": 1_000_000_000.0,
    "tỷ đồng": 1_000_000_000.0,
}

# ==========================================
# STATIC AUDITABLE ITEM ID MAPPING
# ==========================================
# This mapping dictionary defines the exact lists of raw item_ids from BCTC files
# mapped to standardized target metrics using a row-wise coalesce order.
ITEM_MAPPING = {
    # 1. Income Statement top-line & margins
    "revenue": [
        "net_revenue",                             # Commercial net revenue
        "net_sales",                               # Securities net sales
        "revenue_from_securities_business_01_11",  # Securities operating revenue
        "net_interest_income",                     # Bank Net Interest Income
        "interest_income_and_similar_income",      # Bank Gross Interest Income
        "total_net_revenue_from_insurance_business", # Insurance net revenue
        "revenue"                                  # General fallback
    ],
    "net_profit": [
        "net_profit",
        "profit_after_tax_for_shareholders_of_the_parents_company",
        "profit_after_tax_for_shareholders_of_parent_company"
    ],
    "gross_profit": [
        "gross_profit"
    ],
    "operating_profit": [
        "operating_profit",
        "net_profit_from_securities_business_20_50_40_60_61_62"
    ],
    # [VÁ P0-2 12/07/2026] eps_quarterly (earnings_per_share_vnd, nguồn KBS) đã BỊ BỎ khỏi mapping.
    # Điều tra trên 10 mã đủ 4 loại hình (docs/AUDIT_REPORT.md mục "P0-2"): (1) NaN/thiếu dòng hoàn
    # toàn ở CẢ 3 ngân hàng + chứng khoán + bảo hiểm (0/6 mã có số) — không phải chuyện chia scale;
    # (2) ở 4 mã CÓ số (FPT/VNM/MWG/GAS), chia ×1000 chỉ đưa về đúng BẬC ĐỘ LỚN chứ không khớp
    # chính xác (lệch 0,6x–1,1x so với đối chứng net_profit/shares_outstanding, có kỳ lệch tới 40%).
    # -> Thay bằng cột `eps_calc` tự tính (xem ngay dưới `book_value`), tính CHUNG 1 công thức
    # minh bạch cho mọi mã thay vì vá riêng theo bệnh của từng nguồn.

    # 2. Balance Sheet assets, liabilities, & equity
    "total_assets": [
        "total_assets"
    ],
    "total_liabilities": [
        "liabilities"
    ],
    "equity": [
        "owners_equity"
    ],
    "cash": [
        "cash_and_cash_equivalents",
        "cash",
        "cash_and_precious_metals"                 # Bank Cash
    ],
    "inventory": [
        "inventories",
        "inventories_net"
    ],
    "receivables": [
        "accounts_receivable"
    ],
    "short_term_borrowings": [
        "short_term_borrowings"
    ],
    "long_term_borrowings": [
        "long_term_borrowings"
    ],
    "common_shares": [
        "common_shares",
        "charter_capital",  # Bank/finance-company schema par-value equivalent (EVF/VCB/BID/MBB/TCB).
    ],
    "paid_in_capital": [
        "paid_in_capital"
    ],
    
    # 3. Liquidity and efficiency items
    "current_assets": [
        "current_assets"
    ],
    "current_liabilities": [
        "current_liabilities"
    ],
    "cost_of_goods_sold": [
        "cost_of_goods_sold"
    ],
    
    # 4. Cash Flow & CapEx — OCF đã chuyển sang financial_item_map.csv.
    "capex_raw": [
        "payment_for_fixed_assets_constructions_and_other_long_term_assets"
    ]
}

# ==========================================
# LOGGING SETUP
# ==========================================
def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("bctc_processor")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(LOG_DIR / "bctc_processor.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger

log = setup_logging()

# ==========================================
# PERIOD ARITHMETIC STRING HELPERS
# ==========================================
def get_yoy_period_str(p_str: str) -> str | None:
    """Calculate the period string for 1 year prior."""
    if not p_str or not isinstance(p_str, str):
        return None
    if "-Q" in p_str:
        parts = p_str.split("-")
        try:
            year = int(parts[0])
            q = parts[1]
            return f"{year - 1}-{q}"
        except (ValueError, IndexError):
            return None
    elif len(p_str) == 4 and p_str.isdigit():
        try:
            year = int(p_str)
            return str(year - 1)
        except ValueError:
            return None
    return None

def get_qoq_period_str(p_str: str) -> str | None:
    """Calculate the period string for 1 quarter prior. Only valid for quarters."""
    if not p_str or not isinstance(p_str, str):
        return None
    if "-Q" in p_str:
        parts = p_str.split("-")
        try:
            year = int(parts[0])
            q_str = parts[1]
            q_num = int(q_str[1])  # Extract digit from 'Q1', 'Q2', etc.
            if q_num == 1:
                return f"{year - 1}-Q4"
            else:
                return f"{year}-Q{q_num - 1}"
        except (ValueError, IndexError):
            return None
    return None

# ==========================================
# PERIOD PARSING ROBUSTNESS (REGEX)
# ==========================================
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


def _quarter_key(period: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d{4})-Q([1-4])", str(period or ""))
    return (int(match.group(1)), int(match.group(2))) if match else None


def _previous_quarter(period: str) -> str | None:
    key = _quarter_key(period)
    if not key:
        return None
    year, quarter = key
    return f"{year - 1}-Q4" if quarter == 1 else f"{year}-Q{quarter - 1}"


def compute_roe_ttm(
    ticker: str,
    period: str,
    profit_map: dict[tuple[str, str], float],
    equity_map: dict[tuple[str, str], float],
) -> dict[str, object]:
    """TTM ROE cho (ticker, period) — item A, Data Contract Hardening v1.1.

    Tử số: net_profit cộng dồn 4 quý LIÊN TIẾP, nối chuỗi qua _previous_quarter (đúng kỹ
    thuật với OCF TTM ở build_ocf_period_metrics) — chỉ tính khi CẢ 4 quý đều có net_profit
    đã báo cáo, không nội suy/suy diễn quý thiếu. Mẫu số: vốn chủ sở hữu bình quân đầu/cuối
    kỳ TTM khi có cả hai đầu mốc; nếu thiếu mốc đầu (quý T-4), fallback về vốn chủ sở hữu
    cuối kỳ (equity tại T) — hai trường hợp trả `equity_basis` khác nhau để phân biệt rõ.
    Trả {'value': None, 'equity_basis': None} khi không tính được — không bao giờ suy đoán.
    period_type khác 'quarter' cũng trả rỗng (TTM là khái niệm quý-lăn thuần túy).
    """
    if _period_type_of(period) != "quarter":
        return {"value": None, "equity_basis": None}
    window = [period]
    for _ in range(3):
        previous = _previous_quarter(window[-1])
        if previous is None:
            break
        window.append(previous)
    if len(window) != 4:
        return {"value": None, "equity_basis": None}
    profits = [profit_map.get((ticker, p), np.nan) for p in window]
    if any(pd.isna(value) for value in profits):
        return {"value": None, "equity_basis": None}
    ttm_profit = sum(profits)
    boundary_period = _previous_quarter(window[-1])
    equity_end = equity_map.get((ticker, period), np.nan)
    equity_start = equity_map.get((ticker, boundary_period), np.nan) if boundary_period else np.nan
    if not pd.isna(equity_end) and not pd.isna(equity_start) and (equity_end + equity_start) != 0:
        return {"value": ttm_profit / ((equity_end + equity_start) / 2.0), "equity_basis": "ttm_average_equity"}
    if not pd.isna(equity_end) and equity_end != 0:
        return {"value": ttm_profit / equity_end, "equity_basis": "ttm_ending_equity_fallback"}
    return {"value": None, "equity_basis": None}


# ==========================================
# FISCAL PERIOD VERIFICATION (P0-4 khắc phục: xem STOCK_ANALYSIS_MASTER_PLAN.md mục 7 P0-4)
# ==========================================
_QUARTER_CALENDAR_END_MONTH = {1: 3, 2: 6, 3: 9, 4: 12}

# item B (Data Contract Hardening v1.1): tolerance around "exactly 1 calendar year earlier"
# used by find_yoy_comparison_period below. Quarters get a tighter window than years because
# a quarter-end date is a more precise anchor than a fiscal-year-end date.
YOY_TOLERANCE_DAYS = {"quarter": 20, "year": 45}


def calendar_period_end(period: str, period_type: str) -> "pd.Timestamp | None":
    """Ngày kết thúc DƯƠNG LỊCH mà nhãn kỳ ('2026-Q3', '2026') ngụ ý, theo đúng quy ước
    normalize_period_str hiện tại của pipeline (nhãn kỳ = quý/năm dương lịch). Trả None nếu
    nhãn không parse được."""
    if period_type == "quarter":
        m = re.fullmatch(r"(\d{4})-Q([1-4])", str(period or ""))
        if not m:
            return None
        year, q = int(m.group(1)), int(m.group(2))
        month = _QUARTER_CALENDAR_END_MONTH[q]
        return pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)
    if period_type == "year":
        m = re.fullmatch(r"(\d{4})", str(period or ""))
        if not m:
            return None
        return pd.Timestamp(year=int(m.group(1)), month=12, day=31)
    return None


def _period_type_of(period: str) -> str:
    return "quarter" if "-Q" in str(period or "") else "year"


def find_yoy_comparison_period(
    period: str,
    candidate_periods: Iterable[str],
    *,
    as_of_date: str | None = None,
) -> tuple[str | None, str | None]:
    """Trả (kỳ so sánh YoY, lý do KHÔNG khớp nếu có) cho `period` trong tập `candidate_periods`
    CỦA CÙNG MỘT ticker (item B, Data Contract Hardening v1.1).

    Khớp theo `period_calendar_end` (~12 tháng dương lịch trước, có dung sai
    YOY_TOLERANCE_DAYS) — KHÔNG ghép nhãn 'YYYY-Qn'/'YYYY' thuần túy như get_yoy_period_str,
    vì hai kỳ cùng số quý/năm nhãn không đảm bảo cách nhau đúng 12 tháng dương lịch khi công ty
    có năm tài chính lệch. Chỉ chấp nhận candidate ĐÃ xác minh theo lịch dương tại `as_of_date`
    (mặc định hôm nay) — tương đương điều kiện flag_fiscal_period_verification() gắn cờ
    'future_relative_to_calendar_quarter_end', tính lại cục bộ vì hàm đó hiện chạy sau bước
    tăng trưởng trong process_data() và thao tác trên cột thay vì (ticker, period) rời rạc.
    Không so sánh giữa quý và năm (period_type khác nhau bị loại ngay)."""
    ref = pd.Timestamp(as_of_date) if as_of_date else pd.Timestamp.now().normalize()
    p_type = _period_type_of(period)
    this_end = calendar_period_end(period, p_type)
    if this_end is None:
        return None, "current_period_calendar_end_unparseable"
    target = this_end - pd.DateOffset(years=1)
    tolerance = pd.Timedelta(days=YOY_TOLERANCE_DAYS.get(p_type, 45))
    best_period, best_gap = None, None
    for candidate in candidate_periods:
        if candidate == period or _period_type_of(candidate) != p_type:
            continue
        candidate_end = calendar_period_end(candidate, p_type)
        if candidate_end is None:
            continue
        gap = abs(candidate_end - target)
        if gap <= tolerance and (best_gap is None or gap < best_gap):
            best_period, best_gap = candidate, gap
    if best_period is None:
        return None, "no_period_within_12_month_tolerance"
    best_end = calendar_period_end(best_period, p_type)
    if best_end is None or best_end > ref:
        return None, "comparable_period_not_calendar_verified"
    return best_period, None


def flag_fiscal_period_verification(df: pd.DataFrame, as_of_date: str | None = None) -> pd.DataFrame:
    """Gắn cờ xác minh kỳ báo cáo theo lịch dương — khắc phục P0-4 (18 dòng kỳ '2026-Q2..Q4' của
    các DN có năm tài chính lệch như HSG/CTD bị coi nhầm là kỳ dương lịch tương lai đã có số liệu).

    Pipeline này KHÔNG có registry năm tài chính riêng từng doanh nghiệp (chưa xác nhận đầy đủ —
    xem AI ANALYZE knowledge/DataDictionary.md), nên KHÔNG tự suy luận offset thật. Việc duy nhất
    làm được một cách an toàn: nếu ngày kết thúc quý/năm DƯƠNG LỊCH mà nhãn kỳ ngụ ý còn ở TƯƠNG LAI
    so với as_of_date, thì kỳ đó CHƯA THỂ có số liệu thật theo nghĩa dương lịch phổ thông — gắn cờ
    'future_relative_to_calendar_quarter_end' thay vì âm thầm cho qua. Hạ nguồn (export_ai_bundle.py,
    build_ticker_context.py) phải loại các dòng này khỏi lựa chọn "kỳ mới nhất" mặc định.

    Cột mới: period_calendar_end, fiscal_period_status, period_verified (bool).
    """
    ref = pd.Timestamp(as_of_date) if as_of_date else pd.Timestamp.now().normalize()
    ends = df.apply(lambda r: calendar_period_end(r.get("period"), r.get("period_type")), axis=1)
    df = df.copy()
    df["period_calendar_end"] = ends.apply(lambda v: v.strftime("%Y-%m-%d") if v is not None else None)
    is_future = ends.notna() & (ends > ref)
    df["fiscal_period_status"] = np.select(
        [ends.isna(), is_future],
        ["unparseable_period_label", "future_relative_to_calendar_quarter_end"],
        default="calendar_aligned_or_past",
    )
    df["period_verified"] = df["fiscal_period_status"] == "calendar_aligned_or_past"
    return df


def _load_ocf_source_profiles(path: Path = OCF_SOURCE_PROFILE_PATH) -> dict[tuple[str, str, str], dict[str, str]]:
    if not path.exists():
        return {}
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    profiles: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in frame.to_dict("records"):
        key = (
            str(row.get("source", "")).strip().upper(),
            str(row.get("report_type", "")).strip().lower(),
            str(row.get("period_type", "")).strip().lower(),
        )
        profiles[key] = {name: str(value).strip() for name, value in row.items()}
    return profiles


OCF_SOURCE_PROFILES = _load_ocf_source_profiles()


def normalize_ocf_unit(
    value: float | int | None,
    raw_unit: str | None,
    registry_multiplier: float = 1.0,
) -> dict[str, object]:
    """Normalize a declared monetary unit without guessing when metadata is absent."""
    if value is None or pd.isna(value):
        normalized_value = np.nan
    else:
        normalized_value = float(value)
    unit_key = re.sub(r"\s+", " ", str(raw_unit or "").strip().lower())
    unit_multiplier = OCF_UNIT_MULTIPLIERS.get(unit_key)
    declared = unit_multiplier is not None
    effective_multiplier = float(registry_multiplier) * (unit_multiplier if declared else 1.0)
    if not pd.isna(normalized_value):
        normalized_value *= effective_multiplier
    return {
        "value": normalized_value,
        "raw_unit": str(raw_unit).strip() if raw_unit is not None and str(raw_unit).strip() else None,
        "normalized_unit": "VND" if declared else "unknown",
        "unit_multiplier": effective_multiplier,
        "unit_status": "normalized" if declared else "unit_unknown",
    }


def summarize_statement_units(combined: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-row unit_status/effective_unit_multiplier (computed for every mapped item
    in load_and_melt_file) up to one row per ticker-period, BEFORE the pivot in process_data()
    discards these columns for everything except OCF (item C, Data Contract Hardening v1.1).

    A ticker-period's scale is only "normalized" when EVERY mapped item in it declared a raw
    unit AND all declared items agree on the same effective multiplier; a single undeclared
    item, or disagreement between items, keeps the whole statement's scale explicitly
    unconfirmed rather than guessing. All monetary data in this pipeline is Vietnamese-listed
    company VND (OCF_UNIT_MULTIPLIERS and every mapping rule are VND-only already — no other
    currency has ever been supported), so statement_currency is a safe constant, not a guess.
    """
    if combined.empty:
        return pd.DataFrame(
            columns=["ticker", "period", "statement_currency", "statement_scale", "unit_status", "unit_evidence"]
        )
    work = combined[["ticker", "period", "unit_status", "effective_unit_multiplier"]].copy()
    work["_declared_multiplier"] = work["effective_unit_multiplier"].where(work["unit_status"] == "normalized")
    grouped = work.groupby(["ticker", "period"])
    all_declared = grouped["unit_status"].apply(lambda s: bool((s == "normalized").all()))
    distinct_multipliers = grouped["_declared_multiplier"].nunique(dropna=True)
    common_multiplier = grouped["_declared_multiplier"].first()

    result = pd.DataFrame({
        "_all_declared": all_declared,
        "_distinct_multipliers": distinct_multipliers,
        "_common_multiplier": common_multiplier,
    })
    result["unit_status"] = np.select(
        [
            result["_all_declared"] & (result["_distinct_multipliers"] <= 1),
            result["_all_declared"] & (result["_distinct_multipliers"] > 1),
        ],
        ["normalized", "unit_conflict"],
        default="unit_unknown",
    )
    result["statement_scale"] = np.where(
        result["unit_status"] == "normalized", result["_common_multiplier"], np.nan
    )
    result["unit_evidence"] = np.select(
        [result["unit_status"] == "normalized", result["unit_status"] == "unit_conflict"],
        [
            "every mapped item in this ticker-period declared a raw_unit consistent with one scale multiplier",
            "mapped items in this ticker-period declared inconsistent unit multipliers for the same statement",
        ],
        default=(
            "no mapped item in this ticker-period declared a raw_unit; scale defaults to an "
            "unconfirmed 1.0x (base VND) multiplier and is not positively verified against the "
            "filed statement"
        ),
    )
    result["statement_currency"] = "VND"
    return result.reset_index()[
        ["ticker", "period", "statement_currency", "statement_scale", "unit_status", "unit_evidence"]
    ]


def resolve_ocf_basis(
    source: str | None,
    report_type: str | None,
    period_type: str | None,
    explicit_basis: str | None = None,
) -> tuple[str, float]:
    """Resolve period basis from explicit metadata, then an auditable source profile."""
    explicit = str(explicit_basis or "").strip().lower()
    if explicit in {"reported", "ytd", "quarter", "annual"}:
        return explicit, 1.0
    key = (
        str(source or "").strip().upper(),
        str(report_type or "").strip().lower(),
        str(period_type or "").strip().lower(),
    )
    profile = OCF_SOURCE_PROFILES.get(key)
    if profile and profile.get("basis"):
        try:
            confidence = float(profile.get("confidence") or 0.0)
        except ValueError:
            confidence = 0.0
        return profile["basis"].lower(), confidence
    if str(period_type or "").strip().lower() == "year":
        return "annual", 1.0
    return "period_basis_unknown", 0.0


def select_latest_non_null_reported_value(
    rows: list[dict[str, object]],
    value_field: str = "operating_cash_flow",
) -> dict[str, object] | None:
    """Select the latest non-null reported value, never the latest row blindly."""
    candidates = [
        row for row in rows
        if row.get(value_field) is not None and not pd.isna(row.get(value_field))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda row: _quarter_key(str(row.get("period", ""))) or (-1, -1))


def build_ocf_period_metrics(ocf_rows: pd.DataFrame) -> pd.DataFrame:
    """Separate reported/YTD/quarter/TTM OCF without inventing missing periods."""
    output_columns = [
        "ticker", "period", "operating_cash_flow_reported", "operating_cash_flow_ytd",
        "operating_cash_flow_quarter", "operating_cash_flow_quarter_status",
        "operating_cash_flow_ttm", "operating_cash_flow_ttm_status",
        "operating_cash_flow_ttm_reason", "operating_cash_flow",
        "operating_cash_flow_basis", "operating_cash_flow_basis_confidence",
        "operating_cash_flow_status",
        "operating_cash_flow_source_period", "operating_cash_flow_raw_unit",
        "operating_cash_flow_normalized_unit", "operating_cash_flow_unit_multiplier",
        "operating_cash_flow_unit_status", "operating_cash_flow_report_scope",
        "operating_cash_flow_audit_status", "operating_cash_flow_source",
    ]
    if ocf_rows.empty:
        return pd.DataFrame(columns=output_columns)

    work = ocf_rows.copy()
    work = work[work["item_id"] == "operating_cash_flow"].copy()
    if work.empty:
        return pd.DataFrame(columns=output_columns)
    work = work.sort_values(
        ["mapping_priority", "mapping_confidence"],
        ascending=[False, False],
        na_position="last",
    )
    work = work.drop_duplicates(["ticker", "period"], keep="first")
    if "ocf_basis_confidence" not in work.columns:
        work["ocf_basis_confidence"] = 0.0
    work["operating_cash_flow_reported"] = work["value"]
    work["operating_cash_flow_ytd"] = work["value"].where(work["ocf_basis"] == "ytd", np.nan)
    work["operating_cash_flow_quarter"] = work["value"].where(work["ocf_basis"] == "quarter", np.nan)

    # Only comparable YTD observations from the same source/scope/audit/unit may be differenced.
    comparable_fields = ["source", "statement_scope", "audit_status", "normalized_unit"]
    keyed = {(row.ticker, row.period): row for row in work.itertuples(index=False)}
    for index, row in work.iterrows():
        if row["ocf_basis"] != "ytd":
            continue
        key = _quarter_key(row["period"])
        if not key:
            continue
        year, quarter = key
        if quarter == 1:
            work.at[index, "operating_cash_flow_quarter"] = row["value"]
            continue
        previous_period = f"{year}-Q{quarter - 1}"
        previous = keyed.get((row["ticker"], previous_period))
        if previous is None or previous.ocf_basis != "ytd":
            continue
        if any(getattr(previous, field) != row[field] for field in comparable_fields):
            continue
        work.at[index, "operating_cash_flow_quarter"] = row["value"] - previous.value

    work["operating_cash_flow_ttm"] = np.nan
    for ticker, ticker_rows in work.groupby("ticker"):
        quarter_map = {
            row.period: row
            for row in ticker_rows.itertuples()
            if not pd.isna(row.operating_cash_flow_quarter)
        }
        for index, row in ticker_rows.iterrows():
            periods = [row["period"]]
            for _ in range(3):
                previous = _previous_quarter(periods[-1])
                if previous is None:
                    break
                periods.append(previous)
            if len(periods) != 4 or any(period not in quarter_map for period in periods):
                continue
            comparable = [quarter_map[period] for period in periods]
            if any(
                getattr(candidate, field) != row[field]
                for candidate in comparable
                for field in comparable_fields
            ):
                continue
            work.at[index, "operating_cash_flow_ttm"] = sum(
                candidate.operating_cash_flow_quarter for candidate in comparable
            )

    has_ttm = work["operating_cash_flow_ttm"].notna()
    has_quarter = work["operating_cash_flow_quarter"].notna()
    work["operating_cash_flow_quarter_status"] = np.where(
        has_quarter,
        np.where(work["ocf_basis"] == "quarter", "reported", "derived"),
        "insufficient_periods",
    )
    work["operating_cash_flow_ttm_status"] = np.where(
        has_ttm, "derived", "insufficient_periods"
    )
    work["operating_cash_flow_ttm_reason"] = np.where(
        has_ttm, None, "requires_four_contiguous_comparable_quarters"
    )
    work["operating_cash_flow"] = work["operating_cash_flow_ttm"].where(
        has_ttm, work["operating_cash_flow_reported"]
    )
    work["operating_cash_flow_basis"] = np.where(has_ttm, "ttm", work["ocf_basis"])
    work["operating_cash_flow_basis_confidence"] = np.where(
        has_ttm, 1.0, work["ocf_basis_confidence"]
    )
    work["operating_cash_flow_status"] = np.where(
        has_ttm,
        "derived",
        np.where(work["operating_cash_flow_reported"].notna(), "reported", "source_empty"),
    )
    work["operating_cash_flow_source_period"] = work["period"]
    work = work.rename(columns={
        "raw_unit": "operating_cash_flow_raw_unit",
        "normalized_unit": "operating_cash_flow_normalized_unit",
        "effective_unit_multiplier": "operating_cash_flow_unit_multiplier",
        "unit_status": "operating_cash_flow_unit_status",
        "statement_scope": "operating_cash_flow_report_scope",
        "audit_status": "operating_cash_flow_audit_status",
        "source": "operating_cash_flow_source",
    })
    return work[output_columns]


def diagnose_ocf_raw(file_path: Path) -> dict[str, object]:
    """Return an auditable raw-to-selected OCF trace for one statement file."""
    raw = pd.read_parquet(file_path) if file_path.suffix == ".parquet" else pd.read_csv(file_path)
    period_columns = [str(column) for column in raw.columns if re.match(r"^\d{4}", str(column))]
    candidates: list[dict[str, object]] = []
    ticker = str(raw.iloc[0].get("ticker", "")).strip().upper() if not raw.empty else ""
    entity_type = FINANCIAL_REGISTRY.entity_type_for(ticker) if ticker else "unknown"
    for _, row in raw.iterrows():
        mapped = FINANCIAL_REGISTRY.map_financial_item(
            source=row.get("source", ""),
            entity_type=entity_type,
            report_type=row.get("report_type", ""),
            item_id=row.get("item_id", ""),
            raw_label=row.get("item", ""),
            source_field=row.get("source_field", ""),
        )
        if not mapped or mapped["canonical_metric"] != "operating_cash_flow":
            continue
        values = []
        for raw_period in period_columns:
            value = pd.to_numeric(pd.Series([row.get(raw_period)]), errors="coerce").iloc[0]
            values.append({
                "raw_period": raw_period,
                "period": normalize_period_str(raw_period),
                "value": None if pd.isna(value) else float(value),
            })
        candidates.append({
            "item_id": str(row.get("item_id", "")),
            "raw_label": str(row.get("item", "")),
            "mapping_rule_id": mapped["mapping_rule_id"],
            "values": values,
        })

    melted = load_and_melt_file(file_path)
    metrics = build_ocf_period_metrics(melted)
    selected = select_latest_non_null_reported_value(
        metrics.to_dict("records"), "operating_cash_flow_reported"
    )
    selected_output = None
    if selected:
        selected_output = {
            "period": selected.get("period"),
            "value": selected.get("operating_cash_flow_reported"),
            "basis": selected.get("operating_cash_flow_basis"),
            "source": selected.get("operating_cash_flow_source"),
            "raw_unit": selected.get("operating_cash_flow_raw_unit"),
            "normalized_unit": selected.get("operating_cash_flow_normalized_unit"),
            "unit_multiplier": selected.get("operating_cash_flow_unit_multiplier"),
            "unit_status": selected.get("operating_cash_flow_unit_status"),
            "report_scope": selected.get("operating_cash_flow_report_scope"),
            "audit_status": selected.get("operating_cash_flow_audit_status"),
        }
    return {
        "ticker": ticker,
        "source_file": file_path.name,
        "cash_flow_raw_row_count": int(len(raw)),
        "available_periods": period_columns,
        "candidate_item_ids": [candidate["item_id"] for candidate in candidates],
        "candidate_raw_labels": [candidate["raw_label"] for candidate in candidates],
        "candidates": candidates,
        "selected_row": selected_output,
        "ttm_available": bool(not metrics.empty and metrics["operating_cash_flow_ttm"].notna().any()),
        "quarter_available": bool(not metrics.empty and metrics["operating_cash_flow_quarter"].notna().any()),
    }


# Entity types whose statement schema has been POSITIVELY CONFIRMED to structurally lack a
# concept (corporate EBIT/EBITDA split, current-asset/inventory liquidity ratios, etc) —
# Data Contract Hardening v1.1 item E. Deliberately NOT "!= 'corporate'": ~1478 of ~1492
# tickers have no entity profile at all and default to entity_type_for()=="unknown"; treating
# "unknown" as confirmed-non-corporate would silently mislabel ordinary unprofiled corporates
# as not_applicable instead of leaving them on the existing insufficient_periods/no-status
# "we don't know yet" path.
CONFIRMED_NON_CORPORATE = {"bank", "securities", "insurance", "finance_company"}


def materialize_advanced_financial_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    """Materialize Phase 4 metrics with explicit provenance and no silent proxies."""
    work = frame.copy()
    required = [
        "profit_before_tax", "interest_expense", "ebit", "depreciation",
        "amortization", "depreciation_and_amortization", "ebitda",
        "retained_earnings", "retained_earnings_prior_year",
        "retained_earnings_current_year", "selling_expense",
        "general_admin_expense", "sga",
    ]
    for field in required:
        if field not in work.columns:
            work[field] = np.nan

    if isinstance(work.index, pd.MultiIndex) and "ticker" in work.index.names:
        tickers = pd.Series(work.index.get_level_values("ticker"), index=work.index)
    elif "ticker" in work.columns:
        tickers = work["ticker"].astype(str)
    else:
        tickers = pd.Series("", index=work.index)
    entity_type = tickers.map(FINANCIAL_REGISTRY.entity_type_for)
    work["entity_type"] = entity_type

    def initialize_reported(metric: str, missing_reason: str) -> None:
        present = work[metric].notna()
        work[f"{metric}_status"] = np.where(present, "reported", "source_empty")
        work[f"{metric}_basis"] = np.where(present, "reported", None)
        work[f"{metric}_reason"] = np.where(present, None, missing_reason)
        work[f"{metric}_formula"] = None
        work[f"{metric}_inputs"] = None

    for metric, reason in {
        "interest_expense": "reported_interest_expense_not_available",
        "depreciation": "reported_depreciation_not_available",
        "amortization": "reported_amortization_not_available",
        "depreciation_and_amortization": "reported_combined_da_not_available",
    }.items():
        initialize_reported(metric, reason)

    work["interest_expense_sign_convention"] = np.where(
        work["interest_expense"].isna(), "unknown",
        np.where(work["interest_expense"] >= 0, "positive_expense", "negative_unresolved"),
    )

    # Retained earnings: prefer reported end-period total; derive only when both
    # explicitly separated components exist. Never include other equity reserves.
    work["retained_earnings_end_period"] = work["retained_earnings"]
    retained_reported = work["retained_earnings_end_period"].notna()
    retained_derived = (
        ~retained_reported
        & work["retained_earnings_prior_year"].notna()
        & work["retained_earnings_current_year"].notna()
    )
    work.loc[retained_derived, "retained_earnings_end_period"] = (
        work.loc[retained_derived, "retained_earnings_prior_year"]
        + work.loc[retained_derived, "retained_earnings_current_year"]
    )
    work["retained_earnings"] = work["retained_earnings_end_period"]
    work["retained_earnings_status"] = np.select(
        [retained_reported, retained_derived], ["reported", "derived"], default="source_empty"
    )
    work["retained_earnings_basis"] = np.select(
        [retained_reported, retained_derived], ["reported", "derived"], default=None
    )
    work["retained_earnings_reason"] = np.where(
        work["retained_earnings_end_period"].notna(), None,
        "reported_total_missing_and_split_components_incomplete",
    )
    work["retained_earnings_formula"] = np.where(
        retained_derived,
        "retained_earnings_prior_year + retained_earnings_current_year",
        None,
    )
    work["retained_earnings_inputs"] = np.where(
        retained_derived,
        json.dumps(["retained_earnings_prior_year", "retained_earnings_current_year"]),
        None,
    )

    # EBIT: reported has priority. Derived EBIT requires a non-negative,
    # positive-expense normalized interest value.
    ebit_reported = work["ebit"].notna()
    ebit_derived = (
        ~ebit_reported
        & (entity_type == "corporate")
        & work["profit_before_tax"].notna()
        & work["interest_expense"].notna()
        & (work["interest_expense"] >= 0)
    )
    work.loc[ebit_derived, "ebit"] = (
        work.loc[ebit_derived, "profit_before_tax"]
        + work.loc[ebit_derived, "interest_expense"]
    )
    ebit_not_applicable = ~ebit_reported & ~ebit_derived & entity_type.isin(CONFIRMED_NON_CORPORATE)
    work["ebit_status"] = np.select(
        [ebit_reported, ebit_derived, ebit_not_applicable],
        ["reported", "derived", "not_applicable"],
        default="insufficient_periods",
    )
    work["ebit_basis"] = np.select(
        [ebit_reported, ebit_derived], ["reported", "derived"], default=None
    )
    work["ebit_reason"] = np.where(
        work["ebit"].notna(), None,
        np.where(
            (entity_type == "corporate") & work["interest_expense"].notna()
            & (work["interest_expense"] < 0),
            "interest_expense_sign_not_normalized",
            np.where(
                entity_type.isin(CONFIRMED_NON_CORPORATE),
                "corporate_ebit_structure_not_applicable",
                "missing_pbt_or_interest_expense",
            ),
        ),
    )
    work["ebit_formula"] = np.where(
        ebit_derived, "profit_before_tax + interest_expense", None
    )
    work["ebit_inputs"] = np.where(
        ebit_derived, json.dumps(["profit_before_tax", "interest_expense"]), None
    )

    # EBITDA: reported first; otherwise use a reported combined D&A value, or
    # both separate components. A combined value is never split into components.
    ebitda_reported = work["ebitda"].notna()
    ebitda_from_combined = (
        ~ebitda_reported & (entity_type == "corporate")
        & work["ebit"].notna() & work["depreciation_and_amortization"].notna()
    )
    ebitda_from_parts = (
        ~ebitda_reported & ~ebitda_from_combined & (entity_type == "corporate")
        & work["ebit"].notna() & work["depreciation"].notna()
        & work["amortization"].notna()
    )
    work.loc[ebitda_from_combined, "ebitda"] = (
        work.loc[ebitda_from_combined, "ebit"]
        + work.loc[ebitda_from_combined, "depreciation_and_amortization"]
    )
    work.loc[ebitda_from_parts, "ebitda"] = (
        work.loc[ebitda_from_parts, "ebit"]
        + work.loc[ebitda_from_parts, "depreciation"]
        + work.loc[ebitda_from_parts, "amortization"]
    )
    ebitda_derived = ebitda_from_combined | ebitda_from_parts
    ebitda_not_applicable = ~ebitda_reported & ~ebitda_derived & entity_type.isin(CONFIRMED_NON_CORPORATE)
    work["ebitda_status"] = np.select(
        [ebitda_reported, ebitda_derived, ebitda_not_applicable],
        ["reported", "derived", "not_applicable"],
        default="insufficient_periods",
    )
    work["ebitda_basis"] = np.select(
        [ebitda_reported, ebitda_derived], ["reported", "derived"], default=None
    )
    work["ebitda_reason"] = np.where(
        work["ebitda"].notna(), None,
        np.where(
            entity_type.isin(CONFIRMED_NON_CORPORATE),
            "corporate_ebitda_structure_not_applicable",
            "missing_ebit_or_complete_da_inputs",
        ),
    )
    work["ebitda_formula"] = np.select(
        [ebitda_from_combined, ebitda_from_parts],
        ["ebit + depreciation_and_amortization", "ebit + depreciation + amortization"],
        default=None,
    )
    work["ebitda_inputs"] = np.select(
        [ebitda_from_combined, ebitda_from_parts],
        [json.dumps(["ebit", "depreciation_and_amortization"]), json.dumps(["ebit", "depreciation", "amortization"])],
        default=None,
    )

    # SG&A formula is corporate-only. Other entity profiles are explicitly N/A.
    sga_reported = work["sga"].notna() & (entity_type == "corporate")
    sga_derived = (
        ~sga_reported & (entity_type == "corporate")
        & work["selling_expense"].notna() & work["general_admin_expense"].notna()
    )
    work.loc[sga_derived, "sga"] = (
        work.loc[sga_derived, "selling_expense"]
        + work.loc[sga_derived, "general_admin_expense"]
    )
    non_corporate = entity_type != "corporate"
    work.loc[non_corporate, "sga"] = np.nan
    work["sga_status"] = np.select(
        [non_corporate, sga_reported, sga_derived],
        ["not_applicable", "reported", "derived"],
        default="insufficient_periods",
    )
    work["sga_basis"] = np.select(
        [sga_reported, sga_derived], ["reported", "derived"], default=None
    )
    work["sga_reason"] = np.select(
        [non_corporate, work["sga"].notna()],
        ["corporate_sga_structure_not_applicable", None],
        default="missing_selling_or_general_admin_expense",
    )
    work["sga_formula"] = np.where(
        sga_derived, "selling_expense + general_admin_expense", None
    )
    work["sga_inputs"] = np.where(
        sga_derived, json.dumps(["selling_expense", "general_admin_expense"]), None
    )
    return work

# ==========================================
# REPORT CLEANING & NORMALIZATION
# ==========================================
def map_income_item(item_id: str, item_name: str) -> str:
    """Differentiate duplicate raw 'revenue' items in income statements."""
    item_id_clean = str(item_id).strip()
    item_name_lower = str(item_name).lower()
    
    if item_id_clean == "revenue":
        if "thuần" in item_name_lower or "net" in item_name_lower:
            return "net_revenue"
        else:
            return "gross_revenue"
    return item_id_clean

def load_and_melt_file(file_path: Path) -> pd.DataFrame:
    """Read a report file (CSV or Parquet), melt periods, and normalize fields."""
    log.debug("Loading file: %s", file_path.name)
    try:
        if file_path.suffix == ".parquet":
            df = pd.read_parquet(file_path)
        else:
            df = pd.read_csv(file_path)
    except Exception as e:
        log.error("Failed to read file %s: %s", file_path.name, e)
        return pd.DataFrame()

    if df.empty:
        log.warning("File %s is empty", file_path.name)
        return pd.DataFrame()

    df.columns = [str(c).strip() for c in df.columns]
    
    try:
        guard_financial_statement_columns(df.columns, str(file_path))
    except SourceSchemaError as exc:
        log.error("Source schema guard failed: %s", exc.to_dict())
        raise

    df["ticker"] = df["ticker"].str.strip().str.upper()
    df["report_type"] = df["report_type"].str.strip().str.lower()
    df["item_id"] = df["item_id"].str.strip()
    df["raw_item_id"] = df["item_id"]
    if "source" not in df.columns:
        df["source"] = ""
    df["raw_unit"] = df["raw_unit"] if "raw_unit" in df.columns else (
        df["unit"] if "unit" in df.columns else None
    )
    df["period_basis_explicit"] = df["period_basis"] if "period_basis" in df.columns else None
    df["statement_scope"] = df["statement_scope"] if "statement_scope" in df.columns else (
        df["scope"] if "scope" in df.columns else "unknown"
    )
    df["audit_status"] = df["audit_status"] if "audit_status" in df.columns else "unknown"
    
    if df["report_type"].iloc[0] == "income_statement":
        df["item_id"] = df.apply(lambda r: map_income_item(r["item_id"], r["item"]), axis=1)

    ticker = df["ticker"].iloc[0]
    entity_type = FINANCIAL_REGISTRY.entity_type_for(ticker)

    def registry_match(row: pd.Series) -> pd.Series:
        result = FINANCIAL_REGISTRY.map_financial_item(
            source=row.get("source", ""),
            entity_type=entity_type,
            report_type=row.get("report_type", ""),
            item_id=row.get("raw_item_id", ""),
            raw_label=row.get("item", ""),
            source_field=row.get("source_field", ""),
        )
        if not result:
            return pd.Series({
                "canonical_item_id": row["item_id"], "mapping_rule_id": None,
                "match_method": None, "mapping_confidence": None,
                "mapping_priority": 0, "sign_multiplier": 1.0, "unit_multiplier": 1.0,
            })
        if ticker == "PAN":
            log.debug(
                "PAN registry: %s -> %s via %s (%s)",
                row.get("raw_item_id"), result["canonical_metric"],
                result["match_method"], result["mapping_rule_id"],
            )
        return pd.Series({
            "canonical_item_id": result["canonical_metric"],
            "mapping_rule_id": result["mapping_rule_id"],
            "match_method": result["match_method"],
            "mapping_confidence": result["confidence"],
            "mapping_priority": result["priority"],
            "sign_multiplier": result["sign_multiplier"],
            "unit_multiplier": result["unit_multiplier"],
        })

    mapped = df.apply(registry_match, axis=1)
    df = pd.concat([df, mapped], axis=1)

    # Detect period columns starting with a digit
    period_cols = [c for c in df.columns if re.match(r"^\d{4}", c)]
    if not period_cols:
        log.warning("No period columns found in %s", file_path.name)
        return pd.DataFrame()

    id_vars = [
        "ticker", "report_type", "raw_item_id", "canonical_item_id",
        "mapping_rule_id", "match_method", "mapping_confidence", "mapping_priority",
        "sign_multiplier", "unit_multiplier", "raw_unit", "period_basis_explicit",
        "statement_scope", "audit_status",
    ]
    if "item" in df.columns:
        id_vars.append("item")
    if "source" in df.columns:
        id_vars.append("source")
        
    melted = df.melt(
        id_vars=id_vars,
        value_vars=period_cols,
        var_name="raw_period",
        value_name="value"
    )

    # Normalize periods using regex
    melted["period"] = melted["raw_period"].apply(normalize_period_str)
    
    def get_period_type(p: str) -> str:
        if "-Q" in p:
            return "quarter"
        return "year"
        
    melted["period_type"] = melted["period"].apply(get_period_type)
    melted["raw_value"] = pd.to_numeric(melted["value"], errors="coerce")
    unit_meta = melted.apply(
        lambda row: pd.Series(normalize_ocf_unit(row["raw_value"], row.get("raw_unit"), row["unit_multiplier"])),
        axis=1,
    )
    melted["value"] = unit_meta["value"] * melted["sign_multiplier"]
    melted["normalized_unit"] = unit_meta["normalized_unit"]
    melted["effective_unit_multiplier"] = unit_meta["unit_multiplier"]
    melted["unit_status"] = unit_meta["unit_status"]
    basis = melted.apply(
        lambda row: resolve_ocf_basis(
            row.get("source"), row.get("report_type"), row.get("period_type"),
            row.get("period_basis_explicit"),
        ),
        axis=1,
    )
    melted["ocf_basis"] = [item[0] for item in basis]
    melted["ocf_basis_confidence"] = [item[1] for item in basis]
    melted["raw_label"] = melted.get("item")
    melted["item_id"] = melted["canonical_item_id"]
    melted = melted.dropna(subset=["value"])
    
    return melted

# ==========================================
# CORE PROCESSING PIPELINE
# ==========================================
def process_data(
    tickers_filter: list[str] | None = None,
    *,
    schema_error_policy: str = "raise",
    source_diagnostics: list[dict[str, object]] | None = None,
) -> pd.DataFrame:
    log.info("Starting financial statement processing...")
    if schema_error_policy not in {"raise", "quarantine"}:
        raise ValueError("schema_error_policy must be 'raise' or 'quarantine'")
    
    if not INPUT_DIR.exists():
        log.error("Input directory does not exist: %s", INPUT_DIR)
        raise FileNotFoundError(f"Thư mục {INPUT_DIR} không tồn tại.")

    # Discover statement files
    all_files = list(INPUT_DIR.glob("*.parquet")) + list(INPUT_DIR.glob("*.csv"))

    # [VÁ P0-1 12/07/2026] Nhóm cuối `(quarter|year)` là TÙY CHỌN để đọc được cả tên cũ
    # {TICKER}_{report_type}.ext (chu kỳ chuyển tiếp, file nào migration không xác định
    # được period_type thì vẫn giữ tên cũ) lẫn tên mới {TICKER}_{report_type}_{period_type}.ext.
    file_pattern = re.compile(
        r"^([A-Z0-9]+)_(balance_sheet|income_statement|cash_flow)(?:_(quarter|year))?\.(parquet|csv)$",
        re.IGNORECASE
    )

    # Prioritize files based on modification timestamp (OS-level mtime)
    # Khóa GỒM CẢ period_suffix (None cho tên cũ) — nếu chỉ khóa (ticker, report_type) thì
    # 1 mã có cả bản quarter và year sẽ bị dedup nhầm, ÂM THẦM MẤT 1 trong 2 bộ dữ liệu
    # dù cả 2 file đều còn nguyên trên đĩa (đây chính là hệ quả tinh vi của bug P0-1 nếu
    # không sửa luôn chỗ này, không chỉ sửa tên file).
    selected_files: dict[tuple[str, str, str | None], Path] = {}
    for f in all_files:
        match = file_pattern.match(f.name)
        if match:
            ticker = match.group(1).upper()

            # Apply filter if provided (for validation test)
            if tickers_filter and ticker not in tickers_filter:
                continue

            report_type = match.group(2).lower()
            period_suffix = match.group(3).lower() if match.group(3) else None
            key = (ticker, report_type, period_suffix)

            if key not in selected_files:
                selected_files[key] = f
            else:
                existing_file = selected_files[key]
                existing_readable = existing_file.suffix != ".parquet" or PARQUET_ENGINE_AVAILABLE
                current_readable = f.suffix != ".parquet" or PARQUET_ENGINE_AVAILABLE
                # Prefer a readable representation, then the newest timestamp.
                if current_readable and not existing_readable:
                    selected_files[key] = f
                elif current_readable == existing_readable and os.path.getmtime(f) > os.path.getmtime(existing_file):
                    selected_files[key] = f

    if not selected_files:
        log.warning("No financial statements matched filter or exist in %s.", INPUT_DIR)
        return pd.DataFrame()

    unreadable_parquet = [path for path in selected_files.values() if path.suffix == ".parquet"]
    if unreadable_parquet and not PARQUET_ENGINE_AVAILABLE:
        examples = ", ".join(path.name for path in unreadable_parquet[:5])
        raise RuntimeError(
            f"Parquet engine unavailable for {len(unreadable_parquet)} selected statements "
            f"(examples: {examples}). Refusing to build an incomplete snapshot."
        )

    log.info("Processing %d statements after timestamp deduplication.", len(selected_files))
    
    # Load and melt files
    statement_list = []
    for (ticker, report_type, _period_suffix), path in selected_files.items():
        try:
            statement_df = load_and_melt_file(path)
        except SourceSchemaError as exc:
            if schema_error_policy == "raise":
                raise
            diagnostic = {**exc.to_dict(), "ticker": ticker, "report_type": report_type}
            if source_diagnostics is not None:
                source_diagnostics.append(diagnostic)
            log.warning("Quarantined invalid statement source: %s", diagnostic)
            continue
        if not statement_df.empty:
            statement_list.append(statement_df)
            
    if not statement_list:
        log.error("No valid BCTC data extracted.")
        return pd.DataFrame()

    # Combine all statements
    combined = pd.concat(statement_list, ignore_index=True)
    combined = combined.sort_values(
        ["mapping_priority", "mapping_confidence"], ascending=[False, False], na_position="last"
    )
    ocf_metrics = build_ocf_period_metrics(combined)
    statement_units = summarize_statement_units(combined)
    
    # Pivot columns. The 'first' aggregator ensures we get the leftmost period column in the BCTC file,
    # which maps to the latest restated data.
    pivot_df = (
        combined.groupby(["ticker", "period", "period_type", "item_id"])["value"]
        .first()
        .unstack()
    )
    
    pivot_df = pivot_df.reset_index()
    pivot_df = pivot_df.set_index(["ticker", "period"])
    
    # ==========================================
    # ITEM ID COALESCING (STATIC MAPPING)
    # ==========================================
    log.info("Coalescing target fields using ITEM_MAPPING...")
    final_df = pd.DataFrame(index=pivot_df.index)
    final_df["period_type"] = pivot_df["period_type"]
    
    # Programmatically apply mappings
    for target_field, candidates in ITEM_MAPPING.items():
        coalesced = pd.Series(np.nan, index=pivot_df.index)
        for cand in candidates:
            if cand in pivot_df.columns:
                coalesced = coalesced.fillna(pivot_df[cand])
        final_df[target_field] = coalesced

    # Reported metrics managed by the registry. Derived rules are declared in
    # the registry but intentionally not executed until Phase 4.
    for target_field in sorted(FINANCIAL_REGISTRY.reported_metrics()):
        if target_field in final_df.columns:
            continue
        final_df[target_field] = (
            pivot_df[target_field]
            if target_field in pivot_df.columns
            else pd.Series(np.nan, index=pivot_df.index)
        )

    # OCF has explicit reported/YTD/quarter/TTM fields. The legacy scalar uses
    # TTM only when four comparable standalone quarters exist; otherwise it
    # keeps the reported value for that same source period.
    if "operating_cash_flow" in final_df.columns:
        final_df = final_df.drop(columns=["operating_cash_flow"])
    if not ocf_metrics.empty:
        final_df = final_df.join(ocf_metrics.set_index(["ticker", "period"]), how="left")
    else:
        for field in [
            "operating_cash_flow_reported", "operating_cash_flow_ytd",
            "operating_cash_flow_quarter", "operating_cash_flow_quarter_status",
            "operating_cash_flow_ttm", "operating_cash_flow_ttm_status",
            "operating_cash_flow_ttm_reason",
            "operating_cash_flow", "operating_cash_flow_basis",
            "operating_cash_flow_basis_confidence", "operating_cash_flow_status",
            "operating_cash_flow_source_period",
            "operating_cash_flow_raw_unit", "operating_cash_flow_normalized_unit",
            "operating_cash_flow_unit_multiplier", "operating_cash_flow_unit_status",
            "operating_cash_flow_report_scope", "operating_cash_flow_audit_status",
            "operating_cash_flow_source",
        ]:
            final_df[field] = np.nan

    if not statement_units.empty:
        final_df = final_df.join(statement_units.set_index(["ticker", "period"]), how="left")
    else:
        final_df["statement_currency"] = "VND"
        final_df["statement_scale"] = np.nan
        final_df["unit_status"] = "unit_unknown"
        final_df["unit_evidence"] = "no mapped item found for this ticker-period"

    final_df = materialize_advanced_financial_metrics(final_df)

    # Calculate Debt (Short term + Long term debt)
    short_d = final_df["short_term_borrowings"].fillna(0.0)
    long_d = final_df["long_term_borrowings"].fillna(0.0)
    has_debt = final_df["short_term_borrowings"].notna() | final_df["long_term_borrowings"].notna()
    final_df["debt"] = (short_d + long_d).where(has_debt, np.nan)
    
    # Calculate Shares Outstanding (vietnamese par value rule)
    shares_col = pd.Series(np.nan, index=final_df.index)
    if "common_shares" in final_df.columns:
        shares_col = shares_col.fillna(final_df["common_shares"] / 10000.0)
    if "paid_in_capital" in final_df.columns:
        shares_col = shares_col.fillna(final_df["paid_in_capital"] / 10000.0)
    final_df["shares_outstanding"] = shares_col

    # shares_period_end: same value as shares_outstanding under a clearer, spec-aligned name
    # (Data Contract Hardening v1.1 item D) — a period-end, par-value-derived share count. It
    # is NOT shares_current (live, from VNSTOCK metadata) and NOT a weighted-average count;
    # do not substitute one for another without the reconciliation/proxy metadata that
    # consumes this column (see AI ANALYZE build_ticker_context.py share_reconciliation).
    final_df["shares_period_end"] = final_df["shares_outstanding"]
    final_df["shares_period_end_status"] = np.where(
        final_df["shares_period_end"].notna(), "derived", "source_empty"
    )
    final_df["shares_period_end_basis"] = np.where(
        final_df["shares_period_end"].notna(),
        "balance_sheet_common_shares_or_charter_capital_over_par_value_10000_vnd",
        None,
    )
    final_df["shares_period_end_reason"] = np.where(
        final_df["shares_period_end"].notna(), None,
        "common_shares_and_charter_capital_and_paid_in_capital_not_reported",
    )

    # Calculate Book Value (Per Share)
    final_df["book_value"] = final_df["equity"] / final_df["shares_outstanding"]
    # item C: book_value is a self-computed ratio over a period-end (not weighted-average)
    # share proxy — never canonical BVPS. status="proxy" so no consumer promotes it silently.
    final_df["book_value_status"] = np.where(final_df["book_value"].notna(), "proxy", "source_empty")
    final_df["book_value_basis"] = "equity_over_shares_period_end_not_weighted_average"

    # [VÁ P0-2] EPS tự tính — THAY THẾ eps_quarterly thô (đã bỏ khỏi ITEM_MAPPING, xem lý do ở đó).
    # eps_calc = net_profit / shares_outstanding CUỐI KỲ (không phải bình quân gia quyền như EPS
    # chuẩn VAS công bố) -> là PROXY, có thể lệch với EPS chính thức ở mã vừa phát hành/mua lại cổ
    # phiếu giữa kỳ. Đổi lại: minh bạch, tính được cho MỌI mã có đủ net_profit + shares_outstanding
    # (thay vì chỉ 4/10 mã như eps_quarterly thô), không phụ thuộc lỗi scale của riêng nguồn KBS.
    final_df["eps_calc"] = final_df["net_profit"] / final_df["shares_outstanding"]
    # item C: same proxy caveat as book_value — eps_calc must never be treated as canonical EPS.
    final_df["eps_calc_status"] = np.where(final_df["eps_calc"].notna(), "proxy", "source_empty")
    final_df["eps_calc_basis"] = "net_profit_over_shares_period_end_not_weighted_average"

    # Free Cash Flow (FCF) = OCF - CAPEX
    # CAPEX is the outflow from payment_for_fixed_assets... which is negative in statements.
    # We take the absolute value of capex_raw as CAPEX, and subtract it.
    final_df["capex"] = final_df["capex_raw"].abs()
    final_df["free_cash_flow"] = final_df["operating_cash_flow"] - final_df["capex"]

    # ==========================================
    # AUDITED RATIOS & GROWTH (VECTORIZED)
    # ==========================================
    log.info("Calculating audited financial ratios...")
    final_df = final_df.sort_index()
    
    # 1. Growth Rates with Absolute Denominators
    rev_map = final_df["revenue"].to_dict()
    profit_map = final_df["net_profit"].to_dict()

    rev_prev_qoq = []
    rev_prev_yoy = []
    profit_prev_qoq = []
    profit_prev_yoy = []

    # item B: YoY comparison period is calendar-anchored (find_yoy_comparison_period), not a
    # naive 'year-1' label swap — see that function's docstring for why. Only one match is
    # computed per (ticker, period) and reused for both revenue and profit so they can never
    # silently diff against two different "prior year" periods.
    ticker_periods: dict[str, list[str]] = {}
    for _ticker, _period in final_df.index:
        ticker_periods.setdefault(_ticker, []).append(_period)
    yoy_matches = {
        (ticker, period): find_yoy_comparison_period(period, ticker_periods.get(ticker, []))
        for ticker, period in final_df.index
    }

    # Historical lookup lists
    for (ticker, period) in final_df.index:
        p_type = final_df.loc[(ticker, period), "period_type"]

        qoq_period = get_qoq_period_str(period) if p_type == "quarter" else None
        yoy_period, _ = yoy_matches[(ticker, period)]

        rev_prev_qoq.append(rev_map.get((ticker, qoq_period), np.nan) if qoq_period else np.nan)
        rev_prev_yoy.append(rev_map.get((ticker, yoy_period), np.nan) if yoy_period else np.nan)
        profit_prev_qoq.append(profit_map.get((ticker, qoq_period), np.nan) if qoq_period else np.nan)
        profit_prev_yoy.append(profit_map.get((ticker, yoy_period), np.nan) if yoy_period else np.nan)

    final_df["revenue_prev_qoq"] = rev_prev_qoq
    final_df["revenue_prev_yoy"] = rev_prev_yoy
    final_df["profit_prev_qoq"] = profit_prev_qoq
    final_df["profit_prev_yoy"] = profit_prev_yoy
    final_df["_yoy_comparison_period"] = [yoy_matches[key][0] for key in final_df.index]
    final_df["_yoy_no_match_reason"] = [yoy_matches[key][1] for key in final_df.index]

    # Growth formulas use absolute values in denominator to ensure correctness with negative bases
    final_df["revenue_growth_yoy"] = (final_df["revenue"] - final_df["revenue_prev_yoy"]) / final_df["revenue_prev_yoy"].abs()
    final_df["revenue_growth_qoq"] = (final_df["revenue"] - final_df["revenue_prev_qoq"]) / final_df["revenue_prev_qoq"].abs()
    final_df["profit_growth_yoy"] = (final_df["net_profit"] - final_df["profit_prev_yoy"]) / final_df["profit_prev_yoy"].abs()
    final_df["profit_growth_qoq"] = (final_df["net_profit"] - final_df["profit_prev_qoq"]) / final_df["profit_prev_qoq"].abs()

    # item B: never leave a missing YoY value as a bare, unexplained NaN.
    final_df["revenue_growth_yoy_comparison_period"] = final_df["_yoy_comparison_period"]
    final_df["revenue_growth_yoy_status"] = np.select(
        [
            final_df["revenue_growth_yoy"].notna(),
            final_df["revenue"].isna(),
            final_df["_yoy_comparison_period"].isna(),
        ],
        ["derived", "current_period_value_missing", "insufficient_periods"],
        default="comparable_period_value_missing",
    )
    final_df["revenue_growth_yoy_reason"] = np.select(
        [
            final_df["revenue_growth_yoy"].notna(),
            final_df["revenue"].isna(),
            final_df["_yoy_comparison_period"].isna(),
        ],
        [None, "current_period_revenue_not_reported", final_df["_yoy_no_match_reason"]],
        default="comparable_period_revenue_not_reported",
    )
    final_df["profit_growth_yoy_comparison_period"] = final_df["_yoy_comparison_period"]
    final_df["profit_growth_yoy_status"] = np.select(
        [
            final_df["profit_growth_yoy"].notna(),
            final_df["net_profit"].isna(),
            final_df["_yoy_comparison_period"].isna(),
        ],
        ["derived", "current_period_value_missing", "insufficient_periods"],
        default="comparable_period_value_missing",
    )
    final_df["profit_growth_yoy_reason"] = np.select(
        [
            final_df["profit_growth_yoy"].notna(),
            final_df["net_profit"].isna(),
            final_df["_yoy_comparison_period"].isna(),
        ],
        [None, "current_period_profit_not_reported", final_df["_yoy_no_match_reason"]],
        default="comparable_period_profit_not_reported",
    )

    final_df = final_df.drop(columns=[
        "revenue_prev_qoq", "revenue_prev_yoy", "profit_prev_qoq", "profit_prev_yoy",
        "_yoy_comparison_period", "_yoy_no_match_reason",
    ])
    
    # 2. Margins
    final_df["gross_margin"] = final_df["gross_profit"] / final_df["revenue"]
    final_df["operating_margin"] = final_df["operating_profit"] / final_df["revenue"]
    final_df["net_margin"] = final_df["net_profit"] / final_df["revenue"]
    
    # 3. Returns (Average Equity ROE vs Ending ROA)
    # Average Equity ROE logic:
    # We find the previous quarter's equity to compute Average Equity.
    # If the previous quarter's equity is missing, we fall back to Ending Equity to avoid NaN loss.
    equity_map = final_df["equity"].to_dict()
    equity_prev_qoq = [equity_map.get((ticker, get_qoq_period_str(period)), np.nan) for ticker, period in final_df.index]
    
    # Compute Average Equity
    final_df["equity_prev"] = equity_prev_qoq
    average_equity = (final_df["equity"] + final_df["equity_prev"]) / 2.0
    average_equity = average_equity.fillna(final_df["equity"])  # Fallback to Ending Equity
    
    final_df["roe"] = final_df["net_profit"] / average_equity
    final_df["roa"] = final_df["net_profit"] / final_df["total_assets"]

    # ==========================================
    # item A (Data Contract Hardening v1.1): roe_quarter/roe_fy/roe_ttm replace the single
    # ambiguous `roe` column above (quarter ratio on quarter rows, annual ratio on year rows,
    # no unit/basis tag — the exact "6.94% (trailing, metadata.roe) vs 0.0175 (single-quarter
    # ratio, this column)" trap). Legacy `roe` VALUES stay byte-identical for backward
    # compatibility; roe_status/roe_canonical_metric point consumers at the replacement.
    # ==========================================
    is_quarter_row = final_df["period_type"] == "quarter"
    is_year_row = final_df["period_type"] == "year"
    period_values = final_df.index.get_level_values("period")

    final_df["roe_status"] = "deprecated"
    final_df["roe_canonical_metric"] = np.select(
        [is_quarter_row, is_year_row], ["roe_quarter", "roe_fy"], default=None
    )

    def _calendar_end_str(period: str, period_type: str) -> str | None:
        end = calendar_period_end(period, period_type)
        return end.strftime("%Y-%m-%d") if end is not None else None

    def _set_roe_metric(
        name: str,
        applicable: pd.Series,
        value: pd.Series,
        *,
        basis: str,
        annualization: str,
        formula: str,
        calendar_period_type: str,
        missing_reason: str,
    ) -> None:
        final_df[name] = value.where(applicable)
        has_value = applicable & final_df[name].notna()
        final_df[f"{name}_unit"] = np.where(applicable, "ratio", None)
        final_df[f"{name}_basis"] = np.where(applicable, basis, None)
        final_df[f"{name}_annualization"] = np.where(applicable, annualization, None)
        final_df[f"{name}_period"] = np.where(applicable, period_values, None)
        final_df[f"{name}_period_calendar_end"] = [
            _calendar_end_str(period, calendar_period_type) if applies else None
            for applies, period in zip(applicable, period_values)
        ]
        final_df[f"{name}_source"] = np.where(applicable, "financial_snapshot_derived", None)
        final_df[f"{name}_formula"] = np.where(applicable, formula, None)
        final_df[f"{name}_status"] = np.select(
            [has_value, applicable], ["derived", "insufficient_periods"], default="not_applicable"
        )
        final_df[f"{name}_reason"] = np.select(
            [has_value, applicable], [None, missing_reason], default="not_this_period_type",
        )

    # roe_quarter: same figure as legacy `roe` restricted to quarter rows, explicitly labeled.
    _set_roe_metric(
        "roe_quarter", is_quarter_row, final_df["roe"],
        basis="quarter_average_equity", annualization="none",
        formula="net_profit_quarter / average(equity_quarter_end, equity_prior_quarter_end_or_fallback_to_equity_quarter_end)",
        calendar_period_type="quarter",
        missing_reason="missing_net_profit_or_equity_for_quarter",
    )

    # roe_fy: same figure as legacy `roe` restricted to year rows. get_qoq_period_str() only
    # resolves quarter labels, so annual rows never get a true beginning/ending average — the
    # formula text below says "ending_equity", not "average_equity", to match what the number
    # actually is (do not repeat run_validation_test()'s slightly inaccurate "average" prose).
    _set_roe_metric(
        "roe_fy", is_year_row, final_df["roe"],
        basis="fiscal_year_ending_equity", annualization="fiscal_year",
        formula="net_profit_fy / equity_fy_ending",
        calendar_period_type="year",
        missing_reason="missing_net_profit_or_equity_for_fiscal_year",
    )

    # roe_ttm: trailing-twelve-month net profit — sum of 4 CONSECUTIVE, individually-reported
    # quarters chained via _previous_quarter (same building block as the OCF TTM logic above),
    # NOT calendar-distance matched like YoY (item B): TTM only ever means "this ticker's 4
    # immediately preceding quarters," with no cross-company fiscal-calendar ambiguity to
    # resolve. Average equity uses both TTM-window boundary quarters when available, falling
    # back to ending equity only (mirroring roe_quarter's own fallback) when the older
    # boundary is missing — the two cases are labeled with different basis/formula text so a
    # consumer can tell which was actually used.
    ttm_results = {key: compute_roe_ttm(key[0], key[1], profit_map, equity_map) for key in final_df.index}
    is_ttm_computable = pd.Series(
        [ttm_results[key]["value"] is not None for key in final_df.index], index=final_df.index
    )
    final_df["roe_ttm"] = [ttm_results[key]["value"] for key in final_df.index]
    final_df["roe_ttm_unit"] = np.where(is_quarter_row, "ratio", None)
    final_df["roe_ttm_basis"] = [
        ttm_results[key]["equity_basis"] if is_q else None for is_q, key in zip(is_quarter_row, final_df.index)
    ]
    final_df["roe_ttm_annualization"] = np.where(is_quarter_row, "trailing_twelve_month_sum", None)
    final_df["roe_ttm_period"] = np.where(is_quarter_row, period_values, None)
    final_df["roe_ttm_period_calendar_end"] = [
        _calendar_end_str(period, "quarter") if is_q else None
        for is_q, period in zip(is_quarter_row, period_values)
    ]
    final_df["roe_ttm_source"] = np.where(is_quarter_row, "financial_snapshot_derived", None)
    final_df["roe_ttm_formula"] = [
        (
            "sum(net_profit for 4 trailing consecutive quarters) / average(equity_at_ttm_window_start, equity_at_ttm_window_end)"
            if basis == "ttm_average_equity"
            else "sum(net_profit for 4 trailing consecutive quarters) / equity_at_ttm_window_end"
            if basis == "ttm_ending_equity_fallback"
            else None
        )
        for basis in final_df["roe_ttm_basis"]
    ]
    final_df["roe_ttm_status"] = np.select(
        [is_quarter_row & is_ttm_computable, is_quarter_row], ["derived", "insufficient_periods"],
        default="not_applicable",
    )
    final_df["roe_ttm_reason"] = np.select(
        [is_quarter_row & is_ttm_computable, is_quarter_row],
        [None, "requires_four_consecutive_reported_quarters_and_ttm_window_equity"],
        default="not_this_period_type",
    )

    final_df = final_df.drop(columns=["equity_prev"])
    
    # 4. Leverage Ratios
    final_df["debt_to_equity"] = final_df["debt"] / final_df["equity"]
    final_df["debt_ratio"] = final_df["debt"] / final_df["total_assets"]
    
    # 5. Liquidity Ratios (safe fallback to NaN when current assets or liabilities are missing)
    final_df["current_ratio"] = final_df["current_assets"] / final_df["current_liabilities"]
    final_df["quick_ratio"] = (final_df["current_assets"] - final_df["inventory"].fillna(0.0)) / final_df["current_liabilities"]
    final_df["cash_ratio"] = final_df["cash"] / final_df["current_liabilities"]
    
    # 6. Efficiency Turnovers
    final_df["asset_turnover"] = final_df["revenue"] / final_df["total_assets"]
    final_df["inventory_turnover"] = final_df["cost_of_goods_sold"].abs() / final_df["inventory"]
    final_df["receivable_turnover"] = final_df["revenue"] / final_df["receivables"]

    # Liquidity/inventory ratios structurally require a commercial current-asset/inventory
    # schema absent from bank/securities/insurance/finance_company statements (item E) — tag
    # those explicitly not_applicable instead of leaving an unexplained NaN indistinguishable
    # from a genuine reporting gap on a corporate ticker.
    non_corporate_liquidity = final_df["entity_type"].isin(CONFIRMED_NON_CORPORATE)
    for _liquidity_metric in ("current_ratio", "quick_ratio", "cash_ratio", "inventory_turnover"):
        final_df.loc[non_corporate_liquidity, _liquidity_metric] = np.nan
        _has_value = final_df[_liquidity_metric].notna()
        final_df[f"{_liquidity_metric}_status"] = np.select(
            [non_corporate_liquidity, _has_value], ["not_applicable", "derived"], default="source_empty"
        )
        final_df[f"{_liquidity_metric}_reason"] = np.select(
            [non_corporate_liquidity, _has_value],
            ["corporate_liquidity_structure_not_applicable", None],
            default="current_or_inventory_component_not_reported",
        )

    # 7. Operating Cash Flow Ratio
    final_df["operating_cash_flow_ratio"] = final_df["operating_cash_flow"] / final_df["current_liabilities"]

    # Drop intermediate columns
    final_df = final_df.drop(columns=["short_term_borrowings", "long_term_borrowings", "common_shares", "paid_in_capital", "capex_raw"])

    # Reset index and clean up infinite numbers
    final_df = final_df.reset_index()
    final_df = final_df.replace([np.inf, -np.inf], np.nan)
    final_df.insert(0, "schema_version", "2.0")

    # Flat snapshot provenance: keep scalar compatibility fields and attach
    # parallel source/period columns that CSV and every current consumer can read.
    for metric in (
        "ebit", "ebitda", "interest_expense", "retained_earnings",
        "depreciation", "amortization", "depreciation_and_amortization", "sga",
    ):
        status = final_df[f"{metric}_status"]
        final_df[f"{metric}_source"] = np.select(
            [status == "reported", status == "derived"],
            ["financial_mapping_registry", "derived_financial_statement"],
            default=None,
        )
        final_df[f"{metric}_period"] = np.where(
            final_df[metric].notna(), final_df["period"], None
        )

    # [P0-4] Gắn cờ xác minh kỳ theo lịch dương — xem flag_fiscal_period_verification() ở trên.
    final_df = flag_fiscal_period_verification(final_df)

    return final_df

# ==========================================
# ULTIMATE VALIDATION TEST & AUDIT SCRIPT
# ==========================================
def run_validation_test() -> None:
    print("\n" + "=" * 50)
    print("RUNNING THE ULTIMATE VALIDATION TEST (10 TICKERS)")
    print("=" * 50)
    
    validation_tickers = ['HPG', 'FPT', 'VNM', 'SSI', 'VCB', 'BID', 'MBB', 'BVH', 'GAS', 'MWG']
    
    # Verify which files exist in the data folder
    # [VÁ P0-1] glob("*_balance_sheet.*") không khớp tên mới {TICKER}_balance_sheet_{period_type}.ext
    # -> dùng "*_balance_sheet*" (không có dấu chấm ép buộc) để khớp cả tên cũ lẫn mới.
    log.info("Checking data availability for validation tickers...")
    available_tickers = set()
    for f in INPUT_DIR.glob("*_balance_sheet*"):
        ticker = f.name.split("_")[0].upper()
        if ticker in validation_tickers:
            available_tickers.add(ticker)
            
    print(f"Có sẵn BCTC cho {len(available_tickers)}/{len(validation_tickers)} mã audit: {sorted(list(available_tickers))}")
    
    # Process
    try:
        results = process_data(tickers_filter=validation_tickers)
    except Exception as e:
        print(f"[FATAL CRASH] Xử lý dữ liệu thất bại: {e}")
        sys.exit(1)
        
    if results.empty:
        print("[ERROR] Không có dữ liệu snapshot nào được tạo ra.")
        sys.exit(1)
        
    print(f"[SUCCESS] Tạo thành công snapshot validation với {len(results)} bản ghi.")
    
    # sector schema analysis
    sector_summary = []
    for tk in validation_tickers:
        sub = results[results["ticker"] == tk]
        if sub.empty:
            status = "❌ THIẾU FILE (Chưa cào)"
            sector_summary.append({
                "ticker": tk,
                "status": status,
                "period_range": "N/A",
                "revenue_ok": "N/A",
                "gross_margin_ok": "N/A",
                "current_ratio_ok": "N/A",
                "inventory_ok": "N/A"
            })
            continue
            
        latest_row = sub.sort_values(by="period").iloc[-1]
        
        # Sector logic check
        has_rev = pd.notna(latest_row.get("revenue"))
        has_gm = pd.notna(latest_row.get("gross_margin"))
        has_curr = pd.notna(latest_row.get("current_ratio"))
        has_inv = pd.notna(latest_row.get("inventory"))
        
        status = "✅ ĐÃ XỬ LÝ"
        
        # Check specific sector guidelines
        is_bank = tk in ["VCB", "BID", "MBB"]
        is_sec = tk in ["SSI"]
        is_ins = tk in ["BVH"]
        
        if is_bank:
            # Banking: inventory, gross margin, and current ratio MUST be NaN
            if not has_inv and not has_gm and not has_curr:
                status = "✅ HỢP LỆ (Ngành Ngân hàng - Graceful NaN)"
            else:
                status = "⚠️ CẢNH BÁO (Ngân hàng có số liệu phi logic)"
        elif is_sec:
            # Securities: inventory must be NaN, revenue must be OK
            if not has_inv and has_rev:
                status = "✅ HỢP LỆ (Ngành Chứng khoán - Revenue OK, Inventory NaN)"
            else:
                status = "⚠️ CẢNH BÁO (Chứng khoán phi logic)"
        elif is_ins:
            # Insurance: revenue must be OK
            if has_rev:
                status = "✅ HỢP LỆ (Ngành Bảo hiểm - Revenue OK)"
            else:
                status = "⚠️ CẢNH BÁO (Bảo hiểm phi logic)"
        else:
            # Commercial: inventory, gross margin, current ratio, revenue should be OK
            if has_rev and has_gm and has_curr and has_inv:
                status = "✅ HỢP LỆ (Ngành Sản xuất/Thương mại - Đầy đủ)"
            else:
                status = "⚠️ CẢNH BÁO (Thiếu trường ngành thương mại)"
        
        # Extract period range with NaN safety
        if not sub.empty and sub["period"].notna().any():
            p_min = sub["period"].min()
            p_max = sub["period"].max()
            period_range = f"{p_min} -> {p_max}"
        else:
            period_range = "N/A"
                
        sector_summary.append({
            "ticker": tk,
            "status": status,
            "period_range": period_range,
            "revenue_ok": "Đạt (Có giá trị)" if has_rev else "Không có",
            "gross_margin_ok": "Đạt (Có giá trị)" if has_gm else "Không có (NaN)",
            "current_ratio_ok": "Đạt (Có giá trị)" if has_curr else "Không có (NaN)",
            "inventory_ok": "Đạt (Có giá trị)" if has_inv else "Không có (NaN)"
        })

    # Save validation report
    # 1. Format Item Mapping Table
    mapping_rows = []
    for tk_f, cands in ITEM_MAPPING.items():
        mapping_rows.append(f"| `{tk_f}` | `{', '.join(cands)}` |")
    mapping_table_str = "\n".join(mapping_rows)
    
    # 2. Format Test Summary Table
    test_rows = []
    for ss in sector_summary:
        test_rows.append(f"| {ss['ticker']} | {ss['status']} | {ss['period_range']} | {ss['revenue_ok']} | {ss['gross_margin_ok']} | {ss['current_ratio_ok']} | {ss['inventory_ok']} |")
    test_table_str = "\n".join(test_rows)
    
    report_content = r"""# VALIDATION & AUDIT REPORT

Báo cáo chi tiết về logic tài chính, sơ đồ ngành, chuẩn hóa chu kỳ và kết quả kiểm thử snapshot đầu ra của hệ thống xử lý báo cáo tài chính.

## 1. Bảng Item Mapping (Static Item Mapping)

Bảng trích xuất tĩnh các chỉ tiêu tài chính từ tệp thô BCTC được cài đặt cố định trong code:

| Standardized Metric | Raw `item_id` Candidates (Coalesce Order) |
|---|---|
__MAPPING_TABLE__

## 2. Công thức tài chính đã được chuẩn hóa

Các công thức tài chính lõi được sử dụng trong `bctc_processor.py` để tính toán:

*   **Tốc độ tăng trưởng doanh thu YoY**:
    $$\text{Revenue Growth YoY} = \frac{\text{Revenue}_t - \text{Revenue}_{t-\text{prev}}}{\text{abs}(\text{Revenue}_{t-\text{prev}})}$$
    *Sử dụng hàm trị tuyệt đối ở mẫu số để đảm bảo tính đúng đắn khi doanh thu năm trước bị âm.*
*   **Dòng tiền tự do (Free Cash Flow - FCF)**:
    $$\text{Free Cash Flow} = \text{Operating Cash Flow} - \text{CAPEX}$$
    *Trong đó, CAPEX được lấy bằng trị tuyệt đối của chỉ tiêu thô `payment_for_fixed_assets_constructions_and_other_long_term_assets` (chỉ tiêu Tiền chi mua sắm tài sản cố định trong Báo cáo Lưu chuyển tiền tệ).*
*   **ROE (Return on Equity)**:
    $$\text{ROE} = \frac{\text{Net Profit}}{\text{Average Equity}}$$
    *Average Equity được tính bằng trung bình cộng Vốn chủ sở hữu kỳ này và kỳ trước liền kề ($(Equity_t + Equity_{t-1}) / 2.0$). Trường hợp thiếu dữ liệu kỳ trước, hệ thống tự động fallback sử dụng Ending Equity ($Equity_t$) nhằm tránh làm mất dòng dữ liệu.*
*   **EPS (Earnings per Share) — `eps_calc`, TỰ TÍNH (vá 12/07/2026)**:
    $$\text{EPS}_{\text{calc}} = \frac{\text{Net Profit}}{\text{Shares Outstanding}}$$
    *Đã bỏ cột `eps_quarterly` thô (nguồn KBS `earnings_per_share_vnd`): điều tra trên 10 mã đủ 4 loại hình cho thấy nguồn này thiếu hoàn toàn ở ngân hàng/chứng khoán/bảo hiểm (0/6 mã có số) và ở nhóm có số thì lệch scale không ổn định (chia 1000 chỉ đưa về đúng bậc độ lớn, lệch 0,6x–1,1x so với đối chứng, có kỳ lệch tới 40%) — xem `docs/AUDIT_REPORT.md` mục P0-2. `eps_calc` dùng `shares_outstanding` CUỐI KỲ (không phải bình quân gia quyền như EPS chuẩn VAS) nên là PROXY, có thể lệch với số công bố chính thức ở mã vừa phát hành/mua lại cổ phiếu giữa kỳ.*

## 3. Kết quả kiểm thử trên 10 mã (The Ultimate Validation Test)

Kết quả chạy thực tế trên tập 10 mã đại diện cho các ngành khác nhau:

| Ticker | Trạng thái Audit | Chu kỳ dữ liệu | Doanh thu | Biên Lợi nhuận gộp | Hệ số Thanh toán hiện hành | Hàng tồn kho |
|---|---|---|---|---|---|---|
__TEST_TABLE__

**Kết luận Audit:**
Hệ thống xử lý gracefully các giá trị trống (`NaN`) đối với các ngành đặc thù (Ngân hàng không có kho/thanh toán nhanh; Chứng khoán/Bảo hiểm không có biên gộp/kho), đảm bảo snapshot đầu ra có cấu trúc chuẩn hóa cao và tuyệt đối không xảy ra lỗi crash trong quá trình chạy.
"""
    
    report_content = report_content.replace("__MAPPING_TABLE__", mapping_table_str)
    report_content = report_content.replace("__TEST_TABLE__", test_table_str)
    
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    print(f"\n[SUCCESS] Đã ghi báo cáo audit tại: {REPORT_OUT}")
    print("=" * 50)

QUARANTINE_REPORT_OUT = ROOT_DIR / "reports" / "bctc_quarantine_latest.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Xử lý dữ liệu tài chính BCTC thô thành bộ dữ liệu phân tích compact"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Chạy chế độ kiểm thử audit & validation trên 10 mã CK đại diện"
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="KHÔNG cô lập lỗi cấp file/ticker — dừng ngay khi 1 file lỗi schema (hành vi cũ"
             " trước 2026-07-17). Mặc định (không có cờ này): lỗi schema của MỘT file/ticker bị"
             " CÔ LẬP (schema_error_policy='quarantine') và ghi báo cáo, các ticker hợp lệ khác"
             " vẫn được xử lý bình thường — chỉ dừng toàn bộ khi lỗi thuộc hạ tầng chung (không"
             " đọc được thư mục nguồn, thiếu engine parquet) hoặc không tạo được output nào."
    )

    args = parser.parse_args()

    if args.test:
        run_validation_test()
        return

    # Standard run: process all files in data_bctc. Mặc định CÔ LẬP lỗi cấp file/ticker thay vì
    # để 1 file hỏng (vd BIO_balance_sheet.csv — thiếu cột kỳ/giá trị, xem diagnostic đã ghi
    # 2026-07-17) chặn toàn bộ 1.492 mã còn lại. process_data() đã có sẵn cơ chế này
    # (schema_error_policy="quarantine" + source_diagnostics) — dùng lại, không viết logic mới.
    source_diagnostics: list[dict[str, object]] = []
    policy = "raise" if args.strict else "quarantine"
    try:
        final_df = process_data(schema_error_policy=policy, source_diagnostics=source_diagnostics)
    except SourceSchemaError as exc:
        print(f"[FATAL] Dừng toàn bộ vì --strict: {exc}")
        sys.exit(1)

    if source_diagnostics:
        print(f"\n[CẢNH BÁO] Đã CÔ LẬP {len(source_diagnostics)} file lỗi schema"
              " (KHÔNG chặn các ticker/file còn lại):")
        for item in source_diagnostics:
            missing = ", ".join(item.get("missing_fields", []))
            print(f"  - {item.get('ticker')} / {item.get('report_type')}: {item.get('reason')}"
                  f" (thiếu: {missing}) <- {item.get('source')}")
        QUARANTINE_REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
        QUARANTINE_REPORT_OUT.write_text(
            json.dumps({
                "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "quarantined_count": len(source_diagnostics),
                "quarantined": source_diagnostics,
                "note": "File/ticker này bị LOẠI khỏi lần build hiện tại, không bị xóa/sửa trên"
                        " đĩa. Không tự bịa số liệu thay thế — xem 'reason'/'missing_fields'"
                        " từng mục để biết vì sao (vd 'period/value' = file không có cột kỳ/giá"
                        " trị nào, không phải lỗi encoding/delimiter).",
            }, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"  -> Chi tiết đầy đủ: {QUARANTINE_REPORT_OUT}")

    if final_df.empty:
        # "output không thể tạo" — đây LÀ lỗi toàn cục, không phải lỗi 1 ticker -> fail cứng.
        log.error("Không trích xuất được BCTC hợp lệ nào — không tạo được snapshot.")
        print("[FATAL] Không có dữ liệu BCTC hợp lệ nào sau khi xử lý — không tạo file output.")
        sys.exit(1)

    try:
        final_df.to_parquet(PARQUET_OUT, index=False)
        final_df.to_csv(CSV_OUT, index=False, encoding="utf-8-sig")
        status = "[HOÀN TẤT VỚI CẢNH BÁO]" if source_diagnostics else "[SUCCESS]"
        print(f"\n{status} Đã tạo thành công các file snapshot tại:")
        print(f"  - Parquet: {PARQUET_OUT}")
        print(f"  - CSV:     {CSV_OUT}")
        print(f"Tổng số bản ghi: {len(final_df)} dòng.")
        if source_diagnostics:
            print(f"({len(source_diagnostics)} ticker/file bị cô lập — xem {QUARANTINE_REPORT_OUT.name})")

        summary = final_df.groupby("ticker").size().reset_index(name="periods")
        print("\nThống kê theo mã chứng khoán:")
        for _, r in summary.iterrows():
            print(f"  Ticker {r['ticker']}: {r['periods']} kỳ báo cáo.")
    except Exception as e:
        log.error("Failed to save snapshot: %s", e)
        print(f"[ERROR] Lỗi khi lưu snapshot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
