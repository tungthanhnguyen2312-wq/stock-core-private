"""P3-E fundamental coverage closeout and valuation-input readiness tests."""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from multi_period_financial_panel import MultiPeriodPanelError, load_promoted_fundamental_coverage_closeout_citations
from p3e_fundamental_coverage_closeout import (
    build_p3e_closeout,
    classify_p3d_residual_gaps,
    verify_retained_document_bytes,
)
from valuation_input_readiness import evaluate_valuation_input_readiness


class TestP3EFundamentalCoverageCloseout(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.manifest = json.loads((self.root / "config/promoted_fundamental_coverage_closeout_evidence.json").read_text(encoding="utf-8"))
        self.p2 = json.loads((self.root / "operations-review/p2-closeout-financial-fact-panel-20260820/p2_closeout_financial_panel_artifact.json").read_text(encoding="utf-8"))
        self.p3d = json.loads((self.root / "operations-review/p3d-residual-comparative-financial-evidence-20260820/p3d_residual_comparative_evidence_scaleout_artifact.json").read_text(encoding="utf-8"))

    def test_gap_taxonomy_marks_boundary_actionable_and_source_blocked_without_infinite_history(self) -> None:
        taxonomy = classify_p3d_residual_gaps(self.p3d)
        self.assertEqual(taxonomy["counts_by_category"], {
            "ACTIONABLE_INTERNAL_GAP": 13, "DOCUMENT_UNAVAILABLE": 0,
            "NOT_REQUIRED_FOR_CURRENT_RESEARCH_WINDOW": 0, "SEMANTICALLY_UNQUALIFIED": 0,
            "SOURCE_AUTHORITY_BLOCKED": 1, "STRUCTURAL_BOUNDARY_GAP": 28,
        })
        self.assertFalse(taxonomy["supported_history_boundary"]["unlimited_backward_acquisition_required"])
        vcb = [row for row in taxonomy["classifications"] if row["ticker"] == "VCB"]
        self.assertEqual(vcb[0]["gap_category"], "SOURCE_AUTHORITY_BLOCKED")

    def test_twelve_exact_facts_replay_generically_and_sources_fail_closed(self) -> None:
        citations = load_promoted_fundamental_coverage_closeout_citations(self.root)
        self.assertEqual(len(citations), 12)
        values = {(row["ticker"], row["metric"]): row["value"] for row in citations}
        self.assertEqual(values[("HPG", "revenue")], 138_855_112_131_387)
        self.assertEqual(values[("VNM", "total_assets")], 56_993_245)
        with patch("multi_period_financial_panel.admit", return_value={"decision": "refused"}):
            with self.assertRaisesRegex(MultiPeriodPanelError, "source authority"):
                load_promoted_fundamental_coverage_closeout_citations(self.root)

    def test_retained_bytes_and_page_lineage_are_verified(self) -> None:
        verified = verify_retained_document_bytes(self.root, self.manifest)
        self.assertEqual(len(verified), 6)
        self.assertTrue(all(row["integrity_status"] == "SHA256_AND_SOURCE_PAGE_LINEAGE_VERIFIED" for row in verified))

    def test_closeout_preserves_panel_closes_actionable_inputs_and_is_deterministic(self) -> None:
        first = build_p3e_closeout(repo_root=self.root, p2_artifact=self.p2, p3d_artifact=self.p3d, manifest=self.manifest)
        second = build_p3e_closeout(repo_root=self.root, p2_artifact=self.p2, p3d_artifact=self.p3d, manifest=self.manifest)
        self.assertEqual(first["artifact_identity"], second["artifact_identity"])
        self.assertEqual(first["panel_coverage_before_after"]["before"]["qualified_facts_count"], 118)
        self.assertEqual(first["panel_coverage_before_after"]["after"]["qualified_facts_count"], 130)
        self.assertEqual(first["remaining_data_gaps"]["gap_count"], 29)
        self.assertEqual(first["financial_evidence_lane"]["status"], "COMPARATIVE_EVIDENCE_LANE_CLOSED")
        self.assertEqual(first["capex_fcf_terminal_status"]["status"], "CAPEX_FCF_BLOCKED_MISSING_EXACT_IDENTITY")

    def test_readiness_is_not_valuation_and_market_dependency_stays_separate(self) -> None:
        closeout = build_p3e_closeout(repo_root=self.root, p2_artifact=self.p2, p3d_artifact=self.p3d, manifest=self.manifest)
        readiness = closeout["valuation_input_readiness"]
        self.assertFalse(readiness["is_valuation"])
        self.assertIn("target_price", readiness["prohibited_outputs"])
        by_ticker = {row["ticker"]: row for row in readiness["issuers"]}
        hpg = {row["family"]: row for row in by_ticker["HPG"]["families"]}
        self.assertEqual(hpg["P/E"]["financial_status"], "FINANCIAL_INPUT_READY")
        self.assertEqual(hpg["EV/EBITDA"]["financial_status"], "FINANCIAL_INPUT_PARTIAL")
        self.assertEqual(by_ticker["HPG"]["market_dependency"]["status"], "MARKET_INPUT_BLOCKED")
        vcb = {row["family"]: row for row in by_ticker["VCB"]["families"]}
        self.assertEqual(vcb["EV/EBITDA"]["financial_status"], "NOT_APPLICABLE")
        self.assertEqual(by_ticker["SSI"]["share_basis"]["state"], "QUALIFIED_FOR_INTENDED_DATE_USE")


if __name__ == "__main__":
    unittest.main()
