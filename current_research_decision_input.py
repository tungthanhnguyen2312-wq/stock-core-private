"""Current Research Decision Input: one deterministic, per-ticker evidence contract.

The Integrated Decision already joins every Current Research axis. This module restates that
already-computed evidence as one explainable input per ticker, dimension by dimension:
what is AVAILABLE, PARTIAL, BLOCKED or NON_APPLICABLE, under which authority tier, and why.

It computes no indicator, ratio, threshold, score, rank, probability or target. It never feeds
``research_action_posture``: the evidence class describes research coverage, while posture stays
the sole action authority. Current Research is not PIT, exact valuation, or execution
authority; those boundaries are restated explicitly rather than inferred.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from datetime import date
import re
from typing import Any, Iterable, Mapping

import execution_capacity_research as execution_capacity
import fundamental_signal_consumption_contract as fundamental_signals
from operational_fundamental_context_integration import MAX_COMPLETED_QUARTER_LAG
from opportunity_axis_freshness import STALE_BUT_RESEARCH_USABLE, classify_financial_period_freshness

CONTRACT_VERSION = "current_research_decision_input/v1"
#: Every market-wide count this contract emits is over all Integrated Decision records.
COVERAGE_DENOMINATOR = "ATTEMPTED_COHORT"

AVAILABLE = "AVAILABLE"
PARTIAL = "PARTIAL"
BLOCKED = "BLOCKED"
NON_APPLICABLE = "NON_APPLICABLE"
DIMENSION_STATES = (AVAILABLE, PARTIAL, BLOCKED, NON_APPLICABLE)

EXACT_QUALIFIED = "EXACT_QUALIFIED"
RESEARCH_QUALIFIED = "RESEARCH_QUALIFIED"
RESEARCH_PROXY = "RESEARCH_PROXY"
CURRENT_DESCRIPTIVE_ONLY = "CURRENT_DESCRIPTIVE_ONLY"
NO_AUTHORITY = "NONE"

CLASS_FULL = "FULL_CURRENT_RESEARCH"
CLASS_PARTIAL = "PARTIAL_MULTI_FACTOR_RESEARCH"
CLASS_TECHNICAL = "TECHNICAL_MARKET_RESEARCH"
CLASS_FINANCIAL = "FINANCIAL_RESEARCH_ONLY"
CLASS_INSUFFICIENT = "INSUFFICIENT_CURRENT_EVIDENCE"
CLASS_OUT_OF_SCOPE = "OUTSIDE_CURRENT_RESEARCH_SCOPE"
EVIDENCE_CLASSES = (CLASS_FULL, CLASS_PARTIAL, CLASS_TECHNICAL, CLASS_FINANCIAL, CLASS_INSUFFICIENT, CLASS_OUT_OF_SCOPE)

DIMENSIONS = ("MARKET", "TECHNICAL", "FUNDAMENTAL", "VALUATION", "CORPORATE", "LIQUIDITY")
PRIMARY_FACTORS = ("TECHNICAL", "FUNDAMENTAL", "VALUATION")

VALUATION_RELATIVE_WITH_PEERS = "RELATIVE_MULTIPLE_WITH_PEER_CONTEXT"
VALUATION_RELATIVE_NO_PEERS = "RELATIVE_MULTIPLE_WITHOUT_PEER_CONTEXT"
VALUATION_NOT_MEANINGFUL = "PE_NOT_MEANINGFUL_ONLY"
VALUATION_SIZE_ONLY = "SIZE_CONTEXT_ONLY"
VALUATION_NONE = "NONE"

_SIZE_METHODS = frozenset({"market_cap"})
_USABLE_METHOD_STATUSES = frozenset({"RESEARCH_USABLE", "READY"})
_OPERATIONAL_BRIDGE_CONTRACT = "entity_aware_operational_fundamental_context_integration/v1"
_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_:./-]*")


def _codes(*groups: Iterable[Any] | None) -> list[str]:
    """Deduplicated, sorted machine reason codes; prose and non-strings are dropped."""
    out: set[str] = set()
    for group in groups:
        for item in group or []:
            if isinstance(item, str) and _CODE.fullmatch(item):
                out.add(item)
    return sorted(out)


def _market(record: Mapping[str, Any], disposition: Mapping[str, Any] | None, session: str) -> dict[str, Any]:
    disposition = disposition or {}
    exact = (disposition.get("has_exact_session_bar") is True
             and disposition.get("disposition") not in {"MALFORMED_OR_CONFLICTED", "UNEXPLAINED"})
    in_scope = disposition.get("in_official_research_universe")
    market_axis = (record.get("evidence_axes") or {}).get("MARKET_SECTOR") or {}
    return {
        "state": AVAILABLE if exact else BLOCKED,
        "authority": CURRENT_DESCRIPTIVE_ONLY if exact else NO_AUTHORITY,
        "session": session,
        "evidence_currency": record.get("evidence_currency"),
        "research_scope": ("OFFICIAL_RESEARCH_SCOPE" if in_scope is True
                           else "OUTSIDE_OFFICIAL_RESEARCH_SCOPE" if in_scope is False else "NOT_EVALUATED"),
        "technical_coverage_disposition": disposition.get("disposition") or "NOT_SUPPLIED",
        "price_basis": {"current_research_use": "EXACT_SESSION_DESCRIPTIVE_ONLY",
                        "raw_as_traded": "NOT_PROMOTED", "historical_pit": "BLOCKED"},
        "market_regime": market_axis.get("state") if market_axis.get("fitness") not in (None, "UNAVAILABLE") else None,
        "market_breadth": copy.deepcopy((market_axis.get("context") or {}).get("market_breadth")),
        "reason_codes": [] if exact else _codes(
            [disposition.get("disposition") or "TECHNICAL_COVERAGE_DISPOSITION_NOT_SUPPLIED", disposition.get("reason_code")]),
    }


def _technical(record: Mapping[str, Any], disposition: Mapping[str, Any] | None,
               sector_context: Mapping[str, Any] | None) -> dict[str, Any]:
    axes = record.get("evidence_axes") or {}
    tactical_axis = axes.get("TACTICAL_STRUCTURE") or {}
    tactical_context = tactical_axis.get("context") or {}
    momentum_axis = axes.get("MOMENTUM") or {}
    momentum_context = momentum_axis.get("context") or {}
    confirmation_axis = axes.get("PARTICIPATION_CONFIRMATION") or {}
    participation = record.get("participation") or {}
    trigger = record.get("trigger") or {}
    invalidation = record.get("invalidation") or {}
    sector = sector_context or {}
    market_relative = sector.get("market_relative_momentum") or {}
    sector_relative = sector.get("sector_relative_momentum") or {}
    available = tactical_axis.get("fitness") == "AVAILABLE"
    relative_available = AVAILABLE in {market_relative.get("status"), sector_relative.get("status")}
    reasons: list[str] = []
    if not available:
        disposition = disposition or {}
        reasons = _codes(tactical_axis.get("blocker_reason_codes"),
                         [disposition.get("disposition"), disposition.get("reason_code")]
                         if disposition.get("disposition") not in (None, "SAME_SESSION_TECHNICAL_COVERED") else [])
    return {
        "state": AVAILABLE if available else BLOCKED,
        "authority": RESEARCH_QUALIFIED if available else NO_AUTHORITY,
        "components": {
            "trend": {"market_structure_state": record.get("market_structure_state"),
                      "tactical_phase": record.get("tactical_phase")},
            "momentum": {"state": momentum_axis.get("fitness"),
                         **{key: momentum_context.get(key) for key in ("rsi_status", "macd_status", "moving_average_status")}},
            "relative_strength": {
                "state": AVAILABLE if relative_available else "UNAVAILABLE",
                "authority": "CURRENT_CROSS_SECTIONAL_DESCRIPTIVE_NOT_ORDINAL_RANKING",
                "market_relative_bucket": market_relative.get("momentum_bucket"),
                "market_relative_percentile": market_relative.get("momentum_percentile_descriptive"),
                "sector_relative_bucket": sector_relative.get("momentum_bucket"),
                "sector_relative_percentile": sector_relative.get("momentum_percentile_descriptive"),
                "sector_leadership_state": (sector.get("sector_leadership_context") or {}).get("leadership_state"),
            },
            "market_structure": {"bos_state": tactical_context.get("bos_state"),
                                 "choch_state": tactical_context.get("choch_state"),
                                 "breakout_state_v3": record.get("breakout_state_v3"),
                                 "inference": "DETERMINISTIC_TECHNICAL_INFERENCE_NOT_ORDER_FLOW_PROOF"},
            "participation": {"state": AVAILABLE if participation.get("status") == AVAILABLE else "UNAVAILABLE",
                              "authority": RESEARCH_PROXY if participation.get("status") == AVAILABLE else NO_AUTHORITY,
                              "confirmation_state": confirmation_axis.get("state")},
            "trigger": {"state": trigger.get("trigger_state"), "type": trigger.get("trigger_type"),
                        "condition_status": (trigger.get("condition") or {}).get("status"),
                        "condition_identity": (trigger.get("condition") or {}).get("condition_identity")},
            "invalidation": {"available": invalidation.get("invalidation_level") is not None,
                             "method": invalidation.get("invalidation_method"),
                             "condition_status": (invalidation.get("condition") or {}).get("status"),
                             "condition_identity": (invalidation.get("condition") or {}).get("condition_identity")},
        },
        "reason_codes": reasons,
    }


def _period_freshness(period: Any, session: str) -> dict[str, Any]:
    return classify_financial_period_freshness(source_period=period, decision_session=session,
                                               maximum_completed_quarter_lag=MAX_COMPLETED_QUARTER_LAG)


#: Why a current fundamental direction is missing, by what fundamental evidence is known.
_DIRECTION_REASON = {
    fundamental_signals.ABSENT: "FUNDAMENTAL_CONTEXT_ABSENT",
    fundamental_signals.STALE_ONLY: "FUNDAMENTAL_STALE_EVIDENCE_ONLY_NO_CURRENT_DIRECTION",
    fundamental_signals.CURRENT_NON_DIRECTIONAL: "FUNDAMENTAL_CURRENT_DIRECTION_INSUFFICIENT",
    fundamental_signals.NOT_APPLICABLE_ENTITY: "FUNDAMENTAL_ENTITY_NOT_DECISION_APPLICABLE",
}


def _fundamental(record: Mapping[str, Any], financial: Mapping[str, Any] | None,
                 operational_context: Mapping[str, Any] | None, entity: Mapping[str, Any],
                 session: str) -> dict[str, Any]:
    financial = financial or {}
    axis = (record.get("evidence_axes") or {}).get("FUNDAMENTAL") or {}
    state = record.get("fundamental_state")
    synthesis = record.get("fundamental_synthesis")
    # FUNDAMENTAL_SIGNAL_POLICY_HARDENING_V1: the dimension is available when qualified fundamental
    # evidence exists; an insufficient current direction is reported beside it, never as absence.
    direction_sufficient = state not in (None, "INSUFFICIENT")
    evidence_state = ((synthesis.get("evidence_availability") or {}).get("state")
                      if isinstance(synthesis, Mapping) else None)
    available = direction_sufficient or evidence_state == fundamental_signals.AVAILABLE
    # CURRENT_RESEARCH_FUNDAMENTAL_PROMOTION_HARDENING_V1: what evidence is known (five states),
    # the qualified risk level (never from the direction) and the fundamental policy epoch.
    five_state = record.get("fundamental_evidence_availability") or (
        synthesis.get("fundamental_evidence_availability") if isinstance(synthesis, Mapping) else None)
    risk = record.get("fundamental_risk_level") or (
        synthesis.get("fundamental_risk_level") if isinstance(synthesis, Mapping) else None) or {}
    bridge_applied = axis.get("method") == _OPERATIONAL_BRIDGE_CONTRACT
    bridge = operational_context or {}
    fitness = financial.get("feature_fitness") if isinstance(financial.get("feature_fitness"), Mapping) else {}
    if bridge_applied:
        qualified: list[str] = []
        proxy = sorted(bridge.get("usable_features") or {})
        non_applicable = sorted(bridge.get("non_applicable_features") or {})
        blocked = {key: _codes(item.get("reason_codes"), [item.get("integration_fitness")])
                   for key, item in sorted((bridge.get("blocked_features") or {}).items())}
        periods = sorted({period for item in (bridge.get("usable_features") or {}).values()
                          for period in (item.get("input_periods") or [])})
        as_of = periods[-1] if periods else None
        metric_periods = {key: max(item.get("input_periods") or [None], key=str)
                          for key, item in (bridge.get("usable_features") or {}).items()}
        authority = RESEARCH_PROXY
        method = _OPERATIONAL_BRIDGE_CONTRACT
    else:
        qualified = sorted(key for key, item in fitness.items() if (item or {}).get("fitness") == "READY")
        proxy = sorted(key for key, item in fitness.items() if (item or {}).get("fitness") == "RESEARCH_PROXY")
        non_applicable = sorted(key for key, item in fitness.items() if (item or {}).get("fitness") == "NOT_APPLICABLE")
        blocked = {key: _codes((item or {}).get("reason_codes"), [(item or {}).get("fitness")])
                   for key, item in sorted(fitness.items())
                   if (item or {}).get("fitness") not in ("READY", "RESEARCH_PROXY", "NOT_APPLICABLE")}
        as_of = financial.get("as_of_financial_period")
        metric_periods = {key: (fitness.get(key) or {}).get("as_of_period") for key in qualified + proxy}
        authority = RESEARCH_QUALIFIED if financial.get("current_research_ready") is True else RESEARCH_PROXY
        method = axis.get("method") or "financial_analysis_product_integration/v1"
    # Periodic evidence is labelled, never dropped: a valid metric beyond the completed-quarter
    # window stays in its list and is named here as stale-but-usable research context.
    freshness = _period_freshness(as_of, session)
    freshness["stale_but_research_usable_metrics"] = sorted(
        key for key, period in metric_periods.items()
        if period and _period_freshness(period, session)["freshness_status"] == STALE_BUT_RESEARCH_USABLE) if available else []
    if isinstance(synthesis, Mapping):
        # The freshness of the signals that actually decided the direction (CURRENT only), and of
        # the vote-capable signals a stale or unavailable period kept out of the current synthesis.
        freshness["decision_signal_freshness"] = dict(synthesis.get("decision_signal_freshness") or {})
        freshness["signal_freshness_voting"] = dict(synthesis.get("signal_freshness_voting") or {})
    if operational_context is None:
        bridge_state = "NOT_CONSULTED"
    elif bridge_applied:
        bridge_state = "APPLIED"
    else:
        bridge_state = "CONSULTED_BLOCKED"
    reasons: list[str] = []
    if not available:
        if financial.get("status") in (None, "ABSENT", "NOT_SUPPLIED"):
            base = [financial.get("reason") or "FA_V2_CONTEXT_ABSENT"]
        elif financial.get("conflicting_evidence") or financial.get("status") in {"CONFLICTED", "BLOCKED"}:
            base = ["FINANCIAL_V2_CONFLICTING_OR_BLOCKED_EVIDENCE"]
        else:
            base = ["FINANCIAL_V2_DIRECTION_INSUFFICIENT"]
        reasons = _codes(axis.get("blocker_reason_codes"), base, bridge.get("reason_codes"),
                         ["OPERATIONAL_FUNDAMENTAL_BRIDGE_NOT_CONSULTED"] if operational_context is None else [])
    return {
        "state": AVAILABLE if available else BLOCKED,
        "authority": authority if available else NO_AUTHORITY,
        "direction": state,
        "evidence_availability": AVAILABLE if available else "UNAVAILABLE",
        "fundamental_evidence_availability": five_state,
        "directional_sufficiency": "SUFFICIENT" if direction_sufficient else "INSUFFICIENT",
        "direction_reason_codes": [] if direction_sufficient else (
            [_DIRECTION_REASON[five_state]] if five_state in _DIRECTION_REASON else
            ["FUNDAMENTAL_CURRENT_DIRECTION_INSUFFICIENT"] if available else ["FUNDAMENTAL_CONTEXT_ABSENT"]),
        "risk_level": {"state": risk.get("state"), "adverse_level_dimensions": list(risk.get("adverse_level_dimensions") or []),
                       "constructive_level_dimensions": list(risk.get("constructive_level_dimensions") or []),
                       "healthy_level_asserted": False} if risk else None,
        "policy_version": fundamental_signals.policy_epoch(record),
        # Level, direction and transition per dimension, kept apart (never one collapsed label).
        "components": fundamental_signals.compact_components(synthesis) if isinstance(synthesis, Mapping) else None,
        "method": method if available else None,
        "operational_bridge": {"state": bridge_state, "primary_reason": bridge.get("primary_reason")},
        "entity_applicability": dict(entity),
        "analysis_family": financial.get("analysis_family"),
        "as_of_financial_period": as_of,
        "freshness": freshness,
        "metrics": {"qualified": qualified if available else [], "proxy": proxy if available else [],
                    "non_applicable": non_applicable, "blocked": blocked},
        **({"financial_peer_context": copy.deepcopy(record["financial_peer_context"])} if "financial_peer_context" in record else {}),
        "reason_codes": reasons,
    }


def _valuation(record: Mapping[str, Any], valuation_record: Mapping[str, Any] | None,
               entity: Mapping[str, Any]) -> dict[str, Any]:
    methods = record.get("valuation_methods") if isinstance(record.get("valuation_methods"), Mapping) else {}
    summary = record.get("valuation_context_summary") or {}
    valuation_record = valuation_record or {}
    usable: list[str] = []
    not_meaningful: list[str] = []
    non_applicable: list[str] = []
    blocked: dict[str, list[str]] = {}
    exact = False
    for method_id, method in sorted(methods.items()):
        if method_id in _SIZE_METHODS or not isinstance(method, Mapping):
            continue
        status = method.get("status")
        if status in _USABLE_METHOD_STATUSES:
            usable.append(method_id)
            exact = exact or status == "READY"
        elif status == "PE_NOT_MEANINGFUL":
            not_meaningful.append(method_id)
        elif status == "NOT_APPLICABLE" or method.get("applicability") == "NOT_APPLICABLE":
            non_applicable.append(method_id)
        else:
            blocked[method_id] = _codes(method.get("blocker_reason_codes"), [] if method.get("blocker_reason_codes") else ["VALUATION_INPUT_BLOCKED"])
    size = methods.get("market_cap") if isinstance(methods.get("market_cap"), Mapping) else {}
    size_available = size.get("status") in _USABLE_METHOD_STATUSES
    # Every price-based multiple needs the size input; when it is blocked its causes (missing
    # exact-session price, unqualified share basis) are the root reason and are named.
    size_reasons = [] if size_available or not size else _codes(size.get("blocker_reason_codes"))
    peer_state = summary.get("peer_relative_state")
    peer_available = peer_state not in (None, "NOT_APPLICABLE")
    if not methods:
        # A compact/legacy record without per-method detail: defer to the evaluated summary.
        state = AVAILABLE if summary.get("status") == AVAILABLE else BLOCKED
        evidence_class = VALUATION_RELATIVE_WITH_PEERS if state == AVAILABLE and peer_available else (
            VALUATION_RELATIVE_NO_PEERS if state == AVAILABLE else VALUATION_NONE)
    else:
        if usable:
            evidence_class = VALUATION_RELATIVE_WITH_PEERS if peer_available else VALUATION_RELATIVE_NO_PEERS
        elif not_meaningful:
            evidence_class = VALUATION_NOT_MEANINGFUL
        elif size_available:
            evidence_class = VALUATION_SIZE_ONLY
        else:
            evidence_class = VALUATION_NONE
        if usable or peer_available:
            state = AVAILABLE
        elif not blocked and not not_meaningful and non_applicable:
            state = NON_APPLICABLE
        elif not_meaningful or size_available:
            state = PARTIAL
        else:
            state = BLOCKED
    upstream_unknown = ((valuation_record.get("entity_applicability") or {}).get("upstream_valuation_lane_entity_class") == "unknown"
                        and entity.get("applicability_status") == "RESOLVED")
    reasons: list[str] = []
    if state != AVAILABLE:
        reasons = _codes(*blocked.values(), size_reasons, summary.get("unavailable_reason_codes"),
                         ["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"] if state == NON_APPLICABLE else [],
                         ["UPSTREAM_VALUATION_LANE_ENTITY_CLASS_UNRESOLVED"] if upstream_unknown else [],
                         entity.get("reason_codes") if entity.get("applicability_status") != "RESOLVED" else [])
    if state == AVAILABLE:
        authority = EXACT_QUALIFIED if exact else RESEARCH_PROXY
    elif state == PARTIAL:
        authority = RESEARCH_PROXY
    else:
        authority = NO_AUTHORITY
    exact_market_cap_eligible = bool(valuation_record.get("authoritative_current_market_cap_eligible"))
    single_period = [method_id for method_id in usable
                     if methods[method_id].get("denominator_period_semantics") == "SINGLE_REPORTING_PERIOD_NOT_ANNUALIZED"]
    return {
        "state": state,
        "authority": authority,
        "evidence_class": evidence_class,
        "usable_methods": usable,
        "usable_method_period_basis": {method_id: methods[method_id].get("period_basis") for method_id in usable},
        "limitations": ["SINGLE_REPORTING_PERIOD_DENOMINATOR_NOT_TTM"] if single_period else [],
        "not_meaningful_methods": not_meaningful,
        "non_applicable_methods": non_applicable,
        "blocked_methods": blocked,
        **({"intrinsic_scenario_valuation": copy.deepcopy(record["intrinsic_scenario_valuation"])} if "intrinsic_scenario_valuation" in record else {}),
        "peer_relative_state": peer_state,
        "share_basis": summary.get("share_basis") or valuation_record.get("share_basis"),
        "size_context": {"state": AVAILABLE if size_available else "UNAVAILABLE",
                         "role": "SIZE_CONTEXT_NOT_A_VALUATION_MULTIPLE", "reason_codes": size_reasons},
        "exact_market_cap": {"state": EXACT_QUALIFIED if exact_market_cap_eligible else BLOCKED,
                             "reason_codes": [] if exact_market_cap_eligible else ["CURRENT_COMMON_SHARE_AUTHORITY_NOT_QUALIFIED"]},
        "entity_applicability": dict(entity),
        "reason_codes": reasons,
    }


def _corporate(record: Mapping[str, Any]) -> dict[str, Any]:
    context = record.get("corporate_intelligence_context") or {}
    provided = context.get("state") not in (None, "NOT_PROVIDED")
    source_session = context.get("evidence_session")
    temporal = "NOT_PROVIDED"
    if provided:
        try:
            source_day = date.fromisoformat(source_session)
            decision_day = date.fromisoformat(record.get("as_of_session"))
            temporal = ("FUTURE_INFORMATION_PROHIBITED" if source_day > decision_day else
                        "STALE_EVIDENCE_SESSION" if source_day < decision_day else "CURRENT_EVIDENCE_SESSION")
        except (TypeError, ValueError):
            temporal = "SOURCE_SESSION_ABSENT_OR_INVALID"
    temporal_usable = temporal in {"STALE_EVIDENCE_SESSION", "CURRENT_EVIDENCE_SESSION"}
    source_available = context.get("fitness") in {"AVAILABLE", "CURRENT_RESEARCH_ONLY"}
    no_event = context.get("state") == "NO_QUALIFIED_CORPORATE_EVENT"
    unresolved = context.get("state") == "UNRESOLVED_EVIDENCE"
    usable = provided and source_available and temporal_usable and not no_event
    qualified = usable and not unresolved
    reasons = _codes(context.get("blocker_reason_codes"),
                     ["NO_QUALIFIED_CORPORATE_EVENT"] if provided and no_event else [],
                     ["CORPORATE_EVENT_CLASSIFICATION_UNRESOLVED"] if provided and unresolved else [],
                     [temporal] if provided and not temporal_usable else [],
                     ["CORPORATE_SOURCE_FITNESS_UNAVAILABLE"] if provided and not source_available and not no_event else [])
    return {
        "state": (PARTIAL if temporal == "STALE_EVIDENCE_SESSION" or unresolved else AVAILABLE) if usable else BLOCKED,
        "authority": RESEARCH_QUALIFIED if qualified else CURRENT_DESCRIPTIVE_ONLY if usable else NO_AUTHORITY,
        "forward_driver_context": copy.deepcopy(context.get("forward_driver_context")),
        "context_state": context.get("state"),
        "temporal_status": temporal,
        "evidence_session": context.get("evidence_session"),
        "material_event_count": context.get("material_event_count"),
        "active_catalyst_count": context.get("active_catalyst_count"),
        "active_risk_count": context.get("active_risk_count"),
        "reason_codes": reasons,
    }


_OFFICIAL_LIQUIDITY_USES = ("CURRENT_SESSION_LIQUIDITY_RESEARCH", "HISTORICAL_LIQUIDITY_RESEARCH", "ADV_VOLUME_RESEARCH", "ADTV_RESEARCH")


def _official_fitness_state(official_record: Mapping[str, Any], use: str) -> str | None:
    """Per-record fitness is authoritative; research_view.fitness is a string projection."""
    cell = (official_record.get("fitness") or {}).get(use)
    if isinstance(cell, Mapping) and cell.get("state"):
        return str(cell["state"])
    if isinstance(cell, str) and cell:
        return cell
    view = ((official_record.get("research_view") or {}).get("fitness") or {}).get(use)
    if isinstance(view, Mapping) and view.get("state"):
        return str(view["state"])
    if isinstance(view, str) and view:
        return view
    return None


def _official_liquidity(official_record: Mapping[str, Any] | None) -> dict[str, Any]:
    """Qualified official-exchange liquidity research for one ticker (research scope only).

    Absence, an unauthorized exchange or a partial window blocks only the liquidity-dependent use it
    names; it never changes another dimension, the evidence class or the posture. Per-record fitness
    is the authority for each named use; an artifact-level summary cannot widen it.
    """
    if not isinstance(official_record, Mapping):
        return {"state": BLOCKED, "authority": NO_AUTHORITY, "reason_codes": ["OFFICIAL_LIQUIDITY_RESEARCH_NOT_SUPPLIED"]}
    view = official_record.get("research_view") or {}
    fitness = {use: _official_fitness_state(official_record, use) for use in _OFFICIAL_LIQUIDITY_USES}
    for key, value in ((view.get("fitness") or {}) if isinstance(view.get("fitness"), Mapping) else {}).items():
        fitness.setdefault(key, value if not isinstance(value, Mapping) else value.get("state"))
    adtv_ok = fitness.get("ADTV_RESEARCH") == "ELIGIBLE"
    any_usable = any(fitness.get(use) in ("ELIGIBLE", "PARTIAL") for use in _OFFICIAL_LIQUIDITY_USES)
    refs = official_record.get("evidence_refs") or {}
    capacity = execution_capacity.build_envelope(
        ticker=official_record.get("ticker") or "UNKNOWN",
        session=((view.get("current_session") or {}).get("session") or "UNKNOWN"),
        official_liquidity_record=official_record,
        policy=execution_capacity.canonical_unbound_policy(),
    )
    return {
        "state": AVAILABLE if adtv_ok else (PARTIAL if any_usable else BLOCKED),
        "authority": RESEARCH_QUALIFIED if adtv_ok else NO_AUTHORITY,
        "scope": "OFFICIAL_EXCHANGE_RESEARCH_SCOPED_RETROSPECTIVE_KNOWLEDGE_TIME",
        "route_exchange": official_record.get("route_exchange"),
        "window_coverage": view.get("window_coverage"),
        "current_session": view.get("current_session"),
        "adtv20_matched_all_vnd": view.get("adtv20_matched_all_vnd"),
        "adv20_matched_all_shares": view.get("adv20_matched_all_shares"),
        "current_value_to_adtv20": view.get("current_value_to_adtv20"),
        "current_volume_to_adv20": view.get("current_volume_to_adv20"),
        "evidence_currency": view.get("evidence_currency"),
        "fitness": dict(fitness),
        "execution_capacity_research": capacity,
        "evidence_refs": {"source": refs.get("source"), "response_sha256": [r.get("sha256") for r in refs.get("responses") or []]},
        "reason_codes": _codes(view.get("reason_codes")),
    }


def _liquidity(record: Mapping[str, Any], liquidity_record: Mapping[str, Any] | None,
               official_record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    liquidity = liquidity_record or {}
    contract = liquidity.get("liquidity_research_contract") if isinstance(liquidity.get("liquidity_research_contract"), Mapping) else {}
    disposition = liquidity.get("disposition")
    research_available = disposition == "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE"
    participation = record.get("participation") or {}
    capacity = (contract.get("EXECUTION_CAPACITY") or {}).get("state") or "BLOCKED"
    sizing = (contract.get("POSITION_SIZING") or {}).get("state") or "BLOCKED"
    execution_qualified = capacity == "ELIGIBLE" and sizing == "ELIGIBLE"
    qualified = _official_liquidity(official_record) if official_record is not None else None
    qualified_state = (qualified or {}).get("state")
    if qualified is None:
        dim_state = AVAILABLE if research_available else BLOCKED
        dim_authority = CURRENT_DESCRIPTIVE_ONLY if research_available else NO_AUTHORITY
    else:
        dim_state = (
            AVAILABLE if qualified_state == AVAILABLE else
            (PARTIAL if qualified_state == PARTIAL else (AVAILABLE if research_available else BLOCKED))
        )
        dim_authority = (
            RESEARCH_QUALIFIED if qualified.get("authority") == RESEARCH_QUALIFIED else
            (CURRENT_DESCRIPTIVE_ONLY if research_available else NO_AUTHORITY)
        )
    return {
        "state": dim_state,
        "authority": dim_authority,
        **({"qualified_research": qualified} if qualified is not None else {}),
        "research": {"state": AVAILABLE if research_available else BLOCKED,
                     "disposition": disposition or "NOT_SUPPLIED",
                     "reason_codes": [] if research_available else _codes([disposition or "LIQUIDITY_RESEARCH_NOT_SUPPLIED"])},
        "participation": {"state": AVAILABLE if participation.get("status") == AVAILABLE else "UNAVAILABLE",
                          "authority": RESEARCH_PROXY if participation.get("status") == AVAILABLE else NO_AUTHORITY,
                          "warning": participation.get("warning")},
        "execution": {"state": AVAILABLE if execution_qualified else BLOCKED,
                      "authority": EXACT_QUALIFIED if execution_qualified else NO_AUTHORITY,
                      "reason_codes": [] if execution_qualified else _codes(
                          ["QUALIFIED_LIQUIDITY_INPUTS_ABSENT", f"EXECUTION_CAPACITY_{capacity}", f"POSITION_SIZING_{sizing}"])},
    }


def evidence_class(dimensions: Mapping[str, Mapping[str, Any]]) -> str:
    """Coverage class from the three primary factors; never a score and never a posture."""
    if (dimensions.get("MARKET") or {}).get("research_scope") == "OUTSIDE_OFFICIAL_RESEARCH_SCOPE":
        return CLASS_OUT_OF_SCOPE
    usable = [name for name in PRIMARY_FACTORS if (dimensions.get(name) or {}).get("state") == AVAILABLE]
    if len(usable) == 3:
        return CLASS_FULL
    if len(usable) == 2:
        return CLASS_PARTIAL
    if usable == ["TECHNICAL"]:
        return CLASS_TECHNICAL
    if usable:
        return CLASS_FINANCIAL
    return CLASS_INSUFFICIENT


def build_ticker_decision_input(
    *,
    session: str,
    record: Mapping[str, Any],
    financial_record: Mapping[str, Any] | None = None,
    valuation_record: Mapping[str, Any] | None = None,
    disposition_record: Mapping[str, Any] | None = None,
    sector_context: Mapping[str, Any] | None = None,
    liquidity_record: Mapping[str, Any] | None = None,
    entity_applicability_record: Mapping[str, Any] | None = None,
    operational_context: Mapping[str, Any] | None = None,
    official_liquidity_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Restate one Integrated Decision record's evidence as the Current Research decision input."""
    entity_record = entity_applicability_record or {}
    entity = {
        "entity_class": entity_record.get("entity_class") or "unknown",
        "applicability_status": entity_record.get("applicability_status") or "NOT_SUPPLIED",
        "authority_tier": entity_record.get("authority_tier"),
        "authority_scope": "CURRENT_STATE_ONLY",
        "historical_pit_authority": "NOT_ESTABLISHED",
        "reason_codes": list(entity_record.get("reason_codes") or ([] if entity_record else ["ENTITY_APPLICABILITY_NOT_SUPPLIED"])),
    }
    dimensions = {
        "MARKET": _market(record, disposition_record, session),
        "TECHNICAL": _technical(record, disposition_record, sector_context),
        "FUNDAMENTAL": _fundamental(record, financial_record, operational_context, entity, session),
        "VALUATION": _valuation(record, valuation_record, entity),
        "CORPORATE": _corporate(record),
        "LIQUIDITY": _liquidity(record, liquidity_record, official_liquidity_record),
    }
    klass = evidence_class(dimensions)
    posture = record.get("research_action_posture")
    by_state = {state: [name for name in DIMENSIONS if dimensions[name]["state"] == state] for state in DIMENSION_STATES}
    by_authority = Counter(dimensions[name]["authority"] for name in DIMENSIONS)
    composite = record.get("financial_composite_context") or {}
    trigger = dimensions["TECHNICAL"]["components"]["trigger"]
    invalidation = dimensions["TECHNICAL"]["components"]["invalidation"]
    return {
        "contract_version": CONTRACT_VERSION,
        "ticker": record.get("ticker"),
        "session": session,
        "evidence_class": klass,
        "dimensions": dimensions,
        "synthesis": {
            "usable_primary_factors": [name for name in PRIMARY_FACTORS if dimensions[name]["state"] == AVAILABLE],
            "missing_primary_factors": {name: dimensions[name]["reason_codes"] for name in PRIMARY_FACTORS
                                        if dimensions[name]["state"] != AVAILABLE},
            "constructive_reason_codes": _codes(record.get("fundamental_support"), record.get("technical_support"),
                                                record.get("participation_support"), composite.get("supporting_reason_codes")),
            "weak_reason_codes": _codes(record.get("counter_thesis"), composite.get("contradicting_reason_codes")),
            "why_interesting": {"research_priority_tier": (record.get("opportunity_priority") or {}).get("research_priority_tier"),
                                "financial_composite_state": composite.get("financial_composite_state"),
                                "evidence_axis_coherence": (record.get("evidence_axis_coherence") or {}).get("state")},
            "confirms": {"trigger_state": trigger["state"], "trigger_type": trigger["type"],
                         "condition_identity": trigger["condition_identity"]},
            "invalidates": {"available": invalidation["available"], "method": invalidation["method"],
                            "condition_identity": invalidation["condition_identity"]},
            "dimension_states": by_state,
            "proxy_dimensions": [name for name in DIMENSIONS if dimensions[name]["authority"] == RESEARCH_PROXY],
            "exact_or_qualified_dimensions": [name for name in DIMENSIONS
                                              if dimensions[name]["authority"] in (EXACT_QUALIFIED, RESEARCH_QUALIFIED)],
            "authority_distribution": dict(sorted(by_authority.items())),
            "research_action_posture": posture,
            "action_posture_gated_by_current_evidence": (
                posture == "INSUFFICIENT_CURRENT_RESEARCH" and klass not in (CLASS_INSUFFICIENT, CLASS_OUT_OF_SCOPE)),
        },
        "provenance": {
            "decision_identity": record.get("decision_identity"),
            "temporal": {
                "decision_session": session,
                "evidence_currency": record.get("evidence_currency"),
                "technical_feature_as_of_session": (disposition_record or {}).get("feature_as_of_session"),
                "financial_as_of_period": dimensions["FUNDAMENTAL"]["as_of_financial_period"],
                "financial_freshness_status": dimensions["FUNDAMENTAL"]["freshness"]["freshness_status"],
                "corporate_evidence_session": dimensions["CORPORATE"]["evidence_session"],
            },
            "warnings": _codes(record.get("material_uncertainties")),
            "exact_capabilities_unavailable": _codes(record.get("exact_capabilities_unavailable")),
        },
        "authority_boundary": {
            "current_research_only": True,
            "historical_pit_authority": False,
            "exact_valuation_authority": dimensions["VALUATION"]["authority"] == EXACT_QUALIFIED,
            "execution_authority": dimensions["LIQUIDITY"]["execution"]["state"] == AVAILABLE,
            "evidence_class_is_not_action_posture": True,
            "no_score_rank_target_or_probability": True,
            "is_actionable": False,
        },
    }


def coverage(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    inputs = [record.get("current_research_decision_input") or {} for record in records.values()]
    return {
        "contract_version": CONTRACT_VERSION,
        "denominator": COVERAGE_DENOMINATOR,
        "denominator_count": len(inputs),
        "fundamental_freshness_distribution": dict(sorted(Counter(
            str((((item.get("dimensions") or {}).get("FUNDAMENTAL") or {}).get("freshness") or {}).get("freshness_status"))
            for item in inputs).items())),
        "fundamental_evidence_availability_distribution": dict(sorted(Counter(
            str(((item.get("dimensions") or {}).get("FUNDAMENTAL") or {}).get("fundamental_evidence_availability"))
            for item in inputs).items())),
        "evidence_class_distribution": {name: sum(item.get("evidence_class") == name for item in inputs)
                                        for name in EVIDENCE_CLASSES},
        "dimension_state_distribution": {
            name: {state: sum(((item.get("dimensions") or {}).get(name) or {}).get("state") == state for item in inputs)
                   for state in DIMENSION_STATES}
            for name in DIMENSIONS
        },
        "valuation_evidence_class_distribution": dict(sorted(Counter(
            ((item.get("dimensions") or {}).get("VALUATION") or {}).get("evidence_class") for item in inputs).items())),
        "fundamental_bridge_distribution": dict(sorted(Counter(
            (((item.get("dimensions") or {}).get("FUNDAMENTAL") or {}).get("operational_bridge") or {}).get("state")
            for item in inputs).items())),
        "action_posture_gated_by_current_evidence": sum(
            (item.get("synthesis") or {}).get("action_posture_gated_by_current_evidence") is True for item in inputs),
        "qualified_liquidity": _qualified_liquidity_coverage(inputs),
    }


def _qualified_liquidity_coverage(inputs: list[Mapping[str, Any]]) -> dict[str, Any]:
    qualified = [((item.get("dimensions") or {}).get("LIQUIDITY") or {}).get("qualified_research") for item in inputs]
    supplied = [item for item in qualified if isinstance(item, Mapping)]
    envelopes = [item.get("execution_capacity_research") or {} for item in supplied]
    return {
        "official_supplied": len(supplied),
        "current_session_liquidity_research_eligible": sum(
            (item.get("fitness") or {}).get("CURRENT_SESSION_LIQUIDITY_RESEARCH") == "ELIGIBLE" for item in supplied
        ),
        "adtv_research_eligible": sum((item.get("fitness") or {}).get("ADTV_RESEARCH") == "ELIGIBLE" for item in supplied),
        "adv_volume_research_partial": sum(
            (item.get("fitness") or {}).get("ADV_VOLUME_RESEARCH") in ("ELIGIBLE", "PARTIAL") for item in supplied
        ),
        "execution_capacity_state_distribution": dict(sorted(Counter(
            str(envelope.get("state")) for envelope in envelopes).items())),
        "policy_unbound": sum("POLICY_UNBOUND" in (envelope.get("reason_codes") or []) for envelope in envelopes),
        "live_position_sizing": BLOCKED,
        "pit_backtest": BLOCKED,
        "execution_replay": BLOCKED,
        "raw_as_traded": "NOT_PROMOTED",
        "adv_volume_basis": "AS_TRADED_NOT_CA_NORMALIZED",
        "per_record_fitness_is_authoritative": True,
    }


# ── Current Research coverage / decision-fitness read model ──────────────────

DECISION_FITNESS_CONTRACT_VERSION = "current_research_coverage_decision_fitness/v1"

FITNESS_FULL = "FULL_MULTI_FACTOR_CURRENT_RESEARCH"
FITNESS_PARTIAL = "PARTIAL_MULTI_FACTOR_CURRENT_RESEARCH"
FITNESS_LIMITED = "LIMITED_SINGLE_LANE_CURRENT_RESEARCH"
FITNESS_BLOCKED = "BLOCKED_CURRENT_RESEARCH"
FITNESS_OUTSIDE_SCOPE = "OUTSIDE_CURRENT_RESEARCH_SCOPE"
DECISION_FITNESS_STATES = (
    FITNESS_FULL, FITNESS_PARTIAL, FITNESS_LIMITED, FITNESS_BLOCKED, FITNESS_OUTSIDE_SCOPE,
)


def _decision_fitness_state(item: Mapping[str, Any]) -> str:
    """Map the existing evidence class to a product-level coverage state.

    This is a read model only. It never changes research_action_posture and never
    promotes a dimension authority. A posture explicitly gated by missing current
    evidence remains BLOCKED even if other dimensions are present.
    """
    evidence_class = item.get("evidence_class")
    gated = (item.get("synthesis") or {}).get("action_posture_gated_by_current_evidence") is True
    if evidence_class == CLASS_OUT_OF_SCOPE:
        return FITNESS_OUTSIDE_SCOPE
    if evidence_class == CLASS_INSUFFICIENT or gated:
        return FITNESS_BLOCKED
    if evidence_class == CLASS_FULL:
        return FITNESS_FULL
    if evidence_class == CLASS_PARTIAL:
        return FITNESS_PARTIAL
    if evidence_class in {CLASS_TECHNICAL, CLASS_FINANCIAL}:
        return FITNESS_LIMITED
    return FITNESS_BLOCKED


def build_ticker_decision_fitness(item: Mapping[str, Any]) -> dict[str, Any]:
    """Return one deterministic coverage/fitness view over a decision-input record."""
    if item.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("CURRENT_RESEARCH_DECISION_INPUT_CONTRACT_REQUIRED")
    dimensions = item.get("dimensions")
    if not isinstance(dimensions, Mapping) or any(name not in dimensions for name in DIMENSIONS):
        raise ValueError("CURRENT_RESEARCH_DECISION_INPUT_DIMENSIONS_INVALID")

    state = _decision_fitness_state(item)
    missing_primary = {
        name: list((dimensions.get(name) or {}).get("reason_codes") or [])
        for name in PRIMARY_FACTORS
        if (dimensions.get(name) or {}).get("state") != AVAILABLE
    }
    proxy_dimensions = [
        name for name in DIMENSIONS
        if (dimensions.get(name) or {}).get("authority") == RESEARCH_PROXY
    ]
    return {
        "contract_version": DECISION_FITNESS_CONTRACT_VERSION,
        "ticker": item.get("ticker"),
        "session": item.get("session"),
        "decision_fitness_state": state,
        "research_usable": state in {FITNESS_FULL, FITNESS_PARTIAL, FITNESS_LIMITED},
        "evidence_class": item.get("evidence_class"),
        "dimension_states": {
            name: (dimensions.get(name) or {}).get("state") for name in DIMENSIONS
        },
        "dimension_authorities": {
            name: (dimensions.get(name) or {}).get("authority") for name in DIMENSIONS
        },
        "missing_primary_factors": missing_primary,
        "proxy_dimensions": proxy_dimensions,
        "research_action_posture": (item.get("synthesis") or {}).get("research_action_posture"),
        "action_posture_gated_by_current_evidence": (
            (item.get("synthesis") or {}).get("action_posture_gated_by_current_evidence") is True
        ),
        "authority_boundary": {
            "read_model_only": True,
            "does_not_change_research_action_posture": True,
            "does_not_promote_dimension_authority": True,
            "no_score_rank_target_or_probability": True,
            "is_actionable": False,
        },
    }


def decision_fitness_coverage(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate market-wide coverage using only existing Current Research decision inputs."""
    views: dict[str, dict[str, Any]] = {}
    dimension_state: dict[str, Counter[str]] = {name: Counter() for name in DIMENSIONS}
    dimension_authority: dict[str, Counter[str]] = {name: Counter() for name in DIMENSIONS}
    gap_reason_counts: Counter[tuple[str, str]] = Counter()
    non_applicable_reason_counts: Counter[tuple[str, str]] = Counter()

    for ticker, record in sorted(records.items()):
        item = record.get("current_research_decision_input") or record
        view = build_ticker_decision_fitness(item)
        views[ticker] = view
        dimensions = item.get("dimensions") or {}
        for name in DIMENSIONS:
            dim = dimensions.get(name) or {}
            state = str(dim.get("state"))
            authority = str(dim.get("authority"))
            dimension_state[name][state] += 1
            dimension_authority[name][authority] += 1
            reasons = [str(code) for code in dim.get("reason_codes") or [] if isinstance(code, str)]
            if state in {PARTIAL, BLOCKED}:
                for code in set(reasons):
                    gap_reason_counts[(name, code)] += 1
            elif state == NON_APPLICABLE:
                for code in set(reasons):
                    non_applicable_reason_counts[(name, code)] += 1

    fitness_counts = Counter(view["decision_fitness_state"] for view in views.values())
    evidence_class_counts = Counter(view["evidence_class"] for view in views.values())
    posture_counts = Counter(str(view.get("research_action_posture")) for view in views.values())
    primary_gap_combinations = Counter(
        "+".join(sorted(view["missing_primary_factors"])) or "NONE"
        for view in views.values()
    )
    gap_prevalence = [
        {"dimension": dimension, "reason_code": reason, "affected_tickers": count}
        for (dimension, reason), count in sorted(
            gap_reason_counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
        )
    ]
    non_applicable_prevalence = [
        {"dimension": dimension, "reason_code": reason, "affected_tickers": count}
        for (dimension, reason), count in sorted(
            non_applicable_reason_counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
        )
    ]
    return {
        "contract_version": DECISION_FITNESS_CONTRACT_VERSION,
        "denominator": COVERAGE_DENOMINATOR,
        "denominator_count": len(views),
        "decision_fitness_distribution": dict(sorted(fitness_counts.items())),
        "research_usable_count": sum(
            fitness_counts[state] for state in (FITNESS_FULL, FITNESS_PARTIAL, FITNESS_LIMITED)
        ),
        "blocked_current_research_count": fitness_counts[FITNESS_BLOCKED],
        "outside_scope_count": fitness_counts[FITNESS_OUTSIDE_SCOPE],
        "evidence_class_distribution": dict(sorted(evidence_class_counts.items())),
        "dimension_state_distribution": {
            name: dict(sorted(dimension_state[name].items())) for name in DIMENSIONS
        },
        "dimension_authority_distribution": {
            name: dict(sorted(dimension_authority[name].items())) for name in DIMENSIONS
        },
        "dimension_available_count": {
            name: dimension_state[name][AVAILABLE] for name in DIMENSIONS
        },
        "proxy_dimension_count": {
            name: dimension_authority[name][RESEARCH_PROXY] for name in DIMENSIONS
        },
        "research_action_posture_distribution": dict(sorted(posture_counts.items())),
        "action_posture_gated_by_current_evidence_count": sum(
            view["action_posture_gated_by_current_evidence"] for view in views.values()
        ),
        "primary_factor_gap_combination_distribution": dict(sorted(primary_gap_combinations.items())),
        "gap_reason_prevalence": gap_prevalence,
        "non_applicable_reason_prevalence": non_applicable_prevalence,
        "interpretation_boundary": {
            "counts_are_descriptive_not_priority_scores": True,
            "missing_high_authority_is_local_to_dependent_use": True,
            "research_proxy_remains_proxy": True,
            "historical_pit_and_execution_authority_not_inferred": True,
        },
    }


def build_decision_fitness_artifact(*, integrated_decision_artifact: Mapping[str, Any],
                                    requested_at: str | None = None) -> dict[str, Any]:
    """Build a deterministic read-model artifact from an Integrated Decision artifact."""
    records = integrated_decision_artifact.get("records")
    session = integrated_decision_artifact.get("session")
    if not isinstance(records, Mapping) or not records:
        raise ValueError("INTEGRATED_DECISION_RECORDS_REQUIRED")
    if not isinstance(session, str) or not session:
        raise ValueError("INTEGRATED_DECISION_SESSION_REQUIRED")
    coverage_view = decision_fitness_coverage(records)
    per_ticker = {
        ticker: build_ticker_decision_fitness(record.get("current_research_decision_input") or record)
        for ticker, record in sorted(records.items())
    }
    payload: dict[str, Any] = {
        "schema_version": "current_research_coverage_decision_fitness/1.0.0",
        "contract_version": DECISION_FITNESS_CONTRACT_VERSION,
        "session": session,
        "requested_at": requested_at,
        "source_artifact_identity": integrated_decision_artifact.get("artifact_identity"),
        "coverage": coverage_view,
        "records": per_ticker,
        "authority_boundary": {
            "read_model_only": True,
            "does_not_change_research_action_posture": True,
            "does_not_promote_dimension_authority": True,
            "historical_pit_authority": False,
            "execution_authority": False,
            "no_score_rank_target_or_probability": True,
            "is_actionable": False,
        },
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                           allow_nan=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    payload["artifact_sha256"] = digest
    payload["artifact_identity"] = f"current_research_coverage_decision_fitness:{digest}"
    return payload
