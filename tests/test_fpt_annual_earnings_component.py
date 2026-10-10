"""Audited FPT FY2025 provision is historical component context, not current earnings."""
import json
from copy import deepcopy
from pathlib import Path

from ai_research_session_delivery import _compact_context
from current_research_decision_packet import _valuation
from stocklookup_core.valuation.market_wide_current_valuation_input_scaleout import _financial_input
from official_financial_assurance_evidence import resolve_document_assurance_evidence
from official_financial_ocr_table_evidence import (
    qualify_table_facts, resolve_scoped_statement_scope_evidence, resolve_scoped_unit_evidence,
)
from official_financial_ocr_table_evidence import panel_facts_from_qualified_ocr
from reviewed_interim_canonical_ingress import earnings_component_is_admitted, overlay_rows_from_panel_facts
from tests.test_current_official_evidence_projection import baseline
import market_wide_current_fundamental_research as fundamental

FIXTURE = Path(__file__).parent / "fixtures/fpt_official_evidence"
ROOT = Path(__file__).resolve().parents[1]


def _cash_flow():
    return json.loads((FIXTURE / "cash_flow_page_13.json").read_text(encoding="utf-8"))


def _assurance():
    annual = json.loads((FIXTURE / "annual_positioned_tokens.json").read_text(encoding="utf-8"))
    annual["pages"] = [page for page in annual["pages"] if page["page_number"] in {6, 7}]
    evidence = resolve_document_assurance_evidence(annual)
    assert evidence["state"] == "QUALIFIED" and evidence["audit_or_review_status"] == "audited"
    return evidence


def test_retained_fpt_page_qualifies_only_the_literal_provision_amount():
    page = _cash_flow()
    qualified = qualify_table_facts(
        page, ticker="FPT", reporting_period="2025", include_earnings_quality_components=True,
        scoped_unit_evidence=resolve_scoped_unit_evidence(page),
        scoped_statement_scope_evidence=resolve_scoped_statement_scope_evidence(page),
    )
    fact = next(item for item in qualified["qualified_facts"]
                if item["canonical_metric"] == "provision_charge_or_reversal_adjustment")
    assert fact["value"] == 651406282654 and fact["currency"] == "VND" and fact["unit_scale"] == 1
    assert fact["source_lineage"]["line_code"] == "03"
    assert fact["source_lineage"]["row_object"]["reconstructed_label"] == "Provisions"
    assert fact["source_lineage"]["ocr_derived_text_evidence"]["current_raw"] == "651,406,282,654"
    assert fact["statement_family"] == "cash_flow"
    panel = panel_facts_from_qualified_ocr(
        qualified, entity_type="corporate", statement_scope="consolidated",
        audit_or_review_status="audited", assurance_evidence=_assurance(),
        knowledge_available_at="2026-10-08T06:00:00+00:00", observed_at="2026-10-08T02:00:00+00:00",
    )
    rows, blocked = overlay_rows_from_panel_facts(panel, allow_audited_annual_context=True)
    row = next(item for item in rows if item["canonical_metric"] == "provision_charge_or_reversal_adjustment")
    assert not any(item["key"]["metric"] == "provision_charge_or_reversal_adjustment" for item in blocked)
    assert row["reporting_period"] == "2025" and row["period_type"] == "annual"
    assert row["component_semantic_type"] == "PROVISION_COMPONENT_REPORTED"
    assert row["recurrence_assessment"] == "UNKNOWN" and row["normalized_eps"] is None
    assert row["component_direction"] == "REPORTED_POSITIVE"
    assert earnings_component_is_admitted(row)
    assert "NOT_CURRENT_INTERIM_EVIDENCE" in row["research_use_restrictions"]


def test_annual_component_reaches_packet_without_changing_current_or_valuation_fields():
    rows = [json.loads(line) for line in (ROOT / "derived/financial-evidence-currency-refresh-v1/qualified_official_facts.jsonl").read_text(encoding="utf-8").splitlines()]
    component = next(row for row in rows if row["ticker"] == "FPT" and row["canonical_metric"] == "provision_charge_or_reversal_adjustment")
    assert component["period_type"] == "annual" and component["reporting_period"] == "2025"
    assert component["normalized_value"] == 651406282654
    assert component["knowledge_available_at"] >= "2026-10-08"
    base = baseline()
    base["records"]["FPT"] = {"authority_tier": "OFFICIAL_QUALIFIED", "authoritative_periods_available": ["2024"],
                              "metrics": [{"metric_id": "net_margin", "status": "EXACT_QUALIFIED", "periods_used": ["2024"], "value": 0.2}]}
    base.update(fundamental.content_identity(base))
    before = deepcopy(base)
    october7 = fundamental.project_session(baseline=base, official_rows=rows, session="2026-10-07", cutoff="2026-10-07T15:00:00+07:00")
    assert october7["records"]["FPT"]["metrics"] == before["records"]["FPT"]["metrics"]
    assert october7["records"]["FPT"]["earnings_quality_context"]["status"] == "UNKNOWN"
    assert "historical_earnings_quality_context" not in october7["records"]["FPT"]
    assert not any(field["canonical_metric"] == "provision_charge_or_reversal_adjustment"
                   for field in october7["records"]["FPT"]["official_field_context"])
    later = fundamental.project_session(baseline=base, official_rows=rows, session="2026-10-08", cutoff="2026-10-08T15:00:00+07:00")
    assert later["records"]["FPT"]["metrics"] == before["records"]["FPT"]["metrics"]
    assert later["records"]["FPT"]["earnings_quality_context"]["status"] == "UNKNOWN"
    historical = later["records"]["FPT"]["historical_earnings_quality_context"]
    assert historical["status"] == "NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE"
    assert historical["recurrence_assessment"] == "UNKNOWN" and historical["normalized_eps"] is None
    assert historical["periods"] == [{"reporting_period": "2025", "period_type": "annual", "period_label": "FY2025"}]
    assert historical["current_interim_evidence"] is False and historical["valuation_effect"] == "NONE"
    assert historical["component_semantic_types"] == ["PROVISION_COMPONENT_REPORTED"]
    evidence = historical["component_evidence"][0]
    assert evidence["temporal_status"] == "HISTORICAL_OFFICIAL_FACT"
    assert evidence["valuation_use"] == "NOT_PERMITTED_EARNINGS_COMPONENT_CONTEXT"
    assert evidence["research_status"] == "partial"
    assert "EARNINGS_COMPONENT_DOES_NOT_NORMALIZE_EARNINGS" in evidence["research_reason_codes"]
    assert not any(field["temporal_status"] == "CURRENT_OFFICIAL_FACT" for field in later["records"]["FPT"]["official_field_context"])
    without = [row for row in rows if row is not component]
    same_day = fundamental.project_session(baseline=base, official_rows=without, session="2026-10-08", cutoff="2026-10-08T15:00:00+07:00")
    assert later["official_projection"]["current_official_field_count"] == same_day["official_projection"]["current_official_field_count"]
    assert later["official_projection"]["historical_official_overlay_field_count"] == same_day["official_projection"]["historical_official_overlay_field_count"] + 1
    assert october7["official_projection"]["current_official_field_count"] == 9
    financial = _financial_input(later["records"]["FPT"], later)
    assert financial["historical_earnings_quality_context"]["periods"][0]["period_label"] == "FY2025"
    packet = _valuation({"financial_input": financial, "metrics": {"P/E": {"status": "BLOCKED", "value": None}}, "price_input": {}, "share_basis_input": {}})
    assert packet["metrics"]["P/E"]["status"] == "BLOCKED" and "value" not in packet["metrics"]["P/E"]
    assert packet["historical_earnings_quality_context"]["periods"][0]["reporting_period"] == "2025"
    delivered = _compact_context("FPT", {"product": {}}, {"fundamental": later})
    assert delivered["fundamental_context"]["historical_earnings_quality_context"]["periods"][0]["period_label"] == "FY2025"
    assert delivered["fundamental_context"]["historical_earnings_quality_context"]["normalized_eps"] is None
    assert delivered["fundamental_context"]["earnings_quality_context"]["status"] == "UNKNOWN"
