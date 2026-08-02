import unittest
from unittest.mock import patch

from risk_liquidity import evaluate_market_risk as e

_FAKE_PIT_RESULT = {
    "status": "available",
    "metric_series": [{
        "beta_value": 0.5, "correlation_value": 0.4, "calculation_date": "2026-07-30",
        "metric_result_id": "fake", "knowledge_cutoff": None, "anchor_date": "2026-07-30",
        "ordered_pair_ids": [], "upstream_lineage": {},
    }],
}


class T(unittest.TestCase):
    def test_deterministic(self):
        x = {
            "price_adjustment": "qualified",
            "volume_units": "qualified",
            "ohlcv": [{"close": 10, "volume": 0}, {"close": 11, "volume": 2}, {"close": 9, "volume": 3}],
        }
        self.assertEqual(e(x, "x"), e(x, "x"))
        self.assertLess(e(x)["market_risk"]["maximum_drawdown"]["value"], 0)

    def test_closed(self):
        self.assertEqual(e({})["market_risk"]["realized_volatility"]["state"], "unavailable")
        self.assertEqual(e({})["market_risk"]["point_in_time_beta"]["state"], "unavailable")
        self.assertEqual(e({})["market_risk"]["point_in_time_correlation"]["state"], "unavailable")

    def test_hpg_and_vcb_remain_unavailable(self):
        hpg_res = e({"ticker": "HPG"})
        vcb_res = e({"ticker": "VCB"})
        self.assertEqual(hpg_res["market_risk"]["point_in_time_beta"]["state"], "unavailable")
        self.assertEqual(hpg_res["market_risk"]["point_in_time_correlation"]["state"], "unavailable")
        self.assertEqual(vcb_res["market_risk"]["point_in_time_beta"]["state"], "unavailable")
        self.assertEqual(vcb_res["market_risk"]["point_in_time_correlation"]["state"], "unavailable")

    def test_vnm_point_in_time_beta_correlation_is_actionable_follows_current_actionable_not_hardcoded_true(self):
        """Regression guard for a real bug found 2026-08-02: point_in_time_beta/correlation
        were hardcoded is_actionable=True whenever the underlying calculation had a value,
        completely ignoring the caller's current_actionable / global price-basis gate --
        unlike every sibling metric in this same function (realized_volatility etc.), which
        correctly gates on it. A value can legitimately exist (deterministic, lineage-
        tracked) while still not being investment-actionable when basis is unqualified."""
        with patch("risk_liquidity.calculate_point_in_time_beta_and_correlation", return_value=_FAKE_PIT_RESULT):
            unqualified = e({"ticker": "VNM", "current_actionable": False}, runtime_root=None)
            qualified = e({"ticker": "VNM", "current_actionable": True}, runtime_root=None)

        beta_u = unqualified["market_risk"]["point_in_time_beta"]
        corr_u = unqualified["market_risk"]["point_in_time_correlation"]
        self.assertEqual(beta_u["state"], "available")
        self.assertEqual(beta_u["value"], 0.5)
        self.assertFalse(beta_u["is_actionable"], "must not be actionable when current_actionable is False")
        self.assertTrue(beta_u["warnings"], "must warn when downgraded from computed-but-not-actionable")
        self.assertFalse(corr_u["is_actionable"])

        beta_q = qualified["market_risk"]["point_in_time_beta"]
        self.assertTrue(beta_q["is_actionable"], "must be actionable when current_actionable is True")
        self.assertEqual(qualified["market_risk"]["point_in_time_correlation"]["is_actionable"], True)


if __name__ == "__main__":
    unittest.main()
