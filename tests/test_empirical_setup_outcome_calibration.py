"""Synthetic-fixture tests for EMPIRICAL_SETUP_OUTCOME_CALIBRATION_V1.

Every fixture below builds real feedback-record-shaped inputs by actually calling the reused
``integrated_decision_prospective_feedback``/``prospective_decision_outcome_feedback``/
``prospective_decision_retention`` primitives over a synthetic session chain and price
snapshots -- never a hand-mocked shortcut that could drift from the real shape those modules
produce. No real corpus data appears anywhere in this file.
"""
from __future__ import annotations

import datetime as dt

import empirical_setup_outcome_calibration as calib
import integrated_decision_prospective_feedback as feedback_bridge
import prospective_decision_outcome_feedback as outcome_feedback
import prospective_decision_retention as retention


def make_chain(length: int) -> list[str]:
    start = dt.date(2026, 1, 1)
    return [(start + dt.timedelta(days=i)).isoformat() for i in range(length)]


def make_snapshots(chain: list[str], prices: dict[str, dict[str, float]]) -> dict[str, dict]:
    """``prices``: {ticker: {session: close}}. Every session in the chain gets a snapshot row."""
    snapshots: dict[str, dict] = {}
    for session in chain:
        records = {}
        for ticker, series in prices.items():
            if session in series:
                records[ticker] = {"observations": [{
                    "session": session, "close": series[session],
                    "price_basis": "ADJUSTED_RETROSPECTIVE", "transformation_identity": "TEST_BASIS_V1",
                }]}
        snapshots[session] = {"resolved_completed_session": session, "snapshot_identity": f"snap:{session}", "records": records}
    return snapshots


def make_condition(level: float, operator: str, role: str = "invalidation") -> dict:
    payload = {
        "condition_version": retention.CONDITION_CONTRACT_VERSION, "role": role, "status": "MACHINE_EVALUABLE",
        "operator": operator, "reference_field": "close", "reference_level": level,
        "activation_semantics": "TEST_FIXED_T0_LEVEL", "source_rule": "TEST", "reason_codes": [],
    }
    return retention._identity(payload, "retained_strategy_boundary_condition:", "condition_identity")


def make_feedback_record(
    *, ticker: str, t0_session: str, posture: str, entry: float, invalidation_level: float | None,
    chain: list[str], snapshots: dict, tactical_state: str = "BREAKOUT_CONFIRMED",
    invalidation_method: str = "TEST_METHOD", market_regime: str = "NEUTRAL_MIXED",
) -> dict:
    invalidation_condition = make_condition(invalidation_level, "<", role="invalidation") if invalidation_level is not None else None
    decision_record = {
        "ticker": ticker, "as_of_session": t0_session, "decision_identity": f"decision:{ticker}:{t0_session}",
        "research_action_posture": posture,
        "trigger": {"trigger_level": entry, "condition": None},
        "invalidation": {"invalidation_level": invalidation_level, "invalidation_method": invalidation_method, "condition": invalidation_condition},
    }
    forward_outcomes = feedback_bridge.evaluate_decision_forward_outcome(
        decision_record=decision_record, p3f9b_snapshot=None, governed_chain=chain, retained_session_snapshots=snapshots,
    )
    trigger_invalidation_outcome = outcome_feedback._trigger_invalidation(decision_record, snapshots=snapshots, chain=chain)
    return {
        **decision_record, "decision_session": t0_session, "feedback_identity": f"feedback:{ticker}:{t0_session}",
        "t0_snapshot_identity": None, "tactical_structure_state": tactical_state, "market_sector_state": market_regime,
        "forward_outcomes": forward_outcomes, "trigger_invalidation_outcome": trigger_invalidation_outcome,
    }


# ── 1. No look-ahead / exact session-counted maturation ────────────────────────────────────────

def test_horizon_requires_exactly_n_later_completed_sessions_never_calendar_days():
    chain = make_chain(30)
    t0 = chain[0]
    prices = {"AAA": {session: 100.0 for session in chain}}
    prices["AAA"][chain[5]] = 110.0  # the exact T5 session
    prices["AAA"][chain[4]] = 999.0  # one session too early -- must never leak into T5's return
    snapshots = make_snapshots(chain, prices)
    record = make_feedback_record(ticker="AAA", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=90.0, chain=chain, snapshots=snapshots)
    observation = calib.build_observation(record, chain=chain, snapshots=snapshots)
    t5 = observation["horizons"]["T5"]
    assert t5["status"] == "MATURE"
    assert abs(t5["forward_return"] - 0.10) < 1e-9  # uses chain[5]'s close (110), not chain[4]'s (999)


def test_pending_future_depth_when_chain_too_short():
    chain = make_chain(3)  # T0 plus only 2 later sessions -- not enough for any horizon
    t0 = chain[0]
    prices = {"AAA": {session: 100.0 for session in chain}}
    snapshots = make_snapshots(chain, prices)
    record = make_feedback_record(ticker="AAA", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=90.0, chain=chain, snapshots=snapshots)
    observation = calib.build_observation(record, chain=chain, snapshots=snapshots)
    for horizon in ("T5", "T10", "T20", "T60"):
        assert observation["horizons"][horizon]["status"] == feedback_bridge.PENDING
        assert observation["horizons"][horizon]["forward_return"] is None


def test_t60_maturation_uses_the_new_horizon_not_available_upstream():
    chain = make_chain(70)
    t0 = chain[0]
    prices = {"AAA": {session: 100.0 for session in chain}}
    prices["AAA"][chain[60]] = 150.0
    snapshots = make_snapshots(chain, prices)
    record = make_feedback_record(ticker="AAA", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=90.0, chain=chain, snapshots=snapshots)
    observation = calib.build_observation(record, chain=chain, snapshots=snapshots)
    t60 = observation["horizons"]["T60"]
    assert t60["status"] == "MATURE"
    assert abs(t60["forward_return"] - 0.50) < 1e-9


# ── 2. MFE / MAE close-proxy ─────────────────────────────────────────────────────────────────

def test_mfe_mae_close_proxy_over_the_horizon_window():
    chain = make_chain(15)
    t0 = chain[0]
    series = {session: 100.0 for session in chain}
    series[chain[2]] = 120.0  # favorable excursion within the T5 window
    series[chain[4]] = 80.0   # adverse excursion within the T5 window, also the T5 close itself
    prices = {"AAA": series}
    snapshots = make_snapshots(chain, prices)
    record = make_feedback_record(ticker="AAA", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=70.0, chain=chain, snapshots=snapshots)
    observation = calib.build_observation(record, chain=chain, snapshots=snapshots)
    t5 = observation["horizons"]["T5"]
    assert abs(t5["mfe_close_proxy"] - 0.20) < 1e-9
    assert abs(t5["mae_close_proxy"] - (-0.20)) < 1e-9
    assert t5["close_path_semantics"] == "CLOSE_ONLY_NOT_INTRADAY_MFE_MAE"


# ── 3. R-multiple calculation ────────────────────────────────────────────────────────────────

def test_r_multiple_uses_t0_invalidation_as_denominator():
    chain = make_chain(10)
    t0 = chain[0]
    prices = {"AAA": {session: 100.0 for session in chain}}
    prices["AAA"][chain[5]] = 110.0  # +10% return; downside fraction (100-90)/100 = 0.10 -> R = 1.0
    snapshots = make_snapshots(chain, prices)
    record = make_feedback_record(ticker="AAA", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=90.0, chain=chain, snapshots=snapshots)
    observation = calib.build_observation(record, chain=chain, snapshots=snapshots)
    t5 = observation["horizons"]["T5"]
    assert abs(t5["r_multiple"] - 1.0) < 1e-9
    assert t5["r_multiple_status"] == "AVAILABLE"


def test_r_multiple_unavailable_without_t0_invalidation():
    chain = make_chain(10)
    t0 = chain[0]
    prices = {"AAA": {session: 100.0 for session in chain}}
    prices["AAA"][chain[5]] = 110.0
    snapshots = make_snapshots(chain, prices)
    record = make_feedback_record(ticker="AAA", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=None, chain=chain, snapshots=snapshots)
    observation = calib.build_observation(record, chain=chain, snapshots=snapshots)
    t5 = observation["horizons"]["T5"]
    assert t5["r_multiple"] is None
    assert t5["r_multiple_status"] == "UNAVAILABLE_NO_T0_INVALIDATION"
    assert observation["r_multiple_denominator_status"] == "UNAVAILABLE_NO_T0_INVALIDATION"


# ── 4. Invalidation-hit ordering ────────────────────────────────────────────────────────────

def test_invalidation_hit_and_sessions_to_invalidation():
    chain = make_chain(15)
    t0 = chain[0]
    series = {session: 100.0 for session in chain}
    series[chain[3]] = 85.0  # crosses below the invalidation level of 90 at session index 3
    prices = {"AAA": series}
    snapshots = make_snapshots(chain, prices)
    record = make_feedback_record(ticker="AAA", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=90.0, chain=chain, snapshots=snapshots)
    observation = calib.build_observation(record, chain=chain, snapshots=snapshots)
    assert observation["invalidation"]["status"] == "SATISFIED"
    assert observation["invalidation"]["hit"] is True
    assert observation["invalidation"]["sessions_to_invalidation"] == 3


def test_invalidation_not_hit_yet():
    chain = make_chain(15)
    t0 = chain[0]
    prices = {"AAA": {session: 100.0 for session in chain}}
    snapshots = make_snapshots(chain, prices)
    record = make_feedback_record(ticker="AAA", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=90.0, chain=chain, snapshots=snapshots)
    observation = calib.build_observation(record, chain=chain, snapshots=snapshots)
    assert observation["invalidation"]["hit"] is False
    assert observation["invalidation"]["sessions_to_invalidation"] is None


# ── 5. Explicit-target ordering ──────────────────────────────────────────────────────────────

def test_target_hit_before_invalidation():
    chain = make_chain(15)
    t0 = chain[0]
    series = {session: 100.0 for session in chain}
    series[chain[2]] = 120.0  # hits target (115) at session 2
    series[chain[6]] = 80.0   # hits invalidation (90) later, at session 6
    prices = {"AAA": series}
    snapshots = make_snapshots(chain, prices)
    record = make_feedback_record(ticker="AAA", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=90.0, chain=chain, snapshots=snapshots)
    observation = calib.build_observation(record, chain=chain, snapshots=snapshots, target_level=115.0, target_direction="ABOVE")
    assert observation["target"]["status"] == "EVALUATED"
    assert observation["target"]["hit"] is True
    assert observation["target"]["sessions_to_target"] == 2
    assert observation["target_invalidation_ordering"] == "TARGET_BEFORE_INVALIDATION"


def test_invalidation_hit_before_target():
    chain = make_chain(15)
    t0 = chain[0]
    series = {session: 100.0 for session in chain}
    series[chain[2]] = 80.0    # hits invalidation (90) at session 2
    series[chain[6]] = 120.0   # would hit target (115) later, at session 6
    prices = {"AAA": series}
    snapshots = make_snapshots(chain, prices)
    record = make_feedback_record(ticker="AAA", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=90.0, chain=chain, snapshots=snapshots)
    observation = calib.build_observation(record, chain=chain, snapshots=snapshots, target_level=115.0, target_direction="ABOVE")
    assert observation["target_invalidation_ordering"] == "INVALIDATION_BEFORE_TARGET"


def test_target_absent_is_not_evaluated_never_invented():
    chain = make_chain(15)
    t0 = chain[0]
    prices = {"AAA": {session: 100.0 for session in chain}}
    snapshots = make_snapshots(chain, prices)
    record = make_feedback_record(ticker="AAA", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=90.0, chain=chain, snapshots=snapshots)
    observation = calib.build_observation(record, chain=chain, snapshots=snapshots)  # no target_level supplied
    assert observation["target"]["status"] == calib.NOT_EVALUATED
    assert observation["target"]["hit"] is None


# ── 6. Cohort / version incompatibility ─────────────────────────────────────────────────────

def test_different_invalidation_methods_are_never_pooled_into_one_cohort():
    chain = make_chain(15)
    t0 = chain[0]
    prices = {"AAA": {session: 100.0 for session in chain}, "BBB": {session: 100.0 for session in chain}}
    snapshots = make_snapshots(chain, prices)
    record_a = make_feedback_record(ticker="AAA", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=90.0, chain=chain, snapshots=snapshots, invalidation_method="METHOD_A")
    record_b = make_feedback_record(ticker="BBB", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=90.0, chain=chain, snapshots=snapshots, invalidation_method="METHOD_B")
    observation_a = calib.build_observation(record_a, chain=chain, snapshots=snapshots)
    observation_b = calib.build_observation(record_b, chain=chain, snapshots=snapshots)
    key_a = calib.cohort_key(observation_a, horizon="T5")
    key_b = calib.cohort_key(observation_b, horizon="T5")
    assert key_a != key_b
    assert calib.cohort_key_identity(key_a) != calib.cohort_key_identity(key_b)


# ── 7. Sample adequacy boundaries ───────────────────────────────────────────────────────────

def _mature_observation(ticker: str, t0_session: str, *, forward_return: float = 0.05) -> dict:
    """A minimal, already-MATURE synthetic observation for cohort-aggregation-only tests."""
    return {
        "ticker": ticker, "t0_session": t0_session, "t0_decision_identity": f"decision:{ticker}:{t0_session}",
        "t0_feedback_identity": f"feedback:{ticker}:{t0_session}", "t0_snapshot_identity": None,
        "research_action_posture_at_t0": "INITIATE_ON_BREAKOUT", "tactical_structure_state_at_t0": "BREAKOUT_CONFIRMED",
        "invalidation_method_at_t0": "TEST_METHOD", "market_regime_at_t0": "NEUTRAL_MIXED",
        "r_multiple_denominator_status": "AVAILABLE",
        "horizons": {name: {
            "required_completed_future_sessions": sessions, "status": "MATURE", "maturation_state": "MATURED",
            "forward_return": forward_return, "mfe_close_proxy": abs(forward_return), "mae_close_proxy": -abs(forward_return),
            "close_path_semantics": "CLOSE_ONLY_NOT_INTRADAY_MFE_MAE", "r_multiple": forward_return / 0.10, "r_multiple_status": "AVAILABLE",
        } for name, sessions in calib.HORIZONS.items()},
        "invalidation": {"status": "NOT_SATISFIED_YET", "hit": False, "event_session": None, "sessions_to_invalidation": None, "condition_identity": None},
        "target": {"status": calib.NOT_EVALUATED, "hit": None, "event_session": None, "sessions_to_target": None, "reason": "TEST"},
        "target_invalidation_ordering": calib.NOT_EVALUATED,
        "observation_identity": f"empirical_setup_observation:test:{ticker}:{t0_session}",
        "authority_boundary": {},
    }


def test_below_20_observations_is_insufficient_sample():
    observations = [_mature_observation(f"T{i}", f"2026-01-{i+1:02d}") for i in range(19)]
    cohorts = calib.aggregate_cohorts(observations)
    t5 = next(c for c in cohorts if c["horizon"] == "T5" and not c["cohort_key"]["regime_stratified"])
    assert t5["sample_adequacy"] == calib.INSUFFICIENT_SAMPLE
    assert t5["empirical_positive_return_rate"] is None


def test_20_observations_5_sessions_is_descriptive_only_not_calibrated():
    observations = [_mature_observation(f"T{ticker}", f"2026-01-{session+1:02d}") for session in range(5) for ticker in range(4)]
    assert len(observations) == 20
    cohorts = calib.aggregate_cohorts(observations)
    t5 = next(c for c in cohorts if c["horizon"] == "T5" and not c["cohort_key"]["regime_stratified"])
    assert t5["sample_adequacy"] == calib.DESCRIPTIVE_ONLY
    assert t5["forward_return_distribution"] is not None
    # Descriptive-only must never emit a probability/uncertainty-interval claim.
    assert t5["empirical_positive_return_rate"] is None
    assert t5["uncertainty_note"] == "DESCRIPTIVE_SAMPLE_ONLY_NO_PROBABILITY_CLAIM"


def test_distinct_session_requirement_blocks_calibration_even_with_enough_raw_observations():
    # 25 observations, all from the SAME single T0 session -- 1 distinct session, not 5.
    observations = [_mature_observation(f"T{i}", "2026-01-01") for i in range(25)]
    cohorts = calib.aggregate_cohorts(observations)
    t5 = next(c for c in cohorts if c["horizon"] == "T5" and not c["cohort_key"]["regime_stratified"])
    assert t5["distinct_t0_session_count"] == 1
    assert t5["sample_adequacy"] == calib.INSUFFICIENT_SAMPLE


def test_50_observations_10_sessions_reaches_calibrated_research_with_wilson_interval():
    observations = [_mature_observation(f"T{ticker}", f"2026-01-{session+1:02d}") for session in range(10) for ticker in range(5)]
    assert len(observations) == 50
    cohorts = calib.aggregate_cohorts(observations)
    t5 = next(c for c in cohorts if c["horizon"] == "T5" and not c["cohort_key"]["regime_stratified"])
    assert t5["sample_adequacy"] == calib.CALIBRATED_RESEARCH
    assert t5["empirical_positive_return_rate"]["status"] == "AVAILABLE"
    assert 0.0 <= t5["empirical_positive_return_rate"]["lower"] <= t5["empirical_positive_return_rate"]["point_estimate"] <= t5["empirical_positive_return_rate"]["upper"] <= 1.0
    assert t5["uncertainty_note"] == "EMPIRICAL_RESEARCH_ESTIMATE_NOT_UNIVERSAL_PROBABILITY"


def test_wilson_interval_matches_known_reference_values():
    # 8 successes out of 10: hand-computed 95% Wilson score interval (z=1.96) is (0.4902, 0.9434).
    interval = calib.wilson_interval(8, 10)
    assert abs(interval["point_estimate"] - 0.8) < 1e-9
    assert abs(interval["lower"] - 0.4902) < 1e-3
    assert abs(interval["upper"] - 0.9434) < 1e-3


# ── 8. Deterministic / idempotent aggregation ───────────────────────────────────────────────

def test_calibration_artifact_is_deterministic_and_idempotent():
    chain = make_chain(15)
    t0 = chain[0]
    prices = {"AAA": {session: 100.0 for session in chain}}
    prices["AAA"][chain[5]] = 108.0
    snapshots = make_snapshots(chain, prices)
    record = make_feedback_record(ticker="AAA", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=90.0, chain=chain, snapshots=snapshots)
    feedback_artifact = {"artifact_identity": "prospective_decision_outcome_feedback:test", "feedback_records": [record]}
    first = calib.build_calibration_artifact(feedback_artifact=feedback_artifact, chain=chain, snapshots=snapshots)
    second = calib.build_calibration_artifact(feedback_artifact=feedback_artifact, chain=chain, snapshots=snapshots)
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["observations"][0]["observation_identity"] == second["observations"][0]["observation_identity"]


# ── 9. Optional Portfolio V2 consumption, without execution-authority change ───────────────────

def test_v2_hook_not_available_below_calibrated_research():
    chain = make_chain(15)
    t0 = chain[0]
    prices = {"AAA": {session: 100.0 for session in chain}}
    snapshots = make_snapshots(chain, prices)
    record = make_feedback_record(ticker="AAA", t0_session=t0, posture="INITIATE_ON_BREAKOUT", entry=100.0, invalidation_level=90.0, chain=chain, snapshots=snapshots)
    feedback_artifact = {"artifact_identity": "test", "feedback_records": [record]}
    artifact = calib.build_calibration_artifact(feedback_artifact=feedback_artifact, chain=chain, snapshots=snapshots)
    context = calib.empirical_reward_context_for_cohort(
        artifact, posture="INITIATE_ON_BREAKOUT", tactical_structure_state="BREAKOUT_CONFIRMED",
        invalidation_method="TEST_METHOD", horizon="T5",
    )
    assert context["status"] == "NOT_AVAILABLE"
    assert "target_price" not in context and "expected_return" not in context


def test_v2_hook_available_context_never_carries_execution_authority():
    observations = [_mature_observation(f"T{ticker}", f"2026-01-{session+1:02d}") for session in range(10) for ticker in range(5)]
    cohorts = calib.aggregate_cohorts(observations)
    artifact = {"artifact_identity": "test-artifact", "cohorts": cohorts}
    context = calib.empirical_reward_context_for_cohort(
        artifact, posture="INITIATE_ON_BREAKOUT", tactical_structure_state="BREAKOUT_CONFIRMED",
        invalidation_method="TEST_METHOD", horizon="T5",
    )
    assert context["status"] == "AVAILABLE"
    assert context["authority_boundary"]["is_not_a_target_price"] is True
    assert context["authority_boundary"]["is_not_execution_authority"] is True
    for forbidden_key in ("target_price", "expected_return", "analyst_forecast", "execution_qualified_quantity"):
        assert forbidden_key not in context
