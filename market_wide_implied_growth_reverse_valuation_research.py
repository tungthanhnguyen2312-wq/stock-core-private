"""Fail-closed current-research reverse valuation over existing valuation outputs.

This module does not create a valuation model.  It only (a) solves the terminal
growth variable in the existing FCFF perpetuity formulation when every other
input is explicitly supplied by an upstream intrinsic record, and (b) compares
an existing intrinsic per-share result with an upstream current price.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from typing import Any, Mapping


CONTRACT_VERSION = "market_wide_implied_growth_reverse_valuation_research/v1"
RESEARCH_TIER = "CURRENT_RESEARCH_ONLY"
SOLVER_TOLERANCE = 1e-10
SOLVER_MAX_ITERATIONS = 128


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _identity(payload: Mapping[str, Any]) -> dict[str, str]:
    body = {key: value for key, value in payload.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"market_wide_implied_growth_reverse_valuation_research:{digest}"}


def _method(name: str, state: str, *, reason_codes: list[str] | None = None, **fields: Any) -> dict[str, Any]:
    result = {
        "method": name,
        "formula_version": CONTRACT_VERSION,
        "state": state,
        "applicability": "CURRENT_RESEARCH_ONLY",
        "research_tier": RESEARCH_TIER,
        "is_actionable": False,
        "current_price": None,
        "valuation_input_identity": None,
        "used_inputs": {},
        "solved_parameter": None,
        "solved_value": None,
        "bounds": None,
        "convergence": None,
        "iteration_count": None,
        "residual": None,
        "intrinsic_value_per_share": None,
        "absolute_gap": None,
        "relative_gap": None,
        "missing_inputs": [],
        "reason_codes": reason_codes or [],
        "warnings": [],
        "interpretation_limits": [
            "CURRENT_RESEARCH_ONLY",
            "NO_TARGET_PRICE_RECOMMENDATION_SIZING_OR_PROBABILITY",
            "NOT_PIT_OR_RAW_AS_TRADED_AUTHORITY",
        ],
    }
    result.update(fields)
    return result


def solve_fcff_terminal_growth(*, forecast_fcff: float, discount_rate: float,
                               market_enterprise_value: float, lower_bound: float,
                               upper_bound: float, tolerance: float = SOLVER_TOLERANCE,
                               max_iterations: int = SOLVER_MAX_ITERATIONS) -> dict[str, Any]:
    """Solve FCFF / (discount_rate - terminal_growth) = market EV by bisection.

    The existing FCFF perpetuity is strictly monotonic in its admissible domain,
    so a sign-changing bracket establishes a unique root; no stochastic start or
    extrapolation is used.
    """
    values = (forecast_fcff, discount_rate, market_enterprise_value, lower_bound, upper_bound, tolerance)
    if not all(math.isfinite(value) for value in values) or not isinstance(max_iterations, int) or max_iterations < 1:
        return {"state": "BLOCKED", "reason": "SOLVER_INPUT_MALFORMED"}
    if forecast_fcff <= 0 or discount_rate <= 0 or market_enterprise_value <= 0:
        return {"state": "BLOCKED", "reason": "INVALID_FCFF_OR_MARKET_EV_ECONOMICS"}
    if lower_bound >= upper_bound:
        return {"state": "BLOCKED", "reason": "INVALID_SOLVER_BOUNDS"}
    if upper_bound >= discount_rate:
        return {"state": "BLOCKED", "reason": "TERMINAL_GROWTH_BOUND_VIOLATES_DISCOUNT_RATE"}

    def residual(growth: float) -> float:
        return forecast_fcff / (discount_rate - growth) - market_enterprise_value

    low_residual, high_residual = residual(lower_bound), residual(upper_bound)
    if abs(low_residual) <= tolerance:
        return {"state": "READY", "value": lower_bound, "iterations": 0, "residual": low_residual}
    if abs(high_residual) <= tolerance:
        return {"state": "READY", "value": upper_bound, "iterations": 0, "residual": high_residual}
    if low_residual * high_residual > 0:
        return {"state": "BLOCKED", "reason": "NO_ROOT_WITHIN_ADMISSIBLE_BOUNDS"}
    lower, upper = lower_bound, upper_bound
    for iteration in range(1, max_iterations + 1):
        candidate = (lower + upper) / 2.0
        candidate_residual = residual(candidate)
        if abs(candidate_residual) <= tolerance:
            return {"state": "READY", "value": candidate, "iterations": iteration, "residual": candidate_residual}
        if low_residual * candidate_residual < 0:
            upper, high_residual = candidate, candidate_residual
        else:
            lower, low_residual = candidate, candidate_residual
    return {"state": "BLOCKED", "reason": "SOLVER_DID_NOT_CONVERGE_WITHIN_MAX_ITERATIONS"}


def _price(record: Mapping[str, Any] | None) -> tuple[float | None, dict[str, Any] | None, list[str]]:
    candidate = (record or {}).get("price_input") if isinstance(record, Mapping) else None
    if not isinstance(candidate, Mapping):
        return None, None, ["CURRENT_PRICE_INPUT_UNAVAILABLE"]
    value = _number(candidate.get("value"))
    if candidate.get("status") != "PRICE_READY" or value is None or value <= 0:
        return None, None, ["CURRENT_PRICE_UNUSABLE"]
    return value, {
        "source_artifact_identity": candidate.get("source_snapshot_identity"),
        "session": candidate.get("session"),
        "status": candidate.get("status"),
        "source": candidate.get("source"),
    }, []


def _intrinsic_methods(record: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(record, Mapping):
        return {}
    nested = record.get("intrinsic_valuation")
    source = nested if isinstance(nested, Mapping) else record
    methods = source.get("methods")
    return methods if isinstance(methods, Mapping) else {}


def _value_gap(*, price: float | None, price_identity: Mapping[str, Any] | None,
               intrinsic_record: Mapping[str, Any] | None) -> dict[str, Any]:
    methods = _intrinsic_methods(intrinsic_record)
    if not methods:
        return _method("EXISTING_INTRINSIC_VALUE_GAP_V1", "UNAVAILABLE", reason_codes=["INTRINSIC_VALUATION_UPSTREAM_UNAVAILABLE"])
    available = [(name, method) for name, method in sorted(methods.items()) if isinstance(method, Mapping) and method.get("state") == "available"]
    if not available:
        return _method("EXISTING_INTRINSIC_VALUE_GAP_V1", "UNAVAILABLE", reason_codes=["NO_AVAILABLE_UPSTREAM_INTRINSIC_METHOD"])
    if price is None:
        return _method("EXISTING_INTRINSIC_VALUE_GAP_V1", "BLOCKED", reason_codes=["CURRENT_PRICE_UNUSABLE"], missing_inputs=["current_market_price"])
    per_share = [(name, method, _number(method.get("per_share_value"))) for name, method in available]
    usable = [(name, method, value) for name, method, value in per_share if value is not None]
    if not usable:
        return _method("EXISTING_INTRINSIC_VALUE_GAP_V1", "BLOCKED", reason_codes=["UPSTREAM_INTRINSIC_PER_SHARE_VALUE_UNAVAILABLE"], missing_inputs=["intrinsic_value_per_share"])
    if len(usable) != 1:
        return _method("EXISTING_INTRINSIC_VALUE_GAP_V1", "BLOCKED", reason_codes=["MULTIPLE_UPSTREAM_INTRINSIC_METHODS_REQUIRE_SEPARATE_COMPARISON"])
    name, method, value = usable[0]
    return _method(
        "EXISTING_INTRINSIC_VALUE_GAP_V1", "READY", current_price=price,
        valuation_input_identity=price_identity, intrinsic_method=name,
        intrinsic_value_per_share=value, absolute_gap=value - price,
        relative_gap=(value / price) - 1.0,
        used_inputs={"current_market_price": price, "intrinsic_value_per_share": value, "upstream_method": name},
        warnings=list(method.get("warnings") or []),
        interpretation_limits=["NUMERIC_COMPARISON_ONLY_NO_INVESTMENT_LABEL", "CURRENT_RESEARCH_ONLY", "NO_TARGET_PRICE_RECOMMENDATION_SIZING_OR_PROBABILITY"],
    )


def _reverse_growth(*, price: float | None, price_identity: Mapping[str, Any] | None,
                    intrinsic_record: Mapping[str, Any] | None) -> dict[str, Any]:
    if price is None:
        return _method("REVERSE_FCFF_TERMINAL_GROWTH_V1", "BLOCKED", reason_codes=["CURRENT_PRICE_UNUSABLE"], missing_inputs=["current_market_price"])
    if not isinstance(intrinsic_record, Mapping):
        return _method("REVERSE_FCFF_TERMINAL_GROWTH_V1", "UNAVAILABLE", reason_codes=["INTRINSIC_VALUATION_UPSTREAM_UNAVAILABLE"])
    inputs = intrinsic_record.get("reverse_fcff_inputs")
    if not isinstance(inputs, Mapping):
        return _method("REVERSE_FCFF_TERMINAL_GROWTH_V1", "UNAVAILABLE", reason_codes=["REVERSE_FCFF_FIXED_INPUTS_UNAVAILABLE"])
    missing: list[str] = []
    values: dict[str, float] = {}
    for field in ("forecast_fcff", "wacc", "market_enterprise_value"):
        value = _number(inputs.get(field))
        if value is None or not isinstance(inputs.get(f"{field}_source"), str):
            missing.append(f"sourced_{field}")
        else:
            values[field] = value
    bounds = inputs.get("growth_bounds")
    if not isinstance(bounds, Mapping) or _number(bounds.get("lower")) is None or _number(bounds.get("upper")) is None:
        missing.append("explicit_growth_bounds")
    if missing:
        return _method("REVERSE_FCFF_TERMINAL_GROWTH_V1", "UNAVAILABLE", reason_codes=["REVERSE_FCFF_REQUIRED_INPUTS_MISSING"], missing_inputs=missing)
    lower, upper = _number(bounds["lower"]), _number(bounds["upper"])
    assert lower is not None and upper is not None
    existing_terminal = _number(inputs.get("terminal_growth"))
    if existing_terminal is not None and existing_terminal >= values["wacc"]:
        return _method("REVERSE_FCFF_TERMINAL_GROWTH_V1", "BLOCKED", reason_codes=["EXISTING_TERMINAL_GROWTH_VIOLATES_DISCOUNT_RATE"])
    solved = solve_fcff_terminal_growth(
        forecast_fcff=values["forecast_fcff"], discount_rate=values["wacc"],
        market_enterprise_value=values["market_enterprise_value"], lower_bound=lower, upper_bound=upper,
    )
    if solved["state"] != "READY":
        return _method("REVERSE_FCFF_TERMINAL_GROWTH_V1", "BLOCKED", reason_codes=[solved["reason"]], bounds={"lower": lower, "upper": upper})
    return _method(
        "REVERSE_FCFF_TERMINAL_GROWTH_V1", "READY", current_price=price,
        valuation_input_identity=price_identity, solved_parameter="terminal_growth", solved_value=solved["value"],
        bounds={"lower": lower, "upper": upper}, convergence="CONVERGED_UNIQUE_MONOTONIC_FCFF_PERPETUITY_ROOT",
        iteration_count=solved["iterations"], residual=solved["residual"],
        used_inputs={key: values[key] for key in sorted(values)} | {"sources": {key: inputs[f"{key}_source"] for key in sorted(values)}},
        interpretation_limits=["SOLVED_TERMINAL_GROWTH_IS_MODEL_IMPLICATION_NOT_FORECAST", "CURRENT_RESEARCH_ONLY", "NO_TARGET_PRICE_RECOMMENDATION_SIZING_OR_PROBABILITY"],
    )


def build_artifact(*, current_valuation: Mapping[str, Any], valuation_proxy: Mapping[str, Any],
                   fundamental: Mapping[str, Any] | None = None, intrinsic: Mapping[str, Any] | None = None,
                   as_of: str | None = None) -> dict[str, Any]:
    """Evaluate each governed proxy-denominator ticker without recomputing upstream values."""
    proxy_records = valuation_proxy.get("records") if isinstance(valuation_proxy, Mapping) else None
    if not isinstance(proxy_records, Mapping):
        raise ValueError("VALUATION_PROXY_DENOMINATOR_UNAVAILABLE")
    valuation_records = current_valuation.get("records") if isinstance(current_valuation, Mapping) else {}
    fundamental_records = fundamental.get("records") if isinstance(fundamental, Mapping) else {}
    intrinsic_records = intrinsic.get("records") if isinstance(intrinsic, Mapping) else {}
    records: dict[str, dict[str, Any]] = {}
    state_counts: Counter[str] = Counter()
    method_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for ticker in sorted(proxy_records):
        valuation_record = valuation_records.get(ticker) if isinstance(valuation_records, Mapping) else None
        price, price_identity, price_reasons = _price(valuation_record)
        intrinsic_record = intrinsic_records.get(ticker) if isinstance(intrinsic_records, Mapping) else None
        gap = _value_gap(price=price, price_identity=price_identity, intrinsic_record=intrinsic_record)
        reverse = _reverse_growth(price=price, price_identity=price_identity, intrinsic_record=intrinsic_record)
        for reason in price_reasons + list(gap["reason_codes"]) + list(reverse["reason_codes"]):
            reason_counts[reason] += 1
        method_counts[f"{gap['method']}:{gap['state']}"] += 1
        method_counts[f"{reverse['method']}:{reverse['state']}"] += 1
        states = {gap["state"], reverse["state"]}
        state = "READY" if "READY" in states and len(states) == 1 else "PARTIAL" if "READY" in states else "BLOCKED" if "BLOCKED" in states else "UNAVAILABLE"
        state_counts[state] += 1
        proxy = proxy_records[ticker] if isinstance(proxy_records[ticker], Mapping) else {}
        fundamental_context = fundamental_records.get(ticker) if isinstance(fundamental_records, Mapping) else None
        records[ticker] = {
            "ticker": ticker, "as_of": as_of or current_valuation.get("valuation_session"), "state": state,
            "research_tier": RESEARCH_TIER, "is_actionable": False,
            "valuation_proxy_context": {"valuation_tier": proxy.get("valuation_tier"), "metrics": proxy.get("metrics"), "warnings": proxy.get("warnings")},
            "fundamental_context": fundamental_context if isinstance(fundamental_context, Mapping) else {"status": "UNAVAILABLE"},
            "upstream_identities": {"current_valuation": current_valuation.get("artifact_identity") or current_valuation.get("artifact_sha256"), "valuation_proxy": valuation_proxy.get("artifact_identity") or valuation_proxy.get("artifact_sha256"), "fundamental": (fundamental or {}).get("artifact_identity") or (fundamental or {}).get("artifact_sha256"), "intrinsic": (intrinsic or {}).get("artifact_identity") or (intrinsic or {}).get("artifact_sha256")},
            "methods": {gap["method"]: gap, reverse["method"]: reverse},
            "warnings": sorted(set(price_reasons + list(proxy.get("warnings") or []))),
            "interpretation_limits": ["UPSTREAM_MULTIPLES_AND_FUNDAMENTAL_SCORES_ARE_NOT_FORECAST_ASSUMPTIONS", "NO_TARGET_PRICE_RECOMMENDATION_SIZING_OR_PROBABILITY"],
        }
    artifact: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION, "as_of": as_of or current_valuation.get("valuation_session"),
        "universe_denominator": len(records), "residual": 0, "records": records,
        "coverage": {"states": dict(sorted(state_counts.items())), "methods": dict(sorted(method_counts.items())), "reason_codes": dict(sorted(reason_counts.items()))},
        "source_artifacts": {"current_valuation": current_valuation.get("artifact_identity") or current_valuation.get("artifact_sha256"), "valuation_proxy": valuation_proxy.get("artifact_identity") or valuation_proxy.get("artifact_sha256"), "fundamental": (fundamental or {}).get("artifact_identity") or (fundamental or {}).get("artifact_sha256"), "intrinsic": (intrinsic or {}).get("artifact_identity") or (intrinsic or {}).get("artifact_sha256")},
        "authority_effect": "NONE", "research_tier": RESEARCH_TIER, "is_actionable": False,
        "interpretation_limits": ["NO_NEW_VALUATION_ONTOLOGY_OR_ASSUMPTION_GENERATION", "CURRENT_RESEARCH_ONLY", "NO_TARGET_PRICE_RECOMMENDATION_SIZING_PROBABILITY_PIT_OR_RAW_AS_TRADED_AUTHORITY"],
    }
    artifact.update(_identity(artifact))
    return artifact
