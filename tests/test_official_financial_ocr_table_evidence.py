"""Focused retained-only coverage for image-table TSV OCR evidence."""
from __future__ import annotations

import json
from pathlib import Path

from annual_financial_ocr_materialization import parse_accounting_integer
from official_financial_ocr_table_evidence import materialize_tsv_pages, panel_facts_from_qualified_ocr, qualify_table_facts
from official_financial_structural_table import match_geometry_table_row


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


def test_panel_adapter_requires_qualified_metadata_and_complete_row_lineage():
    materialization = materialize_tsv_pages(_record(), evidence_root=EVIDENCE, pages=(12,))
    result = qualify_table_facts(materialization, ticker="FPT", reporting_period="2025")
    facts = panel_facts_from_qualified_ocr(result, entity_type="corporate", statement_scope="consolidated",
                                            audit_or_review_status="audited", knowledge_available_at=_record()["observed_at"], observed_at=_record()["observed_at"])
    assert {fact["canonical_metric"] for fact in facts} == {"revenue", "net_income"}
    assert all(fact["source_lineage"]["citation_id"] and fact["qualification_state"] == "QUALIFIED" for fact in facts)
