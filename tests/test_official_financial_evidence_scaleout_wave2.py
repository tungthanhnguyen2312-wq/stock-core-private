"""Focused unit tests for Wave 2 official financial evidence scale-out."""
from __future__ import annotations

import unittest
from pathlib import Path

from wave2_official_financial_evidence_scaleout import (
    execute,
    build_wave2_scaleout_artifact,
    select_wave2_candidate_cohort,
)


ROOT = Path(__file__).resolve().parents[1]


class TestWave2OfficialFinancialEvidenceScaleout(unittest.TestCase):
    def setUp(self) -> None:
        self.artifact = execute()

    def test_cohort_and_candidate_selection(self) -> None:
        cohort = self.artifact["cohort_identity"]
        self.assertEqual(cohort["total_cohort_count"], 523)
        self.assertEqual(cohort["target_blocked_cohort_count"], 510)
        self.assertEqual(cohort["wave2_candidate_cohort_count"], 17)

        candidates = self.artifact["wave2_candidate_cohort"]
        self.assertEqual(len(candidates), 17)

        # Check candidate sector breakdown
        sectors = Counter_sectors = {}
        for c in candidates:
            sectors[c["entity_type"]] = sectors.get(c["entity_type"], 0) + 1

        self.assertEqual(sectors.get("bank"), 5)
        self.assertEqual(sectors.get("securities"), 2)
        self.assertEqual(sectors.get("corporate"), 10)

        # Check specific priority candidates are included
        candidate_tickers = {c["ticker"] for c in candidates}
        for expected_bank in ("ABB", "ACB", "BID", "MBB", "TCB"):
            self.assertIn(expected_bank, candidate_tickers)
        for expected_sec in ("AAS", "ABW"):
            self.assertIn(expected_sec, candidate_tickers)
        for expected_corp in ("AAA", "AAH", "AAN", "AAT", "AAV", "ABS", "ABT", "ACC", "MWG", "VIC"):
            self.assertIn(expected_corp, candidate_tickers)

    def test_candidate_selection_determinism(self) -> None:
        c1 = select_wave2_candidate_cohort(
            empirical_cohort=self.artifact["cohort_identity"]["name"] and [c["ticker"] for c in self.artifact["wave2_candidate_cohort"]] or [],
            qualified_baseline=["GAS", "HPG", "NVL", "PAN", "POW", "PVD", "QNS", "SSI", "VCB", "VNM", "VRE", "FPT", "PNJ"],
            entity_profiles={"BID": "bank", "MBB": "bank", "MWG": "corporate", "VIC": "corporate"},
            raw_obs_dir=ROOT / "operations-review" / "p1f-milestone-20260803" / "shadow-build-a" / "data" / "market-wide-financials" / "observations",
            max_candidates=10,
        )
        c2 = select_wave2_candidate_cohort(
            empirical_cohort=self.artifact["cohort_identity"]["name"] and [c["ticker"] for c in self.artifact["wave2_candidate_cohort"]] or [],
            qualified_baseline=["GAS", "HPG", "NVL", "PAN", "POW", "PVD", "QNS", "SSI", "VCB", "VNM", "VRE", "FPT", "PNJ"],
            entity_profiles={"BID": "bank", "MBB": "bank", "MWG": "corporate", "VIC": "corporate"},
            raw_obs_dir=ROOT / "operations-review" / "p1f-milestone-20260803" / "shadow-build-a" / "data" / "market-wide-financials" / "observations",
            max_candidates=10,
        )
        self.assertEqual(c1, c2)

    def test_source_discovery_and_fail_closed_dispositions(self) -> None:
        disc = self.artifact["source_discovery_summary"]
        self.assertEqual(disc["total_candidates_attempted"], 17)
        self.assertEqual(disc["disposition_counts"].get("NO_OFFICIAL_ROUTE_DISCOVERABLE"), 17)
        self.assertEqual(disc["route_ownership_status_counts"].get("OWNERSHIP_EVIDENCE_MISSING"), 17)

        evals = self.artifact["wave2_candidate_evaluations"]
        self.assertEqual(len(evals), 17)
        for e in evals:
            self.assertEqual(e["disposition"], "NO_APPROVED_ROUTE_FOUND")
            self.assertEqual(e["retained_documents_count"], 0)
            self.assertEqual(e["route_ownership_status"], "OWNERSHIP_EVIDENCE_MISSING")

    def test_baseline_preservation_and_comparison(self) -> None:
        cmp = self.artifact["before_after_comparison"]
        self.assertEqual(cmp["official_filings_acquired_or_retained"]["before"], 13)
        self.assertEqual(cmp["official_filings_acquired_or_retained"]["after"], 13)
        self.assertEqual(cmp["official_filings_acquired_or_retained"]["delta"], 0)

        self.assertEqual(cmp["canonical_exact_qualified_facts"]["before"], 138)
        self.assertEqual(cmp["canonical_exact_qualified_facts"]["after"], 138)
        self.assertEqual(cmp["canonical_exact_qualified_facts"]["delta"], 0)

        self.assertEqual(cmp["exact_qualified_metrics"]["before"], 94)
        self.assertEqual(cmp["exact_qualified_metrics"]["after"], 94)
        self.assertEqual(cmp["exact_qualified_metrics"]["delta"], 0)

        self.assertEqual(cmp["derived_proxies"]["before"], 22)
        self.assertEqual(cmp["derived_proxies"]["after"], 22)
        self.assertEqual(cmp["derived_proxies"]["delta"], 0)

        self.assertEqual(cmp["fundamental_readiness_status"]["after"]["COMPLETE"], 0)
        self.assertEqual(cmp["fundamental_readiness_status"]["after"]["PARTIAL"], 13)
        self.assertEqual(cmp["fundamental_readiness_status"]["after"]["BLOCKED"], 510)

        # Baseline sector breakdown preserved
        sectors_after = cmp["sector_breakdown_qualified_cohort"]["after"]
        self.assertEqual(sectors_after.get("corporate"), 11)
        self.assertEqual(sectors_after.get("bank"), 1)
        self.assertEqual(sectors_after.get("securities"), 1)

    def test_root_blockers(self) -> None:
        blockers = {b["root_cause"]: b["affected_instruments"] for b in self.artifact["root_blocker_distribution"]}
        self.assertEqual(blockers["no_approved_discoverable_filing"], 510)
        self.assertEqual(blockers["route_ownership_evidence_missing"], 17)
        self.assertEqual(blockers["missing_scope_currency_scale"], 510)

    def test_authority_boundaries(self) -> None:
        boundaries = self.artifact["authority_boundaries"]
        self.assertFalse(boundaries["new_provider_added"])
        self.assertFalse(boundaries["source_authority_promoted"])
        self.assertFalse(boundaries["canonical_store_mutated"])
        self.assertFalse(boundaries["runtime_database_mutated"])
        self.assertFalse(boundaries["historical_pit_promoted"])
        self.assertFalse(boundaries["raw_as_traded_promoted"])
        self.assertFalse(boundaries["liquidity_sizing_promoted"])
        self.assertFalse(boundaries["valuation_or_recommendation_produced"])
        self.assertFalse(boundaries["p3g_started"])
        self.assertEqual(self.artifact["ticker_specific_branch_audit"]["status"], "PASS")

    def test_deterministic_replay(self) -> None:
        second_artifact = execute()
        self.assertEqual(self.artifact["artifact_sha256"], second_artifact["artifact_sha256"])
        self.assertEqual(self.artifact["artifact_identity"], second_artifact["artifact_identity"])

    def test_gates_and_verdicts(self) -> None:
        self.assertEqual(self.artifact["scaleout_gate"], "OFFICIAL_FINANCIAL_EVIDENCE_SCALEOUT_WAVE2_PARTIAL")
        self.assertEqual(self.artifact["verdict"], "OFFICIAL_FINANCIAL_EVIDENCE_SCALEOUT_WAVE2_PARTIAL")


if __name__ == "__main__":
    unittest.main()
