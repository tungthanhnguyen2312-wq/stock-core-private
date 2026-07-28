"""Unit tests for price_basis_contract.py.

Validates price basis qualification, raw vs. adjusted non-mixing enforcement,
independent volume qualification, and metric provenance propagation.
"""

from __future__ import annotations

import unittest

from price_basis_contract import (
    PriceBasis,
    PriceBasisMismatchError,
    VolumeBasis,
    derive_metric_basis,
    qualify_price_basis,
    qualify_volume_basis,
    validate_basis_compatibility,
)


class PriceBasisContractTests(unittest.TestCase):
    def test_raw_basis_remains_raw(self):
        contract = qualify_price_basis("raw", verified=True, adjustment_source="upstream_feed")
        self.assertEqual(contract["price_basis"], PriceBasis.RAW.value)
        self.assertTrue(contract["price_basis_verified"])
        self.assertTrue(contract["is_actionable"])
        self.assertEqual(contract["adjustment_source"], "upstream_feed")

    def test_adjusted_basis_remains_adjusted(self):
        contract = qualify_price_basis("adjusted", verified=True, adjustment_source="corporate_actions_pipeline")
        self.assertEqual(contract["price_basis"], PriceBasis.ADJUSTED.value)
        self.assertTrue(contract["price_basis_verified"])
        self.assertTrue(contract["is_actionable"])
        self.assertEqual(contract["adjustment_source"], "corporate_actions_pipeline")

    def test_unknown_basis_fails_closed(self):
        # Unverified "raw" or "unknown" returns unknown & non-actionable
        contract = qualify_price_basis("raw", verified=False)
        self.assertEqual(contract["price_basis"], PriceBasis.UNKNOWN.value)
        self.assertFalse(contract["price_basis_verified"])
        self.assertFalse(contract["is_actionable"])
        self.assertIsNone(contract["adjustment_source"])

    def test_raw_and_adjusted_mixing_rejected_in_strict_mode(self):
        raw_contract = qualify_price_basis("raw", verified=True)
        adj_contract = qualify_price_basis("adjusted", verified=True)

        with self.assertRaises(PriceBasisMismatchError):
            validate_basis_compatibility(raw_contract, adj_contract, strict=True)

        compat = validate_basis_compatibility(raw_contract, adj_contract, strict=False)
        self.assertFalse(compat["is_compatible"])
        self.assertEqual(compat["reason"], "mixed_raw_and_adjusted_basis")

    def test_unknown_basis_compatibility(self):
        unknown_contract = qualify_price_basis("unknown", verified=False)
        raw_contract = qualify_price_basis("raw", verified=True)

        compat = validate_basis_compatibility(unknown_contract, raw_contract, strict=False)
        self.assertFalse(compat["is_compatible"])
        self.assertEqual(compat["reason"], "unverified_or_unknown_basis")

    def test_volume_basis_qualified_independently(self):
        vol_contract = qualify_volume_basis("raw_shares_traded", verified=True)
        self.assertEqual(vol_contract["volume_basis"], VolumeBasis.RAW_SHARES_TRADED.value)
        self.assertTrue(vol_contract["volume_basis_verified"])
        self.assertTrue(vol_contract["price_volume_basis_decoupled"])

        unverified_vol = qualify_volume_basis("adjusted_volume", verified=False)
        self.assertEqual(unverified_vol["volume_basis"], VolumeBasis.UNKNOWN.value)
        self.assertFalse(unverified_vol["volume_basis_verified"])

    def test_derived_metric_basis_propagation(self):
        price_contract = qualify_price_basis("raw", verified=True)
        vol_contract = qualify_volume_basis("raw_shares_traded", verified=True)

        derived = derive_metric_basis(price_contract, vol_contract, metric_name="sma20")
        self.assertEqual(derived["metric_name"], "sma20")
        self.assertEqual(derived["price_basis"], PriceBasis.RAW.value)
        self.assertTrue(derived["is_actionable"])
        self.assertEqual(derived["qualification_status"], "qualified")

        # Unverified price source yields unverified derived metric
        unverified_price = qualify_price_basis("unknown", verified=False)
        derived_unverified = derive_metric_basis(unverified_price, vol_contract, metric_name="rsi14")
        self.assertFalse(derived_unverified["is_actionable"])
        self.assertEqual(derived_unverified["qualification_status"], "unverified_or_unknown_basis")
        self.assertTrue(len(derived_unverified["warnings"]) > 0)

    def test_deterministic_output(self):
        res1 = qualify_price_basis("raw", verified=True)
        res2 = qualify_price_basis("raw", verified=True)
        self.assertEqual(res1, res2)


if __name__ == "__main__":
    unittest.main()
