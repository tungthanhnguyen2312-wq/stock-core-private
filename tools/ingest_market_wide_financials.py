"""Ingest the retained statement payloads into the market-wide raw observation store.

Offline and read-only over its inputs. It reads `<runtime-root>/data_bctc/*.parquet`,
`<runtime-root>/screen_snapshot.csv`, `<runtime-root>/statement_taxonomy_sidecar.json` and
two tracked config files, and the only things it ever writes are the store's own artifacts
beneath `<runtime-root>/data/market-wide-financials/`:

    observations/<TICKER>.jsonl.gz   ingest_state.json
    coverage_report.json             coverage_by_ticker.csv

It never opens `vn_stock.db`, never touches `analysis_bundle.json`, `bundle_manifest.json`,
`focus_extract.json` or `config/ticker_entity_profiles.csv`, and never reaches the network.

Usage:
  python tools/ingest_market_wide_financials.py --runtime-root <path>
  python tools/ingest_market_wide_financials.py --runtime-root <path> --execute
  python tools/ingest_market_wide_financials.py --runtime-root <path> --check
  python tools/ingest_market_wide_financials.py --runtime-root <path> --execute --ticker HPG --ticker VCB

Without `--execute` this is a strict dry run: the full plan is computed, including the
hashes that decide rebuilt-vs-unchanged, and nothing is written.

`--check` re-derives every shard in memory and compares it against the bytes on disk,
distinguishing a missing shard, a shard whose bytes no longer match the recorded state, a
shard that is stale relative to its source payloads, and a shard that is simply not
byte-reproducible. Exits non-zero on any finding.

Exit codes: 0 success · 1 verification finding or extraction failure · 2 bad invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_file, atomic_write_json  # noqa: E402
from market_wide_financial_coverage import (  # noqa: E402
    COVERAGE_CSV_FILENAME,
    COVERAGE_FILENAME,
    build_coverage,
    coverage_csv,
)
from raw_financial_store import ingest, store_root, verify  # noqa: E402


def _print_ingest(result: dict) -> None:
    counts = result["counts"]
    mode = "EXECUTE" if result["executed"] else "DRY RUN"
    print(f"[market-wide-financials] {mode}")
    print(f"  payloads discovered       : {counts['payloads']}")
    print(f"  tickers                   : {counts['tickers']}")
    print(f"  shards rebuilt            : {counts['rebuilt']}")
    print(f"  shards unchanged          : {counts['unchanged']}")
    if counts["skipped"]:
        print(f"  shards skipped (--ticker) : {counts['skipped']}")
    print(f"  raw observations          : {counts['observations']}")
    if counts["unparsed_payloads"]:
        print(f"  UNPARSED payload names    : {counts['unparsed_payloads']}")
        for entry in result["state"]["unparsed_payloads"][:10]:
            print(f"      {entry['source_file']}: {entry['reason']}")
    if counts["extraction_failures"]:
        print(f"  EXTRACTION FAILURES       : {counts['extraction_failures']}")
        for entry in result["extraction_failures"][:10]:
            print(f"      {entry['ticker']} {entry['source_file']}: {entry['reason']}")
    if result["orphaned_shards"]:
        print(f"  orphaned shards (kept)    : {len(result['orphaned_shards'])}")
    print(f"  state fingerprint         : {result['state']['state_fingerprint'][:16]}...")


def _print_coverage(report: dict) -> None:
    universe = report["universe"]
    families = report["statement_family_coverage"]
    archetype = report["archetype_coverage"]
    ebitda = report["derived_metric_readiness"]["ebitda"]
    reconciliation = report["reconciliation"]
    print("\n[coverage]")
    print(f"  store tickers             : {reconciliation['store_tickers']}")
    print(f"  active universe           : {reconciliation['active_universe_tickers']} "
          f"({universe.get('by_exchange')})")
    print(f"  in store and universe     : {reconciliation['in_store_and_active_universe']}")
    print(f"  universe without a shard  : {reconciliation['in_active_universe_without_store_shard']}")
    print(f"  with all three statements : {families['with_all_three_families']} "
          f"of {families['active_universe_tickers']}")
    print(f"  archetype authority       : {archetype['by_authority']}")
    print(f"  template family           : {archetype['by_template_family']}")
    for metric, counts in report["metric_applicability"].items():
        print(f"  {metric:<24}: {counts}")
    print(f"  EBITDA raw inputs complete: {ebitda['all_raw_identities_present']} "
          f"of {ebitda['not_excluded_tickers']} not ruled out "
          f"({ebitda['coverage_ratio'] * 100:.1f}%); "
          f"{ebitda['confirmed_applicable_tickers']} confirmed applicable")
    print(f"  coverage fingerprint      : {report['coverage_fingerprint'][:16]}...")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--execute", action="store_true",
                        help="Write the store. Without it this is a strict dry run.")
    parser.add_argument("--check", action="store_true",
                        help="Verify the store reproduces byte-identically; never writes.")
    parser.add_argument("--ticker", action="append", default=None,
                        help="Restrict ingestion to these tickers (repeatable).")
    parser.add_argument("--generated-at", default=None,
                        help="Explicit ISO timestamp; defaults to now (UTC, seconds).")
    parser.add_argument("--no-coverage", action="store_true",
                        help="Skip the coverage report (ingest only).")
    parser.add_argument("--json", action="store_true",
                        help="Emit the machine-readable result on stdout.")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if args.execute and args.check:
        print("--execute and --check are mutually exclusive", file=sys.stderr)
        return 2

    runtime_root = args.runtime_root.expanduser().resolve()
    if not (runtime_root / "data_bctc").is_dir():
        print(f"[market-wide-financials] missing {runtime_root / 'data_bctc'}", file=sys.stderr)
        return 2

    if args.check:
        result = verify(runtime_root)
        print(f"[market-wide-financials] CHECK: {result['checked']} shards verified, "
              f"{len(result['findings'])} finding(s)")
        for finding in result["findings"][:20]:
            print(f"    {finding['ticker']}: {finding['finding']}")
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1

    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    result = ingest(runtime_root, generated_at=generated_at, execute=args.execute,
                    tickers=args.ticker)
    _print_ingest(result)

    report = None
    if not args.no_coverage:
        report = build_coverage(runtime_root, source_root=ROOT, generated_at=generated_at)
        _print_coverage(report)
        if args.execute:
            atomic_write_json(store_root(runtime_root) / COVERAGE_FILENAME, report)
            atomic_write_file(store_root(runtime_root) / COVERAGE_CSV_FILENAME,
                              coverage_csv(report))

    if args.json:
        print(json.dumps({"ingest": result["counts"],
                          "state_fingerprint": result["state"]["state_fingerprint"],
                          "coverage_fingerprint": report["coverage_fingerprint"] if report else None},
                         ensure_ascii=False, indent=2))

    return 1 if result["counts"]["extraction_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
