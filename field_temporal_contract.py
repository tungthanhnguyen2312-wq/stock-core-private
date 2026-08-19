"""P0-C.3: Deterministic field-level freshness, temporal provenance, and PIT-eligibility contract.

WHAT THIS IS:
    A pure, deterministic foundation ensuring that every authoritative market-wide field/value
    carries its own temporal envelope (observed_at, as_of/effective_at, freshness_status,
    pit_eligible, pit_status, stale_reason, domain rules, and lineage) so that temporal metadata
    travels with the field/value it qualifies and cannot be silently detached downstream.

THE SIX FRESHNESS STATES:
    - current: Observation is fresh within domain cadence and grace window relative to the
               latest completed market/calendar reference point.
    - expiring: Observation has exceeded nominal cadence but remains inside allowable grace.
    - stale: Observation age exceeds cadence + grace window. Carries explicit reason code.
             NEVER computed as a naive `date < today` check.
    - historical: Reporting-period evidence (e.g. quarterly financial statements) where age
                  represents historical fact rather than stale live market data.
    - missing: Timestamp or value is absent/unprovided.
    - unknown: Malformed, unparseable, or future/look-ahead timestamp.

THE PIT ELIGIBILITY CONTRACT:
    - pit_eligible: bool. True ONLY when:
        1. observed_at is a valid, parseable ISO timestamp.
        2. knowledge_cutoff is provided and observed_at <= knowledge_cutoff.
        3. underlying source/price basis is authoritatively PIT-safe (e.g. PriceBasis.PIT_OBSERVED
           or PriceBasis.RAW_AS_TRADED, or qualified non-price canonical fact). If price basis is
           ADJUSTED_RETROSPECTIVE, UNKNOWN, or unpromoted, pit_eligible is strictly False.
        4. no lookahead / future timestamp relative to reference_at.

FAIL-CLOSED INVARIANTS:
    - A missing, malformed, or future timestamp never yields `current` or `pit_eligible=True`.
    - Temporal metadata travels bound to the field/value.
    - Source lineage, basis, and quality status are preserved without promotion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

from freshness_history import RULES, DomainRule, latest_completed_market_day, parse_timestamp


CONTRACT_VERSION = "1.0.0"


class FreshnessState(StrEnum):
    CURRENT = "current"
    EXPIRING = "expiring"
    STALE = "stale"
    HISTORICAL = "historical"
    MISSING = "missing"
    UNKNOWN = "unknown"


class PitStatus(StrEnum):
    QUALIFIED = "QUALIFIED"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"
    LOOKAHEAD_VIOLATION = "LOOKAHEAD_VIOLATION"
    UNQUALIFIED_PRICE_BASIS = "UNQUALIFIED_PRICE_BASIS"
    TIMESTAMP_MISSING_OR_INVALID = "TIMESTAMP_MISSING_OR_INVALID"
    KNOWLEDGE_CUTOFF_MISSING = "KNOWLEDGE_CUTOFF_MISSING"
    UNKNOWN = "UNKNOWN"


import math


def _sanitize_for_json(val: Any) -> Any:
    if isinstance(val, float) and math.isnan(val):
        return None
    if isinstance(val, dict):
        return {k: _sanitize_for_json(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_sanitize_for_json(v) for v in val]
    return val


def canonical_json(value: Any) -> str:
    """Deterministic JSON serialization with sorted keys and no floating point NaN."""
    sanitized = _sanitize_for_json(value)
    return json.dumps(sanitized, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False, default=str)


def stable_id(value: Any) -> str:
    """Deterministic SHA-256 digest of canonical JSON."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TemporalField:
    """An authoritative field value bound with its field-level temporal metadata."""
    field_name: str
    value: Any
    observed_at: str | None
    as_of: str | None
    freshness_status: str
    pit_eligible: bool
    pit_status: str
    stale_reason: str | None = None
    expected_update_frequency: str | None = None
    source: str | None = None
    knowledge_cutoff: str | None = None
    reference_at: str | None = None
    domain: str = "daily_market"
    quality_status: str = "unqualified"
    price_basis: str | None = None
    contract_version: str = CONTRACT_VERSION
    lineage: Mapping[str, Any] = field(default_factory=dict)

    @property
    def field_id(self) -> str:
        return stable_id({
            "contract_version": self.contract_version,
            "field_name": self.field_name,
            "value": self.value,
            "observed_at": self.observed_at,
            "as_of": self.as_of,
            "freshness_status": self.freshness_status,
            "pit_eligible": self.pit_eligible,
            "pit_status": self.pit_status,
            "price_basis": self.price_basis,
            "quality_status": self.quality_status,
        })

    def is_actionable(self) -> bool:
        return self.freshness_status == FreshnessState.CURRENT.value and self.stale_reason is None

    def record(self) -> dict[str, Any]:
        result = asdict(self)
        result["field_id"] = self.field_id
        result["is_actionable"] = self.is_actionable()
        return result

    def canonical_json(self) -> str:
        return canonical_json(self.record())


def evaluate_field_temporal(
    field_name: str,
    value: Any,
    *,
    observed_at: Any,
    as_of: Any,
    domain: str = "daily_market",
    reference_at: Any,
    knowledge_cutoff: Any = None,
    price_basis: str | None = None,
    quality_status: str = "unqualified",
    source: str | None = None,
    completeness: str | None = None,
    dependency: Mapping[str, Any] | None = None,
    lineage: Mapping[str, Any] | None = None,
) -> TemporalField:
    """Evaluate and construct a deterministic TemporalField for a single field/value."""
    rule = RULES.get(domain, DomainRule(domain, 1, 1, market_days=True))
    ref_dt = parse_timestamp(reference_at)
    if ref_dt is None:
        return TemporalField(
            field_name=field_name,
            value=value,
            observed_at=None,
            as_of=None,
            freshness_status=FreshnessState.UNKNOWN.value,
            pit_eligible=False,
            pit_status=PitStatus.TIMESTAMP_MISSING_OR_INVALID.value,
            stale_reason="invalid_reference_timestamp",
            expected_update_frequency=f"{rule.cadence_days}d",
            source=source,
            knowledge_cutoff=str(knowledge_cutoff) if knowledge_cutoff is not None else None,
            reference_at=None,
            domain=domain,
            quality_status=quality_status,
            price_basis=price_basis,
            lineage=dict(lineage or {}),
        )

    ref_iso = ref_dt.isoformat()
    obs_dt = parse_timestamp(observed_at)
    as_of_dt = parse_timestamp(as_of)
    cutoff_dt = parse_timestamp(knowledge_cutoff) if knowledge_cutoff is not None else None

    obs_iso = obs_dt.isoformat() if obs_dt else None
    as_of_iso = as_of_dt.date().isoformat() if as_of_dt else (_text_date(as_of))

    # Check for missing timestamps
    if obs_dt is None and as_of_dt is None:
        status = FreshnessState.MISSING.value if (observed_at is None and as_of is None) else FreshnessState.UNKNOWN.value
        stale_reason = "source_timestamp_missing" if (observed_at is None and as_of is None) else "source_timestamp_malformed"
        return TemporalField(
            field_name=field_name,
            value=value,
            observed_at=obs_iso,
            as_of=as_of_iso,
            freshness_status=status,
            pit_eligible=False,
            pit_status=PitStatus.TIMESTAMP_MISSING_OR_INVALID.value,
            stale_reason=stale_reason,
            expected_update_frequency=f"{rule.cadence_days}d",
            source=source,
            knowledge_cutoff=cutoff_dt.isoformat() if cutoff_dt else None,
            reference_at=ref_iso,
            domain=domain,
            quality_status=quality_status,
            price_basis=price_basis,
            lineage=dict(lineage or {}),
        )

    # Check for future / lookahead timestamps relative to reference_at
    if as_of_dt and as_of_dt.date() > ref_dt.date():
        return TemporalField(
            field_name=field_name,
            value=value,
            observed_at=obs_iso,
            as_of=as_of_iso,
            freshness_status=FreshnessState.UNKNOWN.value,
            pit_eligible=False,
            pit_status=PitStatus.LOOKAHEAD_VIOLATION.value,
            stale_reason="future_as_of_date_rejected",
            expected_update_frequency=f"{rule.cadence_days}d",
            source=source,
            knowledge_cutoff=cutoff_dt.isoformat() if cutoff_dt else None,
            reference_at=ref_iso,
            domain=domain,
            quality_status=quality_status,
            price_basis=price_basis,
            lineage=dict(lineage or {}),
        )

    if obs_dt and obs_dt > ref_dt:
        return TemporalField(
            field_name=field_name,
            value=value,
            observed_at=obs_iso,
            as_of=as_of_iso,
            freshness_status=FreshnessState.UNKNOWN.value,
            pit_eligible=False,
            pit_status=PitStatus.LOOKAHEAD_VIOLATION.value,
            stale_reason="future_observed_at_rejected",
            expected_update_frequency=f"{rule.cadence_days}d",
            source=source,
            knowledge_cutoff=cutoff_dt.isoformat() if cutoff_dt else None,
            reference_at=ref_iso,
            domain=domain,
            quality_status=quality_status,
            price_basis=price_basis,
            lineage=dict(lineage or {}),
        )

    # Compute freshness age
    primary_dt = as_of_dt or obs_dt
    if primary_dt is None:
        age = 9999
    elif rule.market_days:
        expected = latest_completed_market_day(ref_dt)
        age = (expected - primary_dt.date()).days
    else:
        age = (ref_dt.date() - primary_dt.date()).days

    if rule.historical:
        freshness_status = FreshnessState.HISTORICAL.value if age >= 0 else FreshnessState.UNKNOWN.value
        stale_reason = "reporting_period_historical" if freshness_status == FreshnessState.HISTORICAL.value else "future_historical_period_rejected"
    elif age <= rule.cadence_days:
        freshness_status = FreshnessState.CURRENT.value
        stale_reason = None
    elif age <= rule.cadence_days + rule.grace_days:
        freshness_status = FreshnessState.EXPIRING.value
        stale_reason = f"source_age_{max(age, 0)}d_in_grace_period"
    else:
        freshness_status = FreshnessState.STALE.value
        stale_reason = f"source_age_{max(age, 0)}d_exceeds_{rule.grace_days}d_grace"

    # Evaluate completeness / dependency constraints
    dependency_status = (dependency or {}).get("freshness_status")
    complete = completeness in {"complete", "available", None} and not (
        rule.requires_complete and completeness not in {"complete", "available"}
    )
    if rule.requires_complete and not complete:
        stale_reason = stale_reason or "coverage_or_completeness_not_qualified"
    if dependency_status not in {None, "current"}:
        stale_reason = stale_reason or "underlying_dependency_not_current"

    # Evaluate PIT Eligibility
    pit_eligible, pit_status = _evaluate_pit_eligibility(
        obs_dt=obs_dt,
        cutoff_dt=cutoff_dt,
        price_basis=price_basis,
        quality_status=quality_status,
        field_name=field_name,
    )

    return TemporalField(
        field_name=field_name,
        value=value,
        observed_at=obs_iso,
        as_of=as_of_iso,
        freshness_status=freshness_status,
        pit_eligible=pit_eligible,
        pit_status=pit_status,
        stale_reason=stale_reason,
        expected_update_frequency=f"{rule.cadence_days}d",
        source=source,
        knowledge_cutoff=cutoff_dt.isoformat() if cutoff_dt else None,
        reference_at=ref_iso,
        domain=domain,
        quality_status=quality_status,
        price_basis=price_basis,
        lineage=dict(lineage or {}),
    )


def _text_date(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text if text else None


def _evaluate_pit_eligibility(
    *,
    obs_dt: datetime | None,
    cutoff_dt: datetime | None,
    price_basis: str | None,
    quality_status: str,
    field_name: str,
) -> tuple[bool, str]:
    """Evaluate PIT eligibility fail-closed."""
    if obs_dt is None:
        return False, PitStatus.TIMESTAMP_MISSING_OR_INVALID.value

    if cutoff_dt is None:
        return False, PitStatus.KNOWLEDGE_CUTOFF_MISSING.value

    if obs_dt > cutoff_dt:
        return False, PitStatus.LOOKAHEAD_VIOLATION.value

    # Check price-basis restriction for market price fields
    is_price_field = field_name in {
        "open", "high", "low", "close", "price", "vwap", "market.close",
        "market.return_1d", "market.ma_3", "market.volatility_3"
    }

    if is_price_field:
        # Strict fail-closed: PIT requires explicit positive RAW_AS_TRADED or PIT_OBSERVED authority
        if price_basis in {"RAW_AS_TRADED", "PIT_OBSERVED"}:
            return True, PitStatus.QUALIFIED.value
        return False, PitStatus.UNQUALIFIED_PRICE_BASIS.value

    # Non-price fields (metadata, corporate action, volume, fundamentals)
    if quality_status in {"qualified", "provider_reported", "canonical", "explicit_coverage_input"}:
        return True, PitStatus.QUALIFIED.value

    return True, PitStatus.HISTORICAL_ONLY.value


def wrap_temporal_fields(
    fields: Mapping[str, Any],
    *,
    observed_at: Any,
    as_of: Any,
    domain: str = "daily_market",
    reference_at: Any,
    knowledge_cutoff: Any = None,
    price_basis: str | None = None,
    quality_status: str = "unqualified",
    source: str | None = None,
    completeness: str | None = None,
    dependency: Mapping[str, Any] | None = None,
    lineage: Mapping[str, Any] | None = None,
) -> dict[str, TemporalField]:
    """Wrap a dictionary of field values into TemporalFields sharing the common record observation context."""
    return {
        field_name: evaluate_field_temporal(
            field_name=field_name,
            value=value,
            observed_at=observed_at,
            as_of=as_of,
            domain=domain,
            reference_at=reference_at,
            knowledge_cutoff=knowledge_cutoff,
            price_basis=price_basis,
            quality_status=quality_status,
            source=source,
            completeness=completeness,
            dependency=dependency,
            lineage=lineage,
        )
        for field_name, value in fields.items()
    }


def extract_field_values(fields: Mapping[str, TemporalField | Any]) -> dict[str, Any]:
    """Extract raw values from a mapping of TemporalFields or plain values."""
    return {
        key: (val.value if isinstance(val, TemporalField) else val)
        for key, val in fields.items()
    }


def evaluate_record_freshness(temporal_fields: Mapping[str, TemporalField | Mapping[str, Any]]) -> dict[str, Any]:
    """Derive composite record-level freshness from individual field-level envelopes."""
    statuses = set()
    actionable_count = 0
    total_count = len(temporal_fields)
    field_summaries = {}

    for name, item in temporal_fields.items():
        if isinstance(item, TemporalField):
            tf = item
        elif isinstance(item, Mapping):
            tf = evaluate_field_temporal(
                field_name=name,
                value=item.get("value"),
                observed_at=item.get("observed_at"),
                as_of=item.get("as_of"),
                domain=item.get("domain", "daily_market"),
                reference_at=item.get("reference_at") or datetime.now(timezone.utc),
                knowledge_cutoff=item.get("knowledge_cutoff"),
                price_basis=item.get("price_basis"),
                quality_status=item.get("quality_status", "unqualified"),
                source=item.get("source"),
            )
        else:
            statuses.add(FreshnessState.UNKNOWN.value)
            continue

        statuses.add(tf.freshness_status)
        if tf.is_actionable():
            actionable_count += 1
        field_summaries[name] = {
            "status": tf.freshness_status,
            "pit_eligible": tf.pit_eligible,
            "stale_reason": tf.stale_reason,
        }

    if not statuses or FreshnessState.UNKNOWN.value in statuses:
        composite_status = FreshnessState.UNKNOWN.value
    elif FreshnessState.MISSING.value in statuses:
        composite_status = FreshnessState.MISSING.value
    elif FreshnessState.STALE.value in statuses:
        composite_status = FreshnessState.STALE.value
    elif FreshnessState.EXPIRING.value in statuses:
        composite_status = FreshnessState.EXPIRING.value
    elif FreshnessState.HISTORICAL.value in statuses:
        composite_status = FreshnessState.HISTORICAL.value
    elif statuses == {FreshnessState.CURRENT.value}:
        composite_status = FreshnessState.CURRENT.value
    else:
        composite_status = FreshnessState.UNKNOWN.value

    return {
        "composite_status": composite_status,
        "actionable_fields_count": actionable_count,
        "total_fields_count": total_count,
        "all_actionable": total_count > 0 and actionable_count == total_count,
        "field_summaries": field_summaries,
    }
