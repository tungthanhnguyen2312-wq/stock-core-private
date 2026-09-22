from __future__ import annotations

import json
import inspect
import subprocess
from pathlib import Path

import pytest

from tools import run_owner_daily as workflow
import owner_daily_journal as journal


SESSION = "2026-09-16"


def _write_completion(root: Path, *, state="LOCAL_COMPLETE", producer="COMPLETED", runtime="READY", trusted="READY") -> Path:
    (root / "config").mkdir(parents=True)
    (root / "config" / "daily_research_session_input_registry.json").write_text(json.dumps({
        "completed_sessions": {SESSION: {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True}},
    }), encoding="utf-8")
    source = root / "operations-review" / "daily-research-session-operations-v1" / SESSION / "op"
    source.mkdir(parents=True)
    for name in ("ai_research_session_bundle.json", "daily_opportunity_decision_queue_artifact.json"):
        (source / name).write_text("{}", encoding="utf-8")
    (source / "ai_research_bundle_manifest.json").write_text(json.dumps({"operation_identity": "daily_research_session_operation:test"}), encoding="utf-8")
    record_path = root / "operations-review" / "canonical-daily-operation-v1" / SESSION / "op" / "daily_operation_record.json"
    record_path.parent.mkdir(parents=True)
    record_path.write_text(json.dumps({
        "session": SESSION, "daily_operation_state": state, "daily_producer_status": producer,
        "runtime_release_status": runtime, "trusted_subset_status": trusted,
        "acquisition": {"resolved_completed_session": SESSION}, "daily_producer_run_identity": "run:test",
        "daily_producer_operation_identity": "daily_research_session_operation:test", "operation_identity": "canonical:test",
    }), encoding="utf-8")
    return source


@pytest.mark.parametrize("field,value", [("state", "FAILED"), ("runtime", "NOT_READY"), ("trusted", "NOT_READY")])
def test_completion_gate_refuses_incomplete_daily(tmp_path, field, value):
    kwargs = {field: value}
    _write_completion(tmp_path, **kwargs)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    with pytest.raises(workflow.OwnerDailyError, match="CANONICAL_GATE_FAILED"):
        workflow.verify_daily_completion(tmp_path, runtime, session=SESSION)


def test_completion_gate_returns_exact_source_operation(tmp_path):
    source = _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    result = workflow.verify_daily_completion(tmp_path, runtime, session=SESSION)
    assert result["session"] == SESSION
    assert result["source"] == source


def test_unexpected_post_daily_diff_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(workflow, "_tracked_changes", lambda _: [" M config/daily_research_session_input_registry.json", " M README.md"])
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_POST_DAILY_DIFF:README.md"):
        workflow.commit_daily_state(tmp_path, SESSION)


def test_main_writes_a_result_file_on_an_uncaught_exception(monkeypatch, tmp_path):
    def _boom(**_k):
        raise RuntimeError("SIMULATED_UNEXPECTED_FAILURE")

    monkeypatch.setattr(workflow, "run_workflow", _boom)
    result_path = tmp_path / "result.json"
    code = workflow.main(["--result-path", str(result_path)])
    assert code == 2
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["status"] == "INTERRUPTED"
    assert "SIMULATED_UNEXPECTED_FAILURE" in payload["reason"]


def test_main_writes_a_result_file_on_keyboard_interrupt_then_reraises(monkeypatch, tmp_path):
    def _interrupt(**_k):
        raise KeyboardInterrupt()

    monkeypatch.setattr(workflow, "run_workflow", _interrupt)
    result_path = tmp_path / "result.json"
    with pytest.raises(KeyboardInterrupt):
        workflow.main(["--result-path", str(result_path)])
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["status"] == "INTERRUPTED"
    assert payload["reason"] == "KEYBOARD_INTERRUPT"


def _ready_dashboard(_root, _runtime, session, **_k):
    return {"status": "READY", "expected_session": session, "observed_session": session, "build_id": "b"}


def test_successful_replay_allows_publication_and_reuses_daily(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    calls: list[str] = []
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: calls.append("publish") or {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda _root, session: {"status": "READY", "session": session, "json_path": "private.json", "view_path": "private.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _path: {"status": "READY"})
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    assert result["status"] == "PASS"
    assert result["daily_status"] == "ALREADY_COMPLETED / REUSED"
    assert result["dashboard"]["status"] == "READY"
    assert calls == ["publish"]


def test_action_center_receives_the_exact_completed_session(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    seen: list[str] = []
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda _root, session: seen.append(session) or {"status": "READY", "session": session, "json_path": "private.json", "view_path": "private.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _path: {"status": "READY"})
    assert workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)["status"] == "PASS"
    assert seen == [SESSION]


def test_action_center_failure_is_partial_after_core_success(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "PARTIAL", "reason": "ACTION_CENTER_MATERIALIZATION_FAILED:test"})
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    assert result["status"] == "PARTIAL"
    assert result["ai_handoff"]["remote"]["remote_sha"] == "ai"
    assert result["dashboard"]["status"] == "READY"


def test_view_open_failure_is_non_fatal(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "private.json", "view_path": "private.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _path: {"status": "READY_VIEW_OPEN_FAILED", "reason": "VIEW_OPEN_FAILED:test"})
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    assert result["status"] == "PASS"
    assert result["action_center"]["view_open"]["status"] == "READY_VIEW_OPEN_FAILED"


# --- WORKSPACE_DIAGNOSTIC_TRANSPARENCY_AND_DAILY_DASHBOARD_BINDING_V1: Daily -> Dashboard ---

def test_daily_resolved_session_passed_exactly_into_dashboard_publisher(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    seen = {}
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    def _capture_and_publish(root, rt, session, **k):
        seen["session"] = session
        return _ready_dashboard(root, rt, session)
    monkeypatch.setattr(workflow, "publish_dashboard_release", _capture_and_publish)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    assert seen["session"] == SESSION
    assert result["status"] == "PASS"


def test_normal_daily_uses_the_same_dashboard_publication_boundary(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    seen: list[str] = []
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: seen.append("daily"))
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: seen.append("dashboard") or _ready_dashboard(*a, **k))
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff")

    assert result["status"] == "PASS"
    assert result["daily_status"] == "COMPLETED"
    assert seen == ["daily", "dashboard"]


def test_stale_dashboard_session_produces_partial_never_pass(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: {
        "status": "FAILED", "expected_session": SESSION, "observed_session": "2026-09-15",
        "reason": "DASHBOARD_SESSION_MISMATCH:build_info.market_session='2026-09-15'",
    })
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: pytest.fail("must not open view on PARTIAL"))
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    assert result["status"] == "PARTIAL"
    assert result["dashboard"]["status"] == "FAILED"
    assert result["dashboard"]["expected_session"] == SESSION
    assert result["dashboard"]["observed_session"] == "2026-09-15"


def test_dashboard_publish_failure_does_not_prevent_ai_handoff_or_action_center(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    calls: list[str] = []
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: {"status": "FAILED", "expected_session": SESSION, "observed_session": None, "reason": "x"})
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: calls.append("handoff") or {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: calls.append("action_center") or {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    assert result["status"] == "PARTIAL"
    assert calls == ["handoff", "action_center"]
    assert result["ai_handoff"]["remote"]["remote_sha"] == "ai"
    assert result["action_center"]["status"] == "READY"


def test_dashboard_disabled_flag_skips_publication_and_never_fails_workflow(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: pytest.fail("must not be called when disabled"))
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
                                   replay_completed_session=SESSION, publish_dashboard=False)
    assert result["status"] == "PASS"
    assert result["dashboard"]["status"] == "SKIPPED"


def test_verify_dashboard_session_requires_both_market_and_workspace_session(tmp_path):
    web = tmp_path / "web"; (web / "data").mkdir(parents=True)
    (web / "data" / "build_info.json").write_text(json.dumps({
        "market_session": SESSION,
        "investment_workspace": {"status": "CURRENT", "source_session": "2026-09-15"},
    }), encoding="utf-8")
    result = workflow.verify_dashboard_session(web, SESSION)
    assert result["status"] == "FAILED"
    assert "DASHBOARD_SESSION_MISMATCH" in result["reason"]


def test_verify_dashboard_session_ready_when_both_sessions_match(tmp_path):
    web = tmp_path / "web"; (web / "data").mkdir(parents=True)
    (web / "data" / "build_info.json").write_text(json.dumps({
        "market_session": SESSION, "build_id": "abc",
        "investment_workspace": {"status": "CURRENT", "source_session": SESSION},
    }), encoding="utf-8")
    result = workflow.verify_dashboard_session(web, SESSION)
    assert result["status"] == "READY"
    assert result["observed_session"] == SESSION


def test_publish_dashboard_release_invokes_all_group_with_exact_session(monkeypatch, tmp_path):
    """Group `all` (not `whole-market` alone -- see publish_dashboard_release's own docstring
    for why a whole-market-only publish fails the Dashboard's own release-smoke session-
    coherence gate). No `--generate`/provider-acquisition flags, and never a bare `--expected-
    session` omission that would let the child re-resolve "latest" on its own."""
    captured = {}
    stages: list[str] = []

    class _Result:
        returncode = 0
        stdout = "PUBLICATION_STATE=PUBLISHED\n"
        stderr = ""

    def _fake_run(argv, **kwargs):
        assert stages == ["runtime", "trusted_subset"]
        captured["argv"] = argv
        return _Result()

    def _runtime(*args, **kwargs):
        assert args == (tmp_path, tmp_path / "runtime", SESSION)
        stages.append("runtime")
        return {}

    def _trusted(*args, **kwargs):
        assert args == (tmp_path, tmp_path / "runtime", SESSION)
        stages.append("trusted_subset")
        return {"session": SESSION, "trusted_subset_ready": True}

    monkeypatch.setattr(workflow, "materialize_canonical_runtime_release", _runtime)
    monkeypatch.setattr(workflow, "materialize_canonical_trusted_subset", _trusted)
    monkeypatch.setattr(workflow.subprocess, "run", _fake_run)
    monkeypatch.setattr(workflow, "verify_dashboard_session", lambda web_dir, session: {"status": "READY", "expected_session": session, "observed_session": session})
    web_dir = tmp_path / "web"
    result = workflow.publish_dashboard_release(tmp_path, tmp_path / "runtime", SESSION, web_dir=web_dir)
    argv = captured["argv"]
    assert any("release_orchestrator.py" in str(part) for part in argv)
    assert "all" in argv
    assert "whole-market" not in argv
    assert "--live" in argv
    assert "--complete-publication" in argv
    assert "--expected-session" in argv and argv[argv.index("--expected-session") + 1] == SESSION
    assert "--generate" not in argv
    assert stages == ["runtime", "trusted_subset"]
    assert result["status"] == "READY"
    assert result["publication_state"] == "PUBLISHED"


def test_publish_dashboard_release_can_skip_complete_publication(monkeypatch, tmp_path):
    captured = {}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _Result()

    monkeypatch.setattr(workflow, "materialize_canonical_runtime_release", lambda *a, **k: {})
    monkeypatch.setattr(workflow, "materialize_canonical_trusted_subset", lambda *a, **k: {})
    monkeypatch.setattr(workflow.subprocess, "run", _fake_run)
    monkeypatch.setattr(workflow, "verify_dashboard_session", lambda web_dir, session: {"status": "READY", "expected_session": session, "observed_session": session})
    workflow.publish_dashboard_release(tmp_path, tmp_path / "runtime", SESSION, web_dir=tmp_path / "web", complete_publication=False)
    assert "--complete-publication" not in captured["argv"]


def test_publish_dashboard_release_refuses_missing_trusted_evidence_before_orchestrator(monkeypatch, tmp_path):
    monkeypatch.setattr(workflow, "materialize_canonical_runtime_release", lambda *a, **k: {})
    monkeypatch.setattr(
        workflow, "materialize_canonical_trusted_subset",
        lambda *a, **k: (_ for _ in ()).throw(workflow.CanonicalTrustedSubsetError("STATEMENT_PAYLOAD_ROOT_MISSING")),
    )
    monkeypatch.setattr(workflow.subprocess, "run", lambda *a, **k: pytest.fail("orchestrator must not run"))

    result = workflow.publish_dashboard_release(tmp_path, tmp_path / "runtime", SESSION, web_dir=tmp_path / "web")

    assert result["status"] == "FAILED"
    assert result["expected_session"] == SESSION
    assert result["reason"] == "CANONICAL_TRUSTED_SUBSET_MATERIALIZATION_FAILED:STATEMENT_PAYLOAD_ROOT_MISSING"


def test_verify_dashboard_session_fails_closed_when_build_info_missing(tmp_path):
    web = tmp_path / "web"; web.mkdir()
    result = workflow.verify_dashboard_session(web, SESSION)
    assert result["status"] == "FAILED"
    assert result["observed_session"] is None


def test_failed_daily_prevents_publication(monkeypatch, tmp_path):
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: (_ for _ in ()).throw(workflow.OwnerDailyError("Canonical Daily", "FAILED")))
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: pytest.fail("publication must not run"))
    with pytest.raises(workflow.OwnerDailyError, match="FAILED"):
        workflow.run_workflow(root=tmp_path, runtime_root=tmp_path, handoff_repo=tmp_path / "handoff")


def test_workflow_keeps_private_action_center_out_of_publication_and_uses_safe_git_shortcuts():
    source = Path(workflow.__file__).read_text(encoding="utf-8")
    publication = inspect.getsource(workflow.publish_ai_handoff).lower()
    assert "action_center" not in publication
    assert "portfolio" not in publication
    assert "git add ." not in source
    assert "reset --hard" not in source
    assert '"rebase"' not in source
    assert " push --force" not in source
    assert "DAILY_STATE_ALLOWLIST" in source


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _clone_with_origin(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "stock-core-private.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    seed = tmp_path / "seed"; seed.mkdir(); _git(seed, "init", "-q"); _git(seed, "config", "user.email", "test@example.com"); _git(seed, "config", "user.name", "Test")
    (seed / "README.md").write_text("seed\n"); _git(seed, "add", "README.md"); _git(seed, "commit", "-qm", "seed"); _git(seed, "branch", "-M", "main"); _git(seed, "remote", "add", "origin", str(origin)); _git(seed, "push", "-u", "origin", "main")
    root = tmp_path / "stock-core-private"; subprocess.run(["git", "clone", "-q", str(origin), str(root)], check=True); _git(root, "checkout", "-q", "main")
    return root, origin


def test_clean_behind_origin_is_fast_forwarded(tmp_path):
    root, origin = _clone_with_origin(tmp_path)
    other = tmp_path / "other"; subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True); _git(other, "checkout", "-q", "main"); _git(other, "config", "user.email", "test@example.com"); _git(other, "config", "user.name", "Test")
    (other / "next.txt").write_text("next\n"); _git(other, "add", "next.txt"); _git(other, "commit", "-qm", "next"); _git(other, "push")
    result = workflow.preflight_repository(root, expected_name="stock-core-private", expected_remote_fragment="stock-core-private")
    assert result["status"] == "FAST_FORWARDED"
    assert (root / "next.txt").is_file()


def test_dirty_producer_is_refused(tmp_path):
    root, _origin = _clone_with_origin(tmp_path)
    (root / "README.md").write_text("dirty\n")
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_TRACKED_CHANGES"):
        workflow.preflight_repository(root, expected_name="stock-core-private", expected_remote_fragment="stock-core-private")


def test_approved_untracked_runtime_evidence_does_not_block_preflight(tmp_path):
    root, _origin = _clone_with_origin(tmp_path)
    evidence = root / "data" / "dnse-foreign-flow" / "observations" / "HPG.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text("{}", encoding="utf-8")
    result = workflow.preflight_repository(root, expected_name="stock-core-private", expected_remote_fragment="stock-core-private")
    assert result["status"] == "UP_TO_DATE"
    assert evidence.is_file()


def test_unsafe_untracked_file_is_refused(tmp_path):
    root, _origin = _clone_with_origin(tmp_path)
    (root / "unexpected_module.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(workflow.OwnerDailyError, match="UNSAFE_UNTRACKED_CHECKOUT"):
        workflow.preflight_repository(root, expected_name="stock-core-private", expected_remote_fragment="stock-core-private")


# =====================================================================================
# OWNER_DAILY_GIT_PORCELAIN_STATE_PUBLICATION_CORRECTIVE_V1: `_git`'s whole-stdout `.strip()`
# silently ate the leading space of a `git status --porcelain` record whose XY status code
# starts with a space (e.g. " M path" for an unstaged-only modification), shifting every
# downstream fixed-offset `line[3:]` path slice one character into the path. Real, unmocked git
# repos below so this cannot regress silently through a mocked `_tracked_changes` again.
# =====================================================================================

REGISTRY_PATH = "config/daily_research_session_input_registry.json"


def _clone_with_registry(tmp_path: Path, session: str = SESSION) -> tuple[Path, Path]:
    """Like `_clone_with_origin`, but the seeded repo also carries an already-committed
    ``config/daily_research_session_input_registry.json`` with an empty completed-sessions
    ledger, so a test can apply just the session's completion update as an uncommitted change."""
    root, origin = _clone_with_origin(tmp_path)
    registry_dir = root / "config"
    registry_dir.mkdir(exist_ok=True)
    (registry_dir / "daily_research_session_input_registry.json").write_text(
        json.dumps({"completed_sessions": {}}), encoding="utf-8",
    )
    _git(root, "add", REGISTRY_PATH)
    _git(root, "commit", "-qm", "seed registry")
    _git(root, "push")
    return root, origin


def _write_completed_registry(root: Path, session: str = SESSION) -> None:
    (root / REGISTRY_PATH).write_text(
        json.dumps({"completed_sessions": {session: {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True}}}),
        encoding="utf-8",
    )


def test_tracked_changes_preserves_leading_status_space_for_unstaged_modification(tmp_path):
    root, _origin = _clone_with_registry(tmp_path)
    _write_completed_registry(root)
    lines = workflow._tracked_changes(root)
    assert lines == [" M " + REGISTRY_PATH]
    assert {line[3:] for line in lines} == {REGISTRY_PATH}


def test_commit_daily_state_accepts_real_unstaged_registry_modification(tmp_path):
    root, origin = _clone_with_registry(tmp_path)
    _write_completed_registry(root)
    result = workflow.commit_daily_state(root, SESSION)
    assert result["status"] == "COMMITTED"
    assert workflow._tracked_changes(root) == []
    remote_head = subprocess.run(["git", "-C", str(origin), "rev-parse", "main"], check=True, capture_output=True, text=True).stdout.strip()
    assert remote_head == result["sha"]


def test_commit_daily_state_accepts_staged_only_registry_modification(tmp_path):
    root, _origin = _clone_with_registry(tmp_path)
    _write_completed_registry(root)
    _git(root, "add", REGISTRY_PATH)
    lines = workflow._tracked_changes(root)
    assert lines == ["M  " + REGISTRY_PATH]
    result = workflow.commit_daily_state(root, SESSION)
    assert result["status"] == "COMMITTED"


def test_commit_daily_state_accepts_staged_and_worktree_registry_modification(tmp_path):
    root, _origin = _clone_with_registry(tmp_path)
    _write_completed_registry(root)
    _git(root, "add", REGISTRY_PATH)
    (root / REGISTRY_PATH).write_text(
        json.dumps({"completed_sessions": {SESSION: {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True}}, "note": "second edit"}),
        encoding="utf-8",
    )
    lines = workflow._tracked_changes(root)
    assert lines == ["MM " + REGISTRY_PATH]
    result = workflow.commit_daily_state(root, SESSION)
    assert result["status"] == "COMMITTED"


def test_commit_daily_state_still_rejects_unexpected_tracked_file(tmp_path):
    root, _origin = _clone_with_registry(tmp_path)
    (root / "README.md").write_text("unexpected change\n", encoding="utf-8")
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_POST_DAILY_DIFF:README.md"):
        workflow.commit_daily_state(root, SESSION)


def test_commit_daily_state_still_rejects_mixed_allowlisted_and_unexpected_files(tmp_path):
    root, _origin = _clone_with_registry(tmp_path)
    _write_completed_registry(root)
    (root / "README.md").write_text("unexpected change\n", encoding="utf-8")
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_POST_DAILY_DIFF:README.md") as exc:
        workflow.commit_daily_state(root, SESSION)
    assert REGISTRY_PATH not in str(exc.value)


def test_commit_daily_state_stages_only_allowlisted_path(tmp_path):
    root, _origin = _clone_with_registry(tmp_path)
    _write_completed_registry(root)
    (root / "scratch_untracked.txt").write_text("ignored by this function\n", encoding="utf-8")
    result = workflow.commit_daily_state(root, SESSION)
    assert result["status"] == "COMMITTED"
    committed_files = subprocess.run(
        ["git", "-C", str(root), "show", "--stat", "--pretty=format:", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert REGISTRY_PATH in committed_files
    assert "scratch_untracked.txt" not in committed_files
    # The untracked scratch file must remain on disk, untouched by this function.
    assert (root / "scratch_untracked.txt").is_file()


def test_commit_daily_state_no_change_when_registry_already_matches_committed_state(tmp_path):
    root, _origin = _clone_with_registry(tmp_path)
    result = workflow.commit_daily_state(root, SESSION)
    assert result["status"] == "NO_CHANGE"


# =====================================================================================
# CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1: durable owner-operation
# journal + auto-resume. A hard terminal close/process kill cannot run cleanup code -- the next
# ORDINARY invocation (no --replay-completed-session) must resume from the last durable stage
# without reacquiring/re-running Daily Producer for a session that already fully completed.
# =====================================================================================

def test_auto_resumable_session_none_without_journal(tmp_path):
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    assert workflow._auto_resumable_session(tmp_path, runtime) is None


def test_auto_resumable_session_none_when_journal_session_not_actually_complete(tmp_path):
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    entry = journal.start_run(tmp_path)
    journal.advance(tmp_path, entry["run_id"], journal.LOCAL_COMPLETE, resolved_session=SESSION)
    # No canonical-daily-operation-v1 record exists for SESSION -- verify_daily_completion must
    # fail, so this must never be offered as auto-resumable.
    assert workflow._auto_resumable_session(tmp_path, runtime) is None


def test_auto_resumable_session_returns_session_when_verifiably_complete(tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    entry = journal.start_run(tmp_path)
    journal.advance(tmp_path, entry["run_id"], journal.PRODUCER_STATE_RETAINED, resolved_session=SESSION)
    assert workflow._auto_resumable_session(tmp_path, runtime) == SESSION


def test_run_workflow_auto_resumes_without_explicit_replay_flag(monkeypatch, tmp_path):
    """Section 5/13 acceptance: the next ordinary owner invocation resumes without
    --replay-completed-session and never reacquires (never calls _run_daily again) once the
    session already fully completed."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    entry = journal.start_run(tmp_path)
    journal.advance(tmp_path, entry["run_id"], journal.LOCAL_COMPLETE, resolved_session=SESSION)
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: pytest.fail("must not reacquire an already-completed session"))
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff")

    assert result["status"] == "PASS"
    assert result["daily_status"] == "ALREADY_COMPLETED / RESUMED"
    final_journal = journal.read_journal(tmp_path)
    assert final_journal["stage"] == journal.COMPLETE
    assert final_journal["resolved_session"] == SESSION


def test_run_workflow_writes_journal_stages_through_to_complete(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    assert result["status"] == "PASS"
    final_journal = journal.read_journal(tmp_path)
    assert final_journal["stage"] == journal.COMPLETE
    stages = [row["stage"] for row in final_journal["stage_history"]]
    assert stages == [journal.STARTED, journal.LOCAL_COMPLETE, journal.PRODUCER_STATE_RETAINED,
                      journal.PRESENTATION_BOUND, journal.DASHBOARD_PUBLISHED, journal.AI_HANDOFF_PUBLISHED,
                      journal.ACTION_CENTER_READY, journal.COMPLETE]
    assert final_journal["attestation"]["session"] == SESSION
    assert final_journal["attestation"]["ai_handoff"]["remote_sha"] == "ai"


def test_run_workflow_partial_advances_to_blocked_not_complete(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: {"status": "FAILED", "expected_session": SESSION, "observed_session": None, "reason": "x"})
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    assert result["status"] == "PARTIAL"
    final_journal = journal.read_journal(tmp_path)
    # Dashboard failure never blocks the independent AI handoff / Action Center steps (existing
    # PARTIAL behavior) -- both still complete and advance the journal; only the final
    # PASS-only COMPLETE stage is withheld, with BLOCKED recorded as failure metadata.
    assert final_journal["stage"] == journal.ACTION_CENTER_READY
    assert final_journal["failure"]["stage"] == journal.BLOCKED


def test_run_workflow_marks_journal_failed_on_exception_and_next_run_resumes_without_reacquisition(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})

    def boom(*a, **k):
        raise RuntimeError("dashboard publisher exploded")

    monkeypatch.setattr(workflow, "publish_dashboard_release", boom)
    with pytest.raises(RuntimeError, match="exploded"):
        workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    interrupted = journal.read_journal(tmp_path)
    # PRESENTATION_BOUND is unconditional bookkeeping right after PRODUCER_STATE_RETAINED (the
    # presentation join already happened inside canonical_daily_operation.py itself) -- the
    # crash happens one step later, at Dashboard publication.
    assert interrupted["stage"] == journal.PRESENTATION_BOUND
    assert interrupted["failure"]["stage"] == journal.FAILED
    assert "exploded" in interrupted["failure"]["detail"]["reason"]

    # The NEXT ordinary invocation (no explicit replay flag) must resume without reacquiring.
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: pytest.fail("must not reacquire on resume"))

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff")
    assert result["status"] == "PASS"
    assert result["daily_status"] == "ALREADY_COMPLETED / RESUMED"
    assert journal.read_journal(tmp_path)["stage"] == journal.COMPLETE


def test_run_workflow_marks_journal_interrupted_on_keyboard_interrupt(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})

    def interrupt(*a, **k):
        raise KeyboardInterrupt()

    monkeypatch.setattr(workflow, "commit_daily_state", interrupt)
    with pytest.raises(KeyboardInterrupt):
        workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    interrupted = journal.read_journal(tmp_path)
    assert interrupted["stage"] == journal.LOCAL_COMPLETE
    assert interrupted["failure"]["stage"] == journal.INTERRUPTED


def test_run_workflow_never_raises_on_journal_write_failure(monkeypatch, tmp_path):
    """A journal write failure (disk full, permissions, ...) must degrade the crash-resume
    convenience for this one run, never the real owner Daily workflow itself."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})
    monkeypatch.setattr(workflow.journal, "advance", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    assert result["status"] == "PASS"
