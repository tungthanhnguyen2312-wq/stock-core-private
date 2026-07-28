"""Fail-closed fundamental-quality evaluation over evidence-backed canonical records only."""
from __future__ import annotations

from typing import Any, Callable

VERSION = "1.2.0"
MODEL_NAMES = (
    "growth_profitability", "dupont_roe", "earnings_quality", "financial_strength",
    "piotroski_f_score", "altman_z_score", "beneish_m_score", "bank_financial_quality",
)


def _out(name: str, state: str, **extra: Any) -> dict[str, Any]:
    return {
        "model_name": name, "model_version": VERSION, "applicability_state": state,
        "result_state": state, "score_or_value": None, "component_results": {},
        "input_periods": [], "statement_scope": None, "required_inputs": [],
        "used_inputs": [], "used_input_facts": {}, "input_classification": {},
        "missing_inputs": [], "provenance": "financial_canonical", "warnings": [],
        "interpretation_limits": ["Numeric result is not automatically actionable."],
        "is_actionable": False, **extra,
    }


def _usable(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if r.get("quality_state") == "available" and r.get("value") is not None
            and r.get("statement_scope") in {"consolidated", "separate"}
            and isinstance(r.get("period_identity"), dict)]


def _by_period(records: list[dict[str, Any]], metric: str, scope: str, kind: str) -> dict[str, dict[str, Any]]:
    return {r["period_identity"]["period"]: r for r in records if r.get("canonical_metric") == metric
            and r.get("statement_scope") == scope and r["period_identity"].get("period_type") == kind}


def _latest_common_period(records: list[dict[str, Any]], required: list[str], scope: str, kind: str = "annual") -> tuple[dict[str, dict[str, Any]] | None, list[str]]:
    by_metric = {metric: _by_period(records, metric, scope, kind) for metric in required}
    missing = [metric for metric, values in by_metric.items() if not values]
    if missing:
        return None, missing
    common = set.intersection(*(set(values) for values in by_metric.values()))
    if not common:
        return None, [f"inputs_share_no_common_{kind}_period"]
    period = max(common)
    return {metric: by_metric[metric][period] for metric in required}, []


def _input_classification(records: list[dict[str, Any]], required: list[str], scope: str, kind: str = "annual") -> dict[str, str]:
    result: dict[str, str] = {}
    for metric in required:
        matching = [r for r in records if r.get("canonical_metric") == metric]
        compatible = _by_period(records, metric, scope, kind)
        if compatible:
            result[metric] = "qualified"
        elif any(r.get("quality_state") == "incomparable" for r in matching):
            result[metric] = "incomparable"
        elif any(r.get("freshness_status") == "stale" for r in matching):
            result[metric] = "stale"
        else:
            result[metric] = "missing"
    return result


_COMPONENT_FIELDS = (
    "canonical_metric", "derivation_role", "value", "period_identity", "statement_scope",
    "currency", "unit_scale", "source", "observation_ids", "citation_id", "evidence_id",
)


def _component_key(component: dict[str, Any]) -> tuple[Any, ...]:
    return (component["canonical_metric"], tuple(component["observation_ids"]), component["citation_id"], component["evidence_id"])


def _component_lineage(record: dict[str, Any], components: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not isinstance(components, list) or not components:
        return None, "derived_components_missing"
    expected = {"period_identity": record.get("period_identity"), "statement_scope": record.get("statement_scope"), "currency": record.get("currency"), "unit_scale": record.get("unit_scale")}
    normalized: list[dict[str, Any]] = []
    for component in components:
        if not isinstance(component, dict) or any(component.get(field) is None for field in _COMPONENT_FIELDS):
            return None, "derived_component_lineage_missing_required_field"
        if not isinstance(component["period_identity"], dict) or not component["period_identity"].get("period") or not component["period_identity"].get("period_type"):
            return None, "derived_component_period_identity_invalid"
        if not isinstance(component["observation_ids"], list) or not component["observation_ids"]:
            return None, "derived_component_observation_identity_invalid"
        if any(component[field] != expected[field] for field in expected):
            return None, "derived_component_incomparable_to_fact"
        normalized.append({field: component[field] for field in _COMPONENT_FIELDS})
    normalized.sort(key=_component_key)
    if len({_component_key(component) for component in normalized}) != len(normalized):
        return None, "derived_component_identity_conflict"
    return normalized, None


def _fact(record: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
    fact = {
        "value": record.get("value"), "period_identity": record.get("period_identity"),
        "statement_scope": record.get("statement_scope"), "currency": record.get("currency"),
        "unit_scale": record.get("unit_scale"), "source": record.get("source"),
        "observation_ids": record.get("observation_ids"), "citation_id": evidence.get("citation_id"),
        "evidence_id": evidence.get("evidence_id"),
    }
    components = evidence.get("components")
    if record.get("derivation_status") != "derived" and components is None:
        return fact, None
    lineage, reason = _component_lineage(record, components)
    if reason:
        return None, reason
    fact["component_lineage"] = lineage
    return fact, None


def _model(records: list[dict[str, Any]], name: str, required: list[str], scope: str,
           calc: Callable[[dict[str, dict[str, Any]]], tuple[Any, dict[str, Any]]], *, kind: str = "annual",
           warning: str | None = None) -> dict[str, Any]:
    found, missing = _latest_common_period(records, required, scope, kind)
    classification = _input_classification(records, required, scope, kind)
    if missing:
        return _out(name, "unavailable", statement_scope=scope, required_inputs=required,
                    missing_inputs=missing, input_classification=classification)
    facts: dict[str, dict[str, Any]] = {}
    lineage_errors: dict[str, str] = {}
    for metric, row in found.items():
        fact, reason = _fact(row)
        if reason:
            lineage_errors[metric] = reason
        else:
            facts[metric] = fact
    if lineage_errors:
        invalid = sorted(lineage_errors)
        classifications = dict(classification)
        classifications.update({metric: "incomparable" for metric in invalid})
        return _out(name, "unavailable", statement_scope=scope, required_inputs=required,
                    missing_inputs=[f"{metric}_lineage_unavailable" for metric in invalid],
                    input_classification=classifications,
                    warnings=[lineage_errors[metric] for metric in invalid])
    value, components = calc(found)
    warnings = [warning] if warning else []
    return _out(name, "available", statement_scope=scope, score_or_value=value,
                component_results=components, input_periods=[row["period_identity"] for row in found.values()],
                required_inputs=required, used_inputs=required, used_input_facts=facts,
                input_classification=classification, warnings=warnings)


def _inapplicable(name: str, reason: str) -> dict[str, Any]:
    return _out(name, "inapplicable", warnings=[reason],
                input_classification={"sector": "sector-inapplicable"})


def _corporate_models(records: list[dict[str, Any]], scope: str) -> dict[str, dict[str, Any]]:
    margin = _model(records, "growth_profitability", ["revenue", "net_income"], scope,
                    lambda x: (x["net_income"]["value"] / x["revenue"]["value"] if x["revenue"]["value"] else None,
                               {"net_margin": x["net_income"]["value"] / x["revenue"]["value"] if x["revenue"]["value"] else None}))
    dupont = _model(records, "dupont_roe", ["net_income", "revenue", "total_assets", "shareholders_equity"], scope,
                    lambda x: ((x["net_income"]["value"] / x["revenue"]["value"]) * (x["revenue"]["value"] / x["total_assets"]["value"]) * (x["total_assets"]["value"] / x["shareholders_equity"]["value"])
                               if x["revenue"]["value"] and x["total_assets"]["value"] and x["shareholders_equity"]["value"] else None, {}))
    piotroski = _model(records, "piotroski_f_score", ["net_income", "operating_cash_flow", "total_assets"], scope,
                         lambda x: (sum((x["net_income"]["value"] > 0, x["operating_cash_flow"]["value"] > 0,
                                         x["operating_cash_flow"]["value"] > x["net_income"]["value"])), {}),
                         warning="Incomplete Piotroski criteria are not rescaled to nine points.")
    return {
        "growth_profitability": margin,
        "dupont_roe": dupont,
        "earnings_quality": _model(records, "earnings_quality", ["operating_cash_flow", "net_income"], scope,
                                     lambda x: (x["operating_cash_flow"]["value"] - x["net_income"]["value"], {})),
        "financial_strength": _model(records, "financial_strength", ["total_debt", "cash_and_equivalents", "shareholders_equity"], scope,
                                     lambda x: (x["total_debt"]["value"] - x["cash_and_equivalents"]["value"], {})),
        "piotroski_f_score": piotroski,
        "altman_z_score": _out("altman_z_score", "inapplicable", warnings=["qualified_altman_variant_not_available"]),
        "beneish_m_score": _out("beneish_m_score", "unavailable", warnings=["exact_beneish_variables_not_available"]),
        "bank_financial_quality": _inapplicable("bank_financial_quality", "bank_variant_not_applicable_to_corporate_entity"),
    }


def _bank_models(records: list[dict[str, Any]], scope: str) -> dict[str, dict[str, Any]]:
    bank = _model(records, "bank_financial_quality",
                  ["net_interest_income", "net_income", "customer_loans_net", "customer_deposits", "provision_for_credit_losses", "total_assets", "total_equity"], scope,
                  lambda x: (None, {
                      "net_interest_income": x["net_interest_income"]["value"],
                      "net_income": x["net_income"]["value"],
                      "loan_to_deposit_ratio": x["customer_loans_net"]["value"] / x["customer_deposits"]["value"] if x["customer_deposits"]["value"] else None,
                      "credit_cost_ratio": x["provision_for_credit_losses"]["value"] / x["customer_loans_net"]["value"] if x["customer_loans_net"]["value"] else None,
                      "return_on_assets": x["net_income"]["value"] / x["total_assets"]["value"] if x["total_assets"]["value"] else None,
                      "return_on_equity": x["net_income"]["value"] / x["total_equity"]["value"] if x["total_equity"]["value"] else None,
                  }), warning="Bank component facts only; no corporate cash-flow, debt, Piotroski, Altman, or Beneish assumptions are applied.")
    models = {name: _inapplicable(name, "corporate_variant_not_qualified_for_bank_entity") for name in MODEL_NAMES if name != "bank_financial_quality"}
    models["bank_financial_quality"] = bank
    return models


def evaluate_fundamental_quality(canonical: dict[str, Any] | None, entity_type: str = "unknown") -> dict[str, Any]:
    records = (canonical or {}).get("records", []) if isinstance(canonical, dict) else []
    if not records:
        return {"schema_version": VERSION, "entity_type": entity_type,
                "models": {name: _out(name, "unknown", warnings=["canonical_records_missing"]) for name in MODEL_NAMES}}
    usable = _usable(records)
    if not usable:
        return {"schema_version": VERSION, "entity_type": entity_type,
                "models": {name: _out(name, "unknown", warnings=["no_compatible_known_scope_canonical_records"]) for name in MODEL_NAMES}}
    scopes = sorted({record["statement_scope"] for record in usable})
    scope = scopes[0]
    if entity_type in {"corporate", "industrial"}:
        models = _corporate_models(usable, scope)
    elif entity_type == "bank":
        models = _bank_models(usable, scope)
    else:
        models = {name: _out(name, "unknown", warnings=["entity_type_not_qualified"]) for name in MODEL_NAMES}
    return {"schema_version": VERSION, "entity_type": entity_type, "models": models}
