"""Build market-wide canonical financial facts from the retained raw observation store.

Layer 3 of `docs/market_wide_financial_normalization_contract.md`. Offline and read-only over
its inputs: it reads `<runtime-root>/data/market-wide-financials/` (the layer-1 shards),
`<runtime-root>/data/official-evidence/*_citations.jsonl` (read-only) and the tracked
`config/ticker_entity_profiles.csv`, and the only things it writes are the store's own
artifacts beneath `<runtime-root>/data/canonical-financial-facts/`:

    facts/<TICKER>.jsonl.gz        ingest_state.json
    coverage_report.json           coverage_by_metric.csv
    unresolved_metric_queue.jsonl  conflict_queue.jsonl

It never opens `vn_stock.db`, never touches `analysis_bundle.json`, `bundle_manifest.json`,
`focus_extract.json`, `statement_taxonomy_sidecar.json` or `config/ticker_entity_profiles.csv`
for writing, and never reaches the network. It is not part of `tools/operate_stocklookup.py`'s
release path.

Usage:
  python tools/ingest_canonical_financial_facts.py --runtime-root <path>
  python tools/ingest_canonical_financial_facts.py --runtime-root <path> --execute
  python tools/ingest_canonical_financial_facts.py --runtime-root <path> --check
  python tools/ingest_canonical_financial_facts.py --runtime-root <path> --execute --ticker HPG

Without `--execute` this is a strict dry run: the full plan is computed, including the hashes
that decide rebuilt-vs-unchanged, and nothing is written.

`--check` re-derives every shard in memory and compares it against the bytes on disk.

Exit codes: 0 success · 1 verification finding · 2 bad invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from canonical_fact_store import ingest, store_root, verify  # noqa: E402


def _print_ingest(result: dict) -> None:
    counts = result["counts"]
    coverage = result["coverage"]
    mode = "EXECUTE" if result["executed"] else "DRY RUN"
    print(f"[canonical-financial-facts] {mode}")
    print(f"  tickers                   : {counts['tickers']}")
    print(f"  shards rebuilt            : {counts['rebuilt']}")
    print(f"  shards unchanged          : {counts['unchanged']}")
    if counts["skipped"]:
        print(f"  shards skipped            : {counts['skipped']}")
    print(f"  canonical facts           : {counts['facts']}")
    print(f"  unresolved metric queue   : {counts['unresolved_metrics']}")
    print(f"  conflict queue            : {counts['conflicts']}")
    print("  status totals             :")
    for status, count in sorted(coverage["status_totals"].items()):
        print(f"      {status:<20s} {count}")
    print(f"  state fingerprint         : {result['state']['state_fingerprint']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--execute", action="store_true",
                        help="write the store; without it this is a strict dry run")
    parser.add_argument("--check", action="store_true",
                        help="re-derive every shard and compare against disk; never writes")
    parser.add_argument("--ticker", action="append", default=None,
                        help="restrict to one ticker; repeatable")
    parser.add_argument("--json", action="store_true", help="emit the raw result as JSON")
    args = parser.parse_args(argv)

    runtime_root = args.runtime_root
    if not runtime_root.is_dir():
        print(f"runtime root not found: {runtime_root}", file=sys.stderr)
        return 2
    if args.check and args.execute:
        print("--check and --execute are mutually exclusive", file=sys.stderr)
        return 2

    if args.check:
        result = verify(runtime_root)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"[canonical-financial-facts] CHECK  ok={result['ok']}  "
                  f"checked={result.get('checked', 0)}")
            for finding in result.get("findings", [])[:40]:
                print(f"    {finding}")
            if len(result.get("findings", [])) > 40:
                print(f"    ... {len(result['findings']) - 40} more")
        return 0 if result["ok"] else 1

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result = ingest(runtime_root, generated_at=generated_at, execute=args.execute,
                    tickers=args.ticker)
    if not result.get("ok"):
        print(f"[canonical-financial-facts] FAILED: {result.get('reason')}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({key: value for key, value in result.items() if key != "state"},
                         ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_ingest(result)
        if args.execute:
            print(f"  store                     : {store_root(runtime_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
