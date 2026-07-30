import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import cited_evidence_backup as b
class BackupTests(unittest.TestCase):
 def fixture(self):
  temp=tempfile.TemporaryDirectory();r=Path(temp.name);(r/'x.pdf').write_bytes(b'x');h=hashlib.sha256(b'x').hexdigest();(r/'manifest.json').write_text(json.dumps({'records':[{'ticker':'HPG','reporting_period':'2024','evidence_type':'audited_consolidated_financial_statements','filename':'x.pdf','sha256':h,'evidence_id':'d'}]}));(r/'qualification_citations.jsonl').write_text(json.dumps({'evidence_id':'d','citation_id':'c'})+'\n');return temp,r
 def index(self,*_):return {'schema_version':'1','documents':[{'document_id':'d'}],'chunks':[{'citations':[{'citation_id':'c'}]}]}
 def test_determinism_corruption_missing_and_recovery(self):
  t,r=self.fixture();self.addCleanup(t.cleanup)
  with patch.object(b,'build_index',self.index),patch.object(b,'search',return_value={'state':'available','results':[]}):
   self.assertEqual(b.build_manifest(r,'t'),b.build_manifest(r,'t'))
   out=Path(t.name)/'backup';x=b.create_backup(r,out,'t');self.assertEqual(b.verify_restore(out)['status'],'recovered');(out/'x.pdf').write_bytes(b'bad');self.assertEqual(b.verify_restore(out)['diagnostics'][0]['code'],'source_hash_mismatch');(out/'x.pdf').unlink();self.assertEqual(b.verify_restore(out)['diagnostics'][0]['code'],'missing_file')
   report=b.run_report({'status':'success','backup_hash':'h'},{'status':'recovered'},{'status':'rejected','diagnostics':[{'code':'missing_file'}]});self.assertEqual(report['rejection_diagnostics'][0]['code'],'missing_file')
if __name__=='__main__':unittest.main()