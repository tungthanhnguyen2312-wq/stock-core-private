from __future__ import annotations

import json
from pathlib import Path

import pytest

import integrated_decision_prospective_feedback as bridge
import prospective_decision_outcome_feedback as feedback
from tools.run_prospective_decision_outcome_feedback import run


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _record(session: str, *, posture: str = "WAIT_FOR_CONFIRMATION") -> dict:
    return {
        "ticker": "FPT", "as_of_session": session, "decision_identity": f"decision:FPT:{session}",
        "research_action_posture": posture, "fundamental_state": "IMPROVING",
        "valuation_context_summary": {"status": "AVAILABLE"}, "market_structure_state": "UPTREND",
        "momentum_context": {"status": "AVAILABLE"}, "participation": {"status": "AVAILABLE"},
        "market_sector_context": {"market_regime": "SUPPORTIVE", "sector_leadership": "LEADING"},
        "priority_posture_reconciliation": {"research_priority_tier": "PRIORITY_NOW"},
        "trigger": {"trigger_state": "APPROACHING", "trigger_level": 100.0},
        "invalidation": {"invalidation_level": 90.0},
        "evidence_axes": {
            "FUNDAMENTAL": {"state": "IMPROVING", "fitness": "AVAILABLE", "lineage": {"source_artifact_identity": "fund:a"}},
            "TACTICAL_STRUCTURE": {"state": "UPTREND", "fitness": "AVAILABLE", "lineage": {"source_artifact_identity": "tech:a"}},
        },
        "evidence_axis_coherence": {"state": "ALIGNED"},
    }


def _snapshot(session: str, close: float, *, transform: str = "normalize/v1") -> dict:
    return {
        "resolved_completed_session": session, "snapshot_identity": f"snapshot:{session}",
        "records": {"FPT": {"observations": [{
            "session": session, "close": close, "provider": "KBS", "dataset": "KBS_OHLC_1D",
            "price_basis": "CURRENT_DESCRIPTIVE", "transformation_identity": transform,
            "qualification": "CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY",
        }]}},
    }


def _fixture_root(tmp_path: Path, *, sessions: int = 6) -> tuple[Path, list[str]]:
    chain = [f"2026-01-{number:02d}" for number in range(1, sessions + 1)]
    for index, session in enumerate(chain):
        operation_identity = f"daily-operation:{session}"
        artifact_path = tmp_path / "operations-review" / "integrated-artifacts" / session / "integrated_investment_decision_product_artifact.json"
        artifact = {
            "contract_version": "integrated_investment_decision_product/v1", "session": session,
            "requested_at": session + "T15:00:00+07:00", "artifact_identity": f"integrated:{session}",
            "records": {"FPT": _record(session)},
        }
        _write(artifact_path, artifact)
        _write(tmp_path / "operations-review" / "daily-research-session-operations-v1" / session / "run" / "run_manifest.json", {
            "market_session": session, "operation_identity": operation_identity,
            "generation_context": "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION",
        })
        _write(tmp_path / "operations-review" / "canonical-post-close-v1" / session / "session_handoff_bundle.json", {
            "session": session, "daily_session_operation_identity": operation_identity,
            "integrated_investment_decision_product_identity": f"integrated:{session}",
            "deeper_bundles": {"integrated_investment_decision_product": str(artifact_path.relative_to(tmp_path)).replace("\\", "/")},
            "daily_producer": {"status": "COMPLETED"}, "market_session_proof": {"resolved_completed_session": session},
        })
        nodash = session.replace("-", "")
        _write(tmp_path / "operations-review" / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "p3f9b_mva_exact_session_snapshot.json", _snapshot(session, 100.0 + index))
    # A retained-looking replay must be inventoried but never admitted.
    _write(tmp_path / "operations-review" / "sample-replay" / "integrated_investment_decision_product_artifact.json", {
        "contract_version": "integrated_investment_decision_product/v1", "session": chain[0],
        "requested_at": chain[0] + "T15:00:00+07:00", "artifact_identity": "integrated:replay",
        "records": {"FPT": _record(chain[0])},
    })
    return tmp_path, chain


def test_temporal_gate_excludes_replay_and_uses_only_identity_bound_daily_operations(tmp_path: Path):
    root, chain = _fixture_root(tmp_path)
    corpus = feedback.discover_prospective_corpus(root)
    assert corpus["classification_counts"][feedback.GENUINE] == len(chain)
    assert corpus["classification_counts"][feedback.REPLAY_ONLY] == 1
    assert all(item["temporal"]["status"] == feedback.GENUINE for item in corpus["genuine_artifacts"])


def test_horizons_close_excursions_policy_diagnostics_and_identity_are_deterministic(tmp_path: Path):
    root, chain = _fixture_root(tmp_path)
    original = json.loads(json.dumps(_record(chain[0])))
    first = feedback.build_feedback_artifact(root)
    second = feedback.build_feedback_artifact(root)
    assert first == second
    assert first["prospective_corpus"]["genuine_decision_count"] == len(chain)
    row = next(item for item in first["feedback_records"] if item["decision_session"] == chain[0])
    h1 = row["forward_outcomes"]["horizons"]["forward_close_return_1"]
    h5 = row["forward_outcomes"]["horizons"]["forward_close_return_5"]
    assert h1["status"] == bridge.MATURE
    assert h1["start_session"] == chain[0] and h1["end_session"] == chain[1]
    assert h1["start_price"] == 100.0 and h1["end_price"] == 101.0
    assert h1["series_fitness"] == "COMPATIBLE_RETAINED_CLOSE_SERIES"
    assert h5["return"] == pytest.approx(0.05)
    close5 = row["forward_outcomes"]["close_path_by_horizon"]["close_excursion_5"]
    assert close5["CLOSE_MFE"] == pytest.approx(0.05) and close5["CLOSE_MAE"] == pytest.approx(0.01)
    assert "MFE" not in row["forward_outcomes"]["close_path"]
    assert row["outcome_classification"]["label"] == "WAIT_MISSED_UPSIDE"
    assert first["false_negative_cases"]
    assert row["trigger_invalidation_outcome"]["trigger"]["status"].startswith("T0_TRIGGER_EVENT_NOT_EVALUABLE")
    assert original == _record(chain[0])  # feedback did not mutate the decision source shape
    assert first["policy_diagnostic_candidates"][0]["policy_mutated"] is False


def test_incompatible_transformation_is_not_spliced_between_retained_sessions():
    chain = ["2026-01-01", "2026-01-02"]
    snapshots = {chain[0]: _snapshot(chain[0], 100.0), chain[1]: _snapshot(chain[1], 101.0, transform="other/v1")}
    result = bridge.evaluate_decision_forward_outcome(
        decision_record=_record(chain[0]), p3f9b_snapshot=None, governed_chain=chain, retained_session_snapshots=snapshots,
    )
    assert result["horizons"]["forward_close_return_1"]["status"] == bridge.PRICE_BASIS_INCOMPATIBLE
    assert result["horizons"]["forward_close_return_1"]["series_fitness"] == "INCOMPATIBLE_PRICE_SERIES"


def test_wait_avoided_drawdown_and_failed_breakout_are_descriptive_states():
    negative = {"horizons": {"forward_close_return_5": {"status": bridge.MATURE, "return": -0.04}}, "close_path_by_horizon": {"close_excursion_5": {"CLOSE_MAE": -0.04}}}
    assert feedback._outcome_label(_record("2026-01-01"), negative)["label"] == "WAIT_AVOIDED_DRAWDOWN"
    assert feedback._outcome_label(_record("2026-01-01", posture="INITIATE_ON_BREAKOUT"), negative)["label"] == "FALSE_BREAKOUT_OUTCOME"


def test_runner_writes_required_immutable_evidence_views(tmp_path: Path):
    root, _ = _fixture_root(tmp_path)
    evidence_dir = root / "evidence"
    result = run(root=root, evidence_dir=evidence_dir)
    assert result["artifact_identity"].startswith("prospective_decision_outcome_feedback:")
    for name in (
        "REPORT.md", "prospective_decision_feedback_artifact.json", "prospective_corpus_inventory.json",
        "temporal_qualification.json", "forward_outcome_coverage.json", "posture_outcome_summary.json",
        "coherence_outcome_summary.json", "evidence_axis_outcome_summary.json", "false_negative_cases.json",
        "failed_setup_cases.json", "trigger_invalidation_outcomes.json", "policy_diagnostic_candidates.json",
        "product_feedback_gap_matrix.json",
    ):
        assert (evidence_dir / name).is_file()
