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
import integrated_investment_decision_product as decision_product
import prospective_decision_outcome_feedback as outcome_feedback
import prospective_decision_retention as retention

CONTRACT_VERSION = "empirical_setup_outcome_calibration/v1"
METHOD_VERSION = "empirical_setup_outcome_calibration/v1"

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
    """Union of the two genuine T0 sources' own already-qualified chains/snapshots.

    ``prospective_decision_outcome_feedback.build_feedback_artifact()`` internally evaluates T5/
    T10/T20 against a branch-specific chain (immutable-snapshot-sourced "modern" sessions, or
    canonical-handoff-qualified "legacy" sessions) depending on which genuine T0 source produced a
    given record. For this milestone's own new T60 horizon we use the union of both -- at least as
    complete as, never a subset of, either branch's own chain, so this introduces no additional
    look-ahead risk relative to what the existing bridge already established; it may resolve
    marginally sooner maturity than a strict single-branch chain would for a record whose T0
    session is only qualified on one branch. Both snapshot shapes are already compatible with
    ``retained_session_price_observations`` (session-keyed ``records[ticker].observations`` rows).
    """
    modern = outcome_feedback._modern_snapshot_candidates(root)
    corpus = outcome_feedback.discover_prospective_corpus(root)
    legacy_chain = corpus["qualified_session_chain"]
    legacy_snapshots = outcome_feedback.retained_session_snapshots(root, legacy_chain)
    chain = sorted(set(legacy_chain) | set(modern["chain"]))
    snapshots: dict[str, Mapping[str, Any]] = {**legacy_snapshots, **modern["snapshots"]}
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
    invalidation_level = (record.get("invalidation") or {}).get("invalidation_level")
    entry = (record.get("trigger") or {}).get("trigger_level")
    if entry is None:
        entry = t0_close
    if not isinstance(entry, (int, float)) or entry == 0:
        return None, "UNAVAILABLE_NO_T0_ENTRY_REFERENCE"
    if not isinstance(invalidation_level, (int, float)):
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
        return "TARGET_BEFORE_INVALIDATION" if target_session < invalidation_session else "INVALIDATION_BEFORE_TARGET"
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
            "r_multiple": r_multiple,
            "r_multiple_status": r_multiple_status,
        }

    invalidation_event = (record.get("trigger_invalidation_outcome") or {}).get("invalidation") or {}
    invalidation_hit = invalidation_event.get("status") == "SATISFIED"
    invalidation = {
        "status": invalidation_event.get("status", NOT_EVALUATED),
        "hit": invalidation_hit,
        "event_session": invalidation_event.get("event_session"),
        "sessions_to_invalidation": _event_sessions_to(chain, decision_session, invalidation_event.get("event_session")) if invalidation_hit else None,
        "condition_identity": invalidation_event.get("condition_identity"),
    }

    if target_level is None:
        target = {"status": NOT_EVALUATED, "hit": None, "event_session": None, "sessions_to_target": None,
                  "reason": "NO_DETERMINISTIC_TARGET_REWARD_BOUNDARY_RETAINED_AT_T0"}
    else:
        condition = _target_condition(target_level=target_level, direction=target_direction)
        event = retention.evaluate_serialized_close_condition(
            condition, ticker=ticker, chain=chain, start_session=decision_session, snapshots=snapshots,
        )
        hit = event.get("status") == "SATISFIED"
        target = {
            "status": "EVALUATED", "hit": hit, "event_session": event.get("event_session"),
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
            "prospective_only": True, "no_retroactive_t0_reconstruction": True,
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


def cohort_key(observation: Mapping[str, Any], *, horizon: str, with_regime: bool = False) -> tuple[Any, ...]:
    """Versioned comparable-cohort key, prioritizing action/posture family, setup family,
    invalidation method, horizon, and feature/decision contract versions. Never fragments by
    ticker or sector by default; never pools incompatible setup/method versions.
    """
    base = (
        _FEATURE_CONTRACT_VERSIONS["integrated_decision_contract"],
        _FEATURE_CONTRACT_VERSIONS["prospective_feedback_contract"],
        observation["research_action_posture_at_t0"],
        observation["tactical_structure_state_at_t0"],
        observation["invalidation_method_at_t0"],
        horizon,
    )
    if with_regime:
        return base + (observation["market_regime_at_t0"],)
    return base


def cohort_key_identity(key: Sequence[Any]) -> str:
    return "empirical_setup_cohort:" + _hash(list(key))


_COHORT_KEY_FIELDS = (
    "integrated_decision_contract", "prospective_feedback_contract", "research_action_posture",
    "tactical_structure_state", "invalidation_method", "horizon",
)


def _cohort_key_view(key: Sequence[Any], *, with_regime: bool) -> dict[str, Any]:
    view = dict(zip(_COHORT_KEY_FIELDS, key))
    if with_regime:
        view["market_regime"] = key[len(_COHORT_KEY_FIELDS)]
    view["regime_stratified"] = with_regime
    return view


def _aggregate_one_cohort(key: Sequence[Any], members: Sequence[Mapping[str, Any]], *, horizon: str, with_regime: bool) -> dict[str, Any]:
    matured = [item for item in members if item["horizons"][horizon]["status"] == feedback_bridge.MATURE]
    distinct_sessions = {item["t0_session"] for item in matured}
    adequacy = sample_adequacy(len(matured), len(distinct_sessions))

    forward_returns = [item["horizons"][horizon]["forward_return"] for item in matured]
    mfe_values = [item["horizons"][horizon]["mfe_close_proxy"] for item in matured if item["horizons"][horizon]["mfe_close_proxy"] is not None]
    mae_values = [item["horizons"][horizon]["mae_close_proxy"] for item in matured if item["horizons"][horizon]["mae_close_proxy"] is not None]
    r_values = [item["horizons"][horizon]["r_multiple"] for item in matured if item["horizons"][horizon]["r_multiple"] is not None]

    invalidation_hits = sum(1 for item in members if item["invalidation"]["hit"])
    invalidation_evaluable = sum(1 for item in members if item["invalidation"]["status"] in {"SATISFIED", "NOT_SATISFIED_YET"})
    target_evaluable = [item for item in members if item["target"]["status"] == "EVALUATED"]
    target_hits = sum(1 for item in target_evaluable if item["target"]["hit"])

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
                "median_sessions_to_target": _median([item["target"]["sessions_to_target"] for item in target_evaluable if item["target"]["sessions_to_target"] is not None]),
                "ordering_counts": dict(sorted(Counter(item["target_invalidation_ordering"] for item in target_evaluable).items())),
            }
        ),
        "empirical_positive_return_rate": positive_rate,
        "uncertainty_note": (
            "EMPIRICAL_RESEARCH_ESTIMATE_NOT_UNIVERSAL_PROBABILITY" if adequacy == CALIBRATED_RESEARCH
            else "DESCRIPTIVE_SAMPLE_ONLY_NO_PROBABILITY_CLAIM" if adequacy == DESCRIPTIVE_ONLY
            else "SAMPLE_TOO_SMALL_FOR_ANY_DISTRIBUTIONAL_STATEMENT"
        ),
        "source_lineage": {
            "t0_decision_identities": sorted({item["t0_decision_identity"] for item in members if item.get("t0_decision_identity")}),
            "t0_snapshot_identities": sorted({item["t0_snapshot_identity"] for item in members if item.get("t0_snapshot_identity")}),
            "observation_identities": sorted(item["observation_identity"] for item in members),
        },
        "authority_boundary": {
            "not_a_universal_stock_score": True,
            "probability_emitted_only_when_calibrated_research": adequacy == CALIBRATED_RESEARCH,
            "no_threshold_optimization": True,
            "no_kelly_cvar_or_probability_based_sizing": True,
        },
    }
    return _identity(cohort, "empirical_setup_outcome_cohort:")


def aggregate_cohorts(observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group observations into versioned comparable cohorts per horizon and compute calibration.

    Market regime is used as an optional stratification: a regime-stratified variant of a cohort
    is emitted alongside (never instead of) its base, non-stratified cohort only when every member
    actually retains a regime value and the stratified split itself would still clear the
    ``DESCRIPTIVE_ONLY`` sample floor -- otherwise the corpus is not over-fragmented by regime.
    """
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

def build_calibration_artifact(
    root: str | None = None, *, feedback_artifact: Mapping[str, Any] | None = None,
    target_level_by_ticker_session: Mapping[tuple[str, str], tuple[float, str]] | None = None,
    chain: Sequence[str] | None = None, snapshots: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Deterministic, read-only calibration artifact over the retained prospective corpus.

    Never runs Daily, never acquires provider data, never reconstructs a T0 decision that was not
    genuinely retained. ``root`` is required unless ``feedback_artifact``/``chain``/``snapshots``
    are supplied directly (the synthetic-fixture test path).
    """
    if feedback_artifact is None:
        if root is None:
            raise ValueError("EITHER_ROOT_OR_FEEDBACK_ARTIFACT_REQUIRED")
        feedback_artifact = outcome_feedback.build_feedback_artifact(root)
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
        "source_artifact_identities": {
            "prospective_decision_outcome_feedback_identity": feedback_artifact.get("artifact_identity"),
        },
        "sample_adequacy_policy": {
            "insufficient_sample_below": {"observations": MIN_OBSERVATIONS_DESCRIPTIVE, "distinct_t0_sessions": MIN_SESSIONS_DESCRIPTIVE},
            "descriptive_only_from": {"observations": MIN_OBSERVATIONS_DESCRIPTIVE, "distinct_t0_sessions": MIN_SESSIONS_DESCRIPTIVE},
            "calibrated_research_from": {"observations": MIN_OBSERVATIONS_CALIBRATED, "distinct_t0_sessions": MIN_SESSIONS_CALIBRATED},
            "policy_version": METHOD_VERSION, "authority": "RESEARCH_POLICY_THRESHOLD_NOT_FACTUAL_AUTHORITY",
        },
        "authority_boundary": {
            "prospective_only_no_retroactive_t0_reconstruction": True,
            "no_parallel_backtest_engine": True,
            "no_universal_stock_score": True,
            "no_kelly_cvar_or_probability_based_sizing": True,
            "no_strategy_or_margin_threshold_optimization": True,
            "empirical_probability_only_at_calibrated_research_adequacy": True,
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
    key = (
        _FEATURE_CONTRACT_VERSIONS["integrated_decision_contract"], _FEATURE_CONTRACT_VERSIONS["prospective_feedback_contract"],
        posture, tactical_structure_state, invalidation_method, horizon,
    )
    target_identity = cohort_key_identity(key)
    for cohort in calibration_artifact.get("cohorts") or []:
        if cohort.get("cohort_key_identity") != target_identity or cohort["cohort_key"]["regime_stratified"]:
            continue
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
