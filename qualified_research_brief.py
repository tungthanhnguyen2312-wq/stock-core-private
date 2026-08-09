"""Compact, deterministic historical research brief projected from producer truth."""
from __future__ import annotations

from typing import Any, Mapping


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def build(ticker: str, entry: Mapping[str, Any]) -> dict[str, Any]:
    decision = _map(entry.get("historical_decision_analysis"))
    portfolio = _map(entry.get("portfolio_risk_analysis"))
    analytics = _map(decision.get("fundamental_analytics"))
    facts = list(_map(decision.get("provenance")).get("qualified_fact_references") or [])[:8]
    scenarios = _map(decision.get("scenarios"))
    conclusion = _map(decision.get("historical_conclusion"))
    limitations = sorted(set(list(decision.get("missing_evidence") or []) +
                             list(analytics.get("blocking_reasons") or []) +
                             (["insufficient_history_for_trend"] if analytics.get("trend_status") == "insufficient_history" else [])))
    return {
        "schema_version": "1.1.0",
        "ticker": str(ticker).upper(),
        "analysis_mode": "historical_only_qualified_data",
        "entity_type": entry.get("entity_type"),
        "is_actionable": False,
        "historical_only": True,
        "market_dependent": False,
        "identity": {"periods": decision.get("data_periods_used", []), "eligibility": decision.get("eligibility", {})},
        "qualified_facts": facts,
        "quality": decision.get("quality_assessment", {}),
        "derived_historical_fundamental_analytics": analytics,
        "fundamental_strengths": list(analytics.get("strength_predicates") or []),
        "fundamental_risks": list(analytics.get("risk_predicates") or []),
        "risks": {"phase_4b": decision.get("risks", []), "phase_4c": _map(portfolio.get("fundamental_risk"))},
        "catalysts": decision.get("catalysts", []),
        "scenarios": scenarios,
        "bear_base_bull_conditions": {
            name: list(_map(scenarios.get(name)).get("historical_fundamental_conditions") or
                       _map(scenarios.get(name)).get("required_conditions") or [])
            for name in ("bear", "base", "bull")
        },
        "invalidation_conditions": decision.get("invalidation_conditions", []),
        "historical_conclusion": conclusion,
        "data_limitations": limitations,
        "missing_evidence": decision.get("missing_evidence", []),
        "what_cannot_yet_be_concluded": [
            "No valuation, target price, recommendation, ranking, expected return, or portfolio sizing is produced.",
            "No market-price, liquidity, corporate-action, or valuation conclusion is implied.",
            "Trend interpretation is unavailable until two complete qualified annual periods exist.",
        ],
        "comparative_research_context": entry.get("historical_fundamental_comparative_matrix", {}),
        "qualified_cohort_context": entry.get("qualified_cohort_comparison", {}),
        "portfolio_risk_boundary": {
            "liquidity": portfolio.get("liquidity", {}),
            "portfolio_context": _map(portfolio.get("portfolio_considerations")).get("actual_portfolio_fit", {}),
            "allocation": portfolio.get("allocation_eligibility", {}),
        },
        "prohibited_claims": [
            "current_valuation", "target_price", "buy_hold_sell", "ranking", "sizing",
            "current_market_liquidity", "expected_return", "portfolio_allocation",
        ],
    }
