"""Prospective forward-outcome bridge for integrated_investment_decision_product/v1 records.

Section 9/10/11 scope note (recorded in full in docs/DECISIONS.md): the existing durable T0 case
store (``durable_prospective_research_case_store.py`` + ``prospective_case_admission_policy.py``)
is a real, working, fail-closed pipeline -- but its admission gate is contractually locked to the
older ``investment_decision_workspace_projection/v1`` research_stance vocabulary
(``ADMISSIBLE = {"INITIATE_RESEARCH_CANDIDATE", ...}``), a disjoint 6-value vocabulary from
``integrated_investment_decision_product/v1``'s 9-value ``research_action_posture``. Rewiring that
admission policy to also admit integrated-decision-sourced cases is real, separate, higher-blast-
radius work on a hand-verified fail-closed gate, out of proportion for this milestone.

This module instead observes that every session's ``integrated_investment_decision_product``
artifact is ALREADY a durable, immutable, content-addressed, session-keyed retention of
``decision_identity``/``research_action_posture``/trigger/invalidation for every ticker (Section 9's
core ask) -- no separate admission/store step is needed for retention itself. What is genuinely new
here is the FORWARD-OUTCOME walk: given a past decision and the current session's retained P3F9B
multi-session OHLC observation history (which already carries up to ~250 prior trading sessions'
closes per ticker), compute session-counted forward close returns using the SAME governed-chain
counting and PENDING/price-basis discipline as ``prospective_decision_outcome_measurement.py`` --
reusing its horizon/taxonomy machinery directly rather than duplicating it, per Section 9/12's
"do not create a second independent backtest engine" instruction.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from prospective_decision_outcome_measurement import FIELD_NOT_RETAINED, PENDING, classify_feedback_taxonomy

CONTRACT_VERSION = "integrated_decision_prospective_feedback/v2"
# The close-return bridge is deliberately session-counted.  The prospective
# diagnostics layer consumes the exact same mapping rather than maintaining a
# second horizon vocabulary.
FORWARD_HORIZONS = {
    "forward_close_return_1": 1,
    "forward_close_return_3": 3,
    "forward_close_return_5": 5,
    "forward_close_return_10": 10,
    "forward_close_return_20": 20,
}
PENDING_FUTURE_SESSIONS = "PENDING_FUTURE_SESSIONS"
SESSION_NOT_RETAINED = "T0_SESSION_NOT_IN_GOVERNED_CHAIN"
PRICE_NOT_RETAINED = "CLOSE_PRICE_NOT_RETAINED"
PRICE_BASIS_INCOMPATIBLE = "PRICE_BASIS_INCOMPATIBLE"
MATURE = "MATURE"


def _read_json(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def governed_session_chain(root: Path) -> list[str]:
    """Sorted, deduplicated set of sessions with a materialized daily research session operation.

    Same directory stocklookup.py:_previous() already scans -- deliberately not a different
    definition of "governed session" than what next_session_decision_brief's previous_qualified_
    session already reflects in production.
    """
    sessions: set[str] = set()
    base = root / "operations-review" / "daily-research-session-operations-v1"
    if not base.is_dir():
        return []
    for manifest_path in base.glob("*/*/run_manifest.json"):
        try:
            manifest = _read_json(manifest_path)
        except (json.JSONDecodeError, OSError):
            continue
        session = manifest.get("market_session")
        if isinstance(session, str) and session:
            sessions.add(session)
    return sorted(sessions)


def _price_observations(p3f9b_snapshot: Mapping[str, Any] | None, ticker: str) -> dict[str, Mapping[str, Any]]:
    if not p3f9b_snapshot:
        return {}
    record = (p3f9b_snapshot.get("records") or {}).get(ticker) or {}
    return {row["session"]: row for row in (record.get("observations") or []) if isinstance(row, Mapping) and isinstance(row.get("session"), str)}


def retained_session_price_observations(
    snapshots_by_session: Mapping[str, Mapping[str, Any]] | None, ticker: str,
) -> dict[str, Mapping[str, Any]]:
    """Collect only an exact observation from each already-retained session snapshot.

    P3F9B materializations are intentionally exact-session artifacts; they do
    not promise that every later snapshot retains a complete history.  This
    helper therefore joins their *same-session* observations under their
    explicit resolved-session identities.  It is not a historical series
    reconstruction and it never fills a missing session from another date.
    """
    if not snapshots_by_session:
        return {}
    rows: dict[str, Mapping[str, Any]] = {}
    for expected_session, snapshot in snapshots_by_session.items():
        if not isinstance(expected_session, str) or not isinstance(snapshot, Mapping):
            continue
        if snapshot.get("resolved_completed_session") != expected_session:
            continue
        record = (snapshot.get("records") or {}).get(ticker) or {}
        matches = [
            row for row in (record.get("observations") or [])
            if isinstance(row, Mapping) and row.get("session") == expected_session
        ]
        if len(matches) != 1:
            continue
        row = dict(matches[0])
        row["retained_snapshot_identity"] = snapshot.get("snapshot_identity")
        row["retained_snapshot_session"] = expected_session
        rows[expected_session] = row
    return rows


def _series_lineage(start: Mapping[str, Any] | None, end: Mapping[str, Any] | None) -> dict[str, Any]:
    """Retain endpoint source facts; compatibility stays fail-closed below."""
    def endpoint(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "snapshot_identity": row.get("retained_snapshot_identity"),
            "provider": row.get("provider"), "dataset": row.get("dataset"),
            "price_basis": row.get("price_basis"),
            "transformation_identity": row.get("transformation_identity"),
            "qualification": row.get("qualification"),
        }
    return {"start": endpoint(start), "end": endpoint(end)}


def _compatible_close_series(start: Mapping[str, Any], end: Mapping[str, Any]) -> bool:
    """Use the existing normalized price-basis contract without silent splicing.

    A provider may change only when the retained observations declare the same
    normalized price basis *and* transformation.  Endpoint providers remain in
    the output so a consumer cannot mistake that governed failover for a
    single-provider raw-as-traded series.
    """
    if not (start.get("price_basis") and start.get("price_basis") == end.get("price_basis")):
        return False
    start_transform, end_transform = start.get("transformation_identity"), end.get("transformation_identity")
    # Older retained/test close records predate transformation identity.  They
    # retain only the existing price-basis compatibility contract.  Once either
    # endpoint declares a transform, both must declare the same one.
    return not (start_transform or end_transform) or bool(start_transform and start_transform == end_transform)


def _forward_horizon(*, as_of_session: str, horizon_sessions: int, chain: Sequence[str], observations: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    start = observations.get(as_of_session)
    base = {
        "required_completed_future_sessions": horizon_sessions, "status": None,
        "start_session": as_of_session, "end_session": None, "future_session": None,
        "start_price": start.get("close") if start else None, "end_price": None,
        "return": None, "price_basis": start.get("price_basis") if start else None,
        "series_identity": start.get("retained_snapshot_identity") if start else None,
        "series_fitness": "START_CLOSE_NOT_RETAINED" if start is None else "PENDING_FUTURE_SESSION",
        "series_lineage": _series_lineage(start, None),
    }
    if as_of_session not in chain:
        return {**base, "status": SESSION_NOT_RETAINED}
    index = chain.index(as_of_session)
    target_index = index + horizon_sessions
    if target_index >= len(chain):
        return {**base, "status": PENDING}
    future_session = chain[target_index]
    t0_row, future_row = start, observations.get(future_session)
    if t0_row is None or future_row is None:
        return {
            **base, "status": PRICE_NOT_RETAINED, "future_session": future_session,
            "end_session": future_session, "series_fitness": "EXACT_CLOSE_MISSING",
            "series_lineage": _series_lineage(t0_row, future_row),
        }
    t0_close, future_close = t0_row.get("close"), future_row.get("close")
    if not isinstance(t0_close, (int, float)) or not isinstance(future_close, (int, float)) or t0_close == 0:
        return {
            **base, "status": PRICE_NOT_RETAINED, "future_session": future_session,
            "end_session": future_session, "series_fitness": "CLOSE_VALUE_INVALID",
            "series_lineage": _series_lineage(t0_row, future_row),
        }
    if not _compatible_close_series(t0_row, future_row):
        return {
            **base, "status": PRICE_BASIS_INCOMPATIBLE, "future_session": future_session,
            "end_session": future_session, "end_price": future_close,
            "series_fitness": "INCOMPATIBLE_PRICE_SERIES",
            "series_lineage": _series_lineage(t0_row, future_row),
        }
    return {
        **base, "status": MATURE, "future_session": future_session, "end_session": future_session,
        "end_price": future_close, "return": future_close / t0_close - 1,
        "price_basis": t0_row.get("price_basis"), "series_fitness": "COMPATIBLE_RETAINED_CLOSE_SERIES",
        "series_lineage": _series_lineage(t0_row, future_row),
    }


def _close_excursion(*, as_of_session: str, horizon: Mapping[str, Any], chain: Sequence[str], observations: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Close-only excursion, explicitly not intraday MFE/MAE."""
    if horizon.get("status") != MATURE:
        return {
            "status": horizon.get("status"), "CLOSE_MFE": None, "CLOSE_MAE": None,
            "semantics": "CLOSE_ONLY_NOT_INTRADAY_MFE_MAE",
        }
    start = observations.get(as_of_session)
    if start is None or as_of_session not in chain:
        return {"status": PRICE_NOT_RETAINED, "CLOSE_MFE": None, "CLOSE_MAE": None, "semantics": "CLOSE_ONLY_NOT_INTRADAY_MFE_MAE"}
    index = chain.index(as_of_session)
    returns: list[float] = []
    for session in chain[index + 1:index + horizon["required_completed_future_sessions"] + 1]:
        row = observations.get(session)
        if row is None or not _compatible_close_series(start, row) or not isinstance(row.get("close"), (int, float)):
            return {"status": PRICE_BASIS_INCOMPATIBLE if row else PRICE_NOT_RETAINED, "CLOSE_MFE": None, "CLOSE_MAE": None, "semantics": "CLOSE_ONLY_NOT_INTRADAY_MFE_MAE"}
        returns.append(row["close"] / start["close"] - 1)
    return {"status": MATURE, "CLOSE_MFE": max(returns), "CLOSE_MAE": min(returns), "semantics": "CLOSE_ONLY_NOT_INTRADAY_MFE_MAE"}


def evaluate_decision_forward_outcome(*, decision_record: Mapping[str, Any], p3f9b_snapshot: Mapping[str, Any] | None,
                                      governed_chain: Sequence[str],
                                      retained_session_snapshots: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Forward close-return + close-path favorable/adverse excursion for one integrated decision.

    Names its close-path fields max_favorable_close_excursion/max_adverse_close_excursion (never
    "MFE"/"MAE") because no qualified high/low basis backs this -- close-only path statistics, not
    true intraday MFE/MAE, matching Section 10's explicit naming instruction.
    """
    ticker, as_of_session = decision_record["ticker"], decision_record["as_of_session"]
    observations = retained_session_price_observations(retained_session_snapshots, ticker)
    if not observations:
        observations = _price_observations(p3f9b_snapshot, ticker)
    horizons = {name: _forward_horizon(as_of_session=as_of_session, horizon_sessions=n, chain=governed_chain, observations=observations) for name, n in FORWARD_HORIZONS.items()}
    max_n = max(FORWARD_HORIZONS.values())
    index = governed_chain.index(as_of_session) if as_of_session in governed_chain else None
    t0_row = observations.get(as_of_session)
    close_path_returns: list[float] = []
    if index is not None and t0_row and isinstance(t0_row.get("close"), (int, float)) and t0_row["close"]:
        for step in range(1, max_n + 1):
            step_index = index + step
            if step_index >= len(governed_chain):
                break
            step_row = observations.get(governed_chain[step_index])
            if step_row and isinstance(step_row.get("close"), (int, float)) and step_row.get("price_basis") == t0_row.get("price_basis"):
                close_path_returns.append(step_row["close"] / t0_row["close"] - 1)
    if index is None:
        close_path_status = SESSION_NOT_RETAINED
    elif len(close_path_returns) >= max_n:
        close_path_status = MATURE
    elif close_path_returns:
        close_path_status = "PARTIAL_WINDOW_STILL_ACCUMULATING"
    else:
        close_path_status = PENDING
    close_path = {
        "status": close_path_status,
        "sessions_observed": len(close_path_returns),
        "max_favorable_close_excursion": max(close_path_returns) if close_path_returns else None,
        "max_adverse_close_excursion": min(close_path_returns) if close_path_returns else None,
        "semantics": "CLOSE_ONLY_PATH_STATISTIC_NOT_TRUE_INTRADAY_MFE_MAE",
    }
    close_path_by_horizon = {
        name.replace("forward_close_return_", "close_excursion_"): _close_excursion(
            as_of_session=as_of_session, horizon=horizon, chain=governed_chain, observations=observations,
        )
        for name, horizon in horizons.items() if horizon["required_completed_future_sessions"] in {5, 10, 20}
    }
    return {
        "ticker": ticker, "as_of_session": as_of_session, "decision_identity": decision_record.get("decision_identity"),
        "horizons": horizons, "close_path": close_path, "close_path_by_horizon": close_path_by_horizon,
        "authority_boundary": {
            "close_only_excursions_not_intraday_mfe_mae": True,
            "raw_as_traded_or_pit_not_claimed": True,
            "provider_endpoint_lineage_retained": True,
        },
    }


def classify_decision_feedback(*, decision_record: Mapping[str, Any], forward_outcome: Mapping[str, Any]) -> dict[str, Any]:
    """Reuses prospective_decision_outcome_measurement.classify_feedback_taxonomy verbatim (same
    engine, same labels) via a minimal outcome-shaped shim -- this bridge tracks no confirmation/
    invalidation boundary events (that requires the durable case store), so those two fields are
    always NOT_EVALUABLE here; the taxonomy still degrades gracefully on that basis."""
    t5 = forward_outcome["horizons"]["forward_close_return_5"]
    shim = {
        "research_action_posture_at_t0": decision_record.get("research_action_posture", FIELD_NOT_RETAINED),
        "research_stance_at_t0": FIELD_NOT_RETAINED,
        "horizons": {"T5": {"status": t5["status"], "return": t5["return"]}},
        "confirmation": {"status": "NOT_EVALUABLE"},
        "invalidation": {"status": "NOT_EVALUABLE"},
    }
    return classify_feedback_taxonomy(shim)


def build_prospective_feedback_status(*, current_records: Mapping[str, Mapping[str, Any]], p3f9b_snapshot: Mapping[str, Any] | None,
                                       governed_chain: Sequence[str], evaluate_watchlist_only: Sequence[str] | None = None) -> dict[str, Any]:
    """Section 9-11 top-level status for the daily brief: real forward-outcome/taxonomy evidence
    where the governed chain has matured far enough, explicit PENDING_FUTURE_SESSIONS otherwise --
    never a fabricated horizon or a win-rate/probability claim."""
    if not current_records:
        return {"availability": "UNAVAILABLE", "reason_codes": ["NO_CURRENT_INTEGRATED_DECISION_RECORDS"], "decision_retention": {}, "outcome_horizons": {}, "feedback_taxonomy_distribution": {}}
    scope_tickers = list(evaluate_watchlist_only) if evaluate_watchlist_only is not None else sorted(current_records)
    horizon_status_counts = {name: {} for name in FORWARD_HORIZONS}
    taxonomy_counts: dict[str, int] = {}
    per_ticker: dict[str, Any] = {}
    for ticker in scope_tickers:
        record = current_records.get(ticker)
        if record is None:
            continue
        outcome = evaluate_decision_forward_outcome(decision_record=record, p3f9b_snapshot=p3f9b_snapshot, governed_chain=governed_chain)
        taxonomy = classify_decision_feedback(decision_record=record, forward_outcome=outcome)
        for name in FORWARD_HORIZONS:
            status = outcome["horizons"][name]["status"]
            horizon_status_counts[name][status] = horizon_status_counts[name].get(status, 0) + 1
        taxonomy_counts[taxonomy["label"]] = taxonomy_counts.get(taxonomy["label"], 0) + 1
        per_ticker[ticker] = {"forward_outcome": outcome, "feedback_taxonomy": taxonomy}
    return {
        "availability": "AVAILABLE",
        "decision_retention": {
            "universe_decisions_retained": len(current_records), "retention_mechanism": "SESSION_SCOPED_IMMUTABLE_INTEGRATED_DECISION_ARTIFACT_PATH",
            "every_decision_carries": ["decision_identity", "ticker", "as_of_session", "research_action_posture", "trigger", "invalidation", "source_identities", "policy_version"],
        },
        "governed_chain_length": len(governed_chain),
        "outcome_horizons": {name: {"status_counts": counts, "status": "ACTIVE" if any(k == MATURE for k in counts) else PENDING_FUTURE_SESSIONS} for name, counts in horizon_status_counts.items()},
        "feedback_taxonomy_distribution": dict(sorted(taxonomy_counts.items())),
        "records": per_ticker,
        "authority_boundary": {
            "research_evaluation_labels_not_causal_proof": True, "no_automatic_policy_retuning": True,
            "no_probability_of_success": True, "close_path_is_not_intraday_mfe_mae": True,
            "no_calibration_insufficient_sample": True,
        },
    }
