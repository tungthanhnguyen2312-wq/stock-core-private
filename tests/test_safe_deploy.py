"""Tests for tools/safe_deploy.py — all synthetic temp git repos, never
touches production VNSTOCK/AI ANALYZE. Lives in tests/ so it's picked up by
the existing `python -m unittest discover tests` convention; safe_deploy.py
itself lives one level up in tools/, hence the parent.parent below.
Run directly with: python -m unittest tests.test_safe_deploy -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))
import safe_deploy as sd  # noqa: E402


def make_link(link: Path, target: Path, target_is_directory: bool) -> bool:
    """Best-effort: Windows directory junctions need no elevation, unlike
    symlinks (which normally do unless Developer Mode/admin). Try a
    junction first on Windows, fall back to os.symlink elsewhere / if
    mklink is unavailable for some reason. Returns False if neither works,
    so callers can skip cleanly instead of failing on locked-down hosts.
    """
    if os.name == "nt" and target_is_directory:
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            return True
    try:
        os.symlink(str(target), str(link), target_is_directory=target_is_directory)
        return True
    except (OSError, NotImplementedError):
        return False


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )


def make_source_repo(base: Path, files: dict[str, bytes], branch: str = "main") -> Path:
    repo = base / "source_repo"
    repo.mkdir(parents=True, exist_ok=True)
    _git(base, "init", "-b", branch, str(repo))
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    for rel, data in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")
    return repo


def write_config(base: Path, project: str, dest: Path, allowlist: list[str],
                  denylist: list[str] | None = None, runtime_scan_globs: list[str] | None = None,
                  size_limit_bytes: int | None = None, allowed_branches: list[str] | None = None) -> Path:
    cfg_path = base / "deploy_config.json"
    cfg = {
        "project": project,
        "runtime_destination": str(dest),
        "allowed_branches": allowed_branches or ["main"],
        "size_limit_bytes": size_limit_bytes or sd.DEFAULT_SIZE_LIMIT_BYTES,
        "allowlist": allowlist,
        "denylist": denylist or [],
        "runtime_scan_globs": runtime_scan_globs or allowlist,
    }
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    return cfg_path


class SafeDeployTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="safe_deploy_test_")
        self.base = Path(self._tmp)
        self.dest = self.base / "runtime"
        self.dest.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def run_tool(self, argv: list[str]) -> int:
        return sd.main(argv)

    def default_argv(self, repo: Path, cfg: Path, extra: list[str] | None = None) -> list[str]:
        # REPO_ROOT is a module-level constant computed from __file__ at
        # import time; tests monkeypatch it per-call to point at the
        # synthetic repo instead of the real tools/ directory.
        sd.REPO_ROOT = repo
        argv = ["--config", str(cfg)]
        return argv + (extra or [])


class UnchangedCreateUpdateTests(SafeDeployTestCase):
    def test_git_filtered_bytes_honor_explicit_eol_attributes(self):
        repo = make_source_repo(self.base, {
            ".gitattributes": b"*.py text eol=lf\n*.bat text eol=crlf\n",
            "run.py": b"print(1)\r\n",
            "build.bat": b"@echo off\nexit /b 0\n",
        })
        head = sd.git_head_commit(repo)
        self.assertEqual(sd.git_show_bytes(repo, head, "run.py"), b"print(1)\n")
        self.assertEqual(sd.git_show_bytes(repo, head, "build.bat"), b"@echo off\nexit /b 0\n")
        self.assertEqual(sd.git_filtered_bytes(repo, head, "run.py"), b"print(1)\n")
        self.assertEqual(sd.git_filtered_bytes(repo, head, "build.bat"), b"@echo off\r\nexit /b 0\r\n")

    def test_new_source_file_classified_as_create(self):
        repo = make_source_repo(self.base, {"run.py": b"print(1)\n"})
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        sd.REPO_ROOT = repo
        config = sd.DeployConfig.load(cfg)
        plan = sd.build_plan(repo, config, self.dest, {}, set(), "dry-run")
        rec = next(f for f in plan.files if f.rel_path == "run.py")
        self.assertEqual(rec.classification, "create")
        self.assertFalse((self.dest / "run.py").exists())  # dry-run: nothing written

    def test_unchanged_file_classified_correctly(self):
        repo = make_source_repo(self.base, {"run.py": b"print(1)\n"})
        (self.dest / "run.py").write_bytes(b"print(1)\n")
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        config = sd.DeployConfig.load(cfg)
        plan = sd.build_plan(repo, config, self.dest, {}, set(), "dry-run")
        rec = next(f for f in plan.files if f.rel_path == "run.py")
        self.assertEqual(rec.classification, "unchanged")

    def test_dry_run_does_not_modify_destination(self):
        repo = make_source_repo(self.base, {"run.py": b"print(1)\n"})
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        argv = self.default_argv(repo, cfg)
        rc = self.run_tool(argv)
        self.assertEqual(rc, 0)
        self.assertFalse((self.dest / "run.py").exists())

    def test_untracked_source_file_never_a_candidate(self):
        repo = make_source_repo(self.base, {"run.py": b"print(1)\n"})
        (repo / "untracked.py").write_bytes(b"print(2)\n")  # never git add'ed
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        config = sd.DeployConfig.load(cfg)
        plan = sd.build_plan(repo, config, self.dest, {}, set(), "dry-run")
        paths = [f.rel_path for f in plan.files]
        self.assertNotIn("untracked.py", paths)

    def test_gitignored_source_file_never_a_candidate(self):
        repo = make_source_repo(self.base, {"run.py": b"print(1)\n", ".gitignore": b"secret_local.py\n"})
        (repo / "secret_local.py").write_bytes(b"print(3)\n")
        # deliberately not git add'ed -- .gitignore makes it invisible to git ls-files
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        config = sd.DeployConfig.load(cfg)
        plan = sd.build_plan(repo, config, self.dest, {}, set(), "dry-run")
        paths = [f.rel_path for f in plan.files]
        self.assertNotIn("secret_local.py", paths)

    def test_excluded_not_allowlisted(self):
        repo = make_source_repo(self.base, {"run.py": b"x", "README.md": b"y"})
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])  # README.md not allowlisted
        config = sd.DeployConfig.load(cfg)
        plan = sd.build_plan(repo, config, self.dest, {}, set(), "dry-run")
        rec = next(f for f in plan.files if f.rel_path == "README.md")
        self.assertEqual(rec.classification, "excluded_not_allowlisted")


class DriftDetectionTests(SafeDeployTestCase):
    def test_safe_update_with_prior_deploy_state(self):
        repo = make_source_repo(self.base, {"run.py": b"v2\n"})
        (self.dest / "run.py").write_bytes(b"v1\n")  # what we deployed last time
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        config = sd.DeployConfig.load(cfg)
        state = {"files": {"run.py": sd.sha256_bytes(b"v1\n")}}  # last deploy put v1 there, runtime untouched since
        plan = sd.build_plan(repo, config, self.dest, state, set(), "dry-run")
        rec = next(f for f in plan.files if f.rel_path == "run.py")
        self.assertEqual(rec.classification, "update")
        self.assertIsNone(rec.block_reason)

    def test_runtime_drift_blocks(self):
        repo = make_source_repo(self.base, {"run.py": b"v2\n"})
        (self.dest / "run.py").write_bytes(b"hand-edited-in-production\n")
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        config = sd.DeployConfig.load(cfg)
        state = {"files": {"run.py": sd.sha256_bytes(b"v1\n")}}  # last deploy put v1, but runtime now has neither v1 nor v2
        plan = sd.build_plan(repo, config, self.dest, state, set(), "dry-run")
        rec = next(f for f in plan.files if f.rel_path == "run.py")
        self.assertEqual(rec.classification, "blocked")
        self.assertEqual(rec.block_reason, "runtime_drift")

    def test_initial_difference_blocked_without_approval(self):
        repo = make_source_repo(self.base, {"run.py": b"source-version\n"})
        (self.dest / "run.py").write_bytes(b"pre-existing-runtime-version\n")
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        config = sd.DeployConfig.load(cfg)
        plan = sd.build_plan(repo, config, self.dest, {}, set(), "dry-run")  # no prior state at all
        rec = next(f for f in plan.files if f.rel_path == "run.py")
        self.assertEqual(rec.classification, "blocked")
        self.assertEqual(rec.block_reason, "initial_difference_unapproved")

    def test_initial_difference_allowed_with_explicit_approval(self):
        repo = make_source_repo(self.base, {"run.py": b"source-version\n"})
        (self.dest / "run.py").write_bytes(b"pre-existing-runtime-version\n")
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        config = sd.DeployConfig.load(cfg)
        blocked = sd.build_plan(repo, config, self.dest, {}, {}, "dry-run")
        rec = next(f for f in blocked.files if f.rel_path == "run.py")
        approval = {"run.py": {"rel_path": "run.py", "source_commit": blocked.source_head,
                               "source_sha256": rec.source_sha256,
                               "expected_runtime_sha256": rec.runtime_sha256}}
        plan = sd.build_plan(repo, config, self.dest, {}, approval, "dry-run")
        rec = next(f for f in plan.files if f.rel_path == "run.py")
        self.assertEqual(rec.classification, "update")


class BlockingGuardTests(SafeDeployTestCase):
    def test_denylist_excludes_file_without_blocking_deploy(self):
        repo = make_source_repo(self.base, {"run.py": b"x", ".gitignore": b"*.pyc\n"})
        cfg = write_config(self.base, "proj", self.dest, ["*.py", ".gitignore"], denylist=[".gitignore"])
        config = sd.DeployConfig.load(cfg)
        plan = sd.build_plan(repo, config, self.dest, {}, set(), "dry-run")
        rec = next(f for f in plan.files if f.rel_path == ".gitignore")
        self.assertEqual(rec.classification, "excluded_denylisted")
        self.assertEqual(rec.block_reason, "denylist_match")
        self.assertEqual(plan.blocked(), [])

    def test_path_traversal_rejected(self):
        self.assertTrue(sd.match_pattern("../evil.py", "*.py") or True)  # sanity: pattern matching isn't the guard
        with self.assertRaises(sd.BlockedPathError):
            sd.resolve_dest_path(self.dest, "../evil.py")

    def test_oversized_file_blocked(self):
        big = b"x" * 100
        repo = make_source_repo(self.base, {"big.py": big})
        cfg = write_config(self.base, "proj", self.dest, ["*.py"], size_limit_bytes=10)
        config = sd.DeployConfig.load(cfg)
        plan = sd.build_plan(repo, config, self.dest, {}, set(), "dry-run")
        rec = next(f for f in plan.files if f.rel_path == "big.py")
        self.assertEqual(rec.classification, "blocked")
        self.assertEqual(rec.block_reason, "oversized")

    def test_secret_detected_blocks_file(self):
        repo = make_source_repo(self.base, {"cfg.py": b'API_KEY = "sk-abcdefghijklmnopqrstuvwx"\n'})
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        config = sd.DeployConfig.load(cfg)
        plan = sd.build_plan(repo, config, self.dest, {}, set(), "dry-run")
        rec = next(f for f in plan.files if f.rel_path == "cfg.py")
        self.assertEqual(rec.classification, "blocked")
        self.assertTrue(rec.block_reason.startswith("possible_secret"))

    def test_symlink_or_junction_detection_helper(self):
        target = self.base / "target_dir"
        target.mkdir()
        link = self.base / "link_dir"
        if not make_link(link, target, target_is_directory=True):
            self.skipTest("junction/symlink creation not permitted in this environment")
        self.assertTrue(sd.is_symlink_or_junction(link))
        self.assertFalse(sd.is_symlink_or_junction(target))

    def test_junction_in_destination_path_blocks_file(self):
        # A junction directory anywhere along the destination path must be
        # rejected unconditionally ("never follow"), not only when it
        # would redirect outside dest_root -- this uses mklink /J, which
        # (unlike file symlinks) needs no elevation on Windows, so it
        # actually runs instead of skipping in a normal dev environment.
        repo = make_source_repo(self.base, {"linked/run.py": b"x"})
        real_subdir = self.dest / "real_subdir"
        real_subdir.mkdir()
        junction_path = self.dest / "linked"
        if not make_link(junction_path, real_subdir, target_is_directory=True):
            self.skipTest("junction/symlink creation not permitted in this environment")
        cfg = write_config(self.base, "proj", self.dest, ["linked/**"])
        config = sd.DeployConfig.load(cfg)
        plan = sd.build_plan(repo, config, self.dest, {}, set(), "dry-run")
        rec = next(f for f in plan.files if f.rel_path == "linked/run.py")
        self.assertEqual(rec.classification, "blocked")
        self.assertEqual(rec.block_reason, "symlink_or_junction_in_path")

    def test_junction_escaping_dest_root_blocks_file(self):
        repo = make_source_repo(self.base, {"linked/run.py": b"x"})
        decoy = self.base / "decoy_outside_dest_root"
        decoy.mkdir()
        junction_path = self.dest / "linked"
        if not make_link(junction_path, decoy, target_is_directory=True):
            self.skipTest("junction/symlink creation not permitted in this environment")
        cfg = write_config(self.base, "proj", self.dest, ["linked/**"])
        config = sd.DeployConfig.load(cfg)
        plan = sd.build_plan(repo, config, self.dest, {}, set(), "dry-run")
        rec = next(f for f in plan.files if f.rel_path == "linked/run.py")
        self.assertEqual(rec.classification, "blocked")
        # Caught by the same unconditional in-path check before resolution
        # ever gets far enough to also trip the escape check.
        self.assertEqual(rec.block_reason, "symlink_or_junction_in_path")


class CliGateTests(SafeDeployTestCase):
    def test_apply_without_confirm_token_refused(self):
        repo = make_source_repo(self.base, {"run.py": b"x"})
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        argv = self.default_argv(repo, cfg, ["--apply"])
        rc = self.run_tool(argv)
        self.assertEqual(rc, 2)
        self.assertFalse((self.dest / "run.py").exists())

    def test_apply_with_wrong_confirm_token_refused(self):
        repo = make_source_repo(self.base, {"run.py": b"x"})
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        argv = self.default_argv(repo, cfg, ["--apply", "--confirm", "nope"])
        rc = self.run_tool(argv)
        self.assertEqual(rc, 2)
        self.assertFalse((self.dest / "run.py").exists())

    def test_dirty_tracked_tree_refused(self):
        repo = make_source_repo(self.base, {"run.py": b"x"})
        (repo / "run.py").write_bytes(b"dirty-uncommitted-edit")
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        argv = self.default_argv(repo, cfg)
        rc = self.run_tool(argv)
        self.assertEqual(rc, 2)

    def test_untracked_file_present_does_not_block_dry_run(self):
        # Mirrors SOURCE_BASELINE_ADDITIONS.sanitized.json being untracked
        # forever in both real private repos -- must not make the tool
        # permanently refuse to run.
        repo = make_source_repo(self.base, {"run.py": b"x"})
        (repo / "SOURCE_BASELINE_ADDITIONS.sanitized.json").write_bytes(b"{}")
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        argv = self.default_argv(repo, cfg)
        rc = self.run_tool(argv)
        self.assertEqual(rc, 0)

    def test_wrong_branch_refused(self):
        repo = make_source_repo(self.base, {"run.py": b"x"}, branch="not-main")
        cfg = write_config(self.base, "proj", self.dest, ["*.py"], allowed_branches=["main"])
        argv = self.default_argv(repo, cfg)
        rc = self.run_tool(argv)
        self.assertEqual(rc, 2)


class ApplyAndAtomicityTests(SafeDeployTestCase):
    def test_apply_writes_new_and_updated_files(self):
        repo = make_source_repo(self.base, {"run.py": b"new-content\n", "keep.py": b"same\n"})
        (self.dest / "keep.py").write_bytes(b"same\n")
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        argv = self.default_argv(repo, cfg, [
            "--apply", "--confirm", sd.CONFIRM_TOKEN,
            "--backup-root", str(self.base / "backups"),
        ])
        rc = self.run_tool(argv)
        self.assertEqual(rc, 0)
        self.assertEqual((self.dest / "run.py").read_bytes(), b"new-content\n")

    def test_apply_creates_backup_before_update(self):
        repo = make_source_repo(self.base, {"run.py": b"v2\n"})
        (self.dest / "run.py").write_bytes(b"v1\n")
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        config = sd.DeployConfig.load(cfg)
        sd.REPO_ROOT = repo
        state = {"files": {"run.py": sd.sha256_bytes(b"v1\n")}}
        plan = sd.build_plan(repo, config, self.dest, state, set(), "apply")
        backup_root = self.base / "backups"
        result = sd.apply_plan(repo, plan, self.dest, backup_root)
        self.assertEqual(len(result["backed_up"]), 1)
        backup_path = Path(result["backed_up"][0]["backup_path"])
        self.assertTrue(backup_path.exists())
        self.assertEqual(backup_path.read_bytes(), b"v1\n")
        self.assertEqual((self.dest / "run.py").read_bytes(), b"v2\n")

    def test_rollback_restores_from_backup(self):
        repo = make_source_repo(self.base, {"run.py": b"v2\n"})
        (self.dest / "run.py").write_bytes(b"v1\n")
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        config = sd.DeployConfig.load(cfg)
        sd.REPO_ROOT = repo
        state = {"files": {"run.py": sd.sha256_bytes(b"v1\n")}}
        plan = sd.build_plan(repo, config, self.dest, state, set(), "apply")
        backup_root = self.base / "backups"
        result = sd.apply_plan(repo, plan, self.dest, backup_root)
        self.assertEqual((self.dest / "run.py").read_bytes(), b"v2\n")
        # rollback: restore the pre-deploy backup over the runtime file
        backup_path = Path(result["backed_up"][0]["backup_path"])
        shutil.copy2(backup_path, self.dest / "run.py")
        self.assertEqual((self.dest / "run.py").read_bytes(), b"v1\n")
        self.assertEqual(sd.sha256_file(self.dest / "run.py"), sd.sha256_bytes(b"v1\n"))

    def test_apply_aborts_entirely_if_any_file_blocked(self):
        repo = make_source_repo(self.base, {"run.py": b"new\n", "big.py": b"x" * 100})
        cfg = write_config(self.base, "proj", self.dest, ["*.py"], size_limit_bytes=10)
        argv = self.default_argv(repo, cfg, [
            "--apply", "--confirm", sd.CONFIRM_TOKEN,
            "--backup-root", str(self.base / "backups"),
        ])
        rc = self.run_tool(argv)
        self.assertEqual(rc, 2)
        self.assertFalse((self.dest / "run.py").exists())  # nothing written, even the non-blocked file

    def test_runtime_only_file_never_deleted(self):
        repo = make_source_repo(self.base, {"run.py": b"x"})
        (self.dest / "runtime_only.py").write_bytes(b"exists-only-in-runtime\n")
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        argv = self.default_argv(repo, cfg, [
            "--apply", "--confirm", sd.CONFIRM_TOKEN,
            "--backup-root", str(self.base / "backups"),
        ])
        rc = self.run_tool(argv)
        self.assertEqual(rc, 0)
        self.assertTrue((self.dest / "runtime_only.py").exists())
        self.assertEqual((self.dest / "runtime_only.py").read_bytes(), b"exists-only-in-runtime\n")

    def test_runtime_only_reported_in_plan(self):
        repo = make_source_repo(self.base, {"run.py": b"x"})
        (self.dest / "runtime_only.py").write_bytes(b"y")
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        config = sd.DeployConfig.load(cfg)
        plan = sd.build_plan(repo, config, self.dest, {}, set(), "dry-run")
        self.assertIn("runtime_only.py", plan.runtime_only_files)

    def test_runtime_only_scan_ignores_pycache_noise(self):
        repo = make_source_repo(self.base, {"tests/test_x.py": b"x"})
        cache_dir = self.dest / "tests" / "__pycache__"
        cache_dir.mkdir(parents=True)
        (cache_dir / "test_x.cpython-313.pyc").write_bytes(b"bytecode")
        (self.dest / "tests" / "genuinely_orphaned.py").write_bytes(b"y")
        cfg = write_config(self.base, "proj", self.dest, ["tests/**"])
        config = sd.DeployConfig.load(cfg)
        plan = sd.build_plan(repo, config, self.dest, {}, set(), "dry-run")
        self.assertIn("tests/genuinely_orphaned.py", plan.runtime_only_files)
        self.assertTrue(all("__pycache__" not in f for f in plan.runtime_only_files))
        self.assertTrue(all(not f.endswith(".pyc") for f in plan.runtime_only_files))

    def test_atomic_write_leaves_no_temp_file_on_success(self):
        target = self.dest / "atomic_test.txt"
        sd.atomic_write(target, b"payload")
        self.assertEqual(target.read_bytes(), b"payload")
        leftovers = [p for p in self.dest.iterdir() if p.name.startswith(".safe_deploy_tmp_")]
        self.assertEqual(leftovers, [])

    def test_state_not_written_during_dry_run(self):
        repo = make_source_repo(self.base, {"run.py": b"x"})
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        state_file = self.base / "state.json"
        argv = self.default_argv(repo, cfg, ["--state-file", str(state_file)])
        rc = self.run_tool(argv)
        self.assertEqual(rc, 0)
        self.assertFalse(state_file.exists())

    def test_state_written_after_successful_apply(self):
        repo = make_source_repo(self.base, {"run.py": b"x"})
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        state_file = self.base / "state.json"
        argv = self.default_argv(repo, cfg, [
            "--apply", "--confirm", sd.CONFIRM_TOKEN,
            "--state-file", str(state_file),
            "--backup-root", str(self.base / "backups"),
        ])
        rc = self.run_tool(argv)
        self.assertEqual(rc, 0)
        self.assertTrue(state_file.exists())
        data = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertIn("run.py", data["files"])


class ManifestTests(SafeDeployTestCase):
    def test_dry_run_writes_preview_manifest(self):
        repo = make_source_repo(self.base, {"run.py": b"x"})
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        preview_dir = self.base / "previews"
        argv = self.default_argv(repo, cfg, ["--preview-dir", str(preview_dir)])
        rc = self.run_tool(argv)
        self.assertEqual(rc, 0)
        manifests = list(preview_dir.glob("deploy-preview-*.json"))
        self.assertEqual(len(manifests), 1)
        data = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(data["mode"], "dry-run")
        self.assertIn("summary", data)
        self.assertIn("files", data)

    def test_dry_run_manifest_previews_backup_and_rollback_for_updates(self):
        repo = make_source_repo(self.base, {"run.py": b"v2\n"})
        (self.dest / "run.py").write_bytes(b"v1\n")
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        config = sd.DeployConfig.load(cfg)
        sd.REPO_ROOT = repo
        state = {"files": {"run.py": sd.sha256_bytes(b"v1\n")}}
        backup_root = self.base / "would-be-backups"
        plan = sd.build_plan(repo, config, self.dest, state, set(), "dry-run", backup_root)
        manifest = plan.to_manifest_dict()
        self.assertEqual(len(manifest["backup_and_rollback_preview"]), 1)
        entry = manifest["backup_and_rollback_preview"][0]
        self.assertEqual(entry["rel_path"], "run.py")
        self.assertTrue(entry["would_backup_to"].startswith(str(backup_root)))
        self.assertEqual((self.dest / "run.py").read_bytes(), b"v1\n")  # build_plan() never writes


class SecurityCriticalRegressionTests(SafeDeployTestCase):
    def _plan(self, files, runtime=None, state=None, approvals=None):
        repo = make_source_repo(self.base, files)
        for rel, data in (runtime or {}).items():
            path = self.dest / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        cfg = write_config(self.base, "proj", self.dest, ["*.py", "*.bat", "nested/**"])
        config = sd.DeployConfig.load(cfg)
        plan = sd.build_plan(repo, config, self.dest, state or {}, approvals or {}, "apply",
                             self.base / "backups")
        return repo, config, plan

    def test_filtered_bytes_ignore_machine_autocrlf_but_honor_attributes(self):
        repo = make_source_repo(self.base, {
            ".gitattributes": b"*.py text eol=lf\n*.bat text eol=crlf\n",
            "run.py": b"x\n", "build.bat": b"@echo off\n",
        })
        head = sd.git_head_commit(repo)
        for value in ("true", "false"):
            _git(repo, "config", "core.autocrlf", value)
            self.assertEqual(sd.git_filtered_bytes(repo, head, "run.py"), b"x\n")
            self.assertEqual(sd.git_filtered_bytes(repo, head, "build.bat"), b"@echo off\r\n")

    def test_bound_approval_accepts_only_exact_commit_and_hashes(self):
        repo, config, blocked = self._plan({"run.py": b"source\n"}, {"run.py": b"runtime\n"})
        rec = next(r for r in blocked.files if r.rel_path == "run.py")
        approval = {"run.py": {
            "rel_path": "run.py", "source_commit": blocked.source_head,
            "source_sha256": rec.source_sha256, "expected_runtime_sha256": rec.runtime_sha256,
        }}
        approved = sd.build_plan(repo, config, self.dest, {}, approval, "apply", self.base / "backups")
        self.assertEqual(next(r for r in approved.files if r.rel_path == "run.py").classification, "update")
        approval["run.py"]["source_sha256"] = "0" * 64
        mismatch = sd.build_plan(repo, config, self.dest, {}, approval, "apply", self.base / "backups")
        self.assertEqual(next(r for r in mismatch.files if r.rel_path == "run.py").block_reason,
                         "approval_source_hash_mismatch")
        approval["run.py"]["source_sha256"] = rec.source_sha256
        approval["run.py"]["expected_runtime_sha256"] = "f" * 64
        mismatch = sd.build_plan(repo, config, self.dest, {}, approval, "apply", self.base / "backups")
        self.assertEqual(next(r for r in mismatch.files if r.rel_path == "run.py").block_reason,
                         "approval_runtime_hash_mismatch")

    def test_eol_only_difference_uses_filtered_deploy_bytes(self):
        repo = make_source_repo(self.base, {
            ".gitattributes": b"*.py text eol=lf\n*.bat text eol=crlf\n",
            "run.py": b"x\r\n", "build.bat": b"@echo off\n",
        })
        (self.dest / "run.py").write_bytes(b"x\n")
        (self.dest / "build.bat").write_bytes(b"@echo off\r\n")
        cfg = write_config(self.base, "proj", self.dest, ["*.py", "*.bat"])
        plan = sd.build_plan(repo, sd.DeployConfig.load(cfg), self.dest, {}, {}, "dry-run")
        self.assertEqual({r.rel_path: r.classification for r in plan.files if r.source_sha256},
                         {"build.bat": "unchanged", "run.py": "unchanged"})

    def test_source_head_change_after_plan_blocks_apply(self):
        repo, _, plan = self._plan({"run.py": b"v1\n"})
        (repo / "run.py").write_bytes(b"v2\n")
        _git(repo, "add", "run.py"); _git(repo, "commit", "-m", "v2")
        with self.assertRaisesRegex(sd.DeployError, "source HEAD changed"):
            sd.apply_plan(repo, plan, self.dest, self.base / "backups")
        self.assertFalse((self.dest / "run.py").exists())

    def test_runtime_change_after_plan_blocks_apply(self):
        old = b"old\n"; state = {"files": {"run.py": sd.sha256_bytes(old)}}
        repo, _, plan = self._plan({"run.py": b"new\n"}, {"run.py": old}, state)
        (self.dest / "run.py").write_bytes(b"drift\n")
        with self.assertRaisesRegex(sd.DeployError, "runtime changed after planning"):
            sd.apply_plan(repo, plan, self.dest, self.base / "backups")
        self.assertEqual((self.dest / "run.py").read_bytes(), b"drift\n")

    def test_corrupt_and_stale_state_are_fatal(self):
        path = self.base / "state.json"; path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(sd.DeployError):
            sd.load_deploy_state(path, "proj", self.dest)
        path.write_text(json.dumps({"project": "other", "runtime_destination": str(self.dest), "files": {}}), encoding="utf-8")
        with self.assertRaises(sd.DeployError):
            sd.load_deploy_state(path, "proj", self.dest)

    def test_second_file_failure_rolls_back_first_and_writes_manifest(self):
        repo, _, plan = self._plan({"a.py": b"a\n", "b.py": b"b\n"})
        real_atomic = sd.atomic_write
        def fail_second(path, data):
            if Path(path).name == "b.py":
                raise OSError("injected replace failure")
            return real_atomic(path, data)
        with mock.patch.object(sd, "atomic_write", side_effect=fail_second):
            with self.assertRaises(sd.DeployError):
                sd.apply_plan(repo, plan, self.dest, self.base / "backups")
        self.assertFalse((self.dest / "a.py").exists())
        manifests = list((self.base / "backups").rglob("deploy-result.json"))
        self.assertEqual(len(manifests), 1)
        self.assertEqual(json.loads(manifests[0].read_text(encoding="utf-8"))["result"], "rolled_back_after_failure")

    def test_backup_failure_does_not_replace_runtime(self):
        old = b"old\n"; state = {"files": {"run.py": sd.sha256_bytes(old)}}
        repo, _, plan = self._plan({"run.py": b"new\n"}, {"run.py": old}, state)
        with mock.patch.object(sd, "backup_file", side_effect=OSError("backup denied")):
            with self.assertRaises(sd.DeployError):
                sd.apply_plan(repo, plan, self.dest, self.base / "backups")
        self.assertEqual((self.dest / "run.py").read_bytes(), old)

    def test_state_write_failure_rolls_back_runtime(self):
        repo = make_source_repo(self.base, {"run.py": b"new\n"})
        cfg = write_config(self.base, "proj", self.dest, ["*.py"])
        argv = self.default_argv(repo, cfg, ["--apply", "--confirm", sd.CONFIRM_TOKEN,
                    "--backup-root", str(self.base / "backups"), "--state-file", str(self.base / "state.json")])
        with mock.patch.object(sd, "save_deploy_state", side_effect=OSError("state denied")):
            self.assertEqual(self.run_tool(argv), 2)
        self.assertFalse((self.dest / "run.py").exists())

    def test_deploy_manifest_write_failure_rolls_back_runtime(self):
        repo, _, plan = self._plan({"run.py": b"new\n"})
        real_atomic = sd.atomic_write
        def fail_manifest(path, data):
            if Path(path).name == "deploy-result.json":
                raise OSError("manifest denied")
            return real_atomic(path, data)
        with mock.patch.object(sd, "atomic_write", side_effect=fail_manifest):
            with self.assertRaises(sd.DeployError):
                sd.apply_plan(repo, plan, self.dest, self.base / "backups")
        self.assertFalse((self.dest / "run.py").exists())

    def test_junction_created_after_plan_is_rechecked(self):
        repo, _, plan = self._plan({"nested/run.py": b"x\n"})
        real = self.base / "real"; real.mkdir()
        if not make_link(self.dest / "nested", real, True):
            self.skipTest("junction creation unavailable")
        with self.assertRaises(sd.DeployError):
            sd.apply_plan(repo, plan, self.dest, self.base / "backups")
        self.assertFalse((real / "run.py").exists())

    def test_unicode_and_long_paths_apply(self):
        rel = "nested/" + ("x" * 120) + "_đ.py"
        repo, _, plan = self._plan({rel: b"ok\n"})
        sd.apply_plan(repo, plan, self.dest, self.base / "backups")
        self.assertEqual((self.dest / rel).read_bytes(), b"ok\n")

    def test_case_only_collision_is_blocked(self):
        repo, config, _ = self._plan({"nested/A.py": b"a"})
        with mock.patch.object(sd, "git_ls_files", return_value=["nested/A.py", "nested/a.py"]):
            plan = sd.build_plan(repo, config, self.dest, {}, {}, "dry-run")
        collisions = [r for r in plan.files if r.block_reason == "case_path_collision"]
        self.assertEqual({r.rel_path for r in collisions}, {"nested/A.py", "nested/a.py"})

    def test_rollback_blocks_runtime_modified_after_deploy(self):
        old = b"old\n"; state = {"files": {"run.py": sd.sha256_bytes(old)}}
        repo, _, plan = self._plan({"run.py": b"new\n"}, {"run.py": old}, state)
        result = sd.apply_plan(repo, plan, self.dest, self.base / "backups")
        (self.dest / "run.py").write_bytes(b"edited\n")
        with self.assertRaisesRegex(sd.DeployError, "rollback drift"):
            sd.rollback_deployment(Path(result["manifest_path"]), self.dest)
        self.assertEqual((self.dest / "run.py").read_bytes(), b"edited\n")


if __name__ == "__main__":
    unittest.main()
