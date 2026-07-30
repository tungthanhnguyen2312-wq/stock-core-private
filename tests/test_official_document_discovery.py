import unittest

from official_document_discovery import discover, replay


class DiscoveryTests(unittest.TestCase):
 def page(self, **more):
  return {"ticker":"PAN","source_authority":"issuer_ir","authority_host":"thepangroup.vn","canonical_url":"https://thepangroup.vn/investor/page.htm","links":[{"canonical_url":"https://thepangroup.vn/files/ar.pdf","document_class":"annual_report","reporting_period":"2024","publication_date":"2025-03-01","observed_at":"2025-04-01T00:00:00Z","link_text":"Annual report 2024"}]}|more
 def known(self): return [{"document_id":"old","canonical_url":"https://thepangroup.vn/files/old.pdf"}]
 def test_identity_and_url_deduplication(self):
  page=self.page(links=self.page()["links"]+[{"canonical_url":"https://thepangroup.vn/files/ar.pdf","document_class":"annual_report","reporting_period":"2024","publication_date":"2025-03-01"}])
  out=discover([page],self.known()); self.assertEqual(out["ledger"][0]["state"],"new"); self.assertEqual(out["ledger"][1]["state"],"unchanged")
 def test_changed_version_is_new_url_request(self):
  out=discover([self.page(links=[{"canonical_url":"https://thepangroup.vn/files/new.pdf","document_class":"amendment_or_supersession_notice","reporting_period":"2025","publication_date":"2025-06-01"}])],self.known())
  self.assertEqual(out["accepted_requests"][0]["canonical_url"],"https://thepangroup.vn/files/new.pdf")
 def test_authority_rejection(self):
  out=discover([self.page(links=[{"canonical_url":"https://mirror.example/new.pdf","document_class":"annual_report","reporting_period":"2024","publication_date":"2025-01-01"}])],[])
  self.assertEqual(out["ledger"][0]["reason"],"authority_rejected")
 def test_pagination_bound(self):
  with self.assertRaisesRegex(ValueError,"pagination_bound_exceeded"): discover([self.page()]*26,[])
 def test_deterministic_replay(self):
  out=discover([self.page()],self.known()); self.assertTrue(replay([self.page()],self.known(),out))


if __name__ == "__main__": unittest.main()
