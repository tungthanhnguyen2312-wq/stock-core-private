import pytest
from research_liquidity_portfolio import build_liquidity_research_context, build_portfolio_research_context

def risk():
    return {"artifact_identity":"risk:x", "metadata":{"as_of_session":"2026-08-25"}, "ticker_risk_context":{"AAA":{"sector":"tech","volatility_context":{"L20":{"annualized_research_volatility":.2}}},"BBB":{"sector":"bank","volatility_context":{"L20":{"annualized_research_volatility":.3}}}}, "joint_matrix_context":{"L20":{"status":"JOINT_MATRIX_BLOCKED_T_RELATIVE_TO_N","included_tickers":["AAA","BBB"]},"L60":{"status":"JOINT_MATRIX_READY","included_tickers":["AAA","BBB"]}}}

def test_proxy_is_separate_from_exact_and_compact():
    x=build_liquidity_research_context(as_of_session="2026-08-25",records={"AAA":{"current_volume":200,"rolling_volume":100}})
    r=x["records"]["AAA"]; assert r["relative_volume"]==2 and r["research_proxy_status"]=="LIQUIDITY_RESEARCH_PROXY" and r["exact_execution_capacity_status"]=="EXECUTION_CAPACITY_EXACT_BLOCKED"

def test_explicit_portfolio_adaptive_joint_horizon_and_limits():
    l=build_liquidity_research_context(as_of_session="2026-08-25",records={"AAA":{"current_volume":2,"rolling_volume":1},"BBB":{}})
    p={"portfolio_id":"p","as_of_session":"2026-08-25","positions":[{"ticker":"AAA","explicit_weight":.8},{"ticker":"BBB","explicit_weight":.2}],"risk_limits":{"max_single_name_weight":.5}}
    x=build_portfolio_research_context(portfolio=p,risk_artifact=risk(),liquidity_context=l)
    assert x["selected_joint_risk_horizon"]=="L60" and x["user_limit_breaches"] and x["authority_boundary"]["no_recommended_position_size"]

def test_mixed_or_missing_portfolio_fails_closed():
    l=build_liquidity_research_context(as_of_session="2026-08-25",records={})
    with pytest.raises(ValueError,match="EXPLICIT_PORTFOLIO"):
        build_portfolio_research_context(portfolio={"as_of_session":"2026-08-25"},risk_artifact=risk(),liquidity_context=l)
    with pytest.raises(ValueError,match="MIXED"):
        build_portfolio_research_context(portfolio={"portfolio_id":"p","as_of_session":"2026-08-25","positions":[{"ticker":"AAA","quantity":1,"explicit_weight":.2}]},risk_artifact=risk(),liquidity_context=l,prices={"AAA":1})
