"""Compact presentation projection for two already-governed research contracts:

- ``multi_session_signal_velocity/v1.2`` (multi-session technical-evidence trajectory)
- ``flow_price_divergence_shadow/v1`` (qualified foreign VALUE flow vs. price/structure)

This module computes nothing new. It whitelists and reshapes fields already present
on a retained record for one product surface: a compact "Signal Velocity" /
"Flow-Price Divergence" pair attached to the existing Dashboard ticker decision card.
A ticker with no retained record for the exact requested session is presented with an
explicit, honest unavailable state -- never a fabricated or interpolated value.

Flow-Price cohort membership is a distinct concept from data availability: the
current-foreign-flow research cohort (``owner_research_focus.json``'s
``broader_watchlist``) is the pre-flow-configured set of tickers the DNSE VALUE-flow
acquisition is scoped to. A ticker can be a cohort member and still show
``FLOW_UNAVAILABLE`` (its current-session flow has not yet been acquired/retained); a
ticker outside the cohort is never presented as if the flow system failed for it.
"""
from __future__ import annotations

from typing import Any, Mapping

SIGNAL_VELOCITY_CONTRACT_VERSION = "multi_session_signal_velocity/v1.2"
FLOW_PRICE_CONTRACT_VERSION = "flow_price_divergence_shadow/v1"

VELOCITY_LIMITATIONS = (
    "RETAINED_EVIDENCE_TRAJECTORY_NOT_A_PRICE_FORECAST",
    "NO_SCORE_OR_PROBABILITY",
    "CATEGORICAL_ORDINAL_RANKS_NOT_CARDINAL_ACCELERATION",
)
FLOW_PRICE_DEFAULT_LIMITATIONS = (
    "QUALIFIED_FOREIGN_VALUE_ONLY",
    "NO_FLOW_NORMALIZATION",
    "NO_CAUSAL_OR_INTENT_INTERPRETATION",
    "NO_FORWARD_OUTCOME_CLAIM",
)

IN_COHORT = "IN_CURRENT_FLOW_RESEARCH_COHORT"
OUTSIDE_COHORT = "OUTSIDE_CURRENT_FLOW_RESEARCH_COHORT"


def cohort_tickers_from_owner_focus(owner_focus: Mapping[str, Any] | None) -> frozenset[str]:
    """The configured current-foreign-flow research cohort (never a live-observed set)."""
    if not isinstance(owner_focus, Mapping):
        return frozenset()
    return frozenset(str(ticker).upper() for ticker in (owner_focus.get("broader_watchlist") or []))


def _velocity_unavailable(reason_code: str) -> dict[str, Any]:
    return {
        "contract_version": SIGNAL_VELOCITY_CONTRACT_VERSION,
        "source_artifact_identity": None,
        "source_record_session": None,
        "overall_transition_state": "INSUFFICIENT_EVIDENCE",
        "evidence_quality": "INSUFFICIENT_RETAINED_EVIDENCE",
        "valid_observation_count": 0,
        "retained_session_span": None,
        "continuity_state": None,
        "latest_transition": None,
        "persistence": None,
        "acceleration_state": None,
        "independent_supporting_axes": [],
        "contradicting_axes": [],
        "limitations": list(VELOCITY_LIMITATIONS),
        "reason_code": reason_code,
        "is_actionable": False,
    }


def signal_velocity_view(*, ticker: str, artifact: Mapping[str, Any] | None, as_of_session: str) -> dict[str, Any]:
    """One ticker's compact, presentation-safe Signal Velocity view for ``as_of_session``.

    Only ever reads a record whose own ``session`` equals ``as_of_session`` exactly --
    never the ticker's most recent record from an earlier session (that would silently
    misrepresent an older transition as current).
    """
    if not isinstance(artifact, Mapping) or artifact.get("contract_version") != SIGNAL_VELOCITY_CONTRACT_VERSION:
        return _velocity_unavailable("SIGNAL_VELOCITY_ARTIFACT_NOT_SUPPLIED_OR_UNSUPPORTED_CONTRACT")
    record = next(
        (
            row for row in artifact.get("records", [])
            if isinstance(row, Mapping) and row.get("ticker") == ticker and row.get("session") == as_of_session
        ),
        None,
    )
    if record is None:
        return _velocity_unavailable("NO_RETAINED_VELOCITY_RECORD_FOR_EXACT_SESSION")
    axes = record.get("axes") or {}
    reference_trajectory = next(
        (axis.get("trajectory") for axis in axes.values() if isinstance(axis, Mapping) and axis.get("trajectory")),
        {},
    ) or {}
    return {
        "contract_version": SIGNAL_VELOCITY_CONTRACT_VERSION,
        "source_artifact_identity": artifact.get("artifact_identity"),
        "source_record_session": record.get("session"),
        "overall_transition_state": record.get("overall_transition_state"),
        "evidence_quality": (record.get("evidence_quality") or {}).get("state"),
        "valid_observation_count": reference_trajectory.get("valid_observation_count"),
        "retained_session_span": reference_trajectory.get("retained_session_span"),
        "continuity_state": reference_trajectory.get("continuity_state"),
        "latest_transition": reference_trajectory.get("latest_transition"),
        "persistence": reference_trajectory.get("persistence"),
        "acceleration_state": reference_trajectory.get("acceleration_state"),
        "independent_supporting_axes": list(record.get("independent_supporting_axes") or []),
        "contradicting_axes": list(record.get("contradicting_axes") or []),
        "limitations": list(VELOCITY_LIMITATIONS),
        "reason_code": None,
        "is_actionable": False,
    }


def _flow_price_unavailable(cohort_membership: str, reason_code: str) -> dict[str, Any]:
    return {
        "contract_version": FLOW_PRICE_CONTRACT_VERSION,
        "source_artifact_identity": None,
        "reference_session": None,
        "cohort_membership": cohort_membership,
        "relationship": "FLOW_UNAVAILABLE",
        "foreign_flow_state": None,
        "flow_persistence": None,
        "latest_qualified_flow_session": None,
        "flow_freshness": None,
        "price_state": None,
        "price_velocity_state": None,
        "participation_context": None,
        "market_support": None,
        "sector_support": None,
        "evidence_quality": "INSUFFICIENT_RETAINED_EVIDENCE",
        "session_alignment": "UNAVAILABLE",
        "limitations": list(FLOW_PRICE_DEFAULT_LIMITATIONS),
        "reason_code": reason_code,
        "is_actionable": False,
    }


def flow_price_view(
    *, ticker: str, artifact: Mapping[str, Any] | None, cohort_tickers: frozenset[str],
) -> dict[str, Any]:
    """One ticker's compact, presentation-safe Flow-Price Divergence view.

    ``cohort_tickers`` is the configured current-foreign-flow research cohort, resolved
    independently of whether the join actually produced a current relationship -- this is
    what lets the UI say "not yet in scope" instead of "missing" for the 1,6xx names the
    flow-acquisition system was never configured to track.
    """
    cohort_membership = IN_COHORT if ticker in cohort_tickers else OUTSIDE_COHORT
    if not isinstance(artifact, Mapping) or artifact.get("contract_version") != FLOW_PRICE_CONTRACT_VERSION:
        return _flow_price_unavailable(cohort_membership, "FLOW_PRICE_ARTIFACT_NOT_SUPPLIED_OR_UNSUPPORTED_CONTRACT")
    record = next(
        (row for row in artifact.get("records", []) if isinstance(row, Mapping) and row.get("ticker") == ticker),
        None,
    )
    if record is None:
        return _flow_price_unavailable(cohort_membership, "NO_RETAINED_FLOW_PRICE_RECORD_FOR_TICKER")
    flow = record.get("flow") or {}
    price = record.get("price") or {}
    return {
        "contract_version": FLOW_PRICE_CONTRACT_VERSION,
        "source_artifact_identity": artifact.get("artifact_identity"),
        "reference_session": record.get("reference_session"),
        "cohort_membership": cohort_membership,
        "relationship": record.get("relationship"),
        "foreign_flow_state": flow.get("state"),
        "flow_persistence": flow.get("persistence"),
        "latest_qualified_flow_session": flow.get("latest_qualified_flow_session"),
        "flow_freshness": flow.get("freshness"),
        "price_state": price.get("state"),
        "price_velocity_state": price.get("velocity_state"),
        "participation_context": price.get("participation_context"),
        "market_support": price.get("market_support"),
        "sector_support": price.get("sector_support"),
        "evidence_quality": record.get("evidence_quality"),
        "session_alignment": (record.get("session_alignment") or {}).get("state"),
        "limitations": list(record.get("limitations") or FLOW_PRICE_DEFAULT_LIMITATIONS),
        "reason_code": None,
        "is_actionable": False,
    }
