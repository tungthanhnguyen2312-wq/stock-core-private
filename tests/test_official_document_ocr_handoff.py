import hashlib,json,tempfile,unittest
from pathlib import Path
from official_document_ocr_handoff import *
class T(unittest.TestCase):
 def rec(self,d):p=Path(d)/'x.pdf';p.write_bytes(b'x');return {'document_id':'d','sha256':hashlib.sha256(b'x').hexdigest(),'relative_path':'x.pdf','extraction_status':'needs_ocr'}
 def test_select_hash_checkpoint_resume_atomic(self):
  with tempfile.TemporaryDirectory() as d:
   r=self.rec(d);Path(d,'official_document_acquisition_manifest.json').write_text(json.dumps({'records':[r]}));self.assertEqual(select_documents(Path(d),('d',))[0]['document_id'],'d');c=add_batch({},r,[(1,b'abc',b'\x9d')]);p=Path(d)/'s.json';atomic_write(p,c);self.assertEqual(load_checkpoint(p),c);self.assertEqual(add_batch(c,r,[(1,b'abc',b'')])['pages'],c['pages']);r['sha256']='0'*64;Path(d,'official_document_acquisition_manifest.json').write_text(json.dumps({'records':[r]}));self.assertRaisesRegex(ValueError,'source_hash_mismatch',select_documents,Path(d),('d',))
 def test_states_provenance_order(self):
  r={'document_id':'d','sha256':'h'};c=add_batch({},r,[(2,b'x',b''),(1,b'\x9d',b'')]);self.assertEqual([x['page'] for x in c['pages']],[1,2]);self.assertEqual(c['pages'][0]['status'],'invalid_utf8_ocr_text')
if __name__=='__main__':unittest.main()