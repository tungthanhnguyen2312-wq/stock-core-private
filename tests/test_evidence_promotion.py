# ==========================================================================
# Focused tests for evidence_promotion.py (P0.2: approved evidence write
# boundary). Synthetic temp-dir fixtures only -- no real data, no
# dashboard-runtime access. Verifies append-only, idempotent, hash-verified
# promotion through the real semantic_evidence_bridge.py loader.
# Run: `python -m unittest tests.test_evidence_promotion` from the repo root.
# ==========================================================================

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import evidence_promotion as promotion  # noqa: E402
import semantic_evidence_bridge as bridge  # noqa: E402


class EvidencePromotionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.doc_dir = self.root / "staging"
        self.doc_dir.mkdir(parents=True)
        self.doc_path = self.doc_dir / "notice.html"
        self.doc_path.write_bytes(b"<html>VSD notice 177392 test fixture</html>")
        self.sha256 = hashlib.sha256(self.doc_path.read_bytes()).hexdigest()
        self.evidence_id = promotion._hash({"filename": "notice.html", "sha256": self.sha256, "ticker": "VNM"})

    def _manifest_record(self) -> dict:
        return promotion.build_manifest_record(
            evidence_id=self.evidence_id, archive_document_path=self.doc_path, sha256=self.sha256,
            filename="notice.html",
            authority="Vietnam Securities Depository", ticker="VNM", issuer="Vietnam Dairy Products JSC",
            evidence_type="depository_notice", source_url="https://vsd.vn/en/ad/177392",
            reporting_period="2024",
        )

    def _citation_record(self) -> dict:
        return promotion.build_cash_dividend_citation(
            ticker="VNM", resolution_number="15/NQ-CTS.HDQT/2024", declaration_date="2024-12-05",
            cash_amount=500, currency="VND", evidence_id=self.evidence_id,
            record_date="2024-12-27", payment_date="2025-02-28", event_status="completed",
            citation="VSD notice 177392: 500 VND per share, record date 2024-12-27",
            verified_at="2026-08-02T00:00:00+07:00",
        )

    def test_build_manifest_record_rejects_hash_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            promotion.build_manifest_record(
                evidence_id="x", archive_document_path=self.doc_path, sha256="0" * 64, filename="notice.html",
            )

    def test_build_manifest_record_rejects_missing_file(self) -> None:
        with self.assertRaises(ValueError):
            promotion.build_manifest_record(
                evidence_id="x", archive_document_path=self.doc_dir / "missing.html", sha256=self.sha256,
                filename="missing.html",
            )

    def test_build_manifest_record_rejects_missing_filename(self) -> None:
        with self.assertRaises(ValueError):
            promotion.build_manifest_record(
                evidence_id="x", archive_document_path=self.doc_path, sha256=self.sha256, filename="",
            )

    def test_dry_run_writes_nothing(self) -> None:
        result = promotion.promote(
            self.root, manifest_records=[self._manifest_record()],
            citation_relative=promotion.CASH_DIVIDEND_RELATIVE, citation_records=[self._citation_record()],
            dry_run=True,
        )
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["manifest_added"], 1)
        self.assertEqual(result["citation_added"], 1)
        self.assertFalse((self.root / promotion.MANIFEST_RELATIVE).exists())
        self.assertFalse((self.root / promotion.CASH_DIVIDEND_RELATIVE).exists())

    def test_promote_then_reload_through_real_bridge(self) -> None:
        result = promotion.promote(
            self.root, manifest_records=[self._manifest_record()],
            citation_relative=promotion.CASH_DIVIDEND_RELATIVE, citation_records=[self._citation_record()],
            dry_run=False,
        )
        self.assertEqual(result["status"], "promoted")
        self.assertEqual(result["manifest_added"], 1)
        self.assertEqual(result["citation_added"], 1)

        loaded = bridge.load_verified_cash_dividends(self.root)
        self.assertEqual(loaded["status"], "available")
        self.assertEqual(loaded["rejected"], [])
        self.assertEqual(len(loaded["events"]), 1)
        event = loaded["events"][0]
        self.assertEqual(event["ticker"], "VNM")
        self.assertEqual(event["cash_amount"], 500.0)
        self.assertEqual(event["currency"], "VND")

    def test_promote_is_idempotent(self) -> None:
        manifest_record, citation_record = self._manifest_record(), self._citation_record()
        first = promotion.promote(
            self.root, manifest_records=[manifest_record],
            citation_relative=promotion.CASH_DIVIDEND_RELATIVE, citation_records=[citation_record],
            dry_run=False,
        )
        second = promotion.promote(
            self.root, manifest_records=[manifest_record],
            citation_relative=promotion.CASH_DIVIDEND_RELATIVE, citation_records=[citation_record],
            dry_run=False,
        )
        self.assertEqual(first["manifest_added"], 1)
        self.assertEqual(second["manifest_added"], 0)
        self.assertEqual(second["manifest_skipped_existing"], 1)
        self.assertEqual(first["citation_added"], 1)
        self.assertEqual(second["citation_added"], 0)
        self.assertEqual(second["citation_skipped_existing"], 1)

        manifest = json.loads((self.root / promotion.MANIFEST_RELATIVE).read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["records"]), 1)
        citations = (self.root / promotion.CASH_DIVIDEND_RELATIVE).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len([c for c in citations if c.strip()]), 1)

    def test_promote_never_removes_unrelated_existing_records(self) -> None:
        other_doc = self.doc_dir / "other.pdf"
        other_doc.write_bytes(b"unrelated evidence fixture")
        other_sha = hashlib.sha256(other_doc.read_bytes()).hexdigest()
        preexisting = promotion.build_manifest_record(
            evidence_id="preexisting-id", archive_document_path=other_doc, sha256=other_sha,
            filename="other.pdf", ticker="HPG",
        )
        promotion.promote(self.root, manifest_records=[preexisting], dry_run=False)
        promotion.promote(self.root, manifest_records=[self._manifest_record()], dry_run=False)

        manifest = json.loads((self.root / promotion.MANIFEST_RELATIVE).read_text(encoding="utf-8"))
        evidence_ids = {r["evidence_id"] for r in manifest["records"]}
        self.assertIn("preexisting-id", evidence_ids)
        self.assertIn(self.evidence_id, evidence_ids)
        self.assertEqual(len(manifest["records"]), 2)


if __name__ == "__main__":
    unittest.main()
