"""Focused fixtures for the bounded QNS/POW issuer-evidence milestone."""
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

import canonical_financial_qualification_policy as policy  # noqa: E402
import evidence_promotion as promotion  # noqa: E402
import official_annual_financial_fact_projection as annual  # noqa: E402
import qns_pow_official_financial_materialization as milestone  # noqa: E402
import research_financial_fact_projection as research  # noqa: E402
from qualified_historical_fundamental_analytics import build as build_historical  # noqa: E402
from ticker_capability import build_ticker_capability_matrix  # noqa: E402


class QnsPowOfficialFinancialMaterializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pow = self._record("POW", b"pow-audited-consolidated")
        self.qns = self._record("QNS", b"qns-report-package")
        (self.root / "official_document_acquisition_manifest.json").write_text(
            json.dumps({"records": [self.pow, self.qns]}), encoding="utf-8")

    def _record(self, ticker: str, body: bytes) -> dict:
        path = self.root / "documents" / ticker / "2024" / "audited_annual_financial_statements" / f"{ticker}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return {
            "ticker": ticker, "document_id": f"{ticker.lower()}-document", "sha256": hashlib.sha256(body).hexdigest(),
            "relative_path": path.relative_to(self.root).as_posix(), "acquisition_status": "retained",
            "source_authority": f"{ticker} investor relations", "source_id": "issuer_ir",
            "canonical_url": f"https://issuer.example/{ticker}.pdf", "document_class": "audited_annual_financial_statements",
            "reporting_period": "2024", "published_at": "2025-03-31", "observed_at": "2026-08-09T00:00:00Z",
        }

    def _pow_materialization(self) -> dict:
        rows = []
        for _, _, page, label, value, _, _, _ in milestone.POW_FACTS:
            rows.append({"page": page, "document_id": self.pow["document_id"], "document_sha256": self.pow["sha256"],
                         "status": "ocr_available", "text": f"{label} {value}", "text_sha256": f"text-{page}",
                         "citation_id": f"page-citation-{page}", "materialization_id": f"materialization-{page}",
                         "ocr_engine": "tesseract fixture", "render_dpi": 288})
        debt_text = " ".join(f"{part['ocr_label']} {part['ocr_raw_value']}" for part in milestone.POW_DEBT)
        rows[1] = {**rows[1], "text": rows[1]["text"] + " " + debt_text}
        return {"document_id": self.pow["document_id"], "document_sha256": self.pow["sha256"], "ticker": "POW",
                "ocr_engine": "tesseract fixture", "pages": rows}

    def test_qns_package_without_statement_pages_blocks_without_ocr(self) -> None:
        native = {"source_page_count": 75, "pages": [{"text": "BÁO CÁO TÀI CHÍNH"}]}
        with patch.object(milestone, "QNS_SHA256", self.qns["sha256"]), \
             patch.object(milestone, "extract_pdf_text", return_value=native) as extract:
            result = milestone.inspect_qns(self.root)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["reason"], "AUDITED_CONSOLIDATED_STATEMENT_SECTION_MISSING")
        extract.assert_called_once()

    def test_pow_five_citations_qualify_but_unknown_entity_stays_blocked(self) -> None:
        materialization = self._pow_materialization()
        with patch.object(milestone, "POW_SHA256", self.pow["sha256"]), \
             patch.object(milestone, "render_and_ocr", return_value=materialization):
            milestone.materialize_pow(self.root)
            manifests, citations = milestone.build_pow_promotion(self.root)
        self.assertEqual({row["metric"] for row in citations}, set(research.CORPORATE_REQUIRED_METRICS))
        self.assertEqual(next(row for row in citations if row["metric"] == "total_interest_bearing_debt")["value"], 22_659_403_275_451)
        promotion.promote(self.root, manifest_records=manifests, citation_relative=promotion.FINANCIAL_IDENTITY_RELATIVE,
                          citation_records=citations, dry_run=False)
        facts = annual.facts_for_ticker(self.root, "POW")
        evidence = policy.load_evidence_index(self.root)
        self.assertEqual(len(facts), 5)
        self.assertTrue(all(policy.evaluate_fact(fact, evidence_index=evidence)["status"] == "qualified" for fact in facts))
        blocked = research.build_projection("POW", facts, entity_type="unknown", entity_authority="unknown", evidence_index=evidence)
        self.assertFalse(blocked["research_eligible"])
        available = research.build_projection("POW", facts, entity_type="corporate", entity_authority="fixture", evidence_index=evidence)
        self.assertTrue(available["research_eligible"])
        historical = build_historical("POW", available["research_financial_canonical"])
        self.assertEqual(historical["trend_status"], "insufficient_history")
        matrix = build_ticker_capability_matrix("POW", {"entity_type": "unknown", "research_financial_fact_projection": blocked}, market_authority={})
        self.assertFalse(matrix["is_actionable"])

    def test_wrong_hash_and_cross_ticker_reuse_fail_closed(self) -> None:
        with patch.object(milestone, "POW_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "RETAINED_SOURCE_NOT_QUALIFIED"):
                milestone.materialize_pow(self.root)
        evidence_id = promotion._hash({"ticker": "QNS", "document_sha256": self.qns["sha256"], "document_id": self.qns["document_id"]})
        manifest = promotion.build_manifest_record(evidence_id=evidence_id, archive_document_path=self.root / self.qns["relative_path"],
                                                   sha256=self.qns["sha256"], filename="QNS.pdf", ticker="QNS")
        citation = promotion.build_financial_identity_citation(ticker="POW", metric="net_income", reporting_period="2024",
                                                               value=1, evidence_id=evidence_id)
        promotion.promote(self.root, manifest_records=[manifest], citation_relative=promotion.FINANCIAL_IDENTITY_RELATIVE,
                          citation_records=[citation], dry_run=False)
        self.assertEqual(annual.facts_for_ticker(self.root, "POW"), [])


if __name__ == "__main__":
    unittest.main()
