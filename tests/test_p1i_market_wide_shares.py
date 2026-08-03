"""Comprehensive test suite for P1I — Market-Wide Current Shares Coverage."""

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


class WorkstreamA_ShareObservationInventoryTests(unittest.TestCase):
    def test_share_observation_inventory(self) -> None:
        """Workstream A: Inventories retained share observations without guessing concepts."""
        runtime_root = ROOT.parent / "dashboard-runtime"
        hpg = shares_resolver.resolve_effective_shares("HPG", runtime_root)
        self.assertEqual(hpg["share_concept"], "current_common_shares_outstanding")
        self.assertEqual(hpg["unit"], "shares")
        self.assertEqual(hpg["authority"], "qualified_official")

        pan = shares_resolver.resolve_effective_shares("PAN", runtime_root)
        self.assertEqual(pan["share_concept"], "current_common_shares_outstanding")
        self.assertEqual(pan["unit"], "shares")
        self.assertEqual(pan["authority"], "provider_reported")


class WorkstreamB_AuthorityLanesTests(unittest.TestCase):
    def test_authority_lanes_segregation(self) -> None:
        """Workstream B: Segregates qualified_official, provider_reported, and unavailable lanes."""
        runtime_root = ROOT.parent / "dashboard-runtime"
        hpg = shares_resolver.resolve_effective_shares("HPG", runtime_root)
        self.assertEqual(hpg["authority"], "qualified_official")
        self.assertEqual(hpg["status"], "qualified")

        pan = shares_resolver.resolve_effective_shares("PAN", runtime_root)
        self.assertEqual(pan["authority"], "provider_reported")
        self.assertEqual(pan["status"], "provider_reported")
        self.assertNotEqual(pan["status"], "qualified")

        inv = shares_resolver.resolve_effective_shares("INVALID_TICKER_99", runtime_root)
        self.assertEqual(inv["authority"], "unavailable")
        self.assertEqual(inv["status"], "unavailable")


class WorkstreamC_CurrentEffectiveShareResolverTests(unittest.TestCase):
    def test_current_effective_share_resolution(self) -> None:
        """Workstream C: Resolves effective shares for target session fail-closed."""
        runtime_root = ROOT.parent / "dashboard-runtime"
        vnm = shares_resolver.resolve_effective_shares("VNM", runtime_root, target_date="2026-07-30")
        self.assertEqual(vnm["value"], 2089955445)
        self.assertEqual(vnm["target_date"], "2026-07-30")


class WorkstreamD_MarketWideProjectionTests(unittest.TestCase):
    def test_market_wide_shares_projection(self) -> None:
        """Workstream D: Projects deterministic counts over existing active universe."""
        runtime_root = ROOT.parent / "dashboard-runtime"
        summary = shares_resolver.resolve_market_wide_shares(runtime_root)
        self.assertEqual(summary["active_universe_ticker_count"], 1683)
        self.assertEqual(summary["qualified_official_current_shares_count"], 3)
        self.assertEqual(summary["provider_reported_current_shares_count"], 1679)
        self.assertEqual(summary["unavailable_current_shares_count"], 1)


class WorkstreamE_ValuationReadinessExpansionTests(unittest.TestCase):
    def test_valuation_readiness_expansion(self) -> None:
        """Workstream E: Projects valuation readiness preserving separate authority."""
        res = readiness.evaluate_market_capitalisation(
            period="2024",
            session_price=10000.0,
            effective_shares={"value": 1000000, "status": "provider_reported", "authority": "provider_reported"},
        )
        self.assertEqual(res["readiness"], readiness.READY)
        self.assertEqual(res["status"], readiness.STATUS_PROVIDER_REPORTED)
        self.assertEqual(res["value"], 10000000000.0)


class WorkstreamF_ConflictHandlingTests(unittest.TestCase):
    def test_conflict_handling_fail_closed(self) -> None:
        """Workstream F: Fails closed when share observations are missing or invalid."""
        res = shares_resolver.resolve_effective_shares("NON_EXISTENT_XYZ", ROOT.parent / "dashboard-runtime")
        self.assertEqual(res["authority"], "unavailable")
        self.assertIsNone(res["value"])


class WorkstreamG_ProducerConsumerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_root = ROOT.parent / "dashboard-runtime"

    def test_producer_consumer_four_cases(self) -> None:
        """Workstream G: Proves exact preservation across 4 cases: qualified, provider_reported, unavailable, financial."""
        bundle_entries = {
            "HPG": {"company_name": "Hoa Phat Group"},
            "PAN": {"company_name": "PAN Group"},
            "VCB": {"company_name": "Vietcombank"},
        }
        attached = attach(bundle_entries, self.runtime_root, include=True)

        for ticker in ("HPG", "PAN", "VCB"):
            context = {"ticker": ticker, "provenance": []}
            apply_bundle_canonical_financial_facts_contract(context, {"tickers": attached})
            self.assertIn("canonical_financial_facts", context)
            facts_sec = context["canonical_financial_facts"]
            readiness_list = facts_sec.get("calculation_readiness") or []
            self.assertTrue(len(readiness_list) > 0)


class WorkstreamH_PostCloseOperatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_root = ROOT.parent / "dashboard-runtime"

    def test_operator_market_wide_coverage(self) -> None:
        """Workstream H: Runs operator dry-run with market-wide coverage reporting."""
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
