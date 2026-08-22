"""Regression contract for retained current-share capability reconciliation."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from field_temporal_contract import stable_id
import current_share_basis_capability_reconciliation as reconciliation
import tools.derive_current_share_basis_capability_reconciliation as runner


class CurrentShareBasisCapabilityReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = runner.build()

    def test_artifact_identity_is_deterministic_and_sources_are_retained(self):
        payload = dict(self.artifact)
        digest = payload.pop("artifact_sha256")
        identity = payload.pop("artifact_identity")
        self.assertEqual(digest, stable_id(payload))
        self.assertEqual(f"current_share_basis_capability_reconciliation:{digest}", identity)
        self.assertEqual(3, len(self.artifact["source_artifacts"]))
        retained = json.loads(runner.RETAINED_ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(self.artifact, retained)

    def test_issued_shares_are_not_aliased_even_when_a_number_matches(self):
        examples = self.artifact["representative_reconciliation"]
        self.assertTrue(examples["issued_vs_period_end_difference"])
        self.assertTrue(examples["equal_value_not_identity_proof"])
        provider = next(row for row in self.artifact["capability_records"] if row["capability"] == "provider_reported_issued_shares")
        self.assertEqual("issued_shares", provider["semantic_identity"])
        self.assertEqual(reconciliation.SEMANTICALLY_AMBIGUOUS, provider["verdict"])
        self.assertFalse(provider["allowed_downstream_uses"]["current_market_cap_denominator"]["eligible"])

    def test_missing_treasury_never_becomes_zero_and_weighted_average_is_separate(self):
        formula = self.artifact["formula_tests"]["issued_minus_treasury"]
        self.assertIsNone(formula["value"])
        self.assertEqual("UNKNOWN", formula["identity"])
        weighted = next(row for row in self.artifact["capability_records"] if row["capability"] == "weighted_average_basic_shares")
        self.assertEqual("weighted_average_basic_shares", weighted["semantic_identity"])
        self.assertFalse(weighted["allowed_downstream_uses"]["current_market_cap_denominator"]["eligible"])

    def test_current_market_cap_and_valuation_authority_remain_fail_closed(self):
        coverage = self.artifact["authoritative_current_market_cap_coverage"]
        self.assertEqual(0, coverage["eligible"])
        self.assertEqual(11, coverage["denominator"])
        self.assertTrue(all(row["eligible"] == 0 for row in self.artifact["valuation_authority"].values()))
        self.assertFalse(self.artifact["boundaries"]["provider_source_promoted"])

    def test_retained_corporate_action_blocks_are_reported(self):
        self.assertEqual(2, self.artifact["corpus"]["corporate_action_block_count"])
        self.assertTrue(self.artifact["representative_reconciliation"]["corporate_action_blocks"])
        stale_cases = [row for row in self.artifact["capability_records"]
                       if row["verdict"] == reconciliation.STALE_AFTER_CORPORATE_ACTION]
        self.assertEqual(2, len(stale_cases))


if __name__ == "__main__":
    unittest.main()
