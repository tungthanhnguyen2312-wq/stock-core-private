"""Prospective raw-receipt temporal retention for A1 bitemporal projection.

This module records what acquisition actually knows.  It does not reinterpret HTTP/provider
metadata as official publication or grant historical price authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping, Protocol

from bitemporal_semantic_contract import (
    PublicationAuthorityTier, PublicationTime, TemporalPrecision, infer_precision,
    project_provider_temporal_metadata, resolve_knowledge_availability,
)


TEMPORAL_RETENTION_CONTRACT_VERSION = "provider_temporal_retention/v1"


def retention_fitness(envelope: Mapping[str, Any]) -> dict[str, str]:
    """Classify temporal usability without granting execution or price authority."""
    tier = str(envelope.get("publication_authority_tier") or "UNVERIFIED")
    precision = str(envelope.get("source_published_at_precision") or "UNKNOWN")
    first = aware_iso(envelope.get("first_observed_at"))
    if tier in {"OFFICIAL_ISSUER_IR_OR_EXCHANGE", "REGULATOR_DISCLOSURE"} and precision == "EXACT_DATETIME":
        status, reason = "QUALIFIED_SOURCE_PUBLICATION_EXACT", "qualified_official_publication_timestamp"
    elif tier in {"OFFICIAL_ISSUER_IR_OR_EXCHANGE", "REGULATOR_DISCLOSURE"} and precision == "DATE_ONLY":
        status, reason = "QUALIFIED_SOURCE_PUBLICATION_DATE_ONLY", "conservative_next_session_required"
    elif first:
        status, reason = "FIRST_OBSERVED_FORWARD_ONLY", "provider_or_unqualified_source_receipt"
    else:
        status, reason = "BLOCKED", "legacy_or_timezone_unknown_receipt"
    return {
        "temporal_fitness": status,
        "reason": reason,
        "raw_as_traded": "NOT_PROMOTED",
        "historical_price_pit": "BLOCKED",
        "same_close_execution": "NOT_ESTABLISHED",
    }


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemUTCClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def raw_content_identity(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def aware_iso(value: datetime | str | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def capture_raw_receipt(*, data: bytes | None, raw_received_at: datetime | str | None, source_identity: str | None,
                        provider_or_source: str, acquisition_method: str, source_published_at: str | None = None,
                        publication_authority_tier: str = "UNVERIFIED", provider_reported_date: str | None = None,
                        provider_record_update_at: str | None = None, provider_event_at: str | None = None,
                        http_headers: Mapping[str, Any] | None = None, content_type: str | None = None,
                        known_first_observed_at: str | None = None, raw_identity: str | None = None,
                        legacy_first_observed_unknown: bool = False,
                        warnings: list[str] | None = None) -> dict[str, Any]:
    """Create one serializable receipt envelope at the raw-byte/message boundary."""
    received = aware_iso(raw_received_at)
    if raw_received_at is not None and received is None:
        raise ValueError("RAW_RECEIPT_TIMESTAMP_TIMEZONE_REQUIRED")
    if data is not None and raw_identity is not None and raw_content_identity(data) != raw_identity:
        raise ValueError("RAW_IDENTITY_DOES_NOT_MATCH_BYTES")
    identity = raw_content_identity(data) if data is not None else raw_identity
    first_candidates = [item for item in (received, aware_iso(known_first_observed_at)) if item]
    first = None if legacy_first_observed_unknown else (min(first_candidates) if first_candidates else None)
    headers = {str(key).lower(): value for key, value in (http_headers or {}).items()}
    tier = str(publication_authority_tier)
    return {
        "temporal_retention_contract_version": TEMPORAL_RETENTION_CONTRACT_VERSION,
        "observation_identity": identity,
        "observation_identity_status": "OBSERVATION_IDENTITY_READY" if identity else "OBSERVATION_IDENTITY_UNKNOWN",
        "observation_identity_method": "RAW_BYTES_SHA256" if identity else None,
        "source_identity": source_identity,
        "provider_or_source": provider_or_source,
        "raw_received_at": received,
        "raw_received_timezone": "UTC" if received else "UNKNOWN",
        "first_observed_at": first,
        "first_observed_status": "RETAINED" if first else "LEGACY_UNKNOWN",
        "last_observed_at": received,
        "observation_count": 1,
        "source_published_at": source_published_at,
        "source_published_at_precision": infer_precision(source_published_at).value,
        "publication_authority_tier": tier,
        "provider_reported_date": provider_reported_date,
        "provider_record_update_at": provider_record_update_at,
        "provider_event_at": provider_event_at,
        "http_response_date": headers.get("date"),
        "http_last_modified": headers.get("last-modified"),
        "http_etag": headers.get("etag"),
        "content_type": content_type or headers.get("content-type"),
        "acquisition_method": acquisition_method,
        "warnings": sorted(set((warnings or []) + ["HTTP_METADATA_NOT_PUBLICATION_AUTHORITY"])),
    }


def capture_with_clock(*, clock: Clock, **kwargs: Any) -> dict[str, Any]:
    """Capture a receipt at one injected, testable UTC clock boundary."""
    return capture_raw_receipt(raw_received_at=clock.now(), **kwargs)


def merge_identical_reobservation(existing: Mapping[str, Any] | None, incoming: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve the earliest trustworthy receipt for immutable identical bytes."""
    if not existing:
        return dict(incoming)
    if existing.get("observation_identity") != incoming.get("observation_identity"):
        raise ValueError("IDENTICAL_REOBSERVATION_IDENTITY_MISMATCH")
    times = [aware_iso(value) for value in (existing.get("first_observed_at"), incoming.get("first_observed_at"))]
    earliest = min(value for value in times if value) if any(times) else None
    merged = dict(existing)
    merged["first_observed_at"] = earliest
    merged["first_observed_status"] = "RETAINED" if earliest else "LEGACY_UNKNOWN"
    merged["last_observed_at"] = incoming.get("last_observed_at") or existing.get("last_observed_at")
    merged["observation_count"] = int(existing.get("observation_count") or 1) + 1
    for key in ("provider_reported_date", "provider_record_update_at", "provider_event_at", "http_response_date", "http_last_modified", "http_etag", "content_type"):
        if incoming.get(key) is not None:
            merged[key] = incoming[key]
    merged["warnings"] = sorted(set((existing.get("warnings") or []) + (incoming.get("warnings") or [])))
    return merged


def project_retention_to_a1(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Project retained source/provider/receipt metadata without inference."""
    try:
        tier = PublicationAuthorityTier(str(envelope.get("publication_authority_tier") or "UNVERIFIED"))
    except ValueError:
        tier = PublicationAuthorityTier.UNVERIFIED
    try:
        precision = TemporalPrecision(str(envelope.get("source_published_at_precision") or "UNKNOWN"))
    except ValueError:
        precision = TemporalPrecision.UNKNOWN
    publication = PublicationTime(envelope.get("source_published_at"), precision, tier, envelope.get("source_identity"), "RETAINED_METADATA", "AWARE" if precision == TemporalPrecision.EXACT_DATETIME else "DATE_ONLY" if precision == TemporalPrecision.DATE_ONLY else "UNKNOWN")
    provider = project_provider_temporal_metadata(provider=str(envelope.get("provider_or_source") or ""), metadata={
        "ReportDate": envelope.get("provider_reported_date"), "LastUpdate": envelope.get("provider_record_update_at"),
        "lastUpdated": envelope.get("provider_event_at"),
    }, first_observed_at=envelope.get("first_observed_at"))
    knowledge = resolve_knowledge_availability(publication=publication, first_observed_at=envelope.get("first_observed_at"))
    return {"publication_time": publication.to_dict(), "provider_temporal_metadata": provider["provider_temporal_metadata"],
            "observation_time": {"first_observed_at": envelope.get("first_observed_at"), "first_observed_status": envelope.get("first_observed_status"),
                                  "observation_identity": envelope.get("observation_identity"), "observation_identity_status": envelope.get("observation_identity_status")},
            "knowledge_resolution": knowledge.to_dict(), "authority_boundaries": {"http_metadata_is_not_publication": True,
                "raw_as_traded": "NOT_PROMOTED", "historical_price_pit": "BLOCKED", "same_close_execution": "NOT_ESTABLISHED"},
            "retention_fitness": retention_fitness(envelope)}
