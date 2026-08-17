# ==========================================================================
# Tests for pillar B -- official corporate-action ingestion foundation:
#   official_source_registry.py          -- host/type/rate admission, fail-closed
#   official_document_store.py           -- immutable, content-addressed retention
#   corporate_action_events.py           -- typed extraction, OCR damage refusal
#   official_corporate_action_ledger.py  -- linking, supersession, replay, factors
#   missing_payload_reconciliation.py    -- bounded, resumable classification
#
# Everything runs against synthetic bytes in a tmp runtime root; the bounded
# vertical slice over the real retained HPG evidence is at the bottom and skips
# when that evidence is absent.
# Run: `python -m unittest tests.test_official_corporate_action_pillar`
# ==========================================================================

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import corporate_action_events as events  # noqa: E402
import missing_payload_reconciliation as reconciliation  # noqa: E402
import official_corporate_action_ledger as ledger  # noqa: E402
import official_document_store as document_store  # noqa: E402
import official_source_registry as registry  # noqa: E402

_HTML = (b"<html><body><p>Thong bao</p></body></html>")
_PDF = b"%PDF-1.4\n% minimal\n"


def _unapproved_registry():
    """Registry with sources set to declared, for testing refusal logic."""
    loaded = registry.load_registry()
    loaded["approval_state"]["state"] = "AWAITING_OWNER_APPROVAL"
    for source in loaded["sources"]:
        source["activation"] = "declared"
    return loaded


def _approved_registry():
    """The shipped registry with all sources approved.

    Its `approved_at` carries no clock provenance, so `admit()` refuses on the governance
    verdict alone -- see `_verifiable_registry` for the copy used to exercise the admit path.
    """
    return registry.load_registry()


def _verifiable_registry():
    """The shipped registry with the approval instant made verifiable, in memory only.

    The instant is what B1 cannot currently prove, and that is a question for the owner, not
    for a test fixture. Supplying the provenance here keeps the host, document-type and rate
    rules under test without asserting anything about the real approval.
    """
    loaded = registry.load_registry()
    loaded["approval_state"]["approved_at"] = "2026-08-03T07:00:00+00:00"
    loaded["approval_state"][registry.APPROVAL_PROVENANCE_FIELD] = "test fixture, UTC"
    return loaded


class SourceRegistryTests(unittest.TestCase):
    def test_shipped_registry_approves_declared_sources(self):
        summary = registry.registry_summary()
        self.assertEqual(summary["approved_source_ids"], ["hnx", "hose", "issuer_ir", "vsdc"])
        self.assertEqual(summary["approval_state"]["state"], "APPROVED")

    def test_declared_but_unapproved_source_is_refused(self):
        decision = registry.admit("hnx", "https://www.hnx.vn/x", "corporate_action_notice",
                                  registry=_unapproved_registry())
        self.assertEqual(decision["decision"], registry.REFUSED)
        self.assertEqual(decision["reason"], registry.REASON_NOT_APPROVED)

    def test_approved_source_admits_an_allowlisted_host(self):
        decision = registry.admit("hnx", "https://www.hnx.vn/x", "corporate_action_notice",
                                  registry=_verifiable_registry())
        self.assertEqual(decision["decision"], registry.ADMITTED)
        self.assertEqual(decision["policy"]["max_attempts"], 2)

    def test_an_unverifiable_approval_instant_refuses_an_otherwise_valid_request(self):
        """The shipped instant is owner-verified, so strip its provenance to exercise the gate."""
        unprovenanced = _approved_registry()
        unprovenanced["approval_state"].pop(registry.APPROVAL_PROVENANCE_FIELD, None)
        decision = registry.admit("hnx", "https://www.hnx.vn/x", "corporate_action_notice",
                                  registry=unprovenanced)
        self.assertEqual(decision["decision"], registry.REFUSED)
        self.assertEqual(decision["reason"], registry.REASON_APPROVAL_TIMESTAMP)

    def test_host_matching_is_exact_not_suffix(self):
        decision = registry.admit("hnx", "https://evil-hnx.vn/x", "corporate_action_notice",
                                  registry=_approved_registry())
        self.assertEqual(decision["reason"], registry.REASON_HOST_NOT_ALLOWED)

    def test_undeclared_document_type_is_refused(self):
        decision = registry.admit("hnx", "https://www.hnx.vn/x", "annual_report",
                                  registry=_approved_registry())
        self.assertEqual(decision["reason"], registry.REASON_DOCUMENT_TYPE)

    def test_non_http_scheme_is_refused(self):
        decision = registry.admit("hnx", "file:///etc/passwd", "corporate_action_notice",
                                  registry=_approved_registry())
        self.assertEqual(decision["reason"], registry.REASON_BAD_URL)

    def test_rate_limit_is_enforced(self):
        decision = registry.admit("hnx", "https://www.hnx.vn/x", "corporate_action_notice",
                                  registry=_approved_registry(),
                                  seconds_since_last_request=1.0)
        self.assertEqual(decision["reason"], registry.REASON_RATE)

    def test_unknown_source_is_refused(self):
        self.assertEqual(
            registry.admit("nope", "https://x.vn/a", "corporate_action_notice")["reason"],
            registry.REASON_UNKNOWN_SOURCE)

    def test_eodhd_is_recorded_as_excluded(self):
        excluded = registry.registry_summary()["excluded_sources"]
        self.assertTrue(any(entry["source"] == "EODHD"
                            and entry["status"] == "REJECTED_BY_OWNER" for entry in excluded))


class DocumentStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.source = self.root / "incoming.html"
        self.source.write_bytes(_HTML)

    def tearDown(self):
        self._tmp.cleanup()

    def _adopt(self, execute=True, **overrides):
        kwargs = {
            "ticker": "TST", "document_type": "corporate_action_notice",
            "source_url": "https://www.hnx.vn/a", "source_authority": "HNX",
            "observed_at": "2026-08-03T00:00:00Z", "published_at": "2026-08-01",
            "execute": execute,
        }
        kwargs.update(overrides)
        return document_store.adopt_retained_document(self.root, self.source, **kwargs)

    def test_adoption_is_content_addressed_and_hash_verified(self):
        result = self._adopt()
        self.assertEqual(result["state"], "retained")
        self.assertEqual(result["content_sha256"], document_store.sha256_bytes(_HTML))
        self.assertEqual(document_store.read_document(self.root, result["document_id"]), _HTML)

    def test_readopting_identical_bytes_is_idempotent(self):
        first = self._adopt()
        second = self._adopt()
        self.assertEqual(second["state"], "already_retained")
        self.assertEqual(first["document_id"], second["document_id"])
        self.assertEqual(len(document_store.load_manifest(self.root)["records"]), 1)

    def test_different_bytes_at_the_same_content_path_raise(self):
        result = self._adopt()
        target = Path(self.root) / result["record"]["relative_path"]
        target.write_bytes(b"<html>tampered</html>")
        with self.assertRaises(document_store.HashConflict):
            self._adopt()

    def test_verify_detects_a_source_hash_mismatch(self):
        result = self._adopt()
        target = Path(self.root) / result["record"]["relative_path"]
        target.write_bytes(b"<html>tampered</html>")
        report = document_store.verify(self.root)
        self.assertFalse(report["ok"])
        self.assertEqual(report["findings"][0]["finding"], "content_sha256_mismatch")

    def test_read_document_refuses_tampered_bytes(self):
        result = self._adopt()
        (Path(self.root) / result["record"]["relative_path"]).write_bytes(b"<html>x</html>")
        with self.assertRaises(document_store.HashConflict):
            document_store.read_document(self.root, result["document_id"])

    def test_verify_detects_a_missing_document(self):
        result = self._adopt()
        (Path(self.root) / result["record"]["relative_path"]).unlink()
        report = document_store.verify(self.root)
        self.assertEqual(report["findings"][0]["finding"], "document_missing")

    def test_media_type_must_match_the_bytes(self):
        bad = self.root / "claims.pdf"
        bad.write_bytes(_HTML)
        with self.assertRaises(document_store.UnsupportedDocument):
            document_store.adopt_retained_document(
                self.root, bad, ticker="TST", document_type="corporate_action_notice",
                source_url="https://www.hnx.vn/b", source_authority="HNX",
                observed_at="2026-08-03T00:00:00Z", execute=True)

    def test_unknown_document_type_is_refused(self):
        with self.assertRaises(document_store.UnsupportedDocument):
            self._adopt(document_type="something_else")

    def test_supersession_is_a_new_record_not_an_edit(self):
        first = self._adopt()
        replacement = self.root / "v2.html"
        replacement.write_bytes(b"<html><body>v2</body></html>")
        second = document_store.adopt_retained_document(
            self.root, replacement, ticker="TST", document_type="corporate_action_notice",
            source_url="https://www.hnx.vn/a-v2", source_authority="HNX",
            observed_at="2026-08-04T00:00:00Z",
            supersedes_document_id=first["document_id"], execute=True)
        records = document_store.load_manifest(self.root)["records"]
        self.assertEqual(len(records), 2)
        self.assertEqual(second["record"]["supersedes_document_id"], first["document_id"])
        kept = next(r for r in records if r["document_id"] == first["document_id"])
        self.assertEqual(kept["content_sha256"], document_store.sha256_bytes(_HTML))

    def test_store_has_no_delete_function(self):
        self.assertFalse([name for name in dir(document_store)
                          if "delete" in name or "remove" in name])


def _document(document_type="corporate_action_notice", **overrides):
    record = {
        "document_id": "d1", "ticker": "TST", "document_type": document_type,
        "source_authority": "HNX", "source_url": "https://www.hnx.vn/a",
        "content_sha256": "a" * 64, "published_at": "2026-07-07",
        "observed_at": "2026-08-03T00:00:00Z", "media_type": "text/html",
    }
    record.update(overrides)
    return record


_HOSE_NOTICE = (
    "Thông báo về ngày giao dịch cổ phiếu phát hành trả cổ tức năm 2025. "
    "Số lượng chứng khoán thay đổi niêm yết: 767.498.665 cổ phiếu. "
    "Lý do thay đổi niêm yết: Phát hành cổ phiếu để trả cổ tức năm 2025. "
    "Số lượng chứng khoán sau khi thay đổi niêm yết: 8.442.964.520 cổ phiếu. "
    "Ngày thay đổi niêm yết có hiệu lực: 02/07/2026. "
    "Ngày giao dịch của chứng khoán thay đổi niêm yết: 15/07/2026."
)


class EventExtractionTests(unittest.TestCase):
    def test_vsdc_html_body_keeps_content_after_self_closing_breaks(self):
        payload = (b'<div class="content-category"><p>Record date: 18/08/2026<br />'
                   b'Payment rate: 5:1 (Shareholders are entitled to 1 new share '
                   b'for every 5 shares they own);<br />- planned number of shares to be '
                   b'issued: 500,219,550 shares</p></div>')
        extracted = events.extract_text(payload, "text/html")
        self.assertIn("Record date: 18/08/2026", extracted)
        self.assertIn("Payment rate: 5:1", extracted)
        self.assertIn("planned number of shares to be issued: 500,219,550", extracted)

    def test_vsdc_record_date_template_accepts_its_current_direct_wording(self):
        payload = (b'<div class="content-category">VSDC would like to announce the record '
                   b'date of corporate action processing as follows: Record date: 18/08/2026 '
                   b'Reason: Payment of 2025 cash dividend; Share issuance for raising share '
                   b'capital from owner\'s equity. Payment rate: 5:1 (Shareholders are '
                   b'entitled to 1 new share for every 5 shares they own)'
                   b'</div>')
        import hashlib

        record = _document(document_type="last_registration_date_notice", ticker="SSI",
                           source_authority="Vietnam Securities Depository and Clearing Corporation",
                           source_url="https://vsd.vn/en/ad/test",
                           content_sha256=hashlib.sha256(payload).hexdigest())
        typed = events.classify_retained_document(record, payload)
        observation = events.extract_event_observation(
            typed, events.extract_text(payload, typed["media_type"]))
        self.assertEqual(typed["document_type"], "last_registration_date_notice")
        self.assertEqual(observation["record_date"], "2026-08-18")
        self.assertEqual(observation["event_type"], "bonus_shares")
        self.assertEqual(observation["stock_ratio"], 0.2)
        self.assertIsNone(observation["shares_issued"])
        self.assertIsNone(observation["ex_date"])
        self.assertIn("ex_date_absent", observation["warnings"])
        built = ledger.build_ledger([observation])
        self.assertEqual(built["entry_count"], 0)
        self.assertEqual(built["unlinked_observations"][0]["reason"],
                         "no share-change identity; cannot be linked to an event")

    def test_hose_style_notice_extracts_a_complete_executed_event(self):
        observation = events.extract_event_observation(
            _document("listing_change_notice"), _HOSE_NOTICE)
        self.assertEqual(observation["event_type"], "stock_dividend")
        self.assertEqual(observation["shares_issued"], 767_498_665)
        self.assertEqual(observation["shares_after"], 8_442_964_520)
        self.assertEqual(observation["lifecycle_state"], "executed")
        self.assertAlmostEqual(observation["stock_ratio"], 0.0999937567, places=9)

    def test_ex_date_is_never_substituted(self):
        observation = events.extract_event_observation(
            _document("listing_change_notice"), _HOSE_NOTICE)
        self.assertIsNone(observation["ex_date"])
        self.assertIn("ex_date_absent", observation["warnings"])
        self.assertIn("never", observation["absent_fields"]["ex_date"])

    def test_a_resolution_may_not_assert_execution(self):
        text = _HOSE_NOTICE + " Nghị quyết Đại hội đồng cổ đông."
        observation = events.extract_event_observation(
            _document("agm_document_or_resolution"), text)
        self.assertEqual(observation["lifecycle_state"], "approved")
        self.assertEqual(observation["lifecycle_ceiling"], "approved")

    def test_share_change_form_with_unreadable_columns_refuses_numbers(self):
        # The retained HPG scan's shape: intact English row labels, scrambled column order.
        text = ("NOTICE OF CHANGE IN THE NUMBER OF VOTING SHARES "
                "phát hành cổ phiếu để trả cổ tức "
                "Charter capital 76.764.658 7.674.986.650 84.429.645.700 "
                "Total number of shares 7.675.465.855 767.498.665 8.M2.964.520 "
                "Number of voting shares 7.675.465.855 767.498.665 8.M2.964.520")
        observation = events.extract_event_observation(_document(), text)
        self.assertIsNone(observation["shares_before"])
        self.assertIsNone(observation["shares_after"])
        self.assertIn("share_change_form_numeric_extraction_refused", observation["warnings"])

    def test_no_event_cue_yields_no_event_type(self):
        observation = events.extract_event_observation(_document(), "Bao cao thuong nien 2025")
        self.assertIsNone(observation["event_type"])

    def test_date_parsing_rejects_impossible_dates(self):
        self.assertIsNone(events.parse_vietnamese_date("32/13/2026"))
        self.assertEqual(events.parse_vietnamese_date("02/07/2026"), "2026-07-02")

    def test_extract_text_rejects_an_unsupported_media_type(self):
        with self.assertRaises(ValueError):
            events.extract_text(b"x", "application/zip")


class VcbB2TypedExtractionTests(unittest.TestCase):
    """B3 uses only the one immutable B2 VCB acquisition, never a live request."""

    RETAINED = (ROOT.parent / "operations-review" / "vcb-iss-official-acquisition-20260808")

    def setUp(self):
        manifest_path = self.RETAINED / "official_document_acquisition_manifest.json"
        if not manifest_path.is_file():
            self.skipTest("retained B2 VCB acquisition is not present")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.record = next((record for record in manifest["records"]
                            if record["canonical_url"] == "https://vsd.vn/en/ad/180140"), None)
        if self.record is None:
            self.skipTest("retained B2 VCB record-date acquisition is not present")
        self.payload = (self.RETAINED / self.record["relative_path"]).read_bytes()
        self.typed = events.classify_retained_document(self.record, self.payload)
        self.text = events.extract_text(self.payload, self.typed["media_type"])

    def test_exact_typed_fields_are_supported_by_the_retained_notice(self):
        observation = events.extract_event_observation(self.typed, self.text)
        self.assertEqual(observation["document_type"], "last_registration_date_notice")
        self.assertEqual(observation["event_type"], "stock_dividend")
        self.assertEqual(observation["lifecycle_state"], "record_date_confirmed")
        self.assertEqual(observation["record_date"], "2025-03-13")
        self.assertEqual(observation["stock_ratio"], 0.495)
        self.assertEqual(observation["ratio_basis"], "new_shares_per_existing_share")

    def test_missing_dates_and_share_counts_remain_unavailable(self):
        observation = events.extract_event_observation(self.typed, self.text)
        for field in ("approval_date", "ex_date", "payment_date", "listing_effective_date",
                      "trading_date", "shares_before", "shares_issued", "shares_after"):
            self.assertIsNone(observation[field], field)
        self.assertIn("ex_date_absent", observation["warnings"])
        self.assertIn("never substituted", observation["absent_fields"]["ex_date"])

    def test_hash_and_document_provenance_are_carried_to_the_observation(self):
        observation = events.extract_event_observation(self.typed, self.text)
        self.assertEqual(observation["document_id"], self.record["document_id"])
        self.assertEqual(observation["content_sha256"], self.record["sha256"])
        self.assertEqual(observation["source_url"], self.record["canonical_url"])
        self.assertEqual(observation["document_classification"]["acquisition_document_class"],
                         "corporate_action_notice")
        cited = {row["field"] for row in observation["citations"]}
        self.assertTrue({"record_date", "stock_ratio"}.issubset(cited))

    def test_conflicting_or_ambiguous_inputs_are_refused_fail_closed(self):
        conflicting_type = dict(self.record, document_type="ex_right_notice")
        with self.assertRaisesRegex(ValueError, "document_type_conflicts"):
            events.classify_retained_document(conflicting_type, self.payload)
        ambiguous_text = self.text.replace("495 new shares", "400 new shares", 1)
        observation = events.extract_event_observation(self.typed, ambiguous_text)
        self.assertIsNone(observation["stock_ratio"])
        self.assertEqual(observation["absent_fields"]["stock_ratio"],
                         "execution_rate_wordings_conflict")

    def test_repeat_run_is_deterministic(self):
        first = events.extract_event_observation(self.typed, self.text)
        second = events.extract_event_observation(self.typed, self.text)
        self.assertEqual(first, second)


class VcbListingChangeCertificateTests(unittest.TestCase):
    """The supplied VSDC certificate is exercised offline from its governed B2 retention."""

    RETAINED = (ROOT.parent / "operations-review" / "vcb-iss-official-acquisition-20260808")
    URL = "https://vsd.vn/en/ad/181754"

    def setUp(self):
        manifest_path = self.RETAINED / "official_document_acquisition_manifest.json"
        if not manifest_path.is_file():
            self.skipTest("retained VCB listing-change candidate is not present")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.record = next((record for record in manifest["records"]
                            if record["canonical_url"] == self.URL), None)
        if self.record is None:
            self.skipTest("retained VCB listing-change candidate is not present")
        self.payload = (self.RETAINED / self.record["relative_path"]).read_bytes()
        self.typed = events.classify_retained_document(self.record, self.payload)
        self.text = events.extract_text(self.payload, self.typed["media_type"])

    def test_retained_acquisition_hash_and_discovery_provenance_are_carried(self):
        observation = events.extract_event_observation(self.typed, self.text)
        self.assertEqual(self.record["source_id"], "vsdc")
        self.assertEqual(observation["document_id"], self.record["document_id"])
        self.assertEqual(observation["content_sha256"], self.record["sha256"])
        self.assertEqual(observation["source_url"], self.URL)
        self.assertEqual(observation["discovery_provenance"], self.record["discovery_provenance"])
        self.assertEqual(observation["discovery_provenance"]["listing_url"],
                         "https://vsd.vn/en/ad/177303")

    def test_exact_registered_securities_certificate_fields_are_extracted(self):
        observation = events.extract_event_observation(self.typed, self.text)
        self.assertEqual(observation["document_type"], "corporate_action_notice")
        self.assertEqual(observation["event_type"], None)
        self.assertEqual(observation["lifecycle_state"], "announced")
        self.assertEqual(observation["registration_effective_date"], "2025-04-15")
        self.assertEqual(observation["depository_acceptance_date"], "2025-04-17")
        self.assertEqual(observation["registered_securities_added"], 2_766_583_832)
        self.assertEqual(observation["registered_securities_total"], 8_355_675_094)
        self.assertEqual(observation["isin"], "VN000000VCB4")

    def test_listing_trading_and_corporate_action_fields_remain_unknown(self):
        observation = events.extract_event_observation(self.typed, self.text)
        for field in ("ex_date", "record_date", "payment_date", "listing_effective_date",
                      "trading_date", "shares_before", "shares_issued", "shares_after",
                      "stock_ratio"):
            self.assertIsNone(observation[field], field)
        self.assertIn("never substituted", observation["absent_fields"]["ex_date"])

    def test_date_roles_are_separate(self):
        observation = events.extract_event_observation(self.typed, self.text)
        self.assertNotEqual(observation["registration_effective_date"],
                            observation["depository_acceptance_date"])
        self.assertIsNone(observation["listing_effective_date"])
        self.assertIsNone(observation["trading_date"])

    def test_ambiguous_or_conflicting_inputs_are_refused_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "document_type_conflicts"):
            events.classify_retained_document(dict(self.record,
                                                    document_type="last_registration_date_notice"),
                                             self.payload)
        duplicate_total = self.text + " Total quantity of registered securities: 8,355,675,095"
        observation = events.extract_event_observation(self.typed, duplicate_total)
        self.assertIsNone(observation["registered_securities_total"])
        self.assertEqual(observation["absent_fields"]["registered_securities_total"],
                         "direct_label_missing_or_ambiguous")

    def test_record_date_notice_is_not_cross_linked_without_a_direct_identifier(self):
        other_record = next((record for record in json.loads(
            (self.RETAINED / "official_document_acquisition_manifest.json").read_text())["records"]
            if record["canonical_url"] == "https://vsd.vn/en/ad/180140"), None)
        if other_record is None:
            self.skipTest("retained VCB record-date notice is not present")
        other_payload = (self.RETAINED / other_record["relative_path"]).read_bytes()
        other_typed = events.classify_retained_document(other_record, other_payload)
        other = events.extract_event_observation(
            other_typed, events.extract_text(other_payload, other_typed["media_type"]))
        self.assertEqual(other["isin"], events.extract_event_observation(self.typed, self.text)["isin"])
        self.assertEqual(events.assess_direct_event_cross_link(other,
                                                                events.extract_event_observation(self.typed, self.text)),
                         {"state": "not_linked",
                          "reason": "direct_cross_document_event_identifier_absent"})

    def test_repeat_run_is_deterministic(self):
        first = events.extract_event_observation(self.typed, self.text)
        second = events.extract_event_observation(self.typed, self.text)
        self.assertEqual(first, second)


class VcbListingTransferNoticeTests(unittest.TestCase):
    """One offline VSDC discovery candidate and its hash-verified B2/B3 result."""

    RETAINED = (ROOT.parent / "operations-review" / "vcb-iss-official-acquisition-20260808")
    URL = "https://vsd.vn/en/ad/182319"

    def setUp(self):
        manifest_path = self.RETAINED / "official_document_acquisition_manifest.json"
        if not manifest_path.is_file():
            self.skipTest("retained VCB listing-transfer notice is not present")
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.record = next((record for record in self.manifest["records"]
                            if record["canonical_url"] == self.URL), None)
        if self.record is None:
            self.skipTest("retained VCB listing-transfer notice is not present")
        self.payload = (self.RETAINED / self.record["relative_path"]).read_bytes()
        self.typed = events.classify_retained_document(self.record, self.payload)
        self.text = events.extract_text(self.payload, self.typed["media_type"])

    def test_one_offline_discovery_pass_exposes_the_approved_candidate(self):
        source = next((record for record in self.manifest["records"]
                       if record["canonical_url"] == "https://vsd.vn/en/ad/181754"), None)
        if source is None:
            self.skipTest("retained VCB registration certificate is not present")
        from official_listing_page_parser import parse_index_page
        from official_source_registry import load_registry
        parsed = parse_index_page(
            (self.RETAINED / source["relative_path"]).read_bytes(),
            listing_url=source["canonical_url"], source_id="vsdc", ticker="VCB",
            registry=load_registry())
        candidate = next(row for row in parsed["links"] if row["canonical_url"] == self.URL)
        self.assertEqual(candidate["page_facts"]["visible_date"], "2025-04-29")
        self.assertEqual(candidate["inference"]["cue"], "listing change")

    def test_hash_provenance_and_explicit_listing_semantics_are_retained(self):
        observation = events.extract_event_observation(self.typed, self.text)
        self.assertEqual(observation["document_id"], self.record["document_id"])
        self.assertEqual(observation["content_sha256"], self.record["sha256"])
        self.assertEqual(observation["source_id"], "vsdc")
        self.assertEqual(observation["discovery_provenance"]["listing_url"],
                         "https://vsd.vn/en/ad/181754")
        self.assertEqual(observation["document_type"], "corporate_action_notice")
        self.assertEqual(observation["event_type"], "stock_dividend")
        self.assertEqual(observation["record_date"], "2025-03-13")
        self.assertEqual(observation["trading_date"], "2025-05-09")

    def test_direct_identity_reference_permits_only_the_supported_cross_link(self):
        prior = next(record for record in self.manifest["records"]
                     if record["canonical_url"] == "https://vsd.vn/en/ad/180140")
        prior_payload = (self.RETAINED / prior["relative_path"]).read_bytes()
        prior_typed = events.classify_retained_document(prior, prior_payload)
        prior_observation = events.extract_event_observation(
            prior_typed, events.extract_text(prior_payload, prior_typed["media_type"]))
        observation = events.extract_event_observation(self.typed, self.text)
        self.assertEqual(observation["direct_event_reference"],
                         prior_observation["direct_event_reference"])
        self.assertEqual(events.assess_direct_event_cross_link(prior_observation, observation),
                         {"state": "linked",
                          "reason": "matching_direct_cross_document_event_identifier"})

    def test_date_roles_and_unsupported_fields_remain_separate(self):
        observation = events.extract_event_observation(self.typed, self.text)
        self.assertNotEqual(observation["record_date"], observation["trading_date"])
        for field in ("ex_date", "payment_date", "listing_effective_date", "shares_before",
                      "shares_issued", "shares_after", "stock_ratio"):
            self.assertIsNone(observation[field], field)
        self.assertIn("never substituted", observation["absent_fields"]["ex_date"])
        self.assertEqual(observation["lifecycle_state"], "announced")

    def test_conflicts_and_ambiguous_identity_are_refused_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "document_type_conflicts"):
            events.classify_retained_document(dict(self.record,
                                                    document_type="last_registration_date_notice"),
                                             self.payload)
        ambiguous = self.text + " Issuing shares to pay dividends from remaining profit in 2018 and 2021"
        observation = events.extract_event_observation(self.typed, ambiguous)
        self.assertIsNone(observation["direct_event_reference"])
        self.assertEqual(observation["absent_fields"]["direct_event_reference"],
                         "direct_dividend_event_reference_missing_or_ambiguous")

    def test_repeat_run_is_deterministic(self):
        first = events.extract_event_observation(self.typed, self.text)
        second = events.extract_event_observation(self.typed, self.text)
        self.assertEqual(first, second)


def _observation(event_type="stock_dividend", **overrides):
    record = {
        "observation_id": "o1", "ticker": "TST", "event_type": event_type,
        "lifecycle_state": "executed", "document_id": "d1", "document_type": "listing_change_notice",
        "source_authority": "HNX", "source_url": "https://www.hnx.vn/a",
        "content_sha256": "a" * 64, "announcement_date": "2026-07-07",
        "ex_date": None, "record_date": None, "payment_or_execution_date": "2026-07-02",
        "trading_date": "2026-07-15", "shares_before": None, "shares_issued": 767_498_665,
        "shares_after": 8_442_964_520, "cash_amount_per_share": None,
        "stock_ratio": 0.0999937567, "ratio_basis": "new_shares_per_existing_share",
        "rights_ratio": None, "subscription_price": None, "approval_date": None,
        "citations": [], "absent_fields": {}, "warnings": [],
    }
    record.update(overrides)
    return record


class LedgerTests(unittest.TestCase):
    def test_identical_observations_are_deduplicated(self):
        built = ledger.build_ledger([_observation(), _observation()])
        self.assertEqual(built["entry_count"], 1)
        self.assertEqual(len(built["duplicate_observations"]), 1)

    def test_two_documents_linking_to_one_event(self):
        issuer = _observation(observation_id="o2", document_id="d2", content_sha256="b" * 64,
                              shares_before=7_675_465_855, shares_after=None,
                              lifecycle_state="announced")
        built = ledger.build_ledger([_observation(), issuer])
        self.assertEqual(built["entry_count"], 1)
        entry = built["entries"][0]
        self.assertEqual(len(entry["source_document_ids"]), 2)
        self.assertEqual(entry["arithmetic_corroboration"]["state"], "confirmed")
        self.assertTrue(entry["arithmetic_corroboration"]["cross_document"])
        self.assertEqual(entry["qualification_state"], "qualified")

    def test_violated_share_identity_is_a_conflict(self):
        issuer = _observation(observation_id="o2", document_id="d2", content_sha256="b" * 64,
                              shares_before=1, shares_after=None)
        built = ledger.build_ledger([_observation(), issuer])
        self.assertEqual(built["entries"][0]["qualification_state"], "conflicted")

    def test_disagreeing_documents_conflict_rather_than_prefer_a_source(self):
        other = _observation(observation_id="o2", document_id="d2", content_sha256="b" * 64,
                             shares_after=9_000_000_000)
        built = ledger.build_ledger([_observation(), other])
        entry = built["entries"][0]
        self.assertEqual(entry["conflict_status"], "conflicted")
        self.assertEqual(entry["qualification_state"], "conflicted")
        self.assertIsNone(entry["shares_after"])

    def test_adjustment_factor_is_fail_closed_without_an_ex_date(self):
        entry = ledger.build_ledger([_observation()])["entries"][0]
        self.assertEqual(entry["adjustment_factor_status"], ledger.FACTOR_NOT_READY)
        self.assertIsNone(entry["adjustment_factor"])
        self.assertIn("missing_explicit_official_ex_date", entry["adjustment_factor_blocked_by"])

    def test_adjustment_factor_derived_only_with_an_explicit_ex_date(self):
        entry = ledger.build_ledger([_observation(ex_date="2026-06-20")])["entries"][0]
        self.assertEqual(entry["adjustment_factor_status"], ledger.FACTOR_READY)
        self.assertAlmostEqual(entry["adjustment_factor"], 1 / 1.0999937567, places=9)
        self.assertEqual(entry["authority_state"], "outside_production_authority")

    def test_cash_dividend_factor_is_not_applicable_here(self):
        entry = ledger.build_ledger([
            _observation(event_type="cash_dividend", ex_date="2026-06-20")])["entries"][0]
        self.assertEqual(entry["adjustment_factor_status"], ledger.FACTOR_NOT_APPLICABLE)

    def test_cancellation_supersedes_without_editing_the_original(self):
        original = _observation()
        cancellation = _observation(observation_id="o9", document_id="d9",
                                    content_sha256="c" * 64, event_type="cancellation",
                                    payment_or_execution_date="2026-08-01")
        built = ledger.build_ledger([original, cancellation])
        self.assertEqual(built["entry_count"], 2)
        superseded = next(e for e in built["entries"] if e["event_type"] == "stock_dividend")
        replacement = next(e for e in built["entries"] if e["event_type"] == "cancellation")
        self.assertEqual(superseded["superseded_by"], replacement["event_id"])
        self.assertEqual(superseded["lifecycle_state"], "cancelled")
        self.assertEqual(replacement["supersedes"], superseded["event_id"])
        self.assertEqual(superseded["shares_issued"], 767_498_665)

    def test_amendment_marks_the_original_amended(self):
        built = ledger.build_ledger([
            _observation(),
            _observation(observation_id="o8", document_id="d8", content_sha256="e" * 64,
                         event_type="amendment", payment_or_execution_date="2026-08-05")])
        superseded = next(e for e in built["entries"] if e["event_type"] == "stock_dividend")
        self.assertEqual(superseded["lifecycle_state"], "amended")

    def test_observation_without_event_type_is_reported_unlinked(self):
        built = ledger.build_ledger([_observation(event_type=None)])
        self.assertEqual(built["entry_count"], 0)
        self.assertEqual(len(built["unlinked_observations"]), 1)

    def test_replay_is_deterministic_and_order_independent(self):
        one = _observation()
        two = _observation(observation_id="o2", document_id="d2", content_sha256="b" * 64,
                           shares_before=7_675_465_855, shares_after=None)
        first = ledger.build_ledger([one, two])["replay_fingerprint"]
        second = ledger.build_ledger([two, one])["replay_fingerprint"]
        self.assertEqual(first, second)

    def test_all_designed_event_types_are_supported(self):
        for event_type in ("cash_dividend", "stock_dividend", "bonus_shares", "rights_issue",
                           "stock_split", "reverse_split", "capital_return", "cancellation",
                           "amendment"):
            self.assertIn(event_type, events.EVENT_TYPES)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _reconcile(self, fetcher, tickers=("AAA", "BBB"), **kwargs):
        return reconciliation.reconcile(
            self.root, missing_tickers=tickers, generated_at="T", execute=True,
            fetcher=fetcher, sleep=lambda _seconds: None, **kwargs)

    def test_dry_run_issues_no_request(self):
        calls = []
        reconciliation.reconcile(
            self.root, missing_tickers=["AAA"], generated_at="T", execute=False,
            fetcher=lambda *a, **k: calls.append(a), sleep=lambda _s: None)
        self.assertEqual(calls, [])

    def test_rows_returned_classify_as_payload_available(self):
        result = self._reconcile(lambda *a, **k: [1, 2, 3], tickers=["AAA"])
        self.assertEqual(result["report"]["classification_counts"],
                         {"payload_available": 1})

    def test_empty_source_is_confirmed_not_guessed(self):
        result = self._reconcile(lambda *a, **k: [], tickers=["AAA"])
        self.assertEqual(result["report"]["classification_counts"],
                         {"source_empty_confirmed": 1})

    def test_provider_error_is_distinguished_from_source_empty(self):
        def broken(*_args, **_kwargs):
            raise KeyError("unexpected schema column")

        result = self._reconcile(broken, tickers=["AAA"])
        self.assertEqual(result["report"]["classification_counts"], {"provider_error": 1})
        self.assertTrue(result["report"]["provider_error_kinds"])

    def test_network_error_is_a_retrieval_failure(self):
        def flaky(*_args, **_kwargs):
            raise TimeoutError("connection timeout")

        result = self._reconcile(flaky, tickers=["AAA"])
        self.assertEqual(result["report"]["classification_counts"], {"retrieval_failure": 1})

    def test_max_tickers_bounds_the_run_and_leaves_the_rest_resumable(self):
        result = self._reconcile(lambda *a, **k: [], tickers=["AAA", "BBB", "CCC"],
                                 max_tickers=1)
        self.assertEqual(len(result["probed"]), 1)
        self.assertEqual(len(result["remaining"]), 2)

    def test_a_terminal_classification_is_never_reprobed(self):
        self._reconcile(lambda *a, **k: [], tickers=["AAA"])
        calls = []

        def counting(*args, **kwargs):
            calls.append(args)
            return []

        self._reconcile(counting, tickers=["AAA"])
        self.assertEqual(calls, [], "a settled ticker must not be probed again")

    def test_interrupted_run_resumes_from_written_state(self):
        seen = []

        def once(ticker, *_args, **_kwargs):
            seen.append(ticker)
            if ticker == "BBB" and len(seen) < 8:
                raise TimeoutError("connection reset")
            return []

        self._reconcile(once, tickers=["AAA", "BBB"], max_tickers=1)
        state = reconciliation.load_state(self.root)
        self.assertEqual([entry["ticker"] for entry in state["tickers"]
                          if entry["classification"] != reconciliation.NOT_PROBED], ["AAA"])
        second = self._reconcile(lambda *a, **k: [], tickers=["AAA", "BBB"])
        self.assertEqual(second["probed"], ["BBB"])

    def test_non_equity_instrument_is_resolved_without_a_request(self):
        calls = []
        result = reconciliation.reconcile(
            self.root, missing_tickers=["FUND"], generated_at="T", execute=True,
            instrument_of={"FUND": "FUND_CERTIFICATE"},
            fetcher=lambda *a, **k: calls.append(a), sleep=lambda _s: None)
        self.assertEqual(calls, [])
        self.assertEqual(result["report"]["classification_counts"], {"unsupported_entity": 1})

    def test_no_payload_is_ever_written(self):
        self._reconcile(lambda *a, **k: [1, 2, 3], tickers=["AAA"])
        self.assertEqual(list(self.root.glob("**/*.parquet")), [])


class BoundedVerticalSliceTests(unittest.TestCase):
    """The real retained HPG evidence, offline. Skips when the evidence is absent."""

    RETAINED = (ROOT / "operations-review" / "hpg-vnm-current-share-bridge-20260802"
                / "documents" / "HPG" / "2026" / "corporate_action_notice")

    def setUp(self):
        self.html = self.RETAINED / (
            "cb41c96ef78bed7654030e55bb06dea22d051b1c9fcf1a6cf024e9f964563c1c.html")
        self.pdf = self.RETAINED / (
            "8bbae21fbb3e6c11f925385ac35b290e86e3db8753188131acbbba3bad5b29b2.pdf")
        if not self.html.is_file() or not self.pdf.is_file():
            self.skipTest("retained HPG corporate-action evidence is not present")

    def test_hose_recital_yields_a_qualified_executed_event(self):
        text = events.extract_text(self.html.read_bytes(), "text/html")
        observation = events.extract_event_observation(
            _document("listing_change_notice", document_id="html",
                      content_sha256=document_store.sha256_bytes(self.html.read_bytes())),
            text)
        built = ledger.build_ledger([observation])
        entry = built["entries"][0]
        self.assertEqual(entry["event_type"], "stock_dividend")
        self.assertEqual(entry["shares_issued"], 767_498_665)
        self.assertEqual(entry["shares_after"], 8_442_964_520)
        self.assertEqual(entry["qualification_state"], "qualified")
        self.assertEqual(entry["adjustment_factor_status"], ledger.FACTOR_NOT_READY)

    def test_scanned_issuer_notice_refuses_its_ocr_damaged_numbers(self):
        text = events.extract_text(self.pdf.read_bytes(), "application/pdf")
        observation = events.extract_event_observation(
            _document("corporate_action_notice", document_id="pdf",
                      content_sha256=document_store.sha256_bytes(self.pdf.read_bytes())),
            text)
        # 76,764,658 is the charter-capital row and 2,964,520 is the damaged post-change
        # count. Neither may be emitted as a share count.
        self.assertNotIn(observation["shares_after"], (76_764_658, 2_964_520))
        self.assertIsNone(observation["shares_after"])

    def test_slice_replay_is_stable_across_runs(self):
        observations = []
        for path, media, doc_type in ((self.html, "text/html", "listing_change_notice"),
                                      (self.pdf, "application/pdf", "corporate_action_notice")):
            payload = path.read_bytes()
            observations.append(events.extract_event_observation(
                _document(doc_type, document_id=path.stem[:12],
                          content_sha256=document_store.sha256_bytes(payload)),
                events.extract_text(payload, media)))
        self.assertEqual(ledger.build_ledger(observations)["replay_fingerprint"],
                         ledger.build_ledger(observations)["replay_fingerprint"])


# ==========================================================================
# P0-A.2 document-authority coverage extension (2026-08-17):
#   issuer_ir `listing_change_notice` support through the existing B3/B4 path,
#   plus real-evidence validation for HPG (issuer_ir) and SSI (vsdc, already-supported).
#   Prior art `1183c72`->`d7b9bf3` was reviewed and dispositioned REJECT_AND_REIMPLEMENT:
#   this extends corporate_action_events.py/official_corporate_action_ledger.py directly,
#   with no ticker-specific runtime branch and no second corporate-action pipeline.
# ==========================================================================


def _issuer_listing_change_html(ticker, org_name="CONG TY CO PHAN TEST", notice_no="999",
                                shares_change="1.000.000", shares_after="11.000.000"):
    """A synthetic issuer-IR recital of an exchange listing-change notice.

    The shape (recital sentence, then a "Tổ chức niêm yết:" / "Mã chứng khoán:" labelled
    list) is the exchange's own template wording, reused verbatim by whichever issuer's IR
    site reprints it -- it names no company and no ticker by construction; the ticker is a
    parameter like any other field.
    """
    return (
        '<html><body><div class="content-detail default">'
        '<h1>Thông báo về ngày giao dịch cổ phiếu phát hành trả cổ tức</h1>'
        '<p class="clear time">01/01/2026</p>'
        '<div class="detail css-content default">'
        f'<p>Ngày 01/01/2026 Sở Giao dịch Chứng khoán ra Thông báo số {notice_no}/TB-SGDHCM '
        'về việc giao dịch chứng khoán thay đổi niêm yết cụ thể như sau:</p>'
        '<ul>'
        f'<li>Tổ chức niêm yết: {org_name}</li>'
        '<li>Loại chứng khoán: Cổ phiếu phổ thông</li>'
        f'<li>Mã chứng khoán: {ticker}</li>'
        f'<li>Số lượng chứng khoán thay đổi niêm yết: {shares_change} cổ phiếu</li>'
        '<li>Lý do thay đổi niêm yết: Phát hành cổ phiếu để trả cổ tức.</li>'
        f'<li>Số lượng chứng khoán sau khi thay đổi niêm yết: {shares_after} cổ phiếu</li>'
        '<li>Ngày thay đổi niêm yết có hiệu lực: 15/01/2026</li>'
        '</ul></div></div></body></html>'
    ).encode("utf-8")


def _issuer_ir_document(ticker, payload, **overrides):
    import hashlib

    record = {
        "document_id": f"issuer-ir-{ticker.lower()}", "ticker": ticker,
        "source_authority": f"{ticker} investor relations",
        "source_id": "issuer_ir",
        "source_url": f"https://www.example-issuer.vn/notice-{ticker.lower()}.html",
        "content_sha256": hashlib.sha256(payload).hexdigest(),
        "published_at": "2026-01-01", "observed_at": "2026-01-02T00:00:00Z",
        "media_type": "text/html",
    }
    record.update(overrides)
    return record


class IssuerIrListingChangeClassificationTests(unittest.TestCase):
    """`classify_retained_document` extended to issuer_ir, gated by source_id, not ticker."""

    def test_generic_path_classifies_two_unrelated_tickers_identically(self):
        for ticker in ("AAA", "ZZZ"):
            payload = _issuer_listing_change_html(ticker)
            typed = events.classify_retained_document(_issuer_ir_document(ticker, payload), payload)
            self.assertEqual(typed["document_type"], "listing_change_notice")
            self.assertEqual(typed["document_classification"]["basis"],
                             "document_internal_issuer_listing_change_recital_cues")

    def test_classification_dispatch_has_no_ticker_equality_check(self):
        import inspect

        source = inspect.getsource(events.classify_retained_document)
        self.assertNotRegex(source, r'ticker[^\n]*==\s*["\']',
                            "classification must stay document-class based, never ticker based")

    def test_mismatched_declared_ticker_is_refused_fail_closed(self):
        payload = _issuer_listing_change_html("AAA")
        record = _issuer_ir_document("BBB", payload)
        with self.assertRaisesRegex(ValueError, "document_ticker_conflicts_with_document_text"):
            events.classify_retained_document(record, payload)

    def test_issuer_ir_document_without_listing_change_cues_is_refused(self):
        payload = b"<html><body><h1>Bao cao thuong nien 2025</h1><p>Annual report only.</p></body></html>"
        record = _issuer_ir_document("AAA", payload)
        with self.assertRaisesRegex(ValueError, "document_classification_unsupported_or_ambiguous"):
            events.classify_retained_document(record, payload)

    def test_unsupported_source_id_is_still_refused(self):
        payload = _issuer_listing_change_html("AAA")
        record = _issuer_ir_document("AAA", payload, source_id="some_other_source",
                                     source_authority="Not VSDC and not issuer_ir")
        with self.assertRaisesRegex(ValueError, "document_classification_unsupported_or_ambiguous"):
            events.classify_retained_document(record, payload)


class IssuerIrRealHpgListingChangeTests(unittest.TestCase):
    """The already-retained HPG issuer-IR listing-change notice, classified from raw bytes."""

    RETAINED = (ROOT / "operations-review" / "hpg-vnm-current-share-bridge-20260802"
                / "documents" / "HPG" / "2026" / "corporate_action_notice")
    HTML_NAME = "cb41c96ef78bed7654030e55bb06dea22d051b1c9fcf1a6cf024e9f964563c1c.html"

    def setUp(self):
        self.html = self.RETAINED / self.HTML_NAME
        if not self.html.is_file():
            self.skipTest("retained HPG issuer-IR listing-change notice is not present")
        self.payload = self.html.read_bytes()
        self.record = {
            "document_id": "hpg-listing-change-2026", "ticker": "HPG",
            "source_id": "issuer_ir",
            "source_authority": ("Hoa Phat Group Joint Stock Company investor relations, "
                                 "reciting HOSE notice 1475/TB-SGDHCM"),
            "source_url": ("https://www.hoaphat.com.vn/tin-tuc/"
                           "thong-bao-ve-ngay-giao-dich-co-phieu-phat-hanh-tra-co-tuc-nam-2025-1.html"),
            "content_sha256": document_store.sha256_bytes(self.payload),
            "published_at": "2026-07-07", "observed_at": "2026-08-02T08:10:00Z",
            "media_type": "text/html",
        }

    def test_real_notice_classifies_via_the_generic_issuer_ir_path(self):
        typed = events.classify_retained_document(self.record, self.payload)
        self.assertEqual(typed["document_type"], "listing_change_notice")
        self.assertEqual(typed["document_classification"]["basis"],
                         "document_internal_issuer_listing_change_recital_cues")
        self.assertEqual(typed["ticker"], "HPG")

    def test_real_notice_end_to_end_matches_the_existing_qualified_result(self):
        typed = events.classify_retained_document(self.record, self.payload)
        text = events.extract_text(self.payload, typed["media_type"])
        observation = events.extract_event_observation(typed, text)
        self.assertEqual(observation["event_type"], "stock_dividend")
        self.assertEqual(observation["shares_issued"], 767_498_665)
        self.assertEqual(observation["shares_after"], 8_442_964_520)
        self.assertEqual(observation["lifecycle_state"], "executed")
        self.assertIsNone(observation["ex_date"])
        built = ledger.build_ledger([observation])
        entry = built["entries"][0]
        self.assertEqual(entry["qualification_state"], "qualified")
        self.assertEqual(entry["adjustment_factor_status"], ledger.FACTOR_NOT_READY)
        self.assertIn("missing_explicit_official_ex_date", entry["adjustment_factor_blocked_by"])

    def test_real_notice_lifecycle_stays_under_the_shared_document_class_ceiling(self):
        typed = events.classify_retained_document(self.record, self.payload)
        text = events.extract_text(self.payload, typed["media_type"])
        observation = events.extract_event_observation(typed, text)
        self.assertEqual(events.DOCUMENT_CLASS_CEILING["listing_change_notice"], "executed")
        self.assertEqual(observation["lifecycle_ceiling"], "executed")
        self.assertEqual(observation["lifecycle_state"], "executed")

    def test_real_notice_wrong_ticker_claim_is_refused(self):
        wrong = dict(self.record, ticker="VNM", document_id="wrong-ticker")
        with self.assertRaisesRegex(ValueError, "document_ticker_conflicts_with_document_text"):
            events.classify_retained_document(wrong, self.payload)

    def test_repeat_classification_is_deterministic(self):
        first = events.classify_retained_document(self.record, self.payload)
        second = events.classify_retained_document(self.record, self.payload)
        self.assertEqual(first, second)


class SsiRealVsdcCorporateActionEvidenceTests(unittest.TestCase):
    """The already-retained SSI VSDC notice, validated through the existing (unmodified)
    vsdc classification path -- no new acquisition, no reopening of the deferred SSI
    ex-date acquisition (docs/DECISIONS.md, 2026-08-11): only the record-date facts that
    notice already states are exercised here.
    """

    RETAINED = (ROOT / "operations-review" / "ssi-vsdc-ex-date-notice-acquisition-20260811"
                / "documents" / "SSI" / "2026" / "last_registration_date_notice")
    HTML_NAME = "bd7d4054613ae6f9c5ee1ddc6b787bf706ac6a18f551aff3c9683a85bcc06dad.html"

    def setUp(self):
        self.html = self.RETAINED / self.HTML_NAME
        if not self.html.is_file():
            self.skipTest("retained SSI VSDC notice is not present")
        self.payload = self.html.read_bytes()
        self.record = {
            "document_id": "ssi-vsdc-198728", "ticker": "SSI",
            "document_type": "last_registration_date_notice",
            "source_authority": "Vietnam Securities Depository and Clearing Corporation",
            "source_id": "vsdc", "source_url": "https://vsd.vn/en/ad/198728",
            "content_sha256": document_store.sha256_bytes(self.payload),
            "published_at": "2026-07-29", "observed_at": "2026-08-11T00:00:00Z",
            "media_type": "text/html",
        }

    def _observation(self):
        typed = events.classify_retained_document(self.record, self.payload)
        text = events.extract_text(self.payload, typed["media_type"])
        return events.extract_event_observation(typed, text)

    def test_notice_still_classifies_via_the_unmodified_vsdc_path(self):
        typed = events.classify_retained_document(self.record, self.payload)
        self.assertEqual(typed["document_type"], "last_registration_date_notice")
        self.assertEqual(typed["document_classification"]["basis"],
                         "document_internal_vsd_record_date_notice_cues")

    def test_record_date_and_ex_date_stay_separate_and_ex_date_is_explicit_and_absent(self):
        observation = self._observation()
        self.assertEqual(observation["record_date"], "2026-08-18")
        self.assertIsNone(observation["ex_date"])
        self.assertIn("ex_date_absent", observation["warnings"])
        self.assertIn("never", observation["absent_fields"]["ex_date"])

    def test_planned_bonus_issuance_does_not_become_an_executed_share_count(self):
        observation = self._observation()
        self.assertEqual(observation["event_type"], "bonus_shares")
        self.assertEqual(observation["stock_ratio"], 0.2)
        self.assertNotEqual(observation["lifecycle_state"], "executed")
        self.assertEqual(observation["lifecycle_state"], "record_date_confirmed")
        self.assertIsNone(observation["shares_after"])

    def test_evidence_never_reaches_a_price_adjustment_factor(self):
        built = ledger.build_ledger([self._observation()])
        self.assertEqual(built["entry_count"], 0)
        self.assertEqual(built["qualified_event_count"], 0)
        self.assertEqual(built["adjustment_factor_counts"], {})
        self.assertEqual(built["unlinked_observations"][0]["reason"],
                         "no share-change identity; cannot be linked to an event")

    def test_repeat_run_is_deterministic(self):
        first = self._observation()
        second = self._observation()
        self.assertEqual(first, second)


class IssuerIrRegistryAdmissionTests(unittest.TestCase):
    """config/official_source_registry.json now declares `listing_change_notice` for
    issuer_ir; admission stays host- and type-gated, not opened generally."""

    def test_listing_change_notice_is_now_admitted_for_an_approved_issuer_host(self):
        decision = registry.admit("issuer_ir", "https://www.hoaphat.com.vn/tin-tuc/a.html",
                                  "listing_change_notice")
        self.assertEqual(decision["decision"], registry.ADMITTED)

    def test_listing_change_notice_still_refuses_an_unlisted_host(self):
        decision = registry.admit("issuer_ir", "https://www.some-unapproved-issuer.vn/a.html",
                                  "listing_change_notice")
        self.assertEqual(decision["decision"], registry.REFUSED)
        self.assertEqual(decision["reason"], registry.REASON_HOST_NOT_ALLOWED)

    def test_issuer_ir_still_refuses_an_undeclared_document_type(self):
        decision = registry.admit("issuer_ir", "https://www.hoaphat.com.vn/tin-tuc/a.html",
                                  "quarterly_investor_call_transcript")
        self.assertEqual(decision["decision"], registry.REFUSED)
        self.assertEqual(decision["reason"], registry.REASON_DOCUMENT_TYPE)


if __name__ == "__main__":
    unittest.main()
