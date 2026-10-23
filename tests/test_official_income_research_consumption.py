"""Non-voting source-to-card contracts and portable real-session acceptance."""
import copy
import json
from collections import Counter
from pathlib import Path

import pytest

import ai_research_session_delivery as delivery
from stocklookup_core.financial.fundamental_signal_consumption_contract import (
    official_income_research_context, research_evidence_basis,
)

FIXTURE = Path(__file__).parent / "fixtures/official_income_research_actual_sessions_v1.json"
CUTOFF = "2026-10-22T15:00:00+07:00"


def fact(year, value, **overrides):
    return dict(ticker="SYN", canonical_metric="net_income", line_code="60",
        normalized_value=value, unit_scale=1, source_unit_scale=1000000,
        already_normalized=True, currency="VND", statement_family="income_statement",
        statement_scope="consolidated", reporting_period=str(year), period_type="annual",
        period_start=f"{year}-01-01", period_end=f"{year}-12-31",
        qualification_state="QUALIFIED", factual_status="qualified",
        audit_or_review_status="audited", document_sha256=str(year) * 16,
        citation_id=f"citation:{year}", source_identity=f"official:{year}",
        knowledge_available_at="2026-04-01T10:00:00+07:00") | overrides


def project(rows, **kwargs):
    return official_income_research_context(
        {"entity_class": "corporate", "official_field_context": rows},
        cutoff=CUTOFF, ticker="SYN", **kwargs)


def test_qualified_pair_measures_reported_change_without_a_vote_or_valuation_upgrade():
    rows = [fact(2024, 100), fact(2025, 120)]
    saved = copy.deepcopy(rows)
    result = project(rows)
    pair, = result["comparisons"]
    assert (pair["change"], pair["growth_ratio"], pair["direction"]) == (20, .2, "INCREASED")
    assert pair["prior_period"] == "2024" and pair["current_period"] == "2025"
    assert pair["current_citation_id"] == "citation:2025"
    assert pair["assurance"] == "audited" and "RECURRENCE_UNKNOWN" in pair["limitations"]
    assert result["vote_effect"] == result["strict_valuation_effect"] == "NONE"
    assert result["is_actionable"] is False
    assert result["facts"][0]["research_freshness"]["rewritten_as_current"] is False
    assert result["facts"][0]["research_freshness"]["freshness_status"] == "STALE_BUT_RESEARCH_USABLE"
    assert rows == saved


@pytest.mark.parametrize("changes", [
    {"canonical_metric": "attributable_net_income"}, {"line_code": "61"},
    {"accounting_definition": "profit_attributable_to_parent"},
    {"statement_scope": "standalone"}, {"currency": "USD"},
    {"audit_or_review_status": "reviewed"},
    {"period_start": "2025-04-01", "period_type": "interim", "reporting_period": "2025-9M"},
    {"period_start": "2025-01-01", "period_end": "2025-06-30", "period_type": "interim", "reporting_period": "2025-H1"},
    {"period_end": "2025-06-30"},  # annual label with half-year duration
    {"knowledge_available_at": "2026-10-22T15:00:01+07:00"},
    {"knowledge_available_at": "2026-10-22"},
    {"ticker": "OTHER"}, {"qualification_state": "CANDIDATE"},
    {"audit_or_review_status": "unreviewed"}, {"existing_consumer_usable": False},
    {"evidence_tier": "UNREVIEWED_QUARTERLY"}, {"unit_scale": 1000000}, {"unit_scale": True},
    {"period_type": None}, {"reporting_period": None}, {"normalized_value": float("nan")},
])
def test_incompatible_or_unqualified_inputs_never_produce_direction(changes):
    result = project([fact(2024, 100), fact(2025, 120, **changes)])
    assert result["comparisons"] == []
    assert result["direction_status"] == "UNKNOWN" and result["rejected"]


@pytest.mark.parametrize("entity", ["bank", "securities", "finance_company", "insurance", None])
def test_no_cross_entity_industrial_metrics(entity):
    result = official_income_research_context({"entity_class": entity,
        "official_field_context": [fact(2024, 1), fact(2025, 2)]}, cutoff=CUTOFF, ticker="SYN")
    assert not result["facts"] and not result["comparisons"]
    assert all("INDUSTRIAL_INCOME_IDENTITY_NOT_ADMITTED_FOR_ENTITY" in r["reason_codes"] for r in result["rejected"])


def test_half_year_bounds_and_loss_transition_are_not_annualized():
    rows = [fact(y, v, reporting_period=f"{y}-H1", period_type="interim", period_end=f"{y}-06-30",
                 cumulative_state="cumulative", audit_or_review_status="reviewed")
            for y, v in [(2025, -10), (2026, 5)]]
    result = project(rows)
    pair, = result["comparisons"]
    assert pair["semantic_transition"] == "LOSS_TO_PROFIT"
    assert pair["growth_ratio"] is None and pair["change"] == 15
    assert result["facts"][1]["reporting_period_basis"]["period_family"] == "HALF_YEAR"
    assert result["facts"][1]["research_freshness"]["financial_period_end"] == "2026-06-30"


def test_conflicting_values_and_missing_cutoff_fail_closed():
    rows = [fact(2024, 100), fact(2025, 120), fact(2025, 130, citation_id="conflict")]
    assert not project(rows)["comparisons"]
    result = official_income_research_context({"entity_class": "corporate", "official_field_context": rows}, cutoff=None)
    assert not result["facts"] and not result["comparisons"]


@pytest.mark.parametrize("day", ["2026-10-20", "2026-10-22"])
def test_real_session_evidence_basis_and_all_retained_decision_fields_are_preserved(day):
    session = json.loads(FIXTURE.read_bytes())["sessions"][day]
    counts, facts = Counter(), 0
    retained_pairs = 0
    for ticker, row in session["rows"].items():
        saved = copy.deepcopy(row)
        decision, fundamental = row["integrated"], row["fundamental"]
        before = delivery.project_integrated_decision_for_ai_delivery(decision, source_session=day)
        enriched = delivery.financial_research_card({"ticker": ticker,
            "fundamental_context": row["original_card_fundamental"]}, fundamental, decision,
            cutoff=session["cutoff"])
        context = enriched["fundamental_research_context"]
        basis = context["composite"]["evidence_basis"]
        counts[basis["scope"]] += 1
        if basis["scope"] == "BALANCE_SHEET_ONLY" and context["composite"]["financial_composite_state"] != "INSUFFICIENT_EVIDENCE":
            counts["sufficient_balance_only"] += 1
        income = context["official_income"]
        facts += len(income["facts"])
        retained_pairs += len(income["retained_qualified_income_comparisons"])
        assert income["comparisons"] == []  # new exact-field stream has no compatible pair
        assert income["direction_status"] == "UNKNOWN"
        assert income["existing_income_research"]["metrics"] == fundamental["metrics"]
        assert enriched["fundamental_context"] == row["original_card_fundamental"]
        assert context["composite"] | {"evidence_basis": None} == decision["financial_composite_context"] | {"evidence_basis": None}
        after = delivery.project_integrated_decision_for_ai_delivery(decision, source_session=day)
        assert before == after and row == saved
        assert basis["vote_ids"] == sorted(set(
            decision["evidence_axes"]["FUNDAMENTAL"]["context"].get("favorable_votes", []) +
            decision["evidence_axes"]["FUNDAMENTAL"]["context"].get("adverse_votes", [])))
    assert dict(counts) == session["expected_counts"]
    assert facts == session["expected_fact_count"] == 11
    assert retained_pairs == 9
    if day == "2026-10-22":
        assert counts["sufficient_balance_only"] == 51 and len(session["rows"]) == 72
    else:
        # Existing qualified FY comparisons survive; absence in the new stream is not a downgrade.
        assert session["rows"]["HPG"]["fundamental"]["metrics"][2]["value"] == .7675496
        assert "PROFITABILITY.LEVEL" in session["rows"]["HPG"]["integrated"]["evidence_axes"]["FUNDAMENTAL"]["context"]["favorable_votes"]


def test_full_delivery_primary_cockpit_and_companion_carry_same_non_voting_context():
    from test_ai_research_session_delivery import _operation, _integrated_delivery_fixture
    operation, integrated = _operation(), _integrated_delivery_fixture(session="2026-10-22")
    operation["manifest"]["market_session"] = "2026-10-22"
    integrated["records"]["AAA"]["evidence_axes"]["FUNDAMENTAL"] = {"context": {
        "synthesis_contract": "fundamental_signal_consumption/v1",
        "favorable_votes": ["CAPITAL_STRUCTURE.DIRECTION"], "adverse_votes": []}}
    inputs = {"descriptive": {"records": {"AAA": {}}}, "fundamental": {
        "session_cutoff": CUTOFF, "records": {"AAA": {"entity_class": "corporate",
            "official_field_context": [fact(2024,100,ticker="AAA"), fact(2025,120,ticker="AAA")]}}},
        "integrated_investment_decision_product": integrated}
    saved = copy.deepcopy((operation, inputs))
    output = delivery.build_delivery(operation, inputs)
    primary = json.loads(output["primary"])["ticker_research_contexts"]["AAA"]
    cockpit = json.loads(output["projection"])["ticker_cards"]["AAA"]
    companion = json.loads(output["full_universe"])
    for card in [primary, cockpit, companion]:
        ctx = card["fundamental_research_context"]
        assert ctx["composite"]["evidence_basis"]["scope"] == "BALANCE_SHEET_ONLY"
        assert ctx["official_income"]["comparisons"][0]["growth_ratio"] == .2
    decision_card = json.loads(output["projection"])["decision_card_v1"]["AAA"]
    assert decision_card["fundamental"]["official_income_research_context"] == primary["fundamental_research_context"]["official_income"]
    assert (operation, inputs) == saved


def test_product_summary_preserves_source_owned_context():
    from stocklookup_core.decision.current_daily_decision_research_product import _fundamental_summary
    row = {"official_income_research_context": project([fact(2025, 1)])}
    assert _fundamental_summary(row)["official_income_research_context"] == row["official_income_research_context"]


def test_actual_source_qualification_to_product_summary_boundary():
    from tests.test_current_official_evidence_projection import baseline
    from tests.test_official_financial_source_integrity import _retained_rows
    from market_wide_current_fundamental_research import project_session, content_identity
    from stocklookup_core.decision.current_daily_decision_research_product import _fundamental_summary
    prior = baseline()
    for record in prior["records"].values():
        record["entity_class"] = "corporate"
    prior.update(content_identity(prior))
    projected = project_session(baseline=prior, official_rows=_retained_rows(),
        session="2026-10-08", cutoff="2026-10-08T15:00:00+07:00")
    count = 0
    for ticker, record in projected["records"].items():
        source_context = record["official_income_research_context"]
        count += len(source_context["facts"])
        assert _fundamental_summary(record)["official_income_research_context"] == source_context
        assert all(f["ticker"] == ticker for f in source_context["facts"])
    assert count > 0
