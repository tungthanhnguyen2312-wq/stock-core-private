"""Reported-period valuation integration; synthetic evidence never counts as market coverage."""
from copy import deepcopy

import pytest

from tests.financial_source_fixture import synthetic_retained_source_io  # noqa: F401
from tests.test_financial_evidence_currency_refresh import _fact
from stocklookup_core.valuation import current_research_valuation_context as valuation
from stocklookup_core.valuation.market_wide_current_valuation_input_scaleout import _price_input

# This selected suite owns the intake-to-valuation boundary. New candidate tests
# run in hosted focused CI without changing workflow dispatch or frozen pins.
from tests.test_official_financial_quarterly_intake import (
    test_quarter_and_cumulative_values_are_candidates_not_official_facts,
    test_existing_q3_source_gate_is_unchanged,
    test_column_period_never_invents_covered_dates,
    test_quarter_vs_nine_months_ambiguous_header_is_not_a_column,
    test_total_parent_and_separate_profits_never_alias,
    test_cash_flow_negative_and_nine_months_not_q3,
    test_equity_including_nci_and_lease_debt_stay_distinct,
    test_semantic_adversaries,
    test_hash_page_and_exact_citation_fail_closed,
    test_knowledge_and_publication_are_independent,
    test_reviewed_integer_without_original_lexeme_is_honestly_labeled,
    test_unreviewed_never_becomes_reviewed_from_pdf_creation_metadata,
    test_eps_shares_and_numerator_never_become_current_shares_or_parent_profit,
    test_reclassified_comparative_state_is_preserved_not_inferred,
    test_quarter_and_scope_conflicts_use_existing_conflict_owner,
    test_source_candidate_is_blocked_by_existing_common_admission,
    test_real_candidate_cannot_enable_existing_reported_period_ratios,
    test_document_class_cannot_make_unreviewed_rows_reviewed_or_news_financial,
    test_composite_depreciation_and_capital_amount_do_not_become_ebitda_or_shares,
)


def raw():
    price = _price_input({"disposition": "EXACT_SESSION_RETAINED", "observations": [
        {"session": "2026-10-12", "close": 1, "provider": "DNSE"}]},
        {"resolved_completed_session": "2026-10-12", "source": "DNSE"})
    return {"entity_class": "corporate", "price_input": price,
        "share_basis_input": {"value": 20_000, "share_concept": "ISSUED_SHARES",
            "retained_evidence": {"unit": "shares"},
            "authority": "provider_reported_lagged", "research_proxy_eligible": True,
            "authoritative_current_market_cap_eligible": False},
        "metrics": {"market_cap": {"status": "RESEARCH_USABLE", "value": 20_000_000}}}


def fact(metric, value=1_000_000, **changes):
    return _fact("PNJ", metric, "2026-H1", value,
        statement_family="balance_sheet" if metric == "shareholders_equity" else "income_statement",
        temporal_nature="instant" if metric == "shareholders_equity" else "duration",
        already_normalized=True, **changes)


def evaluate(facts, record=None, **kwargs):
    return valuation.evaluate_ticker_valuation(ticker="PNJ", feature_record=None,
        valuation_record=raw() if record is None else record, decision_session="2026-10-12",
        official_financial_facts=facts, **kwargs)


def test_source_to_three_distinct_reported_period_methods_and_no_input_mutation():
    facts = [fact("net_income"), fact("revenue", 2_000_000), fact("shareholders_equity", 4_000_000)]
    snapshot = deepcopy(facts)
    before = evaluate([])
    after = evaluate(facts)
    for method, expected in [(valuation.PE_REPORTED_PERIOD, 20), (valuation.PS_REPORTED_PERIOD, 10),
                             (valuation.PB_OFFICIAL_RESEARCH, 5)]:
        result = after["methods"][method]
        assert result["status"] == "RESEARCH_USABLE"
        assert result["value"] == pytest.approx(expected)
        assert result["period_basis"] == "2026-H1"
        assert result["source_fact"]["document_sha256"]
        assert result["source_fact"]["citation_id"]
        assert result["share_basis"] == "CURRENT_SHARE_RESEARCH_PROXY"
        assert result["denominator_period_semantics"] == ("BALANCE_SHEET_INSTANT" if method == valuation.PB_OFFICIAL_RESEARCH
                                                        else "SINGLE_REPORTING_PERIOD_NOT_ANNUALIZED")
        assert not result["is_actionable"]
    assert all(after["methods"][k] == v for k, v in before["methods"].items())
    assert facts == snapshot
    assert after["authoritative_current_market_cap_eligible"] is False


@pytest.mark.parametrize("change", [
    {"already_normalized": False}, {"unit_scale": 1000}, {"normalized_value": None},
    {"value": 999}, {"statement_scope": "standalone"}, {"period_start": None},
    {"period_end": "2026-11-30"}, {"knowledge_available_at": "2026-10-13T00:00:00Z"},
    {"qualification_state": "DOCUMENT_METADATA_QUALIFIED"}, {"document_sha256": "a" * 64},
])
def test_source_scale_scope_bounds_cutoff_and_hash_fail_closed(change):
    row = fact("net_income")
    row.update(change)
    result = evaluate([row])["methods"][valuation.PE_REPORTED_PERIOD]
    assert result["status"] == valuation.INPUT_BLOCKED and result["value"] is None
    assert result["denominator_authority"] == "UNAVAILABLE"


def test_true_conflict_is_order_independent_and_future_revision_is_excluded():
    a, b = fact("net_income"), fact("net_income", 2_000_000)
    left = evaluate([a, b])["methods"][valuation.PE_REPORTED_PERIOD]
    right = evaluate([b, a])["methods"][valuation.PE_REPORTED_PERIOD]
    assert left == right
    assert left["blocker_reason_codes"] == ["OFFICIAL_REPORTED_PERIOD_CONFLICT"]
    b["knowledge_available_at"] = "2026-10-13T00:00:00Z"
    assert evaluate([a, b])["methods"][valuation.PE_REPORTED_PERIOD]["value"] == 20


@pytest.mark.parametrize("value", [0, -1_000_000])
def test_non_positive_denominator_is_not_a_usable_multiple(value):
    result = evaluate([fact("net_income", value)])["methods"][valuation.PE_REPORTED_PERIOD]
    assert result["status"] == valuation.INPUT_BLOCKED and result["value"] is None


def test_proxy_denominator_cannot_override_stale_shares_or_price_session():
    record = raw()
    record["share_basis_input"]["research_proxy_eligible"] = False
    assert evaluate([fact("net_income")], record)["methods"][valuation.PE_REPORTED_PERIOD]["value"] is None
    record = raw()
    record["price_input"]["session"] = "2026-10-09"
    assert evaluate([fact("net_income")], record)["methods"][valuation.PE_REPORTED_PERIOD]["value"] is None


def test_bank_never_consumes_corporate_income_identity_or_industrial_sales():
    record = raw()
    record["entity_class"] = "bank"
    result = evaluate([fact("net_income"), fact("revenue")], record)
    assert result["methods"][valuation.PS_REPORTED_PERIOD]["status"] == valuation.NOT_APPLICABLE
    assert result["methods"][valuation.PE_REPORTED_PERIOD]["value"] is None


def test_decision_fitness_retains_method_and_duration_limitations():
    from stocklookup_core.decision.current_research_decision_input import _valuation
    result = evaluate([fact("net_income")])
    dimension = _valuation({"valuation_methods": result["methods"]}, result,
                          {"applicability_status": "RESOLVED", "entity_class": "corporate"})
    assert valuation.PE_REPORTED_PERIOD in dimension["usable_methods"]
    assert dimension["usable_method_period_basis"][valuation.PE_REPORTED_PERIOD] == "2026-H1"
    assert "SINGLE_REPORTING_PERIOD_DENOMINATOR_NOT_TTM" in dimension["limitations"]
    assert dimension["authority"] == "RESEARCH_PROXY"
    assert result["usable_relative_method_count"] == 1


@pytest.mark.parametrize("source_scale", [1, 1000, 1_000_000])
def test_source_display_scale_is_not_applied_twice(source_scale):
    from tests.financial_source_fixture import bind_fixture_source
    row = fact("net_income", source_unit_scale=source_scale, parsed_numeric_value=1_000_000 // source_scale)
    row, _ = bind_fixture_source(row)
    result = evaluate([row])["methods"][valuation.PE_REPORTED_PERIOD]
    assert result["value"] == 20
    assert result["source_fact"]["source_unit_scale"] == source_scale


def test_existing_axis_preserves_numerical_provenance_and_no_fake_ttm():
    row = valuation.attach_peer_relative({"PNJ": evaluate([fact("net_income")])})["PNJ"]
    axis = valuation.valuation_axis(ticker="PNJ", decision_session="2026-10-12",
        valuation_artifact={"valuation_session": "2026-10-12"}, feature_store=None, row=row,
        freshness={"freshness_status": "CURRENT"})
    method = axis["applicable_methods"][valuation.PE_REPORTED_PERIOD]
    assert method["value"] == 20
    assert method["source_fact"]["document_sha256"]
    assert method["reporting_basis"]["duration_days"] == 181
    assert method["numerator_share_basis_input"]["share_concept"] == "ISSUED_SHARES"
    assert method["ttm_periods"] is None
    assert method["peer_relative"]["status"] == "INSUFFICIENT_PEER_COUNT"


def test_existing_materializer_accepts_explicit_official_input_and_packet_schema():
    from canonical_daily_financial_v2_materialization import build_evaluated_valuation_artifact
    facts = [fact("net_income")]
    artifact = build_evaluated_valuation_artifact(engine_artifact={"records": {}},
        raw_valuation_artifact={"records": {"PNJ": raw()}}, product_tickers=["PNJ"],
        requested_at="2026-10-12T15:00:00+07:00", decision_session="2026-10-12",
        official_financial_facts=facts)
    assert artifact["records"]["PNJ"]["methods"][valuation.PE_REPORTED_PERIOD]["value"] == 20


def test_existing_workspace_and_ai_packet_retain_original_trace_and_proxy_boundary():
    from stocklookup_core.decision.investment_decision_workspace_projection import _valuation_view
    from stocklookup_core.decision.current_research_ai_handoff_packet import build_card
    row = valuation.attach_peer_relative({"PNJ": evaluate([fact("net_income")])})["PNJ"]
    axis = valuation.valuation_axis(ticker="PNJ", decision_session="2026-10-12",
        valuation_artifact={"valuation_session": "2026-10-12"}, feature_store=None, row=row,
        freshness={"freshness_status": "CURRENT"})
    workspace_valuation = _valuation_view({"valuation": axis})
    card = build_card(ticker="PNJ", session="2026-10-12",
        workspace_card={"valuation": workspace_valuation}, screener_card=None,
        current_research_scope=None, workspace_identity="synthetic-workspace", screener_identity=None)
    delivered = card["valuation"]["method_diagnostics"][valuation.PE_REPORTED_PERIOD]
    assert delivered["value"] == 20
    assert delivered["source_fact"]["document_sha256"] == row["methods"][valuation.PE_REPORTED_PERIOD]["source_fact"]["document_sha256"]
    assert delivered["numerator_share_basis_input"]["share_concept"] == "ISSUED_SHARES"
    assert delivered["reporting_basis"]["duration_days"] == 181
    assert "NOT_AUTHORITATIVE" in delivered["limitations"]
    assert not card["valuation"]["supporting_methods"]
