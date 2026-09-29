from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import current_research_decision_input as decision_input
import integrated_investment_decision_product as iidp
import liquidity_authority_contract as contract
import official_exchange_trading_statistics as official
import official_liquidity_market_wide as wide
from tools import run_liquidity_authority_closure as closure
from tools import run_liquidity_market_wide_operationalization as runner

SESSIONS = ["2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28", "2026-09-03", "2026-09-04", "2026-09-07", "2026-09-08",
            "2026-09-09", "2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18",
            "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-28"]


def _epoch(session: str) -> int:
    return int(datetime.combine(date.fromisoformat(session), datetime.min.time(), tzinfo=timezone.utc).timestamp())


def _hose_page(symbol: str) -> bytes:
    rows = []
    for session in reversed(SESSIONS[-20:]):
        main, main_value = (24184800, 492561095000) if session == "2026-09-28" else (1000, 20000000)
        odd = (61005, 1249420300) if session == "2026-09-28" else (5, 100000)
        rows.append({"symbol": f"{symbol}     ", "reportDate": _epoch(session), "month": int(session[5:7]), "year": 2026,
                     "mainVolume": main, "mainValue": main_value, "oddlotvolume": odd[0], "oddlotvalue": odd[1],
                     "bigLotVolume": 0, "bigLotValue": 0, "bigLotVolume_OL": 0, "bigLotValue_OL": 0,
                     "totalShare": main + odd[0], "totalValue": main_value + odd[1]})
    return json.dumps({"data": {"list": rows, "paging": {"pageIndex": 1, "pageSize": 20, "totalCount": 500, "totalPages": 25}},
                       "success": True, "message": None}).encode("utf-8")


def _hnx_page() -> bytes:
    header = ("<table><tr><th>STT</th><th>Ngày</th><th>KLGD (Cổ phiếu)</th><th>GTGD (Nghìn đồng)</th></tr>"
              "<tr><th>Khớp lệnh</th><th>Thỏa thuận</th><th>Tổng</th><th>Khớp lệnh</th><th>Thỏa thuận</th><th>Tổng</th></tr>")
    body = []
    for index, session in enumerate(reversed(SESSIONS), start=1):
        volume, value = ("13.716.282", "182.193.500,3") if session == "2026-09-28" else ("100", "1.500")
        dd = f"{session[8:10]}/{session[5:7]}/{session[:4]}"
        cells = [str(index), dd, volume, "0", volume, value, "0", value, "1", "1", "0", "0", "0", "0", "0"]
        body.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    return (header + "".join(body) + "</table>").encode("utf-8")


def _write_json(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _ledger_entry(index, request, body, outcome="OK"):
    digest = hashlib.sha256(body).hexdigest()
    return digest, {"index": index, "request": request, "retrieved_at": "2026-09-28T15:10:00+00:00", "http_status": 200, "content_type": "x",
                    "bytes": len(body), "sha256": digest, "outcome": outcome}


# ---- probe ----------------------------------------------------------------------

@pytest.fixture()
def probe_env(tmp_path, monkeypatch):
    prior = tmp_path / "prior"
    (prior / "probe" / "raw").mkdir(parents=True)
    request = official.hose_request("HPG")
    digest, entry = _ledger_entry(0, request, _hose_page("HPG"))
    (prior / "probe" / "raw" / f"{digest}.bin").write_bytes(_hose_page("HPG"))
    (prior / "probe" / "request_ledger.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr(runner.time, "sleep", lambda _s: None)
    calls: list[str] = []

    def install(script):
        def fake(request):
            calls.append(request["symbol"])
            return script[request["symbol"]].pop(0)
        monkeypatch.setattr(closure, "_execute", fake)

    def plan(symbols):
        requests = [official.hose_request(s) for s in symbols]
        _write_json(out / "probe" / "acquisition_plan.json", {"artifact_identity": "plan:test", "planned_requests": len(requests),
                                                              "retry_allowance": len(requests) // 10, "requests": requests})
    args = argparse.Namespace(output_dir=out, prior_closure_dir=prior)
    return args, install, plan, calls, out


OK = (200, "application/json", _hose_page("AAA"), None)


def test_probe_retries_transient_once_never_retries_permanent_and_reuses_prior_bytes(probe_env):
    args, install, plan, calls, out = probe_env
    plan(["AAA", "BBB", "CCC"])
    install({"AAA": [(503, "x", b"busy", "HTTP_503"), OK], "BBB": [(404, "x", b"", "HTTP_404")], "CCC": [OK]})
    summary = runner.probe_command(args)
    assert calls == ["AAA", "AAA", "BBB", "CCC"] and summary["http_requests_made"] == 4 and summary["retries_used"] == 1
    assert summary["final_outcomes"] == {"HTTP_404": 1, "OK": 2} and summary["carried_prior_entries"] == 1
    ledger = [json.loads(line) for line in (out / "probe" / "request_ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(ledger) == 4 and not (out / "probe" / "request_ledger.partial.jsonl").exists()
    assert sum(1 for e in ledger if e["plan_index"] < 0) == 1
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        runner.probe_command(args)
    series, _ = closure._official_series(out)
    assert series["AAA"]["rows"] and not series["AAA"]["parse_failures"]  # a recovered retry is not a failure
    assert series["BBB"]["parse_failures"] == [{"index": series["BBB"]["parse_failures"][0]["index"], "outcome": "HTTP_404"}]
    assert series["HPG"]["rows"]  # the prior bounded probe's retained bytes were carried, hash-verified


def test_probe_breaker_stops_after_consecutive_failures_and_is_recorded(probe_env):
    args, install, plan, calls, out = probe_env
    names = ["A1", "A2", "A3", "A4", "A5"]
    plan(names)
    install({n: [(404, "x", b"", "HTTP_404")] for n in names})
    summary = runner.probe_command(args)
    assert calls == ["A1", "A2", "A3"]
    assert summary["final_outcomes"] == {"HTTP_404": 3, "NOT_ATTEMPTED_BREAKER_OPEN": 2}


def test_probe_resumes_from_partial_ledger_without_repeating_requests(probe_env):
    args, install, plan, calls, out = probe_env
    plan(["AAA", "BBB"])
    partial = out / "probe" / "request_ledger.partial.jsonl"
    request = official.hose_request("AAA")
    digest, entry = _ledger_entry(0, request, _hose_page("AAA"))
    (out / "probe" / "raw").mkdir(parents=True, exist_ok=True)
    (out / "probe" / "raw" / f"{digest}.bin").write_bytes(_hose_page("AAA"))
    partial.write_text(json.dumps({**entry, "plan_index": 0, "attempts": []}) + "\n", encoding="utf-8")
    install({"BBB": [OK]})
    summary = runner.probe_command(args)
    assert calls == ["BBB"] and summary["final_outcomes"] == {"OK": 2}


def test_probe_refuses_a_plan_beyond_the_hard_budget(probe_env):
    args, install, plan, calls, out = probe_env
    _write_json(out / "probe" / "acquisition_plan.json", {"artifact_identity": "plan:test", "planned_requests": runner.HARD_REQUEST_BUDGET, "retry_allowance": 5, "requests": []})
    with pytest.raises(SystemExit, match="hard request budget"):
        runner.probe_command(args)
    assert calls == []


# ---- offline build --------------------------------------------------------------

def _build_fixture(tmp_path: Path):
    retained = tmp_path / "retained"
    tick = lambda sym, board, market, qty, gross: {"symbol": sym, "boardId": board, "marketId": market, "time": "2026-09-28 14:45:00.000",  # noqa: E731
                                                  "totalVolumeTraded": qty, "grossTradeAmount": gross}
    _write_json(retained / "current-official-market-universe-refresh-v1-20260913" / "current_official_market_universe_artifact.json", {
        "artifact_identity": "current_official_market_universe:test",
        "records": {
            "HPG": {"stocklookup_candidate": True, "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY", "exchange_or_market": "HOSE"},
            "SHS": {"stocklookup_candidate": True, "current_universe_status": "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE", "exchange_or_market": "HNX_LISTED"},
            "ABC": {"stocklookup_candidate": True, "current_universe_status": "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE", "exchange_or_market": "HNX_LISTED"},
            "OLD": {"stocklookup_candidate": True, "current_universe_status": "STOCKLOOKUP_ONLY_UNRESOLVED", "exchange_or_market": "DELISTED"}}})
    _write_json(retained / "market-wide-current-liquidity-research-v1-20260928" / "batches" / "batch-000.json", {
        "session": "2026-09-28",
        "trades": {"HPG": {"ok": True, "body": {"trades": [tick("HPG", "G1", "STO", 2418480, 492.561095), tick("HPG", "G4", "STO", 61005, 1.2494203)]}},
                   "SHS": {"ok": True, "body": {"trades": [tick("SHS", "G1", "STX", 1369520, 181.91409), tick("SHS", "G3", "STX", 1500, 0.198),
                                                           tick("SHS", "G4", "STX", 6082, 0.0814103)]}},
                   "ABC": {"ok": True, "body": {"trades": [tick("ABC", "G1", "STX", 10, 0.01)]}},
                   "OLD": {"ok": True, "body": {"trades": []}}},
        "ohlc": {"HPG": {"ok": True, "body": {"v": [24184800]}}}})
    out = tmp_path / "out"
    raw = out / "probe" / "raw"
    raw.mkdir(parents=True)
    requests = [official.hose_request("HPG"), official.hnx_request("SHS", exchange=official.HNX, rows=60)]
    ledger = []
    for index, (request, body) in enumerate(zip(requests, (_hose_page("HPG"), _hnx_page()))):
        digest, entry = _ledger_entry(index, request, body)
        (raw / f"{digest}.bin").write_bytes(body)
        ledger.append(entry)
    (out / "probe" / "request_ledger.jsonl").write_text("".join(json.dumps(e) + "\n" for e in ledger), encoding="utf-8")
    _write_json(out / "probe" / "acquisition_plan.json", {"artifact_identity": "plan:test"})
    _write_json(out / "probe" / "probe_summary.json", {"attempted": 2})
    return argparse.Namespace(output_dir=out, retained_root=retained, prior_closure_dir=tmp_path / "unused", verify_determinism=False)


def test_offline_build_classifies_every_governed_ticker_and_never_opens_sizing(tmp_path):
    args = _build_fixture(tmp_path)
    first, second = runner.build_artifact(args), runner.build_artifact(args)
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["resolved_completed_session"] == "2026-09-28" and set(first["records"]) == {"HPG", "SHS", "ABC", "OLD"}
    classes = {t: r["coverage"]["coverage_class"] for t, r in first["records"].items()}
    assert classes["HPG"] == wide.EXACT_20_SESSION_WINDOW and classes["SHS"] == wide.EXACT_20_SESSION_WINDOW
    assert classes["ABC"] == wide.PUBLIC_ACQUISITION_NOT_AUTHORIZED and classes["OLD"] == wide.SOURCE_NOT_SUPPORTED
    hpg = first["records"]["HPG"]
    assert hpg["current_session_reconciliation"]["verdict"] == contract.EXACT
    assert hpg["research_view"]["current_session"]["measurement_basis"] == contract.BASIS_OFFICIAL_RECONCILED
    assert hpg["research_view"]["current_value_to_adtv20"]["status"] == "VALID"
    assert first["records"]["ABC"]["research_view"]["current_session"]["matched_value_vnd"] is None
    assert first["denominators"]["governed_universe"] == 4
    assert first["coverage"]["adtv20_exact_total"] == 2
    boundary = first["authority_boundary"]
    assert (boundary["EXECUTION_CAPACITY"], boundary["POSITION_SIZING"], boundary["PIT_BACKTEST"]) == ("BLOCKED",) * 3
    assert boundary["raw_exchange_bodies_published"] is False and boundary["vnstock_kbs_vci_used"] is False
    for record in first["records"].values():
        for dim in (contract.EXECUTION_CAPACITY, contract.POSITION_SIZING, contract.PIT_BACKTEST):
            assert record["fitness"][dim]["state"] == contract.BLOCKED
    assert contract.content_identity(first, kind="official_exchange_liquidity_research")["artifact_identity"] == first["artifact_identity"]
    # The public-safe payload carries hashes and counts, never response bodies.
    serialized = json.dumps(first)
    assert "mainVolume" not in serialized and "raw_row" not in serialized and "raw_cells" not in serialized


def test_official_artifact_is_consumed_by_the_integrated_product_and_guarded(tmp_path):
    artifact = runner.build_artifact(_build_fixture(tmp_path))
    base = dict(session="2026-09-28", requested_at="2026-09-29T00:00:00Z",
                technical_structure_artifact={"artifact_identity": "ts", "records": {"HPG": {"ticker": "HPG"}, "ABC": {"ticker": "ABC"}}})
    built = iidp.build_artifact(**base, official_liquidity_artifact=artifact)
    liquidity = built["records"]["HPG"]["current_research_decision_input"]["dimensions"]["LIQUIDITY"]
    assert liquidity["qualified_research"]["window_coverage"] == wide.EXACT_20_SESSION_WINDOW
    assert liquidity["execution"]["state"] == decision_input.BLOCKED
    unauthorized = built["records"]["ABC"]["current_research_decision_input"]["dimensions"]["LIQUIDITY"]
    assert unauthorized["qualified_research"]["fitness"]["ADTV_RESEARCH"] == "BLOCKED"
    assert built["source_artifacts"]["official_exchange_liquidity_research"] == artifact["artifact_identity"]
    without = iidp.build_artifact(**base)
    assert without["records"]["HPG"]["decision_identity"] == built["records"]["HPG"]["decision_identity"]  # liquidity never enters the decision identity
    assert without["records"]["HPG"]["research_action_posture"] == built["records"]["HPG"]["research_action_posture"]
    with pytest.raises(iidp.IntegratedDecisionProductError, match="OFFICIAL_LIQUIDITY_RESEARCH_SESSION_MISMATCH"):
        iidp.build_artifact(**{**base, "session": "2026-09-25"}, official_liquidity_artifact=artifact)
    with pytest.raises(iidp.IntegratedDecisionProductError, match="OFFICIAL_LIQUIDITY_RESEARCH_CONTRACT_INVALID"):
        iidp.build_artifact(**base, official_liquidity_artifact={**artifact, "records": {}})
    opened = {**artifact, "authority_boundary": {**artifact["authority_boundary"], "POSITION_SIZING": "ELIGIBLE"}}
    opened.update(contract.content_identity(opened, kind="official_exchange_liquidity_research"))
    with pytest.raises(iidp.IntegratedDecisionProductError, match="AUTHORITY_BOUNDARY_VIOLATED"):
        iidp.build_artifact(**base, official_liquidity_artifact=opened)
