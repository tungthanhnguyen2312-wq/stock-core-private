"""Deterministic catalyst semantics over governed current-event contracts.

This is the sole compatibility boundary between the canonical Daily event input and the
opportunity/thesis consumers.  ``current_official_event_context/v1`` is the canonical Daily
contract and owns ``event_state``; ``current_corporate_event_context/v1`` is an older normalized
context that owns ``event_status``.  The fields are not aliases and are interpreted only under
their declared contract versions.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

OFFICIAL_CONTRACT = "current_official_event_context/v1"
CORPORATE_CONTRACT = "current_corporate_event_context/v1"
METHOD_VERSION = "current_event_catalyst_classification/v1"

POSITIVE_CATALYST = "POSITIVE_CATALYST"
NEGATIVE_CATALYST = "NEGATIVE_CATALYST"
NEUTRAL_INFORMATION = "NEUTRAL_INFORMATION"
UNRESOLVED = "UNRESOLVED"
INELIGIBLE = "INELIGIBLE"

_OFFICIAL_CURRENT_STATES = frozenset({"UPCOMING", "EX_DATE_TODAY", "RECENT"})
_OFFICIAL_STATES = _OFFICIAL_CURRENT_STATES | frozenset({"PAST", "DATE_INCOMPLETE", "UNKNOWN"})
_CORPORATE_STATES = frozenset({
    "CONFIRMED_UPCOMING", "CONFIRMED_RECENT", "EXECUTED", "PLANNED_NOT_EXECUTED",
    "CANCELLED", "TEMPORAL_DETAILS_INCOMPLETE", "CONFLICTING_EVIDENCE", "DATA_LIMITED",
})
_ADVERSE_CORPORATE_STATES = frozenset({"CANCELLED", "CONFLICTING_EVIDENCE"})
_PRICE_SHARE_TYPES = frozenset({"CASH_DIVIDEND", "STOCK_DIVIDEND", "BONUS", "RIGHTS"})


def _source_event_identity(event: Mapping[str, Any]) -> str | None:
    for key in ("event_id", "source_record_identity", "source_event_id", "source_identity"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _temporal_status(event: Mapping[str, Any], state: str | None) -> str:
    if state in _OFFICIAL_CURRENT_STATES or state in {"CONFIRMED_UPCOMING", "CONFIRMED_RECENT"}:
        return "CURRENT_OR_RECENT_PER_SOURCE_CONTRACT"
    if state == "PAST":
        return "PAST_PER_SOURCE_CONTRACT"
    if state == "EXECUTED":
        return "EXECUTED_PER_SOURCE_CONTRACT"
    if state in {"DATE_INCOMPLETE", "UNKNOWN", "TEMPORAL_DETAILS_INCOMPLETE", "DATA_LIMITED"}:
        return "TEMPORAL_FITNESS_UNRESOLVED"
    if state == "PLANNED_NOT_EXECUTED":
        return "PLANNED_NOT_EXECUTED"
    if state in _ADVERSE_CORPORATE_STATES:
        return "SUPERSEDED_OR_CONFLICTING_PER_SOURCE_CONTRACT"
    return "UNAVAILABLE"


def _base(event: Mapping[str, Any], *, classification: str, state: str | None, reason_codes: list[str]) -> dict[str, Any]:
    event_type = event.get("event_type")
    return {
        "eligible": classification == POSITIVE_CATALYST,
        "catalyst_class": classification,
        "source_event_identity": _source_event_identity(event),
        "event_type": event_type,
        "event_state": state,
        "temporal_status": _temporal_status(event, state),
        "fitness": event.get("qualification") or event.get("evidence_tier") or "UNSPECIFIED",
        "reason_codes": reason_codes,
        "method_identity": METHOD_VERSION,
        "known_at": event.get("known_at") or event.get("published_at") or event.get("official_observed_at"),
        "event_date": event.get("ex_date") or event.get("effective_date") or event.get("execution_date"),
        "source_identity": event.get("source_identity") or event.get("source_record_identity"),
    }


def classify_event(event: Mapping[str, Any], *, contract_version: str | None) -> dict[str, Any]:
    """Classify one event without inferring dates, execution, or source semantics."""
    if contract_version == OFFICIAL_CONTRACT:
        state = event.get("event_state")
        if state not in _OFFICIAL_STATES:
            return _base(event, classification=UNRESOLVED, state=state, reason_codes=["UNRECOGNIZED_EVENT_STATE"])
        event_type = event.get("event_type")
        materiality = event.get("materiality_status")
        qualification = event.get("qualification")
        if state in _OFFICIAL_CURRENT_STATES:
            if event_type in _PRICE_SHARE_TYPES and materiality == "PRICE_SHARE_AFFECTING" and qualification == "EX_DATE_OFFICIAL_QUALIFIED":
                return _base(event, classification=POSITIVE_CATALYST, state=state, reason_codes=["CURRENT_QUALIFIED_PRICE_SHARE_EVENT"])
            if event_type == "AGM" or materiality == "INFORMATIONAL_GOVERNANCE":
                return _base(event, classification=NEUTRAL_INFORMATION, state=state, reason_codes=["INFORMATIONAL_GOVERNANCE_EVENT"])
            return _base(event, classification=INELIGIBLE, state=state, reason_codes=["CURRENT_EVENT_NOT_QUALIFIED_PRICE_SHARE_EVIDENCE"])
        if state == "PAST":
            return _base(event, classification=INELIGIBLE, state=state, reason_codes=["PAST_EVENT_NOT_CURRENT_CATALYST"])
        return _base(event, classification=UNRESOLVED, state=state, reason_codes=["TEMPORAL_OR_EVENT_STATE_UNRESOLVED"])

    if contract_version == CORPORATE_CONTRACT:
        state = event.get("event_status")
        if state not in _CORPORATE_STATES:
            return _base(event, classification=UNRESOLVED, state=state, reason_codes=["UNRECOGNIZED_EVENT_STATE"])
        if state in _ADVERSE_CORPORATE_STATES:
            return _base(event, classification=NEGATIVE_CATALYST, state=state, reason_codes=["ADVERSE_OR_SUPERSEDED_EVENT_STATE"])
        if state in {"CONFIRMED_UPCOMING", "CONFIRMED_RECENT"}:
            if event.get("event_type") in _PRICE_SHARE_TYPES:
                return _base(event, classification=POSITIVE_CATALYST, state=state, reason_codes=["LEGACY_CONFIRMED_PRICE_SHARE_EVENT"])
            return _base(event, classification=NEUTRAL_INFORMATION, state=state, reason_codes=["LEGACY_CONFIRMED_NON_PRICE_SHARE_EVENT"])
        if state == "PLANNED_NOT_EXECUTED":
            return _base(event, classification=UNRESOLVED, state=state, reason_codes=["PLANNED_NOT_EXECUTED"])
        return _base(event, classification=INELIGIBLE, state=state, reason_codes=["NON_CURRENT_OR_DATA_LIMITED_EVENT"])

    return _base(event, classification=UNRESOLVED, state=None, reason_codes=["UNSUPPORTED_EVENT_CONTRACT"])


def classify_events(events: Sequence[Mapping[str, Any]] | None, *, contract_version: str | None) -> list[dict[str, Any]]:
    """Return deterministic, identity-deduplicated classifications for one ticker's events."""
    by_identity: dict[str, Mapping[str, Any]] = {}
    anonymous: list[Mapping[str, Any]] = []
    for event in events or []:
        if not isinstance(event, Mapping):
            continue
        identity = _source_event_identity(event)
        if identity is None:
            anonymous.append(event)
        else:
            by_identity.setdefault(identity, event)
    ordered = [by_identity[key] for key in sorted(by_identity)] + sorted(
        anonymous, key=lambda item: (str(item.get("event_type") or ""), str(item.get("ex_date") or "")),
    )
    return [classify_event(event, contract_version=contract_version) for event in ordered]
