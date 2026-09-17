"""Tests for PERSONAL_PORTFOLIO_QUANT_RISK_DECOMPOSITION_V1.

No real private portfolio values appear anywhere in this file -- every account/position/price
figure below is fabricated for test purposes only.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

import personal_portfolio_quant_risk_decomposition as q


# ── Tier 1: hand-verified pure math (no price-history plumbing) ────────────────────────────────

def test_hhi_and_effective_n_hand_calculation():
    confirmed = {
        "AAA": {"current_market_value": 600.0},
        "BBB": {"current_market_value": 400.0},
    }
    result = q._hhi_context(confirmed=confirmed, named_cohort=["AAA", "BBB"], excluded_confirmed=[])
    assert result["status"] == "AVAILABLE"
    assert result["hhi"] == pytest.approx(0.36 + 0.16)  # 0.6**2 + 0.4**2 = 0.52
    assert result["effective_n"] == pytest.approx(1.0 / 0.52)


def test_two_security_portfolio_volatility_hand_calculation():
    """Sigma = [[0.0004, 0.0001], [0.0001, 0.0009]] (vol_A=0.02, vol_B=0.03), w=[0.6, 0.4].
    w'Sigma w = 0.36*0.0004 + 0.16*0.0009 + 2*0.6*0.4*0.0001 = 0.000336."""
    covariance = np.array([[0.0004, 0.0001], [0.0001, 0.0009]])
    weights = np.array([0.6, 0.4])
    variance = q._portfolio_variance(weights=weights, covariance=covariance)
    assert variance == pytest.approx(0.000336)
    assert math.sqrt(variance) == pytest.approx(0.018330302779823362)


def _c1_joint_fixture(covariance):
    return {
        "status": "JOINT_MATRIX_READY", "included_tickers": ["AAA", "BBB"],
        "covariance_matrix": covariance.tolist(),
    }


def test_marginal_and_component_contribution_hand_calculation_and_reconciliation():
    """Same Sigma/w as above. component_pct works out to exactly [0.5, 0.5] despite the 60/40
    capital split -- capital weight and risk contribution genuinely differ."""
    covariance = np.array([[0.0004, 0.0001], [0.0001, 0.0009]])
    joint = _c1_joint_fixture(covariance)
    view_result = q._portfolio_volatility_view(
        view=q.NAV_SCALED_EQUITY_RISK, lookback=20, joint=joint,
        market_value_by_ticker={"AAA": 600.0, "BBB": 400.0}, effective_nav=1000.0,
    )
    assert view_result["status"] == "AVAILABLE"
    assert view_result["portfolio_volatility"] == pytest.approx(0.018330302779823362)

    contribution = q._risk_contribution(view_result=view_result, covariance=covariance)
    assert contribution["status"] == "AVAILABLE"
    assert contribution["per_ticker"]["AAA"]["capital_weight"] == pytest.approx(0.6)
    assert contribution["per_ticker"]["AAA"]["component_contribution_pct"] == pytest.approx(0.5, abs=1e-9)
    assert contribution["per_ticker"]["BBB"]["component_contribution_pct"] == pytest.approx(0.5, abs=1e-9)
    # Capital weight (0.6/0.4) genuinely differs from risk contribution (0.5/0.5).
    assert contribution["per_ticker"]["AAA"]["capital_weight"] != contribution["per_ticker"]["AAA"]["component_contribution_pct"]

    reconciliation = contribution["reconciliation"]
    assert reconciliation["status"] == "PASS"
    assert reconciliation["sum_component_contribution"] == pytest.approx(view_result["portfolio_volatility"])
    assert reconciliation["sum_component_contribution_pct"] == pytest.approx(1.0)


def test_diversification_ratio_hand_reference():
    covariance = np.array([[0.0004, 0.0001], [0.0001, 0.0009]])
    joint = _c1_joint_fixture(covariance)
    view_result = q._portfolio_volatility_view(
        view=q.NAV_SCALED_EQUITY_RISK, lookback=20, joint=joint,
        market_value_by_ticker={"AAA": 600.0, "BBB": 400.0}, effective_nav=1000.0,
    )
    result = q._diversification(
        view_result=view_result, covariance=covariance, pairwise_ready=[], cluster_groups=[],
        nominal_holding_count=2, effective_n=1.0 / 0.52,
    )
    assert result["status"] == "AVAILABLE"
    assert result["diversification_ratio"] == pytest.approx(1.3093073414159542)


def test_leave_one_position_to_cash_hand_reference():
    """Removing either ticker (zeroing its NAV weight, no renormalization) lands at the same
    0.012 volatility here -- 0.4*0.03 with only B, or 0.6*0.02 with only A."""
    covariance = np.array([[0.0004, 0.0001], [0.0001, 0.0009]])
    joint = _c1_joint_fixture(covariance)
    view_result = q._portfolio_volatility_view(
        view=q.NAV_SCALED_EQUITY_RISK, lookback=20, joint=joint,
        market_value_by_ticker={"AAA": 600.0, "BBB": 400.0}, effective_nav=1000.0,
    )
    sensitivity = q._leave_one_to_cash_sensitivity(view_result=view_result, covariance=covariance)
    assert sensitivity["status"] == "AVAILABLE"
    assert sensitivity["contract"] == "MOVE_POSITION_TO_CASH_VOLATILITY_SENSITIVITY"
    assert sensitivity["per_ticker"]["AAA"]["volatility_without_position"] == pytest.approx(0.012)
    assert sensitivity["per_ticker"]["BBB"]["volatility_without_position"] == pytest.approx(0.012)
    assert sensitivity["per_ticker"]["AAA"]["absolute_delta"] < 0
    assert sensitivity["authority_boundary"]["not_a_sell_recommendation"] is True


def test_equity_sleeve_weights_normalize_to_one_while_nav_scaled_can_exceed_one():
    """Section 9: margin/gross exposure making summed equity weights >1 is retained in the
    NAV-scaled view, never silently renormalized away."""
    covariance = np.array([[0.0004, 0.0001], [0.0001, 0.0009]])
    joint = _c1_joint_fixture(covariance)
    market_values = {"AAA": 700.0, "BBB": 500.0}  # sums to 1200 > NAV of 1000 (margin/gross exposure)
    equity_sleeve = q._portfolio_volatility_view(view=q.EQUITY_SLEEVE_VOLATILITY, lookback=20, joint=joint, market_value_by_ticker=market_values, effective_nav=1000.0)
    nav_scaled = q._portfolio_volatility_view(view=q.NAV_SCALED_EQUITY_RISK, lookback=20, joint=joint, market_value_by_ticker=market_values, effective_nav=1000.0)
    assert equity_sleeve["weight_sum"] == pytest.approx(1.0)
    assert equity_sleeve["weight_sum_exceeds_one"] is False
    assert nav_scaled["weight_sum"] == pytest.approx(1.2)
    assert nav_scaled["weight_sum_exceeds_one"] is True


def test_portfolio_volatility_unavailable_without_joint_matrix_ready():
    joint = {"status": "JOINT_MATRIX_BLOCKED_T_RELATIVE_TO_N", "included_tickers": []}
    result = q._portfolio_volatility_view(view=q.NAV_SCALED_EQUITY_RISK, lookback=20, joint=joint, market_value_by_ticker={}, effective_nav=1000.0)
    assert result["status"] == "UNAVAILABLE"
    assert result["portfolio_volatility"] is None
    contribution = q._risk_contribution(view_result=result, covariance=None)
    assert contribution["status"] == "UNAVAILABLE"


def test_portfolio_volatility_unavailable_without_qualified_nav():
    covariance = np.array([[0.0004, 0.0001], [0.0001, 0.0009]])
    joint = _c1_joint_fixture(covariance)
    result = q._portfolio_volatility_view(view=q.NAV_SCALED_EQUITY_RISK, lookback=20, joint=joint, market_value_by_ticker={"AAA": 600.0, "BBB": 400.0}, effective_nav=None)
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "WEIGHT_BASIS_UNAVAILABLE"


# ── Tier 2: end-to-end build_artifact over synthetic price histories ────────────────────────────

def _price_history(tickers, *, sessions=25, drift=None):
    calendar = [f"2026-01-{day:02d}" if day <= 31 else f"2026-02-{day - 31:02d}" for day in range(1, sessions + 1)]
    records = {}
    for ordinal, ticker in enumerate(tickers):
        observations = []
        close = 100.0 + ordinal * 10
        for index, session in enumerate(calendar):
            step = 0.001 * (ordinal + 1) + 0.0002 * (((index + ordinal * 3) % 5) - 2)
            if drift and ticker in drift:
                step = drift[ticker][index % len(drift[ticker])]
            close *= 1.0 + step
            observations.append({"session": session, "close": close, "price_basis": "ADJUSTED_RETROSPECTIVE_CURRENT_RESEARCH"})
        records[ticker] = {"observations": observations}
    return {"snapshot_identity": "prices", "resolved_completed_session": calendar[-1], "records": records}


def _position(ticker, quantity, *, status="CURRENT_CONFIRMED", account_attribution=None):
    return {
        "ticker": ticker, "current_quantity": str(quantity) if status == "CURRENT_CONFIRMED" else None,
        "current_position_status": status,
        "current_position_cost_basis_per_share": "90" if status == "CURRENT_CONFIRMED" else None,
        "current_position_cost_basis_method": "WEIGHTED_AVERAGE_CARRYING_COST" if status == "CURRENT_CONFIRMED" else None,
        "lifetime_cash_recovery_breakeven": None, "lifetime_cash_recovery_breakeven_method": None,
        "position_episode_holding_days": 30,
        "account_attribution": account_attribution if account_attribution is not None else [],
    }


def _snapshot(positions, *, as_of_date="2026-02-19", account=None, aggregate=None):
    account_fields = {"cash_available": None, "net_asset_value": None, "margin_debt": None}
    account_fields.update(account or {})
    return {
        "artifact_identity": "portfolio_snapshot:test",
        "snapshot_as_of_date": as_of_date,
        "positions": positions,
        "account_snapshot": {"fields": account_fields},
        "portfolio_policy": {"effective_fields": {}},
        "investment_accounts_portfolio_context": aggregate or {"status": "NOT_PROVIDED", "totals": {}},
    }


def _last_closes(history, tickers):
    return {ticker: history["records"][ticker]["observations"][-1]["close"] for ticker in tickers}


def _build(positions, *, history_tickers, sessions=25, account=None, excluded_tickers=None, aggregate=None):
    history = _price_history(history_tickers, sessions=sessions)
    snapshot = _snapshot(positions, account=account, aggregate=aggregate)
    prices = _last_closes(history, history_tickers)
    return q.build_artifact(
        requested_at="2026-02-19T17:00:00", portfolio_snapshot=snapshot, price_history_snapshot=history,
        prices=prices, sector_by_ticker={ticker: "TECH" for ticker in history_tickers}, excluded_tickers=excluded_tickers,
    )


def test_one_holding_end_to_end():
    artifact = _build([_position("AAA", 10)], history_tickers=["AAA"], account={"cash_available": "1000", "net_asset_value": "2000"})
    assert artifact["status"] == "AVAILABLE"
    assert artifact["exposure_and_concentration"]["current_confirmed_holding_count"] == 1
    assert artifact["exposure_and_concentration"]["concentration"]["hhi"] == pytest.approx(1.0)
    assert artifact["exposure_and_concentration"]["concentration"]["effective_n"] == pytest.approx(1.0)
    # A single-name cohort has no pairwise correlation and cannot form a joint matrix >=2 names.
    assert artifact["pairwise_correlations"] == []


def test_multiple_holdings_all_ready_full_portfolio_risk():
    artifact = _build(
        [_position("AAA", 10), _position("BBB", 5)], history_tickers=["AAA", "BBB"], sessions=30,
        account={"cash_available": "1000", "net_asset_value": "100000"},
    )
    assert artifact["status"] == "AVAILABLE"
    assert artifact["coverage_by_horizon"]["L20"]["status"] == q.FULL_PORTFOLIO_RISK_READY
    assert set(artifact["coverage_by_horizon"]["L20"]["included_tickers"]) == {"AAA", "BBB"}
    for view in q.PORTFOLIO_VOLATILITY_VIEWS:
        assert artifact["portfolio_volatility"][view]["L20"]["status"] == "AVAILABLE"
        assert artifact["risk_contribution"][view]["L20"]["reconciliation"]["status"] == "PASS"


def test_one_history_unavailable_holding_yields_covered_subset():
    """AAA has full history; BBB's ticker is simply absent from the price-history snapshot."""
    history = _price_history(["AAA"], sessions=30)
    positions = [_position("AAA", 10), _position("BBB", 5)]
    snapshot = _snapshot(positions, account={"cash_available": "1000", "net_asset_value": "100000"})
    prices = _last_closes(history, ["AAA"])
    prices["BBB"] = 50.0
    artifact = q.build_artifact(
        requested_at="2026-02-19T17:00:00", portfolio_snapshot=snapshot, price_history_snapshot=history,
        prices=prices, sector_by_ticker={"AAA": "TECH", "BBB": "TECH"},
    )
    assert artifact["exposure_and_concentration"]["named_research_cohort_count"] == 2
    # BBB's history-unavailable status keeps the horizon a covered SUBSET, never mislabeled full --
    # AAA alone still forms a (trivial, single-name) valid covariance.
    assert artifact["coverage_by_horizon"]["L20"]["status"] == q.COVERED_SUBSET_RISK_READY
    assert artifact["coverage_by_horizon"]["L20"]["included_tickers"] == ["AAA"]
    assert any(row["ticker"] == "BBB" for row in artifact["coverage_by_horizon"]["L20"]["excluded_tickers_and_reason"])


def test_unresolved_position_never_gets_numeric_weight_and_appears_in_coverage_only():
    artifact = _build(
        [_position("AAA", 10), _position("BBB", None, status="CURRENT_POSITION_UNRESOLVED")],
        history_tickers=["AAA"], account={"cash_available": "1000", "net_asset_value": "10000"},
    )
    assert artifact["unresolved_positions"]["count"] == 1
    assert artifact["unresolved_positions"]["tickers"] == ["BBB"]
    assert "BBB" not in artifact["exposure_and_concentration"]["single_name_weights"]
    assert "BBB" not in artifact["per_security_volatility"]
    assert artifact["source_coverage"]["status"] == q.PORTFOLIO_INPUT_COVERAGE_PARTIAL


def test_excluded_confirmed_exposure_never_disappears_but_is_anonymized():
    artifact = _build(
        [_position("AAA", 10), _position("BBB", 5)], history_tickers=["AAA", "BBB"], sessions=30,
        account={"cash_available": "1000", "net_asset_value": "100000"}, excluded_tickers=["BBB"],
    )
    exposure = artifact["exposure_and_concentration"]
    assert exposure["named_research_cohort_count"] == 1
    assert exposure["current_confirmed_holding_count"] == 2
    assert exposure["excluded_confirmed_exposure"]["count"] == 1
    assert exposure["excluded_confirmed_exposure"]["market_value"] > 0
    # The excluded ticker's identity never appears anywhere in the artifact.
    assert "BBB" not in exposure["single_name_weights"]
    assert "BBB" not in artifact["per_security_volatility"]
    assert "BBB" not in str(artifact["exposure_and_concentration"]["excluded_confirmed_exposure"])
    # Denominator (all-confirmed equity market value) still includes the excluded ticker's value,
    # so it is strictly greater than the named-cohort-only figure.
    assert exposure["equity_market_value_all_confirmed"] > exposure["equity_market_value_named_cohort"]


def test_missing_nav_degrades_ratios_without_crashing():
    artifact = _build([_position("AAA", 10)], history_tickers=["AAA"], account={})
    exposure = artifact["exposure_and_concentration"]
    assert exposure["effective_nav"] is None
    assert exposure["equity_exposure_to_nav"] is None
    assert exposure["broker_cash_to_nav"] is None


def test_margin_gross_exposure_above_one_is_retained_not_renormalized_end_to_end():
    artifact = _build(
        [_position("AAA", 100), _position("BBB", 100)], history_tickers=["AAA", "BBB"], sessions=30,
        account={"cash_available": "0", "net_asset_value": "1000", "margin_debt": "5000"},
    )
    nav_scaled = artifact["portfolio_volatility"][q.NAV_SCALED_EQUITY_RISK]["L20"]
    if nav_scaled["status"] == "AVAILABLE":
        assert nav_scaled["weight_sum"] > 1.0
        assert nav_scaled["weight_sum_exceeds_one"] is True
    equity_sleeve = artifact["portfolio_volatility"][q.EQUITY_SLEEVE_VOLATILITY]["L20"]
    if equity_sleeve["status"] == "AVAILABLE":
        assert equity_sleeve["weight_sum"] == pytest.approx(1.0)


def test_covariance_t_less_than_n_plus_5_fails_closed():
    """16 names all WINDOW_READY at L20 (T=19) exceeds the T >= N+5 guard (19 < 16+5=21)."""
    tickers = [f"T{i:02d}" for i in range(16)]
    positions = [_position(ticker, 1) for ticker in tickers]
    artifact = _build(positions, history_tickers=tickers, sessions=25, account={"cash_available": "1", "net_asset_value": "10000"})
    joint = artifact["covariance_integrity"]["L20"]
    assert joint["status"] == "JOINT_MATRIX_BLOCKED_T_RELATIVE_TO_N"
    assert artifact["coverage_by_horizon"]["L20"]["status"] == q.INSUFFICIENT_RISK_COVERAGE
    for view in q.PORTFOLIO_VOLATILITY_VIEWS:
        assert artifact["portfolio_volatility"][view]["L20"]["status"] == "UNAVAILABLE"


def test_singular_covariance_fails_closed():
    """A third ticker with closes identical to AAA makes the 3x3 covariance rank-deficient."""
    history = _price_history(["AAA", "BBB"], sessions=30)
    history["records"]["CCC"] = {"observations": [dict(row) for row in history["records"]["AAA"]["observations"]]}
    positions = [_position("AAA", 10), _position("BBB", 5), _position("CCC", 3)]
    snapshot = _snapshot(positions, account={"cash_available": "1000", "net_asset_value": "100000"})
    prices = _last_closes(history, ["AAA", "BBB", "CCC"])
    artifact = q.build_artifact(
        requested_at="2026-02-19T17:00:00", portfolio_snapshot=snapshot, price_history_snapshot=history,
        prices=prices, sector_by_ticker={t: "TECH" for t in ("AAA", "BBB", "CCC")},
    )
    joint = artifact["covariance_integrity"]["L20"]
    assert joint["status"] == "JOINT_MATRIX_NUMERICAL_GUARD_FAILED"
    assert artifact["coverage_by_horizon"]["L20"]["status"] == q.INSUFFICIENT_RISK_COVERAGE


def test_subset_result_never_mislabeled_full():
    """AAA/BBB fully covered, CCC has no history at all -- a COVERED_SUBSET, never FULL."""
    history = _price_history(["AAA", "BBB"], sessions=30)
    positions = [_position("AAA", 10), _position("BBB", 5), _position("CCC", 3)]
    snapshot = _snapshot(positions, account={"cash_available": "1000", "net_asset_value": "100000"})
    prices = _last_closes(history, ["AAA", "BBB"])
    prices["CCC"] = 42.0
    artifact = q.build_artifact(
        requested_at="2026-02-19T17:00:00", portfolio_snapshot=snapshot, price_history_snapshot=history,
        prices=prices, sector_by_ticker={t: "TECH" for t in ("AAA", "BBB", "CCC")},
    )
    coverage = artifact["coverage_by_horizon"]["L20"]
    assert coverage["status"] == q.COVERED_SUBSET_RISK_READY
    assert set(coverage["included_tickers"]) == {"AAA", "BBB"}
    assert coverage["excluded_count"] == 1
    assert coverage["included_nav_weight"] is not None and coverage["excluded_or_unmeasured_nav_weight"] is not None


def test_account_level_position_risk_not_qualified_without_exact_account_attribution():
    positions = [
        _position("AAA", 10, account_attribution=[{"account_id": "ACC-A", "attribution_status": "ATTRIBUTED", "current_quantity": "10"}]),
        _position("BBB", 5, account_attribution=[{"account_id": "ACCOUNT_ATTRIBUTION_UNRESOLVED", "attribution_status": "ACCOUNT_ATTRIBUTION_UNRESOLVED", "current_quantity": None}]),
    ]
    artifact = _build(positions, history_tickers=["AAA", "BBB"], sessions=30, account={"cash_available": "1000", "net_asset_value": "100000"})
    account_level = artifact["account_level_context"]["position_risk_decomposition"]
    assert account_level["status"] == q.ACCOUNT_LEVEL_POSITION_RISK_NOT_QUALIFIED
    assert account_level["unqualified_tickers"] == ["BBB"]


def test_account_level_position_risk_qualified_when_every_named_ticker_is_attributed():
    positions = [
        _position("AAA", 10, account_attribution=[{"account_id": "ACC-A", "attribution_status": "ATTRIBUTED", "current_quantity": "10"}]),
        _position("BBB", 5, account_attribution=[{"account_id": "ACC-B", "attribution_status": "ATTRIBUTED", "current_quantity": "5"}]),
    ]
    artifact = _build(positions, history_tickers=["AAA", "BBB"], sessions=30, account={"cash_available": "1000", "net_asset_value": "100000"})
    account_level = artifact["account_level_context"]["position_risk_decomposition"]
    assert account_level["status"] == "QUALIFIED"
    assert set(account_level["equity_market_value_by_account"]) == {"ACC-A", "ACC-B"}


def test_deterministic_identity():
    positions = [_position("AAA", 10), _position("BBB", 5)]
    history = _price_history(["AAA", "BBB"], sessions=30)
    snapshot = _snapshot(positions, account={"cash_available": "1000", "net_asset_value": "100000"})
    prices = _last_closes(history, ["AAA", "BBB"])
    kwargs = dict(requested_at="2026-02-19T17:00:00", portfolio_snapshot=snapshot, price_history_snapshot=history, prices=prices, sector_by_ticker={"AAA": "TECH", "BBB": "TECH"})
    first = q.build_artifact(**kwargs)
    second = q.build_artifact(**kwargs)
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["artifact_sha256"] == second["artifact_sha256"]


def test_insufficient_portfolio_truth_when_no_confirmed_positions():
    artifact = _build([_position("AAA", None, status="CLOSED")], history_tickers=["AAA"])
    assert artifact["status"] == "INSUFFICIENT_PORTFOLIO_TRUTH"
    assert artifact["source_coverage"]["status"] == q.INSUFFICIENT_PORTFOLIO_TRUTH


def test_no_private_data_publication_console_summary():
    artifact = _build([_position("AAA", 10), _position("BBB", 5)], history_tickers=["AAA", "BBB"], sessions=30, account={"cash_available": "1000", "net_asset_value": "100000"})
    summary = q.public_console_summary(artifact)
    assert "AAA" not in str(summary) and "BBB" not in str(summary)
    assert "single_name_weights" not in summary
    assert "portfolio_volatility" not in summary
    assert summary["current_confirmed_holding_count"] == 2


def test_local_write_path_never_targets_the_repository():
    root = q.default_private_output_root()
    assert ".stocklookup" in str(root)
    assert "operations-review" not in str(root)


def test_source_coverage_flags_unadmitted_workbook_sheets():
    ledger_with_extra_sheet = {"sheet_inventory": [{"sheet": "Trade"}, {"sheet": "AccountSnapshot"}, {"sheet": "FUESSVN30"}]}
    result = q._source_coverage(confirmed_count=1, unresolved_count=0, portfolio_snapshot={}, event_ledger=ledger_with_extra_sheet)
    assert result["status"] == q.QUALIFIED_COVERED_SUBSET
    assert result["unadmitted_source_sheets"] == ["FUESSVN30"]


def test_source_coverage_full_when_no_unadmitted_sheets_and_no_gaps():
    ledger_clean = {"sheet_inventory": [{"sheet": "Trade"}, {"sheet": "Dividend"}, {"sheet": "Money"}, {"sheet": "margin"}, {"sheet": "AccountSnapshot"}]}
    result = q._source_coverage(confirmed_count=1, unresolved_count=0, portfolio_snapshot={}, event_ledger=ledger_clean)
    assert result["status"] == q.FULL_PORTFOLIO_COVERAGE
