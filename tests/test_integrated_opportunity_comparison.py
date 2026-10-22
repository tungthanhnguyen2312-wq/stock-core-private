"""Selected investment research uses existing owners and preserves policy/authority."""
import copy
import json

import pytest

from tests.test_sector_relative_financial_resilience import scenario
from tests.test_valuation_balance_sheet_divergence import run, SESSION
from tests.test_research_posture_v2_policy import tactical, FIRED, BEAR
from tests._integrated_decision_fixture import disposition_artifact, disposition_record
from stocklookup_core.tactical import market_structure_breakout_product_projection as structural
from stocklookup_core.decision import integrated_investment_decision_product as iid
from stocklookup_core.research import evidence_aware_candidate_comparison as comparison
from stocklookup_core.decision import investment_decision_workspace_projection as workspace
from stocklookup_core.decision import current_research_decision_packet as packet
from ai_research_session_delivery import project_opportunity_comparison_for_ai_delivery
import personal_investment_decision_action_center as action_center
from current_evidence_bound_scenario import bind_integrated_scenarios as BIND


def source():
    e,w,sectors,raw = scenario()
    run(e,w,sectors,raw)
    rows = {}
    for i,ticker in enumerate(e["records"]):
        row = tactical(**(BEAR if i == 0 else FIRED))
        row.update(ticker=ticker,as_of_session=SESSION,trigger_close_comparison_operator=">",
            invalidation_close_comparison_operator="<",trigger_horizon="PIVOT_BREAKOUT_MEASUREMENT",
            invalidation_horizon="SWING_STRUCTURE_ANALYTICAL_CONTEXT",
            price_basis_qualification={"price_basis_verified":False,"basis":"PROVIDER_SCOPED","historical_pit_eligible":False})
        rows[ticker] = row
    ta = {"contract_version":structural.CONTRACT_VERSION,"session":SESSION,"records":rows}
    ta.update(structural.content_identity(ta))
    return iid.build_artifact(session=SESSION,requested_at=SESSION+"T16:00:00+07:00",technical_structure_artifact=ta,
        technical_coverage_disposition_artifact=disposition_artifact({t:disposition_record(t,session=SESSION,currency="CURRENT_SESSION") for t in rows},session=SESSION),
        financial_analysis_artifact=w["financial_analysis_product"],financial_peer_materialization_artifact=w,current_valuation_artifact=e)


def request(*tickers):
    return {"research_session":SESSION,"tickers":list(tickers or ("T0","T1"))}


def test_real_financial_timing_contrasts_preserve_source_and_traceable_conditions():
    product = source()
    saved = copy.deepcopy(product)
    result = comparison.build_integrated_comparison(request(),integrated_decision=product,bind_scenarios=BIND)
    assert result["profiles"]["T0"]["finding_codes"] == ["VALUATION_DISCOUNT_WITH_RESILIENCE_COUNTERTHESIS",
        "FINANCIAL_STRENGTH_WITHOUT_FRESH_ENTRY_CONFIRMATION","OBSERVED_ADVERSE_STRUCTURE_DOWNSIDE_CONDITION"]
    assert "OBSERVED_ADVERSE_STRUCTURE_DOWNSIDE_CONDITION" not in result["profiles"]["T1"]["finding_codes"]
    # Compact: the full Integrated Decision record is referenced by identity, never re-embedded.
    t0 = result["profiles"]["T0"]
    assert "integrated_context" not in t0["timing_and_conditions"]
    assert t0["decision_fitness_dimensions"]["VALUATION"]["detail"] == "SEE_SOURCE_DECISION_IDENTITY"
    assert t0["source_decision_identity"] == product["records"]["T0"]["decision_identity"]
    assert result["profiles"]["T0"]["posture_condition_class"] == product["records"]["T0"]["posture_condition_class"]
    assert result["pairwise"][0]["qualified_numerical_axes"].keys() >= {"research_pb","cash_to_assets","debt_to_assets","debt_to_equity"}
    assert result["pairwise"][0]["conditional_contrasts"]
    assert product == saved
    assert project_opportunity_comparison_for_ai_delivery(result) == result
    text = comparison.integrated_comparison_markdown(result)
    assert "sector-relative valuation discount" in text and "Confirmation:" in text and "Counter-thesis:" in text
    assert "UNKNOWN" in text


@pytest.mark.parametrize("tickers", [[],["T0"],["T0","T0"],["T0","T1","T2","T3","T4","T5"],["t0","T1"],["NO_SUCH_TICKER","T1"]])
def test_explicit_selected_request_is_bounded_and_never_silently_drops_names(tickers):
    with pytest.raises(ValueError):
        comparison.build_integrated_comparison({"research_session":SESSION,"tickers":tickers},integrated_decision=source(),bind_scenarios=BIND)


def test_stale_and_unknown_evidence_are_not_current_trading_confirmation():
    product = source()
    # Real no-current-evidence product from the same engine/valuation fixture.
    e,w,s,r = scenario()
    run(e,w,s,r)
    old = iid.build_artifact(session=SESSION,requested_at="retained",technical_structure_artifact={"records":{}},
        financial_analysis_artifact=w["financial_analysis_product"],financial_peer_materialization_artifact=w,current_valuation_artifact=e)
    result = comparison.build_integrated_comparison(request(),integrated_decision=old,bind_scenarios=BIND)
    assert "CURRENT_TIMING_COMPARISON_UNKNOWN" in result["profiles"]["T0"]["finding_codes"]
    assert not any("QUALIFIED_ENTRY_CONDITION" in f for p in result["profiles"].values() for f in p["finding_codes"])


@pytest.mark.parametrize("mutation", ["session","hash","sibling","policy","request_field"])
def test_source_identity_session_and_policy_cannot_be_replaced(mutation):
    product,req = source(),request()
    if mutation == "session":req["research_session"] = "2026-10-15"
    if mutation == "hash":product["artifact_identity"] = "forged"
    if mutation == "sibling":product["records"]["T5"]["research_action_posture"] = "ENTER"
    if mutation == "policy":product["research_action_policy_version"] = "v1"
    if mutation == "request_field":req["buy_score"] = 100
    with pytest.raises(ValueError):comparison.build_integrated_comparison(req,integrated_decision=product,bind_scenarios=BIND)


def test_cross_sector_comparison_preserves_independent_theses_without_numeric_ranking():
    product = source()
    # A real differently classified peer pool must fail closed for dependent axes.
    e,w,sectors,raw = scenario()
    sectors["T1"] = "Different sector"
    run(e,w,sectors,raw)
    new = iid.build_artifact(session=SESSION,requested_at="retained",technical_structure_artifact={"records":{}},
        financial_analysis_artifact=w["financial_analysis_product"],financial_peer_materialization_artifact=w,current_valuation_artifact=e)
    result = comparison.build_integrated_comparison(request(),integrated_decision=new,bind_scenarios=BIND)
    assert result["pairwise"][0]["comparability"] == "INDEPENDENT_RESEARCH_CONTEXT_ONLY"
    assert not result["pairwise"][0]["qualified_numerical_axes"]


def test_selected_evidence_survives_action_center_workspace_and_packet_without_portfolio():
    product,req = source(),request()
    expected = comparison.build_integrated_comparison(req,integrated_decision=product,bind_scenarios=BIND)
    old = action_center.build_artifact(session=SESSION,requested_at="retained",integrated_decision_artifact=product)
    new = action_center.build_artifact(session=SESSION,requested_at="retained",integrated_decision_artifact=product,opportunity_comparison_request=req)
    assert new["selected_opportunity_comparison"] == expected
    assert {k:v for k,v in new.items() if k not in {"selected_opportunity_comparison","artifact_identity","artifact_sha256"}} == {k:v for k,v in old.items() if k not in {"artifact_identity","artifact_sha256"}}
    assert "Selected investment opportunity research" in action_center.markdown(new)
    op = {"contract_version":"opportunity_context/v1","artifact_identity":"op:fixture","as_of_session":SESSION,"records":{t:{} for t in product["records"]}}
    dec = {"contract_version":"security_decision_context/v1","source_artifacts":{"opportunity_context":"op:fixture"},"as_of_session":SESSION,"records":{t:{} for t in product["records"]}}
    view = workspace.build_artifacts(opportunity_artifact=op,decision_artifact=dec,integrated_decision_artifact=product,requested_at="retained",selected_opportunity_comparison=expected)
    assert view["selected_opportunity_comparison"] == expected


def test_comparison_identity_protects_ai_and_human_delivery():
    result = comparison.build_integrated_comparison(request(),integrated_decision=source(),bind_scenarios=BIND)
    result["profiles"]["T0"]["finding_codes"] = ["BUY_NOW"]
    with pytest.raises(ValueError):project_opportunity_comparison_for_ai_delivery(result)
    with pytest.raises(ValueError):comparison.integrated_comparison_markdown(result)


def test_selected_comparison_reaches_research_packet_scope_and_fails_outside_it():
    from tests.test_current_research_decision_packet import _opportunity, _decision
    product,req = source(),request()
    opportunity = _opportunity({t:_decision(t) for t in product["records"]},session=SESSION)
    plain = packet.build_artifact(opportunity=opportunity,integrated_decision=product)
    selected = packet.build_artifact(opportunity=opportunity,integrated_decision=product,opportunity_comparison_request=req)
    assert selected["selected_opportunity_comparison"] == comparison.build_integrated_comparison(req,integrated_decision=product,bind_scenarios=BIND)
    assert selected["records"] == plain["records"]
    narrow = _opportunity({"T1":_decision("T1")},session=SESSION)
    with pytest.raises(packet.CurrentResearchDecisionPacketError,match="SELECTED_COMPARISON_OUTSIDE_PACKET_SCOPE"):
        packet.build_artifact(opportunity=narrow,integrated_decision=product,opportunity_comparison_request=req)
    with pytest.raises(ValueError,match="REQUIRES_VERIFIED_INTEGRATED_DECISION"):
        packet.build_artifact(opportunity=opportunity,opportunity_comparison_request=req)


def test_actual_ai_delivery_bundle_carries_verified_comparison_additively(monkeypatch):
    import ai_research_session_delivery as delivery
    from tests.test_ai_research_session_delivery import _operation
    monkeypatch.setattr(delivery,"owner_focus_tickers",lambda: ())
    product,req = source(),request()
    operation = _operation()
    operation["manifest"].update(market_session=SESSION,session_coherence={"session":SESSION})
    inputs = {"descriptive":{"records":{t:{} for t in product["records"]}},"integrated_investment_decision_product":product}
    saved = copy.deepcopy(inputs)
    plain = json.loads(delivery.build_delivery(operation,inputs)["primary"])
    shipped = delivery.build_delivery(operation,inputs,opportunity_comparison_request=req)
    primary = json.loads(shipped["primary"])
    expected = json.loads(json.dumps(comparison.build_integrated_comparison(req,integrated_decision=product,bind_scenarios=BIND)))
    assert primary.pop("selected_opportunity_comparison") == expected
    assert primary == plain and inputs == saved
    assert expected["authority_boundary"]["no_composite_score_or_winner"] is True
    assert all(p["is_actionable"] is False for p in expected["profiles"].values())
    with pytest.raises(ValueError,match="REQUIRES_VERIFIED_INTEGRATED_DECISION"):
        delivery.build_delivery(operation,{"descriptive":inputs["descriptive"]},opportunity_comparison_request=req)


def test_action_center_rejects_excluded_and_missing_sources_and_console_never_names_tickers():
    product,req = source(),request()
    with pytest.raises(action_center.ActionCenterError,match="EXCLUDED_TICKER"):
        action_center.build_artifact(session=SESSION,requested_at="retained",integrated_decision_artifact=product,
            excluded_tickers=frozenset({"T1"}),opportunity_comparison_request=req)
    artifact = action_center.build_artifact(session=SESSION,requested_at="retained",integrated_decision_artifact=product,opportunity_comparison_request=req)
    summary = action_center.public_console_summary(artifact)
    assert summary["selected_opportunity_comparison_status"] == "READY"
    assert "T0" not in json.dumps(summary) and "T1" not in json.dumps(summary)


def test_cli_compare_request_fails_closed_without_traceback(monkeypatch, capsys):
    import stocklookup
    def refuse(**kwargs):
        assert kwargs["opportunity_comparison_tickers"] == ["AAA"]
        raise ValueError("SELECT_TWO_TO_FIVE_UNIQUE_SECURITIES")
    monkeypatch.setattr(action_center,"evaluate_from_retained_artifacts",refuse)
    assert stocklookup.main(["action-center","--compare","AAA"]) == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == "SELECT_TWO_TO_FIVE_UNIQUE_SECURITIES"


def test_injected_binder_output_is_rechecked_and_workspace_rejects_foreign_comparisons():
    product,req = source(),request()
    def forged(**kwargs):
        binding = BIND(**kwargs)
        binding["records"]["T0"]["decision_identity"] = "decision:forged"
        return binding
    with pytest.raises(ValueError,match="SCENARIO_BINDING_MISMATCH"):
        comparison.build_integrated_comparison(req,integrated_decision=product,bind_scenarios=forged)
    expected = comparison.build_integrated_comparison(req,integrated_decision=product,bind_scenarios=BIND)
    op = {"contract_version":"opportunity_context/v1","artifact_identity":"op:fixture","as_of_session":SESSION,"records":{t:{} for t in product["records"]}}
    dec = {"contract_version":"security_decision_context/v1","source_artifacts":{"opportunity_context":"op:fixture"},"as_of_session":SESSION,"records":{t:{} for t in product["records"]}}
    e,w,_s,_r = scenario()
    run(e,w,_s,_r)
    other = iid.build_artifact(session=SESSION,requested_at="retained",technical_structure_artifact={"records":{}},
        financial_analysis_artifact=w["financial_analysis_product"],financial_peer_materialization_artifact=w,current_valuation_artifact=e)
    assert other["artifact_identity"] != product["artifact_identity"]
    with pytest.raises(workspace.InvestmentDecisionWorkspaceError,match="SOURCE_MISMATCH"):
        workspace.build_artifacts(opportunity_artifact=op,decision_artifact=dec,integrated_decision_artifact=other,requested_at="retained",selected_opportunity_comparison=expected)
    tampered = copy.deepcopy(expected); tampered["profiles"]["T1"]["research_action_posture"] = "ENTER"
    with pytest.raises(workspace.InvestmentDecisionWorkspaceError,match="IDENTITY_INVALID"):
        workspace.build_artifacts(opportunity_artifact=op,decision_artifact=dec,integrated_decision_artifact=product,requested_at="retained",selected_opportunity_comparison=tampered)
