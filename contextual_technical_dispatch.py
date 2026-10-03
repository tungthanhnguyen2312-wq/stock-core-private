"""Explicit technical-version boundary; historical V1 never migrates in place."""
from __future__ import annotations

V1 = "contextual_technical_feature_set/v1"
V2 = "contextual_technical_feature_set/v2"
AUTHORITY_EFFECT = "NONE / DETERMINISTIC_DESCRIPTIVE_TECHNICAL_CONTEXT_ONLY"
SUPPORTED_VERSIONS = (V1, V2)
PRODUCTION_V2_START_SESSION = "2026-10-03"


def module_for_version(version):
    if version == V1:
        import contextual_technical_features as producer
    elif version == V2:
        import contextual_technical_features_v2 as producer
    else:
        raise ValueError("TECHNICAL_VERSION_UNKNOWN:" + str(version))
    return producer


def production_version(session):
    from datetime import date
    if date.fromisoformat(session).isoformat() != session:
        raise ValueError("TECHNICAL_SESSION_INVALID")
    return V2 if session >= PRODUCTION_V2_START_SESSION else V1


def batch_version(contexts):
    rows = contexts.values() if isinstance(contexts, dict) else contexts
    versions = {row.get("contract_version") for row in rows}
    if len(versions) > 1:
        raise ValueError("TECHNICAL_VERSION_MIXED")
    version = next(iter(versions), None)
    if versions and version not in SUPPORTED_VERSIONS:
        raise ValueError("TECHNICAL_VERSION_UNKNOWN:" + str(version))
    return version


def verify_context(context, *, ticker=None, session=None):
    version = context.get("contract_version")
    module_for_version(version)
    ticker = ticker or context.get("ticker")
    session = session or context.get("as_of_session")
    if version == V1:
        from volume_and_flow_context import verify_technical
        verify_technical(context, ticker, session)
    else:
        from contextual_technical_features_v2 import verify_context as verify
        verify(context, ticker=ticker, session=session)
    return version


def verify_batch(contexts, *, session):
    version = batch_version(contexts)
    for ticker, context in contexts.items():
        verify_context(context, ticker=ticker, session=session)
    return version


def build_research_projections(observations, *, ticker, target_session, knowledge_cutoff,
                               source_identity, calendar_evidence=None, ca_events=(), version=None):
    return module_for_version(version or production_version(target_session)).build_research_projections(
        observations, ticker=ticker, target_session=target_session, knowledge_cutoff=knowledge_cutoff,
        source_identity=source_identity, calendar_evidence=calendar_evidence, ca_events=ca_events)


def verified_context_records(artifact, *, session, knowledge_cutoff, verified_bar_contexts):
    contexts = {t: r["contextual_technical"] for t, r in (artifact or {}).get("records", {}).items()
                if r.get("contextual_technical") is not None}
    try:
        version = batch_version(contexts)
    except ValueError as exc:
        if str(exc) == "TECHNICAL_VERSION_MIXED":
            raise
        return {t: {"status": "UNAVAILABLE", "non_voting": True, "reason": str(exc)} for t in contexts}
    if version is None:
        return {}
    return module_for_version(version).verified_context_records(artifact, session=session,
        knowledge_cutoff=knowledge_cutoff, verified_bar_contexts=verified_bar_contexts)
