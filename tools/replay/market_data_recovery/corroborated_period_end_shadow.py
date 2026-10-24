"""Shadow lane: period-end anchor corroborated by an independent observation.

WHAT THIS IS, AND WHAT IT IS NOT
    An official `period_end_shares_outstanding` citation plus a provider observation reporting
    the same count has the same *shape* as the evidence that promotes an executed event: an
    absolute count from an official source, and an independent reading agreeing with it. It is
    not the same *strength*, and this module exists so the difference stays visible rather than
    being argued about at the point of use.

    It is **shadow-only**. Nothing here participates in `resolve_effective_shares`, in the
    authority lane counts, in the operating report's coverage block, or in the exported bundle.
    Reading this module changes no production verdict. Promoting it out of shadow requires its
    own validation and its own governance decision, neither of which exists.

WHY IT IS WEAKER THAN AN EXECUTED EVENT
    An executed event states the count the issuer holds *as of that event*, so the observation
    only has to carry the interval from the event to the session — four weeks for HPG. A
    period-end figure states the count on a balance-sheet date, so the observation carries
    everything since — nineteen months for VNM. The logic of corroboration does not change with
    the length, but the exposure does, and `interval_days_carried_by_observation` reports it on
    every verdict rather than leaving the reader to compute it.

    More fundamentally: agreement proves the **net** count is unchanged, not that nothing
    happened. Two offsetting events produce the same number. `proves_no_intervening_event` is
    `false` on every verdict and is not a field that can ever be true here.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Mapping

from market_wide_current_shares_resolver import (
    _PERIOD_END_IDENTITY,
    _Store,
    ShareStoreUnreadable,
    _anchor_boundary,
    _as_date,
)

SHADOW_VERSION = "1.0.0"

#: The lane's name wherever it is reported. Never `qualified_official`, and never a value the
#: resolver's `authority` field may take.
LANE = "corroborated_period_end"

#: Strictly below executed-event evidence. Present as a number so a future comparison cannot
#: accidentally treat the two as peers.
AUTHORITY_RANK = 1
EXECUTED_EVENT_AUTHORITY_RANK = 2


def _verdict(ticker: str, session: str, eligible: bool, reason: str,
             **extra: Any) -> dict[str, Any]:
    return {
        "shadow_version": SHADOW_VERSION,
        "lane": LANE,
        "shadow_only": True,
        "authority_rank": AUTHORITY_RANK,
        "ticker": ticker,
        "session_date": session,
        "eligible": eligible,
        "reason": reason,
        # Neither of these is ever true in this lane. They are emitted on every verdict so a
        # consumer reading one record in isolation cannot mistake what it is holding.
        "proves_no_intervening_event": False,
        "contributes_to_is_actionable": False,
        "contributes_to_qualified_official": False,
        **extra,
    }


def evaluate_ticker(ticker: str, session_date: str, store: _Store) -> dict[str, Any]:
    """One ticker's shadow verdict. Never raises for an ordinary absence."""
    t = str(ticker).upper()
    session = str(session_date)
    session_on = _as_date(session)
    anchor = store.anchors.get(t)
    shares, updated = store.metadata.get(t, (None, None))
    observed_on = _as_date(updated)

    if anchor is None:
        return _verdict(t, session, False, "no_official_anchor_retained")
    if anchor.get("identity_type") != _PERIOD_END_IDENTITY:
        return _verdict(t, session, False, "anchor_is_not_a_period_end_figure",
                        anchor_identity_type=anchor.get("identity_type"))

    boundary: date | None = _anchor_boundary(anchor)
    if boundary is None:
        return _verdict(t, session, False, "anchor_has_no_resolvable_period_end_date")
    if shares is None or isinstance(shares, bool) or float(shares) <= 0:
        return _verdict(t, session, False, "no_positive_independent_observation",
                        anchor_value=anchor["value"])
    if observed_on is None:
        return _verdict(t, session, False, "observation_carries_no_usable_date",
                        anchor_value=anchor["value"])

    observed_value = int(float(shares))
    carried_days = (observed_on - boundary).days
    common = {
        "anchor_value": anchor["value"],
        "anchor_period_end": boundary.isoformat(),
        "anchor_citation_id": anchor.get("citation_id"),
        "observed_value": observed_value,
        "observation_date": observed_on.isoformat(),
        "observation_source": "VCI.overview.issue_share",
        "interval_days_carried_by_observation": carried_days,
        "session_lag_days": ((session_on - observed_on).days if session_on else None),
    }

    if carried_days < 0:
        return _verdict(t, session, False, "observation_predates_the_period_end", **common)
    if observed_value != int(anchor["value"]):
        return _verdict(t, session, False, "observation_contradicts_the_anchor", **common)

    return _verdict(t, session, True,
                    "period_end_anchor_matched_by_an_independent_observation", **common)


def evaluate(runtime_root: Path | str, session_date: str) -> dict[str, Any]:
    """Shadow verdicts across the retained universe, measured on the call.

    Fails the same way the production resolver does — a store that cannot be read is reported
    as unreadable, never as an absence of eligible tickers.
    """
    session = str(session_date).strip()
    if not _as_date(session):
        raise ValueError(f"session_date must be an ISO date, got {session_date!r}")
    try:
        store = _Store(runtime_root)
    except ShareStoreUnreadable as exc:
        return {"shadow_version": SHADOW_VERSION, "lane": LANE, "shadow_only": True,
                "status": "unresolved_error", "reason": str(exc),
                "session_date": session, "eligible_count": None, "tickers": {}}

    verdicts = {t: evaluate_ticker(t, session, store) for t in store.universe()}
    eligible = sorted(t for t, v in verdicts.items() if v["eligible"])
    carried = [verdicts[t]["interval_days_carried_by_observation"] for t in eligible]
    return {
        "shadow_version": SHADOW_VERSION,
        "lane": LANE,
        "shadow_only": True,
        "status": "measured",
        "session_date": session,
        "eligible_count": len(eligible),
        "eligible_tickers": eligible,
        "max_interval_days_carried": max(carried) if carried else None,
        "authority_rank": AUTHORITY_RANK,
        "below": {"lane": "qualified_official", "authority_rank": EXECUTED_EVENT_AUTHORITY_RANK},
        "governance": ("shadow-only; promoting this lane out of shadow needs its own "
                       "validation and its own owner decision"),
        "tickers": verdicts,
    }
