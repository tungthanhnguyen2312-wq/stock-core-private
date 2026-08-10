"""Offline shadow-report driver: sanitized DNSE index probe evidence -> a
deterministic DNSE index return-series report, plus a cross-check against
vn_stock.db's already-retained benchmark series.

No network I/O, no secrets.env, no credential material anywhere in this tool --
it only reads a JSON evidence file already produced by
`tools/dnse_market_data_probe.py --probe index-return-series --live` and runs
it through `dnse_index_return_series_capability.py`.

A benchmark with no retained cross-check evidence (e.g. VN30) needs no
evidence file at all: `--benchmark`'s eligibility is decided first, and an
ineligible benchmark's OHLC payload -- present or not -- is never inspected.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dnse_current_state_price_analytics as price_analytics  # noqa: E402
import dnse_index_return_series_capability as index_capability  # noqa: E402
from runtime_paths import runtime_root as resolve_runtime_root  # noqa: E402

DEFAULT_EVIDENCE = (
    ROOT.parent / "operations-review" / "dnse-index-return-series-qualification-20260810"
    / "probe_results.json"
)
DEFAULT_OUT_DIR = ROOT.parent / "operations-review" / "dnse-index-return-series-qualification-20260810"


def find_ohlc_result(evidence: dict[str, Any], benchmark_id: str) -> dict[str, Any] | None:
    """The first ok `ohlc` result in `evidence` whose requested symbol matches
    `benchmark_id` (case-insensitive)."""
    normalized = str(benchmark_id).strip().upper()
    for result in evidence.get("results", []):
        if result.get("capability") != "ohlc" or not result.get("ok"):
            continue
        query_symbol = str((result.get("query_sent") or {}).get("symbol", "")).strip().upper()
        if query_symbol == normalized:
            return result
    return None


def retained_close_by_date(runtime_root: Path, benchmark_id: str, dates: list[str]) -> dict[str, float]:
    """Read-only comparison reference: vn_stock.db's own retained close series
    for this benchmark, restricted to the requested session dates. Never
    written to; used only for the Step 6 cross-check, independent of the
    session-gap-detection read `_retained_trading_dates` performs."""
    db_path = Path(runtime_root) / "vn_stock.db"
    if not db_path.exists() or not dates:
        return {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = 1")
        placeholders = ",".join("?" for _ in dates)
        rows = conn.execute(
            f"SELECT date, close FROM ohlcv WHERE ticker = ? AND date IN ({placeholders})",
            (benchmark_id, *dates),
        ).fetchall()
        return {date: close for date, close in rows}
    finally:
        conn.close()


def build_report(
    benchmark_id: str, evidence_path: Path | None, *, runtime_root: Path,
) -> dict[str, Any]:
    raw_ohlc: dict[str, Any] | None = None
    fetch_provenance: dict[str, Any] = {}
    if evidence_path is not None:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        ohlc_result = find_ohlc_result(evidence, benchmark_id)
        if ohlc_result is not None:
            raw_ohlc = ohlc_result.get("body_redacted")
            fetch_provenance = {
                "evidence_path": str(evidence_path),
                "endpoint": ohlc_result.get("endpoint"),
                "query_sent": ohlc_result.get("query_sent"),
                "pit_label": ohlc_result.get("pit_label"),
            }

    series = index_capability.build_index_return_series(
        benchmark_id, raw_ohlc, runtime_root=runtime_root, fetch_provenance=fetch_provenance,
    )
    returns = index_capability.compute_returns_for_series(series)

    cross_check: list[dict[str, Any]] = []
    level_unit_classification = index_capability.INDEX_LEVEL_UNIT_UNQUALIFIED
    if raw_ohlc is not None and series["eligibility"]["eligible_for_current_state_return_series"]:
        normalized = price_analytics.normalize_bars(series["benchmark_id"], raw_ohlc)
        dates = [o["session_date"] for o in normalized["observations"]]
        reference = retained_close_by_date(runtime_root, series["benchmark_id"], dates)
        cross_check = index_capability.cross_check_against_retained(normalized["observations"], reference)
        level_unit_classification = index_capability.classify_level_unit(cross_check)

    return {
        "schema_version": series["schema_version"],
        "benchmark_id": series["benchmark_id"],
        "source": series["source"],
        "status": series["status"],
        "eligibility": series["eligibility"],
        "index_level_unit": series["index_level_unit"],
        "level_unit_classification_this_window": level_unit_classification,
        "source_contract_version": series["source_contract_version"],
        "as_of_session": series["as_of_session"],
        "coverage": series["coverage"],
        "current_state_qualified": series["current_state_qualified"],
        "analysis_time_semantics": series["analysis_time_semantics"],
        "pit_backtest_eligible": series["pit_backtest_eligible"],
        "observations": series["observations"],
        "returns": returns,
        "cross_check": cross_check,
        "warnings": series["warnings"],
        "provenance": series["provenance"],
    }


def serialize(report: Mapping) -> str:
    return json.dumps(report, sort_keys=True, default=str)


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    returns = report.get("returns", {})
    observations = report.get("observations", [])
    cross_check = report.get("cross_check", [])
    return {
        "benchmark_id": report["benchmark_id"],
        "status": report["status"],
        "current_state_qualified": report["current_state_qualified"],
        "index_level_unit": report["index_level_unit"],
        "level_unit_classification_this_window": report["level_unit_classification_this_window"],
        "coverage": report["coverage"],
        "session_count": len(observations),
        "first_session": observations[0]["session_date"] if observations else None,
        "last_session": observations[-1]["session_date"] if observations else None,
        "first_close_level": observations[0]["close_level"] if observations else None,
        "last_close_level": observations[-1]["close_level"] if observations else None,
        "return_count": returns.get("return_count", 0),
        "cumulative_return": returns.get("cumulative_return"),
        "cross_check_session_count": len(cross_check),
        "cross_check_max_relative_difference": (
            max((r["relative_difference"] for r in cross_check if r.get("relative_difference") is not None),
                default=None)
        ),
        "analysis_time_semantics": report["analysis_time_semantics"],
        "pit_backtest_eligible": report["pit_backtest_eligible"],
        "warnings": report["warnings"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", default="VNINDEX")
    parser.add_argument("--evidence", default=str(DEFAULT_EVIDENCE),
                         help="Path to a probe_results.json containing an ohlc result for --benchmark.")
    parser.add_argument("--no-evidence", action="store_true",
                         help="Skip reading any evidence file (for a benchmark expected to fail closed "
                              "purely on eligibility, e.g. --benchmark VN30).")
    parser.add_argument("--runtime-root", default=None,
                         help="Defaults to STOCK_LOOKUP_RUNTIME_ROOT, else CWD.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--write", action="store_true",
                         help="Write the full report to --out-dir/shadow_report_<BENCHMARK>.json.")
    args = parser.parse_args(argv)

    evidence_path: Path | None = None
    if not args.no_evidence:
        evidence_path = Path(args.evidence)
        if not evidence_path.exists():
            print(json.dumps({"status": "evidence_not_found", "path": str(evidence_path)}))
            return 2

    root = resolve_runtime_root(args.runtime_root)
    report = build_report(args.benchmark, evidence_path, runtime_root=root)

    if args.write:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"shadow_report_{report['benchmark_id']}.json"
        out_path.write_text(serialize(report), encoding="utf-8")

    print(json.dumps(_summary(report), indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
