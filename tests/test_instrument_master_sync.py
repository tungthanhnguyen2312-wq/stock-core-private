"""Targeted contracts for VCI source-scoped instrument-master ingestion."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import instrument_master_sync as sync  # noqa: E402


FETCHED_AT = "2026-07-22T00:00:00+00:00"
PAYLOAD = {"records": [
    {"symbol": "VCB", "exchange": "HOSE", "type": "STOCK", "provider_note": None},
    {"symbol": "VNX", "exchange": "HNX", "type": "CS"},
]}


class InstrumentMasterSyncTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        sync.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_successful_ingestion_retains_only_qualified_canonical_fields(self):
        result = sync.persist_current_snapshot(self.conn, PAYLOAD, FETCHED_AT)
        rows = self.conn.execute(
            "SELECT symbol, source_name, provider_identity, exchange, instrument_type, provenance_json "
            "FROM instrument_master_records ORDER BY symbol"
        ).fetchall()
        self.assertTrue(result["inserted"])
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(rows[0][:5], ("VCB", "VCI", "vci:symbol:vcb", "HOSE", "STOCK"))
        provenance = json.loads(rows[0][5])
        self.assertEqual(provenance["unavailable_fields"], ["company_or_organ_identity", "listing_status"])
        self.assertNotIn("listing_status", provenance)

    def test_same_payload_is_idempotent_even_with_different_fetch_time(self):
        first = sync.persist_current_snapshot(self.conn, PAYLOAD, FETCHED_AT)
        repeat = sync.persist_current_snapshot(self.conn, PAYLOAD, "2026-07-23T00:00:00+00:00")
        self.assertTrue(first["inserted"])
        self.assertFalse(repeat["inserted"])
        self.assertEqual(first["snapshot_id"], repeat["snapshot_id"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM instrument_master_snapshots").fetchone(), (1,))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM instrument_master_records").fetchone(), (2,))

    def test_source_isolation_keeps_unqualified_identity_and_status_out_of_canonical_columns(self):
        payload = {"records": [{
            "symbol": "VCB", "exchange": "HOSE", "type": "STOCK",
            "tax_id": "0100112437", "organ_code": "VCB", "listing_status": "listed",
        }]}
        sync.persist_current_snapshot(self.conn, payload, FETCHED_AT)
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(instrument_master_records)")}
        self.assertFalse({"tax_id", "organ_code", "listing_status"} & columns)
        raw, provenance = self.conn.execute(
            "SELECT raw_record_json, provenance_json FROM instrument_master_records"
        ).fetchone()
        self.assertEqual(json.loads(raw)["tax_id"], "0100112437")
        self.assertIn("listing_status", json.loads(provenance)["unavailable_fields"])

    def test_duplicate_identity_rejected_before_any_write(self):
        payload = {"records": [
            {"symbol": "VCB", "exchange": "HOSE", "type": "STOCK"},
            {"symbol": " vcb ", "exchange": "HNX", "type": "CS"},
        ]}
        with self.assertRaisesRegex(ValueError, "duplicate VCI instrument identity: vci:symbol:vcb"):
            sync.persist_current_snapshot(self.conn, payload, FETCHED_AT)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM instrument_master_snapshots").fetchone(), (0,))

    def test_empty_error_and_malformed_payloads_are_rejected_without_writes(self):
        cases = [
            {},
            {"error": "upstream_failed"},
            {"records": []},
            {"records": [{"symbol": "VCB", "exchange": "HOSE"}]},
            {"records": ["not-a-record"]},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    sync.persist_current_snapshot(self.conn, payload, FETCHED_AT)
                self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM instrument_master_snapshots").fetchone(), (0,))

    def test_source_adapter_requires_exact_qualified_columns(self):
        with self.assertRaisesRegex(ValueError, r"missing required columns: \['type'\]"):
            sync.payload_from_symbols_by_exchange_frame(pd.DataFrame([{"symbol": "VCB", "exchange": "HOSE"}]))
        payload = sync.payload_from_symbols_by_exchange_frame(pd.DataFrame(PAYLOAD["records"]))
        self.assertEqual(payload["records"][0]["symbol"], "VCB")

    def test_additive_migration_is_idempotent_and_preserves_existing_tables(self):
        legacy = sqlite3.connect(":memory:")
        legacy.execute("CREATE TABLE metadata(ticker TEXT PRIMARY KEY, exchange TEXT)")
        legacy.execute("INSERT INTO metadata VALUES('VCB', 'HOSE')")
        sync.init_db(legacy)
        sync.init_db(legacy)
        self.assertEqual(legacy.execute("SELECT * FROM metadata").fetchone(), ("VCB", "HOSE"))
        columns = {row[1] for row in legacy.execute("PRAGMA table_info(instrument_master_snapshots)")}
        self.assertTrue({"snapshot_id", "raw_hash", "raw_payload_json", "is_complete"}.issubset(columns))
        legacy.close()


if __name__ == "__main__":
    unittest.main()
