"""Bounded, secret-blind live probe + deterministic artifact builder for
``DNSE_TRADES_AND_LIQUIDITY_BASIS_QUALIFICATION_V1``.

Two legs, both fixed and auditable by reading ``build_call_plan()`` -- never an open-ended sweep:

  CURRENT-SESSION leg (5 tickers, one ``trades_latest`` call each -- no pagination; the endpoint
  already returns each board's own most-recent cumulative tick): HPG, VCB, SSI, FPT (the
  milestone's suggested corpus, four sectors) plus QNS (a lower-activity contrast ticker already
  used by this repository's other DNSE probes). One bounded ``ohlc`` call per ticker (resolution
  ``1D``, a fixed 12-day window) supplies the daily ``v`` cross-check target.

  HISTORICAL leg (3 tickers x 1 already-FHSC-cross-checked session, bounded ``trades_history``
  pagination capped at 4 pages -- the exact page count that fully exhausted a low-activity name in
  this milestone's own preliminary bounded probe): HPG, VCB, SSI at 2026-08-14, the most recent
  date shared with the already-retained ``dnse-fhsc-volume-basis-qualification-v1-20260821``
  evidence, so this leg's findings can be read alongside (not recomputed against) that retained
  FHSC matched/put-through decomposition without any new FHSC call.

Total live calls: 1 auth check + 5 trades_latest + 5 ohlc + up to 12 trades_history = up to 23.

Never reads secrets.env directly (dnse_secrets_env owns that); never prints, logs, or retains a
credential value; clears any credential it injected into os.environ before exiting.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

import dnse_secrets_env  # noqa: E402
import dnse_trades_liquidity_basis as basis  # noqa: E402
import vn_time  # noqa: E402
from dnse_access import BASE_URL, CREDENTIAL_ENV_PAIRS, auth_headers, credentials_for_request  # noqa: E402
from dnse_market_data import resolve_endpoint  # noqa: E402

CREDENTIAL_INJECTION_REQUIRED = "DNSE_CREDENTIAL_INJECTION_REQUIRED"

CURRENT_SESSION_TICKERS: tuple[str, ...] = ("HPG", "VCB", "SSI", "FPT", "QNS")
HISTORICAL_TICKERS: tuple[str, ...] = ("HPG", "VCB", "SSI")
HISTORICAL_SESSION_DATE = "2026-08-14"
PAGE_CAP = 4
OHLC_WINDOW_FROM = "2026-08-10"
OHLC_WINDOW_TO = "2026-08-21"

OUT_DIR = ROOT / "operations-review" / "dnse-trades-liquidity-basis-v1-20260823"
RAW_DIR = OUT_DIR / "raw"

# Read-only citation of already-retained FHSC evidence for the same historical session -- no new
# FHSC call is made anywhere in this tool (FHSC credentials remain CREDENTIAL_BLOCKED per
# docs/STATE.md; this milestone does not attempt to lift that).
RETAINED_FHSC_ARTIFACT = (
    ROOT / "operations-review" / "dnse-fhsc-volume-basis-qualification-v1-20260821"
    / "dnse_fhsc_volume_basis_qualification_artifact.json"
)


def _epoch(dt: datetime) -> int:
    return int(dt.timestamp())


def _day_window_epoch(date_str: str) -> tuple[int, int]:
    start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=vn_time.VN_TZ)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return _epoch(start), _epoch(end)


def build_call_plan() -> dict[str, Any]:
    """A fixed, explicit, bounded call plan -- auditable by reading this function; nothing here
    expands based on a prior response."""
    from_ohlc, to_ohlc = _day_window_epoch(OHLC_WINDOW_FROM)[0], _day_window_epoch(OHLC_WINDOW_TO)[1]
    hist_from, hist_to = _day_window_epoch(HISTORICAL_SESSION_DATE)
    return {
        "auth_check": {"capability": "working_dates", "symbol": None, "query": {}},
        "current_session_leg": [
            {"capability": "trades_latest", "symbol": symbol, "query": {}} for symbol in CURRENT_SESSION_TICKERS
        ],
        "ohlc_leg": [
            {"capability": "ohlc", "symbol": None,
             "query": {"type": "STOCK", "symbol": symbol, "resolution": "1D", "from": from_ohlc, "to": to_ohlc}}
            for symbol in CURRENT_SESSION_TICKERS
        ],
        "historical_leg": [
            {"capability": "trades_history", "symbol": symbol,
             "query": {"limit": 100, "order": "DESC", "from": hist_from, "to": hist_to},
             "session_date": HISTORICAL_SESSION_DATE, "page_cap": PAGE_CAP}
            for symbol in HISTORICAL_TICKERS
        ],
    }


def _fetch(capability: str, symbol: str | None, query: dict[str, Any], *, api_key: str, api_secret: str) -> dict[str, Any]:
    """One signed, read-only GET call. Reuses ``dnse_market_data.resolve_endpoint`` and
    ``dnse_access.auth_headers`` for endpoint/signing; unlike ``dnse_market_data.request_capability``
    this returns the full parsed body (never truncated to a 20-item preview) because this tool
    ingests real trade records rather than only previewing them for qualification -- the bodies
    themselves carry no credential material, so full retention is the correct, doctrine-required
    raw-preservation behavior, not a safety regression."""
    path = resolve_endpoint(capability, symbol)
    headers = auth_headers(api_key, api_secret, "GET", path)
    started = vn_time.vn_now()
    try:
        response = requests.get(f"{BASE_URL}{path}", params=query, headers=headers, timeout=(5.0, 15.0))
    except Exception as exc:  # noqa: BLE001 - record, never raise
        return {"ok": False, "error_code": f"request_failed_{type(exc).__name__}", "capability": capability,
                "symbol": symbol, "query_sent": dict(query)}
    elapsed_ms = round((vn_time.vn_now() - started).total_seconds() * 1000, 1)
    result: dict[str, Any] = {
        "capability": capability, "symbol": symbol, "endpoint": path, "query_sent": dict(query),
        "http_status": response.status_code, "elapsed_ms": elapsed_ms,
    }
    if response.status_code != 200:
        result.update(ok=False, error_code=f"http_status_{response.status_code}")
        return result
    try:
        body = response.json()
    except ValueError:
        result.update(ok=False, error_code="response_not_json")
        return result
    result.update(ok=True, body=body, raw_bytes=response.content)
    return result


def _relative_or_absolute(path: Path) -> str:
    """``path`` relative to the repo root when possible, else its absolute form -- a custom
    ``--out-dir`` (or a test double) need not live under ``ROOT``."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _retain_raw(symbol: str, label: str, raw_bytes: bytes) -> str:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
    path = RAW_DIR / f"{symbol}_{label}_{digest}.json"
    path.write_bytes(raw_bytes)
    return _relative_or_absolute(path)


def _extract_ohlc_v_by_date(body: dict[str, Any]) -> dict[str, float]:
    times, volumes = body.get("t", []), body.get("v", [])
    out: dict[str, float] = {}
    for epoch, v in zip(times, volumes):
        if v is None:
            continue
        date_str = datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(vn_time.VN_TZ).date().isoformat()
        out[date_str] = v
    return out


def _retained_fhsc_context(session_date: str, tickers: tuple[str, ...]) -> dict[str, Any]:
    if not RETAINED_FHSC_ARTIFACT.exists():
        return {"available": False, "reason": "retained_fhsc_artifact_not_found", "path": str(RETAINED_FHSC_ARTIFACT)}
    artifact = json.loads(RETAINED_FHSC_ARTIFACT.read_text(encoding="utf-8"))
    matrix = artifact.get("reconciliation", {}).get("matrix", [])
    rows = [row for row in matrix if row.get("session") == session_date and row.get("ticker") in tickers]
    return {
        "available": True, "source_artifact": _relative_or_absolute(RETAINED_FHSC_ARTIFACT),
        "source_artifact_identity": artifact.get("artifact_identity"), "session_date": session_date,
        "rows": rows, "note": "read-only citation; no new FHSC call made (FHSC remains CREDENTIAL_BLOCKED)",
    }


def run_live() -> dict[str, Any]:
    try:
        load_status = dnse_secrets_env.ensure_credentials_loaded()
        creds = credentials_for_request()
        if creds is None:
            return {"status": CREDENTIAL_INJECTION_REQUIRED, "credential_load_status": load_status}
        api_key, api_secret = creds

        plan = build_call_plan()
        generated_at = vn_time.vn_now_iso()

        auth = _fetch(plan["auth_check"]["capability"], plan["auth_check"]["symbol"], plan["auth_check"]["query"],
                      api_key=api_key, api_secret=api_secret)
        if not auth.get("ok"):
            return {"status": "DNSE_AUTHENTICATION_FAIL", "generated_at": generated_at, "auth_check": {
                k: v for k, v in auth.items() if k not in ("body", "raw_bytes")}}

        current_session: dict[str, Any] = {}
        ohlc_by_ticker: dict[str, dict[str, float]] = {}
        historical: dict[str, Any] = {}
        retained_files: list[str] = []

        for entry in plan["current_session_leg"]:
            symbol = entry["symbol"]
            r = _fetch(entry["capability"], symbol, entry["query"], api_key=api_key, api_secret=api_secret)
            if not r.get("ok"):
                current_session[symbol] = {"ok": False, "error_code": r.get("error_code")}
                continue
            retained_files.append(_retain_raw(symbol, "trades_latest", r["raw_bytes"]))
            parsed = basis.parse_trades_response(r["body"], symbol=symbol, endpoint="trades_latest")
            snapshot = basis.board_latest_snapshot(parsed["records"])
            current_session[symbol] = {"ok": True, "parsed": parsed, "snapshot": snapshot}

        for entry in plan["ohlc_leg"]:
            symbol = entry["query"]["symbol"]
            r = _fetch(entry["capability"], entry["symbol"], entry["query"], api_key=api_key, api_secret=api_secret)
            if not r.get("ok"):
                ohlc_by_ticker[symbol] = {}
                continue
            retained_files.append(_retain_raw(symbol, "ohlc", r["raw_bytes"]))
            ohlc_by_ticker[symbol] = _extract_ohlc_v_by_date(r["body"])

        for entry in plan["historical_leg"]:
            symbol = entry["symbol"]
            session_date = entry["session_date"]
            page_cap = entry["page_cap"]
            all_records: list[dict[str, Any]] = []
            boards_seen: set[str] = set()
            token: str | None = None
            pages_fetched = 0
            exhausted = False
            for page in range(1, page_cap + 1):
                query = dict(entry["query"])
                if token:
                    query["nextPageToken"] = token
                r = _fetch("trades_history", symbol, query, api_key=api_key, api_secret=api_secret)
                pages_fetched = page
                if not r.get("ok"):
                    break
                retained_files.append(_retain_raw(symbol, f"trades_history_p{page}", r["raw_bytes"]))
                parsed = basis.parse_trades_response(r["body"], symbol=symbol, endpoint="trades_history")
                all_records.extend(parsed["records"])
                boards_seen |= {rec["board_id"] for rec in parsed["records"] if rec.get("parse_status") == "PARSED"}
                token = r["body"].get("nextPageToken")
                if not token:
                    exhausted = True
                    break
            snapshot = basis.board_latest_snapshot(all_records, target_session_date=session_date)
            completeness = basis.scan_completeness(
                boards_seen=sorted(boards_seen), pages_fetched=pages_fetched, page_cap=page_cap, exhausted=exhausted)
            historical[symbol] = {"snapshot": snapshot, "completeness": completeness,
                                   "record_count": len(all_records)}

        fhsc_context = _retained_fhsc_context(HISTORICAL_SESSION_DATE, HISTORICAL_TICKERS)

        report = {
            "status": "DNSE_AUTHENTICATION_PASS",
            "generated_at": generated_at,
            "current_session": current_session,
            "ohlc_by_ticker": ohlc_by_ticker,
            "historical": historical,
            "retained_fhsc_context": fhsc_context,
            "retained_raw_files": sorted(retained_files),
        }
        return report
    finally:
        for key1, key2 in CREDENTIAL_ENV_PAIRS:
            os.environ.pop(key1, None)
            os.environ.pop(key2, None)


def build_final_artifact(report: dict[str, Any]) -> dict[str, Any]:
    """Assemble the deterministic capability artifact from one completed live-probe report."""
    per_ticker: dict[str, Any] = {}
    for symbol in CURRENT_SESSION_TICKERS:
        cs = report["current_session"].get(symbol, {})
        if not cs.get("ok"):
            per_ticker[symbol] = {"current_session_available": False}
            continue
        snapshot = cs["snapshot"]
        target_date = snapshot["target_session_date"]
        ohlc_v = report["ohlc_by_ticker"].get(symbol, {}).get(target_date)
        categories = basis.board_category_totals(snapshot)
        cross_check = basis.g1_scale_cross_check(snapshot, ohlc_v=ohlc_v)
        g1_record = snapshot["boards"].get("G1", {})
        gross_check = (
            basis.gross_trade_amount_uniform_formula_check(g1_record)
            if g1_record.get("parse_status") == "PARSED" else {"verdict": "UNAVAILABLE"}
        )
        value_candidates = {
            board_id: basis.traded_value_candidate(entry)
            for board_id, entry in snapshot["boards"].items() if entry.get("parse_status") == "PARSED"
        }
        contract = basis.session_liquidity_research_contract(
            current_session_boards_active=any(
                b.get("activity_state") == basis.OBSERVED_ACTIVE_THIS_SESSION for b in snapshot["boards"].values()
            ),
            historical_scan_state=report["historical"].get(symbol, {}).get("completeness", {}).get("state"),
        )
        basis.assert_fail_closed(contract)
        per_ticker[symbol] = {
            "current_session_available": True,
            "target_session_date": target_date,
            "ohlc_v": ohlc_v,
            "board_snapshot": snapshot,
            "board_category_totals": categories,
            "g1_x10_cross_check": cross_check,
            "gross_trade_amount_uniform_formula_check": gross_check,
            "traded_value_candidates": value_candidates,
            "liquidity_research_contract": contract,
        }
        if symbol in report["historical"]:
            per_ticker[symbol]["historical_scan"] = report["historical"][symbol]

    artifact: dict[str, Any] = {
        "contract_version": basis.CONTRACT_VERSION,
        "schema_version": basis.SCHEMA_VERSION,
        "milestone": basis.MILESTONE,
        "generated_at": report.get("generated_at"),
        "corpus": list(CURRENT_SESSION_TICKERS),
        "historical_session_date": HISTORICAL_SESSION_DATE,
        "historical_tickers": list(HISTORICAL_TICKERS),
        "page_cap": PAGE_CAP,
        "per_ticker": per_ticker,
        "retained_fhsc_context": report.get("retained_fhsc_context"),
        "retained_raw_files": report.get("retained_raw_files"),
        "lineage_status": basis.LIVE_ADAPTER_LINEAGE_STATUS,
        "global_invariants": {
            "qualified_liquidity_inputs": False,
            "position_sizing_is_safe": False,
            "raw_as_traded": "NOT_PROMOTED",
        },
        "authority_effect": "NONE",
    }
    artifact.update(basis.content_identity(artifact))
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Actually call the network.")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR

    if not args.live:
        print(json.dumps({"dry_run": True, "call_plan": build_call_plan()}, indent=2, sort_keys=True, default=str))
        return 0

    report = run_live()
    if report.get("status") == CREDENTIAL_INJECTION_REQUIRED:
        print(CREDENTIAL_INJECTION_REQUIRED)
        return 2
    if report.get("status") == "DNSE_AUTHENTICATION_FAIL":
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 3

    artifact = build_final_artifact(report)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dnse_trades_liquidity_basis_artifact.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps({"status": "OK", "artifact_identity": artifact["artifact_identity"],
                       "out_dir": str(out_dir)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
