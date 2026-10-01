"""Integrated Investment Decision Product (INTEGRATED_INVESTMENT_DECISION_PRODUCT_V1).

Combines Core Fundamental Valuation & Peer Context with Tactical Market Structure V3,
dimensionless participation/relative-volume research, and market/sector context into
a deterministic current-research investment decision product.

Guiding Principles
------------------
1. CURRENT RESEARCH != AUDIT / PIT / EXACT.
   Missing audit-grade authority (monetary scale, exact execution capacity, PIT history)
   blocks only that specific exact use; it never globally forces a security to WAIT or AVOID.
2. NO UNIVERSAL SCORE.
   Deterministic research policy operates over explicit evidence/state combinations.
   Feature engines own measurements; this module owns deterministic research policy.
3. EXTENSION RISK != FUNDAMENTAL REJECTION.
   An attractive security extended past its pivot is HOLD_DO_NOT_ADD or WAIT_FOR_CONFIRMATION,
   not fundamentally flawed or AVOID.
4. ACTUAL ADVERSE EVIDENCE REQUIRED FOR AVOID/REDUCE.
   AVOID/REDUCE requires observed structural breakdown, failed breakout with deterioration,
   or severe fundamental loss/contraction.
5. PORTFOLIO SEPARATION.
   Security attractiveness is kept strictly separate from portfolio fit.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from typing import Any, Mapping, Sequence

import current_research_decision_input as decision_input
import financial_analysis_product_projection as fa_product_projection
import fundamental_signal_consumption_contract as fundamental_signals
import operational_fundamental_context_integration as operational_fundamental

CONTRACT_VERSION = "integrated_investment_decision_product/v1"
MILESTONE = "INTEGRATED_INVESTMENT_DECISION_PRODUCT_V1"

# Size context (market capitalisation) is reported separately and never counts as valuation
# evidence on its own; see evaluate_valuation_context.
_SIZE_CONTEXT_METHODS = ("market_cap",)
LIQUIDITY_RESEARCH_CONTRACT = "market_wide_current_liquidity_research/v1"
OFFICIAL_LIQUIDITY_RESEARCH_CONTRACT = "official_exchange_liquidity_research/v1"

# The one shape evaluate_fundamental_direction()/build_ticker_integrated_decision() actually
# read: financial_analysis_product_projection's compact, flat financial_analysis_product_
# integration/v1 record set. A real production defect fed the raw financial_analysis_context/
# v2 engine artifact and the legacy market_wide_current_fundamental_research/v1 artifact here
# instead -- both structurally incompatible, silently degrading fundamental_state to
# INSUFFICIENT for every ticker. contract_version is intentionally checked leniently (absent
# is allowed, so lightweight test fixtures that omit it keep working); only a PRESENT but
# WRONG contract_version fails closed, which is exactly the shape of both real historical bugs.
FINANCIAL_ANALYSIS_COMPACT_CONTRACT = fa_product_projection.INTEGRATION_CONTRACT

# ── Research Action Posture Taxonomy ──────────────────────────────────────────
POSTURE_EARLY_WATCH = "EARLY_WATCH"
POSTURE_INITIATE_ON_BREAKOUT = "INITIATE_ON_BREAKOUT"
POSTURE_ACCUMULATE_ON_RETEST = "ACCUMULATE_ON_RETEST"
POSTURE_WAIT_FOR_CONFIRMATION = "WAIT_FOR_CONFIRMATION"
POSTURE_HOLD = "HOLD"
POSTURE_HOLD_DO_NOT_ADD = "HOLD_DO_NOT_ADD"
POSTURE_REDUCE = "REDUCE"
POSTURE_AVOID = "AVOID"
POSTURE_INSUFFICIENT = "INSUFFICIENT_CURRENT_RESEARCH"

RESEARCH_ACTION_POSTURES = frozenset({
    POSTURE_EARLY_WATCH,
    POSTURE_INITIATE_ON_BREAKOUT,
    POSTURE_ACCUMULATE_ON_RETEST,
    POSTURE_WAIT_FOR_CONFIRMATION,
    POSTURE_HOLD,
    POSTURE_HOLD_DO_NOT_ADD,
    POSTURE_REDUCE,
    POSTURE_AVOID,
    POSTURE_INSUFFICIENT,
})

# ── Fundamental Direction Taxonomy ───────────────────────────────────────────
# Owned by the fundamental signal consumption contract, which derives it from explicit
# level/direction/transition components (INTEGRATED_FUNDAMENTAL_STATE_CONSUMPTION_RECONCILIATION_V1).
FUNDAMENTAL_IMPROVING = fundamental_signals.FUNDAMENTAL_IMPROVING
FUNDAMENTAL_STABLE = fundamental_signals.FUNDAMENTAL_STABLE
FUNDAMENTAL_MIXED = fundamental_signals.FUNDAMENTAL_MIXED
FUNDAMENTAL_DETERIORATING = fundamental_signals.FUNDAMENTAL_DETERIORATING
FUNDAMENTAL_TURNAROUND = fundamental_signals.FUNDAMENTAL_TURNAROUND
FUNDAMENTAL_INSUFFICIENT = fundamental_signals.FUNDAMENTAL_INSUFFICIENT

FUNDAMENTAL_STATES = frozenset({
    FUNDAMENTAL_IMPROVING,
    FUNDAMENTAL_STABLE,
    FUNDAMENTAL_MIXED,
    FUNDAMENTAL_DETERIORATING,
    FUNDAMENTAL_TURNAROUND,
    FUNDAMENTAL_INSUFFICIENT,
})

# ── Financial Composite Context Taxonomy (MARKET_WIDE_FUNDAMENTAL_VALUATION_ANALYTICAL_
# PRODUCT_V1, section 14) ─────────────────────────────────────────────────────────────
# Deliberately a DISTINCT vocabulary from FUNDAMENTAL_STATES above, even though it joins the
# same fundamental evidence plus valuation: `fundamental_state` already feeds
# decide_research_action_posture and must never be retuned by this milestone (section 17 --
# any policy change requires a demonstrated defect, a counterexample, and a regression test,
# none of which apply here). The composite is a strictly downstream, additive read of
# `fundamental_state`/`valuation_context_summary`, never a replacement for either.
COMPOSITE_FUNDAMENTALS_IMPROVING = "FUNDAMENTALS_IMPROVING"
COMPOSITE_FUNDAMENTALS_STABLE = "FUNDAMENTALS_STABLE"
COMPOSITE_FUNDAMENTALS_MIXED = "FUNDAMENTALS_MIXED"
COMPOSITE_FUNDAMENTALS_DETERIORATING = "FUNDAMENTALS_DETERIORATING"
COMPOSITE_TURNAROUND_EVIDENCE = "TURNAROUND_EVIDENCE"
COMPOSITE_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

FINANCIAL_COMPOSITE_STATES = frozenset({
    COMPOSITE_FUNDAMENTALS_IMPROVING,
    COMPOSITE_FUNDAMENTALS_STABLE,
    COMPOSITE_FUNDAMENTALS_MIXED,
    COMPOSITE_FUNDAMENTALS_DETERIORATING,
    COMPOSITE_TURNAROUND_EVIDENCE,
    COMPOSITE_INSUFFICIENT_EVIDENCE,
})

# ── Tactical Phase Taxonomy ───────────────────────────────────────────────────
TACTICAL_BASE_BUILDING = "BASE_BUILDING"
TACTICAL_EARLY_REVERSAL = "EARLY_REVERSAL"
TACTICAL_BREAKOUT_SETUP = "BREAKOUT_SETUP"
TACTICAL_BREAKOUT_CONFIRMED = "BREAKOUT_CONFIRMED"
TACTICAL_RETEST_AFTER_BREAKOUT = "RETEST_AFTER_BREAKOUT"
TACTICAL_TREND_CONTINUATION = "TREND_CONTINUATION"
TACTICAL_EXTENDED = "EXTENDED"
TACTICAL_DISTRIBUTION_RISK = "DISTRIBUTION_RISK"
TACTICAL_BREAKDOWN = "BREAKDOWN"
TACTICAL_MIXED = "MIXED"
TACTICAL_INSUFFICIENT = "INSUFFICIENT"

TACTICAL_PHASES = frozenset({
    TACTICAL_BASE_BUILDING,
    TACTICAL_EARLY_REVERSAL,
    TACTICAL_BREAKOUT_SETUP,
    TACTICAL_BREAKOUT_CONFIRMED,
    TACTICAL_RETEST_AFTER_BREAKOUT,
    TACTICAL_TREND_CONTINUATION,
    TACTICAL_EXTENDED,
    TACTICAL_DISTRIBUTION_RISK,
    TACTICAL_BREAKDOWN,
    TACTICAL_MIXED,
    TACTICAL_INSUFFICIENT,
})

# Qualitative relationships among distinct evidence axes.  This is deliberately separate from
# the existing action-posture policy: it makes agreement and disagreement inspectable without
# turning correlated technical measurements into a score, a confidence value, or a vote.
EVIDENCE_AXIS_COHERENCE_ALIGNED = "ALIGNED"
EVIDENCE_AXIS_COHERENCE_PARTIALLY_ALIGNED = "PARTIALLY_ALIGNED"
EVIDENCE_AXIS_COHERENCE_MIXED = "MIXED"
EVIDENCE_AXIS_COHERENCE_CONTRADICTED = "CONTRADICTED"
EVIDENCE_AXIS_COHERENCE_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
EVIDENCE_AXIS_COHERENCE_STATES = frozenset({
    EVIDENCE_AXIS_COHERENCE_ALIGNED,
    EVIDENCE_AXIS_COHERENCE_PARTIALLY_ALIGNED,
    EVIDENCE_AXIS_COHERENCE_MIXED,
    EVIDENCE_AXIS_COHERENCE_CONTRADICTED,
    EVIDENCE_AXIS_COHERENCE_INSUFFICIENT,
})

_CONSTRUCTIVE_TACTICAL_PHASES = frozenset({
    TACTICAL_EARLY_REVERSAL,
    TACTICAL_BREAKOUT_SETUP,
    TACTICAL_BREAKOUT_CONFIRMED,
    TACTICAL_RETEST_AFTER_BREAKOUT,
    TACTICAL_TREND_CONTINUATION,
    TACTICAL_EXTENDED,
})
_ADVERSE_MARKET_REGIMES = frozenset({"WEAK_BREADTH", "DETERIORATING_BREADTH", "RISK_OFF"})
_WEAK_SECTOR_STATES = frozenset({"LAGGING", "WEAK", "DETERIORATING"})
_AXIS_UNAVAILABLE_FITNESS = frozenset({
    None, "UNAVAILABLE", "INSUFFICIENT_EVIDENCE", "NOT_PROVIDED", "ABSENT", "NOT_ELIGIBLE", "NOT_AVAILABLE", "INPUT_BLOCKED",
})

# ── Missing Evidence Effects ──────────────────────────────────────────────────
EFFECT_DOES_NOT_BLOCK = "DOES_NOT_BLOCK_CURRENT_RESEARCH"
EFFECT_BLOCKS_VALUATION_ONLY = "BLOCKS_VALUATION_COMPONENT_ONLY"
EFFECT_BLOCKS_DECISION = "BLOCKS_CURRENT_DECISION"


# ── Evidence Currency (CURRENT_DECISION_SURFACE_CONVERGENCE_V1) ─────────────────
# One Producer-owned per-ticker field. Lineage: the Level-2 Daily
# same_session_technical_coverage_disposition/v1 artifact for the exact decision session -- the
# same already-governed per-ticker same-session price/technical verdict the Action Center's
# freshness block and the Workspace indicator bridge already consume. It is never inferred from
# requested_at, the overall artifact session, posture, legacy stance, calendar arithmetic, or mere
# universe membership. Every consumer passes it through; none re-derives it.
EVIDENCE_CURRENCY_CURRENT_SESSION = "CURRENT_SESSION"
EVIDENCE_CURRENCY_LAST_TRADE_PREFIX = "LAST_TRADE_AS_OF:"
EVIDENCE_CURRENCY_NO_CURRENT_EVIDENCE = "NO_CURRENT_EVIDENCE"
EVIDENCE_CURRENCY_SOURCE_CONTRACT = "same_session_technical_coverage_disposition/v1"
_CURRENT_SESSION_DISPOSITION = "SAME_SESSION_TECHNICAL_COVERED"
# A disposition that asserts the retained evidence itself is conflicted/unexplained never yields
# a dated currency, even when a feature date happens to be present.
_UNTRUSTED_DISPOSITIONS = frozenset({"MALFORMED_OR_CONFLICTED", "UNEXPLAINED"})
EVIDENCE_CURRENCY_GATE_RULE = "NO_CURRENT_EVIDENCE_NEVER_WAIT_FOR_CONFIRMATION"

# Position context. Reuses portfolio_aware_decision.POSITION_STATES; the only added value is the
# explicit unknown used when no private portfolio was supplied -- absence is never NOT_HELD.
POSITION_UNKNOWN_NOT_SUPPLIED = "UNKNOWN_POSITION_NOT_SUPPLIED"
# Postures whose meaning presupposes an existing holding: without a confirmed position they are
# presented conditionally ("HOLD -- if currently held"), never as a claim of ownership.
POSITION_CONDITIONAL_POSTURES = frozenset({"HOLD", "HOLD_DO_NOT_ADD", "REDUCE"})

DECISION_SURFACE_INDEX_CONTRACT = "decision_surface_index/v1"


class IntegratedDecisionProductError(ValueError):
    """Fail-closed error for integrated investment decision product."""


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-":
        return False
    return value[:4].isdigit() and value[5:7].isdigit() and value[8:].isdigit()


def resolve_evidence_currency(disposition_record: Mapping[str, Any] | None, *, decision_session: str) -> str:
    """Map one retained same-session technical coverage disposition record to evidence currency.

    CURRENT_SESSION requires the ticker's own disposition to establish an exact-session bar AND
    a current-session technical window dated at the decision session. LAST_TRADE_AS_OF:<date>
    requires an explicit retained feature date strictly older than the decision session. Anything
    else (absent record, undated, conflicted, future-dated) is NO_CURRENT_EVIDENCE.
    """
    if not isinstance(disposition_record, Mapping):
        return EVIDENCE_CURRENCY_NO_CURRENT_EVIDENCE
    disposition = disposition_record.get("disposition")
    feature_as_of = disposition_record.get("feature_as_of_session")
    if disposition in _UNTRUSTED_DISPOSITIONS:
        return EVIDENCE_CURRENCY_NO_CURRENT_EVIDENCE
    if (
        disposition == _CURRENT_SESSION_DISPOSITION
        and disposition_record.get("has_exact_session_bar") is True
        and disposition_record.get("is_current_session") is True
        and feature_as_of == decision_session
    ):
        return EVIDENCE_CURRENCY_CURRENT_SESSION
    if disposition != _CURRENT_SESSION_DISPOSITION and _is_iso_date(feature_as_of) and feature_as_of < decision_session:
        return EVIDENCE_CURRENCY_LAST_TRADE_PREFIX + feature_as_of
    return EVIDENCE_CURRENCY_NO_CURRENT_EVIDENCE


def is_valid_evidence_currency(value: Any) -> bool:
    if value in (EVIDENCE_CURRENCY_CURRENT_SESSION, EVIDENCE_CURRENCY_NO_CURRENT_EVIDENCE):
        return True
    return (
        isinstance(value, str) and value.startswith(EVIDENCE_CURRENCY_LAST_TRADE_PREFIX)
        and _is_iso_date(value[len(EVIDENCE_CURRENCY_LAST_TRADE_PREFIX):])
    )


def evidence_currency_class(value: Any) -> str:
    """Aggregation bucket: the dated LAST_TRADE_AS_OF:<date> values collapse to one class."""
    if isinstance(value, str) and value.startswith(EVIDENCE_CURRENCY_LAST_TRADE_PREFIX):
        return "LAST_TRADE_AS_OF"
    return value if value in (EVIDENCE_CURRENCY_CURRENT_SESSION, EVIDENCE_CURRENCY_NO_CURRENT_EVIDENCE) else "UNKNOWN"


def coherent_technical_coverage_disposition_records(
    artifact: Mapping[str, Any] | None, *, session: str,
) -> Mapping[str, Any] | None:
    """Strict same-session / content-identity gate for the evidence-currency source artifact.

    ``None`` in -> ``None`` out (every ticker then resolves NO_CURRENT_EVIDENCE). A supplied but
    wrong-contract, wrong-session, or self-inconsistent artifact fails closed loudly rather than
    being partially trusted.
    """
    if artifact is None:
        return None
    import same_session_technical_coverage_disposition as disposition_module
    if artifact.get("contract_version") != EVIDENCE_CURRENCY_SOURCE_CONTRACT:
        raise IntegratedDecisionProductError("TECHNICAL_COVERAGE_DISPOSITION_CONTRACT_MISMATCH")
    if artifact.get("session") != session:
        raise IntegratedDecisionProductError(
            f"TECHNICAL_COVERAGE_DISPOSITION_SESSION_MISMATCH:expected={session}:observed={artifact.get('session')}"
        )
    if disposition_module.content_identity(artifact).get("artifact_sha256") != artifact.get("artifact_sha256"):
        raise IntegratedDecisionProductError("TECHNICAL_COVERAGE_DISPOSITION_CONTENT_IDENTITY_INVALID")
    records = artifact.get("records")
    if not isinstance(records, Mapping):
        raise IntegratedDecisionProductError("TECHNICAL_COVERAGE_DISPOSITION_RECORDS_INVALID")
    return records


def position_context_view(portfolio_summary: Mapping[str, Any] | None) -> dict[str, Any]:
    """Explicit position context. No supplied portfolio means UNKNOWN, never NOT_HELD."""
    summary = portfolio_summary or {}
    if summary.get("status") == "AVAILABLE" and isinstance(summary.get("is_held"), bool):
        return {"status": "SUPPLIED", "position_state": "HELD" if summary["is_held"] else "NOT_HELD"}
    return {"status": "NOT_SUPPLIED", "position_state": POSITION_UNKNOWN_NOT_SUPPLIED}


def opportunity_priority_view(queue_record: Mapping[str, Any] | None) -> dict[str, Any]:
    """Orthogonal inspection field: what to look at first, never what to do."""
    if not isinstance(queue_record, Mapping) or not queue_record:
        return {"status": "UNAVAILABLE", "research_priority_tier": None, "entry_relevant": None,
                "reason": "NO_QUALIFYING_CURRENT_SESSION_PRIORITY_EVIDENCE"}
    return {
        "status": "AVAILABLE",
        "research_priority_tier": queue_record.get("research_priority_tier") or queue_record.get("priority_tier"),
        "entry_relevant": queue_record.get("entry_relevant"),
        "source_contract": "daily_opportunity_decision_queue/v1",
        "authority": "INSPECTION_ORDER_ONLY_NOT_AN_ACTION_POSTURE",
    }


def decision_surface_index(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Compact full-universe read model over Integrated Decision records.

    Shared by every delivery surface (AI brief, Action Center) so the convergence tuple
    ``(ticker, research_action_posture, evidence_currency)`` is projected once, identically, and
    never re-derived. It is a read model, not an authority artifact: it carries no reasoning.
    """
    records = artifact.get("records") if isinstance(artifact, Mapping) else None
    if not isinstance(records, Mapping):
        raise IntegratedDecisionProductError("DECISION_SURFACE_INDEX_SOURCE_RECORDS_INVALID")
    rows = []
    for ticker in sorted(records):
        record = records[ticker] or {}
        rows.append({
            "ticker": ticker,
            "research_action_posture": record.get("research_action_posture"),
            "evidence_currency": record.get("evidence_currency"),
            "opportunity_priority_tier": (record.get("opportunity_priority") or {}).get("research_priority_tier"),
        })
    return {
        "contract_version": DECISION_SURFACE_INDEX_CONTRACT,
        "role": "READ_MODEL_NOT_AUTHORITY",
        "session": artifact.get("session"),
        "source_integrated_investment_decision_product_identity": artifact.get("artifact_identity"),
        "denominator": len(rows),
        "rows": rows,
    }


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


_IDENTITY_EXCLUDED = {"artifact_sha256", "artifact_identity", "requested_at"}


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = {k: v for k, v in artifact.items() if k not in _IDENTITY_EXCLUDED}
    digest = _sha256(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def decision_identity(record: Mapping[str, Any]) -> str:
    """Feedback-ready deterministic identity for one ticker decision record.

    Includes ``evidence_currency`` (a decision on different evidence currency is a different
    decision state) and ``fundamental_decision_policy_version`` (the same fundamental_state label
    under another fundamental policy is a different decision state, never a comparable one).
    Deliberately excludes every OPPORTUNITY_PRIORITY input: priority is an orthogonal inspection
    axis and must never move the security decision identity.
    """
    source_identities = dict(record.get("source_identities") or {})
    source_identities.pop("priority_queue_record_identity", None)
    fields = {
        "ticker": record.get("ticker"),
        "as_of_session": record.get("as_of_session"),
        "policy_version": "v1",
        "research_action_posture": record.get("research_action_posture"),
        "evidence_currency": record.get("evidence_currency"),
        "fundamental_state": record.get("fundamental_state"),
        "fundamental_decision_policy_version": record.get("fundamental_decision_policy_version"),
        "tactical_phase": record.get("tactical_phase"),
        "trigger_state": (record.get("trigger") or {}).get("trigger_state"),
        "trigger_type": (record.get("trigger") or {}).get("trigger_type"),
        "trigger_condition_identity": ((record.get("trigger") or {}).get("condition") or {}).get("condition_identity"),
        "invalidation_level": (record.get("invalidation") or {}).get("invalidation_level"),
        "invalidation_condition_identity": ((record.get("invalidation") or {}).get("condition") or {}).get("condition_identity"),
        "source_identities": source_identities,
    }
    return f"decision:{record.get('ticker')}:{_sha256(fields)[:16]}"


# ── Fundamental Direction Evaluator ───────────────────────────────────────────

def evaluate_fundamental_synthesis(fa_context: Mapping[str, Any] | None, *, decision_session: str | None = None,
                                   dialect: str | None = None) -> dict[str, Any]:
    """The multi-dimensional fundamental synthesis for one producer record.

    ``fundamental_signal_consumption_contract`` maps the producer's own vocabulary to separate
    level, direction and transition components (with applicability and fitness) and derives the
    compatible ``fundamental_state`` from their dimension votes under the standing policy: a
    current loss-to-profit transition on a same-quarter YoY or TTM basis is TURNAROUND; more adverse than
    favorable votes with loss-making, contracting growth or a worsening capital structure is
    DETERIORATING; favorable only is IMPROVING (growth, margins or short-term liquidity ratio
    improving) or STABLE; both is MIXED. ``decision_session`` gates freshness: only a CURRENT
    period votes; a stale period stays visible research evidence and never votes, and a period
    after the session never enters (FUNDAMENTAL_SIGNAL_POLICY_HARDENING_V1). ``evidence_
    availability`` says whether qualified fundamental evidence exists, apart from the direction.
    """
    return fundamental_signals.evaluate(fa_context, decision_session=decision_session, dialect=dialect)


def evaluate_fundamental_direction(fa_context: Mapping[str, Any] | None, *,
                                   decision_session: str | None = None) -> tuple[str, list[str], list[str]]:
    """Compact fundamental state and its support/counter reason codes (see the synthesis above)."""
    synthesis = evaluate_fundamental_synthesis(fa_context, decision_session=decision_session)
    return (synthesis["fundamental_state"], list(synthesis["supporting_reason_codes"]),
            list(synthesis["contradicting_reason_codes"]))


def operational_fundamental_bridge_eligible(financial_record: Mapping[str, Any] | None, *,
                                            decision_session: str | None = None) -> bool:
    """Whether the operational fundamental bridge may be consulted for this Financial V2 record.

    Only an INSUFFICIENT direction with no conflicting/blocked Financial V2 evidence qualifies:
    a proxy never overrides a stronger financial read or a stronger conflict. The Daily binding
    selects its candidates with this same predicate and session, so selection and consumption
    cannot drift.
    """
    financial = financial_record or {}
    state, _supports, _counters = evaluate_fundamental_direction(financial, decision_session=decision_session)
    return (state == FUNDAMENTAL_INSUFFICIENT
            and financial.get("status") not in {"CONFLICTED", "BLOCKED"}
            and not financial.get("conflicting_evidence"))


# ── Financial Composite Context Evaluator (section 14) ────────────────────────

def evaluate_financial_composite_context(
    *, fund_state: str, fund_supports: Sequence[str], fund_counters: Sequence[str],
    val_summary: Mapping[str, Any] | None, val_supports: Sequence[str], val_counters: Sequence[str],
    fundamental_evidence_availability: str | None = None,
    fundamental_risk_level: str | None = None,
) -> dict[str, Any]:
    """Join earnings trajectory + profitability + balance sheet + cash quality (already
    synthesized into `fund_state` by `evaluate_fundamental_direction`, UNCHANGED) with
    valuation (`val_summary`, from `evaluate_valuation_context`, UNCHANGED) into one
    descriptive label. Recomputes no ratio and reuses both evaluators' own outputs verbatim
    -- this function only reads their return values, never their inputs.

    Deliberately NOT a vote count across five indicators: the label is fund_state's own
    (already-governed, non-reopened) synthesis, with exactly one explicit override --
    corroborated expensive peer-relative valuation downgrades an otherwise-positive read to
    MIXED, since "cheap/expensive" and "improving/deteriorating" are evidence a research
    reader must be able to tell apart (section 17), not two votes to blend into one score.
    Valuation cheapness never upgrades a deteriorating fundamental read, and never manufactures
    TURNAROUND_EVIDENCE or INSUFFICIENT_EVIDENCE by itself. ``INSUFFICIENT_EVIDENCE`` names an
    insufficient current direction; ``fundamental_evidence_availability`` (the five-state
    availability) says separately what fundamental evidence is known, and ``fundamental_risk_level``
    the qualified level evidence -- an improving direction is never read as a healthy level.
    """
    val_summary = val_summary or {}
    supporting = list(dict.fromkeys(list(fund_supports) + list(val_supports)))
    contradicting = list(dict.fromkeys(list(fund_counters) + list(val_counters)))
    valuation_expensive = val_summary.get("peer_relative_state") == "EXPENSIVE_VS_PEERS"

    if fund_state == FUNDAMENTAL_INSUFFICIENT:
        label = COMPOSITE_INSUFFICIENT_EVIDENCE
    elif fund_state == FUNDAMENTAL_TURNAROUND:
        label = COMPOSITE_TURNAROUND_EVIDENCE
    elif fund_state == FUNDAMENTAL_DETERIORATING:
        # Valuation is reported as a separate, visible axis (val_summary/valuation_context_
        # summary on the same record) -- a cheap price never rescues a deteriorating
        # fundamental read into a blended, falsely-reassuring label here.
        label = COMPOSITE_FUNDAMENTALS_DETERIORATING
    elif fund_state == FUNDAMENTAL_MIXED:
        label = COMPOSITE_FUNDAMENTALS_MIXED
    elif fund_state == FUNDAMENTAL_IMPROVING:
        label = COMPOSITE_FUNDAMENTALS_MIXED if valuation_expensive else COMPOSITE_FUNDAMENTALS_IMPROVING
    elif fund_state == FUNDAMENTAL_STABLE:
        label = COMPOSITE_FUNDAMENTALS_MIXED if valuation_expensive else COMPOSITE_FUNDAMENTALS_STABLE
    else:
        label = COMPOSITE_INSUFFICIENT_EVIDENCE

    return {
        "financial_composite_state": label,
        "supporting_reason_codes": supporting[:10],
        "contradicting_reason_codes": contradicting[:10],
        "joined_axes": {
            "fundamental_state": fund_state,
            "fundamental_evidence_availability": fundamental_evidence_availability,
            "fundamental_risk_level": fundamental_risk_level,
            "valuation_peer_relative_state": val_summary.get("peer_relative_state"),
            "valuation_own_history_state": val_summary.get("own_history_state"),
        },
        "methodology": "join_fundamental_state_and_valuation_context_no_vote_count/v1",
        "is_actionable": False,
    }


# ── Corporate Intelligence context (Section 13: additive only) ───────────────

def evaluate_corporate_intelligence_context(
    corporate_intelligence_record: Mapping[str, Any] | None, *, as_of_session: str,
) -> dict[str, Any]:
    """Thin join over one current_corporate_intelligence_axis/v1 per-ticker record.

    This module never computes catalyst/risk classification, materiality, or freshness itself
    -- current_corporate_intelligence_axis.py owns those measurements; this function only
    extracts the compact axis inputs and flags when the retained corporate-event evidence is
    from an earlier session than today's decision (mission Section 10: freshness must be
    explicit, never silently re-labelled current).
    """
    record = corporate_intelligence_record or {}
    if not record:
        return {
            "state": "NOT_PROVIDED", "fitness": "NOT_PROVIDED",
            "supporting_reason_codes": [], "contradicting_reason_codes": [],
            "blocker_reason_codes": ["CORPORATE_INTELLIGENCE_CONTEXT_NOT_PROVIDED"],
            "active_catalyst_count": 0, "active_risk_count": 0, "mixed_or_unresolved_count": 0,
            "material_event_count": 0, "freshest_material_event": None, "event_identities": [],
            "evidence_session": None, "evidence_session_stale": None, "limitations": [],
        }
    evidence_session = record.get("research_session")
    stale = bool(evidence_session) and evidence_session != as_of_session
    blockers = list(record.get("blockers") or [])
    if stale:
        blockers = blockers + ["CORPORATE_INTELLIGENCE_EVIDENCE_SESSION_STALE"]
    return {
        "state": record.get("state", "NO_QUALIFIED_CORPORATE_EVENT"),
        "fitness": record.get("fitness", "CURRENT_RESEARCH_ONLY"),
        "supporting_reason_codes": list(record.get("supporting_reason_codes") or []),
        "contradicting_reason_codes": list(record.get("contradicting_reason_codes") or []),
        "blocker_reason_codes": blockers,
        "active_catalyst_count": len(record.get("active_catalysts") or []),
        "active_risk_count": len(record.get("active_risks") or []),
        "mixed_or_unresolved_count": len(record.get("mixed_or_unresolved_events") or []),
        "material_event_count": record.get("material_event_count", 0),
        "freshest_material_event": record.get("freshest_material_event"),
        "event_identities": list(record.get("event_identities") or []),
        "evidence_session": evidence_session,
        "evidence_session_stale": stale,
        "limitations": list(record.get("limitations") or []),
    }


# ── Evidence-axis inventory and qualitative coherence ─────────────────────────

#: The FUNDAMENTAL axis blocker for an insufficient current direction, by what evidence is known.
FUNDAMENTAL_EVIDENCE_AVAILABILITY_BLOCKERS = {
    fundamental_signals.ABSENT: "FUNDAMENTAL_CONTEXT_ABSENT",
    fundamental_signals.STALE_ONLY: "FUNDAMENTAL_STALE_EVIDENCE_ONLY_NO_CURRENT_DIRECTION",
    fundamental_signals.CURRENT_NON_DIRECTIONAL: "FUNDAMENTAL_CURRENT_DIRECTION_INSUFFICIENT",
    fundamental_signals.NOT_APPLICABLE_ENTITY: "FUNDAMENTAL_ENTITY_NOT_DECISION_APPLICABLE",
}

def _axis(
    *, state: Any, fitness: Any, supporting: Sequence[str] = (), contradicting: Sequence[str] = (),
    blockers: Sequence[str] = (), method: str, lineage: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the compact, evidence-preserving shape shared by every decision axis.

    The helper only normalizes presentation.  It does not derive an indicator, alter a source
    state, or decide a research posture.
    """
    result: dict[str, Any] = {
        "state": state,
        "fitness": fitness,
        "supporting_reason_codes": list(dict.fromkeys(str(item) for item in supporting if item)),
        "contradicting_reason_codes": list(dict.fromkeys(str(item) for item in contradicting if item)),
        "blocker_reason_codes": list(dict.fromkeys(str(item) for item in blockers if item)),
        "method": method,
        "lineage": dict(lineage or {}),
        "is_actionable": False,
    }
    if context:
        result["context"] = dict(context)
    return result


def build_evidence_axes(
    *, fund_state: str, fund_supports: Sequence[str], fund_counters: Sequence[str],
    financial: Mapping[str, Any], valuation: Mapping[str, Any], val_summary: Mapping[str, Any],
    val_supports: Sequence[str], val_counters: Sequence[str], val_uncertainties: Sequence[str],
    tactical: Mapping[str, Any], tactical_phase: str, tactical_supports: Sequence[str],
    tactical_counters: Sequence[str], momentum: Mapping[str, Any], confirmation: Mapping[str, Any],
    participation_summary: Mapping[str, Any], market_summary: Mapping[str, Any],
    market_context_provided: bool, priority_record: Mapping[str, Any] | None,
    portfolio_summary: Mapping[str, Any], source_artifact_identities: Mapping[str, Any] | None = None,
    corporate_intelligence_summary: Mapping[str, Any] | None = None,
    operational_fundamental_context: Mapping[str, Any] | None = None,
    fundamental_synthesis: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Expose standing decision evidence as distinct, source-preserving axes.

    These are deliberately descriptive joins over already-governed producer outputs.  The action
    policy remains upstream and consumes none of this structure.
    """
    identities = source_artifact_identities or {}
    financial_status = financial.get("status") or (
        "AVAILABLE" if fund_state != FUNDAMENTAL_INSUFFICIENT else "UNAVAILABLE"
    )
    operational_used = (operational_fundamental_context or {}).get("status") == "RESEARCH_USABLE" and fund_state != FUNDAMENTAL_INSUFFICIENT
    if operational_used:
        financial_status = "RESEARCH_PROXY_CONTEXT"
    valuation_status = val_summary.get("status") or valuation.get("status") or "UNAVAILABLE"
    technical_fitness = "AVAILABLE" if tactical.get("eligible") else "INSUFFICIENT_EVIDENCE"
    momentum_fitness = (momentum.get("eligibility") or {}).get("status") or momentum.get("status") or "UNAVAILABLE"
    confirmation_state = confirmation.get("tactical_confirmation_state") or "INSUFFICIENT_EVIDENCE"
    participation_status = participation_summary.get("status") or "UNAVAILABLE"
    priority = priority_record or {}
    priority_fitness = priority.get("data_quality_status") or ("AVAILABLE" if priority_record else "UNAVAILABLE")
    sector_context = (market_summary.get("sector_leadership") if market_context_provided else None)
    sector_fitness = "AVAILABLE" if market_context_provided and sector_context not in (None, "IN_LINE", "UNKNOWN") else (
        "PARTIAL" if market_context_provided else "UNAVAILABLE"
    )
    derivation = (fundamental_synthesis or {}).get("derivation") or {}
    evidence = (fundamental_synthesis or {}).get("evidence_availability") or {}
    availability = (fundamental_synthesis or {}).get("fundamental_evidence_availability")
    risk = (fundamental_synthesis or {}).get("fundamental_risk_level") or {}
    fundamental_context = {
        "synthesis_contract": fundamental_signals.CONTRACT_VERSION,
        "signal_policy": fundamental_synthesis.get("signal_policy"),
        "fundamental_decision_policy_version": fundamental_synthesis.get("fundamental_decision_policy_version"),
        "evidence_availability": evidence.get("state"),
        "fundamental_evidence_availability": availability,
        "directional_sufficiency": evidence.get("directional_sufficiency"),
        "risk_level": risk.get("state"),
        "adverse_level_dimensions": list(risk.get("adverse_level_dimensions") or []),
        "favorable_votes": list(derivation.get("favorable_votes") or []),
        "adverse_votes": list(derivation.get("adverse_votes") or []),
        "folded_votes": list((derivation.get("vote_grouping") or {}).get("folded_votes") or []),
        "stale_research_evidence": list(fundamental_synthesis.get("stale_research_evidence") or []),
        "research_observations": sorted(fundamental_synthesis.get("research_observations") or {}),
        "turnaround_triggered": bool((derivation.get("turnaround") or {}).get("triggered")),
    } if fundamental_synthesis is not None else None
    # A directional INSUFFICIENT with known evidence is never an absent fundamental context: the
    # blocker names what is actually missing (FUNDAMENTAL_EVIDENCE_AVAILABILITY_BLOCKERS).
    if fund_state != FUNDAMENTAL_INSUFFICIENT:
        fundamental_blockers: list[str] = []
    elif availability in FUNDAMENTAL_EVIDENCE_AVAILABILITY_BLOCKERS:
        fundamental_blockers = [FUNDAMENTAL_EVIDENCE_AVAILABILITY_BLOCKERS[availability]]
    elif evidence.get("state") == fundamental_signals.AVAILABLE:
        fundamental_blockers = ["FUNDAMENTAL_CURRENT_DIRECTION_INSUFFICIENT"]
    else:
        fundamental_blockers = ["FUNDAMENTAL_CONTEXT_ABSENT"]

    return {
        "FUNDAMENTAL": _axis(
            state=fund_state, fitness=financial_status, supporting=fund_supports, contradicting=fund_counters,
            blockers=fundamental_blockers,
            method=(operational_fundamental.CONTRACT_VERSION if operational_used else "financial_analysis_product_integration/v1"),
            lineage={"source_artifact_identity": (
                identities.get("operational_fundamental_integration") if operational_used else
                identities.get("financial_analysis") or financial.get("source_context_identity") or financial.get("artifact_identity")),
                **({"source_financial_analysis_identity": identities.get("financial_analysis"),
                    "source_feature_ids": sorted((operational_fundamental_context or {}).get("usable_features") or {})}
                   if operational_used else {})},
            context=fundamental_context,
        ),
        "VALUATION": _axis(
            state=valuation_status, fitness=valuation_status, supporting=val_supports, contradicting=val_counters,
            # Monetary-basis uncertainties stay first; an unavailable valuation additionally names
            # its own method-level causes, so the reason is never left to be reverse-engineered.
            blockers=list(val_uncertainties) + list(val_summary.get("unavailable_reason_codes") or []),
            method="current_research_valuation_context/v1",
            lineage={"source_artifact_identity": identities.get("current_valuation") or valuation.get("artifact_identity")},
            context={
                "peer_relative_state": val_summary.get("peer_relative_state"),
                "own_history_state": val_summary.get("own_history_state"),
                "size_context_status": (val_summary.get("size_context") or {}).get("status"),
                "method_statuses": {
                    str(method_id): (method or {}).get("status")
                    for method_id, method in (valuation.get("methods") or {}).items()
                    if isinstance(method, Mapping)
                },
            },
        ),
        "TACTICAL_STRUCTURE": _axis(
            state=tactical_phase, fitness=technical_fitness,
            supporting=tactical_supports, contradicting=tactical_counters,
            blockers=(tactical.get("blockers") or []) + (
                ["INSUFFICIENT_TECHNICAL_STRUCTURE_SERIES"] if technical_fitness != "AVAILABLE" else []
            ),
            method="market_structure_breakout_product_projection/v1",
            lineage={"source_artifact_identity": identities.get("technical_structure") or tactical.get("artifact_identity")},
            context={
                "market_structure_state": tactical.get("market_structure_state"),
                "breakout_state_v3": tactical.get("breakout_state_v3"),
                "pivot_retest_confirmed": tactical.get("pivot_retest_confirmed"),
                "bos_state": tactical.get("bos_state"),
                "choch_state": tactical.get("choch_state"),
            },
        ),
        "MOMENTUM": _axis(
            state=momentum_fitness, fitness=momentum_fitness,
            blockers=[] if momentum_fitness == "ELIGIBLE" else ["MOMENTUM_CONTEXT_UNAVAILABLE_OR_INSUFFICIENT_HISTORY"],
            method="tactical_momentum_context/v1",
            lineage={
                "source_artifact_identity": identities.get("momentum") or momentum.get("artifact_identity"),
                "technical_history": momentum.get("technical_history_lineage"),
            },
            context={
                "price_direction_1d": momentum.get("price_direction_1d"),
                "rsi_status": (momentum.get("rsi") or {}).get("status"),
                "macd_status": (momentum.get("macd") or {}).get("status"),
                "moving_average_status": (momentum.get("moving_average_ordering") or {}).get("status"),
                "rsi_divergence_status": (momentum.get("rsi_divergence") or {}).get("status"),
            },
        ),
        "PARTICIPATION_CONFIRMATION": _axis(
            state=confirmation_state,
            fitness={"participation": participation_status, "confirmation": confirmation_state},
            supporting=confirmation.get("supporting_reasons") or [],
            contradicting=confirmation.get("contradicting_reasons") or [],
            blockers=[] if confirmation_state != "INSUFFICIENT_EVIDENCE" else ["PARTICIPATION_OR_CONFIRMATION_INSUFFICIENT_EVIDENCE"],
            method="tactical_confirmation_context/v1",
            lineage={
                "source_artifact_identity": identities.get("tactical_confirmation") or confirmation.get("artifact_identity"),
                "participation_artifact_identity": identities.get("relative_volume"),
            },
            context={
                "participation_status": participation_status,
                "participation_detail": confirmation.get("participation_detail"),
                "structure_stance": confirmation.get("structure_stance"),
            },
        ),
        "MARKET_SECTOR": _axis(
            state=market_summary.get("market_regime") if market_context_provided else "UNAVAILABLE",
            fitness=sector_fitness,
            blockers=list(market_summary.get("sector_leadership_reason_codes") or []) if market_context_provided else ["MARKET_SECTOR_CONTEXT_NOT_PROVIDED"],
            method="current_market_sector_leadership_context/v1",
            lineage={"source_artifact_identity": identities.get("market_sector")},
            context={"market_regime": market_summary.get("market_regime"), "sector_leadership": sector_context,
                     **{key: market_summary.get(key) for key in ("market_breadth", "sector_leadership_status", "sector_leadership_reason_codes", "sector_group_key", "sector_group_coverage_ratio")}},
        ),
        "OPPORTUNITY_PRIORITY": _axis(
            # The standing Daily decision queue names this governed lane field
            # `research_priority_tier`; retained older opportunity artifacts use `priority_tier`.
            # Read both without rewriting either producer contract.
            state=priority.get("research_priority_tier") or priority.get("priority_tier") or "UNAVAILABLE", fitness=priority_fitness,
            supporting=priority.get("priority_reasons") or [],
            blockers=priority.get("blocking_reasons") or ([] if priority_record else ["OPPORTUNITY_PRIORITY_NOT_PROVIDED"]),
            method="daily_opportunity_decision_queue/v1",
            lineage={"source_artifact_identity": identities.get("priority_queue"), "record_identity": priority.get("content_identity")},
            context={"scenario_status": priority.get("scenario_status"), "entry_action": priority.get("entry_action")},
        ),
        "PORTFOLIO_FIT": _axis(
            state=portfolio_summary.get("status", "NOT_PROVIDED"), fitness=portfolio_summary.get("status", "NOT_PROVIDED"),
            blockers=[] if portfolio_summary.get("status") == "AVAILABLE" else ["PORTFOLIO_CONTEXT_NOT_PROVIDED"],
            method="integrated_investment_decision_product/portfolio_context/v1",
            lineage={},
            context={
                "is_held": portfolio_summary.get("is_held"),
                "concentration_flag": portfolio_summary.get("concentration_flag"),
                "sector_overlap": portfolio_summary.get("sector_overlap"),
            },
        ),
        # CORPORATE_INTELLIGENCE_CATALYST_EVENT_RISK_DECISION_INTEGRATION_V1: additive evidence
        # axis only. current_corporate_intelligence_axis.py owns every catalyst/risk/materiality/
        # freshness measurement; this axis only exposes its already-computed per-ticker read.
        # decide_research_action_posture (called before this function, above) never reads this
        # axis -- no automatic posture change merely because a catalyst/risk exists (Section 14).
        "CORPORATE_INTELLIGENCE": _axis(
            state=(corporate_intelligence_summary or {}).get("state", "NOT_PROVIDED"),
            fitness=(corporate_intelligence_summary or {}).get("fitness", "NOT_PROVIDED"),
            supporting=(corporate_intelligence_summary or {}).get("supporting_reason_codes") or [],
            contradicting=(corporate_intelligence_summary or {}).get("contradicting_reason_codes") or [],
            blockers=(corporate_intelligence_summary or {}).get("blocker_reason_codes") or [],
            method="current_corporate_intelligence_axis/v1",
            lineage={"source_artifact_identity": identities.get("corporate_intelligence")},
            context={
                "active_catalyst_count": (corporate_intelligence_summary or {}).get("active_catalyst_count"),
                "active_risk_count": (corporate_intelligence_summary or {}).get("active_risk_count"),
                "material_event_count": (corporate_intelligence_summary or {}).get("material_event_count"),
                "freshest_material_event": (corporate_intelligence_summary or {}).get("freshest_material_event"),
                "evidence_session_stale": (corporate_intelligence_summary or {}).get("evidence_session_stale"),
            },
        ),
    }


def evaluate_evidence_axis_coherence(evidence_axes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Describe cross-axis relationships without scoring or changing posture policy.

    A confirmation record is already the standing, correlation-aware technical synthesis.  This
    function therefore reads its declared state once; it never re-counts RSI, MACD, moving average,
    BOS, CHoCH, breakout, or participation measurements as separate votes.
    """
    fundamental = evidence_axes.get("FUNDAMENTAL") or {}
    valuation = evidence_axes.get("VALUATION") or {}
    technical = evidence_axes.get("TACTICAL_STRUCTURE") or {}
    confirmation = evidence_axes.get("PARTICIPATION_CONFIRMATION") or {}
    market = evidence_axes.get("MARKET_SECTOR") or {}
    technical_phase = technical.get("state")
    confirmation_state = confirmation.get("state")
    market_context = market.get("context") or {}
    market_regime = market_context.get("market_regime")
    sector_state = market_context.get("sector_leadership")
    valuation_context = valuation.get("context") or {}
    reasons: list[str] = []

    if technical.get("fitness") != "AVAILABLE":
        state = EVIDENCE_AXIS_COHERENCE_INSUFFICIENT
        reasons.append("TACTICAL_STRUCTURE_INSUFFICIENT_EVIDENCE")
    elif confirmation_state == "CONTRADICTED":
        state = EVIDENCE_AXIS_COHERENCE_CONTRADICTED
        reasons.append("TACTICAL_CONFIRMATION_CONTRADICTED")
    elif fundamental.get("state") == FUNDAMENTAL_DETERIORATING and technical_phase in _CONSTRUCTIVE_TACTICAL_PHASES:
        state = EVIDENCE_AXIS_COHERENCE_CONTRADICTED
        reasons.append("FUNDAMENTALS_DETERIORATING_WHILE_TECHNICAL_STRUCTURE_IS_CONSTRUCTIVE")
    elif technical_phase in (TACTICAL_BREAKDOWN, TACTICAL_DISTRIBUTION_RISK) and fundamental.get("state") in (
        FUNDAMENTAL_IMPROVING, FUNDAMENTAL_STABLE, FUNDAMENTAL_TURNAROUND
    ):
        state = EVIDENCE_AXIS_COHERENCE_MIXED
        reasons.append("CONSTRUCTIVE_FUNDAMENTALS_WITH_ADVERSE_TECHNICAL_STRUCTURE")
    elif technical_phase in _CONSTRUCTIVE_TACTICAL_PHASES and (
        market_regime in _ADVERSE_MARKET_REGIMES or sector_state in _WEAK_SECTOR_STATES
    ):
        state = EVIDENCE_AXIS_COHERENCE_MIXED
        reasons.append("CONSTRUCTIVE_TECHNICAL_STRUCTURE_WITH_WEAK_MARKET_OR_SECTOR_CONTEXT")
    elif technical_phase in _CONSTRUCTIVE_TACTICAL_PHASES and valuation_context.get("peer_relative_state") == "EXPENSIVE_VS_PEERS":
        state = EVIDENCE_AXIS_COHERENCE_MIXED
        reasons.append("CONSTRUCTIVE_TECHNICAL_STRUCTURE_WITH_EXPENSIVE_PEER_RELATIVE_VALUATION")
    elif (
        confirmation_state == "CONFIRMED"
        and fundamental.get("state") in (FUNDAMENTAL_IMPROVING, FUNDAMENTAL_STABLE, FUNDAMENTAL_TURNAROUND)
        and valuation_context.get("peer_relative_state") != "EXPENSIVE_VS_PEERS"
        and market_regime not in _ADVERSE_MARKET_REGIMES
        and sector_state not in _WEAK_SECTOR_STATES
    ):
        state = EVIDENCE_AXIS_COHERENCE_ALIGNED
        reasons.append("STANDING_CONFIRMATION_AND_NON_CONTRADICTORY_CROSS_AXIS_CONTEXT")
    else:
        state = EVIDENCE_AXIS_COHERENCE_PARTIALLY_ALIGNED
        reasons.append("NO_EXPLICIT_CROSS_AXIS_CONTRADICTION_BUT_FULL_ALIGNMENT_NOT_EVIDENCED")

    return {
        "state": state,
        "reason_codes": reasons,
        "methodology": "qualitative_cross_axis_relationships_no_scoring_or_vote_count/v1",
        "axis_order": [
            "FUNDAMENTAL", "VALUATION", "TACTICAL_STRUCTURE", "MOMENTUM",
            "PARTICIPATION_CONFIRMATION", "MARKET_SECTOR", "OPPORTUNITY_PRIORITY", "PORTFOLIO_FIT",
        ],
        "is_actionable": False,
    }


def _evidence_axis_available(axis_name: str, axis: Mapping[str, Any] | None) -> bool:
    """Availability is feature-local and never an action-policy gate."""
    axis = axis or {}
    if (axis_name == "FUNDAMENTAL" and axis.get("state") == FUNDAMENTAL_INSUFFICIENT
            and (axis.get("context") or {}).get("evidence_availability") != fundamental_signals.AVAILABLE):
        return False
    fitness = axis.get("fitness")
    if isinstance(fitness, Mapping):
        return bool(fitness) and all(value not in _AXIS_UNAVAILABLE_FITNESS for value in fitness.values())
    return fitness not in _AXIS_UNAVAILABLE_FITNESS


# ── Tactical Phase Evaluator ──────────────────────────────────────────────────

def evaluate_tactical_phase(tactical_rec: Mapping[str, Any] | None) -> tuple[str, list[str], list[str]]:
    """Determine compact tactical phase and specific technical support/counter points."""
    if not isinstance(tactical_rec, Mapping) or not tactical_rec.get("eligible"):
        return TACTICAL_INSUFFICIENT, [], ["INSUFFICIENT_TECHNICAL_STRUCTURE_SERIES"]

    supports: list[str] = []
    counters: list[str] = []

    ms = tactical_rec.get("market_structure_state")
    brk_v3 = tactical_rec.get("breakout_state_v3")
    bos = tactical_rec.get("bos_state")
    choch = tactical_rec.get("choch_state")
    trig = tactical_rec.get("trigger_state")
    trig_type = tactical_rec.get("trigger_type")
    dist_piv = tactical_rec.get("distance_to_pivot_pct")
    base_st = tactical_rec.get("base_status")
    range_st = tactical_rec.get("range_state")
    slope = tactical_rec.get("ma20_slope_state")
    sh_seq = tactical_rec.get("swing_high_sequence")
    sl_seq = tactical_rec.get("swing_low_sequence")

    # Supports
    if ms == "UPTREND":
        supports.append("STRUCTURE_UPTREND_CONFIRMED")
    elif ms == "EARLY_BULLISH_REVERSAL":
        supports.append("EARLY_BULLISH_REVERSAL_STRUCTURE")

    if sh_seq == "HH":
        supports.append("HIGHER_SWING_HIGHS")
    if sl_seq == "HL":
        supports.append("HIGHER_SWING_LOWS")

    if bos == "BULLISH_BOS_DETECTED_BY_RULE":
        supports.append("BULLISH_BREAK_OF_STRUCTURE")
    if choch == "BULLISH_CHOCH_DETECTED_BY_RULE":
        supports.append("BULLISH_CHANGE_OF_CHARACTER")

    if brk_v3 == "BREAKOUT":
        supports.append("PRICE_ABOVE_CONFIRMED_PIVOT")
    elif brk_v3 == "TESTING_PIVOT":
        supports.append("TESTING_PIVOT_RESISTANCE")
    elif brk_v3 == "EXTENDED_AFTER_BREAKOUT":
        supports.append("EXTENDED_ABOVE_PIVOT")

    if trig == "TRIGGERED":
        if trig_type == "CONFIRMED_BOS_TRIGGER" and bos == "BEARISH_BOS_DETECTED_BY_RULE":
            counters.append("BEARISH_BOS_TRIGGER_FIRED")
        else:
            supports.append(f"TRIGGER_FIRED_{trig_type}")

    if range_st == "RANGE_COMPRESSION":
        supports.append("VOLATILITY_RANGE_COMPRESSION")
    if base_st == "IN_BASE":
        supports.append("CONSTRUCTIVE_BASE_CONSOLIDATION")
    if slope == "RISING":
        supports.append("MA20_SLOPE_RISING")

    # Counters
    if ms == "DOWNTREND":
        counters.append("STRUCTURE_DOWNTREND_CONFIRMED")
    elif ms == "EARLY_BEARISH_REVERSAL":
        counters.append("EARLY_BEARISH_REVERSAL_STRUCTURE")

    if sh_seq == "LH":
        counters.append("LOWER_SWING_HIGHS")
    if sl_seq == "LL":
        counters.append("LOWER_SWING_LOWS")

    if bos == "BEARISH_BOS_DETECTED_BY_RULE":
        counters.append("BEARISH_BREAK_OF_STRUCTURE")
    if choch == "BEARISH_CHOCH_DETECTED_BY_RULE":
        counters.append("BEARISH_CHANGE_OF_CHARACTER")

    if brk_v3 == "FAILED_BREAKOUT":
        counters.append("FAILED_BREAKOUT_REJECTION")
    if slope == "FALLING":
        counters.append("MA20_SLOPE_FALLING")

    # Tactical Phase synthesis
    if bos == "BEARISH_BOS_DETECTED_BY_RULE":
        phase = TACTICAL_BREAKDOWN
    elif brk_v3 == "FAILED_BREAKOUT":
        phase = TACTICAL_DISTRIBUTION_RISK
    elif brk_v3 == "EXTENDED_AFTER_BREAKOUT" or (dist_piv is not None and dist_piv > 0.05 and brk_v3 in ("BREAKOUT", "EXTENDED_AFTER_BREAKOUT")):
        phase = TACTICAL_EXTENDED
    elif brk_v3 == "BREAKOUT" or (trig == "TRIGGERED" and trig_type in ("PIVOT_BREAKOUT_TRIGGER", "CONFIRMED_BOS_TRIGGER")):
        if ms == "DOWNTREND":
            phase = TACTICAL_EARLY_REVERSAL
        else:
            phase = TACTICAL_BREAKOUT_CONFIRMED
    elif tactical_rec.get("pivot_retest_confirmed") is True and ms in ("UPTREND", "EARLY_BULLISH_REVERSAL"):
        phase = TACTICAL_RETEST_AFTER_BREAKOUT
    elif brk_v3 == "TESTING_PIVOT" or trig == "APPROACHING" or (base_st == "IN_BASE" and range_st == "RANGE_COMPRESSION"):
        phase = TACTICAL_BREAKOUT_SETUP
    elif ms == "DOWNTREND":
        phase = TACTICAL_BREAKDOWN
    elif ms == "EARLY_BEARISH_REVERSAL" or choch == "BEARISH_CHOCH_DETECTED_BY_RULE":
        phase = TACTICAL_DISTRIBUTION_RISK
    elif ms == "UPTREND" and slope == "RISING":
        phase = TACTICAL_TREND_CONTINUATION
    elif ms == "EARLY_BULLISH_REVERSAL" or choch == "BULLISH_CHOCH_DETECTED_BY_RULE":
        phase = TACTICAL_EARLY_REVERSAL
    elif base_st == "IN_BASE" or range_st in ("RANGE_COMPRESSION", "RANGE_STABLE"):
        phase = TACTICAL_BASE_BUILDING
    elif ms == "INSUFFICIENT_HISTORY":
        phase = TACTICAL_INSUFFICIENT
    else:
        phase = TACTICAL_MIXED

    return phase, supports, counters


# ── Valuation Context Interpreter ─────────────────────────────────────────────

def evaluate_valuation_context(
    val_rec: Mapping[str, Any] | None,
    fa_context: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], list[str], list[str], list[str]]:
    """Interpret valuation multiples, peer comparisons, and own-history distributions."""
    val_rec = val_rec or {}
    fa_context = fa_context or {}
    supports: list[str] = []
    counters: list[str] = []
    uncertainties: list[str] = []

    methods = val_rec.get("methods") or {}
    pe_item = methods.get("P/E") or methods.get("P/E_TTM") or {}
    research_pb = methods.get("P/B_CURRENT_RESEARCH") or {}
    research_pb_used = research_pb.get("status") in {"RESEARCH_USABLE", "READY"}
    pb_item = research_pb if research_pb_used else (methods.get("P/B") or {})
    ps_item = methods.get("P/S") or methods.get("P/S_TTM") or {}
    # EV/EBITDA_CALC_READY (MARKET_WIDE_FUNDAMENTAL_VALUATION_ANALYTICAL_PRODUCT_V1) is the
    # genuinely computable EV/EBITDA method; the older "EV/EBITDA" method_id is retained for
    # its own always-blocked reason and is only a fallback here for a hypothetical future
    # session where it becomes usable.
    ev_ebitda_item = methods.get("EV/EBITDA_CALC_READY") or methods.get("EV/EBITDA") or {}

    pe_val = val_rec.get("pe") or pe_item.get("value")
    pb_val = val_rec.get("pb") or pb_item.get("value")
    ps_val = val_rec.get("ps") or ps_item.get("value")
    ev_ebitda_val = ev_ebitda_item.get("value") if ev_ebitda_item.get("status") in {"RESEARCH_USABLE", "READY"} else None

    # current_research_valuation_context.attach_peer_relative (the only producer the Daily path
    # feeds here) writes the synthesized verdict at the row's top level as
    # ``relative_research_state`` plus per-method ``peer_relative`` detail; only the
    # opportunity-axis view wraps it as ``peer_relative_context``. Reading solely the wrapped key
    # meant a real producer verdict never reached this record. The producer's own verdict is
    # passed through, never re-thresholded here.
    peer_rel = (val_rec.get("peer_relative_context") or {})
    rel_state = peer_rel.get("relative_research_state") if peer_rel else val_rec.get("relative_research_state")
    peer_pctl = peer_rel.get("peer_relative_percentile") or pe_item.get("peer_percentile") or pb_item.get("peer_percentile") or ps_item.get("peer_percentile")
    peer_basis = {
        method_id: {"percentile": detail.get("percentile"), "peer_count": detail.get("peer_count")}
        for method_id, detail in sorted((val_rec.get("peer_relative") or {}).items())
        if isinstance(detail, Mapping) and detail.get("status") == "READY_RESEARCH_ONLY" and method_id not in _SIZE_CONTEXT_METHODS
    }

    peer_interpretation = "NOT_APPLICABLE"
    if isinstance(peer_pctl, (int, float)):
        if peer_pctl <= 0.33:
            peer_interpretation = "CHEAP_VS_PEERS"
            supports.append(f"VALUATION_CHEAP_VS_PEERS_PCTL_{peer_pctl:.2f}")
        elif peer_pctl >= 0.67:
            peer_interpretation = "EXPENSIVE_VS_PEERS"
            counters.append(f"VALUATION_EXPENSIVE_VS_PEERS_PCTL_{peer_pctl:.2f}")
        else:
            peer_interpretation = "MID_RANGE_VS_PEERS"
            supports.append("VALUATION_IN_LINE_WITH_PEERS")
    elif rel_state == "ATTRACTIVE_RELATIVE_RESEARCH":
        peer_interpretation = "CHEAP_VS_PEERS"
        supports.append("ATTRACTIVE_RELATIVE_RESEARCH_PEER_VALUATION")
    elif rel_state == "EXPENSIVE_RELATIVE_RESEARCH":
        peer_interpretation = "EXPENSIVE_VS_PEERS"
        counters.append("EXPENSIVE_RELATIVE_RESEARCH_PEER_VALUATION")
    elif rel_state == "IN_LINE_RELATIVE_RESEARCH":
        peer_interpretation = "MID_RANGE_VS_PEERS"
        supports.append("VALUATION_IN_LINE_WITH_PEERS")

    # Financial V2 history contains operating/balance-sheet ratios, not historical
    # price-to-fundamental multiples. Its percentiles cannot measure valuation
    # cheapness or expensiveness, nor be averaged across incompatible metrics.
    # The standing valuation producer retains current methods only. Keep the
    # financial history in its own context and fail closed on valuation history.
    own_history_interpretation = "UNAVAILABLE"

    # Monetary basis and availability checks
    share_basis = val_rec.get("share_basis")
    if share_basis in ("CURRENT_SHARE_RESEARCH_PROXY", "PROVIDER_VALUATION_PROXY"):
        uncertainties.append(f"SHARE_BASIS_PROXY_{share_basis}")

    if val_rec.get("earnings_state") == "PE_NOT_MEANINGFUL" or val_rec.get("pe_not_meaningful"):
        uncertainties.append("PE_NOT_MEANINGFUL_NEGATIVE_EARNINGS")
    elif val_rec.get("earnings_state") == "TURNAROUND_CONTEXT":
        uncertainties.append("VALUATION_IN_TURNAROUND_CONTEXT")

    exact_status = val_rec.get("status")
    if exact_status == "INPUT_BLOCKED":
        uncertainties.append("EXACT_VALUATION_INPUT_BLOCKED_MONETARY_BASIS")
    if research_pb_used and pb_val is not None:
        # The book-value multiple here is the research P/B over total owners' equity as reported
        # (non-controlling interests not deducted): never an exact or common-shareholder P/B.
        uncertainties.append("P_B_IS_RESEARCH_TOTAL_EQUITY_NCI_NOT_DEDUCTED_NOT_COMMON_SHAREHOLDER")
    if ev_ebitda_val is not None and ev_ebitda_item.get("denominator_period_semantics") == "SINGLE_REPORTING_PERIOD_NOT_ANNUALIZED":
        # Readiness-engine EV/EBITDA divides by one reporting period's EBITDA; it is comparable
        # within a same-period peer cohort only, never to a TTM multiple.
        uncertainties.append("EV_EBITDA_SINGLE_REPORTING_PERIOD_NOT_TTM")

    method_rows = {key: item for key, item in methods.items() if isinstance(item, Mapping)}
    pe_not_meaningful = (
        any(item.get("status") == "PE_NOT_MEANINGFUL" for item in method_rows.values())
        or val_rec.get("pe_not_meaningful") is True
        or val_rec.get("earnings_state") == "PE_NOT_MEANINGFUL"
    )
    if method_rows:
        # Market capitalisation is size context, never a valuation multiple -- the same invariant
        # attach_peer_relative already enforces for relative state. A row whose only usable
        # method is market cap has no price-to-fundamental relationship to interpret.
        has_usable_metrics = (
            any(item.get("status") in ("RESEARCH_USABLE", "READY")
                for key, item in method_rows.items() if key not in _SIZE_CONTEXT_METHODS)
        )
    else:
        # Compact records without per-method detail keep their own declared usability.
        has_usable_metrics = (
            val_rec.get("research_usable") is True
            or val_rec.get("has_usable_method") is True
            or (val_rec.get("usable_relative_method_count") or 0) > 0
            or pe_val is not None
            or pb_val is not None
            or ps_val is not None
        )
    size_method = next((method_rows[key] for key in _SIZE_CONTEXT_METHODS if key in method_rows), None)
    # A real negative-earnings diagnosis is retained context, not an available
    # price-to-fundamental multiple. Match the standing decision-input distinction
    # without blocking another usable method or changing research posture.
    status = ("AVAILABLE" if (peer_interpretation != "NOT_APPLICABLE" or has_usable_metrics)
              else "PARTIAL" if pe_not_meaningful else "UNAVAILABLE")
    unavailable_reasons: list[str] = []
    if status != "AVAILABLE":
        # A blocked size input (no exact-session price, no qualified share basis) blocks every
        # price-based multiple, so its own causes are named alongside the method-level ones.
        unavailable_reasons = sorted({
            str(code) for key, item in method_rows.items()
            if item.get("status") not in ("NOT_APPLICABLE", "RESEARCH_USABLE", "READY")
            for code in (item.get("blocker_reason_codes") or [])
        } | {"VALUATION_NO_USABLE_RELATIVE_METHOD" if method_rows else "VALUATION_CONTEXT_NOT_PROVIDED"})

    summary = {
        "status": status,
        "peer_relative_state": peer_interpretation,
        "own_history_state": own_history_interpretation,
        "own_history_reason_codes": ["COMPARABLE_VALUATION_HISTORY_NOT_RETAINED"],
        "peer_percentile": peer_pctl,
        "peer_relative_basis": peer_basis,
        "share_basis": share_basis,
        "pe_multiple": pe_val,
        "pb_multiple": pb_val,
        # Which P/B ``pb_multiple`` is, with that method's own limitations carried verbatim.
        "pb_basis": ({"method": "P/B_CURRENT_RESEARCH", "equity_definition": research_pb.get("equity_definition"),
                      "limitations": list(research_pb.get("limitations") or []),
                      "claim": "RESEARCH_ONLY_NOT_EXACT_NOT_COMMON_SHAREHOLDER"}
                     if research_pb_used and pb_val is not None else
                     {"method": (None if pb_val is None else "P/B" if (methods.get("P/B") or {}).get("value") == pb_val
                                 else "UNSPECIFIED_SOURCE"), "claim": None}),
        "ps_multiple": ps_val,
        "ev_ebitda_multiple": ev_ebitda_val,
        "earnings_state": val_rec.get("earnings_state"),
        "size_context": {
            "status": ("AVAILABLE" if (size_method or {}).get("status") in ("RESEARCH_USABLE", "READY")
                       else "UNAVAILABLE" if size_method is not None else "NOT_PROVIDED"),
            "method": "market_cap", "role": "SIZE_CONTEXT_NOT_A_VALUATION_MULTIPLE",
        },
        "unavailable_reason_codes": unavailable_reasons,
        "limitations": uncertainties,
        "valuation_method_reconciliation": val_rec.get("valuation_method_reconciliation") or {},
    }
    return summary, supports, counters, uncertainties


# ── Participation Evaluator ───────────────────────────────────────────────────

def evaluate_market_breadth(source: Mapping[str, Any], session: str) -> dict[str, Any]:
    """Preserve the observed cohort; qualify only same-session, counted breadth."""
    observed = source.get("market") or {}
    reasons = []
    if source.get("session") != session or observed.get("session") != session:
        reasons.append("MARKET_BREADTH_SESSION_MISMATCH_OR_UNKNOWN")
    counts = [observed.get(k) for k in (
        "official_universe_count", "exact_session_observed_count", "missing_current_session_count")]
    valid_counts = all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in counts)
    if not valid_counts or counts[0] <= 0 or counts[1] <= 0 or counts[1] + counts[2] != counts[0]:
        reasons.append("MARKET_BREADTH_DENOMINATOR_MISSING_OR_INCONSISTENT")
    if observed.get("status", "AVAILABLE") not in {"AVAILABLE", "PARTIAL"}:
        reasons.append("MARKET_BREADTH_PROVIDER_STATUS_UNQUALIFIED")
    if not observed.get("current_breadth_state"):
        reasons.append("MARKET_BREADTH_STATE_UNAVAILABLE")
    status = "BLOCKED" if reasons else ("PARTIAL" if counts[2] or observed.get("status") == "PARTIAL" else "AVAILABLE")
    return {
        "status": status,
        "market_regime": observed.get("current_breadth_state") if not reasons else "UNKNOWN",
        "reason_codes": reasons,
        "source_artifact_identity": source.get("artifact_identity"),
        "source_session": source.get("session"),
        "input_lineage": copy.deepcopy(source.get("input_lineage") or {}),
        "observation": copy.deepcopy(observed),
        "use": "OBSERVED_COHORT_CONTEXT_ONLY" if not reasons else "NO_CURRENT_BREADTH_USE",
        "limitations": ["PARTIAL_COHORT_NOT_ALL_MARKET", "NO_FORECAST_CAUSALITY_OR_EXECUTION_AUTHORITY"],
    }


def evaluate_participation(
    tactical_rec: Mapping[str, Any] | None,
    rvol_rec: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Determine participation confirmation / acceleration evidence."""
    supports: list[str] = []
    counters: list[str] = []

    rv_scoped = (tactical_rec or {}).get("relative_volume_provider_scoped")
    rvol_rec = rvol_rec or {}
    pctl = rvol_rec.get("relative_volume_percentile")
    accel = rvol_rec.get("volume_acceleration_ratio")

    if isinstance(accel, (int, float)):
        if accel >= 1.5:
            supports.append(f"VOLUME_ACCELERATION_HIGH_{accel:.2f}X")
        elif accel >= 1.1:
            supports.append(f"VOLUME_ACCELERATION_ELEVATED_{accel:.2f}X")
        elif accel <= 0.6:
            counters.append(f"VOLUME_CONTRACTION_{accel:.2f}X")

    if isinstance(pctl, (int, float)):
        if pctl >= 0.75:
            supports.append(f"RELATIVE_VOLUME_UPPER_QUARTILE_PCTL_{pctl:.2f}")
        elif pctl <= 0.25:
            counters.append(f"RELATIVE_VOLUME_LOWER_QUARTILE_PCTL_{pctl:.2f}")

    if isinstance(rv_scoped, (int, float)) and rv_scoped >= 1.2 and not supports:
        supports.append(f"ELEVATED_SESSION_RELATIVE_VOLUME_{rv_scoped:.2f}")

    summary = {
        "status": "AVAILABLE" if (rv_scoped is not None or pctl is not None or accel is not None) else "NOT_AVAILABLE",
        "relative_volume_provider_scoped": rv_scoped,
        "relative_volume_percentile": pctl,
        "volume_acceleration_ratio": accel,
        "authority_tier": "DERIVED_PROXY",
        "warning": "DIMENSIONLESS_VOLUME_COMPARISON_NOT_ADV_OR_EXECUTION_CAPACITY",
    }
    return summary, supports, counters


# ── Research Action Posture Decision Policy ───────────────────────────────────

#: Branch-1 wording by fundamental evidence availability (the posture itself is unchanged): no
#: current technical evidence AND no current fundamental direction, whatever evidence is known.
_INSUFFICIENT_RESEARCH_REASON = {
    fundamental_signals.ABSENT: ("Insufficient technical price series and fundamental analysis data to establish a current "
                                 "research stance."),
    fundamental_signals.STALE_ONLY: ("Insufficient technical price series, and fundamental evidence is stale-only research "
                                     "context (known, visible, never a current direction); no current research stance."),
    fundamental_signals.CURRENT_NON_DIRECTIONAL: ("Insufficient technical price series, and current fundamental evidence "
                                                  "establishes no direction; no current research stance."),
    fundamental_signals.NOT_APPLICABLE_ENTITY: ("Insufficient technical price series, and the entity family is not "
                                                "decision-applicable for fundamental signals (its evidence stays research "
                                                "context); no current research stance."),
}

def decide_research_action_posture(
    *,
    ticker: str,
    fundamental_state: str,
    tactical_phase: str,
    tactical_rec: Mapping[str, Any],
    fund_supports: list[str],
    fund_counters: list[str],
    tac_supports: list[str],
    tac_counters: list[str],
    val_supports: list[str],
    val_counters: list[str],
    part_supports: list[str],
    part_counters: list[str],
    participation_summary: Mapping[str, Any] | None = None,
    market_sector_summary: Mapping[str, Any] | None = None,
    fundamental_evidence_availability: str | None = None,
) -> tuple[str, str, str]:
    """Pure deterministic research policy mapping explicit evidence into research_action_posture.

    ``fundamental_evidence_availability`` only words the insufficient-research explanation: an
    insufficient current direction with known (stale, non-directional or entity-gated) evidence is
    never described as missing fundamental data. It never moves a posture.

    Returns:
        (posture, why_now, missing_evidence_decision_effect)
    """
    eligible = tactical_rec.get("eligible") is True
    brk_v3 = tactical_rec.get("breakout_state_v3")
    trig_state = tactical_rec.get("trigger_state")
    trig_type = tactical_rec.get("trigger_type")
    ms = tactical_rec.get("market_structure_state")
    choch = tactical_rec.get("choch_state")
    bos = tactical_rec.get("bos_state")
    dist_piv = tactical_rec.get("distance_to_pivot_pct")
    dist_inv = tactical_rec.get("distance_to_invalidation_pct")
    part_summary = participation_summary or {}
    mkt_summary = market_sector_summary or {}
    mkt_regime = mkt_summary.get("market_regime", "NEUTRAL_MIXED")
    sector_lead = mkt_summary.get("sector_leadership", "IN_LINE")

    part_available = part_summary.get("status") == "AVAILABLE"
    vol_accel = part_summary.get("volume_acceleration_ratio")
    vol_pctl = part_summary.get("relative_volume_percentile")
    part_contradiction = False
    part_contradiction_reason = ""
    if part_available:
        if isinstance(vol_accel, (int, float)) and vol_accel <= 0.60:
            part_contradiction = True
            part_contradiction_reason = f"VOLUME_CONTRACTION_{vol_accel:.2f}X"
        elif isinstance(vol_pctl, (int, float)) and vol_pctl <= 0.25:
            part_contradiction = True
            part_contradiction_reason = f"LOW_RELATIVE_VOLUME_PCTL_{vol_pctl:.2f}"
        elif any("VOLUME_CONTRACTION" in c or "RELATIVE_VOLUME_LOWER_QUARTILE" in c for c in part_counters):
            part_contradiction = True
            part_contradiction_reason = part_counters[0] if part_counters else "VOLUME_CONTRACTION"

    is_bearish_market = (
        # DETERIORATING_BREADTH is the real current_market_sector_leadership_context/v1 value for a
        # weak/negative-momentum, below-MA20 majority session. NARROW_LEADERSHIP is deliberately
        # excluded: the same engine's own _leadership_state mapping treats it as LEADING, not
        # bearish (advancers still exceed decliners; participation is merely less broad than ideal).
        mkt_regime in ("DETERIORATING_BREADTH", "DEFENSIVE", "BEARISH", "WEAK", "DISTRIBUTION", "HIGH_RISK")
        or "DEFENSIVE" in str(mkt_regime).upper()
        or "BEARISH" in str(mkt_regime).upper()
    )
    is_sector_leader = sector_lead in ("LEADING", "LEADER", "STRONG_LEADERSHIP", "OUTPERFORMING")

    # 1. INSUFFICIENT CURRENT RESEARCH
    if not eligible and fundamental_state == FUNDAMENTAL_INSUFFICIENT:
        why = f"{ticker}: " + _INSUFFICIENT_RESEARCH_REASON.get(
            fundamental_evidence_availability, _INSUFFICIENT_RESEARCH_REASON[fundamental_signals.ABSENT])
        return POSTURE_INSUFFICIENT, why, EFFECT_BLOCKS_DECISION

    # 2. REAL ADVERSE EVIDENCE -> REDUCE / AVOID
    # Adverse requires real negative evidence, never missing data.
    if bos == "BEARISH_BOS_DETECTED_BY_RULE" or (ms == "DOWNTREND" and not (brk_v3 == "BREAKOUT" or trig_state == "TRIGGERED")):
        why = f"{ticker}: Bearish market structure breakdown with confirmed lower lows / bearish BOS; adverse entry environment."
        return POSTURE_AVOID, why, EFFECT_DOES_NOT_BLOCK

    if fundamental_state == FUNDAMENTAL_DETERIORATING and (ms in ("DOWNTREND", "EARLY_BEARISH_REVERSAL") or tactical_phase in (TACTICAL_DISTRIBUTION_RISK, TACTICAL_BREAKDOWN)):
        why = f"{ticker}: Deteriorating fundamentals aligned with bearish structural pressure; research posture is to avoid new exposure."
        return POSTURE_AVOID, why, EFFECT_DOES_NOT_BLOCK

    if brk_v3 == "FAILED_BREAKOUT" and fundamental_state == FUNDAMENTAL_DETERIORATING:
        why = f"{ticker}: Breakout attempt failed back below pivot while fundamentals are deteriorating; high rejection risk."
        return POSTURE_REDUCE, why, EFFECT_DOES_NOT_BLOCK

    if brk_v3 == "FAILED_BREAKOUT":
        why = f"{ticker}: Breakout attempt failed back below pivot resistance; wait for structural re-basing before considering re-entry."
        return POSTURE_WAIT_FOR_CONFIRMATION, why, EFFECT_DOES_NOT_BLOCK

    # 3. EXTENSION RISK -> HOLD_DO_NOT_ADD / HOLD
    # Distinguish SECURITY_ATTRACTIVE from CURRENT_ENTRY_ATTRACTIVE. Never AVOID solely for extension!
    if tactical_phase == TACTICAL_EXTENDED or brk_v3 == "EXTENDED_AFTER_BREAKOUT" or (dist_piv is not None and dist_piv > 0.05 and brk_v3 in ("BREAKOUT", "EXTENDED_AFTER_BREAKOUT")):
        piv_str = f"{dist_piv*100:.1f}%" if dist_piv is not None else "extended"
        if fundamental_state != FUNDAMENTAL_DETERIORATING:
            why = f"{ticker}: Structure is strong and breakout succeeded, but price is now extended past pivot ({piv_str}); hold existing thesis but do not chase new entry."
            return POSTURE_HOLD_DO_NOT_ADD, why, EFFECT_DOES_NOT_BLOCK
        else:
            why = f"{ticker}: Price extended into resistance with unconfirmed/mixed fundamentals; poor risk/reward asymmetry for new entry."
            return POSTURE_HOLD_DO_NOT_ADD, why, EFFECT_DOES_NOT_BLOCK

    # 4. BREAKOUT TRIGGER FIRED -> INITIATE_ON_BREAKOUT (with deterministic participation/market filtering)
    if (brk_v3 == "BREAKOUT" or trig_state == "TRIGGERED") and (trig_type in ("PIVOT_BREAKOUT_TRIGGER", "CONFIRMED_BOS_TRIGGER") or tactical_phase == TACTICAL_BREAKOUT_CONFIRMED):
        if fundamental_state == FUNDAMENTAL_DETERIORATING:
            why = f"{ticker}: Technical breakout trigger fired but fundamental deterioration creates divergence; awaiting fundamental confirmation."
            return POSTURE_WAIT_FOR_CONFIRMATION, why, EFFECT_DOES_NOT_BLOCK

        if ms == "DOWNTREND" or tactical_phase in (TACTICAL_EARLY_REVERSAL, TACTICAL_BREAKOUT_SETUP):
            why = f"{ticker}: Breakout attempt emerging from established downtrend structure; awaiting higher-low structural confirmation."
            return POSTURE_WAIT_FOR_CONFIRMATION, why, EFFECT_DOES_NOT_BLOCK

        if part_contradiction:
            why = f"{ticker}: Breakout trigger fired, but participation shows volume contradiction ({part_contradiction_reason}); awaiting volume confirmation before initiating."
            return POSTURE_WAIT_FOR_CONFIRMATION, why, EFFECT_DOES_NOT_BLOCK

        if is_bearish_market:
            why = f"{ticker}: Valid structural breakout trigger fired, but defensive/weak market regime ({mkt_regime}) creates headwind; awaiting broader market confirmation."
            return POSTURE_WAIT_FOR_CONFIRMATION, why, EFFECT_DOES_NOT_BLOCK

        lead_note = " with supportive sector leadership" if is_sector_leader else ""
        participation_note = ("supportive participation" if part_supports else
                              "no observed participation contradiction" if part_available else
                              "participation evidence unavailable")
        why = f"{ticker}: Valid structural breakout trigger fired at pivot level with non-conflicting fundamentals and {participation_note}{lead_note}; actionable initiation setup."
        return POSTURE_INITIATE_ON_BREAKOUT, why, EFFECT_DOES_NOT_BLOCK

    # 5. RETEST OF BROKEN PIVOT -> ACCUMULATE_ON_RETEST
    if tactical_rec.get("pivot_retest_confirmed") is True and ms in ("UPTREND", "EARLY_BULLISH_REVERSAL"):
        if dist_inv is not None and dist_inv > 0 and fundamental_state != FUNDAMENTAL_DETERIORATING:
            if is_bearish_market:
                why = f"{ticker}: Constructive retest of pivot, but defensive market regime requires confirmation."
                return POSTURE_WAIT_FOR_CONFIRMATION, why, EFFECT_DOES_NOT_BLOCK
            why = f"{ticker}: Bullish market structure intact with price constructively testing/retesting pivot support above invalidation level; attractive accumulation location."
            return POSTURE_ACCUMULATE_ON_RETEST, why, EFFECT_DOES_NOT_BLOCK

    # 6. EARLY REVERSAL / COMPRESSION -> EARLY_WATCH
    if tactical_phase in (TACTICAL_EARLY_REVERSAL, TACTICAL_BREAKOUT_SETUP) or choch == "BULLISH_CHOCH_DETECTED_BY_RULE" or ms == "EARLY_BULLISH_REVERSAL":
        if fundamental_state != FUNDAMENTAL_DETERIORATING:
            why = f"{ticker}: Early bullish structural reversal / base compression observed, but breakout trigger has not yet fired; prioritized for early monitoring."
            return POSTURE_EARLY_WATCH, why, EFFECT_DOES_NOT_BLOCK

    # 7. TREND CONTINUATION / ESTABLISHED UPTREND -> HOLD
    if ms == "UPTREND" and fundamental_state in (FUNDAMENTAL_IMPROVING, FUNDAMENTAL_STABLE, FUNDAMENTAL_TURNAROUND):
        why = f"{ticker}: Established uptrend confirmed by higher swing highs/lows with supportive fundamentals; constructive holding posture."
        return POSTURE_HOLD, why, EFFECT_DOES_NOT_BLOCK

    # 8. CONSTRUCTIVE BUT AWAITING CONFIRMATION -> WAIT_FOR_CONFIRMATION
    if ms in ("UPTREND", "EARLY_BULLISH_REVERSAL", "RANGE") or fundamental_state in (FUNDAMENTAL_IMPROVING, FUNDAMENTAL_STABLE):
        why = f"{ticker}: Constructive background conditions present, but waiting for clear structural trigger confirmation."
        return POSTURE_WAIT_FOR_CONFIRMATION, why, EFFECT_DOES_NOT_BLOCK

    # 9. WEAK OR DOWNTREND WITHOUT EXTREME BREAKDOWN -> AVOID
    if ms == "DOWNTREND" or tactical_phase == TACTICAL_BREAKDOWN:
        why = f"{ticker}: Established downtrend structure; avoid new capital commitments until a basing or reversal pattern forms."
        return POSTURE_AVOID, why, EFFECT_DOES_NOT_BLOCK

    # 10. Fallback
    why = f"{ticker}: Neutral or mixed structural and fundamental signals; maintain observational watch."
    return POSTURE_WAIT_FOR_CONFIRMATION, why, EFFECT_DOES_NOT_BLOCK


def _priority_posture_reconciliation(
    queue_record: Mapping[str, Any] | None, *, posture: str, tactical: Mapping[str, Any], why_now: str,
) -> dict[str, Any]:
    """Compact, deterministic explanation of priority versus action posture.

    Priority selects research review lanes; it never relaxes the integrated posture
    policy.  Keeping this join in the integrated record means a reviewer need not
    reconstruct it from the separate Daily queue and technical artifacts.
    """
    queue_record = queue_record or {}
    tier = queue_record.get("research_priority_tier")
    entry_relevant = queue_record.get("entry_relevant") is True
    base = {
        "research_priority_tier": tier,
        "entry_relevant": entry_relevant,
        "entry_action": queue_record.get("entry_action"),
        "lane_specific_priority": queue_record.get("lane_specific_priority") or {},
        "priority_reasons": list(queue_record.get("priority_reasons") or []),
        "integrated_posture": posture,
        "integrated_posture_reason": why_now,
    }
    if not queue_record:
        return {**base, "reconciliation_category": "CONTRACT_SHAPE_MISMATCH",
                "reason": "PRIORITY_QUEUE_CONTEXT_NOT_PROVIDED_TO_INTEGRATED_BUILDER"}
    if not (tier == "PRIORITY_NOW" and entry_relevant):
        return {**base, "reconciliation_category": "LEGITIMATE_POLICY_OUTCOME",
                "reason": "NOT_PRIORITY_NOW_ENTRY_RELEVANT"}
    if posture in {POSTURE_INITIATE_ON_BREAKOUT, POSTURE_ACCUMULATE_ON_RETEST, POSTURE_EARLY_WATCH}:
        return {**base, "reconciliation_category": "LEGITIMATE_POLICY_OUTCOME",
                "reason": "PRIORITY_RESEARCH_LANE_AND_CURRENT_ACTION_POSTURE_ALIGNED"}
    if tactical.get("eligible") is not True or tactical.get("market_structure_state") == "INSUFFICIENT_HISTORY":
        return {**base, "reconciliation_category": "MISSING_HISTORY_OR_FEATURE_FITNESS",
                "reason": "TACTICAL_STRUCTURE_NOT_FIT_FOR_CURRENT_ACTION_POSTURE"}
    return {**base, "reconciliation_category": "LEGITIMATE_POLICY_OUTCOME",
            "reason": "PRIORITY_REVIEW_REMAINS_DISTINCT_FROM_ACTION_READINESS"}


# ── Single Ticker Decision Record Builder ─────────────────────────────────────

def build_ticker_integrated_decision(
    *,
    ticker: str,
    as_of_session: str,
    tactical_record: Mapping[str, Any] | None,
    financial_record: Mapping[str, Any] | None,
    valuation_record: Mapping[str, Any] | None,
    relative_volume_record: Mapping[str, Any] | None,
    market_sector_record: Mapping[str, Any] | None,
    portfolio_record: Mapping[str, Any] | None = None,
    legacy_opportunity_record: Mapping[str, Any] | None = None,
    priority_queue_record: Mapping[str, Any] | None = None,
    momentum_record: Mapping[str, Any] | None = None,
    tactical_confirmation_record: Mapping[str, Any] | None = None,
    tactical_boundaries_record: Mapping[str, Any] | None = None,
    tactical_boundaries_identity: str | None = None,
    structural_condition_source_identity: str | None = None,
    corporate_intelligence_record: Mapping[str, Any] | None = None,
    producer_artifact_identities: Mapping[str, Any] | None = None,
    technical_coverage_disposition_record: Mapping[str, Any] | None = None,
    operational_fundamental_context_record: Mapping[str, Any] | None = None,
    liquidity_research_record: Mapping[str, Any] | None = None,
    entity_applicability_record: Mapping[str, Any] | None = None,
    official_liquidity_record: Mapping[str, Any] | None = None,
    financial_peer_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble one complete, self-contained integrated investment decision record.

    ``technical_coverage_disposition_record`` is this ticker's retained same-session technical
    coverage disposition (see ``resolve_evidence_currency``); absent, evidence currency fails
    closed to NO_CURRENT_EVIDENCE. ``liquidity_research_record`` and
    ``entity_applicability_record`` only feed the descriptive Current Research decision input;
    neither can move posture.
    """
    tactical = tactical_record or {}
    financial = financial_record or {}
    valuation = valuation_record or {}
    rvol = relative_volume_record or {}
    market = market_sector_record or {}
    momentum = momentum_record or {}
    confirmation = tactical_confirmation_record or {}

    # 1. Fundamental: explicit level/direction/transition components, freshness-gated against the
    # decision session; fundamental_state is derived from them and they stay on the record.
    fund_synthesis = evaluate_fundamental_synthesis(financial, decision_session=as_of_session)
    applied_operational_context = None
    # The bridge is consulted only where Financial V2 leaves the direction insufficient and not
    # conflicted; a record supplied for any other ticker is ignored and never attached.
    bridge_consulted = (operational_fundamental_context_record is not None
                        and operational_fundamental_bridge_eligible(financial, decision_session=as_of_session))
    if bridge_consulted and operational_fundamental_context_record.get("status") == "RESEARCH_USABLE":
        candidate = evaluate_fundamental_synthesis(
            operational_fundamental_context_record, decision_session=as_of_session,
            dialect=fundamental_signals.DIALECT_OPERATIONAL_BRIDGE,
        )
        if candidate["fundamental_state"] != FUNDAMENTAL_INSUFFICIENT:
            # The Financial V2 evidence the bridge supplements stays visible (never a vote here).
            fund_synthesis = {**candidate, "financial_v2_research_evidence": fundamental_signals.research_evidence(fund_synthesis)}
            applied_operational_context = operational_fundamental_context_record
    fund_state = fund_synthesis["fundamental_state"]
    fund_supp = list(fund_synthesis["supporting_reason_codes"])
    fund_count = list(fund_synthesis["contradicting_reason_codes"])

    # 2. Tactical
    tac_phase, tac_supp, tac_count = evaluate_tactical_phase(tactical)

    # 3. Valuation
    val_summary, val_supp, val_count, val_uncert = evaluate_valuation_context(valuation, financial)

    # 3b. Financial composite context (section 14): a pure join of 1 and 3 above, computed
    # from their own already-produced outputs. Additive only -- feeds nothing below.
    financial_composite_context = evaluate_financial_composite_context(
        fund_state=fund_state, fund_supports=fund_supp, fund_counters=fund_count,
        val_summary=val_summary, val_supports=val_supp, val_counters=val_count,
        fundamental_evidence_availability=fund_synthesis.get("fundamental_evidence_availability"),
        fundamental_risk_level=(fund_synthesis.get("fundamental_risk_level") or {}).get("state"),
    )

    # 4. Participation
    part_summary, part_supp, part_count = evaluate_participation(tactical, rvol)

    # 5. Market / Sector Context
    # current_market_sector_leadership_context/v1's real shape (the artifact canonical_post_close_
    # pipeline.py actually wires in as market_sector_artifact) carries market-wide regime at
    # market["market"]["current_breadth_state"] and per-ticker sector leadership at
    # market["ticker_contexts"][ticker]["sector_leadership_context"]["leadership_state"] -- not the
    # flat breadth_regime/market_state/sector_relative_context/sector_leadership_state keys read
    # previously (that shape matches opportunity_context.py's unrelated _market_axis() output, not
    # this artifact), which made market_regime/sector_leadership silently constant defaults in
    # production regardless of the real session's breadth/leadership.
    ticker_sector_ctx = ((market.get("ticker_contexts") or {}).get(ticker) or {}).get("sector_leadership_context") or {}
    breadth = evaluate_market_breadth(market, as_of_session)
    if market.get("session") != as_of_session:
        ticker_sector_ctx = {"status": "BLOCKED", "reason": "SECTOR_CONTEXT_SESSION_MISMATCH_OR_UNKNOWN"}
    mkt_summary = {
        "market_regime": breadth["market_regime"],
        "market_breadth": breadth,
        # Absence is not an observed neutral sector. Keep the qualified market
        # breadth while preserving the ticker's separate sector coverage gate.
        "sector_leadership": (ticker_sector_ctx.get("leadership_state")
                              if ticker_sector_ctx.get("status") in (None, "AVAILABLE") else None) or "UNKNOWN",
        "sector_leadership_status": ticker_sector_ctx.get("status") or ("AVAILABLE" if ticker_sector_ctx.get("leadership_state") else "UNAVAILABLE"),
        "sector_leadership_reason_codes": list(dict.fromkeys(
            ([ticker_sector_ctx["reason"]] if ticker_sector_ctx.get("reason") else [])
            + list(((market.get("ticker_contexts") or {}).get(ticker) or {}).get("coverage_limitations") or [])
            + (["SECTOR_LEADERSHIP_CONTEXT_NOT_PROVIDED"] if not ticker_sector_ctx else []))),
        "sector_group_key": ticker_sector_ctx.get("group_key"),
        "sector_group_coverage_ratio": ticker_sector_ctx.get("group_coverage_ratio"),
        "authority_tier": "CURRENT_RESEARCH_DESCRIPTIVE",
    }
    if mkt_summary["sector_leadership"] == "UNKNOWN" and not mkt_summary["sector_leadership_reason_codes"]:
        mkt_summary["sector_leadership_reason_codes"] = ["SECTOR_LEADERSHIP_" + mkt_summary["sector_leadership_status"]]
    market_context_provided = isinstance(market_sector_record, Mapping)

    # 6. Portfolio Context
    if portfolio_record is not None and isinstance(portfolio_record, Mapping) and portfolio_record.get("status") != "NOT_PROVIDED":
        portfolio_summary = {
            "status": "AVAILABLE",
            "is_held": portfolio_record.get("is_held", False),
            "concentration_flag": portfolio_record.get("concentration_flag"),
            "sector_overlap": portfolio_record.get("sector_overlap"),
            "policy_note": "Portfolio availability does not alter intrinsic security attractiveness.",
        }
    else:
        portfolio_summary = {
            "status": "NOT_PROVIDED",
            # Unknown, not False: an absent private portfolio never means NOT_HELD.
            "is_held": None,
            "policy_note": "No explicit portfolio supplied; security attractiveness is independently evaluated.",
        }

    # 6b. Corporate Intelligence (Section 13: additive only; computed here, but never passed
    # into decide_research_action_posture below -- no automatic posture change merely because
    # a catalyst/risk exists).
    corporate_intelligence_summary = evaluate_corporate_intelligence_context(
        corporate_intelligence_record, as_of_session=as_of_session,
    )

    # 7. Posture & Why Now
    posture, why_now, missing_effect = decide_research_action_posture(
        ticker=ticker,
        fundamental_state=fund_state,
        tactical_phase=tac_phase,
        tactical_rec=tactical,
        fund_supports=fund_supp,
        fund_counters=fund_count,
        tac_supports=tac_supp,
        tac_counters=tac_count,
        val_supports=val_supp,
        val_counters=val_count,
        part_supports=part_supp,
        part_counters=part_count,
        participation_summary=part_summary,
        market_sector_summary=mkt_summary,
        fundamental_evidence_availability=fund_synthesis.get("fundamental_evidence_availability"),
    )
    # 7b. Evidence-currency gate (CURRENT_DECISION_SURFACE_CONVERGENCE_V1, the only posture
    # correction authorized there). WAIT_FOR_CONFIRMATION means evidence exists and a defined
    # confirmation is pending; with no current evidence at all it resolves to the existing
    # fail-closed posture. No threshold is retuned and no other policy branch is reordered.
    evidence_currency = resolve_evidence_currency(technical_coverage_disposition_record, decision_session=as_of_session)
    evidence_currency_gate = {"rule": EVIDENCE_CURRENCY_GATE_RULE, "applied": False}
    if evidence_currency == EVIDENCE_CURRENCY_NO_CURRENT_EVIDENCE and posture == POSTURE_WAIT_FOR_CONFIRMATION:
        evidence_currency_gate = {"rule": EVIDENCE_CURRENCY_GATE_RULE, "applied": True, "ungated_policy_output": posture}
        posture = POSTURE_INSUFFICIENT
        why_now = (
            f"{ticker}: No current price/technical evidence for this session (evidence_currency="
            f"{EVIDENCE_CURRENCY_NO_CURRENT_EVIDENCE}); a wait-for-confirmation posture requires existing "
            "evidence with a defined pending confirmation."
        )
        missing_effect = EFFECT_BLOCKS_DECISION
    priority_posture = _priority_posture_reconciliation(
        priority_queue_record, posture=posture, tactical=tactical, why_now=why_now,
    )

    # 8. Trigger & Invalidation. V3 levels and their conditions share the same
    # source. Preserve the separate watchlist strategy verbatim without attaching
    # its potentially different level/direction to a V3 structural measurement.
    from prospective_decision_retention import serialize_boundary_condition, serialize_structural_condition
    boundaries = tactical_boundaries_record or {}
    structural_identity = structural_condition_source_identity
    trigger = {
        "trigger_type": tactical.get("trigger_type", "NO_TRIGGER"),
        "trigger_level": tactical.get("trigger_level"),
        "trigger_state": tactical.get("trigger_state", "NOT_AVAILABLE"),
        "distance_to_trigger_pct": tactical.get("distance_to_trigger_pct"),
        "warning": "TRIGGER_IS_RESEARCH_MEASUREMENT_NOT_EXECUTION_AUTHORITY",
        "condition": serialize_structural_condition(
            tactical, role="trigger", session=as_of_session, source_identity=structural_identity,
        ),
        "watchlist_condition": serialize_boundary_condition(
            boundaries.get("confirmation_boundary") if isinstance(boundaries, Mapping) else None,
            role="trigger", source_strategy_identity=tactical_boundaries_identity,
        ),
    }
    invalidation = {
        "invalidation_level": tactical.get("invalidation_level"),
        "invalidation_method": tactical.get("invalidation_method") or "CONFIRMED_SWING_LEVEL_OR_SUPPORT_FALLBACK",
        "distance_to_invalidation_pct": tactical.get("distance_to_invalidation_pct"),
        "warning": "STRUCTURAL_INVALIDATION_LEVEL_NOT_A_STOP_LOSS",
        "condition": serialize_structural_condition(
            tactical, role="invalidation", session=as_of_session, source_identity=structural_identity,
        ),
        "watchlist_condition": serialize_boundary_condition(
            boundaries.get("technical_invalidation_boundary") if isinstance(boundaries, Mapping) else None,
            role="invalidation", source_strategy_identity=tactical_boundaries_identity,
        ),
    }

    # 9. Exact capabilities unavailable list
    exact_unavail: list[str] = []
    if tactical.get("high_low_basis") == "NOT_COMPATIBLE":
        exact_unavail.append("TRUE_ATR_HIGH_LOW_INCOMPATIBLE")
    if val_summary.get("status") == "UNAVAILABLE" or "EXACT_VALUATION_INPUT_BLOCKED_MONETARY_BASIS" in val_uncert:
        exact_unavail.append("EXACT_MONETARY_VALUATION_BLOCKED")
    exact_unavail.append("EXACT_EXECUTION_CAPACITY_BLOCKED")
    exact_unavail.append("PIT_BACKTEST_AUTHORITY_BLOCKED")

    # 10. Multi-axis synthesis
    all_counter_thesis = list(dict.fromkeys(fund_count + tac_count + val_count + part_count))
    all_uncertainties = list(dict.fromkeys(val_uncert + (tactical.get("blockers") or [])))

    # Evidence axes are a strictly additive description of the already-computed inputs above.
    # They are intentionally built after posture, trigger and invalidation so they cannot silently
    # move those governed policy outputs.
    evidence_axes = build_evidence_axes(
        fund_state=fund_state, fund_supports=fund_supp, fund_counters=fund_count,
        financial=financial, valuation=valuation, val_summary=val_summary,
        val_supports=val_supp, val_counters=val_count, val_uncertainties=val_uncert,
        tactical=tactical, tactical_phase=tac_phase, tactical_supports=tac_supp,
        tactical_counters=tac_count, momentum=momentum, confirmation=confirmation,
        participation_summary=part_summary, market_summary=mkt_summary,
        market_context_provided=market_context_provided, priority_record=priority_queue_record,
        portfolio_summary=portfolio_summary, source_artifact_identities=producer_artifact_identities,
        corporate_intelligence_summary=corporate_intelligence_summary,
        operational_fundamental_context=applied_operational_context,
        fundamental_synthesis=fund_synthesis,
    )
    evidence_axis_coherence = evaluate_evidence_axis_coherence(evidence_axes)
    if financial_peer_context is not None:
        evidence_axes["FUNDAMENTAL"].setdefault("context", {})["financial_peer_context"] = copy.deepcopy(dict(financial_peer_context))

    # Legacy stance comparison
    legacy_stance = None
    legacy_entry_state = None
    if legacy_opportunity_record:
        legacy_stance = (legacy_opportunity_record.get("deterministic_research_inference") or {}).get("research_stance") or legacy_opportunity_record.get("research_stance")
        legacy_entry_state = (legacy_opportunity_record.get("factual_axes") or {}).get("tactical_entry_state") or legacy_opportunity_record.get("entry_state")

    record: dict[str, Any] = {
        "ticker": ticker,
        "as_of_session": as_of_session,
        "research_action_posture": posture,
        "evidence_currency": evidence_currency,
        "evidence_currency_lineage": {
            "method": EVIDENCE_CURRENCY_SOURCE_CONTRACT,
            "disposition": (technical_coverage_disposition_record or {}).get("disposition"),
            "feature_as_of_session": (technical_coverage_disposition_record or {}).get("feature_as_of_session"),
        },
        "evidence_currency_gate": evidence_currency_gate,
        "position_context": position_context_view(portfolio_summary),
        # Orthogonal inspection axis; never part of the action label or decision_identity.
        "opportunity_priority": opportunity_priority_view(priority_queue_record),
        "fundamental_state": fund_state,
        # The fundamental decision-policy epoch; part of decision_identity. A state compared
        # across epochs is NOT_COMPARABLE_POLICY_CHANGE, never an issuer/market transition.
        "fundamental_decision_policy_version": fundamental_signals.DECISION_POLICY_VERSION,
        # What fundamental evidence is known, apart from whether a current direction exists.
        "fundamental_evidence_availability": fund_synthesis.get("fundamental_evidence_availability"),
        # Qualified level evidence only; never derived from the direction.
        "fundamental_risk_level": fund_synthesis.get("fundamental_risk_level"),
        # The components fundamental_state is derived from, never collapsed into it.
        "fundamental_synthesis": fund_synthesis,
        "tactical_phase": tac_phase,
        "market_structure_state": tactical.get("market_structure_state", "INSUFFICIENT_HISTORY"),
        "breakout_state_v3": tactical.get("breakout_state_v3", "NO_VALID_PIVOT"),
        "why_now": why_now,
        "priority_posture_reconciliation": priority_posture,
        "fundamental_support": fund_supp,
        "technical_support": tac_supp,
        "valuation_context_summary": val_summary,
        "financial_composite_context": financial_composite_context,
        "valuation_methods": valuation.get("methods") or {},
        "valuation_method_reconciliation": valuation.get("valuation_method_reconciliation") or {},
        "calculation_readiness_context": valuation.get("calculation_readiness_context") or {},
        "participation_support": part_supp,
        # Additive analytical context (TACTICAL_MOMENTUM_PARTICIPATION_CONFIRMATION_V1). Neither
        # field feeds decide_research_action_posture above -- research_action_posture is computed
        # identically to before this milestone. A ticker is not upgraded merely because RSI/MACD/
        # participation agree; see tactical_confirmation_context.py's own no-vote-counting design.
        "momentum_context": momentum_record if momentum_record is not None else {"status": "NOT_AVAILABLE", "reason": "MOMENTUM_CONTEXT_NOT_PROVIDED_TO_INTEGRATED_BUILDER"},
        "tactical_confirmation_context": tactical_confirmation_record if tactical_confirmation_record is not None else {"tactical_confirmation_state": "INSUFFICIENT_EVIDENCE", "reason": "TACTICAL_CONFIRMATION_CONTEXT_NOT_PROVIDED_TO_INTEGRATED_BUILDER"},
        "evidence_axes": evidence_axes,
        "evidence_axis_coherence": evidence_axis_coherence,
        "counter_thesis": all_counter_thesis,
        "material_uncertainties": all_uncertainties,
        "exact_capabilities_unavailable": exact_unavail,
        "missing_evidence_decision_effect": missing_effect,
        "trigger": trigger,
        "invalidation": invalidation,
        "participation": part_summary,
        "market_sector_context": mkt_summary,
        "portfolio_context": portfolio_summary,
        "corporate_intelligence_context": corporate_intelligence_summary,
        "legacy_comparison": {
            "legacy_stance": legacy_stance,
            "legacy_entry_state": legacy_entry_state,
            "posture_delta": f"{legacy_stance} -> {posture}" if legacy_stance else "NO_LEGACY_STANCE",
        },
        "source_identities": {
            "tactical_structure_identity": tactical.get("artifact_identity"),
            "financial_analysis_identity": financial.get("source_context_identity") or financial.get("artifact_identity"),
            "valuation_identity": valuation.get("artifact_identity"),
            "relative_volume_identity": rvol.get("artifact_identity"),
            "priority_queue_record_identity": (priority_queue_record or {}).get("content_identity"),
            "momentum_identity": (producer_artifact_identities or {}).get("momentum") or momentum.get("artifact_identity"),
            "tactical_confirmation_identity": (producer_artifact_identities or {}).get("tactical_confirmation") or confirmation.get("artifact_identity"),
            "tactical_boundaries_identity": tactical_boundaries_identity,
            "corporate_intelligence_identity": (producer_artifact_identities or {}).get("corporate_intelligence"),
        },
        "authority_boundary": {
            "is_actionable": False,
            "no_score_rank_target_or_probability": True,
            "research_support_not_execution_instruction": True,
            "security_attractiveness_separate_from_portfolio_fit": True,
            "unknown_is_local_does_not_force_global_wait": True,
        },
    }
    if financial_peer_context is not None:
        record["financial_peer_context"] = copy.deepcopy(dict(financial_peer_context))
        record["source_identities"]["financial_peer_materialization_identity"] = financial_peer_context.get("source_materialization_identity")
    record["decision_identity"] = decision_identity(record)
    if bridge_consulted:
        record["operational_fundamental_context"] = copy.deepcopy(dict(operational_fundamental_context_record))
        record["source_identities"]["operational_fundamental_integration_identity"] = (
            (producer_artifact_identities or {}).get("operational_fundamental_integration")
        )
        record["decision_identity"] = decision_identity(record)
    # CURRENT_RESEARCH_DECISION_CONVERGENCE_V1: a pure restatement of the record's own evidence,
    # built last so it can neither move posture nor enter decision_identity.
    record["current_research_decision_input"] = decision_input.build_ticker_decision_input(
        session=as_of_session, record=record, financial_record=financial, valuation_record=valuation,
        disposition_record=technical_coverage_disposition_record,
        sector_context=((market.get("ticker_contexts") or {}).get(ticker) if market_context_provided else None),
        liquidity_record=liquidity_research_record, entity_applicability_record=entity_applicability_record,
        official_liquidity_record=official_liquidity_record,
        operational_context=operational_fundamental_context_record if bridge_consulted else None,
    )
    return record


# ── Full Product Artifact Builder ─────────────────────────────────────────────

def build_artifact(
    *,
    session: str,
    requested_at: str,
    technical_structure_artifact: Mapping[str, Any],
    financial_analysis_artifact: Mapping[str, Any] | None = None,
    current_valuation_artifact: Mapping[str, Any] | None = None,
    relative_volume_artifact: Mapping[str, Any] | None = None,
    market_sector_artifact: Mapping[str, Any] | None = None,
    portfolio_artifact: Mapping[str, Any] | None = None,
    legacy_decision_artifact: Mapping[str, Any] | None = None,
    priority_queue_artifact: Mapping[str, Any] | None = None,
    momentum_artifact: Mapping[str, Any] | None = None,
    tactical_confirmation_artifact: Mapping[str, Any] | None = None,
    tactical_boundaries_artifact: Mapping[str, Any] | None = None,
    corporate_intelligence_artifact: Mapping[str, Any] | None = None,
    technical_coverage_disposition_artifact: Mapping[str, Any] | None = None,
    operational_fundamental_integration_artifact: Mapping[str, Any] | None = None,
    liquidity_research_artifact: Mapping[str, Any] | None = None,
    entity_applicability_artifact: Mapping[str, Any] | None = None,
    official_liquidity_artifact: Mapping[str, Any] | None = None,
    financial_peer_materialization_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the market-wide integrated investment decision product artifact.

    ``technical_coverage_disposition_artifact`` is the exact-session evidence-currency source
    (strictly session/identity checked). ``priority_queue_artifact``, when supplied, must be the
    same session's ``daily_opportunity_decision_queue/v1``; it only populates the orthogonal
    OPPORTUNITY_PRIORITY inspection fields and can never change posture or decision identity.
    ``liquidity_research_artifact`` (same-session descriptive liquidity research) and
    ``entity_applicability_artifact`` (governed current-state entity applicability) feed only the
    per-ticker Current Research decision input.
    """
    fa_contract = (financial_analysis_artifact or {}).get("contract_version")
    if fa_contract is not None and fa_contract != FINANCIAL_ANALYSIS_COMPACT_CONTRACT:
        raise IntegratedDecisionProductError(
            "INCOMPATIBLE_FINANCIAL_ANALYSIS_CONTRACT:expected="
            f"{FINANCIAL_ANALYSIS_COMPACT_CONTRACT}:got={fa_contract}"
        )
    tac_records = technical_structure_artifact.get("records") or {}
    # A claimed identity alone does not qualify a new fixed T0 condition. Keep
    # other research axes visible while failing closed on this dependent use.
    import market_structure_breakout_product_projection as structural_projection
    structural_condition_identity = None
    if (technical_structure_artifact.get("contract_version") == structural_projection.CONTRACT_VERSION
            and technical_structure_artifact.get("session") == session):
        try:
            verified = structural_projection.content_identity(technical_structure_artifact)
            if (verified["artifact_identity"] == technical_structure_artifact.get("artifact_identity")
                    and verified["artifact_sha256"] == technical_structure_artifact.get("artifact_sha256")):
                structural_condition_identity = verified["artifact_identity"]
        except (TypeError, ValueError):
            pass
    fa_records = (financial_analysis_artifact or {}).get("records") or {}
    financial_peers = fa_product_projection.financial_peer_contexts(
        materialization=financial_peer_materialization_artifact, product=financial_analysis_artifact, session=session)
    operational_records: Mapping[str, Any] = {}
    if operational_fundamental_integration_artifact is not None:
        integration = operational_fundamental_integration_artifact
        authority = integration.get("authority_boundary") or {}
        if (integration.get("contract_version") != operational_fundamental.CONTRACT_VERSION
                or integration.get("session") != session
                or operational_fundamental.content_identity(integration).get("artifact_identity") != integration.get("artifact_identity")
                or (integration.get("source_artifact_identities") or {}).get("financial_analysis") != (financial_analysis_artifact or {}).get("artifact_identity")
                or not (integration.get("source_artifact_identities") or {}).get("fundamental_feature_store")
                or authority.get("current_research_only") is not True
                or authority.get("source_authority_tier") != "OPERATIONAL_PROVIDER_RESEARCH_ONLY"
                or authority.get("authoritative_financial_eligible") is not False
                or authority.get("pit_backtest_eligible") is not False
                or authority.get("valuation_authority") is not False
                or authority.get("execution_authority") is not False
                or authority.get("is_actionable") is not False):
            raise IntegratedDecisionProductError("OPERATIONAL_FUNDAMENTAL_INTEGRATION_CONTRACT_INVALID")
        operational_records = integration.get("records") or {}
        if set(operational_records) != set(integration.get("cohort_tickers") or []):
            raise IntegratedDecisionProductError("OPERATIONAL_FUNDAMENTAL_COHORT_MISMATCH")
    official_liquidity_records: Mapping[str, Any] = {}
    if official_liquidity_artifact is not None:
        import liquidity_authority_contract as liquidity_contract
        if (official_liquidity_artifact.get("contract_version") != OFFICIAL_LIQUIDITY_RESEARCH_CONTRACT
                or liquidity_contract.content_identity(official_liquidity_artifact, kind="official_exchange_liquidity_research").get("artifact_identity")
                != official_liquidity_artifact.get("artifact_identity")):
            raise IntegratedDecisionProductError("OFFICIAL_LIQUIDITY_RESEARCH_CONTRACT_INVALID")
        if official_liquidity_artifact.get("resolved_completed_session") != session:
            raise IntegratedDecisionProductError(
                "OFFICIAL_LIQUIDITY_RESEARCH_SESSION_MISMATCH:expected="
                f"{session}:observed={official_liquidity_artifact.get('resolved_completed_session')}"
            )
        boundary = official_liquidity_artifact.get("authority_boundary") or {}
        if any(boundary.get(key) != "BLOCKED" for key in ("EXECUTION_CAPACITY", "POSITION_SIZING", "PIT_BACKTEST")):
            raise IntegratedDecisionProductError("OFFICIAL_LIQUIDITY_RESEARCH_AUTHORITY_BOUNDARY_VIOLATED")
        official_liquidity_records = official_liquidity_artifact.get("records") or {}
    liquidity_records: Mapping[str, Any] = {}
    if liquidity_research_artifact is not None:
        if liquidity_research_artifact.get("contract_version") != LIQUIDITY_RESEARCH_CONTRACT:
            raise IntegratedDecisionProductError("LIQUIDITY_RESEARCH_CONTRACT_MISMATCH")
        if liquidity_research_artifact.get("resolved_completed_session") != session:
            raise IntegratedDecisionProductError(
                "LIQUIDITY_RESEARCH_SESSION_MISMATCH:expected="
                f"{session}:observed={liquidity_research_artifact.get('resolved_completed_session')}"
            )
        liquidity_records = liquidity_research_artifact.get("records") or {}
    applicability_records: Mapping[str, Any] = {}
    if entity_applicability_artifact is not None:
        import entity_classification_contract as entity_contract
        if (entity_applicability_artifact.get("contract_version") != entity_contract.CURRENT_RESEARCH_ENTITY_APPLICABILITY_CONTRACT
                or entity_contract.entity_applicability_content_identity(entity_applicability_artifact)
                != entity_applicability_artifact.get("artifact_identity")
                or entity_applicability_artifact.get("historical_pit_authority") != "NOT_ESTABLISHED"):
            raise IntegratedDecisionProductError("ENTITY_APPLICABILITY_CONTRACT_INVALID")
        applicability_records = entity_applicability_artifact.get("records") or {}
        if (operational_fundamental_integration_artifact is not None
                and (operational_fundamental_integration_artifact.get("source_artifact_identities") or {}).get("entity_applicability")
                not in (None, entity_applicability_artifact.get("artifact_identity"))):
            raise IntegratedDecisionProductError("OPERATIONAL_FUNDAMENTAL_ENTITY_APPLICABILITY_IDENTITY_MISMATCH")
    val_records = (current_valuation_artifact or {}).get("records") or {}
    rvol_records = (relative_volume_artifact or {}).get("records") or {}
    legacy_records = (legacy_decision_artifact or {}).get("records") or {}
    priority_records = (priority_queue_artifact or {}).get("records") or {}
    if priority_queue_artifact is not None and not isinstance(priority_records, Mapping):
        raise IntegratedDecisionProductError("PRIORITY_QUEUE_RECORDS_INVALID")
    if priority_queue_artifact is not None and priority_queue_artifact.get("research_session") != session:
        # Never resurrect a stale priority queue merely to make coverage nonzero.
        raise IntegratedDecisionProductError(
            f"PRIORITY_QUEUE_SESSION_MISMATCH:expected={session}:observed={priority_queue_artifact.get('research_session')}"
        )
    disposition_records = coherent_technical_coverage_disposition_records(
        technical_coverage_disposition_artifact, session=session,
    ) or {}
    momentum_records = (momentum_artifact or {}).get("records") or {}
    tactical_confirmation_records = (tactical_confirmation_artifact or {}).get("records") or {}
    tactical_boundaries_records = (tactical_boundaries_artifact or {}).get("records") or {}
    corporate_intelligence_records = (corporate_intelligence_artifact or {}).get("records") or {}

    # All tickers present in technical structure or financial analysis
    all_tickers = sorted(set(tac_records.keys()) | set(fa_records.keys()))
    if not all_tickers:
        raise IntegratedDecisionProductError("EMPTY_UNIVERSE_IN_INPUT_ARTIFACTS")
    if not set(operational_records) <= set(all_tickers):
        raise IntegratedDecisionProductError("OPERATIONAL_FUNDAMENTAL_TICKER_OUTSIDE_UNIVERSE")

    records: dict[str, Any] = {}
    posture_counts: dict[str, int] = {}
    fund_counts: dict[str, int] = {}
    tac_counts: dict[str, int] = {}
    tactical_confirmation_counts: dict[str, int] = {}
    financial_composite_counts: dict[str, int] = {}
    coherence_counts: dict[str, int] = {state: 0 for state in EVIDENCE_AXIS_COHERENCE_STATES}
    axis_available_counts: dict[str, int] = {
        "FUNDAMENTAL": 0, "VALUATION": 0, "TACTICAL_STRUCTURE": 0, "MOMENTUM": 0,
        "PARTICIPATION_CONFIRMATION": 0, "MARKET_SECTOR": 0, "OPPORTUNITY_PRIORITY": 0,
        "PORTFOLIO_FIT": 0, "CORPORATE_INTELLIGENCE": 0,
    }
    all_major_axes_available = 0

    trigger_avail = 0
    inval_avail = 0
    val_avail = 0
    fund_avail = 0
    fund_direction = 0
    tac_avail = 0
    part_avail = 0
    mkt_avail = 1 if market_sector_artifact else 0
    port_avail = 0
    port_not_provided = 0
    ci_evaluated = 0
    ci_any_event = 0
    ci_active_catalyst = 0
    ci_active_risk = 0
    ci_mixed_or_unresolved = 0
    ci_material = 0
    currency_counts: Counter[str] = Counter({"CURRENT_SESSION": 0, "LAST_TRADE_AS_OF": 0, "NO_CURRENT_EVIDENCE": 0})
    currency_gate_applied = 0
    priority_available = 0
    position_counts: Counter[str] = Counter()

    for ticker in all_tickers:
        tac_rec = tac_records.get(ticker)
        fa_rec = fa_records.get(ticker)
        val_rec = val_records.get(ticker)
        rvol_rec = rvol_records.get(ticker)
        leg_rec = legacy_records.get(ticker)

        dec = build_ticker_integrated_decision(
            ticker=ticker,
            as_of_session=session,
            tactical_record=tac_rec,
            financial_record=fa_rec,
            valuation_record=val_rec,
            relative_volume_record=rvol_rec,
            market_sector_record=market_sector_artifact,
            portfolio_record=portfolio_artifact,
            legacy_opportunity_record=leg_rec,
            priority_queue_record=priority_records.get(ticker),
            momentum_record=momentum_records.get(ticker),
            tactical_confirmation_record=tactical_confirmation_records.get(ticker),
            tactical_boundaries_record=tactical_boundaries_records.get(ticker),
            tactical_boundaries_identity=(tactical_boundaries_artifact or {}).get("artifact_identity"),
            structural_condition_source_identity=structural_condition_identity,
            corporate_intelligence_record=corporate_intelligence_records.get(ticker),
            producer_artifact_identities={
                "technical_structure": technical_structure_artifact.get("artifact_identity"),
                "financial_analysis": (financial_analysis_artifact or {}).get("artifact_identity"),
                "current_valuation": (current_valuation_artifact or {}).get("artifact_identity"),
                "relative_volume": (relative_volume_artifact or {}).get("artifact_identity"),
                "market_sector": (market_sector_artifact or {}).get("artifact_identity"),
                "priority_queue": (priority_queue_artifact or {}).get("artifact_identity"),
                "momentum": (momentum_artifact or {}).get("artifact_identity"),
                "tactical_confirmation": (tactical_confirmation_artifact or {}).get("artifact_identity"),
                "tactical_boundaries": (tactical_boundaries_artifact or {}).get("artifact_identity"),
                "corporate_intelligence": (corporate_intelligence_artifact or {}).get("artifact_identity"),
                **({"operational_fundamental_integration": operational_fundamental_integration_artifact.get("artifact_identity")}
                   if operational_fundamental_integration_artifact is not None else {}),
            },
            technical_coverage_disposition_record=disposition_records.get(ticker),
            operational_fundamental_context_record=operational_records.get(ticker),
            liquidity_research_record=liquidity_records.get(ticker),
            entity_applicability_record=applicability_records.get(ticker),
            official_liquidity_record=official_liquidity_records.get(ticker),
            financial_peer_context=financial_peers.get(ticker),
        )
        records[ticker] = dec
        currency_counts[evidence_currency_class(dec["evidence_currency"])] += 1
        if dec["evidence_currency_gate"].get("applied"):
            currency_gate_applied += 1
        if dec["opportunity_priority"]["status"] == "AVAILABLE":
            priority_available += 1
        position_counts[dec["position_context"]["position_state"]] += 1

        # Update counts
        p = dec["research_action_posture"]
        posture_counts[p] = posture_counts.get(p, 0) + 1

        f = dec["fundamental_state"]
        fund_counts[f] = fund_counts.get(f, 0) + 1

        t = dec["tactical_phase"]
        tac_counts[t] = tac_counts.get(t, 0) + 1

        c = (dec.get("tactical_confirmation_context") or {}).get("tactical_confirmation_state")
        tactical_confirmation_counts[c] = tactical_confirmation_counts.get(c, 0) + 1

        fc = (dec.get("financial_composite_context") or {}).get("financial_composite_state")
        financial_composite_counts[fc] = financial_composite_counts.get(fc, 0) + 1

        coherence = (dec.get("evidence_axis_coherence") or {}).get("state")
        coherence_counts[coherence] = coherence_counts.get(coherence, 0) + 1
        axes = dec.get("evidence_axes") or {}
        for axis_name in axis_available_counts:
            if _evidence_axis_available(axis_name, axes.get(axis_name)):
                axis_available_counts[axis_name] += 1
        if all(_evidence_axis_available(axis_name, axes.get(axis_name)) for axis_name in (
            "FUNDAMENTAL", "VALUATION", "TACTICAL_STRUCTURE", "MOMENTUM",
            "PARTICIPATION_CONFIRMATION", "MARKET_SECTOR", "OPPORTUNITY_PRIORITY",
        )):
            all_major_axes_available += 1

        if (dec.get("trigger") or {}).get("trigger_state") not in (None, "NOT_AVAILABLE"):
            trigger_avail += 1
        if (dec.get("invalidation") or {}).get("invalidation_level") is not None:
            inval_avail += 1
        if (dec.get("valuation_context_summary") or {}).get("status") == "AVAILABLE":
            val_avail += 1
        # Qualified fundamental evidence, apart from a sufficient current direction.
        if ((dec.get("fundamental_synthesis") or {}).get("evidence_availability") or {}).get("state") == fundamental_signals.AVAILABLE:
            fund_avail += 1
        if dec["fundamental_state"] != FUNDAMENTAL_INSUFFICIENT:
            fund_direction += 1
        if (tac_rec or {}).get("eligible"):
            tac_avail += 1
        if (dec.get("participation") or {}).get("status") == "AVAILABLE":
            part_avail += 1
        if (dec.get("portfolio_context") or {}).get("status") == "AVAILABLE":
            port_avail += 1
        else:
            port_not_provided += 1
        ci = dec.get("corporate_intelligence_context") or {}
        if ci.get("state") not in (None, "NOT_PROVIDED"):
            ci_evaluated += 1
        if ci.get("event_identities"):
            ci_any_event += 1
        if ci.get("active_catalyst_count"):
            ci_active_catalyst += 1
        if ci.get("active_risk_count"):
            ci_active_risk += 1
        if ci.get("mixed_or_unresolved_count"):
            ci_mixed_or_unresolved += 1
        if ci.get("material_event_count"):
            ci_material += 1

    coverage = {
        "universe_denominator": len(all_tickers),
        "integrated_context_available": len(records),
        "research_action_posture_distribution": dict(sorted(posture_counts.items())),
        "fundamental_state_distribution": dict(sorted(fund_counts.items())),
        "tactical_phase_distribution": dict(sorted(tac_counts.items())),
        "tactical_confirmation_state_distribution": dict(sorted((k, v) for k, v in tactical_confirmation_counts.items() if k is not None)),
        "financial_composite_state_distribution": dict(sorted((k, v) for k, v in financial_composite_counts.items() if k is not None)),
        "evidence_axis_coherence_distribution": dict(sorted((k, v) for k, v in coherence_counts.items() if k is not None)),
        "evidence_axis_available": dict(sorted(axis_available_counts.items())),
        "all_major_evidence_axes_available": all_major_axes_available,
        "momentum_context_available": sum(1 for rec in momentum_records.values() if (rec or {}).get("eligibility", {}).get("status") == "ELIGIBLE"),
        "trigger_available": trigger_avail,
        "invalidation_available": inval_avail,
        "valuation_context_available": val_avail,
        "fundamental_context_available": fund_avail,
        "fundamental_direction_sufficient": fund_direction,
        "tactical_context_available": tac_avail,
        "participation_context_available": part_avail,
        "market_sector_context_available": len(all_tickers) if mkt_avail else 0,
        "portfolio_context_available": port_avail,
        "portfolio_context_not_provided": port_not_provided,
        "corporate_intelligence_context_evaluated": ci_evaluated,
        "corporate_intelligence_any_event_count": ci_any_event,
        "corporate_intelligence_active_catalyst_count": ci_active_catalyst,
        "corporate_intelligence_active_risk_count": ci_active_risk,
        "corporate_intelligence_mixed_or_unresolved_count": ci_mixed_or_unresolved,
        "corporate_intelligence_material_event_count": ci_material,
        "evidence_currency_distribution": dict(sorted(currency_counts.items())),
        "evidence_currency_gate_applied_count": currency_gate_applied,
        "no_current_evidence_wait_count": sum(
            1 for rec in records.values()
            if rec["evidence_currency"] == EVIDENCE_CURRENCY_NO_CURRENT_EVIDENCE
            and rec["research_action_posture"] == POSTURE_WAIT_FOR_CONFIRMATION
        ),
        "opportunity_priority_available_count": priority_available,
        "position_context_distribution": dict(sorted(position_counts.items())),
    }
    if coverage["no_current_evidence_wait_count"]:
        raise IntegratedDecisionProductError("INVARIANT_VIOLATION:NO_CURRENT_EVIDENCE_WAIT_FOR_CONFIRMATION")
    if operational_fundamental_integration_artifact is not None:
        coverage["operational_fundamental_integration_cohort"] = len(operational_records)
        coverage["operational_fundamental_integration_usable"] = sum(
            (record.get("evidence_axes") or {}).get("FUNDAMENTAL", {}).get("method") == operational_fundamental.CONTRACT_VERSION
            for record in records.values()
        )
    coverage["fundamental_signal_consumption"] = fundamental_signals.coverage(
        [record.get("fundamental_synthesis") or {} for record in records.values()])
    coverage["fundamental_decision_policy_version"] = fundamental_signals.DECISION_POLICY_VERSION
    coverage["fundamental_evidence_availability"] = dict(sorted(Counter(
        str(record.get("fundamental_evidence_availability")) for record in records.values()).items()))
    coverage["fundamental_risk_level"] = dict(sorted(Counter(
        str((record.get("fundamental_risk_level") or {}).get("state")) for record in records.values()).items()))
    coverage["current_research_decision_input"] = decision_input.coverage(records)

    payload: dict[str, Any] = {
        "schema_version": "integrated_investment_decision_product/1.0.0",
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "requested_at": requested_at,
        "session": session,
        "coverage": coverage,
        "source_artifacts": {
            "technical_structure": technical_structure_artifact.get("artifact_identity"),
            "financial_analysis": (financial_analysis_artifact or {}).get("artifact_identity"),
            "current_valuation": (current_valuation_artifact or {}).get("artifact_identity"),
            "relative_volume": (relative_volume_artifact or {}).get("artifact_identity"),
            "market_sector": (market_sector_artifact or {}).get("artifact_identity"),
            "priority_queue": (priority_queue_artifact or {}).get("artifact_identity"),
            "momentum": (momentum_artifact or {}).get("artifact_identity"),
            "tactical_confirmation": (tactical_confirmation_artifact or {}).get("artifact_identity"),
            "tactical_boundaries": (tactical_boundaries_artifact or {}).get("artifact_identity"),
            "corporate_intelligence": (corporate_intelligence_artifact or {}).get("artifact_identity"),
            "technical_coverage_disposition": (
                (technical_coverage_disposition_artifact or {}).get("artifact_identity") if disposition_records else None
            ),
            **({"operational_fundamental_integration": operational_fundamental_integration_artifact.get("artifact_identity")}
               if operational_fundamental_integration_artifact is not None else {}),
            **({"liquidity_research": liquidity_research_artifact.get("artifact_identity")}
               if liquidity_research_artifact is not None else {}),
            **({"official_exchange_liquidity_research": official_liquidity_artifact.get("artifact_identity")}
               if official_liquidity_artifact is not None else {}),
            **({"entity_applicability": entity_applicability_artifact.get("artifact_identity")}
               if entity_applicability_artifact is not None else {}),
        },
        "decision_authority": {
            "primary_action_decision_field": "research_action_posture",
            "evidence_currency_field": "evidence_currency",
            "evidence_currency_source_contract": EVIDENCE_CURRENCY_SOURCE_CONTRACT,
            "opportunity_priority_role": "ORTHOGONAL_INSPECTION_AXIS_NEVER_ALTERS_POSTURE_OR_DECISION_IDENTITY",
            "current_research_decision_input_contract": decision_input.CONTRACT_VERSION,
            "evidence_class_role": "RESEARCH_COVERAGE_CLASS_NEVER_AN_ACTION_POSTURE",
        },
        "authority_boundary": {
            "is_actionable": False,
            "no_score_rank_target_or_probability": True,
            "research_support_not_execution_instruction": True,
            "unknown_is_local": True,
        },
        "records": records,
    }
    payload.update(content_identity(payload))
    return payload
