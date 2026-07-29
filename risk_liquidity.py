"""Fail-closed market risk and liquidity metrics with PIT beta and correlation activation."""
from __future__ import annotations
import math
from pathlib import Path
from typing import Any

from point_in_time_market_risk import calculate_point_in_time_beta_and_correlation

VERSION = "1.0.0"


def out(n: str, state: str = "unavailable", **k: Any) -> dict[str, Any]:
    x = {
        "metric": n,
        "method_version": VERSION,
        "state": state,
        "applicability": "unknown",
        "observation_window": None,
        "as_of_date": None,
        "source": None,
        "provenance": {},
        "required_inputs": [],
        "used_inputs": [],
        "missing_inputs": [],
        "calculation_assumptions": [],
        "value": None,
        "unit": None,
        "benchmark": None,
        "warnings": [],
        "interpretation_limits": [],
        "is_actionable": False,
    }
    x.update(k)
    return x


def evaluate_market_risk(d: dict[str, Any] | None, reference_at: str | None = None, runtime_root: Path | None = None) -> dict[str, Any]:
    d = d if isinstance(d, dict) else {}
    ticker = d.get("ticker")
    rows = d.get("ohlcv") if isinstance(d.get("ohlcv"), list) else []
    adjusted = d.get("price_adjustment") == "qualified"
    volume_units = d.get("volume_units") == "qualified"

    # Evaluate PIT Beta & Correlation for qualified ticker (VNM)
    pit_beta = out("point_in_time_beta", "unavailable", reason="unqualified_ticker_or_missing_alignment_chain", missing_inputs=["qualified_adjusted_returns_and_benchmark_alignment_chain"])
    pit_corr = out("point_in_time_correlation", "unavailable", reason="unqualified_ticker_or_missing_alignment_chain", missing_inputs=["qualified_adjusted_returns_and_benchmark_alignment_chain"])

    if ticker == "VNM":
        root_path = runtime_root if isinstance(runtime_root, Path) else Path(".")
        risk_res = calculate_point_in_time_beta_and_correlation(root_path, ticker="VNM")
        if risk_res.get("status") == "available" and risk_res.get("metric_series"):
            last_row = risk_res["metric_series"][-1]
            if last_row.get("beta_value") is not None:
                pit_beta = out(
                    "point_in_time_beta",
                    "available",
                    value=last_row["beta_value"],
                    benchmark="VNINDEX",
                    observation_window="60_sessions",
                    as_of_date=last_row["calculation_date"],
                    provenance={
                        "metric_result_id": last_row["metric_result_id"],
                        "knowledge_cutoff": last_row["knowledge_cutoff"],
                        "anchor_date": last_row["anchor_date"],
                        "ordered_pair_ids": last_row.get("ordered_pair_ids", []),
                        "upstream_lineage": last_row.get("upstream_lineage", {}),
                    },
                    calculation_assumptions=["simple_returns", "sample_covariance_over_sample_benchmark_variance"],
                    is_actionable=True,
                )
            else:
                pit_beta = out("point_in_time_beta", "unavailable", reason=last_row.get("unavailable_reason", "insufficient_aligned_observations"), missing_inputs=["60_consecutive_aligned_vnm_vnindex_pairs"])

            if last_row.get("correlation_value") is not None:
                pit_corr = out(
                    "point_in_time_correlation",
                    "available",
                    value=last_row["correlation_value"],
                    benchmark="VNINDEX",
                    observation_window="60_sessions",
                    as_of_date=last_row["calculation_date"],
                    provenance={
                        "metric_result_id": last_row["metric_result_id"],
                        "knowledge_cutoff": last_row["knowledge_cutoff"],
                        "anchor_date": last_row["anchor_date"],
                        "ordered_pair_ids": last_row.get("ordered_pair_ids", []),
                        "upstream_lineage": last_row.get("upstream_lineage", {}),
                    },
                    calculation_assumptions=["simple_returns", "pearson_product_moment"],
                    is_actionable=True,
                )
            else:
                pit_corr = out("point_in_time_correlation", "unavailable", reason=last_row.get("unavailable_reason", "insufficient_aligned_observations"), missing_inputs=["60_consecutive_aligned_vnm_vnindex_pairs"])

    if not adjusted or len(rows) < 3:
        liq = out(
            "average_volume",
            "available" if volume_units and rows else "unavailable",
            value=sum(float(x.get("volume", 0)) for x in rows) / len(rows) if volume_units and rows else None,
            unit="provider_volume_units" if volume_units else None,
            provenance={"volume_basis": d.get("volume_basis")},
            missing_inputs=[] if volume_units and rows else ["qualified_volume_units"],
            warnings=[] if volume_units else ["volume_basis_unqualified_or_incompatible"],
        )
        return {
            "schema_version": VERSION,
            "reference_at": reference_at,
            "dimensions": {
                "market_risk": "available" if (pit_beta["state"] == "available" or pit_corr["state"] == "available") else "unavailable",
                "liquidity": "available" if liq["state"] == "available" else "unavailable",
                "concentration": "unavailable",
                "position_sizing_readiness": "unavailable",
                "data_confidence": "partial" if (liq["state"] == "available" or pit_beta["state"] == "available") else "unknown",
            },
            "position_sizing": {"state": "unavailable", "reason": "holdings_cash_risk_budget_and_qualified_risk_inputs_required", "is_actionable": False},
            "market_risk": {
                "realized_volatility": out("realized_volatility", missing_inputs=["qualified_adjusted_price_series"], warnings=["Do not mix adjusted and unadjusted returns."]),
                "downside_volatility": out("downside_volatility", missing_inputs=["qualified_adjusted_price_series"]),
                "maximum_drawdown": out("maximum_drawdown", missing_inputs=["qualified_adjusted_price_series"]),
                "point_in_time_beta": pit_beta,
                "point_in_time_correlation": pit_corr,
            },
            "liquidity_risk": {
                "average_volume": liq,
                "days_to_liquidate": out("days_to_liquidate", missing_inputs=["portfolio_order_size", "participation_rate", "qualified_volume_units"]),
            },
            "portfolio_risk": {"state": "unavailable", "reason": "holdings_cash_and_risk_budget_contract_absent"},
            "backtest_summary": {"state": "unavailable", "reason": "point_in_time_signals_absent"},
        }

    closes = [float(x["close"]) for x in rows if x.get("close") not in (None, 0)]
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    mean = sum(rets) / len(rets)
    vol = (sum((x - mean) ** 2 for x in rets) / len(rets)) ** 0.5
    down = (sum(min(0, x) ** 2 for x in rets) / len(rets)) ** 0.5
    peak = closes[0]
    mdd = 0.0
    for c in closes:
        peak = max(peak, c)
        mdd = min(mdd, c / peak - 1.0)

    liq = out("average_volume", "available" if volume_units else "unavailable", value=sum(float(x.get("volume", 0)) for x in rows) / len(rows) if volume_units else None, unit="provider_volume_units", warnings=[] if volume_units else ["volume_units_unqualified"])

    return {
        "schema_version": VERSION,
        "reference_at": reference_at,
        "dimensions": {
            "market_risk": "available",
            "liquidity": "available" if liq["state"] == "available" else "unavailable",
            "concentration": "unavailable",
            "position_sizing_readiness": "unavailable",
            "data_confidence": "partial",
        },
        "position_sizing": {"state": "unavailable", "reason": "holdings_cash_risk_budget_and_qualified_risk_inputs_required", "is_actionable": False},
        "market_risk": {
            "realized_volatility": out("realized_volatility", "available", value=vol, unit="per_observation_return", is_actionable=bool(d.get("current_actionable"))),
            "downside_volatility": out("downside_volatility", "available", value=down, unit="per_observation_return"),
            "maximum_drawdown": out("maximum_drawdown", "available", value=mdd, unit="fraction"),
            "point_in_time_beta": pit_beta,
            "point_in_time_correlation": pit_corr,
        },
        "liquidity_risk": {
            "average_volume": liq,
            "days_to_liquidate": out("days_to_liquidate", missing_inputs=["user_order_size_and_participation_rate"]),
        },
        "portfolio_risk": {"state": "unavailable", "reason": "holdings_contract_absent"},
        "backtest_summary": {"state": "unavailable", "reason": "point_in_time_signals_absent"},
    }
