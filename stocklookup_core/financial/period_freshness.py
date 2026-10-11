"""Financial period freshness policy; thresholds remain explicit caller inputs."""
from __future__ import annotations
from typing import Any
from stocklookup_core.evidence.temporal_freshness import (
    CONTRACT_VERSION, FINANCIAL_PERIOD_FRESHNESS_CONTRACT, CURRENT,
    STALE_BUT_RESEARCH_USABLE, UNAVAILABLE, completed_quarter_lag,
)

# One shared domain contract, also exposed by the legacy decision-axis mapping.
FUNDAMENTAL_CONTRACT = {"older_usable": True, "period_based": True}

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
        "older_evidence_usable": bool(FUNDAMENTAL_CONTRACT["older_usable"]),
        "rewritten_as_current": False,
    }
