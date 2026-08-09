"""Pillar A -> research projection proofs; all fixtures are pure and local."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import research_financial_fact_projection as projection  # noqa: E402
from ticker_capability import build_ticker_capability_matrix  # noqa: E402


def _fact(metric: str, *, status: str = "qualified", value=1, period: str = "2024",
          conflict: bool = False) -> dict:
    return {
        "ticker": "NEW", "canonical_metric": metric, "status": status, "value": value,
        "reporting_period": period, "period_type": "annual", "period_start": "2024-01-01",
        "period_end": "2024-12-31", "statement_family": "income_statement",
        "statement_scope": "consolidated", "currency": "VND", "scale": "units",
        "unit_authority": "official_citation_agreement", "warnings": [],
        "conflicts": [{"kind": "different_value"}] if conflict else [],
        "provider": "fixture", "source_observation_ids": [f"obs-{metric}"],
        "source_sha256": "abc", "citation_id": f"citation-{metric}", "evidence_id": f"evidence-{metric}",
        "fact_id": f"fact-{metric}", "identity_key": f"identity-{metric}",
        "contract_version": "fixture", "mapper_version": "fixture", "resolver_version": "fixture",
    }


class ResearchFinancialFactProjectionTests(unittest.TestCase):
    def test_full_qualified_corporate_set_is_admitted_with_provenance(self) -> None:
        facts = [_fact(metric) for metric in projection.CORPORATE_REQUIRED_METRICS]
        result = projection.build_projection("NEW", facts, entity_type="corporate", entity_authority="manual_profile")
        self.assertEqual(result["status"], "available")
        self.assertTrue(result["research_eligible"])
        self.assertEqual(result["selected_reporting_period"], "2024")
        self.assertEqual(len(result["research_financial_canonical"]["records"]), len(projection.CORPORATE_REQUIRED_METRICS))
        self.assertEqual(result["facts"][0]["provenance"]["fact_id"], "fact-cash_and_equivalents")
        self.assertEqual(result["facts"][0]["provenance"]["citation_id"], "citation-cash_and_equivalents")

    def test_provider_reported_is_visible_but_never_promoted(self) -> None:
        facts = [_fact(metric, status="provider_reported") for metric in projection.CORPORATE_REQUIRED_METRICS]
        result = projection.build_projection("NEW", facts, entity_type="corporate", entity_authority="manual_profile")
        self.assertEqual(result["status"], "provider_reported_only")
        self.assertFalse(result["research_eligible"])
        self.assertIsNone(result["facts"][0]["value"])
        self.assertTrue(result["facts"][0]["value_withheld"])
        self.assertIsNone(result["research_financial_canonical"])

    def test_conflict_and_missing_are_distinct_and_fail_closed(self) -> None:
        conflict = projection.build_projection("NEW", [_fact("net_income", status="conflicted", value=None, conflict=True)],
                                               entity_type="corporate", entity_authority="manual_profile")
        missing = projection.build_projection("NEW", [], entity_type="corporate", entity_authority="manual_profile")
        self.assertEqual(conflict["status"], "conflicted")
        self.assertFalse(conflict["research_eligible"])
        self.assertEqual(missing["status"], "unavailable")
        self.assertNotEqual(conflict["reason_codes"], missing["reason_codes"])

    def test_conflicted_required_identity_vetoes_qualified_sibling(self) -> None:
        facts = [_fact(metric) for metric in projection.CORPORATE_REQUIRED_METRICS]
        conflict = _fact("net_income", status="conflicted", value=None, conflict=True)
        conflict["fact_id"] = "conflicting-sibling"
        facts.append(conflict)

        result = projection.build_projection("NEW", facts, entity_type="corporate", entity_authority="manual_profile")

        self.assertEqual(result["status"], "conflicted")
        self.assertFalse(result["research_eligible"])
        self.assertIn("qualified_research_required_metric_identity_conflicted", result["reason_codes"])

    def test_null_is_not_zero_but_zero_is_preserved(self) -> None:
        zero = projection.build_projection("NEW", [_fact("net_income", value=0)], entity_type="corporate", entity_authority="manual_profile")
        null = projection.build_projection("NEW", [_fact("net_income", value=None)], entity_type="corporate", entity_authority="manual_profile")
        self.assertEqual(zero["facts"][0]["value"], 0)
        self.assertIsNone(null["facts"][0]["value"])
        self.assertFalse(zero["research_eligible"])
        self.assertFalse(null["research_eligible"])

    def test_known_unsupported_and_unknown_entities_remain_distinct(self) -> None:
        facts = [_fact("net_income")]
        unsupported = projection.build_projection("SSI", facts, entity_type="securities", entity_authority="manual_profile")
        unknown = projection.build_projection("POW", facts, entity_type="unknown", entity_authority="unknown")
        bank = projection.build_projection("VCB", facts, entity_type="bank", entity_authority="manual_profile")
        self.assertEqual(unsupported["status"], "not_applicable")
        self.assertEqual(unknown["status"], "unknown")
        self.assertEqual(bank["status"], "not_applicable")

    def test_existing_trusted_input_wins_over_pillar_a_projection(self) -> None:
        pillar = projection.build_projection("HPG", [_fact(metric) for metric in projection.CORPORATE_REQUIRED_METRICS],
                                              entity_type="corporate", entity_authority="manual_profile")
        existing = {"financial_canonical": {"status": "available", "records": [{"quality_state": "available", "value": 1}]}}
        selected = projection.select_research_source(existing, pillar)
        self.assertEqual(selected["selected_source"], "financial_canonical")

    def test_projection_is_deterministic_and_matrix_never_promotes_provider_reported(self) -> None:
        facts = [_fact(metric, status="provider_reported") for metric in projection.CORPORATE_REQUIRED_METRICS]
        first = projection.build_projection("NEW", facts, entity_type="corporate", entity_authority="manual_profile")
        second = projection.build_projection("NEW", copy.deepcopy(facts), entity_type="corporate", entity_authority="manual_profile")
        self.assertEqual(first, second)
        matrix = build_ticker_capability_matrix("NEW", {"entity_type": "corporate", "research_financial_fact_projection": first}, market_authority={})
        self.assertEqual(matrix["fundamental_data"]["pillar_a_research_projection"]["status"], "partial")
        self.assertFalse(matrix["is_actionable"])

    def test_conflict_family_reason_is_exposed_to_the_capability_matrix(self) -> None:
        fact = _fact("net_income", status="conflicted", value=None, conflict=True)
        fact["conflicts"] = [{"kind": "cash_flow_period_attribution_unverified"}]
        projected = projection.build_projection("NEW", [fact], entity_type="corporate", entity_authority="manual_profile")
        matrix = build_ticker_capability_matrix(
            "NEW", {"entity_type": "corporate", "research_financial_fact_projection": projected}, market_authority={},
        )
        capability = matrix["research"]["pillar_a_historical_research_eligibility"]
        self.assertIn("CANONICAL_CASH_FLOW_PERIOD_OR_SCOPE_UNVERIFIED", projected["reason_codes"])
        self.assertIn("CANONICAL_CASH_FLOW_PERIOD_OR_SCOPE_UNVERIFIED", capability["reason_codes"])
        self.assertFalse(matrix["is_actionable"])


if __name__ == "__main__":
    unittest.main()
