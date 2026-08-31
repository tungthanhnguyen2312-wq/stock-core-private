"""Compact market-wide tactical/behavioral projection (TACTICAL_AND_BEHAVIORAL_ENGINE_V2).

One compact ``tactical_behavior_context`` record per ticker, composed entirely from
already-computed evidence: ``watchlist_tactical_entry_classifier.py`` (unmodified, still-primary
``entry_state``), ``technical_structure_context.py``, ``tactical_setup_tags.py``,
``tactical_confirmation_invalidation_boundaries.py``, and
``current_market_sector_leadership_context.py`` (the canonical market/sector regime source for this
milestone). No new computation happens here -- this module only condenses and joins. No full price
history is embedded; the detailed calculation records live in each producing module's own artifact,
referenced here only by identity.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping

CONTRACT_VERSION = "tactical_behavior_context/v1"
MILESTONE = "TACTICAL_AND_BEHAVIORAL_ENGINE_V2"


class TacticalBehaviorContextError(ValueError):
    """A retained input or an invariant of this contract is violated."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


_IDENTITY_EXCLUDED_KEYS = {"artifact_sha256", "artifact_identity", "requested_at"}  # wall-clock never enters canonical identity


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in _IDENTITY_EXCLUDED_KEYS}
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"tactical_behavior_context:{digest}"}


def _verify(source: Mapping[str, Any], module_name: str, label: str) -> None:
    module = __import__(module_name)
    identity = module.content_identity(source)
    if source.get("artifact_sha256") != identity["artifact_sha256"]:
        raise TacticalBehaviorContextError(f"{label}_IDENTITY_MISMATCH")


def _record(*, ticker: str, session: str, tactical_record: Mapping[str, Any], structure_record: Mapping[str, Any],
           setup_record: Mapping[str, Any], boundary_record: Mapping[str, Any] | None,
           leadership_context: Mapping[str, Any] | None, market_breadth_state: str | None) -> dict[str, Any]:
    structure_ctx = structure_record.get("structure_context") or {}
    contraction_ctx = structure_record.get("contraction_context") or {}
    breakout_ctx = structure_record.get("breakout_context") or {}
    trend_ctx = structure_record.get("trend_context") or {}
    relative_volume = structure_record.get("relative_volume") or {}
    active_tags = set(setup_record.get("active_setup_ids") or [])

    market_relative_bucket = sector_leadership_state = sector_relative_bucket = None
    if isinstance(leadership_context, Mapping):
        market_relative = leadership_context.get("market_relative_momentum") or {}
        if market_relative.get("status") == "AVAILABLE":
            market_relative_bucket = market_relative.get("momentum_bucket")
        sector_relative = leadership_context.get("sector_relative_momentum") or {}
        if sector_relative.get("status") == "AVAILABLE":
            sector_relative_bucket = sector_relative.get("momentum_bucket")
        sector_context = leadership_context.get("sector_leadership_context") or {}
        if sector_context.get("status") == "AVAILABLE":
            sector_leadership_state = sector_context.get("leadership_state")

    confirmation = (boundary_record or {}).get("confirmation_boundary") or {"status": "UNAVAILABLE", "reason": "BOUNDARY_ARTIFACT_NOT_SUPPLIED"}
    invalidation = (boundary_record or {}).get("technical_invalidation_boundary") or {"status": "UNAVAILABLE", "reason": "BOUNDARY_ARTIFACT_NOT_SUPPLIED"}

    blockers = list(structure_record.get("blockers") or [])
    if structure_record.get("high_low_basis", {}).get("status") == "NOT_COMPATIBLE":
        blockers.append("HIGH_LOW_BASIS_NOT_COMPATIBLE")
    reason_codes = sorted({
        *(item["reason_codes"][0] for item in setup_record.get("setup_evaluations", []) if item["qualification_state"] in ("QUALIFIED_SHADOW", "QUALIFIED_LOWER_AUTHORITY")),
        *([confirmation.get("boundary_type")] if confirmation.get("status") == "READY" else []),
        *([invalidation.get("boundary_type")] if invalidation.get("status") == "READY" else []),
    } - {None})

    return {
        "ticker": ticker, "as_of_session": session,
        "primary_entry_state": tactical_record.get("entry_state"),
        "setup_tags": sorted(active_tags),
        "trend_context": {
            "trend_state": trend_ctx.get("trend_state"), "ma20_slope_state": (trend_ctx.get("ma20_slope") or {}).get("slope_state"),
            "momentum_20d": trend_ctx.get("momentum_20d"),
        },
        "structure_context": {"structure_status": structure_ctx.get("structure_status"), "resistance": structure_ctx.get("resistance"), "support": structure_ctx.get("support")},
        "contraction_context": {
            "range_state": contraction_ctx.get("range_state"),
            "self_relative_volatility_state": (contraction_ctx.get("self_relative_volatility") or {}).get("self_relative_volatility_state"),
        },
        "breakout_failure_context": {"event": breakout_ctx.get("event")},
        "pullback_reversal_context": {
            "pullback_to_support_in_uptrend": "PULLBACK_TO_SUPPORT_IN_UPTREND" in active_tags,
            "early_reversal_structure": "EARLY_REVERSAL_STRUCTURE" in active_tags,
        },
        "relative_strength_context": {"market_relative_momentum_bucket": market_relative_bucket, "sector_relative_momentum_bucket": sector_relative_bucket},
        "price_volume_behavior": {
            "price_volume_distribution_risk": "PRICE_VOLUME_DISTRIBUTION_RISK" in active_tags,
            "relative_volume_provider_scoped": relative_volume.get("relative_volume_provider_scoped"),
        },
        "market_regime_context": {"current_breadth_state": market_breadth_state, "authority": "CONTEXT_ONLY_NOT_A_GATE"},
        "sector_context": {"leadership_state": sector_leadership_state},
        "confirmation_boundary": confirmation, "technical_invalidation_boundary": invalidation,
        "data_coverage": {
            "technical_eligible": structure_record.get("eligibility", {}).get("status") == "ELIGIBLE",
            "close_history_depth": structure_record.get("close_history_depth"),
            "leadership_context_available": leadership_context is not None,
            "boundary_available": boundary_record is not None,
        },
        "blockers": blockers, "reason_codes": reason_codes,
        "research_authority_boundary": {
            "is_actionable": False, "requires_human_review": True, "not_a_recommendation_or_execution_instruction": True,
            "no_ranking_score_probability_or_target_price": True, "no_position_sizing": True,
            "primary_entry_state_is_authoritative_this_field_is_a_pass_through": True,
        },
    }


def build_artifact(*, tactical: Mapping[str, Any], technical_structure: Mapping[str, Any], tactical_setup_tags: Mapping[str, Any],
                   confirmation_invalidation_boundaries: Mapping[str, Any] | None, current_leadership: Mapping[str, Any] | None,
                   requested_at: str) -> dict[str, Any]:
    _verify(tactical, "watchlist_tactical_entry_classifier", "TACTICAL")
    _verify(technical_structure, "technical_structure_context", "TECHNICAL_STRUCTURE")
    _verify(tactical_setup_tags, "tactical_setup_tags", "SETUP_TAGS")
    if confirmation_invalidation_boundaries is not None:
        _verify(confirmation_invalidation_boundaries, "tactical_confirmation_invalidation_boundaries", "BOUNDARIES")
    if current_leadership is not None:
        _verify(current_leadership, "current_market_sector_leadership_context", "LEADERSHIP")

    session = tactical.get("session")
    for label, artifact in (("technical_structure", technical_structure), ("tactical_setup_tags", tactical_setup_tags)):
        if artifact.get("session") != session:
            raise TacticalBehaviorContextError(f"{label.upper()}_SESSION_MISMATCH")
    if confirmation_invalidation_boundaries is not None and confirmation_invalidation_boundaries.get("session") != session:
        raise TacticalBehaviorContextError("BOUNDARIES_SESSION_MISMATCH")
    if current_leadership is not None and current_leadership.get("session") != session:
        raise TacticalBehaviorContextError("LEADERSHIP_SESSION_MISMATCH")

    tactical_records = tactical.get("records")
    structure_records = technical_structure.get("records")
    setup_records = tactical_setup_tags.get("records")
    if not isinstance(tactical_records, Mapping) or not isinstance(structure_records, Mapping) or not isinstance(setup_records, Mapping):
        raise TacticalBehaviorContextError("SOURCE_RECORDS_INVALID")
    if set(tactical_records) != set(structure_records) or set(tactical_records) != set(setup_records):
        raise TacticalBehaviorContextError("TICKER_SET_MISMATCH_ACROSS_SOURCES")

    boundary_records = (confirmation_invalidation_boundaries or {}).get("records", {})
    leadership_contexts = (current_leadership or {}).get("ticker_contexts", {})
    market_breadth_state = ((current_leadership or {}).get("market") or {}).get("current_breadth_state")

    records: dict[str, dict[str, Any]] = {}
    for ticker in sorted(tactical_records):
        records[ticker] = _record(
            ticker=ticker, session=session, tactical_record=tactical_records[ticker], structure_record=structure_records[ticker],
            setup_record=setup_records[ticker], boundary_record=boundary_records.get(ticker),
            leadership_context=leadership_contexts.get(ticker), market_breadth_state=market_breadth_state,
        )

    entry_state_counts = Counter(record["primary_entry_state"] for record in records.values())
    tag_counts = Counter(tag for record in records.values() for tag in record["setup_tags"])
    coverage = {
        "candidate_count": len(records),
        "technical_eligible_count": sum(record["data_coverage"]["technical_eligible"] for record in records.values()),
        "leadership_context_available_count": sum(record["data_coverage"]["leadership_context_available"] for record in records.values()),
        "boundary_available_count": sum(record["data_coverage"]["boundary_available"] for record in records.values()),
        "entry_state_counts": dict(sorted((key, value) for key, value in entry_state_counts.items() if key is not None)),
        "entry_state_missing_count": entry_state_counts.get(None, 0),
        "setup_tag_counts": dict(sorted(tag_counts.items())),
        "confirmation_boundary_ready_count": sum(record["confirmation_boundary"].get("status") == "READY" for record in records.values()),
        "technical_invalidation_boundary_ready_count": sum(record["technical_invalidation_boundary"].get("status") == "READY" for record in records.values()),
    }

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "milestone": MILESTONE,
        "requested_at": requested_at, "session": session,
        "source_artifacts": {
            "tactical": tactical.get("artifact_identity"), "technical_structure_context": technical_structure.get("artifact_identity"),
            "tactical_setup_tags": tactical_setup_tags.get("artifact_identity"),
            "confirmation_invalidation_boundaries": (confirmation_invalidation_boundaries or {}).get("artifact_identity"),
            "current_leadership": (current_leadership or {}).get("artifact_identity"),
        },
        "coverage": coverage,
        "blocked_outputs": {
            "ordinal_market_ranking": "RANKING_PROHIBITED", "opportunity_score": "SCORING_PROHIBITED",
            "probabilities_or_target_prices": "FORECAST_PROHIBITED", "portfolio_weights_or_position_sizes": "SIZING_NOT_IMPLEMENTED",
            "fixed_stop_percentage": "NOT_IMPLEMENTED", "exact_liquidity_or_execution_capacity": "NOT_IMPLEMENTED",
            "historical_raw_as_traded_or_pit": "RAW_AS_TRADED_NOT_PROMOTED", "backtesting": "OUT_OF_SCOPE_THIS_MILESTONE",
        },
        "authority_boundary": {
            "is_actionable": False, "requires_human_review": True, "primary_entry_state_unchanged_and_authoritative": True,
            "setup_tags_are_secondary_non_exclusive_evidence": True, "market_regime_is_context_not_a_gate": True,
            "no_full_price_history_embedded": True,
        },
        "records": records,
    }
    identity = content_identity(artifact)
    artifact["artifact_sha256"], artifact["artifact_identity"] = identity["artifact_sha256"], identity["artifact_identity"]
    return artifact
