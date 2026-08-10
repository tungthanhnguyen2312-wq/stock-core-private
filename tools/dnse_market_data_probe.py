"""Bounded, secret-blind DNSE OpenAPI market-data capability qualification probe.

Source-qualification tooling only -- see
`operations-review/dnse_market_data_source_qualification_*.md` for the
milestone this supports. This tool never reads `secrets.env`; it consumes
`DNSE_API_KEY`/`DNSE_API_SECRET` or `LIVESPEED_API_KEY`/`LIVESPEED_API_SECRET`
from the process environment only (see `dnse_access.py`), and every response
it writes or prints is redacted first (see `dnse_market_data.py`).

Two probe modes:
  --probe auth    Phase C: the single smallest authenticated read-only call
                   (`/market/working-dates`). Stops here regardless of result.
  --probe matrix  Phase D: the auth check, then -- only if it passes -- the
                   full bounded capability plan across HPG/VNM/QNS and
                   VNINDEX/VN30. A failed auth check stops the run before any
                   further authenticated call is attempted.

Without --live, prints the call plan and makes no network request at all.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dnse_access import credential_status, credentials_for_request  # noqa: E402
from dnse_market_data import request_capability, top_level_schema  # noqa: E402
import vn_time  # noqa: E402

CREDENTIAL_INJECTION_REQUIRED = "DNSE_CREDENTIAL_INJECTION_REQUIRED"

TICKERS: tuple[str, ...] = ("HPG", "VNM", "QNS")
INDEX_SYMBOLS: tuple[str, ...] = ("VNINDEX", "VN30")

# operations-review/ is the workspace-level governance/evidence authority (see
# AGENT_WORKING_CONTRACT.md's "sole canonical location" note) -- one directory
# above this Producer repo's own root, not the untracked same-named folder
# that has accumulated inside stock-core-private itself.
DEFAULT_OUT_DIR = ROOT.parent / "operations-review" / "dnse-market-data-qualification-20260810"

_AUTH_CHECK_CALL = {"capability": "working_dates", "symbol": None, "query": {}}


def _epoch(dt) -> int:
    return int(dt.timestamp())


def build_call_plan() -> list[dict[str, Any]]:
    """A fixed, explicit, bounded call plan -- not an open-ended sweep. Every
    entry is auditable by reading this function; nothing here expands based
    on a prior response."""
    now = vn_time.vn_now()
    to_short, from_short = _epoch(now), _epoch(now - timedelta(days=2))
    to_wide, from_wide = _epoch(now), _epoch(now - timedelta(days=10))
    # expected-price and foreign-trading rejected the 10-day window with
    # "range exceeds maximum time range" (observed 2026-08-10); both are
    # intraday-shaped concepts (indicative auction price; a trading day's
    # foreign flow), so a same-day window is the natural bounded retry.
    to_intraday, from_intraday = _epoch(now), _epoch(now - timedelta(days=1))

    plan: list[dict[str, Any]] = [dict(_AUTH_CHECK_CALL, family_note="calendar")]
    plan.append({"capability": "trading_session", "symbol": None, "query": {}})

    for symbol in (*TICKERS, "VNINDEX"):
        plan.append({"capability": "security_definition", "symbol": symbol, "query": {}})
    plan.append({"capability": "instruments", "symbol": None,
                 "query": {"symbol": ",".join(TICKERS)}})
    plan.append({"capability": "instruments", "symbol": None,
                 "query": {"indexName": "VN30"}})

    plan.append({"capability": "ohlc", "symbol": None,
                 "query": {"type": "STOCK", "symbol": "HPG", "resolution": "1",
                           "from": from_short, "to": to_short}})
    for symbol in TICKERS:
        plan.append({"capability": "ohlc", "symbol": None,
                     "query": {"type": "STOCK", "symbol": symbol, "resolution": "D",
                               "from": from_wide, "to": to_wide}})
    # resolution="D" came back all-null (accepted, zero rows) for every ticker
    # on the first pass (observed 2026-08-10) -- one bounded alternate-token
    # retry for the daily-bar resolution string, HPG only.
    plan.append({"capability": "ohlc", "symbol": None,
                 "query": {"type": "STOCK", "symbol": "HPG", "resolution": "1D",
                           "from": from_wide, "to": to_wide}})
    for symbol in INDEX_SYMBOLS:
        plan.append({"capability": "ohlc", "symbol": None,
                     "query": {"type": "INDEX", "symbol": symbol, "resolution": "D",
                               "from": from_wide, "to": to_wide}})

    for symbol in TICKERS:
        plan.append({"capability": "trades_latest", "symbol": symbol, "query": {}})
    # trades/quotes history rejected a call with no "from" ("missing timestamp
    # param 'from'"), then rejected a 2-day window ("range exceeds maximum
    # time range", both observed 2026-08-10) -- one further bounded retry at
    # the same same-day window that worked for expected-price/foreign-trading.
    plan.append({"capability": "trades_history", "symbol": "HPG",
                 "query": {"limit": 20, "order": "DESC", "from": from_intraday, "to": to_intraday}})

    for symbol in TICKERS:
        plan.append({"capability": "quotes_latest", "symbol": symbol, "query": {}})
    plan.append({"capability": "quotes_history", "symbol": "HPG",
                 "query": {"limit": 5, "order": "DESC", "from": from_intraday, "to": to_intraday}})

    for symbol in TICKERS:
        plan.append({"capability": "close_price", "symbol": symbol, "query": {}})
    plan.append({"capability": "expected_price", "symbol": "HPG",
                 "query": {"limit": 5, "order": "DESC", "from": from_intraday, "to": to_intraday}})

    for symbol in TICKERS:
        plan.append({"capability": "foreign_trading", "symbol": symbol,
                     "query": {"limit": 5, "order": "DESC", "from": from_intraday, "to": to_intraday}})
    return plan


def _run_one(entry: dict[str, Any], api_key: str, api_secret: str) -> dict[str, Any]:
    result = request_capability(
        entry["capability"], api_key=api_key, api_secret=api_secret,
        symbol=entry.get("symbol"), query=entry.get("query"),
    )
    if result.get("ok") and "body_redacted" in result:
        result["schema"] = top_level_schema(result["body_redacted"])
    return result


def run(mode: str, *, out_dir: Path) -> dict[str, Any]:
    creds = credentials_for_request()
    if creds is None:
        return {"status": CREDENTIAL_INJECTION_REQUIRED}
    api_key, api_secret = creds

    auth_result = _run_one(_AUTH_CHECK_CALL, api_key, api_secret)
    generated_at = vn_time.vn_now_iso()
    if not auth_result.get("ok"):
        report = {
            "status": "DNSE_AUTHENTICATION_FAIL",
            "generated_at": generated_at,
            "auth_check": auth_result,
            "results": [auth_result],
        }
        _write_evidence(out_dir, report)
        return report

    if mode == "auth":
        report = {
            "status": "DNSE_AUTHENTICATION_PASS",
            "generated_at": generated_at,
            "auth_check": auth_result,
            "results": [auth_result],
        }
        _write_evidence(out_dir, report)
        return report

    # mode == "matrix": auth already passed above; run the rest of the bounded plan.
    results = [auth_result]
    for entry in build_call_plan()[1:]:  # [0] is the same working_dates call already run
        results.append(_run_one(entry, api_key, api_secret))

    ok_count = sum(1 for r in results if r.get("ok"))
    report = {
        "status": "DNSE_AUTHENTICATION_PASS",
        "generated_at": generated_at,
        "call_count": len(results),
        "ok_count": ok_count,
        "failed_count": len(results) - ok_count,
        "auth_check": auth_result,
        "results": results,
    }
    _write_evidence(out_dir, report)
    return report


def _write_evidence(out_dir: Path, report: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "probe_results.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    """The compact, always-safe-to-print form -- full bodies stay in the evidence file."""
    by_family: dict[str, dict[str, int]] = {}
    for r in report.get("results", []):
        fam = r.get("family", "auth")
        bucket = by_family.setdefault(fam, {"ok": 0, "failed": 0})
        bucket["ok" if r.get("ok") else "failed"] += 1
    return {
        "status": report["status"],
        "generated_at": report.get("generated_at"),
        "call_count": report.get("call_count", len(report.get("results", []))),
        "ok_count": report.get("ok_count"),
        "failed_count": report.get("failed_count"),
        "by_family": by_family,
        "auth_http_status": report.get("auth_check", {}).get("http_status"),
        "auth_error_code": report.get("auth_check", {}).get("error_code"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                         help="Actually call the network. Without this, only the call plan is printed.")
    parser.add_argument("--probe", choices=("auth", "matrix"), default="auth")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args(argv)

    if not args.live:
        print(json.dumps({"dry_run": True, "probe": args.probe,
                          "call_plan": build_call_plan()}, indent=2, sort_keys=True, default=str))
        return 0

    if credential_status()["configured"] is False:
        print(CREDENTIAL_INJECTION_REQUIRED)
        return 2

    report = run(args.probe, out_dir=Path(args.out_dir))
    print(json.dumps(_summary(report), indent=2, sort_keys=True))
    if report["status"] == CREDENTIAL_INJECTION_REQUIRED:
        return 2
    if report["status"] == "DNSE_AUTHENTICATION_FAIL":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
