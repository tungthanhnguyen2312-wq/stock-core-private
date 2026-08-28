"""Focused A2 regression tests for prospective provider/receipt retention."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from acquisition_landing_checkpoint import load_content_manifest, process_batch
from acquisition_landing_contract import AcquisitionSpec
from dnse_prospective_pit_shadow import build_observation
from kbs_quarterly_financial_retention import metadata_rows
from temporal_retention import (
    capture_raw_receipt,
    capture_with_clock,
    merge_identical_reobservation,
    project_retention_to_a1,
    retention_fitness,
)


class FixedClock:
    def __init__(self, value: datetime):
        self.value = value

    def now(self) -> datetime:
        return self.value


class TemporalRetentionTests(unittest.TestCase):
    def test_receipt_captures_explicit_metadata_without_promoting_http_to_publication(self):
        envelope = capture_with_clock(
            clock=FixedClock(datetime(2026, 8, 29, 7, 30, tzinfo=timezone.utc)),
            data=b'{"value":1}', source_identity="https://provider.invalid/record", provider_or_source="KBS",
            acquisition_method="test", source_published_at=None, provider_reported_date="2026-06-30",
            provider_record_update_at="2026-08-29T14:00:00", http_headers={
                "Date": "Fri, 29 Aug 2026 07:30:00 GMT", "Last-Modified": "Fri, 29 Aug 2026 07:00:00 GMT",
                "ETag": "abc", "Content-Type": "application/json",
            },
        )
        self.assertEqual(envelope["raw_received_at"], "2026-08-29T07:30:00Z")
        self.assertEqual(envelope["http_etag"], "abc")
        self.assertEqual(envelope["publication_authority_tier"], "UNVERIFIED")
        self.assertIsNone(envelope["source_published_at"])
        self.assertIn("HTTP_METADATA_NOT_PUBLICATION_AUTHORITY", envelope["warnings"])

    def test_identical_reobservation_preserves_earliest_receipt(self):
        first = capture_raw_receipt(data=b"same", raw_received_at="2026-08-01T01:00:00Z", source_identity="s",
                                    provider_or_source="KBS", acquisition_method="test")
        later = capture_raw_receipt(data=b"same", raw_received_at="2026-08-02T01:00:00Z", source_identity="s",
                                    provider_or_source="KBS", acquisition_method="test")
        merged = merge_identical_reobservation(first, later)
        self.assertEqual(merged["first_observed_at"], "2026-08-01T01:00:00Z")
        self.assertEqual(merged["last_observed_at"], "2026-08-02T01:00:00Z")
        self.assertEqual(merged["observation_count"], 2)

    def test_legacy_identity_is_not_backfilled_with_a_new_receipt(self):
        envelope = capture_raw_receipt(data=b"legacy", raw_received_at="2026-08-29T01:00:00Z", source_identity="s",
                                       provider_or_source="KBS", acquisition_method="test", legacy_first_observed_unknown=True)
        self.assertIsNone(envelope["first_observed_at"])
        self.assertEqual(envelope["first_observed_status"], "LEGACY_UNKNOWN")
        self.assertEqual(envelope["last_observed_at"], "2026-08-29T01:00:00Z")

    def test_provider_metadata_projects_to_a1_without_publication_authority(self):
        envelope = capture_raw_receipt(data=b"provider", raw_received_at="2026-08-29T07:30:00Z", source_identity="kbs",
                                       provider_or_source="KBS", acquisition_method="test",
                                       provider_reported_date="2026-06-30", provider_record_update_at="2026-08-29T14:00:00")
        projected = project_retention_to_a1(envelope)
        self.assertEqual(projected["publication_time"]["publication_authority_tier"], "UNVERIFIED")
        self.assertEqual(projected["provider_temporal_metadata"]["provider_reported_date"], "2026-06-30")
        self.assertIn("KBS_LASTUPDATE_TIMEZONE_NAIVE_OR_UNKNOWN", projected["provider_temporal_metadata"]["warnings"])
        self.assertEqual(projected["retention_fitness"]["temporal_fitness"], "FIRST_OBSERVED_FORWARD_ONLY")

    def test_qualified_date_only_publication_is_conservative_and_not_execution_authority(self):
        envelope = capture_raw_receipt(data=b"official", raw_received_at="2026-08-29T07:30:00Z", source_identity="issuer",
                                       provider_or_source="issuer", acquisition_method="test", source_published_at="2026-08-28",
                                       publication_authority_tier="OFFICIAL_ISSUER_IR_OR_EXCHANGE")
        fitness = retention_fitness(envelope)
        self.assertEqual(fitness["temporal_fitness"], "QUALIFIED_SOURCE_PUBLICATION_DATE_ONLY")
        self.assertEqual(fitness["historical_price_pit"], "BLOCKED")

    def test_kbs_legacy_sidecar_keeps_receipt_unknown_and_provider_dates_separate(self):
        request = {"ticker": "AAA", "endpoint_contract": "KBS_FINANCE_INFO_KQKD_QUARTER_PAGED_V1",
                   "params": {"page": 1, "pageSize": 8, "type": "KQKD", "unit": 1000, "termtype": 2, "languageid": 1},
                   "url": "https://kbs.invalid/AAA", "retrieved_at": None}
        raw = {"Unit": [{"UnitedCode": "1", "UnitedName": "Hợp nhất"}], "Head": [{
            "YearPeriod": "2026", "TermName": "Quý 2", "United": "1", "ReportDate": "2026-06-30",
            "LastUpdate": "2026-08-29T14:00:00", "Currency": "VND",
        }]}
        row = metadata_rows(request, raw, raw_hash="a" * 64)[0]
        self.assertEqual(row["temporal_retention"]["first_observed_status"], "LEGACY_UNKNOWN")
        self.assertEqual(row["a1_temporal_projection"]["publication_time"]["publication_authority_tier"], "UNVERIFIED")
        self.assertEqual(row["a1_temporal_projection"]["provider_temporal_metadata"]["provider_reported_date"], "2026-06-30")

    def test_dnse_observation_has_receipt_and_event_but_stays_non_authoritative(self):
        observation = build_observation(
            payload={"T": "bc", "symbol": "AAA", "resolution": "1m", "time": "2026-08-29T07:29:00Z",
                     "lastUpdated": "2026-08-29T07:30:00Z", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 3},
            channel="ohlc_closed.AAA.1m", message_type="bc", receipt_at=datetime(2026, 8, 29, 7, 30, 1, tzinfo=timezone.utc),
            collector_execution_id="test",
        )
        self.assertEqual(observation["temporal_retention"]["provider_event_at"], "2026-08-29T07:30:00Z")
        self.assertEqual(observation["a1_temporal_projection"]["authority_boundaries"]["historical_price_pit"], "BLOCKED")


class LandingTemporalRetentionTests(unittest.TestCase):
    def test_replay_preserves_first_observed_and_changed_bytes_are_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "landing"
            spec = AcquisitionSpec(domain="official", source_locator="https://issuer.invalid/a.pdf", source_authority_class="issuer_ir")
            allowed = root
            first = process_batch(root, [(spec, {"data": b"%PDF-1.4\nfirst\n%%EOF"})], run_id="one", domain="official",
                                  allowed_root=allowed, observed_at_fn=lambda: "2026-08-01T01:00:00Z")
            second = process_batch(root, [(spec, {"data": b"%PDF-1.4\nfirst\n%%EOF"})], run_id="two", domain="official",
                                   allowed_root=allowed, observed_at_fn=lambda: "2026-08-02T01:00:00Z")
            third = process_batch(root, [(spec, {"data": b"%PDF-1.4\nchanged\n%%EOF"})], run_id="three", domain="official",
                                  allowed_root=allowed, observed_at_fn=lambda: "2026-08-03T01:00:00Z")
            manifest = load_content_manifest(root)
            self.assertEqual(first.succeeded, 1)
            self.assertEqual(second.records[0]["temporal_retention"]["first_observed_at"], "2026-08-01T01:00:00Z")
            self.assertEqual(len(manifest["blobs"]), 2)
            self.assertNotEqual(third.records[0]["sha256"], first.records[0]["sha256"])
            self.assertEqual(third.records[0]["supersedes_sha256"], first.records[0]["sha256"])


if __name__ == "__main__":
    unittest.main()
