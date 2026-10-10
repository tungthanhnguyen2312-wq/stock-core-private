"""DAILY_LIQUIDITY_AUTHORITY_WIRING_RECONCILIATION_V1: scoped summary vs per-record fitness."""
from __future__ import annotations

import stocklookup_core.decision.current_research_decision_input as decision_input
import stocklookup_core.portfolio.execution_capacity_research as capacity
import market_wide_current_liquidity_research as descriptive
import official_liquidity_market_wide as wide
from tests.test_execution_capacity_research import SESSION, _official, _policy
from tests.test_official_liquidity_market_wide import _frame_row, _record, _slot
import official_exchange_trading_statistics as official


def _descriptive(eligible=True):
    return {
        "disposition": "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE" if eligible else "INCOMPLETE",
        "liquidity_research_contract": {
            "EXECUTION_CAPACITY": {"state": "BLOCKED"},
            "POSITION_SIZING": {"state": "BLOCKED"},
            "ADTV_RESEARCH": {"state": "BLOCKED"},
            "ADV_VOLUME_RESEARCH": {"state": "BLOCKED"},
            "PIT_BACKTEST": {"state": "BLOCKED"},
        },
    }


def test_qualified_adtv_row_is_not_artifact_globally_blocked():
    record = _record(_slot())
    liq = decision_input._liquidity({}, _descriptive(), record)
    assert liq["qualified_research"]["fitness"]["ADTV_RESEARCH"] == "ELIGIBLE"
    assert liq["authority"] == decision_input.RESEARCH_QUALIFIED
    envelope = liq["qualified_research"]["execution_capacity_research"]
    assert envelope["reason_codes"] == ["POLICY_UNBOUND"]
    assert envelope["state"] == "BLOCKED"
    assert envelope["participation_used"] is None
    assert envelope["days_to_liquidate_used"] is None


def test_non_qualified_and_unmatched_rows_remain_blocked():
    blocked = _record(None, row=_frame_row("BBB", official.HNX))
    liq = decision_input._liquidity({}, _descriptive(False), blocked)
    assert liq["qualified_research"]["fitness"]["ADTV_RESEARCH"] == "BLOCKED"
    missing = decision_input._liquidity({}, _descriptive(), None)
    assert "qualified_research" not in missing
    assert missing["authority"] == decision_input.CURRENT_DESCRIPTIVE_ONLY


def test_adv_volume_remains_as_traded_not_ca_normalized():
    record = _record(_slot())
    assert record["fitness"]["ADV_VOLUME_RESEARCH"]["state"] == "PARTIAL"
    summary = wide.artifact_authority_summary({"AAA": record})
    assert summary["ADV_VOLUME_RESEARCH"]["basis"] == wide.AS_TRADED_NOT_CA_NORMALIZED
    descriptive_boundary = descriptive.artifact_authority_boundary(eligible_count=1, universe_count=1)
    assert descriptive_boundary["ADV_VOLUME_RESEARCH"]["basis"] == descriptive.AS_TRADED_NOT_CA_NORMALIZED


def test_qualified_row_reaches_execution_capacity_engine_and_unbound_policy_is_explicit():
    record = _official()
    envelope = capacity.build_envelope(
        ticker="AAA", session=SESSION, official_liquidity_record=record,
        policy=capacity.canonical_unbound_policy(),
    )
    assert envelope["state"] == "BLOCKED"
    assert envelope["reason_codes"] == ["POLICY_UNBOUND"]
    bound = capacity.build_envelope(
        ticker="AAA", session=SESSION, official_liquidity_record=record,
        policy=_policy(), current_price="1250", price_identity="price:test",
    )
    assert bound["state"] == "AVAILABLE"
    assert bound["capacity_notional_vnd"] == "375000"


def test_live_pit_replay_and_raw_as_traded_remain_blocked():
    matrix = capacity.use_specific_authority(capacity_state=capacity.AVAILABLE, private_size_state=capacity.AVAILABLE)
    assert matrix[capacity.LIVE_POSITION_SIZING] == "BLOCKED"
    assert matrix[capacity.PIT_BACKTEST] == "BLOCKED"
    assert matrix[capacity.EXECUTION_REPLAY] == "BLOCKED"
    assert matrix[capacity.PORTFOLIO_CAPITAL_ALLOCATION] == "BLOCKED"
    assert matrix[capacity.HISTORICAL_PIT_SIZE_REPLAY] == "BLOCKED"
    summary = wide.artifact_authority_summary({"AAA": _record(_slot())})
    assert summary["RAW_AS_TRADED"] == "NOT_PROMOTED"
    assert summary["PIT_BACKTEST"] == "BLOCKED"
    assert summary["EXECUTION_REPLAY"] == "BLOCKED"
    assert summary["LIVE_POSITION_SIZING"] == "BLOCKED"


def test_hnx_upcom_unauthorized_bulk_stays_rights_gated():
    record = _official(exchange="HNX", exact=False, current=False, coverage_class="PUBLIC_ACQUISITION_NOT_AUTHORIZED")
    envelope = capacity.build_envelope(
        ticker="AAA", session=SESSION, official_liquidity_record=record, policy=_policy(),
    )
    assert envelope["reason_codes"] == ["PUBLIC_ACQUISITION_NOT_AUTHORIZED"]
    hnx = _record(None, row=_frame_row("SHS", official.HNX))
    summary = wide.artifact_authority_summary({"SHS": hnx})
    assert summary["hnx_upcom_bulk_public_acquisition_not_authorized_count"] == 1
    assert summary["ADTV_RESEARCH"]["eligible_count"] == 0


def test_coverage_reports_scoped_qualified_counts_without_leaking_to_unmatched():
    exact = _record(_slot())
    blocked = _record(None, row=_frame_row("BBB", official.HNX))
    records = {
        "AAA": {"current_research_decision_input": decision_input.build_ticker_decision_input(
            session="2026-09-28", record={"ticker": "AAA", "research_action_posture": "WAIT"},
            liquidity_record=_descriptive(), official_liquidity_record=exact,
        )},
        "BBB": {"current_research_decision_input": decision_input.build_ticker_decision_input(
            session="2026-09-28", record={"ticker": "BBB", "research_action_posture": "WAIT"},
            liquidity_record=_descriptive(), official_liquidity_record=blocked,
        )},
        "CCC": {"current_research_decision_input": decision_input.build_ticker_decision_input(
            session="2026-09-28", record={"ticker": "CCC", "research_action_posture": "WAIT"},
            liquidity_record=_descriptive(), official_liquidity_record=None,
        )},
    }
    cov = decision_input.coverage(records)["qualified_liquidity"]
    assert cov["official_supplied"] == 2
    assert cov["adtv_research_eligible"] == 1
    assert cov["adv_volume_research_partial"] == 1
    assert cov["current_session_liquidity_research_eligible"] == 0
    assert cov["policy_unbound"] == 1
    assert cov["live_position_sizing"] == "BLOCKED"
    assert cov["pit_backtest"] == "BLOCKED"
    assert cov["raw_as_traded"] == "NOT_PROMOTED"
    assert records["CCC"]["current_research_decision_input"]["dimensions"]["LIQUIDITY"].get("qualified_research") is None
    assert records["AAA"]["current_research_decision_input"]["authority_boundary"]["execution_authority"] is False
    assert records["AAA"]["current_research_decision_input"]["authority_boundary"]["historical_pit_authority"] is False
