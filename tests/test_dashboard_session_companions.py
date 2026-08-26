"""Public session companions for Dashboard publication. Temp fixtures only."""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import canonical_dashboard_runtime_release as runtime_release
import canonical_trusted_subset_release as trusted
import dashboard_session_companions as companions
import publish_dashboard as pd
import release_orchestrator
from export_ai_bundle import DEFAULT_TICKERS
from trusted_subset_contract import verify_trusted_subset

SESSION = "2026-08-26"
DASHBOARD = ROOT.parent / "market-dashboard"
CONSUMER = ROOT.parent / "ai-core-private"
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "session-companion-tests",
    "GIT_AUTHOR_EMAIL": "session-companion-tests@example.invalid",
    "GIT_COMMITTER_NAME": "session-companion-tests",
    "GIT_COMMITTER_EMAIL": "session-companion-tests@example.invalid",
}
OPERATION = "daily_research_session_operation:1883a16b50f0ef2d8e367391811ad164c1742532b7d4ae3c72fe6e3c218c30e0"
RUN = "daily_producer_run:9f8dcbb36d9428ff772d94a3dec85d96d0a573e39d5905b433c7ba28ffb856b0"
PACKET = "current_research_decision_packet:ed1bfde1a066f7f311fdeec67ccc200b98f05286152560b79563423c0919d176"
COHORT = "prospective_research_cohort_snapshot:6b98b3925a2bb836cde294b85e61a2bb514b6ff6992d29126b911a7cfdfa877c"
PRODUCER_COMMIT = "dc82bade484a9f205025fc0d18089aefab89d630"
PRODUCER_SUMMARY = "Canonical trusted-subset financial-evidence bridge"
BUILD_ID = "2026-08-26-dc82bad-testhash01"

BANNED_IMPORTS = (
    "import urllib", "import requests", "import httpx", "import aiohttp",
    "import dnse_access", "import dnse_market_data",
)


def _plan(**overrides):
    kwargs = {
        "producer_commit": PRODUCER_COMMIT,
        "producer_commit_summary": PRODUCER_SUMMARY,
        "build_id": BUILD_ID,
    }
    kwargs.update(overrides)
    return companions.compute_session_companions(ROOT, SESSION, **kwargs)


def test_computation_is_deterministic():
    first = _plan()
    second = _plan()
    assert first.manifest_text == second.manifest_text
    assert first.report_html == second.report_html
    assert first.manifest_bytes == second.manifest_bytes
    assert first.relpaths == (
        "data/session_2026_08_26_manifest.json",
        "report-2026-08-26.html",
    )


def test_manifest_session_and_lineage():
    plan = _plan()
    manifest = plan.manifest
    assert manifest["dashboard_session"] == SESSION
    status = manifest["canonical_producer_status"]
    assert status["status"] == "COMPLETED"
    assert status["operation_identity"] == OPERATION
    assert status["run_identity"] == RUN
    assert status["registration_state"] == "COMPLETED_RETAINED_EVIDENCE"
    assert status["technical_coverage"] == 887
    assert status["observed_session_cohort"] == 889
    assert status["active_equity_universe"] == 1506
    assert manifest["current_research_packet_identity"] == PACKET
    assert manifest["prospective_cohort_identity"] == COHORT
    assert manifest["source_artifacts"]["daily_producer_run_manifest"]["run_identity"] == RUN
    assert manifest["market_summary"]["advancing"] == 378
    assert manifest["market_summary"]["declining"] == 289
    assert manifest["market_summary"]["unchanged"] == 220


def test_report_contains_2026_08_26_facts_not_prior_session():
    plan = _plan()
    html = plan.report_html
    assert SESSION in html
    assert "26/08/2026" in html
    assert "378" in html and "289" in html and "220" in html
    assert "25/08/2026" not in html
    assert "246 tăng" not in html
    assert "437 giảm" not in html
    assert "95 Entry-Relevant" not in html
    assert "95 cơ hội" not in html
    assert "NOT_PROMOTED" in html
    assert "NOT_EMITTED" in html
    assert "BLOCKED" in html
    assert "No price targets or expected returns." in html
    assert f"dashboard.html?v={BUILD_ID}" in html
    assert "STRICT_VALUATION" in html


def test_unsupported_claims_remain_explicitly_unavailable():
    bounds = _plan().manifest["governed_boundaries"]
    assert bounds["strict_valuation"] == "BLOCKED"
    assert bounds["pit_raw_as_traded"] == "NOT_PROMOTED"
    assert bounds["calibrated_targets_probabilities"] == "NOT_EMITTED"
    assert bounds["liquidity_sizing_execution"] == "BLOCKED_NO_SIZING_EXECUTION_AUTHORITY"
    assert "STRICT_VALUATION" in bounds["blocked_dimensions"]
    assert "NO_LIQUIDITY_SIZING_EXECUTION_AUTHORITY" in bounds["blocked_dimensions"]


def test_omitted_when_handoff_absent(tmp_path):
    plan = companions.compute_session_companions(
        tmp_path, "2026-07-17",
        producer_commit="x", producer_commit_summary="y", build_id="z",
    )
    assert plan.omitted
    assert plan.omit_reason == "NO_RETAINED_CANONICAL_HANDOFF"
    assert companions.apply_session_companions(tmp_path, plan) == []


def test_no_network_or_dnse_acquisition():
    source = (ROOT / "dashboard_session_companions.py").read_text(encoding="utf-8")
    for banned in BANNED_IMPORTS:
        assert banned not in source


class _FakeGit:
    def __init__(self, root: Path, branch: str = "main"):
        self.root = root
        self.branch = branch
        self.calls: list[tuple[str, ...]] = []
        self.status_output = " M dashboard.html\n"

    def __call__(self, *args: str, timeout: int = 180):
        self.calls.append(args)
        if args == ("rev-parse", "--show-toplevel"):
            return True, str(self.root)
        if args == ("branch", "--show-current"):
            return True, self.branch
        if args == ("remote", "get-url", "origin"):
            return True, "https://example.invalid/repo.git"
        if args == ("diff", "--name-only", "--diff-filter=U"):
            return True, ""
        if args == ("rev-parse", "HEAD"):
            return True, "0" * 40
        if args[:2] == ("show", "-s"):
            return True, "2026-08-26T00:00:00+07:00"
        if args == ("fetch", "origin", self.branch):
            return True, ""
        if args == ("rev-parse", f"origin/{self.branch}"):
            return True, "0" * 40
        if args and args[0] == "rev-list":
            return True, "0\t0"
        if args[:3] == ("diff", "--check", "--"):
            return True, ""
        if args[:2] == ("status", "--porcelain"):
            return True, self.status_output
        raise AssertionError(f"Unexpected git() call: {args!r}")


def _write_session_web(root: Path, session: str = SESSION) -> None:
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "js").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "css").mkdir(parents=True, exist_ok=True)
    (root / "screen_snapshot.csv").write_text(
        f"ticker,exchange,date\nHPG,HSX,{session}\n", encoding="utf-8",
    )
    (root / "market_breadth.csv").write_text(
        f"group,date,n_up,n_down,n_flat\nALL,{session},378,289,220\n", encoding="utf-8",
    )
    (root / "analysis_bundle.json").write_text(
        json.dumps({"reference_session_date": session, "is_actionable": False}),
        encoding="utf-8",
    )
    (root / "analysis_latest.json").write_text(
        json.dumps({"summary": {"session_date": session, "generated_at": f"{session} 16:00"}}),
        encoding="utf-8",
    )
    for name in ("app.js", "style.css", "assets/js/value-format.js",
                 "assets/js/company-panel.js", "assets/css/tailwind.generated.css"):
        (root / name).write_text("/* fixture */\n", encoding="utf-8")
    for relative in sorted(pd.SAFE_WEB_ARTIFACTS):
        path = root / relative
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n" if relative.endswith(".json") else "/* fixture */\n", encoding="utf-8")
    (root / "dashboard.html").write_text(
        '<html><head><link href="style.css"><script src="app.js"></script></head><body></body></html>\n',
        encoding="utf-8",
    )
    (root / "screener.html").write_text("<html></html>\n", encoding="utf-8")
    (root / "analysis.html").write_text("<html></html>\n", encoding="utf-8")


@pytest.fixture
def publish_sandbox(tmp_path, monkeypatch):
    web = tmp_path / "web"
    backend = tmp_path / "backend"
    web.mkdir()
    backend.mkdir()
    _write_session_web(web)
    _write_session_web(backend)
    monkeypatch.setattr(pd, "WEB_ROOT", web)
    monkeypatch.setattr(pd, "BACKEND_ROOT", backend)
    monkeypatch.setattr(pd, "LIVE_MODE", False)
    monkeypatch.setenv("STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE", str(web.resolve()))
    fake = _FakeGit(web)
    monkeypatch.setattr(pd, "git", fake)
    return web, backend, fake


def test_dry_run_plans_both_paths_zero_mutation(publish_sandbox, monkeypatch):
    web, _backend, _fake = publish_sandbox
    before = {p: p.read_bytes() for p in web.rglob("*") if p.is_file()}
    buf = io.StringIO()
    monkeypatch.setattr(sys, "argv", ["publish_dashboard.py"])
    with mock.patch("sys.stdout", buf):
        rc = pd.main()
    assert rc == 0
    after = {p: p.read_bytes() for p in web.rglob("*") if p.is_file()}
    assert before == after
    out = buf.getvalue()
    assert "data/session_2026_08_26_manifest.json" in out
    assert "report-2026-08-26.html" in out
    assert "zero mutation" in out
    assert not (web / "data" / "session_2026_08_26_manifest.json").exists()
    assert not (web / "report-2026-08-26.html").exists()


def test_live_writes_companions_before_release_smoke(publish_sandbox, monkeypatch):
    web, _backend, _fake = publish_sandbox
    seen: list[str] = []

    def spy_smoke():
        seen.append("smoke")
        manifest = web / "data" / "session_2026_08_26_manifest.json"
        report = web / "report-2026-08-26.html"
        assert manifest.is_file() and manifest.stat().st_size > 0
        assert report.is_file() and report.stat().st_size > 0
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        assert payload["dashboard_session"] == SESSION
        return 0

    captured: dict[str, list[str]] = {}

    def spy_publish(whitelist, branch, **kwargs):
        captured["whitelist"] = list(whitelist)
        return 0

    monkeypatch.setattr(pd, "run_release_smoke_tests", spy_smoke)
    monkeypatch.setattr(pd, "publish_live", spy_publish)
    monkeypatch.setattr(sys, "argv", ["publish_dashboard.py", "--live"])
    rc = pd.main()
    assert rc == 0
    assert seen == ["smoke"]
    whitelist = captured["whitelist"]
    assert "data/session_2026_08_26_manifest.json" in whitelist
    assert "report-2026-08-26.html" in whitelist
    assert "report-2099-01-01.html" not in whitelist


def test_whitelist_is_exact_dynamic_paths_not_a_glob():
    plan = _plan()
    extended = companions.extend_whitelist(
        ["dashboard.html", "data/build_info.json"],
        plan, web_root=Path("."), require_exist=False,
    )
    assert "data/session_2026_08_26_manifest.json" in extended
    assert "report-2026-08-26.html" in extended
    assert "data/session_2026_08_25_manifest.json" not in extended
    assert "report-2026-08-25.html" not in extended


def test_managed_path_rollback_removes_new_restores_prior_preserves_unrelated(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    env = os.environ.copy()
    env.update(GIT_IDENTITY)
    subprocess.run(["git", "init", "-q"], cwd=web, env=env, check=True)
    (web / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=web, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=web, env=env, check=True)
    manifest_rel, report_rel = companions.companion_relpaths(SESSION)
    prior = web / manifest_rel
    prior.parent.mkdir(parents=True, exist_ok=True)
    prior.write_bytes(b'{"dashboard_session":"preexisting"}\n')
    snapshot = release_orchestrator.capture_dashboard_transaction(
        web, managed_relpaths=companions.companion_relpaths(SESSION),
    )
    prior.write_bytes(b'{"dashboard_session":"mutated"}\n')
    (web / report_rel).write_text("newly-created-report\n", encoding="utf-8")
    unrelated = web / "operator_untracked.txt"
    unrelated.write_text("keep-me\n", encoding="utf-8")
    ignored_tool = web / "tools" / "tailwind" / "tailwindcss.exe"
    ignored_tool.parent.mkdir(parents=True, exist_ok=True)
    ignored_tool.write_bytes(b"operator-local-tool")
    source = Path(release_orchestrator.__file__).read_text(encoding="utf-8")
    assert '["git", "clean"' not in source
    assert '"reset", "--hard"' not in source
    release_orchestrator.restore_dashboard_transaction(web, snapshot)
    assert prior.read_bytes() == b'{"dashboard_session":"preexisting"}\n'
    assert not (web / report_rel).exists()
    assert unrelated.read_text(encoding="utf-8") == "keep-me\n"
    assert ignored_tool.read_bytes() == b"operator-local-tool"


def _copy_parquet(dest: Path, ticker: str) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for source_root in (ROOT / "data_bctc", ROOT.parent / "dashboard-runtime" / "data_bctc"):
        path = source_root / f"{ticker}_balance_sheet_quarter.parquet"
        if path.is_file():
            shutil.copy2(path, dest / path.name)
            return
    raise AssertionError(f"missing parquet for {ticker}")


def _copy_dashboard_smoke_tree(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        DASHBOARD,
        dest,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".pytest_cache"),
    )


def _git_init_with_local_origin(web: Path) -> Path:
    env = os.environ.copy()
    env.update(GIT_IDENTITY)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=web, env=env, check=True)
    subprocess.run(["git", "add", "-A"], cwd=web, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture dashboard"], cwd=web, env=env, check=True)
    remote = web.parent / "remote.git"
    subprocess.run(["git", "clone", "--bare", "-q", str(web), str(remote)], env=env, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=web, env=env, check=True)
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=web, env=env, check=True)
    subprocess.run(["git", "branch", "-u", "origin/main"], cwd=web, env=env, check=True)
    return remote


def test_release_smoke_and_temp_end_to_end(tmp_path):
    lock = Path(tempfile.gettempdir()) / "stock_lookup_release_orchestrator.lock"
    if lock.exists():
        lock.unlink()
    runtime = tmp_path / "runtime"
    runtime_release.materialize_canonical_runtime_release(ROOT, runtime, SESSION)
    parquet_dir = runtime / "data_bctc"
    for ticker in DEFAULT_TICKERS:
        _copy_parquet(parquet_dir, ticker)
    trusted.materialize_canonical_trusted_subset(
        ROOT, runtime, SESSION, consumer_root=CONSUMER, tickers=list(DEFAULT_TICKERS),
    )
    trusted_report = verify_trusted_subset(runtime)
    assert trusted_report.ready

    sys.path.insert(0, str(CONSUMER))
    from builders.build_ticker_context import verify_exact_session_bundle
    bundle_path = runtime / "analysis_bundle.json"
    ok, reason = verify_exact_session_bundle(
        bundle_path,
        json.loads(bundle_path.read_text(encoding="utf-8")),
        json.loads((runtime / "bundle_manifest.json").read_text(encoding="utf-8")),
    )
    assert ok, reason

    web = tmp_path / "web"
    _write_session_web(web)
    _copy_dashboard_smoke_tree(web)
    for name in ("analysis_bundle.json", "bundle_manifest.json", "focus_extract.json",
                 "statement_taxonomy_sidecar.json", "analysis_latest.json",
                 "screen_snapshot.csv", "market_breadth.csv"):
        shutil.copy2(runtime / name, web / name)

    plan = companions.compute_session_companions(
        ROOT, SESSION,
        producer_commit=PRODUCER_COMMIT,
        producer_commit_summary=PRODUCER_SUMMARY,
        build_id=BUILD_ID,
    )
    companions.apply_session_companions(web, plan)
    (web / "data" / "build_info.json").write_text(
        json.dumps({"market_session": SESSION, "build_id": BUILD_ID}, indent=2) + "\n",
        encoding="utf-8",
    )
    smoke = subprocess.run(
        ["node", "--test", str(web / "tests" / "release-smoke.test.js")],
        cwd=web, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    smoke_out = (smoke.stdout or "") + (smoke.stderr or "")
    assert smoke.returncode == 0, smoke_out
    assert "checked-out source session is coherent for public verification" in smoke_out

    whitelist = companions.extend_whitelist(
        ["dashboard.html", "data/build_info.json"], plan, web_root=web, require_exist=True,
    )
    assert plan.manifest_relpath in whitelist
    assert plan.report_relpath in whitelist
    deploy = (web / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")
    assert "session_${EXPECTED_SESSION//-/_}_manifest.json" in deploy
    assert "report-${EXPECTED_SESSION}.html" in deploy
    assert (web / plan.manifest_relpath).is_file()
    assert (web / plan.report_relpath).is_file()

    _git_init_with_local_origin(web)
    env = os.environ.copy()
    env.update(GIT_IDENTITY)
    env["STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE"] = str(web.resolve())
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        sys.executable, str(ROOT / "tools" / "release_orchestrator.py"), "all", "--live",
        "--backend-dir", str(runtime),
        "--web-dir", str(web),
        "--producer-dir", str(ROOT),
        "--expected-session", SESSION,
    ]
    result = subprocess.run(
        cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    combined = (result.stdout or "") + (result.stderr or "")
    assert "github.com/tungthanhnguyen2312-wq/market-dashboard" not in combined
    assert result.returncode == 0, combined
    assert (web / "data" / "session_2026_08_26_manifest.json").is_file()
    assert (web / "report-2026-08-26.html").is_file()
    post = verify_trusted_subset(web)
    assert post.ready
    assert not (DASHBOARD / "data" / "session_2026_08_26_manifest.json").exists()
    assert not (DASHBOARD / "report-2026-08-26.html").exists()
