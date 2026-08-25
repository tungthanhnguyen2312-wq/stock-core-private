from __future__ import annotations
import copy,json,tempfile,unittest
from pathlib import Path
import current_research_decision_packet as packet
import export_ai_bundle as bundle

ROOT=Path(__file__).resolve().parents[1]
PATHS={"opportunity":ROOT/"operations-review/current-opportunity-prioritization-v1-20260824/current_opportunity_prioritization_artifact.json","scenario":ROOT/"operations-review/current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json","risk_register":ROOT/"operations-review/current-research-risk-register-v1/current_research_risk_register_artifact.json","market_sector":ROOT/"operations-review/current-market-sector-leadership-context-v1-20260825/current_market_sector_leadership_context_artifact.json","financial_momentum":ROOT/"operations-review/current-financial-momentum-context-v1/current_financial_momentum_context_artifact.json","corporate_event":ROOT/"operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json","valuation":ROOT/"operations-review/market-wide-current-valuation-research-scaleout-v1/market_wide_current_valuation_artifact.json","historical":ROOT/"operations-review/market-wide-historical-research-context-v1-20260824/market_wide_historical_research_context_artifact.json"}
def inputs():return {n:json.loads(p.read_bytes().decode("utf-8")) for n,p in PATHS.items()}
class PacketTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.inputs=inputs();cls.artifact=packet.build_artifact(**cls.inputs)
 def test_preserves_decision_and_component_semantics(self):
  row=self.artifact["records"]["AAA"]; source=self.inputs["opportunity"]["records"]["AAA"]
  self.assertEqual(row["current_decision_context"]["priority_tier"],source["priority_tier"]);self.assertEqual(row["current_decision_context"]["entry_action"],source["entry_action"]);self.assertEqual(row["current_decision_context"]["eligible_strategies"],source["eligible_strategies"])
  self.assertEqual(row["components"]["scenario_context"]["scenario_disposition"],self.inputs["scenario"]["records"]["AAA"]["scenario_disposition"]);self.assertEqual(row["components"]["risk_register"]["risk_register_status"],self.inputs["risk_register"]["records"]["AAA"]["risk_register_status"]);self.assertEqual(row["components"]["valuation_context"]["metrics"]["market_cap"]["status"],self.inputs["valuation"]["records"]["AAA"]["metrics"]["market_cap"]["status"])
 def test_determinism_temporal_boundaries_and_missing_locality(self):
  self.assertEqual(self.artifact["artifact_sha256"],packet.content_identity(self.artifact)["artifact_sha256"]);packet.replay(self.artifact)
  self.assertEqual(self.artifact["component_manifest"]["historical"]["source_as_of"],"2026-08-24");self.assertEqual(self.artifact["component_manifest"]["valuation"]["source_as_of"],"2026-08-21")
  bad=copy.deepcopy(self.inputs["financial_momentum"]);bad["coverage"]["universe_denominator"]=0
  self.assertEqual(packet._manifest("financial_momentum",bad)["status"],"MALFORMED");self.assertEqual(self.artifact["records"]["AAA"]["current_decision_context"]["entry_action"],self.inputs["opportunity"]["records"]["AAA"]["entry_action"])
 def test_no_authority_upgrade_and_opt_in_attachment(self):
  self.assertTrue(self.artifact["authority_boundary"]["no_global_authority_score"]);self.assertFalse(self.artifact["authority_boundary"]["is_actionable"]);self.assertNotIn("recommendation",self.artifact["records"]["AAA"])
  entries={"AAA":{"research_priority":"keep","entry_action":"keep","strategy_eligibility":"keep"}};original=copy.deepcopy(entries);self.assertEqual(bundle.attach_current_research_decision_packet(entries,False,"x"),original)
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"p.json";p.write_text(json.dumps(self.artifact),encoding="utf-8");out=bundle.attach_current_research_decision_packet(entries,True,str(p));self.assertFalse(out["AAA"]["current_research_decision_packet"]["is_actionable"]);self.assertEqual(out["AAA"]["entry_action"],"keep")
if __name__=="__main__":unittest.main()
