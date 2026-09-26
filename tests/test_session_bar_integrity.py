"""SESSION_BAR_DUPLICATE_INTEGRITY_CORRECTIVE_V1 -- one (ticker, session) uniqueness invariant.

Real evidence: the retained 2026-09-16 P3F9B snapshot carries a second 2026-09-15 DNSE bar for 599
tickers (189 of them non-identical, e.g. AAM 7.79/400 vs 7.39/300) plus pre/post-adjustment copies
of 2026-08-28/09-03/09-04 for VPI and TCH, all from one request with one ``retrieved_at``. Before
this corrective the structural engine and the descriptive features counted both copies, the
historical context kept the last copy, and relative volume refused even identical copies.
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import unittest
from datetime import date, timedelta

import integrated_decision_prospective_feedback as feedback_module
import market_structure_breakout_product_projection as projection_module
import market_wide_current_descriptive_research as descriptive_module
import market_wide_historical_research_context as historical_module
import market_wide_relative_volume_research as rvol_module
import same_session_technical_coverage_disposition as disposition_module
import session_bar_integrity as integrity
import tactical_momentum_context as momentum_module
import technical_structure_context as structure_module
from field_temporal_contract import stable_id
from market_wide_current_liquidity_research import content_identity as liquidity_content_identity

TARGET = "2026-09-16"
BASIS = "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED"
TRANSFORM = "identity_provider_numeric_ohlc/v1"
RETRIEVED_AT = "2026-09-16T17:03:15.613874+07:00"


def _trading_days(end: str, count: int) -> list[str]:
    d = date.fromisoformat(end)
    days: list[str] = []
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= timedelta(days=1)
    return list(reversed(days))


def _bar(session: str, close: float, volume: int = 1000, **extra) -> dict:
    """A P3F9B-shaped DNSE observation (every field the real snapshot retains)."""
    row = {
        "session": session, "open": close, "high": close, "low": close, "close": close, "volume": volume,
        "provider": "DNSE", "dataset": "DNSE_OHLC_1D",
        "field_identity": {"open": "DNSE_OHLC.open", "high": "DNSE_OHLC.high", "low": "DNSE_OHLC.low",
                           "close": "DNSE_OHLC.close", "volume": "DNSE_OHLC.volume"},
        "field_representation": {"open": "DNSE_PROVIDER_NATIVE_RAW", "high": "DNSE_PROVIDER_NATIVE_RAW",
                                 "low": "DNSE_PROVIDER_NATIVE_RAW", "close": "DNSE_PROVIDER_NATIVE_RAW"},
        "transformation_identity": TRANSFORM, "price_unit": "SOURCE_PRICE_UNIT_UNDOCUMENTED",
        "request": {"symbol": "X", "resolution": "1D", "from": 1, "to": 2, "type": "STOCK"},
        "retrieved_at": RETRIEVED_AT, "price_basis": BASIS, "qualification": "CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY",
    }
    row.update(extra)
    return row


def _series(closes, *, end=TARGET, volume_base=1000) -> list[dict]:
    return [_bar(day, close, volume_base + i) for i, (day, close) in enumerate(zip(_trading_days(end, len(closes)), closes))]


def _with_copy_after(observations: list[dict], session: str, **changes) -> list[dict]:
    """Insert a second bar for ``session`` directly after the first -- the real snapshot's layout."""
    out: list[dict] = []
    for row in observations:
        out.append(row)
        if row["session"] == session:
            twin = copy.deepcopy(row)
            twin.update(changes)
            out.append(twin)
    return out


PRIOR = _trading_days(TARGET, 2)[0]  # 2026-09-15
# A zig-zag long enough for swings, a 20-session base and >25 sessions for MA20 slope.
ZIGZAG = [20.0 + (i % 7) * 0.4 - (i % 11) * 0.25 + i * 0.03 for i in range(80)]


class InvariantTests(unittest.TestCase):
    def test_unique_record_is_returned_unchanged_as_the_same_object(self) -> None:
        observations = _series(ZIGZAG[:30])
        record = {"disposition": "EXACT_SESSION_RETAINED", "observations": observations}
        resolved, resolution = integrity.resolve_record(record, as_of_session=TARGET)
        self.assertIs(resolved, record)
        self.assertIs(resolution["observations"], observations)
        self.assertEqual(resolution["status"], integrity.UNIQUE)

    def test_exact_duplicate_collapses_to_one_observation(self) -> None:
        clean = _series(ZIGZAG[:30])
        resolution = integrity.resolve_session_bars(_with_copy_after(clean, PRIOR), as_of_session=TARGET)
        self.assertEqual(resolution["status"], integrity.EXACT_DUPLICATE_COLLAPSED)
        self.assertEqual(resolution["observations"], clean)
        self.assertEqual(resolution["exact_duplicate_sessions"], [PRIOR])
        self.assertEqual(resolution["conflicting_sessions"], [])

    def test_exact_means_every_retained_field_not_only_close(self) -> None:
        clean = _series(ZIGZAG[:30])
        for field, value in (("volume", 999999), ("high", 99.0), ("price_basis", "OTHER_BASIS"),
                             ("transformation_identity", "other/v1"), ("provider", "KBS"),
                             ("retrieved_at", "2026-09-17T16:38:10+07:00"), ("request", {"symbol": "Y"})):
            with self.subTest(field=field):
                resolution = integrity.resolve_session_bars(_with_copy_after(clean, PRIOR, **{field: value}), as_of_session=TARGET)
                self.assertEqual(resolution["status"], integrity.CONFLICTING_DUPLICATE_REFUSED)
                self.assertEqual(resolution["observations"], [])
                self.assertIn(field, resolution["conflicting_fields"][PRIOR])

    def test_conflicting_duplicate_is_refused_never_averaged_or_first_last_wins(self) -> None:
        # AAM, 2026-09-16 snapshot: first 2026-09-15 copy 7.39/7.79/7.39/7.79 vol 400, second 7.39 flat vol 300.
        clean = _series([7.5] * 29 + [7.4])
        first = dict(open=7.39, high=7.79, low=7.39, close=7.79, volume=400)
        second = dict(open=7.39, high=7.39, low=7.39, close=7.39, volume=300)
        observations = []
        for row in clean:
            if row["session"] == PRIOR:
                observations += [{**row, **first}, {**row, **second}]
            else:
                observations.append(row)
        resolution = integrity.resolve_session_bars(observations, as_of_session=TARGET)
        self.assertEqual(resolution["status"], integrity.CONFLICTING_DUPLICATE_REFUSED)
        self.assertEqual(resolution["conflicting_sessions"], [PRIOR])
        self.assertEqual(resolution["conflicting_fields"][PRIOR], ["close", "high", "volume"])
        summary = integrity.integrity_summary(resolution)
        self.assertEqual(summary["reason"], integrity.REFUSAL_REASON)

    def test_no_authority_rule_selects_a_winner_even_with_a_later_retrieval(self) -> None:
        # Recency is not evidence (DECISIONS archive): a later retrieved_at never supersedes.
        clean = _series(ZIGZAG[:30])
        observations = _with_copy_after(clean, PRIOR, close=99.0, retrieved_at="2026-09-17T16:38:10+07:00")
        for ordering in (observations, list(reversed(observations))):
            resolution = integrity.resolve_session_bars(ordering, as_of_session=TARGET)
            self.assertEqual(resolution["status"], integrity.CONFLICTING_DUPLICATE_REFUSED)
            self.assertEqual(resolution["observations"], [])

    def test_result_is_independent_of_input_order(self) -> None:
        base = _with_copy_after(_series(ZIGZAG[:8]), PRIOR)
        canonical = lambda rows: sorted(json.dumps(r, sort_keys=True) for r in rows)  # noqa: E731
        expected = canonical(integrity.resolve_session_bars(base, as_of_session=TARGET)["observations"])
        for permutation in itertools.islice(itertools.permutations(base), 0, 400, 7):
            resolution = integrity.resolve_session_bars(list(permutation), as_of_session=TARGET)
            self.assertEqual(resolution["status"], integrity.EXACT_DUPLICATE_COLLAPSED)
            self.assertEqual(canonical(resolution["observations"]), expected)
        conflicting = _with_copy_after(_series(ZIGZAG[:8]), PRIOR, close=1.0)
        for permutation in itertools.islice(itertools.permutations(conflicting), 0, 400, 7):
            resolution = integrity.resolve_session_bars(list(permutation), as_of_session=TARGET)
            self.assertEqual((resolution["status"], resolution["conflicting_sessions"]),
                             (integrity.CONFLICTING_DUPLICATE_REFUSED, [PRIOR]))

    def test_rows_after_as_of_never_influence_the_decision(self) -> None:
        clean = _series(ZIGZAG[:30])
        future = "2026-09-17"
        observations = clean + [_bar(future, 1.0), _bar(future, 2.0)]
        resolution = integrity.resolve_session_bars(observations, as_of_session=TARGET)
        self.assertEqual(resolution["status"], integrity.UNIQUE)
        self.assertIs(resolution["observations"], observations)

    def test_mixed_basis_for_one_session_is_refused_but_distinct_sessions_are_not_a_duplicate(self) -> None:
        clean = _series(ZIGZAG[:30])
        same_session = _with_copy_after(clean, PRIOR, price_basis="CURRENT_DESCRIPTIVE_NOT_PROMOTED_RAW_AS_TRADED")
        resolution = integrity.resolve_session_bars(same_session, as_of_session=TARGET)
        self.assertEqual(resolution["status"], integrity.CONFLICTING_DUPLICATE_REFUSED)
        self.assertIn("price_basis", resolution["conflicting_fields"][PRIOR])
        across_sessions = [dict(row, price_basis="OTHER") if row["session"] == PRIOR else row for row in clean]
        self.assertEqual(integrity.resolve_session_bars(across_sessions, as_of_session=TARGET)["status"], integrity.UNIQUE)

    def test_non_list_and_malformed_rows_pass_through_to_consumer_handling(self) -> None:
        self.assertEqual(integrity.resolve_session_bars(None)["status"], integrity.UNIQUE)
        rows = [{"close": 1.0}, "junk", _bar(PRIOR, 1.0)]
        self.assertIs(integrity.resolve_session_bars(rows)["observations"], rows)


class SharedBoundaryTests(unittest.TestCase):
    def test_snapshot_record_sources(self) -> None:
        clean = _series(ZIGZAG[:30])
        record, source = structure_module.resolve_target_session_observations(
            pf_record={"observations": clean}, recovery_override=None, target_session=TARGET)
        self.assertEqual(source, "P3F9B_EXACT_SESSION_RECORD")
        record, source = structure_module.resolve_target_session_observations(
            pf_record={"observations": _with_copy_after(clean, PRIOR)}, recovery_override=None, target_session=TARGET)
        self.assertEqual((source, record["observations"]), ("P3F9B_EXACT_SESSION_RECORD", clean))
        self.assertEqual(record["session_bar_integrity"]["status"], integrity.EXACT_DUPLICATE_COLLAPSED)
        record, source = structure_module.resolve_target_session_observations(
            pf_record={"observations": _with_copy_after(clean, PRIOR, close=1.0)}, recovery_override=None, target_session=TARGET)
        self.assertEqual((source, record["observations"]), ("SESSION_BAR_CONFLICT_REFUSED", []))

    def test_recovery_series_is_subject_to_the_same_invariant(self) -> None:
        clean = _series(ZIGZAG[:30])
        pf = {"observations": clean[-5:]}
        conflicting_recovery = {"state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY", "observations": _with_copy_after(clean, PRIOR, close=1.0)}
        record, source = structure_module.resolve_target_session_observations(pf_record=pf, recovery_override=conflicting_recovery, target_session=TARGET)
        self.assertEqual((source, record), ("RECOVERY_REJECTED_SESSION_BAR_CONFLICT", pf))
        exact_recovery = {"state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY", "observations": _with_copy_after(clean, PRIOR)}
        record, source = structure_module.resolve_target_session_observations(pf_record=pf, recovery_override=exact_recovery, target_session=TARGET)
        self.assertEqual((source, record["observations"]), ("RETAINED_TECHNICAL_HISTORY_RECOVERY", clean))

    def test_clean_recovery_is_still_adopted_when_the_snapshot_record_is_refused(self) -> None:
        clean = _series(ZIGZAG[:30])
        pf = {"observations": _with_copy_after(clean, PRIOR, close=1.0)}
        recovery = {"state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY", "observations": clean}
        record, source = structure_module.resolve_target_session_observations(pf_record=pf, recovery_override=recovery, target_session=TARGET)
        self.assertEqual((source, record), ("RETAINED_TECHNICAL_HISTORY_RECOVERY", recovery))


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _pipeline(observations_by_ticker: dict[str, list[dict]]):
    ur_records, pf_records, liq_records = {}, {}, {}
    for ticker, observations in observations_by_ticker.items():
        ur_records[ticker] = {"ticker": ticker, "activity_and_session_state": "ACTIVE_LISTED_OBSERVED", "membership_state": "INCLUDED"}
        pf_records[ticker] = {"disposition": "EXACT_SESSION_RETAINED", "observations": observations}
        liq_records[ticker] = {"ticker": ticker, "disposition": "MISSING", "reason": "NO_CURRENT_SESSION_ACTIVE_BOARD"}
    ur_payload = {"records": ur_records, "current_active_equity_denominator": {"count": len(ur_records)},
                  "observed_session_cohort": {"count": len(ur_records)}, "input_candidates": {"resolved_completed_session": TARGET}}
    ur = {**ur_payload, "artifact_sha256": _hash(ur_payload),
          "artifact_identity": f"current_universe_status_and_session_coverage_resolution:{_hash(ur_payload)}"}
    pf_payload = {"records": pf_records, "resolved_completed_session": TARGET}
    pf = {**pf_payload, "snapshot_sha256": stable_id(pf_payload), "snapshot_identity": f"p3f9_exact_session_snapshot:{stable_id(pf_payload)}"}
    liq_payload = {"records": liq_records, "resolved_completed_session": TARGET,
                   "universe": {"canonical_candidate_count": len(liq_records), "source_snapshot_identity": pf["snapshot_identity"]},
                   "coverage": {"disposition_counts": {"CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE": 0}},
                   "authority_boundary": {"QUALIFIED_LIQUIDITY_INPUTS": False}}
    liq = {**liq_payload, **liquidity_content_identity(liq_payload)}
    descriptive = descriptive_module.build_artifact(
        universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq,
        entity_classifications={t: {"classification_authority": "QUALIFIED_CLASSIFICATION", "classification_namespace": "NS",
                                    "entity_class": "SECTOR_A"} for t in observations_by_ticker})
    requested_at = f"{TARGET}T15:00:00+07:00"
    structure = structure_module.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=pf, requested_at=requested_at)
    momentum = momentum_module.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=pf, requested_at=requested_at)
    projection = projection_module.build_artifact(technical_structure=structure, requested_at=requested_at)
    rvol = rvol_module.build_artifact(candidates=sorted(pf_records), records=pf_records, session=TARGET, requested_at=requested_at)
    historical = {t: historical_module.evaluate_historical_context(o, target_session=TARGET) for t, o in observations_by_ticker.items()}
    return {"pf": pf, "descriptive": descriptive, "structure": structure, "momentum": momentum,
            "projection": projection, "rvol": rvol, "historical": historical}


def _per_ticker(run, ticker):
    """Per-ticker engine outputs with integrity annotations and artifact lineage removed."""
    technical = copy.deepcopy(run["descriptive"]["records"][ticker]["technical_features"])
    technical.get("technical_history_provenance", {}).pop("session_bar_integrity", None)
    structure = copy.deepcopy(run["structure"]["records"][ticker])
    momentum = copy.deepcopy(run["momentum"]["records"][ticker])
    historical = copy.deepcopy(run["historical"][ticker])
    historical.get("history", {}).pop("session_bar_integrity", None)
    rvol = {k: v for k, v in run["rvol"]["records"][ticker].items() if k in ("status", "reason", "percentile_status", "acceleration_status", "volume_acceleration_ratio")}
    return {"technical": technical, "structure": structure, "momentum": momentum,
            "projection": run["projection"]["records"][ticker], "historical": historical, "rvol": rvol}


class ConsumersShareOneCleanedSeriesTests(unittest.TestCase):
    """Representative 2026-09-16 regression through the real builders."""

    @classmethod
    def setUpClass(cls) -> None:
        clean = _series(ZIGZAG)
        cls.clean = clean
        # EXA: an identical second 2026-09-15 bar (410 real 09-15 pairs were identical).
        # AAM: a non-identical second 2026-09-15 bar (189 real pairs), AAM's real values.
        aam = [dict(row) for row in _series([7.5 + 0.02 * ((i * 5) % 7) for i in range(79)] + [7.4])]
        aam_index = next(i for i, row in enumerate(aam) if row["session"] == PRIOR)
        aam[aam_index].update(open=7.39, high=7.79, low=7.39, close=7.79, volume=400)
        aam.insert(aam_index + 1, {**aam[aam_index], "high": 7.39, "close": 7.39, "volume": 300})
        # VPI: pre/post-adjustment copies of older sessions, identical volume, same basis label.
        vpi = [dict(row) for row in _series([60.0 + ((i * 3) % 5) * 0.5 for i in range(80)])]
        older = _trading_days(TARGET, 13)[0]
        vpi = _with_copy_after(vpi, older, open=68.1, high=68.1, low=68.1, close=68.1)
        cls.with_duplicates = _pipeline({"EXA": _with_copy_after(clean, PRIOR), "AAM": aam, "VPI": vpi, "CLN": clean})
        cls.deduplicated = _pipeline({"EXA": clean, "AAM": aam, "VPI": vpi, "CLN": clean})

    def test_exact_duplicate_every_engine_sees_the_deduplicated_series(self) -> None:
        self.assertEqual(_per_ticker(self.with_duplicates, "EXA"), _per_ticker(self.deduplicated, "EXA"))
        tf = self.with_duplicates["descriptive"]["records"]["EXA"]["technical_features"]
        self.assertEqual(tf["status"], "SHADOW_ONLY")
        self.assertEqual(tf["technical_history_provenance"]["session_bar_integrity"]["exact_duplicate_sessions"], [PRIOR])
        self.assertEqual(self.with_duplicates["structure"]["records"]["EXA"]["close_history_depth"], len(self.clean))
        self.assertEqual(self.with_duplicates["rvol"]["records"]["EXA"]["percentile_status"],
                         self.deduplicated["rvol"]["records"]["EXA"]["percentile_status"])
        self.assertNotEqual(self.with_duplicates["rvol"]["records"]["EXA"].get("reason"), "DUPLICATE_SESSION_ROW")

    def test_conflicting_duplicate_every_engine_fails_closed_with_one_reason(self) -> None:
        for ticker in ("AAM", "VPI"):
            with self.subTest(ticker=ticker):
                run = self.with_duplicates
                tf = run["descriptive"]["records"][ticker]["technical_features"]
                self.assertEqual((tf["status"], tf["blockers"], tf["is_current_session"]), ("MISSING", [integrity.REFUSAL_REASON], False))
                self.assertIsNone(run["descriptive"]["records"][ticker]["trend_state"])
                self.assertEqual(run["structure"]["records"][ticker]["eligibility"]["status"], "NOT_ELIGIBLE")
                self.assertEqual(run["momentum"]["records"][ticker]["eligibility"]["status"], "NOT_ELIGIBLE")
                self.assertFalse(run["projection"]["records"][ticker].get("eligible"))
                self.assertEqual((run["rvol"]["records"][ticker]["status"], run["rvol"]["records"][ticker]["reason"]),
                                 ("UNAVAILABLE", integrity.REFUSAL_REASON))
                self.assertEqual(run["historical"][ticker]["context_status"], "MISSING")
                self.assertEqual(run["historical"][ticker]["drawdown"]["reason"], integrity.REFUSAL_REASON)

    def test_refusal_does_not_abort_the_descriptive_build_or_touch_other_tickers(self) -> None:
        # The descriptive build above would raise RECOVERABLE_SAME_SESSION_TECHNICAL_HISTORY_GAP if the
        # refusal were not registered as unrecoverable.
        self.assertEqual(_per_ticker(self.with_duplicates, "CLN"), _per_ticker(self.deduplicated, "CLN"))
        solo = _pipeline({"CLN": self.clean})
        for engine in ("technical", "structure", "momentum", "projection", "historical"):
            self.assertEqual(_per_ticker(self.with_duplicates, "CLN")[engine], _per_ticker(solo, "CLN")[engine])

    def test_unique_records_carry_no_integrity_annotation(self) -> None:
        tf = self.with_duplicates["descriptive"]["records"]["CLN"]["technical_features"]
        self.assertNotIn("session_bar_integrity", tf["technical_history_provenance"])
        self.assertNotIn("session_bar_integrity", self.with_duplicates["historical"]["CLN"]["history"])
        self.assertNotIn("session_bar_integrity", self.with_duplicates["rvol"]["records"]["CLN"])


class DispositionAndFeedbackTests(unittest.TestCase):
    def test_refused_ticker_is_conflicted_evidence_not_a_recoverable_filter(self) -> None:
        row = disposition_module._classify_one(
            ticker="AAM",
            descriptive={"technical_features": {"status": "MISSING", "blockers": [integrity.REFUSAL_REASON],
                                                "is_current_session": False, "feature_as_of_session": None},
                         "activity_and_session_state": "ACTIVE_LISTED_OBSERVED"},
            snapshot={"disposition": "EXACT_SESSION_RETAINED", "observations": [_bar(TARGET, 7.4)]},
            status={}, official=None, target_session=TARGET, official_tickers={"AAM"})
        self.assertEqual((row["disposition"], row["reason_code"]), ("MALFORMED_OR_CONFLICTED", integrity.REFUSAL_REASON))

    def test_prospective_price_lookup_never_lets_the_last_copy_win(self) -> None:
        clean = _series(ZIGZAG[:10])
        snapshot = {"records": {"AAM": {"observations": _with_copy_after(clean, PRIOR, close=1.0)},
                                "EXA": {"observations": _with_copy_after(clean, PRIOR)}}}
        self.assertEqual(feedback_module._price_observations(snapshot, "AAM"), {})
        self.assertEqual(feedback_module._price_observations(snapshot, "EXA"), {row["session"]: row for row in clean})


if __name__ == "__main__":
    unittest.main()
