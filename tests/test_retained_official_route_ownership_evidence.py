"""Focused unit tests for Retained Official Route Ownership Evidence Acquisition V1."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from official_financial_source_route_discovery import (
    discover_and_qualify_routes,
    ROUTE_STATUS_OWNERSHIP_QUALIFIED,
    ROUTE_STATUS_EVIDENCE_MISSING,
    VALIDATION_COHORT_17,
)
from retained_official_route_ownership_evidence import (
    execute,
    build_retained_evidence_records,
    OFFLINE_RETAINED_EVIDENCE_CATALOG,
    TECHNICAL_FAILURE_DISPOSITIONS,
    EVIDENCE_STORE_DIR,
)


ROOT = Path(__file__).resolve().parents[1]


class TestRetainedOfficialRouteOwnershipEvidence(unittest.TestCase):
    def setUp(self) -> None:
        self.artifact = execute()

    def test_retained_bytes_hashed_and_correspond_to_objects(self) -> None:
        records = build_retained_evidence_records()
        self.assertEqual(len(records), 10)

        for rec in records:
            file_path = ROOT / rec["retained_file_path"]
            self.assertTrue(file_path.is_file(), f"Missing file: {file_path}")

            raw_bytes = file_path.read_bytes()
            computed_sha = hashlib.sha256(raw_bytes).hexdigest()

            # Prove that evidence SHA corresponds exactly to the on-disk bytes
            self.assertEqual(computed_sha, rec["raw_document_sha256"])
            self.assertEqual(len(raw_bytes), rec["content_bytes_length"])
            self.assertGreater(rec["content_bytes_length"], 0)

    def test_assertion_without_retained_bytes_fails_qualification(self) -> None:
        registry = json.loads((ROOT / "config" / "official_source_registry.json").read_text(encoding="utf-8"))

        # Fake record with no real SHA
        fake_records = [{
            "canonical_instrument": "MWG",
            "issuer_legal_identity": "CTCP Đầu tư Thế giới Di động",
            "source_id": "issuer_ir",
            "route_class": "issuer_ir",
            "candidate_locator": "https://mwg.vn",
            "profile_locator": "https://mwg.vn",
            "raw_document_sha256": "not_a_valid_sha256",  # invalid SHA
            "ownership_evidence": "retained_official_document_locator",
            "evidence_type": "statutory_corporate_registration_on_domain",
            "evidence_provenance": {"url": "https://mwg.vn"},
        }]

        res = discover_and_qualify_routes(
            cohort=["MWG"],
            registry=registry,
            retained_ownership_evidence=fake_records,
        )
        mwg_ir = next(r for r in res["route_evaluations"] if r["ticker"] == "MWG" and r["route_class"] == "issuer_ir")
        self.assertEqual(mwg_ir["route_status"], ROUTE_STATUS_EVIDENCE_MISSING)
        self.assertFalse(mwg_ir["route_approval_eligible"])

    def test_issuer_mismatch_fails_qualification(self) -> None:
        registry = json.loads((ROOT / "config" / "official_source_registry.json").read_text(encoding="utf-8"))
        records = build_retained_evidence_records()
        mwg_rec = dict(next(r for r in records if r["canonical_instrument"] == "MWG"))

        # Alter ticker to VIC while keeping MWG domain
        mwg_rec["canonical_instrument"] = "VIC"

        res = discover_and_qualify_routes(
            cohort=["VIC"],
            registry=registry,
            retained_ownership_evidence=[mwg_rec],
        )
        vic_ir = next(r for r in res["route_evaluations"] if r["ticker"] == "VIC" and r["route_class"] == "issuer_ir")
        self.assertEqual(vic_ir["route_status"], ROUTE_STATUS_EVIDENCE_MISSING)

    def test_domain_mismatch_fails_qualification(self) -> None:
        registry = json.loads((ROOT / "config" / "official_source_registry.json").read_text(encoding="utf-8"))
        records = build_retained_evidence_records()
        mwg_rec = dict(next(r for r in records if r["canonical_instrument"] == "MWG"))

        # Alter candidate locator to a third party domain
        mwg_rec["candidate_locator"] = "https://finance.vietstock.vn/MWG"

        res = discover_and_qualify_routes(
            cohort=["MWG"],
            registry=registry,
            retained_ownership_evidence=[mwg_rec],
        )
        mwg_ir = next(r for r in res["route_evaluations"] if r["ticker"] == "MWG" and r["route_class"] == "issuer_ir")
        self.assertEqual(mwg_ir["route_status"], ROUTE_STATUS_EVIDENCE_MISSING)

    def test_generic_exchange_host_alone_fails_qualification(self) -> None:
        registry = json.loads((ROOT / "config" / "official_source_registry.json").read_text(encoding="utf-8"))

        # No retained per-ticker exchange profile evidence
        res = discover_and_qualify_routes(
            cohort=["MWG", "ACB"],
            registry=registry,
            retained_ownership_evidence=(),
        )
        for r in res["route_evaluations"]:
            if r["route_class"] == "exchange_disclosure":
                self.assertEqual(r["route_status"], ROUTE_STATUS_EVIDENCE_MISSING)
                self.assertFalse(r["route_approval_eligible"])

    def test_ticker_specific_retained_exchange_evidence_can_qualify(self) -> None:
        registry = json.loads((ROOT / "config" / "official_source_registry.json").read_text(encoding="utf-8"))
        valid_exchange_record = {
            "canonical_instrument": "MWG",
            "issuer_legal_identity": "CTCP Đầu tư Thế giới Di động",
            "source_id": "hose",
            "route_class": "exchange_disclosure",
            "candidate_locator": "https://www.hsx.vn/Modules/Listed/Web/SymbolView?id=MWG",
            "profile_locator": "https://www.hsx.vn/Modules/Listed/Web/SymbolView?id=MWG",
            "raw_document_sha256": "7dbc4cffdf9cdbb9564cb1a134a66e74b34b7f9435b64c017d84fbb7eec03d52",
            "ownership_evidence": "retained_ticker_specific_exchange_profile",
            "evidence_type": "ticker_specific_exchange_profile",
            "evidence_provenance": {"url": "https://www.hsx.vn/Modules/Listed/Web/SymbolView?id=MWG"},
        }
        res = discover_and_qualify_routes(
            cohort=["MWG"],
            registry=registry,
            retained_ownership_evidence=[valid_exchange_record],
        )
        mwg_exchange = next(r for r in res["route_evaluations"] if r["ticker"] == "MWG" and r["route_class"] == "exchange_disclosure")
        self.assertEqual(mwg_exchange["route_status"], ROUTE_STATUS_OWNERSHIP_QUALIFIED)
        self.assertTrue(mwg_exchange["route_approval_eligible"])

    def test_technical_acquisition_errors_remain_non_authoritative(self) -> None:
        tf = self.artifact["retained_evidence_summary"]["technical_failures"]
        self.assertEqual(len(tf), 7)
        self.assertIn("VIC", tf)
        self.assertIn("ABB", tf)
        self.assertIn("AAS", tf)
        self.assertEqual(tf["AAS"]["failure_disposition"], "SSL_CERTIFICATE_VERIFICATION_FAILED")
        self.assertEqual(tf["ABB"]["failure_disposition"], "CONNECTION_TIMEOUT")
        self.assertEqual(tf["VIC"]["failure_disposition"], "HTTP_FORBIDDEN_403")

    def test_registry_not_mutated(self) -> None:
        gov = self.artifact["governance_separation"]
        self.assertTrue(gov["evidence_retained"])
        self.assertFalse(gov["registry_mutated"])
        self.assertFalse(gov["activation_promoted"])
        self.assertEqual(gov["financial_documents_acquired"], 0)
        self.assertEqual(gov["financial_facts_created"], 0)
        self.assertFalse(gov["fundamental_readiness_mutated"])

    def test_deterministic_replay_and_prior_zero_baseline(self) -> None:
        second_artifact = execute()
        self.assertEqual(self.artifact["artifact_sha256"], second_artifact["artifact_sha256"])

        # Prior zero baseline when no evidence supplied
        zero_res = discover_and_qualify_routes(
            cohort=VALIDATION_COHORT_17,
            retained_ownership_evidence=(),
        )
        self.assertEqual(zero_res["summary_counts"]["ownership_qualified_routes"], 0)
        self.assertEqual(zero_res["summary_counts"]["ownership_evidence_missing_routes"], 34)


if __name__ == "__main__":
    unittest.main()
