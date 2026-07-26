"""Fail-closed relative valuation evaluation over qualified observations only."""
from __future__ import annotations

import math
from typing import Any, Mapping

SCHEMA_VERSION = "1.0.0"
METHOD_VERSION = "1.0.0"
METHODS = ("pe", "pb", "ps", "ev_ebitda", "ev_sales")
MIN_REFERENCE_OBSERVATIONS = 3


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(value) else (int(value) if value.is_integer() else value)


def _method(name: str, state: str = "unavailable", **extra: Any) -> dict[str, Any]:
    result = {"method": name, "method_version": METHOD_VERSION, "state": state,
              "applicability": "unknown", "observed_multiple": None,
              "numerator_identity": None, "denominator_identity": None,
              "price_as_of_date": None, "financial_period": None, "statement_scope": None,
              "source": None, "provenance": {}, "comparison_universe": None,
              "observation_count": 0, "percentile": None, "reference_range": None,
              "implied_value_range": None, "missing_inputs": [], "warnings": [],
              "interpretation_limits": ["No target price is produced by this contract."],
              "is_actionable": False}
    result.update(extra)
    return result


def _reference(values: list[Any], universe: Mapping[str, Any] | None) -> tuple[dict[str, Any] | None, list[str]]:
    parsed = sorted(v for v in (_number(x) for x in values) if v is not None and v >= 0)
    if not isinstance(universe, Mapping) or not universe.get("deterministic"):
        return None, ["comparison_universe_not_deterministic"]
    if len(parsed) < MIN_REFERENCE_OBSERVATIONS:
        return None, ["reference_observations_insufficient"]
    # A deterministic, documented IQR fence excludes extreme observations without changing the raw evidence.
    q1, q3 = parsed[(len(parsed)-1)//4], parsed[(3*(len(parsed)-1))//4]
    low, high = q1 - 1.5*(q3-q1), q3 + 1.5*(q3-q1)
    kept = [v for v in parsed if low <= v <= high]
    if len(kept) < MIN_REFERENCE_OBSERVATIONS:
        return None, ["reference_observations_insufficient_after_outlier_filter"]
    return {"low": kept[0], "high": kept[-1], "median": kept[(len(kept)-1)//2], "outlier_policy": "iqr_1_5"}, []


def _qualified(record: Mapping[str, Any] | None, required_metric: str | None = None) -> tuple[float | int | None, list[str]]:
    if not isinstance(record, Mapping): return None, ["required_input_missing"]
    if required_metric and record.get("canonical_metric") != required_metric: return None, ["canonical_metric_mismatch"]
    if record.get("quality_state") != "available": return None, ["canonical_input_not_available"]
    if record.get("statement_scope") not in {"consolidated", "separate"}: return None, ["statement_scope_unknown_or_incompatible"]
    if not isinstance(record.get("period_identity"), Mapping): return None, ["financial_period_missing"]
    number = _number(record.get("value"))
    return (number, [] if number is not None else ["canonical_value_missing_or_malformed"])


def evaluate_relative_valuation(inputs: Mapping[str, Any] | None, reference_at: str | None = None) -> dict[str, Any]:
    """Evaluate only explicitly qualified observations; never reconstruct legacy inputs."""
    inputs = inputs if isinstance(inputs, Mapping) else {}
    entity_type = str(inputs.get("entity_type") or "unknown")
    price = inputs.get("current_price") if isinstance(inputs.get("current_price"), Mapping) else {}
    price_value = _number(price.get("value")); price_ok = bool(price.get("is_actionable") is True and price.get("as_of_date") and price_value is not None)
    share = inputs.get("share_count") if isinstance(inputs.get("share_count"), Mapping) else {}
    share_value = _number(share.get("value")); share_ok = share.get("semantics") in {"basic", "diluted"} and share_value is not None and share_value > 0
    financial = inputs.get("financial") if isinstance(inputs.get("financial"), Mapping) else {}
    direct = inputs.get("direct_multiples") if isinstance(inputs.get("direct_multiples"), Mapping) else {}
    methods: dict[str, dict[str, Any]] = {}
    for name in METHODS:
        methods[name] = _method(name, applicability="inapplicable" if entity_type == "financial" and name.startswith("ev_") else "unknown")
        if entity_type == "financial" and name.startswith("ev_"):
            methods[name]["state"] = "inapplicable"; methods[name]["warnings"] = ["enterprise_value_method_not_qualified_for_financial_sector"]
    specs = {"pe": "net_income", "pb": "shareholders_equity", "ps": "revenue", "ev_ebitda": "ebitda", "ev_sales": "revenue"}
    for name, metric in specs.items():
        if methods[name]["state"] == "inapplicable": continue
        direct_record = direct.get(name)
        if isinstance(direct_record, Mapping):
            value = _number(direct_record.get("value"))
            valid = (value is not None and direct_record.get("as_of_date") and direct_record.get("source") and
                     direct_record.get("multiple_semantics") == name and direct_record.get("is_actionable") is True)
            if valid and name == "pe" and value < 0:
                methods[name] = _method(name, "incomparable", applicability="applicable", observed_multiple=value,
                    price_as_of_date=direct_record["as_of_date"], source=direct_record["source"],
                    provenance=dict(direct_record.get("provenance") or {}), warnings=["negative_earnings_multiple_not_normalized"])
                continue
            if valid:
                methods[name] = _method(name, "available", applicability="applicable", observed_multiple=value,
                    price_as_of_date=direct_record["as_of_date"], source=direct_record["source"],
                    provenance=dict(direct_record.get("provenance") or {}), is_actionable=price_ok,
                    warnings=[] if price_ok else ["current_price_not_actionable"],
                    interpretation_limits=["Direct provider multiple; denominator semantics are provider-declared.", "No target price is produced by this contract."])
                continue
            methods[name] = _method(name, "malformed", missing_inputs=["qualified_direct_multiple_contract"], warnings=["direct_multiple_missing_semantics_or_provenance"]); continue
        denominator, missing = _qualified(financial.get(metric), metric)
        if name.startswith("ev_"):
            market_cap = inputs.get("market_cap") if isinstance(inputs.get("market_cap"), Mapping) else {}
            debt, debt_missing = _qualified(financial.get("total_debt"), "total_debt")
            cash, cash_missing = _qualified(financial.get("cash_and_equivalents"), "cash_and_equivalents")
            cap = _number(market_cap.get("value")); cap_ok = cap is not None and market_cap.get("semantics") == "qualified_market_cap" and market_cap.get("as_of_date")
            if cap_ok and debt is not None and cash is not None and denominator is not None and denominator > 0:
                methods[name] = _method(name, "available", applicability="applicable", observed_multiple=(cap+debt-cash)/denominator,
                    numerator_identity="enterprise_value", denominator_identity=metric, price_as_of_date=market_cap.get("as_of_date"),
                    financial_period=financial[metric].get("period_identity"), statement_scope=financial[metric].get("statement_scope"),
                    source=market_cap.get("source"), provenance={"market_cap": market_cap, "debt": financial["total_debt"], "cash": financial["cash_and_equivalents"]},
                    is_actionable=price_ok, warnings=[] if price_ok else ["current_price_not_actionable"])
            else: methods[name] = _method(name, "unavailable", missing_inputs=missing+debt_missing+cash_missing+([] if cap_ok else ["qualified_market_cap"]), warnings=["enterprise_value_semantics_or_inputs_unqualified"])
            continue
        if denominator is None or denominator <= 0:
            methods[name] = _method(name, "incomparable" if denominator is not None and denominator < 0 else "unavailable", missing_inputs=missing or ["positive_denominator_required"], warnings=["negative_or_zero_denominator_not_normalized"]); continue
        period = financial[metric].get("period_identity")
        aligned = isinstance(period, Mapping) and price.get("financial_period") == period.get("period")
        if not price_ok or not share_ok or not aligned:
            methods[name] = _method(name, "unavailable", missing_inputs=([] if price_ok else ["actionable_current_price"]) + ([] if share_ok else ["qualified_share_count"]) + ([] if aligned else ["price_financial_period_alignment"])); continue
        scope = financial[metric].get("statement_scope")
        methods[name] = _method(name, "available", applicability="applicable", observed_multiple=(price_value*share_value)/denominator,
            numerator_identity="market_cap_derived_from_price_and_qualified_share_count", denominator_identity=metric,
            price_as_of_date=price.get("as_of_date"), financial_period=financial[metric].get("period_identity"), statement_scope=scope,
            source=price.get("source"), provenance={"price": dict(price), "share_count": dict(share), "financial": dict(financial[metric])}, is_actionable=True)
    for name, values in (inputs.get("historical") or {}).items():
        if name in methods and isinstance(values, list):
            ref, warnings = _reference(values, inputs.get("historical_universe")); methods[name]["reference_range"] = ref; methods[name]["observation_count"] = len(values); methods[name]["warnings"].extend(warnings)
    return {"schema_version": SCHEMA_VERSION, "reference_at": reference_at, "status": "available" if any(m["state"] == "available" for m in methods.values()) else "unknown", "methods": methods,
            "warnings": ["Relative valuation does not produce a target price."]}
