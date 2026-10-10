"""P3-B deterministic, sector-aware fundamental research-readiness engine.

This engine consumes the authoritative Phase-2 panel only.  It deliberately has
no price, liquidity, valuation, ranking, recommendation, or portfolio inputs.
Every emitted metric is independently applicable, traceable, and fail-closed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from enum import StrEnum
import hashlib
import json
from typing import Any, Callable, Iterable, Mapping


SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "fundamental_research_readiness/v1"
ARTIFACT_TYPE = "PHASE_3_FUNDAMENTAL_RESEARCH_READINESS"
SUPPORTED_ENTITY_CLASSES = frozenset({"corporate", "bank", "securities"})
NON_AUTHORIZED_DOWNSTREAM_USES = (
    "universal_quality_score",
    "cross_sectional_ranking",
    "buy_sell_recommendation",
    "target_price",
    "dcf",
    "peer_multiple_valuation",
    "portfolio_sizing",
    "backtesting",
    "price_or_liquidity_analysis",
)


class MetricStatus(StrEnum):
    EXACT_QUALIFIED = "EXACT_QUALIFIED"
    DERIVED_PROXY = "DERIVED_PROXY"
    MISSING = "MISSING"
    BLOCKED = "BLOCKED"
    CONFLICT = "CONFLICT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def stable_id(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def metric_definition_inventory() -> list[dict[str, Any]]:
    """Versioned inventory; formulas are never inferred from a metric label."""
    definitions = [
        ("revenue_growth_yoy", "growth", ("corporate",), "(revenue_t - revenue_t-1) / abs(revenue_t-1)", "revenue"),
        ("earnings_growth_yoy", "growth", ("corporate", "bank", "securities"), "(earnings_t - earnings_t-1) / abs(earnings_t-1)", "entity-specific parent/total earnings identity"),
        ("operating_cash_flow_growth_yoy", "growth", ("corporate",), "(ocf_t - ocf_t-1) / abs(ocf_t-1)", "operating_cash_flow"),
        ("net_margin", "profitability", ("corporate",), "net_income / revenue", "net_income, revenue"),
        ("return_on_assets", "profitability", ("corporate", "bank", "securities"), "earnings / average assets; ending-assets proxy only when prior balance is absent", "entity-specific earnings, total_assets"),
        ("return_on_equity", "profitability", ("corporate", "bank", "securities"), "earnings / average equity; ending-equity proxy only when prior balance is absent", "entity-specific earnings, entity-specific equity"),
        ("debt_to_equity", "balance_sheet", ("corporate",), "total_interest_bearing_debt / shareholders_equity", "total_interest_bearing_debt, shareholders_equity"),
        ("net_debt", "balance_sheet", ("corporate",), "total_interest_bearing_debt - cash_and_equivalents", "total_interest_bearing_debt, cash_and_equivalents"),
        ("cash_flow_to_earnings", "cashflow", ("corporate",), "operating_cash_flow / net_income", "operating_cash_flow, net_income"),
        ("cash_flow_minus_earnings", "cashflow", ("corporate",), "operating_cash_flow - net_income", "operating_cash_flow, net_income"),
        ("loan_to_deposit_ratio", "balance_sheet", ("bank",), "customer_loans_net / customer_deposits", "customer_loans_net, customer_deposits"),
        ("credit_cost_to_loans", "profitability", ("bank",), "provision_for_credit_losses / customer_loans_net", "provision_for_credit_losses, customer_loans_net"),
        ("fvtpl_assets_to_total_assets", "balance_sheet", ("securities",), "financial_assets_fvtpl / total_assets", "financial_assets_fvtpl, total_assets"),
        ("margin_loans_to_total_assets", "balance_sheet", ("securities",), "loans_balance / total_assets", "loans_balance, total_assets"),
    ]
    return [
        {"metric_id": metric, "family": family, "applicable_entity_classes": list(classes),
         "formula_or_method": formula, "required_canonical_metrics": required,
         "contract_version": CONTRACT_VERSION}
        for metric, family, classes, formula, required in definitions
    ]


def _fact_id(fact: Mapping[str, Any]) -> str:
    temporal = fact.get("temporal_envelope") if isinstance(fact.get("temporal_envelope"), Mapping) else {}
    return str(temporal.get("field_id") or stable_id({
        "issuer": fact.get("issuer_identity"), "metric": fact.get("canonical_metric"),
        "period": fact.get("reporting_period"), "scope": fact.get("statement_scope"),
        "currency": fact.get("currency"), "lineage": fact.get("source_lineage"),
    }))


def _lineage(fact: Mapping[str, Any]) -> dict[str, Any]:
    source = fact.get("source_lineage") if isinstance(fact.get("source_lineage"), Mapping) else {}
    return {
        "input_fact_id": _fact_id(fact), "canonical_metric": fact.get("canonical_metric"),
        "reporting_period": fact.get("reporting_period"), "statement_scope": fact.get("statement_scope"),
        "currency": fact.get("currency"), "unit_scale": fact.get("unit_scale"),
        "citation_id": source.get("citation_id"), "evidence_id": source.get("evidence_id"),
        "document_sha256": source.get("document_sha256"), "source_page": source.get("source_page"),
        "authority_tier": source.get("authority_tier"), "reconciliation_status": source.get("reconciliation_status"),
        "point_in_time_eligibility": (fact.get("temporal_envelope") or {}).get("pit_status"),
    }


def _positive_authoritative(fact: Mapping[str, Any]) -> bool:
    temporal = fact.get("temporal_envelope") if isinstance(fact.get("temporal_envelope"), Mapping) else {}
    return bool(
        fact.get("qualification_state") == "QUALIFIED"
        and fact.get("is_positive_authority") is True
        and fact.get("value") is not None
        and temporal.get("pit_eligible") is True
    )


def _base_result(metric_id: str, entity_class: str, periods: Iterable[str] = ()) -> dict[str, Any]:
    return {
        "metric_id": metric_id, "value": None, "method": None, "status": MetricStatus.BLOCKED.value,
        "entity_class": entity_class, "periods_used": sorted(set(str(p) for p in periods)),
        "statement_scope": None, "currency": None, "input_fact_ids": [], "evidence_lineage": [],
        "warnings": [], "blocked_reason": None, "point_in_time_eligibility": "NOT_ELIGIBLE",
    }


def _not_applicable(metric_id: str, entity_class: str, reason: str) -> dict[str, Any]:
    result = _base_result(metric_id, entity_class)
    result.update({"status": MetricStatus.NOT_APPLICABLE.value, "blocked_reason": reason,
                   "point_in_time_eligibility": "NOT_APPLICABLE"})
    return result


def _blocked(metric_id: str, entity_class: str, reason: str, periods: Iterable[str] = ()) -> dict[str, Any]:
    result = _base_result(metric_id, entity_class, periods)
    result.update({"status": MetricStatus.MISSING.value if reason.startswith("MISSING_") else MetricStatus.BLOCKED.value,
                   "blocked_reason": reason})
    return result


def _complete(metric_id: str, entity_class: str, facts: list[Mapping[str, Any]], value: float,
              method: str, status: MetricStatus = MetricStatus.EXACT_QUALIFIED,
              warnings: Iterable[str] = ()) -> dict[str, Any]:
    result = _base_result(metric_id, entity_class, (fact.get("reporting_period") for fact in facts))
    ordered = sorted(facts, key=lambda f: (_fact_id(f), str(f.get("canonical_metric"))))
    result.update({
        "value": round(float(value), 8), "method": method, "status": status.value,
        "statement_scope": ordered[0].get("statement_scope"), "currency": ordered[0].get("currency"),
        "input_fact_ids": [_fact_id(fact) for fact in ordered], "evidence_lineage": [_lineage(fact) for fact in ordered],
        "warnings": sorted(set(warnings)), "point_in_time_eligibility": "QUALIFIED",
    })
    return result


def _fact_index(issuer: Mapping[str, Any]) -> tuple[dict[tuple[str, str], list[Mapping[str, Any]]], set[tuple[str, str]]]:
    indexed: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    conflicts: set[tuple[str, str]] = set()
    for fact in issuer.get("facts", []):
        if not isinstance(fact, Mapping):
            continue
        metric, period = fact.get("canonical_metric"), fact.get("reporting_period")
        if not metric or not period:
            continue
        key = (str(metric), str(period))
        if fact.get("qualification_state") == "CONFLICT":
            conflicts.add(key)
        elif _positive_authoritative(fact):
            indexed[key].append(fact)
    for key, facts in indexed.items():
        signatures = {(f.get("value"), f.get("statement_scope"), f.get("currency"), f.get("unit_scale")) for f in facts}
        if len(signatures) != 1:
            conflicts.add(key)
    return indexed, conflicts


def _choose_same_dimension(metric_id: str, entity_class: str, period: str, index: Mapping[tuple[str, str], list[Mapping[str, Any]]],
                           conflicts: set[tuple[str, str]], required: tuple[str, ...]) -> tuple[list[Mapping[str, Any]] | None, dict[str, Any] | None]:
    keys = [(name, period) for name in required]
    if any(key in conflicts for key in keys):
        return None, _blocked(metric_id, entity_class, "CONFLICT_INPUT_FACT", (period,)) | {"status": MetricStatus.CONFLICT.value}
    if any(not index.get(key) for key in keys):
        return None, _blocked(metric_id, entity_class, "MISSING_INPUTS:" + ",".join(name for name, key in zip(required, keys) if not index.get(key)), (period,))
    facts = [index[key][0] for key in keys]
    scopes = {fact.get("statement_scope") for fact in facts}
    currencies = {fact.get("currency") for fact in facts}
    scales = {fact.get("unit_scale") for fact in facts}
    if len(scopes) != 1 or len(currencies) != 1 or len(scales) != 1:
        return None, _blocked(metric_id, entity_class, "SCOPE_CURRENCY_OR_SCALE_MISMATCH", (period,))
    return facts, None


def _ratio(metric_id: str, entity_class: str, period: str, index: Mapping[tuple[str, str], list[Mapping[str, Any]]],
           conflicts: set[tuple[str, str]], numerator: str, denominator: str, method: str) -> dict[str, Any]:
    facts, error = _choose_same_dimension(metric_id, entity_class, period, index, conflicts, (numerator, denominator))
    if error:
        return error
    assert facts is not None
    denominator_value = float(facts[1]["value"])
    if denominator_value == 0:
        return _blocked(metric_id, entity_class, "ZERO_DENOMINATOR", (period,))
    return _complete(metric_id, entity_class, facts, float(facts[0]["value"]) / denominator_value, method)


def _growth(metric_id: str, entity_class: str, period: str, prior: str, index: Mapping[tuple[str, str], list[Mapping[str, Any]]],
            conflicts: set[tuple[str, str]], canonical_metric: str) -> dict[str, Any]:
    current, error = _choose_same_dimension(metric_id, entity_class, period, index, conflicts, (canonical_metric,))
    if error:
        return error
    previous, previous_error = _choose_same_dimension(metric_id, entity_class, prior, index, conflicts, (canonical_metric,))
    if previous_error:
        previous_error["periods_used"] = [prior, period]
        return previous_error
    assert current is not None and previous is not None
    facts = [current[0], previous[0]]
    if (facts[0].get("statement_scope"), facts[0].get("currency"), facts[0].get("unit_scale")) != (facts[1].get("statement_scope"), facts[1].get("currency"), facts[1].get("unit_scale")):
        return _blocked(metric_id, entity_class, "SCOPE_CURRENCY_OR_SCALE_MISMATCH_ACROSS_PERIODS", (prior, period))
    prior_value = float(facts[1]["value"])
    if prior_value == 0:
        return _blocked(metric_id, entity_class, "ZERO_PRIOR_PERIOD_VALUE", (prior, period))
    return _complete(metric_id, entity_class, facts, (float(facts[0]["value"]) - prior_value) / abs(prior_value),
                     "YOY_GROWTH=(current-prior)/abs(prior)")


def _return_metric(metric_id: str, entity_class: str, period: str, prior: str | None,
                   index: Mapping[tuple[str, str], list[Mapping[str, Any]]], conflicts: set[tuple[str, str]],
                   earnings_metric: str, balance_metric: str) -> dict[str, Any]:
    current, error = _choose_same_dimension(metric_id, entity_class, period, index, conflicts, (earnings_metric, balance_metric))
    if error:
        return error
    assert current is not None
    earnings, ending = current
    if prior is not None:
        previous, previous_error = _choose_same_dimension(metric_id, entity_class, prior, index, conflicts, (balance_metric,))
        if previous_error is None:
            assert previous is not None
            prior_balance = previous[0]
            if (ending.get("statement_scope"), ending.get("currency"), ending.get("unit_scale")) == (prior_balance.get("statement_scope"), prior_balance.get("currency"), prior_balance.get("unit_scale")):
                denom = (float(ending["value"]) + float(prior_balance["value"])) / 2
                if denom != 0:
                    return _complete(metric_id, entity_class, [earnings, ending, prior_balance], float(earnings["value"]) / denom,
                                     "AVERAGE_DENOMINATOR=(ending_balance+prior_ending_balance)/2")
    denom = float(ending["value"])
    if denom == 0:
        return _blocked(metric_id, entity_class, "ZERO_ENDING_BALANCE_DENOMINATOR", (period,))
    return _complete(metric_id, entity_class, [earnings, ending], float(earnings["value"]) / denom,
                     "ENDING_BALANCE_PROXY=earnings/ending_balance", MetricStatus.DERIVED_PROXY,
                     ("AVERAGE_DENOMINATOR_NOT_AVAILABLE; ending-balance result is a proxy, not equivalent ROA/ROE",))


def _periods(index: Mapping[tuple[str, str], list[Mapping[str, Any]]]) -> list[str]:
    return sorted({period for _, period in index})


def _earnings_metric(entity_class: str) -> str:
    return {"corporate": "net_income", "bank": "net_profit_parent", "securities": "profit_after_tax_parent"}[entity_class]


def _equity_metric(entity_class: str) -> str:
    return "shareholders_equity" if entity_class == "corporate" else "total_equity"


def evaluate_issuer_fundamental_research(issuer: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a single Phase-2 issuer panel without reading any runtime data."""
    identity = issuer.get("issuer_identity") if isinstance(issuer.get("issuer_identity"), Mapping) else {}
    ticker, entity_class = str(identity.get("ticker") or "UNKNOWN"), str(identity.get("entity_type") or "unknown")
    index, conflicts = _fact_index(issuer)
    periods = _periods(index)
    metrics: list[dict[str, Any]] = []
    all_definitions = metric_definition_inventory()
    if entity_class not in SUPPORTED_ENTITY_CLASSES:
        for definition in all_definitions:
            metrics.append(_not_applicable(definition["metric_id"], entity_class, "ENTITY_CLASS_UNPROMOTED_OR_UNSUPPORTED"))
    else:
        for period_index, period in enumerate(periods):
            prior = periods[period_index - 1] if period_index > 0 and int(period[:4]) == int(periods[period_index - 1][:4]) + 1 else None
            if entity_class == "corporate":
                metrics.extend([
                    _growth("revenue_growth_yoy", entity_class, period, prior, index, conflicts, "revenue") if prior else _blocked("revenue_growth_yoy", entity_class, "MISSING_CONSECUTIVE_PRIOR_PERIOD", (period,)),
                    _growth("earnings_growth_yoy", entity_class, period, prior, index, conflicts, "net_income") if prior else _blocked("earnings_growth_yoy", entity_class, "MISSING_CONSECUTIVE_PRIOR_PERIOD", (period,)),
                    _growth("operating_cash_flow_growth_yoy", entity_class, period, prior, index, conflicts, "operating_cash_flow") if prior else _blocked("operating_cash_flow_growth_yoy", entity_class, "MISSING_CONSECUTIVE_PRIOR_PERIOD", (period,)),
                    _ratio("net_margin", entity_class, period, index, conflicts, "net_income", "revenue", "NET_MARGIN=net_income/revenue"),
                    _return_metric("return_on_assets", entity_class, period, prior, index, conflicts, "net_income", "total_assets"),
                    _return_metric("return_on_equity", entity_class, period, prior, index, conflicts, "net_income", "shareholders_equity"),
                    _ratio("debt_to_equity", entity_class, period, index, conflicts, "total_interest_bearing_debt", "shareholders_equity", "DEBT_TO_EQUITY=interest_bearing_debt/equity"),
                    _net_debt(entity_class, period, index, conflicts),
                    _ratio("cash_flow_to_earnings", entity_class, period, index, conflicts, "operating_cash_flow", "net_income", "CFO_TO_EARNINGS=operating_cash_flow/net_income"),
                    _difference("cash_flow_minus_earnings", entity_class, period, index, conflicts, "operating_cash_flow", "net_income", "CFO_MINUS_EARNINGS=operating_cash_flow-net_income"),
                ])
            elif entity_class == "bank":
                metrics.extend([
                    _growth("earnings_growth_yoy", entity_class, period, prior, index, conflicts, "net_profit_parent") if prior else _blocked("earnings_growth_yoy", entity_class, "MISSING_CONSECUTIVE_PRIOR_PERIOD", (period,)),
                    _return_metric("return_on_assets", entity_class, period, prior, index, conflicts, "net_profit_parent", "total_assets"),
                    _return_metric("return_on_equity", entity_class, period, prior, index, conflicts, "net_profit_parent", "total_equity"),
                    _ratio("loan_to_deposit_ratio", entity_class, period, index, conflicts, "customer_loans_net", "customer_deposits", "LOAN_TO_DEPOSIT=customer_loans_net/customer_deposits"),
                    _ratio("credit_cost_to_loans", entity_class, period, index, conflicts, "provision_for_credit_losses", "customer_loans_net", "CREDIT_COST_TO_LOANS=provision_for_credit_losses/customer_loans_net"),
                    _not_applicable("debt_to_equity", entity_class, "CORPORATE_DEBT_SEMANTICS_NOT_APPLICABLE_TO_BANK"),
                    _not_applicable("net_debt", entity_class, "CORPORATE_DEBT_SEMANTICS_NOT_APPLICABLE_TO_BANK"),
                    _not_applicable("cash_flow_to_earnings", entity_class, "CORPORATE_CASHFLOW_MODEL_NOT_PROMOTED_FOR_BANK"),
                ])
            else:
                metrics.extend([
                    _growth("earnings_growth_yoy", entity_class, period, prior, index, conflicts, "profit_after_tax_parent") if prior else _blocked("earnings_growth_yoy", entity_class, "MISSING_CONSECUTIVE_PRIOR_PERIOD", (period,)),
                    _return_metric("return_on_assets", entity_class, period, prior, index, conflicts, "profit_after_tax_parent", "total_assets"),
                    _return_metric("return_on_equity", entity_class, period, prior, index, conflicts, "profit_after_tax_parent", "total_equity"),
                    _ratio("fvtpl_assets_to_total_assets", entity_class, period, index, conflicts, "financial_assets_fvtpl", "total_assets", "FVTPL_ASSETS_TO_TOTAL_ASSETS=financial_assets_fvtpl/total_assets"),
                    _ratio("margin_loans_to_total_assets", entity_class, period, index, conflicts, "loans_balance", "total_assets", "MARGIN_LOANS_TO_TOTAL_ASSETS=loans_balance/total_assets"),
                    _not_applicable("debt_to_equity", entity_class, "CORPORATE_DEBT_SEMANTICS_NOT_APPLICABLE_TO_SECURITIES"),
                    _not_applicable("net_debt", entity_class, "CORPORATE_DEBT_SEMANTICS_NOT_APPLICABLE_TO_SECURITIES"),
                    _not_applicable("cash_flow_to_earnings", entity_class, "CORPORATE_CASHFLOW_MODEL_NOT_PROMOTED_FOR_SECURITIES"),
                ])
    metrics.sort(key=lambda item: (item["metric_id"], item["periods_used"], item["method"] or ""))
    family_states = _family_states(metrics)
    history = _history_readiness(issuer, periods, metrics)
    available = sum(metric["status"] in {MetricStatus.EXACT_QUALIFIED.value, MetricStatus.DERIVED_PROXY.value} for metric in metrics)
    blocked = sum(metric["status"] in {MetricStatus.MISSING.value, MetricStatus.BLOCKED.value, MetricStatus.CONFLICT.value} for metric in metrics)
    readiness = "READY" if available and not blocked else "PARTIAL" if available else "BLOCKED"
    return {
        "issuer_identity": {"ticker": ticker, "entity_class": entity_class}, "authoritative_periods_available": periods,
        "metrics": metrics, "metric_family_states": family_states, "history_readiness": history,
        "fundamental_research_readiness": readiness,
        "evidence_completeness": {"positive_authoritative_fact_count": sum(len(v) for v in index.values()),
                                    "conflict_fact_keys": ["%s:%s" % key for key in sorted(conflicts)],
                                    "all_metric_lineage_present": all(bool(metric["evidence_lineage"]) for metric in metrics if metric["status"] in {MetricStatus.EXACT_QUALIFIED.value, MetricStatus.DERIVED_PROXY.value})},
        "warnings": ["FUNDAMENTAL_RESEARCH_ONLY", "NO_PRICE_LIQUIDITY_VALUATION_RANKING_OR_PORTFOLIO_AUTHORITY"],
    }


def _net_debt(entity_class: str, period: str, index: Mapping[tuple[str, str], list[Mapping[str, Any]]], conflicts: set[tuple[str, str]]) -> dict[str, Any]:
    facts, error = _choose_same_dimension("net_debt", entity_class, period, index, conflicts, ("total_interest_bearing_debt", "cash_and_equivalents"))
    if error:
        return error
    assert facts is not None
    return _complete("net_debt", entity_class, facts, float(facts[0]["value"]) - float(facts[1]["value"]), "NET_DEBT=interest_bearing_debt-cash_and_equivalents")


def _difference(metric_id: str, entity_class: str, period: str, index: Mapping[tuple[str, str], list[Mapping[str, Any]]], conflicts: set[tuple[str, str]], first: str, second: str, method: str) -> dict[str, Any]:
    facts, error = _choose_same_dimension(metric_id, entity_class, period, index, conflicts, (first, second))
    if error:
        return error
    assert facts is not None
    return _complete(metric_id, entity_class, facts, float(facts[0]["value"]) - float(facts[1]["value"]), method)


def _family_states(metrics: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    inventory = {item["metric_id"]: item["family"] for item in metric_definition_inventory()}
    groups: dict[str, list[str]] = defaultdict(list)
    for metric in metrics:
        family = inventory.get(str(metric["metric_id"]), "stability")
        groups[family].append(str(metric["status"]))
    result = {}
    available_statuses = {MetricStatus.EXACT_QUALIFIED.value, MetricStatus.DERIVED_PROXY.value}
    for family, statuses in sorted(groups.items()):
        if all(status == MetricStatus.NOT_APPLICABLE.value for status in statuses):
            state = "NOT_APPLICABLE"
        elif any(status in available_statuses for status in statuses):
            state = "AVAILABLE" if all(status in available_statuses | {MetricStatus.NOT_APPLICABLE.value} for status in statuses) else "PARTIAL"
        else:
            state = "BLOCKED"
        result[family] = f"{family.upper()}_{state}"
    return result


def _history_readiness(issuer: Mapping[str, Any], periods: list[str], metrics: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    years = sorted({int(period[:4]) for period in periods if period[:4].isdigit()})
    expected = set(range(min(years), max(years) + 1)) if years else set()
    scopes = sorted({str(fact.get("statement_scope")) for fact in issuer.get("facts", []) if _positive_authoritative(fact)})
    currencies = sorted({str(fact.get("currency")) for fact in issuer.get("facts", []) if _positive_authoritative(fact)})
    pit = [fact for fact in issuer.get("facts", []) if isinstance(fact, Mapping) and _positive_authoritative(fact)]
    return {"compatible_annual_period_count": len(years), "periods": [str(year) for year in years],
            "gaps": [str(year) for year in sorted(expected - set(years))], "statement_scope_continuity": len(scopes) == 1,
            "statement_scopes": scopes, "currency_continuity": len(currencies) == 1, "currencies": currencies,
            "point_in_time_eligible_fact_count": len(pit), "point_in_time_status": "QUALIFIED" if pit else "BLOCKED",
            "multi_period_growth_available": any(metric["metric_id"].endswith("growth_yoy") and metric["status"] == MetricStatus.EXACT_QUALIFIED.value for metric in metrics)}


def build_fundamental_research_artifact(panel_or_closeout: Mapping[str, Any]) -> dict[str, Any]:
    """Build a fully deterministic artifact from a Phase-2 panel or its closeout wrapper."""
    panel = panel_or_closeout.get("panel_data") if isinstance(panel_or_closeout.get("panel_data"), Mapping) else panel_or_closeout
    issuers = panel.get("issuers") if isinstance(panel, Mapping) else None
    if not isinstance(issuers, list):
        raise ValueError("authoritative Phase-2 panel_data.issuers is required")
    issuer_results = [evaluate_issuer_fundamental_research(issuer) for issuer in issuers if isinstance(issuer, Mapping)]
    issuer_results.sort(key=lambda item: item["issuer_identity"]["ticker"])
    payload = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION, "artifact_type": ARTIFACT_TYPE,
        "cohort_identity": {"source_panel_artifact_id": panel.get("artifact_id"), "source_panel_content_hash": panel.get("content_hash"),
                            "issuers": [item["issuer_identity"]["ticker"] for item in issuer_results],
                            "entity_class_distribution": panel.get("entity_class_distribution")},
        "metric_definition_inventory": metric_definition_inventory(), "issuer_research_readiness": issuer_results,
        "non_authorized_downstream_uses": list(NON_AUTHORIZED_DOWNSTREAM_USES),
        "governance": {"price_liquidity_dependency": False, "universal_composite_score_produced": False,
                       "cross_sectional_ranking_produced": False, "valuation_produced": False},
    }
    payload["coverage_summary"] = _coverage_summary(issuer_results)
    payload["calculation_traces"] = [
        {"ticker": result["issuer_identity"]["ticker"], "metric": metric}
        for result in issuer_results for metric in result["metrics"]
        if metric["status"] in {MetricStatus.EXACT_QUALIFIED.value, MetricStatus.DERIVED_PROXY.value}
    ]
    payload["blocked_not_applicable_matrix"] = [
        {"ticker": result["issuer_identity"]["ticker"], "metric_id": metric["metric_id"],
         "periods_used": metric["periods_used"], "status": metric["status"], "blocked_reason": metric["blocked_reason"]}
        for result in issuer_results for metric in result["metrics"]
        if metric["status"] in {MetricStatus.MISSING.value, MetricStatus.BLOCKED.value,
                                MetricStatus.CONFLICT.value, MetricStatus.NOT_APPLICABLE.value}
    ]
    payload["data_gap_matrix"] = [
        {"ticker": row["ticker"], "metric_id": row["metric_id"], "periods_used": row["periods_used"],
         "missing_or_blocked_reason": row["blocked_reason"]}
        for row in payload["blocked_not_applicable_matrix"]
        if row["status"] in {MetricStatus.MISSING.value, MetricStatus.BLOCKED.value, MetricStatus.CONFLICT.value}
    ]
    qualified = [trace["metric"] for trace in payload["calculation_traces"]]
    payload["lineage_completeness"] = {
        "positive_metric_count": len(qualified),
        "positive_metrics_with_input_fact_ids": sum(bool(metric["input_fact_ids"]) for metric in qualified),
        "positive_metrics_with_evidence_lineage": sum(bool(metric["evidence_lineage"]) for metric in qualified),
    }
    artifact_hash = stable_id(payload)
    payload["artifact_sha256"] = artifact_hash
    payload["artifact_identity"] = f"p3b_fundamental_research_readiness:{artifact_hash}"
    return payload


def _coverage_summary(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"by_entity_class": {}, "metric_status_counts": dict(Counter()), "issuer_metric_family_coverage": []}
    counter: Counter[str] = Counter()
    for result in results:
        entity = result["issuer_identity"]["entity_class"]
        summary["by_entity_class"].setdefault(entity, {"issuer_count": 0, "readiness": Counter()})
        summary["by_entity_class"][entity]["issuer_count"] += 1
        summary["by_entity_class"][entity]["readiness"][result["fundamental_research_readiness"]] += 1
        counter.update(metric["status"] for metric in result["metrics"])
        summary["issuer_metric_family_coverage"].append({"ticker": result["issuer_identity"]["ticker"], "entity_class": entity,
                                                           "family_states": result["metric_family_states"]})
    for entry in summary["by_entity_class"].values():
        entry["readiness"] = dict(sorted(entry["readiness"].items()))
    summary["metric_status_counts"] = dict(sorted(counter.items()))
    return summary
