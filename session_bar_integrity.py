"""Shared (ticker, session) uniqueness invariant for retained daily-bar observations.

A retained record's ``observations`` must carry at most one bar per trading session before any
multi-session analytical series is computed from it. Real evidence: the 2026-09-16 P3F9B snapshot's
DNSE ``/price/ohlc`` responses carried two 2026-09-15 bars for 599 tickers, plus pre-/post-
adjustment copies of 2026-08-28/09-03/09-04 for VPI and TCH, all under one request, one
``retrieved_at`` and one declared price basis. ``mva_exact_session_snapshot._observation_rows``
enforces uniqueness only for the target session, so the history rows were retained as returned.

Every series consumer resolves a record through this one function, so no engine keeps its own
duplicate rule:

* ``UNIQUE`` -- no session repeats; the input list is returned unchanged (same object).
* ``EXACT_DUPLICATE_COLLAPSED`` -- repeats are identical in every retained field (values, provider,
  request, ``retrieved_at``, price basis, transformation identity, ...). Any copy yields the same
  observation, so they collapse to the first occurrence. No authority decision is involved.
* ``CONFLICTING_DUPLICATE_REFUSED`` -- repeats differ in any field. No repository rule establishes
  which copy is authoritative: both copies share provider, request, ``retrieved_at``, basis label
  and transformation identity, and list position is not provenance. The record is refused for
  series use -- never averaged, never first/last-wins. Precedent: every other retained-bar reader
  refuses duplicate sessions (``historical_series_failover`` ``DUPLICATE_SESSION_ROW``,
  ``current_portfolio_risk_research`` ``DUPLICATE_SESSION_WITHOUT_DETERMINISTIC_RESOLUTION``,
  ``dnse_current_state_price_analytics``, ``kbs_empirical_basis``).

Rows dated after ``as_of_session`` never influence the decision and pass through untouched, so
consumers keep their own future-row rules. Non-mapping rows and rows without a string session also
pass through untouched for the consumer's own malformed-row handling.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

UNIQUE = "UNIQUE"
EXACT_DUPLICATE_COLLAPSED = "EXACT_DUPLICATE_COLLAPSED"
CONFLICTING_DUPLICATE_REFUSED = "CONFLICTING_DUPLICATE_REFUSED"
REFUSAL_REASON = "CONFLICTING_DUPLICATE_SESSION_BAR"
CONTRACT = "session_bar_integrity/v1"


def _row_identity(row: Mapping[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def resolve_session_bars(observations: Any, *, as_of_session: str | None = None) -> dict[str, Any]:
    """Resolve one record's observations to the uniqueness invariant.

    Returns ``{"status", "observations", "exact_duplicate_sessions", "conflicting_sessions",
    "conflicting_fields"}``. ``observations`` is the input object itself when ``UNIQUE``, the
    collapsed list when ``EXACT_DUPLICATE_COLLAPSED`` and ``[]`` when refused.
    """
    result: dict[str, Any] = {
        "status": UNIQUE, "observations": observations,
        "exact_duplicate_sessions": [], "conflicting_sessions": [], "conflicting_fields": {},
    }
    if not isinstance(observations, list):
        return result
    groups: dict[str, list[int]] = {}
    for index, row in enumerate(observations):
        if not isinstance(row, Mapping):
            continue
        session = row.get("session")
        if not isinstance(session, str) or (as_of_session is not None and session > as_of_session):
            continue
        groups.setdefault(session, []).append(index)
    repeated = {session: indexes for session, indexes in groups.items() if len(indexes) > 1}
    if not repeated:
        return result
    drop: set[int] = set()
    exact: list[str] = []
    conflicting: dict[str, list[str]] = {}
    for session, indexes in repeated.items():
        rows = [observations[index] for index in indexes]
        if len({_row_identity(row) for row in rows}) == 1:
            exact.append(session)
            drop.update(indexes[1:])
            continue
        fields = sorted({key for row in rows for key in row if any(other.get(key) != row.get(key) for other in rows)})
        conflicting[session] = fields
    result["exact_duplicate_sessions"] = sorted(exact)
    if conflicting:
        result.update(
            status=CONFLICTING_DUPLICATE_REFUSED, observations=[],
            conflicting_sessions=sorted(conflicting), conflicting_fields=dict(sorted(conflicting.items())),
        )
        return result
    result.update(
        status=EXACT_DUPLICATE_COLLAPSED,
        observations=[row for index, row in enumerate(observations) if index not in drop],
    )
    return result


def integrity_summary(resolution: Mapping[str, Any]) -> dict[str, Any]:
    """The compact, deterministic block a consumer attaches when a record was not ``UNIQUE``."""
    summary = {
        "contract": CONTRACT, "status": resolution["status"],
        "exact_duplicate_sessions": list(resolution["exact_duplicate_sessions"]),
        "conflicting_sessions": list(resolution["conflicting_sessions"]),
    }
    if resolution["conflicting_sessions"]:
        summary["conflicting_fields"] = dict(resolution["conflicting_fields"])
        summary["reason"] = REFUSAL_REASON
    return summary


def resolve_record(record: Any, *, as_of_session: str | None = None) -> tuple[Any, dict[str, Any]]:
    """Resolve a retained record. ``UNIQUE`` returns the record itself; otherwise a shallow copy
    whose ``observations`` are resolved and which carries ``session_bar_integrity``."""
    if not isinstance(record, Mapping):
        return record, resolve_session_bars(None)
    resolution = resolve_session_bars(record.get("observations"), as_of_session=as_of_session)
    if resolution["status"] == UNIQUE:
        return record, resolution
    return {**record, "observations": resolution["observations"],
            "session_bar_integrity": integrity_summary(resolution)}, resolution


def is_refused(record: Any) -> bool:
    return isinstance(record, Mapping) and (record.get("session_bar_integrity") or {}).get("status") == CONFLICTING_DUPLICATE_REFUSED
