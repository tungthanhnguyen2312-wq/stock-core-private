"""Focused retained-only coverage for image-table TSV OCR evidence."""
from __future__ import annotations

import json
import copy
import inspect
from pathlib import Path

from annual_financial_ocr_materialization import parse_accounting_integer
import official_financial_ocr_table_evidence as cell_module
from official_financial_ocr_table_evidence import (
    CELL_CODE_READ_CONFIG,
    assess_secondary_line_code_raw,
    materialize_tsv_pages,
    panel_facts_from_qualified_ocr,
    qualify_table_facts,
    resolve_ambiguous_debt_line_code_cells,
    resolve_scoped_statement_scope_evidence,
    resolve_scoped_unit_evidence,
    resolve_statement_scope_for_page,
)
from financial_statement_unit_resolution import resolve_unit_for_scope
from official_financial_structural_table import match_geometry_ambiguous_line_code_cell, match_geometry_table_row


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "operations-review" / "governed-official-evidence-v1"
DOCUMENT_SHA = "630f61f6ef9f07d5c593c3bf8f65bad1d56ecbb091921296ed5c4e830ea070a4"


def _record() -> dict:
    records = json.loads((EVIDENCE / "official_document_acquisition_manifest.json").read_text(encoding="utf-8"))["records"]
    return next(row for row in records if row["sha256"] == DOCUMENT_SHA)


def test_numeric_ocr_repair_is_never_permitted():
    assert parse_accounting_integer("9.376.127.629.501")[0] == 9_376_127_629_501
    for raw in ("3\u00b20", "19.169.697.497.95O", "37 ,165,930"):
        try:
            parse_accounting_integer(raw)
        except ValueError as error:
            assert str(error) == "OCR_NUMERIC_AMBIGUITY"
        else:  # pragma: no cover - a future repair would be an authority defect
            raise AssertionError(raw)


def test_shared_row_match_refuses_native_or_mixed_tokens():
    page = {"page_number": 1, "positioned_tokens": [{"text": "10", "x0": 1, "x1": 2, "top": 1, "bottom": 2,
             "raw_token_order": 0, "provenance": "NATIVE_PDF_POSITIONED_TOKEN"}]}
    assert match_geometry_table_row(page, line_code="10", target_period="2025") is None


def test_explicit_consolidated_scope_is_page_scoped_and_required_when_supplied():
    def token(text, order, top=10):
        return {"text": text, "token_id": str(order), "raw_token_order": order, "top": top, "bottom": top + 1,
                "x0": order * 5, "x1": order * 5 + 2, "tsv_hierarchy": {}}
    materialization = {"document_sha256": DOCUMENT_SHA, "pages": [
        {"page_number": 1, "positioned_token_provenance": "OCR_TSV_POSITIONED_TOKEN",
         "ocr_derived_text_evidence": {"tokens": [token(value, index) for index, value in enumerate(
             "CONSOLIDATED INCOME STATEMENT Code Current year Prior year".split())]}},
        {"page_number": 2, "positioned_token_provenance": "OCR_TSV_POSITIONED_TOKEN",
         "ocr_derived_text_evidence": {"tokens": [
             *[token(value, index, 10) for index, value in enumerate("INCOME STATEMENT Code Current year Prior year".split())],
             token("consolidated", 90, 300), token("note", 91, 300),
         ]}},
    ]}
    evidence = resolve_scoped_statement_scope_evidence(materialization)
    assert [item["page_number"] for item in evidence["declarations"]] == [1]
    resolved = resolve_statement_scope_for_page(evidence, document_sha256=DOCUMENT_SHA, page_number=1,
                                                statement_family="income_statement")
    assert resolved["state"] == "QUALIFIED" and resolved["statement_scope"] == "consolidated"
    missing = resolve_statement_scope_for_page(evidence, document_sha256=DOCUMENT_SHA, page_number=2,
                                               statement_family="income_statement")
    assert missing["state"] == "STATEMENT_SCOPE_BLOCKED"


def test_immediate_explicit_continuation_inherits_only_predecessor_scope_and_unit():
    def token(text, order, top=10):
        return {"text": text, "token_id": str(order), "raw_token_order": order, "top": top, "bottom": top + 1,
                "x0": order * 5, "x1": order * 5 + 2,
                "tsv_hierarchy": {"block_num": 1, "par_num": 1, "line_num": 1}}
    materialization = {"document_sha256": DOCUMENT_SHA, "pages": [
        {"page_number": 1, "positioned_token_provenance": "OCR_TSV_POSITIONED_TOKEN",
         "ocr_derived_text_evidence": {"tokens": [token(value, index) for index, value in enumerate(
             "CONSOLIDATED INCOME STATEMENT Code Unit: VND".split())]}},
        {"page_number": 2, "positioned_token_provenance": "OCR_TSV_POSITIONED_TOKEN",
         "ocr_derived_text_evidence": {"tokens": [token(value, index) for index, value in enumerate(
             "Continued Code Current year Prior year".split())]}},
    ]}
    scope = resolve_scoped_statement_scope_evidence(materialization)
    resolved_scope = resolve_statement_scope_for_page(scope, document_sha256=DOCUMENT_SHA, page_number=2,
                                                       statement_family="income_statement")
    assert resolved_scope["state"] == "QUALIFIED" and resolved_scope["evidence"]["continuation_of_page"] == 1
    units = resolve_scoped_unit_evidence(materialization)
    resolved_unit = resolve_unit_for_scope(units["declarations"], document_sha256=DOCUMENT_SHA, page_number=2,
                                           statement_family="income_statement", table_id="ocr-page:x:2:income_statement")
    assert (resolved_unit["state"], resolved_unit["currency"], resolved_unit["evidence"]["continuation_of_page"]) == ("QUALIFIED", "VND", 1)


def test_fpt_income_page_is_deterministic_and_qualifies_only_exact_numeric_cells():
    first = materialize_tsv_pages(_record(), evidence_root=EVIDENCE, pages=(12,))
    second = materialize_tsv_pages(_record(), evidence_root=EVIDENCE, pages=(12,))
    assert first["materialization_id"] == second["materialization_id"]
    assert first["pages"][0]["positioned_token_provenance"] == "OCR_TSV_POSITIONED_TOKEN"
    assert first["pages"][0]["ocr_derived_text_evidence"]["tokens"] == second["pages"][0]["ocr_derived_text_evidence"]["tokens"]
    result = qualify_table_facts(first, ticker="FPT", reporting_period="2025")
    assert {row["canonical_metric"]: row["value"] for row in result["qualified_facts"]} == {
        "revenue": 70_112_825_100_710, "net_income": 9_376_127_629_501,
    }
    for row in result["qualified_facts"]:
        assert row["source_lineage"]["row_object"]["column_bands"]["bands"]["label"]
        assert row["source_lineage"]["source_image_evidence"]["rendered_image_sha256"]


def test_fpt_debt_blocks_when_line_320_has_an_ambiguous_ocr_code():
    materialization = materialize_tsv_pages(_record(), evidence_root=EVIDENCE, pages=(10,))
    result = qualify_table_facts(materialization, ticker="FPT", reporting_period="2025")
    blocked = {row["canonical_metric"]: row for row in result["blocked_candidates"]}
    assert blocked["short_term_borrowings"]["reason"] == "ROW_NOT_UNIQUE_OR_NOT_GEOMETRICALLY_RESOLVED"
    assert blocked["total_interest_bearing_debt"]["reason"] == "DEBT_COMPONENT_INCOMPLETE"


def test_cell_code_raw_assessment_never_repairs_or_accepts_conflicting_evidence():
    assert assess_secondary_line_code_raw("320", "320\r\n") == ("320", "QUALIFIED_BY_SECONDARY_RAW_CODE")
    assert assess_secondary_line_code_raw("320", "3\u00b20") == ("3\u00b20", "SECONDARY_CODE_NOT_EXACT")
    assert assess_secondary_line_code_raw("320", "321\n") == ("321", "CONFLICTING_PRIMARY_SECONDARY_CODE")
    assert assess_secondary_line_code_raw("320", "\n") == ("", "SECONDARY_CODE_NOT_EXACT")
    assert CELL_CODE_READ_CONFIG["tesseract_variables"] == {"tessedit_char_whitelist": "0123456789"}
    # The public resolver has no metric/value argument: it is field-scoped to
    # declared line-code debt components, not reusable for monetary values/prose.
    assert "raw_value" not in inspect.signature(resolve_ambiguous_debt_line_code_cells).parameters


def test_ambiguous_code_crop_is_geometry_derived_and_outside_code_band_fails_closed():
    materialization = materialize_tsv_pages(_record(), evidence_root=EVIDENCE, pages=(10,))
    page = materialization["pages"][0]
    structural_page = {"page_number": 10, "document_sha256": DOCUMENT_SHA, "statement_family": "balance_sheet",
                       "positioned_token_provenance": page["positioned_token_provenance"],
                       "positioned_tokens": page["ocr_derived_text_evidence"]["tokens"]}
    locator = match_geometry_ambiguous_line_code_cell(structural_page, target_period="2025", required_label_terms=("vay", "ngan", "han"))
    assert locator is not None and locator["observed_line_code_raw"] == "3\u00b20"
    assert locator["code_cell_bbox"]["x0"] >= locator["row_object"]["column_bands"]["bands"]["line_code"]["x0"]
    moved = copy.deepcopy(structural_page)
    token = next(item for item in moved["positioned_tokens"] if item["text"] == "3\u00b20")
    token["x0"], token["x1"] = 400.0, 453.0
    assert match_geometry_ambiguous_line_code_cell(moved, target_period="2025", required_label_terms=("vay", "ngan", "han")) is None
    assert match_geometry_ambiguous_line_code_cell(structural_page, target_period="2025", required_label_terms=("unrelated",)) is None


def test_fpt_cell_level_code_evidence_is_deterministic_and_qualifies_only_complete_debt():
    materialization = materialize_tsv_pages(_record(), evidence_root=EVIDENCE, pages=(10,))
    first = resolve_ambiguous_debt_line_code_cells(materialization, record=_record(), evidence_root=EVIDENCE, reporting_period="2025")
    second = resolve_ambiguous_debt_line_code_cells(materialization, record=_record(), evidence_root=EVIDENCE, reporting_period="2025")
    assert first == second
    cells = {item["canonical_metric"]: item for item in first["cells"]}
    short = cells["short_term_borrowings"]
    assert short["state"] == "QUALIFIED" and short["secondary_run_count"] == 1
    evidence = short["cell_evidence"]
    assert evidence["primary_evidence"]["raw_token"] == "3\u00b20"
    assert evidence["crop_bbox"] == {"left": 248, "top": 1020, "right": 312, "bottom": 1059, "coordinate_system": "base_rendered_image_pixels_top_left"}
    assert evidence["crop_image_sha256"] and evidence["secondary_ocr"]["raw_output"] == "320\r\n"
    assert evidence["disposition"] == "QUALIFIED_BY_SECONDARY_RAW_CODE"
    assert cells["long_term_borrowings_or_finance_leases"]["state"] == "PRIMARY_EXACT"
    qualification = qualify_table_facts(materialization, ticker="FPT", reporting_period="2025", line_code_cell_resolution=first)
    debt = next(item for item in qualification["qualified_facts"] if item["canonical_metric"] == "total_interest_bearing_debt")
    assert debt["value"] == 21_073_487_486_139
    assert [item["value"] for item in debt["debt_components"]] == [19_169_697_497_955, 1_903_789_988_184]
    assert debt["debt_components"][0]["source_lineage"]["line_code_cell_evidence"] == evidence


def test_cell_level_production_path_is_document_generic_not_ticker_specific():
    source = inspect.getsource(cell_module)
    assert "ticker ==" not in source and "FPT" not in source


def test_panel_adapter_requires_qualified_metadata_and_complete_row_lineage():
    materialization = materialize_tsv_pages(_record(), evidence_root=EVIDENCE, pages=(12,))
    result = qualify_table_facts(materialization, ticker="FPT", reporting_period="2025")
    facts = panel_facts_from_qualified_ocr(result, entity_type="corporate", statement_scope="consolidated",
                                            audit_or_review_status="audited", knowledge_available_at=_record()["observed_at"], observed_at=_record()["observed_at"])
    assert {fact["canonical_metric"] for fact in facts} == {"revenue", "net_income"}
    assert all(fact["source_lineage"]["citation_id"] and fact["qualification_state"] == "QUALIFIED" for fact in facts)
