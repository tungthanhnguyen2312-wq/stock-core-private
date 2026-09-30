from __future__ import annotations

from decimal import Decimal

import pytest

import current_research_decision_input as decision_input
import liquidity_authority_contract as c
import official_exchange_trading_statistics as official
import official_liquidity_market_wide as w
from governed_trading_session_calendar import calendar_from_sessions
from market_wide_historical_matched_liquidity import EXACT_WINDOW

SESSIONS = [f"2026-08-{d:02d}" for d in (24, 25, 26, 27, 28, 31)] + [f"2026-09-{d:02d}" for d in (1, 3, 4, 7, 8, 9, 10, 11, 14, 15, 16, 17, 18, 21, 22, 23, 24, 25, 28)]
TARGET = "2026-09-28"
CAL = calendar_from_sessions(SESSIONS, source={"kind": "EXPLICIT_GOVERNED_SESSION_EVIDENCE", "scope": "test"})


def _hose_row(session: str, main=(1000, 20_000_000), odd=(5, 100_000)) -> dict:
    comps = {c.MATCHED_ROUND_LOT: main, c.MATCHED_ODD_LOT: odd, c.PUT_THROUGH_ROUND_LOT: (0, 0), c.PUT_THROUGH_ODD_LOT: (0, 0)}
    out = {name: {"volume_shares": v, "value_vnd": val} for name, (v, val) in comps.items()}
    out[c.TOTAL] = {"volume_shares": main[0] + odd[0], "value_vnd": main[1] + odd[1]}
    out[c.MATCHED_ALL] = dict(out[c.TOTAL])
    out[c.PUT_THROUGH_ALL] = {"volume_shares": 0, "value_vnd": 0}
    return {"session": session, "components": out, "row_integrity": "COMPONENTS_SUM_TO_TOTAL", "symbol_binding": "RESPONSE_FIELD"}


def _slot(ticker="AAA", exchange=official.HOSE, sessions=SESSIONS[-20:], exhausted=False, rows=None, failures=None, responses=None, zero=(), broken=()):
    built = rows if rows is not None else {}
    if rows is None:
        for s in sessions:
            row = _hose_row(s, main=(0, 0), odd=(0, 0)) if s in zero else _hose_row(s)
            if s in broken:
                row["row_integrity"] = "COMPONENTS_DO_NOT_SUM_TO_TOTAL"
            built[s] = row
    return {"ticker": ticker, "exchange": exchange, "source": official.SOURCE_HOSE_TRADING_RESULT, "rows": built,
            "responses": responses if responses is not None else [{"index": 0, "sha256": "ab" * 32, "retrieved_at": "t", "url": "u", "parse_status": "PARSED", "rows": len(built)}],
            "parse_failures": failures or [], "rejected_rows": 0, "exhausted": exhausted,
            "oldest": min(built) if built else None, "newest": max(built) if built else None}


def _frame_row(ticker="AAA", route=official.HOSE, resolution="AGREE"):
    return {"ticker": ticker, "official_exchange": route, "official_presence": route is not None, "official_current_universe_status": "X",
            "official_qualification": None, "dnse_exchange": route, "dnse_state": "RESOLVED", "dnse_prior_market_ids": [],
            "exchange_resolution": resolution, "route_exchange": route, "eligibility_reason": "R"}


# ---- rights gate / frame / plan -------------------------------------------------

def test_rights_gate_authorizes_only_hose_for_bulk_acquisition():
    assert w.ACQUISITION_RIGHTS[official.HOSE]["decision"] == w.AUTHORIZED_BOUNDED_INTERNAL
    assert w.ACQUISITION_RIGHTS[official.HOSE]["external_approval_needed"] is None
    for exchange in (official.HNX, official.UPCOM):
        assert w.ACQUISITION_RIGHTS[exchange]["decision"] == w.PUBLIC_ACQUISITION_NOT_AUTHORIZED
        assert "HNX" in w.ACQUISITION_RIGHTS[exchange]["external_approval_needed"]
    for rights in w.ACQUISITION_RIGHTS.values():
        assert rights["redistribution"].startswith("NOT_ESTABLISHED")


def _official_records():
    def rec(exchange, status="OFFICIAL_CURRENT_EXCHANGE_SECURITY", candidate=True):
        return {"stocklookup_candidate": candidate, "current_universe_status": status, "exchange_or_market": exchange, "qualification": "Q"}
    return {"AGR": rec("HOSE"), "OFF": rec("HNX_LISTED", "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE"), "TRF": rec("HOSE"), "CNF": rec("UPCOM", "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE"),
            "DEL": rec("DELISTED", "STOCKLOOKUP_ONLY_UNRESOLVED"), "ZZZ": rec("HOSE", candidate=False), "GHO": rec("DELISTED", "STOCKLOOKUP_ONLY_UNRESOLVED")}


def test_frame_universe_resolution_states_and_no_manufactured_route():
    dnse = {"AGR": {"exchange": official.HOSE, "state": "RESOLVED", "prior_market_boards": {}},
            "TRF": {"exchange": official.HNX, "state": "RESOLVED", "prior_market_boards": {"STO": ["G1"]}},
            "CNF": {"exchange": official.HOSE, "state": "RESOLVED", "prior_market_boards": {}},
            "GHO": {"exchange": official.UPCOM, "state": "RESOLVED", "prior_market_boards": {}}}
    frame = w.frame_universe(_official_records(), dnse)
    assert set(frame) == {"AGR", "OFF", "TRF", "CNF", "DEL", "GHO"}  # non-candidates never enter the governed frame
    assert {t: r["exchange_resolution"] for t, r in frame.items()} == {
        "AGR": "AGREE", "OFF": "OFFICIAL_ONLY", "TRF": "TRANSFER_EVIDENCE", "CNF": "CONFLICT", "DEL": "UNRESOLVED", "GHO": "CONFLICT"}
    assert {t: r["route_exchange"] for t, r in frame.items()} == {"AGR": official.HOSE, "OFF": official.HNX, "TRF": None, "CNF": None, "DEL": None, "GHO": None}
    counts = w.universe_denominators(frame, retained_tickers=[])
    assert counts["governed_universe"] == 6
    assert counts["current_official_presence_denominator"]["count"] == 4
    assert counts["exchange_resolved_subset"]["count"] == 2
    assert counts["source_supported_subset"]["by_exchange"] == {official.HOSE: 1}
    assert w.universe_denominators(frame, retained_tickers=["OFF"])["source_supported_subset"]["by_exchange"] == {official.HNX: 1, official.HOSE: 1}


def test_plan_requests_only_authorized_missing_tickers_and_is_deterministic():
    frame = {t: _frame_row(t, ex) for t, ex in (("AAA", official.HOSE), ("BBB", official.HOSE), ("CCC", official.HNX), ("DDD", official.HNX), ("EEE", official.UPCOM))}
    frame["NNN"] = _frame_row("NNN", None, "UNRESOLVED")
    retained = {"BBB": _slot("BBB"), "DDD": _slot("DDD", official.HNX)}
    plan = w.plan_acquisition(frame, retained, target_session=TARGET, hard_request_budget=50)
    assert [r["symbol"] for r in plan["requests"]] == ["AAA"] and plan["requests"][0]["exchange"] == official.HOSE
    assert plan["planned_by_exchange"] == {official.HOSE: 1}
    assert plan["reused_retained_by_exchange"] == {official.HNX: 1, official.HOSE: 1}
    assert plan["not_authorized_tickers"] == {official.HNX: ["CCC"], official.UPCOM: ["EEE"]}
    assert plan["limits"]["background_daemon"] is False and plan["limits"]["vnstock_kbs_vci_calls"] is False
    assert plan == w.plan_acquisition(frame, retained, target_session=TARGET, hard_request_budget=50)
    with pytest.raises(w.OfficialLiquidityMarketWideError, match="PLAN_EXCEEDS_HARD_REQUEST_BUDGET"):
        w.plan_acquisition(frame, retained, target_session=TARGET, hard_request_budget=0)


def test_stale_or_failed_retained_series_is_replanned_not_reused():
    frame = {"AAA": _frame_row("AAA"), "BBB": _frame_row("BBB")}
    stale = _slot("AAA", sessions=SESSIONS[-21:-1])
    failed = _slot("BBB", failures=[{"index": 0, "outcome": "HTTP_503"}])
    plan = w.plan_acquisition(frame, {"AAA": stale, "BBB": failed}, target_session=TARGET, hard_request_budget=50)
    assert [r["symbol"] for r in plan["requests"]] == ["AAA", "BBB"]


# ---- classification + record ----------------------------------------------------

def _record(slot, row=None, calendar=CAL):
    return w.build_record(row=row or _frame_row(), slot=slot, dnse_item=None, recon=None, units=None, calendar=calendar, target_session=TARGET)


def test_exact_window_record_emits_adtv_adv_ratios_and_partial_adv_authority():
    slot = _slot()
    for s in SESSIONS[-20:]:
        slot["rows"][s] = _hose_row(s, main=(1000, 20_000_000), odd=(0, 0))
    slot["rows"][TARGET] = _hose_row(TARGET, main=(3000, 60_000_000), odd=(0, 0))
    rec = _record(slot)
    assert rec["coverage"]["coverage_class"] == w.EXACT_20_SESSION_WINDOW
    assert rec["features"]["ADTV20_MATCHED_ALL_VND"]["status"] == EXACT_WINDOW
    assert rec["fitness"][c.ADTV_RESEARCH]["state"] == c.ELIGIBLE
    assert rec["fitness"][c.HISTORICAL_LIQUIDITY_RESEARCH]["state"] == c.ELIGIBLE
    assert rec["fitness"][c.ADV_VOLUME_RESEARCH]["state"] == c.PARTIAL
    for blocked in (c.EXECUTION_CAPACITY, c.POSITION_SIZING, c.PIT_BACKTEST):
        assert rec["fitness"][blocked]["state"] == c.BLOCKED
    view = rec["research_view"]
    assert view["adtv20_matched_all_vnd"]["value"] == "22000000.00"
    assert view["current_value_to_adtv20"]["status"] == "VALID" and view["current_value_to_adtv20"]["value"] == "2.7273"
    assert view["current_value_to_adtv20"]["numerator"]["source"] == "OFFICIAL_EXCHANGE_ROW"
    assert view["current_volume_to_adv20"]["authority"].startswith("PARTIAL_AS_TRADED")
    assert view["evidence_currency"]["state"] == "CURRENT_TARGET_SESSION"
    assert rec["evidence_refs"]["responses"][0]["sha256"] == "ab" * 32


def test_zero_trading_is_a_valid_published_zero_never_missing():
    rec = _record(_slot(zero=(SESSIONS[-5],)))
    assert rec["coverage"]["coverage_class"] == w.EXACT_20_SESSION_WINDOW
    assert w.ZERO_TRADING_VALID in rec["coverage"]["labels"] and rec["coverage"]["zero_trading_sessions"] == [SESSIONS[-5]]
    assert rec["features"]["ADTV20_MATCHED_ALL_VND"]["status"] == EXACT_WINDOW


def test_missing_session_and_partial_window_are_distinct_and_never_filled():
    with_gap = _slot(sessions=[s for s in SESSIONS[-21:] if s != SESSIONS[-5]])
    rec = _record(with_gap)
    assert rec["coverage"]["coverage_class"] == w.MISSING_SESSION
    assert rec["features"]["ADTV20_MATCHED_ALL_VND"]["value"] is None
    assert rec["fitness"][c.ADTV_RESEARCH]["state"] == c.PARTIAL
    recent = _record(_slot(sessions=SESSIONS[-8:], exhausted=True))
    assert recent["coverage"]["coverage_class"] == w.PARTIAL_WINDOW
    assert recent["research_view"]["current_value_to_adtv20"]["status"] == "UNAVAILABLE"
    assert recent["fitness"][c.ADTV_RESEARCH]["state"] == c.BLOCKED


def test_failure_classes():
    assert _record(_slot(rows={}, failures=[{"index": 0, "outcome": "HTTP_503"}]))["coverage"]["coverage_class"] == w.HTTP_OR_SOURCE_FAILURE
    assert _record(_slot(rows={}, failures=[{"index": 0, "outcome": "URLError"}]))["coverage"]["coverage_class"] == w.HTTP_OR_SOURCE_FAILURE
    assert _record(_slot(rows={}, failures=[{"index": 0, "outcome": "NOT_ATTEMPTED_BREAKER_OPEN"}]))["coverage"]["coverage_class"] == w.HTTP_OR_SOURCE_FAILURE
    assert _record(_slot(rows={}, failures=[{"index": 0, "outcome": "MALFORMED_JSON"}]))["coverage"]["coverage_class"] == w.SEMANTIC_CONFLICT
    assert _record(_slot(rows={}, failures=[{"index": 0, "outcome": "HOSE_LIST_ABSENT"}]))["coverage"]["coverage_class"] == w.TICKER_NOT_FOUND
    assert _record(_slot(rows={}))["coverage"]["coverage_class"] == w.TICKER_NOT_FOUND
    broken = _record(_slot(broken=(SESSIONS[-3],)))
    assert broken["coverage"]["coverage_class"] == w.SEMANTIC_CONFLICT
    assert broken["fitness"][c.ADTV_RESEARCH]["state"] != c.ELIGIBLE


def test_unauthorized_unsupported_conflict_and_transfer_classes():
    hnx = _record(None, row=_frame_row("HNXT", official.HNX))
    assert hnx["coverage"]["coverage_class"] == w.PUBLIC_ACQUISITION_NOT_AUTHORIZED
    assert "EXTERNAL_APPROVAL_REQUIRED:HNX" in hnx["coverage"]["reason_codes"]
    assert hnx["fitness"][c.ADTV_RESEARCH]["state"] == c.BLOCKED
    assert hnx["fitness"][c.ADTV_RESEARCH]["external_dependency"] == "HNX_INFORMATION_SERVICE_APPROVAL"
    assert hnx["research_view"]["current_value_to_adtv20"]["status"] == "UNAVAILABLE"
    assert _record(None, row=_frame_row("UNR", None, "UNRESOLVED"))["coverage"]["coverage_class"] == w.SOURCE_NOT_SUPPORTED
    assert _record(None, row=_frame_row("CNF", None, "CONFLICT"))["coverage"]["coverage_class"] == w.EXCHANGE_IDENTITY_CONFLICT
    assert _record(None, row=_frame_row("TRF", None, "TRANSFER_EVIDENCE"))["coverage"]["coverage_class"] == w.TRANSFERRED_LISTING


def test_retained_series_for_unauthorized_exchange_is_still_classified_from_its_evidence():
    slot = _slot("SHS", official.HNX)
    for s, row in slot["rows"].items():
        row["components"] = {c.MATCHED_ALL: {"volume_shares": 10, "value_vnd": 1000}, c.PUT_THROUGH_ALL: {"volume_shares": 0, "value_vnd": 0},
                             c.TOTAL: {"volume_shares": 10, "value_vnd": 1000}}
    rec = _record(slot, row=_frame_row("SHS", official.HNX))
    assert rec["coverage"]["coverage_class"] == w.EXACT_20_SESSION_WINDOW


def test_ratio_is_unavailable_for_zero_denominator():
    rec = _record(_slot(zero=tuple(SESSIONS[-20:])))
    assert rec["research_view"]["current_value_to_adtv20"]["reason_codes"] == ["DENOMINATOR_ZERO"]


def test_coverage_tables_and_readiness_never_open_sizing():
    records = {"AAA": _record(_slot()), "BBB": _record(None, row=_frame_row("BBB", official.HNX)), "CCC": _record(None, row=_frame_row("CCC", None, "UNRESOLVED"))}
    tables = w.coverage_tables(records)
    assert tables["by_exchange_and_class"][official.HOSE] == {w.EXACT_20_SESSION_WINDOW: 1}
    assert tables["by_exchange_and_class"][official.HNX] == {w.PUBLIC_ACQUISITION_NOT_AUTHORIZED: 1}
    assert tables["unrouted_by_class"] == {w.SOURCE_NOT_SUPPORTED: 1}
    assert tables["adtv20_exact_total"] == 1
    readiness = w.execution_capacity_readiness(records["AAA"])
    assert set(readiness) == set(w.READINESS_DIMENSIONS) and set(readiness.values()) <= set(w.READINESS_STATES)
    assert readiness["ADTV20"] == w.AVAILABLE_DATA and readiness["PARTICIPATION_RATE_POLICY"] == w.POLICY_NOT_DEFINED
    assert readiness["POINT_IN_TIME_LIQUIDITY_KNOWLEDGE"] == w.PIT_REQUIRED and readiness["ORDER_SIZE_INPUT"] == w.USER_INPUT_REQUIRED
    assert w.execution_capacity_readiness(records["BBB"])["ADTV20"] == w.DATA_NOT_QUALIFIED
    summary = w.readiness_summary(records)
    assert summary["position_sizing"] == c.BLOCKED and summary["execution_capacity"] == c.BLOCKED


# ---- Daily decision-input integration -------------------------------------------

def test_official_liquidity_enriches_only_the_liquidity_dimension():
    exact = _record(_slot())
    blocked = _record(None, row=_frame_row("BBB", official.HNX))
    base = decision_input._liquidity({}, None)
    assert base["state"] == decision_input.BLOCKED and "qualified_research" not in base
    good = decision_input._liquidity({}, None, exact)
    assert good["state"] == decision_input.AVAILABLE and good["authority"] == decision_input.RESEARCH_QUALIFIED
    assert good["qualified_research"]["adtv20_matched_all_vnd"]["status"] == EXACT_WINDOW
    assert good["execution"]["state"] == decision_input.BLOCKED
    unauthorized = decision_input._liquidity({}, None, blocked)
    assert unauthorized["state"] == decision_input.BLOCKED
    assert unauthorized["qualified_research"]["fitness"]["ADTV_RESEARCH"] == "BLOCKED"
    assert unauthorized["qualified_research"]["fitness"]["EXECUTION_CAPACITY"] == "BLOCKED"


def test_descriptive_eligible_does_not_override_official_adtv_fitness():
    exact = _record(_slot())
    descriptive = {"disposition": "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE",
                   "liquidity_research_contract": {"EXECUTION_CAPACITY": {"state": "BLOCKED"}, "POSITION_SIZING": {"state": "BLOCKED"}}}
    both = decision_input._liquidity({}, descriptive, exact)
    assert both["authority"] == decision_input.RESEARCH_QUALIFIED
    assert both["research"]["state"] == decision_input.AVAILABLE
    assert both["qualified_research"]["fitness"]["ADTV_RESEARCH"] == "ELIGIBLE"
    assert both["execution"]["state"] == decision_input.BLOCKED
    unauthorized = _record(None, row=_frame_row("BBB", official.HNX))
    mixed_blocked = decision_input._liquidity({}, descriptive, unauthorized)
    assert mixed_blocked["qualified_research"]["fitness"]["ADTV_RESEARCH"] == "BLOCKED"
    assert mixed_blocked["research"]["state"] == decision_input.AVAILABLE
    assert mixed_blocked["authority"] == decision_input.CURRENT_DESCRIPTIVE_ONLY


def test_artifact_summary_cannot_override_per_record_fitness():
    exact = _record(_slot())
    blocked = _record(None, row=_frame_row("BBB", official.HNX))
    summary = w.artifact_authority_summary({"AAA": exact, "BBB": blocked})
    assert summary["ADTV_RESEARCH"]["state"] == w.SCOPED_ELIGIBLE
    assert summary["ADTV_RESEARCH"]["eligible_count"] == 1
    assert summary["CURRENT_SESSION_LIQUIDITY_RESEARCH"]["eligible_count"] == 0
    assert summary["ADV_VOLUME_RESEARCH"]["state"] == w.SCOPED_PARTIAL
    assert summary["ADV_VOLUME_RESEARCH"]["basis"] == w.AS_TRADED_NOT_CA_NORMALIZED
    assert summary["QUALIFIED_LIQUIDITY_INPUTS"]["state"] == w.PER_RECORD
    assert summary["EXECUTION_CAPACITY"] == c.BLOCKED
    assert summary["PIT_BACKTEST"] == c.BLOCKED
    assert summary["LIVE_POSITION_SIZING"] == c.BLOCKED
    assert summary["RAW_AS_TRADED"] == "NOT_PROMOTED"
    assert summary["artifact_summary_cannot_override_per_record_fitness"] is True
    assert w.fitness_state(blocked, c.ADTV_RESEARCH) == c.BLOCKED
    assert w.fitness_state(exact, c.ADTV_RESEARCH) == c.ELIGIBLE
    assert blocked["coverage"]["coverage_class"] == w.PUBLIC_ACQUISITION_NOT_AUTHORIZED


def test_missing_official_liquidity_does_not_change_evidence_class():
    dims_with = {"MARKET": {"state": "AVAILABLE"}, "TECHNICAL": {"state": "AVAILABLE"}, "FUNDAMENTAL": {"state": "AVAILABLE"}, "VALUATION": {"state": "AVAILABLE"},
                 "LIQUIDITY": decision_input._liquidity({}, None, None)}
    dims_official = {**dims_with, "LIQUIDITY": decision_input._liquidity({}, None, _record(_slot()))}
    assert decision_input.evidence_class(dims_with) == decision_input.evidence_class(dims_official)
    assert "LIQUIDITY" not in decision_input.PRIMARY_FACTORS


def test_every_legacy_liquidity_proxy_consumer_is_classified():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    pattern = re.compile("|".join(w.LEGACY_PROXY_TOKENS))
    found = {p.name for p in root.glob("*.py") if p.name != "official_liquidity_market_wide.py" and pattern.search(p.read_text(encoding="utf-8", errors="ignore"))}
    assert found <= set(w.LEGACY_LIQUIDITY_CONSUMERS), f"unclassified legacy liquidity consumers: {sorted(found - set(w.LEGACY_LIQUIDITY_CONSUMERS))}"
    assert set(w.LEGACY_LIQUIDITY_CONSUMERS) <= found, "inventory names a module that no longer references a legacy liquidity proxy"
    for name, item in w.LEGACY_LIQUIDITY_CONSUMERS.items():
        assert item["state"] in (w.ACTIVE, w.SHADOW, w.DEAD, w.HISTORICAL_ONLY) and item["disposition"], name


# ---- G3 / board semantics on the Daily-facing path --------------------------------

def _tick(board, market, qty, gross, time=f"{TARGET} 14:45:00.000", symbol="AAA"):
    return {"symbol": symbol, "boardId": board, "marketId": market, "time": time, "totalVolumeTraded": Decimal(str(qty)), "grossTradeAmount": Decimal(str(gross))}


def _units_with_exact_evidence():
    def evidence(exchange, component, boards):
        return [{"ticker": f"T{i}", "exchange": exchange, "kind": "CURRENT_SESSION",
                 "reconciliation": {"session": TARGET, "components": {component: {"verdict": c.EXACT, "nonzero_dnse_boards": boards}}}} for i in range(3)]
    return c.qualify_board_units(evidence(official.HNX, c.MATCHED_ALL, ["G1", "G3", "G4"]) + evidence(official.HOSE, c.MATCHED_ROUND_LOT, ["G1"]))


def _dnse_record(ticks, exchange, symbol="AAA"):
    row = _frame_row(symbol, exchange)
    item = c.dnse_board_contributions({"trades": ticks}, symbol=symbol)
    return w.build_record(row=row, slot=None, dnse_item=item, recon=None, units=_units_with_exact_evidence(), calendar=CAL, target_session=TARGET)


def test_hnx_post_close_g3_is_counted_only_where_its_unit_is_qualified_for_that_exchange():
    hnx = _dnse_record([_tick("G1", "STX", 100, "0.5"), _tick("G3", "STX", 10, "0.05")], official.HNX)
    view = hnx["research_view"]["current_session"]
    assert view["active_boards"] == ["G1", "G3"] and view["measurement_basis"] == c.BASIS_UNIT_CONTRACT_APPLIED
    # G1 100 raw x 10 + G3 10 raw x 10 = 1,100 shares; 0.5 + 0.05 billion VND
    assert view["matched_volume_shares"]["amount"] == 1100 and view["matched_value_vnd"]["amount"] == 550000000
    assert view["matched_value_vnd"]["source"] == "DNSE_QUALIFIED_BOARD_UNIT_CONTRACT"
    # HNX evidence is never generalized to HOSE: a HOSE ticker with G3 active stays raw-counter only.
    hose = _dnse_record([_tick("G1", "STO", 100, "0.5"), _tick("G3", "STO", 10, "0.05")], official.HOSE)
    assert hose["research_view"]["current_session"]["measurement_basis"] == c.BASIS_RAW_COUNTERS_ONLY
    assert hose["research_view"]["current_session"]["matched_value_vnd"] is None
    assert hose["fitness"][c.CURRENT_SESSION_LIQUIDITY_RESEARCH]["measurement_basis"] == c.BASIS_RAW_COUNTERS_ONLY


def test_stale_boards_of_a_prior_exchange_never_enter_the_current_measures():
    ticks = [_tick("G1", "STX", 100, "0.5"), _tick("G1", "STO", 99999, "99.0", time="2026-09-10 14:45:00.000"), _tick("G3", "STO", 5, "5.0", time="2026-09-10 14:59:00.000")]
    record = _dnse_record(ticks, official.HNX)
    view = record["research_view"]["current_session"]
    assert view["active_boards"] == ["G1"] and view["matched_volume_shares"]["amount"] == 1000
    # A ticker whose official master says HOSE but whose DNSE latest market is HNX (with prior STO boards) is a transfer, not a route.
    frame = w.frame_universe({"AAA": {"stocklookup_candidate": True, "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY", "exchange_or_market": "HOSE"}},
                             {"AAA": c.dnse_board_contributions({"trades": ticks}, symbol="AAA")})
    assert frame["AAA"]["exchange_resolution"] == "TRANSFER_EVIDENCE" and frame["AAA"]["route_exchange"] is None


def test_dnse_board_vocabulary_includes_g3_as_round_lot_post_close():
    from market_phase2_foundation import DNSE_BOARD_SEMANTICS
    assert DNSE_BOARD_SEMANTICS["G3"] == "ROUND_LOT"
    assert c.DNSE_BOARD_UNIT_HYPOTHESIS["G3"]["phase"] == "POST_CLOSE_ORDER_MATCHING"
