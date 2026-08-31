"""Per-axis session/freshness contracts for current opportunity integration.

Current retained axes may have different sessions. This module never coerces them into one
fictitious same-session snapshot, never rewrites an old observation as current, and never
joins future information relative to the decision session.
"""
from __future__ import annotations

from typing import Any, Mapping

CONTRACT_VERSION = "opportunity_axis_freshness/v1"
CURRENT = "CURRENT"
STALE_BUT_RESEARCH_USABLE = "STALE_BUT_RESEARCH_USABLE"
STALE_NOT_USABLE_FOR_THIS_AXIS = "STALE_NOT_USABLE_FOR_THIS_AXIS"
UNAVAILABLE = "UNAVAILABLE"
FRESHNESS_STATES = (CURRENT, STALE_BUT_RESEARCH_USABLE, STALE_NOT_USABLE_FOR_THIS_AXIS, UNAVAILABLE)
COMPATIBLE = "TEMPORALLY_COMPATIBLE"
INCOMPATIBLE_FUTURE = "FUTURE_INFORMATION_PROHIBITED"
INCOMPATIBLE_STALE = "STALE_AXIS_LOCALIZED"
MISSING = "SOURCE_SESSION_ABSENT"

# older_usable: lagged evidence may still support this axis as research context.
# Tactical/market structure is session-sensitive; financials and descriptive liquidity are not.
AXIS_CONTRACTS = {
    "fundamental": {"older_usable": True, "period_based": True},
    "valuation": {"older_usable": True, "period_based": False},
    "tactical": {"older_usable": False, "period_based": False},
    "market_sector": {"older_usable": False, "period_based": False},
    "catalyst": {"older_usable": True, "period_based": False},
    "downside_invalidation": {"older_usable": True, "period_based": False},
    "liquidity": {"older_usable": True, "period_based": False},
    "portfolio": {"older_usable": True, "period_based": False},
    "data_authority": {"older_usable": True, "period_based": False},
}


class FutureInformationError(ValueError):
    """An input artifact or observation is strictly later than the decision session."""


def _session(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def classify_axis_freshness(
    *,
    axis: str,
    decision_session: str,
    source_session: str | None,
    known_at: str | None = None,
    source_period: str | None = None,
    source_artifact_identity: str | None = None,
) -> dict[str, Any]:
    """Return the deterministic freshness envelope for one opportunity axis."""
    if axis not in AXIS_CONTRACTS:
        raise ValueError(f"UNKNOWN_OPPORTUNITY_AXIS:{axis}")
    if not isinstance(decision_session, str) or not decision_session:
        raise ValueError("DECISION_SESSION_REQUIRED")
    contract = AXIS_CONTRACTS[axis]
    source = _session(source_session)
    if source is None:
        if contract.get("period_based") and source_period:
            state, compatibility = STALE_BUT_RESEARCH_USABLE, COMPATIBLE
        else:
            state, compatibility = UNAVAILABLE, MISSING
        return _envelope(axis, decision_session, source, known_at, source_period,
                         source_artifact_identity, state, compatibility, contract)
    if source > decision_session:
        raise FutureInformationError(f"FUTURE_INFORMATION_PROHIBITED:{axis}:{source}>{decision_session}")
    if source == decision_session:
        state, compatibility = CURRENT, COMPATIBLE
    elif contract["older_usable"]:
        state, compatibility = STALE_BUT_RESEARCH_USABLE, COMPATIBLE
    else:
        state, compatibility = STALE_NOT_USABLE_FOR_THIS_AXIS, INCOMPATIBLE_STALE
    return _envelope(axis, decision_session, source, known_at, source_period,
                     source_artifact_identity, state, compatibility, contract)


def _envelope(axis: str, decision_session: str, source_session: str | None, known_at: str | None,
              source_period: str | None, source_artifact_identity: str | None, state: str,
              compatibility: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "axis": axis,
        "decision_session": decision_session,
        "source_session": source_session,
        "source_period": source_period,
        "known_at": known_at,
        "source_artifact_identity": source_artifact_identity,
        "freshness_status": state,
        "compatibility_status": compatibility,
        "older_evidence_usable": bool(contract["older_usable"]) and state == STALE_BUT_RESEARCH_USABLE,
        "rewritten_as_current": False,
        "contract_version": CONTRACT_VERSION,
    }


def axis_is_research_usable(envelope: Mapping[str, Any]) -> bool:
    return envelope.get("freshness_status") in {CURRENT, STALE_BUT_RESEARCH_USABLE}


def assert_artifact_session_not_future(session: str | None, *, decision_session: str, label: str) -> None:
    """Fail closed when a whole source artifact is later than the decision session."""
    if _session(session) and session > decision_session:
        raise FutureInformationError(f"FUTURE_INFORMATION_PROHIBITED:{label}:{session}>{decision_session}")
