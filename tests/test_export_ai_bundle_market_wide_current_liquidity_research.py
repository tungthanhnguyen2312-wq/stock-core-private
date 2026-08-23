"""Unit tests for attaching market_wide_current_liquidity_research to the AI bundle
(export_ai_bundle.py).

Verifies the evidence-bounded attachment contract:
- Opt-in flag --include-market-wide-current-liquidity-research attaches
  `market_wide_current_liquidity_research`; disabled by default, the retained artifact file is
  never even opened.
- An explicit --market-wide-current-liquidity-research-path is required; a missing path,
  nonexistent file, or a hash mismatch against the artifact's own recomputed content_identity()
  fails the whole attach step closed (no key on any ticker) rather than degrading partially.
- Per-ticker fields (disposition, board_composition, g1_v_reconciliation, current_ohlc_v,
  liquidity_research_contract, value_status) are reused verbatim -- never recalculated.
- A non-EXACT_MATCH g1_v_reconciliation verdict (the SHB-style residual) is preserved exactly,
  never coerced toward EXACT_MATCH.
- A ticker missing/incomplete/provider-rejected in the retained artifact still gets an explicit
  key with that disposition; a ticker absent from the artifact's universe altogether gets no key.
- is_actionable=False unconditionally; no ADV/ADTV/turnover/liquidity/sizing field is invented.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import export_ai_bundle as bundle
from market_wide_current_liquidity_research import build_artifact, content_identity


def _eligible_trade(volume: int) -> dict:
    return {"ok": True, "body": {"trades": [
        {"boardId": "G1", "time": "2026-08-21 14:59:00", "matchPrice": 1, "matchQtty": 1,
         "avgPrice": 1, "totalVolumeTraded": volume, "grossTradeAmount": 1},
    ]}}


def _ohlc(v: float) -> dict:
    return {"ok": True, "body": {"t": [1787328000], "v": [v]}}


def _build_fixture_artifact() -> dict:
    """AAA: exact 10xG1==v match. SHB: same shape but a 4-unit residual, mirroring the real
    2026-08-23 checkpoint's own SHB record. BBB: no trade/ohlc supplied at all -> MISSING.
    CCC: provider explicitly rejected the request."""
    return build_artifact(
        candidates=["AAA", "SHB", "BBB", "CCC"],
        trades={
            "AAA": _eligible_trade(10),
            "SHB": _eligible_trade(10),
            "CCC": {"ok": False, "disposition": "PROVIDER_REJECTED", "reason": "TEST_REJECTED"},
        },
        ohlc={
            "AAA": _ohlc(100),
            "SHB": _ohlc(104),
        },
        requested_at="SESSION_BOUND:2026-08-21",
    )


class ExportAiBundleMarketWideCurrentLiquidityResearchTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.artifact = _build_fixture_artifact()
        self.artifact_path = self.root / "market_wide_current_liquidity_research_artifact.json"
        self.artifact_path.write_text(json.dumps(self.artifact, sort_keys=True), encoding="utf-8")

        # Same content, one nested field flipped after the hash was already stamped -- must fail
        # the whole attach step closed rather than silently attaching the tampered copy.
        tampered = copy.deepcopy(self.artifact)
        tampered["records"]["AAA"]["disposition"] = "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE_FAKE"
        self.tampered_path = self.root / "tampered_artifact.json"
        self.tampered_path.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")

        self.nonexistent_path = str(self.root / "does_not_exist.json")

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _entries(self) -> dict[str, dict]:
        return {t: {"ticker": t} for t in ("AAA", "SHB", "BBB", "CCC", "ZZZ")}

    # -- opt-in gating ------------------------------------------------------

    def test_disabled_by_default_leaves_bundle_unchanged(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_liquidity_research(
            entries, include=False, artifact_path=str(self.artifact_path)
        )
        for t in entries:
            self.assertNotIn("market_wide_current_liquidity_research", result[t])

    def test_disabled_include_never_opens_the_artifact_file(self) -> None:
        entries = self._entries()
        # A path that does not exist would raise on read; include=False must never get there.
        result = bundle.attach_market_wide_current_liquidity_research(
            entries, include=False, artifact_path=self.nonexistent_path
        )
        for t in entries:
            self.assertNotIn("market_wide_current_liquidity_research", result[t])

    def test_missing_path_argument_fails_closed(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_liquidity_research(
            entries, include=True, artifact_path=None
        )
        for t in entries:
            self.assertNotIn("market_wide_current_liquidity_research", result[t])

    def test_nonexistent_file_fails_closed_without_raising(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_liquidity_research(
            entries, include=True, artifact_path=self.nonexistent_path
        )
        for t in entries:
            self.assertNotIn("market_wide_current_liquidity_research", result[t])

    def test_tampered_hash_fails_closed_for_every_ticker(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_liquidity_research(
            entries, include=True, artifact_path=str(self.tampered_path)
        )
        for t in entries:
            self.assertNotIn("market_wide_current_liquidity_research", result[t])

    # -- verbatim passthrough -------------------------------------------------

    def test_eligible_ticker_attaches_available_with_exact_match(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_liquidity_research(
            entries, include=True, artifact_path=str(self.artifact_path)
        )
        record = result["AAA"]["market_wide_current_liquidity_research"]
        self.assertEqual("available", record["status"])
        self.assertEqual("CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE", record["disposition"])
        self.assertEqual("EXACT_MATCH", record["reconciliation_verdict"])
        self.assertEqual("EXACT_MATCH", record["g1_v_reconciliation"]["verdict"])
        self.assertFalse(record["is_actionable"])
        self.assertIn("board_composition", record)
        self.assertIn("liquidity_research_contract", record)
        self.assertEqual(
            "ELIGIBLE", record["liquidity_research_contract"]["CURRENT_SESSION_LIQUIDITY_RESEARCH"]["state"],
        )
        self.assertEqual("BLOCKED", record["liquidity_research_contract"]["POSITION_SIZING"]["state"])

    def test_shb_style_residual_preserved_verbatim_never_coerced(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_liquidity_research(
            entries, include=True, artifact_path=str(self.artifact_path)
        )
        record = result["SHB"]["market_wide_current_liquidity_research"]
        source_verdict = self.artifact["records"]["SHB"]["g1_v_reconciliation"]["verdict"]
        self.assertNotEqual("EXACT_MATCH", source_verdict, "fixture must exercise a real residual")
        self.assertEqual(source_verdict, record["reconciliation_verdict"])
        self.assertEqual(source_verdict, record["g1_v_reconciliation"]["verdict"])
        self.assertEqual(4.0, record["g1_v_reconciliation"]["delta"])
        self.assertFalse(record["g1_v_reconciliation"]["exact_match"])
        # Still descriptive-eligible: a reconciliation residual is a warning, not a rejection.
        self.assertEqual("CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE", record["disposition"])

    def test_missing_disposition_ticker_attaches_not_available(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_liquidity_research(
            entries, include=True, artifact_path=str(self.artifact_path)
        )
        record = result["BBB"]["market_wide_current_liquidity_research"]
        self.assertEqual("MISSING", record["disposition"])
        self.assertEqual("not_available", record["status"])
        self.assertFalse(record["is_actionable"])
        self.assertIsNone(record["reconciliation_verdict"])
        self.assertNotIn("board_composition", record)

    def test_provider_rejected_disposition_preserved(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_liquidity_research(
            entries, include=True, artifact_path=str(self.artifact_path)
        )
        record = result["CCC"]["market_wide_current_liquidity_research"]
        self.assertEqual("PROVIDER_REJECTED", record["disposition"])
        self.assertEqual("not_available", record["status"])
        self.assertEqual("TEST_REJECTED", record["reason"])

    def test_ticker_absent_from_artifact_universe_gets_no_key(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_liquidity_research(
            entries, include=True, artifact_path=str(self.artifact_path)
        )
        self.assertNotIn("market_wide_current_liquidity_research", result["ZZZ"])

    def test_value_status_never_promoted_and_no_derived_value_field(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_liquidity_research(
            entries, include=True, artifact_path=str(self.artifact_path)
        )
        record = result["AAA"]["market_wide_current_liquidity_research"]
        self.assertEqual(
            "GROSS_TRADE_AMOUNT_RETAINED_ONLY_NON_AUTHORITATIVE_SCALE_BASIS_UNRESOLVED",
            record["value_status"],
        )
        for forbidden in ("traded_value", "turnover", "adtv", "adv", "position_size"):
            self.assertNotIn(forbidden, record)

    def test_other_bundle_fields_unaffected(self) -> None:
        entries = {
            "AAA": {
                "ticker": "AAA",
                "research_financial_fact_projection": {"research_eligible": True},
            }
        }
        before = copy.deepcopy(entries["AAA"]["research_financial_fact_projection"])
        result = bundle.attach_market_wide_current_liquidity_research(
            entries, include=True, artifact_path=str(self.artifact_path)
        )
        self.assertEqual(before, result["AAA"]["research_financial_fact_projection"])

    def test_repeated_build_is_deterministic(self) -> None:
        entries1 = self._entries()
        entries2 = self._entries()
        res1 = bundle.attach_market_wide_current_liquidity_research(
            entries1, include=True, artifact_path=str(self.artifact_path)
        )
        res2 = bundle.attach_market_wide_current_liquidity_research(
            entries2, include=True, artifact_path=str(self.artifact_path)
        )
        json1 = json.dumps(res1["AAA"]["market_wide_current_liquidity_research"], sort_keys=True)
        json2 = json.dumps(res2["AAA"]["market_wide_current_liquidity_research"], sort_keys=True)
        self.assertEqual(json1, json2)

    # -- loader unit tests -----------------------------------------------------

    def test_loader_returns_none_for_nonexistent_file(self) -> None:
        self.assertIsNone(
            bundle.load_market_wide_current_liquidity_research_artifact(Path(self.nonexistent_path))
        )

    def test_loader_returns_none_for_tampered_hash(self) -> None:
        self.assertIsNone(
            bundle.load_market_wide_current_liquidity_research_artifact(self.tampered_path)
        )

    def test_loader_returns_artifact_when_hash_verifies(self) -> None:
        loaded = bundle.load_market_wide_current_liquidity_research_artifact(self.artifact_path)
        self.assertIsNotNone(loaded)
        self.assertEqual(self.artifact["artifact_sha256"], loaded["artifact_sha256"])

    def test_fixture_artifact_self_verifies(self) -> None:
        """Guards the test fixture itself against silently drifting out of sync with
        content_identity() -- if this ever fails, the fixture (not the production code) is
        the thing to fix."""
        recomputed = content_identity(self.artifact)
        self.assertEqual(recomputed["artifact_sha256"], self.artifact["artifact_sha256"])


if __name__ == "__main__":
    unittest.main()
