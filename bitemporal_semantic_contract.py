"""Canonical, fail-closed bitemporal semantics for Stock Lookup research.

This contract separates domain validity, disclosure/provider time, Stock Lookup receipt,
and later pipeline work.  It is an architectural semantic layer, not historical price-PIT
or execution authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from enum import Enum
import hashlib
import json
from typing import Any, Iterable, Mapping


CONTRACT_VERSION = "bitemporal_semantic_contract/v1"
OPERATING_TIMEZONE = "Asia/Ho_Chi_Minh"
EOD_RESEARCH_CUTOFF = time(18, 0)
EOD_CUTOFF_PROVENANCE = "OWNER_OPERATING_CONVENTION_V1_REUSED_COMPLETED_MARKET_SESSION_GATE"


class _ValueEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - serialization uses .value
        return self.value


class TemporalPrecision(_ValueEnum):
    EXACT_DATETIME = "EXACT_DATETIME"
    DATE_ONLY = "DATE_ONLY"
    PARTIAL_DATE = "PARTIAL_DATE"
    UNKNOWN = "UNKNOWN"


class PublicationAuthorityTier(_ValueEnum):
    OFFICIAL_ISSUER_IR_OR_EXCHANGE = "OFFICIAL_ISSUER_IR_OR_EXCHANGE"
    REGULATOR_DISCLOSURE = "REGULATOR_DISCLOSURE"
    PROVIDER_REPORTED = "PROVIDER_REPORTED"
    UNVERIFIED = "UNVERIFIED"


class KnowledgeTimeStatus(_ValueEnum):
    KNOWLEDGE_RESOLVED_SOURCE_PUBLICATION = "KNOWLEDGE_RESOLVED_SOURCE_PUBLICATION"
    KNOWLEDGE_RESOLVED_SOURCE_PUBLICATION_DATE_ONLY = "KNOWLEDGE_RESOLVED_SOURCE_PUBLICATION_DATE_ONLY"
    KNOWLEDGE_RESOLVED_FIRST_OBSERVED_CONSERVATIVE = "KNOWLEDGE_RESOLVED_FIRST_OBSERVED_CONSERVATIVE"
    KNOWLEDGE_RESOLVED_DERIVED = "KNOWLEDGE_RESOLVED_DERIVED"
    KNOWLEDGE_UNKNOWN = "KNOWLEDGE_UNKNOWN"


class HistoricalReconstructionScope(_ValueEnum):
    FROM_QUALIFIED_SOURCE_PUBLICATION = "FROM_QUALIFIED_SOURCE_PUBLICATION"
    FROM_FIRST_OBSERVED_FORWARD_ONLY = "FROM_FIRST_OBSERVED_FORWARD_ONLY"
    FROM_REQUIRED_INPUT_BOUNDS = "FROM_REQUIRED_INPUT_BOUNDS"
    NONE = "NONE"


class EODResolutionRule(_ValueEnum):
    EXACT_TIMESTAMP_CUTOFF = "EXACT_TIMESTAMP_CUTOFF"
    DATE_ONLY_CONSERVATIVE_NEXT_SESSION = "DATE_ONLY_CONSERVATIVE_NEXT_SESSION"
    FIRST_OBSERVED_CONSERVATIVE = "FIRST_OBSERVED_CONSERVATIVE"
    DERIVED_REQUIRED_INPUT_MAX = "DERIVED_REQUIRED_INPUT_MAX"
    UNRESOLVED = "UNRESOLVED"


class ObservationIdentityStatus(_ValueEnum):
    OBSERVATION_IDENTITY_READY = "OBSERVATION_IDENTITY_READY"
    OBSERVATION_IDENTITY_DERIVED_NORMALIZED = "OBSERVATION_IDENTITY_DERIVED_NORMALIZED"
    OBSERVATION_IDENTITY_UNKNOWN = "OBSERVATION_IDENTITY_UNKNOWN"


class RevisionStatus(_ValueEnum):
    REVISION_IDENTITY_READY = "REVISION_IDENTITY_READY"
    REVISION_IDENTITY_PARTIAL = "REVISION_IDENTITY_PARTIAL"
    REVISION_HISTORY_UNKNOWN = "REVISION_HISTORY_UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class TemporalFitnessStatus(_ValueEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    VALID_TIME_INSUFFICIENT = "VALID_TIME_INSUFFICIENT"
    UNKNOWN = "UNKNOWN"


class ClosePriceExecutionEligibility(_ValueEnum):
    NOT_ESTABLISHED = "NOT_ESTABLISHED"


QUALIFIED_PUBLICATION_TIERS = {
    PublicationAuthorityTier.OFFICIAL_ISSUER_IR_OR_EXCHANGE,
    PublicationAuthorityTier.REGULATOR_DISCLOSURE,
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"bitemporal_semantic_contract:{digest}"}


def _enum_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_enum_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _enum_value(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class ValidTime:
    domain: str
    fitness_status: TemporalFitnessStatus
    reference_session: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    statement_scope: str | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _enum_value(asdict(self))


@dataclass(frozen=True)
class PublicationTime:
    source_published_at: str | None
    source_published_at_precision: TemporalPrecision
    publication_authority_tier: PublicationAuthorityTier
    source_identity: str | None
    qualification_status: str
    timezone_status: str

    def to_dict(self) -> dict[str, Any]:
        return _enum_value(asdict(self))


@dataclass(frozen=True)
class ProviderTemporalMetadata:
    provider_reported_date: str | None = None
    provider_record_update_time: str | None = None
    provider_event_time: str | None = None
    provider_time_precision: TemporalPrecision = TemporalPrecision.UNKNOWN
    timezone_status: str = "UNKNOWN"
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _enum_value(asdict(self))


@dataclass(frozen=True)
class ObservationTime:
    first_observed_at: str | None
    first_observed_status: str
    observation_identity: str | None
    observation_identity_status: ObservationIdentityStatus
    observation_identity_method: str | None

    def to_dict(self) -> dict[str, Any]:
        return _enum_value(asdict(self))


@dataclass(frozen=True)
class PipelineTime:
    processing_at: str | None = None
    parsed_at: str | None = None
    verified_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeResolution:
    knowledge_time_status: KnowledgeTimeStatus
    knowledge_available_at: str | None
    knowledge_available_research_session: str | None
    historical_reconstruction_scope: HistoricalReconstructionScope
    eod_resolution_rule: EODResolutionRule
    close_price_execution_eligibility: ClosePriceExecutionEligibility = ClosePriceExecutionEligibility.NOT_ESTABLISHED
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _enum_value(asdict(self))


@dataclass(frozen=True)
class RevisionMetadata:
    revision_status: RevisionStatus
    revision_identity: str | None = None
    supersedes_identity: str | None = None
    variant_index: int | None = None
    variant_disposition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _enum_value(asdict(self))


@dataclass(frozen=True)
class TemporalLineage:
    source_identity: str | None
    raw_identity: str | None
    provider_metadata: ProviderTemporalMetadata
    pipeline_time: PipelineTime

    def to_dict(self) -> dict[str, Any]:
        return {"source_identity": self.source_identity, "raw_identity": self.raw_identity,
                "provider_metadata": self.provider_metadata.to_dict(), "pipeline_time": self.pipeline_time.to_dict()}


@dataclass(frozen=True)
class TemporalEnvelope:
    valid_time: ValidTime
    publication_time: PublicationTime
    observation_time: ObservationTime
    knowledge_resolution: KnowledgeResolution
    revision_metadata: RevisionMetadata
    temporal_lineage: TemporalLineage
    authority_boundaries: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"contract_version": CONTRACT_VERSION, "valid_time": self.valid_time.to_dict(),
                "publication_time": self.publication_time.to_dict(), "observation_time": self.observation_time.to_dict(),
                "knowledge_resolution": self.knowledge_resolution.to_dict(), "revision_metadata": self.revision_metadata.to_dict(),
                "temporal_lineage": self.temporal_lineage.to_dict(), "authority_boundaries": dict(self.authority_boundaries)}


def _parse_date_only(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _parse_aware(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo is not None and result.utcoffset() is not None else None


def infer_precision(value: Any) -> TemporalPrecision:
    if _parse_date_only(value):
        return TemporalPrecision.DATE_ONLY
    if _parse_aware(value):
        return TemporalPrecision.EXACT_DATETIME
    if isinstance(value, str) and len(value) == 7 and value[4] == "-":
        return TemporalPrecision.PARTIAL_DATE
    return TemporalPrecision.UNKNOWN


def validate_valid_time(*, domain: str, reference_session: str | None = None, period_start: str | None = None,
                        period_end: str | None = None, event_type: str | None = None,
                        event_dates: Mapping[str, Any] | None = None, effective_from: str | None = None,
                        effective_to: str | None = None, statement_scope: str | None = None) -> ValidTime:
    if domain == "MARKET_OBSERVATION":
        return ValidTime(domain, TemporalFitnessStatus.READY if _parse_date_only(reference_session) else TemporalFitnessStatus.VALID_TIME_INSUFFICIENT,
                         reference_session=reference_session)
    if domain == "FINANCIAL_STOCK_FACT":
        return ValidTime(domain, TemporalFitnessStatus.READY if _parse_date_only(period_end) else TemporalFitnessStatus.VALID_TIME_INSUFFICIENT,
                         period_end=period_end, effective_from=effective_from, effective_to=effective_to, statement_scope=statement_scope)
    if domain == "FINANCIAL_FLOW_FACT":
        fitness = TemporalFitnessStatus.READY if _parse_date_only(period_start) and _parse_date_only(period_end) else (TemporalFitnessStatus.PARTIAL if _parse_date_only(period_end) else TemporalFitnessStatus.VALID_TIME_INSUFFICIENT)
        return ValidTime(domain, fitness, period_start=period_start if _parse_date_only(period_start) else None, period_end=period_end if _parse_date_only(period_end) else None, statement_scope=statement_scope)
    if domain == "CORPORATE_EVENT":
        qualified_dates = {key: value for key, value in (event_dates or {}).items() if _parse_date_only(value)}
        return ValidTime(domain, TemporalFitnessStatus.READY if event_type and qualified_dates else TemporalFitnessStatus.VALID_TIME_INSUFFICIENT,
                         effective_from=qualified_dates.get("effective_date") or qualified_dates.get("listing_effective_date"),
                         warnings=() if event_type and qualified_dates else ("EVENT_TYPE_AND_QUALIFIED_EVENT_DATE_REQUIRED",))
    if domain == "STATIC_PROFILE_FACT":
        return ValidTime(domain, TemporalFitnessStatus.READY, effective_from=effective_from, effective_to=effective_to)
    return ValidTime(domain, TemporalFitnessStatus.UNKNOWN, warnings=("UNKNOWN_VALID_TIME_DOMAIN",))


def classify_observation_identity(*, raw_identity: str | None = None, normalized_identity: str | None = None) -> ObservationTime:
    if raw_identity:
        return ObservationTime(None, "LEGACY_UNKNOWN", raw_identity, ObservationIdentityStatus.OBSERVATION_IDENTITY_READY, "IMMUTABLE_RETAINED_RAW_IDENTITY")
    if normalized_identity:
        return ObservationTime(None, "LEGACY_UNKNOWN", normalized_identity, ObservationIdentityStatus.OBSERVATION_IDENTITY_DERIVED_NORMALIZED, "NORMALIZED_RECORD_IDENTITY")
    return ObservationTime(None, "LEGACY_UNKNOWN", None, ObservationIdentityStatus.OBSERVATION_IDENTITY_UNKNOWN, None)


def revision_metadata(*, revision_identity: str | None = None, supersedes_identity: str | None = None,
                      variant_index: int | None = None, variant_disposition: str | None = None) -> RevisionMetadata:
    if revision_identity:
        status = RevisionStatus.REVISION_IDENTITY_READY
    elif variant_disposition:
        status = RevisionStatus.REVISION_IDENTITY_PARTIAL
    else:
        status = RevisionStatus.REVISION_HISTORY_UNKNOWN
    return RevisionMetadata(status, revision_identity, supersedes_identity, variant_index, variant_disposition)


def _sessions(values: Iterable[str] | None) -> list[str]:
    return sorted({_parse_date_only(item) for item in (values or []) if _parse_date_only(item)})


def _next_session_strictly_after(day: str, sessions: Iterable[str] | None) -> str | None:
    return next((session for session in _sessions(sessions) if session > day), None)


def resolve_eod_research_session(*, timestamp: str | None = None, publication_date: str | None = None,
                                 governed_sessions: Iterable[str] | None = None) -> tuple[str | None, EODResolutionRule, tuple[str, ...]]:
    sessions = _sessions(governed_sessions)
    if publication_date is not None:
        day = _parse_date_only(publication_date)
        if not day:
            return None, EODResolutionRule.UNRESOLVED, ("PUBLICATION_DATE_INVALID",)
        result = _next_session_strictly_after(day, sessions)
        return result, EODResolutionRule.DATE_ONLY_CONSERVATIVE_NEXT_SESSION, (() if result else ("SESSION_RESOLUTION_UNAVAILABLE",))
    instant = _parse_aware(timestamp)
    if not instant:
        return None, EODResolutionRule.UNRESOLVED, ("EXACT_TIMESTAMP_TIMEZONE_UNKNOWN_OR_MISSING",)
    local = instant.astimezone(__import__("zoneinfo").ZoneInfo(OPERATING_TIMEZONE))
    day = local.date().isoformat()
    if day in sessions and local.timetz().replace(tzinfo=None) < EOD_RESEARCH_CUTOFF:
        return day, EODResolutionRule.EXACT_TIMESTAMP_CUTOFF, ()
    result = _next_session_strictly_after(day, sessions)
    return result, EODResolutionRule.EXACT_TIMESTAMP_CUTOFF, (() if result else ("SESSION_RESOLUTION_UNAVAILABLE",))


def resolve_knowledge_availability(*, publication: PublicationTime, first_observed_at: str | None,
                                   governed_sessions: Iterable[str] | None = None) -> KnowledgeResolution:
    if publication.publication_authority_tier in QUALIFIED_PUBLICATION_TIERS:
        if publication.source_published_at_precision == TemporalPrecision.EXACT_DATETIME and _parse_aware(publication.source_published_at):
            session, rule, warnings = resolve_eod_research_session(timestamp=publication.source_published_at, governed_sessions=governed_sessions)
            return KnowledgeResolution(KnowledgeTimeStatus.KNOWLEDGE_RESOLVED_SOURCE_PUBLICATION, publication.source_published_at, session,
                                       HistoricalReconstructionScope.FROM_QUALIFIED_SOURCE_PUBLICATION, rule, warnings=warnings)
        if publication.source_published_at_precision == TemporalPrecision.DATE_ONLY and _parse_date_only(publication.source_published_at):
            session, rule, warnings = resolve_eod_research_session(publication_date=publication.source_published_at, governed_sessions=governed_sessions)
            return KnowledgeResolution(KnowledgeTimeStatus.KNOWLEDGE_RESOLVED_SOURCE_PUBLICATION_DATE_ONLY, None, session,
                                       HistoricalReconstructionScope.FROM_QUALIFIED_SOURCE_PUBLICATION, rule, warnings=warnings)
    if _parse_aware(first_observed_at):
        session, _, warnings = resolve_eod_research_session(timestamp=first_observed_at, governed_sessions=governed_sessions)
        return KnowledgeResolution(KnowledgeTimeStatus.KNOWLEDGE_RESOLVED_FIRST_OBSERVED_CONSERVATIVE, first_observed_at, session,
                                   HistoricalReconstructionScope.FROM_FIRST_OBSERVED_FORWARD_ONLY, EODResolutionRule.FIRST_OBSERVED_CONSERVATIVE, warnings=warnings)
    return KnowledgeResolution(KnowledgeTimeStatus.KNOWLEDGE_UNKNOWN, None, None, HistoricalReconstructionScope.NONE,
                               EODResolutionRule.UNRESOLVED, warnings=("QUALIFIED_PUBLICATION_AND_TRUSTWORTHY_FIRST_OBSERVED_UNAVAILABLE",))


def propagate_derived_knowledge(*, required_inputs: Iterable[KnowledgeResolution | Mapping[str, Any]],
                                optional_inputs: Iterable[KnowledgeResolution | Mapping[str, Any]] = ()) -> KnowledgeResolution:
    def coerce(value: KnowledgeResolution | Mapping[str, Any]) -> KnowledgeResolution:
        if isinstance(value, KnowledgeResolution):
            return value
        return KnowledgeResolution(KnowledgeTimeStatus(value.get("knowledge_time_status", KnowledgeTimeStatus.KNOWLEDGE_UNKNOWN)),
            value.get("knowledge_available_at"), value.get("knowledge_available_research_session"),
            HistoricalReconstructionScope(value.get("historical_reconstruction_scope", HistoricalReconstructionScope.NONE)),
            EODResolutionRule(value.get("eod_resolution_rule", EODResolutionRule.UNRESOLVED)))
    required = [coerce(item) for item in required_inputs]
    if not required or any(item.knowledge_time_status == KnowledgeTimeStatus.KNOWLEDGE_UNKNOWN or not item.knowledge_available_research_session for item in required):
        return KnowledgeResolution(KnowledgeTimeStatus.KNOWLEDGE_UNKNOWN, None, None, HistoricalReconstructionScope.NONE,
                                   EODResolutionRule.UNRESOLVED, warnings=("REQUIRED_INPUT_KNOWLEDGE_UNRESOLVED",))
    session = max(str(item.knowledge_available_research_session) for item in required)
    instants = [item.knowledge_available_at for item in required]
    exact = max(instants) if all(_parse_aware(item) for item in instants) else None
    warnings = ("OPTIONAL_INPUT_KNOWLEDGE_UNRESOLVED_IGNORED",) if any(coerce(item).knowledge_time_status == KnowledgeTimeStatus.KNOWLEDGE_UNKNOWN for item in optional_inputs) else ()
    return KnowledgeResolution(KnowledgeTimeStatus.KNOWLEDGE_RESOLVED_DERIVED, exact, session,
                               HistoricalReconstructionScope.FROM_REQUIRED_INPUT_BOUNDS, EODResolutionRule.DERIVED_REQUIRED_INPUT_MAX, warnings=warnings)


def historical_reconstruction_eligible(*, knowledge: KnowledgeResolution, requested_research_session: str | None) -> bool:
    """Fail closed before the resolved research-session bound; never backdate a later receipt."""
    return bool(knowledge.historical_reconstruction_scope != HistoricalReconstructionScope.NONE
                and knowledge.knowledge_available_research_session
                and _parse_date_only(requested_research_session)
                and str(requested_research_session) >= str(knowledge.knowledge_available_research_session))


def project_official_evidence_temporal_metadata(record: Mapping[str, Any], *, governed_sessions: Iterable[str] | None = None) -> dict[str, Any]:
    published = record.get("published_at") or record.get("publication_date")
    precision = infer_precision(published)
    tier = PublicationAuthorityTier.OFFICIAL_ISSUER_IR_OR_EXCHANGE if str(record.get("source_authority") or record.get("source_id") or "").lower() not in {"", "provider"} else PublicationAuthorityTier.UNVERIFIED
    publication = PublicationTime(published, precision, tier, record.get("document_id") or record.get("sha256"), str(record.get("qualification_state") or "UNKNOWN"),
                                  "AWARE" if precision == TemporalPrecision.EXACT_DATETIME else "DATE_ONLY" if precision == TemporalPrecision.DATE_ONLY else "UNKNOWN")
    first = record.get("observed_at") or record.get("retrieved_at")
    knowledge = resolve_knowledge_availability(publication=publication, first_observed_at=first, governed_sessions=governed_sessions)
    identity = classify_observation_identity(raw_identity=record.get("sha256") or record.get("document_sha256"))
    identity = ObservationTime(first if _parse_aware(first) else None, "RETAINED" if _parse_aware(first) else "LEGACY_UNKNOWN", identity.observation_identity, identity.observation_identity_status, identity.observation_identity_method)
    return {"publication_time": publication.to_dict(), "observation_time": identity.to_dict(), "knowledge_resolution": knowledge.to_dict()}


def project_provider_temporal_metadata(*, provider: str, metadata: Mapping[str, Any], first_observed_at: str | None = None) -> dict[str, Any]:
    name = provider.upper()
    warnings: list[str] = []
    if name == "KBS":
        update = metadata.get("LastUpdate") if "LastUpdate" in metadata else metadata.get("provider_update_date")
        reported = metadata.get("ReportDate") if "ReportDate" in metadata else metadata.get("report_date")
        if update and not _parse_aware(update): warnings.append("KBS_LASTUPDATE_TIMEZONE_NAIVE_OR_UNKNOWN")
        provider_meta = ProviderTemporalMetadata(reported, update, None, infer_precision(update), "AWARE" if _parse_aware(update) else "UNKNOWN", tuple(warnings))
        mapping = {"report_date_semantics": "PROVIDER_REPORTED_REPORT_DATE", "last_update_semantics": "PROVIDER_RECORD_UPDATE_TIME_EXACT", "publication_resolution_prohibited": True}
    elif name in {"DNSE", "DNSE/LIVESPEED"}:
        event = metadata.get("lastUpdated") if "lastUpdated" in metadata else metadata.get("source_event_time")
        if _parse_aware(event) and _parse_aware(first_observed_at) and _parse_aware(event) > _parse_aware(first_observed_at): warnings.append("PROVIDER_CLIENT_CLOCK_CONFLICT")
        provider_meta = ProviderTemporalMetadata(None, None, event, infer_precision(event), "AWARE" if _parse_aware(event) else "UNKNOWN", tuple(warnings))
        mapping = {"last_updated_semantics": "PROVIDER_EVENT_TIME_EXACT", "publication_resolution_prohibited": True, "first_observed_required_for_knowledge": True}
    else:
        provider_meta = ProviderTemporalMetadata(warnings=("PROVIDER_TEMPORAL_MAPPING_UNAVAILABLE",))
        mapping = {"publication_resolution_prohibited": True}
    publication = PublicationTime(None, TemporalPrecision.UNKNOWN, PublicationAuthorityTier.PROVIDER_REPORTED, provider, "PROVIDER_METADATA_ONLY", "UNKNOWN")
    knowledge = resolve_knowledge_availability(publication=publication, first_observed_at=first_observed_at)
    return {"provider_temporal_metadata": provider_meta.to_dict(), "knowledge_resolution": knowledge.to_dict(), "mapping": mapping}


def build_temporal_envelope(*, valid_time: ValidTime, publication_time: PublicationTime, first_observed_at: str | None,
                            raw_identity: str | None = None, normalized_identity: str | None = None,
                            provider_metadata: ProviderTemporalMetadata | None = None, pipeline_time: PipelineTime | None = None,
                            revision: RevisionMetadata | None = None, governed_sessions: Iterable[str] | None = None) -> TemporalEnvelope:
    identity = classify_observation_identity(raw_identity=raw_identity, normalized_identity=normalized_identity)
    observation = ObservationTime(first_observed_at if _parse_aware(first_observed_at) else None,
                                  "RETAINED" if _parse_aware(first_observed_at) else "LEGACY_UNKNOWN", identity.observation_identity,
                                  identity.observation_identity_status, identity.observation_identity_method)
    return TemporalEnvelope(valid_time, publication_time, observation,
        resolve_knowledge_availability(publication=publication_time, first_observed_at=first_observed_at, governed_sessions=governed_sessions),
        revision or revision_metadata(), TemporalLineage(publication_time.source_identity, raw_identity, provider_metadata or ProviderTemporalMetadata(), pipeline_time or PipelineTime()),
        {"raw_as_traded": "NOT_PROMOTED", "historical_price_pit": "BLOCKED", "historical_full_system_backtest": "BLOCKED",
         "same_session_close_execution": "NOT_ESTABLISHED", "invariant": "BITEMPORAL_RESEARCH_SESSION_DOES_NOT_GRANT_SAME_SESSION_CLOSE_EXECUTION"})
