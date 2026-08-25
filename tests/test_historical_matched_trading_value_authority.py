from __future__ import annotations

import json
import tempfile
from pathlib import Path

import export_ai_bundle as bundle

from historical_matched_traded_value_authority import MATCHED_VALUE_FORMULA, summarize_complete_trade_session
from historical_matched_trading_value_authority import (
    ADTV20_BLOCKED,
    ADTV20_NOT_APPLICABLE,
    ADTV20_PARTIAL,
    ADTV20_READY,
    COVERAGE_RESTRICTED_RECONCILED,
    EXACT_RECONCILED,
    FEATURE_ADTV20,
    FEATURE_ADV20_VOLUME,
    INSUFFICIENT_DISCRIMINATION,
    MATCHED_VALUE_NON_DISCRIMINATING,
    MATCHED_VALUE_OBSERVATION_QUALIFIED,
    MATCHED_VALUE_RESTRICTED_SCOPE,
    RESTRICTED_SCOPE_EXACT,
    UNAVAILABLE,
    UNAVAILABLE_MISSING_TRADES,
    UNAVAILABLE_NO_VALUE_ANCHOR,
    adtv20_matched_value,
    adv20_matched_volume_status,
    build_historical_matched_trading_value_authority,
    classify_conflict_cause,
    classify_session_discrimination,
    content_identity,
    reconcile_expected_session_grid,
    session_value_reconciliation,
    trailing_expected_sessions,
)
from tools.derive_market_wide_current_valuation_input_scaleout import FROZEN_OUTPUTS, _refuse_frozen_output

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "daily_research_session_input_registry.json"
FROZEN_20260821 = "market_wide_current_valuation:e6d015f2feee4cc5c5969d7a1fddac9d2f1b2b55918adb4ea199920e4455b29a"
FROZEN_20260824 = "market_wide_current_valuation:b9ca122464fa5e70c127bae642a32ac4dacc786f1682a828445c5754f4110388"


def _trade(board, price, quantity, time="2026-08-11 14:45:00.000"):
    return {"boardId": board, "matchPrice": price, "matchQtty": quantity, "time": time}


def _qualified_row(*, ticker="HPG", session="2026-08-11", g4=10, t1=5, value=20_000_000, volume=1000):
    candidate = summarize_complete_trade_session(
        ticker=ticker, session=session,
        pages=[
            {"page_index": 0, "page_cursor": None, "next_page_token": "n",
             "trades": [
                 _trade("G1", "20", "100", time=f"{session} 09:15:00.000"),
                 _trade("G4", "20", str(g4), time=f"{session} 09:16:00.000"),
             ]},
            {"page_index": 1, "page_cursor": "n", "next_page_token": None,
             "trades": [_trade("T1", "20", str(t1), time=f"{session} 10:00:00.000")] if t1 else []},
        ],
        raw_payload_hashes=["a", "b"],
    )
    candidate["qualification_status"] = "MATCHED_VALUE_QUALIFIED"
    candidate["matched_value_vnd"] = value
    candidate["g1_share_quantity"] = volume
    candidate["fhsc_reconciliation"] = {
        "status": "EXACT", "fhsc_matched_value": value, "fhsc_matched_volume": volume,
        "g1_to_fhsc_matched_value": "EXACT", "g1_to_fhsc_matched_volume": "EXACT",
    }
    return candidate


def _official(*tickers: str, exchanges: dict[str, str] | None = None) -> dict:
    return {"artifact_identity": "official:test", "records": {
        ticker: {
            "stocklookup_candidate": True,
            "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY",
            "exchange_or_market": (exchanges or {}).get(ticker, "HOSE"),
        }
        for ticker in tickers
    }}


def test_composition_identities_are_preserved_and_missing_boards_are_not_zero():
    row = _qualified_row()
    discrimination = classify_session_discrimination(row["board_composition"])
    assert discrimination["status"] == "DISCRIMINATING"
    assert "G4" in [item["board_id"] for item in row["board_composition"]]
    included = {item["board_id"]: item["included_in_matched_value"] for item in row["board_composition"]}
    assert included["G1"] is True
    assert included["G4"] is False
    assert included["T1"] is False
    assert "T3" in discrimination["missing_boards_not_imputed_zero"]
    g1_only = summarize_complete_trade_session(
        ticker="AAA", session="2026-08-11",
        pages=[{"page_index": 0, "page_cursor": None, "next_page_token": None, "trades": [_trade("G1", "20", "100")]}],
        raw_payload_hashes=["a"],
    )
    g1_only["qualification_status"] = "MATCHED_VALUE_QUALIFIED"
    g1_only["fhsc_reconciliation"] = {"status": "EXACT", "fhsc_matched_value": 20_000_000, "fhsc_matched_volume": 1000}
    assert classify_session_discrimination(g1_only["board_composition"])["status"] == "NON_DISCRIMINATING"
    assert session_value_reconciliation(g1_only) == INSUFFICIENT_DISCRIMINATION


def test_adtv20_uses_trading_sessions_and_does_not_fill_calendar_days():
    calendar = [f"2026-07-{day:02d}" for day in range(1, 21)]
    three = [_qualified_row(session=session) for session in ("2026-08-07", "2026-08-10", "2026-08-11")]
    short = adtv20_matched_value(
        three, expected_trading_sessions=calendar, exchange_by_ticker={"HPG": "HOSE"}, tickers=["HPG"],
    )
    assert short["HPG"]["status"] == ADTV20_BLOCKED
    assert short["HPG"]["adtv20_matched_value_vnd"] is None
    assert short["HPG"]["expected_sessions"] == 20
    assert short["HPG"]["qualified_sessions"] == 0
    assert short["HPG"]["feature_id"] == FEATURE_ADTV20
    assert short["HPG"]["calendar_day_imputation"] is False
    assert short["HPG"]["participation_policy_embedded"] is False
    twenty = [_qualified_row(session=session) for session in calendar]
    ready = adtv20_matched_value(
        twenty, expected_trading_sessions=calendar, exchange_by_ticker={"HPG": "HOSE"}, tickers=["HPG"],
    )
    assert ready["HPG"]["status"] == ADTV20_READY
    assert ready["HPG"]["qualified_sessions"] == 20
    assert ready["HPG"]["adtv20_matched_value_vnd"] == 20_000_000
    assert ready["HPG"]["first_session"] == "2026-07-01"
    assert ready["HPG"]["last_session"] == "2026-07-20"
    assert adv20_matched_volume_status()["feature_id"] == FEATURE_ADV20_VOLUME
    assert adv20_matched_volume_status()["status"] == "NOT_EMITTED"


def test_adtv20_does_not_replace_missing_or_conflict_with_older_qualified_session():
    calendar = [f"2026-07-{day:02d}" for day in range(1, 21)]
    older = _qualified_row(session="2026-06-30")
    window_rows = [_qualified_row(session=session) for session in calendar if session != "2026-07-20"]
    gap = adtv20_matched_value(
        [older, *window_rows],
        expected_trading_sessions=calendar,
        exchange_by_ticker={"HPG": "HOSE"},
        tickers=["HPG"],
    )
    assert gap["HPG"]["status"] == ADTV20_PARTIAL
    assert gap["HPG"]["qualified_sessions"] == 19
    assert gap["HPG"]["unavailable_sessions"] == 1
    assert gap["HPG"]["adtv20_matched_value_vnd"] is None
    assert gap["HPG"]["gap_filled_with_older_session"] is False
    assert "2026-06-30" not in gap["HPG"]["window_sessions"]
    conflict = _qualified_row(session="2026-07-20")
    conflict["qualification_status"] = "CONFLICTING"
    conflict["fhsc_reconciliation"] = {"status": "CONFLICT"}
    conflicted = adtv20_matched_value(
        [older, *window_rows, conflict],
        expected_trading_sessions=calendar,
        exchange_by_ticker={"HPG": "HOSE"},
        tickers=["HPG"],
    )
    assert conflicted["HPG"]["status"] == ADTV20_PARTIAL
    assert conflicted["HPG"]["conflict_sessions"] == 1
    assert conflicted["HPG"]["qualified_sessions"] == 19
    assert conflicted["HPG"]["adtv20_matched_value_vnd"] is None


def test_non_hose_and_non_discriminating_exact_are_not_promoted():
    hose = _qualified_row(ticker="HPG", session="2026-08-11")
    hnx = _qualified_row(ticker="SHS", session="2026-08-11")
    g1_only = _qualified_row(ticker="AAA", session="2026-08-11", g4=0, t1=0)
    assert session_value_reconciliation(hose, exchange="HOSE") == EXACT_RECONCILED
    assert session_value_reconciliation(hnx, exchange="HNX_LISTED") == RESTRICTED_SCOPE_EXACT
    assert session_value_reconciliation(g1_only, exchange="HOSE") == INSUFFICIENT_DISCRIMINATION
    cause = classify_conflict_cause({
        "g1_share_quantity": 1000,
        "fhsc_matched_volume": 1088,
        "board_composition": [
            {"board_id": "G1", "raw_quantity": 100},
            {"board_id": "G4", "raw_quantity": 88},
        ],
    })
    assert cause["cause"] == "FHSC_MATCHED_EQUALS_G1_PLUS_G4_RAW_SHARES"
    assert cause["formula_rewritten"] is False
    calendar = trailing_expected_sessions([f"2026-07-{day:02d}" for day in range(1, 21)])
    hnx_window = [_qualified_row(ticker="SHS", session=session) for session in calendar]
    hnx_adtv = adtv20_matched_value(
        hnx_window, expected_trading_sessions=calendar, exchange_by_ticker={"SHS": "HNX_LISTED"}, tickers=["SHS"],
    )
    assert hnx_adtv["SHS"]["status"] == ADTV20_NOT_APPLICABLE
    assert hnx_adtv["SHS"]["adtv20_matched_value_vnd"] is None
    grid = reconcile_expected_session_grid(
        official_ticker_count=1507, trading_session_count=40, evaluated_pairs=60273,
        exact=13196, conflict=5447, not_comparable=12746, unavailable=28884, structurally_absent=7,
    )
    assert grid["expected_ticker_session_pairs"] == 60280
    assert grid["residual"] == 0


def test_market_wide_dispositions_reconcile_and_do_not_claim_sizing():
    artifact = build_historical_matched_trading_value_authority(
        official_universe=_official("HPG", "AAA", "ZZZ", "SHS", exchanges={"SHS": "HNX_LISTED"}),
        qualified_rows=[
            _qualified_row(session="2026-08-07"),
            _qualified_row(session="2026-08-10"),
            _qualified_row(session="2026-08-11"),
            _qualified_row(ticker="SHS", session="2026-08-11"),
            _qualified_row(ticker="AAA", session="2026-08-11", g4=0, t1=0),
        ],
        trades_universe=["HPG", "AAA", "SHS"],
        expected_trading_sessions=[f"2026-07-{day:02d}" for day in range(1, 21)],
    )
    assert artifact["coverage"]["universe_denominator"] == 4
    assert artifact["coverage"]["denominator_reconciles"] is True
    assert artifact["coverage"]["unexplained_count"] == 0
    assert artifact["records"]["HPG"]["authority_tier"] == MATCHED_VALUE_OBSERVATION_QUALIFIED
    assert artifact["records"]["AAA"]["authority_tier"] == MATCHED_VALUE_NON_DISCRIMINATING
    assert artifact["records"]["SHS"]["authority_tier"] == MATCHED_VALUE_RESTRICTED_SCOPE
    assert artifact["records"]["ZZZ"]["authority_tier"] == UNAVAILABLE_MISSING_TRADES
    assert artifact["coverage"]["adtv20_ready_count"] == 0
    assert artifact["records"]["HPG"]["adtv20_matched_value"]["status"] == ADTV20_BLOCKED
    assert artifact["records"]["SHS"]["adtv20_matched_value"]["status"] == ADTV20_NOT_APPLICABLE
    assert artifact["reconciliation"]["cohort_status"] == UNAVAILABLE
    assert artifact["reconciliation"]["hose_discriminating_exact_sessions"] == 3
    assert artifact["qualified_session_rows"][0]["value_reconciliation"] == EXACT_RECONCILED
    assert artifact["authority_boundary"]["position_sizing_is_safe"] is False
    assert artifact["authority_boundary"]["qualified_liquidity_inputs"] is False
    assert artifact["authority_boundary"]["participation_cap"] == "NOT_EMBEDDED"
    assert artifact["matched_value_contract"]["formula"] == MATCHED_VALUE_FORMULA
    assert artifact["adv20_volume_contract"]["ready_count"] == 0
    replay = build_historical_matched_trading_value_authority(
        official_universe=_official("HPG", "AAA", "ZZZ", "SHS", exchanges={"SHS": "HNX_LISTED"}),
        qualified_rows=[
            _qualified_row(session="2026-08-07"),
            _qualified_row(session="2026-08-10"),
            _qualified_row(session="2026-08-11"),
            _qualified_row(ticker="SHS", session="2026-08-11"),
            _qualified_row(ticker="AAA", session="2026-08-11", g4=0, t1=0),
        ],
        trades_universe=["HPG", "AAA", "SHS"],
        expected_trading_sessions=[f"2026-07-{day:02d}" for day in range(1, 21)],
    )
    assert replay["artifact_identity"] == artifact["artifact_identity"]
    assert content_identity(artifact)["artifact_sha256"] == artifact["artifact_sha256"]
    dumped = json.dumps(artifact)
    assert "5%" not in dumped and "10%" not in dumped
    assert "POSITION_SIZING_IS_SAFE\": true" not in dumped.lower()


def test_opt_in_attach_is_default_off_and_fail_closed():
    artifact = build_historical_matched_trading_value_authority(
        official_universe=_official("HPG"),
        qualified_rows=[_qualified_row()],
        trades_universe=["HPG"],
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "artifact.json"
        path.write_text(json.dumps(artifact), encoding="utf-8")
        entries = {"HPG": {"ticker": "HPG"}, "AAA": {"ticker": "AAA"}}
        off = bundle.attach_historical_matched_trading_value(entries, include=False, artifact_path=str(path))
        assert "historical_matched_trading_value" not in off["HPG"]
        on = bundle.attach_historical_matched_trading_value(
            {"HPG": {"ticker": "HPG"}}, include=True, artifact_path=str(path),
        )
        assert on["HPG"]["historical_matched_trading_value"]["is_actionable"] is False
        assert on["HPG"]["historical_matched_trading_value"]["authority_tier"] == MATCHED_VALUE_OBSERVATION_QUALIFIED
        closed = bundle.attach_historical_matched_trading_value(
            {"HPG": {"ticker": "HPG"}}, include=True, artifact_path=str(Path(tmp) / "missing.json"),
        )
        assert "historical_matched_trading_value" not in closed["HPG"]


def test_frozen_session_identities_unchanged():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["sessions"]["2026-08-21"]["valuation"]["artifact_identity"] == FROZEN_20260821
    assert registry["sessions"]["2026-08-24"]["valuation"]["artifact_identity"] == FROZEN_20260824
    try:
        _refuse_frozen_output(next(iter(FROZEN_OUTPUTS)))
        raise AssertionError("frozen output must be refused")
    except ValueError as exc:
        assert "REFUSING_TO_OVERWRITE_FROZEN_VALUATION_ARTIFACT" in str(exc)


def test_materialized_report_reconciles_when_present():
    path = ROOT / "operations-review" / "historical-matched-trading-value-authority-v1" / "historical_matched_trading_value_authority_report.json"
    if not path.is_file():
        return
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["universe_denominator"] == 1507
    assert report["denominator_reconciles"] is True
    assert report["unexplained_count"] == 0
    assert report["adtv20_ready_count"] == 0
    assert report["adv20_matched_volume_ready_count"] == 0
    assert report["qualified_liquidity_inputs"] is False
    assert report["position_sizing_is_safe"] is False
    assert FROZEN_20260821 in report["frozen_identities_unchanged"]
    assert FROZEN_20260824 in report["frozen_identities_unchanged"]
