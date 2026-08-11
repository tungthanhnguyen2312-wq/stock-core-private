import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import evidence_promotion as promotion
from official_evidence import load_cited_financial_records


class OfficialEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.evidence = self.root / "data" / "official-evidence"
        self.evidence.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_manifest(self, record):
        (self.evidence / "manifest.json").write_text(
            json.dumps({"schema_version": "1.0.0", "records": [record]}), encoding="utf-8")

    def _write_citation(self, *, ticker="ABC", metric="net_income", evidence_id="e1", value=42):
        citation = promotion.build_financial_identity_citation(
            ticker=ticker, metric=metric, reporting_period="2024", value=value, evidence_id=evidence_id,
            citation="PDF page 1.", extraction={"method": "document_line_item", "source_pages": [1],
                                                   "raw_labels": ["Net income"]},
        )
        (self.evidence / "financial_identity_citations.jsonl").write_text(
            json.dumps(citation) + "\n", encoding="utf-8")
        return citation

    def _record(self, document, *, ticker="ABC", evidence_id="e1", archive_document_path=None, sha256=None):
        return {"evidence_id": evidence_id, "ticker": ticker, "reporting_period": "2024",
                "qualification_state": "qualified", "filename": document.name,
                "sha256": sha256 or hashlib.sha256(document.read_bytes()).hexdigest(),
                **({"archive_document_path": str(archive_document_path)} if archive_document_path is not None else {})}

    def test_flat_path_citation_resolves_and_preserves_canonical_provenance(self):
        document = self.evidence / "official.pdf"
        document.write_bytes(b"flat authoritative document")
        self._write_manifest(self._record(document))
        citation = self._write_citation()

        result = load_cited_financial_records(self.root, "ABC")

        self.assertEqual(result["status"], "available")
        self.assertEqual(len(result["records"]), 1)
        record = result["records"][0]
        self.assertEqual(record["canonical_metric"], "net_income")
        self.assertEqual(record["period_identity"], {"fiscal_year": 2024, "fiscal_quarter": None,
                         "period_type": "annual", "period_end": "2024-12-31",
                         "report_published_at": None, "period": "2024"})
        self.assertEqual(record["statement_scope"], citation["statement_scope"])
        self.assertEqual(record["currency"], citation["currency"])
        self.assertEqual(record["unit_scale"], citation["unit_scale"])
        self.assertEqual(record["official_evidence"]["evidence_id"], citation["evidence_id"])
        self.assertEqual(record["official_evidence"]["citation_id"], citation["citation_id"])
        self.assertEqual(record["official_evidence"]["extraction"], citation["extraction"])

    def test_explicit_archive_path_resolves_without_a_flat_copy(self):
        archive = Path(__file__).resolve().parents[1] / "operations-review" / "test-evidence" / "archive.pdf"
        archive.parent.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: archive.parent.rmdir() if archive.parent.exists() else None)
        self.addCleanup(lambda: archive.unlink(missing_ok=True))
        archive.write_bytes(b"archive authoritative document")
        self._write_manifest(self._record(archive, archive_document_path=archive.relative_to(Path(__file__).resolve().parents[1])))
        self._write_citation()

        result = load_cited_financial_records(self.root, "ABC")

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["records"][0]["value"], 42)

    def test_missing_referenced_file_fails_closed(self):
        missing = self.evidence / "missing.pdf"
        self._write_manifest(self._record(missing, sha256="0" * 64))
        self._write_citation()

        result = load_cited_financial_records(self.root, "ABC")

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["records"], [])

    def test_archive_path_never_falls_back_to_same_named_flat_file(self):
        flat = self.evidence / "collision.pdf"
        flat.write_bytes(b"flat collision")
        missing_archive = Path("operations-review") / "test-evidence" / "collision.pdf"
        self._write_manifest(self._record(flat, archive_document_path=missing_archive))
        self._write_citation()

        result = load_cited_financial_records(self.root, "ABC")

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["records"], [])

    def test_document_hash_mismatch_fails_closed(self):
        document = self.evidence / "tampered.pdf"
        document.write_bytes(b"actual")
        self._write_manifest(self._record(document, sha256="f" * 64))
        self._write_citation()

        result = load_cited_financial_records(self.root, "ABC")

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["records"], [])

    def test_missing_manifest_registration_is_rejected(self):
        registered = self.evidence / "registered.pdf"
        registered.write_bytes(b"registered document")
        self._write_manifest(self._record(registered, evidence_id="another"))
        self._write_citation(evidence_id="unregistered")

        result = load_cited_financial_records(self.root, "ABC")

        self.assertEqual(result["status"], "unavailable")
        self.assertIn({"key": ("ABC", "net_income", "2024"), "reason": "evidence_missing_or_hash_mismatch",
                       "authority_status": "document_not_registered_in_authority"}, result["rejected"])

    def test_loader_has_no_hpg_specific_branch(self):
        document = self.evidence / "generic.pdf"
        document.write_bytes(b"generic document")
        self._write_manifest(self._record(document, ticker="ZZZ"))
        self._write_citation(ticker="ZZZ")

        result = load_cited_financial_records(self.root, "ZZZ")

        self.assertEqual(result["status"], "available")
        self.assertNotIn("HPG", Path(__file__).resolve().parents[1].joinpath("official_evidence.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
