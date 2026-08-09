"""Deterministic Phase 4B historical fundamental decision-support contract.

This module is deliberately pure: it consumes already-built qualified/canonical Producer
sections and never reads provider payloads, prices, shares, or the clock.  It emits a
historical-only structured analysis for the approved pilot set; it is not a valuation,
ranking, or recommendation engine.
"""

from __future__ import annotations

from typing import Any, Mapping


SCHEMA_VERSION = "1.0.0"
ENGINE_VERSION = "phase-4b/1.0.0"
PILOT_TICKERS = frozenset({"HPG", "VNM", "VCB"})
_ELIGIBILITY = frozenset({"eligible", "partially_eligible", "insufficient_evidence", "blocked"})
_DIMENSION_STATES = frozenset({"available", "unavailable", "not_applicable"})


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sorted_strings(values: list[str]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value})


def _period(record: Mapping[str, Any]) -> str | None:
    identity = _mapping(record.get("period_identity"))
    value = identity.get("period") or record.get("reporting_period")
    return str(value) if value is not None else None


def _fact_reference(record: Mapping[str, Any]) -> dict[str, Any]:
    evidence = _mapping(record.get("evidence"))
    return {
        "canonical_metric": record.get("canonical_metric"),
        "value": record.get("value"),
        "reporting_period": _period(record),
        "statement_scope": record.get("statement_scope"),
        "currency": record.get("currency"),
        "unit_scale": record.get("unit_scale"),
        "source": record.get("source"),
        "observation_ids": sorted(str(value) for value in (record.get("observation_ids") or []) if value),
        "evidence_id": evidence.get("evidence_id"),
        "citation_id": evidence.get("citation_id"),
    }


def _qualified_facts(financial_canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = financial_canonical.get("records")
    if not isinstance(records, list):
        return []
    accepted = [
        _fact_reference(record) for record in records
        if isinstance(record, Mapping)
        and record.get("quality_state") == "available"
        and record.get("value") is not None
        and record.get("canonical_metric")
    ]
    return sorted(accepted, key=lambda item: (
        str(item.get("reporting_period") or ""), str(item.get("canonical_metric") or ""),
        ",".join(item.get("observation_ids") or []),
    ))


def _dimension(
    name: str, status: str, *, supporting_facts: list[dict[str, Any]] | None = None,
    source_paths: list[str] | None = None, warnings: list[str] | None = None,
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    if status not in _DIMENSION_STATES:
        raise ValueError(f"unsupported_dimension_status:{status}")
    return {
        "dimension": name,
        "status": status,
        "supporting_facts": supporting_facts or [],
        "source_paths": _sorted_strings(source_paths or []),
        "warnings": _sorted_strings(warnings or []),
        "reason_codes": _sorted_strings(reason_codes or []),
    }


def _model_dimension(entity_type: str, fundamental_quality: Mapping[str, Any]) -> dict[str, Any]:
    models = _mapping(fundamental_quality.get("models"))
    if entity_type == "bank":
        names = ("bank_financial_quality",)
        name = "bank_financial_quality"
    else:
        names = ("growth_profitability", "financial_strength", "dupont_roe")
        name = "profitability_and_resilience"
    facts: list[dict[str, Any]] = []
    unavailable: list[str] = []
    for model_name in names:
        model = _mapping(models.get(model_name))
        state = model.get("result_state") or model.get("status")
        if state in {"available", "partial"}:
            facts.append({
                "model": model_name,
                "result_state": state,
                "value": model.get("score_or_value"),
                "input_periods": list(model.get("input_periods") or []),
                "source_path": f"fundamental_quality.models.{model_name}",
            })
        else:
            unavailable.append(f"model_not_available:{model_name}:{state or 'missing'}")
    if facts:
        return _dimension(name, "available", supporting_facts=facts,
                          source_paths=[item["source_path"] for item in facts], warnings=unavailable)
    return _dimension(name, "unavailable", source_paths=[f"fundamental_quality.models.{item}" for item in names],
                      reason_codes=unavailable or ["fundamental_quality_models_missing"])


def _cash_conversion_dimension(evidence: Mapping[str, Any], legacy_quality: Mapping[str, Any]) -> dict[str, Any]:
    metrics = _mapping(evidence.get("metrics"))
    qualified = []
    for metric_name in ("operating_cash_flow_less_net_income", "cash_conversion_ratio"):
        metric = _mapping(metrics.get(metric_name))
        if metric.get("qualification_status") == "qualified":
            qualified.append({"metric": metric_name, "value": metric.get("value"),
                              "source_path": f"fundamental_quality_evidence.metrics.{metric_name}"})
    if qualified:
        return _dimension("earnings_cash_conversion", "available", supporting_facts=qualified,
                          source_paths=[item["source_path"] for item in qualified])
    model = _mapping(_mapping(legacy_quality.get("models")).get("earnings_quality"))
    state = model.get("result_state") or model.get("status")
    if state in {"available", "partial"}:
        return _dimension("earnings_cash_conversion", "available", supporting_facts=[{
            "model": "earnings_quality", "result_state": state, "value": model.get("score_or_value"),
            "source_path": "fundamental_quality.models.earnings_quality",
        }], source_paths=["fundamental_quality.models.earnings_quality"],
        warnings=["qualified_cash_conversion_evidence_not_present_using_existing_canonical_model_only"])
    return _dimension("earnings_cash_conversion", "unavailable",
                      source_paths=["fundamental_quality_evidence", "fundamental_quality.models.earnings_quality"],
                      reason_codes=[f"cash_conversion_unavailable:{state or 'missing'}"])


def _capital_dimension(entity_type: str, capital: Mapping[str, Any]) -> dict[str, Any]:
    if entity_type == "bank":
        return _dimension("capital_structure", "not_applicable",
                          reason_codes=["corporate_capital_structure_ratio_contract_not_applicable_to_bank"])
    metrics = _mapping(capital.get("metrics"))
    accepted = []
    for metric_name in ("net_debt_to_equity", "debt_to_equity", "cash_to_debt"):
        metric = _mapping(metrics.get(metric_name))
        if metric.get("qualification_status") == "qualified":
            accepted.append({"metric": metric_name, "value": metric.get("value"),
                             "source_path": f"historical_capital_structure.metrics.{metric_name}"})
    if accepted:
        return _dimension("capital_structure", "available", supporting_facts=accepted,
                          source_paths=[item["source_path"] for item in accepted])
    return _dimension("capital_structure", "unavailable", source_paths=["historical_capital_structure"],
                      reason_codes=[str(item) for item in (capital.get("blocking_reasons") or [])]
                      or ["qualified_capital_structure_metrics_unavailable"])


def _risks(dimensions: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    cash = _mapping(dimensions.get("earnings_cash_conversion"))
    for fact in cash.get("supporting_facts") or []:
        if isinstance(fact, Mapping) and fact.get("metric") == "operating_cash_flow_less_net_income":
            value = fact.get("value")
            if isinstance(value, (int, float)) and value < 0:
                risks.append({
                    "risk_id": "cash_conversion_below_net_income",
                    "fact": {"metric": fact.get("metric"), "value": value},
                    "inference": "Latest qualified annual operating cash flow was below net income.",
                    "uncertainty": "This is a historical observation, not a future earnings forecast.",
                    "provenance": [fact.get("source_path")],
                    "invalidation_or_mitigation": ["Later qualified period shows durable cash-conversion improvement."],
                })
    capital = _mapping(dimensions.get("capital_structure"))
    for fact in capital.get("supporting_facts") or []:
        if isinstance(fact, Mapping) and fact.get("metric") == "net_debt_to_equity":
            value = fact.get("value")
            if isinstance(value, (int, float)) and value > 0:
                risks.append({
                    "risk_id": "positive_net_debt_observed",
                    "fact": {"metric": fact.get("metric"), "value": value},
                    "inference": "Net debt was positive in the qualified historical capital-structure observation.",
                    "uncertainty": "No leverage threshold or future financing outcome is implied.",
                    "provenance": [fact.get("source_path")],
                    "invalidation_or_mitigation": ["Later qualified capital-structure evidence shows a different position."],
                })
    unavailable = sorted(name for name, dimension in dimensions.items()
                         if _mapping(dimension).get("status") == "unavailable")
    if unavailable:
        risks.append({
            "risk_id": "historical_evidence_coverage_limited",
            "fact": {"unavailable_dimensions": unavailable},
            "inference": "The historical conclusion is bounded by unavailable analytical dimensions.",
            "uncertainty": "Unavailable is not evidence of deterioration or safety.",
            "provenance": [f"quality_assessment.{name}" for name in unavailable],
            "invalidation_or_mitigation": ["New qualified canonical facts make the missing dimension available."],
        })
    if not risks:
        risks.append({
            "risk_id": "historical_conditions_can_change",
            "fact": {"available_dimensions": sorted(name for name, dimension in dimensions.items()
                                                       if _mapping(dimension).get("status") == "available")},
            "inference": "Historical qualified conditions may change in later reporting.",
            "uncertainty": "No future deterioration is asserted.",
            "provenance": ["quality_assessment"],
            "invalidation_or_mitigation": ["Later qualified reporting confirms or contradicts the historical profile."],
        })
    return sorted(risks, key=lambda item: item["risk_id"])


def _catalysts(dimensions: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    available = sorted(name for name, value in dimensions.items()
                       if _mapping(value).get("status") == "available")
    if not available:
        return [{"status": "unavailable", "reason_code": "no_qualified_historical_catalyst_condition",
                 "conditions": [], "provenance": []}]
    return [{
        "status": "available",
        "kind": "evidence_backed_condition",
        "condition": "Qualified historical fundamental dimensions remain internally consistent or improve in later qualified reporting.",
        "depends_on_dimensions": available,
        "provenance": [f"quality_assessment.{name}" for name in available],
        "limitation": "A condition is not a prediction of a future event.",
    }]


def _scenarios(eligible: bool, facts: list[dict[str, Any]], dimensions: Mapping[str, Mapping[str, Any]],
               risks: list[dict[str, Any]], catalysts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    available = sorted(name for name, value in dimensions.items()
                       if _mapping(value).get("status") == "available")
    unavailable = sorted(name for name, value in dimensions.items()
                         if _mapping(value).get("status") == "unavailable")
    base = {
        "status": "available" if eligible else "unavailable",
        "thesis": "Qualified historical fundamentals remain internally consistent.",
        "supporting_facts": facts,
        "required_conditions": ["Qualified reporting continues to support the available historical dimensions."],
        "key_dependencies": available,
        "invalidation_conditions": ["A later qualified fact conflicts with the cited historical inputs.",
                                    "A required available dimension becomes unavailable or conflicted."],
        "missing_evidence": unavailable,
    }
    bear = {
        "status": "available" if eligible else "unavailable",
        "thesis": "Historical fundamental support weakens if the qualified conditions no longer hold.",
        "supporting_facts": facts,
        "required_conditions": ["Historical risk observations persist or new qualified evidence contradicts the available dimensions."],
        "key_dependencies": [risk["risk_id"] for risk in risks],
        "invalidation_conditions": ["Qualified later reporting resolves the identified risk observations."],
        "missing_evidence": unavailable,
    }
    bull = {
        "status": "available" if eligible else "unavailable",
        "thesis": "The historical fundamental profile improves only if later qualified evidence strengthens the available dimensions.",
        "supporting_facts": facts,
        "required_conditions": ["Evidence-backed catalyst conditions are observed in later qualified reporting."],
        "key_dependencies": [item.get("condition") for item in catalysts if item.get("status") == "available"],
        "invalidation_conditions": ["No new qualified reporting supports the required improvement conditions."],
        "missing_evidence": unavailable,
    }
    return {"bear": bear, "base": base, "bull": bull}


def evaluate_historical_decision_analysis(ticker: str, entry: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build one deterministic historical decision-support result from a bundle entry."""
    ticker = str(ticker).upper()
    source = _mapping(entry)
    entity_type = source.get("entity_type")
    financial_canonical = _mapping(source.get("financial_canonical"))
    qualified_facts = _qualified_facts(financial_canonical)
    fundamental_quality = _mapping(source.get("fundamental_quality"))
    quality_evidence = _mapping(source.get("fundamental_quality_evidence"))
    capital = _mapping(source.get("historical_capital_structure"))

    blocking: list[str] = []
    if ticker not in PILOT_TICKERS:
        blocking.append("ticker_not_in_phase_4b_pilot")
    if entity_type not in {"corporate", "bank"}:
        blocking.append("entity_type_not_supported_for_historical_decision_engine")
    if financial_canonical.get("status") != "available":
        blocking.append("canonical_financial_section_not_available")
    if not qualified_facts:
        blocking.append("qualified_canonical_facts_missing")

    model = _model_dimension(str(entity_type), fundamental_quality)
    cash = _cash_conversion_dimension(quality_evidence, fundamental_quality)
    capital_dimension = _capital_dimension(str(entity_type), capital)
    dimensions = {item["dimension"]: item for item in (model, cash, capital_dimension)}
    available_count = sum(item["status"] == "available" for item in dimensions.values())
    if blocking:
        eligibility_status = "blocked" if any(code != "qualified_canonical_facts_missing" for code in blocking) else "insufficient_evidence"
    elif available_count == 0:
        eligibility_status = "partially_eligible"
        blocking.append("qualified_analysis_dimensions_unavailable")
    else:
        eligibility_status = "eligible"

    risks = _risks(dimensions)
    catalysts = _catalysts(dimensions)
    scenarios = _scenarios(eligibility_status == "eligible", qualified_facts, dimensions, risks, catalysts)
    conclusion_status = "historically_mixed" if eligibility_status == "eligible" else "insufficient_evidence"
    conclusion = {
        "status": conclusion_status,
        "rationale": (
            "Qualified historical facts support a bounded multi-dimension review, but no universal score, "
            "future forecast, or market-dependent conclusion is produced."
            if conclusion_status == "historically_mixed" else
            "Required qualified historical inputs are absent, unsupported, or blocked; no directional conclusion is produced."
        ),
        "base_case_requires": scenarios["base"]["required_conditions"],
        "bear_case_triggers": scenarios["bear"]["required_conditions"],
        "missing_evidence": sorted(name for name, item in dimensions.items() if item["status"] == "unavailable"),
    }
    periods = sorted({period for fact in qualified_facts if (period := fact.get("reporting_period"))})
    return {
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "ticker": ticker,
        "analysis_mode": "historical_only_qualified_data",
        "historical_only": True,
        "market_dependent": False,
        "is_actionable": False,
        "data_periods_used": periods,
        "eligibility": {"status": eligibility_status, "reason_codes": _sorted_strings(blocking),
                        "required_qualified_fact_count": 1, "qualified_fact_count": len(qualified_facts)},
        "provenance": {
            "upstream_contracts": [
                {"path": "financial_canonical", "status": financial_canonical.get("status")},
                {"path": "fundamental_quality", "status": fundamental_quality.get("schema_version")},
                {"path": "fundamental_quality_evidence", "status": quality_evidence.get("status")},
                {"path": "historical_capital_structure", "status": capital.get("status")},
            ],
            "qualified_fact_references": qualified_facts,
        },
        "quality_assessment": dimensions,
        "risks": risks,
        "catalysts": catalysts,
        "scenarios": scenarios,
        "invalidation_conditions": _sorted_strings(
            [condition for scenario in scenarios.values() for condition in scenario["invalidation_conditions"]]
        ),
        "historical_conclusion": conclusion,
        "data_warnings": _sorted_strings(
            [f"dimension_unavailable:{name}" for name, item in dimensions.items() if item["status"] == "unavailable"]
        ),
        "missing_evidence": sorted(name for name, item in dimensions.items() if item["status"] == "unavailable"),
        "prohibited_output_boundary": [
            "target_price", "current_valuation", "recommendation", "ranking", "portfolio_sizing",
            "market_dependent_return",
        ],
    }
