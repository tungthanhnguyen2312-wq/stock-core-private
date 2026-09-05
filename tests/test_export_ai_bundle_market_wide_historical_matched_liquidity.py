"""Fail-closed AI-bundle pass-through for historical matched-liquidity evidence."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import export_ai_bundle as bundle
from market_wide_historical_matched_liquidity import build_artifact, content_identity


def _artifact() -> dict:
    # The retained history intentionally has no target-session entry.  The bundle
    # must preserve that evidence boundary rather than manufacturing readiness.
    return build_artifact(
        target_session="2026-09-04",
        universe={"AAA": {"exchange_or_market": "HOSE"}, "BBB": {"exchange_or_market": "HNX"}},
        calendar=["2026-08-11"],
        daily_cells={},
        source_identities={"canonical_trades_manifest": "sha256:test"},
    )


class ExportAiBundleHistoricalMatchedLiquidityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "historical_matched_liquidity.json"
        self.payload = _artifact()
        self.path.write_text(json.dumps(self.payload, sort_keys=True), encoding="utf-8")
        tampered = copy.deepcopy(self.payload)
        tampered["records"]["AAA"]["liquidity_state"] = "FABRICATED_READY"
        self.tampered = Path(self.tmp.name) / "tampered.json"
        self.tampered.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def _entries() -> dict[str, dict]:
        return {ticker: {"ticker": ticker} for ticker in ("AAA", "BBB", "ZZZ")}

    def test_disabled_or_missing_artifact_path_leaves_entries_untouched(self) -> None:
        for include, path in ((False, str(self.path)), (True, None)):
            result = bundle.attach_market_wide_historical_matched_liquidity(self._entries(), include, path)
            for entry in result.values():
                self.assertNotIn("market_wide_historical_matched_liquidity", entry)

    def test_tampered_artifact_fails_closed_for_all_tickers(self) -> None:
        result = bundle.attach_market_wide_historical_matched_liquidity(
            self._entries(), True, str(self.tampered)
        )
        for entry in result.values():
            self.assertNotIn("market_wide_historical_matched_liquidity", entry)

    def test_verified_context_is_preserved_and_never_actionable(self) -> None:
        result = bundle.attach_market_wide_historical_matched_liquidity(
            self._entries(), True, str(self.path)
        )
        attached = result["AAA"]["market_wide_historical_matched_liquidity"]
        self.assertEqual(self.payload["records"]["AAA"]["features"], attached["features"])
        self.assertEqual("INCOMPLETE_TRADES_HISTORY", attached["liquidity_state"])
        self.assertEqual("not_available", attached["status"])
        self.assertFalse(attached["is_actionable"])
        self.assertFalse(attached["position_sizing_eligible"])
        self.assertEqual(self.payload["artifact_identity"], attached["source_artifact_identity"])
        self.assertNotIn("position_size", attached)
        self.assertNotIn("participation_cap", attached)
        self.assertNotIn("market_wide_historical_matched_liquidity", result["ZZZ"])

    def test_loader_verifies_its_own_identity(self) -> None:
        self.assertEqual(
            content_identity(self.payload)["artifact_sha256"], self.payload["artifact_sha256"]
        )
        self.assertIsNotNone(bundle.load_market_wide_historical_matched_liquidity_artifact(self.path))
        self.assertIsNone(bundle.load_market_wide_historical_matched_liquidity_artifact(self.tampered))


if __name__ == "__main__":
    unittest.main()
