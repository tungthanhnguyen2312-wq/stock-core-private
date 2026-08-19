"""Tests for P2-C Official Financial Evidence Scale-Out & First Corporate Acquisition Wave."""

from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

from field_temporal_contract import stable_id
from official_source_registry import ADMITTED, REFUSED, admit, load_registry
from tools.run_p2c_corporate_evidence_scale_out import (
    ALREADY_COVERED_TICKERS,
    REQUESTED_COHORT_SIZE,
    evaluate_cohort,
    load_profiles,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestP2CCorporateEvidenceScaleOut(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = PROJECT_ROOT
        self.profiles = load_profiles(self.repo_root)
        self.registry = load_registry(self.repo_root / "config" / "official_source_registry.json")

    def test_positive_entity_profiles_authority(self) -> None:
        """Verify that entity profiles are loaded strictly from config/ticker_entity_profiles.csv."""
        self.assertGreaterEqual(len(self.profiles), 20)
        self.assertEqual(self.profiles["GAS"], "corporate")
        self.assertEqual(self.profiles["MWG"], "corporate")
        self.assertEqual(self.profiles["VIC"], "corporate")
        self.assertEqual(self.profiles["VRE"], "corporate")
        # Verify financials
        self.assertEqual(self.profiles["BID"], "bank")
        self.assertEqual(self.profiles["SSI"], "securities")
        self.assertEqual(self.profiles["BVH"], "insurance")
        self.assertEqual(self.profiles["EVF"], "finance_company")

    def test_reconciliation_and_cohort_shortfall(self) -> None:
        """Verify exact reconciliation counts and shortfall reporting."""
        report = evaluate_cohort(self.repo_root)
        rec = report["reconciliation"]
        metrics = report["metrics"]

        # C.1 Candidates
        self.assertEqual(rec["total_candidates"], 3250)
        self.assertEqual(rec["listed_equity_candidates"], 1660)
        self.assertEqual(rec["non_equity_candidates"], 1590)

        # Profiled counts
        self.assertEqual(rec["positively_classified_corporates"], 13)
        self.assertEqual(rec["positively_classified_financials"], 7)
        self.assertEqual(rec["unknown_entity_class_issuers"], 1640)

        # Already covered
        self.assertEqual(rec["already_covered_corporates"], 9)
        self.assertEqual(rec["uncovered_authority_eligible_corporates"], ["GAS", "MWG", "VIC", "VRE"])

        # Metrics
        self.assertEqual(metrics["requested_cohort_size"], 20)
        self.assertEqual(metrics["actual_authority_eligible_cohort_size"], 4)
        self.assertEqual(metrics["cohort_shortfall_due_to_entity_classification"], 16)
        self.assertEqual(metrics["new_ticker_specific_materializer_count"], 0)

    def test_official_source_gate_fails_closed(self) -> None:
        """Promoted hosts are admitted while unapproved IR hosts fail closed as not admitted."""
        res_gas = admit(
            "issuer_ir",
            "https://www.pvgas.com.vn/quan-he-co-dong/bao-cao-tai-chinh/2024",
            "audited_annual_financial_statements",
            registry=self.registry,
        )
        self.assertEqual(res_gas["decision"], ADMITTED)

        res_mwg = admit(
            "issuer_ir",
            "https://mwg.vn/quan-he-co-dong/bao-cao-tai-chinh/2024",
            "audited_annual_financial_statements",
            registry=self.registry,
        )
        self.assertEqual(res_mwg["decision"], REFUSED)

        res_vic = admit(
            "issuer_ir",
            "https://vingroup.net/quan-he-co-dong/bao-cao-tai-chinh/2024",
            "audited_annual_financial_statements",
            registry=self.registry,
        )
        self.assertEqual(res_vic["decision"], REFUSED)

    def test_no_ticker_specific_materializer_modules_created(self) -> None:
        """Ensure zero per-ticker materializer Python modules exist for the cohort."""
        cohort = ["GAS", "MWG", "VIC", "VRE"]
        for sym in cohort:
            ticker_module = self.repo_root / f"{sym.lower()}_official_financial_materialization.py"
            self.assertFalse(ticker_module.exists(), f"Found forbidden ticker module: {ticker_module}")

    def test_deterministic_artifact_hashing(self) -> None:
        """Verify deterministic hashing of the scale-out evaluation artifact."""
        report1 = evaluate_cohort(self.repo_root)
        hash1 = report1["content_hash"]

        report2 = evaluate_cohort(self.repo_root)
        hash2 = report2["content_hash"]

        # Note: generated_at changes so content_hash is based on data fields
        raw1 = {k: v for k, v in report1.items() if k not in ("generated_at", "content_hash", "artifact_id")}
        raw2 = {k: v for k, v in report2.items() if k not in ("generated_at", "content_hash", "artifact_id")}
        self.assertEqual(stable_id(raw1), stable_id(raw2))


if __name__ == "__main__":
    unittest.main()
