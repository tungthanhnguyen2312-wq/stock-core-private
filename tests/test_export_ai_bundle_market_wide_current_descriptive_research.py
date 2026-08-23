"""Unit tests for attaching market_wide_current_descriptive_research to the AI bundle
(export_ai_bundle.py).

Mirrors tests/test_export_ai_bundle_market_wide_current_liquidity_research.py's opt-in/
fail-closed/verbatim-passthrough convention:
- Opt-in flag --include-market-wide-current-descriptive-research attaches
  `market_wide_current_descriptive_research`; disabled by default, the retained artifact file is
  never even opened.
- An explicit --market-wide-current-descriptive-research-path is required; a missing path,
  nonexistent file, or a hash mismatch against the artifact's own recomputed content_identity()
  fails the whole attach step closed (no key on any ticker).
- Per-ticker technical_features/liquidity/sector_classification are reused verbatim; the
  market-wide denominator/observed-cohort/coverage-ratio and blocked_outputs travel with every
  ticker so coverage disclosure is never lost when a reader looks at a single ticker.
- A stale (not same-session) technical-feature record and a non-EXACT_MATCH liquidity residual
  are preserved exactly, never coerced.
- is_actionable=False unconditionally.
"""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import export_ai_bundle as bundle
from field_temporal_contract import stable_id as p3f9b_stable_id
from market_wide_current_descriptive_research import build_artifact, content_identity
from market_wide_current_liquidity_research import content_identity as liquidity_content_identity

TARGET = "2026-08-21"


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _trading_days(end: str, count: int) -> list[str]:
    d = date.fromisoformat(end)
    days = []
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= timedelta(days=1)
    return list(reversed(days))


def _observations(end: str, count: int, *, start_close: float, step: float) -> list[dict]:
    days = _trading_days(end, count)
    return [{"session": day, "close": start_close + step * i, "volume": 1000 + i} for i, day in enumerate(days)]


def _universe_resolution(records):
    payload = {
        "records": records,
        "current_active_equity_denominator": {"count": 2},
        "observed_session_cohort": {"count": 1},
        "input_candidates": {"resolved_completed_session": TARGET},
    }
    digest = _hash(payload)
    return {**payload, "artifact_sha256": digest, "artifact_identity": f"current_universe_status_and_session_coverage_resolution:{digest}"}


def _p3f9b_snapshot(records):
    payload = {"records": records, "resolved_completed_session": TARGET}
    digest = p3f9b_stable_id(payload)
    return {**payload, "snapshot_sha256": digest, "snapshot_identity": f"p3f9_exact_session_snapshot:{digest}"}


def _liquidity_artifact(records, *, snapshot_identity):
    payload = {
        "records": records, "resolved_completed_session": TARGET,
        "universe": {"canonical_candidate_count": len(records), "source_snapshot_identity": snapshot_identity},
        "coverage": {"disposition_counts": {}}, "authority_boundary": {"QUALIFIED_LIQUIDITY_INPUTS": False},
    }
    return {**payload, **liquidity_content_identity(payload)}


def _build_fixture_artifact() -> dict:
    """RIS1: same-session, full 20-day window, eligible liquidity with an EXACT_MATCH. SHB: same
    shape but a 4-unit residual, mirroring the real 2026-08-23 checkpoint's own SHB record.
    OLD1: INACTIVE_OR_DELISTED, out of current-descriptive scope."""
    ur = {
        "RIS1": {"ticker": "RIS1", "activity_and_session_state": "ACTIVE_LISTED_OBSERVED", "membership_state": "INCLUDED"},
        "SHB": {"ticker": "SHB", "activity_and_session_state": "ACTIVE_LISTED_OBSERVED", "membership_state": "INCLUDED"},
        "OLD1": {"ticker": "OLD1", "activity_and_session_state": "INACTIVE_OR_DELISTED", "membership_state": "UNKNOWN"},
    }
    pf = {
        "RIS1": {"disposition": "EXACT_SESSION_RETAINED", "observations": _observations(TARGET, 20, start_close=10.0, step=0.1)},
        "SHB": {"disposition": "EXACT_SESSION_RETAINED", "observations": _observations(TARGET, 20, start_close=11.0, step=0.05)},
        "OLD1": {"disposition": "PROVIDER_REJECTED", "observations": []},
    }
    p3f9b = _p3f9b_snapshot(pf)
    liq = _liquidity_artifact(
        {
            "RIS1": {"disposition": "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE", "session": TARGET,
                    "board_composition": {"MATCHED_ROUND_LOT": {"active_volume_raw_total": 500.0}},
                    "g1_v_reconciliation": {"verdict": "EXACT_MATCH", "delta": 0.0},
                    "current_ohlc_v": 5000.0, "liquidity_research_contract": {},
                    "value_status": "GROSS_TRADE_AMOUNT_RETAINED_ONLY_NON_AUTHORITATIVE_SCALE_BASIS_UNRESOLVED"},
            "SHB": {"disposition": "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE", "session": TARGET,
                   "board_composition": {"MATCHED_ROUND_LOT": {"active_volume_raw_total": 6961550.0}},
                   "g1_v_reconciliation": {"verdict": "OTHER", "delta": 4.0, "exact_match": False},
                   "current_ohlc_v": 69615504.0, "liquidity_research_contract": {},
                   "value_status": "GROSS_TRADE_AMOUNT_RETAINED_ONLY_NON_AUTHORITATIVE_SCALE_BASIS_UNRESOLVED"},
            "OLD1": {"disposition": "MISSING", "reason": "NO_CURRENT_SESSION_ACTIVE_BOARD"},
        },
        snapshot_identity=p3f9b["snapshot_identity"],
    )
    return build_artifact(
        universe_resolution_artifact=_universe_resolution(ur), p3f9b_snapshot=p3f9b,
        liquidity_artifact=liq, entity_classifications={},
    )


class ExportAiBundleMarketWideCurrentDescriptiveResearchTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.artifact = _build_fixture_artifact()
        self.artifact_path = self.root / "market_wide_current_descriptive_research_artifact.json"
        self.artifact_path.write_text(json.dumps(self.artifact, sort_keys=True), encoding="utf-8")

        tampered = copy.deepcopy(self.artifact)
        tampered["records"]["RIS1"]["activity_and_session_state"] = "ACTIVE_LISTED_OBSERVED_FAKE"
        self.tampered_path = self.root / "tampered_artifact.json"
        self.tampered_path.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")

        self.nonexistent_path = str(self.root / "does_not_exist.json")

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _entries(self) -> dict[str, dict]:
        return {t: {"ticker": t} for t in ("RIS1", "SHB", "OLD1", "ZZZ")}

    # -- opt-in gating ------------------------------------------------------

    def test_disabled_by_default_leaves_bundle_unchanged(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_descriptive_research(
            entries, include=False, artifact_path=str(self.artifact_path)
        )
        for t in entries:
            self.assertNotIn("market_wide_current_descriptive_research", result[t])

    def test_disabled_include_never_opens_the_artifact_file(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_descriptive_research(
            entries, include=False, artifact_path=self.nonexistent_path
        )
        for t in entries:
            self.assertNotIn("market_wide_current_descriptive_research", result[t])

    def test_missing_path_argument_fails_closed(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_descriptive_research(entries, include=True, artifact_path=None)
        for t in entries:
            self.assertNotIn("market_wide_current_descriptive_research", result[t])

    def test_nonexistent_file_fails_closed_without_raising(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_descriptive_research(
            entries, include=True, artifact_path=self.nonexistent_path
        )
        for t in entries:
            self.assertNotIn("market_wide_current_descriptive_research", result[t])

    def test_tampered_hash_fails_closed_for_every_ticker(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_descriptive_research(
            entries, include=True, artifact_path=str(self.tampered_path)
        )
        for t in entries:
            self.assertNotIn("market_wide_current_descriptive_research", result[t])

    # -- verbatim passthrough -------------------------------------------------

    def test_same_session_ticker_attaches_available_with_coverage(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_descriptive_research(
            entries, include=True, artifact_path=str(self.artifact_path)
        )
        record = result["RIS1"]["market_wide_current_descriptive_research"]
        self.assertEqual("available", record["status"])
        self.assertFalse(record["is_actionable"])
        self.assertTrue(record["technical_features"]["is_current_session"])
        self.assertEqual(TARGET, record["session"])
        self.assertEqual(2, record["market_coverage"]["current_active_equity_denominator"])
        self.assertEqual(1, record["market_coverage"]["observed_session_cohort"])
        self.assertIn("quality_state", record["market_coverage"])
        self.assertIn("blocked_outputs", record)
        self.assertEqual("RANKING_PROHIBITED", record["blocked_outputs"]["stock_rankings"])

    def test_shb_style_residual_preserved_verbatim_never_coerced(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_descriptive_research(
            entries, include=True, artifact_path=str(self.artifact_path)
        )
        record = result["SHB"]["market_wide_current_descriptive_research"]
        verdict = record["liquidity"]["g1_v_reconciliation"]["verdict"]
        self.assertEqual("OTHER", verdict)
        self.assertEqual(4.0, record["liquidity"]["g1_v_reconciliation"]["delta"])
        self.assertEqual("available", record["status"])

    def test_delisted_ticker_attaches_not_available_out_of_scope(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_descriptive_research(
            entries, include=True, artifact_path=str(self.artifact_path)
        )
        record = result["OLD1"]["market_wide_current_descriptive_research"]
        self.assertEqual("not_available", record["status"])
        self.assertFalse(record["in_current_descriptive_scope"])
        self.assertEqual("NOT_APPLICABLE", record["technical_features"]["status"])
        self.assertEqual("NOT_APPLICABLE", record["liquidity"]["status"])

    def test_ticker_absent_from_artifact_universe_gets_no_key(self) -> None:
        entries = self._entries()
        result = bundle.attach_market_wide_current_descriptive_research(
            entries, include=True, artifact_path=str(self.artifact_path)
        )
        self.assertNotIn("market_wide_current_descriptive_research", result["ZZZ"])

    def test_no_ranking_recommendation_or_sizing_field_anywhere(self) -> None:
        """Checks the data payload (technical_features/liquidity), not the deliberate
        blocked_outputs guardrail vocabulary, which legitimately names
        "probabilities_or_target_prices" as a key it prohibits."""
        entries = self._entries()
        result = bundle.attach_market_wide_current_descriptive_research(
            entries, include=True, artifact_path=str(self.artifact_path)
        )
        record = result["RIS1"]["market_wide_current_descriptive_research"]
        payload = json.dumps({"technical_features": record["technical_features"], "liquidity": record["liquidity"]})
        for forbidden in ("recommendation_score", "target_price", "buy_signal", "sell_signal", "position_size"):
            self.assertNotIn(forbidden, payload)

    def test_other_bundle_fields_unaffected(self) -> None:
        entries = {"RIS1": {"ticker": "RIS1", "research_financial_fact_projection": {"research_eligible": True}}}
        before = copy.deepcopy(entries["RIS1"]["research_financial_fact_projection"])
        result = bundle.attach_market_wide_current_descriptive_research(
            entries, include=True, artifact_path=str(self.artifact_path)
        )
        self.assertEqual(before, result["RIS1"]["research_financial_fact_projection"])

    def test_repeated_build_is_deterministic(self) -> None:
        entries1, entries2 = self._entries(), self._entries()
        res1 = bundle.attach_market_wide_current_descriptive_research(entries1, include=True, artifact_path=str(self.artifact_path))
        res2 = bundle.attach_market_wide_current_descriptive_research(entries2, include=True, artifact_path=str(self.artifact_path))
        json1 = json.dumps(res1["RIS1"]["market_wide_current_descriptive_research"], sort_keys=True)
        json2 = json.dumps(res2["RIS1"]["market_wide_current_descriptive_research"], sort_keys=True)
        self.assertEqual(json1, json2)

    # -- loader unit tests -----------------------------------------------------

    def test_loader_returns_none_for_nonexistent_file(self) -> None:
        self.assertIsNone(bundle.load_market_wide_current_descriptive_research_artifact(Path(self.nonexistent_path)))

    def test_loader_returns_none_for_tampered_hash(self) -> None:
        self.assertIsNone(bundle.load_market_wide_current_descriptive_research_artifact(self.tampered_path))

    def test_loader_returns_artifact_when_hash_verifies(self) -> None:
        loaded = bundle.load_market_wide_current_descriptive_research_artifact(self.artifact_path)
        self.assertIsNotNone(loaded)
        self.assertEqual(self.artifact["artifact_sha256"], loaded["artifact_sha256"])

    def test_fixture_artifact_self_verifies(self) -> None:
        recomputed = content_identity(self.artifact)
        self.assertEqual(recomputed["artifact_sha256"], self.artifact["artifact_sha256"])


if __name__ == "__main__":
    unittest.main()
