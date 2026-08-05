"""Dedicated test suite for release_orchestrator.py."""

import os
import sys
import unittest
import tempfile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = ROOT / "tools" / "release_orchestrator.py"


class ReleaseOrchestratorUnitTests(unittest.TestCase):

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

    def test_missing_subcommand_fails(self):
        res = self.run_orchestrator_proc([])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Missing release group subcommand", res.stderr)

    def test_unknown_argument_fails(self):
        res = self.run_orchestrator_proc(["--unknown-arg"])
        self.assertNotEqual(res.returncode, 0)

    def test_wrong_expected_session_fails(self):
        res = self.run_orchestrator_proc(["whole-market", "--expected-session", "2099-01-01"])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Session mismatch", res.stderr)

    def test_wrong_expected_dashboard_head_fails(self):
        res = self.run_orchestrator_proc(["whole-market", "--expected-dashboard-head", "0000000000000000000000000000000000000000"])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Dashboard HEAD mismatch", res.stderr)

    def test_canonical_whole_market_plan_isolation(self):
        res = self.run_orchestrator_proc(["whole-market", "--expected-session", "2026-08-04"])
        self.assertEqual(res.returncode, 0, f"Unexpected error: {res.stderr}\nSTDOUT:\n{res.stdout}")
        self.assertIn("SELECTED_GROUP        : whole-market", res.stdout)
        self.assertIn("TRUSTED_AI_INVOKED    : false", res.stdout)
        self.assertNotIn("publish_release.py", res.stdout)
        self.assertNotIn(".bat", res.stdout)
        self.assertNotIn("cmd.exe", res.stdout)
        self.assertIn("stock-core-private\\tools\\build_frontend.py", res.stdout)
        self.assertIn("stock-core-private\\publish_dashboard.py", res.stdout)
        self.assertNotIn("market-dashboard-main\\publish_dashboard.py", res.stdout)

    def test_single_instance_lock(self):
        lock_file = Path(tempfile.gettempdir()) / "stock_lookup_release_orchestrator.lock"
        if lock_file.exists():
            try:
                lock_file.unlink()
            except Exception:
                pass
        lock_file.write_text("99999", encoding="utf-8")
        try:
            res = self.run_orchestrator_proc(["whole-market"])
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("Lock file exists", res.stderr)
        finally:
            if lock_file.exists():
                try:
                    lock_file.unlink()
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
