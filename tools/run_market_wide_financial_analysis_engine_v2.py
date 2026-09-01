"""Run Financial Analysis Engine V2 from retained rows and an explicit cohort.

Every input is read-only.  The caller supplies a legacy cohort artifact when it is
gitignored in the active worktree; no primary checkout or runtime path is mutated.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import financial_analysis_engine_v2 as engine  # noqa: E402

DEFAULT_ROWS = ROOT / "operations-review" / "market-wide-structured-financial-period-semantics-v1-20260831" / "structured_financial_period_semantics_facts.jsonl.gz"


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("FINANCIAL_ANALYSIS_INPUT_NOT_OBJECT")
    return value


def _rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _non_consecutive_standalone_pairs(rows: list[dict], tickers: set[str]) -> int:
    series: dict[tuple[str, str, str, str, str], set[tuple[int, int]]] = defaultdict(set)
    for row in rows:
        if row.get("ticker") not in tickers or row.get("period_semantic_state") != engine.FLOW_STANDALONE:
            continue
        # The historical reviewed diagnostic was the revenue Q3 -> Q1 candidate
        # set; net income is evaluated separately by the engine with the same
        # consecutive-quarter guard, not folded into this count.
        if row.get("canonical_metric") != "revenue" or not engine._row_usable(row, engine.FLOW_STANDALONE):
            continue
        key = engine._source_key(row)[:4] + (str(row.get("canonical_metric")),)
        quarter = engine._quarter(row.get("native_period_label"))
        if quarter:
            series[key].add(quarter)
    # The review anchor is specifically an observed Q3 -> following-Q1 gap.  Do
    # not inflate this diagnostic with unrelated sparse-history gaps.
    return sum(
        (year, 3) in periods and (year + 1, 1) in periods and (year, 4) not in periods
        for periods in series.values()
        for year, quarter in periods if quarter == 3
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-artifact", type=Path, required=True)
    parser.add_argument("--semantic-rows", type=Path, default=DEFAULT_ROWS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--requested-at", default="2026-09-01T00:00:00+07:00")
    args = parser.parse_args()
    if not args.cohort_artifact.is_file():
        raise SystemExit("FINANCIAL_ANALYSIS_COHORT_ARTIFACT_MISSING")
    if not args.semantic_rows.is_file():
        raise SystemExit("FINANCIAL_ANALYSIS_SEMANTIC_ROWS_MISSING")
    cohort = _read_json(args.cohort_artifact)
    records = cohort.get("records")
    if not isinstance(records, dict) or cohort.get("denominator") != len(records) or cohort.get("residual") != 0:
        raise SystemExit("FINANCIAL_ANALYSIS_COHORT_COVERAGE_INVALID")
    rows = _rows(args.semantic_rows)
    tickers = sorted(records)
    identities = {
        "cohort_artifact_identity": cohort.get("artifact_identity") or cohort.get("artifact_sha256"),
        "period_semantics_rows_sha256": __import__("hashlib").sha256(args.semantic_rows.read_bytes()).hexdigest(),
        "period_semantics_contract": "market_wide_structured_financial_period_semantics/v1",
    }
    artifact = engine.build_artifact(
        tickers=tickers, rows=rows,
        issuer_types={ticker: record.get("entity_class") for ticker, record in records.items()},
        source_identities=identities, requested_at=args.requested_at,
    )
    artifact["replay"] = {
        "cohort_selector": "LEGACY_HISTORICAL_FROZEN_523_V1",
        "non_consecutive_standalone_pair_rejected_count": _non_consecutive_standalone_pairs(rows, set(tickers)),
        "network_used": False, "runtime_or_primary_write": False,
    }
    artifact.update(engine.content_identity(artifact))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact_identity": artifact["artifact_identity"], "coverage": artifact["coverage"], "replay": artifact["replay"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
