import hashlib,json,tempfile,unittest
from pathlib import Path
from evidence_registry import EvidenceRegistry, main

def h(b): return hashlib.sha256(b).hexdigest()
def write(root):
 e=root/'data'/'official-evidence'; e.mkdir(parents=True); docs=[]
 for t in ('HPG','VNM','VCB'):
  b=(t+' pdf').encode(); fn=t+'.pdf'; (e/fn).write_bytes(b); docs.append({'evidence_id':t+'e','ticker':t,'filename':fn,'sha256':h(b),'qualification_state':'qualified'})
 (e/'manifest.json').write_text(json.dumps({'schema_version':'1.0.0','records':docs}))
 rows=[{'ticker':'HPG','reporting_period':'2024','identity_type':'period_end_shares_outstanding','citation_id':'h1','evidence_id':'HPGe'}, {'ticker':'VNM','reporting_period':'2024','identity_type':'period_end_shares_outstanding','citation_id':'v1','evidence_id':'VNMe'}, {'ticker':'VCB','reporting_period':'2024','identity_type':'weighted_average_basic_shares_outstanding','citation_id':'b1','evidence_id':'VCBe'}]
 (e/'share_basis_citations.jsonl').write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
 return e
class RegistryTests(unittest.TestCase):
 def test_coexistence_queries_and_determinism(self):
  with tempfile.TemporaryDirectory() as d:
   r=EvidenceRegistry(Path(d)).load(); write(Path(d)); r=EvidenceRegistry(Path(d)).load()
   self.assertEqual(len(r.query(ticker='HPG',period='2024')),1); self.assertEqual(r.query(ticker='VCB',metric='weighted_average_basic_shares_outstanding'),r.query(ticker='VCB',metric='weighted_average_basic_shares_outstanding')); self.assertEqual(r.issues,[])
 def test_integrity_fail_closed(self):
  with tempfile.TemporaryDirectory() as d:
   e=write(Path(d)); rows=[json.loads(x) for x in (e/'share_basis_citations.jsonl').read_text().splitlines()]; rows.append({'ticker':'VCB','reporting_period':'2024','identity_type':'unsupported','citation_id':'x','evidence_id':'missing'}); (e/'share_basis_citations.jsonl').write_text('\n'.join(json.dumps(x) for x in rows)); r=EvidenceRegistry(Path(d)).load(); self.assertTrue(any(x['reason']=='dangling_evidence' for x in r.issues)); self.assertTrue(any(x['reason']=='unsupported_metric_semantics' for x in r.issues))
 def test_cli_requires_explicit_output(self):
  with tempfile.TemporaryDirectory() as d:
   write(Path(d)); out=Path(d)/'out.json'; self.assertEqual(main(['--runtime-root',d,'--output',str(out)]),0); self.assertTrue(out.exists())
if __name__=='__main__': unittest.main()