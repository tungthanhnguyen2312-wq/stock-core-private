"""ASYMMETRIC_DISLOCATION_RESEARCH_V1.

Deterministic, read-only research product joining already-retained current-research
evidence -- fundamental/financial quality, valuation/peer context, tactical/market-
structure state, Corporate Intelligence catalyst/risk, and structural invalidation --
into one asymmetric-dislocation research classification per ticker.

This module computes NO new financial ratio, technical indicator, catalyst
classification, or entity-family determination. Every axis below is a pure,
descriptive join over one already-governed `integrated_investment_decision_product/v1`
per-ticker record (itself already the join point for Fundamental, Valuation,
Tactical Structure, Momentum, Participation/Confirmation, Market/Sector, Opportunity
Priority, Portfolio Fit, and Corporate Intelligence evidence). It never mutates that
record, never re-derives its inputs, and never changes `research_action_posture`.

Standalone / read-only over retained completed-session products. Does not modify
canonical Daily Producer orchestration, Daily Brief generation, AI delivery, the
Integrated Investment Decision production path, or Portfolio V2 decision semantics.
No probability, expected return, or target price is ever emitted; scenario asymmetry
defaults to `ASYMMETRY_NOT_QUANTIFIED` unless an already-retained scenario boundary is
explicitly supplied.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from field_temporal_contract import stable_id

CONTRACT_VERSION = "asymmetric_dislocation_research/v1"
MILESTONE = "ASYMMETRIC_DISLOCATION_RESEARCH_V1"
ARTIFACT_TYPE = "asymmetric_dislocation_research"

# ── Primary classification contract ──────────────────────────────────────────
QUALITY_DISLOCATION = "QUALITY_DISLOCATION"
CYCLICAL_RECOVERY_FORMING = "CYCLICAL_RECOVERY_FORMING"
TURNAROUND_EVIDENCE_FORMING = "TURNAROUND_EVIDENCE_FORMING"
DISTRESS_SPECULATIVE = "DISTRESS_SPECULATIVE"
VALUE_TRAP_RISK = "VALUE_TRAP_RISK"
NO_QUALIFIED_DISLOCATION = "NO_QUALIFIED_DISLOCATION"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

PRIMARY_STATES = (
    QUALITY_DISLOCATION, CYCLICAL_RECOVERY_FORMING, TURNAROUND_EVIDENCE_FORMING,
    DISTRESS_SPECULATIVE, VALUE_TRAP_RISK, NO_QUALIFIED_DISLOCATION, INSUFFICIENT_EVIDENCE,
)

# Only these primary states describe a genuine asymmetric-dislocation research
# candidate. VALUE_TRAP_RISK, NO_QUALIFIED_DISLOCATION, and INSUFFICIENT_EVIDENCE are
# retained per-ticker evidence but are never ranked as candidates. Tier order is the
# documented, explicit ranking rule (see `RANKING_ORDERING_SEMANTICS`): descending
# survivability conviction, not a weighted score.
CANDIDATE_STATE_PRIORITY: dict[str, int] = {
    QUALITY_DISLOCATION: 0,
    TURNAROUND_EVIDENCE_FORMING: 1,
    CYCLICAL_RECOVERY_FORMING: 2,
    DISTRESS_SPECULATIVE: 3,
}
VALUATION_DISLOCATION_ORDER: dict[str, int] = {"CHEAP": 0, "MID": 1, "UNAVAILABLE": 2, "EXPENSIVE": 3}

RANKING_ORDERING_SEMANTICS = (
    "Deterministic lexicographic ordering among ELIGIBLE_RESEARCH_CANDIDATE records only, "
    "using already-qualified component states -- never an opaque weighted score: "
    "(1) primary_research_state tier -- QUALITY_DISLOCATION > TURNAROUND_EVIDENCE_FORMING > "
    "CYCLICAL_RECOVERY_FORMING > DISTRESS_SPECULATIVE, reflecting descending survivability "
    "conviction (viable/improving economics with confirmed price dislocation ranks above an "
    "explicit turnaround signal, which ranks above a forming cyclical recovery, which ranks "
    "above a speculative distress candidate with weak or unknown survivability); "
    "(2) valuation_dislocation_context.state -- CHEAP > MID > UNAVAILABLE > EXPENSIVE; "
    "(3) count of reason_codes, descending (more corroborating reused evidence ranks higher; "
    "this counts already-emitted reason codes, it does not weight or score them); "
    "(4) ticker, ascending, as the final deterministic tie-break."
)

FUNDAMENTAL_STATES_KNOWN = frozenset({"IMPROVING", "STABLE", "MIXED", "DETERIORATING", "TURNAROUND"})

# Tactical/market-structure vocabularies reused verbatim from
# market_structure_breakout_product_projection/v1 (tactical_phase) and its
# market_structure_state context field -- no new technical state is introduced.
_DISTRESS_TACTICAL_PHASES = frozenset({"BREAKDOWN", "DISTRIBUTION_RISK"})
_DISTRESS_MARKET_STRUCTURE = frozenset({"DOWNTREND", "EARLY_BEARISH_REVERSAL"})
_RECOVERY_TACTICAL_PHASES = frozenset({"EARLY_REVERSAL", "BASE_BUILDING", "RETEST_AFTER_BREAKOUT"})
_RECOVERY_MARKET_STRUCTURE = frozenset({"EARLY_BULLISH_REVERSAL"})

_SPECIALIST_ENTITY_FAMILIES = frozenset({"bank", "securities", "insurance", "finance_company"})

ASYMMETRY_NOT_QUANTIFIED = "ASYMMETRY_NOT_QUANTIFIED"


class AsymmetricDislocationResearchError(ValueError):
    """A deliberately concise operational refusal."""


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: value for key, value in artifact.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


# ── Evidence axes: pure descriptive joins over the retained Integrated Decision
#    record. None of these functions compute a new ratio, indicator, or catalyst
#    classification -- they only read and interpret already-governed fields. ─────

def evaluate_economic_survivability(integrated_record: Mapping[str, Any]) -> dict[str, Any]:
    """Balance-sheet/leverage/cash-flow/profitability survivability, reused verbatim
    from `fundamental_state` (financial_analysis_product_integration/v1). Severe or
    continuing deterioration is surfaced explicitly so it can never be hidden by a
    cheap valuation reading elsewhere in the record."""
    fund_state = integrated_record.get("fundamental_state") or "INSUFFICIENT"
    fund_axis = ((integrated_record.get("evidence_axes") or {}).get("FUNDAMENTAL") or {})
    composite = integrated_record.get("financial_composite_context") or {}
    return {
        "state": fund_state,
        "fitness": fund_axis.get("fitness", "UNAVAILABLE"),
        "financial_composite_state": composite.get("financial_composite_state"),
        "severe_deterioration_evidenced": fund_state == "DETERIORATING",
        "supporting_reason_codes": list(fund_axis.get("supporting_reason_codes") or []),
        "contradicting_reason_codes": list(fund_axis.get("contradicting_reason_codes") or []),
        "method": "financial_analysis_product_integration/v1 (reused verbatim via fundamental_state)",
    }


def evaluate_valuation_dislocation(integrated_record: Mapping[str, Any]) -> dict[str, Any]:
    """Cheap-vs-expensive read, reused verbatim from `valuation_context_summary`
    (current_research_valuation_context/v1: peer-relative + own-history percentile
    context). Never fabricates an intrinsic value or target; only classifies the
    already-computed peer/own-history state."""
    val = integrated_record.get("valuation_context_summary") or {}
    peer = val.get("peer_relative_state") or "NOT_APPLICABLE"
    own_hist = val.get("own_history_state") or "UNAVAILABLE"
    status = val.get("status") or "UNAVAILABLE"

    if peer == "CHEAP_VS_PEERS" or own_hist == "LOW_VS_OWN_HISTORY":
        state = "CHEAP"
    elif peer == "EXPENSIVE_VS_PEERS" or own_hist == "HIGH_VS_OWN_HISTORY":
        state = "EXPENSIVE"
    elif peer == "MID_RANGE_VS_PEERS" or own_hist == "MID_VS_OWN_HISTORY":
        state = "MID"
    else:
        state = "UNAVAILABLE"

    return {
        "state": state,
        "status": status,
        "peer_relative_state": peer,
        "own_history_state": own_hist,
        "pe_multiple": val.get("pe_multiple"),
        "pb_multiple": val.get("pb_multiple"),
        "ps_multiple": val.get("ps_multiple"),
        "ev_ebitda_multiple": val.get("ev_ebitda_multiple"),
        "limitations": list(val.get("limitations") or []),
        "no_fabricated_intrinsic_value_or_target": True,
        "method": "current_research_valuation_context/v1 (reused verbatim)",
    }


def evaluate_market_dislocation(integrated_record: Mapping[str, Any]) -> dict[str, Any]:
    """Drawdown/trend/base/reversal/oversold context, reused verbatim from
    `tactical_phase`, `market_structure_state`, `breakout_state_v3`
    (market_structure_breakout_product_projection/v1) and RSI zone
    (tactical_momentum_context/v1). Oversold alone is deliberately never treated as
    a genuine reversal/basing signal -- `oversold_only` and `reversal_or_basing_evidenced`
    are mutually informative but distinct flags."""
    tactical_phase = integrated_record.get("tactical_phase") or "INSUFFICIENT"
    market_structure = integrated_record.get("market_structure_state")
    breakout = integrated_record.get("breakout_state_v3")
    rsi = ((integrated_record.get("momentum_context") or {}).get("rsi") or {})
    rsi_zone = rsi.get("zone")
    tac_axis = ((integrated_record.get("evidence_axes") or {}).get("TACTICAL_STRUCTURE") or {})

    oversold = rsi_zone == "OVERSOLD"
    distribution_or_breakdown = (
        tactical_phase in _DISTRESS_TACTICAL_PHASES or market_structure in _DISTRESS_MARKET_STRUCTURE
    )
    reversal_or_basing = (
        tactical_phase in _RECOVERY_TACTICAL_PHASES or market_structure in _RECOVERY_MARKET_STRUCTURE
    )
    # A confirmed dislocation requires actual price weakness evidence, not merely a
    # momentum reading -- oversold alone never satisfies this.
    genuine_price_dislocation = distribution_or_breakdown
    oversold_only = oversold and not reversal_or_basing and not distribution_or_breakdown

    return {
        "tactical_phase": tactical_phase,
        "market_structure_state": market_structure,
        "breakout_state_v3": breakout,
        "rsi_zone": rsi_zone,
        "oversold": oversold,
        "oversold_only": oversold_only,
        "distribution_or_breakdown_evidenced": distribution_or_breakdown,
        "reversal_or_basing_evidenced": reversal_or_basing,
        "genuine_price_dislocation": genuine_price_dislocation,
        "fitness": tac_axis.get("fitness", "INSUFFICIENT_EVIDENCE"),
        "supporting_reason_codes": list(tac_axis.get("supporting_reason_codes") or []),
        "contradicting_reason_codes": list(tac_axis.get("contradicting_reason_codes") or []),
        "method": "market_structure_breakout_product_projection/v1 + tactical_momentum_context/v1 (reused verbatim)",
    }


def evaluate_corporate_intelligence(integrated_record: Mapping[str, Any]) -> dict[str, Any]:
    """Thin passthrough over `corporate_intelligence_context`
    (current_corporate_intelligence_axis/v1). This module performs no catalyst/risk/
    materiality classification of its own."""
    corp = integrated_record.get("corporate_intelligence_context") or {}
    return {
        "state": corp.get("state", "NOT_PROVIDED"),
        "fitness": corp.get("fitness", "NOT_PROVIDED"),
        "active_catalyst_count": corp.get("active_catalyst_count", 0),
        "active_risk_count": corp.get("active_risk_count", 0),
        "material_event_count": corp.get("material_event_count", 0),
        "evidence_session": corp.get("evidence_session"),
        "evidence_session_stale": corp.get("evidence_session_stale"),
        "limitations": list(corp.get("limitations") or []),
        "method": "current_corporate_intelligence_axis/v1 (reused verbatim)",
    }


def evaluate_recovery_evidence(
    survivability: Mapping[str, Any], market: Mapping[str, Any], corporate: Mapping[str, Any],
) -> dict[str, Any]:
    """Recovery evidence is explicit evidence only: an explicit financial turnaround
    read (already produced upstream from earnings/margin/cash-flow trajectory), an
    improving tactical structure, or a qualified active corporate catalyst. Absence
    is recorded explicitly rather than inferred from silence."""
    fundamental_inflection = survivability["state"] == "TURNAROUND"
    technical_improving = bool(market["reversal_or_basing_evidenced"])
    qualified_catalyst = corporate["state"] == "CATALYST_PRESENT"
    flags = []
    if fundamental_inflection:
        flags.append("FUNDAMENTAL_INFLECTION_EVIDENCED")
    if technical_improving:
        flags.append("IMPROVING_TACTICAL_STRUCTURE_EVIDENCED")
    if qualified_catalyst:
        flags.append("QUALIFIED_CORPORATE_CATALYST_EVIDENCED")
    return {
        "state": "RECOVERY_EVIDENCE_PRESENT" if flags else "RECOVERY_EVIDENCE_ABSENT",
        "fundamental_inflection_evidenced": fundamental_inflection,
        "technical_improving_evidenced": technical_improving,
        "qualified_catalyst_evidenced": qualified_catalyst,
        "evidence_flags": flags,
        "explicit_absence_not_inferred": not flags,
    }


def evaluate_risk_invalidation(
    integrated_record: Mapping[str, Any], survivability: Mapping[str, Any], corporate: Mapping[str, Any],
) -> dict[str, Any]:
    """Deterministic invalidation/risk boundary, reused verbatim from `invalidation`
    (tactical_confirmation_invalidation_boundaries/v1, joined into the Integrated
    Decision record) plus the already-computed Corporate Intelligence risk read. Cost
    basis never enters this evaluation."""
    inval = integrated_record.get("invalidation") or {}
    condition = inval.get("condition") or {}
    boundary_status = condition.get("source_boundary_status", "UNAVAILABLE")
    material_risk_active = corporate["state"] in {"RISK_PRESENT", "MIXED_EVIDENCE"} or bool(corporate["active_risk_count"])
    return {
        "state": boundary_status,
        "invalidation_level": inval.get("invalidation_level"),
        "invalidation_method": inval.get("invalidation_method"),
        "distance_to_invalidation_pct": inval.get("distance_to_invalidation_pct"),
        "narrative_reason": condition.get("narrative_reason"),
        "severe_fundamental_deterioration_evidenced": survivability["severe_deterioration_evidenced"],
        "material_corporate_risk_active": material_risk_active,
        "cost_basis_irrelevant_to_classification": True,
        "method": "tactical_confirmation_invalidation_boundaries/v1 (reused verbatim)",
    }


def evaluate_scenario_asymmetry(scenario_record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Scenario-asymmetry context. The new calibration pipeline
    (empirical_setup_outcome_calibration/v1) has every real cohort at
    INSUFFICIENT_SAMPLE, so no probability or expected return is emitted here. When an
    already-retained deterministic scenario boundary (current_evidence_bound_scenario/v1)
    is supplied for this ticker/session, its existing qualitative Bear/Base/Bull labels
    are passed through verbatim; otherwise this axis is explicitly
    `ASYMMETRY_NOT_QUANTIFIED`, never a manufactured target."""
    if not scenario_record:
        return {
            "state": ASYMMETRY_NOT_QUANTIFIED,
            "reason": "NO_RETAINED_SCENARIO_BOUNDARY_SUPPLIED_FOR_THIS_TICKER_SESSION",
            "bear_case": None, "base_case": None, "bull_case": None,
            "no_fabricated_target_or_probability": True,
        }
    return {
        "state": "SCENARIO_BOUNDARY_AVAILABLE",
        "bear_case": scenario_record.get("bear_case"),
        "base_case": scenario_record.get("base_case"),
        "bull_case": scenario_record.get("bull_case"),
        "no_fabricated_target_or_probability": True,
        "method": "current_evidence_bound_scenario/v1 (reused verbatim, when supplied)",
    }


def evaluate_sector_applicability(entity_family: str | None = None) -> dict[str, Any]:
    """Descriptive sector/model-applicability note only. This module performs no
    entity-family-specific financial computation of its own; every fundamental,
    valuation, and financial-composite input it reads is already family-aware
    (financial_analysis_engine_v2.py / current_research_valuation_context.py already
    special-case bank/securities/insurance/finance_company families before this
    module ever sees `fundamental_state` or `valuation_context_summary`)."""
    family = (entity_family or "unknown").lower()
    specialist = family in _SPECIALIST_ENTITY_FAMILIES
    note = (
        "Specialist financial family: industrial-company debt/working-capital formulas are "
        "not applicable and are not applied. This module performs no new sector-specific "
        "financial computation; it fully inherits whatever family-aware gating "
        "financial_analysis_engine_v2 and current_research_valuation_context already applied "
        "upstream to fundamental_state and valuation_context_summary."
        if specialist else
        "Generic/industrial or unclassified entity family; no new sector-specific financial "
        "computation is performed by this module."
    )
    return {"entity_family": family, "specialist_financial_family": specialist, "note": note}


# ── Classification ────────────────────────────────────────────────────────────

def _no_countervailing_evidence(market: Mapping[str, Any], risk: Mapping[str, Any]) -> bool:
    return (
        not market["distribution_or_breakdown_evidenced"]
        and not market["reversal_or_basing_evidenced"]
        and not risk["material_corporate_risk_active"]
    )


def classify_dislocation(
    *, survivability: Mapping[str, Any], valuation: Mapping[str, Any], market: Mapping[str, Any],
    recovery: Mapping[str, Any], corporate: Mapping[str, Any], risk: Mapping[str, Any],
) -> tuple[str, list[str], list[str]]:
    """Pure deterministic classification over the six evidence axes above. Returns
    (primary_state, reason_codes, missing_evidence_flags). Priority-ordered rules;
    first qualifying rule wins. No weighted score, vote count, or probability is
    computed anywhere in this function."""
    reason_codes: list[str] = []
    missing_evidence: list[str] = []
    if valuation["status"] == "UNAVAILABLE":
        missing_evidence.append("VALUATION_EVIDENCE_UNAVAILABLE")
    fund_state = survivability["state"]
    if fund_state not in FUNDAMENTAL_STATES_KNOWN:
        missing_evidence.append("FUNDAMENTAL_EVIDENCE_UNAVAILABLE")

    # TURNAROUND and DETERIORATING are themselves strong, explicit, self-sufficient
    # survivability reads (an earnings/margin/cash-flow inflection or an active
    # deterioration signal says something real on its own); STABLE/IMPROVING/MIXED are
    # comparatively uninformative about dislocation without a valuation or market
    # signal to pair with, and INSUFFICIENT means survivability itself is unknown.
    fund_is_self_sufficient = fund_state in {"TURNAROUND", "DETERIORATING"}
    critical_axis_missing = (not fund_is_self_sufficient) and (
        valuation["status"] == "UNAVAILABLE" or fund_state not in FUNDAMENTAL_STATES_KNOWN
    )
    if critical_axis_missing and _no_countervailing_evidence(market, risk):
        return INSUFFICIENT_EVIDENCE, ["INSUFFICIENT_EVIDENCE_ACROSS_REUSED_AXES"], missing_evidence

    def _finish(state: str, codes: list[str]) -> tuple[str, list[str], list[str]]:
        if corporate["state"] == "CATALYST_PRESENT" and state in {NO_QUALIFIED_DISLOCATION, VALUE_TRAP_RISK, INSUFFICIENT_EVIDENCE}:
            codes = codes + ["CATALYST_PRESENT_BUT_NO_ECONOMIC_SUPPORT_EVIDENCED"]
        return state, codes, missing_evidence

    if fund_state == "DETERIORATING":
        if valuation["state"] == "CHEAP":
            return _finish(VALUE_TRAP_RISK, reason_codes + ["CHEAP_VALUATION_WITH_DETERIORATING_FUNDAMENTALS"])
        if market["distribution_or_breakdown_evidenced"]:
            codes = reason_codes + ["PRICE_BREAKDOWN_WITH_WEAK_SURVIVABILITY"]
            if risk["material_corporate_risk_active"]:
                codes.append("MATERIAL_CORPORATE_RISK_ACTIVE")
            return _finish(DISTRESS_SPECULATIVE, codes)
        return _finish(NO_QUALIFIED_DISLOCATION, reason_codes + ["DETERIORATING_FUNDAMENTALS_NO_QUALIFIED_CHEAPNESS_OR_BREAKDOWN"])

    if fund_state == "TURNAROUND":
        return _finish(TURNAROUND_EVIDENCE_FORMING, reason_codes + ["EXPLICIT_FINANCIAL_TURNAROUND_EVIDENCE"])

    if fund_state in {"STABLE", "IMPROVING"}:
        if valuation["state"] == "CHEAP" and market["genuine_price_dislocation"]:
            return _finish(QUALITY_DISLOCATION, reason_codes + ["CHEAP_VALUATION_WITH_VIABLE_ECONOMICS_AND_PRICE_DISLOCATION"])
        if market["reversal_or_basing_evidenced"] and recovery["state"] == "RECOVERY_EVIDENCE_PRESENT":
            return _finish(CYCLICAL_RECOVERY_FORMING, reason_codes + ["IMPROVING_TACTICAL_STRUCTURE_WITH_NON_DETERIORATING_FUNDAMENTALS"])
        if market["oversold_only"]:
            reason_codes.append("OVERSOLD_ALONE_NOT_SUFFICIENT")
        return _finish(NO_QUALIFIED_DISLOCATION, reason_codes)

    if fund_state == "MIXED":
        if valuation["state"] == "CHEAP" and market["genuine_price_dislocation"] and recovery["state"] == "RECOVERY_EVIDENCE_PRESENT":
            return _finish(QUALITY_DISLOCATION, reason_codes + ["CHEAP_VALUATION_WITH_MIXED_FUNDAMENTALS_CORROBORATED_BY_RECOVERY_EVIDENCE"])
        if market["reversal_or_basing_evidenced"] and recovery["state"] == "RECOVERY_EVIDENCE_PRESENT":
            return _finish(CYCLICAL_RECOVERY_FORMING, reason_codes + ["IMPROVING_TACTICAL_STRUCTURE_WITH_MIXED_FUNDAMENTALS"])
        if market["oversold_only"]:
            reason_codes.append("OVERSOLD_ALONE_NOT_SUFFICIENT")
        return _finish(NO_QUALIFIED_DISLOCATION, reason_codes)

    # fund_state == "INSUFFICIENT": reached only when a countervailing market/risk
    # signal exists (the top gate already returned INSUFFICIENT_EVIDENCE otherwise).
    if market["distribution_or_breakdown_evidenced"] and risk["material_corporate_risk_active"]:
        return _finish(DISTRESS_SPECULATIVE, reason_codes + ["PRICE_BREAKDOWN_WITH_UNKNOWN_SURVIVABILITY_AND_ACTIVE_MATERIAL_RISK"])
    if market["oversold_only"]:
        reason_codes.append("OVERSOLD_ALONE_NOT_SUFFICIENT")
    return _finish(NO_QUALIFIED_DISLOCATION, reason_codes)


# ── Per-ticker and market-wide artifact assembly ──────────────────────────────

def build_ticker_record(
    *, ticker: str, session: str, integrated_record: Mapping[str, Any],
    scenario_record: Mapping[str, Any] | None = None, entity_family: str | None = None,
) -> dict[str, Any]:
    survivability = evaluate_economic_survivability(integrated_record)
    valuation = evaluate_valuation_dislocation(integrated_record)
    market = evaluate_market_dislocation(integrated_record)
    corporate = evaluate_corporate_intelligence(integrated_record)
    recovery = evaluate_recovery_evidence(survivability, market, corporate)
    risk = evaluate_risk_invalidation(integrated_record, survivability, corporate)
    scenario = evaluate_scenario_asymmetry(scenario_record)
    sector = evaluate_sector_applicability(entity_family)

    primary_state, reason_codes, missing_evidence = classify_dislocation(
        survivability=survivability, valuation=valuation, market=market,
        recovery=recovery, corporate=corporate, risk=risk,
    )
    eligibility = "ELIGIBLE_RESEARCH_CANDIDATE" if primary_state in CANDIDATE_STATE_PRIORITY else "NOT_ELIGIBLE"

    record: dict[str, Any] = {
        "ticker": ticker,
        "research_session": session,
        "source_decision_identity": integrated_record.get("decision_identity"),
        "primary_research_state": primary_state,
        "reason_codes": reason_codes,
        "missing_evidence_flags": missing_evidence,
        "research_eligibility": eligibility,
        "economic_survivability_context": survivability,
        "valuation_dislocation_context": valuation,
        "market_dislocation_context": market,
        "recovery_catalyst_context": recovery,
        "corporate_intelligence_context": corporate,
        "risk_invalidation_context": risk,
        "scenario_asymmetry_context": scenario,
        "sector_model_applicability": sector,
        "authority_boundary": {
            "is_actionable": False,
            "no_score_rank_target_or_probability": True,
            "does_not_change_research_action_posture": True,
            "cost_basis_irrelevant_to_classification": True,
            "oversold_alone_never_sufficient": True,
        },
    }
    identity = content_identity(record)
    record["content_identity"] = identity["artifact_identity"]
    record["content_sha256"] = identity["artifact_sha256"]
    return record


def _candidate_sort_key(record: Mapping[str, Any]) -> tuple[int, int, int, str]:
    tier = CANDIDATE_STATE_PRIORITY.get(record["primary_research_state"], 99)
    val_order = VALUATION_DISLOCATION_ORDER.get(record["valuation_dislocation_context"]["state"], 9)
    neg_support = -len(record.get("reason_codes") or [])
    return (tier, val_order, neg_support, str(record["ticker"]))


def _rank_candidates(records: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    eligible = [r for r in records.values() if r["research_eligibility"] == "ELIGIBLE_RESEARCH_CANDIDATE"]
    ordered = sorted(eligible, key=_candidate_sort_key)
    return [
        {
            "ticker": r["ticker"],
            "primary_research_state": r["primary_research_state"],
            "valuation_dislocation_state": r["valuation_dislocation_context"]["state"],
            "reason_codes": r["reason_codes"],
        }
        for r in ordered
    ]


def _coverage(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    state_counts = Counter(r["primary_research_state"] for r in records.values())
    reason_counts = Counter(code for r in records.values() for code in r["reason_codes"])
    missing_counts = Counter(code for r in records.values() for code in r["missing_evidence_flags"])
    evidence_qualified = sum(
        1 for r in records.values()
        if r["economic_survivability_context"]["state"] in FUNDAMENTAL_STATES_KNOWN
        or r["valuation_dislocation_context"]["status"] == "AVAILABLE"
    )
    return {
        "universe_denominator": len(records),
        "state_distribution": dict(sorted(state_counts.items())),
        "evidence_qualified_count": evidence_qualified,
        "missing_evidence_ticker_count": sum(1 for r in records.values() if r["missing_evidence_flags"]),
        "candidate_count": sum(1 for r in records.values() if r["research_eligibility"] == "ELIGIBLE_RESEARCH_CANDIDATE"),
        "reason_code_distribution": dict(sorted(reason_counts.items())),
        "missing_evidence_flag_distribution": dict(sorted(missing_counts.items())),
    }


def build_artifact(
    *, session: str, integrated_product: Mapping[str, Any],
    scenario_records: Mapping[str, Mapping[str, Any]] | None = None,
    entity_families: Mapping[str, str] | None = None,
    requested_at: str | None = None, top_candidate_limit: int = 50,
) -> dict[str, Any]:
    """Build the market-wide asymmetric-dislocation research artifact for one
    already-completed, retained current-research session. `integrated_product` must be
    the retained `integrated_investment_decision_product/v1` artifact for that exact
    session (never a different session's artifact) -- every per-ticker record's
    `research_session` is stamped from the `session` parameter, and no field from any
    other session is ever consulted."""
    if not session:
        raise AsymmetricDislocationResearchError("RESEARCH_SESSION_REQUIRED")
    if integrated_product.get("session") not in (None, session):
        raise AsymmetricDislocationResearchError(
            f"SESSION_MISMATCH: requested {session!r}, integrated_product is for {integrated_product.get('session')!r}"
        )
    scenario_records = scenario_records or {}
    entity_families = entity_families or {}

    records: dict[str, Any] = {}
    for ticker, integrated_record in sorted((integrated_product.get("records") or {}).items()):
        records[ticker] = build_ticker_record(
            ticker=ticker, session=session, integrated_record=integrated_record,
            scenario_record=scenario_records.get(ticker), entity_family=entity_families.get(ticker),
        )

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "milestone": MILESTONE,
        "research_mode": "RESEARCH_ONLY_STANDALONE_NOT_ACTIONABLE",
        "session": session,
        "requested_at": requested_at,
        "primary_states": list(PRIMARY_STATES),
        "candidate_eligible_states": list(CANDIDATE_STATE_PRIORITY.keys()),
        "ranking_ordering_semantics": RANKING_ORDERING_SEMANTICS,
        "source_integrated_decision_identity": integrated_product.get("artifact_identity"),
        "records": records,
        "coverage": _coverage(records),
        "top_candidates": _rank_candidates(records)[:top_candidate_limit],
        "authority_boundary": {
            "is_actionable": False,
            "research_only": True,
            "does_not_activate_in_canonical_daily": True,
            "does_not_change_research_action_posture": True,
            "no_probability_or_target_fabrication": True,
            "oversold_alone_never_sufficient": True,
        },
    }
    artifact.update(content_identity(artifact))
    return artifact
