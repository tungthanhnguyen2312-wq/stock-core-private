import unittest
from risk_liquidity import evaluate_market_risk as e


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


if __name__ == "__main__":
    unittest.main()
