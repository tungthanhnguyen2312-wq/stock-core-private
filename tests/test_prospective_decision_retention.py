from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import prospective_decision_outcome_feedback as feedback
import prospective_decision_retention as retention


def _axis(state: str = "AVAILABLE") -> dict:
    return {
        "state": state, "fitness": "AVAILABLE", "supporting_reason_codes": ["SUPPORT"],
        "contradicting_reason_codes": [], "blocker_reason_codes": [], "method": "existing/v1",
        "lineage": {"source_artifact_identity": "source:1"},
    }


def _condition(role: str, *, operator: str = "FUTURE_CLOSE_GT_RESISTANCE_LEVEL") -> dict:
    return retention.serialize_boundary_condition({
        "status": "READY", "boundary_type": "BREAKOUT", "comparison_operator": operator,
        "source_metric": "resistance" if "GT" in operator else "support", "baseline_value": 100.0,
        "source_rule": "R1", "method": "watchlist_tactical_entry_classifier/v1",
        "evidence_lineage": {"technical": "retained"}, "warnings": [], "reason": "Existing rule.",
    }, role=role, source_strategy_identity="tactical-boundaries:1")


def _decision(session: str, *, decision_identity: str = "decision:FPT:one", axes: bool = True) -> dict:
    return {
        "ticker": "FPT", "as_of_session": session, "decision_identity": decision_identity,
        "research_action_posture": "WAIT_FOR_CONFIRMATION", "why_now": "Retained T0 rationale.",
        "priority_posture_reconciliation": {"research_priority_tier": "PRIORITY_NOW"},
        "evidence_axis_coherence": {"state": "ALIGNED"},
        "evidence_axes": {name: _axis() for name in retention.REQUIRED_AXES} if axes else {},
        "trigger": {"trigger_state": "APPROACHING", "condition": _condition("trigger")},
        "invalidation": {"invalidation_level": 90.0, "condition": _condition("invalidation", operator="FUTURE_CLOSE_LT_SUPPORT_LEVEL")},
        "source_identities": {"technical_structure_identity": "structure:1"},
    }


def _price_snapshot(session: str, close: float) -> dict:
    return {
        "resolved_completed_session": session, "snapshot_identity": f"price:{session}",
        "records": {"FPT": {"observations": [{
            "session": session, "close": close, "provider": "DNSE", "dataset": "OHLC",
            "price_basis": "CURRENT_DESCRIPTIVE", "transformation_identity": "normalization/v1",
            "qualification": "CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY",
        }]}},
    }


def _integrated(session: str, *, decision_identity: str = "decision:FPT:one", axes: bool = True) -> dict:
    return {
        "contract_version": "integrated_investment_decision_product/v1", "session": session,
        "artifact_identity": f"integrated:{session}:{decision_identity}", "artifact_sha256": "x" * 64,
        "records": {"FPT": _decision(session, decision_identity=decision_identity, axes=axes)},
    }


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _bind(root: Path, snapshot: dict) -> None:
    session = snapshot["session"]
    operation_identity = snapshot["daily_session_operation_identity"]
    _write(root / "operations-review" / "daily-research-session-operations-v1" / session / "run" / "run_manifest.json", {
        "market_session": session, "operation_identity": operation_identity,
        "generation_context": "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION",
    })
    _write(root / "operations-review" / "canonical-post-close-v1" / session / "session_handoff_bundle.json", {
        "session": session, "daily_session_operation_identity": operation_identity,
        "integrated_investment_decision_product_identity": snapshot["source_integrated_decision_artifact"]["artifact_identity"],
        "prospective_decision_snapshot": {"identity": snapshot["snapshot_identity"]},
    })


def _snapshot(session: str, close: float, *, decision_identity: str = "decision:FPT:one", axes: bool = True) -> dict:
    return retention.build_snapshot(
        session=session, operation_identity=f"daily-operation:{session}", producer_run_identity=f"daily-run:{session}",
        integrated_artifact=_integrated(session, decision_identity=decision_identity, axes=axes),
        exact_session_snapshot=_price_snapshot(session, close),
    )


def test_deterministic_identity_and_warm_rerun_are_append_only(tmp_path: Path):
    first = _snapshot("2026-01-02", 100.0)
    again = _snapshot("2026-01-02", 100.0)
    source_before = copy.deepcopy(_integrated("2026-01-02"))
    assert first == again
    path = retention.write_immutable_snapshot(tmp_path, first)
    assert retention.write_immutable_snapshot(tmp_path, again) == path
    assert retention.validate_snapshot(first)
    assert _integrated("2026-01-02") == source_before


def test_distinct_decision_gets_distinct_snapshot_without_overwriting_t0(tmp_path: Path):
    original = _snapshot("2026-01-02", 100.0, decision_identity="decision:FPT:original")
    changed = _snapshot("2026-01-02", 100.0, decision_identity="decision:FPT:changed")
    assert original["snapshot_identity"] != changed["snapshot_identity"]
    assert retention.write_immutable_snapshot(tmp_path, original) != retention.write_immutable_snapshot(tmp_path, changed)


def test_legacy_missing_axis_stays_field_not_retained_at_t0():
    integrated = _integrated("2026-01-02", axes=False)
    del integrated["records"]["FPT"]["evidence_axes"]
    snapshot = retention.build_snapshot(
        session="2026-01-02", operation_identity="daily-operation:2026-01-02", producer_run_identity="daily-run:2026-01-02",
        integrated_artifact=integrated, exact_session_snapshot=_price_snapshot("2026-01-02", 100.0),
    )
    item = snapshot["records"]["FPT"]["evidence_axis_snapshot"]
    assert item["status"] == retention.FIELD_NOT_RETAINED
    # The record itself is retained unchanged, so a later evaluator can tell
    # this apart from an unavailable current-market field.
    assert "evidence_axes" not in snapshot["records"]["FPT"]["integrated_decision_at_t0"]


def test_narrative_or_dynamic_condition_remains_explicitly_non_evaluable():
    condition = retention.serialize_boundary_condition({
        "status": "CONDITIONAL", "boundary_type": "BASE_RESOLUTION",
        "source_metric": "ma_20_or_momentum_20d", "warnings": ["DISJUNCTIVE"],
        "reason": "Existing disjunctive rule.",
    }, role="trigger", source_strategy_identity="tactical-boundaries:1")
    assert condition["status"] == "NOT_MACHINE_EVALUABLE"
    assert "EXISTING_BOUNDARY_NOT_REDUCED_TO_NEW_TRIGGER_ENGINE" in condition["reason_codes"]


def test_modern_snapshot_is_the_t0_source_and_t_plus_one_matures_by_trading_session(tmp_path: Path):
    first = _snapshot("2026-01-02", 100.0)
    second = _snapshot("2026-01-05", 104.0)
    for snapshot in (first, second):
        retention.write_immutable_snapshot(tmp_path, snapshot)
        _bind(tmp_path, snapshot)

    # Recreate the Sep-04 regression shape: a mutable working path has a
    # different content identity than the handoff's original source.  It must
    # not replace the sealed T0 snapshot in a later feedback artifact.
    _write(tmp_path / "operations-review" / "integrated-artifacts" / "2026-01-02" / "integrated_investment_decision_product_artifact.json", {
        **_integrated("2026-01-02", decision_identity="decision:FPT:rewritten"),
        "artifact_identity": "integrated:rewritten-after-handoff",
        "requested_at": "2026-01-02T15:00:00+07:00",
    })

    artifact = feedback.build_feedback_artifact(tmp_path)
    row = next(item for item in artifact["feedback_records"] if item["decision_session"] == "2026-01-02")
    horizon = row["forward_outcomes"]["horizons"]["forward_close_return_1"]
    assert row["t0_snapshot_identity"] == first["snapshot_identity"]
    assert row["decision_identity"] == "decision:FPT:one"
    assert horizon["status"] == "MATURE" and horizon["maturation_state"] == "MATURED"
    assert horizon["return"] == pytest.approx(0.04)
    assert row["trigger_invalidation_outcome"]["trigger"]["status"] == "SATISFIED"
    assert artifact["prospective_corpus"]["genuine_immutable_snapshot_count"] == 2


def test_corporate_intelligence_axis_is_retained_and_tracked_when_present():
    """CORPORATE_INTELLIGENCE_CATALYST_EVENT_RISK_DECISION_INTEGRATION_V1: a FUTURE modern T0
    snapshot must retain the new axis (mission Section 21) with zero code change to the
    verbatim `integrated_decision_at_t0` copy, and _axis_completeness must track it."""
    integrated = _integrated("2026-01-02", axes=True)
    integrated["records"]["FPT"]["evidence_axes"]["CORPORATE_INTELLIGENCE"] = _axis(state="CATALYST_PRESENT")
    snapshot = retention.build_snapshot(
        session="2026-01-02", operation_identity="daily-operation:2026-01-02", producer_run_identity="daily-run:2026-01-02",
        integrated_artifact=integrated, exact_session_snapshot=_price_snapshot("2026-01-02", 100.0),
    )
    item = snapshot["records"]["FPT"]["evidence_axis_snapshot"]
    assert item["corporate_intelligence_retained"] is True
    assert item["status"] == "COMPLETE"
    assert "CORPORATE_INTELLIGENCE" not in item["missing_axes"]
    # Verbatim capture requires no producer-side code change: the T0 copy already carries it.
    assert snapshot["records"]["FPT"]["integrated_decision_at_t0"]["evidence_axes"]["CORPORATE_INTELLIGENCE"]["state"] == "CATALYST_PRESENT"


def test_no_qualified_corporate_event_state_is_still_a_complete_retained_axis():
    """A definitive NO_QUALIFIED_CORPORATE_EVENT read is a resolved result, not an incomplete
    one -- it must not be conflated with the axis never having been attempted (NOT_PROVIDED)."""
    integrated = _integrated("2026-01-02", axes=True)
    integrated["records"]["FPT"]["evidence_axes"]["CORPORATE_INTELLIGENCE"] = _axis(state="NO_QUALIFIED_CORPORATE_EVENT")
    snapshot = retention.build_snapshot(
        session="2026-01-02", operation_identity="daily-operation:2026-01-02", producer_run_identity="daily-run:2026-01-02",
        integrated_artifact=integrated, exact_session_snapshot=_price_snapshot("2026-01-02", 100.0),
    )
    item = snapshot["records"]["FPT"]["evidence_axis_snapshot"]
    assert item["corporate_intelligence_retained"] is True
    assert item["status"] == "COMPLETE"


def test_legacy_snapshot_without_corporate_intelligence_axis_is_not_retrofitted():
    """A legacy (pre-milestone) integrated decision that never had a CORPORATE_INTELLIGENCE
    axis at all must not be penalized as incomplete, and must not be silently backfilled --
    mission Section 21: legacy snapshots are not reconstructed."""
    integrated = _integrated("2026-01-02", axes=True)
    assert "CORPORATE_INTELLIGENCE" not in integrated["records"]["FPT"]["evidence_axes"]
    snapshot = retention.build_snapshot(
        session="2026-01-02", operation_identity="daily-operation:2026-01-02", producer_run_identity="daily-run:2026-01-02",
        integrated_artifact=integrated, exact_session_snapshot=_price_snapshot("2026-01-02", 100.0),
    )
    item = snapshot["records"]["FPT"]["evidence_axis_snapshot"]
    assert item["corporate_intelligence_retained"] is False
    assert item["status"] == "COMPLETE"
    assert "CORPORATE_INTELLIGENCE" not in snapshot["records"]["FPT"]["integrated_decision_at_t0"]["evidence_axes"]


def test_pending_and_insufficient_depth_are_distinct():
    assert retention.maturity_state(horizon_status="PENDING_NOT_ENOUGH_FUTURE_SESSIONS", later_completed_sessions=0, required_sessions=1) == "PENDING"
    assert retention.maturity_state(horizon_status="PENDING_NOT_ENOUGH_FUTURE_SESSIONS", later_completed_sessions=1, required_sessions=5) == "INSUFFICIENT_FUTURE_DEPTH"
    assert retention.maturity_state(horizon_status="PRICE_BASIS_INCOMPATIBLE", later_completed_sessions=5, required_sessions=5) == "PRICE_SERIES_UNQUALIFIED"
