"""A retained handoff names its producer run even when a rerun left a second manifest.

2026-10-05 Dashboard publication failed closed with
DAILY_PRODUCER_RUN_AMBIGUOUS_OR_MISSING:count=2. The crashed attempt and the
completed attempt both wrote run_manifest.json. The sealed session handoff
already named the completed run. Companions must use that binding.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import dashboard_session_companions as companions

SESSION = "2026-10-05"
COMPLETED = "daily_producer_run:" + "a" * 64
CRASHED = "daily_producer_run:" + "b" * 64
UPSTREAM = {
    name: {"artifact_identity": f"{name}:identity"}
    for name in ("descriptive", "screening", "tactical", "triage")
}


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _session(root: Path, *, handoff_run: str | None, nested_run: str | None = None) -> None:
    _write(root / "config" / "daily_research_session_input_registry.json", {
        "contract_version": "daily_research_session_input_registry/v1",
        "completed_sessions": {SESSION: {"status": "COMPLETED_RETAINED_EVIDENCE"}},
        "sessions": {SESSION: {}},
    })
    handoff: dict = {
        "session": SESSION,
        "market_session_proof": {"resolved_completed_session": SESSION},
        "upstream_evidence_identities": UPSTREAM,
        "daily_producer": {"status": "COMPLETED", "operation_identity": "daily_research_session_operation:completed"},
    }
    if handoff_run is not None:
        handoff["daily_producer_run_identity"] = handoff_run
    if nested_run is not None:
        handoff["daily_producer"]["run_identity"] = nested_run
    _write(
        root / "operations-review" / "canonical-post-close-v1" / SESSION / "session_handoff_bundle.json",
        handoff,
    )
    for identity in (COMPLETED, CRASHED):
        digest = identity.split(":", 1)[1]
        _write(
            root / "operations-review" / "daily-producer-runs-v1" / SESSION / digest / "run_manifest.json",
            {
                "target_market_session": SESSION,
                "run_identity": identity,
                "upstream_artifact_identities": UPSTREAM,
            },
        )


def _plan(root: Path, **kwargs):
    return companions.compute_session_companions(
        root, SESSION, producer_commit="abc", producer_commit_summary="test", build_id="build", **kwargs,
    )


def test_declared_handoff_run_wins_over_an_earlier_manifest(tmp_path: Path):
    _session(tmp_path, handoff_run=COMPLETED, nested_run=COMPLETED)
    plan = _plan(tmp_path)
    assert plan.manifest["source_artifacts"]["daily_producer_run_manifest"]["run_identity"] == COMPLETED
    assert plan.manifest["canonical_producer_status"]["run_identity"] == COMPLETED
    assert plan.session == SESSION


def test_undeclared_handoff_still_refuses_two_runs(tmp_path: Path):
    _session(tmp_path, handoff_run=None)
    with pytest.raises(companions.DashboardSessionCompanionError, match="DAILY_PRODUCER_RUN_AMBIGUOUS_OR_MISSING:2026-10-05:count=2"):
        _plan(tmp_path)


def test_conflicting_handoff_run_fields_refuse(tmp_path: Path):
    _session(tmp_path, handoff_run=COMPLETED, nested_run=CRASHED)
    with pytest.raises(companions.DashboardSessionCompanionError, match="HANDOFF_PRODUCER_RUN_IDENTITY_CONFLICT"):
        _plan(tmp_path)


def test_caller_identity_must_match_the_handoff(tmp_path: Path):
    _session(tmp_path, handoff_run=COMPLETED, nested_run=COMPLETED)
    with pytest.raises(companions.DashboardSessionCompanionError, match="HANDOFF_PRODUCER_RUN_IDENTITY_MISMATCH"):
        _plan(tmp_path, producer_run_identity=CRASHED)
    plan = _plan(tmp_path, producer_run_identity=COMPLETED)
    assert plan.manifest["source_artifacts"]["daily_producer_run_manifest"]["run_identity"] == COMPLETED
