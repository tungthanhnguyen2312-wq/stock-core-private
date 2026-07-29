"""Producer-owned Point-in-Time Adjusted Return Series MVP for Stock Lookup.

Derives deterministic point-in-time adjusted simple price returns from qualified
point-in-time adjusted price series.

Emits 0 benchmark returns, 0 beta, 0 correlation, and 0 backtest outputs.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from point_in_time_adjusted_prices import build_point_in_time_adjusted_prices

RETURN_CONTRACT_VERSION = "1.0.0"
SUPPORTED_RETURN_TYPES = {"simple_price_return"}


def _hash(value: Any) -> str:
    """Compute deterministic SHA-256 string for canonical return objects."""
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_point_in_time_adjusted_returns(
    runtime_root: Path,
    ticker: str = "VNM",
    knowledge_cutoff: str | None = None,
    anchor_date: str | None = None,
    return_type: str = "simple_price_return",
) -> dict[str, Any]:
    """Build deterministic point-in-time adjusted price return series for ticker.

    Accepts an explicit knowledge_cutoff timestamp to isolate observable evidence vintages.
    Calculates simple price returns: (P_t / P_{t-1}) - 1 from pre-aligned adjusted close series.
    The first row has return_value = null with reason 'no_previous_eligible_session'.

    Emits 0 benchmark returns, 0 beta, 0 correlation, and 0 backtest outputs.

    Returns:
        {
            "status": "available" | "unavailable",
            "return_contract_version": RETURN_CONTRACT_VERSION,
            "return_type": return_type,
            "ticker": ticker,
            "anchor_date": anchor_date,
            "knowledge_cutoff": knowledge_cutoff,
            "return_series": [...],
            "valid_return_count": N,
            "unavailable_return_count": M,
            "total_row_count": T
        }
    """
    if return_type not in SUPPORTED_RETURN_TYPES:
        return {
            "status": "unavailable",
            "return_contract_version": RETURN_CONTRACT_VERSION,
            "return_type": return_type,
            "ticker": ticker,
            "anchor_date": anchor_date,
            "knowledge_cutoff": knowledge_cutoff,
            "return_series": [],
            "valid_return_count": 0,
            "unavailable_return_count": 0,
            "total_row_count": 0,
            "reason": "unsupported_return_type",
        }

    pit_prices = build_point_in_time_adjusted_prices(
        runtime_root=runtime_root,
        ticker=ticker,
        knowledge_cutoff=knowledge_cutoff,
        anchor_date=anchor_date,
    )

    if pit_prices.get("status") != "available":
        return {
            "status": "unavailable",
            "return_contract_version": RETURN_CONTRACT_VERSION,
            "return_type": return_type,
            "ticker": ticker,
            "anchor_date": anchor_date,
            "knowledge_cutoff": knowledge_cutoff,
            "return_series": [],
            "valid_return_count": 0,
            "unavailable_return_count": 0,
            "total_row_count": 0,
            "reason": "adjusted_prices_unavailable",
        }

    adjusted_series = pit_prices.get("adjusted_series", [])
    if not adjusted_series:
        return {
            "status": "unavailable",
            "return_contract_version": RETURN_CONTRACT_VERSION,
            "return_type": return_type,
            "ticker": ticker,
            "anchor_date": anchor_date,
            "knowledge_cutoff": knowledge_cutoff,
            "return_series": [],
            "valid_return_count": 0,
            "unavailable_return_count": 0,
            "total_row_count": 0,
            "reason": "empty_adjusted_series",
        }

    return_series: list[dict[str, Any]] = []
    valid_count = 0
    unavailable_count = 0

    effective_anchor_date = pit_prices.get("anchor_date")

    for idx, curr in enumerate(adjusted_series):
        t_date = curr["trading_date"]
        curr_price = float(curr["adjusted_close"])
        curr_row_id = curr["adjusted_row_id"]

        if idx == 0:
            # First row has no previous session
            row_id = _hash({
                "ticker": ticker,
                "trading_date": t_date,
                "previous_trading_date": None,
                "current_adjusted_row_id": curr_row_id,
                "previous_adjusted_row_id": None,
                "return_type": return_type,
                "knowledge_cutoff": knowledge_cutoff,
                "anchor_date": effective_anchor_date,
                "version": RETURN_CONTRACT_VERSION,
            })

            ret_row = {
                "return_row_id": row_id,
                "ticker": ticker,
                "trading_date": t_date,
                "previous_trading_date": None,
                "current_adjusted_row_id": curr_row_id,
                "previous_adjusted_row_id": None,
                "current_adjusted_close": curr_price,
                "previous_adjusted_close": None,
                "return_type": return_type,
                "return_value": None,
                "currency": "VND",
                "anchor_date": effective_anchor_date,
                "knowledge_cutoff": knowledge_cutoff,
                "applied_factor_ids": curr.get("applied_factor_ids", []),
                "applied_event_ids": curr.get("applied_event_ids", []),
                "source_observation_ids": [curr["raw_observation_id"]] if curr.get("raw_observation_id") else [],
                "return_contract_version": RETURN_CONTRACT_VERSION,
                "qualification_state": "qualified",
                "unavailable_reason": "no_previous_eligible_session",
            }
            return_series.append(ret_row)
            unavailable_count += 1
            continue

        prev = adjusted_series[idx - 1]
        prev_t_date = prev["trading_date"]
        prev_price = float(prev["adjusted_close"])
        prev_row_id = prev["adjusted_row_id"]

        if prev_price <= 0 or curr_price <= 0:
            row_id = _hash({
                "ticker": ticker,
                "trading_date": t_date,
                "previous_trading_date": prev_t_date,
                "current_adjusted_row_id": curr_row_id,
                "previous_adjusted_row_id": prev_row_id,
                "return_type": return_type,
                "knowledge_cutoff": knowledge_cutoff,
                "anchor_date": effective_anchor_date,
                "version": RETURN_CONTRACT_VERSION,
            })

            ret_row = {
                "return_row_id": row_id,
                "ticker": ticker,
                "trading_date": t_date,
                "previous_trading_date": prev_t_date,
                "current_adjusted_row_id": curr_row_id,
                "previous_adjusted_row_id": prev_row_id,
                "current_adjusted_close": curr_price,
                "previous_adjusted_close": prev_price,
                "return_type": return_type,
                "return_value": None,
                "currency": "VND",
                "anchor_date": effective_anchor_date,
                "knowledge_cutoff": knowledge_cutoff,
                "applied_factor_ids": list(set(curr.get("applied_factor_ids", []) + prev.get("applied_factor_ids", []))),
                "applied_event_ids": list(set(curr.get("applied_event_ids", []) + prev.get("applied_event_ids", []))),
                "source_observation_ids": [r["raw_observation_id"] for r in [curr, prev] if r.get("raw_observation_id")],
                "return_contract_version": RETURN_CONTRACT_VERSION,
                "qualification_state": "qualified",
                "unavailable_reason": "invalid_or_non_positive_price",
            }
            return_series.append(ret_row)
            unavailable_count += 1
            continue

        # Simple price return calculation: (P_t / P_{t-1}) - 1
        ret_val = (curr_price / prev_price) - 1.0

        row_id = _hash({
            "ticker": ticker,
            "trading_date": t_date,
            "previous_trading_date": prev_t_date,
            "current_adjusted_row_id": curr_row_id,
            "previous_adjusted_row_id": prev_row_id,
            "return_type": return_type,
            "knowledge_cutoff": knowledge_cutoff,
            "anchor_date": effective_anchor_date,
            "version": RETURN_CONTRACT_VERSION,
        })

        obs_ids = []
        if curr.get("raw_observation_id"):
            obs_ids.append(curr["raw_observation_id"])
        if prev.get("raw_observation_id") and prev["raw_observation_id"] != curr.get("raw_observation_id"):
            obs_ids.append(prev["raw_observation_id"])

        ret_row = {
            "return_row_id": row_id,
            "ticker": ticker,
            "trading_date": t_date,
            "previous_trading_date": prev_t_date,
            "current_adjusted_row_id": curr_row_id,
            "previous_adjusted_row_id": prev_row_id,
            "current_adjusted_close": curr_price,
            "previous_adjusted_close": prev_price,
            "return_type": return_type,
            "return_value": ret_val,
            "currency": "VND",
            "anchor_date": effective_anchor_date,
            "knowledge_cutoff": knowledge_cutoff,
            "applied_factor_ids": sorted(list(set(curr.get("applied_factor_ids", []) + prev.get("applied_factor_ids", [])))),
            "applied_event_ids": sorted(list(set(curr.get("applied_event_ids", []) + prev.get("applied_event_ids", [])))),
            "source_observation_ids": obs_ids,
            "return_contract_version": RETURN_CONTRACT_VERSION,
            "qualification_state": "qualified",
            "unavailable_reason": None,
        }

        return_series.append(ret_row)
        valid_count += 1

    return {
        "status": "available",
        "return_contract_version": RETURN_CONTRACT_VERSION,
        "return_type": return_type,
        "ticker": ticker,
        "anchor_date": effective_anchor_date,
        "knowledge_cutoff": knowledge_cutoff,
        "return_series": return_series,
        "valid_return_count": valid_count,
        "unavailable_return_count": unavailable_count,
        "total_row_count": len(return_series),
    }
