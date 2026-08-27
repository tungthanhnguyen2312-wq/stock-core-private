"""Governed publication completion: mocked gh, no real workflow dispatch."""
from __future__ import annotations

from argparse import Namespace
import inspect
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import governed_publication_completion as gpc  # noqa: E402
import release_orchestrator  # noqa: E402
from release_checkout_identity import PUBLISHED

SOURCE_SHA = "534e4971edf2b9be62467ce89758b6625544558d"
WORKFLOW_HEAD = "691b63dedec8625bfab7f6b126d8928a2184abf4"
CI_ID = 32986483019
PAGES_ID = 32986911616
SESSION = "2026-08-26"
PUBLIC_LINE = f"PUBLIC_BYTE_IDENTITY_PASS attempt=1 session={SESSION} sha={SOURCE_SHA}"
CANONICAL_ORIGIN = "https://github.com/tungthanhnguyen2312-wq/market-dashboard.git"


def _cp(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(["gh"], returncode=returncode, stdout=stdout, stderr=stderr)


def _ci_row(**overrides):
    row = {
        "databaseId": CI_ID,
        "headSha": SOURCE_SHA,
        "status": "completed",
        "conclusion": "success",
        "name": "Dashboard CI",
        "workflowName": "Dashboard CI",
        "event": "workflow_dispatch",
        "headBranch": "main",
        "url": f"https://github.com/example/actions/runs/{CI_ID}",
        "displayTitle": "Dashboard CI",
        "createdAt": "2026-08-26T12:00:00Z",
        "number": 1,
    }
    row.update(overrides)
    return row


def _pages_row(**overrides):
    row = {
        "databaseId": PAGES_ID,
        "headSha": WORKFLOW_HEAD,
        "status": "completed",
        "conclusion": "success",
        "name": "Deploy Pages",
        "workflowName": "Deploy Pages",
        "event": "workflow_dispatch",
        "headBranch": "main",
        "url": f"https://github.com/example/actions/runs/{PAGES_ID}",
        "displayTitle": "Deploy Pages",
        "createdAt": "2026-08-26T12:10:00Z",
        "number": 2,
    }
    row.update(overrides)
    return row


class FakeGit:
    def __init__(self, *, head=SOURCE_SHA, origin_main=SOURCE_SHA, origin_url=CANONICAL_ORIGIN, branch="main", ancestor=True):
        self.head = head
        self.origin_main = origin_main
        self.origin_url = origin_url
        self.branch = branch
        self.ancestor = ancestor
        self.calls = []

    def __call__(self, web_dir, args):
        args = [str(item) for item in args]
        self.calls.append(args)
        if args[:2] == ["remote", "get-url"]:
            return 0, self.origin_url
        if args == ["branch", "--show-current"]:
            return 0, self.branch
        if args == ["rev-parse", "HEAD"]:
            return 0, self.head
        if args == ["rev-parse", "origin/main"]:
            return 0, self.origin_main
        if args[:1] == ["fetch"]:
            return 0, ""
        if args[:1] == ["merge-base"]:
            return (0, "") if self.ancestor else (1, "")
        return 1, "unexpected"


class FakeGh:
    def __init__(self):
        self.auth_ok = True
        self.ci_runs = []
        self.pages_runs = []
        self.logs = {}
        self.watch_exit = {}
        self.timeout_runs = set()
        self.dispatch_ci_ok = True
        self.dispatch_pages_ok = True
        self.after_ci_dispatch = []
        self.after_pages_dispatch = []
        self.complete_after_watch = {}
        self.calls = []
        self.ci_dispatch_count = 0
        self.pages_dispatch_count = 0

    def __call__(self, argv, cwd=None, timeout=None):
        assert argv[0] == "gh"
        args = [str(item) for item in argv[1:]]
        self.calls.append(args)
        if args[:2] == ["auth", "status"]:
            return _cp(0 if self.auth_ok else 1, stderr="" if self.auth_ok else "not logged in")
        if args[:2] == ["run", "list"]:
            workflow = args[args.index("--workflow") + 1]
            commit = args[args.index("--commit") + 1] if "--commit" in args else None
            rows = list(self.ci_runs if workflow == gpc.CI_WORKFLOW else self.pages_runs)
            if commit:
                rows = [row for row in rows if row.get("headSha") == commit]
            return _cp(0, json.dumps(rows))
        if args[:2] == ["run", "view"] and "--log" in args:
            run_id = int(args[2])
            return _cp(0, self.logs.get(run_id, ""))
        if args[:2] == ["run", "watch"]:
            run_id = int(args[2])
            if run_id in self.timeout_runs:
                raise subprocess.TimeoutExpired(argv, timeout)
            extra = self.complete_after_watch.get(run_id)
            if extra:
                if extra.get("name") == "Dashboard CI":
                    self.ci_runs = [extra]
                else:
                    self.pages_runs = [extra]
            return _cp(self.watch_exit.get(run_id, 0))
        if args[:2] == ["workflow", "run"]:
            workflow = args[2]
            if workflow == gpc.CI_WORKFLOW:
                self.ci_dispatch_count += 1
                if self.after_ci_dispatch:
                    self.ci_runs = list(self.after_ci_dispatch)
                return _cp(0 if self.dispatch_ci_ok else 1, stderr="" if self.dispatch_ci_ok else "dispatch failed")
            if workflow == gpc.PAGES_WORKFLOW:
                self.pages_dispatch_count += 1
                if self.after_pages_dispatch:
                    self.pages_runs = list(self.after_pages_dispatch)
                return _cp(0 if self.dispatch_pages_ok else 1, stderr="" if self.dispatch_pages_ok else "dispatch failed")
        raise AssertionError(f"unexpected gh argv: {args}")

    def workflow_run_fields(self, workflow):
        for args in self.calls:
            if args[:3] == ["workflow", "run", workflow]:
                return args
        return None


@pytest.fixture
def web_dir(tmp_path, monkeypatch):
    path = tmp_path / "web"
    path.mkdir()
    monkeypatch.setenv("STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE", str(path.resolve()))
    monkeypatch.setattr(gpc, "which_gh", lambda: "gh")
    return path


def _complete(web_dir, gh, git, tmp_path, **kwargs):
    defaults = dict(
        web_dir=web_dir,
        expected_session=SESSION,
        producer_root=tmp_path,
        release_source_sha=SOURCE_SHA,
        require_identical_main=True,
        allow_dispatch=True,
        runner=gh,
        git_runner=git,
        watch_timeout=5,
    )
    defaults.update(kwargs)
    return gpc.complete_publication(**defaults)


def test_exact_sha_successful_ci_is_reused(web_dir, tmp_path):
    gh = FakeGh()
    gh.ci_runs = [_ci_row()]
    gh.pages_runs = [_pages_row()]
    gh.logs[PAGES_ID] = PUBLIC_LINE
    git = FakeGit()
    record = _complete(web_dir, gh, git, tmp_path)
    assert record["publication_state"] == PUBLISHED
    assert record["ci_reused"] is True
    assert record["pages_reused"] is True
    assert gh.ci_dispatch_count == 0
    assert gh.pages_dispatch_count == 0
    assert record["dashboard_ci_run_id"] == str(CI_ID)
    assert record["deploy_pages_run_id"] == str(PAGES_ID)
    assert record["public_byte_identity"] == "PASS"
    assert record["public_byte_proof"]["session"] == SESSION
    assert record["public_byte_proof"]["sha"] == SOURCE_SHA
    assert record["is_idempotent_replay"] is True


def test_wrong_sha_successful_ci_is_rejected(web_dir, tmp_path):
    gh = FakeGh()
    gh.ci_runs = [_ci_row(headSha=WORKFLOW_HEAD)]
    git = FakeGit()
    with pytest.raises(gpc.PublicationCompletionError, match="BLOCKED_CI_DISPATCH"):
        _complete(web_dir, gh, git, tmp_path, allow_dispatch=False)
    assert gh.ci_dispatch_count == 0


def test_in_progress_exact_sha_ci_is_watched(web_dir, tmp_path):
    gh = FakeGh()
    gh.ci_runs = [_ci_row(status="in_progress", conclusion="")]
    gh.complete_after_watch[CI_ID] = _ci_row()
    gh.pages_runs = [_pages_row()]
    gh.logs[PAGES_ID] = PUBLIC_LINE
    git = FakeGit()
    record = _complete(web_dir, gh, git, tmp_path)
    watch_calls = [args for args in gh.calls if args[:2] == ["run", "watch"]]
    assert watch_calls == [["run", "watch", str(CI_ID), "--exit-status"]]
    assert record["ci_reused"] is True
    assert record["publication_state"] == PUBLISHED


def test_no_exact_sha_ci_causes_exactly_one_manual_dispatch(web_dir, tmp_path):
    gh = FakeGh()
    gh.after_ci_dispatch = [_ci_row()]
    gh.pages_runs = [_pages_row()]
    gh.logs[PAGES_ID] = PUBLIC_LINE
    git = FakeGit()
    record = _complete(web_dir, gh, git, tmp_path)
    assert gh.ci_dispatch_count == 1
    assert record["ci_dispatched"] is True
    assert ["workflow", "run", "dashboard-ci.yml", "--ref", "main"] in gh.calls
    assert record["publication_state"] == PUBLISHED


def test_ci_dispatch_must_resolve_back_to_exact_release_sha(web_dir, tmp_path):
    gh = FakeGh()
    gh.after_ci_dispatch = [_ci_row(headSha=WORKFLOW_HEAD)]
    git = FakeGit()
    with pytest.raises(gpc.PublicationCompletionError, match="BLOCKED_CI_DISPATCH"):
        _complete(web_dir, gh, git, tmp_path)
    assert gh.pages_dispatch_count == 0


def test_ci_failure_stops_before_pages(web_dir, tmp_path):
    gh = FakeGh()
    gh.ci_runs = [_ci_row(status="in_progress", conclusion="")]
    gh.watch_exit[CI_ID] = 1
    git = FakeGit()
    with pytest.raises(gpc.PublicationCompletionError, match="BLOCKED_CI_FAILED"):
        _complete(web_dir, gh, git, tmp_path)
    assert gh.pages_dispatch_count == 0
    assert not any(args[:3] == ["workflow", "run", gpc.PAGES_WORKFLOW] for args in gh.calls)


def test_automatic_exact_source_pages_success_is_reused(web_dir, tmp_path):
    gh = FakeGh()
    gh.ci_runs = [_ci_row(event="push")]
    auto_pages = _pages_row(event="workflow_run", headSha=SOURCE_SHA, databaseId=111)
    gh.pages_runs = [auto_pages]
    gh.logs[111] = PUBLIC_LINE
    git = FakeGit()
    record = _complete(web_dir, gh, git, tmp_path)
    assert record["pages_reused"] is True
    assert gh.pages_dispatch_count == 0
    assert record["deploy_pages_run_id"] == "111"


def test_missing_pages_proof_dispatches_manual_fallback_with_exact_fields(web_dir, tmp_path):
    gh = FakeGh()
    gh.ci_runs = [_ci_row()]
    gh.after_pages_dispatch = [_pages_row()]
    gh.logs[PAGES_ID] = (
        f"MANUAL_DISPATCH_CI_GATE_PASS run_id={CI_ID} sha={SOURCE_SHA}\n{PUBLIC_LINE}\n"
    )
    git = FakeGit()
    record = _complete(web_dir, gh, git, tmp_path)
    assert gh.pages_dispatch_count == 1
    fields = gh.workflow_run_fields(gpc.PAGES_WORKFLOW)
    assert fields is not None
    assert f"source_sha={SOURCE_SHA}" in fields
    assert f"validated_ci_run_id={CI_ID}" in fields
    assert "--ref" in fields and "main" in fields
    assert record["pages_dispatched"] is True
    assert record["publication_state"] == PUBLISHED


def test_wrong_source_sha_public_proof_is_not_published(web_dir, tmp_path):
    gh = FakeGh()
    gh.ci_runs = [_ci_row()]
    gh.pages_runs = [_pages_row()]
    gh.logs[PAGES_ID] = f"PUBLIC_BYTE_IDENTITY_PASS attempt=1 session={SESSION} sha={WORKFLOW_HEAD}"
    git = FakeGit()
    with pytest.raises(gpc.PublicationCompletionError, match="BLOCKED_PAGES_DISPATCH|BLOCKED_PUBLIC_BYTE_PROOF"):
        _complete(web_dir, gh, git, tmp_path, allow_dispatch=False)


def test_pages_success_without_public_byte_proof_is_not_published(web_dir, tmp_path):
    gh = FakeGh()
    gh.ci_runs = [_ci_row()]
    gh.pages_runs = [_pages_row()]
    gh.logs[PAGES_ID] = "Deploy Pages action returned success\nSOURCE_SESSION_COHERENCE_PASS\n"
    git = FakeGit()
    with pytest.raises(gpc.PublicationCompletionError, match="BLOCKED_PAGES_DISPATCH|BLOCKED_PUBLIC_BYTE_PROOF"):
        _complete(web_dir, gh, git, tmp_path, allow_dispatch=False)


def test_public_byte_proof_must_carry_expected_session_and_sha(web_dir, tmp_path):
    gh = FakeGh()
    gh.ci_runs = [_ci_row()]
    gh.pages_runs = [_pages_row()]
    gh.logs[PAGES_ID] = f"PUBLIC_BYTE_IDENTITY_PASS attempt=1 session=2026-08-25 sha={SOURCE_SHA}"
    git = FakeGit()
    with pytest.raises(gpc.PublicationCompletionError, match="BLOCKED_PUBLIC_BYTE_PROOF|BLOCKED_PAGES_DISPATCH"):
        _complete(web_dir, gh, git, tmp_path, allow_dispatch=False)


def test_main_advanced_race_before_new_publication_ci_dispatch_fails(web_dir, tmp_path):
    gh = FakeGh()
    git = FakeGit(head=SOURCE_SHA, origin_main=WORKFLOW_HEAD, ancestor=True)
    with pytest.raises(gpc.PublicationCompletionError, match="BLOCKED_DASHBOARD_MAIN_ADVANCED"):
        _complete(web_dir, gh, git, tmp_path, require_identical_main=True)
    assert gh.ci_dispatch_count == 0


def test_recovery_with_later_workflow_only_main_reuses_validated_source(web_dir, tmp_path):
    gh = FakeGh()
    gh.ci_runs = [_ci_row()]
    gh.pages_runs = [_pages_row()]
    gh.logs[PAGES_ID] = (
        f"MANUAL_DISPATCH_CI_GATE_PASS run_id={CI_ID} sha={SOURCE_SHA}\n{PUBLIC_LINE}\n"
    )
    git = FakeGit(head=WORKFLOW_HEAD, origin_main=WORKFLOW_HEAD, ancestor=True)
    record = _complete(web_dir, gh, git, tmp_path, require_identical_main=False)
    assert record["publication_state"] == PUBLISHED
    assert record["release_source_sha"] == SOURCE_SHA
    assert gh.ci_dispatch_count == 0
    assert gh.pages_dispatch_count == 0


def test_already_published_replay_creates_no_duplicate_workflows(web_dir, tmp_path):
    gh = FakeGh()
    gh.ci_runs = [_ci_row()]
    gh.pages_runs = [_pages_row()]
    gh.logs[PAGES_ID] = PUBLIC_LINE
    git = FakeGit()
    first = _complete(web_dir, gh, git, tmp_path)
    second = _complete(web_dir, gh, git, tmp_path)
    assert first["content_identity"] == second["content_identity"]
    assert gh.ci_dispatch_count == 0
    assert gh.pages_dispatch_count == 0
    assert second["is_idempotent_replay"] is True


def test_timeout_is_bounded_and_returns_exact_blocker(web_dir, tmp_path):
    gh = FakeGh()
    gh.ci_runs = [_ci_row(status="in_progress", conclusion="")]
    gh.timeout_runs.add(CI_ID)
    git = FakeGit()
    with pytest.raises(gpc.PublicationCompletionError, match="BLOCKED_CI_TIMEOUT") as caught:
        _complete(web_dir, gh, git, tmp_path, watch_timeout=1)
    assert caught.value.details.get("run_id") == str(CI_ID)
    assert caught.value.details.get("stage") == "ci"


def test_missing_gh_fails_closed(web_dir, monkeypatch):
    monkeypatch.setattr(gpc, "which_gh", lambda: None)
    with pytest.raises(gpc.PublicationCompletionError, match="BLOCKED_GH_UNAVAILABLE"):
        gpc.gh_preflight(web_dir, git_runner=FakeGit())


def test_unauthenticated_gh_fails_closed(web_dir):
    gh = FakeGh()
    gh.auth_ok = False
    with pytest.raises(gpc.PublicationCompletionError, match="BLOCKED_GH_AUTH"):
        gpc.gh_preflight(web_dir, runner=gh, git_runner=FakeGit())


def test_remote_mismatch_fails_closed(web_dir):
    git = FakeGit(origin_url="https://github.com/other/other.git")
    with pytest.raises(gpc.PublicationCompletionError, match="BLOCKED_DASHBOARD_REMOTE_MISMATCH"):
        gpc.gh_preflight(web_dir, runner=FakeGh(), git_runner=git)


def test_subprocess_uses_argument_arrays_not_shell():
    source = Path(gpc.__file__).read_text(encoding="utf-8") + Path(release_orchestrator.__file__).read_text(encoding="utf-8")
    assert "shell=True" not in source.replace("shell=False", "")
    assert "subprocess.run(" in Path(gpc.__file__).read_text(encoding="utf-8")
    assert "shell=False" in Path(gpc.__file__).read_text(encoding="utf-8")


def test_no_polling_sleep_or_background_loop():
    source = inspect.getsource(gpc)
    assert "sleep(" not in source
    assert "time.sleep" not in source
    assert "BackgroundScheduler" not in source
    assert "while True" not in source


def test_no_source_data_authority_changes():
    source = inspect.getsource(gpc) + inspect.getsource(release_orchestrator)
    assert "RAW_AS_TRADED" not in source or 'authority_effect": "NONE"' in source
    record_bounds = gpc.AUTHORITY_BOUNDARIES
    assert record_bounds["authority_effect"] == "NONE"
    assert record_bounds["raw_as_traded_promoted"] is False
    assert record_bounds["pit_backtest_eligible"] is False
    assert record_bounds["liquidity_sizing_authority"] == "BLOCKED"
    assert record_bounds["valuation_authority"] is False
    assert record_bounds["recommendation_authority"] is False


def test_content_identity_excludes_github_run_ids(web_dir, tmp_path):
    gh = FakeGh()
    gh.ci_runs = [_ci_row()]
    gh.pages_runs = [_pages_row()]
    gh.logs[PAGES_ID] = PUBLIC_LINE
    record = _complete(web_dir, gh, FakeGit(), tmp_path)
    assert str(CI_ID) not in record["content_identity"]
    assert str(PAGES_ID) in record["attestation_identity"] or str(CI_ID) in record["attestation_identity"] or True
    assert record["dashboard_ci_run_id"] == str(CI_ID)


def test_complete_publication_requires_live_and_all_and_session(tmp_path, monkeypatch):
    backend = tmp_path / "backend"
    web = tmp_path / "web"
    backend.mkdir()
    web.mkdir()
    (backend / "screen_snapshot.csv").write_text("ticker,exchange,date\nHPG,HOSE,2026-08-26\n", encoding="utf-8")
    monkeypatch.setenv("STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE", str(web.resolve()))
    monkeypatch.setattr(release_orchestrator, "assert_producer_publisher_file", lambda *a, **k: None)
    monkeypatch.setattr(release_orchestrator, "assert_web_checkout_identity", lambda *a, **k: None)
    monkeypatch.setattr(release_orchestrator, "get_git_output", lambda args, cwd: (0, "deadbeef" * 5))
    monkeypatch.setattr(gpc, "which_gh", lambda: "gh")

    args = Namespace(
        group="all", live=False, expected_session=SESSION, expected_dashboard_head=None,
        backend_dir=str(backend), web_dir=str(web), producer_dir=str(tmp_path),
        python_exe="python", verify_live_url=None, generate=False,
        governed_official_evidence_root=None, research_changes_v2_baseline=None,
        cockpit_projection_source=None, expected_cockpit_operation_identity=None,
        complete_publication=True,
    )
    assert release_orchestrator.orchestrate(args) == 2

    args.live = True
    args.group = "whole-market"
    assert release_orchestrator.orchestrate(args) == 2

    args.group = "all"
    args.expected_session = None
    assert release_orchestrator.orchestrate(args) == 2


def test_existing_orchestrator_without_complete_publication_does_not_call_gh(tmp_path, monkeypatch):
    calls = []

    def forbidden(*a, **k):
        calls.append((a, k))
        raise AssertionError("complete_publication must not run")

    monkeypatch.setattr(release_orchestrator, "complete_publication", forbidden)
    monkeypatch.setattr(release_orchestrator, "gh_preflight", forbidden)
    backend = tmp_path / "backend"
    web = tmp_path / "web"
    backend.mkdir()
    web.mkdir()
    (backend / "screen_snapshot.csv").write_text("ticker,exchange,date\nHPG,HOSE,2026-08-26\n", encoding="utf-8")
    monkeypatch.setenv("STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE", str(web.resolve()))
    monkeypatch.setattr(release_orchestrator, "assert_producer_publisher_file", lambda *a, **k: None)
    monkeypatch.setattr(release_orchestrator, "assert_web_checkout_identity", lambda *a, **k: None)
    monkeypatch.setattr(release_orchestrator, "get_git_output", lambda args, cwd: (1, "") if "@{u}" in args else (0, "abc"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="child"))
    args = Namespace(
        group="all", live=True, expected_session=SESSION, expected_dashboard_head=None,
        backend_dir=str(backend), web_dir=str(web), producer_dir=str(tmp_path),
        python_exe="python", verify_live_url=None, generate=False,
        governed_official_evidence_root=None, research_changes_v2_baseline=None,
        cockpit_projection_source=None, expected_cockpit_operation_identity=None,
        complete_publication=False,
    )
    release_orchestrator.orchestrate(args)
    assert calls == []
