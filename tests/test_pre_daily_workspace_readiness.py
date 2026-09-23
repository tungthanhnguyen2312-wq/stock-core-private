"""PRE_DAILY_WORKSPACE_READINESS_CORRECTIVE_V1.

Defect 1: the zero-flag ``stocklookup.py daily`` (what ``stocklookup.ps1 daily`` runs) built its
``--result-path`` under the Producer checkout's own ``run-logs/``, which
``tools.run_owner_daily.validate_result_path`` deliberately refuses
(RESULT_PATH_INSIDE_PRODUCER_CHECKOUT) -- the production entrypoint refused itself. The earlier
delegation test mocked ``run_owner_daily.main`` away and so never exercised that boundary; the
tests here run the REAL ``main`` + ``validate_result_path`` and stub only ``run_workflow``.

Defect 2: the canonical Dashboard checkout could be a clean-but-stale ancestor of ``origin/main``
when Daily starts (Dashboard source promoted from an isolated worktree); the publisher refuses to
pull, so publication failed only after the whole analytical Daily. Owner Daily now runs the same
shared safe-sync ``preflight_repository`` on the Dashboard before any analytical work. Real,
unmocked git repositories below.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

import stocklookup
from release_checkout_identity import CANONICAL_WEB_ROOT, ReleaseIdentityError, assert_web_checkout_identity
from tools import run_owner_daily as workflow

DASHBOARD_ORIGIN_URL = "https://github.com/tungthanhnguyen2312-wq/market-dashboard.git"


# ----------------------------------------------------------------------------- Defect 1

def _fake_producer(tmp_path: Path) -> Path:
    root = tmp_path / "workspace" / "stock-core-private"
    root.mkdir(parents=True)
    return root


def test_zero_flag_daily_result_path_passes_the_real_validator_and_stays_outside_producer(monkeypatch, tmp_path):
    root = _fake_producer(tmp_path)
    monkeypatch.setattr(stocklookup, "ROOT", root)
    monkeypatch.setattr(workflow, "ROOT", root)  # the real main() validates against workflow.ROOT
    seen: list[dict] = []

    def fake_run_workflow(**kwargs):
        seen.append(kwargs)
        return {"status": "PASS", "session": "2026-09-24", "daily_status": "COMPLETED",
                "ai_handoff": {"publication": {"status": "PUBLISHED_READY_FOR_AI"}},
                "dashboard": {"status": "READY"}, "action_center": {"status": "READY"}}

    monkeypatch.setattr(workflow, "run_workflow", fake_run_workflow)
    code = stocklookup.main(["daily"])  # real run_owner_daily.main + real validate_result_path

    assert code == 0, "the zero-flag production entrypoint must not refuse its own result path"
    assert len(seen) == 1
    results = list((root.parent / "run-logs").glob("stock_lookup_daily_*.result.json"))
    assert len(results) == 1
    result_path = results[0]
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "PASS"
    assert workflow.validate_result_path(result_path, root=root) == result_path.resolve()
    assert not (root / "run-logs").exists(), "nothing may be created under the Producer's own run-logs"
    assert list(root.iterdir()) == [], "the Producer checkout must stay untouched"


def test_the_pre_fix_in_checkout_result_path_is_refused_by_the_real_validator(tmp_path):
    root = _fake_producer(tmp_path)
    old = root / "run-logs" / f"stocklookup_daily_result_{datetime.now():%Y%m%d_%H%M%S}.json"
    with pytest.raises(workflow.OwnerDailyError, match="RESULT_PATH_INSIDE_PRODUCER_CHECKOUT"):
        workflow.validate_result_path(old, root=root)


def test_default_result_path_matches_the_desktop_launcher_root_and_creates_nothing(tmp_path):
    root = _fake_producer(tmp_path)
    path = workflow.default_result_path(root=root, now=datetime(2026, 9, 24, 15, 45, 0))
    assert path == (root.parent / "run-logs" / "stock_lookup_daily_20260924_154500.result.json").resolve()
    assert not path.parent.exists(), "the resolver is pure; run_owner_daily.main creates the directory"
    # Same workspace-level directory and file-name pattern as tools/run_owner_daily.ps1.
    ps1 = (Path(workflow.__file__).parent / "run_owner_daily.ps1").read_text(encoding="utf-8")
    assert r"$logDir = 'C:\Projects\StockLookup\run-logs'" in ps1
    assert '"stock_lookup_daily_$stamp.result.json"' in ps1
    assert workflow.DEFAULT_RESULT_LOG_ROOT == workflow.ROOT.parent / "run-logs"


def test_default_result_path_for_the_real_producer_root_is_outside_the_checkout():
    path = workflow.default_result_path()
    assert path.parent == (workflow.ROOT.parent / "run-logs").resolve()
    assert workflow.ROOT.resolve() not in path.parents


def test_an_in_checkout_log_root_is_never_whitelisted(tmp_path):
    root = _fake_producer(tmp_path)
    with pytest.raises(workflow.OwnerDailyError, match="RESULT_PATH_INSIDE_PRODUCER_CHECKOUT"):
        workflow.default_result_path(root=root, log_root=root / "run-logs")


def test_stocklookup_computes_no_result_path_of_its_own():
    source = Path(stocklookup.__file__).read_text(encoding="utf-8")
    assert 'ROOT / "run-logs"' not in source
    assert "owner_daily.default_result_path(root=ROOT)" in source


# ----------------------------------------------------------------------------- Defect 2

def _git(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def _identity(path: Path) -> None:
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")


def _dashboard_with_origin(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "market-dashboard.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q")
    _identity(seed)
    (seed / "index.html").write_text("v1\n")
    _git(seed, "add", "index.html")
    _git(seed, "commit", "-qm", "seed")
    _git(seed, "branch", "-M", "main")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-qu", "origin", "main")
    web = tmp_path / "market-dashboard"
    subprocess.run(["git", "clone", "-q", str(origin), str(web)], check=True)
    _git(web, "checkout", "-q", "main")
    _identity(web)
    return web, origin


def _advance_origin(tmp_path: Path, origin: Path, name: str) -> str:
    other = tmp_path / f"other-{name}"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    _git(other, "checkout", "-q", "main")
    _identity(other)
    (other / f"{name}.js").write_text(name + "\n")
    _git(other, "add", f"{name}.js")
    _git(other, "commit", "-qm", name)
    _git(other, "push", "-q")
    return _git(other, "rev-parse", "HEAD")


def test_clean_behind_dashboard_is_fast_forwarded(tmp_path):
    web, origin = _dashboard_with_origin(tmp_path)
    remote_head = _advance_origin(tmp_path, origin, "m1")
    result = workflow.preflight_dashboard_repository(web)
    assert result == {"head": remote_head, "status": "FAST_FORWARDED"}
    assert (web / "m1.js").is_file()
    assert _git(web, "rev-parse", "HEAD") == _git(web, "rev-parse", "origin/main")


def test_up_to_date_dashboard_is_a_no_op(tmp_path):
    web, _origin = _dashboard_with_origin(tmp_path)
    before = _git(web, "rev-parse", "HEAD")
    assert workflow.preflight_dashboard_repository(web) == {"head": before, "status": "UP_TO_DATE"}
    assert _git(web, "rev-parse", "HEAD") == before


@pytest.mark.parametrize("dirt", ["tracked", "untracked"])
def test_dirty_dashboard_is_refused_and_nothing_is_discarded(tmp_path, dirt):
    web, origin = _dashboard_with_origin(tmp_path)
    _advance_origin(tmp_path, origin, "m1")
    target = web / ("index.html" if dirt == "tracked" else "scratch.js")
    target.write_text("owner work\n")
    with pytest.raises(workflow.OwnerDailyError,
                       match="UNEXPECTED_TRACKED_CHANGES" if dirt == "tracked" else "UNSAFE_UNTRACKED_CHECKOUT"):
        workflow.preflight_dashboard_repository(web)
    assert target.read_text() == "owner work\n"
    assert not (web / "m1.js").exists(), "a dirty checkout is never fast-forwarded"


def test_ahead_dashboard_is_refused(tmp_path):
    web, _origin = _dashboard_with_origin(tmp_path)
    (web / "local.js").write_text("local\n")
    _git(web, "add", "local.js")
    _git(web, "commit", "-qm", "local only")
    local = _git(web, "rev-parse", "HEAD")
    with pytest.raises(workflow.OwnerDailyError, match="UNSAFE_GIT_DIVERGENCE"):
        workflow.preflight_dashboard_repository(web)
    assert _git(web, "rev-parse", "HEAD") == local


def test_diverged_dashboard_is_refused(tmp_path):
    web, origin = _dashboard_with_origin(tmp_path)
    _advance_origin(tmp_path, origin, "remote")
    (web / "local.js").write_text("local\n")
    _git(web, "add", "local.js")
    _git(web, "commit", "-qm", "local only")
    local = _git(web, "rev-parse", "HEAD")
    with pytest.raises(workflow.OwnerDailyError, match="UNSAFE_GIT_DIVERGENCE"):
        workflow.preflight_dashboard_repository(web)
    assert _git(web, "rev-parse", "HEAD") == local, "never reset/rebase"


def test_non_main_or_wrong_checkout_is_refused(tmp_path):
    web, _origin = _dashboard_with_origin(tmp_path)
    _git(web, "checkout", "-qb", "feature")
    with pytest.raises(workflow.OwnerDailyError, match="BRANCH_IS_NOT_MAIN"):
        workflow.preflight_dashboard_repository(web)
    with pytest.raises(workflow.OwnerDailyError, match="WRONG_REPOSITORY"):
        workflow.preflight_dashboard_repository(tmp_path / "seed")


def test_remote_advance_after_preflight_is_still_caught_by_the_publisher_guard(tmp_path):
    web, origin = _dashboard_with_origin(tmp_path)
    assert workflow.preflight_dashboard_repository(web)["status"] == "UP_TO_DATE"
    head = _git(web, "rev-parse", "HEAD")
    advanced = _advance_origin(tmp_path, origin, "race")  # lands after the preflight
    _git(web, "fetch", "-q", "origin")
    origin_main = _git(web, "rev-parse", "origin/main")
    assert origin_main == advanced != head
    # The publisher's own unchanged live guard (publish_dashboard.git_preflight ->
    # assert_web_checkout_identity(live=True)) on the canonical checkout refuses the stale HEAD.
    with pytest.raises(ReleaseIdentityError, match=r"HEAD .* != origin/main"):
        assert_web_checkout_identity(CANONICAL_WEB_ROOT, origin_url=DASHBOARD_ORIGIN_URL, branch="main",
                                     head=head, origin_main=origin_main, live=True)


def _fresh_run_stubs(monkeypatch, order: list[str]) -> None:
    real_preflight = workflow.preflight_repository

    def preflight(root, *, expected_name, expected_remote_fragment, **kwargs):
        if expected_name == "stock-core-private":
            order.append("producer_preflight")
            return {"head": "producer", "status": "UP_TO_DATE"}
        if expected_name == "ai-core-private":  # covered by test_consumer_preflight_*
            order.append("consumer_preflight")
            return {"head": "consumer", "status": "UP_TO_DATE"}
        order.append("dashboard_preflight")
        return real_preflight(root, expected_name=expected_name,
                              expected_remote_fragment=expected_remote_fragment, **kwargs)

    monkeypatch.setattr(workflow, "preflight_repository", preflight)
    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: "2026-09-24")
    monkeypatch.setattr(workflow, "_auto_resumable_session", lambda *a, **k: None)

    def run_daily(*_a, **_k):
        order.append("daily")
        raise RuntimeError("STOP_AFTER_ORDERING_PROOF")

    monkeypatch.setattr(workflow, "_run_daily", run_daily)


def test_dirty_dashboard_blocks_owner_daily_before_any_analytical_work(monkeypatch, tmp_path):
    web, _origin = _dashboard_with_origin(tmp_path)
    (web / "index.html").write_text("owner work\n")
    producer = tmp_path / "producer"
    producer.mkdir()
    order: list[str] = []
    _fresh_run_stubs(monkeypatch, order)
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_TRACKED_CHANGES"):
        workflow.run_workflow(root=producer, runtime_root=tmp_path / "runtime",
                              handoff_repo=tmp_path / "handoff", dashboard_web_dir=web)
    assert order == ["producer_preflight", "consumer_preflight", "dashboard_preflight"], "Daily must never start"


def test_stale_clean_dashboard_is_fast_forwarded_before_daily_starts(monkeypatch, tmp_path):
    web, origin = _dashboard_with_origin(tmp_path)
    remote_head = _advance_origin(tmp_path, origin, "m1")
    producer = tmp_path / "producer"
    producer.mkdir()
    order: list[str] = []
    _fresh_run_stubs(monkeypatch, order)
    with pytest.raises(RuntimeError, match="STOP_AFTER_ORDERING_PROOF"):
        workflow.run_workflow(root=producer, runtime_root=tmp_path / "runtime",
                              handoff_repo=tmp_path / "handoff", dashboard_web_dir=web)
    assert order == ["producer_preflight", "consumer_preflight", "dashboard_preflight", "daily"]
    assert _git(web, "rev-parse", "HEAD") == remote_head


def test_no_publish_dashboard_skips_the_dashboard_preflight(monkeypatch, tmp_path):
    producer = tmp_path / "producer"
    producer.mkdir()
    order: list[str] = []
    _fresh_run_stubs(monkeypatch, order)
    with pytest.raises(RuntimeError, match="STOP_AFTER_ORDERING_PROOF"):
        workflow.run_workflow(root=producer, runtime_root=tmp_path / "runtime",
                              handoff_repo=tmp_path / "handoff", dashboard_web_dir=tmp_path / "absent",
                              publish_dashboard=False)
    assert order == ["producer_preflight", "consumer_preflight", "daily"]


def test_dashboard_preflight_reuses_the_single_safe_sync_engine():
    import inspect
    source = inspect.getsource(workflow.preflight_dashboard_repository)
    assert "preflight_repository(" in source
    for forbidden in ("reset", "rebase", "stash", "clean", "subprocess"):
        assert forbidden not in source.split('"""')[-1], forbidden
