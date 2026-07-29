import unittest
from vnm_shadow_backtest import run_shadow_backtest

def snap(**k):
 x={"ticker":"VNM","snapshot_id":"s","knowledge_cutoff":"2026-06-30T00:00:00Z","state":"partial","input_vintage":{"identity":"v"},"input_lineage":[{"lineage_id":"l"}],"ranking":{"dimensions":{"technical_current_market_readiness":{"state":"available"}}},"scenarios":{"records":{"bull":{"state":"available"}}}};x.update(k);return x
def row(d,p=100,**k):
 x={"trading_date":d,"raw_close":p,"volume":10,"price_basis":"raw_historical","volume_qualification":"qualified","price_source_id":"p"+d,"citation_id":"c"+d,"source_hash":"h"+d};x.update(k);return x
def costs():return {"cost_model_version":"1.0.0","commission_bps":5,"slippage_bps":5,"tax_bps":0}
def run(**k):
 x={"snapshots":[snap()],"raw_sessions":[row("2026-06-30"),row("2026-07-01",101),row("2026-07-02",102),row("2026-07-03",103),row("2026-07-04",104)],"benchmark_sessions":[row("2026-07-01",200),row("2026-07-04",202)],"costs":costs()};x.update(k);return run_shadow_backtest(**x)
class ShadowTests(unittest.TestCase):
 def test_timing_fill_exit_costs_benchmark(self):
  x=run();t=x["trades"][0];self.assertEqual(t["entry"]["fill_date"],"2026-07-01");self.assertEqual(t["exit"]["fill_date"],"2026-07-04");self.assertLess(t["net_return"],t["gross_return"]);self.assertAlmostEqual(x["metrics"]["benchmark_return"],.01)
 def test_determinism(self):self.assertEqual(run(),run())
 def test_missing_exit_and_benchmark_fail_closed(self):self.assertEqual(run(raw_sessions=[row("2026-07-01")])["state"],"unavailable");self.assertEqual(run(benchmark_sessions=[])["state"],"unavailable")
 def test_signal_and_raw_price_gates(self):self.assertEqual(run(snapshots=[snap(state="unavailable")])["state"],"unavailable");self.assertEqual(run(raw_sessions=[row("2026-07-01",price_basis="adjusted")])["state"],"unavailable")
 def test_no_same_session_or_future_leak(self):
  x=run(raw_sessions=[row("2026-06-30"),row("2026-07-01"),row("2026-07-02"),row("2026-07-03"),row("2026-07-04")]);self.assertEqual(x["trades"][0]["entry"]["fill_date"],"2026-07-01")
if __name__=="__main__":unittest.main()
