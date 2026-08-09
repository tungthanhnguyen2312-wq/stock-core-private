import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from annual_financial_ocr_materialization import (  # noqa: E402
    CONTRACT, materialization_id, parse_accounting_integer, verified_extraction, verified_sum_extraction,
    verified_debt_extraction,
)


class AnnualFinancialOcrMaterializationTests(unittest.TestCase):
    def materialization(self, text="Cash and cash equivalents 1,234,567"):
        digest = hashlib.sha256(text.encode()).hexdigest()
        page_id = materialization_id(document_sha256="source", page=7, engine="tesseract v5", text_sha256=digest)
        return {"document_sha256": "source", "pages": [{"page": 7, "document_id": "doc",
                "document_sha256": "source", "status": "ocr_available", "text": text, "text_sha256": digest,
                "citation_id": "page-citation", "materialization_id": page_id, "ocr_engine": "tesseract v5",
                "render_dpi": 216, "contract": CONTRACT}]}

    def test_accounting_numbers_preserve_commas_and_parentheses(self):
        self.assertEqual(parse_accounting_integer("1,234,567"), (1234567, "positive"))
        self.assertEqual(parse_accounting_integer("1.234.567"), (1234567, "positive"))
        self.assertEqual(parse_accounting_integer("(1,234,567)"), (-1234567, "negative"))
        for value in ("1,23,456", "1.234,567", "1O0", "1.0", "(123"):
            with self.assertRaisesRegex(ValueError, "OCR_NUMERIC_AMBIGUITY"):
                parse_accounting_integer(value)

    def test_page_identity_and_source_verification_are_required(self):
        materialization = self.materialization()
        extraction = verified_extraction(materialization, page=7, raw_label="Cash and cash equivalents",
                                         raw_value="1,234,567", unit="VND", statement="balance_sheet",
                                         visual_source_page_verified=True)
        self.assertEqual(extraction["materialization"]["page"], 7)
        self.assertEqual(extraction["normalized_value"], 1234567)
        with self.assertRaisesRegex(ValueError, "CITATION_VERIFICATION_FAILED"):
            verified_extraction(materialization, page=7, raw_label="Cash and cash equivalents", raw_value="1,234,567",
                                unit="VND", statement="balance_sheet", visual_source_page_verified=False)

    def test_wrong_ocr_value_or_missing_debt_component_fails_closed(self):
        materialization = self.materialization()
        with self.assertRaisesRegex(ValueError, "OCR_NUMERIC_AMBIGUITY"):
            verified_extraction(materialization, page=7, raw_label="Cash and cash equivalents", raw_value="1,234,568",
                                unit="VND", statement="balance_sheet", visual_source_page_verified=True)
        with self.assertRaisesRegex(ValueError, "REQUIRED_DEBT_COMPONENT_MISSING"):
            verified_sum_extraction(materialization, components=[{"page": 7, "label": "Cash and cash equivalents",
                                     "raw_value": "1,234,567", "visual_source_page_verified": True}],
                                    unit="VND", statement="balance_sheet")

    def test_identity_is_deterministic_and_binds_engine_and_page(self):
        one = materialization_id(document_sha256="source", page=7, engine="tesseract v5", text_sha256="text")
        self.assertEqual(one, materialization_id(document_sha256="source", page=7, engine="tesseract v5", text_sha256="text"))
        self.assertNotEqual(one, materialization_id(document_sha256="source", page=8, engine="tesseract v5", text_sha256="text"))
        self.assertNotEqual(one, materialization_id(document_sha256="source", page=7, engine="tesseract v6", text_sha256="text"))

    def test_text_bearing_materialization_uses_the_same_verified_page_contract(self):
        text = "Cash and cash equivalents 1,234,567"
        digest = hashlib.sha256(text.encode()).hexdigest()
        materialization = {"document_sha256": "source", "pages": [{"page": 7, "document_id": "doc",
            "document_sha256": "source", "status": "text_available", "text": text, "text_sha256": digest,
            "citation_id": "page-citation", "materialization_id": materialization_id(
                document_sha256="source", page=7, engine="pypdf 6", text_sha256=digest),
            "extraction_engine": "pypdf 6", "contract": CONTRACT}]}
        extracted = verified_extraction(materialization, page=7, raw_label="Cash and cash equivalents",
                                        raw_value="1,234,567", unit="VND", statement="balance_sheet",
                                        visual_source_page_verified=True)
        self.assertEqual(extracted["materialization"]["extraction_method"], "pdf_text")
        self.assertEqual(extracted["normalized_value"], 1234567)

    def test_source_label_is_preserved_while_the_ocr_anchor_stays_exact(self):
        materialization = self.materialization("Tien va cac khoan tuong duong tien 1.234.567")
        extracted = verified_extraction(
            materialization, page=7, raw_label="Tien va cac khoan tuong duong tien",
            raw_value="1.234.567", source_raw_label="Tiền và các khoản tương đương tiền",
            source_raw_value="1.234.567", unit="VND", statement="balance_sheet",
            visual_source_page_verified=True,
        )
        self.assertEqual(extracted["raw_labels"], ["Tiền và các khoản tương đương tiền"])
        self.assertEqual(extracted["ocr_anchors"]["value"], "1.234.567")

    def test_debt_requires_both_labelled_same_period_components(self):
        materialization = self.materialization(
            "Short-term borrowings 100 Long-term borrowings 200 Other liabilities 300")
        components = [
            {"component_type": "short_term_borrowings", "reporting_period": "2024", "page": 7,
             "label": "Short-term borrowings", "raw_value": "100", "visual_source_page_verified": True},
            {"component_type": "long_term_borrowings_or_finance_leases", "reporting_period": "2024", "page": 7,
             "label": "Long-term borrowings", "raw_value": "200", "visual_source_page_verified": True},
        ]
        debt = verified_debt_extraction(materialization, components=components, unit="VND",
                                        statement="balance_sheet", reporting_period="2024")
        self.assertEqual(debt["normalized_value"], 300)
        self.assertEqual(debt["unit"], "VND")
        ambiguous = [*components]
        ambiguous[1] = {**ambiguous[1], "label": "Other liabilities"}
        with self.assertRaisesRegex(ValueError, "DEBT_COMPONENT_LABEL_UNQUALIFIED"):
            verified_debt_extraction(materialization, components=ambiguous, unit="VND",
                                     statement="balance_sheet", reporting_period="2024")
        with self.assertRaisesRegex(ValueError, "DEBT_COMPONENT_PERIOD_MISMATCH"):
            verified_debt_extraction(materialization, components=[components[0],
                {**components[1], "reporting_period": "2023"}], unit="VND",
                                     statement="balance_sheet", reporting_period="2024")
        with self.assertRaisesRegex(ValueError, "REQUIRED_DEBT_COMPONENT_MISSING"):
            verified_debt_extraction(materialization, components=components[:1], unit="VND",
                                     statement="balance_sheet", reporting_period="2024")

    def test_explicit_short_and_long_term_loans_are_debt_components(self):
        materialization = self.materialization("Short-term loans 100 Long-term loans 200")
        debt = verified_debt_extraction(materialization, components=[
            {"component_type": "short_term_borrowings", "reporting_period": "2024", "page": 7,
             "label": "Short-term loans", "raw_value": "100", "visual_source_page_verified": True},
            {"component_type": "long_term_borrowings_or_finance_leases", "reporting_period": "2024", "page": 7,
             "label": "Long-term loans", "raw_value": "200", "visual_source_page_verified": True},
        ], unit="VND", statement="balance_sheet", reporting_period="2024")
        self.assertEqual(debt["normalized_value"], 300)

    def test_vietnamese_borrowing_labels_preserve_the_two_component_debt_gate(self):
        materialization = self.materialization("Vay va no thue tai chinh ngan han 100 Vay va no thue tai chinh dai han 200")
        debt = verified_debt_extraction(materialization, components=[
            {"component_type": "short_term_borrowings", "reporting_period": "2024", "page": 7,
             "label": "Vay và nợ thuê tài chính ngắn hạn", "ocr_label": "Vay va no thue tai chinh ngan han",
             "raw_value": "100", "visual_source_page_verified": True},
            {"component_type": "long_term_borrowings_or_finance_leases", "reporting_period": "2024", "page": 7,
             "label": "Vay và nợ thuê tài chính dài hạn", "ocr_label": "Vay va no thue tai chinh dai han",
             "raw_value": "200", "visual_source_page_verified": True},
        ], unit="VND", statement="balance_sheet", reporting_period="2024")
        self.assertEqual(debt["normalized_value"], 300)


if __name__ == "__main__":
    unittest.main()
