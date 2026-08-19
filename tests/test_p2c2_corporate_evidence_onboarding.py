"""Unit tests for Phase 2 / P2-D: Generic Financial Template Onboarding (GAS & VRE)."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

from tools.run_p2c2_corporate_evidence_onboarding import (
    ACTIVE_COHORT,
    CONTRACT_VERSION,
    COHORT_PROFILES,
    PRESERVED_TERMINAL_COHORT,
    SCHEMA_VERSION,
    execute_p2c2_onboarding,
    generate_readiness_report,
)
from official_source_registry import ADMITTED, admit, load_registry
from official_document_qualification import QUALIFICATION_SUCCESS_STATUS, qualify_retained_document

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestP2C2CorporateEvidenceOnboarding(unittest.TestCase):

    def setUp(self):
        self.repo_root = PROJECT_ROOT
        self.registry = load_registry(self.repo_root / "config" / "official_source_registry.json")
        self.evidence_root = self.repo_root / "operations-review" / "governed-official-evidence-v1"
        self.sidecar_dir = self.repo_root / "derived" / "annual_financial_ocr_materialization_v1"

    def test_bounded_cohort_and_preserved_terminal_states(self):
        """Active cohort is strictly GAS and VRE; MWG and VIC remain blocked."""
        self.assertEqual(ACTIVE_COHORT, ("GAS", "VRE"))
        self.assertEqual(PRESERVED_TERMINAL_COHORT["MWG"], "NOT_READY_REDIRECT_CHAIN")
        self.assertEqual(PRESERVED_TERMINAL_COHORT["VIC"], "NOT_READY_REPRODUCIBILITY")

    def test_official_source_admission(self):
        """GAS and VRE official routes are admitted under promoted authority."""
        gas_adm = admit(
            "issuer_ir",
            "https://www.pvgas.com.vn/DesktopModules/EasyDNNNews/DocumentDownload.ashx?portalid=0&moduleid=574&articleid=14454&documentid=3253",
            "audited_annual_financial_statements",
            registry=self.registry,
        )
        self.assertEqual(gas_adm["decision"], ADMITTED)
        self.assertEqual(gas_adm["reason"], "admitted_by_registry")

        vre_adm = admit(
            "issuer_ir",
            "https://ir.vincom.com.vn/wp-content/uploads/2026/03/BCTC-hop-nhat-2025-1.pdf",
            "audited_annual_financial_statements",
            registry=self.registry,
        )
        self.assertEqual(vre_adm["decision"], ADMITTED)
        self.assertEqual(vre_adm["reason"], "admitted_by_registry")

    def test_anti_regression_no_embedded_production_financial_facts(self):
        """Verify that runner source code contains ZERO hardcoded authoritative financial values."""
        runner_path = self.repo_root / "tools" / "run_p2c2_corporate_evidence_onboarding.py"
        source_code = runner_path.read_text(encoding="utf-8")

        # Specific known financial values that previously appeared as hardcoded constants
        prohibited_financial_literals = [
            "135129055328395",
            "11571631226008",
            "13040237870138",
            "93568198109790",
            "67653389117937",
            "6876468282085",
            "20573719389418",
            "2971690340782",
            "8837380",
            "6445924",
            "-3262205",
            "61279149",
            "48368203",
            "4434617",
            "5173857",
            "6401081",
        ]

        parsed_ast = ast.parse(source_code)
        numeric_constants = [
            node.value
            for node in ast.walk(parsed_ast)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
        ]

        for lit in prohibited_financial_literals:
            num_val = int(lit)
            self.assertNotIn(
                num_val,
                numeric_constants,
                f"Prohibited financial value {lit} found hardcoded in production runner!",
            )

    def test_document_qualification_criteria(self):
        """Retained official documents meet strict audited annual consolidated criteria."""
        manifest_path = self.evidence_root / "official_document_acquisition_manifest.json"
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        for ticker in ACTIVE_COHORT:
            recs = [r for r in manifest["records"] if r["ticker"] == ticker]
            self.assertTrue(len(recs) >= 1)
            rec = recs[-1]
            qual = qualify_retained_document(
                rec,
                evidence_root=self.evidence_root,
                registry=self.registry,
            )
            self.assertEqual(qual.qualification_status, QUALIFICATION_SUCCESS_STATUS)
            self.assertEqual(qual.document_class, "audited_annual_financial_statements")
            self.assertEqual(qual.statement_scope, "consolidated")
            self.assertEqual(qual.audit_status, "audited")
            self.assertEqual(qual.periodicity, "annual")

    def test_end_to_end_onboarding_and_zero_ticker_materializers(self):
        """End-to-end execution onboards GAS and VRE with zero ticker-specific materializers."""
        result = execute_p2c2_onboarding(
            self.repo_root,
            evidence_root=self.evidence_root,
            sidecar_dir=self.sidecar_dir,
            generated_at="2026-08-19T14:30:00Z",
        )

        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["active_cohort_size"], 2)
        self.assertEqual(result["successful_onboarded_count"], 2)
        self.assertEqual(result["end_to_end_onboarding_rate"], 1.0)
        self.assertEqual(result["new_ticker_specific_materializer_count"], 0)
        self.assertEqual(result["total_canonical_facts_emitted"], 16)
        self.assertEqual(
            result["governance_audit"]["production_fact_source"],
            "GENERIC_TEMPLATE_RECOGNITION_OCR_EXTRACTION",
        )
        self.assertEqual(result["governance_audit"]["document_qualification_persisted"], "YES")
        self.assertEqual(result["governance_audit"]["persisted_citation_lineage"], "16 / 16")

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

    def test_panel_derived_metrics_and_roe_proxy(self):
        """Multi-period panel derived ratios are properly computed with ENDING_EQUITY_ROE_PROXY semantics."""
        result = execute_p2c2_onboarding(
            self.repo_root,
            evidence_root=self.evidence_root,
            sidecar_dir=self.sidecar_dir,
            generated_at="2026-08-19T14:30:00Z",
        )

        gas_panel = result["panels_by_issuer"]["GAS"]
        gas_derived = gas_panel["derived_metrics"]["2025"]
        self.assertAlmostEqual(gas_derived["cash_flow_to_net_income"]["value"], 1.1424, places=3)
        self.assertAlmostEqual(gas_derived["debt_to_equity"]["value"], 0.0439, places=3)
        self.assertAlmostEqual(gas_derived["roe_proxy"]["value"], 0.1687, places=3)
        self.assertEqual(gas_derived["net_debt"]["status"], "QUALIFIED")

        vre_panel = result["panels_by_issuer"]["VRE"]
        vre_derived = vre_panel["derived_metrics"]["2025"]
        self.assertAlmostEqual(vre_derived["cash_flow_to_net_income"]["value"], -0.5061, places=3)
        self.assertAlmostEqual(vre_derived["debt_to_equity"]["value"], 0.1323, places=3)
        self.assertAlmostEqual(vre_derived["roe_proxy"]["value"], 0.1333, places=3)
        self.assertEqual(vre_derived["net_debt"]["status"], "QUALIFIED")

    def test_readiness_report_generation(self):
        """Readiness report contains required tables, metrics, and invariant checks."""
        result = execute_p2c2_onboarding(
            self.repo_root,
            evidence_root=self.evidence_root,
            sidecar_dir=self.sidecar_dir,
            generated_at="2026-08-19T14:30:00Z",
        )
        report = generate_readiness_report(result)

        self.assertIn("# Phase 2 / P2-D: Generic Financial Statement Template Recognition & Extraction Report", report)
        self.assertIn("ONBOARDING_SUCCESS", report)
        self.assertIn("NOT_READY_REDIRECT_CHAIN", report)
        self.assertIn("NOT_READY_REPRODUCIBILITY", report)
        self.assertIn("ENDING_EQUITY_ROE_PROXY", report)
        self.assertIn("GENERIC_TEMPLATE_RECOGNITION_OCR_EXTRACTION", report)


if __name__ == "__main__":
    unittest.main()
