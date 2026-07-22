"""Read-only current-snapshot comparison contracts for index membership history."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import index_constituents_sync as snapshots  # noqa: E402
import index_membership_history as history  # noqa: E402


T1 = "2026-07-22T00:00:00+00:00"
T2 = "2026-07-23T00:00:00+00:00"


class IndexMembershipHistoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        snapshots.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def persist(self, group="VN30", members=None, fetched_at=T1):
        return snapshots.persist_current_snapshot(
            self.conn, group, {"members": members or ["ACB", "BID", "FPT"]}, fetched_at
        )

    def test_first_snapshot_has_no_previous_snapshot(self):
        current = self.persist()
        result = history.latest_group_change(self.conn, "vn30")
        self.assertEqual(result["status"], "no_previous_snapshot")
        self.assertIsNone(result["previous_snapshot_id"])
        self.assertEqual(result["current_snapshot_id"], current["snapshot_id"])
        self.assertEqual(result["current_observed_at"], T1)

    def test_distinct_payload_order_with_same_members_is_unchanged(self):
        first = self.persist(members=["ACB", "BID", "FPT"], fetched_at=T1)
        second = self.persist(members=["FPT", "ACB", "BID"], fetched_at=T2)
        result = history.compare_snapshots(self.conn, first["snapshot_id"], second["snapshot_id"])
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["added_symbols"], [])
        self.assertEqual(result["removed_symbols"], [])
        self.assertEqual(result["unchanged_count"], 3)

    def test_added_removed_and_deterministic_order(self):
        first = self.persist(members=["ZED", "BID", "ACB"], fetched_at=T1)
        second = self.persist(members=["FPT", "ACB", "AAA"], fetched_at=T2)
        result = history.latest_group_change(self.conn, "VN30")
        self.assertEqual(result["status"], "changed")
        self.assertEqual(result["previous_snapshot_id"], first["snapshot_id"])
        self.assertEqual(result["current_snapshot_id"], second["snapshot_id"])
        self.assertEqual(result["added_symbols"], ["AAA", "FPT"])
        self.assertEqual(result["removed_symbols"], ["BID", "ZED"])
        self.assertEqual(result["unchanged_count"], 1)

    def test_case_normalized_group_uses_exact_requested_scope(self):
        first = self.persist(group="vn30", members=["ACB"], fetched_at=T1)
        second = self.persist(group="VN30", members=["BID"], fetched_at=T2)
        result = history.latest_group_change(self.conn, "vN30")
        self.assertEqual(result["status"], "changed")
        self.assertEqual((result["previous_snapshot_id"], result["current_snapshot_id"]),
                         (first["snapshot_id"], second["snapshot_id"]))

    def test_alias_scopes_are_not_merged(self):
        self.persist(group="VNI", members=["ACB"], fetched_at=T1)
        self.persist(group="VNINDEX", members=["BID"], fetched_at=T2)
        vni = history.latest_group_change(self.conn, "VNI")
        vnindex = history.latest_group_change(self.conn, "VNINDEX")
        self.assertEqual(vni["status"], "no_previous_snapshot")
        self.assertEqual(vnindex["status"], "no_previous_snapshot")
        self.assertNotEqual(vni["current_snapshot_id"], vnindex["current_snapshot_id"])

    def test_source_effective_group_and_reference_mismatches_are_incomparable(self):
        first = self.persist(fetched_at=T1)
        self.conn.execute("PRAGMA ignore_check_constraints = ON")
        try:
            cases = [
                ("different-source", "KBS", "VN30", snapshots.SOURCE_REFERENCE),
                ("different-effective-group", "VCI", "OTHER", snapshots.SOURCE_REFERENCE),
                ("different-reference", "VCI", "VN30", "other-reference"),
            ]
            for snapshot_id, source_name, effective_group, source_reference in cases:
                self.conn.execute(
                    """INSERT INTO index_constituent_snapshots
                    (snapshot_id,schema_version,source_name,requested_group,effective_provider_group,source_reference,
                     fetched_at,raw_hash,raw_payload_json,provenance_json,record_count,status,is_complete)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (snapshot_id, 1, source_name, "VN30", effective_group, source_reference, T2,
                     f"{snapshot_id}-hash", "{}", "{}", 1, "complete_response", 1),
                )
        finally:
            self.conn.execute("PRAGMA ignore_check_constraints = OFF")
        for snapshot_id, *_ in cases:
            with self.subTest(snapshot_id=snapshot_id):
                result = history.compare_snapshots(self.conn, first["snapshot_id"], snapshot_id)
                self.assertEqual(result["status"], "incomparable_scope")

    def test_missing_or_malformed_snapshot_fails_closed(self):
        valid = self.persist()
        self.assertEqual(history.compare_snapshots(self.conn, valid["snapshot_id"], "missing")["status"], "invalid_snapshot")
        malformed_id = "malformed"
        self.conn.execute(
            """INSERT INTO index_constituent_snapshots
            (snapshot_id,schema_version,source_name,requested_group,effective_provider_group,source_reference,
             fetched_at,raw_hash,raw_payload_json,provenance_json,record_count,status,is_complete)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (malformed_id, 1, "VCI", "VN30", "VN30", snapshots.SOURCE_REFERENCE, T2, "malformed-hash", "{}",
             "{}", 2, "complete_response", 1),
        )
        self.assertEqual(history.compare_snapshots(self.conn, valid["snapshot_id"], malformed_id)["status"], "invalid_snapshot")

    def test_no_write_or_schema_change_during_comparison(self):
        first = self.persist(fetched_at=T1)
        second = self.persist(members=["ACB", "HPG"], fetched_at=T2)
        before = {
            table: self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("index_constituent_snapshots", "index_constituent_records")
        }
        history.compare_snapshots(self.conn, first["snapshot_id"], second["snapshot_id"])
        history.latest_group_change(self.conn, "VN30")
        after = {
            table: self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("index_constituent_snapshots", "index_constituent_records")
        }
        self.assertEqual(after, before)
        self.assertFalse(any(row[1].startswith("index_membership_history") for row in self.conn.execute("PRAGMA table_info(index_constituent_snapshots)")))


if __name__ == "__main__":
    unittest.main()
