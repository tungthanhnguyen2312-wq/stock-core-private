"""Unit tests for observability_events.py.

Validates versioned structured event generation, success and failure paths,
price/volume basis contract status recording, and deterministic JSON emission.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from observability_events import (
    SCHEMA_VERSION,
    EventOutcome,
    EventStage,
    build_observability_event,
    emit_observability_event,
)


class ObservabilityEventsTests(unittest.TestCase):
    def test_schema_version_is_1_0_0(self):
        self.assertEqual(SCHEMA_VERSION, "1.0.0")

    def test_success_event_building(self):
        event = build_observability_event(
            EventStage.ATOMIC_PROMOTION,
            EventOutcome.SUCCESS,
            artifact_filename="focus_extract.json",
            sha256="abc123sha",
            size_bytes=1024,
            price_basis="raw",
            volume_basis="raw_shares_traded",
            is_actionable=True,
            target_path="/tmp/focus_extract.json",
        )
        self.assertEqual(event["schema_version"], "1.0.0")
        self.assertEqual(event["stage"], "atomic_promotion")
        self.assertEqual(event["outcome"], "success")
        self.assertEqual(event["artifact_identity"]["filename"], "focus_extract.json")
        self.assertEqual(event["basis_contract_status"]["price_basis"], "raw")
        self.assertTrue(event["basis_contract_status"]["is_actionable"])
        self.assertIsNone(event["failure_reason"])

    def test_failure_event_building(self):
        event = build_observability_event(
            EventStage.PRE_PROMOTION_VALIDATION,
            EventOutcome.FAILED,
            artifact_filename="analysis_bundle.json",
            reason="malformed_json_structure",
            error_type="ValueError",
            price_basis="unknown",
            is_actionable=False,
        )
        self.assertEqual(event["stage"], "pre_promotion_validation")
        self.assertEqual(event["outcome"], "failed")
        self.assertEqual(event["failure_reason"]["reason"], "malformed_json_structure")
        self.assertEqual(event["failure_reason"]["error_type"], "ValueError")
        self.assertFalse(event["basis_contract_status"]["is_actionable"])

    def test_emit_observability_event_jsonl_append(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "events.jsonl"
            ev1 = build_observability_event("artifact_generation", "success", artifact_filename="bundle.json", timestamp="2026-07-28T12:00:00Z")
            ev2 = build_observability_event("publish_dashboard", "skipped", reason="dry_run", timestamp="2026-07-28T12:00:01Z")

            str1 = emit_observability_event(ev1, log_file)
            str2 = emit_observability_event(ev2, log_file)

            lines = log_file.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            parsed1 = json.loads(lines[0])
            parsed2 = json.loads(lines[1])
            self.assertEqual(parsed1["stage"], "artifact_generation")
            self.assertEqual(parsed2["stage"], "publish_dashboard")
            self.assertEqual(parsed2["outcome"], "skipped")

    def test_deterministic_serialization(self):
        ev = build_observability_event(
            EventStage.MANIFEST_VERIFICATION,
            EventOutcome.SUCCESS,
            artifact_filename="bundle_manifest.json",
            timestamp="2026-07-28T12:00:00Z",
        )
        json1 = emit_observability_event(ev)
        json2 = emit_observability_event(ev)
        self.assertEqual(json1, json2)


if __name__ == "__main__":
    unittest.main()
