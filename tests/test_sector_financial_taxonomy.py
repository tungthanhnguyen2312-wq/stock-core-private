"""Unit and contract tests for Phase 2 / P2-F1 Sector Financial Taxonomy & Disclosure Parsing Foundation."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from entity_classification_contract import (
    ClassificationStatus,
    EntityClass,
    resolve_layered_entity_classification,
)
from sector_financial_taxonomy import (
    ALL_SECTOR_METRICS,
    BANK_METRICS,
    CORPORATE_METRICS,
    FINANCE_COMPANY_METRICS,
    INSURANCE_METRICS,
    MetricApplicabilityState,
    REAL_DATA_PROOF_CORPUS,
    REAL_DATA_VALIDATED_SECTORS,
    SCHEMA_ONLY_SECTORS,
    SECURITIES_METRICS,
    SECTOR_INAPPLICABLE_CORPORATE_METRICS,
    SECTOR_PRIMARY_STATEMENT_FORMS,
    StatementFormFamily,
    evaluate_metric_sector_applicability,
)
from financial_disclosure_recognizer import (
    DisclosureSectionType,
    ExtractedSectorFact,
    compute_sector_citation_id,
    extract_note_headings,
    extract_note_numbers_from_text,
    extract_sector_facts_from_sidecar,
    recognize_disclosure_page,
    recognize_unit_scale_from_evidence,
)


class TestSectorFinancialTaxonomy(unittest.TestCase):

    def test_proof_corpus_inventory_distinguishes_real_vs_schema_only(self):
        """Verify bank and securities are real-data validated while insurance & finance company are schema-only."""
        self.assertEqual(REAL_DATA_VALIDATED_SECTORS, ("bank", "securities"))
        self.assertEqual(SCHEMA_ONLY_SECTORS, ("insurance", "finance_company"))

        bank_p = REAL_DATA_PROOF_CORPUS[EntityClass.BANK]
        self.assertEqual(bank_p["status"], "REAL_DATA_VALIDATED")
        self.assertTrue(bank_p["proof_available"])

        sec_p = REAL_DATA_PROOF_CORPUS[EntityClass.SECURITIES]
        self.assertEqual(sec_p["status"], "REAL_DATA_VALIDATED")
        self.assertTrue(sec_p["proof_available"])

        ins_p = REAL_DATA_PROOF_CORPUS[EntityClass.INSURANCE]
        self.assertEqual(ins_p["status"], "SCHEMA_SUPPORTED_BUT_NOT_REAL_DATA_VALIDATED")
        self.assertFalse(ins_p["proof_available"])

        fc_p = REAL_DATA_PROOF_CORPUS[EntityClass.FINANCE_COMPANY]
        self.assertEqual(fc_p["status"], "SCHEMA_SUPPORTED_BUT_NOT_REAL_DATA_VALIDATED")
        self.assertFalse(fc_p["proof_available"])

    def test_ordinary_corporate_vs_bank_applicability(self):
        """Verify corporate metrics fail closed on banks and bank metrics fail closed on corporates."""
        # Corporate metrics on Bank -> NOT_APPLICABLE
        for corp_metric in ("ebitda", "ev_ebitda", "total_interest_bearing_debt", "debt_to_equity", "cost_of_goods_sold", "working_capital"):
            res = evaluate_metric_sector_applicability(EntityClass.BANK, corp_metric)
            self.assertEqual(res.applicability, MetricApplicabilityState.NOT_APPLICABLE)
            self.assertTrue(res.is_ordinary_corporate_metric)

        # Bank metrics on Corporate -> UNSUPPORTED_SECTOR_METRIC
        for bank_metric in ("net_interest_income", "customer_deposits", "customer_loans_net"):
            res = evaluate_metric_sector_applicability(EntityClass.CORPORATE, bank_metric)
            self.assertEqual(res.applicability, MetricApplicabilityState.UNSUPPORTED_SECTOR_METRIC)

        # Valid bank metrics on Bank -> APPLICABLE
        res_nii = evaluate_metric_sector_applicability(EntityClass.BANK, "net_interest_income")
        self.assertEqual(res_nii.applicability, MetricApplicabilityState.APPLICABLE)
        self.assertEqual(res_nii.statement_family, "income_statement")

    def test_ordinary_corporate_vs_securities_applicability(self):
        """Verify corporate debt/EBITDA metrics fail closed on securities and securities metrics fail closed on corporates."""
        # Corporate metrics on Securities -> NOT_APPLICABLE
        for corp_metric in ("ebitda", "ev_ebitda", "total_interest_bearing_debt", "debt_to_equity", "cost_of_goods_sold"):
            res = evaluate_metric_sector_applicability(EntityClass.SECURITIES, corp_metric)
            self.assertEqual(res.applicability, MetricApplicabilityState.NOT_APPLICABLE)

        # Securities metrics on Corporate -> UNSUPPORTED_SECTOR_METRIC
        for sec_metric in ("brokerage_revenue", "financial_assets_fvtpl", "loans_balance"):
            res = evaluate_metric_sector_applicability(EntityClass.CORPORATE, sec_metric)
            self.assertEqual(res.applicability, MetricApplicabilityState.UNSUPPORTED_SECTOR_METRIC)

        # Valid securities metrics on Securities -> APPLICABLE
        res_brok = evaluate_metric_sector_applicability(EntityClass.SECURITIES, "brokerage_revenue")
        self.assertEqual(res_brok.applicability, MetricApplicabilityState.APPLICABLE)
        self.assertEqual(res_brok.statement_family, "income_statement")

    def test_unclassified_unknown_entity_fails_closed(self):
        """Verify unknown entity class fails closed."""
        res = evaluate_metric_sector_applicability(EntityClass.UNKNOWN, "net_income")
        self.assertEqual(res.applicability, MetricApplicabilityState.UNKNOWN_ENTITY_CLASS)

    def test_statement_structure_recognition(self):
        """Test primary statement structure recognition across sectors."""
        # Bank Balance Sheet
        bank_bs_text = "NGÂN HÀNG TMCP NGOẠI THƯƠNG VIỆT NAM\r\nBẢNG CÂN ĐỐI KẾ TOÁN HỢP NHẤT Mẫu số B 02/TCTD-HN"
        p_bs = recognize_disclosure_page(bank_bs_text, 8, EntityClass.BANK)
        self.assertEqual(p_bs.section_type, DisclosureSectionType.PRIMARY_STATEMENT)
        self.assertEqual(p_bs.statement_type, "balance_sheet")
        self.assertEqual(p_bs.form_code, "B 02/TCTD-HN")

        # Securities Income Statement
        sec_is_text = "SSI Securities Corporation\r\nCONSOLIDATED INCOME STATEMENT B02-CTCK/HN"
        p_is = recognize_disclosure_page(sec_is_text, 14, EntityClass.SECURITIES)
        self.assertEqual(p_is.section_type, DisclosureSectionType.PRIMARY_STATEMENT)
        self.assertEqual(p_is.statement_type, "income_statement")
        self.assertEqual(p_is.form_code, "B02-CTCK/HN")

        # Notes section
        note_text = "BẢN THUYẾT MINH BÁO CÁO TÀI CHÍNH HỢP NHẤT Mẫu số B 05/TCTD-HN\r\n23. Thu nhập lãi và các khoản thu nhập tương tự"
        p_note = recognize_disclosure_page(note_text, 25, EntityClass.BANK)
        self.assertEqual(p_note.section_type, DisclosureSectionType.NOTES_AND_DISCLOSURES)
        self.assertEqual(p_note.statement_type, "notes")
        self.assertEqual(p_note.form_code, "B 05/TCTD-HN")
        self.assertIn("23", p_note.detected_note_numbers)

    def test_note_number_and_heading_extraction(self):
        """Test parsing of note numbers from Vietnamese and English disclosure texts."""
        sample_text = """
        BẢN THUYẾT MINH BÁO CÁO TÀI CHÍNH
        15. Vốn chủ sở hữu
        Thuyết minh số 21: Vay và nợ thuê tài chính ngắn hạn
        Ghi chú 23. Thu nhập lãi
        Note 29.1 - Undistributed earnings
        """
        nums = extract_note_numbers_from_text(sample_text)
        self.assertIn("15", nums)
        self.assertIn("21", nums)
        self.assertIn("23", nums)
        self.assertIn("29.1", nums)

        headings = extract_note_headings([{"page": 45, "text": sample_text}])
        heading_notes = [h.note_number for h in headings]
        self.assertIn("15", heading_notes)
        self.assertIn("21", heading_notes)
        self.assertIn("23", heading_notes)
        self.assertIn("29.1", heading_notes)

    def test_unit_and_scale_recognition(self):
        """Test scale discovery for VND, triệu VND, tỷ VND."""
        curr1, scale1, _ = recognize_unit_scale_from_evidence("Đơn vị tính: triệu VND")
        self.assertEqual(curr1, "VND")
        self.assertEqual(scale1, 1_000_000)

        curr2, scale2, _ = recognize_unit_scale_from_evidence("Currency: VND")
        self.assertEqual(curr2, "VND")
        self.assertEqual(scale2, 1)

        curr3, scale3, _ = recognize_unit_scale_from_evidence("Đơn vị tính: tỷ đồng")
        self.assertEqual(curr3, "VND")
        self.assertEqual(scale3, 1_000_000_000)

    def test_deterministic_citation_identity(self):
        """Verify citation IDs are deterministic and immutable."""
        c1 = compute_sector_citation_id(
            ticker="VCB",
            metric="net_interest_income",
            reporting_period="2024",
            document_sha256="abc123",
            source_page=9,
            raw_value="55,405,735",
            note_number="23",
        )
        c2 = compute_sector_citation_id(
            ticker="VCB",
            metric="net_interest_income",
            reporting_period="2024",
            document_sha256="abc123",
            source_page=9,
            raw_value="55,405,735",
            note_number="23",
        )
        self.assertEqual(c1, c2)
        self.assertEqual(len(c1), 64)

    def test_vcb_bank_regression_and_extraction(self):
        """Verify generic extraction accurately reproduces cited VCB bank facts."""
        vcb_manifest = {
            "ticker": "VCB",
            "document_id": "vcb_doc_1",
            "sha256": "9deccc3518e23302d00353b4d371a9dd251b67b12f9fe58a4da4ad3c727e99f8",
        }
        vcb_sidecar = {
            "document_id": "vcb_doc_1",
            "document_sha256": "9deccc3518e23302d00353b4d371a9dd251b67b12f9fe58a4da4ad3c727e99f8",
            "pages": [
                {
                    "page": 8,
                    "text": "NGÂN HÀNG TMCP NGOẠI THƯƠNG VIỆT NAM\r\nBẢNG CÂN ĐỐI KẾ TOÁN HỢP NHẤT Mẫu số B 02/TCTD-HN\r\nĐơn vị tính: triệu VND\r\nIII. Cho vay khách hàng 1.418.015.724\r\nB. TỔNG CỘNG TÀI SẢN 2.085.873.522\r\nIII. Tiền gửi của khách hàng 1.514.664.850\r\nVIII. Vốn và các quỹ 196.209.168\r\n",
                },
                {
                    "page": 9,
                    "text": "BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT Mẫu số B 03/TCTD-HN\r\nĐơn vị tính: triệu VND\r\n1. Thu nhập lãi và các khoản thu nhập tương tự 23 93.654.841\r\n2. Chi phí lãi và các chi phí tương tự 24 (38.249.106)\r\nI. Thu nhập lãi thuần 55.405.735\r\nXI. Tổng lợi nhuận trước thuế 42.236.135\r\nLợi nhuận sau thuế của cổ đông ngân hàng mẹ 33.831.386\r\n",
                },
            ],
        }

        facts = extract_sector_facts_from_sidecar(
            ticker="VCB",
            qualification=vcb_manifest,
            sidecar=vcb_sidecar,
            reporting_period="2024",
        )
        by_metric = {f.normalized_metric: f for f in facts}
        
        self.assertEqual(by_metric["interest_income"].value, 93_654_841_000_000)
        self.assertEqual(by_metric["interest_expense"].value, 38_249_106_000_000)
        self.assertEqual(by_metric["net_interest_income"].value, 55_405_735_000_000)
        self.assertEqual(by_metric["profit_before_tax"].value, 42_236_135_000_000)
        self.assertEqual(by_metric["net_profit_parent"].value, 33_831_386_000_000)
        self.assertEqual(by_metric["total_assets"].value, 2_085_873_522_000_000)
        self.assertEqual(by_metric["customer_deposits"].value, 1_514_664_850_000_000)
        self.assertEqual(by_metric["customer_loans_net"].value, 1_418_015_724_000_000)
        self.assertEqual(by_metric["total_equity"].value, 196_209_168_000_000)
        
        # Check cross reference notes
        self.assertEqual(by_metric["interest_income"].note_number, "23")
        self.assertEqual(by_metric["interest_expense"].note_number, "24")

    def test_ssi_securities_regression_and_extraction(self):
        """Verify generic extraction accurately reproduces cited SSI securities facts."""
        ssi_manifest = {
            "ticker": "SSI",
            "document_id": "ssi_doc_1",
            "sha256": "38e5b9ba2fc951120be813b09df05fa2d8b152b3b95443c6cd108de8abf03b74",
        }
        ssi_sidecar = {
            "document_id": "ssi_doc_1",
            "document_sha256": "38e5b9ba2fc951120be813b09df05fa2d8b152b3b95443c6cd108de8abf03b74",
            "pages": [
                {
                    "page": 8,
                    "text": "CONSOLIDATED STATEMENT OF FINANCIAL POSITION B01-CTCK/HN\r\nCurrency: VND\r\n111 | Financial assets at fair value through profit or loss (FVTPL) | 42,438,121,481,401\r\n114 | Loans | 21,998,601,885,375\r\n",
                },
                {
                    "page": 9,
                    "text": "270 | TOTAL ASSETS | 73,507,302,559,722\r\n",
                },
                {
                    "page": 10,
                    "text": "310 | 1. Current liabilities | 46,599,438,522,989\r\n311 | 1. Short-term borrowings and financial leases | 21 | 45,501,969,699,137\r\n400 | D. OWNERS’ EQUITY | 29 | 26,826,650,611,768\r\n",
                },
                {
                    "page": 14,
                    "text": "CONSOLIDATED INCOME STATEMENT B02-CTCK/HN\r\n06 | Revenue from brokerage services | 1,667,430,605,344\r\n01 | Gain from financial assets at fair value through profit or loss (FVTPL) | 4,021,594,603,243\r\n21 | Loss from financial assets at fair value through profit or loss (FVTPL) | 1,458,465,074,277\r\n",
                },
                {
                    "page": 15,
                    "text": "52 | Borrowing costs | 1,505,764,783,295\r\n70 | PROFIT AFTER TAX | 2,845,109,032,672\r\n71 | Profit after tax attributable to the Parent Company’s owners | 2,835,023,120,364\r\n",
                },
            ],
        }

        facts = extract_sector_facts_from_sidecar(
            ticker="SSI",
            qualification=ssi_manifest,
            sidecar=ssi_sidecar,
            reporting_period="2024",
        )
        by_metric = {f.normalized_metric: f for f in facts}

        self.assertEqual(by_metric["financial_assets_fvtpl"].value, 42_438_121_481_401)
        self.assertEqual(by_metric["loans_balance"].value, 21_998_601_885_375)
        self.assertEqual(by_metric["total_assets"].value, 73_507_302_559_722)
        self.assertEqual(by_metric["current_liabilities"].value, 46_599_438_522_989)
        self.assertEqual(by_metric["short_term_borrowings_and_financial_leases"].value, 45_501_969_699_137)
        self.assertEqual(by_metric["total_equity"].value, 26_826_650_611_768)
        self.assertEqual(by_metric["brokerage_revenue"].value, 1_667_430_605_344)
        self.assertEqual(by_metric["fvtpl_gain"].value, 4_021_594_603_243)
        self.assertEqual(by_metric["fvtpl_loss"].value, 1_458_465_074_277)
        self.assertEqual(by_metric["borrowing_costs"].value, 1_505_764_783_295)
        self.assertEqual(by_metric["profit_after_tax_total"].value, 2_845_109_032_672)
        self.assertEqual(by_metric["profit_after_tax_parent"].value, 2_835_023_120_364)

        # Check cross reference note on borrowings
        self.assertEqual(by_metric["short_term_borrowings_and_financial_leases"].note_number, "21")

    def test_schema_only_sectors_fail_closed_on_real_data_extraction(self):
        """Verify BVH (insurance) and EVF (finance company) fail closed on real extraction until proof filing exists."""
        bvh_facts = extract_sector_facts_from_sidecar(
            ticker="BVH",
            qualification={"sha256": "0" * 64, "document_id": "dummy"},
            sidecar={"pages": []},
            reporting_period="2024",
        )
        self.assertEqual(bvh_facts[0].extraction_status, "SCHEMA_SUPPORTED_BUT_NOT_REAL_DATA_VALIDATED")

        evf_facts = extract_sector_facts_from_sidecar(
            ticker="EVF",
            qualification={"sha256": "0" * 64, "document_id": "dummy"},
            sidecar={"pages": []},
            reporting_period="2024",
        )
        self.assertEqual(evf_facts[0].extraction_status, "SCHEMA_SUPPORTED_BUT_NOT_REAL_DATA_VALIDATED")

    def test_unknown_entity_extraction_fails_closed(self):
        """Verify unpromoted / unknown issuer fails closed."""
        zzz_facts = extract_sector_facts_from_sidecar(
            ticker="ZZZ",
            qualification={"sha256": "0" * 64, "document_id": "dummy"},
            sidecar={"pages": []},
            reporting_period="2024",
        )
        self.assertEqual(zzz_facts[0].extraction_status, "ENTITY_CLASS_UNRESOLVED")

    def test_zero_ticker_specific_branches_in_production(self):
        """Verify zero ticker-specific logic or symbol branching in production modules."""
        root = Path(__file__).resolve().parents[1]
        prod_files = [
            root / "sector_financial_taxonomy.py",
            root / "financial_disclosure_recognizer.py",
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


if __name__ == "__main__":
    unittest.main()
