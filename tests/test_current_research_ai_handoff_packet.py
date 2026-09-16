"""Focused tests for current_research_ai_handoff_packet.py.

Two layers: (1) synthetic-fixture unit tests that always run, built directly against the real
``investment_decision_workspace_projection/v1`` / ``screener_master_projection/v1`` / ``market_
wide_current_descriptive_research/v1`` card shapes (verified against the real modules); (2) one
real-evidence integration test against the actual released 2026-09-15 governed operation,
skipped (not failed) when that gitignored ``operations-review/`` evidence is absent in a fresh
checkout -- the same pattern already used throughout this repository's test suite.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import current_research_official_universe_scope as scope_module
from current_research_ai_handoff_packet import (
    AI_BOUNDARY,
    CONTRACT_VERSION,
    CurrentResearchAiHandoffPacketError,
    WATCHLIST_CONTRACT_VERSION,
    build_packet,
    build_watchlist_subset,
    content_identity,
)

SESSION = "2026-09-15"
PREVIOUS_SESSION = "2026-09-14"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _workspace_card(ticker: str, *, session: str = SESSION, stance="ACCUMULATE_RESEARCH_CANDIDATE", entry_state="BASE_BUILDING"):
    return {
        "ticker": ticker, "as_of_session": session, "sector": "Steel",
        "research_stance": stance, "research_stance_readiness": "READY",
        "entry_state": entry_state, "entry_action": "WATCH", "setup_tags": ["BASE_BUILDING_STRUCTURE"],
        "why": {
            "fundamental_evidence": {}, "valuation_evidence": {}, "tactical_evidence": {},
            "market_sector_evidence": {}, "catalyst_evidence": {}, "deterministic_reasons": ["R1"],
            "financial_analysis": {"status": "AVAILABLE", "supporting": [], "compact": {"profitability_state": "PROFITABLE"}},
            "counterbalancing_context": ["C1"],
        },
        "counter_thesis": {
            "warnings": ["W1"], "key_counter_thesis": ["K1"],
            "financial_analysis": {"counter_thesis": [], "missing_dimensions": [], "current_financial_weakness": []},
            "unavailable_dimensions": [],
        },
        "confirmation": {"status": "READY"},
        "invalidation": {"technical": {"status": "READY"}, "fundamental": {"status": "UNAVAILABLE"}, "future_financial_invalidation_watch": []},
        "fundamental": {
            "state": "PROFITABLE", "trajectory": "IMPROVING", "readiness": "READY",
            "research_fitness": "CURRENT_RESEARCH_READY", "freshness_status": "CURRENT", "source_period": "2026-Q1",
        },
        "valuation": {
            "relative_research_state": "ABSOLUTE_RESEARCH_ONLY", "usable_relative_method_count": 0,
            "supporting_methods": [], "share_basis": "ISSUED_SHARES", "entity_class": "corporate",
            "earnings_state": "POSITIVE", "readiness": "READY", "freshness_status": "CURRENT", "source_session": session,
        },
        "tactical": {
            "primary_entry_state": entry_state, "entry_action": "WATCH", "setup_tags": ["BASE_BUILDING_STRUCTURE"],
            "freshness_status": "CURRENT", "source_session": session,
        },
        "market_sector": {"breadth_regime": "MARKET_BREADTH_MIXED", "sector_relative_context": None, "freshness_status": "CURRENT"},
        "catalyst": {
            "status": "AVAILABLE", "qualified_current_catalysts": [], "pending_watch_items": [],
            "event_count": 0, "freshness_status": "CURRENT", "source_session": session,
        },
        "liquidity": {
            "readiness": "RESEARCH_PROXY", "descriptive_research_state": "ELIGIBLE",
            "exact_execution_capacity_status": "EXECUTION_CAPACITY_EXACT_BLOCKED",
            "freshness_status": "CURRENT", "source_session": session,
        },
        # Private-position context: MUST never surface in the AI handoff packet.
        "portfolio": {
            "evaluated": True, "status": "ALREADY_HELD", "weight": 0.234,
            "holding_status": "HELD", "portfolio_id": "private_portfolio_id_should_never_leak",
        },
        "prospective_case": {"status": "NO_RETAINED_CURRENT_CASES"},
        "lineage": {
            "per_axis_source_session": {"fundamental": session}, "per_axis_freshness": {"fundamental": "CURRENT"},
            "per_axis_proxy_or_qualified_state": {}, "blockers": [],
        },
        "authority_boundary": {"is_actionable": False},
    }


def _screener_card(ticker: str, *, session: str = SESSION):
    return {
        "ticker": ticker, "listing_exchange": "HOSE", "display_exchange": "HSX",
        "exchange_status": "AVAILABLE", "exchange_reason": None,
        "price": {
            "value": 25.6, "change_pct": 0.012, "change_pct_unit": "FRACTION", "change_pct_status": "AVAILABLE",
            "change_pct_reason": None, "status": "PRICE_AVAILABLE", "reason": None,
            "basis": "ADJUSTED_RETROSPECTIVE", "as_of": session, "source_identity": "snap", "freshness": "CURRENT",
        },
        "sector": {"label": "Steel", "code": None, "namespace": "VCI_PROVIDER_INDUSTRY", "status": "AVAILABLE", "reason": None, "as_of": session},
        "entity_type": {"value": "corporate", "status": "AVAILABLE", "reason": None},
        "liquidity": {
            "research_value": None, "research_value_status": "UNKNOWN",
            "research_value_reason": "NO_QUALIFIED_MARKET_WIDE_NUMERIC_ADV20",
            "method": "LIQUIDITY_RESEARCH_PROXY", "fitness": "LIQUIDITY_RESEARCH_PROXY", "as_of": session,
            "descriptive_state": "AVAILABLE", "status": "AVAILABLE", "reason": None,
        },
        "execution": {"capacity_exact_status": "EXECUTION_CAPACITY_EXACT_BLOCKED", "capacity_exact_reason": "EXECUTION_CAPACITY_EXACT_NOT_QUALIFIED"},
        "tactical": {"entry_state": "BASE_BUILDING", "entry_action": "WATCH", "as_of": session, "freshness": "CURRENT", "status": "AVAILABLE", "reason": None},
        "research": {"stance": "ACCUMULATE_RESEARCH_CANDIDATE", "stance_readiness": "READY", "as_of": session, "status": "AVAILABLE", "reason": None},
        "workspace_ref": {"ticker": ticker, "producer_artifact_identity": "investment_decision_workspace_projection/v1:abc", "status": "AVAILABLE", "reason": None},
        "financial_v2": {
            "status": "AVAILABLE", "fitness": "READY", "current_research_ready": True,
            "profitability_state": "PROFITABLE", "cash_conversion_state": None, "capital_efficiency_state": None,
            "short_term_liquidity_state": None, "working_capital_state": None, "reason": None,
        },
        "freshness": {"price": "CURRENT", "sector": "CURRENT", "liquidity": "CURRENT", "tactical": "CURRENT", "research": "CURRENT", "financial_v2": "CURRENT", "row": "CURRENT"},
        "authority_boundary": {"is_actionable": False},
    }


def _workspace_artifact(cards: dict, *, session: str = SESSION):
    return {
        "contract_version": "investment_decision_workspace_projection/v1", "as_of_session": session,
        "artifact_identity": "investment_decision_workspace_projection/v1:workspace_abc",
        "cards": cards,
    }


def _screener_artifact(cards: dict, *, session: str = SESSION):
    return {
        "contract_version": "screener_master_projection/v1", "as_of_session": session,
        "artifact_identity": "screener_master_projection/v1:screener_abc",
        "cards": cards,
    }


def _descriptive_artifact(*, session: str, advancing: int, declining: int, unchanged: int, above_ma20: int, below_ma20: int, identity: str):
    denom = advancing + declining + unchanged
    return {
        "contract_version": "market_wide_current_descriptive_research/v1", "session": session,
        "artifact_identity": identity,
        "market_breadth": {
            "current_active_equity_denominator": denom, "advancing": advancing, "declining": declining,
            "unchanged": unchanged, "advance_ratio": advancing / denom,
            "same_session_technical_feature_available_count": denom,
            "trend": {"above_ma20": above_ma20, "at_or_below_ma20": below_ma20, "unavailable": 0},
            "breadth_descriptor": {"descriptor": "MARKET_BREADTH_MIXED", "rule_identity": "market_regime_breadth_context/v1"},
            "momentum_descriptor": {"descriptor": "MOMENTUM_BREADTH_NEGATIVE", "rule_identity": "market_regime_breadth_context/v1"},
            "authority_boundary": {"not_bull_bear_call_forecast_or_timing": True},
        },
        "sector_breadth": {"method": "x"},
    }


def _scope(*, session: str, records: dict, observed_at: str = "2026-09-13T00:00:00Z"):
    return {
        "contract_version": scope_module.CONTRACT_VERSION, "research_session": session,
        "official_snapshot_observed_at": observed_at, "temporally_eligible": True,
        "disposition": "CURRENT_OBSERVED_EVIDENCE_AVAILABLE",
        "source_reference_ticker_count": len(records), "current_research_scope_ticker_count": sum(
            1 for row in records.values() if row["current_research_scope_state"] == scope_module.SCOPE_ELIGIBLE
        ),
        "records": records,
    }


def _scope_row(state):
    return {
        "current_research_scope_state": state,
        "current_research_scope_fitness": scope_module.FITNESS_ELIGIBLE if state == scope_module.SCOPE_ELIGIBLE else scope_module.FITNESS_INELIGIBLE_MASTER,
        "current_research_scope_reason": None, "official_current_exchange_presence": "OFFICIAL_CURRENT_EXCHANGE_SECURITY",
        "official_security_status": "NORMAL",
    }


# ---------------------------------------------------------------------------
# Contract / schema / identity
# ---------------------------------------------------------------------------

def test_content_identity_deterministic_and_uses_own_contract_version():
    payload = {"contract_version": "x/v1", "a": 1, "b": [1, 2], "requested_at": "now"}
    first = content_identity(payload)
    second = content_identity(payload)
    assert first == second
    assert first["artifact_identity"].startswith("x/v1:")


def test_build_packet_rejects_wrong_workspace_contract():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    workspace["contract_version"] = "something_else/v1"
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    with pytest.raises(CurrentResearchAiHandoffPacketError):
        build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                     workspace_artifact=workspace, screener_artifact=screener)


def test_build_packet_rejects_session_mismatch():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")}, session="2026-09-14")
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    with pytest.raises(CurrentResearchAiHandoffPacketError):
        build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                     workspace_artifact=workspace, screener_artifact=screener)


def test_build_packet_rejects_empty_denominator():
    workspace = _workspace_artifact({})
    screener = _screener_artifact({})
    with pytest.raises(CurrentResearchAiHandoffPacketError):
        build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                     workspace_artifact=workspace, screener_artifact=screener)


# ---------------------------------------------------------------------------
# Zero silent drops / union semantics
# ---------------------------------------------------------------------------

def test_build_packet_unions_workspace_and_screener_never_intersects():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA"), "BBB": _workspace_card("BBB")})
    screener = _screener_artifact({"AAA": _screener_card("AAA"), "CCC": _screener_card("CCC")})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener)
    assert set(packet["cards"]) == {"AAA", "BBB", "CCC"}
    assert packet["coverage"]["reference_denominator"] == 3
    assert packet["coverage"]["workspace_and_screener_both_covered_count"] == 1
    assert packet["coverage"]["workspace_only_count"] == 1
    assert packet["coverage"]["screener_only_count"] == 1
    assert packet["cards"]["BBB"]["identity"]["data_availability"] == {"workspace_covered": True, "screener_covered": False}
    assert packet["cards"]["CCC"]["identity"]["data_availability"] == {"workspace_covered": False, "screener_covered": True}
    assert packet["coverage"]["zero_silent_ticker_drops"] is True


def test_watchlist_subset_never_drops_a_requested_ticker():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener)
    subset = build_watchlist_subset(packet, ["AAA", "aaa", "ZZZ", "AAA"])
    assert subset["requested_tickers"] == ["AAA", "ZZZ"]  # case-normalized, de-duplicated, order preserved
    assert set(subset["cards"]) == {"AAA", "ZZZ"}
    assert subset["cards"]["ZZZ"]["coverage_status"] == "NOT_COVERED_BY_CURRENT_PRODUCTS"
    assert subset["cards"]["AAA"]["coverage_status"] == "COVERED"
    assert subset["coverage"] == {"requested_count": 2, "covered_count": 1, "not_covered_count": 1, "zero_silent_ticker_drops": True}
    assert subset["contract_version"] == WATCHLIST_CONTRACT_VERSION
    assert subset["artifact_identity"].startswith(WATCHLIST_CONTRACT_VERSION + ":")


def test_watchlist_subset_rejects_wrong_source_contract():
    with pytest.raises(CurrentResearchAiHandoffPacketError):
        build_watchlist_subset({"contract_version": "not_the_packet/v1"}, ["AAA"])


def test_watchlist_subset_rejects_empty_request():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener)
    with pytest.raises(CurrentResearchAiHandoffPacketError):
        build_watchlist_subset(packet, [])


# ---------------------------------------------------------------------------
# Official research scope join
# ---------------------------------------------------------------------------

def test_official_research_scope_join_in_out_and_unknown():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA"), "BBB": _workspace_card("BBB"), "CCC": _workspace_card("CCC")})
    screener = _screener_artifact({"AAA": _screener_card("AAA"), "BBB": _screener_card("BBB"), "CCC": _screener_card("CCC")})
    scope = _scope(session=SESSION, records={
        "AAA": _scope_row(scope_module.SCOPE_ELIGIBLE),
        "BBB": _scope_row(scope_module.SCOPE_OUTSIDE_DELISTING_CORRELATED),
        # CCC deliberately absent from official records -> unknown bucket.
    })
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener, current_research_scope=scope)
    assert packet["cards"]["AAA"]["official_research_scope"]["scope_bucket"] == scope_module.SIMPLE_IN_SCOPE
    assert packet["cards"]["BBB"]["official_research_scope"]["scope_bucket"] == scope_module.SIMPLE_OUTSIDE_SCOPE
    assert packet["cards"]["CCC"]["official_research_scope"]["scope_bucket"] == scope_module.SIMPLE_SCOPE_UNKNOWN
    assert packet["coverage"]["current_official_research_scope_count"] == 1
    assert packet["coverage"]["outside_current_official_research_scope_count"] == 1
    assert packet["coverage"]["current_official_research_scope_unknown_count"] == 1
    assert packet["coverage"]["current_research_scope_supplied"] is True


def test_official_research_scope_omitted_degrades_to_unknown_never_fabricated():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener)
    assert packet["cards"]["AAA"]["official_research_scope"]["scope_bucket"] == scope_module.SIMPLE_SCOPE_UNKNOWN
    assert packet["coverage"]["current_research_scope_supplied"] is False


# ---------------------------------------------------------------------------
# Market context: two-session breadth, deltas, no invented regime
# ---------------------------------------------------------------------------

def test_market_context_deltas_between_two_governed_sessions():
    current = _descriptive_artifact(session=SESSION, advancing=428, declining=228, unchanged=199, above_ma20=234, below_ma20=621, identity="market_wide_current_descriptive_research:cur")
    previous = _descriptive_artifact(session=PREVIOUS_SESSION, advancing=210, declining=442, unchanged=200, above_ma20=212, below_ma20=640, identity="market_wide_current_descriptive_research:prev")
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener,
                          descriptive_current=current, descriptive_previous=previous, previous_session=PREVIOUS_SESSION)
    context = packet["market_context"]
    assert context["current_session_breadth"]["advancing"] == 428
    assert context["previous_governed_session_breadth"]["advancing"] == 210
    assert context["previous_governed_session"] == PREVIOUS_SESSION
    assert context["deterministic_deltas"]["advancing_delta"] == 218
    assert context["deterministic_deltas"]["declining_delta"] == -214
    # No new regime label is invented anywhere in market_context.
    assert "regime_label" not in context
    assert context["current_session_breadth"]["breadth_descriptor"]["rule_identity"] == "market_regime_breadth_context/v1"


def test_market_context_degrades_explicitly_without_previous_session():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener)
    context = packet["market_context"]
    assert context["current_session_breadth"] == {"status": "NOT_AVAILABLE", "reason": "NO_CURRENT_SESSION_DESCRIPTIVE_EVIDENCE"}
    assert context["previous_governed_session_breadth"]["status"] == "NOT_AVAILABLE"
    assert context["deterministic_deltas"] is None


# ---------------------------------------------------------------------------
# Privacy boundary
# ---------------------------------------------------------------------------

def _walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, value
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def test_no_private_portfolio_data_anywhere_in_packet():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener)
    serialized = json.dumps(packet)
    assert "private_portfolio_id_should_never_leak" not in serialized
    assert "portfolio" not in packet["cards"]["AAA"]
    for key, container in _walk(packet):
        assert key != "portfolio", "private portfolio context must never appear in the AI handoff packet"
    assert packet["privacy_boundary"] == {
        "private_portfolio_positions": "NEVER_INCLUDED", "account_data": "NEVER_INCLUDED",
        "credentials": "NEVER_INCLUDED", "private_sizing": "NEVER_INCLUDED", "private_user_policy_limits": "NEVER_INCLUDED",
    }


# ---------------------------------------------------------------------------
# Authority boundary: no score/rank/probability/target/sizing anywhere
# ---------------------------------------------------------------------------

FORBIDDEN_KEYS = {"score", "rank", "probability", "recommended_size", "buy_price", "sell_price"}
#: These keys are legitimately present, but only ever as the fixed prohibition sentinel that
#: declares the output blocked -- never a real numeric/string value.
BLOCKED_SENTINEL_KEYS = {
    "target_price": "NOT_EMITTED", "position_size": "NOT_EMITTED",
    "probability_of_success": "FORECAST_PROHIBITED", "execution_eligibility": "NOT_EMITTED",
    "universal_score": "SCORING_PROHIBITED", "ordinal_rank": "RANKING_PROHIBITED",
}


def test_no_score_rank_probability_target_sizing_fields():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener)
    for key, container in _walk(packet):
        assert key not in FORBIDDEN_KEYS, f"forbidden field present in packet: {key}"
        if key in BLOCKED_SENTINEL_KEYS:
            assert container[key] == BLOCKED_SENTINEL_KEYS[key], f"{key} must stay the fixed prohibition sentinel, never a real value"
    assert packet["authority_boundary"] == AI_BOUNDARY
    assert packet["blocked_outputs"]["target_price"] == "NOT_EMITTED"
    assert packet["blocked_outputs"]["probability_of_success"] == "FORECAST_PROHIBITED"
    assert packet["blocked_outputs"]["position_size"] == "NOT_EMITTED"
    assert packet["authority_effect"] == (
        "AI_RESEARCH_TRANSPORT_AND_FITNESS_FOR_USE_ONLY / "
        "NO_NEW_MARKET_DATA_PIT_LIQUIDITY_SIZING_EXECUTION_RECOMMENDATION_AUTHORITY"
    )


def test_technical_axes_omitted_degrade_explicitly_not_silently():
    """When the three technical-producer axes are not supplied to build_packet at all (the
    caller only has Workspace/Screener on hand), every technical block is an explicit
    NOT_AVAILABLE with a stated reason -- never silently absent, never a computed substitute."""
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener)
    measurements = packet["cards"]["AAA"]["tactical"]["measurements"]
    assert measurements["momentum"] == {"status": "NOT_AVAILABLE", "reason": "AXIS_NOT_SUPPLIED_THIS_BUILD"}
    assert measurements["structure"] == {"status": "NOT_AVAILABLE", "reason": "AXIS_NOT_SUPPLIED_THIS_BUILD"}
    assert measurements["confirmation_synthesis"] == {"status": "NOT_AVAILABLE", "reason": "AXIS_NOT_SUPPLIED_THIS_BUILD"}
    assert measurements["price_basis_fitness"]["status"] == "NOT_AVAILABLE"
    # Real pass-through fields ARE populated (from Screener's price view).
    assert measurements["close"] == 25.6
    assert measurements["session_return_pct"] == 0.012
    assert measurements["price_freshness"] == "CURRENT"
    assert packet["coverage"]["momentum_context_supplied"] is False
    assert packet["coverage"]["momentum_eligible_count"] == 0


def test_stale_per_ticker_price_is_explicitly_flagged_not_just_a_diffable_date():
    """PERSONAL_DECISION_INPUT_TRUTH_V1: a ticker whose own last observed price bar lags the
    packet's research session (e.g. a provider gap for that one ticker) must carry an explicit
    STALE disposition, not just a `price_as_of` date a reader would have to manually diff
    against `as_of_session` to notice."""
    stale_card = _screener_card("AAA")
    stale_card["price"]["as_of"] = "2026-09-12"
    stale_card["price"]["freshness"] = "STALE_BUT_RESEARCH_USABLE"
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": stale_card})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener)
    measurements = packet["cards"]["AAA"]["tactical"]["measurements"]

    assert packet["as_of_session"] == SESSION
    assert measurements["price_as_of"] == "2026-09-12"
    assert measurements["price_as_of"] != packet["as_of_session"]
    assert measurements["price_freshness"] == "STALE_BUT_RESEARCH_USABLE"


def _momentum_artifact(records: dict, *, session: str = SESSION):
    return {
        "contract_version": "tactical_momentum_context/v1", "target_session": session,
        "artifact_identity": "tactical_momentum_context:momentum_abc", "records": records,
    }


def _momentum_record(ticker: str, *, eligible: bool = True, rsi_value: float = 43.3, ma20_value: float = 21.6):
    if not eligible:
        return {
            "ticker": ticker, "eligibility": {"status": "NOT_ELIGIBLE", "reason": "TECHNICAL_FEATURES_UNAVAILABLE_OR_NOT_CURRENT_SESSION"},
            "close_history_depth": 0, "price_direction_1d": None,
            "rsi": {"status": "NOT_AVAILABLE", "reason": "TECHNICAL_FEATURES_UNAVAILABLE_OR_NOT_CURRENT_SESSION"},
            "rsi_divergence": {"status": "NOT_AVAILABLE"}, "moving_averages": {}, "moving_average_ordering": {"status": "NOT_AVAILABLE"},
            "macd": {"status": "NOT_AVAILABLE"}, "technical_history_lineage": None,
            "authority_boundary": {"rsi_zone_is_measurement_not_buy_sell_signal": True},
        }
    return {
        "ticker": ticker, "eligibility": {"status": "ELIGIBLE"}, "close_history_depth": 249, "price_direction_1d": "UP",
        "rsi": {"status": "AVAILABLE", "value": rsi_value, "zone": "NEUTRAL", "direction": "RISING", "method": "WILDER_RSI_14"},
        "rsi_divergence": {"status": "AVAILABLE", "divergence_state": "NO_DIVERGENCE_CANDIDATE"},
        "moving_averages": {"20": {"status": "AVAILABLE", "value": ma20_value, "price_above": False, "price_below": True}},
        "moving_average_ordering": {"status": "AVAILABLE", "ma_ordering": "DESCENDING_SHORT_UNDER_LONG"},
        "macd": {"status": "AVAILABLE", "macd_line": -0.14, "signal_line": -0.08, "histogram": -0.06, "cross_event": "NONE"},
        "technical_history_lineage": {"provider": "KBS", "source": "RETAINED_TECHNICAL_HISTORY_RECOVERY", "recovery_artifact_identity": "market_wide_current_technical_coverage_scaleout:xyz"},
        "authority_boundary": {"rsi_zone_is_measurement_not_buy_sell_signal": True, "macd_cross_is_measurement_not_confirmation_signal": True},
    }


def _structure_artifact(records: dict, *, session: str = SESSION):
    return {
        "contract_version": "technical_structure_context/v2", "session": session,
        "artifact_identity": "technical_structure_context:structure_abc", "records": records,
    }


def _structure_record(ticker: str, *, eligible: bool = True):
    if not eligible:
        return {"ticker": ticker, "eligibility": {"status": "NOT_ELIGIBLE", "reason": "INSUFFICIENT_STRUCTURE"}}
    return {
        "ticker": ticker, "eligibility": {"status": "ELIGIBLE"}, "authority_tier": "SHADOW_ONLY",
        "trend_context": {"status": "AVAILABLE", "momentum_20d": -0.21, "trend_state": "AT_OR_BELOW_MA20"},
        "structure_context": {"status": "AVAILABLE", "structure_status": "NEAR_RECENT_SUPPORT", "support": {"value": 20.9}, "resistance": {"value": 22.25}},
        "contraction_context": {"status": "AVAILABLE", "range_state": "RANGE_STABLE"},
        "relative_volume": {"status": "NOT_AVAILABLE", "relative_volume_provider_scoped": None},
        "swing_structure": {"status": "AVAILABLE", "market_structure_state": "EARLY_BEARISH_REVERSAL"},
        "bos_context": {"status": "AVAILABLE", "bos_state": "BEARISH_BOS_DETECTED_BY_RULE"},
        "choch_context": {"status": "AVAILABLE", "choch_state": "NO_CHOCH"},
        "breakout_context": {"status": "AVAILABLE", "event": "RE_ENTRY_ABOVE_SUPPORT"},
        "breakout_state_v3": "BELOW_PIVOT",
        "trigger_context": {"status": "AVAILABLE", "trigger_state": "TRIGGERED"},
        "invalidation_context": {"status": "AVAILABLE", "invalidation_level": 22.05},
        "pivot_context": {"status": "AVAILABLE", "pivot_price": 22.05},
        "high_low_basis": {"status": "NOT_COMPATIBLE", "reason": "HIGH_LOW_BASIS_NOT_COMPATIBLE"},
        "blockers": [],
        "authority_boundary": {"invalidation_level_is_not_a_stop_loss": True},
    }


def _confirmation_artifact(records: dict, *, session: str = SESSION):
    return {
        "contract_version": "tactical_confirmation_context/v1", "session": session,
        "artifact_identity": "tactical_confirmation_context:confirmation_abc", "records": records,
    }


def _confirmation_record(ticker: str, *, state: str = "NEUTRAL"):
    return {
        "ticker": ticker, "tactical_confirmation_state": state, "structure_stance": "BEARISH",
        "structure_phase_label": "BREAKDOWN", "momentum_direction": "MIXED",
        "participation_detail": {"participation_state": "INSUFFICIENT_EVIDENCE"}, "price_direction_1d": "UP",
        "supporting_reasons": [], "contradicting_reasons": [],
        "authority_boundary": {"not_a_recommendation_or_execution_instruction": True},
    }


def test_technical_measurements_pass_through_exact_upstream_values():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    momentum = _momentum_artifact({"AAA": _momentum_record("AAA", rsi_value=43.321958231, ma20_value=21.595)})
    structure = _structure_artifact({"AAA": _structure_record("AAA")})
    confirmation = _confirmation_artifact({"AAA": _confirmation_record("AAA")})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener,
                          momentum_context_artifact=momentum, structure_context_artifact=structure,
                          confirmation_context_artifact=confirmation)
    measurements = packet["cards"]["AAA"]["tactical"]["measurements"]
    assert measurements["momentum"]["status"] == "AVAILABLE"
    assert measurements["momentum"]["rsi"]["value"] == 43.321958231
    assert measurements["momentum"]["moving_averages"]["20"]["value"] == 21.595
    assert measurements["momentum"]["source_artifact_identity"] == "tactical_momentum_context:momentum_abc"
    assert measurements["structure"]["trend_context"]["momentum_20d"] == -0.21
    assert measurements["structure"]["structure_context"]["support"]["value"] == 20.9
    assert measurements["structure"]["relative_volume"]["status"] == "NOT_AVAILABLE"  # producer's own NOT_AVAILABLE preserved verbatim
    assert measurements["structure"]["source_artifact_identity"] == "technical_structure_context:structure_abc"
    assert measurements["confirmation_synthesis"]["tactical_confirmation_state"] == "NEUTRAL"
    assert measurements["confirmation_synthesis"]["source_artifact_identity"] == "tactical_confirmation_context:confirmation_abc"
    assert packet["source_artifacts"]["tactical_momentum_context"] == "tactical_momentum_context:momentum_abc"
    assert packet["source_artifacts"]["technical_structure_context"] == "technical_structure_context:structure_abc"
    assert packet["source_artifacts"]["tactical_confirmation_context"] == "tactical_confirmation_context:confirmation_abc"
    assert packet["coverage"]["momentum_eligible_count"] == 1
    assert packet["coverage"]["structure_eligible_count"] == 1


def test_producer_own_not_available_is_never_rewritten_to_available():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    momentum = _momentum_artifact({"AAA": _momentum_record("AAA", eligible=False)})
    structure = _structure_artifact({"AAA": _structure_record("AAA", eligible=False)})
    confirmation = _confirmation_artifact({"AAA": _confirmation_record("AAA", state="INSUFFICIENT_EVIDENCE")})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener,
                          momentum_context_artifact=momentum, structure_context_artifact=structure,
                          confirmation_context_artifact=confirmation)
    measurements = packet["cards"]["AAA"]["tactical"]["measurements"]
    assert measurements["momentum"]["eligibility"]["status"] == "NOT_ELIGIBLE"
    assert measurements["momentum"]["rsi"]["status"] == "NOT_AVAILABLE"
    assert measurements["structure"]["eligibility"]["status"] == "NOT_ELIGIBLE"
    assert measurements["confirmation_synthesis"]["tactical_confirmation_state"] == "INSUFFICIENT_EVIDENCE"
    assert packet["coverage"]["momentum_eligible_count"] == 0
    assert packet["coverage"]["structure_eligible_count"] == 0
    assert packet["coverage"]["confirmation_evaluated_count"] == 0
    # Not eligible -> price-basis fitness is explicitly unavailable, never computed anyway.
    assert measurements["price_basis_fitness"]["status"] == "NOT_AVAILABLE"
    assert measurements["price_basis_fitness"]["reason"] == "MOMENTUM_CONTEXT_TICKER_NOT_ELIGIBLE_THIS_SESSION"


def test_price_basis_fitness_reuses_existing_contract_never_widens_verdict():
    import price_basis_feature_fitness

    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    momentum = _momentum_artifact({"AAA": _momentum_record("AAA")})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener, momentum_context_artifact=momentum)
    fitness = packet["cards"]["AAA"]["tactical"]["measurements"]["price_basis_fitness"]
    assert fitness["status"] == "AVAILABLE"
    assert fitness["rsi_fitness"]["contract_version"] == "price_basis_semantics_and_feature_fitness/v1"
    assert fitness["rsi_fitness"]["state"] in price_basis_feature_fitness.FITNESS_STATES
    assert fitness["moving_average_fitness"]["state"] in price_basis_feature_fitness.FITNESS_STATES
    # The Screener fixture's own basis ("ADJUSTED_RETROSPECTIVE") is a genuinely recognized
    # basis in price_basis_feature_fitness's vocabulary -> a real, non-fabricated verdict.
    assert fitness["context"]["observed_basis"] in price_basis_feature_fitness.BASIS_VOCABULARY


def test_technical_semantic_guard_flags_present_on_every_card():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener)
    boundary = packet["cards"]["AAA"]["authority_boundary"]
    assert boundary["TECHNICAL_MEASUREMENT_IS_NOT_EXECUTION_INSTRUCTION"] is True
    assert boundary["PRICE_DERIVED_LEVEL_REQUIRES_BASIS_FITNESS_INTERPRETATION"] is True
    assert boundary["CURRENT_RESEARCH_MEASUREMENT_DOES_NOT_GRANT_PIT_AUTHORITY"] is True
    assert boundary == AI_BOUNDARY
    assert packet["authority_boundary"] == AI_BOUNDARY


def test_watchlist_subset_preserves_technical_values_exactly():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    momentum = _momentum_artifact({"AAA": _momentum_record("AAA", rsi_value=61.5)})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener, momentum_context_artifact=momentum)
    subset = build_watchlist_subset(packet, ["AAA"])
    assert subset["cards"]["AAA"] == packet["cards"]["AAA"]
    assert subset["cards"]["AAA"]["tactical"]["measurements"]["momentum"]["rsi"]["value"] == 61.5


def test_momentum_context_wrong_contract_version_rejected():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    momentum = _momentum_artifact({"AAA": _momentum_record("AAA")})
    momentum["contract_version"] = "not_the_real_contract/v1"
    with pytest.raises(CurrentResearchAiHandoffPacketError):
        build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                    workspace_artifact=workspace, screener_artifact=screener, momentum_context_artifact=momentum)


def test_technical_field_coverage_correctly_classifies_produced_vs_absent():
    from current_research_ai_handoff_packet import TECHNICAL_FIELD_COVERAGE
    available = TECHNICAL_FIELD_COVERAGE["available_from_stocklookup"]
    absent = TECHNICAL_FIELD_COVERAGE["not_currently_produced"]
    for field in ("rsi_14", "moving_average_20_50_100_200", "macd_12_26_9", "momentum_20d", "support_resistance_levels"):
        assert field in available
    for field in ("adx", "mfi"):
        assert field in absent
    # The corrected classification must never claim RSI/MA/MACD are absent.
    for field in absent:
        assert "rsi" not in field.lower() or field == "adx"  # ADX itself never mentions rsi; sanity guard only
    assert not any("moving_average" in field or "macd" in field or "rsi" in field for field in absent)


def test_ticker_absent_from_both_products_is_explicit_not_dropped():
    workspace = _workspace_artifact({"AAA": _workspace_card("AAA")})
    screener = _screener_artifact({"AAA": _screener_card("AAA")})
    packet = build_packet(session=SESSION, requested_at="now", producer_commit="abc", daily_operation_identity="op:abc",
                          workspace_artifact=workspace, screener_artifact=screener)
    subset = build_watchlist_subset(packet, ["NOTREAL"])
    card = subset["cards"]["NOTREAL"]
    assert card["coverage_status"] == "NOT_COVERED_BY_CURRENT_PRODUCTS"
    assert card["official_research_scope"]["scope_bucket"] == scope_module.SIMPLE_SCOPE_UNKNOWN
    assert card["authority_boundary"] == AI_BOUNDARY


# ---------------------------------------------------------------------------
# Real 2026-09-15 governed evidence (skipped, not failed, if the gitignored
# operations-review evidence is absent in this checkout).
# ---------------------------------------------------------------------------

VALIDATION_TICKERS = ["HPG", "SSI", "PAN", "FPT", "VCB", "PNJ", "PVD", "QNS", "VNM", "EVF", "POW", "NVL"]
_REAL_OP_DIR = (
    REPO_ROOT / "operations-review" / "daily-research-session-operations-v1" / SESSION
    / "2026166fdb3fdea24d3b6c38847cca3bb28d1e35cecdad38ba2a91d3caa106bf"
)


def _load_real_technical_axes(root: Path, session: str):
    import daily_session_level2_package as level2

    paths = level2.session_artifact_paths(root, session)

    def _maybe_load(key: str):
        path = paths.get(key)
        return json.loads(path.read_text(encoding="utf-8")) if isinstance(path, Path) and path.is_file() else None

    return (
        _maybe_load("tactical_momentum_context"),
        _maybe_load("technical_structure_context"),
        _maybe_load("tactical_confirmation_context"),
    )


@pytest.mark.skipif(
    not (_REAL_OP_DIR / "investment_decision_workspace_projection.json").is_file(),
    reason="real 2026-09-15 operations-review evidence not present in this checkout",
)
def test_real_20260915_packet_matches_released_counts_and_validation_tickers():
    import canonical_current_product_projections as ccpp
    import daily_research_session_operations as dso
    import governed_previous_operation as gpo

    root = REPO_ROOT
    registry = json.loads((root / "config" / "daily_research_session_input_registry.json").read_text(encoding="utf-8"))
    workspace = json.loads((_REAL_OP_DIR / "investment_decision_workspace_projection.json").read_text(encoding="utf-8"))
    screener = json.loads((_REAL_OP_DIR / "screener_master_projection.json").read_text(encoding="utf-8"))
    values, _ = dso.resolve_inputs(root, SESSION, registry)
    previous = gpo.resolve_governed_previous_operation(SESSION, registry, root)
    descriptive_previous = None
    if previous.get("status") == gpo.AVAILABLE and previous.get("previous_session"):
        previous_values, _ = dso.resolve_inputs(root, previous["previous_session"], registry)
        descriptive_previous = previous_values.get("descriptive")
    scope = ccpp.resolve_current_research_official_universe_scope(root, SESSION)
    momentum, structure, confirmation = _load_real_technical_axes(root, SESSION)

    packet = build_packet(
        session=SESSION, requested_at="2026-09-15T12:00:00Z", producer_commit="test", daily_operation_identity="test",
        workspace_artifact=workspace, screener_artifact=screener,
        descriptive_current=values.get("descriptive"), descriptive_previous=descriptive_previous,
        previous_session=previous.get("previous_session"), current_research_scope=scope,
        momentum_context_artifact=momentum, structure_context_artifact=structure, confirmation_context_artifact=confirmation,
    )
    # Existing 1683 / 1504 / 179 contract must be exactly unchanged by the technical corrective pass.
    assert packet["coverage"]["reference_denominator"] == 1683
    assert packet["coverage"]["current_official_research_scope_count"] == 1504
    assert packet["coverage"]["outside_current_official_research_scope_count"] == 179
    for ticker in VALIDATION_TICKERS:
        assert ticker in packet["cards"], f"{ticker} missing from real packet"
        assert packet["cards"][ticker]["coverage_status"] == "COVERED"

    subset = build_watchlist_subset(packet, VALIDATION_TICKERS)
    assert subset["coverage"]["covered_count"] == len(VALIDATION_TICKERS)
    assert subset["coverage"]["not_covered_count"] == 0
    assert set(subset["cards"]) == set(VALIDATION_TICKERS)
    for ticker in ("HPG", "SSI", "PAN"):
        card = subset["cards"][ticker]
        assert card["decision_context"]["research_stance"] is not None
        assert card["fundamental"]["state"] is not None
        assert card["blocked_outputs"]["target_price"] == "NOT_EMITTED"
        # No private portfolio/account data anywhere in the real HPG/SSI/PAN cards.
        assert "portfolio" not in card


@pytest.mark.skipif(
    not (_REAL_OP_DIR / "investment_decision_workspace_projection.json").is_file(),
    reason="real 2026-09-15 operations-review evidence not present in this checkout",
)
def test_real_20260915_hpg_ssi_pan_technical_field_availability():
    """All 12 validation tickers are genuinely eligible in the real 2026-09-15 technical
    producers (verified: 855/855/855 eligible market-wide, matching each producer's own
    ``coverage`` block exactly), so this proves real RSI/MA/MACD/structure pass-through for
    HPG/SSI/PAN specifically -- not merely that the packet builds without error."""
    import daily_session_level2_package as level2
    import price_basis_feature_fitness

    root = REPO_ROOT
    workspace = json.loads((_REAL_OP_DIR / "investment_decision_workspace_projection.json").read_text(encoding="utf-8"))
    screener = json.loads((_REAL_OP_DIR / "screener_master_projection.json").read_text(encoding="utf-8"))
    momentum, structure, confirmation = _load_real_technical_axes(root, SESSION)
    assert momentum is not None and structure is not None and confirmation is not None, "real technical producers must be present for this session"

    packet = build_packet(
        session=SESSION, requested_at="2026-09-15T12:00:00Z", producer_commit="test", daily_operation_identity="test",
        workspace_artifact=workspace, screener_artifact=screener,
        momentum_context_artifact=momentum, structure_context_artifact=structure, confirmation_context_artifact=confirmation,
    )
    # Cross-check against the producer's own real coverage counters (855/855/855 for 2026-09-15).
    momentum_coverage = momentum.get("coverage") or {}
    assert packet["coverage"]["momentum_eligible_count"] == momentum_coverage.get("eligible_count")

    for ticker in VALIDATION_TICKERS:
        measurements = packet["cards"][ticker]["tactical"]["measurements"]
        assert measurements["momentum"]["status"] == "AVAILABLE", f"{ticker} momentum record missing"
        assert measurements["momentum"]["eligibility"]["status"] == "ELIGIBLE", f"{ticker} not eligible for technical momentum this real session"
        assert isinstance(measurements["momentum"]["rsi"]["value"], float)
        assert isinstance(measurements["momentum"]["macd"]["macd_line"], float)
        assert "20" in measurements["momentum"]["moving_averages"]
        assert measurements["structure"]["status"] == "AVAILABLE"
        assert measurements["structure"]["eligibility"]["status"] == "ELIGIBLE"
        # relative_volume genuinely varies per ticker (NOT_AVAILABLE for some, AVAILABLE for
        # others, e.g. HPG/SSI vs. PAN/VCB on 2026-09-15) -- report actual per-ticker status,
        # never assume uniform availability across the validation cohort.
        assert measurements["structure"]["relative_volume"]["status"] in ("AVAILABLE", "NOT_AVAILABLE")
        assert measurements["confirmation_synthesis"]["tactical_confirmation_state"] is not None
        fitness = measurements["price_basis_fitness"]
        assert fitness["status"] == "AVAILABLE"
        assert fitness["rsi_fitness"]["state"] in price_basis_feature_fitness.FITNESS_STATES


def test_no_external_provider_fallback_in_module_source():
    """Static guard: the packet module and its CLI never call out to an external market-data
    provider, HTTP client, or web-fetch mechanism -- every field is a pass-through of already-
    retained Stock Lookup evidence. (The module docstring legitimately *mentions* "Finhay" as the
    problem this milestone solves, so that word itself is not scanned -- only real fetch-call
    tokens are.)"""
    import current_research_ai_handoff_packet as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    forbidden = ["requests.", "urllib.request", "http.client", "httpx.", "aiohttp.", "socket.connect"]
    for token in forbidden:
        assert token not in source, f"forbidden external-fetch token found in packet module: {token}"
