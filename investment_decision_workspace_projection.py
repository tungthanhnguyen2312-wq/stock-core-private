"""investment_decision_workspace_projection/v1: compact per-ticker workspace card.

A pure join over already-computed opportunity_context/v1 and security_decision_context/v1
records (plus optional sector-leadership, explicit-portfolio, and prospective-lifecycle
context). No new fundamental/technical/valuation/liquidity/portfolio computation happens
here -- this module only reshapes and joins retained evidence for one product surface: a
Dashboard opportunity list plus a seven-section per-ticker decision card. It does not
require requalification of any raw upstream artifact.

Enforces defensively, at display time, the invariant that market cap and enterprise value
are size context and never a relative-value signal: ATTRACTIVE_RELATIVE_RESEARCH /
EXPENSIVE_RELATIVE_RESEARCH is only ever surfaced when at least one true relative-valuation
method (P/E, P/S, P/B, EV/Sales, EV/EBITDA) actually supports it. This mirrors the source-level
fix in current_research_valuation_context.py::attach_peer_relative -- kept here too because a
workspace built from an opportunity_context artifact materialized before that fix (or from any
future regression) must still never display a market-cap-only mislabel.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping

from current_research_valuation_context import RELATIVE_METHODS
import current_research_official_universe_scope as current_research_official_universe_scope_module

CONTRACT_VERSION = "investment_decision_workspace_projection/v1"
MILESTONE = "INVESTMENT_DECISION_WORKSPACE_V1"
SCHEMA_VERSION = "1.0.0"
_IDENTITY_EXCLUDED = {"artifact_sha256", "artifact_identity", "requested_at"}

DEEP_EVIDENCE_NOT_MATERIALIZED = "DEEP_EVIDENCE_ARTIFACT_NOT_MATERIALIZED_LOCALLY"
RELATIVE_VALUATION_LABELS = frozenset({"ATTRACTIVE_RELATIVE_RESEARCH", "EXPENSIVE_RELATIVE_RESEARCH"})
WORKSPACE_AXES = (
    "fundamental", "valuation", "tactical", "market_sector", "catalyst", "downside_invalidation", "liquidity",
)
# Section 6 / DECISIONS.md invariant: portfolio fit never mutates or re-labels security research
# stance. This vocabulary is derived only from already-computed portfolio_research_context fields
# (position lookup, existing user_limit_breaches, existing sector_concentration weights) -- no new
# correlation, volatility, or optimization math is computed anywhere in this module.
PORTFOLIO_FIT_STATUSES = (
    "NOT_EVALUATED", "NO_CONCENTRATION_FLAGGED", "ALREADY_HELD",
    "ADDS_SECTOR_CONCENTRATION", "EXCEEDS_USER_POLICY_LIMIT",
)


class InvestmentDecisionWorkspaceError(ValueError):
    """A required input contract or invariant of this projection is violated."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in _IDENTITY_EXCLUDED}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _valuation_view(opportunity_record: Mapping[str, Any]) -> dict[str, Any]:
    """Method/basis-qualified valuation view with the market-cap-is-not-cheapness guard applied."""
    valuation = opportunity_record.get("valuation") or {}
    absolute = valuation.get("absolute_research_context") or {}
    peer = valuation.get("peer_relative_context") or {}
    methods = peer.get("methods") or {}
    usable_count = absolute.get("usable_relative_method_count") or 0
    raw_state = peer.get("relative_research_state")
    supporting = [
        {
            "method": method_id,
            "percentile": detail.get("percentile"),
            "peer_count": detail.get("peer_count"),
            "peer_median": detail.get("peer_median"),
            "premium_or_discount_to_peer_median": detail.get("premium_or_discount_to_peer_median"),
            "basis": detail.get("basis"),
            "methodology": detail.get("methodology"),
        }
        for method_id, detail in methods.items()
        if method_id in RELATIVE_METHODS and isinstance(detail, Mapping) and detail.get("status") == "READY_RESEARCH_ONLY"
    ]
    guard_applied = raw_state in RELATIVE_VALUATION_LABELS and not supporting
    display_state = raw_state
    if guard_applied:
        display_state = "ABSOLUTE_RESEARCH_ONLY" if usable_count else "UNAVAILABLE"
    market_cap_detail = methods.get("market_cap") if isinstance(methods, Mapping) else None
    applicable_methods = valuation.get("applicable_methods") or {}
    # WORKSPACE_DIAGNOSTIC_TRANSPARENCY_AND_DAILY_DASHBOARD_BINDING_V1: pass through the
    # already-computed per-method AVAILABLE_QUALIFIED/AVAILABLE_REFERENCE_ONLY/NOT_AVAILABLE
    # diagnostic and the display-oriented summary unchanged -- never recomputed here, never
    # replacing `relative_research_state`/`supporting_methods` above (which stay byte-identical
    # to their pre-existing behavior; see current_research_valuation_context.method_availability_state
    # / _valuation_display_summary for the source of truth).
    method_diagnostics = {
        method_id: {
            "status": detail.get("status"), "value": detail.get("value"),
            "availability_state": detail.get("availability_state"),
            "blocker_reason_codes": detail.get("blocker_reason_codes"),
            "period_basis": detail.get("period_basis"), "share_basis": detail.get("share_basis"),
            "peer_relative": detail.get("peer_relative"),
        }
        for method_id, detail in applicable_methods.items()
        if isinstance(detail, Mapping)
    }
    return {
        "relative_research_state": display_state,
        "raw_upstream_relative_research_state": raw_state,
        "market_cap_semantic_guard_applied": guard_applied,
        "usable_relative_method_count": usable_count,
        "supporting_methods": supporting,
        "valuation_summary": valuation.get("valuation_summary"),
        "method_diagnostics": method_diagnostics,
        "market_cap_size_context": {
            "percentile": (market_cap_detail or {}).get("percentile"),
            "peer_count": (market_cap_detail or {}).get("peer_count"),
            "status": (market_cap_detail or {}).get("status"),
        } if isinstance(market_cap_detail, Mapping) else None,
        "share_basis": valuation.get("share_basis"),
        "entity_class": valuation.get("entity_class"),
        "earnings_state": valuation.get("earnings_state"),
        "readiness": valuation.get("readiness"),
        "freshness_status": (valuation.get("freshness") or {}).get("freshness_status"),
        "source_session": (valuation.get("freshness") or {}).get("source_session"),
    }


def _catalyst_view(opportunity_record: Mapping[str, Any]) -> dict[str, Any]:
    catalyst = opportunity_record.get("catalyst") or {}
    return {
        "status": catalyst.get("status"),
        "qualified_current_catalysts": list(catalyst.get("qualified_current_catalysts") or []),
        "pending_watch_items": list(catalyst.get("pending_watch_items") or []),
        # WORKSPACE_DIAGNOSTIC_TRANSPARENCY_AND_DAILY_DASHBOARD_BINDING_V1: already computed on
        # the opportunity record (`opportunity_context.py::_catalyst_axis`) but previously
        # dropped here -- a genuinely observed adverse/negative event existed upstream while the
        # card rendered no catalyst signal at all. Passthrough only, additive.
        "adverse_events": list(catalyst.get("adverse_events") or []),
        "event_classifications": list(catalyst.get("event_classifications") or []),
        "event_count": catalyst.get("event_count"),
        "freshness_status": (catalyst.get("freshness") or {}).get("freshness_status"),
        "source_session": (catalyst.get("freshness") or {}).get("source_session"),
    }


def _liquidity_view(opportunity_record: Mapping[str, Any]) -> dict[str, Any]:
    liquidity = opportunity_record.get("liquidity") or {}
    return {
        "readiness": liquidity.get("readiness"),
        "descriptive_research_state": liquidity.get("descriptive_research_state"),
        "exact_execution_capacity_status": liquidity.get("exact_execution_capacity_status"),
        # WORKSPACE_DIAGNOSTIC_TRANSPARENCY_AND_DAILY_DASHBOARD_BINDING_V1: already present on
        # the opportunity record (`opportunity_context.py::_liquidity_row`) but previously
        # dropped here even though it survived that far. Passthrough only, additive.
        "current_session_volume": liquidity.get("current_session_volume"),
        "research_usable": liquidity.get("research_usable"),
        "authority_boundary": liquidity.get("authority_boundary"),
        "freshness_status": (liquidity.get("freshness") or {}).get("freshness_status"),
        "source_session": (liquidity.get("freshness") or {}).get("source_session"),
    }


def _fundamental_view(opportunity_record: Mapping[str, Any]) -> dict[str, Any]:
    """Additive diagnostic lens over the fundamental axis -- never recomputed.

    `financial_health`/`current_features` (with each feature's own `blocker_reason_codes`)/
    `peer_relative`/`entity_type`/`entity_applicability`/`warnings_blockers` are already
    retained on `opportunity_context.py::_fundamental_axis`'s output but were previously
    dropped at this join -- a ticker genuinely blocked for a specific documented reason
    rendered identically to a ticker with no fundamental data at all.
    """
    fundamental = opportunity_record.get("fundamental") or {}
    return {
        "state": fundamental.get("state"), "trajectory": fundamental.get("trajectory"),
        "readiness": fundamental.get("readiness"), "research_fitness": fundamental.get("research_fitness"),
        "financial_health": fundamental.get("financial_health"),
        "current_features": fundamental.get("current_features") or {},
        "peer_relative": fundamental.get("peer_relative") or {},
        "entity_type": fundamental.get("entity_type"), "entity_applicability": fundamental.get("entity_applicability"),
        "warnings_blockers": list(fundamental.get("warnings_blockers") or []),
        "freshness_status": (fundamental.get("freshness") or {}).get("freshness_status"),
        "source_period": (fundamental.get("freshness") or {}).get("source_period"),
    }


def _sector_diagnostic_view(leadership_records: Mapping[str, Any], ticker: str) -> dict[str, Any]:
    """Additive diagnostic lens over the full leadership record already looked up for
    `_sector_label` -- previously discarded immediately after extracting the bare group
    string. `current_market_sector_leadership_context.py` computes real percentile/peer-
    median/observation-count/breadth-support detail per ticker that never reached the card.
    """
    record = leadership_records.get(ticker) or {}
    market_relative = record.get("market_relative_momentum") or {}
    sector_relative = record.get("sector_relative_momentum") or {}
    return {
        "breadth_support_state": record.get("breadth_support_state"),
        "coverage_limitations": list(record.get("coverage_limitations") or []),
        "market_relative_momentum": {
            "status": market_relative.get("status"),
            "momentum_percentile_descriptive": market_relative.get("momentum_percentile_descriptive"),
            "peer_median_momentum_20d": market_relative.get("peer_median_momentum_20d"),
            "valid_observation_count": market_relative.get("valid_observation_count"),
        } if market_relative else None,
        "sector_relative_momentum": {
            "status": sector_relative.get("status"),
            "momentum_percentile_descriptive": sector_relative.get("momentum_percentile_descriptive"),
            "peer_median_momentum_20d": sector_relative.get("peer_median_momentum_20d"),
            "valid_observation_count": sector_relative.get("valid_observation_count"),
        } if sector_relative else None,
        "group_coverage_ratio": (record.get("sector_leadership_context") or {}).get("group_coverage_ratio"),
    }


def _trigger_reference_view(opportunity_record: Mapping[str, Any]) -> dict[str, Any]:
    """Diagnostic-only reference trigger/invalidation level -- never a confirmed entry.

    Preserves the four concepts the milestone requires kept distinct: whether a reference
    price level exists at all, whether a condition is attached to it, whether that
    condition has actually fired, and that none of this carries entry/execution authority.
    """
    tactical = opportunity_record.get("tactical") or {}
    trigger = tactical.get("reference_trigger_context") or {}
    return {
        "trigger_level_exists": bool(trigger.get("trigger_level_exists")),
        "trigger_level": trigger.get("trigger_level"),
        "trigger_type": trigger.get("trigger_type"),
        "trigger_condition_attached": bool(trigger.get("trigger_condition_attached")),
        "trigger_condition_satisfied": bool(trigger.get("trigger_condition_satisfied")),
        "trigger_state": trigger.get("trigger_state"),
        "invalidation_level": trigger.get("invalidation_level"),
        "invalidation_method": trigger.get("invalidation_method"),
        "entry_authority": False,
        "status": trigger.get("status", "NOT_AVAILABLE"),
        "display_note": "Reference level only -- not a confirmed entry (điểm mua) unless trigger_condition_satisfied is true.",
    }


def _sector_label(leadership_records: Mapping[str, Any], ticker: str) -> str:
    context = leadership_records.get(ticker) or {}
    group = (context.get("sector_leadership_context") or {}).get("group_key")
    return group if isinstance(group, str) and group else "UNKNOWN"


def _prospective_view(prospective_lifecycle: Mapping[str, Any] | None, ticker: str) -> dict[str, Any]:
    records = (prospective_lifecycle or {}).get("records") if isinstance(prospective_lifecycle, Mapping) else None
    if not isinstance(records, Mapping):
        return {
            "status": "CASE_DATA_UNAVAILABLE", "thesis_lifecycle_state": None,
            "reason": "NO_PROSPECTIVE_LIFECYCLE_ARTIFACT_SUPPLIED",
            "t0_session": None, "t0_stance": None, "t0_tactical_setup": None,
            "confirmation": None, "invalidation": None,
            "forward_outcome_status": "PENDING_NOT_ENOUGH_FUTURE_SESSIONS",
            "t_plus_5": None, "t_plus_20": None, "t_plus_60": None, "mfe": None, "mae": None,
            "benchmark_relative_result": None,
        }
    record = records.get(ticker)
    if record is None:
        return {
            "status": "NO_RETAINED_CURRENT_CASES", "thesis_lifecycle_state": None,
            "reason": "TICKER_NOT_IN_PROSPECTIVE_COHORT",
            "t0_session": None, "t0_stance": None, "t0_tactical_setup": None,
            "confirmation": None, "invalidation": None,
            "forward_outcome_status": "PENDING_NOT_ENOUGH_FUTURE_SESSIONS",
            "t_plus_5": None, "t_plus_20": None, "t_plus_60": None, "mfe": None, "mae": None,
            "benchmark_relative_result": None,
        }
    lifecycle_state = record.get("thesis_lifecycle_state")
    transitions = record.get("component_transitions") or []
    status = "PENDING_NOT_ENOUGH_FUTURE_SESSIONS" if lifecycle_state == "INITIAL_OBSERVATION" else "ACTIVE_CASES_AVAILABLE"
    t0_recommendation = record.get("previous_recommendation") or record.get("current_recommendation") or {}
    t0_tactical = record.get("previous_tactical_state") or record.get("current_tactical_state") or {}
    return {
        "status": status,
        "thesis_lifecycle_state": lifecycle_state,
        "reason": None,
        "material_change": record.get("material_change"),
        "material_change_reasons": list(record.get("material_change_reasons") or []),
        "t0_session": record.get("previous_session") or record.get("current_session"),
        "t0_stance": t0_recommendation.get("recommendation_label"),
        "t0_tactical_setup": t0_tactical.get("entry_state"),
        "confirmation": "GAINED" if any(item.get("transition") == "CONFIRMATION_GAINED" for item in transitions) else None,
        "invalidation": "ACTIVATED" if any(item.get("transition") == "INVALIDATION_ACTIVATED" for item in transitions) else None,
        # Forward-looking outcome metrics (T+5/T+20/T+60, MFE, MAE, benchmark-relative result) have
        # no producing module anywhere in this codebase (repo-wide search: zero MFE/MAE hits). This
        # is an honest PENDING, never a fabricated zero or a silently omitted field.
        "forward_outcome_status": "PENDING_NOT_ENOUGH_FUTURE_SESSIONS",
        "t_plus_5": None, "t_plus_20": None, "t_plus_60": None, "mfe": None, "mae": None,
        "benchmark_relative_result": None,
    }


def _portfolio_view(portfolio_research: Mapping[str, Any] | None, ticker: str, sector: str) -> dict[str, Any]:
    """Portfolio fit for one ticker. Never reads or mutates security_decision_context's stance."""
    if not isinstance(portfolio_research, Mapping) or not portfolio_research.get("portfolio_id"):
        return {"evaluated": False, "status": "NOT_EVALUATED", "reason": "NO_PORTFOLIO_RESEARCH_CONTEXT_SUPPLIED"}
    positions = {
        position.get("ticker"): position
        for position in portfolio_research.get("normalized_positions") or []
        if isinstance(position, Mapping)
    }
    holding = positions.get(ticker)
    limit_breaches = [
        breach for breach in portfolio_research.get("user_limit_breaches") or []
        if isinstance(breach, Mapping) and (breach.get("ticker") == ticker or breach.get("sector") == sector)
    ]
    sector_concentration = dict(portfolio_research.get("sector_concentration") or {})
    sector_weight = sector_concentration.get(sector)
    adds_sector_concentration = (not holding) and isinstance(sector_weight, (int, float)) and sector_weight > 0
    if limit_breaches:
        status = "EXCEEDS_USER_POLICY_LIMIT"
    elif holding:
        status = "ALREADY_HELD"
    elif adds_sector_concentration:
        status = "ADDS_SECTOR_CONCENTRATION"
    else:
        status = "NO_CONCENTRATION_FLAGGED"
    if status not in PORTFOLIO_FIT_STATUSES:
        raise InvestmentDecisionWorkspaceError(f"PORTFOLIO_FIT_STATUS_NOT_IN_GOVERNED_VOCABULARY:{status}")
    return {
        "evaluated": True,
        "status": status,
        "portfolio_id": portfolio_research.get("portfolio_id"),
        "as_of_session": portfolio_research.get("as_of_session"),
        "holding_status": "HELD" if holding else "NOT_HELD",
        "weight": (holding or {}).get("weight"),
        "sector": (holding or {}).get("sector") or sector,
        "existing_sector_concentration_weight": sector_weight,
        "sector_concentration": sector_concentration,
        "tactical_concentration": dict(portfolio_research.get("tactical_concentration") or {}),
        "selected_joint_risk_horizon": portfolio_research.get("selected_joint_risk_horizon"),
        "joint_risk_status": portfolio_research.get("joint_risk_status"),
        "pairwise_correlation_status": portfolio_research.get("pairwise_correlation_status"),
        "user_limit_breaches": limit_breaches,
        "liquidity_research_context": (holding or {}).get("liquidity_research_context"),
        "exact_execution_capacity_status": (holding or {}).get("exact_execution_capacity_status"),
        "volatility": (holding or {}).get("volatility"),
        "cash_weight": portfolio_research.get("cash_weight"),
        "calculation_lineage": portfolio_research.get("calculation_lineage"),
        "warnings": list(portfolio_research.get("warnings") or []),
    }


def _lineage_view(opportunity_record: Mapping[str, Any]) -> dict[str, Any]:
    authority = opportunity_record.get("data_authority") or {}
    return {
        "per_axis_source_session": dict(authority.get("per_axis_session") or {}),
        "per_axis_freshness": dict(authority.get("per_axis_freshness") or {}),
        "per_axis_proxy_or_qualified_state": dict(authority.get("proxy_or_qualified_state") or {}),
        "blockers": list(authority.get("blockers") or []),
        "deep_evidence_availability": DEEP_EVIDENCE_NOT_MATERIALIZED,
    }


def build_ticker_card(
    *, ticker: str, opportunity_record: Mapping[str, Any], decision_record: Mapping[str, Any],
    sector: str, portfolio_research: Mapping[str, Any] | None, prospective_record: Mapping[str, Any],
    leadership_records: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose one seven-section decision-workspace card for a single ticker."""
    fundamental = opportunity_record.get("fundamental") or {}
    tactical = opportunity_record.get("tactical") or {}
    market = opportunity_record.get("market_sector") or {}
    usable_axes = set(opportunity_record.get("usable_major_axes") or [])
    valuation_view = _valuation_view(opportunity_record)
    catalyst_view = _catalyst_view(opportunity_record)
    fundamental_view = _fundamental_view(opportunity_record)
    sector_diagnostic = _sector_diagnostic_view(leadership_records or {}, ticker)
    trigger_reference = _trigger_reference_view(opportunity_record)
    reasons = (decision_record.get("deterministic_research_inference") or {}).get("reasons") or []
    warnings = (decision_record.get("warnings_counter_thesis") or {}).get("warnings") or decision_record.get("warnings") or []
    financial = decision_record.get("financial_analysis") or {"status": "NOT_SUPPLIED", "compact": None}
    return {
        "ticker": ticker,
        "as_of_session": decision_record.get("as_of_session") or opportunity_record.get("as_of_session"),
        "sector": sector,
        # A. Current stance
        "research_stance": decision_record.get("research_stance"),
        "research_stance_readiness": decision_record.get("research_stance_readiness"),
        "entry_state": decision_record.get("entry_state"),
        "entry_action": decision_record.get("entry_action"),
        "setup_tags": list(tactical.get("setup_tags") or []),
        # B. Why
        "why": {
            "fundamental_evidence": fundamental_view,
            "valuation_evidence": valuation_view,
            "tactical_evidence": {
                "primary_entry_state": tactical.get("primary_entry_state"),
                "entry_action": tactical.get("entry_action"),
                "setup_tags": list(tactical.get("setup_tags") or []),
                "reference_trigger": trigger_reference,
            },
            "market_sector_evidence": {
                "breadth_regime": market.get("breadth_regime"),
                "sector_relative_context": market.get("sector_relative_context"),
                "sector_diagnostic": sector_diagnostic,
            },
            "catalyst_evidence": catalyst_view,
            "deterministic_reasons": list(reasons),
            "financial_analysis": {
                "status": financial.get("status"), "supporting": list(financial.get("supporting") or []),
                "compact": financial.get("compact"),
            },
            "counterbalancing_context": list(decision_record.get("counterbalancing_context") or []),
        },
        # C. Counter-thesis
        "counter_thesis": {
            "warnings": list(warnings),
            "key_counter_thesis": list(decision_record.get("key_counter_thesis") or []),
            "financial_analysis": {
                "counter_thesis": list(financial.get("counter_thesis") or []),
                "missing_dimensions": list(financial.get("missing_dimensions") or []),
                "current_financial_weakness": list(financial.get("current_financial_weakness") or []),
            },
            "unavailable_dimensions": sorted(set(WORKSPACE_AXES) - usable_axes),
        },
        # D. Confirmation
        "confirmation": dict(decision_record.get("confirmation_boundary") or {"status": "UNAVAILABLE"}),
        # Reference trigger/invalidation level -- diagnostic only, never a confirmed entry.
        "reference_trigger": trigger_reference,
        # E. Invalidation
        "invalidation": {
            "technical": dict(decision_record.get("technical_invalidation") or {"status": "UNAVAILABLE"}),
            "fundamental": dict(decision_record.get("fundamental_invalidation") or {"status": "UNAVAILABLE"}),
            "future_financial_invalidation_watch": list(financial.get("future_financial_invalidation_watch") or []),
        },
        # Supporting axes shown alongside the card
        "fundamental": fundamental_view,
        "valuation": valuation_view,
        "tactical": {
            "primary_entry_state": tactical.get("primary_entry_state"), "entry_action": tactical.get("entry_action"),
            "setup_tags": list(tactical.get("setup_tags") or []),
            "freshness_status": (tactical.get("freshness") or {}).get("freshness_status"),
            "source_session": (tactical.get("freshness") or {}).get("source_session"),
            "reference_trigger": trigger_reference,
        },
        "market_sector": {
            "breadth_regime": market.get("breadth_regime"), "sector_relative_context": market.get("sector_relative_context"),
            "freshness_status": (market.get("freshness") or {}).get("freshness_status"),
            "sector_diagnostic": sector_diagnostic,
        },
        "catalyst": catalyst_view,
        "liquidity": _liquidity_view(opportunity_record),
        # F. Portfolio impact
        "portfolio": _portfolio_view(portfolio_research, ticker, sector),
        # Prospective research case
        "prospective_case": prospective_record,
        # G. Data / authority
        "lineage": _lineage_view(opportunity_record),
        "authority_boundary": {
            "is_actionable": False, "no_score": True, "no_rank": True, "no_probability": True, "no_target_price": True,
            "research_stance_is_not_execution_order": True, "priority_now_is_not_buy_now": True,
            "security_attractiveness_separate_from_portfolio_fit": True,
            "portfolio_fit_does_not_mutate_research_stance": True,
        },
    }


def build_artifacts(
    *,
    opportunity_artifact: Mapping[str, Any],
    decision_artifact: Mapping[str, Any],
    leadership: Mapping[str, Any] | None = None,
    portfolio_research: Mapping[str, Any] | None = None,
    prospective_lifecycle: Mapping[str, Any] | None = None,
    requested_at: str,
    current_research_scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Join a matched opportunity_context/v1 + security_decision_context/v1 pair into the
    compact investment_decision_workspace_projection/v1 artifact. Raises fail-closed if the two
    artifacts are not the same lineage pair, if a ticker is present in one but not the other, or
    if the denominator is empty. leadership/portfolio_research/prospective_lifecycle are optional
    enrichment inputs; their absence degrades individual card fields to explicit unavailable
    states, never the whole workspace.

    ``current_research_scope`` is a fully opt-in, explicit seam: omitted (the default), the
    denominator and every card are byte-identical to the pre-existing behavior. When supplied
    (the return value of ``current_research_official_universe_scope.resolve_scope``), every card
    is built EXACTLY as before -- decision fields (research_stance, entry_state, valuation,
    thesis/counter-thesis, confirmation, invalidation, financial context, ...) are never
    re-derived or mutated by scope.

    CURRENT_OFFICIAL_RESEARCH_UNIVERSE_PRODUCT_CUTOVER_AND_RELEASE_INTEGRATION_V1: supplying
    ``current_research_scope`` never narrows or drops the Daily ticker denominator -- every card
    this function would otherwise build stays present. Each card instead gains an additive
    ``official_research_scope`` field (``current_research_official_universe_scope.
    ticker_scope_view``), and ``coverage`` gains an aggregate scope-count block. A ticker outside
    the current official research scope is presented with an explicit reason, never dropped.
    """
    if opportunity_artifact.get("contract_version") != "opportunity_context/v1":
        raise InvestmentDecisionWorkspaceError("OPPORTUNITY_CONTRACT_UNSUPPORTED")
    if decision_artifact.get("contract_version") != "security_decision_context/v1":
        raise InvestmentDecisionWorkspaceError("DECISION_CONTRACT_UNSUPPORTED")
    if decision_artifact.get("source_artifacts", {}).get("opportunity_context") != opportunity_artifact.get("artifact_identity"):
        raise InvestmentDecisionWorkspaceError("OPPORTUNITY_DECISION_LINEAGE_MISMATCH")

    opportunity_records = opportunity_artifact.get("records")
    decision_records = decision_artifact.get("records")
    if not isinstance(opportunity_records, Mapping) or not isinstance(decision_records, Mapping):
        raise InvestmentDecisionWorkspaceError("SOURCE_RECORDS_INVALID")
    tickers = sorted(opportunity_records)
    if not tickers:
        raise InvestmentDecisionWorkspaceError("EMPTY_WORKSPACE_DENOMINATOR")
    if set(opportunity_records) != set(decision_records):
        raise InvestmentDecisionWorkspaceError("OPPORTUNITY_DECISION_TICKER_SET_MISMATCH")

    leadership_records = (leadership or {}).get("ticker_contexts") if isinstance(leadership, Mapping) else None
    if not isinstance(leadership_records, Mapping):
        leadership_records = {}

    current_research_scope_supplied = current_research_scope is not None
    current_research_scope_applied = bool(
        isinstance(current_research_scope, Mapping) and current_research_scope.get("temporally_eligible")
    )

    cards: dict[str, Any] = {}
    for ticker in tickers:
        sector = _sector_label(leadership_records, ticker)
        card = build_ticker_card(
            ticker=ticker,
            opportunity_record=opportunity_records[ticker],
            decision_record=decision_records[ticker],
            sector=sector,
            portfolio_research=portfolio_research,
            prospective_record=_prospective_view(prospective_lifecycle, ticker),
            leadership_records=leadership_records,
        )
        if current_research_scope_supplied:
            card["official_research_scope"] = current_research_official_universe_scope_module.ticker_scope_view(
                current_research_scope, ticker,
            )
        cards[ticker] = card

    if set(cards) != set(tickers):
        raise InvestmentDecisionWorkspaceError("SILENT_TICKER_DROP")

    pre_scope_ticker_count = len(cards)
    official_scope_coverage: dict[str, Any] | None = None
    if current_research_scope_supplied:
        _scope_mod = current_research_official_universe_scope_module
        in_scope = sum(card["official_research_scope"]["scope_bucket"] == _scope_mod.SIMPLE_IN_SCOPE for card in cards.values())
        outside_scope = sum(card["official_research_scope"]["scope_bucket"] == _scope_mod.SIMPLE_OUTSIDE_SCOPE for card in cards.values())
        unknown_scope = len(cards) - in_scope - outside_scope
        official_scope_coverage = {
            "temporally_eligible": current_research_scope_applied,
            "disposition": current_research_scope.get("disposition") if isinstance(current_research_scope, Mapping) else None,
            "research_session": current_research_scope.get("research_session") if isinstance(current_research_scope, Mapping) else None,
            "official_snapshot_observed_at": current_research_scope.get("official_snapshot_observed_at") if isinstance(current_research_scope, Mapping) else None,
            "workspace_denominator": len(cards),
            "current_official_research_scope_count": in_scope,
            "outside_current_official_scope_count": outside_scope,
            "current_official_scope_unknown_count": unknown_scope,
        }

    stance_counts = Counter(card["research_stance"] or "NONE" for card in cards.values())
    entry_state_counts = Counter(card["entry_state"] or "NONE" for card in cards.values())
    valuation_counts = Counter(card["valuation"]["relative_research_state"] or "NONE" for card in cards.values())
    guard_applied_count = sum(1 for card in cards.values() if card["valuation"]["market_cap_semantic_guard_applied"])
    portfolio_evaluated_count = sum(1 for card in cards.values() if card["portfolio"]["evaluated"])
    prospective_available_count = sum(
        1 for card in cards.values() if card["prospective_case"]["status"] == "ACTIVE_CASES_AVAILABLE"
    )
    stale_axis_count = sum(
        1 for card in cards.values()
        if any(status not in {None, "CURRENT"} for status in (card["lineage"]["per_axis_freshness"] or {}).values())
    )
    financial_available_count = sum(card["why"]["financial_analysis"]["status"] == "AVAILABLE" for card in cards.values())

    source_artifacts = {
        "opportunity_context": opportunity_artifact.get("artifact_identity"),
        "security_decision_context": decision_artifact.get("artifact_identity"),
        "market_sector_leadership": (leadership or {}).get("artifact_identity"),
        "portfolio_research_context": (portfolio_research or {}).get("artifact_identity"),
        "prospective_thesis_lifecycle": (prospective_lifecycle or {}).get("artifact_identity"),
        "current_research_official_universe_scope": (
            {"research_session": current_research_scope.get("research_session"), "official_snapshot_observed_at": current_research_scope.get("official_snapshot_observed_at")}
            if current_research_scope_supplied else None
        ),
    }

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION, "milestone": MILESTONE,
        "requested_at": requested_at, "as_of_session": opportunity_artifact.get("as_of_session"),
        "source_artifacts": source_artifacts,
        "official_scope_coverage": official_scope_coverage,
        "coverage": {
            "ticker_denominator": len(cards),
            "workspace_coverage": len(cards),
            "zero_silent_ticker_drops": True,
            "pre_scope_ticker_count": pre_scope_ticker_count,
            "current_research_scope_supplied": current_research_scope_supplied,
            "current_research_scope_applied": current_research_scope_applied,
            "research_stance_distribution": dict(sorted(stance_counts.items())),
            "entry_state_distribution": dict(sorted(entry_state_counts.items())),
            "valuation_relative_state_distribution": dict(sorted(valuation_counts.items())),
            "market_cap_semantic_guard_applied_count": guard_applied_count,
            "portfolio_evaluated_count": portfolio_evaluated_count,
            "prospective_cases_available_count": prospective_available_count,
            "stale_axis_present_count": stale_axis_count,
            "financial_analysis_available_count": financial_available_count,
        },
        "blocked_outputs": {
            "universal_score": "SCORING_PROHIBITED", "ordinal_rank": "RANKING_PROHIBITED",
            "probability_of_success": "FORECAST_PROHIBITED", "target_price": "NOT_EMITTED",
            "backtest_or_pit_outcome": "NOT_EMITTED", "portfolio_optimization": "NOT_EMITTED",
        },
        "cards": cards,
        "authority_effect": "NONE / PRODUCT_WORKSPACE_ONLY",
    }
    artifact.update(content_identity(artifact))
    return artifact
