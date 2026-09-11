"""Research-only shadow counterfactual evaluation of the R6/R8 tactical reversal policy.

This module answers one bounded question: across a broad, deterministic, local
reconstruction of past sessions, would a small set of T0-only shadow "probe" policies
have offered materially earlier useful entry timing than the existing R6
``EARLY_REVERSAL_CANDIDATE`` -> ``EARLY_ENTRY`` rule, without an unacceptable false-start
cost -- compared against the unchanged classifier as the control.

It is deliberately a *consumer*.  It does not copy or alter
``watchlist_tactical_entry_classifier``'s rule table, does not create a new evidence
foundation (session reconstruction is delegated to
``historical_tactical_replay_evidence_foundation``'s existing sqlite-freeze and
descriptive/screening/classifier composition), and does not introduce a weighted score
or sizing policy.  Every shadow candidate is a pure function of one session's own
classifier-produced signals plus, where declared, the immediately adjacent prior
reconstructed session's own rule_id for the same ticker -- never a later observation.
Outcome evaluation (reference-low distance, MAE/MFE, confirmation lag) is research-only
retrospective-adjusted labeling, applied strictly after a signal is already decided.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from statistics import mean, median
from typing import Any, Callable, Mapping, Sequence

import current_market_screening_opportunity_comparison_foundation as screening_module
import historical_tactical_replay_evidence_foundation as foundation
import tactical_reversal_retrospective_validation as validation
import watchlist_tactical_entry_classifier as classifier


CONTRACT_VERSION = "tactical_reversal_probe_policy_counterfactual_evaluation/v1"
MILESTONE = "TACTICAL_REVERSAL_PROBE_POLICY_COUNTERFACTUAL_EVALUATION_V1"

KEEP_CURRENT_R6_POLICY = "KEEP_CURRENT_R6_POLICY"
EVIDENCE_SUPPORTS_SHADOW_PROBE_POLICY = "EVIDENCE_SUPPORTS_SHADOW_PROBE_POLICY"
INSUFFICIENT_COHORT_EVIDENCE = "INSUFFICIENT_COHORT_EVIDENCE"
TERMINAL_DECISIONS = frozenset({
    KEEP_CURRENT_R6_POLICY, EVIDENCE_SUPPORTS_SHADOW_PROBE_POLICY, INSUFFICIENT_COHORT_EVIDENCE,
})

R8_RULE_ID = "R8_SELLING_PRESSURE_EASING"
R6_RULE_ID = "R6_EARLY_REVERSAL_CANDIDATE"
CONFIRMATION_RULE_IDS = ("R6_EARLY_REVERSAL_CANDIDATE", "R3_UPTREND_CONFIRMED_DEFAULT", "R2_BREAKOUT_READY_CONFIRMED")
BREAKDOWN_RULE_IDS = ("R5_BREAKDOWN_RISK", "R9_DOWNTREND_DEFAULT")
UPPER_HALF_MOMENTUM = frozenset({"UPPER_QUARTILE", "UPPER_MIDDLE"})

# Reused verbatim from the retained retrospective-validation module: these are
# reporting-only diagnostic thresholds, not classifier policy.  See
# tactical_reversal_retrospective_validation.TIMING_THRESHOLDS.
TIMING_THRESHOLDS = validation.TIMING_THRESHOLDS

MIN_COHORT_TICKERS = 30
MIN_COHORT_R8_EPISODES = 30


class TacticalReversalProbePolicyEvaluationError(ValueError):
    """A cohort, evidence, or temporal contract required by this evaluation was not met."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _identity(prefix: str, value: Any) -> str:
    return f"{prefix}:{_digest(value)}"


# --------------------------------------------------------------------------------------
# Cohort session discovery (enumeration only; the actual reconstruction is delegated to
# historical_tactical_replay_evidence_foundation, never duplicated here).
# --------------------------------------------------------------------------------------

def available_sessions(runtime_root: Path, *, start: str, end: str, source: str = foundation.DNSE_SOURCE) -> list[str]:
    """List distinct provider-scoped local sessions in [start, end] without a provider call."""
    database = Path(runtime_root) / "vn_stock.db"
    if not database.is_file():
        raise TacticalReversalProbePolicyEvaluationError("RUNTIME_CAPABILITY_VN_STOCK_DB_MISSING")
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    try:
        rows = connection.execute(
            "SELECT DISTINCT date FROM ohlcv WHERE date BETWEEN ? AND ? AND source = ? ORDER BY date",
            (start, end, source),
        ).fetchall()
    finally:
        connection.close()
    return [str(row[0]) for row in rows]


def reconstruct_cohort_sessions(runtime_root: Path, *, sessions: Sequence[str]) -> dict[str, Any]:
    """Reconstruct every T0 candidate ticker's classifier output per session.

    Reuses ``historical_tactical_replay_evidence_foundation``'s sqlite-freeze and its
    descriptive/screening/classifier composition exactly as
    HISTORICAL_TACTICAL_REPLAY_EVIDENCE_FOUNDATION_V1 does, but retains every T0
    candidate ticker rather than narrowing to a fixed representative pair.  A session
    without a complete 20-session lookback window (insufficient local history) is
    recorded as an explicit exclusion, never silently skipped or defaulted.
    """
    reconstructions: dict[str, Any] = {}
    session_exclusions: dict[str, str] = {}
    for session in sessions:
        try:
            freeze = foundation.freeze_sqlite_evidence(runtime_root, target_sessions=(session,))
        except foundation.HistoricalTacticalReplayEvidenceError as error:
            session_exclusions[session] = str(error)
            continue
        selection = freeze["selections"][session]
        rows = foundation._selection_rows(freeze, selection, kind="ohlcv")
        lineages = foundation._selection_rows(freeze, selection, kind="lineage")
        descriptive = foundation._descriptive_source(selection=selection, rows=rows, lineages=lineages)
        screening = screening_module.build_artifact(descriptive)
        fundamental = foundation._fundamental_source(session)
        result = classifier.build_artifact(
            descriptive_source=descriptive, screening_source=screening, fundamental_source=fundamental,
            requested_at=f"HISTORICAL_RECONSTRUCTION:{session}",
        )
        reconstructions[session] = {
            "session": session,
            "candidate_ticker_count": len(selection["candidate_tickers"]),
            "selected_rows_identity": selection["selected_rows_identity"],
            "source_artifacts": {
                "descriptive": descriptive["artifact_identity"],
                "screening": screening["artifact_identity"],
                "fundamental": fundamental["artifact_identity"],
                "classifier": result["artifact_identity"],
            },
            "records": result["records"],
        }
    return {"reconstructions": reconstructions, "session_exclusions": session_exclusions}


def ticker_series(reconstructions: Mapping[str, Mapping[str, Any]], *, all_sessions: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
    """Build each ticker's own chronological, gap-aware row sequence.

    A row is only present for a session where that ticker was an actual T0 candidate
    with a resolvable classifier record; missing days are gaps, never interpolated.
    Each row carries whether its immediate predecessor in the ticker's own sequence is
    truly the adjacent trading session (no gap) -- required for any T0-legitimate
    "prior session" candidate condition.
    """
    session_index = {session: index for index, session in enumerate(all_sessions)}
    by_ticker: dict[str, dict[str, Mapping[str, Any]]] = {}
    for session in all_sessions:
        replay = reconstructions.get(session)
        if replay is None:
            continue
        for tick, record in replay["records"].items():
            by_ticker.setdefault(tick, {})[session] = record

    series: dict[str, list[dict[str, Any]]] = {}
    for tick, by_session in by_ticker.items():
        ordered_sessions = sorted(by_session, key=lambda s: session_index[s])
        rows: list[dict[str, Any]] = []
        for position, session in enumerate(ordered_sessions):
            prior_session = ordered_sessions[position - 1] if position > 0 else None
            adjacent = (
                prior_session is not None
                and session_index[session] - session_index[prior_session] == 1
            )
            rows.append({
                "session": session,
                "session_index": session_index[session],
                "position": position,
                "record": by_session[session],
                "prior_row": rows[position - 1] if (position > 0 and adjacent) else None,
                "prior_row_gap": prior_session is not None and not adjacent,
            })
        series[tick] = rows
    return series


# --------------------------------------------------------------------------------------
# Shadow candidate policies.  Each evaluator reads only the current row's own
# classifier-produced rule_id/signals plus, where declared, the immediately adjacent
# prior row's rule_id for the same ticker.  None ever reads a later session.
# --------------------------------------------------------------------------------------

def _is_r8(record: Mapping[str, Any]) -> bool:
    return record.get("rule_id") == R8_RULE_ID


def candidate_r8_momentum_bucket_subset(row: Mapping[str, Any]) -> dict[str, Any]:
    """Strict subset of R8: only the market-relative-momentum-upper-half confirmation arm.

    Drops R8's weaker "today's return positive" arm entirely.  Since R8 only fires when
    momentum_20d is not yet positive, this is by construction a pre-momentum-positive
    signal -- the milestone's required strict-subset-of-R8 candidate.
    """
    record = row["record"]
    if not _is_r8(record):
        return {"eligible": False, "reason_codes": ["NOT_R8_SELLING_PRESSURE_EASING"]}
    bucket = (record.get("signals") or {}).get("momentum_bucket")
    if bucket is None:
        return {"eligible": None, "reason_codes": ["MOMENTUM_BUCKET_UNAVAILABLE"]}
    if bucket in UPPER_HALF_MOMENTUM:
        return {"eligible": True, "reason_codes": ["R8_WITH_MARKET_RELATIVE_MOMENTUM_UPPER_HALF"]}
    return {"eligible": False, "reason_codes": ["R8_MOMENTUM_BUCKET_NOT_UPPER_HALF"]}


def candidate_r8_two_session_persistence(row: Mapping[str, Any]) -> dict[str, Any]:
    """R8 required on two consecutive reconstructed sessions before PROBE_ELIGIBLE.

    A single-day easing blip (the PAN 2026-09-09 pattern) never qualifies.  If the
    immediately adjacent prior session is unavailable (no candidate row, or a genuine
    calendar gap), persistence cannot be confirmed and the row is explicitly marked
    unevaluable -- never defaulted to eligible or ineligible.
    """
    record = row["record"]
    if not _is_r8(record):
        return {"eligible": False, "reason_codes": ["NOT_R8_SELLING_PRESSURE_EASING"]}
    prior_row = row.get("prior_row")
    if prior_row is None:
        reason = "PRIOR_SESSION_GAP" if row.get("prior_row_gap") else "NO_PRIOR_SESSION_EVIDENCE"
        return {"eligible": None, "reason_codes": [reason, "PERSISTENCE_UNEVALUABLE"]}
    if _is_r8(prior_row["record"]):
        return {"eligible": True, "reason_codes": ["TWO_CONSECUTIVE_SESSION_R8_PERSISTENCE"]}
    return {"eligible": False, "reason_codes": ["PRIOR_SESSION_NOT_R8_NO_PERSISTENCE"]}


def candidate_r8_volume_return_no_breakdown_quartile(row: Mapping[str, Any]) -> dict[str, Any]:
    """R8 plus elevated relative volume and a positive same-day return.

    Excludes the bottom-quartile market-relative momentum cohort (an existing breakdown
    exclusion signal) rather than inventing a new threshold.
    """
    record = row["record"]
    if not _is_r8(record):
        return {"eligible": False, "reason_codes": ["NOT_R8_SELLING_PRESSURE_EASING"]}
    signals = record.get("signals") or {}
    elevated = signals.get("elevated_volume_vs_cohort_median")
    today_return = signals.get("return_1d")
    bucket = signals.get("momentum_bucket")
    if elevated is None or not isinstance(today_return, (int, float)) or bucket is None:
        return {"eligible": None, "reason_codes": ["REQUIRED_SIGNAL_DIMENSION_UNAVAILABLE"]}
    if bucket == "LOWER_QUARTILE":
        return {"eligible": False, "reason_codes": ["BREAKDOWN_QUARTILE_EXCLUSION"]}
    if elevated is True and today_return > 0:
        return {"eligible": True, "reason_codes": ["ELEVATED_RELATIVE_VOLUME_AND_POSITIVE_RETURN_NO_BREAKDOWN_QUARTILE"]}
    return {"eligible": False, "reason_codes": ["VOLUME_OR_RETURN_CONDITION_NOT_MET"]}


CANDIDATE_POLICIES: dict[str, dict[str, Any]] = {
    "CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET": {
        "evaluator": candidate_r8_momentum_bucket_subset,
        "description": (
            "Strict subset of R8: requires only the market-relative-momentum-upper-half "
            "confirmation arm, dropping R8's weaker today-positive-only arm. Fires before "
            "momentum_20d turns positive, since R8 itself already requires momentum_20d<=0."
        ),
        "fields_used": ["rule_id", "signals.momentum_bucket"],
    },
    "CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE": {
        "evaluator": candidate_r8_two_session_persistence,
        "description": (
            "R8 required on two consecutive reconstructed sessions for the same ticker "
            "before PROBE_ELIGIBLE; a single-day easing blip never qualifies."
        ),
        "fields_used": ["rule_id", "prior_session.rule_id"],
    },
    "CANDIDATE_C_R8_VOLUME_RETURN_NO_BREAKDOWN_QUARTILE": {
        "evaluator": candidate_r8_volume_return_no_breakdown_quartile,
        "description": (
            "R8 plus elevated provider-relative volume and a positive same-day return, "
            "excluding the bottom-quartile market-relative momentum breakdown cohort."
        ),
        "fields_used": ["rule_id", "signals.elevated_volume_vs_cohort_median", "signals.return_1d", "signals.momentum_bucket"],
    },
}


def evaluate_candidate(name: str, row: Mapping[str, Any]) -> dict[str, Any]:
    policy = CANDIDATE_POLICIES.get(name)
    if policy is None:
        raise TacticalReversalProbePolicyEvaluationError(f"UNKNOWN_CANDIDATE_POLICY:{name}")
    return policy["evaluator"](row)


# --------------------------------------------------------------------------------------
# Episode extraction and outcome evaluation.  Episode/trigger identification is strictly
# T0.  Outcome evaluation may use later same-series rows, but only as a research label
# attached after the signal is already decided.
# --------------------------------------------------------------------------------------

def _episodes(rows: Sequence[Mapping[str, Any]], *, predicate: Callable[[Mapping[str, Any]], bool]) -> list[int]:
    """Return the start position of each maximal run where predicate(row) is True."""
    starts: list[int] = []
    previous = False
    for position, row in enumerate(rows):
        current = bool(predicate(row))
        if current and not previous:
            starts.append(position)
        previous = current
    return starts


def _close(row: Mapping[str, Any]) -> float | None:
    value = (row["record"].get("signals") or {}).get("close")
    return value if isinstance(value, (int, float)) else None


def _timing_label(*, lag: int | None, distance_pct: float | None) -> str:
    if lag is None or distance_pct is None:
        return validation.INSUFFICIENT_TEMPORAL_OR_BASIS_EVIDENCE
    if lag <= TIMING_THRESHOLDS["near_low_max_sessions_after_low"] and distance_pct <= TIMING_THRESHOLDS["near_low_max_distance_pct"]:
        return validation.EARLY_SIGNAL_NEAR_LOW
    if lag <= TIMING_THRESHOLDS["acceptable_lag_max_sessions_after_low"] and distance_pct <= TIMING_THRESHOLDS["acceptable_lag_max_distance_pct"]:
        return validation.EARLY_SIGNAL_ACCEPTABLE_LAG
    return validation.SIGNAL_TOO_LATE_FOR_BOTTOM_CAPTURE


def _horizon_metrics(forward_prices: Sequence[tuple[str, float]], *, signal_price: float, n: int) -> dict[str, Any]:
    window = forward_prices[:n]
    if not window:
        return {"status": "INSUFFICIENT_FORWARD_EVIDENCE", "available_sessions": 0}
    lower_low = any(price < signal_price for _, price in window)
    lowest_session, lowest_price = min(window, key=lambda item: (item[1], item[0]))
    highest_session, highest_price = max(window, key=lambda item: (item[1], item[0]))
    first_up = next((index for index, (_, price) in enumerate(window) if price > signal_price), None)
    first_down = next((index for index, (_, price) in enumerate(window) if price < signal_price), None)
    positive_excursion_before_lower_low = first_up is not None and (first_down is None or first_up < first_down)
    return {
        "status": "COMPUTED_RETROSPECTIVE_SAME_SERIES_ONLY" if len(window) == n else "PARTIAL_FORWARD_WINDOW",
        "available_sessions": len(window),
        "lower_low": lower_low,
        "mae_pct": (lowest_price - signal_price) / signal_price,
        "mae_session": lowest_session,
        "mfe_pct": (highest_price - signal_price) / signal_price,
        "mfe_session": highest_session,
        "positive_excursion_before_lower_low": positive_excursion_before_lower_low,
    }


def episode_outcome(rows: Sequence[Mapping[str, Any]], *, signal_position: int) -> dict[str, Any]:
    """Compute research-only outcome labels for one already-decided signal.

    ``rows`` is one ticker's full chronological reconstructed row sequence (gap-aware).
    The reference low is the minimum close observed anywhere in this same reconstructed
    window -- a later-informed research label, never fed back into signal generation.
    """
    prices = [(row["session"], _close(row)) for row in rows]
    valid_prices = [(session, price) for session, price in prices if price is not None]
    signal_row = rows[signal_position]
    signal_price = _close(signal_row)
    if not valid_prices or signal_price is None or signal_price == 0:
        return {"status": "NOT_COMPUTED", "reason_codes": ["COMPARABLE_CLOSE_UNAVAILABLE"]}

    low_session, low_price = min(valid_prices, key=lambda item: (item[1], item[0]))
    low_position = next(index for index, row in enumerate(rows) if row["session"] == low_session)
    distance_from_low_pct = (signal_price - low_price) / low_price if low_price else None
    session_lag_from_low = signal_position - low_position

    forward_prices = [
        (row["session"], _close(row)) for row in rows[signal_position + 1:] if _close(row) is not None
    ]
    horizons = {f"t{n}": _horizon_metrics(forward_prices, signal_price=signal_price, n=n) for n in (5, 10, 20)}

    confirmation = None
    for offset, row in enumerate(rows[signal_position + 1:], start=1):
        rule_id = row["record"].get("rule_id")
        if rule_id in CONFIRMATION_RULE_IDS:
            confirmation = {"session": row["session"], "rule_id": rule_id, "session_lag": offset}
            break

    return {
        "status": "COMPUTED_RETROSPECTIVE_SAME_SERIES_ONLY",
        "price_basis": foundation.PRICE_BASIS,
        "research_series_identity": foundation.RESEARCH_PRICE_SERIES_IDENTITY,
        "signal_session": signal_row["session"],
        "reference_low": {"session": low_session, "close": low_price},
        "distance_from_reference_low_pct": distance_from_low_pct,
        "session_lag_from_reference_low": session_lag_from_low,
        "timing_label": _timing_label(lag=session_lag_from_low, distance_pct=distance_from_low_pct),
        "horizons": horizons,
        "confirmation": confirmation,
    }


def _aggregate_numeric(values: Sequence[float]) -> dict[str, Any]:
    values = [value for value in values if isinstance(value, (int, float))]
    if not values:
        return {"n": 0, "mean": None, "median": None}
    return {"n": len(values), "mean": mean(values), "median": median(values)}


def _aggregate_episodes(outcomes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    computed = [outcome for outcome in outcomes if outcome.get("status") == "COMPUTED_RETROSPECTIVE_SAME_SERIES_ONLY"]
    labels: dict[str, int] = {}
    for outcome in computed:
        labels[outcome["timing_label"]] = labels.get(outcome["timing_label"], 0) + 1
    horizon_summary: dict[str, Any] = {}
    for horizon in ("t5", "t10", "t20"):
        entries = [outcome["horizons"][horizon] for outcome in computed]
        available = [entry for entry in entries if entry.get("status") != "INSUFFICIENT_FORWARD_EVIDENCE"]
        horizon_summary[horizon] = {
            "evaluable_n": len(available),
            "insufficient_forward_evidence_n": len(entries) - len(available),
            "lower_low_rate": (sum(1 for entry in available if entry["lower_low"]) / len(available)) if available else None,
            "mae_pct": _aggregate_numeric([entry["mae_pct"] for entry in available]),
            "mfe_pct": _aggregate_numeric([entry["mfe_pct"] for entry in available]),
            "positive_excursion_before_lower_low_rate": (
                sum(1 for entry in available if entry["positive_excursion_before_lower_low"]) / len(available)
            ) if available else None,
        }
    confirmations = [outcome["confirmation"] for outcome in computed]
    reached = [item for item in confirmations if item is not None]
    by_rule: dict[str, int] = {}
    for item in reached:
        by_rule[item["rule_id"]] = by_rule.get(item["rule_id"], 0) + 1
    return {
        "episode_count": len(outcomes),
        "computed_count": len(computed),
        "not_computed_count": len(outcomes) - len(computed),
        "timing_label_distribution": labels,
        "distance_from_reference_low_pct": _aggregate_numeric([outcome["distance_from_reference_low_pct"] for outcome in computed]),
        "session_lag_from_reference_low": _aggregate_numeric([outcome["session_lag_from_reference_low"] for outcome in computed]),
        "horizons": horizon_summary,
        "confirmation_reached_rate": (len(reached) / len(computed)) if computed else None,
        "confirmation_reached_by_rule": by_rule,
        "confirmation_session_lag_when_reached": _aggregate_numeric([item["session_lag"] for item in reached]),
    }


def evaluate_cohort(series: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """Extract control (R6, R8) and candidate probe episodes and their outcomes."""
    control_r8: dict[str, list[dict[str, Any]]] = {}
    control_r6: dict[str, list[dict[str, Any]]] = {}
    candidate_signals: dict[str, dict[str, list[dict[str, Any]]]] = {name: {} for name in CANDIDATE_POLICIES}
    candidate_unevaluable: dict[str, int] = {name: 0 for name in CANDIDATE_POLICIES}

    for ticker, rows in series.items():
        r8_starts = _episodes(rows, predicate=lambda row: _is_r8(row["record"]))
        r6_starts = _episodes(rows, predicate=lambda row: row["record"].get("rule_id") == R6_RULE_ID)
        control_r8[ticker] = [
            {"position": position, "outcome": episode_outcome(rows, signal_position=position)}
            for position in r8_starts
        ]
        control_r6[ticker] = [
            {"position": position, "outcome": episode_outcome(rows, signal_position=position)}
            for position in r6_starts
        ]
        for name in CANDIDATE_POLICIES:
            fired_positions: list[int] = []
            for position, row in enumerate(rows):
                verdict = evaluate_candidate(name, row)
                if verdict["eligible"] is None:
                    candidate_unevaluable[name] += 1
                elif verdict["eligible"] is True:
                    fired_positions.append(position)
            candidate_signals[name][ticker] = [
                {"position": position, "outcome": episode_outcome(rows, signal_position=position)}
                for position in fired_positions
            ]

    def flatten(by_ticker: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
        return [outcome["outcome"] for episodes in by_ticker.values() for outcome in episodes]

    return {
        "control": {
            "r8_selling_pressure_easing": {
                "episodes_by_ticker": control_r8,
                "aggregate": _aggregate_episodes(flatten(control_r8)),
            },
            "r6_early_reversal_candidate": {
                "episodes_by_ticker": control_r6,
                "aggregate": _aggregate_episodes(flatten(control_r6)),
            },
        },
        "candidates": {
            name: {
                "episodes_by_ticker": candidate_signals[name],
                "unevaluable_row_count": candidate_unevaluable[name],
                "aggregate": _aggregate_episodes(flatten(candidate_signals[name])),
            }
            for name in CANDIDATE_POLICIES
        },
    }


# --------------------------------------------------------------------------------------
# SSI / PNJ / PAN interpretability case studies (not the basis for policy selection).
# --------------------------------------------------------------------------------------

def case_study_ticker(series: Mapping[str, Sequence[Mapping[str, Any]]], *, ticker: str) -> dict[str, Any]:
    rows = series.get(ticker)
    if not rows:
        return {"status": "NOT_RECONSTRUCTED", "ticker": ticker}
    per_row = []
    for position, row in enumerate(rows):
        record = row["record"]
        verdicts = {name: evaluate_candidate(name, row) for name in CANDIDATE_POLICIES}
        per_row.append({
            "session": row["session"],
            "entry_state": record.get("entry_state"),
            "entry_action": record.get("entry_action"),
            "rule_id": record.get("rule_id"),
            "close": _close(row),
            "candidate_verdicts": verdicts,
        })
    return {"status": "RECONSTRUCTED", "ticker": ticker, "rows": per_row}


def pan_control_case_study(*, session_2026_09_08: Mapping[str, Any] | None, session_2026_09_09: Mapping[str, Any], session_2026_09_10: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the shadow candidates to PAN's exact retained control transition.

    Sourced entirely from already-retained real daily tactical artifacts (not
    reconstructed), preserving the existing HISTORICAL_TACTICAL_REPLAY_EVIDENCE_FOUNDATION_V1
    PAN control unchanged. 2026-09-08's retained record is optional; when absent the
    two-session-persistence candidate is marked unevaluable rather than defaulted.
    """
    row_09 = {
        "record": session_2026_09_09,
        "prior_row": {"record": session_2026_09_08} if session_2026_09_08 is not None else None,
        "prior_row_gap": session_2026_09_08 is None,
    }
    verdicts_09 = {name: evaluate_candidate(name, row_09) for name in CANDIDATE_POLICIES}
    return {
        "transition": {
            "from_session": "2026-09-09",
            "from_state": session_2026_09_09.get("entry_state"),
            "from_action": session_2026_09_09.get("entry_action"),
            "from_rule_id": session_2026_09_09.get("rule_id"),
            "to_session": "2026-09-10",
            "to_state": session_2026_09_10.get("entry_state"),
            "to_action": session_2026_09_10.get("entry_action"),
            "to_rule_id": session_2026_09_10.get("rule_id"),
        },
        "session_2026_09_08_prior_state": (
            {"entry_state": session_2026_09_08.get("entry_state"), "rule_id": session_2026_09_08.get("rule_id")}
            if session_2026_09_08 is not None else None
        ),
        "candidate_verdicts_on_2026_09_09": verdicts_09,
        "deterioration_2026_09_10": {
            "entry_state": session_2026_09_10.get("entry_state"),
            "rule_id": session_2026_09_10.get("rule_id"),
            "close_change_pct": (
                (session_2026_09_10.get("signals", {}).get("close") - session_2026_09_09.get("signals", {}).get("close"))
                / session_2026_09_09.get("signals", {}).get("close")
                if isinstance(session_2026_09_09.get("signals", {}).get("close"), (int, float))
                and isinstance(session_2026_09_10.get("signals", {}).get("close"), (int, float))
                and session_2026_09_09.get("signals", {}).get("close")
                else None
            ),
        },
    }


# --------------------------------------------------------------------------------------
# Decision.
# --------------------------------------------------------------------------------------

MIN_CANDIDATE_COMPUTED_EPISODES = 30
MIN_CONFIRMATION_LAG_MEDIAN_SESSIONS = 2
MIN_FALSE_START_RATE_IMPROVEMENT_VS_FULL_R8 = 0.05
MIN_MAE_T10_IMPROVEMENT_VS_FULL_R8 = 0.005


def decide(
    *, cohort_summary: Mapping[str, Any], cohort_eval: Mapping[str, Any],
    pan_case_study: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply named, individually-reported criteria rather than one blended score.

    INSUFFICIENT_COHORT_EVIDENCE if the cohort is too small to compare policies at all.
    A candidate is EVIDENCE_SUPPORTS_SHADOW_PROBE_POLICY-eligible only if it (a) fires
    with a materially earlier median session-lag to eventual R6/R3/R2 confirmation than
    simply waiting for R6, (b) shows a materially lower T10 false-start (lower-low) rate
    than the full R8 population it subsets -- proving the extra condition actually filters
    out weaker cases rather than merely inheriting R8's own baseline risk, (c) shows a
    materially better T10 MAE than that same full R8 baseline, and (d) does not itself
    mark the retained PAN 2026-09-09 control episode -- an explicit, real false start --
    as PROBE_ELIGIBLE. Each criterion is reported per candidate; nothing is blended into
    a single score. KEEP_CURRENT_R6_POLICY if no candidate clears all four.
    """
    if (
        cohort_summary["tickers_with_any_reconstruction"] < MIN_COHORT_TICKERS
        or cohort_summary["control_r8_episode_count"] < MIN_COHORT_R8_EPISODES
    ):
        return {
            "decision": INSUFFICIENT_COHORT_EVIDENCE,
            "reason_codes": ["COHORT_TICKER_OR_R8_EPISODE_COUNT_BELOW_MINIMUM"],
        }

    control_r8_agg = cohort_eval["control"]["r8_selling_pressure_easing"]["aggregate"]
    control_r8_t10 = control_r8_agg["horizons"]["t10"]
    control_r8_lower_low_rate = control_r8_t10.get("lower_low_rate")
    control_r8_mae_mean = control_r8_t10["mae_pct"].get("mean")
    control_r6_agg = cohort_eval["control"]["r6_early_reversal_candidate"]["aggregate"]

    pan_verdicts = (pan_case_study or {}).get("candidate_verdicts_on_2026_09_09") or {}

    per_candidate: dict[str, Any] = {}
    supported: list[str] = []
    for name, result in cohort_eval["candidates"].items():
        agg = result["aggregate"]
        candidate_t10 = agg["horizons"]["t10"]
        candidate_lower_low_rate = candidate_t10.get("lower_low_rate")
        candidate_mae_mean = candidate_t10["mae_pct"].get("mean")
        confirmation_lag = agg["confirmation_session_lag_when_reached"]

        criteria = {
            "sufficient_sample": agg["computed_count"] >= MIN_CANDIDATE_COMPUTED_EPISODES,
            "materially_earlier_than_waiting_for_r6": (
                confirmation_lag["n"] >= MIN_CANDIDATE_COMPUTED_EPISODES
                and (confirmation_lag["median"] or 0) >= MIN_CONFIRMATION_LAG_MEDIAN_SESSIONS
            ),
            "false_start_rate_materially_below_full_r8_baseline": (
                candidate_lower_low_rate is not None and control_r8_lower_low_rate is not None
                and (control_r8_lower_low_rate - candidate_lower_low_rate) >= MIN_FALSE_START_RATE_IMPROVEMENT_VS_FULL_R8
            ),
            "mae_t10_materially_better_than_full_r8_baseline": (
                candidate_mae_mean is not None and control_r8_mae_mean is not None
                and (candidate_mae_mean - control_r8_mae_mean) >= MIN_MAE_T10_IMPROVEMENT_VS_FULL_R8
            ),
            "does_not_flag_pan_control_episode_eligible": pan_verdicts.get(name, {}).get("eligible") is not True,
        }
        per_candidate[name] = {
            "criteria": criteria,
            "all_criteria_met": all(criteria.values()),
            "t10_lower_low_rate": candidate_lower_low_rate,
            "t10_mae_pct_mean": candidate_mae_mean,
            "confirmation_session_lag_when_reached": confirmation_lag,
            "pan_control_episode_verdict": pan_verdicts.get(name),
        }
        if per_candidate[name]["all_criteria_met"]:
            supported.append(name)

    evaluation = {
        "control_r8_full_population_baseline": {
            "t10_lower_low_rate": control_r8_lower_low_rate,
            "t10_mae_pct_mean": control_r8_mae_mean,
        },
        "control_r6_computed_episode_count": control_r6_agg["computed_count"],
        "per_candidate": per_candidate,
        "thresholds": {
            "min_candidate_computed_episodes": MIN_CANDIDATE_COMPUTED_EPISODES,
            "min_confirmation_lag_median_sessions": MIN_CONFIRMATION_LAG_MEDIAN_SESSIONS,
            "min_false_start_rate_improvement_vs_full_r8": MIN_FALSE_START_RATE_IMPROVEMENT_VS_FULL_R8,
            "min_mae_t10_improvement_vs_full_r8": MIN_MAE_T10_IMPROVEMENT_VS_FULL_R8,
        },
    }

    if supported:
        return {
            "decision": EVIDENCE_SUPPORTS_SHADOW_PROBE_POLICY,
            "reason_codes": ["CANDIDATE_CLEARED_ALL_NAMED_TIMING_FALSE_START_AND_PAN_CONTROL_CRITERIA"],
            "supported_candidates": supported,
            "evaluation": evaluation,
        }
    return {
        "decision": KEEP_CURRENT_R6_POLICY,
        "reason_codes": ["NO_CANDIDATE_CLEARED_ALL_NAMED_TIMING_FALSE_START_AND_PAN_CONTROL_CRITERIA"],
        "evaluation": evaluation,
    }


# --------------------------------------------------------------------------------------
# Artifact assembly.
# --------------------------------------------------------------------------------------

def _cohort_summary(*, cohort: Mapping[str, Any], series: Mapping[str, Sequence[Mapping[str, Any]]], sessions: Sequence[str], cohort_eval: Mapping[str, Any]) -> dict[str, Any]:
    reconstructions = cohort["reconstructions"]
    total_candidate_signals = sum(len(replay["records"]) for replay in reconstructions.values())
    r0_count = sum(
        1
        for replay in reconstructions.values()
        for record in replay["records"].values()
        if record.get("rule_id") == "R0_TECHNICAL_FEATURES_UNAVAILABLE"
    )
    return {
        "sessions_requested": len(sessions),
        "sessions_reconstructed": len(reconstructions),
        "session_exclusions": cohort["session_exclusions"],
        "tickers_with_any_reconstruction": len(series),
        "total_candidate_signal_count": total_candidate_signals,
        "technical_features_unavailable_count": r0_count,
        "control_r8_episode_count": cohort_eval["control"]["r8_selling_pressure_easing"]["aggregate"]["episode_count"],
        "control_r6_episode_count": cohort_eval["control"]["r6_early_reversal_candidate"]["aggregate"]["episode_count"],
        "candidate_episode_counts": {
            name: result["aggregate"]["episode_count"] for name, result in cohort_eval["candidates"].items()
        },
        "candidate_unevaluable_row_counts": {
            name: result["unevaluable_row_count"] for name, result in cohort_eval["candidates"].items()
        },
        "reconstruction_qualification": foundation.RETROSPECTIVE_RESEARCH_RECONSTRUCTION,
        "basis": {
            "observed_price_basis": foundation.PRICE_BASIS,
            "research_series_identity": foundation.RESEARCH_PRICE_SERIES_IDENTITY,
            "historical_pit": "NOT_PROMOTED",
        },
    }


def build_artifact(
    *, cohort: Mapping[str, Any], sessions: Sequence[str],
    pan_case_study: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose the full research artifact from an already-reconstructed cohort.

    ``cohort`` is the return value of :func:`reconstruct_cohort_sessions`. This function
    performs no further reconstruction or I/O.
    """
    series = ticker_series(cohort["reconstructions"], all_sessions=sessions)
    cohort_eval = evaluate_cohort(series)
    summary = _cohort_summary(cohort=cohort, series=series, sessions=sessions, cohort_eval=cohort_eval)
    decision = decide(cohort_summary=summary, cohort_eval=cohort_eval, pan_case_study=pan_case_study)

    case_studies = {
        "SSI": case_study_ticker(series, ticker="SSI"),
        "PNJ": case_study_ticker(series, ticker="PNJ"),
        "PAN": pan_case_study if pan_case_study is not None else {"status": "NOT_AVAILABLE", "reason_codes": ["PAN_RETAINED_EVIDENCE_NOT_SUPPLIED"]},
    }

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "candidate_policy_definitions": {
            name: {"description": policy["description"], "fields_used": policy["fields_used"]}
            for name, policy in CANDIDATE_POLICIES.items()
        },
        "timing_thresholds_reused_reporting_only": dict(TIMING_THRESHOLDS),
        "cohort_summary": summary,
        "control": cohort_eval["control"],
        "candidates": cohort_eval["candidates"],
        "case_studies": case_studies,
        "decision": decision,
        "authority_boundary": {
            "classifier_policy_changed": False,
            "daily_modified": False,
            "daily_brief_binding_modified": False,
            "integrated_decision_modified": False,
            "portfolio_modified": False,
            "raw_as_traded": "NOT_PROMOTED",
            "historical_pit": "NOT_PROMOTED",
            "price_basis_authority": "UNCHANGED",
            "provider_or_network_calls": False,
            "database_written": False,
            "probability_or_recommendation": "NOT_EMITTED",
            "sizing_formula_introduced": False,
            "classifier_v2_queued": False,
        },
    }
    artifact["artifact_sha256"] = _digest(artifact)
    artifact["artifact_identity"] = "tactical_reversal_probe_policy_counterfactual_evaluation:" + artifact["artifact_sha256"]
    return artifact


def build_from_runtime(
    *, runtime_root: Path, start: str, end: str, pan_case_study: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read local SQLite once per session, reconstruct the cohort, then build the artifact."""
    sessions = available_sessions(runtime_root, start=start, end=end)
    cohort = reconstruct_cohort_sessions(runtime_root, sessions=sessions)
    return build_artifact(cohort=cohort, sessions=sessions, pan_case_study=pan_case_study)
