from __future__ import annotations

from bitemporal_semantic_contract import (
    ClosePriceExecutionEligibility, EODResolutionRule, HistoricalReconstructionScope,
    KnowledgeTimeStatus, PublicationAuthorityTier, PublicationTime, TemporalPrecision,
    build_temporal_envelope, canonical_json, classify_observation_identity, content_identity,
    project_provider_temporal_metadata, propagate_derived_knowledge, resolve_knowledge_availability,
    resolve_eod_research_session, revision_metadata, validate_valid_time, historical_reconstruction_eligible,
)


SESSIONS = ["2025-03-31", "2025-04-01", "2025-04-02"]


def _official(value: str, precision: TemporalPrecision) -> PublicationTime:
    return PublicationTime(value, precision, PublicationAuthorityTier.OFFICIAL_ISSUER_IR_OR_EXCHANGE,
                           "synthetic-official", "QUALIFIED", "AWARE" if precision == TemporalPrecision.EXACT_DATETIME else "DATE_ONLY")


def test_semantic_objects_keep_valid_publication_observation_and_processing_separate():
    valid = validate_valid_time(domain="FINANCIAL_STOCK_FACT", period_end="2024-12-31")
    envelope = build_temporal_envelope(valid_time=valid, publication_time=_official("2025-03-31", TemporalPrecision.DATE_ONLY),
                                       first_observed_at="2025-04-01T09:00:00+07:00", raw_identity="raw:synthetic", governed_sessions=SESSIONS)
    payload = envelope.to_dict()
    assert payload["valid_time"]["period_end"] == "2024-12-31"
    assert payload["publication_time"]["source_published_at"] == "2025-03-31"
    assert payload["observation_time"]["first_observed_at"] == "2025-04-01T09:00:00+07:00"
    assert payload["knowledge_resolution"]["knowledge_available_at"] is None


def test_date_only_never_becomes_midnight_and_uses_next_governed_session():
    result = resolve_knowledge_availability(publication=_official("2025-03-31", TemporalPrecision.DATE_ONLY), first_observed_at=None, governed_sessions=SESSIONS)
    assert result.knowledge_time_status == KnowledgeTimeStatus.KNOWLEDGE_RESOLVED_SOURCE_PUBLICATION_DATE_ONLY
    assert result.knowledge_available_at is None
    assert result.knowledge_available_research_session == "2025-04-01"
    assert "T00:00" not in canonical_json(result.to_dict())


def test_exact_publication_and_first_observed_fallback_are_distinct():
    exact = resolve_knowledge_availability(publication=_official("2025-03-31T17:00:00+07:00", TemporalPrecision.EXACT_DATETIME), first_observed_at=None, governed_sessions=SESSIONS)
    fallback = resolve_knowledge_availability(publication=PublicationTime(None, TemporalPrecision.UNKNOWN, PublicationAuthorityTier.PROVIDER_REPORTED, "p", "UNKNOWN", "UNKNOWN"), first_observed_at="2025-03-31T19:00:00+07:00", governed_sessions=SESSIONS)
    assert exact.knowledge_time_status == KnowledgeTimeStatus.KNOWLEDGE_RESOLVED_SOURCE_PUBLICATION
    assert exact.knowledge_available_research_session == "2025-03-31"
    assert fallback.knowledge_time_status == KnowledgeTimeStatus.KNOWLEDGE_RESOLVED_FIRST_OBSERVED_CONSERVATIVE
    assert fallback.historical_reconstruction_scope == HistoricalReconstructionScope.FROM_FIRST_OBSERVED_FORWARD_ONLY
    assert fallback.knowledge_available_research_session == "2025-04-01"
    assert not historical_reconstruction_eligible(knowledge=fallback, requested_research_session="2025-03-31")
    assert historical_reconstruction_eligible(knowledge=fallback, requested_research_session="2025-04-01")


def test_naive_timestamp_and_missing_time_fail_closed():
    session, rule, warnings = resolve_eod_research_session(timestamp="2025-03-31T17:00:00", governed_sessions=SESSIONS)
    unknown = resolve_knowledge_availability(publication=PublicationTime(None, TemporalPrecision.UNKNOWN, PublicationAuthorityTier.UNVERIFIED, None, "UNKNOWN", "UNKNOWN"), first_observed_at=None)
    assert session is None and rule == EODResolutionRule.UNRESOLVED
    assert "TIMEZONE_UNKNOWN" in warnings[0]
    assert unknown.knowledge_time_status == KnowledgeTimeStatus.KNOWLEDGE_UNKNOWN


def test_corporate_event_requires_any_qualified_domain_date_not_record_date():
    listing = validate_valid_time(domain="CORPORATE_EVENT", event_type="LISTING_CHANGE", event_dates={"listing_effective_date": "2025-04-01"})
    trading = validate_valid_time(domain="CORPORATE_EVENT", event_type="NEW_SHARE_TRADING", event_dates={"trading_date": "2025-04-01"})
    missing = validate_valid_time(domain="CORPORATE_EVENT", event_type="DIVIDEND", event_dates={})
    assert listing.fitness_status.value == "READY"
    assert trading.fitness_status.value == "READY"
    assert missing.fitness_status.value == "VALID_TIME_INSUFFICIENT"


def test_identity_and_revision_are_explicit_without_fake_values():
    raw = classify_observation_identity(raw_identity="sha256:real-retained")
    normalized = classify_observation_identity(normalized_identity="normalized:synthetic")
    unknown = classify_observation_identity()
    assert raw.observation_identity_status.value == "OBSERVATION_IDENTITY_READY"
    assert normalized.observation_identity_method == "NORMALIZED_RECORD_IDENTITY"
    assert unknown.observation_identity is None
    assert revision_metadata().revision_status.value == "REVISION_HISTORY_UNKNOWN"
    assert revision_metadata(variant_disposition="CONFLICTING_RESTATEMENT_VARIANTS").revision_identity is None


def test_kbs_and_dnse_provider_time_can_never_be_publication_time_and_clock_conflict_is_visible():
    kbs = project_provider_temporal_metadata(provider="KBS", metadata={"ReportDate": "2025-03-31", "LastUpdate": "2025-04-01T09:00:00"})
    dnse = project_provider_temporal_metadata(provider="DNSE", metadata={"lastUpdated": "2025-04-01T10:00:00+07:00"}, first_observed_at="2025-04-01T09:00:00+07:00")
    assert kbs["mapping"]["publication_resolution_prohibited"] is True
    assert "KBS_LASTUPDATE_TIMEZONE_NAIVE_OR_UNKNOWN" in kbs["provider_temporal_metadata"]["warnings"]
    assert dnse["mapping"]["last_updated_semantics"] == "PROVIDER_EVENT_TIME_EXACT"
    assert "PROVIDER_CLIENT_CLOCK_CONFLICT" in dnse["provider_temporal_metadata"]["warnings"]


def test_derived_required_bounds_fail_closed_but_optional_unknown_does_not_block():
    left = resolve_knowledge_availability(publication=_official("2025-03-31T17:00:00+07:00", TemporalPrecision.EXACT_DATETIME), first_observed_at=None, governed_sessions=SESSIONS)
    right = resolve_knowledge_availability(publication=_official("2025-04-01", TemporalPrecision.DATE_ONLY), first_observed_at=None, governed_sessions=SESSIONS)
    unknown = resolve_knowledge_availability(publication=PublicationTime(None, TemporalPrecision.UNKNOWN, PublicationAuthorityTier.UNVERIFIED, None, "UNKNOWN", "UNKNOWN"), first_observed_at=None)
    derived = propagate_derived_knowledge(required_inputs=[left, right], optional_inputs=[unknown])
    failed = propagate_derived_knowledge(required_inputs=[left, unknown])
    assert derived.knowledge_time_status == KnowledgeTimeStatus.KNOWLEDGE_RESOLVED_DERIVED
    assert derived.knowledge_available_research_session == "2025-04-02"
    assert derived.knowledge_available_at is None
    assert derived.historical_reconstruction_scope == HistoricalReconstructionScope.FROM_REQUIRED_INPUT_BOUNDS
    assert failed.knowledge_time_status == KnowledgeTimeStatus.KNOWLEDGE_UNKNOWN


def test_execution_and_price_authority_remain_blocked_and_serialization_is_deterministic():
    valid = validate_valid_time(domain="MARKET_OBSERVATION", reference_session="2025-03-31")
    first = build_temporal_envelope(valid_time=valid, publication_time=_official("2025-03-31T17:00:00+07:00", TemporalPrecision.EXACT_DATETIME), first_observed_at=None, raw_identity="raw:synthetic", governed_sessions=SESSIONS).to_dict()
    second = build_temporal_envelope(valid_time=valid, publication_time=_official("2025-03-31T17:00:00+07:00", TemporalPrecision.EXACT_DATETIME), first_observed_at=None, raw_identity="raw:synthetic", governed_sessions=SESSIONS).to_dict()
    assert first["knowledge_resolution"]["close_price_execution_eligibility"] == ClosePriceExecutionEligibility.NOT_ESTABLISHED.value
    assert first["authority_boundaries"]["raw_as_traded"] == "NOT_PROMOTED"
    assert first["authority_boundaries"]["historical_price_pit"] == "BLOCKED"
    assert canonical_json(first) == canonical_json(second)
    assert content_identity(first) == content_identity(second)
