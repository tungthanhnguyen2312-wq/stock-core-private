"""Economic identity and existing-consumer regressions; synthetic receipts grant no authority."""
import copy
import json
from pathlib import Path

import pytest

import current_corporate_intelligence_axis as axis
import ai_research_session_delivery as delivery
from stocklookup_core.research import shareholder_economics as economics

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = "2026-10-22T15:00:00+07:00"
PREVIEW = json.loads((ROOT / "tests/fixtures/shareholder_economics_candidate_preview_v1.json").read_bytes())
ACTUAL = json.loads((ROOT / "tests/fixtures/official_income_research_actual_sessions_v1.json").read_bytes())
SEMANTIC_KEYS = ("kind", "state", "unit", "subject", "value", "scope", "effective_date",
                 "period_start", "period_end", "consideration") + economics.OPTIONAL_SEMANTICS


def receipt(kind="ISSUANCE", state="APPROVED_PROPOSAL", **changes):
    # Only an issuer-neutral unit-test stand-in for a previously qualified source receipt.
    # No document is registered, fetched or represented as actual first-party bytes.
    row = dict(ticker="SYN", kind=kind, state=state, value=100, unit="shares", subject="SYNTHETIC_CASE",
        scope="issuer", effective_date="2026-10-01", period_start=None, period_end=None,
        source_owner="corporate_action_events", qualification_state="QUALIFIED", field_qualification="QUALIFIED",
        coverage_kind="REAL_RETAINED_INPUT", document_sha256="d" * 64, source_identity="synthetic-owner-receipt",
        source_locator="https://example.invalid/offline-test", citation_id="synthetic-citation",
        published_at="2026-10-01T08:00:00+07:00", observed_at="2026-10-01T09:00:00+07:00",
        knowledge_available_at="2026-10-01T10:00:00+07:00") | changes
    row["qualified_semantics"] = {k: row.get(k) for k in SEMANTIC_KEYS}
    return row


def project(*rows, **kwargs):
    return economics.project_context(ticker="SYN", cutoff=CUTOFF, observations=rows, **kwargs)


def codes(context):
    return {x["code"] for x in context["explanations"]}


@pytest.mark.parametrize("ticker", ["PNJ", "NVL", "SSI", "HPG", "PAN"])
def test_five_dossier_cases_are_preview_only(ticker):
    rows = PREVIEW["rows"][ticker]
    live = economics.project_context(ticker=ticker, cutoff=PREVIEW["cutoff"], observations=rows)
    assert not live["claims"]
    assert all("value" not in row for row in live["rejected"])
    demo = economics.offline_preview(ticker=ticker, cutoff=PREVIEW["cutoff"], observations=rows)
    assert demo["status"] == "OFFLINE_PREVIEW" and demo["coverage_kind"] == "OFFLINE_FIXTURE"
    assert not demo["rejected"]
    assert all(row["qualification_state"] == "CANDIDATE_NOT_PRODUCER_QUALIFIED" for row in demo["claims"])
    assert economics.at_cutoff(demo, ticker=ticker, cutoff=PREVIEW["cutoff"]) is None
    assert demo["current_outstanding_shares"] is None and demo["price_adjustment_factor"] is None
    if ticker == "PNJ":
        assert {"BOOKED", "MANAGEMENT_ESTIMATE", "APPROVED_PROPOSAL"} <= {r["state"] for r in demo["claims"]}
        assert {"AGGREGATE_PROVISION_CAPTION", "ESTIMATE_NOT_REPORTED_ACTUAL", "PROFIT_PLAN_NOT_ACTUAL"} <= codes(demo)
        assert not any(r["kind"] == "SHARE_REPURCHASE" for r in demo["claims"])
        assert next(r for r in demo["claims"] if r["kind"] == "CONTRACTUAL_OBLIGATION")["value"] is None
    if ticker == "NVL":
        assert {"NONCASH_CONVERSION_NOT_CASH_RAISE", "PLANNED_FUNDS_NOT_RECEIVED", "EARMARKED_NOT_REPAID"} <= codes(demo)
        assert not any(r["state"] in {"RECEIVED", "REPAID"} for r in demo["claims"])
    if ticker == "SSI":
        assert "BONUS_NOT_NEW_EARNINGS_OR_CASH" in codes(demo)
        assert "EPS_WEIGHTED_AVERAGE_SHARES" in demo["unavailable_dimensions"]
    if ticker == "HPG":
        assert {r["kind"] for r in demo["claims"]} == {"OUTSTANDING_SHARES", "LISTED_SHARES"}
        assert "TRADABLE_SHARES" in demo["unavailable_dimensions"]
    if ticker == "PAN":
        assert not demo["claims"] and "OUTSTANDING_SHARES" in demo["unavailable_dimensions"]


@pytest.mark.parametrize("state", ["APPROVED_PROPOSAL", "REGISTERED_OFFER", "EXECUTED"])
def test_issuance_never_sets_current_denominator_cash_or_factor(state):
    r = receipt(state=state, execution_evidence_qualified=state == "EXECUTED", ex_date="2026-09-30")
    ctx = project(r)
    assert ctx["claims"][0]["state"] == state
    assert ctx["current_outstanding_shares"] is None and ctx["prospective_outstanding_shares"] is None
    assert ctx["price_adjustment_factor"] is None
    assert "FINANCING_PROCEEDS" in ctx["unavailable_dimensions"]
    assert not ctx["historical_pit_eligible"]


@pytest.mark.parametrize("kind,state,flag", [
    ("ISSUANCE", "EXECUTED", "execution_evidence_qualified"),
    ("FINANCING_PROCEEDS", "RECEIVED", "settlement_evidence_qualified"),
    ("DEBT_REPAYMENT", "REPAID", "settlement_evidence_qualified"),
])
def test_execution_and_settlement_require_separate_proof(kind, state, flag):
    r = receipt(kind, state, unit="shares" if kind == "ISSUANCE" else "VND")
    assert not project(r)["claims"]
    assert project(r | {flag: True})["claims"]


@pytest.mark.parametrize("mutation", [
    {"qualification_state": "CANDIDATE"}, {"field_qualification": "UNKNOWN"}, {"source_owner": "GROK"},
    {"published_at": None}, {"observed_at": "2026-10-22T09:00:00"},
    {"knowledge_available_at": "2026-10-23T08:00:00Z"}, {"document_sha256": "bad"},
    {"citation_id": None}, {"value": True}, {"value": float("inf")},
    {"unit": "VND"}, {"ticker": "OTHER"}, {"qualified_semantics": {}},
    {"conflicts": ["AMENDED_AMOUNT_NOT_RECONCILED"]}, {"effective_date": "bad"},
    {"coverage_kind": "OFFLINE_FIXTURE"}, {"knowledge_available_at": "2026-10-01T07:00:00+07:00"},
])
def test_source_time_identity_and_unit_gates_fail_locally(mutation):
    r = receipt() | mutation
    ctx = project(r)
    assert ctx["status"] == "UNKNOWN" and not ctx["claims"] and ctx["rejected"]


def test_conflict_blocks_only_its_identity_and_duplicate_is_not_a_new_fact():
    a = receipt()
    b = receipt(value=101, citation_id="other-citation")
    independent = receipt("OUTSTANDING_SHARES", "DATED_OBSERVATION", subject="COMMON_OUTSTANDING")
    ctx = project(a, a, b, independent)
    assert len(ctx["claims"]) == 1 and ctx["claims"][0]["kind"] == "OUTSTANDING_SHARES"
    assert ctx["current_outstanding_shares"] is None


def test_qualified_semantic_binding_prevents_caption_or_stage_reinterpretation():
    r = receipt()
    assert not project(r | {"state": "EXECUTED", "execution_evidence_qualified": True})["claims"]
    r = receipt("PROVISION", "BOOKED", unit="VND")
    assert not project(r)["claims"]  # Corporate source cannot manufacture a financial-owner fact.


def test_weighted_average_listed_and_outstanding_remain_independent():
    ctx = project(receipt("OUTSTANDING_SHARES", "DATED_OBSERVATION"),
        receipt("ISSUED_SHARES", "DATED_OBSERVATION", value=110),
        receipt("LISTED_SHARES", "DATED_OBSERVATION", value=105),
        receipt("EPS_WEIGHTED_AVERAGE_SHARES", "REPORTED", value=90,
                period_start="2026-01-01", period_end="2026-06-30"))
    assert len(ctx["claims"]) == 4
    assert "TRADABLE_SHARES" in ctx["unavailable_dimensions"]
    assert "EPS_BASIS_SEPARATE" in codes(ctx)


def test_duration_or_charter_capital_cannot_stand_in_for_dated_outstanding():
    duration = receipt("OUTSTANDING_SHARES", "DATED_OBSERVATION", effective_date=None,
                       period_start="2026-01-01", period_end="2026-06-30")
    capital = receipt("OUTSTANDING_SHARES", "DATED_OBSERVATION", unit="VND")
    assert not project(duration, capital)["claims"]
    assert project(duration)["rejected"][0]["reason_codes"] == ["SHARE_OBSERVATION_REQUIRES_EXPLICIT_DATE"]


@pytest.mark.parametrize("kind,state", [("ISSUANCE", "EXECUTED"),
    ("FINANCING_PROCEEDS", "RECEIVED"), ("DEBT_REPAYMENT", "REPAID")])
def test_future_actual_effects_stay_unavailable_even_with_qualified_proof(kind, state):
    row = receipt(kind, state, unit="shares" if kind == "ISSUANCE" else "VND",
        effective_date="2026-10-23", execution_evidence_qualified=True, settlement_evidence_qualified=True)
    assert not project(row)["claims"]
    assert "ACTUAL_EFFECT_AFTER_CUTOFF" in project(row)["rejected"][0]["reason_codes"]


@pytest.mark.parametrize("ticker", ["PNJ", "NVL", "SSI", "HPG", "PAN"])
def test_real_oct22_admitted_rows_only_and_existing_card_parity(ticker):
    data = ACTUAL["sessions"]["2026-10-22"]["rows"][ticker]
    original = {"ticker": ticker, "entry_action": "WAIT", "valuation_context": {"status": "UNCHANGED"}}
    before = copy.deepcopy(data)
    card = delivery.financial_research_card(original, data["fundamental"], data["integrated"], cutoff=CUTOFF)
    ctx = card.pop("shareholder_economics_context")
    card.pop("fundamental_research_context")
    assert card == original and data == before
    assert all(c["kind"] in {"OPERATING_CASH_FLOW", "PROVISION_CASH_FLOW_ADJUSTMENT"} for c in ctx["claims"])
    assert not any(c["kind"] == "PROVISION" for c in ctx["claims"])
    if ticker == "PNJ":
        provision = next(c for c in ctx["claims"] if c["kind"] == "PROVISION_CASH_FLOW_ADJUSTMENT")
        assert provision["value"] == 2667248523366 and "AGGREGATE_PROVISION_CAPTION" in codes(ctx)
    else:
        assert not ctx["claims"]  # Their new dossier figures are not admitted October22 inputs.


def test_non_voting_context_survives_existing_corporate_to_card_chain():
    from test_current_corporate_intelligence_axis import _signed_official, _signed_event_context
    from stocklookup_core.decision import integrated_investment_decision_product as iid
    from stocklookup_core.decision import current_research_decision_input as research
    from stocklookup_core.decision import current_research_decision_packet as packet
    from stocklookup_core.decision import investment_decision_workspace_projection as workspace
    from stocklookup_core.decision import current_research_ai_handoff_packet as ai
    from test_current_research_decision_packet import _opportunity, _decision
    inputs = dict(official_universe=_signed_official(["SYN"]), official_event_context=_signed_event_context([], "2026-10-22"),
                  root=ROOT, research_session="2026-10-22", include_supplemental_events=False)
    original = axis.build_artifact(**inputs)
    enriched = axis.build_artifact(**inputs, shareholder_economics_observations=[receipt()])
    assert enriched["coverage"] == original["coverage"]
    kwargs = dict(ticker="SYN", as_of_session="2026-10-22", tactical_record=None, financial_record=None,
                  valuation_record=None, relative_volume_record=None, market_sector_record=None)
    old = iid.build_ticker_integrated_decision(**kwargs, corporate_intelligence_record=original["records"]["SYN"])
    new = iid.build_ticker_integrated_decision(**kwargs, corporate_intelligence_record=enriched["records"]["SYN"])
    for k in ("research_action_posture", "decision_identity", "valuation_context_summary", "trigger", "invalidation"):
        assert old.get(k) == new.get(k)
    context = new["corporate_intelligence_context"]["forward_driver_context"]["shareholder_economics_context"]
    assert research._corporate(new)["forward_driver_context"]["shareholder_economics_context"] == context
    integrated = dict(contract_version=iid.CONTRACT_VERSION, session="2026-10-22", records={"SYN": new}, research_action_policy_version="v2")
    integrated.update(iid.content_identity(integrated))
    dp = packet.build_artifact(opportunity=_opportunity({"SYN": _decision("SYN")}, "2026-10-22"), integrated_decision=integrated)
    assert dp["records"]["SYN"]["components"]["shareholder_economics_context"] == context
    card = workspace.build_ticker_card(ticker="SYN", opportunity_record={"as_of_session": "2026-10-22"},
        decision_record={"as_of_session": "2026-10-22"}, sector="STEEL", portfolio_research=None, prospective_record={}, integrated_record=new)
    assert card["shareholder_economics_context"] == context
    ai_card = ai.build_card(ticker="SYN", workspace_card=card, screener_card=None, session="2026-10-22",
        current_research_scope=None, workspace_identity="synthetic-workspace", screener_identity=None)
    assert ai_card["shareholder_economics_context"] == context
    assert economics.at_cutoff(context, ticker="SYN", cutoff="2026-10-21T15:00:00+07:00") is None
    tampered = copy.deepcopy(context); tampered["claims"][0]["value"] += 1
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        economics.at_cutoff(tampered, ticker="SYN", cutoff=CUTOFF)


def test_generic_executed_issuance_no_longer_asserts_new_cash():
    result, reasons = axis.classify_catalyst_risk(event_type=axis.SHARE_ISSUANCE,
        status=axis.EXECUTED, original_event_status="EXECUTED")
    assert result == axis.MIXED
    assert "EXECUTED_ISSUANCE_RAISES_CAPITAL" not in reasons
    assert "EXECUTED_ISSUANCE_CASH_RECEIPT_NOT_ESTABLISHED" in reasons


def test_absent_cutoff_is_local_unknown_without_data_leak_or_crash():
    ctx = economics.project_context(ticker="SYN", cutoff=None, observations=[receipt()])
    assert not ctx["claims"] and ctx["status"] == "UNKNOWN"


def test_all_daily_delivery_surfaces_preserve_the_explanation():
    from test_ai_research_session_delivery import _operation, _integrated_delivery_fixture
    operation, integrated = _operation(), _integrated_delivery_fixture(session="2026-10-22")
    operation["manifest"]["market_session"] = "2026-10-22"
    source = ACTUAL["sessions"]["2026-10-22"]["rows"]["PNJ"]["fundamental"]
    source = copy.deepcopy(source)
    source["ticker"] = "AAA"
    for fact in source["official_field_context"]:
        fact["ticker"] = "AAA"
    inputs = {"descriptive": {"records": {"AAA": {}}}, "fundamental": {"session_cutoff": CUTOFF,
              "records": {"AAA": source}}, "integrated_investment_decision_product": integrated}
    saved = copy.deepcopy((operation, inputs))
    output = delivery.build_delivery(operation, inputs)
    primary = json.loads(output["primary"])["ticker_research_contexts"]["AAA"]["shareholder_economics_context"]
    cockpit = json.loads(output["projection"])
    assert cockpit["ticker_cards"]["AAA"]["shareholder_economics_context"] == primary
    assert cockpit["decision_card_v1"]["AAA"]["shareholder_economics_context"] == primary
    assert json.loads(output["full_universe"])["shareholder_economics_context"] == primary
    assert (operation, inputs) == saved


def test_canonical_exact_field_explanation_does_not_feed_the_numerical_financial_owner():
    source = (ROOT / "canonical_post_close_pipeline.py").read_text(encoding="utf-8")
    assert "financial_records=_corporate_economic_records()" in source
    assert 'financial_analysis_artifact=financial_session_artifact["financial_analysis_product"]' in source
