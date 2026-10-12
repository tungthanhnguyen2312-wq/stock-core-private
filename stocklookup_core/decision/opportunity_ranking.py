"""Evidence-gated opportunity dimensions and deterministic ordering; never recommendations."""
from __future__ import annotations
from typing import Any, Mapping

VERSION = "1.0.0"
DIMENSIONS = ("financial_quality", "valuation", "technical_current_market_readiness", "catalyst_evidence", "downside_invalidation", "data_confidence")
STATES = frozenset({"available", "limited", "partial", "unavailable", "unknown", "incomparable", "inapplicable", "blocked"})
_STATE_ORDER = {"available": 0, "limited": 1, "partial": 2, "unavailable": 3, "unknown": 4, "blocked": 5, "incomparable": 6, "inapplicable": 7}
_COMPONENT_FIELDS = {"canonical_metric", "derivation_role", "value", "period_identity", "statement_scope", "currency", "unit_scale", "source", "observation_ids", "citation_id", "evidence_id"}


def _dimension(name: str, state: str, *, facts: list[dict[str, Any]] | None = None, warnings: list[str] | None = None, reason: str | None = None) -> dict[str, Any]:
    return {"dimension": name, "state": state, "facts": facts or [], "data_warnings": warnings or [], "reason": reason, "is_actionable": state == "available"}


def _fact_ok(fact: Any) -> bool:
    if not isinstance(fact, Mapping): return False
    lineage = fact.get("component_lineage")
    if lineage is None: return bool(fact.get("citation_id") and fact.get("evidence_id"))
    if not isinstance(lineage, list) or not lineage: return False
    seen: set[tuple[Any, ...]] = set()
    for component in lineage:
        if not isinstance(component, Mapping) or set(component) != _COMPONENT_FIELDS: return False
        if not isinstance(component.get("observation_ids"), list) or not component["observation_ids"]: return False
        if not isinstance(component.get("period_identity"), Mapping): return False
        key = (component["canonical_metric"], tuple(component["observation_ids"]), component["citation_id"], component["evidence_id"])
        if key in seen: return False
        seen.add(key)
    return True


def _financial(entry: Mapping[str, Any], entity_type: str) -> dict[str, Any]:
    quality = entry.get("fundamental_quality") if isinstance(entry.get("fundamental_quality"), Mapping) else {}
    models = quality.get("models") if isinstance(quality.get("models"), Mapping) else {}
    available = []
    for name, model in sorted(models.items()):
        if not isinstance(model, Mapping) or model.get("result_state") != "available": continue
        facts = model.get("used_input_facts")
        if not isinstance(facts, Mapping) or not all(_fact_ok(fact) for fact in facts.values()):
            return _dimension("financial_quality", "incomparable", warnings=["financial_quality_lineage_missing_or_conflicting"])
        available.append({"model": name, "facts": dict(facts)})
    if entity_type == "bank" and any(name != "bank_financial_quality" and isinstance(model, Mapping) and model.get("result_state") == "available" for name, model in models.items()):
        return _dimension("financial_quality", "incomparable", warnings=["corporate_financial_quality_model_available_for_bank"])
    if not available: return _dimension("financial_quality", "unavailable", warnings=["qualified_financial_quality_model_missing"])
    return _dimension("financial_quality", "available", facts=available)


def _valuation(entry: Mapping[str, Any], entity_type: str) -> dict[str, Any]:
    valuation = entry.get("relative_valuation") if isinstance(entry.get("relative_valuation"), Mapping) else {}
    methods = valuation.get("methods") if isinstance(valuation.get("methods"), Mapping) else {}
    if entity_type == "bank" and any(name.startswith("ev_") and isinstance(method, Mapping) and method.get("state") == "available" for name, method in methods.items()):
        return _dimension("valuation", "incomparable", warnings=["enterprise_value_method_available_for_bank"])
    qualified = [{"method": name, "provenance": method.get("provenance", {})} for name, method in sorted(methods.items()) if isinstance(method, Mapping) and method.get("state") == "available" and method.get("is_actionable") is True]
    return _dimension("valuation", "available", facts=qualified) if qualified else _dimension("valuation", "unavailable", warnings=["qualified_actionable_valuation_missing"])


def _technical(entry: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    freshness = entry.get("freshness") if isinstance(entry.get("freshness"), Mapping) else {}
    readiness = entry.get("analysis_readiness") if isinstance(entry.get("analysis_readiness"), Mapping) else {}
    market = freshness.get("daily_prices") if isinstance(freshness.get("daily_prices"), Mapping) else {}
    technical = freshness.get("technical_signals") if isinstance(freshness.get("technical_signals"), Mapping) else {}
    domain = (readiness.get("domains") or {}).get("market_technical") if isinstance(readiness.get("domains"), Mapping) else {}
    signal = entry.get("ta_signal") if isinstance(entry.get("ta_signal"), Mapping) else {}
    above = signal.get("above_sma50")
    ready = market.get("is_actionable") is True and technical.get("is_actionable") is True and domain.get("state") == "ready" and isinstance(above, bool)
    payload = {"above_sma50": above} if isinstance(above, bool) else {}
    if ready: return _dimension("technical_current_market_readiness", "available", facts=[payload]), payload
    return _dimension("technical_current_market_readiness", "unavailable", warnings=["market_technical_not_ready_or_current"]), payload


def _catalyst(entry: Mapping[str, Any]) -> dict[str, Any]:
    ci = entry.get("corporate_intelligence") if isinstance(entry.get("corporate_intelligence"), Mapping) else {}
    events = ci.get("corporate_events") if isinstance(ci.get("corporate_events"), Mapping) else {}
    if events.get("coverage_status") == "complete" and isinstance(events.get("freshness"), Mapping) and events["freshness"].get("is_actionable") is True and isinstance(events.get("records"), list):
        facts = [{"event_id": row.get("event_id"), "source_provenance": row.get("provenance")} for row in events["records"] if isinstance(row, Mapping) and row.get("event_id")]
        return _dimension("catalyst_evidence", "available", facts=facts)
    return _dimension("catalyst_evidence", "unknown", warnings=["qualified_complete_current_catalyst_evidence_missing"])


def _downside(technical: dict[str, Any], signal: dict[str, Any]) -> dict[str, Any]:
    if technical["state"] != "available" or not isinstance(signal.get("above_sma50"), bool):
        return _dimension("downside_invalidation", "unknown", warnings=["technical_invalidation_not_current_or_qualified"])
    return _dimension("downside_invalidation", "available", facts=[{"field": "above_sma50", "value": signal["above_sma50"], "invalidation": "above_sma50 changes state"}])


def evaluate_opportunity(entry: Mapping[str, Any] | None, *, ticker: str, entity_type: str) -> dict[str, Any]:
    source = entry if isinstance(entry, Mapping) else {}
    financial = _financial(source, entity_type)
    valuation = _valuation(source, entity_type)
    technical, signal = _technical(source)
    catalyst = _catalyst(source)
    downside = _downside(technical, signal)
    primary = [financial, valuation, technical, catalyst, downside]
    if any(item["state"] in {"incomparable", "blocked"} for item in primary): confidence = _dimension("data_confidence", "incomparable", warnings=["one_or_more_dimension_conflicting_or_blocked"])
    elif all(item["state"] == "available" for item in primary): confidence = _dimension("data_confidence", "available")
    elif any(item["state"] == "available" for item in primary): confidence = _dimension("data_confidence", "partial", warnings=["one_or_more_required_dimensions_not_qualified"])
    else: confidence = _dimension("data_confidence", "unknown", warnings=["no_qualified_opportunity_dimensions"])
    dimensions = {item["dimension"]: item for item in (financial, valuation, technical, catalyst, downside, confidence)}
    return {"schema_version": VERSION, "ticker": ticker, "entity_type": entity_type, "state": confidence["state"], "dimensions": dimensions, "ranking_key": [_STATE_ORDER[dimensions[name]["state"]] for name in DIMENSIONS] + [ticker], "facts": [fact for item in primary for fact in item["facts"]], "data_warnings": [warning for item in dimensions.values() for warning in item["data_warnings"]], "inferences": [], "hypotheses": [], "interpretation_limits": ["Dimensions are evidence availability states, not a score, recommendation, probability, or target price."]}


def rank_opportunities(entries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    evaluated = {ticker: evaluate_opportunity(entry, ticker=ticker, entity_type=str(entry.get("entity_type") or "unknown")) for ticker, entry in entries.items()}
    ordered = sorted(evaluated.values(), key=lambda item: tuple(item["ranking_key"]))
    return {"schema_version": VERSION, "state": "available" if any(item["state"] in {"available", "partial"} for item in ordered) else "unknown", "ranking_basis": list(DIMENSIONS) + ["ticker"], "ranking_kind": "evidence_availability_ordering_only", "ordered_tickers": [{"ticker": item["ticker"], "state": item["state"], "dimensions": {name: item["dimensions"][name]["state"] for name in DIMENSIONS}} for item in ordered], "is_actionable": False, "interpretation_limits": ["No composite magic score, recommendation, probability, target price, or portfolio sizing."]}
