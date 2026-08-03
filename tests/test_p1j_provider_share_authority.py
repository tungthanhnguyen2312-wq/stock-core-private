"""P1J — provider-reported share authority and freshness.

What P1J set out to prove still holds and is tested here: the provider field's semantics, its
grounding against the official anchors, and the freshness rules. What P1J's review asserted
about that grounding did not hold, and the corrected comparison is the subject of
`WorkstreamB_OfficialAnchorGroundingTests`.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CONSUMER_ROOT = ROOT.parent / "ai-core-private"
sys.path.insert(0, str(CONSUMER_ROOT))

import market_wide_current_shares_resolver as shares_resolver  # noqa: E402
from builders.build_ticker_context import (  # noqa: E402
    apply_bundle_canonical_financial_facts_contract,
)
from canonical_financial_bundle_section import attach  # noqa: E402
from tools.operate_stocklookup import Operator  # noqa: E402

RUNTIME = ROOT.parent / "dashboard-runtime"
SESSION = "2026-07-30"


class WorkstreamA_ProviderFieldProvenanceTests(unittest.TestCase):
    def test_the_provider_concept_is_issued_shares_and_says_so(self) -> None:
        result = shares_resolver.resolve_effective_shares("PAN", RUNTIME, SESSION)
        self.assertEqual(result["share_concept"], "ISSUED_SHARES")
        self.assertEqual(result["source"], "VCI.overview.issue_share")
        self.assertEqual(result["unit"], "shares")
        self.assertEqual(result["lineage"], "retained_provider_metadata_issue_share")

    def test_every_result_carries_its_observation_date(self) -> None:
        result = shares_resolver.resolve_effective_shares("PAN", RUNTIME, SESSION)
        self.assertIsNotNone(result["observation_date"])


class WorkstreamB_OfficialAnchorGroundingTests(unittest.TestCase):
    """The corrected grounding.

    P1J's review recorded HPG's provider value as 6,396,250,200 against an official
    7,163,748,865, and VCB as an exact agreement at 5,589,091,222. The database holds
    8,442,964,520 for HPG and 8,355,675,094 for VCB, and the citation store holds
    5,589,091,262 for VCB. All three of those review lines were wrong.
    """

    def test_the_hpg_provider_value_already_reflects_the_stock_dividend(self) -> None:
        result = shares_resolver.resolve_effective_shares("HPG", RUNTIME, SESSION)
        self.assertEqual(result["value"], 8442964520)
        self.assertEqual(result["official_anchor_value"], 6396250200)

    def test_the_official_anchor_is_a_2024_period_end_figure(self) -> None:
        for ticker in ("HPG", "VNM", "VCB"):
            anchor = shares_resolver.load_official_anchors(RUNTIME)[ticker]
            self.assertEqual(anchor["reporting_period"], "2024")
            self.assertEqual(anchor["share_class"], "common_outstanding")

    def test_vnm_is_the_one_ticker_where_provider_and_anchor_agree(self) -> None:
        result = shares_resolver.resolve_effective_shares("VNM", RUNTIME, SESSION)
        self.assertEqual(result["value"], result["official_anchor_value"])


class WorkstreamC_FreshnessContractTests(unittest.TestCase):
    def test_freshness_is_measured_against_the_observation_not_a_fixed_date(self) -> None:
        result = shares_resolver.resolve_effective_shares("PAN", RUNTIME, SESSION)
        self.assertEqual(result["authority"], "provider_reported_current")
        self.assertEqual(result["observation_lag_days"], 0)

    def test_the_absence_of_a_ledger_is_stated_not_treated_as_proof(self) -> None:
        result = shares_resolver.resolve_effective_shares("PAN", RUNTIME, SESSION)
        self.assertEqual(result["freshness_proof"], "absent_no_ledger_coverage")


class WorkstreamD_CorporateActionInvalidationTests(unittest.TestCase):
    def test_an_undated_share_event_withholds_the_value(self) -> None:
        """VCB and SSI carry an issuance with no ex-right date, so neither can be resolved."""
        for ticker in ("VCB", "SSI"):
            result = shares_resolver.resolve_effective_shares(ticker, RUNTIME, SESSION)
            self.assertEqual(result["authority"], "provider_reported_unverifiable_freshness")
            self.assertIsNone(result["value"])

    def test_the_share_changing_code_set_is_explicit(self) -> None:
        self.assertIn("ISS", shares_resolver.SHARE_CHANGING_EVENT_CODES)
        self.assertNotIn("DIV", shares_resolver.SHARE_CHANGING_EVENT_CODES)
        self.assertEqual(shares_resolver.SHARE_CHANGING_EVENT_CODES
                         & shares_resolver.NON_SHARE_CHANGING_EVENT_CODES, frozenset())


class WorkstreamE_MarketWideAuditTests(unittest.TestCase):
    def test_the_audit_is_measured_and_reconciles(self) -> None:
        summary = shares_resolver.resolve_market_wide_shares(RUNTIME, SESSION)
        self.assertEqual(summary["status"], "measured")
        self.assertTrue(summary["counts_reconcile"])
        self.assertEqual(summary["official_anchors_retained"], 3)

    def test_the_provider_lane_is_the_market_wide_ceiling(self) -> None:
        summary = shares_resolver.resolve_market_wide_shares(RUNTIME, SESSION)
        self.assertEqual(summary["counts"].get("qualified_official", 0), 0)
        self.assertGreater(summary["counts"].get("provider_reported_current", 0), 0)


class WorkstreamF_ProducerConsumerTests(unittest.TestCase):
    def test_representative_cases_cross_the_boundary(self) -> None:
        attached = attach({"HPG": {"company_name": "Hoa Phat Group"},
                           "VNM": {"company_name": "Vinamilk"},
                           "VCB": {"company_name": "Vietcombank"},
                           "PAN": {"company_name": "PAN Group"}},
                          RUNTIME, include=True, session_date=SESSION)
        for ticker in ("HPG", "VNM", "VCB", "PAN"):
            context = {"ticker": ticker, "provenance": []}
            apply_bundle_canonical_financial_facts_contract(context, {"tickers": attached})
            self.assertIn("canonical_financial_facts", context)


class WorkstreamG_OperatorTests(unittest.TestCase):
    def test_the_operator_reports_a_measurement_not_a_constant(self) -> None:
        operator = Operator(root=RUNTIME, tickers=["HPG", "VNM", "VCB"], execute=False,
                            publish=False, live=False, include_canonical_financial_facts=True)
        self.assertEqual(operator.run(), 0)
        coverage = operator.market_wide_shares_coverage()
        self.assertEqual(coverage["status"], "measured")
        self.assertTrue(coverage["measured_at"])
        self.assertNotIn("tickers", coverage)

    def test_coverage_is_unavailable_before_a_session_is_resolved(self) -> None:
        operator = Operator(root=RUNTIME, tickers=["HPG"], execute=False, publish=False,
                            live=False)
        coverage = operator.market_wide_shares_coverage()
        self.assertEqual(coverage["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
