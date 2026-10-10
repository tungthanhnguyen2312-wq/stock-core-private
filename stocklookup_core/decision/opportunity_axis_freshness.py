"""Per-axis session/freshness contracts for current opportunity integration.

Current retained axes may have different sessions. This module never coerces them into one
fictitious same-session snapshot, never rewrites an old observation as current, and never
joins future information relative to the decision session.
"""
from __future__ import annotations

import calendar
from datetime import date
import re
from typing import Any, Mapping

CONTRACT_VERSION = "opportunity_axis_freshness/v1"
FINANCIAL_PERIOD_FRESHNESS_CONTRACT = "financial_period_freshness/v1"
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


def completed_quarter_lag(source_period: Any, decision_session: str) -> tuple[int | None, int | None, str | None]:
    """``(lag, quarters_behind_last_completed, blocker)`` for one ``YYYY-Qn`` financial period.

    ``lag`` is the decision session's quarter index minus the period's, the measure every
    Current Research financial window already uses. A period that has not ended by the decision
    session is future information; a label that is not a quarter is unresolved.
    """
    match = re.fullmatch(r"(\d{4})-Q([1-4])", str(source_period or ""))
    if not match:
        return None, None, "FINANCIAL_SOURCE_PERIOD_UNRESOLVED"
    period_index = int(match[1]) * 4 + int(match[2])
    day = date.fromisoformat(str(decision_session)[:10])
    quarter = (day.month - 1) // 3 + 1
    session_index = day.year * 4 + quarter
    quarter_end = date(day.year, quarter * 3, calendar.monthrange(day.year, quarter * 3)[1])
    last_completed = session_index if day >= quarter_end else session_index - 1
    if period_index > last_completed:
        return None, None, "FINANCIAL_PERIOD_AFTER_DECISION_SESSION"
    return session_index - period_index, last_completed - period_index, None


def classify_financial_period_freshness(*, source_period: Any, decision_session: str,
                                        maximum_completed_quarter_lag: int) -> dict[str, Any]:
    """Freshness of periodic financial evidence for the (period-based, older-usable) fundamental axis.

    Within the governed completed-quarter window the evidence is ``CURRENT``; beyond it, it stays
    ``STALE_BUT_RESEARCH_USABLE`` and labelled, never dropped and never rewritten as current. No
    resolvable, completed period means ``UNAVAILABLE``.
    """
    lag, behind, blocker = (None, None, "FINANCIAL_SOURCE_PERIOD_ABSENT") if not source_period else \
        completed_quarter_lag(source_period, decision_session)
    if blocker:
        state, reasons = UNAVAILABLE, [blocker]
    elif lag > maximum_completed_quarter_lag:
        state, reasons = STALE_BUT_RESEARCH_USABLE, ["FINANCIAL_PERIOD_BEYOND_MAXIMUM_COMPLETED_QUARTER_LAG"]
    else:
        state, reasons = CURRENT, []
    return {
        "contract_version": FINANCIAL_PERIOD_FRESHNESS_CONTRACT,
        "vocabulary": CONTRACT_VERSION,
        "source_period": source_period,
        "decision_session": decision_session,
        "completed_quarter_lag": lag,
        "quarters_behind_last_completed_quarter": behind,
        "maximum_completed_quarter_lag": maximum_completed_quarter_lag,
        "freshness_status": state,
        "reason_codes": reasons,
        "older_evidence_usable": bool(AXIS_CONTRACTS["fundamental"]["older_usable"]),
        "rewritten_as_current": False,
    }


def axis_is_research_usable(envelope: Mapping[str, Any]) -> bool:
    return envelope.get("freshness_status") in {CURRENT, STALE_BUT_RESEARCH_USABLE}


def assert_artifact_session_not_future(session: str | None, *, decision_session: str, label: str) -> None:
    """Fail closed when a whole source artifact is later than the decision session."""
    if _session(session) and session > decision_session:
        raise FutureInformationError(f"FUTURE_INFORMATION_PROHIBITED:{label}:{session}>{decision_session}")
