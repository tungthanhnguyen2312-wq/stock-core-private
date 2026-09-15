"""current_research_ai_handoff_packet/v1: deterministic, portable, session-bound consumer
contract that hands a fresh AI research chat everything Investment Decision Workspace and
Screener Master Projection already computed for a session, without repository access.

Why this exists: a fresh AI chat has no way to read
``investment_decision_workspace_projection.json`` / ``screener_master_projection.json`` from a
Stock Lookup checkout. Today that means it falls back to external overlays (Finhay, generic web
research) for basic questions Stock Lookup itself already answers -- current research stance,
entry state, valuation readiness/method, catalyst context, confirmation/invalidation -- risking
blurred authority between Stock Lookup's governed evidence and un-governed external claims, and
inviting the AI to invent sizing or exact technical triggers on an unbound price basis. This is a
consumer transport / fitness-for-use gap, not a missing analytical capability.

Mandatory flow, enforced structurally by this module: retained qualified evidence (Workspace,
Screener, market-wide descriptive research, official-universe scope, and -- as of the
``CURRENT_RESEARCH_AI_HANDOFF_PACKET_V1_CORRECTIVE_TECHNICAL_PASS_THROUGH_AND_RELEASE`` corrective
pass -- the existing current-session technical producers ``tactical_momentum_context/v1``,
``technical_structure_context/v2``, ``tactical_confirmation_context/v1``) -> already-computed by
those modules -> this packet. This module performs ZERO new analysis: every field is either a
direct pass-through of an already-built Workspace/Screener card field or an already-built
technical-producer record, or an explicit ``NOT_AVAILABLE`` only when the producing artifact
genuinely does not have a value for that ticker/session (see ``_technical_measurements_view``). It
never computes RSI/MACD/moving averages/structure itself (those are read verbatim from
``tactical_momentum_context``/``technical_structure_context``, never recalculated), never invents
ADX/MFI (genuinely absent from this repository), never derives a target price, probability,
position size, or execution level, and never reads private portfolio/account state (Workspace's
own ``portfolio`` section, which is private-position context, is deliberately never read by this
module -- see ``build_card``).

Correction to an earlier pass of this milestone: RSI/MACD/moving-average/momentum/structure/
relative-volume measurements were previously reported as ``NOT_CURRENTLY_PRODUCED``. That was
wrong -- they are already produced and retained per current session by
``tactical_momentum_context.py``/``technical_structure_context.py`` (resolved here via the exact
same deterministic ``daily_session_level2_package.session_artifact_paths()`` path contract
Workspace's own supplementary technical axes already use), simply not yet threaded through
Workspace/Screener's own card shape. The gap was ``NOT_EXPOSED_BY_OLD_WORKSPACE_SCREENER_JOIN``,
not ``NOT_CURRENTLY_PRODUCED``. Numeric price-derived technical measurements are additionally
paired with a reused ``price_basis_feature_fitness`` (``price_basis_semantics_and_feature_
fitness/v1``) verdict per ticker, exactly the module's existing, unmodified evaluator and
vocabulary (``BASIS_COMPATIBLE`` / ``BASIS_COMPATIBLE_RESEARCH_ONLY`` / ``BASIS_UNVERIFIED`` /
``BASIS_INCOMPATIBLE`` / ``POINT_IN_TIME_SEMANTICS_UNQUALIFIED``), so a numeric level never reads
as execution-qualified.

``market_context`` is built from two independently governed sessions'
``market_wide_current_descriptive_research/v1`` artifacts (current + the one prior governed
session, both resolved the same already-governed way
``daily_research_session_operations.resolve_inputs`` already resolves them for their own
sessions) so a single-session snapshot cannot be over-read by the AI consumer as a regime
transition. No new regime label is invented: the existing ``breadth_descriptor``/
``momentum_descriptor`` objects (``market_regime_breadth_context/v1``) are passed through with
their own rule identity intact.

``official_research_scope`` per card reuses
``canonical_current_product_projections.resolve_current_research_official_universe_scope`` and
``current_research_official_universe_scope.ticker_scope_view`` -- the exact same pinned,
identity-verified evidence and classification Workspace/Screener already apply internally when
that axis is threaded through them. This module never re-derives the classification itself; it
only joins the same resolved result onto cards, exactly the way those two build functions already
do when ``current_research_scope`` is supplied to them.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

import current_research_official_universe_scope as current_research_official_universe_scope_module
import price_basis_feature_fitness

CONTRACT_VERSION = "current_research_ai_handoff_packet/v1"
WATCHLIST_CONTRACT_VERSION = "current_research_ai_handoff_watchlist/v1"
MILESTONE = "CURRENT_RESEARCH_AI_HANDOFF_PACKET_V1"
SCHEMA_VERSION = "1.0.0"
_IDENTITY_EXCLUDED = {"artifact_sha256", "artifact_identity", "requested_at"}

NOT_AVAILABLE = "NOT_AVAILABLE"
NOT_COVERED = "NOT_COVERED_BY_CURRENT_PRODUCTS"

#: Section 7 machine-readable AI boundary. Every packet and every card carries this exact
#: vocabulary -- never a per-card variant, never silently omitted.
AI_BOUNDARY: dict[str, bool] = {
    "AI_MAY_EXPLAIN": True,
    "AI_MAY_COMPARE": True,
    "AI_MAY_FORM_CONDITIONAL_RESEARCH_SCENARIOS": True,
    "AI_MAY_IDENTIFY_COUNTER_THESIS": True,
    "AI_MAY_PROMOTE_AUTHORITY": False,
    "AI_MAY_CREATE_EXECUTION_ORDER": False,
    "AI_MAY_INVENT_PRICE_TRIGGER": False,
    "AI_MAY_INVENT_POSITION_SIZE": False,
    "AI_MAY_INVENT_TARGET_PRICE": False,
    "AI_MAY_INVENT_PROBABILITY": False,
    "RESEARCH_STANCE_IS_NOT_EXECUTION_ORDER": True,
    "PRIORITY_NOW_IS_NOT_BUY_NOW": True,
    # Corrective technical pass-through seam: a numeric technical measurement is a research
    # observation, never an instruction, a stop, an execution eligibility grant, or PIT authority.
    "TECHNICAL_MEASUREMENT_IS_NOT_EXECUTION_INSTRUCTION": True,
    "PRICE_DERIVED_LEVEL_REQUIRES_BASIS_FITNESS_INTERPRETATION": True,
    "CURRENT_RESEARCH_MEASUREMENT_DOES_NOT_GRANT_PIT_AUTHORITY": True,
}

BLOCKED_OUTPUTS: dict[str, str] = {
    "target_price": "NOT_EMITTED",
    "probability_of_success": "FORECAST_PROHIBITED",
    "position_size": "NOT_EMITTED",
    "execution_eligibility": "NOT_EMITTED",
    "universal_score": "SCORING_PROHIBITED",
    "ordinal_rank": "RANKING_PROHIBITED",
}

PRIVACY_BOUNDARY: dict[str, str] = {
    "private_portfolio_positions": "NEVER_INCLUDED",
    "account_data": "NEVER_INCLUDED",
    "credentials": "NEVER_INCLUDED",
    "private_sizing": "NEVER_INCLUDED",
    "private_user_policy_limits": "NEVER_INCLUDED",
}

#: Corrected per CURRENT_RESEARCH_AI_HANDOFF_PACKET_V1_CORRECTIVE_TECHNICAL_PASS_THROUGH_AND_
#: RELEASE: RSI/MA/MACD/structure/momentum/relative-volume ARE produced and retained per current
#: session (tactical_momentum_context/v1, technical_structure_context/v2,
#: tactical_confirmation_context/v1) -- the earlier "not currently produced" claim for these
#: fields was wrong; they were simply not yet threaded through Workspace/Screener's own card
#: shape (PRODUCED_AND_RESEARCH_USABLE / NOT_EXPOSED_BY_OLD_WORKSPACE_SCREENER_JOIN, not
#: NOT_CURRENTLY_PRODUCED). Only ADX and MFI are genuinely absent from this repository.
TECHNICAL_FIELD_COVERAGE: dict[str, list[str]] = {
    "available_from_stocklookup": [
        "entry_state", "entry_action", "setup_tags", "close", "session_return_pct", "price_basis",
        "rsi_14", "rsi_zone_direction_cross_event", "rsi_divergence_confirmed_swing",
        "moving_average_20_50_100_200", "moving_average_price_above_below", "moving_average_slope",
        "moving_average_ordering", "macd_12_26_9", "price_direction_1d", "close_history_depth",
        "momentum_20d", "trend_state", "support_resistance_levels", "structure_status",
        "swing_structure_market_structure_state", "bos_choch_context", "breakout_context",
        "breakout_state_v3", "trigger_context", "invalidation_context", "pivot_context",
        "contraction_range_state", "self_relative_volatility_state",
        "relative_volume_provider_scoped_research_context", "tactical_confirmation_synthesis",
        "price_basis_feature_fitness_verdict", "market_wide_moving_average_participation",
        "market_wide_advance_decline_breadth", "market_wide_momentum_breadth",
    ],
    "not_currently_produced": [
        "adx", "mfi", "target_price", "position_size", "probability_of_success", "execution_eligibility",
    ],
}


class CurrentResearchAiHandoffPacketError(ValueError):
    """A required input contract or invariant of this packet is violated."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    """Content identity keyed off ``value``'s own ``contract_version`` -- not the module
    constant -- so the watchlist subset (``current_research_ai_handoff_watchlist/v1``) gets its
    own correctly-prefixed identity rather than borrowing the full packet's."""
    payload = {key: item for key, item in value.items() if key not in _IDENTITY_EXCLUDED}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    contract_version = value.get("contract_version") or CONTRACT_VERSION
    return {"artifact_sha256": digest, "artifact_identity": f"{contract_version}:{digest}"}


def _market_breadth_view(descriptive: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Pure pass-through of ``market_wide_current_descriptive_research/v1``'s own
    ``market_breadth`` block. No recomputation: every value is read directly."""
    if not isinstance(descriptive, Mapping):
        return None
    breadth = descriptive.get("market_breadth")
    if not isinstance(breadth, Mapping):
        return None
    trend = breadth.get("trend") or {}
    return {
        "session": descriptive.get("session"),
        "source_artifact_identity": descriptive.get("artifact_identity"),
        "ticker_denominator": breadth.get("current_active_equity_denominator"),
        "same_session_available_count": breadth.get("same_session_technical_feature_available_count"),
        "advancing": breadth.get("advancing"),
        "declining": breadth.get("declining"),
        "unchanged": breadth.get("unchanged"),
        "advance_ratio": breadth.get("advance_ratio"),
        "moving_average_participation": {
            "above_ma20": trend.get("above_ma20"),
            "at_or_below_ma20": trend.get("at_or_below_ma20"),
            "unavailable": trend.get("unavailable"),
        },
        "breadth_descriptor": breadth.get("breadth_descriptor"),
        "momentum_descriptor": breadth.get("momentum_descriptor"),
        "sector_breadth": descriptive.get("sector_breadth"),
        "authority_boundary": dict(breadth.get("authority_boundary") or {}),
    }


def _market_context(
    *, descriptive_current: Mapping[str, Any] | None, descriptive_previous: Mapping[str, Any] | None,
    previous_session: str | None,
) -> dict[str, Any]:
    """Two-session breadth snapshot -- deliberately never a single-session view -- so the AI
    consumer cannot infer a market-regime transition from one session alone. Deltas are computed
    only between two already-resolved numeric fields; no new descriptor/label is invented."""
    current_view = _market_breadth_view(descriptive_current)
    previous_view = _market_breadth_view(descriptive_previous)
    deltas: dict[str, Any] | None = None
    if current_view is not None and previous_view is not None:
        def _delta(key: str) -> float | int | None:
            a, b = current_view.get(key), previous_view.get(key)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
                return a - b
            return None

        deltas = {
            "advancing_delta": _delta("advancing"),
            "declining_delta": _delta("declining"),
            "unchanged_delta": _delta("unchanged"),
            "advance_ratio_delta": _delta("advance_ratio"),
            "above_ma20_delta": (
                current_view["moving_average_participation"]["above_ma20"] - previous_view["moving_average_participation"]["above_ma20"]
                if isinstance(current_view["moving_average_participation"]["above_ma20"], (int, float))
                and isinstance(previous_view["moving_average_participation"]["above_ma20"], (int, float))
                else None
            ),
        }
    return {
        "current_session_breadth": current_view or {"status": NOT_AVAILABLE, "reason": "NO_CURRENT_SESSION_DESCRIPTIVE_EVIDENCE"},
        "previous_governed_session": previous_session,
        "previous_governed_session_breadth": previous_view or {
            "status": NOT_AVAILABLE,
            "reason": "NO_PRIOR_GOVERNED_SESSION_DESCRIPTIVE_EVIDENCE" if previous_session else "NO_PRIOR_GOVERNED_SESSION",
        },
        "deterministic_deltas": deltas,
        "notice": (
            "Two independently governed sessions are shown explicitly so a single session's "
            "breadth is never read as a confirmed regime change. No new regime label is created "
            "here; breadth_descriptor/momentum_descriptor above already carry their own "
            "deterministic rule identity (market_regime_breadth_context/v1)."
        ),
    }


def _artifact_session(artifact: Mapping[str, Any] | None) -> str | None:
    if not isinstance(artifact, Mapping):
        return None
    return artifact.get("session") or artifact.get("target_session")


def _price_basis_fitness_view(
    *, ticker: str, session: str, price_basis: str | None, momentum_record: Mapping[str, Any] | None,
    momentum_identity: str | None,
) -> dict[str, Any]:
    """Reuse the existing, unmodified ``price_basis_feature_fitness`` evaluator to attach a
    genuine basis/fitness verdict to the numeric technical measurements below -- never a new
    compatibility rule, never a widened verdict. Only computed when there is a real eligible
    momentum record and a real observed price basis to reason about; otherwise explicit
    ``NOT_AVAILABLE`` rather than a fabricated context.

    The evaluator compares a "current" against a "history" price-series context; this module has
    only one retained context per session at this layer (no separate historical comparison
    series), so the same context is deliberately passed as both -- this yields a same-session,
    single-basis classification (typically ``BASIS_COMPATIBLE_RESEARCH_ONLY`` for the qualified
    ``ADJUSTED_RETROSPECTIVE``/``CURRENT_RETROSPECTIVE_ADJUSTED`` basis this repository already
    uses), not a cross-period PIT/backtest claim. ``feature`` is chosen from the module's own
    closed ``PRICE_DERIVED_FEATURES`` vocabulary; MACD has no exact match in that vocabulary and
    is deliberately noted as an approximate mapping rather than silently treated as exact.
    """
    eligible = isinstance(momentum_record, Mapping) and (momentum_record.get("eligibility") or {}).get("status") == "ELIGIBLE"
    if not eligible or not price_basis:
        return {
            "status": NOT_AVAILABLE,
            "reason": (
                "MOMENTUM_CONTEXT_TICKER_NOT_ELIGIBLE_THIS_SESSION" if not eligible
                else "NO_OBSERVED_PRICE_BASIS_AVAILABLE_FROM_SCREENER"
            ),
            "context": None, "rsi_fitness": None, "moving_average_fitness": None,
        }
    lineage = momentum_record.get("technical_history_lineage") if isinstance(momentum_record.get("technical_history_lineage"), Mapping) else {}
    provider = lineage.get("provider")
    source_identity = momentum_identity or lineage.get("recovery_artifact_identity")
    provenance = [str(item) for item in (lineage.get("source"), lineage.get("recovery_artifact_identity")) if item]
    context = price_basis_feature_fitness.price_series_context(
        ticker=ticker, provider=provider, source_identity=source_identity,
        session_start=session, session_end=session, observed_basis=str(price_basis),
        basis_provenance=provenance, basis_confidence="SOURCE_SCOPED_CURRENT_RESEARCH_ONLY",
        basis_lineage_identity=source_identity,
    )
    rsi_fitness = price_basis_feature_fitness.evaluate_feature_fitness(
        feature=price_basis_feature_fitness.RSI, current_context=context, history_context=context,
        decision_as_of=session,
    )
    ma_fitness = price_basis_feature_fitness.evaluate_feature_fitness(
        feature=price_basis_feature_fitness.MA20, current_context=context, history_context=context,
        decision_as_of=session,
    )
    return {
        "status": "AVAILABLE",
        "reason": None,
        "context": context,
        "rsi_fitness": rsi_fitness,
        "moving_average_fitness": ma_fitness,
        "macd_fitness_note": (
            "MACD has no exact entry in price_basis_feature_fitness.PRICE_DERIVED_FEATURES; the "
            "RSI/MA verdicts above -- built from the same observed price-basis context -- apply "
            "equally to MACD, which shares that same context, not a separately-evaluated verdict."
        ),
    }


def _technical_measurements_view(
    *, ticker: str, session: str, screener_card: Mapping[str, Any] | None,
    momentum_record: Mapping[str, Any] | None, momentum_identity: str | None, momentum_supplied: bool,
    structure_record: Mapping[str, Any] | None, structure_identity: str | None, structure_supplied: bool,
    confirmation_record: Mapping[str, Any] | None, confirmation_identity: str | None, confirmation_supplied: bool,
) -> dict[str, Any]:
    """Technical measurements: close/session-return (Screener's price view, as before) plus a
    verbatim pass-through of the real per-ticker ``tactical_momentum_context``/
    ``technical_structure_context``/``tactical_confirmation_context`` records when those optional
    axes are supplied to ``build_packet``. Every sub-field keeps the producing module's own
    status/reason exactly as retained -- a producer's own ``NOT_AVAILABLE``/``NOT_ELIGIBLE`` is
    never rewritten, and this module never fills a gap with a computed or invented value. When an
    axis is not supplied to this build at all, its block is explicitly ``NOT_AVAILABLE`` with
    ``AXIS_NOT_SUPPLIED_THIS_BUILD`` -- never silently omitted, never confused with the producer
    itself reporting no data for an ineligible ticker.
    """
    price = (screener_card or {}).get("price") if isinstance(screener_card, Mapping) else None
    price = price if isinstance(price, Mapping) else {}

    if not momentum_supplied:
        momentum_view: dict[str, Any] = {"status": NOT_AVAILABLE, "reason": "AXIS_NOT_SUPPLIED_THIS_BUILD"}
    elif not isinstance(momentum_record, Mapping):
        momentum_view = {"status": NOT_AVAILABLE, "reason": "TICKER_ABSENT_FROM_TACTICAL_MOMENTUM_CONTEXT"}
    else:
        momentum_view = {
            "status": "AVAILABLE",
            "eligibility": momentum_record.get("eligibility"),
            "close_history_depth": momentum_record.get("close_history_depth"),
            "price_direction_1d": momentum_record.get("price_direction_1d"),
            "rsi": momentum_record.get("rsi"),
            "rsi_divergence": momentum_record.get("rsi_divergence"),
            "moving_averages": momentum_record.get("moving_averages"),
            "moving_average_ordering": momentum_record.get("moving_average_ordering"),
            "macd": momentum_record.get("macd"),
            "technical_history_lineage": momentum_record.get("technical_history_lineage"),
            "authority_boundary": momentum_record.get("authority_boundary"),
            "source_artifact_identity": momentum_identity,
        }

    if not structure_supplied:
        structure_view: dict[str, Any] = {"status": NOT_AVAILABLE, "reason": "AXIS_NOT_SUPPLIED_THIS_BUILD"}
    elif not isinstance(structure_record, Mapping):
        structure_view = {"status": NOT_AVAILABLE, "reason": "TICKER_ABSENT_FROM_TECHNICAL_STRUCTURE_CONTEXT"}
    else:
        structure_view = {
            "status": "AVAILABLE",
            "eligibility": structure_record.get("eligibility"),
            "authority_tier": structure_record.get("authority_tier"),
            "trend_context": structure_record.get("trend_context"),
            "structure_context": structure_record.get("structure_context"),
            "contraction_context": structure_record.get("contraction_context"),
            "relative_volume": structure_record.get("relative_volume"),
            "swing_structure": structure_record.get("swing_structure"),
            "bos_context": structure_record.get("bos_context"),
            "choch_context": structure_record.get("choch_context"),
            "breakout_context": structure_record.get("breakout_context"),
            "breakout_state_v3": structure_record.get("breakout_state_v3"),
            "trigger_context": structure_record.get("trigger_context"),
            "invalidation_context": structure_record.get("invalidation_context"),
            "pivot_context": structure_record.get("pivot_context"),
            "high_low_basis": structure_record.get("high_low_basis"),
            "blockers": list(structure_record.get("blockers") or []),
            "authority_boundary": structure_record.get("authority_boundary"),
            "source_artifact_identity": structure_identity,
        }

    if not confirmation_supplied:
        confirmation_view: dict[str, Any] = {"status": NOT_AVAILABLE, "reason": "AXIS_NOT_SUPPLIED_THIS_BUILD"}
    elif not isinstance(confirmation_record, Mapping):
        confirmation_view = {"status": NOT_AVAILABLE, "reason": "TICKER_ABSENT_FROM_TACTICAL_CONFIRMATION_CONTEXT"}
    else:
        confirmation_view = {
            "status": "AVAILABLE",
            "tactical_confirmation_state": confirmation_record.get("tactical_confirmation_state"),
            "structure_stance": confirmation_record.get("structure_stance"),
            "structure_phase_label": confirmation_record.get("structure_phase_label"),
            "momentum_direction": confirmation_record.get("momentum_direction"),
            "participation_detail": confirmation_record.get("participation_detail"),
            "price_direction_1d": confirmation_record.get("price_direction_1d"),
            "supporting_reasons": list(confirmation_record.get("supporting_reasons") or []),
            "contradicting_reasons": list(confirmation_record.get("contradicting_reasons") or []),
            "authority_boundary": confirmation_record.get("authority_boundary"),
            "source_artifact_identity": confirmation_identity,
        }

    return {
        "close": price.get("value"),
        "close_status": price.get("status"),
        "close_reason": price.get("reason"),
        "session_return_pct": price.get("change_pct"),
        "session_return_pct_unit": price.get("change_pct_unit"),
        "session_return_pct_status": price.get("change_pct_status"),
        "price_basis": price.get("basis"),
        "price_as_of": price.get("as_of"),
        "momentum": momentum_view,
        "structure": structure_view,
        "confirmation_synthesis": confirmation_view,
        "price_basis_fitness": _price_basis_fitness_view(
            ticker=ticker, session=session, price_basis=price.get("basis"),
            momentum_record=momentum_record if momentum_supplied else None, momentum_identity=momentum_identity,
        ),
        "not_available_reason": (
            None if (momentum_supplied or structure_supplied or confirmation_supplied) else
            "NO_TECHNICAL_PRODUCER_AXIS_SUPPLIED_TO_THIS_BUILD -- tactical_momentum_context/"
            "technical_structure_context/tactical_confirmation_context were not passed to "
            "build_packet; only Screener's own close/session_return are available."
        ),
    }


def _unknown_scope_view(reason: str) -> dict[str, Any]:
    scope_mod = current_research_official_universe_scope_module
    return {
        "scope_bucket": scope_mod.SIMPLE_SCOPE_UNKNOWN,
        "current_research_scope_state": None,
        "current_research_scope_fitness": None,
        "current_research_scope_reason": reason,
        "official_current_exchange_presence": None,
        "official_security_status": None,
        "research_session": None,
        "official_snapshot_observed_at": None,
    }


def build_card(
    *,
    ticker: str,
    session: str,
    workspace_card: Mapping[str, Any] | None,
    screener_card: Mapping[str, Any] | None,
    current_research_scope: Mapping[str, Any] | None,
    workspace_identity: str | None,
    screener_identity: str | None,
    momentum_record: Mapping[str, Any] | None = None,
    momentum_identity: str | None = None,
    momentum_supplied: bool = False,
    structure_record: Mapping[str, Any] | None = None,
    structure_identity: str | None = None,
    structure_supplied: bool = False,
    confirmation_record: Mapping[str, Any] | None = None,
    confirmation_identity: str | None = None,
    confirmation_supplied: bool = False,
) -> dict[str, Any]:
    """Compose one AI-consumer card from already-built Workspace/Screener cards for ``ticker``,
    plus (when supplied) the real per-ticker technical-producer records.

    Never reads Workspace's own ``portfolio`` section (private-position context) -- this module
    has no private-portfolio input in scope at all, so there is nothing to accidentally leak.
    Never computes a new field; every value below traces to an existing Workspace/Screener card
    field, an existing technical-producer record field, or is an explicit ``NOT_AVAILABLE``."""
    if workspace_card is None and screener_card is None:
        return {
            "ticker": ticker,
            "coverage_status": NOT_COVERED,
            "reason": "TICKER_ABSENT_FROM_BOTH_WORKSPACE_AND_SCREENER_THIS_SESSION",
            "official_research_scope": _unknown_scope_view("TICKER_NOT_COVERED_BY_CURRENT_PRODUCTS"),
            "blocked_outputs": dict(BLOCKED_OUTPUTS),
            "authority_boundary": dict(AI_BOUNDARY),
        }

    w = workspace_card if isinstance(workspace_card, Mapping) else {}
    s = screener_card if isinstance(screener_card, Mapping) else {}
    fundamental = w.get("fundamental") if isinstance(w.get("fundamental"), Mapping) else {}
    valuation = w.get("valuation") if isinstance(w.get("valuation"), Mapping) else {}
    tactical_state = w.get("tactical") if isinstance(w.get("tactical"), Mapping) else {}
    market_sector = w.get("market_sector") if isinstance(w.get("market_sector"), Mapping) else {}
    catalyst = w.get("catalyst") if isinstance(w.get("catalyst"), Mapping) else {}
    liquidity = w.get("liquidity") if isinstance(w.get("liquidity"), Mapping) else {}
    why = w.get("why") if isinstance(w.get("why"), Mapping) else {}
    counter_thesis = w.get("counter_thesis") if isinstance(w.get("counter_thesis"), Mapping) else {}
    lineage = w.get("lineage") if isinstance(w.get("lineage"), Mapping) else {}
    sector_view = s.get("sector") if isinstance(s.get("sector"), Mapping) else {}
    entity_view = s.get("entity_type") if isinstance(s.get("entity_type"), Mapping) else {}
    execution_view = s.get("execution") if isinstance(s.get("execution"), Mapping) else {}
    financial_v2 = s.get("financial_v2") if isinstance(s.get("financial_v2"), Mapping) else {}

    scope_mod = current_research_official_universe_scope_module

    return {
        "ticker": ticker,
        "coverage_status": "COVERED",
        "identity": {
            "ticker": ticker,
            "sector": sector_view.get("label"),
            "sector_status": sector_view.get("status"),
            "entity_class": entity_view.get("value"),
            "entity_class_status": entity_view.get("status"),
            "display_exchange": s.get("display_exchange"),
            "listing_exchange": s.get("listing_exchange"),
            "as_of_session": w.get("as_of_session"),
            "data_availability": {
                "workspace_covered": workspace_card is not None,
                "screener_covered": screener_card is not None,
            },
        },
        "decision_context": {
            "research_stance": w.get("research_stance"),
            "research_stance_readiness": w.get("research_stance_readiness"),
            "entry_state": w.get("entry_state"),
            "entry_action": w.get("entry_action"),
            "setup_tags": list(w.get("setup_tags") or []),
        },
        "fundamental": {
            "state": fundamental.get("state"),
            "trajectory": fundamental.get("trajectory"),
            "readiness": fundamental.get("readiness"),
            "research_fitness": fundamental.get("research_fitness"),
            "freshness_status": fundamental.get("freshness_status"),
            "source_period": fundamental.get("source_period"),
            "financial_v2_status": financial_v2.get("status"),
            "financial_v2_fitness": financial_v2.get("fitness"),
            "financial_v2_current_research_ready": financial_v2.get("current_research_ready"),
        },
        "valuation": dict(valuation),
        "tactical": {
            "entry_state": tactical_state.get("primary_entry_state"),
            "entry_action": tactical_state.get("entry_action"),
            "setup_tags": list(tactical_state.get("setup_tags") or []),
            "freshness_status": tactical_state.get("freshness_status"),
            "source_session": tactical_state.get("source_session"),
            "measurements": _technical_measurements_view(
                ticker=ticker, session=session, screener_card=s,
                momentum_record=momentum_record, momentum_identity=momentum_identity, momentum_supplied=momentum_supplied,
                structure_record=structure_record, structure_identity=structure_identity, structure_supplied=structure_supplied,
                confirmation_record=confirmation_record, confirmation_identity=confirmation_identity, confirmation_supplied=confirmation_supplied,
            ),
        },
        "market_sector": {
            "breadth_regime": market_sector.get("breadth_regime"),
            "sector_relative_context": market_sector.get("sector_relative_context"),
            "freshness_status": market_sector.get("freshness_status"),
        },
        "catalyst": {
            "status": catalyst.get("status"),
            "qualified_current_catalysts": list(catalyst.get("qualified_current_catalysts") or []),
            "pending_watch_items": list(catalyst.get("pending_watch_items") or []),
            "event_count": catalyst.get("event_count"),
            "freshness_status": catalyst.get("freshness_status"),
            "source_session": catalyst.get("source_session"),
        },
        "liquidity": {
            "readiness": liquidity.get("readiness"),
            "descriptive_research_state": liquidity.get("descriptive_research_state"),
            "exact_execution_capacity_status": (
                liquidity.get("exact_execution_capacity_status")
                or execution_view.get("capacity_exact_status")
            ),
            "freshness_status": liquidity.get("freshness_status"),
            "source_session": liquidity.get("source_session"),
        },
        "thesis": {
            "deterministic_reasons": list(why.get("deterministic_reasons") or []),
            "financial_analysis": why.get("financial_analysis"),
            "counterbalancing_context": list(why.get("counterbalancing_context") or []),
        },
        "counter_thesis": {
            "warnings": list(counter_thesis.get("warnings") or []),
            "key_counter_thesis": list(counter_thesis.get("key_counter_thesis") or []),
            "financial_analysis": counter_thesis.get("financial_analysis"),
            "unavailable_dimensions": list(counter_thesis.get("unavailable_dimensions") or []),
        },
        "confirmation": dict(w.get("confirmation") or {"status": "UNAVAILABLE"}),
        "invalidation": dict(w.get("invalidation") or {"status": "UNAVAILABLE"}),
        "provenance": {
            "per_axis_source_session": dict(lineage.get("per_axis_source_session") or {}),
            "per_axis_freshness": dict(lineage.get("per_axis_freshness") or {}),
            "per_axis_proxy_or_qualified_state": dict(lineage.get("per_axis_proxy_or_qualified_state") or {}),
            "blockers": list(lineage.get("blockers") or []),
            "workspace_source_artifact_identity": workspace_identity,
            "screener_source_artifact_identity": screener_identity,
        },
        "official_research_scope": (
            current_research_official_universe_scope_module.ticker_scope_view(current_research_scope, ticker)
            if current_research_scope is not None
            else _unknown_scope_view("CURRENT_OFFICIAL_SCOPE_NOT_SUPPLIED")
        ),
        "blocked_outputs": dict(BLOCKED_OUTPUTS),
        "authority_boundary": dict(AI_BOUNDARY),
    }


def build_packet(
    *,
    session: str,
    requested_at: str,
    producer_commit: str | None,
    daily_operation_identity: str | None,
    workspace_artifact: Mapping[str, Any],
    screener_artifact: Mapping[str, Any],
    descriptive_current: Mapping[str, Any] | None = None,
    descriptive_previous: Mapping[str, Any] | None = None,
    previous_session: str | None = None,
    current_research_scope: Mapping[str, Any] | None = None,
    momentum_context_artifact: Mapping[str, Any] | None = None,
    structure_context_artifact: Mapping[str, Any] | None = None,
    confirmation_context_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build ``current_research_ai_handoff_packet/v1`` over the union of Workspace and Screener
    ticker sets -- never their intersection, so a ticker present in only one product is still
    surfaced (with its own ``data_availability`` flags) rather than silently dropped.

    ``workspace_artifact``/``screener_artifact`` must be the real, already-materialized
    ``investment_decision_workspace_projection/v1`` / ``screener_master_projection/v1``
    artifacts for the same ``session`` -- this function never rebuilds them. ``current_research_
    scope`` (optional) must be the return value of ``current_research_official_universe_scope.
    resolve_scope`` (typically via ``canonical_current_product_projections.resolve_current_
    research_official_universe_scope``); omitted, every card's ``official_research_scope``
    degrades to an explicit unknown state, never a fabricated bucket.

    ``momentum_context_artifact``/``structure_context_artifact``/``confirmation_context_artifact``
    (all optional) are the real, already-materialized ``tactical_momentum_context/v1`` /
    ``technical_structure_context/v1`` or ``/v2`` / ``tactical_confirmation_context/v1``
    artifacts for the same ``session`` -- resolved by the caller via the existing deterministic
    ``daily_session_level2_package.session_artifact_paths()`` path contract, never a search. Any
    of the three may be omitted independently (e.g. a caller with only Workspace/Screener on
    hand); an omitted axis degrades every card's corresponding technical block to an explicit
    ``NOT_AVAILABLE`` with ``AXIS_NOT_SUPPLIED_THIS_BUILD``, never silently absent and never
    substituted with a computed value. Session mismatch on a *supplied* axis fails closed.
    """
    if workspace_artifact.get("contract_version") != "investment_decision_workspace_projection/v1":
        raise CurrentResearchAiHandoffPacketError("WORKSPACE_CONTRACT_UNSUPPORTED")
    if screener_artifact.get("contract_version") != "screener_master_projection/v1":
        raise CurrentResearchAiHandoffPacketError("SCREENER_CONTRACT_UNSUPPORTED")
    if workspace_artifact.get("as_of_session") != session:
        raise CurrentResearchAiHandoffPacketError("WORKSPACE_SESSION_MISMATCH")
    if screener_artifact.get("as_of_session") != session:
        raise CurrentResearchAiHandoffPacketError("SCREENER_SESSION_MISMATCH")

    momentum_supplied = momentum_context_artifact is not None
    if momentum_supplied:
        if momentum_context_artifact.get("contract_version") != "tactical_momentum_context/v1":
            raise CurrentResearchAiHandoffPacketError("MOMENTUM_CONTEXT_CONTRACT_UNSUPPORTED")
        if _artifact_session(momentum_context_artifact) != session:
            raise CurrentResearchAiHandoffPacketError("MOMENTUM_CONTEXT_SESSION_MISMATCH")
    momentum_records = momentum_context_artifact.get("records") if momentum_supplied else None
    momentum_records = momentum_records if isinstance(momentum_records, Mapping) else {}
    momentum_identity = momentum_context_artifact.get("artifact_identity") if momentum_supplied else None

    structure_supplied = structure_context_artifact is not None
    if structure_supplied:
        if structure_context_artifact.get("contract_version") not in ("technical_structure_context/v1", "technical_structure_context/v2"):
            raise CurrentResearchAiHandoffPacketError("STRUCTURE_CONTEXT_CONTRACT_UNSUPPORTED")
        if _artifact_session(structure_context_artifact) != session:
            raise CurrentResearchAiHandoffPacketError("STRUCTURE_CONTEXT_SESSION_MISMATCH")
    structure_records = structure_context_artifact.get("records") if structure_supplied else None
    structure_records = structure_records if isinstance(structure_records, Mapping) else {}
    structure_identity = structure_context_artifact.get("artifact_identity") if structure_supplied else None

    confirmation_supplied = confirmation_context_artifact is not None
    if confirmation_supplied:
        if confirmation_context_artifact.get("contract_version") != "tactical_confirmation_context/v1":
            raise CurrentResearchAiHandoffPacketError("CONFIRMATION_CONTEXT_CONTRACT_UNSUPPORTED")
        if _artifact_session(confirmation_context_artifact) != session:
            raise CurrentResearchAiHandoffPacketError("CONFIRMATION_CONTEXT_SESSION_MISMATCH")
    confirmation_records = confirmation_context_artifact.get("records") if confirmation_supplied else None
    confirmation_records = confirmation_records if isinstance(confirmation_records, Mapping) else {}
    confirmation_identity = confirmation_context_artifact.get("artifact_identity") if confirmation_supplied else None

    workspace_cards = workspace_artifact.get("cards")
    screener_cards = screener_artifact.get("cards")
    if not isinstance(workspace_cards, Mapping) or not isinstance(screener_cards, Mapping):
        raise CurrentResearchAiHandoffPacketError("SOURCE_CARDS_INVALID")

    tickers = sorted(set(workspace_cards) | set(screener_cards))
    if not tickers:
        raise CurrentResearchAiHandoffPacketError("EMPTY_PACKET_DENOMINATOR")

    workspace_identity = workspace_artifact.get("artifact_identity")
    screener_identity = screener_artifact.get("artifact_identity")

    cards: dict[str, Any] = {}
    for ticker in tickers:
        cards[ticker] = build_card(
            ticker=ticker,
            session=session,
            workspace_card=workspace_cards.get(ticker),
            screener_card=screener_cards.get(ticker),
            current_research_scope=current_research_scope,
            workspace_identity=workspace_identity if ticker in workspace_cards else None,
            screener_identity=screener_identity if ticker in screener_cards else None,
            momentum_record=momentum_records.get(ticker), momentum_identity=momentum_identity, momentum_supplied=momentum_supplied,
            structure_record=structure_records.get(ticker), structure_identity=structure_identity, structure_supplied=structure_supplied,
            confirmation_record=confirmation_records.get(ticker), confirmation_identity=confirmation_identity, confirmation_supplied=confirmation_supplied,
        )
    if set(cards) != set(tickers):
        raise CurrentResearchAiHandoffPacketError("SILENT_TICKER_DROP")

    scope_mod = current_research_official_universe_scope_module
    in_scope = sum(1 for card in cards.values() if card["official_research_scope"]["scope_bucket"] == scope_mod.SIMPLE_IN_SCOPE)
    outside_scope = sum(1 for card in cards.values() if card["official_research_scope"]["scope_bucket"] == scope_mod.SIMPLE_OUTSIDE_SCOPE)
    unknown_scope = len(cards) - in_scope - outside_scope

    coverage = {
        "reference_denominator": len(cards),
        "workspace_denominator": len(workspace_cards),
        "screener_denominator": len(screener_cards),
        "workspace_and_screener_both_covered_count": sum(1 for t in tickers if t in workspace_cards and t in screener_cards),
        "workspace_only_count": sum(1 for t in tickers if t in workspace_cards and t not in screener_cards),
        "screener_only_count": sum(1 for t in tickers if t not in workspace_cards and t in screener_cards),
        "zero_silent_ticker_drops": True,
        "current_research_scope_supplied": current_research_scope is not None,
        "current_research_scope_applied": bool(
            isinstance(current_research_scope, Mapping) and current_research_scope.get("temporally_eligible")
        ),
        "current_official_research_scope_count": in_scope,
        "outside_current_official_research_scope_count": outside_scope,
        "current_official_research_scope_unknown_count": unknown_scope,
        "momentum_context_supplied": momentum_supplied,
        "momentum_eligible_count": sum(
            1 for card in cards.values()
            if (card.get("tactical", {}).get("measurements", {}).get("momentum", {}).get("eligibility") or {}).get("status") == "ELIGIBLE"
        ),
        "structure_context_supplied": structure_supplied,
        "structure_eligible_count": sum(
            1 for card in cards.values()
            if (card.get("tactical", {}).get("measurements", {}).get("structure", {}).get("eligibility") or {}).get("status") == "ELIGIBLE"
        ),
        "confirmation_context_supplied": confirmation_supplied,
        "confirmation_evaluated_count": sum(
            1 for card in cards.values()
            if card.get("tactical", {}).get("measurements", {}).get("confirmation_synthesis", {}).get("tactical_confirmation_state")
            not in (None, "INSUFFICIENT_EVIDENCE")
        ),
    }

    source_artifacts = {
        "investment_decision_workspace": workspace_identity,
        "screener_master_projection": screener_identity,
        "market_wide_current_descriptive_research_current": (
            descriptive_current.get("artifact_identity") if isinstance(descriptive_current, Mapping) else None
        ),
        "market_wide_current_descriptive_research_previous": (
            descriptive_previous.get("artifact_identity") if isinstance(descriptive_previous, Mapping) else None
        ),
        "tactical_momentum_context": momentum_identity,
        "technical_structure_context": structure_identity,
        "tactical_confirmation_context": confirmation_identity,
        "current_research_official_universe_scope": (
            {
                "research_session": current_research_scope.get("research_session"),
                "official_snapshot_observed_at": current_research_scope.get("official_snapshot_observed_at"),
            }
            if current_research_scope is not None else None
        ),
    }

    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "as_of_session": session,
        "requested_at": requested_at,
        "producer_commit": producer_commit,
        "daily_operation_identity": daily_operation_identity,
        "source_artifacts": source_artifacts,
        "market_context": _market_context(
            descriptive_current=descriptive_current, descriptive_previous=descriptive_previous,
            previous_session=previous_session,
        ),
        "coverage": coverage,
        "cards": cards,
        "technical_field_coverage": {key: list(value) for key, value in TECHNICAL_FIELD_COVERAGE.items()},
        "blocked_outputs": dict(BLOCKED_OUTPUTS),
        "privacy_boundary": dict(PRIVACY_BOUNDARY),
        "authority_boundary": dict(AI_BOUNDARY),
        "authority_effect": "AI_RESEARCH_TRANSPORT_AND_FITNESS_FOR_USE_ONLY / NO_NEW_MARKET_DATA_PIT_LIQUIDITY_SIZING_EXECUTION_RECOMMENDATION_AUTHORITY",
        "portable": True,
    }
    packet.update(content_identity(packet))
    return packet


def build_watchlist_subset(packet: Mapping[str, Any], tickers: Sequence[str]) -> dict[str, Any]:
    """Deterministic subset projection of a ``current_research_ai_handoff_packet/v1`` for
    explicit ticker selection. Never recomputes analytical fields (every card is copied verbatim
    from ``packet``), never silently drops a requested ticker (a ticker outside the packet's own
    denominator is included with an explicit ``NOT_COVERED_BY_CURRENT_PRODUCTS`` status, never
    omitted), and preserves ``source_artifacts``/``market_context`` unchanged."""
    if packet.get("contract_version") != CONTRACT_VERSION:
        raise CurrentResearchAiHandoffPacketError("PACKET_CONTRACT_UNSUPPORTED")

    requested: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        ticker = str(raw).strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        requested.append(ticker)
    if not requested:
        raise CurrentResearchAiHandoffPacketError("EMPTY_WATCHLIST_REQUEST")

    full_cards = packet.get("cards")
    if not isinstance(full_cards, Mapping):
        raise CurrentResearchAiHandoffPacketError("SOURCE_PACKET_CARDS_INVALID")

    cards: dict[str, Any] = {}
    for ticker in requested:
        if ticker in full_cards:
            cards[ticker] = full_cards[ticker]
        else:
            cards[ticker] = {
                "ticker": ticker,
                "coverage_status": NOT_COVERED,
                "reason": "TICKER_NOT_IN_SOURCE_PACKET_REFERENCE_DENOMINATOR",
                "official_research_scope": _unknown_scope_view("TICKER_NOT_COVERED_BY_CURRENT_PRODUCTS"),
                "blocked_outputs": dict(BLOCKED_OUTPUTS),
                "authority_boundary": dict(AI_BOUNDARY),
            }
    if set(cards) != set(requested):
        raise CurrentResearchAiHandoffPacketError("WATCHLIST_SILENT_TICKER_DROP")

    subset: dict[str, Any] = {
        "schema_version": packet.get("schema_version"),
        "contract_version": WATCHLIST_CONTRACT_VERSION,
        "milestone": MILESTONE,
        "as_of_session": packet.get("as_of_session"),
        "requested_at": packet.get("requested_at"),
        "producer_commit": packet.get("producer_commit"),
        "daily_operation_identity": packet.get("daily_operation_identity"),
        "source_artifacts": dict(packet.get("source_artifacts") or {}),
        "source_packet_identity": packet.get("artifact_identity"),
        "market_context": packet.get("market_context"),
        "requested_tickers": requested,
        "coverage": {
            "requested_count": len(requested),
            "covered_count": sum(1 for t in requested if t in full_cards),
            "not_covered_count": sum(1 for t in requested if t not in full_cards),
            "zero_silent_ticker_drops": True,
        },
        "cards": cards,
        "technical_field_coverage": dict(packet.get("technical_field_coverage") or {}),
        "blocked_outputs": dict(BLOCKED_OUTPUTS),
        "privacy_boundary": dict(PRIVACY_BOUNDARY),
        "authority_boundary": dict(AI_BOUNDARY),
        "authority_effect": packet.get("authority_effect"),
        "portable": True,
    }
    subset.update(content_identity(subset))
    return subset
