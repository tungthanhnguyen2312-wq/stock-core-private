"""Comprehensive test suite for P1G — Final Data-Authority Bridge and Post-Close Closeout."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CONSUMER_ROOT = ROOT.parent / "ai-core-private"
sys.path.insert(0, str(CONSUMER_ROOT))

#: The session the retained runtime is anchored to. The share and price legs of this
#: section are both session-relative, so the tests state the session explicitly.
SESSION = "2026-07-30"


import official_source_registry as registry  # noqa: E402
import official_document_store as doc_store  # noqa: E402
import corporate_action_events as events  # noqa: E402
import official_corporate_action_ledger as ledger  # noqa: E402
import share_transition_bridge as share_bridge  # noqa: E402
import market_wide_calculation_readiness as readiness  # noqa: E402
from canonical_financial_bundle_section import attach  # noqa: E402
from builders.build_ticker_context import (  # noqa: E402
    canonical_financial_facts_contract,
    apply_bundle_canonical_financial_facts_contract,
)
from tools.operate_stocklookup import Operator  # noqa: E402


class WorkstreamA_SourceRegistryTests(unittest.TestCase):
    @staticmethod
    def _verifiable_registry() -> dict:
        """The shipped registry with the approval instant made verifiable, in memory only.

        B1's recorded `approved_at` has no clock provenance and is future-dated, so `admit()`
        refuses on it alone. Whether the owner meant 07:00Z or 14:00Z is not a question a test
        may answer, so this fixture asserts nothing about the real approval: it isolates the
        host, document-type and rate rules from the governance verdict.
        """
        loaded = registry.load_registry()
        loaded["approval_state"]["approved_at"] = "2026-08-03T07:00:00+00:00"
        loaded["approval_state"][registry.APPROVAL_PROVENANCE_FIELD] = "test fixture, UTC"
        return loaded

    def test_approved_sources_admit_valid_urls(self) -> None:
        """Workstream A: Approved sources pass admit(); undeclared hosts or types fail."""
        verifiable = self._verifiable_registry()
        res_hose = registry.admit("hose", "https://www.hsx.vn/notice.pdf",
                                  "corporate_action_notice", registry=verifiable)
        self.assertEqual(res_hose["decision"], registry.ADMITTED)
        self.assertEqual(res_hose["reason"], "admitted_by_registry")

        res_vsdc = registry.admit("vsdc", "https://vsdc.vn/notice.pdf",
                                  "last_registration_date_notice", registry=verifiable)
        self.assertEqual(res_vsdc["decision"], registry.ADMITTED)

        res_ir = registry.admit("issuer_ir", "https://file.hoaphat.com.vn/notice.pdf",
                                "corporate_action_notice", registry=verifiable)
        self.assertEqual(res_ir["decision"], registry.ADMITTED)

    def test_the_shipped_approval_instant_is_unverified_and_admits_nothing(self) -> None:
        verdict = registry.approval_instant_verdict()
        self.assertEqual(verdict["verdict"], registry.VERDICT_UNVERIFIED)
        decision = registry.admit("hose", "https://www.hsx.vn/notice.pdf",
                                  "corporate_action_notice")
        self.assertEqual(decision["decision"], registry.REFUSED)
        self.assertEqual(decision["reason"], registry.REASON_APPROVAL_TIMESTAMP)

        # Refused cases
        res_unapproved_host = registry.admit("hose", "https://evil-hsx.vn/notice.pdf", "corporate_action_notice")
        self.assertEqual(res_unapproved_host["decision"], registry.REFUSED)
        self.assertEqual(res_unapproved_host["reason"], registry.REASON_HOST_NOT_ALLOWED)

        res_unapproved_type = registry.admit("hose", "https://www.hsx.vn/notice.pdf", "unsupported_type")
        self.assertEqual(res_unapproved_type["decision"], registry.REFUSED)
        self.assertEqual(res_unapproved_type["reason"], registry.REASON_DOCUMENT_TYPE)


class WorkstreamB_DocumentStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_immutable_document_retention_and_deduplication(self) -> None:
        """Workstream B: Immutable content-addressed storage, deduplication, hash verification."""
        html_bytes = b"<!DOCTYPE html><html><body><p>HPG Corporate Action Notice</p></body></html>"
        html_path = self.root / "hpg_notice.html"
        html_path.write_bytes(html_bytes)

        result = doc_store.adopt_retained_document(
            self.root,
            html_path,
            ticker="HPG",
            document_type="corporate_action_notice",
            source_url="https://www.hsx.vn/hpg.html",
            source_authority="Ho Chi Minh City Stock Exchange",
            observed_at="2026-08-03T14:00:00Z",
            execute=True,
        )
        self.assertEqual(result["state"], "retained")
        self.assertEqual(result["record"]["retrieval_status"], doc_store.RETRIEVAL_ADOPTED)
        self.assertEqual(result["content_sha256"], doc_store.sha256_bytes(html_bytes))

        # Re-adopting identical bytes returns existing record without error
        result_dup = doc_store.adopt_retained_document(
            self.root,
            html_path,
            ticker="HPG",
            document_type="corporate_action_notice",
            source_url="https://www.hsx.vn/hpg.html",
            source_authority="Ho Chi Minh City Stock Exchange",
            observed_at="2026-08-03T14:00:00Z",
            execute=True,
        )
        self.assertEqual(result_dup["document_id"], result["document_id"])

        # Verification passes
        res_verify = doc_store.verify(self.root)
        self.assertTrue(res_verify["ok"])
        self.assertEqual(res_verify["checked"], 1)
        self.assertEqual(res_verify["findings"], [])


class WorkstreamC_EventLedgerTests(unittest.TestCase):
    def test_event_ledger_reconciliation_and_supersession(self) -> None:
        """Workstream C: Reconciles observations, supports event types, handles supersession."""
        obs1 = {
            "observation_id": "obs_hpg_div_1",
            "document_id": "doc1",
            "content_sha256": "hash1",
            "ticker": "HPG",
            "event_type": "stock_dividend",
            "lifecycle_state": "announced",
            "announcement_date": "2026-05-15",
            "shares_before": 7675465855,
            "shares_issued": 767498665,
            "stock_ratio": 0.0999937567,
            "source_authority": "Ho Chi Minh City Stock Exchange",
            "source_url": "https://www.hsx.vn/hpg1.html",
        }
        obs2 = {
            "observation_id": "obs_hpg_div_2",
            "document_id": "doc2",
            "content_sha256": "hash2",
            "ticker": "HPG",
            "event_type": "stock_dividend",
            "lifecycle_state": "executed",
            "ex_date": "2026-06-04",
            "record_date": "2026-06-05",
            "payment_or_execution_date": "2026-06-05",
            "shares_before": 7675465855,
            "shares_issued": 767498665,
            "shares_after": 8442964520,
            "stock_ratio": 0.0999937567,
            "source_authority": "Ho Chi Minh City Stock Exchange",
            "source_url": "https://www.hsx.vn/hpg2.html",
        }

        result = ledger.build_ledger([obs1, obs2])
        self.assertEqual(result["entry_count"], 1)
        entry = result["entries"][0]

        self.assertEqual(entry["ticker"], "HPG")
        self.assertEqual(entry["event_type"], "stock_dividend")
        self.assertEqual(entry["lifecycle_state"], "executed")
        self.assertEqual(entry["ex_date"], "2026-06-04")
        self.assertEqual(entry["qualification_state"], "qualified")
        self.assertEqual(entry["adjustment_factor_status"], ledger.FACTOR_READY)
        self.assertIsNotNone(entry["adjustment_factor"])


class WorkstreamD_DatedSharesTimelineTests(unittest.TestCase):
    def test_hpg_and_vnm_share_timelines(self) -> None:
        """Workstream D: Evaluates dated shares timeline across events and fail-closed cases."""
        opening_hpg = {
            "effective_date": "2026-06-03",
            "value": 7675465855,
            "unit": "shares",
            "share_class": "common_outstanding",
            "identity_scope": "issuer",
            "qualification": "qualified",
            "citation_id": "cite_hpg_pre_div",
            "source_hash": "hash_hpg_pre_div",
        }
        event_hpg = {
            "event_id": "evt_hpg_stock_div",
            "action_type": "stock_dividend",
            "effective_date": "2026-06-04",
            "qualification": "qualified",
            "lifecycle": "completed",
            "resulting_identity_type": "common_outstanding_shares",
            "unit": "shares",
            "identity_scope": "issuer",
            "opening_shares": 7675465855,
            "resulting_shares": 8442964520,
            "citation_id": "cite_hpg_div",
            "source_hash": "hash_hpg_div",
        }

        res_hpg = share_bridge.resolve_share_transition(
            opening=opening_hpg,
            events=[event_hpg],
            target_date="2026-07-30",
            coverage_through="2026-07-30",
        )
        self.assertEqual(res_hpg["current_shares"]["value"], 8442964520)

        # Insufficient evidence case fails closed
        unqualified_opening = dict(opening_hpg, qualification="provisional")
        res_fail = share_bridge.resolve_share_transition(
            opening=unqualified_opening,
            events=[event_hpg],
            target_date="2026-07-30",
            coverage_through=None,
        )
        self.assertEqual(res_fail["status"], "blocked")


class WorkstreamE_AdjustmentFactorsTests(unittest.TestCase):
    def test_adjustment_factor_strict_ex_date_requirement(self) -> None:
        """Workstream E: Factors emitted only with explicit ex-date; missing ex-date yields NOT_READY."""
        obs_no_ex_date = {
            "observation_id": "obs_no_ex",
            "document_id": "doc1",
            "content_sha256": "hash1",
            "ticker": "HPG",
            "event_type": "stock_dividend",
            "lifecycle_state": "executed",
            "record_date": "2026-06-05",
            "shares_before": 7675465855,
            "shares_issued": 767498665,
            "shares_after": 8442964520,
            "stock_ratio": 0.0999937567,
        }
        res = ledger.build_ledger([obs_no_ex_date])
        entry = res["entries"][0]
        self.assertEqual(entry["adjustment_factor_status"], ledger.FACTOR_NOT_READY)
        self.assertIn("missing_explicit_official_ex_date", entry["adjustment_factor_blocked_by"])


class WorkstreamF_ValuationReadinessTests(unittest.TestCase):
    def test_valuation_readiness_distinguishes_authorities(self) -> None:
        """Workstream F: Computes market-wide readiness counts while distinguishing authorities."""
        res_ticker = readiness.evaluate_ticker("HPG", [], {"metric_applicability": {}})
        self.assertIn("still_blocked_by_price_basis", res_ticker)
        self.assertEqual(res_ticker["ticker"], "HPG")


class WorkstreamG_ProducerConsumerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_root = ROOT.parent / "dashboard-runtime"

    def test_producer_to_consumer_exact_pass_through(self) -> None:
        """Workstream G: Verifies Producer section attached and Consumer preserves it verbatim."""
        bundle_entries = {
            "HPG": {"company_name": "Hoa Phat Group"},
            "VCB": {"company_name": "Vietcombank"},
        }
        attached = attach(bundle_entries, self.runtime_root, include=True, session_date=SESSION)
        bundle = {"schema_version": "1.0.0", "tickers": attached}

        context_hpg = {"ticker": "HPG", "provenance": []}
        apply_bundle_canonical_financial_facts_contract(context_hpg, bundle)
        self.assertEqual(context_hpg["canonical_financial_facts"], attached["HPG"]["canonical_financial_facts"])

        context_vcb = {"ticker": "VCB", "provenance": []}
        apply_bundle_canonical_financial_facts_contract(context_vcb, bundle)
        self.assertEqual(context_vcb["canonical_financial_facts"], attached["VCB"]["canonical_financial_facts"])


class WorkstreamH_OperatorIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_root = ROOT.parent / "dashboard-runtime"

    def _operator(self, **kwargs) -> Operator:
        params = {"root": self.runtime_root, "tickers": ["HPG", "VNM", "VCB"],
                  "execute": False, "publish": False, "live": False}
        params.update(kwargs)
        return Operator(**params)

    def test_operator_dry_run_executes_all_stages(self) -> None:
        """Workstream H: the post-close dry run reaches its plan on the live runtime.

        Without the canonical-financial-facts flag no share count reaches the export, so the
        share observation's age cannot affect the artifact and the run proceeds.
        """
        operator = self._operator()
        self.assertEqual(operator.run(), 0)
        self.assertTrue(any(step["step"] == "dry_run_plan" and step["status"] == "passed"
                            for step in operator.steps))

    def test_the_dry_run_refuses_lagged_shares_that_would_enter_the_export(self) -> None:
        """The live runtime's share observation is older than its session, which is exactly
        the case the freshness contract exists to catch."""
        operator = self._operator(include_canonical_financial_facts=True)
        self.assertEqual(operator.run(), 1)
        failure = next(step for step in operator.steps if step["status"] == "failed")
        self.assertEqual(failure["step"], "preflight_share_freshness")
        self.assertGreater(failure["provider_reported_lagged_count"], 0)
        self.assertLess(failure["shares_observation_date"], failure["reference_session"])


if __name__ == "__main__":
    unittest.main()
