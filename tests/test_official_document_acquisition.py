import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from official_document_acquisition import DOCUMENT_CLASSES, MANIFEST, acquire, canonical_url, coverage_matrix, retrieval_handoff

PDF=b"%PDF-1.4\nfixture\n"
class AcquisitionTests(unittest.TestCase):
 def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
 def tearDown(self): self.tmp.cleanup()
 def spec(self, **more): return {"ticker":"SSI","canonical_url":"https://ir.example.test/files/fy2024.pdf#fragment","document_class":"audited_annual_financial_statements","reporting_period":"2024","published_at":"2025-03-31","observed_at":"2025-04-01T00:00:00Z","source_authority":"issuer_ir"}|more
 def fetch(self, url, *, timeout_seconds): return 200,{"Content-Type":"application/pdf"},PDF
 def test_url_identity_idempotency_and_deterministic_manifest(self):
  self.assertEqual(canonical_url("HTTPS://IR.EXAMPLE.test/a?b=2&a=1#x"),"https://ir.example.test/a?a=1&b=2")
  with patch("official_document_acquisition._extraction_state",return_value="ready_for_direct_citations"):
   first=acquire([self.spec()],self.root,fetcher=self.fetch); before=(self.root/MANIFEST).read_text(); second=acquire([self.spec()],self.root,fetcher=self.fetch)
  self.assertEqual(first["outcomes"][0]["state"],"retained"); self.assertEqual(second["outcomes"][0]["state"],"skipped_idempotent")
  self.assertEqual(before,(self.root/MANIFEST).read_text()); handoff=retrieval_handoff(self.root); self.assertEqual(len(handoff),1); self.assertEqual(handoff[0]["canonical_observation_status"],"not_created")
 def test_changed_bytes_versions_and_supersession(self):
  with patch("official_document_acquisition._extraction_state",return_value="needs_ocr"): acquire([self.spec()],self.root,fetcher=self.fetch)
  old=retrieval_handoff(self.root)[0]["document_id"]
  changed=lambda *_,**__: (200,{"Content-Type":"application/pdf"},PDF+b"v2")
  with patch("official_document_acquisition._extraction_state",return_value="needs_ocr"):
   out=acquire([self.spec(document_class="amendment_or_supersession_notice",supersedes_document_id=old)],self.root,fetcher=changed)
  self.assertEqual(out["outcomes"][0]["state"],"retained"); records=json.loads((self.root/MANIFEST).read_text())["records"]
  self.assertEqual(records[-1]["supersedes_document_id"],old); self.assertEqual(len(records),2)
 def test_bounded_retry_and_needs_ocr(self):
  attempts=[]
  def eventually(url, *, timeout_seconds):
   attempts.append((url,timeout_seconds))
   if len(attempts)==1: raise TimeoutError()
   return 200,{"Content-Type":"application/pdf"},PDF
  with patch("official_document_acquisition._extraction_state",return_value="needs_ocr"):
   out=acquire([self.spec()],self.root,fetcher=eventually,max_attempts=2,timeout_seconds=20)
  self.assertEqual(out["outcomes"][0]["state"],"retained"); self.assertEqual(len(attempts),2); self.assertEqual(out["outcomes"][0]["extraction_status"],"needs_ocr")
 def test_isolation_failures_and_coverage(self):
  bad=lambda *_,**__: (404,{},b"")
  self.assertEqual(acquire([self.spec(ticker="BAD")],self.root,fetcher=self.fetch)["outcomes"][0]["state"],"unsupported_request")
  self.assertEqual(acquire([self.spec()],self.root,fetcher=bad)["outcomes"][0]["state"],"inaccessible")
  malformed=lambda *_,**__: (200,{"Content-Type":"text/html"},b"no")
  self.assertEqual(acquire([self.spec()],self.root,fetcher=malformed)["outcomes"][0]["state"],"malformed")
  matrix=coverage_matrix([]); self.assertEqual(len(matrix),5*len(DOCUMENT_CLASSES)); self.assertTrue(all(x["state"]=="missing" for x in matrix))
if __name__=='__main__': unittest.main()