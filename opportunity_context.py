"""Market-wide opportunity_context/v1: interpretable per-axis current research join.

Preserves separate axes. No opaque total score, rank, or probability of success.
A stale axis is localized and never globally blocks the ticker.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from current_corporate_event_context import CONFIRMED_RECENT, CONFIRMED_UPCOMING, PLANNED_NOT_EXECUTED
from current_research_valuation_context import evaluate_ticker_valuation, valuation_axis
from opportunity_axis_freshness import STALE_BUT_RESEARCH_USABLE, axis_is_research_usable, classify_axis_freshness
from watchlist_tactical_entry_classifier import ENTRY_ACTION_BY_ENTRY_STATE

CONTRACT_VERSION = "opportunity_context/v1"
CONFIRMED = "CONFIRMED"
PLANNED_PENDING = "PLANNED_PENDING"
WATCH_FOR_EXECUTION = "WATCH_FOR_EXECUTION"
CATALYST_UNAVAILABLE = "UNAVAILABLE"
MAJOR_AXES = (
    "fundamental", "valuation", "tactical", "market_sector", "catalyst", "downside_invalidation", "liquidity",
)
READY_FEATURE = frozenset({"READY_RESEARCH", "READY_RESEARCH_PROXY", "PARTIAL_RESEARCH"})


def _records(artifact: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(artifact, Mapping):
        return {}
    records = artifact.get("records")
    return records if isinstance(records, Mapping) else {}


def _session(artifact: Mapping[str, Any] | None, *keys: str) -> str | None:
    if not isinstance(artifact, Mapping):
        return None
    for key in keys:
        value = artifact.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _feature_context(record: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return (record or {}).get("fundamental_feature_context") or {}


def _feature(record: Mapping[str, Any] | None, feature_id: str) -> Mapping[str, Any]:
    return (_feature_context(record).get("current_features") or {}).get(feature_id) or {}


def _catalyst_status(events: list[Mapping[str, Any]], thesis: Mapping[str, Any] | None) -> str:
    if thesis and thesis.get("catalysts"):
        return CONFIRMED
    statuses = {event.get("event_status") for event in events}
    if statuses & {CONFIRMED_UPCOMING, CONFIRMED_RECENT}:
        return CONFIRMED
    if PLANNED_NOT_EXECUTED in statuses:
        return PLANNED_PENDING
    if events:
        return WATCH_FOR_EXECUTION
    if thesis and thesis.get("retained_event_context"):
        return WATCH_FOR_EXECUTION
    return CATALYST_UNAVAILABLE


def _map_event_status(status: str | None) -> str:
    if status in {CONFIRMED_UPCOMING, CONFIRMED_RECENT}:
        return CONFIRMED
    if status == PLANNED_NOT_EXECUTED:
        return PLANNED_PENDING
    if status:
        return WATCH_FOR_EXECUTION
    return CATALYST_UNAVAILABLE


def _portfolio_availability(portfolio: Mapping[str, Any] | None, freshness: Mapping[str, Any]) -> str:
    if not isinstance(portfolio, Mapping) or not portfolio.get("portfolio_id"):
        return "NOT_PROVIDED"
    if freshness.get("freshness_status") == STALE_BUT_RESEARCH_USABLE:
        return "STALE"
    if freshness.get("freshness_status") == CURRENT:
        return "AVAILABLE"
    if freshness.get("freshness_status") == UNAVAILABLE:
        return "NOT_PROVIDED"
    return "NOT_APPLICABLE"


def _liquidity_row(record: Mapping[str, Any] | None, *, session: str | None,
                   source_identity: str | None, decision_session: str) -> dict[str, Any]:
    record = record or {}
    contract = record.get("liquidity_research_contract") or {}
    current = ((contract.get("CURRENT_SESSION_LIQUIDITY_RESEARCH") or {}).get("state")
               or record.get("research_proxy_status"))
    eligible = current in {"ELIGIBLE", "LIQUIDITY_RESEARCH_PROXY"} or record.get("disposition") == "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE"
    volume = record.get("current_ohlc_v")
    if volume is None:
        volume = record.get("current_session_volume")
    execution = ((contract.get("EXECUTION_CAPACITY") or {}).get("state")
                 or record.get("exact_execution_capacity_status") or "BLOCKED")
    exact_blocked = execution not in {"ELIGIBLE", "EXECUTION_CAPACITY_EXACT_READY"}
    source_session = record.get("session") or session
    freshness = classify_axis_freshness(
        axis="liquidity", decision_session=decision_session, source_session=source_session,
        source_artifact_identity=source_identity,
    )
    ready = axis_is_research_usable(freshness) and (eligible or isinstance(volume, (int, float)))
    return {
        "readiness": "LIQUIDITY_RESEARCH_PROXY" if ready else "LIQUIDITY_RESEARCH_UNAVAILABLE",
        "descriptive_research_state": record.get("disposition") or ("AVAILABLE" if ready else "UNAVAILABLE"),
        "exact_execution_capacity_status": "EXECUTION_CAPACITY_EXACT_BLOCKED" if exact_blocked else "EXECUTION_CAPACITY_EXACT_READY",
        "current_session_volume": volume if isinstance(volume, (int, float)) else None,
        "freshness": freshness,
        "research_usable": ready,
        "authority_boundary": "RESEARCH_PROXY_ONLY_NOT_EXECUTION_SIZING",
    }


def _fundamental_axis(*, record: Mapping[str, Any] | None, peers: Mapping[str, Any] | None,
                      decision_session: str, source_identity: str | None) -> dict[str, Any]:
    context = _feature_context(record)
    profit = _feature(record, "profit_state")
    growth = _feature(record, "net_income_same_period_yoy")
    periods = [period for feature in (context.get("current_features") or {}).values()
               for period in (feature.get("input_periods") or [])]
    latest_period = max(periods) if periods else None
    freshness = classify_axis_freshness(
        axis="fundamental", decision_session=decision_session, source_session=None,
        source_period=latest_period, source_artifact_identity=source_identity,
    )
    ready_count = context.get("ready_feature_count") or 0
    availability = context.get("availability")
    if not record:
        freshness = classify_axis_freshness(
            axis="fundamental", decision_session=decision_session, source_session=None,
            source_artifact_identity=source_identity,
        )
        return {
            "readiness": "UNAVAILABLE", "state": "UNAVAILABLE", "trajectory": "UNAVAILABLE",
            "financial_health": "UNAVAILABLE", "research_fitness": "UNAVAILABLE",
            "freshness": freshness, "research_usable": False, "peer_relative": {},
            "entity_type": None, "entity_applicability": None, "warnings_blockers": ["FUNDAMENTAL_FEATURE_STORE_ABSENT"],
        }
    readiness = availability if availability else ("READY_RESEARCH_PROXY" if ready_count else "BLOCKED")
    axes = context.get("health_axes") or {}
    usable = axis_is_research_usable(freshness) and ready_count > 0
    return {
        "readiness": readiness if usable else freshness["freshness_status"],
        "state": profit.get("categorical_state") or axes.get("PROFITABILITY_STATE") or "INSUFFICIENT_DATA",
        "trajectory": growth.get("categorical_state") or axes.get("GROWTH_STATE") or "INSUFFICIENT_DATA",
        "financial_health": {
            "profitability": axes.get("PROFITABILITY_STATE"),
            "margin": axes.get("MARGIN_STATE"),
            "balance_sheet": axes.get("BALANCE_SHEET_STATE"),
            "leverage": axes.get("LEVERAGE_STATE"),
            "cash_quality": axes.get("CASH_QUALITY_STATE"),
        },
        "research_fitness": axes.get("DATA_COVERAGE_STATE") or readiness,
        "ready_feature_count": ready_count,
        "current_features": {
            key: {
                "status": item.get("status"), "value": item.get("value"),
                "categorical_state": item.get("categorical_state"),
                "method": item.get("method"), "compatibility_class": item.get("compatibility_class"),
                "input_periods": item.get("input_periods"), "blocker_reason_codes": item.get("blocker_reason_codes"),
            }
            for key, item in (context.get("current_features") or {}).items()
        },
        "peer_relative": peers or {},
        "entity_type": (record or {}).get("entity_type"),
        "entity_applicability": (record or {}).get("entity_applicability"),
        "warnings_blockers": list(context.get("warnings_blockers") or []),
        "freshness": freshness,
        "research_usable": usable,
    }


def _tactical_axis(*, behavior: Mapping[str, Any] | None, watchlist: Mapping[str, Any] | None,
                   decision_session: str, source_identity: str | None) -> dict[str, Any]:
    source_session = (behavior or {}).get("as_of_session")
    freshness = classify_axis_freshness(
        axis="tactical", decision_session=decision_session, source_session=source_session,
        source_artifact_identity=source_identity,
    )
    entry_state = (behavior or {}).get("primary_entry_state") or (watchlist or {}).get("entry_state")
    entry_action = (watchlist or {}).get("entry_action")
    if entry_action is None and entry_state in ENTRY_ACTION_BY_ENTRY_STATE:
        entry_action = ENTRY_ACTION_BY_ENTRY_STATE[entry_state]
    usable = axis_is_research_usable(freshness) and bool(behavior) and bool(entry_state)
    confirmation = (behavior or {}).get("confirmation_boundary") or {"status": "UNAVAILABLE"}
    invalidation = (behavior or {}).get("technical_invalidation_boundary") or {"status": "UNAVAILABLE"}
    return {
        "readiness": "READY" if usable else (freshness["freshness_status"] if behavior else "UNAVAILABLE"),
        "primary_entry_state": entry_state,
        "entry_action": entry_action,
        "setup_tags": list((behavior or {}).get("setup_tags") or []),
        "confirmation": confirmation,
        "invalidation": invalidation,
        "price_volume_behavior": (behavior or {}).get("price_volume_behavior") or {},
        "trend_context": (behavior or {}).get("trend_context") or {},
        "structure_context": (behavior or {}).get("structure_context") or {},
        "freshness": freshness,
        "research_usable": usable,
        "rewritten_as_current": False,
    }


def _market_axis(*, behavior: Mapping[str, Any] | None, leadership: Mapping[str, Any] | None,
                 decision_session: str, source_identity: str | None, leadership_session: str | None) -> dict[str, Any]:
    source_session = (behavior or {}).get("as_of_session") or leadership_session
    freshness = classify_axis_freshness(
        axis="market_sector", decision_session=decision_session, source_session=source_session,
        source_artifact_identity=source_identity,
    )
    regime = ((behavior or {}).get("market_regime_context") or {})
    sector = ((behavior or {}).get("sector_context") or {})
    relative = ((behavior or {}).get("relative_strength_context") or {})
    usable = axis_is_research_usable(freshness) and bool(behavior or leadership)
    return {
        "readiness": "READY" if usable else freshness["freshness_status"],
        "breadth_regime": regime.get("current_breadth_state"),
        "sector_relative_context": {
            "leadership_state": sector.get("leadership_state"),
            "market_relative_momentum_bucket": relative.get("market_relative_momentum_bucket"),
            "sector_relative_momentum_bucket": relative.get("sector_relative_momentum_bucket"),
        },
        "freshness": freshness,
        "research_usable": usable,
    }


def _catalyst_axis(*, events_record: Mapping[str, Any] | None, thesis: Mapping[str, Any] | None,
                   decision_session: str, events_session: str | None, events_identity: str | None,
                   thesis_session: str | None, thesis_identity: str | None) -> dict[str, Any]:
    source_session = events_session or thesis_session
    source_identity = events_identity or thesis_identity
    freshness = classify_axis_freshness(
        axis="catalyst", decision_session=decision_session, source_session=source_session,
        known_at=None, source_artifact_identity=source_identity,
    )
    events = list((events_record or {}).get("events") or [])
    status = _catalyst_status(events, thesis)
    qualified = [event for event in events if _map_event_status(event.get("event_status")) == CONFIRMED]
    pending = [event for event in events if _map_event_status(event.get("event_status")) == PLANNED_PENDING]
    watch = [event for event in events if _map_event_status(event.get("event_status")) == WATCH_FOR_EXECUTION]
    usable = axis_is_research_usable(freshness) and status != CATALYST_UNAVAILABLE
    compact_events = [
        {"event_type": event.get("event_type"), "event_status": _map_event_status(event.get("event_status")),
         "source_status": event.get("event_status"), "known_at": event.get("known_at") or event.get("published_at"),
         "effective_or_expected_date": event.get("effective_date") or event.get("ex_date") or event.get("execution_date")}
        for event in events
    ]
    return {
        "readiness": status if (events_record or thesis) else "UNAVAILABLE",
        "status": status,
        "qualified_current_catalysts": (
            [item for item in compact_events if item["event_status"] == CONFIRMED]
            or list((thesis or {}).get("catalysts") or [])
        ),
        "pending_watch_items": [item for item in compact_events if item["event_status"] in {PLANNED_PENDING, WATCH_FOR_EXECUTION}],
        "adverse_events": [item for item in compact_events if item.get("source_status") == "CANCELLED"],
        "event_count": len(events),
        "freshness": freshness,
        "research_usable": usable,
        "inferred_from_price_action": False,
    }


def _downside_axis(*, tactical: Mapping[str, Any], thesis: Mapping[str, Any] | None,
                   decision_session: str, thesis_session: str | None, thesis_identity: str | None) -> dict[str, Any]:
    technical = (tactical.get("invalidation") if tactical.get("research_usable") else None) or (
        (thesis or {}).get("technical_invalidation")
    ) or {"status": "UNAVAILABLE"}
    fundamental = (thesis or {}).get("fundamental_invalidation") or {"status": "UNAVAILABLE"}
    source_session = (technical.get("as_of") if isinstance(technical, Mapping) else None) or thesis_session
    freshness = classify_axis_freshness(
        axis="downside_invalidation", decision_session=decision_session,
        source_session=source_session or (tactical.get("freshness") or {}).get("source_session"),
        source_artifact_identity=thesis_identity or (tactical.get("freshness") or {}).get("source_artifact_identity"),
    )
    usable = axis_is_research_usable(freshness) and (
        (isinstance(technical, Mapping) and technical.get("status") not in {None, "UNAVAILABLE"})
        or (isinstance(fundamental, Mapping) and fundamental.get("status") not in {None, "UNAVAILABLE"})
    )
    counter = list((thesis or {}).get("counter_thesis_evidence") or [])
    return {
        "readiness": "READY" if usable else freshness["freshness_status"],
        "technical": technical if isinstance(technical, Mapping) else {"status": "UNAVAILABLE"},
        "fundamental": fundamental if isinstance(fundamental, Mapping) else {"status": "UNAVAILABLE"},
        "thesis_conflict": counter,
        "freshness": freshness,
        "research_usable": usable,
    }


def build_ticker_opportunity(
    *,
    ticker: str,
    decision_session: str,
    feature_record: Mapping[str, Any] | None,
    valuation_row: Mapping[str, Any] | None,
    valuation_freshness: Mapping[str, Any],
    fundamental_peers: Mapping[str, Any] | None,
    behavior: Mapping[str, Any] | None,
    watchlist: Mapping[str, Any] | None,
    tactical_identity: str | None,
    leadership: Mapping[str, Any] | None,
    leadership_session: str | None,
    leadership_identity: str | None,
    liquidity_record: Mapping[str, Any] | None,
    liquidity_session: str | None,
    liquidity_identity: str | None,
    events_record: Mapping[str, Any] | None,
    events_session: str | None,
    events_identity: str | None,
    thesis: Mapping[str, Any] | None,
    thesis_session: str | None,
    thesis_identity: str | None,
    portfolio: Mapping[str, Any] | None,
    portfolio_freshness: Mapping[str, Any],
    feature_store_identity: str | None,
) -> dict[str, Any]:
    fundamental = _fundamental_axis(
        record=feature_record, peers=fundamental_peers, decision_session=decision_session,
        source_identity=feature_store_identity,
    )
    valuation = valuation_axis(
        ticker=ticker, decision_session=decision_session, valuation_artifact=None,
        feature_store=None, row=valuation_row or evaluate_ticker_valuation(
            ticker=ticker, feature_record=feature_record, valuation_record=None,
        ),
        freshness=valuation_freshness,
    )
    tactical = _tactical_axis(
        behavior=behavior, watchlist=watchlist, decision_session=decision_session,
        source_identity=tactical_identity,
    )
    market = _market_axis(
        behavior=behavior, leadership=leadership, decision_session=decision_session,
        source_identity=leadership_identity or tactical_identity, leadership_session=leadership_session,
    )
    catalyst = _catalyst_axis(
        events_record=events_record, thesis=thesis, decision_session=decision_session,
        events_session=events_session, events_identity=events_identity,
        thesis_session=thesis_session, thesis_identity=thesis_identity,
    )
    downside = _downside_axis(
        tactical=tactical, thesis=thesis, decision_session=decision_session,
        thesis_session=thesis_session, thesis_identity=thesis_identity,
    )
    liquidity = _liquidity_row(
        liquidity_record, session=liquidity_session, source_identity=liquidity_identity,
        decision_session=decision_session,
    )
    portfolio_status = _portfolio_availability(portfolio, portfolio_freshness)
    axes = {
        "fundamental": fundamental, "valuation": valuation, "tactical": tactical,
        "market_sector": market, "catalyst": catalyst, "downside_invalidation": downside,
        "liquidity": liquidity,
    }
    usable_major = [name for name, axis in axes.items() if axis.get("research_usable")]
    blockers = []
    for name, axis in axes.items():
        if not axis.get("research_usable"):
            blockers.append({
                "axis": name,
                "freshness_status": (axis.get("freshness") or {}).get("freshness_status"),
                "readiness": axis.get("readiness"),
            })
    return {
        "ticker": ticker,
        "as_of_session": decision_session,
        "disposition": "PARTIAL_BY_EVIDENCE" if usable_major else "INSUFFICIENT_EVIDENCE",
        "usable_major_axis_count": len(usable_major),
        "usable_major_axes": usable_major,
        "fundamental": fundamental,
        "valuation": valuation,
        "tactical": tactical,
        "market_sector": market,
        "catalyst": catalyst,
        "downside_invalidation": downside,
        "liquidity": liquidity,
        "portfolio_availability": {
            "status": portfolio_status,
            "freshness": dict(portfolio_freshness),
            "does_not_change_security_attractiveness": True,
        },
        "data_authority": {
            "per_axis_session": {
                name: (axis.get("freshness") or {}).get("source_session") or (axis.get("freshness") or {}).get("source_period")
                for name, axis in axes.items()
            },
            "per_axis_freshness": {name: (axis.get("freshness") or {}).get("freshness_status") for name, axis in axes.items()},
            "proxy_or_qualified_state": {
                "fundamental": fundamental.get("research_fitness"),
                "valuation_share_basis": valuation.get("share_basis"),
                "liquidity": liquidity.get("readiness"),
            },
            "blockers": blockers,
        },
        "authority_boundary": {
            "is_actionable": False, "no_universal_score": True, "no_rank": True,
            "no_probability": True, "no_target_price": True, "not_execution_authority": True,
            "portfolio_fit_deferred_to_decision_workspace": True,
        },
    }


def compact_opportunity(record: Mapping[str, Any]) -> dict[str, Any]:
    """Product-facing projection without full fundamental/technical/price histories."""
    return {
        "ticker": record["ticker"], "as_of_session": record["as_of_session"],
        "disposition": record["disposition"], "usable_major_axis_count": record["usable_major_axis_count"],
        "usable_major_axes": record["usable_major_axes"],
        "fundamental": {
            "readiness": record["fundamental"]["readiness"], "state": record["fundamental"]["state"],
            "trajectory": record["fundamental"]["trajectory"],
            "research_fitness": record["fundamental"]["research_fitness"],
            "freshness_status": record["fundamental"]["freshness"]["freshness_status"],
            "source_period": record["fundamental"]["freshness"].get("source_period"),
        },
        "valuation": {
            "readiness": record["valuation"]["readiness"],
            "relative_research_state": (record["valuation"].get("peer_relative_context") or {}).get("relative_research_state"),
            "share_basis": record["valuation"].get("share_basis"),
            "earnings_state": record["valuation"].get("earnings_state"),
            "freshness_status": record["valuation"]["freshness"]["freshness_status"],
            "source_session": record["valuation"]["freshness"].get("source_session"),
        },
        "tactical": {
            "primary_entry_state": record["tactical"].get("primary_entry_state"),
            "entry_action": record["tactical"].get("entry_action"),
            "setup_tags": record["tactical"].get("setup_tags"),
            "confirmation_status": (record["tactical"].get("confirmation") or {}).get("status"),
            "invalidation_status": (record["tactical"].get("invalidation") or {}).get("status"),
            "freshness_status": record["tactical"]["freshness"]["freshness_status"],
            "source_session": record["tactical"]["freshness"].get("source_session"),
        },
        "market_sector": {
            "breadth_regime": record["market_sector"].get("breadth_regime"),
            "sector_relative_context": record["market_sector"].get("sector_relative_context"),
            "freshness_status": record["market_sector"]["freshness"]["freshness_status"],
        },
        "catalyst": {
            "status": record["catalyst"].get("status"),
            "freshness_status": record["catalyst"]["freshness"]["freshness_status"],
        },
        "downside_invalidation": {
            "technical_status": (record["downside_invalidation"].get("technical") or {}).get("status"),
            "fundamental_status": (record["downside_invalidation"].get("fundamental") or {}).get("status"),
            "counter_thesis_present": bool(record["downside_invalidation"].get("thesis_conflict")),
        },
        "liquidity": {
            "readiness": record["liquidity"].get("readiness"),
            "exact_execution_capacity_status": record["liquidity"].get("exact_execution_capacity_status"),
            "freshness_status": record["liquidity"]["freshness"]["freshness_status"],
        },
        "portfolio_availability": record["portfolio_availability"]["status"],
        "authority_boundary": record["authority_boundary"],
    }
