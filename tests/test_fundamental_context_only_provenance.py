import pytest

import stocklookup_core.financial.fundamental_signal_consumption_contract as contract
import integrated_investment_decision_product as product
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery


def compact(*, period="2026-Q1", qualification="READY", issuer="corporate"):
    return {"contract_version": contract.DIALECT_FINANCIAL_V2, "status": "AVAILABLE", "issuer_type": issuer,
            "analysis_family": "INDUSTRIAL_FINANCIAL_ANALYSIS" if issuer == "corporate" else "BANK_FINANCIAL_ANALYSIS",
            "free_cash_flow_proxy_direction_state": "WORSENING", "working_capital_trajectory_state": "WORKING_CAPITAL_IMPROVING",
            "working_capital_state": "NEGATIVE_NET_WORKING_CAPITAL",
            "feature_fitness": {key: {"fitness": qualification, "as_of_period": period}
                                for key in ["free_cash_flow_proxy_direction", "net_working_capital_direction", "net_working_capital"]}}


def synthesis(record):
    return contract.evaluate(record, decision_session="2026-09-30")


def test_amount_trajectories_keep_their_non_voting_semantics_and_period():
    result = synthesis(compact())
    working = result["dimensions"]["SHORT_TERM_LIQUIDITY"]
    observation = working["context_only_observations"]["net_working_capital_direction"]
    assert working["context_only"]["net_working_capital_direction"] == contract.RISING
    assert observation["value"] == contract.RISING
    assert observation["producer_value"] == "WORKING_CAPITAL_IMPROVING"
    assert observation["as_of_period"] == "2026-Q1" and observation["freshness"] == "CURRENT"
    assert observation["qualification"] == "READY"
    assert observation["source_features"] == ["net_working_capital_direction"]
    assert observation["decision_eligible"] is False
    assert observation["consumption_class"] == contract.RESEARCH_EVIDENCE_ONLY
    assert "No governed quality" in observation["policy_reason"]
    assert result["fundamental_state"] == contract.FUNDAMENTAL_INSUFFICIENT
    assert result["supporting_reason_codes"] == [] and result["contradicting_reason_codes"] == []


def test_proxy_and_stale_observations_remain_labelled_without_current_votes():
    result = synthesis(compact(period="2024-Q1", qualification="RESEARCH_PROXY"))
    observation = result["dimensions"]["CASH_QUALITY"]["context_only_observations"]["free_cash_flow_proxy_direction"]
    assert observation["qualification"] == "RESEARCH_PROXY"
    assert observation["freshness"] == "STALE_BUT_RESEARCH_USABLE"
    assert observation["decision_eligible"] is False
    assert observation["no_quality_or_action_inference"] is True


@pytest.mark.parametrize("record", [compact(period="2026-Q4"), compact(period="unknown"),
                                   compact(qualification="BLOCKED_BY_EVIDENCE"), compact(issuer="bank")])
def test_unusable_or_specialist_context_is_not_a_bare_observation(record):
    result = synthesis(record)
    assert not result["context_only"]
    assert all(not d.get("context_only_observations") for d in result["dimensions"].values())


def test_same_context_flows_through_existing_decision_dimension_and_ai_projection():
    result = product.build_ticker_integrated_decision(ticker="TEST", as_of_session="2026-09-30",
        tactical_record=None, financial_record=compact(), valuation_record=None,
        relative_volume_record=None, market_sector_record=None)
    observed = result["fundamental_synthesis"]["dimensions"]["CASH_QUALITY"]["context_only_observations"]
    components = result["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]["components"]
    assert components["dimensions"]["CASH_QUALITY"]["context_only_observations"] == observed
    view = project_integrated_decision_for_ai_delivery(result)
    assert view["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]["components"] == components
    assert view["is_actionable"] is False
