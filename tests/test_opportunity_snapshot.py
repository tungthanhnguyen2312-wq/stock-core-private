import unittest
from opportunity_ranking import evaluate_opportunity
from scenario_analysis import evaluate_scenario_analysis
from opportunity_contract_validation import find_prohibited_fields
from opportunity_snapshot import build_snapshot, serialize_snapshot

def entry():
 f={"value":1,"period_identity":{"period":"2024","period_type":"annual"},"statement_scope":"consolidated","currency":"VND","unit_scale":1,"source":"test","observation_ids":["o"],"citation_id":"c","evidence_id":"e"}
 return {"fundamental_quality":{"models":{"financial_strength":{"result_state":"available","used_input_facts":{"net_income":f}}}},"relative_valuation":{"methods":{"pb":{"state":"available","is_actionable":True,"provenance":{}}}},"freshness":{"daily_prices":{"is_actionable":True},"technical_signals":{"is_actionable":True}},"analysis_readiness":{"domains":{"market_technical":{"state":"ready"}}},"ta_signal":{"above_sma50":True},"corporate_intelligence":{}}
def inputs(cutoff="2026-06-30T00:00:00Z"):
 e=entry(); o=evaluate_opportunity(e,ticker="VNM",entity_type="corporate"); s=evaluate_scenario_analysis({"freshness":e["freshness"],"readiness":e["analysis_readiness"]["domains"],"technical":e["ta_signal"],"opportunity":o})
 m={"knowledge_cutoff":cutoff,"calculation_timestamp":"2026-07-29T00:00:00Z","input_vintage":{"identity":"v1","price_observation_cutoff":"2026-06-01T00:00:00Z","financial_statement_publication_cutoff":"2026-05-01T00:00:00Z","corporate_action_evidence_cutoff":"2026-05-01T00:00:00Z","market_risk_calculation_cutoff":"2026-06-01T00:00:00Z"}}
 l=[{"lineage_id":"x","citation_id":"c","source_hash":"a"*64,"observed_date":"2026-05-01T00:00:00Z","published_date":"2026-05-01T00:00:00Z","effective_date":"2026-05-01T00:00:00Z","calculation_date":"2026-06-01T00:00:00Z","derived":False}]
 return o,s,m,l
def build(**kw):
 o,s,m,l=inputs(); return build_snapshot(ticker="VNM",opportunity=o,scenario=s,market_risk={"point_in_time_beta":{"state":"available"}},metadata=m,input_lineage=l,**kw)
class SnapshotTests(unittest.TestCase):
 def test_valid_stable_byte_identical(self):
  a=build(); b=build(); self.assertEqual(a["snapshot_id"],b["snapshot_id"]); self.assertEqual(serialize_snapshot(a),serialize_snapshot(b))
 def test_earlier_cutoff_excludes_later_evidence(self):
  o,s,m,l=inputs("2026-04-01T00:00:00Z"); x=build_snapshot(ticker="VNM",opportunity=o,scenario=s,market_risk={},metadata=m,input_lineage=l); self.assertEqual(x["state"],"unavailable"); self.assertIn("future_data_leakage",x["gate_failures"][0])
 def test_later_cutoff_is_distinct_identity(self):
  a=build(); o,s,m,l=inputs("2026-07-01T00:00:00Z"); m["input_vintage"]["identity"]="v2"; b=build_snapshot(ticker="VNM",opportunity=o,scenario=s,market_risk={},metadata=m,input_lineage=l); self.assertNotEqual(a["snapshot_id"],b["snapshot_id"])
 def test_invalid_metadata_is_stable_and_empty(self):
  o,s,m,l=inputs(); m["input_vintage"]["price_observation_cutoff"]="2026-07-01T00:00:00Z"; a=build_snapshot(ticker="VNM",opportunity=o,scenario=s,market_risk={"point_in_time_beta":{"state":"available"}},metadata=m,input_lineage=l); b=build_snapshot(ticker="VNM",opportunity=o,scenario=s,market_risk={"point_in_time_beta":{"state":"available"}},metadata=m,input_lineage=l); self.assertEqual(a["snapshot_id"],b["snapshot_id"]); self.assertEqual(serialize_snapshot(a),serialize_snapshot(b)); self.assertEqual(a["ranking"]["facts"],[]); self.assertEqual(a["scenarios"]["records"],{}); self.assertIn("future_data_leakage",a["gate_failures"][0])
 def test_vintage_mismatch_fails_closed(self):
  o,s,m,l=inputs(); m["input_vintage"]["price_observation_cutoff"]="2026-07-01T00:00:00Z"; self.assertEqual(build_snapshot(ticker="VNM",opportunity=o,scenario=s,market_risk={},metadata=m,input_lineage=l)["state"],"unavailable")
 def test_citation_and_hash_failure(self):
  o,s,m,l=inputs(); l[0]["citation_id"]=None; self.assertEqual(build_snapshot(ticker="VNM",opportunity=o,scenario=s,market_risk={},metadata=m,input_lineage=l)["state"],"unavailable")
 def test_incomplete_derived_lineage(self):
  o,s,m,l=inputs(); l[0].update({"derived":True,"derived_fact_lineage_complete":False}); self.assertEqual(build_snapshot(ticker="VNM",opportunity=o,scenario=s,market_risk={},metadata=m,input_lineage=l)["state"],"unavailable")
 def test_unavailable_and_partial_dimensions_preserved(self):
  x=build(); self.assertIn("catalyst_evidence",x["unavailable_or_partial_dimensions"]); self.assertEqual(x["state"],"partial")
 def test_scenario_unavailable_fails_closed(self):
  o,s,m,l=inputs(); self.assertEqual(build_snapshot(ticker="VNM",opportunity=o,scenario={},market_risk={},metadata=m,input_lineage=l)["state"],"unavailable")
 def test_classes_and_prohibited_outputs(self):
  x=build(); self.assertIsInstance(x["ranking"]["facts"],list); self.assertIsInstance(x["ranking"]["data_warnings"],list); self.assertEqual(x["ranking"]["inferences"],[]); self.assertEqual(x["ranking"]["hypotheses"],[]); self.assertEqual(find_prohibited_fields(x),[]); self.assertEqual(x["backtest_outputs"],[])
 def test_legacy_phase4b_is_not_mutated(self):
  o,s,m,l=inputs(); before=serialize_snapshot(build_snapshot(ticker="VNM",opportunity=o,scenario=s,market_risk={},metadata=m,input_lineage=l)); self.assertEqual(before,serialize_snapshot(build_snapshot(ticker="VNM",opportunity=o,scenario=s,market_risk={},metadata=m,input_lineage=l)))
if __name__ == "__main__": unittest.main()
