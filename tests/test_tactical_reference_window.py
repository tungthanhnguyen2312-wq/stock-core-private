"""TACTICAL_REFERENCE_WINDOW_CORRECTIVE_V1 -- the authoritative 20-observation reference window.

Before this corrective, market_wide_current_descriptive_research passed the whole retained
history (~250 observations) to mva_daily_research_bundle.market_features(), so the tactical lens's
``ma_20``/``momentum_20d`` were a whole-history mean/return. These tests pin the restored
contract, the single shared computation, and that no structural/posture/priority code moved.
"""
from __future__ import annotations

import hashlib
import json
import statistics
import unittest
from datetime import date, timedelta
from pathlib import Path

import current_market_screening_opportunity_comparison_foundation as screening_module
import market_structure_breakout_product_projection as projection_module
import market_wide_current_descriptive_research as descriptive_module
import market_wide_current_fundamental_research as fundamental_module
import session_bar_integrity
import tactical_momentum_context as momentum_module
import tactical_reference_window as window
import technical_structure_context as structure_module
import watchlist_tactical_entry_classifier as classifier_module
from field_temporal_contract import stable_id
from integrated_investment_decision_product import decide_research_action_posture, evaluate_tactical_phase
from market_wide_current_liquidity_research import content_identity as liquidity_content_identity
from mva_daily_research_bundle import market_features

REPO = Path(__file__).resolve().parents[1]
TARGET = "2026-08-21"
BASIS = "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED"
TRANSFORM = "identity_provider_numeric_ohlc/v1"


def _trading_days(end: str, count: int) -> list[str]:
    d = date.fromisoformat(end)
    days: list[str] = []
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= timedelta(days=1)
    return list(reversed(days))


def _rows(closes, *, end=TARGET, volume=1000.0, basis=BASIS):
    return [{"date": day, "close": close, "volume": volume, "price_basis": basis, "transformation_identity": TRANSFORM}
            for day, close in zip(_trading_days(end, len(closes)), closes)]


def _pre_corrective_market_features(rows):
    """Verbatim arithmetic of the pre-corrective function, for equality on exactly-20 windows."""
    ordered = sorted(rows, key=lambda row: str(row["date"]))
    closes = [float(row["close"]) for row in ordered]
    volumes = [float(row["volume"]) for row in ordered]
    returns = [(closes[i] / closes[i - 1]) - 1 for i in range(1, len(closes))]
    median_volume = statistics.median(volumes)
    return {"close": closes[-1], "return_1d": returns[-1], "momentum_20d": (closes[-1] / closes[0]) - 1,
            "ma_3": statistics.mean(closes[-3:]), "ma_5": statistics.mean(closes[-5:]), "ma_20": statistics.mean(closes),
            "volatility_20d": statistics.pstdev(returns), "relative_volume_provider_scoped": volumes[-1] / median_volume}


# Hand-computable: ten closes of 10 then ten of 15 -> MA20 = 12.5, momentum = 15/10 - 1 = 0.5.
EXACT_WINDOW = [10.0] * 10 + [15.0] * 10


class WindowSelectionTests(unittest.TestCase):
    def test_exactly_twenty_observations(self) -> None:
        result = window.reference_values(_rows(EXACT_WINDOW), as_of_session=TARGET)
        self.assertEqual(result["status"], window.AVAILABLE)
        self.assertEqual(result["ma_20"], 12.5)
        self.assertEqual(result["momentum_20d"], 0.5)
        self.assertEqual(result["last_session"], TARGET)
        self.assertEqual(result["observations"], 20)

    def test_twenty_one_observations_drop_the_oldest(self) -> None:
        result = window.reference_values(_rows([1000.0] + EXACT_WINDOW), as_of_session=TARGET)
        self.assertEqual((result["ma_20"], result["momentum_20d"]), (12.5, 0.5))

    def test_long_history_only_latest_twenty_contribute(self) -> None:
        rows = _rows([95.0] * 229 + EXACT_WINDOW)
        features = market_features(rows, as_of_session=TARGET)
        self.assertEqual(features["status"], "SHADOW_ONLY")
        self.assertEqual(features["values"]["ma_20"], 12.5)
        self.assertEqual(features["values"]["momentum_20d"], 0.5)
        self.assertNotEqual(features["values"]["ma_20"], statistics.mean([95.0] * 229 + EXACT_WINDOW))
        # Every other window feature is also computed over the same 20 rows only.
        self.assertEqual(features["values"], _pre_corrective_market_features(rows[-20:]))

    def test_fewer_than_twenty_fails_closed(self) -> None:
        result = window.reference_values(_rows(EXACT_WINDOW[:19]), as_of_session=TARGET)
        self.assertEqual(result["status"], window.MISSING)
        self.assertEqual(result["blockers"], [window.BLOCKER_INCOMPLETE_WINDOW])
        self.assertIsNone(result["ma_20"])
        self.assertEqual(market_features(_rows(EXACT_WINDOW[:19]))["status"], "MISSING")

    def test_unusable_row_inside_window_fails_closed_and_is_never_skipped(self) -> None:
        for field, bad in (("close", None), ("close", 0.0), ("close", float("nan")), ("volume", None)):
            rows = _rows([11.0] * 30 + EXACT_WINDOW)
            rows[-5] = {**rows[-5], field: bad}
            with self.subTest(field=field, bad=bad):
                self.assertEqual(window.select_reference_window(rows, as_of_session=TARGET)["blockers"],
                                 [window.BLOCKER_INCOMPLETE_WINDOW])
                self.assertEqual(market_features(rows)["status"], "MISSING")

    def test_unusable_row_outside_window_does_not_contaminate(self) -> None:
        rows = _rows([11.0] * 30 + EXACT_WINDOW)
        rows[3] = {**rows[3], "close": None, "volume": None}
        self.assertEqual(window.reference_values(rows, as_of_session=TARGET)["ma_20"], 12.5)

    def test_mixed_price_basis_inside_window_fails_closed(self) -> None:
        rows = _rows(EXACT_WINDOW)
        rows[7] = {**rows[7], "price_basis": "CURRENT_DESCRIPTIVE_NOT_PROMOTED_RAW_AS_TRADED"}
        self.assertEqual(window.select_reference_window(rows)["blockers"], [window.BLOCKER_MIXED_PRICE_BASIS])
        rows = _rows(EXACT_WINDOW)
        rows[7] = {**rows[7], "transformation_identity": "other/v1"}
        self.assertEqual(market_features(rows)["blockers"], [window.BLOCKER_MIXED_PRICE_BASIS])
        # A different basis outside the window is irrelevant to the window.
        rows = _rows([11.0] * 5 + EXACT_WINDOW)
        rows[0] = {**rows[0], "price_basis": "CURRENT_DESCRIPTIVE_NOT_PROMOTED_RAW_AS_TRADED"}
        self.assertEqual(window.reference_values(rows)["ma_20"], 12.5)

    def test_rows_without_basis_fields_are_uniform(self) -> None:
        rows = [{"date": row["date"], "close": row["close"], "volume": row["volume"]} for row in _rows(EXACT_WINDOW)]
        self.assertEqual(window.reference_values(rows)["ma_20"], 12.5)

    def test_reversed_or_shuffled_input_is_ordered_by_session(self) -> None:
        rows = _rows([95.0] * 10 + EXACT_WINDOW)
        expected = window.reference_values(rows, as_of_session=TARGET)
        shuffled = rows[::-1]
        shuffled[3], shuffled[17] = shuffled[17], shuffled[3]
        self.assertEqual(window.reference_values(shuffled, as_of_session=TARGET), expected)
        self.assertEqual(market_features(shuffled), market_features(rows))

    def test_exact_duplicate_session_counts_once(self) -> None:
        rows = _rows([95.0] * 5 + EXACT_WINDOW)
        doubled = rows + [dict(rows[-1]), dict(rows[-7])]
        self.assertEqual(window.reference_values(doubled, as_of_session=TARGET), window.reference_values(rows, as_of_session=TARGET))

    def test_conflicting_duplicate_session_inside_window_fails_closed(self) -> None:
        rows = _rows(EXACT_WINDOW)
        rows.append({**rows[-3], "close": 99.0})  # same session, different close (2026-09-16 shape)
        result = window.select_reference_window(rows, as_of_session=TARGET)
        self.assertEqual(result["blockers"], [session_bar_integrity.REFUSAL_REASON])
        self.assertIn(session_bar_integrity.REFUSAL_REASON, window.INTEGRITY_BLOCKERS)
        self.assertEqual(market_features(rows)["blockers"], [session_bar_integrity.REFUSAL_REASON])

    def test_conflicting_duplicate_outside_window_refuses_under_the_shared_policy(self) -> None:
        # DATA_INTEGRITY_AND_TACTICAL_REFERENCE_INTEGRATION_V1: the window keeps no duplicate rule
        # of its own. session_bar_integrity refuses the whole series, wherever the conflict sits.
        rows = _rows([95.0] * 5 + EXACT_WINDOW)
        rows.append({**rows[1], "close": 1.0})
        result = window.reference_values(rows, as_of_session=TARGET)
        self.assertEqual((result["ma_20"], result["blockers"]), (None, [session_bar_integrity.REFUSAL_REASON]))

    def test_future_observation_never_enters_t0_window(self) -> None:
        rows = _rows(EXACT_WINDOW)
        future = {**rows[-1], "date": "2026-08-24", "close": 1000.0}
        with_future = window.reference_values(rows + [future], as_of_session=TARGET)
        self.assertEqual(with_future, window.reference_values(rows, as_of_session=TARGET))
        self.assertEqual(with_future["last_session"], TARGET)
        self.assertEqual(market_features(rows + [future], as_of_session=TARGET), market_features(rows))

    def test_exactly_twenty_row_callers_are_byte_identical_to_before(self) -> None:
        rows = _rows([100.0 + ((i * 7) % 11) * 0.37 for i in range(20)], volume=1234.0)
        self.assertEqual(market_features(rows)["values"], _pre_corrective_market_features(rows))

    def test_reference_functions_refuse_a_non_twenty_window(self) -> None:
        with self.assertRaises(ValueError):
            window.reference_ma20([1.0] * 21)
        with self.assertRaises(ValueError):
            window.reference_momentum_20d([1.0] * 19)


# ── Descriptive -> classifier and momentum context: one shared source ─────────────────────────

def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _inputs(observations_by_ticker):
    ur_records, pf_records, liq_records = {}, {}, {}
    for ticker, observations in observations_by_ticker.items():
        ur_records[ticker] = {"ticker": ticker, "activity_and_session_state": "ACTIVE_LISTED_OBSERVED", "membership_state": "INCLUDED"}
        pf_records[ticker] = {"disposition": "EXACT_SESSION_RETAINED", "observations": observations}
        liq_records[ticker] = {"ticker": ticker, "disposition": "MISSING", "reason": "NO_CURRENT_SESSION_ACTIVE_BOARD"}
    ur_payload = {"records": ur_records, "current_active_equity_denominator": {"count": len(ur_records)},
                  "observed_session_cohort": {"count": len(ur_records)}, "input_candidates": {"resolved_completed_session": TARGET}}
    ur_digest = _hash(ur_payload)
    ur = {**ur_payload, "artifact_sha256": ur_digest, "artifact_identity": f"current_universe_status_and_session_coverage_resolution:{ur_digest}"}
    pf_payload = {"records": pf_records, "resolved_completed_session": TARGET}
    pf_digest = stable_id(pf_payload)
    pf = {**pf_payload, "snapshot_sha256": pf_digest, "snapshot_identity": f"p3f9_exact_session_snapshot:{pf_digest}"}
    liq_payload = {"records": liq_records, "resolved_completed_session": TARGET,
                   "universe": {"canonical_candidate_count": len(liq_records), "source_snapshot_identity": pf["snapshot_identity"]},
                   "coverage": {"disposition_counts": {"CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE": 0}},
                   "authority_boundary": {"QUALIFIED_LIQUIDITY_INPUTS": False}}
    liq = {**liq_payload, **liquidity_content_identity(liq_payload)}
    return ur, pf, liq


def _observations(closes, *, end=TARGET):
    return [{"session": day, "open": close, "high": close, "low": close, "close": close, "volume": 1000.0 + i,
             "price_basis": BASIS, "transformation_identity": TRANSFORM}
            for i, (day, close) in enumerate(zip(_trading_days(end, len(closes)), closes))]


# GEE-shaped regression: a long history near 95 followed by a 20-session base near 60-70. The
# whole-history mean (~91) puts the close far "below MA20"; the true MA20 is 65 and the close is above it.
GEE_LIKE = [95.0] * 229 + [60.0] * 10 + [70.0] * 10
GEE_TRUE_MA20 = 65.0


def _pipeline(observations_by_ticker):
    ur, pf, liq = _inputs(observations_by_ticker)
    descriptive = descriptive_module.build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf,
                                                    liquidity_artifact=liq, entity_classifications={
                                                        ticker: {"classification_authority": "QUALIFIED_CLASSIFICATION",
                                                                 "classification_namespace": "NS", "entity_class": "SECTOR_A"}
                                                        for ticker in observations_by_ticker})
    screening = screening_module.build_artifact(descriptive)
    fundamental_payload = {"schema_version": "1.0.0", "contract_version": "market_wide_current_fundamental_research/v1",
                           "records": {}, "coverage": {"candidate_count": 0}}
    fundamental = {**fundamental_payload, **fundamental_module.content_identity(fundamental_payload)}
    tactical = classifier_module.build_artifact(descriptive_source=descriptive, screening_source=screening,
                                                fundamental_source=fundamental, requested_at="2026-08-21T15:00:00+07:00")
    momentum = momentum_module.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=pf,
                                              requested_at="2026-08-21T15:00:00+07:00")
    return pf, descriptive, tactical, momentum


class SharedReferenceSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pf, cls.descriptive, cls.tactical, cls.momentum = _pipeline({
            "GEE": _observations(GEE_LIKE),
            "UPX": _observations([10.0 + 0.1 * i for i in range(60)]),
            "DNX": _observations([30.0 - 0.1 * i for i in range(45)]),
        })

    def test_classifier_and_momentum_context_share_identical_ma20_and_momentum(self) -> None:
        for ticker in ("GEE", "UPX", "DNX"):
            with self.subTest(ticker=ticker):
                signals = self.tactical["records"][ticker]["signals"]
                momentum = self.momentum["records"][ticker]
                self.assertEqual(momentum["eligibility"]["status"], "ELIGIBLE")
                self.assertEqual(signals["ma_20"], momentum["moving_averages"]["20"]["value"])
                self.assertEqual(signals["ma_20"], momentum["reference_window"]["ma_20"])
                self.assertEqual(signals["momentum_20d"], momentum["reference_window"]["momentum_20d"])
                self.assertEqual(momentum["reference_window"]["last_session"], TARGET)

    def test_gee_shaped_regression_uses_true_ma20(self) -> None:
        technical = self.descriptive["records"]["GEE"]["technical_features"]
        self.assertEqual(technical["values"]["ma_20"], GEE_TRUE_MA20)
        self.assertEqual(technical["values"]["momentum_20d"], 70.0 / 60.0 - 1)
        self.assertEqual(technical["reference_window"]["observations"], 20)
        self.assertLess(technical["values"]["close"], statistics.mean(GEE_LIKE))  # the old, wrong reading
        self.assertEqual(self.descriptive["records"]["GEE"]["trend_state"], "ABOVE_MA20")
        self.assertTrue(self.tactical["records"]["GEE"]["ticker_structure_state"].startswith("ABOVE_MA20"))

    def test_future_observation_does_not_change_t0_tactical_values(self) -> None:
        future = dict(_observations(GEE_LIKE)[-1], session="2026-08-24", close=500.0)
        _, descriptive, tactical, momentum = _pipeline({"GEE": _observations(GEE_LIKE) + [future]})
        technical = descriptive["records"]["GEE"]["technical_features"]
        self.assertTrue(technical["is_current_session"])
        self.assertEqual(technical["feature_as_of_session"], TARGET)
        self.assertEqual(technical["values"], self.descriptive["records"]["GEE"]["technical_features"]["values"])
        self.assertEqual(tactical["records"]["GEE"]["signals"]["ma_20"], GEE_TRUE_MA20)
        self.assertEqual(momentum["records"]["GEE"]["reference_window"]["ma_20"], GEE_TRUE_MA20)


class DescriptiveIntegrityRefusalTests(unittest.TestCase):
    def test_conflicting_duplicate_fails_closed_per_ticker_without_aborting_the_build(self) -> None:
        observations = _observations(GEE_LIKE)
        observations.append({**observations[-2], "close": 61.5})  # conflicting copy of a window session
        _, descriptive, tactical, momentum = _pipeline({"GEE": observations, "UPX": _observations([10.0 + 0.1 * i for i in range(60)])})
        technical = descriptive["records"]["GEE"]["technical_features"]
        self.assertEqual(technical["status"], "MISSING")
        self.assertEqual(technical["blockers"], [session_bar_integrity.REFUSAL_REASON])
        self.assertIsNone(tactical["records"]["GEE"]["entry_state"])
        self.assertEqual(momentum["records"]["GEE"]["eligibility"]["status"], "NOT_ELIGIBLE")
        self.assertEqual(descriptive["records"]["UPX"]["technical_features"]["status"], "SHADOW_ONLY")

    def test_exact_duplicate_bar_keeps_classifier_and_momentum_identical(self) -> None:
        observations = _observations(GEE_LIKE)
        observations.append(dict(observations[-4]))
        _, descriptive, tactical, momentum = _pipeline({"GEE": observations})
        self.assertEqual(tactical["records"]["GEE"]["signals"]["ma_20"], GEE_TRUE_MA20)
        self.assertEqual(momentum["records"]["GEE"]["moving_averages"]["20"]["value"], GEE_TRUE_MA20)
        self.assertEqual(momentum["records"]["GEE"]["reference_window"]["ma_20"], GEE_TRUE_MA20)


class PolicyInvarianceTests(unittest.TestCase):
    """Tactical values change; the structural engine, posture policy, and priority code do not."""

    def test_structural_engine_does_not_consume_the_corrected_values(self) -> None:
        pf, descriptive, _, _ = _pipeline({"GEE": _observations(GEE_LIKE), "UPX": _observations([10.0 + 0.1 * i for i in range(60)])})
        tampered = json.loads(json.dumps(descriptive))
        for record in tampered["records"].values():
            record["technical_features"]["values"].update(ma_20=1.0, momentum_20d=-0.99, volatility_20d=9.9)
            record["trend_state"] = "AT_OR_BELOW_MA20"
        tampered.update(descriptive_module.content_identity(tampered))
        base = structure_module.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=pf, requested_at="t")
        other = structure_module.build_artifact(current_descriptive=tampered, p3f9b_snapshot=pf, requested_at="t")
        v3_keys = ("swing_structure", "bos_context", "choch_context", "pivot_context", "breakout_state_v3",
                   "trigger_context", "invalidation_context", "structure_context", "contraction_context", "base_context")
        for ticker in base["records"]:
            for key in v3_keys:
                self.assertEqual(base["records"][ticker][key], other["records"][ticker][key])
            self.assertEqual(base["records"][ticker]["trend_context"]["ma20_slope"], other["records"][ticker]["trend_context"]["ma20_slope"])
        # The posture policy reads the structural projection; the only fields that differ
        # (trend_state pass-through) are not policy inputs, so posture and phase are identical.
        base_projection = projection_module.build_artifact(technical_structure=base, requested_at="t")["records"]
        other_projection = projection_module.build_artifact(technical_structure=other, requested_at="t")["records"]
        for ticker, record in base_projection.items():
            phase_a = evaluate_tactical_phase(record)
            phase_b = evaluate_tactical_phase(other_projection[ticker])
            self.assertEqual(phase_a, phase_b)
            common = dict(ticker=ticker, fundamental_state="STABLE", tac_supports=phase_a[1], tac_counters=phase_a[2],
                          fund_supports=[], fund_counters=[], val_supports=[], val_counters=[], part_supports=[], part_counters=[])
            self.assertEqual(decide_research_action_posture(tactical_phase=phase_a[0], tactical_rec=record, **common),
                             decide_research_action_posture(tactical_phase=phase_b[0], tactical_rec=other_projection[ticker], **common))

    def test_posture_structure_and_priority_modules_do_not_use_the_reference_window(self) -> None:
        for name in ("integrated_investment_decision_product.py", "technical_structure_context.py",
                     "market_structure_breakout_product_projection.py", "daily_opportunity_decision_queue.py",
                     "current_opportunity_prioritization.py"):
            with self.subTest(module=name):
                self.assertNotIn("tactical_reference_window", (REPO / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
