"""Offline shadow-report driver: HPG + VNINDEX retained DNSE probe evidence ->
a deterministic current-state beta/correlation report.

No network I/O, no secrets.env, no credential material anywhere in this tool
-- it only reads the two JSON evidence files already produced by
`tools/dnse_market_data_probe.py --probe current-state --live` (HPG) and
`--probe index-return-series --live` (VNINDEX) in prior milestones, and runs
them through `dnse_current_state_market_risk.py`. Both evidence files are
reused as-is; this milestone performs zero new network calls.

A ticker/benchmark absent from its evidence file (e.g. `--ticker VNM`) needs
no special flag: `find_ohlc_result` simply finds nothing, `raw_ohlc` stays
`None`, and the ticker's own DNSE price-analytics eligibility gate fails
closed before any payload is inspected -- the same fail-closed demonstration
pattern already established by the sibling shadow tools
(`dnse_current_state_analytics_shadow.py`, `dnse_index_return_series_shadow.py`).
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

import dnse_current_state_market_risk as market_risk  # noqa: E402
import dnse_current_state_price_analytics as price_analytics  # noqa: E402
import dnse_index_return_series_capability as index_capability  # noqa: E402
from runtime_paths import runtime_root as resolve_runtime_root  # noqa: E402

DEFAULT_STOCK_EVIDENCE = (
    ROOT.parent / "operations-review" / "dnse-current-state-price-analytics-20260810"
    / "probe_results.json"
)
DEFAULT_BENCHMARK_EVIDENCE = (
    ROOT.parent / "operations-review" / "dnse-index-return-series-qualification-20260810"
    / "probe_results.json"
)
DEFAULT_OUT_DIR = ROOT.parent / "operations-review" / "current-state-beta-correlation-20260810"


def find_ohlc_result(evidence: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    """The first ok `ohlc` result in `evidence` whose requested symbol matches
    `symbol` (case-insensitive). Shared shape for both a stock ticker and an
    index benchmark -- DNSE's `ohlc` endpoint uses the same
    `query_sent.symbol` field for both (identical logic to the
    ticker-scoped/benchmark-scoped copies already established in
    `dnse_current_state_analytics_shadow.py` /
    `dnse_index_return_series_shadow.py`)."""
    normalized = str(symbol).strip().upper()
    for result in evidence.get("results", []):
        if result.get("capability") != "ohlc" or not result.get("ok"):
            continue
        query_symbol = str((result.get("query_sent") or {}).get("symbol", "")).strip().upper()
        if query_symbol == normalized:
            return result
    return None


def _load_raw_ohlc(
    evidence_path: Path | None, symbol: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if evidence_path is None or not evidence_path.exists():
        return None, {}
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    ohlc_result = find_ohlc_result(evidence, symbol)
    if ohlc_result is None:
        return None, {}
    provenance = {
        "evidence_path": str(evidence_path),
        "endpoint": ohlc_result.get("endpoint"),
        "query_sent": ohlc_result.get("query_sent"),
        "pit_label": ohlc_result.get("pit_label"),
    }
    return ohlc_result.get("body_redacted"), provenance


def build_report(
    ticker: str,
    benchmark_id: str,
    stock_evidence_path: Path | None,
    benchmark_evidence_path: Path | None,
    *,
    runtime_root: Path,
) -> dict[str, Any]:
    stock_raw, stock_provenance = _load_raw_ohlc(stock_evidence_path, ticker)
    benchmark_raw, benchmark_provenance = _load_raw_ohlc(benchmark_evidence_path, benchmark_id)

    stock_report = price_analytics.build_shadow_report(
        ticker, stock_raw, runtime_root=runtime_root, fetch_provenance=stock_provenance,
        include_technical_indicators=False,
    )
    benchmark_series = index_capability.build_index_return_series(
        benchmark_id, benchmark_raw, runtime_root=runtime_root, fetch_provenance=benchmark_provenance,
    )
    return market_risk.compute_current_state_beta_correlation(stock_report, benchmark_series)


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    aligned = report.get("aligned_sessions", {})
    return {
        "ticker": report["ticker"],
        "benchmark": report["benchmark"],
        "qualification_status": report["qualification_status"],
        "input_gates": report["input_gates"],
        "stock_return_count": aligned.get("stock_return_count", 0),
        "benchmark_return_count": aligned.get("benchmark_return_count", 0),
        "paired_return_count": report["paired_return_count"],
        "dropped_stock_sessions": aligned.get("dropped_stock_sessions", []),
        "dropped_benchmark_sessions": aligned.get("dropped_benchmark_sessions", []),
        "beta": report["beta"],
        "correlation": report["correlation"],
        "coverage": report["coverage"],
        "analysis_time_semantics": report["analysis_time_semantics"],
        "pit_backtest_eligible": report["pit_backtest_eligible"],
        "warnings": report["warnings"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="HPG")
    parser.add_argument("--benchmark", default="VNINDEX")
    parser.add_argument("--stock-evidence", default=str(DEFAULT_STOCK_EVIDENCE))
    parser.add_argument("--benchmark-evidence", default=str(DEFAULT_BENCHMARK_EVIDENCE))
    parser.add_argument("--runtime-root", default=None,
                         help="Defaults to STOCK_LOOKUP_RUNTIME_ROOT, else CWD.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--write", action="store_true",
                         help="Write the full report to "
                              "--out-dir/shadow_report_<TICKER>_<BENCHMARK>.json.")
    args = parser.parse_args(argv)

    root = resolve_runtime_root(args.runtime_root)
    report = build_report(
        args.ticker, args.benchmark,
        Path(args.stock_evidence), Path(args.benchmark_evidence),
        runtime_root=root,
    )

    if args.write:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"shadow_report_{report['ticker']}_{report['benchmark']}.json"
        out_path.write_text(market_risk.serialize(report), encoding="utf-8")

    print(json.dumps(_summary(report), indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
