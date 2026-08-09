import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qualified_research_change_events import build
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


if __name__ == "__main__": unittest.main()
