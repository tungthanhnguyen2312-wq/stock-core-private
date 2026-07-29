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
 def test_promotion_preserves_null_and_rejects_conflict(self):
  from temporal_evidence_registry import _promoted_temporal
  base=rec();doc={"publication_date":"2025-01-01"};temporal,reasons=_promoted_temporal(base,doc,{"verified_at":"2025-01-02"});self.assertEqual(temporal["published_at"],"2025-01-01");self.assertIsNone(temporal["period_end"]);self.assertIn("period_end",reasons);bad=rec();bad["temporal"]["published_at"]="2024-01-01";self.assertRaises(TemporalRegistryError,_promoted_temporal,bad,doc,{})
 def test_promotion_keeps_lineage(self):
  from temporal_evidence_registry import identity
  x=rec();x["record_type"]="temporal_promotion";x["base_record_id"]="base";x["temporal_reasons"]={};del x["record_id"];x["record_id"]=identity(x);self.assertEqual(validate(x)["citation_id"],"c")
 def test_direct_promotion_is_deterministic_and_idempotent(self):
  from unittest.mock import patch
  from temporal_evidence_registry import promote_temporal_metadata
  base=rec(evidence_id="doc",citation_id="cite")
  sources=({"doc":{"publication_date":"2025-01-01"}},{"cite":{"verified_at":"2025-01-02"}})
  with patch("temporal_evidence_registry._sidecar_temporal_sources",return_value=sources):
   first=promote_temporal_metadata([base],Path("unused"));second=promote_temporal_metadata([base],Path("unused"))
  self.assertEqual(len(first),1);self.assertEqual(first,second);self.assertEqual(first[0]["citation_id"],"cite");self.assertIn("period_end",first[0]["temporal_reasons"])
 def test_replay_parity_exact_and_expected_enrichment(self):
  from temporal_evidence_registry import _promoted_temporal,classify_replay_parity,identity
  base=rec();docs={"e":{"publication_date":"2025-01-01"}};citations={"c":{"verified_at":"2025-01-02"}}
  exact=classify_replay_parity([base],[base],docs,citations);self.assertEqual(exact["EXACT"],1)
  temporal,reasons=_promoted_temporal(base,docs["e"],citations["c"]);overlay={"record_type":"temporal_promotion","base_record_id":base["record_id"],"ticker":base["ticker"],"period":base["period"],"metric":base["metric"],"source":base["source"],"qualification_status":base.get("qualification_status"),"observation_id":base["observation_id"],"citation_id":base["citation_id"],"evidence_id":base["evidence_id"],"document_hash":base["document_hash"],"lineage":base["lineage"],"supersedes":base["supersedes"],"temporal":temporal,"temporal_reasons":reasons};overlay["record_id"]=identity(overlay)
  result=classify_replay_parity([base],[base,overlay],docs,citations);self.assertEqual(result["EXPECTED_ENRICHMENT"],1);self.assertIsNone(overlay["temporal"]["period_end"]);self.assertIn("period_end",overlay["temporal_reasons"])
 def test_replay_parity_rejects_conflict_and_reports_extra(self):
  from temporal_evidence_registry import classify_replay_parity
  base=rec();broken=dict(base);broken["document_hash"]="different";self.assertRaises(TemporalRegistryError,classify_replay_parity,[base],[broken],{}, {})
  extra=rec("HPG");result=classify_replay_parity([base],[base,extra],{},{});self.assertEqual(result["UNEXPECTED_EXTRA"],1)
 def test_replay_parity_hash_is_stable_on_repeated_replay(self):
  import hashlib
  from temporal_evidence_registry import canonical
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"s.jsonl";x=rec();append(p,[x]);first=replay(p);append(p,[x]);second=replay(p)
  self.assertEqual(hashlib.sha256(canonical(first)).hexdigest(),hashlib.sha256(canonical(second)).hexdigest())
if __name__=="__main__":
 unittest.main()
