import unittest
from scenario_analysis import evaluate_scenario_analysis as e
class T(unittest.TestCase):
 def test_current_deterministic(self):
  x={"freshness":{"daily_prices":{"is_actionable":True},"technical_signals":{"is_actionable":True}},"readiness":{"market_technical":{"state":"ready"}},"technical":{"above_sma50":True}};self.assertEqual(e(x,"x"),e(x,"x"));self.assertTrue(e(x)["scenarios"]["bull"]["is_actionable"])
 def test_fail_closed(self):
  x={"corporate_events":{"coverage_status":"partial_unqualified_50_row_cap"}};a=e(x);self.assertEqual(a["state"],"unknown");self.assertIn("corporate_events_partial_unqualified_50_row_cap",a["data_warnings"])
if __name__=="__main__":unittest.main()
