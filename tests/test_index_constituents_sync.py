"""Targeted contracts for source-scoped VCI current constituent snapshots."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import index_constituents_sync as sync  # noqa: E402


FETCHED_AT = "2026-07-22T00:00:00+00:00"
VN30 = {"members": ["ACB", "BID", "FPT"]}
VN100 = {"members": ["ACB", "BID", "FPT", "HPG"]}
HNX30 = {"members": ["BVS", "CEO", "SHS"]}


class IndexConstituentsSyncTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        sync.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_successful_vn30_vn100_hnx30_style_ingestion(self):
        for group, payload in (("VN30", VN30), ("VN100", VN100), ("HNX30", HNX30)):
            with self.subTest(group=group):
                result = sync.persist_current_snapshot(self.conn, group, payload, FETCHED_AT)
                self.assertTrue(result["inserted"])
                self.assertEqual(result["record_count"], len(payload["members"]))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM index_constituent_snapshots").fetchone(), (3,))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM index_constituent_records").fetchone(), (10,))

    def test_case_normalized_requested_scope_and_effective_parameter_are_retained(self):
        result = sync.persist_current_snapshot(self.conn, "vn30", VN30, FETCHED_AT)
        row = self.conn.execute(
            "SELECT requested_group, effective_provider_group FROM index_constituent_snapshots"
        ).fetchone()
        self.assertEqual(row, ("VN30", "VN30"))
        self.assertEqual(result["requested_group"], "VN30")
        self.assertEqual(sync.resolve_group("vni"), {
            "requested_group": "VNI", "effective_provider_group": "VNINDEX",
        })

    def test_aliases_are_not_merged_even_when_effective_provider_group_matches(self):
        first = sync.persist_current_snapshot(self.conn, "VNI", VN30, FETCHED_AT)
        second = sync.persist_current_snapshot(self.conn, "VNINDEX", VN30, FETCHED_AT)
        self.assertNotEqual(first["snapshot_id"], second["snapshot_id"])
        groups = self.conn.execute(
            "SELECT requested_group, effective_provider_group FROM index_constituent_snapshots ORDER BY requested_group"
        ).fetchall()
        self.assertEqual(groups, [("VNI", "VNINDEX"), ("VNINDEX", "VNINDEX")])

    def test_same_scoped_payload_is_idempotent_and_changed_membership_versions_snapshot(self):
        first = sync.persist_current_snapshot(self.conn, "VN30", VN30, FETCHED_AT)
        repeat = sync.persist_current_snapshot(self.conn, "VN30", VN30, "2026-07-23T00:00:00+00:00")
        changed = sync.persist_current_snapshot(self.conn, "VN30", {"members": ["ACB", "BID", "HPG"]}, FETCHED_AT)
        self.assertTrue(first["inserted"])
        self.assertFalse(repeat["inserted"])
        self.assertEqual(first["snapshot_id"], repeat["snapshot_id"])
        self.assertNotEqual(first["snapshot_id"], changed["snapshot_id"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM index_constituent_snapshots").fetchone(), (2,))

    def test_group_scope_and_vci_source_are_isolated(self):
        sync.persist_current_snapshot(self.conn, "VN30", VN30, FETCHED_AT)
        sync.persist_current_snapshot(self.conn, "VN100", VN30, FETCHED_AT)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM index_constituent_snapshots").fetchone(), (2,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO index_constituent_snapshots(snapshot_id,schema_version,source_name,requested_group,effective_provider_group,source_reference,fetched_at,raw_hash,raw_payload_json,provenance_json,record_count,status,is_complete) VALUES('bad',1,'KBS','VN30','VN30','x','t','h','{}','{}',1,'complete_response',1)")

    def test_duplicate_null_blank_empty_malformed_and_invalid_inputs_fail_before_write(self):
        cases = [
            ("VN30", {"members": ["ACB", " acb "]}),
            ("VN30", {"members": [None]}),
            ("VN30", {"members": ["  "]}),
            ("VN30", {"members": []}),
            ("VN30", {"members": "ACB"}),
            ("VN30", {}),
            ("NOT_A_VALID_INDEX_GROUP", VN30),
        ]
        for group, payload in cases:
            with self.subTest(group=group, payload=payload):
                with self.assertRaises(ValueError):
                    sync.persist_current_snapshot(self.conn, group, payload, FETCHED_AT)
                self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM index_constituent_snapshots").fetchone(), (0,))

    def test_malformed_adapter_output_is_rejected_and_invalid_group_does_not_import_provider(self):
        with self.assertRaisesRegex(ValueError, "malformed"):
            sync.payload_from_symbols_series(["ACB"])
        with self.assertRaisesRegex(ValueError, "invalid VCI index group"):
            sync.fetch_current_payload("INVALID")
        frame_series = pd.Series(["ACB", "BID"], name="symbol")
        self.assertEqual(sync.payload_from_symbols_series(frame_series), {"members": ["ACB", "BID"]})

    def test_sync_group_provider_error_fails_closed_before_any_write(self):
        with mock.patch.object(sync, "fetch_current_payload", side_effect=RuntimeError("upstream failed")):
            with self.assertRaisesRegex(RuntimeError, "upstream failed"):
                sync.sync_group(self.conn, "VN30", fetched_at=FETCHED_AT)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM index_constituent_snapshots").fetchone(), (0,))

    def test_no_orphans_unique_member_identity_and_raw_provenance(self):
        sync.persist_current_snapshot(self.conn, "VN30", VN30, FETCHED_AT)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM index_constituent_records r LEFT JOIN index_constituent_snapshots s ON s.snapshot_id=r.snapshot_id WHERE s.snapshot_id IS NULL"
        ).fetchone(), (0,))
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM (SELECT snapshot_id, source_member_identity, COUNT(*) n FROM index_constituent_records GROUP BY snapshot_id, source_member_identity HAVING n > 1)"
        ).fetchone(), (0,))
        snapshot_provenance = json.loads(self.conn.execute(
            "SELECT provenance_json FROM index_constituent_snapshots"
        ).fetchone()[0])
        record_provenance = json.loads(self.conn.execute(
            "SELECT provenance_json FROM index_constituent_records WHERE symbol='ACB'"
        ).fetchone()[0])
        self.assertEqual(snapshot_provenance["fetch_timestamp_semantics"], "collection_provenance_not_effective_or_as_of_date")
        self.assertNotIn("effective_date", snapshot_provenance)
        self.assertIn("history", record_provenance["unavailable_fields"])
        self.assertEqual(json.loads(self.conn.execute(
            "SELECT raw_member_json FROM index_constituent_records WHERE symbol='ACB'"
        ).fetchone()[0]), "ACB")

    def test_additive_migration_is_idempotent_and_preserves_existing_tables(self):
        legacy = sqlite3.connect(":memory:")
        legacy.execute("CREATE TABLE metadata(ticker TEXT PRIMARY KEY, exchange TEXT)")
        legacy.execute("INSERT INTO metadata VALUES('ACB', 'HOSE')")
        sync.init_db(legacy)
        sync.init_db(legacy)
        self.assertEqual(legacy.execute("SELECT * FROM metadata").fetchone(), ("ACB", "HOSE"))
        columns = {row[1] for row in legacy.execute("PRAGMA table_info(index_constituent_snapshots)")}
        self.assertTrue({"requested_group", "effective_provider_group", "raw_hash", "is_complete"}.issubset(columns))
        legacy.close()


if __name__ == "__main__":
    unittest.main()
