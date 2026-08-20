"""P3-D residual comparative financial evidence regression tests."""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from multi_period_financial_panel import (
    MultiPeriodPanelError,
    load_promoted_residual_comparative_financial_citations,
)
from p3d_residual_comparative_financial_evidence import (
    build_p3d_closeout,
    build_reconciled_residual_gap_inventory,
    verify_retained_document_bytes,
)


class TestP3DResidualComparativeFinancialEvidence(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.manifest = json.loads((self.root / "config" / "promoted_residual_comparative_financial_evidence.json").read_text(encoding="utf-8"))
        self.p2 = json.loads((self.root / "operations-review" / "p2-closeout-financial-fact-panel-20260820" / "p2_closeout_financial_panel_artifact.json").read_text(encoding="utf-8"))
        self.p3c = json.loads((self.root / "operations-review" / "p3c-comparative-financial-evidence-20260820" / "p3c_comparative_evidence_scaleout_artifact.json").read_text(encoding="utf-8"))

    def test_recomputed_starting_inventory_is_55_and_ssi_count_is_correct_by_definition(self) -> None:
        inventory = build_reconciled_residual_gap_inventory(self.p3c)
        self.assertEqual(inventory["gap_count"], 55)
        self.assertEqual(inventory["gap_counts_by_reason"], {
            "MISSING_CONSECUTIVE_PRIOR_PERIOD": 29,
            "MISSING_INPUTS:revenue": 15,
            "MISSING_INPUTS:total_assets": 11,
        })
        self.assertEqual(inventory["reconciliation"]["status"], "CORRECT_BY_DEFINITION")
        self.assertEqual(inventory["reconciliation"]["ssi_new_structural_gap"]["periods_used"], ["2023"])

    def test_generic_extraction_qualifies_exact_ten_facts_with_source_page_semantics(self) -> None:
        citations = load_promoted_residual_comparative_financial_citations(self.root)
        self.assertEqual(len(citations), 10)
        values = {(row["ticker"], row["reporting_period"], row["metric"]): row["value"] for row in citations}
        self.assertEqual(values[("HPG", "2022", "revenue")], 141_409_274_460_632)
        self.assertEqual(values[("HPG", "2023", "total_assets")], 187_782_586_563_801)
        self.assertEqual(values[("PVD", "2024", "revenue")], 373_599_586)
        self.assertEqual(values[("PVD", "2024", "total_assets")], 935_192_973)
        self.assertTrue(all(row["statement_scope"] == "consolidated" and row["audit_status"] == "audited" for row in citations))
        self.assertTrue(all(row["reconciliation_status"] == "EXACT_MATCH" for row in citations))

    def test_source_authority_fails_closed_and_vcb_is_recorded_not_promoted(self) -> None:
        with patch("multi_period_financial_panel.admit", return_value={"decision": "refused"}):
            with self.assertRaisesRegex(MultiPeriodPanelError, "source authority is not approved"):
                load_promoted_residual_comparative_financial_citations(self.root)
        blocked = [row for row in self.manifest["attempted_issuer_periods"] if row["ticker"] == "VCB"]
        self.assertEqual(blocked[0]["status"], "SOURCE_NOT_APPROVED")
        self.assertIn("VCB_FY2023_BLOCKED_SOURCE_NOT_APPROVED", blocked[0]["reason"])

    def test_retained_bytes_and_original_materialization_page_lineage_are_verified(self) -> None:
        results = verify_retained_document_bytes(self.root, self.manifest)
        self.assertEqual(len(results), 5)
        self.assertTrue(all(row["integrity_status"] == "SHA256_AND_SOURCE_PAGE_LINEAGE_VERIFIED" for row in results))

    def test_closeout_is_deterministic_preserves_panel_and_consumes_all_new_facts(self) -> None:
        first = build_p3d_closeout(repo_root=self.root, p2_artifact=self.p2, p3c_artifact=self.p3c, manifest=self.manifest)
        second = build_p3d_closeout(repo_root=self.root, p2_artifact=self.p2, p3c_artifact=self.p3c, manifest=self.manifest)
        self.assertEqual(first["artifact_identity"], second["artifact_identity"])
        self.assertEqual(first["panel_coverage_before_after"]["before"]["qualified_facts_count"], 108)
        self.assertEqual(first["panel_coverage_before_after"]["after"]["qualified_facts_count"], 118)
        self.assertEqual(first["remaining_data_gaps"]["gap_count"], 42)
        self.assertEqual(first["fundamental_readiness_before_after"]["after"]["metric_status_counts"], {
            "DERIVED_PROXY": 17, "EXACT_QUALIFIED": 86, "MISSING": 42, "NOT_APPLICABLE": 9,
        })
        upgrades = {(row["ticker"], row["metric_id"], row["period"]) for row in first["proxy_to_exact_upgrades"]}
        self.assertEqual(upgrades, {("HPG", "return_on_equity", "2022"), ("PVD", "return_on_equity", "2022")})


if __name__ == "__main__":
    unittest.main()
