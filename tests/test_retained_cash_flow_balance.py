"""Source geometry recovery never repairs value digits or broadens authority."""
import copy
import json
from pathlib import Path
import pytest
import official_financial_structural_table as geometry
import official_financial_ocr_table_evidence as ocr

FIXTURES = Path(__file__).parent / "fixtures/retained_cash_flow_balance"

def source(ticker):
    return json.loads((FIXTURES / f"{ticker}_FY25.json").read_text(encoding="utf8"))

def qualify(mat, ticker, cells=None):
    return ocr.qualify_table_facts(mat, ticker=ticker, reporting_period="2025",
        line_code_cell_resolution=cells, scoped_unit_evidence=ocr.resolve_scoped_unit_evidence(mat),
        scoped_statement_scope_evidence=ocr.resolve_scoped_statement_scope_evidence(mat))


def test_nested_header_aliases_are_one_literal_source_phrase():
    mat = source("PVD")
    result = qualify(mat, "PVD")
    assert {f["canonical_metric"]: f["value"] for f in result["qualified_facts"]} == {
        "total_assets": 28309862682750, "shareholders_equity": 17098286949122}
    for fact in result["qualified_facts"]:
        header = fact["source_lineage"]["row_object"]["column_bands"]["header_evidence"]
        assert header["period_header_class"] == "CLOSING_OPENING_BALANCE"
        assert header["period_identities"]["current"]["raw_text"] == "Số cuối năm"
        assert header["period_identities"]["comparative"]["raw_text"] == "Số đầu năm"
    # No parent, cash or cash-flow number repairs accompany this header recovery.
    assert not any(f["canonical_metric"] in {"cash_and_equivalents", "operating_cash_flow"} for f in result["qualified_facts"])


def test_repeated_or_damaged_period_phrases_are_not_merged():
    page = ocr._pages_by_statement_family(source("PVD"))["balance_sheet"][0]
    tokens = page["positioned_tokens"]
    lines = geometry.reconstruct_physical_lines(tokens)["lines"]
    candidates = geometry._semantic_period_header_candidates(lines, target_period="2025", statement_family="balance_sheet")
    orders = candidates[0]["current"]["source_token_orders"]
    copied = copy.deepcopy(tokens)
    for token in [t for t in copied if t["raw_token_order"] in orders]:
        duplicate = copy.deepcopy(token)
        duplicate["raw_token_order"] += 10000
        duplicate["x0"] -= 200
        duplicate["x1"] -= 200
        duplicate["tsv_hierarchy"]["line_num"] += 1000
        copied.append(duplicate)
    assert geometry.discover_column_bands(geometry.reconstruct_physical_lines(copied)["lines"], "2025", statement_family="balance_sheet") is None
    damaged = copy.deepcopy(tokens)
    for token in damaged:
        if token["raw_token_order"] in orders and token["text"] == "cuối":
            token["text"] = "cu0i"
    assert geometry.discover_column_bands(geometry.reconstruct_physical_lines(damaged)["lines"], "2025", statement_family="balance_sheet") is None


def test_no_note_cash_flow_header_requires_literal_ma_so_and_two_periods():
    page = ocr._pages_by_statement_family(source("PVD"))["cash_flow"][0]
    lines = geometry.reconstruct_physical_lines(page["positioned_tokens"])["lines"]
    bands = geometry.discover_column_bands(lines, "2025", statement_family="cash_flow")
    assert bands and bands["bands"]["note_reference"] is None
    assert bands["header_evidence"]["period_header_class"] == "CURRENT_PRIOR"
    broken = copy.deepcopy(page)
    for token in broken["positioned_tokens"]:
        if token["text"] == "Mã": token["text"] = "M0"
    assert geometry.discover_column_bands(geometry.reconstruct_physical_lines(broken["positioned_tokens"])["lines"], "2025", statement_family="cash_flow") is None


def test_pnj_operating_flow_code_is_independent_from_amount_cells():
    mat = source("PNJ")
    page = ocr._pages_by_statement_family(mat)["cash_flow"][0]
    locator = geometry.match_geometry_ambiguous_line_code_cell(page, target_period="2025",
        required_label_terms=("thuan", "hoat", "dong", "kinh", "doanh"))
    assert locator["observed_line_code_raw"] == "²0"
    assert locator["current_raw"] == "18.890.403.841"
    assert not any(f["canonical_metric"] == "operating_cash_flow" for f in qualify(mat, "PNJ")["qualified_facts"])
    match = copy.deepcopy(locator)
    match["row_object"]["line_code"] = "20"
    cells = {"cells": [{"canonical_metric": "operating_cash_flow", "state": "QUALIFIED", "match": match,
        "cell_evidence": {"disposition": "QUALIFIED_BY_SECONDARY_RAW_CODE", "secondary_ocr": {"field_raw": "20"}}}]}
    result = qualify(mat, "PNJ", cells)
    assert next(f for f in result["qualified_facts"] if f["canonical_metric"] == "operating_cash_flow")["value"] == 18890403841
    match["current_raw"] = "18.89².403.841"
    result = qualify(mat, "PNJ", cells)
    assert not result["qualified_facts"]
    assert any(b["reason"] == "OCR_NUMERIC_AMBIGUITY" for b in result["blocked_candidates"])

@pytest.mark.parametrize("raw", ["2O", "²0", "200", "20 21", "", "2\n0"])
def test_secondary_code_must_be_raw_exact_without_character_repair(raw):
    assert ocr.assess_secondary_line_code_raw("20", raw)[1] != "QUALIFIED_BY_SECONDARY_RAW_CODE"


def test_append_only_refresh_preserves_first_qualification_and_precedence(tmp_path):
    from tools.run_reviewed_interim_canonical_ingress import write_outputs
    from financial_evidence_currency_refresh import PUBLIC_FACTS, PUBLIC_PRECEDENCE
    old = {"ticker": "PNJ", "canonical_metric": "cash_and_equivalents", "reporting_period": "2025",
        "statement_scope": "consolidated", "normalized_value": 522025257031, "currency": "VND",
        "unit_scale": 1, "citation_id": "first-citation", "knowledge_available_at": "2026-10-08T06:18:00+07:00"}
    new = {**old, "canonical_metric": "operating_cash_flow", "normalized_value": 18890403841, "citation_id": "new-flow"}
    newer = {**old, "citation_id": "replay-citation", "knowledge_available_at": "2026-10-08T08:00:00+07:00"}
    def precedence(row):
        return {"key": {"ticker": row["ticker"], "metric": row["canonical_metric"],
            "period": row["reporting_period"], "scope": row["statement_scope"]}, "legacy_modified": False}
    (tmp_path/PUBLIC_FACTS).write_text(json.dumps(old)+"\n",encoding="utf8")
    (tmp_path/PUBLIC_PRECEDENCE).write_text(json.dumps(precedence(old))+"\n",encoding="utf8")
    result = {"report": {"documents": [{"ticker": "PNJ", "reporting_period": "2025"}]},
        "overlay_rows": [newer, new], "precedence_rows": [precedence(newer),precedence(new)]}
    copy_before = copy.deepcopy(result)
    write_outputs(result,tmp_path,append_new_facts_only=True)
    rows = [json.loads(line) for line in (tmp_path/PUBLIC_FACTS).read_text().splitlines()]
    assert rows == [old,new]
    assert len((tmp_path/PUBLIC_PRECEDENCE).read_text().splitlines())==2
    assert result == copy_before
    write_outputs(result,tmp_path,append_new_facts_only=True)
    assert [json.loads(line) for line in (tmp_path/PUBLIC_FACTS).read_text().splitlines()] == rows
    before = (tmp_path/PUBLIC_FACTS).read_bytes()
    result["overlay_rows"][0]["normalized_value"] += 1
    with pytest.raises(ValueError,match="APPEND_ONLY_OFFICIAL_FACT_CONFLICT"):
        write_outputs(result,tmp_path,append_new_facts_only=True)
    assert (tmp_path/PUBLIC_FACTS).read_bytes() == before


def test_retained_secondary_code_evidence_never_includes_value_cells():
    root = Path(__file__).resolve().parents[1] / "derived/financial-evidence-currency-refresh-v1"
    report = json.loads((root / "retained_cash_flow_balance_report.json").read_text(encoding="utf8"))
    pnj = next(d for d in report["documents"] if d["ticker"] == "PNJ")
    cell = next(c for c in pnj["line_code_cell_resolution"]["cells"] if c["canonical_metric"] == "operating_cash_flow")
    assert cell["state"] == "QUALIFIED" and cell["secondary_run_count"] == 1
    evidence = cell["cell_evidence"]
    assert evidence["primary_evidence"]["raw_token"] == "²0"
    assert evidence["secondary_ocr"]["field_raw"] == "20"
    assert evidence["disposition"] == "QUALIFIED_BY_SECONDARY_RAW_CODE"
    assert evidence["crop_bbox"]["right"] < evidence["row_identity"]["current_value_bbox"]["x0"]
    assert evidence["crop_bbox"]["right"] < evidence["row_identity"]["comparative_value_bbox"]["x0"]
    assert report["overlay_write"]["appended_fact_count"] == 3
    assert report["overlay_write"]["prior_facts_preserved"] is True


def test_retained_runner_emits_lossless_json_on_windows_legacy_console(monkeypatch):
    import io
    import sys
    import tools.run_retained_audited_annual_context as runner
    class LegacyConsole(io.StringIO):
        def write(self, value):
            value.encode("cp1252", errors="strict")
            return super().write(value)
    stream = LegacyConsole()
    payload = {"source_token": "Mã số ²0", "quantity": 18890403841}
    monkeypatch.setattr(runner, "run", lambda **kwargs: {"report": payload})
    monkeypatch.setattr(sys, "argv", ["runner", "--tickers", "PNJ"])
    monkeypatch.setattr(sys, "stdout", stream)
    assert runner.main() == 0
    assert json.loads(stream.getvalue()) == payload
