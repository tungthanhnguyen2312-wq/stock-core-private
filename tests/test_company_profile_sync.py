"""Source-scoped current company-profile snapshot contracts."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import company_profile_sync as sync  # noqa: E402


FETCHED_AT = "2026-07-22T00:00:00+00:00"
VCI_PAYLOAD = {"record": {
    "symbol": "VCB", "organ_code": "VCB", "organ_name": "VCI Bank", "organ_short_name": "Bank",
    "sector": "Banks", "company_profile": "Provider profile", "listing_date": "2009-06-30T00:00:00",
    "issue_share": 1000,
}}
KBS_PAYLOAD = {"record": {
    "symbol": "VCB", "business_model": "Provider business list", "charter_capital": 83557,
    "listing_date": "30/06/2009", "exchange": "HOSE", "outstanding_shares": 1000,
    "website": "https://example.test", "address": "Provider address", "tax_id": "0100112437",
    "as_of_date": "2025-12-31T00:00:00",
}}


class CompanyProfileSyncTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        sync.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_source_specific_normalization_keeps_non_equivalent_fields_separate(self):
        vci = sync.normalize_current_payload("VCB", "VCI", VCI_PAYLOAD, FETCHED_AT)
        kbs = sync.normalize_current_payload("VCB", "KBS", KBS_PAYLOAD, FETCHED_AT)
        self.assertEqual(vci["provider_identity"], "VCB")
        self.assertEqual(vci["identity_basis"], "organ_code")
        self.assertEqual(vci["qualified_fields"]["issue_share"], 1000)
        self.assertNotIn("outstanding_shares", vci["qualified_fields"])
        self.assertEqual(kbs["provider_identity"], "0100112437")
        self.assertEqual(kbs["identity_basis"], "tax_id")
        self.assertEqual(kbs["qualified_fields"]["charter_capital"], 83557)
        self.assertEqual(kbs["qualified_fields"]["address"], "Provider address")
        self.assertNotIn("sector", kbs["qualified_fields"])

    def test_source_separation_does_not_create_a_common_identity(self):
        vci = sync.persist_current_snapshot(self.conn, "VCB", "VCI", VCI_PAYLOAD, FETCHED_AT)
        kbs = sync.persist_current_snapshot(self.conn, "VCB", "KBS", KBS_PAYLOAD, FETCHED_AT)
        self.assertNotEqual(vci["snapshot_id"], kbs["snapshot_id"])
        rows = self.conn.execute(
            "SELECT source_name, provider_identity, identity_basis FROM company_profile_records ORDER BY source_name"
        ).fetchall()
        self.assertEqual(rows, [("KBS", "0100112437", "tax_id"), ("VCI", "VCB", "organ_code")])

    def test_same_payload_is_idempotent_and_changed_payload_versions_snapshot(self):
        first = sync.persist_current_snapshot(self.conn, "VCB", "VCI", VCI_PAYLOAD, FETCHED_AT)
        repeat = sync.persist_current_snapshot(self.conn, "VCB", "VCI", VCI_PAYLOAD, "2026-07-23T00:00:00+00:00")
        changed_payload = {"record": {**VCI_PAYLOAD["record"], "company_profile": "Changed profile"}}
        changed = sync.persist_current_snapshot(self.conn, "VCB", "VCI", changed_payload, "2026-07-24T00:00:00+00:00")
        self.assertTrue(first["inserted"])
        self.assertFalse(repeat["inserted"])
        self.assertEqual(first["snapshot_id"], repeat["snapshot_id"])
        self.assertNotEqual(first["snapshot_id"], changed["snapshot_id"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM company_profile_snapshots").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM company_profile_records").fetchone()[0], 2)

    def test_null_qualified_fields_and_raw_record_are_retained(self):
        payload = {"record": {"symbol": "AAA", "tax_id": None, "charter_capital": None, "address": None}}
        result = sync.persist_current_snapshot(self.conn, "AAA", "KBS", payload, FETCHED_AT)
        row = self.conn.execute("SELECT provider_identity, identity_basis, qualified_fields_json, raw_record_json FROM company_profile_records").fetchone()
        self.assertEqual(row[:2], ("AAA", "symbol_fallback"))
        self.assertIsNone(json.loads(row[2])["charter_capital"])
        self.assertIsNone(json.loads(row[2])["address"])
        self.assertEqual(json.loads(row[3])["symbol"], "AAA")
        self.assertTrue(result["is_complete"])

    def test_empty_or_error_payload_never_creates_complete_snapshot(self):
        for source, payload in (
            ("VCI", {"record": {}}),
            ("KBS", {"error": "upstream_failed"}),
            ("VCI", {"record": [VCI_PAYLOAD["record"], VCI_PAYLOAD["record"]]}),
        ):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, "(empty|missing)"):
                    sync.persist_current_snapshot(self.conn, "AAA", source, payload, FETCHED_AT)
                self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM company_profile_snapshots").fetchone()[0], 0)

    def test_duplicate_provider_profile_rows_are_rejected_deterministically(self):
        class DuplicateOverview:
            def __len__(self):
                return 2

        with self.assertRaisesRegex(ValueError, "VCI returned 2 company profile rows for VCB"):
            sync.payload_from_overview_frame(DuplicateOverview(), "VCI", "VCB")

    def test_additive_migration_is_idempotent_and_preserves_existing_tables(self):
        legacy = sqlite3.connect(":memory:")
        legacy.execute("CREATE TABLE shareholders(ticker TEXT PRIMARY KEY, shareholder_name TEXT)")
        legacy.execute("INSERT INTO shareholders VALUES('AAA', 'Legacy Holder')")
        sync.init_db(legacy)
        sync.init_db(legacy)
        self.assertEqual(legacy.execute("SELECT shareholder_name FROM shareholders").fetchone(), ("Legacy Holder",))
        columns = {row[1] for row in legacy.execute("PRAGMA table_info(company_profile_snapshots)")}
        self.assertTrue({"snapshot_id", "schema_version", "raw_hash", "raw_payload_json", "is_complete"}.issubset(columns))
        legacy.close()


if __name__ == "__main__":
    unittest.main()
