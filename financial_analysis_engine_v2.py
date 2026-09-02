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

import monetary_basis_contract as basis_contract
import bank_financial_research_component as bank_component
import securities_financial_research_component as securities_component


CONTRACT_VERSION = "financial_analysis_context/v2"
#: Bumped 2026-09-02: SECURITIES_SPECIALIST_FINANCIAL_RESEARCH_FOUNDATION_V1 added the
#: additive securities_* feature/state family and securities_specialist_contract_version,
#: mirroring the bank specialist family's own additive shape.
SCHEMA_VERSION = "2.2.0"
FITNESS = ("READY", "RESEARCH_PROXY", "BLOCKED_BY_EVIDENCE", "NOT_APPLICABLE")
INDUSTRIAL = "INDUSTRIAL_FINANCIAL_ANALYSIS"
LIMITED = "OTHER_FINANCIAL_LIMITED_ANALYSIS"
NON_INDUSTRIAL = frozenset({"bank", "securities", "insurance", "finance_company", "unknown", None, ""})
FLOW_STANDALONE = "STANDALONE_QUARTER"
PIT = "POINT_IN_TIME_BALANCE_SHEET"
UNKNOWN = "UNKNOWN_DURATION"
PERIOD_SEMANTICS = frozenset({FLOW_STANDALONE, "YTD_CUMULATIVE_INTERIM", "ANNUAL", PIT, UNKNOWN})

# --- Bank specialist research family (additive; never alters INDUSTRIAL/LIMITED) ---
BANK = "bank"
BANK_NPL_RATIO = "bank_npl_ratio"
BANK_LDR = "bank_ldr"
BANK_CIR = "bank_cir"
BANK_PROVISION_COVERAGE = "bank_provision_coverage"
BANK_LOAN_GROWTH = "bank_loan_growth"
BANK_NIM_PROVIDER_PROXY = "bank_nim_provider_proxy"
BANK_FEATURE_IDS = (BANK_NPL_RATIO, BANK_LDR, BANK_CIR, BANK_PROVISION_COVERAGE, BANK_LOAN_GROWTH, BANK_NIM_PROVIDER_PROXY)
BANK_ASSET_QUALITY_STATE = "bank_asset_quality_state"
BANK_FUNDING_STATE = "bank_funding_state"
BANK_EFFICIENCY_STATE = "bank_efficiency_state"
BANK_STATE_NAMES = (BANK_ASSET_QUALITY_STATE, BANK_FUNDING_STATE, BANK_EFFICIENCY_STATE)
# Raw bank_financial_research_component/v1 metric_id vocabulary this milestone's
# deterministic formulas read (see bank_financial_research_component.KNOWN_RAW_METRIC_IDS
# for the full TCBS-probe-established universe, only part of which is consumed here).
_CUSTOMER_LOAN = "customer_loan"
_DEPOSIT = "deposit"
_NON_PERFORMING_LOAN = "non_performing_loan"
_PROVISION = "provision"
_OPERATION_EXPENSE = "operation_expense"
_TOTAL_OPERATION_INCOME = "total_operation_income"
_NET_INTEREST_MARGIN_PROVIDER = "net_interest_margin"

# --- Securities-firm specialist research family (additive; never alters INDUSTRIAL/LIMITED) ---
SECURITIES = "securities"
SECURITIES_FVTPL_ASSET_INTENSITY = "fvtpl_asset_intensity"
SECURITIES_MARGIN_LENDING_ASSET_INTENSITY = "margin_lending_asset_intensity"
SECURITIES_BROKERAGE_REVENUE_MIX = "brokerage_revenue_mix"
SECURITIES_LOAN_INTEREST_INCOME_MIX = "loan_interest_income_mix"
SECURITIES_FEATURE_IDS = (SECURITIES_FVTPL_ASSET_INTENSITY, SECURITIES_MARGIN_LENDING_ASSET_INTENSITY,
                          SECURITIES_BROKERAGE_REVENUE_MIX, SECURITIES_LOAN_INTEREST_INCOME_MIX)
SECURITIES_FVTPL_ASSET_INTENSITY_STATE = "fvtpl_asset_intensity_trajectory_state"
SECURITIES_MARGIN_LENDING_INTENSITY_STATE = "margin_lending_intensity_trajectory_state"
SECURITIES_BROKERAGE_MIX_STATE = "brokerage_mix_trajectory_state"
SECURITIES_STATE_NAMES = (SECURITIES_FVTPL_ASSET_INTENSITY_STATE, SECURITIES_MARGIN_LENDING_INTENSITY_STATE,
                          SECURITIES_BROKERAGE_MIX_STATE)
# Raw securities_financial_research_component/v1 metric_id vocabulary this milestone's
# deterministic formulas read (see securities_financial_research_component.KNOWN_RAW_METRIC_IDS
# for the full retained-corpus-established universe, only part of which is consumed here).
_FVTPL_FINANCIAL_ASSETS = "fvtpl_financial_assets"
_SECURITIES_TOTAL_ASSETS = "total_assets"
_MARGIN_LENDING_RECEIVABLE = "margin_lending_receivable"
_BROKERAGE_REVENUE = "brokerage_revenue"
_LOAN_RECEIVABLE_INTEREST_INCOME = "loan_receivable_interest_income"
_TOTAL_SECURITIES_OPERATING_INCOME = "total_securities_operating_income"


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
    # `agree()` treats every sentinel (missing key, None, "unknown", ...) as "no proof",
    # never as a distinct-but-fake shared value -- a str(None) -> "None" stringification
    # here must never read back as a known, agreed currency or scale.
    currency = basis_contract.agree({(row.get("normalized_candidate_unit") or {}).get("currency") for row in inputs})
    scale = basis_contract.agree({(row.get("normalized_candidate_unit") or {}).get("scale") for row in inputs})
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
        "currency": currency,
        "scale": scale,
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
                             denominator_metric: str, feature_id: str, *,
                             method: str = "same_provider_point_in_time_explicit_debt_ratio_yoy/v2",
                             semantic: str = PIT) -> dict[str, Any]:
    """Directional change for two explicit, same-source facts at one shared period semantic.

    Despite the name (kept for the two original P-I-T callers), this is not
    intrinsically balance-sheet-specific: passing `semantic=FLOW_STANDALONE` gives the
    same same-provider, same-quarter-prior-year comparison over a flow ratio such as
    gross margin instead of a stock ratio.
    """
    numerator = _groups(rows, numerator_metric, semantic)
    denominator = _groups(rows, denominator_metric, semantic)
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
    return _feature(feature_id, value=value, fitness="READY", method=method,
                    inputs=[prior_num, prior_den, current_num, current_den],
                    growth_basis="POINT_IN_TIME_YOY")


def _difference(feature_id: str, pair: tuple[Mapping[str, Any], Mapping[str, Any]] | None, *, method: str) -> dict[str, Any]:
    """A single compatible same-representation (minuend - subtrahend) at one P-I-T period."""
    if not pair:
        return _blocked(feature_id, "MISSING_SAME_PROVIDER_TICKER_PERIOD_SCOPE_REPRESENTATION")
    minuend, subtrahend = pair
    return _feature(feature_id, value=minuend["reported_value"] - subtrahend["reported_value"],
                    fitness="READY", method=method, inputs=[minuend, subtrahend])


def _signed_flow_sum(feature_id: str, pair: tuple[Mapping[str, Any], Mapping[str, Any]] | None, *,
                     method: str) -> dict[str, Any]:
    """Return a same-representation sum without changing either component's sign.

    ``capital_expenditure`` stays in its provider-native signed cash-flow
    representation. This is a research proxy, not a universal CapEx-sign claim.
    """
    if not pair:
        return _blocked(feature_id, "MISSING_SAME_PROVIDER_TICKER_PERIOD_SCOPE_REPRESENTATION")
    operating_cash_flow, capital_expenditure = pair
    return _feature(feature_id,
                    value=operating_cash_flow["reported_value"] + capital_expenditure["reported_value"],
                    fitness="READY", method=method, inputs=[operating_cash_flow, capital_expenditure],
                    warnings=["CAPEX_PROVIDER_SIGN_RETAINED_NO_NORMALIZATION"])


def _signed_flow_sum_direction(rows: Sequence[Mapping[str, Any]], *, feature_id: str) -> dict[str, Any]:
    """Same-provider, same-quarter YoY level delta for the qualified FCF proxy."""
    operating_cash_flow = _groups(rows, "operating_cash_flow", FLOW_STANDALONE)
    capital_expenditure = _groups(rows, "capital_expenditure", FLOW_STANDALONE)
    candidates = []
    for key in set(operating_cash_flow) & set(capital_expenditure):
        periods = sorted(set(operating_cash_flow[key]) & set(capital_expenditure[key]))
        for current_label in periods:
            quarter = _quarter(current_label)
            prior_label = f"{quarter[0] - 1}-Q{quarter[1]}" if quarter else None
            if not prior_label or prior_label not in operating_cash_flow[key] or prior_label not in capital_expenditure[key]:
                continue
            candidates.append((current_label,
                               operating_cash_flow[key][prior_label], capital_expenditure[key][prior_label],
                               operating_cash_flow[key][current_label], capital_expenditure[key][current_label]))
    if not candidates:
        return _blocked(feature_id, "MISSING_SAME_PROVIDER_SAME_QUARTER_PRIOR_YEAR_FCF_PROXY_INPUTS")
    _, prior_ocf, prior_capex, current_ocf, current_capex = max(candidates, key=lambda item: item[0])
    prior_value = prior_ocf["reported_value"] + prior_capex["reported_value"]
    current_value = current_ocf["reported_value"] + current_capex["reported_value"]
    return _feature(feature_id, value=current_value - prior_value, fitness="READY",
                    method="same_provider_same_quarter_free_cash_flow_proxy_direction/v1",
                    inputs=[prior_ocf, prior_capex, current_ocf, current_capex],
                    growth_basis="SAME_QUARTER_YOY",
                    warnings=["CAPEX_PROVIDER_SIGN_RETAINED_NO_NORMALIZATION"])


def _pit_component_direction(rows: Sequence[Mapping[str, Any]], minuend_metric: str,
                             subtrahend_metric: str, feature_id: str) -> dict[str, Any]:
    """YoY change in (minuend - subtrahend) at two compatible same-representation P-I-T periods.

    A plain value delta, not a percentage change: the underlying difference (e.g. net working
    capital) may legitimately be negative, zero, or cross zero between periods, and a
    percentage-of-prior formula is not meaningful in that case. Mirrors
    `_pit_ratio_direction_for`'s pairing and YoY-quarter selection exactly, substituting a
    subtraction for a division.
    """
    minuend = _groups(rows, minuend_metric, PIT)
    subtrahend = _groups(rows, subtrahend_metric, PIT)
    candidates = []
    for key in set(minuend) & set(subtrahend):
        periods = sorted(set(minuend[key]) & set(subtrahend[key]))
        if len(periods) < 2:
            continue
        current_label = periods[-1]
        quarter = _quarter(current_label)
        prior_label = f"{quarter[0] - 1}-Q{quarter[1]}" if quarter else None
        if not prior_label or prior_label not in minuend[key] or prior_label not in subtrahend[key]:
            continue
        candidates.append((current_label, minuend[key][prior_label], subtrahend[key][prior_label],
                           minuend[key][current_label], subtrahend[key][current_label]))
    if not candidates:
        return _blocked(feature_id, "MISSING_SAME_POINT_IN_TIME_PRIOR_YEAR_RATIO_PAIR")
    _, prior_min, prior_sub, current_min, current_sub = max(candidates, key=lambda item: item[0])
    prior_value = prior_min["reported_value"] - prior_sub["reported_value"]
    current_value = current_min["reported_value"] - current_sub["reported_value"]
    return _feature(feature_id, value=current_value - prior_value, fitness="READY",
                    method="same_provider_point_in_time_component_difference_yoy/v2",
                    inputs=[prior_min, prior_sub, current_min, current_sub],
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


def _same_provider_eop_proxy(rows: Sequence[Mapping[str, Any]], numerator_metric: str,
                             denominator_metric: str, feature_id: str) -> dict[str, Any]:
    """One compatible standalone flow divided by its ending same-provider balance sheet.

    This is deliberately an *EOP proxy*.  It must never be relabelled as an average-balance
    ROA/ROE/turnover measure simply because both inputs share a quarter label.
    """
    def index(metric: str, semantic: str) -> dict[tuple[str, str, str, str, str], dict[str, Mapping[str, Any]]]:
        result: dict[tuple[str, str, str, str, str], dict[str, Mapping[str, Any]]] = defaultdict(dict)
        for row in rows:
            if _row_usable(row, semantic) and row.get("canonical_metric") == metric:
                unit = row.get("normalized_candidate_unit") or {}
                key = (str(row.get("ticker")), str((row.get("source_lineage") or {}).get("provider")),
                       str(row.get("statement_scope")), str(unit.get("currency")), str(unit.get("scale")))
                result[key][str(row.get("native_period_label") or row.get("period_end"))] = row
        return result
    flows = index(numerator_metric, FLOW_STANDALONE)
    stocks = index(denominator_metric, PIT)
    candidates = []
    for key in set(flows) & set(stocks):
        for label in set(flows[key]) & set(stocks[key]):
            candidates.append((label, flows[key][label], stocks[key][label]))
    if not candidates:
        return _blocked(feature_id, "MISSING_SAME_PROVIDER_FLOW_AND_ENDING_BALANCE_SHEET_INPUT")
    _, flow, stock = max(candidates, key=lambda item: item[0])
    if stock["reported_value"] == 0:
        return _blocked(feature_id, "ZERO_DENOMINATOR")
    return _feature(feature_id, value=flow["reported_value"] / stock["reported_value"], fitness="READY",
                    method="same_provider_standalone_flow_end_of_period_balance_proxy/v2", inputs=[flow, stock],
                    warnings=["END_OF_PERIOD_BALANCE_PROXY_NOT_AVERAGE_BALANCE_RETURN"])


def _bank_usable(component: Mapping[str, Any], *, fitness: str) -> bool:
    return (
        component.get("contract_version") == bank_component.CONTRACT_VERSION
        and component.get("fitness") == fitness
        and component.get("conflict_status") != "CAPTURE_VALUE_CONFLICT"
        and _numeric(component.get("raw_value"))
        and component.get("provider") not in (None, "", "unknown")
        and component.get("source_identity") not in (None, "", "unknown")
    )


def _bank_period(component: Mapping[str, Any]) -> tuple[int, int | None] | None:
    year = component.get("year")
    if not isinstance(year, int) or isinstance(year, bool):
        return None
    quarter = component.get("quarter")
    return (year, quarter if isinstance(quarter, int) and not isinstance(quarter, bool) else None)


def _bank_group(components: Sequence[Mapping[str, Any]], metric_id: str, *,
                fitness: str) -> dict[str, dict[tuple[int, int | None], Mapping[str, Any]]]:
    grouped: dict[str, dict[tuple[int, int | None], Mapping[str, Any]]] = defaultdict(dict)
    for component in components:
        if not _bank_usable(component, fitness=fitness) or component.get("metric_id") != metric_id:
            continue
        period = _bank_period(component)
        if period is None:
            continue
        key = f"{component.get('ticker')}|{component.get('provider')}"
        grouped[key][period] = component
    return grouped


def _bank_same_period_pair(components: Sequence[Mapping[str, Any]], numerator_metric: str,
                           denominator_metric: str) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    """Same-provider, same-period pair of raw structured bank components.

    Mirrors `_same_period_pair`'s same-source-key discipline: a pair can only
    form within one (ticker, provider) group, at one shared (year, quarter)
    period -- the same-representation guarantee that lets a same-row ratio
    stay valid even when currency/scale are both UNKNOWN (they cancel).
    """
    left = _bank_group(components, numerator_metric, fitness=bank_component.STRUCTURED_RESEARCH_COMPONENT)
    right = _bank_group(components, denominator_metric, fitness=bank_component.STRUCTURED_RESEARCH_COMPONENT)
    candidates = [(period, left[key][period], right[key][period])
                  for key in set(left) & set(right) for period in set(left[key]) & set(right[key])]
    return max(candidates, key=lambda item: item[0])[1:] if candidates else None


def _bank_feature(feature_id: str, *, value: Any = None, fitness: str = "BLOCKED_BY_EVIDENCE",
                  method: str, inputs: Sequence[Mapping[str, Any]] = (),
                  reason_codes: Sequence[str] = (), warnings: Sequence[str] = ()) -> dict[str, Any]:
    return {
        "feature_id": feature_id, "value": value, "fitness": fitness, "method": method,
        "period_identity": [f"{c.get('year')}-Q{c['quarter']}" if c.get("quarter") else f"{c.get('year')}-FY" for c in inputs],
        "provider_source_provenance": [
            {"provider": c.get("provider"), "source_identity": c.get("source_identity"), "retrieved_at": c.get("retrieved_at")}
            for c in inputs
        ],
        # Purely descriptive lineage, never a gate: a same-row ratio stays READY
        # even when every input's status here reads UNKNOWN (see module docstring).
        "period_semantics_status": sorted({str(c.get("period_semantics_status")) for c in inputs}),
        "component_currency_status": sorted({str(c.get("currency_status")) for c in inputs}),
        "component_scale_status": sorted({str(c.get("scale_status")) for c in inputs}),
        "reason_codes": list(reason_codes), "warnings": list(warnings), "is_actionable": False,
    }


def _bank_blocked(feature_id: str, *codes: str, method: str = "bank_blocked_by_evidence/v1") -> dict[str, Any]:
    return _bank_feature(feature_id, method=method, reason_codes=codes)


def _bank_not_applicable(feature_id: str) -> dict[str, Any]:
    return _bank_feature(feature_id, fitness="NOT_APPLICABLE", method="bank_entity_applicability/v1",
                         reason_codes=["ISSUER_NOT_BANK"])


def _bank_ratio(feature_id: str, pair: tuple[Mapping[str, Any], Mapping[str, Any]] | None, *,
                method: str, abs_numerator: bool = False) -> dict[str, Any]:
    if not pair:
        return _bank_blocked(feature_id, "MISSING_SAME_PROVIDER_TICKER_PERIOD_BANK_COMPONENT_PAIR")
    numerator, denominator = pair
    if denominator["raw_value"] == 0:
        return _bank_blocked(feature_id, "ZERO_DENOMINATOR")
    numerator_value = abs(numerator["raw_value"]) if abs_numerator else numerator["raw_value"]
    return _bank_feature(feature_id, value=numerator_value / denominator["raw_value"], fitness="READY",
                         method=method, inputs=[numerator, denominator])


def _bank_loan_growth(components: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Same-provider, same-quarter YoY customer-loan growth.

    Quarter=5 (or any non-1..4 value) rows are excluded here even though the
    same-row ratios above accept them: a growth comparison needs a genuine,
    deterministically-checkable prior-year-same-quarter relationship, and
    quarter=5's empirical FY behaviour is explicitly not a stable provider
    contract (see module docstring / AI_RULES period-semantics boundary).
    """
    series = _bank_group(components, _CUSTOMER_LOAN, fitness=bank_component.STRUCTURED_RESEARCH_COMPONENT)
    candidates = []
    for periods in series.values():
        for (year, quarter), current in periods.items():
            if quarter not in (1, 2, 3, 4):
                continue
            prior = periods.get((year - 1, quarter))
            if prior is not None:
                candidates.append(((year, quarter), prior, current))
    if not candidates:
        return _bank_blocked(BANK_LOAN_GROWTH, "MISSING_COMPATIBLE_SAME_QUARTER_PRIOR_YEAR_LOAN_BALANCE")
    _, prior, current = max(candidates, key=lambda item: item[0])
    if prior["raw_value"] == 0:
        return _bank_blocked(BANK_LOAN_GROWTH, "ZERO_DENOMINATOR")
    return _bank_feature(BANK_LOAN_GROWTH, value=current["raw_value"] / prior["raw_value"] - 1, fitness="READY",
                         method="same_provider_same_quarter_yoy_bank_loan_growth/v1", inputs=[prior, current])


def _bank_nim_proxy(components: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """NIM is never computed. A retained provider NIM is a proxy, never READY.

    The 2026-09-01 TCBS MCP probe could not independently reconstruct NIM from
    raw components (unlike CIR/LDR/NPL, which matched exactly); only a
    verbatim provider-derived value is ever surfaced here.
    """
    candidates = [c for c in components
                  if _bank_usable(c, fitness=bank_component.PROVIDER_DERIVED_RESEARCH_PROXY)
                  and c.get("metric_id") == _NET_INTEREST_MARGIN_PROVIDER and _bank_period(c)]
    if not candidates:
        return _bank_blocked(BANK_NIM_PROVIDER_PROXY, "MISSING_PROVIDER_DERIVED_NET_INTEREST_MARGIN_OBSERVATION")
    latest = max(candidates, key=lambda c: _bank_period(c))
    return _bank_feature(BANK_NIM_PROVIDER_PROXY, value=latest["raw_value"], fitness="RESEARCH_PROXY",
                         method="provider_derived_net_interest_margin_proxy/v1", inputs=[latest],
                         reason_codes=["PROVIDER_DERIVED_NOT_STOCKLOOKUP_DETERMINISTIC_AUTHORITY"],
                         warnings=["NIM_NOT_INDEPENDENTLY_RECONSTRUCTED_FROM_COMPONENTS"])


def _build_bank_features(components: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        BANK_NPL_RATIO: _bank_ratio(BANK_NPL_RATIO, _bank_same_period_pair(components, _NON_PERFORMING_LOAN, _CUSTOMER_LOAN),
                                    method="same_provider_same_period_bank_npl_ratio/v1"),
        BANK_LDR: _bank_ratio(BANK_LDR, _bank_same_period_pair(components, _CUSTOMER_LOAN, _DEPOSIT),
                              method="same_provider_same_period_bank_loan_to_deposit/v1"),
        BANK_CIR: _bank_ratio(BANK_CIR, _bank_same_period_pair(components, _OPERATION_EXPENSE, _TOTAL_OPERATION_INCOME),
                              method="same_provider_same_period_bank_cost_to_income/v1", abs_numerator=True),
        BANK_PROVISION_COVERAGE: _bank_ratio(BANK_PROVISION_COVERAGE,
                                             _bank_same_period_pair(components, _PROVISION, _NON_PERFORMING_LOAN),
                                             method="same_provider_same_period_bank_provision_coverage/v1"),
        BANK_LOAN_GROWTH: _bank_loan_growth(components),
        BANK_NIM_PROVIDER_PROXY: _bank_nim_proxy(components),
    }


def _bank_ratio_trajectory(components: Sequence[Mapping[str, Any]], numerator_metric: str, denominator_metric: str,
                           *, abs_numerator: bool = False) -> float | None:
    """YoY delta of one same-provider, same-quarter bank ratio, or None.

    Internal to state derivation only -- not one of the six named bank
    features. Returns None (never a fabricated 0) whenever no compatible
    prior-year-same-quarter pair exists, so a single retained period can
    never present as a trajectory.
    """
    def _ratio(num: Mapping[str, Any], den: Mapping[str, Any]) -> float:
        value = abs(num["raw_value"]) if abs_numerator else num["raw_value"]
        return value / den["raw_value"]

    numerator = _bank_group(components, numerator_metric, fitness=bank_component.STRUCTURED_RESEARCH_COMPONENT)
    denominator = _bank_group(components, denominator_metric, fitness=bank_component.STRUCTURED_RESEARCH_COMPONENT)
    candidates = []
    for key in set(numerator) & set(denominator):
        for (year, quarter), current_num in numerator[key].items():
            if quarter not in (1, 2, 3, 4):
                continue
            current_den = denominator[key].get((year, quarter))
            prior_num = numerator[key].get((year - 1, quarter))
            prior_den = denominator[key].get((year - 1, quarter))
            if not (current_den and prior_num and prior_den):
                continue
            if current_den["raw_value"] == 0 or prior_den["raw_value"] == 0:
                continue
            candidates.append(((year, quarter), _ratio(current_num, current_den) - _ratio(prior_num, prior_den)))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _bank_trend_state(feature: Mapping[str, Any], trajectory: float | None, *, improving_when_falling: bool) -> str:
    if feature["fitness"] != "READY":
        return "UNAVAILABLE"
    if trajectory is None:
        return "AVAILABLE"
    if trajectory == 0:
        return "STABLE"
    falling = trajectory < 0
    return "IMPROVING" if falling == improving_when_falling else "WORSENING"


def _bank_feature_states(features: Mapping[str, Mapping[str, Any]],
                         components: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    npl_trajectory = _bank_ratio_trajectory(components, _NON_PERFORMING_LOAN, _CUSTOMER_LOAN)
    ldr_trajectory = _bank_ratio_trajectory(components, _CUSTOMER_LOAN, _DEPOSIT)
    cir_trajectory = _bank_ratio_trajectory(components, _OPERATION_EXPENSE, _TOTAL_OPERATION_INCOME, abs_numerator=True)
    return {
        # Lower NPL/LDR/CIR is the improving direction in each case: fewer bad
        # loans, a more conservative funding mix, a lower cost-to-income ratio.
        # This is a *direction* classification (mirrors margin/leverage states
        # elsewhere in this module), never a threshold-based investment label.
        BANK_ASSET_QUALITY_STATE: _bank_trend_state(features[BANK_NPL_RATIO], npl_trajectory, improving_when_falling=True),
        BANK_FUNDING_STATE: _bank_trend_state(features[BANK_LDR], ldr_trajectory, improving_when_falling=True),
        BANK_EFFICIENCY_STATE: _bank_trend_state(features[BANK_CIR], cir_trajectory, improving_when_falling=True),
    }


def _securities_usable(component: Mapping[str, Any], *, fitness: str) -> bool:
    return (
        component.get("contract_version") == securities_component.CONTRACT_VERSION
        and component.get("fitness") == fitness
        and _numeric(component.get("raw_value"))
        and component.get("provider") not in (None, "", "unknown")
        and component.get("source_identity") not in (None, "", "unknown")
    )


def _securities_period(component: Mapping[str, Any]) -> tuple[int, int | None] | None:
    year = component.get("year")
    if not isinstance(year, int) or isinstance(year, bool):
        return None
    quarter = component.get("quarter")
    return (year, quarter if isinstance(quarter, int) and not isinstance(quarter, bool) else None)


def _securities_group(components: Sequence[Mapping[str, Any]], metric_id: str, *,
                      fitness: str) -> dict[tuple[str, str, str], dict[tuple[int, int | None], Mapping[str, Any]]]:
    # Keying on statement_family too (beyond ticker/provider) is a representation-
    # compatibility guard: it costs nothing for this milestone's real ratios, since
    # each named ratio's own metric ids are always drawn from one fixed statement
    # family each, but it structurally blocks a hypothetical cross-statement-family
    # pairing rather than relying on that never happening by convention alone.
    grouped: dict[tuple[str, str, str], dict[tuple[int, int | None], Mapping[str, Any]]] = defaultdict(dict)
    for component in components:
        if not _securities_usable(component, fitness=fitness) or component.get("metric_id") != metric_id:
            continue
        period = _securities_period(component)
        if period is None:
            continue
        key = (str(component.get("ticker")), str(component.get("provider")), str(component.get("statement_family")))
        grouped[key][period] = component
    return grouped


def _securities_same_period_pair(components: Sequence[Mapping[str, Any]], numerator_metric: str,
                                 denominator_metric: str) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    """Same-provider, same-period pair of raw structured securities components.

    Mirrors `_bank_same_period_pair`'s same-source-key discipline: a pair can only
    form within one (ticker, provider) group, at one shared (year, quarter) period.
    """
    left = _securities_group(components, numerator_metric, fitness=securities_component.STRUCTURED_RESEARCH_COMPONENT)
    right = _securities_group(components, denominator_metric, fitness=securities_component.STRUCTURED_RESEARCH_COMPONENT)
    candidates = [(period, left[key][period], right[key][period])
                  for key in set(left) & set(right) for period in set(left[key]) & set(right[key])]
    return max(candidates, key=lambda item: item[0])[1:] if candidates else None


def _securities_feature(feature_id: str, *, value: Any = None, fitness: str = "BLOCKED_BY_EVIDENCE",
                        method: str, inputs: Sequence[Mapping[str, Any]] = (),
                        reason_codes: Sequence[str] = (), warnings: Sequence[str] = ()) -> dict[str, Any]:
    return {
        "feature_id": feature_id, "value": value, "fitness": fitness, "method": method,
        "period_identity": [f"{c.get('year')}-Q{c['quarter']}" if c.get("quarter") else f"{c.get('year')}-FY" for c in inputs],
        "provider_source_provenance": [
            {"provider": c.get("provider"), "source_identity": c.get("source_identity"), "retrieved_at": c.get("retrieved_at")}
            for c in inputs
        ],
        "statement_families": sorted({str(c.get("statement_family")) for c in inputs}),
        # Purely descriptive lineage, never a gate: a same-row ratio stays READY
        # even when every input's status here reads UNKNOWN.
        "period_semantics_status": sorted({str(c.get("period_semantics_status")) for c in inputs}),
        "component_currency_status": sorted({str(c.get("currency_status")) for c in inputs}),
        "component_scale_status": sorted({str(c.get("scale_status")) for c in inputs}),
        "limitations": sorted({limitation for c in inputs for limitation in (c.get("limitations") or [])}),
        "reason_codes": list(reason_codes), "warnings": list(warnings), "is_actionable": False,
    }


def _securities_blocked(feature_id: str, *codes: str, method: str = "securities_blocked_by_evidence/v1") -> dict[str, Any]:
    return _securities_feature(feature_id, method=method, reason_codes=codes)


def _securities_not_applicable(feature_id: str) -> dict[str, Any]:
    return _securities_feature(feature_id, fitness="NOT_APPLICABLE", method="securities_entity_applicability/v1",
                               reason_codes=["ISSUER_NOT_SECURITIES"])


def _securities_ratio(feature_id: str, pair: tuple[Mapping[str, Any], Mapping[str, Any]] | None, *,
                      method: str) -> dict[str, Any]:
    if not pair:
        return _securities_blocked(feature_id, "MISSING_SAME_PROVIDER_TICKER_PERIOD_SECURITIES_COMPONENT_PAIR")
    numerator, denominator = pair
    if denominator["raw_value"] == 0:
        return _securities_blocked(feature_id, "ZERO_DENOMINATOR")
    # Never abs()'d: a negative numerator or denominator is retained and surfaced
    # exactly as reported, not silently normalized (task boundary: a negative
    # FVTPL asset amount is treated according to source semantics, not coerced).
    return _securities_feature(feature_id, value=numerator["raw_value"] / denominator["raw_value"], fitness="READY",
                               method=method, inputs=[numerator, denominator])


def _build_securities_features(components: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        SECURITIES_FVTPL_ASSET_INTENSITY: _securities_ratio(
            SECURITIES_FVTPL_ASSET_INTENSITY,
            _securities_same_period_pair(components, _FVTPL_FINANCIAL_ASSETS, _SECURITIES_TOTAL_ASSETS),
            method="same_provider_same_period_fvtpl_asset_intensity/v1"),
        SECURITIES_MARGIN_LENDING_ASSET_INTENSITY: _securities_ratio(
            SECURITIES_MARGIN_LENDING_ASSET_INTENSITY,
            _securities_same_period_pair(components, _MARGIN_LENDING_RECEIVABLE, _SECURITIES_TOTAL_ASSETS),
            method="same_provider_same_period_margin_lending_asset_intensity/v1"),
        SECURITIES_BROKERAGE_REVENUE_MIX: _securities_ratio(
            SECURITIES_BROKERAGE_REVENUE_MIX,
            _securities_same_period_pair(components, _BROKERAGE_REVENUE, _TOTAL_SECURITIES_OPERATING_INCOME),
            method="same_provider_same_period_brokerage_revenue_mix/v1"),
        SECURITIES_LOAN_INTEREST_INCOME_MIX: _securities_ratio(
            SECURITIES_LOAN_INTEREST_INCOME_MIX,
            _securities_same_period_pair(components, _LOAN_RECEIVABLE_INTEREST_INCOME, _TOTAL_SECURITIES_OPERATING_INCOME),
            method="same_provider_same_period_loan_interest_income_mix/v1"),
    }


def _securities_ratio_trajectory(components: Sequence[Mapping[str, Any]], numerator_metric: str,
                                 denominator_metric: str) -> float | None:
    """YoY delta of one same-provider, same-quarter securities ratio, or None.

    Internal to state derivation only -- not one of the four named securities
    features. Returns None (never a fabricated 0) whenever no compatible
    prior-year-same-quarter pair exists, so a single retained period can never
    present as a trajectory. Mirrors `_bank_ratio_trajectory` exactly.
    """
    numerator = _securities_group(components, numerator_metric, fitness=securities_component.STRUCTURED_RESEARCH_COMPONENT)
    denominator = _securities_group(components, denominator_metric, fitness=securities_component.STRUCTURED_RESEARCH_COMPONENT)
    candidates = []
    for key in set(numerator) & set(denominator):
        for (year, quarter), current_num in numerator[key].items():
            if quarter not in (1, 2, 3, 4):
                continue
            current_den = denominator[key].get((year, quarter))
            prior_num = numerator[key].get((year - 1, quarter))
            prior_den = denominator[key].get((year - 1, quarter))
            if not (current_den and prior_num and prior_den):
                continue
            if current_den["raw_value"] == 0 or prior_den["raw_value"] == 0:
                continue
            candidates.append(((year, quarter),
                               current_num["raw_value"] / current_den["raw_value"] - prior_num["raw_value"] / prior_den["raw_value"]))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _securities_trend_state(feature: Mapping[str, Any], trajectory: float | None, *,
                            rising: str, falling: str, stable: str) -> str:
    if feature["fitness"] != "READY":
        return "UNAVAILABLE"
    if trajectory is None:
        return "AVAILABLE"
    if trajectory == 0:
        return stable
    return rising if trajectory > 0 else falling


def _securities_feature_states(features: Mapping[str, Mapping[str, Any]],
                               components: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    fvtpl_trajectory = _securities_ratio_trajectory(components, _FVTPL_FINANCIAL_ASSETS, _SECURITIES_TOTAL_ASSETS)
    margin_trajectory = _securities_ratio_trajectory(components, _MARGIN_LENDING_RECEIVABLE, _SECURITIES_TOTAL_ASSETS)
    brokerage_trajectory = _securities_ratio_trajectory(components, _BROKERAGE_REVENUE, _TOTAL_SECURITIES_OPERATING_INCOME)
    return {
        # No thresholds, no scoring: a pure sign-of-delta trajectory classification,
        # exactly mirroring the bank/gross-margin/working-capital trajectory states.
        SECURITIES_FVTPL_ASSET_INTENSITY_STATE: _securities_trend_state(
            features[SECURITIES_FVTPL_ASSET_INTENSITY], fvtpl_trajectory,
            rising="FVTPL_ASSET_INTENSITY_RISING", falling="FVTPL_ASSET_INTENSITY_FALLING", stable="FVTPL_ASSET_INTENSITY_STABLE"),
        SECURITIES_MARGIN_LENDING_INTENSITY_STATE: _securities_trend_state(
            features[SECURITIES_MARGIN_LENDING_ASSET_INTENSITY], margin_trajectory,
            rising="MARGIN_LENDING_INTENSITY_RISING", falling="MARGIN_LENDING_INTENSITY_FALLING", stable="MARGIN_LENDING_INTENSITY_STABLE"),
        SECURITIES_BROKERAGE_MIX_STATE: _securities_trend_state(
            features[SECURITIES_BROKERAGE_REVENUE_MIX], brokerage_trajectory,
            rising="BROKERAGE_MIX_RISING", falling="BROKERAGE_MIX_FALLING", stable="BROKERAGE_MIX_STABLE"),
    }


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
    cash_ratio = features["cfo_to_net_income_ttm"] if features["cfo_to_net_income_ttm"]["fitness"] == "READY" else features["cfo_to_net_income"]
    cash = "HEALTHY" if cash_ratio["fitness"] in {"READY", "RESEARCH_PROXY"} and _numeric(cash_ratio.get("value")) and cash_ratio["value"] > 0 else "WEAK" if cash_ratio["fitness"] in {"READY", "RESEARCH_PROXY"} and _numeric(cash_ratio.get("value")) else "UNAVAILABLE"
    capital = "UNAVAILABLE"  # Cross-provider values remain explicitly proxies, never state-ready.
    debt_direction = features["debt_to_equity_direction"]
    leverage = _direction(debt_direction, "WORSENING", "IMPROVING", "STABLE")
    if leverage == "UNAVAILABLE":
        leverage = _direction(features["equity_to_assets_direction"], "IMPROVING", "WORSENING", "STABLE")
    resilience = "RESILIENT" if profitability == "PROFITABLE" and margin in {"MARGIN_EXPANDING", "MARGIN_STABLE"} and cash == "HEALTHY" and balance in {"STRENGTHENING", "STABLE"} else "STRESSED" if profitability == "LOSS_MAKING" and cash == "WEAK" else "UNAVAILABLE"
    nwc = features["net_working_capital"]
    # Purely descriptive: a sign classification of the level, never a healthy/avoid verdict.
    working_capital = ("POSITIVE_NET_WORKING_CAPITAL" if nwc["fitness"] == "READY" and nwc["value"] > 0
                       else "NEGATIVE_NET_WORKING_CAPITAL" if nwc["fitness"] == "READY" and nwc["value"] < 0
                       else "ZERO_NET_WORKING_CAPITAL" if nwc["fitness"] == "READY"
                       else "WORKING_CAPITAL_UNAVAILABLE")
    working_capital_trajectory = _direction(features["net_working_capital_direction"],
                                            "WORKING_CAPITAL_IMPROVING", "WORKING_CAPITAL_WORSENING", "WORKING_CAPITAL_STABLE")
    current_ratio_trajectory = _direction(features["current_ratio_direction"],
                                          "CURRENT_RATIO_IMPROVING", "CURRENT_RATIO_WORSENING", "CURRENT_RATIO_STABLE")
    gross_margin_trajectory = _direction(features["gross_margin_direction"],
                                         "GROSS_MARGIN_IMPROVING", "GROSS_MARGIN_WORSENING", "GROSS_MARGIN_STABLE")
    free_cash_flow_proxy_direction = _direction(features["free_cash_flow_proxy_direction"],
                                                 "IMPROVING", "WORSENING", "STABLE")
    turnaround = next((features[item].get("semantic_transition") for item in ("net_income_qoq", "net_income_same_quarter_yoy", "net_income_ttm_yoy") if features[item].get("semantic_transition")), "UNAVAILABLE")
    return {"profitability_state": profitability, "margin_state": margin, "growth_state": growth,
            "earnings_turnaround_state": turnaround,
            "balance_sheet_state": balance, "cash_conversion_state": cash,
            "capital_efficiency_state": capital, "leverage_state": leverage, "resilience_state": resilience,
            "working_capital_state": working_capital, "working_capital_trajectory_state": working_capital_trajectory,
            "current_ratio_trajectory_state": current_ratio_trajectory,
            "gross_margin_trajectory_state": gross_margin_trajectory,
            "free_cash_flow_proxy_direction_state": free_cash_flow_proxy_direction}


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
    if states["working_capital_state"] == "POSITIVE_NET_WORKING_CAPITAL": positive.append(f"{ticker}: positive net working capital")
    if states["working_capital_state"] == "NEGATIVE_NET_WORKING_CAPITAL": negative.append(f"{ticker}: negative net working capital")
    # Thesis-context pairing only: describes co-movement of two already-computed dimensions,
    # never a score, stance gate, or synthetic financial-health formula.
    if states["leverage_state"] == "WORSENING" and states["working_capital_trajectory_state"] == "WORKING_CAPITAL_WORSENING":
        negative.append(f"{ticker}: leverage worsening alongside working capital worsening")
    if states["leverage_state"] == "IMPROVING" and states["working_capital_trajectory_state"] == "WORKING_CAPITAL_IMPROVING":
        positive.append(f"{ticker}: leverage improving alongside working capital improving")
    if states["leverage_state"] == "WORSENING" and states["working_capital_state"] == "POSITIVE_NET_WORKING_CAPITAL":
        conflicts.append(f"{ticker}: leverage worsening despite positive net working capital")
    for feature_id, feature in sorted(features.items()):
        if feature["fitness"] == "BLOCKED_BY_EVIDENCE": missing.append(f"{feature_id}:{','.join(feature['reason_codes'][:1])}")
    return {"positive_evidence": positive[:6], "negative_evidence": negative[:6],
            "conflicting_evidence": conflicts[:6], "missing_dimensions": missing[:12]}


def build_ticker_context(ticker: str, rows: Sequence[Mapping[str, Any]], *, issuer_type: str | None,
                         source_identities: Mapping[str, Any],
                         bank_components: Sequence[Mapping[str, Any]] = (),
                         securities_components: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    normalized_type = str(issuer_type).lower() if issuer_type not in (None, "") else "unknown"
    family = INDUSTRIAL if normalized_type == "corporate" else LIMITED
    ids = ("net_income_sign", "net_margin", "pbt_margin", "gross_margin", "net_margin_direction", "gross_margin_direction", "revenue_qoq", "profit_before_tax_qoq", "net_income_qoq",
           "revenue_same_quarter_yoy", "profit_before_tax_same_quarter_yoy", "net_income_same_quarter_yoy", "revenue_ytd_yoy", "net_income_ytd_yoy", "revenue_ttm_yoy", "profit_before_tax_ttm_yoy", "net_income_ttm_yoy", "operating_cash_flow_ttm_yoy", "revenue_ttm", "profit_before_tax_ttm", "net_income_ttm", "operating_cash_flow_ttm", "ttm_net_margin", "ttm_pbt_margin", "operating_cash_flow_sign", "operating_cash_flow_qoq", "operating_cash_flow_same_quarter_yoy", "cfo_to_net_income", "cfo_to_net_income_ttm",
           "free_cash_flow_proxy", "free_cash_flow_proxy_direction", "equity_to_assets", "cash_to_assets", "debt_to_equity", "debt_to_assets", "debt_to_equity_direction", "equity_to_assets_direction", "assets_yoy", "equity_yoy",
           "cash_yoy", "same_provider_roa", "same_provider_roe", "same_provider_roa_eop_proxy", "same_provider_roe_eop_proxy", "same_provider_asset_turnover_eop_proxy", "mixed_provider_roa_proxy", "mixed_provider_asset_turnover_proxy",
           "net_working_capital", "current_ratio", "net_working_capital_direction", "current_ratio_direction")
    if family == LIMITED:
        features = {feature_id: _not_applicable(feature_id) for feature_id in ids}
        states = {"profitability_state": "UNAVAILABLE", "margin_state": "UNAVAILABLE", "growth_state": "UNAVAILABLE", "earnings_turnaround_state": "UNAVAILABLE",
                  "balance_sheet_state": "UNAVAILABLE", "cash_conversion_state": "UNAVAILABLE",
                  "capital_efficiency_state": "UNAVAILABLE", "leverage_state": "UNAVAILABLE", "resilience_state": "UNAVAILABLE",
                  "working_capital_state": "WORKING_CAPITAL_UNAVAILABLE", "working_capital_trajectory_state": "UNAVAILABLE",
                  "current_ratio_trajectory_state": "UNAVAILABLE", "gross_margin_trajectory_state": "UNAVAILABLE",
                  "free_cash_flow_proxy_direction_state": "UNAVAILABLE"}
    else:
        revenue = _best_series(rows, "revenue", FLOW_STANDALONE)
        pbt = _best_series(rows, "profit_before_tax", FLOW_STANDALONE)
        income = _best_series(rows, "net_income", FLOW_STANDALONE)
        ocf = _best_series(rows, "operating_cash_flow", FLOW_STANDALONE)
        revenue_ytd = _best_series(rows, "revenue", "YTD_CUMULATIVE_INTERIM")
        income_ytd = _best_series(rows, "net_income", "YTD_CUMULATIVE_INTERIM")
        revenue_ttm, revenue_ttm_inputs = _ttm_sum(revenue, "revenue_ttm")
        pbt_ttm, pbt_ttm_inputs = _ttm_sum(pbt, "profit_before_tax_ttm")
        income_ttm, income_ttm_inputs = _ttm_sum(income, "net_income_ttm")
        ocf_ttm, ocf_ttm_inputs = _ttm_sum(ocf, "operating_cash_flow_ttm")
        net_margin = _ratio("net_margin", _same_period_pair(rows, "net_income", "revenue", FLOW_STANDALONE), method="same_provider_same_period_net_margin/v2")
        pbt_margin = _ratio("pbt_margin", _same_period_pair(rows, "profit_before_tax", "revenue", FLOW_STANDALONE), method="same_provider_same_period_pbt_margin/v2")
        # Same-provider, same-period, standalone-quarter only: `gross_profit` is itself
        # canonicalized KBS-only (canonical_financial_facts.METRIC_REGISTRY), and this
        # pairing's own semantic gate independently keeps out any VCI-provider revenue a
        # ticker might also carry, since VCI income-statement facts never reach
        # `FLOW_STANDALONE` (structured_financial_period_semantics.py's provider-scoped
        # contract). A negative gross profit is a valid input and yields a negative
        # margin -- `_ratio` never special-cases the numerator's sign, only a zero
        # denominator.
        gross_margin = _ratio("gross_margin", _same_period_pair(rows, "gross_profit", "revenue", FLOW_STANDALONE), method="same_provider_same_period_gross_margin/v2")
        gross_margin_direction = _pit_ratio_direction_for(rows, "gross_profit", "revenue", "gross_margin_direction",
                                                           method="same_provider_same_quarter_yoy_gross_margin/v1", semantic=FLOW_STANDALONE)
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
        def ttm_ratio(feature_id: str, numerator: Mapping[str, Any], numerator_inputs: Sequence[Mapping[str, Any]], denominator: Mapping[str, Any], denominator_inputs: Sequence[Mapping[str, Any]], method: str) -> dict[str, Any]:
            if numerator["fitness"] != "READY" or denominator["fitness"] != "READY" or not numerator_inputs or not denominator_inputs:
                return _blocked(feature_id, "MISSING_COMPATIBLE_TTM_INPUTS")
            n_row, d_row = numerator_inputs[-1], denominator_inputs[-1]
            n_key, d_key = _source_key(n_row), _source_key(d_row)
            if n_key[0] != d_key[0] or n_key[1] != d_key[1] or n_key[3:] != d_key[3:]:
                return _blocked(feature_id, "TTM_PROVIDER_SCOPE_CURRENCY_SCALE_INCOMPATIBLE")
            if denominator["value"] == 0:
                return _blocked(feature_id, "ZERO_DENOMINATOR")
            return _feature(feature_id, value=numerator["value"] / denominator["value"], fitness="READY", method=method,
                            inputs=list(numerator_inputs) + list(denominator_inputs), growth_basis="TTM")
        features = {
            "net_income_sign": _feature("net_income_sign", value=_latest(income)["reported_value"], fitness="READY", method="latest_compatible_standalone_sign/v2", inputs=[_latest(income)]) if _latest(income) else _blocked("net_income_sign", "MISSING_STANDALONE_NET_INCOME"),
            "net_margin": net_margin, "pbt_margin": pbt_margin, "gross_margin": gross_margin,
            "net_margin_direction": margin_direction, "gross_margin_direction": gross_margin_direction,
            "revenue_qoq": _growth("revenue_qoq", revenue, basis="QOQ_STANDALONE"),
            "profit_before_tax_qoq": _growth("profit_before_tax_qoq", pbt, basis="QOQ_STANDALONE", earnings=True),
            "net_income_qoq": _growth("net_income_qoq", income, basis="QOQ_STANDALONE", earnings=True),
            "revenue_same_quarter_yoy": _growth("revenue_same_quarter_yoy", revenue, basis="SAME_QUARTER_YOY"),
            "profit_before_tax_same_quarter_yoy": _growth("profit_before_tax_same_quarter_yoy", pbt, basis="SAME_QUARTER_YOY", earnings=True),
            "net_income_same_quarter_yoy": _growth("net_income_same_quarter_yoy", income, basis="SAME_QUARTER_YOY", earnings=True),
            "revenue_ytd_yoy": _growth("revenue_ytd_yoy", revenue_ytd, basis="YTD_YOY"),
            "net_income_ytd_yoy": _growth("net_income_ytd_yoy", income_ytd, basis="YTD_YOY", earnings=True),
            "revenue_ttm": revenue_ttm, "profit_before_tax_ttm": pbt_ttm, "net_income_ttm": income_ttm, "operating_cash_flow_ttm": ocf_ttm,
            "revenue_ttm_yoy": _ttm_yoy("revenue_ttm_yoy", revenue), "profit_before_tax_ttm_yoy": _ttm_yoy("profit_before_tax_ttm_yoy", pbt), "net_income_ttm_yoy": _ttm_yoy("net_income_ttm_yoy", income), "operating_cash_flow_ttm_yoy": _ttm_yoy("operating_cash_flow_ttm_yoy", ocf),
            "ttm_net_margin": ttm_ratio("ttm_net_margin", income_ttm, income_ttm_inputs, revenue_ttm, revenue_ttm_inputs, "same_provider_ttm_net_margin/v2"),
            "ttm_pbt_margin": ttm_ratio("ttm_pbt_margin", pbt_ttm, pbt_ttm_inputs, revenue_ttm, revenue_ttm_inputs, "same_provider_ttm_pbt_margin/v2"),
            "operating_cash_flow_sign": _feature("operating_cash_flow_sign", value=_latest(ocf)["reported_value"], fitness="READY", method="latest_compatible_standalone_cfo_sign/v2", inputs=[_latest(ocf)]) if _latest(ocf) else _blocked("operating_cash_flow_sign", "MISSING_STANDALONE_OPERATING_CASH_FLOW"),
            "operating_cash_flow_qoq": _growth("operating_cash_flow_qoq", ocf, basis="QOQ_STANDALONE"),
            "operating_cash_flow_same_quarter_yoy": _growth("operating_cash_flow_same_quarter_yoy", ocf, basis="SAME_QUARTER_YOY"),
            "cfo_to_net_income": (_feature("cfo_to_net_income", value=cash_pair[0]["reported_value"] / cash_pair[1]["reported_value"], fitness="READY", method="same_provider_cross_statement_cash_earnings_ratio/v2", inputs=list(cash_pair), warnings=["NEGATIVE_NET_INCOME_RATIO_RETAINED_AS_REPORTED"] if cash_pair[1]["reported_value"] < 0 else []) if cash_pair and cash_pair[1]["reported_value"] != 0 else _blocked("cfo_to_net_income", "ZERO_NET_INCOME_DENOMINATOR" if cash_pair else "MISSING_SAME_PROVIDER_CFO_AND_NET_INCOME")),
            "cfo_to_net_income_ttm": ttm_ratio("cfo_to_net_income_ttm", ocf_ttm, ocf_ttm_inputs, income_ttm, income_ttm_inputs, "same_provider_cross_statement_ttm_cash_earnings_ratio/v2"),
            # Direct canonical OCF + signed canonical CapEx in one exact compatible
            # standalone-quarter representation. It never affects readiness or decisions.
            "free_cash_flow_proxy": _signed_flow_sum(
                "free_cash_flow_proxy",
                _same_period_pair(rows, "operating_cash_flow", "capital_expenditure", FLOW_STANDALONE),
                method="same_provider_same_period_operating_cash_flow_plus_signed_capex/v1"),
            "free_cash_flow_proxy_direction": _signed_flow_sum_direction(
                rows, feature_id="free_cash_flow_proxy_direction"),
            "equity_to_assets": _ratio("equity_to_assets", _same_period_pair(rows, "shareholders_equity", "total_assets", PIT), method="same_provider_same_period_equity_to_assets/v2"),
            "cash_to_assets": _ratio("cash_to_assets", _same_period_pair(rows, "cash_and_cash_equivalents", "total_assets", PIT), method="same_provider_same_period_cash_to_assets/v2"),
            "debt_to_equity": _ratio("debt_to_equity", _same_period_pair(rows, "total_interest_bearing_debt", "shareholders_equity", PIT), method="same_provider_same_period_explicit_debt_to_equity/v2"),
            "debt_to_assets": _ratio("debt_to_assets", _same_period_pair(rows, "total_interest_bearing_debt", "total_assets", PIT), method="same_provider_same_period_explicit_debt_to_assets/v2"),
            "debt_to_equity_direction": _pit_ratio_direction_for(rows, "total_interest_bearing_debt", "shareholders_equity", "debt_to_equity_direction"),
            "equity_to_assets_direction": _pit_ratio_direction(rows),
            "assets_yoy": _pit_trajectory(rows, "total_assets"), "equity_yoy": _pit_trajectory(rows, "shareholders_equity"), "cash_yoy": _pit_trajectory(rows, "cash_and_cash_equivalents"),
            # Legacy IDs stay present as aliases for the explicitly named EOP proxies; the
            # old average-balance implication is removed rather than silently retained.
            "same_provider_roa": _same_provider_eop_proxy(rows, "net_income", "total_assets", "same_provider_roa"),
            "same_provider_roe": _same_provider_eop_proxy(rows, "net_income", "shareholders_equity", "same_provider_roe"),
            "same_provider_roa_eop_proxy": _same_provider_eop_proxy(rows, "net_income", "total_assets", "same_provider_roa_eop_proxy"),
            "same_provider_roe_eop_proxy": _same_provider_eop_proxy(rows, "net_income", "shareholders_equity", "same_provider_roe_eop_proxy"),
            "same_provider_asset_turnover_eop_proxy": _same_provider_eop_proxy(rows, "revenue", "total_assets", "same_provider_asset_turnover_eop_proxy"),
            "mixed_provider_roa_proxy": _mixed_provider_proxy(rows, "net_income", "total_assets", "mixed_provider_roa_proxy"),
            "mixed_provider_asset_turnover_proxy": _mixed_provider_proxy(rows, "revenue", "total_assets", "mixed_provider_asset_turnover_proxy"),
            "net_working_capital": _difference("net_working_capital", _same_period_pair(rows, "current_assets", "current_liabilities", PIT), method="same_provider_same_period_net_working_capital/v2"),
            "current_ratio": _ratio("current_ratio", _same_period_pair(rows, "current_assets", "current_liabilities", PIT), method="same_provider_same_period_current_ratio/v2"),
            "net_working_capital_direction": _pit_component_direction(rows, "current_assets", "current_liabilities", "net_working_capital_direction"),
            "current_ratio_direction": _pit_ratio_direction_for(rows, "current_assets", "current_liabilities", "current_ratio_direction", method="same_provider_point_in_time_current_ratio_yoy/v2"),
        }
        states = _feature_states(features)

    # Bank specialist family: purely additive over whatever the INDUSTRIAL/LIMITED
    # branch above already produced.  Never runs for a non-bank ticker, even if
    # bank_components was (incorrectly) supplied for one -- entity classification
    # is the only gate, mirroring the same rule the corporate family already
    # enforces the other way around (family == LIMITED never gets corporate ratios).
    is_bank = normalized_type == BANK
    bank_features = _build_bank_features(bank_components) if is_bank else {
        feature_id: _bank_not_applicable(feature_id) for feature_id in BANK_FEATURE_IDS}
    features.update(bank_features)
    states.update(_bank_feature_states(bank_features, bank_components) if is_bank
                  else {name: "NOT_APPLICABLE" for name in BANK_STATE_NAMES})

    # Securities specialist family: purely additive, mirrors the bank family above
    # exactly (including the same one-way entity-classification gate: a non-securities
    # ticker never gets securities ratios even if securities_components was supplied).
    is_securities = normalized_type == SECURITIES
    securities_features = _build_securities_features(securities_components) if is_securities else {
        feature_id: _securities_not_applicable(feature_id) for feature_id in SECURITIES_FEATURE_IDS}
    features.update(securities_features)
    states.update(_securities_feature_states(securities_features, securities_components) if is_securities
                  else {name: "NOT_APPLICABLE" for name in SECURITIES_STATE_NAMES})

    readiness_features = ("net_margin", "pbt_margin", "gross_margin", "equity_to_assets", "cash_to_assets", "assets_yoy", "equity_yoy", "current_ratio")
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
            "bank_specialist_contract_version": bank_component.CONTRACT_VERSION if is_bank else None,
            "securities_specialist_contract_version": securities_component.CONTRACT_VERSION if is_securities else None,
            "authority_boundary": {"is_actionable": False, "financial_authority_promoted": False, "decision_integration": False}}


def build_artifact(*, tickers: Sequence[str], rows: Sequence[Mapping[str, Any]], issuer_types: Mapping[str, str | None],
                   source_identities: Mapping[str, Any], requested_at: str,
                   bank_components: Sequence[Mapping[str, Any]] = (),
                   securities_components: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    names = sorted({str(ticker).upper() for ticker in tickers})
    by_ticker: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if ticker in names:
            by_ticker[ticker].append(row)
    bank_by_ticker: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for component in bank_components:
        ticker = str(component.get("ticker") or "").upper()
        if ticker in names:
            bank_by_ticker[ticker].append(component)
    securities_by_ticker: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for component in securities_components:
        ticker = str(component.get("ticker") or "").upper()
        if ticker in names:
            securities_by_ticker[ticker].append(component)
    records = {ticker: build_ticker_context(ticker, by_ticker.get(ticker, []), issuer_type=issuer_types.get(ticker),
                                            source_identities=source_identities,
                                            bank_components=bank_by_ticker.get(ticker, []),
                                            securities_components=securities_by_ticker.get(ticker, [])) for ticker in names}
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
