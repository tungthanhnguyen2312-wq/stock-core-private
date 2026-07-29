import tempfile,unittest
from pathlib import Path
from corporate_action_evidence_registry import *
def rec(**x):
 r={"schema_version":"1","ticker":"VNM","provider":"VCI","provider_event_id":"e","action_type":"cash_dividend","event_code":"DIV","cash_amount":1,"share_ratio":None,"temporal":dict.fromkeys(FIELDS),"source_hash":"h","citation_id":None,"citation_reason":"partial","qualification":"partial","coverage_limitation":"partial","supersedes":[],"adjustment_provenance":"not_generated"};r.update(x);r["record_id"]=identity(r);return r
class Tests(unittest.TestCase):
 def test_append_idempotent_replay_query(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"x";r=rec();self.assertEqual(append(p,[r])["added"],1);self.assertEqual(append(p,[r])["idempotent"],1);self.assertEqual(len(query(replay(p),ticker="VNM",action_type="cash_dividend")),1)
 def test_conflict_ratio_and_temporal_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"x";r=rec();append(p,[r]);bad=dict(r);bad["cash_amount"]=2;self.assertRaises(CorporateActionRegistryError,append,p,[bad]);self.assertRaises(CorporateActionRegistryError,validate,rec(share_ratio=-1));self.assertRaises(CorporateActionRegistryError,validate,rec(temporal={}))
 def test_partial_citation_and_no_adjustment(self):
  r=rec();self.assertIsNone(r["citation_id"]);self.assertEqual(r["adjustment_provenance"],"not_generated")
 def test_vcb_official_promotion_and_factor(self):
  p={"ticker":"VCB","provider":"VCI","provider_event_id":"6708f3f70ec61045ab800869","exercise_ratio":0.495,"record_date":"2025-03-13"};o={"ticker":"VCB","provider_event_id":"6708f3f70ec61045ab800869","ratio":0.495,"approval_date":"2025-01-15","record_date":"2025-03-13","issuance_date":"2025-05-09","listing_date":"2025-05-09","completion_date":"2025-05-09","lifecycle":"completed","source_hash":"8a79e8b0ca1381cd1cac12a82818f382052e55a323e9386ebbd54a7f93e712ef","citation_id":"vsdc-182319","citation":"VSDC notice 182319","observed_at":"2026-07-29T00:00:00Z"};r=promote_official_stock_dividend(p,o);self.assertEqual(r["qualification"],"qualified");f=shadow_share_factor(r);self.assertEqual(f["share_quantity_multiplier"],1.495);self.assertEqual(f["lineage"]["source_hash"],o["source_hash"])
 def test_official_promotion_rejects_conflict(self):
  p={"ticker":"VCB","provider_event_id":"x","exercise_ratio":.495,"record_date":"2025-03-13"};o={"ticker":"VCB","provider_event_id":"x","ratio":.4,"approval_date":"a","record_date":"2025-03-13","issuance_date":"i","listing_date":"l","completion_date":"c","lifecycle":"completed","source_hash":"h","citation_id":"c","citation":"x"};self.assertRaises(CorporateActionRegistryError,promote_official_stock_dividend,p,o)
if __name__=="__main__":unittest.main()