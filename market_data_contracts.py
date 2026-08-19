"""Market-wide ingest-first contracts.

These are pure, runtime-independent contracts.  They deliberately retain observations whose
semantics are incomplete: qualification constrains feature use, never raw retention.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import math
from typing import Any, Iterable, Mapping


CONTRACT_VERSION = "1.0.0"


class FeatureStatus(StrEnum):
    OBSERVED = "OBSERVED"
    CANONICAL = "CANONICAL"
    QUALIFIED = "QUALIFIED"
    DERIVED = "DERIVED"
    DERIVED_PROXY = "DERIVED_PROXY"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"
    UNQUALIFIED = "UNQUALIFIED"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    SUSPECT = "SUSPECT"


class PriceBasis(StrEnum):
    RAW_AS_TRADED = "RAW_AS_TRADED"
    ADJUSTED_RETROSPECTIVE = "ADJUSTED_RETROSPECTIVE"
    CURRENT_MARKET = "CURRENT_MARKET"
    PIT_OBSERVED = "PIT_OBSERVED"
    UNKNOWN = "UNKNOWN"


class ExceptionDisposition(StrEnum):
    VALID_MARKET_EVENT = "VALID_MARKET_EVENT"
    SOURCE_ERROR = "SOURCE_ERROR"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    UNIT_TRANSFORM_REQUIRED = "UNIT_TRANSFORM_REQUIRED"
    UNRESOLVED = "UNRESOLVED"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False, default=str)


def stable_id(value: Mapping[str, Any]) -> str:
    return sha256(canonical_json(dict(value)).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RawObservation:
    """Immutable provider observation, including unknown semantic dimensions."""
    provider: str
    dataset: str
    instrument: str
    retrieved_at: str
    request_identity: str
    raw_payload_hash: str
    schema_version: str
    raw_payload: Mapping[str, Any]
    source_event_time: str | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION

    @property
    def observation_id(self) -> str:
        return stable_id({
            "contract_version": self.contract_version, "provider": self.provider,
            "dataset": self.dataset, "instrument": self.instrument,
            "retrieved_at": self.retrieved_at, "request_identity": self.request_identity,
            "source_event_time": self.source_event_time, "raw_payload_hash": self.raw_payload_hash,
            "schema_version": self.schema_version,
        })

    def record(self) -> dict[str, Any]:
        return {**asdict(self), "observation_id": self.observation_id}


from field_temporal_contract import TemporalField, wrap_temporal_fields, extract_field_values


@dataclass(frozen=True)
class CanonicalRecord:
    """Standardized record; unresolved fields remain explicit rather than being invented."""
    raw_observation_id: str
    instrument: str
    exchange: str | None
    board: str | None
    instrument_class: str
    observed_at: str | None
    price_basis: PriceBasis
    corporate_action_basis: str
    financial_statement_scope: str | None
    reporting_period: str | None
    publication_date: str | None
    effective_from: str | None
    revision_state: str
    quality_flags: tuple[str, ...]
    fields: Mapping[str, Any]
    unit_multiplier: float = 1.0
    status: FeatureStatus = FeatureStatus.CANONICAL
    lineage: Mapping[str, Any] = field(default_factory=dict)
    temporal_fields: Mapping[str, Any] = field(default_factory=dict)

    def record(self) -> dict[str, Any]:
        result = asdict(self)
        result["price_basis"] = self.price_basis.value
        result["status"] = self.status.value
        if self.temporal_fields:
            result["temporal_fields"] = {
                key: (val.record() if hasattr(val, "record") else val)
                for key, val in self.temporal_fields.items()
            }
        return result

    def with_temporal_evaluation(self, *, reference_at: Any, knowledge_cutoff: Any = None,
                                 domain: str = "daily_market") -> CanonicalRecord:
        """Evaluate field-level temporal envelopes for every field in this record."""
        as_of = self.observed_at[:10] if self.observed_at and len(self.observed_at) >= 10 else self.observed_at
        t_fields = wrap_temporal_fields(
            self.fields,
            observed_at=self.observed_at,
            as_of=as_of,
            domain=domain,
            reference_at=reference_at,
            knowledge_cutoff=knowledge_cutoff,
            price_basis=self.price_basis.value,
            quality_status=self.status.value,
            source=self.exchange or "UNKNOWN",
            lineage=dict(self.lineage),
        )
        return CanonicalRecord(
            raw_observation_id=self.raw_observation_id,
            instrument=self.instrument,
            exchange=self.exchange,
            board=self.board,
            instrument_class=self.instrument_class,
            observed_at=self.observed_at,
            price_basis=self.price_basis,
            corporate_action_basis=self.corporate_action_basis,
            financial_statement_scope=self.financial_statement_scope,
            reporting_period=self.reporting_period,
            publication_date=self.publication_date,
            effective_from=self.effective_from,
            revision_state=self.revision_state,
            quality_flags=self.quality_flags,
            fields=self.fields,
            unit_multiplier=self.unit_multiplier,
            status=self.status,
            lineage=self.lineage,
            temporal_fields=t_fields,
        )


@dataclass(frozen=True)
class QualityException:
    observation_id: str
    rule: str
    severity: str
    raw_value: Any
    contextual_values: Mapping[str, Any]
    disposition: ExceptionDisposition = ExceptionDisposition.UNRESOLVED


@dataclass(frozen=True)
class PitFinancialFact:
    feature_id: str
    instrument: str
    value: float | int | None
    period_end: str
    publish_date: str
    received_at: str
    effective_from: str
    revision_publish_date: str | None
    source_document: str
    statement_scope: str
    audit_status: str
    status: FeatureStatus
    lineage: Mapping[str, Any] = field(default_factory=dict)

    def available_at(self) -> str:
        return self.revision_publish_date or self.effective_from or self.publish_date


def canonicalize_market_record(raw: RawObservation, *, exchange: str | None, board: str | None,
                               instrument_class: str, fields: Mapping[str, Any],
                               unit_multiplier: float = 1.0,
                               price_basis: PriceBasis = PriceBasis.UNKNOWN,
                               quality_flags: Iterable[str] = (),
                               reference_at: Any = None,
                               knowledge_cutoff: Any = None,
                               domain: str = "daily_market") -> CanonicalRecord:
    """Create a deterministic canonical projection while preserving the raw identity.

    The caller must supply a documented/evidenced multiplier.  This function never guesses one.
    """
    if not math.isfinite(unit_multiplier) or unit_multiplier <= 0:
        raise ValueError("unit_multiplier must be finite and positive")
    normalized = {
        key: (value * unit_multiplier if key in {"volume", "value", "turnover"}
              and isinstance(value, (int, float)) and not isinstance(value, bool) else value)
        for key, value in sorted(fields.items())
    }
    temporal_fields = {}
    if reference_at is not None:
        obs_time = raw.source_event_time or raw.retrieved_at
        as_of_time = (raw.source_event_time[:10] if raw.source_event_time and len(raw.source_event_time) >= 10
                      else (raw.retrieved_at[:10] if raw.retrieved_at and len(raw.retrieved_at) >= 10 else None))
        temporal_fields = wrap_temporal_fields(
            normalized,
            observed_at=obs_time,
            as_of=as_of_time,
            domain=domain,
            reference_at=reference_at,
            knowledge_cutoff=knowledge_cutoff,
            price_basis=price_basis.value,
            quality_status=FeatureStatus.CANONICAL.value,
            source=raw.provider,
            lineage={"raw_payload_hash": raw.raw_payload_hash, "contract_version": CONTRACT_VERSION},
        )
    return CanonicalRecord(
        raw_observation_id=raw.observation_id, instrument=raw.instrument, exchange=exchange,
        board=board, instrument_class=instrument_class, observed_at=raw.source_event_time or raw.retrieved_at,
        price_basis=price_basis, corporate_action_basis="unknown", financial_statement_scope=None,
        reporting_period=None, publication_date=None, effective_from=None, revision_state="unknown",
        quality_flags=tuple(sorted(set(quality_flags))), fields=normalized,
        unit_multiplier=unit_multiplier, lineage={"raw_payload_hash": raw.raw_payload_hash,
                                                   "contract_version": CONTRACT_VERSION},
        temporal_fields=temporal_fields,
    )


def financial_facts_available_as_of(facts: Iterable[PitFinancialFact], as_of: str) -> list[PitFinancialFact]:
    """Return only facts published/effective by ``as_of``; period end is never an availability proxy."""
    return sorted((fact for fact in facts if fact.available_at() <= as_of),
                  key=lambda fact: (fact.instrument, fact.feature_id, fact.available_at()))
