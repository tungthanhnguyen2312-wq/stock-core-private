"""Orchestrate the existing shadow-recommendation/invalidation engine chain for one session.

This module invents no recommendation, invalidation, opportunity, or tactical rule. It
resolves same-session raw research (market/tactical) and reuses already-retained,
legitimately session-independent context (fundamental cross-sectional scoring,
valuation-research proxy, corporate events, TTM, A1/A2 temporal) exactly as the canonical
Daily Producer session operation already treats those same dimensions
(REUSE_HISTORICAL_CONTEXT / ACCEPTED_UNDATED_RETAINED_CONTEXT), then calls the existing
engines verbatim, in their established order:

    fundamental_market_opportunity_ranking
    -> thesis_catalyst_downside_research_cases
    -> shadow_action_readiness            (pass 1, no boundaries yet)
    -> fundamental_thesis_invalidation_precision
    -> action_instrumentation             (pass 1, informs pass-2 readiness)
    -> shadow_action_readiness            (pass 2, boundary-informed)
    -> action_instrumentation             (pass 2, final)
    -> shadow_security_recommendation

This mirrors exactly the two-phase bootstrap already used by
tools/run_fundamental_thesis_invalidation_precision_v1.py and
tools/run_shadow_security_recommendation.py; only the source of `market`/`tactical`
becomes an explicit session parameter instead of a hardcoded frozen-cohort path. No
engine's rule, threshold, label vocabulary, or evaluation order is changed.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

import action_instrumentation
import fundamental_market_opportunity_ranking
import fundamental_thesis_invalidation_precision
import shadow_action_readiness
import shadow_security_recommendation
import thesis_catalyst_downside_research_cases

CONTRACT_VERSION = "daily_session_shadow_recommendation/v1"


class DailySessionShadowRecommendationError(ValueError):
    """Fail-closed refusal: the target session's own inputs are incoherent or insufficient."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"daily_session_shadow_recommendation:{digest}"}


def build(
    *,
    market: Mapping[str, Any],
    tactical: Mapping[str, Any],
    fundamental: Mapping[str, Any],
    valuation: Mapping[str, Any],
    events: Mapping[str, Any],
    ttm: Mapping[str, Any],
    risk_research: Mapping[str, Any] | None = None,
    valuation_research: Mapping[str, Any] | None = None,
    a1_temporal: Mapping[str, Any] | None = None,
    a2_temporal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reuse the existing engines verbatim for the session carried by `market`/`tactical`.

    `market` is the raw market_wide_current_descriptive_research/v1 artifact and `tactical`
    the raw watchlist_tactical_entry_classifier/v1 artifact for the target session; both are
    required to already agree on `session` (fundamental_market_opportunity_ranking enforces
    this itself). `fundamental`/`valuation`/`events`/`ttm`/`risk_research`/`valuation_research`/
    `a1_temporal`/`a2_temporal` are passed straight through to the unmodified engines and may
    legitimately be reused, undated, retained context -- exactly as the canonical Daily
    Producer pipeline already treats the `fundamental` and `catalyst` dimensions.
    """
    session = market.get("session")
    if not isinstance(session, str) or not session:
        raise DailySessionShadowRecommendationError("MARKET_SESSION_MISSING")
    if tactical.get("session") != session:
        raise DailySessionShadowRecommendationError("TACTICAL_SESSION_MISMATCH")

    opportunity = fundamental_market_opportunity_ranking.build_artifact(
        fundamental=fundamental, market=market, tactical=tactical, valuation=valuation)
    cases = thesis_catalyst_downside_research_cases.build_artifact(opportunity=opportunity, events=events, ttm=ttm)
    base_shadow = shadow_action_readiness.build_artifact(research_cases=cases)
    boundaries = fundamental_thesis_invalidation_precision.build_artifact(shadow=base_shadow)
    preliminary_action = action_instrumentation.build_artifact(
        shadow=base_shadow, tactical=tactical, descriptive=market, fundamental_boundaries_by_ticker=boundaries["records"])
    final_shadow = shadow_action_readiness.build_artifact(
        research_cases=cases, fundamental_boundaries_by_ticker=boundaries["records"],
        technical_boundaries_by_ticker=preliminary_action["records"])
    action = action_instrumentation.build_artifact(
        shadow=final_shadow, tactical=tactical, descriptive=market, fundamental_boundaries_by_ticker=boundaries["records"])
    recommendation = shadow_security_recommendation.build_artifact(
        research_cases=cases, shadow_readiness=final_shadow, action_instrumentation=action,
        fundamental_invalidation=boundaries, risk_research=risk_research, valuation_research=valuation_research,
        a1_temporal=a1_temporal, a2_temporal=a2_temporal)
    recommendation_as_of = (recommendation.get("metadata") or {}).get("as_of_session")
    if recommendation_as_of != session:
        raise DailySessionShadowRecommendationError("OUTPUT_SESSION_MISMATCH:" + str(recommendation_as_of))

    artifact: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "session": session,
        "source_artifact_identities": {
            "market": market.get("artifact_identity"),
            "tactical": tactical.get("artifact_identity"),
            "fundamental": fundamental.get("artifact_identity"),
            "valuation": valuation.get("artifact_identity"),
            "events": events.get("artifact_identity"),
            "ttm": ttm.get("artifact_identity"),
            "risk_research": (risk_research or {}).get("artifact_identity"),
            "valuation_research": (valuation_research or {}).get("artifact_identity") or (valuation_research or {}).get("artifact_sha256"),
            "a1_temporal": (a1_temporal or {}).get("artifact_identity"),
            "a2_temporal": (a2_temporal or {}).get("artifact_identity"),
        },
        "denominator_by_stage": {
            "opportunity_ranking": len(opportunity.get("records") or {}),
            "research_cases": len(cases.get("records") or {}),
            "shadow_action_readiness": len(final_shadow.get("records") or {}),
            "fundamental_thesis_invalidation_precision": len(boundaries.get("records") or {}),
            "action_instrumentation": len(action.get("records") or {}),
            "shadow_security_recommendation": recommendation.get("denominator"),
        },
        "engines_reused_verbatim": [
            fundamental_market_opportunity_ranking.CONTRACT_VERSION,
            thesis_catalyst_downside_research_cases.CONTRACT_VERSION,
            shadow_action_readiness.CONTRACT_VERSION,
            fundamental_thesis_invalidation_precision.CONTRACT_VERSION,
            action_instrumentation.CONTRACT_VERSION,
            shadow_security_recommendation.CONTRACT_VERSION,
        ],
        "opportunity_ranking": opportunity,
        "research_cases": cases,
        "shadow_action_readiness": final_shadow,
        "fundamental_thesis_invalidation_precision": boundaries,
        "action_instrumentation": action,
        "shadow_security_recommendation": recommendation,
        "authority_effect": "NONE",
        "research_tier": "PROSPECTIVE_MULTI_SESSION_RESEARCH_ONLY",
        "is_actionable": False,
    }
    artifact.update(_identity(artifact))
    return artifact
