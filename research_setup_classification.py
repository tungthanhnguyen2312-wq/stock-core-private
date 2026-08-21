"""Deterministic multi-label research setup classification; never a strategy signal."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping

METHOD = "research_setup_classification/v1"


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


REGISTRY = {
    "TREND_CONTINUATION_CONTEXT": {
        "rule": "trend_state == ABOVE_MA20 AND momentum_20d > 0",
        "required_features": ("trend_state", "momentum_20d"), "authority": "SHADOW_ONLY"},
    "BREAKOUT_CONTEXT": {
        "rule": "price_structure_state == BREAKOUT_CONFIRMED_BY_RULE",
        "required_features": ("price_structure_state",), "authority": "SHADOW_ONLY"},
    "NEAR_RESISTANCE_CONTEXT": {
        "rule": "price_structure_state == NEAR_RECENT_RESISTANCE",
        "required_features": ("price_structure_state",), "authority": "SHADOW_ONLY"},
    "BREAKOUT_WITH_ELEVATED_VOLUME_PROXY_CONTEXT": {
        "rule": "BREAKOUT_CONTEXT AND volume_proxy_state == ELEVATED_PROVIDER_RELATIVE_VOLUME_PROXY",
        "required_features": ("price_structure_state", "volume_proxy_state"), "authority": "DERIVED_PROXY"},
    "NEAR_SUPPORT_CONTEXT": {
        "rule": "price_structure_state == NEAR_RECENT_SUPPORT",
        "required_features": ("price_structure_state",), "authority": "SHADOW_ONLY"},
    "TREND_PULLBACK_CONTEXT": {
        "rule": "NEAR_SUPPORT_CONTEXT AND trend_state == ABOVE_MA20",
        "required_features": ("price_structure_state", "trend_state"), "authority": "SHADOW_ONLY"},
    "RANGE_COMPRESSION_CONTEXT": {
        "rule": "range_state == RANGE_COMPRESSION",
        "required_features": ("range_state",), "authority": "SHADOW_ONLY"},
    "WEAKENING_STRUCTURE_CONTEXT": {
        "rule": "trend_state == AT_OR_BELOW_MA20 AND momentum_20d < 0",
        "required_features": ("trend_state", "momentum_20d"), "authority": "SHADOW_ONLY"},
    "BREAKDOWN_CONTEXT": {
        "rule": "price_structure_state == BREAKDOWN_CONFIRMED_BY_RULE",
        "required_features": ("price_structure_state",), "authority": "SHADOW_ONLY"},
    "RELATIVE_STRENGTH_CONTEXT": {
        "rule": "relative momentum_20d is AVAILABLE and descriptive_bucket == UPPER_QUARTILE",
        "required_features": ("relative_momentum_20d",), "authority": "RELATIVE_CONTEXT_DEPENDENT"},
}


def _evaluation(ticker: str, session: str, setup_id: str, present: bool | None, authority: str,
                values: Mapping[str, Any], sources: Mapping[str, str | None], reasons: list[str]) -> dict[str, Any]:
    state = "UNAVAILABLE" if present is None else ("QUALIFIED_LOWER_AUTHORITY" if present and authority == "PROVIDER_DESCRIPTIVE_CLASSIFICATION" else "QUALIFIED_SHADOW" if present else "NOT_PRESENT")
    item = {"setup_id": setup_id, "version": "v1", "ticker": ticker, "research_session": session,
            "qualification_state": state, "authority_ceiling": authority if authority != "PROVIDER_DESCRIPTIVE_CLASSIFICATION" else "PROVIDER_DESCRIPTIVE_CLASSIFICATION",
            "rule": REGISTRY[setup_id]["rule"], "required_feature_identities": list(REGISTRY[setup_id]["required_features"]),
            "observed_feature_values": dict(values), "reason_codes": reasons,
            "source_artifact_identities": dict(sources)}
    item["setup_content_identity"] = "research_setup:" + _hash(item)
    return item


def build(product: Mapping[str, Any], price: Mapping[str, Any], relative: Mapping[str, Any], market: Mapping[str, Any],
          downside: Mapping[str, Any], scenarios: Mapping[str, Any], review_pack: Mapping[str, Any]) -> dict[str, Any]:
    prices = {row["ticker"]: row for row in price["records"]}
    relatives = {row["ticker"]: row for row in relative["records"]}
    downsides = {row["ticker"]: row for row in downside["records"]}
    scenario_tickers = {row["ticker"] for row in scenarios["scenarios"]}
    sources = {"daily_product": product["artifact_identity"], "price_structure": price["artifact_identity"],
               "relative_context": relative["artifact_identity"], "market_context": market["artifact_identity"],
               "downside_context": downside["artifact_identity"], "scenario": scenarios["artifact_identity"],
               "review_pack": review_pack["artifact_identity"]}
    records = []
    for daily in sorted(product["stock_research"], key=lambda row: row["ticker"]):
        ticker = daily["ticker"]; facts = daily["ai_ready_brief"]["facts"]; structure = prices.get(ticker); context = relatives.get(ticker)
        trend = daily["research_summary"]["trend_state"]; momentum = facts.get("momentum_20d")
        state = structure.get("structure_status") if structure else None; range_state = structure.get("range_state") if structure else None
        volume = structure.get("volume_proxy_state") if structure else None
        base_values = {"trend_state": trend, "momentum_20d": momentum, "price_structure_state": state,
                       "range_state": range_state, "volume_proxy_state": volume}
        unavailable_structure = structure is None or state == "INSUFFICIENT_HISTORY"
        setups = [
            _evaluation(ticker, facts["session"], "TREND_CONTINUATION_CONTEXT", None if trend is None or not isinstance(momentum, (int, float)) else trend == "ABOVE_MA20" and momentum > 0, "SHADOW_ONLY", base_values, sources, ["ABOVE_MA20_AND_POSITIVE_20D_MOMENTUM"]),
            _evaluation(ticker, facts["session"], "BREAKOUT_CONTEXT", None if unavailable_structure else state == "BREAKOUT_CONFIRMED_BY_RULE", "SHADOW_ONLY", base_values, sources, ["PRICE_STRUCTURE_BREAKOUT_RULE"]),
            _evaluation(ticker, facts["session"], "NEAR_RESISTANCE_CONTEXT", None if unavailable_structure else state == "NEAR_RECENT_RESISTANCE", "SHADOW_ONLY", base_values, sources, ["PRICE_STRUCTURE_NEAR_RESISTANCE_RULE"]),
            _evaluation(ticker, facts["session"], "BREAKOUT_WITH_ELEVATED_VOLUME_PROXY_CONTEXT", None if unavailable_structure or volume is None else state == "BREAKOUT_CONFIRMED_BY_RULE" and volume == "ELEVATED_PROVIDER_RELATIVE_VOLUME_PROXY", "DERIVED_PROXY", base_values, sources, ["BREAKOUT_RULE_AND_ELEVATED_PROVIDER_RELATIVE_VOLUME_PROXY"]),
            _evaluation(ticker, facts["session"], "NEAR_SUPPORT_CONTEXT", None if unavailable_structure else state == "NEAR_RECENT_SUPPORT", "SHADOW_ONLY", base_values, sources, ["PRICE_STRUCTURE_NEAR_SUPPORT_RULE"]),
            _evaluation(ticker, facts["session"], "TREND_PULLBACK_CONTEXT", None if unavailable_structure or trend is None else state == "NEAR_RECENT_SUPPORT" and trend == "ABOVE_MA20", "SHADOW_ONLY", base_values, sources, ["NEAR_SUPPORT_AND_ABOVE_MA20"]),
            _evaluation(ticker, facts["session"], "RANGE_COMPRESSION_CONTEXT", None if unavailable_structure else range_state == "RANGE_COMPRESSION", "SHADOW_ONLY", base_values, sources, ["PRICE_STRUCTURE_RANGE_COMPRESSION_RULE"]),
            _evaluation(ticker, facts["session"], "WEAKENING_STRUCTURE_CONTEXT", None if trend is None or not isinstance(momentum, (int, float)) else trend == "AT_OR_BELOW_MA20" and momentum < 0, "SHADOW_ONLY", base_values, sources, ["AT_OR_BELOW_MA20_AND_NEGATIVE_20D_MOMENTUM"]),
            _evaluation(ticker, facts["session"], "BREAKDOWN_CONTEXT", None if unavailable_structure else state == "BREAKDOWN_CONFIRMED_BY_RULE", "SHADOW_ONLY", base_values, sources, ["PRICE_STRUCTURE_BREAKDOWN_RULE"]),
        ]
        relative_metric = next((metric for metric in (context or {}).get("relative_metrics", []) if metric["metric_identity"] == "momentum_20d"), None)
        if not relative_metric or relative_metric["status"] != "AVAILABLE":
            setups.append(_evaluation(ticker, facts["session"], "RELATIVE_STRENGTH_CONTEXT", None, "UNAVAILABLE", {"relative_momentum_20d": relative_metric}, sources, [relative_metric.get("missing_or_exclusion_reason", "RELATIVE_CONTEXT_UNAVAILABLE") if relative_metric else "RELATIVE_CONTEXT_UNAVAILABLE"]))
        else:
            authority = context["relative_context_authority"]
            setups.append(_evaluation(ticker, facts["session"], "RELATIVE_STRENGTH_CONTEXT", relative_metric["descriptive_bucket"] == "UPPER_QUARTILE", authority, {"relative_momentum_20d": relative_metric}, sources, ["UPPER_QUARTILE_RELATIVE_MOMENTUM"]))
        active = [item for item in setups if item["qualification_state"] in ("QUALIFIED_SHADOW", "QUALIFIED_LOWER_AUTHORITY")]
        unavailable = [item for item in setups if item["qualification_state"] == "UNAVAILABLE"]
        records.append({"ticker": ticker, "research_session": facts["session"], "setup_evaluations": setups,
                        "active_setup_ids": [item["setup_id"] for item in active], "active_setup_authorities": {item["setup_id"]: item["authority_ceiling"] for item in active},
                        "record_setup_state": "NO_DISTINCT_SETUP" if not active else "MULTI_LABEL_SETUP_CONTEXT" if len(active) > 1 else "SINGLE_SETUP_CONTEXT",
                        "unavailable_setup_reasons": {item["setup_id"]: item["reason_codes"] for item in unavailable},
                        "market_context": {"descriptor": market["breadth"]["trend"]["descriptor"]["descriptor"], "source_identity": market["artifact_identity"]},
                        "downside_reference": {"technical_status": downsides[ticker]["domains"]["TECHNICAL_DOWNSIDE_CONTEXT"]["status"], "source_identity": downside["artifact_identity"]},
                        "scenario_available": ticker in scenario_tickers})
    label_counts = Counter(label for record in records for label in record["active_setup_ids"])
    state_counts = Counter(record["record_setup_state"] for record in records)
    relative_auth = Counter(record["active_setup_authorities"].get("RELATIVE_STRENGTH_CONTEXT", "NOT_ACTIVE") for record in records)
    artifact = {"schema_version": "1.0.0", "contract_version": METHOD, "research_session": product["daily_market_research"]["session"],
                "cohort": {"member_count": len(records), "authority": "EMPIRICAL_ACTIVE_SHADOW_ONLY"}, "registry": REGISTRY,
                "qualification_state_vocabulary": ["QUALIFIED_SHADOW", "QUALIFIED_LOWER_AUTHORITY", "PARTIAL", "BLOCKED", "NOT_PRESENT", "UNAVAILABLE"],
                "source_artifact_identities": sources, "records": records,
                "coverage": {"records": len(records), "active_setup_counts": dict(sorted(label_counts.items())), "record_setup_state_counts": dict(state_counts),
                             "relative_strength_authority_counts": dict(relative_auth), "unavailable_evaluation_count": sum(len(row["unavailable_setup_reasons"]) for row in records)},
                "authority_boundary": {"not_signal_ranking_recommendation_or_expected_return": True, "market_context_is_not_setup_gate": True,
                                       "provider_relative_volume_is_derived_proxy_not_liquidity": True, "historical_pit_raw_as_traded_backtest": "NOT_PROMOTED"},
                "verdict": "RESEARCH_SETUP_CLASSIFICATION_V1_READY"}
    artifact["artifact_identity"] = "research_setup_classification:" + _hash(artifact)
    return artifact


def daily_overlay(context: Mapping[str, Any]) -> dict[str, Any]:
    overlay = {"contract_version": "research_setup_daily_overlay/v1", "setup_context_identity": context["artifact_identity"],
               "records": [{"ticker": row["ticker"], "research_session": row["research_session"], "active_setup_ids": row["active_setup_ids"], "record_setup_state": row["record_setup_state"], "authority": row["active_setup_authorities"]} for row in context["records"]]}
    overlay["artifact_identity"] = "research_setup_daily_overlay:" + _hash(overlay)
    return overlay


def consumer_overlays(context: Mapping[str, Any], review_pack: Mapping[str, Any], scenarios: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    by = {row["ticker"]: row for row in context["records"]}
    review = {"contract_version": "research_setup_review_overlay/v1", "setup_context_identity": context["artifact_identity"], "entries": [{"ticker": item["ticker"], "section": "SETUP_CONTEXT", "active_setup_ids": by[item["ticker"]]["active_setup_ids"], "authorities": by[item["ticker"]]["active_setup_authorities"], "market_context": by[item["ticker"]]["market_context"], "strongest_observable_structure_facts": [value for value in by[item["ticker"]]["setup_evaluations"] if value["setup_id"] in by[item["ticker"]]["active_setup_ids"]], "key_limitation": by[item["ticker"]]["unavailable_setup_reasons"]} for item in review_pack["owner_review_queue"]]}
    review["artifact_identity"] = "research_setup_review_overlay:" + _hash(review)
    scenario = {"contract_version": "research_setup_scenario_fact_overlay/v1", "setup_context_identity": context["artifact_identity"], "entries": [{"ticker": item["ticker"], "classification": "FACT", "active_setup_ids": by[item["ticker"]]["active_setup_ids"], "record_setup_state": by[item["ticker"]]["record_setup_state"], "warning": "CURRENT_DESCRIPTIVE_SETUP_NOT_FORECAST_OR_SCENARIO_PROBABILITY"} for item in scenarios["scenarios"]]}
    scenario["artifact_identity"] = "research_setup_scenario_fact_overlay:" + _hash(scenario)
    downside = {"contract_version": "research_setup_downside_fact_overlay/v1", "setup_context_identity": context["artifact_identity"], "entries": [{"ticker": row["ticker"], "classification": "FACT", "observed_weakening_or_breakdown": [label for label in row["active_setup_ids"] if label in ("WEAKENING_STRUCTURE_CONTEXT", "BREAKDOWN_CONTEXT")], "warning": "OBSERVED_TECHNICAL_CONTEXT_NOT_RISK_SCORE_OR_SELL_SIGNAL"} for row in context["records"]]}
    downside["artifact_identity"] = "research_setup_downside_fact_overlay:" + _hash(downside)
    return review, scenario, downside
