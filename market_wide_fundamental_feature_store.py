"""Compatibility-aware, research-only fundamental feature store over period semantics."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from financial_entity_applicability import FINANCIAL_ENTITY_TYPES, load_entity_profiles

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "market_wide_fundamental_feature_store/v1"
COMPATIBILITY_VERSION = "same_native_series_research_compatibility/v2"
ARTIFACT_TYPE = "MARKET_WIDE_FUNDAMENTAL_FEATURE_STORE"
EXACT = "EXACT_TYPED_RESEARCH_COMPATIBLE"
NATIVE = "SAME_NATIVE_SERIES_RESEARCH_COMPATIBLE"
PIT = "POINT_IN_TIME_TRAJECTORY_COMPATIBLE"
BLOCKED = "BLOCKED_INCOMPATIBLE"
READY = "READY_RESEARCH"
PROXY = "READY_RESEARCH_PROXY"
PARTIAL = "PARTIAL_RESEARCH"
FEATURE_BLOCKED = "BLOCKED"
FLOW = frozenset({"income_statement", "cash_flow"})
FEATURE_FAMILY = {
    "revenue_same_period_yoy": "GROWTH_TRAJECTORY", "net_income_same_period_yoy": "GROWTH_TRAJECTORY",
    "revenue_ttm_sum": "GROWTH_TRAJECTORY", "net_income_ttm_sum": "GROWTH_TRAJECTORY",
    "operating_cash_flow_ttm_sum": "CASH_EARNINGS_QUALITY",
    "net_margin": "PROFITABILITY_MARGIN", "gross_margin": "PROFITABILITY_MARGIN", "profit_state": "PROFITABILITY",
    "operating_cash_flow_sign": "CASH_EARNINGS_QUALITY", "cfo_to_net_income": "CASH_EARNINGS_QUALITY", "cash_earnings_alignment": "CASH_EARNINGS_QUALITY",
    "total_assets_pit_trajectory": "BALANCE_SHEET_HEALTH", "shareholders_equity_pit_trajectory": "BALANCE_SHEET_HEALTH",
    "cash_and_cash_equivalents_pit_trajectory": "BALANCE_SHEET_HEALTH", "cash_to_assets": "BALANCE_SHEET_HEALTH",
    "equity_to_assets": "LEVERAGE_SOLVENCY", "debt_to_equity": "LEVERAGE_SOLVENCY",
    "roa_eop_proxy": "CAPITAL_EFFICIENCY", "roe_eop_proxy": "CAPITAL_EFFICIENCY",
}
ROOT = Path(__file__).resolve().parent
DEFAULT_SEMANTICS = ROOT / "operations-review" / "market-wide-structured-financial-period-semantics-v1-20260831" / "structured_financial_period_semantics_facts.jsonl.gz"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {k: v for k, v in value.items() if k not in {"artifact_sha256", "artifact_identity", "requested_at"}}
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (str(row["source_lineage"].get("provider")), str(row["source_lineage"].get("source_file")),
            str(row.get("statement_scope")), str(row.get("period_semantic_state")))


def _feature(feature_id: str, *, value: Any, status: str, compatibility: str, method: str,
             inputs: Sequence[Mapping[str, Any]] = (), blockers: Sequence[str] = (), state: str | None = None) -> dict[str, Any]:
    return {
        "feature_id": feature_id, "value": value, "categorical_state": state,
        "status": status, "method": method, "compatibility_class": compatibility,
        "compatibility_rule_version": COMPATIBILITY_VERSION,
        "input_periods": [item.get("native_period_label") or item.get("period_end") for item in inputs],
        "duration_semantics": sorted({str(item.get("period_semantic_state")) for item in inputs}),
        "scope": sorted({str(item.get("statement_scope")) for item in inputs}),
        "provider_source_lineage": [item.get("source_lineage") for item in inputs],
        "native_field_lineage": [
            {"canonical_metric": item.get("canonical_metric"), "source_file": item.get("source_lineage", {}).get("source_file"),
             "raw_item_id": item.get("source_lineage", {}).get("raw_item_id")} for item in inputs
        ],
        "calculation_lineage": {"method": method, "input_count": len(inputs)},
        "blocker_reason_codes": list(blockers), "research_fitness": status,
        "authority_tier": "OPERATIONAL_PROVIDER_RESEARCH_ONLY", "authoritative_financial_eligible": False,
        "pit_backtest_eligible": False, "is_actionable": False,
    }


def _blocked(feature_id: str, *reasons: str, state: str | None = None) -> dict[str, Any]:
    return _feature(feature_id, value=None, status=FEATURE_BLOCKED, compatibility=BLOCKED,
                    method="blocked_feature_contract/v1", blockers=reasons, state=state)


def _usable(row: Mapping[str, Any], semantic: str | None = None) -> bool:
    return (row.get("source_status") == "provider_reported" and row.get("lineage_complete")
            and not row.get("source_conflicts") and _numeric(row.get("reported_value"))
            and (semantic is None or row.get("period_semantic_state") == semantic))


def _groups(rows: Sequence[Mapping[str, Any]], metric: str, semantic: str) -> dict[tuple[str, str, str, str], dict[str, Mapping[str, Any]]]:
    out: dict[tuple[str, str, str, str], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        if _usable(row, semantic) and row.get("canonical_metric") == metric:
            out[_key(row)][str(row.get("native_period_label") or row.get("period_end"))] = row
    return out


def _best(groups: Mapping[tuple[str, str, str, str], Mapping[str, Mapping[str, Any]]]) -> Mapping[str, Mapping[str, Any]]:
    return max(groups.values(), key=lambda rows: (len(rows), sorted(rows)[-1] if rows else ""), default={})


def _latest(rows: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return rows[max(rows)] if rows else None


def _quarter_key(label: Any) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d{4})-Q([1-4])", str(label))
    return (int(match.group(1)), int(match.group(2))) if match else None


def _quarter_label(year: int, quarter: int) -> str:
    return f"{year}-Q{quarter}"


def _prior_quarter(year: int, quarter: int) -> tuple[int, int]:
    return (year - 1, 4) if quarter == 1 else (year, quarter - 1)


def _same_period_pair(rows: Sequence[Mapping[str, Any]], numerator: str, denominator: str,
                      semantic: str = "STANDALONE_QUARTER") -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    left, right = _groups(rows, numerator, semantic), _groups(rows, denominator, semantic)
    candidates = []
    for key in set(left) & set(right):
        periods = set(left[key]) & set(right[key])
        if periods:
            period = max(periods); candidates.append((period, left[key][period], right[key][period]))
    return (max(candidates, key=lambda item: item[0])[1:]) if candidates else None


def _yoy(rows: Mapping[str, Mapping[str, Any]], feature_id: str, *, earnings: bool = False) -> dict[str, Any]:
    current = _latest(rows)
    current_key = _quarter_key(current.get("native_period_label")) if current else None
    if not current or not current_key:
        return _blocked(feature_id, "MISSING_COMPATIBLE_STANDALONE_QUARTER_SERIES")
    prior_label = _quarter_label(current_key[0] - 1, current_key[1])
    prior = rows.get(prior_label)
    if not prior:
        return _blocked(feature_id, "MISSING_SAME_QUARTER_PRIOR_YEAR")
    old, new = prior["reported_value"], current["reported_value"]
    if earnings and (old <= 0 or new <= 0):
        state = ("TURNAROUND_TO_PROFIT" if old < 0 < new else "TURNED_TO_LOSS" if old > 0 > new
                 else "LOSS_NARROWED" if old < 0 and new > old else "LOSS_WIDENED" if old < 0 else "ZERO_BASE_EARNINGS")
        return _feature(feature_id, value=None, status=PARTIAL, compatibility=NATIVE,
                        method="same_native_series_sign_transition/v1", inputs=[prior, current], state=state)
    if old == 0:
        return _blocked(feature_id, "ZERO_PRIOR_PERIOD_DENOMINATOR")
    return _feature(feature_id, value=new / old - 1, status=PROXY, compatibility=NATIVE,
                    method="same_native_series_same_quarter_yoy/v1", inputs=[prior, current],
                    state="PROFIT_GROWTH" if earnings and new > old else "PROFIT_DECLINE" if earnings else None)


def _ttm(rows: Mapping[str, Mapping[str, Any]], feature_id: str) -> dict[str, Any]:
    """Return a four-consecutive-quarter sum from one compatible native series only."""
    current = _latest(rows)
    current_key = _quarter_key(current.get("native_period_label")) if current else None
    if not current or not current_key:
        return _blocked(feature_id, "MISSING_CONSECUTIVE_STANDALONE_QUARTER_INPUTS")
    required_labels: list[str] = []
    year, quarter = current_key
    for _ in range(4):
        required_labels.append(_quarter_label(year, quarter))
        year, quarter = _prior_quarter(year, quarter)
    inputs = [rows.get(label) for label in reversed(required_labels)]
    if any(item is None for item in inputs):
        return _blocked(feature_id, "MISSING_CONSECUTIVE_STANDALONE_QUARTER_INPUTS")
    concrete_inputs = [item for item in inputs if item is not None]
    if any(item.get("period_semantic_state") != "STANDALONE_QUARTER" for item in concrete_inputs):
        return _blocked(feature_id, "MISSING_CONSECUTIVE_STANDALONE_QUARTER_INPUTS")
    exact = all(not item.get("metadata_missing", {}).get("unit", True) for item in concrete_inputs)
    return _feature(feature_id, value=sum(item["reported_value"] for item in concrete_inputs),
                    status=READY if exact else PROXY, compatibility=EXACT if exact else NATIVE,
                    method="TTM_SUM_RESEARCH" if exact else "TTM_SUM_PROXY", inputs=concrete_inputs)


def _ratio(feature_id: str, pair: tuple[Mapping[str, Any], Mapping[str, Any]] | None, *, state: str | None = None) -> dict[str, Any]:
    if not pair:
        return _blocked(feature_id, "MISSING_SAME_NATIVE_PERIOD_SCOPE_SERIES")
    numerator, denominator = pair
    if denominator["reported_value"] == 0:
        return _blocked(feature_id, "ZERO_DENOMINATOR")
    return _feature(feature_id, value=numerator["reported_value"] / denominator["reported_value"], status=PROXY,
                    compatibility=NATIVE, method="same_native_series_dimensionless_ratio/v1",
                    inputs=[numerator, denominator], state=state)


def _trajectory(rows: Sequence[Mapping[str, Any]], metric: str) -> dict[str, Any]:
    series = _best(_groups(rows, metric, "POINT_IN_TIME_BALANCE_SHEET"))
    if len(series) < 2:
        return _blocked(f"{metric}_pit_trajectory", "MISSING_COMPATIBLE_POINT_IN_TIME_SERIES")
    ordered = [series[key] for key in sorted(series)]
    prior, current = ordered[-2:]
    state = "IMPROVING" if current["reported_value"] > prior["reported_value"] else "WEAKENING" if current["reported_value"] < prior["reported_value"] else "STABLE"
    return _feature(f"{metric}_pit_trajectory", value=current["reported_value"] / prior["reported_value"] - 1 if prior["reported_value"] else None,
                    status=PROXY if prior["reported_value"] else PARTIAL, compatibility=PIT,
                    method="same_native_point_in_time_trajectory/v1", inputs=[prior, current], state=state)


def _pit_ratio(rows: Sequence[Mapping[str, Any]], feature_id: str, numerator: str, denominator: str) -> dict[str, Any]:
    return _ratio(feature_id, _same_period_pair(rows, numerator, denominator, "POINT_IN_TIME_BALANCE_SHEET"))


def _entity_state(ticker: str, profiles: Mapping[str, str]) -> tuple[str, str | None]:
    entity = profiles.get(ticker)
    if entity in FINANCIAL_ENTITY_TYPES:
        return "GENERIC_CORPORATE_FEATURE_NOT_APPLICABLE", entity
    return "GENERIC_RESEARCH_PRIMITIVES_ALLOWED", entity


def _compact_feature(feature: Mapping[str, Any]) -> dict[str, Any]:
    """Serving-safe projection: current feature state without raw history or detailed lineage."""
    return {
        "feature_id": feature["feature_id"], "value": feature["value"],
        "categorical_state": feature["categorical_state"], "status": feature["status"],
        "method": feature["method"], "compatibility_class": feature["compatibility_class"],
        "input_periods": list(feature["input_periods"]),
        "blocker_reason_codes": list(feature["blocker_reason_codes"]),
        "research_fitness": feature["research_fitness"],
        "authoritative_financial_eligible": False, "is_actionable": False,
    }


def build_ticker_record(ticker: str, rows: Sequence[Mapping[str, Any]], profiles: Mapping[str, str]) -> dict[str, Any]:
    entity_applicability, entity_type = _entity_state(ticker, profiles)
    revenue = _best(_groups(rows, "revenue", "STANDALONE_QUARTER"))
    earnings = _best(_groups(rows, "net_income", "STANDALONE_QUARTER"))
    ocf = _best(_groups(rows, "operating_cash_flow", "STANDALONE_QUARTER"))
    features = {
        "revenue_same_period_yoy": _yoy(revenue, "revenue_same_period_yoy"),
        "net_income_same_period_yoy": _yoy(earnings, "net_income_same_period_yoy", earnings=True),
        "revenue_ttm_sum": _ttm(revenue, "revenue_ttm_sum"),
        "net_income_ttm_sum": _ttm(earnings, "net_income_ttm_sum"),
        "operating_cash_flow_ttm_sum": _ttm(ocf, "operating_cash_flow_ttm_sum"),
        "net_margin": _ratio("net_margin", _same_period_pair(rows, "net_income", "revenue")),
        "gross_margin": _ratio("gross_margin", _same_period_pair(rows, "gross_profit", "revenue")),
        "total_assets_pit_trajectory": _trajectory(rows, "total_assets"),
        "shareholders_equity_pit_trajectory": _trajectory(rows, "shareholders_equity"),
        "cash_and_cash_equivalents_pit_trajectory": _trajectory(rows, "cash_and_cash_equivalents"),
        "cash_to_assets": _pit_ratio(rows, "cash_to_assets", "cash_and_cash_equivalents", "total_assets"),
        "equity_to_assets": _pit_ratio(rows, "equity_to_assets", "shareholders_equity", "total_assets"),
        "debt_to_equity": _pit_ratio(rows, "debt_to_equity", "total_interest_bearing_debt", "shareholders_equity"),
        "roa_eop_proxy": _blocked("roa_eop_proxy", "CROSS_PROVIDER_OR_DURATION_INCOMPATIBLE"),
        "roe_eop_proxy": _blocked("roe_eop_proxy", "CROSS_PROVIDER_OR_DURATION_INCOMPATIBLE"),
    }
    latest_earnings, latest_ocf = _latest(earnings), _latest(ocf)
    features["profit_state"] = (_feature("profit_state", value=latest_earnings["reported_value"], status=PROXY, compatibility=NATIVE,
                                          method="same_native_latest_sign/v1", inputs=[latest_earnings],
                                          state="PROFITABLE" if latest_earnings["reported_value"] > 0 else "LOSS_MAKING" if latest_earnings["reported_value"] < 0 else "BREAK_EVEN")
                                if latest_earnings else _blocked("profit_state", "MISSING_STANDALONE_QUARTER_EARNINGS"))
    features["operating_cash_flow_sign"] = (_feature("operating_cash_flow_sign", value=latest_ocf["reported_value"], status=PROXY, compatibility=NATIVE,
                                                       method="same_native_latest_sign/v1", inputs=[latest_ocf],
                                                       state="POSITIVE_CFO" if latest_ocf["reported_value"] > 0 else "NEGATIVE_CFO" if latest_ocf["reported_value"] < 0 else "ZERO_CFO")
                                           if latest_ocf else _blocked("operating_cash_flow_sign", "MISSING_STANDALONE_QUARTER_CFO"))
    features["cfo_to_net_income"] = _ratio("cfo_to_net_income", _same_period_pair(rows, "operating_cash_flow", "net_income"))
    cash_pair = _same_period_pair(rows, "operating_cash_flow", "net_income")
    features["cash_earnings_alignment"] = (_feature("cash_earnings_alignment", value=None, status=PROXY, compatibility=NATIVE,
                                                       method="same_native_cash_earnings_sign_alignment/v1", inputs=list(cash_pair),
                                                       state="NEGATIVE_CFO_WITH_PROFIT" if cash_pair[0]["reported_value"] < 0 < cash_pair[1]["reported_value"] else "CASH_BACKED_EARNINGS" if cash_pair[0]["reported_value"] > 0 and cash_pair[1]["reported_value"] > 0 else "EARNINGS_AHEAD_OF_CASH")
                                          if cash_pair else _blocked("cash_earnings_alignment", "MISSING_SAME_NATIVE_PERIOD_SCOPE_SERIES", state="CASH_QUALITY_UNAVAILABLE"))
    if entity_applicability != "GENERIC_RESEARCH_PRIMITIVES_ALLOWED":
        for feature_id in ("cash_to_assets", "equity_to_assets"):
            features[feature_id] = _blocked(feature_id, "GENERIC_CORPORATE_FEATURE_NOT_APPLICABLE", state=entity_type)
    ready = [item for item in features.values() if item["status"] in {READY, PROXY, PARTIAL}]
    axes = {
        "PROFITABILITY_STATE": features["profit_state"]["categorical_state"] or "INSUFFICIENT_DATA",
        "GROWTH_STATE": features["net_income_same_period_yoy"]["categorical_state"] or "INSUFFICIENT_DATA",
        "MARGIN_STATE": "AVAILABLE" if features["net_margin"]["status"] == PROXY else "INSUFFICIENT_DATA",
        "CASH_QUALITY_STATE": "CASH_QUALITY_UNAVAILABLE",
        "BALANCE_SHEET_STATE": features["total_assets_pit_trajectory"]["categorical_state"] or "INSUFFICIENT_DATA",
        "LEVERAGE_STATE": "GENERIC_CORPORATE_FEATURE_NOT_APPLICABLE" if entity_applicability != "GENERIC_RESEARCH_PRIMITIVES_ALLOWED" else "INSUFFICIENT_DATA",
        "CAPITAL_EFFICIENCY_STATE": "INSUFFICIENT_DATA",
        "DATA_COVERAGE_STATE": "READY_RESEARCH_PROXY" if ready else "INSUFFICIENT_DATA",
    }
    context = {"availability": "PRODUCT_READY_RESEARCH_CONTEXT" if ready else "INSUFFICIENT_DATA",
               "projection_contract_version": "fundamental_feature_context/v2",
               "health_axes": axes, "ready_feature_count": len(ready),
               "current_features": {feature_id: _compact_feature(feature) for feature_id, feature in sorted(features.items())},
               "source_provider_summary": sorted({str(row["source_lineage"].get("provider")) for row in rows if row["source_lineage"].get("provider")}),
               "warnings_blockers": sorted({code for item in features.values() for code in item["blocker_reason_codes"]}),
               "research_authority_boundary": "OPERATIONAL_PROVIDER_RESEARCH_ONLY_NOT_AUTHORITATIVE"}
    return {"ticker": ticker, "entity_type": entity_type, "entity_applicability": entity_applicability,
            "features": features, "fundamental_feature_context": context, "authority_boundary": {"authoritative": False, "pit": False, "actionable": False}}


def build_artifact(*, semantic_rows: Sequence[Mapping[str, Any]], period_semantics_identity: str, requested_at: str,
                   profiles: Mapping[str, str] | None = None) -> dict[str, Any]:
    profiles = profiles or load_entity_profiles(ROOT / "config" / "ticker_entity_profiles.csv")
    by_ticker: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in semantic_rows:
        by_ticker[str(row.get("ticker"))].append(row)
    records = {ticker: build_ticker_record(ticker, rows, profiles) for ticker, rows in sorted(by_ticker.items())}
    features = [feature for record in records.values() for feature in record["features"].values()]
    family = Counter(FEATURE_FAMILY.get(feature["feature_id"], "OTHER") for feature in features)
    compatibility = Counter(feature["compatibility_class"] for feature in features)
    blockers = Counter(reason for feature in features for reason in feature["blocker_reason_codes"])
    semantic_coverage = Counter(state for feature in features for state in feature["duration_semantics"])
    successful = sorted((record for record in records.values() if record["fundamental_feature_context"]["ready_feature_count"]),
                        key=lambda record: (-record["fundamental_feature_context"]["ready_feature_count"], record["ticker"]))[:5]
    blocked = sorted((record for record in records.values() if not record["fundamental_feature_context"]["ready_feature_count"]),
                     key=lambda record: record["ticker"])[:5]
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION, "artifact_type": ARTIFACT_TYPE,
        "requested_at": requested_at, "input_period_semantics_identity": period_semantics_identity,
        "compatibility_rule_version": COMPATIBILITY_VERSION, "records": records,
        "coverage": {"ticker_denominator": len(records), "ticker_record_count": len(records),
                     "zero_silent_ticker_drops": len(records) == len(by_ticker),
                     "tickers_with_ready_feature": sum(record["fundamental_feature_context"]["ready_feature_count"] >= 1 for record in records.values()),
                     "tickers_with_three_feature_families": sum(len({FEATURE_FAMILY.get(key, "OTHER") for key, value in record["features"].items() if value["status"] in {READY, PROXY, PARTIAL}}) >= 3 for record in records.values()),
                     "tickers_with_product_ready_health_context": sum(record["fundamental_feature_context"]["availability"] == "PRODUCT_READY_RESEARCH_CONTEXT" for record in records.values()),
                     "total_emitted_feature_count": len(features), "feature_counts_by_family": dict(sorted(family.items())),
                     "exact_vs_proxy_counts": {"EXACT_TYPED_RESEARCH_COMPATIBLE": sum(feature["compatibility_class"] == EXACT for feature in features),
                                               "RESEARCH_PROXY_COMPATIBLE": sum(feature["compatibility_class"] in {NATIVE, PIT} for feature in features)},
                     "feature_status_distribution": dict(sorted(Counter(feature["status"] for feature in features).items())),
                     "compatibility_class_distribution": dict(sorted(compatibility.items())),
                     "period_semantic_coverage": dict(sorted(semantic_coverage.items())),
                     "generic_corporate_applicability_exclusions": sum(record["entity_applicability"] != "GENERIC_RESEARCH_PRIMITIVES_ALLOWED" for record in records.values()),
                     "provider_source_coverage": dict(sorted(Counter(provider for record in records.values() for provider in record["fundamental_feature_context"]["source_provider_summary"]).items()))},
        "blocker_distribution": dict(sorted(blockers.items())),
        "health_context_coverage": dict(sorted(Counter(record["fundamental_feature_context"]["availability"] for record in records.values()).items())),
        "representative_successful_tickers": [{"ticker": record["ticker"], "ready_feature_count": record["fundamental_feature_context"]["ready_feature_count"], "health_axes": record["fundamental_feature_context"]["health_axes"]} for record in successful],
        "representative_blocked_tickers": [{"ticker": record["ticker"], "warnings_blockers": record["fundamental_feature_context"]["warnings_blockers"]} for record in blocked],
        "authority_effect": "NONE / OPERATIONAL_PROVIDER_RESEARCH_ONLY",
        "feature_definitions": "per-ticker feature records retain compatibility, input period, native/provider lineage, blockers, research fitness, and non-authoritative boundary",
    }
    artifact.update(content_identity(artifact))
    return artifact
