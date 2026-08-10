"""Offline shadow-report driver: sanitized DNSE probe evidence -> a deterministic
DNSE current-state price-analytics report.

No network I/O, no secrets.env, no credential material anywhere in this tool --
it only reads a JSON evidence file already produced by
`tools/dnse_market_data_probe.py --probe current-state --live` (or, for a ticker
whose evidence was retained by an earlier milestone -- e.g. VCB -- any other
`probe_results.json` containing an `ohlc` result for that ticker, such as
`--probe price-basis`'s own evidence) and runs it through
`dnse_current_state_price_analytics.build_shadow_report()`.

A ticker with no retained DNSE OHLC price-basis evidence (e.g. VNM, QNS, or any
other current Stock Lookup production-universe ticker) needs no evidence file at
all: `--ticker`'s eligibility is decided first, and an ineligible ticker's OHLC
payload -- present or not -- is never inspected. This is the fail-closed
demonstration Step 11 of the milestone asks for, runnable with `--no-evidence`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dnse_current_state_price_analytics as analytics  # noqa: E402
from runtime_paths import runtime_root as resolve_runtime_root  # noqa: E402

DEFAULT_EVIDENCE = (
    ROOT.parent / "operations-review" / "dnse-current-state-price-analytics-20260810"
    / "probe_results.json"
)
DEFAULT_OUT_DIR = ROOT.parent / "operations-review" / "dnse-current-state-price-analytics-20260810"


def find_ohlc_result(evidence: dict[str, Any], ticker: str) -> dict[str, Any] | None:
    """The first ok `ohlc` result in `evidence` whose requested symbol matches
    `ticker` (case-insensitive) -- never the first ohlc result unconditionally,
    so an evidence file covering more than one ticker (e.g. the price-basis
    milestone's HPG+VCB file) resolves to the right one."""
    normalized = str(ticker).strip().upper()
    for result in evidence.get("results", []):
        if result.get("capability") != "ohlc" or not result.get("ok"):
            continue
        query_symbol = str((result.get("query_sent") or {}).get("symbol", "")).strip().upper()
        if query_symbol == normalized:
            return result
    return None


def build_report(
    ticker: str, evidence_path: Path | None, *, runtime_root: Path,
) -> dict[str, Any]:
    raw_ohlc: dict[str, Any] | None = None
    fetch_provenance: dict[str, Any] = {}
    if evidence_path is not None:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        ohlc_result = find_ohlc_result(evidence, ticker)
        if ohlc_result is not None:
            raw_ohlc = ohlc_result.get("body_redacted")
            fetch_provenance = {
                "evidence_path": str(evidence_path),
                "endpoint": ohlc_result.get("endpoint"),
                "query_sent": ohlc_result.get("query_sent"),
                "pit_label": ohlc_result.get("pit_label"),
            }
    return analytics.build_shadow_report(
        ticker, raw_ohlc, runtime_root=runtime_root, fetch_provenance=fetch_provenance,
    )


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    returns = report.get("returns", {})
    return {
        "ticker": report["ticker"],
        "status": report["status"],
        "qualification_scope": report["qualification_scope"],
        "price_basis": report["price_basis"],
        "as_of_session": report["as_of_session"],
        "coverage": report["coverage"],
        "session_count": len(report.get("observations", [])),
        "return_count": returns.get("return_count", 0),
        "cumulative_return": returns.get("cumulative_return"),
        "volatility": report.get("volatility", {}).get("value"),
        "maximum_drawdown": report.get("drawdown", {}).get("maximum_drawdown"),
        "technical_indicators": report.get("technical_indicators"),
        "analysis_time_semantics": report["analysis_time_semantics"],
        "pit_backtest_eligible": report["pit_backtest_eligible"],
        "warnings": report["warnings"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="HPG")
    parser.add_argument("--evidence", default=str(DEFAULT_EVIDENCE),
                         help="Path to a probe_results.json containing an ohlc result for --ticker.")
    parser.add_argument("--no-evidence", action="store_true",
                         help="Skip reading any evidence file (for a ticker expected to fail closed "
                              "purely on eligibility, e.g. --ticker VNM).")
    parser.add_argument("--runtime-root", default=None,
                         help="Defaults to STOCK_LOOKUP_RUNTIME_ROOT, else CWD.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--write", action="store_true",
                         help="Write the full report to --out-dir/shadow_report_<TICKER>.json.")
    args = parser.parse_args(argv)

    evidence_path: Path | None = None
    if not args.no_evidence:
        evidence_path = Path(args.evidence)
        if not evidence_path.exists():
            print(json.dumps({"status": "evidence_not_found", "path": str(evidence_path)}))
            return 2

    root = resolve_runtime_root(args.runtime_root)
    report = build_report(args.ticker, evidence_path, runtime_root=root)

    if args.write:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"shadow_report_{report['ticker']}.json"
        out_path.write_text(analytics.serialize(report), encoding="utf-8")

    print(json.dumps(_summary(report), indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
