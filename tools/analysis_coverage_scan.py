"""Universe-wide analysis-capability scan: which models can actually run, for how many
tickers, and exactly what blocks the rest.

Motivation: qualification work had been proceeding one ticker at a time (HPG, then VNM),
which produces data, not a system. This tool answers the systemic question directly --
across every ticker in `financial_snapshot.parquet`, for a given period, which analytical
models have a complete input set, and for those that do not, which specific input is
missing and for how many tickers. That turns "add another ticker by hand" into a measured
decision about which single upstream gap unlocks the most coverage.

Read-only. Never writes to the runtime root, never fetches, never fills a missing value.
A model is reported runnable for a ticker only when every one of its inputs is present and
its denominators are usable; absence is always attributed to a named input.

Evidence tiers are reported separately and never merged:
  - `officially_cited`  -- values cross-checked against a retained, hash-verified official
                           document (data/official-evidence/*.jsonl). Highest tier.
  - `provider_reported` -- values from the provider snapshot only. Statement scope,
                           restatement state, and publication date are unknown for these
                           (docs/data_capability_inventory.md marks this domain
                           `semantics_blocked`), so a model run at this tier is a screening
                           diagnostic, never an evidence-qualified result.

Usage:
  python tools/analysis_coverage_scan.py --runtime-root <path> [--period 2024-Q4] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SNAPSHOT_RELATIVE = "financial_snapshot.parquet"

# Model name -> required snapshot columns. Kept declarative so a new model is one entry,
# and so the blocker report is derived from the same definition the runnability check uses.
MODELS: dict[str, tuple[str, ...]] = {
    "liquidity_screen": ("current_assets", "current_liabilities"),
    "leverage_screen": ("total_liabilities", "equity", "total_assets"),
    "altman_z_prime": ("current_assets", "current_liabilities", "retained_earnings",
                        "total_assets", "total_liabilities", "revenue", "equity"),
    "dupont_roe": ("net_profit", "revenue", "total_assets", "equity"),
    "earnings_quality": ("operating_cash_flow", "net_profit"),
}

# Denominators that must be present and strictly positive for the owning model to run.
POSITIVE_REQUIRED: dict[str, tuple[str, ...]] = {
    "liquidity_screen": ("current_liabilities",),
    "leverage_screen": ("equity", "total_assets"),
    "altman_z_prime": ("total_assets", "total_liabilities"),
    "dupont_roe": ("total_assets", "equity"),
    "earnings_quality": (),
}


def _load(runtime_root: Path):
    import pandas as pd
    return pd.read_parquet(runtime_root / SNAPSHOT_RELATIVE)


def scan(runtime_root: Path, period: str) -> dict[str, Any]:
    frame = _load(runtime_root)
    subset = frame[frame["period"].astype(str) == period]
    universe = int(subset["ticker"].nunique())
    models: dict[str, Any] = {}

    for model, required in MODELS.items():
        missing_columns = [column for column in required if column not in subset.columns]
        if missing_columns:
            models[model] = {"runnable_tickers": 0, "coverage_pct": 0.0,
                             "blocking_inputs": {column: universe for column in missing_columns},
                             "note": "input column absent from the snapshot schema entirely"}
            continue
        usable = subset.dropna(subset=list(required))
        for column in POSITIVE_REQUIRED[model]:
            usable = usable[usable[column] > 0]
        runnable = int(usable["ticker"].nunique())
        # Attribute the shortfall to each individual input, so the report names the one
        # upstream gap worth fixing rather than reporting an undifferentiated "incomplete".
        blocking = {column: int(subset[column].isna().sum()) for column in required
                    if int(subset[column].isna().sum()) > 0}
        models[model] = {
            "runnable_tickers": runnable,
            "coverage_pct": round(100.0 * runnable / universe, 2) if universe else 0.0,
            "blocking_inputs": dict(sorted(blocking.items(), key=lambda item: -item[1])),
        }

    ranked = sorted(
        ((column, count) for model in models.values() for column, count in model["blocking_inputs"].items()),
        key=lambda item: -item[1])
    highest_impact: dict[str, int] = {}
    for column, count in ranked:
        highest_impact.setdefault(column, count)

    return {
        "schema_version": "1.0.0",
        "period": period,
        "universe_tickers": universe,
        "evidence_tier": "provider_reported",
        "tier_limitations": [
            "Statement scope, restatement state, and publication date are unknown for the "
            "provider snapshot (docs/data_capability_inventory.md: semantics_blocked).",
            "A model reported runnable here is a screening diagnostic, not an "
            "evidence-qualified result; officially-cited coverage is reported separately.",
        ],
        "models": models,
        "highest_impact_missing_inputs": dict(sorted(highest_impact.items(), key=lambda item: -item[1])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--period", default="2024-Q4")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    report = scan(args.runtime_root, args.period)
    text = json.dumps(report, indent=1, sort_keys=False)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
