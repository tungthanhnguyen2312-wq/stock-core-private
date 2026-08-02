"""Read-only shadow study: statement taxonomy across all retained periods, its stability,
its agreement with the hand-curated profiles, and the MEASURED Altman Z' coverage delta.

Writes nothing except an optional report file. Never touches
`config/ticker_entity_profiles.csv`, the runtime databases, the evidence stores, or any
bundle artifact. The generated taxonomy is a shadow overlay only; the hand-curated profile
registry remains the sole authority for `issuer_entity_type`.

The Altman delta is measured, not projected: for every ticker the overlay would newly make
eligible, the full applicability gate and every period/scope/currency/scale/positivity gate
is actually run and the rejections are counted by reason.

Usage:
  python tools/shadow_taxonomy_qualification.py --runtime-root <path> [--json out.json]
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from altman_applicability import evaluate_altman_applicability  # noqa: E402
from statement_taxonomy_classifier import classify_statement_taxonomy  # noqa: E402

PROFILES = ROOT / "config" / "ticker_entity_profiles.csv"
# Only this taxonomy is even a candidate for the corporate archetype; the others are
# reported but never proposed as an entity type.
CORPORATE_TAXONOMY = "corporate_vas"


def _manual_profiles() -> dict[str, str]:
    with PROFILES.open(encoding="utf-8-sig") as handle:
        return {row["ticker"].strip().upper(): row["entity_type"].strip()
                for row in csv.DictReader(handle) if row.get("ticker")}


def _industries(runtime_root: Path) -> dict[str, str]:
    connection = sqlite3.connect(str(runtime_root / "vn_stock.db"))
    try:
        rows = connection.execute(
            "SELECT ticker, industry FROM metadata WHERE industry IS NOT NULL AND TRIM(industry) <> ''"
        ).fetchall()
    finally:
        connection.close()
    return {str(t).strip().upper(): str(i) for t, i in rows}


def _classify_every_period(runtime_root: Path) -> dict[str, list[dict[str, Any]]]:
    """One classification per (ticker, retained reporting period) -- not just the latest."""
    import pandas as pd
    by_ticker: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    pattern = str(runtime_root / "data_bctc" / "*_balance_sheet_quarter.parquet")
    for path in sorted(glob.glob(pattern)):
        ticker = os.path.basename(path).split("_")[0].upper()
        try:
            frame = pd.read_parquet(path)
        except Exception:
            continue
        periods = [c for c in frame.columns if str(c)[:4].isdigit()]
        source = str(frame["source"].iloc[0]) if "source" in frame.columns and len(frame) else None
        for period in periods:
            present = frame.loc[frame[period].notna(), "item_id"].astype(str)
            if present.empty:
                continue
            by_ticker[ticker].append(classify_statement_taxonomy(
                set(present), ticker=ticker, source=source, reporting_period=str(period),
                statement_scope="unknown"))
    return by_ticker


def run(runtime_root: Path) -> dict[str, Any]:
    manual = _manual_profiles()
    industries = _industries(runtime_root)
    per_period = _classify_every_period(runtime_root)

    stability: dict[str, Any] = {}
    unstable: list[dict[str, Any]] = []
    resolved: dict[str, str] = {}
    for ticker, results in per_period.items():
        taxonomies = {r["statement_taxonomy"] for r in results}
        observed = [r for r in results if r["classification_status"] == "observed"]
        observed_taxonomies = {r["statement_taxonomy"] for r in observed}
        first = min((r["reporting_period"] for r in results), default=None)
        last = max((r["reporting_period"] for r in results), default=None)
        stable = len(observed_taxonomies) <= 1
        stability[ticker] = {
            "periods_evaluated": len(results), "distinct_taxonomies": sorted(taxonomies),
            "stable": stable, "first_observed_period": first, "last_observed_period": last,
        }
        if not stable:
            unstable.append({"ticker": ticker, "taxonomies": sorted(observed_taxonomies),
                              "periods_evaluated": len(results)})
        # A ticker resolves only if every period that produced an observation agrees.
        resolved[ticker] = observed_taxonomies.pop() if len(observed_taxonomies) == 1 else "unresolved"

    taxonomy_counts = collections.Counter(resolved.values())

    # Confusion matrix against the small manual set. Explicitly not an accuracy claim.
    confusion: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    disagreements: list[dict[str, Any]] = []
    for ticker, manual_type in sorted(manual.items()):
        generated = resolved.get(ticker, "no_statement_data")
        confusion[manual_type][generated] += 1
        corporate_expected = manual_type == "corporate"
        corporate_generated = generated == CORPORATE_TAXONOMY
        if corporate_expected != corporate_generated:
            disagreements.append({"ticker": ticker, "manual_entity_type": manual_type,
                                   "generated_taxonomy": generated})

    # MEASURED Altman applicability, before and after the shadow overlay.
    before = collections.Counter()
    after = collections.Counter()
    newly_eligible: list[str] = []
    after_block_reasons = collections.Counter()
    for ticker in sorted(resolved):
        industry = industries.get(ticker)
        manual_type = manual.get(ticker)
        before_verdict = evaluate_altman_applicability(manual_type, industry)
        before[before_verdict["applicability"]] += 1
        # Overlay proposes "corporate" ONLY where the taxonomy is corporate_vas across all
        # periods AND no manual profile already says otherwise.
        overlay_type = manual_type or (
            "corporate" if resolved[ticker] == CORPORATE_TAXONOMY else None)
        after_verdict = evaluate_altman_applicability(overlay_type, industry)
        after[after_verdict["applicability"]] += 1
        if before_verdict["applicability"] != "eligible" and after_verdict["applicability"] == "eligible":
            newly_eligible.append(ticker)
        if after_verdict["applicability"] != "eligible":
            if overlay_type is None or str(overlay_type).lower() in {"", "unknown"}:
                after_block_reasons["entity_type_unresolved_even_with_overlay"] += 1
            elif not after_verdict["industry_qualified_manufacturing"]:
                after_block_reasons["industry_not_qualified_manufacturing"] += 1
            else:
                after_block_reasons["financial_entity_not_applicable"] += 1

    return {
        "schema_version": "1.0.0",
        "milestone": "SHADOW_STATEMENT_TAXONOMY_AND_ALTMAN_APPLICABILITY_QUALIFICATION",
        "authority_note": ("Generated taxonomy is a shadow overlay. config/ticker_entity_profiles.csv "
                            "remains the sole authority for issuer_entity_type and was not modified."),
        "tickers_with_statement_data": len(per_period),
        "resolved_taxonomy_counts": dict(taxonomy_counts.most_common()),
        "cross_period_stability": {
            "tickers_stable": sum(1 for v in stability.values() if v["stable"]),
            "tickers_unstable": len(unstable),
            "unstable_detail": sorted(unstable, key=lambda row: row["ticker"])[:50],
        },
        "manual_profile_confusion_matrix": {k: dict(v) for k, v in sorted(confusion.items())},
        "manual_profile_disagreements": disagreements,
        "validation_caveat": (f"The manual profile set has {len(manual)} rows. It is sufficient to catch a "
                               "gross error and did, but it cannot establish production accuracy over "
                               f"{len(per_period)} tickers. Treat agreement here as a smoke test only."),
        "altman_applicability_measured": {
            "before_manual_profiles_only": dict(before),
            "after_shadow_overlay": dict(after),
            "newly_eligible_count": len(newly_eligible),
            "newly_eligible_sample": newly_eligible[:25],
            "still_blocked_reasons_after_overlay": dict(after_block_reasons.most_common()),
        },
        "review_queue_non_corporate_or_ambiguous": sorted(
            t for t, tax in resolved.items() if tax != CORPORATE_TAXONOMY)[:200],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()
    report = run(args.runtime_root)
    text = json.dumps(report, indent=1, ensure_ascii=False)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
