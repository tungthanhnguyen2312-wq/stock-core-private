"""P1I — market-wide current-share coverage.

Coverage is asserted as invariants, not as a transcript of one day's database. The previous
revision pinned `active_universe_ticker_count == 1683` and three lane counts, so any legitimate
change to the universe broke the suite while a wrong lane rule that preserved the totals passed.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CONSUMER_ROOT = ROOT.parent / "ai-core-private"

import market_wide_calculation_readiness as readiness  # noqa: E402
import market_wide_current_shares_resolver as shares_resolver  # noqa: E402
from canonical_financial_bundle_section import attach  # noqa: E402
from tools.operate_stocklookup import Operator  # noqa: E402

if CONSUMER_ROOT.is_dir():
    sys.path.insert(0, str(CONSUMER_ROOT))
    from builders.build_ticker_context import (  # noqa: E402
        apply_bundle_canonical_financial_facts_contract,
    )
else:
    apply_bundle_canonical_financial_facts_contract = None

RUNTIME = ROOT.parent / "dashboard-runtime"
#: The session the retained runtime is anchored to.
SESSION = "2026-07-30"

PROVIDER_LANES = {"provider_reported_current", "provider_reported_lagged"}
WITHHELD_LANES = {"provider_reported_stale", "provider_reported_unverifiable_freshness",
                  "unknown_observation_date", "unavailable", "unresolved_error"}


@unittest.skipUnless(CONSUMER_ROOT.is_dir(), "Consumer repository required")
class UniverseCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.summary = shares_resolver.resolve_market_wide_shares(RUNTIME, SESSION)

    def test_the_universe_is_the_retained_metadata_universe(self) -> None:
        self.assertEqual(self.summary["status"], "measured")
        self.assertGreater(self.summary["active_universe_count"], 0)
        self.assertEqual(len(self.summary["tickers"]), self.summary["active_universe_count"])

    def test_every_ticker_lands_in_exactly_one_lane(self) -> None:
        self.assertTrue(self.summary["counts_reconcile"])
        known = PROVIDER_LANES | WITHHELD_LANES | {"qualified_official"}
        self.assertEqual(set(self.summary["counts"]) - known, set())

    def test_a_withheld_lane_never_carries_a_value(self) -> None:
        for ticker, result in self.summary["tickers"].items():
            if result["authority"] in WITHHELD_LANES:
                self.assertIsNone(result["value"], f"{ticker} withheld but carries a value")

    def test_a_provider_lane_always_carries_its_concept_and_source(self) -> None:
        for ticker, result in self.summary["tickers"].items():
            if result["authority"] in PROVIDER_LANES:
                self.assertEqual(result["share_concept"], shares_resolver.PROVIDER_SHARE_CONCEPT)
                self.assertEqual(result["source"], shares_resolver.PROVIDER_SOURCE)
                self.assertGreater(result["value"], 0, f"{ticker} in a provider lane with no value")

    def test_usable_values_reconcile_with_the_valued_lanes(self) -> None:
        valued = sum(1 for r in self.summary["tickers"].values() if r["value"] is not None)
        self.assertEqual(valued, self.summary["usable_share_value_count"])


@unittest.skipUnless(CONSUMER_ROOT.is_dir(), "Consumer repository required")
class UnknownTickerTests(unittest.TestCase):
    def test_a_ticker_outside_the_universe_is_unavailable(self) -> None:
        result = shares_resolver.resolve_effective_shares("NON_EXISTENT_XYZ", RUNTIME, SESSION)
        self.assertEqual(result["authority"], "unavailable")
        self.assertIsNone(result["value"])


@unittest.skipUnless(CONSUMER_ROOT.is_dir(), "Consumer repository required")
class ValuationReadinessTests(unittest.TestCase):
    def test_a_provider_share_count_yields_a_provider_reported_cap(self) -> None:
        result = readiness.evaluate_market_capitalisation(
            period="2024", session_price=10000.0,
            effective_shares={"value": 1000000, "status": "provider_reported",
                              "authority": "provider_reported_lagged",
                              "share_concept": "ISSUED_SHARES"})
        self.assertEqual(result["readiness"], readiness.READY)
        self.assertEqual(result["status"], readiness.STATUS_PROVIDER_REPORTED)
        self.assertEqual(result["value"], 10000000000.0)

    def test_no_price_means_no_cap(self) -> None:
        result = readiness.evaluate_market_capitalisation(
            period="2024", session_price=None,
            effective_shares={"value": 1000000, "status": "provider_reported"})
        self.assertEqual(result["readiness"], readiness.BLOCKED)
        self.assertIsNone(result.get("value"))


@unittest.skipUnless(CONSUMER_ROOT.is_dir(), "Consumer repository required")
class ProducerConsumerTests(unittest.TestCase):
    def test_the_section_survives_the_boundary_intact(self) -> None:
        attached = attach({"HPG": {"company_name": "Hoa Phat Group"},
                           "PAN": {"company_name": "PAN Group"},
                           "VCB": {"company_name": "Vietcombank"}},
                          RUNTIME, include=True, session_date=SESSION)
        for ticker in ("HPG", "PAN", "VCB"):
            context = {"ticker": ticker, "provenance": []}
            apply_bundle_canonical_financial_facts_contract(context, {"tickers": attached})
            self.assertIn("canonical_financial_facts", context)
            self.assertTrue(context["canonical_financial_facts"].get("calculation_readiness"))

    def test_without_a_session_nothing_is_attached(self) -> None:
        entries = {"HPG": {"company_name": "Hoa Phat Group"}}
        attached = attach(entries, RUNTIME, include=True, session_date=None)
        self.assertNotIn("canonical_financial_facts", attached["HPG"])


@unittest.skipUnless(CONSUMER_ROOT.is_dir(), "Consumer repository required")
class PostCloseOperatorTests(unittest.TestCase):
    def test_the_dry_run_passes_and_measures_coverage(self) -> None:
        # No canonical-facts flag: no share count reaches the export, so the share
        # observation's age cannot block the run. The lagged case is covered by
        # tests/test_daily_freshness_contract.py.
        operator = Operator(root=RUNTIME, tickers=["HPG", "VNM", "VCB"], execute=False,
                            publish=False, live=False)
        self.assertEqual(operator.run(), 0)
        coverage = operator.market_wide_shares_coverage()
        self.assertEqual(coverage["status"], "measured")
        self.assertEqual(coverage["session_date"], operator.reference_session_date)


if __name__ == "__main__":
    unittest.main()
