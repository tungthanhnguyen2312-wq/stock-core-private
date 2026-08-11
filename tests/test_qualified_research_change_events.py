import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qualified_research_change_events import build, build_v2
from qualified_research_snapshot_v2 import SCHEMA_VERSION, build as build_snapshot_v2
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

    def test_v2_unavailable_to_available_uses_the_real_previous_status(self):
        """A served baseline that actually evaluated and recorded `unavailable` (checked, no
        brief attached) must not be reported as `unknown` (never checked) — that would invent
        history the served artifact does not support."""
        previous = {"schema_version": "2.0.0", "snapshot_id": "qrs2-served",
                    "tickers": [{"ticker": "HPG", "research_status": "unavailable", "semantic_sha256": "old"}]}
        current = {"schema_version": "2.0.0", "snapshot_id": "qrs2-current",
                   "tickers": [{"ticker": "HPG", "research_status": "available", "semantic_sha256": "new"}]}
        result = build_v2(previous, current)
        self.assertEqual(len(result["events"]), 1)
        event = result["events"][0]
        self.assertEqual((event["family"], event["previous"], event["current"]),
                         ("research_availability_established", "unavailable", "available"))

    def test_v2_available_to_available_emits_no_new_establishment_event(self):
        """POW carried forward as already-available must not re-fire just because the
        destination snapshot identity changed (e.g. because other tickers changed alongside it)."""
        previous = {"schema_version": "2.0.0", "snapshot_id": "qrs2-served",
                    "tickers": [{"ticker": "POW", "research_status": "available", "semantic_sha256": "same"}]}
        current = {"schema_version": "2.0.0", "snapshot_id": "qrs2-current",
                   "tickers": [{"ticker": "POW", "research_status": "available", "semantic_sha256": "same"}]}
        self.assertEqual(build_v2(previous, current)["status"], "NO_CHANGE")

    def test_v2_mixed_cohort_emits_exactly_the_truthful_transitions(self):
        """Regression proof for the real corrective-release shape: an already-available ticker
        must not re-fire, an untouched not-yet-available ticker must stay silent, and each
        genuinely newly-available ticker gets exactly one truthfully-labeled event."""
        previous = {"schema_version": "2.0.0", "snapshot_id": "qrs2-served", "tickers": [
            {"ticker": "POW", "research_status": "available", "semantic_sha256": "p0"},
            {"ticker": "HPG", "research_status": "unavailable", "semantic_sha256": "h0"},
            {"ticker": "VNM", "research_status": "unavailable", "semantic_sha256": "v0"},
            {"ticker": "SSI", "research_status": "unavailable", "semantic_sha256": "s0"},
        ]}
        current = {"schema_version": "2.0.0", "snapshot_id": "qrs2-current", "tickers": [
            {"ticker": "POW", "research_status": "available", "semantic_sha256": "p0"},
            {"ticker": "HPG", "research_status": "available", "semantic_sha256": "h1"},
            {"ticker": "VNM", "research_status": "available", "semantic_sha256": "v1"},
            {"ticker": "SSI", "research_status": "unavailable", "semantic_sha256": "s0"},
        ]}
        result = build_v2(previous, current)
        self.assertEqual(sorted(event["ticker"] for event in result["events"]), ["HPG", "VNM"])
        for event in result["events"]:
            self.assertEqual(event["previous"], "unavailable")
            self.assertEqual(event["current"], "available")
        self.assertEqual(len({event["event_id"] for event in result["events"]}), 2)

    def test_v2_ticker_missing_from_previous_snapshot_is_treated_as_unknown(self):
        """Missing capability authority in the baseline itself remains `unknown`, never a
        guessed `unavailable`."""
        previous = {"schema_version": "2.0.0", "snapshot_id": "qrs2-served", "tickers": []}
        current = {"schema_version": "2.0.0", "snapshot_id": "qrs2-current",
                   "tickers": [{"ticker": "PVD", "research_status": "available", "semantic_sha256": "new"}]}
        result = build_v2(previous, current)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["previous"], "unknown")

    def test_v2_legacy_baseline_remains_event_compatible_with_current_snapshot(self):
        previous = {"schema_version": "2.0.0", "snapshot_id": "qrs2-served",
                    "tickers": [{"ticker": "HPG", "research_status": "unavailable"}]}
        current = build_snapshot_v2(
            {"tickers": {"HPG": {"ticker_capability_matrix": {
                "research": {"qualified_research_brief": {"status": "available"}}}}}},
            source_identity={"reference_session_date": "2026-08-07"},
        )
        result = build_v2(previous, current)
        self.assertEqual(result["snapshot_version"], SCHEMA_VERSION)
        self.assertEqual([(item["ticker"], item["previous"], item["current"])
                          for item in result["events"]], [("HPG", "unavailable", "available")])


if __name__ == "__main__": unittest.main()
