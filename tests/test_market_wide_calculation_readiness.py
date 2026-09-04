"""Focused unit tests for market_wide_calculation_readiness.evaluate_ev_ebitda.

No dedicated test file existed for this module before (it was previously exercised only
indirectly through tests/test_p1h_valuation_readiness.py's integration-level coverage). This
file targets specifically the negative/zero-EBITDA-denominator reason-code gap found via a real
2026-08-25 market-wide replay: 13 real ticker-periods (e.g. AAH 2026-Q1, ABS 2025-Q3) had a
ready, usable, negative EBITDA and a ready enterprise value, yet ev_ebitda's `blocked_by` came
back an empty list -- correctly refusing to compute a meaningless ratio, but with no reason
explaining why, indistinguishable from a missing-input block.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import market_wide_calculation_readiness as readiness


def _ready_ebitda(value):
    return readiness._result("ebitda", readiness.READY, period="2026-Q1", value=value,
                             status="provider_reported", formula=readiness.EBITDA_FORMULA)


def _ready_ev(value=1_000_000):
    return readiness._result("enterprise_value", readiness.READY, period="2026-Q1", value=value,
                             status="provider_reported", formula=readiness.EV_FORMULA)


def _blocked_ev(blocked_by=("price_basis_unknown_and_unverified_universe_wide",)):
    return readiness._result("enterprise_value", readiness.BLOCKED, period="2026-Q1",
                             status="unavailable", formula=readiness.EV_FORMULA,
                             blocked_by=list(blocked_by))


class NegativeOrZeroEbitdaDenominatorTests(unittest.TestCase):
    def test_negative_ebitda_blocks_with_an_explicit_reason(self):
        verdict = readiness.evaluate_ev_ebitda(_ready_ebitda(-500_000), _ready_ev(), "2026-Q1")
        self.assertEqual(verdict["readiness"], readiness.BLOCKED)
        self.assertIn("negative_or_zero_ebitda_denominator", verdict["blocked_by"])
        self.assertIn("not a meaningful multiple", verdict["reason"])

    def test_zero_ebitda_blocks_with_an_explicit_reason(self):
        verdict = readiness.evaluate_ev_ebitda(_ready_ebitda(0), _ready_ev(), "2026-Q1")
        self.assertEqual(verdict["readiness"], readiness.BLOCKED)
        self.assertIn("negative_or_zero_ebitda_denominator", verdict["blocked_by"])

    def test_positive_ebitda_and_ready_ev_computes_the_ratio(self):
        verdict = readiness.evaluate_ev_ebitda(_ready_ebitda(200_000), _ready_ev(1_000_000), "2026-Q1")
        self.assertEqual(verdict["readiness"], readiness.READY)
        self.assertEqual(verdict["value"], 5.0)

    def test_ebitda_not_ready_still_reports_ebitda_not_ready(self):
        not_ready_ebitda = readiness._result("ebitda", readiness.BLOCKED, period="2026-Q1",
                                             status="unavailable", formula=readiness.EBITDA_FORMULA,
                                             blocked_by=["missing_term:profit_before_tax"])
        verdict = readiness.evaluate_ev_ebitda(not_ready_ebitda, _ready_ev(), "2026-Q1")
        self.assertEqual(verdict["readiness"], readiness.BLOCKED)
        self.assertIn("ebitda_not_ready", verdict["blocked_by"])
        self.assertNotIn("negative_or_zero_ebitda_denominator", verdict["blocked_by"])

    def test_ev_not_ready_never_masked_by_the_new_check(self):
        """A negative EBITDA alongside a not-ready EV must still surface EV's own blockers."""
        verdict = readiness.evaluate_ev_ebitda(_ready_ebitda(-1), _blocked_ev(), "2026-Q1")
        self.assertEqual(verdict["readiness"], readiness.BLOCKED)
        self.assertIn("price_basis_unknown_and_unverified_universe_wide", verdict["blocked_by"])


if __name__ == "__main__":
    unittest.main()
