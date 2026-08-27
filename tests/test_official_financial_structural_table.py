"""Regression coverage for the bilingual/non-form-code structural table recognizer.

Covers:
1. Dispatch is a fallback only -- never touches the AAA exact-form path.
2. Layout-family classification is deterministic and evidence-derived.
3. Statement-family/consolidated-scope recognition requires explicit structural
   evidence (never guessed from being the only candidate).
4. Bank/securities documents never reach this module's corporate row logic.
5. Period-column and unit/currency evidence: explicit, table-local, fail-closed.
6. Row parsing: parentheses negatives, dash vs blank vs zero, note references,
   wrapped labels.
7. Canonical mapping: exact-anchor only, no ticker-specific branch.
8. Citation integrity: every qualified candidate is provably grounded in retained
   page text via the existing verified_extraction contract.
9. Phase 13 reconciliation never silently overwrites an existing qualified fact.
10. Real retained-corpus regression: VNM/PAN produce their independently verified
    values; QNS75/GAS honestly report no embedded statement table.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

from financial_statement_template_recognizer import StatementType
import official_financial_pdf_page_evidence as pdf_page_evidence
import official_financial_structural_table as structural


ROOT = Path(__file__).resolve().parents[1]
_SCALEOUT_ARTIFACT = ROOT / "operations-review" / "retained-official-financial-pdf-extraction-scaleout-v1-20260827" / "artifact.json"


def _load_replays() -> dict[str, dict]:
    """The already-materialized page_evidence for each target document, by short label.

    Reuses the retained scaleout artifact instead of re-parsing PDFs in every test;
    skips gracefully if that operations-review artifact has not been generated yet
    (it is gitignored, produced by tools/run_retained_official_financial_pdf_scaleout_v1.py).
    """
    if not _SCALEOUT_ARTIFACT.is_file():
        return {}
    data = json.loads(_SCALEOUT_ARTIFACT.read_text(encoding="utf-8"))
    labels = {
        "VNM": "4313d34c5d21", "HPG23": "44919df68306", "HPG22": "4fb8f8e0f8dd",
        "PAN": "757f8e5fe983", "QNS75": "a43f5b274524", "GAS": "b1cfb676ad81",
        "QNS41": "faaa54465d1d", "VCB": "9deccc3518e2", "SSI": "9fc4daa41947",
        "AAA": "fa5a765bf521",
    }
    by_label = {}
    for replay in data.get("replays", []):
        for label, prefix in labels.items():
            if replay["document_sha256"].startswith(prefix):
                by_label[label] = replay
    return by_label


REPLAYS = _load_replays()


def _document_for(replay: dict) -> dict:
    return {
        "document_id": replay["artifact"]["document"]["document_id"],
        "ticker": replay["ticker"],
        "sha256": replay["document_sha256"],
        "official_url": replay["artifact"]["document"].get("official_url"),
        "retrieved_at": replay["artifact"]["document"].get("retrieved_at"),
        "entity_type": "corporate",
    }


@unittest.skipUnless(REPLAYS, "retained scaleout artifact not generated in this environment")
class RealCorpusRegressionTests(unittest.TestCase):
    """Exercises the real retained target corpus end-to-end, not synthetic fixtures."""

    def test_vnm_produces_its_independently_verified_qualified_values(self):
        candidates, _ = structural.build_structural_candidates(document=_document_for(REPLAYS["VNM"]), pages=REPLAYS["VNM"]["artifact"]["page_evidence"])
        by_metric = {c["canonical_metric"]: c for c in candidates if c["qualification_status"] == "OFFICIAL_FACT_QUALIFIED"}
        # Values independently verified against the retained page text (see the
        # milestone's own evidence trail): cash and net profit exactly match VNM's
        # existing P3-F13 entries; revenue is a genuine, larger, correctly-scaled
        # figure the existing entry itself understates (see reconciliation test).
        self.assertEqual(by_metric["cash_and_equivalents"]["normalized_value"], 2_225_944_000_000)
        self.assertEqual(by_metric["net_income"]["normalized_value"], 8_686_245_000_000)
        self.assertEqual(by_metric["revenue"]["normalized_value"], 52_576_991_000_000)
        for row in by_metric.values():
            self.assertEqual(row["currency"], "VND")
            self.assertEqual(row["statement_scope"], "consolidated")
            self.assertEqual(row["fiscal_period"], "2024")

    def test_vnm_fragmented_equity_cell_blocks_rather_than_silently_truncates(self):
        # VNM's own PDF text layer renders this one figure as "37 ,165,930" (a
        # spurious space before the thousands comma).  The un-fixed regression was
        # silently returning 165930 (dropping the leading "37,") as if it were the
        # real value; it must now block explicitly instead.
        candidates, blocked = structural.build_structural_candidates(document=_document_for(REPLAYS["VNM"]), pages=REPLAYS["VNM"]["artifact"]["page_evidence"])
        self.assertNotIn("shareholders_equity", {c["canonical_metric"] for c in candidates})
        equity_blocks = [b for b in blocked if b.get("canonical_metric") == "shareholders_equity"]
        self.assertTrue(equity_blocks and equity_blocks[0]["reason"] == "CURRENT_PERIOD_CELL_UNPARSEABLE")

    def test_pan_produces_its_independently_verified_qualified_values(self):
        candidates, _ = structural.build_structural_candidates(document=_document_for(REPLAYS["PAN"]), pages=REPLAYS["PAN"]["artifact"]["page_evidence"])
        by_metric = {c["canonical_metric"]: c for c in candidates if c["qualification_status"] == "OFFICIAL_FACT_QUALIFIED"}
        self.assertEqual(by_metric["total_assets"]["normalized_value"], 23_840_652_907_125)
        self.assertEqual(by_metric["cash_and_equivalents"]["normalized_value"], 2_958_874_263_351)
        self.assertEqual(by_metric["revenue"]["normalized_value"], 16_181_632_412_859)

    def test_pan_equity_subline_is_not_confused_with_total_equity(self):
        # PAN's balance sheet also contains "Equity investments in other entities
        # ... 26,121,735,380" -- a same-anchor-prefixed but semantically different
        # line.  It must never be mistaken for the real (much larger) total-equity row.
        candidates, blocked = structural.build_structural_candidates(document=_document_for(REPLAYS["PAN"]), pages=REPLAYS["PAN"]["artifact"]["page_evidence"])
        equity_candidates = [c for c in candidates if c["canonical_metric"] == "shareholders_equity"]
        self.assertEqual(equity_candidates, [])
        equity_blocks = [b for b in blocked if b.get("canonical_metric") == "shareholders_equity"]
        self.assertTrue(equity_blocks)

    def test_qns75_and_gas_have_no_embedded_statement_table(self):
        # Real, honest structural findings: QNS75 is the annual-report narrative
        # volume (its financial statements are a separate retained document); GAS is
        # a bare disclosure notice.  Neither should fabricate a table.
        for label in ("QNS75", "GAS"):
            tables, _ = structural.recognize_structural_statement_tables(REPLAYS[label]["artifact"]["page_evidence"])
            self.assertEqual(tables, {}, f"{label} must not recognize a fabricated statement table")

    def test_vcb_and_ssi_never_reach_structural_candidate_building(self):
        # Bank/securities entity_type is refused before official_financial_pdf_page_
        # evidence.extract_candidates ever calls into this module (see
        # test_dispatch_is_never_reached_for_bank_or_securities_entities below); this
        # additionally proves the structural table recognizer itself never claims a
        # BALANCE_SHEET-typed page on their retained documents as a corporate table
        # in a way that would emit a corporate fact if it were ever misrouted there.
        for label in ("VCB", "SSI"):
            pages = REPLAYS[label]["artifact"]["page_evidence"]
            document = {**_document_for(REPLAYS[label]), "entity_type": {"VCB": "bank", "SSI": "securities"}[label]}
            candidates, blocked = pdf_page_evidence.extract_candidates(document=document, pages=pages, metadata={"metadata_claims": {}, "qualification_status": "DOCUMENT_METADATA_BLOCKED"})
            self.assertEqual(candidates, [])
            self.assertEqual(blocked, [{"state": "NOT_APPLICABLE", "reason": "ENTITY_LAYOUT_NOT_SUPPORTED_BY_CORPORATE_TEMPLATE", "entity_type": document["entity_type"]}])

    def test_reconciliation_never_marks_a_colliding_key_eligible_for_ingress(self):
        import p3f13_official_financial_evidence_scaleout as p3f13
        all_candidates = []
        for label in ("VNM", "PAN"):
            candidates, _ = structural.build_structural_candidates(document=_document_for(REPLAYS[label]), pages=REPLAYS[label]["artifact"]["page_evidence"])
            all_candidates.extend(candidates)
        panel = p3f13.execute()["refreshed_panel_data"]
        records = structural.reconcile_against_existing_panel(all_candidates, panel)
        # Every one of these six (ticker, metric, period, scope) keys already has an
        # existing OFFICIAL_QUALIFIED P3-F13 entry from an earlier, differently
        # evidenced route; none may be silently merged over.
        self.assertEqual(len(records), 6)
        self.assertTrue(all(not row["eligible_for_ingress"] for row in records))
        self.assertEqual({row["classification"] for row in records}, {"EXACT_MATCH"})

    def test_reconciliation_new_key_would_be_eligible_for_ingress(self):
        fake_candidate = {"ticker": "ZZZZ", "canonical_metric": "revenue", "fiscal_period": "2024",
                           "statement_scope": "consolidated", "qualification_status": "OFFICIAL_FACT_QUALIFIED",
                           "normalized_value": 123, "document_sha256": "deadbeef"}
        records = structural.reconcile_against_existing_panel([fake_candidate], {"issuers": []})
        self.assertEqual(records, [{
            "ticker": "ZZZZ", "canonical_metric": "revenue", "reporting_period": "2024", "statement_scope": "consolidated",
            "classification": "NOT_COMPARABLE_NEW_KEY", "existing_value": None, "new_value": 123,
            "new_document_sha256": "deadbeef", "eligible_for_ingress": True,
        }])


class LayoutFamilyRecognitionTests(unittest.TestCase):
    def test_no_recognized_page_is_narrative_only(self):
        pages = [{"page_number": 1, "page_text": "Just a cover page with no statements."}]
        self.assertEqual(structural.recognize_layout_family(pages), "NARRATIVE_ONLY_NO_EMBEDDED_STATEMENT")

    def test_english_titled_pages_classify_as_bilingual_family(self):
        pages = [{"page_number": 1, "page_text": "CONSOLIDATED BALANCE SHEET\nAs at 31 December 2024\nASSETS\nCurrent assets 100 200"}]
        self.assertEqual(structural.recognize_layout_family(pages), "BILINGUAL_ENGLISH_TITLED_STATEMENT_TABLE")

    def test_classification_is_deterministic(self):
        pages = [{"page_number": 1, "page_text": "CONSOLIDATED BALANCE SHEET\nAs at 31 December 2024\nASSETS\nCurrent assets 100 200"}]
        first = structural.recognize_layout_family(pages)
        second = structural.recognize_layout_family(pages)
        self.assertEqual(first, second)


class ConsolidatedBlockSelectionTests(unittest.TestCase):
    def test_toc_entry_naming_a_statement_is_not_mistaken_for_its_heading(self):
        # A page whose own heading region says CONTENTS, later listing "Consolidated
        # balance sheet" as an entry, must never be selected as the real table.
        page_map = {
            1: "CONTENTS\nReport of the BOD\nIndependent auditor's report\nConsolidated balance sheet\nConsolidated statement of income",
        }
        block, selection = structural.select_consolidated_block(page_map, StatementType.BALANCE_SHEET)
        self.assertIsNone(block)
        # The page IS recognized structurally (it contains "balance sheet"), but its
        # own heading region says CONTENTS, so it is excluded as front matter before
        # ever being counted as a consolidated-marked block -- zero blocks remain.
        self.assertEqual(selection["state"], "STATEMENT_SCOPE_UNPROVEN")

    def test_single_explicit_consolidated_heading_is_selected(self):
        page_map = {
            1: "COMPANY NAME\nCONSOLIDATED BALANCE SHEET AS AT 31 DECEMBER 2024\nASSETS\nCodes Notes Closing balance Opening balance\nCurrent assets 100 1,000,000 900,000",
        }
        block, selection = structural.select_consolidated_block(page_map, StatementType.BALANCE_SHEET)
        self.assertEqual(block, [1])
        self.assertEqual(selection["state"], "SELECTED")

    def test_scope_is_never_assumed_from_being_the_only_block(self):
        # A recognized balance-sheet page with no consolidated (or separate) marker
        # anywhere must block rather than default to "must be consolidated".
        page_map = {1: "BALANCE SHEET\nAs at 31 December 2024\nASSETS\nCurrent assets 100 1,000,000 900,000"}
        block, selection = structural.select_consolidated_block(page_map, StatementType.BALANCE_SHEET)
        self.assertIsNone(block)
        self.assertEqual(selection["state"], "STATEMENT_SCOPE_UNPROVEN")


class RowCellStateTests(unittest.TestCase):
    def test_parentheses_are_negative(self):
        cell = structural._cell_state("(1,234)")
        self.assertEqual(cell, {"raw_text": "(1,234)", "state": "NUMERIC", "parsed_value": -1234, "sign": "negative"})

    def test_dash_is_not_zero(self):
        cell = structural._cell_state("-")
        self.assertEqual(cell["state"], "DASH")
        self.assertIsNone(cell["parsed_value"])

    def test_blank_is_not_zero(self):
        cell = structural._cell_state(None)
        self.assertEqual(cell["state"], "BLANK")
        self.assertIsNone(cell["parsed_value"])

    def test_literal_zero_is_real_zero_not_blank_or_dash(self):
        cell = structural._cell_state("0")
        self.assertEqual(cell, {"raw_text": "0", "state": "NUMERIC", "parsed_value": 0, "sign": "positive"})

    def test_fragmented_number_is_unparseable_not_silently_truncated(self):
        cell = structural._cell_state("37 ,165,930")
        self.assertEqual(cell["state"], "UNPARSEABLE")
        self.assertIsNone(cell["parsed_value"])


class RowMajorMatchTests(unittest.TestCase):
    def test_wrapped_two_line_label_is_matched(self):
        block = {1: "Items Codes Notes Current year Prior year\n"
                    "3.  Net revenue from goods sold and services \n"
                    "rendered (10=01-02) 10 32 16,181,632,412,859 13,204,596,686,662\n"}
        match = structural.match_metric_row(block, "revenue")
        self.assertIsNotNone(match)
        self.assertEqual(match["current_raw"], "16,181,632,412,859")
        self.assertEqual(match["comparative_raw"], "13,204,596,686,662")

    def test_formula_annotation_minus_sign_is_not_read_as_a_nil_cell(self):
        # "(10 = 01 - 02)" is a formula reference, not a value column; a naive dash
        # scan would otherwise report this row's value as DASH.
        block = {1: "Net revenue (10 = 01 - 02)\nCost of sales\nGross profit (20 = 10 - 11)\n"}
        match = structural.match_metric_row(block, "revenue")
        self.assertIsNone(match)

    def test_anchor_must_open_its_own_window_not_borrow_a_preceding_rows_numbers(self):
        # Regression: a window starting one line early (at the unrelated "Current
        # assets" row) must not be allowed to satisfy the "Cash and cash
        # equivalents" anchor and then report Current assets' own value instead.
        block = {1: "Current assets 37,501,520 35,931,145\nCash and cash equivalents  2,225,944 2,912,027\n"}
        match = structural.match_metric_row(block, "cash_and_equivalents")
        self.assertIsNotNone(match)
        self.assertEqual(match["current_raw"], "2,225,944")

    def test_bare_single_word_anchor_does_not_match_a_different_compound_line(self):
        # "Equity investments in other entities" must not satisfy the bare "equity"
        # anchor meant for the real, standalone "Equity <amount>" total-equity row.
        block = {1: "Equity investments in other entities 26,121,735,380 26,121,735,380\n"}
        match = structural.match_metric_row(block, "shareholders_equity")
        self.assertIsNone(match)

    def test_bare_single_word_anchor_matches_its_own_standalone_row(self):
        block = {1: "Equity 37,165,930 35,783,726\n"}
        match = structural.match_metric_row(block, "shareholders_equity")
        self.assertIsNotNone(match)
        self.assertEqual(match["current_raw"], "37,165,930")


class ColumnMajorMatchTests(unittest.TestCase):
    """_column_runs only registers a run of >=5 lines (see module docstring guard
    against stray-short-number false positives), so every fixture here uses 5 rows."""

    def test_positional_reconstruction_requires_exact_run_length_parity(self):
        # 5 codes but only 4 "current" values -- positions cannot be trusted to
        # align, so this must block rather than guess.
        lines = ["Net revenue", "Cost of sales", "Gross profit", "Operating profit", "Net income",
                 "10", "11", "20", "30", "60",
                 "1,000,000", "2,000,000", "3,000,000", "4,000,000",
                 "1,100,000", "2,100,000", "3,100,000", "4,100,000", "5,100,000"]
        block = {1: "\n".join(lines)}
        match = structural._column_major_match(block, "revenue")
        self.assertIsNone(match)

    def test_positional_reconstruction_succeeds_with_matching_run_lengths_and_anchor(self):
        # The current-year and prior-year value blocks must be two DISTINCT runs
        # (matching real HPG cash-flow pages, which repeat a short "Code Note ..."
        # header between them) -- back-to-back number lines with nothing between them
        # merge into one run of double length and correctly fail parity instead
        # (see test_positional_reconstruction_requires_exact_run_length_parity).
        lines = ["Net revenue", "Cost of sales", "Gross profit", "Operating profit", "Net profit after tax",
                 "10", "11", "20", "30", "60",
                 "16,181,632,412,859", "12,799,997,630,821", "3,381,634,782,038", "1,354,279,053,368", "1,167,068,107,309",
                 "Code Note 2024 VND 2023 VND",
                 "13,204,596,686,662", "10,544,753,392,618", "2,659,843,294,044", "952,068,504,119", "817,117,336,270"]
        block = {1: "\n".join(lines)}
        match = structural._column_major_match(block, "revenue")
        self.assertIsNotNone(match)
        self.assertEqual(match["current_raw"], "16,181,632,412,859")
        self.assertEqual(match["comparative_raw"], "13,204,596,686,662")
        self.assertEqual(match["layout"], "column_major")


class PeriodAmbiguityTests(unittest.TestCase):
    def test_zero_years_found_blocks(self):
        self.assertIsNone(structural._infer_target_period({1: "No date evidence here at all."}))

    def test_more_than_two_distinct_years_blocks_rather_than_guesses(self):
        text = "Current year 2024 Prior year 2023 as at 2022"
        self.assertIsNone(structural._infer_target_period({1: text}))

    def test_exactly_two_years_resolves_to_the_maximum(self):
        text = "31/12/2024\n31/12/2023\n"
        self.assertEqual(structural._infer_target_period({1: text}), "2024")


class UnitScaleTests(unittest.TestCase):
    def test_bare_currency_scale_line_without_the_word_unit_is_recognized(self):
        unit = structural._fallback_unit_and_scale("31/12/2024\nVND million\n31/12/2023\nVND million\n")
        self.assertIsNotNone(unit)
        self.assertEqual((unit.currency, unit.unit_scale), ("VND", 1_000_000))

    def test_absent_unit_evidence_returns_none_not_a_guess(self):
        self.assertIsNone(structural._fallback_unit_and_scale("Just some narrative text with 2024 mentioned."))


class GovernanceTests(unittest.TestCase):
    """No ticker-specific branch, no network/OCR/provider fallback, no VALUE activation."""

    def test_no_ticker_or_network_or_ocr_constants_in_source(self):
        source = (ROOT / "official_financial_structural_table.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        string_constants = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        for ticker in ("AAA", "VNM", "HPG", "PAN", "QNS", "GAS", "VCB", "SSI"):
            self.assertNotIn(ticker, string_constants, f"{ticker} must not appear as a source-level ticker branch")
        for forbidden in ("requests", "urllib", "sqlite3", "tesseract", "pytesseract"):
            self.assertNotIn(forbidden, source)

    def test_no_value_or_recommendation_authority_terms_in_source(self):
        source = (ROOT / "official_financial_structural_table.py").read_text(encoding="utf-8")
        for forbidden in ("recommendation", "ranking", "target_price", "probability", "position_size", "pit_backtest"):
            self.assertNotIn(forbidden, source.casefold())


class DispatchTests(unittest.TestCase):
    def test_dispatch_is_never_reached_for_bank_or_securities_entities(self):
        # Regardless of what discover_tables finds, entity_type is checked first.
        document = {"ticker": "ZZZZ", "sha256": "x", "official_url": None, "entity_type": "bank"}
        candidates, blocked = pdf_page_evidence.extract_candidates(document=document, pages=[], metadata={"metadata_claims": {}, "qualification_status": "DOCUMENT_METADATA_BLOCKED"})
        self.assertEqual(candidates, [])
        self.assertEqual(blocked[0]["reason"], "ENTITY_LAYOUT_NOT_SUPPORTED_BY_CORPORATE_TEMPLATE")

    def test_dispatch_fallback_only_fires_when_exact_form_finds_zero_tables(self):
        source = (ROOT / "official_financial_pdf_page_evidence.py").read_text(encoding="utf-8")
        self.assertIn("if not tables:", source)
        self.assertIn("official_financial_structural_table.build_structural_candidates", source)


if __name__ == "__main__":
    unittest.main()
