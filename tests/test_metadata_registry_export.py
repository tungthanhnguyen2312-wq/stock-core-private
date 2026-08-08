from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import metadata_registry_export as adapter

REPO_ROOT = Path(__file__).resolve().parent.parent
# Cross-repo, TEST-ONLY: confirms Producer output matches the Consumer-owned schema.
# metadata_registry_export.py itself never imports ai-core-private.
SCHEMA_PATH = REPO_ROOT.parent / "ai-core-private" / "validation" / "schemas" / "vnstock_metadata_snapshot_registry_handoff.schema.json"
VALIDATOR_PATH = REPO_ROOT.parent / "ai-core-private" / "builders" / "validate_json_schema_subset.py"

_ROW_COLUMNS = (
    "ticker", "exchange", "industry", "foreign_room_pct", "pe", "pb", "roe",
    "market_cap", "shares_outstanding", "free_float_est", "dividend_yield",
    "margin_status", "updated",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _consumer_schema_validator():
    return _load_module("registry_schema_validator_for_producer_tests", VALIDATOR_PATH)


class MetadataRegistryExportTests(unittest.TestCase):
    def make_db(self, path: Path, rows: list[tuple]) -> None:
        conn = sqlite3.connect(path)
        conn.execute(
            """CREATE TABLE metadata(
                ticker TEXT PRIMARY KEY, exchange TEXT, industry TEXT, foreign_room_pct REAL,
                pe REAL, pb REAL, roe REAL, market_cap REAL, shares_outstanding REAL,
                free_float_est REAL, dividend_yield REAL, margin_status TEXT, updated TEXT)"""
        )
        placeholders = ",".join("?" for _ in _ROW_COLUMNS)
        conn.executemany(f"INSERT INTO metadata({','.join(_ROW_COLUMNS)}) VALUES ({placeholders})", rows)
        conn.commit()
        conn.close()

    def test_export_produces_schema_valid_records_for_a_fully_synced_ticker(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "vn_stock.db"
            self.make_db(db, [(
                "AAA", "HSX", "Hóa chất", 98.49, 8.38, 0.51, 6.75,
                2669576000000.0, 393742730.0, 0.4977, 4.0, None, "2026-07-27 19:38",
            )])
            records = adapter.export_records(db, tickers=["AAA"])
            self.assertEqual(len(records), len(adapter.FIELD_CATALOG))

            validator = _consumer_schema_validator()
            schema = validator.load_json(SCHEMA_PATH)
            for record in records:
                self.assertEqual(validator.validate(record, schema), [], record)

    def test_null_field_value_and_dividend_yield_sentinel_are_preserved_not_coerced(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "vn_stock.db"
            self.make_db(db, [(
                "BBB", "HSX", "X", None, None, None, None, None, None, None, -1, None,
                "2026-07-27 20:00",
            )])
            records = adapter.export_records(db, tickers=["BBB"])
            by_field = {r["field"]: r for r in records}
            self.assertIsNone(by_field["margin_status"]["value"])
            self.assertIsNone(by_field["pe"]["value"])
            self.assertEqual(by_field["dividend_yield"]["value"], -1)  # sentinel, never coerced

            validator = _consumer_schema_validator()
            schema = validator.load_json(SCHEMA_PATH)
            for record in records:
                self.assertEqual(validator.validate(record, schema), [], record)

    def test_unsynced_ticker_fails_closed_with_no_records(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "vn_stock.db"
            self.make_db(db, [(
                "DDD", "HSX", "X", None, None, None, None, None, None, None, None, None, None,
            )])
            records = adapter.export_records(db, tickers=["DDD"])
            self.assertEqual(records, [])

    def test_ticker_subset_filters_correctly(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "vn_stock.db"
            self.make_db(db, [
                ("AAA", "HSX", "X", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, None, "2026-07-27 19:38"),
                ("BBB", "HSX", "X", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, None, "2026-07-27 19:38"),
            ])
            records = adapter.export_records(db, tickers=["AAA"])
            self.assertEqual({r["ticker"] for r in records}, {"AAA"})

    def test_deterministic_output_for_same_input(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "vn_stock.db"
            self.make_db(db, [
                ("BBB", "HSX", "X", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, None, "2026-07-27 19:38"),
                ("AAA", "HSX", "X", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, None, "2026-07-27 19:38"),
            ])
            first = adapter.export_records(db)
            second = adapter.export_records(db)
            self.assertEqual(first, second)
            self.assertEqual(first[0]["ticker"], "AAA")  # ORDER BY ticker, not insertion order
            self.assertEqual(first[-1]["ticker"], "BBB")

    def test_missing_database_raises(self):
        with tempfile.TemporaryDirectory() as raw:
            missing = Path(raw) / "does_not_exist.db"
            with self.assertRaises(FileNotFoundError):
                adapter.export_records(missing)

    def test_missing_table_raises(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "vn_stock.db"
            sqlite3.connect(db).close()  # valid db file, no metadata table
            with self.assertRaises(sqlite3.OperationalError):
                adapter.export_records(db)

    def test_write_records_only_when_explicit_output_path_given(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "vn_stock.db"
            self.make_db(db, [(
                "AAA", "HSX", "X", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, None, "2026-07-27 19:38",
            )])
            records = adapter.export_records(db, tickers=["AAA"])
            out = Path(raw) / "dry_run_output.json"
            self.assertFalse(out.exists())
            adapter.write_records(records, out)
            self.assertTrue(out.exists())
            written = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(len(written["records"]), len(adapter.FIELD_CATALOG))

        with self.assertRaises(TypeError):
            adapter.write_records(records)  # no default output path exists to fall back to

    def test_cli_output_defaults_to_none_no_default_write_target(self):
        args = adapter._parse_args(["--db", "unused.db"])
        self.assertIsNone(args.output)

    def test_transform_version_matches_pattern_and_current_meta_sync(self):
        version = adapter.compute_transform_version()
        self.assertRegex(version, r"^meta_sync\.py@sha256:[0-9a-f]{12}$")
        # Pinned to meta_sync.py's current bytes -- update after any legitimate edit to that file
        # (last updated for the vn_time.py sync-timestamp contract, commit e5ba186).
        self.assertEqual(version, "meta_sync.py@sha256:af99418b031c")

    def test_default_registry_snapshot_dir_matches_spec(self):
        self.assertEqual(adapter.DEFAULT_REGISTRY_SNAPSHOT_DIR.parts[-2:], ("registry_snapshots", "metadata"))

    def test_registry_snapshot_filename_and_content_are_schema_valid_jsonl(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "vn_stock.db"
            self.make_db(db, [(
                "AAA", "HSX", "Hóa chất", 98.49, 8.38, 0.51, 6.75,
                2669576000000.0, 393742730.0, 0.4977, 4.0, None, "2026-07-27 19:38",
            )])
            records = adapter.export_records(db, tickers=["AAA"])
            registry_dir = Path(raw) / "registry_snapshots" / "metadata"
            fixed_now = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)

            path = adapter.write_registry_snapshot(records, registry_dir, now=fixed_now)

            self.assertEqual(path.parent, registry_dir)
            self.assertRegex(path.name, r"^vnstock_metadata_snapshot_\d{8}T\d{6}Z_[0-9a-f]{12}\.jsonl$")
            self.assertTrue(path.name.startswith("vnstock_metadata_snapshot_20260728T100000Z_"))

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), len(adapter.FIELD_CATALOG))

            validator = _consumer_schema_validator()
            schema = validator.load_json(SCHEMA_PATH)
            for line in lines:
                record = json.loads(line)
                self.assertEqual(validator.validate(record, schema), [], record)

    def test_registry_snapshot_serialization_is_order_independent(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "vn_stock.db"
            self.make_db(db, [
                ("AAA", "HSX", "X", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, None, "2026-07-27 19:38"),
                ("BBB", "HSX", "X", 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, None, "2026-07-27 19:38"),
            ])
            records = adapter.export_records(db)
            shuffled = list(reversed(records))
            fixed_now = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)

            name_forward = adapter.registry_snapshot_filename(adapter._jsonl_body(records), fixed_now)
            name_shuffled = adapter.registry_snapshot_filename(adapter._jsonl_body(shuffled), fixed_now)
            self.assertEqual(name_forward, name_shuffled)

    def test_registry_snapshot_never_overwrites(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "vn_stock.db"
            self.make_db(db, [(
                "AAA", "HSX", "X", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, None, "2026-07-27 19:38",
            )])
            records = adapter.export_records(db, tickers=["AAA"])
            registry_dir = Path(raw) / "snap"
            fixed_now = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)

            first_path = adapter.write_registry_snapshot(records, registry_dir, now=fixed_now)
            original_content = first_path.read_bytes()

            with self.assertRaises(FileExistsError):
                adapter.write_registry_snapshot(records, registry_dir, now=fixed_now)

            self.assertEqual(first_path.read_bytes(), original_content)  # untouched by the refused retry
            self.assertEqual(len(list(registry_dir.iterdir())), 1)  # no stray temp/second file

    def test_registry_snapshot_atomic_no_partial_or_temp_file_on_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "vn_stock.db"
            self.make_db(db, [(
                "AAA", "HSX", "X", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, None, "2026-07-27 19:38",
            )])
            records = adapter.export_records(db, tickers=["AAA"])
            registry_dir = Path(raw) / "snap"
            fixed_now = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)

            with mock.patch("metadata_registry_export.os.rename", side_effect=OSError("simulated failure")):
                with self.assertRaises(OSError):
                    adapter.write_registry_snapshot(records, registry_dir, now=fixed_now)

            remaining = list(registry_dir.iterdir()) if registry_dir.exists() else []
            self.assertEqual(remaining, [])  # neither the final file nor a stray temp file

    def test_cli_registry_snapshot_flag_optional_and_explicit(self):
        omitted = adapter._parse_args(["--db", "unused.db"])
        self.assertIsNone(omitted.registry_snapshot)

        bare = adapter._parse_args(["--db", "unused.db", "--registry-snapshot"])
        self.assertEqual(Path(bare.registry_snapshot), adapter.DEFAULT_REGISTRY_SNAPSHOT_DIR)

        custom = adapter._parse_args(["--db", "unused.db", "--registry-snapshot", "custom_dir"])
        self.assertEqual(custom.registry_snapshot, "custom_dir")

    def test_main_cli_end_to_end_writes_registry_snapshot_only_when_asked(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "vn_stock.db"
            self.make_db(db, [(
                "AAA", "HSX", "X", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, None, "2026-07-27 19:38",
            )])
            registry_dir = Path(raw) / "snap"

            exit_code = adapter.main(["--db", str(db), "--tickers", "AAA"])
            self.assertEqual(exit_code, 0)
            self.assertFalse(registry_dir.exists())  # dry-run only: nothing written anywhere

            exit_code = adapter.main(["--db", str(db), "--tickers", "AAA", "--registry-snapshot", str(registry_dir)])
            self.assertEqual(exit_code, 0)
            written = list(registry_dir.glob("*.jsonl"))
            self.assertEqual(len(written), 1)
            self.assertEqual(len(written[0].read_text(encoding="utf-8").splitlines()), len(adapter.FIELD_CATALOG))


if __name__ == "__main__":
    unittest.main()
