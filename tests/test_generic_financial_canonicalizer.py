"""Unit tests for Phase 2 / P2-B: Generic Financial Statement Canonicalization & Retained-Evidence Scale-Out."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from generic_financial_canonicalizer import (
    CONTRACT_VERSION,
    SCHEMA_VERSION,
    ARTIFACT_TYPE,
    EvidenceClassification,
    LegacyModuleRole,
    canonicalize_citation,
    classify_evidence_candidate,
    classify_legacy_materializers,
    execute_generic_canonicalization,
)


class TestGenericFinancialCanonicalizer(unittest.TestCase):

    def setUp(self):
        self.sample_citations = [
            {
                "ticker": "HPG", "metric": "net_income", "reporting_period": "2024",
                "value": 11986478931123, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_ni_2024",
                "evidence_id": "e_hpg_2024", "published_at": "2025-03-24",
                "verified_at": "2026-08-09T00:00:00Z", "document_sha256": "304a93a65e1587f625e0045d6ec9bcfba6647d19df4034cfd8fc1ec7b62eeb64",
                "citation": "Lợi nhuận sau thuế TNDN: 11.986.478.931.123",
            },
            {
                "ticker": "PVD", "metric": "net_income", "reporting_period": "2023",
                "value": 23061808, "currency": "USD", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_pvd_ni_2023",
                "evidence_id": "e_pvd_2023", "published_at": "2024-03-25",
                "verified_at": "2026-08-09T00:00:00Z", "document_sha256": "ba70100acf9391a85992e67ebc1a3d68da33e50402a17e860f579e320f5f2d14",
                "citation": "Net profit after tax: 23,061,808",
            },
            {
                "ticker": "VCB", "metric": "total_interest_bearing_debt", "reporting_period": "2024",
                "value": 1000000, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_vcb_debt",
                "evidence_id": "e_vcb", "published_at": "2025-04-20",
                "verified_at": "2026-08-09T00:00:00Z",
            },
        ]

        self.sample_manifest = [
            {
                "ticker": "HPG", "reporting_period": "2024",
                "document_class": "audited_annual_financial_statements",
                "sha256": "304a93a65e1587f625e0045d6ec9bcfba6647d19df4034cfd8fc1ec7b62eeb64",
            },
            {
                "ticker": "VCB", "reporting_period": "2024",
                "document_class": "annual_report",
                "sha256": "9deccc3518e23302d00353b4d371a9dd251b67b12f9fe58a4da4ad3c727e99f8",
            },
            {
                "ticker": "SSI", "reporting_period": "2024",
                "document_class": "audited_annual_financial_statements",
                "sha256": "38e5b9ba2fc951120be813b09df05fa2d8b152b3b95443c6cd108de8abf03b74",
            },
            {
                "ticker": "PAN", "reporting_period": "2025",
                "document_class": "agm_document_or_resolution",
                "sha256": "21982c2f0c755875e6783fd7970d8e69e1526edf2e0ee752b08d337bfbfcc19d",
            },
            {
                "ticker": "PNJ", "reporting_period": "2024",
                "document_class": "audited_annual_financial_statements",
                "sha256": "71eb69f97fab83a36ed3dca032193cfc24754f416d24d4ad136f198ab2a73099",
            },
        ]

        self.entity_profiles = {
            "HPG": "corporate",
            "PVD": "corporate",
            "VCB": "bank",
            "SSI": "securities",
            "PAN": "corporate",
            "PNJ": "corporate",
        }

    def test_ticker_independent_canonicalization(self):
        """Canonicalization logic applies identically to any corporate ticker."""
        fact_hpg = canonicalize_citation(self.sample_citations[0], entity_type="corporate")
        fact_pvd = canonicalize_citation(self.sample_citations[1], entity_type="corporate")

        self.assertEqual(fact_hpg.canonical_metric, "net_income")
        self.assertEqual(fact_hpg.statement_family, "income_statement")
        self.assertEqual(fact_hpg.temporal_nature, "duration")
        self.assertEqual(fact_hpg.currency, "VND")
        self.assertEqual(fact_hpg.qualification_state, "QUALIFIED")

        self.assertEqual(fact_pvd.canonical_metric, "net_income")
        self.assertEqual(fact_pvd.currency, "USD")
        self.assertEqual(fact_pvd.qualification_state, "QUALIFIED")

    def test_sector_specialized_fail_closed(self):
        """Financial intermediaries fail closed on corporate debt metrics."""
        fact_vcb = canonicalize_citation(self.sample_citations[2], entity_type="bank")
        self.assertEqual(fact_vcb.qualification_state, "NOT_APPLICABLE")
        self.assertEqual(fact_vcb.applicability_state, "NOT_APPLICABLE")
        self.assertIn("SECTOR_INAPPROPRIATE_FINANCIAL_INTERMEDIARY_DEBT_RATIO", fact_vcb.reason_codes)

    def test_evidence_classification_rules(self):
        """Documents are deterministically classified according to structure and sector."""
        # Audited corporate statement -> GENERICALLY_CANONICALIZABLE
        cls_hpg, _ = classify_evidence_candidate(self.sample_manifest[0], entity_profiles=self.entity_profiles)
        self.assertEqual(cls_hpg, EvidenceClassification.GENERICALLY_CANONICALIZABLE)

        # Bank annual report -> SECTOR_SPECIALIZED
        cls_vcb, _ = classify_evidence_candidate(self.sample_manifest[1], entity_profiles=self.entity_profiles)
        self.assertEqual(cls_vcb, EvidenceClassification.SECTOR_SPECIALIZED)

        # Securities statement -> SECTOR_SPECIALIZED
        cls_ssi, _ = classify_evidence_candidate(self.sample_manifest[2], entity_profiles=self.entity_profiles)
        self.assertEqual(cls_ssi, EvidenceClassification.SECTOR_SPECIALIZED)

        # AGM document -> INSUFFICIENT_EVIDENCE
        cls_pan_agm, _ = classify_evidence_candidate(self.sample_manifest[3], entity_profiles=self.entity_profiles)
        self.assertEqual(cls_pan_agm, EvidenceClassification.INSUFFICIENT_EVIDENCE)

        # PNJ Debt Note in review -> INSUFFICIENT_MAPPING
        cls_pnj, _ = classify_evidence_candidate(self.sample_manifest[4], entity_profiles=self.entity_profiles)
        self.assertEqual(cls_pnj, EvidenceClassification.INSUFFICIENT_MAPPING)

    def test_legacy_materializer_classification_audit(self):
        """Legacy materializers are audited and classified without ambiguity."""
        roles = classify_legacy_materializers()
        self.assertIn("fpt_fy2025_official_financial_materialization.py", roles)
        self.assertEqual(roles["fpt_fy2025_official_financial_materialization.py"]["role"], LegacyModuleRole.GENERICALLY_SUPERSEDED.value)
        self.assertEqual(roles["ssi_official_financial_materialization.py"]["role"], LegacyModuleRole.SECTOR_SPECIALIZED.value)
        self.assertEqual(roles["annual_financial_ocr_materialization.py"]["role"], LegacyModuleRole.GENERIC_EXTRACTION_ENGINE.value)

    def test_generic_canonicalization_execution_and_hashing(self):
        """Execution across corpus produces deterministic hash and 100% rate on qualified facts."""
        res1 = execute_generic_canonicalization(
            citations=self.sample_citations[:2],
            manifest_records=self.sample_manifest,
            entity_profiles=self.entity_profiles,
            reference_at="2026-08-11T16:00:00+07:00",
            generated_at="2026-08-19T16:00:00Z",
        )
        res2 = execute_generic_canonicalization(
            citations=list(reversed(self.sample_citations[:2])),
            manifest_records=list(reversed(self.sample_manifest)),
            entity_profiles=self.entity_profiles,
            reference_at="2026-08-11T16:00:00+07:00",
            generated_at="2026-08-19T16:00:00Z",
        )
        self.assertEqual(res1["content_hash"], res2["content_hash"])
        self.assertEqual(res1["generic_canonicalization_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
