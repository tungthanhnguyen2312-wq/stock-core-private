import copy
import inspect
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import historical_tactical_replay_evidence_foundation as foundation
import tactical_reversal_probe_policy_counterfactual_evaluation as probe
import tactical_reversal_retrospective_validation as validation
import watchlist_tactical_entry_classifier as classifier


def _row(session, *, rule_id, close, momentum_bucket=None, elevated_volume=None, return_1d=None, prior_row=None, prior_row_gap=False):
    return {
        "session": session,
        "record": {
            "rule_id": rule_id,
            "signals": {
                "close": close,
                "momentum_bucket": momentum_bucket,
                "elevated_volume_vs_cohort_median": elevated_volume,
                "return_1d": return_1d,
            },
        },
        "prior_row": prior_row,
        "prior_row_gap": prior_row_gap,
    }


class CandidateEvaluatorTests(unittest.TestCase):
    def test_non_r8_row_is_ineligible_for_every_candidate(self):
        row = _row("2026-07-01", rule_id="R9_DOWNTREND_DEFAULT", close=10.0)
        for name in probe.CANDIDATE_POLICIES:
            verdict = probe.evaluate_candidate(name, row)
            self.assertFalse(verdict["eligible"])
            self.assertIn("NOT_R8_SELLING_PRESSURE_EASING", verdict["reason_codes"])

    def test_candidate_a_requires_upper_half_momentum_bucket(self):
        upper = _row("2026-07-01", rule_id="R8_SELLING_PRESSURE_EASING", close=10.0, momentum_bucket="UPPER_QUARTILE")
        lower = _row("2026-07-01", rule_id="R8_SELLING_PRESSURE_EASING", close=10.0, momentum_bucket="LOWER_MIDDLE")
        missing = _row("2026-07-01", rule_id="R8_SELLING_PRESSURE_EASING", close=10.0, momentum_bucket=None)
        self.assertTrue(probe.evaluate_candidate("CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET", upper)["eligible"])
        self.assertFalse(probe.evaluate_candidate("CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET", lower)["eligible"])
        self.assertIsNone(probe.evaluate_candidate("CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET", missing)["eligible"])

    def test_candidate_b_requires_adjacent_prior_r8_and_never_defaults_a_gap(self):
        prior_r8 = _row("2026-07-01", rule_id="R8_SELLING_PRESSURE_EASING", close=10.0)
        today_no_prior = _row("2026-07-02", rule_id="R8_SELLING_PRESSURE_EASING", close=10.5)
        today_with_prior_r8 = _row("2026-07-02", rule_id="R8_SELLING_PRESSURE_EASING", close=10.5, prior_row=prior_r8)
        prior_r9 = _row("2026-07-01", rule_id="R9_DOWNTREND_DEFAULT", close=10.0)
        today_with_prior_r9 = _row("2026-07-02", rule_id="R8_SELLING_PRESSURE_EASING", close=10.5, prior_row=prior_r9)
        today_with_gap = _row("2026-07-03", rule_id="R8_SELLING_PRESSURE_EASING", close=10.5, prior_row_gap=True)

        self.assertIsNone(probe.evaluate_candidate("CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE", today_no_prior)["eligible"])
        self.assertTrue(probe.evaluate_candidate("CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE", today_with_prior_r8)["eligible"])
        self.assertFalse(probe.evaluate_candidate("CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE", today_with_prior_r9)["eligible"])
        gap_verdict = probe.evaluate_candidate("CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE", today_with_gap)
        self.assertIsNone(gap_verdict["eligible"])
        self.assertIn("PRIOR_SESSION_GAP", gap_verdict["reason_codes"])

    def test_candidate_c_excludes_breakdown_quartile_and_requires_volume_and_return(self):
        eligible = _row("2026-07-01", rule_id="R8_SELLING_PRESSURE_EASING", close=10.0, momentum_bucket="LOWER_MIDDLE", elevated_volume=True, return_1d=0.01)
        breakdown_quartile = _row("2026-07-01", rule_id="R8_SELLING_PRESSURE_EASING", close=10.0, momentum_bucket="LOWER_QUARTILE", elevated_volume=True, return_1d=0.01)
        no_volume = _row("2026-07-01", rule_id="R8_SELLING_PRESSURE_EASING", close=10.0, momentum_bucket="LOWER_MIDDLE", elevated_volume=False, return_1d=0.01)
        negative_return = _row("2026-07-01", rule_id="R8_SELLING_PRESSURE_EASING", close=10.0, momentum_bucket="LOWER_MIDDLE", elevated_volume=True, return_1d=-0.01)
        name = "CANDIDATE_C_R8_VOLUME_RETURN_NO_BREAKDOWN_QUARTILE"
        self.assertTrue(probe.evaluate_candidate(name, eligible)["eligible"])
        self.assertEqual(probe.evaluate_candidate(name, breakdown_quartile)["reason_codes"], ["BREAKDOWN_QUARTILE_EXCLUSION"])
        self.assertFalse(probe.evaluate_candidate(name, no_volume)["eligible"])
        self.assertFalse(probe.evaluate_candidate(name, negative_return)["eligible"])

    def test_evaluators_take_only_the_current_and_adjacent_prior_row_never_a_forward_row(self):
        for policy in probe.CANDIDATE_POLICIES.values():
            parameters = list(inspect.signature(policy["evaluator"]).parameters)
            self.assertEqual(parameters, ["row"])
            for forbidden in ("future", "forward", "rows", "next", "outcome"):
                self.assertNotIn(forbidden, " ".join(parameters).lower())


class T0OnlySignalGenerationTests(unittest.TestCase):
    """Prove signal generation is unaffected by any later same-ticker observation."""

    def test_candidate_verdict_is_identical_regardless_of_what_happens_afterward(self):
        prior = _row("2026-07-01", rule_id="R8_SELLING_PRESSURE_EASING", close=10.0)
        today = _row("2026-07-02", rule_id="R8_SELLING_PRESSURE_EASING", close=10.2, prior_row=prior)
        baseline = {name: probe.evaluate_candidate(name, today) for name in probe.CANDIDATE_POLICIES}

        adversarial_future = copy.deepcopy(today)
        adversarial_future["record"]["future_injected_field"] = "SHOULD_NEVER_BE_READ"
        mutated = {name: probe.evaluate_candidate(name, adversarial_future) for name in probe.CANDIDATE_POLICIES}
        self.assertEqual(baseline, mutated)

    def test_episode_starts_are_found_from_rule_id_only_without_consulting_outcome(self):
        rows = [
            _row("2026-07-01", rule_id="R9_DOWNTREND_DEFAULT", close=10.0),
            _row("2026-07-02", rule_id="R8_SELLING_PRESSURE_EASING", close=10.2),
            _row("2026-07-03", rule_id="R8_SELLING_PRESSURE_EASING", close=10.4),
            _row("2026-07-06", rule_id="R9_DOWNTREND_DEFAULT", close=9.8),
            _row("2026-07-07", rule_id="R8_SELLING_PRESSURE_EASING", close=10.0),
        ]
        starts = probe._episodes(rows, predicate=lambda row: probe._is_r8(row["record"]))
        self.assertEqual(starts, [1, 4])


class EpisodeOutcomeTests(unittest.TestCase):
    def _series(self):
        closes = [10.0, 9.5, 9.0, 8.8, 9.4, 9.6, 9.9, 10.2, 10.5, 10.1, 9.7, 9.2]
        sessions = [f"2026-07-{day:02d}" for day in range(1, 1 + len(closes))]
        rule_ids = ["R9_DOWNTREND_DEFAULT"] * 3 + ["R8_SELLING_PRESSURE_EASING"] + ["R9_DOWNTREND_DEFAULT"] * 3 + ["R6_EARLY_REVERSAL_CANDIDATE"] + ["R3_UPTREND_CONFIRMED_DEFAULT"] * 4
        return [
            _row(session, rule_id=rule_id, close=close)
            for session, close, rule_id in zip(sessions, closes, rule_ids)
        ]

    def test_reference_low_distance_and_lag_are_computed_from_the_full_window(self):
        rows = self._series()
        outcome = probe.episode_outcome(rows, signal_position=3)
        self.assertEqual(outcome["status"], "COMPUTED_RETROSPECTIVE_SAME_SERIES_ONLY")
        self.assertEqual(outcome["reference_low"], {"session": "2026-07-04", "close": 8.8})
        self.assertEqual(outcome["session_lag_from_reference_low"], 0)
        self.assertAlmostEqual(outcome["distance_from_reference_low_pct"], 0.0)
        self.assertEqual(outcome["timing_label"], validation.EARLY_SIGNAL_NEAR_LOW)

    def test_confirmation_detection_finds_the_first_r6_r3_or_r2_after_the_signal(self):
        rows = self._series()
        outcome = probe.episode_outcome(rows, signal_position=3)
        self.assertIsNotNone(outcome["confirmation"])
        self.assertEqual(outcome["confirmation"]["rule_id"], "R6_EARLY_REVERSAL_CANDIDATE")
        self.assertEqual(outcome["confirmation"]["session_lag"], 4)

    def test_horizon_metrics_mark_insufficient_forward_evidence_rather_than_partial_defaulting(self):
        rows = self._series()
        outcome = probe.episode_outcome(rows, signal_position=len(rows) - 1)
        self.assertEqual(outcome["horizons"]["t5"]["status"], "INSUFFICIENT_FORWARD_EVIDENCE")

    def test_missing_comparable_close_fails_closed(self):
        rows = [_row("2026-07-01", rule_id="R9_DOWNTREND_DEFAULT", close=None)]
        outcome = probe.episode_outcome(rows, signal_position=0)
        self.assertEqual(outcome["status"], "NOT_COMPUTED")

    def test_outcome_carries_the_same_price_basis_and_series_identity_as_the_foundation(self):
        rows = self._series()
        outcome = probe.episode_outcome(rows, signal_position=3)
        self.assertEqual(outcome["price_basis"], foundation.PRICE_BASIS)
        self.assertEqual(outcome["research_series_identity"], foundation.RESEARCH_PRICE_SERIES_IDENTITY)


class PanControlUnchangedTests(unittest.TestCase):
    """Locks in the exact retained PAN 2026-09-09 -> 2026-09-10 control transition."""

    SESSION_08 = {"entry_state": "DOWNTREND", "entry_action": "AVOID", "rule_id": "R9_DOWNTREND_DEFAULT",
                  "signals": {"close": 18.5, "momentum_bucket": "LOWER_MIDDLE", "elevated_volume_vs_cohort_median": True, "return_1d": -0.0159}}
    SESSION_09 = {"entry_state": "SELLING_PRESSURE_EASING", "entry_action": "WAIT", "rule_id": "R8_SELLING_PRESSURE_EASING",
                  "signals": {"close": 18.65, "momentum_bucket": "LOWER_MIDDLE", "elevated_volume_vs_cohort_median": True, "return_1d": 0.0081}}
    SESSION_10 = {"entry_state": "DOWNTREND", "entry_action": "AVOID", "rule_id": "R9_DOWNTREND_DEFAULT",
                  "signals": {"close": 18.5, "momentum_bucket": "LOWER_MIDDLE", "elevated_volume_vs_cohort_median": True, "return_1d": -0.008}}

    def test_transition_is_reported_unchanged_from_retained_evidence(self):
        result = probe.pan_control_case_study(
            session_2026_09_08=self.SESSION_08, session_2026_09_09=self.SESSION_09, session_2026_09_10=self.SESSION_10,
        )
        self.assertEqual(result["transition"], {
            "from_session": "2026-09-09", "from_state": "SELLING_PRESSURE_EASING",
            "from_action": "WAIT", "from_rule_id": "R8_SELLING_PRESSURE_EASING",
            "to_session": "2026-09-10", "to_state": "DOWNTREND",
            "to_action": "AVOID", "to_rule_id": "R9_DOWNTREND_DEFAULT",
        })

    def test_candidate_a_and_b_correctly_exclude_the_pan_false_start_but_c_flags_it(self):
        result = probe.pan_control_case_study(
            session_2026_09_08=self.SESSION_08, session_2026_09_09=self.SESSION_09, session_2026_09_10=self.SESSION_10,
        )
        verdicts = result["candidate_verdicts_on_2026_09_09"]
        self.assertFalse(verdicts["CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET"]["eligible"])
        self.assertFalse(verdicts["CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE"]["eligible"])
        self.assertTrue(verdicts["CANDIDATE_C_R8_VOLUME_RETURN_NO_BREAKDOWN_QUARTILE"]["eligible"])

    def test_persistence_candidate_is_unevaluable_without_a_retained_prior_session(self):
        result = probe.pan_control_case_study(
            session_2026_09_08=None, session_2026_09_09=self.SESSION_09, session_2026_09_10=self.SESSION_10,
        )
        verdict = result["candidate_verdicts_on_2026_09_09"]["CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE"]
        self.assertIsNone(verdict["eligible"])


class DecisionCriteriaTests(unittest.TestCase):
    def _cohort_eval(self, *, control_r8_lower_low=0.80, control_r8_mae=-0.04, candidate_overrides=None):
        def agg(lower_low, mae_mean, lag_median, lag_n, computed_n):
            return {
                "computed_count": computed_n,
                "horizons": {"t10": {"lower_low_rate": lower_low, "mae_pct": {"mean": mae_mean}}},
                "confirmation_session_lag_when_reached": {"median": lag_median, "n": lag_n},
            }
        candidates = {
            "CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET": {"aggregate": agg(0.70, -0.03, 8, 50, 100)},
            "CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE": {"aggregate": agg(0.72, -0.03, 10, 50, 100)},
            "CANDIDATE_C_R8_VOLUME_RETURN_NO_BREAKDOWN_QUARTILE": {"aggregate": agg(0.79, -0.041, 12, 50, 100)},
        }
        if candidate_overrides:
            for name, override in candidate_overrides.items():
                candidates[name]["aggregate"].update(override)
        return {
            "control": {
                "r8_selling_pressure_easing": {"aggregate": agg(control_r8_lower_low, control_r8_mae, None, 0, 500)},
                "r6_early_reversal_candidate": {"aggregate": agg(0.7, -0.03, 1, 100, 100)},
            },
            "candidates": candidates,
        }

    def test_insufficient_cohort_evidence_when_the_cohort_is_too_small(self):
        summary = {"tickers_with_any_reconstruction": 5, "control_r8_episode_count": 10}
        result = probe.decide(cohort_summary=summary, cohort_eval=self._cohort_eval())
        self.assertEqual(result["decision"], probe.INSUFFICIENT_COHORT_EVIDENCE)

    def test_keep_current_policy_when_no_candidate_clears_the_bar(self):
        summary = {"tickers_with_any_reconstruction": 500, "control_r8_episode_count": 500}
        overrides = {name: {"horizons": {"t10": {"lower_low_rate": 0.80, "mae_pct": {"mean": -0.04}}}} for name in probe.CANDIDATE_POLICIES}
        result = probe.decide(cohort_summary=summary, cohort_eval=self._cohort_eval(candidate_overrides=overrides))
        self.assertEqual(result["decision"], probe.KEEP_CURRENT_R6_POLICY)

    def test_supports_probe_policy_only_for_candidates_clearing_every_named_criterion(self):
        summary = {"tickers_with_any_reconstruction": 500, "control_r8_episode_count": 500}
        pan_case_study = {"candidate_verdicts_on_2026_09_09": {
            "CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET": {"eligible": False},
            "CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE": {"eligible": False},
            "CANDIDATE_C_R8_VOLUME_RETURN_NO_BREAKDOWN_QUARTILE": {"eligible": True},
        }}
        result = probe.decide(cohort_summary=summary, cohort_eval=self._cohort_eval(), pan_case_study=pan_case_study)
        self.assertEqual(result["decision"], probe.EVIDENCE_SUPPORTS_SHADOW_PROBE_POLICY)
        self.assertIn("CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET", result["supported_candidates"])
        self.assertIn("CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE", result["supported_candidates"])
        self.assertNotIn("CANDIDATE_C_R8_VOLUME_RETURN_NO_BREAKDOWN_QUARTILE", result["supported_candidates"])

    def test_a_candidate_that_flags_the_pan_control_episode_eligible_is_never_supported(self):
        summary = {"tickers_with_any_reconstruction": 500, "control_r8_episode_count": 500}
        pan_case_study = {"candidate_verdicts_on_2026_09_09": {
            "CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET": {"eligible": True},
            "CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE": {"eligible": False},
            "CANDIDATE_C_R8_VOLUME_RETURN_NO_BREAKDOWN_QUARTILE": {"eligible": False},
        }}
        result = probe.decide(cohort_summary=summary, cohort_eval=self._cohort_eval(), pan_case_study=pan_case_study)
        self.assertNotIn("CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET", result.get("supported_candidates", []))


class PolicyBoundaryTests(unittest.TestCase):
    def test_no_rule_table_copy_exists_in_this_module(self):
        source = inspect.getsource(probe)
        self.assertNotIn("_entry_state_rule", source)
        self.assertNotIn("RULE_DEFINITIONS =", source)

    def test_timing_thresholds_are_reused_not_redefined(self):
        self.assertIs(probe.TIMING_THRESHOLDS, validation.TIMING_THRESHOLDS)

    def test_classifier_rule_definitions_are_untouched(self):
        self.assertIn("R8_SELLING_PRESSURE_EASING", classifier.RULE_DEFINITIONS)
        self.assertIn("R6_EARLY_REVERSAL_CANDIDATE", classifier.RULE_DEFINITIONS)

    def test_no_sizing_or_weighted_score_helper_is_introduced(self):
        source = inspect.getsource(probe)
        for forbidden in ("position_size", "sizing_multiplier", "weighted_score", "composite_score"):
            self.assertNotIn(forbidden, source)


DATES = tuple(f"2026-06-{day:02d}" for day in range(1, 21)) + tuple(f"2026-07-{day:02d}" for day in range(1, 6))


def _make_runtime():
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    database = root / "vn_stock.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript("""
            CREATE TABLE ohlcv(
                ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
                volume INTEGER, source TEXT, PRIMARY KEY(ticker, date)
            );
            CREATE TABLE ohlcv_lineage(
                ticker TEXT NOT NULL, trading_session_date TEXT NOT NULL, provider TEXT NOT NULL,
                provider_version TEXT NOT NULL, adapter_schema_version TEXT NOT NULL, endpoint TEXT NOT NULL,
                canonical_field TEXT NOT NULL, retrieved_at TEXT NOT NULL, source_record_hash TEXT NOT NULL,
                unit_scale INTEGER NOT NULL, PRIMARY KEY(ticker, trading_session_date)
            );
        """)
        for ticker, offset in (("AAA", 0.0), ("BBB", 30.0), ("CCC", 60.0)):
            for index, day in enumerate(DATES):
                close = 100.0 + offset + index
                connection.execute(
                    "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (ticker, day, close, close, close, close, 1_000 + index, "DNSE"),
                )
                connection.execute(
                    "INSERT INTO ohlcv_lineage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (ticker, day, "DNSE", "snapshot/v2", "lineage/v1", "/price/ohlc", "ohlcv", "2026-08-25T21:50:44+07:00", f"sha-{ticker}-{day}", 1),
                )
        connection.commit()
    finally:
        connection.close()
    return temp, root


class ReconstructionInvocationAndDeterminismTests(unittest.TestCase):
    def test_reconstruction_invokes_the_existing_classifier_without_a_provider_call(self):
        temp, root = _make_runtime()
        self.addCleanup(temp.cleanup)
        sessions = probe.available_sessions(root, start="2026-07-01", end="2026-07-05")
        self.assertTrue(sessions)
        with mock.patch.object(foundation.classifier, "build_artifact", wraps=classifier.build_artifact) as build, \
             mock.patch("socket.socket.connect", side_effect=AssertionError("provider call attempted")):
            cohort = probe.reconstruct_cohort_sessions(root, sessions=sessions)
        self.assertTrue(build.called)
        for call in build.call_args_list:
            self.assertTrue(call.kwargs["requested_at"].startswith("HISTORICAL_RECONSTRUCTION:"))
        self.assertEqual(cohort["session_exclusions"], {})

    def test_repeated_builds_from_the_same_reconstruction_are_byte_identical(self):
        temp, root = _make_runtime()
        self.addCleanup(temp.cleanup)
        sessions = probe.available_sessions(root, start="2026-07-01", end="2026-07-05")
        cohort = probe.reconstruct_cohort_sessions(root, sessions=sessions)
        first = probe.build_artifact(cohort=cohort, sessions=sessions)
        second = probe.build_artifact(cohort=cohort, sessions=sessions)
        self.assertEqual(first["artifact_identity"], second["artifact_identity"])
        self.assertEqual(first, second)

    def test_insufficient_lookback_sessions_are_recorded_as_explicit_exclusions_not_skipped_silently(self):
        temp, root = _make_runtime()
        self.addCleanup(temp.cleanup)
        cohort = probe.reconstruct_cohort_sessions(root, sessions=["2026-06-05"])
        self.assertIn("2026-06-05", cohort["session_exclusions"])
        self.assertEqual(cohort["reconstructions"], {})


if __name__ == "__main__":
    unittest.main()
