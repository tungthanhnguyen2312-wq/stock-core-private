"""Contracts for source-scoped, forward-only company relationship snapshots."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import company_subsidiaries_sync as sync  # noqa: E402


FETCHED_AT = "2026-07-22T00:00:00+00:00"


VCI_PAYLOAD = {
    "subsidiaries": [{"organ_name": "VCI Sub", "ownership_percent": 1.0, "sub_organ_code": "VCI-001"}],
    "affiliates": [{"organ_name": "VCI Affiliate", "ownership_percent": 0.2622, "sub_organ_code": "VCI-002"}],
}
KBS_PAYLOAD = {
    "records": [{
        "update_date": "2025-12-31", "name": "KBS Company", "charter_capital": -1,
        "ownership_percent": 52.0, "currency": "", "type": "công ty con",
    }],
}


class CompanySubsidiariesSyncTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        sync.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_normalization_preserves_provider_specific_relationship_semantics(self):
        vci = sync.normalize_current_payload("VCB", "VCI", VCI_PAYLOAD, FETCHED_AT)
        kbs = sync.normalize_current_payload("VCB", "KBS", KBS_PAYLOAD, FETCHED_AT)
        self.assertEqual(vci[0]["ownership_unit"], "fraction")
        self.assertEqual(vci[1]["relationship_type"], "affiliate")
        self.assertEqual(vci[0]["source_record_identity"], "vci:sub_organ_code:VCI-001")
        self.assertEqual(kbs[0]["ownership_unit"], "percent")
        self.assertEqual(kbs[0]["relationship_type"], "công ty con")
        self.assertEqual(kbs[0]["source_record_identity"], "kbs:name:kbs company")
        self.assertEqual(kbs[0]["charter_capital"], -1)
        self.assertIsNone(kbs[0]["currency"])

    def test_source_separation_does_not_merge_identity_or_relationship_type(self):
        vci = sync.persist_current_snapshot(self.conn, "VCB", "VCI", VCI_PAYLOAD, FETCHED_AT)
        kbs = sync.persist_current_snapshot(self.conn, "VCB", "KBS", KBS_PAYLOAD, FETCHED_AT)
        self.assertNotEqual(vci["snapshot_id"], kbs["snapshot_id"])
        rows = self.conn.execute(
            "SELECT source_name, relationship_type, ownership_unit FROM company_subsidiary_records ORDER BY source_name"
        ).fetchall()
        self.assertIn(("KBS", "công ty con", "percent"), rows)
        self.assertIn(("VCI", "affiliate", "fraction"), rows)

    def test_same_payload_is_idempotent_and_changed_payload_versions_snapshot(self):
        first = sync.persist_current_snapshot(self.conn, "AAA", "VCI", VCI_PAYLOAD, FETCHED_AT)
        repeat = sync.persist_current_snapshot(self.conn, "AAA", "VCI", VCI_PAYLOAD, "2026-07-23T00:00:00+00:00")
        changed_payload = {**VCI_PAYLOAD, "subsidiaries": [{**VCI_PAYLOAD["subsidiaries"][0], "ownership_percent": 0.9}]}
        changed = sync.persist_current_snapshot(self.conn, "AAA", "VCI", changed_payload, "2026-07-24T00:00:00+00:00")
        self.assertTrue(first["inserted"])
        self.assertFalse(repeat["inserted"])
        self.assertEqual(first["snapshot_id"], repeat["snapshot_id"])
        self.assertNotEqual(first["raw_hash"], changed["raw_hash"])
        self.assertNotEqual(first["snapshot_id"], changed["snapshot_id"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM company_subsidiary_snapshots").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM company_subsidiary_records").fetchone()[0], 4)

    def test_null_fields_and_raw_payload_are_retained(self):
        payload = {"records": [{
            "update_date": None, "name": "Name Only", "charter_capital": None,
            "ownership_percent": None, "currency": None, "type": None,
        }]}
        result = sync.persist_current_snapshot(self.conn, "AAA", "KBS", payload, FETCHED_AT)
        record = self.conn.execute(
            "SELECT provider_record_id, relationship_type, ownership_percent, charter_capital, currency, provider_update_date, raw_record_json, provenance_json FROM company_subsidiary_records"
        ).fetchone()
        self.assertEqual(record[:6], (None, None, None, None, None, None))
        self.assertEqual(json.loads(record[6])["name"], "Name Only")
        self.assertEqual(json.loads(record[7])["ownership_unit"], "percent")
        self.assertEqual(result["record_count"], 1)

    def test_empty_or_error_payload_never_creates_complete_snapshot(self):
        cases = [
            ("VCI", {"subsidiaries": [], "affiliates": []}),
            ("KBS", {"records": []}),
            ("VCI", {"error": "upstream_failed"}),
            ("KBS", {"error": "upstream_failed"}),
        ]
        for source, payload in cases:
            with self.subTest(source=source, payload=payload):
                with self.assertRaisesRegex(ValueError, "(empty|missing)"):
                    sync.persist_current_snapshot(self.conn, "AAA", source, payload, FETCHED_AT)
                self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM company_subsidiary_snapshots").fetchone()[0], 0)

    def test_duplicate_provider_identity_is_rejected_before_any_write(self):
        payload = {"subsidiaries": [
            {"organ_name": "First", "ownership_percent": 1.0, "sub_organ_code": "DUP"},
            {"organ_name": "Second", "ownership_percent": 0.9, "sub_organ_code": "DUP"},
        ], "affiliates": []}
        with self.assertRaisesRegex(ValueError, "duplicate VCI source record identity"):
            sync.persist_current_snapshot(self.conn, "AAA", "VCI", payload, FETCHED_AT)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM company_subsidiary_snapshots").fetchone()[0], 0)

    def test_additive_migration_preserves_existing_schema_and_is_idempotent(self):
        legacy = sqlite3.connect(":memory:")
        legacy.execute("CREATE TABLE shareholders(ticker TEXT PRIMARY KEY, shareholder_name TEXT)")
        legacy.execute("INSERT INTO shareholders VALUES('AAA', 'Legacy Holder')")
        sync.init_db(legacy)
        sync.init_db(legacy)
        self.assertEqual(legacy.execute("SELECT shareholder_name FROM shareholders").fetchone(), ("Legacy Holder",))
        columns = {row[1] for row in legacy.execute("PRAGMA table_info(company_subsidiary_snapshots)")}
        self.assertTrue({"snapshot_id", "schema_version", "raw_hash", "raw_payload_json", "is_complete"}.issubset(columns))
        self.assertEqual(legacy.execute("SELECT COUNT(*) FROM company_subsidiary_snapshots").fetchone(), (0,))
        legacy.close()


if __name__ == "__main__":
    unittest.main()
