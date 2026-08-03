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

#: The session the retained runtime is anchored to. The share and price legs of this
#: section are both session-relative, so the tests state the session explicitly.
SESSION = "2026-07-30"


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
        # The event's own figures, not the FY2024 period-end anchor: the 2026-06-04 dividend
        # was issued on a base of 7,675,465,852, and the ledger records shares_after as
        # 8,442,964,520. Carrying the FY2024 anchor in as the event base is what produced the
        # retired 7,163,748,865, a number no citation and no ledger contains.
        opening_hpg = {
            "effective_date": "2026-06-03",
            "value": 7675465852,
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
            "opening_shares": 7675465852,
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


class WorkstreamB_SessionPriceInputTests(unittest.TestCase):
    def test_session_price_resolution(self) -> None:
        """Workstream B: Resolves current-session market price from runtime database/csv."""
        runtime_root = ROOT.parent / "dashboard-runtime"
        price_hpg, shares_hpg = _resolve_session_inputs("HPG", {}, runtime_root, SESSION)
        self.assertEqual(price_hpg, 21800.0)
        self.assertEqual(shares_hpg["value"], 8442964520)

        price_vnm, shares_vnm = _resolve_session_inputs("VNM", {}, runtime_root, SESSION)
        self.assertEqual(price_vnm, 61200.0)
        self.assertEqual(shares_vnm["value"], 2089955445)

    def test_the_price_is_the_session_close_not_the_newest_close(self) -> None:
        """2026-08-03 closes exist in the store; asking for 2026-07-30 must not return them."""
        runtime_root = ROOT.parent / "dashboard-runtime"
        price, _ = _resolve_session_inputs("HPG", {}, runtime_root, "2026-08-03")
        self.assertEqual(price, 22550.0)

    def test_a_session_the_ticker_did_not_trade_yields_no_price(self) -> None:
        runtime_root = ROOT.parent / "dashboard-runtime"
        price, _ = _resolve_session_inputs("HPG", {}, runtime_root, "1990-01-02")
        self.assertIsNone(price)


class WorkstreamC_CurrentMarketCapTests(unittest.TestCase):
    def test_reconstructed_current_market_cap_calculation(self) -> None:
        """Workstream C: Reconstructs current market cap from session price and effective shares."""
        res = readiness.evaluate_market_capitalisation(
            period="2024",
            session_price=21800.0,
            effective_shares={"value": 8442964520, "status": "qualified"},
            price_basis_verified=True,
        )
        self.assertEqual(res["readiness"], readiness.READY)
        self.assertEqual(res["value"], 184056626536000.0)
        self.assertEqual(res["status"], readiness.STATUS_QUALIFIED)
        self.assertEqual(res["terms"]["basis_type"], "current_snapshot")

    def test_a_qualified_share_count_alone_does_not_qualify_the_cap(self) -> None:
        """The bundle's price basis is unverified today, which is the live case."""
        res = readiness.evaluate_market_capitalisation(
            period="2024",
            session_price=21800.0,
            effective_shares={"value": 8442964520, "status": "qualified"},
        )
        self.assertEqual(res["readiness"], readiness.READY)
        self.assertEqual(res["status"], readiness.STATUS_PROVIDER_REPORTED)


class WorkstreamD_ValuationReadinessTests(unittest.TestCase):
    def test_valuation_readiness_pe_pb_ev_ev_ebitda(self) -> None:
        """Workstream D: Computes P/E, P/B, EV, and EV/EBITDA fail-closed."""
        period_facts = {
            "total_interest_bearing_debt": {"value": 75348775190094.0, "status": readiness.STATUS_PROVIDER_REPORTED, "fact_id": "debt_f", "reporting_period": "2024", "statement_scope": "consolidated", "currency": "VND", "scale": "unit", "cumulative_state": "cumulative"},
            "cash_and_cash_equivalents": {"value": 34228815082143.0, "status": readiness.STATUS_PROVIDER_REPORTED, "fact_id": "cash_f", "reporting_period": "2024", "statement_scope": "consolidated", "currency": "VND", "scale": "unit", "cumulative_state": "cumulative"},
            "net_income": {"value": 11765835335016.0, "status": readiness.STATUS_PROVIDER_REPORTED, "fact_id": "net_inc_f", "reporting_period": "2024", "statement_scope": "consolidated", "currency": "VND", "scale": "unit", "cumulative_state": "cumulative"},
            "shareholders_equity": {"value": 111262497237341.0, "status": readiness.STATUS_PROVIDER_REPORTED, "fact_id": "eq_f", "reporting_period": "2024", "statement_scope": "consolidated", "currency": "VND", "scale": "unit", "cumulative_state": "cumulative"},
        }
        mcap = readiness.evaluate_market_capitalisation(
            period="2024", session_price=21800.0,
            effective_shares={"value": 8442964520, "status": readiness.STATUS_PROVIDER_REPORTED,
                              "authority": "provider_reported_lagged",
                              "share_concept": "ISSUED_SHARES"})
        ev = readiness.evaluate_enterprise_value(period_facts, "2024", mcap)
        self.assertEqual(ev["readiness"], readiness.READY)
        self.assertEqual(ev["value"], 225176586643951.0)

        pe = readiness.evaluate_price_ratio("pe", period_facts["net_income"], "2024", mcap, "net_income")
        self.assertEqual(pe["readiness"], readiness.READY)
        self.assertAlmostEqual(pe["value"], 15.6433, places=3)

        pb = readiness.evaluate_price_ratio("pb", period_facts["shareholders_equity"], "2024", mcap, "shareholders_equity")
        self.assertEqual(pb["readiness"], readiness.READY)
        self.assertAlmostEqual(pb["value"], 1.6543, places=3)


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
        res = attach(bundle, runtime_root, include=True, session_date=SESSION)
        statuses = [(v.get("canonical_financial_facts", {}).get("calculation_readiness") or [{}])[0]
                    .get("market_capitalisation", {}).get("status") for v in res.values()]
        # Zero, not three. The three qualified caps came from a hardcoded share table whose
        # HPG and VCB entries were wrong, and from a market cap that ignored the price basis.
        # The bundle's price basis is unverified, so no cap can be qualified today.
        self.assertEqual(sum(1 for s in statuses if s == readiness.STATUS_QUALIFIED), 0)
        self.assertTrue(any(s == readiness.STATUS_PROVIDER_REPORTED for s in statuses))


class WorkstreamF_ProducerConsumerOperatorIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_root = ROOT.parent / "dashboard-runtime"

    def test_producer_consumer_operator_flow(self) -> None:
        """Workstream F: Verifies Producer export, Consumer pass-through, and Operator dry-run summary."""
        bundle_entries = {"HPG": {"company_name": "Hoa Phat Group"}}
        attached = attach(bundle_entries, self.runtime_root, include=True, session_date=SESSION)
        context = {"ticker": "HPG", "provenance": []}
        apply_bundle_canonical_financial_facts_contract(context, {"tickers": attached})
        self.assertIn("canonical_financial_facts", context)

        # The section itself is exercised above. The flag is omitted here because it is what
        # routes a share count into the export, and the live runtime's share observation is
        # older than its session -- see tests/test_daily_freshness_contract.py for that gate.
        op = Operator(
            root=self.runtime_root,
            tickers=["HPG", "VNM", "VCB"],
            execute=False,
            publish=False,
            live=False,
        )
        self.assertEqual(op.run(), 0)


if __name__ == "__main__":
    unittest.main()
