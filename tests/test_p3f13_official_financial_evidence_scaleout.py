"""Tests for P3-F13 generic official financial evidence operational scale-out."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from p3f13_official_financial_evidence_scaleout import execute, build_scaleout_artifact


ROOT = Path(__file__).resolve().parents[1]


class TestP3F13OfficialFinancialEvidenceScaleout(unittest.TestCase):
    def setUp(self) -> None:
        self.artifact = execute()

    def test_cohort_and_disposition_reconciliation(self) -> None:
        cohort = self.artifact["cohort_identity"]
        self.assertEqual(cohort["total_cohort_count"], 523)
        self.assertEqual(cohort["target_blocked_cohort_count"], 512)

        summary = self.artifact["acquisition_dispositions_summary"]
        self.assertEqual(summary["total_attempted"], 512)
        self.assertEqual(summary["unattempted_without_explicit_disposition"], 0)
        self.assertTrue(summary["disposition_reconciliation_ok"])

        counts = summary["disposition_counts"]
        self.assertEqual(counts.get("FILING_ALREADY_RETAINED", 0), 2)
        self.assertEqual(counts.get("NO_APPROVED_ROUTE_FOUND", 0), 510)
        self.assertEqual(sum(counts.values()), 512)

    def test_newly_qualified_issuers(self) -> None:
        new_issuers = self.artifact["newly_qualified_issuers"]
        self.assertEqual(sorted(new_issuers), ["FPT", "PNJ"])

    def test_before_after_comparison(self) -> None:
        cmp = self.artifact["before_after_comparison"]
        self.assertEqual(cmp["official_filings_acquired_or_retained"]["before"], 11)
        self.assertEqual(cmp["official_filings_acquired_or_retained"]["after"], 13)
        self.assertEqual(cmp["official_filings_acquired_or_retained"]["delta"], 2)

        self.assertEqual(cmp["canonical_exact_qualified_facts"]["before"], 130)
        self.assertEqual(cmp["canonical_exact_qualified_facts"]["after"], 138)
        self.assertEqual(cmp["canonical_exact_qualified_facts"]["delta"], 8)

        self.assertEqual(cmp["exact_qualified_metrics"]["before"], 94)
        self.assertEqual(cmp["exact_qualified_metrics"]["after"], 94)
        self.assertEqual(cmp["exact_qualified_metrics"]["delta"], 0)

        self.assertEqual(cmp["derived_proxies"]["before"], 22)
        self.assertEqual(cmp["derived_proxies"]["after"], 22)
        self.assertEqual(cmp["derived_proxies"]["delta"], 0)

        readiness = cmp["fundamental_readiness_status"]["after"]
        self.assertEqual(readiness["COMPLETE"], 0)
        self.assertEqual(readiness["PARTIAL"], 13)
        self.assertEqual(readiness["BLOCKED"], 510)

    def test_root_blockers(self) -> None:
        blockers = {r["root_cause"]: r["affected_instruments"] for r in self.artifact["root_blocker_distribution"]}
        self.assertEqual(blockers["no_approved_discoverable_filing"], 510)
        self.assertEqual(blockers["inaccessible_official_route"], 0)
        self.assertEqual(blockers["unsupported_document_layout"], 0)

    def test_authority_boundaries(self) -> None:
        boundaries = self.artifact["authority_boundaries"]
        self.assertFalse(boundaries["new_provider_added"])
        self.assertFalse(boundaries["source_authority_promoted"])
        self.assertFalse(boundaries["canonical_store_mutated"])
        self.assertFalse(boundaries["runtime_database_mutated"])
        self.assertFalse(boundaries["p3g_started"])
        self.assertEqual(self.artifact["ticker_specific_branch_audit"]["status"], "PASS")

    def test_gates_and_verdict(self) -> None:
        self.assertEqual(self.artifact["scaleout_gate"], "OFFICIAL_FINANCIAL_EVIDENCE_SCALEOUT_PARTIAL")
        self.assertEqual(self.artifact["verdict"], "P3F13_OFFICIAL_FINANCIAL_EVIDENCE_SCALEOUT_COMPLETE")


if __name__ == "__main__":
    unittest.main()
