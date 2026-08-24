"""Opt-in attach tests for market_wide_historical_research_context."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import export_ai_bundle as bundle

from tests.test_market_wide_historical_research_context import (
    TARGET,
    _bars,
    _rising,
    _ur,
    p3f9b_snapshot,
    universe_resolution,
)
from market_wide_historical_research_context import FORBIDDEN_PAYLOAD_TOKENS, build_artifact


class ExportAiBundleMarketWideHistoricalResearchContextTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        ur = {
            "RIS1": _ur("RIS1"),
            "THIN1": _ur("THIN1"),
            "OLD1": _ur("OLD1", "INACTIVE_OR_DELISTED"),
        }
        pf = {
            "RIS1": {"disposition": "EXACT_SESSION_RETAINED", "observations": _bars(TARGET, _rising(28))},
            "THIN1": {"disposition": "EXACT_SESSION_RETAINED", "observations": _bars(TARGET, _rising(5))},
            "OLD1": {"disposition": "PROVIDER_REJECTED", "observations": []},
        }
        self.artifact = build_artifact(
            universe_resolution_artifact=universe_resolution(ur, denominator=2, observed=2),
            p3f9b_snapshot=p3f9b_snapshot(pf),
        )
        self.artifact_path = self.root / "market_wide_historical_research_context_artifact.json"
        self.artifact_path.write_text(json.dumps(self.artifact, sort_keys=True), encoding="utf-8")
        tampered = copy.deepcopy(self.artifact)
        tampered["records"]["RIS1"]["context_status"] = "AVAILABLE_FAKE"
        self.tampered_path = self.root / "tampered_artifact.json"
        self.tampered_path.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")
        self.nonexistent_path = str(self.root / "does_not_exist.json")

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _entries(self) -> dict[str, dict]:
        return {ticker: {"ticker": ticker} for ticker in ("RIS1", "THIN1", "OLD1", "ZZZ")}

    def test_disabled_by_default_leaves_bundle_unchanged(self) -> None:
        result = bundle.attach_market_wide_historical_research_context(
            self._entries(), include=False, artifact_path=str(self.artifact_path)
        )
        for ticker in result:
            self.assertNotIn("market_wide_historical_research_context", result[ticker])

    def test_disabled_include_never_opens_the_artifact_file(self) -> None:
        result = bundle.attach_market_wide_historical_research_context(
            self._entries(), include=False, artifact_path=self.nonexistent_path
        )
        for ticker in result:
            self.assertNotIn("market_wide_historical_research_context", result[ticker])

    def test_missing_path_fails_closed(self) -> None:
        result = bundle.attach_market_wide_historical_research_context(
            self._entries(), include=True, artifact_path=None
        )
        for ticker in result:
            self.assertNotIn("market_wide_historical_research_context", result[ticker])

    def test_nonexistent_file_fails_closed_without_raising(self) -> None:
        result = bundle.attach_market_wide_historical_research_context(
            self._entries(), include=True, artifact_path=self.nonexistent_path
        )
        for ticker in result:
            self.assertNotIn("market_wide_historical_research_context", result[ticker])

    def test_tampered_hash_fails_closed_for_every_ticker(self) -> None:
        result = bundle.attach_market_wide_historical_research_context(
            self._entries(), include=True, artifact_path=str(self.tampered_path)
        )
        for ticker in result:
            self.assertNotIn("market_wide_historical_research_context", result[ticker])

    def test_same_session_ticker_attaches_available_context(self) -> None:
        result = bundle.attach_market_wide_historical_research_context(
            self._entries(), include=True, artifact_path=str(self.artifact_path)
        )
        record = result["RIS1"]["market_wide_historical_research_context"]
        self.assertEqual("available", record["status"])
        self.assertFalse(record["is_actionable"])
        self.assertEqual(TARGET, record["session"])
        self.assertEqual("TREND_CONTINUATION", record["structural_state"]["value"])
        self.assertEqual("ADJUSTED_RETROSPECTIVE", record["history"]["price_basis"])
        self.assertEqual("NOT_PROMOTED", record["history"]["raw_as_traded"])
        self.assertFalse(record["history"]["historical_pit_eligible"])
        self.assertEqual("BLOCKED", record["cross_sectional_historical_comparison"]["status"])
        self.assertEqual("NOT_PROMOTED", record["authority_boundary"]["RAW_AS_TRADED"])
        self.assertEqual("BLOCKED", record["authority_boundary"]["PIT"])
        self.assertNotIn("research_priority", record)
        self.assertNotIn("entry_action", record)
        self.assertNotIn("eligible_strategy_ids", record)

    def test_short_history_attaches_insufficient_not_synthetic(self) -> None:
        result = bundle.attach_market_wide_historical_research_context(
            self._entries(), include=True, artifact_path=str(self.artifact_path)
        )
        record = result["THIN1"]["market_wide_historical_research_context"]
        self.assertEqual("available", record["status"])
        self.assertEqual("INSUFFICIENT_HISTORY", record["context_status"])
        self.assertIsNone(record["trailing_range"]["value"])

    def test_delisted_ticker_attaches_not_available(self) -> None:
        result = bundle.attach_market_wide_historical_research_context(
            self._entries(), include=True, artifact_path=str(self.artifact_path)
        )
        record = result["OLD1"]["market_wide_historical_research_context"]
        self.assertEqual("not_available", record["status"])
        self.assertFalse(record["in_current_descriptive_scope"])
        self.assertEqual("NOT_APPLICABLE", record["context_status"])

    def test_ticker_absent_from_artifact_universe_gets_no_key(self) -> None:
        result = bundle.attach_market_wide_historical_research_context(
            self._entries(), include=True, artifact_path=str(self.artifact_path)
        )
        self.assertNotIn("market_wide_historical_research_context", result["ZZZ"])

    def test_no_historical_performance_or_authority_fields(self) -> None:
        result = bundle.attach_market_wide_historical_research_context(
            self._entries(), include=True, artifact_path=str(self.artifact_path)
        )
        record = result["RIS1"]["market_wide_historical_research_context"]
        payload = json.dumps({
            "trailing_range": record["trailing_range"],
            "drawdown": record["drawdown"],
            "structural_state": record["structural_state"],
            "history": record["history"],
        })
        for token in FORBIDDEN_PAYLOAD_TOKENS:
            self.assertNotIn(token, payload)
        self.assertNotIn("RAW_AS_TRADED", record["history"]["price_basis"])

    def test_other_bundle_fields_unaffected(self) -> None:
        entries = {"RIS1": {"ticker": "RIS1", "research_priority": "PRIORITY_NOW", "entry_action": "WAIT"}}
        result = bundle.attach_market_wide_historical_research_context(
            entries, include=True, artifact_path=str(self.artifact_path)
        )
        self.assertEqual("PRIORITY_NOW", result["RIS1"]["research_priority"])
        self.assertEqual("WAIT", result["RIS1"]["entry_action"])

    def test_repeated_attach_is_deterministic(self) -> None:
        first = bundle.attach_market_wide_historical_research_context(
            self._entries(), include=True, artifact_path=str(self.artifact_path)
        )
        second = bundle.attach_market_wide_historical_research_context(
            self._entries(), include=True, artifact_path=str(self.artifact_path)
        )
        self.assertEqual(
            json.dumps(first["RIS1"]["market_wide_historical_research_context"], sort_keys=True),
            json.dumps(second["RIS1"]["market_wide_historical_research_context"], sort_keys=True),
        )


if __name__ == "__main__":
    unittest.main()
