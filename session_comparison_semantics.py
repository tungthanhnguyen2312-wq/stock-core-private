"""Deterministic comparison-session semantics, distinguishing what a comparison actually is.

Context (SESSION_REGISTRY_PROMOTION_AND_COMPARISON_SEMANTICS_CORRECTIVE_V1): the governed
"previous session" (latest ``completed_sessions`` entry strictly before the current session) is
not always the immediately preceding trading session -- a registry-promotion gap can leave several
known, real sessions between them. ``next_session_decision_brief`` and downstream AI-facing briefs
previously exposed only ``previous_qualified_session``, which reads identically whether the gap is
zero or several sessions wide. This module adds an explicit, additive classification so a
multi-session gap can never be silently presented as an ordinary adjacent-day transition.

Every field is derived purely from the already-loaded session registry
(``config/daily_research_session_input_registry.json``): ``completed_sessions`` (governed-complete)
and ``sessions`` (registered/attempted, not necessarily governed-complete). No calendar-day
arithmetic, no filesystem scan, no wall clock, no market-calendar inference. Where the registry does
not already know about an intervening session, this module reports that it cannot prove adjacency
rather than assuming there is none.
"""
from __future__ import annotations

from typing import Any, Mapping

CONTRACT_VERSION = "session_comparison_semantics/v1"

ROLE_IMMEDIATE = "IMMEDIATE_PREVIOUS_GOVERNED_SESSION"
ROLE_DISTANT = "DISTANT_PREVIOUS_GOVERNED_SESSION"
ROLE_NONE = "NO_PREVIOUS_GOVERNED_SESSION"

FITNESS_FRESH = "FRESH_ADJACENT"
FITNESS_DEGRADED = "DEGRADED_MULTI_SESSION_GAP"
FITNESS_UNAVAILABLE = "UNAVAILABLE"

REASON_NO_PREVIOUS_GOVERNED_SESSION = "NO_PREVIOUS_GOVERNED_SESSION"
REASON_REGISTRY_GAP = "PREVIOUS_SESSION_REGISTRY_GAP"


def _known_sessions(registry: Mapping[str, Any]) -> set[str]:
    """Every session identifier this registry has ever recorded, governed or merely attempted."""
    known: set[str] = set()
    completed = registry.get("completed_sessions")
    attempted = registry.get("sessions")
    if isinstance(completed, Mapping):
        known |= {str(key) for key in completed}
    if isinstance(attempted, Mapping):
        known |= {str(key) for key in attempted}
    return known


def _notice(*, current_session: str, comparison_session: str, gap: int) -> str:
    plural = "session" if gap == 1 else "sessions"
    return (
        f"Comparison session is {comparison_session}, the latest governed-complete session before "
        f"{current_session} -- not necessarily the immediately preceding trading session. "
        f"{gap} known {plural} between {comparison_session} and {current_session} exist but are "
        f"excluded from this comparison because the registry never marked them governed-complete."
    )


def build_comparison_metadata(
    *, registry: Mapping[str, Any], current_session: str, comparison_session: str | None,
) -> dict[str, Any]:
    """Classify ``comparison_session`` (already resolved as the latest governed-complete session
    strictly before ``current_session``, e.g. by ``stocklookup.py:_previous``) against everything
    else this registry independently knows about.

    Never recomputes ``comparison_session`` itself -- that resolution, and its
    governed-completion requirement, stays exactly where it already lives.
    """
    if comparison_session is None:
        return {
            "schema_version": "1.0.0",
            "contract_version": CONTRACT_VERSION,
            "comparison_session": None,
            "comparison_session_role": ROLE_NONE,
            "session_gap_trading_sessions": None,
            "is_immediate_previous_completed_session": False,
            "comparison_fitness": FITNESS_UNAVAILABLE,
            "comparison_reason_codes": [REASON_NO_PREVIOUS_GOVERNED_SESSION],
            "skipped_known_sessions": [],
            "notice": None,
        }

    known = _known_sessions(registry)
    # By construction, comparison_session is the LATEST governed-complete session strictly before
    # current_session, so nothing in ``between`` can itself be governed-complete -- if it were, it
    # would have been chosen instead. This is re-derived from the registry, not assumed.
    between = sorted(session for session in known if comparison_session < session < current_session)
    gap = len(between)

    if gap == 0:
        return {
            "schema_version": "1.0.0",
            "contract_version": CONTRACT_VERSION,
            "comparison_session": comparison_session,
            "comparison_session_role": ROLE_IMMEDIATE,
            "session_gap_trading_sessions": 0,
            "is_immediate_previous_completed_session": True,
            "comparison_fitness": FITNESS_FRESH,
            "comparison_reason_codes": [],
            "skipped_known_sessions": [],
            "notice": None,
        }

    return {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "comparison_session": comparison_session,
        "comparison_session_role": ROLE_DISTANT,
        "session_gap_trading_sessions": gap,
        "is_immediate_previous_completed_session": False,
        "comparison_fitness": FITNESS_DEGRADED,
        "comparison_reason_codes": [REASON_REGISTRY_GAP],
        "skipped_known_sessions": between,
        "notice": _notice(current_session=current_session, comparison_session=comparison_session, gap=gap),
    }
