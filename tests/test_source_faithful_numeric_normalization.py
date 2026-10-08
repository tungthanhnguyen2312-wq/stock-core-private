"""Superscript amount cells stay blocked until independent confirmation exists."""
import json
import re
import unicodedata
from pathlib import Path

from annual_financial_ocr_materialization import parse_accounting_integer
from official_financial_ocr_table_evidence import row_label_supports_metric
from official_financial_structural_table import _semantic_header_spans
from source_faithful_numeric_glyph_normalization import (
    DISPOSITION, cohort_decisions, normalization_decision, unicode_compatibility_folds_superscript_digits,
)

FIXTURE = Path(__file__).parent / "fixtures/source_faithful_normalization_candidates.json"
YEAR = re.compile(r"20[0-3][0-9]")


def _header_line(words):
    tokens = []
    for index, word in enumerate(words, start=1):
        tokens.append({"text": word, "raw_token_order": index, "x0": index * 20, "x1": index * 20 + 10,
                       "tsv_hierarchy": {"page_num": 1, "block_num": 1, "par_num": 1, "line_num": 1}})
    return [{"line_id": 1, "text": " ".join(words), "tokens": tokens, "baseline": 10}]


def test_nfkc_maps_superscript_digits_but_year_identity_uses_the_raw_token():
    assert unicodedata.normalize("NFKC", "²0²5") == "2025"
    assert unicode_compatibility_folds_superscript_digits("²0²5")
    assert YEAR.fullmatch("²0²5") is None
    assert YEAR.fullmatch("2025")


def test_labels_codes_units_and_damaged_headers_are_not_numeric_amounts():
    for candidate in (
        {"raw_token": "Provisi²ns", "token_class": "ROW_LABEL", "row_identity_qualified": True, "column_identity_qualified": True},
        {"raw_token": "0²", "token_class": "ROW_CODE", "row_identity_qualified": True, "column_identity_qualified": True},
        {"raw_token": "triệu²", "token_class": "UNIT", "row_identity_qualified": True, "column_identity_qualified": True},
        {"raw_token": "1²3", "token_class": "NUMERIC_AMOUNT", "row_identity_qualified": False, "column_identity_qualified": True},
        {"raw_token": "1²3", "token_class": "NUMERIC_AMOUNT", "row_identity_qualified": True, "column_identity_qualified": False},
        {"raw_token": "1²3", "token_class": "NUMERIC_AMOUNT", "row_identity_qualified": True, "column_identity_qualified": True, "competing_numeric_token": True},
        {"raw_token": "1²3", "token_class": "NUMERIC_AMOUNT", "row_identity_qualified": True, "column_identity_qualified": True, "footnote_ambiguity": True},
        {"raw_token": "1²3", "token_class": "NUMERIC_AMOUNT", "row_identity_qualified": True, "column_identity_qualified": True,
         "independent_confirmation": "SAME_OCR_PROFILE"},
    ):
        decision = normalization_decision(candidate)
        assert decision["state"] == "STILL_BLOCKED" and decision["normalized_token"] is None
        assert decision["raw_token"] == candidate["raw_token"]
        assert decision["admitted"] is False
    assert not row_label_supports_metric("provision_charge_or_reversal_adjustment", "Provisi²ns")
    assert row_label_supports_metric("total_assets", "Tài sản dài hạn khác") is False
    assert _semantic_header_spans(_header_line(["Số", "cudi", "ky"]), phrases=("so cuoi ky", "cuoi ky"), header_class="CLOSING_BALANCE") == []
    assert _semantic_header_spans(_header_line(["Số", "cuối", "kỳ"]), phrases=("so cuoi ky",), header_class="CLOSING_BALANCE")


def test_confirmation_does_not_emit_a_normalized_amount_and_repeat_is_identical():
    ready = {"raw_token": "1,23²,456", "token_class": "NUMERIC_AMOUNT", "row_identity_qualified": True,
             "column_identity_qualified": True, "independent_confirmation": "NATIVE_PDF_TEXT_LAYER"}
    first, second = normalization_decision(ready), normalization_decision(ready)
    assert first == second
    assert first["disposition"] == DISPOSITION and first["normalized_token"] is None
    assert "INDEPENDENT_CONFIRMATION_ABSENT" not in first["reasons"]
    assert DISPOSITION in first["reasons"]


def test_retained_cohort_stays_blocked_and_parser_rejects_the_raw_token():
    cohort = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(cohort) == 5
    decisions = cohort_decisions(cohort)
    assert {item["state"] for item in decisions} == {"STILL_BLOCKED"}
    assert all(item["raw_token"] == source["raw_token"] and item["normalized_token"] is None
               for item, source in zip(decisions, cohort))
    hpg = decisions[-1]
    assert "FOOTNOTE_SUPERSCRIPT_AMBIGUITY" in hpg["reasons"]
    for source in cohort:
        try:
            parse_accounting_integer(source["raw_token"])
        except ValueError as error:
            assert str(error) == "OCR_NUMERIC_AMBIGUITY"
        else:
            raise AssertionError(source["raw_token"])
