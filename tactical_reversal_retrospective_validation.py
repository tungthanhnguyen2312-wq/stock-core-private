"""Retained-evidence replay and timing diagnostics for tactical reversal states.

This module is deliberately a *consumer* of the existing
``watchlist_tactical_entry_classifier``.  It neither reproduces that classifier's
decision table nor changes its rules.  A retained session is replayed by invoking
``build_artifact`` on the exact registered descriptive, screening, and fundamental
inputs and comparing its SSI/PNJ/PAN records with the retained tactical artifact.

The distinction between a reproducible retained snapshot and a point-in-time
backtest is important.  Retrospectively adjusted technical input can reproduce the
classifier for research, but it cannot become a PIT claim without the already
required qualified factor chain and knowable adjustment cutoff.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

import feature_input_fitness_contract as fitness_contract
import price_basis_feature_fitness as basis
import technical_structure_context
import watchlist_tactical_entry_classifier as classifier


CONTRACT_VERSION = "tactical_reversal_retrospective_validation/v1"
MILESTONE = "TACTICAL_REVERSAL_RETROSPECTIVE_VALIDATION_V1"
REPRESENTATIVE_TICKERS = ("SSI", "PNJ", "PAN")

PIT_QUALIFIED_REPLAY = "PIT_QUALIFIED_REPLAY"
RETROSPECTIVE_RESEARCH_REPLAY = "RETROSPECTIVE_RESEARCH_REPLAY"
NOT_REPLAYABLE = "NOT_REPLAYABLE"
REPLAY_QUALIFICATIONS = frozenset({
    PIT_QUALIFIED_REPLAY,
    RETROSPECTIVE_RESEARCH_REPLAY,
    NOT_REPLAYABLE,
})

EARLY_SIGNAL_NEAR_LOW = "EARLY_SIGNAL_NEAR_LOW"
EARLY_SIGNAL_ACCEPTABLE_LAG = "EARLY_SIGNAL_ACCEPTABLE_LAG"
SIGNAL_TOO_LATE_FOR_BOTTOM_CAPTURE = "SIGNAL_TOO_LATE_FOR_BOTTOM_CAPTURE"
PREMATURE_SIGNAL_FALSE_START = "PREMATURE_SIGNAL_FALSE_START"
NO_ACTIONABLE_REVERSAL_SIGNAL = "NO_ACTIONABLE_REVERSAL_SIGNAL"
INSUFFICIENT_TEMPORAL_OR_BASIS_EVIDENCE = "INSUFFICIENT_TEMPORAL_OR_BASIS_EVIDENCE"
MISSED_OPPORTUNITY_CLASSES = frozenset({
    EARLY_SIGNAL_NEAR_LOW,
    EARLY_SIGNAL_ACCEPTABLE_LAG,
    SIGNAL_TOO_LATE_FOR_BOTTOM_CAPTURE,
    PREMATURE_SIGNAL_FALSE_START,
    NO_ACTIONABLE_REVERSAL_SIGNAL,
    INSUFFICIENT_TEMPORAL_OR_BASIS_EVIDENCE,
})

# Reporting-only diagnostic thresholds.  They are intentionally absent from the
# classifier and do not alter a state/action.  A return is considered only after
# the caller establishes an explicit compatible price lineage.
TIMING_THRESHOLDS = {
    "near_low_max_sessions_after_low": 2,
    "near_low_max_distance_pct": 0.03,
    "acceptable_lag_max_sessions_after_low": 5,
    "acceptable_lag_max_distance_pct": 0.08,
}

TARGET_WINDOW_DECLARATIONS = {
    "SSI": {
        "description": "Late July through early August 2026 decline, easing, initial reversal, and recovery",
        "required_before_session": "2026-08-21",
    },
    "PNJ": {
        "description": "Late July through early August 2026 decline, easing, initial reversal, and recovery",
        "required_before_session": "2026-08-21",
    },
    "PAN": {
        "description": "Most recent retained decline through 2026-09-10",
        "required_through_session": "2026-09-10",
    },
}


class TacticalReversalReplayError(ValueError):
    """Raised when a supposedly historical replay would use incoherent evidence."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = _identity(payload)
    return {
        "artifact_sha256": digest,
        "artifact_identity": f"tactical_reversal_retrospective_validation:{digest}",
    }


def _source_session(source: Mapping[str, Any]) -> str | None:
    for key in ("session", "source_market_session", "resolved_completed_session", "research_session"):
        value = source.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def assert_no_future_session_input(*, target_session: str, inputs: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Validate the temporal boundary before invoking the existing classifier.

    Descriptive/screening/tactical inputs have to be the exact target session.  The
    fundamental source is an already-registered undated context: it is passed to the
    unchanged classifier only for its non-state/action context and is explicitly not
    treated as a PIT fact set.
    """
    required = ("descriptive", "screening", "tactical", "fundamental")
    missing = [name for name in required if not isinstance(inputs.get(name), Mapping)]
    if missing:
        raise TacticalReversalReplayError("REPLAY_INPUTS_MISSING:" + ",".join(missing))

    statuses: dict[str, dict[str, Any]] = {}
    for name in ("descriptive", "screening", "tactical"):
        declared = _source_session(inputs[name])
        if declared is None:
            raise TacticalReversalReplayError(f"REPLAY_SOURCE_SESSION_MISSING:{name}")
        if declared > target_session:
            raise TacticalReversalReplayError(f"FUTURE_SESSION_INPUT_REJECTED:{name}:{declared}>{target_session}")
        if declared != target_session:
            raise TacticalReversalReplayError(f"REPLAY_SOURCE_SESSION_MISMATCH:{name}:{declared}!={target_session}")
        statuses[name] = {"declared_session": declared, "temporal_status": "EXACT_TARGET_SESSION"}

    fundamental_session = _source_session(inputs["fundamental"])
    if fundamental_session is not None and fundamental_session > target_session:
        raise TacticalReversalReplayError(
            f"FUTURE_SESSION_INPUT_REJECTED:fundamental:{fundamental_session}>{target_session}"
        )
    statuses["fundamental"] = {
        "declared_session": fundamental_session,
        "temporal_status": (
            "REGISTERED_NOT_LATER_THAN_TARGET_CONTEXT_ONLY"
            if fundamental_session is not None
            else "REGISTERED_UNDATED_CONTEXT_NOT_A_PIT_CLAIM"
        ),
        "entry_state_or_action_dependency": "NONE",
    }
    return statuses


def _replay_basis_context(
    *, ticker: str, technical_features: Mapping[str, Any], source_artifact_identity: str | None,
) -> dict[str, Any]:
    provenance = technical_features.get("technical_history_provenance") or {}
    provider = provenance.get("provider") if isinstance(provenance, Mapping) else None
    return technical_structure_context.price_basis_fitness_context(
        ticker=ticker,
        technical_features=technical_features,
        source_artifact_identity=source_artifact_identity,
        provider=provider,
    )


def price_replay_fitness(
    *, ticker: str, technical_features: Mapping[str, Any], source_artifact_identity: str | None,
    session: str,
) -> dict[str, Any]:
    """Expose the local research and strict historical-use boundaries for one replay row."""
    context = _replay_basis_context(
        ticker=ticker,
        technical_features=technical_features,
        source_artifact_identity=source_artifact_identity,
    )
    local = fitness_contract.evaluate_price_derived_basis_fitness(
        feature=basis.MA20,
        current_context=context,
        history_context=context,
    )
    pit = fitness_contract.evaluate_price_derived_basis_fitness(
        feature=basis.PIT_BACKTEST,
        current_context=context,
        history_context=context,
        decision_as_of=session,
    )
    # A local current-adjusted feature is allowed to be labelled research-only,
    # but cannot stand in for a verified *cross-session* reconstruction when no
    # qualified corporate-action chain was retained.
    strict_cross_session = {
        "state": basis.BASIS_UNVERIFIED,
        "reason_codes": [basis.REASON_NO_QUALIFIED_FACTOR_CHAIN],
        "note": "No qualified factor-chain identity is retained for a historical cross-session price return or reference-low calculation.",
    }
    return {
        "context": context,
        "local_price_feature_fitness": local,
        "pit_feature_fitness": pit,
        "strict_cross_session_fitness": strict_cross_session,
    }


def replay_qualification(*, temporal_inputs: Mapping[str, Mapping[str, Any]], price_fitness: Mapping[str, Any]) -> str:
    """Name the strongest supported replay class without widening price authority."""
    if not temporal_inputs:
        return NOT_REPLAYABLE
    pit_state = (price_fitness.get("pit_feature_fitness") or {}).get("state")
    if pit_state == basis.BASIS_COMPATIBLE:
        return PIT_QUALIFIED_REPLAY
    return RETROSPECTIVE_RESEARCH_REPLAY


def _replay_equivalence(retained: Mapping[str, Any], replayed: Mapping[str, Any], *, ticker: str) -> dict[str, Any]:
    fields = ("entry_state", "entry_action", "action", "rule_id", "signals")
    mismatches = [field for field in fields if retained.get(field) != replayed.get(field)]
    if mismatches:
        raise TacticalReversalReplayError(
            f"CURRENT_CLASSIFIER_REPLAY_MISMATCH:{ticker}:" + ",".join(mismatches)
        )
    return {"status": "CURRENT_CLASSIFIER_SEMANTICS_REPRODUCED", "compared_fields": list(fields)}


def replay_registered_session(
    *, session: str, inputs: Mapping[str, Mapping[str, Any]], selection: Mapping[str, Mapping[str, Any]],
    tickers: Sequence[str] = REPRESENTATIVE_TICKERS,
) -> dict[str, Any]:
    """Replay one registry-locked session through the actual classifier implementation."""
    temporal_inputs = assert_no_future_session_input(target_session=session, inputs=inputs)
    replayed = classifier.build_artifact(
        descriptive_source=inputs["descriptive"],
        screening_source=inputs["screening"],
        fundamental_source=inputs["fundamental"],
        requested_at=f"RETAINED_REPLAY:{session}",
    )
    retained_records = inputs["tactical"].get("records") or {}
    descriptive_records = inputs["descriptive"].get("records") or {}
    rows: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        retained = retained_records.get(ticker)
        record = replayed.get("records", {}).get(ticker)
        descriptive = descriptive_records.get(ticker)
        if not isinstance(retained, Mapping) or not isinstance(record, Mapping) or not isinstance(descriptive, Mapping):
            rows[ticker] = {
                "ticker": ticker,
                "session": session,
                "replay_qualification": NOT_REPLAYABLE,
                "reason_codes": ["RETAINED_TICKER_INPUT_OR_OUTPUT_ABSENT"],
            }
            continue
        equivalence = _replay_equivalence(retained, record, ticker=ticker)
        technical = descriptive.get("technical_features") or {}
        price_fitness = price_replay_fitness(
            ticker=ticker,
            technical_features=technical,
            source_artifact_identity=(selection.get("descriptive") or {}).get("artifact_identity"),
            session=session,
        )
        qualification = replay_qualification(temporal_inputs=temporal_inputs, price_fitness=price_fitness)
        rows[ticker] = {
            "ticker": ticker,
            "session": session,
            "replay_qualification": qualification,
            "replay_equivalence": equivalence,
            "entry_state": record.get("entry_state"),
            "entry_action": record.get("entry_action"),
            "action": record.get("action"),
            "rule_id": record.get("rule_id"),
            "relevant_reason_codes": [record.get("rule_id")],
            "technical_inputs_consumed": record.get("signals"),
            "market_context_consumed": {
                "classifier_market_state": record.get("market_state"),
                "breadth_descriptor": ((inputs["descriptive"].get("market_breadth") or {}).get("breadth_descriptor") or {}).get("descriptor"),
                "momentum_descriptor": ((inputs["descriptive"].get("market_breadth") or {}).get("momentum_descriptor") or {}).get("descriptor"),
                "volatility_median_used_by_rules": ((inputs["descriptive"].get("market_breadth") or {}).get("volatility") or {}).get("median"),
                "entry_state_gate": "NONE; market regime labels are context only",
            },
            "fundamental_context_consumed": record.get("fundamental_context"),
            "feature_basis_fitness": price_fitness,
            "source_artifacts": {
                name: {
                    "artifact_identity": (selection.get(name) or {}).get("artifact_identity"),
                    "relative_path": (selection.get(name) or {}).get("path"),
                }
                for name in ("descriptive", "screening", "fundamental", "tactical")
            },
            "temporal_inputs": temporal_inputs,
        }
    return {
        "session": session,
        "classifier_contract_version": classifier.CONTRACT_VERSION,
        "classifier_replay_method": "watchlist_tactical_entry_classifier.build_artifact",
        "records": rows,
    }


def first_transition(rows: Sequence[Mapping[str, Any]], *, field: str = "entry_state") -> dict[str, Any] | None:
    """Return the first chronological state change, never inferring omitted sessions."""
    sentinel = object()
    prior: Any = sentinel
    for row in rows:
        value = row.get(field)
        if prior is not sentinel and value != prior:
            return {
                "session": row.get("session"),
                "from": prior,
                "to": value,
                "field": field,
            }
        prior = value
    return None


def _first_matching(rows: Sequence[Mapping[str, Any]], *, field: str, accepted: Sequence[str]) -> dict[str, Any] | None:
    for row in rows:
        if row.get(field) in accepted:
            return {"session": row.get("session"), field: row.get(field), "rule_id": row.get("rule_id")}
    return None


def same_basis_return(
    *, start: Mapping[str, Any], end: Mapping[str, Any], start_price: float | None, end_price: float | None,
) -> dict[str, Any]:
    """Compute a diagnostic return only after explicit same-lineage compatibility.

    The default retained SSI/PNJ/PAN rows deliberately fail this gate: the inputs say
    current-retrospective adjusted, but do not retain a qualified factor chain for a
    historical cross-session return.  The separate raw-vs-adjusted check makes it
    impossible to accidentally combine those bases.
    """
    start_context = ((start.get("feature_basis_fitness") or {}).get("context") or {})
    end_context = ((end.get("feature_basis_fitness") or {}).get("context") or {})
    start_basis, end_basis = start_context.get("observed_basis"), end_context.get("observed_basis")
    if start_basis != end_basis:
        return {"status": "NOT_COMPUTED", "reason_codes": [basis.REASON_BASIS_MISMATCH], "return_pct": None}
    if start_basis != basis.CURRENT_RETROSPECTIVE_ADJUSTED and start_basis != basis.POINT_IN_TIME_ADJUSTED:
        return {"status": "NOT_COMPUTED", "reason_codes": ["UNSUPPORTED_PRICE_BASIS_FOR_RESEARCH_RETURN"], "return_pct": None}
    if (start.get("feature_basis_fitness") or {}).get("strict_cross_session_fitness", {}).get("state") != basis.BASIS_COMPATIBLE:
        return {"status": "NOT_COMPUTED", "reason_codes": ["CROSS_SESSION_PRICE_BASIS_UNVERIFIED"], "return_pct": None}
    if (end.get("feature_basis_fitness") or {}).get("strict_cross_session_fitness", {}).get("state") != basis.BASIS_COMPATIBLE:
        return {"status": "NOT_COMPUTED", "reason_codes": ["CROSS_SESSION_PRICE_BASIS_UNVERIFIED"], "return_pct": None}
    if not isinstance(start_price, (int, float)) or not isinstance(end_price, (int, float)) or start_price == 0:
        return {"status": "NOT_COMPUTED", "reason_codes": ["PRICE_INPUT_MISSING"], "return_pct": None}
    return {
        "status": "COMPUTED_SAME_BASIS_ONLY",
        "reason_codes": [],
        "return_pct": (float(end_price) - float(start_price)) / float(start_price),
    }


def detect_false_start(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Detect a lower-low only from already compatible diagnostic price observations."""
    early_index = next((index for index, row in enumerate(rows) if row.get("entry_action") == "EARLY_ENTRY"), None)
    if early_index is None:
        return {"status": "NO_EARLY_ENTRY_SIGNAL", "lower_low_after_first_early_signal": None}
    signal = rows[early_index]
    signal_price = signal.get("comparable_price")
    if not isinstance(signal_price, (int, float)):
        return {"status": "NOT_COMPUTED", "lower_low_after_first_early_signal": None, "reason_codes": ["COMPARABLE_PRICE_UNAVAILABLE"]}
    for row in rows[early_index + 1:]:
        price = row.get("comparable_price")
        if isinstance(price, (int, float)) and price < signal_price:
            return {
                "status": "LOWER_LOW_AFTER_FIRST_EARLY_SIGNAL",
                "lower_low_after_first_early_signal": True,
                "signal_session": signal.get("session"),
                "lower_low_session": row.get("session"),
            }
    return {"status": "NO_LOWER_LOW_OBSERVED", "lower_low_after_first_early_signal": False}


def classify_missed_opportunity(
    *, target_window_replayability: str, timing_metrics_available: bool,
    first_early_entry: Mapping[str, Any] | None, reference_low_session_index: int | None,
    first_early_entry_session_index: int | None, distance_from_low_pct: float | None,
    false_start: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply reporting-only, transparent thresholds without touching tactical policy."""
    if target_window_replayability == NOT_REPLAYABLE or not timing_metrics_available:
        return {
            "classification": INSUFFICIENT_TEMPORAL_OR_BASIS_EVIDENCE,
            "reason_codes": ["TARGET_WINDOW_OR_SAME_BASIS_TIMING_METRICS_UNAVAILABLE"],
        }
    if first_early_entry is None:
        return {"classification": NO_ACTIONABLE_REVERSAL_SIGNAL, "reason_codes": ["NO_EARLY_ENTRY_IN_REPLAYABLE_WINDOW"]}
    if false_start.get("lower_low_after_first_early_signal") is True:
        return {"classification": PREMATURE_SIGNAL_FALSE_START, "reason_codes": ["LOWER_LOW_AFTER_FIRST_EARLY_SIGNAL"]}
    if reference_low_session_index is None or first_early_entry_session_index is None or distance_from_low_pct is None:
        return {
            "classification": INSUFFICIENT_TEMPORAL_OR_BASIS_EVIDENCE,
            "reason_codes": ["REFERENCE_LOW_OR_DISTANCE_UNAVAILABLE"],
        }
    lag = first_early_entry_session_index - reference_low_session_index
    if lag <= TIMING_THRESHOLDS["near_low_max_sessions_after_low"] and distance_from_low_pct <= TIMING_THRESHOLDS["near_low_max_distance_pct"]:
        category = EARLY_SIGNAL_NEAR_LOW
    elif lag <= TIMING_THRESHOLDS["acceptable_lag_max_sessions_after_low"] and distance_from_low_pct <= TIMING_THRESHOLDS["acceptable_lag_max_distance_pct"]:
        category = EARLY_SIGNAL_ACCEPTABLE_LAG
    else:
        category = SIGNAL_TOO_LATE_FOR_BOTTOM_CAPTURE
    return {"classification": category, "reason_codes": [], "session_lag": lag, "distance_from_low_pct": distance_from_low_pct}


def _target_window_replayability(ticker: str, available_sessions: Sequence[str]) -> dict[str, Any]:
    declaration = TARGET_WINDOW_DECLARATIONS[ticker]
    if ticker in ("SSI", "PNJ"):
        earlier = [session for session in available_sessions if session < declaration["required_before_session"]]
        if not earlier:
            return {
                "qualification": NOT_REPLAYABLE,
                "reason_codes": ["NO_RETAINED_COHERENT_CLASSIFIER_SNAPSHOT_FOR_LATE_JULY_TO_EARLY_AUGUST"],
                "available_sessions": list(available_sessions),
                "declaration": declaration,
            }
    if ticker == "PAN" and declaration["required_through_session"] not in available_sessions:
        return {
            "qualification": NOT_REPLAYABLE,
            "reason_codes": ["PAN_2026_09_10_SESSION_NOT_RETAINED"],
            "available_sessions": list(available_sessions),
            "declaration": declaration,
        }
    return {
        "qualification": RETROSPECTIVE_RESEARCH_REPLAY,
        "reason_codes": ["RETAINED_EXACT_SESSION_SNAPSHOTS_AVAILABLE_BUT_PIT_UNQUALIFIED"],
        "available_sessions": list(available_sessions),
        "declaration": declaration,
    }


def _bottom_timing(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    first_easing = _first_matching(rows, field="entry_state", accepted=("SELLING_PRESSURE_EASING",))
    first_early = _first_matching(rows, field="entry_state", accepted=("EARLY_REVERSAL_CANDIDATE",))
    first_confirmation = _first_matching(rows, field="entry_action", accepted=("BUY_ON_CONFIRMATION",))
    first_early_action = _first_matching(rows, field="entry_action", accepted=("EARLY_ENTRY",))
    return {
        "status": "NOT_COMPUTED",
        "reference_low_session": None,
        "reference_low_price": None,
        "reference_low_basis": None,
        "classifier_on_reference_low": None,
        "first_selling_pressure_easing": first_easing,
        "first_early_reversal_candidate": first_early,
        "first_early_probe_action": first_early_action,
        "first_stronger_confirmation": first_confirmation,
        "distance_from_reference_low": None,
        "session_lag_from_reference_low": None,
        "mae_mfe": None,
        "reason_codes": ["CROSS_SESSION_PRICE_BASIS_UNVERIFIED", "NO_QUALIFIED_CORPORATE_ACTION_FACTOR_CHAIN"],
    }


def _pan_now(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    current = next((row for row in reversed(rows) if row.get("session") == "2026-09-10"), None)
    if not isinstance(current, Mapping):
        return {"status": "NOT_REPLAYABLE", "reason_codes": ["PAN_2026_09_10_RETAINED_ROW_ABSENT"]}
    signals = current.get("technical_inputs_consumed") or {}
    return {
        "status": "RETAINED_CURRENT_RESEARCH_CONTEXT_ONLY",
        "session": "2026-09-10",
        "entry_state": current.get("entry_state"),
        "entry_action": current.get("entry_action"),
        "rule_id": current.get("rule_id"),
        "prior_retained_selling_pressure_easing": _first_matching(rows, field="entry_state", accepted=("SELLING_PRESSURE_EASING",)),
        "current_separators_from_early_reversal": {
            "momentum_20d": signals.get("momentum_20d"),
            "momentum_must_turn_positive_for_r6": True,
            "close_is_still_at_or_below_ma20": not bool(signals.get("close", 0) > signals.get("ma_20", 0)),
            "independent_r6_confirmation_required_after_momentum_flip": [
                "market_relative_momentum_bucket_upper_half",
                "sector_relative_momentum_bucket_upper_half",
                "positive_return_and_above_median_provider_relative_volume",
            ],
            "current_today_positive": (signals.get("return_1d") or 0) > 0,
            "current_momentum_bucket": signals.get("momentum_bucket"),
            "current_sector_momentum_bucket": signals.get("sector_momentum_bucket"),
            "current_elevated_volume": signals.get("elevated_volume_vs_cohort_median"),
        },
        "conditions_that_can_change_without_ma50_or_ma200": [
            "A positive return or upper-half market-relative momentum can produce R8 SELLING_PRESSURE_EASING while momentum remains negative.",
            "A positive 20-day momentum flip plus one existing R6 independent confirmation can produce EARLY_REVERSAL_CANDIDATE before an MA20 reclaim.",
            "MA50 and MA200 are not inputs to the existing classifier decision table.",
        ],
        "bottom_prediction": "NOT_MADE",
    }


def build_diagnostic(
    *, registry: Mapping[str, Any], inputs_by_session: Mapping[str, Mapping[str, Mapping[str, Any]]],
    selections_by_session: Mapping[str, Mapping[str, Mapping[str, Any]]],
    tickers: Sequence[str] = REPRESENTATIVE_TICKERS,
) -> dict[str, Any]:
    """Build a deterministic retained-data diagnostic from registry-resolved snapshots."""
    sessions = sorted(inputs_by_session)
    replayed_sessions = {
        session: replay_registered_session(
            session=session,
            inputs=inputs_by_session[session],
            selection=selections_by_session[session],
            tickers=tickers,
        )
        for session in sessions
    }
    cases: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        rows = [replayed_sessions[session]["records"][ticker] for session in sessions if ticker in replayed_sessions[session]["records"]]
        transitions = []
        previous = None
        for row in rows:
            if previous is not None and row.get("entry_state") != previous.get("entry_state"):
                transitions.append({
                    "session": row.get("session"),
                    "from_state": previous.get("entry_state"),
                    "to_state": row.get("entry_state"),
                    "from_action": previous.get("entry_action"),
                    "to_action": row.get("entry_action"),
                })
            previous = row
        target_replay = _target_window_replayability(ticker, [row.get("session") for row in rows])
        timing = _bottom_timing(rows)
        false_start = detect_false_start(rows)
        missed = classify_missed_opportunity(
            target_window_replayability=target_replay["qualification"],
            timing_metrics_available=timing["status"] == "COMPUTED_SAME_BASIS_ONLY",
            first_early_entry=timing["first_early_probe_action"],
            reference_low_session_index=None,
            first_early_entry_session_index=None,
            distance_from_low_pct=None,
            false_start=false_start,
        )
        cases[ticker] = {
            "target_window_replayability": target_replay,
            "registered_snapshot_rows": rows,
            "chronological_transitions": transitions,
            "bottom_timing": timing,
            "false_start_diagnostic": false_start,
            "missed_opportunity": missed,
        }
    pan_rows = cases.get("PAN", {}).get("registered_snapshot_rows", [])
    market_0910 = ((inputs_by_session.get("2026-09-10", {}).get("descriptive") or {}).get("market_breadth") or {})
    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "replay_qualification_vocabulary": sorted(REPLAY_QUALIFICATIONS),
        "missed_opportunity_vocabulary": sorted(MISSED_OPPORTUNITY_CLASSES),
        "timing_thresholds_reporting_only": dict(TIMING_THRESHOLDS),
        "replay_sessions": replayed_sessions,
        "cases": cases,
        "pan_now": _pan_now(pan_rows),
        "market_regime_interaction": {
            "session": "2026-09-10",
            "retained_breadth": {
                "above_ma20": (market_0910.get("trend") or {}).get("above_ma20"),
                "technical_feature_denominator": market_0910.get("same_session_technical_feature_available_count"),
                "negative_20d_momentum_count": ((market_0910.get("momentum_descriptor") or {}).get("input_statistics") or {}).get("negative_count"),
                "negative_20d_momentum_share": ((market_0910.get("momentum_descriptor") or {}).get("input_statistics") or {}).get("negative_share"),
                "breadth_descriptor": ((market_0910.get("breadth_descriptor") or {}).get("descriptor")),
                "momentum_descriptor": ((market_0910.get("momentum_descriptor") or {}).get("descriptor")),
            },
            "classifier_effect": "Market breadth/regime labels are passed through as context and do not gate or downgrade an entry_state or entry_action.",
            "rule_level_exception": "The contemporaneous volatility median is a technical input to R2/R7; it is not a market-regime/breadth gate.",
            "policy_changed": False,
        },
        "authority_boundary": {
            "classifier_policy_changed": False,
            "canonical_daily_modified": False,
            "integrated_decision_modified": False,
            "raw_as_traded": "NOT_PROMOTED",
            "historical_pit": "NOT_PROMOTED",
            "price_basis_authority": "UNCHANGED",
            "liquidity_execution_sizing": "UNCHANGED_AND_BLOCKED",
            "provider_or_network_calls": False,
            "calibrated_probability_output": "NOT_AVAILABLE_CASE_STUDY_ONLY",
            "runtime_root_written": False,
        },
        "source_registry_contract": registry.get("contract_version"),
    }
    artifact.update(content_identity(artifact))
    return artifact
