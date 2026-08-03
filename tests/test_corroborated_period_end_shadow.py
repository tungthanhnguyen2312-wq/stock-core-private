"""The `corroborated_period_end` shadow lane, and the six constraints it must not break.

The lane exists so VNM can be studied without weakening what `qualified_official` means. Each
constraint the owner set is a test here, because a shadow lane that quietly stops being a
shadow is worse than not having one.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import corroborated_period_end_shadow as shadow  # noqa: E402
import market_wide_current_shares_resolver as prod  # noqa: E402
from tests.test_b1_share_basis_event_promotion import (  # noqa: E402
    event_anchor, period_end_anchor, write_runtime,
)

RUNTIME = ROOT.parent / "dashboard-runtime"
SESSION = "2026-08-03"


class ShadowContainmentTests(unittest.TestCase):
    """Constraint 3 and 4: never raises `is_actionable`, never leaves shadow."""

    def test_every_verdict_declares_itself_shadow_only(self) -> None:
        result = shadow.evaluate(RUNTIME, SESSION)
        self.assertTrue(result["shadow_only"])
        for ticker, verdict in result["tickers"].items():
            self.assertTrue(verdict["shadow_only"], ticker)
            self.assertFalse(verdict["contributes_to_is_actionable"], ticker)
            self.assertFalse(verdict["contributes_to_qualified_official"], ticker)

    def test_the_lane_name_is_never_a_production_authority(self) -> None:
        summary = prod.resolve_market_wide_shares(RUNTIME, SESSION)
        self.assertNotIn(shadow.LANE, summary["counts"])
        for verdict in summary["tickers"].values():
            self.assertNotEqual(verdict["authority"], shadow.LANE)

    def test_the_production_lanes_are_identical_with_and_without_the_shadow(self) -> None:
        before = prod.resolve_market_wide_shares(RUNTIME, SESSION)["counts"]
        shadow.evaluate(RUNTIME, SESSION)
        after = prod.resolve_market_wide_shares(RUNTIME, SESSION)["counts"]
        self.assertEqual(before, after)

    def test_the_shadow_never_reads_as_qualified_official(self) -> None:
        result = shadow.evaluate(RUNTIME, SESSION)
        for ticker in result["eligible_tickers"]:
            self.assertNotEqual(
                prod.resolve_effective_shares(ticker, RUNTIME, SESSION)["authority"],
                "qualified_official",
                f"{ticker} is shadow-eligible and must not be production-qualified")


class ShadowAuthorityTests(unittest.TestCase):
    """Constraint 1: strictly below executed-event evidence."""

    def test_the_rank_is_below_executed_event_evidence(self) -> None:
        self.assertLess(shadow.AUTHORITY_RANK, shadow.EXECUTED_EVENT_AUTHORITY_RANK)
        result = shadow.evaluate(RUNTIME, SESSION)
        self.assertEqual(result["authority_rank"], shadow.AUTHORITY_RANK)
        self.assertEqual(result["below"]["lane"], "qualified_official")

    def test_an_event_anchor_is_out_of_scope_for_this_lane(self) -> None:
        """HPG has an executed-event anchor; the weaker lane must not claim it."""
        verdict = shadow.evaluate(RUNTIME, SESSION)["tickers"]["HPG"]
        self.assertFalse(verdict["eligible"])
        self.assertEqual(verdict["reason"], "anchor_is_not_a_period_end_figure")


class ShadowHonestyTests(unittest.TestCase):
    """Constraints 2 and 5: proves no absence of events, and shows the interval carried."""

    def test_no_verdict_ever_claims_to_prove_the_absence_of_an_event(self) -> None:
        result = shadow.evaluate(RUNTIME, SESSION)
        for ticker, verdict in result["tickers"].items():
            self.assertFalse(verdict["proves_no_intervening_event"], ticker)

    def test_an_eligible_verdict_states_the_interval_it_is_carrying(self) -> None:
        result = shadow.evaluate(RUNTIME, SESSION)
        self.assertTrue(result["eligible_tickers"])
        for ticker in result["eligible_tickers"]:
            verdict = result["tickers"][ticker]
            self.assertIsInstance(verdict["interval_days_carried_by_observation"], int)
            self.assertGreaterEqual(verdict["interval_days_carried_by_observation"], 0)
            self.assertTrue(verdict["anchor_period_end"])
            self.assertTrue(verdict["observation_date"])

    def test_vnm_is_eligible_and_the_exposure_is_visible(self) -> None:
        verdict = shadow.evaluate(RUNTIME, SESSION)["tickers"]["VNM"]
        self.assertTrue(verdict["eligible"])
        self.assertEqual(verdict["anchor_period_end"], "2024-12-31")
        self.assertEqual(verdict["observation_date"], "2026-07-30")
        self.assertEqual(verdict["interval_days_carried_by_observation"], 576)

    def test_vcb_is_refused_because_the_observation_disagrees(self) -> None:
        verdict = shadow.evaluate(RUNTIME, SESSION)["tickers"]["VCB"]
        self.assertFalse(verdict["eligible"])
        self.assertEqual(verdict["reason"], "observation_contradicts_the_anchor")


class ShadowEdgeTests(unittest.TestCase):
    def _verdict(self, **kwargs) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = write_runtime(Path(tmp), **kwargs)
            return shadow.evaluate(root, SESSION)["tickers"]["AAA"]

    def test_a_disagreeing_observation_is_refused(self) -> None:
        verdict = self._verdict(anchors=[period_end_anchor()], shares_outstanding=1001)
        self.assertFalse(verdict["eligible"])
        self.assertEqual(verdict["reason"], "observation_contradicts_the_anchor")

    def test_an_observation_predating_the_period_end_is_refused(self) -> None:
        verdict = self._verdict(anchors=[period_end_anchor(reporting_period="2026")],
                                shares_outstanding=1000, observed="2026-07-30")
        self.assertFalse(verdict["eligible"])
        self.assertEqual(verdict["reason"], "observation_predates_the_period_end")

    def test_an_event_anchor_outranks_and_removes_the_ticker_from_this_lane(self) -> None:
        verdict = self._verdict(anchors=[period_end_anchor(), event_anchor()],
                                shares_outstanding=2000)
        self.assertFalse(verdict["eligible"])
        self.assertEqual(verdict["reason"], "anchor_is_not_a_period_end_figure")

    def test_an_unreadable_store_reports_error_not_zero_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = shadow.evaluate(Path(tmp), SESSION)
        self.assertEqual(result["status"], "unresolved_error")
        self.assertIsNone(result["eligible_count"])

    def test_a_bad_session_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            shadow.evaluate(RUNTIME, "not-a-date")


if __name__ == "__main__":
    unittest.main()
