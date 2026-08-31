"""Focused tests for investment_decision_workspace_projection.py."""
from __future__ import annotations

import pytest

from current_valuation_opportunity_integration import build_artifacts as build_opportunity_artifacts
from investment_decision_workspace_projection import (
    InvestmentDecisionWorkspaceError, RELATIVE_VALUATION_LABELS, build_artifacts, build_ticker_card,
    content_identity,
)

DECISION = "2026-08-28"


# ---------------------------------------------------------------------------
# Minimal fixture builders for the real upstream chain (opportunity_context +
# security_decision_context), trimmed from tests/test_current_valuation_opportunity_integration.py's
# proven-working versions -- this module's own tests build a real matched pair through the actual
# upstream module rather than hand-faking its output shape.
# ---------------------------------------------------------------------------

def _identity(kind: str) -> str:
    return f"{kind}:abc"


def _feature(status, value=None, state=None, periods=None):
    return {
        "feature_id": "x", "value": value, "categorical_state": state, "status": status,
        "method": "same_native_series_dimensionless_ratio/v1",
        "compatibility_class": "SAME_NATIVE_SERIES_RESEARCH_COMPATIBLE",
        "input_periods": list(periods or []), "blocker_reason_codes": [],
    }


def feature_record(ticker, *, profit="PROFITABLE", ni=100.0, ttm_ni=400.0, ttm_rev=4000.0,
                    periods=("2025-Q4", "2026-Q1")):
    blocked = _feature("BLOCKED")
    features = {
        "net_income_ttm_sum": _feature("READY_RESEARCH_PROXY", ttm_ni, periods=periods) if ttm_ni is not None else blocked,
        "revenue_ttm_sum": _feature("READY_RESEARCH_PROXY", ttm_rev, periods=periods) if ttm_rev is not None else blocked,
        "profit_state": _feature("READY_RESEARCH_PROXY", ni, state=profit, periods=[periods[-1]]),
    }
    return {
        "ticker": ticker, "entity_type": "corporate", "entity_applicability": "GENERIC_RESEARCH_PRIMITIVES_ALLOWED",
        "fundamental_feature_context": {
            "availability": "PRODUCT_READY_RESEARCH_CONTEXT", "ready_feature_count": 3,
            "health_axes": {"PROFITABILITY_STATE": profit, "GROWTH_STATE": "INSUFFICIENT_DATA"},
            "current_features": features, "warnings_blockers": [],
        },
    }


def valuation_record(ticker, *, market_cap=8000.0, pe=10.0):
    share = {"authority": "provider_reported_lagged", "status": "PROVIDER_REPORTED_LAGGED",
              "value": 1000, "share_concept": "ISSUED_SHARES", "research_proxy_eligible": True,
              "authoritative_current_market_cap_eligible": False}

    def metric(status, value=None):
        return {"status": status, "value": value, "applicability": "APPLICABLE", "blocked_reasons": [], "share_identity": "ISSUED_SHARES"}

    return {
        "ticker": ticker, "entity_class": "corporate", "share_basis_input": share,
        "price_input": {"status": "PRICE_READY", "value": 8.0, "session": DECISION},
        "metrics": {
            "market_cap": metric("RESEARCH_USABLE", market_cap),
            "P/E": metric("RESEARCH_USABLE" if pe is not None else "BLOCKED", pe),
            "P/B": metric("BLOCKED"), "P/S": metric("BLOCKED"),
            "EV/Sales": metric("BLOCKED"), "EV/EBITDA": metric("BLOCKED"),
        },
    }


def behavior(ticker, *, entry="EARLY_REVERSAL_CANDIDATE", session=DECISION):
    return {
        "ticker": ticker, "as_of_session": session, "primary_entry_state": entry,
        "setup_tags": ["EARLY_REVERSAL_STRUCTURE"],
        "confirmation_boundary": {"status": "READY", "as_of": session, "boundary_type": "REVERSAL_CONFIRM"},
        "technical_invalidation_boundary": {"status": "READY", "as_of": session, "boundary_type": "BREAKDOWN"},
        "price_volume_behavior": {}, "trend_context": {}, "structure_context": {},
        "market_regime_context": {"current_breadth_state": "MARKET_BREADTH_MIXED"},
        "sector_context": {"leadership_state": None}, "relative_strength_context": {},
    }


def watchlist(ticker, *, entry="EARLY_REVERSAL_CANDIDATE", action="EARLY_ENTRY"):
    return {"ticker": ticker, "entry_state": entry, "entry_action": action}


def liquidity_record(ticker, *, session=DECISION):
    return {
        "ticker": ticker, "session": session, "disposition": "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE",
        "current_ohlc_v": 1000,
        "liquidity_research_contract": {
            "CURRENT_SESSION_LIQUIDITY_RESEARCH": {"state": "ELIGIBLE"},
            "EXECUTION_CAPACITY": {"state": "BLOCKED"}, "ADTV_RESEARCH": {"state": "BLOCKED"},
        },
    }


def _artifact(records, *, session=DECISION, kind="x"):
    return {"session": session, "as_of_session": session, "artifact_identity": _identity(kind), "records": records}


def _feature_store(rows):
    return {"artifact_identity": _identity("feature"), "contract_version": "market_wide_fundamental_feature_store/v1", "records": rows}


def real_pair(*, tickers=("AAA",), session=DECISION, behaviors=None, market_caps=None, pes=None, liquid=True, ttm=True):
    market_caps, pes = market_caps or {}, pes or {}
    behaviors = behaviors or {ticker: "EARLY_REVERSAL_CANDIDATE" for ticker in tickers}
    features = {ticker: feature_record(ticker, ttm_ni=(400.0 if ttm else None), ttm_rev=(4000.0 if ttm else None)) for ticker in tickers}
    valuations = {ticker: valuation_record(ticker, market_cap=market_caps.get(ticker, 8000.0), pe=pes.get(ticker, 10.0)) for ticker in tickers}
    behavior_records = {ticker: behavior(ticker, entry=behaviors[ticker], session=session) for ticker in tickers}
    watch = {ticker: watchlist(ticker, entry=behaviors[ticker]) for ticker in tickers}
    liquids = {ticker: liquidity_record(ticker, session=session) for ticker in tickers} if liquid else {}
    out = build_opportunity_artifacts(
        as_of_session=session, feature_store=_feature_store(features),
        tactical_behavior=_artifact(behavior_records, session=session, kind="tactical"),
        watchlist=_artifact(watch, session=session, kind="watch"),
        valuation={"valuation_session": session, "artifact_identity": _identity("val"), "records": valuations},
        liquidity=_artifact(liquids, session=session, kind="liq") if liquids else None,
        events={"research_session": session, "artifact_identity": _identity("evt"), "records": {}},
        thesis_cases={"as_of_session": session, "artifact_identity": _identity("thesis"), "records": {}},
        requested_at="2026-08-31T00:00:00+07:00",
    )
    return out["opportunity_context"], out["security_decision_context"]


def _leadership(tickers, group="INDUSTRIALS"):
    return {"artifact_identity": _identity("leadership"), "session": DECISION,
            "ticker_contexts": {t: {"sector_leadership_context": {"group_key": group}} for t in tickers}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_ticker_denominator_not_silently_dropped():
    opportunity, decision = real_pair(tickers=("AAA", "BBB", "CCC"))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    assert out["coverage"]["ticker_denominator"] == 3
    assert out["coverage"]["zero_silent_ticker_drops"] is True
    assert set(out["cards"]) == {"AAA", "BBB", "CCC"}


def test_deterministic_workspace_identity_ignores_wall_clock():
    opportunity, decision = real_pair()
    first = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="2026-08-31T00:00:00+07:00")
    second = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="2099-01-01T00:00:00Z")
    assert first["artifact_sha256"] == second["artifact_sha256"]
    replay = content_identity(first)
    assert replay["artifact_sha256"] == first["artifact_sha256"]


def test_mismatched_lineage_pair_rejected():
    opportunity, _ = real_pair(tickers=("AAA",))
    _, decision = real_pair(tickers=("BBB",))
    with pytest.raises(InvestmentDecisionWorkspaceError):
        build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")


def test_empty_denominator_rejected():
    opportunity, decision = real_pair(tickers=("AAA",))
    empty_opportunity = {**opportunity, "records": {}}
    with pytest.raises(InvestmentDecisionWorkspaceError):
        build_artifacts(opportunity_artifact=empty_opportunity, decision_artifact=decision, requested_at="t")


def test_market_cap_only_cannot_create_valuation_stance_end_to_end():
    # AAA has zero usable relative multiples (P/E blocked here) but a real market-cap peer cohort
    # via BBB/CCC/DDD/EEE -- the whole pipeline (fixed upstream attach_peer_relative, then this
    # module's own defensive guard) must not label AAA attractive/expensive.
    opportunity, decision = real_pair(
        tickers=("AAA", "BBB", "CCC", "DDD", "EEE"),
        market_caps={"AAA": 1000.0, "BBB": 5000.0, "CCC": 5000.0, "DDD": 9000.0, "EEE": 20000.0},
        pes={"AAA": None, "BBB": None, "CCC": None, "DDD": None, "EEE": None},
        ttm=False,
    )
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    card = out["cards"]["AAA"]
    assert card["valuation"]["usable_relative_method_count"] == 0
    assert card["valuation"]["relative_research_state"] not in RELATIVE_VALUATION_LABELS


def test_defensive_guard_overrides_a_rigged_upstream_mislabel():
    # Unit-level defense-in-depth: even if some future/older opportunity_context artifact still
    # carries a market-cap-driven ATTRACTIVE_RELATIVE_RESEARCH label (e.g. materialized before the
    # source-level fix), this module must never display it as attractive/expensive.
    opportunity_record = {
        "ticker": "ZZZ", "usable_major_axes": ["fundamental", "valuation", "tactical"],
        "fundamental": {"state": "PROFITABLE", "trajectory": "INSUFFICIENT_DATA", "readiness": "READY_RESEARCH_PROXY", "research_fitness": "READY", "freshness": {}},
        "valuation": {
            "readiness": "READY_RESEARCH_PROXY", "share_basis": "CURRENT_SHARE_RESEARCH_PROXY", "entity_class": "corporate",
            "freshness": {"freshness_status": "CURRENT", "source_session": DECISION},
            "absolute_research_context": {"usable_relative_method_count": 0},
            "peer_relative_context": {
                "relative_research_state": "ATTRACTIVE_RELATIVE_RESEARCH",
                "methods": {"market_cap": {"status": "READY_RESEARCH_ONLY", "percentile": 0.1, "peer_count": 5}},
            },
        },
        "tactical": {"primary_entry_state": "BREAKOUT_READY", "entry_action": "BUY_ON_CONFIRMATION", "setup_tags": [], "freshness": {}},
        "market_sector": {"freshness": {}},
        "catalyst": {"freshness": {}},
        "liquidity": {"freshness": {}},
        "data_authority": {"per_axis_session": {}, "per_axis_freshness": {}, "proxy_or_qualified_state": {}, "blockers": []},
    }
    decision_record = {
        "as_of_session": DECISION, "research_stance": "INITIATE_RESEARCH_CANDIDATE", "research_stance_readiness": "RESEARCH_READY_CONDITIONAL",
        "entry_state": "BREAKOUT_READY", "entry_action": "BUY_ON_CONFIRMATION",
        "deterministic_research_inference": {"reasons": []}, "warnings_counter_thesis": {"warnings": []},
        "confirmation_boundary": {"status": "READY"}, "technical_invalidation": {"status": "READY"},
        "fundamental_invalidation": {"status": "UNAVAILABLE"}, "key_counter_thesis": [],
    }
    card = build_ticker_card(
        ticker="ZZZ", opportunity_record=opportunity_record, decision_record=decision_record,
        sector="UNKNOWN", portfolio_research=None, prospective_record={"status": "NO_RETAINED_CURRENT_CASES"},
    )
    assert card["valuation"]["relative_research_state"] not in RELATIVE_VALUATION_LABELS
    assert card["valuation"]["market_cap_semantic_guard_applied"] is True
    assert card["valuation"]["raw_upstream_relative_research_state"] == "ATTRACTIVE_RELATIVE_RESEARCH"
    # The security research stance itself is untouched by the valuation display guard.
    assert card["research_stance"] == "INITIATE_RESEARCH_CANDIDATE"


def test_valuation_supporting_method_and_basis_exposed_when_real():
    opportunity, decision = real_pair(tickers=("AAA",), pes={"AAA": 10.0})
    # Give AAA four peers on the same P/E basis so it clears MIN_COHORT_MEMBERS.
    opp2, dec2 = real_pair(tickers=("AAA", "BBB", "CCC", "DDD", "EEE"), pes={t: 10.0 + i for i, t in enumerate(("AAA", "BBB", "CCC", "DDD", "EEE"))})
    out = build_artifacts(opportunity_artifact=opp2, decision_artifact=dec2, requested_at="t")
    card = out["cards"]["AAA"]
    if card["valuation"]["relative_research_state"] in RELATIVE_VALUATION_LABELS:
        assert card["valuation"]["supporting_methods"]
        method = card["valuation"]["supporting_methods"][0]
        assert method["method"] and method["basis"] is not None


def test_research_stance_preserved_verbatim_from_decision_context():
    opportunity, decision = real_pair(tickers=("AAA",), behaviors={"AAA": "DOWNTREND"})
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    assert out["cards"]["AAA"]["research_stance"] == decision["records"]["AAA"]["research_stance"] == "AVOID_NEW_ENTRY"


def test_why_section_carries_counterbalancing_context_from_decision_record():
    # AAA is DOWNTREND (AVOID_NEW_ENTRY) with a profitable fundamental -- the positive evidence
    # must reach the card's Why section as counterbalancing context, not be dropped by the join.
    opportunity, decision = real_pair(tickers=("AAA",), behaviors={"AAA": "DOWNTREND"})
    assert decision["records"]["AAA"]["counterbalancing_context"] == ["PROFITABLE_FUNDAMENTAL"]
    card = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")["cards"]["AAA"]
    assert card["why"]["counterbalancing_context"] == ["PROFITABLE_FUNDAMENTAL"]
    assert "PROFITABLE_FUNDAMENTAL" not in card["why"]["deterministic_reasons"]


def test_portfolio_fit_is_separate_from_and_never_mutates_security_stance():
    opportunity, decision = real_pair(tickers=("AAA",))
    portfolio_research = {
        "portfolio_id": "demo", "as_of_session": DECISION, "normalized_positions": [],
        "user_limit_breaches": [{"reason": "MAX_SECTOR_WEIGHT", "sector": "UNKNOWN"}],
        "sector_concentration": {"UNKNOWN": 0.5}, "tactical_concentration": {},
        "selected_joint_risk_horizon": "L60", "joint_risk_status": "READY",
        "pairwise_correlation_status": "AVAILABLE_SEPARATELY_FROM_JOINT_MATRIX",
    }
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, portfolio_research=portfolio_research, requested_at="t")
    card = out["cards"]["AAA"]
    assert card["portfolio"]["status"] == "EXCEEDS_USER_POLICY_LIMIT"
    assert card["research_stance"] == decision["records"]["AAA"]["research_stance"]
    assert card["authority_boundary"]["security_attractiveness_separate_from_portfolio_fit"] is True


def test_portfolio_not_evaluated_when_not_supplied():
    opportunity, decision = real_pair(tickers=("AAA",))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    assert out["cards"]["AAA"]["portfolio"] == {
        "evaluated": False, "status": "NOT_EVALUATED", "reason": "NO_PORTFOLIO_RESEARCH_CONTEXT_SUPPLIED",
    }
    assert out["coverage"]["portfolio_evaluated_count"] == 0


def test_mixed_session_freshness_preserved_per_axis_not_coerced():
    opportunity, decision = real_pair(tickers=("AAA",))
    lineage = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")["cards"]["AAA"]["lineage"]
    sessions = lineage["per_axis_source_session"]
    # tactical/liquidity are session-dated CURRENT; fundamental is period-based -- distinct axes,
    # never coerced into one fabricated same-session snapshot.
    assert sessions.get("tactical") == DECISION
    assert lineage["per_axis_freshness"].get("tactical") == "CURRENT"


def test_liquidity_proxy_and_exact_execution_capacity_are_separate_fields():
    opportunity, decision = real_pair(tickers=("AAA",))
    card = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")["cards"]["AAA"]
    assert card["liquidity"]["readiness"] == "LIQUIDITY_RESEARCH_PROXY"
    assert card["liquidity"]["exact_execution_capacity_status"] == "EXECUTION_CAPACITY_EXACT_BLOCKED"


def test_exact_liquidity_block_does_not_force_wait():
    opportunity, decision = real_pair(tickers=("AAA",), behaviors={"AAA": "EARLY_REVERSAL_CANDIDATE"})
    card = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")["cards"]["AAA"]
    assert card["liquidity"]["exact_execution_capacity_status"] == "EXECUTION_CAPACITY_EXACT_BLOCKED"
    assert card["research_stance"] == "INITIATE_RESEARCH_CANDIDATE"
    assert card["research_stance"] != "WAIT_FOR_CONFIRMATION"


def test_confirmation_and_invalidation_retained():
    opportunity, decision = real_pair(tickers=("AAA",))
    card = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")["cards"]["AAA"]
    assert card["confirmation"]["status"] == "READY"
    assert card["invalidation"]["technical"]["status"] == "READY"
    assert "fundamental" in card["invalidation"]


def test_absent_deep_evidence_is_localized_and_does_not_block_the_card():
    opportunity, decision = real_pair(tickers=("AAA",))
    card = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")["cards"]["AAA"]
    assert card["lineage"]["deep_evidence_availability"] == "DEEP_EVIDENCE_ARTIFACT_NOT_MATERIALIZED_LOCALLY"
    assert card["research_stance"] is not None


def test_no_current_prospective_cases_does_not_block_workspace():
    # No prospective_lifecycle artifact supplied at all -> honest CASE_DATA_UNAVAILABLE, and the
    # ticker still gets a complete card (prospective cases are not a prerequisite).
    opportunity, decision = real_pair(tickers=("AAA",))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    assert out["cards"]["AAA"]["prospective_case"]["status"] == "CASE_DATA_UNAVAILABLE"
    assert out["coverage"]["ticker_denominator"] == 1
    assert out["cards"]["AAA"]["research_stance"] is not None

    # Artifact supplied but this ticker genuinely absent from it -> NO_RETAINED_CURRENT_CASES,
    # distinct from CASE_DATA_UNAVAILABLE.
    lifecycle = {"artifact_identity": "lifecycle:1", "records": {"OTHER": {"thesis_lifecycle_state": "UNCHANGED"}}}
    out2 = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, prospective_lifecycle=lifecycle, requested_at="t")
    assert out2["cards"]["AAA"]["prospective_case"]["status"] == "NO_RETAINED_CURRENT_CASES"


def test_forward_outcome_pending_when_lifecycle_is_initial_observation():
    opportunity, decision = real_pair(tickers=("AAA",))
    lifecycle = {
        "artifact_identity": "lifecycle:1",
        "records": {"AAA": {"thesis_lifecycle_state": "INITIAL_OBSERVATION", "previous_session": None, "current_session": DECISION,
                             "material_change": False, "material_change_reasons": [], "component_transitions": [],
                             "current_recommendation": {"recommendation_label": "INITIATE_RESEARCH_CANDIDATE"}, "current_tactical_state": {"entry_state": "BREAKOUT_READY"}}},
    }
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, prospective_lifecycle=lifecycle, requested_at="t")
    prospective = out["cards"]["AAA"]["prospective_case"]
    assert prospective["status"] == "PENDING_NOT_ENOUGH_FUTURE_SESSIONS"
    assert prospective["forward_outcome_status"] == "PENDING_NOT_ENOUGH_FUTURE_SESSIONS"
    for field in ("t_plus_5", "t_plus_20", "t_plus_60", "mfe", "mae", "benchmark_relative_result"):
        assert prospective[field] is None


def test_t0_is_never_fabricated_when_no_prior_session_exists():
    opportunity, decision = real_pair(tickers=("AAA",))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    prospective = out["cards"]["AAA"]["prospective_case"]
    assert prospective["t0_session"] is None
    assert prospective["t0_stance"] is None


def test_sector_enrichment_from_leadership_when_available_else_unknown():
    opportunity, decision = real_pair(tickers=("AAA",))
    with_leadership = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision,
                                       leadership=_leadership(["AAA"], group="STEEL"), requested_at="t")
    without_leadership = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    assert with_leadership["cards"]["AAA"]["sector"] == "STEEL"
    assert without_leadership["cards"]["AAA"]["sector"] == "UNKNOWN"


def test_no_score_rank_probability_or_target_price_anywhere():
    opportunity, decision = real_pair(tickers=("AAA",))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    assert out["blocked_outputs"]["universal_score"] == "SCORING_PROHIBITED"
    assert out["blocked_outputs"]["target_price"] == "NOT_EMITTED"
    card = out["cards"]["AAA"]
    assert "score" not in card and "rank" not in card and "probability" not in card and "target_price" not in card
    assert card["authority_boundary"]["no_score"] is True
    assert card["authority_boundary"]["no_probability"] is True
    assert card["authority_boundary"]["no_target_price"] is True
