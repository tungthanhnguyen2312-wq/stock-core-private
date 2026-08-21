"""Focused unit tests for Official Financial Source Route Discovery V1."""
from __future__ import annotations

import unittest
from pathlib import Path

from official_financial_source_route_discovery import (
    execute,
    discover_and_qualify_routes,
    normalize_domain,
    ROUTE_STATUS_OWNERSHIP_QUALIFIED,
    ROUTE_STATUS_DISCOVERED_UNQUALIFIED,
    ROUTE_STATUS_REJECTED,
    ROUTE_STATUS_NOT_FOUND,
    VALIDATION_COHORT_17,
)


ROOT = Path(__file__).resolve().parents[1]


class TestOfficialFinancialSourceRouteDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        self.artifact = execute()

    def test_deterministic_discovery_artifact_identity(self) -> None:
        second_artifact = execute()
        self.assertEqual(self.artifact["artifact_sha256"], second_artifact["artifact_sha256"])
        self.assertEqual(self.artifact["artifact_identity"], second_artifact["artifact_identity"])

    def test_candidate_route_normalization(self) -> None:
        self.assertEqual(normalize_domain("https://www.mwg.vn/ir"), "www.mwg.vn")
        self.assertEqual(normalize_domain("http://vingroup.net:8080/path"), "vingroup.net")
        self.assertEqual(normalize_domain("techcombank.com/about"), "techcombank.com")
        self.assertEqual(normalize_domain(""), "")
        self.assertEqual(normalize_domain(None), "")

    def test_issuer_identity_and_cohort_preservation(self) -> None:
        cohort = self.artifact["validation_cohort_identity"]
        self.assertEqual(cohort["candidate_count"], 17)
        self.assertEqual(tuple(cohort["members"]), tuple(sorted(VALIDATION_COHORT_17)))

        evals = self.artifact["route_evaluations"]
        self.assertEqual(len(evals), 34)  # 17 exchange + 17 IR

        tickers_evaluated = {r["ticker"] for r in evals}
        self.assertEqual(tickers_evaluated, set(VALIDATION_COHORT_17))

        for r in evals:
            self.assertTrue(bool(r["legal_issuer_identity"]))
            self.assertIn(r["route_class"], {"exchange_disclosure", "issuer_ir"})

    def test_valid_ownership_evidence(self) -> None:
        evals = self.artifact["route_evaluations"]
        qualified = [r for r in evals if r["route_status"] == ROUTE_STATUS_OWNERSHIP_QUALIFIED]

        # 17 exchange routes + 11 IR routes = 28 qualified
        self.assertEqual(len(qualified), 28)

        # Check exchange route proof
        mwg_exchange = next(r for r in qualified if r["ticker"] == "MWG" and r["route_class"] == "exchange_disclosure")
        self.assertIn("Official HOSE listing record", mwg_exchange["ownership_evidence_span"])
        self.assertTrue(mwg_exchange["route_approval_eligible"])

        # Check IR route proof
        mwg_ir = next(r for r in qualified if r["ticker"] == "MWG" and r["route_class"] == "issuer_ir")
        self.assertIn("0303270651", mwg_ir["ownership_evidence_span"])
        self.assertEqual(mwg_ir["probe_status"], "ACCESSIBLE")
        self.assertTrue(mwg_ir["route_approval_eligible"])

    def test_insufficient_ownership_evidence_and_fail_closed_rejections(self) -> None:
        evals = self.artifact["route_evaluations"]
        rejected = [r for r in evals if r["route_status"] == ROUTE_STATUS_REJECTED]
        self.assertEqual(len(rejected), 6)

        rejected_map = {r["ticker"]: r for r in rejected}
        self.assertEqual(rejected_map["AAS"]["probe_status"], "SSL_CERTIFICATE_MISMATCH")
        self.assertEqual(rejected_map["ABB"]["probe_status"], "TIMEOUT")
        self.assertEqual(rejected_map["AAV"]["probe_status"], "CONNECTION_REFUSED")
        self.assertEqual(rejected_map["AAH"]["probe_status"], "DNS_RESOLUTION_FAILED")
        self.assertEqual(rejected_map["AAN"]["probe_status"], "DNS_RESOLUTION_FAILED")
        self.assertEqual(rejected_map["ACC"]["probe_status"], "DNS_RESOLUTION_FAILED")

        for r in rejected:
            self.assertFalse(r["route_approval_eligible"])
            self.assertTrue(len(r["blockers"]) > 0)

    def test_third_party_route_rejection_and_search_engine_not_authority(self) -> None:
        prohibited = self.artifact["prohibited_source_classes"]
        self.assertIn("search_engine_results_pages", prohibited)
        self.assertIn("third_party_financial_portals", prohibited)
        self.assertIn("broker_trading_platforms", prohibited)
        self.assertIn("unverified_document_mirrors", prohibited)

        # Ensure no route candidate is from a third-party class
        for r in self.artifact["route_evaluations"]:
            self.assertNotIn(r["route_class"], prohibited)

    def test_discovery_not_activation(self) -> None:
        gov = self.artifact["governance_separation"]
        self.assertTrue(gov["discovery_performed"])
        self.assertFalse(gov["registry_mutated"])
        self.assertFalse(gov["activation_promoted"])
        self.assertEqual(gov["financial_documents_acquired"], 0)
        self.assertEqual(gov["financial_facts_created"], 0)
        self.assertFalse(gov["fundamental_readiness_mutated"])

        candidates = self.artifact["governed_registry_candidates"]
        self.assertEqual(len(candidates), 11)
        for gc in candidates:
            self.assertEqual(gc["activation_recommendation"], "PENDING_OWNER_PROMOTION_REVIEW")

    def test_authority_boundaries(self) -> None:
        boundaries = self.artifact["authority_boundaries"]
        self.assertFalse(boundaries["new_provider_added"])
        self.assertFalse(boundaries["source_authority_promoted"])
        self.assertFalse(boundaries["canonical_store_mutated"])
        self.assertFalse(boundaries["runtime_database_mutated"])
        self.assertFalse(boundaries["raw_as_traded_promoted"])
        self.assertFalse(boundaries["liquidity_sizing_promoted"])
        self.assertFalse(boundaries["valuation_or_recommendation_produced"])
        self.assertFalse(boundaries["p3g_started"])

    def test_verdict_and_next_gate(self) -> None:
        self.assertEqual(self.artifact["verdict"], "OFFICIAL_SOURCE_ROUTE_DISCOVERY_V1_READY")
        self.assertEqual(self.artifact["next_gate"], "GOVERNED_OFFICIAL_SOURCE_REGISTRY_ACTIVATION_REVIEW")


if __name__ == "__main__":
    unittest.main()
