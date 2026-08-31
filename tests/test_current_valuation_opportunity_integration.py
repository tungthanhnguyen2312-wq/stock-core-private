"""Focused tests for current valuation + opportunity integration."""
from __future__ import annotations

import copy

import pytest

from current_market_sector_leadership_context import _percentile
from current_research_valuation_context import (
    CURRENT_SHARE_RESEARCH_PROXY, EXACT_OR_QUALIFIED, INPUT_BLOCKED, NOT_APPLICABLE,
    PE_NOT_MEANINGFUL, PE_TTM, PS_TTM, attach_peer_relative, evaluate_ticker_valuation, share_basis_class,
)
from current_valuation_opportunity_integration import build_artifacts, content_identity
from opportunity_axis_freshness import (
    CURRENT, STALE_BUT_RESEARCH_USABLE, STALE_NOT_USABLE_FOR_THIS_AXIS, UNAVAILABLE,
    FutureInformationError, classify_axis_freshness,
)
from sector_relative_research_context import MIN_COHORT_MEMBERS
from security_decision_context import infer_research_stance

DECISION = "2026-08-28"


def _identity(kind: str) -> str:
    return f"{kind}:abc"


def _feature(status, value=None, state=None, periods=None, method="same_native_series_dimensionless_ratio/v1",
             compat="SAME_NATIVE_SERIES_RESEARCH_COMPATIBLE", blockers=None):
    return {
        "feature_id": "x", "value": value, "categorical_state": state, "status": status, "method": method,
        "compatibility_class": compat, "input_periods": list(periods or []),
        "blocker_reason_codes": list(blockers or []), "research_fitness": status,
        "authoritative_financial_eligible": False, "is_actionable": False,
    }


def _blocked(reason="MISSING"):
    return _feature("BLOCKED", blockers=[reason], method="blocked_feature_contract/v1", compat="BLOCKED_INCOMPATIBLE")


def feature_record(ticker, *, entity="corporate", profit="PROFITABLE", ni=100.0, ttm_ni=400.0, ttm_rev=4000.0,
                   margin=0.1, equity=0.5, yoy=0.2, periods=("2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1")):
    ttm_status = "READY_RESEARCH_PROXY" if ttm_ni is not None else "BLOCKED"
    features = {
        "net_income_ttm_sum": _feature(ttm_status, ttm_ni, periods=periods, method="TTM_SUM_PROXY") if ttm_ni is not None else _blocked("MISSING_CONSECUTIVE_STANDALONE_QUARTER_INPUTS"),
        "revenue_ttm_sum": _feature("READY_RESEARCH_PROXY", ttm_rev, periods=periods, method="TTM_SUM_PROXY") if ttm_rev is not None else _blocked("MISSING_CONSECUTIVE_STANDALONE_QUARTER_INPUTS"),
        "profit_state": _feature("READY_RESEARCH_PROXY", ni, state=profit, periods=[periods[-1]], method="same_native_latest_sign/v1"),
        "net_margin": _feature("READY_RESEARCH_PROXY", margin, periods=[periods[-1], periods[-1]]),
        "equity_to_assets": _feature("READY_RESEARCH_PROXY", equity, periods=[periods[-1], periods[-1]]) if entity == "corporate" else _blocked("GENERIC_CORPORATE_FEATURE_NOT_APPLICABLE"),
        "revenue_same_period_yoy": _feature("READY_RESEARCH_PROXY", yoy, periods=[periods[0], periods[-1]], method="same_native_series_same_quarter_yoy/v1"),
        "net_income_same_period_yoy": _feature("READY_RESEARCH_PROXY", yoy, state="PROFIT_GROWTH", periods=[periods[0], periods[-1]], method="same_native_series_same_quarter_yoy/v1"),
        "roa_eop_proxy": _blocked("CROSS_PROVIDER_OR_DURATION_INCOMPATIBLE"),
        "roe_eop_proxy": _blocked("CROSS_PROVIDER_OR_DURATION_INCOMPATIBLE"),
    }
    ready = [item for item in features.values() if item["status"] in {"READY_RESEARCH", "READY_RESEARCH_PROXY", "PARTIAL_RESEARCH"}]
    return {
        "ticker": ticker, "entity_type": entity,
        "entity_applicability": "GENERIC_RESEARCH_PRIMITIVES_ALLOWED" if entity == "corporate" else "GENERIC_CORPORATE_FEATURE_NOT_APPLICABLE",
        "features": features,
        "fundamental_feature_context": {
            "availability": "PRODUCT_READY_RESEARCH_CONTEXT", "ready_feature_count": len(ready),
            "health_axes": {
                "PROFITABILITY_STATE": profit, "GROWTH_STATE": features["net_income_same_period_yoy"]["categorical_state"] or "INSUFFICIENT_DATA",
                "MARGIN_STATE": "AVAILABLE", "DATA_COVERAGE_STATE": "READY_RESEARCH_PROXY",
                "BALANCE_SHEET_STATE": "IMPROVING", "LEVERAGE_STATE": "INSUFFICIENT_DATA",
                "CASH_QUALITY_STATE": "CASH_QUALITY_UNAVAILABLE", "CAPITAL_EFFICIENCY_STATE": "INSUFFICIENT_DATA",
            },
            "current_features": features, "warnings_blockers": [],
        },
    }


def valuation_record(ticker, *, entity="corporate", market_cap=8000.0, pe=None, pb=None, ps=None,
                     share_authority="provider_reported_lagged", share_value=1000, research_proxy=True,
                     official=False, ev_ebitda=None):
    share = {
        "authority": "qualified_official" if official else share_authority,
        "status": "QUALIFIED_OFFICIAL" if official else "PROVIDER_REPORTED_LAGGED",
        "value": share_value, "share_concept": "current_common_shares_outstanding" if official else "ISSUED_SHARES",
        "research_proxy_eligible": research_proxy or official,
        "authoritative_current_market_cap_eligible": False,
    }
    def metric(status, value=None, blockers=None, applicability="APPLICABLE"):
        return {"status": status, "value": value, "applicability": applicability, "blocked_reasons": blockers or [],
                "share_identity": share["share_concept"]}
    na = "NOT_APPLICABLE" if entity in {"bank", "securities", "insurance", "finance_company"} else "APPLICABLE"
    ev_na = "NOT_APPLICABLE" if entity in {"bank", "securities", "insurance", "finance_company"} else "APPLICABLE"
    return {
        "ticker": ticker, "entity_class": entity, "share_basis_input": share,
        "price_input": {"status": "PRICE_READY", "value": 8.0, "session": DECISION},
        "metrics": {
            "market_cap": metric("RESEARCH_USABLE" if market_cap is not None else "BLOCKED", market_cap,
                                 [] if market_cap is not None else ["SHARE_AUTHORITY_OR_PROXY_UNAVAILABLE"]),
            "P/E": metric("RESEARCH_USABLE" if pe is not None else "BLOCKED", pe, [] if pe is not None else ["PROVIDER_RESEARCH_NOT_AUTHORIZED_FOR_ABSOLUTE_VALUATION_INPUTS"]),
            "P/B": metric("RESEARCH_USABLE" if pb is not None else "BLOCKED", pb),
            "P/S": metric("NOT_APPLICABLE" if na == "NOT_APPLICABLE" else ("RESEARCH_USABLE" if ps is not None else "BLOCKED"),
                          ps, ["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"] if na == "NOT_APPLICABLE" else [], na),
            "EV/Sales": metric("NOT_APPLICABLE" if ev_na == "NOT_APPLICABLE" else "BLOCKED", None, ["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"] if ev_na == "NOT_APPLICABLE" else ["PROVIDER_RESEARCH_NOT_AUTHORIZED_FOR_ABSOLUTE_VALUATION_INPUTS"], ev_na),
            "EV/EBITDA": metric("NOT_APPLICABLE" if ev_na == "NOT_APPLICABLE" else "BLOCKED", ev_ebitda,
                                ["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"] if ev_na == "NOT_APPLICABLE" else ["EXACT_EBITDA_COMPARABILITY_NOT_RETAINED"],
                                ev_na),
        },
    }


def behavior(ticker, *, entry="EARLY_REVERSAL_CANDIDATE", session=DECISION, confirm="READY",
             invalid="READY", tags=None):
    return {
        "ticker": ticker, "as_of_session": session, "primary_entry_state": entry,
        "setup_tags": list(tags or ["EARLY_REVERSAL_STRUCTURE"]),
        "confirmation_boundary": {"status": confirm, "as_of": session, "boundary_type": "REVERSAL_CONFIRM"},
        "technical_invalidation_boundary": {"status": invalid, "as_of": session, "boundary_type": "BREAKDOWN"},
        "price_volume_behavior": {"price_volume_distribution_risk": False},
        "trend_context": {"trend_state": "RECOVERING"}, "structure_context": {"structure_status": "HIGHER_LOW"},
        "market_regime_context": {"current_breadth_state": "MARKET_BREADTH_MIXED"},
        "sector_context": {"leadership_state": None},
        "relative_strength_context": {"market_relative_momentum_bucket": "UPPER_MIDDLE"},
    }


def watchlist(ticker, *, entry="EARLY_REVERSAL_CANDIDATE", action="EARLY_ENTRY"):
    return {"ticker": ticker, "entry_state": entry, "entry_action": action}


def liquidity_record(ticker, *, session=DECISION, eligible=True):
    return {
        "ticker": ticker, "session": session, "disposition": "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE" if eligible else "MISSING",
        "current_ohlc_v": 1000 if eligible else None,
        "liquidity_research_contract": {
            "CURRENT_SESSION_LIQUIDITY_RESEARCH": {"state": "ELIGIBLE" if eligible else "BLOCKED"},
            "EXECUTION_CAPACITY": {"state": "BLOCKED"},
            "ADTV_RESEARCH": {"state": "BLOCKED"},
        },
    }


def artifact(records, *, session=DECISION, kind="x"):
    return {"session": session, "as_of_session": session, "artifact_identity": _identity(kind), "records": records}


def feature_store(rows):
    return {"artifact_identity": _identity("feature"), "contract_version": "market_wide_fundamental_feature_store/v1", "records": rows}


def build(*, features, valuations, behaviors, watch, liquids=None, events=None, thesis=None,
          session=DECISION, portfolio=None):
    return build_artifacts(
        as_of_session=session,
        feature_store=feature_store(features),
        tactical_behavior=artifact(behaviors, session=session, kind="tactical"),
        watchlist=artifact(watch, session=session, kind="watch"),
        valuation={"valuation_session": session, "artifact_identity": _identity("val"), "records": valuations},
        liquidity=artifact(liquids or {}, session=session, kind="liq") if liquids is not None else None,
        events={"research_session": session, "artifact_identity": _identity("evt"), "records": events or {}},
        thesis_cases={"as_of_session": session, "artifact_identity": _identity("thesis"), "records": thesis or {}},
        portfolio=portfolio,
        requested_at="2026-08-31T00:00:00+07:00",
    )


def test_session_freshness_preserved_per_axis_and_not_coerced():
    envelope = classify_axis_freshness(axis="liquidity", decision_session=DECISION, source_session="2026-08-21")
    assert envelope["freshness_status"] == STALE_BUT_RESEARCH_USABLE
    assert envelope["source_session"] == "2026-08-21"
    assert envelope["rewritten_as_current"] is False
    tactical = classify_axis_freshness(axis="tactical", decision_session=DECISION, source_session="2026-08-21")
    assert tactical["freshness_status"] == STALE_NOT_USABLE_FOR_THIS_AXIS
    current = classify_axis_freshness(axis="tactical", decision_session=DECISION, source_session=DECISION)
    assert current["freshness_status"] == CURRENT


def test_no_future_data_join():
    with pytest.raises(FutureInformationError):
        classify_axis_freshness(axis="valuation", decision_session=DECISION, source_session="2026-08-29")
    with pytest.raises(FutureInformationError):
        build_artifacts(
            as_of_session=DECISION,
            tactical_behavior=artifact({"AAA": behavior("AAA")}, session="2026-08-29", kind="tactical"),
            requested_at="t",
        )


def test_stale_axis_localized_does_not_block_ticker():
    features = {"AAA": feature_record("AAA")}
    valuations = {"AAA": valuation_record("AAA")}
    behaviors = {"AAA": behavior("AAA")}
    watch = {"AAA": watchlist("AAA")}
    liquids = {"AAA": liquidity_record("AAA", session="2026-08-21")}
    out = build(features=features, valuations=valuations, behaviors=behaviors, watch=watch, liquids=liquids)
    row = out["opportunity_context"]["records"]["AAA"]
    assert row["liquidity"]["freshness"]["freshness_status"] == STALE_BUT_RESEARCH_USABLE
    assert row["tactical"]["freshness"]["freshness_status"] == CURRENT
    assert row["disposition"] != "BLOCKED"
    assert row["tactical"]["research_usable"] is True


def test_compatible_ttm_valuation_and_share_basis_proxy_explicit():
    row = evaluate_ticker_valuation(
        ticker="AAA", feature_record=feature_record("AAA", ttm_ni=400, ttm_rev=4000),
        valuation_record=valuation_record("AAA", market_cap=8000),
    )
    assert row["share_basis"] == CURRENT_SHARE_RESEARCH_PROXY
    assert row["methods"][PE_TTM]["status"] == "RESEARCH_USABLE"
    assert row["methods"][PE_TTM]["value"] == pytest.approx(20.0)
    assert row["methods"][PS_TTM]["value"] == pytest.approx(2.0)
    assert row["methods"][PE_TTM]["share_basis"] == CURRENT_SHARE_RESEARCH_PROXY


def test_negative_and_zero_earnings_pe_not_meaningful():
    loss = evaluate_ticker_valuation(
        ticker="LOS", feature_record=feature_record("LOS", profit="LOSS_MAKING", ni=-10, ttm_ni=-40),
        valuation_record=valuation_record("LOS", market_cap=8000),
    )
    assert loss["methods"][PE_TTM]["status"] == PE_NOT_MEANINGFUL
    assert loss["methods"][PE_TTM]["value"] is None
    assert loss["methods"][PS_TTM]["status"] == "RESEARCH_USABLE"
    zero = evaluate_ticker_valuation(
        ticker="ZRO", feature_record=feature_record("ZRO", profit="BREAK_EVEN", ni=0, ttm_ni=0),
        valuation_record=valuation_record("ZRO", market_cap=8000),
    )
    assert zero["methods"][PE_TTM]["status"] == PE_NOT_MEANINGFUL
    assert "ZERO_OR_NEAR_ZERO_EARNINGS" in zero["methods"][PE_TTM]["blocker_reason_codes"]


def test_entity_class_applicability_excludes_bank_generic_methods():
    bank = evaluate_ticker_valuation(
        ticker="VCB", feature_record=feature_record("VCB", entity="bank", ttm_ni=400, ttm_rev=4000),
        valuation_record=valuation_record("VCB", entity="bank", market_cap=8000),
    )
    assert bank["methods"][PS_TTM]["applicability"] == NOT_APPLICABLE
    assert bank["methods"][PS_TTM]["status"] == NOT_APPLICABLE
    assert bank["methods"]["EV/EBITDA"]["applicability"] == NOT_APPLICABLE
    assert bank["methods"][PE_TTM]["applicability"] == "APPLICABLE"
    sec = evaluate_ticker_valuation(
        ticker="SSI", feature_record=feature_record("SSI", entity="securities"),
        valuation_record=valuation_record("SSI", entity="securities"),
    )
    assert sec["methods"]["EV/EBITDA"]["status"] == NOT_APPLICABLE
    unknown = evaluate_ticker_valuation(
        ticker="UNK", feature_record=feature_record("UNK", entity="unknown"),
        valuation_record=valuation_record("UNK", entity="unknown"),
    )
    assert unknown["entity_class"] == "unknown"
    assert unknown["methods"][PE_TTM]["applicability"] == INPUT_BLOCKED


def test_same_method_peer_comparison_canonical_percentile_and_minimum_count():
    rows = {}
    values = [10.0, 20.0, 20.0, 30.0, 40.0]
    for index, value in enumerate(values):
        ticker = f"P{index}"
        rows[ticker] = evaluate_ticker_valuation(
            ticker=ticker, feature_record=feature_record(ticker, ttm_ni=1000 / value, ttm_rev=10000),
            valuation_record=valuation_record(ticker, market_cap=1000),
        )
    attach_peer_relative(rows)
    subject = rows["P1"]["peer_relative"][PE_TTM]
    assert subject["status"] == "READY_RESEARCH_ONLY"
    assert subject["peer_count"] == 5
    assert subject["percentile"] == pytest.approx(_percentile(values, 20.0))
    assert subject["percentile"] == pytest.approx((1 + 0.5 * 2) / 5)
    short = {ticker: rows[ticker] for ticker in ("P0", "P1", "P2")}
    attach_peer_relative(short)
    assert short["P0"]["peer_relative"][PE_TTM]["status"] == "INSUFFICIENT_PEER_COUNT"
    assert MIN_COHORT_MEMBERS == 5


def test_incompatible_valuation_basis_excluded_from_peers():
    exact = evaluate_ticker_valuation(
        ticker="HPG", feature_record=feature_record("HPG", ttm_ni=400),
        valuation_record=valuation_record("HPG", market_cap=8000, official=True),
    )
    proxy = evaluate_ticker_valuation(
        ticker="AAA", feature_record=feature_record("AAA", ttm_ni=400),
        valuation_record=valuation_record("AAA", market_cap=8000),
    )
    assert exact["share_basis"] == EXACT_OR_QUALIFIED
    assert proxy["share_basis"] == CURRENT_SHARE_RESEARCH_PROXY
    attached = attach_peer_relative({"HPG": exact, "AAA": proxy, "BBB": copy.deepcopy(proxy), "CCC": copy.deepcopy(proxy), "DDD": copy.deepcopy(proxy)})
    assert attached["HPG"]["peer_relative"][PE_TTM]["status"] == "INSUFFICIENT_PEER_COUNT"
    assert attached["AAA"]["peer_relative"][PE_TTM]["peer_count"] == 4 or attached["AAA"]["peer_relative"][PE_TTM]["status"] == "INSUFFICIENT_PEER_COUNT"


def test_fundamental_peer_method_compatibility_excludes_blocked_roe_proxy():
    features = {f"T{i}": feature_record(f"T{i}", margin=0.1 + i * 0.01) for i in range(6)}
    from current_research_valuation_context import attach_fundamental_peers
    peers = attach_fundamental_peers(features, {})
    assert peers["T0"]["net_margin"]["status"] == "READY_RESEARCH_ONLY"
    assert peers["T0"]["net_margin"]["percentile_formula"] == "(below + 0.5 * equal) / n"
    # ROE EOP proxy is blocked in the feature store; it is not in the comparable set.
    assert "roe_eop_proxy" not in peers["T0"]


def test_missing_valuation_and_catalyst_are_localized():
    features = {"AAA": feature_record("AAA", ttm_ni=None, ttm_rev=None)}
    valuations = {"AAA": valuation_record("AAA", market_cap=None, share_authority="unavailable", share_value=None, research_proxy=False)}
    valuations["AAA"]["share_basis_input"] = {"authority": "unavailable", "status": "UNAVAILABLE", "research_proxy_eligible": False}
    behaviors = {"AAA": behavior("AAA", entry="UPTREND_CONFIRMED")}
    watch = {"AAA": watchlist("AAA", entry="UPTREND_CONFIRMED", action="WAIT")}
    out = build(features=features, valuations=valuations, behaviors=behaviors, watch=watch, liquids={"AAA": liquidity_record("AAA")}, events={})
    row = out["opportunity_context"]["records"]["AAA"]
    assert row["valuation"]["research_usable"] in {False, True}
    assert row["catalyst"]["status"] in {"UNAVAILABLE", "WATCH_FOR_EXECUTION"}
    assert row["tactical"]["research_usable"] is True
    assert row["disposition"] == "PARTIAL_BY_EVIDENCE"


def test_research_liquidity_independent_of_execution_capacity_and_does_not_force_wait():
    features = {"AAA": feature_record("AAA")}
    valuations = {"AAA": valuation_record("AAA")}
    behaviors = {"AAA": behavior("AAA", entry="EARLY_REVERSAL_CANDIDATE")}
    watch = {"AAA": watchlist("AAA")}
    liquids = {"AAA": liquidity_record("AAA")}
    out = build(features=features, valuations=valuations, behaviors=behaviors, watch=watch, liquids=liquids)
    row = out["opportunity_context"]["records"]["AAA"]
    decision = out["security_decision_context"]["records"]["AAA"]
    assert row["liquidity"]["readiness"] == "LIQUIDITY_RESEARCH_PROXY"
    assert row["liquidity"]["exact_execution_capacity_status"] == "EXECUTION_CAPACITY_EXACT_BLOCKED"
    assert decision["research_stance"] == "INITIATE_RESEARCH_CANDIDATE"
    assert decision["research_stance"] != "WAIT_FOR_CONFIRMATION"
    assert "EXECUTION_CAPACITY_EXACT_BLOCKED_NOT_A_STANCE_GATE" in decision["warnings_counter_thesis"]["warnings"]
    assert decision["authority_boundary"]["exact_execution_capacity_is_not_a_wait_gate"] is True


def test_tactical_entry_confirmation_and_invalidation_preserved():
    features = {"AAA": feature_record("AAA")}
    valuations = {"AAA": valuation_record("AAA")}
    behaviors = {"AAA": behavior("AAA", entry="BREAKOUT_READY", confirm="READY", invalid="READY", tags=["BREAKOUT_CONFIRMED_BY_RULE"])}
    watch = {"AAA": watchlist("AAA", entry="BREAKOUT_READY", action="BUY_ON_CONFIRMATION")}
    thesis = {"AAA": {
        "as_of_session": DECISION, "catalysts": [], "retained_event_context": [],
        "technical_invalidation": {"status": "CONDITIONAL", "as_of": DECISION},
        "fundamental_invalidation": {"status": "CONDITIONAL", "reason": "MARGIN_BASELINE_MISSING"},
        "counter_thesis_evidence": [{"reason": "WEAK_SETUP_CONTEXT"}],
    }}
    out = build(features=features, valuations=valuations, behaviors=behaviors, watch=watch,
                liquids={"AAA": liquidity_record("AAA")}, thesis=thesis)
    row = out["opportunity_context"]["records"]["AAA"]
    decision = out["security_decision_context"]["records"]["AAA"]
    assert row["tactical"]["primary_entry_state"] == "BREAKOUT_READY"
    assert row["tactical"]["entry_action"] == "BUY_ON_CONFIRMATION"
    assert row["tactical"]["confirmation"]["status"] == "READY"
    assert row["tactical"]["invalidation"]["status"] == "READY"
    assert decision["entry_state"] == "BREAKOUT_READY"
    assert decision["entry_action"] == "BUY_ON_CONFIRMATION"
    assert decision["confirmation_boundary"]["status"] == "READY"
    assert decision["technical_invalidation"]["status"] == "READY"
    assert decision["fundamental_invalidation"]["status"] == "CONDITIONAL"
    assert decision["key_counter_thesis"]


def test_security_stance_separate_from_portfolio_fit():
    features = {"AAA": feature_record("AAA")}
    valuations = {"AAA": valuation_record("AAA")}
    behaviors = {"AAA": behavior("AAA")}
    watch = {"AAA": watchlist("AAA")}
    portfolio = {"portfolio_id": "demo", "as_of_session": "2026-08-25", "artifact_identity": "portfolio:x",
                 "normalized_positions": [{"ticker": "AAA", "weight": 0.9}]}
    out = build(features=features, valuations=valuations, behaviors=behaviors, watch=watch,
                liquids={"AAA": liquidity_record("AAA")}, portfolio=portfolio)
    row = out["opportunity_context"]["records"]["AAA"]
    decision = out["security_decision_context"]["records"]["AAA"]
    assert row["portfolio_availability"]["status"] == "STALE"
    assert row["portfolio_availability"]["does_not_change_security_attractiveness"] is True
    assert decision["factual_axes"]["portfolio_availability"] == "STALE"
    assert decision["research_stance"] == "INITIATE_RESEARCH_CANDIDATE"
    assert decision["authority_boundary"]["security_attractiveness_separate_from_portfolio_fit"] is True


def test_no_score_rank_probability_or_target_price():
    out = build(
        features={"AAA": feature_record("AAA")},
        valuations={"AAA": valuation_record("AAA")},
        behaviors={"AAA": behavior("AAA")},
        watch={"AAA": watchlist("AAA")},
        liquids={"AAA": liquidity_record("AAA")},
    )
    blob = str(out)
    for banned in ("universal_score", "probability_of_success", "target_price_value", "fair_value_target"):
        assert banned not in blob.lower() or out["opportunity_context"]["blocked_outputs"]["universal_score"] == "SCORING_PROHIBITED"
    row = out["opportunity_context"]["records"]["AAA"]
    assert "score" not in row
    assert row["authority_boundary"]["no_universal_score"] is True
    assert row["authority_boundary"]["no_probability"] is True
    assert row["authority_boundary"]["no_target_price"] is True
    for method in row["valuation"]["applicable_methods"].values():
        assert method.get("value") is None or isinstance(method.get("value"), (int, float))
    assert out["opportunity_context"]["blocked_outputs"]["target_price"] == "NOT_EMITTED"


def test_zero_vs_missing_and_zero_silent_drops():
    features = {
        "AAA": feature_record("AAA", ttm_ni=0, profit="BREAK_EVEN", ni=0),
        "BBB": feature_record("BBB", ttm_ni=None, ttm_rev=None),
        "CCC": feature_record("CCC"),
    }
    valuations = {ticker: valuation_record(ticker) for ticker in features}
    behaviors = {
        "AAA": behavior("AAA", entry="BASE_BUILDING"),
        "BBB": behavior("BBB", entry="DOWNTREND"),
        "CCC": behavior("CCC", entry="SIDEWAYS_NEUTRAL"),
        "DDD": behavior("DDD", entry="SELLING_PRESSURE_EASING"),
    }
    watch = {ticker: watchlist(ticker, entry=behaviors[ticker]["primary_entry_state"],
                               action="AVOID" if ticker == "BBB" else "WAIT") for ticker in behaviors}
    out = build(features=features, valuations=valuations, behaviors=behaviors, watch=watch,
                liquids={ticker: liquidity_record(ticker) for ticker in behaviors})
    assert out["opportunity_context"]["coverage"]["ticker_denominator"] == 4
    assert out["opportunity_context"]["coverage"]["zero_silent_ticker_drops"] is True
    assert set(out["opportunity_context"]["records"]) == {"AAA", "BBB", "CCC", "DDD"}
    assert out["security_decision_context"]["coverage"]["security_decision_context_coverage"] == 4
    aaa = out["opportunity_context"]["records"]["AAA"]["valuation"]["applicable_methods"][PE_TTM]
    bbb = out["opportunity_context"]["records"]["BBB"]["valuation"]["applicable_methods"][PE_TTM]
    assert aaa["status"] == PE_NOT_MEANINGFUL
    assert bbb["status"] == INPUT_BLOCKED
    assert aaa["value"] is None and bbb["value"] is None


def test_deterministic_identity_ignores_wall_clock():
    kwargs = dict(
        as_of_session=DECISION,
        feature_store=feature_store({"AAA": feature_record("AAA")}),
        tactical_behavior=artifact({"AAA": behavior("AAA")}, kind="tactical"),
        watchlist=artifact({"AAA": watchlist("AAA")}, kind="watch"),
        valuation={"valuation_session": DECISION, "artifact_identity": _identity("val"), "records": {"AAA": valuation_record("AAA")}},
        liquidity=artifact({"AAA": liquidity_record("AAA")}, kind="liq"),
    )
    first = build_artifacts(**kwargs, requested_at="2026-08-31T00:00:00+07:00")
    second = build_artifacts(**kwargs, requested_at="2099-01-01T00:00:00Z")
    assert first["opportunity_context"]["artifact_sha256"] == second["opportunity_context"]["artifact_sha256"]
    assert first["security_decision_context"]["artifact_sha256"] == second["security_decision_context"]["artifact_sha256"]
    replay = content_identity(first["opportunity_context"])
    assert replay["artifact_sha256"] == first["opportunity_context"]["artifact_sha256"]


def test_compact_projection_omits_full_histories():
    out = build(
        features={"AAA": feature_record("AAA")},
        valuations={"AAA": valuation_record("AAA")},
        behaviors={"AAA": behavior("AAA")},
        watch={"AAA": watchlist("AAA")},
        liquids={"AAA": liquidity_record("AAA")},
    )
    compact = out["opportunity_context"]["opportunity_context"]["AAA"]
    assert "current_features" not in compact["fundamental"]
    assert "close_history" not in str(compact)
    assert compact["tactical"]["primary_entry_state"] == "EARLY_REVERSAL_CANDIDATE"
    decision = out["security_decision_context"]["security_decision_context"]["AAA"]
    assert set(decision) >= {"ticker", "entry_state", "entry_action", "research_stance", "factual_axes"}


def test_market_cap_percentile_alone_cannot_produce_attractive_or_expensive_relative_state():
    # Five tickers with every true multiple (TTM P/E, TTM P/S, P/E, P/S, P/B, EV/Sales, EV/EBITDA)
    # blocked, but a clean, cheap-to-expensive market-cap spread. Market cap and EV are size
    # context, never a relative-value input (docs/DECISIONS.md's own corrective invariant) -- this
    # must not yield ATTRACTIVE_RELATIVE_RESEARCH / EXPENSIVE_RELATIVE_RESEARCH. Regression for the
    # live 2026-08-28 finding: 440/1699 real tickers (25.9%) had usable_relative_method_count == 0
    # yet a market-cap-driven ATTRACTIVE_RELATIVE_RESEARCH label before this fix.
    market_caps = [1000.0, 5000.0, 5000.0, 9000.0, 20000.0]
    rows = {}
    for index, cap in enumerate(market_caps):
        ticker = f"MCAP{index}"
        rows[ticker] = evaluate_ticker_valuation(
            ticker=ticker, feature_record=feature_record(ticker, ttm_ni=None, ttm_rev=None),
            valuation_record=valuation_record(ticker, market_cap=cap, pe=None, pb=None, ps=None, ev_ebitda=None),
        )
        assert rows[ticker]["usable_relative_method_count"] == 0
    attach_peer_relative(rows)
    cheapest, priciest = rows["MCAP0"], rows["MCAP4"]
    assert cheapest["peer_relative"]["market_cap"]["status"] == "READY_RESEARCH_ONLY"
    assert cheapest["peer_relative"]["market_cap"]["percentile"] <= 0.25
    assert cheapest["relative_research_state"] not in {"ATTRACTIVE_RELATIVE_RESEARCH", "EXPENSIVE_RELATIVE_RESEARCH"}
    assert priciest["peer_relative"]["market_cap"]["percentile"] >= 0.75
    assert priciest["relative_research_state"] not in {"ATTRACTIVE_RELATIVE_RESEARCH", "EXPENSIVE_RELATIVE_RESEARCH"}
    assert cheapest["relative_research_state"] == "UNAVAILABLE"


def test_infer_stance_examples_do_not_default_to_wait():
    def opportunity(entry, profit="PROFITABLE", relative="ATTRACTIVE_RELATIVE_RESEARCH"):
        return {
            "ticker": "X", "as_of_session": DECISION,
            "fundamental": {"research_usable": True, "state": profit, "trajectory": "PROFIT_GROWTH", "readiness": "READY_RESEARCH_PROXY"},
            "tactical": {"research_usable": True, "primary_entry_state": entry, "entry_action": "EARLY_ENTRY",
                         "confirmation": {"status": "READY"}, "invalidation": {"status": "READY"}},
            "valuation": {"peer_relative_context": {"relative_research_state": relative}, "share_basis": CURRENT_SHARE_RESEARCH_PROXY},
            "liquidity": {"readiness": "LIQUIDITY_RESEARCH_PROXY", "exact_execution_capacity_status": "EXECUTION_CAPACITY_EXACT_BLOCKED"},
            "downside_invalidation": {"technical": {"status": "READY"}, "fundamental": {"status": "CONDITIONAL"}, "thesis_conflict": []},
        }
    assert infer_research_stance(opportunity("EARLY_REVERSAL_CANDIDATE"))["research_stance"] == "INITIATE_RESEARCH_CANDIDATE"
    assert infer_research_stance(opportunity("DOWNTREND"))["research_stance"] == "AVOID_NEW_ENTRY"
    assert infer_research_stance(opportunity("EARLY_REVERSAL_CANDIDATE", profit="LOSS_MAKING"))["research_stance"] == "HIGH_RISK_SPECULATION_ONLY"
    assert infer_research_stance(opportunity("BASE_BUILDING"))["research_stance"] == "ACCUMULATE_RESEARCH_CANDIDATE"


# ---------------------------------------------------------------------------
# Decision-quality corrective pass (INVESTMENT_DECISION_WORKSPACE_V1 bounded correction):
# confirmation semantics, fundamental/tactical missingness handling.
# ---------------------------------------------------------------------------

def _stance_input(entry, *, profit="PROFITABLE", relative="ATTRACTIVE_RELATIVE_RESEARCH", confirmation=None,
                  tac_usable=True, fund_usable=True, setup_tags=None):
    return {
        "ticker": "X", "as_of_session": DECISION,
        "fundamental": {"research_usable": fund_usable, "state": profit, "trajectory": "PROFIT_GROWTH", "readiness": "READY_RESEARCH_PROXY"},
        "tactical": {"research_usable": tac_usable, "primary_entry_state": entry, "entry_action": None,
                     "confirmation": confirmation or {}, "invalidation": {"status": "READY"}, "setup_tags": list(setup_tags or [])},
        "valuation": {"peer_relative_context": {"relative_research_state": relative}, "share_basis": CURRENT_SHARE_RESEARCH_PROXY},
        "liquidity": {"readiness": "LIQUIDITY_RESEARCH_PROXY", "exact_execution_capacity_status": "EXECUTION_CAPACITY_EXACT_BLOCKED"},
        "downside_invalidation": {"technical": {"status": "READY"}, "fundamental": {"status": "CONDITIONAL"}, "thesis_conflict": []},
    }


def test_breakout_ready_merely_instrumented_boundary_cannot_alone_initiate():
    # status == READY only means the boundary is instrumented (a real baseline value/operator
    # exists); it is not evidence the trigger fired. A merely-instrumented boundary must preserve
    # the existing WAIT_FOR_CONFIRMATION path, never promote straight to INITIATE.
    result = infer_research_stance(_stance_input("BREAKOUT_READY", confirmation={"status": "READY"}))
    assert result["research_stance"] == "WAIT_FOR_CONFIRMATION"
    assert "BREAKOUT_READY_AWAITING_CONFIRMATION" in result["reasons"]


def test_breakout_ready_actual_trigger_state_promotes_to_initiate():
    result = infer_research_stance(_stance_input("BREAKOUT_READY", confirmation={"status": "READY", "current_trigger_state": "TRIGGERED"}))
    assert result["research_stance"] == "INITIATE_RESEARCH_CANDIDATE"
    result2 = infer_research_stance(_stance_input("BREAKOUT_READY", confirmation={"status": "TRIGGERED"}))
    assert result2["research_stance"] == "INITIATE_RESEARCH_CANDIDATE"


def test_breakout_ready_conditional_or_unavailable_boundary_also_waits():
    for status in ("CONDITIONAL", "UNAVAILABLE"):
        result = infer_research_stance(_stance_input("BREAKOUT_READY", confirmation={"status": status}))
        assert result["research_stance"] == "WAIT_FOR_CONFIRMATION"


def test_constructive_tactical_with_fundamental_missing_is_insufficient_not_high_risk():
    # Missing/unusable fundamental evidence is not an observed weak fundamental.
    result = infer_research_stance(_stance_input("BASE_BUILDING", fund_usable=False))
    assert result["research_stance"] == "INSUFFICIENT_EVIDENCE"
    assert result["research_stance"] != "HIGH_RISK_SPECULATION_ONLY"


def test_constructive_tactical_with_observed_weak_fundamental_stays_high_risk():
    # Regression guard: an actually-observed loss-making fundamental combined with constructive
    # tactical evidence must still be reserved for HIGH_RISK_SPECULATION_ONLY.
    result = infer_research_stance(_stance_input("BASE_BUILDING", profit="LOSS_MAKING"))
    assert result["research_stance"] == "HIGH_RISK_SPECULATION_ONLY"


def test_tactical_not_current_with_usable_fundamental_waits_not_insufficient():
    result = infer_research_stance(_stance_input(None, tac_usable=False, fund_usable=True))
    assert result["research_stance"] == "WAIT_FOR_CONFIRMATION"
    assert "TACTICAL_AXIS_NOT_CURRENT" in result["reasons"]


def test_expensive_relative_research_not_silently_omitted_from_counter_thesis():
    # ACCUMULATE via BASE_BUILDING + usable fundamental, but valuation is expensive: the conflict
    # must survive into key_counter_thesis, not disappear.
    result = infer_research_stance(_stance_input("BASE_BUILDING", relative="EXPENSIVE_RELATIVE_RESEARCH"))
    assert result["research_stance"] == "ACCUMULATE_RESEARCH_CANDIDATE"
    assert "EXPENSIVE_RELATIVE_RESEARCH" in result["counter_thesis"]


def test_attractive_relative_research_surfaces_in_why_when_constructive():
    result = infer_research_stance(_stance_input("BASE_BUILDING", relative="ATTRACTIVE_RELATIVE_RESEARCH"))
    assert "ATTRACTIVE_RELATIVE_RESEARCH" in result["reasons"]


def test_avoid_new_entry_shows_positive_fundamental_as_counterbalancing_not_as_veto_reason():
    result = infer_research_stance(_stance_input("DOWNTREND", profit="PROFITABLE"))
    assert result["research_stance"] == "AVOID_NEW_ENTRY"
    assert "PROFITABLE_FUNDAMENTAL" in result["counterbalancing_context"]
    assert "PROFITABLE_FUNDAMENTAL" not in result["reasons"]


def test_wait_for_confirmation_with_loss_making_fundamental_carries_weakness_in_why_and_counter_thesis():
    result = infer_research_stance(_stance_input("SIDEWAYS_NEUTRAL", profit="LOSS_MAKING"))
    assert result["research_stance"] == "WAIT_FOR_CONFIRMATION"
    assert "LOSS_MAKING" in result["reasons"]
    assert "LOSS_MAKING" in result["counter_thesis"]
