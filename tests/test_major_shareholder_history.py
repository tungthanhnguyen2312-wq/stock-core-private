"""Forward-only major-shareholder snapshot and delta contracts."""

from __future__ import annotations

import sqlite3
import sys
import unittest
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shareholder_pipeline import (  # noqa: E402
    DONE,
    MAJOR_SHAREHOLDER_SNAPSHOT_SCHEMA_VERSION,
    build_major_shareholder_snapshot_manifest,
    calculate_major_shareholder_delta,
    validate_major_shareholder_snapshot,
)
if importlib.util.find_spec("pandas"):
    import shareholders_sync as sync  # noqa: E402
else:
    sync = None


FETCHED_AT = "2026-07-22T00:00:00+00:00"


def record(
    holder: str,
    as_of: str = "2026-06-30",
    *,
    shares: float | None = 100,
    pct: float | None = 10,
    ticker: str = "AAA",
    source: str = "VCI",
    origin: str = "api",
    reference: str | None = "fixture://vci",
    reconciliation_status: str = "accepted",
) -> dict:
    return {
        "ticker": ticker,
        "holder_name": holder.title(),
        "normalized_holder_name": holder.casefold(),
        "shares": shares,
        "ownership_pct": pct,
        "as_of_date": as_of,
        "source_name": source,
        "source_reference": reference,
        "verified_at": None,
        "fetched_at": FETCHED_AT,
        "note": None,
        "record_origin": origin,
        "reconciliation_status": reconciliation_status,
        "conflict_group": None,
        "provenance": [],
    }


def summary(records: list[dict]) -> dict:
    source = records[0]["source_name"] if records else "VCI"
    return {
        "ticker": records[0]["ticker"] if records else "AAA",
        "status": DONE,
        "reason": "fixture",
        "attempts": [{
            "source": source, "status": DONE, "error": None, "reason": None,
            "error_reason": None, "record_count": len(records), "parsed_record_count": len(records),
            "request_timestamp": FETCHED_AT, "latest_as_of_date": records[0]["as_of_date"] if records else None,
        }],
        "raw_record_count": len(records),
        "parsed_record_count": len(records),
        "deduplicated_record_count": len(records),
        "manual_override_count": 0,
        "latest_as_of_date": records[0]["as_of_date"] if records else None,
        "freshness": {},
        "records": records,
    }


def manifest(records: list[dict]) -> dict:
    built = build_major_shareholder_snapshot_manifest(summary(records))
    assert built is not None
    return built


class MajorShareholderHistoryTests(unittest.TestCase):
    @unittest.skipUnless(sync is not None, "pandas is only required by the SQLite sync wrapper")
    def test_migration_and_manifest_persistence_are_idempotent(self):
        connection = sqlite3.connect(":memory:")
        sync.init_db(connection)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(major_shareholder_snapshots)")}
        self.assertTrue({"snapshot_id", "schema_version", "as_of_date", "is_complete"}.issubset(columns))

        payload = summary([record("holder a"), record("holder b", shares=20, pct=2)])
        self.assertTrue(sync.persist_summary(connection, payload))
        self.assertTrue(sync.persist_summary(connection, payload))
        rows = connection.execute(
            "SELECT schema_version, record_count, is_complete FROM major_shareholder_snapshots"
        ).fetchall()
        self.assertEqual(rows, [(MAJOR_SHAREHOLDER_SNAPSHOT_SCHEMA_VERSION, 2, 1)])
        connection.close()

    def test_manifest_is_forward_only_and_requires_one_complete_dated_api_scope(self):
        self.assertIsNotNone(build_major_shareholder_snapshot_manifest(summary([record("holder a")])))
        self.assertIsNone(build_major_shareholder_snapshot_manifest(summary([record("holder a", as_of=None)])))
        self.assertIsNone(build_major_shareholder_snapshot_manifest(summary([record("holder a", origin="manual")])))
        self.assertIsNone(build_major_shareholder_snapshot_manifest(summary([
            record("holder a"), record("holder b", source="KBS"),
        ])))
        self.assertIsNone(build_major_shareholder_snapshot_manifest(summary([
            record("holder a", reconciliation_status="conflict_preserved"),
        ])))

    def test_snapshot_eligibility_excludes_invalid_dates_incomplete_conflicts_manual_and_mixed_scope(self):
        records = [record("holder a")]
        valid = manifest(records)
        cases = [
            (dict(valid, is_complete=0), records, "incomplete_snapshot"),
            (dict(valid, as_of_date="bad-date"), records, "invalid_snapshot_date"),
            (dict(valid, record_origin="manual"), [record("holder a", origin="manual")], "manual_only_snapshot"),
            (valid, [record("holder a", reconciliation_status="conflict_preserved")], "conflict_preserved"),
            (valid, [record("holder a", source="KBS")], "mixed_scope"),
        ]
        for candidate, candidate_records, reason in cases:
            with self.subTest(reason=reason):
                result = validate_major_shareholder_snapshot(candidate, candidate_records)
                self.assertFalse(result["eligible"])
                self.assertEqual(result["reason"], reason)

    def test_delta_detects_new_disappeared_and_numeric_changes_without_null_inference(self):
        previous_records = [
            record("holder changed", shares=100, pct=10),
            record("holder gone", shares=50, pct=5),
            record("holder null", shares=None, pct=None),
        ]
        current_records = [
            record("holder changed", as_of="2026-07-31", shares=125, pct=12),
            record("holder new", as_of="2026-07-31", shares=20, pct=2),
            record("holder null", as_of="2026-07-31", shares=10, pct=None),
        ]
        result = calculate_major_shareholder_delta(
            manifest(previous_records), previous_records, manifest(current_records), current_records,
        )
        self.assertEqual(result["status"], "ok")
        changes = {item["normalized_holder_name"]: item for item in result["changes"]}
        self.assertEqual(set(changes), {"holder changed", "holder gone", "holder new"})
        self.assertEqual(changes["holder changed"]["change_type"], "changed")
        self.assertEqual(changes["holder changed"]["shares_delta"], 25)
        self.assertEqual(changes["holder changed"]["ownership_pct_delta"], 2)
        self.assertEqual(changes["holder gone"]["change_type"], "disappeared_holder")
        self.assertEqual(changes["holder new"]["change_type"], "new_holder")
        self.assertNotIn("holder null", changes)

    def test_delta_rejects_different_source_scope(self):
        previous_records = [record("holder a")]
        current_records = [record("holder a", as_of="2026-07-31", source="KBS", reference="fixture://kbs")]
        result = calculate_major_shareholder_delta(
            manifest(previous_records), previous_records, manifest(current_records), current_records,
        )
        self.assertEqual(result["status"], "incomparable_source_scope")
        self.assertEqual(result["changes"], [])


if __name__ == "__main__":
    unittest.main()
