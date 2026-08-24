"""A keyword match alone is never authoritative; only a section anchor plus a cue is."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import audit_opinion_evidence as opinion  # noqa: E402

UNMODIFIED_PAGE = (
    "Independent Auditor's Report\n"
    "To the shareholders of Example JSC\n"
    "In our opinion, the accompanying financial statements present fairly, in all material "
    "respects, the financial position of the Company.")

QUALIFIED_PAGE = (
    "Independent Auditor's Report\n"
    "Qualified Opinion\n"
    "Except for the effects of the matter described in the Basis for Qualified Opinion "
    "section, the financial statements present fairly...")

GOING_CONCERN_PAGE = (
    "Independent Auditor's Report\nOpinion\nIn our opinion the statements present fairly...\n"
    "Material Uncertainty Related to Going Concern\n"
    "We draw attention to Note 2 which indicates a material uncertainty related to going concern.")

BARE_MENTION_NO_ANCHOR = (
    "Director's Report\nIn the opinion of the directors, the Company performed well this year.")

NO_OPINION_LANGUAGE_AT_ALL = "Notes to the financial statements. Note 1. Basis of preparation."


class ClassifyPage(unittest.TestCase):
    def test_unmodified(self):
        result = opinion.classify_page(UNMODIFIED_PAGE)
        self.assertEqual(result["opinion_type"], opinion.UNMODIFIED)
        self.assertIsNotNone(result["section_anchor"])
        self.assertIsNotNone(result["citation_excerpt"])

    def test_qualified(self):
        result = opinion.classify_page(QUALIFIED_PAGE)
        self.assertEqual(result["opinion_type"], opinion.QUALIFIED)

    def test_going_concern_wins_over_bare_unmodified_language_before_it(self):
        result = opinion.classify_page(GOING_CONCERN_PAGE)
        self.assertEqual(result["opinion_type"], opinion.GOING_CONCERN_MATERIAL_UNCERTAINTY)

    def test_bare_mention_without_auditors_heading_is_unknown(self):
        """'opinion' appears in a director's report too; that alone must never classify."""
        result = opinion.classify_page(BARE_MENTION_NO_ANCHOR)
        self.assertEqual(result["opinion_type"], opinion.UNKNOWN)
        self.assertEqual(result["reason"], "no_auditors_report_section_heading_found")

    def test_no_opinion_language_anywhere(self):
        result = opinion.classify_page(NO_OPINION_LANGUAGE_AT_ALL)
        self.assertEqual(result["opinion_type"], opinion.UNKNOWN)


class EvaluateDocument(unittest.TestCase):
    def test_needs_ocr_never_classified(self):
        result = opinion.evaluate_document(
            document_id="D1", content_sha256="S1", ticker="HPG", reporting_period="2024",
            document_type="audited_annual_financial_statements", parser_status="needs_ocr",
            page_texts=["anything, even the word opinion, is irrelevant here"])
        self.assertEqual(result["opinion_type"], opinion.UNKNOWN)
        self.assertEqual(result["qualification"], "EXTRACTION_BLOCKED")

    def test_ready_document_with_no_extractable_text(self):
        result = opinion.evaluate_document(
            document_id="D2", content_sha256="S2", ticker="GAS", reporting_period="2025",
            document_type="audited_annual_financial_statements",
            parser_status="ready_for_direct_citations", page_texts=["", "", ""])
        self.assertEqual(result["opinion_type"], opinion.UNKNOWN)
        self.assertEqual(result["reason"], "no_extractable_text_on_any_page")

    def test_ready_document_with_text_but_no_heading(self):
        result = opinion.evaluate_document(
            document_id="D3", content_sha256="S3", ticker="QNS", reporting_period="2024",
            document_type="audited_annual_financial_statements",
            parser_status="ready_for_direct_citations", page_texts=[NO_OPINION_LANGUAGE_AT_ALL])
        self.assertEqual(result["qualification"], "NOT_IDENTIFIED")
        self.assertEqual(result["reason"], "no_auditors_report_section_heading_found_on_any_extracted_page")

    def test_finds_opinion_on_a_later_page_and_cites_it(self):
        result = opinion.evaluate_document(
            document_id="D4", content_sha256="S4", ticker="HPG", reporting_period="2024",
            document_type="audited_annual_financial_statements",
            parser_status="ready_for_direct_citations",
            page_texts=["cover page", NO_OPINION_LANGUAGE_AT_ALL, UNMODIFIED_PAGE, "notes..."])
        self.assertEqual(result["opinion_type"], opinion.UNMODIFIED)
        self.assertEqual(result["page"], 2)
        self.assertEqual(result["qualification"], "EXTRACTED")


if __name__ == "__main__":
    unittest.main()
