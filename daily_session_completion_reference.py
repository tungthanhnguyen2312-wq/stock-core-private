"""Read-only, fail-closed access to Daily's own governed completed-session registry
(config/daily_research_session_input_registry.json) as a bounded, NON-EXHAUSTIVE proof
source for "was this exact date a real, completed trading session".

AUTHORITY BOUNDARY -- do not weaken this without a new owner decision
    This module answers exactly one narrow question per date: does the registry
    explicitly record it as a Daily session with

        status = "COMPLETED_RETAINED_EVIDENCE"
        trading_day_valid = true

    That is a QUALIFIED_COMPLETED_SESSION_SET, never an EXHAUSTIVE_TRADING_DATE_
    REFERENCE (see dnse_foreign_flow_store.py, which is the only authority allowed to
    name the difference to a caller). A date's ABSENCE from the registry proves nothing:
    Daily can fail, be skipped, or simply never run on a real trading day, and the
    registry then has no row for that date at all. Nothing in this module may be used,
    directly or indirectly, to assert that an absent date was NOT a trading session --
    only ever that a present, qualifying date WAS one. This module never promotes
    itself to a trading calendar, never fills a missing date, and never performs
    weekday/calendar arithmetic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

REGISTRY_RELATIVE_PATH = Path("config") / "daily_research_session_input_registry.json"
QUALIFYING_STATUS = "COMPLETED_RETAINED_EVIDENCE"


def registry_path(source_root: Path | str) -> Path:
    """The one deterministic, explicit location of the registry beneath a source
    checkout root. Callers that already resolve their own source root (never a
    runtime/evidence root, which is a distinct concept) should use this instead of
    re-deriving the relative path themselves."""
    return Path(source_root) / REGISTRY_RELATIVE_PATH


def load_qualified_completed_sessions(path: Path | str) -> frozenset[str]:
    """The set of dates this registry file explicitly proves as completed,
    trading-day-valid Daily sessions.

    Fails closed to an EMPTY set -- never raises -- on a missing file, unreadable/
    malformed JSON, an unexpected top-level shape, or a `completed_sessions` entry
    that does not exactly match the required status/flag pair. An empty result means
    "no proof available from this source", never "these dates are not trading days".
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    if not isinstance(payload, Mapping):
        return frozenset()
    completed = payload.get("completed_sessions")
    if not isinstance(completed, Mapping):
        return frozenset()
    qualified: set[str] = set()
    for date, row in completed.items():
        if (isinstance(date, str) and isinstance(row, Mapping)
                and row.get("status") == QUALIFYING_STATUS and row.get("trading_day_valid") is True):
            qualified.add(date)
    return frozenset(qualified)
