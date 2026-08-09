"""Producer-owned descriptive comparison for the fixed qualified historical cohort.

This module consumes already-derived historical fundamental analytics.  It never derives a
financial metric, converts currency, ranks an investment, or reads a data source.  Its only
comparisons are explicitly descriptive cross-sectional observations over the approved cohort.
"""
from __future__ import annotations

from typing import Any, Mapping

SCHEMA_VERSION = "1.0.0"
QUALIFIED_COHORT = ("HPG", "VNM", "PAN", "PVD", "NVL")
RATIO_METRICS = ("operating_cash_flow_to_net_income", "debt_to_equity", "cash_to_debt", "net_debt_to_equity")


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _metric(value: Any) -> dict[str, Any]:
    source = _map(value)
    return {
        "status": source.get("status", "unavailable"), "value": source.get("value"),
        "applicability": source.get("applicability", "blocked"),
        "reason_codes": list(source.get("reason_codes") or []),
        "source_fact_identities": list(source.get("source_fact_identities") or []),
    }


def _state_metric(metrics: Mapping[str, Any], name: str) -> dict[str, Any]:
    return _metric(metrics.get(name))


def _funding_position(metrics: Mapping[str, Any]) -> dict[str, Any]:
    metric = _state_metric(metrics, "net_debt")
    return {key: metric[key] for key in ("status", "applicability", "reason_codes", "source_fact_identities")}


def _sub_conclusions(metrics: Mapping[str, Any]) -> dict[str, Any]:
    conversion = _state_metric(metrics, "operating_cash_flow_to_net_income")
    earnings = _state_metric(metrics, "earnings_state")
    ocf = _state_metric(metrics, "operating_cash_flow_state")
    risk_codes = set(earnings.get("reason_codes") or []) | set(ocf.get("reason_codes") or [])
    if conversion["status"] != "available":
        conversion_code = "cash_conversion_not_applicable_or_unavailable"
    elif isinstance(conversion["value"], (int, float)) and conversion["value"] > 0:
        conversion_code = "positive_cash_conversion"
    else:
        conversion_code = "negative_or_zero_cash_conversion"
    if "loss_making" in risk_codes and "operating_cash_flow_negative" in risk_codes:
        stress = "combined_earnings_and_cash_flow_stress"
    elif "loss_making" in risk_codes:
        stress = "earnings_stress"
    elif "operating_cash_flow_negative" in risk_codes:
        stress = "cash_flow_stress"
    else:
        stress = "no_explicit_earnings_or_cash_flow_stress_predicate"
    return {
        "earnings_quality": {"code": conversion_code, "metric": conversion},
        "cash_flow_resilience": {"code": (ocf.get("reason_codes") or ["operating_cash_flow_unavailable"])[0], "metric": ocf},
        "historical_stress": {"code": stress, "source_metrics": [earnings, ocf]},
    }


def _position(metric_name: str, ticker: str, rows: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    values = {name: _map(_map(row.get("metrics")).get(metric_name)).get("value") for name, row in rows.items()}
    numeric = {name: value for name, value in values.items() if isinstance(value, (int, float))}
    own = numeric.get(ticker)
    if own is None:
        return {"status": "unavailable", "reason_codes": [f"{metric_name}_not_comparable_for_ticker"]}
    low, high = min(numeric.values()), max(numeric.values())
    if low == high:
        code = "equal_to_all_observed_qualified_cohort_values"
    elif own == low:
        code = "lowest_observed_in_qualified_cohort"
    elif own == high:
        code = "highest_observed_in_qualified_cohort"
    else:
        code = "between_observed_qualified_cohort_extremes"
    return {
        "status": "available", "code": code, "metric": metric_name, "value": own,
        "comparison_tickers": sorted(numeric),
        "source_fact_identities": list(_map(_map(rows[ticker].get("metrics")).get(metric_name)).get("source_fact_identities") or []),
    }


def build(analyses: Mapping[str, Mapping[str, Any]] | None) -> dict[str, Any]:
    """Build the fixed-cohort historical comparison, failing closed on an incomplete cohort."""
    source = analyses if isinstance(analyses, Mapping) else {}
    missing = [ticker for ticker in QUALIFIED_COHORT if ticker not in source]
    rows: dict[str, dict[str, Any]] = {}
    for ticker in QUALIFIED_COHORT:
        analysis = _map(source.get(ticker))
        metrics = _map(analysis.get("metrics"))
        rows[ticker] = {
            "ticker": ticker, "status": analysis.get("status", "unavailable"),
            "analysis_period": analysis.get("analysis_period"), "currency": analysis.get("currency"),
            "qualified_period_count": len(analysis.get("qualified_annual_periods") or []),
            "trend_status": analysis.get("trend_status", "insufficient_history"),
            "metrics": {name: _state_metric(metrics, name) for name in (
                "earnings_state", "operating_cash_flow_state", *RATIO_METRICS,
            )},
            "funding_position": _funding_position(metrics),
            "risk_predicates": list(analysis.get("risk_predicates") or []),
            "strength_predicates": list(analysis.get("strength_predicates") or []),
            "conclusion_code": _map(analysis.get("historical_conclusion")).get("code"),
            "sub_conclusions": _sub_conclusions(metrics),
        }
    available = not missing and all(row["status"] == "available" for row in rows.values())
    for ticker, row in rows.items():
        row["comparative_positions"] = {
            "debt_to_equity": _position("debt_to_equity", ticker, rows),
            "cash_to_debt": _position("cash_to_debt", ticker, rows),
            "net_debt_to_equity": _position("net_debt_to_equity", ticker, rows),
        }
        row["sub_conclusions"]["funding_structure"] = {
            "code": row["comparative_positions"]["debt_to_equity"].get("code", "insufficient_evidence"),
            "metric": row["comparative_positions"]["debt_to_equity"],
        }
    return {
        "schema_version": SCHEMA_VERSION, "status": "available" if available else "unavailable",
        "cohort_name": "qualified_historical_fundamental_cohort", "cohort_tickers": list(QUALIFIED_COHORT),
        "historical_only": True, "market_dependent": False, "is_actionable": False,
        "cross_sectional_comparison": "available" if available else "unavailable",
        "multi_period_trend": "insufficient_history",
        "ranking_prohibited": True, "fx_conversion_prohibited": True,
        "absolute_cross_currency_comparison_prohibited": True,
        "rows": [rows[ticker] for ticker in QUALIFIED_COHORT],
        "blocking_reasons": ["qualified_cohort_incomplete:" + ",".join(missing)] if missing else [],
        "limitations": [
            "This is a qualified cohort comparison, not a peer group or investment ranking.",
            "All current cohort rows have one complete qualified annual period; trends are unavailable.",
            "PVD remains USD; absolute monetary amounts are excluded from cross-company comparisons.",
        ],
    }
