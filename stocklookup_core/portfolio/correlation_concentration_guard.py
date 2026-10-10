"""Deterministic research-only concentration context over frozen C1 outputs.

This is deliberately not a return, covariance, optimization, allocation, or
recommendation engine.  It consumes the retained C1 pairwise correlations
verbatim for an explicit finite security set and surfaces a small, explainable
connected-component view of correlations strictly above the frozen V1
research heuristic.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
from itertools import combinations
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "correlation_concentration_guard/v1"
C1_CONTRACT_VERSION = "current_portfolio_risk_research/v1"
SUPPORTED_LOOKBACKS = (20, 60, 120, 250)
MATERIAL_CORRELATION_THRESHOLD = 0.80
THRESHOLD_RULE = "STRICTLY_GREATER_THAN"


class CorrelationConcentrationGuardError(ValueError):
    """Raised when the bounded C1 input contract cannot be used safely."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"correlation_concentration_guard:{digest}"}


def _security_set(securities: Sequence[str]) -> list[str]:
    if isinstance(securities, str) or not isinstance(securities, Sequence):
        raise CorrelationConcentrationGuardError("SECURITY_SET_INVALID")
    if any(not isinstance(ticker, str) or not ticker for ticker in securities):
        raise CorrelationConcentrationGuardError("SECURITY_IDENTITY_INVALID")
    if len(set(securities)) != len(securities):
        raise CorrelationConcentrationGuardError("DUPLICATE_SECURITY_IDENTITY_INPUT")
    return sorted(securities)


def _validate_risk_artifact(risk_research: Mapping[str, Any]) -> None:
    if not isinstance(risk_research, Mapping) or risk_research.get("contract_version") != C1_CONTRACT_VERSION:
        raise CorrelationConcentrationGuardError("RISK_ARTIFACT_CONTRACT_INVALID")
    if not isinstance(risk_research.get("pairwise_relationships"), Sequence):
        raise CorrelationConcentrationGuardError("C1_PAIRWISE_MATERIAL_MISSING")
    if not isinstance(risk_research.get("ticker_risk_context"), Mapping):
        raise CorrelationConcentrationGuardError("C1_TICKER_CONTEXT_MISSING")


def _pair_key(first: Any, second: Any) -> tuple[str, str] | None:
    if not isinstance(first, str) or not isinstance(second, str) or not first or not second or first == second:
        return None
    return tuple(sorted((first, second)))


def _row_signature(row: Mapping[str, Any]) -> str:
    # Deliberately do not canonical-JSON raw C1 values here: malformed NaN is
    # itself evidence to classify fail-closed below, rather than an encoder error.
    return repr((row.get("status"), row.get("correlation"), row.get("return_observations"), row.get("lookback_sessions")))


def _pair_index(risk_research: Mapping[str, Any], lookback: int) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    indexed: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in risk_research["pairwise_relationships"]:
        if not isinstance(row, Mapping) or row.get("lookback_sessions") != lookback:
            continue
        key = _pair_key(row.get("ticker_i"), row.get("ticker_j"))
        if key is not None:
            indexed[key].append(row)
    return indexed


def _pair_context(*, first: str, second: str, lookback: int, known: set[str], index: Mapping[tuple[str, str], list[Mapping[str, Any]]],
                  lineage: Mapping[str, Any]) -> dict[str, Any]:
    key = (first, second)
    base = {
        "ticker_i": first, "ticker_j": second, "lookback_sessions": lookback,
        "correlation": None, "return_observations": None,
        "source_lineage": {"risk_artifact_identity": lineage.get("risk_artifact_identity"),
                           "source_contract_version": C1_CONTRACT_VERSION,
                           "source_surface": "C1_PAIRWISE_RELATIONSHIP"},
        "warnings": [],
    }
    if first not in known or second not in known:
        return {**base, "status": "UNKNOWN_SECURITY_IDENTITY", "warnings": ["SECURITY_NOT_IN_C1_RISK_COHORT"]}
    rows = index.get(key, [])
    if not rows:
        return {**base, "status": "C1_PAIRWISE_MATERIAL_MISSING", "warnings": ["PAIRWISE_CONTEXT_UNAVAILABLE"]}
    if len({_row_signature(row) for row in rows}) != 1:
        return {**base, "status": "PAIRWISE_EVIDENCE_CONFLICT", "warnings": ["DUPLICATED_PAIRWISE_EVIDENCE_CONFLICT"]}
    row = rows[0]
    status, correlation = row.get("status"), row.get("correlation")
    samples = row.get("return_observations")
    if status == "PAIRWISE_CORRELATION_READY":
        if (not isinstance(correlation, (int, float)) or isinstance(correlation, bool) or
                not math.isfinite(float(correlation)) or abs(float(correlation)) > 1.0 or
                not isinstance(samples, int) or samples <= 0):
            return {**base, "status": "PAIRWISE_INPUT_INVALID", "warnings": ["C1_READY_PAIRWISE_VALUE_INVALID"]}
        return {**base, "status": "PAIRWISE_CORRELATION_READY", "correlation": float(correlation),
                "return_observations": samples, "warnings": sorted(set(row.get("warnings") or []))}
    return {**base, "status": "PAIRWISE_INSUFFICIENT_OR_PARTIAL", "source_pairwise_status": status,
            "return_observations": samples if isinstance(samples, int) else None,
            "warnings": sorted(set((row.get("warnings") or []) + ["C1_PAIRWISE_NOT_READY"]))}


def _components(pairs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    edges: dict[tuple[str, str], Mapping[str, Any]] = {}
    for pair in pairs:
        if pair["status"] == "PAIRWISE_CORRELATION_READY" and pair["correlation"] > MATERIAL_CORRELATION_THRESHOLD:
            first, second = pair["ticker_i"], pair["ticker_j"]
            adjacency[first].add(second)
            adjacency[second].add(first)
            edges[(first, second)] = pair
    groups: list[dict[str, Any]] = []
    unvisited = set(adjacency)
    while unvisited:
        start = min(unvisited)
        stack, component = [start], set()
        while stack:
            ticker = stack.pop()
            if ticker in component:
                continue
            component.add(ticker)
            stack.extend(sorted(adjacency[ticker] - component, reverse=True))
        unvisited -= component
        tickers = sorted(component)
        component_edges = [deepcopy(edges[key]) for key in sorted(edges) if key[0] in component and key[1] in component]
        groups.append({
            "group_id": f"CORRELATION_COMPONENT_{len(groups) + 1:03d}", "tickers": tickers,
            "security_count": len(tickers),
            "group_status": "CONCENTRATED_CORRELATED_GROUP" if len(tickers) >= 3 else "CORRELATED_PAIR_CONTEXT",
            "edge_count": len(component_edges), "triggered_edges": component_edges,
            "method": "CONNECTED_COMPONENTS_ON_READY_PAIRS_ABOVE_STRICT_THRESHOLD",
        })
    return groups


def _recommendation_context(recommendations: Mapping[str, Any] | None, securities: Sequence[str]) -> dict[str, Any]:
    records = (recommendations or {}).get("records") if isinstance(recommendations, Mapping) else None
    context = {}
    for ticker in securities:
        record = records.get(ticker) if isinstance(records, Mapping) else None
        recommendation = record.get("recommendation") if isinstance(record, Mapping) else None
        context[ticker] = (
            {"status": "UPSTREAM_RECOMMENDATION_PASSTHROUGH", "recommendation_label": recommendation.get("recommendation_label"),
             "recommendation_readiness": recommendation.get("recommendation_readiness")}
            if isinstance(recommendation, Mapping) else {"status": "UPSTREAM_RECOMMENDATION_CONTEXT_ABSENT"}
        )
    return context


def build_artifact(*, risk_research: Mapping[str, Any], securities: Sequence[str], lookback: int,
                   shadow_recommendations: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Create one immutable research context using C1 pairwise material verbatim.

    ``lookback`` is intentionally required.  The caller must make the frozen
    C1 horizon selection explicit; C2 has no hidden presentation default.
    """
    _validate_risk_artifact(risk_research)
    if lookback not in SUPPORTED_LOOKBACKS:
        raise CorrelationConcentrationGuardError("LOOKBACK_OUTSIDE_FROZEN_C1_CONTRACT")
    selected = _security_set(securities)
    known = set(risk_research["ticker_risk_context"])
    lineage = {"risk_artifact_identity": risk_research.get("artifact_identity"),
               "risk_artifact_sha256": risk_research.get("artifact_sha256"),
               "shadow_recommendation_artifact_identity": None if shadow_recommendations is None else shadow_recommendations.get("artifact_identity")}
    pair_rows = [_pair_context(first=first, second=second, lookback=lookback, known=known,
                               index=_pair_index(risk_research, lookback), lineage=lineage)
                 for first, second in combinations(selected, 2)]
    ready_pairs = [row for row in pair_rows if row["status"] == "PAIRWISE_CORRELATION_READY"]
    unavailable_pairs = [row for row in pair_rows if row["status"] != "PAIRWISE_CORRELATION_READY"]
    groups = _components(pair_rows)
    joint = deepcopy(((risk_research.get("joint_matrix_context") or {}).get(f"L{lookback}")))
    joint_status = joint.get("status") if isinstance(joint, Mapping) else "C1_JOINT_MATRIX_CONTEXT_MISSING"
    reasons: list[str] = []
    if len(selected) < 2:
        guard_status = "INPUT_COHORT_TOO_SMALL_FOR_CONCENTRATION_ANALYSIS"
        reasons.append("AT_LEAST_TWO_SECURITIES_REQUIRED")
    elif not ready_pairs:
        guard_status = "INSUFFICIENT_PAIRWISE_EVIDENCE"
        reasons.append("NO_READY_PAIRWISE_CORRELATION")
    elif unavailable_pairs:
        guard_status = "PARTIAL_PAIRWISE_VIEW"
        reasons.append("MIXED_PAIRWISE_READINESS")
    elif any(group["security_count"] >= 3 for group in groups):
        guard_status = "CONCENTRATED_CORRELATED_GROUP"
    elif groups:
        guard_status = "CORRELATED_PAIR_CONTEXT"
    else:
        guard_status = "NO_MATERIAL_CORRELATION_CONCENTRATION"
    if ready_pairs and joint_status != "JOINT_MATRIX_READY":
        reasons.append("JOINT_MATRIX_UNAVAILABLE_PAIRWISE_CONTEXT_USABLE")
    recommendation_context = _recommendation_context(shadow_recommendations, selected)
    warnings = sorted(set(reasons))
    pair_status_counts = dict(sorted(Counter(row["status"] for row in pair_rows).items()))
    artifact: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION,
        "metadata": {"as_of_session": (risk_research.get("metadata") or {}).get("as_of_session"),
                     "selected_lookback_sessions": lookback,
                     "threshold_contract": {"metric": "PEARSON_CORRELATION_FROM_C1", "threshold": MATERIAL_CORRELATION_THRESHOLD,
                                            "comparison": THRESHOLD_RULE,
                                            "status": "V1_DETERMINISTIC_RESEARCH_HEURISTIC_NOT_STATISTICALLY_CALIBRATED"},
                     "method": "CONNECTED_COMPONENTS_ON_READY_PAIRS_ONLY"},
        "input_lineage": lineage,
        "input_cohort": {"security_identifiers": selected, "security_count": len(selected),
                          "known_c1_security_count": sum(ticker in known for ticker in selected),
                          "unknown_security_identifiers": [ticker for ticker in selected if ticker not in known],
                          "presence_means_concentration_diagnostics_only": True},
        "pairwise_correlation_context": pair_rows,
        "concentration_groups": groups,
        "guard_context": {"status": guard_status, "reason_codes": warnings,
                          "joint_matrix_source_context": joint,
                          "joint_matrix_status": joint_status,
                          "pairwise_context_is_independent_of_joint_matrix_readiness": True},
        "upstream_recommendation_context": recommendation_context,
        "validation": {"pair_count": len(pair_rows), "pairwise_ready_count": len(ready_pairs),
                       "pairwise_insufficient_or_unavailable_count": len(unavailable_pairs), "pairwise_status_counts": pair_status_counts,
                       "triggered_edge_count": sum(group["edge_count"] for group in groups),
                       "triggered_group_count": len(groups), "concentrated_group_count": sum(group["security_count"] >= 3 for group in groups),
                       "recommendation_mutation_count": 0,
                       "forbidden_output_audit": {"buy_sell_hold": 0, "target_price": 0, "probability": 0,
                                                  "position_size": 0, "portfolio_weight": 0, "risk_budget": 0,
                                                  "recommended_allocation": 0, "order_size": 0, "execution_signal": 0}},
        "authority_boundaries": {"research_context_only": True, "recommendation_label_mutation": "NOT_PERMITTED",
                                 "recommendation_readiness_mutation": "NOT_PERMITTED", "portfolio_weights": "NOT_EMITTED",
                                 "position_sizing": "NOT_EMITTED", "risk_budget": "NOT_EMITTED", "allocation": "NOT_EMITTED",
                                 "execution": "NOT_EMITTED", "raw_as_traded": "NOT_PROMOTED",
                                 "historical_price_pit": "BLOCKED", "historical_backtest": "BLOCKED",
                                 "same_close_execution": "NOT_ESTABLISHED"},
        "warnings": ["C1_ADJUSTED_RETROSPECTIVE_CURRENT_RESEARCH_CONTEXT", "CORRELATION_IS_OBSERVED_ASSOCIATION_NOT_CAUSATION"] + warnings,
    }
    return {**artifact, **content_identity(artifact)}
