"""Frozen retained-artifact tests for the nested current-screening bundle extension."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import export_ai_bundle as bundle
from current_market_screening_opportunity_comparison_foundation import content_identity


ROOT = Path(__file__).resolve().parents[1]
DESCRIPTIVE = ROOT / "operations-review/market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json"
SCREENING = ROOT / "operations-review/current-market-screening-opportunity-comparison-foundation-v1-20260823/current_market_screening_opportunity_comparison_foundation_artifact.json"


@unittest.skipUnless(DESCRIPTIVE.exists() and SCREENING.exists(), "retained screening/descriptive artifacts unavailable")
class CurrentScreeningResearchConsumptionTests(unittest.TestCase):
    def _entries(self):
        return {ticker: {"ticker": ticker} for ticker in ("AAA", "SHB", "A32", "ZZZ_NOT_IN_RETAINED_UNIVERSE")}

    def test_explicit_opt_in_nests_exact_retained_screening_context(self):
        entries = self._entries()
        bundle.attach_market_wide_current_descriptive_research(
            entries, include=True, artifact_path=str(DESCRIPTIVE),
            include_screening_comparison=True, screening_comparison_artifact_path=str(SCREENING),
        )
        retained = json.loads(SCREENING.read_text(encoding="utf-8"))
        for ticker in ("AAA", "SHB", "A32"):
            result = entries[ticker]["market_wide_current_descriptive_research"]["screening_comparison"]
            self.assertEqual(retained["records"][ticker], result["ticker_context"])
            self.assertEqual(retained["coverage_disclosure"], result["coverage_disclosure"])
            self.assertEqual(retained["screen_membership_counts"], result["screen_membership_counts"])
            self.assertFalse(result["is_actionable"])
        self.assertEqual(1510, result["coverage_disclosure"]["denominator"])
        self.assertEqual(960, result["coverage_disclosure"]["observed_session_cohort"])
        self.assertEqual("OTHER", entries["SHB"]["market_wide_current_descriptive_research"]["screening_comparison"]
                         ["ticker_context"]["liquidity_context"]["g1_v_reconciliation_verdict"])
        self.assertNotIn("market_wide_current_descriptive_research", entries["ZZZ_NOT_IN_RETAINED_UNIVERSE"])

    def test_screening_opt_in_is_off_by_default_and_lineage_mismatch_fails_closed(self):
        entries = self._entries()
        bundle.attach_market_wide_current_descriptive_research(
            entries, include=True, artifact_path=str(DESCRIPTIVE),
            include_screening_comparison=False, screening_comparison_artifact_path=str(SCREENING),
        )
        self.assertNotIn("screening_comparison", entries["AAA"]["market_wide_current_descriptive_research"])

        tampered = json.loads(SCREENING.read_text(encoding="utf-8"))
        tampered["input_lineage"] = copy.deepcopy(tampered["input_lineage"])
        tampered["input_lineage"]["current_descriptive_artifact_identity"] = "wrong-source-identity"
        tampered = {**tampered, **content_identity(tampered)}
        with tempfile.TemporaryDirectory() as temp:
            wrong_path = Path(temp) / "screening.json"
            wrong_path.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")
            entries = self._entries()
            bundle.attach_market_wide_current_descriptive_research(
                entries, include=True, artifact_path=str(DESCRIPTIVE),
                include_screening_comparison=True, screening_comparison_artifact_path=str(wrong_path),
            )
        for entry in entries.values():
            self.assertNotIn("market_wide_current_descriptive_research", entry)


if __name__ == "__main__":
    unittest.main()
