# ==========================================================================
# Focused tests for ticker_capability.py (P1.5: ticker capability matrix).
# Pure unit tests -- no I/O, no dashboard-runtime access. Verifies each tier
# gates strictly on its own already-qualified input and never upgrades from
# mere availability.
# Run: `python -m unittest tests.test_ticker_capability` from the repo root.
# ==========================================================================

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ticker_capability as tc  # noqa: E402


def _empty_capability_inputs() -> dict:
    return {
        "has_technical_coverage": False,
        "historical_fundamental_brief": None,
        "distribution_evidence": None,
        "price_basis_provenance": None,
        "current_shares_proven": False,
    }


class TickerCapabilityTests(unittest.TestCase):
    def test_t0_always_eligible(self) -> None:
        result = tc.evaluate_ticker_capability("XYZ", **_empty_capability_inputs())
        self.assertTrue(result["tiers"]["T0_informational"]["eligible"])
        self.assertFalse(result["is_actionable"])

    def test_all_tiers_blocked_with_no_evidence(self) -> None:
        result = tc.evaluate_ticker_capability("XYZ", **_empty_capability_inputs())
        for tier in ("T1_technical_display", "T2_historical_fundamental", "T3_distribution_event", "T4_market_dependent"):
            self.assertFalse(result["tiers"][tier]["eligible"], tier)
            self.assertIsInstance(result["tiers"][tier]["reason"], str)

    def test_t1_gates_on_technical_coverage_only(self) -> None:
        inputs = _empty_capability_inputs()
        inputs["has_technical_coverage"] = True
        result = tc.evaluate_ticker_capability("HPG", **inputs)
        self.assertTrue(result["tiers"]["T1_technical_display"]["eligible"])
        self.assertFalse(result["tiers"]["T2_historical_fundamental"]["eligible"])

    def test_t2_requires_available_status_and_facts(self) -> None:
        inputs = _empty_capability_inputs()
        inputs["historical_fundamental_brief"] = {"status": "available", "facts": []}
        result = tc.evaluate_ticker_capability("HPG", **inputs)
        self.assertFalse(result["tiers"]["T2_historical_fundamental"]["eligible"], "empty facts must not qualify")

        inputs["historical_fundamental_brief"] = {"status": "partial", "facts": [{"identity": "x"}]}
        result = tc.evaluate_ticker_capability("HPG", **inputs)
        self.assertFalse(result["tiers"]["T2_historical_fundamental"]["eligible"], "partial status must not qualify")

        inputs["historical_fundamental_brief"] = {"status": "available", "facts": [{"identity": "x"}]}
        result = tc.evaluate_ticker_capability("HPG", **inputs)
        self.assertTrue(result["tiers"]["T2_historical_fundamental"]["eligible"])

    def test_t3_requires_coverage_available_and_nonzero_events(self) -> None:
        inputs = _empty_capability_inputs()
        inputs["distribution_evidence"] = {"coverage_status": "missing", "cash_distributions": [], "non_cash_distributions": []}
        result = tc.evaluate_ticker_capability("HPG", **inputs)
        self.assertFalse(result["tiers"]["T3_distribution_event"]["eligible"])

        inputs["distribution_evidence"] = {"coverage_status": "available", "cash_distributions": [], "non_cash_distributions": []}
        result = tc.evaluate_ticker_capability("HPG", **inputs)
        self.assertFalse(result["tiers"]["T3_distribution_event"]["eligible"], "available coverage with zero events must not qualify")

        inputs["distribution_evidence"] = {"coverage_status": "available", "cash_distributions": [{"event_id": "e1"}], "non_cash_distributions": []}
        result = tc.evaluate_ticker_capability("VNM", **inputs)
        self.assertTrue(result["tiers"]["T3_distribution_event"]["eligible"])

    def test_t4_requires_all_three_conditions(self) -> None:
        inputs = _empty_capability_inputs()
        inputs["price_basis_provenance"] = {"is_actionable": True, "volume_basis_verified": True}
        inputs["current_shares_proven"] = False
        result = tc.evaluate_ticker_capability("HPG", **inputs)
        self.assertFalse(result["tiers"]["T4_market_dependent"]["eligible"])
        self.assertIn("current_shares", result["tiers"]["T4_market_dependent"]["reason"])

        inputs["current_shares_proven"] = True
        result = tc.evaluate_ticker_capability("HPG", **inputs)
        self.assertTrue(result["tiers"]["T4_market_dependent"]["eligible"])

    def test_t4_reflects_current_project_state_as_blocked(self) -> None:
        """Regression guard: at the current (2026-08-02) project state, price_basis is
        unknown/unverified for every ticker, so T4 must never be eligible via this path."""
        inputs = _empty_capability_inputs()
        inputs["price_basis_provenance"] = {"price_basis": "unknown", "is_actionable": False, "volume_basis_verified": False}
        inputs["current_shares_proven"] = False
        result = tc.evaluate_ticker_capability("HPG", **inputs)
        self.assertFalse(result["tiers"]["T4_market_dependent"]["eligible"])

    def test_is_actionable_always_false_on_every_tier_and_top_level(self) -> None:
        inputs = _empty_capability_inputs()
        inputs["has_technical_coverage"] = True
        inputs["historical_fundamental_brief"] = {"status": "available", "facts": [{"identity": "x"}]}
        inputs["distribution_evidence"] = {"coverage_status": "available", "cash_distributions": [{"event_id": "e1"}], "non_cash_distributions": []}
        inputs["price_basis_provenance"] = {"is_actionable": True, "volume_basis_verified": True}
        inputs["current_shares_proven"] = True
        result = tc.evaluate_ticker_capability("VNM", **inputs)
        self.assertFalse(result["is_actionable"])
        for tier_result in result["tiers"].values():
            self.assertFalse(tier_result["is_actionable"])


if __name__ == "__main__":
    unittest.main()
