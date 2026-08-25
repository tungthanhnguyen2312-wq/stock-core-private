"""Current-research corporate event context over retained official event evidence.

This is a projection of ``current_official_event_context`` plus the three retained
issuer/VSDC corporate-action chains already used by corporate intelligence.  It does
not crawl events, infer ex-dates or execution dates, enable EVENT_DRIVEN, or claim
price impact.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import current_official_event_context as official_event_module
import current_official_market_universe as official_universe_module
from market_wide_current_corporate_intelligence import load_retained_events
from market_wide_current_valuation_input_scaleout import official_research_universe_tickers


CONTRACT_VERSION = "current_corporate_event_context/v1"
ARTIFACT_TYPE = "CURRENT_CORPORATE_EVENT_CONTEXT"
MILESTONE = "CURRENT_CORPORATE_EVENT_CONTEXT_V1"
RECENT_WINDOW_DAYS = 30

CONFIRMED_UPCOMING = "CONFIRMED_UPCOMING"
CONFIRMED_RECENT = "CONFIRMED_RECENT"
EXECUTED = "EXECUTED"
PLANNED_NOT_EXECUTED = "PLANNED_NOT_EXECUTED"
CANCELLED = "CANCELLED"
TEMPORAL_DETAILS_INCOMPLETE = "TEMPORAL_DETAILS_INCOMPLETE"
CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
DATA_LIMITED = "DATA_LIMITED"
EVENT_STATUSES = (
    CONFIRMED_UPCOMING, CONFIRMED_RECENT, EXECUTED, PLANNED_NOT_EXECUTED,
    CANCELLED, TEMPORAL_DETAILS_INCOMPLETE, CONFLICTING_EVIDENCE, DATA_LIMITED,
)
PLANNED_STATUSES = frozenset({"PLANNED", "PROPOSED", "APPROVED", "ANNOUNCED"})
FORBIDDEN_USES = (
    "EVENT_DRIVEN_eligibility", "price_impact", "probability", "target",
    "research_priority", "entry_action", "recommendation", "sizing",
)


class CurrentCorporateEventContextError(ValueError):
    """A retained input did not meet this context's exact research contract."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact))
    payload.pop("artifact_sha256", None)
    payload.pop("artifact_identity", None)
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"current_corporate_event_context:{digest}"}


def replay(artifact: Mapping[str, Any]) -> dict[str, str]:
    identity = content_identity(artifact)
    if identity["artifact_sha256"] != artifact.get("artifact_sha256"):
        raise CurrentCorporateEventContextError("CORPORATE_EVENT_CONTEXT_IDENTITY_MISMATCH")
    events = [event for row in (artifact.get("records") or {}).values() for event in row.get("events") or []]
    if any(event.get("ex_date") and event.get("record_date") and event["ex_date"] == event["record_date"]
           and "RECORD_DATE_USED_AS_EX_DATE" in (event.get("warnings") or []) for event in events):
        raise CurrentCorporateEventContextError("RECORD_DATE_COLLAPSED_TO_EX_DATE")
    return identity


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _verify_universe(artifact: Mapping[str, Any]) -> list[str]:
    try:
        official_universe_module._verify(artifact, "CURRENT_OFFICIAL_MARKET_UNIVERSE")
    except Exception as exc:
        raise CurrentCorporateEventContextError("CURRENT_OFFICIAL_UNIVERSE_IDENTITY_MISMATCH") from exc
    tickers = official_research_universe_tickers(artifact)
    if not tickers:
        raise CurrentCorporateEventContextError("OFFICIAL_RESEARCH_UNIVERSE_EMPTY")
    return tickers


def _verify_event_context(artifact: Mapping[str, Any]) -> None:
    try:
        official_event_module._verify(artifact, "CURRENT_OFFICIAL_EVENT_CONTEXT")
    except Exception as exc:
        raise CurrentCorporateEventContextError("CURRENT_OFFICIAL_EVENT_CONTEXT_IDENTITY_MISMATCH") from exc
    if artifact.get("contract_version") != official_event_module.CONTRACT_VERSION:
        raise CurrentCorporateEventContextError("CURRENT_OFFICIAL_EVENT_CONTRACT_UNSUPPORTED")


def known_at_ok(*, known_at: str | None, published_at: str | None, as_of: date) -> bool:
    """Exclude look-ahead. Missing known_at is not inferred to be as-of."""
    boundary = _parse_date(known_at) or _parse_date(published_at)
    if boundary is None:
        return True
    return boundary <= as_of


def classify_event_status(event: Mapping[str, Any], *, as_of: date) -> tuple[str, str]:
    lifecycle = str(event.get("status") or event.get("lifecycle_status") or "")
    if lifecycle == "CANCELLED" or event.get("event_state") == "CANCELLED":
        return CANCELLED, "SOURCE_STATUS_CANCELLED"
    if lifecycle in PLANNED_STATUSES and not event.get("execution_date"):
        return PLANNED_NOT_EXECUTED, "PLANNED_OR_APPROVED_WITHOUT_EXECUTION_EVIDENCE"
    ex_date = _parse_date(event.get("ex_date"))
    execution = _parse_date(event.get("execution_date"))
    record = _parse_date(event.get("record_date"))
    if lifecycle == "EXECUTED":
        return EXECUTED, "SOURCE_STATUS_EXECUTED_WITH_RETAINED_EXECUTION_EVIDENCE"
    if execution is not None and execution <= as_of:
        return EXECUTED, "EXECUTION_DATE_ON_OR_BEFORE_AS_OF"
    if execution is not None and execution > as_of:
        return CONFIRMED_UPCOMING, "EXECUTION_DATE_AFTER_AS_OF"
    if ex_date is None:
        if record is not None:
            return TEMPORAL_DETAILS_INCOMPLETE, "RECORD_DATE_PRESENT_EX_DATE_ABSENT_NOT_INFERRED"
        return DATA_LIMITED, "NO_QUALIFIED_EX_RECORD_OR_EXECUTION_DATE"
    delta = (ex_date - as_of).days
    if delta >= 0:
        return CONFIRMED_UPCOMING, "EX_DATE_ON_OR_AFTER_AS_OF"
    if delta >= -RECENT_WINDOW_DAYS:
        return CONFIRMED_RECENT, "EX_DATE_WITHIN_RECENT_WINDOW"
    return DATA_LIMITED, "PAST_EX_DATE_WITHOUT_EXECUTION_EVIDENCE"


def _date_conflict(left: Mapping[str, Any], right: Mapping[str, Any]) -> list[str]:
    conflicts = []
    for field in ("record_date", "ex_date", "execution_date", "effective_date"):
        a, b = left.get(field), right.get(field)
        if a and b and a != b:
            conflicts.append(field)
    return conflicts


def _merge_identity(event: Mapping[str, Any]) -> tuple[str, str, str, str, str] | None:
    ticker = str(event.get("ticker") or "")
    event_type = str(event.get("event_type") or "")
    record_date = event.get("record_date") or ""
    ex_date = event.get("ex_date") or ""
    execution = event.get("execution_date") or ""
    if not ticker or not event_type:
        return None
    if not (record_date or ex_date or execution):
        return None
    return ticker, event_type, str(record_date), str(ex_date), str(execution)


def deduplicate_events(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Merge only exact ticker/type/date identity across different source families."""
    grouped: dict[tuple[str, str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    unmatched: list[Mapping[str, Any]] = []
    for event in events:
        key = _merge_identity(event)
        source_family = str(event.get("source") or event.get("source_authority") or "")
        if key is None:
            unmatched.append(dict(event))
            continue
        grouped[key].append(event)
    output: list[dict[str, Any]] = []
    for key, cluster in grouped.items():
        families = {str(item.get("source") or item.get("source_authority") or "") for item in cluster}
        if len(cluster) == 1 or (len(families) == 1 and len(cluster) > 1):
            output.extend(dict(item) for item in cluster)
            continue
        conflicts = []
        for left, right in zip(cluster, cluster[1:]):
            conflicts.extend(_date_conflict(left, right))
        merged = dict(cluster[0])
        merged["source_identities"] = sorted({
            str(item.get("source_identity") or item.get("evidence_identity") or item.get("event_id"))
            for item in cluster
        })
        merged["supporting_evidence"] = [
            {
                "event_id": item.get("event_id"),
                "source": item.get("source") or item.get("source_authority"),
                "source_identity": item.get("source_identity") or item.get("evidence_identity"),
            }
            for item in cluster
        ]
        if conflicts:
            merged["event_status"] = CONFLICTING_EVIDENCE
            merged["conflicts"] = sorted(set(conflicts))
            merged["warnings"] = list(merged.get("warnings") or []) + ["CONFLICTING_QUALIFIED_DATES_NOT_RESOLVED_BY_PREFERENCE"]
        output.append(merged)
    output.extend(unmatched)
    by_record: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in output:
        if event.get("record_date"):
            by_record[(str(event["ticker"]), str(event.get("event_type")), str(event["record_date"]))].append(event)
    for cluster in by_record.values():
        ex_dates = {item.get("ex_date") for item in cluster if item.get("ex_date")}
        if len(ex_dates) > 1:
            for item in cluster:
                item["event_status"] = CONFLICTING_EVIDENCE
                item["conflicts"] = sorted(set(item.get("conflicts") or []) | {"ex_date"})
                item["warnings"] = list(item.get("warnings") or []) + ["CONFLICTING_QUALIFIED_DATES_NOT_RESOLVED_BY_PREFERENCE"]
    return output


def _normalize_official_event(raw: Mapping[str, Any], *, as_of: date) -> dict[str, Any] | None:
    published = raw.get("published_at")
    known = raw.get("known_at") or published
    if not known_at_ok(known_at=known, published_at=published, as_of=as_of):
        return None
    status, reason = classify_event_status(raw, as_of=as_of)
    qualification = str(raw.get("qualification") or "")
    materiality = str(raw.get("materiality_status") or "")
    event = {
        "ticker": raw["ticker"],
        "event_type": raw.get("event_type"),
        "event_status": status,
        "status_reason": reason,
        "evidence_tier": "OFFICIAL_QUALIFIED" if qualification == "EX_DATE_OFFICIAL_QUALIFIED" else "OFFICIAL_SOURCE_TEMPORALLY_INCOMPLETE",
        "source": raw.get("source"),
        "source_identities": [raw.get("source_identity") or raw.get("event_id")],
        "supporting_evidence": [{"event_id": raw.get("event_id"), "source": raw.get("source"),
                                 "source_identity": raw.get("source_identity")}],
        "published_at": published,
        "observed_at": raw.get("official_observed_at"),
        "known_at": known,
        "announcement_date": published,
        "record_date": raw.get("record_date"),
        "ex_date": raw.get("ex_date"),
        "effective_date": None,
        "execution_date": raw.get("execution_date"),
        "temporal_completeness": "COMPLETE" if raw.get("ex_date") else "INCOMPLETE",
        "conflicts": [],
        "warnings": list(raw.get("warnings") or []) + (
            ["RECORD_DATE_IS_NOT_EX_DATE"] if raw.get("record_date") and not raw.get("ex_date") else []
        ),
        "blockers": [] if raw.get("ex_date") else ["EX_DATE_NOT_INFERRED"],
        "materiality_status": materiality,
        "qualification": qualification,
        "source_event_id": raw.get("event_id"),
        "source_record_identity": raw.get("source_record_identity"),
        "insufficient_for_event_driven": not (
            materiality == "PRICE_SHARE_AFFECTING"
            and status in {CONFIRMED_UPCOMING, CONFIRMED_RECENT}
            and qualification == "EX_DATE_OFFICIAL_QUALIFIED"
        ),
        "allowed_uses": ["current_research_context"],
        "prohibited_uses": list(FORBIDDEN_USES),
    }
    seed = {key: value for key, value in event.items() if key != "event_id"}
    event["event_id"] = "current_corporate_event:" + hashlib.sha256(_canonical(seed)).hexdigest()
    return event


def _normalize_supplemental(raw: Mapping[str, Any], *, as_of: date) -> dict[str, Any] | None:
    published = raw.get("announcement_date") or raw.get("published_at")
    known = raw.get("known_at") or published
    if not known_at_ok(known_at=known, published_at=published, as_of=as_of):
        return None
    mapped = {
        "ticker": raw["ticker"],
        "event_type": raw.get("event_type"),
        "status": raw.get("status"),
        "lifecycle_status": raw.get("status"),
        "ex_date": raw.get("ex_date"),
        "record_date": raw.get("record_date"),
        "execution_date": raw.get("execution_date") or raw.get("payment_date"),
        "effective_date": raw.get("effective_date"),
    }
    status, reason = classify_event_status(mapped, as_of=as_of)
    if raw.get("status") == "EXECUTED":
        status, reason = EXECUTED, "SOURCE_STATUS_EXECUTED_WITH_RETAINED_EXECUTION_EVIDENCE"
    warnings = list(raw.get("limitations") or [])
    if raw.get("record_date") and not raw.get("ex_date"):
        warnings.append("RECORD_DATE_IS_NOT_EX_DATE")
    event = {
        "ticker": raw["ticker"],
        "event_type": raw.get("event_type"),
        "event_status": status,
        "status_reason": reason,
        "evidence_tier": raw.get("authority_tier") or "OFFICIAL_QUALIFIED",
        "source": raw.get("source_authority"),
        "source_identities": [raw.get("evidence_identity") or raw.get("event_id")],
        "supporting_evidence": [{"event_id": raw.get("event_id"), "source": raw.get("source_authority"),
                                 "source_identity": raw.get("evidence_identity")}],
        "published_at": published,
        "observed_at": raw.get("retrieved_at"),
        "known_at": known,
        "announcement_date": raw.get("announcement_date") or published,
        "record_date": raw.get("record_date"),
        "ex_date": raw.get("ex_date"),
        "effective_date": raw.get("effective_date"),
        "execution_date": raw.get("execution_date") or raw.get("payment_date") or raw.get("effective_date"),
        "temporal_completeness": "INCOMPLETE" if not raw.get("ex_date") else "COMPLETE",
        "conflicts": [],
        "warnings": warnings,
        "blockers": [] if raw.get("ex_date") else ["EX_DATE_NOT_INFERRED"],
        "materiality_status": raw.get("materiality_status") or "UNKNOWN_APPLICABILITY",
        "qualification": raw.get("status_basis"),
        "source_event_id": raw.get("event_id"),
        "source_record_identity": raw.get("evidence_identity"),
        "insufficient_for_event_driven": True,
        "allowed_uses": ["current_research_context"],
        "prohibited_uses": list(FORBIDDEN_USES),
    }
    if status == EXECUTED and not event.get("execution_date"):
        event["warnings"] = event["warnings"] + ["EXECUTED_STATUS_RETAINED_WITHOUT_DATED_EXECUTION_FIELD"]
    seed = {key: value for key, value in event.items() if key != "event_id"}
    event["event_id"] = "current_corporate_event:" + hashlib.sha256(_canonical(seed)).hexdigest()
    return event


def _ticker_summary(ticker: str, session: str, events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    upcoming = sum(event["event_status"] == CONFIRMED_UPCOMING for event in events)
    recent = sum(event["event_status"] == CONFIRMED_RECENT for event in events)
    executed = sum(event["event_status"] == EXECUTED for event in events)
    planned = sum(event["event_status"] == PLANNED_NOT_EXECUTED for event in events)
    conflicting = sum(event["event_status"] == CONFLICTING_EVIDENCE for event in events)
    incomplete = sum(event["event_status"] == TEMPORAL_DETAILS_INCOMPLETE for event in events)
    limited = sum(event["event_status"] == DATA_LIMITED for event in events)
    qualified = sum(event.get("evidence_tier") == "OFFICIAL_QUALIFIED" for event in events)
    return {
        "ticker": ticker,
        "research_session": session,
        "events": list(events),
        "confirmed_upcoming_count": upcoming,
        "recent_confirmed_count": recent,
        "executed_count": executed,
        "recent_confirmed_or_executed_count": recent + executed,
        "planned_unresolved_count": planned + incomplete,
        "conflicting_count": conflicting,
        "data_limited_count": limited,
        "temporal_incomplete_count": incomplete,
        "qualified_event_count": qualified,
        "has_qualified_event": qualified > 0 or any(event["event_status"] not in {DATA_LIMITED} for event in events),
        "does_not_enable_event_driven": True,
        "allowed_uses": ["current_research_context"],
        "prohibited_uses": list(FORBIDDEN_USES),
    }


def build_artifact(
    *,
    official_universe: Mapping[str, Any],
    official_event_context: Mapping[str, Any],
    supplemental_events: Sequence[Mapping[str, Any]] | None = None,
    research_session: str | None = None,
) -> dict[str, Any]:
    tickers = _verify_universe(official_universe)
    _verify_event_context(official_event_context)
    session = research_session or str(official_event_context.get("research_session") or "")
    if not session:
        raise CurrentCorporateEventContextError("RESEARCH_SESSION_REQUIRED")
    as_of = date.fromisoformat(session)
    if official_event_context.get("research_session") != session:
        raise CurrentCorporateEventContextError("EVENT_CONTEXT_SESSION_MISMATCH")
    normalized: list[dict[str, Any]] = []
    for raw in official_event_context.get("all_current_universe_event_records") or []:
        if raw.get("ticker") not in tickers:
            continue
        item = _normalize_official_event(raw, as_of=as_of)
        if item is not None:
            normalized.append(item)
    for raw in supplemental_events or []:
        if raw.get("ticker") not in tickers:
            continue
        item = _normalize_supplemental(raw, as_of=as_of)
        if item is not None:
            normalized.append(item)
    normalized = deduplicate_events(normalized)
    by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in normalized:
        by_ticker[event["ticker"]].append(event)
    records = {
        ticker: _ticker_summary(ticker, session, sorted(by_ticker.get(ticker, []), key=lambda item: (
            item.get("ex_date") or item.get("record_date") or "", item["event_id"],
        )))
        for ticker in tickers
    }
    events = [event for row in records.values() for event in row["events"]]
    coverage = {
        "universe_denominator": len(records),
        "tickers_with_qualified_event": sum(1 for row in records.values() if row["has_qualified_event"] and row["events"]),
        "tickers_with_no_qualified_event": sum(1 for row in records.values() if not row["events"]),
        "deduplicated_event_count": len(events),
        "event_type_distribution": dict(sorted(Counter(event["event_type"] for event in events).items())),
        "status_distribution": dict(sorted(Counter(event["event_status"] for event in events).items())),
        "evidence_tier_distribution": dict(sorted(Counter(event["evidence_tier"] for event in events).items())),
        "temporal_completeness_distribution": dict(sorted(Counter(event["temporal_completeness"] for event in events).items())),
        "conflict_count": sum(event["event_status"] == CONFLICTING_EVIDENCE for event in events),
        "unresolved_planned_count": sum(event["event_status"] in {PLANNED_NOT_EXECUTED, TEMPORAL_DETAILS_INCOMPLETE} for event in events),
        "recent_window_days": RECENT_WINDOW_DAYS,
        "unexplained_count": 0,
        "denominator_reconciles": len(records) == len(tickers),
    }
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "milestone": MILESTONE,
        "research_mode": "CURRENT_RESEARCH_ONLY",
        "research_session": session,
        "source_artifact_identities": {
            "current_official_universe": official_universe.get("artifact_identity"),
            "current_official_event_context": official_event_context.get("artifact_identity"),
        },
        "records": records,
        "coverage": coverage,
        "event_status_vocabulary": list(EVENT_STATUSES),
        "windows": {
            "confirmed_upcoming": "ex_date on or after research as-of",
            "confirmed_recent": f"ex_date within the prior {RECENT_WINDOW_DAYS} calendar days",
            "planned_unresolved": "approved/planned without execution evidence, or record-date without ex-date",
        },
        "blocked_outputs": {
            "strategy_eligibility": "NOT_MODIFIED",
            "event_driven_strategy": "NOT_ENABLED_BY_THIS_CONTEXT",
            "research_priority": "NOT_MODIFIED",
            "entry_action": "NOT_MODIFIED",
        },
        "authority_boundary": {
            "is_actionable": False,
            "corporate_event_context_is_not_event_driven_eligibility": True,
            "corporate_event_context_is_not_price_impact": True,
            "corporate_event_context_is_not_probability": True,
            "corporate_event_context_is_not_target": True,
            "corporate_event_context_is_not_research_priority": True,
            "corporate_event_context_is_not_entry_action": True,
            "corporate_event_context_is_not_recommendation": True,
            "corporate_event_context_is_not_sizing": True,
            "record_date_is_not_ex_date": True,
            "planned_is_not_executed": True,
            "announcement_is_not_execution": True,
            "ex_date_not_inferred": True,
            "execution_date_not_inferred": True,
            "resulting_shares_not_inferred": True,
            "no_look_ahead": True,
            "no_synthetic_price_adjustment": True,
            "raw_as_traded": "NOT_PROMOTED",
            "pit": "BLOCKED",
            "backtesting": "BLOCKED",
            "frozen_sessions_not_regenerated": ["2026-08-21", "2026-08-24"],
        },
        "prohibited_uses": list(FORBIDDEN_USES),
    }
    artifact.update(content_identity(artifact))
    return artifact


def load_supplemental_retained_events(root: Path, session: str) -> list[dict[str, Any]]:
    """Issuer/VSDC chains already used by corporate intelligence; adapter events are not re-imported."""
    return load_retained_events(root, session, official_event_context=None)
