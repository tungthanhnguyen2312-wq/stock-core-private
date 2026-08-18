"""Protected-root isolation tests. assert_write_allowed performs pure path
logic and no filesystem I/O, so the real absolute protected-root paths can
be used directly as inputs without ever touching those directories."""

import tempfile
import unittest
from pathlib import Path

from acquisition_landing_contract import ProtectedRootWriteError
from acquisition_landing_isolation import assert_write_allowed, default_protected_roots

class RealProtectedRootsAreRejectedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.tmp.name).resolve()
        self.protected_roots = default_protected_roots(self.workspace_root)
        self.allowed_root = self.workspace_root / "data-landing" / "official-financial-filings-v1"

    def tearDown(self):
        self.tmp.cleanup()

    def test_dashboard_runtime_rejected(self):
        target = self.workspace_root / "dashboard-runtime" / "vn_stock.db"
        with self.assertRaises(ProtectedRootWriteError):
            assert_write_allowed(target, allowed_root=self.allowed_root, protected_roots=self.protected_roots)

    def test_dashboard_runtime_nested_official_evidence_rejected(self):
        target = self.workspace_root / "dashboard-runtime" / "data" / "official-evidence" / "manifest.json"
        with self.assertRaises(ProtectedRootWriteError):
            assert_write_allowed(target, allowed_root=self.allowed_root, protected_roots=self.protected_roots)

    def test_ai_runtime_rejected(self):
        target = self.workspace_root / "ai-runtime" / "exports" / "context_packages" / "x.json"
        with self.assertRaises(ProtectedRootWriteError):
            assert_write_allowed(target, allowed_root=self.allowed_root, protected_roots=self.protected_roots)

    def test_ai_core_private_rejected(self):
        target = self.workspace_root / "ai-core-private" / "builders" / "evil.py"
        with self.assertRaises(ProtectedRootWriteError):
            assert_write_allowed(target, allowed_root=self.allowed_root, protected_roots=self.protected_roots)

    def test_publish_rejected(self):
        target = self.workspace_root / "publish" / "evil.html"
        with self.assertRaises(ProtectedRootWriteError):
            assert_write_allowed(target, allowed_root=self.allowed_root, protected_roots=self.protected_roots)

    def test_primary_stock_core_private_checkout_rejected(self):
        target = self.workspace_root / "stock-core-private" / "evil.py"
        with self.assertRaises(ProtectedRootWriteError):
            assert_write_allowed(target, allowed_root=self.allowed_root, protected_roots=self.protected_roots)

    def test_governed_evidence_source_root_rejected_via_extra_protected_paths(self):
        governed_root = (
            self.workspace_root / "stock-core-private" / "operations-review" / "governed-official-evidence-v1"
        )
        target = governed_root / "official_document_acquisition_manifest.json"
        with self.assertRaises(ProtectedRootWriteError):
            assert_write_allowed(
                target,
                allowed_root=self.allowed_root,
                protected_roots=self.protected_roots,
                extra_protected_paths=(governed_root,),
            )

    def test_vn_stock_db_filename_rejected_even_under_an_unrelated_directory(self):
        target = self.workspace_root / "data-landing" / "official-financial-filings-v1" / "vn_stock.db"
        with self.assertRaises(ProtectedRootWriteError):
            assert_write_allowed(target, allowed_root=self.allowed_root, protected_roots=self.protected_roots)

    def test_case_insensitive_protected_root_match(self):
        target = Path(str(self.workspace_root).upper()) / "DASHBOARD-RUNTIME" / "vn_stock.db"
        with self.assertRaises(ProtectedRootWriteError):
            assert_write_allowed(target, allowed_root=self.allowed_root, protected_roots=self.protected_roots)


class AllowedRootTests(unittest.TestCase):
    def test_path_under_allowed_root_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            allowed_root = Path(tmp) / "data-landing" / "official-financial-filings-v1"
            protected_roots = default_protected_roots(tmp)
            target = allowed_root / "raw" / "blobs" / "abc.pdf"
            resolved = assert_write_allowed(target, allowed_root=allowed_root, protected_roots=protected_roots)
            self.assertEqual(resolved, target.resolve())

    def test_path_outside_allowed_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            allowed_root = Path(tmp) / "data-landing" / "official-financial-filings-v1"
            protected_roots = default_protected_roots(tmp)
            target = Path(tmp) / "elsewhere" / "abc.pdf"
            with self.assertRaises(ProtectedRootWriteError):
                assert_write_allowed(target, allowed_root=allowed_root, protected_roots=protected_roots)

    def test_path_traversal_out_of_allowed_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            allowed_root = Path(tmp) / "data-landing" / "official-financial-filings-v1"
            protected_roots = default_protected_roots(tmp)
            (Path(tmp) / "dashboard-runtime").mkdir(parents=True, exist_ok=True)
            target = allowed_root / ".." / ".." / "dashboard-runtime" / "evil.db"
            with self.assertRaises(ProtectedRootWriteError):
                assert_write_allowed(target, allowed_root=allowed_root, protected_roots=protected_roots)


if __name__ == "__main__":
    unittest.main()
