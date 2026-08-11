"""Request-scoped Pillar A shard reuse without changing projection semantics."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import export_ai_bundle as exporter  # noqa: E402


class PillarARequestScopedCacheTests(unittest.TestCase):
    def test_each_canonical_shard_is_read_once_across_projection_and_summaries(self) -> None:
        state = {"tickers": [
            {"ticker": "VNM", "issuer_entity_type": "corporate", "archetype_authority": "manual_profile"},
            {"ticker": "HPG", "issuer_entity_type": "corporate", "archetype_authority": "manual_profile"},
        ]}
        reads: list[str] = []

        def read_facts(_root: Path, ticker: str) -> list[dict]:
            reads.append(ticker)
            return [{"ticker": ticker, "fact_id": f"{ticker}-canonical"}]

        def projection(ticker: str, facts: list[dict], **_kwargs) -> dict:
            return {"ticker": ticker, "fact_ids": [fact["fact_id"] for fact in facts], "research_eligible": False}

        def coverage_summary(records: list[dict], facts_for, **_kwargs) -> dict:
            return {"coverage": {record["ticker"]: [fact["fact_id"] for fact in facts_for(record["ticker"])] for record in records}}

        def conflict_summary(records: list[dict], facts_for) -> dict:
            return {"conflicts": {record["ticker"]: [fact["fact_id"] for fact in facts_for(record["ticker"])] for record in records}}

        entries = {"VNM": {"financial_canonical": {"status": "available"}}}
        observed_stages: list[tuple[str, str | None]] = []
        with patch("canonical_fact_store._load_state", return_value=state), \
             patch("canonical_fact_store.read_facts", side_effect=read_facts), \
             patch("official_annual_financial_fact_projection.facts_for_ticker", return_value=[]), \
             patch("financial_entity_applicability.load_entity_profiles", return_value={}), \
             patch.object(exporter, "load_evidence_index", return_value={}), \
             patch.object(exporter, "build_research_financial_fact_projection", side_effect=projection), \
             patch.object(exporter, "research_financial_coverage_summary", side_effect=coverage_summary), \
             patch.object(exporter, "canonical_conflict_coverage_summary", side_effect=conflict_summary):
            result = exporter.attach_pillar_a_research_projection(
                entries, Path("runtime"), True,
                stage_observer=lambda stage, ticker, _elapsed: observed_stages.append((stage, ticker)),
            )

        self.assertEqual(reads, ["VNM", "HPG"])
        self.assertEqual(entries["VNM"]["research_financial_fact_projection"]["fact_ids"], ["VNM-canonical"])
        self.assertEqual(result["coverage"]["VNM"], ["VNM-canonical"])
        self.assertEqual(result["conflict_decomposition"]["conflicts"]["HPG"], ["HPG-canonical"])
        self.assertEqual(observed_stages, [
            ("pillar_a_projection", "VNM"),
            ("pillar_a_coverage_conflict", None),
        ])


if __name__ == "__main__":
    unittest.main()
