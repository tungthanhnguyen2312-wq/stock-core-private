"""Synthetic-fixture tests for PORTFOLIO_AWARE_DECISION_AND_RISK_SIZING_V1.

No real private portfolio values appear anywhere in this file -- every account, position, and
policy figure below is fabricated for test purposes only.
"""
from __future__ import annotations

import portfolio_aware_decision as pad


DEFAULT_POLICY = {
    "risk_budget_per_investment_decision_to_nav": "0.01",
    "max_single_position_weight": "0.30",
    "max_sector_weight": "0.45",
    "max_gross_exposure_to_nav": "1.15",
    "max_margin_debt_to_nav": "0.15",
    "minimum_cash_reserve_to_nav": "0.05",
    "max_margin_rate_percent_for_new_leveraged_exposure": "15.0",
    "probe_risk_budget_multiplier": "0.50",
    "tactical_margin_holding_days": "30",
    "min_net_reward_risk_for_margin": "2.0",
    "strong_net_reward_risk_for_max_margin": "3.0",
    "max_financing_cost_fraction_of_gross_upside": "0.20",
}


def make_position(ticker, quantity, cost_basis=None, breakeven=None):
    return {
        "ticker": ticker,
        "current_quantity": str(quantity),
        "current_position_cost_basis_per_share": None if cost_basis is None else str(cost_basis),
        "current_position_cost_basis_method": "WEIGHTED_AVERAGE_CARRYING_COST" if cost_basis is not None else None,
        "lifetime_cash_recovery_breakeven": None if breakeven is None else str(breakeven),
        "lifetime_cash_recovery_breakeven_method": "LIFETIME_NET_CASH_OUTFLOW_PER_CURRENT_SHARE" if breakeven is not None else None,
        "position_episode_holding_days": 42,
    }


def make_snapshot(*, positions=None, account=None, policy=None, as_of_date="2026-09-08"):
    account_fields = {
        "as_of_date": as_of_date, "currency": "VND",
        "cash_available": None, "cash_reserved": None, "margin_debt": None,
        "margin_available_minimum": None, "margin_available_maximum": None,
        "annual_margin_rate_percent": None, "accrued_margin_interest": None,
        "net_asset_value": None, "gross_market_value": None,
    }
    account_fields.update(account or {})
    effective_fields = dict(DEFAULT_POLICY)
    effective_fields.update(policy or {})
    return {
        "schema_version": "portfolio_snapshot_v1",
        "contract_version": "portfolio_snapshot/v1",
        "artifact_identity": "portfolio_snapshot:synthetic-test",
        "snapshot_as_of_date": as_of_date,
        "positions": positions or [],
        "account_snapshot": {"fields": account_fields},
        "portfolio_policy": {"effective_fields": effective_fields},
    }


def make_security_decision(ticker, posture, *, trigger_level=None, invalidation_level=None,
                            counter_thesis=None, material_uncertainties=None, as_of_session="2026-09-08"):
    return {
        "ticker": ticker, "as_of_session": as_of_session, "research_action_posture": posture,
        "trigger": {"trigger_level": trigger_level, "trigger_type": "STRUCTURAL" if trigger_level else "NO_TRIGGER"},
        "invalidation": {"invalidation_level": invalidation_level},
        "counter_thesis": counter_thesis or [], "material_uncertainties": material_uncertainties or [],
        "decision_identity": f"decision:{ticker}:test-{posture}",
    }


def decide(ticker, snapshot, decision, *, prices=None, sector_by_ticker=None, position_lanes=None,
           excluded_tickers=None, position_lane=None, reward_boundary=None):
    state = pad.derive_portfolio_state(
        portfolio_snapshot=snapshot, prices=prices, sector_by_ticker=sector_by_ticker,
        position_lanes=position_lanes, excluded_tickers=excluded_tickers,
    )
    return pad.build_ticker_portfolio_aware_decision(
        ticker=ticker, portfolio_state=state, security_decision=decision, position_lane=position_lane,
        reward_boundary=reward_boundary,
    )


# ── 1. New position ─────────────────────────────────────────────────────────────

def test_01_new_position_sizes_a_fresh_add():
    snapshot = make_snapshot(account={"cash_available": "100000000", "net_asset_value": "100000000"})
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=50, invalidation_level=45)
    record = decide("AAA", snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"})
    assert record["position_state"] == "NOT_HELD"
    assert record["sizing_mode"] == "FULL_RISK_BUDGET"
    assert record["portfolio_action_research"] == "ADD_WITHIN_RISK_CEILING"
    assert record["portfolio_constraint_completeness"] == "FULL"
    assert record["portfolio_risk_quantity_ceiling"] == 200000  # 100e6*0.01/5
    assert record["binding_constraint"] == "NONE"
    assert record["execution_qualified_quantity_status"] == "NOT_EVALUATED"
    assert record["execution_qualified_quantity"] is None
    assert record["portfolio_risk_sizing"]["portfolio_risk_quantity_ceiling"] == 200000


# ── 2. Existing position with add room ──────────────────────────────────────────

def test_02_existing_position_with_room_still_sizes_the_add():
    snapshot = make_snapshot(
        positions=[make_position("AAA", 1000, cost_basis=40)],
        account={"cash_available": "50000000", "net_asset_value": "100000000"},
    )
    decision = make_security_decision("AAA", "ACCUMULATE_ON_RETEST", trigger_level=50, invalidation_level=45)
    record = decide("AAA", snapshot, decision, prices={"AAA": 48}, sector_by_ticker={"AAA": "TECHNOLOGY"})
    assert record["position_state"] == "HELD"
    assert record["portfolio_action_research"] == "ADD_WITHIN_RISK_CEILING"
    assert record["cost_basis_context"]["cost_basis_per_share"] == 40.0


# ── 3. Existing position above max weight -> signal valid, no add ──────────────

def test_03_existing_position_above_cap_is_review_not_sell():
    snapshot = make_snapshot(
        positions=[make_position("AAA", 1000000, cost_basis=40)],
        account={"cash_available": "10000000", "net_asset_value": "100000000"},
    )
    decision = make_security_decision("AAA", "ACCUMULATE_ON_RETEST", trigger_level=50, invalidation_level=45)
    record = decide("AAA", snapshot, decision, prices={"AAA": 40}, sector_by_ticker={"AAA": "TECHNOLOGY"})
    assert record["position_state"] == "HELD_ABOVE_POLICY_CAP"
    assert record["portfolio_action_research"] == "OVER_LIMIT_REVIEW"
    assert record["security_research_action_posture"] == "ACCUMULATE_ON_RETEST"  # thesis untouched
    assert "no_forced_liquidation" in record["authority_boundary"]
    assert record["authority_boundary"]["existing_exposure_above_cap_is_no_new_addition_not_an_automatic_sell"] is True


# ── 4. Sector cap ────────────────────────────────────────────────────────────────

def test_04_sector_cap_blocks_the_add():
    snapshot = make_snapshot(
        positions=[make_position("BBB", 1000000)],
        account={"cash_available": "50000000", "net_asset_value": "100000000"},
    )
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=50, invalidation_level=45)
    record = decide(
        "AAA", snapshot, decision, prices={"BBB": 50, "AAA": 50},
        sector_by_ticker={"AAA": "TECHNOLOGY", "BBB": "TECHNOLOGY"},
    )
    assert record["sector_constraint"]["status"] == "LIMIT_BREACH"
    assert record["portfolio_action_research"] == "NO_ADD"
    assert record["binding_constraint"] == "SECTOR"


# ── 5. Insufficient cash ─────────────────────────────────────────────────────────

def test_05_insufficient_cash_reserve_blocks_the_add():
    snapshot = make_snapshot(account={"cash_available": "1000000", "net_asset_value": "100000000"})
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=50, invalidation_level=45)
    record = decide("AAA", snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"})
    assert record["cash_reserve_constraint"]["status"] == "LIMIT_BREACH"
    assert record["portfolio_action_research"] == "NO_ADD"
    assert record["binding_constraint"] == "CASH_RESERVE"


# ── 6. Probe with half risk budget ──────────────────────────────────────────────

def test_06_probe_uses_half_the_normal_risk_budget():
    snapshot = make_snapshot(account={"cash_available": "100000000", "net_asset_value": "100000000"})
    full_decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=100, invalidation_level=90)
    probe_decision = make_security_decision("BBB", "EARLY_WATCH", trigger_level=100, invalidation_level=90)
    full_record = decide("AAA", snapshot, full_decision, sector_by_ticker={"AAA": "TECHNOLOGY"})
    probe_record = decide("BBB", snapshot, probe_decision, sector_by_ticker={"BBB": "TECHNOLOGY"})
    assert full_record["sizing_mode"] == "FULL_RISK_BUDGET"
    assert probe_record["sizing_mode"] == "PROBE_RISK_BUDGET"
    assert probe_record["portfolio_action_research"] == "PROBE_WITHIN_RISK_CEILING"
    assert probe_record["portfolio_risk_quantity_ceiling"] == full_record["portfolio_risk_quantity_ceiling"] // 2
    assert probe_record["portfolio_risk_sizing"]["probe_risk_budget_multiplier_applied"] == 0.5


def test_06b_probe_is_never_manufactured_from_a_non_early_watch_posture():
    snapshot = make_snapshot(account={"cash_available": "100000000", "net_asset_value": "100000000"})
    decision = make_security_decision("AAA", "WAIT_FOR_CONFIRMATION", trigger_level=100, invalidation_level=90)
    record = decide("AAA", snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"})
    assert record["sizing_mode"] == "NOT_APPLICABLE"
    assert record["portfolio_action_research"] == "NO_ADD"


def test_06c_probe_requires_a_deterministic_invalidation_not_just_the_posture():
    snapshot = make_snapshot(account={"cash_available": "100000000", "net_asset_value": "100000000"})
    decision = make_security_decision("AAA", "EARLY_WATCH", trigger_level=100, invalidation_level=None)
    record = decide("AAA", snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"})
    assert record["sizing_mode"] == "NOT_APPLICABLE"


# ── 7. Invalidation missing ─────────────────────────────────────────────────────

def test_07_missing_invalidation_blocks_sizing_not_the_whole_decision():
    snapshot = make_snapshot(account={"cash_available": "100000000", "net_asset_value": "100000000"})
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=50, invalidation_level=None)
    record = decide("AAA", snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"})
    assert record["risk_sizing_status"] == "UNAVAILABLE_MISSING_INVALIDATION"
    assert record["portfolio_action_research"] == "ADD_ELIGIBLE_SIZING_UNAVAILABLE"
    assert record["portfolio_risk_quantity_ceiling"] is None


# ── 8. Cash-only tactical trade ──────────────────────────────────────────────────

def test_08_cash_only_tactical_trade_has_no_margin_capacity_needed():
    snapshot = make_snapshot(account={"cash_available": "100000000", "net_asset_value": "100000000"})
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=50, invalidation_level=45)
    record = decide("AAA", snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"})
    assert record["cash_funding_capacity"]["status"] == "AVAILABLE"
    assert record["cash_funding_capacity"]["max_cash_fundable_quantity"] >= record["portfolio_risk_quantity_ceiling"]
    assert record["margin_economics"]["status"] == "NOT_EVALUATED"
    assert record["margin_economics"]["reason_code"] == "NO_QUALIFIED_UPSIDE_OR_REWARD_BASIS_UPSTREAM"


# ── 9. Margin below economic hurdle -> NO_MARGIN ────────────────────────────────

def test_09_margin_below_economic_hurdle_is_no_margin():
    snapshot = make_snapshot(account={
        "cash_available": "100000000", "net_asset_value": "100000000",
        "margin_available_minimum": "10000000", "margin_available_maximum": "50000000",
        "annual_margin_rate_percent": "13.5",
    })
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=50, invalidation_level=45)
    # gross upside 3/share vs downside 5/share -> net R/R well under 2.0 even before financing cost.
    record = decide("AAA", snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"}, reward_boundary=53.0)
    me = record["margin_economics"]
    assert me["status"] == "EVALUATED"
    assert me["margin_research_band"] == "NO_MARGIN"
    assert me["reason_code"] == "BELOW_MIN_NET_REWARD_RISK_ECONOMICS"
    assert me["research_capacity"]["final_margin_research_capacity_quantity"] == 0


# ── 10. MIN margin band ──────────────────────────────────────────────────────────

def test_10_min_margin_band_at_exactly_the_qualifying_threshold():
    snapshot = make_snapshot(account={
        "cash_available": "100000000", "net_asset_value": "1000000000",
        "margin_available_minimum": "10000000", "margin_available_maximum": "50000000",
        "annual_margin_rate_percent": "0",
    })
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=100, invalidation_level=90)
    # No financing cost (rate 0): net R/R = gross_upside/downside = 20/10 = 2.0 exactly.
    record = decide("AAA", snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"}, reward_boundary=120.0)
    me = record["margin_economics"]
    assert me["status"] == "EVALUATED"
    assert abs(me["calculation"]["net_reward_risk"] - 2.0) < 1e-6
    assert me["margin_research_band"] == "INTERPOLATED_MIN_TO_MAX"
    assert me["research_capacity"]["capacity_before_portfolio_caps_notional"] == 10000000.0


# ── 11. Interpolation MIN -> MAX ─────────────────────────────────────────────────

def test_11_interpolated_margin_band_between_min_and_max():
    snapshot = make_snapshot(account={
        "cash_available": "100000000", "net_asset_value": "1000000000",
        "margin_available_minimum": "10000000", "margin_available_maximum": "50000000",
        "annual_margin_rate_percent": "0",
    })
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=100, invalidation_level=90)
    # net R/R = 25/10 = 2.5 -> halfway between 2.0 and 3.0.
    record = decide("AAA", snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"}, reward_boundary=125.0)
    me = record["margin_economics"]
    assert me["margin_research_band"] == "INTERPOLATED_MIN_TO_MAX"
    assert abs(me["research_capacity"]["capacity_before_portfolio_caps_notional"] - 30000000.0) < 1.0


# ── 12. MAX band ──────────────────────────────────────────────────────────────────

def test_12_max_band_for_strong_economics():
    snapshot = make_snapshot(account={
        "cash_available": "100000000", "net_asset_value": "1000000000",
        "margin_available_minimum": "10000000", "margin_available_maximum": "50000000",
        "annual_margin_rate_percent": "0",
    })
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=100, invalidation_level=90)
    # net R/R = 40/10 = 4.0 -> strong, clamps to MAX.
    record = decide("AAA", snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"}, reward_boundary=140.0)
    me = record["margin_economics"]
    assert me["margin_research_band"] == "MAX_BAND"
    assert me["research_capacity"]["capacity_before_portfolio_caps_notional"] == 50000000.0


# ── 13. Financing cost makes a formerly attractive trade ineligible ────────────

def test_13_financing_cost_disqualifies_a_high_rate_trade():
    low_rate_snapshot = make_snapshot(account={
        "cash_available": "100000000", "net_asset_value": "1000000000",
        "margin_available_minimum": "10000000", "margin_available_maximum": "50000000",
        "annual_margin_rate_percent": "0",
    })
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=100, invalidation_level=90)
    # gross upside 25/share vs downside 10/share -> net R/R 2.5 at zero financing cost: qualifies.
    low_rate_record = decide("AAA", low_rate_snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"}, reward_boundary=125.0)
    assert low_rate_record["margin_economics"]["margin_research_band"] in ("INTERPOLATED_MIN_TO_MAX", "MAX_BAND")

    high_rate_snapshot = make_snapshot(account={
        "cash_available": "100000000", "net_asset_value": "1000000000",
        "margin_available_minimum": "10000000", "margin_available_maximum": "50000000",
        "annual_margin_rate_percent": "180",  # extreme rate: financing cost swallows the gross upside.
    })
    high_rate_record = decide("AAA", high_rate_snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"}, reward_boundary=125.0)
    me = high_rate_record["margin_economics"]
    assert me["margin_research_band"] == "NO_MARGIN"
    assert me["reason_code"] in ("FINANCING_COST_EXCEEDS_POLICY_MAX_FRACTION_OF_GROSS_UPSIDE", "BELOW_MIN_NET_REWARD_RISK_ECONOMICS")
    assert me["research_capacity"]["final_margin_research_capacity_quantity"] == 0


# ── 14. Max-margin-debt cap ───────────────────────────────────────────────────────

def test_14_margin_debt_cap_zeroes_out_margin_research_capacity():
    snapshot = make_snapshot(account={
        "cash_available": "100000000", "net_asset_value": "1000000000",
        "margin_debt": "150000000",  # already at the 15% NAV cap.
        "margin_available_minimum": "10000000", "margin_available_maximum": "50000000",
        "annual_margin_rate_percent": "0",
    })
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=100, invalidation_level=90)
    record = decide("AAA", snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"}, reward_boundary=140.0)
    assert record["margin_debt_constraint"]["status"] in ("AT_LIMIT", "LIMIT_BREACH")
    me = record["margin_economics"]
    assert me["research_capacity"]["final_margin_research_capacity_quantity"] == 0
    assert "MARGIN_DEBT" in me["research_capacity"]["capped_by"]


# ── 15. Gross exposure cap ────────────────────────────────────────────────────────

def test_15_gross_exposure_cap_blocks_the_add():
    snapshot = make_snapshot(
        positions=[make_position("BBB", 2400000)],
        account={"cash_available": "10000000", "net_asset_value": "100000000"},
    )
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=50, invalidation_level=45)
    record = decide(
        "AAA", snapshot, decision, prices={"BBB": 50, "AAA": 50},
        sector_by_ticker={"AAA": "TECHNOLOGY", "BBB": "INDUSTRIALS"},
    )
    assert record["gross_exposure_constraint"]["status"] == "LIMIT_BREACH"
    assert record["portfolio_action_research"] == "NO_ADD"
    assert record["binding_constraint"] == "GROSS_EXPOSURE"


# ── 16. Excluded position does not affect active workflow ──────────────────────

def test_16_excluded_position_is_inactive_and_does_not_count_toward_exposure():
    snapshot = make_snapshot(
        positions=[make_position("BBB", 9000)],
        account={"cash_available": "50000000", "net_asset_value": "100000000"},
    )
    decision_bbb = make_security_decision("BBB", "HOLD")
    decision_aaa = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=50, invalidation_level=45)
    excluded_record = decide(
        "BBB", snapshot, decision_bbb, prices={"BBB": 50}, sector_by_ticker={"BBB": "TECHNOLOGY"},
        excluded_tickers=["BBB"],
    )
    assert excluded_record["position_state"] == "EXCLUDED_INACTIVE"
    assert excluded_record["portfolio_action_research"] == "EXCLUDED_FROM_ACTIVE_PORTFOLIO"

    unrelated_record = decide(
        "AAA", snapshot, decision_aaa, prices={"BBB": 50, "AAA": 50},
        sector_by_ticker={"AAA": "TECHNOLOGY", "BBB": "TECHNOLOGY"}, excluded_tickers=["BBB"],
    )
    # With BBB excluded, its 4.5B VND sector exposure no longer counts against AAA's sector cap.
    assert unrelated_record["sector_constraint"]["status"] == "WITHIN_LIMIT"
    assert unrelated_record["portfolio_action_research"] == "ADD_WITHIN_RISK_CEILING"


# ── 17. No execution qualification when liquidity authority is absent ──────────

def test_17_execution_qualified_quantity_is_always_not_qualified():
    snapshot = make_snapshot(account={"cash_available": "100000000", "net_asset_value": "100000000"})
    for posture in ("INITIATE_ON_BREAKOUT", "EARLY_WATCH", "HOLD", "AVOID"):
        decision = make_security_decision("AAA", posture, trigger_level=50, invalidation_level=45)
        record = decide("AAA", snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"})
        assert record["execution_qualified_quantity"] is None
        assert record["execution_qualified_quantity_status"] == "NOT_EVALUATED"
        assert record["authority_boundary"]["is_actionable"] is False


# ── 18. Deterministic / idempotent private artifacts ────────────────────────────

def test_18_artifact_is_deterministic_and_idempotent():
    snapshot = make_snapshot(
        positions=[make_position("AAA", 1000, cost_basis=40)],
        account={"cash_available": "50000000", "net_asset_value": "100000000"},
    )
    state = pad.derive_portfolio_state(portfolio_snapshot=snapshot, prices={"AAA": 48}, sector_by_ticker={"AAA": "TECHNOLOGY"})
    integrated = {
        "artifact_identity": "integrated_investment_decision_product:test",
        "records": {"AAA": make_security_decision("AAA", "ACCUMULATE_ON_RETEST", trigger_level=50, invalidation_level=45)},
    }
    first = pad.build_artifact(session="2026-09-08", requested_at="2026-09-08T00:00:00", portfolio_state=state, integrated_decision_artifact=integrated)
    second = pad.build_artifact(session="2026-09-08", requested_at="2026-09-08T00:00:00", portfolio_state=state, integrated_decision_artifact=integrated)
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["records"]["AAA"]["portfolio_decision_identity"] == second["records"]["AAA"]["portfolio_decision_identity"]


def test_18b_public_console_summary_has_no_private_values():
    snapshot = make_snapshot(
        positions=[make_position("AAA", 1000, cost_basis=40)],
        account={"cash_available": "50000000", "net_asset_value": "100000000", "margin_debt": "1000000"},
    )
    state = pad.derive_portfolio_state(portfolio_snapshot=snapshot, prices={"AAA": 48}, sector_by_ticker={"AAA": "TECHNOLOGY"})
    integrated = {
        "artifact_identity": "integrated_investment_decision_product:test",
        "records": {"AAA": make_security_decision("AAA", "ACCUMULATE_ON_RETEST", trigger_level=50, invalidation_level=45)},
    }
    artifact = pad.build_artifact(session="2026-09-08", requested_at="2026-09-08T00:00:00", portfolio_state=state, integrated_decision_artifact=integrated)
    summary = pad.public_console_summary(artifact)
    forbidden_keys = {
        "current_quantity", "current_weight", "cost_basis_per_share", "cash_available",
        "margin_debt", "net_asset_value", "entry_reference_price", "portfolio_risk_quantity_ceiling",
    }
    assert forbidden_keys.isdisjoint(summary.keys())
    blob = str(summary)
    # Distinctive private magnitudes (unlikely to coincidentally appear inside an unrelated
    # sha256 hex digest) must never leak into the console-safe summary.
    for forbidden in ("50000000", "1000000"):
        assert forbidden not in blob


# ── Portfolio-fit adapter (unwired demonstration) ───────────────────────────────

def test_19_portfolio_fit_adapter_reflects_concentration_and_sector_overlap():
    snapshot = make_snapshot(
        positions=[make_position("AAA", 1000000)],
        account={"cash_available": "10000000", "net_asset_value": "100000000"},
    )
    state = pad.derive_portfolio_state(portfolio_snapshot=snapshot, prices={"AAA": 40}, sector_by_ticker={"AAA": "TECHNOLOGY"})
    fit = pad.project_portfolio_fit_for_integrated_decision(state, "AAA")
    assert fit["status"] == "AVAILABLE"
    assert fit["is_held"] is True
    assert fit["concentration_flag"] is True


def test_20_not_provided_portfolio_state_is_honest_not_a_forced_wait():
    state = pad.derive_portfolio_state(portfolio_snapshot=None)
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=50, invalidation_level=45)
    record = pad.build_ticker_portfolio_aware_decision(ticker="AAA", portfolio_state=state, security_decision=decision)
    assert record["portfolio_action_research"] == "NOT_EVALUATED"
    # The security's own posture is preserved untouched even with no private state.
    assert record["security_research_action_posture"] == "INITIATE_ON_BREAKOUT"
    assert record["margin_economics"]["status"] == "NOT_APPLICABLE"


# ── 21. Bounded, optional EMPIRICAL_SETUP_OUTCOME_CALIBRATION_V1 research hook ──────────────

def test_21_empirical_reward_context_defaults_to_not_applicable():
    snapshot = make_snapshot(account={"cash_available": "100000000", "net_asset_value": "100000000"})
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=50, invalidation_level=45)
    record = decide("AAA", snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"})
    assert record["empirical_reward_context"]["status"] == "NOT_APPLICABLE"


def test_21b_empirical_reward_context_attaches_without_changing_execution_or_margin_authority():
    import empirical_setup_outcome_calibration as calib

    observations = [
        {
            "ticker": f"T{ticker}", "t0_session": f"2026-01-{session + 1:02d}",
            "research_action_posture_at_t0": "INITIATE_ON_BREAKOUT", "tactical_structure_state_at_t0": "INSUFFICIENT_HISTORY",
            "invalidation_method_at_t0": "CONFIRMED_SWING_LEVEL_OR_SUPPORT_FALLBACK", "market_regime_at_t0": "NEUTRAL_MIXED",
            "r_multiple_denominator_status": "AVAILABLE",
            "horizons": {name: {
                "required_completed_future_sessions": sessions, "status": "MATURE", "maturation_state": "MATURED",
                "forward_return": 0.05, "mfe_close_proxy": 0.05, "mae_close_proxy": -0.02,
                "close_path_semantics": "CLOSE_ONLY_NOT_INTRADAY_MFE_MAE", "r_multiple": 0.5, "r_multiple_status": "AVAILABLE",
            } for name, sessions in calib.HORIZONS.items()},
            "invalidation": {"status": "NOT_SATISFIED_YET", "hit": False, "event_session": None, "sessions_to_invalidation": None, "condition_identity": None},
            "target": {"status": calib.NOT_EVALUATED, "hit": None, "event_session": None, "sessions_to_target": None, "reason": "TEST"},
            "target_invalidation_ordering": calib.NOT_EVALUATED,
            "observation_identity": f"empirical_setup_observation:test:{ticker}:{session}",
            "authority_boundary": {},
        }
        for session in range(10) for ticker in range(5)
    ]
    calibration_artifact = {"artifact_identity": "test-calibration", "cohorts": calib.aggregate_cohorts(observations)}

    snapshot = make_snapshot(account={"cash_available": "100000000", "net_asset_value": "100000000"})
    decision = make_security_decision("AAA", "INITIATE_ON_BREAKOUT", trigger_level=50, invalidation_level=45)
    decision["market_structure_state"] = "INSUFFICIENT_HISTORY"
    decision["invalidation"]["invalidation_method"] = "CONFIRMED_SWING_LEVEL_OR_SUPPORT_FALLBACK"
    without_hook = decide("AAA", snapshot, decision, sector_by_ticker={"AAA": "TECHNOLOGY"})
    state = pad.derive_portfolio_state(portfolio_snapshot=snapshot, sector_by_ticker={"AAA": "TECHNOLOGY"})
    with_hook = pad.build_ticker_portfolio_aware_decision(
        ticker="AAA", portfolio_state=state, security_decision=decision, calibration_artifact=calibration_artifact,
    )

    assert with_hook["empirical_reward_context"]["status"] == "AVAILABLE"
    assert with_hook["empirical_reward_context"]["authority_boundary"]["is_not_execution_authority"] is True
    # Execution/margin authority and sizing are byte-identical whether or not the hook fires.
    assert with_hook["execution_qualified_quantity"] == without_hook["execution_qualified_quantity"]
    assert with_hook["execution_qualified_quantity_status"] == without_hook["execution_qualified_quantity_status"]
    assert with_hook["margin_economics"]["status"] == without_hook["margin_economics"]["status"]
    assert with_hook["portfolio_risk_quantity_ceiling"] == without_hook["portfolio_risk_quantity_ceiling"]
    assert with_hook["portfolio_action_research"] == without_hook["portfolio_action_research"]
