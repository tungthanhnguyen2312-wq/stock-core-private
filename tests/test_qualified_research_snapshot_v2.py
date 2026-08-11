import json
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from export_ai_bundle import build_qualified_research_snapshot_v2_for_bundle
from qualified_research_snapshot_v2 import PRODUCTION_UNIVERSE, SCHEMA_VERSION, build, from_served_bundle

class SnapshotV2Tests(unittest.TestCase):
 def test_explicit_universe_and_deterministic_identity(self):
  bundle={"tickers":{"POW":{"ticker_capability_matrix":{"research":{"qualified_research_brief":{"status":"available"}}}}}}
  a=build(bundle,source_identity={"bundle":"served"}); b=build(bundle,source_identity={"bundle":"served"})
  self.assertEqual(a,b);self.assertEqual([x["ticker"] for x in a["tickers"]],list(PRODUCTION_UNIVERSE));self.assertNotIn("VCB",PRODUCTION_UNIVERSE)
  self.assertEqual(next(x for x in a["tickers"] if x["ticker"]=="POW")["research_status"],"available")
 def test_absent_production_ticker_is_explicit_unknown(self):
  row=next(x for x in build({"tickers":{}},source_identity={})["tickers"] if x["ticker"]=="QNS")
  self.assertEqual(row["research_status"],"unknown")
 def test_from_served_bundle_reconstructs_the_identity_build_produced_at_serve_time(self):
  served_bundle={"reference_session_date":"2026-08-07","tickers":{"POW":{"ticker_capability_matrix":{"research":{"qualified_research_brief":{"status":"available"}}}}}}
  expected=build(served_bundle,source_identity={"reference_session_date":"2026-08-07","bundle_generation":"export_ai_bundle"})
  self.assertEqual(from_served_bundle(served_bundle),expected)
 def test_from_served_bundle_is_a_pure_replay_not_a_new_generation(self):
  served_bundle={"reference_session_date":"2026-08-07","tickers":{}}
  self.assertEqual(from_served_bundle(served_bundle),from_served_bundle(served_bundle))
 def test_snapshot_preserves_explicit_existing_capability_states_without_market_inference(self):
  bundle={"tickers":{"HPG":{
   "ticker_capability_matrix":{"research":{"qualified_research_brief":{"status":"available","reason_codes":[]}},"market_actionable":{
    "raw_as_traded_price":{"status":"unavailable","authority_status":"PARTIAL","reason_codes":["raw_history_missing"]},
    "current_valuation":{"status":"blocked","authority_status":"BLOCKED","reason_codes":["qualified_current_inputs_missing"]},
    "generic_liquidity":{"status":"blocked","authority_status":"BLOCKED","reason_codes":["complete_market_composition_not_qualified"]},
   }},
   "foreign_flow":{"status":"available","reason_codes":[]},
   "qualified_research_brief":{"probability":0.9,"target_price":99999},
  }}}
  snapshot=build(bundle,source_identity={"reference_session_date":"2026-08-07"})
  row=next(item for item in snapshot["tickers"] if item["ticker"]=="HPG")
  self.assertEqual(snapshot["schema_version"],SCHEMA_VERSION)
  self.assertEqual(row["analysis_states"]["historical_research"]["status"],"available")
  self.assertEqual(row["analysis_states"]["current_valuation"]["status"],"blocked")
  self.assertEqual(row["analysis_states"]["generic_liquidity"]["reason_codes"],["complete_market_composition_not_qualified"])
  self.assertEqual(row["analysis_states"]["foreign_flow_value"]["status"],"available")
  serialized=json.dumps(snapshot,sort_keys=True)
  self.assertNotIn("target_price",serialized);self.assertNotIn("probability",serialized);self.assertNotIn("99999",serialized)
 def test_missing_capability_contract_stays_unknown_and_is_stable(self):
  bundle={"tickers":{"QNS":{}}}
  first=build(bundle,source_identity={});second=build(bundle,source_identity={})
  row=next(item for item in first["tickers"] if item["ticker"]=="QNS")
  self.assertEqual(first,second)
  self.assertTrue(all(state["status"]=="unknown" for state in row["analysis_states"].values()))
  self.assertNotIn("volume",json.dumps(first).lower())
 def test_producer_export_boundary_retains_the_current_v2_baseline(self):
  entries={"HPG":{"ticker_capability_matrix":{"research":{"qualified_research_brief":{"status":"available"}}}}}
  result=build_qualified_research_snapshot_v2_for_bundle(entries,"2026-08-07")
  expected=build({"tickers":entries},source_identity={"reference_session_date":"2026-08-07","bundle_generation":"export_ai_bundle"})
  self.assertEqual(result,expected)
if __name__=='__main__': unittest.main()
