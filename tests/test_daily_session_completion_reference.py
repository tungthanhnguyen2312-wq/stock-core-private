"""daily_session_completion_reference.py: the non-exhaustive, fail-closed registry
loader that QUALIFIED_SESSION_REFERENCE_CORRECTIVE introduces. Covers exactly the
authority boundary its own module docstring states -- only a status/flag-matched
date is ever returned; a missing/malformed registry or a non-qualifying row never
degrades to anything other than "no proof for this date", never "not a trading day".
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from daily_session_completion_reference import load_qualified_completed_sessions, registry_path


def _write(tmp: str, payload) -> Path:
    path = registry_path(tmp)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class RegistryPathTests(unittest.TestCase):
    def test_registry_path_is_config_relative_to_source_root(self):
        self.assertEqual(Path("/x") / "config" / "daily_research_session_input_registry.json",
                          registry_path("/x"))


class LoadQualifiedCompletedSessionsTests(unittest.TestCase):
    def test_accepts_only_completed_retained_evidence_and_trading_day_valid_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, {"completed_sessions": {
                "2026-09-14": {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True},
                "2026-09-15": {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": False},
                "2026-09-16": {"status": "IN_PROGRESS", "trading_day_valid": True},
                "2026-09-17": {"status": "COMPLETED_RETAINED_EVIDENCE"},
                "2026-09-18": {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": "true"},
            }})
            qualified = load_qualified_completed_sessions(registry_path(tmp))
            self.assertEqual(frozenset({"2026-09-14"}), qualified)

    def test_missing_registry_file_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            qualified = load_qualified_completed_sessions(registry_path(tmp))
            self.assertEqual(frozenset(), qualified)

    def test_malformed_json_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = registry_path(tmp)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{not valid json", encoding="utf-8")
            self.assertEqual(frozenset(), load_qualified_completed_sessions(path))

    def test_unexpected_top_level_shape_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, ["not", "a", "mapping"])
            self.assertEqual(frozenset(), load_qualified_completed_sessions(registry_path(tmp)))

    def test_missing_completed_sessions_key_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, {"schema_version": "1.0.0"})
            self.assertEqual(frozenset(), load_qualified_completed_sessions(registry_path(tmp)))

    def test_absence_from_registry_is_never_asserted_as_a_non_trading_day(self):
        """The loader only ever returns dates it can PROVE; a date simply absent from
        the payload must never appear in the returned set as if it had been positively
        checked and rejected -- there is no way to distinguish "checked, not a trading
        day" from "never recorded" from this function's output, by design."""
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, {"completed_sessions": {
                "2026-09-14": {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True},
                "2026-09-18": {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True},
            }})
            qualified = load_qualified_completed_sessions(registry_path(tmp))
            # 2026-09-15/16/17 are absent -- neither present nor "known false".
            self.assertNotIn("2026-09-15", qualified)
            self.assertNotIn("2026-09-16", qualified)
            self.assertNotIn("2026-09-17", qualified)
            self.assertEqual(frozenset({"2026-09-14", "2026-09-18"}), qualified)


if __name__ == "__main__":
    unittest.main()
