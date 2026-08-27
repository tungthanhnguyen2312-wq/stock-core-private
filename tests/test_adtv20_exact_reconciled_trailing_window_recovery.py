"""ADTV20 trailing-window recovery: exact calendar, no substitution, G1-only, budget."""
from __future__ import annotations

import inspect

import pytest

import adtv20_exact_reconciled_trailing_window_recovery as rec
from historical_matched_traded_value_authority import MATCHED_VALUE_FORMULA
from historical_matched_trading_value_authority import (
    ADTV20_BLOCKED,
    ADTV20_NOT_APPLICABLE,
    ADTV20_PARTIAL,
    ADTV20_READY,
    trailing_expected_sessions,
)
from tests.test_historical_matched_trading_value_authority import _qualified_row

WINDOW = [f"2026-07-{day:02d}" for day in range(1, 21)]
HOSE = {"HPG": "HOSE", "VCB": "HOSE", "AAA": "HOSE"}


def _exact(ticker="HPG", session="2026-07-01", **kwargs):
    return _qualified_row(ticker=ticker, session=session, **kwargs)


def _inventory(qualified, recon=None, tickers=("HPG", "SSI"), exchanges=None, window=WINDOW, absent=()):
    exchanges = exchanges or {"HPG": "HOSE", "SSI": "HNX_LISTED"}
    return rec.inventory_trailing20(
        tickers=list(tickers),
        exchanges=exchanges,
        window=window,
        qualified_rows=qualified,
        recon_rows=recon or [],
        structurally_absent=absent,
    )


def test_trailing20_calendar_is_exact_and_deterministic():
    calendar = [f"2026-06-{d:02d}" for d in range(1, 31)] + WINDOW
    assert trailing_expected_sessions(calendar) == WINDOW
    assert trailing_expected_sessions(calendar) == trailing_expected_sessions(list(reversed(calendar)))
    assert rec.EXPECTED_ADTV_SESSIONS == 20


def test_older_session_cannot_substitute_missing_expected_session():
    older = _exact(session="2026-06-30")
    window_rows = [_exact(session=session) for session in WINDOW if session != "2026-07-20"]
    features = rec.recompute_adtv20(
        rec.evaluation_rows_from_qualified([older, *window_rows], HOSE),
        tickers=["HPG"], exchanges={"HPG": "HOSE"}, window=WINDOW,
    )
    assert features["features"]["HPG"]["status"] == ADTV20_PARTIAL
    assert features["features"]["HPG"]["qualified_sessions"] == 19
    assert features["ready_count"] == 0
    assert "2026-06-30" not in features["features"]["HPG"]["window_sessions"]
    assert features["features"]["HPG"]["gap_filled_with_older_session"] is False


def test_missing_is_not_zero():
    rows = [_exact(session=session) for session in WINDOW[:19]]
    features = rec.recompute_adtv20(
        rec.evaluation_rows_from_qualified(rows, {"HPG": "HOSE"}),
        tickers=["HPG"], exchanges={"HPG": "HOSE"}, window=WINDOW,
    )
    assert features["features"]["HPG"]["adtv20_matched_value_vnd"] is None
    assert features["features"]["HPG"]["unavailable_sessions"] == 1


def test_g1_formula_unchanged_and_g4_excluded():
    assert rec.MATCHED_VALUE_FORMULA == MATCHED_VALUE_FORMULA
    assert rec.MATCHED_VALUE_FORMULA == "sum(G1.matchPrice * G1.matchQtty) * 10 * 1000"
    row = _exact()
    included = {item["board_id"]: item["included_in_matched_value"] for item in row["board_composition"]}
    assert included["G1"] is True
    assert included["G4"] is False


def test_g1_plus_g4_conflict_pattern_remains_conflict():
    recon = {
        "ticker": "HPG", "session": "2026-07-01", "status": "CONFLICT",
        "g1_share_quantity": 1000, "fhsc_matched_volume": 1010,
        "board_composition": [
            {"board_id": "G1", "raw_quantity": 100, "included_in_matched_value": True},
            {"board_id": "G4", "raw_quantity": 10, "included_in_matched_value": False},
        ],
    }
    state = rec.classify_cell(
        ticker="HPG", session="2026-07-01", exchange="HOSE",
        qualified_row=None, recon_row=recon, structurally_absent=False,
    )
    assert state == rec.STATE_G1_PLUS_G4_CONFLICT
    conflict = _exact(session="2026-07-20")
    conflict["qualification_status"] = "CONFLICTING"
    conflict["fhsc_reconciliation"] = {"status": "CONFLICT"}
    mixed = [_exact(session=session) for session in WINDOW if session != "2026-07-20"] + [conflict]
    result = rec.recompute_adtv20(
        rec.evaluation_rows_from_qualified(mixed, {"HPG": "HOSE"}),
        tickers=["HPG"], exchanges={"HPG": "HOSE"}, window=WINDOW,
    )
    assert result["features"]["HPG"]["status"] != ADTV20_READY
    assert result["features"]["HPG"]["conflict_sessions"] == 1


def test_non_discriminating_exact_is_not_authoritative():
    g1_only = _exact(session="2026-07-01")
    g1_only["board_composition"] = [item for item in g1_only["board_composition"] if item["board_id"] == "G1"]
    inv = _inventory([g1_only], tickers=("HPG",), exchanges={"HPG": "HOSE"}, window=["2026-07-01"])
    assert inv["state_counts"][rec.STATE_NUMERIC_EXACT_NON_DISCRIMINATING] == 1
    assert inv["state_counts"][rec.STATE_QUALIFIED_G1_EXACT] == 0


def test_exchange_scope_preserved():
    row = _exact(ticker="SSI", session="2026-07-01")
    inv = _inventory([row], tickers=("SSI",), exchanges={"SSI": "HNX_LISTED"}, window=["2026-07-01"])
    assert inv["state_counts"][rec.STATE_EXCHANGE_NOT_APPLICABLE] == 1
    features = rec.recompute_adtv20(
        rec.evaluation_rows_from_qualified([row], {"SSI": "HNX_LISTED"}),
        tickers=["SSI"], exchanges={"SSI": "HNX_LISTED"}, window=WINDOW,
    )
    assert features["features"]["SSI"]["status"] == ADTV20_NOT_APPLICABLE


def test_inventory_residual_zero():
    qualified = [_exact(ticker="HPG", session=session) for session in WINDOW[:5]]
    recon = [{"ticker": "HPG", "session": WINDOW[5], "status": "CONFLICT"}]
    inv = _inventory(qualified, recon=recon, tickers=("HPG", "SSI"), exchanges={"HPG": "HOSE", "SSI": "UPCOM"}, absent=(("SSI", WINDOW[0]),))
    assert inv["residual"] == 0
    assert inv["expected_ticker_session_pairs"] == 40
    assert inv["accounted"] == 40
    assert inv["state_counts"][rec.STATE_STRUCTURALLY_ABSENT] == 1
    assert inv["state_counts"][rec.STATE_QUALIFIED_G1_EXACT] == 5
    assert inv["state_counts"][rec.STATE_CONFLICT_G1_VS_FHSC] == 1
    assert inv["state_counts"][rec.STATE_FHSC_MISSING] == 40 - 5 - 1 - 1


def test_19_of_20_is_partial_never_ready():
    rows = [_exact(session=session) for session in WINDOW[:19]]
    features = rec.recompute_adtv20(
        rec.evaluation_rows_from_qualified(rows, {"HPG": "HOSE"}),
        tickers=["HPG"], exchanges={"HPG": "HOSE"}, window=WINDOW,
    )
    assert features["features"]["HPG"]["status"] == ADTV20_PARTIAL
    assert features["ready_count"] == 0
    assert features["features"]["HPG"]["qualified_sessions"] == 19


def test_20_of_20_is_ready():
    rows = [_exact(session=session) for session in WINDOW]
    features = rec.recompute_adtv20(
        rec.evaluation_rows_from_qualified(rows, {"HPG": "HOSE"}),
        tickers=["HPG"], exchanges={"HPG": "HOSE"}, window=WINDOW,
    )
    assert features["features"]["HPG"]["status"] == ADTV20_READY
    assert features["ready_count"] == 1
    assert features["features"]["HPG"]["qualified_sessions"] == 20


def test_one_conflict_in_window_is_not_ready():
    rows = [_exact(session=session) for session in WINDOW[:19]]
    conflict = _exact(session=WINDOW[19])
    conflict["qualification_status"] = "CONFLICTING"
    conflict["fhsc_reconciliation"] = {"status": "CONFLICT"}
    features = rec.recompute_adtv20(
        rec.evaluation_rows_from_qualified([*rows, conflict], {"HPG": "HOSE"}),
        tickers=["HPG"], exchanges={"HPG": "HOSE"}, window=WINDOW,
    )
    assert features["features"]["HPG"]["status"] != ADTV20_READY
    assert features["features"]["HPG"]["conflict_sessions"] == 1


def test_one_missing_expected_session_is_not_ready():
    rows = [_exact(session=session) for session in WINDOW[:19]]
    features = rec.recompute_adtv20(
        rec.evaluation_rows_from_qualified(rows, {"HPG": "HOSE"}),
        tickers=["HPG"], exchanges={"HPG": "HOSE"}, window=WINDOW,
    )
    assert features["features"]["HPG"]["status"] != ADTV20_READY
    assert features["features"]["HPG"]["unavailable_sessions"] == 1


def test_new_evidence_upgrades_only_its_exact_ticker_session_cell():
    hpg = [_exact(ticker="HPG", session=session) for session in WINDOW[:19]]
    vcb = [_exact(ticker="VCB", session=session) for session in WINDOW[:10]]
    rows = rec.evaluation_rows_from_qualified([*hpg, *vcb], {"HPG": "HOSE", "VCB": "HOSE"})
    before = rec.recompute_adtv20(rows, tickers=["HPG", "VCB"], exchanges={"HPG": "HOSE", "VCB": "HOSE"}, window=WINDOW)
    added = rec.evaluation_rows_from_qualified([_exact(ticker="HPG", session=WINDOW[19])], {"HPG": "HOSE"})[0]
    merged = rec.merge_new_exact_row(rows, added)
    after = rec.recompute_adtv20(merged, tickers=["HPG", "VCB"], exchanges={"HPG": "HOSE", "VCB": "HOSE"}, window=WINDOW)
    assert after["features"]["HPG"]["status"] == ADTV20_READY
    assert after["features"]["VCB"]["qualified_sessions"] == before["features"]["VCB"]["qualified_sessions"] == 10
    assert after["features"]["VCB"]["status"] == ADTV20_PARTIAL


def test_acquisition_plan_is_deterministic_and_closest_to_ready():
    qualified = []
    for session in WINDOW[:19]:
        qualified.append(_exact(ticker="AAA", session=session))
    for session in WINDOW[:18]:
        qualified.append(_exact(ticker="BID", session=session))
    for session in WINDOW[:5]:
        qualified.append(_exact(ticker="HPG", session=session))
    inv = _inventory(qualified, tickers=("AAA", "BID", "HPG", "SSI"), exchanges={"AAA": "HOSE", "BID": "HOSE", "HPG": "HOSE", "SSI": "HNX_LISTED"})
    plan = rec.acquisition_plan(inv, budget=2)
    assert [item["ticker"] for item in plan["selected"]] == ["AAA", "BID"]
    assert rec.acquisition_plan(inv, budget=2)["selected"] == plan["selected"]
    assert plan["selection_rule"] == "HOSE_TICKERS_SOLE_BLOCKER_FHSC_MISSING_CLOSEST_TO_20_OF_20"
    assert [item["ticker"] for item in plan["selected"]] != ["HPG"]


def test_request_budget_enforced_and_rate_limit_retains_partial_without_fabricated_rows(tmp_path):
    plan = {
        "request_budget": 6,
        "selected": [{"ticker": name, "fhsc_missing_sessions": ["2026-08-06"]} for name in ("AAA", "BID", "CTG", "DPM", "BWE", "MZG")],
    }

    def limited(symbol, **kwargs):
        limited.calls.append(symbol)
        if len(limited.calls) == 2:
            return {
                "symbol": symbol, "successful": False, "http_status": 429,
                "failure_disposition": "HTTP_ERROR_429", "rate_limited": True,
                "raw_response_retained": False,
            }
        return {
            "symbol": symbol, "successful": True, "http_status": 200,
            "raw_bytes": b'{"data":{"data":[]}}', "raw_sha256": "cd" * 32, "rate_limited": False,
        }

    limited.calls = []
    result = rec.run_bounded_acquisition(plan, api_key="k", raw_dir=tmp_path, budget=6, fetcher=limited)
    assert result["requests_sent"] == 2
    assert result["terminated_reason"] == "RATE_LIMITED"
    assert result["http_disposition"]["HTTP_200"] == 1
    assert result["http_disposition"]["HTTP_429"] == 1
    assert len(result["records"]) == 2
    assert "BID" not in result["new_fhsc_sessions"]

    def once(symbol, **kwargs):
        once.calls.append(symbol)
        return {
            "symbol": symbol, "successful": True, "http_status": 200,
            "raw_bytes": b'{"data":{"data":[]}}', "raw_sha256": "ef" * 32, "rate_limited": False,
        }

    once.calls = []
    capped = rec.run_bounded_acquisition(plan, api_key="k", raw_dir=tmp_path, budget=1, fetcher=once)
    assert capped["requests_sent"] == 1
    assert capped["terminated_reason"] == "BUDGET_EXHAUSTED"
    assert once.calls == ["AAA"]


def test_no_new_provider_or_forbidden_outputs():
    source = inspect.getsource(rec)
    assert "eodhd" not in source.lower()
    assert "ADV20_MATCHED_VOLUME" in source
    artifact = rec.build_recovery_artifact(
        inventory={"window": WINDOW, "expected_ticker_session_pairs": 0, "accounted": 0, "residual": 0,
                   "state_counts": {}, "hose_state_counts": {}, "fhsc_missing_by_session": {},
                   "session_wide_fhsc_holes": ["2026-08-06"], "per_ticker": {}},
        plan={"request_budget": 6, "selected": [], "selection_rule": "x", "route": "FHSC", "route_role": "SUPPLEMENTAL_BOUNDED", "eligible_count": 0},
        before={"ready_count": 0, "partial_count": 213, "blocked_count": 190, "not_applicable_count": 1104},
        after={"ready_count": 0, "partial_count": 213, "blocked_count": 190, "not_applicable_count": 1104, "features": {}},
        acquisition={"requests_sent": 0, "request_budget": 6, "http_disposition": {}, "terminated_reason": "EMPTY", "records": []},
    )
    assert artifact["authority_effect"] == "NONE"
    assert artifact["adv20_matched_volume"]["status"] == "NOT_EMITTED"
    assert artifact["authority_boundary"]["qualified_liquidity_inputs"] is False
    assert artifact["authority_boundary"]["position_sizing_is_safe"] is False
    assert artifact["authority_boundary"]["raw_as_traded"] == "NOT_PROMOTED"
    assert artifact["authority_boundary"]["pit"] == "BLOCKED"
    assert "slippage" not in artifact
    assert "participation_rate" not in artifact
    text = rec.json_dumps(artifact)
    assert "TARGET_PRICE" not in text
    assert "PROBABILITY" not in text
    assert artifact["outcome"] == rec.OUTCOME_C


def test_module_has_no_sleep_or_background_loop():
    source = inspect.getsource(rec)
    assert "sleep(" not in source
    assert "time.sleep" not in source
    assert inspect.getsource(rec.run_bounded_acquisition).count("while ") == 0


def test_retained_trailing20_inventory_residual_zero_against_real_artifacts():
    inputs = rec.load_retained_inputs()
    inv = rec.inventory_trailing20(
        tickers=inputs["tickers"],
        exchanges=inputs["exchanges"],
        window=inputs["window"],
        qualified_rows=inputs["qualified_rows"],
        recon_rows=inputs["recon_rows"],
    )
    assert inv["residual"] == 0
    assert inv["expected_ticker_session_pairs"] == 1507 * 20
    assert inv["session_wide_fhsc_holes"] == ["2026-08-06"]
    assert inputs["window"][0] == "2026-07-15"
    assert inputs["window"][-1] == "2026-08-11"
    plan = rec.acquisition_plan(inv, budget=6)
    assert [item["ticker"] for item in plan["selected"]] == ["AAA", "BID", "BWE", "CTG", "DPM", "MZG"]
    before = rec.recompute_adtv20(
        rec.evaluation_rows_from_qualified(inputs["qualified_rows"], inputs["exchanges"]),
        tickers=inputs["tickers"], exchanges=inputs["exchanges"], window=inputs["window"],
    )
    assert before["ready_count"] == 0
    assert before["partial_count"] == 213
    assert before["blocked_count"] == 190
    assert before["not_applicable_count"] == 1104
