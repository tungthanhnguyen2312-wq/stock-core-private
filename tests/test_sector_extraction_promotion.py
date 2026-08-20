"""Phase 2 / P2-F3: Contract and unit tests for Bounded Generic Sector Extraction Authority Promotion."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from entity_classification_contract import (
    EntityClass,
    load_promoted_entity_classifications,
    load_seed_profiles,
    resolve_layered_entity_classification,
)
from generic_financial_canonicalizer import (
    LegacyModuleRole,
    classify_legacy_materializers,
)
from sector_financial_taxonomy import (
    AuthoritativeSectorFact,
    PromotedScopeEvaluationState,
    ReconciliationStatus,
    SectorAuthorityTier,
    StatementFormFamily,
    evaluate_sector_extraction_authority_scope,
    load_promoted_sector_extractions,
    reconcile_and_resolve_authoritative_sector_facts,
)
from financial_disclosure_recognizer import (
    extract_sector_facts_from_sidecar,
)


class TestSectorExtractionPromotion(unittest.TestCase):

    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.config_path = self.root / "config" / "promoted_sector_extractions.json"

        # VCB test fixtures
        self.vcb_manifest = {
            "ticker": "VCB",
            "document_id": "aec971a73211a62c73167acc9f187a1ab1d88e9d1db5b73b399a598e9325fd2a",
            "sha256": "9deccc3518e23302d00353b4d371a9dd251b67b12f9fe58a4da4ad3c727e99f8",
            "reporting_period": "2024",
        }
        self.vcb_sidecar = {
            "document_id": self.vcb_manifest["document_id"],
            "document_sha256": self.vcb_manifest["sha256"],
            "pages": [
                {
                    "page": 8,
                    "text": "NGÂN HÀNG TMCP NGOẠI THƯƠNG VIỆT NAM\r\nBẢNG CÂN ĐỐI KẾ TOÁN HỢP NHẤT Mẫu số B 02/TCTD-HN\r\ntại ngày 31 tháng 12 năm 2024\r\nĐơn vị tính: triệu VND\r\nIII. Cho vay khách hàng 1.418.015.724\r\nB. TỔNG CỘNG TÀI SẢN 2.085.873.522\r\nIII. Tiền gửi của khách hàng 1.514.664.850\r\nB. Nợ phải trả 1.889.664.354\r\nVIII. Vốn và các quỹ 196.209.168\r\nLợi ích của cổ đông không kiểm soát 96.261\r\n",
                },
                {
                    "page": 9,
                    "text": "NGÂN HÀNG TMCP NGOẠI THƯƠNG VIỆT NAM\r\nBÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT Mẫu số B 03/TCTD-HN\r\ncho năm tài chính kết thúc ngày 31 tháng 12 năm 2024\r\nĐơn vị tính: triệu VND\r\n1. Thu nhập lãi và các khoản thu nhập tương tự 23 93.654.841\r\n2. Chi phí lãi và các chi phí tương tự 24 (38.249.106)\r\nI. Thu nhập lãi thuần 55.405.735\r\nII. Lãi thuần từ hoạt động dịch vụ 25 5.136.561\r\nIII. Lãi thuần từ hoạt động kinh doanh ngoại hối và vàng 26 5.291.751\r\nIV. Lãi thuần từ mua bán chứng khoán kinh doanh 27 62.123\r\nV. Lãi thuần từ mua bán chứng khoán đầu tư 28 3.444\r\nVIII. Chi phí hoạt động (23.027.363)\r\nIX. Lợi nhuận thuần từ hoạt động kinh doanh trước chi phí dự phòng rủi ro tín dụng 45.551.133\r\nX. Chi phí dự phòng rủi ro tín dụng (3.314.998)\r\nXI. Tổng lợi nhuận trước thuế 42.236.135\r\nXIV. Lợi nhuận sau thuế 33.853.117\r\nLợi nhuận sau thuế của cổ đông ngân hàng mẹ 33.831.386\r\n",
                },
            ],
        }
        self.specialized_vcb_facts = {
            "customer_loans_net": 1_418_015_724_000_000,
            "total_assets": 2_085_873_522_000_000,
            "customer_deposits": 1_514_664_850_000_000,
            "total_liabilities": 1_889_664_354_000_000,
            "total_equity": 196_209_168_000_000,
            "minority_interest": 96_261_000_000,
            "interest_income": 93_654_841_000_000,
            "interest_expense": 38_249_106_000_000,
            "net_interest_income": 55_405_735_000_000,
            "operating_expenses": 23_027_363_000_000,
            "operating_profit_before_provision_for_credit_losses": 45_551_133_000_000,
            "provision_for_credit_losses": 3_314_998_000_000,
            "profit_before_tax": 42_236_135_000_000,
            "net_profit_total": 33_853_117_000_000,
            "net_profit_parent": 33_831_386_000_000,
        }

        # SSI test fixtures
        self.ssi_manifest = {
            "ticker": "SSI",
            "document_id": "3fd72890fe43b78071d641b8d89523d4aa28e340d4f1904a90667f8c1d794bf0",
            "sha256": "38e5b9ba2fc951120be813b09df05fa2d8b152b3b95443c6cd108de8abf03b74",
            "reporting_period": "2024",
        }
        self.ssi_sidecar = {
            "document_id": self.ssi_manifest["document_id"],
            "document_sha256": self.ssi_manifest["sha256"],
            "pages": [
                {
                    "page": 8,
                    "text": "SSI Securities Corporation\r\nCONSOLIDATED STATEMENT OF FINANCIAL POSITION B01-CTCK/HN\r\nas at 31 December 2024 Currency: VND\r\n111 | Financial assets at fair value through profit or loss (FVTPL) | 42,438,121,481,401\r\n114 | Loans | 21,998,601,885,375\r\n",
                },
                {
                    "page": 9,
                    "text": "270 | TOTAL ASSETS | 73,507,302,559,722\r\n",
                },
                {
                    "page": 10,
                    "text": "310 | 1. Current liabilities | 46,599,438,522,989\r\n311 | 1. Short-term borrowings and financial leases | 21 | 45,501,969,699,137\r\n400 | D. OWNERS’ EQUITY | 29 | 26,826,650,611,768\r\n411 | 1. Share capital | 20,713,065,094,108\r\n",
                },
                {
                    "page": 14,
                    "text": "CONSOLIDATED INCOME STATEMENT B02-CTCK/HN\r\n20 | Total operating revenue | 8,529,279,575,474\r\n06 | Revenue from brokerage services | 1,667,430,605,344\r\n01 | Gain from financial assets at fair value through profit or loss (FVTPL) | 4,021,594,603,243\r\n21 | Loss from financial assets at fair value through profit or loss (FVTPL) | 1,458,465,074,277\r\n",
                },
                {
                    "page": 15,
                    "text": "52 | Borrowing costs | 1,505,764,783,295\r\n70 | PROFIT AFTER TAX | 2,845,109,032,672\r\n71 | Profit after tax attributable to the Parent Company’s owners | 2,835,023,120,364\r\n",
                },
                {
                    "page": 16,
                    "text": "72 | Earnings per share | 1,554\r\n",
                },
                {
                    "page": 65,
                    "text": "NOTES TO THE CONSOLIDATED FINANCIAL STATEMENTS B09-CTCK\r\nOutstanding shares - Ordinary shares 1,961,872,450\r\n",
                },
            ],
        }
        self.specialized_ssi_facts = {
            "current_liabilities": 46_599_438_522_989,
        }

    def test_vcb_generic_authority_resolves_to_15_matched_facts(self):
        """Proof Criterion 1: VCB generic authority resolves exactly to the 15 previously matched FY2024 facts."""
        vcb_extracted = extract_sector_facts_from_sidecar(
            ticker="VCB",
            qualification=self.vcb_manifest,
            sidecar=self.vcb_sidecar,
            reporting_period="2024",
        )
        self.assertEqual(len(vcb_extracted), 15)

        promoted = reconcile_and_resolve_authoritative_sector_facts(
            generic_facts=vcb_extracted,
            specialized_observations=self.specialized_vcb_facts,
            config_path=self.config_path,
        )
        self.assertEqual(len(promoted), 15)

        for fact in promoted:
            self.assertTrue(fact.is_positive_authority)
            self.assertEqual(fact.authority_tier, SectorAuthorityTier.GENERIC_SECTOR_TAXONOMY_PROMOTED)
            self.assertEqual(fact.reconciliation_status, ReconciliationStatus.EXACT_MATCH)
            self.assertTrue(fact.specialized_corroboration)
            self.assertEqual(fact.value, self.specialized_vcb_facts[fact.canonical_metric])

    def test_ssi_generic_authority_preserves_overlap_and_exposes_authorized_facts(self):
        """Proof Criterion 2: SSI generic authority preserves qualified overlap and exposes additional facts."""
        ssi_extracted = extract_sector_facts_from_sidecar(
            ticker="SSI",
            qualification=self.ssi_manifest,
            sidecar=self.ssi_sidecar,
            reporting_period="2024",
        )
        self.assertEqual(len(ssi_extracted), 16)

        promoted = reconcile_and_resolve_authoritative_sector_facts(
            generic_facts=ssi_extracted,
            specialized_observations=self.specialized_ssi_facts,
            config_path=self.config_path,
        )
        self.assertEqual(len(promoted), 16)

        by_metric = {f.canonical_metric: f for f in promoted}

        # Overlapping fact: current_liabilities
        cl_fact = by_metric["current_liabilities"]
        self.assertTrue(cl_fact.is_positive_authority)
        self.assertEqual(cl_fact.authority_tier, SectorAuthorityTier.GENERIC_SECTOR_TAXONOMY_PROMOTED)
        self.assertEqual(cl_fact.reconciliation_status, ReconciliationStatus.EXACT_MATCH)
        self.assertTrue(cl_fact.specialized_corroboration)
        self.assertEqual(cl_fact.value, 46_599_438_522_989)

        # Additional generic facts: e.g. brokerage_revenue, total_assets, total_equity
        brok_fact = by_metric["brokerage_revenue"]
        self.assertTrue(brok_fact.is_positive_authority)
        self.assertEqual(brok_fact.authority_tier, SectorAuthorityTier.GENERIC_SECTOR_TAXONOMY_PROMOTED)
        self.assertEqual(brok_fact.reconciliation_status, ReconciliationStatus.GENERIC_EVIDENCED_PROMOTED)
        self.assertFalse(brok_fact.specialized_corroboration)
        self.assertEqual(brok_fact.value, 1_667_430_605_344)

    def test_specialized_paths_remain_regression_and_reference_only(self):
        """Proof Criterion 3: Specialized paths remain regression/reference only after promotion."""
        roles = classify_legacy_materializers()
        self.assertEqual(
            roles["ssi_official_financial_materialization.py"]["role"],
            LegacyModuleRole.GENERICALLY_SUPERSEDED.value,
        )
        self.assertEqual(
            roles["ssi_official_financial_materialization.py"]["migration_status"],
            "SUPERSEDED_BY_GENERIC_SECTOR_TAXONOMY_RETAINED_FOR_REFERENCE",
        )

    def test_injected_conflict_fails_closed(self):
        """Proof Criterion 4: Generic-vs-specialized conflict fails closed as CONFLICT without choosing a value."""
        ssi_extracted = extract_sector_facts_from_sidecar(
            ticker="SSI",
            qualification=self.ssi_manifest,
            sidecar=self.ssi_sidecar,
            reporting_period="2024",
        )

        # Inject corrupt specialized value
        conflicted_specialized = {"current_liabilities": 111_222_333}
        promoted = reconcile_and_resolve_authoritative_sector_facts(
            generic_facts=ssi_extracted,
            specialized_observations=conflicted_specialized,
            config_path=self.config_path,
        )

        by_metric = {f.canonical_metric: f for f in promoted}
        cl_fact = by_metric["current_liabilities"]

        self.assertFalse(cl_fact.is_positive_authority)
        self.assertIsNone(cl_fact.value)
        self.assertEqual(cl_fact.authority_tier, SectorAuthorityTier.CONFLICT_UNRESOLVED)
        self.assertEqual(cl_fact.reconciliation_status, ReconciliationStatus.CONFLICT)
        self.assertIn("CONFLICT", cl_fact.reason_codes[0])

    def test_insurance_finance_company_unknown_remain_non_authoritative(self):
        """Proof Criterion 5: Insurance, Finance Company, UNKNOWN, and unpromoted tickers remain non-authoritative."""
        # Unpromoted Bank ticker (ACB)
        acb_scope, acb_msg = evaluate_sector_extraction_authority_scope(
            ticker="ACB",
            entity_class=EntityClass.BANK,
            config_path=self.config_path,
        )
        self.assertEqual(acb_scope, PromotedScopeEvaluationState.UNPROMOTED_ISSUER)

        # Unpromoted Securities ticker (AAS)
        aas_scope, aas_msg = evaluate_sector_extraction_authority_scope(
            ticker="AAS",
            entity_class=EntityClass.SECURITIES,
            config_path=self.config_path,
        )
        self.assertEqual(aas_scope, PromotedScopeEvaluationState.UNPROMOTED_ISSUER)

        # Insurance (BVH)
        bvh_scope, bvh_msg = evaluate_sector_extraction_authority_scope(
            ticker="BVH",
            entity_class=EntityClass.INSURANCE,
            config_path=self.config_path,
        )
        self.assertEqual(bvh_scope, PromotedScopeEvaluationState.UNPROMOTED_SECTOR)

        # Finance Company (EVF)
        evf_scope, evf_msg = evaluate_sector_extraction_authority_scope(
            ticker="EVF",
            entity_class=EntityClass.FINANCE_COMPANY,
            config_path=self.config_path,
        )
        self.assertEqual(evf_scope, PromotedScopeEvaluationState.UNPROMOTED_SECTOR)

        # Unknown (ZZZ)
        zzz_scope, zzz_msg = evaluate_sector_extraction_authority_scope(
            ticker="ZZZ",
            entity_class=EntityClass.UNKNOWN,
            config_path=self.config_path,
        )
        self.assertEqual(zzz_scope, PromotedScopeEvaluationState.UNRESOLVED_ENTITY_CLASS)

    def test_zero_ticker_specific_branches_in_production(self):
        """Proof Criterion 6: No ticker/SHA/host-specific production extraction branches exist."""
        prod_files = [
            self.root / "sector_financial_taxonomy.py",
            self.root / "financial_disclosure_recognizer.py",
        ]
        forbidden_symbols = ["VCB", "SSI", "ABI", "EVF", "BVH"]
        for p_file in prod_files:
            content = p_file.read_text(encoding="utf-8")
            for sym in forbidden_symbols:
                branches = [line for line in content.splitlines() if f'"{sym}"' in line or f"'{sym}'" in line]
                self.assertEqual(
                    branches,
                    [],
                    f"Forbidden hardcoded symbol {sym} found in {p_file.name}: {branches}",
                )

    def test_promoted_sector_extractions_config_integrity(self):
        """Verify config/promoted_sector_extractions.json schema, hashes, and scope."""
        self.assertTrue(self.config_path.is_file())
        data = load_promoted_sector_extractions(self.config_path)

        self.assertEqual(data["schema_version"], "1.0.0")
        self.assertEqual(data["contract_version"], "sector_financial_taxonomy/v1")
        self.assertEqual(data["authority_type"], "PROMOTED_SECTOR_EXTRACTION_REGISTRY")
        self.assertEqual(data["authority_scope"], "BOUNDED_PROOF_CORPUS_ONLY")
        self.assertEqual(data["historical_pit_authority"], "NOT_ESTABLISHED")

        promoted_sectors = data["promoted_sectors"]
        self.assertEqual(set(promoted_sectors.keys()), {"bank", "securities"})
        self.assertEqual(promoted_sectors["bank"]["proof_ticker"], "VCB")
        self.assertEqual(promoted_sectors["bank"]["promoted_fact_count"], 15)
        self.assertEqual(promoted_sectors["securities"]["proof_ticker"], "SSI")
        self.assertEqual(promoted_sectors["securities"]["promoted_fact_count"], 16)

    def test_immutable_seed_profiles_and_promoted_classifications_preserved(self):
        """Verify seed profiles (20) and promoted entity classifications (20) remain unmutated."""
        seed_path = self.root / "config" / "ticker_entity_profiles.csv"
        seed_profiles = load_seed_profiles(seed_path)
        self.assertEqual(len(seed_profiles), 20)

        promoted_class_path = self.root / "config" / "promoted_entity_classifications.json"
        promoted_classes = load_promoted_entity_classifications(promoted_class_path)
        self.assertEqual(len(promoted_classes), 20)


if __name__ == "__main__":
    unittest.main()
