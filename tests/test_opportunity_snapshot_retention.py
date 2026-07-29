import tempfile,unittest
from pathlib import Path
from opportunity_snapshot_retention import RetentionError,append_snapshot,replay_vnm,validate_snapshot

def snapshot(cutoff="2026-06-30T00:00:00Z",sid="vnm-pit-a"):
 vintage={"identity":"v1","price_observation_cutoff":"2026-06-01T00:00:00Z","financial_statement_publication_cutoff":"2026-05-01T00:00:00Z","corporate_action_evidence_cutoff":"2026-05-01T00:00:00Z","market_risk_calculation_cutoff":"2026-06-01T00:00:00Z"}
 return {"schema_version":"1.0.0","snapshot_id":sid,"ticker":"VNM","knowledge_cutoff":cutoff,"snapshot_identity":{"identity_version":"1.0.0","ticker":"VNM","knowledge_cutoff":cutoff,"calculation_contract_version":"1.0.0","ranking_contract_version":"1.0.0","scenario_contract_version":"1.1.0","input_vintage_identity":"v1"},"input_vintage":vintage,"input_lineage":[{"lineage_id":"l","source_hash":"h","citation_id":"c","observed_date":"2026-05-01T00:00:00Z","published_date":"2026-05-01T00:00:00Z","effective_date":"2026-05-01T00:00:00Z","calculation_date":"2026-06-01T00:00:00Z"}],"ranking":{"dimensions":{}},"scenarios":{"records":{}},"market_risk":{},"backtest_outputs":[]}
class RetentionTests(unittest.TestCase):
 def test_append_idempotent_and_deterministic_replay(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"vnm.jsonl";self.assertEqual(append_snapshot(p,snapshot()),"appended");self.assertEqual(append_snapshot(p,snapshot()),"idempotent");self.assertEqual(replay_vnm(p),replay_vnm(p))
 def test_conflicting_duplicate_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"v.jsonl";append_snapshot(p,snapshot());x=snapshot();x["ranking"]={"changed":True};self.assertRaises(RetentionError,append_snapshot,p,x)
 def test_replay_orders_cutoff(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"v.jsonl";append_snapshot(p,snapshot("2026-06-30T00:00:00Z","vnm-pit-b"));append_snapshot(p,snapshot("2026-06-29T00:00:00Z","vnm-pit-a"));self.assertEqual([x["snapshot_id"] for x in replay_vnm(p)],["vnm-pit-a","vnm-pit-b"])
 def test_future_evidence_excluded(self):
  x=snapshot();x["input_lineage"][0]["published_date"]="2026-07-01T00:00:00Z";self.assertRaises(RetentionError,validate_snapshot,x)
 def test_malformed_and_mixed_vintage_rejected(self):
  x=snapshot();x["knowledge_cutoff"]="bad";self.assertRaises(RetentionError,validate_snapshot,x);x=snapshot();x["input_vintage"]["identity"]="v2";self.assertRaises(RetentionError,validate_snapshot,x)
 def test_missing_lineage_and_legacy_rejected(self):
  x=snapshot();x["input_lineage"]=[];self.assertRaises(RetentionError,validate_snapshot,x);self.assertRaises(RetentionError,validate_snapshot,{"snapshot_id":"legacy"})
if __name__=="__main__":unittest.main()
