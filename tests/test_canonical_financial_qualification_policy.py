"""Qualification promotion policy proofs; all fixtures are pure and local."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import canonical_financial_qualification_policy as policy  # noqa: E402


def _fact(*, status: str = "provider_reported", period: str = "2024", scope: str = "consolidated") -> dict:
    return {
        "ticker": "NEW", "canonical_metric": "net_income", "status": status, "value": 100,
        "reporting_period": period, "period_type": "annual", "period_start": "2024-01-01",
        "period_end": "2024-12-31", "statement_family": "income_statement", "statement_scope": scope,
        "currency": "VND", "scale": "units", "provider": "fixture", "source_sha256": "source-hash",
        "source_observation_ids": ["obs-1"], "identity_key": "identity-1", "fact_id": "fact-1", "conflicts": [],
    }


def _evidence() -> dict:
    return {("NEW", "net_income", "2024"): {
        "citation_id": "citation-1", "evidence_id": "evidence-1", "document_sha256": "document-hash",
        "citation": "page 1", "value": 100, "currency": "VND", "unit_scale": 1,
        "statement_scope": "consolidated", "verified": True,
    }}


class QualificationPolicyTests(unittest.TestCase):
    def test_fully_evidenced_fact_is_safe_promotion(self) -> None:
        result = policy.evaluate_fact(_fact(), evidence_index=_evidence())
        self.assertEqual(result["status"], "qualified")
        self.assertTrue(result["safe_promotion"])

    def test_missing_citation_remains_provider_reported_and_is_frontier(self) -> None:
        result = policy.evaluate_fact(_fact())
        self.assertEqual(result["status"], "provider_reported")
        self.assertEqual(result["reason_codes"], ["CITATION_MISSING"])
        self.assertTrue(policy.is_promotion_frontier(result))

    def test_missing_source_hash_is_not_qualified(self) -> None:
        fact = _fact()
        fact["source_sha256"] = None
        result = policy.evaluate_fact(fact, evidence_index=_evidence())
        self.assertIn("SOURCE_HASH_MISSING", result["reason_codes"])
        self.assertNotEqual(result["status"], "qualified")

    def test_wrong_scope_and_period_are_separate_blockers(self) -> None:
        scoped = policy.evaluate_fact(_fact(scope="separate"), evidence_index=_evidence())
        period = _fact()
        period["period_start"] = None
        period_result = policy.evaluate_fact(period, evidence_index=_evidence())
        self.assertIn("CONSOLIDATION_SCOPE_UNQUALIFIED", scoped["reason_codes"])
        self.assertIn("PERIOD_IDENTITY_INCOMPLETE", period_result["reason_codes"])

    def test_unknown_restatement_never_uses_ingestion_order(self) -> None:
        fact = _fact(status="conflicted")
        fact["conflicts"] = [{"kind": "restated_period_column_disagrees", "ingested_at": "2099-01-01"}]
        result = policy.evaluate_fact(fact, evidence_index=_evidence())
        self.assertEqual(result["status"], "conflicted")
        self.assertIn("RESTATEMENT_STATE_UNKNOWN", result["reason_codes"])

    def test_explicit_restatement_supersession_is_accepted_only_with_all_evidence(self) -> None:
        fact = _fact(status="conflicted")
        fact["conflicts"] = [{"kind": "restated_period_column_disagrees", "superseding_document_id": "amended-1",
                              "supersession_evidence_id": "evidence-2", "publication_date": "2025-03-01"}]
        self.assertEqual(policy.evaluate_fact(fact, evidence_index=_evidence())["status"], "qualified")
        fact["conflicts"][0].pop("publication_date")
        self.assertIn("RESTATEMENT_STATE_UNKNOWN", policy.evaluate_fact(fact, evidence_index=_evidence())["reason_codes"])

    def test_arithmetic_failure_blocks(self) -> None:
        fact = _fact(status="conflicted")
        fact["conflicts"] = [{"kind": "balance_sheet_identity_violated"}]
        result = policy.evaluate_fact(fact, evidence_index=_evidence())
        self.assertIn("ARITHMETIC_INTEGRITY_FAILED", result["reason_codes"])
        self.assertEqual(result["status"], "conflicted")

    def test_multi_gap_and_qualified_are_not_frontier(self) -> None:
        multi = _fact()
        multi["source_sha256"] = None
        self.assertFalse(policy.is_promotion_frontier(policy.evaluate_fact(multi)))
        self.assertFalse(policy.is_promotion_frontier(policy.evaluate_fact(_fact(), evidence_index=_evidence())))

    def test_quarterly_fact_cannot_count_toward_annual_research_frontier(self) -> None:
        fact = _fact(status="qualified", period="2024-Q4")
        fact["period_type"] = "quarterly"
        fact["period_start"] = "2024-10-01"
        fact["period_end"] = "2024-12-31"
        result = policy.ticker_frontier("NEW", [fact], required_metrics={"net_income"},
                                        entity_type="corporate", evidence_index={})
        self.assertEqual(result["qualified_metrics"], [])
        self.assertIn("RESEARCH_PERIOD_NOT_ANNUAL", result["reason_codes"])

    def test_inventory_and_manifest_are_deterministic_and_value_free(self) -> None:
        facts = [_fact(), _fact(status="qualified")]
        facts[1]["fact_id"] = "fact-2"
        first = policy.inventory(facts, evidence_index=_evidence())
        second = policy.inventory(copy.deepcopy(facts), evidence_index=_evidence())
        self.assertEqual(first, second)
        manifest = policy.candidate_manifest({"NEW": facts}, required_metrics={"net_income"},
                                             entity_types={"NEW": "corporate"}, evidence_index=_evidence())
        self.assertNotIn("value", str(manifest["promotion_frontier_candidates"]))


if __name__ == "__main__":
    unittest.main()
