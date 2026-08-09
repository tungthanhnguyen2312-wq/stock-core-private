"""Pure conflict-decomposition tests; fixtures contain no runtime or provider I/O."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from canonical_conflict_decomposition import decompose_facts, semantic_identity  # noqa: E402


def _fact(*, kind: str, status: str = "conflicted", detail: dict | None = None) -> dict:
    return {
        "ticker": "NEW", "canonical_metric": "net_income", "reporting_period": "2024-Q4",
        "period_type": "quarterly", "period_start": "2024-10-01", "period_end": "2024-12-31",
        "statement_family": "income_statement", "statement_scope": "consolidated",
        "currency": "VND", "scale": "units", "provider": "fixture", "identity_key": "identity",
        "fact_id": "fact", "source_sha256": "source-hash", "status": status,
        "source_observation_ids": ["observation-primary"],
        "conflicts": [{"kind": kind, **(detail or {})}],
    }


class CanonicalConflictDecompositionTests(unittest.TestCase):
    def test_existing_restated_variant_is_temporally_blocked_with_both_observations(self) -> None:
        result = decompose_facts([_fact(
            kind="restated_period_column_disagrees",
            detail={"variant_observation_id": "observation-variant", "primary_value": 100, "variant_value": 120},
        )])
        conflict = result["identities"][0]["conflicts"][0]
        self.assertEqual("restatement_identity_ambiguous", conflict["family"])
        self.assertEqual("blocked", conflict["resolution"])
        self.assertEqual(["observation-primary", "observation-variant"], conflict["source_observation_ids"])
        self.assertEqual("conflicted", result["identities"][0]["status_after"])

    def test_known_unit_mismatch_never_guesses_a_normalization(self) -> None:
        result = decompose_facts([_fact(kind="component_unit_mismatch")])
        conflict = result["identities"][0]["conflicts"][0]
        self.assertEqual("unit_or_scale_unresolved", conflict["family"])
        self.assertEqual("CANONICAL_FACT_UNIT_OR_SCALE_UNRESOLVED", conflict["reason_code"])
        self.assertEqual(0, result["auto_resolved_conflict_count"])

    def test_provider_disagreement_has_no_majority_or_newest_tiebreak(self) -> None:
        result = decompose_facts([_fact(kind="equal_priority_candidates_disagree")])
        conflict = result["identities"][0]["conflicts"][0]
        self.assertEqual("provider_or_candidate_disagreement", conflict["family"])
        self.assertEqual("no_majority_vote_or_candidate_tiebreak", conflict["authority_rule"])
        self.assertEqual("blocked", conflict["resolution"])

    def test_period_and_consolidation_are_part_of_the_exposed_semantic_identity(self) -> None:
        fact = _fact(kind="cash_flow_period_attribution_unverified")
        identity = semantic_identity(fact)
        self.assertEqual("2024-Q4", identity["reporting_period"])
        self.assertEqual("2024-12-31", identity["period_end"])
        self.assertEqual("consolidated", identity["statement_scope"])
        self.assertEqual("income_statement", identity["statement_family"])

    def test_same_input_is_deterministic_and_no_conflict_is_promoted(self) -> None:
        facts = [
            _fact(kind="balance_sheet_identity_violated"),
            _fact(kind="revenue_occurrences_do_not_reconcile_with_deductions"),
        ]
        facts[1]["canonical_metric"] = "revenue"
        facts[1]["fact_id"] = "fact-revenue"
        first = decompose_facts(facts)
        second = decompose_facts(copy.deepcopy(facts))
        self.assertEqual(first, second)
        self.assertEqual(0, first["auto_resolved_conflict_count"])
        self.assertEqual(2, first["terminally_unresolved_conflict_count"])


if __name__ == "__main__":
    unittest.main()
