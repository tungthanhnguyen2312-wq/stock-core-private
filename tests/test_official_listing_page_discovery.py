"""An announcement index page is admissible to fetch and never admissible as evidence.

The listing-page route removes the "an owner hand-supplies every notice URL" dependency. It
adds exactly one new power -- reading links out of one stored page -- so every test here is
about a boundary that power must not cross. Tests assert the *absence* of a call or a write
wherever the property is "this never happens", because an assertion on a returned message
cannot tell a refusal apart from a request that was made and then regretted.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import official_document_acquisition as acquisition  # noqa: E402
import official_document_discovery as discovery  # noqa: E402
import official_document_store as store  # noqa: E402
import official_listing_page_parser as parser  # noqa: E402
import official_source_registry as registry  # noqa: E402

INDEX_TYPE = "announcement_index_page"
LISTING_URL = "https://vsd.vn/en/alc/6"

PAGE = b"""<html><body>
<div class="bread-crumb"><ul><li><a href="/en/tin-tuc">News</a></li>
<li><a href="/en/alo/ISSUER">Securities registration institution</a></li></ul></div>
<ul class="list-news">
  <li><h3><a href="/en/ad/197038">VNM: Residual Payment of 2025 cash dividend</a></h3>
      <div class="time-news">Date update 17/06/2026 - 17:20:44</div></li>
  <li><h3><a href="/en/ad/191001">VNM: Listing change and additional listing of shares</a></h3>
      <div class="time-news">Date update 02/02/2026 - 09:10:00</div></li>
  <li><h3><a href="/EN/AD/191001?b=2&amp;a=1#frag">VNM: Listing change and additional listing of shares</a></h3>
      <div class="time-news">Date update 02/02/2026 - 09:10:00</div></li>
  <li><h3><a href="/en/ad/198728">SSI: Payment of 2025 cash dividend</a></h3>
      <div class="time-news">Date update 01/08/2026 - 10:00:00</div></li>
  <li><h3><a href="/en/ad/198718">NAB12504: 1st Payment of Bond Interest</a></h3>
      <div class="time-news">Date update 01/08/2026 - 10:00:00</div></li>
  <li><h3><a href="https://evil.example.com/en/ad/1">VNM: fake offsite notice</a></h3>
      <div class="time-news">Date update 01/08/2026 - 10:00:00</div></li>
  <li><h3><a href="javascript:alert(1)">VNM: unsafe scheme</a></h3></li>
  <li><h3><a href="https://user:pw@vsd.vn/en/ad/2">VNM: credentialled</a></h3></li>
  <li><h3><a href="/en/ad/3?token=abc">VNM: session url</a></h3></li>
  <li><h3><a href="/en/ad/4">no code prefix here</a></h3></li>
</ul></body></html>"""


def parse(page: bytes = PAGE, *, ticker: str = "VNM", url: str = LISTING_URL) -> dict:
    return parser.parse_index_page(page, listing_url=url, source_id="vsdc", ticker=ticker,
                                   registry=registry.load_registry())


class RecordingFetcher:
    def __init__(self, body: bytes = PAGE, final_url: str | None = None):
        self.urls: list[str] = []
        self.body, self.final_url = body, final_url

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        return 200, {"Content-Type": "text/html"}, self.body, self.final_url or url


def acquire(specs, *, fetcher, reg=None, sleeps=None, clock=None):
    with tempfile.TemporaryDirectory() as tmp:
        result = acquisition.acquire(
            specs, Path(tmp), fetcher=fetcher,
            registry=reg if reg is not None else registry.load_registry(),
            sleep=(sleeps.append if sleeps is not None else (lambda _s: None)),
            **({"clock": clock} if clock else {}))
    return result


def spec(**overrides) -> dict:
    base = {"ticker": "VNM", "source_id": "vsdc", "document_class": INDEX_TYPE,
            "reporting_period": "2026", "canonical_url": LISTING_URL}
    base.update(overrides)
    return base


class RegistryContractTests(unittest.TestCase):
    """1. Unsupported listing-page source/type pairs emit no network call."""

    def test_the_index_type_is_declared_for_vsdc_only(self) -> None:
        reg = registry.load_registry()
        declaring = {source_id for source_id, source in registry.source_index(reg).items()
                     if INDEX_TYPE in registry.index_document_types(source)}
        self.assertEqual(declaring, {"vsdc"},
                         "a listing type must not broaden every host by default")

    def test_an_index_page_is_admitted_for_the_source_that_exposes_one(self) -> None:
        self.assertEqual(registry.admit("vsdc", LISTING_URL, INDEX_TYPE)["decision"],
                         registry.ADMITTED)

    def test_the_same_type_is_refused_for_a_source_that_does_not_expose_one(self) -> None:
        for source_id, url in (("hose", "https://www.hsx.vn/x"), ("hnx", "https://www.hnx.vn/x"),
                               ("issuer_ir", "https://www.vinamilk.com.vn/x")):
            decision = registry.admit(source_id, url, INDEX_TYPE)
            self.assertEqual(decision["reason"], registry.REASON_DOCUMENT_TYPE, source_id)

    def test_an_unsupported_pair_makes_no_request_at_all(self) -> None:
        fetcher = RecordingFetcher()
        result = acquire([spec(source_id="hose", canonical_url="https://www.hsx.vn/x")],
                         fetcher=fetcher)
        self.assertEqual(fetcher.urls, [])
        self.assertEqual(result["outcomes"][0]["reason"], registry.REASON_DOCUMENT_TYPE)

    def test_evidence_and_index_vocabularies_stay_disjoint(self) -> None:
        reg = registry.load_registry()
        for source in registry.source_index(reg).values():
            self.assertFalse(registry.evidence_document_types(source)
                             & registry.index_document_types(source))

    def test_existing_notice_classes_are_unchanged(self) -> None:
        """12. Existing notice document classes remain accepted and unchanged."""
        for document_class in ("last_registration_date_notice", "corporate_action_notice",
                               "amendment_or_supersession_notice"):
            self.assertEqual(
                registry.admit("vsdc", "https://vsd.vn/en/ad/177392", document_class)["decision"],
                registry.ADMITTED, document_class)
        self.assertEqual(
            registry.admit("hose", "https://www.hsx.vn/n.html", "ex_right_notice")["decision"],
            registry.ADMITTED)


class NonPromotableTests(unittest.TestCase):
    """11. A listing-page artifact cannot be promoted as official corporate-action evidence."""

    def test_the_store_refuses_to_adopt_an_index_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            page = runtime / "index.html"
            page.write_bytes(PAGE)
            with self.assertRaises(store.UnsupportedDocument) as caught:
                store.adopt_retained_document(
                    runtime, page, ticker="VNM", document_type=INDEX_TYPE,
                    source_url=LISTING_URL, source_authority="VSDC",
                    observed_at="2026-08-04T00:00:00Z", execute=True)
            self.assertIn("discovery input", str(caught.exception))
            self.assertFalse((runtime / "data").exists(),
                             "a refused adoption must write nothing at all")

    def test_an_unreadable_registry_still_refuses_an_index_page(self) -> None:
        """The store's guard must fail closed, not break adoption, if the registry is gone."""
        original = store.is_discovery_input

        def unreadable(*args, **kwargs):
            raise registry.RegistryError("registry unreadable")

        store.is_discovery_input = unreadable
        try:
            with tempfile.TemporaryDirectory() as tmp:
                runtime = Path(tmp)
                page = runtime / "index.html"
                page.write_bytes(PAGE)
                with self.assertRaises(store.UnsupportedDocument):
                    store.adopt_retained_document(
                        runtime, page, ticker="VNM", document_type=INDEX_TYPE,
                        source_url=LISTING_URL, source_authority="VSDC",
                        observed_at="2026-08-04T00:00:00Z", execute=True)
                self.assertFalse((runtime / "data").exists())
        finally:
            store.is_discovery_input = original

    def test_the_index_type_is_absent_from_the_evidence_store_vocabulary(self) -> None:
        self.assertNotIn(INDEX_TYPE, store.DOCUMENT_TYPES)
        self.assertTrue(registry.is_discovery_input(INDEX_TYPE))

    def test_an_index_page_is_never_itself_a_discovery_candidate(self) -> None:
        page = {"ticker": "VNM", "source_id": "vsdc", "authority_host": "vsd.vn",
                "canonical_url": LISTING_URL, "source_authority": "VSDC",
                "links": [{"canonical_url": "https://vsd.vn/en/alc/7",
                           "document_class": INDEX_TYPE, "reporting_period": "2026",
                           "publication_date": "2026-06-17", "link_text": "VNM: another index"}]}
        rows = discovery.discover([page], [])["ledger"]
        self.assertEqual(rows[0]["reason"], "ambiguous_document_identity")


class ParserBoundaryTests(unittest.TestCase):
    """5. Parser execution performs no network call. 6/7/8: rejection, resolution, dedup."""

    def test_the_parser_makes_no_network_call(self) -> None:
        calls: list[str] = []

        def explode(*a, **k):
            calls.append("called")
            raise AssertionError("the parser must not reach the network")

        original = acquisition.requests.get
        acquisition.requests.get = explode
        try:
            parse()
        finally:
            acquisition.requests.get = original
        self.assertEqual(calls, [])

    def test_relative_links_resolve_against_the_admitted_listing_url(self) -> None:
        urls = {link["canonical_url"] for link in parse()["links"]}
        self.assertIn("https://vsd.vn/en/ad/197038", urls)

    def test_offsite_unsafe_and_credentialled_links_are_rejected(self) -> None:
        parsed = parse()
        reasons = {row["reason"] for row in parsed["rejected_links"]}
        urls = {link["canonical_url"] for link in parsed["links"]}
        self.assertIn("host_outside_approved_source", reasons)
        self.assertFalse(any("evil.example.com" in url for url in urls))
        self.assertFalse(any("@" in url for url in urls))
        self.assertFalse(any(url.startswith("javascript") for url in urls))
        self.assertFalse(any("token" in url for url in urls))

    def test_a_fragment_is_dropped_and_a_query_is_sorted(self) -> None:
        normalized = parser.normalize_candidate_url("/en/ad/9?b=2&a=1#section", LISTING_URL)
        self.assertEqual(normalized, "https://vsd.vn/en/ad/9?a=1&b=2")

    def test_duplicates_collapse_deterministically(self) -> None:
        """8. The same notice linked twice, differing only in case/query order/fragment."""
        parsed = parse()
        urls = [link["canonical_url"] for link in parsed["links"]]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(parse()["links"], parsed["links"], "same bytes, same candidates")

    def test_the_issuer_is_matched_by_code_not_substring(self) -> None:
        parsed = parse()
        codes = {link["page_facts"]["issuer_code"] for link in parsed["links"]}
        self.assertEqual(codes, {"VNM"})
        rejected = {row.get("issuer_code") for row in parsed["rejected_links"]}
        self.assertIn("SSI", rejected)
        self.assertIn("NAB12504", rejected, "a bond code must not match its issuer by prefix")

    def test_page_facts_and_inference_are_separate(self) -> None:
        link = next(row for row in parse()["links"] if "191001" in row["canonical_url"])
        self.assertEqual(link["page_facts"]["visible_date"], "2026-02-02")
        # vsdc does not declare listing_change_notice, so the class falls back to one it does
        # declare while the cue that matched is still reported.
        self.assertEqual(link["inference"]["document_class"], "corporate_action_notice")
        self.assertEqual(link["inference"]["cue"], "listing change")
        self.assertIn("index-page subject line only", link["inference"]["basis"])

    def test_inference_stays_inside_what_the_source_declares(self) -> None:
        """A VSDC candidate must never be minted with a class VSDC cannot be asked for."""
        reg = registry.load_registry()
        declared = registry.evidence_document_types(registry.source_index(reg)["vsdc"])
        self.assertNotIn("listing_change_notice", declared, "vsdc declares no listing change")
        page = (b'<html><ul class="list-news"><li><h3><a href="/en/ad/6">'
                b'VNM: Adjustment of the number of registered shares</a></h3>'
                b'<div class="time-news">Date update 01/07/2026 - 10:00:00</div></li></ul></html>')
        link = parse(page)["links"][0]
        self.assertIn(link["inference"]["document_class"], declared)
        self.assertEqual(
            registry.admit("vsdc", link["canonical_url"],
                           link["inference"]["document_class"], registry=reg)["decision"],
            registry.ADMITTED, "the inferred class must be one the gate admits")

    def test_a_registered_share_notice_is_flagged_as_share_relevant(self) -> None:
        page = (b'<html><ul class="list-news"><li><h3><a href="/en/ad/7">'
                b'VNM: Adjustment of the number of registered shares</a></h3>'
                b'<div class="time-news">Date update 01/07/2026 - 10:00:00</div></li></ul></html>')
        row = parser.review_queue(parse(page))[0]
        self.assertIn("registered shares", row["share_relevance_cues"])
        self.assertEqual(row["confidence"], "high")

    def test_a_missing_date_is_absent_rather_than_invented(self) -> None:
        page = b'<html><ul class="list-news"><li><h3><a href="/en/ad/5">VNM: no date</a></h3>' \
               b'</li></ul></html>'
        link = parse(page)["links"][0]
        self.assertIsNone(link["page_facts"]["visible_date"])
        self.assertIsNone(link["publication_date"])


class SeamTests(unittest.TestCase):
    """9. Discovery output includes source_id and can cross the retention seam."""

    def test_parsed_candidates_cross_into_discovery_with_a_source(self) -> None:
        found = discovery.discover(parser.listing_pages(parse()), [])
        accepted = found["accepted_requests"]
        self.assertTrue(accepted)
        self.assertTrue(all(row["source_id"] == "vsdc" for row in accepted))

    def test_parsing_and_discovering_acquire_nothing(self) -> None:
        """10. Retaining or parsing a candidate does not acquire it."""
        calls: list[str] = []
        original = acquisition.requests.get
        acquisition.requests.get = lambda *a, **k: calls.append("called")
        try:
            found = discovery.discover(parser.listing_pages(parse()), [])
        finally:
            acquisition.requests.get = original
        self.assertEqual(calls, [], "discovery must not fetch a candidate")
        self.assertTrue(found["accepted_requests"], "candidates exist but were not acquired")

    def test_candidate_ids_are_stable_across_runs(self) -> None:
        self.assertEqual([row["candidate_id"] for row in parser.review_queue(parse())],
                         [row["candidate_id"] for row in parser.review_queue(parse())])


class GovernedTransportTests(unittest.TestCase):
    """2/3/4: redirects re-admitted under the listing contract, retries keep the interval."""

    def test_a_redirect_hop_is_re_admitted_under_the_index_contract(self) -> None:
        fetcher = RecordingFetcher(final_url="https://www.vsdc.vn/en/alc/6")
        result = acquire([spec()], fetcher=fetcher)
        self.assertEqual(result["outcomes"][0]["state"], "retained",
                         "www.vsdc.vn is on the vsdc allowlist")

    def test_a_redirect_to_an_unapproved_host_retains_nothing(self) -> None:
        fetcher = RecordingFetcher(final_url="https://evil.example.com/alc/6")
        result = acquire([spec()], fetcher=fetcher)
        outcome = result["outcomes"][0]
        self.assertEqual(outcome["state"], "redirect_refused_by_source_registry")
        self.assertNotIn("document_id", outcome)

    def test_no_request_reaches_an_unapproved_redirect_target(self) -> None:
        requested: list[str] = []

        class _Response:
            def __init__(self, status, headers, body=b"", redirect=False):
                self.status_code, self.headers, self._body = status, headers, body
                self.is_redirect = self.is_permanent_redirect = redirect

            def iter_content(self, chunk_size=1):
                yield self._body

            def close(self):
                pass

        def fake_get(url, **kwargs):
            requested.append(url)
            if len(requested) == 1:
                return _Response(302, {"Location": "https://evil.example.com/x"}, redirect=True)
            return _Response(200, {"Content-Type": "text/html"}, PAGE)

        original = acquisition.requests.get
        acquisition.requests.get = fake_get
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(ValueError, "redirect_refused_by_source_registry"):
                    acquisition.fetch_http(
                        LISTING_URL, temporary_path=Path(tmp) / "part",
                        admit_hop=lambda target: registry.admit(
                            "vsdc", target, INDEX_TYPE)["decision"] == registry.ADMITTED)
        finally:
            acquisition.requests.get = original
        self.assertEqual(requested, [LISTING_URL])

    def test_a_retry_waits_out_the_vsdc_interval(self) -> None:
        # vsdc declares 15s, longer than hose's 10s, so the value is source-specific.
        class Flaky:
            def __init__(self):
                self.urls: list[str] = []

            def __call__(self, url, **kwargs):
                self.urls.append(url)
                if len(self.urls) == 1:
                    raise TimeoutError("simulated")
                return 200, {"Content-Type": "text/html"}, PAGE, url

        ticks = iter([0.0, 0.0, 15.0])
        sleeps: list[float] = []
        fetcher = Flaky()
        acquire([spec()], fetcher=fetcher, sleeps=sleeps, clock=lambda: next(ticks))
        self.assertEqual(len(fetcher.urls), 2)
        self.assertEqual(sleeps, [15.0])

    def test_an_unverifiable_approval_still_stops_an_index_request(self) -> None:
        reg = copy.deepcopy(registry.load_registry())
        reg["approval_state"].pop(registry.APPROVAL_PROVENANCE_FIELD, None)
        fetcher = RecordingFetcher()
        result = acquire([spec()], fetcher=fetcher, reg=reg)
        self.assertEqual(fetcher.urls, [])
        self.assertEqual(result["outcomes"][0]["reason"], registry.REASON_APPROVAL_TIMESTAMP)


class EntryUrlProvenanceTests(unittest.TestCase):
    """The entry URL is observed in a retained artifact, not assumed from a pattern."""

    ARTIFACT = (ROOT / "operations-review" / "vnm-2024-cash-dividend-official-evidence"
                / "vsdc-record-date-notice.html")

    def test_the_listing_url_is_present_in_the_retained_vnm_notice(self) -> None:
        self.assertTrue(self.ARTIFACT.is_file(), "provenance artifact must exist")
        document = self.ARTIFACT.read_text(encoding="utf-8", errors="replace")
        self.assertIn('href="/en/alc/6"', document,
                      "the entry URL must be an observed navigation link, never a guess")

    def test_the_retained_notice_is_the_vsdc_vnm_document_it_claims_to_be(self) -> None:
        manifest = json.loads(
            (ROOT / "operations-review" / "vnm-2024-cash-dividend-official-evidence"
             / "source-manifest.json").read_text(encoding="utf-8"))
        self.assertIn("vsd.vn", json.dumps(manifest))


if __name__ == "__main__":
    unittest.main()
