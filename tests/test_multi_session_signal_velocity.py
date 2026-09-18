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
        "market_structure_state": structural, "fundamental_state": "INSUFFICIENT",
        "momentum_context": {"price_direction_1d": "UP" if price == "UPTREND" else "DOWN"},
        "breakout_state_v3": setup,
        "current_decision_state": {"entry_state": setup},
        "participation": {"status": participation},
        "market_sector_context": {"market_regime": support},
        "evidence_axes": {
            "TACTICAL_STRUCTURE": {"state": structural, "context": {"market_structure_state": structural, "breakout_state_v3": setup}, "lineage": {"source_artifact_identity": "technical:" + session}},
            "MOMENTUM": {"state": "ELIGIBLE", "lineage": {"source_artifact_identity": "momentum:" + session}},
            "PARTICIPATION_CONFIRMATION": {"state": participation, "context": {"participation_detail": {"participation_state": participation}}, "lineage": {"participation_artifact_identity": "participation:" + session}},
            "FUNDAMENTAL": {"state": "INSUFFICIENT", "lineage": {"source_artifact_identity": "fundamental:" + session}},
            "MARKET_SECTOR": {"state": support, "context": {"market_regime": support, "sector_leadership": support}, "lineage": {"source_artifact_identity": "market:" + session}},
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
    assert row["overall_transition_state"] == "MIXED_TRANSITION"
    assert row["axes"]["setup_maturation"]["trajectory"]["latest_transition"] == "IMPROVING"
    assert row["source_paths"]["snapshot"].endswith("prospective_decision_snapshot.json")
    assert row["axes"]["structural_repair"]["trajectory"]["observation_count"] == 2
    assert not {"score", "probability", "recommendation", "target_price"}.intersection(row)


def test_missing_axes_are_explicit_and_never_imputed(tmp_path: Path):
    decision = _decision("2026-01-02")
    decision["evidence_axes"] = {}
    decision["participation"] = {}
    _fixture(tmp_path, [("2026-01-02", decision)])
    artifact = velocity.build_from_retained_root(tmp_path)
    row = artifact["records"][0]
    assert row["axes"]["participation_confirmation"]["state"] == "UNAVAILABLE"
    assert row["evidence_quality"]["state"] == "PARTIAL_RETAINED_EVIDENCE"
    assert row["overall_transition_state"] == "STABLE"


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
    assert row["axes"]["setup_maturation"]["state"] == "INVALID"
    assert row["overall_transition_state"] == "DETERIORATING"


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


def test_structural_repair_never_reads_fundamental_and_fundamental_is_explicit():
    decision = _decision("2026-01-02", structural="BREAKDOWN")
    decision["evidence_axes"]["FUNDAMENTAL"]["state"] = "IMPROVING"
    structural = velocity._axis(decision, "structural_repair")
    fundamental = velocity._axis(decision, "fundamental_trajectory")
    assert structural["state"] == "ADVERSE"
    assert structural["source_field"].startswith("TACTICAL_STRUCTURE")
    assert fundamental["state"] == "IMPROVING"


def test_technical_axes_share_identity_but_cannot_be_independent_support():
    axes = {name: {"state": "CONSTRUCTIVE", "source_identity": "same-technical", "trajectory": {"persistence": "IMPROVEMENT_PERSISTENT", "acceleration_state": "ACCELERATING", "latest_transition": "IMPROVING"}} for name in velocity.AXES}
    axes["setup_maturation"]["state"] = "CONFIRMED"
    result, supporting, _ = velocity._overall(axes, "COMPLETE_RETAINED_EVIDENCE")
    assert result == "EARLY_IMPROVEMENT"
    assert len({axes[name]["source_identity"] for name in supporting}) == 1


def test_two_observations_never_claim_persistence_or_acceleration():
    history = [{"state": "ADVERSE"}, {"state": "REPAIRING"}]
    state = velocity._trajectory("structural_repair", history)
    assert state["persistence"] == "INSUFFICIENT_HISTORY"
    assert state["acceleration_state"] == "INSUFFICIENT_HISTORY"


def test_three_and_five_session_categorical_trajectory_states():
    three = velocity._trajectory("structural_repair", [{"state": "ADVERSE"}, {"state": "REPAIRING"}, {"state": "CONSTRUCTIVE"}])
    five = velocity._trajectory("structural_repair", [{"state": "ADVERSE"}, {"state": "REPAIRING"}, {"state": "CONSTRUCTIVE"}, {"state": "CONSTRUCTIVE"}, {"state": "CONSTRUCTIVE"}])
    assert three["persistence"] == "IMPROVEMENT_PERSISTENT"
    assert five["window_5_state"] in {"IMPROVEMENT_PERSISTENT", "NO_CLEAR_DIRECTION"}


def test_noisy_reversal_and_missing_observation_remain_explicit():
    noisy = velocity._trajectory("price_momentum", [{"state": "DETERIORATING"}, {"state": "IMPROVING"}, {"state": "DETERIORATING"}])
    missing = velocity._trajectory("price_momentum", [{"state": "DETERIORATING"}, {"state": "UNAVAILABLE"}, {"state": "IMPROVING"}])
    assert noisy["persistence"] == "MIXED"
    assert missing["observation_count"] == 2


def test_critical_structure_or_setup_veto_blocks_constructive_overall():
    axes = {name: {"state": "NEUTRAL", "source_identity": name, "trajectory": {"persistence": "NO_CLEAR_DIRECTION", "acceleration_state": "STABLE", "latest_transition": "UNCHANGED"}} for name in velocity.AXES}
    axes["structural_repair"]["state"] = "ADVERSE"
    result, _, veto = velocity._overall(axes, "PARTIAL_RETAINED_EVIDENCE")
    assert result == "DETERIORATING" and veto == ["structural_repair"]
