"""Producer-owned Point-in-Time Adjusted Price Series MVP for Stock Lookup.

Applies qualified cash and non-cash corporate action adjustment factors to
raw historical market close prices under an explicit knowledge_cutoff.

Emits deterministic, provenance-carrying point-in-time adjusted close series.
Emits 0 adjusted returns.
"""

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from corporate_action_factors import (
    derive_cash_dividend_adjustment_factors,
    derive_non_cash_adjustment_factors,
)
from semantic_evidence_bridge import DB_RELATIVE, load_verified_market_price

ADJUSTMENT_CONTRACT_VERSION = "1.0.0"


def _hash(value: Any) -> str:
    """Compute deterministic SHA-256 string for canonical adjusted price objects."""
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _query_all_raw_ohlcv(db_path: Path, ticker: str) -> list[dict[str, Any]]:
    """Read-only query of all raw daily OHLCV rows for ticker ordered by trading_date."""
    if not db_path.is_file():
        return []
    try:
        connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(
            "SELECT ticker, date as trading_date, open, high, low, close, volume, source FROM ohlcv WHERE ticker=? ORDER BY date ASC",
            (ticker,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        connection.close()
        return rows
    except sqlite3.Error:
        return []


def build_point_in_time_adjusted_prices(
    runtime_root: Path,
    ticker: str = "VNM",
    knowledge_cutoff: str | None = None,
    anchor_date: str | None = None,
) -> dict[str, Any]:
    """Build deterministic point-in-time backward-adjusted close price series for ticker.

    Accepts an explicit knowledge_cutoff timestamp to isolate observable evidence vintages.
    Applies qualified cash, stock dividend, and bonus share multipliers to pre-event sessions (T < ex_date).

    Emits 0 adjusted returns.

    Returns:
        {
            "status": "available" | "unavailable",
            "adjustment_contract_version": ADJUSTMENT_CONTRACT_VERSION,
            "ticker": ticker,
            "anchor_date": anchor_date,
            "knowledge_cutoff": knowledge_cutoff,
            "adjusted_series": [...],
            "applied_factors_summary": {...},
            "raw_row_count": N,
            "adjusted_row_count": M
        }
    """
    price_res = load_verified_market_price(runtime_root)
    non_cash_res = derive_non_cash_adjustment_factors(runtime_root, ticker=ticker)
    cash_res = derive_cash_dividend_adjustment_factors(runtime_root, ticker=ticker)

    if price_res.get("status") != "available":
        return {
            "status": "unavailable",
            "adjustment_contract_version": ADJUSTMENT_CONTRACT_VERSION,
            "ticker": ticker,
            "anchor_date": anchor_date,
            "knowledge_cutoff": knowledge_cutoff,
            "adjusted_series": [],
            "applied_factors_summary": {},
            "raw_row_count": 0,
            "adjusted_row_count": 0,
        }

    prices_by_date = price_res.get("by_ticker_date", {})
    db_path = runtime_root / DB_RELATIVE
    raw_rows = _query_all_raw_ohlcv(db_path, ticker=ticker)

    if not raw_rows:
        return {
            "status": "unavailable",
            "adjustment_contract_version": ADJUSTMENT_CONTRACT_VERSION,
            "ticker": ticker,
            "anchor_date": anchor_date,
            "knowledge_cutoff": knowledge_cutoff,
            "adjusted_series": [],
            "applied_factors_summary": {},
            "raw_row_count": 0,
            "adjusted_row_count": 0,
        }

    # Filter qualified factors by knowledge_cutoff if provided
    eligible_factors: list[dict[str, Any]] = []

    # Non-cash factors
    if non_cash_res.get("status") == "available":
        for f in non_cash_res.get("individual_factors", []):
            if f.get("event_status") == "completed":
                decl = f.get("declaration_date") or ""
                verified_at = f.get("evidence", {}).get("publication_date") or decl
                if knowledge_cutoff is None or verified_at <= knowledge_cutoff or decl <= knowledge_cutoff:
                    eligible_factors.append(f)

    # Cash factors
    if cash_res.get("status") == "available":
        for f in cash_res.get("cash_dividend_factors", []):
            if f.get("event_status") == "completed":
                decl = f.get("declaration_date") or ""
                verified_at = f.get("evidence", {}).get("publication_date") or decl
                if knowledge_cutoff is None or verified_at <= knowledge_cutoff or decl <= knowledge_cutoff:
                    eligible_factors.append(f)

    # Sort factors by ex_date / ordering key
    eligible_factors.sort(key=lambda f: (f.get("ex_date") or "9999-99-99", f.get("factor_id")))

    # Set anchor date (default: latest trading date in raw_rows)
    latest_raw_date = raw_rows[-1]["trading_date"]
    effective_anchor_date = anchor_date or latest_raw_date

    adjusted_series: list[dict[str, Any]] = []

    for r in raw_rows:
        t_date = r["trading_date"]
        raw_close = float(r["close"])
        obs_citation = prices_by_date.get((ticker, t_date))
        obs_id = obs_citation.get("citation_id") if obs_citation else None

        applied_factors: list[dict[str, Any]] = []
        cum_mult = 1.0

        for f in eligible_factors:
            ex_date = f.get("ex_date")
            if ex_date and t_date < ex_date:
                mult = float(f["theoretical_price_multiplier"])
                cum_mult *= mult
                applied_factors.append(f)

        # Backward adjustment convention: P_adj(T) = P_raw(T) * cum_mult
        adjusted_close = raw_close * cum_mult

        row_id = _hash({
            "ticker": ticker,
            "trading_date": t_date,
            "raw_close": raw_close,
            "anchor_date": effective_anchor_date,
            "knowledge_cutoff": knowledge_cutoff,
            "cumulative_multiplier": cum_mult,
            "version": ADJUSTMENT_CONTRACT_VERSION,
        })

        adjusted_row = {
            "adjusted_row_id": row_id,
            "ticker": ticker,
            "trading_date": t_date,
            "raw_close": raw_close,
            "adjusted_close": adjusted_close,
            "currency": "VND",
            "anchor_date": effective_anchor_date,
            "knowledge_cutoff": knowledge_cutoff,
            "applied_factor_ids": [f["factor_id"] for f in applied_factors],
            "applied_event_ids": [f["canonical_event_id"] for f in applied_factors],
            "cumulative_multiplier": cum_mult,
            "adjustment_contract_version": ADJUSTMENT_CONTRACT_VERSION,
            "raw_observation_id": obs_id,
            "qualification_state": "qualified",
        }

        adjusted_series.append(adjusted_row)

    cash_applied = sum(1 for f in eligible_factors if f.get("event_type") == "cash_dividend")
    stock_div_applied = sum(1 for f in eligible_factors if f.get("event_type") == "stock_dividend")
    bonus_share_applied = sum(1 for f in eligible_factors if f.get("event_type") == "bonus_share")

    return {
        "status": "available",
        "adjustment_contract_version": ADJUSTMENT_CONTRACT_VERSION,
        "ticker": ticker,
        "anchor_date": effective_anchor_date,
        "knowledge_cutoff": knowledge_cutoff,
        "adjusted_series": adjusted_series,
        "applied_factors_summary": {
            "total_eligible_factors": len(eligible_factors),
            "cash_dividend_factors": cash_applied,
            "stock_dividend_factors": stock_div_applied,
            "bonus_share_factors": bonus_share_applied,
        },
        "raw_row_count": len(raw_rows),
        "adjusted_row_count": len(adjusted_series),
    }
