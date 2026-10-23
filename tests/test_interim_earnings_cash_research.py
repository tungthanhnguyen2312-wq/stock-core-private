"""Non-voting reviewed interim earnings and cash research: semantics, gates, preview and real sessions."""
import copy
import json
from pathlib import Path

import pytest

import ai_research_session_delivery as delivery
from stocklookup_core.financial.interim_earnings_cash_research import (
    GATES_PATH, interim_earnings_cash_research_context, load_issuer_gates,
)

FIXTURES = Path(__file__).parent / "fixtures"
SESSIONS = FIXTURES / "official_income_research_actual_sessions_v1.json"
PREVIEW = FIXTURES / "interim_earnings_cash_candidate_preview_v1.json"
CUTOFF = "2026-10-22T15:00:00+07:00"
FAMILY = {"revenue": "income_statement", "net_income": "income_statement", "attributable_net_income": "income_statement",
          "investment_property_disposal_result": "income_statement", "operating_cash_flow": "cash_flow",
          "provision_charge_or_reversal_adjustment": "cash_flow", "cash_and_equivalents": "balance_sheet"}
LINE = {"revenue": "10", "net_income": "60", "attributable_net_income": "61", "operating_cash_flow": "20",
        "investment_property_disposal_result": "21", "provision_charge_or_reversal_adjustment": "03",
        "cash_and_equivalents": "110"}
NO_GATES = {"issuers": {}}


def fact(metric, value, year=2026, doc="d" * 64, **overrides):
    return dict(ticker="SYN", canonical_metric=metric, line_code=LINE[metric], normalized_value=value,
        unit_scale=1, already_normalized=True, currency="VND", statement_family=FAMILY[metric],
        statement_scope="consolidated", reporting_period=f"{year}-H1", period_type="interim",
        period_start=f"{year}-01-01", period_end=f"{year}-06-30", qualification_state="QUALIFIED",
        factual_status="qualified", audit_or_review_status="reviewed", document_sha256=doc,
        citation_id=f"{metric}:{year}:{doc[:4]}:{overrides.get('comparative_basis')}", source_identity="official:" + doc,
        knowledge_available_at="2026-09-01T10:00:00+07:00",
        temporal_status="CURRENT_OFFICIAL_FACT" if year == 2026 else "HISTORICAL_OFFICIAL_FACT") | overrides


def run(rows, gates=NO_GATES, entity="corporate", cutoff=CUTOFF, ticker="SYN"):
    return interim_earnings_cash_research_context({"entity_class": entity, "official_field_context": rows},
                                                  cutoff=cutoff, ticker=ticker, gates=gates)


def gate(*cautions):
    return {"issuers": {"SYN": {"document": {"document_sha256": "d" * 64}, "qualification_blockers": [],
                                "comparability_cautions": list(cautions)}}}


@pytest.mark.parametrize("profit,cash,relationship,ratio", [
    (100, 120, "OPERATING_CASH_AT_OR_ABOVE_PROFIT", 1.2), (100, 40, "OPERATING_CASH_BELOW_PROFIT", .4),
    (100, -30, "POSITIVE_PROFIT_NEGATIVE_OPERATING_CASH", -.3), (-10, 50, "PROFIT_NON_POSITIVE_RATIO_NOT_MEANINGFUL", None),
])
def test_same_statement_set_cash_conversion_is_labelled_and_non_voting(profit, cash, relationship, ratio):
    rows = [fact("net_income", profit), fact("operating_cash_flow", cash)]
    saved = copy.deepcopy(rows)
    result = run(rows)
    measurement, = result["cash_conversion"]["measurements"]
    assert measurement["relationship"] == relationship and measurement["conversion_ratio"] == ratio
    assert measurement["operating_cash_minus_profit"] == cash - profit
    assert measurement["method"].startswith("operating_cash_flow_over_profit_after_tax_same_statement_set")
    assert {"SINGLE_PERIOD_IS_NOT_A_TREND", "NOT_FREE_CASH_FLOW"} <= set(measurement["limitations"])
    assert result["vote_effect"] == result["strict_valuation_effect"] == "NONE" and result["is_actionable"] is False
    assert result["economics_status"] == "MEASURED" and rows == saved


def test_parent_profit_conversion_names_the_minority_interest_mismatch():
    result = run([fact("attributable_net_income", 100), fact("operating_cash_flow", 50)])
    assert "PARENT_PROFIT_EXCLUDES_NON_CONTROLLING_INTERESTS_OPERATING_CASH_IS_GROUP_WIDE" in \
        result["cash_conversion"]["measurements"][0]["limitations"]


def test_cash_conversion_never_crosses_periods_or_documents():
    # PNJ shape: audited FY2025 operating cash flow, reviewed H1 2026 profit.
    rows = [fact("net_income", 100), fact("operating_cash_flow", 20, year=2025, reporting_period="2025",
            period_type="annual", period_start="2025-01-01", period_end="2025-12-31", audit_or_review_status="audited"),
            fact("operating_cash_flow", 90, doc="e" * 64)]
    result = run(rows)
    assert not result["cash_conversion"]["measurements"]
    codes = {code for b in result["cash_conversion"]["blockers"] for code in b["reason_codes"]}
    assert {"NO_SAME_STATEMENT_SET_OPERATING_CASH_FLOW", "OPERATING_CASH_FLOW_ONLY_FOR_OTHER_PERIODS",
            "NO_SAME_STATEMENT_SET_QUALIFIED_PROFIT"} <= codes
    assert result["economics_status"] == "PARTIAL_FACTS_NO_MEASUREMENT"


@pytest.mark.parametrize("changes", [
    {"audit_or_review_status": "unreviewed"}, {"evidence_tier": "UNREVIEWED_QUARTERLY"},
    {"existing_consumer_usable": False}, {"qualification_state": "CANDIDATE"}, {"factual_status": "candidate"},
    {"knowledge_available_at": "2026-10-22T15:00:01+07:00"}, {"unit_scale": 1000}, {"already_normalized": False},
    {"ticker": "OTHER"}, {"statement_family": "income_statement"}, {"comparative_basis": "ANALYST_ADJUSTED"},
    {"normalized_value": float("nan")}, {"period_end": None},
])
def test_unqualified_or_d1_cash_rows_never_measure(changes):
    result = run([fact("net_income", 100), fact("operating_cash_flow", 50, **changes)])
    assert not result["cash_conversion"]["measurements"] and result["rejected"]


@pytest.mark.parametrize("entity", ["bank", "securities", "insurance", "finance_company", None])
def test_financial_or_unresolved_entities_get_no_industrial_cash_interpretation(entity):
    result = run([fact("net_income", 100), fact("operating_cash_flow", -50)], entity=entity)
    assert result["applicability"] == "NOT_APPLICABLE_FINANCIAL_OR_UNRESOLVED_ENTITY"
    assert result["economics_status"] == "NOT_APPLICABLE" and not result["facts"]


def test_conflicting_values_drop_the_metric_instead_of_choosing():
    result = run([fact("net_income", 100), fact("net_income", 101, citation_id="other"), fact("operating_cash_flow", 50)])
    assert not result["cash_conversion"]["measurements"]
    assert any("CONFLICTING_OFFICIAL_VALUES_IN_STATEMENT_SET" in r["reason_codes"] for r in result["rejected"])


def test_profit_up_cash_down_is_explained_with_matched_periods_and_unresolved_economics():
    rows = [fact("net_income", 120), fact("operating_cash_flow", 60),
            fact("net_income", 100, year=2025, comparative_basis="RECLASSIFIED_COMPARATIVE"),
            fact("operating_cash_flow", 90, year=2025, comparative_basis="RECLASSIFIED_COMPARATIVE")]
    caution = {"caution_id": "C1", "kind": "COMPARATIVES_RECLASSIFIED", "document_sha256": "d" * 64,
               "statement_families": ["income_statement", "cash_flow"], "effect": "X"}
    result = run(rows + [fact("net_income", 95, year=2025, doc="f" * 64)], gates=gate(caution))
    move, = result["profit_cash_co_movement"]
    assert move["label"] == "PROFIT_INCREASED_OPERATING_CASH_DECREASED" and move["relationship"] == "OPPOSITE_DIRECTION"
    change, = result["conversion_changes"]
    assert (change["prior_ratio"], change["current_ratio"], change["direction"]) == (.9, .5, "LOWER")
    assert all("RECLASSIFIED_COMPARATIVE_PRESERVED:C1" in p["basis_labels"] for p in result["matched_comparisons"])
    refused, = result["refused_comparisons"]  # the prior original filing is not the reclassified basis
    assert refused["reason_codes"] == ["PRIOR_VALUE_NOT_ON_RECLASSIFIED_COMPARATIVE_BASIS:C1"]
    assert result["earnings_quality"]["reported_profit_increase_interpretation"] == "REPORTED_PROFIT_INCREASE_ECONOMICS_UNRESOLVED"
    assert "QUALIFIED_SHARE_BASIS_UNAVAILABLE" in result["earnings_quality"]["unresolved_components"]
    assert {e["code"] for e in result["explanation"]} >= {"PROFIT_INCREASED_OPERATING_CASH_DECREASED",
                                                          "REPORTED_PROFIT_INCREASE_ECONOMICS_UNRESOLVED"}


def test_scope_change_requires_issuer_like_for_like_basis_and_never_manufactures_cash_deterioration():
    caution = {"caution_id": "SCOPE", "kind": "CONSOLIDATION_SCOPE_CHANGE", "effective_from": "2026-01-01",
               "statement_families": ["income_statement", "cash_flow"], "effect": "X",
               "like_for_like_basis": {"statement_families": ["income_statement"], "line_codes": ["10", "61"]}}
    rows = [fact("revenue", 80), fact("attributable_net_income", 114), fact("operating_cash_flow", -11),
            fact("revenue", 100, year=2025, comparative_basis="AS_PREVIOUSLY_REPORTED"),
            fact("revenue", 70, year=2025, comparative_basis="ISSUER_LIKE_FOR_LIKE_RESTATEMENT"),
            fact("attributable_net_income", 100, year=2025, comparative_basis="ISSUER_LIKE_FOR_LIKE_RESTATEMENT"),
            fact("operating_cash_flow", 17, year=2025, comparative_basis="AS_PREVIOUSLY_REPORTED")]
    result = run(rows, gates=gate(caution))
    measured = {(p["metric"], p["prior_basis"]): p for p in result["matched_comparisons"]}
    assert set(measured) == {("revenue", "ISSUER_LIKE_FOR_LIKE_RESTATEMENT"),
                             ("attributable_net_income", "ISSUER_LIKE_FOR_LIKE_RESTATEMENT")}
    assert measured[("revenue", "ISSUER_LIKE_FOR_LIKE_RESTATEMENT")]["direction"] == "INCREASED"
    refused = {(p["metric"], p["prior_basis"]): p["reason_codes"] for p in result["refused_comparisons"]}
    assert refused[("revenue", "AS_PREVIOUSLY_REPORTED")] == ["COMPARATIVE_NOT_RESTATED_FOR_SCOPE_CHANGE:SCOPE"]
    assert refused[("operating_cash_flow", "AS_PREVIOUSLY_REPORTED")] == ["COMPARATIVE_NOT_RESTATED_FOR_SCOPE_CHANGE:SCOPE"]
    assert not result["profit_cash_co_movement"] and not result["conversion_changes"]
    assert "POSITIVE_PROFIT_NEGATIVE_OPERATING_CASH" in result["earnings_quality"]["divergences"]


def test_template_line_code_change_refuses_cross_template_identity():
    caution = {"caution_id": "TT43", "kind": "TEMPLATE_LINE_CODE_CHANGE", "effective_from": "2026-01-01",
               "statement_families": ["income_statement"], "line_codes": ["10"], "effect": "X"}
    result = run([fact("revenue", 2), fact("revenue", 1, year=2025, doc="f" * 64)], gates=gate(caution))
    assert result["refused_comparisons"][0]["reason_codes"] == ["TEMPLATE_LINE_CODE_IDENTITY_CHANGED:TT43"]


def test_explicit_non_operating_line_and_cash_balance_limits():
    rows = [fact("net_income", 200), fact("investment_property_disposal_result", 50),
            fact("cash_and_equivalents", 999)]
    result = run(rows)
    component, = result["earnings_quality"]["explicit_components"]
    assert component["share_of_profit_after_tax"] == .25 and component["recurrence_assessment"] == "UNKNOWN"
    assert "EXCEPTIONAL_ITEMS_NOT_EXPLICITLY_QUALIFIED" not in result["earnings_quality"]["unresolved_components"]
    balance, = result["balance_context"]
    assert {"CASH_BALANCE_IS_NOT_FREE_CASH_FLOW", "NET_CASH_NOT_CALCULATED_NO_QUALIFIED_DEFINITION"} <= set(balance["limitations"])


def test_gate_registry_is_closed_carries_no_amounts_and_names_exact_blockers(tmp_path):
    spec = load_issuer_gates()
    assert set(spec["issuers"]) == {"VNM", "FPT", "QNS"} and spec["authority_effect"] == "NONE"
    for ticker, entry in spec["issuers"].items():
        assert entry["qualification_blockers"] and entry["owner_decisions_required"]
        assert len(entry["document"]["document_sha256"]) == 64
        assert "value" not in json.dumps(entry["candidate_rows"])
    kinds = {c["kind"] for c in spec["issuers"]["FPT"]["comparability_cautions"]}
    assert {"CONSOLIDATION_SCOPE_CHANGE", "DECONSOLIDATION_CASH_OUTFLOW", "UNREVIEWED_BUSINESS_RELEASE"} <= kinds
    bad = json.loads(GATES_PATH.read_bytes())
    bad["issuers"]["VNM"]["candidate_rows"][0]["value"] = 1
    path = tmp_path / "gates.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="MUST_NOT_CARRY_AMOUNTS"):
        load_issuer_gates(path)


def _preview_rows(ticker, *, as_qualified):
    spec = json.loads(PREVIEW.read_bytes())
    issuer = spec["issuers"][ticker]
    rows = []
    for row in issuer["rows"]:
        out = fact(row["canonical_metric"], row["value"], year=int(row["reporting_period"][:4]),
                   doc=issuer["document_sha256"], ticker=ticker, line_code=row["line_code"],
                   knowledge_available_at=spec["preview_knowledge_available_at"],
                   qualification_state="QUALIFIED" if as_qualified else spec["qualification_state"],
                   factual_status="qualified" if as_qualified else "candidate")
        if row["comparative_basis"]:
            out["comparative_basis"] = row["comparative_basis"]
        rows.append(out)
    return spec, rows


@pytest.mark.parametrize("ticker", ["VNM", "FPT", "QNS"])
def test_candidates_never_enter_the_default_path(ticker):
    spec, rows = _preview_rows(ticker, as_qualified=False)
    result = interim_earnings_cash_research_context({"entity_class": "corporate", "official_field_context": rows},
                                                    cutoff=spec["preview_cutoff"], ticker=ticker)
    assert not result["facts"] and result["economics_status"] == "UNKNOWN"
    assert all("EXISTING_EXACT_FIELD_QUALIFICATION_REQUIRED" in r["reason_codes"] for r in result["rejected"])
    assert any(e["code"] == "CURRENT_INCOME_AND_CASH_FACTS_NOT_QUALIFIED" for e in result["explanation"])


def _preview(ticker):
    # Isolated offline interface preview: the test, not production code, treats candidates as qualified.
    spec, rows = _preview_rows(ticker, as_qualified=True)
    return interim_earnings_cash_research_context({"entity_class": "corporate", "official_field_context": rows},
                                                  cutoff=spec["preview_cutoff"], ticker=ticker)


def test_offline_preview_vnm_profit_up_operating_cash_down_on_reclassified_comparatives():
    result = _preview("VNM")
    labels = {(m["profit_metric"], m["label"]) for m in result["profit_cash_co_movement"]}
    assert labels == {("net_income", "PROFIT_INCREASED_OPERATING_CASH_DECREASED"),
                      ("attributable_net_income", "PROFIT_INCREASED_OPERATING_CASH_DECREASED")}
    change = next(c for c in result["conversion_changes"] if c["profit_metric"] == "net_income")
    assert change["direction"] == "LOWER"
    assert round(change["prior_ratio"], 4) == .9373 and round(change["current_ratio"], 4) == .6156
    assert all(p["prior_basis"] == "RECLASSIFIED_COMPARATIVE" for p in result["matched_comparisons"])
    assert not result["refused_comparisons"] and not result["balance_context"]


def test_offline_preview_fpt_uses_like_for_like_income_and_refuses_cash_comparison():
    result = _preview("FPT")
    measured = {(p["metric"], p["prior_basis"]): p for p in result["matched_comparisons"]}
    assert set(measured) == {("revenue", "ISSUER_LIKE_FOR_LIKE_RESTATEMENT"),
                             ("net_income", "ISSUER_LIKE_FOR_LIKE_RESTATEMENT"),
                             ("attributable_net_income", "ISSUER_LIKE_FOR_LIKE_RESTATEMENT")}
    assert round(measured[("revenue", "ISSUER_LIKE_FOR_LIKE_RESTATEMENT")]["growth_ratio"], 3) == .126
    assert round(measured[("attributable_net_income", "ISSUER_LIKE_FOR_LIKE_RESTATEMENT")]["growth_ratio"], 3) == .141
    refused = {p["metric"] for p in result["refused_comparisons"]}
    assert refused == {"revenue", "net_income", "attributable_net_income", "operating_cash_flow"}
    assert not result["profit_cash_co_movement"] and not result["conversion_changes"]
    current = [m for m in result["cash_conversion"]["measurements"] if m["comparative_basis"] == "CURRENT_COLUMN"]
    assert {m["relationship"] for m in current} == {"POSITIVE_PROFIT_NEGATIVE_OPERATING_CASH"}


def test_offline_preview_qns_profit_and_cash_same_direction_without_net_cash():
    result = _preview("QNS")
    assert {m["relationship"] for m in result["profit_cash_co_movement"]} == {"SAME_DIRECTION"}
    change = next(c for c in result["conversion_changes"] if c["profit_metric"] == "net_income")
    assert change["direction"] == "HIGHER" and round(change["current_ratio"], 3) == .477
    assert "NET_CASH_NOT_CALCULATED_COMPONENTS_KEPT_SEPARATE" in json.dumps(result["comparability"]["issuer_cautions"])


def _session(day):
    return json.loads(SESSIONS.read_bytes())["sessions"][day]


@pytest.mark.parametrize("day", ["2026-10-20", "2026-10-22"])
def test_real_sessions_add_context_without_changing_any_retained_decision_field(day):
    session = _session(day)
    statuses = {}
    for ticker, row in session["rows"].items():
        saved = copy.deepcopy(row)
        decision, fundamental = row["integrated"], row["fundamental"]
        before = delivery.project_integrated_decision_for_ai_delivery(decision, source_session=day)
        card = delivery.financial_research_card({"ticker": ticker, "fundamental_context": row["original_card_fundamental"]},
                                                fundamental, decision, cutoff=session["cutoff"])
        context = card["fundamental_research_context"]["earnings_cash"]
        statuses[ticker] = context["economics_status"]
        assert context["vote_effect"] == "NONE" and context["is_actionable"] is False
        assert not context["matched_comparisons"] and not context["cash_conversion"]["measurements"]
        assert card["fundamental_context"] == row["original_card_fundamental"]
        assert delivery.project_integrated_decision_for_ai_delivery(decision, source_session=day) == before
        assert row == saved
        if ticker in {"VNM", "FPT", "QNS"}:
            codes = {e["code"] for e in context["explanation"]}
            assert "CURRENT_INCOME_AND_CASH_FACTS_NOT_QUALIFIED" in codes
            assert context["issuer_gate"]["qualification_blockers"]
    assert statuses["VNM"] == statuses["QNS"] == "UNKNOWN"
    assert statuses["FPT"] == statuses["PNJ"] == "PARTIAL_FACTS_NO_MEASUREMENT"
    pnj = interim_earnings_cash_research_context(session["rows"]["PNJ"]["fundamental"], cutoff=session["cutoff"], ticker="PNJ")
    assert "OPERATING_CASH_FLOW_ONLY_FOR_OTHER_PERIODS" in {c for b in pnj["cash_conversion"]["blockers"] for c in b["reason_codes"]}


def test_actual_qualified_overlay_measures_vre_conversion_through_source_projection():
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
    measured = {}
    for ticker, record in projected["records"].items():
        context = record["interim_earnings_cash_research_context"]
        assert _fundamental_summary(record)["interim_earnings_cash_research_context"] == context
        for m in context["cash_conversion"]["measurements"]:
            measured[(ticker, m["profit_metric"])] = m
    vre = measured[("VRE", "net_income")]
    assert vre["relationship"] == "OPERATING_CASH_BELOW_PROFIT"
    assert (vre["profit"], vre["operating_cash_flow"]) == (3214788000000, 1555752000000)
    component = next(c for c in projected["records"]["VRE"]["interim_earnings_cash_research_context"]
                     ["earnings_quality"]["explicit_components"] if c["metric"] == "investment_property_disposal_result")
    assert component["role"] == "EXPLICIT_NON_OPERATING_EARNINGS_LINE"


def test_full_delivery_surfaces_carry_the_same_earnings_cash_context():
    from test_ai_research_session_delivery import _operation, _integrated_delivery_fixture
    operation, integrated = _operation(), _integrated_delivery_fixture(session="2026-10-22")
    operation["manifest"]["market_session"] = "2026-10-22"
    rows = [fact("net_income", 100, ticker="AAA"), fact("operating_cash_flow", -5, ticker="AAA")]
    inputs = {"descriptive": {"records": {"AAA": {}}}, "fundamental": {"session_cutoff": CUTOFF,
              "records": {"AAA": {"entity_class": "corporate", "official_field_context": rows}}},
              "integrated_investment_decision_product": integrated}
    saved = copy.deepcopy((operation, inputs))
    output = delivery.build_delivery(operation, inputs)
    primary = json.loads(output["primary"])["ticker_research_contexts"]["AAA"]
    cockpit = json.loads(output["projection"])["ticker_cards"]["AAA"]
    companion = json.loads(output["full_universe"])
    for card in [primary, cockpit, companion]:
        measurement, = card["fundamental_research_context"]["earnings_cash"]["cash_conversion"]["measurements"]
        assert measurement["relationship"] == "POSITIVE_PROFIT_NEGATIVE_OPERATING_CASH"
    decision_card = json.loads(output["projection"])["decision_card_v1"]["AAA"]
    assert decision_card["fundamental"]["interim_earnings_cash_research_context"] == \
        primary["fundamental_research_context"]["earnings_cash"]
    assert (operation, inputs) == saved
