import hashlib,io,json,tempfile,unittest
from pathlib import Path
from official_document_ocr_handoff import *
class T(unittest.TestCase):
 def test_console_is_utf8_safe(self):
  raw=io.BytesIO();stream=io.TextIOWrapper(raw,encoding='cp1252');text='T\u00ednh c\u1ee5c b\u1ed9';configure_utf8_console(stream,object());stream.write(text);stream.flush();self.assertEqual(raw.getvalue(),text.encode('utf-8'))
 def rec(self,d):p=Path(d)/'x.pdf';p.write_bytes(b'x');return {'document_id':'d','sha256':hashlib.sha256(b'x').hexdigest(),'relative_path':'x.pdf','extraction_status':'needs_ocr'}
 def test_select_hash_checkpoint_resume_atomic(self):
  with tempfile.TemporaryDirectory() as d:
   r=self.rec(d);Path(d,'official_document_acquisition_manifest.json').write_text(json.dumps({'records':[r]}));self.assertEqual(select_documents(Path(d),('d',))[0]['document_id'],'d');c=add_batch({},r,[(1,b'abc',b'\x9d')]);p=Path(d)/'s.json';atomic_write(p,c);self.assertEqual(load_checkpoint(p),c);self.assertEqual(add_batch(c,r,[(1,b'abc',b'')])['pages'],c['pages']);r['sha256']='0'*64;Path(d,'official_document_acquisition_manifest.json').write_text(json.dumps({'records':[r]}));self.assertRaisesRegex(ValueError,'source_hash_mismatch',select_documents,Path(d),('d',))
 def test_rotated_revision_augments_without_replacing_source(self):
  r={'document_id':'d','sha256':'h'};source=add_batch({},r,[(51,b'upside-down',b'')]);before=dict(source['pages'][0]);revised=add_rotated_revision(source,r,51,90,'tesseract 5.5.0',b'right-side-up',b'')
  self.assertEqual(revised['pages'][0],before);self.assertEqual(len(revised['revisions']),1);self.assertEqual(revised['revisions'][0]['linkage'],'augments');self.assertEqual(revised['revisions'][0]['source_page_citation_id'],before['citation_id']);self.assertEqual(replay_revisions(revised['revisions']),revised['revisions']);self.assertEqual(add_batch(revised,r,[(52,b'next',b'')])['revisions'],revised['revisions'])
  self.assertRaisesRegex(ValueError,'ocr_rotation_invalid',add_rotated_revision,source,r,51,180,'tesseract 5.5.0',b'x',b'')
 def test_states_provenance_order(self):
  r={'document_id':'d','sha256':'h'};c=add_batch({},r,[(2,b'x',b''),(1,b'\x9d',b'')]);self.assertEqual([x['page'] for x in c['pages']],[1,2]);self.assertEqual(c['pages'][0]['status'],'invalid_utf8_ocr_text')
if __name__=='__main__':unittest.main()
