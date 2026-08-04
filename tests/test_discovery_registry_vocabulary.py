"""Discovery and acquisition share one vocabulary and one source identity.

`3b4cc5f` moved the acquirer's requestable document types onto the registry and made
`source_id` mandatory. `official_document_discovery` was one import away and moved neither:

  * it kept gating on `official_document_acquisition.DOCUMENT_CLASSES`, which omits
    `ex_right_notice`, `listing_change_notice` and `last_registration_date_notice` -- so it
    rejected as `ambiguous_document_identity` exactly the three notices that carry an
    ex-date, a listing change and a last registration date;
  * it never carried a `source_id`, so `retain()` handed `acquire()` specs that were refused
    as `missing_source_id` -- every candidate, with no request made and no document retained.

The second is a regression the same commit introduced: before it, `acquire()` did not require
a source, so `retain()` worked and stopped working silently.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import official_document_acquisition as acquisition  # noqa: E402
import official_document_discovery as discovery  # noqa: E402
import official_source_registry as registry  # noqa: E402


class RecordingFetcher:
    def __init__(self):
        self.urls: list[str] = []

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        return 200, {"Content-Type": "text/html"}, b"<html>notice</html>", url


def page(links, **more) -> dict:
    base = {"ticker": "VNM", "source_id": "hose", "authority_host": "hsx.vn",
            "canonical_url": "https://www.hsx.vn/vnm-notices",
            "source_authority": "Ho Chi Minh City Stock Exchange", "links": links}
    base.update(more)
    return base


def link(document_class, url, **more) -> dict:
    base = {"canonical_url": url, "document_class": document_class,
            "reporting_period": "2026", "publication_date": "2026-06-20",
            "link_text": f"VNM {document_class}"}
    base.update(more)
    return base


class VocabularyTests(unittest.TestCase):
    def test_the_three_execution_notices_are_admissible_candidates(self) -> None:
        rows = discovery.discover([page([
            link("listing_change_notice", "https://www.hsx.vn/a.pdf"),
            link("ex_right_notice", "https://www.hsx.vn/b.pdf"),
            link("last_registration_date_notice", "https://www.hsx.vn/c.pdf"),
        ])], [])["ledger"]
        self.assertEqual([row["state"] for row in rows], ["new", "new", "new"],
                         "the notices carrying an ex-date must not be ambiguous identities")

    def test_the_vocabulary_is_the_registry_not_the_module_tuple(self) -> None:
        declared = acquisition.declared_document_types(registry.load_registry())
        for missing_from_tuple in ("ex_right_notice", "listing_change_notice",
                                   "last_registration_date_notice"):
            self.assertIn(missing_from_tuple, declared)
            self.assertNotIn(missing_from_tuple, acquisition.DOCUMENT_CLASSES)

    def test_a_type_no_source_declares_is_still_an_ambiguous_identity(self) -> None:
        rows = discovery.discover([page([
            link("press_release", "https://www.hsx.vn/d.pdf")])], [])["ledger"]
        self.assertEqual(rows[0]["reason"], "ambiguous_document_identity")

    def test_an_html_notice_is_a_candidate_because_acquisition_retains_html(self) -> None:
        rows = discovery.discover([page([
            link("listing_change_notice", "https://www.hsx.vn/notice.html")])], [])["ledger"]
        self.assertEqual(rows[0]["state"], "new")

    def test_a_non_document_link_is_still_rejected(self) -> None:
        rows = discovery.discover([page([
            link("corporate_action_notice", "https://www.hsx.vn/style.css")])], [])["ledger"]
        self.assertEqual(rows[0]["reason"], "unsupported_mime_hint")


class SourceIdentityTests(unittest.TestCase):
    def test_retain_reaches_the_network_instead_of_missing_source_id(self) -> None:
        found = discovery.discover([page([
            link("corporate_action_notice", "https://www.hsx.vn/notice.pdf")])], [])
        fetcher = RecordingFetcher()
        with tempfile.TemporaryDirectory() as tmp:
            result = discovery.retain(found, Path(tmp), fetcher=fetcher,
                                      registry=registry.load_registry(),
                                      sleep=lambda _s: None)
        states = [outcome["state"] for outcome in result["outcomes"]]
        self.assertNotIn("missing_source_id", states)
        self.assertEqual(states, ["retained"])
        self.assertEqual(fetcher.urls, ["https://www.hsx.vn/notice.pdf"])

    def test_the_accepted_requests_carry_the_source_that_governs_them(self) -> None:
        found = discovery.discover([page([
            link("corporate_action_notice", "https://www.hsx.vn/notice.pdf")])], [])
        self.assertEqual(found["accepted_requests"][0]["source_id"], "hose")

    def test_a_listing_page_without_a_source_is_rejected_whole(self) -> None:
        rows = discovery.discover([page([
            link("corporate_action_notice", "https://www.hsx.vn/notice.pdf")],
            source_id="")], [])["ledger"]
        self.assertEqual(rows[0]["reason"], "listing_identity_or_authority_invalid")

    def test_a_candidate_never_outruns_the_registry_gate(self) -> None:
        """Discovery may accept a row the registry still refuses; acquisition must refuse it."""
        found = discovery.discover([page([
            link("annual_report", "https://www.hsx.vn/ar.pdf")])], [])
        self.assertEqual(found["ledger"][0]["state"], "new", "declared by issuer_ir, so valid here")
        fetcher = RecordingFetcher()
        with tempfile.TemporaryDirectory() as tmp:
            result = discovery.retain(found, Path(tmp), fetcher=fetcher,
                                      registry=registry.load_registry(),
                                      sleep=lambda _s: None)
        self.assertEqual(fetcher.urls, [], "hose does not publish annual reports")
        self.assertEqual(result["outcomes"][0]["reason"], registry.REASON_DOCUMENT_TYPE)


if __name__ == "__main__":
    unittest.main()
