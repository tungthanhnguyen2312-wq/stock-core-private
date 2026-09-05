"""Daily Integrated Decision Brief (DAILY_INTEGRATED_DECISION_BRIEF_AND_PROSPECTIVE_FEEDBACK_V1).

The successor daily product boundary for ``current_daily_decision_research_product/v2``: a compact,
AI-facing, single-artifact answer to "what does today's completed session mean" -- market regime,
sector leadership, deterministic opportunity sets, the canonical 11-ticker owner watchlist, what
changed since the previous qualified session, and prospective feedback status. Named as its own
contract (``daily_integrated_decision_brief/v1``) rather than literally reusing the
``current_daily_decision_research_product`` name because the shape is genuinely disjoint from that
contract's per-ticker research-card browsing product, which stays untouched for its own real
consumers (``daily_research_session_operations.py``, ``export_ai_bundle.py``,
``ai_research_session_delivery.py``) -- see ``docs/DECISIONS.md`` for the naming rationale.

This module is a pure JOIN over already-governed evidence. It recomputes nothing:
* ``integrated_investment_decision_product/v1`` supplies every per-ticker posture/phase/trigger/
  invalidation/valuation/participation/why-now/counter-thesis fact.
* ``next_session_decision_brief/v2`` supplies every current-vs-previous-session comparison
  (market_transition, sector_transition, opportunity_transition, posture_transition).
* ``current_market_sector_leadership_context/v1`` supplies per-sector breadth/leadership.
* ``current_opportunity_prioritization/v1`` supplies the optional secondary priority-tier ordering.
* ``owner_research_focus.broader_watchlist()`` supplies the governed 11-ticker canonical watchlist.
* ``integrated_decision_prospective_feedback.py`` supplies the prospective-outcome feedback status.

No universal score, rank, target price, or probability is introduced anywhere in this module.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import daily_session_level2_package as level2
import integrated_decision_prospective_feedback as feedback_bridge
import owner_research_focus

CONTRACT_VERSION = "daily_integrated_decision_brief/v1"
SCHEMA_VERSION = "1.0.0"
POLICY_VERSION = "v1"

# ── Deterministic ordering (section 5): posture class, then governed priority tier, then trigger
# state/distance, then participation confirmation, then a stable ticker tie-break. No hidden weight.
_POSTURE_ORDER_RANK = {
    "INITIATE_ON_BREAKOUT": 0, "ACCUMULATE_ON_RETEST": 1, "EARLY_WATCH": 2, "HOLD": 3,
    "HOLD_DO_NOT_ADD": 4, "WAIT_FOR_CONFIRMATION": 5, "REDUCE": 6, "AVOID": 7,
    "INSUFFICIENT_CURRENT_RESEARCH": 8,
}
_PRIORITY_TIER_RANK = {"PRIORITY_NOW": 0, "SETUP_WATCH": 1, "MONITOR": 2, "DATA_LIMITED": 3, "EXCLUDED": 4}
_TRIGGER_STATE_RANK = {"TRIGGERED": 0, "APPROACHING": 1, "BELOW_TRIGGER": 2, "NOT_AVAILABLE": 3}
ORDERING_METHOD = (
    "Ascending tuple sort: (1) research_action_posture class rank (INITIATE_ON_BREAKOUT best), "
    "(2) current_opportunity_prioritization/v1 priority_tier rank when the ticker is present there "
    "(PRIORITY_NOW best; DATA_LIMITED/absent worst), (3) trigger.trigger_state rank (TRIGGERED best) "
    "then |distance_to_trigger_pct| ascending, (4) participation confirmation before contradiction "
    "before unavailable, (5) ticker ascending as the stable tie-break. No hidden numeric weighting; "
    "every component is an already-governed evidence field."
)

# ── Opportunity set classification (sections 4-5): a complete, non-overlapping partition of the
# 9-value research_action_posture vocabulary. Sector context never participates (section 3: sector
# strength must not create a BUY signal).
ACTIONABLE_NOW, RETEST_CANDIDATES, EARLY_SETUPS = "ACTIONABLE_NOW", "RETEST_CANDIDATES", "EARLY_SETUPS"
EXTENDED_DO_NOT_CHASE, HOLD_MANAGE, RISK_AVOID = "EXTENDED_DO_NOT_CHASE", "HOLD_MANAGE", "RISK_AVOID"
INSUFFICIENT_RESEARCH = "INSUFFICIENT_RESEARCH"
OPPORTUNITY_SET_NAMES = (ACTIONABLE_NOW, EARLY_SETUPS, RETEST_CANDIDATES, EXTENDED_DO_NOT_CHASE, HOLD_MANAGE, RISK_AVOID, INSUFFICIENT_RESEARCH)
_EARLY_SETUP_PHASES = frozenset({"EARLY_REVERSAL", "BREAKOUT_SETUP", "BASE_BUILDING", "RETEST_AFTER_BREAKOUT"})


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = {k: v for k, v in artifact.items() if k not in {"artifact_sha256", "artifact_identity", "requested_at"}}
    digest = hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def classify_opportunity_set(record: Mapping[str, Any]) -> str:
    """Pure function of an integrated_investment_decision_product/v1 ticker record's own posture
    and tactical_phase -- never re-derives or overrides the posture policy itself."""
    posture = record.get("research_action_posture")
    phase = record.get("tactical_phase")
    if posture == "INITIATE_ON_BREAKOUT":
        return ACTIONABLE_NOW
    if posture == "ACCUMULATE_ON_RETEST":
        return RETEST_CANDIDATES
    if posture == "EARLY_WATCH":
        return EARLY_SETUPS
    if posture == "WAIT_FOR_CONFIRMATION":
        return EARLY_SETUPS if phase in _EARLY_SETUP_PHASES else HOLD_MANAGE
    if posture == "HOLD_DO_NOT_ADD":
        return EXTENDED_DO_NOT_CHASE
    if posture == "HOLD":
        return HOLD_MANAGE
    if posture in ("AVOID", "REDUCE"):
        return RISK_AVOID
    return INSUFFICIENT_RESEARCH


def _participation_confirmation_state(record: Mapping[str, Any]) -> str:
    """Presentation-layer label over already-computed evidence strings -- never a new threshold.

    integrated_investment_decision_product.py computes a local part_contradiction flag inside
    decide_research_action_posture() but does not store it on the record; this recovers the same
    signal by checking the counter_thesis/participation_support markers it already merges in.
    """
    participation = record.get("participation") or {}
    if participation.get("status") != "AVAILABLE":
        return "NOT_AVAILABLE"
    counters = record.get("counter_thesis") or []
    if any("VOLUME_CONTRACTION" in item or "RELATIVE_VOLUME_LOWER_QUARTILE" in item for item in counters):
        return "CONTRADICTED"
    supports = record.get("participation_support") or []
    if any("VOLUME_ACCELERATION" in item or "RELATIVE_VOLUME_UPPER_QUARTILE" in item or "ELEVATED_SESSION_RELATIVE_VOLUME" in item for item in supports):
        return "CONFIRMED"
    return "NEUTRAL"


def _ordering_key(record: Mapping[str, Any], priority_tier_by_ticker: Mapping[str, str]) -> tuple:
    trigger = record.get("trigger") or {}
    distance = trigger.get("distance_to_trigger_pct")
    part_state = _participation_confirmation_state(record)
    part_rank = {"CONFIRMED": 0, "NEUTRAL": 1, "CONTRADICTED": 2, "NOT_AVAILABLE": 3}[part_state]
    return (
        _POSTURE_ORDER_RANK.get(record.get("research_action_posture"), 99),
        _PRIORITY_TIER_RANK.get(priority_tier_by_ticker.get(record["ticker"]), 99),
        _TRIGGER_STATE_RANK.get(trigger.get("trigger_state"), 99),
        abs(distance) if isinstance(distance, (int, float)) else 999.0,
        part_rank,
        record["ticker"],
    )


def _compact_opportunity_row(record: Mapping[str, Any], priority_tier_by_ticker: Mapping[str, str]) -> dict[str, Any]:
    trigger = record.get("trigger") or {}
    return {
        "ticker": record["ticker"], "research_action_posture": record.get("research_action_posture"),
        "tactical_phase": record.get("tactical_phase"), "fundamental_state": record.get("fundamental_state"),
        "trigger_state": trigger.get("trigger_state"), "distance_to_trigger_pct": trigger.get("distance_to_trigger_pct"),
        "participation_confirmation_state": _participation_confirmation_state(record),
        "research_priority_tier": priority_tier_by_ticker.get(record["ticker"]),
        "why_now": record.get("why_now"), "decision_identity": record.get("decision_identity"),
    }


def build_opportunity_sets(current_records: Mapping[str, Mapping[str, Any]], opportunity_prioritization: Mapping[str, Any] | None) -> dict[str, Any]:
    """Sections 4-5: deterministic opportunity sets plus ordered shortlists. No universal score."""
    priority_records = (opportunity_prioritization or {}).get("records") or {}
    priority_tier_by_ticker = {ticker: row.get("priority_tier") for ticker, row in priority_records.items() if isinstance(row, Mapping)}
    buckets: dict[str, list[str]] = {name: [] for name in OPPORTUNITY_SET_NAMES}
    for ticker, record in current_records.items():
        buckets[classify_opportunity_set(record)].append(ticker)
    sets: dict[str, Any] = {}
    for name, tickers in buckets.items():
        ordered = sorted(tickers, key=lambda t: _ordering_key(current_records[t], priority_tier_by_ticker))
        sets[name] = {"tickers": ordered, "count": len(ordered)}
    top_now = sorted(buckets[ACTIONABLE_NOW], key=lambda t: _ordering_key(current_records[t], priority_tier_by_ticker))[:10]
    top_early = sorted(buckets[EARLY_SETUPS], key=lambda t: _ordering_key(current_records[t], priority_tier_by_ticker))[:10]
    risk_ordered = sorted(buckets[RISK_AVOID], key=lambda t: _ordering_key(current_records[t], priority_tier_by_ticker))[:10]
    return {
        "sets": sets,
        "set_counts": {name: len(buckets[name]) for name in OPPORTUNITY_SET_NAMES},
        "ordering_method": ORDERING_METHOD,
        "top_current_opportunities": [_compact_opportunity_row(current_records[t], priority_tier_by_ticker) for t in top_now],
        "top_early_setups": [_compact_opportunity_row(current_records[t], priority_tier_by_ticker) for t in top_early],
        "highest_risk_names": [_compact_opportunity_row(current_records[t], priority_tier_by_ticker) for t in risk_ordered],
        "priority_tier_source_identity": (opportunity_prioritization or {}).get("artifact_identity"),
        "authority_boundary": {"no_universal_score": True, "no_probability_or_target": True, "priority_tier_optional_secondary_ordering_only": True},
    }


# ── Market / Sector summary (sections 2-3) ──────────────────────────────────────────────────────

def build_market_summary(*, descriptive: Mapping[str, Any] | None, sector_leadership: Mapping[str, Any] | None,
                          current_records: Mapping[str, Mapping[str, Any]], market_transition: Mapping[str, Any] | None) -> dict[str, Any]:
    breadth = (descriptive or {}).get("market_breadth") or {}
    market = (sector_leadership or {}).get("market") or {}
    groups = ((sector_leadership or {}).get("groups") or {}).get("records") or {}
    leading_groups = sum(1 for row in groups.values() if row.get("leadership_state") == "LEADING")
    available_groups = ((sector_leadership or {}).get("groups") or {}).get("available_group_count") or 0
    phase_dist = Counter(record.get("tactical_phase") for record in current_records.values())
    posture_dist = Counter(record.get("research_action_posture") for record in current_records.values())
    fundamental_dist = Counter(record.get("fundamental_state") for record in current_records.values())
    composite_dist = Counter((record.get("financial_composite_context") or {}).get("financial_composite_state") for record in current_records.values())
    part_states = Counter(_participation_confirmation_state(record) for record in current_records.values())
    market_regime = market.get("current_breadth_state") or "NOT_AVAILABLE"
    return {
        "status": "AVAILABLE" if descriptive is not None else "UNAVAILABLE",
        "market_regime": market_regime,
        "market_regime_source": "current_market_sector_leadership_context/v1:market.current_breadth_state",
        "is_defensive_or_weak_regime": market_regime == "DETERIORATING_BREADTH",
        "breadth": {
            "advancing": breadth.get("advancing"), "declining": breadth.get("declining"), "unchanged": breadth.get("unchanged"),
            "advance_ratio": breadth.get("advance_ratio"), "breadth_descriptor": (breadth.get("breadth_descriptor") or {}).get("descriptor"),
            "momentum_descriptor": (breadth.get("momentum_descriptor") or {}).get("descriptor"),
        },
        "breadth_transition_vs_previous_session": market_transition or {"availability": "UNAVAILABLE", "reason_codes": ["MARKET_TRANSITION_NOT_SUPPLIED"]},
        "technical_participation_coverage": {
            "same_session_technical_feature_available_count": breadth.get("same_session_technical_feature_available_count"),
            "current_active_equity_denominator": breadth.get("current_active_equity_denominator"),
        },
        "breakout_participation": {
            "breakout_confirmed_count": phase_dist.get("BREAKOUT_CONFIRMED", 0), "extended_count": phase_dist.get("EXTENDED", 0),
            "breakdown_count": phase_dist.get("BREAKDOWN", 0), "distribution_risk_count": phase_dist.get("DISTRIBUTION_RISK", 0),
        },
        "relative_volume_participation_breadth": {
            "confirmed_count": part_states.get("CONFIRMED", 0), "contradicted_count": part_states.get("CONTRADICTED", 0),
            "neutral_count": part_states.get("NEUTRAL", 0), "not_available_count": part_states.get("NOT_AVAILABLE", 0),
        },
        "sector_leadership_concentration": {
            "leading_sector_group_count": leading_groups, "available_sector_group_count": available_groups,
            "concentration_ratio": (leading_groups / available_groups) if available_groups else None,
        },
        "research_action_posture_distribution": dict(sorted(posture_dist.items())),
        "fundamental_state_distribution": dict(sorted(fundamental_dist.items())),
        "financial_composite_state_distribution": dict(sorted((k, v) for k, v in composite_dist.items() if k is not None)),
        "authority_boundary": {"deterministic_technical_inference_only": True, "not_institutional_or_order_flow_proof": True, "sector_strength_never_a_buy_signal": True},
    }


def build_sector_summary(*, sector_leadership: Mapping[str, Any] | None, current_records: Mapping[str, Mapping[str, Any]],
                          sector_transition: Mapping[str, Any] | None, watchlist_tickers: Sequence[str]) -> dict[str, Any]:
    groups = ((sector_leadership or {}).get("groups") or {}).get("records") or {}
    ticker_contexts = (sector_leadership or {}).get("ticker_contexts") or {}
    if not groups:
        return {"status": "UNAVAILABLE", "reason_codes": ["SECTOR_LEADERSHIP_ARTIFACT_NOT_SUPPLIED_OR_NO_AVAILABLE_GROUPS"], "sectors": []}
    ticker_to_group: dict[str, str] = {}
    for ticker, row in ticker_contexts.items():
        group_key = ((row or {}).get("sector_leadership_context") or {}).get("group_key")
        if group_key:
            ticker_to_group[ticker] = group_key
    watch_set = set(watchlist_tickers)
    transition_sectors = (sector_transition or {}).get("sectors") or {}
    rows = []
    for group_key, group in sorted(groups.items()):
        member_tickers = [t for t, gk in ticker_to_group.items() if gk == group_key and t in current_records]
        postures = Counter(current_records[t].get("research_action_posture") for t in member_tickers)
        breakout_count = sum(1 for t in member_tickers if current_records[t].get("breakout_state_v3") == "BREAKOUT")
        breakdown_count = sum(1 for t in member_tickers if current_records[t].get("tactical_phase") == "BREAKDOWN")
        rows.append({
            "group_key": group_key, "sector_label": group.get("group_identity"), "group_scope": group.get("group_scope"),
            "current_breadth_status": group.get("status"), "relative_strength_leadership_state": group.get("leadership_state"),
            "breadth_transition_vs_previous_session": transition_sectors.get(group_key, {"transition": "UNAVAILABLE", "reason": "SECTOR_KEY_NOT_FOUND_IN_TRANSITION"}),
            "universe_member_count": group.get("universe_member_count"), "exact_session_observed_count": group.get("exact_session_observed_count"),
            "posture_counts": {
                "INITIATE_ON_BREAKOUT": postures.get("INITIATE_ON_BREAKOUT", 0), "ACCUMULATE_ON_RETEST": postures.get("ACCUMULATE_ON_RETEST", 0),
                "EARLY_WATCH": postures.get("EARLY_WATCH", 0), "AVOID": postures.get("AVOID", 0),
            },
            "breakout_count": breakout_count, "breakdown_count": breakdown_count,
            "watchlist_membership_count": sum(1 for t in member_tickers if t in watch_set),
        })
    return {
        "status": "AVAILABLE", "sectors": rows, "sector_count": len(rows),
        "authority_boundary": {"explanatory_confidence_context_only": True, "sector_strength_never_a_buy_signal": True},
    }


# ── Watchlist-11 (section 6) ────────────────────────────────────────────────────────────────────

def _financial_context_for_ticker(
    financial_analysis_product_current: Mapping[str, Any] | None, ticker: str,
) -> dict[str, Any]:
    """Pass through the existing compact Financial V2 record for one AI-facing ticker.

    The Daily brief must not reconstruct financial measurements from statements.  It only joins
    the already product-safe ``financial_analysis_product_integration/v1`` projection, whose
    record explicitly carries AVAILABLE/ABSENT and fitness/lineage limits.  This keeps the
    financial reporting clock distinct from the Daily decision-session clock.
    """
    if not financial_analysis_product_current:
        return {
            "status": "UNAVAILABLE",
            "reason_codes": ["FINANCIAL_ANALYSIS_PRODUCT_NOT_SUPPLIED"],
            "is_actionable": False,
        }
    product = financial_analysis_product_current.get("financial_analysis_product") or {}
    records = product.get("records") if isinstance(product, Mapping) else None
    if not isinstance(records, Mapping):
        return {
            "status": "UNAVAILABLE",
            "reason_codes": ["FINANCIAL_ANALYSIS_PRODUCT_RECORDS_INVALID"],
            "source_context_identity": product.get("artifact_identity") if isinstance(product, Mapping) else None,
            "is_actionable": False,
        }
    record = records.get(ticker)
    if not isinstance(record, Mapping):
        return {
            "status": "UNAVAILABLE",
            "reason_codes": ["FINANCIAL_ANALYSIS_PRODUCT_TICKER_MISSING"],
            "source_context_identity": product.get("artifact_identity"),
            "is_actionable": False,
        }
    # The compact projection intentionally excludes raw engine records.  A shallow copy avoids
    # allowing later brief assembly to mutate the retained product payload.
    return dict(record)


def _research_safe_valuation_methods(methods: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep valuation method fitness/context while excluding prohibited target/probability fields.

    Current Research uses the retained methods to explain availability, basis, peer compatibility,
    and blockers.  It does not emit intrinsic value, fair value, target price, or probability.
    """
    result: dict[str, Any] = {}
    for method_id, method in (methods or {}).items():
        if isinstance(method, Mapping):
            result[str(method_id)] = {
                key: value for key, value in method.items()
                if key not in {"fair_value", "target_price", "probability"}
            }
    return result


def build_watchlist_record(*, ticker: str, current: Mapping[str, Any] | None, tactical_raw: Mapping[str, Any] | None,
                            sector_label: str | None, posture_transition_row: Mapping[str, Any] | None,
                            financial_analysis: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if current is None:
        return {
            "ticker": ticker, "status": "NOT_AVAILABLE_IN_CURRENT_INTEGRATED_DECISION", "sector": sector_label,
            "posture_transition": posture_transition_row or {"transition": "NO_LONGER_AVAILABLE"},
            "financial_analysis": dict(financial_analysis or {
                "status": "UNAVAILABLE", "reason_codes": ["FINANCIAL_ANALYSIS_PRODUCT_NOT_SUPPLIED"],
                "is_actionable": False,
            }),
        }
    val = current.get("valuation_context_summary") or {}
    trig = current.get("trigger") or {}
    inv = current.get("invalidation") or {}
    part = current.get("participation") or {}
    legacy = current.get("legacy_comparison") or {}
    return {
        "ticker": ticker, "status": "AVAILABLE", "sector": sector_label,
        "research_action_posture": current.get("research_action_posture"),
        "legacy_stance": legacy.get("legacy_stance"),
        "posture_transition": (posture_transition_row or {}).get("transition", "UNAVAILABLE"),
        "fundamental_state": current.get("fundamental_state"), "fundamental_support": current.get("fundamental_support"),
        # The compact Financial V2 context contains only deterministic direction/state, feature
        # fitness, own-history context, blocker reasons, and lineage.  It is deliberately not a
        # raw statement export or an invitation for AI to recompute a metric.
        "financial_analysis": dict(financial_analysis or {
            "status": "UNAVAILABLE", "reason_codes": ["FINANCIAL_ANALYSIS_PRODUCT_NOT_SUPPLIED"],
            "is_actionable": False,
        }),
        "valuation": {
            "status": val.get("status"), "pe_multiple": val.get("pe_multiple"), "pb_multiple": val.get("pb_multiple"),
            "ps_multiple": val.get("ps_multiple"), "ev_ebitda_multiple": val.get("ev_ebitda_multiple"),
            "peer_relative_state": val.get("peer_relative_state"),
            "own_history_state": val.get("own_history_state"),
        },
        # MARKET_WIDE_FUNDAMENTAL_VALUATION_ANALYTICAL_PRODUCT_V1 section 18: the AI-facing
        # product must expose the joined fundamental+valuation composite read alongside its own
        # supporting/contradicting reasons and uncertainty -- passthrough only, no recomputation.
        "financial_composite_context": current.get("financial_composite_context"),
        # Preserve every existing valuation method's status, basis, peer gate, and reconciliation
        # verbatim.  The brief does not choose a preferred multiple or convert blocked methods to
        # a conclusion.
        "valuation_methods": _research_safe_valuation_methods(current.get("valuation_methods")),
        "valuation_method_reconciliation": current.get("valuation_method_reconciliation") or {},
        "tactical_phase": current.get("tactical_phase"), "market_structure_state": current.get("market_structure_state"),
        "bos_state": (tactical_raw or {}).get("bos_state"), "choch_state": (tactical_raw or {}).get("choch_state"),
        "breakout_state": current.get("breakout_state_v3"),
        "participation": {
            "relative_volume_percentile": part.get("relative_volume_percentile"), "volume_acceleration_ratio": part.get("volume_acceleration_ratio"),
            "confirmation_state": _participation_confirmation_state(current),
        },
        "trigger_type": trig.get("trigger_type"), "trigger_level": trig.get("trigger_level"),
        "trigger_state": trig.get("trigger_state"), "distance_to_trigger_pct": trig.get("distance_to_trigger_pct"),
        "invalidation_level": inv.get("invalidation_level"), "invalidation_method": inv.get("invalidation_method"),
        "distance_to_invalidation_pct": inv.get("distance_to_invalidation_pct"),
        "why_now": current.get("why_now"), "counter_thesis": current.get("counter_thesis"),
        "material_uncertainties": current.get("material_uncertainties"),
        "missing_evidence_decision_effect": current.get("missing_evidence_decision_effect"),
        "security_attractiveness": {
            "research_action_posture": current.get("research_action_posture"), "tactical_phase": current.get("tactical_phase"),
            "fundamental_state": current.get("fundamental_state"),
        },
        "portfolio_action_context": current.get("portfolio_context"),
        "decision_identity": current.get("decision_identity"),
        "authority_boundary": {"no_target_price": True, "research_support_not_execution_instruction": True},
    }


def build_watchlist(*, current_records: Mapping[str, Mapping[str, Any]], tactical_raw_records: Mapping[str, Any] | None,
                     sector_leadership: Mapping[str, Any] | None, posture_transition: Mapping[str, Any] | None,
                     financial_analysis_product_current: Mapping[str, Any] | None = None) -> dict[str, Any]:
    tickers = list(owner_research_focus.broader_watchlist())
    ticker_contexts = (sector_leadership or {}).get("ticker_contexts") or {}
    tac_records = (tactical_raw_records or {}).get("records") or {}
    transition_records = (posture_transition or {}).get("records") or {}
    records = []
    for ticker in tickers:
        sector_ctx = ((ticker_contexts.get(ticker) or {}).get("sector_leadership_context") or {})
        sector_label = sector_ctx.get("group_key")
        records.append(build_watchlist_record(
            ticker=ticker, current=current_records.get(ticker), tactical_raw=tac_records.get(ticker),
            sector_label=sector_label, posture_transition_row=transition_records.get(ticker),
            financial_analysis=_financial_context_for_ticker(financial_analysis_product_current, ticker),
        ))
    return {
        "tickers": tickers, "count": len(tickers), "records": records,
        "authority_source": "owner_research_focus.broader_watchlist/v1", "role": "BROADER_WATCHLIST_NOT_PORTFOLIO_HOLDINGS",
        "available_count": sum(1 for row in records if row["status"] == "AVAILABLE"),
    }


# ── Decision transitions (section 7) / What changed today (section 8) ──────────────────────────

_TRANSITIONS_TOWARD_ACTIONABLE = frozenset({"NEW_BREAKOUT", "WAIT_TO_INITIATE", "EARLY_WATCH_TO_INITIATE"})


def build_decision_transitions(*, posture_transition: Mapping[str, Any] | None, watchlist_tickers: Sequence[str]) -> dict[str, Any]:
    posture_transition = posture_transition or {}
    records = posture_transition.get("records") or {}
    watch_set = set(watchlist_tickers)
    watchlist_transitions = {ticker: records[ticker] for ticker in watchlist_tickers if ticker in records}
    return {
        "availability": posture_transition.get("availability", "UNAVAILABLE"),
        "reason_codes": posture_transition.get("reason_codes", []),
        "transition_counts": posture_transition.get("transition_counts", {}),
        "watchlist_transitions": watchlist_transitions,
        "current_universe_count": posture_transition.get("current_universe_count"),
        "previous_universe_count": posture_transition.get("previous_universe_count"),
        "source_lineage": posture_transition.get("source_lineage", {}),
        "full_detail_source": "next_session_decision_brief/v2:posture_transition.records (full 1,683-ticker universe)",
    }


def build_what_changed_today(*, posture_transition: Mapping[str, Any] | None, market_transition: Mapping[str, Any] | None,
                              sector_transition: Mapping[str, Any] | None, watchlist_tickers: Sequence[str]) -> dict[str, Any]:
    records = (posture_transition or {}).get("records") or {}
    if not records:
        return {
            "availability": (posture_transition or {}).get("availability", "UNAVAILABLE"),
            "reason_codes": (posture_transition or {}).get("reason_codes", ["POSTURE_TRANSITION_NOT_AVAILABLE"]),
            "market_breadth_change": None, "sector_leadership_changes": None, "new_actionable_now": [], "new_early_setups": [],
            "new_failed_breakouts": [], "new_breakdowns": [], "names_becoming_extended": [], "watchlist_posture_changes": [],
        }

    def _tickers(pred) -> list[str]:
        return sorted(ticker for ticker, row in records.items() if pred(row))

    watch_set = set(watchlist_tickers)
    sector_changes = [
        {"group_key": key, "transition": row.get("transition")}
        for key, row in ((sector_transition or {}).get("sectors") or {}).items()
        if row.get("transition") not in (None, "UNCHANGED", "INSUFFICIENT_EVIDENCE")
    ]
    return {
        "availability": "AVAILABLE",
        "market_breadth_change": (market_transition or {}).get("transition"),
        "sector_leadership_changes": sorted(sector_changes, key=lambda row: row["group_key"]),
        "new_actionable_now": _tickers(lambda row: row["transition"] in _TRANSITIONS_TOWARD_ACTIONABLE),
        "new_early_setups": _tickers(lambda row: row["transition"] == "NEW_EARLY_WATCH"),
        "new_failed_breakouts": _tickers(lambda row: row["transition"] == "BREAKOUT_FAILED"),
        "new_breakdowns": _tickers(lambda row: row["transition"] == "UPTREND_TO_BREAKDOWN"),
        "names_becoming_extended": _tickers(lambda row: row["transition"] == "INITIATE_TO_EXTENDED"),
        "watchlist_posture_changes": sorted(
            ({"ticker": ticker, **records[ticker]} for ticker in (watch_set & records.keys()) if records[ticker]["transition"] != "POSTURE_UNCHANGED"),
            key=lambda row: row["ticker"],
        ),
        "is_ai_narrative": False,
    }


# ── Risk summary ─────────────────────────────────────────────────────────────────────────────

def build_risk_summary(*, current_records: Mapping[str, Mapping[str, Any]], watchlist_tickers: Sequence[str], what_changed_today: Mapping[str, Any]) -> dict[str, Any]:
    avoid = [t for t, r in current_records.items() if r.get("research_action_posture") == "AVOID"]
    reduce_ = [t for t, r in current_records.items() if r.get("research_action_posture") == "REDUCE"]
    breakdown = [t for t, r in current_records.items() if r.get("tactical_phase") == "BREAKDOWN"]
    distribution_risk = [t for t, r in current_records.items() if r.get("tactical_phase") == "DISTRIBUTION_RISK"]
    deteriorating = [t for t, r in current_records.items() if r.get("fundamental_state") == "DETERIORATING"]
    watch_set = set(watchlist_tickers)
    watchlist_at_risk = sorted(t for t in watch_set if current_records.get(t, {}).get("research_action_posture") in ("AVOID", "REDUCE") or current_records.get(t, {}).get("tactical_phase") == "BREAKDOWN")
    return {
        "avoid_count": len(avoid), "reduce_count": len(reduce_), "breakdown_count": len(breakdown),
        "distribution_risk_count": len(distribution_risk), "deteriorating_fundamental_count": len(deteriorating),
        "watchlist_at_risk": watchlist_at_risk,
        "new_breakdowns_today": what_changed_today.get("new_breakdowns", []),
        "new_failed_breakouts_today": what_changed_today.get("new_failed_breakouts", []),
        "authority_boundary": {"adverse_evidence_requires_actual_breakdown_or_deterioration": True, "extension_risk_kept_separate_from_avoid": True},
    }


# ── Financial evidence context (section 23: AI handoff must be able to say "fundamental
# evidence is based on FY/Q reporting period X, while market/technical evidence is session Y"
# without guessing) ──────────────────────────────────────────────────────────────────────────

def build_financial_evidence_context(financial_analysis_product_current: Mapping[str, Any] | None) -> dict[str, Any]:
    if not financial_analysis_product_current:
        return {"status": "UNAVAILABLE", "reason_codes": ["FINANCIAL_ANALYSIS_PRODUCT_NOT_SUPPLIED"]}
    compact = financial_analysis_product_current.get("financial_analysis_product") or {}
    return {
        "status": "AVAILABLE",
        "financial_analysis_product_identity": compact.get("artifact_identity"),
        "financial_v2_engine_identity": financial_analysis_product_current.get("financial_v2_engine_identity"),
        "financial_evidence_as_of_period": financial_analysis_product_current.get("financial_evidence_as_of_period"),
        "financial_evidence_period_range": financial_analysis_product_current.get("financial_evidence_period_range"),
        "decision_session": financial_analysis_product_current.get("decision_session"),
        "coverage": financial_analysis_product_current.get("coverage"),
        "note": "Financial evidence is periodic: an identical financial_v2_engine_identity across "
                "several consecutive decision sessions is normal and expected between real "
                "financial reports. Fundamental evidence is dated by financial_evidence_as_of_"
                "period; market/technical evidence is dated by session -- the two are not the "
                "same clock.",
    }


# ── Top-level assembly ──────────────────────────────────────────────────────────────────────────

def build_artifact(
    *,
    session: str,
    requested_at: str,
    integrated_decision_current: Mapping[str, Any],
    next_session_brief: Mapping[str, Any],
    descriptive_current: Mapping[str, Any] | None = None,
    sector_leadership_current: Mapping[str, Any] | None = None,
    tactical_current: Mapping[str, Any] | None = None,
    opportunity_prioritization_current: Mapping[str, Any] | None = None,
    feedback_status: Mapping[str, Any] | None = None,
    financial_analysis_product_current: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one daily_integrated_decision_brief/v1 artifact. Pure join; recomputes nothing."""
    if integrated_decision_current.get("session") != session:
        raise ValueError(f"INTEGRATED_DECISION_SESSION_MISMATCH:expected={session}:observed={integrated_decision_current.get('session')}")
    if next_session_brief.get("current_session") != session:
        raise ValueError(f"NEXT_SESSION_BRIEF_SESSION_MISMATCH:expected={session}:observed={next_session_brief.get('current_session')}")
    current_records = integrated_decision_current.get("records") or {}
    watchlist_tickers = list(owner_research_focus.broader_watchlist())

    market_summary = build_market_summary(
        descriptive=descriptive_current, sector_leadership=sector_leadership_current, current_records=current_records,
        market_transition=next_session_brief.get("market_transition"),
    )
    sector_summary = build_sector_summary(
        sector_leadership=sector_leadership_current, current_records=current_records,
        sector_transition=next_session_brief.get("sector_transition"), watchlist_tickers=watchlist_tickers,
    )
    opportunity_sets = build_opportunity_sets(current_records, opportunity_prioritization_current)
    watchlist = build_watchlist(
        current_records=current_records, tactical_raw_records=tactical_current, sector_leadership=sector_leadership_current,
        posture_transition=next_session_brief.get("posture_transition"),
        financial_analysis_product_current=financial_analysis_product_current,
    )
    decision_transitions = build_decision_transitions(posture_transition=next_session_brief.get("posture_transition"), watchlist_tickers=watchlist_tickers)
    what_changed_today = build_what_changed_today(
        posture_transition=next_session_brief.get("posture_transition"), market_transition=next_session_brief.get("market_transition"),
        sector_transition=next_session_brief.get("sector_transition"), watchlist_tickers=watchlist_tickers,
    )
    risk_summary = build_risk_summary(current_records=current_records, watchlist_tickers=watchlist_tickers, what_changed_today=what_changed_today)
    financial_evidence_context = build_financial_evidence_context(financial_analysis_product_current)

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION,
        "session": session, "previous_qualified_session": next_session_brief.get("previous_qualified_session"),
        "requested_at": requested_at, "policy_version": POLICY_VERSION,
        "market_summary": market_summary, "sector_summary": sector_summary,
        "opportunity_sets": opportunity_sets, "watchlist": watchlist,
        "decision_transitions": decision_transitions, "what_changed_today": what_changed_today,
        "risk_summary": risk_summary, "financial_evidence_context": financial_evidence_context,
        "feedback_status": feedback_status if feedback_status is not None else {"availability": "UNAVAILABLE", "reason_codes": ["FEEDBACK_STATUS_NOT_SUPPLIED"]},
        "coverage": {
            "universe_denominator": integrated_decision_current.get("coverage", {}).get("universe_denominator"),
            "integrated_context_available": integrated_decision_current.get("coverage", {}).get("integrated_context_available"),
            "watchlist_coverage": watchlist["available_count"],
        },
        "source_artifact_identities": {
            "integrated_investment_decision_product": integrated_decision_current.get("artifact_identity"),
            "next_session_decision_brief": next_session_brief.get("artifact_identity"),
            "descriptive_research": (descriptive_current or {}).get("artifact_identity"),
            "sector_leadership": (sector_leadership_current or {}).get("artifact_identity"),
            "tactical_classifier": (tactical_current or {}).get("artifact_identity"),
            "opportunity_prioritization": (opportunity_prioritization_current or {}).get("artifact_identity"),
            "financial_analysis_product": financial_evidence_context.get("financial_analysis_product_identity"),
        },
        "authority_boundary": {
            "is_actionable": False, "no_universal_score_rank_target_or_probability": True,
            "research_support_not_execution_instruction": True, "no_ai_narrative_generated_in_python": True,
        },
    }
    artifact.update(content_identity(artifact))
    return artifact


def _load_json(path: Path) -> Mapping[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def build_from_session(*, root: Path, session: str, next_session_brief: Mapping[str, Any]) -> dict[str, Any] | None:
    """CLI-level convenience mirroring next_session_decision_brief.build_from_previous_bundle_path:
    resolve every input from the canonical session-scoped path registry and build one artifact.

    Returns None (never raises) when the one hard requirement -- this session's own
    integrated_investment_decision_product artifact -- is not yet materialized (canonical post-close
    already auto-builds it; if it is genuinely missing this session should not silently fall back to
    a stale prior-session product per Section 15). Every other input degrades gracefully inside the
    section builders themselves.
    """
    paths = level2.session_artifact_paths(root, session)
    integrated_current = _load_json(paths["integrated_investment_decision_product"])
    if integrated_current is None:
        return None
    descriptive_current = _load_json(paths["descriptive_research"])
    sector_leadership_current = _load_json(paths["sector_leadership"])
    tactical_current = _load_json(paths["market_structure_breakout_v3_projection"])
    opportunity_prioritization_current = _load_json(paths["opportunity_prioritization"])
    financial_analysis_product_current = _load_json(paths["financial_analysis_product"])
    p3f9b_snapshot = _load_json(paths["exact_session_snapshot"])
    governed_chain = feedback_bridge.governed_session_chain(root)
    watchlist_tickers = list(owner_research_focus.broader_watchlist())
    feedback_status = feedback_bridge.build_prospective_feedback_status(
        current_records=integrated_current.get("records") or {}, p3f9b_snapshot=p3f9b_snapshot,
        governed_chain=governed_chain, evaluate_watchlist_only=watchlist_tickers,
    )
    return build_artifact(
        session=session, requested_at=f"{session}T15:05:00+07:00",
        integrated_decision_current=integrated_current, next_session_brief=next_session_brief,
        descriptive_current=descriptive_current, sector_leadership_current=sector_leadership_current,
        tactical_current=tactical_current, opportunity_prioritization_current=opportunity_prioritization_current,
        feedback_status=feedback_status, financial_analysis_product_current=financial_analysis_product_current,
    )
