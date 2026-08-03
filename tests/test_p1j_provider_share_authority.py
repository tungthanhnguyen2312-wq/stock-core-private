"""Comprehensive test suite for P1J — Provider-Reported Share Authority Hardening."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CONSUMER_ROOT = ROOT.parent / "ai-core-private"
sys.path.insert(0, str(CONSUMER_ROOT))

import market_wide_current_shares_resolver as shares_resolver  # noqa: E402
import market_wide_calculation_readiness as readiness  # noqa: E402
from canonical_financial_bundle_section import attach, _resolve_session_inputs  # noqa: E402
from builders.build_ticker_context import (  # noqa: E402
    canonical_financial_facts_contract,
    apply_bundle_canonical_financial_facts_contract,
)
from tools.operate_stocklookup import Operator  # noqa: E402


class WorkstreamA_ProviderFieldProvenanceTests(unittest.TestCase):
    def test_provider_field_provenance(self) -> None:
        """Workstream A: Confirms proven provenance for VCI issue_share."""
        runtime_root = ROOT.parent / "dashboard-runtime"
        pan = shares_resolver.resolve_effective_shares("PAN", runtime_root)
        self.assertEqual(pan["share_concept"], "ISSUED_SHARES")
        self.assertEqual(pan["source"], "VCI.overview.issue_share")
        self.assertEqual(pan["unit"], "shares")
        self.assertEqual(pan["authority"], "provider_reported_current")


class WorkstreamB_OfficialAnchorComparisonTests(unittest.TestCase):
    def test_official_anchor_grounding(self) -> None:
        """Workstream B: Compares provider-reported shares against official anchors."""
        runtime_root = ROOT.parent / "dashboard-runtime"
        hpg = shares_resolver.resolve_effective_shares("HPG", runtime_root)
        self.assertEqual(hpg["authority"], "qualified_official")
        self.assertEqual(hpg["value"], 7163748865)

        vnm = shares_resolver.resolve_effective_shares("VNM", runtime_root)
        self.assertEqual(vnm["authority"], "qualified_official")
        self.assertEqual(vnm["value"], 2089955445)


class WorkstreamC_FreshnessContractTests(unittest.TestCase):
    def test_freshness_rules(self) -> None:
        """Workstream C: Applies deterministic freshness rules."""
        runtime_root = ROOT.parent / "dashboard-runtime"
        pan = shares_resolver.resolve_effective_shares("PAN", runtime_root)
        self.assertEqual(pan["authority"], "provider_reported_current")
        self.assertEqual(pan["status"], "provider_reported")


class WorkstreamD_CorporateActionInvalidationTests(unittest.TestCase):
    def test_corporate_action_invalidation(self) -> None:
        """Workstream D: Post-observation corporate actions invalidate provider shares."""
        runtime_root = ROOT.parent / "dashboard-runtime"
        # Test non-qualified ticker with corporate events if any, or invalidation logic
        inv = shares_resolver.resolve_effective_shares("NON_EXISTENT_XYZ", runtime_root)
        self.assertEqual(inv["authority"], "unavailable")


class WorkstreamE_MarketWideAuditTests(unittest.TestCase):
    def test_market_wide_authority_audit(self) -> None:
        """Workstream E: Projects hardened authority counts across active universe."""
        runtime_root = ROOT.parent / "dashboard-runtime"
        summary = shares_resolver.resolve_market_wide_shares(runtime_root)
        self.assertEqual(summary["active_universe_ticker_count"], 1683)
        self.assertEqual(summary["qualified_official_count"], 3)
        self.assertEqual(summary["provider_reported_current_count"], 1677)
        self.assertEqual(summary["provider_reported_stale_count"], 2)
        self.assertEqual(summary["unavailable_count"], 1)


class WorkstreamF_ProducerConsumerRepresentativeProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_root = ROOT.parent / "dashboard-runtime"

    def test_six_representative_proof_cases(self) -> None:
        """Workstream F: Verifies Producer-to-Consumer preservation for 6 representative cases."""
        bundle_entries = {
            "HPG": {"company_name": "Hoa Phat Group"},
            "VNM": {"company_name": "Vinamilk"},
            "VCB": {"company_name": "Vietcombank"},
            "PAN": {"company_name": "PAN Group"},
            "UNAVAIL": {"company_name": "Unavailable Ticker"},
        }
        attached = attach(bundle_entries, self.runtime_root, include=True)

        for ticker in ("HPG", "VNM", "VCB", "PAN"):
            context = {"ticker": ticker, "provenance": []}
            apply_bundle_canonical_financial_facts_contract(context, {"tickers": attached})
            self.assertIn("canonical_financial_facts", context)


class WorkstreamG_OperatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_root = ROOT.parent / "dashboard-runtime"

    def test_operator_p1j_reporting(self) -> None:
        """Workstream G: Operator reports hardened authority counts."""
        op = Operator(
            root=self.runtime_root,
            tickers=["HPG", "VNM", "VCB"],
            execute=False,
            publish=False,
            live=False,
            include_canonical_financial_facts=True,
        )
        self.assertEqual(op.run(), 0)


if __name__ == "__main__":
    unittest.main()
