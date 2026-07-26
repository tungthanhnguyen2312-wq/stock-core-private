"""Deterministic, fail-closed freshness envelopes for exported data.

This is deliberately independent of artifact mtimes: callers must supply a source
timestamp/date and an injected evaluation time.  It is the only owner of the
freshness vocabulary used by the bundle.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

STATUSES = frozenset({"current", "expiring", "stale", "missing", "historical", "unknown"})


@dataclass(frozen=True)
class DomainRule:
    name: str
    cadence_days: int
    grace_days: int
    historical: bool = False
    requires_complete: bool = False
    market_days: bool = False


RULES = {
    "daily_market": DomainRule("daily_market", 1, 1, market_days=True),
    "technical": DomainRule("technical", 1, 1, market_days=True),
    "ai_report": DomainRule("ai_report", 1, 1, market_days=True),
    "macro_daily": DomainRule("macro_daily", 1, 2),
    "macro_weekly": DomainRule("macro_weekly", 7, 7),
    "macro_monthly": DomainRule("macro_monthly", 31, 14),
    "macro_quarterly": DomainRule("macro_quarterly", 92, 35),
    "financial_quarterly": DomainRule("financial_quarterly", 92, 45, historical=True),
    "corporate_snapshot": DomainRule("corporate_snapshot", 92, 45, requires_complete=True),
    "corporate_events": DomainRule("corporate_events", 1, 7, requires_complete=True),
}


def parse_timestamp(value: Any) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def latest_completed_market_day(reference: datetime) -> date:
    """Deterministic weekday calendar; injected holiday sets can override it later."""
    candidate = reference.date()
    # Before the Vietnamese close, the prior completed session is the anchor.
    if reference.hour < 15:
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def freshness_envelope(*, domain: str, as_of_date: Any, generated_at: Any,
                       source: str | None, reference_at: datetime,
                       completeness: str | None = None,
                       dependency: dict[str, Any] | None = None) -> dict[str, Any]:
    rule = RULES[domain]
    ref = parse_timestamp(reference_at)
    if ref is None:
        raise ValueError("reference_at must be an ISO timestamp")
    observed = parse_timestamp(as_of_date)
    generated = parse_timestamp(generated_at)
    envelope = {
        "generated_at": generated.isoformat() if generated else None,
        "as_of_date": observed.date().isoformat() if observed else None,
        "source": source or None,
        "freshness_status": "unknown",
        "expected_update_frequency": f"{rule.cadence_days}d",
        "stale_reason": None,
        "is_actionable": False,
    }
    if observed is None:
        envelope.update(freshness_status="missing" if as_of_date is None else "unknown",
                        stale_reason="source_timestamp_missing_or_malformed")
        return envelope
    if generated is None:
        envelope.update(stale_reason="source_generation_timestamp_missing_or_malformed")
        return envelope
    if rule.market_days:
        expected = latest_completed_market_day(ref)
        age = (expected - observed.date()).days
    else:
        age = (ref.date() - observed.date()).days
    if rule.historical:
        # Reporting periods are evidence, not a promise of continuously current values.
        status = "historical" if age >= 0 else "unknown"
    elif age <= rule.cadence_days:
        status = "current"
    elif age <= rule.cadence_days + rule.grace_days:
        status = "expiring"
    else:
        status = "stale"
    reason = None if status == "current" else (
        "reporting_period_historical" if status == "historical" else f"source_age_{max(age, 0)}d_exceeds_{rule.grace_days}d_grace"
    )
    dependency_status = (dependency or {}).get("freshness_status")
    complete = completeness in {"complete", "available", None} and not (rule.requires_complete and completeness not in {"complete", "available"})
    actionable = status == "current" and complete and dependency_status in {None, "current"}
    if rule.requires_complete and not complete:
        reason = reason or "coverage_or_completeness_not_qualified"
    if dependency_status not in {None, "current"}:
        reason = reason or "underlying_dependency_not_current"
    envelope.update(freshness_status=status, stale_reason=reason, is_actionable=actionable)
    return envelope
