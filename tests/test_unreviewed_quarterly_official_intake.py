"""Owner D-1: unreviewed quarterly statements stay a labelled research tier, read fail-closed."""
import json

import pytest

import official_financial_ocr_table_evidence as ocr
from official_financial_structural_table import match_quarterly_four_column_row
from tools import run_unreviewed_quarterly_official_intake as intake

H = 30.0
COLUMNS = (1500.0, 1850.0, 2200.0, 2550.0)  # right edges of the four value columns


def tok(text, x0, y, order, *, width=None, line=None):
    width = width if width is not None else 14.0 * len(text)
    return {"text": text, "x0": x0, "x1": x0 + width, "top": y, "bottom": y + H, "raw_token_order": order,
            "provenance": "OCR_TSV_POSITIONED_TOKEN", "tsv_hierarchy": {"block_num": 1, "par_num": 1, "line_num": line or int(y)}}


def amount(text, column, y, order):
    width = 14.0 * len(text)
    return tok(text, COLUMNS[column] - width, y, order, width=width)


def page(header, rows):
    tokens, order = [], 0
    for line_y, words in header:
        for word, x in words:
            order += 1
            tokens.append(tok(word, x, line_y, order))
    y = 300.0
    for code, label, values in rows:
        order += 1
        tokens.append(tok(code, 200, y, order))
        order += 1
        tokens.append(tok(label, 300, y, order))
        for column, value in values.items():
            order += 1
            tokens.append(amount(value, column, y, order))
        y += 60
    return {"page_number": 6, "statement_family": "income_statement", "positioned_tokens": tokens}


FOUR_COLUMN_HEADER = [
    (180.0, [("Mã", 200), ("Quý", 1250), ("2", 1310), ("năm", 1340), ("LŨY", 1950), ("KẾ", 2010)]),
    (230.0, [("2026", 1440), ("2025", 1790), ("2026", 2140), ("2025", 2490)]),
]
ROWS = [
    ("01", "Doanh thu bán hàng", {0: "9.000.000", 1: "8.000.000", 2: "18.000.000", 3: "15.000.000"}),
    ("10", "Doanh thu thuần về bán hàng", {0: "8.483.734", 1: "7.582.449", 2: "25.728.965", 3: "17.217.545"}),
    ("50", "Tổng lợi nhuận kế toán trước thuế", {0: "(326.947)", 1: "547.392", 2: "1.537.863", 3: "1.401.630"}),
    ("60", "Lợi nhuận/(lỗ) sau thuế TNDN", {0: "(283.029)", 1: "436.997", 2: "1.184.376", 3: "1.114.725"}),
]


def test_quarter_pair_is_taken_and_year_to_date_is_ignored():
    match = match_quarterly_four_column_row(page(FOUR_COLUMN_HEADER, ROWS), line_code="10", target_period="2026-Q2")
    assert (match["current_raw"], match["comparative_raw"]) == ("8.483.734", "7.582.449")
    assert match["row_object"]["period_binding"] == "EXPLICIT_QUARTER_COLUMN_YEARS"
    assert match["row_object"]["year_to_date_values_ignored"] == [2, 3]
    assert match["row_object"]["comparative_period_label"] == "2025-Q2"


@pytest.mark.parametrize("mutation", ["no_quarter_heading", "wrong_quarter", "cumulative_left_of_quarter", "swapped_years"])
def test_missing_or_contradictory_period_evidence_fails_closed(mutation):
    header = [(y, list(words)) for y, words in FOUR_COLUMN_HEADER]
    if mutation == "no_quarter_heading":
        header[0] = (180.0, [("Mã", 200), ("LŨY", 1950), ("KẾ", 2010)])
    if mutation == "wrong_quarter":
        header[0] = (180.0, [("Mã", 200), ("Quý", 1250), ("3", 1310), ("LŨY", 1950), ("KẾ", 2010)])
    if mutation == "cumulative_left_of_quarter":
        header[0] = (180.0, [("Mã", 200), ("LŨY", 1250), ("KẾ", 1310), ("Quý", 1950), ("2", 2010)])
    if mutation == "swapped_years":
        header[1] = (230.0, [("2025", 1440), ("2026", 1790), ("2026", 2140), ("2025", 2490)])
    assert match_quarterly_four_column_row(page(header, ROWS), line_code="10", target_period="2026-Q2") is None


def test_quarterly_target_never_binds_to_date_only_year_to_date_columns():
    header = [(180.0, [("Mã", 200), ("30/06/2026", 1950), ("30/06/2025", 2300)])]
    assert match_quarterly_four_column_row(page(header, ROWS), line_code="10", target_period="2026-Q2") is None


def test_illegible_quarter_years_bind_only_by_explicit_cumulative_order():
    header = [(180.0, [("Mã", 200), ("Quý", 1250), ("II", 1310), ("Quý", 1600), ("II", 1660), ("6", 1950), ("tháng", 1980)]),
              (230.0, [("2026", 2140), ("2025", 2490)])]
    match = match_quarterly_four_column_row(page(header, ROWS), line_code="60", target_period="2026-Q2")
    assert match["row_object"]["period_binding"] == "QUARTER_PAIR_BY_EXPLICIT_CUMULATIVE_ORDER"
    one_heading = [(180.0, [("Mã", 200), ("Quý", 1250), ("II", 1310), ("6", 1950), ("tháng", 1980)]), header[1]]
    assert match_quarterly_four_column_row(page(one_heading, ROWS), line_code="60", target_period="2026-Q2") is None


def test_superscript_damaged_amount_is_never_repaired_but_year_glyphs_are():
    tokens = [{"text": "²0²6"}, {"text": "6.4²4.474.²67.094"}, {"text": "(1.²34)"}, {"text": "Quy"}]
    assert ocr._normalize_glyph_digits(tokens) == 1
    assert [t["text"] for t in tokens] == ["2026", "6.4²4.474.²67.094", "(1.²34)", "Quy"]
    assert tokens[0]["source_text"] == "²0²6" and tokens[0]["glyph_normalization"] == ocr.GLYPH_NORMALIZATION_CONTRACT
    rows = [(c, l, dict(v)) for c, l, v in ROWS]
    rows[1][2][1] = "7.58².449"
    assert match_quarterly_four_column_row(page(FOUR_COLUMN_HEADER, rows), line_code="10", target_period="2026-Q2") is None


def test_profit_loss_qualifier_is_quarterly_only_and_keeps_forbidden_terms():
    assert ocr._quarterly_label_supports_metric("net_income", "Loi nhuan/(Ié) sau thué TNDN")
    assert not ocr._quarterly_label_supports_metric("net_income", "Lợi nhuận/(lỗ) sau thuế của cổ đông thiểu số")
    assert not ocr._quarterly_label_supports_metric("net_income", "Lợi nhuận/(lỗ) sau thuế của công ty mẹ")
    assert not ocr.row_label_supports_metric("net_income", "Lợi nhuận/(lỗ) sau thuế TNDN")  # shared contract unchanged
    with pytest.raises(ValueError, match="REQUIRES_QUARTER_PERIOD"):
        ocr.qualify_table_facts({"document_sha256": "x", "pages": [], "materialization_id": "m"}, ticker="PNJ",
                                reporting_period="2026-H1", quarterly_four_column=True)


def test_tier_rows_are_labelled_and_the_loader_rejects_any_relabelling(tmp_path):
    retained = next(r for r in intake.load_unreviewed_quarterly_facts(intake.ROOT / intake.PUBLIC_ARTIFACT_DIR)
                    if r["ticker"] == "PNJ" and r["canonical_metric"] == "revenue" and r["column_role"] == "PRIOR_YEAR_QUARTER")
    fact = {"canonical_metric": "revenue", "value": retained["value"], "currency": "VND", "unit_scale": 1, "reporting_period": "2025-Q2",
            "statement_family": "income_statement", "column_role": "PRIOR_YEAR_QUARTER",
            "reason_codes": ["OFFICIAL_QUARTERLY_STATEMENT_ROW", "COMPARATIVE_COLUMN_OF_LATER_REPORT"],
            "source_lineage": {"line_code": "10", "source_page": 6, "document_sha256": retained["document_sha256"],
                               "row_object": retained["row_object"], "unit_evidence": {"evidence": {"evidence_id": "u"}},
                               "statement_scope_evidence": {"statement_scope": "consolidated"},
                               "ocr_derived_text_evidence": {"current_raw": retained["raw_values"]["current"],
                                                             "comparative_raw": retained["raw_values"]["comparative"], "materialization_id": "m"}}}
    record = {"sha256": retained["document_sha256"], "ticker": "PNJ", "reporting_period": intake.PERIOD,
              "observed_at": "2026-09-29T11:31:14Z", "document_class": "reviewed_interim_financial_statements",
              "source_id": retained["source_family"], "canonical_url": retained["canonical_url"]}
    row = intake.fact_row(fact, ticker="PNJ", record=record, assurance={"state": "BLOCKED", "reason": "ASSURANCE_STATUS_NOT_EXPLICIT"}, adapters={})
    assert (row["evidence_tier"], row["audit_or_review_status"], row["qualification_state"]) == (
        "UNREVIEWED_QUARTERLY", "unreviewed", "QUALIFIED_UNREVIEWED_QUARTERLY_RESEARCH")
    assert (row["period_start"], row["period_end"], row["period_type"]) == ("2025-04-01", "2025-06-30", "quarter")
    assert "NO_Q1_BY_SUBTRACTION" in row["research_use_restrictions"] and row["publication_date"] is None
    intake.write_outputs({"rows": [row], "report": {}}, tmp_path)
    assert intake.load_unreviewed_quarterly_facts(tmp_path) == [row]
    (tmp_path / intake.PUBLIC_FACTS).write_text(json.dumps({**row, "audit_or_review_status": "reviewed"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="TIER_LABEL_INVALID"):
        intake.load_unreviewed_quarterly_facts(tmp_path)


@pytest.mark.parametrize("field,value", [("reporting_period", "2026-Q1"), ("period_start", "2025-01-01"),
    ("document_sha256", "0" * 64), ("source_page", 1), ("value", 0), ("statement_scope", "standalone"),
    ("official_fact_admitted", True), ("strict_valuation_eligible", True), ("existing_consumer_usable", True),
    ("publication_date", "2026-06-30"), ("research_use_restrictions", [])])
def test_tier_loader_refuses_period_source_value_and_authority_tampering(tmp_path, field, value):
    row = intake.load_unreviewed_quarterly_facts(intake.ROOT / intake.PUBLIC_ARTIFACT_DIR)[0]
    (tmp_path / intake.PUBLIC_FACTS).write_text(json.dumps({**row, field: value}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        intake.load_unreviewed_quarterly_facts(tmp_path)


def test_non_year_numeric_glyphs_and_non_loss_identity_qualifiers_are_not_repaired():
    tokens = [{"text": text} for text in ("²00", "(²00)", "²0²6", "1.²34")]
    assert ocr._normalize_glyph_digits(tokens) == 1
    assert [t["text"] for t in tokens] == ["²00", "(²00)", "2026", "1.²34"]
    header = [tok("Quy", 100, 100, 1), tok("²", 150, 100, 2)]
    assert ocr._normalize_glyph_digits(header) == 1 and header[1]["text"] == "2"
    assert not ocr._quarterly_label_supports_metric("net_income", "Lợi nhuận/(mẹ) sau thuế TNDN")


def test_six_retained_research_facts_never_enter_the_reviewed_overlay():
    from financial_evidence_currency_refresh import load_public_official_fact_rows
    research = intake.load_unreviewed_quarterly_facts(intake.ROOT / intake.PUBLIC_ARTIFACT_DIR)
    reviewed = load_public_official_fact_rows(intake.ROOT)
    assert len(research) == 6
    assert {r["fact_id"] for r in research}.isdisjoint({r.get("fact_id") for r in reviewed})
    assert {r["ticker"] for r in research} == {"NVL", "PNJ"}
    with pytest.raises(ValueError, match="REQUIRES_SEPARATE_RESEARCH_TIER"):
        ocr.panel_facts_from_qualified_ocr({"qualified_facts": research}, entity_type="corporate",
            statement_scope="consolidated", audit_or_review_status="audited",
            knowledge_available_at="2026-10-22", observed_at="2026-10-22")
