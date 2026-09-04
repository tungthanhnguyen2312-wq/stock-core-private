"""Deterministic market-wide calculation-readiness report over the canonical fact store.

Reads `<runtime-root>/data/canonical-financial-facts/` and writes one artifact beside it:

    calculation_readiness_report.json

Read-only over everything else other than an explicit, read-only `vn_stock.db` open when
`--session-date` is given (see below): it never touches a published artifact and never reaches
the network. It computes no ranking and no score: every output is a count, a named blocker, or
a value with its formula lineage.

`--session-date` is optional and changes nothing about the price-independent capabilities
(`ebitda`, `roe`): without it, `market_capitalisation`/`enterprise_value`/`pe`/`pb`/`ev_ebitda`
report `blocked` for every ticker, exactly as before this flag existed, because
`evaluate_ticker()`'s `session_price`/`effective_shares` default to `None`. With it, this tool
resolves each ticker's real session price (`canonical_financial_bundle_section.
_resolve_session_inputs`, which already existed and is the same resolver
`canonical_financial_bundle_section.attach`'s opt-in bundle section uses -- reused, not
reimplemented here) and effective shares (`market_wide_current_shares_resolver`), and passes
them through so those five capabilities are actually measured rather than trivially blocked by
omission. `--price-basis-verified` is a separate, explicit opt-in (default False): the price
basis is not independently verified market-wide (see this module's own docstring), so results
stay `provider_reported`, never `qualified`, unless the caller asserts otherwise.

Usage:
  python tools/report_market_wide_readiness.py --runtime-root <path>
  python tools/report_market_wide_readiness.py --runtime-root <path> --session-date 2026-08-25
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
    parser.add_argument("--session-date", default=None,
                        help="resolve real session price/shares for this date (YYYY-MM-DD) "
                             "so market_capitalisation/enterprise_value/pe/pb/ev_ebitda are "
                             "actually measured instead of trivially blocked; omit to keep the "
                             "price-independent-only behavior unchanged")
    parser.add_argument("--price-basis-verified", action="store_true",
                        help="assert the resolved price basis is independently verified "
                             "(default False -- results stay provider_reported, never "
                             "qualified, unless explicitly asserted)")
    args = parser.parse_args(argv)

    runtime_root = args.runtime_root
    if not runtime_root.is_dir():
        print(f"runtime root not found: {runtime_root}", file=sys.stderr)
        return 2

    state = _load_state(runtime_root)
    if not state:
        print("canonical fact store is missing or has an unsupported schema", file=sys.stderr)
        return 1

    shares_store = None
    if args.session_date:
        from canonical_financial_bundle_section import _resolve_session_inputs
        try:
            from market_wide_current_shares_resolver import _Store
            shares_store = _Store(runtime_root)
        except Exception:  # noqa: BLE001 - each ticker then resolves fail-closed on its own
            shares_store = None

    wanted = {ticker.upper() for ticker in args.ticker} if args.ticker else None
    per_ticker = []
    for record in state.get("tickers") or []:
        ticker = str(record["ticker"])
        if wanted is not None and ticker not in wanted:
            continue
        facts = read_facts(runtime_root, ticker)
        if not facts:
            continue
        session_price, effective_shares = (None, None)
        if args.session_date:
            try:
                session_price, effective_shares = _resolve_session_inputs(
                    ticker, {}, runtime_root, args.session_date, shares_store)
            except Exception:  # noqa: BLE001 - unresolved inputs fail closed to blocked, not a crash
                session_price, effective_shares = (None, None)
        per_ticker.append(evaluate_ticker(
            ticker, facts, _applicability_from_state(record),
            session_price=session_price, effective_shares=effective_shares,
            price_basis_verified=args.price_basis_verified))

    report = build_readiness_report(per_ticker)
    report["generated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report["fact_store_state_fingerprint"] = state.get("state_fingerprint")
    report["session_date"] = args.session_date
    report["price_basis_verified"] = args.price_basis_verified

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
