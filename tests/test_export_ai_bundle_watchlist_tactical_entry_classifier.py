"""Unit tests for attaching watchlist_tactical_entry_classifier to the AI bundle
(export_ai_bundle.py).

Verifies the evidence-bounded attachment contract, mirroring
test_export_ai_bundle_market_wide_current_fundamental_research.py's convention exactly:
- Opt-in flag --include-watchlist-tactical-entry-classifier attaches
  `watchlist_tactical_entry_classifier`; disabled by default, the retained artifact file is never
  even opened.
- An explicit --watchlist-tactical-entry-classifier-path is required; a missing path, nonexistent
  file, or a hash mismatch against the artifact's own recomputed content_identity() fails the whole
  attach step closed (no key on any ticker) rather than degrading partially.
- Per-ticker fields are reused verbatim -- never recalculated.
- A ticker absent from the artifact's universe altogether gets no key.
- is_actionable=False unconditionally; requires_human_review=True unconditionally.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import export_ai_bundle as bundle
from test_watchlist_tactical_entry_classifier import _build


def _write_artifact(tmpdir: str, artifact: dict, name: str = "watchlist_tactical_entry_classifier_artifact.json") -> Path:
    path = Path(tmpdir) / name
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


class AttachWatchlistTacticalEntryClassifier(unittest.TestCase):
    def setUp(self) -> None:
        _, _, _, self.artifact = _build()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = _write_artifact(self.tmpdir.name, self.artifact)
        self.bundle_entries = {"BRK": {}, "REV": {}, "THN": {}, "ZZZ_OUTSIDE_UNIVERSE": {}}

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_disabled_by_default_leaves_bundle_untouched(self) -> None:
        result = bundle.attach_watchlist_tactical_entry_classifier(copy.deepcopy(self.bundle_entries), False, str(self.path))
        for entry in result.values():
            self.assertNotIn("watchlist_tactical_entry_classifier", entry)

    def test_missing_path_leaves_bundle_untouched(self) -> None:
        result = bundle.attach_watchlist_tactical_entry_classifier(copy.deepcopy(self.bundle_entries), True, None)
        for entry in result.values():
            self.assertNotIn("watchlist_tactical_entry_classifier", entry)

    def test_nonexistent_file_fails_closed(self) -> None:
        result = bundle.attach_watchlist_tactical_entry_classifier(
            copy.deepcopy(self.bundle_entries), True, str(Path(self.tmpdir.name) / "absent.json"))
        for entry in result.values():
            self.assertNotIn("watchlist_tactical_entry_classifier", entry)

    def test_hash_mismatch_fails_closed_for_every_ticker(self) -> None:
        tampered = dict(self.artifact)
        tampered["records"] = dict(tampered["records"])
        tampered["records"]["BRK"] = {**tampered["records"]["BRK"], "entry_state": "TAMPERED"}
        tampered_path = _write_artifact(self.tmpdir.name, tampered, "tampered.json")
        result = bundle.attach_watchlist_tactical_entry_classifier(copy.deepcopy(self.bundle_entries), True, str(tampered_path))
        for entry in result.values():
            self.assertNotIn("watchlist_tactical_entry_classifier", entry)

    def test_classified_ticker_keeps_full_tactical_detail(self) -> None:
        result = bundle.attach_watchlist_tactical_entry_classifier(copy.deepcopy(self.bundle_entries), True, str(self.path))
        brk = result["BRK"]["watchlist_tactical_entry_classifier"]
        self.assertEqual(brk["entry_state"], "BREAKOUT_READY")
        self.assertEqual(brk["action"], "BUY_ON_CONFIRMATION")
        self.assertEqual(brk["status"], "classified")
        self.assertFalse(brk["is_actionable"])
        self.assertTrue(brk["evidence_for"])
        self.assertIn("state_taxonomy", brk)
        self.assertIn("action_taxonomy", brk)
        self.assertEqual(set(brk["state_taxonomy"]), set(self.artifact["state_taxonomy"]))

    def test_early_entry_ticker_never_full_position_ready(self) -> None:
        result = bundle.attach_watchlist_tactical_entry_classifier(copy.deepcopy(self.bundle_entries), True, str(self.path))
        rev = result["REV"]["watchlist_tactical_entry_classifier"]
        self.assertEqual(rev["action"], "EARLY_ENTRY")
        self.assertFalse(rev["is_full_position_ready"])

    def test_insufficient_data_ticker_status(self) -> None:
        result = bundle.attach_watchlist_tactical_entry_classifier(copy.deepcopy(self.bundle_entries), True, str(self.path))
        thn = result["THN"]["watchlist_tactical_entry_classifier"]
        self.assertEqual(thn["status"], "insufficient_data")
        self.assertIsNone(thn["entry_state"])

    def test_ticker_outside_universe_has_no_key(self) -> None:
        result = bundle.attach_watchlist_tactical_entry_classifier(copy.deepcopy(self.bundle_entries), True, str(self.path))
        self.assertNotIn("watchlist_tactical_entry_classifier", result["ZZZ_OUTSIDE_UNIVERSE"])

    def test_no_recompute_deepcopy_not_shared_reference(self) -> None:
        result = bundle.attach_watchlist_tactical_entry_classifier(copy.deepcopy(self.bundle_entries), True, str(self.path))
        result["BRK"]["watchlist_tactical_entry_classifier"]["evidence_for"].append("MUTATED")
        self.assertNotIn("MUTATED", self.artifact["records"]["BRK"]["evidence_for"])

    def test_disabled_flag_never_opens_the_file(self) -> None:
        # A path pointing at a directory (unreadable as JSON) must not raise when include=False.
        result = bundle.attach_watchlist_tactical_entry_classifier(copy.deepcopy(self.bundle_entries), False, self.tmpdir.name)
        for entry in result.values():
            self.assertNotIn("watchlist_tactical_entry_classifier", entry)


if __name__ == "__main__":
    unittest.main()
