"""Focused contracts for generic table/page-scoped financial unit evidence."""
from __future__ import annotations

import inspect

from financial_statement_unit_resolution import (
    CONTRACT_VERSION, declaration_from_tokens, parse_explicit_unit_declaration,
    resolve_unit_for_scope,
)
import official_financial_ocr_table_evidence as ocr


DOC = "a" * 64


def _declaration(text: str, *, scope: str = "table", page: int = 1, family: str = "balance_sheet", table: str | None = "t1"):
    parsed = parse_explicit_unit_declaration(text)
    assert parsed is not None
    return {**parsed, "scope_level": scope, "document_sha256": DOC, "page_number": page,
            "statement_family": family, "table_id": table, "evidence_id": f"{scope}:{page}:{table}:{text}"}


def _resolve(declarations, *, table: str = "t1", page: int = 1, family: str = "balance_sheet"):
    return resolve_unit_for_scope(declarations, document_sha256=DOC, page_number=page,
                                  statement_family=family, table_id=table)


def test_explicit_table_local_vnd_million_wins_over_document_usd():
    result = _resolve([_declaration("Đơn vị tính: VND million"),
                       _declaration("Unit: USD", scope="document", table=None)])
    assert result["state"] == "QUALIFIED"
    assert (result["currency"], result["unit_scale"], result["scope_level"]) == ("VND", 1_000_000, "table")


def test_explicit_table_local_usd_is_preserved_without_fx_conversion():
    result = _resolve([_declaration("Unit: USD")])
    assert (result["currency"], result["unit_scale"]) == ("USD", 1)


def test_unrelated_usd_on_the_same_page_but_another_table_does_not_contaminate_table_vnd():
    result = _resolve([_declaration("Đơn vị: triệu đồng"),
                       _declaration("Currency: USD", page=1, family="balance_sheet", table="t2")])
    assert (result["currency"], result["unit_scale"]) == ("VND", 1_000_000)


def test_table_local_usd_overrides_document_wide_vnd():
    result = _resolve([_declaration("Unit: USD"), _declaration("Đơn vị tính: VND", scope="statement_page", table=None)])
    assert result["currency"] == "USD" and result["scope_level"] == "table"


def test_conflicting_same_table_declarations_fail_closed():
    result = _resolve([_declaration("Unit: VND"), _declaration("Unit: USD")])
    assert result["state"] == "UNIT_SCALE_BLOCKED"
    assert result["reason"] == "SCOPED_UNIT_DECLARATION_CONFLICT"


def test_currency_known_scale_unknown_is_not_qualified_when_contract_requires_scale():
    result = _resolve([{"scope_level": "table", "document_sha256": DOC, "page_number": 1,
                        "statement_family": "balance_sheet", "table_id": "t1", "currency": "VND",
                        "unit_scale": None, "evidence_id": "currency-only"}])
    assert result["state"] == "UNIT_SCALE_BLOCKED"


def test_scale_without_currency_is_blocked():
    assert parse_explicit_unit_declaration("Đơn vị tính: triệu") is None


def test_vnd_thousand_and_base_vnd_are_distinct():
    assert parse_explicit_unit_declaration("Đơn vị tính: VND thousand")["unit_scale"] == 1_000
    assert parse_explicit_unit_declaration("Đơn vị tính: VND")["unit_scale"] == 1


def test_bilingual_and_normalized_declarations_are_supported():
    assert parse_explicit_unit_declaration("Unit: VND million")["unit_scale"] == 1_000_000
    assert parse_explicit_unit_declaration("Don vi tinh: trieu dong")["currency"] == "VND"


def test_ambiguous_ocr_declaration_fails_closed():
    assert parse_explicit_unit_declaration("Don vi tinh: VND USD") is None


def test_statement_page_fallback_is_bounded_and_document_fallback_is_last():
    page = _declaration("Đơn vị tính: VND", scope="statement_page", table=None)
    document = _declaration("Unit: USD", scope="document", table=None)
    assert _resolve([page, document])["scope_level"] == "statement_page"
    assert _resolve([document])["scope_level"] == "document"


def test_missing_scope_fails_closed():
    result = _resolve([])
    assert result == {"state": "UNIT_SCALE_BLOCKED", "reason": "SCOPED_UNIT_DECLARATION_MISSING"}


def test_token_declaration_has_exact_token_provenance_and_deterministic_identity():
    tokens = [
        {"text": "Đơn", "token_id": "a", "raw_token_order": 1, "tsv_hierarchy": {"block_num": 1, "par_num": 1, "line_num": 1}},
        {"text": "vị", "token_id": "b", "raw_token_order": 2, "tsv_hierarchy": {"block_num": 1, "par_num": 1, "line_num": 1}},
        {"text": "tính:", "token_id": "c", "raw_token_order": 3, "tsv_hierarchy": {"block_num": 1, "par_num": 1, "line_num": 1}},
        {"text": "VND", "token_id": "d", "raw_token_order": 4, "tsv_hierarchy": {"block_num": 1, "par_num": 1, "line_num": 1}},
    ]
    first = declaration_from_tokens(tokens=tokens, document_sha256=DOC, page_number=1, statement_family="balance_sheet", table_id="t1")
    second = declaration_from_tokens(tokens=tokens, document_sha256=DOC, page_number=1, statement_family="balance_sheet", table_id="t1")
    assert first == second and first[0]["source_span"]["token_ids"] == ["a", "b", "c", "d"]


def test_ocr_qualification_api_exposes_scoped_unit_evidence_and_preserves_legacy_default():
    signature = inspect.signature(ocr.qualify_table_facts)
    assert "scoped_unit_evidence" in signature.parameters
    assert signature.parameters["currency"].default == "VND"
    assert CONTRACT_VERSION == "financial_statement_scoped_unit_resolution/v1"


def test_no_ticker_specific_logic_in_scoped_resolver():
    source = inspect.getsource(__import__("financial_statement_unit_resolution"))
    assert "ticker ==" not in source and '"NVL"' not in source and '"FPT"' not in source
