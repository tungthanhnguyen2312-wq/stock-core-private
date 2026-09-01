"""Materialize the Financial Analysis V2 compact product join.  No network."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from financial_analysis_product_projection import build_product_projection
from current_valuation_opportunity_integration import _decision_artifact, content_identity
from security_decision_context import build_ticker_decision
from investment_decision_workspace_projection import build_artifacts as build_workspace


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("ARTIFACT_NOT_OBJECT")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--financial-analysis-context", type=Path, required=True)
    parser.add_argument("--opportunity-context", type=Path, required=True)
    parser.add_argument("--decision-context", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--requested-at", default="2026-09-01T00:00:00+07:00")
    args = parser.parse_args()
    engine, opportunity, old_decision = load(args.financial_analysis_context), load(args.opportunity_context), load(args.decision_context)
    records = opportunity.get("records")
    if not isinstance(records, dict) or not records:
        raise ValueError("PRODUCT_OPPORTUNITY_RECORDS_INVALID")
    product = build_product_projection(financial_context=engine, product_tickers=sorted(records), requested_at=args.requested_at)
    updated_records = {ticker: {**record, "financial_analysis": product["records"][ticker]} for ticker, record in records.items()}
    updated_opportunity = dict(opportunity)
    updated_opportunity["requested_at"] = args.requested_at
    updated_opportunity["source_artifacts"] = {**dict(opportunity.get("source_artifacts") or {}),
                                                  "financial_analysis_product_integration": product["artifact_identity"]}
    updated_opportunity["records"] = updated_records
    # The historical compact opportunity surface is regenerated from the updated
    # records by the main integration path.  Here retain full records for the
    # validation join and recompute the contract identity deterministically.
    updated_opportunity.update(content_identity(updated_opportunity))
    baseline_decisions = {ticker: build_ticker_decision(record) for ticker, record in records.items()}
    decisions = {ticker: build_ticker_decision(record) for ticker, record in updated_records.items()}
    updated_decision = _decision_artifact(
        as_of_session=updated_opportunity["as_of_session"], requested_at=args.requested_at, records=decisions,
        source_artifacts=updated_opportunity["source_artifacts"], opportunity_identity=updated_opportunity["artifact_identity"],
    )
    baseline_distribution = {}
    for record in baseline_decisions.values():
        baseline_distribution[record["research_stance"]] = baseline_distribution.get(record["research_stance"], 0) + 1
    if updated_decision["coverage"]["research_stance_distribution"] != dict(sorted(baseline_distribution.items())):
        raise ValueError("FINANCIAL_ANALYSIS_STANCE_DISTRIBUTION_REGRESSION")
    workspace = build_workspace(opportunity_artifact=updated_opportunity, decision_artifact=updated_decision, requested_at=args.requested_at)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in (("financial_analysis_product_integration.json", product),
                        ("opportunity_context_artifact.json", updated_opportunity),
                        ("security_decision_context_artifact.json", updated_decision),
                        ("investment_decision_workspace_artifact.json", workspace)):
        (args.output_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"engine_denominator": engine.get("coverage", {}).get("ticker_denominator"),
                      "product_denominator": product["coverage"]["ticker_denominator"],
                      "compact_coverage": product["coverage"]["compact_coverage"],
                      "absent_coverage": product["coverage"]["absent_coverage"],
                      "stance_distribution": updated_decision["coverage"]["research_stance_distribution"],
                      "identities": {"product": product["artifact_identity"], "opportunity": updated_opportunity["artifact_identity"],
                                     "decision": updated_decision["artifact_identity"], "workspace": workspace["artifact_identity"]}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
