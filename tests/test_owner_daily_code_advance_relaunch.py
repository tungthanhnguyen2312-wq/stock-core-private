"""OWNER_DAILY_AI_HANDOFF_IMPORT_RECOVERY_20261012.

The 2026-10-12 Owner Daily process imported tools/run_owner_daily.py at 95216b77; its own
phase-1 preflight then fast-forwarded the checkout to the V3 merge d11b1016, and phase 6 ran the
pre-pull ``resolve_m1_handoff_authority``, whose ``import daily_integrated_decision_brief`` no
longer existed on disk (ModuleNotFoundError after Canonical Daily, Producer state and Dashboard
had completed). These tests pin the corrective: no phase after a Producer fast-forward ever runs
on the pre-pull code, the entrypoint is relaunched exactly once on the new HEAD, the phase-6
import chain resolves cold from the production entry context, and a run interrupted after the
Dashboard resumes without re-running Canonical Daily and publishes the AI handoff exactly once.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tools import run_owner_daily as workflow
import owner_daily_journal as journal
import owner_daily_progress as progress
from release_checkout_identity import PUBLISHED

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "tools" / "run_owner_daily.py"
SESSION = "2026-10-12"
PHASE_6_FUNCTIONS = ("publish_ai_handoff", "_sealed_operation_manifest", "resolve_m1_handoff_authority")


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    # Real external state (Dashboard checkout, AI handoff repo, Action Center root, host capacity)
    # never decides these tests; each test that needs a verified proof supplies it explicitly.
    monkeypatch.delenv("STOCK_LOOKUP_OWNER_DAILY_CODE_HEAD", raising=False)
    monkeypatch.setattr(workflow, "_verify_dashboard_published", lambda *a, **k: None)
    monkeypatch.setattr(workflow, "_verify_ai_handoff_published", lambda *a, **k: None)
    monkeypatch.setattr(workflow, "_verify_action_center_ready", lambda *a, **k: None)
    monkeypatch.setattr(workflow, "_require_host_ready", lambda *a, **k: {"classification": "READY"})
    monkeypatch.setattr(workflow, "_presentation_bound_state", lambda *a, **k: "BOUND")


def _later_phases_forbidden(monkeypatch, calls: list[str]) -> None:
    def forbid(name):
        return lambda *a, **k: calls.append(name) or pytest.fail(f"{name} ran on pre-pull code")
    for name in ("preflight_consumer_repository", "preflight_dashboard_repository", "_run_daily",
                 "verify_daily_completion", "commit_daily_state", "publish_dashboard_release",
                 "publish_ai_handoff", "materialize_action_center"):
        monkeypatch.setattr(workflow, name, forbid(name))


def _write_completion(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "daily_research_session_input_registry.json").write_text(json.dumps({
        "completed_sessions": {SESSION: {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True}},
    }), encoding="utf-8")
    source = root / "operations-review" / "daily-research-session-operations-v1" / SESSION / "op"
    source.mkdir(parents=True)
    for name in ("ai_research_session_bundle.json", "daily_opportunity_decision_queue_artifact.json"):
        (source / name).write_text("{}", encoding="utf-8")
    (source / "ai_research_bundle_manifest.json").write_text(
        json.dumps({"operation_identity": "daily_research_session_operation:test"}), encoding="utf-8")
    record_path = root / "operations-review" / "canonical-daily-operation-v1" / SESSION / "op" / "daily_operation_record.json"
    record_path.parent.mkdir(parents=True)
    record_path.write_text(json.dumps({
        "session": SESSION, "daily_operation_state": "LOCAL_COMPLETE", "daily_producer_status": "COMPLETED",
        "runtime_release_status": "READY", "trusted_subset_status": "READY",
        "acquisition": {"resolved_completed_session": SESSION}, "daily_producer_run_identity": "run:test",
        "daily_producer_operation_identity": "daily_research_session_operation:test", "operation_identity": "canonical:test",
    }), encoding="utf-8")


# --- The exact defect: a Producer fast-forward must never be followed by more pre-pull code ---

def test_fast_forward_stops_the_workflow_before_any_later_phase(monkeypatch, tmp_path):
    calls: list[str] = []
    _later_phases_forbidden(monkeypatch, calls)
    monkeypatch.setattr(workflow, "preflight_repository",
                        lambda *a, **k: {"head": "f" * 40, "status": "FAST_FORWARDED"})

    # Pre-fix this reached preflight_consumer_repository (and on to phase 6) on the pre-pull code.
    with pytest.raises(Exception) as advanced:
        workflow.run_workflow(root=tmp_path, runtime_root=tmp_path / "runtime",
                              handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    assert type(advanced.value).__name__ == "ProducerCodeAdvanced"
    assert advanced.value.head == "f" * 40
    assert calls == []
    # Not recorded as a failure: the relaunched process supersedes this journal run.
    entry = journal.read_journal(tmp_path)
    assert entry["stage"] == journal.SESSION_RESOLVED and entry["failure"] is None


def test_real_git_fast_forward_signals_relaunch_before_consumer_preflight(monkeypatch, tmp_path):
    def git(path: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)

    origin = tmp_path / "stock-core-private.git"
    subprocess.run(["git", "init", "--bare", "-q", "--initial-branch=main", str(origin)], check=True)
    root = tmp_path / "stock-core-private"
    subprocess.run(["git", "clone", "-q", str(origin), str(root)], check=True, capture_output=True)
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True, capture_output=True)
    for checkout in (root, other):
        git(checkout, "config", "user.email", "test@example.com")
        git(checkout, "config", "user.name", "Test")
    (root / "README.md").write_text("seed\n")
    (root / ".gitignore").write_text("operations-review/\n")  # where the owner journal lives
    git(root, "checkout", "-q", "-b", "main")
    git(root, "add", "README.md", ".gitignore"); git(root, "commit", "-qm", "seed"); git(root, "push", "-q", "-u", "origin", "main")
    git(other, "fetch", "-q"); git(other, "checkout", "-q", "main")
    (other / "relocated.txt").write_text("v3\n"); git(other, "add", "relocated.txt"); git(other, "commit", "-qm", "v3"); git(other, "push", "-q")
    pushed = subprocess.run(["git", "-C", str(other), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    calls: list[str] = []
    _later_phases_forbidden(monkeypatch, calls)

    with pytest.raises(workflow.ProducerCodeAdvanced) as advanced:
        workflow.run_workflow(root=root, runtime_root=tmp_path / "runtime",
                              handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    assert advanced.value.head == pushed
    assert (root / "relocated.txt").is_file()  # the governed fast-forward itself still happened
    assert calls == []


def test_main_relaunches_the_same_entrypoint_once_on_the_new_head(monkeypatch, tmp_path):
    result_path = tmp_path / "logs" / "result.json"
    progress_path = tmp_path / "logs" / "progress.jsonl"
    argv = ["--result-path", str(result_path), "--progress-path", str(progress_path),
            "--replay-completed-session", SESSION]
    monkeypatch.setattr(workflow, "run_workflow", lambda **_k: (_ for _ in ()).throw(workflow.ProducerCodeAdvanced("a" * 40)))
    launched: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        launched.append((command, kwargs))
        return subprocess.CompletedProcess(command, 3)

    monkeypatch.setattr(workflow.subprocess, "run", fake_run)
    monkeypatch.setattr(workflow, "safe_progress_path", lambda path, root: path)

    assert workflow.main(argv) == 3

    assert len(launched) == 1
    command, kwargs = launched[0]
    assert command == [sys.executable, "-u", str(ENTRY), *argv]
    assert kwargs["cwd"] == workflow.ROOT and kwargs["check"] is False
    env = kwargs["env"]
    assert env[workflow.CODE_HEAD_ENV] == "a" * 40
    assert len(env[progress.RUN_ID_ENV]) == 32
    assert progress.RUN_STARTED_AT_ENV in env and progress.RUN_STARTED_MONOTONIC_ENV in env
    assert not result_path.exists()  # the relaunched process owns the result file


def test_relaunch_that_cannot_start_writes_a_failed_result(monkeypatch, tmp_path):
    monkeypatch.setattr(workflow, "run_workflow", lambda **_k: (_ for _ in ()).throw(workflow.ProducerCodeAdvanced("a" * 40)))
    monkeypatch.setattr(workflow.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("python")))
    monkeypatch.setattr(workflow, "_auto_resumable_session", lambda *a, **k: None)
    result_path = tmp_path / "result.json"

    assert workflow.main(["--result-path", str(result_path)]) == 1

    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "FAILED"
    assert result["reason"] == "PRODUCER_CODE_RELAUNCH_FAILED:FileNotFoundError"


def test_relaunched_process_fails_closed_on_a_second_fast_forward(monkeypatch, tmp_path):
    monkeypatch.setenv(workflow.CODE_HEAD_ENV, "a" * 40)
    calls: list[str] = []
    _later_phases_forbidden(monkeypatch, calls)
    monkeypatch.setattr(workflow, "preflight_repository",
                        lambda *a, **k: {"head": "b" * 40, "status": "FAST_FORWARDED"})
    root = tmp_path / "stock-core-private"; root.mkdir()
    real_run_workflow = workflow.run_workflow
    monkeypatch.setattr(workflow, "run_workflow",
                        lambda **k: real_run_workflow(root=root, **{**k, "runtime_root": tmp_path / "runtime"}))
    monkeypatch.setattr(workflow.subprocess, "run", lambda *a, **k: pytest.fail("must not relaunch twice"))
    result_path = tmp_path / "logs" / "result.json"

    assert workflow.main(["--result-path", str(result_path), "--replay-completed-session", SESSION]) == 1

    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "FAILED"
    assert result["reason"] == "PRODUCER_CODE_ADVANCED_AFTER_RELAUNCH:" + "b" * 40
    assert calls == []
    assert journal.read_journal(root)["failure"]["detail"]["reason"].endswith("b" * 40)


def test_relaunched_process_continues_the_same_run_without_a_second_owner_view(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(workflow.CODE_HEAD_ENV, "a" * 40)
    monkeypatch.setenv(progress.RUN_ID_ENV, "run-from-parent")
    monkeypatch.setenv(progress.RUN_STARTED_AT_ENV, "2026-10-12T11:26:55+00:00")
    monkeypatch.setenv(progress.STRUCTURED_CONSOLE_ENV, "1")
    monkeypatch.setattr(workflow, "run_workflow", lambda **_k: {"status": "PASS", "session": SESSION})
    result_path = tmp_path / "result.json"

    assert workflow.main(["--result-path", str(result_path)]) == 0

    assert "OWNER_DAILY_PRESENTATION=" not in capsys.readouterr().out
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "PASS"
    assert result["telemetry"]["run_id"] == "run-from-parent"


def test_up_to_date_producer_runs_in_process_without_relaunch(monkeypatch, tmp_path):
    monkeypatch.setattr(workflow.subprocess, "run", lambda *a, **k: pytest.fail("no relaunch when nothing advanced"))
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "p", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "preflight_consumer_repository", lambda *a, **k: {"head": "c", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "p", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda _r, s: {"status": "READY", "session": s, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
                                   publish_dashboard=False, replay_completed_session=SESSION)

    assert result["status"] == "PASS"


# --- Cold-start phase-6 import chain from the production entry context ---

def _function_local_imports() -> tuple[list[ast.stmt], dict[str, list[str]]]:
    tree = ast.parse(ENTRY.read_text(encoding="utf-8"))
    nodes: list[ast.stmt] = []
    owners: dict[str, list[str]] = {}
    for function in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        for node in ast.walk(function):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                nodes.append(node)
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                owners.setdefault(function.name, []).extend(names)
    return nodes, owners


def test_phase_6_imports_are_function_local_and_include_the_failed_module():
    _nodes, owners = _function_local_imports()
    assert all(owners.get(name) for name in PHASE_6_FUNCTIONS)
    assert "stocklookup_core.decision.daily_integrated_decision_brief" in owners["resolve_m1_handoff_authority"]
    assert "daily_integrated_decision_brief" not in {m for names in owners.values() for m in names}


def test_every_lazy_entry_import_resolves_cold_from_the_production_entry_context(tmp_path):
    """A fresh interpreter, started the way ``python -u tools/run_owner_daily.py`` starts (script
    directory first on sys.path, foreign cwd, nothing preloaded), loads the entry module and then
    executes every function-local import statement it contains -- the actual statements, phase 6
    included -- with provider packages refused and any network socket refused."""
    nodes, _owners = _function_local_imports()
    statements = ast.unparse(ast.Module(body=nodes, type_ignores=[]))
    script = textwrap.dedent(f"""
        import importlib.util, json, socket, sys
        class _NoProvider:
            def find_spec(self, name, path=None, target=None):
                if name.partition(".")[0] in ("vnstock", "vnai"):
                    raise ModuleNotFoundError("PROVIDER_BLOCKED:" + name, name=name)
        sys.meta_path.insert(0, _NoProvider())
        def _no_network(*a, **k):
            raise OSError("NETWORK_BLOCKED")
        socket.socket.connect = _no_network
        socket.create_connection = _no_network
        sys.path[0] = {str(ENTRY.parent)!r}
        before = set(sys.modules)
        assert not any("daily_integrated_decision_brief" in m for m in before)
        spec = importlib.util.spec_from_file_location("owner_daily_entry", {str(ENTRY)!r})
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert not any("daily_integrated_decision_brief" in m for m in sys.modules), "phase 6 must stay lazy"
    """) + statements + textwrap.dedent("""
        import stocklookup_core.decision.daily_integrated_decision_brief as brief
        assert brief.__file__.replace("\\\\", "/").endswith("stocklookup_core/decision/daily_integrated_decision_brief.py")
        assert "daily_integrated_decision_brief" not in sys.modules
        assert not [m for m in sys.modules if m.partition(".")[0] in ("vnstock", "vnai")]
        print("COLD_PHASE6_IMPORTS_OK")
    """)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONSTARTUP", "STOCK_LOOKUP_OWNER_DAILY_CODE_HEAD")}
    completed = subprocess.run([sys.executable, "-u", "-c", script], cwd=tmp_path, env=env,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    assert completed.returncode == 0, completed.stderr[-4000:]
    assert "COLD_PHASE6_IMPORTS_OK" in completed.stdout


# --- 2026-10-12 shape: interrupted after Dashboard, resumed without re-running Canonical Daily ---

def _interrupted_after_dashboard(root: Path) -> None:
    run = journal.start_run(root, intended_session=SESSION)["run_id"]
    for stage in (journal.SESSION_RESOLVED, journal.LOCAL_COMPLETE, journal.PRODUCER_STATE_RETAINED,
                  journal.PRESENTATION_BOUND, journal.DASHBOARD_PUBLISHED):
        journal.advance(root, run, stage, resolved_session=SESSION)
    journal.advance(root, run, journal.FAILED,
                    detail={"reason": "ModuleNotFoundError:No module named 'daily_integrated_decision_brief'"})


def test_interrupted_after_dashboard_resumes_and_publishes_the_handoff_exactly_once(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    _interrupted_after_dashboard(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    published: dict[str, str] = {}
    handoffs: list[str] = []
    action_centers: list[str] = []
    monkeypatch.setattr(workflow, "_run_daily", lambda *a, **k: pytest.fail("Canonical Daily must not rerun"))
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "p", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "preflight_consumer_repository", lambda *a, **k: {"head": "c", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "preflight_dashboard_repository", lambda *a, **k: {"head": "d", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "p", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "_verify_dashboard_published", lambda *a, **k: {
        "status": "READY", "expected_session": SESSION, "observed_session": SESSION,
        "publication_state": PUBLISHED, "release_source_sha": "d" * 40, "public_byte_identity": "PASS",
        "build_id": "b", "resume_status": "REUSED_EXISTING_PUBLICATION"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: pytest.fail("verified Dashboard must not republish"))
    monkeypatch.setattr(workflow, "_verify_ai_handoff_published",
                        lambda repo, session: dict(published) if published.get("latest_session") == session else None)

    def publish(root, repo, completion):
        handoffs.append(completion["session"])
        published.update(remote_sha="ai" * 20, latest_session=completion["session"], handoff_build_id="handoff_build_x")
        return {"publication": {"status": "PUBLISHED"}, "remote": {"remote_sha": "ai" * 20, "handoff_build_id": "handoff_build_x"}}

    monkeypatch.setattr(workflow, "publish_ai_handoff", publish)
    monkeypatch.setattr(workflow, "materialize_action_center",
                        lambda _r, s: action_centers.append(s) or {"status": "READY", "session": s, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    first = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
                                  replay_completed_session=SESSION)
    second = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
                                   replay_completed_session=SESSION)

    assert first["status"] == second["status"] == "PASS"
    assert first["daily_status"] == "ALREADY_COMPLETED / REUSED"
    assert handoffs == [SESSION]  # exactly once across both replays
    assert second["ai_handoff"]["publication"]["status"] == "ALREADY_PUBLISHED_VERIFIED"
    assert first["dashboard"]["publication_state"] == PUBLISHED
    assert action_centers == [SESSION, SESSION]
    entry = journal.read_journal(tmp_path)
    assert entry["stage"] == journal.COMPLETE
    assert entry["attestation"]["ai_handoff"] == {"session": SESSION, "remote_sha": "ai" * 20, "handoff_build_id": "handoff_build_x"}
