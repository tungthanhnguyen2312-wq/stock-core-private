from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from source_schema_guards import (  # noqa: E402
    SourceSchemaError, guard_alias_columns, guard_financial_statement_columns,
)


class SourceSchemaGuardTests(unittest.TestCase):
    def test_valid_financial_wide_schema(self):
        result = guard_financial_statement_columns(
            ["ticker", "report_type", "source", "item", "item_id", "unit", "2025-Q4"],
            "fixture://financial",
        )
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["period_fields"], ["2025-Q4"])

    def test_missing_fields_raise_structured_parse_failure(self):
        with self.assertRaises(SourceSchemaError) as caught:
            guard_financial_statement_columns(["ticker", "unexpected"], "fixture://broken")
        payload = caught.exception.to_dict()
        self.assertEqual(payload["status"], "parse_failed")
        self.assertEqual(payload["source"], "fixture://broken")
        self.assertIn("period/value", payload["missing_fields"])
        self.assertEqual(payload["payload_keys"], ["ticker", "unexpected"])

    def test_unit_can_be_diagnostic_or_required(self):
        columns = ["ticker", "report_type", "source", "item", "item_id", "2025-Q4"]
        self.assertEqual(
            guard_financial_statement_columns(columns, "fixture://legacy")["unit_field_status"],
            "missing",
        )
        with self.assertRaises(SourceSchemaError):
            guard_financial_statement_columns(columns, "fixture://strict", require_unit=True)

    def test_alias_schema_guard(self):
        with self.assertRaises(SourceSchemaError) as caught:
            guard_alias_columns(["ticker", "alias"], "fixture://aliases")
        self.assertIn("priority", caught.exception.missing_fields)


if __name__ == "__main__":
    unittest.main()
