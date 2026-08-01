"""Fail-closed fundamental-quality evaluation over evidence-backed canonical records only.

Phase 6B hardening: the legacy MODEL_NAMES submodels are computed from single, evidence-
verified (quality_state=="available") periods only -- never an unverified prior period.
Several submodel names imply a standard, comparative-period-aware methodology
(dupont_roe, piotroski_f_score) that this module has never actually implemented; this
version makes that gap explicit rather than silent:
  - dupont_roe uses period-end (not average) total_assets/shareholders_equity, because no
    verified prior-period closing balance exists to average against. result_state is
    "partial" (not "available") whenever it computes a value, with limitations explaining
    the period-end-vs-average distinction. This module still never computes an
    average-balance DuPont -- there is nothing here to "complete" once a verified prior
    period exists; that remains a future milestone's decision.
  - piotroski_f_score only ever evaluates 3 of the 9 standard criteria (none of which are
    year-over-year comparisons); it never emits a value under score_or_value (so nothing
    resembling a 0-9 F-Score is ever presented as usable), and reports the raw
    criteria-met count separately, clearly scoped to a 0-3 range, under component_results.
  - altman_z_score and beneish_m_score remain unavailable/inapplicable exactly as before
    (no qualified variant or exact variables exist for these tickers).
  - earnings_quality's result can be reconciled after the fact against the newer, stricter
    fundamental_quality_evidence contract (Phase 6A) via
    reconcile_legacy_fundamental_quality_with_qualified_evidence(); when the two would
    diverge or are not directly comparable, the legacy value is superseded rather than
    left to potentially contradict the qualified evidence.

Every model result additionally exposes status/applicability/is_partial/blocking_reasons/
limitations (equivalent to, and derived from, the pre-existing result_state/
applicability_state/interpretation_limits/missing_inputs fields) without removing or
renaming any existing key -- Consumer's fundamental_quality_contract() already validates
result_state against {"available","partial","unavailable","inapplicable","incomparable",
"unknown"}, so "partial" is an existing, already-supported state, not a new one.
is_actionable is unconditionally False throughout, and no submodel here ever emits a
recommendation, rating, ranking, or composite score.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

VERSION = "1.2.0"
MODEL_NAMES = (
    "growth_profitability", "dupont_roe", "earnings_quality", "financial_strength",
    "piotroski_f_score", "altman_z_score", "beneish_m_score", "bank_financial_quality",
)


def _out(name: str, state: str, **extra: Any) -> dict[str, Any]:
    is_partial = extra.pop("is_partial", False)
    blocking_reasons_override = extra.pop("blocking_reasons", None)
    limitations_override = extra.pop("limitations", None)
    result = {
        "model_name": name, "model_version": VERSION, "applicability_state": state,
        "result_state": state, "score_or_value": None, "component_results": {},
        "input_periods": [], "statement_scope": None, "required_inputs": [],
        "used_inputs": [], "used_input_facts": {}, "input_classification": {},
        "missing_inputs": [], "provenance": "financial_canonical", "warnings": [],
        "interpretation_limits": ["Numeric result is not automatically actionable."],
        "is_actionable": False, **extra,
    }
    # Phase 6B: additive fields equivalent to status/applicability/is_partial/
    # blocking_reasons/limitations. Existing keys above are unchanged.
    result["status"] = result["result_state"]
    result["applicability"] = result["applicability_state"]
    result["is_partial"] = is_partial
    result["blocking_reasons"] = list(blocking_reasons_override) if blocking_reasons_override is not None else list(result["missing_inputs"])
    result["limitations"] = list(limitations_override) if limitations_override is not None else list(result["interpretation_limits"])
    return result


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


def _distinct_annual_periods(records: list[dict[str, Any]], metric: str, scope: str) -> set[str]:
    """All distinct annual periods with an evidence-verified (quality_state==available)
    observation for one metric -- used only to detect whether verified comparative
    (year-over-year) history exists at all, never to select an unverified period."""
    return set(_by_period(records, metric, scope, "annual"))


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
    return _out(name, "inapplicable", warnings=[reason], blocking_reasons=[reason],
                limitations=[reason], input_classification={"sector": "sector-inapplicable"})


def _harden_dupont(dupont: dict[str, Any]) -> dict[str, Any]:
    """Requirement 3 (Phase 6B): must not imply a standard (average-balance) decomposition.
    This module has never computed an average-balance DuPont and does not start now -- when
    a value is available it is demoted from "available" to the already-Consumer-supported
    "partial" state, with an explicit limitation, rather than silently presented as the
    standard three-step identity."""
    if dupont.get("result_state") != "available":
        return dupont
    dupont["result_state"] = "partial"
    dupont["status"] = "partial"
    dupont["is_partial"] = True
    dupont["warnings"] = list(dupont.get("warnings", [])) + [
        "period_end_balances_used_not_average_this_is_not_the_standard_dupont_identity",
    ]
    dupont["limitations"] = list(dupont.get("limitations", [])) + [
        "Uses period-end total_assets and shareholders_equity, not the average of beginning- and "
        "ending-period balances; this is a simplified approximation, not the standard three-step "
        "DuPont identity, because no verified prior-period closing balance exists to average "
        "against. Do not read this value as directly comparable to a textbook average-balance ROE "
        "decomposition.",
    ]
    return dupont


def _harden_piotroski(piotroski: dict[str, Any], has_comparative_history: bool) -> dict[str, Any]:
    """Requirements 2 and 4 (Phase 6B): a model requiring verified comparative periods must
    not emit a usable score when they are absent, and must never be presented as a standard
    0-9 F-Score from a partial single-period proxy. This implementation only ever evaluates
    3 of the 9 standard Piotroski criteria (all non-comparative); it now never emits a value
    under score_or_value regardless of comparative-period availability, since the underlying
    calculation can never produce a standard F-Score. The raw criteria-met count is preserved,
    transparently, under component_results (never under score_or_value), explicitly scoped to
    0-3, not 0-9."""
    if piotroski.get("result_state") != "available":
        return piotroski
    criteria_met = piotroski.get("score_or_value")
    piotroski["result_state"] = "partial"
    piotroski["status"] = "partial"
    piotroski["is_partial"] = True
    piotroski["score_or_value"] = None
    piotroski["component_results"] = {
        "non_comparative_criteria_met": criteria_met,
        "non_comparative_criteria_evaluated": 3,
        "standard_piotroski_f_score_scale": "0-9 (NOT reported here)",
    }
    reasons = ["only_3_of_9_standard_piotroski_criteria_are_implemented_no_year_over_year_criteria_are_computed"]
    if not has_comparative_history:
        reasons.append("no_verified_comparative_annual_period_available_for_the_6_year_over_year_criteria")
    piotroski["blocking_reasons"] = list(piotroski.get("blocking_reasons", [])) + reasons
    piotroski["warnings"] = list(piotroski.get("warnings", [])) + reasons
    piotroski["limitations"] = list(piotroski.get("limitations", [])) + [
        "The standard Piotroski F-Score requires all 9 criteria, 6 of which are year-over-year "
        "comparisons; this implementation only evaluates the 3 non-comparative criteria and never "
        "emits a value under score_or_value, to avoid presenting a partial single-period proxy as "
        "if it were a standard 0-9 F-Score. See component_results for the transparent 0-3 count.",
    ]
    return piotroski


def _corporate_models(records: list[dict[str, Any]], scope: str) -> dict[str, dict[str, Any]]:
    has_comparative_history = len(_distinct_annual_periods(records, "net_income", scope)) >= 2

    margin = _model(records, "growth_profitability", ["revenue", "net_income"], scope,
                    lambda x: (x["net_income"]["value"] / x["revenue"]["value"] if x["revenue"]["value"] else None,
                               {"net_margin": x["net_income"]["value"] / x["revenue"]["value"] if x["revenue"]["value"] else None}))
    dupont = _harden_dupont(_model(
        records, "dupont_roe", ["net_income", "revenue", "total_assets", "shareholders_equity"], scope,
        lambda x: ((x["net_income"]["value"] / x["revenue"]["value"]) * (x["revenue"]["value"] / x["total_assets"]["value"]) * (x["total_assets"]["value"] / x["shareholders_equity"]["value"])
                   if x["revenue"]["value"] and x["total_assets"]["value"] and x["shareholders_equity"]["value"] else None, {}),
    ))
    piotroski = _harden_piotroski(
        _model(records, "piotroski_f_score", ["net_income", "operating_cash_flow", "total_assets"], scope,
               lambda x: (sum((x["net_income"]["value"] > 0, x["operating_cash_flow"]["value"] > 0,
                               x["operating_cash_flow"]["value"] > x["net_income"]["value"])), {})),
        has_comparative_history,
    )
    altman_reason = "qualified_altman_variant_not_available_ebit_retained_earnings_and_working_capital_are_not_qualified_canonical_metrics"
    beneish_reason = "exact_beneish_variables_not_available_requires_verified_comparative_period_not_available"
    return {
        "growth_profitability": margin,
        "dupont_roe": dupont,
        "earnings_quality": _model(records, "earnings_quality", ["operating_cash_flow", "net_income"], scope,
                                     lambda x: (x["operating_cash_flow"]["value"] - x["net_income"]["value"], {})),
        "financial_strength": _model(records, "financial_strength", ["total_debt", "cash_and_equivalents", "shareholders_equity"], scope,
                                     lambda x: (x["total_debt"]["value"] - x["cash_and_equivalents"]["value"], {})),
        "piotroski_f_score": piotroski,
        "altman_z_score": _out("altman_z_score", "inapplicable", warnings=[altman_reason],
                                blocking_reasons=[altman_reason], limitations=[altman_reason]),
        "beneish_m_score": _out("beneish_m_score", "unavailable", warnings=[beneish_reason],
                                 blocking_reasons=[beneish_reason], limitations=[beneish_reason]),
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
    if bank.get("result_state") == "available":
        bank["is_partial"] = True
        bank["limitations"] = list(bank.get("limitations", [])) + [
            "Component facts and simple ratios only; not a comparative-period-aware or "
            "composite bank health assessment.",
        ]
    models = {name: _inapplicable(name, "corporate_variant_not_qualified_for_bank_entity") for name in MODEL_NAMES if name != "bank_financial_quality"}
    models["bank_financial_quality"] = bank
    return models


def reconcile_earnings_quality_with_qualified_evidence(
    earnings_quality: dict[str, Any], qualified_evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Cross-check the legacy earnings_quality submodel against the newer, stricter
    fundamental_quality_evidence contract (Phase 6A) for the same ticker, when supplied.
    Mutates and returns earnings_quality in place. Qualified evidence takes precedence:
    when both agree (same statement scope, same reporting period, identical computed
    accrual gap) the legacy value is kept and marked comparable; otherwise the legacy
    submodel is superseded (downgraded, score withheld) rather than presenting a possibly
    diverging number as reliable. A no-op limitation note only is added when
    qualified_evidence is absent or itself not available -- this never makes
    fundamental_quality_evidence depend on this function or on the legacy field."""
    if not isinstance(qualified_evidence, Mapping) or qualified_evidence.get("status") != "available":
        earnings_quality["limitations"] = list(earnings_quality.get("limitations", [])) + [
            "Not cross-checked against fundamental_quality_evidence (not computed for this run).",
        ]
        return earnings_quality

    if earnings_quality.get("result_state") != "available":
        return earnings_quality

    qe_metrics = qualified_evidence.get("metrics") if isinstance(qualified_evidence.get("metrics"), Mapping) else {}
    qe_gap = qe_metrics.get("operating_cash_flow_less_net_income")
    legacy_periods = {p.get("period") for p in earnings_quality.get("input_periods", []) if isinstance(p, Mapping)}
    comparable = (
        qe_gap is not None
        and earnings_quality.get("statement_scope") == qualified_evidence.get("statement_scope")
        and legacy_periods == {qualified_evidence.get("reporting_period")}
        and earnings_quality.get("score_or_value") == qe_gap
    )
    if comparable:
        earnings_quality["warnings"] = list(earnings_quality.get("warnings", [])) + ["comparable_to_qualified_evidence"]
        earnings_quality["limitations"] = list(earnings_quality.get("limitations", [])) + [
            "Matches the qualified fundamental_quality_evidence result for the same period, "
            "scope, and inputs.",
        ]
    else:
        earnings_quality["result_state"] = "unavailable"
        earnings_quality["status"] = "unavailable"
        earnings_quality["score_or_value"] = None
        earnings_quality["is_partial"] = True
        earnings_quality["blocking_reasons"] = list(earnings_quality.get("blocking_reasons", [])) + [
            "superseded_by_qualified_fundamental_quality_evidence_diverging_or_not_comparable",
        ]
        earnings_quality["limitations"] = list(earnings_quality.get("limitations", [])) + [
            "Diverges from, or is not directly comparable to, the qualified "
            "fundamental_quality_evidence result for this ticker; that contract takes "
            "precedence over this legacy interpretation. See "
            "tickers[ticker].fundamental_quality_evidence for the qualified figure.",
        ]
    return earnings_quality


def reconcile_legacy_fundamental_quality_with_qualified_evidence(entry: Mapping[str, Any]) -> None:
    """Bundle-entry-level convenience wrapper (Phase 6B): mutates
    entry['fundamental_quality']['models']['earnings_quality'] in place using
    entry.get('fundamental_quality_evidence'), when both are present on the same entry.
    No-op when either is absent or malformed."""
    fundamental_quality = entry.get("fundamental_quality") if isinstance(entry, Mapping) else None
    if not isinstance(fundamental_quality, dict):
        return
    models = fundamental_quality.get("models")
    if not isinstance(models, dict) or not isinstance(models.get("earnings_quality"), dict):
        return
    reconcile_earnings_quality_with_qualified_evidence(models["earnings_quality"], entry.get("fundamental_quality_evidence"))


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
