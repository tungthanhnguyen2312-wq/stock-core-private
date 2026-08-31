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
    return {
        "relative_research_state": display_state,
        "raw_upstream_relative_research_state": raw_state,
        "market_cap_semantic_guard_applied": guard_applied,
        "usable_relative_method_count": usable_count,
        "supporting_methods": supporting,
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
        "freshness_status": (liquidity.get("freshness") or {}).get("freshness_status"),
        "source_session": (liquidity.get("freshness") or {}).get("source_session"),
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
) -> dict[str, Any]:
    """Compose one seven-section decision-workspace card for a single ticker."""
    fundamental = opportunity_record.get("fundamental") or {}
    tactical = opportunity_record.get("tactical") or {}
    market = opportunity_record.get("market_sector") or {}
    usable_axes = set(opportunity_record.get("usable_major_axes") or [])
    valuation_view = _valuation_view(opportunity_record)
    catalyst_view = _catalyst_view(opportunity_record)
    reasons = (decision_record.get("deterministic_research_inference") or {}).get("reasons") or []
    warnings = (decision_record.get("warnings_counter_thesis") or {}).get("warnings") or decision_record.get("warnings") or []
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
            "fundamental_evidence": {
                "state": fundamental.get("state"), "trajectory": fundamental.get("trajectory"),
                "readiness": fundamental.get("readiness"), "research_fitness": fundamental.get("research_fitness"),
            },
            "valuation_evidence": valuation_view,
            "tactical_evidence": {
                "primary_entry_state": tactical.get("primary_entry_state"),
                "entry_action": tactical.get("entry_action"),
                "setup_tags": list(tactical.get("setup_tags") or []),
            },
            "market_sector_evidence": {
                "breadth_regime": market.get("breadth_regime"),
                "sector_relative_context": market.get("sector_relative_context"),
            },
            "catalyst_evidence": catalyst_view,
            "deterministic_reasons": list(reasons),
            "counterbalancing_context": list(decision_record.get("counterbalancing_context") or []),
        },
        # C. Counter-thesis
        "counter_thesis": {
            "warnings": list(warnings),
            "key_counter_thesis": list(decision_record.get("key_counter_thesis") or []),
            "unavailable_dimensions": sorted(set(WORKSPACE_AXES) - usable_axes),
        },
        # D. Confirmation
        "confirmation": dict(decision_record.get("confirmation_boundary") or {"status": "UNAVAILABLE"}),
        # E. Invalidation
        "invalidation": {
            "technical": dict(decision_record.get("technical_invalidation") or {"status": "UNAVAILABLE"}),
            "fundamental": dict(decision_record.get("fundamental_invalidation") or {"status": "UNAVAILABLE"}),
        },
        # Supporting axes shown alongside the card
        "fundamental": {
            "state": fundamental.get("state"), "trajectory": fundamental.get("trajectory"),
            "readiness": fundamental.get("readiness"), "research_fitness": fundamental.get("research_fitness"),
            "freshness_status": (fundamental.get("freshness") or {}).get("freshness_status"),
            "source_period": (fundamental.get("freshness") or {}).get("source_period"),
        },
        "valuation": valuation_view,
        "tactical": {
            "primary_entry_state": tactical.get("primary_entry_state"), "entry_action": tactical.get("entry_action"),
            "setup_tags": list(tactical.get("setup_tags") or []),
            "freshness_status": (tactical.get("freshness") or {}).get("freshness_status"),
            "source_session": (tactical.get("freshness") or {}).get("source_session"),
        },
        "market_sector": {
            "breadth_regime": market.get("breadth_regime"), "sector_relative_context": market.get("sector_relative_context"),
            "freshness_status": (market.get("freshness") or {}).get("freshness_status"),
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
) -> dict[str, Any]:
    """Join a matched opportunity_context/v1 + security_decision_context/v1 pair into the
    compact investment_decision_workspace_projection/v1 artifact. Raises fail-closed if the two
    artifacts are not the same lineage pair, if a ticker is present in one but not the other, or
    if the denominator is empty. leadership/portfolio_research/prospective_lifecycle are optional
    enrichment inputs; their absence degrades individual card fields to explicit unavailable
    states, never the whole workspace.
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

    cards: dict[str, Any] = {}
    for ticker in tickers:
        sector = _sector_label(leadership_records, ticker)
        cards[ticker] = build_ticker_card(
            ticker=ticker,
            opportunity_record=opportunity_records[ticker],
            decision_record=decision_records[ticker],
            sector=sector,
            portfolio_research=portfolio_research,
            prospective_record=_prospective_view(prospective_lifecycle, ticker),
        )

    if set(cards) != set(tickers):
        raise InvestmentDecisionWorkspaceError("SILENT_TICKER_DROP")

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

    source_artifacts = {
        "opportunity_context": opportunity_artifact.get("artifact_identity"),
        "security_decision_context": decision_artifact.get("artifact_identity"),
        "market_sector_leadership": (leadership or {}).get("artifact_identity"),
        "portfolio_research_context": (portfolio_research or {}).get("artifact_identity"),
        "prospective_thesis_lifecycle": (prospective_lifecycle or {}).get("artifact_identity"),
    }

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION, "milestone": MILESTONE,
        "requested_at": requested_at, "as_of_session": opportunity_artifact.get("as_of_session"),
        "source_artifacts": source_artifacts,
        "coverage": {
            "ticker_denominator": len(cards),
            "workspace_coverage": len(cards),
            "zero_silent_ticker_drops": True,
            "research_stance_distribution": dict(sorted(stance_counts.items())),
            "entry_state_distribution": dict(sorted(entry_state_counts.items())),
            "valuation_relative_state_distribution": dict(sorted(valuation_counts.items())),
            "market_cap_semantic_guard_applied_count": guard_applied_count,
            "portfolio_evaluated_count": portfolio_evaluated_count,
            "prospective_cases_available_count": prospective_available_count,
            "stale_axis_present_count": stale_axis_count,
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
