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
import market_wide_current_fundamental_research as research

DEFAULT_HISTORICAL_SCALEOUT = ROOT / (
    "operations-review/market-wide-historical-fundamentals-scaleout-v1-20260828/artifact.json"
)


def _facts(root: Path, ticker: str) -> list[dict]:
    path = root / f"{ticker}.jsonl.gz"
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def execute(*, requested_at: str = "2026-08-28T00:00:00+07:00") -> dict:
    # The prior residual-zero historical scaleout is the current consumer-owned universe and
    # entity-class authority.  Reusing its retained artifact avoids recomputing P3-F13 and keeps
    # this semantic replay strictly a transform over existing retained inputs.
    historical = json.loads(DEFAULT_HISTORICAL_SCALEOUT.read_text(encoding="utf-8"))
    base_records = historical["consumer_artifact"]["records"]
    tickers = sorted(base_records)
    entities = {ticker: record.get("entity_class") for ticker, record in base_records.items()}
    facts_by_ticker = {ticker: _facts(research.DEFAULT_CANONICAL_FACTS_ROOT, ticker) for ticker in tickers}
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
        "historical_scaleout": historical.get("artifact_identity"),
        "canonical_facts_root": str(research.DEFAULT_CANONICAL_FACTS_ROOT),
    }
    artifact.update(bridge.content_identity(artifact))
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--requested-at", default="2026-08-28T00:00:00+07:00")
    args = parser.parse_args()
    artifact = execute(requested_at=args.requested_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact["coverage"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
