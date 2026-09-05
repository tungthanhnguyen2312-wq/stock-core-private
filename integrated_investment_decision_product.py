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
from typing import Any, Mapping, Sequence

import financial_analysis_product_projection as fa_product_projection

CONTRACT_VERSION = "integrated_investment_decision_product/v1"
MILESTONE = "INTEGRATED_INVESTMENT_DECISION_PRODUCT_V1"

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
FUNDAMENTAL_IMPROVING = "IMPROVING"
FUNDAMENTAL_STABLE = "STABLE"
FUNDAMENTAL_MIXED = "MIXED"
FUNDAMENTAL_DETERIORATING = "DETERIORATING"
FUNDAMENTAL_TURNAROUND = "TURNAROUND"
FUNDAMENTAL_INSUFFICIENT = "INSUFFICIENT"

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


class IntegratedDecisionProductError(ValueError):
    """Fail-closed error for integrated investment decision product."""


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
    """Feedback-ready deterministic identity for one ticker decision record."""
    fields = {
        "ticker": record.get("ticker"),
        "as_of_session": record.get("as_of_session"),
        "policy_version": "v1",
        "research_action_posture": record.get("research_action_posture"),
        "fundamental_state": record.get("fundamental_state"),
        "tactical_phase": record.get("tactical_phase"),
        "trigger_state": (record.get("trigger") or {}).get("trigger_state"),
        "trigger_type": (record.get("trigger") or {}).get("trigger_type"),
        "invalidation_level": (record.get("invalidation") or {}).get("invalidation_level"),
        "source_identities": record.get("source_identities"),
    }
    return f"decision:{record.get('ticker')}:{_sha256(fields)[:16]}"


# ── Fundamental Direction Evaluator ───────────────────────────────────────────

def evaluate_fundamental_direction(fa_context: Mapping[str, Any] | None) -> tuple[str, list[str], list[str]]:
    """Determine compact fundamental state and specific support/counter points."""
    if not isinstance(fa_context, Mapping) or fa_context.get("status") in (None, "ABSENT", "NOT_SUPPLIED"):
        return FUNDAMENTAL_INSUFFICIENT, [], ["FUNDAMENTAL_CONTEXT_ABSENT"]

    supports: list[str] = []
    counters: list[str] = []

    prof = fa_context.get("profitability_state")
    turnaround = fa_context.get("earnings_turnaround_state")
    margin = fa_context.get("margin_state")
    growth = fa_context.get("growth_state")
    cash = fa_context.get("cash_conversion_state")
    balance = fa_context.get("balance_sheet_state")
    leverage = fa_context.get("leverage_state")
    wc_traj = fa_context.get("working_capital_trajectory_state")
    gm_traj = fa_context.get("gross_margin_trajectory_state")

    # Specialist states
    bank_asset = fa_context.get("bank_asset_quality_state")
    bank_fund = fa_context.get("bank_funding_state")
    sec_brokerage = fa_context.get("brokerage_mix_trajectory_state")

    if prof == "PROFITABLE":
        supports.append("PROFITABLE_CORE_OPERATIONS")
    elif prof == "LOSS_MAKING":
        counters.append("OBSERVED_LOSS_MAKING")
    elif prof == "TURNAROUND_CONTEXT" or turnaround == "TURNAROUND":
        supports.append("EARNINGS_TURNAROUND_DETECTED")

    if margin == "MARGIN_EXPANDING" or gm_traj == "IMPROVING":
        supports.append("MARGIN_EXPANSION")
    elif margin == "MARGIN_COMPRESSING" or gm_traj == "WORSENING":
        counters.append("MARGIN_COMPRESSION")

    if growth in ("ACCELERATING", "EXPANDING"):
        supports.append("REVENUE_GROWTH_EXPANDING")
    elif growth == "CONTRACTING":
        counters.append("REVENUE_CONTRACTION")

    if cash == "HEALTHY":
        supports.append("POSITIVE_CASH_CONVERSION_PROXY")
    elif cash == "WEAK":
        counters.append("WEAK_CASH_CONVERSION_PROXY")

    if balance == "STRENGTHENING":
        supports.append("BALANCE_SHEET_STRENGTHENING")
    elif balance == "DETERIORATING":
        counters.append("BALANCE_SHEET_DETERIORATING")

    if leverage == "SAFE":
        supports.append("CONSERVATIVE_LEVERAGE")
    elif leverage == "STRESSED":
        counters.append("ELEVATED_LEVERAGE_STRESS")

    if wc_traj == "IMPROVING":
        supports.append("WORKING_CAPITAL_IMPROVING")
    elif wc_traj == "WORSENING":
        counters.append("WORKING_CAPITAL_WORSENING")

    if bank_asset in ("STRONG", "IMPROVING"):
        supports.append(f"BANK_ASSET_QUALITY_{bank_asset}")
    elif bank_asset in ("WEAK", "DETERIORATING"):
        counters.append(f"BANK_ASSET_QUALITY_{bank_asset}")

    if sec_brokerage == "BROKERAGE_MIX_RISING":
        supports.append("SECURITIES_BROKERAGE_MIX_EXPANDING")

    # Synthesize fundamental_state
    if prof == "TURNAROUND_CONTEXT" or turnaround == "TURNAROUND":
        state = FUNDAMENTAL_TURNAROUND
    elif len(counters) > len(supports) and (prof == "LOSS_MAKING" or growth == "CONTRACTING" or balance == "DETERIORATING"):
        state = FUNDAMENTAL_DETERIORATING
    elif len(supports) > 0 and len(counters) == 0:
        state = FUNDAMENTAL_IMPROVING if (growth in ("ACCELERATING", "EXPANDING") or margin == "MARGIN_EXPANDING" or wc_traj == "IMPROVING") else FUNDAMENTAL_STABLE
    elif len(supports) > 0 and len(counters) > 0:
        state = FUNDAMENTAL_MIXED
    elif prof == "PROFITABLE":
        state = FUNDAMENTAL_STABLE
    else:
        state = FUNDAMENTAL_INSUFFICIENT

    return state, supports, counters


# ── Financial Composite Context Evaluator (section 14) ────────────────────────

def evaluate_financial_composite_context(
    *, fund_state: str, fund_supports: Sequence[str], fund_counters: Sequence[str],
    val_summary: Mapping[str, Any] | None, val_supports: Sequence[str], val_counters: Sequence[str],
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
    TURNAROUND_EVIDENCE or INSUFFICIENT_EVIDENCE by itself.
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
            "valuation_peer_relative_state": val_summary.get("peer_relative_state"),
            "valuation_own_history_state": val_summary.get("own_history_state"),
        },
        "methodology": "join_fundamental_state_and_valuation_context_no_vote_count/v1",
        "is_actionable": False,
    }


# ── Evidence-axis inventory and qualitative coherence ─────────────────────────

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
) -> dict[str, dict[str, Any]]:
    """Expose standing decision evidence as distinct, source-preserving axes.

    These are deliberately descriptive joins over already-governed producer outputs.  The action
    policy remains upstream and consumes none of this structure.
    """
    identities = source_artifact_identities or {}
    financial_status = financial.get("status") or (
        "AVAILABLE" if fund_state != FUNDAMENTAL_INSUFFICIENT else "UNAVAILABLE"
    )
    valuation_status = val_summary.get("status") or valuation.get("status") or "UNAVAILABLE"
    technical_fitness = "AVAILABLE" if tactical.get("eligible") else "INSUFFICIENT_EVIDENCE"
    momentum_fitness = (momentum.get("eligibility") or {}).get("status") or momentum.get("status") or "UNAVAILABLE"
    confirmation_state = confirmation.get("tactical_confirmation_state") or "INSUFFICIENT_EVIDENCE"
    participation_status = participation_summary.get("status") or "UNAVAILABLE"
    priority = priority_record or {}
    priority_fitness = priority.get("data_quality_status") or ("AVAILABLE" if priority_record else "UNAVAILABLE")
    sector_context = (market_summary.get("sector_leadership") if market_context_provided else None)
    sector_fitness = "AVAILABLE" if market_context_provided and sector_context not in (None, "IN_LINE") else (
        "PARTIAL" if market_context_provided else "UNAVAILABLE"
    )

    return {
        "FUNDAMENTAL": _axis(
            state=fund_state, fitness=financial_status, supporting=fund_supports, contradicting=fund_counters,
            blockers=["FUNDAMENTAL_CONTEXT_ABSENT"] if fund_state == FUNDAMENTAL_INSUFFICIENT else [],
            method="financial_analysis_product_integration/v1",
            lineage={"source_artifact_identity": identities.get("financial_analysis") or financial.get("source_context_identity") or financial.get("artifact_identity")},
        ),
        "VALUATION": _axis(
            state=valuation_status, fitness=valuation_status, supporting=val_supports, contradicting=val_counters,
            blockers=val_uncertainties,
            method="current_research_valuation_context/v1",
            lineage={"source_artifact_identity": identities.get("current_valuation") or valuation.get("artifact_identity")},
            context={
                "peer_relative_state": val_summary.get("peer_relative_state"),
                "own_history_state": val_summary.get("own_history_state"),
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
            blockers=[] if market_context_provided else ["MARKET_SECTOR_CONTEXT_NOT_PROVIDED"],
            method="current_market_sector_leadership_context/v1",
            lineage={"source_artifact_identity": identities.get("market_sector")},
            context={"market_regime": market_summary.get("market_regime"), "sector_leadership": sector_context},
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
    if axis_name == "FUNDAMENTAL" and axis.get("state") == FUNDAMENTAL_INSUFFICIENT:
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
    elif trig_type == "RETEST_BROKEN_PIVOT" or (ms == "UPTREND" and brk_v3 == "TESTING_PIVOT"):
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
    pb_item = methods.get("P/B") or {}
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

    peer_rel = (val_rec.get("peer_relative_context") or {})
    rel_state = peer_rel.get("relative_research_state")
    peer_pctl = peer_rel.get("peer_relative_percentile") or pe_item.get("peer_percentile") or pb_item.get("peer_percentile") or ps_item.get("peer_percentile")

    # Own-history context from FA V2
    hist_ctx = fa_context.get("history_context") or {}

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

    # Own history interpretation. `financial_analysis_engine_v2._history_entry()` (the sole
    # producer of this shape, passed through verbatim by financial_analysis_product_projection)
    # names this field "percentile", never "percentile_in_history" -- the prior key name never
    # matched a single real record, so this axis silently never activated. Confirmed by reading
    # both producers; fixed to read the field that is actually emitted.
    own_history_interpretation = "UNAVAILABLE"
    if hist_ctx:
        pctls = [v.get("percentile") for v in hist_ctx.values() if isinstance(v, Mapping) and isinstance(v.get("percentile"), (int, float))]
        if pctls:
            avg_pctl = sum(pctls) / len(pctls)
            if avg_pctl <= 0.33:
                own_history_interpretation = "LOW_VS_OWN_HISTORY"
                supports.append("RATIOS_LOW_VS_OWN_HISTORICAL_RANGE")
            elif avg_pctl >= 0.67:
                own_history_interpretation = "HIGH_VS_OWN_HISTORY"
                counters.append("RATIOS_ELEVATED_VS_OWN_HISTORICAL_RANGE")
            else:
                own_history_interpretation = "MID_VS_OWN_HISTORY"

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

    has_usable_metrics = (
        val_rec.get("research_usable") is True
        or val_rec.get("has_usable_method") is True
        or (val_rec.get("usable_relative_method_count") or 0) > 0
        or any(m.get("status") in ("RESEARCH_USABLE", "READY") for m in methods.values() if isinstance(m, Mapping))
        or pe_val is not None
        or pb_val is not None
        or ps_val is not None
    )

    summary = {
        "status": "AVAILABLE" if (peer_interpretation != "NOT_APPLICABLE" or has_usable_metrics) else "UNAVAILABLE",
        "peer_relative_state": peer_interpretation,
        "own_history_state": own_history_interpretation,
        "peer_percentile": peer_pctl,
        "share_basis": share_basis,
        "pe_multiple": pe_val,
        "pb_multiple": pb_val,
        "ps_multiple": ps_val,
        "ev_ebitda_multiple": ev_ebitda_val,
        "earnings_state": val_rec.get("earnings_state"),
        "limitations": uncertainties,
        "valuation_method_reconciliation": val_rec.get("valuation_method_reconciliation") or {},
    }
    return summary, supports, counters, uncertainties


# ── Participation Evaluator ───────────────────────────────────────────────────

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
) -> tuple[str, str, str]:
    """Pure deterministic research policy mapping explicit evidence into research_action_posture.

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
        why = f"{ticker}: Insufficient technical price series and fundamental analysis data to establish a current research stance."
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
        why = f"{ticker}: Valid structural breakout trigger fired at pivot level with non-conflicting fundamentals and supportive participation{lead_note}; actionable initiation setup."
        return POSTURE_INITIATE_ON_BREAKOUT, why, EFFECT_DOES_NOT_BLOCK

    # 5. RETEST OF BROKEN PIVOT -> ACCUMULATE_ON_RETEST
    if (tactical_phase == TACTICAL_RETEST_AFTER_BREAKOUT or brk_v3 == "TESTING_PIVOT" or trig_type == "RETEST_BROKEN_PIVOT") and ms in ("UPTREND", "EARLY_BULLISH_REVERSAL"):
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
    producer_artifact_identities: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble one complete, self-contained integrated investment decision record."""
    tactical = tactical_record or {}
    financial = financial_record or {}
    valuation = valuation_record or {}
    rvol = relative_volume_record or {}
    market = market_sector_record or {}
    momentum = momentum_record or {}
    confirmation = tactical_confirmation_record or {}

    # 1. Fundamental
    fund_state, fund_supp, fund_count = evaluate_fundamental_direction(financial)

    # 2. Tactical
    tac_phase, tac_supp, tac_count = evaluate_tactical_phase(tactical)

    # 3. Valuation
    val_summary, val_supp, val_count, val_uncert = evaluate_valuation_context(valuation, financial)

    # 3b. Financial composite context (section 14): a pure join of 1 and 3 above, computed
    # from their own already-produced outputs. Additive only -- feeds nothing below.
    financial_composite_context = evaluate_financial_composite_context(
        fund_state=fund_state, fund_supports=fund_supp, fund_counters=fund_count,
        val_summary=val_summary, val_supports=val_supp, val_counters=val_count,
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
    mkt_summary = {
        "market_regime": (market.get("market") or {}).get("current_breadth_state") or "NEUTRAL_MIXED",
        "sector_leadership": ticker_sector_ctx.get("leadership_state") or "IN_LINE",
        "authority_tier": "CURRENT_RESEARCH_DESCRIPTIVE",
    }
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
            "is_held": False,
            "policy_note": "No explicit portfolio supplied; security attractiveness is independently evaluated.",
        }

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
    )
    priority_posture = _priority_posture_reconciliation(
        priority_queue_record, posture=posture, tactical=tactical, why_now=why_now,
    )

    # 8. Trigger & Invalidation
    trigger = {
        "trigger_type": tactical.get("trigger_type", "NO_TRIGGER"),
        "trigger_level": tactical.get("trigger_level"),
        "trigger_state": tactical.get("trigger_state", "NOT_AVAILABLE"),
        "distance_to_trigger_pct": tactical.get("distance_to_trigger_pct"),
        "warning": "TRIGGER_IS_RESEARCH_MEASUREMENT_NOT_EXECUTION_AUTHORITY",
    }
    invalidation = {
        "invalidation_level": tactical.get("invalidation_level"),
        "invalidation_method": tactical.get("invalidation_method") or "CONFIRMED_SWING_LEVEL_OR_SUPPORT_FALLBACK",
        "distance_to_invalidation_pct": tactical.get("distance_to_invalidation_pct"),
        "warning": "STRUCTURAL_INVALIDATION_LEVEL_NOT_A_STOP_LOSS",
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
    )
    evidence_axis_coherence = evaluate_evidence_axis_coherence(evidence_axes)

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
        "fundamental_state": fund_state,
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
        },
        "authority_boundary": {
            "is_actionable": False,
            "no_score_rank_target_or_probability": True,
            "research_support_not_execution_instruction": True,
            "security_attractiveness_separate_from_portfolio_fit": True,
            "unknown_is_local_does_not_force_global_wait": True,
        },
    }
    record["decision_identity"] = decision_identity(record)
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
) -> dict[str, Any]:
    """Build the market-wide integrated investment decision product artifact."""
    fa_contract = (financial_analysis_artifact or {}).get("contract_version")
    if fa_contract is not None and fa_contract != FINANCIAL_ANALYSIS_COMPACT_CONTRACT:
        raise IntegratedDecisionProductError(
            "INCOMPATIBLE_FINANCIAL_ANALYSIS_CONTRACT:expected="
            f"{FINANCIAL_ANALYSIS_COMPACT_CONTRACT}:got={fa_contract}"
        )
    tac_records = technical_structure_artifact.get("records") or {}
    fa_records = (financial_analysis_artifact or {}).get("records") or {}
    val_records = (current_valuation_artifact or {}).get("records") or {}
    rvol_records = (relative_volume_artifact or {}).get("records") or {}
    legacy_records = (legacy_decision_artifact or {}).get("records") or {}
    priority_records = (priority_queue_artifact or {}).get("records") or {}
    if priority_queue_artifact is not None and not isinstance(priority_records, Mapping):
        raise IntegratedDecisionProductError("PRIORITY_QUEUE_RECORDS_INVALID")
    momentum_records = (momentum_artifact or {}).get("records") or {}
    tactical_confirmation_records = (tactical_confirmation_artifact or {}).get("records") or {}

    # All tickers present in technical structure or financial analysis
    all_tickers = sorted(set(tac_records.keys()) | set(fa_records.keys()))
    if not all_tickers:
        raise IntegratedDecisionProductError("EMPTY_UNIVERSE_IN_INPUT_ARTIFACTS")

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
        "PORTFOLIO_FIT": 0,
    }
    all_major_axes_available = 0

    trigger_avail = 0
    inval_avail = 0
    val_avail = 0
    fund_avail = 0
    tac_avail = 0
    part_avail = 0
    mkt_avail = 1 if market_sector_artifact else 0
    port_avail = 0
    port_not_provided = 0

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
            producer_artifact_identities={
                "technical_structure": technical_structure_artifact.get("artifact_identity"),
                "financial_analysis": (financial_analysis_artifact or {}).get("artifact_identity"),
                "current_valuation": (current_valuation_artifact or {}).get("artifact_identity"),
                "relative_volume": (relative_volume_artifact or {}).get("artifact_identity"),
                "market_sector": (market_sector_artifact or {}).get("artifact_identity"),
                "priority_queue": (priority_queue_artifact or {}).get("artifact_identity"),
                "momentum": (momentum_artifact or {}).get("artifact_identity"),
                "tactical_confirmation": (tactical_confirmation_artifact or {}).get("artifact_identity"),
            },
        )
        records[ticker] = dec

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
        if dec["fundamental_state"] != FUNDAMENTAL_INSUFFICIENT:
            fund_avail += 1
        if (tac_rec or {}).get("eligible"):
            tac_avail += 1
        if (dec.get("participation") or {}).get("status") == "AVAILABLE":
            part_avail += 1
        if (dec.get("portfolio_context") or {}).get("status") == "AVAILABLE":
            port_avail += 1
        else:
            port_not_provided += 1

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
        "tactical_context_available": tac_avail,
        "participation_context_available": part_avail,
        "market_sector_context_available": len(all_tickers) if mkt_avail else 0,
        "portfolio_context_available": port_avail,
        "portfolio_context_not_provided": port_not_provided,
    }

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
