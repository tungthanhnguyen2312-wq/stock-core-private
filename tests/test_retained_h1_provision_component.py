"""Retained PNJ/VRE H1 provision components and total-asset row identity."""
import json
from pathlib import Path
import pytest
from official_financial_ocr_table_evidence import (
    qualify_table_facts, resolve_scoped_statement_scope_evidence, resolve_scoped_unit_evidence,
    row_label_supports_metric,
)
from reviewed_interim_canonical_ingress import (
    EARNINGS_COMPONENT_CONTRACT, CONTRACT_VERSION, earnings_component_is_admitted, overlay_rows_from_panel_facts,
)
from tools.run_retained_h1_component_context import emphasis_of_matter_evidence

FIXTURE = Path(__file__).parent / "fixtures/retained_h1_components"


def source(name):
    return json.loads((FIXTURE / name).read_text(encoding="utf8"))


def qualify(m, ticker):
    return qualify_table_facts(m, ticker=ticker, reporting_period="2026-H1", include_earnings_quality_components=True,
                               scoped_unit_evidence=resolve_scoped_unit_evidence(m),
                               scoped_statement_scope_evidence=resolve_scoped_statement_scope_evidence(m))


@pytest.mark.parametrize("label,ok", [("TONG CONG TAI SAN", True), ("TỔNG TÀI SẢN", True), ("Total assets", True),
    ("Tai san dai han khác", False), ("TỔNG TÀI SẢN NGẮN HẠN", False), ("Tài sản ngắn hạn khác", False), ("", False)])
def test_total_assets_requires_literal_total_label(label, ok):
    assert row_label_supports_metric("total_assets", label) is ok


@pytest.mark.parametrize("label,ok", [("Cac khoan dy phòng/(hºàn nhap dy phòng)", True), ("Các khoản dự phòng", True),
    ("Khấu hao tài sản cố định", False), ("Lãi, lỗ chênh lệch tỷ giá hối đoái", False),
    ("Lãi từ hoạt động đầu tư", False), ("Dự phòng", False)])
def test_provision_component_label_contract(label, ok):
    assert row_label_supports_metric("provision_charge_or_reversal_adjustment", label) is ok


def test_pnj_renumbered_other_long_term_assets_never_becomes_total_assets():
    q = qualify(source("pnj_h1_positioned_tokens.json"), "PNJ")
    metrics = {f["canonical_metric"]: f["value"] for f in q["qualified_facts"]}
    assert "total_assets" not in metrics and 1036364443459 not in metrics.values()
    assert {"canonical_metric": "total_assets", "line_code": "270", "statement_family": "balance_sheet",
            "state": "BLOCKED", "reason": "ROW_LABEL_DOES_NOT_SUPPORT_METRIC"} in q["blocked_candidates"]


def test_pnj_and_vre_literal_provision_rows_qualify_without_repair():
    pnj = qualify(source("pnj_h1_positioned_tokens.json"), "PNJ")
    vre = qualify(source("vre_h1_positioned_tokens.json"), "VRE")
    get = lambda q: {f["canonical_metric"]: f for f in q["qualified_facts"]}
    p, v = get(pnj)["provision_charge_or_reversal_adjustment"], get(vre)["provision_charge_or_reversal_adjustment"]
    assert (p["value"], p["source_lineage"]["line_code"], p["statement_family"]) == (2667248523366, "03", "cash_flow")
    assert (v["value"], v["unit_scale"]) == (-7066000000, 1000000)
    # Damaged OCF digits stay blocked; no glyph repair is attempted.
    assert any(b["canonical_metric"] == "operating_cash_flow" and b["reason"] == "OCR_NUMERIC_AMBIGUITY"
               for b in pnj["blocked_candidates"])


def _row(**over):
    row = {"canonical_metric": "provision_charge_or_reversal_adjustment", "context_kind": "EARNINGS_QUALITY_COMPONENT",
           "component_contract": EARNINGS_COMPONENT_CONTRACT, "ingress_contract": CONTRACT_VERSION,
           "projection_currency_policy": "VND_EXISTING_CONTRACT", "currency": "VND", "period_type": "interim",
           "statement_family": "cash_flow", "line_code": "03", "citation_id": "c",
           "reported_component_evidence": {"citation_id": "c", "literal_label": "Các khoản dự phòng"}}
    return row | over


@pytest.mark.parametrize("over,ok", [({}, True), ({"line_code": "21"}, False), ({"statement_family": "income_statement"}, False),
    ({"currency": "USD"}, False), ({"period_type": "annual"}, False),
    ({"reported_component_evidence": {"citation_id": "c", "literal_label": "Khấu hao"}}, False),
    ({"canonical_metric": "investment_property_disposal_result"}, False)])
def test_component_admission_binds_metric_family_code_and_label(over, ok):
    assert earnings_component_is_admitted(_row(**over)) is ok


def test_foreign_currency_component_is_refused_at_ingress():
    fact = {"issuer_identity": "PVD", "canonical_metric": "provision_charge_or_reversal_adjustment", "currency": "USD",
            "statement_family": "cash_flow", "reporting_period": "2026-H1", "value": -3397931,
            "source_lineage": {"document_sha256": "d", "citation_id": "c", "line_code": "03",
                               "row_object": {"reconstructed_label": "Các khoản dự phòng"}}}
    rows, blocked = overlay_rows_from_panel_facts([fact])
    assert rows == [] and "FOREIGN_CURRENCY_METRIC_NOT_ADMITTED" in blocked[0]["reasons"]


def test_pnj_review_emphasis_is_retained_literally_without_interpretation():
    m = source("pnj_h1_positioned_tokens.json")
    front = {"pages": [p for p in m["pages"] if p["page_number"] == 6]}
    [evidence] = emphasis_of_matter_evidence(front)
    assert evidence["page_number"] == 6 and "39" in evidence["literal_ocr_text"].split()
    assert evidence["interpretation"] == "NONE_RECURRENCE_AND_FINANCIAL_EFFECT_NOT_INFERRED"
    assert emphasis_of_matter_evidence({"pages": [p for p in m["pages"] if p["page_number"] == 11]}) == []


def test_later_known_components_respect_completed_session_cutoff():
    import market_wide_current_fundamental_research as fundamental
    from market_wide_current_valuation_input_scaleout import _financial_input
    from tests.test_current_official_evidence_projection import ROOT, baseline
    rows = [json.loads(line) for line in (ROOT / "derived/financial-evidence-currency-refresh-v1/qualified_official_facts.jsonl")
            .read_text(encoding="utf8").splitlines()]
    new = [r for r in rows if r["canonical_metric"] == "provision_charge_or_reversal_adjustment"]
    assert {(r["ticker"], r["normalized_value"]) for r in new} == {("PNJ", 2667248523366), ("VRE", -7066000000)}
    assert all(r["knowledge_available_at"] >= "2026-10-08" for r in new)
    completed = fundamental.project_session(baseline=baseline(), official_rows=rows, session="2026-10-07",
                                            cutoff="2026-10-07T15:00:00+07:00")
    assert completed["records"]["PNJ"]["earnings_quality_context"]["status"] == "UNKNOWN"
    assert not any(f["canonical_metric"] == "provision_charge_or_reversal_adjustment"
                   for record in completed["records"].values() for f in record["official_field_context"])
    later = fundamental.project_session(baseline=baseline(), official_rows=rows, session="2026-10-08",
                                        cutoff="2026-10-08T15:00:00+07:00")
    quality = later["records"]["PNJ"]["earnings_quality_context"]
    assert quality["status"] == "NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE"
    assert quality["reason"] == "EXPLICIT_REPORTED_PROVISION_CHARGE_OR_REVERSAL_ADJUSTMENT"
    assert quality["recurrence_assessment"] == "UNKNOWN" and quality["normalized_eps"] is None
    assert _financial_input(later["records"]["PNJ"], later)["earnings_quality_context"] == quality
    vre = {f["canonical_metric"]: f for f in later["records"]["VRE"]["official_field_context"]}
    assert vre["shareholders_equity"]["normalized_value"] == 49310673000000
    assert vre["operating_cash_flow"]["temporal_status"] == "CURRENT_OFFICIAL_FACT"
