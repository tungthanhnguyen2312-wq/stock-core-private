"""Current-research financial momentum context over retained fundamental evidence.

This is a descriptive projection of already-qualified official metrics and already-emitted
provider-series trends.  It does not acquire facts, mix official and provider values, annualize
partial periods, or change strategy eligibility, research_priority, or entry_action.

Existing ``fundamental_trajectory_context`` remains the QoQ alignment envelope used by
``FUNDAMENTAL_IMPROVEMENT``.  This sibling adds comparable-period momentum state, component
coverage, and an explicit operational-versus-price contrast.  It does not replace trajectory.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from typing import Any, Mapping, Sequence

import current_official_market_universe as official_universe_module
from market_wide_current_descriptive_research import content_identity as descriptive_content_identity
from market_wide_current_fundamental_research import (
    BLOCKED_TIER,
    OFFICIAL_TIER,
    PROVIDER_TIER,
    content_identity as fundamental_content_identity,
)
from market_wide_current_valuation_input_scaleout import official_research_universe_tickers


CONTRACT_VERSION = "current_financial_momentum_context/v1"
ARTIFACT_TYPE = "CURRENT_FINANCIAL_MOMENTUM_CONTEXT"
MILESTONE = "CURRENT_FINANCIAL_MOMENTUM_CONTEXT_V1"

BROAD_IMPROVEMENT = "BROAD_IMPROVEMENT"
EARNINGS_IMPROVING = "EARNINGS_IMPROVING"
MIXED = "MIXED"
DETERIORATING = "DETERIORATING"
LOSS_MAKING_OR_STRESSED = "LOSS_MAKING_OR_STRESSED"
INSUFFICIENT_COMPARABLE_DATA = "INSUFFICIENT_COMPARABLE_DATA"
NOT_APPLICABLE = "NOT_APPLICABLE"
MOMENTUM_STATES = (
    BROAD_IMPROVEMENT, EARNINGS_IMPROVING, MIXED, DETERIORATING,
    LOSS_MAKING_OR_STRESSED, INSUFFICIENT_COMPARABLE_DATA, NOT_APPLICABLE,
)

COVERAGE_FULL = "FULL"
COVERAGE_PARTIAL = "PARTIAL"
COVERAGE_INSUFFICIENT = "INSUFFICIENT"
COVERAGE_NOT_APPLICABLE = "NOT_APPLICABLE"

CORPORATE_COMPONENTS = ("revenue_growth", "earnings_growth", "net_margin_change", "operating_cash_flow")
BANK_SECURITIES_COMPONENTS = ("earnings_growth",)
INDUSTRIAL_COMPONENTS = frozenset({"revenue_growth", "net_margin_change"})
EXPANDING = frozenset({"EXPANDING", "IMPROVING", "INCREASED"})
CONTRACTING = frozenset({"CONTRACTING", "DETERIORATING", "DECREASED"})

FORBIDDEN_USES = (
    "cheapness", "VALUE", "target_price", "forecast", "probability",
    "strategy_eligibility", "research_priority", "entry_action",
    "recommendation", "sizing", "dcf", "earnings_surprise",
)


class CurrentFinancialMomentumContextError(ValueError):
    """A retained input did not meet this context's exact research contract."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact))
    payload.pop("artifact_sha256", None)
    payload.pop("artifact_identity", None)
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"current_financial_momentum_context:{digest}"}


def replay(artifact: Mapping[str, Any]) -> dict[str, str]:
    identity = content_identity(artifact)
    if identity["artifact_sha256"] != artifact.get("artifact_sha256"):
        raise CurrentFinancialMomentumContextError("MOMENTUM_CONTEXT_IDENTITY_MISMATCH")
    return identity


def _verify_official_universe(artifact: Mapping[str, Any]) -> list[str]:
    try:
        official_universe_module._verify(artifact, "CURRENT_OFFICIAL_MARKET_UNIVERSE")
    except Exception as exc:
        raise CurrentFinancialMomentumContextError("CURRENT_OFFICIAL_UNIVERSE_IDENTITY_MISMATCH") from exc
    tickers = official_research_universe_tickers(artifact)
    if not tickers:
        raise CurrentFinancialMomentumContextError("OFFICIAL_RESEARCH_UNIVERSE_EMPTY")
    return tickers


def _verify_fundamental(artifact: Mapping[str, Any]) -> None:
    if artifact.get("contract_version") != "market_wide_current_fundamental_research/v1":
        raise CurrentFinancialMomentumContextError("CURRENT_FUNDAMENTAL_CONTRACT_UNSUPPORTED")
    recomputed = fundamental_content_identity(artifact)
    if recomputed.get("artifact_sha256") != artifact.get("artifact_sha256"):
        raise CurrentFinancialMomentumContextError("CURRENT_FUNDAMENTAL_IDENTITY_MISMATCH")


def _verify_descriptive(artifact: Mapping[str, Any] | None) -> None:
    if artifact is None:
        return
    if artifact.get("contract_version") != "market_wide_current_descriptive_research/v1":
        raise CurrentFinancialMomentumContextError("CURRENT_DESCRIPTIVE_CONTRACT_UNSUPPORTED")
    if artifact.get("artifact_sha256") != descriptive_content_identity(artifact)["artifact_sha256"]:
        raise CurrentFinancialMomentumContextError("CURRENT_DESCRIPTIVE_IDENTITY_MISMATCH")


def _period_kind(period: Any) -> str | None:
    text = str(period or "")
    if len(text) == 4 and text.isdigit():
        return "FY"
    if len(text) == 7 and text[4:6] == "-Q" and text[6] in "1234" and text[:4].isdigit():
        return "QUARTER"
    return None


def _period_sort_key(period: Any) -> tuple[int, int]:
    kind = _period_kind(period)
    text = str(period or "")
    if kind == "FY":
        return int(text), 0
    if kind == "QUARTER":
        return int(text[:4]), int(text[6])
    return -1, -1


def _growth_direction(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if value > 0:
        return "EXPANDING"
    if value < 0:
        return "CONTRACTING"
    return "UNCHANGED"


def _empty_component(component_id: str, *, status: str, reason: str | None,
                     authority_tier: str | None = None, warnings: Sequence[str] = ()) -> dict[str, Any]:
    return {
        "component_id": component_id,
        "status": status,
        "authority_tier": authority_tier,
        "comparison_type": None,
        "current_value": None,
        "comparison_value": None,
        "change": None,
        "direction": None,
        "periods": [],
        "lineage": [],
        "blocked_reason": reason,
        "warnings": list(warnings),
    }


def _applicable_components(entity_class: str) -> tuple[str, ...]:
    if entity_class == "corporate":
        return CORPORATE_COMPONENTS
    if entity_class in {"bank", "securities"}:
        return BANK_SECURITIES_COMPONENTS
    return ()


def _latest_official_metric(metrics: Sequence[Mapping[str, Any]], metric_id: str) -> Mapping[str, Any] | None:
    rows = [
        row for row in metrics
        if row.get("metric_id") == metric_id and row.get("status") == "EXACT_QUALIFIED"
        and isinstance(row.get("value"), (int, float)) and not isinstance(row.get("value"), bool)
    ]
    if not rows:
        return None
    return max(rows, key=lambda row: _period_sort_key((row.get("periods_used") or [""])[-1]))


def _official_level_pair(metrics: Sequence[Mapping[str, Any]], metric_id: str) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    rows = [
        row for row in metrics
        if row.get("metric_id") == metric_id and row.get("status") == "EXACT_QUALIFIED"
        and isinstance(row.get("value"), (int, float)) and not isinstance(row.get("value"), bool)
        and len(row.get("periods_used") or []) == 1
    ]
    rows.sort(key=lambda row: _period_sort_key((row.get("periods_used") or [""])[0]))
    if len(rows) < 2:
        return None
    previous, current = rows[-2], rows[-1]
    if _period_kind((previous.get("periods_used") or [None])[0]) != _period_kind((current.get("periods_used") or [None])[0]):
        return None
    if (previous.get("statement_scope"), previous.get("currency")) != (current.get("statement_scope"), current.get("currency")):
        return None
    return previous, current


def _official_growth_component(metrics: Sequence[Mapping[str, Any]], *, component_id: str,
                               metric_id: str, entity_class: str) -> dict[str, Any]:
    if component_id in INDUSTRIAL_COMPONENTS and entity_class in {"bank", "securities"}:
        return _empty_component(component_id, status="NOT_APPLICABLE",
                                reason="INDUSTRIAL_METRIC_NOT_APPLICABLE_TO_ENTITY_CLASS",
                                authority_tier=OFFICIAL_TIER)
    row = _latest_official_metric(metrics, metric_id)
    if row is None:
        blocked = next((item for item in metrics if item.get("metric_id") == metric_id and item.get("blocked_reason")), None)
        return _empty_component(
            component_id, status="UNAVAILABLE",
            reason=(blocked or {}).get("blocked_reason") or "NO_EXACT_OFFICIAL_COMPARABLE_GROWTH",
            authority_tier=OFFICIAL_TIER,
        )
    periods = list(row.get("periods_used") or [])
    kinds = {_period_kind(period) for period in periods}
    if len(periods) != 2 or kinds != {"FY"}:
        return _empty_component(component_id, status="BLOCKED",
                                reason="OFFICIAL_GROWTH_PERIODS_NOT_FY_YOY_PAIR",
                                authority_tier=OFFICIAL_TIER, warnings=list(row.get("warnings") or []))
    if row.get("statement_scope") in {None, ""}:
        return _empty_component(component_id, status="BLOCKED",
                                reason="STATEMENT_SCOPE_UNKNOWN", authority_tier=OFFICIAL_TIER)
    direction = _growth_direction(row["value"])
    return {
        "component_id": component_id, "status": "AVAILABLE", "authority_tier": OFFICIAL_TIER,
        "comparison_type": "FY_YOY", "current_value": row["value"], "comparison_value": None,
        "change": row["value"], "direction": direction, "periods": periods,
        "lineage": list(row.get("evidence_lineage") or []),
        "blocked_reason": None, "warnings": list(row.get("warnings") or []),
        "statement_scope": row.get("statement_scope"), "currency": row.get("currency"),
        "method": row.get("method"), "earnings_identity": (
            {"corporate": "net_income", "bank": "net_profit_parent", "securities": "profit_after_tax_parent"}.get(entity_class)
            if component_id == "earnings_growth" else None
        ),
    }


def _official_margin_component(metrics: Sequence[Mapping[str, Any]], entity_class: str) -> dict[str, Any]:
    if entity_class != "corporate":
        return _empty_component("net_margin_change", status="NOT_APPLICABLE",
                                reason="INDUSTRIAL_METRIC_NOT_APPLICABLE_TO_ENTITY_CLASS",
                                authority_tier=OFFICIAL_TIER)
    pair = _official_level_pair(metrics, "net_margin")
    if pair is None:
        return _empty_component("net_margin_change", status="UNAVAILABLE",
                                reason="NO_TWO_EXACT_OFFICIAL_NET_MARGIN_PERIODS",
                                authority_tier=OFFICIAL_TIER)
    previous, current = pair
    change = float(current["value"]) - float(previous["value"])
    direction = "IMPROVING" if change > 0 else "DETERIORATING" if change < 0 else "UNCHANGED"
    return {
        "component_id": "net_margin_change", "status": "AVAILABLE", "authority_tier": OFFICIAL_TIER,
        "comparison_type": "FY_YOY", "current_value": current["value"], "comparison_value": previous["value"],
        "change": change, "direction": direction,
        "periods": [previous["periods_used"][0], current["periods_used"][0]],
        "lineage": list(previous.get("evidence_lineage") or []) + list(current.get("evidence_lineage") or []),
        "blocked_reason": None, "warnings": [],
        "statement_scope": current.get("statement_scope"), "currency": current.get("currency"),
    }


def _provider_growth_component(metric: Mapping[str, Any] | None, *, component_id: str,
                               entity_class: str) -> dict[str, Any]:
    if component_id in INDUSTRIAL_COMPONENTS and entity_class != "corporate":
        return _empty_component(component_id, status="NOT_APPLICABLE",
                                reason="INDUSTRIAL_METRIC_NOT_APPLICABLE_TO_ENTITY_CLASS",
                                authority_tier=PROVIDER_TIER)
    if component_id == "earnings_growth" and entity_class in {"bank", "securities"}:
        return _empty_component(
            component_id, status="BLOCKED",
            reason="PROVIDER_NET_INCOME_IS_NOT_PARENT_ATTRIBUTABLE_EARNINGS",
            authority_tier=PROVIDER_TIER,
            warnings=["parent_versus_total_earnings_remain_distinct"],
        )
    metric = metric or {}
    yoy = (metric.get("comparisons") or {}).get("yoy") if isinstance(metric.get("comparisons"), Mapping) else None
    selected = None
    comparison_type = None
    warnings: list[str] = []
    if isinstance(yoy, Mapping) and yoy.get("status") == "AVAILABLE":
        selected, comparison_type = yoy, "YoY"
    elif isinstance(yoy, Mapping) and yoy.get("blocked_reason") in {
        "STATEMENT_SCOPE_NOT_COMPARABLE", "SCOPE_CURRENCY_OR_SCALE_MISMATCH",
        "SCOPE_CURRENCY_OR_SCALE_MISMATCH_ACROSS_PERIODS",
    }:
        return _empty_component(
            component_id, status="BLOCKED", reason=str(yoy.get("blocked_reason")),
            authority_tier=PROVIDER_TIER,
        )
    elif metric.get("status") == "AVAILABLE" and metric.get("growth_fraction") is not None:
        selected, comparison_type = metric, str(metric.get("comparison_type") or "QoQ")
        if comparison_type != "YoY":
            warnings.append("YOY_COMPARABLE_ABSENT_QOQ_NOT_SUBSTITUTED_AS_YOY")
    if selected is None:
        reason = None
        if isinstance(yoy, Mapping):
            reason = yoy.get("blocked_reason")
        reason = reason or metric.get("blocked_reason") or "NO_PROVIDER_COMPARABLE_GROWTH"
        status = "UNAVAILABLE"
        if reason == "GROWTH_BASE_NON_POSITIVE":
            status = "BLOCKED"
        if reason in {"STATEMENT_SCOPE_NOT_COMPARABLE", "SCOPE_CURRENCY_OR_SCALE_MISMATCH"}:
            status = "BLOCKED"
        return _empty_component(component_id, status=status, reason=reason, authority_tier=PROVIDER_TIER)
    change = selected.get("growth_fraction")
    if change is None:
        change = metric.get("growth_fraction")
    return {
        "component_id": component_id, "status": "PARTIAL" if comparison_type == "QoQ" else "AVAILABLE",
        "authority_tier": PROVIDER_TIER, "comparison_type": comparison_type,
        "current_value": None, "comparison_value": None, "change": change,
        "direction": _growth_direction(change), "periods": list(selected.get("periods") or metric.get("periods") or []),
        "lineage": list(selected.get("lineage") or metric.get("lineage") or []),
        "blocked_reason": None, "warnings": warnings, "provider": selected.get("provider") or metric.get("provider"),
        "method": metric.get("method"),
    }


def _provider_direction_component(metric: Mapping[str, Any] | None, *, component_id: str,
                                  entity_class: str) -> dict[str, Any]:
    if entity_class != "corporate":
        return _empty_component(component_id, status="NOT_APPLICABLE",
                                reason="INDUSTRIAL_METRIC_NOT_APPLICABLE_TO_ENTITY_CLASS",
                                authority_tier=PROVIDER_TIER)
    metric = metric or {}
    if metric.get("status") != "AVAILABLE" or metric.get("direction") not in {"INCREASED", "DECREASED", "UNCHANGED"}:
        return _empty_component(component_id, status="UNAVAILABLE",
                                reason=metric.get("blocked_reason") or "NO_PROVIDER_DIRECTION",
                                authority_tier=PROVIDER_TIER)
    mapped = {"INCREASED": "EXPANDING", "DECREASED": "CONTRACTING", "UNCHANGED": "UNCHANGED"}[metric["direction"]]
    return {
        "component_id": component_id, "status": "PARTIAL", "authority_tier": PROVIDER_TIER,
        "comparison_type": "QoQ", "current_value": None, "comparison_value": None, "change": None,
        "direction": mapped, "periods": list(metric.get("periods") or []),
        "lineage": list(metric.get("lineage") or []), "blocked_reason": None,
        "warnings": ["YOY_COMPARABLE_ABSENT_QOQ_NOT_SUBSTITUTED_AS_YOY"],
        "provider": metric.get("provider"), "method": metric.get("method"),
    }


def _components_from_fundamental(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    entity_class = str(record.get("entity_class") or "unknown")
    applicable = _applicable_components(entity_class)
    components: dict[str, dict[str, Any]] = {}
    if record.get("authority_tier") == OFFICIAL_TIER:
        metrics = record.get("metrics") or []
        mapping = {
            "revenue_growth": ("revenue_growth_yoy", _official_growth_component),
            "earnings_growth": ("earnings_growth_yoy", _official_growth_component),
            "operating_cash_flow": ("operating_cash_flow_growth_yoy", _official_growth_component),
        }
        for component_id in CORPORATE_COMPONENTS:
            if component_id == "net_margin_change":
                components[component_id] = _official_margin_component(metrics, entity_class)
            elif component_id in mapping:
                metric_id, builder = mapping[component_id]
                components[component_id] = builder(metrics, component_id=component_id, metric_id=metric_id, entity_class=entity_class)
            if component_id not in applicable and components[component_id]["status"] != "NOT_APPLICABLE":
                components[component_id] = _empty_component(
                    component_id, status="NOT_APPLICABLE",
                    reason="INDUSTRIAL_METRIC_NOT_APPLICABLE_TO_ENTITY_CLASS", authority_tier=OFFICIAL_TIER,
                )
        return components
    trends = ((record.get("provider_series_trends") or {}).get("metrics") or {})
    components["revenue_growth"] = _provider_growth_component(trends.get("revenue_growth"), component_id="revenue_growth", entity_class=entity_class)
    components["earnings_growth"] = _provider_growth_component(trends.get("earnings_growth"), component_id="earnings_growth", entity_class=entity_class)
    components["net_margin_change"] = _empty_component(
        "net_margin_change", status="NOT_APPLICABLE" if entity_class != "corporate" else "UNAVAILABLE",
        reason="PROVIDER_ABSOLUTE_VALUES_NOT_EMITTED_FOR_MARGIN", authority_tier=PROVIDER_TIER,
    )
    components["operating_cash_flow"] = _provider_direction_component(
        trends.get("operating_cash_flow_direction"), component_id="operating_cash_flow", entity_class=entity_class,
    )
    return components


def classify_financial_momentum_state(components: Mapping[str, Mapping[str, Any]], *,
                                      entity_class: str, loss_making: bool) -> tuple[str, str]:
    """Transparent component rules. No weighted score."""
    if entity_class not in {"corporate", "bank", "securities"}:
        return NOT_APPLICABLE, "ENTITY_CLASS_HAS_NO_APPLICABLE_MOMENTUM_CONTRACT"
    if loss_making:
        return LOSS_MAKING_OR_STRESSED, "NEGATIVE_EARNINGS_OR_NON_POSITIVE_GROWTH_BASE"
    revenue = (components.get("revenue_growth") or {}).get("direction")
    earnings = (components.get("earnings_growth") or {}).get("direction")
    margin = (components.get("net_margin_change") or {}).get("direction")
    revenue_status = (components.get("revenue_growth") or {}).get("status")
    earnings_status = (components.get("earnings_growth") or {}).get("status")
    if earnings_status not in {"AVAILABLE", "PARTIAL"} and revenue_status not in {"AVAILABLE", "PARTIAL"}:
        return INSUFFICIENT_COMPARABLE_DATA, "NO_COMPARABLE_REVENUE_OR_EARNINGS_DIMENSION"
    if revenue in EXPANDING and earnings_status not in {"AVAILABLE", "PARTIAL"}:
        return MIXED, "REVENUE_DIRECTION_AVAILABLE_EARNINGS_COMPARABLE_ABSENT"
    if earnings in EXPANDING and revenue_status not in {"AVAILABLE", "PARTIAL"} and entity_class == "corporate":
        return EARNINGS_IMPROVING, "EARNINGS_EXPANDING_WITHOUT_REVENUE_CONTRACTION"
    if entity_class in {"bank", "securities"}:
        if earnings == "EXPANDING":
            return EARNINGS_IMPROVING, "PARENT_OR_APPLICABLE_EARNINGS_EXPANDING_INDUSTRIAL_METRICS_NOT_FORCED"
        if earnings == "CONTRACTING":
            return DETERIORATING, "APPLICABLE_EARNINGS_CONTRACTING"
        if earnings == "UNCHANGED":
            return MIXED, "APPLICABLE_EARNINGS_UNCHANGED"
        return INSUFFICIENT_COMPARABLE_DATA, "NO_COMPARABLE_ARCHETYPE_COMPATIBLE_EARNINGS"
    if revenue in EXPANDING and earnings in EXPANDING and margin == "IMPROVING":
        return BROAD_IMPROVEMENT, "REVENUE_UP_EARNINGS_UP_MARGIN_IMPROVING"
    if revenue in EXPANDING and earnings in EXPANDING:
        if margin == "DETERIORATING":
            return MIXED, "REVENUE_UP_EARNINGS_UP_MARGIN_DOWN"
        return EARNINGS_IMPROVING, "REVENUE_UP_EARNINGS_UP"
    if revenue in EXPANDING and earnings in CONTRACTING:
        return MIXED, "REVENUE_UP_EARNINGS_DOWN"
    if revenue in CONTRACTING and earnings in EXPANDING:
        return MIXED, "REVENUE_DOWN_EARNINGS_UP"
    if revenue in EXPANDING and margin == "DETERIORATING":
        return MIXED, "REVENUE_UP_BUT_EARNINGS_OR_MARGIN_DOWN"
    if earnings in EXPANDING and revenue not in CONTRACTING:
        return EARNINGS_IMPROVING, "EARNINGS_EXPANDING_WITHOUT_REVENUE_CONTRACTION"
    if revenue in CONTRACTING or earnings in CONTRACTING:
        return DETERIORATING, "REVENUE_OR_EARNINGS_CONTRACTING"
    if revenue == "UNCHANGED" and earnings == "UNCHANGED":
        return MIXED, "REVENUE_AND_EARNINGS_UNCHANGED"
    return INSUFFICIENT_COMPARABLE_DATA, "NO_DETERMINISTIC_INCOME_DIRECTION"


def _coverage_status(components: Mapping[str, Mapping[str, Any]], applicable: Sequence[str],
                     momentum_state: str) -> str:
    if momentum_state == NOT_APPLICABLE:
        return COVERAGE_NOT_APPLICABLE
    statuses = [components[name]["status"] for name in applicable if name in components]
    available = [status for status in statuses if status in {"AVAILABLE", "PARTIAL"}]
    if not available:
        return COVERAGE_INSUFFICIENT
    if all(status == "AVAILABLE" for status in statuses) and applicable:
        return COVERAGE_FULL
    return COVERAGE_PARTIAL


def _loss_making(record: Mapping[str, Any], components: Mapping[str, Mapping[str, Any]]) -> bool:
    earnings = components.get("earnings_growth") or {}
    if earnings.get("blocked_reason") == "GROWTH_BASE_NON_POSITIVE":
        return True
    if record.get("authority_tier") == OFFICIAL_TIER:
        latest_margin = _latest_official_metric(record.get("metrics") or [], "net_margin")
        if latest_margin is not None and float(latest_margin["value"]) < 0:
            return True
    return False


def _price_contrast(descriptive_row: Mapping[str, Any] | None, momentum_state: str) -> dict[str, Any]:
    unavailable = {
        "status": "UNAVAILABLE", "price_momentum_20d": None, "current_session": False,
        "contrast": "PRICE_CONTEXT_UNAVAILABLE",
        "reason": "NO_CURRENT_SESSION_TECHNICAL_FEATURES",
        "financial_momentum_is_not_price_momentum": True,
    }
    if not isinstance(descriptive_row, Mapping):
        return unavailable
    technical = descriptive_row.get("technical_features") or {}
    values = technical.get("values") if isinstance(technical, Mapping) else None
    if not (
        isinstance(technical, Mapping) and technical.get("status") == "SHADOW_ONLY"
        and technical.get("is_current_session") is True and isinstance(values, Mapping)
        and isinstance(values.get("momentum_20d"), (int, float)) and not isinstance(values.get("momentum_20d"), bool)
    ):
        return unavailable
    price = float(values["momentum_20d"])
    financial_up = momentum_state in {BROAD_IMPROVEMENT, EARNINGS_IMPROVING}
    financial_down = momentum_state in {DETERIORATING, LOSS_MAKING_OR_STRESSED}
    if financial_up and price > 0:
        contrast = "ALIGNED_NOT_DISTINGUISHED"
        reason = "FINANCIAL_IMPROVEMENT_AND_POSITIVE_PRICE_MOMENTUM_ARE_BOTH_PRESENT"
    elif financial_up and price <= 0:
        contrast = "FINANCIAL_IMPROVEMENT_WITHOUT_PRICE_MOMENTUM"
        reason = "COMPARABLE_FINANCIALS_IMPROVE_WHILE_CURRENT_SESSION_PRICE_MOMENTUM_IS_NOT_POSITIVE"
    elif financial_down and price > 0:
        contrast = "PRICE_MOMENTUM_WITHOUT_FINANCIAL_IMPROVEMENT"
        reason = "CURRENT_SESSION_PRICE_MOMENTUM_IS_POSITIVE_WHILE_COMPARABLE_FINANCIALS_ARE_NOT_IMPROVING"
    else:
        contrast = "NO_CLEAR_OPERATIONAL_PRICE_CONTRAST"
        reason = "FINANCIAL_STATE_AND_PRICE_MOMENTUM_DO_NOT_FORM_A_DISTINGUISHING_PAIR"
    return {
        "status": "AVAILABLE", "price_momentum_20d": price, "current_session": True,
        "contrast": contrast, "reason": reason, "financial_momentum_is_not_price_momentum": True,
    }


def _record_for_ticker(*, ticker: str, official_row: Mapping[str, Any] | None,
                       fundamental_row: Mapping[str, Any] | None,
                       descriptive_row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(fundamental_row, Mapping):
        return {
            "ticker": ticker,
            "as_of_financial_period": None,
            "entity_class": (official_row or {}).get("exchange_or_market") and "unknown" or "unknown",
            "evidence_tier": "UNAVAILABLE",
            "coverage_status": COVERAGE_INSUFFICIENT,
            "financial_momentum_state": INSUFFICIENT_COMPARABLE_DATA,
            "state_rule": "NOT_IN_FUNDAMENTAL_COHORT",
            "comparable_period_identities": [],
            "components": {
                name: _empty_component(name, status="UNAVAILABLE", reason="NOT_IN_FUNDAMENTAL_COHORT")
                for name in CORPORATE_COMPONENTS
            },
            "supporting_dimensions": [],
            "weakening_dimensions": [],
            "blockers": ["NOT_IN_FUNDAMENTAL_COHORT"],
            "warnings": ["absence_from_fundamental_cohort_is_not_zero_or_deterioration"],
            "price_momentum_context": _price_contrast(descriptive_row, INSUFFICIENT_COMPARABLE_DATA),
            "allowed_uses": ["current_research_context"],
            "prohibited_uses": list(FORBIDDEN_USES),
        }
    entity_class = str(fundamental_row.get("entity_class") or "unknown")
    evidence_tier = str(fundamental_row.get("authority_tier") or "UNAVAILABLE")
    components = _components_from_fundamental(fundamental_row)
    loss = _loss_making(fundamental_row, components)
    state, rule = classify_financial_momentum_state(components, entity_class=entity_class, loss_making=loss)
    if evidence_tier == BLOCKED_TIER:
        state, rule = INSUFFICIENT_COMPARABLE_DATA, "NO_RETAINED_PROVIDER_OR_OFFICIAL_SOURCE"
    applicable = _applicable_components(entity_class)
    coverage = _coverage_status(components, applicable, state)
    supporting = [name for name, row in components.items() if row.get("direction") in EXPANDING]
    weakening = [name for name, row in components.items() if row.get("direction") in CONTRACTING]
    periods = sorted({
        period for row in components.values() for period in row.get("periods") or []
    }, key=_period_sort_key)
    blockers = sorted({
        row["blocked_reason"] for row in components.values() if row.get("blocked_reason")
    })
    warnings = sorted({
        warning for row in components.values() for warning in row.get("warnings") or []
    })
    if evidence_tier == PROVIDER_TIER:
        warnings.append("provider_research_is_not_official_qualified")
    return {
        "ticker": ticker,
        "as_of_financial_period": periods[-1] if periods else None,
        "entity_class": entity_class,
        "evidence_tier": evidence_tier,
        "coverage_status": coverage,
        "financial_momentum_state": state,
        "state_rule": rule,
        "comparable_period_identities": [
            {"component_id": row["component_id"], "comparison_type": row.get("comparison_type"),
             "periods": list(row.get("periods") or [])}
            for row in components.values() if row.get("periods")
        ],
        "components": components,
        "supporting_dimensions": supporting,
        "weakening_dimensions": weakening,
        "blockers": blockers,
        "warnings": warnings,
        "price_momentum_context": _price_contrast(descriptive_row, state),
        "allowed_uses": ["current_research_context"],
        "prohibited_uses": list(FORBIDDEN_USES),
        "does_not_enable_fundamental_improvement_strategy": True,
    }


def build_artifact(
    *,
    current_official_universe: Mapping[str, Any],
    current_fundamental: Mapping[str, Any],
    current_descriptive: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    tickers = _verify_official_universe(current_official_universe)
    _verify_fundamental(current_fundamental)
    _verify_descriptive(current_descriptive)
    fundamental_records = current_fundamental.get("records") if isinstance(current_fundamental.get("records"), Mapping) else {}
    official_records = current_official_universe.get("records") if isinstance(current_official_universe.get("records"), Mapping) else {}
    descriptive_records = {}
    if current_descriptive and isinstance(current_descriptive.get("records"), Mapping):
        descriptive_records = current_descriptive["records"]
    records: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        record = _record_for_ticker(
            ticker=ticker,
            official_row=official_records.get(ticker) if isinstance(official_records.get(ticker), Mapping) else None,
            fundamental_row=fundamental_records.get(ticker) if isinstance(fundamental_records.get(ticker), Mapping) else None,
            descriptive_row=descriptive_records.get(ticker) if isinstance(descriptive_records.get(ticker), Mapping) else None,
        )
        records[ticker] = record
    if len(records) != len(tickers):
        raise CurrentFinancialMomentumContextError("OFFICIAL_UNIVERSE_DENOMINATOR_DRIFT")
    coverage = {
        "universe_denominator": len(records),
        "fundamental_cohort_present": sum(row["evidence_tier"] != "UNAVAILABLE" for row in records.values()),
        "tickers_with_comparable_dimension": sum(
            1 for row in records.values()
            if any(component.get("status") in {"AVAILABLE", "PARTIAL"} for component in row["components"].values())
        ),
        "coverage_status_distribution": dict(sorted(Counter(row["coverage_status"] for row in records.values()).items())),
        "momentum_state_distribution": dict(sorted(Counter(row["financial_momentum_state"] for row in records.values()).items())),
        "evidence_tier_distribution": dict(sorted(Counter(row["evidence_tier"] for row in records.values()).items())),
        "archetype_distribution": dict(sorted(Counter(row["entity_class"] for row in records.values()).items())),
        "component_availability": {
            name: dict(sorted(Counter(
                (row["components"].get(name) or {}).get("status") for row in records.values()
            ).items()))
            for name in CORPORATE_COMPONENTS
        },
        "unexplained_count": 0,
        "denominator_reconciles": True,
    }
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "milestone": MILESTONE,
        "research_mode": "CURRENT_RESEARCH_ONLY",
        "source_artifact_identities": {
            "current_official_universe": current_official_universe.get("artifact_identity"),
            "market_wide_current_fundamental_research": current_fundamental.get("artifact_identity"),
            "market_wide_current_descriptive_research": None if current_descriptive is None else current_descriptive.get("artifact_identity"),
        },
        "session": None if current_descriptive is None else current_descriptive.get("session"),
        "records": records,
        "coverage": coverage,
        "momentum_state_vocabulary": list(MOMENTUM_STATES),
        "state_rules": {
            BROAD_IMPROVEMENT: "corporate revenue expanding AND earnings expanding AND net margin improving",
            EARNINGS_IMPROVING: "earnings expanding without revenue contraction; banks/securities use earnings only",
            MIXED: "revenue expanding while earnings or margin contract, or unchanged income pair",
            DETERIORATING: "revenue or earnings contracting without an offsetting broad-improvement pattern",
            LOSS_MAKING_OR_STRESSED: "negative official net margin or non-positive earnings growth base",
            INSUFFICIENT_COMPARABLE_DATA: "no comparable revenue/earnings dimension of compatible period/scope/identity",
            NOT_APPLICABLE: "entity class has no applicable momentum contract",
        },
        "blocked_outputs": {
            "strategy_eligibility": "NOT_MODIFIED",
            "research_priority": "NOT_MODIFIED",
            "entry_action": "NOT_MODIFIED",
            "fundamental_improvement_strategy": "NOT_ENABLED_BY_THIS_CONTEXT",
        },
        "authority_boundary": {
            "is_actionable": False,
            "financial_momentum_is_not_cheapness": True,
            "financial_momentum_is_not_value": True,
            "financial_momentum_is_not_target_price": True,
            "financial_momentum_is_not_forecast": True,
            "financial_momentum_is_not_probability": True,
            "financial_momentum_is_not_strategy_eligibility": True,
            "financial_momentum_is_not_research_priority": True,
            "financial_momentum_is_not_entry_action": True,
            "financial_momentum_is_not_recommendation": True,
            "financial_momentum_is_not_sizing": True,
            "financial_momentum_is_not_price_momentum": True,
            "official_and_provider_remain_separated": True,
            "provider_not_upgraded_to_official": True,
            "adjacent_period_not_substituted_for_missing_comparable": True,
            "missing_is_not_zero": True,
            "industrial_metrics_not_forced_onto_bank_or_securities": True,
            "one_missing_metric_does_not_globally_block_ticker": True,
            "raw_as_traded": "NOT_PROMOTED",
            "pit": "BLOCKED",
            "backtesting": "BLOCKED",
            "frozen_sessions_not_regenerated": ["2026-08-21", "2026-08-24"],
        },
        "prohibited_uses": list(FORBIDDEN_USES),
    }
    artifact.update(content_identity(artifact))
    return artifact
