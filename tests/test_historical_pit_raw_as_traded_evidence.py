import unittest

from historical_pit_raw_as_traded_evidence import (build_artifact, event_from_observation,
                                                     price_source_inventory, source_document)


def record():
    return {"document_id": "d" * 64, "ticker": "DTP", "canonical_url": "https://vsd.vn/en/ad/199587",
            "observed_at": "2026-08-24T01:00:00Z", "published_at": "2026-08-22T10:01:48+00:00",
            "sha256": "a" * 64, "content_type": "text/html", "acquisition_status": "retained", "source_id": "vsdc"}


def observation(**more):
    return {"ticker": "DTP", "event_type": "cash_dividend", "lifecycle_state": "record_date_confirmed",
            "announcement_date": "2026-08-22T10:01:48+00:00", "record_date": "2026-09-04", "ex_date": None,
            "payment_or_execution_date": "2026-09-25", "cash_amount_per_share": 800.0,
            "stock_ratio": None, "rights_ratio": None, "subscription_price": None,
            "absent_fields": {"ex_date": "no explicit official ex-date"}, "warnings": ["ex_date_absent"]} | more


class HistoricalPitEvidenceTests(unittest.TestCase):
    def test_document_provenance_is_complete(self):
        document = source_document(record())
        self.assertEqual(document["raw_payload_sha256"], "a" * 64)
        self.assertEqual(document["status"], "retained")

    def test_missing_ex_date_never_uses_record_date(self):
        event = event_from_observation(record(), observation())
        self.assertIsNone(event["ex_date"])
        self.assertEqual(event["ex_date_status"], "MISSING_EXPLICIT_EX_DATE")

    def test_explicit_ex_date_is_preserved_only_when_present(self):
        event = event_from_observation(record(), observation(ex_date="2026-09-03"))
        self.assertEqual(event["ex_date_status"], "EXPLICIT_OFFICIAL")
        self.assertEqual(event["ex_date"], "2026-09-03")

    def test_ticker_conflict_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "ticker"):
            event_from_observation(record(), observation(ticker="HPG"))

    def test_artifact_blocks_authority_without_explicit_date(self):
        artifact = build_artifact([event_from_observation(record(), observation())])
        self.assertEqual(artifact["coverage"]["ex_date_qualified_events"], 0)
        self.assertEqual(artifact["coverage"]["insufficient_windows"], 1)
        self.assertEqual(artifact["raw_as_traded_authority_result"], "NOT_PROMOTED")
        self.assertFalse(artifact["shadow_adjustment_ledger"][0]["mutates_ohlc"])

    def test_artifact_is_deterministic(self):
        event = event_from_observation(record(), observation())
        self.assertEqual(build_artifact([event])["artifact_identity"], build_artifact([event])["artifact_identity"])

    def test_price_inventory_uses_only_known_stream_labels(self):
        self.assertEqual({row["stream"] for row in price_source_inventory()},
                         {"RAW_AS_TRADED", "RETROSPECTIVELY_ADJUSTED", "ADJUSTED_ANALYTICAL", "UNKNOWN"})

    def test_price_inventory_has_no_provider_wide_raw_claim(self):
        self.assertEqual(next(row for row in price_source_inventory() if row["source_id"] == "DNSE_OHLC")["authority"],
                         "not_raw_not_point_in_time")


if __name__ == "__main__":
    unittest.main()
