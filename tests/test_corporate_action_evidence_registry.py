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
if __name__=="__main__":unittest.main()