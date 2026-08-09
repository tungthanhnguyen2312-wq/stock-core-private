import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from annual_financial_ocr_materialization import (  # noqa: E402
    CONTRACT, materialization_id, parse_accounting_integer, verified_extraction, verified_sum_extraction,
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
        self.assertEqual(parse_accounting_integer("(1,234,567)"), (-1234567, "negative"))
        for value in ("1,23,456", "1O0", "1.0", "(123"):
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


if __name__ == "__main__":
    unittest.main()
