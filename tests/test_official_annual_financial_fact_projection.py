"""Issuer-document annual research inputs remain bounded, cited, and fail closed."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import evidence_promotion as promotion  # noqa: E402
import official_annual_financial_fact_projection as annual  # noqa: E402
import research_financial_fact_projection as research  # noqa: E402
import semantic_evidence_bridge as bridge  # noqa: E402


class OfficialAnnualFinancialFactProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        document = self.root / "retained" / "pan-fy2024.pdf"
        document.parent.mkdir()
        document.write_bytes(b"PAN FY2024 consolidated audited fixture")
        sha256 = hashlib.sha256(document.read_bytes()).hexdigest()
        self.evidence_id = promotion._hash({"ticker": "PAN", "document_sha256": sha256, "document_id": "pan-fy2024"})
        self.manifest = promotion.build_manifest_record(
            evidence_id=self.evidence_id, archive_document_path=document, sha256=sha256,
            filename=document.name, ticker="PAN", authority="PAN investor relations",
            source_url="https://issuer.example/PAN-2024.pdf", document_id="pan-fy2024",
            document_class="audited_annual_financial_statements", reporting_period="2024",
            published_at="2025-03-31", observed_at="2026-08-09T00:00:00Z",
        )

    def _citation(self, metric: str, value: int) -> dict:
        labels = {
            "operating_cash_flow": "Net cash used in operating activities",
            "net_income": "Net profit after corporate income tax",
            "cash_and_equivalents": "Cash and cash equivalents",
            "shareholders_equity": "Total equity",
        }
        page = {"operating_cash_flow": 13, "net_income": 12, "cash_and_equivalents": 8,
                "shareholders_equity": 11}.get(metric, 10)
        extraction = {"method": "document_line_item", "source_pages": [page],
                      "raw_labels": [labels[metric]]} if metric in labels else {
            "method": "document_line_item_sum", "source_pages": [10],
            "raw_labels": ["Short-term loans and obligations under finance leases",
                           "Long-term loans and obligations under finance leases"],
            "components": [
                {"label": "Short-term loans and obligations under finance leases", "value": 11_493_025_595_010},
                {"label": "Long-term loans and obligations under finance leases", "value": 206_652_925_496},
            ],
        }
        return promotion.build_financial_identity_citation(
            ticker="PAN", metric=metric, reporting_period="2024", value=value,
            evidence_id=self.evidence_id, citation=f"PDF page {page}; audited consolidated FY2024.",
            verified_at="2026-08-09T00:00:00Z", extraction=extraction,
        )

    def _promote(self, missing: str | None = None) -> None:
        values = {
            "operating_cash_flow": -1_739_184_049_701,
            "net_income": 1_167_068_107_309,
            "cash_and_equivalents": 2_958_874_263_351,
            "total_interest_bearing_debt": 11_699_678_520_506,
            "shareholders_equity": 8_859_450_516_042,
        }
        records = [self._citation(metric, value) for metric, value in values.items() if metric != missing]
        promotion.promote(self.root, manifest_records=[self.manifest],
                          citation_relative=promotion.FINANCIAL_IDENTITY_RELATIVE,
                          citation_records=records, dry_run=False)

    def test_five_hash_verified_annual_facts_qualify_for_corporate_research(self) -> None:
        self._promote()
        facts = annual.facts_for_ticker(self.root, "PAN")
        result = research.build_projection("PAN", facts, entity_type="corporate", entity_authority="issuer_profile")

        self.assertEqual(len(facts), 5)
        self.assertEqual(result["status"], "available")
        self.assertTrue(result["research_eligible"])
        debt = next(fact for fact in facts if fact["canonical_metric"] == "total_interest_bearing_debt")
        self.assertEqual(debt["value"], 11_699_678_520_506)
        self.assertEqual(debt["extraction"]["method"], "document_line_item_sum")
        self.assertTrue(debt["source_observation_ids"])

    def test_missing_or_invalid_issuer_evidence_cannot_create_eligibility(self) -> None:
        self._promote(missing="cash_and_equivalents")
        facts = annual.facts_for_ticker(self.root, "PAN")
        result = research.build_projection("PAN", facts, entity_type="corporate", entity_authority="issuer_profile")
        self.assertFalse(result["research_eligible"])
        self.assertEqual(result["status"], "unavailable")

    def test_unbalanced_document_component_sum_is_rejected_before_projection(self) -> None:
        bad_extraction = {
            "method": "document_line_item_sum", "source_pages": [10],
            "raw_labels": ["Short-term loans", "Long-term loans"],
            "components": [
                {"label": "Short-term loans", "value": 11_493_025_595_010},
                {"label": "Long-term loans", "value": 206_652_925_497},
            ],
        }
        citation = promotion.build_financial_identity_citation(
            ticker="PAN", metric="total_interest_bearing_debt", reporting_period="2024",
            value=11_699_678_520_506, evidence_id=self.evidence_id,
            citation="PDF page 10; audited consolidated FY2024.", extraction=bad_extraction,
        )
        promotion.promote(self.root, manifest_records=[self.manifest],
                          citation_relative=promotion.FINANCIAL_IDENTITY_RELATIVE,
                          citation_records=[citation], dry_run=False)
        rejected = bridge.load_verified_financial_identities(self.root)["rejected"]
        self.assertIn({"key": ("PAN", "total_interest_bearing_debt", "2024"),
                       "reason": "invalid_extraction_metadata"}, rejected)

    def test_another_ticker_cannot_reuse_pan_artifact_evidence(self) -> None:
        citation = promotion.build_financial_identity_citation(
            ticker="FPT", metric="net_income", reporting_period="2024", value=1,
            evidence_id=self.evidence_id, citation="PDF page 1.",
            extraction={"method": "document_line_item", "source_pages": [1],
                        "raw_labels": ["Net income"]},
        )
        promotion.promote(self.root, manifest_records=[self.manifest],
                          citation_relative=promotion.FINANCIAL_IDENTITY_RELATIVE,
                          citation_records=[citation], dry_run=False)
        self.assertIn({"key": ("FPT", "net_income", "2024"),
                       "reason": "evidence_ticker_mismatch"},
                      bridge.load_verified_financial_identities(self.root)["rejected"])

if __name__ == "__main__":
    unittest.main()
