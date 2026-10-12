"""Fail-closed point-in-time bridge for qualified common-share identities."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

VERSION = "1.0.0"
SHARE_CHANGING_ACTIONS = {"stock_dividend", "bonus_share", "rights_issue", "stock_split"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> str:
    return "share-bridge-" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _date(value: Any, code: str) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(code) from exc


def _qualified_identity(value: Mapping[str, Any]) -> bool:
    return (
        isinstance(value.get("value"), int)
        and not isinstance(value.get("value"), bool)
        and value["value"] > 0
        and value.get("unit") == "shares"
        and value.get("share_class") == "common_outstanding"
        and value.get("identity_scope") == "issuer"
        and value.get("qualification") == "qualified"
        and bool(value.get("source_hash"))
        and bool(value.get("citation_id"))
    )


def resolve_share_transition(
    opening: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    *,
    target_date: str,
    coverage_through: str | None,
) -> dict[str, Any]:
    """Resolve a dated share chain without inferring lifecycle completion or coverage.

    A direct resulting-share count is mandatory for every share-changing event;
    ratios alone are not used to manufacture an outstanding-share identity.
    """
    target = _date(target_date, "target_date_invalid")
    blocked: list[dict[str, Any]] = []
    applied: list[dict[str, Any]] = []
    if not _qualified_identity(opening):
        return {
            "version": VERSION, "status": "blocked", "target_date": target,
            "latest_qualified_identity": None, "applied_events": [],
            "blocked_events": [{"event_id": None, "reason": "opening_identity_unqualified"}],
            "current_shares": {"value": None, "qualified": False, "reason": "opening_identity_unqualified"},
            "market_value_ready": False,
        }
    try:
        opening_date = _date(opening.get("effective_date"), "opening_effective_date_invalid")
    except ValueError:
        return {
            "version": VERSION, "status": "blocked", "target_date": target,
            "latest_qualified_identity": None, "applied_events": [],
            "blocked_events": [{"event_id": None, "reason": "opening_effective_date_invalid"}],
            "current_shares": {"value": None, "qualified": False,
                               "reason": "opening_effective_date_invalid"},
            "market_value_ready": False,
        }
    if opening_date > target:
        blocked.append({"event_id": None, "reason": "opening_identity_after_target"})

    unique: dict[str, Mapping[str, Any]] = {}
    conflicted_ids: set[str] = set()
    for event in events:
        event_id = str(event.get("event_id") or "")
        if not event_id:
            blocked.append({"event_id": None, "reason": "event_identity_missing"})
            continue
        existing = unique.get(event_id)
        if existing is not None and _canonical(existing) != _canonical(event):
            blocked.append({"event_id": event_id, "reason": "conflicting_duplicate_event"})
            conflicted_ids.add(event_id)
            continue
        unique[event_id] = event

    for event_id in conflicted_ids:
        unique.pop(event_id, None)

    current_value = int(opening["value"])
    current_date = opening_date
    current_lineage = [opening["citation_id"]]
    def event_key(item: Mapping[str, Any]) -> tuple[str, str]:
        try:
            effective = _date(item.get("effective_date"), "event_effective_date_invalid")
        except ValueError:
            effective = "9999-12-31"
        return effective, str(item.get("event_id"))

    for event in sorted(unique.values(), key=event_key):
        event_id = str(event["event_id"])
        try:
            effective = _date(event.get("effective_date"), "event_effective_date_invalid")
        except ValueError:
            blocked.append({"event_id": event_id, "reason": "event_effective_date_invalid"})
            continue
        if effective > target:
            continue
        if effective < current_date:
            blocked.append({"event_id": event_id, "reason": "event_precedes_resolved_identity"})
            continue
        if event.get("qualification") != "qualified" or not event.get("source_hash") or not event.get("citation_id"):
            blocked.append({"event_id": event_id, "reason": "event_evidence_unqualified"})
            continue
        action = event.get("action_type")
        if action == "cash_dividend":
            if event.get("resulting_shares") not in (None, current_value) or event.get("share_delta") not in (None, 0):
                blocked.append({"event_id": event_id, "reason": "cash_dividend_changes_share_count"})
                continue
            applied.append({"event_id": event_id, "action_type": action, "effective_date": effective,
                            "opening_shares": current_value, "resulting_shares": current_value,
                            "citation_id": event["citation_id"], "source_hash": event["source_hash"]})
            current_date = effective
            current_lineage.append(event["citation_id"])
            continue
        if action not in SHARE_CHANGING_ACTIONS:
            blocked.append({"event_id": event_id, "reason": "unsupported_share_action"})
            continue
        if event.get("lifecycle") != "completed":
            blocked.append({"event_id": event_id, "reason": "share_action_completion_unqualified"})
            continue
        if (
            event.get("resulting_identity_type") != "common_outstanding_shares"
            or event.get("unit") != "shares"
            or event.get("identity_scope") != "issuer"
        ):
            blocked.append({"event_id": event_id, "reason": "resulting_share_identity_unqualified"})
            continue
        resulting = event.get("resulting_shares")
        if not isinstance(resulting, int) or isinstance(resulting, bool) or resulting <= 0:
            blocked.append({"event_id": event_id, "reason": "direct_resulting_share_identity_missing"})
            continue
        if event.get("opening_shares") not in (None, current_value):
            blocked.append({"event_id": event_id, "reason": "event_opening_share_conflict"})
            continue
        applied.append({"event_id": event_id, "action_type": action, "effective_date": effective,
                        "opening_shares": current_value, "resulting_shares": resulting,
                        "ratio": event.get("ratio"), "citation_id": event["citation_id"],
                        "source_hash": event["source_hash"]})
        current_value, current_date = resulting, effective
        current_lineage.append(event["citation_id"])

    latest = {
        "value": current_value, "effective_date": current_date, "unit": "shares",
        "share_class": "common_outstanding", "identity_type": "latest_qualified_historical_shares_outstanding",
        "citation_ids": current_lineage,
    }
    latest["record_id"] = _identity(latest)
    coverage = None
    if coverage_through is not None:
        try:
            coverage = _date(coverage_through, "coverage_date_invalid")
        except ValueError:
            blocked.append({"event_id": None, "reason": "coverage_date_invalid"})
    blocking_before_target = bool(blocked)
    current_qualified = coverage is not None and coverage >= target and not blocking_before_target
    current_reason = "qualified_through_target" if current_qualified else (
        "transition_conflict_or_incomplete" if blocking_before_target else "coverage_through_target_not_proven"
    )
    return {
        "version": VERSION,
        "status": "current_qualified" if current_qualified else "latest_historical_only",
        "target_date": target,
        "coverage_through": coverage,
        "latest_qualified_identity": latest,
        "applied_events": applied,
        "blocked_events": blocked,
        "current_shares": {"value": current_value if current_qualified else None,
                           "qualified": current_qualified, "reason": current_reason},
        "market_value_ready": False,
    }
