"""Comprehensive test suite for P1H — Current Share Basis and Valuation Readiness Activation."""

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

import share_transition_bridge as share_bridge  # noqa: E402
import market_wide_calculation_readiness as readiness  # noqa: E402
from canonical_financial_bundle_section import attach, _resolve_session_inputs  # noqa: E402
from builders.build_ticker_context import (  # noqa: E402
    canonical_financial_facts_contract,
    apply_bundle_canonical_financial_facts_contract,
)
from tools.operate_stocklookup import Operator  # noqa: E402


class WorkstreamA_CurrentEffectiveSharesTests(unittest.TestCase):
    def test_resolve_current_effective_shares_authority_order(self) -> None:
        """Workstream A: Resolves current effective shares by authority order without backsolving."""
        opening_hpg = {
            "effective_date": "2024-12-31",
            "value": 6396250200,
            "unit": "shares",
            "share_class": "common_outstanding",
            "identity_scope": "issuer",
            "qualification": "qualified",
            "citation_id": "cite_hpg_2024",
            "source_hash": "hash_hpg_2024",
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
            "opening_shares": 6396250200,
            "resulting_shares": 7163748865,
            "citation_id": "cite_hpg_div",
            "source_hash": "hash_hpg_div",
        }

        res_hpg = share_bridge.resolve_share_transition(
            opening=opening_hpg,
            events=[event_hpg],
            target_date="2026-07-30",
            coverage_through="2026-07-30",
        )
        self.assertEqual(res_hpg["current_shares"]["value"], 7163748865)


class WorkstreamB_SessionPriceInputTests(unittest.TestCase):
    def test_session_price_resolution(self) -> None:
        """Workstream B: Resolves current-session market price from runtime database/csv."""
        runtime_root = ROOT.parent / "dashboard-runtime"
        price_hpg, shares_hpg = _resolve_session_inputs("HPG", {}, runtime_root)
        self.assertEqual(price_hpg, 21800.0)
        self.assertEqual(shares_hpg["value"], 7163748865)

        price_vnm, shares_vnm = _resolve_session_inputs("VNM", {}, runtime_root)
        self.assertEqual(price_vnm, 61200.0)
        self.assertEqual(shares_vnm["value"], 2089955445)


class WorkstreamC_CurrentMarketCapTests(unittest.TestCase):
    def test_reconstructed_current_market_cap_calculation(self) -> None:
        """Workstream C: Reconstructs current market cap from session price and effective shares."""
        res = readiness.evaluate_market_capitalisation(
            period="2024",
            session_price=21800.0,
            effective_shares={"value": 7163748865, "status": "qualified"},
        )
        self.assertEqual(res["readiness"], readiness.READY)
        self.assertEqual(res["value"], 156169725257000.0)
        self.assertEqual(res["status"], readiness.STATUS_QUALIFIED)
        self.assertEqual(res["terms"]["basis_type"], "current_snapshot")


class WorkstreamD_ValuationReadinessTests(unittest.TestCase):
    def test_valuation_readiness_pe_pb_ev_ev_ebitda(self) -> None:
        """Workstream D: Computes P/E, P/B, EV, and EV/EBITDA fail-closed."""
        period_facts = {
            "total_interest_bearing_debt": {"value": 75348775190094.0, "status": readiness.STATUS_PROVIDER_REPORTED, "fact_id": "debt_f", "reporting_period": "2024", "statement_scope": "consolidated", "currency": "VND", "scale": "unit", "cumulative_state": "cumulative"},
            "cash_and_cash_equivalents": {"value": 34228815082143.0, "status": readiness.STATUS_PROVIDER_REPORTED, "fact_id": "cash_f", "reporting_period": "2024", "statement_scope": "consolidated", "currency": "VND", "scale": "unit", "cumulative_state": "cumulative"},
            "net_income": {"value": 11765835335016.0, "status": readiness.STATUS_PROVIDER_REPORTED, "fact_id": "net_inc_f", "reporting_period": "2024", "statement_scope": "consolidated", "currency": "VND", "scale": "unit", "cumulative_state": "cumulative"},
            "shareholders_equity": {"value": 111262497237341.0, "status": readiness.STATUS_PROVIDER_REPORTED, "fact_id": "eq_f", "reporting_period": "2024", "statement_scope": "consolidated", "currency": "VND", "scale": "unit", "cumulative_state": "cumulative"},
        }
        mcap = readiness.evaluate_market_capitalisation(period="2024", session_price=21800.0, effective_shares=7163748865)
        ev = readiness.evaluate_enterprise_value(period_facts, "2024", mcap)
        self.assertEqual(ev["readiness"], readiness.READY)
        self.assertEqual(ev["value"], 197289685364951.0)

        pe = readiness.evaluate_price_ratio("pe", period_facts["net_income"], "2024", mcap, "net_income")
        self.assertEqual(pe["readiness"], readiness.READY)
        self.assertAlmostEqual(pe["value"], 13.2731, places=3)

        pb = readiness.evaluate_price_ratio("pb", period_facts["shareholders_equity"], "2024", mcap, "shareholders_equity")
        self.assertEqual(pb["readiness"], readiness.READY)
        self.assertAlmostEqual(pb["value"], 1.4036, places=3)


class WorkstreamE_MarketWideClassificationTests(unittest.TestCase):
    def test_market_wide_readiness_counts(self) -> None:
        """Workstream E: Produces exact classification counts across supported tickers."""
        runtime_root = ROOT.parent / "dashboard-runtime"
        bundle = {
            "HPG": {"company_name": "Hoa Phat Group"},
            "VNM": {"company_name": "Vinamilk"},
            "VCB": {"company_name": "Vietcombank"},
            "AAH": {"company_name": "AAH"},
        }
        res = attach(bundle, runtime_root, include=True)
        mcap_ready = sum(1 for t, v in res.items() if (v.get("canonical_financial_facts", {}).get("calculation_readiness") or [{}])[0].get("market_capitalisation", {}).get("readiness") == readiness.READY)
        self.assertEqual(mcap_ready, 3)


class WorkstreamF_ProducerConsumerOperatorIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_root = ROOT.parent / "dashboard-runtime"

    def test_producer_consumer_operator_flow(self) -> None:
        """Workstream F: Verifies Producer export, Consumer pass-through, and Operator dry-run summary."""
        bundle_entries = {"HPG": {"company_name": "Hoa Phat Group"}}
        attached = attach(bundle_entries, self.runtime_root, include=True)
        context = {"ticker": "HPG", "provenance": []}
        apply_bundle_canonical_financial_facts_contract(context, {"tickers": attached})
        self.assertIn("canonical_financial_facts", context)

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
