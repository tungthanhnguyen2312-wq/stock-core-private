"""Deterministic, machine-readable source/freshness summary for the AI handoff.

Built purely from data already resolved inside ``daily_research_session_operations.
build_operation`` (the session's ``inputs``, the already-computed ``macro_context``/
``macro_presentation_context``, ``flow``, and ``integrated_delivery``) -- no new
acquisition, no new provider call, no recomputation of any analytical value. This module
only classifies and re-describes evidence that already exists so an AI consumer can decide
which domains it can already trust internally and which still deserve bounded online
enrichment.

It never emits an investment conclusion (no BUY/SELL, target, probability, sizing, or
execution signal): the goal is source selection, not market interpretation.
"""
from __future__ import annotations

from typing import Any, Mapping

from freshness_history import freshness_envelope

CONTRACT_VERSION = "ai_handoff_source_freshness_matrix/v1"

FITNESS_CURRENT = "CURRENT_INTERNAL"
FITNESS_PARTIAL = "PARTIAL_INTERNAL"
FITNESS_STALE = "STALE_INTERNAL"
FITNESS_UNAVAILABLE = "UNAVAILABLE_INTERNAL"

ENRICHMENT_SUFFICIENT = "INTERNAL_SUFFICIENT"
ENRICHMENT_PARTIAL = "INTERNAL_PARTIAL"
ENRICHMENT_EXTERNAL_MAY_BE_REQUIRED = "EXTERNAL_CONTEXT_MAY_BE_REQUIRED"

_FRESHNESS_TO_FITNESS = {
    "current": FITNESS_CURRENT,
    "expiring": FITNESS_PARTIAL,
    "historical": FITNESS_PARTIAL,
    "stale": FITNESS_STALE,
    "missing": FITNESS_UNAVAILABLE,
    "unknown": FITNESS_UNAVAILABLE,
}


def _same_session_domain(
    *, artifact: Mapping[str, Any] | None, session: str, session_field: str | None,
    domain_label: str, online_enrichment: str = ENRICHMENT_SUFFICIENT,
) -> dict[str, Any]:
    """A domain already validated same-session-or-nothing upstream (validate_coherence
    raises on mismatch): presence means current, absence means unavailable. This never
    re-derives the coherence check itself -- it only reports what upstream already proved."""
    if not isinstance(artifact, Mapping):
        return {
            "status": FITNESS_UNAVAILABLE,
            "source_artifact_identity": None,
            "source_session_or_data_as_of": None,
            "freshness": None,
            "authority_tier": None,
            "reason_codes": [f"NO_{domain_label}_INPUT_REGISTERED_THIS_SESSION"],
            "fitness": FITNESS_UNAVAILABLE,
            "online_enrichment": ENRICHMENT_EXTERNAL_MAY_BE_REQUIRED,
        }
    observed_session = artifact.get(session_field) if session_field else session
    return {
        "status": "AVAILABLE_EXACT_SESSION",
        "source_artifact_identity": artifact.get("artifact_identity"),
        "source_session_or_data_as_of": observed_session or session,
        "freshness": {"freshness_status": "current", "expected_update_frequency": "1_market_day"},
        "authority_tier": "RESEARCH_USABLE_EXACT_SESSION",
        "reason_codes": [],
        "fitness": FITNESS_CURRENT,
        "online_enrichment": online_enrichment,
    }


def _fundamentals_domain(fundamental: Mapping[str, Any] | None, *, session: str) -> dict[str, Any]:
    """Fundamentals are intentionally reused across many sessions until a newer market-wide
    fundamental research artifact is registered (see docs/STATE.md fundamental cohort
    milestones) -- the artifact carries no per-session embedded reporting-period timestamp,
    so its age cannot be machine-verified from the artifact content itself. This is a
    genuine, permanent evidence-shape limit, not a defect: reported honestly as PARTIAL,
    never asserted exact-session current."""
    if not isinstance(fundamental, Mapping):
        return {
            "status": FITNESS_UNAVAILABLE,
            "source_artifact_identity": None,
            "source_session_or_data_as_of": None,
            "freshness": None,
            "authority_tier": None,
            "reason_codes": ["NO_FUNDAMENTAL_INPUT_REGISTERED_THIS_SESSION"],
            "fitness": FITNESS_UNAVAILABLE,
            "online_enrichment": ENRICHMENT_EXTERNAL_MAY_BE_REQUIRED,
        }
    return {
        "status": "AVAILABLE_SLOW_CYCLE_EVIDENCE",
        "source_artifact_identity": fundamental.get("artifact_identity"),
        "source_session_or_data_as_of": None,
        "freshness": {"freshness_status": "historical", "expected_update_frequency": "quarterly_or_slower"},
        "authority_tier": "RESEARCH_USABLE_SLOW_CYCLE",
        "reason_codes": ["NO_EMBEDDED_REPORTING_PERIOD_TIMESTAMP_REUSE_BY_DESIGN"],
        "fitness": FITNESS_PARTIAL,
        "online_enrichment": ENRICHMENT_PARTIAL,
    }


def _catalyst_domain(catalyst: Mapping[str, Any] | None, *, session: str) -> dict[str, Any]:
    if not isinstance(catalyst, Mapping):
        return {
            "status": FITNESS_UNAVAILABLE,
            "source_artifact_identity": None,
            "source_session_or_data_as_of": None,
            "freshness": None,
            "authority_tier": None,
            "reason_codes": ["NO_CATALYST_INPUT_REGISTERED_THIS_SESSION"],
            "fitness": FITNESS_UNAVAILABLE,
            "online_enrichment": ENRICHMENT_EXTERNAL_MAY_BE_REQUIRED,
        }
    research_session = catalyst.get("research_session")
    if research_session and research_session != session:
        envelope = freshness_envelope(
            domain="corporate_events", as_of_date=research_session, generated_at=research_session,
            source="catalyst_event_research_context", reference_at=session,
        )
        return {
            "status": "AVAILABLE_EARLIER_RETAINED",
            "source_artifact_identity": catalyst.get("artifact_identity"),
            "source_session_or_data_as_of": research_session,
            "freshness": envelope,
            "authority_tier": "RESEARCH_USABLE_DEGRADED_ACCEPTED",
            "reason_codes": ["EARLIER_RETAINED_CATALYST_CONTEXT"],
            "fitness": _FRESHNESS_TO_FITNESS.get(envelope["freshness_status"], FITNESS_STALE),
            "online_enrichment": ENRICHMENT_EXTERNAL_MAY_BE_REQUIRED,
        }
    return {
        "status": "AVAILABLE_EXACT_SESSION",
        "source_artifact_identity": catalyst.get("artifact_identity"),
        "source_session_or_data_as_of": research_session or session,
        "freshness": {"freshness_status": "current", "expected_update_frequency": "event_driven"},
        "authority_tier": "RESEARCH_USABLE_EXACT_SESSION",
        "reason_codes": [],
        "fitness": FITNESS_CURRENT,
        "online_enrichment": ENRICHMENT_PARTIAL,
    }


def _macro_domain(
    macro_context: Mapping[str, Any] | None, macro_presentation_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    regime_status = (macro_context or {}).get("status", "UNAVAILABLE")
    presentation = macro_presentation_context or {}
    presentation_status = presentation.get("status", "UNAVAILABLE")
    if presentation_status == "AVAILABLE":
        fitness = FITNESS_CURRENT
    elif presentation_status == "PARTIAL":
        fitness = FITNESS_PARTIAL
    else:
        fitness = FITNESS_UNAVAILABLE
    reason_codes = []
    if regime_status != "AVAILABLE":
        reason_codes.append("CURRENT_MACRO_REGIME_V1_NOT_BOUND:" + str((macro_context or {}).get("reason") or "UNAVAILABLE"))
    if presentation_status != "AVAILABLE":
        reason_codes.append("MACRO_PRESENTATION_CONTEXT:" + str(presentation.get("reason_code") or presentation_status))
    return {
        "status": presentation_status,
        "source_artifact_identity": presentation.get("artifact_identity"),
        "source_session_or_data_as_of": presentation.get("snapshot_data_as_of"),
        "freshness": presentation.get("quality"),
        "authority_tier": "DESCRIPTIVE_CURRENT_RESEARCH_ONLY" if presentation_status != "UNAVAILABLE" else None,
        "reason_codes": reason_codes,
        "fitness": fitness,
        "online_enrichment": ENRICHMENT_SUFFICIENT if fitness == FITNESS_CURRENT else (
            ENRICHMENT_PARTIAL if fitness == FITNESS_PARTIAL else ENRICHMENT_EXTERNAL_MAY_BE_REQUIRED
        ),
        "regime_evidence": {
            "contract_version": "current_macro_regime/v1",
            "status": regime_status,
            "reason": (macro_context or {}).get("reason"),
        },
        "presentation_context": {
            "contract_version": "macro_presentation_context/v1",
            "status": presentation_status,
        },
    }


def _market_flow_domain(flow: Mapping[str, Any] | None, *, session: str, macro_presentation_context: Mapping[str, Any] | None) -> dict[str, Any]:
    """Three genuinely distinct flow evidence classes, never collapsed into one label:
    (1) the qualified DNSE value-flow projection bound as ``market_flow_positioning`` when a
    genuinely same-session artifact exists; (2) the macro-snapshot's own foreign-flow slot,
    which macro_sync.py always reports unavailable today; (3) any broader proprietary
    trading-flow capability, which does not exist in this milestone and is never inferred."""
    if isinstance(flow, Mapping):
        qualified = {
            "status": "AVAILABLE_EXACT_SESSION",
            "source_artifact_identity": flow.get("artifact_identity"),
            "source_session_or_data_as_of": flow.get("session") or session,
            "fitness": FITNESS_CURRENT,
            "reason_codes": [],
        }
    else:
        qualified = {
            "status": FITNESS_UNAVAILABLE,
            "source_artifact_identity": None,
            "source_session_or_data_as_of": None,
            "fitness": FITNESS_UNAVAILABLE,
            "reason_codes": ["NO_COMPATIBLE_CURRENT_MARKET_FLOW_ARTIFACT"],
        }
    macro_foreign_flow = (macro_presentation_context or {}).get("foreign_flow") or {"status": "UNAVAILABLE", "reason": None}
    proprietary = {
        "status": FITNESS_UNAVAILABLE,
        "reason_codes": ["NO_PROPRIETARY_FLOW_CAPABILITY_THIS_MILESTONE"],
    }
    overall_fitness = qualified["fitness"]
    return {
        "status": qualified["status"],
        "source_artifact_identity": qualified["source_artifact_identity"],
        "source_session_or_data_as_of": qualified["source_session_or_data_as_of"],
        "freshness": None,
        "authority_tier": "RESEARCH_USABLE_PROVIDER_LIMITED" if overall_fitness == FITNESS_CURRENT else None,
        "reason_codes": qualified["reason_codes"],
        "fitness": overall_fitness,
        "online_enrichment": ENRICHMENT_SUFFICIENT if overall_fitness == FITNESS_CURRENT else ENRICHMENT_EXTERNAL_MAY_BE_REQUIRED,
        "qualified_dnse_value_flow": qualified,
        "macro_snapshot_foreign_flow": {
            "status": str(macro_foreign_flow.get("status") or "UNAVAILABLE").upper(),
            "reason": macro_foreign_flow.get("reason"),
        },
        "proprietary_flow": proprietary,
    }


def _integrated_decision_domain(integrated_delivery: Mapping[str, Any] | None, *, session: str) -> dict[str, Any]:
    product = (integrated_delivery or {}).get("integrated_investment_decision_product") if isinstance(integrated_delivery, Mapping) else None
    if not isinstance(product, Mapping):
        return {
            "status": FITNESS_UNAVAILABLE,
            "source_artifact_identity": None,
            "source_session_or_data_as_of": None,
            "freshness": None,
            "authority_tier": None,
            "reason_codes": ["NO_INTEGRATED_DECISION_PRODUCT_BOUND_THIS_SESSION"],
            "fitness": FITNESS_UNAVAILABLE,
            "online_enrichment": ENRICHMENT_EXTERNAL_MAY_BE_REQUIRED,
        }
    return {
        "status": "AVAILABLE_EXACT_SESSION",
        "source_artifact_identity": product.get("artifact_identity"),
        "source_session_or_data_as_of": session,
        "freshness": {"freshness_status": "current", "expected_update_frequency": "1_market_day"},
        "authority_tier": "RESEARCH_OVERLAY_NOT_EXECUTION_AUTHORITY",
        "reason_codes": [],
        "fitness": FITNESS_CURRENT,
        "online_enrichment": ENRICHMENT_SUFFICIENT,
    }


def build_source_freshness_matrix(
    *,
    session: str,
    inputs: Mapping[str, Any],
    macro_context: Mapping[str, Any] | None,
    macro_presentation_context: Mapping[str, Any] | None,
    flow: Mapping[str, Any] | None,
    integrated_delivery: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    descriptive = inputs.get("descriptive")
    domains = {
        "market_price_descriptive": _same_session_domain(
            artifact=descriptive, session=session, session_field="session", domain_label="DESCRIPTIVE",
        ),
        "breadth": {
            **_same_session_domain(artifact=descriptive, session=session, session_field="session", domain_label="BREADTH"),
            "reason_codes": ["EMBEDDED_IN_DESCRIPTIVE_MARKET_BREADTH_FIELD"] if isinstance(descriptive, Mapping) else ["NO_BREADTH_INPUT_REGISTERED_THIS_SESSION"],
        },
        "sector": {
            **_same_session_domain(artifact=descriptive, session=session, session_field="session", domain_label="SECTOR"),
            "reason_codes": ["SECTOR_CONTEXT_EMBEDDED_NOT_A_STANDALONE_SESSION_INPUT"] if isinstance(descriptive, Mapping) else ["NO_SECTOR_INPUT_REGISTERED_THIS_SESSION"],
        },
        "tactical": _same_session_domain(
            artifact=inputs.get("tactical"), session=session, session_field=None, domain_label="TACTICAL",
        ),
        "screening": _same_session_domain(
            artifact=inputs.get("screening"), session=session, session_field=None, domain_label="SCREENING",
        ),
        "fundamentals": _fundamentals_domain(inputs.get("fundamental"), session=session),
        "valuation": _same_session_domain(
            artifact=inputs.get("valuation"), session=session, session_field="valuation_session", domain_label="VALUATION",
        ),
        "corporate_intelligence": _same_session_domain(
            artifact=inputs.get("corporate_intelligence"), session=session, session_field="session",
            domain_label="CORPORATE_INTELLIGENCE",
        ),
        "catalyst_event": _catalyst_domain(inputs.get("catalyst"), session=session),
        "macro": _macro_domain(macro_context, macro_presentation_context),
        "market_flow_positioning": _market_flow_domain(flow, session=session, macro_presentation_context=macro_presentation_context),
        "integrated_decision": _integrated_decision_domain(integrated_delivery, session=session),
    }
    enrichment_recommended = sorted(
        name for name, row in domains.items() if row["online_enrichment"] == ENRICHMENT_EXTERNAL_MAY_BE_REQUIRED
    )
    internally_sufficient = sorted(
        name for name, row in domains.items() if row["online_enrichment"] == ENRICHMENT_SUFFICIENT
    )
    return {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "session": session,
        "domains": domains,
        "online_enrichment_guidance": {
            "internally_sufficient_domains": internally_sufficient,
            "domains_where_external_context_may_be_required": enrichment_recommended,
            "notice": (
                "This guidance is derived mechanically from internal freshness/availability only. "
                "It never embeds live web research and never establishes Producer factual authority "
                "for anything found online."
            ),
        },
        "is_actionable": False,
    }
