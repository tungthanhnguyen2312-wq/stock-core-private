"""tools/build_daily_analyst_brief.py — Daily Analyst Brief V1.

Consumes the existing research_intelligence_digest_v1 artifact only. This module is a
presentation / prioritization-of-attention layer over already-computed evidence: it does not
recompute market state, cohort membership, cross-dimension reason codes, or coverage
accounting. It selects a small bounded set of cases for human review using an explicit,
non-investment attention-priority contract (research_attention_priority), and renders a
concise analyst-facing Markdown brief.

It must never become a recommendation engine: no ranking of expected return, no BUY/SELL/HOLD,
no investment score, no target price, no probability, no causal-actor inference, no authority
promotion.

Authority Boundary:
- authority_effect: "NONE"
- ranking_authority: False
- recommendation_authority: False
- sizing_authority: False
- valuation_authority: False
- pit_backtest_eligible: False
- raw_as_traded_promoted: False
- database_mutated: False
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_file, atomic_write_json
from tools.derive_cross_dimension_research_digest import (
    CODE_HIGH_FOREIGN_ROOM,
    CODE_MATERIAL_ACTIVE_BUY_IMBALANCE,
    CODE_MATERIAL_ACTIVE_SELL_IMBALANCE,
    CODE_MATERIAL_PROP_NET_BUY,
    CODE_MATERIAL_PROP_NET_SELL,
    CODE_MOMENTUM_WITH_PROP_BUY,
    CODE_MOMENTUM_WITH_PROP_SELL,
    CODE_PUT_THROUGH_DOMINANT,
    CODE_REVERSAL_WITH_ACTIVE_SELLING,
    CODE_SIGNIFICANT_PUT_THROUGH,
)
from tools.derive_research_intelligence_digest import (
    CASE_EXPLICIT_DIVERGENCE,
    FLAG_HIGH_VOL_LOW_VALUE,
    FLAG_LOW_REL_VOL_WITH_ACTIVITY,
    FLAG_PRICE_FLOW_DIVERGENCE,
    FLAG_PUT_THROUGH_DOMINANCE,
    INSUFFICIENT_COVERAGE,
    PUT_THROUGH_RECORDED,
)

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "capability_first_daily_analyst_brief/v1"
REQUIRED_INPUT_IDENTITY_PREFIX = "research_intelligence_digest_v1:"

MAX_MAIN_CASES = 10
MAX_PUT_THROUGH_CASES = 5
MAX_DIVERGENCE_CASES = 5

AUTHORITY_BOUNDARIES = {
    "authority_effect": "NONE",
    "ranking_authority": False,
    "recommendation_authority": False,
    "sizing_authority": False,
    "valuation_authority": False,
    "pit_backtest_eligible": False,
    "raw_as_traded_promoted": False,
    "database_mutated": False,
}

# Reason codes that make a ticker eligible for attention-case selection. Sourced only from
# codes/flag-types the upstream digest already computed -- nothing is invented here.
QUALIFYING_REASON_CODES: frozenset[str] = frozenset({
    CODE_PUT_THROUGH_DOMINANT,
    CODE_SIGNIFICANT_PUT_THROUGH,
    CODE_MATERIAL_ACTIVE_BUY_IMBALANCE,
    CODE_MATERIAL_ACTIVE_SELL_IMBALANCE,
    CODE_MATERIAL_PROP_NET_BUY,
    CODE_MATERIAL_PROP_NET_SELL,
    CODE_MOMENTUM_WITH_PROP_BUY,
    CODE_MOMENTUM_WITH_PROP_SELL,
    CODE_REVERSAL_WITH_ACTIVE_SELLING,
    CODE_HIGH_FOREIGN_ROOM,
    FLAG_PUT_THROUGH_DOMINANCE,
    FLAG_PRICE_FLOW_DIVERGENCE,
    FLAG_LOW_REL_VOL_WITH_ACTIVITY,
    FLAG_HIGH_VOL_LOW_VALUE,
})

# research_attention_priority: an explicit, non-investment ordering of which existing evidence a
# human reviews first. It is not a ranking, score, or recommendation of any kind.
ATTENTION_PRIORITY_CONTRACT = {
    "name": "research_attention_priority",
    "ranking_authority": False,
    "recommendation_authority": False,
    "max_main_cases": MAX_MAIN_CASES,
    "priority_tiers": {
        "1": "Multiple independent material reason codes on the same ticker.",
        "2": "Explicit divergence/contradiction across dimensions.",
        "3": "PUT_THROUGH_DOMINANT.",
        "4": "Material proprietary or microstructure threshold triggers.",
        "5": "Other single evidence-supported research flags.",
    },
    "tie_break_rules": [
        "number_of_distinct_qualifying_reason_codes_descending",
        "ticker_alphabetical_ascending",
    ],
    "disclaimer": (
        "research_attention_priority orders which existing evidence a human reviews first; it is "
        "not an expected-return ranking, quality score, conviction score, investment score, or "
        "market-cap preference, and it promotes no authority."
    ),
}

# Deterministic research-question templates, keyed by the single highest-priority qualifying
# code present on a ticker. Every template is a question about what happens next, never a
# forecast, target, or trade instruction.
_RESEARCH_QUESTION_TEMPLATES: dict[str, str] = {
    FLAG_PRICE_FLOW_DIVERGENCE: (
        "For {ticker}, does the same-session divergence between price direction and proprietary/"
        "order-flow direction resolve or persist in the next session?"
    ),
    CODE_PUT_THROUGH_DOMINANT: (
        "Is the unusually high negotiated-trade (put-through) share for {ticker} persistent "
        "across future sessions, or isolated to this session?"
    ),
    CODE_MOMENTUM_WITH_PROP_SELL: (
        "Does {ticker}'s price/volume momentum continue while proprietary flow remains negative?"
    ),
    CODE_MOMENTUM_WITH_PROP_BUY: (
        "Does {ticker}'s price/volume momentum continue while proprietary flow remains positive, "
        "or does it fade?"
    ),
    CODE_REVERSAL_WITH_ACTIVE_SELLING: (
        "Does active selling in {ticker} persist in subsequent sessions alongside negative price "
        "action?"
    ),
    CODE_HIGH_FOREIGN_ROOM: (
        "Does foreign-room utilization in {ticker} remain elevated and coincide with changes in "
        "price/volume behavior?"
    ),
    CODE_SIGNIFICANT_PUT_THROUGH: (
        "Does {ticker}'s significant put-through share reflect a recurring pattern or a single-"
        "session event?"
    ),
    CODE_MATERIAL_ACTIVE_BUY_IMBALANCE: (
        "Does {ticker}'s material active buy-order imbalance continue in subsequent sessions?"
    ),
    CODE_MATERIAL_ACTIVE_SELL_IMBALANCE: (
        "Does {ticker}'s material active sell-order imbalance continue in subsequent sessions?"
    ),
    CODE_MATERIAL_PROP_NET_BUY: (
        "Does {ticker}'s material proprietary net-buy flow continue in subsequent sessions?"
    ),
    CODE_MATERIAL_PROP_NET_SELL: (
        "Does {ticker}'s material proprietary net-sell flow continue in subsequent sessions?"
    ),
    FLAG_LOW_REL_VOL_WITH_ACTIVITY: (
        "Is {ticker}'s elevated traded value against a depressed relative-volume baseline a data "
        "artifact, or a genuine shift in participation?"
    ),
    FLAG_HIGH_VOL_LOW_VALUE: (
        "Was {ticker}'s recent price move supported by proportionate trading activity, or was it "
        "thinly traded?"
    ),
}

# Fixed precedence for picking exactly one template when a ticker qualifies under several codes.
_QUESTION_TEMPLATE_PRIORITY: tuple[str, ...] = (
    FLAG_PRICE_FLOW_DIVERGENCE,
    CODE_PUT_THROUGH_DOMINANT,
    CODE_MOMENTUM_WITH_PROP_SELL,
    CODE_MOMENTUM_WITH_PROP_BUY,
    CODE_REVERSAL_WITH_ACTIVE_SELLING,
    CODE_HIGH_FOREIGN_ROOM,
    CODE_SIGNIFICANT_PUT_THROUGH,
    CODE_MATERIAL_ACTIVE_BUY_IMBALANCE,
    CODE_MATERIAL_ACTIVE_SELL_IMBALANCE,
    CODE_MATERIAL_PROP_NET_BUY,
    CODE_MATERIAL_PROP_NET_SELL,
    FLAG_LOW_REL_VOL_WITH_ACTIVITY,
    FLAG_HIGH_VOL_LOW_VALUE,
)


class InputDigestIdentityError(ValueError):
    """Raised when the input research_intelligence_digest_v1 lacks a valid identity/authority posture."""


def _canonical_json(val: Any) -> str:
    return json.dumps(val, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_json(val: Any) -> str:
    return hashlib.sha256(_canonical_json(val).encode("utf-8")).hexdigest()


def validate_input_digest(research_intelligence_digest: Mapping[str, Any]) -> None:
    """Fail closed if the input digest lacks a valid identity or a NONE authority posture."""
    identity = research_intelligence_digest.get("digest_identity")
    if not identity or not isinstance(identity, str) or not identity.startswith(REQUIRED_INPUT_IDENTITY_PREFIX):
        raise InputDigestIdentityError(
            "research_intelligence_digest_v1 input is missing a valid digest_identity "
            f"(expected prefix {REQUIRED_INPUT_IDENTITY_PREFIX!r}, got {identity!r}); refusing to "
            "build a daily analyst brief from an unidentified or incompatible input."
        )
    authority = research_intelligence_digest.get("authority_boundaries", {})
    if authority.get("authority_effect") != "NONE":
        raise InputDigestIdentityError(
            "research_intelligence_digest_v1 input does not declare authority_effect == 'NONE' "
            f"(got {authority.get('authority_effect')!r}); refusing to build a brief from an "
            "artifact with a promoted authority posture."
        )


def _build_cohort_membership_map(cohort_profiles: Mapping[str, Any]) -> dict[str, list[str]]:
    membership: dict[str, list[str]] = {}
    for cohort_name, profile in cohort_profiles.items():
        for ticker in profile["member_tickers"]:
            membership.setdefault(ticker, []).append(cohort_name)
    return membership


def _build_ticker_evidence_map(research_intelligence_digest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Per-ticker merged price/trading facts, sourced only from fields already in this digest.

    put_through_digest covers every acquired trading-history symbol (return_1d, relative volume,
    value composition) but not close/MA20. cross_dimension_cases target records additionally
    carry close/MA20/above_ma20 for the fully/partially enriched subset. Where both exist, the
    richer cross-dimension record wins; where only put_through_digest exists, the MA20 fields
    stay None (never fabricated, never zero-filled).
    """
    evidence: dict[str, dict[str, Any]] = {}

    for e in research_intelligence_digest["put_through_digest"]["entries"]:
        evidence[e["ticker"]] = {
            "return_1d": e["return_1d"],
            "relative_volume_provider_scoped": e["relative_volume_provider_scoped"],
            "matched_traded_value_vnd": e["matched_traded_value_vnd"],
            "put_through_traded_value_vnd": e["put_through_traded_value_vnd"],
            "put_through_share_ratio": e["put_through_share_ratio"],
            "put_through_status": e["put_through_status"],
            "close_vnd": None,
            "ma_20_vnd": None,
            "above_ma20": None,
            "trading_history_status": "ACQUIRED",
        }

    for bucket in research_intelligence_digest["cross_dimension_cases"]["cases"].values():
        for rec in bucket["members"]:
            ticker = rec["ticker"]
            entry = evidence.setdefault(ticker, {"trading_history_status": "ACQUIRED"})
            pt = rec["price_and_trend"]
            tv = rec["traded_value_composition"]
            entry["return_1d"] = pt.get("return_1d")
            entry["relative_volume_provider_scoped"] = pt.get("relative_volume")
            entry["close_vnd"] = pt.get("close_vnd")
            entry["ma_20_vnd"] = pt.get("ma_20_vnd")
            entry["above_ma20"] = pt.get("above_ma20")
            entry["matched_traded_value_vnd"] = tv.get("matched_traded_value_vnd")
            entry["put_through_traded_value_vnd"] = tv.get("put_through_traded_value_vnd")
            entry["put_through_share_ratio"] = tv.get("put_through_share_ratio")

    return evidence


def _gather_candidate_tickers(
    cross_dimension_cases: Mapping[str, Any],
    follow_up_flags: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """ticker -> {qualifying_codes, flag_types, is_divergent, cross_dimension_record}."""
    candidates: dict[str, dict[str, Any]] = {}

    seen_cd_tickers: set[str] = set()
    for bucket in cross_dimension_cases["cases"].values():
        for member in bucket["members"]:
            ticker = member["ticker"]
            if ticker in seen_cd_tickers:
                continue
            seen_cd_tickers.add(ticker)
            entry = candidates.setdefault(ticker, {
                "qualifying_codes": set(), "flag_types": set(), "cross_dimension_record": None,
            })
            entry["cross_dimension_record"] = member
            entry["qualifying_codes"] |= (set(member["reason_codes"]) & QUALIFYING_REASON_CODES)

    is_divergent_tickers = {m["ticker"] for m in cross_dimension_cases["cases"][CASE_EXPLICIT_DIVERGENCE]["members"]}

    for flag in follow_up_flags["flags"]:
        ticker = flag["ticker"]
        entry = candidates.setdefault(ticker, {
            "qualifying_codes": set(), "flag_types": set(), "cross_dimension_record": None,
        })
        entry["flag_types"].add(flag["flag_type"])
        if flag["flag_type"] in QUALIFYING_REASON_CODES:
            entry["qualifying_codes"].add(flag["flag_type"])

    for ticker, entry in candidates.items():
        entry["is_divergent"] = ticker in is_divergent_tickers

    # Only tickers with at least one qualifying code are genuinely eligible.
    return {t: e for t, e in candidates.items() if e["qualifying_codes"]}


def _classify_attention_priority(qualifying_codes: set[str], is_divergent: bool) -> int:
    """First-match priority cascade -- explicit, non-investment (see ATTENTION_PRIORITY_CONTRACT)."""
    if len(qualifying_codes) >= 2:
        return 1
    if is_divergent:
        return 2
    if CODE_PUT_THROUGH_DOMINANT in qualifying_codes:
        return 3
    if qualifying_codes & {
        CODE_MATERIAL_PROP_NET_BUY, CODE_MATERIAL_PROP_NET_SELL,
        CODE_MATERIAL_ACTIVE_BUY_IMBALANCE, CODE_MATERIAL_ACTIVE_SELL_IMBALANCE,
    }:
        return 4
    return 5


def _select_attention_cases(
    candidates: Mapping[str, Mapping[str, Any]], max_cases: int,
) -> list[tuple[int, str, Mapping[str, Any]]]:
    scored: list[tuple[int, int, str, Mapping[str, Any]]] = []
    for ticker, entry in candidates.items():
        priority = _classify_attention_priority(entry["qualifying_codes"], entry["is_divergent"])
        scored.append((priority, -len(entry["qualifying_codes"]), ticker, entry))
    scored.sort(key=lambda x: (x[0], x[1], x[2]))
    return [(priority, ticker, entry) for priority, _neg_count, ticker, entry in scored[:max_cases]]


def _build_research_question(ticker: str, qualifying_codes: set[str]) -> str:
    for code in _QUESTION_TEMPLATE_PRIORITY:
        if code in qualifying_codes:
            return _RESEARCH_QUESTION_TEMPLATES[code].format(ticker=ticker)
    return f"What explains the combination of flagged evidence for {ticker} this session?"


def _build_case_card(
    ticker: str,
    priority: int,
    entry: Mapping[str, Any],
    evidence_map: Mapping[str, Mapping[str, Any]],
    cohort_membership_map: Mapping[str, list[str]],
) -> dict[str, Any]:
    ev = evidence_map.get(ticker, {})
    cd_record = entry.get("cross_dimension_record")

    price_context = {
        "return_1d": ev.get("return_1d"),
        "close_vnd": ev.get("close_vnd"),
        "ma_20_vnd": ev.get("ma_20_vnd"),
        "above_ma20": ev.get("above_ma20"),
        "relative_volume_provider_scoped": ev.get("relative_volume_provider_scoped"),
    }
    trading_activity = {
        "matched_traded_value_vnd": ev.get("matched_traded_value_vnd"),
        "put_through_traded_value_vnd": ev.get("put_through_traded_value_vnd"),
        "put_through_share_ratio": ev.get("put_through_share_ratio"),
    }

    if cd_record is not None:
        prop = cd_record["proprietary_flow"]
        micro = cd_record["microstructure"]
        fr = cd_record["foreign_room"]
        cross_dimension = {
            "proprietary_net_value_vnd": prop.get("net_value_vnd"),
            "proprietary_flow_status": prop.get("status"),
            "active_imbalance_ratio": micro.get("imbalance_ratio"),
            "microstructure_status": micro.get("status"),
            "foreign_room_utilization_ratio": fr.get("utilization_ratio"),
            "foreign_room_status": fr.get("status"),
        }
        enrichment_tier = cd_record["enrichment_tier"]
        missing_dimensions = dict(cd_record["missing_or_failed_capabilities"])
    else:
        cross_dimension = {
            "proprietary_net_value_vnd": None,
            "proprietary_flow_status": "NOT_IN_CROSS_DIMENSION_DIGEST",
            "active_imbalance_ratio": None,
            "microstructure_status": "NOT_IN_CROSS_DIMENSION_DIGEST",
            "foreign_room_utilization_ratio": None,
            "foreign_room_status": "NOT_IN_CROSS_DIMENSION_DIGEST",
        }
        enrichment_tier = "TRADING_HISTORY_ONLY_OR_UNKNOWN"
        missing_dimensions = {}

    return {
        "ticker": ticker,
        "attention_priority": priority,
        "research_cohort_memberships": sorted(cohort_membership_map.get(ticker, [])),
        "why_selected": {
            "reason_codes": sorted(entry["qualifying_codes"]),
            "follow_up_flag_types": sorted(entry["flag_types"]),
        },
        "price_context": price_context,
        "trading_activity": trading_activity,
        "cross_dimension": cross_dimension,
        "coverage": {
            "trading_history_status": ev.get("trading_history_status", "UNKNOWN"),
            "enrichment_tier": enrichment_tier,
            "missing_dimensions": missing_dimensions,
        },
        "research_question": _build_research_question(ticker, entry["qualifying_codes"]),
    }


def build_market_in_one_minute(research_intelligence_digest: Mapping[str, Any]) -> dict[str, Any]:
    ms = research_intelligence_digest["market_state"]
    return {
        "source_artifact_identity": ms["source_artifact_identity"],
        "universe_denominator": ms["universe_count"],
        "regime_label": ms["regime_classification"]["regime_label"],
        "regime_derivation_reason": ms["regime_classification"]["derivation_reason"],
        "breadth": ms["breadth"],
        "moving_average_breadth": ms["moving_average_breadth"],
        "median_return_1d": ms["return_distribution"]["median_return_1d"],
        "relative_volume_breadth": ms["relative_volume_breadth"],
        "volatility_distribution": ms["volatility_distribution"],
    }


def build_cohort_snapshot(research_intelligence_digest: Mapping[str, Any]) -> dict[str, Any]:
    profiles = research_intelligence_digest["cohort_profiles"]
    comparison_metrics = research_intelligence_digest["cohort_comparison"]["metrics"]

    cohorts: dict[str, Any] = {}
    for cohort_name, profile in profiles.items():
        cohorts[cohort_name] = {
            "total_member_count": profile["total_member_count"],
            "trading_history_covered_count": profile["trading_history_covered_count"],
            "trading_history_coverage_ratio": profile["trading_history_coverage_ratio"],
            "median_return_1d": profile["return_distribution"]["median"],
            "median_relative_volume": profile["relative_volume_distribution"]["median"],
            "median_matched_traded_value_vnd_among_covered": comparison_metrics["median_matched_traded_value_vnd_among_covered"][cohort_name],
            "put_through_incidence_among_covered": comparison_metrics["put_through_incidence_ratio_among_covered"][cohort_name],
        }

    return {
        "scope": "FULL_RESEARCH_UNIVERSE",
        "cohorts": cohorts,
        "comparison_contract": research_intelligence_digest["cohort_comparison"]["comparison_contract"],
    }


def build_divergences(research_intelligence_digest: Mapping[str, Any], max_cases: int = MAX_DIVERGENCE_CASES) -> dict[str, Any]:
    members = research_intelligence_digest["cross_dimension_cases"]["cases"][CASE_EXPLICIT_DIVERGENCE]["members"]
    bounded = members[:max_cases]
    cases = []
    for m in bounded:
        cases.append({
            "ticker": m["ticker"],
            "price_vs_prop_alignment": m["cross_dimension_analysis"]["price_vs_prop_alignment"],
            "price_vs_order_imbalance_alignment": m["cross_dimension_analysis"]["price_vs_order_imbalance_alignment"],
            "return_1d": m["price_and_trend"]["return_1d"],
            "proprietary_net_value_vnd": m["proprietary_flow"].get("net_value_vnd"),
            "active_imbalance_ratio": m["microstructure"].get("imbalance_ratio"),
            "reason_codes": list(m["reason_codes"]),
        })
    return {"max_cases": max_cases, "total_available": len(members), "cases": cases}


def build_put_through_watch(
    research_intelligence_digest: Mapping[str, Any],
    cohort_membership_map: Mapping[str, list[str]],
    max_cases: int = MAX_PUT_THROUGH_CASES,
) -> dict[str, Any]:
    entries = [
        e for e in research_intelligence_digest["put_through_digest"]["entries"]
        if e["put_through_status"] == PUT_THROUGH_RECORDED
    ]
    entries_sorted = sorted(entries, key=lambda e: (e["put_through_share_ratio"] or 0.0, e["ticker"]), reverse=True)
    bounded = entries_sorted[:max_cases]
    cases = []
    for e in bounded:
        cases.append({
            "ticker": e["ticker"],
            "matched_traded_value_vnd": e["matched_traded_value_vnd"],
            "put_through_traded_value_vnd": e["put_through_traded_value_vnd"],
            "put_through_share_ratio": e["put_through_share_ratio"],
            "return_1d": e["return_1d"],
            "relative_volume_provider_scoped": e["relative_volume_provider_scoped"],
            "cohort_memberships": sorted(cohort_membership_map.get(e["ticker"], [])),
            "put_through_status": e["put_through_status"],
        })
    return {"max_cases": max_cases, "total_available": len(entries_sorted), "cases": cases}


def build_data_limitations(research_intelligence_digest: Mapping[str, Any]) -> dict[str, Any]:
    cov = research_intelligence_digest["coverage_and_data_quality"]
    backlog = research_intelligence_digest["data_coverage_backlog"]
    return {
        "tiers": cov["tiers"],
        "reconciliation": cov["reconciliation"],
        "disclaimer": cov["disclaimer"],
        "coverage_gap_examples": backlog["coverage_gap_examples"],
        "coverage_gap_backlog_disclaimer": backlog["disclaimer"],
        "statement": "Coverage gaps recorded above are data limitations, not acquisition recommendations.",
    }


def build_current_valuation_research_section(current_valuation_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Opt-in coverage pass-through. Does not affect attention-case selection or VALUE eligibility."""
    from market_wide_current_valuation_input_scaleout import content_identity as valuation_identity

    if valuation_identity(current_valuation_artifact)["artifact_sha256"] != current_valuation_artifact.get("artifact_sha256"):
        raise InputDigestIdentityError("current valuation artifact failed content-identity verification")
    coverage = current_valuation_artifact.get("coverage") or {}
    value_lane = current_valuation_artifact.get("value_strategy_readiness") or {}
    return {
        "source_artifact_identity": current_valuation_artifact.get("artifact_identity"),
        "valuation_session": current_valuation_artifact.get("valuation_session"),
        "universe_denominator": coverage.get("universe_denominator"),
        "price_ready": coverage.get("price_ready"),
        "share_authority_tiers": coverage.get("share_authority_tiers"),
        "metric_ready_counts": coverage.get("metric_ready_counts"),
        "metric_research_usable_counts": coverage.get("metric_research_usable_counts"),
        "metric_blocked_counts": coverage.get("metric_blocked_counts"),
        "metric_not_applicable_counts": coverage.get("metric_not_applicable_counts"),
        "value_strategy_eligible": value_lane.get("eligible", 0),
        "value_strategy_blocked": value_lane.get("blocked"),
        "research_usable_does_not_satisfy_value": True,
        "attention_priority_unaffected": True,
        "allowed_uses": ["CURRENT_RESEARCH_CONTEXT_ONLY"],
        "forbidden_uses": [
            "AUTHORITATIVE_VALUATION", "VALUE_STRATEGY_ELIGIBILITY", "TARGET_PRICE",
            "BUY_RECOMMENDATION", "SIZING", "RANKING",
        ],
    }


def build_daily_analyst_brief(
    research_intelligence_digest: Mapping[str, Any],
    current_valuation_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validate_input_digest(research_intelligence_digest)

    session_date = research_intelligence_digest["session_date"]
    cohort_membership_map = _build_cohort_membership_map(research_intelligence_digest["cohort_profiles"])
    evidence_map = _build_ticker_evidence_map(research_intelligence_digest)

    market_in_one_minute = build_market_in_one_minute(research_intelligence_digest)
    cohort_snapshot = build_cohort_snapshot(research_intelligence_digest)

    candidates = _gather_candidate_tickers(
        research_intelligence_digest["cross_dimension_cases"], research_intelligence_digest["follow_up_flags"],
    )
    selected = _select_attention_cases(candidates, max_cases=MAX_MAIN_CASES)
    cases = [
        _build_case_card(ticker, priority, entry, evidence_map, cohort_membership_map)
        for priority, ticker, entry in selected
    ]

    put_through_watch = build_put_through_watch(research_intelligence_digest, cohort_membership_map)
    divergences = build_divergences(research_intelligence_digest)
    data_limitations = build_data_limitations(research_intelligence_digest)

    research_questions_for_next_review = [
        {"ticker": c["ticker"], "research_question": c["research_question"]} for c in cases
    ]

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "session_date": session_date,
        "execution_timestamp": datetime.now(UTC).isoformat(),
        "input_digest_identity": research_intelligence_digest["digest_identity"],
        "market_in_one_minute": market_in_one_minute,
        "cohort_snapshot": cohort_snapshot,
        "attention_priority_contract": ATTENTION_PRIORITY_CONTRACT,
        "cases_to_review": {
            "max_cases": MAX_MAIN_CASES,
            "total_eligible_candidates": len(candidates),
            "cases": cases,
        },
        "put_through_watch": put_through_watch,
        "divergences": divergences,
        "data_limitations": data_limitations,
        "research_questions_for_next_review": research_questions_for_next_review,
        "authority_boundaries": AUTHORITY_BOUNDARIES,
    }
    if current_valuation_artifact is not None:
        artifact["current_valuation_research"] = build_current_valuation_research_section(current_valuation_artifact)

    brief_sha256 = _sha256_json({
        k: v for k, v in artifact.items()
        if k not in {"brief_sha256", "brief_identity", "execution_timestamp"}
    })
    artifact["brief_sha256"] = brief_sha256
    artifact["brief_identity"] = f"daily_analyst_brief_v1:{brief_sha256}"

    return artifact


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def generate_daily_analyst_brief_markdown(artifact: Mapping[str, Any]) -> str:
    session = artifact["session_date"]
    m1 = artifact["market_in_one_minute"]
    cohorts = artifact["cohort_snapshot"]["cohorts"]
    cases_block = artifact["cases_to_review"]
    cases = cases_block["cases"]
    pt_watch = artifact["put_through_watch"]
    div = artifact["divergences"]
    dl = artifact["data_limitations"]
    questions = artifact["research_questions_for_next_review"]

    md: list[str] = [
        f"# Daily Analyst Brief — Session {session}",
        "",
        f"- **Brief Identity**: `{artifact['brief_identity']}`",
        f"- **Input Digest Identity**: `{artifact['input_digest_identity']}`",
        f"- **Contract Version**: `{artifact['contract_version']}`",
        "- **Authority**: research-only -- `ranking_authority=False`, `recommendation_authority=False`, "
        "`sizing_authority=False`, `valuation_authority=False`, `pit_backtest_eligible=False`.",
        "",
        "---",
        "",
        "# MARKET IN ONE MINUTE",
        "",
        f"- **Regime**: `{m1['regime_label']}` -- {m1['regime_derivation_reason']}",
        f"- **Breadth**: {m1['breadth']['advancers_count']} up / {m1['breadth']['decliners_count']} down / "
        f"{m1['breadth']['unchanged_count']} flat (A/D ratio `{m1['breadth']['advance_decline_ratio']}`), "
        f"of `{m1['universe_denominator']}` symbols",
        f"- **Above 20D MA**: `{m1['moving_average_breadth']['above_ma20_count']}/{m1['universe_denominator']}` "
        f"({m1['moving_average_breadth']['above_ma20_ratio'] * 100:.1f}%)",
        f"- **Median 1D Return**: `{m1['median_return_1d'] * 100:+.2f}%`",
        f"- **Relative Volume**: elevated `{m1['relative_volume_breadth']['elevated_volume_count']}`, "
        f"normal `{m1['relative_volume_breadth']['normal_volume_count']}`, "
        f"depressed `{m1['relative_volume_breadth']['depressed_volume_count']}`, "
        f"median `{m1['relative_volume_breadth']['median_relative_volume']:.2f}x`",
        f"- **20D Volatility (median)**: `{m1['volatility_distribution']['median_volatility_20d']:.4f}`",
        "",
        "---",
        "",
        "# WHAT CHANGED / WHAT STANDS OUT",
        "",
        f"- `{cases_block['total_eligible_candidates']}` tickers carry at least one evidence-supported "
        f"research flag this session; `{len(cases)}` selected below under `research_attention_priority` "
        "(attention order, not an investment ranking).",
        f"- `{div['total_available']}` explicit cross-dimension divergence(s) observed (showing up to `{div['max_cases']}`).",
        f"- `{pt_watch['total_available']}` symbol(s) show a recorded (non-zero) put-through print (showing up to `{pt_watch['max_cases']}`).",
    ]
    valuation = artifact.get("current_valuation_research")
    if isinstance(valuation, Mapping):
        md.extend([
            f"- Current valuation research (non-authoritative): session `{valuation.get('valuation_session')}`; "
            f"denominator `{valuation.get('universe_denominator')}`; "
            f"VALUE eligible `{valuation.get('value_strategy_eligible')}` / blocked `{valuation.get('value_strategy_blocked')}`. "
            "Research-usable multiples do not create recommendation, VALUE-eligibility, or target-price authority.",
        ])
    md.extend([
        "",
        "---",
        "",
        "# COHORT SNAPSHOT",
        "",
        "| Cohort | Members | FHSC Covered | Median Return | Median Rel Vol | Median Matched Value (covered) | PT Incidence (covered) |",
        "|:---|---:|---:|---:|---:|---:|---:|",
    ])

    for name, c in cohorts.items():
        cov_s = f"{c['trading_history_covered_count']}/{c['total_member_count']}"
        ret_s = f"{c['median_return_1d'] * 100:+.2f}%" if c["median_return_1d"] is not None else "N/A"
        rv_s = f"{c['median_relative_volume']:.2f}x" if c["median_relative_volume"] is not None else "N/A"
        mv_cell = c["median_matched_traded_value_vnd_among_covered"]
        mv_s = (
            f"`{INSUFFICIENT_COVERAGE}`" if mv_cell["value"] == INSUFFICIENT_COVERAGE
            else f"{mv_cell['value']:,.0f} (n={mv_cell['denominator']})"
        )
        pt_cell = c["put_through_incidence_among_covered"]
        pt_s = (
            f"`{INSUFFICIENT_COVERAGE}`" if pt_cell["value"] == INSUFFICIENT_COVERAGE
            else f"{pt_cell['value'] * 100:.1f}% (n={pt_cell['denominator']})"
        )
        md.append(f"| **{name}** | {c['total_member_count']} | {cov_s} | {ret_s} | {rv_s} | {mv_s} | {pt_s} |")

    md.extend([
        "",
        "---",
        "",
        "# CASES TO REVIEW",
        "",
        "> `research_attention_priority` orders which existing evidence a human reviews first; it is "
        "not an investment ranking, score, or recommendation (`ranking_authority=False`).",
        "",
    ])
    for c in cases:
        pcx, ta, cdx, cov = c["price_context"], c["trading_activity"], c["cross_dimension"], c["coverage"]
        ret_s = f"{pcx['return_1d'] * 100:+.2f}%" if pcx["return_1d"] is not None else "N/A"
        rv_s = f"{pcx['relative_volume_provider_scoped']:.2f}x" if pcx["relative_volume_provider_scoped"] is not None else "N/A"
        ma_s = (
            f", Close `{pcx['close_vnd']:,.0f}` vs MA20 `{pcx['ma_20_vnd']:,.0f}`"
            if pcx["close_vnd"] is not None and pcx["ma_20_vnd"] is not None else ""
        )
        mv_s = f"{ta['matched_traded_value_vnd']:,.0f} VND" if ta["matched_traded_value_vnd"] is not None else "N/A"
        pt_s = f"{ta['put_through_share_ratio'] * 100:.1f}%" if ta["put_through_share_ratio"] is not None else "N/A"
        prop_s = f"{cdx['proprietary_net_value_vnd']:+,.0f} VND" if cdx["proprietary_net_value_vnd"] is not None else cdx["proprietary_flow_status"]
        imb_s = f"{cdx['active_imbalance_ratio']:+.3f}" if cdx["active_imbalance_ratio"] is not None else cdx["microstructure_status"]
        room_s = f"{cdx['foreign_room_utilization_ratio'] * 100:.1f}%" if cdx["foreign_room_utilization_ratio"] is not None else cdx["foreign_room_status"]
        # reason_codes and follow_up_flag_types intentionally overlap in vocabulary (a flag_type
        # can itself be a qualifying code); dedupe only for this human-readable concatenation.
        reasons_s = "; ".join(sorted(set(c["why_selected"]["reason_codes"]) | set(c["why_selected"]["follow_up_flag_types"])))

        md.extend([
            f"### {c['ticker']} (attention priority `{c['attention_priority']}`, tier `{cov['enrichment_tier']}`)",
            f"- **Cohorts**: {', '.join(c['research_cohort_memberships']) or 'NONE'}",
            f"- **Why selected**: {reasons_s}",
            f"- **Price**: `{ret_s}` return, RelVol `{rv_s}`{ma_s}",
            f"- **Trading activity**: Matched `{mv_s}`, PT share `{pt_s}`",
            f"- **Cross-dimension**: Prop net `{prop_s}`, Active imbalance `{imb_s}`, Foreign room `{room_s}`",
            f"- **Research question**: {c['research_question']}",
            "",
        ])

    md.extend([
        "---",
        "",
        "# PUT-THROUGH WATCH",
        "",
        f"> Showing `{len(pt_watch['cases'])}` of `{pt_watch['total_available']}` recorded put-through cases "
        f"(max `{pt_watch['max_cases']}`). Facts only -- no actor identity is implied.",
        "",
        "| Ticker | Matched (VND) | PT (VND) | PT Share | Return | Rel Vol | Cohorts |",
        "|:---|---:|---:|---:|---:|---:|:---|",
    ])
    for c in pt_watch["cases"]:
        mv_s = f"{c['matched_traded_value_vnd']:,.0f}" if c["matched_traded_value_vnd"] is not None else "N/A"
        pv_s = f"{c['put_through_traded_value_vnd']:,.0f}" if c["put_through_traded_value_vnd"] is not None else "N/A"
        pt_s = f"{c['put_through_share_ratio'] * 100:.1f}%" if c["put_through_share_ratio"] is not None else "N/A"
        ret_s = f"{c['return_1d'] * 100:+.2f}%" if c["return_1d"] is not None else "N/A"
        rv_s = f"{c['relative_volume_provider_scoped']:.2f}x" if c["relative_volume_provider_scoped"] is not None else "N/A"
        cohorts_s = ", ".join(c["cohort_memberships"]) or "NONE"
        md.append(f"| **{c['ticker']}** | {mv_s} | {pv_s} | {pt_s} | {ret_s} | {rv_s} | {cohorts_s} |")

    md.extend([
        "",
        "---",
        "",
        "# CROSS-DIMENSION DIVERGENCES",
        "",
        f"> Showing `{len(div['cases'])}` of `{div['total_available']}` explicit divergence case(s) "
        f"(max `{div['max_cases']}`). Facts only; no bullish/bearish label, no causal inference.",
        "",
        "| Ticker | Price-vs-Prop | Price-vs-OrderFlow | Return | Prop Net (VND) | Imbalance |",
        "|:---|:---|:---|---:|---:|---:|",
    ])
    for c in div["cases"]:
        ret_s = f"{c['return_1d'] * 100:+.2f}%" if c["return_1d"] is not None else "N/A"
        prop_s = f"{c['proprietary_net_value_vnd']:+,.0f}" if c["proprietary_net_value_vnd"] is not None else "N/A"
        imb_s = f"{c['active_imbalance_ratio']:+.3f}" if c["active_imbalance_ratio"] is not None else "N/A"
        md.append(f"| **{c['ticker']}** | `{c['price_vs_prop_alignment']}` | `{c['price_vs_order_imbalance_alignment']}` | {ret_s} | {prop_s} | {imb_s} |")

    md.extend([
        "",
        "---",
        "",
        "# DATA LIMITATIONS",
        "",
        "| Tier | Count |",
        "|:---|---:|",
    ])
    for k, v in dl["tiers"].items():
        md.append(f"| `{k}` | {v} |")
    examples = dl["coverage_gap_examples"]
    md.extend([
        "",
        f"*{dl['statement']}*",
        "",
        f"Bounded coverage-gap examples carried from the upstream digest (already capped there): "
        f"`{examples['returned_count']}` of `{examples['total_available_count']}` total "
        f"(max `{examples['max_examples']}`); not shown per-symbol here to keep this brief short -- see the "
        "research_intelligence_digest_v1 artifact for the full bounded list.",
        "",
        "---",
        "",
        "# RESEARCH QUESTIONS FOR NEXT REVIEW",
        "",
    ])
    for q in questions:
        md.append(f"- **{q['ticker']}**: {q['research_question']}")

    md.extend([
        "",
        "---",
        "",
        "## Authority Boundaries",
        "",
    ])
    for k, v in artifact["authority_boundaries"].items():
        md.append(f"- `{k}`: `{v}`")

    return "\n".join(md) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the deterministic Daily Analyst Brief V1 from the research_intelligence_digest_v1 artifact."
    )
    parser.add_argument(
        "--digest-path",
        default="operations-review/research-intelligence-digest-2026-08-21/research_intelligence_digest_v1.json",
    )
    parser.add_argument(
        "--out-dir",
        default="operations-review/daily-analyst-brief-2026-08-21",
    )
    parser.add_argument(
        "--valuation-path",
        default=None,
        help="Optional current-valuation research artifact. Coverage only; does not change attention cases.",
    )
    args = parser.parse_args(argv)

    def _resolve(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else ROOT / path

    digest_path = _resolve(args.digest_path)
    out_dir = _resolve(args.out_dir)

    print(f"Loading research intelligence digest from: {digest_path}")
    research_intelligence_digest = json.loads(digest_path.read_text(encoding="utf-8"))

    print("Building daily analyst brief...")
    valuation_artifact = None
    if args.valuation_path:
        valuation_artifact = json.loads(_resolve(args.valuation_path).read_text(encoding="utf-8"))
    artifact = build_daily_analyst_brief(research_intelligence_digest, current_valuation_artifact=valuation_artifact)

    summary_md = generate_daily_analyst_brief_markdown(artifact)

    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / "daily_analyst_brief_v1.json"
    summary_path = out_dir / "daily_analyst_brief_v1_summary.md"
    manifest_path = out_dir / "manifest.json"

    atomic_write_json(artifact_path, artifact)
    atomic_write_file(summary_path, summary_md)

    manifest = {
        "manifest_schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "session_date": artifact["session_date"],
        "created_at": datetime.now(UTC).isoformat(),
        "brief_identity": artifact["brief_identity"],
        "brief_sha256": artifact["brief_sha256"],
        "input_digest_identity": artifact["input_digest_identity"],
        "files": {
            "daily_analyst_brief_v1.json": {
                "size_bytes": artifact_path.stat().st_size,
                "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            },
            "daily_analyst_brief_v1_summary.md": {
                "size_bytes": summary_path.stat().st_size,
                "sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
            },
        },
        "authority_boundaries": AUTHORITY_BOUNDARIES,
    }
    atomic_write_json(manifest_path, manifest)

    print(json.dumps({
        "status": "DAILY_ANALYST_BRIEF_COMPLETE",
        "brief_identity": artifact["brief_identity"],
        "session_date": artifact["session_date"],
        "total_eligible_candidates": artifact["cases_to_review"]["total_eligible_candidates"],
        "cases_selected": len(artifact["cases_to_review"]["cases"]),
        "divergences_shown": len(artifact["divergences"]["cases"]),
        "put_through_watch_shown": len(artifact["put_through_watch"]["cases"]),
        "out_dir": str(out_dir),
    }, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    sys.exit(main())
