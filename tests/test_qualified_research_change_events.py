import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qualified_research_change_events import build, build_v2
from tests.test_qualified_research_delta import brief


class ChangeEventsTests(unittest.TestCase):
    def test_identical_brief_is_no_change_and_deterministic(self):
        first, second = build(brief(), brief()), build(brief(), brief())
        self.assertEqual(first, second); self.assertEqual(first["status"], "NO_CHANGE")

    def test_capability_transition_has_semantic_id_and_provenance(self):
        before, after = brief(), brief()
        before["identity"]["eligibility"] = {"status": "blocked", "reason_codes": ["missing"]}
        after["identity"]["eligibility"] = {"status": "available", "reason_codes": []}
        result = build(before, after)
        event = next(item for item in result["events"] if item["family"] == "capability_transition")
        self.assertTrue(event["event_id"].startswith("qrc-")); self.assertEqual(event["provenance_references"], ["identity.eligibility"])
        self.assertFalse(event["is_actionable"])

    def test_formatting_only_difference_is_not_an_event(self):
        before, after = brief(), copy.deepcopy(brief())
        after["display_only"] = "rebuilt"
        self.assertEqual(build(before, after)["status"], "NO_CHANGE")

    def test_v2_unknown_to_available_is_availability_established_not_blocked(self):
        previous = {"schema_version": "2.0.0", "snapshot_id": "qrs2-served", "tickers": [{"ticker": "POW", "research_status": "unknown", "semantic_sha256": "old"}]}
        current = {"schema_version": "2.0.0", "snapshot_id": "qrs2-current", "tickers": [{"ticker": "POW", "research_status": "available", "semantic_sha256": "new"}]}
        result = build_v2(previous, current)
        self.assertEqual(len(result["events"]), 1)
        event = result["events"][0]
        self.assertEqual((event["family"], event["previous"], event["current"]), ("research_availability_established", "unknown", "available"))
        self.assertNotIn("blocked", str(event))
        self.assertEqual(build_v2(previous, current), result)

    def test_v2_unknown_without_availability_is_no_change(self):
        snapshot = {"schema_version": "2.0.0", "snapshot_id": "qrs2-same", "tickers": [{"ticker": "QNS", "research_status": "unknown"}]}
        self.assertEqual(build_v2(snapshot, snapshot)["status"], "NO_CHANGE")


if __name__ == "__main__": unittest.main()
