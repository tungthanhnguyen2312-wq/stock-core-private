from __future__ import annotations

import json
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


def test_successful_replay_allows_publication_and_reuses_daily(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    calls: list[str] = []
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: calls.append("publish") or {"remote": {"remote_sha": "ai"}})
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    assert result["status"] == "PASS"
    assert result["daily_status"] == "ALREADY_COMPLETED / REUSED"
    assert calls == ["publish"]


def test_failed_daily_prevents_publication(monkeypatch, tmp_path):
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: (_ for _ in ()).throw(workflow.OwnerDailyError("Canonical Daily", "FAILED")))
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: pytest.fail("publication must not run"))
    with pytest.raises(workflow.OwnerDailyError, match="FAILED"):
        workflow.run_workflow(root=tmp_path, runtime_root=tmp_path, handoff_repo=tmp_path / "handoff")


def test_workflow_has_no_portfolio_access_or_unsafe_git_shortcuts():
    source = Path(workflow.__file__).read_text(encoding="utf-8")
    assert ".stocklookup\\portfolio" not in source
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
