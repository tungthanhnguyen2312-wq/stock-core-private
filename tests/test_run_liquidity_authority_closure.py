from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import liquidity_authority_contract as contract
import official_exchange_trading_statistics as official
from tools import run_liquidity_authority_closure as runner

SESSIONS = ["2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28", "2026-09-03", "2026-09-04", "2026-09-07", "2026-09-08",
            "2026-09-09", "2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18",
            "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-28"]


def _epoch(session: str) -> int:
    return int(datetime.combine(date.fromisoformat(session), datetime.min.time(), tzinfo=timezone.utc).timestamp())


def _hose_page(symbol: str) -> bytes:
    rows = []
    for session in reversed(SESSIONS[-20:]):
        main, main_value = (24184800, 492561095000) if session == "2026-09-28" else (1000, 20000000)
        odd_pair = (61005, 1249420300) if session == "2026-09-28" else (5, 100000)
        rows.append({"symbol": f"{symbol}     ", "reportDate": _epoch(session), "month": int(session[5:7]), "year": 2026,
                     "mainVolume": main, "mainValue": main_value, "oddlotvolume": odd_pair[0], "oddlotvalue": odd_pair[1],
                     "bigLotVolume": 0, "bigLotValue": 0, "bigLotVolume_OL": 0, "bigLotValue_OL": 0,
                     "totalShare": main + odd_pair[0], "totalValue": main_value + odd_pair[1]})
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


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _fixture(tmp_path: Path) -> argparse.Namespace:
    out = tmp_path / "out"
    raw = out / "probe" / "raw"
    raw.mkdir(parents=True)
    requests = [official.hose_request("HPG"), official.hnx_request("SHS", exchange=official.HNX, rows=60)]
    ledger = []
    for index, (request, body) in enumerate(zip(requests, (_hose_page("HPG"), _hnx_page()))):
        digest = hashlib.sha256(body).hexdigest()
        (raw / f"{digest}.bin").write_bytes(body)
        ledger.append({"index": index, "request": request, "retrieved_at": "2026-09-28T15:10:00+00:00", "http_status": 200,
                       "content_type": "x", "bytes": len(body), "sha256": digest, "outcome": "OK"})
    (out / "probe" / "request_ledger.jsonl").write_text("".join(json.dumps(e) + "\n" for e in ledger), encoding="utf-8")
    _write(out / "probe" / "cohort_plan.json", {"artifact_identity": "liquidity_authority_closure_probe_plan:test"})
    tick = lambda sym, board, market, qty, gross, time="2026-09-28 14:45:00.000": {  # noqa: E731
        "symbol": sym, "boardId": board, "marketId": market, "time": time, "totalVolumeTraded": qty, "grossTradeAmount": gross}
    batch = {"session": "2026-09-28", "trades": {
        "HPG": {"ok": True, "body": {"trades": [tick("HPG", "G1", "STO", 2418480, 492.561095), tick("HPG", "G4", "STO", 61005, 1.2494203)]}},
        "SHS": {"ok": True, "body": {"trades": [tick("SHS", "G1", "STX", 1369520, 181.91409), tick("SHS", "G3", "STX", 1500, 0.198),
                                                tick("SHS", "G4", "STX", 6082, 0.0814103)]}}},
        "ohlc": {"HPG": {"ok": True, "body": {"v": [24184800]}}, "SHS": {"ok": True, "body": {"v": [13695200]}}}}
    _write(tmp_path / "batches" / "batch-000.json", batch)
    artifact = _write(tmp_path / "dnse.json", {"artifact_identity": "market_wide_current_liquidity_research:test", "authority_boundary": {},
                                               "coverage": {"disposition_counts": {}}, "universe": {"canonical_candidate_count": 1683}})
    tail = _write(tmp_path / "tail.json", {"rows": [{"ticker": "HPG", "session": "2026-09-04", "status": "CONFLICT", "conflict_cause": "UNEXPLAINED_RESIDUAL",
                                                      "g1_share_quantity": 900, "matched_value_vnd": 18000000, "fhsc_matched_volume": 1000,
                                                      "fhsc_matched_value": 20000000}]})
    prior = _write(tmp_path / "prior.json", {"run_1": {"exact": 0, "coverage_restricted": 42, "semantics_unqualified": 1641, "insufficient_window": 0}})
    _write(tmp_path / "fhsc" / "AAA.json", {"data": {"data": [{"date": "2026-08-05"}]}})
    return argparse.Namespace(output_dir=out, dnse_batches=tmp_path / "batches", dnse_artifact=artifact, tail_reconciliation=tail,
                              prior_adtv20=prior, fhsc_raw_dir=tmp_path / "fhsc", fhsc_canary=tmp_path / "missing.json")


def test_offline_build_is_deterministic_scoped_and_never_opens_sizing(tmp_path):
    args = _fixture(tmp_path)
    first, second = runner.build_artifact(args), runner.build_artifact(args)
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["terminal_disposition"] == "LIQUIDITY_AUTHORITY_PARTIALLY_PROMOTABLE"
    assert first["governed_calendar_extension"]["state"] == "EXTENDED"
    assert first["cohort_records"]["HPG"]["current_session_reconciliation"]["verdict"] == contract.EXACT
    assert first["cohort_records"]["SHS"]["current_session_reconciliation"]["components"]["MATCHED_ALL"]["nonzero_dnse_boards"] == ["G1", "G3", "G4"]
    assert first["adtv20_eligible_tickers"] == ["HPG", "SHS"]
    # One ticker per exchange is below the unit-qualification threshold: evidence, not authority.
    assert first["qualified_board_units"]["HOSE"]["volume_and_value"] == []
    assert first["tail_conflict_adjudication"]["counts"] == {"HOSE:CONFLICT:OFFICIAL_EQUALS_FHSC_ONLY_DNSE_G1_UNDERCOUNT": 1}
    boundary = first["authority_boundary"]
    assert boundary["POSITION_SIZING_IS_SAFE"] is False and boundary["execution_input_eligible"] is False
    assert boundary["market_wide_promotion"] is False and boundary["vnstock_kbs_vci_used"] is False
    for record in first["cohort_records"].values():
        for dimension in (contract.POSITION_SIZING, contract.EXECUTION_CAPACITY, contract.PIT_BACKTEST):
            assert record["fitness"][dimension]["state"] == contract.BLOCKED
    assert first["prior_ceiling_reproduced"]["prior_adtv20_target_2026_09_04"]["exact"] == 0


def test_build_refuses_tampered_raw_bytes(tmp_path):
    args = _fixture(tmp_path)
    raw = next((args.output_dir / "probe" / "raw").iterdir())
    raw.write_bytes(raw.read_bytes() + b" ")
    try:
        runner.build_artifact(args)
    except SystemExit as exc:
        assert "hash mismatch" in str(exc)
    else:
        raise AssertionError("tampered raw bytes were accepted")


def test_plan_is_deterministic_and_within_budget():
    tick = lambda sym, board, market, gross, time="2026-09-28 14:45:00.000": {  # noqa: E731
        "symbol": sym, "boardId": board, "marketId": market, "time": time, "totalVolumeTraded": 10, "grossTradeAmount": gross}
    trades = {sym: {"ok": True, "body": {"trades": [tick(sym, "G1", market, gross)]}}
              for sym, market, gross in (("AAA", "STO", 5), ("BBB", "STO", 9), ("CCC", "STX", 1), ("DDD", "UPX", 2))}
    trades["EEE"] = {"ok": True, "body": {"trades": [tick("EEE", "G3", "STX", 1)]}}
    first = runner.plan_cohort(trades=trades, tail_rows=[], watchlist=["AAA"])
    assert first == runner.plan_cohort(trades=trades, tail_rows=[], watchlist=["AAA"])
    reasons = {item["ticker"]: item["selection_reasons"] for item in first["cohort"]}
    assert "OWNER_WATCHLIST" in reasons["AAA"] and "G3_POST_CLOSE_ACTIVE_TODAY" in reasons["EEE"]
    hose_pages = [r["page"] for r in first["requests"] if r["symbol"] == "AAA"]
    assert hose_pages == [1, 2, 3]
    assert first["request_count"] <= runner.REQUEST_BUDGET
