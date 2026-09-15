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
Screener, market-wide descriptive research, official-universe scope) -> already-computed by
those modules -> this packet. This module performs ZERO new analysis: every field is either a
direct pass-through of an already-built Workspace/Screener card field, or an explicit
``NOT_AVAILABLE`` when Stock Lookup genuinely does not produce that measurement today (see
``_tactical_measurement_view``). It never computes RSI/ADX/MFI, never derives a target price,
probability, position size, or execution level, and never reads private portfolio/account state
(Workspace's own ``portfolio`` section, which is private-position context, is deliberately never
read by this module -- see ``build_card``).

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

TECHNICAL_FIELD_COVERAGE: dict[str, list[str]] = {
    "available_from_stocklookup": [
        "entry_state", "entry_action", "setup_tags", "close", "session_return_pct",
        "price_basis", "market_wide_moving_average_participation",
        "market_wide_advance_decline_breadth", "market_wide_momentum_breadth",
    ],
    "not_currently_produced": [
        "per_ticker_moving_average_value", "per_ticker_momentum_value",
        "per_ticker_volatility_value", "per_ticker_relative_volume_value",
        "per_ticker_rsi_adx_mfi", "deterministic_technical_structure_pattern_detail",
        "target_price", "position_size", "probability_of_success", "execution_eligibility",
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


def _tactical_measurement_view(screener_card: Mapping[str, Any] | None) -> dict[str, Any]:
    """Numeric technical measurements genuinely available at the per-ticker join today (close,
    session return, price basis, from Screener's price view) vs. what is honestly not produced.
    Never computes RSI/ADX/MFI or any other indicator not already an existing artifact field."""
    price = (screener_card or {}).get("price") if isinstance(screener_card, Mapping) else None
    price = price if isinstance(price, Mapping) else {}
    return {
        "close": price.get("value"),
        "close_status": price.get("status"),
        "close_reason": price.get("reason"),
        "session_return_pct": price.get("change_pct"),
        "session_return_pct_unit": price.get("change_pct_unit"),
        "session_return_pct_status": price.get("change_pct_status"),
        "price_basis": price.get("basis"),
        "price_as_of": price.get("as_of"),
        "moving_average_value": NOT_AVAILABLE,
        "momentum_value": NOT_AVAILABLE,
        "volatility_value": NOT_AVAILABLE,
        "relative_volume_value": NOT_AVAILABLE,
        "deterministic_technical_structure_detail": NOT_AVAILABLE,
        "not_available_reason": (
            "STOCK_LOOKUP_DOES_NOT_PRODUCE_A_PER_TICKER_MOVING_AVERAGE_MOMENTUM_VOLATILITY_OR_"
            "RELATIVE_VOLUME_JOIN_IN_WORKSPACE_OR_SCREENER_TODAY -- market-wide cross-sectional "
            "aggregates exist (see market_context), never substituted here for a missing "
            "per-ticker measurement."
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
    workspace_card: Mapping[str, Any] | None,
    screener_card: Mapping[str, Any] | None,
    current_research_scope: Mapping[str, Any] | None,
    workspace_identity: str | None,
    screener_identity: str | None,
) -> dict[str, Any]:
    """Compose one AI-consumer card from already-built Workspace/Screener cards for ``ticker``.

    Never reads Workspace's own ``portfolio`` section (private-position context) -- this module
    has no private-portfolio input in scope at all, so there is nothing to accidentally leak.
    Never computes a new field; every value below traces to an existing Workspace/Screener card
    field or is an explicit ``NOT_AVAILABLE``."""
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
            "measurements": _tactical_measurement_view(s),
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
    """
    if workspace_artifact.get("contract_version") != "investment_decision_workspace_projection/v1":
        raise CurrentResearchAiHandoffPacketError("WORKSPACE_CONTRACT_UNSUPPORTED")
    if screener_artifact.get("contract_version") != "screener_master_projection/v1":
        raise CurrentResearchAiHandoffPacketError("SCREENER_CONTRACT_UNSUPPORTED")
    if workspace_artifact.get("as_of_session") != session:
        raise CurrentResearchAiHandoffPacketError("WORKSPACE_SESSION_MISMATCH")
    if screener_artifact.get("as_of_session") != session:
        raise CurrentResearchAiHandoffPacketError("SCREENER_SESSION_MISMATCH")

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
            workspace_card=workspace_cards.get(ticker),
            screener_card=screener_cards.get(ticker),
            current_research_scope=current_research_scope,
            workspace_identity=workspace_identity if ticker in workspace_cards else None,
            screener_identity=screener_identity if ticker in screener_cards else None,
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
