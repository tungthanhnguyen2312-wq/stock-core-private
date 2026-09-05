from __future__ import annotations

from market_wide_historical_matched_liquidity import (
    COVERAGE_RESTRICTED_WINDOW,
    EXACT_WINDOW,
    INSUFFICIENT_WINDOW,
    KNOWN_FAILED,
    NO_TRADES_CONFIRMED,
    QUALIFIED_MATCHED_VALUE,
    QUALIFIED_MATCHED_VOLUME,
    SEMANTICS_UNQUALIFIED,
    SEMANTICS_UNQUALIFIED_WINDOW,
    aggregate_regular_board_trades,
    build_artifact,
    build_ticker_liquidity_context,
    calculate_trailing_feature,
    daily_cells_from_retained_evidence,
    unit_coverage_from_manifest,
)


def _sessions(count: int) -> list[str]:
    # Explicit governed sessions: 2026-01-05 is intentionally omitted as a holiday.
    return [f"2026-01-{day:02d}" for day in range(2, count + 3) if day != 5]


def _qualified_cell(ticker: str, session: str, value: int = 100, volume: int = 10) -> dict:
    return {
        "ticker": ticker, "session": session, "session_completeness": "COMPLETE",
        "matched_volume_state": QUALIFIED_MATCHED_VOLUME,
        "matched_value_state": QUALIFIED_MATCHED_VALUE,
        "regular_board_matched_volume_shares": volume,
        "regular_board_matched_value_vnd": value,
        "source_lineage": {"raw": f"{ticker}:{session}"}, "blockers": [],
    }


def test_regular_board_aggregation_filters_boards_calculates_units_and_deduplicates():
    rows = [
        {"raw_record_identity": "g1-1", "board_id": "G1", "quantity": 10, "price": 20, "source_page_payload_hash": "a"},
        {"raw_record_identity": "g1-1", "board_id": "G1", "quantity": 10, "price": 20, "source_page_payload_hash": "a"},
        {"raw_record_identity": "g4", "board_id": "G4", "quantity": 9, "price": 20, "source_page_payload_hash": "b"},
        {"raw_record_identity": "t1", "board_id": "T1", "quantity": 8, "price": 20, "source_page_payload_hash": "b"},
    ]
    result = aggregate_regular_board_trades(
        ticker="aaa", session="2026-01-02", trades=rows, session_completeness="COMPLETE",
        unit_semantics={"quantity_shares_qualified": True, "price_vnd_per_share_qualified": True, "quantity_multiplier": 10, "price_multiplier": 1000},
    )
    assert result["regular_board_matched_volume_shares"] == 100
    assert result["regular_board_matched_value_vnd"] == 2_000_000
    assert result["record_count"] == 1
    assert result["duplicate_records_discarded"] == 1
    assert result["other_board_record_count"] == {"G4": 1, "T1": 1}


def test_aggregation_never_infers_units_and_complete_no_regular_trade_is_zero_only_when_confirmed():
    unresolved = aggregate_regular_board_trades(
        ticker="AAA", session="2026-01-02", trades=[{"board_id": "G1", "quantity": 1, "price": 2}],
        session_completeness="COMPLETE", unit_semantics={},
    )
    assert unresolved["matched_volume_state"] == SEMANTICS_UNQUALIFIED
    assert unresolved["regular_board_matched_value_vnd"] is None
    no_regular = aggregate_regular_board_trades(
        ticker="AAA", session="2026-01-02", trades=[{"board_id": "G4", "quantity": 1, "price": 2}],
        session_completeness="COMPLETE", unit_semantics={},
    )
    assert no_regular["session_completeness"] == NO_TRADES_CONFIRMED
    assert no_regular["regular_board_matched_value_vnd"] == 0


def test_manifest_coverage_distinguishes_empty_failed_and_absent():
    units = unit_coverage_from_manifest([
        {"instrument": "AAA", "session": "2026-01-02", "logical_status": "ORIGINAL_SUCCESS_EMPTY"},
        {"instrument": "BBB", "session": "2026-01-02", "logical_status": "REMAINING_FAILED"},
        {"instrument": "CCC", "session": "2026-01-02", "logical_status": "REPAIR_RECOVERED_SUCCESS"},
    ])
    assert units[("AAA", "2026-01-02")]["session_completeness"] == NO_TRADES_CONFIRMED
    assert units[("BBB", "2026-01-02")]["session_completeness"] == KNOWN_FAILED
    daily = daily_cells_from_retained_evidence(unit_coverage=units, reconciliation_rows=[], qualified_value_rows=[])
    assert daily[("AAA", "2026-01-02")]["regular_board_matched_value_vnd"] == 0
    assert daily[("BBB", "2026-01-02")]["matched_value_state"] == KNOWN_FAILED
    assert ("MISSING", "2026-01-02") not in daily


def test_trading_session_window_excludes_holiday_and_emits_exact_adv_and_adtv():
    sessions = _sessions(61)
    cells = {("AAA", session): _qualified_cell("AAA", session, value=1000, volume=100) for session in sessions}
    adv20 = calculate_trailing_feature(ticker="AAA", feature_id="ADV20_MATCHED_SHARES", metric="volume", unit="shares", target_session=sessions[-1], calendar=sessions, size=20, daily_cells=cells)
    adtv60 = calculate_trailing_feature(ticker="AAA", feature_id="ADTV60_MATCHED_VND", metric="value", unit="VND", target_session=sessions[-1], calendar=sessions, size=60, daily_cells=cells)
    assert adv20["status"] == EXACT_WINDOW and adv20["value"] == 100
    assert adtv60["status"] == EXACT_WINDOW and adtv60["value"] == 1000
    assert "2026-01-05" not in adv20["window_sessions"]


def test_partial_and_semantic_windows_never_emit_an_exact_proxy_average():
    sessions = _sessions(21)
    cells = {("AAA", session): _qualified_cell("AAA", session) for session in sessions}
    del cells[("AAA", sessions[1])]
    partial = calculate_trailing_feature(ticker="AAA", feature_id="ADTV20_MATCHED_VND", metric="value", unit="VND", target_session=sessions[-1], calendar=sessions, size=20, daily_cells=cells)
    assert partial["status"] == COVERAGE_RESTRICTED_WINDOW
    assert partial["value"] is None
    cells[("AAA", sessions[1])] = {**_qualified_cell("AAA", sessions[1]), "matched_value_state": SEMANTICS_UNQUALIFIED}
    blocked = calculate_trailing_feature(ticker="AAA", feature_id="ADTV20_MATCHED_VND", metric="value", unit="VND", target_session=sessions[-1], calendar=sessions, size=20, daily_cells=cells)
    assert blocked["status"] == SEMANTICS_UNQUALIFIED_WINDOW
    assert blocked["value"] is None


def test_missing_target_calendar_fails_closed_and_cannot_leak_future_sessions():
    sessions = _sessions(20)
    cells = {("AAA", session): _qualified_cell("AAA", session) for session in sessions}
    result = calculate_trailing_feature(ticker="AAA", feature_id="ADTV20_MATCHED_VND", metric="value", unit="VND", target_session="2026-02-01", calendar=sessions, size=20, daily_cells=cells)
    assert result["status"] == INSUFFICIENT_WINDOW
    assert result["window_sessions"] == []
    assert "TARGET_SESSION_NOT_IN_GOVERNED_CALENDAR" in result["blockers"]


def test_context_separates_research_execution_and_position_sizing_and_is_deterministic():
    sessions = _sessions(61)
    cells = {("AAA", session): _qualified_cell("AAA", session) for session in sessions}
    context = build_ticker_liquidity_context(ticker="AAA", target_session=sessions[-1], calendar=sessions, daily_cells=cells)
    assert context["research_liquidity_eligible"] is True
    assert context["execution_liquidity_input_eligible"] is False
    assert context["position_sizing_eligible"] is False
    assert "recommended_position_size" not in context
    artifact_a = build_artifact(target_session=sessions[-1], universe={"AAA": {}}, calendar=sessions, daily_cells=cells, source_identities={"x": "1"})
    artifact_b = build_artifact(target_session=sessions[-1], universe={"AAA": {}}, calendar=list(reversed(sessions)), daily_cells=cells, source_identities={"x": "1"})
    assert artifact_a["artifact_identity"] == artifact_b["artifact_identity"]
