"""P3-C comparative annual evidence regression tests."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from entity_classification_contract import EntityClass
from multi_period_financial_panel import load_promoted_comparative_financial_citations
from p3c_comparative_financial_evidence import (
    build_p3c_closeout,
    build_starting_gap_inventory,
    verify_retained_document_bytes,
)
from sector_financial_taxonomy import PromotedScopeEvaluationState, evaluate_sector_extraction_authority_scope


class TestP3CComparativeFinancialEvidence(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.manifest = json.loads((self.root / "config" / "promoted_comparative_financial_evidence.json").read_text(encoding="utf-8"))
        self.p2 = json.loads((self.root / "operations-review" / "p2-closeout-financial-fact-panel-20260820" / "p2_closeout_financial_panel_artifact.json").read_text(encoding="utf-8"))
        self.p3b = json.loads((self.root / "operations-review" / "p3b-fundamental-research-readiness-20260820" / "p3b_fundamental_research_readiness_artifact.json").read_text(encoding="utf-8"))

    def test_six_facts_replay_through_generic_recognizer(self) -> None:
        citations = load_promoted_comparative_financial_citations(self.root)
        self.assertEqual(len(citations), 6)
        values = {citation["metric"]: citation["value"] for citation in citations}
        self.assertEqual(values["financial_assets_fvtpl"], 44_072_153_174_688)
        self.assertEqual(values["loans_balance"], 15_134_065_013_420)
        self.assertEqual(values["total_assets"], 69_241_327_102_648)
        self.assertEqual(values["total_equity"], 23_240_892_110_813)
        self.assertEqual(values["profit_after_tax_total"], 2_294_472_821_558)
        self.assertEqual(values["profit_after_tax_parent"], 2_292_781_385_416)
        self.assertTrue(all(citation["statement_scope"] == "consolidated" for citation in citations))
        self.assertTrue(all(citation["audit_status"] == "audited" for citation in citations))

    def test_additional_promoted_scope_is_hash_bound_and_not_ticker_branch(self) -> None:
        doc = self.manifest["evidence_documents"][0]
        state, _ = evaluate_sector_extraction_authority_scope(
            ticker=doc["ticker"], entity_class=EntityClass.SECURITIES,
            reporting_period=doc["reporting_period"], statement_scope=doc["statement_scope"],
            document_sha256=doc["document_sha256"],
        )
        self.assertEqual(state, PromotedScopeEvaluationState.PROMOTED_PROOF_SCOPE)
        wrong_state, _ = evaluate_sector_extraction_authority_scope(
            ticker=doc["ticker"], entity_class=EntityClass.SECURITIES,
            reporting_period=doc["reporting_period"], statement_scope=doc["statement_scope"],
            document_sha256="0" * 64,
        )
        self.assertEqual(wrong_state, PromotedScopeEvaluationState.UNPROMOTED_PERIOD_OR_SCOPE)

    def test_closeout_is_deterministic_and_lifts_only_bounded_ssi_facts(self) -> None:
        first = build_p3c_closeout(repo_root=self.root, p2_artifact=self.p2, p3b_before=self.p3b, manifest=self.manifest)
        second = build_p3c_closeout(repo_root=self.root, p2_artifact=self.p2, p3b_before=self.p3b, manifest=self.manifest)
        self.assertEqual(first["artifact_identity"], second["artifact_identity"])
        self.assertEqual(first["panel_coverage_before_after"]["before"]["qualified_facts_count"], 102)
        self.assertEqual(first["panel_coverage_before_after"]["after"]["qualified_facts_count"], 108)
        upgrades = first["proxy_to_exact_upgrades"]
        self.assertEqual([(row["ticker"], row["metric_id"], row["period"]) for row in upgrades], [
            ("SSI", "return_on_assets", "2024"), ("SSI", "return_on_equity", "2024"),
        ])
        self.assertEqual(first["evidence_acquisition"]["blocked_issuer_periods"][0]["ticker"], "VCB")
        self.assertEqual(first["sector_and_authority_boundaries"]["capex_boundary"]["status"], "NOT_PROMOTED")

    def test_frozen_gap_inventory_and_retained_bytes_are_bound_to_source_artifacts(self) -> None:
        frozen = build_starting_gap_inventory(self.p3b)
        self.assertEqual(frozen["frozen_from_artifact_identity"], self.p3b["artifact_identity"])
        self.assertEqual(frozen["gap_count"], len(self.p3b["data_gap_matrix"]))
        verified = verify_retained_document_bytes(self.root, self.manifest)
        self.assertEqual(verified[0]["integrity_status"], "SHA256_VERIFIED")
        self.assertEqual(verified[0]["document_sha256"], self.manifest["evidence_documents"][0]["document_sha256"])


if __name__ == "__main__":
    unittest.main()
