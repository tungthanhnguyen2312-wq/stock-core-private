from __future__ import annotations

import json
import inspect
import subprocess
from pathlib import Path

import pytest

from tools import run_owner_daily as workflow


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

    class _Result:
        returncode = 0
        stdout = "PUBLICATION_STATE=PUBLISHED\n"
        stderr = ""

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _Result()

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

    monkeypatch.setattr(workflow.subprocess, "run", _fake_run)
    monkeypatch.setattr(workflow, "verify_dashboard_session", lambda web_dir, session: {"status": "READY", "expected_session": session, "observed_session": session})
    workflow.publish_dashboard_release(tmp_path, tmp_path / "runtime", SESSION, web_dir=tmp_path / "web", complete_publication=False)
    assert "--complete-publication" not in captured["argv"]


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
