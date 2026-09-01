"""Deterministic issuer-level financial research context over retained semantics.

This module is deliberately downstream of canonical facts and period semantics.  It
does not acquire evidence, infer duration from labels, widen a financial schema, or
alter investment/valuation decision machines.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "financial_analysis_context/v2"
SCHEMA_VERSION = "2.0.0"
FITNESS = ("READY", "RESEARCH_PROXY", "BLOCKED_BY_EVIDENCE", "NOT_APPLICABLE")
INDUSTRIAL = "INDUSTRIAL_FINANCIAL_ANALYSIS"
LIMITED = "OTHER_FINANCIAL_LIMITED_ANALYSIS"
NON_INDUSTRIAL = frozenset({"bank", "securities", "insurance", "finance_company", "unknown", None, ""})
FLOW_STANDALONE = "STANDALONE_QUARTER"
PIT = "POINT_IN_TIME_BALANCE_SHEET"
UNKNOWN = "UNKNOWN_DURATION"
PERIOD_SEMANTICS = frozenset({FLOW_STANDALONE, "YTD_CUMULATIVE_INTERIM", "ANNUAL", PIT, UNKNOWN})


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: value for key, value in artifact.items()
               if key not in {"artifact_sha256", "artifact_identity", "requested_at"}}
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _quarter(value: Any) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d{4})-Q([1-4])", str(value or ""))
    return (int(match.group(1)), int(match.group(2))) if match else None


def normalize_period_semantic(value: Any) -> str:
    """Fail closed to UNKNOWN_DURATION; duration is never inferred from a label."""
    return str(value) if str(value) in PERIOD_SEMANTICS else UNKNOWN


def _prior_quarter(key: tuple[int, int]) -> tuple[int, int]:
    return (key[0] - 1, 4) if key[1] == 1 else (key[0], key[1] - 1)


def _row_usable(row: Mapping[str, Any], semantic: str | None = None) -> bool:
    lineage = row.get("source_lineage") or {}
    return (
        row.get("source_status") == "provider_reported"
        and row.get("lineage_complete") is True
        and not row.get("source_conflicts")
        and _numeric(row.get("reported_value"))
        and all(lineage.get(key) not in (None, "", "unknown") for key in ("provider", "source_file", "source_sha256", "fact_id"))
        and (semantic is None or normalize_period_semantic(row.get("period_semantic_state")) == semantic)
    )


def _source_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str, str]:
    lineage = row["source_lineage"]
    unit = row.get("normalized_candidate_unit") or {}
    return (
        str(row.get("ticker")), str(lineage.get("provider")), str(lineage.get("source_file")),
        str(row.get("statement_scope")), str(unit.get("currency")), str(unit.get("scale")),
    )


def _feature(feature_id: str, *, value: Any = None, fitness: str = "BLOCKED_BY_EVIDENCE",
             method: str, inputs: Sequence[Mapping[str, Any]] = (), reason_codes: Sequence[str] = (),
             warnings: Sequence[str] = (), growth_basis: str | None = None,
             semantic_transition: str | None = None) -> dict[str, Any]:
    return {
        "feature_id": feature_id, "value": value, "fitness": fitness, "method": method,
        "growth_basis": growth_basis, "semantic_transition": semantic_transition,
        "period_identity": [str(row.get("native_period_label") or row.get("period_end")) for row in inputs],
        "provider_source_provenance": [
            {"provider": (row.get("source_lineage") or {}).get("provider"),
             "source_file": (row.get("source_lineage") or {}).get("source_file"),
             "source_sha256": (row.get("source_lineage") or {}).get("source_sha256"),
             "fact_id": (row.get("source_lineage") or {}).get("fact_id")} for row in inputs
        ],
        "scope": sorted({str(row.get("statement_scope")) for row in inputs}),
        "period_semantics": sorted({str(row.get("period_semantic_state")) for row in inputs}),
        "reason_codes": list(reason_codes), "warnings": list(warnings), "is_actionable": False,
    }


def _blocked(feature_id: str, *codes: str, method: str = "blocked_by_evidence/v2", growth_basis: str | None = None) -> dict[str, Any]:
    return _feature(feature_id, method=method, reason_codes=codes, growth_basis=growth_basis)


def _not_applicable(feature_id: str) -> dict[str, Any]:
    return _feature(feature_id, fitness="NOT_APPLICABLE", method="entity_applicability/v2",
                    reason_codes=["ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE"])


def _groups(rows: Sequence[Mapping[str, Any]], metric: str, semantic: str) -> dict[tuple[str, str, str, str, str, str], dict[str, Mapping[str, Any]]]:
    grouped: dict[tuple[str, str, str, str, str, str], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        if _row_usable(row, semantic) and row.get("canonical_metric") == metric:
            grouped[_source_key(row)][str(row.get("native_period_label") or row.get("period_end"))] = row
    return grouped


def _best_series(rows: Sequence[Mapping[str, Any]], metric: str, semantic: str) -> dict[str, Mapping[str, Any]]:
    groups = _groups(rows, metric, semantic)
    return max(groups.values(), key=lambda series: (len(series), sorted(series)[-1] if series else ""), default={})


def _latest(series: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return series[max(series)] if series else None


def _same_period_pair(rows: Sequence[Mapping[str, Any]], numerator: str, denominator: str,
                      semantic: str) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    left, right = _groups(rows, numerator, semantic), _groups(rows, denominator, semantic)
    candidates: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = []
    for key in set(left) & set(right):
        for period in set(left[key]) & set(right[key]):
            candidates.append((period, left[key][period], right[key][period]))
    return max(candidates, key=lambda item: item[0])[1:] if candidates else None


def _cross_statement_same_representation_pair(rows: Sequence[Mapping[str, Any]], numerator: str, denominator: str,
                                               semantic: str) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    def index(metric: str) -> dict[tuple[str, str, str, str, str], dict[str, Mapping[str, Any]]]:
        result: dict[tuple[str, str, str, str, str], dict[str, Mapping[str, Any]]] = defaultdict(dict)
        for row in rows:
            if _row_usable(row, semantic) and row.get("canonical_metric") == metric:
                unit = row.get("normalized_candidate_unit") or {}
                key = (str(row.get("ticker")), str((row.get("source_lineage") or {}).get("provider")),
                       str(row.get("statement_scope")), str(unit.get("currency")), str(unit.get("scale")))
                result[key][str(row.get("native_period_label") or row.get("period_end"))] = row
        return result
    left, right = index(numerator), index(denominator)
    candidates = [(period, left[key][period], right[key][period]) for key in set(left) & set(right)
                  for period in set(left[key]) & set(right[key])]
    return max(candidates, key=lambda item: item[0])[1:] if candidates else None


def _ratio(feature_id: str, pair: tuple[Mapping[str, Any], Mapping[str, Any]] | None, *, method: str) -> dict[str, Any]:
    if not pair:
        return _blocked(feature_id, "MISSING_SAME_PROVIDER_TICKER_PERIOD_SCOPE_REPRESENTATION")
    numerator, denominator = pair
    if denominator["reported_value"] == 0:
        return _blocked(feature_id, "ZERO_DENOMINATOR")
    return _feature(feature_id, value=numerator["reported_value"] / denominator["reported_value"], fitness="READY",
                    method=method, inputs=[numerator, denominator])


def _growth(feature_id: str, series: Mapping[str, Mapping[str, Any]], *, basis: str,
            earnings: bool = False) -> dict[str, Any]:
    current = _latest(series)
    if not current:
        return _blocked(feature_id, "MISSING_COMPATIBLE_SERIES", growth_basis=basis)
    current_key = _quarter(current.get("native_period_label"))
    if not current_key:
        return _blocked(feature_id, "PERIOD_LABEL_NOT_QUARTER_KEY", growth_basis=basis)
    if basis == "QOQ_STANDALONE":
        prior = series.get(f"{_prior_quarter(current_key)[0]}-Q{_prior_quarter(current_key)[1]}")
        if not prior:
            return _blocked(feature_id, "MISSING_CONSECUTIVE_STANDALONE_QUARTER_INPUTS", growth_basis=basis)
    elif basis in {"SAME_QUARTER_YOY", "YTD_YOY"}:
        prior = series.get(f"{current_key[0] - 1}-Q{current_key[1]}")
        if not prior:
            return _blocked(feature_id, "MISSING_SAME_QUARTER_PRIOR_YEAR", growth_basis=basis)
    else:
        return _blocked(feature_id, "UNSUPPORTED_GROWTH_BASIS", growth_basis=basis)
    old, new = prior["reported_value"], current["reported_value"]
    if old <= 0:
        transition = (
            "LOSS_TO_PROFIT" if old < 0 < new else "PROFIT_TO_LOSS" if old > 0 > new
            else "LOSS_NARROWED" if old < 0 and new > old else "LOSS_WIDENED" if old < 0
            else "ZERO_BASE"
        )
        return _feature(feature_id, fitness="READY", method="compatible_period_sign_transition/v2",
                        inputs=[prior, current], growth_basis=basis, semantic_transition=transition,
                        warnings=["GROWTH_BASE_NON_POSITIVE"])
    return _feature(feature_id, value=new / old - 1, fitness="READY", method="compatible_period_growth/v2",
                    inputs=[prior, current], growth_basis=basis)


def _ttm_sum(series: Mapping[str, Mapping[str, Any]], feature_id: str) -> tuple[dict[str, Any], list[Mapping[str, Any]]]:
    current = _latest(series)
    current_key = _quarter(current.get("native_period_label")) if current else None
    if not current_key:
        return _blocked(feature_id, "MISSING_CONSECUTIVE_STANDALONE_QUARTER_INPUTS", method="ttm_rolling_four/v2"), []
    labels = []
    key = current_key
    for _ in range(4):
        labels.append(f"{key[0]}-Q{key[1]}")
        key = _prior_quarter(key)
    inputs = [series.get(label) for label in reversed(labels)]
    if any(row is None for row in inputs):
        return _blocked(feature_id, "MISSING_CONSECUTIVE_STANDALONE_QUARTER_INPUTS", method="ttm_rolling_four/v2"), []
    concrete = [row for row in inputs if row is not None]
    return _feature(feature_id, value=sum(row["reported_value"] for row in concrete), fitness="READY",
                    method="four_consecutive_compatible_standalone_quarters/v2", inputs=concrete,
                    growth_basis="TTM"), concrete


def _ttm_yoy(feature_id: str, series: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    current, inputs = _ttm_sum(series, feature_id + "_current_ttm")
    if current["fitness"] != "READY" or not inputs:
        return _blocked(feature_id, "MISSING_CONSECUTIVE_STANDALONE_QUARTER_INPUTS", growth_basis="TTM")
    prior_inputs = []
    for row in inputs:
        key = _quarter(row.get("native_period_label"))
        label = f"{key[0] - 1}-Q{key[1]}" if key else ""
        prior = series.get(label)
        if not prior:
            return _blocked(feature_id, "MISSING_PRIOR_YEAR_TTM_WINDOW", growth_basis="TTM")
        prior_inputs.append(prior)
    old = sum(row["reported_value"] for row in prior_inputs)
    new = current["value"]
    if old <= 0:
        return _feature(feature_id, fitness="READY", method="compatible_ttm_sign_transition/v2",
                        inputs=prior_inputs + inputs, growth_basis="TTM", warnings=["GROWTH_BASE_NON_POSITIVE"],
                        semantic_transition="LOSS_TO_PROFIT" if old < 0 < new else "PROFIT_TO_LOSS" if old > 0 > new else "ZERO_BASE")
    return _feature(feature_id, value=new / old - 1, fitness="READY", method="compatible_ttm_yoy/v2",
                    inputs=prior_inputs + inputs, growth_basis="TTM")


def _pit_trajectory(rows: Sequence[Mapping[str, Any]], metric: str) -> dict[str, Any]:
    series = _best_series(rows, metric, PIT)
    if len(series) < 2:
        return _blocked(f"{metric}_yoy", "MISSING_COMPATIBLE_POINT_IN_TIME_SERIES")
    current = _latest(series)
    key = _quarter(current.get("native_period_label")) if current else None
    prior = series.get(f"{key[0] - 1}-Q{key[1]}") if key else None
    if not prior:
        return _blocked(f"{metric}_yoy", "MISSING_SAME_POINT_IN_TIME_PRIOR_YEAR")
    if prior["reported_value"] == 0:
        return _blocked(f"{metric}_yoy", "ZERO_DENOMINATOR")
    return _feature(f"{metric}_yoy", value=current["reported_value"] / prior["reported_value"] - 1,
                    fitness="READY", method="same_provider_point_in_time_yoy/v2", inputs=[prior, current],
                    growth_basis="POINT_IN_TIME_YOY")


def _pit_ratio_direction(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    equity = _groups(rows, "shareholders_equity", PIT)
    assets = _groups(rows, "total_assets", PIT)
    candidates = []
    for key in set(equity) & set(assets):
        periods = sorted(set(equity[key]) & set(assets[key]))
        if len(periods) < 2:
            continue
        current_label = periods[-1]
        quarter = _quarter(current_label)
        prior_label = f"{quarter[0] - 1}-Q{quarter[1]}" if quarter else None
        if prior_label not in equity[key] or prior_label not in assets[key]:
            continue
        prior_equity, prior_assets = equity[key][prior_label], assets[key][prior_label]
        current_equity, current_assets = equity[key][current_label], assets[key][current_label]
        if prior_assets["reported_value"] == 0 or current_assets["reported_value"] == 0:
            continue
        candidates.append((current_label, prior_equity, prior_assets, current_equity, current_assets))
    if not candidates:
        return _blocked("equity_to_assets_direction", "MISSING_SAME_POINT_IN_TIME_PRIOR_YEAR_RATIO_PAIR")
    _, prior_equity, prior_assets, current_equity, current_assets = max(candidates, key=lambda item: item[0])
    value = current_equity["reported_value"] / current_assets["reported_value"] - prior_equity["reported_value"] / prior_assets["reported_value"]
    return _feature("equity_to_assets_direction", value=value, fitness="READY", method="same_provider_point_in_time_equity_to_assets_yoy/v2",
                    inputs=[prior_equity, prior_assets, current_equity, current_assets], growth_basis="POINT_IN_TIME_YOY")


def _pit_ratio_direction_for(rows: Sequence[Mapping[str, Any]], numerator_metric: str,
                             denominator_metric: str, feature_id: str) -> dict[str, Any]:
    """Directional change for two explicit, same-source P-I-T balance-sheet facts."""
    numerator = _groups(rows, numerator_metric, PIT)
    denominator = _groups(rows, denominator_metric, PIT)
    candidates = []
    for key in set(numerator) & set(denominator):
        periods = sorted(set(numerator[key]) & set(denominator[key]))
        if len(periods) < 2:
            continue
        current_label = periods[-1]
        quarter = _quarter(current_label)
        prior_label = f"{quarter[0] - 1}-Q{quarter[1]}" if quarter else None
        if not prior_label or prior_label not in numerator[key] or prior_label not in denominator[key]:
            continue
        prior_num, prior_den = numerator[key][prior_label], denominator[key][prior_label]
        current_num, current_den = numerator[key][current_label], denominator[key][current_label]
        if prior_den["reported_value"] == 0 or current_den["reported_value"] == 0:
            continue
        candidates.append((current_label, prior_num, prior_den, current_num, current_den))
    if not candidates:
        return _blocked(feature_id, "MISSING_SAME_POINT_IN_TIME_PRIOR_YEAR_RATIO_PAIR")
    _, prior_num, prior_den, current_num, current_den = max(candidates, key=lambda item: item[0])
    value = (current_num["reported_value"] / current_den["reported_value"]
             - prior_num["reported_value"] / prior_den["reported_value"])
    return _feature(feature_id, value=value, fitness="READY",
                    method="same_provider_point_in_time_explicit_debt_ratio_yoy/v2",
                    inputs=[prior_num, prior_den, current_num, current_den],
                    growth_basis="POINT_IN_TIME_YOY")


def _direction(feature: Mapping[str, Any], positive: str, negative: str, stable: str) -> str:
    if feature["fitness"] != "READY" or not _numeric(feature.get("value")):
        return "UNAVAILABLE"
    return positive if feature["value"] > 0 else negative if feature["value"] < 0 else stable


def _mixed_provider_proxy(rows: Sequence[Mapping[str, Any]], numerator: str, denominator: str,
                          feature_id: str) -> dict[str, Any]:
    flows = _best_series(rows, numerator, FLOW_STANDALONE)
    stocks = _best_series(rows, denominator, PIT)
    current = _latest(flows)
    if not current:
        return _blocked(feature_id, "MISSING_COMPATIBLE_FLOW_INPUT")
    target = str(current.get("native_period_label"))
    stock = stocks.get(target)
    if not stock:
        return _blocked(feature_id, "MISSING_SAME_PERIOD_BALANCE_SHEET_INPUT")
    if stock["reported_value"] == 0:
        return _blocked(feature_id, "ZERO_DENOMINATOR")
    if (current.get("source_lineage") or {}).get("provider") == (stock.get("source_lineage") or {}).get("provider"):
        return _blocked(feature_id, "SAME_PROVIDER_AVERAGE_BALANCE_INPUTS_INCOMPLETE")
    return _feature(feature_id, value=current["reported_value"] / stock["reported_value"], fitness="RESEARCH_PROXY",
                    method="cross_provider_end_of_period_proxy/v2", inputs=[current, stock],
                    reason_codes=["CROSS_PROVIDER_UNRESOLVED_SCALE"],
                    warnings=["NOT_READY_NOT_VALUATION_ELIGIBLE_NOT_CURRENT_RESEARCH_READY_BY_ITSELF"])


def _feature_states(features: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    income = features["net_income_sign"]
    income_value = income.get("value") if _numeric(income.get("value")) else 0
    transition = features["net_income_same_quarter_yoy"].get("semantic_transition")
    profitability = "TURNAROUND_CONTEXT" if transition == "LOSS_TO_PROFIT" else (
        "PROFITABLE" if income_value > 0 and income["fitness"] == "READY" else
        "LOSS_MAKING" if income_value < 0 and income["fitness"] == "READY" else "UNAVAILABLE")
    margin = _direction(features["net_margin_direction"], "MARGIN_EXPANDING", "MARGIN_COMPRESSING", "MARGIN_STABLE")
    growth_candidates = [features["revenue_qoq"], features["revenue_same_quarter_yoy"], features["net_income_qoq"], features["net_income_same_quarter_yoy"]]
    directions = [_direction(item, "GROWING", "CONTRACTING", "STABLE") for item in growth_candidates]
    directions = [item for item in directions if item != "UNAVAILABLE"]
    growth = directions[0] if directions and len(set(directions)) == 1 else "UNAVAILABLE" if not directions or len(set(directions)) > 1 else directions[0]
    balance = _direction(features["equity_to_assets_direction"], "STRENGTHENING", "DETERIORATING", "STABLE")
    cash_ratio = features["cfo_to_net_income"]
    cash = "HEALTHY" if cash_ratio["fitness"] == "RESEARCH_PROXY" and _numeric(cash_ratio.get("value")) and cash_ratio["value"] > 0 else "WEAK" if cash_ratio["fitness"] == "RESEARCH_PROXY" and _numeric(cash_ratio.get("value")) else "UNAVAILABLE"
    capital = "UNAVAILABLE"  # Cross-provider values remain explicitly proxies, never state-ready.
    debt_direction = features["debt_to_equity_direction"]
    leverage = _direction(debt_direction, "WORSENING", "IMPROVING", "STABLE")
    if leverage == "UNAVAILABLE":
        leverage = _direction(features["equity_to_assets_direction"], "IMPROVING", "WORSENING", "STABLE")
    resilience = "RESILIENT" if profitability == "PROFITABLE" and margin in {"MARGIN_EXPANDING", "MARGIN_STABLE"} and cash == "HEALTHY" and balance in {"STRENGTHENING", "STABLE"} else "STRESSED" if profitability == "LOSS_MAKING" and cash == "WEAK" else "UNAVAILABLE"
    return {"profitability_state": profitability, "margin_state": margin, "growth_state": growth,
            "balance_sheet_state": balance, "cash_conversion_state": cash,
            "capital_efficiency_state": capital, "leverage_state": leverage, "resilience_state": resilience}


def _evidence(ticker: str, features: Mapping[str, Mapping[str, Any]], states: Mapping[str, str]) -> dict[str, list[str]]:
    positive: list[str] = []
    negative: list[str] = []
    conflicts: list[str] = []
    missing: list[str] = []
    if states["profitability_state"] == "PROFITABLE": positive.append(f"{ticker}: profitable retained net income")
    if states["margin_state"] == "MARGIN_EXPANDING": positive.append(f"{ticker}: compatible net margin expanding")
    if states["balance_sheet_state"] == "STRENGTHENING": positive.append(f"{ticker}: equity/assets strengthening")
    if states["cash_conversion_state"] == "HEALTHY": positive.append(f"{ticker}: CFO/net-income proxy is positive")
    if states["profitability_state"] == "LOSS_MAKING": negative.append(f"{ticker}: retained net income is loss-making")
    if states["margin_state"] == "MARGIN_COMPRESSING": negative.append(f"{ticker}: compatible net margin compressing")
    if states["cash_conversion_state"] == "WEAK": negative.append(f"{ticker}: CFO/net-income proxy is weak")
    if states["profitability_state"] == "PROFITABLE" and states["cash_conversion_state"] == "WEAK": conflicts.append(f"{ticker}: profitable earnings conflict with weak cash conversion")
    if states["growth_state"] == "GROWING" and states["margin_state"] == "MARGIN_COMPRESSING": conflicts.append(f"{ticker}: growth conflicts with margin compression")
    for feature_id, feature in sorted(features.items()):
        if feature["fitness"] == "BLOCKED_BY_EVIDENCE": missing.append(f"{feature_id}:{','.join(feature['reason_codes'][:1])}")
    return {"positive_evidence": positive[:6], "negative_evidence": negative[:6],
            "conflicting_evidence": conflicts[:6], "missing_dimensions": missing[:12]}


def build_ticker_context(ticker: str, rows: Sequence[Mapping[str, Any]], *, issuer_type: str | None,
                         source_identities: Mapping[str, Any]) -> dict[str, Any]:
    normalized_type = str(issuer_type).lower() if issuer_type not in (None, "") else "unknown"
    family = INDUSTRIAL if normalized_type == "corporate" else LIMITED
    ids = ("net_income_sign", "net_margin", "pbt_margin", "net_margin_direction", "revenue_qoq", "net_income_qoq",
           "revenue_same_quarter_yoy", "net_income_same_quarter_yoy", "revenue_ytd_yoy", "net_income_ytd_yoy", "revenue_ttm_yoy", "net_income_ttm_yoy", "revenue_ttm", "net_income_ttm", "operating_cash_flow_sign", "cfo_to_net_income",
           "fcf", "equity_to_assets", "cash_to_assets", "debt_to_equity", "debt_to_assets", "debt_to_equity_direction", "equity_to_assets_direction", "assets_yoy", "equity_yoy",
           "cash_yoy", "same_provider_roa", "same_provider_roe", "mixed_provider_roa_proxy", "mixed_provider_asset_turnover_proxy")
    if family == LIMITED:
        features = {feature_id: _not_applicable(feature_id) for feature_id in ids}
        states = {"profitability_state": "UNAVAILABLE", "margin_state": "UNAVAILABLE", "growth_state": "UNAVAILABLE",
                  "balance_sheet_state": "UNAVAILABLE", "cash_conversion_state": "UNAVAILABLE",
                  "capital_efficiency_state": "UNAVAILABLE", "leverage_state": "UNAVAILABLE", "resilience_state": "UNAVAILABLE"}
    else:
        revenue = _best_series(rows, "revenue", FLOW_STANDALONE)
        income = _best_series(rows, "net_income", FLOW_STANDALONE)
        ocf = _best_series(rows, "operating_cash_flow", FLOW_STANDALONE)
        revenue_ytd = _best_series(rows, "revenue", "YTD_CUMULATIVE_INTERIM")
        income_ytd = _best_series(rows, "net_income", "YTD_CUMULATIVE_INTERIM")
        revenue_ttm, _ = _ttm_sum(revenue, "revenue_ttm")
        income_ttm, _ = _ttm_sum(income, "net_income_ttm")
        net_margin = _ratio("net_margin", _same_period_pair(rows, "net_income", "revenue", FLOW_STANDALONE), method="same_provider_same_period_net_margin/v2")
        pbt_margin = _ratio("pbt_margin", _same_period_pair(rows, "profit_before_tax", "revenue", FLOW_STANDALONE), method="same_provider_same_period_pbt_margin/v2")
        previous_margin = None
        pair = _same_period_pair(rows, "net_income", "revenue", FLOW_STANDALONE)
        if pair:
            current_q = _quarter(pair[0].get("native_period_label")); key = _source_key(pair[0])
            if current_q:
                prior_label = f"{_prior_quarter(current_q)[0]}-Q{_prior_quarter(current_q)[1]}"
                left = _groups(rows, "net_income", FLOW_STANDALONE).get(key, {}).get(prior_label)
                right = _groups(rows, "revenue", FLOW_STANDALONE).get(key, {}).get(prior_label)
                previous_margin = _ratio("net_margin_direction", (left, right) if left and right else None, method="prior_period_net_margin/v2")
        current_margin = net_margin
        if current_margin["fitness"] == "READY" and previous_margin and previous_margin["fitness"] == "READY":
            margin_direction = _feature("net_margin_direction", value=current_margin["value"] - previous_margin["value"], fitness="READY", method="consecutive_same_provider_net_margin_direction/v2", inputs=[])
        else:
            margin_direction = _blocked("net_margin_direction", "MISSING_CONSECUTIVE_COMPATIBLE_MARGIN_PERIODS")
        cash_pair = _cross_statement_same_representation_pair(rows, "operating_cash_flow", "net_income", FLOW_STANDALONE)
        features = {
            "net_income_sign": _feature("net_income_sign", value=_latest(income)["reported_value"], fitness="READY", method="latest_compatible_standalone_sign/v2", inputs=[_latest(income)]) if _latest(income) else _blocked("net_income_sign", "MISSING_STANDALONE_NET_INCOME"),
            "net_margin": net_margin, "pbt_margin": pbt_margin, "net_margin_direction": margin_direction,
            "revenue_qoq": _growth("revenue_qoq", revenue, basis="QOQ_STANDALONE"),
            "net_income_qoq": _growth("net_income_qoq", income, basis="QOQ_STANDALONE", earnings=True),
            "revenue_same_quarter_yoy": _growth("revenue_same_quarter_yoy", revenue, basis="SAME_QUARTER_YOY"),
            "net_income_same_quarter_yoy": _growth("net_income_same_quarter_yoy", income, basis="SAME_QUARTER_YOY", earnings=True),
            "revenue_ytd_yoy": _growth("revenue_ytd_yoy", revenue_ytd, basis="YTD_YOY"),
            "net_income_ytd_yoy": _growth("net_income_ytd_yoy", income_ytd, basis="YTD_YOY", earnings=True),
            "revenue_ttm": revenue_ttm, "net_income_ttm": income_ttm,
            "revenue_ttm_yoy": _ttm_yoy("revenue_ttm_yoy", revenue), "net_income_ttm_yoy": _ttm_yoy("net_income_ttm_yoy", income),
            "operating_cash_flow_sign": _feature("operating_cash_flow_sign", value=_latest(ocf)["reported_value"], fitness="READY", method="latest_compatible_standalone_cfo_sign/v2", inputs=[_latest(ocf)]) if _latest(ocf) else _blocked("operating_cash_flow_sign", "MISSING_STANDALONE_OPERATING_CASH_FLOW"),
            "cfo_to_net_income": _feature("cfo_to_net_income", value=cash_pair[0]["reported_value"] / cash_pair[1]["reported_value"], fitness="RESEARCH_PROXY", method="same_provider_cross_statement_cash_earnings_proxy/v2", inputs=list(cash_pair), warnings=["CROSS_STATEMENT_SCALE_SEMANTICS_NOT_FULLY_AUTHORITATIVE"]) if cash_pair and cash_pair[1]["reported_value"] != 0 else _blocked("cfo_to_net_income", "MISSING_SAME_REPRESENTATION_CFO_AND_NET_INCOME"),
            "fcf": _blocked("fcf", "FCF_BLOCKED_BY_EVIDENCE_CAPEX_SEMANTICS_UNAVAILABLE"),
            "equity_to_assets": _ratio("equity_to_assets", _same_period_pair(rows, "shareholders_equity", "total_assets", PIT), method="same_provider_same_period_equity_to_assets/v2"),
            "cash_to_assets": _ratio("cash_to_assets", _same_period_pair(rows, "cash_and_cash_equivalents", "total_assets", PIT), method="same_provider_same_period_cash_to_assets/v2"),
            "debt_to_equity": _ratio("debt_to_equity", _same_period_pair(rows, "total_interest_bearing_debt", "shareholders_equity", PIT), method="same_provider_same_period_explicit_debt_to_equity/v2"),
            "debt_to_assets": _ratio("debt_to_assets", _same_period_pair(rows, "total_interest_bearing_debt", "total_assets", PIT), method="same_provider_same_period_explicit_debt_to_assets/v2"),
            "debt_to_equity_direction": _pit_ratio_direction_for(rows, "total_interest_bearing_debt", "shareholders_equity", "debt_to_equity_direction"),
            "equity_to_assets_direction": _pit_ratio_direction(rows),
            "assets_yoy": _pit_trajectory(rows, "total_assets"), "equity_yoy": _pit_trajectory(rows, "shareholders_equity"), "cash_yoy": _pit_trajectory(rows, "cash_and_cash_equivalents"),
            "same_provider_roa": _blocked("same_provider_roa", "SAME_PROVIDER_AVERAGE_BALANCE_INPUTS_UNAVAILABLE"),
            "same_provider_roe": _blocked("same_provider_roe", "SAME_PROVIDER_AVERAGE_BALANCE_INPUTS_UNAVAILABLE"),
            "mixed_provider_roa_proxy": _mixed_provider_proxy(rows, "net_income", "total_assets", "mixed_provider_roa_proxy"),
            "mixed_provider_asset_turnover_proxy": _mixed_provider_proxy(rows, "revenue", "total_assets", "mixed_provider_asset_turnover_proxy"),
        }
        states = _feature_states(features)
    readiness_features = ("net_margin", "pbt_margin", "equity_to_assets", "cash_to_assets", "assets_yoy", "equity_yoy")
    ready = family == INDUSTRIAL and any(features[item]["fitness"] == "READY" for item in readiness_features)
    evidence = _evidence(ticker, features, states)
    valuation_hints = []
    if states["profitability_state"] == "LOSS_MAKING": valuation_hints.append("EARNINGS_NOT_MEANINGFUL_FOR_PE")
    if states["profitability_state"] == "TURNAROUND_CONTEXT": valuation_hints.append("TRAILING_EARNINGS_NOT_STABLE_RUN_RATE")
    if states["profitability_state"] == "LOSS_MAKING" and features["net_margin"]["fitness"] == "READY": valuation_hints.append("SALES_BASED_CONTEXT_PREFERRED")
    warnings = ["PIT_AUTHORITY_NOT_GRANTED"]
    if features["debt_to_equity"]["fitness"] != "READY":
        warnings.append("DEBT_EVIDENCE_UNAVAILABLE_NO_EXACT_DEBT_LEVERAGE")
    if any(feature["fitness"] == "RESEARCH_PROXY" for feature in features.values()): warnings.append("PROXY_FEATURES_REMAIN_DISTINCT_FROM_READY")
    return {"ticker": ticker, "issuer_type": normalized_type, "analysis_family": family,
            "current_research_ready": ready, "pit_authority": "NOT_GRANTED",
            "period_coverage": dict(sorted(Counter(normalize_period_semantic(row.get("period_semantic_state")) for row in rows).items())),
            "states": states, "features": {key: features[key] for key in sorted(features)},
            **evidence, "warnings": warnings, "valuation_hints": valuation_hints,
            "source_identities": dict(source_identities),
            "leverage_basis": ("EXPLICIT_SAME_PROVIDER_SHORT_AND_LONG_TERM_BORROWINGS"
                                if features["debt_to_equity"]["fitness"] == "READY"
                                else "EQUITY_TO_ASSETS_STRUCTURAL_DIRECTION_ONLY_DEBT_UNAVAILABLE"),
            "authority_boundary": {"is_actionable": False, "financial_authority_promoted": False, "decision_integration": False}}


def build_artifact(*, tickers: Sequence[str], rows: Sequence[Mapping[str, Any]], issuer_types: Mapping[str, str | None],
                   source_identities: Mapping[str, Any], requested_at: str) -> dict[str, Any]:
    names = sorted({str(ticker).upper() for ticker in tickers})
    by_ticker: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if ticker in names:
            by_ticker[ticker].append(row)
    records = {ticker: build_ticker_context(ticker, by_ticker.get(ticker, []), issuer_type=issuer_types.get(ticker), source_identities=source_identities) for ticker in names}
    all_features = [feature for record in records.values() for feature in record["features"].values()]
    artifact: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION,
        "requested_at": requested_at, "source_identities": dict(source_identities), "records": records,
        "coverage": {"ticker_denominator": len(names), "ticker_record_count": len(records), "zero_silent_ticker_drops": len(names) == len(records),
            "issuer_family_distribution": dict(sorted(Counter(record["analysis_family"] for record in records.values()).items())),
            "current_research_ready_count": sum(record["current_research_ready"] for record in records.values()),
            "feature_fitness": dict(sorted(Counter(feature["fitness"] for feature in all_features).items())),
            "feature_ready_counts": dict(sorted(Counter(feature["feature_id"] for feature in all_features if feature["fitness"] == "READY").items())),
            "feature_proxy_counts": dict(sorted(Counter(feature["feature_id"] for feature in all_features if feature["fitness"] == "RESEARCH_PROXY").items())),
            "state_distribution": {name: dict(sorted(Counter(record["states"][name] for record in records.values()).items())) for name in sorted(next(iter(records.values()))["states"]) } if records else {},
            "evidence_coverage": {name: sum(bool(record[name]) for record in records.values()) for name in ("positive_evidence", "negative_evidence", "conflicting_evidence", "missing_dimensions")}},
        "authority_boundary": {"is_actionable": False, "score_or_rank_emitted": False, "target_or_probability_emitted": False,
            "financial_authority_promoted": False, "pit_authority_granted": False, "decision_integration": False}}
    artifact.update(content_identity(artifact))
    return artifact
