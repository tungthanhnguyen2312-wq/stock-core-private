"""Per-axis session/freshness contracts for current opportunity integration.

Current retained axes may have different sessions. This module never coerces them into one
fictitious same-session snapshot, never rewrites an old observation as current, and never
joins future information relative to the decision session.
"""
from __future__ import annotations

from typing import Any, Mapping

from stocklookup_core.evidence.temporal_freshness import (
    CONTRACT_VERSION, FINANCIAL_PERIOD_FRESHNESS_CONTRACT, CURRENT,
    STALE_BUT_RESEARCH_USABLE, STALE_NOT_USABLE_FOR_THIS_AXIS, UNAVAILABLE,
    FRESHNESS_STATES, COMPATIBLE, INCOMPATIBLE_FUTURE, INCOMPATIBLE_STALE, MISSING,
    FutureInformationError, _session, _envelope, completed_quarter_lag, classify_freshness,
    reporting_period_basis, reporting_period_relation,
    assert_artifact_session_not_future,
)
from stocklookup_core.financial.period_freshness import FUNDAMENTAL_CONTRACT, classify_financial_period_freshness
from stocklookup_core.valuation.freshness import VALUATION_CONTRACT, axis_is_research_usable

# older_usable: lagged evidence may still support this axis as research context.
# Tactical/market structure is session-sensitive; financials and descriptive liquidity are not.
AXIS_CONTRACTS = {
    "fundamental": FUNDAMENTAL_CONTRACT,
    "valuation": VALUATION_CONTRACT,
    "tactical": {"older_usable": False, "period_based": False},
    "market_sector": {"older_usable": False, "period_based": False},
    "catalyst": {"older_usable": True, "period_based": False},
    "downside_invalidation": {"older_usable": True, "period_based": False},
    "liquidity": {"older_usable": True, "period_based": False},
    "portfolio": {"older_usable": True, "period_based": False},
    "data_authority": {"older_usable": True, "period_based": False},
}

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
    return classify_freshness(
        axis=axis, contract=AXIS_CONTRACTS[axis], decision_session=decision_session,
        source_session=source_session, known_at=known_at, source_period=source_period,
        source_artifact_identity=source_artifact_identity,
    )
