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
from pathlib import Path
from typing import Any, Mapping

import action_instrumentation
import fundamental_market_opportunity_ranking
import fundamental_thesis_invalidation_precision
import shadow_action_readiness
import shadow_security_recommendation
import thesis_catalyst_downside_research_cases

CONTRACT_VERSION = "daily_session_shadow_recommendation/v1"

# These are the existing governed, session-independent research contexts consumed
# by the proven daily-session chain.  They are deliberately explicit rather than
# discovered by glob/latest selection.  Market and tactical inputs come from the
# completed-session registry and remain exact-session inputs.
SHARED_CONTEXT_RELATIVE_PATHS = {
    "fundamental": "operations-review/fundamental-cross-sectional-scoring-and-ranking-v1-20260828/artifact.json",
    "valuation": "operations-review/current-valuation-research-proxy-and-relative-value-axis-v1-20260828/artifact.json",
    "events": "operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json",
    "ttm": "operations-review/financial-flow-semantics-and-ttm-bridge-foundation-v1-20260828/artifact.json",
    "risk_research": "operations-review/current-portfolio-risk-research-v1-20260829/artifact.json",
    "a1_temporal": "operations-review/a1-bitemporal-semantic-contract-v1-20260828/artifact.json",
    "a2_temporal": "operations-review/a2-provider-publication-first-seen-retention-v1-20260829/artifact.json",
}
RETAINED_ARTIFACT_DIRECTORY = "daily-session-shadow-recommendation-v1"


class DailySessionShadowRecommendationError(ValueError):
    """Fail-closed refusal: the target session's own inputs are incoherent or insufficient."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"daily_session_shadow_recommendation:{digest}"}


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical(value) + "\n").encode("utf-8")


def _load_retained_context(root: Path, name: str, relative_path: str) -> dict[str, Any]:
    path = root / relative_path
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except FileNotFoundError as exc:
        raise DailySessionShadowRecommendationError("RETAINED_CONTEXT_MISSING:" + name) from exc
    except json.JSONDecodeError as exc:
        raise DailySessionShadowRecommendationError("RETAINED_CONTEXT_CORRUPT:" + name) from exc
    if not isinstance(value, dict):
        raise DailySessionShadowRecommendationError("RETAINED_CONTEXT_INVALID:" + name)
    value.setdefault("source_artifact_sha256", hashlib.sha256(raw).hexdigest())
    return value


def _source_identity(value: Mapping[str, Any] | None) -> str | None:
    source = value or {}
    return source.get("artifact_identity") or source.get("artifact_sha256") or source.get("source_artifact_sha256")


def resolve_or_build(
    root: Path,
    *,
    session: str,
    inputs: Mapping[str, Any],
    output_root: Path | None = None,
    shared_context_paths: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve the exact-session chain, then immutably build or reuse it.

    This is the canonical Producer integration point.  It performs no provider
    acquisition: ``inputs`` are already registry-resolved and every remaining
    context is an explicitly named retained artifact.  A session directory is
    intentionally single-identity: changed same-session lineage is an integrity
    conflict, not an invitation to silently replace historical research.
    """
    source_root = Path(root)
    if not isinstance(inputs.get("descriptive"), Mapping) or not isinstance(inputs.get("tactical"), Mapping):
        raise DailySessionShadowRecommendationError("SESSION_RESEARCH_INPUTS_MISSING")
    if inputs["descriptive"].get("session") != session or inputs["tactical"].get("session") != session:
        raise DailySessionShadowRecommendationError("SESSION_RESEARCH_INPUTS_MISMATCH")
    paths = dict(SHARED_CONTEXT_RELATIVE_PATHS if shared_context_paths is None else shared_context_paths)
    if set(paths) != set(SHARED_CONTEXT_RELATIVE_PATHS):
        raise DailySessionShadowRecommendationError("RETAINED_CONTEXT_PATH_SET_INVALID")
    shared = {name: _load_retained_context(source_root, name, paths[name]) for name in sorted(paths)}
    chain = build(
        market=inputs["descriptive"], tactical=inputs["tactical"],
        fundamental=shared["fundamental"], valuation=shared["valuation"], events=shared["events"], ttm=shared["ttm"],
        risk_research=shared["risk_research"], valuation_research=shared["valuation"],
        a1_temporal=shared["a1_temporal"], a2_temporal=shared["a2_temporal"],
    )
    if chain.get("session") != session or (chain.get("shadow_security_recommendation", {}).get("metadata") or {}).get("as_of_session") != session:
        raise DailySessionShadowRecommendationError("AUTOSOURCED_OUTPUT_SESSION_MISMATCH")
    target_root = Path(output_root) if output_root is not None else source_root / "operations-review"
    path = target_root / RETAINED_ARTIFACT_DIRECTORY / session / "daily_session_shadow_recommendation.json"
    payload = _canonical_bytes(chain)
    if path.exists():
        try:
            retained = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DailySessionShadowRecommendationError("RETAINED_DAILY_SHADOW_ARTIFACT_CORRUPT") from exc
        retained_identity = _identity(retained) if isinstance(retained, Mapping) else {}
        if (
            not isinstance(retained, Mapping)
            or retained_identity.get("artifact_identity") != retained.get("artifact_identity")
            or retained_identity.get("artifact_sha256") != retained.get("artifact_sha256")
            or retained.get("session") != session
            or retained.get("source_artifact_identities") != chain.get("source_artifact_identities")
            or _canonical_bytes(retained) != payload
        ):
            raise DailySessionShadowRecommendationError("IMMUTABLE_DAILY_SESSION_SHADOW_RECOMMENDATION_CONFLICT")
        return {"status": "REUSED", "path": path, "chain": retained}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"status": "BUILT", "path": path, "chain": chain}


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
            "market": _source_identity(market),
            "tactical": _source_identity(tactical),
            "fundamental": _source_identity(fundamental),
            "valuation": _source_identity(valuation),
            "events": _source_identity(events),
            "ttm": _source_identity(ttm),
            "risk_research": _source_identity(risk_research),
            "valuation_research": _source_identity(valuation_research),
            "a1_temporal": _source_identity(a1_temporal),
            "a2_temporal": _source_identity(a2_temporal),
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
