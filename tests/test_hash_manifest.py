# ==========================================================================
# Focused tests for tools/hash_manifest.py (P0.3: hash-manifest for large
# untracked operations-review trees). Synthetic temp-dir fixtures only.
# Run: `python -m unittest tests.test_hash_manifest` from the repo root.
# ==========================================================================

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import hash_manifest as hm  # noqa: E402


class HashManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "sub").mkdir()
        (self.root / "a.txt").write_bytes(b"hello")
        (self.root / "sub" / "b.pdf").write_bytes(b"world" * 100)

    def test_build_manifest_covers_all_files_deterministically(self) -> None:
        m1 = hm.build_manifest(self.root, label="test")
        m2 = hm.build_manifest(self.root, label="test")
        self.assertEqual(m1["file_count"], 2)
        self.assertEqual(m1["total_bytes"], 5 + 500)
        paths1 = [e["path"] for e in m1["entries"]]
        paths2 = [e["path"] for e in m2["entries"]]
        self.assertEqual(paths1, paths2, "entry order must be deterministic across runs")
        self.assertEqual({e["sha256"] for e in m1["entries"]}, {e["sha256"] for e in m2["entries"]})

    def test_verify_manifest_clean_tree_has_no_issues(self) -> None:
        manifest = hm.build_manifest(self.root)
        issues = hm.verify_manifest(self.root, manifest)
        self.assertEqual(issues, [])

    def test_verify_manifest_detects_hash_mismatch(self) -> None:
        manifest = hm.build_manifest(self.root)
        (self.root / "a.txt").write_bytes(b"tampered")
        issues = hm.verify_manifest(self.root, manifest)
        reasons = {i["reason"] for i in issues}
        self.assertIn("hash_mismatch", reasons)

    def test_verify_manifest_detects_missing_file(self) -> None:
        manifest = hm.build_manifest(self.root)
        (self.root / "a.txt").unlink()
        issues = hm.verify_manifest(self.root, manifest)
        reasons = {i["reason"] for i in issues}
        self.assertIn("missing_on_disk", reasons)

    def test_verify_manifest_detects_new_untracked_file(self) -> None:
        manifest = hm.build_manifest(self.root)
        (self.root / "new.txt").write_bytes(b"surprise")
        issues = hm.verify_manifest(self.root, manifest)
        reasons = {i["reason"] for i in issues}
        self.assertIn("present_on_disk_not_in_manifest", reasons)


if __name__ == "__main__":
    unittest.main()
