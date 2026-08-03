"""Deterministic market-wide calculation-readiness report over the canonical fact store.

Reads `<runtime-root>/data/canonical-financial-facts/` and writes one artifact beside it:

    calculation_readiness_report.json

Read-only over everything else. It never opens `vn_stock.db`, never touches a published
artifact, and never reaches the network. It computes no ranking and no score: every output is
a count, a named blocker, or a value with its formula lineage.

Usage:
  python tools/report_market_wide_readiness.py --runtime-root <path>
  python tools/report_market_wide_readiness.py --runtime-root <path> --execute
  python tools/report_market_wide_readiness.py --runtime-root <path> --ticker HPG --detail

Exit codes: 0 success · 1 store missing · 2 bad invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_json  # noqa: E402
from canonical_fact_store import (  # noqa: E402
    _load_state,
    read_facts,
    store_root,
)
from financial_entity_applicability import (  # noqa: E402
    load_entity_profiles,
)
from market_wide_calculation_readiness import (  # noqa: E402
    CAPABILITIES,
    build_readiness_report,
    evaluate_ticker,
)

REPORT_FILENAME = "calculation_readiness_report.json"


def _applicability_from_state(record: dict) -> dict:
    """Rebuild the applicability verdict the fact store already recorded per ticker.

    The store persists the resolved archetype, so the readiness pass does not re-read the raw
    observation shards to recover it.
    """
    from financial_entity_applicability import metric_applicability

    archetype = {
        "ticker": record["ticker"],
        "issuer_entity_type": record.get("issuer_entity_type"),
        "template_family": record.get("template_family"),
        "authority": record.get("archetype_authority"),
    }
    return {
        "ticker": record["ticker"],
        "archetype": archetype,
        "metric_applicability": {metric: metric_applicability(archetype, metric)
                                 for metric in ("ebitda", "ev_ebitda")},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="write the report artifact")
    parser.add_argument("--ticker", action="append", default=None)
    parser.add_argument("--detail", action="store_true",
                        help="print each selected ticker's per-period verdicts")
    args = parser.parse_args(argv)

    runtime_root = args.runtime_root
    if not runtime_root.is_dir():
        print(f"runtime root not found: {runtime_root}", file=sys.stderr)
        return 2

    state = _load_state(runtime_root)
    if not state:
        print("canonical fact store is missing or has an unsupported schema", file=sys.stderr)
        return 1

    wanted = {ticker.upper() for ticker in args.ticker} if args.ticker else None
    per_ticker = []
    for record in state.get("tickers") or []:
        ticker = str(record["ticker"])
        if wanted is not None and ticker not in wanted:
            continue
        facts = read_facts(runtime_root, ticker)
        if not facts:
            continue
        per_ticker.append(evaluate_ticker(ticker, facts, _applicability_from_state(record)))

    report = build_readiness_report(per_ticker)
    report["generated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report["fact_store_state_fingerprint"] = state.get("state_fingerprint")

    print("[calculation-readiness]")
    print(f"  tickers evaluated          : {report['ticker_count']}")
    for name in CAPABILITIES:
        ready = report["ready_ticker_counts"][name]
        na = report["not_applicable_ticker_counts"][name]
        print(f"  {name:<26s} ready={ready:<6d} not_applicable={na}")
    print(f"  EV balance-sheet components ready : "
          f"{report['enterprise_value_balance_sheet_components_ready']}")

    if args.detail:
        for entry in per_ticker:
            print(f"\n  == {entry['ticker']}")
            for period in entry["periods"]:
                for name in CAPABILITIES:
                    verdict = period[name]
                    if verdict["readiness"] == "ready":
                        print(f"     {period['reporting_period']} {name:<22s} "
                              f"{verdict['status']:<18s} {verdict['value']}")
                    elif verdict["readiness"] == "not_applicable":
                        print(f"     {period['reporting_period']} {name:<22s} not_applicable")

    if args.execute:
        target = store_root(runtime_root) / REPORT_FILENAME
        atomic_write_json(target, report)
        print(f"  report                     : {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
