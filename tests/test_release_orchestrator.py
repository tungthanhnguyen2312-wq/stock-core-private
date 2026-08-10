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

    def run_orchestrator_proc(self, args: list[str], cwd=None):
        cmd = [sys.executable, str(ORCHESTRATOR)] + args
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
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
        args += ["--backend-dir", str(overrides.get("backend_dir", self.backend_dir))]
        args += ["--web-dir", str(overrides.get("web_dir", self.web_dir))]
        if "expected_session" not in overrides or overrides["expected_session"] is not None:
            args += ["--expected-session", overrides.get("expected_session", FIXTURE_SESSION)]
        return self.run_orchestrator_proc(args)

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
