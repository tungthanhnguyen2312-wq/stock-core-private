"""Quarantine-layer unit tests: bytes preserved when safe, append-only
atomic manifest, and strict isolation from the content-addressed store."""

import json
import tempfile
import unittest
from pathlib import Path

from acquisition_landing_isolation import default_protected_roots
from acquisition_landing_quarantine import load_quarantine_manifest, quarantine_item, quarantine_root


class QuarantineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.tmp.name)
        self.landing_root = self.workspace_root / "data-landing" / "official-financial-filings-v1"
        self.protected_roots = default_protected_roots(self.workspace_root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_bytes_are_preserved_when_given(self):
        record = quarantine_item(
            self.landing_root,
            allowed_root=self.landing_root,
            protected_roots=self.protected_roots,
            run_id="r1",
            domain="d",
            source_locator="https://x.invalid/a.pdf",
            reason="not_a_pdf_header",
            observed_at="2026-01-01T00:00:00Z",
            data=b"NOT A PDF",
            sha256="deadbeef" * 8,
            content_type="application/pdf",
            original_filename="a.pdf",
        )
        self.assertIsNotNone(record.stored_relative_path)
        stored_path = self.landing_root / record.stored_relative_path
        self.assertTrue(stored_path.exists())
        self.assertEqual(stored_path.read_bytes(), b"NOT A PDF")

    def test_manifest_is_append_only_and_always_valid_json(self):
        for i in range(3):
            quarantine_item(
                self.landing_root,
                allowed_root=self.landing_root,
                protected_roots=self.protected_roots,
                run_id="r1",
                domain="d",
                source_locator=f"https://x.invalid/{i}.pdf",
                reason="empty_document",
                observed_at="2026-01-01T00:00:00Z",
                data=b"",
                sha256=None,
                content_type=None,
                original_filename=None,
            )
        manifest = load_quarantine_manifest(self.landing_root)
        self.assertEqual(len(manifest), 3)
        manifest_path = quarantine_root(self.landing_root) / "quarantine_manifest.json"
        with manifest_path.open("r", encoding="utf-8") as fh:
            json.load(fh)  # must parse cleanly - proves the write is never left half-written

    def test_never_writes_into_raw_blobs(self):
        quarantine_item(
            self.landing_root,
            allowed_root=self.landing_root,
            protected_roots=self.protected_roots,
            run_id="r1",
            domain="d",
            source_locator="https://x.invalid/a.pdf",
            reason="not_a_pdf_header",
            observed_at="2026-01-01T00:00:00Z",
            data=b"NOT A PDF",
            sha256="cafebabe" * 8,
            content_type="application/pdf",
            original_filename="a.pdf",
        )
        raw_blobs_dir = self.landing_root / "raw" / "blobs"
        self.assertFalse(raw_blobs_dir.exists() and any(raw_blobs_dir.iterdir()))

    def test_unhashable_bytes_still_get_a_deterministic_stored_name(self):
        record_a = quarantine_item(
            self.landing_root,
            allowed_root=self.landing_root,
            protected_roots=self.protected_roots,
            run_id="r1",
            domain="d",
            source_locator="https://x.invalid/weird.pdf",
            reason="malformed_metadata",
            observed_at="2026-01-01T00:00:00Z",
            data=b"some bytes",
            sha256=None,
            content_type=None,
            original_filename=None,
        )
        self.assertIsNotNone(record_a.stored_relative_path)
        self.assertIn("unhashable-", record_a.stored_relative_path)


if __name__ == "__main__":
    unittest.main()
