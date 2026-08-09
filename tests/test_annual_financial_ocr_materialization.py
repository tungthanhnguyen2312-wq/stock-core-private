import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from annual_financial_ocr_materialization import (  # noqa: E402
    CONTRACT, materialization_id, parse_accounting_integer, verified_extraction, verified_sum_extraction,
    verified_debt_extraction, verified_maturity_zero_extraction,
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


class MaturityZeroDebtExtractionTests(unittest.TestCase):
    """Focused coverage for the explicit-zero maturity-note debt contract (QNS 2026-08-10)."""

    LIQUIDITY_NOTE_TEXT = (
        "Tong hop cac khoan no phai tra tai chinh cua Cong ty theo thoi han thanh toan nhu sau:\n"
        "Phai tra nguoi ban\n"
        "464.095.068.931\n"
        "-\n"
        "464.095.068.931\n"
        "Vay va no thue tai chinh\n"
        "2.713.580.820.203\n"
        "-\n"
        "2.713.580.820.203\n"
        "Phai tra khac\n"
        "49.713.233.167\n"
        "8.301.854.364\n"
        "58.015.087.531\n"
    )

    def _page(self, page, text, *, status="text_available", suffix=""):
        digest = hashlib.sha256((text + suffix).encode()).hexdigest()
        page_id = materialization_id(document_sha256="source", page=page, engine="pypdf 6", text_sha256=digest)
        return {"page": page, "document_id": "doc", "document_sha256": "source", "status": status, "text": text,
                "text_sha256": digest, "citation_id": f"page-citation-{page}-{suffix}", "materialization_id": page_id,
                "extraction_engine": "pypdf 6", "contract": CONTRACT}

    def materialization(self, *, short_term_text="Vay va no thue tai chinh ngan han 2.713.580.820.203",
                        note_text=None):
        return {"document_sha256": "source",
                "pages": [self._page(8, short_term_text, suffix="short"),
                         self._page(39, note_text if note_text is not None else self.LIQUIDITY_NOTE_TEXT, suffix="note")]}

    def debt_components(self, *, long_term_bucket_raw_value="-", short_term_bucket_raw_value="2.713.580.820.203",
                        total_raw_value="2.713.580.820.203", row_label="Vay va no thue tai chinh",
                        reporting_period="2024"):
        short = {"component_type": "short_term_borrowings", "reporting_period": reporting_period, "page": 8,
                 "label": "Vay và nợ thuê tài chính ngắn hạn", "raw_value": "2.713.580.820.203",
                 "ocr_label": "Vay va no thue tai chinh ngan han", "ocr_raw_value": "2.713.580.820.203",
                 "visual_source_page_verified": True}
        long = {"component_type": "long_term_borrowings_or_finance_leases", "reporting_period": reporting_period,
                "page": 39, "qualification_method": "maturity_note_explicit_zero", "unit": "VND",
                "label": row_label, "short_term_bucket_raw_value": short_term_bucket_raw_value,
                "long_term_bucket_raw_value": long_term_bucket_raw_value, "total_raw_value": total_raw_value,
                "visual_source_page_verified": True}
        return short, long

    def test_explicit_audited_long_term_zero_accepted_when_population_matches(self):
        materialization = self.materialization()
        short, long = self.debt_components()
        debt = verified_debt_extraction(materialization, components=[short, long], unit="VND",
                                        statement="balance_sheet", reporting_period="2024")
        self.assertEqual(debt["normalized_value"], 2_713_580_820_203)
        components = debt["materialization"]["components"]
        self.assertEqual(components[0]["qualification_method"], "direct_statement_line")
        self.assertEqual(components[1]["qualification_method"], "maturity_note_explicit_zero")
        self.assertEqual(components[1]["maturity_long_term_bucket_raw_value"], "-")

    def test_missing_long_term_line_alone_is_not_zero(self):
        materialization = self.materialization()
        short, _ = self.debt_components()
        with self.assertRaisesRegex(ValueError, "REQUIRED_DEBT_COMPONENT_MISSING"):
            verified_debt_extraction(materialization, components=[short], unit="VND", statement="balance_sheet",
                                     reporting_period="2024")
        blank_long = {**self.debt_components()[1], "long_term_bucket_raw_value": ""}
        with self.assertRaisesRegex(ValueError, "MATURITY_ZERO_MARKER_UNRECOGNIZED"):
            verified_debt_extraction(materialization, components=[short, blank_long], unit="VND",
                                     statement="balance_sheet", reporting_period="2024")

    def test_generic_liabilities_maturity_row_rejected(self):
        materialization = self.materialization()
        short, _ = self.debt_components()
        other_payables = {**self.debt_components()[1], "label": "Phai tra khac",
                          "short_term_bucket_raw_value": "49.713.233.167",
                          "long_term_bucket_raw_value": "8.301.854.364", "total_raw_value": "58.015.087.531"}
        with self.assertRaisesRegex(ValueError, "MATURITY_ZERO_MARKER_UNRECOGNIZED|MATURITY_POPULATION_LABEL_UNQUALIFIED"):
            verified_debt_extraction(materialization, components=[short, other_payables], unit="VND",
                                     statement="balance_sheet", reporting_period="2024")
        # Isolate the population-label gate directly: an explicit nil for a non-borrowing row still refuses.
        with self.assertRaisesRegex(ValueError, "MATURITY_POPULATION_LABEL_UNQUALIFIED"):
            verified_maturity_zero_extraction(materialization, page=39, row_label="Phai tra nguoi ban",
                                              short_term_bucket_raw_value="464.095.068.931",
                                              long_term_bucket_raw_value="-", total_raw_value="464.095.068.931",
                                              unit="VND", statement="balance_sheet",
                                              visual_source_page_verified=True)

    def test_scope_and_period_mismatch_rejected(self):
        materialization = self.materialization()
        short, long = self.debt_components()
        with self.assertRaisesRegex(ValueError, "DEBT_COMPONENT_PERIOD_MISMATCH"):
            verified_debt_extraction(materialization, components=[short, {**long, "reporting_period": "2023"}],
                                     unit="VND", statement="balance_sheet", reporting_period="2024")

    def test_currency_mismatch_rejected(self):
        materialization = self.materialization()
        short, long = self.debt_components()
        with self.assertRaisesRegex(ValueError, "DEBT_COMPONENT_CURRENCY_MISMATCH"):
            verified_debt_extraction(materialization, components=[short, {**long, "unit": "USD"}], unit="VND",
                                     statement="balance_sheet", reporting_period="2024")

    def test_explicit_non_zero_maturity_value_is_refused_not_mishandled(self):
        materialization = self.materialization()
        short, long = self.debt_components()
        non_zero_long = {**long, "long_term_bucket_raw_value": "1.000.000"}
        with self.assertRaisesRegex(ValueError, "MATURITY_ZERO_MARKER_UNRECOGNIZED"):
            verified_debt_extraction(materialization, components=[short, non_zero_long], unit="VND",
                                     statement="balance_sheet", reporting_period="2024")

    def test_citation_and_provenance_serialization_is_deterministic(self):
        materialization = self.materialization()
        _, long = self.debt_components()
        first = verified_maturity_zero_extraction(materialization, page=39, row_label=long["label"],
                                                   short_term_bucket_raw_value=long["short_term_bucket_raw_value"],
                                                   long_term_bucket_raw_value=long["long_term_bucket_raw_value"],
                                                   total_raw_value=long["total_raw_value"], unit="VND",
                                                   statement="balance_sheet", visual_source_page_verified=True)
        second = verified_maturity_zero_extraction(materialization, page=39, row_label=long["label"],
                                                    short_term_bucket_raw_value=long["short_term_bucket_raw_value"],
                                                    long_term_bucket_raw_value=long["long_term_bucket_raw_value"],
                                                    total_raw_value=long["total_raw_value"], unit="VND",
                                                    statement="balance_sheet", visual_source_page_verified=True)
        self.assertEqual(first, second)
        self.assertEqual(first["materialization"]["materialization_id"], second["materialization"]["materialization_id"])

    def test_existing_direct_statement_debt_extraction_unchanged(self):
        materialization = self.materialization(short_term_text="Short-term borrowings 100 Long-term borrowings 200")
        components = [
            {"component_type": "short_term_borrowings", "reporting_period": "2024", "page": 8,
             "label": "Short-term borrowings", "raw_value": "100", "visual_source_page_verified": True},
            {"component_type": "long_term_borrowings_or_finance_leases", "reporting_period": "2024", "page": 8,
             "label": "Long-term borrowings", "raw_value": "200", "visual_source_page_verified": True},
        ]
        debt = verified_debt_extraction(materialization, components=components, unit="VND",
                                        statement="balance_sheet", reporting_period="2024")
        self.assertEqual(debt["normalized_value"], 300)
        for component in debt["materialization"]["components"]:
            self.assertEqual(component["qualification_method"], "direct_statement_line")

    def test_arithmetic_mismatch_and_ambiguous_structure_fail_closed(self):
        materialization = self.materialization()
        short, long = self.debt_components()
        with self.assertRaisesRegex(ValueError, "MATURITY_ZERO_ARITHMETIC_MISMATCH"):
            verified_debt_extraction(materialization, components=[short, {**long, "total_raw_value": "1.234"}],
                                     unit="VND", statement="balance_sheet", reporting_period="2024")
        with self.assertRaisesRegex(ValueError, "MATURITY_TABLE_STRUCTURE_NOT_VERIFIED"):
            verified_debt_extraction(
                materialization,
                components=[short, {**long, "short_term_bucket_raw_value": "999.999.999",
                                    "total_raw_value": "999.999.999"}],
                unit="VND", statement="balance_sheet", reporting_period="2024")

    def test_maturity_population_mismatch_against_sibling_short_component_fails_closed(self):
        materialization = self.materialization(short_term_text="Vay va no thue tai chinh ngan han 999.999.999")
        short = {"component_type": "short_term_borrowings", "reporting_period": "2024", "page": 8,
                 "label": "Vay và nợ thuê tài chính ngắn hạn", "raw_value": "999.999.999",
                 "ocr_label": "Vay va no thue tai chinh ngan han", "ocr_raw_value": "999.999.999",
                 "visual_source_page_verified": True}
        _, long = self.debt_components()
        with self.assertRaisesRegex(ValueError, "MATURITY_POPULATION_MISMATCH"):
            verified_debt_extraction(materialization, components=[short, long], unit="VND",
                                     statement="balance_sheet", reporting_period="2024")


if __name__ == "__main__":
    unittest.main()
