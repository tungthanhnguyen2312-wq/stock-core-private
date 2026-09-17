"""Personal Investment Decision Action Center (PERSONAL_INVESTMENT_DECISION_ACTION_CENTER_V1).

Turns Stock Lookup's existing research engines into one deterministic owner-facing daily decision
surface. This module computes NO new decision: every field below is read straight from an
already-materialized, already-governed retained artifact for one completed session --
``integrated_investment_decision_product/v1`` (research_action_posture, trigger, invalidation,
counter-thesis, evidence axes), ``asymmetric_dislocation_research/v1`` (discovery lanes),
``market_wide_current_descriptive_research/v1`` and ``current_market_sector_leadership_context/v1``
(market regime), and -- only when a private local portfolio is present -- the just-released
``portfolio_aware_decision/v1`` current-position-truth chain (``CURRENT_CONFIRMED`` /
``CLOSED`` / ``CURRENT_POSITION_UNRESOLVED``, ``PERSONAL_DECISION_INPUT_TRUTH_V1``). It only
selects, remaps to a bounded action vocabulary, and re-presents.

Seven sections, in the order an owner reads them: MARKET, PORTFOLIO (confirmed holdings only --
``CURRENT_POSITION_UNRESOLVED`` and owner-excluded tickers are structurally excluded, never
just filtered by convention), UNRESOLVED_PORTFOLIO (review-only, no BUY/SELL derived from an
uncertain holding), WATCHLIST (the governed owner-focus config, not portfolio holdings), DISCOVERY
(the full research universe, portfolio-independent), CAPITAL_ROTATION (research comparison only,
never sourced from an unresolved position), and ATTENTION_QUEUE (categorical, never a score).

No universal stock score, no fabricated probability, no fabricated target price, no execution
order -- this module inherits every one of those boundaries unchanged from its sources; it has no
authority to create any of them itself.

Private-portfolio-optional by design (``AI_RULES.md``: a system authority gap must not
automatically produce WAIT): MARKET / WATCHLIST / DISCOVERY / a general ATTENTION_QUEUE are always
produced from public retained artifacts alone. PORTFOLIO / UNRESOLVED_PORTFOLIO / CAPITAL_ROTATION
require a private local portfolio and degrade to an explicit ``PRIVATE_PORTFOLIO_NOT_SUPPLIED``
status when one is not present -- never a silent empty result indistinguishable from "no holdings".

Local-only output, always: ``%USERPROFILE%\\.stocklookup\\action_center\\<session>\\``. Never
written to Git, ``operations-review/``, the Dashboard, or the public
``current_research_ai_handoff_packet``/``stocklookup-ai-handoffs`` path -- even the
private-portfolio-free baseline, because the whole point of this product is the owner's own local
daily read, not a second public artifact. No second AI reasoning engine: the JSON artifact is
already structured enough for an external AI research consumer to explain without recomputing
anything; nothing here calls one.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import asymmetric_dislocation_research as _asymmetric
import owner_research_exclusions as _owner_research_exclusions
import owner_research_focus as _owner_focus
import portfolio_aware_decision as _pad
import private_portfolio_context as _private_portfolio_context

CONTRACT_VERSION = "personal_investment_decision_action_center/v1"
MILESTONE = "PERSONAL_INVESTMENT_DECISION_ACTION_CENTER_V1"

# ── Bounded action vocabularies (pure remaps of already-computed posture/portfolio_action_research
# -- no new threshold or scoring logic anywhere in this module). ──────────────────────────────────
HOLDING_ACTIONS = frozenset({
    "ADD_CANDIDATE", "HOLD", "HOLD_NO_ADD", "REDUCE_REVIEW", "EXIT_REVIEW", "WAIT_FOR_CONFIRMATION",
})
WATCHLIST_ACTIONS = frozenset({"BUY_PROBE_CANDIDATE", "WAIT_FOR_CONFIRMATION", "WATCH", "AVOID_NEW_ENTRY"})
DISCOVERY_LANES = ("TACTICAL_SETUP", "EARLY_REVERSAL", "VALUATION_DISLOCATION", "ASYMMETRIC_RECOVERY_CASE")
ATTENTION_BUCKETS = ("ACTION_REVIEW_NOW", "PORTFOLIO_DATA_REVIEW", "THESIS_REVIEW", "CONFIRMATION_WATCH", "NO_ACTION_REQUIRED")
_ATTENTION_PRIORITY = {name: index for index, name in enumerate(ATTENTION_BUCKETS)}

# Asymmetric-dislocation states this module treats as a genuine opportunity candidate vs a risk
# flag -- reusing exactly the same split ``portfolio_aware_opportunity_shortlist.py`` already
# established (``_RECOVERY``/``_RISK``), not a new classification.
_ASYMMETRIC_OPPORTUNITY_LANE = {
    "QUALITY_DISLOCATION": "VALUATION_DISLOCATION",
    "TURNAROUND_EVIDENCE_FORMING": "ASYMMETRIC_RECOVERY_CASE",
    "CYCLICAL_RECOVERY_FORMING": "ASYMMETRIC_RECOVERY_CASE",
}
_TACTICAL_SETUP_POSTURES = frozenset({"INITIATE_ON_BREAKOUT", "ACCUMULATE_ON_RETEST"})
_EARLY_REVERSAL_POSTURES = frozenset({"EARLY_WATCH"})

_ROTATION_DESTINATION_LIMIT = 5


class ActionCenterError(ValueError):
    pass


def default_action_center_root() -> Path:
    """The sole default local storage root; deliberately outside Git, a sibling of the private
    portfolio root but independent of it -- this product does not require a private portfolio."""
    user_profile = os.environ.get("USERPROFILE")
    return Path(user_profile) / ".stocklookup" / "action_center" if user_profile else Path.home() / ".stocklookup" / "action_center"


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(body: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in body.items() if key not in {"artifact_identity", "artifact_sha256", "requested_at"}}
    digest = hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


# ── Per-ticker evidence condensation (read-only projection of integrated_investment_decision_product) ──

def _condensed_trigger(trigger: Mapping[str, Any] | None, *, price_fresh: bool) -> dict[str, Any]:
    trigger = trigger or {}
    # PERSONAL_INVESTMENT_DECISION_ACTION_CENTER_V1 fail-closed rule: a numeric, price-sensitive
    # trigger distance is never shown next to a stale price mark -- the qualitative trigger_state/
    # warning still passes through unchanged (this is a narrowing, never a widening, of what the
    # producer already asserted).
    return {
        "trigger_type": trigger.get("trigger_type"),
        "trigger_level": trigger.get("trigger_level") if price_fresh else None,
        "distance_to_trigger_pct": trigger.get("distance_to_trigger_pct") if price_fresh else None,
        "trigger_state": trigger.get("trigger_state"),
        "warning": trigger.get("warning"),
        "numeric_fields_withheld_stale_price": not price_fresh,
    }


def _condensed_invalidation(invalidation: Mapping[str, Any] | None, *, price_fresh: bool) -> dict[str, Any]:
    invalidation = invalidation or {}
    return {
        "invalidation_level": invalidation.get("invalidation_level") if price_fresh else None,
        "distance_to_invalidation_pct": invalidation.get("distance_to_invalidation_pct") if price_fresh else None,
        "invalidation_method": invalidation.get("invalidation_method"),
        "warning": invalidation.get("warning"),
        "numeric_fields_withheld_stale_price": not price_fresh,
    }


def _condensed_axis(evidence_axes: Mapping[str, Any] | None, axis: str) -> dict[str, Any]:
    axis_record = (evidence_axes or {}).get(axis)
    if not isinstance(axis_record, Mapping):
        return {"fitness": "NOT_PROVIDED"}
    return {
        "fitness": axis_record.get("fitness"),
        "is_actionable": axis_record.get("is_actionable"),
        "contradicting_reason_codes": list(axis_record.get("contradicting_reason_codes") or []),
        "blocker_reason_codes": list(axis_record.get("blocker_reason_codes") or []),
    }


def _freshness(ticker: str, *, session: str, coverage_records: Mapping[str, Any] | None) -> dict[str, Any]:
    """The exact-session price/technical distinction this milestone's predecessor
    (PERSONAL_DECISION_INPUT_TRUTH_V1) fixed in the AI-handoff card: ``research_session`` is
    always this artifact's own session; ``technical_coverage_disposition`` is this ticker's own,
    already-computed same-session-or-not verdict (``same_session_technical_coverage_disposition``)
    when that artifact was supplied -- never re-derived here. ``price_freshness`` is a direct,
    un-widened remap of that disposition, never a new staleness judgment."""
    row = (coverage_records or {}).get(ticker)
    if not isinstance(row, Mapping):
        return {"research_session": session, "technical_coverage_disposition": "NOT_EVALUATED", "price_freshness": "NOT_EVALUATED"}
    disposition = row.get("disposition")
    fresh = disposition == "SAME_SESSION_TECHNICAL_COVERED"
    return {
        "research_session": session,
        "technical_coverage_disposition": disposition,
        "price_freshness": "CURRENT" if fresh else "STALE_OR_UNAVAILABLE",
    }


def _evidence_block(ticker: str, record: Mapping[str, Any], *, session: str, coverage_records: Mapping[str, Any] | None) -> dict[str, Any]:
    freshness = _freshness(ticker, session=session, coverage_records=coverage_records)
    price_fresh = freshness["price_freshness"] == "CURRENT"
    evidence_axes = record.get("evidence_axes") or {}
    corporate_intelligence = record.get("corporate_intelligence_context") or {}
    return {
        "why_now": record.get("why_now"),
        "research_action_posture": record.get("research_action_posture"),
        "tactical_phase": record.get("tactical_phase"),
        "market_structure_state": record.get("market_structure_state"),
        "fundamental_state": record.get("fundamental_state"),
        "valuation_context_summary": record.get("valuation_context_summary"),
        "market_sector_context": record.get("market_sector_context"),
        "catalyst_state": {
            "fitness": corporate_intelligence.get("fitness"),
            "active_catalyst_count": corporate_intelligence.get("active_catalyst_count"),
            "active_risk_count": corporate_intelligence.get("active_risk_count"),
            "evidence_session": corporate_intelligence.get("evidence_session"),
            "evidence_session_stale": corporate_intelligence.get("evidence_session_stale"),
        },
        "trigger": _condensed_trigger(record.get("trigger"), price_fresh=price_fresh),
        "invalidation": _condensed_invalidation(record.get("invalidation"), price_fresh=price_fresh),
        "counter_thesis": list(record.get("counter_thesis") or []),
        "material_uncertainties": list(record.get("material_uncertainties") or []),
        "evidence_axes_summary": {
            "TACTICAL_STRUCTURE": _condensed_axis(evidence_axes, "TACTICAL_STRUCTURE"),
            "FUNDAMENTAL": _condensed_axis(evidence_axes, "FUNDAMENTAL"),
            "VALUATION": _condensed_axis(evidence_axes, "VALUATION"),
            "CORPORATE_INTELLIGENCE": _condensed_axis(evidence_axes, "CORPORATE_INTELLIGENCE"),
            "MARKET_SECTOR": _condensed_axis(evidence_axes, "MARKET_SECTOR"),
        },
        "freshness": freshness,
        "source_identities": {"decision_identity": record.get("decision_identity")},
    }


# ── Action remaps (deterministic lookup tables over already-computed posture/portfolio fields) ────

def _holding_action(*, portfolio_action_research: str, posture: str) -> str:
    # `position_state` (HELD vs HELD_ABOVE_POLICY_CAP) is deliberately not consulted directly:
    # the over-limit case is already carried in `portfolio_action_research == "OVER_LIMIT_REVIEW"`,
    # and an AVOID/REDUCE posture overrides regardless of whether the position happens to be
    # over-weighted -- an existing thesis breaking is the same signal either way.
    if posture == "AVOID":
        return "EXIT_REVIEW"
    if posture == "REDUCE":
        return "REDUCE_REVIEW"
    if portfolio_action_research == "OVER_LIMIT_REVIEW":
        return "HOLD_NO_ADD"
    if portfolio_action_research in (
        "ADD_WITHIN_RISK_CEILING", "ADD_WITHIN_EVALUATED_CONSTRAINTS", "ADD_ELIGIBLE_SIZING_UNAVAILABLE",
        "PROBE_WITHIN_RISK_CEILING", "PROBE_WITHIN_EVALUATED_CONSTRAINTS", "PROBE_ELIGIBLE_SIZING_UNAVAILABLE",
    ):
        return "ADD_CANDIDATE"
    if posture in ("WAIT_FOR_CONFIRMATION", "EARLY_WATCH"):
        return "WAIT_FOR_CONFIRMATION"
    return "HOLD"


def _watchlist_action(posture: str) -> str:
    if posture in ("INITIATE_ON_BREAKOUT", "ACCUMULATE_ON_RETEST"):
        return "BUY_PROBE_CANDIDATE"
    if posture in ("WAIT_FOR_CONFIRMATION", "EARLY_WATCH"):
        return "WAIT_FOR_CONFIRMATION"
    if posture in ("AVOID", "REDUCE"):
        return "AVOID_NEW_ENTRY"
    return "WATCH"


# ── Section builders ────────────────────────────────────────────────────────────────────────────

def _build_market_section(
    *, session: str, descriptive: Mapping[str, Any] | None, sector_leadership: Mapping[str, Any] | None,
    previous_descriptive: Mapping[str, Any] | None, previous_session: str | None,
) -> dict[str, Any]:
    if not isinstance(descriptive, Mapping):
        return {"status": "NOT_AVAILABLE", "reason": "NO_RETAINED_DESCRIPTIVE_RESEARCH_FOR_SESSION"}
    breadth = descriptive.get("market_breadth") or {}
    market_block = (sector_leadership or {}).get("market") or {}
    groups = ((sector_leadership or {}).get("groups") or {}).get("records") or {}
    leading = sorted(
        (row.get("group_identity") for row in groups.values() if isinstance(row, Mapping) and row.get("leadership_state") == "LEADING"),
    )
    lagging = sorted(
        (row.get("group_identity") for row in groups.values() if isinstance(row, Mapping) and row.get("leadership_state") in ("LAGGING", "WEAK", "DETERIORATING")),
    )
    previous_breadth = (previous_descriptive or {}).get("market_breadth") if isinstance(previous_descriptive, Mapping) else None
    previous_comparison: dict[str, Any]
    if isinstance(previous_breadth, Mapping):
        def _delta(key: str) -> float | int | None:
            a, b = breadth.get(key), previous_breadth.get(key)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
                return a - b
            return None
        previous_comparison = {
            "status": "AVAILABLE", "previous_session": previous_session,
            "advance_ratio_delta": _delta("advance_ratio"), "advancing_delta": _delta("advancing"), "declining_delta": _delta("declining"),
        }
    else:
        previous_comparison = {"status": "NOT_AVAILABLE", "previous_session": previous_session}
    return {
        "status": "AVAILABLE",
        "session": session,
        "market_regime": {
            "current_breadth_state": market_block.get("current_breadth_state") or (breadth.get("breadth_descriptor") or {}).get("descriptor"),
            "advance_ratio": breadth.get("advance_ratio"), "advancing": breadth.get("advancing"), "declining": breadth.get("declining"), "unchanged": breadth.get("unchanged"),
        },
        "momentum_participation": {
            "momentum_descriptor": (breadth.get("momentum_descriptor") or {}).get("descriptor"),
            "positive_momentum_ratio": market_block.get("positive_momentum_ratio"),
            "negative_momentum_ratio": market_block.get("negative_momentum_ratio"),
            "trend_participation": market_block.get("trend_participation"),
        },
        "sector_leadership": {
            "leading_groups": leading, "lagging_or_weak_groups": lagging,
            "available_group_count": ((sector_leadership or {}).get("groups") or {}).get("available_group_count"),
            "data_limited_group_count": ((sector_leadership or {}).get("groups") or {}).get("data_limited_group_count"),
        } if sector_leadership is not None else {"status": "NOT_AVAILABLE"},
        "warnings": list(market_block.get("warnings") or []),
        "previous_session_comparison": previous_comparison,
        "source_artifact_identities": {
            "market_wide_current_descriptive_research": descriptive.get("artifact_identity"),
            "current_market_sector_leadership_context": (sector_leadership or {}).get("artifact_identity"),
        },
    }


def _build_portfolio_sections(
    *, session: str, integrated_records: Mapping[str, Any], portfolio_artifact: Mapping[str, Any] | None,
    coverage_records: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (portfolio_section, unresolved_section). Structurally excludes CLOSED and
    EXCLUDED_INACTIVE tickers -- they are simply absent from `portfolio_artifact["records"]`'s
    HELD/HELD_ABOVE_POLICY_CAP/CURRENT_POSITION_UNRESOLVED subsets, never a filtered-out flag a
    caller could accidentally ignore."""
    if not isinstance(portfolio_artifact, Mapping):
        return (
            {"status": "PRIVATE_PORTFOLIO_NOT_SUPPLIED", "holdings": []},
            {"status": "PRIVATE_PORTFOLIO_NOT_SUPPLIED", "items": []},
        )
    records = portfolio_artifact.get("records") or {}
    holdings: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for ticker, row in sorted(records.items()):
        position_state = row.get("position_state")
        integrated_record = integrated_records.get(ticker) or {}
        if position_state in ("HELD", "HELD_ABOVE_POLICY_CAP"):
            posture = row.get("security_research_action_posture")
            action = _holding_action(portfolio_action_research=row.get("portfolio_action_research"), posture=posture)
            holdings.append({
                "ticker": ticker,
                "action": action,
                "position_state": position_state,
                "portfolio_action_research": row.get("portfolio_action_research"),
                "current_weight": row.get("current_weight"),
                "current_weight_status": row.get("current_weight_status"),
                "binding_constraint": row.get("binding_constraint"),
                "evidence": _evidence_block(ticker, integrated_record, session=session, coverage_records=coverage_records),
            })
        elif position_state == "CURRENT_POSITION_UNRESOLVED":
            unresolved.append({
                "ticker": ticker,
                "status": "CURRENT_POSITION_UNRESOLVED",
                "note": "Owner reconciliation of the private workbook is required before any portfolio action for this ticker; no BUY/SELL is derived from an uncertain holding.",
                "portfolio_action_research": row.get("portfolio_action_research"),
            })
    return (
        {"status": "AVAILABLE", "holdings": holdings},
        {"status": "AVAILABLE", "items": unresolved},
    )


def _build_watchlist_section(
    *, session: str, integrated_records: Mapping[str, Any], owner_focus: Mapping[str, Any] | None,
    excluded_tickers: frozenset[str], coverage_records: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if owner_focus is None:
        return {"status": "NOT_AVAILABLE", "reason": "OWNER_FOCUS_CONFIG_UNAVAILABLE", "entries": []}
    entries: list[dict[str, Any]] = []
    for ticker in sorted(owner_focus.get("broader_watchlist") or ()):
        if ticker in excluded_tickers:
            continue
        record = integrated_records.get(ticker)
        if not isinstance(record, Mapping):
            entries.append({"ticker": ticker, "action": "WATCH", "owner_focus": ticker in set(owner_focus.get("owner_focus_tickers") or ()), "status": "NOT_EVALUATED_THIS_SESSION"})
            continue
        posture = record.get("research_action_posture")
        entries.append({
            "ticker": ticker, "action": _watchlist_action(posture),
            "owner_focus": ticker in set(owner_focus.get("owner_focus_tickers") or ()),
            "status": "AVAILABLE",
            "evidence": _evidence_block(ticker, record, session=session, coverage_records=coverage_records),
        })
    return {"status": "AVAILABLE", "entries": entries}


def _build_discovery_section(
    *, session: str, integrated_records: Mapping[str, Any], asymmetric_records: Mapping[str, Any],
    excluded_tickers: frozenset[str], held_tickers: frozenset[str], coverage_records: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Full research universe, deliberately independent of any private portfolio input --
    ``integrated_records``/``asymmetric_records`` are both public, market-wide artifacts."""
    lanes: dict[str, list[dict[str, Any]]] = {lane: [] for lane in DISCOVERY_LANES}
    for ticker in sorted(integrated_records):
        if ticker in excluded_tickers or ticker in held_tickers:
            continue
        record = integrated_records[ticker]
        posture = record.get("research_action_posture")
        if posture in _TACTICAL_SETUP_POSTURES:
            tactical_lane = "TACTICAL_SETUP"
        elif posture in _EARLY_REVERSAL_POSTURES:
            tactical_lane = "EARLY_REVERSAL"
        else:
            tactical_lane = None
        asymmetric_state = (asymmetric_records.get(ticker) or {}).get("primary_research_state")
        asymmetric_lane = _ASYMMETRIC_OPPORTUNITY_LANE.get(asymmetric_state)
        if tactical_lane is None and asymmetric_lane is None:
            continue
        evidence = _evidence_block(ticker, record, session=session, coverage_records=coverage_records)
        if tactical_lane is not None:
            lanes[tactical_lane].append({"ticker": ticker, "lane": tactical_lane, "reason": f"POSTURE:{posture}", "evidence": evidence})
        if asymmetric_lane is not None:
            lanes[asymmetric_lane].append({"ticker": ticker, "lane": asymmetric_lane, "reason": f"ASYMMETRIC_STATE:{asymmetric_state}", "evidence": evidence})
    return {
        "status": "AVAILABLE",
        "lanes": lanes,
        "lane_counts": {lane: len(rows) for lane, rows in lanes.items()},
        "requires_private_portfolio": False,
    }


def _build_investment_accounts_section(portfolio_snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    """PRIVATE_MULTI_BROKER_INVESTMENT_ACCOUNT_CONTEXT_V1, Section 8: an aggregate-only owner
    summary (never a per-account breakdown, never a raw account alias/number -- see
    ``private_portfolio_research_handoff.py`` for the anonymized per-account form meant for
    external upload). Purely informational: nothing here is read by ``_holding_action``,
    ``_watchlist_action``, or ``_build_attention_queue`` -- cash existing is capital context, not
    a BUY signal."""
    if not isinstance(portfolio_snapshot, Mapping):
        return {"status": "PRIVATE_PORTFOLIO_NOT_SUPPLIED"}
    aggregate = portfolio_snapshot.get("investment_accounts_portfolio_context") or {}
    if aggregate.get("status") in (None, "NOT_PROVIDED"):
        return {"status": "NOT_PROVIDED", "broker_account_count": 0}
    totals = aggregate.get("totals") or {}
    return {
        "status": aggregate.get("status"),
        "broker_account_count": aggregate.get("account_count", 0),
        "broker_cash": totals.get("total_broker_cash"),
        "reserved_cash": totals.get("total_reserved_cash"),
        "receivables": totals.get("total_receivables"),
        "margin_debt": totals.get("total_margin_debt"),
        "broker_reported_nav": totals.get("total_broker_reported_nav"),
        "broker_reported_securities_market_value": totals.get("total_broker_reported_securities_market_value"),
        "as_of_consistency": aggregate.get("as_of_consistency"),
        "source_artifact_identity": aggregate.get("artifact_identity"),
    }


def _build_rotation_section(
    *, holdings: Sequence[Mapping[str, Any]], discovery_lanes: Mapping[str, list[dict[str, Any]]],
    sector_by_ticker: Mapping[str, str],
) -> dict[str, Any]:
    """A rotation pair only ever cites already-computed posture/evidence -- never cost basis
    (never read anywhere in this function) -- and only ever pairs a CURRENT_CONFIRMED source
    (``holdings`` is already exactly that subset) with a same-sector DISCOVERY candidate, so the
    comparison is at least sector-comparable rather than an arbitrary cross-sector implication.
    A source with no same-sector destination candidate emits no pair at all -- fail closed, never
    a forced or cross-sector comparison."""
    destination_candidates: dict[str, list[dict[str, Any]]] = {}
    for lane in ("TACTICAL_SETUP", "VALUATION_DISLOCATION"):
        for row in discovery_lanes.get(lane) or []:
            destination_candidates.setdefault(row["ticker"], []).append(row)

    pairs: list[dict[str, Any]] = []
    for holding in holdings:
        if holding["action"] not in ("EXIT_REVIEW", "REDUCE_REVIEW"):
            continue
        source_ticker = holding["ticker"]
        source_sector = sector_by_ticker.get(source_ticker)
        if not source_sector:
            continue
        destinations = sorted(
            ticker for ticker in destination_candidates
            if ticker != source_ticker and sector_by_ticker.get(ticker) == source_sector
        )[:_ROTATION_DESTINATION_LIMIT]
        if not destinations:
            continue
        pairs.append({
            "source_ticker": source_ticker,
            "source_action": holding["action"],
            "source_sector": source_sector,
            "consider_reduce": source_ticker,
            "consider_candidates": [
                {"ticker": ticker, "lanes": [row["lane"] for row in destination_candidates[ticker]], "reason": destination_candidates[ticker][0]["reason"]}
                for ticker in destinations
            ],
            "reason": f"Existing holding {source_ticker}'s own research posture is {holding['portfolio_action_research']!r} "
                      f"(security posture led to {holding['action']}) while same-sector ({source_sector}) candidates above show materially stronger evidence.",
            "blockers": [
                "NOT_AN_EXECUTION_ORDER", "COST_BASIS_NOT_USED_IN_THIS_ARGUMENT",
                "DESTINATION_SIZING_STILL_SUBJECT_TO_ITS_OWN_PORTFOLIO_CONSTRAINTS",
            ],
        })
    return {"status": "AVAILABLE", "pairs": pairs, "requires_private_portfolio": True, "destination_limit_per_source": _ROTATION_DESTINATION_LIMIT}


def _build_attention_queue(*, holdings: Sequence[Mapping[str, Any]], unresolved: Sequence[Mapping[str, Any]], watchlist_entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in unresolved:
        rows.append({"ticker": item["ticker"], "bucket": "PORTFOLIO_DATA_REVIEW", "source_section": "UNRESOLVED_PORTFOLIO", "reason": "CURRENT_POSITION_UNRESOLVED"})
    for holding in holdings:
        action = holding["action"]
        if action in ("EXIT_REVIEW", "REDUCE_REVIEW", "ADD_CANDIDATE"):
            bucket = "ACTION_REVIEW_NOW"
        elif action == "HOLD_NO_ADD":
            bucket = "THESIS_REVIEW"
        elif action == "WAIT_FOR_CONFIRMATION":
            bucket = "CONFIRMATION_WATCH"
        else:
            bucket = "NO_ACTION_REQUIRED"
        rows.append({"ticker": holding["ticker"], "bucket": bucket, "source_section": "PORTFOLIO", "reason": action})
    for entry in watchlist_entries:
        action = entry.get("action")
        if action == "BUY_PROBE_CANDIDATE":
            bucket = "ACTION_REVIEW_NOW"
        elif action == "WAIT_FOR_CONFIRMATION":
            bucket = "CONFIRMATION_WATCH"
        else:
            bucket = "NO_ACTION_REQUIRED"
        rows.append({"ticker": entry["ticker"], "bucket": bucket, "source_section": "WATCHLIST", "reason": action})
    rows.sort(key=lambda row: (_ATTENTION_PRIORITY.get(row["bucket"], len(ATTENTION_BUCKETS)), row["ticker"]))
    counts = {bucket: sum(1 for row in rows if row["bucket"] == bucket) for bucket in ATTENTION_BUCKETS}
    return {"status": "AVAILABLE", "rows": rows, "bucket_counts": counts}


# ── Top-level artifact ─────────────────────────────────────────────────────────────────────────

def build_artifact(
    *, session: str, requested_at: str, integrated_decision_artifact: Mapping[str, Any],
    descriptive_artifact: Mapping[str, Any] | None = None, sector_leadership_artifact: Mapping[str, Any] | None = None,
    previous_descriptive_artifact: Mapping[str, Any] | None = None, previous_session: str | None = None,
    asymmetric_dislocation_artifact: Mapping[str, Any] | None = None, coverage_disposition_artifact: Mapping[str, Any] | None = None,
    owner_focus: Mapping[str, Any] | None = None, portfolio_aware_decision_artifact: Mapping[str, Any] | None = None,
    sector_by_ticker: Mapping[str, str] | None = None, excluded_tickers: frozenset[str] = frozenset(),
    portfolio_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure composition over already-built artifacts for one session -- no file I/O, no
    recomputation. See ``evaluate_from_retained_artifacts`` for the real-session, file-resolving
    entry point."""
    if integrated_decision_artifact.get("session") not in (None, session):
        raise ActionCenterError("INTEGRATED_DECISION_SESSION_MISMATCH")
    integrated_records = integrated_decision_artifact.get("records") or {}
    coverage_records = (coverage_disposition_artifact or {}).get("records") if coverage_disposition_artifact else None
    asymmetric_records = (asymmetric_dislocation_artifact or {}).get("records") or {}

    market = _build_market_section(
        session=session, descriptive=descriptive_artifact, sector_leadership=sector_leadership_artifact,
        previous_descriptive=previous_descriptive_artifact, previous_session=previous_session,
    )
    portfolio_section, unresolved_section = _build_portfolio_sections(
        session=session, integrated_records=integrated_records, portfolio_artifact=portfolio_aware_decision_artifact,
        coverage_records=coverage_records,
    )
    held_tickers = frozenset(row["ticker"] for row in portfolio_section.get("holdings") or [])
    watchlist = _build_watchlist_section(
        session=session, integrated_records=integrated_records, owner_focus=owner_focus,
        excluded_tickers=excluded_tickers, coverage_records=coverage_records,
    )
    discovery = _build_discovery_section(
        session=session, integrated_records=integrated_records, asymmetric_records=asymmetric_records,
        excluded_tickers=excluded_tickers, held_tickers=held_tickers, coverage_records=coverage_records,
    )
    if portfolio_aware_decision_artifact is not None:
        rotation = _build_rotation_section(
            holdings=portfolio_section.get("holdings") or [], discovery_lanes=discovery["lanes"],
            sector_by_ticker=sector_by_ticker or {},
        )
    else:
        rotation = {"status": "PRIVATE_PORTFOLIO_NOT_SUPPLIED", "pairs": [], "requires_private_portfolio": True}
    attention = _build_attention_queue(
        holdings=portfolio_section.get("holdings") or [], unresolved=unresolved_section.get("items") or [],
        watchlist_entries=watchlist.get("entries") or [],
    )
    investment_accounts = _build_investment_accounts_section(portfolio_snapshot)

    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "session": session,
        "requested_at": requested_at,
        "market": market,
        "portfolio": portfolio_section,
        "unresolved_portfolio": unresolved_section,
        "watchlist": watchlist,
        "discovery": discovery,
        "capital_rotation": rotation,
        "investment_accounts": investment_accounts,
        "attention_queue": attention,
        "coverage": {
            "security_denominator": len(integrated_records),
            "portfolio_supplied": portfolio_aware_decision_artifact is not None,
            "confirmed_holding_count": len(portfolio_section.get("holdings") or []),
            "unresolved_portfolio_count": len(unresolved_section.get("items") or []),
            "watchlist_count": len(watchlist.get("entries") or []),
            "rotation_pair_count": len(rotation.get("pairs") or []),
        },
        "source_artifact_identities": {
            "integrated_investment_decision_product": integrated_decision_artifact.get("artifact_identity"),
            "asymmetric_dislocation_research": (asymmetric_dislocation_artifact or {}).get("artifact_identity"),
            "portfolio_aware_decision": (portfolio_aware_decision_artifact or {}).get("artifact_identity"),
        },
        "authority_boundary": {
            "no_universal_score": True,
            "no_fabricated_probability_or_target_price": True,
            "no_execution_order": True,
            "capital_rotation_is_research_recommendation_not_execution": True,
            "unresolved_position_never_yields_buy_sell_or_rotation_source": True,
            "closed_and_excluded_positions_never_enter_active_portfolio_decisions": True,
            "pit_authority_gap_does_not_block_current_technical_or_fundamental_research": True,
            "private_local_only_never_git_dashboard_or_public_ai_handoff": True,
            "cash_availability_is_capital_context_not_a_buy_signal": True,
            "investment_account_values_never_alter_security_or_portfolio_action_computation": True,
        },
    }
    return {**body, **_identity(body)}


# ── Retained-artifact resolution (read-only; no Daily run, no provider call) ──────────────────────

def _nodash(session: str) -> str:
    return session.replace("-", "")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _descriptive_artifact_path(repo_root: Path, session: str) -> Path:
    return repo_root / "operations-review" / f"market-wide-current-descriptive-research-v1-{_nodash(session)}" / "market_wide_current_descriptive_research_artifact.json"


def _sector_leadership_artifact_path(repo_root: Path, session: str) -> Path:
    return repo_root / "operations-review" / f"current-market-sector-leadership-context-v1-{_nodash(session)}" / "current_market_sector_leadership_context_artifact.json"


def _coverage_disposition_artifact_path(repo_root: Path, session: str) -> Path:
    return repo_root / "operations-review" / f"same-session-technical-coverage-recovery-v1-{_nodash(session)}" / "same_session_technical_coverage_disposition_artifact.json"


def _previous_session(repo_root: Path, session: str) -> str | None:
    """Lexicographically latest retained descriptive-research session strictly before ``session``
    -- the same sorted-glob idiom already established elsewhere in this codebase (e.g.
    ``portfolio_aware_decision.default_latest_completed_session``), never an mtime scan."""
    root = repo_root / "operations-review"
    if not root.is_dir():
        return None
    prefix = "market-wide-current-descriptive-research-v1-"
    candidates = sorted(
        entry.name[len(prefix):] for entry in root.iterdir()
        if entry.is_dir() and entry.name.startswith(prefix) and entry.name[len(prefix):] < _nodash(session)
    )
    if not candidates:
        return None
    nodash = candidates[-1]
    return f"{nodash[0:4]}-{nodash[4:6]}-{nodash[6:8]}"


def evaluate_from_retained_artifacts(
    *, repo_root: Path, session: str | None = None, portfolio_root: Path | None = None, requested_at: str,
) -> dict[str, Any]:
    """One deterministic, read-only evaluation over already-retained same-session artifacts.

    Never runs Daily, never calls a provider. Raises ``FileNotFoundError`` if no completed session
    (explicit or latest) has a retained Integrated Decision artifact. A private portfolio is
    entirely optional: when ``private_portfolio_context.portfolio_status`` is not ``READY``, the
    portfolio/unresolved/rotation sections degrade to an explicit ``PRIVATE_PORTFOLIO_NOT_SUPPLIED``
    and everything else (market/watchlist/discovery/a general attention queue) is produced exactly
    the same as when a private portfolio is present.
    """
    resolved_session = session or _pad.default_latest_completed_session(repo_root)
    if not resolved_session:
        raise FileNotFoundError("NO_RETAINED_COMPLETED_INTEGRATED_DECISION_SESSION_AVAILABLE")
    integrated_decision_artifact = _pad.load_integrated_decision_artifact(repo_root, resolved_session)
    descriptive_artifact = _load_json(_descriptive_artifact_path(repo_root, resolved_session))
    sector_leadership_artifact = _load_json(_sector_leadership_artifact_path(repo_root, resolved_session))
    coverage_disposition_artifact = _load_json(_coverage_disposition_artifact_path(repo_root, resolved_session))
    previous_session = _previous_session(repo_root, resolved_session)
    previous_descriptive_artifact = _load_json(_descriptive_artifact_path(repo_root, previous_session)) if previous_session else None
    asymmetric_dislocation_artifact = _asymmetric.build_artifact(session=resolved_session, integrated_product=integrated_decision_artifact)

    try:
        owner_focus = _owner_focus.load_owner_research_focus()
    except _owner_focus.OwnerResearchFocusError:
        owner_focus = None

    governed_sector_snapshot = _pad.load_governed_sector_snapshot(repo_root)
    sector_by_ticker, _sector_sources, _snapshot_identity = _pad.resolve_sector_by_ticker(governed_sector_snapshot=governed_sector_snapshot)

    status = _private_portfolio_context.portfolio_status(portfolio_root=portfolio_root)
    portfolio_aware_decision_artifact = None
    portfolio_snapshot = None
    excluded_tickers: frozenset[str] = frozenset()
    if status.get("status") == "READY":
        portfolio_aware_decision_artifact = _pad.evaluate_from_retained_artifacts(
            repo_root=repo_root, session=resolved_session, portfolio_root=portfolio_root, requested_at=requested_at,
        )
        portfolio_snapshot = status.get("snapshot")
        excluded_tickers = _owner_research_exclusions.excluded_ticker_set(_owner_research_exclusions.load_research_exclusions(portfolio_root))

    return build_artifact(
        session=resolved_session, requested_at=requested_at, integrated_decision_artifact=integrated_decision_artifact,
        descriptive_artifact=descriptive_artifact, sector_leadership_artifact=sector_leadership_artifact,
        previous_descriptive_artifact=previous_descriptive_artifact, previous_session=previous_session,
        asymmetric_dislocation_artifact=asymmetric_dislocation_artifact, coverage_disposition_artifact=coverage_disposition_artifact,
        owner_focus=owner_focus, portfolio_aware_decision_artifact=portfolio_aware_decision_artifact,
        sector_by_ticker=sector_by_ticker, excluded_tickers=excluded_tickers, portfolio_snapshot=portfolio_snapshot,
    )


def write_private_artifact(artifact: Mapping[str, Any], *, root: Path | None = None) -> Path:
    destination = (root or default_action_center_root()) / str(artifact["session"]) / "personal_investment_decision_action_center_v1.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = _canon(artifact) + "\n"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def public_console_summary(artifact: Mapping[str, Any], *, destination: Path | None = None, markdown_destination: Path | None = None) -> dict[str, Any]:
    """Safe CLI surface: identities/counts/status only, never a ticker or evidence value."""
    coverage = artifact.get("coverage") or {}
    return {
        "status": "ACTION_CENTER_READY",
        "milestone": MILESTONE,
        "session": artifact.get("session"),
        "personal_investment_decision_action_center_identity": artifact.get("artifact_identity"),
        "market_status": (artifact.get("market") or {}).get("status"),
        "portfolio_status": (artifact.get("portfolio") or {}).get("status"),
        "investment_accounts_status": (artifact.get("investment_accounts") or {}).get("status"),
        "watchlist_status": (artifact.get("watchlist") or {}).get("status"),
        "discovery_lane_counts": (artifact.get("discovery") or {}).get("lane_counts"),
        "attention_bucket_counts": (artifact.get("attention_queue") or {}).get("bucket_counts"),
        "coverage": coverage,
        "written_to": str(destination) if destination is not None else None,
        "markdown_written_to": str(markdown_destination) if markdown_destination is not None else None,
    }


# ── Owner-readable local Markdown view ─────────────────────────────────────────────────────────

def _md_evidence_line(evidence: Mapping[str, Any]) -> str:
    freshness = evidence.get("freshness") or {}
    return f"  - why: {evidence.get('why_now') or 'n/a'} _(price: {freshness.get('price_freshness', 'NOT_EVALUATED')})_"


def markdown(artifact: Mapping[str, Any]) -> str:
    """Compact owner-readable render. Provenance/authority detail stays in short flags, not prose."""
    lines: list[str] = []
    session = artifact.get("session")
    lines.append(f"# Personal Investment Decision Action Center — {session}")
    lines.append("")
    lines.append(f"_Not a recommendation engine: every action below is a bounded remap of already-governed research, never a new computation._")
    lines.append("")

    lines.append("## TODAY")
    market = artifact.get("market") or {}
    if market.get("status") == "AVAILABLE":
        regime = market.get("market_regime") or {}
        lines.append(f"- Market regime: **{regime.get('current_breadth_state')}** (advance ratio {regime.get('advance_ratio')})")
        leadership = market.get("sector_leadership") or {}
        if leadership.get("leading_groups"):
            lines.append(f"- Leading sectors: {', '.join(leadership['leading_groups'])}")
        if leadership.get("lagging_or_weak_groups"):
            lines.append(f"- Lagging/weak sectors: {', '.join(leadership['lagging_or_weak_groups'])}")
        previous = market.get("previous_session_comparison") or {}
        if previous.get("status") == "AVAILABLE":
            lines.append(f"- Vs {previous.get('previous_session')}: advance-ratio delta {previous.get('advance_ratio_delta')}")
    else:
        lines.append(f"- Market: {market.get('status')} ({market.get('reason')})")
    lines.append("")

    lines.append("## PORTFOLIO ACTIONS")
    portfolio = artifact.get("portfolio") or {}
    if portfolio.get("status") == "PRIVATE_PORTFOLIO_NOT_SUPPLIED":
        lines.append("- PRIVATE_PORTFOLIO_NOT_SUPPLIED — import a workbook (`portfolio import`) to enable this section.")
    elif not portfolio.get("holdings"):
        lines.append("- No confirmed current holdings.")
    else:
        for row in portfolio["holdings"]:
            lines.append(f"- **{row['ticker']}** — {row['action']} _(posture-derived; binding constraint: {row.get('binding_constraint')})_")
            lines.append(_md_evidence_line(row["evidence"]))
    lines.append("")

    lines.append("## UNRESOLVED PORTFOLIO ITEMS")
    unresolved = artifact.get("unresolved_portfolio") or {}
    if unresolved.get("status") == "PRIVATE_PORTFOLIO_NOT_SUPPLIED":
        lines.append("- PRIVATE_PORTFOLIO_NOT_SUPPLIED")
    elif not unresolved.get("items"):
        lines.append("- None — reconciliation is clean.")
    else:
        for item in unresolved["items"]:
            lines.append(f"- **{item['ticker']}** — {item['note']}")
    lines.append("")

    lines.append("## INVESTMENT ACCOUNTS")
    accounts = artifact.get("investment_accounts") or {}
    if accounts.get("status") in ("PRIVATE_PORTFOLIO_NOT_SUPPLIED", "NOT_PROVIDED", None):
        lines.append(f"- {accounts.get('status', 'NOT_PROVIDED')} — capital context only, never a BUY/SELL signal by itself.")
    else:
        lines.append(f"- Broker accounts: {accounts.get('broker_account_count')} _(aggregate status: {accounts.get('status')})_")
        lines.append(f"- Broker cash: {accounts.get('broker_cash')}")
        lines.append(f"- Reserved cash: {accounts.get('reserved_cash')}")
        lines.append(f"- Receivables: {accounts.get('receivables')}")
        lines.append(f"- Margin debt: {accounts.get('margin_debt')}")
        lines.append(f"- Broker-reported securities market value: {accounts.get('broker_reported_securities_market_value')}")
        lines.append(f"- Broker-reported NAV: {accounts.get('broker_reported_nav')}")
        lines.append(f"- Account freshness: {accounts.get('as_of_consistency')}")
        lines.append("- Cash availability is capital context only, never a BUY/SELL signal by itself.")
    lines.append("")

    lines.append("## WATCHLIST")
    watchlist = artifact.get("watchlist") or {}
    for entry in watchlist.get("entries") or []:
        tag = "★" if entry.get("owner_focus") else "-"
        lines.append(f"{tag} **{entry['ticker']}** — {entry.get('action')}")
    lines.append("")

    lines.append("## NEW OPPORTUNITIES")
    discovery = artifact.get("discovery") or {}
    for lane, rows in (discovery.get("lanes") or {}).items():
        if not rows:
            continue
        tickers = ", ".join(sorted({row["ticker"] for row in rows}))
        lines.append(f"- **{lane}** ({len(rows)}): {tickers}")
    lines.append("")

    lines.append("## CAPITAL ROTATION")
    rotation = artifact.get("capital_rotation") or {}
    if rotation.get("status") == "PRIVATE_PORTFOLIO_NOT_SUPPLIED":
        lines.append("- PRIVATE_PORTFOLIO_NOT_SUPPLIED")
    elif not rotation.get("pairs"):
        lines.append("- No qualifying rotation candidates today (a deteriorating holding needs a same-sector candidate with meaningfully stronger evidence).")
    else:
        for pair in rotation["pairs"]:
            destinations = ", ".join(c["ticker"] for c in pair["consider_candidates"])
            lines.append(f"- CONSIDER_REDUCE {pair['source_ticker']} → CONSIDER {destinations} _(sector: {pair['source_sector']})_")
            lines.append(f"  - {pair['reason']}")
    lines.append("")

    lines.append("## WHAT NEEDS CONFIRMATION")
    attention = artifact.get("attention_queue") or {}
    for bucket in ATTENTION_BUCKETS:
        rows = [row for row in attention.get("rows") or [] if row["bucket"] == bucket]
        if not rows:
            continue
        lines.append(f"- **{bucket}**: {', '.join(row['ticker'] for row in rows)}")
    lines.append("")

    lines.append("## DATA / AUTHORITY WARNINGS")
    lines.append(f"- Security denominator: {(artifact.get('coverage') or {}).get('security_denominator')}")
    lines.append(f"- Portfolio supplied: {(artifact.get('coverage') or {}).get('portfolio_supplied')}")
    lines.append("- No universal score, no fabricated probability/target price, no execution order anywhere in this file.")
    lines.append("")
    return "\n".join(lines)


def write_markdown(artifact: Mapping[str, Any], *, root: Path | None = None) -> Path:
    destination = (root or default_action_center_root()) / str(artifact["session"]) / "personal_investment_decision_action_center.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(markdown(artifact), encoding="utf-8")
    return destination
