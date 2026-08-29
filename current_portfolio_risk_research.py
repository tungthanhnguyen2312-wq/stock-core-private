"""Deterministic current candidate-set risk context; never allocates capital.

This module consumes retained DNSE completed-session observations only.  It is
deliberately separate from ``current_portfolio_risk_envelope``: that contract
requires explicit holdings, while this contract describes the READY_SHADOW
candidate set and cannot infer holdings, weights, or a portfolio.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from itertools import combinations
from typing import Any, Mapping, Sequence

import numpy as np


CONTRACT_VERSION = "current_portfolio_risk_research/v1"
STANDARD_RISK_LOOKBACKS = (20, 60, 120, 250)
ANNUALIZATION_SESSIONS = 250
PRICE_BASIS = "ADJUSTED_RETROSPECTIVE"
RETURN_CONTRACT = "SIMPLE_CLOSE_TO_CLOSE_RETURN_V1"
JOINT_MATRIX_GUARD = "JOINT_MATRIX_RESEARCH_GUARD_V1"
SYMMETRY_TOLERANCE = 1e-10


class CurrentPortfolioRiskResearchError(ValueError):
    """Raised where a retained-input contract cannot be interpreted safely."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"current_portfolio_risk_research:{digest}"}


def simple_close_to_close_returns(closes: Sequence[float]) -> np.ndarray:
    """Return exactly ``close_t / close_(t-1) - 1``; no filling or splicing."""
    values = np.asarray(closes, dtype=float)
    if len(values) < 2 or not np.all(np.isfinite(values)) or np.any(values <= 0):
        raise CurrentPortfolioRiskResearchError("NONFINITE_OR_NONPOSITIVE_CLOSE")
    return values[1:] / values[:-1] - 1.0


def _basis_is_compatible(value: Any) -> bool:
    return isinstance(value, str) and "ADJUSTED_RETROSPECTIVE" in value


def _session_calendar(snapshot: Mapping[str, Any], as_of_session: str) -> list[str]:
    sessions = set()
    for record in (snapshot.get("records") or {}).values():
        for row in record.get("observations") or []:
            session = row.get("session")
            if isinstance(session, str) and session <= as_of_session:
                sessions.add(session)
    ordered = sorted(sessions)
    if not ordered or ordered[-1] != as_of_session:
        raise CurrentPortfolioRiskResearchError("GOVERNED_SESSION_SEQUENCE_DOES_NOT_END_AT_AS_OF")
    return ordered


def _price_index(snapshot_record: Mapping[str, Any], *, as_of_session: str) -> tuple[dict[str, float], list[str], list[str]]:
    """Return valid closes plus duplicate/basis-input local error dispositions."""
    closes: dict[str, float] = {}
    duplicate_sessions: list[str] = []
    problems: list[str] = []
    seen_sessions: set[str] = set()
    for row in snapshot_record.get("observations") or []:
        session, close = row.get("session"), row.get("close")
        if not isinstance(session, str):
            problems.append("SESSION_INVALID")
            continue
        if session > as_of_session:
            problems.append("NO_FUTURE_SESSION_AFTER_AS_OF")
            continue
        if session in seen_sessions:
            duplicate_sessions.append(session)
            continue
        seen_sessions.add(session)
        if not _basis_is_compatible(row.get("price_basis")):
            problems.append("PRICE_BASIS_CONFLICT")
            continue
        if not isinstance(close, (int, float)) or not math.isfinite(float(close)) or float(close) <= 0:
            problems.append("NONFINITE_INPUT")
            continue
        closes[session] = float(close)
    return closes, sorted(set(duplicate_sessions)), sorted(set(problems))


def _window_for(
    *, ticker: str, lookback: int, sessions: Sequence[str], close_index: Mapping[str, float],
    duplicate_sessions: Sequence[str], input_problems: Sequence[str],
) -> dict[str, Any]:
    if len(sessions) < lookback:
        return {
            "status": "SESSION_WINDOW_UNRESOLVED", "required_sessions": [], "observed_sessions": [],
            "missing_sessions": [], "missing_session_count": None, "returns": None,
            "warnings": ["GOVERNED_SESSION_SEQUENCE_SHORTER_THAN_LOOKBACK"],
        }
    required = list(sessions[-lookback:])
    observed = [session for session in required if session in close_index]
    missing = [session for session in required if session not in close_index]
    duplicate = sorted(set(required).intersection(duplicate_sessions))
    warnings = list(input_problems)
    if duplicate:
        warnings.append("DUPLICATE_SESSION_WITHOUT_DETERMINISTIC_RESOLUTION")
    if input_problems or duplicate:
        status = "PRICE_BASIS_CONFLICT" if "PRICE_BASIS_CONFLICT" in input_problems else "NONFINITE_INPUT"
        return {
            "status": status, "required_sessions": required, "observed_sessions": observed,
            "missing_sessions": missing, "missing_session_count": len(missing), "returns": None,
            "warnings": sorted(set(warnings)),
        }
    if missing:
        return {
            "status": "UNAVAILABLE_FULL_WINDOW", "required_sessions": required, "observed_sessions": observed,
            "missing_sessions": missing, "missing_session_count": len(missing), "returns": None,
            "warnings": [],
        }
    try:
        returns = simple_close_to_close_returns([close_index[session] for session in required])
    except CurrentPortfolioRiskResearchError:
        return {
            "status": "NONFINITE_INPUT", "required_sessions": required, "observed_sessions": observed,
            "missing_sessions": [], "missing_session_count": 0, "returns": None,
            "warnings": ["NONFINITE_OR_NONPOSITIVE_CLOSE"],
        }
    return {
        "status": "WINDOW_READY", "required_sessions": required, "observed_sessions": observed,
        "missing_sessions": [], "missing_session_count": 0, "returns": returns, "warnings": [],
    }


def _volatility_context(window: Mapping[str, Any]) -> dict[str, Any]:
    ready = window["status"] == "WINDOW_READY"
    raw = None
    annualized = None
    if ready:
        returns = window["returns"]
        raw = float(np.std(returns, ddof=1))
        annualized = float(raw * math.sqrt(ANNUALIZATION_SESSIONS))
    return {
        "status": "VOLATILITY_READY" if ready else window["status"],
        "required_price_sessions": len(window["required_sessions"]),
        "observed_price_sessions": len(window["observed_sessions"]),
        "return_observations": len(window["required_sessions"]) - 1 if ready else None,
        "raw_daily_volatility": raw,
        "annualized_research_volatility": annualized,
        "annualization_convention": "RESEARCH_ANNUALIZATION_CONVENTION_V1" if ready else None,
        "missing_sessions": window["missing_sessions"],
        "warnings": window["warnings"],
    }


def _sector_value(sector_context: Mapping[str, Any] | None, ticker: str) -> str | None:
    record = ((sector_context or {}).get("ticker_contexts") or {}).get(ticker) or {}
    return ((record.get("sector_leadership_context") or {}).get("group_key"))


def _pairwise(
    *, ticker_i: str, ticker_j: str, lookback: int, as_of_session: str,
    first: Mapping[str, Any], second: Mapping[str, Any], same_sector: bool | None,
) -> dict[str, Any]:
    if first["status"] != "WINDOW_READY" or second["status"] != "WINDOW_READY":
        return {
            "ticker_i": ticker_i, "ticker_j": ticker_j, "lookback_sessions": lookback,
            "return_observations": None, "as_of_session": as_of_session, "price_basis": PRICE_BASIS,
            "correlation": None, "same_sector": same_sector, "status": "PAIRWISE_PARTIAL_OVERLAP",
            "warnings": sorted(set(first["warnings"] + second["warnings"])),
        }
    left, right = first["returns"], second["returns"]
    correlation = float(np.corrcoef(left, right)[0, 1])
    if not math.isfinite(correlation):
        return {
            "ticker_i": ticker_i, "ticker_j": ticker_j, "lookback_sessions": lookback,
            "return_observations": lookback - 1, "as_of_session": as_of_session, "price_basis": PRICE_BASIS,
            "correlation": None, "same_sector": same_sector, "status": "PAIRWISE_INPUT_UNAVAILABLE",
            "warnings": ["NONFINITE_PEARSON_CORRELATION"],
        }
    return {
        "ticker_i": ticker_i, "ticker_j": ticker_j, "lookback_sessions": lookback,
        "return_observations": lookback - 1, "as_of_session": as_of_session, "price_basis": PRICE_BASIS,
        "correlation": correlation, "same_sector": same_sector, "status": "PAIRWISE_CORRELATION_READY", "warnings": [],
    }


def _joint_context(*, lookback: int, windows: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    included = sorted(ticker for ticker, window in windows.items() if window["status"] == "WINDOW_READY")
    excluded = [
        {"ticker": ticker, "reason": windows[ticker]["status"]}
        for ticker in sorted(windows) if ticker not in included
    ]
    count, observations = len(included), lookback - 1
    base = {
        "lookback_sessions": lookback, "included_tickers": included, "excluded_tickers_and_reason": excluded,
        "N": count, "T": observations, "T_minus_N": observations - count,
        "T_ge_N_plus_5": observations >= count + 5, "covariance_rank": None,
        "minimum_covariance_eigenvalue": None, "condition_number": None,
        "covariance_symmetry_pass": None, "correlation_symmetry_pass": None,
        "correlation_diagonal_pass": None, "warnings": [], "covariance_matrix": None, "correlation_matrix": None,
    }
    if not included:
        return {**base, "status": "JOINT_MATRIX_NO_COMPLETE_TICKERS", "warnings": ["COMPLETE_INTERSECTION_EMPTY"]}
    if observations < count + 5:
        return {**base, "status": "JOINT_MATRIX_BLOCKED_T_RELATIVE_TO_N", "warnings": [JOINT_MATRIX_GUARD]}
    values = np.column_stack([windows[ticker]["returns"] for ticker in included])
    if not np.all(np.isfinite(values)):
        return {**base, "status": "JOINT_MATRIX_NONFINITE_INPUT", "warnings": ["NONFINITE_RETURN_INPUT"]}
    covariance = np.atleast_2d(np.cov(values, rowvar=False, ddof=1))
    correlation = np.atleast_2d(np.corrcoef(values, rowvar=False))
    finite = bool(np.all(np.isfinite(covariance)) and np.all(np.isfinite(correlation)))
    cov_symmetric = bool(np.allclose(covariance, covariance.T, rtol=0.0, atol=SYMMETRY_TOLERANCE))
    corr_symmetric = bool(np.allclose(correlation, correlation.T, rtol=0.0, atol=SYMMETRY_TOLERANCE))
    diagonal = bool(np.allclose(np.diag(correlation), np.ones(count), rtol=0.0, atol=SYMMETRY_TOLERANCE))
    rank = int(np.linalg.matrix_rank(covariance)) if finite else None
    eigenvalue = float(np.min(np.linalg.eigvalsh(covariance))) if finite and cov_symmetric else None
    condition = float(np.linalg.cond(covariance)) if finite else None
    diagnostics = {
        **base, "covariance_rank": rank, "minimum_covariance_eigenvalue": eigenvalue,
        "condition_number": condition, "covariance_symmetry_pass": cov_symmetric,
        "correlation_symmetry_pass": corr_symmetric, "correlation_diagonal_pass": diagonal,
    }
    ready = finite and cov_symmetric and corr_symmetric and diagonal and rank == count and math.isfinite(condition)
    if not ready:
        return {**diagnostics, "status": "JOINT_MATRIX_NUMERICAL_GUARD_FAILED", "warnings": [JOINT_MATRIX_GUARD]}
    return {
        **diagnostics, "status": "JOINT_MATRIX_READY",
        "covariance_matrix": [[float(value) for value in row] for row in covariance],
        "correlation_matrix": [[float(value) for value in row] for row in correlation],
    }


def build_artifact(
    *, shadow_readiness: Mapping[str, Any], research_cases: Mapping[str, Any], price_snapshot: Mapping[str, Any],
    sector_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an optional current-risk attachment from retained, compatible inputs."""
    snapshot_session = price_snapshot.get("resolved_completed_session")
    if not isinstance(snapshot_session, str):
        raise CurrentPortfolioRiskResearchError("PRICE_SNAPSHOT_AS_OF_SESSION_MISSING")
    cases = research_cases.get("records") or {}
    shadows = shadow_readiness.get("records") or {}
    cohort = sorted(ticker for ticker, record in shadows.items() if record.get("action_readiness_gate") == "READY_SHADOW")
    if not cohort or any(ticker not in cases for ticker in cohort):
        raise CurrentPortfolioRiskResearchError("READY_SHADOW_COHORT_OR_CASE_CONTEXT_INVALID")
    if any(cases[ticker].get("as_of_session") != snapshot_session for ticker in cohort):
        raise CurrentPortfolioRiskResearchError("COHORT_AND_PRICE_SNAPSHOT_AS_OF_MISMATCH")
    sessions = _session_calendar(price_snapshot, snapshot_session)
    price_records = price_snapshot.get("records") or {}
    windows: dict[str, dict[int, dict[str, Any]]] = {}
    ticker_records: dict[str, Any] = {}
    sector_rows: list[dict[str, Any]] = []
    for ticker in cohort:
        shadow, case = shadows[ticker], cases[ticker]
        closes, duplicate_sessions, input_problems = _price_index(price_records.get(ticker) or {}, as_of_session=snapshot_session)
        per_ticker = {
            lookback: _window_for(ticker=ticker, lookback=lookback, sessions=sessions, close_index=closes,
                                  duplicate_sessions=duplicate_sessions, input_problems=input_problems)
            for lookback in STANDARD_RISK_LOOKBACKS
        }
        windows[ticker] = per_ticker
        sector = _sector_value(sector_context, ticker)
        entity = case.get("entity_class")
        sector_rows.append({"ticker": ticker, "sector": sector, "entity_class": entity,
                            "sector_known": sector is not None, "entity_class_known": entity is not None})
        ticker_records[ticker] = {
            "ticker": ticker, "shadow_posture": shadow.get("shadow_posture"),
            "action_readiness_gate": shadow.get("action_readiness_gate"), "as_of_session": snapshot_session,
            "price_source": "RETAINED_DNSE_P3F9B_EXACT_SESSION_SNAPSHOT", "price_basis": PRICE_BASIS,
            "sector": sector, "entity_class": entity,
            "volatility_context": {f"L{lookback}": _volatility_context(per_ticker[lookback]) for lookback in STANDARD_RISK_LOOKBACKS},
        }
    pairwise: list[dict[str, Any]] = []
    for lookback in STANDARD_RISK_LOOKBACKS:
        for ticker_i, ticker_j in combinations(cohort, 2):
            first, second = ticker_records[ticker_i]["sector"], ticker_records[ticker_j]["sector"]
            same_sector = None if first is None or second is None else first == second
            pairwise.append(_pairwise(ticker_i=ticker_i, ticker_j=ticker_j, lookback=lookback, as_of_session=snapshot_session,
                                      first=windows[ticker_i][lookback], second=windows[ticker_j][lookback], same_sector=same_sector))
    joints = {f"L{lookback}": _joint_context(lookback=lookback, windows={ticker: windows[ticker][lookback] for ticker in cohort})
              for lookback in STANDARD_RISK_LOOKBACKS}
    pair_counts = {
        f"L{lookback}": dict(sorted(Counter(row["status"] for row in pairwise if row["lookback_sessions"] == lookback).items()))
        for lookback in STANDARD_RISK_LOOKBACKS
    }
    expected_pairs = len(cohort) * (len(cohort) - 1) // 2
    for lookback in STANDARD_RISK_LOOKBACKS:
        if sum(pair_counts[f"L{lookback}"].values()) != expected_pairs:
            raise CurrentPortfolioRiskResearchError("PAIRWISE_ACCOUNTING_RECONCILIATION_FAILED")
    sector_known = sum(row["sector_known"] for row in sector_rows)
    entity_known = sum(row["entity_class_known"] for row in sector_rows)
    initiate_count = sum(ticker_records[ticker]["shadow_posture"] == "INITIATE_CANDIDATE" for ticker in cohort)
    accumulate_count = sum(ticker_records[ticker]["shadow_posture"] == "ACCUMULATE_CANDIDATE" for ticker in cohort)
    artifact: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION,
        "metadata": {
            "as_of_session": snapshot_session, "price_source": "DNSE", "price_basis": PRICE_BASIS,
            "return_contract": RETURN_CONTRACT, "return_formula": "close_t / close_(t-1) - 1",
            "standard_risk_lookbacks": list(STANDARD_RISK_LOOKBACKS), "lookback_semantics": "EXACT_COMPLETED_CLOSING_PRICE_SESSIONS",
            "return_observations": {f"L{lookback}": lookback - 1 for lookback in STANDARD_RISK_LOOKBACKS},
            "annualization_sessions": ANNUALIZATION_SESSIONS, "annualization_convention": "RESEARCH_ANNUALIZATION_CONVENTION_V1",
            "session_calendar_contract": "RETAINED_DNSE_GOVERNED_COMPLETED_SESSION_SEQUENCE_V1",
            "session_calendar": sessions,
            "input_artifact_identities": {
                "shadow_readiness": shadow_readiness.get("artifact_identity"), "research_cases": research_cases.get("artifact_identity"),
                "price_snapshot": price_snapshot.get("snapshot_identity") or price_snapshot.get("artifact_identity"),
                "sector_context": None if sector_context is None else sector_context.get("artifact_identity"),
            },
        },
        "cohort_summary": {
            "primary_cohort_definition": "READY_SHADOW", "primary_cohort_count": len(cohort), "tickers": cohort,
            "initiate_candidate_count": initiate_count, "accumulate_candidate_count": accumulate_count,
            "pre_c1_shadow_posture": {ticker: shadows[ticker].get("shadow_posture") for ticker in cohort},
            "post_c1_shadow_posture": {ticker: ticker_records[ticker]["shadow_posture"] for ticker in cohort},
        },
        "ticker_risk_context": ticker_records,
        "pairwise_relationships": pairwise,
        "joint_matrix_context": joints,
        "sector_context": {
            "context_name": "CANDIDATE_SET_SECTOR_CONTEXT", "records": sector_rows,
            "candidate_count_by_sector": dict(sorted(Counter(row["sector"] for row in sector_rows if row["sector"] is not None).items())),
            "unknown_sector_count": len(sector_rows) - sector_known,
            "candidate_count_by_entity_class": dict(sorted(Counter(row["entity_class"] for row in sector_rows if row["entity_class"] is not None).items())),
            "unknown_entity_class_count": len(sector_rows) - entity_known,
        },
        "validation": {
            "exact_ready_ticker_counts": {f"L{lookback}": sum(windows[ticker][lookback]["status"] == "WINDOW_READY" for ticker in cohort) for lookback in STANDARD_RISK_LOOKBACKS},
            "volatility_ready_counts": {f"L{lookback}": sum(ticker_records[ticker]["volatility_context"][f"L{lookback}"]["status"] == "VOLATILITY_READY" for ticker in cohort) for lookback in STANDARD_RISK_LOOKBACKS},
            "pairwise_total_pair_count": expected_pairs, "pairwise_status_counts": pair_counts,
            "pairwise_accounting_reconciled": True, "sector_known_count": sector_known, "sector_unknown_count": len(sector_rows) - sector_known,
            "entity_class_known_count": entity_known, "no_future_session_after_as_of": all(session <= snapshot_session for session in sessions),
            "shadow_posture_unchanged": all(shadows[ticker].get("shadow_posture") == ticker_records[ticker]["shadow_posture"] for ticker in cohort),
        },
        "authority_boundaries": {
            "research_context_only": True, "raw_as_traded": "NOT_PROMOTED", "historical_price_pit": "BLOCKED",
            "historical_backtest_authority": "BLOCKED", "execution_price_authority": "BLOCKED",
            "portfolio_weights": "NOT_EMITTED", "risk_budget": "NOT_EMITTED", "position_sizing": "NOT_EMITTED",
            "portfolio_volatility": "NOT_EMITTED", "recommendation_output": "NOT_EMITTED",
            "matrix_repair": "NOT_USED", "shadow_posture_mutation": "NOT_USED",
        },
        "warnings": ["ADJUSTED_RETROSPECTIVE_NOT_RAW_AS_TRADED", "CURRENT_RESEARCH_CONTEXT_NOT_HISTORICAL_PIT_OR_BACKTEST_AUTHORITY"],
    }
    return {**artifact, **content_identity(artifact)}
