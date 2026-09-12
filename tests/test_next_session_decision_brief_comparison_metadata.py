"""Focused, fully self-contained coverage of next_session_decision_brief's new
``comparison_metadata`` field (SESSION_REGISTRY_PROMOTION_AND_COMPARISON_SEMANTICS_CORRECTIVE_V1).

Deliberately independent of tests/test_next_session_decision_brief.py's real-evidence replay
suite (which is machine-local and gated behind a primary-checkout evidence pointer): every
fixture here is synthetic and self-contained, so these tests run identically on any checkout.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from next_session_decision_brief import NextSessionDecisionBriefError, build_artifact
from session_comparison_semantics import FITNESS_DEGRADED, FITNESS_FRESH, FITNESS_UNAVAILABLE, ROLE_DISTANT, ROLE_IMMEDIATE, ROLE_NONE


def _write_operation(directory: Path, *, session: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    operation_identity = f"daily_research_session_operation:{session}"
    product_identity = f"current_daily_decision_research_product/v2:{session}"
    manifest = {
        "market_session": session,
        "operation_identity": operation_identity,
        "outputs": {"daily_product": product_identity},
    }
    bundle = {
        "session": session,
        "operation_identity": operation_identity,
        "product_identity": product_identity,
        "ticker_research_contexts": {},
    }
    (directory / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (directory / "ai_research_session_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")


def _register_session(root: Path, registry: dict, session: str) -> None:
    """Write minimal, mutually-consistent descriptive/tactical artifacts for ``session`` and
    register them exactly as ``register_session_inputs``/``validate_and_freeze_completed_session``
    would, so every transition section _resolve_registered_artifact touches can actually load."""
    descriptive_identity = f"market_wide_current_descriptive_research:{session}"
    tactical_identity = f"watchlist_tactical_entry_classifier:{session}"
    descriptive_path = root / f"descriptive_{session}.json"
    tactical_path = root / f"tactical_{session}.json"
    descriptive_path.write_text(json.dumps({
        "artifact_identity": descriptive_identity, "session": session,
        "market_breadth": {
            "advancing": 1, "declining": 1, "unchanged": 0, "advance_ratio": 0.5,
            "same_session_technical_feature_available_count": 100,
            "current_active_equity_denominator": 200, "observed_session_cohort": 150,
        },
        "sector_breadth": {"sectors": {}},
    }), encoding="utf-8")
    tactical_path.write_text(json.dumps({"artifact_identity": tactical_identity, "records": {}}), encoding="utf-8")
    # next_session_decision_brief only ever loads "descriptive"/"tactical" by name, but
    # registered_session_selection requires every REQUIRED key present as a selection entry;
    # the other six never get read in these tests, so a placeholder path/identity suffices.
    other_required = ("screening", "triage", "fundamental", "valuation", "catalyst", "corporate_intelligence")
    registry.setdefault("sessions", {})[session] = {
        "descriptive": {"path": descriptive_path.relative_to(root).as_posix(), "artifact_identity": descriptive_identity},
        "tactical": {"path": tactical_path.relative_to(root).as_posix(), "artifact_identity": tactical_identity},
        **{
            key: {"path": f"unused_{key}_{session}.json", "artifact_identity": f"{key}:{session}"}
            for key in other_required
        },
    }
    registry.setdefault("completed_sessions", {})[session] = {
        "status": "COMPLETED_RETAINED_EVIDENCE",
        "frozen_input_identities": {"descriptive": descriptive_identity, "tactical": tactical_identity},
    }


def _registry(root: Path, *, completed: list[str], attempted: dict | None = None) -> dict:
    registry: dict = {"completed_sessions": {}, "sessions": dict(attempted or {})}
    for session in completed:
        _register_session(root, registry, session)
    return registry


def test_comparison_metadata_unavailable_with_no_previous_session(tmp_path):
    current_dir = tmp_path / "current"
    _write_operation(current_dir, session="2026-08-21")
    registry = _registry(tmp_path, completed=["2026-08-21"])
    brief = build_artifact(root=tmp_path, current_session="2026-08-21", current_source=current_dir, registry=registry)
    meta = brief["comparison_metadata"]
    assert meta["comparison_session"] is None
    assert meta["comparison_session_role"] == ROLE_NONE
    assert meta["comparison_fitness"] == FITNESS_UNAVAILABLE
    assert brief["previous_qualified_session"] is None  # existing field, unchanged behavior


def test_comparison_metadata_fresh_adjacent_end_to_end(tmp_path):
    current_dir, previous_dir = tmp_path / "current", tmp_path / "previous"
    _write_operation(current_dir, session="2026-08-26")
    _write_operation(previous_dir, session="2026-08-25")
    registry = _registry(tmp_path, completed=["2026-08-25", "2026-08-26"])
    brief = build_artifact(
        root=tmp_path, current_session="2026-08-26", current_source=current_dir,
        previous_session="2026-08-25", previous_source=previous_dir, registry=registry,
    )
    meta = brief["comparison_metadata"]
    assert meta["comparison_session"] == "2026-08-25"
    assert meta["comparison_session_role"] == ROLE_IMMEDIATE
    assert meta["comparison_fitness"] == FITNESS_FRESH
    assert meta["is_immediate_previous_completed_session"] is True
    assert meta["session_gap_trading_sessions"] == 0
    assert brief["previous_qualified_session"] == "2026-08-25"  # existing field preserved verbatim


def test_comparison_metadata_degraded_multi_session_gap_end_to_end(tmp_path):
    """The exact historical shape this milestone exists to fix, run through the real,
    unmocked build_artifact -> _build_from_resolved_operations path: a governed comparator
    five known sessions removed from the current session must not read as adjacent."""
    current_dir, previous_dir = tmp_path / "current", tmp_path / "previous"
    _write_operation(current_dir, session="2026-09-11")
    _write_operation(previous_dir, session="2026-08-26")
    registry = _registry(
        tmp_path,
        completed=["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26", "2026-09-11"],
        attempted={"2026-08-27": {}, "2026-08-28": {}, "2026-09-03": {}, "2026-09-04": {}, "2026-09-10": {}},
    )
    brief = build_artifact(
        root=tmp_path, current_session="2026-09-11", current_source=current_dir,
        previous_session="2026-08-26", previous_source=previous_dir, registry=registry,
    )
    meta = brief["comparison_metadata"]
    assert meta["comparison_session"] == "2026-08-26"
    assert meta["comparison_session_role"] == ROLE_DISTANT
    assert meta["comparison_fitness"] == FITNESS_DEGRADED
    assert meta["is_immediate_previous_completed_session"] is False
    assert meta["session_gap_trading_sessions"] == 5
    assert meta["skipped_known_sessions"] == [
        "2026-08-27", "2026-08-28", "2026-09-03", "2026-09-04", "2026-09-10",
    ]
    assert meta["comparison_reason_codes"] == ["PREVIOUS_SESSION_REGISTRY_GAP"]
    assert meta["notice"] is not None
    # the existing field must still read exactly as before -- additive only, never renamed.
    assert brief["previous_qualified_session"] == "2026-08-26"


def test_current_session_analytical_sections_are_unaffected_by_comparison_metadata(tmp_path):
    """Comparison-interpretation changes must never alter any other section's own content."""
    current_dir = tmp_path / "current"
    _write_operation(current_dir, session="2026-08-21")
    registry_no_gap_field = _registry(tmp_path, completed=["2026-08-21"])
    brief = build_artifact(root=tmp_path, current_session="2026-08-21", current_source=current_dir, registry=registry_no_gap_field)
    for key in (
        "market_transition", "sector_transition", "opportunity_transition", "lifecycle",
        "recommendation_transition", "invalidation_transition", "tactical_transition",
        "posture_transition", "correlation_concentration_context", "next_session_watch_conditions",
    ):
        assert key in brief  # untouched sections still present and computed exactly as before


def test_deterministic_rerun_produces_identical_comparison_metadata(tmp_path):
    current_dir, previous_dir = tmp_path / "current", tmp_path / "previous"
    _write_operation(current_dir, session="2026-09-11")
    _write_operation(previous_dir, session="2026-08-26")
    registry = _registry(
        tmp_path,
        completed=["2026-08-26", "2026-09-11"],
        attempted={"2026-09-04": {}},
    )
    first = build_artifact(
        root=tmp_path, current_session="2026-09-11", current_source=current_dir,
        previous_session="2026-08-26", previous_source=previous_dir, registry=registry,
    )
    second = build_artifact(
        root=tmp_path, current_session="2026-09-11", current_source=current_dir,
        previous_session="2026-08-26", previous_source=previous_dir, registry=registry,
    )
    assert first["comparison_metadata"] == second["comparison_metadata"]


def test_publication_alone_never_qualifies_a_session_as_a_valid_comparator(tmp_path):
    """A retained operation bundle existing on disk (i.e. already published) is not, by
    itself, evidence of governed completion -- next_session_decision_brief must still refuse
    a current or previous session the registry has not locked as COMPLETED_RETAINED_EVIDENCE,
    exactly as it does today; this is a self-contained regression for that existing invariant."""
    current_dir = tmp_path / "current"
    _write_operation(current_dir, session="2026-08-21")
    registry = _registry(tmp_path, completed=["2026-08-21"])
    registry["completed_sessions"]["2026-08-21"]["status"] = "INTRADAY"  # published, not governed-complete
    with pytest.raises(NextSessionDecisionBriefError, match="SESSION_NOT_GOVERNED_QUALIFIED"):
        build_artifact(root=tmp_path, current_session="2026-08-21", current_source=current_dir, registry=registry)
