"""Classify the active-universe tickers that have no retained statement payload.

Bounded and resumable. Reads `<runtime-root>/screen_snapshot.csv` and the raw observation
store to determine the missing set, then probes each unresolved ticker through the same
authorized provider path `bctc_sync.py` uses (`vnstock` `Finance(source).<family>`), and
writes only:

    <runtime-root>/data/market-wide-financials/missing_payload_reconciliation.json
    <runtime-root>/data/market-wide-financials/missing_payload_report.json

It never writes a statement payload, never rebuilds the observation store, never touches
`vn_stock.db` or any published artifact, and never reopens a terminally blocked price-path or
corporate-event investigation.

Without `--execute` this is a strict dry run and issues no network request at all.

Usage:
  python tools/reconcile_missing_payloads.py --runtime-root <path>
  python tools/reconcile_missing_payloads.py --runtime-root <path> --execute --max-tickers 25

Exit codes: 0 success · 1 universe or store unavailable · 2 bad invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_wide_financial_coverage import load_universe  # noqa: E402
from missing_payload_reconciliation import (  # noqa: E402
    DEFAULT_DELAY_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_TICKERS,
    reconcile,
    report_path,
    state_path,
)
from raw_financial_store import load_state as load_raw_state, state_index  # noqa: E402


def _instrument_map(runtime_root: Path) -> dict[str, str]:
    import pandas as pd

    path = runtime_root / "screen_snapshot.csv"
    if not path.is_file():
        return {}
    frame = pd.read_csv(path)
    if "instrument_type" not in frame.columns:
        return {}
    return {str(row.get("ticker") or "").strip().upper():
            str(row.get("instrument_type") or "").strip().upper()
            for row in frame.to_dict("records")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--execute", action="store_true",
                        help="issue provider requests; without it no request is made")
    parser.add_argument("--max-tickers", type=int, default=DEFAULT_MAX_TICKERS)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--delay-seconds", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    runtime_root = args.runtime_root
    if not runtime_root.is_dir():
        print(f"runtime root not found: {runtime_root}", file=sys.stderr)
        return 2
    if args.max_tickers < 0 or not 1 <= args.max_attempts <= 3 or not 0.0 <= args.delay_seconds <= 30.0:
        print("bounded-run arguments out of range", file=sys.stderr)
        return 2

    universe = load_universe(runtime_root)
    if not universe.get("available"):
        print(f"universe unavailable: {universe.get('reason')}", file=sys.stderr)
        return 1
    store = set(state_index(load_raw_state(runtime_root)))
    if not store:
        print("raw observation store is missing or unsupported", file=sys.stderr)
        return 1

    missing = sorted(set(universe.get("tickers") or []) - store)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result = reconcile(runtime_root, missing_tickers=missing, generated_at=generated_at,
                       instrument_of=_instrument_map(runtime_root), execute=args.execute,
                       max_tickers=args.max_tickers, max_attempts=args.max_attempts,
                       delay_seconds=args.delay_seconds)

    report = result["report"]
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        mode = "EXECUTE" if result["executed"] else "DRY RUN"
        print(f"[missing-payload-reconciliation] {mode}")
        print(f"  active-universe tickers with no retained payload : {len(missing)}")
        print(f"  probed this run                                  : {len(result['probed'])}")
        print(f"  remaining unprobed                               : {len(result['remaining'])}")
        print("  classifications:")
        for classification, count in sorted(report["classification_counts"].items()):
            print(f"      {classification:<26s} {count}")
        if report["provider_error_kinds"]:
            print("  provider error kinds:")
            for kind, count in sorted(report["provider_error_kinds"].items()):
                print(f"      {kind:<40s} {count}")
        if result["executed"]:
            print(f"  state  : {state_path(runtime_root)}")
            print(f"  report : {report_path(runtime_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
