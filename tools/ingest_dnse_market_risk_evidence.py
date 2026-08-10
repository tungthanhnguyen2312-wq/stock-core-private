"""Offline materialization: sanitized DNSE probe evidence already retained under
the workspace-level operations-review/ (by the two prior DNSE current-state
qualification milestones) -> the durable, runtime-root-backed
dnse_market_risk_evidence_store.py.

No network I/O, no secrets.env, no credential material anywhere in this tool --
it only reads the two JSON evidence files already produced by
`tools/dnse_market_data_probe.py --probe current-state --live` (HPG) and
`--probe index-return-series --live` (VNINDEX) in prior milestones, and copies
their sanitized o/h/l/c/t arrays into the runtime-root store. This is a
one-time (replayable) migration step, not a recurring data-refresh job: running
it again with the same evidence input overwrites the store with byte-identical
content (idempotent), and it never fetches anything live.

Preserves exact values, session timestamps, and source/query provenance from
the original evidence; removes no existing qualification artifact (the source
operations-review files are read-only here, never modified or deleted).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dnse_market_risk_evidence_store as store  # noqa: E402
from runtime_paths import runtime_root as resolve_runtime_root  # noqa: E402

DEFAULT_STOCK_EVIDENCE = (
    ROOT.parent / "operations-review" / "dnse-current-state-price-analytics-20260810"
    / "probe_results.json"
)
DEFAULT_BENCHMARK_EVIDENCE = (
    ROOT.parent / "operations-review" / "dnse-index-return-series-qualification-20260810"
    / "probe_results.json"
)


def find_ohlc_result(evidence: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    """The first ok `ohlc` result in `evidence` whose requested symbol matches
    `symbol` (case-insensitive) -- same logic already established independently
    in tools/dnse_current_state_market_risk_shadow.py."""
    normalized = str(symbol).strip().upper()
    for result in evidence.get("results", []):
        if result.get("capability") != "ohlc" or not result.get("ok"):
            continue
        query_symbol = str((result.get("query_sent") or {}).get("symbol", "")).strip().upper()
        if query_symbol == normalized:
            return result
    return None


def materialize(
    stock_evidence_path: Path,
    benchmark_evidence_path: Path,
    runtime_root: Path,
    *,
    ticker: str = "HPG",
    benchmark_id: str = "VNINDEX",
    dry_run: bool,
) -> dict[str, Any]:
    materialized_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report: dict[str, Any] = {
        "runtime_root": str(runtime_root), "dry_run": dry_run, "stock": None, "benchmark": None,
    }

    stock_evidence = json.loads(stock_evidence_path.read_text(encoding="utf-8"))
    stock_result = find_ohlc_result(stock_evidence, ticker)
    if stock_result is not None:
        raw_ohlc = stock_result["body_redacted"]
        provenance = {
            "materialized_from": str(stock_evidence_path),
            "materialized_at": materialized_at,
            "endpoint": stock_result.get("endpoint"),
            "query_sent": stock_result.get("query_sent"),
        }
        report["stock"] = {"ticker": ticker, "status": "materialized",
                           "session_count": len(raw_ohlc.get("t", []))}
        if not dry_run:
            store.write_stock_ohlc(runtime_root, ticker, raw_ohlc, provenance=provenance)
    else:
        report["stock"] = {"ticker": ticker, "status": "not_found_in_evidence"}

    benchmark_evidence = json.loads(benchmark_evidence_path.read_text(encoding="utf-8"))
    benchmark_result = find_ohlc_result(benchmark_evidence, benchmark_id)
    if benchmark_result is not None:
        raw_ohlc = benchmark_result["body_redacted"]
        provenance = {
            "materialized_from": str(benchmark_evidence_path),
            "materialized_at": materialized_at,
            "endpoint": benchmark_result.get("endpoint"),
            "query_sent": benchmark_result.get("query_sent"),
        }
        report["benchmark"] = {"benchmark_id": benchmark_id, "status": "materialized",
                               "session_count": len(raw_ohlc.get("t", []))}
        if not dry_run:
            store.write_benchmark_ohlc(runtime_root, benchmark_id, raw_ohlc, provenance=provenance)
    else:
        report["benchmark"] = {"benchmark_id": benchmark_id, "status": "not_found_in_evidence"}

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-evidence", default=str(DEFAULT_STOCK_EVIDENCE))
    parser.add_argument("--benchmark-evidence", default=str(DEFAULT_BENCHMARK_EVIDENCE))
    parser.add_argument("--ticker", default="HPG")
    parser.add_argument("--benchmark", default="VNINDEX")
    parser.add_argument("--runtime-root", default=None,
                         help="Defaults to STOCK_LOOKUP_RUNTIME_ROOT, else CWD.")
    parser.add_argument("--dry-run", action="store_true",
                         help="Report what would be materialized without writing the store.")
    args = parser.parse_args(argv)

    stock_path = Path(args.stock_evidence)
    benchmark_path = Path(args.benchmark_evidence)
    if not stock_path.exists() or not benchmark_path.exists():
        print(json.dumps({"status": "evidence_not_found",
                          "stock_evidence_exists": stock_path.exists(),
                          "benchmark_evidence_exists": benchmark_path.exists()}))
        return 2

    root = resolve_runtime_root(args.runtime_root)
    report = materialize(stock_path, benchmark_path, root, ticker=args.ticker,
                         benchmark_id=args.benchmark, dry_run=args.dry_run)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
