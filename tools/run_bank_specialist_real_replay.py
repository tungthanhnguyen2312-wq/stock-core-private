#!/usr/bin/env python3
"""Real-data replay for BANK_SPECIALIST_FINANCIAL_RESEARCH_FOUNDATION_V1.

Read-only.  Never calls TCBS or any live provider (owner rule for this
milestone).  Reports, against currently retained data only:

  1. The real bank ticker denominator (layered entity-classification authority).
  2. Which canonical_metric values the real retained semantic facts actually
     carry for those tickers -- proving whether any bank-specific raw
     component (customer loan, deposit, NPL, provision, opex/income split)
     is already canonicalized (expected: no, per config/financial_item_map.csv).
  3. The real bank_financial_research_component/v1 observation count (0 --
     no importer exists yet; this milestone does not add one).
  4. Real per-feature fitness for the six bank specialist features, run
     through the actual engine over the real bank tickers with the real
     (empty) bank_components input.

No network, no runtime DB write, no primary-checkout write.
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import financial_analysis_engine_v2 as engine  # noqa: E402
from entity_classification_contract import load_layered_entity_profiles  # noqa: E402

DEFAULT_SEMANTIC_ROWS = ROOT / "operations-review" / "market-wide-structured-financial-period-semantics-v1-20260831" / "structured_financial_period_semantics_facts.jsonl.gz"


def _rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    profiles = load_layered_entity_profiles()
    bank_tickers = sorted(ticker for ticker, entity_type in profiles.items() if entity_type == "bank")

    rows = _rows(DEFAULT_SEMANTIC_ROWS)
    bank_rows = [row for row in rows if str(row.get("ticker") or "").upper() in bank_tickers]
    real_metric_coverage = dict(sorted(Counter(row.get("canonical_metric") for row in bank_rows).items()))

    required_bank_metric_ids = sorted(
        {engine._CUSTOMER_LOAN, engine._DEPOSIT, engine._NON_PERFORMING_LOAN, engine._PROVISION,
         engine._OPERATION_EXPENSE, engine._TOTAL_OPERATION_INCOME, engine._NET_INTEREST_MARGIN_PROVIDER}
    )
    present_required = sorted(set(required_bank_metric_ids) & set(real_metric_coverage))

    # Real bank_financial_research_component/v1 observation count: no importer
    # exists yet (owner rule for this milestone: no live TCBS acquisition), so
    # this is architecturally 0, not a placeholder.
    real_bank_components: list[dict] = []

    artifact = engine.build_artifact(
        tickers=bank_tickers, rows=bank_rows,
        issuer_types={ticker: "bank" for ticker in bank_tickers},
        source_identities={"semantic_rows_path": str(DEFAULT_SEMANTIC_ROWS.relative_to(ROOT))},
        requested_at="2026-09-01T00:00:00+07:00",
        bank_components=real_bank_components,
    )

    usable_counts = {
        feature_id: sum(artifact["records"][ticker]["features"][feature_id]["fitness"] == "READY" for ticker in bank_tickers)
        for feature_id in engine.BANK_FEATURE_IDS
    }
    fitness_by_feature = {
        feature_id: dict(sorted(Counter(artifact["records"][ticker]["features"][feature_id]["fitness"] for ticker in bank_tickers).items()))
        for feature_id in engine.BANK_FEATURE_IDS
    }

    report = {
        "milestone": "BANK_SPECIALIST_FINANCIAL_RESEARCH_FOUNDATION_V1",
        "replay_kind": "REAL_RETAINED_DATA_ONLY_NO_LIVE_PROVIDER_CALL",
        "bank_ticker_denominator": len(bank_tickers),
        "bank_tickers": bank_tickers,
        "semantic_rows_path": str(DEFAULT_SEMANTIC_ROWS.relative_to(ROOT)),
        "bank_row_count_in_semantic_rows": len(bank_rows),
        "real_canonical_metric_coverage_for_bank_tickers": real_metric_coverage,
        "required_bank_raw_metric_ids": required_bank_metric_ids,
        "required_bank_raw_metric_ids_present_in_real_canonical_facts": present_required,
        "real_bank_financial_research_component_observation_count": len(real_bank_components),
        "bank_feature_fitness_distribution": fitness_by_feature,
        "bank_feature_usable_ready_counts": usable_counts,
        "financial_v2_zero_silent_ticker_drops": artifact["coverage"]["zero_silent_ticker_drops"],
        "disposition": ("CAPABILITY_IMPLEMENTED / REAL_DATA_COVERAGE_ZERO_OR_PARTIAL_BY_INPUT"
                        if not present_required else "CAPABILITY_IMPLEMENTED / PARTIAL_REAL_COVERAGE_FOUND"),
        "network_used": False, "runtime_or_primary_write": False, "tcbs_called": False,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
