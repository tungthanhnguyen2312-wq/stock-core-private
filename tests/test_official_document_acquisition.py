import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from stocklookup_core.evidence.official_document_acquisition import BOUNDED_ADDITIONAL_TICKER_SCOPE_EXCEEDED, EVENTS, MANIFEST, TICKERS, _response_failure, acquire, canonical_url, import_offline_event

PDF=b"%PDF-1.4\nfixture\n"
HTML=b"<html><body>official notice</body></html>"

#: These tests are about retention mechanics -- caching, redirects, hash conflicts, size and
#: timeout handling -- against fixture hosts that are deliberately not real. `acquire()` now
#: refuses anything the source registry does not admit, so they run against a registry that
#: declares those fixture hosts. Governance itself is covered by
#: tests/test_acquisition_registry_gate.py, against the shipped registry.
FIXTURE_REGISTRY={"schema_version":"1.0.0","approval_state":{"state":"APPROVED","approved_at":"2026-08-03T07:00:00Z","approved_at_provenance":"test fixture, UTC"},
 "global_policy":{"connect_timeout_seconds":5,"read_timeout_seconds":15,"max_attempts":2,"max_response_bytes":20971520,"user_agent":"test"},
 "sources":[{"source_id":"issuer_ir","activation":"approved","allowed_hosts":["issuer.example","cdn.example"],
   "document_types":["corporate_action_notice","reviewed_interim_financial_statements","corporate_governance_report","annual_report","amendment_or_supersession_notice"],
   "min_request_interval_seconds":0,"parser_version":"1.0.0"},
  {"source_id":"hnx","activation":"approved","allowed_hosts":["hnx.example"],
   "document_types":[],"index_document_types":["disclosure_rss_feed"],
   "min_request_interval_seconds":0,"parser_version":"1.0.0"}]}

class AcquisitionTests(unittest.TestCase):
 def test_index_refresh_versions_changed_bytes_and_same_bytes_are_a_noop(self):
  import copy
  registry=copy.deepcopy(FIXTURE_REGISTRY)
  registry['sources'][0]['index_document_types']=['issuer_ir_index_page']
  spec=self.spec(document_class='issuer_ir_index_page')
  fetch=lambda *_a,**_k:(200,{'Content-Type':'text/html'},HTML)
  acquire([spec],self.root,fetcher=fetch,registry=registry)
  first=(self.root/MANIFEST).read_bytes()
  same=acquire([spec|{'observed_at':'2026-10-07T00:00:00Z'}],self.root,fetcher=fetch,registry=registry,refresh_index_pages=True)
  self.assertTrue(same['outcomes'][0]['refreshed_same_bytes'])
  self.assertEqual((self.root/MANIFEST).read_bytes(),first)
  newer=HTML+b'changed index'
  acquire([spec|{'observed_at':'2026-10-07T00:00:00Z'}],self.root,
          fetcher=lambda *_a,**_k:(200,{'Content-Type':'text/html'},newer),registry=registry,refresh_index_pages=True)
  records=json.loads((self.root/MANIFEST).read_text())['records']
  self.assertEqual(len(records),2)
  self.assertEqual(records[0],json.loads(first)['records'][0])
  self.assertEqual((self.root/records[0]['relative_path']).read_bytes(),HTML)
  self.assertEqual((self.root/records[1]['relative_path']).read_bytes(),newer)

 def test_index_refresh_flag_never_refetches_a_cached_pdf(self):
  acquire([self.spec()],self.root,fetcher=self.fetch)
  before=(self.root/MANIFEST).read_bytes()
  result=acquire([self.spec()],self.root,fetcher=lambda *_a,**_k:self.fail('cached PDF fetched'),refresh_index_pages=True)
  self.assertEqual(result['outcomes'][0]['state'],'cached_valid')
  self.assertEqual((self.root/MANIFEST).read_bytes(),before)
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
  patcher=patch('stocklookup_core.evidence.official_document_acquisition.load_registry',return_value=FIXTURE_REGISTRY)
  patcher.start(); self.addCleanup(patcher.stop)
 def tearDown(self): self.tmp.cleanup()
 def spec(self, **more): return {"ticker":"HPG","source_id":"issuer_ir","canonical_url":"https://issuer.example/f.pdf","document_class":"corporate_action_notice","reporting_period":"2024","source_authority":"issuer_ir","observed_at":"2026-08-02T00:00:00Z"}|more
 def fetch(self, *_args, **_kwargs): return 200,{"Content-Type":"application/pdf"},PDF,"https://cdn.example/f.pdf"
 def metadata(self, **more): return {"ticker":"HPG","exchange":"HOSE","action_type":"bonus_share","ex_date":"2024-01-04","ratio":.2,"ratio_basis":"new_shares_per_existing_share","source_authority":"issuer_ir","source_url":"https://issuer.example/f.pdf","document_identity":"fixture-notice-1","retrieved_at":"2026-08-02T00:00:00Z","reporting_period":"2024"}|more
 def test_success_redirect_and_cache(self):
  with patch('stocklookup_core.evidence.official_document_acquisition._extraction_state',return_value="needs_ocr"):
   first=acquire([self.spec()],self.root,fetcher=self.fetch); second=acquire([self.spec()],self.root,fetcher=lambda *_a,**_k:self.fail("network"))
  self.assertEqual(first["outcomes"][0]["state"],"retained"); self.assertEqual(second["outcomes"][0]["state"],"cached_valid")
 def test_explicitly_qualified_issuer_publication_projects_to_a1(self):
  acquire([self.spec(qualification_state="QUALIFIED",published_at="2026-08-01")],self.root,fetcher=self.fetch)
  record=json.loads((self.root/MANIFEST).read_text())["records"][0]
  self.assertEqual(record["temporal_retention"]["publication_authority_tier"],"OFFICIAL_ISSUER_IR_OR_EXCHANGE")
  self.assertEqual(record["a1_temporal_projection"]["knowledge_resolution"]["historical_reconstruction_scope"],"FROM_QUALIFIED_SOURCE_PUBLICATION")
  self.assertEqual(json.loads((self.root/MANIFEST).read_text())["records"][0]["final_url"],"https://cdn.example/f.pdf")
 def test_retains_governed_source_and_discovery_provenance(self):
  provenance={"listing_url":"https://issuer.example/notices","link_text":"Official notice","page_index":1}
  acquire([self.spec(discovery_provenance=provenance)],self.root,fetcher=self.fetch)
  record=json.loads((self.root/MANIFEST).read_text())["records"][0]
  self.assertEqual(record["source_id"],"issuer_ir")
  self.assertEqual(record["discovery_provenance"],provenance)
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
  with patch('stocklookup_core.evidence.official_document_acquisition._extraction_state',return_value="needs_ocr"): acquire([self.spec()],self.root,fetcher=self.fetch)
  record=json.loads((self.root/MANIFEST).read_text())["records"][0]; (self.root/record["relative_path"]).write_bytes(PDF+b"bad")
  self.assertEqual(acquire([self.spec()],self.root,fetcher=self.fetch)["outcomes"][0]["state"],"hash_conflict")
 def test_offline_pdf_html_dry_run_and_idempotence(self):
  pdf=self.root/"notice.pdf"; pdf.write_bytes(PDF)
  dry=import_offline_event(pdf,self.root,self.metadata(),dry_run=True); self.assertEqual(dry["state"],"dry_run")
  first=import_offline_event(pdf,self.root,self.metadata()); second=import_offline_event(pdf,self.root,self.metadata())
  self.assertEqual(first["state"],"retained"); self.assertEqual(second["state"],"cached_valid")
  event=json.loads((self.root/EVENTS).read_text()); self.assertTrue(event["qualified_for_price_basis_test"]); self.assertFalse(event["qualified_for_share_transition"])
  record=json.loads((self.root/MANIFEST).read_text())["records"][0]
  self.assertEqual(record["temporal_retention"]["first_observed_at"],"2026-08-02T00:00:00Z")
  self.assertEqual(record["a1_temporal_projection"]["publication_time"]["publication_authority_tier"],"UNVERIFIED")
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
 def test_index_observed_dtp_is_a_finite_supported_ticker(self):
  self.assertIn("DTP",TICKERS)
 def test_explicit_bounded_additional_ticker_is_admitted_without_widening_default_scope(self):
  denied=acquire([self.spec(ticker="VBB")],self.root,fetcher=self.fetch)
  admitted=acquire([self.spec(ticker="VBB")],self.root,fetcher=self.fetch,additional_allowed_tickers=("VBB",))
  self.assertEqual(denied["outcomes"][0]["state"],"unsupported_request")
  self.assertEqual(admitted["outcomes"][0]["state"],"retained")
 def test_additional_ticker_scope_is_finite_and_rejects_invalid_extensions(self):
  for scope in ((), ("VBB","VBB"), ("VBB","KLB","MZG","AAA"), ("V-BB",), ("HPG",)):
   with self.subTest(scope=scope):
    with self.assertRaisesRegex(ValueError,BOUNDED_ADDITIONAL_TICKER_SCOPE_EXCEEDED):
     acquire([],self.root,additional_allowed_tickers=scope)
 def test_additional_ticker_request_must_be_in_explicit_scope_before_http(self):
  result=acquire([self.spec(ticker="KLB")],self.root,fetcher=lambda *_a,**_k:self.fail("scope rejection must precede HTTP"),additional_allowed_tickers=("VBB",))
  self.assertEqual(result["outcomes"][0]["state"],BOUNDED_ADDITIONAL_TICKER_SCOPE_EXCEEDED)
 def test_registry_still_independently_refuses_an_explicitly_scoped_ticker(self):
  denied={**FIXTURE_REGISTRY,"sources":[{**FIXTURE_REGISTRY["sources"][0],"activation":"pending"},FIXTURE_REGISTRY["sources"][1]]}
  result=acquire([self.spec(ticker="VBB")],self.root,fetcher=self.fetch,registry=denied,additional_allowed_tickers=("VBB",))
  self.assertEqual(result["outcomes"][0]["state"],"refused_by_source_registry")
 def test_declared_rss_discovery_input_is_retained_as_xml_but_not_evidence(self):
  rss=b'<?xml version="1.0"?><rss><channel><title>HNX</title></channel></rss>'
  spec={"ticker":"DTP","source_id":"hnx","canonical_url":"https://hnx.example/feed.rss","document_class":"disclosure_rss_feed","reporting_period":"2026","source_authority":"exchange","observed_at":"2026-09-15T00:00:00Z"}
  result=acquire([spec],self.root,fetcher=lambda *_a,**_k:(200,{"Content-Type":"application/rss+xml"},rss))
  self.assertEqual(result["outcomes"][0]["state"],"retained")
  record=json.loads((self.root/MANIFEST).read_text())["records"][0]
  self.assertEqual(record["content_type"],"application/rss+xml")
  self.assertEqual(record["extraction_status"],"ready_for_discovery_parsing")
  self.assertTrue(record["relative_path"].endswith(".xml"))
 def test_reviewed_interim_statement_is_supported(self):
  result=acquire([self.spec(reporting_period="2026",document_class="reviewed_interim_financial_statements")],self.root,fetcher=self.fetch)
  self.assertEqual(result["outcomes"][0]["state"],"retained")
 def test_corporate_governance_report_is_supported(self):
  result=acquire([self.spec(reporting_period="2026",document_class="corporate_governance_report")],self.root,fetcher=self.fetch)
  self.assertEqual(result["outcomes"][0]["state"],"retained")
 def test_http_fetch_stream_retains_every_chunk_after_type_sniff(self):
  import stocklookup_core.evidence.official_document_acquisition as module
  class Response:
   status_code=200; headers={"Content-Type":"text/html"}
   is_redirect=False; is_permanent_redirect=False
   def iter_content(self,chunk_size=1):
    yield b"<html>first"
    yield b" middle"
    yield b" last</html>"
   def close(self): pass
  with tempfile.TemporaryDirectory() as folder, patch.object(module.requests,"get",return_value=Response()):
   target=Path(folder)/"document.part"
   status,headers,prefix,final=module.fetch_http("https://issuer.example/f.html",temporary_path=target,admit_hop=lambda _url:True)
   self.assertEqual(200,status); self.assertEqual("https://issuer.example/f.html",final)
   self.assertEqual(b"<html>first middle last</html>",target.read_bytes())

if __name__=='__main__': unittest.main()
