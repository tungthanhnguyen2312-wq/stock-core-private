"""KBS-only current ownership-structure snapshot contracts."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ownership_structure_sync as sync  # noqa: E402


FETCHED_AT = "2026-07-22T00:00:00+00:00"
PAYLOAD = {"records": [
    {"owner_type": "State", "ownership_percentage": 74.8, "shares_owned": 6250338600, "update_date": "2025-12-31"},
    {"owner_type": "Foreign", "ownership_percentage": 25.21, "shares_owned": 2100000000, "update_date": "2025-12-31"},
]}


class OwnershipStructureSyncTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        sync.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_normalization_keeps_raw_kbs_groups_percentage_points_and_rounding(self):
        records = sync.normalize_current_payload("VCB", PAYLOAD, FETCHED_AT)
        self.assertEqual(records[0]["owner_type"], "State")
        self.assertEqual(records[1]["ownership_percentage"], 25.21)
        self.assertAlmostEqual(sum(item["ownership_percentage"] for item in records), 100.01, places=8)
        self.assertEqual(records[0]["provenance"]["ownership_unit"], "percentage_points")
        self.assertEqual(records[0]["provenance"]["update_date_semantics"], "current_response_provenance_not_historical_api")

    def test_same_payload_is_idempotent_and_changed_payload_creates_snapshot(self):
        first = sync.persist_current_snapshot(self.conn, "VCB", PAYLOAD, FETCHED_AT)
        repeat = sync.persist_current_snapshot(self.conn, "VCB", PAYLOAD, "2026-07-23T00:00:00+00:00")
        changed_payload = {"records": [{**PAYLOAD["records"][0], "ownership_percentage": 74.79}, PAYLOAD["records"][1]]}
        changed = sync.persist_current_snapshot(self.conn, "VCB", changed_payload, "2026-07-24T00:00:00+00:00")
        self.assertTrue(first["inserted"])
        self.assertFalse(repeat["inserted"])
        self.assertEqual(first["snapshot_id"], repeat["snapshot_id"])
        self.assertNotEqual(first["snapshot_id"], changed["snapshot_id"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM ownership_structure_snapshots").fetchone()[0], 2)

    def test_null_values_are_retained_without_zero_filling(self):
        payload = {"records": [{"owner_type": "Other", "ownership_percentage": None, "shares_owned": None, "update_date": None}]}
        sync.persist_current_snapshot(self.conn, "AAA", payload, FETCHED_AT)
        row = self.conn.execute("SELECT ownership_percentage, shares_owned, update_date, raw_record_json FROM ownership_structure_records").fetchone()
        self.assertEqual(row[:3], (None, None, None))
        self.assertIsNone(json.loads(row[3])["ownership_percentage"])

    def test_empty_error_malformed_and_duplicate_identities_are_rejected_before_write(self):
        cases = [
            {},
            {"records": []},
            {"records": "upstream_error"},
            {"records": [{"owner_type": "One"}, {"owner_type": " one "}]},
            {"records": [{"owner_type": None}]},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    sync.persist_current_snapshot(self.conn, "AAA", payload, FETCHED_AT)
                self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM ownership_structure_snapshots").fetchone()[0], 0)

    def test_additive_migration_is_idempotent_and_preserves_existing_tables(self):
        legacy = sqlite3.connect(":memory:")
        legacy.execute("CREATE TABLE shareholders(ticker TEXT PRIMARY KEY, shareholder_name TEXT)")
        legacy.execute("INSERT INTO shareholders VALUES('AAA', 'Legacy Holder')")
        sync.init_db(legacy)
        sync.init_db(legacy)
        self.assertEqual(legacy.execute("SELECT shareholder_name FROM shareholders").fetchone(), ("Legacy Holder",))
        columns = {row[1] for row in legacy.execute("PRAGMA table_info(ownership_structure_snapshots)")}
        self.assertTrue({"snapshot_id", "schema_version", "raw_hash", "raw_payload_json", "is_complete"}.issubset(columns))
        legacy.close()


if __name__ == "__main__":
    unittest.main()
