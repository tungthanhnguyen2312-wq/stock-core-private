"""Personal Portfolio Quantitative Risk Decomposition (PERSONAL_PORTFOLIO_QUANT_RISK_DECOMPOSITION_V1).

Deterministic, local-only descriptive risk decomposition over the owner's real current
investment portfolio: concentration (HHI/effective N), per-security realized volatility,
pairwise correlation, covariance integrity, portfolio volatility (two distinguished views),
risk contribution, diversification, and a mechanical leave-one-position-to-cash sensitivity.

This module computes NO new decision. It reuses, rather than reimplements, the existing return/
volatility/correlation/covariance engine in ``current_portfolio_risk_research.py`` (its window
construction, ``simple_close_to_close_returns``, per-security volatility, pairwise Pearson
correlation, and the ``T >= N + 5`` joint-matrix numerical guard, all called verbatim) and the
existing correlation-cluster engine in ``correlation_concentration_guard.py`` (its frozen,
un-retuned 0.80 ``DETERMINISTIC_RESEARCH_HEURISTIC_NOT_STATISTICALLY_CALIBRATED`` threshold). It
also reuses ``portfolio_aware_decision.derive_portfolio_state`` for already-qualified current
quantities, market values, NAV weights, sector, and the qualified multi-account aggregate (NAV/
cash/margin) rather than re-deriving any of that.

Descriptive/research-only, explicitly:
- No BUY/SELL decision, no optimal portfolio, no target weights, no Kelly sizing.
- No VaR/CVaR authority, no probability-based sizing, no expected-return optimization.
- No efficient frontier, no Sharpe-based ranking, no automatic capital rotation, no execution.
A high measured risk-contribution percentage is never itself transformed into REDUCE/SELL.

Privacy: everything here stays under the private local root. An owner-excluded ticker's current
confirmed exposure is retained in every aggregate NAV/exposure total (a research exclusion must
never manufacture zero economic exposure), but its identity never appears anywhere in this
artifact -- only an anonymized ``excluded_confirmed_exposure`` aggregate bucket. A
CURRENT_POSITION_UNRESOLVED ticker never receives a numeric weight or risk contribution; it is
named only in the coverage section (mirroring existing Action Center precedent for unresolved
positions, which are already named there -- unlike an owner exclusion, an unresolved
reconciliation state is not an identity-privacy concern).
"""
from __future__ import annotations

import hashlib
import json
import math
from itertools import combinations
from typing import Any, Mapping, Sequence

import numpy as np

import correlation_concentration_guard as _guard
import current_portfolio_risk_research as _cprr
import portfolio_aware_decision as _pad

CONTRACT_VERSION = "personal_portfolio_quant_risk_decomposition/v1"
MILESTONE = "PERSONAL_PORTFOLIO_QUANT_RISK_DECOMPOSITION_V1"
STANDARD_RISK_LOOKBACKS = _cprr.STANDARD_RISK_LOOKBACKS
PRICE_BASIS = _cprr.PRICE_BASIS

EQUITY_SLEEVE_VOLATILITY = "EQUITY_SLEEVE_VOLATILITY"
NAV_SCALED_EQUITY_RISK = "NAV_SCALED_EQUITY_RISK"
PORTFOLIO_VOLATILITY_VIEWS = (EQUITY_SLEEVE_VOLATILITY, NAV_SCALED_EQUITY_RISK)

SENSITIVITY_CONTRACT = "MOVE_POSITION_TO_CASH_VOLATILITY_SENSITIVITY"

FULL_PORTFOLIO_COVERAGE = "FULL_PORTFOLIO_COVERAGE"
QUALIFIED_COVERED_SUBSET = "QUALIFIED_COVERED_SUBSET"
PORTFOLIO_INPUT_COVERAGE_PARTIAL = "PORTFOLIO_INPUT_COVERAGE_PARTIAL"
INSUFFICIENT_PORTFOLIO_TRUTH = "INSUFFICIENT_PORTFOLIO_TRUTH"

FULL_PORTFOLIO_RISK_READY = "FULL_PORTFOLIO_RISK_READY"
COVERED_SUBSET_RISK_READY = "COVERED_SUBSET_RISK_READY"
INSUFFICIENT_RISK_COVERAGE = "INSUFFICIENT_RISK_COVERAGE"

ACCOUNT_LEVEL_POSITION_RISK_NOT_QUALIFIED = "ACCOUNT_LEVEL_POSITION_RISK_NOT_QUALIFIED"

# Reconciliation tolerances for the descriptive risk-contribution identity below (Section 10):
# sum(component_contribution_i) ~= portfolio_volatility and sum(component_contribution_pct_i) ~= 1.
_RECONCILIATION_REL_TOL = 1e-6
_RECONCILIATION_ABS_TOL = 1e-9
# A sample covariance's minimum eigenvalue can be a tiny negative float-noise value even when the
# matrix is mathematically PSD; only clip within this band, never a genuinely singular/indefinite one
# (JOINT_MATRIX_NUMERICAL_GUARD_FAILED already rejects those upstream in ``_joint_context``).
_VARIANCE_CLIP_TOLERANCE = 1e-12

_RECOGNIZED_WORKBOOK_SHEET_TOKENS = frozenset({"trade", "dividend", "money", "margin", "accountsnapshot", "portfoliopolicy", "total"})


class PersonalPortfolioQuantRiskError(ValueError):
    """A required input cannot be interpreted safely."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _isclose(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=_RECONCILIATION_REL_TOL, abs_tol=_RECONCILIATION_ABS_TOL)


# ── Source coverage (Section 4) ────────────────────────────────────────────────────────────────

def _normal_sheet_token(name: Any) -> str:
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def _unadmitted_sheet_names(event_ledger: Mapping[str, Any] | None) -> list[str] | None:
    """Sheets present in the source workbook but never ingested by any recognized parser.

    Returns ``None`` (unknown, not zero) when no ledger was supplied -- an absent ledger must
    never read as "no unadmitted sheets exist". This is a dynamic check against the ledger's own
    ``sheet_inventory`` rather than a hardcoded institutional fact, so it naturally re-evaluates if
    the owner's workbook shape changes.
    """
    if not isinstance(event_ledger, Mapping):
        return None
    inventory = event_ledger.get("sheet_inventory") or []
    return sorted(
        str(entry.get("sheet")) for entry in inventory
        if isinstance(entry, Mapping) and entry.get("sheet") and _normal_sheet_token(entry.get("sheet")) not in _RECOGNIZED_WORKBOOK_SHEET_TOKENS
    )


def _source_coverage(
    *, confirmed_count: int, unresolved_count: int, portfolio_snapshot: Mapping[str, Any], event_ledger: Mapping[str, Any] | None,
) -> dict[str, Any]:
    reasons: list[str] = []
    attribution_summary = portfolio_snapshot.get("position_account_attribution_summary") or {}
    unadmitted = _unadmitted_sheet_names(event_ledger)
    if confirmed_count == 0:
        status = INSUFFICIENT_PORTFOLIO_TRUTH
        reasons.append("NO_CURRENT_CONFIRMED_POSITIONS")
    elif unresolved_count > 0:
        status = PORTFOLIO_INPUT_COVERAGE_PARTIAL
        reasons.append("CURRENT_POSITION_UNRESOLVED_TICKERS_PRESENT")
    elif unadmitted is None:
        status = QUALIFIED_COVERED_SUBSET
        reasons.append("EVENT_LEDGER_NOT_SUPPLIED_UNADMITTED_SOURCE_MATERIAL_UNKNOWN")
    elif unadmitted:
        status = QUALIFIED_COVERED_SUBSET
        reasons.append("UNADMITTED_SOURCE_SHEET_IDENTIFIER_NAMESPACE_NOT_CROSSWALKED")
    elif attribution_summary.get("tickers_unresolved_attribution_only", 0) > 0:
        status = QUALIFIED_COVERED_SUBSET
        reasons.append("SOME_LEDGER_ACTIVITY_HAS_NO_ACCOUNT_ATTRIBUTION")
    else:
        status = FULL_PORTFOLIO_COVERAGE
    return {
        "status": status,
        "reason_codes": reasons,
        "unadmitted_source_sheets": unadmitted,
        "current_position_unresolved_count": unresolved_count,
        "authority_boundary": {
            "does_not_block_named_cohort_research_merely_because_attribution_is_partial": True,
            "unadmitted_sheet_crosswalk_never_guessed": True,
        },
    }


# ── Weight/exposure derivation over the already-qualified portfolio state ──────────────────────

def _partition_positions(state: Mapping[str, Any]) -> tuple[dict[str, dict], list[str], list[str], list[str]]:
    """confirmed(dict ticker->derived position), named_cohort tickers, excluded_confirmed tickers,
    unresolved tickers -- all sorted, deterministic."""
    positions = state.get("positions") or {}
    confirmed = {ticker: row for ticker, row in positions.items() if row.get("current_position_status") == "CURRENT_CONFIRMED"}
    named_cohort = sorted(ticker for ticker, row in confirmed.items() if row.get("is_active", True))
    excluded_confirmed = sorted(ticker for ticker, row in confirmed.items() if not row.get("is_active", True))
    unresolved = sorted(ticker for ticker, row in positions.items() if row.get("current_position_status") == "CURRENT_POSITION_UNRESOLVED")
    return confirmed, named_cohort, excluded_confirmed, unresolved


def _hhi_context(*, confirmed: Mapping[str, dict], named_cohort: Sequence[str], excluded_confirmed: Sequence[str]) -> dict[str, Any]:
    """Equity-sleeve concentration: HHI over priced, named (non-excluded) confirmed positions only."""
    priced = {ticker: confirmed[ticker]["current_market_value"] for ticker in named_cohort if confirmed[ticker].get("current_market_value") is not None}
    unpriced = sorted(ticker for ticker in named_cohort if ticker not in priced)
    total = sum(priced.values())
    if not priced or total <= 0:
        return {
            "status": "INSUFFICIENT_PRICED_EQUITY_FOR_CONCENTRATION", "hhi": None, "effective_n": None,
            "equity_normalized_weights": {}, "priced_named_count": len(priced), "unpriced_named_tickers": unpriced,
            "definition": {"hhi": "sum(equity_normalized_weight_i ** 2)", "effective_n": "1 / hhi"},
        }
    weights = {ticker: value / total for ticker, value in priced.items()}
    hhi = sum(weight ** 2 for weight in weights.values())
    return {
        "status": "AVAILABLE", "hhi": hhi, "effective_n": (1.0 / hhi) if hhi > 0 else None,
        "equity_normalized_weights": dict(sorted(weights.items())), "priced_named_count": len(priced),
        "unpriced_named_tickers": unpriced,
        "definition": {"hhi": "sum(equity_normalized_weight_i ** 2)", "effective_n": "1 / hhi",
                       "normalization_basis": "PRICED_NAMED_CONFIRMED_EQUITY_ONLY_EXCLUDES_OWNER_EXCLUDED_AND_UNPRICED"},
    }


# ── Per-security / pairwise / covariance, all reusing current_portfolio_risk_research verbatim ──

def _build_windows(
    *, named_cohort: Sequence[str], price_history_snapshot: Mapping[str, Any], as_of_session: str,
) -> tuple[dict[str, dict[int, dict[str, Any]]], list[str]]:
    sessions = _cprr._session_calendar(price_history_snapshot, as_of_session)
    records = price_history_snapshot.get("records") or {}
    windows: dict[str, dict[int, dict[str, Any]]] = {}
    for ticker in named_cohort:
        closes, duplicate_sessions, input_problems = _cprr._price_index(records.get(ticker) or {}, as_of_session=as_of_session)
        windows[ticker] = {
            lookback: _cprr._window_for(
                ticker=ticker, lookback=lookback, sessions=sessions, close_index=closes,
                duplicate_sessions=duplicate_sessions, input_problems=input_problems,
            )
            for lookback in STANDARD_RISK_LOOKBACKS
        }
    return windows, sessions


def _c1_compatible_risk_research(
    *, named_cohort: Sequence[str], windows: Mapping[str, Mapping[int, dict[str, Any]]], as_of_session: str,
    sector_by_ticker: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """A minimal ``current_portfolio_risk_research/v1``-shaped subset -- only the fields
    ``correlation_concentration_guard`` actually reads -- built from the exact same reused
    per-lookback windows, so its pairwise/joint content is byte-identical in method to C1's own.
    """
    pairwise: list[dict[str, Any]] = []
    for lookback in STANDARD_RISK_LOOKBACKS:
        for ticker_i, ticker_j in combinations(named_cohort, 2):
            first_sector = (sector_by_ticker or {}).get(ticker_i)
            second_sector = (sector_by_ticker or {}).get(ticker_j)
            same_sector = None if first_sector is None or second_sector is None else first_sector == second_sector
            pairwise.append(_cprr._pairwise(
                ticker_i=ticker_i, ticker_j=ticker_j, lookback=lookback, as_of_session=as_of_session,
                first=windows[ticker_i][lookback], second=windows[ticker_j][lookback], same_sector=same_sector,
            ))
    joint = {
        f"L{lookback}": _cprr._joint_context(lookback=lookback, windows={ticker: windows[ticker][lookback] for ticker in named_cohort})
        for lookback in STANDARD_RISK_LOOKBACKS
    }
    body = {
        "contract_version": _cprr.CONTRACT_VERSION,
        "metadata": {"as_of_session": as_of_session},
        "ticker_risk_context": {ticker: {} for ticker in named_cohort},
        "pairwise_relationships": pairwise,
        "joint_matrix_context": joint,
    }
    return {**body, **_cprr.content_identity(body)}


def _correlation_clusters(*, c1_compatible: Mapping[str, Any], named_cohort: Sequence[str]) -> dict[str, Any]:
    clusters: dict[str, Any] = {}
    for lookback in STANDARD_RISK_LOOKBACKS:
        if len(named_cohort) < 2:
            clusters[f"L{lookback}"] = {"status": "INPUT_COHORT_TOO_SMALL_FOR_CONCENTRATION_ANALYSIS", "concentration_groups": []}
            continue
        clusters[f"L{lookback}"] = _guard.build_artifact(risk_research=c1_compatible, securities=named_cohort, lookback=lookback)
    return clusters


# ── Portfolio volatility / risk contribution / diversification (new to this milestone) ─────────

def _weight_vector(*, included: Sequence[str], weights_by_ticker: Mapping[str, float]) -> np.ndarray | None:
    if any(ticker not in weights_by_ticker for ticker in included):
        return None
    return np.array([weights_by_ticker[ticker] for ticker in included], dtype=float)


def _portfolio_variance(*, weights: np.ndarray, covariance: np.ndarray) -> float | None:
    variance = float(weights @ covariance @ weights)
    if variance < -_VARIANCE_CLIP_TOLERANCE:
        return None
    return max(variance, 0.0)


def _view_weights(*, view: str, included: Sequence[str], market_value_by_ticker: Mapping[str, float], effective_nav: float | None) -> dict[str, float] | None:
    if view == EQUITY_SLEEVE_VOLATILITY:
        total = sum(market_value_by_ticker.get(ticker, 0.0) for ticker in included)
        if total <= 0:
            return None
        return {ticker: market_value_by_ticker[ticker] / total for ticker in included}
    if not effective_nav or effective_nav <= 0:
        return None
    return {ticker: market_value_by_ticker.get(ticker, 0.0) / effective_nav for ticker in included}


def _portfolio_volatility_view(
    *, view: str, lookback: int, joint: Mapping[str, Any], market_value_by_ticker: Mapping[str, float], effective_nav: float | None,
) -> dict[str, Any]:
    included = joint.get("included_tickers") or []
    if joint.get("status") != "JOINT_MATRIX_READY" or not included:
        return {"status": "UNAVAILABLE", "reason": joint.get("status"), "view": view, "lookback_sessions": lookback,
                "included_tickers": included, "portfolio_volatility": None, "portfolio_variance": None, "weights": {}}
    weights_map = _view_weights(view=view, included=included, market_value_by_ticker=market_value_by_ticker, effective_nav=effective_nav)
    if weights_map is None:
        return {"status": "UNAVAILABLE", "reason": "WEIGHT_BASIS_UNAVAILABLE", "view": view, "lookback_sessions": lookback,
                "included_tickers": included, "portfolio_volatility": None, "portfolio_variance": None, "weights": {}}
    weights = np.array([weights_map[ticker] for ticker in included], dtype=float)
    covariance = np.array(joint["covariance_matrix"], dtype=float)
    variance = _portfolio_variance(weights=weights, covariance=covariance)
    if variance is None:
        return {"status": "NUMERICAL_GUARD_FAILED", "reason": "NEGATIVE_PORTFOLIO_VARIANCE", "view": view, "lookback_sessions": lookback,
                "included_tickers": included, "portfolio_volatility": None, "portfolio_variance": None, "weights": weights_map}
    weight_sum = float(weights.sum())
    return {
        "status": "AVAILABLE", "view": view, "lookback_sessions": lookback, "included_tickers": included,
        "weight_sum": weight_sum,
        "weight_sum_exceeds_one": weight_sum > 1.0 + 1e-9,
        "portfolio_variance": variance, "portfolio_volatility": math.sqrt(variance), "weights": weights_map,
        "formula": {"portfolio_variance": "w' Sigma w", "portfolio_volatility": "sqrt(w' Sigma w)"},
    }


def _risk_contribution(*, view_result: Mapping[str, Any], covariance: np.ndarray | None) -> dict[str, Any]:
    if view_result.get("status") != "AVAILABLE" or covariance is None:
        return {"status": "UNAVAILABLE", "reason": view_result.get("status"), "per_ticker": {}, "reconciliation": None}
    sigma_p = view_result["portfolio_volatility"]
    included = view_result["included_tickers"]
    if not sigma_p or sigma_p <= 0:
        return {"status": "UNAVAILABLE", "reason": "ZERO_PORTFOLIO_VOLATILITY", "per_ticker": {}, "reconciliation": None}
    weights = np.array([view_result["weights"][ticker] for ticker in included], dtype=float)
    sigma_w = covariance @ weights
    marginal = sigma_w / sigma_p
    component = weights * marginal
    component_pct = component / sigma_p
    per_ticker = {
        ticker: {
            "capital_weight": float(weights[index]),
            "marginal_contribution": float(marginal[index]),
            "component_contribution": float(component[index]),
            "component_contribution_pct": float(component_pct[index]),
            "capital_weight_minus_risk_contribution_pct": float(weights[index] - component_pct[index]),
        }
        for index, ticker in enumerate(included)
    }
    sum_component = float(component.sum())
    sum_pct = float(component_pct.sum())
    reconciled = _isclose(sum_component, sigma_p) and _isclose(sum_pct, 1.0)
    return {
        "status": "AVAILABLE", "per_ticker": per_ticker,
        "reconciliation": {
            "sum_component_contribution": sum_component, "portfolio_volatility": sigma_p,
            "sum_component_contribution_pct": sum_pct,
            "status": "PASS" if reconciled else "FAIL",
            "tolerance": {"rel_tol": _RECONCILIATION_REL_TOL, "abs_tol": _RECONCILIATION_ABS_TOL},
        },
        "authority_boundary": {"descriptive_only": True, "high_risk_contribution_is_not_a_reduce_or_sell_signal": True},
    }


def _diversification(*, view_result: Mapping[str, Any], covariance: np.ndarray | None, pairwise_ready: Sequence[Mapping[str, Any]], cluster_groups: Sequence[Mapping[str, Any]], nominal_holding_count: int, effective_n: float | None) -> dict[str, Any]:
    ratio = None
    if view_result.get("status") == "AVAILABLE" and covariance is not None and view_result.get("portfolio_volatility"):
        included = view_result["included_tickers"]
        individual_vol = np.sqrt(np.clip(np.diag(covariance), 0.0, None))
        weights = np.array([view_result["weights"][ticker] for ticker in included], dtype=float)
        weighted_sum = float(np.sum(weights * individual_vol))
        ratio = weighted_sum / view_result["portfolio_volatility"]
    correlations = [row["correlation"] for row in pairwise_ready]
    top_pairs = sorted(pairwise_ready, key=lambda row: abs(row["correlation"]), reverse=True)[:5]
    return {
        "status": "AVAILABLE" if ratio is not None else "UNAVAILABLE",
        "diversification_ratio": ratio,
        "diversification_ratio_formula": "sum(w_i * individual_vol_i) / portfolio_volatility",
        "average_ready_pairwise_correlation": (sum(correlations) / len(correlations)) if correlations else None,
        "ready_pairwise_correlation_count": len(correlations),
        "highest_ready_pair_correlations": [
            {"ticker_i": row["ticker_i"], "ticker_j": row["ticker_j"], "correlation": row["correlation"]} for row in top_pairs
        ],
        "correlation_concentration_group_count": len(cluster_groups),
        "nominal_holding_count": nominal_holding_count,
        "effective_n": effective_n,
        "authority_boundary": {"no_universal_diversification_score": True},
    }


def _leave_one_to_cash_sensitivity(*, view_result: Mapping[str, Any], covariance: np.ndarray | None) -> dict[str, Any]:
    """NAV-scaled-only, per Section 12. Every other position's NAV weight is left unchanged; the
    removed exposure becomes implicit cash. No renormalization, no multi-name optimization."""
    if view_result.get("status") != "AVAILABLE" or covariance is None:
        return {"status": "UNAVAILABLE", "reason": view_result.get("status"), "per_ticker": {}}
    included = view_result["included_tickers"]
    base_weights = np.array([view_result["weights"][ticker] for ticker in included], dtype=float)
    base_volatility = view_result["portfolio_volatility"]
    per_ticker: dict[str, Any] = {}
    for index, ticker in enumerate(included):
        adjusted = base_weights.copy()
        adjusted[index] = 0.0
        variance = _portfolio_variance(weights=adjusted, covariance=covariance)
        if variance is None:
            per_ticker[ticker] = {"status": "NUMERICAL_GUARD_FAILED"}
            continue
        volatility_without = math.sqrt(variance)
        delta = volatility_without - base_volatility
        per_ticker[ticker] = {
            "status": "AVAILABLE",
            "current_portfolio_volatility": base_volatility,
            "volatility_without_position": volatility_without,
            "absolute_delta": delta,
            "relative_delta": (delta / base_volatility) if base_volatility else None,
        }
    return {
        "status": "AVAILABLE", "contract": SENSITIVITY_CONTRACT, "view": NAV_SCALED_EQUITY_RISK, "per_ticker": per_ticker,
        "authority_boundary": {
            "not_a_sell_recommendation": True, "no_renormalization_of_remaining_positions": True,
            "single_name_removal_only_no_combinatorial_optimization": True,
        },
    }


def _coverage_status_for_horizon(*, joint: Mapping[str, Any], named_cohort_count: int, named_cohort_nav_weight: float | None, market_value_by_ticker: Mapping[str, float], effective_nav: float | None) -> dict[str, Any]:
    included = joint.get("included_tickers") or []
    excluded = joint.get("excluded_tickers_and_reason") or []
    if joint.get("status") != "JOINT_MATRIX_READY" or not included:
        status = INSUFFICIENT_RISK_COVERAGE
    elif len(included) >= named_cohort_count:
        status = FULL_PORTFOLIO_RISK_READY
    else:
        status = COVERED_SUBSET_RISK_READY
    included_nav_weight = None
    excluded_nav_weight = None
    if effective_nav:
        included_nav_weight = sum(market_value_by_ticker.get(ticker, 0.0) for ticker in included) / effective_nav
        excluded_tickers = [row["ticker"] for row in excluded]
        excluded_nav_weight = sum(market_value_by_ticker.get(ticker, 0.0) for ticker in excluded_tickers) / effective_nav
    return {
        "status": status, "included_tickers": included, "included_count": len(included),
        "excluded_tickers_and_reason": excluded, "excluded_count": len(excluded),
        "included_nav_weight": included_nav_weight, "excluded_or_unmeasured_nav_weight": excluded_nav_weight,
        "joint_matrix_status": joint.get("status"),
    }


# ── Account-level boundary (Section 6) ──────────────────────────────────────────────────────────

def _account_level_context(*, portfolio_snapshot: Mapping[str, Any], named_cohort: Sequence[str], confirmed: Mapping[str, dict]) -> dict[str, Any]:
    aggregate = portfolio_snapshot.get("investment_accounts_portfolio_context") or {}
    raw_positions = {row.get("ticker"): row for row in portfolio_snapshot.get("positions") or [] if row.get("ticker")}
    qualified_tickers: list[str] = []
    unqualified_tickers: list[str] = []
    for ticker in named_cohort:
        attribution = (raw_positions.get(ticker) or {}).get("account_attribution") or []
        if attribution and all(row.get("attribution_status") == "ATTRIBUTED" for row in attribution):
            qualified_tickers.append(ticker)
        else:
            unqualified_tickers.append(ticker)
    position_qualified = bool(named_cohort) and not unqualified_tickers
    position_risk: dict[str, Any]
    if not position_qualified:
        position_risk = {
            "status": ACCOUNT_LEVEL_POSITION_RISK_NOT_QUALIFIED,
            "unqualified_tickers": sorted(unqualified_tickers),
            "reason": "EXACT_CURRENT_PER_ACCOUNT_QUANTITY_NOT_ESTABLISHED_FOR_AT_LEAST_ONE_NAMED_HOLDING",
        }
    else:
        by_account: dict[str, float] = {}
        for ticker in named_cohort:
            market_value = confirmed[ticker].get("current_market_value")
            if market_value is None:
                continue
            attribution = (raw_positions.get(ticker) or {}).get("account_attribution") or []
            total_quantity = sum(_num(row.get("current_quantity")) or 0.0 for row in attribution)
            if total_quantity <= 0:
                continue
            for row in attribution:
                quantity = _num(row.get("current_quantity")) or 0.0
                by_account[row["account_id"]] = by_account.get(row["account_id"], 0.0) + market_value * (quantity / total_quantity)
        position_risk = {
            "status": "QUALIFIED", "method": "QUANTITY_PROPORTIONAL_MARKET_VALUE_ALLOCATION_PER_ACCOUNT",
            "equity_market_value_by_account": dict(sorted(by_account.items())),
        }
    return {
        "aggregate_status": aggregate.get("status"),
        "account_count": aggregate.get("account_count", 0),
        "totals": aggregate.get("totals"),
        "as_of_consistency": aggregate.get("as_of_consistency"),
        "position_risk_decomposition": position_risk,
        "authority_boundary": {"account_cash_nav_margin_always_allowed_when_aggregate_qualified": True,
                               "account_level_position_risk_requires_exact_qualified_quantities": True},
    }


# ── Top-level artifact ───────────────────────────────────────────────────────────────────────

def build_artifact(
    *, requested_at: str, portfolio_snapshot: Mapping[str, Any], price_history_snapshot: Mapping[str, Any],
    prices: Mapping[str, Any] | None = None, sector_by_ticker: Mapping[str, Any] | None = None,
    governed_sector_snapshot: Mapping[str, Any] | None = None, excluded_tickers: Sequence[str] | None = None,
    event_ledger: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    state = _pad.derive_portfolio_state(
        portfolio_snapshot=portfolio_snapshot, prices=prices, sector_by_ticker=sector_by_ticker,
        governed_sector_snapshot=governed_sector_snapshot, excluded_tickers=excluded_tickers,
    )
    confirmed, named_cohort, excluded_confirmed, unresolved = _partition_positions(state)
    source_coverage = _source_coverage(
        confirmed_count=len(confirmed), unresolved_count=len(unresolved), portfolio_snapshot=portfolio_snapshot, event_ledger=event_ledger,
    )
    if not confirmed:
        body = {
            "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "milestone": MILESTONE,
            "requested_at": requested_at, "portfolio_as_of_date": portfolio_snapshot.get("snapshot_as_of_date"),
            "source_coverage": source_coverage, "status": "INSUFFICIENT_PORTFOLIO_TRUTH",
            "exposure_and_concentration": None, "per_security_volatility": {}, "pairwise_correlations": [],
            "correlation_clusters": {}, "covariance_integrity": {}, "portfolio_volatility": {}, "risk_contribution": {},
            "diversification": {}, "sensitivity_leave_one_to_cash": {}, "account_level_context": None,
            "coverage_by_horizon": {}, "warnings": ["NO_CURRENT_CONFIRMED_POSITIONS"],
            "authority_boundary": _authority_boundary(),
            "source_artifact_identities": {
                "portfolio_snapshot_identity": portfolio_snapshot.get("artifact_identity"),
                "price_history_snapshot_identity": price_history_snapshot.get("snapshot_identity") or price_history_snapshot.get("artifact_identity"),
            },
        }
        return {**body, **content_identity(body)}

    equity_market_value_all_confirmed = sum(row["current_market_value"] for row in confirmed.values() if row.get("current_market_value") is not None)
    equity_market_value_named = sum(confirmed[ticker]["current_market_value"] for ticker in named_cohort if confirmed[ticker].get("current_market_value") is not None)
    excluded_confirmed_market_value = sum(confirmed[ticker]["current_market_value"] for ticker in excluded_confirmed if confirmed[ticker].get("current_market_value") is not None)
    effective_nav = state.get("effective_nav")

    exposure_and_concentration = {
        "nav_basis": state.get("nav_basis"), "effective_nav": effective_nav,
        "investment_accounts_aggregate_status": state.get("investment_accounts_aggregate_status"),
        "equity_market_value_all_confirmed": equity_market_value_all_confirmed,
        "equity_market_value_named_cohort": equity_market_value_named,
        "equity_exposure_to_nav": (equity_market_value_all_confirmed / effective_nav) if effective_nav else None,
        "broker_cash": state.get("cash_available"), "broker_cash_to_nav": (state.get("cash_available") / effective_nav) if (effective_nav and state.get("cash_available") is not None) else None,
        "margin_debt": state.get("margin_debt"), "margin_debt_to_nav": (state.get("margin_debt") / effective_nav) if (effective_nav and state.get("margin_debt") is not None) else None,
        "current_confirmed_holding_count": len(confirmed), "named_research_cohort_count": len(named_cohort),
        "sector_weights": state.get("sector_weights"),
        "single_name_weights": {ticker: confirmed[ticker].get("current_weight") for ticker in named_cohort},
        "excluded_confirmed_exposure": (
            {"count": len(excluded_confirmed), "market_value": excluded_confirmed_market_value,
             "nav_weight": (excluded_confirmed_market_value / effective_nav) if effective_nav else None,
             "status": "OWNER_EXCLUDED_ANONYMIZED_RETAINED_IN_DENOMINATOR"}
            if excluded_confirmed else {"count": 0, "market_value": 0.0, "nav_weight": 0.0, "status": "NONE"}
        ),
        "concentration": _hhi_context(confirmed=confirmed, named_cohort=named_cohort, excluded_confirmed=excluded_confirmed),
    }

    as_of_session = price_history_snapshot.get("resolved_completed_session")
    if not isinstance(as_of_session, str):
        raise PersonalPortfolioQuantRiskError("PRICE_HISTORY_SNAPSHOT_AS_OF_SESSION_MISSING")
    market_value_by_ticker = {ticker: confirmed[ticker]["current_market_value"] for ticker in named_cohort if confirmed[ticker].get("current_market_value") is not None}

    per_security_volatility: dict[str, Any] = {}
    pairwise_correlations: list[dict[str, Any]] = []
    correlation_clusters: dict[str, Any] = {}
    covariance_integrity: dict[str, Any] = {}
    portfolio_volatility: dict[str, Any] = {view: {} for view in PORTFOLIO_VOLATILITY_VIEWS}
    risk_contribution: dict[str, Any] = {view: {} for view in PORTFOLIO_VOLATILITY_VIEWS}
    diversification: dict[str, Any] = {view: {} for view in PORTFOLIO_VOLATILITY_VIEWS}
    sensitivity: dict[str, Any] = {}
    coverage_by_horizon: dict[str, Any] = {}

    if len(named_cohort) >= 1:
        windows, sessions = _build_windows(named_cohort=named_cohort, price_history_snapshot=price_history_snapshot, as_of_session=as_of_session)
        for ticker in named_cohort:
            per_security_volatility[ticker] = {f"L{lookback}": _cprr._volatility_context(windows[ticker][lookback]) for lookback in STANDARD_RISK_LOOKBACKS}
        c1_compatible = _c1_compatible_risk_research(named_cohort=named_cohort, windows=windows, as_of_session=as_of_session, sector_by_ticker=sector_by_ticker)
        pairwise_correlations = c1_compatible["pairwise_relationships"]
        correlation_clusters = _correlation_clusters(c1_compatible=c1_compatible, named_cohort=named_cohort)
        covariance_integrity = c1_compatible["joint_matrix_context"]

        for lookback in STANDARD_RISK_LOOKBACKS:
            key = f"L{lookback}"
            joint = covariance_integrity[key]
            coverage_by_horizon[key] = _coverage_status_for_horizon(
                joint=joint, named_cohort_count=len(named_cohort), named_cohort_nav_weight=None,
                market_value_by_ticker=market_value_by_ticker, effective_nav=effective_nav,
            )
            covariance = np.array(joint["covariance_matrix"], dtype=float) if joint.get("covariance_matrix") is not None else None
            ready_pairs_this_horizon = [row for row in pairwise_correlations if row["lookback_sessions"] == lookback and row["status"] == "PAIRWISE_CORRELATION_READY"]
            group_count_this_horizon = len(correlation_clusters[key].get("concentration_groups") or []) if isinstance(correlation_clusters[key], Mapping) else 0
            for view in PORTFOLIO_VOLATILITY_VIEWS:
                view_result = _portfolio_volatility_view(view=view, lookback=lookback, joint=joint, market_value_by_ticker=market_value_by_ticker, effective_nav=effective_nav)
                portfolio_volatility[view][key] = view_result
                risk_contribution[view][key] = _risk_contribution(view_result=view_result, covariance=covariance)
                diversification[view][key] = _diversification(
                    view_result=view_result, covariance=covariance, pairwise_ready=ready_pairs_this_horizon,
                    cluster_groups=correlation_clusters[key].get("concentration_groups") or [] if isinstance(correlation_clusters[key], Mapping) else [],
                    nominal_holding_count=len(named_cohort), effective_n=exposure_and_concentration["concentration"].get("effective_n"),
                )
            sensitivity[key] = _leave_one_to_cash_sensitivity(view_result=portfolio_volatility[NAV_SCALED_EQUITY_RISK][key], covariance=covariance)

    account_level_context = _account_level_context(portfolio_snapshot=portfolio_snapshot, named_cohort=named_cohort, confirmed=confirmed)

    body = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "milestone": MILESTONE,
        "requested_at": requested_at,
        "portfolio_as_of_date": portfolio_snapshot.get("snapshot_as_of_date"),
        "price_history_as_of_session": as_of_session,
        "price_basis": PRICE_BASIS,
        "return_contract": _cprr.RETURN_CONTRACT,
        "standard_risk_lookbacks": list(STANDARD_RISK_LOOKBACKS),
        "source_coverage": source_coverage,
        "status": "AVAILABLE",
        "unresolved_positions": {"count": len(unresolved), "tickers": unresolved},
        "exposure_and_concentration": exposure_and_concentration,
        "per_security_volatility": per_security_volatility,
        "pairwise_correlations": pairwise_correlations,
        "correlation_clusters": correlation_clusters,
        "covariance_integrity": covariance_integrity,
        "coverage_by_horizon": coverage_by_horizon,
        "portfolio_volatility": portfolio_volatility,
        "risk_contribution": risk_contribution,
        "diversification": diversification,
        "sensitivity_leave_one_to_cash": sensitivity,
        "account_level_context": account_level_context,
        "warnings": [
            "ADJUSTED_RETROSPECTIVE_NOT_RAW_AS_TRADED", "DESCRIPTIVE_RESEARCH_ONLY_NOT_EXECUTION_OR_SIZING_AUTHORITY",
            "CORRELATION_IS_OBSERVED_ASSOCIATION_NOT_CAUSATION",
        ],
        "authority_boundary": _authority_boundary(),
        "source_artifact_identities": {
            "portfolio_snapshot_identity": portfolio_snapshot.get("artifact_identity"),
            "price_history_snapshot_identity": price_history_snapshot.get("snapshot_identity") or price_history_snapshot.get("artifact_identity"),
            "governed_sector_snapshot_identity": (governed_sector_snapshot or {}).get("artifact_identity") if governed_sector_snapshot else None,
            "portfolio_state_source_identities": state.get("source_identities"),
        },
    }
    return {**body, **content_identity(body)}


def _authority_boundary() -> dict[str, Any]:
    return {
        "descriptive_research_only": True,
        "no_buy_sell_decision": True, "no_optimal_portfolio": True, "no_target_weights": True, "no_kelly_sizing": True,
        "no_var_or_cvar_authority": True, "no_probability_based_sizing": True, "no_expected_return_optimization": True,
        "no_efficient_frontier": True, "no_sharpe_based_ranking": True, "no_automatic_capital_rotation": True,
        "no_execution_orders": True, "high_risk_contribution_is_never_a_reduce_or_sell_instruction": True,
        "correlation_threshold_v1_deterministic_research_heuristic_not_statistically_calibrated": True,
        "owner_excluded_ticker_identity_never_surfaced": True,
        "unresolved_position_never_receives_numeric_weight_or_risk_contribution": True,
        "private_local_only_never_producer_git_dashboard_or_public_ai_handoff": True,
    }


# ── Retained-artifact resolution (read-only; no Daily run, no provider call) ──────────────────

def load_price_history_snapshot(repo_root, session: str):
    from pathlib import Path
    nodash = session.replace("-", "")
    path = Path(repo_root) / "operations-review" / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "p3f9b_mva_exact_session_snapshot.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_from_retained_artifacts(*, repo_root, portfolio_root=None, session: str | None = None, requested_at: str) -> dict[str, Any]:
    """One deterministic, read-only evaluation over already-retained artifacts. Raises
    ``FileNotFoundError`` when no private portfolio has been imported or no retained price-history
    snapshot exists for the resolved session -- never fabricates a substitute for either.
    """
    from pathlib import Path
    import owner_research_exclusions as _exclusions
    import private_portfolio_context as _ppc

    repo_root = Path(repo_root)
    status = _ppc.portfolio_status(portfolio_root=portfolio_root)
    if status.get("status") not in ("READY", "RECONCILIATION_INCOMPLETE"):
        raise FileNotFoundError("PRIVATE_PORTFOLIO_NOT_IMPORTED")
    portfolio_snapshot = status["snapshot"]

    resolved_session = session or _pad.default_latest_completed_session(repo_root)
    if not resolved_session:
        raise FileNotFoundError("NO_RETAINED_COMPLETED_INTEGRATED_DECISION_SESSION_AVAILABLE")
    price_history_snapshot = load_price_history_snapshot(repo_root, resolved_session)
    if price_history_snapshot is None:
        raise FileNotFoundError(f"NO_RETAINED_PRICE_HISTORY_SNAPSHOT_FOR_SESSION:{resolved_session}")

    prices = _pad.load_descriptive_prices(repo_root, resolved_session)
    governed_sector_snapshot = _pad.load_governed_sector_snapshot(repo_root)
    sector_by_ticker, _sources, _identity = _pad.resolve_sector_by_ticker(governed_sector_snapshot=governed_sector_snapshot)
    excluded = _exclusions.excluded_ticker_set(_exclusions.load_research_exclusions(portfolio_root))

    directory = (portfolio_root or _ppc.default_portfolio_root()).expanduser().resolve() / str(status["pointer"]["relative_directory"])
    event_ledger = None
    ledger_path = directory / "portfolio_event_ledger_v1.json"
    if ledger_path.is_file():
        event_ledger = json.loads(ledger_path.read_text(encoding="utf-8"))

    return build_artifact(
        requested_at=requested_at, portfolio_snapshot=portfolio_snapshot, price_history_snapshot=price_history_snapshot,
        prices=prices, sector_by_ticker=sector_by_ticker, governed_sector_snapshot=governed_sector_snapshot,
        excluded_tickers=sorted(excluded), event_ledger=event_ledger,
    )


def default_private_output_root():
    import private_portfolio_context as _ppc
    return _ppc.default_portfolio_root() / "personal_portfolio_quant_risk_decomposition"


def write_private_artifact(artifact: Mapping[str, Any], *, portfolio_root=None):
    import os
    root = default_private_output_root() if portfolio_root is None else (portfolio_root.expanduser().resolve() / "personal_portfolio_quant_risk_decomposition")
    destination = root / "personal_portfolio_quant_risk_decomposition_v1.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical(artifact) + "\n"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def public_console_summary(artifact: Mapping[str, Any], *, destination=None) -> dict[str, Any]:
    """Safe CLI surface: counts/status/percentages only, never a ticker or monetary value."""
    exposure = artifact.get("exposure_and_concentration") or {}
    concentration = exposure.get("concentration") or {}
    coverage_by_horizon = artifact.get("coverage_by_horizon") or {}
    return {
        "status": artifact.get("status"),
        "personal_portfolio_quant_risk_decomposition_identity": artifact.get("artifact_identity"),
        "source_coverage_status": (artifact.get("source_coverage") or {}).get("status"),
        "current_confirmed_holding_count": exposure.get("current_confirmed_holding_count"),
        "named_research_cohort_count": exposure.get("named_research_cohort_count"),
        "unresolved_position_count": (artifact.get("unresolved_positions") or {}).get("count"),
        "excluded_confirmed_exposure_count": (exposure.get("excluded_confirmed_exposure") or {}).get("count"),
        "effective_n": concentration.get("effective_n"),
        "account_level_position_risk_status": ((artifact.get("account_level_context") or {}).get("position_risk_decomposition") or {}).get("status"),
        "coverage_by_horizon_status": {horizon: row.get("status") for horizon, row in coverage_by_horizon.items()},
        "risk_contribution_reconciliation_status": {
            view: {horizon: (row.get("reconciliation") or {}).get("status") for horizon, row in (artifact.get("risk_contribution") or {}).get(view, {}).items()}
            for view in PORTFOLIO_VOLATILITY_VIEWS
        },
        "correlation_group_counts": {
            horizon: len((row.get("concentration_groups") or [])) if isinstance(row, Mapping) else None
            for horizon, row in (artifact.get("correlation_clusters") or {}).items()
        },
        "leave_one_to_cash_qualified_count": {
            horizon: sum(1 for row in (sens.get("per_ticker") or {}).values() if row.get("status") == "AVAILABLE")
            for horizon, sens in (artifact.get("sensitivity_leave_one_to_cash") or {}).items()
        },
        "written_to": str(destination) if destination is not None else None,
    }
