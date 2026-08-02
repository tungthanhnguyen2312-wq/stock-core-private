import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from official_document_acquisition import EVENTS, MANIFEST, _response_failure, acquire, canonical_url, import_offline_event

PDF=b"%PDF-1.4\nfixture\n"
HTML=b"<html><body>official notice</body></html>"

class AcquisitionTests(unittest.TestCase):
 def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
 def tearDown(self): self.tmp.cleanup()
 def spec(self, **more): return {"ticker":"HPG","canonical_url":"https://issuer.example/f.pdf","document_class":"corporate_action_notice","reporting_period":"2024","source_authority":"issuer_ir","observed_at":"2026-08-02T00:00:00Z"}|more
 def fetch(self, *_args, **_kwargs): return 200,{"Content-Type":"application/pdf"},PDF,"https://cdn.example/f.pdf"
 def metadata(self, **more): return {"ticker":"HPG","exchange":"HOSE","action_type":"bonus_share","ex_date":"2024-01-04","ratio":.2,"ratio_basis":"new_shares_per_existing_share","source_authority":"issuer_ir","source_url":"https://issuer.example/f.pdf","document_identity":"fixture-notice-1","retrieved_at":"2026-08-02T00:00:00Z","reporting_period":"2024"}|more
 def test_success_redirect_and_cache(self):
  with patch("official_document_acquisition._extraction_state",return_value="needs_ocr"):
   first=acquire([self.spec()],self.root,fetcher=self.fetch); second=acquire([self.spec()],self.root,fetcher=lambda *_a,**_k:self.fail("network"))
  self.assertEqual(first["outcomes"][0]["state"],"retained"); self.assertEqual(second["outcomes"][0]["state"],"cached_valid")
  self.assertEqual(json.loads((self.root/MANIFEST).read_text())["records"][0]["final_url"],"https://cdn.example/f.pdf")
 def test_timeout_then_success_and_two_timeouts(self):
  calls=[]
  def retry(*_a,**_k):
   calls.append(1)
   if len(calls)==1: raise TimeoutError()
   return 200,{"Content-Type":"application/pdf"},PDF
  self.assertEqual(acquire([self.spec()],self.root,fetcher=retry,sleep=lambda _:None)["outcomes"][0]["state"],"retained")
  with tempfile.TemporaryDirectory() as other:
   self.assertEqual(acquire([self.spec()],Path(other),fetcher=lambda *_a,**_k:(_ for _ in ()).throw(TimeoutError()),sleep=lambda _:None)["outcomes"][0]["state"],"timeout")
 def test_invalid_oversized_truncated_and_partial_cleanup(self):
  html=lambda *_a,**_k:(200,{"Content-Type":"text/plain"},b"no")
  large=lambda *_a,**_k:(200,{"Content-Type":"application/pdf"},PDF+b"x"*2000)
  self.assertEqual(acquire([self.spec()],self.root,fetcher=html)["outcomes"][0]["state"],"invalid_content_type")
  self.assertEqual(acquire([self.spec()],self.root,fetcher=large,max_response_bytes=1024)["outcomes"][0]["state"],"response_size_limit")
  self.assertEqual(_response_failure(200,{"Content-Type":"application/pdf"},b"%PDF",0),"empty_or_truncated_document")
  self.assertFalse(list(self.root.rglob("*.part")))
 def test_hash_conflict(self):
  with patch("official_document_acquisition._extraction_state",return_value="needs_ocr"): acquire([self.spec()],self.root,fetcher=self.fetch)
  record=json.loads((self.root/MANIFEST).read_text())["records"][0]; (self.root/record["relative_path"]).write_bytes(PDF+b"bad")
  self.assertEqual(acquire([self.spec()],self.root,fetcher=self.fetch)["outcomes"][0]["state"],"hash_conflict")
 def test_offline_pdf_html_dry_run_and_idempotence(self):
  pdf=self.root/"notice.pdf"; pdf.write_bytes(PDF)
  dry=import_offline_event(pdf,self.root,self.metadata(),dry_run=True); self.assertEqual(dry["state"],"dry_run")
  first=import_offline_event(pdf,self.root,self.metadata()); second=import_offline_event(pdf,self.root,self.metadata())
  self.assertEqual(first["state"],"retained"); self.assertEqual(second["state"],"cached_valid")
  event=json.loads((self.root/EVENTS).read_text()); self.assertTrue(event["qualified_for_price_basis_test"]); self.assertFalse(event["qualified_for_share_transition"])
  html=self.root/"notice.html"; html.write_bytes(HTML)
  self.assertEqual(import_offline_event(html,self.root,self.metadata(source_url="https://issuer.example/h.html"))["state"],"retained")
 def test_offline_rejects_missing_empty_and_conflicting_metadata(self):
  with self.assertRaisesRegex(ValueError,"local_document_missing"): import_offline_event(self.root/"none.pdf",self.root,self.metadata())
  empty=self.root/"empty.pdf"; empty.write_bytes(b"")
  with self.assertRaisesRegex(ValueError,"unsupported_or_empty_local_document"): import_offline_event(empty,self.root,self.metadata())
  pdf=self.root/"notice.pdf"; pdf.write_bytes(PDF)
  with self.assertRaisesRegex(ValueError,"required_event_metadata_missing"): import_offline_event(pdf,self.root,self.metadata(ex_date=None))
  import_offline_event(pdf,self.root,self.metadata())
  with self.assertRaisesRegex(ValueError,"offline_event_metadata_conflict"): import_offline_event(pdf,self.root,self.metadata(retrieved_at="2026-08-03T00:00:00Z"))
 def test_url_is_deterministic(self): self.assertEqual(canonical_url("HTTPS://ISSUER.EXAMPLE/a?b=2&a=1#x"),"https://issuer.example/a?a=1&b=2")
 def test_current_year_corporate_action_is_supported_but_future_year_is_rejected(self):
  current=acquire([self.spec(reporting_period="2026")],self.root,fetcher=self.fetch)
  future=acquire([self.spec(reporting_period="2027")],self.root,fetcher=self.fetch)
  self.assertEqual(current["outcomes"][0]["state"],"retained")
  self.assertEqual(future["outcomes"][0]["state"],"unsupported_request")

if __name__=='__main__': unittest.main()
