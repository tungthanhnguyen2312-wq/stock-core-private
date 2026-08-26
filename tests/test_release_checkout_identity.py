"""Canonical Dashboard checkout identity and publication-state vocabulary."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from release_checkout_identity import (
    CANONICAL_BACKEND_ROOT,
    CANONICAL_PRODUCER_ORCHESTRATOR,
    CANONICAL_PRODUCER_PUBLISH_DASHBOARD,
    CANONICAL_PRODUCER_PUBLISH_RELEASE,
    CANONICAL_WEB_ROOT,
    GITHUB_SOURCE_UPDATED,
    PUBLISHED,
    ReleaseIdentityError,
    TEST_FIXTURE_ENV,
    assert_producer_publisher_file,
    assert_web_checkout_identity,
    origin_is_canonical,
    publication_state_after_push,
)


class OriginAndPublisherAuthorityTests(unittest.TestCase):
    def test_canonical_https_and_ssh_origins(self):
        self.assertTrue(origin_is_canonical(
            "https://github.com/tungthanhnguyen2312-wq/market-dashboard.git"))
        self.assertTrue(origin_is_canonical(
            "git@github.com:tungthanhnguyen2312-wq/market-dashboard.git"))
        self.assertFalse(origin_is_canonical("https://github.com/other/market-dashboard.git"))

    def test_producer_files_are_the_only_publisher_authority(self):
        assert_producer_publisher_file(CANONICAL_PRODUCER_PUBLISH_DASHBOARD, role="publish_dashboard")
        assert_producer_publisher_file(CANONICAL_PRODUCER_PUBLISH_RELEASE, role="publish_release")
        assert_producer_publisher_file(CANONICAL_PRODUCER_ORCHESTRATOR, role="release_orchestrator")
        with self.assertRaises(ReleaseIdentityError):
            assert_producer_publisher_file(
                CANONICAL_WEB_ROOT / "publish_dashboard.py", role="publish_dashboard")

    def test_push_is_not_published(self):
        self.assertEqual(publication_state_after_push(local_validation_pass=True),
                         GITHUB_SOURCE_UPDATED)
        self.assertNotEqual(publication_state_after_push(local_validation_pass=True), PUBLISHED)
        self.assertEqual(
            publication_state_after_push(
                local_validation_pass=True, ci_pass=True, pages_pass=True, public_verify_pass=True),
            PUBLISHED,
        )


class CheckoutRefusalTests(unittest.TestCase):
    def setUp(self):
        self._orig = os.environ.get(TEST_FIXTURE_ENV)
        os.environ.pop(TEST_FIXTURE_ENV, None)

    def tearDown(self):
        if self._orig is None:
            os.environ.pop(TEST_FIXTURE_ENV, None)
        else:
            os.environ[TEST_FIXTURE_ENV] = self._orig

    def test_wrong_path_refused(self):
        with self.assertRaises(ReleaseIdentityError) as ctx:
            assert_web_checkout_identity(Path(r"C:\Projects\StockLookup\worktrees\market-dashboard-main"))
        self.assertIn("legacy Dashboard checkout", str(ctx.exception))

    def test_wrong_origin_refused(self):
        os.environ[TEST_FIXTURE_ENV] = ""
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            os.environ.pop(TEST_FIXTURE_ENV, None)
            with self.assertRaises(ReleaseIdentityError):
                assert_web_checkout_identity(
                    CANONICAL_WEB_ROOT,
                    origin_url="https://github.com/someone-else/market-dashboard.git",
                    branch="main",
                )

    def test_wrong_branch_refused(self):
        with self.assertRaises(ReleaseIdentityError) as ctx:
            assert_web_checkout_identity(
                CANONICAL_WEB_ROOT,
                origin_url="https://github.com/tungthanhnguyen2312-wq/market-dashboard.git",
                branch="feature/horizontal-top-navigation",
            )
        self.assertIn("web branch must be main", str(ctx.exception))

    def test_runtime_as_web_refused(self):
        with self.assertRaises(ReleaseIdentityError) as ctx:
            assert_web_checkout_identity(CANONICAL_BACKEND_ROOT)
        self.assertIn("dashboard-runtime", str(ctx.exception).replace("/", "\\"))

    def test_backend_equals_web_refused(self):
        with self.assertRaises(ReleaseIdentityError):
            assert_web_checkout_identity(CANONICAL_WEB_ROOT, backend_dir=CANONICAL_WEB_ROOT)

    def test_same_checkout_mismatch_refused(self):
        with self.assertRaises(ReleaseIdentityError) as ctx:
            assert_web_checkout_identity(
                CANONICAL_WEB_ROOT,
                origin_url="https://github.com/tungthanhnguyen2312-wq/market-dashboard.git",
                branch="main",
                git_toplevel=CANONICAL_BACKEND_ROOT,
            )
        self.assertIn("same checkout", str(ctx.exception))

    def test_live_head_must_match_origin_main(self):
        with self.assertRaises(ReleaseIdentityError) as ctx:
            assert_web_checkout_identity(
                CANONICAL_WEB_ROOT,
                origin_url="https://github.com/tungthanhnguyen2312-wq/market-dashboard.git",
                branch="main",
                head="aaaaaaaa",
                origin_main="bbbbbbbb",
                live=True,
                git_toplevel=CANONICAL_WEB_ROOT,
            )
        self.assertIn("HEAD", str(ctx.exception))

    def test_canonical_live_accepts_matching_identity(self):
        assert_web_checkout_identity(
            CANONICAL_WEB_ROOT,
            backend_dir=CANONICAL_BACKEND_ROOT,
            origin_url="https://github.com/tungthanhnguyen2312-wq/market-dashboard.git",
            branch="main",
            head="661bb77b9caa5630ad02949233eb7433a63fe728",
            origin_main="661bb77b9caa5630ad02949233eb7433a63fe728",
            live=True,
            git_toplevel=CANONICAL_WEB_ROOT,
        )


class WorkspaceStatusTopologyTests(unittest.TestCase):
    def test_workspace_status_lists_canonical_dashboard_not_legacy_web(self):
        status = Path(r"C:\Projects\StockLookup\tools\workspace_status.py")
        text = status.read_text(encoding="utf-8")
        self.assertIn('("market-dashboard", "main", True)', text)
        self.assertNotIn("worktrees/market-dashboard-main", text)
        self.assertNotIn("worktrees/market-dashboard-phase5", text)
        self.assertNotIn("worktrees/market-dashboard-ci", text)
        self.assertIn('("dashboard-runtime", None, False)', text)


if __name__ == "__main__":
    unittest.main()
