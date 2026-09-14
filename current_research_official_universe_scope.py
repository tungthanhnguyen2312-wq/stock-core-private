"""Consumer-scope adapter over ``current_official_market_universe.py``.

Turns an already-built official-universe (optionally HNX/UPCoM security-status-enriched)
artifact plus a requested Current Research session into a deterministic per-ticker scope
decision: is this Stock Lookup reference candidate inside the Current Research official-universe
scope for THIS session, and is the underlying official evidence even temporally usable for it.

This module contains:
    - NO acquisition code, no network, no provider calls (consumes retained artifacts only);
    - NO listing-status inference (every status value is read verbatim from the supplied
      artifact's own fields -- see ``current_official_market_universe.py`` and
      ``hnx_official_issuer_profile_multi_gate.py`` for where those are actually computed);
    - NO strategy/ranking/sizing/valuation rules.

THE THREE UNIVERSES THIS MODULE DELIBERATELY KEEPS DISTINCT
    A. Source/acquisition reference universe -- ``official_artifact["records"]`` restricted to
       ``stocklookup_candidate`` rows (the governed 1,683). Never shrunk here.
    B. Current official exchange-presence research universe -- the subset of A currently matched
       to a live HNX/UPCoM or HOSE official master row (~1,504 as of the 2026-09-13 evidence).
       This is INTERSECTION(A, official presence), never a union that adds official-only rows.
    C. Session-observed cohort (price/tactical availability) -- deliberately NOT computed here;
       this module only ever reports UNIVERSE membership, never data availability. A caller that
       wants "eligible AND has a price" composes that itself from this output plus its own
       Screener/Workspace price fields.

THE TEMPORAL GATE (non-negotiable)
    Official evidence carries its own observation timestamp
    (``current_official_market_universe`` records' ``official_observed_at``, all 2026-09-13 for
    the currently retained snapshot). A research session's official-universe scope is usable only
    when that session's own date is ON OR AFTER the evidence's observation date -- using evidence
    observed AFTER a session to retroactively define what the universe "was" on that earlier date
    would silently rewrite history with knowledge that did not exist yet. A session strictly
    BEFORE the observation date gets an explicit ``TEMPORALLY_INELIGIBLE_FOR_SESSION`` disposition
    and NEVER a numeric scope denominator for that session -- see ``resolve_scope``.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

CONTRACT_VERSION = "current_research_official_universe_scope/v1"

# Per-ticker current_research_scope_state.
SCOPE_ELIGIBLE = "IN_CURRENT_OFFICIAL_RESEARCH_SCOPE"
SCOPE_OUTSIDE_DELISTING_CORRELATED = "OUTSIDE_CURRENT_OFFICIAL_MASTER_REASON_DELISTING_CORRELATED"
SCOPE_OUTSIDE_UNRESOLVED = "OUTSIDE_CURRENT_OFFICIAL_MASTER_REASON_UNRESOLVED"
SCOPE_TEMPORAL_UNAVAILABLE = "TEMPORAL_EVIDENCE_NOT_AVAILABLE_FOR_SESSION"
SCOPE_CONFLICT = "CONFLICT"

# Per-ticker current_research_scope_fitness (deliberately NOT historical-PIT vocabulary).
FITNESS_ELIGIBLE = "CURRENT_RESEARCH_SCOPE_ELIGIBLE"
FITNESS_INELIGIBLE_MASTER = "CURRENT_RESEARCH_SCOPE_INELIGIBLE_CURRENT_MASTER"
FITNESS_TEMPORAL_INELIGIBLE = "TEMPORALLY_INELIGIBLE_FOR_REQUESTED_SESSION"
FITNESS_PARTIAL = "CURRENT_STATUS_PARTIAL"
FITNESS_CONFLICT = "CONFLICT"

# Top-level disposition.
DISPOSITION_ELIGIBLE = "CURRENT_OBSERVED_EVIDENCE_AVAILABLE"
DISPOSITION_TEMPORALLY_INELIGIBLE = "TEMPORALLY_INELIGIBLE_FOR_SESSION"

_ELIGIBLE_PRESENCE_STATES = frozenset({"OFFICIAL_CURRENT_EXCHANGE_SECURITY", "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE"})
_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")


class CurrentResearchOfficialUniverseScopeError(ValueError):
    """A required input or invariant of this adapter is violated."""


def _date_only(value: str) -> str:
    match = _DATE_PREFIX.match(str(value or ""))
    if not match:
        raise CurrentResearchOfficialUniverseScopeError(f"UNPARSEABLE_SESSION_OR_TIMESTAMP_DATE:{value!r}")
    return match.group(1)


def derive_official_snapshot_observed_at(official_artifact: Mapping[str, Any]) -> str:
    """The evidence's own observation timestamp, derived from its already-retained per-record
    ``official_observed_at`` values (the latest one) -- never a new acquisition, never today's
    wall-clock date. Raises if no record carries one (an artifact this module cannot date)."""
    records = official_artifact.get("records")
    if not isinstance(records, Mapping):
        raise CurrentResearchOfficialUniverseScopeError("OFFICIAL_ARTIFACT_RECORDS_MISSING")
    observed = sorted({row.get("official_observed_at") for row in records.values() if isinstance(row, Mapping) and row.get("official_observed_at")})
    if not observed:
        raise CurrentResearchOfficialUniverseScopeError("OFFICIAL_ARTIFACT_HAS_NO_OBSERVED_AT_EVIDENCE")
    return observed[-1]


def _security_status(row: Mapping[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Prefer the HNX/UPCoM security-status enrichment (more specific: actual control/trading
    status text) when present on this record; otherwise fall back to the generic
    ``official_security_status`` field ``current_official_market_universe.py`` already attaches
    to every matched row (NORMAL_OR_NO_SPECIAL_STATUS for HOSE, NOT_PROVIDED_BY_SOURCE_SURFACE
    for HNX/UPCoM absent the narrower enrichment). Never blends or overwrites either source."""
    if "hnx_upcom_official_trading_status" in row:
        return (
            row.get("hnx_upcom_official_trading_status"),
            row.get("hnx_upcom_official_control_status"),
            row.get("hnx_upcom_target_session_applicability"),
        )
    return row.get("official_security_status"), None, None


def resolve_scope(
    *,
    official_artifact: Mapping[str, Any],
    research_session: str,
    official_snapshot_observed_at: str | None = None,
) -> dict[str, Any]:
    """Resolve the Current Research official-universe scope for ``research_session``.

    ``official_snapshot_observed_at`` may be supplied explicitly (e.g. for a test); when omitted
    it is derived from the artifact's own retained evidence via
    ``derive_official_snapshot_observed_at``. Never derives it from wall-clock "now".
    """
    observed_at = official_snapshot_observed_at or derive_official_snapshot_observed_at(official_artifact)
    temporally_eligible = _date_only(research_session) >= _date_only(observed_at)

    records = official_artifact.get("records")
    if not isinstance(records, Mapping):
        raise CurrentResearchOfficialUniverseScopeError("OFFICIAL_ARTIFACT_RECORDS_MISSING")

    per_ticker: dict[str, dict[str, Any]] = {}
    for ticker, row in records.items():
        if not isinstance(row, Mapping) or not row.get("stocklookup_candidate"):
            # Official-only rows (not in the governed 1,683 reference set) are never part of
            # this scope -- intersection, never union. See module docstring universe B.
            continue
        current_universe_status = row.get("current_universe_status")
        official_presence = current_universe_status in _ELIGIBLE_PRESENCE_STATES
        trading_status, control_status, target_session_applicability = _security_status(row)

        if not temporally_eligible:
            scope_state = SCOPE_TEMPORAL_UNAVAILABLE
            fitness = FITNESS_TEMPORAL_INELIGIBLE
        elif official_presence:
            scope_state = SCOPE_ELIGIBLE
            fitness = FITNESS_PARTIAL if trading_status not in (None, "ACTIVE", "NORMAL_OR_NO_SPECIAL_STATUS") else FITNESS_ELIGIBLE
        else:
            qualification = row.get("qualification")
            if qualification == "DELISTED_OR_NO_LONGER_CURRENT":
                scope_state = SCOPE_OUTSIDE_DELISTING_CORRELATED
            elif qualification == "UNRESOLVED":
                scope_state = SCOPE_OUTSIDE_UNRESOLVED
            else:
                scope_state = SCOPE_CONFLICT
            fitness = FITNESS_CONFLICT if scope_state == SCOPE_CONFLICT else FITNESS_INELIGIBLE_MASTER

        per_ticker[ticker] = {
            "ticker": ticker,
            "source_reference_member": True,
            "official_current_exchange_presence": official_presence,
            "official_exchange_or_market": row.get("exchange_or_market"),
            "official_security_status": trading_status,
            "official_security_control_status": control_status,
            "official_status_observed_at": row.get("official_observed_at") or observed_at,
            "official_status_temporal_fitness": (
                target_session_applicability if temporally_eligible and target_session_applicability
                else (DISPOSITION_ELIGIBLE if temporally_eligible else FITNESS_TEMPORAL_INELIGIBLE)
            ),
            "current_research_scope_state": scope_state,
            "current_research_scope_reason": row.get("qualification"),
            "current_research_scope_fitness": fitness,
            "target_session_observation_state": None,  # deliberately not computed here; see module docstring universe C
        }

    if len(per_ticker) != sum(1 for row in records.values() if isinstance(row, Mapping) and row.get("stocklookup_candidate")):
        raise CurrentResearchOfficialUniverseScopeError("SOURCE_REFERENCE_ACCOUNTING_INVALID")

    source_reference_ticker_count = len(per_ticker)
    scope_ticker_count = sum(1 for row in per_ticker.values() if row["current_research_scope_state"] == SCOPE_ELIGIBLE)

    return {
        "contract_version": CONTRACT_VERSION,
        "research_session": research_session,
        "official_snapshot_observed_at": observed_at,
        "temporally_eligible": temporally_eligible,
        "disposition": DISPOSITION_ELIGIBLE if temporally_eligible else DISPOSITION_TEMPORALLY_INELIGIBLE,
        "source_reference_ticker_count": source_reference_ticker_count,
        # Deliberately None (never 0, never a stale number) when the session is temporally
        # ineligible -- there is no valid session-native denominator to report at all, per the
        # non-negotiable temporal gate. A caller must check `disposition`/`temporally_eligible`
        # before ever reading this field as a real count.
        "current_research_scope_ticker_count": scope_ticker_count if temporally_eligible else None,
        "records": per_ticker,
        "authority_boundary": {
            "historical_pit_universe": "BLOCKED",
            "active_universe_authority_promotion": "NOT_PERFORMED",
            "denominator_cutover": "NOT_PERFORMED_BY_THIS_MODULE",
            "note": "This function only classifies; it never writes to or mutates any retained product artifact.",
        },
    }


def eligible_ticker_set(scope_result: Mapping[str, Any]) -> frozenset[str]:
    """The plain ticker set a consumer adapter (Screener/Workspace) actually filters against.
    Empty (never a stale prior scope) when the session was temporally ineligible.

    Kept for callers that genuinely need a plain eligible-ticker-set view (e.g. cross-checks,
    negative controls). Product surfaces that render every reference row -- Screener, Workspace
    -- must NOT use this to narrow their own denominator; see ``ticker_scope_view`` below."""
    if not scope_result.get("temporally_eligible"):
        return frozenset()
    return frozenset(
        ticker for ticker, row in scope_result["records"].items()
        if row["current_research_scope_state"] == SCOPE_ELIGIBLE
    )


# Simplified 3-state bucket for a consumer card -- additive to, never a replacement for, the
# richer per-ticker vocabulary ``resolve_scope`` already emits (``current_research_scope_state``,
# ``current_research_scope_fitness``, ...), which ``ticker_scope_view`` also passes through
# verbatim below.
SIMPLE_IN_SCOPE = "IN_CURRENT_OFFICIAL_RESEARCH_SCOPE"
SIMPLE_OUTSIDE_SCOPE = "OUTSIDE_CURRENT_OFFICIAL_RESEARCH_SCOPE"
SIMPLE_SCOPE_UNKNOWN = "CURRENT_OFFICIAL_SCOPE_UNKNOWN"


def ticker_scope_view(scope_result: Mapping[str, Any] | None, ticker: str) -> dict[str, Any]:
    """Deterministic, non-destructive per-ticker scope view for a consumer card (Screener,
    Workspace, ...).

    Unlike ``eligible_ticker_set``, this NEVER narrows or drops a caller's own ticker/card set --
    a caller attaches this view to every card it already builds, including tickers outside the
    current official research scope and tickers this adapter cannot resolve at all (not a
    governed reference member, or the scope itself is unavailable/temporally ineligible for the
    requested session). No card is ever removed because of what this function returns.

    Returns the simplified ``scope_bucket`` (one of ``SIMPLE_IN_SCOPE`` /
    ``SIMPLE_OUTSIDE_SCOPE`` / ``SIMPLE_SCOPE_UNKNOWN`` -- the repository vocabulary named in
    ``docs/STATE.md``'s official-research-scope contract) plus the richer existing-vocabulary
    detail (``current_research_scope_state``, ``current_research_scope_fitness``, official
    exchange presence/status) when resolvable, and ``None`` for the detail fields otherwise.
    """
    if not isinstance(scope_result, Mapping) or not scope_result.get("temporally_eligible"):
        reason = "CURRENT_OFFICIAL_SCOPE_NOT_SUPPLIED"
        if isinstance(scope_result, Mapping):
            reason = scope_result.get("disposition") or FITNESS_TEMPORAL_INELIGIBLE
        return {
            "scope_bucket": SIMPLE_SCOPE_UNKNOWN,
            "current_research_scope_state": None,
            "current_research_scope_fitness": None,
            "current_research_scope_reason": reason,
            "official_current_exchange_presence": None,
            "official_security_status": None,
            "research_session": scope_result.get("research_session") if isinstance(scope_result, Mapping) else None,
            "official_snapshot_observed_at": scope_result.get("official_snapshot_observed_at") if isinstance(scope_result, Mapping) else None,
        }
    record = (scope_result.get("records") or {}).get(ticker)
    if not isinstance(record, Mapping):
        return {
            "scope_bucket": SIMPLE_SCOPE_UNKNOWN,
            "current_research_scope_state": None,
            "current_research_scope_fitness": None,
            "current_research_scope_reason": "NOT_A_GOVERNED_REFERENCE_MEMBER",
            "official_current_exchange_presence": None,
            "official_security_status": None,
            "research_session": scope_result.get("research_session"),
            "official_snapshot_observed_at": scope_result.get("official_snapshot_observed_at"),
        }
    bucket = SIMPLE_IN_SCOPE if record["current_research_scope_state"] == SCOPE_ELIGIBLE else SIMPLE_OUTSIDE_SCOPE
    return {
        "scope_bucket": bucket,
        "current_research_scope_state": record["current_research_scope_state"],
        "current_research_scope_fitness": record.get("current_research_scope_fitness"),
        "current_research_scope_reason": record.get("current_research_scope_reason"),
        "official_current_exchange_presence": record.get("official_current_exchange_presence"),
        "official_security_status": record.get("official_security_status"),
        "research_session": scope_result.get("research_session"),
        "official_snapshot_observed_at": scope_result.get("official_snapshot_observed_at"),
    }
