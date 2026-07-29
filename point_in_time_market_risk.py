"""Producer-owned Point-in-Time Rolling Beta and Correlation MVP for Stock Lookup.

Derives deterministic point-in-time rolling 60-session Beta and Pearson correlation for VNM
against the qualified VNINDEX benchmark.

Emits 0 alpha, 0 portfolio outputs, and 0 backtest outputs.
"""

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from point_in_time_benchmark import QUALIFIED_BENCHMARK_SYMBOL, align_vnm_and_benchmark_returns

METRIC_CONTRACT_VERSION = "1.0.0"
REQUIRED_WINDOW_LENGTH = 60


def _hash(value: Any) -> str:
    """Compute deterministic SHA-256 string for canonical risk metric objects."""
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def calculate_point_in_time_beta_and_correlation(
    runtime_root: Path,
    ticker: str = "VNM",
    benchmark_symbol: str = QUALIFIED_BENCHMARK_SYMBOL,
    knowledge_cutoff: str | None = None,
    anchor_date: str | None = None,
    window_length: int = REQUIRED_WINDOW_LENGTH,
) -> dict[str, Any]:
    """Calculate rolling Beta and Pearson correlation for ticker vs benchmark_symbol over a trailing window.

    Requires exactly window_length (default 60) consecutive valid aligned return pairs.
    Fails closed (metric_value = null) if observation count < window_length or if benchmark/VNM variance <= 0.

    Emits 0 alpha, 0 portfolio outputs, and 0 backtest outputs.

    Returns:
        {
            "status": "available" | "unavailable",
            "metric_contract_version": METRIC_CONTRACT_VERSION,
            "ticker": ticker,
            "benchmark_symbol": benchmark_symbol,
            "window_length": window_length,
            "knowledge_cutoff": knowledge_cutoff,
            "anchor_date": anchor_date,
            "metric_series": [...],
            "valid_beta_count": B,
            "valid_correlation_count": C,
            "total_evaluated_dates": T
        }
    """
    align_res = align_vnm_and_benchmark_returns(
        runtime_root=runtime_root,
        ticker=ticker,
        benchmark_symbol=benchmark_symbol,
        knowledge_cutoff=knowledge_cutoff,
        anchor_date=anchor_date,
    )

    if align_res.get("status") != "available":
        return {
            "status": "unavailable",
            "metric_contract_version": METRIC_CONTRACT_VERSION,
            "ticker": ticker,
            "benchmark_symbol": benchmark_symbol,
            "window_length": window_length,
            "knowledge_cutoff": knowledge_cutoff,
            "anchor_date": anchor_date,
            "metric_series": [],
            "valid_beta_count": 0,
            "valid_correlation_count": 0,
            "total_evaluated_dates": 0,
            "reason": "alignment_series_unavailable",
        }

    aligned_pairs = align_res.get("aligned_pairs", [])
    effective_anchor_date = align_res.get("anchor_date")

    # Filter only pairs with non-null valid returns
    valid_pairs = [p for p in aligned_pairs if p.get("vnm_return_value") is not None and p.get("benchmark_return_value") is not None]

    metric_series: list[dict[str, Any]] = []
    valid_beta_count = 0
    valid_corr_count = 0

    for i in range(len(aligned_pairs)):
        curr_pair = aligned_pairs[i]
        calc_date = curr_pair["trading_date"]

        # Gather valid trailing pairs up to curr_pair
        trailing_valid = [p for p in valid_pairs if p["trading_date"] <= calc_date]

        if len(trailing_valid) < window_length:
            # Fewer than 60 observations available
            metric_id = _hash({
                "ticker": ticker,
                "benchmark_symbol": benchmark_symbol,
                "calculation_date": calc_date,
                "window_length": window_length,
                "knowledge_cutoff": knowledge_cutoff,
                "anchor_date": effective_anchor_date,
                "version": METRIC_CONTRACT_VERSION,
            })

            metric_row = {
                "metric_result_id": metric_id,
                "ticker": ticker,
                "benchmark_symbol": benchmark_symbol,
                "metric_type": "rolling_beta_and_correlation",
                "calculation_date": calc_date,
                "window_length": window_length,
                "window_start_date": trailing_valid[0]["trading_date"] if trailing_valid else None,
                "window_end_date": calc_date,
                "knowledge_cutoff": knowledge_cutoff,
                "anchor_date": effective_anchor_date,
                "eligible_observation_count": len(trailing_valid),
                "required_observation_count": window_length,
                "beta_value": None,
                "correlation_value": None,
                "currency": "VND",
                "ordered_pair_ids": [p["pair_id"] for p in trailing_valid],
                "upstream_lineage": {},
                "metric_contract_version": METRIC_CONTRACT_VERSION,
                "qualification_state": "qualified",
                "unavailable_reason": "insufficient_aligned_observations",
            }
            metric_series.append(metric_row)
            continue

        # Extract trailing window of exactly window_length pairs
        window_pairs = trailing_valid[-window_length:]
        vnm_returns = [float(p["vnm_return_value"]) for p in window_pairs]
        bmk_returns = [float(p["benchmark_return_value"]) for p in window_pairs]

        mean_vnm = sum(vnm_returns) / float(window_length)
        mean_bmk = sum(bmk_returns) / float(window_length)

        # Sample covariance & sample variances (denominator N-1 = 59)
        cov = sum((vnm_returns[k] - mean_vnm) * (bmk_returns[k] - mean_bmk) for k in range(window_length)) / float(window_length - 1)
        var_bmk = sum((bmk_returns[k] - mean_bmk) ** 2 for k in range(window_length)) / float(window_length - 1)
        var_vnm = sum((vnm_returns[k] - mean_vnm) ** 2 for k in range(window_length)) / float(window_length - 1)

        beta_val = None
        corr_val = None
        unavail_reason = None

        if var_bmk <= 1e-12:
            unavail_reason = "zero_or_near_zero_benchmark_variance"
        else:
            beta_val = cov / var_bmk
            valid_beta_count += 1

            if var_vnm <= 1e-12:
                unavail_reason = "zero_or_near_zero_vnm_variance"
            else:
                denom = math.sqrt(var_vnm * var_bmk)
                if denom > 0:
                    corr_val = cov / denom
                    # Numerical clamp tolerance
                    if corr_val > 1.0 and corr_val <= 1.000001:
                        corr_val = 1.0
                    elif corr_val < -1.0 and corr_val >= -1.000001:
                        corr_val = -1.0
                    elif abs(corr_val) > 1.000001:
                        corr_val = None
                        unavail_reason = "correlation_out_of_mathematical_range"
                    else:
                        valid_corr_count += 1

        metric_id = _hash({
            "ticker": ticker,
            "benchmark_symbol": benchmark_symbol,
            "calculation_date": calc_date,
            "window_length": window_length,
            "knowledge_cutoff": knowledge_cutoff,
            "anchor_date": effective_anchor_date,
            "version": METRIC_CONTRACT_VERSION,
        })

        metric_row = {
            "metric_result_id": metric_id,
            "ticker": ticker,
            "benchmark_symbol": benchmark_symbol,
            "metric_type": "rolling_beta_and_correlation",
            "calculation_date": calc_date,
            "window_length": window_length,
            "window_start_date": window_pairs[0]["trading_date"],
            "window_end_date": calc_date,
            "knowledge_cutoff": knowledge_cutoff,
            "anchor_date": effective_anchor_date,
            "eligible_observation_count": window_length,
            "required_observation_count": window_length,
            "beta_value": beta_val,
            "correlation_value": corr_val,
            "currency": "VND",
            "ordered_pair_ids": [p["pair_id"] for p in window_pairs],
            "upstream_lineage": {
                "vnm_factors": list(set(f for p in window_pairs for f in p.get("vnm_lineage", {}).get("applied_factor_ids", []))),
                "benchmark_observations": [p.get("benchmark_lineage", {}).get("benchmark_observation_id") for p in window_pairs if p.get("benchmark_lineage", {}).get("benchmark_observation_id")],
            },
            "metric_contract_version": METRIC_CONTRACT_VERSION,
            "qualification_state": "qualified",
            "unavailable_reason": unavail_reason,
        }
        metric_series.append(metric_row)

    return {
        "status": "available",
        "metric_contract_version": METRIC_CONTRACT_VERSION,
        "ticker": ticker,
        "benchmark_symbol": benchmark_symbol,
        "window_length": window_length,
        "knowledge_cutoff": knowledge_cutoff,
        "anchor_date": effective_anchor_date,
        "metric_series": metric_series,
        "valid_beta_count": valid_beta_count,
        "valid_correlation_count": valid_corr_count,
        "total_evaluated_dates": len(metric_series),
    }
