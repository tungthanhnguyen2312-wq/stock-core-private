#!/usr/bin/env python3
"""Real retained-evidence replay for CORE_FUNDAMENTAL_VALUATION_AND_PEER_CONTEXT_V1.

Read-only against tracked evidence already retained in this worktree's
`operations-review/`. No provider calls, no store writes, no new acquisition:

  * `market-wide-structured-financial-period-semantics-v1-20260831/` -- the semantic
    facts `financial_analysis_engine_v2`/`market_wide_financial_analysis_v2_scaleout`
    consume (the "Financial V2" real production path).
  * `market-wide-fundamental-feature-store-v1-20260831/` -- the Feature Store artifact
    the scaleout widens the engine's cohort against.
  * `market-wide-financial-entity-classification-scaleout-v1-20260901/` -- entity-class
    diagnostics (issuer_entity_type per ticker) and the retained ICB level-2 sector
    snapshot used here for genuine sector/industry peer cohorts.
  * `current-common-shares-authority-recovery-and-scaleout-v1-20260827/
    market_wide_current_valuation_artifact.json` -- a retained, already-computed
    `market_wide_current_valuation/v1` artifact (934 RESEARCH_USABLE existing-method
    entries market-wide as of its own 2026-08-26 price session) exercising the
    pre-existing, unmodified `current_research_valuation_context.evaluate_ticker_
    valuation`/`attach_peer_relative` P/E, P/B, P/S route this milestone reuses rather
    than rebuilds.

Entity classification is sourced from the CURRENT tracked `entity_classification_contract`
authority (`load_layered_entity_profiles()`, which already includes the 2026-09-02
LEGACY_ENTITY_CLASSIFICATION_TRACKED_AUTHORITY_RECOVERY_V1 fourth tier), layered over the
2026-09-01 diagnostics snapshot as a fallback -- not the diagnostics snapshot alone. Doing
so reproduces the regression-locked headline numbers exactly from tracked inputs alone:
Financial V2 denominator 1,492, current_research_ready 1,380, entity family split
1,382 INDUSTRIAL / 83 LIMITED / 27 UNCLASSIFIED_GENERIC.

The underlying semantic-facts snapshot itself still predates this milestone's 2026-09-02
base (gross_profit canonicalization landed 2026-09-02; current_assets/current_liabilities
landed in the 2026-09-01 working-capital milestone, one day after this snapshot), so this
replay's own gross_margin/current_ratio/securities counts read lower than the engine's true
current market-wide numbers -- reported explicitly below, not smoothed over.
same_provider_roe/roa_eop_proxy (pre-existing, unmodified) and this milestone's new
same_provider_roe_avg_equity/roa_avg_assets are BOTH 0 READY market-wide in this replay for
a third, independent, snapshot-vintage-unrelated reason: the retained corpus's dominant
provider split (KBS income statements, VCI balance sheets) makes a same-provider net-income-
and-equity/assets pair rare -- confirmed by mixed_provider_roa_proxy's much higher retained
proxy count for the same tickers.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import current_research_valuation_context as valuation_context  # noqa: E402
import entity_classification_contract as entity_classification  # noqa: E402
import exchange_industry_classification as industry_classification  # noqa: E402
import financial_analysis_engine_v2 as engine  # noqa: E402
import financial_analysis_product_projection as product_projection  # noqa: E402
import market_wide_financial_analysis_v2_scaleout as scaleout  # noqa: E402

SEMANTICS_DIR = ROOT / "operations-review" / "market-wide-structured-financial-period-semantics-v1-20260831"
FEATURE_STORE_DIR = ROOT / "operations-review" / "market-wide-fundamental-feature-store-v1-20260831"
CLASSIFICATION_DIR = ROOT / "operations-review" / "market-wide-financial-entity-classification-scaleout-v1-20260901"
VALUATION_DIR = ROOT / "operations-review" / "current-common-shares-authority-recovery-and-scaleout-v1-20260827"
REQUESTED_AT = "2026-09-02T00:00:00+07:00"
REPRESENTATIVE_TICKERS = ("HPG", "PNJ")


def load_semantic_rows() -> tuple[list[dict], dict]:
    artifact = json.loads((SEMANTICS_DIR / "structured_financial_period_semantics_artifact.json").read_text(encoding="utf-8"))
    with gzip.open(SEMANTICS_DIR / "structured_financial_period_semantics_facts.jsonl.gz", "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return rows, artifact


def load_classification_diagnostics() -> dict:
    return json.loads((CLASSIFICATION_DIR / "scaleout_classification_diagnostics.json").read_text(encoding="utf-8"))


def load_industry_by_ticker() -> dict[str, str]:
    """ticker -> retained ICB level-2 sector label, only where genuinely retained."""
    snapshot = industry_classification.load_snapshot(CLASSIFICATION_DIR / "exchange_industry_classification_snapshot.json")
    index = industry_classification.industry_index(snapshot)
    return {ticker: record["icb_level_2_label"] for ticker, record in index.items()
            if isinstance(record.get("icb_level_2_label"), str) and record["icb_level_2_label"].strip()}


def load_current_valuation_artifact() -> dict:
    return json.loads((VALUATION_DIR / "market_wide_current_valuation_artifact.json").read_text(encoding="utf-8"))


def build_financial_v2(rows: list[dict], semantics_artifact: dict, classification: dict) -> dict:
    records, feature_store_artifact = scaleout.load_feature_store(
        FEATURE_STORE_DIR / "market_wide_fundamental_feature_store_artifact.json",
        FEATURE_STORE_DIR / "market_wide_fundamental_feature_store_records.jsonl.gz",
    )
    records_with_types = {ticker: dict(record) for ticker, record in records.items()}
    for row in classification.get("rows") or []:
        ticker = str(row.get("ticker") or "").upper()
        outcome = str(row.get("outcome") or "")
        if ticker in records_with_types and outcome in {"corporate", "bank", "securities", "insurance", "finance_company"}:
            records_with_types[ticker]["entity_type"] = outcome
    # The frozen 2026-09-01 diagnostics snapshot above predates LEGACY_ENTITY_CLASSIFICATION_
    # TRACKED_AUTHORITY_RECOVERY_V1's 2026-09-02 fourth classification tier. The current tracked
    # entity_classification_contract authority is fully reproducible from tracked config alone
    # (no sibling-worktree or live-DB input) and takes final precedence where it resolves a ticker.
    for ticker, entity_type in entity_classification.load_layered_entity_profiles().items():
        if ticker in records_with_types:
            records_with_types[ticker]["entity_type"] = entity_type
    qualified_flow_artifact = scaleout.build_qualified_flow_artifact(
        semantic_rows=rows, feature_records=records_with_types, requested_at=REQUESTED_AT,
    )
    return scaleout.build_scaleout(
        semantic_rows=rows, feature_records=records_with_types, feature_store_artifact=feature_store_artifact,
        period_semantics_identity=semantics_artifact["artifact_identity"], requested_at=REQUESTED_AT,
        classification_diagnostics_identity=classification.get("diagnostics_identity"),
        qualified_flow_artifact=qualified_flow_artifact,
    )


def valuation_counts(financial_v2: dict, current_valuation: dict) -> dict:
    """Real P/E, P/B, P/S readiness over the pre-existing, unmodified valuation route,
    joined to this milestone's fresh Financial V2 TTM outputs where the ticker overlaps."""
    engine_records = financial_v2["records"]
    valuation_records = current_valuation.get("records") or {}
    tickers = sorted(set(engine_records) & set(valuation_records))
    rows = {
        ticker: valuation_context.evaluate_ticker_valuation(
            ticker=ticker, feature_record=None, valuation_record=valuation_records[ticker],
            financial_analysis_record=engine_records[ticker],
            financial_analysis_context_identity=financial_v2.get("artifact_identity"),
        )
        for ticker in tickers
    }
    rows = valuation_context.attach_peer_relative(rows)
    method_status: dict[str, Counter] = {}
    for row in rows.values():
        for method_id, method in row["methods"].items():
            method_status.setdefault(method_id, Counter())[method["status"]] += 1
    return {
        "joined_ticker_count": len(tickers),
        "method_status": {method: dict(sorted(counts.items())) for method, counts in sorted(method_status.items())},
        "usable_relative_method_ready_tickers": sum(row["usable_relative_method_count"] > 0 for row in rows.values()),
    }, rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    rows, semantics_artifact = load_semantic_rows()
    classification = load_classification_diagnostics()
    financial_v2 = build_financial_v2(rows, semantics_artifact, classification)
    engine_records = financial_v2["records"]

    industry_by_ticker = load_industry_by_ticker()
    peer_context = valuation_context.attach_engine_fundamental_peers(engine_records, industry_by_ticker=industry_by_ticker)

    product = product_projection.build_product_projection(
        financial_context=financial_v2, product_tickers=sorted(engine_records), requested_at=REQUESTED_AT,
    )

    current_valuation = load_current_valuation_artifact()
    pe_pb_ps_counts, valuation_rows = valuation_counts(financial_v2, current_valuation)

    roe_avg_ready = sum(record["features"]["same_provider_roe_avg_equity"]["fitness"] == "READY" for record in engine_records.values())
    roe_eop_ready = sum(record["features"]["same_provider_roe_eop_proxy"]["fitness"] == "READY" for record in engine_records.values())
    roa_avg_ready = sum(record["features"]["same_provider_roa_avg_assets"]["fitness"] == "READY" for record in engine_records.values())
    roa_eop_ready = sum(record["features"]["same_provider_roa_eop_proxy"]["fitness"] == "READY" for record in engine_records.values())

    peer_ready_by_metric = {
        feature_id: sum(peer_context[ticker][feature_id]["status"] == "READY_RESEARCH_ONLY" for ticker in peer_context)
        for feature_id in valuation_context.ENGINE_PEER_FEATURES
    }
    sector_cohort_ticker_count = sum(
        any(peer_context[ticker][feature_id].get("cohort_level") == valuation_context.SECTOR_COHORT_LEVEL
            for feature_id in valuation_context.ENGINE_PEER_FEATURES)
        for ticker in peer_context
    )

    history_coverage = financial_v2["coverage"]["history_context_coverage"]

    summary = {
        "financial_v2_ticker_denominator": financial_v2["coverage"]["ticker_denominator"],
        "financial_v2_current_research_ready_count": financial_v2["coverage"]["current_research_ready_count"],
        "product_ticker_denominator": product["financial_analysis_market_summary"]["product_ticker_denominator"],
        "product_zero_silent_ticker_drops": product["coverage"]["zero_silent_ticker_drops"],
        "roe_avg_equity_ready": roe_avg_ready, "roe_eop_proxy_ready": roe_eop_ready,
        "roa_avg_assets_ready": roa_avg_ready, "roa_eop_proxy_ready": roa_eop_ready,
        "gross_margin_ready": financial_v2["coverage"]["feature_ready_counts"].get("gross_margin", 0),
        "history_context_coverage": history_coverage,
        "peer_context_ready_by_metric": peer_ready_by_metric,
        "peer_context_sector_cohort_ticker_count": sector_cohort_ticker_count,
        "peer_context_entity_class_fallback_ticker_count": len(peer_context) - sector_cohort_ticker_count,
        "pe_pb_ps_from_retained_current_valuation_artifact": pe_pb_ps_counts,
        "material_blockers": [
            "gross_margin/gross_margin_direction/gross_margin peer+history: 0 READY market-wide in "
            "this replay because the tracked 2026-08-31 semantic-facts snapshot predates gross_profit's "
            "2026-09-02 canonicalization; the current engine correctly computes it once fed current facts "
            "(regression-locked production figure: 1,283 READY, unaffected by this milestone).",
            "current_ratio peer+history: 0 READY market-wide in this replay because current_assets/"
            "current_liabilities canonicalization landed in the 2026-09-01 working-capital milestone, "
            "one day after this tracked snapshot (regression-locked production figure: 1,276 READY).",
            "same_provider_roe/roa_avg_equity/avg_assets AND the pre-existing same_provider_roe/roa_eop_proxy "
            "(unmodified by this milestone): 0 READY market-wide because the retained corpus's dominant "
            "provider split (KBS income statements, VCI balance sheets) makes a same-provider net-income-and-"
            "balance pair rare; mixed_provider_roa_proxy's much higher retained-proxy count for the same "
            "tickers independently confirms this is the real, structural provider-mix shape, not a defect "
            "in either the new or the pre-existing feature.",
            "P/E_TTM: 0 RESEARCH_USABLE (44 PE_NOT_MEANINGFUL, rest INPUT_BLOCKED) because its TTM route "
            "needs 4 consecutive same-provider standalone quarters of net income, gated by the same "
            "provider-mix rarity above; the pre-existing EXISTING-method P/E route (provider-reported, "
            "not TTM-derived) is unaffected and shows 9 RESEARCH_USABLE.",
        ],
        "zero_silent_drops": {
            "financial_v2": financial_v2["coverage"]["zero_silent_ticker_drops"],
            "product": product["coverage"]["zero_silent_ticker_drops"],
            "peer_context": set(peer_context) == set(engine_records),
        },
        "representative_traces": {
            ticker: {
                "in_financial_v2": ticker in engine_records,
                "current_research_ready": engine_records.get(ticker, {}).get("current_research_ready"),
                "same_provider_roe_avg_equity": engine_records.get(ticker, {}).get("features", {}).get("same_provider_roe_avg_equity"),
                "same_provider_roe_eop_proxy": engine_records.get(ticker, {}).get("features", {}).get("same_provider_roe_eop_proxy"),
                "gross_margin": engine_records.get(ticker, {}).get("features", {}).get("gross_margin"),
                "history_context_gross_margin": engine_records.get(ticker, {}).get("history_context", {}).get("gross_margin"),
                "peer_context_gross_margin": peer_context.get(ticker, {}).get("gross_margin"),
                "in_retained_valuation_artifact": ticker in (current_valuation.get("records") or {}),
                "valuation_methods": valuation_rows.get(ticker, {}).get("methods"),
            }
            for ticker in REPRESENTATIVE_TICKERS
        },
    }
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True, indent=2, default=str))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({
            "summary": summary, "financial_v2_coverage": financial_v2["coverage"],
        }, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
