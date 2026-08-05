"""Regression coverage for the dry-run/--live safety split in publish_dashboard.py.

publish_dashboard.py is a gitignored, local-only script (see docs/PROJECT_HEALTH_AUDIT.md
finding P1-02 and C:\\Projects\\.ai\\PUBLISH_DRYRUN_FIX_REPORT.md for the fix this test
file exists to protect). These tests import it directly the same way
tests/test_selftest.py imports stock_analyzer — it only works on a machine that has the
real file on disk, which is the intended/only environment this script ever runs in.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import publish_dashboard as pd  # noqa: E402


def _write_min_fixture(root: Path) -> None:
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "js").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "css").mkdir(parents=True, exist_ok=True)
    (root / "screen_snapshot.csv").write_text(
        "ticker,exchange,date\nHPG,HSX,2026-07-17\nABC,HNX,2026-07-17\n", encoding="utf-8"
    )
    # date column matches screen_snapshot.csv above — release_session_contract cross-
    # checks every session-sensitive artifact, so a realistic fixture ("published at
    # least once") must agree on session, same as the real repo does after a publish.
    (root / "market_breadth.csv").write_text("group,date,n_up\nALL,2026-07-17,1\n", encoding="utf-8")
    (root / "analysis_bundle.json").write_text(
        '{"reference_session_date": "2026-07-17"}\n', encoding="utf-8"
    )
    for name in (
        "app.js", "style.css", "assets/js/value-format.js",
        "assets/js/company-panel.js", "assets/css/tailwind.generated.css",
    ):
        (root / name).write_text("/* fixture */\n", encoding="utf-8")
    # build_whitelist()/validate_json_artifacts() require every SAFE_WEB_ARTIFACTS
    # path to already exist on disk (pre-existing behaviour, unrelated to the
    # dry-run fix) — stub whatever isn't already created above, so the fixture
    # represents "a repo that has published at least once", matching the real repo.
    for relative in sorted(pd.SAFE_WEB_ARTIFACTS):
        path = root / relative
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n" if relative.endswith(".json") else "/* fixture */\n", encoding="utf-8")
    (root / "dashboard.html").write_text(
        '<html><head><link href="style.css"><script src="app.js"></script></head>'
        "<body></body></html>\n",
        encoding="utf-8",
    )


class FakeGit:
    """Records every git(*args) call; answers only the read-only queries publish_dashboard
    needs for a clean, conflict-free repo. Anything unexpected raises loudly instead of
    silently faking a mutating command."""

    def __init__(self, root: Path, branch: str = "main"):
        self.root = root
        self.branch = branch
        self.calls: list[tuple[str, ...]] = []
        self.status_output = ""

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
            return True, "2026-07-19T00:00:00+07:00"
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
        raise AssertionError(f"Unexpected git() call in test: {args!r}")


class _PublishDashboardTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="publish_dashboard_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        _write_min_fixture(self.tmp)

        self._orig_web = pd.WEB_ROOT
        self._orig_backend = pd.BACKEND_ROOT
        self._orig_live = pd.LIVE_MODE
        pd.WEB_ROOT = self.tmp
        pd.BACKEND_ROOT = self.tmp  # backend == web -> copy step is a documented no-op
        pd.LIVE_MODE = False
        self.addCleanup(self._restore_globals)

        self.fake_git = FakeGit(self.tmp)

    def _restore_globals(self):
        pd.WEB_ROOT = self._orig_web
        pd.BACKEND_ROOT = self._orig_backend
        pd.LIVE_MODE = self._orig_live

    def _all_files(self, exclude_logs: bool = False) -> dict[str, tuple[int, bytes]]:
        return {
            str(p.relative_to(self.tmp)): (p.stat().st_mtime_ns, p.read_bytes())
            for p in self.tmp.rglob("*")
            if p.is_file() and not (exclude_logs and "logs" in p.relative_to(self.tmp).parts)
        }

    def _run(self, argv: list[str]) -> int:
        with mock.patch.object(pd, "git", self.fake_git), mock.patch("sys.argv", argv):
            return pd.main()


class DryRunIsFullyReadOnlyTests(_PublishDashboardTestBase):
    """No --live: publisher must not write, copy, or mutate anything."""

    def test_write_functions_are_never_called(self):
        with mock.patch.object(pd, "copy_public_artifacts") as m_copy, \
             mock.patch.object(pd, "write_build_manifest") as m_manifest, \
             mock.patch.object(pd, "update_asset_versions") as m_version:
            rc = self._run(["publish_dashboard.py"])
        self.assertEqual(rc, 0)
        m_copy.assert_not_called()
        m_manifest.assert_not_called()
        m_version.assert_not_called()

    def test_no_tracked_or_output_file_changes_on_disk(self):
        before = self._all_files()
        rc = self._run(["publish_dashboard.py"])
        self.assertEqual(rc, 0)
        after = self._all_files()
        self.assertEqual(before, after, "Dry-run không được đổi hoặc tạo bất kỳ byte nào trên đĩa")

    def test_no_new_output_file_is_created(self):
        before_paths = {str(p.relative_to(self.tmp)) for p in self.tmp.rglob("*") if p.is_file()}
        rc = self._run(["publish_dashboard.py"])
        self.assertEqual(rc, 0)
        after_paths = {str(p.relative_to(self.tmp)) for p in self.tmp.rglob("*") if p.is_file()}
        self.assertEqual(before_paths, after_paths, "Dry-run không được tạo file output mới nào")

    def test_no_log_file_is_written(self):
        rc = self._run(["publish_dashboard.py"])
        self.assertEqual(rc, 0)
        self.assertFalse((self.tmp / "logs").exists(), "Dry-run không được tạo thư mục/log file logs/*")

    def test_no_git_mutation_commands_are_issued(self):
        rc = self._run(["publish_dashboard.py"])
        self.assertEqual(rc, 0)
        mutating = {"add", "commit", "push", "pull", "fetch"}
        used = {call[0] for call in self.fake_git.calls if call}
        self.assertFalse(used & mutating, f"Dry-run gọi git mutation: {used & mutating}")

    def test_preview_reports_the_plan_without_applying_it(self):
        rc = self._run(["publish_dashboard.py"])
        self.assertEqual(rc, 0)
        # dashboard.html references style.css/app.js -> plan_asset_versions() must
        # detect it would change, purely by computing (not writing) the new text.
        rows, breadth, market_session = pd.validate_snapshot()
        manifest, _content = pd.compute_manifest(rows, breadth, market_session, "0" * 40)
        version_plan = pd.plan_asset_versions(str(manifest["build_id"]))
        self.assertIn("dashboard.html", version_plan)

    def test_missing_volume_basis_fails_closed_in_computed_manifest(self):
        rows, breadth, market_session = pd.validate_snapshot()
        manifest, _content = pd.compute_manifest(rows, breadth, market_session, "0" * 40)
        contract = manifest["price_basis_contract"]
        self.assertEqual(contract["volume_basis"], "unknown")
        self.assertFalse(contract["volume_basis_verified"])

    def test_partial_provenance_cannot_enable_volume_basis_by_default(self):
        (self.tmp / "analysis_bundle.json").write_text(
            '{"price_basis_provenance":{"price_basis":"unknown","price_basis_verified":false}}\n',
            encoding="utf-8",
        )
        rows, breadth, market_session = pd.validate_snapshot()
        manifest, _content = pd.compute_manifest(rows, breadth, market_session, "0" * 40)
        contract = manifest["price_basis_contract"]
        self.assertEqual(contract["volume_basis"], "unknown")
        self.assertFalse(contract["volume_basis_verified"])


class LiveModeAppliesWritesInOrderTests(_PublishDashboardTestBase):
    """--live: the same three write functions must run, in order, and only touch the
    sandboxed WEB_ROOT — never a real git push."""

    def test_live_calls_copy_manifest_version_in_order_then_publish_live(self):
        self.fake_git.status_output = " M dashboard.html\n"
        order: list[str] = []
        real_copy, real_manifest, real_version = (
            pd.copy_public_artifacts, pd.write_build_manifest, pd.update_asset_versions,
        )

        def spy_copy():
            order.append("copy")
            return real_copy()

        def spy_manifest(manifest, content):
            order.append("manifest")
            return real_manifest(manifest, content)

        def spy_version(build_id):
            order.append("version")
            return real_version(build_id)

        with mock.patch.object(pd, "copy_public_artifacts", side_effect=spy_copy), \
             mock.patch.object(pd, "write_build_manifest", side_effect=spy_manifest), \
             mock.patch.object(pd, "update_asset_versions", side_effect=spy_version), \
             mock.patch.object(pd, "publish_live", return_value=0) as m_publish:
            rc = self._run(["publish_dashboard.py", "--live"])

        self.assertEqual(rc, 0)
        self.assertEqual(order, ["copy", "manifest", "version"],
                          "Thứ tự apply phải đúng: copy -> manifest -> version")
        m_publish.assert_called_once()
        # publish_live() itself was mocked out, so no add/commit/push should ever fire.
        mutating = {"add", "commit", "push"}
        used = {call[0] for call in self.fake_git.calls if call}
        self.assertFalse(used & mutating,
                          "Test không được thật sự add/commit/push — publish_live phải bị mock")

    def test_live_actually_writes_files_only_inside_sandbox(self):
        self.fake_git.status_output = " M dashboard.html\n"
        with mock.patch.object(pd, "publish_live", return_value=0):
            rc = self._run(["publish_dashboard.py", "--live"])
        self.assertEqual(rc, 0)
        self.assertTrue((self.tmp / "data" / "build_info.json").exists())
        self.assertTrue((self.tmp / "data" / "screener_data.js").exists())
        html = (self.tmp / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("?v=", html, "update_asset_versions() phải thêm cache-busting token khi --live")


class ValidationFailureStopsBeforeAnyWriteTests(_PublishDashboardTestBase):
    def setUp(self):
        super().setUp()
        # Xoá cột bắt buộc -> validate_snapshot() phải raise trước khi chạm bước ghi nào.
        (self.tmp / "screen_snapshot.csv").write_text("ticker,date\nHPG,2026-07-17\n", encoding="utf-8")

    def test_invalid_snapshot_stops_before_any_write_even_with_live(self):
        # exclude_logs=True: một lời gọi --live hợp lệ (dù validation thất bại) vẫn được
        # phép ghi log — đó là hành vi mong đợi từ trước, không phải phần của lỗi P1 đang
        # sửa. Cái cần chứng minh ở đây là KHÔNG file nội dung nào (HTML/manifest/data) bị
        # ghi khi validation thất bại, kể cả với --live.
        before = self._all_files(exclude_logs=True)
        with mock.patch.object(pd, "copy_public_artifacts") as m_copy, \
             mock.patch.object(pd, "write_build_manifest") as m_manifest, \
             mock.patch.object(pd, "update_asset_versions") as m_version:
            rc = self._run(["publish_dashboard.py", "--live"])
        self.assertEqual(rc, 1, "Validation lỗi phải trả về mã lỗi, không được publish")
        m_copy.assert_not_called()
        m_manifest.assert_not_called()
        m_version.assert_not_called()
        after = self._all_files(exclude_logs=True)
        self.assertEqual(before, after, "Validation thất bại không được để lại thay đổi nào trên đĩa")


def _write_backend_fixture(root: Path, session: str, *, live_session: str | None = None) -> None:
    """A backend/runtime root holding just the generated data files (no HTML/assets) —
    what BACKEND_ROOT looks like after a `vn_indicators.py` + `export_ai_bundle.py` run."""
    live_session = live_session or session
    root.mkdir(parents=True, exist_ok=True)
    (root / "bundle_manifest.json").write_text(json.dumps({
        "schema_version": "1.1.0",
        "freshness": {"reference_session": session, "blocked": False, "status": "fresh"},
    }), encoding="utf-8")
    (root / "screen_snapshot.csv").write_text(
        f"ticker,exchange,date\nHPG,HSX,{session}\nABC,HNX,{session}\n", encoding="utf-8")
    (root / "market_breadth.csv").write_text(f"group,date,n_up\nALL,{session},1\n", encoding="utf-8")
    (root / "screen_snapshot_live.csv").write_text(
        f"ticker,exchange,date\nHPG,HSX,{live_session}\n", encoding="utf-8")
    (root / "analysis_bundle.json").write_text(
        json.dumps({"reference_session_date": session}), encoding="utf-8")


class SessionMismatchStopsBeforeAnyWriteTests(_PublishDashboardTestBase):
    """Reproduces the reported defect directly: a session disagreement must stop the
    publisher before any copy/manifest/version/git write, in both the single-root case
    (bare invocation; BACKEND_ROOT defaults to WEB_ROOT) and the cross-root case."""

    def test_single_root_self_inconsistent_manifest_fails_closed(self):
        # The exact repro: bundle_manifest.json (already in WEB_ROOT from an earlier,
        # separate publish_release.py run) disagrees with WEB_ROOT's own stale
        # screen_snapshot.csv — BACKEND_ROOT == WEB_ROOT because no override was set.
        (self.tmp / "bundle_manifest.json").write_text(json.dumps({
            "freshness": {"reference_session": "2026-08-04", "blocked": False, "status": "fresh"},
        }), encoding="utf-8")
        before = self._all_files(exclude_logs=True)
        with mock.patch.object(pd, "copy_public_artifacts") as m_copy, \
             mock.patch.object(pd, "write_build_manifest") as m_manifest:
            rc = self._run(["publish_dashboard.py"])
        self.assertEqual(rc, 1)
        m_copy.assert_not_called()
        m_manifest.assert_not_called()
        after = self._all_files(exclude_logs=True)
        self.assertEqual(before, after)

    def test_cross_root_stale_web_copy_does_not_mask_fresh_backend_mismatch_report(self):
        backend = Path(tempfile.mkdtemp(prefix="publish_dashboard_backend_"))
        self.addCleanup(shutil.rmtree, backend, ignore_errors=True)
        # WEB_ROOT (self.tmp) already holds screen_snapshot.csv dated 2026-07-17 from the
        # fixture; BACKEND_ROOT disagrees internally (manifest says 08-04, its own
        # screen_snapshot.csv is 07-24) — the exact "two publishers left it inconsistent"
        # shape found in the real worktree. This must fail on the BACKEND disagreement,
        # not silently pass by reading WEB_ROOT's unrelated stale copy instead.
        _write_backend_fixture(backend, "2026-08-04")
        (backend / "screen_snapshot.csv").write_text(
            "ticker,exchange,date\nHPG,HSX,2026-07-24\nABC,HNX,2026-07-24\n", encoding="utf-8")
        pd.BACKEND_ROOT = backend

        with mock.patch.object(pd, "copy_public_artifacts") as m_copy:
            rc = self._run(["publish_dashboard.py"])
        self.assertEqual(rc, 1)
        m_copy.assert_not_called()


class PathResolutionReadsFreshBackendTests(_PublishDashboardTestBase):
    """Scenario 11 (generalized): proves the publisher reads BACKEND_ROOT's current
    generation, not whatever stale copy already sits in WEB_ROOT from a previous publish —
    the concrete case is BACKEND_ROOT=dashboard-runtime, WEB_ROOT=the served checkout;
    this test stands the same shape up with two temp directories."""

    def test_dry_run_reports_backend_session_not_stale_web_root_session(self):
        backend = Path(tempfile.mkdtemp(prefix="publish_dashboard_backend_"))
        self.addCleanup(shutil.rmtree, backend, ignore_errors=True)
        _write_backend_fixture(backend, "2026-08-04")
        pd.BACKEND_ROOT = backend
        # self.tmp (WEB_ROOT) still holds the fixture's 2026-07-17 screen_snapshot.csv —
        # a stand-in for the served checkout's last-published, now-stale copy.
        self.assertIn("2026-07-17", (self.tmp / "screen_snapshot.csv").read_text(encoding="utf-8"))

        rc = self._run(["publish_dashboard.py"])

        self.assertEqual(rc, 0)
        rows, breadth, market_session = pd.validate_snapshot()
        self.assertEqual(market_session, "2026-08-04", "must read BACKEND_ROOT's session, not WEB_ROOT's stale copy")

    def test_backend_missing_optional_files_falls_back_to_web_root_gracefully(self):
        """BACKEND_ROOT lacking an optional artifact (e.g. analysis_bundle.json was never
        generated there) must not crash source_root() — it degrades to WEB_ROOT for that
        one name, same as a single-root invocation would."""
        backend = Path(tempfile.mkdtemp(prefix="publish_dashboard_backend_"))
        self.addCleanup(shutil.rmtree, backend, ignore_errors=True)
        (backend / "screen_snapshot.csv").write_text(
            "ticker,exchange,date\nHPG,HSX,2026-07-17\nABC,HNX,2026-07-17\n", encoding="utf-8")
        (backend / "market_breadth.csv").write_text("group,date,n_up\nALL,2026-07-17,1\n", encoding="utf-8")
        pd.BACKEND_ROOT = backend

        self.assertEqual(pd.source_root("analysis_bundle.json"), pd.WEB_ROOT)
        rc = self._run(["publish_dashboard.py"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
