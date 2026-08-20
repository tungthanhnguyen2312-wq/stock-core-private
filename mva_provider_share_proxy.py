"""MVA-only provider-issued-share proxy policy and valuation adapter.

This module deliberately does not participate in the authoritative P3-F2
resolver.  It consumes retained provider observations in their own namespace
and permits them only in a complete MINIMUM_VIABLE_ANALYSIS_SHADOW envelope.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping

import p3f_current_market_valuation as p3f

POLICY_VERSION = "p3f6_mva_provider_issued_share_proxy/v1"
PROXY_NAMESPACE = "PROVIDER_REPORTED_ISSUED_SHARES_PROXY"
PROXY_METRIC_IDENTITY = "market_cap_provider_issued_share_proxy"
PROVIDER_SOURCE = "VCI.overview.issue_share"
PROVIDER_FIELD_LINEAGE = "Company(source='VCI').overview().issue_share"
SEMANTIC_IDENTITY = "ISSUED_SHARES"
SOURCE_AUTHORITY = "NOT_PROMOTED"
RUNTIME_MODE = "MINIMUM_VIABLE_ANALYSIS_SHADOW"

REQUIRED_ENVELOPE = {
    "runtime_mode": RUNTIME_MODE,
    "is_actionable_for_execution": False,
    "pit_backtest_eligible": False,
    "liquidity_sizing_authority": "BLOCKED",
    "valuation_scope": "CURRENT_DESCRIPTIVE_ONLY",
}
CORPORATE_ACTION_BLOCKS = frozenset({
    "provider_reported_stale", "provider_reported_unverifiable_freshness",
})


def _iso_date(value: Any) -> str | None:
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError):
        return None


def shadow_envelope_is_valid(envelope: Mapping[str, Any]) -> bool:
    """Require the complete MVA envelope; partial declarations fail closed."""
    return all(envelope.get(key) == value for key, value in REQUIRED_ENVELOPE.items())


def qualify_provider_issued_shares_proxy(
    instrument: Mapping[str, Any], observation: Mapping[str, Any] | None, *,
    valuation_date: str, safety_state: Mapping[str, Any] | None,
    envelope: Mapping[str, Any],
) -> dict[str, Any]:
    """Qualify one retained provider observation for MVA shadow use only.

    ``PROXY_STALE`` is intentionally visible rather than silently forward
    filled.  The owner-approved policy permits that degraded state for current
    descriptive MVA only; corporate-action ambiguity remains a hard block.
    """
    ticker = str(instrument.get("canonical_ticker") or "").strip().upper()
    target = _iso_date(valuation_date)
    base = {
        "policy_version": POLICY_VERSION,
        "canonical_instrument": dict(instrument),
        "proxy_namespace": PROXY_NAMESPACE,
        "semantic_identity": SEMANTIC_IDENTITY,
        "source_authority": SOURCE_AUTHORITY,
        "official_share_authority": False,
        "common_outstanding_equivalence": False,
        "output_status": "DERIVED_PROXY",
        "provider_source": PROVIDER_SOURCE,
        "provider_field_lineage": PROVIDER_FIELD_LINEAGE,
        "valuation_date": target,
        "provider_observation_date": None,
        "provider_retrieved_at": None,
        "observation_age_days": None,
        "freshness_state": "UNKNOWN",
        "effective_date_limitation": "provider_observation_date_is_not_a_common_share_effective_date",
        "corporate_action_state": str((safety_state or {}).get("authority") or "unknown"),
        "value": None,
        "status": "PROXY_MISSING",
        "mva_proxy_eligible": False,
        "warnings": [],
        "blockers": [],
    }
    if not shadow_envelope_is_valid(envelope):
        return {**base, "status": "PROXY_NOT_ALLOWED", "blockers": ["MVA_SHADOW_ENVELOPE_REQUIRED"]}
    if not ticker or target is None:
        return {**base, "status": "PROXY_MALFORMED", "blockers": ["CANONICAL_INSTRUMENT_OR_VALUATION_DATE_INVALID"]}
    if observation is None:
        return {**base, "status": "PROXY_MISSING", "blockers": ["PROVIDER_OBSERVATION_MISSING"]}
    observed_ticker = str(observation.get("canonical_ticker") or observation.get("ticker") or "").strip().upper()
    if observed_ticker != ticker:
        return {**base, "status": "PROXY_CONFLICT", "blockers": ["CANONICAL_INSTRUMENT_MAPPING_CONFLICT"]}
    value = observation.get("value")
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return {**base, "status": "PROXY_MALFORMED", "blockers": ["PROVIDER_VALUE_MUST_BE_POSITIVE_INTEGRAL"]}
    if observation.get("semantic_identity") != SEMANTIC_IDENTITY:
        return {**base, "status": "PROXY_CONFLICT", "blockers": ["PROVIDER_SEMANTIC_IDENTITY_MISMATCH"]}
    if observation.get("provider_source") != PROVIDER_SOURCE or observation.get("provider_field_lineage") != PROVIDER_FIELD_LINEAGE:
        return {**base, "status": "PROXY_CONFLICT", "blockers": ["PROVIDER_FIELD_LINEAGE_MISMATCH"]}
    observed_on = _iso_date(observation.get("observation_date"))
    if observed_on is None:
        return {**base, "status": "PROXY_MALFORMED", "blockers": ["PROVIDER_OBSERVATION_DATE_REQUIRED"]}
    retrieved_at = observation.get("retrieved_at")
    if not isinstance(retrieved_at, str) or not retrieved_at.strip():
        return {**base, "provider_observation_date": observed_on, "status": "PROXY_MALFORMED",
                "blockers": ["PROVIDER_RETRIEVAL_TIMESTAMP_REQUIRED"]}
    state = safety_state or {}
    authority = str(state.get("authority") or "unknown")
    if authority in CORPORATE_ACTION_BLOCKS:
        return {**base, "provider_observation_date": observed_on, "provider_retrieved_at": retrieved_at, "value": value,
                "status": "PROXY_CORPORATE_ACTION_BLOCKED", "corporate_action_state": authority,
                "blockers": ["CORPORATE_ACTION_TIMING_OR_RESULT_UNRESOLVED"],
                "warnings": list(state.get("share_changing_after_observation") or []) + list(state.get("undated_share_relevant_events") or [])}
    official_value = state.get("value")
    if authority == "qualified_official" and isinstance(official_value, int) and official_value != value:
        return {**base, "provider_observation_date": observed_on, "provider_retrieved_at": retrieved_at, "value": value,
                "status": "PROXY_CONFLICT", "corporate_action_state": authority,
                "blockers": ["PROVIDER_VALUE_CONFLICTS_WITH_RETAINED_OFFICIAL_REFERENCE"]}
    if authority in {"unavailable", "unknown_observation_date", "unresolved_error"}:
        return {**base, "provider_observation_date": observed_on, "provider_retrieved_at": retrieved_at, "value": value,
                "status": "PROXY_MISSING", "corporate_action_state": authority,
                "blockers": ["PROVIDER_SAFETY_STATE_UNAVAILABLE"]}
    age = (date.fromisoformat(target) - date.fromisoformat(observed_on)).days
    stale = age > 0 or authority == "provider_reported_lagged"
    return {**base, "provider_observation_date": observed_on, "provider_retrieved_at": retrieved_at,
            "observation_age_days": age, "value": value,
            "status": "PROXY_STALE" if stale else "PROXY_ELIGIBLE", "mva_proxy_eligible": True,
            "freshness_state": "STALE_DEGRADED" if stale else "OBSERVED_ON_VALUATION_DATE",
            "corporate_action_state": authority,
            "warnings": (["STALE_PROVIDER_OBSERVATION_VISIBLE_ONLY_IN_MVA_SHADOW"] if stale else [])}


def build_provider_proxy_market_cap(price: Mapping[str, Any], proxy: Mapping[str, Any], *, envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Build the distinct provider-issued-share market-cap metric identity."""
    base = {
        "metric_identity": PROXY_METRIC_IDENTITY,
        "policy_version": POLICY_VERSION,
        "output_status": "DERIVED_PROXY",
        "valuation_lane": "MVA_SHADOW",
        "is_actionable": False,
        "valuation_date": proxy.get("valuation_date"),
        "value": None,
        "status": "PROXY_MARKET_CAP_BLOCKED",
        "warnings": list(proxy.get("warnings") or []),
        "blockers": [],
    }
    if not shadow_envelope_is_valid(envelope):
        return {**base, "blockers": ["MVA_SHADOW_ENVELOPE_REQUIRED"]}
    if price.get("status") != "PRICE_READY":
        return {**base, "blockers": list(price.get("reason_codes") or ["CURRENT_PRICE_NOT_READY"])}
    if not proxy.get("mva_proxy_eligible"):
        return {**base, "blockers": list(proxy.get("blockers") or [str(proxy.get("status") or "PROXY_NOT_ELIGIBLE")])}
    price_value, share_value = price.get("value"), proxy.get("value")
    if not isinstance(price_value, (int, float)) or isinstance(price_value, bool) or not isinstance(share_value, int):
        return {**base, "blockers": ["PROXY_MARKET_CAP_INPUT_MALFORMED"]}
    return {**base, "status": "PROXY_MARKET_CAP_READY", "value": price_value * share_value,
            "price_identity": {key: price.get(key) for key in ("provider", "field_identity", "session", "payload_identity", "price_basis", "price_namespace", "raw_as_traded")},
            "provider_share_identity": {key: proxy.get(key) for key in ("proxy_namespace", "semantic_identity", "source_authority", "provider_source", "provider_field_lineage", "provider_observation_date", "observation_age_days", "freshness_state", "corporate_action_state", "official_share_authority", "common_outstanding_equivalence")}}


def evaluate_mva_proxy_issuer(issuer: Mapping[str, Any], *, price: Mapping[str, Any], proxy: Mapping[str, Any], envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Reuse the P3-F formula evaluator while emitting a separate shadow lane."""
    market_cap = build_provider_proxy_market_cap(price, proxy, envelope=envelope)
    share_input = {
        "status": "PROXY_SHARE_READY" if market_cap["status"] == "PROXY_MARKET_CAP_READY" else "PROXY_SHARE_BLOCKED",
        "value": proxy.get("value") if market_cap["status"] == "PROXY_MARKET_CAP_READY" else None,
        "reason_codes": [] if market_cap["status"] == "PROXY_MARKET_CAP_READY" else list(market_cap["blockers"]),
        "identity": SEMANTIC_IDENTITY,
    }
    formula_row = p3f._evaluate_issuer(issuer, price=price, shares=share_input)
    methods = {}
    for name, method in formula_row["methods"].items():
        methods[name] = {**method, "status": "MVA_PROXY_READY" if method["status"] == "VALUATION_READY" else method["status"],
                         "output_status": "DERIVED_PROXY", "valuation_lane": "MVA_SHADOW",
                         "market_cap_metric_identity": PROXY_METRIC_IDENTITY,
                         "provider_share_proxy_namespace": PROXY_NAMESPACE}
    return {
        "ticker": formula_row["ticker"], "entity_class": formula_row["entity_class"],
        "valuation_date": formula_row["valuation_date"], "valuation_lane": "MVA_SHADOW",
        "output_status": "DERIVED_PROXY", "is_actionable": False,
        "price_input": dict(price), "provider_share_proxy": dict(proxy),
        PROXY_METRIC_IDENTITY: market_cap, "financial_readiness_by_method": formula_row["financial_readiness_by_method"],
        "methods": methods,
    }
