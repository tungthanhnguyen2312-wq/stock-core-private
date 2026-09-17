"""Synthetic-fixture tests for PERSONAL_INVESTMENT_DECISION_ACTION_CENTER_V1.

No real private portfolio values appear anywhere in this file -- every account/position figure
below is fabricated for test purposes only.
"""
from __future__ import annotations

import personal_investment_decision_action_center as ac

SESSION = "2026-09-16"


def _integrated_record(ticker: str, posture: str, **overrides) -> dict:
    record = {
        "ticker": ticker,
        "research_action_posture": posture,
        "why_now": f"{ticker}: synthetic why_now for {posture}.",
        "tactical_phase": "RETEST_AFTER_BREAKOUT",
        "market_structure_state": "UPTREND",
        "fundamental_state": "MIXED",
        "valuation_context_summary": {"own_history_state": "LOW_VS_OWN_HISTORY"},
        "market_sector_context": {"market_regime": "MIXED_BREADTH", "sector_leadership": "LEADING"},
        "corporate_intelligence_context": {"fitness": "NO_QUALIFIED_CORPORATE_EVENT", "active_catalyst_count": 0, "active_risk_count": 0},
        "trigger": {"trigger_type": "PIVOT_BREAKOUT_TRIGGER", "trigger_level": 10.0, "distance_to_trigger_pct": -0.01, "trigger_state": "APPROACHING", "warning": "TRIGGER_IS_RESEARCH_MEASUREMENT_NOT_EXECUTION_AUTHORITY"},
        "invalidation": {"invalidation_level": 9.0, "distance_to_invalidation_pct": 0.02, "invalidation_method": "CONFIRMED_SWING_LEVEL", "warning": "NOT_A_STOP_LOSS"},
        "counter_thesis": [f"{ticker}_COUNTER"],
        "material_uncertainties": [],
        "evidence_axes": {
            "TACTICAL_STRUCTURE": {"fitness": "AVAILABLE", "is_actionable": True, "contradicting_reason_codes": [], "blocker_reason_codes": []},
            "FUNDAMENTAL": {"fitness": "AVAILABLE", "is_actionable": False, "contradicting_reason_codes": [], "blocker_reason_codes": []},
        },
        "decision_identity": f"decision:{ticker}",
    }
    record.update(overrides)
    return record


def _integrated_artifact(records: dict[str, dict]) -> dict:
    return {"contract_version": "integrated_investment_decision_product/v1", "session": SESSION, "artifact_identity": "iid:test", "records": records}


def _asymmetric_artifact(states: dict[str, str]) -> dict:
    return {
        "contract_version": "asymmetric_dislocation_research/v1", "session": SESSION, "artifact_identity": "adr:test",
        "records": {ticker: {"primary_research_state": state, "source_decision_identity": f"decision:{ticker}"} for ticker, state in states.items()},
    }


def _portfolio_row(ticker: str, position_state: str, *, portfolio_action_research: str = "HOLD_EXISTING_NO_ACTION", posture: str = "HOLD") -> dict:
    return {
        "ticker": ticker, "position_state": position_state, "portfolio_action_research": portfolio_action_research,
        "security_research_action_posture": posture, "current_weight": 0.1, "current_weight_status": "AVAILABLE",
        "binding_constraint": "NONE",
    }


def _portfolio_artifact(rows: dict[str, dict]) -> dict:
    return {"contract_version": "portfolio_aware_decision/v1", "session": SESSION, "artifact_identity": "pad:test", "records": rows}


def _coverage_artifact(dispositions: dict[str, str]) -> dict:
    return {"session": SESSION, "records": {ticker: {"disposition": disposition} for ticker, disposition in dispositions.items()}}


_OWNER_FOCUS = {"owner_focus_tickers": ("AAA",), "broader_watchlist": ("AAA", "BBB")}


def _build(*, integrated, portfolio=None, asymmetric=None, coverage=None, owner_focus=None, sector_by_ticker=None, excluded_tickers=frozenset(), portfolio_snapshot=None):
    return ac.build_artifact(
        session=SESSION, requested_at="2026-09-16T17:00:00", integrated_decision_artifact=integrated,
        asymmetric_dislocation_artifact=asymmetric, coverage_disposition_artifact=coverage,
        owner_focus=owner_focus, portfolio_aware_decision_artifact=portfolio,
        sector_by_ticker=sector_by_ticker or {}, excluded_tickers=excluded_tickers,
        portfolio_snapshot=portfolio_snapshot,
    )


# ── Portfolio truth propagation ─────────────────────────────────────────────────────────────────

def test_confirmed_holding_reaches_a_valid_action_surface():
    integrated = _integrated_artifact({"AAA": _integrated_record("AAA", "HOLD")})
    portfolio = _portfolio_artifact({"AAA": _portfolio_row("AAA", "HELD", posture="HOLD")})
    artifact = _build(integrated=integrated, portfolio=portfolio)
    holdings = artifact["portfolio"]["holdings"]
    assert len(holdings) == 1
    assert holdings[0]["ticker"] == "AAA"
    assert holdings[0]["action"] in ac.HOLDING_ACTIONS
    assert holdings[0]["action"] == "HOLD"
    assert "evidence" in holdings[0] and holdings[0]["evidence"]["why_now"]


def test_avoid_posture_on_a_held_position_surfaces_as_exit_review_not_bare_hold():
    """portfolio_aware_decision.py's own action vocabulary collapses HELD+AVOID and HELD+HOLD to
    the same HOLD_EXISTING_NO_ACTION -- the Action Center's remap is what actually distinguishes
    them, using only the already-computed posture, never a new threshold."""
    integrated = _integrated_artifact({"AAA": _integrated_record("AAA", "AVOID")})
    portfolio = _portfolio_artifact({"AAA": _portfolio_row("AAA", "HELD", posture="AVOID")})
    artifact = _build(integrated=integrated, portfolio=portfolio)
    assert artifact["portfolio"]["holdings"][0]["action"] == "EXIT_REVIEW"


def test_closed_position_never_appears_in_active_portfolio_decisions():
    integrated = _integrated_artifact({"AAA": _integrated_record("AAA", "HOLD")})
    portfolio = _portfolio_artifact({"AAA": _portfolio_row("AAA", "CLOSED")})
    artifact = _build(integrated=integrated, portfolio=portfolio)
    assert artifact["portfolio"]["holdings"] == []
    assert artifact["unresolved_portfolio"]["items"] == []
    assert artifact["coverage"]["confirmed_holding_count"] == 0


def test_unresolved_position_is_review_only_never_a_buy_sell_or_rotation_source():
    integrated = _integrated_artifact({"AAA": _integrated_record("AAA", "AVOID")})
    portfolio = _portfolio_artifact({"AAA": _portfolio_row("AAA", "CURRENT_POSITION_UNRESOLVED", portfolio_action_research="CURRENT_POSITION_UNRESOLVED_REVIEW_NEEDED")})
    artifact = _build(integrated=integrated, portfolio=portfolio)
    assert artifact["portfolio"]["holdings"] == []
    assert len(artifact["unresolved_portfolio"]["items"]) == 1
    item = artifact["unresolved_portfolio"]["items"][0]
    assert item["ticker"] == "AAA"
    assert item["status"] == "CURRENT_POSITION_UNRESOLVED"
    assert "reconciliation" in item["note"].lower()
    # Never a rotation source: no holdings means no possible rotation pairs.
    assert artifact["capital_rotation"]["pairs"] == []
    # And never counted in the attention queue as anything but a data-review item.
    rows = [row for row in artifact["attention_queue"]["rows"] if row["ticker"] == "AAA"]
    assert len(rows) == 1 and rows[0]["bucket"] == "PORTFOLIO_DATA_REVIEW"


def test_owner_excluded_ticker_is_absent_from_every_active_surface():
    integrated = _integrated_artifact({
        "AAA": _integrated_record("AAA", "HOLD"),
        "KSH": _integrated_record("KSH", "INITIATE_ON_BREAKOUT"),
    })
    portfolio = _portfolio_artifact({
        "AAA": _portfolio_row("AAA", "HELD", posture="HOLD"),
        "KSH": _portfolio_row("KSH", "EXCLUDED_INACTIVE", portfolio_action_research="EXCLUDED_FROM_ACTIVE_PORTFOLIO"),
    })
    owner_focus = {"owner_focus_tickers": (), "broader_watchlist": ("KSH",)}
    artifact = _build(integrated=integrated, portfolio=portfolio, owner_focus=owner_focus, excluded_tickers=frozenset({"KSH"}))
    assert all(row["ticker"] != "KSH" for row in artifact["portfolio"]["holdings"])
    assert all(row["ticker"] != "KSH" for row in artifact["unresolved_portfolio"]["items"])
    assert all(entry["ticker"] != "KSH" for entry in artifact["watchlist"]["entries"])
    for rows in artifact["discovery"]["lanes"].values():
        assert all(row["ticker"] != "KSH" for row in rows)
    assert all(row["ticker"] != "KSH" for row in artifact["attention_queue"]["rows"])


def test_no_private_portfolio_still_produces_market_watchlist_and_discovery():
    integrated = _integrated_artifact({
        "AAA": _integrated_record("AAA", "INITIATE_ON_BREAKOUT"),
        "BBB": _integrated_record("BBB", "HOLD"),
    })
    artifact = _build(integrated=integrated, portfolio=None, owner_focus=_OWNER_FOCUS)
    assert artifact["portfolio"]["status"] == "PRIVATE_PORTFOLIO_NOT_SUPPLIED"
    assert artifact["unresolved_portfolio"]["status"] == "PRIVATE_PORTFOLIO_NOT_SUPPLIED"
    assert artifact["capital_rotation"]["status"] == "PRIVATE_PORTFOLIO_NOT_SUPPLIED"
    assert artifact["watchlist"]["status"] == "AVAILABLE"
    assert len(artifact["watchlist"]["entries"]) == 2
    assert artifact["discovery"]["lane_counts"]["TACTICAL_SETUP"] == 1
    assert artifact["coverage"]["portfolio_supplied"] is False


# ── Exact-session price semantics ───────────────────────────────────────────────────────────────

def test_stale_price_is_visible_and_never_backs_a_numeric_trigger():
    integrated = _integrated_artifact({"AAA": _integrated_record("AAA", "INITIATE_ON_BREAKOUT")})
    coverage = _coverage_artifact({"AAA": "RAW_SAME_SESSION_PRESENT_TECHNICAL_MATERIALIZATION_MISSING"})
    artifact = _build(integrated=integrated, coverage=coverage, owner_focus={"owner_focus_tickers": (), "broader_watchlist": ("AAA",)})
    evidence = artifact["watchlist"]["entries"][0]["evidence"]
    assert evidence["freshness"]["price_freshness"] == "STALE_OR_UNAVAILABLE"
    assert evidence["trigger"]["trigger_level"] is None
    assert evidence["trigger"]["distance_to_trigger_pct"] is None
    assert evidence["trigger"]["numeric_fields_withheld_stale_price"] is True
    assert evidence["invalidation"]["invalidation_level"] is None
    # Qualitative posture/why_now/structure are NOT blocked by a stale price mark.
    assert evidence["why_now"]
    assert evidence["research_action_posture"] == "INITIATE_ON_BREAKOUT"
    assert evidence["tactical_phase"] == "RETEST_AFTER_BREAKOUT"


def test_current_price_freshness_keeps_numeric_trigger_fields():
    integrated = _integrated_artifact({"AAA": _integrated_record("AAA", "INITIATE_ON_BREAKOUT")})
    coverage = _coverage_artifact({"AAA": "SAME_SESSION_TECHNICAL_COVERED"})
    artifact = _build(integrated=integrated, coverage=coverage, owner_focus={"owner_focus_tickers": (), "broader_watchlist": ("AAA",)})
    evidence = artifact["watchlist"]["entries"][0]["evidence"]
    assert evidence["freshness"]["price_freshness"] == "CURRENT"
    assert evidence["trigger"]["trigger_level"] == 10.0
    assert evidence["trigger"]["numeric_fields_withheld_stale_price"] is False


def test_technical_research_not_blocked_merely_by_missing_coverage_artifact():
    """No same_session_technical_coverage_disposition artifact supplied at all (a real PIT/
    coverage-authority gap) must not block current technical/fundamental research posture --
    it only degrades price_freshness to NOT_EVALUATED, which fails closed on numeric triggers only."""
    integrated = _integrated_artifact({"AAA": _integrated_record("AAA", "INITIATE_ON_BREAKOUT")})
    artifact = _build(integrated=integrated, coverage=None, owner_focus={"owner_focus_tickers": (), "broader_watchlist": ("AAA",)})
    evidence = artifact["watchlist"]["entries"][0]["evidence"]
    assert evidence["freshness"]["price_freshness"] == "NOT_EVALUATED"
    assert evidence["trigger"]["trigger_level"] is None  # numeric trigger fails closed
    assert evidence["research_action_posture"] == "INITIATE_ON_BREAKOUT"  # posture research unaffected
    assert evidence["why_now"]
    assert evidence["fundamental_state"] == "MIXED"


# ── Watchlist / discovery ───────────────────────────────────────────────────────────────────────

def test_watchlist_actions_are_a_bounded_deterministic_remap():
    integrated = _integrated_artifact({
        "AAA": _integrated_record("AAA", "INITIATE_ON_BREAKOUT"),
        "BBB": _integrated_record("BBB", "WAIT_FOR_CONFIRMATION"),
    })
    owner_focus = {"owner_focus_tickers": ("AAA",), "broader_watchlist": ("AAA", "BBB")}
    artifact = _build(integrated=integrated, owner_focus=owner_focus)
    by_ticker = {e["ticker"]: e for e in artifact["watchlist"]["entries"]}
    assert by_ticker["AAA"]["action"] == "BUY_PROBE_CANDIDATE"
    assert by_ticker["AAA"]["owner_focus"] is True
    assert by_ticker["BBB"]["action"] == "WAIT_FOR_CONFIRMATION"
    assert by_ticker["BBB"]["owner_focus"] is False
    assert set(by_ticker["AAA"]["action"] for _ in [0]).issubset(ac.WATCHLIST_ACTIONS)


def test_discovery_works_outside_the_watchlist_and_requires_no_private_portfolio():
    integrated = _integrated_artifact({
        "ZZZ": _integrated_record("ZZZ", "INITIATE_ON_BREAKOUT"),  # not on any watchlist
        "AAA": _integrated_record("AAA", "HOLD"),
    })
    artifact = _build(integrated=integrated, owner_focus={"owner_focus_tickers": (), "broader_watchlist": ("AAA",)})
    assert artifact["discovery"]["requires_private_portfolio"] is False
    tactical = artifact["discovery"]["lanes"]["TACTICAL_SETUP"]
    assert any(row["ticker"] == "ZZZ" for row in tactical)


def test_discovery_excludes_already_held_tickers():
    integrated = _integrated_artifact({"AAA": _integrated_record("AAA", "INITIATE_ON_BREAKOUT")})
    portfolio = _portfolio_artifact({"AAA": _portfolio_row("AAA", "HELD", posture="HOLD")})
    artifact = _build(integrated=integrated, portfolio=portfolio)
    assert all(row["ticker"] != "AAA" for rows in artifact["discovery"]["lanes"].values() for row in rows)


def test_asymmetric_states_map_to_named_discovery_lanes_not_risk_states():
    integrated = _integrated_artifact({
        "AAA": _integrated_record("AAA", "HOLD_DO_NOT_ADD"),
        "BBB": _integrated_record("BBB", "HOLD_DO_NOT_ADD"),
    })
    asymmetric = _asymmetric_artifact({"AAA": "QUALITY_DISLOCATION", "BBB": "VALUE_TRAP_RISK"})
    artifact = _build(integrated=integrated, asymmetric=asymmetric)
    assert any(row["ticker"] == "AAA" for row in artifact["discovery"]["lanes"]["VALUATION_DISLOCATION"])
    for rows in artifact["discovery"]["lanes"].values():
        assert all(row["ticker"] != "BBB" for row in rows)  # VALUE_TRAP_RISK is never an opportunity lane


# ── No fabricated authority ─────────────────────────────────────────────────────────────────────

def test_no_universal_score_no_probability_no_target_price_anywhere():
    integrated = _integrated_artifact({
        "AAA": _integrated_record("AAA", "INITIATE_ON_BREAKOUT"),
        "BBB": _integrated_record("BBB", "HOLD"),
    })
    portfolio = _portfolio_artifact({"BBB": _portfolio_row("BBB", "HELD", posture="HOLD")})
    artifact = _build(integrated=integrated, portfolio=portfolio, owner_focus=_OWNER_FOCUS)
    dumped = str(artifact)
    for forbidden in ("'target_price':", "'probability_of_success':", "'score':", "global_score", "'rank':"):
        assert forbidden not in dumped
    assert artifact["authority_boundary"]["no_universal_score"] is True
    assert artifact["authority_boundary"]["no_fabricated_probability_or_target_price"] is True
    assert artifact["authority_boundary"]["no_execution_order"] is True


def test_capital_rotation_only_sourced_from_confirmed_holdings_never_unresolved():
    integrated = _integrated_artifact({
        "AAA": _integrated_record("AAA", "AVOID"),
        "CCC": _integrated_record("CCC", "INITIATE_ON_BREAKOUT"),
    })
    portfolio = _portfolio_artifact({
        "AAA": _portfolio_row("AAA", "HELD", posture="AVOID"),
    })
    artifact = _build(integrated=integrated, portfolio=portfolio, sector_by_ticker={"AAA": "STEEL", "CCC": "STEEL"})
    assert len(artifact["capital_rotation"]["pairs"]) == 1
    pair = artifact["capital_rotation"]["pairs"][0]
    assert pair["source_ticker"] == "AAA"
    assert pair["consider_candidates"][0]["ticker"] == "CCC"
    assert "cost_basis" not in str(pair).lower().replace("cost_basis_not_used_in_this_argument", "")


def test_capital_rotation_skips_source_with_no_same_sector_destination():
    integrated = _integrated_artifact({
        "AAA": _integrated_record("AAA", "AVOID"),
        "CCC": _integrated_record("CCC", "INITIATE_ON_BREAKOUT"),
    })
    portfolio = _portfolio_artifact({"AAA": _portfolio_row("AAA", "HELD", posture="AVOID")})
    artifact = _build(integrated=integrated, portfolio=portfolio, sector_by_ticker={"AAA": "STEEL", "CCC": "BANKING"})
    assert artifact["capital_rotation"]["pairs"] == []


# ── Determinism / no private leak ───────────────────────────────────────────────────────────────

def test_artifact_is_deterministic_and_idempotent():
    integrated = _integrated_artifact({"AAA": _integrated_record("AAA", "HOLD")})
    portfolio = _portfolio_artifact({"AAA": _portfolio_row("AAA", "HELD", posture="HOLD")})
    first = _build(integrated=integrated, portfolio=portfolio)
    second = _build(integrated=integrated, portfolio=portfolio)
    assert first["artifact_identity"] == second["artifact_identity"]


def test_local_write_paths_never_target_the_repository_or_git():
    root = ac.default_action_center_root()
    assert ".stocklookup" in str(root)
    assert "operations-review" not in str(root)


def test_markdown_renders_without_crashing_for_every_section_state():
    integrated = _integrated_artifact({
        "AAA": _integrated_record("AAA", "AVOID"),
        "BBB": _integrated_record("BBB", "INITIATE_ON_BREAKOUT"),
    })
    portfolio = _portfolio_artifact({
        "AAA": _portfolio_row("AAA", "HELD", posture="AVOID"),
        "CCC": _portfolio_row("CCC", "CURRENT_POSITION_UNRESOLVED", portfolio_action_research="CURRENT_POSITION_UNRESOLVED_REVIEW_NEEDED"),
    })
    artifact = _build(integrated=integrated, portfolio=portfolio, owner_focus=_OWNER_FOCUS, sector_by_ticker={"AAA": "STEEL", "BBB": "STEEL"})
    text = ac.markdown(artifact)
    for header in ("## TODAY", "## PORTFOLIO ACTIONS", "## UNRESOLVED PORTFOLIO ITEMS", "## WATCHLIST", "## NEW OPPORTUNITIES", "## CAPITAL ROTATION", "## WHAT NEEDS CONFIRMATION"):
        assert header in text


def test_console_summary_has_no_ticker_or_evidence_values():
    integrated = _integrated_artifact({"AAA": _integrated_record("AAA", "HOLD")})
    portfolio = _portfolio_artifact({"AAA": _portfolio_row("AAA", "HELD", posture="HOLD")})
    artifact = _build(integrated=integrated, portfolio=portfolio)
    summary = ac.public_console_summary(artifact)
    assert "holdings" not in summary
    assert "AAA" not in str(summary)


# ── PRIVATE_MULTI_BROKER_INVESTMENT_ACCOUNT_CONTEXT_V1: INVESTMENT ACCOUNTS section ──────────────

def test_investment_accounts_section_absent_without_a_private_portfolio():
    integrated = _integrated_artifact({"AAA": _integrated_record("AAA", "HOLD")})
    artifact = _build(integrated=integrated)
    assert artifact["investment_accounts"]["status"] == "PRIVATE_PORTFOLIO_NOT_SUPPLIED"
    text = ac.markdown(artifact)
    assert "## INVESTMENT ACCOUNTS" in text
    assert "PRIVATE_PORTFOLIO_NOT_SUPPLIED" in text


def test_investment_accounts_section_surfaces_qualified_aggregate_only():
    integrated = _integrated_artifact({"AAA": _integrated_record("AAA", "HOLD")})
    portfolio = _portfolio_artifact({"AAA": _portfolio_row("AAA", "HELD", posture="HOLD")})
    snapshot = {
        "investment_accounts_portfolio_context": {
            "status": "AGGREGATED", "account_count": 2, "as_of_consistency": "CONSISTENT",
            "artifact_identity": "investment_accounts_portfolio_context:test",
            "totals": {
                "total_broker_cash": "300000000", "total_reserved_cash": None, "total_receivables": None,
                "total_margin_debt": "10000000", "total_broker_reported_nav": "500000000",
                "total_broker_reported_securities_market_value": "190000000",
            },
        },
    }
    artifact = _build(integrated=integrated, portfolio=portfolio, portfolio_snapshot=snapshot)
    section = artifact["investment_accounts"]

    assert section["status"] == "AGGREGATED"
    assert section["broker_account_count"] == 2
    assert section["broker_cash"] == "300000000"
    assert section["margin_debt"] == "10000000"
    assert section["broker_reported_nav"] == "500000000"
    # Never a per-account raw identity/alias in this local-owner-facing surface.
    assert "account_id" not in str(section)
    text = ac.markdown(artifact)
    assert "Broker accounts: 2" in text
    assert "capital context only" in text


def test_investment_account_values_never_alter_holding_actions():
    """Cash existing must never change a holding's derived action -- this section is purely
    informational and structurally cannot feed `_holding_action`."""
    integrated = _integrated_artifact({"AAA": _integrated_record("AAA", "HOLD")})
    portfolio = _portfolio_artifact({"AAA": _portfolio_row("AAA", "HELD", posture="HOLD")})
    snapshot = {"investment_accounts_portfolio_context": {"status": "AGGREGATED", "account_count": 1, "totals": {"total_broker_cash": "999999999999"}}}

    without_cash = _build(integrated=integrated, portfolio=portfolio)
    with_cash = _build(integrated=integrated, portfolio=portfolio, portfolio_snapshot=snapshot)

    assert without_cash["portfolio"]["holdings"][0]["action"] == with_cash["portfolio"]["holdings"][0]["action"]
    assert without_cash["attention_queue"]["bucket_counts"] == with_cash["attention_queue"]["bucket_counts"]
