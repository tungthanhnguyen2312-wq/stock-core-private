"""Generate Phase 5 canonical news mapping diagnostics for a ticker."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from news_ticker_mapping import (  # noqa: E402
    TickerAliasRegistry,
    load_config,
    map_articles,
    summarize_news,
)


MAP_FIELDS = ["news_id", "ticker", "match_method", "matched_alias", "confidence", "mapping_version"]


def build_diagnostic(ticker: str = "PAN") -> tuple[dict, list[dict]]:
    ticker = ticker.strip().upper()
    registry = TickerAliasRegistry.from_csv(ROOT / "config" / "ticker_aliases.csv")
    registry.add_metadata_aliases([{"ticker": ticker}])
    with (ROOT / "news_latest.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        articles = list(csv.DictReader(handle))
    config = load_config(ROOT / "config" / "news_mapping_config.json")
    mapped = map_articles(
        articles, registry,
        mapping_version=config["mapping_version"],
        auto_accept_confidence=float(config["auto_accept_confidence"]),
        candidate_confidence=float(config["candidate_confidence"]),
    )
    ticker_mappings = [row for row in mapped["accepted"] if row["ticker"] == ticker]
    summary = summarize_news(
        ticker, articles, registry,
        now=datetime.now(timezone.utc), config=config,
    )
    diagnostic = {
        "schema_version": "1.0.0",
        "ticker": ticker,
        "mapping_version": config["mapping_version"],
        "aliases": [
            {
                "alias": item.alias,
                "alias_type": item.alias_type,
                "priority": item.priority,
                "source": "manual" if item.alias_type != "ticker" else "metadata",
            }
            for item in registry.aliases if item.ticker == ticker
        ],
        "source_article_count": len(articles),
        "accepted_mapping_count": len(ticker_mappings),
        "candidate_review_count": summary["candidate_review_count"],
        "status": summary["status"],
        "company_news_count": summary["company_news_count"],
        "sector_news_count": summary["sector_news_count"],
        "market_news_count": summary["market_news_count"],
        "lookback_days": summary["lookback_days"],
        "cutoff": summary["cutoff"],
        "company_items": summary["items"],
        "sector_fallback_items": summary["sector_items"],
        "market_fallback_items": summary["market_items"],
        "policy": {
            "generic_uppercase_tokens_are_not_tickers": True,
            "sector_or_market_news_is_not_company_news": True,
            "low_confidence_matches_require_review": True,
        },
    }
    return diagnostic, ticker_mappings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="PAN")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--map-output", type=Path, required=True)
    args = parser.parse_args()
    diagnostic, mappings = build_diagnostic(args.ticker)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(diagnostic, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    args.map_output.parent.mkdir(parents=True, exist_ok=True)
    with args.map_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MAP_FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field) for field in MAP_FIELDS} for row in mappings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
