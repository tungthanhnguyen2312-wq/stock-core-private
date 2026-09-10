import copy
import inspect
import unittest
from unittest import mock

import price_basis_feature_fitness as basis
import tactical_reversal_retrospective_validation as validation
import watchlist_tactical_entry_classifier as classifier


SESSION = "2026-08-21"


def _technical(*, basis_name="ADJUSTED_RETROSPECTIVE"):
    return {
        "status": "SHADOW_ONLY", "is_current_session": True,
        "feature_as_of_session": SESSION, "price_basis": basis_name,
        "technical_history_provenance": {"source": "TEST_RETAINED_SERIES"},
        "values": {
            "close": 100.0, "ma_20": 105.0, "momentum_20d": -0.02,
            "return_1d": 0.01, "volatility_20d": 0.02,
        },
    }


def _inputs(*, target_session=SESSION):
    descriptive = {
        "session": target_session,
        "records": {"SSI": {
            "technical_features": _technical(), "trend_state": "AT_OR_BELOW_MA20",
        }},
        "market_breadth": {
            "breadth_descriptor": {"descriptor": "MARKET_BREADTH_MIXED"},
            "momentum_descriptor": {"descriptor": "MOMENTUM_BREADTH_NEGATIVE"},
            "volatility": {"median": 0.03},
        },
    }
    screening = {"session": target_session, "records": {"SSI": {}}
    }
    tactical_record = {
        "entry_state": "SELLING_PRESSURE_EASING", "entry_action": "WAIT", "action": "WAIT",
        "rule_id": "R8_SELLING_PRESSURE_EASING", "signals": {"close": 100.0, "ma_20": 105.0},
    }
    tactical = {"session": target_session, "records": {"SSI": tactical_record}}
    fundamental = {"records": {"SSI": {"authority_tier": "OFFICIAL_QUALIFIED"}}}
    return {"descriptive": descriptive, "screening": screening, "tactical": tactical, "fundamental": fundamental}


def _selection():
    return {
        name: {"artifact_identity": f"{name}:fixture", "path": f"fixtures/{name}.json"}
        for name in ("descriptive", "screening", "tactical", "fundamental")
    }


def _replayed_artifact():
    return {
        "records": {"SSI": {
            "entry_state": "SELLING_PRESSURE_EASING", "entry_action": "WAIT", "action": "WAIT",
            "rule_id": "R8_SELLING_PRESSURE_EASING", "signals": {"close": 100.0, "ma_20": 105.0},
            "market_state": "MIXED_NO_CLEAR_MARKET_REGIME", "fundamental_context": {"authority_tier": "OFFICIAL_QUALIFIED"},
        }}
    }


class ReplayUsesExistingClassifierTests(unittest.TestCase):
    def test_replay_invokes_existing_classifier_not_a_duplicate_rule_table(self):
        inputs = _inputs()
        with mock.patch.object(classifier, "build_artifact", return_value=_replayed_artifact()) as build:
            result = validation.replay_registered_session(
                session=SESSION, inputs=inputs, selection=_selection(), tickers=("SSI",),
            )
        build.assert_called_once_with(
            descriptive_source=inputs["descriptive"], screening_source=inputs["screening"],
            fundamental_source=inputs["fundamental"], requested_at="RETAINED_REPLAY:2026-08-21",
        )
        self.assertEqual(result["records"]["SSI"]["entry_state"], "SELLING_PRESSURE_EASING")
        self.assertNotIn("_entry_state_rule", inspect.getsource(validation))

    def test_future_session_input_is_rejected_before_classifier_invocation(self):
        inputs = _inputs()
        inputs["screening"]["session"] = "2026-08-22"
        with self.assertRaisesRegex(validation.TacticalReversalReplayError, "FUTURE_SESSION_INPUT_REJECTED:screening"):
            validation.assert_no_future_session_input(target_session=SESSION, inputs=inputs)

    def test_missing_historical_window_is_not_replayable(self):
        result = validation._target_window_replayability("SSI", ["2026-08-21", "2026-09-10"])
        self.assertEqual(result["qualification"], validation.NOT_REPLAYABLE)
        self.assertIn("NO_RETAINED_COHERENT_CLASSIFIER_SNAPSHOT", result["reason_codes"][0])


class BasisAndTimingGuardTests(unittest.TestCase):
    def test_raw_and_current_adjusted_prices_cannot_be_mixed_in_return_calculation(self):
        raw_context = basis.price_series_context(
            ticker="SSI", provider="TEST", source_identity="raw", session_start=SESSION, session_end=SESSION,
            observed_basis=basis.RAW_AS_TRADED, basis_provenance=["fixture"],
        )
        adjusted_context = basis.price_series_context(
            ticker="SSI", provider="TEST", source_identity="adjusted", session_start=SESSION, session_end=SESSION,
            observed_basis=basis.CURRENT_RETROSPECTIVE_ADJUSTED, basis_provenance=["fixture"],
        )
        start = {"feature_basis_fitness": {"context": raw_context, "strict_cross_session_fitness": {"state": basis.BASIS_COMPATIBLE}}}
        end = {"feature_basis_fitness": {"context": adjusted_context, "strict_cross_session_fitness": {"state": basis.BASIS_COMPATIBLE}}}
        result = validation.same_basis_return(start=start, end=end, start_price=100.0, end_price=110.0)
        self.assertEqual(result["status"], "NOT_COMPUTED")
        self.assertEqual(result["reason_codes"], [basis.REASON_BASIS_MISMATCH])

    def test_basis_unverified_blocks_pit_but_allows_labelled_research_replay(self):
        technical = _technical()
        price_fitness = validation.price_replay_fitness(
            ticker="SSI", technical_features=technical, source_artifact_identity="descriptive:fixture", session=SESSION,
        )
        self.assertEqual(price_fitness["strict_cross_session_fitness"]["state"], basis.BASIS_UNVERIFIED)
        self.assertEqual(price_fitness["pit_feature_fitness"]["state"], basis.POINT_IN_TIME_SEMANTICS_UNQUALIFIED)
        self.assertEqual(
            validation.replay_qualification(temporal_inputs={"descriptive": {}}, price_fitness=price_fitness),
            validation.RETROSPECTIVE_RESEARCH_REPLAY,
        )

    def test_first_state_transition_is_deterministic(self):
        rows = [
            {"session": "2026-08-21", "entry_state": "DOWNTREND"},
            {"session": "2026-08-24", "entry_state": "DOWNTREND"},
            {"session": "2026-08-25", "entry_state": "SELLING_PRESSURE_EASING"},
        ]
        result = validation.first_transition(rows)
        self.assertEqual(result, {"session": "2026-08-25", "from": "DOWNTREND", "to": "SELLING_PRESSURE_EASING", "field": "entry_state"})

    def test_false_start_lower_low_logic(self):
        rows = [
            {"session": "2026-08-21", "entry_action": "WAIT", "comparable_price": 100.0},
            {"session": "2026-08-24", "entry_action": "EARLY_ENTRY", "comparable_price": 102.0},
            {"session": "2026-08-25", "entry_action": "WAIT", "comparable_price": 99.0},
        ]
        result = validation.detect_false_start(rows)
        self.assertTrue(result["lower_low_after_first_early_signal"])
        self.assertEqual(result["lower_low_session"], "2026-08-25")


class PolicyBoundaryTests(unittest.TestCase):
    def test_reporting_thresholds_do_not_change_classifier_policy(self):
        self.assertEqual(classifier.ENTRY_ACTION_BY_ENTRY_STATE["EARLY_REVERSAL_CANDIDATE"], "EARLY_ENTRY")
        self.assertEqual(classifier.RULE_DEFINITIONS["R6_EARLY_REVERSAL_CANDIDATE"], (
            "Price at or below the 20-day moving average but 20-day momentum has turned positive -- "
            "momentum inflecting before price structure confirms -- AND at least one independent "
            "confirming signal: same-session market-relative momentum in the upper half of the market "
            "cohort, same-session sector-relative momentum in the upper half of its own sector cohort, "
            "or today's return positive together with today's provider-relative volume above the "
            "cohort median."
        ))
        self.assertEqual(validation.TIMING_THRESHOLDS["near_low_max_sessions_after_low"], 2)


if __name__ == "__main__":
    unittest.main()
