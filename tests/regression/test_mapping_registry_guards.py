from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from financial_mapping import FinancialMappingRegistry  # noqa: E402


SOURCE = ROOT / "config" / "financial_item_map.csv"


class MappingRegistryGuardTests(unittest.TestCase):
    def rows(self):
        with SOURCE.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or []), list(reader)

    def registry(self, mutate=None, metadata=None, require_metadata=False):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        fields, rows = self.rows()
        if mutate:
            mutate(fields, rows)
        path = root / "map.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        meta_path = None
        if metadata is not None:
            meta_path = root / "meta.json"
            meta_path.write_text(json.dumps(metadata), encoding="utf-8")
        try:
            return FinancialMappingRegistry(
                path, metadata_path=meta_path, require_metadata=require_metadata,
                enforce_known_metrics=True,
            )
        finally:
            temporary.cleanup()

    def assert_invalid(self, mutate, phrase):
        with self.assertRaisesRegex((ValueError, csv.Error), phrase):
            self.registry(mutate)

    def test_duplicate_rule_id_rejected(self):
        self.assert_invalid(lambda _f, rows: rows.append(dict(rows[0])), "duplicate rule_id")

    def test_ambiguous_duplicate_priority_rejected(self):
        def mutate(_fields, rows):
            clone = dict(rows[0]); clone["rule_id"] += "_clone"; rows.append(clone)
        self.assert_invalid(mutate, "Ambiguous exact mapping")

    def test_invalid_regex_rejected(self):
        self.assert_invalid(lambda _f, rows: rows[0].update(label_regex="["), "unterminated")

    def test_unknown_canonical_metric_rejected(self):
        self.assert_invalid(lambda _f, rows: rows[0].update(canonical_metric="invented"), "Unknown canonical")

    def test_invalid_entity_and_report_types_rejected(self):
        self.assert_invalid(lambda _f, rows: rows[0].update(entity_type="fund"), "Unsupported entity")
        self.assert_invalid(lambda _f, rows: rows[0].update(report_type="notes"), "Unsupported report")

    def test_invalid_sign_and_unit_multipliers_rejected(self):
        self.assert_invalid(lambda _f, rows: rows[0].update(sign_multiplier="0"), "Invalid sign")
        self.assert_invalid(lambda _f, rows: rows[0].update(unit_multiplier="-1"), "Invalid unit")

    def test_conflicting_exact_mapping_rejected(self):
        def mutate(_fields, rows):
            clone = dict(rows[0]); clone["rule_id"] += "_conflict"; clone["canonical_metric"] = "ebit"; rows.append(clone)
        self.assert_invalid(mutate, "Ambiguous exact mapping")

    def test_registry_metadata_requires_version_and_provenance(self):
        with self.assertRaisesRegex(ValueError, "registry_version"):
            self.registry(metadata={}, require_metadata=True)
        valid = {
            "registry_version": "test",
            "provenance": {"source_basis": "fixture", "owner": "test", "updated_at": "2026-07-13"},
        }
        self.assertEqual(self.registry(metadata=valid, require_metadata=True).metadata, valid)


if __name__ == "__main__":
    unittest.main()
