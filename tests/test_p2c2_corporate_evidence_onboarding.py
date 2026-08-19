"""Unit tests for Phase 2 / P2-C2: Bounded Financial Evidence Onboarding (GAS & VRE)."""

from __future__ import annotations

from pathlib import Path
import unittest

from tools.run_p2c2_corporate_evidence_onboarding import (
    ACTIVE_COHORT,
    CONTRACT_VERSION,
    OFFICIAL_EVIDENCE_SPECS,
    PRESERVED_TERMINAL_COHORT,
    SCHEMA_VERSION,
    execute_p2c2_onboarding,
    generate_readiness_report,
)
from official_source_registry import ADMITTED, admit, load_registry

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestP2C2CorporateEvidenceOnboarding(unittest.TestCase):

    def setUp(self):
        self.repo_root = PROJECT_ROOT
        self.registry = load_registry(self.repo_root / "config" / "official_source_registry.json")

    def test_bounded_cohort_and_preserved_terminal_states(self):
        """Active cohort is strictly GAS and VRE; MWG and VIC remain blocked."""
        self.assertEqual(ACTIVE_COHORT, ("GAS", "VRE"))
        self.assertEqual(PRESERVED_TERMINAL_COHORT["MWG"], "NOT_READY_REDIRECT_CHAIN")
        self.assertEqual(PRESERVED_TERMINAL_COHORT["VIC"], "NOT_READY_REPRODUCIBILITY")

    def test_official_source_admission(self):
        """GAS and VRE official routes are admitted under promoted authority."""
        gas_spec = OFFICIAL_EVIDENCE_SPECS["GAS"]
        gas_adm = admit(
            gas_spec["source_id"],
            gas_spec["locator"],
            gas_spec["document_class"],
            registry=self.registry,
        )
        self.assertEqual(gas_adm["decision"], ADMITTED)
        self.assertEqual(gas_adm["reason"], "admitted_by_registry")

        vre_spec = OFFICIAL_EVIDENCE_SPECS["VRE"]
        vre_adm = admit(
            vre_spec["source_id"],
            vre_spec["locator"],
            vre_spec["document_class"],
            registry=self.registry,
        )
        self.assertEqual(vre_adm["decision"], ADMITTED)
        self.assertEqual(vre_adm["reason"], "admitted_by_registry")

    def test_document_qualification_criteria(self):
        """Financial statements meet strict audited annual consolidated criteria."""
        for ticker in ACTIVE_COHORT:
            spec = OFFICIAL_EVIDENCE_SPECS[ticker]
            self.assertEqual(spec["document_class"], "audited_annual_financial_statements")
            self.assertEqual(spec["scope"], "consolidated")
            self.assertEqual(spec["auditor"], "Deloitte Vietnam")
            self.assertEqual(spec["reporting_period"], "2025")
            self.assertTrue(len(spec["content_sha256"]) == 64)
            self.assertGreater(spec["file_size_bytes"], 10_000_000)

    def test_end_to_end_onboarding_and_zero_ticker_materializers(self):
        """End-to-end execution onboards GAS and VRE with zero ticker-specific materializers."""
        result = execute_p2c2_onboarding(self.repo_root, generated_at="2026-08-19T13:30:00Z")

        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["active_cohort_size"], 2)
        self.assertEqual(result["successful_onboarded_count"], 2)
        self.assertEqual(result["end_to_end_onboarding_rate"], 1.0)
        self.assertEqual(result["new_ticker_specific_materializer_count"], 0)
        self.assertEqual(result["total_canonical_facts_emitted"], 16)

        gas_res = result["issuer_results"]["GAS"]
        self.assertEqual(gas_res["onboarding_status"], "ONBOARDING_SUCCESS")
        self.assertEqual(gas_res["canonicalization_method"], "generic_dictionary_pipeline")
        self.assertEqual(len(gas_res["facts"]), 8)

        vre_res = result["issuer_results"]["VRE"]
        self.assertEqual(vre_res["onboarding_status"], "ONBOARDING_SUCCESS")
        self.assertEqual(vre_res["canonicalization_method"], "generic_dictionary_pipeline")
        self.assertEqual(len(vre_res["facts"]), 8)

        # Unpromoted candidates preserved
        self.assertEqual(result["issuer_results"]["MWG"]["terminal_state"], "NOT_READY_REDIRECT_CHAIN")
        self.assertEqual(result["issuer_results"]["VIC"]["terminal_state"], "NOT_READY_REPRODUCIBILITY")

    def test_panel_derived_metrics(self):
        """Multi-period panel derived ratios are properly computed."""
        result = execute_p2c2_onboarding(self.repo_root, generated_at="2026-08-19T13:30:00Z")

        gas_panel = result["panels_by_issuer"]["GAS"]
        gas_derived = gas_panel["derived_metrics"]["2025"]
        self.assertAlmostEqual(gas_derived["cash_flow_to_net_income"]["value"], 1.1269, places=3)
        self.assertAlmostEqual(gas_derived["debt_to_equity"]["value"], 0.0439, places=3)
        self.assertAlmostEqual(gas_derived["roe_proxy"]["value"], 0.1710, places=3)
        self.assertEqual(gas_derived["net_debt"]["status"], "QUALIFIED")

        vre_panel = result["panels_by_issuer"]["VRE"]
        vre_derived = vre_panel["derived_metrics"]["2025"]
        self.assertAlmostEqual(vre_derived["cash_flow_to_net_income"]["value"], -0.5061, places=3)
        self.assertAlmostEqual(vre_derived["debt_to_equity"]["value"], 0.1323, places=3)
        self.assertAlmostEqual(vre_derived["roe_proxy"]["value"], 0.1333, places=3)
        self.assertEqual(vre_derived["net_debt"]["status"], "QUALIFIED")

    def test_readiness_report_generation(self):
        """Readiness report contains required tables, metrics, and invariant checks."""
        result = execute_p2c2_onboarding(self.repo_root, generated_at="2026-08-19T13:30:00Z")
        report = generate_readiness_report(result)

        self.assertIn("# Phase 2 / P2-C2: Bounded Financial Evidence Onboarding Report (GAS & VRE)", report)
        self.assertIn("ONBOARDING_SUCCESS", report)
        self.assertIn("NOT_READY_REDIRECT_CHAIN", report)
        self.assertIn("NOT_READY_REPRODUCIBILITY", report)
        self.assertIn("ZERO ticker-specific Python modules", report)
        self.assertIn("STRICT INVARIANT MET", report)


if __name__ == "__main__":
    unittest.main()
