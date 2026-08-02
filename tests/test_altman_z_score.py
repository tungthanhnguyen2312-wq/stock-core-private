# ==========================================================================
# Focused tests for altman_z_score.py. Pure unit tests -- no I/O, no
# dashboard-runtime access. HPG FY2024 values are the independently
# PDF-verified consolidated figures (see docs/altman_z_prime_qualification.md).
# Run: `python -m unittest tests.test_altman_z_score` from the repo root.
# ==========================================================================

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from altman_z_score import (  # noqa: E402
    DISTRESS_THRESHOLD, REQUIRED_IDENTITIES, SAFE_THRESHOLD, VARIANT, evaluate_altman_z_score,
)

_HPG_FY2024 = {
    "current_assets": 86674276272995,
    "current_liabilities": 75225243262689,
    "retained_earnings": 49599124109203,
    "total_assets": 224489707553981,
    "total_liabilities": 109842249570282,
    "net_sales": 138855112131387,
    "owners_equity": 114647457983699,
    "ebit": 15980863072058,
}


def _identities(overrides=None, **common):
    base = {"period": "2024", "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1}
    base.update(common)
    values = dict(_HPG_FY2024)
    if overrides:
        values.update(overrides)
    return {name: {"value": value, **base} for name, value in values.items()}


class AltmanZScoreTests(unittest.TestCase):
    def test_hpg_fy2024_matches_hand_computation_and_is_grey_zone(self):
        result = evaluate_altman_z_score(_identities())
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["variant"], VARIANT)
        self.assertAlmostEqual(result["score"], 1.5006, places=3)
        self.assertEqual(result["zone"], "grey")
        self.assertEqual(result["period"], "2024")
        self.assertEqual(result["statement_scope"], "consolidated")

    def test_working_capital_is_derived_not_taken_as_an_input(self):
        result = evaluate_altman_z_score(_identities())
        wc = result["inputs"]["working_capital"]
        self.assertEqual(wc["value"], 86674276272995 - 75225243262689)
        self.assertEqual(wc["derivation"], "current_assets - current_liabilities")

    def test_components_are_weighted_and_sum_to_the_score(self):
        result = evaluate_altman_z_score(_identities())
        self.assertAlmostEqual(sum(c["weighted"] for c in result["components"].values()), result["score"], places=9)

    def test_each_missing_identity_fails_closed_by_name(self):
        for name in REQUIRED_IDENTITIES:
            identities = _identities()
            del identities[name]
            result = evaluate_altman_z_score(identities)
            self.assertEqual(result["status"], "insufficient_evidence", name)
            self.assertIn(name, result["missing_inputs"], name)
            self.assertIsNone(result["score"], name)
            self.assertIsNone(result["zone"], name)

    def test_identity_misalignment_fails_closed_and_never_combines(self):
        for key, bad in (("period", "2023"), ("statement_scope", "separate"),
                          ("currency", "USD"), ("unit_scale", 1000)):
            identities = _identities()
            identities["net_sales"] = {**identities["net_sales"], key: bad}
            result = evaluate_altman_z_score(identities)
            self.assertEqual(result["status"], "insufficient_evidence", key)
            self.assertTrue(any(key in reason for reason in result["blocking_reasons"]), key)

    def test_non_positive_denominators_fail_closed(self):
        for name in ("total_assets", "total_liabilities"):
            result = evaluate_altman_z_score(_identities({name: 0}))
            self.assertEqual(result["status"], "insufficient_evidence", name)
            self.assertTrue(any("strictly positive" in reason for reason in result["blocking_reasons"]), name)

    def test_zone_boundaries_use_z_prime_bands_not_classic_z(self):
        # A classic-Z reader would call 2.5 "grey" too, but 1.9 "grey" vs Z' "grey" and
        # 2.95 differs: Z' safe starts at 2.90, classic Z at 2.99.
        self.assertEqual(evaluate_altman_z_score(_identities({"net_sales": 0, "retained_earnings": 0,
                                                               "ebit": 0, "owners_equity": 1}))["zone"], "distress")
        result = evaluate_altman_z_score(_identities())
        self.assertEqual(result["thresholds"], {"distress_below": DISTRESS_THRESHOLD, "safe_above": SAFE_THRESHOLD})

    def test_never_actionable_and_always_historical_only(self):
        for identities in (_identities(), {}):
            result = evaluate_altman_z_score(identities)
            self.assertFalse(result["is_actionable"])
            self.assertTrue(result["historical_only"])
            self.assertFalse(result["market_dependent"])

    def test_no_market_input_is_consumed(self):
        """Z' must never require a price/market-cap identity -- that is the whole reason
        this variant was chosen over the classic 1968 Z (see module docstring)."""
        for name in REQUIRED_IDENTITIES:
            self.assertNotIn("market", name)
            self.assertNotIn("price", name)
        self.assertEqual(evaluate_altman_z_score(_identities())["status"], "available")

    def test_malformed_input_never_raises(self):
        for bad in (None, {}, {"total_assets": None}, {"total_assets": {"value": "abc"}}, []):
            result = evaluate_altman_z_score(bad)
            self.assertEqual(result["status"], "insufficient_evidence")




class EntityTypeApplicabilityTests(unittest.TestCase):
    """Altman's corporate Z/Z' was estimated on non-financial firms. A bank's balance
    sheet has no operating-cycle current/non-current split and no meaningful asset
    turnover, so a complete set of bank identities must still not produce a score --
    and must say 'not_applicable', not 'insufficient_evidence'."""

    def test_financial_entity_types_are_not_applicable_even_with_complete_inputs(self):
        for entity_type in ("bank", "securities", "insurance", "finance_company", "BANK"):
            result = evaluate_altman_z_score(_identities(), entity_type=entity_type)
            self.assertEqual(result["status"], "not_applicable", entity_type)
            self.assertIsNone(result["score"], entity_type)
            self.assertIsNone(result["zone"], entity_type)
            self.assertEqual(result["missing_inputs"], [], "structural inapplicability is not an evidence gap")
            self.assertTrue(result["blocking_reasons"], entity_type)

    def test_corporate_and_unknown_entity_types_still_evaluate_normally(self):
        for entity_type in ("corporate", "unknown", ""):
            result = evaluate_altman_z_score(_identities(), entity_type=entity_type)
            self.assertEqual(result["status"], "available", entity_type)

    def test_default_entity_type_is_corporate(self):
        self.assertEqual(evaluate_altman_z_score(_identities())["status"], "available")

if __name__ == "__main__":
    unittest.main()
