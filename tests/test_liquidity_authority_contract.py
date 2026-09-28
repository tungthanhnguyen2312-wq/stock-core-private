from __future__ import annotations

from decimal import Decimal

import pytest

import dnse_trades_liquidity_basis as descriptive
import liquidity_authority_contract as c
import official_exchange_trading_statistics as official
from governed_trading_session_calendar import calendar_from_sessions
from market_wide_historical_matched_liquidity import COVERAGE_RESTRICTED_WINDOW, EXACT_WINDOW, INSUFFICIENT_WINDOW

S = "2026-09-28"
D = Decimal


def _tick(board: str, *, qty, gross, time: str = f"{S} 14:45:00.000", market: str = "STO", symbol: str = "HPG") -> dict:
    return {"symbol": symbol, "boardId": board, "marketId": market, "time": time,
            "totalVolumeTraded": D(str(qty)), "grossTradeAmount": D(str(gross))}


# Retained DNSE 2026-09-28 trades_latest counters (HPG/HOSE, SHS/HNX, FHS/UPCoM, CTD/HOSE).
HPG = {"trades": [_tick("G1", qty=2418480, gross="492.561095"), _tick("G4", qty=61005, gross="1.2494203"),
                  _tick("T1", qty=935000, gross="200.5575", time=f"{S} 13:46:24.089"),
                  _tick("T3", qty=474900, gross="102.34095", time="2026-09-18 14:51:34.246")]}
SHS = {"trades": [_tick("G1", qty=1369520, gross="181.91409", market="STX", symbol="SHS"),
                  _tick("G3", qty=1500, gross="0.198", market="STX", symbol="SHS", time=f"{S} 14:59:19.510"),
                  _tick("G4", qty=6082, gross="0.0814103", market="STX", symbol="SHS"),
                  _tick("T1", qty=750, gross="0.1125", market="STX", symbol="SHS", time="2026-08-26 09:50:12.370")]}
FHS = {"trades": [_tick("G1", qty=10, gross="0.0026", market="UPX", symbol="FHS"),
                  _tick("G4", qty=19, gross="0.000475", market="UPX", symbol="FHS"),
                  _tick("T1", qty=7771, gross="2.020616", market="UPX", symbol="FHS")]}


def _row(session: str, exchange: str, **components) -> dict:
    comps = {name: {"volume_shares": v, "value_vnd": w} for name, (v, w) in components.items()}
    return {"session": session, "components": comps, "row_integrity": "COMPONENTS_SUM_TO_TOTAL", "exchange": exchange}


HPG_OFFICIAL = _row(S, official.HOSE, MATCHED_ROUND_LOT=(24184800, 492561095000), MATCHED_ODD_LOT=(61005, 1249420300),
                    PUT_THROUGH_ROUND_LOT=(9350000, 200557500000), PUT_THROUGH_ODD_LOT=(0, 0), TOTAL=(33595805, 694368015300))
SHS_OFFICIAL = _row(S, official.HNX, MATCHED_ALL=(13716282, 182193500300), PUT_THROUGH_ALL=(0, 0), TOTAL=(13716282, 182193500300))
FHS_OFFICIAL = _row(S, official.UPCOM, MATCHED_ALL=(119, 3075000), PUT_THROUGH_ALL=(77716, 2020616000), TOTAL=(77835, 2023691000))


def _recon(body: dict, symbol: str, official_row: dict, exchange: str) -> dict:
    resolved = c.dnse_board_contributions(body, symbol=symbol)
    return c.reconcile_session(c.dnse_session_measures(resolved, session=S), official_row, exchange=exchange)


def test_board_unit_hypothesis_reconciles_hose_exactly_including_put_through():
    recon = _recon(HPG, "HPG", HPG_OFFICIAL, official.HOSE)
    assert recon["verdict"] == c.EXACT and recon["matched_verdict"] == c.EXACT
    assert recon["components"][c.MATCHED_ROUND_LOT]["nonzero_dnse_boards"] == ["G1"]
    assert recon["components"][c.PUT_THROUGH_ROUND_LOT]["dnse"] == {"volume_shares": 9350000, "value_vnd": 200557500000}


def test_hnx_matched_total_needs_the_post_close_g3_board():
    recon = _recon(SHS, "SHS", SHS_OFFICIAL, official.HNX)
    assert recon["verdict"] == c.EXACT
    assert recon["components"][c.MATCHED_ALL]["nonzero_dnse_boards"] == ["G1", "G3", "G4"]
    without_g3 = {"trades": [t for t in SHS["trades"] if t["boardId"] != "G3"]}
    assert _recon(without_g3, "SHS", SHS_OFFICIAL, official.HNX)["components"][c.MATCHED_ALL]["verdict"] == c.CONFLICT
    parsed = descriptive.canonicalize_trade_tick(
        {**SHS["trades"][1], "matchPrice": 1.0, "matchQtty": 1.0, "avgPrice": 1.0,
         "totalVolumeTraded": 1500.0, "grossTradeAmount": 0.198},
        symbol="SHS", endpoint="trades_latest")
    assert parsed["parse_status"] == "PARSED"
    assert parsed["board_semantic"] == "ROUND_LOT"


def test_put_through_cumulative_truncation_is_its_own_verdict_not_a_unit_conflict():
    recon = _recon(FHS, "FHS", FHS_OFFICIAL, official.UPCOM)
    assert recon["components"][c.PUT_THROUGH_ALL]["verdict"] == c.VOLUME_TRUNCATED_VALUE_EXACT
    assert recon["components"][c.PUT_THROUGH_ALL]["volume_delta_shares"] == 6
    assert recon["matched_verdict"] == c.EXACT
    assert recon["put_through_verdict"] == c.VOLUME_TRUNCATED_VALUE_EXACT


def test_a_wrong_unit_is_a_conflict():
    wrong = {**HPG_OFFICIAL, "components": {**HPG_OFFICIAL["components"], c.MATCHED_ROUND_LOT: {"volume_shares": 2418480, "value_vnd": 492561095000}}}
    recon = _recon(HPG, "HPG", wrong, official.HOSE)
    assert recon["components"][c.MATCHED_ROUND_LOT]["verdict"] == c.CONFLICT
    assert recon["components"][c.MATCHED_ROUND_LOT]["volume_delta_shares"] == "-21766320"


def test_missing_or_broken_official_rows_never_reconcile():
    measures = c.dnse_session_measures(c.dnse_board_contributions(HPG, symbol="HPG"), session=S)
    assert c.reconcile_session(measures, None, exchange=official.HOSE)["verdict"] == c.OFFICIAL_ROW_ABSENT
    broken = {**HPG_OFFICIAL, "row_integrity": "COMPONENTS_DO_NOT_SUM_TO_TOTAL"}
    assert c.reconcile_session(measures, broken, exchange=official.HOSE)["verdict"] == "OFFICIAL_ROW_INTEGRITY_FAILED"
    with pytest.raises(c.LiquidityAuthorityContractError):
        c.reconcile_session(measures, {**HPG_OFFICIAL, "session": "2026-09-25"}, exchange=official.HOSE)


def test_board_contributions_bind_to_the_latest_market_and_refuse_foreign_symbols():
    moved = {"trades": [_tick("G1", qty=57920, gross="1", market="STX", symbol="AAV", time="2026-05-14 14:45:00.713"),
                        _tick("G1", qty=13870, gross="1", market="UPX", symbol="AAV", time=f"{S} 14:59:57.418"),
                        {**_tick("ZZ", qty=1, gross="0", market="UPX", symbol="AAV")}]}
    resolved = c.dnse_board_contributions(moved, symbol="AAV")
    assert resolved["exchange"] == official.UPCOM and resolved["boards"]["G1"]["quantity_raw"] == D(13870)
    assert resolved["prior_market_boards"] == {"STX": ["G1"]}
    assert resolved["unknown_boards"] == ["ZZ"]
    with pytest.raises(c.LiquidityAuthorityContractError):
        c.dnse_board_contributions(HPG, symbol="VNM")
    future = {"trades": [_tick("G1", qty=1, gross="1", time="2026-09-29 09:15:00.000")]}
    with pytest.raises(c.LiquidityAuthorityContractError):
        c.dnse_session_measures(c.dnse_board_contributions(future, symbol="HPG"), session=S)


def test_stale_board_points_distinguish_exact_lower_bound_and_conflict():
    resolved = c.dnse_board_contributions(SHS, symbol="SHS")
    rows = {"2026-08-26": _row("2026-08-26", official.HNX, MATCHED_ALL=(1, 1), PUT_THROUGH_ALL=(7500, 112500000), TOTAL=(7501, 112500001))}
    assert [p["verdict"] for p in c.stale_board_points(resolved, rows, exchange=official.HNX, target_session=S)] == [c.EXACT]
    rows["2026-08-26"]["components"][c.PUT_THROUGH_ALL] = {"volume_shares": 9000, "value_vnd": 140000000}
    assert c.stale_board_points(resolved, rows, exchange=official.HNX, target_session=S)[0]["verdict"] == c.LOWER_BOUND_CONSISTENT
    rows["2026-08-26"]["components"][c.PUT_THROUGH_ALL] = {"volume_shares": 700, "value_vnd": 112500000}
    assert c.stale_board_points(resolved, rows, exchange=official.HNX, target_session=S)[0]["verdict"] == c.CONFLICT
    assert c.stale_board_points(resolved, {}, exchange=official.HNX, target_session=S)[0]["verdict"] == c.OFFICIAL_ROW_ABSENT


def _evidence(ticker: str, exchange: str, recon: dict) -> dict:
    return {"ticker": ticker, "exchange": exchange, "kind": "CURRENT_SESSION", "reconciliation": recon}


def test_unit_qualification_needs_three_tickers_per_exchange_and_never_crosses_exchanges():
    recon = _recon(HPG, "HPG", HPG_OFFICIAL, official.HOSE)
    two = c.qualify_board_units([_evidence("A", official.HOSE, recon), _evidence("B", official.HOSE, recon)])
    assert two[official.HOSE]["G1"]["state"] == c.UNIT_INSUFFICIENT
    three = c.qualify_board_units([_evidence(t, official.HOSE, recon) for t in ("A", "B", "C")])
    assert three[official.HOSE]["G1"]["state"] == c.UNIT_QUALIFIED
    assert three[official.HNX]["G1"]["state"] == c.UNIT_UNOBSERVED
    assert three[official.HOSE]["G1"]["scope"]["generalized_to_other_exchanges"] is False


def test_total_is_never_attributed_and_truncation_keeps_value_qualified():
    fhs = _recon(FHS, "FHS", FHS_OFFICIAL, official.UPCOM)
    units = c.qualify_board_units([_evidence(t, official.UPCOM, fhs) for t in ("A", "B", "C")])
    assert units[official.UPCOM]["G1"]["state"] == c.UNIT_QUALIFIED  # TOTAL mismatch does not leak onto G1
    t1 = units[official.UPCOM]["T1"]
    assert t1["value_state"] == c.UNIT_QUALIFIED and t1["volume_state"] == c.UNIT_TRUNCATED and t1["state"] == c.UNIT_TRUNCATED
    wrong = {**HPG_OFFICIAL, "components": {**HPG_OFFICIAL["components"], c.MATCHED_ODD_LOT: {"volume_shares": 610050, "value_vnd": 1249420300}}}
    conflicted = c.qualify_board_units([_evidence(t, official.HOSE, _recon(HPG, "HPG", wrong, official.HOSE)) for t in ("A", "B", "C")])
    assert conflicted[official.HOSE]["G4"]["state"] == c.UNIT_CONFLICTED
    assert conflicted[official.HOSE]["G1"]["state"] == c.UNIT_QUALIFIED


def _base_calendar():
    return calendar_from_sessions(["2026-09-01", "2026-09-02", "2026-09-03"], source={"kind": "EXPLICIT_GOVERNED_SESSION_EVIDENCE", "scope": "test"})


def test_calendar_extension_requires_both_publishers_and_agreement_on_overlap():
    base = _base_calendar()
    extended = c.extend_governed_calendar(base, hose_sessions={"2026-09-02", "2026-09-03", "2026-09-04", "2026-09-07"},
                                          hnx_sessions={"2026-09-02", "2026-09-03", "2026-09-04"}, evidence_identity="t")
    assert extended["state"] == "EXTENDED"
    assert extended["extension_sessions"] == ["2026-09-04"]
    assert extended["single_publisher_dates"] == ["2026-09-07"]
    assert extended["calendar"].sessions[-1] == "2026-09-04"
    disagree = c.extend_governed_calendar(base, hose_sessions={"2026-09-02", "2026-09-04"}, hnx_sessions={"2026-09-02", "2026-09-04"}, evidence_identity="t")
    assert disagree["state"] == "OFFICIAL_CALENDAR_DISAGREES_WITH_GOVERNED_BASE" and disagree["calendar"] is None
    assert disagree["base_only"] == ["2026-09-03"]


def _series(sessions: list[str], exchange: str, value: int = 100) -> dict:
    if exchange == official.HOSE:
        return {s: _row(s, exchange, MATCHED_ROUND_LOT=(10, value), MATCHED_ODD_LOT=(1, 1), MATCHED_ALL=(11, value + 1),
                        PUT_THROUGH_ROUND_LOT=(0, 0), PUT_THROUGH_ODD_LOT=(0, 0), PUT_THROUGH_ALL=(0, 0), TOTAL=(11, value + 1)) for s in sessions}
    return {s: _row(s, exchange, MATCHED_ALL=(10, value), PUT_THROUGH_ALL=(0, 0), TOTAL=(10, value)) for s in sessions}


def _feature(rows: dict, calendar, *, component: str = c.MATCHED_ALL, exchange: str = official.HNX, size: int = 3,
             exhausted: bool = False, oldest: str | None = None) -> dict:
    return c.official_trailing_feature(ticker="X", exchange=exchange, feature_id="F", component=component, metric="value", size=size,
                                       target_session=calendar.sessions[-1], calendar=calendar, rows_by_session=rows,
                                       series_exhausted=exhausted, oldest_retained_session=oldest or (min(rows) if rows else None))


def test_official_trailing_window_is_exact_only_over_every_governed_session():
    cal = _base_calendar()
    rows = _series(list(cal.sessions), official.HNX)
    rows["2026-09-02"] = _row("2026-09-02", official.HNX, MATCHED_ALL=(0, 0), PUT_THROUGH_ALL=(0, 0), TOTAL=(0, 0))
    exact = _feature(rows, cal)
    assert exact["status"] == EXACT_WINDOW and exact["value"] == "66.67"  # a published zero counts as zero
    assert exact["calendar_day_imputation"] is False and exact["zero_fill"] is False
    gap = dict(rows); gap.pop("2026-09-02")
    restricted = _feature(gap, cal, oldest="2026-09-01")
    assert restricted["status"] == COVERAGE_RESTRICTED_WINDOW and restricted["value"] is None
    assert c.MISSING_OFFICIAL_ROW in restricted["blockers"]


def test_official_trailing_window_depth_listing_and_publication_limits():
    cal = _base_calendar()
    shallow = {s: r for s, r in _series(list(cal.sessions), official.HNX).items() if s >= "2026-09-02"}
    assert _feature(shallow, cal)["blockers"] == [c.NOT_ACQUIRED_DEPTH]
    assert _feature(shallow, cal, exhausted=True)["blockers"] == ["SERIES_STARTS_INSIDE_WINDOW"]
    assert _feature(shallow, cal, exhausted=True)["status"] == INSUFFICIENT_WINDOW
    hnx_round_lot = _feature(_series(list(cal.sessions), official.HNX), cal, component=c.MATCHED_ROUND_LOT)
    assert hnx_round_lot["status"] == c.NOT_APPLICABLE and hnx_round_lot["blockers"] == [c.NOT_PUBLISHED_BY_SOURCE]
    hose_all = _feature(_series(list(cal.sessions), official.HOSE), cal, exchange=official.HOSE)
    assert hose_all["status"] == EXACT_WINDOW and hose_all["value"] == "101.00"
    broken = _series(list(cal.sessions), official.HNX)
    broken["2026-09-03"] = {**broken["2026-09-03"], "row_integrity": "COMPONENTS_DO_NOT_SUM_TO_TOTAL"}
    assert "OFFICIAL_ROW_INTEGRITY_FAILED" in _feature(broken, cal)["blockers"]


def test_dimension_fitness_opens_research_only_and_never_sizing_execution_or_pit():
    features = {"ADTV20_MATCHED_ALL_VND": {"status": EXACT_WINDOW}, "ADV20_MATCHED_ALL_SHARES": {"status": EXACT_WINDOW}}
    cell = c.dimension_fitness(current_basis=c.BASIS_OFFICIAL_RECONCILED, current_active=True, official_series_acquired=True, features=features)
    assert cell[c.ADTV_RESEARCH]["state"] == c.ELIGIBLE
    assert cell[c.HISTORICAL_LIQUIDITY_RESEARCH]["state"] == c.ELIGIBLE
    assert cell[c.ADV_VOLUME_RESEARCH]["state"] == c.PARTIAL  # as-traded shares, no corporate-action normalization
    for dimension in (c.POSITION_SIZING, c.EXECUTION_CAPACITY, c.PIT_BACKTEST):
        assert cell[dimension]["state"] == c.BLOCKED
    unacquired = c.dimension_fitness(current_basis=c.BASIS_UNIT_CONTRACT_APPLIED, current_active=True, official_series_acquired=False, features={})
    assert unacquired[c.ADTV_RESEARCH]["state"] == c.BLOCKED and unacquired[c.CURRENT_SESSION_LIQUIDITY_RESEARCH]["state"] == c.ELIGIBLE
    restricted = c.dimension_fitness(current_basis=None, current_active=False, official_series_acquired=True,
                                     features={"ADTV20_MATCHED_ALL_VND": {"status": COVERAGE_RESTRICTED_WINDOW}})
    assert restricted[c.ADTV_RESEARCH]["state"] == c.PARTIAL and restricted[c.CURRENT_SESSION_LIQUIDITY_RESEARCH]["state"] == c.BLOCKED
    tampered = dict(cell); tampered[c.POSITION_SIZING] = {**cell[c.POSITION_SIZING], "state": c.ELIGIBLE}
    with pytest.raises(descriptive.TradesLiquidityBasisError):
        descriptive.assert_fail_closed(tampered)


def test_measurement_basis_and_put_through_precision_follow_board_states():
    qualified = {"state": c.UNIT_QUALIFIED, "volume_state": c.UNIT_QUALIFIED, "value_state": c.UNIT_QUALIFIED}
    truncated = {"state": c.UNIT_TRUNCATED, "volume_state": c.UNIT_TRUNCATED, "value_state": c.UNIT_QUALIFIED}
    units = {"G1": qualified, "G3": {**qualified, "state": c.UNIT_UNOBSERVED}, "G4": qualified, "T1": truncated}
    assert c.matched_measurement_basis(["G1", "G4"], units) == c.BASIS_UNIT_CONTRACT_APPLIED
    assert c.matched_measurement_basis(["G1", "G3"], units) == c.BASIS_RAW_COUNTERS_ONLY
    assert c.matched_measurement_basis(["G3"], units, {"matched_verdict": c.EXACT}) == c.BASIS_OFFICIAL_RECONCILED
    assert c.put_through_precision(["G1"], units) == "NO_PUT_THROUGH_ACTIVE"
    assert c.put_through_precision(["T1"], units) == "VALUE_QUALIFIED_VOLUME_LOWER_BOUND_OR_UNQUALIFIED"
    assert c.put_through_precision(["T1"], units, {"put_through_verdict": c.VOLUME_TRUNCATED_VALUE_EXACT}) == "OFFICIAL_RECONCILED_VALUE_EXACT_VOLUME_TRUNCATED"


def test_prior_cell_adjudication_is_exact_on_hose_and_ordering_only_on_hnx():
    hose = {c.MATCHED_ROUND_LOT: {"volume_shares": 440800, "value_vnd": 3302984000}}
    undercount = c.adjudicate_prior_matched_cell(exchange=official.HOSE, official_components=hose,
                                                 dnse_g1=(400500, 3000338000), fhsc_matched=(440800, 3302984000))
    assert undercount["verdict"] == "OFFICIAL_EQUALS_FHSC_ONLY_DNSE_G1_UNDERCOUNT"
    assert undercount["comparability"] == "EXACT_COMPARABLE_ROUND_LOT_ORDER_MATCHING"
    hnx = {c.MATCHED_ALL: {"volume_shares": 2450895, "value_vnd": 19718850900}}
    ordered = c.adjudicate_prior_matched_cell(exchange=official.HNX, official_components=hnx,
                                              dnse_g1=(2311000, 18603370000), fhsc_matched=(2449900, 19710940000))
    assert ordered["verdict"] == "ORDERING_CONSISTENT_NOT_DIRECTLY_COMPARABLE" and ordered["dnse_g1_vs_fhsc"] == "DNSE_BELOW_FHSC"
    violation = c.adjudicate_prior_matched_cell(exchange=official.HNX, official_components=hnx,
                                                dnse_g1=(2500000, 19800000000), fhsc_matched=(2449900, 19710940000))
    assert violation["verdict"] == "ORDERING_VIOLATION"


def test_sizing_readiness_envelope_reports_gaps_without_emitting_a_size():
    envelope = c.sizing_readiness_envelope(qualified_liquidity_tickers=93)
    assert envelope["POSITION_SIZING"] == c.BLOCKED and envelope["EXECUTION_CAPACITY"] == c.BLOCKED
    assert envelope["position_sizing_is_safe"] is False
    absent = {item["input"] for item in envelope["inputs"] if item["status"] == "ABSENT"}
    assert {"participation_rate_policy", "max_days_to_liquidate_policy", "market_impact_model", "order_size"} <= absent
    assert not any("size" in key and key != "position_sizing_is_safe" for key in envelope if key.islower())
