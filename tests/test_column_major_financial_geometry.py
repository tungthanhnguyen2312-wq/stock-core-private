"""Focused native-geometry regression tests for column-major corporate tables."""
from __future__ import annotations

import json
from pathlib import Path

from official_financial_pdf_page_evidence import build_artifact
import official_financial_structural_table as structural


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "operations-review" / "governed-official-evidence-v1" / "data" / "official-evidence" / "manifest.json"


def _token(text: str, x0: float, top: float, order: int) -> dict:
    return {"text": text, "x0": x0, "x1": x0 + max(1, len(text)) * 0.55,
            "top": top, "bottom": top + 1, "font_size": 1, "raw_token_order": order}


def _geometry_fixture() -> list[dict]:
    rows = [
        ("Net revenue", "10", "31", "100,000", "90,000"),
        ("Cost of sales", "11", "31", "70,000", "65,000"),
        ("Gross profit", "20", "31", "30,000", "25,000"),
        ("Operating profit", "30", "32", "20,000", "15,000"),
        ("Shareholders of the parent company", "61", "40", "12,000", "9,000"),
    ]
    tokens = [_token("Code Note 2024 2023", 40, 510, 0)]
    for index, (label, code, note, current, comparative) in enumerate(rows, 1):
        y = 490 - index * 20
        tokens.extend([_token(label, 10, y, len(tokens)), _token(code, 50, y, len(tokens) + 1),
                       _token(note, 75, y, len(tokens) + 2), _token(current, 110, y, len(tokens) + 3),
                       _token(comparative, 180, y, len(tokens) + 4)])
    return tokens


def _period_header_fixture(header: list[tuple[str, float]]) -> list[dict]:
    rows = [
        ("Net revenue", "10", "31", "100,000", "90,000"),
        ("Cost of sales", "11", "31", "70,000", "65,000"),
        ("Gross profit", "20", "31", "30,000", "25,000"),
        ("Operating profit", "30", "32", "20,000", "15,000"),
        ("Shareholders of the parent company", "61", "40", "12,000", "9,000"),
    ]
    tokens = [_token(text, x0, 510, index) for index, (text, x0) in enumerate(header)]
    for index, (label, code, note, current, comparative) in enumerate(rows, 1):
        y = 490 - index * 20
        tokens.extend([_token(label, 10, y, len(tokens)), _token(code, 50, y, len(tokens) + 1),
                       _token(note, 75, y, len(tokens) + 2), _token(current, 110, y, len(tokens) + 3),
                       _token(comparative, 180, y, len(tokens) + 4)])
    return tokens


def test_physical_lines_are_geometry_deterministic_and_x_sorted_not_stream_sorted():
    tokens = _geometry_fixture()
    first = structural.reconstruct_physical_lines(tokens)
    second = structural.reconstruct_physical_lines(list(reversed(tokens)))
    assert first["vertical_tolerance"] == second["vertical_tolerance"]
    first_line = next(line for line in first["lines"] if "Net revenue" in line["text"])
    second_line = next(line for line in second["lines"] if "Net revenue" in line["text"])
    assert [token["text"] for token in first_line["tokens"]] == ["Net revenue", "10", "31", "100,000", "90,000"]
    assert [token["text"] for token in second_line["tokens"]] == ["Net revenue", "10", "31", "100,000", "90,000"]
    assert 0.5 <= first["vertical_tolerance"] <= 3.0


def test_column_bands_require_explicit_two_period_header_and_keep_code_note_distinct():
    lines = structural.reconstruct_physical_lines(_geometry_fixture())["lines"]
    bands = structural.discover_column_bands(lines, "2024")
    assert bands is not None
    assert bands["current_period_label"] == "2024"
    assert bands["comparative_period_label"] == "2023"
    assert bands["bands"]["line_code"]["x1"] < bands["bands"]["note_reference"]["x0"]
    assert bands["bands"]["note_reference"]["x1"] < bands["bands"]["current_period_value"]["x0"]
    no_header = [token for token in _geometry_fixture() if "2024" not in token["text"]]
    assert structural.discover_column_bands(structural.reconstruct_physical_lines(no_header)["lines"], "2024") is None
    reversed_header = [dict(token) for token in _geometry_fixture()]
    reversed_header[0]["text"] = "Code Note 2023 2024"
    reversed_match = structural._geometry_column_major_match({"page_number": 1, "document_sha256": "x", "positioned_tokens": reversed_header}, "net_income", "2024")
    assert reversed_match is not None
    assert (reversed_match["current_raw"], reversed_match["comparative_raw"]) == ("9,000", "12,000")


def test_explicit_full_dates_bind_current_and_comparative_bands_with_provenance():
    tokens = _period_header_fixture([("Code", 50), ("Note", 75), ("31", 110), ("December", 116), ("2024", 126),
                                     ("31", 180), ("December", 186), ("2023", 196)])
    bands = structural.discover_column_bands(structural.reconstruct_physical_lines(tokens)["lines"], "2024", statement_family="income_statement")
    assert bands is not None
    assert bands["header_evidence"]["period_header_class"] == "EXPLICIT_FULL_DATE"
    assert bands["current_period_label"] == "31 December 2024"
    assert bands["comparative_period_label"] == "31 December 2023"
    assert bands["header_evidence"]["period_identities"]["current"]["parsed_date"] == "2024-12-31"
    assert bands["bands"]["current_period_value"]["x0"] < bands["bands"]["comparative_period_value"]["x0"]


def test_balance_sheet_closing_opening_is_family_scoped_and_geometry_bound():
    tokens = _period_header_fixture([("Code", 50), ("Note", 75), ("Closing", 105), ("balance", 110),
                                     ("Opening", 175), ("balance", 180)])
    lines = structural.reconstruct_physical_lines(tokens)["lines"]
    bands = structural.discover_column_bands(lines, "2024", statement_family="balance_sheet")
    assert bands is not None
    assert bands["header_evidence"]["period_header_class"] == "CLOSING_OPENING_BALANCE"
    assert bands["current_period_label"] == "Closing balance"
    assert bands["comparative_period_label"] == "Opening balance"
    assert structural.discover_column_bands(lines, "2024", statement_family="income_statement") is None


def test_current_prior_reversal_preserves_explicit_direction_not_left_right_assumption():
    tokens = _period_header_fixture([("Code", 50), ("Note", 75), ("Prior", 110), ("Current", 180)])
    bands = structural.discover_column_bands(structural.reconstruct_physical_lines(tokens)["lines"], "2024", statement_family="cash_flow")
    assert bands is not None
    assert bands["header_evidence"]["period_header_class"] == "CURRENT_PRIOR"
    assert bands["current_period_label"] == "Current"
    assert bands["bands"]["current_period_value"]["x0"] > bands["bands"]["comparative_period_value"]["x0"]


def test_current_prior_fused_tokens_feed_the_existing_ocr_row_geometry_path():
    tokens = _period_header_fixture([("Code", 50), ("Note", 75), ("Prior year", 110), ("Current year", 180)])
    for token in tokens:
        token["provenance"] = "OCR_TSV_POSITIONED_TOKEN"
        if token["top"] != 510 and token["x0"] == 10:
            token["x0"], token["x1"] = 55, 70
    page = {"page_number": 1, "document_sha256": "synthetic", "statement_family": "income_statement", "positioned_tokens": tokens}
    match = structural.match_geometry_table_row(page, line_code="10", target_period="2024", label_anchors=("net revenue",), require_label_anchor=True)
    assert match is not None
    assert (match["current_raw"], match["comparative_raw"]) == ("90,000", "100,000")
    assert match["row_object"]["column_bands"]["header_evidence"]["period_header_class"] == "CURRENT_PRIOR"


def test_malformed_single_or_competing_period_headers_fail_closed_without_year_fallback():
    malformed = _period_header_fixture([("Code", 50), ("Note", 75), ("31/13/2024", 110), ("31/12/2023", 180)])
    single = _period_header_fixture([("Code", 50), ("Note", 75), ("31/12/2024", 110)])
    competing = _period_header_fixture([("Code", 50), ("Note", 75), ("31/12/2024", 110), ("31/12/2023", 140),
                                        ("31/12/2022", 180), ("31/12/2021", 210)])
    for tokens in (malformed, single, competing):
        assert structural.discover_column_bands(structural.reconstruct_physical_lines(tokens)["lines"], "2024", statement_family="income_statement") is None


def test_geometry_rejects_a_line_code_lookalike_in_note_band_and_preserves_raw_fragments():
    page = {"page_number": 1, "document_sha256": "x", "positioned_tokens": _geometry_fixture()}
    match = structural._geometry_column_major_match(page, "net_income", "2024")
    assert match is not None
    assert match["row_object"]["line_code"] == "61"
    assert match["row_object"]["note_reference"] == "40"
    assert match["row_object"]["raw_label_fragments"] == ["Shareholders of the parent company"]
    altered = [dict(token) for token in _geometry_fixture()]
    next(token for token in altered if token["text"] == "61")["x0"] = 75  # note band, not code band
    assert structural._geometry_column_major_match({"page_number": 1, "document_sha256": "x", "positioned_tokens": altered}, "net_income", "2024") is None


def _hpg_artifacts() -> dict[str, dict]:
    if hasattr(_hpg_artifacts, "value"):
        return _hpg_artifacts.value  # type: ignore[attr-defined]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    result = {}
    for row in manifest["records"]:
        if row["sha256"].startswith(("44919df68306", "4fb8f8e0f8dd")):
            document = {"document_id": row["document_id"], "ticker": row["ticker"], "sha256": row["sha256"],
                        "official_url": row["source_url"], "retrieved_at": row["observed_at"], "entity_type": "corporate"}
            result[row["reporting_period"]] = build_artifact(document=document, path=ROOT / row["archive_document_path"])
    _hpg_artifacts.value = result  # type: ignore[attr-defined]
    return result


def test_hpg_2022_and_2023_independently_qualify_geometry_cited_target_facts():
    expected = {
        "2022": {"revenue": 141_409_274_460_632, "net_income": 8_483_510_554_031, "operating_cash_flow": 12_277_636_676_507},
        "2023": {"revenue": 118_953_027_893_654, "net_income": 6_835_064_334_356, "operating_cash_flow": 8_643_030_777_026},
    }
    for period, values in expected.items():
        candidates = {row["canonical_metric"]: row for row in _hpg_artifacts()[period]["fact_candidates"]}
        assert {metric: candidates[metric]["normalized_value"] for metric in values} == values
        for metric in values:
            evidence = candidates[metric]["structural_evidence"]
            assert evidence["row_layout"] == "column_major_geometry"
            assert evidence["row_object"]["current_period_label"] == period
            assert evidence["row_object"]["current_value_bbox"]
            assert candidates[metric]["table_id"] and candidates[metric]["raw_numeric_text"]


def test_hpg_existing_official_collisions_remain_explicit_and_never_ingress():
    import p3f13_official_financial_evidence_scaleout as p3f13

    candidates = [candidate for artifact in _hpg_artifacts().values() for candidate in artifact["fact_candidates"]]
    records = structural.reconcile_against_existing_panel(candidates, p3f13.execute()["refreshed_panel_data"])
    assert len(records) == 6
    assert all(not record["eligible_for_ingress"] for record in records)
    by_metric = {(record["reporting_period"], record["canonical_metric"]): record["classification"] for record in records}
    assert set(by_metric.values()) == {"EXACT_MATCH"}
