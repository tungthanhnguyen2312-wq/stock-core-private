"""Current-research Corporate Intelligence axis: catalyst/risk/materiality/freshness
classification over retained corporate-event evidence.

CORPORATE_INTELLIGENCE_CATALYST_EVENT_RISK_DECISION_INTEGRATION_V1.

This module adds exactly what does not exist anywhere else in the corporate-intelligence
stack: a canonical event-type taxonomy, a canonical event-status ladder, a deterministic
catalyst/risk/mixed/informational classification, and one compact per-ticker axis suitable
for additive Integrated Decision wiring. It does not crawl events, acquire new evidence,
infer dates, compute price impact, assign probability, or replace research_action_posture.

Reuses, rather than reimplements:
  - current_corporate_event_context.py for the deduplicated, conflict-checked per-event
    evidence (already carries event_type, event_status, materiality_status, evidence_tier,
    and every corporate-action date field this contract needs). Its existing but, in the
    standing canonical_post_close_pipeline enrichment build, unused `supplemental_events`
    parameter is activated here (via `load_supplemental_retained_events`) to include the
    three retained issuer/VSDC chains (HPG executed corporate action, VNM executed dividend,
    VCB approved stock dividend) that build does not pass in. This module builds its own
    copy of the event-context artifact with that parameter populated rather than modifying
    the shared enrichment component other consumers (current_research_risk_register.py,
    current_research_decision_packet.py) already depend on byte-for-byte.
  - market_wide_current_corporate_intelligence.py for the honest UNAVAILABLE ownership/
    governance placeholders (no retained market-wide shareholder or board-change corpus
    exists yet; this module never invents one) and for cross-checking its own artifact
    identity in source lineage.
  - bitemporal_semantic_contract.py's existing CORPORATE_EVENT domain for temporal/PIT
    fitness (READY/PARTIAL/VALID_TIME_INSUFFICIENT/UNKNOWN) -- no second temporal-fitness
    ladder is invented.

Catalyst/risk classification (classify_catalyst_risk) depends only on
(canonical event type, canonical status, original event-status), never on keyword sentiment,
and is deliberately conservative: most event types classify as INFORMATIONAL or MIXED rather
than a one-directional catalyst or risk, because a bare event type is rarely enough to know
direction (e.g. a dividend announcement is not automatically bullish; new borrowing is not
automatically negative if terms are unknown).
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

import bitemporal_semantic_contract as bitemporal
import current_corporate_event_context as event_context_module

CONTRACT_VERSION = "current_corporate_intelligence_axis/v1"
ARTIFACT_TYPE = "CURRENT_CORPORATE_INTELLIGENCE_AXIS"
MILESTONE = "CORPORATE_INTELLIGENCE_CATALYST_EVENT_RISK_DECISION_INTEGRATION_V1"

# Reuses market_wide_current_corporate_intelligence._freshness's own 90-day resolved-recency
# window; current_corporate_event_context.RECENT_WINDOW_DAYS (30) already governs the
# upstream ACTIVE/RECENT event-status split this module reads, not reinvented here.
RESOLVED_RECENT_WINDOW_DAYS = 90

# ── Per-ticker axis state ──────────────────────────────────────────────────────
NO_QUALIFIED_CORPORATE_EVENT = "NO_QUALIFIED_CORPORATE_EVENT"
CATALYST_PRESENT = "CATALYST_PRESENT"
RISK_PRESENT = "RISK_PRESENT"
MIXED_EVIDENCE = "MIXED_EVIDENCE"
INFORMATIONAL_ONLY = "INFORMATIONAL_ONLY"
UNRESOLVED_EVIDENCE = "UNRESOLVED_EVIDENCE"
TICKER_STATES = (
    NO_QUALIFIED_CORPORATE_EVENT, CATALYST_PRESENT, RISK_PRESENT,
    MIXED_EVIDENCE, INFORMATIONAL_ONLY, UNRESOLVED_EVIDENCE,
)

# ── Per-event catalyst/risk interpretation ──────────────────────────────────────
POTENTIAL_CATALYST = "POTENTIAL_CATALYST"
POTENTIAL_RISK = "POTENTIAL_RISK"
MIXED = "MIXED"
INFORMATIONAL = "INFORMATIONAL"
UNRESOLVED = "UNRESOLVED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
CATALYST_RISK_CLASSIFICATIONS = (
    POTENTIAL_CATALYST, POTENTIAL_RISK, MIXED, INFORMATIONAL, UNRESOLVED, INSUFFICIENT_EVIDENCE,
)

# ── Canonical event status ladder (Section 4/7) ─────────────────────────────────
ANNOUNCED = "ANNOUNCED"
PLANNED = "PLANNED"
APPROVED = "APPROVED"
EXECUTED = "EXECUTED"
COMPLETED = "COMPLETED"
CANCELLED = "CANCELLED"
STATUS_UNKNOWN = "UNKNOWN"
CANONICAL_STATUSES = (ANNOUNCED, PLANNED, APPROVED, EXECUTED, COMPLETED, CANCELLED, STATUS_UNKNOWN)

# ── Canonical event taxonomy (Section 6) ────────────────────────────────────────
EARNINGS_BUSINESS_UPDATE = "EARNINGS_BUSINESS_UPDATE"
DIVIDEND = "DIVIDEND"
CAPITAL_INCREASE = "CAPITAL_INCREASE"
BONUS_ISSUE = "BONUS_ISSUE"
RIGHTS_ISSUE = "RIGHTS_ISSUE"
SHARE_REPURCHASE = "SHARE_REPURCHASE"
SHARE_ISSUANCE = "SHARE_ISSUANCE"
DEBT_FINANCING = "DEBT_FINANCING"
ASSET_ACQUISITION = "ASSET_ACQUISITION"
ASSET_DISPOSAL = "ASSET_DISPOSAL"
M_AND_A = "M_AND_A"
NEW_PROJECT = "NEW_PROJECT"
MAJOR_CONTRACT = "MAJOR_CONTRACT"
SUBSIDIARY_EVENT = "SUBSIDIARY_EVENT"
OWNERSHIP_CHANGE = "OWNERSHIP_CHANGE"
MANAGEMENT_GOVERNANCE = "MANAGEMENT_GOVERNANCE"
REGULATORY_LEGAL = "REGULATORY_LEGAL"
RESTRUCTURING = "RESTRUCTURING"
AUDIT_ACCOUNTING = "AUDIT_ACCOUNTING"
GUIDANCE_PLAN_TARGET = "GUIDANCE_PLAN_TARGET"
OTHER_MATERIAL_EVENT = "OTHER_MATERIAL_EVENT"
EVENT_TAXONOMY = (
    EARNINGS_BUSINESS_UPDATE, DIVIDEND, CAPITAL_INCREASE, BONUS_ISSUE, RIGHTS_ISSUE,
    SHARE_REPURCHASE, SHARE_ISSUANCE, DEBT_FINANCING, ASSET_ACQUISITION, ASSET_DISPOSAL,
    M_AND_A, NEW_PROJECT, MAJOR_CONTRACT, SUBSIDIARY_EVENT, OWNERSHIP_CHANGE,
    MANAGEMENT_GOVERNANCE, REGULATORY_LEGAL, RESTRUCTURING, AUDIT_ACCOUNTING,
    GUIDANCE_PLAN_TARGET, OTHER_MATERIAL_EVENT,
)

# Raw event_type strings observed across current_corporate_event_context /
# market_wide_current_corporate_intelligence -> canonical taxonomy. An unmapped or ambiguous
# raw type falls back to OTHER_MATERIAL_EVENT rather than being forced into a specific
# category (mission Section 6: "Do not force ambiguous evidence into a specific category").
# Every already-canonical taxonomy value maps to itself first (idempotent: safe to call twice,
# and forward-compatible if an upstream source ever starts emitting a canonical-shaped type
# directly), then explicit raw-source spellings override/collapse onto their canonical bucket.
#
# CORPORATE_EVENT_CANONICAL_DATA_REFRESH_AND_LEDGER_CONSOLIDATION_V1 root-caused five live raw
# "bonus issue" spellings across the wider corporate-action stack: bonus_issue
# (corporate_actions.py / share_basis_event_promotion.py -- already converges via the identity
# seed above, since BONUS_ISSUE is itself a canonical taxonomy member), BONUS/BONUS_ISSUE
# (current_official_event_context.py), BONUS_OR_STOCK_DIVIDEND (market_wide_current_corporate_
# intelligence.py), and the two raw PIT-ledger spellings bonus_shares (official_corporate_
# action_ledger.py, corporate_action_events.py) and bonus_share (corporate_action_ledger.py,
# corporate_action_factors.py, distribution_evidence.py) -- plus the DNSE price-basis compound
# stock_dividend_bonus_issue. Neither raw PIT ledger currently feeds this axis (see
# ledger_reconciliation.json: they serve PIT/price-adjustment authority, a distinct use case,
# and their own native vocabulary is preserved unmodified, per-module, per DATA_FIRST_DOCTRINE).
# These three additional aliases guarantee that if a future milestone ever does connect that raw
# vocabulary here, none of it silently falls into OTHER_MATERIAL_EVENT as an independent event
# family instead of BONUS_ISSUE.
_RAW_EVENT_TYPE_MAP: dict[str, str] = {value: value for value in EVENT_TAXONOMY}
_RAW_EVENT_TYPE_MAP.update({
    "CASH_DIVIDEND": DIVIDEND,
    "STOCK_DIVIDEND": BONUS_ISSUE,
    "BONUS": BONUS_ISSUE,
    "BONUS_OR_STOCK_DIVIDEND": BONUS_ISSUE,
    "BONUS_SHARES": BONUS_ISSUE,
    "BONUS_SHARE": BONUS_ISSUE,
    "STOCK_DIVIDEND_BONUS_ISSUE": BONUS_ISSUE,
    "RIGHTS": RIGHTS_ISSUE,
    "AGM": MANAGEMENT_GOVERNANCE,
    "CORPORATE_ACTION": OTHER_MATERIAL_EVENT,
    "OTHER": OTHER_MATERIAL_EVENT,
    "UNKNOWN": OTHER_MATERIAL_EVENT,
})

# current_corporate_event_context.EVENT_STATUSES -> canonical status. This is a coarser,
# additive projection of a richer field; original_event_status is always preserved verbatim
# on the classified event (mission Section 7: never silently rewrite the historical event).
_EVENT_STATUS_TO_CANONICAL = {
    "CONFIRMED_UPCOMING": APPROVED,
    "CONFIRMED_RECENT": EXECUTED,
    "EXECUTED": EXECUTED,
    "PLANNED_NOT_EXECUTED": PLANNED,
    "CANCELLED": CANCELLED,
    "TEMPORAL_DETAILS_INCOMPLETE": STATUS_UNKNOWN,
    "CONFLICTING_EVIDENCE": STATUS_UNKNOWN,
    "DATA_LIMITED": STATUS_UNKNOWN,
}

ACTIVE_EVENT_STATUSES = frozenset({"CONFIRMED_UPCOMING", "CONFIRMED_RECENT", "PLANNED_NOT_EXECUTED"})
RESOLVED_EVENT_STATUSES = frozenset({"EXECUTED", "CANCELLED"})

# ── Freshness / event window (Section 10) ───────────────────────────────────────
FRESHNESS_ACTIVE = "ACTIVE"
FRESHNESS_RESOLVED_RECENT = "RESOLVED_RECENT"
FRESHNESS_RESOLVED_HISTORICAL = "RESOLVED_HISTORICAL"
FRESHNESS_UNKNOWN = "UNKNOWN"
FRESHNESS_STATES = (FRESHNESS_ACTIVE, FRESHNESS_RESOLVED_RECENT, FRESHNESS_RESOLVED_HISTORICAL, FRESHNESS_UNKNOWN)
_RESOLVED_FRESHNESS = frozenset({FRESHNESS_ACTIVE, FRESHNESS_RESOLVED_RECENT})

# ── Materiality (Section 9) ──────────────────────────────────────────────────────
MATERIAL = "MATERIAL"
POTENTIALLY_MATERIAL = "POTENTIALLY_MATERIAL"
NON_MATERIAL = "NON_MATERIAL"
UNKNOWN_MATERIALITY = "UNKNOWN_MATERIALITY"
MATERIALITY_STATES = (MATERIAL, POTENTIALLY_MATERIAL, NON_MATERIAL, UNKNOWN_MATERIALITY)
_MATERIAL_STATES = frozenset({MATERIAL, POTENTIALLY_MATERIAL})

FORBIDDEN_USES = (
    "price_impact", "probability", "target_price", "universal_score",
    "automatic_policy_retuning", "authority_promotion", "research_priority",
    "entry_action", "recommendation", "sizing", "event_driven_eligibility",
)


class CorporateIntelligenceAxisError(ValueError):
    """A retained input did not meet this axis's exact research contract."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact))
    payload.pop("artifact_sha256", None)
    payload.pop("artifact_identity", None)
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"current_corporate_intelligence_axis:{digest}"}


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def canonical_event_type(raw_event_type: str | None) -> str:
    return _RAW_EVENT_TYPE_MAP.get(str(raw_event_type or "").upper(), OTHER_MATERIAL_EVENT)


def canonical_status(event_status: str | None) -> str:
    return _EVENT_STATUS_TO_CANONICAL.get(str(event_status or ""), STATUS_UNKNOWN)


def canonical_materiality(materiality_status: str | None) -> str:
    """Fails closed to POTENTIALLY_MATERIAL, never MATERIAL: no compatible amount-vs-denominator
    comparison (event amount vs. market cap/revenue) is available from retained evidence
    (mission Section 9 -- never compare an event amount to a denominator when currency/scale
    is unresolved, and never invent a magnitude threshold)."""
    if materiality_status == "PRICE_SHARE_AFFECTING":
        return POTENTIALLY_MATERIAL
    if materiality_status == "INFORMATIONAL_GOVERNANCE":
        return NON_MATERIAL
    return UNKNOWN_MATERIALITY


def canonical_freshness(original_event_status: str | None, *, as_of: date, event_date: date | None) -> str:
    """Reuses current_corporate_event_context's own ACTIVE/RESOLVED event-status split and
    market_wide_current_corporate_intelligence's own 90-day resolved-recency window -- no new
    freshness window is invented here."""
    status = str(original_event_status or "")
    if status in ACTIVE_EVENT_STATUSES:
        return FRESHNESS_ACTIVE
    if status in RESOLVED_EVENT_STATUSES:
        if event_date is None:
            return FRESHNESS_UNKNOWN
        return FRESHNESS_RESOLVED_RECENT if (as_of - event_date).days <= RESOLVED_RECENT_WINDOW_DAYS else FRESHNESS_RESOLVED_HISTORICAL
    return FRESHNESS_UNKNOWN


def classify_catalyst_risk(
    *, event_type: str, status: str, original_event_status: str, materiality: str = UNKNOWN_MATERIALITY,
) -> tuple[str, list[str]]:
    """Deterministic catalyst/risk/mixed/informational classification.

    Depends only on (canonical event type, canonical status, original event-status, and the
    already-computed, non-inferred materiality state); never on keyword sentiment or narrative
    text. Conflicting or temporally/data-limited evidence fails closed to UNRESOLVED/
    INSUFFICIENT_EVIDENCE before any type-specific rule runs (mission Section 11: conflicts
    fail closed for any dependent authoritative use; no evidence-count voting).
    """
    if original_event_status == "CONFLICTING_EVIDENCE":
        return UNRESOLVED, ["CONFLICTING_EVIDENCE_BLOCKS_CLASSIFICATION"]
    if original_event_status in {"TEMPORAL_DETAILS_INCOMPLETE", "DATA_LIMITED"}:
        return INSUFFICIENT_EVIDENCE, ["TEMPORAL_OR_DATA_LIMITATION_BLOCKS_CLASSIFICATION"]
    if status == CANCELLED:
        return INFORMATIONAL, ["CANCELLED_EVENT_NO_LONGER_PENDING"]

    if event_type == DIVIDEND:
        return INFORMATIONAL, ["DIVIDEND_IS_NOT_AUTOMATICALLY_BULLISH"]
    if event_type == BONUS_ISSUE:
        return INFORMATIONAL, ["BONUS_OR_STOCK_DIVIDEND_IS_SHARE_COUNT_NEUTRAL_NOT_DILUTIVE_BY_ITSELF"]
    if event_type in {RIGHTS_ISSUE, SHARE_ISSUANCE, CAPITAL_INCREASE}:
        if status == EXECUTED:
            return MIXED, ["EXECUTED_ISSUANCE_RAISES_CAPITAL", "EXECUTED_ISSUANCE_MAY_DILUTE_EXISTING_HOLDERS"]
        return POTENTIAL_RISK, ["PLANNED_OR_APPROVED_ISSUANCE_MAY_DILUTE_PENDING_EXECUTION"]
    if event_type == SHARE_REPURCHASE:
        if status == EXECUTED:
            return POTENTIAL_CATALYST, ["EXECUTED_REPURCHASE_RETURNS_CAPITAL_AND_REDUCES_SHARE_COUNT"]
        return INFORMATIONAL, ["PLANNED_REPURCHASE_NOT_YET_EXECUTED"]
    if event_type == ASSET_DISPOSAL:
        if status == EXECUTED:
            return POTENTIAL_CATALYST, ["EXECUTED_DISPOSAL_MAY_SUPPORT_DELEVERAGING_OR_MONETIZATION"]
        return INFORMATIONAL, ["PLANNED_DISPOSAL_NOT_YET_EXECUTED"]
    if event_type == DEBT_FINANCING:
        return INFORMATIONAL, ["DEBT_FINANCING_DIRECTION_AND_TERMS_UNKNOWN_FROM_EVENT_TYPE_ALONE"]
    if event_type in {ASSET_ACQUISITION, M_AND_A, NEW_PROJECT, MAJOR_CONTRACT, SUBSIDIARY_EVENT,
                       GUIDANCE_PLAN_TARGET, EARNINGS_BUSINESS_UPDATE}:
        return INFORMATIONAL, ["EVENT_IS_CONTEXT_NOT_A_RECOGNIZED_FINANCIAL_OUTCOME"]
    if event_type == REGULATORY_LEGAL:
        if status in {EXECUTED, CANCELLED, COMPLETED}:
            return INFORMATIONAL, ["REGULATORY_OR_LEGAL_MATTER_RESOLVED_OR_CLOSED"]
        return POTENTIAL_RISK, ["UNRESOLVED_REGULATORY_OR_LEGAL_MATTER"]
    if event_type == AUDIT_ACCOUNTING:
        return POTENTIAL_RISK, ["AUDIT_OR_ACCOUNTING_EVENT_CONVENTIONALLY_RISK_ORIENTED"]
    if event_type in {RESTRUCTURING, MANAGEMENT_GOVERNANCE, OWNERSHIP_CHANGE}:
        # A routine, already-materiality-screened governance event (the common case: an AGM
        # notice carrying current_official_event_context's own INFORMATIONAL_GOVERNANCE
        # materiality) is not evidence of an actual management/ownership change. Only a
        # governance event the upstream materiality gate could not screen out as routine
        # remains genuinely direction-ambiguous.
        if materiality == NON_MATERIAL:
            return INFORMATIONAL, ["ROUTINE_GOVERNANCE_EVENT_NOT_PRICE_SHARE_AFFECTING"]
        return MIXED, ["DIRECTION_NOT_DETERMINABLE_FROM_EVENT_TYPE_ALONE"]
    return INSUFFICIENT_EVIDENCE, ["EVENT_TYPE_NOT_MAPPED_TO_A_KNOWN_CATALYST_RISK_RULE"]


def classify_event(raw_event: Mapping[str, Any], *, as_of: date) -> dict[str, Any]:
    """Attach canonical taxonomy, canonical status, materiality, freshness, catalyst/risk
    classification, and temporal/PIT fitness on top of one already-normalized, already-
    deduplicated current_corporate_event_context event. Never re-derives ticker, event
    identity, dates, or conflict state -- those remain that module's own authority.
    """
    event_type = canonical_event_type(raw_event.get("event_type"))
    original_status = str(raw_event.get("event_status") or "")
    status = canonical_status(original_status)
    materiality = canonical_materiality(raw_event.get("materiality_status"))
    event_date = (
        _parse_date(raw_event.get("ex_date"))
        or _parse_date(raw_event.get("execution_date"))
        or _parse_date(raw_event.get("record_date"))
        or _parse_date(raw_event.get("announcement_date"))
    )
    freshness = canonical_freshness(original_status, as_of=as_of, event_date=event_date)
    classification, reason_codes = classify_catalyst_risk(
        event_type=event_type, status=status, original_event_status=original_status, materiality=materiality,
    )
    valid_time = bitemporal.validate_valid_time(
        domain="CORPORATE_EVENT",
        event_type=raw_event.get("event_type"),
        event_dates={
            "record_date": raw_event.get("record_date"),
            "ex_date": raw_event.get("ex_date"),
            "execution_date": raw_event.get("execution_date"),
            "effective_date": raw_event.get("effective_date"),
            "announcement_date": raw_event.get("announcement_date"),
        },
    )
    return {
        "event_id": raw_event.get("event_id"),
        "ticker": raw_event.get("ticker"),
        "event_type": event_type,
        "event_subtype": raw_event.get("event_type"),
        "original_event_status": original_status,
        "status": status,
        "materiality": materiality,
        "freshness": freshness,
        "classification": classification,
        "reason_codes": list(reason_codes),
        "evidence_tier": raw_event.get("evidence_tier"),
        "source": raw_event.get("source"),
        "source_identities": list(raw_event.get("source_identities") or []),
        "announcement_date": raw_event.get("announcement_date"),
        "record_date": raw_event.get("record_date"),
        "ex_date": raw_event.get("ex_date"),
        "effective_date": raw_event.get("effective_date"),
        "execution_date": raw_event.get("execution_date"),
        "temporal_completeness": raw_event.get("temporal_completeness"),
        "temporal_fitness": valid_time.fitness_status.value,
        "temporal_fitness_warnings": list(valid_time.warnings),
        "conflicts": list(raw_event.get("conflicts") or []),
        "warnings": list(raw_event.get("warnings") or []),
        "limitations": list(raw_event.get("blockers") or []) + [
            "NOT_EVENT_DRIVEN_ELIGIBILITY", "NOT_PRICE_IMPACT", "NOT_PROBABILITY", "NOT_TARGET_PRICE",
        ],
    }


def _event_sort_key(event: Mapping[str, Any]) -> tuple[str, str]:
    when = event.get("ex_date") or event.get("execution_date") or event.get("record_date") or event.get("announcement_date") or ""
    return (str(when), str(event.get("event_id")))


def _ticker_axis(ticker: str, session: str, classified_events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    active = [event for event in classified_events if event["freshness"] in _RESOLVED_FRESHNESS]
    active_catalysts = [event for event in active if event["classification"] == POTENTIAL_CATALYST]
    active_risks = [event for event in active if event["classification"] == POTENTIAL_RISK]
    active_mixed_or_unresolved = [event for event in active if event["classification"] in {MIXED, UNRESOLVED, INSUFFICIENT_EVIDENCE}]
    mixed_or_unresolved_events = [event for event in classified_events if event["classification"] in {MIXED, UNRESOLVED, INSUFFICIENT_EVIDENCE}]
    material_events = [event for event in classified_events if event["materiality"] in _MATERIAL_STATES]

    if not classified_events:
        state = NO_QUALIFIED_CORPORATE_EVENT
    elif active_catalysts and active_risks:
        state = MIXED_EVIDENCE
    elif active_catalysts:
        state = CATALYST_PRESENT
    elif active_risks:
        state = RISK_PRESENT
    elif active_mixed_or_unresolved:
        state = UNRESOLVED_EVIDENCE
    else:
        # Either only-informational active events, or every retained event is resolved-
        # historical -- still real evidence, just never re-labelled an active catalyst/risk
        # (mission Section 10: do not keep stale resolved events forever as active catalysts).
        state = INFORMATIONAL_ONLY

    freshest_material_event = (
        max(material_events, key=_event_sort_key)["event_id"] if material_events else None
    )
    supporting = sorted({code for event in active_catalysts for code in event["reason_codes"]})
    contradicting = sorted({code for event in active_risks for code in event["reason_codes"]})
    blockers = sorted(
        {code for event in mixed_or_unresolved_events for code in event["reason_codes"]}
        | {warning for event in classified_events for warning in event.get("warnings", [])}
    )
    limitations = sorted({item for event in classified_events for item in event.get("limitations", [])})
    if not classified_events:
        limitations = ["NO_RETAINED_CORPORATE_EVENT_EVIDENCE_FOR_THIS_TICKER"]

    ordered_events = sorted(classified_events, key=_event_sort_key)
    return {
        "ticker": ticker,
        "research_session": session,
        "state": state,
        "fitness": "AVAILABLE" if classified_events else NO_QUALIFIED_CORPORATE_EVENT,
        "active_catalysts": [event["event_id"] for event in active_catalysts],
        "active_risks": [event["event_id"] for event in active_risks],
        "mixed_or_unresolved_events": [event["event_id"] for event in mixed_or_unresolved_events],
        "material_event_count": len(material_events),
        "freshest_material_event": freshest_material_event,
        "supporting_reason_codes": supporting,
        "contradicting_reason_codes": contradicting,
        "blockers": blockers,
        "event_identities": [event["event_id"] for event in ordered_events],
        "events": ordered_events,
        "limitations": limitations,
        "does_not_enable_event_driven": True,
        "does_not_change_action_posture": True,
    }


def build_artifact(
    *,
    official_universe: Mapping[str, Any],
    official_event_context: Mapping[str, Any],
    root: Path,
    research_session: str | None = None,
    market_wide_current_corporate_intelligence: Mapping[str, Any] | None = None,
    include_supplemental_events: bool = True,
) -> dict[str, Any]:
    """Build the market-wide Corporate Intelligence axis artifact for one Current-Research
    session. `root` is the Producer workspace root used only to read the already-retained
    supplemental issuer/VSDC evidence chains (never a fresh acquisition)."""
    session = research_session or str(official_event_context.get("research_session") or "")
    if not session:
        raise CorporateIntelligenceAxisError("RESEARCH_SESSION_REQUIRED")
    as_of = date.fromisoformat(session)
    supplemental = (
        event_context_module.load_supplemental_retained_events(root, session)
        if include_supplemental_events else None
    )
    event_context_artifact = event_context_module.build_artifact(
        official_universe=official_universe,
        official_event_context=official_event_context,
        supplemental_events=supplemental,
        research_session=session,
    )

    records: dict[str, Any] = {}
    all_events: list[dict[str, Any]] = []
    for ticker, row in sorted(event_context_artifact.get("records", {}).items()):
        classified = [classify_event(event, as_of=as_of) for event in row.get("events", [])]
        records[ticker] = _ticker_axis(ticker, session, classified)
        all_events.extend(classified)

    ownership_governance_reason = "No retained market-wide current shareholder or management/board-change corpus is available."
    if isinstance(market_wide_current_corporate_intelligence, Mapping):
        sample = next(iter((market_wide_current_corporate_intelligence.get("records") or {}).values()), {})
        ownership_governance_reason = (sample.get("ownership_context") or {}).get("reason", ownership_governance_reason)

    coverage = {
        "universe_denominator": len(records),
        "tickers_with_any_corporate_intelligence": sum(1 for row in records.values() if row["event_identities"]),
        "state_distribution": dict(sorted(Counter(row["state"] for row in records.values()).items())),
        "event_type_distribution": dict(sorted(Counter(event["event_type"] for event in all_events).items())),
        "event_status_distribution": dict(sorted(Counter(event["status"] for event in all_events).items())),
        "original_event_status_distribution": dict(sorted(Counter(event["original_event_status"] for event in all_events).items())),
        "classification_distribution": dict(sorted(Counter(event["classification"] for event in all_events).items())),
        "materiality_distribution": dict(sorted(Counter(event["materiality"] for event in all_events).items())),
        "freshness_distribution": dict(sorted(Counter(event["freshness"] for event in all_events).items())),
        "temporal_fitness_distribution": dict(sorted(Counter(event["temporal_fitness"] for event in all_events).items())),
        "active_catalyst_ticker_count": sum(1 for row in records.values() if row["active_catalysts"]),
        "active_risk_ticker_count": sum(1 for row in records.values() if row["active_risks"]),
        "mixed_or_unresolved_ticker_count": sum(1 for row in records.values() if row["mixed_or_unresolved_events"]),
        "material_event_ticker_count": sum(1 for row in records.values() if row["material_event_count"]),
        "ownership_coverage": 0,
        "governance_coverage": 0,
        "total_classified_events": len(all_events),
        "supplemental_events_included": include_supplemental_events,
    }

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "milestone": MILESTONE,
        "research_mode": "CURRENT_RESEARCH_ONLY",
        "research_session": session,
        "source_artifact_identities": {
            "current_corporate_event_context": event_context_artifact.get("artifact_identity"),
            "market_wide_current_corporate_intelligence": (market_wide_current_corporate_intelligence or {}).get("artifact_identity"),
        },
        "event_taxonomy": list(EVENT_TAXONOMY),
        "status_ladder": list(CANONICAL_STATUSES),
        "catalyst_risk_classifications": list(CATALYST_RISK_CLASSIFICATIONS),
        "materiality_states": list(MATERIALITY_STATES),
        "freshness_states": list(FRESHNESS_STATES),
        "ticker_states": list(TICKER_STATES),
        "records": records,
        "coverage": coverage,
        "ownership_context": {"status": "UNAVAILABLE", "reason": ownership_governance_reason},
        "governance_context": {"status": "UNAVAILABLE", "reason": ownership_governance_reason},
        "blocked_outputs": {
            "event_driven_strategy": "NOT_ENABLED_BY_THIS_CONTEXT",
            "research_priority": "NOT_MODIFIED",
            "entry_action": "NOT_MODIFIED",
            "research_action_posture": "NOT_MODIFIED",
            "universal_score": "NOT_EMITTED",
            "probability": "NOT_EMITTED",
            "target_price": "NOT_EMITTED",
        },
        "authority_boundary": {
            "is_actionable": False,
            "no_automatic_posture_change": True,
            "no_universal_score_or_probability": True,
            "no_authority_promotion": True,
            "record_date_is_not_ex_date": True,
            "planned_or_approved_is_not_executed": True,
            "share_basis_unchanged_by_planned_issuance": True,
            "financial_metrics_unchanged_by_event_narrative": True,
            "raw_as_traded": "NOT_PROMOTED",
            "pit": "BLOCKED",
        },
        "prohibited_uses": list(FORBIDDEN_USES),
    }
    artifact.update(content_identity(artifact))
    return artifact


FORWARD_DRIVER_VERSION = "forward_driver_context/v1"
_FORWARD_CATEGORIES = {
    "DIVIDEND": "DISTRIBUTION_CONTEXT",
    "BONUS_ISSUE": "CAPITAL_STRUCTURE_CONTEXT",
    "RIGHTS_ISSUE": "CAPITAL_STRUCTURE_CONTEXT",
    "MANAGEMENT_GOVERNANCE": "GOVERNANCE_CONTEXT",
    "OTHER_MATERIAL_EVENT": "OTHER_EVENT_CONTEXT",
}
_FORWARD_DATES = ("announcement_date", "record_date", "ex_date", "effective_date", "execution_date")


def _driver_date(value: Any) -> date | None:
    """Only canonical ISO calendar dates; no truncation or semantic substitution."""
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        parsed = date.fromisoformat(value)
        return parsed if parsed.isoformat() == value else None
    except ValueError:
        return None


def build_forward_driver_context(record: Mapping[str, Any] | None, *,
                                 as_of_session: str, ticker: str | None = None) -> dict[str, Any]:
    """Non-voting explanatory projection of retained, classified corporate events.

    Qualification means source-qualified, temporally usable current research context,
    never directional thesis support or event-driven eligibility. Earlier source sessions
    remain PARTIAL. Resolved historical evidence is retained but not a qualified forward
    driver. Reuses the standing recency window; dates never prove execution on their own.
    V1 has no contract supporting SUPPORTIVE/ADVERSE direction from a bare event type.
    """
    source = record or {}
    source_session = source.get("research_session")
    source_day, decision_day = _driver_date(source_session), _driver_date(as_of_session)
    session_fitness = ("SOURCE_SESSION_ABSENT_OR_INVALID" if not source_day or not decision_day else
                       "FUTURE_INFORMATION_PROHIBITED" if source_day > decision_day else
                       "STALE_EVIDENCE_SESSION" if source_day < decision_day else "CURRENT_EVIDENCE_SESSION")
    session_usable = session_fitness in {"STALE_EVIDENCE_SESSION", "CURRENT_EVIDENCE_SESSION"}
    drivers = []
    identity_payloads: dict[str, set[str]] = {}
    for event in source.get("events") or []:
        identity_payloads.setdefault(str(event.get("event_id")), set()).add(
            json.dumps(event, sort_keys=True, ensure_ascii=False))
    for raw in source.get("events") or []:
        event = copy.deepcopy(raw)
        reasons = set(event.get("reason_codes") or [])
        blockers = set()
        dates = {key: event.get(key) for key in _FORWARD_DATES}
        parsed = {key: _driver_date(value) for key, value in dates.items()}
        if any(value is not None and parsed[key] is None for key, value in dates.items()):
            blockers.add("FORWARD_DRIVER_DATE_MALFORMED")
        if not any(parsed.values()):
            blockers.add("FORWARD_DRIVER_KNOWN_DATE_ABSENT")
        if source.get("fitness") not in {"AVAILABLE", "CURRENT_RESEARCH_ONLY"}:
            blockers.add("FORWARD_DRIVER_SOURCE_FITNESS_UNAVAILABLE")
        if len(identity_payloads.get(str(event.get("event_id")), set())) > 1:
            blockers.add("FORWARD_DRIVER_IDENTITY_CONFLICT")
        if not session_usable:
            blockers.add(session_fitness)
        # Scheduled future dates are valid plans, but future announcements/execution
        # cannot establish already-known/executed evidence at this decision session.
        if decision_day and (parsed["announcement_date"] and parsed["announcement_date"] > decision_day or
                             event.get("status") in {"EXECUTED", "COMPLETED"} and
                             parsed["execution_date"] and parsed["execution_date"] > decision_day):
            blockers.add("FORWARD_DRIVER_FUTURE_OBSERVATION")
        if event.get("ticker") != (source.get("ticker") or ticker):
            blockers.add("FORWARD_DRIVER_TICKER_MISMATCH")
        identities = sorted(set(str(v) for v in event.get("source_identities") or [] if v))
        if not event.get("event_id") or not identities or not event.get("source"):
            blockers.add("FORWARD_DRIVER_PROVENANCE_INCOMPLETE")
        if event.get("evidence_tier") != "OFFICIAL_QUALIFIED":
            blockers.add("FORWARD_DRIVER_SOURCE_NOT_QUALIFIED")
        if event.get("conflicts"):
            blockers.add("FORWARD_DRIVER_CONFLICTING_EVIDENCE")
        if event.get("status") not in CANONICAL_STATUSES or event.get("status") == STATUS_UNKNOWN:
            blockers.add("FORWARD_DRIVER_STATUS_UNRESOLVED")
        if event.get("temporal_fitness") not in {"READY", "PARTIAL"}:
            blockers.add("FORWARD_DRIVER_TEMPORAL_FITNESS_UNAVAILABLE")
        if event.get("classification") in {"INSUFFICIENT_EVIDENCE", "UNRESOLVED"}:
            blockers.add("FORWARD_DRIVER_CLASSIFICATION_UNRESOLVED")
        # Exactly the standing freshness date precedence, without filling absent fields.
        event_day = next((parsed[key] for key in ("ex_date", "execution_date", "record_date", "announcement_date")
                          if parsed[key]), None)
        freshness = canonical_freshness(event.get("original_event_status"), as_of=decision_day,
                                        event_date=event_day) if decision_day else FRESHNESS_UNKNOWN
        if freshness not in {FRESHNESS_ACTIVE, FRESHNESS_RESOLVED_RECENT}:
            blockers.add("FORWARD_DRIVER_NOT_CURRENT_OR_RECENT")
        direction = ("INFORMATIONAL" if event.get("classification") == "INFORMATIONAL" else
                     "MIXED" if event.get("classification") == "MIXED" else "UNKNOWN")
        if event.get("conflicts"):
            direction = "UNKNOWN"
        reasons.add("FORWARD_DRIVER_NON_VOTING_EXPLANATORY_CONTEXT")
        reasons.add("EXISTING_INFORMATIONAL_CLASSIFICATION" if direction == "INFORMATIONAL" else
                    "EXISTING_MIXED_CLASSIFICATION" if direction == "MIXED" else "DIRECTION_NOT_ESTABLISHED")
        qualified = not blockers
        fitness = ("PARTIAL" if session_fitness == "STALE_EVIDENCE_SESSION" or
                   event.get("temporal_fitness") == "PARTIAL" else "AVAILABLE") if qualified else "BLOCKED"
        driver = dict(ticker=source.get("ticker") or ticker, as_of_session=as_of_session,
                      evidence_session=source_session, event_identity=event.get("event_id"),
                      event_type=event.get("event_type"), event_subtype=event.get("event_subtype"),
                      status=event.get("status"), original_event_status=event.get("original_event_status"),
                      known_dates=dates, evidence_tier=event.get("evidence_tier"),
                      source=event.get("source"), source_identities=identities,
                      source_freshness=event.get("freshness"), freshness=freshness,
                      temporal_fitness=event.get("temporal_fitness"), session_fitness=session_fitness,
                      materiality=event.get("materiality"),
                      driver_category=_FORWARD_CATEGORIES.get(event.get("event_type"), "UNCLASSIFIED_DRIVER"),
                      relevance=("PENDING_EVENT_CONTEXT" if freshness == FRESHNESS_ACTIVE else
                                 "RECENT_RESOLVED_CONTEXT" if freshness == FRESHNESS_RESOLVED_RECENT else
                                 "HISTORICAL_CONTEXT" if freshness == FRESHNESS_RESOLVED_HISTORICAL else "UNRESOLVED_CONTEXT"),
                      warnings=sorted(set(event.get("warnings") or [])),
                      temporal_fitness_warnings=sorted(set(event.get("temporal_fitness_warnings") or [])),
                      direction=direction, qualified=qualified, fitness=fitness,
                      reason_codes=sorted(reasons), blocker_reason_codes=sorted(blockers),
                      conflicts=event.get("conflicts") or [],
                      limitations=sorted(set(event.get("limitations") or []) | {
                          "NO_DIRECTIONAL_THESIS_VOTE", "NO_POSTURE_EFFECT", "CURRENT_RESEARCH_ONLY",
                          "DATES_DO_NOT_ESTABLISH_EXECUTION", "NO_PRICE_IMPACT_OR_PROBABILITY"}))
        drivers.append(driver)
    drivers.sort(key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
    payload = dict(contract_version=FORWARD_DRIVER_VERSION, ticker=source.get("ticker") or ticker,
                   as_of_session=as_of_session, evidence_session=source_session,
                   session_fitness=session_fitness, drivers=drivers,
                   qualified_driver_count=sum(d["qualified"] for d in drivers),
                   blocker_reason_codes=sorted({b for d in drivers for b in d["blocker_reason_codes"]} |
                                              ({"NO_QUALIFIED_FORWARD_DRIVER"} if not any(d["qualified"] for d in drivers) else set())),
                   authority_effect="NONE", applicability="CURRENT_RESEARCH_EXPLANATION_ONLY")
    payload["context_identity"] = FORWARD_DRIVER_VERSION + ":" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    return payload


def forward_driver_coverage(contexts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One context per canonical decision ticker; distributions count retained drivers.

    Blocker prevalence counts tickers, not repeated events. Qualification is separately
    distributed, so historical/unresolved observations never inflate forward coverage.
    """
    drivers = [d for context in contexts for d in context.get("drivers") or []]
    qualified = sum(bool(context.get("qualified_driver_count")) for context in contexts)
    coverage = dict(denominator=len(contexts), tickers_with_qualified_driver=qualified,
                    no_qualified_driver_count=len(contexts) - qualified,
                    total_retained_drivers=len(drivers),
                    qualified_driver_count=sum(d["qualified"] for d in drivers))
    for label, field in (("driver_type", "event_type"), ("driver_category", "driver_category"), ("canonical_status", "status"),
                         ("freshness", "freshness"), ("fitness", "fitness"),
                         ("temporal_fitness", "temporal_fitness"), ("materiality", "materiality"),
                         ("direction", "direction")):
        counts = Counter(d.get(field) or "UNKNOWN" for d in drivers)
        if label == "direction":
            for value in ("SUPPORTIVE", "ADVERSE", "MIXED", "INFORMATIONAL", "UNKNOWN"):
                counts.setdefault(value, 0)
        coverage[label + "_distribution"] = dict(sorted(counts.items()))
    coverage["blocker_prevalence"] = dict(sorted(Counter(
        reason for context in contexts for reason in set(context.get("blocker_reason_codes") or [])).items()))
    return coverage
