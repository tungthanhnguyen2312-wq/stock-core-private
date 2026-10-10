from __future__ import annotations

from copy import deepcopy

import pytest

import stocklookup_core.portfolio.execution_capacity_research as capacity
import stocklookup_core.portfolio.portfolio_aware_decision as portfolio


SESSION = "2026-09-28"


def _official(*, adtv="1000000", exchange="HOSE", exact=True, current=True,
              coverage_class="EXACT_20_SESSION_WINDOW", reasons=None):
    return {
        "ticker": "AAA",
        "route_exchange": exchange,
        "coverage": {"coverage_class": coverage_class, "reason_codes": reasons or [], "labels": []},
        "fitness": {
            "CURRENT_SESSION_LIQUIDITY_RESEARCH": {"state": "ELIGIBLE" if current else "BLOCKED"},
            "ADTV_RESEARCH": {"state": "ELIGIBLE" if exact else "BLOCKED"},
        },
        "research_view": {
            "current_session": {"session": SESSION},
            "adtv20_matched_all_vnd": {"status": "EXACT_WINDOW" if exact else "UNAVAILABLE", "value": adtv if exact else None},
            "fitness": {"CURRENT_SESSION_LIQUIDITY_RESEARCH": "ELIGIBLE" if current else "BLOCKED", "ADTV_RESEARCH": "ELIGIBLE" if exact else "BLOCKED"},
            "reason_codes": reasons or [],
        },
        "evidence_refs": {"source": "OFFICIAL_TEST_FIXTURE", "responses": []},
    }


def _policy(**overrides):
    values = dict(max_participation_of_adtv20="0.125", max_days_to_liquidate=3,
                  board_lot_shares_by_exchange={"HOSE": 100}, policy_version="TEST_POLICY_V1",
                  policy_source="SYNTHETIC_TEST")
    values.update(overrides)
    return capacity.build_policy(**values)


def test_capacity_decimal_arithmetic_identity_and_policy_epoch():
    policy = _policy()
    first = capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=_official(),
                                    policy=policy, current_price="1250", price_identity="price:test")
    second = capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=_official(),
                                     policy=policy, current_price="1250", price_identity="price:test")
    assert first["capacity_notional_vnd"] == "375000"
    assert first["capacity_shares_lot_rounded"] == 300
    assert first["artifact_identity"] == second["artifact_identity"]
    changed = _policy(max_participation_of_adtv20="0.1", policy_version="TEST_POLICY_V2")
    third = capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=_official(),
                                    policy=changed, current_price="1250", price_identity="price:test")
    assert third["artifact_identity"] != first["artifact_identity"]
    assert capacity.compare_policy_epochs(policy, changed)["state"] == "NOT_COMPARABLE_POLICY_CHANGE"
    version_only = _policy(policy_version="TEST_POLICY_V2")
    version_envelope = capacity.build_envelope(
        ticker="AAA", session=SESSION, official_liquidity_record=_official(), policy=version_only,
        current_price="1250", price_identity="price:test",
    )
    assert version_envelope["capacity_notional_vnd"] == first["capacity_notional_vnd"]
    assert version_envelope["artifact_identity"] != first["artifact_identity"]


def test_zero_trading_is_available_zero_not_missing():
    envelope = capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=_official(adtv="0"),
                                       policy=_policy(), current_price="1250", price_identity="price:test")
    assert envelope["state"] == "AVAILABLE"
    assert envelope["capacity_notional_vnd"] == "0"
    assert envelope["capacity_shares_lot_rounded"] == 0
    assert envelope["reason_codes"] == ["ZERO_TRADING_VALID", "ILLIQUID_ZERO_ADTV"]


def test_incomplete_window_and_current_only_never_fabricate_capacity():
    record = _official(exact=False, current=True, coverage_class="PARTIAL_WINDOW", reasons=["SERIES_STARTS_INSIDE_WINDOW"])
    envelope = capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=record,
                                       policy=_policy(), current_price="1250")
    assert envelope["state"] == "PARTIAL"
    assert envelope["capacity_notional_vnd"] is None
    assert "CURRENT_LIQUIDITY_ONLY_NO_ADTV" in envelope["reason_codes"]
    assert "SERIES_STARTS_INSIDE_WINDOW" in envelope["reason_codes"]


def test_exact_feature_without_exact_coverage_or_adtv_fitness_fails_closed():
    record = _official(coverage_class="PARTIAL_WINDOW")
    assert capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=record,
                                   policy=_policy())["capacity_notional_vnd"] is None
    record = _official()
    record["fitness"]["ADTV_RESEARCH"]["state"] = "BLOCKED"
    assert capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=record,
                                   policy=_policy())["capacity_notional_vnd"] is None


def test_policy_unbound_and_validation_domains():
    envelope = capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=_official(),
                                       policy=capacity.canonical_unbound_policy())
    assert envelope["state"] == "BLOCKED" and envelope["reason_codes"] == ["POLICY_UNBOUND"]
    with pytest.raises(capacity.ExecutionCapacityPolicyError):
        capacity.build_policy(max_participation_of_adtv20="0", max_days_to_liquidate=1)
    with pytest.raises(capacity.ExecutionCapacityPolicyError):
        capacity.build_policy(max_participation_of_adtv20="0.1", max_days_to_liquidate=21)


def test_lot_rounding_and_unbound_lot_keep_notional():
    bound = capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=_official(),
                                    policy=_policy(), current_price="1100", price_identity="price:test")
    assert bound["capacity_shares_lot_rounded"] == 300
    no_lot = capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=_official(),
                                     policy=_policy(board_lot_shares_by_exchange={}), current_price="1100", price_identity="price:test")
    assert no_lot["capacity_notional_vnd"] == "375000"
    assert no_lot["capacity_shares_lot_rounded"] is None
    assert no_lot["state"] == "PARTIAL" and "LOT_RULE_UNBOUND" in no_lot["reason_codes"]


@pytest.mark.parametrize("exchange", ["HNX", "UPCOM"])
def test_unauthorized_hnx_upcom_reason(exchange):
    record = _official(exchange=exchange, exact=False, current=False, coverage_class="PUBLIC_ACQUISITION_NOT_AUTHORIZED")
    envelope = capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=record,
                                       policy=_policy(board_lot_shares_by_exchange={exchange: 100}))
    assert envelope["state"] == "BLOCKED"
    assert envelope["reason_codes"] == ["PUBLIC_ACQUISITION_NOT_AUTHORIZED"]


def test_route_conflict_and_historical_use_fail_closed():
    conflict = _official(exact=False, current=False, coverage_class="EXCHANGE_IDENTITY_CONFLICT")
    assert capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=conflict,
                                   policy=_policy())["reason_codes"] == ["EXCHANGE_IDENTITY_CONFLICT"]
    historical = capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=_official(),
                                         policy=_policy(), historical_t0_use=True)
    assert historical["state"] == "BLOCKED" and historical["reason_codes"] == ["PIT_REQUIRED_HISTORICAL_USE"]


def _constraint(value):
    return {"remaining_quantity": value, "status": "WITHIN_LIMIT" if value is not None else "NOT_EVALUATED"}


def test_private_size_minimum_missing_invalidation_degenerate_and_no_atr_substitution():
    public = capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=_official(adtv="100000000"),
                                     policy=_policy(), current_price="1000", price_identity="price:test")
    risk = portfolio._compute_risk_sizing(entry_price=1000, invalidation_price=990, effective_nav=1_000_000,
                                          risk_budget_fraction=0.01)
    envelope = portfolio._research_size_envelope(
        risk_sizing=risk, execution_capacity_envelope=public,
        single_constraint=_constraint(2000), sector_constraint=_constraint(1500), gross_constraint=_constraint(1800),
        sizing_policy_version="SYNTHETIC_V3", portfolio_state_identity="private:test", security_decision_identity="decision:test",
    )
    assert envelope["risk_cap_shares"] == 1000
    assert envelope["liquidity_cap_shares"] == 37500
    assert envelope["concentration_cap_shares"] == 1500
    assert envelope["research_size_envelope_shares"] == 1000
    assert envelope["binding_constraint"] == "RISK_CAP" and envelope["completeness"] == "FULL"
    assert envelope["execution_qualified_quantity_status"] == "NOT_QUALIFIED"
    prior_epoch = portfolio._research_size_envelope(
        risk_sizing=risk, execution_capacity_envelope=public,
        single_constraint=_constraint(2000), sector_constraint=_constraint(1500), gross_constraint=_constraint(1800),
        sizing_policy_version="SYNTHETIC_V2", portfolio_state_identity="private:test", security_decision_identity="decision:test",
    )
    assert prior_epoch["artifact_identity"] != envelope["artifact_identity"]

    missing = portfolio._compute_risk_sizing(entry_price=1000, invalidation_price=None, effective_nav=1_000_000,
                                             risk_budget_fraction=0.01)
    partial = portfolio._research_size_envelope(
        risk_sizing=missing, execution_capacity_envelope=public,
        single_constraint=_constraint(2000), sector_constraint=_constraint(1500), gross_constraint=_constraint(1800),
        sizing_policy_version="SYNTHETIC_V3", portfolio_state_identity="private:test", security_decision_identity="decision:test",
    )
    assert partial["risk_cap_shares"] is None and partial["completeness"] == "PARTIAL"
    assert "UNAVAILABLE_MISSING_INVALIDATION" in partial["reason_codes"]
    # No ATR argument or fallback exists; a caller cannot turn technical geometry into a stop.
    assert "atr" not in portfolio._compute_risk_sizing.__code__.co_varnames

    degenerate = portfolio._compute_risk_sizing(entry_price=1000, invalidation_price=1000, effective_nav=1_000_000,
                                                risk_budget_fraction=0.01)
    assert degenerate["status"] == "UNAVAILABLE_DEGENERATE_DOWNSIDE"


def test_use_specific_authority_never_opens_live_or_pit_uses():
    matrix = capacity.use_specific_authority(capacity_state=capacity.AVAILABLE, private_size_state=capacity.PARTIAL)
    assert matrix[capacity.CURRENT_SESSION_EXECUTION_CAPACITY_RESEARCH] == "ELIGIBLE"
    assert matrix[capacity.CURRENT_SESSION_RISK_SIZE_RESEARCH] == "PARTIAL"
    assert all(matrix[name] == "BLOCKED" for name in (
        capacity.LIVE_POSITION_SIZING, capacity.PORTFOLIO_CAPITAL_ALLOCATION,
        capacity.HISTORICAL_PIT_SIZE_REPLAY, capacity.PIT_BACKTEST, capacity.EXECUTION_REPLAY,
    ))


def test_public_envelope_contains_no_private_fields_and_is_deterministic():
    envelope = capacity.build_envelope(ticker="AAA", session=SESSION, official_liquidity_record=_official(),
                                       policy=_policy(), current_price="1250")
    text = capacity._canonical(envelope).lower()
    assert all(token not in text for token in ("net_asset_value", "holdings", "cost_basis", "account_alias", "intended_order_size"))
    assert set(envelope["forbidden_uses"]) == set(capacity.FORBIDDEN_USES)


def test_private_policy_binding_through_portfolio_builder_remains_research_only():
    from tests.test_portfolio_aware_decision import make_security_decision, make_snapshot
    snapshot = make_snapshot(
        account={"cash_available": "100000000", "net_asset_value": "100000000"},
        policy={"max_participation_of_adtv20": "0.125", "max_days_to_liquidate": "3"},
    )
    state = portfolio.derive_portfolio_state(portfolio_snapshot=snapshot, prices={"AAA": 50})
    official = {
        "contract_version": "official_exchange_liquidity_research/v1",
        "resolved_completed_session": SESSION,
        "artifact_identity": "official_exchange_liquidity_research:synthetic",
        "records": {"AAA": _official(adtv="100000000")},
    }
    integrated = {"artifact_identity": "integrated:test", "records": {
        "AAA": make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=50,
                                      invalidation_level=45, as_of_session=SESSION),
    }}
    artifact = portfolio.build_artifact(
        session=SESSION, requested_at="2026-09-28T00:00:00", portfolio_state=state,
        integrated_decision_artifact=integrated, official_liquidity_artifact=official,
        capacity_price_by_ticker={"AAA": 50}, capacity_price_identity="price:synthetic",
    )
    size = artifact["records"]["AAA"]["research_size_envelope"]
    assert size["policy_identity"].startswith("execution_capacity_policy:")
    assert size["liquidity_cap_shares"] is None  # no qualified board-lot rule
    assert "LOT_RULE_UNBOUND" in size["reason_codes"]
    assert size["execution_qualified_quantity_status"] == "NOT_QUALIFIED"
