"""Empirical Setup Outcome Calibration (EMPIRICAL_SETUP_OUTCOME_CALIBRATION_V1).

Turns the existing, deliberately non-calibrated prospective outcome corpus into deterministic
empirical setup distributions. This module builds no new backtest engine and reconstructs no T0
decision that was never retained: it is a pure, read-only aggregation layer sitting strictly
downstream of

  * ``prospective_decision_outcome_feedback.build_feedback_artifact()`` -- the existing corpus
    discovery, temporal qualification, and per-(ticker, T0 session) forward-outcome/trigger-
    invalidation computation (horizons T1/T3/T5/T10/T20, close-only MFE/MAE proxies, serialized
    trigger/invalidation condition evaluation). Its own authority boundary already says
    ``"no_probability_or_calibration": True`` -- this module is exactly the explicitly-deferred
    successor that boundary points to.
  * ``integrated_decision_prospective_feedback``'s private ``_forward_horizon``/``_close_excursion``
    primitives, called directly (not duplicated) to add the one additional horizon this milestone
    requires (T60) that the existing shared bridge does not compute, without mutating that shared,
    Daily-brief-facing module's own ``FORWARD_HORIZONS`` contract.
  * ``prospective_decision_retention.evaluate_serialized_close_condition`` -- reused verbatim for
    invalidation-hit (and, when a deterministic target/reward boundary genuinely exists at T0,
    target-hit) event detection over the same governed session chain.

Every metric below is prospective-only: horizons are counted in completed trading sessions from
the governed chain (never calendar days), a T0 decision's posture/setup/trigger/invalidation is
read once and never mutated by a later observation, and missing future depth stays an explicit
``PENDING``/``INSUFFICIENT_FUTURE_DEPTH`` state rather than a fabricated zero.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

import integrated_decision_prospective_feedback as feedback_bridge
import stocklookup_core.decision.integrated_investment_decision_product as decision_product
import prospective_decision_outcome_feedback as outcome_feedback
import prospective_decision_retention as retention

CONTRACT_VERSION = "empirical_setup_outcome_calibration/v2"
METHOD_VERSION = "empirical_setup_outcome_calibration/v2"

# Prospective-only: session-counted, never calendar-day. T60 is this milestone's own addition;
# T5/T10/T20 reuse the existing bridge's already-computed values verbatim.
HORIZONS = {"T5": 5, "T10": 10, "T20": 20, "T60": 60}
_REUSED_HORIZON_FIELD = {"T5": "forward_close_return_5", "T10": "forward_close_return_10", "T20": "forward_close_return_20"}
_REUSED_EXCURSION_FIELD = {"T5": "close_excursion_5", "T10": "close_excursion_10", "T20": "close_excursion_20"}

# Sample-adequacy research policy thresholds (V1). Factual authority never overrides these; they
# gate PRESENTATION of empirical statistics, never the underlying observation itself.
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
CALIBRATED_RESEARCH = "CALIBRATED_RESEARCH"
MIN_OBSERVATIONS_DESCRIPTIVE = 20
MIN_SESSIONS_DESCRIPTIVE = 5
MIN_OBSERVATIONS_CALIBRATED = 50
MIN_SESSIONS_CALIBRATED = 10
SAMPLE_ADEQUACY_POLICY_VERSION = "empirical_setup_outcome_calibration/v1"  # Numerical thresholds unchanged.
WILSON_Z_95 = 1.959963984540054

NOT_EVALUATED = "NOT_EVALUATED"
FIELD_NOT_RETAINED = "FIELD_NOT_RETAINED_AT_T0"


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _identity(payload: dict[str, Any], prefix: str, field: str = "artifact_identity") -> dict[str, Any]:
    payload[field] = prefix + _hash(payload)
    return payload


# ── Statistics primitives (deterministic; no fitted parametric distributions) ─────────────────

def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def _quantile(values: Sequence[float], q: float) -> float | None:
    """Linear-interpolated quantile over a deterministic sort -- no external stats dependency."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _quantile_summary(values: Sequence[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "median": _median(values),
        "p10": _quantile(values, 0.10),
        "p25": _quantile(values, 0.25),
        "p75": _quantile(values, 0.75),
        "p90": _quantile(values, 0.90),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def wilson_interval(successes: int, n: int, *, z: float = WILSON_Z_95) -> dict[str, Any]:
    """Wilson score interval for a binomial proportion. Never a fitted/normal-approx interval."""
    if n <= 0:
        return {"status": "UNAVAILABLE", "point_estimate": None, "lower": None, "upper": None, "n": 0, "z": z}
    phat = successes / n
    denominator = 1 + (z * z) / n
    center = phat + (z * z) / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) / n) + (z * z) / (4 * n * n))
    lower = max(0.0, (center - margin) / denominator)
    upper = min(1.0, (center + margin) / denominator)
    return {"status": "AVAILABLE", "point_estimate": phat, "lower": lower, "upper": upper, "n": n, "z": z}


def sample_adequacy(observation_count: int, distinct_t0_session_count: int) -> str:
    """Research policy thresholds, not factual authority. See module docstring for the flow."""
    if observation_count >= MIN_OBSERVATIONS_CALIBRATED and distinct_t0_session_count >= MIN_SESSIONS_CALIBRATED:
        return CALIBRATED_RESEARCH
    if observation_count >= MIN_OBSERVATIONS_DESCRIPTIVE and distinct_t0_session_count >= MIN_SESSIONS_DESCRIPTIVE:
        return DESCRIPTIVE_ONLY
    return INSUFFICIENT_SAMPLE


# ── Combined governed chain / price-observation resolution (reused, not re-derived) ───────────

def resolve_combined_chain_and_snapshots(root: str) -> tuple[list[str], dict[str, Mapping[str, Any]]]:
    """The same completed-session chain used by every retained T0 source and horizon.

    Qualified Daily market observations supply future sessions independently of whether a
    decision snapshot exists. Sealed T0 price copies take precedence at their own sessions.
    """
    modern = outcome_feedback._modern_snapshot_candidates(root)
    corpus = outcome_feedback.discover_prospective_corpus(root, payload_projection=outcome_feedback._project_artifact_for_feedback)
    market_chain, market_snapshots = outcome_feedback.resolve_completed_market_observations(root)
    legacy_chain = corpus["qualified_session_chain"]
    legacy_snapshots = outcome_feedback.retained_session_snapshots(root, legacy_chain)
    chain = sorted(set(market_chain) | set(legacy_chain) | set(modern["chain"]))
    snapshots = {**market_snapshots, **legacy_snapshots, **modern["snapshots"]}
    return chain, snapshots


def _horizon_60(*, ticker: str, as_of_session: str, chain: Sequence[str], snapshots: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    observations = feedback_bridge.retained_session_price_observations(snapshots, ticker)
    horizon = feedback_bridge._forward_horizon(as_of_session=as_of_session, horizon_sessions=60, chain=chain, observations=observations)
    excursion = feedback_bridge._close_excursion(as_of_session=as_of_session, horizon=horizon, chain=chain, observations=observations)
    later_completed_sessions = (len(chain) - chain.index(as_of_session) - 1) if as_of_session in chain else 0
    horizon["maturation_state"] = retention.maturity_state(
        horizon_status=str(horizon.get("status")), later_completed_sessions=later_completed_sessions, required_sessions=60,
    )
    return horizon, excursion


# ── Per-observation construction ────────────────────────────────────────────────────────────────

def _r_multiple_denominator(record: Mapping[str, Any], t0_close: float | None) -> tuple[float | None, str]:
    """Fractional downside per share at T0, from the already-retained trigger/invalidation levels.

    Never a stop-loss or execution boundary -- purely the denominator for expressing a later
    return in "R units" of the T0 decision's own already-retained deterministic invalidation.
    """
    condition = (record.get("invalidation") or {}).get("condition") or {}
    if condition.get("status") != "MACHINE_EVALUABLE" or condition.get("operator") != "<" or condition.get("condition_identity") != "retained_strategy_boundary_condition:" + retention._hash({k: v for k, v in condition.items() if k != "condition_identity"}):
        return None, "UNAVAILABLE_NO_QUALIFIED_T0_DOWNSIDE_BOUNDARY"
    invalidation_level = condition.get("reference_level")
    if invalidation_level != (record.get("invalidation") or {}).get("invalidation_level"):
        return None, "UNAVAILABLE_T0_DOWNSIDE_SEMANTICS_MISMATCH"
    if not feedback_bridge._qualified_close(t0_close):
        return None, "UNAVAILABLE_NO_T0_ENTRY_REFERENCE"
    entry = (record.get("trigger") or {}).get("trigger_level")
    if entry is None:
        entry = t0_close
    if not feedback_bridge._qualified_close(entry):
        return None, "UNAVAILABLE_NO_T0_ENTRY_REFERENCE"
    if not feedback_bridge._qualified_close(invalidation_level):
        return None, "UNAVAILABLE_NO_T0_INVALIDATION"
    downside_fraction = (entry - invalidation_level) / entry
    if downside_fraction <= 0:
        return None, "UNAVAILABLE_DEGENERATE_DOWNSIDE"
    return downside_fraction, "AVAILABLE"


def _event_sessions_to(chain: Sequence[str], start_session: str, event_session: str | None) -> int | None:
    if event_session is None or start_session not in chain or event_session not in chain:
        return None
    delta = chain.index(event_session) - chain.index(start_session)
    return delta if delta > 0 else None


def _target_condition(*, target_level: float, direction: str) -> dict[str, Any]:
    """Ad hoc MACHINE_EVALUABLE condition shaped exactly like ``serialize_boundary_condition``'s
    output, built only from an explicit caller-supplied deterministic target/reward boundary --
    never fabricated. ``direction`` is ``"ABOVE"`` (long target) or ``"BELOW"``.
    """
    operator = ">" if direction == "ABOVE" else "<"
    payload = {
        "condition_version": retention.CONDITION_CONTRACT_VERSION, "role": "target", "status": "MACHINE_EVALUABLE",
        "operator": operator, "reference_field": "close", "reference_level": target_level,
        "activation_semantics": "FIRST_LATER_COMPLETED_SESSION_WITH_RETAINED_CLOSE_SATISFIES_FIXED_T0_TARGET",
        "source_rule": "CALLER_SUPPLIED_DETERMINISTIC_TARGET_REWARD_BOUNDARY", "reason_codes": [],
    }
    return retention._identity(payload, "retained_strategy_boundary_condition:", "condition_identity")


def _target_invalidation_ordering(target: Mapping[str, Any], invalidation: Mapping[str, Any], *,
                                   chain: Sequence[str], start_session: str) -> str:
    target_session = target.get("sessions_to_target")
    invalidation_session = invalidation.get("sessions_to_invalidation")
    if isinstance(target_session, int) and isinstance(invalidation_session, int):
        return "TARGET_BEFORE_INVALIDATION" if target_session < invalidation_session else "SAME_SESSION_ORDER_UNRESOLVED" if target_session == invalidation_session else "INVALIDATION_BEFORE_TARGET"
    if isinstance(target_session, int):
        return "TARGET_ONLY"
    if isinstance(invalidation_session, int):
        return "INVALIDATION_ONLY"
    if target.get("status") == NOT_EVALUATED:
        return NOT_EVALUATED
    return "NEITHER_YET"


def build_observation(
    record: Mapping[str, Any], *, chain: Sequence[str], snapshots: Mapping[str, Mapping[str, Any]],
    target_level: float | None = None, target_direction: str = "ABOVE",
) -> dict[str, Any]:
    """One deterministic per-(ticker, T0 session) observation row, feeding cohort aggregation.

    ``target_level``/``target_direction`` are optional, explicit, caller-supplied inputs for the
    rare case a deterministic target/reward boundary genuinely existed at T0. Nothing upstream in
    this repository emits one today (see PORTFOLIO_AWARE_DECISION_AND_RISK_SIZING_V1's own finding
    that no module emits a price target); target statistics are honestly ``NOT_EVALUATED`` absent
    this explicit input, never invented from a later observation.
    """
    ticker, decision_session = record["ticker"], record["decision_session"]
    forward_outcomes = record["forward_outcomes"]
    t0_close = (forward_outcomes.get("horizons") or {}).get("forward_close_return_1", {}).get("start_price")
    downside_fraction, downside_status = _r_multiple_denominator(record, t0_close)

    horizons: dict[str, Any] = {}
    for name, sessions in HORIZONS.items():
        if name == "T60":
            horizon, excursion = _horizon_60(ticker=ticker, as_of_session=decision_session, chain=chain, snapshots=snapshots)
        else:
            horizon = forward_outcomes["horizons"][_REUSED_HORIZON_FIELD[name]]
            excursion = forward_outcomes["close_path_by_horizon"].get(_REUSED_EXCURSION_FIELD[name], {})
        diagnostics = outcome_feedback.feedback_diagnostics({**record, "as_of_session": decision_session},
            chain=chain, snapshots=snapshots, horizon_sessions=sessions)
        is_mature = horizon.get("status") == feedback_bridge.MATURE
        forward_return = horizon.get("return") if is_mature else None
        r_multiple = (forward_return / downside_fraction) if (is_mature and downside_fraction and forward_return is not None) else None
        r_multiple_status = (
            "AVAILABLE" if r_multiple is not None
            else "UNAVAILABLE_NOT_MATURE" if not is_mature
            else downside_status
        )
        horizons[name] = {
            "required_completed_future_sessions": sessions,
            "status": horizon.get("status"),
            "maturation_state": horizon.get("maturation_state"),
            "forward_return": forward_return,
            "mfe_close_proxy": excursion.get("CLOSE_MFE") if is_mature else None,
            "mae_close_proxy": excursion.get("CLOSE_MAE") if is_mature else None,
            "close_path_semantics": "CLOSE_ONLY_NOT_INTRADAY_MFE_MAE",
            "favorable_semantics": "CLOSE_ONLY_FAVORABLE_EXCURSION", "adverse_semantics": "CLOSE_ONLY_ADVERSE_EXCURSION",
            "series_lineage": horizon.get("series_lineage"),
            "confirmation": diagnostics["confirmation"], "invalidation": diagnostics["invalidation"],
            "event_ordering": diagnostics["event_ordering"],
            "benchmark_relative": outcome_feedback.outcome_measurement._benchmark(
                {"status": horizon.get("status"), "return": forward_return, "required_completed_future_sessions": sessions},
                {"benchmark": record.get("benchmark")},
                [snapshots.get(session, {}) for session in chain[chain.index(decision_session)+1:]] if decision_session in chain else []),
            "start_session": decision_session, "future_session": horizon.get("future_session"),
            "series_fitness": horizon.get("series_fitness"),
            "evidence_state": "NOT_RETAINED_AT_T0" if horizon.get("series_fitness") in {"T0_CLOSE_NOT_RETAINED", "T0_CLOSE_VALUE_INVALID", "START_CLOSE_NOT_RETAINED"} else
                              "RETAINED_BUT_NOT_YET_MATURE" if horizon.get("status") == feedback_bridge.PENDING else
                              "SEMANTICALLY_INCOMPATIBLE" if horizon.get("status") == feedback_bridge.PRICE_BASIS_INCOMPATIBLE else
                              "MATURE" if is_mature else "OUTCOME_DATA_UNAVAILABLE",
            "r_multiple": r_multiple,
            "r_multiple_status": r_multiple_status,
        }

    retained_target = record.get("target_condition_at_t0")
    for name, count in HORIZONS.items():
        prefix = chain[:chain.index(decision_session) + count + 1] if decision_session in chain else []
        event = retention.evaluate_serialized_close_condition(retained_target, ticker=ticker, chain=prefix,
            start_session=decision_session, snapshots=snapshots)
        horizons[name]["target"] = {**event, "hit": event.get("status") == "SATISFIED",
            "sessions_to_target": _event_sessions_to(chain, decision_session, event.get("event_session"))}

    invalidation_event = (record.get("trigger_invalidation_outcome") or {}).get("invalidation") or {}
    invalidation_hit = invalidation_event.get("status") == "SATISFIED"
    invalidation = {
        "status": invalidation_event.get("status", NOT_EVALUATED),
        "hit": invalidation_hit,
        "event_session": invalidation_event.get("event_session"),
        "sessions_to_invalidation": _event_sessions_to(chain, decision_session, invalidation_event.get("event_session")) if invalidation_hit else None,
        "condition_identity": invalidation_event.get("condition_identity"),
    }

    retained_target = record.get("target_condition_at_t0")
    if not isinstance(retained_target, Mapping) or retained_target.get("status") != "MACHINE_EVALUABLE":
        target_level = None
    elif target_level is None:
        target_level = retained_target.get("reference_level")
        target_direction = "ABOVE" if retained_target.get("operator") == ">" else "BELOW"
    elif target_level != retained_target.get("reference_level"):
        target_level = None
    if target_level is None:
        target = {"status": NOT_EVALUATED, "hit": None, "event_session": None, "sessions_to_target": None,
                  "reason": "NO_DETERMINISTIC_TARGET_REWARD_BOUNDARY_RETAINED_AT_T0"}
    else:
        condition = retained_target
        event = retention.evaluate_serialized_close_condition(
            condition, ticker=ticker, chain=chain, start_session=decision_session, snapshots=snapshots,
        )
        hit = event.get("status") == "SATISFIED"
        target = {
            "status": "EVALUATED" if event.get("status") in {"SATISFIED", "NOT_SATISFIED_YET"} else NOT_EVALUATED, "hit": hit, "event_session": event.get("event_session"),
            "sessions_to_target": _event_sessions_to(chain, decision_session, event.get("event_session")) if hit else None,
            "target_level": target_level, "condition_identity": event.get("condition_identity"),
        }

    ordering = _target_invalidation_ordering(
        {"sessions_to_target": target.get("sessions_to_target"), "status": target["status"]},
        {"sessions_to_invalidation": invalidation["sessions_to_invalidation"]},
        chain=chain, start_session=decision_session,
    )

    observation = {
        "ticker": ticker, "t0_session": decision_session,
        "t0_decision_identity": record.get("decision_identity"),
        "t0_feedback_identity": record.get("feedback_identity"),
        "t0_source_artifact_identity": (record.get("source_artifact") or {}).get("identity", FIELD_NOT_RETAINED),
        "t0_contract_versions": dict(record.get("t0_contract_versions") or {}),
        "feature_versions_at_t0": {name: axis.get("method", FIELD_NOT_RETAINED) for name, axis in ((record.get("evidence_axes") or {}).get("axis_states") or {}).items()},
        "source_type": record.get("source_type", FIELD_NOT_RETAINED),
        "feedback_diagnostics": record.get("feedback_diagnostics", {}),
        "feedback_taxonomy": record.get("feedback_taxonomy", {"label": "INSUFFICIENT_OUTCOME_EVIDENCE"}),
        "forward_driver_context_at_t0": record.get("forward_driver_context_at_t0", FIELD_NOT_RETAINED),
        "intrinsic_scenario_at_t0": record.get("intrinsic_scenario_at_t0", FIELD_NOT_RETAINED),
        "t0_snapshot_identity": record.get("t0_snapshot_identity"),
        "research_action_posture_at_t0": record.get("research_action_posture", FIELD_NOT_RETAINED),
        "tactical_structure_state_at_t0": record.get("tactical_structure_state", FIELD_NOT_RETAINED),
        "invalidation_method_at_t0": (record.get("invalidation") or {}).get("invalidation_method", FIELD_NOT_RETAINED),
        "market_regime_at_t0": record.get("market_sector_state", FIELD_NOT_RETAINED),
        "r_multiple_denominator_status": downside_status,
        "horizons": horizons,
        "invalidation": invalidation,
        "target": target,
        "target_invalidation_ordering": ordering,
        "authority_boundary": {
            "prospective_only": True, "no_retroactive_t0_reconstruction": (record.get("temporal_qualification") or {}).get("status") == outcome_feedback.GENUINE,
            "close_path_is_not_intraday_mfe_mae": True, "r_multiple_is_not_execution_authority": True,
            "target_never_invented_after_t0": True,
        },
    }
    return _identity(observation, "empirical_setup_observation:", "observation_identity")


# ── Cohort key and aggregation ──────────────────────────────────────────────────────────────────

_FEATURE_CONTRACT_VERSIONS = {
    "integrated_decision_contract": decision_product.CONTRACT_VERSION,
    "prospective_feedback_contract": outcome_feedback.CONTRACT_VERSION,
    "calibration_method": METHOD_VERSION,
}


def comparable_policy_key(observation):
    versions = observation.get("t0_contract_versions") or {}
    features = observation.get("feature_versions_at_t0") or {}
    required = ("integrated_decision_contract", "research_action_policy_version", "fundamental_policy_version")
    complete = all(versions.get(key) not in (None, "", FIELD_NOT_RETAINED) for key in required) and bool(features) and all(value not in (None, "", FIELD_NOT_RETAINED) for value in features.values())
    payload = {"policy": versions, "features": features}
    if not complete:
        source = observation.get("t0_source_artifact_identity")
        payload["unqualified_t0_source_partition"] = source if source not in (None, "", FIELD_NOT_RETAINED) else observation.get("t0_snapshot_identity") or observation["t0_session"]
    return _canon(payload)


def cohort_key(observation: Mapping[str, Any], *, horizon: str, with_regime: bool = False) -> tuple[Any, ...]:
    """Versioned comparable-cohort key, prioritizing action/posture family, setup family,
    invalidation method, horizon, and feature/decision contract versions. Never fragments by
    ticker or sector by default; never pools incompatible setup/method versions.
    """
    base = (
        (observation.get("t0_contract_versions") or {}).get("integrated_decision_contract", FIELD_NOT_RETAINED),
        outcome_feedback.CONTRACT_VERSION,
        observation["research_action_posture_at_t0"],
        observation["tactical_structure_state_at_t0"],
        observation["invalidation_method_at_t0"],
        horizon,
        comparable_policy_key(observation),
    )
    if with_regime:
        return base + (observation["market_regime_at_t0"],)
    return base


def cohort_key_identity(key: Sequence[Any]) -> str:
    return "empirical_setup_cohort:" + _hash(list(key))


_COHORT_KEY_FIELDS = (
    "integrated_decision_contract", "prospective_feedback_contract", "research_action_posture",
    "tactical_structure_state", "invalidation_method", "horizon", "policy_and_feature_versions",
)


def _cohort_key_view(key: Sequence[Any], *, with_regime: bool) -> dict[str, Any]:
    view = dict(zip(_COHORT_KEY_FIELDS, key))
    if with_regime:
        view["market_regime"] = key[len(_COHORT_KEY_FIELDS)]
    view["regime_stratified"] = with_regime
    return view


INSUFFICIENT_PROSPECTIVE_EVIDENCE = "INSUFFICIENT_PROSPECTIVE_EVIDENCE"
DESCRIPTIVE_EVIDENCE_ONLY = "DESCRIPTIVE_EVIDENCE_ONLY"
CALIBRATION_REVIEW_ELIGIBLE = "CALIBRATION_REVIEW_ELIGIBLE"


def calibration_eligibility(cohort, members):
    """Presentation adequacy is necessary but not proof of comparable policy evidence."""
    reasons = []
    versions = cohort.get("current_policy") or {}
    if any(versions.get(key) in (None, "", FIELD_NOT_RETAINED) for key in
           ("integrated_decision_contract", "research_action_policy_version", "fundamental_policy_version")):
        reasons.append("POLICY_OR_DECISION_VERSION_NOT_RETAINED_AT_T0")
    if any(not item.get("feature_versions_at_t0") or any(value in (None, "", FIELD_NOT_RETAINED) for value in item["feature_versions_at_t0"].values()) for item in members):
        reasons.append("FEATURE_VERSIONS_NOT_RETAINED_AT_T0")
    if any(item["horizons"][cohort["horizon"]].get("status") == feedback_bridge.PRICE_BASIS_INCOMPATIBLE for item in members):
        reasons.append("PRICE_BASIS_INCOMPATIBILITY_PRESENT")
    if any(not (item.get("authority_boundary") or {}).get("no_retroactive_t0_reconstruction") or not item.get("t0_decision_identity") or item.get("t0_source_artifact_identity") in (None, "", FIELD_NOT_RETAINED) or item.get("source_type") not in {"IMMUTABLE_INTEGRATED_T0", "QUALIFIED_LEGACY_INTEGRATED_T0"} or (item.get("source_type") == "IMMUTABLE_INTEGRATED_T0" and not item.get("t0_snapshot_identity")) for item in members):
        reasons.append("GENUINE_PROSPECTIVE_T0_PROOF_MISSING")
    if cohort["sample_adequacy"] == INSUFFICIENT_SAMPLE:
        reasons.append("EXISTING_SAMPLE_ADEQUACY_NOT_SATISFIED")
        state = INSUFFICIENT_PROSPECTIVE_EVIDENCE
    elif cohort["sample_adequacy"] != CALIBRATED_RESEARCH or reasons:
        if cohort["sample_adequacy"] != CALIBRATED_RESEARCH:
            reasons.append("EXISTING_CALIBRATED_RESEARCH_FLOOR_NOT_SATISFIED")
        state = DESCRIPTIVE_EVIDENCE_ONLY
    else:
        state = CALIBRATION_REVIEW_ELIGIBLE
    return {"contract_version": "prospective_calibration_eligibility/v1", "state": state, "reason_codes": sorted(set(reasons)),
            "sample_policy_version": SAMPLE_ADEQUACY_POLICY_VERSION, "authority": "RESEARCH_PRESENTATION_POLICY",
            "automatic_policy_change": False}


def _aggregate_one_cohort(key: Sequence[Any], members: Sequence[Mapping[str, Any]], *, horizon: str, with_regime: bool) -> dict[str, Any]:
    matured = [item for item in members if item["horizons"][horizon]["status"] == feedback_bridge.MATURE]
    distinct_sessions = {item["t0_session"] for item in matured}
    adequacy = sample_adequacy(len(matured), len(distinct_sessions))

    forward_returns = [item["horizons"][horizon]["forward_return"] for item in matured]
    mfe_values = [item["horizons"][horizon]["mfe_close_proxy"] for item in matured if item["horizons"][horizon]["mfe_close_proxy"] is not None]
    mae_values = [item["horizons"][horizon]["mae_close_proxy"] for item in matured if item["horizons"][horizon]["mae_close_proxy"] is not None]
    r_values = [item["horizons"][horizon]["r_multiple"] for item in matured if item["horizons"][horizon]["r_multiple"] is not None]

    invalidation_events = [item["horizons"][horizon].get("invalidation", {}) for item in matured]
    confirmation_events = [item["horizons"][horizon].get("confirmation", {}) for item in matured]
    invalidation_hits = sum(e.get("status") == "INVALIDATED" for e in invalidation_events)
    invalidation_evaluable = sum(e.get("status") in {"INVALIDATED", "NOT_INVALIDATED_YET"} for e in invalidation_events)
    confirmation_hits = sum(e.get("status") == "CONFIRMED" for e in confirmation_events)
    confirmation_evaluable = sum(e.get("status") in {"CONFIRMED", "NOT_CONFIRMED_YET"} for e in confirmation_events)
    target_evaluable = [item["horizons"][horizon]["target"] for item in matured
                        if item["horizons"][horizon].get("target", {}).get("status") in {"SATISFIED", "NOT_SATISFIED_YET"}]
    target_hits = sum(item["hit"] for item in target_evaluable)

    status_counts = dict(sorted(Counter(item["horizons"][horizon]["status"] for item in members).items()))
    maturation_counts = dict(sorted(Counter(item["horizons"][horizon]["maturation_state"] for item in members).items()))

    positive_rate = None
    if adequacy == CALIBRATED_RESEARCH and forward_returns:
        positive_rate = wilson_interval(sum(1 for value in forward_returns if value > 0), len(forward_returns))
    invalidation_rate = None
    if adequacy == CALIBRATED_RESEARCH and invalidation_evaluable:
        invalidation_rate = wilson_interval(invalidation_hits, invalidation_evaluable)
    target_hit_rate = None
    if adequacy == CALIBRATED_RESEARCH and target_evaluable:
        target_hit_rate = wilson_interval(target_hits, len(target_evaluable))

    cohort = {
        "cohort_key": _cohort_key_view(key, with_regime=with_regime),
        "cohort_key_identity": cohort_key_identity(key),
        "horizon": horizon,
        "required_completed_future_sessions": HORIZONS[horizon],
        "sample_count_all_members": len(members),
        "matured_observation_count": len(matured),
        "distinct_t0_session_count": len(distinct_sessions),
        "sample_adequacy": adequacy,
        "unique_ticker_count": len({item["ticker"] for item in matured}),
        "current_policy": (members[0].get("t0_contract_versions") or {}) if members else {},
        "taxonomy_distribution": dict(sorted(Counter((item.get("feedback_taxonomy") or {}).get("label", "INSUFFICIENT_OUTCOME_EVIDENCE") for item in matured).items())),
        "taxonomy_basis_horizon": "T5",
        "observed_close_return_counts": {"positive": sum(v > 0 for v in forward_returns), "negative": sum(v < 0 for v in forward_returns), "unchanged": sum(v == 0 for v in forward_returns)},
        "observed_close_return_rates": {name: count / len(forward_returns) if adequacy == CALIBRATED_RESEARCH and forward_returns else None
            for name, count in {"positive":sum(v > 0 for v in forward_returns), "negative":sum(v < 0 for v in forward_returns), "unchanged":sum(v == 0 for v in forward_returns)}.items()},
        "observed_rate_semantics": "RETROSPECTIVE_DESCRIPTION_OF_PROSPECTIVE_CORPUS_NOT_FORECAST",
        "confirmation_frequency": {"hit_count": confirmation_hits, "evaluable_count": confirmation_evaluable,
            "empirical_rate_uncertainty_interval": wilson_interval(confirmation_hits, confirmation_evaluable) if adequacy == CALIBRATED_RESEARCH and confirmation_evaluable else None},
        "temporal_fitness_counts": status_counts,
        "maturation_state_counts": maturation_counts,
        "forward_return_distribution": _quantile_summary(forward_returns) if adequacy != INSUFFICIENT_SAMPLE else None,
        "mfe_close_proxy_distribution": _quantile_summary(mfe_values) if adequacy != INSUFFICIENT_SAMPLE else None,
        "mae_close_proxy_distribution": _quantile_summary(mae_values) if adequacy != INSUFFICIENT_SAMPLE else None,
        "r_multiple_distribution": _quantile_summary(r_values) if (adequacy != INSUFFICIENT_SAMPLE and r_values) else None,
        "invalidation_frequency": {
            "hit_count": invalidation_hits, "evaluable_count": invalidation_evaluable,
            "empirical_rate_uncertainty_interval": invalidation_rate,
        },
        "target_dependent_statistics": (
            {"status": NOT_EVALUATED, "reason": "NO_T0_TARGET_RETAINED_IN_THIS_COHORT"} if not target_evaluable
            else {
                "status": "EVALUATED", "evaluable_count": len(target_evaluable), "hit_count": target_hits,
                "empirical_target_hit_rate_uncertainty_interval": target_hit_rate,
                "median_sessions_to_target": _median([item["sessions_to_target"] for item in target_evaluable if item["sessions_to_target"] is not None]),
                "ordering_counts": dict(sorted(Counter(item.get("status") for item in target_evaluable).items())),
            }
        ),
        "empirical_positive_return_rate": positive_rate,
        "uncertainty_note": (
            "OBSERVED_PROSPECTIVE_CORPUS_FREQUENCY_NOT_FORECAST" if adequacy == CALIBRATED_RESEARCH
            else "DESCRIPTIVE_SAMPLE_ONLY_NO_PROBABILITY_CLAIM" if adequacy == DESCRIPTIVE_ONLY
            else "SAMPLE_TOO_SMALL_FOR_ANY_DISTRIBUTIONAL_STATEMENT"
        ),
        "source_lineage": {
            "t0_sessions": sorted({item["t0_session"] for item in members}),
            "t0_decision_identities": sorted({item["t0_decision_identity"] for item in members if item.get("t0_decision_identity")}),
            "t0_snapshot_identities": sorted({item["t0_snapshot_identity"] for item in members if item.get("t0_snapshot_identity")}),
            "observation_identities": sorted(item["observation_identity"] for item in members),
        },
        "authority_boundary": {
            "not_a_universal_stock_score": True,
            "observed_rates_are_not_forecast_probabilities": True,
            "no_threshold_optimization": True,
            "no_kelly_cvar_or_probability_based_sizing": True,
        },
    }
    cohort["calibration_eligibility"] = calibration_eligibility(cohort, members)
    return _identity(cohort, "empirical_setup_outcome_cohort:")


def aggregate_cohorts(observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group observations into versioned comparable cohorts per horizon and compute calibration.

    Market regime is used as an optional stratification: a regime-stratified variant of a cohort
    is emitted alongside (never instead of) its base, non-stratified cohort only when every member
    actually retains a regime value and the stratified split itself would still clear the
    ``DESCRIPTIVE_ONLY`` sample floor -- otherwise the corpus is not over-fragmented by regime.
    """
    unique = {}
    for item in observations:
        identity = item["observation_identity"]
        if identity in unique and unique[identity] != item:
            raise ValueError("CONFLICTING_PROSPECTIVE_OBSERVATION_IDENTITY")
        unique[identity] = item
    observations = list(unique.values())
    cohorts: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        base_groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
        for observation in observations:
            base_groups[cohort_key(observation, horizon=horizon)].append(observation)
        for key, members in sorted(base_groups.items(), key=lambda item: cohort_key_identity(item[0])):
            cohorts.append(_aggregate_one_cohort(key, members, horizon=horizon, with_regime=False))

            regime_values = {member["market_regime_at_t0"] for member in members}
            if FIELD_NOT_RETAINED in regime_values or "UNAVAILABLE" in regime_values or len(regime_values) < 2:
                continue
            regime_groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
            for member in members:
                regime_groups[cohort_key(member, horizon=horizon, with_regime=True)].append(member)
            for regime_key, regime_members in sorted(regime_groups.items(), key=lambda item: cohort_key_identity(item[0])):
                matured = [item for item in regime_members if item["horizons"][horizon]["status"] == feedback_bridge.MATURE]
                if sample_adequacy(len(matured), len({item["t0_session"] for item in matured})) == INSUFFICIENT_SAMPLE:
                    continue
                cohorts.append(_aggregate_one_cohort(regime_key, regime_members, horizon=horizon, with_regime=True))
    return cohorts


# ── Top-level artifact builder ──────────────────────────────────────────────────────────────────

def corpus_inventory(feedback, observations):
    records = feedback.get("feedback_records") or []
    return {
        "genuine_t0_case_count": len(records),
        "immutable_t0_case_count": sum(r.get("source_type") == "IMMUTABLE_INTEGRATED_T0" for r in records),
        "immutable_t0_session_count": len({r["decision_session"] for r in records if r.get("source_type") == "IMMUTABLE_INTEGRATED_T0"}),
        "qualified_legacy_t0_session_count": len({r["decision_session"] for r in records if r.get("source_type") == "QUALIFIED_LEGACY_INTEGRATED_T0"}), "t0_session_count": len({r["decision_session"] for r in records}),
        "unique_ticker_count": len({r["ticker"] for r in records}),
        "source_type_distribution": dict(sorted(Counter(r.get("source_type", FIELD_NOT_RETAINED) for r in records).items())),
        "source_contract_policy_distribution": dict(sorted(Counter(_canon(r.get("t0_contract_versions") or {}) for r in records).items())),
        "distinct_contract_policy_versions": len({_canon(r.get("t0_contract_versions") or {}) for r in records}),
        "posture_distribution": dict(sorted(Counter(r["research_action_posture"] for r in records).items())),
        "setup_distribution": dict(sorted(Counter(r["tactical_structure_state"] for r in records).items())),
        "horizon_status_counts": {h: dict(sorted(Counter(o["horizons"][h]["status"] for o in observations).items())) for h in HORIZONS},
        "horizon_evidence_states": {h: dict(sorted(Counter(o["horizons"][h]["evidence_state"] for o in observations).items())) for h in HORIZONS},
        "confirmation_evaluability": dict(sorted(Counter((r.get("feedback_diagnostics") or {}).get("confirmation", {}).get("status", FIELD_NOT_RETAINED) for r in records).items())),
        "invalidation_evaluability": dict(sorted(Counter((r.get("feedback_diagnostics") or {}).get("invalidation", {}).get("status", FIELD_NOT_RETAINED) for r in records).items())),
        "event_ordering": dict(sorted(Counter((r.get("feedback_diagnostics") or {}).get("event_ordering", FIELD_NOT_RETAINED) for r in records).items())),
        "taxonomy_distribution": dict(sorted(Counter((r.get("feedback_taxonomy") or {}).get("label", "INSUFFICIENT_OUTCOME_EVIDENCE") for r in records).items())),
        "qualified_t0_downside_denominator_count": sum(o["r_multiple_denominator_status"] == "AVAILABLE" for o in observations),
        "genuine_t0_target_boundary_count": sum(o["target"]["status"] == "EVALUATED" for o in observations),
        "r4_attribution_retained_count": sum(o["forward_driver_context_at_t0"] != FIELD_NOT_RETAINED for o in observations),
        "r5_attribution_retained_count": sum(o["intrinsic_scenario_at_t0"] != FIELD_NOT_RETAINED for o in observations),
        "attribution_limitations": ["ASSOCIATION_NOT_CAUSATION", "INTRINSIC_UNAVAILABLE_IS_NOT_BEARISH", "OPTIONAL_CONTEXT_NOT_AN_ADMISSION_GATE"],
        "temporal_source_inventory": feedback.get("temporal_qualification"),
    }


def _valid_session(value):
    from datetime import date
    try:
        return date.fromisoformat(value).isoformat() == value
    except (TypeError, ValueError):
        return False


def build_policy_candidates(cohorts, governed_candidates=()):
    """One predeclared review rule per comparable cohort; no optimizer or proposed cutoff."""
    rows = []
    for cohort in cohorts:
        disposition = "NO_GOVERNED_POLICY_CANDIDATE_TO_COMPARE"
        matches = [c for c in governed_candidates if c.get("current_policy") == cohort["current_policy"] and c.get("horizon") == cohort["horizon"] and c.get("cohort_key_identity") == cohort["cohort_key_identity"]]
        candidate = matches[0] if len(matches) == 1 else None
        reason = [disposition]
        if len(matches) > 1:
            reason = ["MULTIPLE_COMPARISONS_NOT_ADMITTED_PARAMETER_SEARCH_FORBIDDEN"]
        if candidate is not None:
            rule = candidate.get("comparison_rule") or {}
            rule = rule if isinstance(rule, Mapping) else {}
            count = cohort["taxonomy_distribution"].get(str(rule.get("taxonomy_label")), 0)
            earliest = min(cohort["source_lineage"].get("t0_sessions") or ["0000-00-00"])
            threshold = rule.get("minimum_count")
            valid = (candidate.get("contract_version") == "governed_prospective_policy_review_rule/v1" and
                bool(candidate.get("declaration_identity")) and bool(candidate.get("comparison_policy_identity")) and
                isinstance(candidate.get("predeclared_session"), str) and _valid_session(candidate["predeclared_session"]) and candidate["predeclared_session"] < earliest and
                rule.get("method") == "PREDECLARED_TAXONOMY_COUNT_AT_LEAST" and
                str(rule.get("taxonomy_label")) in {"FALSE_POSITIVE_BREAKOUT", "FALSE_POSITIVE_EARLY_REVERSAL", "MISSED_BREAKOUT", "POSSIBLE_FALSE_NEGATIVE", "POLICY_TOO_DEFENSIVE", "TACTICAL_SIGNAL_NOT_INTEGRATED"} and
                isinstance(threshold, int) and not isinstance(threshold, bool) and threshold > 0)
            if not valid:
                disposition = "GOVERNED_CANDIDATE_CONTRACT_OR_PREDECLARATION_UNQUALIFIED"
            elif cohort["calibration_eligibility"]["state"] != CALIBRATION_REVIEW_ELIGIBLE:
                disposition = "CALIBRATION_REVIEW_NOT_ELIGIBLE"
            elif count < threshold:
                disposition = "PREDECLARED_REVIEW_RULE_NOT_SATISFIED"
            else:
                disposition = "HUMAN_CALIBRATION_REVIEW_CANDIDATE"
            reason = [disposition]
        rows.append(_identity({"contract_version": "prospective_policy_calibration_candidate/v1", "disposition": disposition,
            "current_policy": cohort["current_policy"], "cohort_identity": cohort["artifact_identity"], "horizon": cohort["horizon"],
            "observation_count": cohort["matured_observation_count"], "distinct_t0_session_count": cohort["distinct_t0_session_count"],
            "empirical_statistics": {k: cohort[k] for k in ("forward_return_distribution", "observed_close_return_counts", "observed_close_return_rates", "invalidation_frequency", "confirmation_frequency")},
            "uncertainty_interval": cohort["empirical_positive_return_rate"], "failure_taxonomy": cohort["taxonomy_distribution"],
            "governed_comparison_identity": candidate.get("declaration_identity") if candidate else None,
            "reason_for_review": reason, "limitations": ["PROSPECTIVE_RESEARCH_ONLY", "OVERLAPPING_WINDOWS_ARE_NOT_INDEPENDENT", "NO_THRESHOLD_OPTIMIZATION_OR_SEARCH"],
            "required_human_approval": True, "automatic_policy_change": False}, "prospective_policy_calibration_candidate:"))
    return {"contract_version": "prospective_policy_calibration_candidates/v1", "records": rows,
            "human_review_candidate_count": sum(r["disposition"] == "HUMAN_CALIBRATION_REVIEW_CANDIDATE" for r in rows),
            "disposition_distribution": dict(sorted(Counter(r["disposition"] for r in rows).items())), "automatic_policy_change": False}


def build_calibration_artifact(
    root: str | None = None, *, feedback_artifact: Mapping[str, Any] | None = None,
    target_level_by_ticker_session: Mapping[tuple[str, str], tuple[float, str]] | None = None,
    chain: Sequence[str] | None = None, snapshots: Mapping[str, Mapping[str, Any]] | None = None,
    governed_policy_candidates: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Deterministic, read-only calibration artifact over the retained prospective corpus.

    Never runs Daily, never acquires provider data, never reconstructs a T0 decision that was not
    genuinely retained. ``root`` is required unless ``feedback_artifact``/``chain``/``snapshots``
    are supplied directly (the synthetic-fixture test path).
    """
    if feedback_artifact is None:
        if root is None:
            raise ValueError("EITHER_ROOT_OR_FEEDBACK_ARTIFACT_REQUIRED")
        context = {}
        feedback_artifact = outcome_feedback.build_feedback_artifact(root, resolved_context=context)
        if chain is None:
            chain = context["chain"]
        if snapshots is None:
            snapshots = context["snapshots"]
    if chain is None or snapshots is None:
        if root is None:
            raise ValueError("EITHER_ROOT_OR_CHAIN_AND_SNAPSHOTS_REQUIRED")
        chain, snapshots = resolve_combined_chain_and_snapshots(root)

    target_lookup = target_level_by_ticker_session or {}
    observations: list[dict[str, Any]] = []
    for record in feedback_artifact.get("feedback_records") or []:
        key = (record["ticker"], record["decision_session"])
        target_level, target_direction = target_lookup.get(key, (None, "ABOVE"))
        observations.append(build_observation(
            record, chain=chain, snapshots=snapshots, target_level=target_level, target_direction=target_direction,
        ))
    observations.sort(key=lambda item: (item["t0_session"], item["ticker"]))
    cohorts = aggregate_cohorts(observations)

    horizon_adequacy_counts = {
        horizon: dict(sorted(Counter(row["sample_adequacy"] for row in cohorts if row["horizon"] == horizon and not row["cohort_key"]["regime_stratified"]).items()))
        for horizon in HORIZONS
    }
    calibrated_cohort_count = sum(1 for row in cohorts if row["sample_adequacy"] == CALIBRATED_RESEARCH)

    artifact = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "method_version": METHOD_VERSION,
        "feature_contract_versions": dict(_FEATURE_CONTRACT_VERSIONS),
        "horizons": {name: sessions for name, sessions in HORIZONS.items()},
        "observation_count": len(observations),
        "t0_session_count": len({item["t0_session"] for item in observations}),
        "cohort_count": len(cohorts),
        "calibrated_research_cohort_count": calibrated_cohort_count,
        "adequacy_state_counts_by_horizon": horizon_adequacy_counts,
        "observations": observations,
        "cohorts": cohorts,
        "retained_corpus_inventory": corpus_inventory(feedback_artifact, observations),
        "calibration_eligibility_distribution": dict(sorted(Counter(row["calibration_eligibility"]["state"] for row in cohorts).items())),
        "policy_calibration_candidates": build_policy_candidates(cohorts, governed_policy_candidates),
        "source_artifact_identities": {
            "prospective_decision_outcome_feedback_identity": feedback_artifact.get("artifact_identity"),
        },
        "sample_adequacy_policy": {
            "insufficient_sample_below": {"observations": MIN_OBSERVATIONS_DESCRIPTIVE, "distinct_t0_sessions": MIN_SESSIONS_DESCRIPTIVE},
            "descriptive_only_from": {"observations": MIN_OBSERVATIONS_DESCRIPTIVE, "distinct_t0_sessions": MIN_SESSIONS_DESCRIPTIVE},
            "calibrated_research_from": {"observations": MIN_OBSERVATIONS_CALIBRATED, "distinct_t0_sessions": MIN_SESSIONS_CALIBRATED},
            "policy_version": SAMPLE_ADEQUACY_POLICY_VERSION, "authority": "RESEARCH_POLICY_THRESHOLD_NOT_FACTUAL_AUTHORITY",
        },
        "authority_boundary": {
            "prospective_only_no_retroactive_t0_reconstruction": True,
            "no_parallel_backtest_engine": True,
            "no_universal_stock_score": True,
            "no_kelly_cvar_or_probability_based_sizing": True,
            "no_strategy_or_margin_threshold_optimization": True,
            "observed_rates_are_descriptive_not_forecast_probabilities": True,
        },
    }
    return _identity(artifact, "empirical_setup_outcome_calibration_artifact:")


def public_console_summary(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Identities/counts only -- no private, per-ticker, or per-session detail."""
    return {
        "status": "EVALUATED",
        "contract_version": artifact.get("contract_version"),
        "artifact_identity": artifact.get("artifact_identity"),
        "observation_count": artifact.get("observation_count"),
        "t0_session_count": artifact.get("t0_session_count"),
        "cohort_count": artifact.get("cohort_count"),
        "calibrated_research_cohort_count": artifact.get("calibrated_research_cohort_count"),
        "calibration_eligibility_distribution": artifact.get("calibration_eligibility_distribution"),
        "human_review_candidate_count": (artifact.get("policy_calibration_candidates") or {}).get("human_review_candidate_count"),
        "adequacy_state_counts_by_horizon": artifact.get("adequacy_state_counts_by_horizon"),
        "source_artifact_identities": artifact.get("source_artifact_identities"),
    }


# ── Bounded, optional Portfolio V2 research hook (never wired automatically) ──────────────────

def empirical_reward_context_for_cohort(
    calibration_artifact: Mapping[str, Any], *, posture: str, tactical_structure_state: str, invalidation_method: str, horizon: str,
) -> dict[str, Any]:
    """Bounded, read-only lookup for an optional Portfolio V2 research hook.

    Returns a cohort's empirical R-multiple/return context ONLY when that exact cohort reached
    ``CALIBRATED_RESEARCH`` sample adequacy; otherwise explicitly ``NOT_AVAILABLE``. This is never
    a target price, an analyst forecast, an expected return, or execution authority -- it is a
    labelled empirical research estimate a caller may retain as context only. Never silently
    converts MFE into an executable target, and never triggers margin evaluation on its own: a
    caller (e.g. ``portfolio_aware_decision.py``) decides independently whether and how to use it.
    """
    matches = [row for row in calibration_artifact.get("cohorts") or [] if
        all(row["cohort_key"].get(key) == value for key, value in
            (("research_action_posture",posture), ("tactical_structure_state",tactical_structure_state),
             ("invalidation_method",invalidation_method), ("horizon",horizon))) and not row["cohort_key"]["regime_stratified"]]
    if len(matches) != 1:
        return {"status": "NOT_AVAILABLE", "reason": "NO_UNAMBIGUOUS_COMPARABLE_POLICY_COHORT", "authority_boundary": _EMPIRICAL_CONTEXT_BOUNDARY}
    for cohort in matches:
        if cohort.get("sample_adequacy") != CALIBRATED_RESEARCH:
            return {
                "status": "NOT_AVAILABLE", "reason": f"COHORT_SAMPLE_ADEQUACY_{cohort.get('sample_adequacy')}",
                "authority_boundary": _EMPIRICAL_CONTEXT_BOUNDARY,
            }
        return {
            "status": "AVAILABLE",
            "cohort_key_identity": cohort["cohort_key_identity"],
            "matured_observation_count": cohort["matured_observation_count"],
            "distinct_t0_session_count": cohort["distinct_t0_session_count"],
            "empirical_r_multiple_distribution": cohort.get("r_multiple_distribution"),
            "empirical_forward_return_distribution": cohort.get("forward_return_distribution"),
            "empirical_positive_return_rate": cohort.get("empirical_positive_return_rate"),
            "calibration_artifact_identity": calibration_artifact.get("artifact_identity"),
            "authority_boundary": _EMPIRICAL_CONTEXT_BOUNDARY,
        }
    return {"status": "NOT_AVAILABLE", "reason": "NO_MATCHING_COHORT_IN_RETAINED_CALIBRATION_ARTIFACT", "authority_boundary": _EMPIRICAL_CONTEXT_BOUNDARY}


_EMPIRICAL_CONTEXT_BOUNDARY = {
    "is_not_a_target_price": True,
    "is_not_an_analyst_forecast": True,
    "is_not_an_expected_return": True,
    "is_not_execution_authority": True,
    "empirical_research_estimate_not_universal_probability": True,
    "never_silently_converted_to_executable_target": True,
}
