"""Focused contract tests for the bounded SSI FY2024 issuer evidence path."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import evidence_promotion as promotion  # noqa: E402
import semantic_evidence_bridge as bridge  # noqa: E402
import ssi_official_financial_materialization as milestone  # noqa: E402


class SsiOfficialFinancialMaterializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "documents" / "SSI" / "2024" / "audited_annual_financial_statements" / "SSI.pdf"
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"SSI audited fixture")
        self.record = {
            "ticker": "SSI", "document_id": "ssi-document", "sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
            "relative_path": self.path.relative_to(self.root).as_posix(), "acquisition_status": "retained",
            "source_authority": "SSI Securities Corporation investor relations", "source_id": "issuer_ir",
            "canonical_url": "https://www.ssi.com.vn/fy2024.pdf", "document_class": "audited_annual_financial_statements",
            "reporting_period": "2024", "published_at": "2025-03-20", "observed_at": "2026-07-30T00:00:00Z",
        }
        (self.root / "official_document_acquisition_manifest.json").write_text(json.dumps({"records": [self.record]}), encoding="utf-8")

    def _materialization(self) -> dict:
        text = "CONSOLIDATED STATEMENT OF FINANCIAL POSITION Currency: VND Current liabilities 46,599,438,522,989"
        return {"ticker": "SSI", "document_id": self.record["document_id"], "document_sha256": self.record["sha256"],
                "pages": [{"page": 10, "document_id": self.record["document_id"], "document_sha256": self.record["sha256"],
                           "status": "ocr_available", "text": text, "text_sha256": "page-text", "citation_id": "page-citation",
                           "materialization_id": "materialization", "ocr_engine": "tesseract fixture", "render_dpi": 288}]}

    def test_only_direct_current_liabilities_is_promoted_and_hash_verified(self) -> None:
        with patch.object(milestone, "SSI_FY2024_SHA256", self.record["sha256"]), \
             patch.object(milestone, "render_and_ocr", return_value=self._materialization()):
            milestone.materialize_ssi_current_liabilities(self.root)
            manifests, citations = milestone.build_ssi_promotion(self.root)
        self.assertEqual([citation["metric"] for citation in citations], ["current_liabilities"])
        promotion.promote(self.root, manifest_records=manifests, citation_relative=promotion.FINANCIAL_IDENTITY_RELATIVE,
                          citation_records=citations, dry_run=False)
        verified = bridge.load_verified_financial_identities(self.root)
        self.assertEqual(verified["rejected"], [])
        self.assertEqual(verified["by_key"][("SSI", "current_liabilities", "2024")]["value"], milestone.CURRENT_LIABILITIES)

    def test_missing_or_mismatched_sidecar_fails_closed(self) -> None:
        with patch.object(milestone, "SSI_FY2024_SHA256", self.record["sha256"]):
            with self.assertRaisesRegex(ValueError, "SSI_MATERIALIZATION_REQUIRED"):
                milestone.build_ssi_promotion(self.root)
        sidecar = self.root / milestone.MATERIALIZATION_ROOT / "ssi-fy2024-current-liabilities.json"
        sidecar.parent.mkdir(parents=True)
        sidecar.write_text(json.dumps({"document_id": "wrong", "document_sha256": "wrong"}), encoding="utf-8")
        with patch.object(milestone, "SSI_FY2024_SHA256", self.record["sha256"]):
            with self.assertRaisesRegex(ValueError, "SSI_SIDECAR_DOCUMENT_MISMATCH"):
                milestone.build_ssi_promotion(self.root)


if __name__ == "__main__":
    unittest.main()
