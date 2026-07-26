"""Producer-side Corporate Intelligence snapshot export contracts."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import company_profile_sync as profile_sync  # noqa: E402
import company_subsidiaries_sync as subsidiaries_sync  # noqa: E402
import corporate_events_sync as events_sync  # noqa: E402
import export_ai_bundle as bundle  # noqa: E402
import ownership_structure_sync as ownership_sync  # noqa: E402


FETCHED_AT = "2026-07-22T00:00:00+00:00"


class CorporateIntelligenceExportTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        profile_sync.init_db(self.conn)
        subsidiaries_sync.init_db(self.conn)
        ownership_sync.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_available_sections_keep_sources_and_provenance_separate(self):
        profile_sync.persist_current_snapshot(self.conn, "AAA", "VCI", {"record": {
            "symbol": "AAA", "organ_code": "AAA", "organ_name": "VCI Name", "sector": "Banks",
        }}, FETCHED_AT)
        profile_sync.persist_current_snapshot(self.conn, "AAA", "KBS", {"record": {
            "symbol": "AAA", "tax_id": "0100", "business_model": "KBS model", "charter_capital": 77,
        }}, FETCHED_AT)
        subsidiaries_sync.persist_current_snapshot(self.conn, "AAA", "VCI", {
            "subsidiaries": [{"organ_name": "Sub", "sub_organ_code": "SUB", "ownership_percent": 1.0}],
            "affiliates": [],
        }, FETCHED_AT)
        ownership_sync.persist_current_snapshot(self.conn, "AAA", {"records": [{
            "owner_type": "State", "ownership_percentage": 74.8, "shares_owned": 100, "update_date": "2025-12-31",
        }]}, FETCHED_AT)
        result = bundle.load_corporate_intelligence(self.conn, "AAA")
        self.assertEqual(result["status"], "available")
        self.assertEqual({item["source_name"] for item in result["company_profile"]["sources"]}, {"VCI", "KBS"})
        profile_sources = {item["source_name"]: item["record"]["qualified_fields"] for item in result["company_profile"]["sources"]}
        self.assertIn("sector", profile_sources["VCI"])
        self.assertNotIn("sector", profile_sources["KBS"])
        ownership = result["ownership_structure"]["sources"][0]["records"][0]
        self.assertEqual(ownership["fields"]["ownership_percentage"], 74.8)
        self.assertEqual(ownership["provenance"]["ownership_unit"], "percentage_points")

    def test_missing_tables_are_explicit(self):
        conn = sqlite3.connect(":memory:")
        result = bundle.load_corporate_intelligence(conn, "AAA")
        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["company_profile"]["status"], "missing")
        conn.close()

    def test_corporate_events_export_is_partial_with_bounded_provenance(self):
        events_sync.init_db(self.conn)
        events_sync.ingest_events(self.conn, "AAA", "VCI", [{
            "id": "event-1", "ticker": "AAA", "event_code": "DIV", "category": "DIVIDEND",
            "event_title_vi": "Cash dividend", "event_title_en": "Dividend", "record_date": None,
            "exercise_ratio": None, "value_per_share": 0,
        }], FETCHED_AT, parameters={"fixture": True})
        section = bundle.load_corporate_intelligence(self.conn, "AAA")["corporate_events"]
        self.assertEqual((section["status"], section["coverage_status"]), ("partial", "partial_unqualified_50_row_cap"))
        record = section["sources"][0]["records"][0]
        self.assertEqual(record["provider_event_id"], "event-1")
        self.assertIsNone(record["fields"]["record_date"])
        self.assertEqual(record["fields"]["value_per_share"], 0)
        self.assertEqual(record["provenance"]["provider"], "VCI")

    def test_corporate_events_missing_and_malformed_are_explicit(self):
        self.assertEqual(bundle.load_corporate_intelligence(self.conn, "AAA")["corporate_events"]["status"], "missing")
        events_sync.init_db(self.conn)
        self.conn.execute("INSERT INTO corporate_event_records(record_id,schema_version,provider,provider_event_id,ticker,first_observed_at,last_observed_at,revision_status,coverage_status) VALUES('bad',1,'KBS','bad','AAA',?,?,?,?)", (FETCHED_AT, FETCHED_AT, "observed", "partial_unqualified_50_row_cap"))
        self.conn.commit()
        self.assertEqual(bundle.load_corporate_intelligence(self.conn, "AAA")["corporate_events"]["status"], "malformed")

    def test_malformed_latest_snapshot_is_not_silently_replaced(self):
        profile_sync.persist_current_snapshot(self.conn, "AAA", "VCI", {"record": {"symbol": "AAA", "organ_code": "AAA"}}, FETCHED_AT)
        self.conn.execute("UPDATE company_profile_snapshots SET raw_payload_json='not-json'")
        self.conn.commit()
        result = bundle.load_corporate_intelligence(self.conn, "AAA")
        self.assertEqual(result["status"], "malformed")
        section = result["company_profile"]
        self.assertEqual(section["status"], "malformed")
        self.assertEqual(section["sources"][0]["status"], "malformed_snapshot")

    def test_multi_source_profile_rows_are_not_merged(self):
        profile_sync.persist_current_snapshot(self.conn, "AAA", "VCI", {"record": {"symbol": "AAA", "organ_code": "AAA", "issue_share": 10}}, FETCHED_AT)
        profile_sync.persist_current_snapshot(self.conn, "AAA", "KBS", {"record": {"symbol": "AAA", "tax_id": "99", "outstanding_shares": 11}}, FETCHED_AT)
        sources = bundle.load_corporate_intelligence(self.conn, "AAA")["company_profile"]["sources"]
        records = {item["source_name"]: item["record"]["qualified_fields"] for item in sources}
        self.assertIn("issue_share", records["VCI"])
        self.assertNotIn("outstanding_shares", records["VCI"])
        self.assertIn("outstanding_shares", records["KBS"])

    def test_latest_major_shareholder_snapshot_exports_existing_delta_contract(self):
        self.conn.executescript("""
        CREATE TABLE major_shareholder_snapshots(
            snapshot_id TEXT PRIMARY KEY, schema_version INTEGER, ticker TEXT, as_of_date TEXT,
            source_name TEXT, record_origin TEXT, source_reference TEXT, fetched_at TEXT,
            record_count INTEGER, status TEXT, is_complete INTEGER);
        CREATE TABLE shareholder_records_v2(
            record_key TEXT PRIMARY KEY, ticker TEXT, holder_name TEXT, normalized_holder_name TEXT,
            shares REAL, ownership_pct REAL, as_of_date TEXT, source_name TEXT, source_reference TEXT,
            record_origin TEXT, reconciliation_status TEXT, provenance_json TEXT);
        """)
        self.conn.executemany(
            "INSERT INTO major_shareholder_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("old", 1, "AAA", "2026-01-31", "VCI", "api", "fixture://vci", FETCHED_AT, 1, "done", 1),
                ("new", 1, "AAA", "2026-02-28", "VCI", "api", "fixture://vci", "2026-07-23T00:00:00+00:00", 1, "done", 1),
            ],
        )
        self.conn.executemany(
            "INSERT INTO shareholder_records_v2 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("old-row", "AAA", "Holder", "holder", 100, 10, "2026-01-31", "VCI", "fixture://vci", "api", "accepted", "[]"),
                ("new-row", "AAA", "Holder", "holder", 125, 12, "2026-02-28", "VCI", "fixture://vci", "api", "accepted", "[]"),
            ],
        )
        self.conn.commit()
        major = bundle.load_corporate_intelligence(self.conn, "AAA")["major_shareholders"]
        self.assertEqual(major["status"], "available")
        self.assertEqual(major["sources"][0]["snapshot_id"], "new")
        self.assertEqual(major["sources"][0]["delta"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
