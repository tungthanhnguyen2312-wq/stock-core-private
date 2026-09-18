from __future__ import annotations

import json
from pathlib import Path

import multi_session_signal_velocity as velocity
import prospective_decision_retention as retention
from canonical_post_close_pipeline import run_multi_session_signal_velocity_shadow
from tools.run_multi_session_signal_velocity import run


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _decision(session: str, *, price: str = "DOWNTREND", participation: str = "WEAKENING", setup: str = "BASE_BUILDING", structural: str = "WEAKENING", support: str = "ADVERSE") -> dict:
    return {
        "ticker": "FPT", "as_of_session": session, "decision_identity": f"decision:FPT:{session}",
        "market_structure_state": price, "fundamental_state": structural,
        "current_decision_state": {"entry_state": setup},
        "participation": {"status": participation},
        "market_sector_context": {"market_regime": support},
        "evidence_axes": {
            "TACTICAL_STRUCTURE": {"state": price}, "PARTICIPATION_CONFIRMATION": {"state": participation},
            "FUNDAMENTAL": {"state": structural}, "MARKET_SECTOR": {"state": support},
        },
    }


def _snapshot(session: str, decision: dict, *, operation: str | None = None) -> dict:
    operation = operation or f"operation:{session}"
    sealed = {
        "ticker": "FPT", "decision_session": session, "integrated_decision_identity": decision["decision_identity"],
        "t0_close_observation": {"session": session, "close": 100.0},
        "evidence_axis_snapshot": {"status": "COMPLETE", "complete": True},
        "integrated_decision_at_t0": decision,
    }
    sealed = retention._identity(sealed, retention.RECORD_PREFIX, "prospective_snapshot_record_identity")
    return retention._identity({
        "schema_version": "1.0.0", "contract_version": "prospective_decision_snapshot/v1", "session": session,
        "daily_session_operation_identity": operation, "daily_producer_run_identity": f"run:{session}",
        "source_integrated_decision_artifact": {"artifact_identity": f"integrated:{session}", "session": session},
        "t0_price_snapshot": {"snapshot_identity": f"price:{session}", "resolved_completed_session": session},
        "decision_count": 1, "records": {"FPT": sealed}, "authority_boundary": {"immutable_t0_only": True},
    }, retention.SNAPSHOT_PREFIX, "snapshot_identity")


def _fixture(root: Path, sessions: list[tuple[str, dict]], *, invalid_handoff: bool = False) -> None:
    _write(root / "config" / "daily_research_session_input_registry.json", {
        "contract_version": "daily_research_session_input_registry/v1",
        "completed_sessions": {session: {"status": "COMPLETED_RETAINED_EVIDENCE"} for session, _ in sessions},
    })
    for session, decision in sessions:
        snapshot = _snapshot(session, decision)
        _write(root / "operations-review" / "prospective-decision-retention-v1" / session / snapshot["snapshot_identity"].split(":", 1)[1] / "prospective_decision_snapshot.json", snapshot)
        _write(root / "operations-review" / "daily-research-session-operations-v1" / session / "run" / "run_manifest.json", {
            "market_session": session, "operation_identity": snapshot["daily_session_operation_identity"],
            "generation_context": "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION",
        })
        _write(root / "operations-review" / "canonical-post-close-v1" / session / "session_handoff_bundle.json", {
            "session": session, "daily_session_operation_identity": snapshot["daily_session_operation_identity"],
            "integrated_investment_decision_product_identity": "wrong" if invalid_handoff else f"integrated:{session}",
            "prospective_decision_snapshot": {"identity": snapshot["snapshot_identity"], "status": "RETAINED"},
        })


def test_exact_session_discovery_rejects_bad_handoff_and_never_substitutes(tmp_path: Path):
    _fixture(tmp_path, [("2026-01-02", _decision("2026-01-02"))], invalid_handoff=True)
    discovery = velocity.discover_retained_snapshots(tmp_path)
    assert discovery["qualified_snapshots"] == []
    assert discovery["inventory"][0]["classification"] == "EXCLUDED"
    assert "HANDOFF_SOURCE_DECISION_IDENTITY_MISMATCH" in discovery["inventory"][0]["reason_codes"]


def test_categorical_early_transition_and_source_identity_are_deterministic(tmp_path: Path):
    _fixture(tmp_path, [
        ("2026-01-02", _decision("2026-01-02")),
        ("2026-01-03", _decision("2026-01-03", price="UPTREND", participation="IMPROVING", setup="EARLY_REVERSAL_CANDIDATE", structural="REPAIRING", support="SUPPORTIVE")),
    ])
    first = velocity.build_from_retained_root(tmp_path)
    second = velocity.build_from_retained_root(tmp_path)
    assert first == second
    row = [item for item in first["records"] if item["session"] == "2026-01-03"][0]
    assert row["overall_transition_state"] == "EARLY_TRANSITION_EMERGING"
    assert row["axis_transitions"]["setup_maturation"] == "MATURING"
    assert row["source_paths"]["snapshot"].endswith("prospective_decision_snapshot.json")
    assert row["observations_count"] == 2
    assert not {"score", "probability", "recommendation", "target_price"}.intersection(row)


def test_missing_axes_are_explicit_and_never_imputed(tmp_path: Path):
    decision = _decision("2026-01-02")
    decision["evidence_axes"] = {}
    decision["participation"] = {}
    _fixture(tmp_path, [("2026-01-02", decision)])
    artifact = velocity.build_from_retained_root(tmp_path)
    row = artifact["records"][0]
    assert row["axes"]["participation"]["state"] == "UNAVAILABLE"
    assert row["evidence_quality"]["state"] == "PARTIAL_RETAINED_EVIDENCE"
    assert row["overall_transition_state"] == "INITIAL_OBSERVATION"


def test_no_future_data_can_change_an_earlier_session_record(tmp_path: Path):
    base = [("2026-01-02", _decision("2026-01-02")), ("2026-01-03", _decision("2026-01-03", price="UPTREND"))]
    _fixture(tmp_path, base)
    before = velocity.build_from_retained_root(tmp_path)
    _fixture(tmp_path, base + [("2026-01-04", _decision("2026-01-04", price="DOWNTREND", setup="DOWNTREND"))])
    after = velocity.build_from_retained_root(tmp_path)
    assert [row for row in before["records"] if row["session"] != "2026-01-04"] == [row for row in after["records"] if row["session"] != "2026-01-04"]


def test_setup_failure_and_divergence_stay_categorical(tmp_path: Path):
    _fixture(tmp_path, [
        ("2026-01-02", _decision("2026-01-02", price="UPTREND", participation="IMPROVING", setup="EARLY_REVERSAL_CANDIDATE", support="SUPPORTIVE")),
        ("2026-01-03", _decision("2026-01-03", price="DOWNTREND", participation="WEAKENING", setup="DOWNTREND", structural="REPAIRING", support="SUPPORTIVE")),
    ])
    row = velocity.build_from_retained_root(tmp_path)["records"][-1]
    assert row["axis_transitions"]["setup_maturation"] == "FAILED_OR_INVALIDATED"
    assert row["overall_transition_state"] == "DIVERGENT_TRANSITION"


def test_runner_writes_idempotent_immutable_artifact(tmp_path: Path):
    _fixture(tmp_path, [("2026-01-02", _decision("2026-01-02"))])
    destination = tmp_path / "out" / "velocity.json"
    first = run(root=tmp_path, output=destination)
    second = run(root=tmp_path, output=destination)
    assert first["artifact_identity"] == second["artifact_identity"]
    assert json.loads(destination.read_text(encoding="utf-8"))["artifact_identity"] == first["artifact_identity"]


def test_no_qualified_input_returns_explicit_empty_validation(tmp_path: Path):
    artifact = velocity.build_from_retained_root(tmp_path)
    assert artifact["validation"]["retained_session_count"] == 0
    assert artifact["validation"]["lead_time_diagnostic"]["status"] == "NOT_EVALUABLE_NO_FORWARD_OUTCOME_CONTRACT"


def test_optional_daily_shadow_collector_is_nonblocking_and_idempotent(tmp_path: Path):
    _fixture(tmp_path, [("2026-01-02", _decision("2026-01-02"))])
    first = run_multi_session_signal_velocity_shadow(tmp_path, "2026-01-02")
    second = run_multi_session_signal_velocity_shadow(tmp_path, "2026-01-02")
    assert first["status"] == second["status"] == "COLLECTED"
    assert first["artifact_identity"] == second["artifact_identity"]
    assert (tmp_path / first["path"]).is_file()
