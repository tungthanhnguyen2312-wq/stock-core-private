import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

import daily_session_level2_package as level2
from daily_research_session_operations import load_registry
from daily_session_level2_package import (
    BLOCKED_BY_STALE_TRIAGE_DEPENDENCY,
    EXACT_SESSION_CLEAN,
    UNAVAILABLE_REQUIRED_INPUT,
    build_tactical_current_session_signal,
    classify_level2_components,
    evaluate_canonical_daily_producer,
    resolve_level2_session,
    session_triage_status,
    write_level2_package,
)
from vn_time import VN_TZ

ROOT = Path(__file__).resolve().parents[1]
NAMED_TRIAGE = ROOT / "operations-review/full-universe-entry-candidate-triage-20260824/full_universe_entry_candidate_triage_20260824.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _prime_materialization_outputs(paths: dict[str, Path]) -> None:
    for key in (
        "breadth_foundation", "universe_resolution", "liquidity_research", "technical_recovery",
        "descriptive_research", "screening_foundation", "tactical_classifier",
        "corporate_intelligence", "valuation", "sector_leadership", "peer_relative",
        "risk_register", "technical_coverage_disposition",
    ):
        _write_json(paths[key], {})


def test_run_cmd_executes_relative_tool_from_explicit_execution_root(tmp_path):
    execution_root = tmp_path / "producer"
    execution_root.mkdir()
    with patch.object(level2.subprocess, "run") as mocked:
        level2.run_cmd(execution_root, ["tools/example.py", "--flag"])
    assert mocked.call_args.args[0] == [sys.executable, "tools/example.py", "--flag"]
    assert mocked.call_args.kwargs["cwd"] == str(execution_root)
    assert mocked.call_args.kwargs["check"] is True


def test_ensure_exact_session_snapshot_issues_the_real_cli_flags_and_returns_the_path(tmp_path):
    session = "2026-08-26"
    paths = level2.session_artifact_paths(tmp_path, session)
    calls: list[tuple[Path, list[str]]] = []

    def fake_run(execution_root: Path, command: list[str]) -> None:
        calls.append((execution_root, command))
        _write_json(paths["exact_session_snapshot"], {"resolved_completed_session": session})

    with patch.object(level2, "run_cmd", fake_run):
        result = level2.ensure_exact_session_snapshot(tmp_path, session, tmp_path / "runtime")

    assert result == paths["exact_session_snapshot"]
    assert len(calls) == 1
    assert calls[0][0] == tmp_path
    command = calls[0][1]
    assert command[0] == "tools/run_p3f9b_market_wide_exact_session_scaleout.py"
    assert command[command.index("--output-dir") + 1] == str(paths["exact_session_snapshot"].parent)
    assert command[command.index("--session") + 1] == session


def test_ensure_exact_session_snapshot_is_idempotent_when_already_present(tmp_path):
    session = "2026-08-26"
    paths = level2.session_artifact_paths(tmp_path, session)
    _write_json(paths["exact_session_snapshot"], {"resolved_completed_session": session})

    with patch.object(level2, "run_cmd") as mocked:
        result = level2.ensure_exact_session_snapshot(tmp_path, session, tmp_path / "runtime")

    mocked.assert_not_called()
    assert result == paths["exact_session_snapshot"]


def test_ensure_exact_session_snapshot_raises_on_session_mismatch(tmp_path):
    session = "2026-08-26"
    paths = level2.session_artifact_paths(tmp_path, session)

    def fake_run(execution_root: Path, command: list[str]) -> None:
        _write_json(paths["exact_session_snapshot"], {"resolved_completed_session": "2026-08-25"})

    with patch.object(level2, "run_cmd", fake_run):
        with pytest.raises(ValueError, match="P3F9B_ACQUIRED_SESSION_MISMATCH:requested=2026-08-26:resolved=2026-08-25"):
            level2.ensure_exact_session_snapshot(tmp_path, session, tmp_path / "runtime")


def test_materialize_independent_components_delegates_snapshot_acquisition_to_the_helper(tmp_path):
    # Backward-compatibility contract: a standalone materialize_independent_components() caller
    # (any pre-existing caller that never adopted ensure_exact_session_snapshot directly) must
    # still get exactly the same acquisition behaviour through the extracted helper.
    session = "2026-08-26"
    paths = level2.session_artifact_paths(tmp_path, session)
    calls = []

    def fake_ensure(artifact_root, sess, runtime_root, workers, now, *, execution_root=None):
        calls.append((artifact_root, sess, execution_root))
        _write_json(paths["exact_session_snapshot"], {"resolved_completed_session": session})
        return paths["exact_session_snapshot"]

    _prime_materialization_outputs(paths)
    with patch.object(level2, "ensure_exact_session_snapshot", fake_ensure), \
         patch.object(level2, "_prior_completed_descriptive", return_value=tmp_path / "prior.json"):
        level2.materialize_independent_components(tmp_path, session, tmp_path / "runtime")

    assert calls == [(tmp_path, session, tmp_path)]


def test_materialization_separates_attempt_artifact_root_from_execution_root(tmp_path):
    session = "2026-08-26"
    attempt_root = tmp_path / "operations-review" / "canonical-post-close-v1" / session / "post-close-attempt-190500"
    paths = level2.session_artifact_paths(attempt_root, session)
    _prime_materialization_outputs(paths)
    calls: list[tuple[Path, list[str]]] = []

    def fake_run(execution_root: Path, command: list[str]) -> None:
        calls.append((execution_root, command))
        _write_json(paths["exact_session_snapshot"], {"resolved_completed_session": session})

    with patch.object(level2, "run_cmd", fake_run):
        level2.materialize_independent_components(
            attempt_root,
            session,
            tmp_path / "runtime",
            execution_root=ROOT,
        )

    assert len(calls) == 1
    assert calls[0][0] == ROOT
    command = calls[0][1]
    assert command[0] == "tools/run_p3f9b_market_wide_exact_session_scaleout.py"
    assert command[command.index("--output-dir") + 1] == str(paths["exact_session_snapshot"].parent)
    assert str(attempt_root) in command[command.index("--output-dir") + 1]
    assert command[command.index("--session") + 1] == session


def test_ordinary_materialization_keeps_its_single_root_as_execution_root(tmp_path):
    session = "2026-08-26"
    paths = level2.session_artifact_paths(tmp_path, session)
    _prime_materialization_outputs(paths)
    calls: list[tuple[Path, list[str]]] = []

    def fake_run(execution_root: Path, command: list[str]) -> None:
        calls.append((execution_root, command))
        _write_json(paths["exact_session_snapshot"], {"resolved_completed_session": session})

    with patch.object(level2, "run_cmd", fake_run), \
         patch.object(level2, "_prior_completed_descriptive", return_value=tmp_path / "prior.json"):
        level2.materialize_independent_components(tmp_path, session, tmp_path / "runtime")

    assert calls[0][0] == tmp_path


def test_named_20260824_triage_file_is_2026_08_21_session():
    import json
    artifact = json.loads(NAMED_TRIAGE.read_text(encoding="utf-8"))
    assert artifact["source_market_session"] == "2026-08-21"
    assert artifact["artifact_identity"].startswith("full_universe_entry_candidate_triage:4b527330")


def test_2026_08_25_has_authorized_exact_session_triage():
    registry = load_registry(ROOT)
    status = session_triage_status(ROOT, "2026-08-25", registry)
    assert status["status"] == EXACT_SESSION_CLEAN
    assert status["source_session"] == "2026-08-25"
    assert status["identity"].startswith("full_universe_entry_candidate_triage:97d80cf0")


def test_latest_completed_after_close_on_trading_day():
    now = datetime(2026, 8, 25, 16, 0, tzinfo=VN_TZ)
    resolved = resolve_level2_session(None, now=now)
    assert resolved["session"] == "2026-08-25"
    assert resolved["resolution_mode"] == "LATEST_COMPLETED_WORKING_DATE"


def test_latest_completed_morning_before_session_completes():
    now = datetime(2026, 8, 25, 9, 0, tzinfo=VN_TZ)
    resolved = resolve_level2_session("latest-completed", now=now)
    assert resolved["session"] == "2026-08-24"


def test_latest_completed_weekend_is_prior_friday():
    saturday = datetime(2026, 8, 22, 16, 0, tzinfo=VN_TZ)
    sunday = datetime(2026, 8, 23, 10, 0, tzinfo=VN_TZ)
    assert resolve_level2_session(None, now=saturday)["session"] == "2026-08-21"
    assert resolve_level2_session(None, now=sunday)["session"] == "2026-08-21"


def test_explicit_historical_session_is_not_overridden_by_clock():
    now = datetime(2026, 8, 25, 16, 0, tzinfo=VN_TZ)
    resolved = resolve_level2_session("2026-08-21", now=now)
    assert resolved["session"] == "2026-08-21"
    assert resolved["resolution_mode"] == "EXPLICIT_SESSION"


def test_canonical_2026_08_25_is_eligible_without_fake_outputs():
    now = datetime(2026, 8, 26, 16, 0, tzinfo=VN_TZ)
    status = evaluate_canonical_daily_producer(ROOT, "2026-08-25", now=now)
    assert status["canonical_daily_producer_status"] == "ELIGIBLE_NOT_EXECUTED_BY_LEVEL2"
    assert status["fake_canonical_outputs_written"] is False
    assert status["root_blocker"] is None


def test_tactical_signal_is_distinct_from_opportunity_prioritization():
    tactical = {
        "session": "2026-08-25",
        "artifact_identity": "watchlist_tactical_entry_classifier:test",
        "coverage": {
            "classified_count": 3,
            "entry_state_counts": {"BREAKOUT_READY": 1, "UPTREND_CONFIRMED": 1, "BASE_BUILDING": 1},
            "entry_action_counts": {"BUY_ON_CONFIRMATION": 1, "WAIT": 1, "ACCUMULATE_IN_BASE": 1},
        },
        "records": {
            "AAA": {"entry_state": "BREAKOUT_READY", "entry_action": "BUY_ON_CONFIRMATION"},
            "BBB": {"entry_state": "UPTREND_CONFIRMED", "entry_action": "WAIT"},
            "CCC": {"entry_state": "BASE_BUILDING", "entry_action": "ACCUMULATE_IN_BASE"},
        },
    }
    signal = build_tactical_current_session_signal(tactical, "2026-08-25")
    assert signal["signal_class"] == "TACTICAL_CURRENT_SESSION_SIGNAL"
    assert signal["full_opportunity_prioritization"] == "FULL_OPPORTUNITY_PRIORITIZATION_UNAVAILABLE"
    assert signal["selective_tactical_states"]["BREAKOUT_READY"]["tickers"] == ["AAA"]
    assert "FULL_OPPORTUNITY_PRIORITIZATION_UNAVAILABLE" in signal["blocked_claims"]


def test_stale_scenario_is_not_advertised_exact_session_clean(tmp_path):
    root = tmp_path
    ops = root / "operations-review"
    session = "2026-08-25"
    nodash = "20260825"
    (ops / f"current-evidence-bound-scenario-v1-{nodash}").mkdir(parents=True)
    (ops / "full-universe-entry-candidate-triage-20260824").mkdir(parents=True)
    (root / "config").mkdir()
    registry = {
        "schema_version": "1.0.0",
        "contract_version": "daily_research_session_input_registry/v1",
        "completed_sessions": {
            "2026-08-21": {
                "status": "COMPLETED_RETAINED_EVIDENCE",
                "trading_day_valid": True,
                "frozen_input_identities": {"triage": "full_universe_entry_candidate_triage:stale21"},
            }
        },
        "sessions": {
            "2026-08-21": {
                "descriptive": {"path": "x", "artifact_identity": "d"},
                "screening": {"path": "x", "artifact_identity": "s"},
                "tactical": {"path": "x", "artifact_identity": "t"},
                "triage": {"path": "operations-review/full-universe-entry-candidate-triage-20260824/full_universe_entry_candidate_triage_20260824.json", "artifact_identity": "full_universe_entry_candidate_triage:stale21"},
                "fundamental": {"path": "x", "artifact_identity": "f"},
                "valuation": {"path": "x", "artifact_identity": "v"},
                "catalyst": {"path": "x", "artifact_identity": "c"},
                "corporate_intelligence": {"path": "x", "artifact_identity": "ci"},
            }
        },
    }
    (root / "config" / "daily_research_session_input_registry.json").write_text(
        __import__("json").dumps(registry), encoding="utf-8"
    )
    triage = {
        "artifact_identity": "full_universe_entry_candidate_triage:stale21",
        "source_market_session": "2026-08-21",
    }
    (ops / "full-universe-entry-candidate-triage-20260824" / "full_universe_entry_candidate_triage_20260824.json").write_text(
        __import__("json").dumps(triage), encoding="utf-8"
    )
    scenario = {
        "artifact_identity": "current_evidence_bound_scenario:contaminated",
        "session": "2026-08-25",
        "source_artifact_identities": {"triage": "full_universe_entry_candidate_triage:stale21"},
        "records": {},
    }
    (ops / f"current-evidence-bound-scenario-v1-{nodash}" / "current_evidence_bound_scenario_artifact.json").write_text(
        __import__("json").dumps(scenario), encoding="utf-8"
    )
    snapshot = {
        "snapshot_identity": "p3f9_exact_session_snapshot:sess",
        "resolved_completed_session": session,
        "records": {},
    }
    snap_dir = ops / f"p3f9b-market-wide-exact-session-scaleout-{nodash}"
    snap_dir.mkdir(parents=True)
    (snap_dir / "p3f9b_mva_exact_session_snapshot.json").write_text(__import__("json").dumps(snapshot), encoding="utf-8")
    tactical = {
        "artifact_identity": "watchlist_tactical_entry_classifier:clean",
        "session": session,
        "coverage": {"classified_count": 1, "entry_state_counts": {"BREAKOUT_READY": 1}, "entry_action_counts": {"BUY_ON_CONFIRMATION": 1}},
        "records": {"AAA": {"entry_state": "BREAKOUT_READY", "entry_action": "BUY_ON_CONFIRMATION"}},
    }
    tac_dir = ops / f"watchlist-tactical-entry-decision-v1-{nodash}"
    tac_dir.mkdir(parents=True)
    (tac_dir / "watchlist_tactical_entry_classifier_artifact.json").write_text(__import__("json").dumps(tactical), encoding="utf-8")

    classification = classify_level2_components(root, session)
    by_id = {row["component_id"]: row for row in classification["components"]}
    assert by_id["current_evidence_bound_scenario"]["exact_session_vs_reusable_context_status"] == BLOCKED_BY_STALE_TRIAGE_DEPENDENCY
    assert by_id["current_evidence_bound_scenario"]["advertised_as_exact_session_clean"] is False
    assert by_id["current_opportunity_prioritization"]["exact_session_vs_reusable_context_status"] == BLOCKED_BY_STALE_TRIAGE_DEPENDENCY
    assert by_id["tactical_classifier"]["exact_session_vs_reusable_context_status"] == EXACT_SESSION_CLEAN
    assert classification["tactical_current_session_signal"]["status"] == "AVAILABLE"
    assert classification["stale_triage_dependency_trace"]["stale_triage_used_by_scenario"]["source_session"] == "2026-08-21"
    assert "PRIORITY" not in " ".join(by_id["tactical_classifier"]["allowed_claims"])

    canonical = evaluate_canonical_daily_producer(root, session, now=datetime(2026, 8, 25, 16, tzinfo=VN_TZ))
    resolution = resolve_level2_session(session, now=datetime(2026, 8, 25, 16, tzinfo=VN_TZ))
    written = write_level2_package(root, session, classification=classification, canonical=canonical, resolution=resolution)
    manifest = __import__("json").loads(written["manifest"].read_text(encoding="utf-8"))
    brief = written["brief"].read_text(encoding="utf-8")
    assert manifest["canonical_daily_producer_status"] == "BLOCKED"
    assert manifest["canonical_producer_status"]["root_blocker"] == "REQUIRED_TRIAGE_GENERATOR_UNAVAILABLE"
    assert manifest["canonical_producer_status"]["fake_canonical_outputs_written"] is False
    scenario_row = next(c for c in manifest["components"] if c["component_id"] == "current_evidence_bound_scenario")
    assert scenario_row["advertised_as_exact_session_clean"] is False
    assert "FULL_OPPORTUNITY_PRIORITIZATION" in " ".join(manifest["governed_claims"]["blocked_claims"])
    assert brief.startswith("# Stock Lookup")
    assert "CANONICAL DAILY PRODUCER: BLOCKED" in brief
    assert "BLOCKER: REQUIRED_TRIAGE_GENERATOR_UNAVAILABLE" in brief
    assert "CURRENT-SESSION ANALYSIS STILL AVAILABLE: YES" in brief
    assert "## CURRENT-SESSION CLEAN COMPONENTS" in brief
    assert "## PRIOR-AS-OF CONTEXT" in brief
    assert "## UNAVAILABLE / TRIAGE-DEPENDENT COMPONENTS" in brief
    assert "FULL_OPPORTUNITY_PRIORITIZATION_UNAVAILABLE" in brief
    assert "TACTICAL_CURRENT_SESSION_SIGNAL" in brief
    producer_dir = root / "operations-review" / "daily-producer-runs-v1"
    assert not producer_dir.exists()
