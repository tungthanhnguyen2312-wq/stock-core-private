import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from official_document_retrieval import build_index,search
class Page:
 def __init__(self,text):self.text=text
 def extract_text(self):return self.text
class Reader:
 def __init__(self,*_):self.pages=[Page('Revenue brokerage income for HPG FY2024'),Page('Other page')]
class RetrievalTests(unittest.TestCase):
 def fixture(self):
  tmp=tempfile.TemporaryDirectory(); root=Path(tmp.name); pdf=root/'x.pdf'; pdf.write_bytes(b'%PDF test'); h=hashlib.sha256(pdf.read_bytes()).hexdigest(); eid='e'; (root/'manifest.json').write_text(json.dumps({'records':[{'evidence_id':eid,'ticker':'HPG','reporting_period':'2024','qualification_state':'qualified','evidence_type':'audited_consolidated_financial_statements','filename':'x.pdf','sha256':h,'publication_date':'2025-01-01','retrieved_at':'2025-01-02'}]})); (root/'qualification_citations.jsonl').write_text(json.dumps({'citation_id':'c','evidence_id':eid,'raw_item_id':'revenue','citation':{'pdf_page':1,'line_label_vi':'Revenue'}})+'\n'); return tmp,root
 def test_determinism_citation_isolation_and_ranking(self):
  tmp,root=self.fixture(); self.addCleanup(tmp.cleanup)
  with patch('official_document_retrieval.PdfReader',Reader):a=build_index(root);b=build_index(root)
  self.assertEqual(a,b);r=search(a,ticker='HPG',period='2024',metric='revenue',keyword='brokerage');self.assertEqual(r['state'],'available');self.assertEqual(r['results'][0]['citations'][0]['citation_id'],'c');self.assertEqual(search(a,ticker='VNM',period='2024',keyword='revenue')['state'],'unavailable')
 def test_hash_and_unsupported_fail_closed(self):
  tmp,root=self.fixture();self.addCleanup(tmp.cleanup);p=root/'x.pdf';p.write_bytes(p.read_bytes()+b'x');self.assertRaisesRegex(ValueError,'source_hash_mismatch',build_index,root);self.assertEqual(search({'chunks':[]},ticker='BAD',period='2024',keyword='x')['reason'],'unsupported_query')
if __name__=='__main__':unittest.main()