"""Live, market-wide confirmation/technical-invalidation boundaries (TACTICAL_AND_BEHAVIORAL_ENGINE_V2).

Reuses ``action_instrumentation._boundary()`` verbatim -- the same generic envelope shape (status,
boundary_type, direction, value, comparison_operator, source_metric, baseline_value,
baseline_period_session, method, evidence_lineage, warnings, reason) already proven for exactly this
purpose -- rather than duplicating it. What changes here is scope: ``action_instrumentation.py``'s
own ``execute()`` reads a single frozen 13-issuer ``operations-review/*-20260828`` snapshot triple;
this module's ``build_artifact()`` takes the current live retained artifacts directly as arguments
and runs over every ticker in the market-wide tactical cohort, with zero dependency on that frozen
snapshot or its issuer count.

Every boundary is keyed off the unmodified, still-primary ``watchlist_tactical_entry_classifier``
``entry_state`` -- this module never re-derives or replaces it. Where the classifier's own published
confirmation/invalidation text names a single clean numeric trigger (a specific MA20 or momentum-sign
comparison, or -- newly, via ``technical_structure_context.py`` -- a specific support/resistance
level), the boundary is ``READY`` with a real baseline value and comparison operator. Where the
classifier's own text is genuinely disjunctive or multi-signal, the boundary stays honestly
``CONDITIONAL`` (never collapsed into a fabricated single threshold) or ``UNAVAILABLE`` where the
state carries no directional thesis to confirm or invalidate (``SIDEWAYS_NEUTRAL``, ``DOWNTREND``'s
own confirmation). No arbitrary fixed stop percentage is introduced anywhere. These are research
boundaries for human review, never executable orders.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from action_instrumentation import _boundary

CONTRACT_VERSION = "tactical_confirmation_invalidation_boundaries/v1"
MILESTONE = "TACTICAL_AND_BEHAVIORAL_ENGINE_V2"
METHOD = "watchlist_tactical_entry_classifier/v1 + technical_structure_context/v1"


class TacticalBoundariesError(ValueError):
    """A retained input or an invariant of this contract is violated."""


def _canonical_json(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    import hashlib
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


_IDENTITY_EXCLUDED_KEYS = {"artifact_sha256", "artifact_identity", "requested_at"}  # wall-clock never enters canonical identity


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in _IDENTITY_EXCLUDED_KEYS}
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"tactical_confirmation_invalidation_boundaries:{digest}"}


def _verify(source: Mapping[str, Any], module_name: str, label: str) -> None:
    module = __import__(module_name)
    identity = module.content_identity(source)
    if source.get("artifact_sha256") != identity["artifact_sha256"]:
        raise TacticalBoundariesError(f"{label}_IDENTITY_MISMATCH")


def _context(*, tactical_record: Mapping[str, Any], descriptive_record: Mapping[str, Any], structure_record: Mapping[str, Any] | None) -> dict[str, Any]:
    values = (descriptive_record.get("technical_features") or {}).get("values") or {}
    session = (descriptive_record.get("technical_features") or {}).get("feature_as_of_session")
    structure = (structure_record or {}).get("structure_context") or {}
    structure_available = structure.get("status") == "AVAILABLE"
    return {
        "entry_state": tactical_record.get("entry_state"), "rule_id": tactical_record.get("rule_id"),
        "ma_20": values.get("ma_20"), "momentum_20d": values.get("momentum_20d"), "session": session,
        "resistance": structure.get("resistance", {}).get("value") if structure_available else None,
        "support": structure.get("support", {}).get("value") if structure_available else None,
        "structure_available": structure_available,
        "lineage": {"tactical_rule_id": tactical_record.get("rule_id"), "feature_as_of_session": session,
                    "technical_structure_available": structure_available},
    }


def _ma_boundary(*, boundary_type: str, direction: str, operator: str, ctx: Mapping[str, Any], reason: str) -> dict[str, Any]:
    if not isinstance(ctx["ma_20"], (int, float)):
        return _boundary(status="CONDITIONAL", boundary_type=boundary_type, direction=direction, source_rule=ctx["rule_id"],
                         source_metric="ma_20", as_of=ctx["session"], method=METHOD, lineage=ctx["lineage"],
                         warnings=["MA20_INPUT_UNAVAILABLE"], reason=reason)
    return _boundary(status="READY", boundary_type=boundary_type, direction=direction, value=ctx["ma_20"], unit="ADJUSTED_RETROSPECTIVE_PRICE",
                     comparison_operator=operator, source_rule=ctx["rule_id"], source_metric="ma_20", baseline_value=ctx["ma_20"],
                     baseline_period_session=ctx["session"], as_of=ctx["session"], method=METHOD, lineage=ctx["lineage"], reason=reason)


def _momentum_boundary(*, boundary_type: str, direction: str, operator: str, ctx: Mapping[str, Any], reason: str) -> dict[str, Any]:
    if not isinstance(ctx["momentum_20d"], (int, float)):
        return _boundary(status="CONDITIONAL", boundary_type=boundary_type, direction=direction, source_rule=ctx["rule_id"],
                         source_metric="momentum_20d", as_of=ctx["session"], method=METHOD, lineage=ctx["lineage"],
                         warnings=["MOMENTUM_INPUT_UNAVAILABLE"], reason=reason)
    return _boundary(status="READY", boundary_type=boundary_type, direction=direction, value=0.0, unit="RETURN_RATIO",
                     comparison_operator=operator, source_rule=ctx["rule_id"], source_metric="momentum_20d", baseline_value=ctx["momentum_20d"],
                     baseline_period_session=ctx["session"], as_of=ctx["session"], method=METHOD, lineage=ctx["lineage"], reason=reason)


def _level_boundary(*, boundary_type: str, direction: str, operator: str, level_name: str, ctx: Mapping[str, Any], reason: str,
                    fallback_reason: str | None = None) -> dict[str, Any]:
    level = ctx.get(level_name)
    if not isinstance(level, (int, float)):
        # No qualified structural level for this ticker/session; fall back to the MA20 anchor rather
        # than fabricating a level, matching this module's own no-fabrication invariant. The displayed
        # text must name the metric this fallback actually tests (MA20), never the unavailable level --
        # so a dedicated fallback_reason is required rather than reusing the level-based reason string.
        return _ma_boundary(boundary_type=boundary_type, direction=direction,
                            operator="FUTURE_CLOSE_GT_FUTURE_MA20" if "GT" in operator else "FUTURE_CLOSE_LT_FUTURE_MA20",
                            ctx=ctx, reason=(fallback_reason or reason) + " (structural level unavailable; MA20 fallback anchor.)")
    return _boundary(status="READY", boundary_type=boundary_type, direction=direction, value=level, unit="ADJUSTED_RETROSPECTIVE_PRICE",
                     comparison_operator=operator, source_rule=ctx["rule_id"], source_metric=level_name, baseline_value=level,
                     baseline_period_session=ctx["session"], as_of=ctx["session"], method="technical_structure_context/v1",
                     lineage=ctx["lineage"], reason=reason)


_UNAVAILABLE_NO_THESIS = _boundary(status="UNAVAILABLE", reason="STATE_HAS_NO_DIRECTIONAL_THESIS_TO_CONFIRM_OR_INVALIDATE")
_UNAVAILABLE_NO_EVIDENCE = _boundary(status="UNAVAILABLE", reason="ENTRY_STATE_TECHNICALLY_INELIGIBLE_NO_RETAINED_BOUNDARY")


def _boundaries_for_state(ctx: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (confirmation_boundary, technical_invalidation_boundary) for one ticker's entry_state,
    preserving each state's own published confirmation/invalidation text from
    ``watchlist_tactical_entry_classifier.py`` as the boundary's ``reason``."""
    state = ctx["entry_state"]
    if state is None:
        return _UNAVAILABLE_NO_EVIDENCE, _UNAVAILABLE_NO_EVIDENCE

    if state == "BREAKOUT_READY":
        confirmation = _level_boundary(boundary_type="BREAKOUT_EXTENSION_CONFIRMATION", direction="ABOVE_TO_CONFIRM",
            operator="FUTURE_CLOSE_GT_RESISTANCE_LEVEL", level_name="resistance", ctx=ctx,
            reason="Next session extends the move on continued above-median relative volume.")
        invalidation = _level_boundary(boundary_type="BREAKOUT_LEVEL_FAILURE", direction="BELOW_TO_INVALIDATE",
            operator="FUTURE_CLOSE_LT_RESISTANCE_LEVEL", level_name="resistance", ctx=ctx,
            reason="A session close back below the breakout's resistance level invalidates the breakout-ready classification.",
            fallback_reason="A session close back below the 20-day moving average invalidates the breakout-ready classification.")
        return confirmation, invalidation

    if state == "UPTREND_CONFIRMED":
        confirmation = _boundary(status="CONDITIONAL", boundary_type="ONGOING_TREND_CONTINUATION", direction="STATE_TRANSITION",
            source_rule=ctx["rule_id"], source_metric="ma_20_and_momentum_20d", as_of=ctx["session"], method=METHOD, lineage=ctx["lineage"],
            warnings=["NO_RETAINED_NEXT_SESSION_EXTENSION_THRESHOLD"], reason="The trend is already confirmed; the ongoing trigger is simply continued price above the 20-day moving average with 20-day momentum staying positive.")
        invalidation = _momentum_boundary(boundary_type="MOMENTUM_ROLLOVER", direction="BELOW_TO_INVALIDATE", operator="FUTURE_MOMENTUM_20D_LT_0", ctx=ctx,
            reason="20-day momentum turning negative while price is still above the 20-day moving average invalidates this classification.")
        return confirmation, invalidation

    if state == "EARLY_REVERSAL_CANDIDATE":
        confirmation = _ma_boundary(boundary_type="EARLY_REVERSAL_CONFIRMATION_MA20_RECLAIM", direction="ABOVE_TO_CONFIRM", operator="FUTURE_CLOSE_GT_FUTURE_MA20", ctx=ctx,
            reason="A reclaim of the 20-day moving average alongside continued positive 20-day momentum would confirm this as a full reversal.")
        invalidation = _momentum_boundary(boundary_type="EARLY_REVERSAL_MOMENTUM_FAILURE", direction="BELOW_TO_INVALIDATE", operator="FUTURE_MOMENTUM_20D_LT_0", ctx=ctx,
            reason="20-day momentum turning negative again invalidates the reversal signal.")
        return confirmation, invalidation

    if state == "BASE_BUILDING":
        confirmation = _boundary(status="CONDITIONAL", boundary_type="BASE_RESOLUTION", direction="ABOVE_TO_CONFIRM",
            source_rule=ctx["rule_id"], source_metric="ma_20_or_momentum_20d_or_resistance_level", as_of=ctx["session"], method=METHOD,
            lineage=ctx["lineage"], warnings=["DISJUNCTIVE_CONFIRMATION_NOT_A_SINGLE_FIXED_BOUNDARY"],
            reason="A 20-day momentum flip to positive, a provider-relative-volume-backed move back above the 20-day moving average, or a close above the base's own resistance level would confirm the base is resolving higher.")
        invalidation = _level_boundary(boundary_type="BASE_FAILURE", direction="BELOW_TO_INVALIDATE", operator="FUTURE_CLOSE_LT_SUPPORT_LEVEL", level_name="support", ctx=ctx,
            reason="A close below the base's own support level invalidates the base.",
            fallback_reason="A session close back below the 20-day moving average invalidates the base.")
        return confirmation, invalidation

    if state == "SELLING_PRESSURE_EASING":
        confirmation = _ma_boundary(boundary_type="EASING_TO_REVERSAL_UPGRADE", direction="ABOVE_TO_CONFIRM", operator="FUTURE_CLOSE_GT_FUTURE_MA20", ctx=ctx,
            reason="Price reclaiming the 20-day moving average would upgrade this to an early reversal candidate.")
        invalidation = _boundary(status="CONDITIONAL", boundary_type="RENEWED_BREAKDOWN_RISK", direction="STATE_TRANSITION",
            source_rule=ctx["rule_id"], source_metric="momentum_bucket_and_relative_volume", as_of=ctx["session"], method=METHOD,
            lineage=ctx["lineage"], warnings=["MULTI_SIGNAL_RULE_NOT_REDUCED_TO_A_SINGLE_THRESHOLD"],
            reason="A renewed drop to bottom-quartile same-session relative momentum together with an elevated-volume down session invalidates the easing read.")
        return confirmation, invalidation

    if state == "SIDEWAYS_NEUTRAL":
        confirmation = _boundary(status="CONDITIONAL", boundary_type="DIRECTIONAL_RESOLUTION", direction="STATE_TRANSITION",
            source_rule=ctx["rule_id"], source_metric="ma20_distance_and_momentum_bucket", as_of=ctx["session"], method=METHOD,
            lineage=ctx["lineage"], warnings=["MULTI_SIGNAL_RULE_NOT_REDUCED_TO_A_SINGLE_THRESHOLD"],
            reason="A decisive move away from the 20-day moving average combined with a same-session momentum quartile extreme would resolve the current lack of a directional edge.")
        return confirmation, _UNAVAILABLE_NO_THESIS

    if state == "DISTRIBUTION_RISK":
        confirmation = _ma_boundary(boundary_type="DISTRIBUTION_ROLLOVER_CONFIRMATION", direction="BELOW_TO_CONFIRM", operator="FUTURE_CLOSE_LT_FUTURE_MA20", ctx=ctx,
            reason="A session close below the 20-day moving average would confirm the momentum rollover already visible in the 20-day reading.")
        invalidation = _momentum_boundary(boundary_type="DISTRIBUTION_RECOVERY", direction="ABOVE_TO_INVALIDATE", operator="FUTURE_MOMENTUM_20D_GT_0", ctx=ctx,
            reason="A recovery of 20-day momentum back to positive while price remains above the 20-day moving average invalidates the distribution warning.")
        return confirmation, invalidation

    if state == "BREAKDOWN_RISK":
        confirmation = _level_boundary(boundary_type="BREAKDOWN_EXTENSION_CONFIRMATION", direction="BELOW_TO_CONFIRM", operator="FUTURE_CLOSE_LT_SUPPORT_LEVEL", level_name="support", ctx=ctx,
            reason="Already showing a provider-relative-volume-confirmed down session below the 20-day moving average; the remaining trigger is whether the next session continues the break.")
        invalidation = _ma_boundary(boundary_type="BREAKDOWN_RECLAIM", direction="ABOVE_TO_INVALIDATE", operator="FUTURE_CLOSE_GT_FUTURE_MA20", ctx=ctx,
            reason="A session close reclaiming the 20-day moving average invalidates the active-breakdown classification.")
        return confirmation, invalidation

    if state == "DOWNTREND":
        invalidation = _momentum_boundary(boundary_type="DOWNTREND_STABILIZATION", direction="ABOVE_TO_INVALIDATE", operator="FUTURE_MOMENTUM_20D_GT_0", ctx=ctx,
            reason="A 20-day momentum flip to positive (even before price reclaims the 20-day moving average) would be the first deterministic sign of stabilization.")
        return _UNAVAILABLE_NO_THESIS, invalidation

    return _UNAVAILABLE_NO_EVIDENCE, _UNAVAILABLE_NO_EVIDENCE


def build_artifact(*, tactical: Mapping[str, Any], current_descriptive: Mapping[str, Any],
                   technical_structure: Mapping[str, Any] | None, requested_at: str) -> dict[str, Any]:
    """Build market-wide confirmation/technical-invalidation boundaries for every ticker in
    ``tactical`` (zero silent drops). ``technical_structure`` is optional: when absent or when a
    given ticker's own structure record is unavailable, boundaries fall back to the MA20/momentum-only
    anchors -- exactly action_instrumentation.py's original technical_risk_boundary anchors -- rather
    than being blocked."""
    _verify(tactical, "watchlist_tactical_entry_classifier", "TACTICAL")
    _verify(current_descriptive, "market_wide_current_descriptive_research", "DESCRIPTIVE")
    if technical_structure is not None:
        _verify(technical_structure, "technical_structure_context", "TECHNICAL_STRUCTURE")
        if technical_structure.get("session") != current_descriptive.get("session"):
            raise TacticalBoundariesError("TECHNICAL_STRUCTURE_SESSION_MISMATCH")

    if tactical.get("session") != current_descriptive.get("session"):
        raise TacticalBoundariesError("TACTICAL_DESCRIPTIVE_SESSION_MISMATCH")
    if tactical.get("source_artifacts", {}).get("descriptive") != current_descriptive.get("artifact_identity"):
        raise TacticalBoundariesError("TACTICAL_DESCRIPTIVE_LINEAGE_MISMATCH")

    tactical_records = tactical.get("records")
    descriptive_records = current_descriptive.get("records")
    structure_records = (technical_structure or {}).get("records", {})
    if not isinstance(tactical_records, Mapping) or not isinstance(descriptive_records, Mapping):
        raise TacticalBoundariesError("SOURCE_RECORDS_INVALID")

    records: dict[str, dict[str, Any]] = {}
    for ticker in sorted(tactical_records):
        ctx = _context(tactical_record=tactical_records[ticker], descriptive_record=descriptive_records.get(ticker, {}), structure_record=structure_records.get(ticker))
        confirmation, invalidation = _boundaries_for_state(ctx)
        records[ticker] = {
            "ticker": ticker, "entry_state": ctx["entry_state"],
            "confirmation_boundary": confirmation, "technical_invalidation_boundary": invalidation,
            "structure_level_used": ctx["structure_available"],
            "reason_codes": [item for item in (confirmation.get("reason"), invalidation.get("reason")) if item],
            "warnings": sorted(set((confirmation.get("warnings") or []) + (invalidation.get("warnings") or []))),
            "authority_boundary": {"research_boundary_only": True, "not_an_executable_order": True, "decision_authority_promoted": False, "no_fixed_stop_percentage": True},
        }

    coverage = Counter()
    for record in records.values():
        for name, boundary_key in (("CONFIRMATION", "confirmation_boundary"), ("TECHNICAL_INVALIDATION", "technical_invalidation_boundary")):
            coverage[f"{name}_{record[boundary_key]['status']}"] += 1
    for name in ("CONFIRMATION", "TECHNICAL_INVALIDATION"):
        for status in ("READY", "CONDITIONAL", "UNAVAILABLE"):
            coverage.setdefault(f"{name}_{status}", 0)
    coverage["STRUCTURE_LEVEL_USED_COUNT"] = sum(record["structure_level_used"] for record in records.values())
    entry_state_counts = Counter(record["entry_state"] for record in records.values())

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "milestone": MILESTONE,
        "requested_at": requested_at, "session": current_descriptive.get("session"),
        "source_artifacts": {
            "tactical": tactical.get("artifact_identity"), "current_descriptive": current_descriptive.get("artifact_identity"),
            "technical_structure_context": (technical_structure or {}).get("artifact_identity"),
        },
        "denominator": len(records),
        "coverage": {**dict(sorted(coverage.items())), "entry_state_counts": dict(sorted((key, value) for key, value in entry_state_counts.items() if key is not None))},
        "authority_boundary": {
            "experiment_shadow_only": False, "market_wide_not_bounded_snapshot_cohort": True,
            "research_boundaries_only": True, "no_decision_authority": True, "no_fixed_stop_percentage": True,
            "no_arbitrary_price_target": True,
        },
        "records": records,
    }
    identity = content_identity(artifact)
    artifact["artifact_sha256"], artifact["artifact_identity"] = identity["artifact_sha256"], identity["artifact_identity"]
    return artifact
