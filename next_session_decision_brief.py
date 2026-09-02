"""Pure, package-local transition projection between two governed daily research sessions.

Never a new factual authority: every field below is either read verbatim from already-governed
per-session evidence (the input registry, a materialized session-operation directory, or a
published Session Bundle) or a simple, threshold-free comparison of two already-governed values
-- a delta, a set difference, or a status carried across from an existing retained record. This
module computes no score, forecast, probability, target, or sizing, and never infers a previous
session from calendar-day subtraction or filesystem mtime; session identity always comes from the
governed input registry (``config/daily_research_session_input_registry.json``) and the already
materialized ``run_manifest.json``/``ai_research_session_bundle.json`` for each side.

v2 (DAILY_INTEGRATED_DECISION_BRIEF_AND_PROSPECTIVE_FEEDBACK_V1) adds ``posture_transition``: a
per-ticker deterministic named transition between the two sessions' own already-computed
``integrated_investment_decision_product/v1`` records (``research_action_posture``/
``tactical_phase``/``decision_identity``), resolved from the same session-scoped path
``canonical_post_close_pipeline.py`` writes and ``export_ai_bundle.py`` auto-resolves. Every v1
field/section is unchanged; this is purely additive.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import daily_session_level2_package
from correlation_concentration_guard import CONTRACT_VERSION as CORRELATION_CONCENTRATION_GUARD_CONTRACT_VERSION
from daily_research_session_operations import frozen_input_identities, load_registry, registered_session_selection
from field_temporal_contract import stable_id
from multi_session_thesis_recommendation_lifecycle import CONFIRMATION_STATES as TACTICAL_CONFIRMATION_STATES
from multi_session_thesis_recommendation_lifecycle import build_artifact as build_lifecycle_artifact

CONTRACT_VERSION = "next_session_decision_brief/v2"
HIGH_PRIORITY_TIER = "PRIORITY_NOW"
AVAILABLE, PARTIAL, UNAVAILABLE, NOT_APPLICABLE = "AVAILABLE", "PARTIAL", "UNAVAILABLE", "NOT_APPLICABLE"
_CONSTRUCTIVE_TACTICAL_PHASES = frozenset({"TREND_CONTINUATION", "BREAKOUT_CONFIRMED", "RETEST_AFTER_BREAKOUT", "EXTENDED", "BASE_BUILDING"})
POSTURE_TRANSITION_LABELS = frozenset({
    "NEW_BREAKOUT", "NEW_EARLY_WATCH", "NEW_RETEST_CANDIDATE", "WAIT_TO_INITIATE", "EARLY_WATCH_TO_INITIATE",
    "INITIATE_TO_HOLD", "INITIATE_TO_EXTENDED", "BREAKOUT_FAILED", "UPTREND_TO_BREAKDOWN", "AVOID_TO_RECOVERY_WATCH",
    "POSTURE_UNCHANGED", "NEWLY_AVAILABLE", "NO_LONGER_AVAILABLE", "POSTURE_CHANGED_OTHER",
})


class NextSessionDecisionBriefError(ValueError):
    """A deliberately explicit fail-closed refusal (session/identity/hash inconsistency)."""


def _read_json(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: value for key, value in artifact.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"next_session_decision_brief:{digest}"}


def _section(*, availability: str, reason_codes: tuple[str, ...] | list[str] = (), **fields: Any) -> dict[str, Any]:
    return {"availability": availability, "reason_codes": list(reason_codes), **fields}


def _require_qualified(registry: Mapping[str, Any], session: str) -> None:
    if frozen_input_identities(registry, session) is None:
        raise NextSessionDecisionBriefError("SESSION_NOT_GOVERNED_QUALIFIED:" + session)


def _qualified_session_chain(registry: Mapping[str, Any]) -> list[str]:
    ledger = registry.get("completed_sessions") or {}
    return sorted(session for session, row in ledger.items() if isinstance(row, Mapping) and row.get("status") == "COMPLETED_RETAINED_EVIDENCE")


def _resolve_registered_artifact(*, root: Path, registry: Mapping[str, Any], session: str, name: str) -> Mapping[str, Any] | None:
    """Load one registry-tracked raw input artifact for ``session``, fail closed on a hash lie."""
    selection = registered_session_selection(registry, session)
    entry = selection.get(name)
    if entry is None:
        return None
    value = _read_json(root / entry["path"])
    if value.get("artifact_identity") != entry["artifact_identity"]:
        raise NextSessionDecisionBriefError(f"REGISTERED_ARTIFACT_IDENTITY_MISMATCH:{name}:{session}")
    return value


def _resolve_operation(*, session: str, operation_dir: Path) -> dict[str, Any]:
    """Load and cross-verify one session's already-materialized operation output. Never writes."""
    manifest_path = operation_dir / "run_manifest.json"
    if not manifest_path.is_file():
        raise NextSessionDecisionBriefError("RUN_MANIFEST_MISSING:" + session)
    manifest = _read_json(manifest_path)
    if manifest.get("market_session") != session:
        raise NextSessionDecisionBriefError("RUN_MANIFEST_SESSION_MISMATCH:" + session)
    bundle_path = operation_dir / "ai_research_session_bundle.json"
    if not bundle_path.is_file():
        raise NextSessionDecisionBriefError("SESSION_BUNDLE_MISSING:" + session)
    bundle = _read_json(bundle_path)
    if bundle.get("session") != session or bundle.get("operation_identity") != manifest.get("operation_identity"):
        raise NextSessionDecisionBriefError("SESSION_BUNDLE_OPERATION_IDENTITY_MISMATCH:" + session)
    if bundle.get("product_identity") != (manifest.get("outputs") or {}).get("daily_product"):
        raise NextSessionDecisionBriefError("SESSION_BUNDLE_PRODUCT_IDENTITY_MISMATCH:" + session)
    queue_path = operation_dir / "daily_opportunity_decision_queue_artifact.json"
    queue = _read_json(queue_path) if queue_path.is_file() else None
    if queue is not None:
        if queue.get("research_session") != session:
            raise NextSessionDecisionBriefError("OPPORTUNITY_QUEUE_SESSION_MISMATCH:" + session)
        expected_queue_identity = (manifest.get("outputs") or {}).get("daily_opportunity_decision_queue")
        if expected_queue_identity is not None and queue.get("artifact_identity") != expected_queue_identity:
            raise NextSessionDecisionBriefError("OPPORTUNITY_QUEUE_IDENTITY_MISMATCH:" + session)
    return {
        "session": session,
        "manifest": manifest,
        "bundle": bundle,
        "bundle_sha256": _sha256_file(bundle_path),
        "queue": queue,
    }


def _delta_label(previous: float | None, current: float | None) -> str:
    if previous is None or current is None:
        return "INSUFFICIENT_EVIDENCE"
    if current > previous:
        return "IMPROVING"
    if current < previous:
        return "WEAKENING"
    return "UNCHANGED"


def _breadth_view(breadth: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "advancing": breadth.get("advancing"),
        "declining": breadth.get("declining"),
        "unchanged": breadth.get("unchanged"),
        "advance_ratio": breadth.get("advance_ratio"),
        "breadth_descriptor": (breadth.get("breadth_descriptor") or {}).get("descriptor"),
        "momentum_descriptor": (breadth.get("momentum_descriptor") or {}).get("descriptor"),
        "same_session_technical_feature_available_count": breadth.get("same_session_technical_feature_available_count"),
        "current_active_equity_denominator": breadth.get("current_active_equity_denominator"),
        "observed_session_cohort": breadth.get("observed_session_cohort"),
    }


def _market_transition(*, root: Path, registry: Mapping[str, Any], current_session: str, previous_session: str | None) -> dict[str, Any]:
    current_descriptive = _resolve_registered_artifact(root=root, registry=registry, session=current_session, name="descriptive")
    if current_descriptive is None:
        return _section(availability=UNAVAILABLE, reason_codes=["CURRENT_DESCRIPTIVE_ARTIFACT_NOT_REGISTERED"], previous=None, current=None, transition=None)
    current_view = _breadth_view(current_descriptive["market_breadth"])
    lineage = {"current_descriptive_artifact_identity": current_descriptive.get("artifact_identity")}
    if previous_session is None:
        return _section(availability=UNAVAILABLE, reason_codes=["NO_PREVIOUS_QUALIFIED_SESSION"], previous=None, current=current_view, transition="INITIAL_OBSERVATION", source_lineage=lineage)
    previous_descriptive = _resolve_registered_artifact(root=root, registry=registry, session=previous_session, name="descriptive")
    if previous_descriptive is None:
        return _section(availability=PARTIAL, reason_codes=["PREVIOUS_DESCRIPTIVE_ARTIFACT_NOT_REGISTERED"], previous=None, current=current_view, transition=None, source_lineage=lineage)
    previous_view = _breadth_view(previous_descriptive["market_breadth"])
    lineage["previous_descriptive_artifact_identity"] = previous_descriptive.get("artifact_identity")
    ratio_delta_raw = (
        current_view["advance_ratio"] - previous_view["advance_ratio"]
        if isinstance(current_view["advance_ratio"], (int, float)) and isinstance(previous_view["advance_ratio"], (int, float))
        else None
    )
    return _section(
        availability=AVAILABLE,
        previous=previous_view,
        current=current_view,
        transition={
            "advance_ratio_direction": _delta_label(previous_view["advance_ratio"], current_view["advance_ratio"]),
            # Explicitly named and unit-labeled so a reader never has to guess what a bare
            # "delta" means or infer units from magnitude: advance_ratio is a 0-1 share, so
            # the raw delta and its *100 percentage-point restatement are both spelled out.
            "advance_ratio_delta_raw": ratio_delta_raw,
            "advance_ratio_delta_percentage_points": ratio_delta_raw * 100 if ratio_delta_raw is not None else None,
            "technical_covered_count_previous": previous_view["same_session_technical_feature_available_count"],
            "technical_covered_count_current": current_view["same_session_technical_feature_available_count"],
            "technical_covered_count_delta": current_view["same_session_technical_feature_available_count"] - previous_view["same_session_technical_feature_available_count"],
            "observed_session_cohort_previous": previous_view["observed_session_cohort"],
            "observed_session_cohort_current": current_view["observed_session_cohort"],
            "observed_session_cohort_delta": current_view["observed_session_cohort"] - previous_view["observed_session_cohort"],
        },
        source_lineage=lineage,
    )


def _sector_view(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {"status": "NOT_PRESENT", "advance_ratio": None, "advancing": None, "declining": None, "same_session_eligible_count": None}
    if row.get("status") != "AVAILABLE":
        return {"status": row.get("status"), "advance_ratio": None, "advancing": None, "declining": None, "same_session_eligible_count": row.get("same_session_eligible_count")}
    return {"status": "AVAILABLE", "advance_ratio": row.get("advance_ratio"), "advancing": row.get("advancing"), "declining": row.get("declining"), "same_session_eligible_count": row.get("same_session_eligible_count")}


def _sector_pair(previous_row: Mapping[str, Any] | None, current_row: Mapping[str, Any] | None) -> dict[str, Any]:
    previous_view = _sector_view(previous_row) if previous_row is not None else None
    current_view = _sector_view(current_row) if current_row is not None else None
    if previous_row is None and current_row is not None:
        transition = "INITIAL_OBSERVATION"
    elif current_row is None:
        transition = "INSUFFICIENT_EVIDENCE"
    elif previous_view["status"] != "AVAILABLE" or current_view["status"] != "AVAILABLE":
        transition = "INSUFFICIENT_EVIDENCE"
    else:
        transition = _delta_label(previous_view["advance_ratio"], current_view["advance_ratio"])
    return {"previous": previous_view, "current": current_view, "transition": transition}


def _sector_counts(descriptive: Mapping[str, Any]) -> dict[str, int]:
    breadth = descriptive["sector_breadth"]
    return {"sector_count_total": breadth.get("sector_count_total"), "sector_count_available": breadth.get("sector_count_available")}


def _sector_transition(*, root: Path, registry: Mapping[str, Any], current_session: str, previous_session: str | None) -> dict[str, Any]:
    current_descriptive = _resolve_registered_artifact(root=root, registry=registry, session=current_session, name="descriptive")
    if current_descriptive is None:
        return _section(availability=UNAVAILABLE, reason_codes=["CURRENT_DESCRIPTIVE_ARTIFACT_NOT_REGISTERED"], sectors={})
    current_sectors = current_descriptive["sector_breadth"]["sectors"]
    if previous_session is None:
        sectors = {key: _sector_pair(None, row) for key, row in sorted(current_sectors.items())}
        return _section(availability=UNAVAILABLE, reason_codes=["NO_PREVIOUS_QUALIFIED_SESSION"], sectors=sectors, current_counts=_sector_counts(current_descriptive))
    previous_descriptive = _resolve_registered_artifact(root=root, registry=registry, session=previous_session, name="descriptive")
    if previous_descriptive is None:
        return _section(availability=PARTIAL, reason_codes=["PREVIOUS_DESCRIPTIVE_ARTIFACT_NOT_REGISTERED"], sectors={}, current_counts=_sector_counts(current_descriptive))
    previous_sectors = previous_descriptive["sector_breadth"]["sectors"]
    sectors = {key: _sector_pair(previous_sectors.get(key), current_sectors.get(key)) for key in sorted(set(current_sectors) | set(previous_sectors))}
    return _section(
        availability=AVAILABLE,
        sectors=sectors,
        previous_counts=_sector_counts(previous_descriptive),
        current_counts=_sector_counts(current_descriptive),
        source_lineage={"previous_descriptive_artifact_identity": previous_descriptive.get("artifact_identity"), "current_descriptive_artifact_identity": current_descriptive.get("artifact_identity")},
    )


def _opportunity_transition(current_queue: Mapping[str, Any] | None, previous_queue: Mapping[str, Any] | None) -> dict[str, Any]:
    empty_sets = {"new_entry_relevant": [], "persisting_entry_relevant": [], "lost_entry_relevant": [], "new_high_priority": [], "persisting_high_priority": [], "lost_high_priority": []}
    if current_queue is None:
        return _section(availability=UNAVAILABLE, reason_codes=["CURRENT_OPPORTUNITY_QUEUE_NOT_MATERIALIZED"], **empty_sets)
    current_records = current_queue.get("records") or {}
    current_entry_relevant = {ticker for ticker, row in current_records.items() if row.get("entry_relevant")}
    current_high_priority = {ticker for ticker, row in current_records.items() if row.get("research_priority_tier") == HIGH_PRIORITY_TIER}
    if previous_queue is None:
        return _section(
            availability=UNAVAILABLE,
            reason_codes=["NO_PREVIOUS_QUALIFIED_OPPORTUNITY_QUEUE"],
            **empty_sets,
            current_entry_relevant_count=len(current_entry_relevant),
            current_high_priority_count=len(current_high_priority),
            source_lineage={"current_opportunity_decision_queue_identity": current_queue.get("artifact_identity")},
        )
    previous_records = previous_queue.get("records") or {}
    previous_entry_relevant = {ticker for ticker, row in previous_records.items() if row.get("entry_relevant")}
    previous_high_priority = {ticker for ticker, row in previous_records.items() if row.get("research_priority_tier") == HIGH_PRIORITY_TIER}
    return _section(
        availability=AVAILABLE,
        new_entry_relevant=sorted(current_entry_relevant - previous_entry_relevant),
        persisting_entry_relevant=sorted(current_entry_relevant & previous_entry_relevant),
        lost_entry_relevant=sorted(previous_entry_relevant - current_entry_relevant),
        new_high_priority=sorted(current_high_priority - previous_high_priority),
        persisting_high_priority=sorted(current_high_priority & previous_high_priority),
        lost_high_priority=sorted(previous_high_priority - current_high_priority),
        # Explicit counts on both sides, alongside the artifact identities, so a mismatch
        # against any other computation is mechanically diagnosable without re-deriving the
        # sets by hand: a caller comparing against a different (e.g. stale/narrower) queue
        # artifact will see it immediately in record_count/entry_relevant_count here.
        source_lineage={
            "previous_opportunity_decision_queue_identity": previous_queue.get("artifact_identity"),
            "current_opportunity_decision_queue_identity": current_queue.get("artifact_identity"),
            "previous_record_count": len(previous_records),
            "current_record_count": len(current_records),
            "previous_entry_relevant_count": len(previous_entry_relevant),
            "current_entry_relevant_count": len(current_entry_relevant),
            "previous_high_priority_count": len(previous_high_priority),
            "current_high_priority_count": len(current_high_priority),
        },
    )


def _lifecycle_compact_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ticker": record["ticker"],
        "thesis_lifecycle_state": record["thesis_lifecycle_state"],
        "material_change": record["material_change"],
        "material_change_reasons": record["material_change_reasons"],
        "missing_dimensions": record["missing_dimensions"],
        "reason_codes": record["reason_codes"],
    }


def _lifecycle_section(current_bundle: Mapping[str, Any], previous_bundle: Mapping[str, Any] | None, qualified_chain: list[str]) -> dict[str, Any]:
    try:
        artifact = build_lifecycle_artifact(previous_bundle=previous_bundle, current_bundle=current_bundle, qualified_session_chain=qualified_chain)
    except ValueError as exc:
        return _section(availability=UNAVAILABLE, reason_codes=["LIFECYCLE_BUILD_REFUSED:" + str(exc)], records={})
    if previous_bundle is None:
        availability, reason_codes = UNAVAILABLE, ["NO_PREVIOUS_QUALIFIED_SESSION_INITIAL_OBSERVATION_ONLY"]
    else:
        availability, reason_codes = AVAILABLE, []
    return _section(
        availability=availability,
        reason_codes=reason_codes,
        lifecycle_artifact_identity=artifact.get("artifact_identity"),
        denominator=artifact["denominator"],
        comparable_count=artifact["comparable_count"],
        lifecycle_state_counts=artifact["coverage"]["lifecycle_states"],
        material_change_count=artifact["coverage"]["material_change_count"],
        tactical_confirmation_transition_counts=artifact["coverage"]["tactical_transitions"],
        records={ticker: _lifecycle_compact_record(record) for ticker, record in sorted(artifact["records"].items())},
        source_lineage={"lifecycle_artifact_identity": artifact.get("artifact_identity"), "source_artifacts": artifact.get("source_artifacts")},
    )


def _retention_pair(previous_card: Mapping[str, Any], current_card: Mapping[str, Any], retention_key: str, value_key: str) -> dict[str, Any]:
    previous_retention = previous_card.get(retention_key)
    current_retention = current_card.get(retention_key)
    previous_status = previous_retention.get("status") if isinstance(previous_retention, Mapping) else None
    current_status = current_retention.get("status") if isinstance(current_retention, Mapping) else None
    if previous_status != "RETAINED":
        reason = "MISSING_PREVIOUS_CONTEXT" if previous_retention is None else f"PREVIOUS_{previous_status}"
        return {"availability": PARTIAL if current_status == "RETAINED" else UNAVAILABLE, "reason_codes": [reason], "previous": None, "current": current_card.get(value_key) if current_status == "RETAINED" else None, "transition": None}
    if current_status != "RETAINED":
        reason = "MISSING_CURRENT_CONTEXT" if current_retention is None else f"CURRENT_{current_status}"
        return {"availability": UNAVAILABLE, "reason_codes": [reason], "previous": previous_card.get(value_key), "current": None, "transition": None}
    previous_value, current_value = previous_card.get(value_key), current_card.get(value_key)
    return {"availability": AVAILABLE, "reason_codes": [], "previous": previous_value, "current": current_value, "transition": "STATE_CHANGED" if previous_value != current_value else "UNCHANGED"}


def _retention_transition(current_bundle: Mapping[str, Any], previous_bundle: Mapping[str, Any] | None, retention_key: str, value_key: str) -> dict[str, Any]:
    current_contexts = current_bundle.get("ticker_research_contexts") or {}
    if previous_bundle is None:
        return _section(availability=UNAVAILABLE, reason_codes=["NO_PREVIOUS_QUALIFIED_SESSION"], comparable_count=0, records={})
    previous_contexts = previous_bundle.get("ticker_research_contexts") or {}
    comparable = sorted(set(current_contexts) & set(previous_contexts))
    records = {ticker: _retention_pair(previous_contexts[ticker], current_contexts[ticker], retention_key, value_key) for ticker in comparable}
    statuses = {record["availability"] for record in records.values()}
    if not statuses:
        availability, reason_codes = UNAVAILABLE, ["NO_COMPARABLE_TICKERS_BETWEEN_SESSIONS"]
    elif statuses == {AVAILABLE}:
        availability, reason_codes = AVAILABLE, []
    elif statuses <= {UNAVAILABLE}:
        availability, reason_codes = UNAVAILABLE, ["NO_COMPARABLE_RECORD_RETAINS_PREVIOUS_CONTEXT"]
    else:
        availability, reason_codes = PARTIAL, ["SOME_COMPARABLE_RECORDS_MISSING_PREVIOUS_OR_CURRENT_CONTEXT"]
    return _section(availability=availability, reason_codes=reason_codes, comparable_count=len(comparable), records=records)


def _tactical_transition(*, root: Path, registry: Mapping[str, Any], current_session: str, previous_session: str | None) -> dict[str, Any]:
    empty_sets = {"gained_confirmation": [], "retained_confirmation": [], "lost_confirmation": []}
    current_tactical = _resolve_registered_artifact(root=root, registry=registry, session=current_session, name="tactical")
    if current_tactical is None:
        return _section(availability=UNAVAILABLE, reason_codes=["CURRENT_TACTICAL_ARTIFACT_NOT_REGISTERED"], confirmation_states=sorted(TACTICAL_CONFIRMATION_STATES), **empty_sets)
    current_records = current_tactical.get("records") or {}
    current_confirmed = {ticker for ticker, row in current_records.items() if row.get("entry_state") in TACTICAL_CONFIRMATION_STATES}
    if previous_session is None:
        return _section(availability=UNAVAILABLE, reason_codes=["NO_PREVIOUS_QUALIFIED_SESSION"], confirmation_states=sorted(TACTICAL_CONFIRMATION_STATES), current_confirmed_count=len(current_confirmed), **empty_sets)
    previous_tactical = _resolve_registered_artifact(root=root, registry=registry, session=previous_session, name="tactical")
    if previous_tactical is None:
        return _section(availability=PARTIAL, reason_codes=["PREVIOUS_TACTICAL_ARTIFACT_NOT_REGISTERED"], confirmation_states=sorted(TACTICAL_CONFIRMATION_STATES), **empty_sets)
    previous_records = previous_tactical.get("records") or {}
    previous_confirmed = {ticker for ticker, row in previous_records.items() if row.get("entry_state") in TACTICAL_CONFIRMATION_STATES}
    return _section(
        availability=AVAILABLE,
        confirmation_states=sorted(TACTICAL_CONFIRMATION_STATES),
        gained_confirmation=sorted(current_confirmed - previous_confirmed),
        retained_confirmation=sorted(current_confirmed & previous_confirmed),
        lost_confirmation=sorted(previous_confirmed - current_confirmed),
        source_lineage={
            "previous_tactical_artifact_identity": previous_tactical.get("artifact_identity"),
            "current_tactical_artifact_identity": current_tactical.get("artifact_identity"),
            "previous_record_count": len(previous_records),
            "current_record_count": len(current_records),
            "previous_confirmed_count": len(previous_confirmed),
            "current_confirmed_count": len(current_confirmed),
        },
    )


def _correlation_concentration_context() -> dict[str, Any]:
    return _section(
        availability=NOT_APPLICABLE,
        reason_codes=["NO_QUALIFIED_PAIR_BOUND_C2_ARTIFACT", "ENGINE_REQUIRES_EXPLICIT_SECURITY_SET_AND_LOOKBACK"],
        engine_contract_version_reference=CORRELATION_CONCENTRATION_GUARD_CONTRACT_VERSION,
    )


def _watch_conditions(current_bundle: Mapping[str, Any]) -> dict[str, Any]:
    contexts = current_bundle.get("ticker_research_contexts") or {}
    conditions: list[dict[str, Any]] = []
    for ticker in sorted(contexts):
        card = contexts[ticker]
        trigger, invalidation = card.get("trigger"), card.get("invalidation")
        if trigger:
            conditions.append({"ticker": ticker, "condition_type": "TRIGGER", "source_text": trigger, "if_satisfied": "REEVALUATE_CLASSIFICATION"})
        if invalidation:
            conditions.append({"ticker": ticker, "condition_type": "INVALIDATION", "source_text": invalidation, "if_satisfied": "FLAG_INVALIDATION"})
    return _section(
        availability=AVAILABLE if conditions else UNAVAILABLE,
        reason_codes=[] if conditions else ["NO_CURRENT_SESSION_TRIGGER_OR_INVALIDATION_TEXT"],
        conditions=conditions,
        no_forecast=True,
        no_probability=True,
        no_target_price=True,
    )


def _classify_posture_transition(previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None) -> str:
    """Deterministic (previous, current) integrated-decision-record pair -> named transition.

    A pure lookup over the two sessions' own already-computed research_action_posture/
    tactical_phase; never infers a causal story. UPTREND_TO_BREAKDOWN is checked first since it is
    a tactical_phase signal that can co-occur with several different posture pairs. The specific
    named pairs (WAIT_TO_INITIATE, EARLY_WATCH_TO_INITIATE, INITIATE_TO_HOLD, INITIATE_TO_EXTENDED,
    BREAKOUT_FAILED, AVOID_TO_RECOVERY_WATCH) win over the more general NEW_*/POSTURE_CHANGED_OTHER
    buckets.
    """
    if current is None:
        return "NO_LONGER_AVAILABLE"
    if previous is None:
        return "NEWLY_AVAILABLE"
    prev_posture, curr_posture = previous.get("research_action_posture"), current.get("research_action_posture")
    prev_phase, curr_phase = previous.get("tactical_phase"), current.get("tactical_phase")
    if prev_phase in _CONSTRUCTIVE_TACTICAL_PHASES and curr_phase == "BREAKDOWN":
        return "UPTREND_TO_BREAKDOWN"
    if prev_posture == curr_posture:
        return "POSTURE_UNCHANGED"
    if prev_posture == "WAIT_FOR_CONFIRMATION" and curr_posture == "INITIATE_ON_BREAKOUT":
        return "WAIT_TO_INITIATE"
    if prev_posture == "EARLY_WATCH" and curr_posture == "INITIATE_ON_BREAKOUT":
        return "EARLY_WATCH_TO_INITIATE"
    if prev_posture == "INITIATE_ON_BREAKOUT" and curr_posture == "HOLD":
        return "INITIATE_TO_HOLD"
    if prev_posture == "INITIATE_ON_BREAKOUT" and curr_posture == "HOLD_DO_NOT_ADD":
        return "INITIATE_TO_EXTENDED"
    if prev_posture == "INITIATE_ON_BREAKOUT" and curr_posture in ("WAIT_FOR_CONFIRMATION", "AVOID", "REDUCE"):
        return "BREAKOUT_FAILED"
    if prev_posture == "AVOID" and curr_posture in ("EARLY_WATCH", "WAIT_FOR_CONFIRMATION"):
        return "AVOID_TO_RECOVERY_WATCH"
    if curr_posture == "INITIATE_ON_BREAKOUT":
        return "NEW_BREAKOUT"
    if curr_posture == "EARLY_WATCH":
        return "NEW_EARLY_WATCH"
    if curr_posture == "ACCUMULATE_ON_RETEST":
        return "NEW_RETEST_CANDIDATE"
    return "POSTURE_CHANGED_OTHER"


def _resolve_integrated_decision_artifact(root: Path, session: str | None) -> Mapping[str, Any] | None:
    """Load the per-session integrated_investment_decision_product/v1 artifact if materialized.

    Same canonical session-scoped path canonical_post_close_pipeline.py writes and
    export_ai_bundle.py auto-resolves from (daily_session_level2_package.session_artifact_paths);
    fails soft to None (not yet materialized) rather than guessing a different session's artifact.
    """
    if not session:
        return None
    path = daily_session_level2_package.session_artifact_paths(root, session)["integrated_investment_decision_product"]
    if not path.is_file():
        return None
    artifact = _read_json(path)
    if artifact.get("session") != session:
        raise NextSessionDecisionBriefError(f"INTEGRATED_DECISION_ARTIFACT_SESSION_MISMATCH:expected={session}:observed={artifact.get('session')}")
    return artifact


def _posture_transition(*, root: Path, current_session: str, previous_session: str | None) -> dict[str, Any]:
    current_integrated = _resolve_integrated_decision_artifact(root, current_session)
    if current_integrated is None:
        return _section(availability=UNAVAILABLE, reason_codes=["CURRENT_INTEGRATED_DECISION_ARTIFACT_NOT_MATERIALIZED"], transition_counts={}, records={})
    current_records = current_integrated.get("records") or {}
    if previous_session is None:
        return _section(
            availability=UNAVAILABLE, reason_codes=["NO_PREVIOUS_QUALIFIED_SESSION"], transition_counts={}, records={},
            current_universe_count=len(current_records),
            source_lineage={"current_integrated_decision_identity": current_integrated.get("artifact_identity")},
        )
    previous_integrated = _resolve_integrated_decision_artifact(root, previous_session)
    if previous_integrated is None:
        return _section(
            availability=PARTIAL, reason_codes=["PREVIOUS_INTEGRATED_DECISION_ARTIFACT_NOT_MATERIALIZED"], transition_counts={}, records={},
            current_universe_count=len(current_records),
            source_lineage={"current_integrated_decision_identity": current_integrated.get("artifact_identity")},
        )
    previous_records = previous_integrated.get("records") or {}
    records: dict[str, Any] = {}
    counts: Counter = Counter()
    for ticker in sorted(set(current_records) | set(previous_records)):
        prev_rec, curr_rec = previous_records.get(ticker), current_records.get(ticker)
        label = _classify_posture_transition(prev_rec, curr_rec)
        counts[label] += 1
        records[ticker] = {
            "transition": label,
            "previous_posture": (prev_rec or {}).get("research_action_posture"),
            "current_posture": (curr_rec or {}).get("research_action_posture"),
            "previous_tactical_phase": (prev_rec or {}).get("tactical_phase"),
            "current_tactical_phase": (curr_rec or {}).get("tactical_phase"),
            "previous_decision_identity": (prev_rec or {}).get("decision_identity"),
            "current_decision_identity": (curr_rec or {}).get("decision_identity"),
        }
    return _section(
        availability=AVAILABLE,
        transition_counts=dict(sorted(counts.items())),
        records=records,
        current_universe_count=len(current_records),
        previous_universe_count=len(previous_records),
        source_lineage={
            "previous_integrated_decision_identity": previous_integrated.get("artifact_identity"),
            "current_integrated_decision_identity": current_integrated.get("artifact_identity"),
        },
    )


def build_artifact(
    *,
    root: Path,
    current_session: str,
    current_source: Path,
    previous_session: str | None = None,
    previous_source: Path | None = None,
    run_identity: str | None = None,
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one next_session_decision_brief/v1 artifact. Never mutates Producer evidence."""
    registry = registry if registry is not None else load_registry(root)
    _require_qualified(registry, current_session)
    current = _resolve_operation(session=current_session, operation_dir=current_source)

    if (previous_session is None) != (previous_source is None):
        raise NextSessionDecisionBriefError("PREVIOUS_SESSION_AND_SOURCE_MUST_BOTH_BE_GIVEN_OR_BOTH_ABSENT")
    previous: dict[str, Any] | None = None
    if previous_session is not None and previous_source is not None:
        if previous_session >= current_session:
            raise NextSessionDecisionBriefError("PREVIOUS_SESSION_NOT_STRICTLY_BEFORE_CURRENT_SESSION")
        _require_qualified(registry, previous_session)
        previous = _resolve_operation(session=previous_session, operation_dir=previous_source)

    resolved_previous_session = previous["session"] if previous else None
    qualified_chain = _qualified_session_chain(registry)

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "current_session": current_session,
        "previous_qualified_session": resolved_previous_session,
        "binding": {
            "run_identity": run_identity,
            "run_identity_availability": AVAILABLE if run_identity else UNAVAILABLE,
            "run_identity_reason_codes": [] if run_identity else ["NO_PRODUCER_RUN_BINDING_REPLAY_OR_NON_PRODUCER_CONTEXT"],
            "operation_identity": current["manifest"].get("operation_identity"),
            "current_session_bundle": {"identity": current["bundle"].get("operation_identity"), "sha256": current["bundle_sha256"]},
            "previous_session_bundle": {"identity": previous["bundle"].get("operation_identity"), "sha256": previous["bundle_sha256"]} if previous else None,
        },
        "market_transition": _market_transition(root=root, registry=registry, current_session=current_session, previous_session=resolved_previous_session),
        "sector_transition": _sector_transition(root=root, registry=registry, current_session=current_session, previous_session=resolved_previous_session),
        "opportunity_transition": _opportunity_transition(current["queue"], previous["queue"] if previous else None),
        "lifecycle": _lifecycle_section(current["bundle"], previous["bundle"] if previous else None, qualified_chain),
        "recommendation_transition": _retention_transition(current["bundle"], previous["bundle"] if previous else None, "recommendation_retention", "recommendation"),
        "invalidation_transition": _retention_transition(current["bundle"], previous["bundle"] if previous else None, "fundamental_invalidation_retention", "fundamental_invalidation"),
        "tactical_transition": _tactical_transition(root=root, registry=registry, current_session=current_session, previous_session=resolved_previous_session),
        "posture_transition": _posture_transition(root=root, current_session=current_session, previous_session=resolved_previous_session),
        "correlation_concentration_context": _correlation_concentration_context(),
        "next_session_watch_conditions": _watch_conditions(current["bundle"]),
        "authority_boundary": {
            "derived_evidence_not_new_factual_authority": True,
            "supersedes_session_bundle_authority": False,
            "is_actionable": False,
            "no_forecast": True,
            "no_probability": True,
            "no_target_price": True,
            "no_sizing": True,
        },
    }
    artifact.update(content_identity(artifact))
    return artifact


def build_from_previous_bundle_path(
    *,
    root: Path,
    session: str,
    source: Path,
    previous: Path | None = None,
    run_identity: str | None = None,
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convenience entry point mirroring ``ai_handoff_publication.build_package``'s own
    ``(source, session, previous)`` convention, where ``previous`` is a path to the previous
    qualified session's own ``ai_research_session_bundle.json`` -- exactly what
    ``stocklookup.py:_previous`` already returns.
    """
    previous_session = previous_source = None
    if previous is not None:
        previous_bundle = _read_json(previous)
        previous_session = previous_bundle.get("session")
        if not isinstance(previous_session, str) or not previous_session:
            raise NextSessionDecisionBriefError("PREVIOUS_BUNDLE_SESSION_FIELD_MISSING_OR_INVALID")
        previous_source = previous.parent
    return build_artifact(
        root=root,
        current_session=session,
        current_source=source,
        previous_session=previous_session,
        previous_source=previous_source,
        run_identity=run_identity,
        registry=registry,
    )
