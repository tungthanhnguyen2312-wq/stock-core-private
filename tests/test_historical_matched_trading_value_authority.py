from __future__ import annotations

import json
import tempfile
from pathlib import Path

import export_ai_bundle as bundle

from historical_matched_traded_value_authority import MATCHED_VALUE_FORMULA, summarize_complete_trade_session
from historical_matched_trading_value_authority import (
    COVERAGE_RESTRICTED_RECONCILED,
    EXACT_RECONCILED,
    FEATURE_ADTV20,
    FEATURE_ADV20_VOLUME,
    INSUFFICIENT_DISCRIMINATION,
    MATCHED_VALUE_OBSERVATION_QUALIFIED,
    UNAVAILABLE_MISSING_TRADES,
    UNAVAILABLE_NO_VALUE_ANCHOR,
    adtv20_matched_value,
    adv20_matched_volume_status,
    build_historical_matched_trading_value_authority,
    classify_session_discrimination,
    content_identity,
    session_value_reconciliation,
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


def _official(*tickers: str) -> dict:
    return {"artifact_identity": "official:test", "records": {
        ticker: {"stocklookup_candidate": True, "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY"}
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
    three = [_qualified_row(session=session) for session in ("2026-08-07", "2026-08-10", "2026-08-11")]
    short = adtv20_matched_value(three)
    assert short["HPG"]["status"] == "ADTV20_INSUFFICIENT_HISTORY"
    assert short["HPG"]["adtv20_matched_value_vnd"] is None
    assert short["HPG"]["expected_sessions"] == 20
    assert short["HPG"]["observed_sessions"] == 3
    assert short["HPG"]["feature_id"] == FEATURE_ADTV20
    assert short["HPG"]["calendar_day_imputation"] is False
    assert short["HPG"]["participation_policy_embedded"] is False
    twenty = [_qualified_row(session=f"2026-07-{day:02d}") for day in range(1, 21)]
    ready = adtv20_matched_value(twenty)
    assert ready["HPG"]["status"] == "ADTV20_READY"
    assert ready["HPG"]["observed_sessions"] == 20
    assert ready["HPG"]["adtv20_matched_value_vnd"] == 20_000_000
    assert adv20_matched_volume_status()["feature_id"] == FEATURE_ADV20_VOLUME
    assert adv20_matched_volume_status()["status"] == "NOT_EMITTED"


def test_market_wide_dispositions_reconcile_and_do_not_claim_sizing():
    artifact = build_historical_matched_trading_value_authority(
        official_universe=_official("HPG", "AAA", "ZZZ"),
        qualified_rows=[
            _qualified_row(session="2026-08-07"),
            _qualified_row(session="2026-08-10"),
            _qualified_row(session="2026-08-11"),
        ],
        trades_universe=["HPG", "AAA"],
    )
    assert artifact["coverage"]["universe_denominator"] == 3
    assert artifact["coverage"]["denominator_reconciles"] is True
    assert artifact["coverage"]["unexplained_count"] == 0
    assert artifact["records"]["HPG"]["authority_tier"] == MATCHED_VALUE_OBSERVATION_QUALIFIED
    assert artifact["records"]["AAA"]["authority_tier"] == UNAVAILABLE_NO_VALUE_ANCHOR
    assert artifact["records"]["ZZZ"]["authority_tier"] == UNAVAILABLE_MISSING_TRADES
    assert artifact["coverage"]["adtv20_ready_count"] == 0
    assert artifact["reconciliation"]["cohort_status"] == COVERAGE_RESTRICTED_RECONCILED
    assert artifact["reconciliation"]["discriminating_sessions"] == 3
    assert artifact["qualified_session_rows"][0]["value_reconciliation"] == EXACT_RECONCILED
    assert artifact["authority_boundary"]["position_sizing_is_safe"] is False
    assert artifact["authority_boundary"]["qualified_liquidity_inputs"] is False
    assert artifact["authority_boundary"]["participation_cap"] == "NOT_EMBEDDED"
    assert artifact["matched_value_contract"]["formula"] == MATCHED_VALUE_FORMULA
    assert artifact["adv20_volume_contract"]["ready_count"] == 0
    replay = build_historical_matched_trading_value_authority(
        official_universe=_official("HPG", "AAA", "ZZZ"),
        qualified_rows=[
            _qualified_row(session="2026-08-07"),
            _qualified_row(session="2026-08-10"),
            _qualified_row(session="2026-08-11"),
        ],
        trades_universe=["HPG", "AAA"],
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
