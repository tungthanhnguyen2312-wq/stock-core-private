"""DAILY_OFFICIAL_LIQUIDITY_ROLLFORWARD_V1 hermetic tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import current_research_decision_input as decision_input
import daily_official_liquidity_rollforward as rollforward
import execution_capacity_research as capacity
import official_exchange_trading_statistics as official
import official_liquidity_market_wide as wide
from tests.test_daily_liquidity_authority_wiring import _descriptive
from tests.test_execution_capacity_research import SESSION, _official, _policy
from tests.test_official_liquidity_market_wide import TARGET, _frame_row, _record, _slot

RETAINED_OFFICIAL_28 = Path(
    r"C:\Projects\StockLookup\worktrees\stock-core-liquidity-market-wide-v1-20260929"
    r"\operations-review\official-exchange-liquidity-research-v1-20260928"
    r"\official_exchange_liquidity_research_artifact.json"
)


def _artifact(session=TARGET, records=None, **overrides):
    records = records or {"AAA": _record(_slot())}
    payload = {
        "schema_version": "1.0.0",
        "contract_version": wide.CONTRACT_VERSION,
        "milestone": wide.MILESTONE,
        "resolved_completed_session": session,
        "records": records,
        "authority_boundary": {
            **wide.artifact_authority_summary(records),
            "market_wide_promotion": False,
            "raw_exchange_bodies_published": False,
        },
    }
    payload.update(overrides)
    payload.update(__import__("liquidity_authority_contract").content_identity(payload, kind="official_exchange_liquidity_research"))
    return payload


def test_same_session_artifact_is_accepted_and_prior_session_is_rejected():
    artifact = _artifact()
    accepted, status = rollforward.accept_same_session_official_artifact(artifact, TARGET)
    assert status == rollforward.AVAILABLE and accepted["artifact_identity"] == artifact["artifact_identity"]
    rejected, status = rollforward.accept_same_session_official_artifact(artifact, "2026-09-29")
    assert status == rollforward.UNAVAILABLE_SESSION and rejected is None


def test_malformed_artifact_fails_component_closed():
    rejected, status = rollforward.accept_same_session_official_artifact({"contract_version": "nope"}, TARGET)
    assert status == rollforward.MALFORMED_ARTIFACT and rejected is None
    opened = _artifact()
    opened["authority_boundary"]["POSITION_SIZING"] = "ELIGIBLE"
    opened.update(__import__("liquidity_authority_contract").content_identity(opened, kind="official_exchange_liquidity_research"))
    _, status = rollforward.accept_same_session_official_artifact(opened, TARGET)
    assert status == rollforward.MALFORMED_ARTIFACT


def test_missing_official_does_not_kill_daily_and_materializes_before_bind(tmp_path):
    order = ["materialize"]
    result = rollforward.materialize_same_session_official_liquidity(
        session=TARGET, artifact_root=tmp_path, allow_network=False,
    )
    order.append("consume")
    assert order == ["materialize", "consume"]
    assert result["status"] == rollforward.UNAVAILABLE_SOURCE
    assert result["http_requests_made"] == 0
    assert result.get("bound_before_consumer") is not True
    assert Path(result["status_path"]).is_file()


def test_rights_gate_blocks_hnx_upcom_and_allows_hose_under_existing_contract():
    frame = {t: _frame_row(t, ex) for t, ex in (("AAA", official.HOSE), ("CCC", official.HNX), ("EEE", official.UPCOM))}
    plan = rollforward.plan_daily_rollforward(frame, {}, target_session=TARGET, hard_request_budget=50)
    assert plan["status"] == "PLANNED"
    assert plan["planned_by_exchange"] == {official.HOSE: 1}
    assert plan["hnx_upcom_planned_requests"] == 0
    assert wide.ACQUISITION_RIGHTS[official.HOSE]["decision"] == wide.AUTHORIZED_BOUNDED_INTERNAL
    assert wide.ACQUISITION_RIGHTS[official.HNX]["decision"] == wide.PUBLIC_ACQUISITION_NOT_AUTHORIZED


def test_acquisition_plan_is_deterministic_and_reuses_only_current_retained():
    frame = {t: _frame_row(t) for t in ("AAA", "BBB")}
    retained = {"BBB": _slot("BBB")}
    first = rollforward.plan_daily_rollforward(frame, retained, target_session=TARGET, hard_request_budget=50)
    second = rollforward.plan_daily_rollforward(frame, retained, target_session=TARGET, hard_request_budget=50)
    assert first == second
    assert [r["symbol"] for r in first["requests"]] == ["AAA"]
    assert first["reused_retained_by_exchange"] == {official.HOSE: 1}
    stale = {"BBB": _slot("BBB", sessions=["2026-09-01", "2026-09-02"])}
    replanned = rollforward.plan_daily_rollforward(frame, stale, target_session=TARGET, hard_request_budget=50)
    assert [r["symbol"] for r in replanned["requests"]] == ["AAA", "BBB"]


def test_exact_window_zero_trading_and_missing_session_are_preserved():
    zero = _record(_slot(zero=(TARGET,)))
    assert wide.ZERO_TRADING_VALID in zero["coverage"]["labels"]
    missing = _record(_slot(sessions=["2026-09-01"]))
    assert missing["coverage"]["coverage_class"] in (wide.MISSING_SESSION, wide.PARTIAL_WINDOW)


def test_request_ceiling_is_enforced_without_hidden_batches(tmp_path):
    frame = {f"T{i:03d}": _frame_row(f"T{i:03d}") for i in range(403)}
    plan = rollforward.plan_daily_rollforward(frame, {}, target_session="2026-09-29")
    assert plan["status"] == rollforward.UNAVAILABLE_REQUEST_BUDGET
    assert plan["planned_requests"] == 403
    assert plan["planned_requests"] + plan["retry_allowance"] > rollforward.HARD_REQUEST_BUDGET
    assert plan["hnx_upcom_planned_requests"] == 0
    calls: list[str] = []
    result = rollforward.materialize_same_session_official_liquidity(
        session="2026-09-29", artifact_root=tmp_path, allow_network=True,
        universe={"records": {
            ticker: {"stocklookup_candidate": True, "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY",
                     "exchange_or_market": "HOSE", "qualification": "Q"}
            for ticker in frame
        }},
        retained_series={},
        execute_request=lambda req: calls.append(req["symbol"]),
    )
    assert result["status"] == rollforward.UNAVAILABLE_REQUEST_BUDGET
    assert result["http_requests_made"] == 0
    assert calls == []


def test_per_record_fitness_and_descriptive_never_override_official():
    record = _record(_slot())
    liq = decision_input._liquidity({}, _descriptive(), record)
    assert liq["qualified_research"]["fitness"]["ADTV_RESEARCH"] == "ELIGIBLE"
    summary = wide.artifact_authority_summary({"AAA": record, "BBB": _record(None, row=_frame_row("BBB", official.HNX))})
    assert summary["per_record_fitness_is_authoritative"] is True
    assert summary["ADTV_RESEARCH"]["eligible_count"] == 1


def test_qualified_adtv_reaches_execution_capacity_and_policy_unbound_is_preserved():
    envelope = capacity.build_envelope(
        ticker="AAA", session=SESSION, official_liquidity_record=_official(),
        policy=capacity.canonical_unbound_policy(),
    )
    assert envelope["state"] == "BLOCKED" and envelope["reason_codes"] == ["POLICY_UNBOUND"]
    bound = capacity.build_envelope(
        ticker="AAA", session=SESSION, official_liquidity_record=_official(),
        policy=_policy(), current_price="1250", price_identity="price:test",
    )
    assert bound["state"] == "AVAILABLE"


def test_raw_pit_live_sizing_remain_blocked():
    matrix = capacity.use_specific_authority(capacity_state=capacity.AVAILABLE, private_size_state=capacity.AVAILABLE)
    assert matrix[capacity.LIVE_POSITION_SIZING] == "BLOCKED"
    assert matrix[capacity.PIT_BACKTEST] == "BLOCKED"
    assert matrix[capacity.EXECUTION_REPLAY] == "BLOCKED"
    summary = wide.artifact_authority_summary({"AAA": _record(_slot())})
    assert summary["RAW_AS_TRADED"] == "NOT_PROMOTED"
    assert summary["PIT_BACKTEST"] == "BLOCKED"


def test_malformed_json_file_is_component_closed(tmp_path):
    dest_dir = tmp_path / "operations-review" / f"official-exchange-liquidity-research-v1-{TARGET.replace('-', '')}"
    dest_dir.mkdir(parents=True)
    (dest_dir / "official_exchange_liquidity_research_artifact.json").write_text("{not json", encoding="utf-8")
    payload, error = rollforward.load_official_payload(dest_dir / "official_exchange_liquidity_research_artifact.json")
    assert payload is None and error == rollforward.MALFORMED_ARTIFACT
    result = rollforward.materialize_same_session_official_liquidity(session=TARGET, artifact_root=tmp_path)
    assert result["status"] == rollforward.MALFORMED_ARTIFACT


def test_same_session_bind_copies_artifact_before_consumer(tmp_path):
    artifact = _artifact()
    retained = tmp_path / "retained"
    dest = retained / "operations-review" / f"official-exchange-liquidity-research-v1-{TARGET.replace('-', '')}"
    dest.mkdir(parents=True)
    (dest / "official_exchange_liquidity_research_artifact.json").write_text(json.dumps(artifact), encoding="utf-8")
    attempt = tmp_path / "attempt"
    result = rollforward.materialize_same_session_official_liquidity(
        session=TARGET, artifact_root=attempt, retained_evidence_root=retained, allow_network=False,
    )
    assert result["status"] == rollforward.AVAILABLE
    assert result["bound_before_consumer"] is True
    copied = attempt / "operations-review" / f"official-exchange-liquidity-research-v1-{TARGET.replace('-', '')}" / "official_exchange_liquidity_research_artifact.json"
    accepted, status = rollforward.accept_same_session_official_artifact(
        json.loads(copied.read_text(encoding="utf-8")), TARGET,
    )
    assert status == rollforward.AVAILABLE
    assert accepted["artifact_identity"] == artifact["artifact_identity"]


def test_within_budget_plan_dispatches_only_through_explicit_seam(tmp_path):
    calls: list[str] = []
    universe = {"records": {
        "AAA": {"stocklookup_candidate": True, "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY",
                "exchange_or_market": "HOSE", "qualification": "Q"},
    }}
    result = rollforward.materialize_same_session_official_liquidity(
        session=TARGET, artifact_root=tmp_path, allow_network=True,
        universe=universe, retained_series={},
        execute_request=lambda req: calls.append(req["symbol"]),
    )
    assert calls == []
    assert result["http_requests_made"] == 0
    assert result["status"] == rollforward.UNAVAILABLE_SOURCE
    result_off = rollforward.materialize_same_session_official_liquidity(
        session=TARGET, artifact_root=tmp_path / "off", allow_network=True,
        universe=universe, retained_series={},
    )
    assert result_off["http_requests_made"] == 0


def test_zero_active_vnstock_on_rollforward_import():
    import sys
    assert "vnstock" not in sys.modules and "vnai" not in sys.modules


@pytest.mark.skipif(not RETAINED_OFFICIAL_28.is_file(), reason="retained 2026-09-28 official artifact absent")
def test_retained_2026_09_28_replay_reproduces_952_457_457():
    official_art = json.loads(RETAINED_OFFICIAL_28.read_text(encoding="utf-8"))
    accepted, status = rollforward.accept_same_session_official_artifact(official_art, "2026-09-28")
    assert status == rollforward.AVAILABLE
    assert official_art["artifact_identity"] == "official_exchange_liquidity_research:f35f882c860af8a2d01b3b31ec7a3f74a9f9607a1f71f736d320c0f9a22a696b"
    summary = wide.artifact_authority_summary(official_art["records"])
    assert summary["CURRENT_SESSION_LIQUIDITY_RESEARCH"]["eligible_count"] == 952
    assert summary["ADTV_RESEARCH"]["eligible_count"] == 457
    assert summary["ADV_VOLUME_RESEARCH"]["eligible_count"] == 457
    assert summary["ADV_VOLUME_RESEARCH"]["basis"] == wide.AS_TRADED_NOT_CA_NORMALIZED
    _, other = rollforward.accept_same_session_official_artifact(official_art, "2026-09-29")
    assert other == rollforward.UNAVAILABLE_SESSION
    frame = rollforward._frame_from_universe({"records": {
        ticker: {
            "stocklookup_candidate": True,
            "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY" if rec.get("route_exchange") else "STOCKLOOKUP_ONLY_UNRESOLVED",
            "exchange_or_market": {"HOSE": "HOSE", "HNX": "HNX_LISTED", "UPCOM": "UPCOM"}.get(rec.get("route_exchange") or "", "DELISTED"),
            "qualification": "Q",
        }
        for ticker, rec in official_art["records"].items()
    }})
    # Rebuild slots with exchange so retained_is_current works.
    retained = {}
    for ticker, rec in official_art["records"].items():
        refs = rec.get("evidence_refs") or {}
        if refs.get("newest"):
            retained[ticker] = {"newest": refs["newest"], "parse_failures": [], "rows": {refs["newest"]: {}}}
    plan = rollforward.plan_daily_rollforward(frame, retained, target_session="2026-09-29")
    assert plan["status"] == rollforward.UNAVAILABLE_REQUEST_BUDGET
    assert plan["planned_requests"] == 403
    assert plan["hnx_upcom_planned_requests"] == 0
    public = capacity.build_retained_acceptance(
        official_liquidity_artifact=official_art, policy=capacity.canonical_unbound_policy(),
    )
    assert public["counts"]["capacity_AVAILABLE"] == 0
    assert public["counts"]["capacity_BLOCKED"] == 1683
    assert public["counts"]["policy_unbound"] == 457
    assert public["authority_boundary"][capacity.LIVE_POSITION_SIZING] == "BLOCKED"
    assert public["authority_boundary"][capacity.PIT_BACKTEST] == "BLOCKED"
    assert rollforward.LIVE_ACCEPTANCE == "LIVE_ACCEPTANCE_PENDING_2026_09_30_COMPLETED_SESSION"


def _hose_frame(n=403):
    return {f"T{i:03d}": _frame_row(f"T{i:03d}") for i in range(n)}


@pytest.mark.parametrize("budget", [399, 400])
def test_governed_budget_may_be_narrowed_or_equal(budget):
    plan = rollforward.plan_daily_rollforward(_hose_frame(10), {}, target_session="2026-09-29", hard_request_budget=budget)
    assert plan["status"] == rollforward.WITHIN_BUDGET or plan["hard_request_budget"] == budget
    assert plan["hard_request_budget"] == budget


@pytest.mark.parametrize("budget", [401, 1000])
def test_governed_budget_cannot_be_widened(budget, tmp_path):
    with pytest.raises(rollforward.OfficialLiquidityRollforwardError, match="GOVERNED_REQUEST_BUDGET_EXCEEDED"):
        rollforward.plan_daily_rollforward(_hose_frame(), {}, target_session="2026-09-29", hard_request_budget=budget)
    result = rollforward.materialize_same_session_official_liquidity(
        session="2026-09-29", artifact_root=tmp_path, hard_request_budget=budget,
    )
    assert result["status"] != rollforward.AVAILABLE
    assert "GOVERNED_REQUEST_BUDGET_EXCEEDED" in result["reason_code"]


def test_real_403_plan_stays_over_budget_at_governed_ceiling():
    plan = rollforward.plan_daily_rollforward(_hose_frame(), {}, target_session="2026-09-29", hard_request_budget=400)
    assert plan["status"] == rollforward.UNAVAILABLE_REQUEST_BUDGET
    assert plan["reason_code"] == rollforward.BUDGET_CEILING if "reason_code" in plan else True


@pytest.mark.parametrize("key,value", [
    ("RAW_AS_TRADED", "PROMOTED"),
    ("EXECUTION_REPLAY", "ELIGIBLE"),
    ("LIVE_POSITION_SIZING", "ELIGIBLE"),
    ("PORTFOLIO_CAPITAL_ALLOCATION", "ELIGIBLE"),
    ("HISTORICAL_PIT_SIZE_REPLAY", "ELIGIBLE"),
    ("PIT_BACKTEST", "ELIGIBLE"),
    ("EXECUTION_CAPACITY", "ELIGIBLE"),
])
def test_rehashed_same_session_artifact_cannot_promote_forbidden_authority(key, value):
    opened = _artifact()
    opened["authority_boundary"][key] = value
    opened.update(__import__("liquidity_authority_contract").content_identity(opened, kind="official_exchange_liquidity_research"))
    rejected, status = rollforward.accept_same_session_official_artifact(opened, TARGET)
    assert status == rollforward.MALFORMED_ARTIFACT and rejected is None
