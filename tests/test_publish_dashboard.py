"""Regression coverage for the dry-run/--live safety split in publish_dashboard.py.

publish_dashboard.py is a gitignored, local-only script (see docs/PROJECT_HEALTH_AUDIT.md
finding P1-02 and C:\\Projects\\.ai\\PUBLISH_DRYRUN_FIX_REPORT.md for the fix this test
file exists to protect). These tests import it directly the same way
tests/test_selftest.py imports stock_analyzer — it only works on a machine that has the
real file on disk, which is the intended/only environment this script ever runs in.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import publish_dashboard as pd  # noqa: E402
from tools.publish_release import RELEASE_ALLOWLIST as TRUSTED_AI_RELEASE_ALLOWLIST  # noqa: E402


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
    # date matches screen_snapshot.csv above for the same reason as analysis_bundle.json --
    # analysis_latest.json is now a REQUIRED release-session artifact (see
    # docs/dashboard_release_session_contract.md's "closing the publication gap" section).
    (root / "analysis_latest.json").write_text(
        '{"summary": {"session_date": "2026-07-17", "generated_at": "2026-07-17 16:00"}}\n',
        encoding="utf-8",
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
        self.tmp = Path(tempfile.mkdtemp(prefix="publish_dashboard_web_test_"))
        self.backend = Path(tempfile.mkdtemp(prefix="publish_dashboard_backend_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.backend, ignore_errors=True)

        _write_min_fixture(self.tmp)
        _write_min_fixture(self.backend)

        self._orig_web = pd.WEB_ROOT
        self._orig_backend = pd.BACKEND_ROOT
        self._orig_live = pd.LIVE_MODE
        pd.WEB_ROOT = self.tmp
        pd.BACKEND_ROOT = self.backend
        pd.LIVE_MODE = False
        self._orig_identity_env = os.environ.get("STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE")
        os.environ["STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE"] = str(self.tmp.resolve())
        self.addCleanup(self._restore_globals)

        self.fake_git = FakeGit(self.tmp)

    def _restore_globals(self):
        pd.WEB_ROOT = self._orig_web
        pd.BACKEND_ROOT = self._orig_backend
        pd.LIVE_MODE = self._orig_live
        if self._orig_identity_env is None:
            os.environ.pop("STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE", None)
        else:
            os.environ["STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE"] = self._orig_identity_env

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

        def spy_smoke():
            order.append("smoke")
            return 0

        with mock.patch.object(pd, "copy_public_artifacts", side_effect=spy_copy), \
             mock.patch.object(pd, "write_build_manifest", side_effect=spy_manifest), \
             mock.patch.object(pd, "update_asset_versions", side_effect=spy_version), \
             mock.patch.object(pd, "run_release_smoke_tests", side_effect=spy_smoke), \
             mock.patch.object(pd, "publish_live", return_value=0) as m_publish:
            rc = self._run(["publish_dashboard.py", "--live"])

        self.assertEqual(rc, 0)
        self.assertEqual(order, ["copy", "manifest", "version", "smoke"],
                          "Thứ tự apply phải đúng: copy -> manifest -> version -> smoke")
        m_publish.assert_called_once()
        # publish_live() itself was mocked out, so no add/commit/push should ever fire.
        mutating = {"add", "commit", "push"}
        used = {call[0] for call in self.fake_git.calls if call}
        self.assertFalse(used & mutating,
                          "Test không được thật sự add/commit/push — publish_live phải bị mock")

    def test_live_actually_writes_files_only_inside_sandbox(self):
        self.fake_git.status_output = " M dashboard.html\n"
        with mock.patch.object(pd, "run_release_smoke_tests", return_value=0), \
             mock.patch.object(pd, "publish_live", return_value=0):
            rc = self._run(["publish_dashboard.py", "--live"])
        self.assertEqual(rc, 0)
        self.assertTrue((self.tmp / "data" / "build_info.json").exists())
        self.assertTrue((self.tmp / "data" / "screener_data.js").exists())
        html = (self.tmp / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("?v=", html, "update_asset_versions() phải thêm cache-busting token khi --live")

    def test_atomic_all_mode_explicitly_verifies_and_stages_full_trusted_subset(self):
        """The final whole-market publisher cannot rely on incidental asset references."""
        self.fake_git.status_output = " M dashboard.html\n"
        report = pd.trusted_subset_contract.TrustedSubsetReport(
            ready=True,
            checked=list(pd.trusted_subset_contract.TRUSTED_SUBSET_ARTIFACTS),
        )
        with mock.patch.object(pd, "run_release_smoke_tests", return_value=0), \
             mock.patch.object(pd.trusted_subset_contract, "verify_trusted_subset", return_value=report) as verify, \
             mock.patch.object(pd, "publish_live", return_value=0) as publish:
            rc = self._run(["publish_dashboard.py", "--live", "--include-trusted-subset"])

        self.assertEqual(rc, 0)
        verify.assert_called_once_with(self.tmp)
        whitelist = publish.call_args.args[0]
        self.assertTrue(set(pd.trusted_subset_contract.TRUSTED_SUBSET_ARTIFACTS) <= set(whitelist))
        self.assertEqual(
            publish.call_args.kwargs["required_release_paths"],
            pd.trusted_subset_contract.TRUSTED_SUBSET_ARTIFACTS,
        )


class RemoteRaceTests(_PublishDashboardTestBase):
    def test_remote_advance_fails_closed_without_a_pull(self):
        calls: list[tuple[str, ...]] = []

        def fake_git(*args: str, timeout: int = 180):
            calls.append(args)
            if args == ("fetch", "origin", "main"):
                return True, ""
            if args == ("rev-parse", "origin/main"):
                return True, "1" * 40
            if args and args[0] == "rev-list":
                return True, "0\t1"
            raise AssertionError(f"unexpected git call: {args!r}")

        with mock.patch.object(pd, "git", side_effect=fake_git):
            with self.assertRaisesRegex(ValueError, "refusing to merge or pull"):
                pd.sync_remote_before_live("main")

        self.assertNotIn(("pull", "--ff-only", "origin", "main"), calls)


class ValidationFailureStopsBeforeAnyWriteTests(_PublishDashboardTestBase):
    def setUp(self):
        super().setUp()
        # Xoá cột bắt buộc -> validate_snapshot() phải raise trước khi chạm bước ghi nào.
        (self.backend / "screen_snapshot.csv").write_text("ticker,date\nHPG,2026-07-17\n", encoding="utf-8")

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
    (root / "analysis_latest.json").write_text(
        json.dumps({"summary": {"session_date": session}}), encoding="utf-8")


class SessionMismatchStopsBeforeAnyWriteTests(_PublishDashboardTestBase):
    """Reproduces the reported defect directly: a session disagreement must stop the
    publisher before any copy/manifest/version/git write, in both the single-root case
    (bare invocation; BACKEND_ROOT defaults to WEB_ROOT) and the cross-root case."""

    def test_single_root_self_inconsistent_manifest_fails_closed(self):
        # The exact repro: bundle_manifest.json (already in WEB_ROOT from an earlier,
        # separate publish_release.py run) disagrees with WEB_ROOT's own stale
        # screen_snapshot.csv — BACKEND_ROOT == WEB_ROOT because no override was set.
        orig_b = pd.BACKEND_ROOT
        pd.BACKEND_ROOT = self.tmp
        try:
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
        finally:
            pd.BACKEND_ROOT = orig_b

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
        one name, same as a single-root invocation would. analysis_latest.json is written
        here (unlike analysis_bundle.json) only because it is now a REQUIRED session
        artifact -- its presence is a fixture precondition for reaching the code path this
        test actually exercises, not something this test is itself about."""
        backend = Path(tempfile.mkdtemp(prefix="publish_dashboard_backend_"))
        self.addCleanup(shutil.rmtree, backend, ignore_errors=True)
        (backend / "screen_snapshot.csv").write_text(
            "ticker,exchange,date\nHPG,HSX,2026-07-17\nABC,HNX,2026-07-17\n", encoding="utf-8")
        (backend / "market_breadth.csv").write_text("group,date,n_up\nALL,2026-07-17,1\n", encoding="utf-8")
        (backend / "analysis_latest.json").write_text(
            json.dumps({"summary": {"session_date": "2026-07-17"}}), encoding="utf-8")
        pd.BACKEND_ROOT = backend

        self.assertEqual(pd.source_root("analysis_bundle.json"), pd.WEB_ROOT)
        rc = self._run(["publish_dashboard.py"])
        self.assertEqual(rc, 0)


class PublishedAtSeparationTests(_PublishDashboardTestBase):
    """published_at must track an actual --live publish of new content, never a dry-run
    preview, and must never move on a republish of unchanged content -- the runtime/publish
    contract audit (operations-review/runtime_pipeline_publish_contract_audit_20260808.md)
    found no field anywhere distinguishing 'this artifact set was generated' from 'this
    artifact set was actually committed and pushed'. See
    docs/dashboard_release_session_contract.md for the field's contract."""

    def test_dry_run_computes_generated_at_but_never_published_at(self):
        rows, breadth, market_session = pd.validate_snapshot()
        manifest, _content = pd.compute_manifest(rows, breadth, market_session, "0" * 40)
        self.assertIsNotNone(manifest["generated_at"], "preview vẫn phải tính generated_at")
        self.assertIsNone(manifest["published_at"],
                           "dry-run không xuất bản gì -- published_at phải là None")

    def test_live_new_content_gets_a_fresh_tz_aware_published_at(self):
        rows, breadth, market_session = pd.validate_snapshot()
        manifest, _content = pd.compute_manifest(rows, breadth, market_session, "0" * 40, live=True)
        self.assertIsInstance(manifest["published_at"], str)
        parsed = datetime.fromisoformat(manifest["published_at"])
        self.assertIsNotNone(parsed.tzinfo, "published_at phải timezone-aware")

    def test_market_session_is_unaffected_by_published_at(self):
        rows, breadth, market_session = pd.validate_snapshot()
        dry, _ = pd.compute_manifest(rows, breadth, market_session, "0" * 40, live=False)
        live, _ = pd.compute_manifest(rows, breadth, market_session, "0" * 40, live=True)
        self.assertEqual(dry["market_session"], market_session)
        self.assertEqual(live["market_session"], market_session,
                          "data_as_of không được đổi chỉ vì published_at khác")

    def test_republish_of_unchanged_build_id_does_not_move_published_at(self):
        rows, breadth, market_session = pd.validate_snapshot()
        first, _ = pd.compute_manifest(rows, breadth, market_session, "0" * 40, live=True)
        (self.tmp / "data" / "build_info.json").write_text(json.dumps(first), encoding="utf-8")

        second, _ = pd.compute_manifest(rows, breadth, market_session, "0" * 40, live=True)

        self.assertEqual(second["build_id"], first["build_id"],
                          "fixture không đổi giữa 2 lần gọi -- build_id phải giống nhau")
        self.assertEqual(second["published_at"], first["published_at"],
                          "republish nội dung không đổi không được sinh published_at mới")
        self.assertEqual(second["generated_at"], first["generated_at"])

    def test_new_content_after_a_publish_gets_its_own_new_published_at(self):
        # compute_published_at() directly, with two distinct injected clock readings --
        # asserting on real datetime.now(VN_TZ) output at second precision would be flaky
        # whenever both compute_manifest() calls land in the same wall-clock second.
        first_at = pd.compute_published_at(
            {}, "build-a", live=True, now=datetime(2026, 8, 7, 10, 0, 0, tzinfo=timezone.utc))
        second_at = pd.compute_published_at(
            {"build_id": "build-a", "published_at": first_at}, "build-b", live=True,
            now=datetime(2026, 8, 8, 10, 0, 0, tzinfo=timezone.utc))

        self.assertEqual(first_at, "2026-08-07T10:00:00+00:00")
        self.assertNotEqual(second_at, first_at,
                             "nội dung mới (build_id khác) phải được coi là một lần publish mới, "
                             "có published_at riêng")

    def test_legacy_manifest_without_published_at_key_fails_safe(self):
        rows, breadth, market_session = pd.validate_snapshot()
        first, _ = pd.compute_manifest(rows, breadth, market_session, "0" * 40)
        legacy = dict(first)
        legacy.pop("published_at", None)  # a build_info.json written before this patch existed
        (self.tmp / "data" / "build_info.json").write_text(json.dumps(legacy), encoding="utf-8")

        manifest, _ = pd.compute_manifest(rows, breadth, market_session, "0" * 40, live=True)

        self.assertEqual(manifest["build_id"], legacy["build_id"])
        self.assertIsNone(manifest["published_at"],
                           "manifest cũ thiếu published_at -- build_id không đổi nên vẫn phải là "
                           "None, không được raise KeyError")


class AnalysisLatestPublicationContractTests(_PublishDashboardTestBase):
    """analysis_latest.json publication contract -- closes the confirmed BACKEND_ROOT <->
    WEB_ROOT drift (operations-review/runtime_pipeline_publish_contract_audit_20260808.md;
    milestone: "analysis_latest.json Publication Contract Repair"). See
    docs/dashboard_release_session_contract.md's "closing the publication gap" section for
    the design this proves."""

    def test_included_in_whole_market_release_group_not_trusted_ai(self):
        self.assertIn("analysis_latest.json", pd.COPY_ARTIFACTS)
        self.assertIn("analysis_latest.json", pd.SAFE_WEB_ARTIFACTS)
        self.assertIn("analysis_latest.json", pd.BACKEND_SOURCED)
        self.assertIn("analysis_latest.json", pd.REQUIRED_SESSION_ARTIFACTS)
        self.assertIn("analysis_latest.json", pd.release_session_contract.ARTIFACT_SESSION_RULES)
        self.assertNotIn(
            "analysis_latest.json", TRUSTED_AI_RELEASE_ALLOWLIST,
            "belongs to the whole-market publisher (analysis.js/analysis.html consumer, "
            "stock_analyzer.py producer), not the static trusted-ai allowlist "
            "(analysis_bundle.json's own producer/consumer family)",
        )

    def test_source_to_destination_mapping(self):
        """Same relative name in BACKEND_ROOT and WEB_ROOT -- exactly what analysis.js's
        bare `ANALYSIS_URL = "analysis_latest.json"` fetch (no path prefix) requires."""
        self.assertEqual(pd.source_root("analysis_latest.json"), self.backend,
                          "must read the fresh BACKEND_ROOT generation, not a stale WEB_ROOT copy")
        (self.backend / "analysis_latest.json").write_text(
            json.dumps({"summary": {"session_date": "2026-07-17"}, "marker": "backend-fresh"}),
            encoding="utf-8")
        copied = pd.copy_public_artifacts()
        self.assertIn("analysis_latest.json", copied)
        self.assertEqual(
            json.loads((self.tmp / "analysis_latest.json").read_text(encoding="utf-8"))["marker"],
            "backend-fresh", "destination content must match the source that was just copied")

    def test_allowlist_permits_it_while_rejecting_unrelated_file(self):
        whitelist = pd.build_whitelist()
        self.assertIn("analysis_latest.json", whitelist)
        (self.tmp / "totally_unrelated_file.json").write_text("{}\n", encoding="utf-8")
        whitelist_after = pd.build_whitelist()
        self.assertIn("analysis_latest.json", whitelist_after)
        self.assertNotIn(
            "totally_unrelated_file.json", whitelist_after,
            "a file not referenced by any HTML/JS and not in SAFE_WEB_ARTIFACTS must never "
            "enter the whitelist merely by existing in WEB_ROOT")

    def test_protected_staging_rejects_a_pre_staged_unexpected_file(self):
        """publish_live()'s own guard: something already staged outside the whitelist before
        it runs must refuse the whole publish -- proves analysis_latest.json's addition to
        the whitelist did not loosen this pre-existing protection for anything else."""
        calls: list[tuple[str, ...]] = []

        def fake_git(*args, **kwargs):
            calls.append(args)
            if args == ("diff", "--cached", "--name-only"):
                return True, "unexpected_unrelated_file.txt"
            raise AssertionError(f"unexpected git call in this test: {args!r}")

        with mock.patch.object(pd, "git", side_effect=fake_git):
            rc = pd.publish_live(["analysis_latest.json", "dashboard.html"], "main")

        self.assertEqual(rc, 1)
        self.assertEqual(calls, [("diff", "--cached", "--name-only")],
                          "must stop at the pre-staged-file check -- never reach git add/commit")

    def test_missing_source_fails_closed_before_any_write(self):
        """Missing analysis_latest.json in BACKEND_ROOT must fail the whole publish, never
        silently proceed and leave WEB_ROOT's existing (possibly stale) copy untouched but
        unvalidated -- the required, not optional, half of the contract decision."""
        backend = Path(tempfile.mkdtemp(prefix="publish_dashboard_backend_"))
        self.addCleanup(shutil.rmtree, backend, ignore_errors=True)
        _write_backend_fixture(backend, "2026-08-07")
        (backend / "analysis_latest.json").unlink()
        pd.BACKEND_ROOT = backend

        before = self._all_files(exclude_logs=True)
        with mock.patch.object(pd, "copy_public_artifacts") as m_copy, \
             mock.patch.object(pd, "write_build_manifest") as m_manifest:
            rc = self._run(["publish_dashboard.py", "--live"])
        self.assertEqual(rc, 1)
        m_copy.assert_not_called()
        m_manifest.assert_not_called()
        after = self._all_files(exclude_logs=True)
        self.assertEqual(before, after,
                          "a required artifact missing from BACKEND_ROOT must fail closed, "
                          "never silently publish with WEB_ROOT's stale existing copy")

    def test_session_mismatched_source_fails_before_any_write(self):
        """One artifact silently lagging the rest of BACKEND_ROOT's own session must fail
        the publish before any copy/manifest/git write -- the exact shape a real partial or
        interrupted pipeline run could produce."""
        backend = Path(tempfile.mkdtemp(prefix="publish_dashboard_backend_"))
        self.addCleanup(shutil.rmtree, backend, ignore_errors=True)
        _write_backend_fixture(backend, "2026-08-07")
        (backend / "analysis_latest.json").write_text(
            json.dumps({"summary": {"session_date": "2026-08-06"}}), encoding="utf-8")
        pd.BACKEND_ROOT = backend

        before = self._all_files(exclude_logs=True)
        with mock.patch.object(pd, "copy_public_artifacts") as m_copy, \
             mock.patch.object(pd, "write_build_manifest") as m_manifest:
            rc = self._run(["publish_dashboard.py", "--live"])
        self.assertEqual(rc, 1)
        m_copy.assert_not_called()
        m_manifest.assert_not_called()
        after = self._all_files(exclude_logs=True)
        self.assertEqual(before, after, "session mismatch must leave WEB_ROOT untouched, even with --live")

    def test_stale_served_copy_is_replaced_with_source_equivalent_content_on_live_publish(self):
        """Reproduces the confirmed defect directly: served (WEB_ROOT) analysis_latest.json
        is old/stale; BACKEND_ROOT has newer valid content for a later session. Dry-run must
        plan to copy it; a live publish must leave WEB_ROOT's copy byte-identical to
        BACKEND_ROOT's -- the publisher copies, it does not reinterpret analysis content."""
        backend = Path(tempfile.mkdtemp(prefix="publish_dashboard_backend_"))
        self.addCleanup(shutil.rmtree, backend, ignore_errors=True)
        _write_backend_fixture(backend, "2026-08-07")
        pd.BACKEND_ROOT = backend

        stale = (self.tmp / "analysis_latest.json").read_bytes()
        fresh = (backend / "analysis_latest.json").read_bytes()
        self.assertNotEqual(stale, fresh, "fixture sanity: source and destination must start different")

        self.assertIn("analysis_latest.json", pd.plan_copy_artifacts(),
                       "dry-run plan must identify BACKEND_ROOT's fresher copy as the publish candidate")

        self.fake_git.status_output = " M analysis_latest.json\n"
        with mock.patch.object(pd, "run_release_smoke_tests", return_value=0), \
             mock.patch.object(pd, "publish_live", return_value=0):
            rc = self._run(["publish_dashboard.py", "--live"])
        self.assertEqual(rc, 0)

        self.assertEqual(
            (self.tmp / "analysis_latest.json").read_bytes(), fresh,
            "after a live publish, the served copy must be byte-equivalent to the validated source")

    def test_identical_source_and_destination_is_a_noop(self):
        backend = Path(tempfile.mkdtemp(prefix="publish_dashboard_backend_"))
        self.addCleanup(shutil.rmtree, backend, ignore_errors=True)
        _write_backend_fixture(backend, "2026-07-17")  # matches self.tmp's own fixture session
        (backend / "analysis_latest.json").write_bytes((self.tmp / "analysis_latest.json").read_bytes())
        pd.BACKEND_ROOT = backend

        self.assertNotIn("analysis_latest.json", pd.plan_copy_artifacts(),
                          "byte-identical source/destination must not be planned for copy")

        before_bytes = (self.tmp / "analysis_latest.json").read_bytes()
        before_mtime_ns = (self.tmp / "analysis_latest.json").stat().st_mtime_ns
        copied = pd.copy_public_artifacts()
        self.assertNotIn("analysis_latest.json", copied)
        self.assertEqual((self.tmp / "analysis_latest.json").read_bytes(), before_bytes)
        self.assertEqual((self.tmp / "analysis_latest.json").stat().st_mtime_ns, before_mtime_ns,
                          "no-op republish must not even rewrite identical bytes")


if __name__ == "__main__":
    unittest.main()
