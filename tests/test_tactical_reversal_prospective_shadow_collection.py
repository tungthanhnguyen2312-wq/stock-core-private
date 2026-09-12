import copy
import inspect
import json
import tempfile
import unittest
from pathlib import Path

import tactical_reversal_prospective_shadow_collection as collection


R8 = "R8_SELLING_PRESSURE_EASING"
R9 = "R9_DOWNTREND_DEFAULT"
R6 = "R6_EARLY_REVERSAL_CANDIDATE"
R3 = "R3_UPTREND_CONFIRMED_DEFAULT"
R2 = "R2_BREAKOUT_READY_CONFIRMED"
DESCRIPTIVE_BASIS = "market_wide_current_descriptive_research"


def _record(*, rule_id, close=10.0, momentum_bucket=None, entry_state="SELLING_PRESSURE_EASING", entry_action="WAIT"):
    return {
        "entry_state": entry_state, "entry_action": entry_action, "rule_id": rule_id,
        "signals": {"close": close, "momentum_bucket": momentum_bucket},
    }


def _artifact(session, records, *, descriptive_hash="abc123"):
    return {
        "session": session,
        "artifact_identity": f"watchlist_tactical_entry_classifier:fake-{session}",
        "source_artifacts": {"descriptive": f"{DESCRIPTIVE_BASIS}:{descriptive_hash}"},
        "records": records,
    }


def _future_row(session, record, *, basis=DESCRIPTIVE_BASIS):
    return {"session": session, "record": record, "price_basis_identity": basis}


class ActivationBoundaryTests(unittest.TestCase):
    def test_historical_bootstrap_session_is_tagged_non_prospective(self):
        self.assertEqual(collection.evidence_mode_for_session("2026-09-11"), collection.BOOTSTRAP_NON_PROSPECTIVE)
        self.assertEqual(collection.evidence_mode_for_session("2026-08-25"), collection.BOOTSTRAP_NON_PROSPECTIVE)

    def test_first_post_activation_session_is_prospective(self):
        self.assertEqual(collection.evidence_mode_for_session("2026-09-12"), collection.PROSPECTIVE)
        self.assertEqual(collection.evidence_mode_for_session("2026-12-01"), collection.PROSPECTIVE)


class ObservationBuildTests(unittest.TestCase):
    def test_t0_observation_is_deterministic_and_immutable_across_reruns(self):
        current = _artifact("2026-09-12", {"XXX": _record(rule_id=R8, momentum_bucket="UPPER_QUARTILE")})
        before = copy.deepcopy(current)
        first = collection.build_prospective_observation(ticker="XXX", trigger_session="2026-09-12", current_tactical_artifact=current)
        second = collection.build_prospective_observation(ticker="XXX", trigger_session="2026-09-12", current_tactical_artifact=current)
        self.assertEqual(current, before)
        self.assertEqual(first, second)
        self.assertEqual(first["observation_id"], second["observation_id"])
        self.assertTrue(collection.observation_identity_valid(first))

    def test_candidate_a_retained_on_observation(self):
        current = _artifact("2026-09-12", {"XXX": _record(rule_id=R8, momentum_bucket="UPPER_QUARTILE")})
        obs = collection.build_prospective_observation(ticker="XXX", trigger_session="2026-09-12", current_tactical_artifact=current)
        self.assertTrue(obs["candidate_a"]["eligible"])
        self.assertIn("R8_WITH_MARKET_RELATIVE_MOMENTUM_UPPER_HALF", obs["candidate_a"]["reason_codes"])

    def test_candidate_b_retained_on_observation(self):
        current = _artifact("2026-09-12", {"XXX": _record(rule_id=R8, momentum_bucket="LOWER_MIDDLE")})
        prior = _artifact("2026-09-11", {"XXX": _record(rule_id=R8, momentum_bucket="LOWER_MIDDLE")})
        obs = collection.build_prospective_observation(
            ticker="XXX", trigger_session="2026-09-12", current_tactical_artifact=current,
            prior_session="2026-09-11", prior_tactical_artifact=prior,
        )
        self.assertTrue(obs["candidate_b"]["eligible"])
        self.assertEqual(obs["prior_trigger_session"], "2026-09-11")
        self.assertEqual(obs["prior_source_classifier_state"]["rule_id"], R8)

    def test_a_and_b_preserved_independently_when_both_fire(self):
        current = _artifact("2026-09-12", {"XXX": _record(rule_id=R8, momentum_bucket="UPPER_MIDDLE")})
        prior = _artifact("2026-09-11", {"XXX": _record(rule_id=R8, momentum_bucket="UPPER_MIDDLE")})
        obs = collection.build_prospective_observation(
            ticker="XXX", trigger_session="2026-09-12", current_tactical_artifact=current,
            prior_session="2026-09-11", prior_tactical_artifact=prior,
        )
        self.assertTrue(obs["candidate_a"]["eligible"])
        self.assertTrue(obs["candidate_b"]["eligible"])
        self.assertNotIn("blended_score", obs)
        self.assertNotIn("score", obs)

    def test_candidate_c_never_appears_on_an_observation(self):
        current = _artifact("2026-09-12", {"XXX": _record(rule_id=R8, momentum_bucket="LOWER_MIDDLE")})
        obs = collection.build_prospective_observation(ticker="XXX", trigger_session="2026-09-12", current_tactical_artifact=current)
        # Candidate C is required to be *named* as rejected (excluded_candidates), but must
        # never exist as its own active field, never be evaluated, and never contribute an
        # eligible=True verdict anywhere on the observation.
        self.assertNotIn("candidate_c", obs)
        self.assertIn("CANDIDATE_C_R8_VOLUME_RETURN_NO_BREAKDOWN_QUARTILE", obs["excluded_candidates"])
        self.assertEqual(set(obs["excluded_candidates"]), {"CANDIDATE_C_R8_VOLUME_RETURN_NO_BREAKDOWN_QUARTILE"})
        for field in ("candidate_a", "candidate_b"):
            self.assertNotIn("CANDIDATE_C", json.dumps(obs[field]))

    def test_candidate_b_unevaluable_on_missing_adjacent_history(self):
        current = _artifact("2026-09-12", {"XXX": _record(rule_id=R8, momentum_bucket="LOWER_MIDDLE")})
        obs = collection.build_prospective_observation(
            ticker="XXX", trigger_session="2026-09-12", current_tactical_artifact=current,
            prior_session=None, prior_tactical_artifact=None, prior_evidence_supplied=True,
        )
        self.assertIsNone(obs["candidate_b"]["eligible"])
        self.assertIn("PRIOR_SESSION_GAP", obs["candidate_b"]["reason_codes"])

    def test_future_field_injection_cannot_alter_t0_eligibility(self):
        current = _artifact("2026-09-12", {"XXX": _record(rule_id=R8, momentum_bucket="LOWER_MIDDLE")})
        prior = _artifact("2026-09-11", {"XXX": _record(rule_id=R8, momentum_bucket="LOWER_MIDDLE")})
        baseline = collection.build_prospective_observation(
            ticker="XXX", trigger_session="2026-09-12", current_tactical_artifact=current,
            prior_session="2026-09-11", prior_tactical_artifact=prior,
        )
        adversarial_current = copy.deepcopy(current)
        adversarial_current["records"]["XXX"]["future_outcome_lower_low"] = True
        adversarial_current["records"]["XXX"]["next_session_rule_id"] = R9
        adversarial_prior = copy.deepcopy(prior)
        adversarial_prior["records"]["XXX"]["future_outcome_lower_low"] = True
        mutated = collection.build_prospective_observation(
            ticker="XXX", trigger_session="2026-09-12", current_tactical_artifact=adversarial_current,
            prior_session="2026-09-11", prior_tactical_artifact=adversarial_prior,
        )
        self.assertEqual(baseline["candidate_a"], mutated["candidate_a"])
        self.assertEqual(baseline["candidate_b"], mutated["candidate_b"])
        self.assertEqual(baseline["shadow_disposition"], mutated["shadow_disposition"])

    def test_shadow_collection_failure_does_not_mutate_the_source_artifact(self):
        current = _artifact("2026-09-12", {"XXX": _record(rule_id=R8)})
        before = copy.deepcopy(current)
        with self.assertRaises(collection.ProspectiveShadowCollectionError):
            collection.build_prospective_observation(ticker="NOT_PRESENT", trigger_session="2026-09-12", current_tactical_artifact=current)
        self.assertEqual(current, before)


class StoreTests(unittest.TestCase):
    def test_rerun_identity_is_deterministic_and_persist_is_idempotent(self):
        current = _artifact("2026-09-12", {"XXX": _record(rule_id=R8, momentum_bucket="UPPER_QUARTILE")})
        observation = collection.build_prospective_observation(ticker="XXX", trigger_session="2026-09-12", current_tactical_artifact=current)
        with tempfile.TemporaryDirectory() as tmp:
            store = collection.ProspectiveShadowObservationStore(tmp)
            first = store.persist_observation(observation)
            second = store.persist_observation(observation)
            self.assertEqual(first, second)
            self.assertEqual(store.list_observation_ids(), [observation["observation_id"]])

    def test_t0_observation_content_unchanged_after_future_enrichment(self):
        current = _artifact("2026-09-12", {"XXX": _record(rule_id=R8, momentum_bucket="UPPER_QUARTILE", close=10.0)})
        observation = collection.build_prospective_observation(ticker="XXX", trigger_session="2026-09-12", current_tactical_artifact=current)
        with tempfile.TemporaryDirectory() as tmp:
            store = collection.ProspectiveShadowObservationStore(tmp)
            saved = store.persist_observation(observation)
            future_rows = [_future_row(f"2026-09-{d}", _record(rule_id=R9, close=9.0)) for d in range(15, 20)]
            outcome = collection.mature_outcome(saved, future_rows, evaluation_as_of_session="2026-09-19")
            store.persist_outcome_update(saved["observation_id"], outcome)
            reloaded = store.load_observation(saved["observation_id"])
            self.assertEqual(reloaded, saved)
            self.assertEqual(reloaded, observation)


class HorizonLifecycleTests(unittest.TestCase):
    def _observation(self, close=10.0):
        current = _artifact("2026-09-12", {"XXX": _record(rule_id=R8, momentum_bucket="UPPER_QUARTILE", close=close)})
        return collection.build_prospective_observation(ticker="XXX", trigger_session="2026-09-12", current_tactical_artifact=current)

    def test_t5_pending_before_five_completed_trading_sessions(self):
        observation = self._observation()
        future_rows = [_future_row(f"2026-09-{d}", _record(rule_id=R9, close=9.0)) for d in range(15, 18)]
        outcome = collection.mature_outcome(observation, future_rows, evaluation_as_of_session="2026-09-17")
        self.assertEqual(outcome["horizons"]["T5"]["status"], collection.PENDING_HORIZON)
        self.assertIsNone(outcome["horizons"]["T5"].get("return_pct"))

    def test_t5_complete_only_after_five_real_sessions(self):
        observation = self._observation()
        future_rows = [_future_row(f"2026-09-{d}", _record(rule_id=R9, close=9.0)) for d in range(15, 20)]
        outcome = collection.mature_outcome(observation, future_rows, evaluation_as_of_session="2026-09-19")
        self.assertEqual(outcome["horizons"]["T5"]["status"], "MATURE")
        self.assertEqual(outcome["horizons"]["T5"]["horizon_session"], "2026-09-19")

    def test_t10_lifecycle_pending_then_mature(self):
        observation = self._observation()
        seven = [_future_row(f"2026-09-{d}", _record(rule_id=R9, close=9.0)) for d in range(15, 22)]
        pending = collection.mature_outcome(observation, seven, evaluation_as_of_session=seven[-1]["session"])
        self.assertEqual(pending["horizons"]["T10"]["status"], collection.PENDING_HORIZON)
        ten = [_future_row(f"2026-09-{15+i}", _record(rule_id=R9, close=9.0)) for i in range(10)]
        mature = collection.mature_outcome(observation, ten, evaluation_as_of_session=ten[-1]["session"])
        self.assertEqual(mature["horizons"]["T10"]["status"], "MATURE")

    def test_t20_lifecycle_pending_then_mature(self):
        observation = self._observation()
        fifteen = [_future_row(f"session_{i:03d}", _record(rule_id=R9, close=9.0)) for i in range(15)]
        pending = collection.mature_outcome(observation, fifteen, evaluation_as_of_session=fifteen[-1]["session"])
        self.assertEqual(pending["horizons"]["T20"]["status"], collection.PENDING_HORIZON)
        twenty = [_future_row(f"session_{i:03d}", _record(rule_id=R9, close=9.0)) for i in range(20)]
        mature = collection.mature_outcome(observation, twenty, evaluation_as_of_session=twenty[-1]["session"])
        self.assertEqual(mature["horizons"]["T20"]["status"], "MATURE")

    def test_trading_session_counting_not_calendar_day_counting(self):
        observation = self._observation()
        # Large calendar gaps (holiday weekends etc.) between five retained trading
        # sessions must still count as exactly five sessions, not zero/partial by date math.
        sparse_dates = ["2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12"]
        future_rows = [_future_row(session, _record(rule_id=R9, close=9.0)) for session in sparse_dates]
        outcome = collection.mature_outcome(observation, future_rows, evaluation_as_of_session=sparse_dates[-1])
        self.assertEqual(outcome["horizons"]["T5"]["status"], "MATURE")
        self.assertEqual(outcome["retained_future_session_count"], 5)

    def test_incomplete_horizon_never_imputed(self):
        observation = self._observation()
        future_rows = [_future_row("2026-09-15", _record(rule_id=R9, close=9.0))]
        outcome = collection.mature_outcome(observation, future_rows, evaluation_as_of_session="2026-09-15")
        for name in collection.HORIZONS:
            self.assertEqual(outcome["horizons"][name]["status"], collection.PENDING_HORIZON)
            self.assertNotIn("return_pct", outcome["horizons"][name])
            self.assertNotIn("mae_pct", outcome["horizons"][name])


class DeterministicMetricTests(unittest.TestCase):
    def test_mae_is_deterministic(self):
        observation = HorizonLifecycleTests()._observation(close=10.0)
        future_rows = [_future_row(f"2026-09-{d}", _record(rule_id=R9, close=c)) for d, c in zip(range(15, 20), [9.5, 8.0, 9.0, 10.5, 11.0])]
        first = collection.mature_outcome(observation, future_rows, evaluation_as_of_session="2026-09-19")
        second = collection.mature_outcome(observation, future_rows, evaluation_as_of_session="2026-09-19")
        self.assertEqual(first["horizons"]["T5"]["mae_pct"], second["horizons"]["T5"]["mae_pct"])
        self.assertAlmostEqual(first["horizons"]["T5"]["mae_pct"], -0.2)

    def test_mfe_is_deterministic(self):
        observation = HorizonLifecycleTests()._observation(close=10.0)
        future_rows = [_future_row(f"2026-09-{d}", _record(rule_id=R9, close=c)) for d, c in zip(range(15, 20), [9.5, 8.0, 9.0, 10.5, 11.0])]
        first = collection.mature_outcome(observation, future_rows, evaluation_as_of_session="2026-09-19")
        second = collection.mature_outcome(observation, future_rows, evaluation_as_of_session="2026-09-19")
        self.assertEqual(first["horizons"]["T5"]["mfe_pct"], second["horizons"]["T5"]["mfe_pct"])
        self.assertAlmostEqual(first["horizons"]["T5"]["mfe_pct"], 0.1)

    def test_lower_low_accounting(self):
        observation = HorizonLifecycleTests()._observation(close=10.0)
        future_rows = [_future_row(f"2026-09-{d}", _record(rule_id=R9, close=c)) for d, c in zip(range(15, 20), [10.5, 9.0, 11.0, 11.5, 12.0])]
        outcome = collection.mature_outcome(observation, future_rows, evaluation_as_of_session="2026-09-19")
        self.assertTrue(outcome["horizons"]["T5"]["lower_low_within_horizon"])
        self.assertEqual(outcome["horizons"]["T5"]["sessions_to_first_lower_low"], 2)

    def test_confirmation_lag_accounting(self):
        observation = HorizonLifecycleTests()._observation(close=10.0)
        future_rows = [
            _future_row("2026-09-15", _record(rule_id=R9, close=9.5)),
            _future_row("2026-09-16", _record(rule_id=R9, close=9.0)),
            _future_row("2026-09-17", _record(rule_id=R6, close=10.5)),
        ]
        outcome = collection.mature_outcome(observation, future_rows, evaluation_as_of_session="2026-09-17")
        self.assertEqual(outcome["confirmation_transitions"]["first_R6"]["status"], "COMPLETE")
        self.assertEqual(outcome["confirmation_transitions"]["first_R6"]["sessions_to_event"], 3)
        self.assertEqual(outcome["first_confirmation"]["rule_id"], R6)
        self.assertEqual(outcome["first_confirmation"]["sessions_to_event"], 3)

    def test_unsuitable_price_basis_becomes_unevaluable(self):
        observation = HorizonLifecycleTests()._observation(close=10.0)
        future_rows = [_future_row(f"2026-09-{d}", _record(rule_id=R9, close=9.0), basis="A_DIFFERENT_BASIS_METHOD") for d in range(15, 20)]
        outcome = collection.mature_outcome(observation, future_rows, evaluation_as_of_session="2026-09-19")
        self.assertEqual(outcome["horizons"]["T5"]["status"], collection.BASIS_UNEVALUABLE)


class AggregateCollectionStatusTests(unittest.TestCase):
    def _built(self, ticker, trigger_session, rule_id, momentum_bucket, prior_rule_id=None):
        current = _artifact(trigger_session, {ticker: _record(rule_id=rule_id, momentum_bucket=momentum_bucket)})
        prior = None
        if prior_rule_id is not None:
            prior_session = "2026-09-11" if trigger_session != "2026-09-11" else "2026-09-10"
            prior = _artifact(prior_session, {ticker: _record(rule_id=prior_rule_id, momentum_bucket=momentum_bucket)})
            return collection.build_prospective_observation(
                ticker=ticker, trigger_session=trigger_session, current_tactical_artifact=current,
                prior_session=prior_session, prior_tactical_artifact=prior,
            )
        return collection.build_prospective_observation(ticker=ticker, trigger_session=trigger_session, current_tactical_artifact=current)

    def test_bootstrap_records_excluded_from_prospective_aggregate(self):
        bootstrap = self._built("AAA", "2026-09-11", R8, "UPPER_QUARTILE")  # A-only, bootstrap
        status = collection.build_collection_status([bootstrap], {})
        self.assertEqual(status["prospective_observation_count"], 0)
        self.assertEqual(status["overall_status"], "NO_PROSPECTIVE_OBSERVATIONS_YET")
        self.assertEqual(status["bootstrap_observation_count"], 1)
        self.assertEqual(status["bootstrap_cohorts_regression_only"]["A_ONLY"], 1)

    def test_a_b_a_and_b_control_cohorts_preserved_separately(self):
        a_only = self._built("AAA", "2026-09-12", R8, "UPPER_QUARTILE")
        b_only = self._built("BBB", "2026-09-12", R8, "LOWER_MIDDLE", prior_rule_id=R8)
        a_and_b = self._built("CCC", "2026-09-12", R8, "UPPER_MIDDLE", prior_rule_id=R8)
        neither = self._built("DDD", "2026-09-12", R8, "LOWER_MIDDLE")
        not_control = self._built("EEE", "2026-09-12", R9, None)
        observations = [a_only, b_only, a_and_b, neither, not_control]
        status = collection.build_collection_status(observations, {})
        self.assertEqual(status["prospective_observation_count"], 5)
        cohorts = status["prospective_cohorts"]
        self.assertEqual(cohorts["A_ONLY"], 1)
        self.assertEqual(cohorts["B_ONLY"], 1)
        self.assertEqual(cohorts["A_AND_B"], 1)
        self.assertEqual(cohorts["R8_NEITHER"], 1)
        self.assertEqual(cohorts["NOT_R8_CONTROL_POPULATION"], 1)


class NoInvestmentAuthorityTests(unittest.TestCase):
    def test_no_probability_target_or_sizing_fields_anywhere(self):
        current = _artifact("2026-09-12", {"XXX": _record(rule_id=R8, momentum_bucket="UPPER_QUARTILE")})
        observation = collection.build_prospective_observation(ticker="XXX", trigger_session="2026-09-12", current_tactical_artifact=current)
        future_rows = [_future_row(f"2026-09-{d}", _record(rule_id=R9, close=9.0)) for d in range(15, 20)]
        outcome = collection.mature_outcome(observation, future_rows, evaluation_as_of_session="2026-09-19")
        # The one expected, deliberate occurrence of "probability" is the boundary flag
        # itself asserting its own absence; strip that known-safe key/value before scanning.
        safe_marker = '"no_probability_target_or_sizing_emitted": true'
        observation_text = json.dumps(observation).lower().replace(safe_marker, "")
        outcome_text = json.dumps(outcome).lower().replace(safe_marker, "")
        for forbidden in ("probability", "target_price", "position_size", "expected_return", "confidence_score", "win_rate"):
            self.assertNotIn(forbidden, observation_text)
            self.assertNotIn(forbidden, outcome_text)
        self.assertTrue(observation["no_probability_target_or_sizing_emitted"])
        self.assertTrue(outcome["no_probability_target_or_sizing_emitted"])


class ProductionSurfaceUnchangedGuardTests(unittest.TestCase):
    """This module is a read-only consumer; it must never import production decision
    surfaces at all, since that is a stronger guarantee than merely not calling them."""

    FORBIDDEN_IMPORTS = (
        "import watchlist_tactical_entry_classifier",
        "import canonical_daily_operation",
        "import daily_producer_pipeline",
        "import canonical_post_close_pipeline",
        "import daily_integrated_decision_brief",
        "import integrated_investment_decision_product",
    )

    def test_module_never_imports_production_classifier_or_daily_surfaces(self):
        source = inspect.getsource(collection)
        for forbidden in self.FORBIDDEN_IMPORTS:
            self.assertNotIn(forbidden, source)

    def test_module_delegates_eligibility_to_the_unmodified_shadow_policy_module(self):
        source = inspect.getsource(collection)
        self.assertIn("import tactical_reversal_shadow_probe_policy as shadow", source)
        self.assertIn("shadow.evaluate_shadow_probe(", source)


if __name__ == "__main__":
    unittest.main()
