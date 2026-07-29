import tempfile,unittest
from pathlib import Path
from vnm_historical_snapshot_reconstruction import reconstruct_and_replay

def record(cutoff="2026-06-30T00:00:00Z"):
 f={"value":1,"period_identity":{"period":"2024","period_type":"annual"},"statement_scope":"consolidated","currency":"VND","unit_scale":1,"source":"test","observation_ids":["o"],"citation_id":"c","evidence_id":"e"}
 entry={"fundamental_quality":{"models":{"financial_strength":{"result_state":"available","used_input_facts":{"net_income":f}}}},"relative_valuation":{"methods":{"pb":{"state":"available","is_actionable":True,"provenance":{}}}},"freshness":{"daily_prices":{"is_actionable":True},"technical_signals":{"is_actionable":True}},"analysis_readiness":{"domains":{"market_technical":{"state":"ready"}}},"ta_signal":{"above_sma50":True},"corporate_intelligence":{}}
 meta={"knowledge_cutoff":cutoff,"calculation_timestamp":"2026-07-29T00:00:00Z","input_vintage":{"identity":"v1","price_observation_cutoff":"2026-06-01T00:00:00Z","financial_statement_publication_cutoff":"2026-05-01T00:00:00Z","corporate_action_evidence_cutoff":"2026-05-01T00:00:00Z","market_risk_calculation_cutoff":"2026-06-01T00:00:00Z"}}
 scenario={"freshness":entry["freshness"],"readiness":entry["analysis_readiness"]["domains"],"technical":entry["ta_signal"]}
 lineage=[{"lineage_id":"l","source_hash":"h","citation_id":"c","observed_date":"2026-05-01T00:00:00Z","published_date":"2026-05-01T00:00:00Z","effective_date":"2026-05-01T00:00:00Z","calculation_date":"2026-06-01T00:00:00Z","derived":False}]
 return {"ticker":"VNM","metadata":meta,"opportunity_entry":entry,"scenario_input":scenario,"input_lineage":lineage,"market_risk":{"point_in_time_beta":{"state":"available"}}}
class ReconstructionTests(unittest.TestCase):
 def test_reconstruct_persist_replay_idempotent(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"v.jsonl";a=reconstruct_and_replay([record()],p);b=reconstruct_and_replay([record()],p);self.assertEqual(a["snapshots_persisted"],1);self.assertEqual(b["snapshots_persisted"],1);self.assertEqual(a["replay"],b["replay"])
 def test_future_known_input_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   x=record();x["input_lineage"][0]["published_date"]="2026-07-01T00:00:00Z";r=reconstruct_and_replay([x],Path(d)/"v.jsonl");self.assertEqual(r["snapshots_reconstructed"],0);self.assertIn("future_data_leakage",r["unavailable"][0]["reason"])
 def test_incomplete_input_and_determinism(self):
  with tempfile.TemporaryDirectory() as d:
   x=record();del x["scenario_input"];r=reconstruct_and_replay([x],Path(d)/"v.jsonl");self.assertEqual(r["snapshots_reconstructed"],0)
 def test_shadow_integration_is_fixed_contract(self):
  with tempfile.TemporaryDirectory() as d:
   rows=[{"trading_date":d,"raw_close":p,"volume":10,"price_basis":"raw_historical","volume_qualification":"qualified","price_source_id":"p"+d,"citation_id":"c"+d,"source_hash":"h"+d} for d,p in [("2026-06-30",100),("2026-07-01",101),("2026-07-02",102),("2026-07-03",103),("2026-07-04",104)]];r=reconstruct_and_replay([record()],Path(d)/"v.jsonl",raw_sessions=rows,benchmark_sessions=[rows[1],rows[4]],costs={"cost_model_version":"1.0.0","commission_bps":5,"slippage_bps":5,"tax_bps":0});self.assertEqual(r["shadow"]["metrics"]["trade_count"],1)
if __name__=="__main__":unittest.main()
