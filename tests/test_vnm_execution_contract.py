import unittest
from vnm_execution_contract import resolve_vnm_fill

def signal(cutoff="2026-06-30T00:00:00Z"): return {"ticker":"VNM","snapshot_id":"s1","knowledge_cutoff":cutoff,"state":"partial"}
def costs(**overrides):
 x={"cost_model_version":"1.0.0","commission_bps":5,"slippage_bps":10,"tax_bps":0};x.update(overrides);return x
def row(day="2026-07-01",**overrides):
 x={"trading_date":day,"raw_close":81.0,"volume":10.0,"price_basis":"raw_historical","volume_qualification":"qualified","price_source_id":"p","citation_id":"c","source_hash":"h"};x.update(overrides);return x
class ExecutionContractTests(unittest.TestCase):
 def test_next_session_raw_fill_and_determinism(self):
  a=resolve_vnm_fill(signal=signal(),raw_sessions=[row()],costs=costs());b=resolve_vnm_fill(signal=signal(),raw_sessions=[row()],costs=costs());self.assertEqual(a,b);self.assertEqual(a["fill_date"],"2026-07-01");self.assertEqual(a["price_basis"],"raw_historical_only");self.assertEqual(a["backtest_outputs"],[])
 def test_same_session_is_never_a_fill(self):
  x=resolve_vnm_fill(signal=signal(),raw_sessions=[row("2026-06-30"),row("2026-07-01")],costs=costs());self.assertEqual(x["fill_date"],"2026-07-01")
 def test_adjusted_price_is_rejected(self):
  x=resolve_vnm_fill(signal=signal(),raw_sessions=[row(price_basis="adjusted")],costs=costs());self.assertEqual(x["state"],"unavailable");self.assertEqual(x["reason"],"no_tradable_session_within_lag")
 def test_missing_session_and_lag_fail_closed(self):
  x=resolve_vnm_fill(signal=signal(),raw_sessions=[row("2026-06-30")],costs=costs());self.assertEqual(x["reason"],"no_next_eligible_trading_session")
 def test_zero_missing_volume_and_invalid_price_rejected(self):
  for bad in (row(volume=0),row(volume=None),row(raw_close=0)):
   x=resolve_vnm_fill(signal=signal(),raw_sessions=[bad],costs=costs());self.assertEqual(x["state"],"unavailable")
 def test_unsupported_costs_and_unavailable_signal(self):
  self.assertEqual(resolve_vnm_fill(signal=signal(),raw_sessions=[row()],costs=costs(commission_bps=-1))["reason"],"unsupported_cost_parameter:commission_bps");self.assertEqual(resolve_vnm_fill(signal={**signal(),"state":"unavailable"},raw_sessions=[row()],costs=costs())["reason"],"signal_unavailable")
 def test_lineage_and_no_prohibited_outputs(self):
  x=resolve_vnm_fill(signal=signal(),raw_sessions=[row()],costs=costs());self.assertIn("source_hash",x["price_source_lineage"]);self.assertNotIn("adjusted_close",x);self.assertNotIn("recommendation",x);self.assertNotIn("returns",x)
if __name__=="__main__":unittest.main()
