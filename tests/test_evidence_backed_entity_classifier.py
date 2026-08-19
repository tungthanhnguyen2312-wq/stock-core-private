"""Unit and integration tests for Phase 2 / P2-E evidence-backed entity classification foundation.

Covers:
1. Canonical Entity Classification Schema & Dataclasses.
2. Legal Charter & Form Code Recognition (Corporate, Bank, Securities, Insurance, Finance Company).
3. Fail-Closed Unknown Semantics (Absence of evidence remains UNKNOWN, never default to corporate).
4. Conflict & Ambiguity Resolution (Contradictory evidence across sources yields CONFLICT).
5. Curated Seed Authority Integration & Consistency.
6. Temporal Provenance Preservation (effective_from, knowledge_available_at, verified_at).
7. Downstream Financial Applicability Integration (EBITDA, Debt-to-Equity, Net Debt).
8. AST Anti-Regression Governance (Zero ticker branches in production classifier).
9. End-to-End Evaluation Runner & Artifact Generation.
"""

import ast
import json
from pathlib import Path
import unittest

from entity_classification_contract import (
    CONTRACT_VERSION,
    ClassificationStatus,
    ConfidenceSemantics,
    EntityClass,
    EntityClassificationRecord,
    EvidenceTier,
    SCHEMA_VERSION,
    compute_classification_evidence_id,
)
from evidence_backed_entity_classifier import (
    TICKER_SPECIFIC_EXTRACTION_BRANCH_COUNT,
    _normalize_text,
    classify_entity,
    evaluate_legal_charter_evidence,
    evaluate_line_item_marker_evidence,
    evaluate_statement_form_evidence,
)
from financial_entity_applicability import evaluate_ticker, metric_applicability
from multi_period_financial_panel import compute_bounded_derived_metrics, evaluate_sector_applicability
from tools.run_p2e_entity_classification_foundation import (
    execute_entity_classification_evaluation,
    generate_readiness_report,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


class EntityClassificationContractTests(unittest.TestCase):
    """Tests for entity classification schema and deterministic evidence hashing."""

    def test_schema_and_contract_constants(self):
        self.assertEqual(SCHEMA_VERSION, "1.0.0")
        self.assertEqual(CONTRACT_VERSION, "entity_classification_contract/v1")
        self.assertEqual(EntityClass.CORPORATE.value, "corporate")
        self.assertEqual(EntityClass.BANK.value, "bank")
        self.assertEqual(EntityClass.SECURITIES.value, "securities")
        self.assertEqual(EntityClass.INSURANCE.value, "insurance")
        self.assertEqual(EntityClass.FINANCE_COMPANY.value, "finance_company")
        self.assertEqual(EntityClass.UNKNOWN.value, "unknown")

    def test_deterministic_evidence_id(self):
        ev_id_1 = compute_classification_evidence_id(
            issuer_identity="candidate:123",
            ticker="ABC",
            entity_class="corporate",
            classification_status="QUALIFIED",
            source_id="test_source",
            evidence_payload={"name": "CTCP ABC"},
        )
        ev_id_2 = compute_classification_evidence_id(
            issuer_identity="candidate:123",
            ticker="ABC",
            entity_class="corporate",
            classification_status="QUALIFIED",
            source_id="test_source",
            evidence_payload={"name": "CTCP ABC"},
        )
        self.assertEqual(ev_id_1, ev_id_2)
        self.assertEqual(len(ev_id_1), 64)


class EvidenceBackedClassifierTests(unittest.TestCase):
    """Tests for generic evidence-backed classification logic."""

    def test_legal_charter_bank_recognition(self):
        cls, reason, markers = evaluate_legal_charter_evidence("Ngân hàng TMCP Ngoại thương Việt Nam")
        self.assertEqual(cls, EntityClass.BANK)
        self.assertIn("charter_matches_bank_descriptor", reason)

    def test_legal_charter_securities_recognition(self):
        cls, reason, markers = evaluate_legal_charter_evidence("Công ty Cổ phần Chứng khoán SSI")
        self.assertEqual(cls, EntityClass.SECURITIES)
        self.assertIn("charter_matches_securities_descriptor", reason)

    def test_legal_charter_insurance_recognition(self):
        cls, reason, markers = evaluate_legal_charter_evidence("Tổng Công ty Cổ phần Bảo hiểm Bảo Việt")
        self.assertEqual(cls, EntityClass.INSURANCE)
        self.assertIn("charter_matches_insurance_descriptor", reason)

    def test_legal_charter_finance_company_recognition(self):
        cls, reason, markers = evaluate_legal_charter_evidence("Công ty Tài chính Cổ phần Điện lực")
        self.assertEqual(cls, EntityClass.FINANCE_COMPANY)
        self.assertIn("charter_matches_finance_company_descriptor", reason)

    def test_statement_form_code_corporate(self):
        texts = ["BẢNG CÂN ĐỐI KẾ TOÁN", "Mẫu số B 01-DN/HN", "Ban hành theo Thông tư 202/2014/TT-BTC"]
        cls, reason, codes = evaluate_statement_form_evidence(texts)
        self.assertEqual(cls, EntityClass.CORPORATE)

    def test_statement_form_code_bank(self):
        texts = ["BẢNG CÂN ĐỐI KẾ TOÁN", "Mẫu số B 01-NH/HN", "Ban hành theo Thông tư 49/2014/TT-NHNN"]
        cls, reason, codes = evaluate_statement_form_evidence(texts)
        self.assertEqual(cls, EntityClass.BANK)

    def test_statement_form_code_securities(self):
        texts = ["BÁO CÁO TÌNH HÌNH TÀI CHÍNH", "Mẫu số B 01-CK/HN", "Thông tư 334/2016/TT-BTC"]
        cls, reason, codes = evaluate_statement_form_evidence(texts)
        self.assertEqual(cls, EntityClass.SECURITIES)

    def test_line_item_marker_credit_institution(self):
        bs_items = ["deposits_from_customers", "balances_with_the_sbv"]
        is_items = ["net_interest_income", "provision_for_credit_losses"]
        cls, reason, details = evaluate_line_item_marker_evidence(bs_items, is_items)
        self.assertEqual(cls, EntityClass.BANK)

    def test_line_item_marker_securities(self):
        bs_items = ["customerss_deposits_for_securities_trading", "available_for_sale_financial_assets_afs"]
        is_items = ["revenue_from_securities_custody_services", "revenue_from_investment_advisory_services"]
        cls, reason, details = evaluate_line_item_marker_evidence(bs_items, is_items)
        self.assertEqual(cls, EntityClass.SECURITIES)

    def test_line_item_marker_insurance(self):
        is_items = ["total_net_revenue_from_insurance_business", "claim_and_maturity_payment_expenses"]
        cls, reason, details = evaluate_line_item_marker_evidence(None, is_items)
        self.assertEqual(cls, EntityClass.INSURANCE)

    def test_fail_closed_unknown_when_evidence_absent(self):
        rec = classify_entity(
            issuer_identity="candidate:unknown1",
            ticker="XYZ",
            legal_name="XYZ Global Investment",  # No positive Vietnamese enterprise charter or statement proof
        )
        self.assertEqual(rec.entity_class, EntityClass.UNKNOWN)
        self.assertEqual(rec.classification_status, ClassificationStatus.UNKNOWN)
        self.assertEqual(rec.confidence_semantics, ConfidenceSemantics.UNPROVEN_ABSENCE)

        # Test legal_name=None as well
        rec_none = classify_entity(
            issuer_identity="candidate:unknown2",
            ticker="NONE",
            legal_name=None,
        )
        self.assertEqual(rec_none.entity_class, EntityClass.UNKNOWN)
        self.assertEqual(rec_none.classification_status, ClassificationStatus.UNKNOWN)

    def test_conflict_resolution_across_contradictory_evidence(self):
        # Bank charter name vs Securities form code
        rec = classify_entity(
            issuer_identity="candidate:conflict1",
            ticker="CFL",
            legal_name="Ngân hàng TMCP Quốc tế",
            statement_texts=["BÁO CÁO Mẫu số B 01-CK/HN Thông tư 210/2014/TT-BTC"],
        )
        self.assertEqual(rec.entity_class, EntityClass.UNKNOWN)
        self.assertEqual(rec.classification_status, ClassificationStatus.CONFLICT)
        self.assertEqual(rec.confidence_semantics, ConfidenceSemantics.CONTRADICTORY_EVIDENCE)
        self.assertIn("CONFLICT", rec.classification_reason)

    def test_seed_profile_conflict_resolution(self):
        # Seed says bank, but primary evidence is general corporate
        rec = classify_entity(
            issuer_identity="candidate:conflict2",
            ticker="XYZ",
            legal_name="Công ty Cổ phần May Xuất Khẩu",
            curated_seed_profile="bank",
        )
        self.assertEqual(rec.entity_class, EntityClass.UNKNOWN)
        self.assertEqual(rec.classification_status, ClassificationStatus.CONFLICT)


class DownstreamApplicabilityIntegrationTests(unittest.TestCase):
    """Tests verifying that classified entity_type feeds downstream applicability correctly."""

    def test_corporate_downstream_applicability(self):
        app = metric_applicability({"issuer_entity_type": "corporate"}, "ebitda")
        self.assertEqual(app["status"], "applicable_subject_to_inputs")

        # Multi-period panel sector applicability
        state, reasons = evaluate_sector_applicability(ticker="HPG", entity_type="corporate", canonical_metric="debt_to_equity")
        self.assertEqual(state.value, "APPLICABLE")
        self.assertIn("CORPORATE_DEBT_RATIO_APPLICABLE", reasons)

    def test_bank_downstream_applicability(self):
        app = metric_applicability({"issuer_entity_type": "bank"}, "ebitda")
        self.assertEqual(app["status"], "not_applicable")
        self.assertIn("p_b", app["substitute_metrics"])

        # Multi-period panel sector applicability fails closed on financial intermediaries
        state, reasons = evaluate_sector_applicability(ticker="VCB", entity_type="bank", canonical_metric="debt_to_equity")
        self.assertEqual(state.value, "NOT_APPLICABLE")
        self.assertIn("SECTOR_INAPPROPRIATE_FINANCIAL_INTERMEDIARY_DEBT_RATIO", reasons)

    def test_securities_downstream_applicability(self):
        app = metric_applicability({"issuer_entity_type": "securities"}, "ebitda")
        self.assertEqual(app["status"], "not_applicable")
        self.assertIn("p_b", app["substitute_metrics"])

        state, reasons = evaluate_sector_applicability(ticker="SSI", entity_type="securities", canonical_metric="debt_to_equity")
        self.assertEqual(state.value, "NOT_APPLICABLE")
        self.assertIn("SECTOR_INAPPROPRIATE_FINANCIAL_INTERMEDIARY_DEBT_RATIO", reasons)

    def test_insurance_downstream_applicability(self):
        app = metric_applicability({"issuer_entity_type": "insurance"}, "ebitda")
        self.assertEqual(app["status"], "not_applicable")

        state, reasons = evaluate_sector_applicability(ticker="BVH", entity_type="insurance", canonical_metric="debt_to_equity")
        self.assertEqual(state.value, "NOT_APPLICABLE")

    def test_unknown_downstream_applicability(self):
        app = metric_applicability({"issuer_entity_type": "unknown"}, "ebitda")
        self.assertEqual(app["status"], "insufficient_evidence")

        state, reasons = evaluate_sector_applicability(ticker="XYZ", entity_type="unknown", canonical_metric="debt_to_equity")
        self.assertEqual(state.value, "UNKNOWN")
        self.assertIn("INSUFFICIENT_SECTOR_EVIDENCE", reasons)


class ZeroTickerBranchGovernanceTests(unittest.TestCase):
    """Governance tests ensuring zero hardcoded ticker logic in production classification code."""

    def test_zero_ticker_branches_in_classifier(self):
        code_path = REPO_ROOT / "evidence_backed_entity_classifier.py"
        tree = ast.parse(code_path.read_text(encoding="utf-8"))

        forbidden_tickers = {"GAS", "VRE", "MWG", "VIC", "VNM", "HPG", "VCB", "SSI", "BID", "MBB", "TCB"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val = node.value.strip().upper()
                if val in forbidden_tickers:
                    self.fail(f"Forbidden hardcoded ticker '{val}' found in classifier: {node}")


class EndToEndP2EEvaluationTests(unittest.TestCase):
    """Integration tests for the full P2-E evaluation pipeline."""

    def test_execute_p2e_evaluation(self):
        result = execute_entity_classification_evaluation(
            REPO_ROOT,
            generated_at="2026-08-19T15:00:00Z",
        )

        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["authority_status"], "PROMOTION_REVIEW_READY")

        scale = result["scale_metrics"]
        self.assertEqual(scale["total_canonical_candidates"], 3250)
        self.assertEqual(scale["listed_equity_candidates"], 1660)
        self.assertEqual(scale["previously_positively_classified"], 20)
        self.assertEqual(scale["previously_unknown"], 1640)
        self.assertEqual(scale["validation_unknown_cohort"], 20)
        self.assertEqual(scale["validation_total_evaluated"], 40)
        self.assertEqual(scale["ticker_specific_extraction_branch_count"], 0)

        # Part A results (20 known)
        part_a = result["part_a_known_results"]
        self.assertEqual(len(part_a), 20)
        for item in part_a:
            self.assertEqual(item["classification"]["classification_status"], "QUALIFIED")

        # Part B results (20 unknown cohort)
        part_b = result["part_b_unknown_results"]
        self.assertEqual(len(part_b), 20)
        for item in part_b:
            self.assertEqual(item["classification"]["classification_status"], "QUALIFIED")

        # Readiness report generation
        report = generate_readiness_report(result)
        self.assertIn("# Phase 2 / P2-E: Evidence-Backed Entity Classification Scale-Out Foundation Report", report)
        self.assertIn("PROMOTION_REVIEW_READY", report)
        self.assertIn("Total Canonical Candidates", report)


if __name__ == "__main__":
    unittest.main()
