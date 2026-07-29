import tempfile,unittest
from pathlib import Path
from temporal_evidence_registry import append,replay,query,validate,TemporalRegistryError

def rec(ticker="VNM",rid=None,**changes):
 r={"record_type":"qualification","ticker":ticker,"period":"2024","metric":"net_sales","source":"qualification","observation_id":"o","citation_id":"c","evidence_id":"e","document_hash":"h","lineage":{"supersedes":[]},"supersedes":[],"temporal":{"observed_at":None,"published_at":"2025-01-01","effective_at":None,"period_end":None,"calculated_at":"2025-01-02"}}
 r.update(changes)
 from temporal_evidence_registry import identity
 r["record_id"]=identity(r) if rid is None else rid
 return r
class TemporalRegistryTests(unittest.TestCase):
 def test_identity_idempotency_and_replay(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"s.jsonl";x=rec();self.assertEqual(append(p,[x])["added"],1);self.assertEqual(append(p,[x])["idempotent"],1);self.assertEqual(replay(p),replay(p))
 def test_conflict_and_temporal_semantics(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"s.jsonl";x=rec();append(p,[x]);y=dict(x);y["metric"]="changed";self.assertRaises(TemporalRegistryError,append,p,[y]);self.assertIsNone(replay(p)[0]["temporal"]["observed_at"])
 def test_missing_temporal_rejected(self):
  x=rec();x["temporal"]={};self.assertRaises(TemporalRegistryError,validate,x)
 def test_cross_ticker_query_and_isolation(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"s.jsonl";append(p,[rec("HPG"),rec("VNM"),rec("VCB")]);self.assertEqual(len(query(replay(p),ticker="VNM")),1)
 def test_supersession_preserved(self):
  x=rec(supersedes=["old"],lineage={"supersedes":["old"]});self.assertEqual(validate(x)["supersedes"],["old"])
if __name__=="__main__":unittest.main()
