"""Real, retained-data-only market-wide replay for gross_profit / gross_margin.

Reads `data_bctc/*.parquet` directly from the runtime root and derives canonical
facts, period semantics, and Financial Analysis V2 features in memory -- it never
mutates `canonical_fact_store`'s persisted cache or any other generated runtime
artifact. `--issuer-type-ground-truth` accepts a retained
`financial_analysis_engine_v2.build_artifact` artifact (any prior bounded
milestone's full market-wide run) to source per-ticker `issuer_type`, so entity
classification exactly matches the last-established INDUSTRIAL/LIMITED split
instead of independently re-deriving it. No network calls, no writes outside
`--output`.

Usage:
  python tools/run_gross_margin_real_replay.py --runtime-root <path> \
      --issuer-type-ground-truth <financial_analysis_v2_market_wide_after.json> \
      --output coverage.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import raw_financial_store as rfs  # noqa: E402
import raw_financial_observations as robs  # noqa: E402
import canonical_financial_facts as facts  # noqa: E402
import structured_financial_period_semantics as sps  # noqa: E402
import financial_analysis_engine_v2 as engine  # noqa: E402

USABLE_STATUSES = {facts.STATUS_QUALIFIED, facts.STATUS_PROVIDER_REPORTED, facts.STATUS_PARTIAL}
OLD_READINESS_FEATURES = ("net_margin", "pbt_margin", "equity_to_assets", "cash_to_assets", "assets_yoy", "equity_yoy", "current_ratio")
BANK_TICKERS = ("ABB", "ACB", "BID", "MBB", "TCB", "VCB")


def _issuer_types(ground_truth_path: Path | None) -> dict[str, str | None]:
    if ground_truth_path is None or not ground_truth_path.is_file():
        return {}
    payload = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    records = payload.get("records") or {}
    return {ticker: record.get("issuer_type") for ticker, record in records.items()}


def run(runtime_root: Path, issuer_type_ground_truth: Path | None) -> dict:
    issuer_type_by_ticker = _issuer_types(issuer_type_ground_truth)
    discovered = rfs.discover_payloads(runtime_root)
    source_root = rfs.source_root(runtime_root)
    by_ticker = discovered["by_ticker"]

    raw_gross_profit_tickers: set[str] = set()
    vci_gross_profit_raw_present: set[str] = set()
    canonical_gross_profit_tickers: set[str] = set()
    gross_profit_fact_count = 0
    compatible_pair_tickers: set[str] = set()
    compatible_pair_count = 0

    gross_margin_status: Counter = Counter()
    gross_margin_direction_status: Counter = Counter()
    gross_margin_trajectory_state: Counter = Counter()
    entity_family: Counter = Counter()
    current_research_ready_before = 0
    current_research_ready_after = 0
    newly_ready_tickers: list[str] = []
    zero_observation_tickers: list[str] = []
    ticker_not_in_ground_truth: list[str] = []
    bank_regression: dict[str, dict] = {}

    denominator = 0
    for ticker, entries in sorted(by_ticker.items()):
        if issuer_type_by_ticker and ticker not in issuer_type_by_ticker:
            ticker_not_in_ground_truth.append(ticker)
            continue
        observations: list[dict] = []
        for entry in entries:
            path = source_root / entry["source_file"]
            try:
                extracted = robs.extract_payload_file(path)
            except Exception:  # noqa: BLE001 -- an unreadable payload is a reported gap, never a crash
                continue
            observations.extend(extracted["observations"])

        gp_raw = [o for o in observations if o.get("raw_item_id") == "gross_profit"
                  and o.get("statement_family") == "income_statement"]
        if gp_raw:
            raw_gross_profit_tickers.add(ticker)
        if any(str(o.get("provider") or "").upper() == "VCI" for o in gp_raw):
            vci_gross_profit_raw_present.add(ticker)

        if not observations:
            zero_observation_tickers.append(ticker)
            continue
        denominator += 1

        built = facts.build_facts(ticker, observations)
        gp_facts = [f for f in built["facts"] if f["canonical_metric"] == "gross_profit"]
        usable_gp = [f for f in gp_facts if f["status"] in USABLE_STATUSES]
        if usable_gp:
            canonical_gross_profit_tickers.add(ticker)
            gross_profit_fact_count += len(usable_gp)

        revenue_facts = {f["reporting_period"]: f for f in built["facts"]
                         if f["canonical_metric"] == "revenue" and f["status"] in USABLE_STATUSES}
        has_pair = False
        for gp in usable_gp:
            rev = revenue_facts.get(gp["reporting_period"])
            if rev and rev["provider"] == gp["provider"]:
                has_pair = True
                compatible_pair_count += 1
        if has_pair:
            compatible_pair_tickers.add(ticker)

        rows = [sps.project_fact(f) for f in built["facts"]]
        issuer_type = issuer_type_by_ticker.get(ticker)
        result = engine.build_ticker_context(ticker, rows, issuer_type=issuer_type, source_identities={"replay": "gross_margin_depth_v1"})
        entity_family[result["analysis_family"]] += 1
        gross_margin_status[result["features"]["gross_margin"]["fitness"]] += 1
        gross_margin_direction_status[result["features"]["gross_margin_direction"]["fitness"]] += 1
        gross_margin_trajectory_state[result["states"]["gross_margin_trajectory_state"]] += 1

        before = result["analysis_family"] == engine.INDUSTRIAL and any(
            result["features"][item]["fitness"] == "READY" for item in OLD_READINESS_FEATURES)
        after = result["current_research_ready"]
        current_research_ready_before += bool(before)
        current_research_ready_after += bool(after)
        if after and not before:
            newly_ready_tickers.append(ticker)

        if ticker in BANK_TICKERS:
            bank_regression[ticker] = {
                "issuer_type": issuer_type,
                "analysis_family": result["analysis_family"],
                "gross_margin_fitness": result["features"]["gross_margin"]["fitness"],
                "bank_npl_ratio_fitness": result["features"]["bank_npl_ratio"]["fitness"],
                "bank_ldr_fitness": result["features"]["bank_ldr"]["fitness"],
                "bank_cir_fitness": result["features"]["bank_cir"]["fitness"],
            }

    return {
        "denominator": denominator,
        "discovered_payload_tickers": discovered["ticker_count"],
        "unparsed_payloads": len(discovered["unparsed"]),
        "zero_observation_tickers": len(zero_observation_tickers),
        "ticker_not_in_ground_truth": ticker_not_in_ground_truth,
        "RAW_GROSS_PROFIT_TICKERS": len(raw_gross_profit_tickers),
        "RAW_GROSS_PROFIT_TICKERS_WITH_ANY_VCI_ROW": len(vci_gross_profit_raw_present),
        "CANONICAL_GROSS_PROFIT_TICKERS": len(canonical_gross_profit_tickers),
        "GROSS_PROFIT_CANONICAL_FACT_COUNT": gross_profit_fact_count,
        "COMPATIBLE_GROSS_PROFIT_REVENUE_PAIRS_TICKERS": len(compatible_pair_tickers),
        "COMPATIBLE_GROSS_PROFIT_REVENUE_PAIRS_TOTAL": compatible_pair_count,
        "gross_margin_status": dict(sorted(gross_margin_status.items())),
        "gross_margin_direction_status": dict(sorted(gross_margin_direction_status.items())),
        "gross_margin_trajectory_state": dict(sorted(gross_margin_trajectory_state.items())),
        "entity_family_distribution": dict(sorted(entity_family.items())),
        "current_research_ready_before": current_research_ready_before,
        "current_research_ready_after": current_research_ready_after,
        "newly_ready_ticker_count": len(newly_ready_tickers),
        "newly_ready_tickers_sample": newly_ready_tickers[:20],
        "bank_regression": bank_regression,
        "network_used": False,
        "runtime_or_primary_write": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--issuer-type-ground-truth", type=Path, default=None,
                        help="a retained financial_analysis_engine_v2 build_artifact JSON to source issuer_type from")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    if not args.runtime_root.is_dir():
        print(f"runtime root not found: {args.runtime_root}", file=sys.stderr)
        return 2
    report = run(args.runtime_root, args.issuer_type_ground_truth)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
