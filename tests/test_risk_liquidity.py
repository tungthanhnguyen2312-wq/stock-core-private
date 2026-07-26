import unittest
from risk_liquidity import evaluate_market_risk as e
class T(unittest.TestCase):
 def test_deterministic(self):
  x={"price_adjustment":"qualified","volume_units":"qualified","ohlcv":[{"close":10,"volume":0},{"close":11,"volume":2},{"close":9,"volume":3}]};self.assertEqual(e(x,"x"),e(x,"x"));self.assertLess(e(x)["market_risk"]["maximum_drawdown"]["value"],0)
 def test_closed(self):self.assertEqual(e({})["market_risk"]["realized_volatility"]["state"],"unavailable")
if __name__=="__main__":unittest.main()
