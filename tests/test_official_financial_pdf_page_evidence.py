"""Regression coverage for retained official-financial PDF page/table extraction."""
from __future__ import annotations

from copy import deepcopy
import ast
import hashlib
from pathlib import Path

from annual_financial_ocr_materialization import parse_accounting_integer
from official_financial_pdf_page_evidence import (
    VERSION,
    build_artifact,
    extract_candidates,
)
from p3f13_official_financial_evidence_scaleout import merge_document_qualified_facts_into_panel


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "operations-review" / "approved-issuer-ir-official-financial-evidence-cohort-v1-20260827" / "evidence" / "AAA_fa5a765bf5214c56a609361699a04e9d527e99b34c18c2ff52ac12aecd197fd8.bin"
DOCUMENT = {
    "document_id": "issuer-ir:AAA:fa5a765bf5214c56a609361699a04e9d527e99b34c18c2ff52ac12aecd197fd8",
    "ticker": "AAA",
    "sha256": "fa5a765bf5214c56a609361699a04e9d527e99b34c18c2ff52ac12aecd197fd8",
    "official_url": "https://anphatbioplastics.com/wp-content/uploads/2025/10/BCTN-AAA-2024-VIE-2.pdf",
    "retrieved_at": "2026-08-27T06:52:19.219164Z",
}


def _artifact() -> dict:
    # A function attribute avoids repeated PDF parsing while retaining an actual
    # immutable-file integration fixture rather than a hand-built synthetic PDF.
    if not hasattr(_artifact, "value"):
        _artifact.value = build_artifact(document=DOCUMENT, path=SOURCE)  # type: ignore[attr-defined]
    return _artifact.value  # type: ignore[attr-defined]


def test_page_hashes_metadata_and_current_period_orientation_are_explicit():
    artifact = _artifact()
    assert artifact["schema_version"] == VERSION
    assert artifact["page_count"] == 104
    for page in artifact["page_evidence"]:
        assert hashlib.sha256(page["page_text"].encode("utf-8")).hexdigest() == page["page_text_hash"]
        assert page["document_sha256"] == DOCUMENT["sha256"]
        assert page["page_evidence_id"]

    claims = artifact["document_metadata"]["metadata_claims"]
    assert claims["issuer_identity"]["value"] == "CÔNG TY CỔ PHẦN NHỰA AN PHÁT XANH"
    assert claims["reporting_period"]["value"] == "2024"
    assert claims["periodicity"]["value"] == "annual"
    assert claims["statement_scope"]["value"] == "consolidated"
    assert claims["audit_or_review_status"]["value"] == "audited"
    assert claims["currency"]["value"] == "VND"
    assert claims["unit_scale"]["value"] == 1

    by_metric = {row["canonical_metric"]: row for row in artifact["fact_candidates"]}
    assert by_metric["total_assets"]["period_column_label"] == "Số cuối năm"
    assert by_metric["revenue"]["period_column_label"] == "Năm nay"
    assert all(row["fiscal_period"] == "2024" for row in by_metric.values())


def test_exact_canonical_mapping_has_page_table_row_citation_and_native_coordinates():
    artifact = _artifact()
    expected = {
        "cash_and_equivalents": (2_419_517_905_105, 68),
        "total_assets": (13_768_215_584_455, 69),
        "shareholders_equity": (6_236_273_953_200, 69),
        "total_interest_bearing_debt": (3_894_476_057_853, 69),
        "revenue": (12_782_230_561_048, 70),
        "net_income": (368_580_504_091, 70),
        "operating_cash_flow": (958_913_854_214, 70),
    }
    assert len(artifact["fact_candidates"]) == len(expected)
    for row in artifact["fact_candidates"]:
        value, page = expected[row["canonical_metric"]]
        assert row["canonical_mapping_state"] == "CANONICAL_IDENTITY_EXACT"
        assert row["normalized_value"] == value
        assert row["page_number"] == page
        assert row["table_id"] and row["raw_row_label"]
        span = row["source_span"]
        assert span["text"]
        if row["canonical_metric"] == "total_interest_bearing_debt":
            assert span["coordinate_status"] == "UNAVAILABLE_FOR_DERIVED_OR_WRAPPED_ROW"
            assert span["start"] is None and span["end"] is None
        else:
            assert span["coordinate_status"] == "NATIVE_TEXT_LINE"
            assert isinstance(span["start"], int) and span["end"] > span["start"]
    assert all(row["source_lineage"]["source_page"] and row["source_lineage"]["citation_id"]
               for row in artifact["p3f13_panel_facts"])


def test_negative_and_dash_cells_are_not_silently_repaired_to_positive_or_zero():
    assert parse_accounting_integer("(1.234)") == (-1234, "negative")
    try:
        parse_accounting_integer("-")
    except ValueError as error:
        assert str(error) == "OCR_NUMERIC_AMBIGUITY"
    else:  # pragma: no cover - defensive regression guard
        raise AssertionError("a dash must not silently become numeric zero in page extraction")


def test_missing_currency_or_scale_blocks_ingress_and_bank_or_securities_get_no_corporate_mapping():
    artifact = _artifact()
    for missing_field in ("currency", "unit_scale"):
        metadata = deepcopy(artifact["document_metadata"])
        metadata["metadata_claims"][missing_field]["value"] = None
        metadata["qualification_status"] = "DOCUMENT_METADATA_BLOCKED"
        candidates, _ = extract_candidates(document=DOCUMENT, pages=artifact["page_evidence"], metadata=metadata)
        assert candidates and {row["qualification_status"] for row in candidates} == {"OFFICIAL_FACT_CANDIDATE_BLOCKED"}

    for entity_type in ("bank", "securities"):
        document = {**DOCUMENT, "entity_type": entity_type}
        candidates, rejected = extract_candidates(document=document, pages=artifact["page_evidence"], metadata=artifact["document_metadata"])
        assert candidates == []
        assert rejected == [{"state": "NOT_APPLICABLE", "reason": "ENTITY_LAYOUT_NOT_SUPPORTED_BY_CORPORATE_TEMPLATE", "entity_type": entity_type}]


def test_only_qualified_document_cited_facts_enter_p3f13_and_duplicate_key_replaces():
    facts = _artifact()["p3f13_panel_facts"]
    merged = merge_document_qualified_facts_into_panel({"issuers": []}, facts + facts)
    issuer_facts = merged["issuers"][0]["facts"]
    assert len(issuer_facts) == 7
    assert all(row["qualification_state"] == "QUALIFIED" and row["source_lineage"]["citation_id"] for row in issuer_facts)

    rejected = deepcopy(facts[0])
    rejected["qualification_state"] = "OFFICIAL_FACT_CANDIDATE_BLOCKED"
    try:
        merge_document_qualified_facts_into_panel({"issuers": []}, [rejected])
    except ValueError as error:
        assert str(error) == "P3F13_REQUIRES_QUALIFIED_DOCUMENT_CITED_FACT"
    else:  # pragma: no cover
        raise AssertionError("blocked candidates must not enter P3-F13")


def test_artifact_is_deterministic_and_production_module_has_no_ticker_network_or_value_activation_branch():
    first = _artifact()
    second = build_artifact(document=DOCUMENT, path=SOURCE)
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["authority"] == {
        "network_used": False, "provider_used": False,
        "production_db_mutated": False, "value_or_recommendation_activated": False,
    }

    source = (ROOT / "official_financial_pdf_page_evidence.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "AAA" not in {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "requests" not in source and "urllib" not in source and "sqlite" not in source
