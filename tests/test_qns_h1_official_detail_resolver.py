"""QNS detail-page resolver: one consolidated PDF, no header repair, no new fact invention."""
import json
from pathlib import Path

import market_wide_current_fundamental_research as fundamental
from official_financial_ocr_table_evidence import row_label_supports_metric
from source_faithful_numeric_glyph_normalization import normalization_decision
import qns_h1_official_detail_resolver as resolver

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/triad_current_h1/qns_h1_positioned_tokens.json"
FACTS = ROOT / "derived/financial-evidence-currency-refresh-v1/qualified_official_facts.jsonl"
CONSOLIDATED = "https://www.qns.com.vn/upload/product/2026q2-bctc-hop-nhat-sau-kt-1786788334.pdf"
PAGE = """
<html><body>
<a href="/upload/product/vie-cbtt-1786788333.pdf">Công văn Công bố thông tin</a>
<a href="/upload/product/2026q2-bctc-hop-nhat-sau-kt-1786788334.pdf">Báo cáo tài chính hợp nhất bán niên năm 2026</a>
<a href="/upload/product/2026q2-bctc-tong-hop-sau-kt-1786788334.pdf">Báo cáo tài chính tổng hợp bán niên năm 2026</a>
<p>Doanh thu 1</p>
</body></html>
""".encode()


def test_budget_is_qns_only_and_forbids_another_discovery_layer():
    budget = resolver.declared_budget()
    assert budget["issuer"] == "QNS" and budget["detail_page_requests_max"] == 1
    assert budget["pdf_requests_max"] == 1 and budget["total_requests_including_redirects_retries_max"] == 5
    assert budget["index_refresh"] is False and budget["further_discovery_layers"] is False
    assert budget["pagination"] is False and budget["generic_search"] is False


def test_detail_page_selects_only_the_literal_consolidated_pdf():
    selected = resolver.select_statement(resolver.DETAIL_URL, PAGE)
    assert selected["state"] == "PDF_LOCATOR_ON_ADMITTED_QNS_HOST"
    assert selected["selected_locator"] == CONSOLIDATED
    assert selected["html_is_financial_evidence"] is False
    assert len(selected["pdf_anchors"]) == 3


def test_missing_consolidated_anchor_does_not_search_further():
    html = b'<a href="/upload/product/letter.pdf">Cong van</a>'
    selected = resolver.select_statement(resolver.DETAIL_URL, html)
    assert selected["state"] == "DETAIL_PAGE_HAS_NO_OFFICIAL_PDF"
    assert resolver.terminal_disposition(selected["state"], []) == "QNS_2026_H1_DETAIL_HAS_NO_PDF"


def test_unapproved_host_stops_for_an_owner_route_decision():
    html = ('<a href="https://files.example/statement.pdf">' + resolver.CONSOLIDATED_TITLE + "</a>").encode()
    selected = resolver.select_statement(resolver.DETAIL_URL, html)
    assert selected["state"] == "OWNER_ROUTE_DECISION_REQUIRED"
    assert resolver.terminal_disposition(selected["state"], []) == "QNS_2026_H1_ROUTE_BLOCKED"


def test_retained_ocr_keeps_equity_and_blocks_damaged_headers():
    materialization = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert resolver.classify_representation(materialization) == "OCR_REQUIRED"
    attempt = resolver.attempt_priority_facts(materialization)
    by_metric = {row["canonical_metric"]: row for row in attempt["facts"]}
    assert by_metric["shareholders_equity"]["state"] == "QUALIFIED"
    assert by_metric["shareholders_equity"]["value"] == 10647823148609
    for metric in ("revenue", "net_income", "attributable_net_income", "cash_and_equivalents",
                   "total_assets", "operating_cash_flow"):
        assert by_metric[metric]["state"] == "BLOCKED"
        assert by_metric[metric]["reason"] == "ROW_NOT_UNIQUE_OR_NOT_GEOMETRICALLY_RESOLVED"
    assert by_metric["long_term_borrowings_or_finance_leases"]["reason"] == "ROW_LABEL_DOES_NOT_SUPPORT_METRIC"
    assert by_metric["total_interest_bearing_debt"]["reason"] == "DEBT_COMPONENT_INCOMPLETE"
    assert attempt["earnings_components"] == []
    assert attempt["normalization"] == "SOURCE_FAITHFUL_NORMALIZATION_NOT_YET_PROVABLE"
    assert resolver.terminal_disposition("PDF_LOCATOR_ON_ADMITTED_QNS_HOST", ["shareholders_equity"]) == (
        "QNS_2026_H1_CURRENT_OFFICIAL_EVIDENCE_READY")


def test_label_and_superscript_guards_remain_closed():
    assert row_label_supports_metric("total_assets", "Tài sản dài hạn khác") is False
    decision = normalization_decision({
        "raw_token": "1,23\u00b2,456", "token_class": "NUMERIC_AMOUNT",
        "row_identity_qualified": True, "column_identity_qualified": True,
        "independent_confirmation": "NATIVE_PDF_TEXT_LAYER",
    })
    assert decision["state"] == "STILL_BLOCKED" and decision["normalized_token"] is None


def test_october7_excludes_qns_equity_and_prior_facts_remain():
    rows = [json.loads(line) for line in FACTS.read_text(encoding="utf-8").splitlines() if line.strip()]
    qns = next(row for row in rows if row["ticker"] == "QNS" and row["canonical_metric"] == "shareholders_equity")
    vnm = next(row for row in rows if row["ticker"] == "VNM" and row["canonical_metric"] == "cash_and_equivalents")
    fpt = next(row for row in rows if row["ticker"] == "FPT" and row["canonical_metric"] == "provision_charge_or_reversal_adjustment")
    assert vnm["normalized_value"] == 4535672366831 and vnm["knowledge_available_at"].startswith("2026-10-08")
    assert fpt["normalized_value"] == 651406282654 and fpt["reporting_period"] == "2025"
    assert qns["normalized_value"] == 10647823148609 and qns["knowledge_available_at"].startswith("2026-10-08")
    base = {"contract_version": fundamental.CONTRACT_VERSION, "records": {
        "QNS": {"authority_tier": "OFFICIAL_QUALIFIED", "authoritative_periods_available": ["2024"],
                "metrics": [{"metric_id": "net_margin", "status": "EXACT_QUALIFIED", "periods_used": ["2024"], "value": 0.1}]}}}
    base.update(fundamental.content_identity(base))
    october7 = fundamental.project_session(baseline=base, official_rows=[qns], session="2026-10-07", cutoff="2026-10-07T15:00:00+07:00")
    assert october7["records"]["QNS"]["official_field_context"] == []
    later = fundamental.project_session(baseline=base, official_rows=[qns], session="2026-10-08", cutoff="2026-10-08T15:00:00+07:00")
    assert later["records"]["QNS"]["official_field_context"][0]["canonical_metric"] == "shareholders_equity"
    assert later["records"]["QNS"]["metrics"] == base["records"]["QNS"]["metrics"]
    assert later["records"]["QNS"]["earnings_quality_context"]["status"] == "UNKNOWN"
    from ai_research_session_delivery import _compact_context
    import current_research_decision_packet as packet
    from market_wide_current_valuation_input_scaleout import _financial_input
    financial = _financial_input(later["records"]["QNS"], later)
    assert financial["official_field_context"][0]["normalized_value"] == 10647823148609
    assert financial["interim_context_does_not_supply_annual_valuation_inputs"] is True
    delivered_packet = packet._valuation({"financial_input": financial, "metrics": {"P/E": {"status": "BLOCKED"}}, "price_input": {}, "share_basis_input": {}})
    assert delivered_packet["official_field_context"][0]["canonical_metric"] == "shareholders_equity"
    assert "value" not in delivered_packet["metrics"]["P/E"]
    delivered = _compact_context("QNS", {"product": {}}, {"fundamental": later})
    assert delivered["fundamental_context"]["official_field_context"][0]["reporting_period"] == "2026-H1"
