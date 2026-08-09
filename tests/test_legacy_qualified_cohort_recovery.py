"""Focused proof for the bounded legacy citation recovery contract and VNM slice."""
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
import legacy_qualified_cohort_recovery as recovery  # noqa: E402
import official_annual_financial_fact_projection as annual  # noqa: E402
import research_financial_fact_projection as research  # noqa: E402
import semantic_evidence_bridge as bridge  # noqa: E402


class LegacyQualifiedCohortRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        records, filings = [], {}
        for ticker in recovery.LEGACY_TICKERS:
            path = self.root / "documents" / ticker / "2024" / "annual_report" / f"{ticker}.pdf"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"{ticker} retained official filing".encode())
            record = {"ticker": ticker, "document_id": f"{ticker.lower()}-document", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "relative_path": path.relative_to(self.root).as_posix(), "acquisition_status": "retained",
                      "reporting_period": "2024", "source_authority": f"{ticker} investor relations",
                      "canonical_url": f"https://issuer.example/{ticker}.pdf", "document_class": "annual_report",
                      "published_at": "2025-03-15", "observed_at": "2026-08-09T00:00:00Z"}
            records.append(record)
            filings[ticker] = record["sha256"]
        (self.root / "official_document_acquisition_manifest.json").write_text(json.dumps({"records": records}), encoding="utf-8")
        self.filings = filings

    def _materialization(self) -> dict:
        by_page = {}
        for _, _, page, label, value, _ in recovery.VNM_FACTS:
            row = by_page.setdefault(page, {"page": page, "document_id": "vnm-document", "document_sha256": self.filings["VNM"],
                                             "status": "ocr_available", "text": "", "text_sha256": f"text-{page}",
                                             "citation_id": f"citation-{page}", "materialization_id": f"materialization-{page}",
                                             "ocr_engine": "tesseract fixture", "render_dpi": 288})
            row["text"] += f" {label} {value}"
        by_page[92]["text"] += " Borrowings 9,115,435 Borrowings 157,904"
        rows = list(by_page.values())
        return {"ticker": "VNM", "document_id": "vnm-document", "document_sha256": self.filings["VNM"], "pages": rows}

    def test_contract_is_exactly_five_retained_filings_and_excludes_served_outputs(self) -> None:
        with patch.object(recovery, "LEGACY_FILINGS", self.filings):
            contract = recovery.recovery_contract(self.root)
        self.assertEqual(contract["tickers"], ["HPG", "VNM", "PAN", "PVD", "NVL"])
        self.assertEqual(contract["restoration_sources"], "retained_official_filings_only")
        self.assertFalse(contract["comparison_outputs_permitted_as_evidence"])
        self.assertEqual(set(contract["documents"]), set(recovery.LEGACY_TICKERS))

    def test_vnm_five_fresh_citations_qualify_in_temporary_evidence_only(self) -> None:
        with patch.object(recovery, "LEGACY_FILINGS", self.filings), \
             patch.object(recovery, "render_and_ocr", return_value=self._materialization()):
            recovery.materialize_vnm(self.root)
            manifests, citations = recovery.build_vnm_promotion(self.root)
        self.assertEqual({citation["metric"] for citation in citations}, research.CORPORATE_REQUIRED_METRICS)
        self.assertTrue(all(citation["unit_scale"] == 1_000_000 for citation in citations))
        promotion.promote(self.root, manifest_records=manifests, citation_relative=promotion.FINANCIAL_IDENTITY_RELATIVE,
                          citation_records=citations, dry_run=False)
        verified = bridge.load_verified_financial_identities(self.root)
        self.assertEqual(verified["rejected"], [])
        facts = annual.facts_for_ticker(self.root, "VNM")
        evidence = policy.load_evidence_index(self.root)
        self.assertEqual(len(facts), 5)
        self.assertTrue(all(policy.evaluate_fact(fact, evidence_index=evidence)["status"] == "qualified" for fact in facts))
        projection = research.build_projection("VNM", facts, entity_type="corporate", entity_authority="manual_profile",
                                               evidence_index=evidence)
        self.assertTrue(projection["research_eligible"])
        self.assertEqual(projection["selected_reporting_period"], "2024")

    def test_hash_mismatch_and_out_of_scope_ticker_fail_closed(self) -> None:
        with patch.object(recovery, "LEGACY_FILINGS", self.filings):
            (self.root / "documents" / "VNM" / "2024" / "annual_report" / "VNM.pdf").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "RETAINED_FILING_HASH_MISMATCH:VNM"):
                recovery.retained_filing(self.root, "VNM")
            with self.assertRaisesRegex(ValueError, "LEGACY_TICKER_OUT_OF_SCOPE"):
                recovery.retained_filing(self.root, "POW")

    def test_remaining_contract_is_fixed_to_four_tickers_and_five_identity_shapes(self) -> None:
        self.assertEqual(set(recovery.REMAINING_RETAINED_FILINGS), {
            "HPG_FY2022", "HPG_FY2023", "HPG_FY2024", "PAN_FY2024_AUDITED",
            "PAN_FY2024_ANNUAL_REPORT", "PVD_FY2022", "PVD_FY2023", "PVD_FY2024", "NVL_FY2024",
        })
        self.assertEqual(set(recovery.REMAINING_FY2024_SPECS), {"HPG", "PAN", "PVD", "NVL"})
        for ticker, spec in recovery.REMAINING_FY2024_SPECS.items():
            self.assertEqual({fact[0] for fact in spec["facts"]} | {"total_interest_bearing_debt"},
                             research.CORPORATE_REQUIRED_METRICS, ticker)
            self.assertEqual({item[-1] for item in spec["debt"]}, {
                "short_term_borrowings", "long_term_borrowings_or_finance_leases"}, ticker)

    def test_existing_evidence_id_with_changed_payload_fails_closed(self) -> None:
        target = self.root / "data" / "official-evidence"
        target.mkdir(parents=True)
        (target / "manifest.json").write_text(json.dumps({"schema_version": "official_evidence_manifest/v1",
                                                            "records": [{"evidence_id": "same", "value": 1}]}),
                                             encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "LEGACY_PROMOTION_EXISTING_EVIDENCE_CONFLICT:same"):
            recovery._assert_append_compatible(self.root, [{"evidence_id": "same", "value": 2}], [])


if __name__ == "__main__":
    unittest.main()
