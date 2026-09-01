"""Replay retained canonical flow facts through the V1 semantic/TTM bridge."""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import financial_flow_semantics_ttm_bridge as bridge
import market_wide_financial_analysis_v2_scaleout as scaleout

DEFAULT_HISTORICAL_SCALEOUT = ROOT / (
    "operations-review/market-wide-historical-fundamentals-scaleout-v1-20260828/artifact.json"
)


def execute(*, semantic_rows: Path, feature_store_artifact: Path, feature_store_records: Path,
            classification_diagnostics: Path | None = None,
            requested_at: str = "2026-09-01T00:00:00+07:00") -> dict:
    """Replay the current 1,492 structured-financial universe; no historical 523 selector."""
    records, _ = scaleout.load_feature_store(feature_store_artifact, feature_store_records)
    entities = {ticker: record.get("entity_type") for ticker, record in records.items()}
    if classification_diagnostics:
        diagnostics = json.loads(classification_diagnostics.read_text(encoding="utf-8"))
        for item in diagnostics.get("rows") or []:
            ticker, outcome = str(item.get("ticker") or "").upper(), item.get("outcome")
            if ticker in entities and outcome in {"corporate", "bank", "securities", "insurance", "finance_company"}:
                entities[ticker] = outcome
    with gzip.open(semantic_rows, "rt", encoding="utf-8") as handle:
        source_rows = [json.loads(line) for line in handle if line.strip()]
    facts_by_ticker = bridge.facts_from_structured_semantic_rows(source_rows)
    tickers = sorted(records)
    artifact = bridge.build_artifact(tickers=tickers, facts_by_ticker=facts_by_ticker,
                                     entity_type_by_ticker=entities, requested_at=requested_at)
    artifact["consumer_attachment"] = {
        "attached_ticker_count": len(artifact["records"]),
        "ttm_ready_ticker_count": sum(bool(row.get("ttm")) for row in artifact["records"].values()),
        "attachment_mode": "READ_ONLY_FLOW_SEMANTICS_RESEARCH_CONTEXT",
        "authoritative_coverage_unchanged": True,
        "valuation_or_ranking_promoted": False,
    }
    artifact["source_artifacts"] = {
        "structured_semantic_rows": str(semantic_rows),
        "feature_store_artifact": str(feature_store_artifact),
        "full_universe_only": True,
    }
    # The bridge uses integer depth buckets in coverage.  Normalize them to the exact
    # JSON representation before sealing the persisted artifact identity.
    artifact = json.loads(json.dumps(artifact, ensure_ascii=False, sort_keys=True))
    artifact.update(bridge.content_identity(artifact))
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--semantic-rows", type=Path, required=True)
    parser.add_argument("--feature-store-artifact", type=Path, required=True)
    parser.add_argument("--feature-store-records", type=Path, required=True)
    parser.add_argument("--classification-diagnostics", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--requested-at", default="2026-09-01T00:00:00+07:00")
    args = parser.parse_args()
    artifact = execute(semantic_rows=args.semantic_rows, feature_store_artifact=args.feature_store_artifact,
                       feature_store_records=args.feature_store_records, classification_diagnostics=args.classification_diagnostics,
                       requested_at=args.requested_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact["coverage"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
