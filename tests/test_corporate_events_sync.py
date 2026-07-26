"""Fixture contracts for VCI-only corporate-event forward observation."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import corporate_events_sync as sync  # noqa: E402


FETCHED_AT = "2026-07-26T00:00:00+00:00"
PAYLOAD = {
    "id": "event-001", "ticker": "VCB", "event_code": "DIV", "category": "DIVIDEND",
    "event_name_vi": "Trả cổ tức", "event_name_en": "Cash dividend",
    "event_title_vi": "VCB - 450 VND", "event_title_en": "VCB - 450 VND",
    "public_date": "2026-07-14", "record_date": "2026-07-24", "exright_date": "2026-07-23",
    "payout_date": "2026-08-27", "exercise_ratio": None, "value_per_share": 450.0,
}


class CorporateEventsSyncTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        sync.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def ingest(self, payloads, **kwargs):
        return sync.ingest_events(self.conn, "VCB", "VCI", payloads, FETCHED_AT, **kwargs)

    def test_first_ingestion_records_canonical_event_and_observation(self):
        result = self.ingest([PAYLOAD])
        self.assertEqual(result["inserted_observations"], 1)
        row = self.conn.execute("SELECT provider,provider_event_id,ticker,event_code,value_per_share,coverage_status FROM corporate_event_records").fetchone()
        self.assertEqual(row, ("VCI", "event-001", "VCB", "DIV", 450.0, sync.COVERAGE_STATUS))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM corporate_event_observations").fetchone(), (1,))

    def test_identical_second_ingestion_is_idempotent(self):
        self.ingest([PAYLOAD])
        repeat = sync.ingest_events(self.conn, "VCB", "VCI", [PAYLOAD], "2026-07-27T00:00:00+00:00")
        self.assertEqual(repeat["inserted_observations"], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM corporate_event_records").fetchone(), (1,))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM corporate_event_observations").fetchone(), (1,))

    def test_changed_payload_preserves_both_observations_and_marks_revision_unknown(self):
        self.ingest([PAYLOAD])
        changed = {**PAYLOAD, "value_per_share": 500.0}
        result = sync.ingest_events(self.conn, "VCB", "VCI", [changed], "2026-07-27T00:00:00+00:00")
        self.assertEqual((result["inserted_observations"], result["revisions"]), (1, 1))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM corporate_event_observations").fetchone(), (2,))
        self.assertEqual(self.conn.execute("SELECT revision_status FROM corporate_event_records").fetchone(), ("revised_or_unknown",))

    def test_missing_malformed_empty_and_duplicate_payloads_fail_closed(self):
        cases = ([{"ticker": "VCB"}], ["bad"], [PAYLOAD, PAYLOAD])
        for payloads in cases:
            with self.subTest(payloads=payloads):
                with self.assertRaises(sync.CorporateEventsContractError):
                    self.ingest(payloads)
                self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM corporate_event_records").fetchone(), (0,))
                self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM corporate_event_observations").fetchone(), (0,))

    def test_null_remains_null_and_zero_remains_zero(self):
        payload = {**PAYLOAD, "id": "event-null-zero", "record_date": None, "exercise_ratio": 0, "value_per_share": None}
        self.ingest([payload])
        row = self.conn.execute("SELECT record_date,exercise_ratio,value_per_share FROM corporate_event_records").fetchone()
        self.assertEqual(row, (None, 0.0, None))
        raw = json.loads(self.conn.execute("SELECT raw_payload_json FROM corporate_event_observations").fetchone()[0])
        self.assertIsNone(raw["record_date"])
        self.assertEqual(raw["exercise_ratio"], 0)

    def test_provider_scoped_identity_ticker_mismatch_and_unsupported_provider_reject(self):
        self.ingest([PAYLOAD])
        with self.assertRaisesRegex(sync.CorporateEventsContractError, "ticker mismatch"):
            sync.ingest_events(self.conn, "HPG", "VCI", [PAYLOAD], FETCHED_AT)
        with self.assertRaisesRegex(sync.CorporateEventsContractError, "unsupported"):
            sync.ingest_events(self.conn, "VCB", "KBS", [PAYLOAD], FETCHED_AT)
        conflict = {**PAYLOAD, "ticker": "HPG"}
        with self.assertRaisesRegex(sync.CorporateEventsContractError, "existing ticker"):
            sync.ingest_events(self.conn, "HPG", "VCI", [conflict], FETCHED_AT)

    def test_coverage_is_never_complete_and_empty_is_explicit(self):
        result = self.ingest([])
        self.assertEqual((result["status"], result["coverage_status"]), ("source_empty", sync.COVERAGE_STATUS))
        run = self.conn.execute("SELECT coverage_status,response_count,accepted_count,status FROM corporate_event_ingestion_runs").fetchone()
        self.assertEqual(run, (sync.COVERAGE_STATUS, 0, 0, "source_empty"))

    def test_additive_migration_and_foreign_key_integrity(self):
        legacy = sqlite3.connect(":memory:")
        legacy.execute("CREATE TABLE shareholders(ticker TEXT PRIMARY KEY, shareholder_name TEXT)")
        legacy.execute("INSERT INTO shareholders VALUES('AAA','Legacy Holder')")
        sync.init_db(legacy)
        sync.init_db(legacy)
        self.assertEqual(legacy.execute("SELECT shareholder_name FROM shareholders").fetchone(), ("Legacy Holder",))
        columns = {row[1] for row in legacy.execute("PRAGMA table_info(corporate_event_records)")}
        self.assertTrue({"provider", "provider_event_id", "coverage_status"}.issubset(columns))
        self.assertEqual(legacy.execute("PRAGMA foreign_key_check").fetchall(), [])
        legacy.close()

    def test_no_orphan_records_or_observations(self):
        self.ingest([PAYLOAD])
        self.assertEqual(self.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.conn.execute("""SELECT COUNT(*) FROM corporate_event_observations o
            LEFT JOIN corporate_event_records r ON r.record_id=o.record_id WHERE r.record_id IS NULL""").fetchone(), (0,))


if __name__ == "__main__":
    unittest.main()
