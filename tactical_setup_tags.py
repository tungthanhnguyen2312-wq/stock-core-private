"""Deterministic multi-label tactical setup tags (TACTICAL_AND_BEHAVIORAL_ENGINE_V2).

Registry style proven by ``research_setup_classification.py``, applied to the current governed
lineage. This module computes no new technical indicator, ranking, or evidence of its own: every
value it reads was already computed by ``technical_structure_context.py`` (close-based structure/
contraction/breakout facts), ``market_wide_current_descriptive_research.py`` (trend/momentum),
``current_market_screening_opportunity_comparison_foundation.py`` (relative-volume cohort-membership
flag only -- never its market-relative momentum percentile, which uses a different, non-canonical
tie-break formula), ``current_market_sector_leadership_context.py`` (the canonical market/sector
relative-strength and regime source for this milestone, using the ``(below + 0.5*equal)/n``
percentile convention throughout), and ``watchlist_tactical_entry_classifier.py`` (the unmodified,
still-primary ``entry_state``, exposed here only as one tag's input, never re-derived).

Tags are independent and multi-label: none is forced to appear, several may co-occur, and a ticker
may have zero active tags. ``MARKET_REGIME_TAILWIND``/``HEADWIND`` are contemporaneous context only,
never a gate on any other tag or on ``entry_state``. No tag ever substitutes a fixed numeric
threshold for a cross-sectional or self-relative comparison already computed upstream (no universal
RV>=1.5 rule; relative-volume membership reuses the existing cohort-median flag verbatim).
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping

CONTRACT_VERSION = "tactical_setup_tags/v1"
MILESTONE = "TACTICAL_AND_BEHAVIORAL_ENGINE_V2"

QUALIFICATION_STATES = ("QUALIFIED_SHADOW", "QUALIFIED_LOWER_AUTHORITY", "NOT_PRESENT", "UNAVAILABLE")

REGISTRY: dict[str, dict[str, Any]] = {
    "NEAR_RESISTANCE": {"rule": "structure_status == NEAR_RECENT_RESISTANCE", "required_features": ("structure_status",), "authority": "SHADOW_ONLY"},
    "NEAR_SUPPORT": {"rule": "structure_status == NEAR_RECENT_SUPPORT", "required_features": ("structure_status",), "authority": "SHADOW_ONLY"},
    "RANGE_COMPRESSION": {"rule": "range_state == RANGE_COMPRESSION", "required_features": ("range_state",), "authority": "SHADOW_ONLY"},
    "RANGE_EXPANSION": {"rule": "range_state == RANGE_EXPANSION", "required_features": ("range_state",), "authority": "SHADOW_ONLY"},
    "PULLBACK_TO_SUPPORT_IN_UPTREND": {"rule": "NEAR_SUPPORT AND trend_state == ABOVE_MA20", "required_features": ("structure_status", "trend_state"), "authority": "SHADOW_ONLY"},
    "BREAKOUT_CONFIRMED_BY_RULE": {"rule": "structure_status == BREAKOUT_CONFIRMED_BY_RULE", "required_features": ("structure_status",), "authority": "SHADOW_ONLY"},
    "BREAKOUT_FAILURE": {"rule": "breakout_event == BREAKOUT_FAILURE (today back below yesterday's resistance)", "required_features": ("breakout_event",), "authority": "SHADOW_ONLY"},
    "EARLY_REVERSAL_STRUCTURE": {"rule": "watchlist_tactical_entry_classifier.entry_state == EARLY_REVERSAL_CANDIDATE (pass-through, not re-derived)", "required_features": ("entry_state",), "authority": "SHADOW_ONLY"},
    "RELATIVE_STRENGTH_LEADER": {"rule": "current_market_sector_leadership_context market_relative_momentum.momentum_bucket == UPPER_QUARTILE", "required_features": ("market_relative_momentum_bucket",), "authority": "SHADOW_ONLY"},
    "RELATIVE_STRENGTH_LAGGARD": {"rule": "current_market_sector_leadership_context market_relative_momentum.momentum_bucket == LOWER_QUARTILE", "required_features": ("market_relative_momentum_bucket",), "authority": "SHADOW_ONLY"},
    "SECTOR_LEADING": {"rule": "current_market_sector_leadership_context sector_leadership_context.leadership_state == LEADING", "required_features": ("sector_leadership_state",), "authority": "SHADOW_ONLY"},
    "SECTOR_WEAKENING": {"rule": "current_market_sector_leadership_context sector_leadership_context.leadership_state == WEAKENING", "required_features": ("sector_leadership_state",), "authority": "SHADOW_ONLY"},
    "MARKET_REGIME_TAILWIND": {"rule": "current_market_sector_leadership_context.market.current_breadth_state == BROAD_PARTICIPATION (context only, never a gate)", "required_features": ("market_breadth_state",), "authority": "SHADOW_ONLY"},
    "MARKET_REGIME_HEADWIND": {"rule": "current_market_sector_leadership_context.market.current_breadth_state == DETERIORATING_BREADTH (context only, never a gate)", "required_features": ("market_breadth_state",), "authority": "SHADOW_ONLY"},
    "TECHNICAL_DETERIORATION": {"rule": "momentum_20d < 0 AND (trend_state == AT_OR_BELOW_MA20 OR ma20_slope_state == FALLING)", "required_features": ("momentum_20d", "trend_state", "ma20_slope_state"), "authority": "SHADOW_ONLY"},
    "PRICE_VOLUME_DISTRIBUTION_RISK": {"rule": "return_1d <= 0 AND RELATIVE_VOLUME_ABOVE_COHORT_MEDIAN member == True", "required_features": ("return_1d", "elevated_volume"), "authority": "DERIVED_PROXY"},
}


class TacticalSetupTagsError(ValueError):
    """A retained input or an invariant of this contract is violated."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


_IDENTITY_EXCLUDED_KEYS = {"artifact_sha256", "artifact_identity", "requested_at"}  # wall-clock never enters canonical identity


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in _IDENTITY_EXCLUDED_KEYS}
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"tactical_setup_tags:{digest}"}


def _verify(source: Mapping[str, Any], module_name: str, label: str) -> None:
    module = __import__(module_name)
    identity = module.content_identity(source)
    if source.get("artifact_sha256") != identity["artifact_sha256"]:
        raise TacticalSetupTagsError(f"{label}_IDENTITY_MISMATCH")


def _evaluation(setup_id: str, present: bool | None, authority: str, values: Mapping[str, Any], reasons: list[str]) -> dict[str, Any]:
    state = "UNAVAILABLE" if present is None else "QUALIFIED_LOWER_AUTHORITY" if present and authority == "PROVIDER_DESCRIPTIVE_CLASSIFICATION" else "QUALIFIED_SHADOW" if present else "NOT_PRESENT"
    return {
        "setup_id": setup_id, "version": "v1", "qualification_state": state,
        "authority_ceiling": authority, "rule": REGISTRY[setup_id]["rule"],
        "required_feature_identities": list(REGISTRY[setup_id]["required_features"]),
        "observed_feature_values": dict(values), "reason_codes": reasons,
    }


def _facts(*, ticker: str, structure_record: Mapping[str, Any], descriptive_record: Mapping[str, Any],
           screening_record: Mapping[str, Any] | None, leadership_ticker_context: Mapping[str, Any] | None,
           entry_state: str | None) -> dict[str, Any]:
    structure_status = (structure_record.get("structure_context") or {}).get("structure_status")
    range_state = (structure_record.get("contraction_context") or {}).get("range_state")
    breakout_event = (structure_record.get("breakout_context") or {}).get("event")
    ma20_slope_state = ((structure_record.get("trend_context") or {}).get("ma20_slope") or {}).get("slope_state")
    trend_state = descriptive_record.get("trend_state")
    values = (descriptive_record.get("technical_features") or {}).get("values", {})
    momentum_20d, return_1d = values.get("momentum_20d"), values.get("return_1d")

    elevated_volume = None
    if isinstance(screening_record, Mapping):
        membership = screening_record.get("screen_membership", {}).get("RELATIVE_VOLUME_ABOVE_COHORT_MEDIAN", {})
        if membership.get("status") == "ELIGIBLE":
            elevated_volume = membership.get("member")

    market_relative_bucket = sector_leadership_state = None
    if isinstance(leadership_ticker_context, Mapping):
        market_relative = leadership_ticker_context.get("market_relative_momentum") or {}
        if market_relative.get("status") == "AVAILABLE":
            market_relative_bucket = market_relative.get("momentum_bucket")
        sector_context = leadership_ticker_context.get("sector_leadership_context") or {}
        if sector_context.get("status") == "AVAILABLE":
            sector_leadership_state = sector_context.get("leadership_state")

    return {
        "structure_status": structure_status, "range_state": range_state, "breakout_event": breakout_event,
        "trend_state": trend_state, "momentum_20d": momentum_20d, "return_1d": return_1d,
        "ma20_slope_state": ma20_slope_state, "elevated_volume": elevated_volume,
        "market_relative_momentum_bucket": market_relative_bucket, "sector_leadership_state": sector_leadership_state,
        "entry_state": entry_state,
    }


def _evaluate_all(facts: Mapping[str, Any], market_breadth_state: str | None) -> list[dict[str, Any]]:
    f = facts
    near_support = f["structure_status"] == "NEAR_RECENT_SUPPORT"
    structure_known = f["structure_status"] is not None
    momentum_known = isinstance(f["momentum_20d"], (int, float))
    return_known = isinstance(f["return_1d"], (int, float))
    return [
        _evaluation("NEAR_RESISTANCE", None if not structure_known else f["structure_status"] == "NEAR_RECENT_RESISTANCE", "SHADOW_ONLY", {"structure_status": f["structure_status"]}, ["STRUCTURE_STATUS_UNAVAILABLE"] if not structure_known else ["PRICE_STRUCTURE_NEAR_RESISTANCE_RULE"]),
        _evaluation("NEAR_SUPPORT", None if not structure_known else near_support, "SHADOW_ONLY", {"structure_status": f["structure_status"]}, ["STRUCTURE_STATUS_UNAVAILABLE"] if not structure_known else ["PRICE_STRUCTURE_NEAR_SUPPORT_RULE"]),
        _evaluation("RANGE_COMPRESSION", None if f["range_state"] is None else f["range_state"] == "RANGE_COMPRESSION", "SHADOW_ONLY", {"range_state": f["range_state"]}, ["RANGE_STATE_UNAVAILABLE"] if f["range_state"] is None else ["PRICE_STRUCTURE_RANGE_COMPRESSION_RULE"]),
        _evaluation("RANGE_EXPANSION", None if f["range_state"] is None else f["range_state"] == "RANGE_EXPANSION", "SHADOW_ONLY", {"range_state": f["range_state"]}, ["RANGE_STATE_UNAVAILABLE"] if f["range_state"] is None else ["PRICE_STRUCTURE_RANGE_EXPANSION_RULE"]),
        _evaluation("PULLBACK_TO_SUPPORT_IN_UPTREND", None if not structure_known or f["trend_state"] is None else near_support and f["trend_state"] == "ABOVE_MA20", "SHADOW_ONLY", {"structure_status": f["structure_status"], "trend_state": f["trend_state"]}, ["STRUCTURE_OR_TREND_UNAVAILABLE"] if not structure_known or f["trend_state"] is None else ["NEAR_SUPPORT_AND_ABOVE_MA20"]),
        _evaluation("BREAKOUT_CONFIRMED_BY_RULE", None if not structure_known else f["structure_status"] == "BREAKOUT_CONFIRMED_BY_RULE", "SHADOW_ONLY", {"structure_status": f["structure_status"]}, ["STRUCTURE_STATUS_UNAVAILABLE"] if not structure_known else ["PRICE_STRUCTURE_BREAKOUT_RULE"]),
        _evaluation("BREAKOUT_FAILURE", None if f["breakout_event"] is None else f["breakout_event"] == "BREAKOUT_FAILURE", "SHADOW_ONLY", {"breakout_event": f["breakout_event"]}, ["BREAKOUT_EVENT_UNAVAILABLE"] if f["breakout_event"] is None else ["SESSION_OVER_SESSION_BREAKOUT_FAILURE_RULE"]),
        _evaluation("EARLY_REVERSAL_STRUCTURE", None if f["entry_state"] is None else f["entry_state"] == "EARLY_REVERSAL_CANDIDATE", "SHADOW_ONLY", {"entry_state": f["entry_state"]}, ["ENTRY_STATE_UNAVAILABLE"] if f["entry_state"] is None else ["PRIMARY_ENTRY_STATE_PASSTHROUGH"]),
        _evaluation("RELATIVE_STRENGTH_LEADER", None if f["market_relative_momentum_bucket"] is None else f["market_relative_momentum_bucket"] == "UPPER_QUARTILE", "SHADOW_ONLY", {"market_relative_momentum_bucket": f["market_relative_momentum_bucket"]}, ["MARKET_RELATIVE_MOMENTUM_UNAVAILABLE"] if f["market_relative_momentum_bucket"] is None else ["CANONICAL_MARKET_RELATIVE_MOMENTUM_UPPER_QUARTILE"]),
        _evaluation("RELATIVE_STRENGTH_LAGGARD", None if f["market_relative_momentum_bucket"] is None else f["market_relative_momentum_bucket"] == "LOWER_QUARTILE", "SHADOW_ONLY", {"market_relative_momentum_bucket": f["market_relative_momentum_bucket"]}, ["MARKET_RELATIVE_MOMENTUM_UNAVAILABLE"] if f["market_relative_momentum_bucket"] is None else ["CANONICAL_MARKET_RELATIVE_MOMENTUM_LOWER_QUARTILE"]),
        _evaluation("SECTOR_LEADING", None if f["sector_leadership_state"] is None else f["sector_leadership_state"] == "LEADING", "SHADOW_ONLY", {"sector_leadership_state": f["sector_leadership_state"]}, ["SECTOR_LEADERSHIP_UNAVAILABLE"] if f["sector_leadership_state"] is None else ["SECTOR_LEADERSHIP_STATE_LEADING"]),
        _evaluation("SECTOR_WEAKENING", None if f["sector_leadership_state"] is None else f["sector_leadership_state"] == "WEAKENING", "SHADOW_ONLY", {"sector_leadership_state": f["sector_leadership_state"]}, ["SECTOR_LEADERSHIP_UNAVAILABLE"] if f["sector_leadership_state"] is None else ["SECTOR_LEADERSHIP_STATE_WEAKENING"]),
        _evaluation("MARKET_REGIME_TAILWIND", None if market_breadth_state is None else market_breadth_state == "BROAD_PARTICIPATION", "SHADOW_ONLY", {"market_breadth_state": market_breadth_state}, ["MARKET_BREADTH_STATE_UNAVAILABLE"] if market_breadth_state is None else ["MARKET_BREADTH_STATE_BROAD_PARTICIPATION_CONTEXT_ONLY"]),
        _evaluation("MARKET_REGIME_HEADWIND", None if market_breadth_state is None else market_breadth_state == "DETERIORATING_BREADTH", "SHADOW_ONLY", {"market_breadth_state": market_breadth_state}, ["MARKET_BREADTH_STATE_UNAVAILABLE"] if market_breadth_state is None else ["MARKET_BREADTH_STATE_DETERIORATING_CONTEXT_ONLY"]),
        _evaluation("TECHNICAL_DETERIORATION", None if not momentum_known or f["trend_state"] is None else f["momentum_20d"] < 0 and (f["trend_state"] == "AT_OR_BELOW_MA20" or f["ma20_slope_state"] == "FALLING"), "SHADOW_ONLY", {"momentum_20d": f["momentum_20d"], "trend_state": f["trend_state"], "ma20_slope_state": f["ma20_slope_state"]}, ["MOMENTUM_OR_TREND_UNAVAILABLE"] if not momentum_known or f["trend_state"] is None else ["NEGATIVE_MOMENTUM_WITH_WEAK_TREND_OR_FALLING_SLOPE"]),
        _evaluation("PRICE_VOLUME_DISTRIBUTION_RISK", None if not return_known or f["elevated_volume"] is None else f["return_1d"] <= 0 and f["elevated_volume"] is True, "DERIVED_PROXY", {"return_1d": f["return_1d"], "elevated_volume": f["elevated_volume"]}, ["RETURN_OR_VOLUME_FLAG_UNAVAILABLE"] if not return_known or f["elevated_volume"] is None else ["NON_POSITIVE_RETURN_WITH_ABOVE_COHORT_MEDIAN_RELATIVE_VOLUME"]),
    ]


def build_artifact(*, technical_structure: Mapping[str, Any], current_descriptive: Mapping[str, Any],
                   current_screening: Mapping[str, Any], current_leadership: Mapping[str, Any],
                   tactical: Mapping[str, Any], requested_at: str) -> dict[str, Any]:
    _verify(technical_structure, "technical_structure_context", "TECHNICAL_STRUCTURE")
    _verify(current_descriptive, "market_wide_current_descriptive_research", "DESCRIPTIVE")
    _verify(current_screening, "current_market_screening_opportunity_comparison_foundation", "SCREENING")
    _verify(current_leadership, "current_market_sector_leadership_context", "LEADERSHIP")
    _verify(tactical, "watchlist_tactical_entry_classifier", "TACTICAL")

    session = current_descriptive.get("session")
    if technical_structure.get("session") != session or current_screening.get("session") != session or current_leadership.get("session") != session or tactical.get("session") != session:
        raise TacticalSetupTagsError("SESSION_MISMATCH_ACROSS_SOURCES")
    if technical_structure.get("source_artifacts", {}).get("current_descriptive") != current_descriptive.get("artifact_identity"):
        raise TacticalSetupTagsError("TECHNICAL_STRUCTURE_DESCRIPTIVE_LINEAGE_MISMATCH")

    descriptive_records = current_descriptive.get("records", {})
    structure_records = technical_structure.get("records", {})
    screening_records = current_screening.get("records", {})
    leadership_contexts = current_leadership.get("ticker_contexts", {})
    tactical_records = tactical.get("records", {})
    market_breadth_state = (current_leadership.get("market") or {}).get("current_breadth_state")

    if set(descriptive_records) != set(structure_records):
        raise TacticalSetupTagsError("DESCRIPTIVE_STRUCTURE_TICKER_SET_MISMATCH")

    records: dict[str, dict[str, Any]] = {}
    for ticker in sorted(descriptive_records):
        facts = _facts(
            ticker=ticker, structure_record=structure_records[ticker], descriptive_record=descriptive_records[ticker],
            screening_record=screening_records.get(ticker), leadership_ticker_context=leadership_contexts.get(ticker),
            entry_state=(tactical_records.get(ticker) or {}).get("entry_state"),
        )
        evaluations = _evaluate_all(facts, market_breadth_state)
        active = [item for item in evaluations if item["qualification_state"] in ("QUALIFIED_SHADOW", "QUALIFIED_LOWER_AUTHORITY")]
        unavailable = [item for item in evaluations if item["qualification_state"] == "UNAVAILABLE"]
        records[ticker] = {
            "ticker": ticker, "research_session": session, "setup_evaluations": evaluations,
            "active_setup_ids": [item["setup_id"] for item in active],
            "record_setup_state": "NO_DISTINCT_SETUP" if not active else "MULTI_LABEL_SETUP_CONTEXT" if len(active) > 1 else "SINGLE_SETUP_CONTEXT",
            "unavailable_setup_reasons": {item["setup_id"]: item["reason_codes"] for item in unavailable},
            "is_actionable": False,
        }

    label_counts = Counter(label for record in records.values() for label in record["active_setup_ids"])
    for setup_id in REGISTRY:
        label_counts.setdefault(setup_id, 0)
    state_counts = Counter(record["record_setup_state"] for record in records.values())

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "milestone": MILESTONE,
        "requested_at": requested_at, "session": session,
        "source_artifacts": {
            "technical_structure_context": technical_structure.get("artifact_identity"),
            "current_descriptive": current_descriptive.get("artifact_identity"),
            "current_screening": current_screening.get("artifact_identity"),
            "current_leadership": current_leadership.get("artifact_identity"),
            "tactical": tactical.get("artifact_identity"),
        },
        "registry": REGISTRY, "qualification_state_vocabulary": list(QUALIFICATION_STATES),
        "records": records,
        "coverage": {
            "candidate_count": len(records), "active_setup_counts": dict(sorted(label_counts.items())),
            "record_setup_state_counts": dict(sorted(state_counts.items())),
            "no_distinct_setup_count": state_counts.get("NO_DISTINCT_SETUP", 0),
        },
        "authority_boundary": {
            "not_signal_ranking_recommendation_or_expected_return": True, "market_regime_is_context_not_a_gate": True,
            "no_forced_tag_membership": True, "no_universal_relative_volume_threshold": True,
            "historical_pit_raw_as_traded_backtest": "NOT_PROMOTED",
        },
    }
    identity = content_identity(artifact)
    artifact["artifact_sha256"], artifact["artifact_identity"] = identity["artifact_sha256"], identity["artifact_identity"]
    return artifact
