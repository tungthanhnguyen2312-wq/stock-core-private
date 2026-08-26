"""Dedicated test suite for release_orchestrator.py.

Every test runs against isolated temp fixtures (a minimal --backend-dir with its own
screen_snapshot.csv, and a freshly `git init`ed --web-dir), never the real dashboard-runtime
or worktrees/market-dashboard-main. A live runtime's session date moves daily; a test that
depends on it (as this file previously did — a hardcoded "2026-08-04" against the real
dashboard-runtime) goes stale within days for reasons unrelated to any code change. See
operations-review/PROJECT_STATE.md's note on this for the incident that this fixture
isolation replaces.
"""

import csv
import json
import os
import sys
import tempfile
import unittest
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = ROOT / "tools" / "release_orchestrator.py"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import release_orchestrator  # noqa: E402
from qualified_research_snapshot_v2 import from_served_bundle  # noqa: E402

FIXTURE_SESSION = "2026-08-04"
GIT_IDENTITY_ENV = {
    "GIT_AUTHOR_NAME": "release-orchestrator-tests",
    "GIT_AUTHOR_EMAIL": "release-orchestrator-tests@example.invalid",
    "GIT_COMMITTER_NAME": "release-orchestrator-tests",
    "GIT_COMMITTER_EMAIL": "release-orchestrator-tests@example.invalid",
}


class ReleaseOrchestratorUnitTests(unittest.TestCase):
    """Every test gets its own --backend-dir/--web-dir fixture pair; see setUp."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.backend_dir = self._make_backend_dir(base / "backend", FIXTURE_SESSION)
        self.web_dir = self._make_web_dir(base / "web")

    @staticmethod
    def _make_backend_dir(path: Path, session: str) -> Path:
        """A --backend-dir with just enough to satisfy the orchestrator's own session read.

        Deliberately missing everything tools/operate_stocklookup.py needs (vn_stock.db,
        data_bctc/, ...): tests that exercise --generate want that child to fail fast and
        deterministically, without a real database or a real daily-chain run.
        """
        path.mkdir(parents=True, exist_ok=True)
        with (path / "screen_snapshot.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["ticker", "exchange", "date"])
            writer.writerow(["HPG", "HOSE", session])
            writer.writerow(["DELISTEDCO", "DELISTED", "2020-01-01"])
        return path

    @staticmethod
    def _make_web_dir(path: Path) -> Path:
        """A real, minimal git repo standing in for the served Dashboard checkout.

        No remote/upstream is configured, so the orchestrator's upstream-divergence check
        (guarded on `rev-parse @{u}` succeeding) is naturally a no-op here, same as it would
        be for any git operation not touching that check's own contract.
        """
        path.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update(GIT_IDENTITY_ENV)
        subprocess.run(["git", "init", "-q"], cwd=path, env=env, check=True)
        (path / "README.md").write_text("release_orchestrator test fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=path, env=env, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fixture init"], cwd=path, env=env, check=True)
        return path

    def run_orchestrator_proc(self, args: list[str], cwd=None, extra_env=None):
        cmd = [sys.executable, str(ORCHESTRATOR)] + args
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            cmd,
            cwd=cwd or ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=False,
        )

    def run_fixture(self, group_and_flags: list[str], **overrides) -> subprocess.CompletedProcess:
        """Run against this test's own fixture dirs, with `--expected-session` set correctly
        unless the test is specifically about a session mismatch."""
        args = list(group_and_flags)
        web_dir = overrides.get("web_dir", self.web_dir)
        args += ["--backend-dir", str(overrides.get("backend_dir", self.backend_dir))]
        args += ["--web-dir", str(web_dir)]
        if "expected_session" not in overrides or overrides["expected_session"] is not None:
            args += ["--expected-session", overrides.get("expected_session", FIXTURE_SESSION)]
        extra_env = {"STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE": str(Path(web_dir).resolve())}
        extra_env.update(overrides.get("extra_env") or {})
        return self.run_orchestrator_proc(args, extra_env=extra_env)

    @staticmethod
    def _executed(res: subprocess.CompletedProcess, needle: str) -> bool:
        """Whether `needle` appears in an actually-executed child process line (not just in
        the pre-execution 'Execution Plans:' preview, which lists every planned command
        whether or not it later runs)."""
        return any(line.startswith("[INFO] Executing child process:") and needle in line
                   for line in res.stdout.splitlines())

    # ------------------------------------------------------------------ basic invocation
    def test_missing_subcommand_fails(self):
        res = self.run_orchestrator_proc([])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Missing release group subcommand", res.stderr)

    def test_unknown_argument_fails(self):
        res = self.run_orchestrator_proc(["--unknown-arg"])
        self.assertNotEqual(res.returncode, 0)

    def test_wrong_expected_session_fails(self):
        res = self.run_fixture(["whole-market"], expected_session="2099-01-01")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Session mismatch", res.stderr)

    def test_wrong_expected_dashboard_head_fails(self):
        res = self.run_fixture(
            ["whole-market", "--expected-dashboard-head",
             "0000000000000000000000000000000000000000"])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Dashboard HEAD mismatch", res.stderr)

    def test_canonical_whole_market_plan_isolation(self):
        # Not asserting a clean exit: build_frontend.py needs a real Tailwind CLI + asset tree
        # under --web-dir, and publish_dashboard.py needs a fuller backend artifact set than
        # this suite fixtures — both are environment/content dependencies of those two scripts,
        # not of the orchestrator's own plan construction, which is everything this test
        # actually checks (and which is printed before either child process runs).
        res = self.run_fixture(["whole-market"])
        self.assertIn("SELECTED_GROUP        : whole-market", res.stdout)
        self.assertIn("TRUSTED_AI_INVOKED    : false", res.stdout)
        self.assertIn("GENERATE_INVOKED      : false", res.stdout)
        self.assertNotIn("publish_release.py", res.stdout)
        self.assertNotIn(".bat", res.stdout)
        self.assertNotIn("cmd.exe", res.stdout)
        # The full producer-rooted path must be used for both whole-market plans — not a bare
        # name, and not a copy living under --web-dir (the historical release-chain-break
        # defect this isolation guards against). build_frontend.py's path is checked against
        # its actually-executed line (plain string); publish_dashboard.py (Plan 2) never gets
        # that far once Plan 1 fails on this fixture's missing Tailwind CLI, so it is checked
        # against the pre-execution plan preview instead — printed as a Python list repr,
        # hence the doubled backslashes on Windows.
        self.assertIn(str(ROOT / "tools" / "build_frontend.py"), res.stdout)
        self.assertIn(repr(str(ROOT / "publish_dashboard.py")), res.stdout)
        self.assertNotIn(repr(str(self.web_dir / "publish_dashboard.py")), res.stdout)

    def test_single_instance_lock(self):
        lock_file = Path(tempfile.gettempdir()) / "stock_lookup_release_orchestrator.lock"
        if lock_file.exists():
            try:
                lock_file.unlink()
            except Exception:
                pass
        lock_file.write_text("99999", encoding="utf-8")
        try:
            res = self.run_fixture(["whole-market"])
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("Lock file exists", res.stderr)
        finally:
            if lock_file.exists():
                try:
                    lock_file.unlink()
                except Exception:
                    pass

    # ------------------------------------------------------------------ --generate composition
    def test_generate_is_a_noop_for_whole_market_only(self):
        res = self.run_fixture(["whole-market", "--generate"])
        self.assertIn("GENERATE_INVOKED      : false", res.stdout)
        self.assertNotIn("operate_stocklookup.py", res.stdout)

    def test_generate_runs_before_trusted_ai_plan_and_its_failure_stops_publish(self):
        """The fixture backend dir has no upstream artifacts, so the generate stage (running
        for real, as a subprocess — this suite has no dependency-injection seam) fails its own
        preflight immediately, before writing anything. Composition contract under test:
        publish_release.py must never be reached after that failure."""
        res = self.run_fixture(["trusted-ai", "--generate"])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("GENERATE_INVOKED      : true", res.stdout)
        # Planned (both commands are always printed up front)...
        self.assertIn("operate_stocklookup.py", res.stdout)
        self.assertIn("publish_release.py", res.stdout)
        # ...but only the generate stage actually ran.
        self.assertTrue(self._executed(res, "operate_stocklookup.py"),
                        f"expected operate_stocklookup.py to have been executed\n{res.stdout}")
        self.assertFalse(self._executed(res, "publish_release.py"),
                         f"publish_release.py must not run after a failed generate stage\n{res.stdout}")
        self.assertIn("required upstream artifact(s) absent", res.stdout)

    def test_generate_passes_execute_only_in_live_mode(self):
        """--generate's child gets --execute only when the orchestrator itself is --live —
        dry-run orchestration must not let a 'preview' invocation quietly write real files."""
        dry = self.run_fixture(["trusted-ai", "--generate"])
        live = self.run_fixture(["trusted-ai", "--generate", "--live"])
        dry_plan = next(l for l in dry.stdout.splitlines() if l.strip().startswith("Plan 1:"))
        live_plan = next(l for l in live.stdout.splitlines() if l.strip().startswith("Plan 1:"))
        self.assertIn("operate_stocklookup.py", dry_plan)
        self.assertIn("operate_stocklookup.py", live_plan)
        self.assertNotIn("--execute", dry_plan)
        self.assertIn("--execute", live_plan)
        # Neither ever asks the generate stage to publish: that stays this script's own job.
        self.assertNotIn("--publish", dry_plan)
        self.assertNotIn("--publish", live_plan)
        self.assertNotIn("--live", dry_plan)
        self.assertNotIn("--live", live_plan)

    def test_verify_live_url_only_reaches_publish_release_when_live(self):
        """operate_stocklookup.py's own --live path used to thread --verify-live-url straight
        to publish_release.py; retiring that path must not silently drop the ability to do a
        live re-fetch-and-compare check, so release_orchestrator.py carries it now instead."""
        url = "https://example.invalid/market-dashboard"
        live = self.run_fixture(["trusted-ai", "--live", "--verify-live-url", url])
        dry = self.run_fixture(["trusted-ai", "--verify-live-url", url])
        live_plan = next(l for l in live.stdout.splitlines() if l.strip().startswith("Plan 1:"))
        dry_plan = next(l for l in dry.stdout.splitlines() if l.strip().startswith("Plan 1:"))
        self.assertIn("publish_release.py", live_plan)
        self.assertIn("publish_release.py", dry_plan)
        self.assertIn(url, live_plan)
        self.assertNotIn(url, dry_plan)

    def test_generate_plan_always_includes_dnse_foreign_flow_for_trusted_ai(self):
        """The authoritative production release profile opts DNSE foreign-flow value in
        unconditionally whenever it generates the trusted-ai artifact set -- no separate
        orchestrator-level flag is needed to turn it on for a real release. The lower-level
        builder keeps its own independent, explicit, default-off flag (see
        test_operate_stocklookup.py's forwarding tests)."""
        dry = self.run_fixture(["trusted-ai", "--generate"])
        dry_plan = next(l for l in dry.stdout.splitlines() if l.strip().startswith("Plan 1:"))
        self.assertIn("--include-dnse-foreign-flow", dry_plan)
        live = self.run_fixture(["trusted-ai", "--generate", "--live"])
        live_plan = next(l for l in live.stdout.splitlines() if l.strip().startswith("Plan 1:"))
        self.assertIn("--include-dnse-foreign-flow", live_plan)

    def test_generate_plan_includes_dnse_foreign_flow_for_all_group_too(self):
        res = self.run_fixture(["all", "--generate"])
        plan = next(l for l in res.stdout.splitlines() if l.strip().startswith("Plan 1:"))
        self.assertIn("--include-dnse-foreign-flow", plan)

    def test_all_group_generate_dry_run_excludes_execute_but_includes_dnse_flag(self):
        """The --execute fix and the DNSE opt-in are independent gates on the same
        cmd_generate list -- both must hold for the 'all' group exactly as they do for
        'trusted-ai' alone (same code path, no group-specific special case)."""
        dry = self.run_fixture(["all", "--generate"])
        live = self.run_fixture(["all", "--generate", "--live"])
        dry_plan = next(l for l in dry.stdout.splitlines() if l.strip().startswith("Plan 1:"))
        live_plan = next(l for l in live.stdout.splitlines() if l.strip().startswith("Plan 1:"))
        self.assertNotIn("--execute", dry_plan)
        self.assertIn("--include-dnse-foreign-flow", dry_plan)
        self.assertIn("--execute", live_plan)
        self.assertIn("--include-dnse-foreign-flow", live_plan)

    def test_generate_plan_always_includes_current_state_market_risk_for_trusted_ai(self):
        """Same status as the DNSE foreign-flow capability immediately above: the
        authoritative production release profile opts current-state market risk in
        unconditionally whenever it generates the trusted-ai artifact set -- no separate
        orchestrator-level flag needed. The lower-level builder keeps its own independent,
        explicit, default-off flag (see test_operate_stocklookup.py's forwarding tests)."""
        dry = self.run_fixture(["trusted-ai", "--generate"])
        dry_plan = next(l for l in dry.stdout.splitlines() if l.strip().startswith("Plan 1:"))
        self.assertIn("--include-current-state-market-risk", dry_plan)
        live = self.run_fixture(["trusted-ai", "--generate", "--live"])
        live_plan = next(l for l in live.stdout.splitlines() if l.strip().startswith("Plan 1:"))
        self.assertIn("--include-current-state-market-risk", live_plan)

    def test_generate_plan_includes_current_state_market_risk_for_all_group_too(self):
        res = self.run_fixture(["all", "--generate"])
        plan = next(l for l in res.stdout.splitlines() if l.strip().startswith("Plan 1:"))
        self.assertIn("--include-current-state-market-risk", plan)

    def test_current_state_market_risk_flag_never_leaks_into_publish_plan(self):
        live = self.run_fixture(["trusted-ai", "--generate", "--live"])
        generate_plan = next(l for l in live.stdout.splitlines()
                             if l.strip().startswith("Plan") and "operate_stocklookup.py" in l)
        publish_plan = next(l for l in live.stdout.splitlines()
                            if l.strip().startswith("Plan") and "publish_release.py" in l)
        self.assertIn("--include-current-state-market-risk", generate_plan)
        self.assertNotIn("--include-current-state-market-risk", publish_plan)

    def test_whole_market_live_gating_unaffected_by_the_execute_fix(self):
        """whole-market's own child commands (build_frontend.py, publish_dashboard.py)
        already gated --live correctly before this repair; the cmd_generate fix must not
        have disturbed that unrelated code path."""
        dry = self.run_fixture(["whole-market"])
        live = self.run_fixture(["whole-market", "--live"])
        dry_out = "\n".join(l for l in dry.stdout.splitlines() if l.strip().startswith("Plan"))
        live_out = "\n".join(l for l in live.stdout.splitlines() if l.strip().startswith("Plan"))
        self.assertIn("build_frontend.py", dry_out)
        self.assertIn("publish_dashboard.py", dry_out)
        self.assertNotIn("--live", dry_out)
        self.assertIn("--live", live_out)

    def test_publish_release_plan_never_receives_live_without_orchestrator_live(self):
        """The publisher plan (Plan 2 when --generate is set) must only ever carry --live
        when the orchestrator itself is --live -- --generate alone (the fixed preflight
        mode) must not be able to reach the live publisher path at all."""
        dry = self.run_fixture(["trusted-ai", "--generate"])
        live = self.run_fixture(["trusted-ai", "--generate", "--live"])
        dry_publish_plan = next(l for l in dry.stdout.splitlines()
                                if l.strip().startswith("Plan") and "publish_release.py" in l)
        live_publish_plan = next(l for l in live.stdout.splitlines()
                                 if l.strip().startswith("Plan") and "publish_release.py" in l)
        self.assertNotIn("--live", dry_publish_plan)
        self.assertIn("--live", live_publish_plan)

    def test_generate_and_publish_plans_do_not_share_flags(self):
        """Generation flags (--execute, --include-dnse-foreign-flow) must never leak into
        the publish_release.py plan, and publish-only concerns (--live on that specific
        command) must never leak into the generate plan -- the two child commands stay
        cleanly separated regardless of mode."""
        live = self.run_fixture(["trusted-ai", "--generate", "--live"])
        generate_plan = next(l for l in live.stdout.splitlines()
                             if l.strip().startswith("Plan") and "operate_stocklookup.py" in l)
        publish_plan = next(l for l in live.stdout.splitlines()
                            if l.strip().startswith("Plan") and "publish_release.py" in l)
        self.assertNotIn("--include-dnse-foreign-flow", publish_plan)
        self.assertNotIn("--execute", publish_plan)
        self.assertNotIn("--live", generate_plan)

    def test_dry_run_generate_performs_no_backend_artifact_writes(self):
        """The literal proof the milestone asks for: a real (non-mocked) --generate
        subprocess call against a runtime root that is valid enough to reach
        operate_stocklookup.py's own dry-run branch must leave every existing backend
        artifact byte-identical -- not merely "the argv lacks --execute" but "nothing on
        disk changed". This fixture is intentionally minimal (no release artifacts), so
        Plan 2 (publish_release.py) legitimately fails its own, separate, pre-existing
        missing-manifest gate -- that failure is expected and irrelevant to what this
        test proves; test_generate_runs_before_trusted_ai_plan_and_its_failure_stops_publish
        already covers plan-failure composition. This test only asserts Plan 1 itself: it
        ran for real, in dry mode, and wrote nothing. Deliberately does not exercise the
        served/web side (already covered by test_canonical_whole_market_plan_isolation and
        the web-dir fixture staying untouched whenever the generate stage fails or stays
        dry)."""
        backend = self._make_valid_operate_backend_dir(self.backend_dir, FIXTURE_SESSION)
        before = {p: (backend / p).read_bytes() for p in
                 ("vn_stock.db", "screen_snapshot_live.csv", "market_breadth.csv",
                  "ta_signals.csv", "analysis_latest.json", "macro_snapshot.csv",
                  "Focus_Analysis.md")}
        reports_dir = backend / "reports"
        self.assertFalse(reports_dir.exists(), "fixture must start with no reports/ directory")

        res = self.run_fixture(["trusted-ai", "--generate"], backend_dir=backend)

        self.assertTrue(self._executed(res, "operate_stocklookup.py"), res.stdout + res.stderr)
        self.assertIn("[operate] dry_run_plan: passed", res.stdout)
        self.assertIn("[operate] rollback_point: skipped", res.stdout)
        after = {p: (backend / p).read_bytes() for p in before}
        self.assertEqual(before, after, "a dry-run --generate must not modify any backend artifact")
        # capture_rollback_point() is itself skipped when execute=False (see
        # operate_stocklookup.py); its absence is further proof no write-mode branch ran.
        self.assertFalse((backend / "reports").exists(),
                         "dry-run must not create reports/ (rollback point / operating report)")
        self.assertFalse((backend / "analysis_bundle.json").exists(),
                         "dry-run must not create a new analysis_bundle.json")

    @staticmethod
    def _make_valid_operate_backend_dir(path: Path, session: str) -> Path:
        """Enough of a runtime root for operate_stocklookup.py's OWN dry-run branch to
        reach `return 0` for real (preflight, database, share-freshness) without ever
        needing --execute's write path -- mirrors tests/test_operate_stocklookup.py's
        `_runtime()` fixture, trimmed to exactly what the dry-run code path reads.
        No sidecar file is pre-created: build_sidecar() skips cleanly (not a write) when
        none exists yet, so this stays the minimal valid fixture, not a maximal one."""
        import sqlite3

        path.mkdir(parents=True, exist_ok=True)
        (path / "data_bctc").mkdir(parents=True, exist_ok=True)
        (path / "data_bctc" / "AAA_balance_sheet_quarter.parquet").write_bytes(b"payload")
        for name in ("screen_snapshot_live.csv", "market_breadth.csv", "ta_signals.csv",
                     "analysis_latest.json", "macro_snapshot.csv"):
            (path / name).write_text("upstream", encoding="utf-8")
        (path / "Focus_Analysis.md").write_text(
            f"# Phan tich sau\n\n*phiên snapshot mới nhất: **{session}***\n\n## HPG\n\n## VNM\n",
            encoding="utf-8")
        evidence = path / "data" / "official-evidence"
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "share_basis_citations.jsonl").write_text("", encoding="utf-8")

        connection = sqlite3.connect(path / "vn_stock.db")
        connection.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT)")
        connection.execute("INSERT INTO ohlcv VALUES ('HPG', ?)", (session,))
        connection.execute("CREATE TABLE metadata (ticker TEXT, shares_outstanding REAL, updated TEXT)")
        connection.executemany("INSERT INTO metadata VALUES (?, ?, ?)",
                               [(t, 1000.0, f"{session} 17:00") for t in ("HPG", "VNM")])
        connection.execute("CREATE TABLE corporate_event_records "
                           "(ticker TEXT, event_code TEXT, exright_date TEXT, coverage_status TEXT)")
        connection.commit()
        connection.close()

        # release_orchestrator.py's OWN session anchor (get_runtime_session), separate
        # from operate_stocklookup.py's REQUIRED_UPSTREAM screen_snapshot_live.csv.
        with (path / "screen_snapshot.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["ticker", "exchange", "date"])
            writer.writerow(["HPG", "HOSE", session])
        return path

    def test_no_generate_means_no_operate_stocklookup_invocation_at_all(self):
        """Without --generate, the trusted-ai group only publishes an already-built
        artifact set -- operate_stocklookup.py (and therefore the DNSE flag) never appears."""
        res = self.run_fixture(["trusted-ai"])
        self.assertNotIn("operate_stocklookup.py", res.stdout)

    def test_session_gate_blocks_generate_same_as_publish(self):
        """'expected session is preserved through the call chain': a session mismatch must
        fail before ANY child process runs, generate stage included — not just before publish."""
        res = self.run_fixture(["trusted-ai", "--generate"], expected_session="2099-01-01")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Session mismatch", res.stderr)
        self.assertNotIn("[INFO] Executing child process:", res.stdout)

    # ------------------------------------------------------------------ V2 served baseline
    def test_generate_plan_auto_resolves_baseline_from_served_bundle(self):
        """The exact defect this milestone fixes: a served --web-dir must feed its own
        currently-served bundle into the next release's comparison baseline, not a stale
        hand-picked file left over from an earlier release."""
        served_bundle = {
            "reference_session_date": "2026-08-07",
            "tickers": {"POW": {"ticker_capability_matrix": {
                "research": {"qualified_research_brief": {"status": "available"}}}}},
        }
        (self.web_dir / "analysis_bundle.json").write_text(json.dumps(served_bundle), encoding="utf-8")
        res = self.run_fixture(["trusted-ai", "--generate"])
        # Checked against the actually-executed line (plain joined argv, no repr escaping) —
        # not the pre-execution "Plan 1:" preview, which prints the argv list via repr() and
        # doubles every backslash on Windows (see test_canonical_whole_market_plan_isolation).
        self.assertTrue(self._executed(res, "--research-changes-v2-baseline"), res.stdout)
        baseline_path = self.backend_dir / "reports" / "research_changes_v2_served_baseline.json"
        self.assertTrue(self._executed(res, str(baseline_path)), res.stdout)
        self.assertTrue(baseline_path.is_file())
        recorded = json.loads(baseline_path.read_text(encoding="utf-8"))
        self.assertEqual(recorded, from_served_bundle(served_bundle))
        pow_row = next(row for row in recorded["tickers"] if row["ticker"] == "POW")
        self.assertEqual(pow_row["research_status"], "available")

    def test_generate_plan_has_no_baseline_when_nothing_is_served_yet(self):
        """A fresh --web-dir with no analysis_bundle.json (first-ever release) legitimately
        yields no baseline — never a fabricated or guessed one."""
        res = self.run_fixture(["trusted-ai", "--generate"])
        self.assertFalse(self._executed(res, "--research-changes-v2-baseline"), res.stdout)

    def test_explicit_baseline_overrides_auto_resolution(self):
        """An operator-supplied --research-changes-v2-baseline still wins over whatever is
        currently served — the auto-resolution is a default, not a forced behavior."""
        served_bundle = {"reference_session_date": "2026-08-07", "tickers": {}}
        (self.web_dir / "analysis_bundle.json").write_text(json.dumps(served_bundle), encoding="utf-8")
        override = self.backend_dir / "explicit-baseline.json"
        override.write_text(json.dumps({"schema_version": "2.0.0", "snapshot_id": "qrs2-forced", "tickers": []}),
                            encoding="utf-8")
        res = self.run_fixture(["trusted-ai", "--generate", "--research-changes-v2-baseline", str(override)])
        self.assertTrue(self._executed(res, str(override)), res.stdout)
        self.assertFalse(self._executed(res, "research_changes_v2_served_baseline.json"), res.stdout)

    def test_wrong_path_legacy_web_dir_is_refused(self):
        legacy = Path(r"C:\Projects\StockLookup\worktrees\market-dashboard-main")
        res = self.run_orchestrator_proc(
            ["whole-market", "--backend-dir", str(self.backend_dir),
             "--web-dir", str(legacy), "--expected-session", FIXTURE_SESSION],
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("REFUSED", res.stderr)
        self.assertIn("legacy Dashboard checkout", res.stderr)

    def test_runtime_as_web_is_refused(self):
        runtime = Path(r"C:\Projects\StockLookup\dashboard-runtime")
        res = self.run_orchestrator_proc(
            ["whole-market", "--backend-dir", str(self.backend_dir),
             "--web-dir", str(runtime), "--expected-session", FIXTURE_SESSION],
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("REFUSED", res.stderr)

    def test_backend_equals_web_is_refused(self):
        res = self.run_fixture(["whole-market"], backend_dir=self.web_dir, web_dir=self.web_dir)
        self.assertNotEqual(res.returncode, 0)
        combined = res.stderr + res.stdout
        self.assertTrue(
            "equals WEB_ROOT" in combined or "backend == web" in combined,
            combined,
        )

    def test_cockpit_uses_producer_publisher_not_web_dir_copy(self):
        projection = self.backend_dir / "current_decision_cockpit_projection.json"
        projection.write_text(json.dumps({
            "session": FIXTURE_SESSION,
            "source": {"operation_identity": "daily_research_session_operation:test"},
        }), encoding="utf-8")
        res = self.run_fixture([
            "cockpit",
            "--cockpit-projection-source", str(projection),
            "--expected-cockpit-operation-identity", "daily_research_session_operation:test",
        ])
        self.assertIn(repr(str(ROOT / "publish_dashboard.py")), res.stdout)
        self.assertNotIn(repr(str(self.web_dir / "publish_dashboard.py")), res.stdout)

    def test_live_success_is_github_source_updated_not_published(self):
        from release_checkout_identity import GITHUB_SOURCE_UPDATED, PUBLISHED, publication_state_after_push
        self.assertEqual(
            publication_state_after_push(local_validation_pass=True),
            GITHUB_SOURCE_UPDATED,
        )
        self.assertEqual(
            publication_state_after_push(
                local_validation_pass=True, ci_pass=True, pages_pass=True, public_verify_pass=True,
            ),
            PUBLISHED,
        )
        res = self.run_fixture(["whole-market", "--live"])
        if "Release orchestration" in res.stdout:
            self.assertIn(GITHUB_SOURCE_UPDATED, res.stdout)
            self.assertNotIn(f"[OK] Release orchestration for 'whole-market' completed successfully.", res.stdout)


class ResolveResearchChangesV2BaselineTests(unittest.TestCase):
    """Direct unit tests of the resolution function, isolated from subprocess/CLI concerns."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.web_dir = base / "web"
        self.web_dir.mkdir()
        self.backend_dir = base / "backend"
        self.backend_dir.mkdir()

    def test_no_served_bundle_yields_no_baseline(self):
        result = release_orchestrator.resolve_research_changes_v2_baseline(self.web_dir, self.backend_dir, ROOT)
        self.assertIsNone(result)

    def test_served_bundle_is_reconstructed_deterministically(self):
        served_bundle = {
            "reference_session_date": "2026-08-07",
            "tickers": {
                "POW": {"ticker_capability_matrix": {"research": {"qualified_research_brief": {"status": "available"}}}},
                "HPG": {"ticker_capability_matrix": {"research": {"qualified_research_brief": {"status": "unavailable"}}}},
            },
        }
        (self.web_dir / "analysis_bundle.json").write_text(json.dumps(served_bundle), encoding="utf-8")
        result = release_orchestrator.resolve_research_changes_v2_baseline(self.web_dir, self.backend_dir, ROOT)
        self.assertIsNotNone(result)
        recorded = json.loads(result.read_text(encoding="utf-8"))
        self.assertEqual(recorded, from_served_bundle(served_bundle))
        statuses = {row["ticker"]: row["research_status"] for row in recorded["tickers"]}
        self.assertEqual(statuses["POW"], "available")
        self.assertEqual(statuses["HPG"], "unavailable")

    def test_malformed_served_bundle_yields_no_baseline_not_a_crash(self):
        (self.web_dir / "analysis_bundle.json").write_text("{not valid json", encoding="utf-8")
        result = release_orchestrator.resolve_research_changes_v2_baseline(self.web_dir, self.backend_dir, ROOT)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
