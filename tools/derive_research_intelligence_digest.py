"""tools/derive_research_intelligence_digest.py — Research Intelligence Digest V1.

Cohesive integration layer over three already-retained, already-authoritative artifacts:
- scaleout_capability_research_digest.py -> capability_research_digest.json
  (524/524 DNSE market-wide core + FHSC acquired-enrichment cohort)
- derive_market_state_and_candidates.py -> market_state_and_candidates.json
  (descriptive regime/breadth + 5 deterministic research candidate cohorts)
- derive_cross_dimension_research_digest.py -> cross_dimension_research_digest.json
  (multi-endpoint FHSC cross-dimension cases for fully/partially enriched symbols)

This module does not recompute market breadth, cohort membership, or cross-dimension reason
codes: those remain the sole authority of their producing tools. It only joins, profiles,
compares, and surfaces what those three artifacts already contain, and adds three things that
do not exist upstream: per-cohort trading-history coverage profiling/comparison, deterministic
non-actionable research follow-up flags (evidence-supported analytical observations only), and
a separate, bounded, non-actionable data-coverage backlog (what is missing, never a priority
queue or acquisition recommendation).

Authority Boundary (identical in kind to all three upstream producers):
- authority_effect: "NONE"
- raw_as_traded_promoted: False
- pit_backtest_eligible: False
- liquidity_sizing_authority: "BLOCKED"
- valuation_authority: False
- recommendation_authority: False
- ranking_authority: False
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
    THRESHOLD_DEPRESSED_REL_VOL,
    THRESHOLD_DOMINANT_PUT_THROUGH,
    THRESHOLD_SIGNIFICANT_PUT_THROUGH,
)
from tools.derive_market_state_and_candidates import (
    COHORT_HIGH_ACTIVITY_REVERSAL,
    COHORT_HIGH_VOLATILITY_WATCH,
    COHORT_MOMENTUM_PARTICIPATION,
    COHORT_TREND_WITHOUT_PARTICIPATION,
)

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "capability_first_research_intelligence_digest/v1"

AUTHORITY_BOUNDARIES = {
    "authority_effect": "NONE",
    "raw_as_traded_promoted": False,
    "pit_backtest_eligible": False,
    "liquidity_sizing_authority": "BLOCKED",
    "valuation_authority": False,
    "recommendation_authority": False,
    "ranking_authority": False,
    "database_mutated": False,
}

AUTHORITY_DISCLAIMER = "DESCRIPTIVE_RESEARCH_DIGEST_NO_EXECUTION_NO_VALUATION_NO_RANKING_NO_RECOMMENDATION_AUTHORITY"

# The four active research cohorts this digest profiles (excludes FHSC_ENRICHED_FLOW_WATCH,
# which is coverage-scoped by construction and is instead surfaced through the put-through
# digest and cross-dimension cases sections).
ACTIVE_COHORT_NAMES: tuple[str, ...] = (
    COHORT_MOMENTUM_PARTICIPATION,
    COHORT_HIGH_ACTIVITY_REVERSAL,
    COHORT_HIGH_VOLATILITY_WATCH,
    COHORT_TREND_WITHOUT_PARTICIPATION,
)

INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE_FOR_COMPARISON"

NO_PUT_THROUGH_RECORDED = "NO_PUT_THROUGH_RECORDED"
PUT_THROUGH_RECORDED = "PUT_THROUGH_RECORDED"
PUT_THROUGH_UNKNOWN = "PUT_THROUGH_UNKNOWN"

# Cross-dimension case bucket identifiers (surfaced strictly from upstream reason codes).
CASE_MOMENTUM_WITH_PROP_BUY = "momentum_with_proprietary_net_buy"
CASE_MOMENTUM_WITH_PROP_SELL = "momentum_with_proprietary_net_sell"
CASE_REVERSAL_WITH_ACTIVE_SELLING = "reversal_price_down_with_material_active_sell_imbalance"
CASE_PRICE_UP_WITH_ACTIVE_BUY_IMBALANCE = "price_up_with_material_active_buy_imbalance"
CASE_PUT_THROUGH_DOMINANCE = "put_through_dominance"
CASE_HIGH_FOREIGN_ROOM = "high_foreign_room_utilization"
CASE_EXPLICIT_DIVERGENCE = "explicit_price_flow_divergence"

CROSS_DIMENSION_CASE_NAMES: tuple[str, ...] = (
    CASE_MOMENTUM_WITH_PROP_BUY,
    CASE_MOMENTUM_WITH_PROP_SELL,
    CASE_REVERSAL_WITH_ACTIVE_SELLING,
    CASE_PRICE_UP_WITH_ACTIVE_BUY_IMBALANCE,
    CASE_PUT_THROUGH_DOMINANCE,
    CASE_HIGH_FOREIGN_ROOM,
    CASE_EXPLICIT_DIVERGENCE,
)

# Deterministic, non-actionable follow-up flag types. Every flag here must be supported by
# ACQUIRED evidence (a real observation worth a closer analytical look) -- never a per-symbol
# "we don't have data for this yet" entry. That belongs in the data_coverage_backlog instead.
FLAG_PUT_THROUGH_DOMINANCE = "INVESTIGATE_PUT_THROUGH_DOMINANCE"
FLAG_PRICE_FLOW_DIVERGENCE = "INVESTIGATE_PRICE_FLOW_DIVERGENCE"
FLAG_LOW_REL_VOL_WITH_ACTIVITY = "INVESTIGATE_ACTIVITY_WITH_LOW_RELATIVE_VOLUME"
FLAG_HIGH_VOL_LOW_VALUE = "INVESTIGATE_HIGH_VOLATILITY_WITH_LOW_TRADING_VALUE"

FOLLOW_UP_FLAGS_DISCLAIMER = "FOLLOW_UP_FLAGS_ARE_RESEARCH_ONLY_NOT_RECOMMENDATIONS_NOT_RANKINGS_NOT_TARGETS_NOT_SIZING"

# data_coverage_backlog: a separate, bounded, descriptive-only inventory of what is missing.
# It is never a priority queue, acquisition recommendation, or next-wave authorization.
MAX_COVERAGE_GAP_EXAMPLES = 10
COVERAGE_GAP_EXAMPLE_LABEL = "COVERAGE_GAP_EXAMPLE"
DATA_COVERAGE_BACKLOG_DISCLAIMER = (
    "DATA_COVERAGE_BACKLOG_IS_DESCRIPTIVE_ONLY_NOT_AN_ACQUISITION_RECOMMENDATION_"
    "NOT_A_PRIORITY_QUEUE_NOT_A_NEXT_WAVE_AUTHORIZATION"
)

# Cohort-comparison sufficiency contract (explicit, not a hidden threshold): a metric is
# SAMPLE_DESCRIPTIVE whenever its observed denominator is >= 1; it is never extrapolated to the
# full cohort or universe. INSUFFICIENT_COVERAGE_FOR_COMPARISON fires only when the observed
# denominator is exactly 0. No minimum-N or minimum-coverage-ratio threshold beyond that exists.
MINIMUM_DENOMINATOR_FOR_DESCRIPTIVE_COMPARISON = 1
SAMPLE_DESCRIPTIVE = "SAMPLE_DESCRIPTIVE"


class IdentityChainMismatchError(ValueError):
    """Raised when the three upstream artifacts do not form one consistent provenance chain."""


def _canonical_json(val: Any) -> str:
    return json.dumps(val, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_json(val: Any) -> str:
    return hashlib.sha256(_canonical_json(val).encode("utf-8")).hexdigest()


def _distribution_stats(values: Sequence[float | None]) -> dict[str, Any]:
    """Deterministic descriptive distribution stats. Never treats a missing value as zero."""
    vals = sorted(v for v in values if v is not None)
    n = len(vals)
    if n == 0:
        return {"n": 0, "mean": None, "median": None, "p25": None, "p75": None, "min": None, "max": None}
    mid = n // 2
    median = vals[mid] if n % 2 == 1 else round((vals[mid - 1] + vals[mid]) / 2.0, 6)
    return {
        "n": n,
        "mean": round(sum(vals) / n, 6),
        "median": median,
        "p25": vals[int(n * 0.25)],
        "p75": vals[int(n * 0.75)],
        "min": vals[0],
        "max": vals[-1],
    }


def _put_through_status(put_through_value: float | None) -> str:
    if put_through_value is None:
        return PUT_THROUGH_UNKNOWN
    if put_through_value == 0:
        return NO_PUT_THROUGH_RECORDED
    return PUT_THROUGH_RECORDED


def _normalize_status_group(status: str | None) -> str:
    """Coarse grouping for narrative convenience only -- never a substitute for the raw status.

    Every caller of this function must also retain the exact upstream status string alongside
    the group; this mapping exists only so a reader can quickly tell "attempted but blocked"
    apart from "never attempted" without losing the precise reason. Mirrors the grouping
    tools.derive_cross_dimension_research_digest already applies to the same raw vocabulary.
    """
    if status == "ACQUIRED":
        return "ACQUIRED"
    if status == "PROVIDER_RATE_LIMITED":
        return "ATTEMPTED_RATE_LIMITED"
    if status in ("REQUESTED_BUT_MISSING", "MISSING_REQUESTED_SESSION", "TRANSPORT_TIMEOUT", "ACQUISITION_ERROR") or (status or "").startswith("FAILED_"):
        return "ATTEMPTED_BUT_MISSING_OR_FAILED"
    if status == "BUDGET_EXHAUSTED":
        return "ATTEMPTED_BUDGET_EXHAUSTED"
    if status == "CONFLICTING":
        return "ATTEMPTED_CONFLICTING_EVIDENCE"
    if status == "NOT_ACQUIRED_IN_THIS_SCALEOUT":
        return "GENUINELY_UNATTEMPTED"
    return "UNKNOWN_STATUS"


def validate_identity_chain(
    capability_digest: Mapping[str, Any],
    market_state_artifact: Mapping[str, Any],
    cross_dimension_digest: Mapping[str, Any],
) -> None:
    """Fail closed if the three artifacts do not cite one consistent provenance chain.

    Combining a fresh capability digest with a cross-dimension digest built from a stale,
    superseded capability digest would silently blend two different snapshots. That is
    exactly the failure this check exists to catch.
    """
    errors: list[str] = []

    cap_identity = capability_digest.get("digest_identity")
    ms_input_identity = market_state_artifact.get("input_digest_identity")
    cd_input_digest_identity = cross_dimension_digest.get("input_digest_identity")
    ms_identity = market_state_artifact.get("artifact_identity")
    cd_input_candidates_identity = cross_dimension_digest.get("input_candidates_identity")

    if ms_input_identity != cap_identity:
        errors.append(
            "market_state_and_candidates.input_digest_identity "
            f"({ms_input_identity!r}) does not match capability_research_digest.digest_identity "
            f"({cap_identity!r})"
        )
    if cd_input_digest_identity != cap_identity:
        errors.append(
            "cross_dimension_research_digest.input_digest_identity "
            f"({cd_input_digest_identity!r}) does not match capability_research_digest.digest_identity "
            f"({cap_identity!r})"
        )
    if cd_input_candidates_identity != ms_identity:
        errors.append(
            "cross_dimension_research_digest.input_candidates_identity "
            f"({cd_input_candidates_identity!r}) does not match market_state_and_candidates.artifact_identity "
            f"({ms_identity!r})"
        )

    sessions = {
        capability_digest.get("session_date"),
        market_state_artifact.get("session_date"),
        cross_dimension_digest.get("session_date"),
    }
    if len(sessions) > 1:
        errors.append(f"session_date is not consistent across the three inputs: {sorted(sessions)}")

    if errors:
        raise IdentityChainMismatchError(
            "Refusing to build research_intelligence_digest_v1 from an inconsistent provenance chain: "
            + "; ".join(errors)
        )


def _build_capability_record_map(capability_digest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["ticker"]: r for r in capability_digest["records"]}


def _build_cohort_membership_map(market_state_artifact: Mapping[str, Any]) -> dict[str, list[str]]:
    membership: dict[str, list[str]] = {}
    cohort_entries = market_state_artifact["research_candidate_cohorts"]["cohort_entries"]
    for cohort_name, entries in cohort_entries.items():
        for entry in entries:
            membership.setdefault(entry["ticker"], []).append(cohort_name)
    return membership


# ---------------------------------------------------------------------------
# 1. MARKET STATE (pass-through; no parallel recomputation)
# ---------------------------------------------------------------------------

def build_market_state_section(market_state_artifact: Mapping[str, Any]) -> dict[str, Any]:
    ms = market_state_artifact["market_state"]
    return {
        "source_artifact_identity": market_state_artifact["artifact_identity"],
        "source_input_digest_identity": market_state_artifact["input_digest_identity"],
        "aggregate_scope": ms["aggregate_scope"],
        "universe_count": ms["universe_count"],
        "session_date": ms["session_date"],
        "regime_classification": ms["regime_classification"],
        "breadth": ms["breadth"],
        "return_distribution": ms["return_distribution"],
        "moving_average_breadth": ms["moving_average_breadth"],
        "volatility_distribution": ms["volatility_distribution"],
        "relative_volume_breadth": ms["relative_volume_breadth"],
        "cross_metric_intersections": ms["cross_metric_intersections"],
        "descriptive_tails": ms["descriptive_tails"],
    }


# ---------------------------------------------------------------------------
# 2. ACTIVE COHORT PROFILES + 6. COHORT COMPARISON
# ---------------------------------------------------------------------------

def build_cohort_profiles(
    market_state_artifact: Mapping[str, Any],
    record_map: Mapping[str, Mapping[str, Any]],
    membership_map: Mapping[str, list[str]],
) -> dict[str, Any]:
    cohort_entries_all = market_state_artifact["research_candidate_cohorts"]["cohort_entries"]
    cohort_summaries_all = market_state_artifact["research_candidate_cohorts"]["cohort_summaries"]
    universe_count = market_state_artifact["market_state"]["universe_count"]

    profiles: dict[str, Any] = {}
    for cohort_name in ACTIVE_COHORT_NAMES:
        entries = cohort_entries_all.get(cohort_name, [])
        total_member_count = len(entries)
        member_tickers = sorted(e["ticker"] for e in entries)

        returns = [e["input_metrics"].get("return_1d") for e in entries]
        rel_vols = [e["input_metrics"].get("relative_volume_provider_scoped") for e in entries]

        covered_entries = [
            e for e in entries
            if record_map.get(e["ticker"], {}).get("fhsc_value_volume_composition", {}).get("status") == "ACQUIRED"
        ]
        covered_count = len(covered_entries)
        coverage_ratio = round(covered_count / total_member_count, 6) if total_member_count else None

        matched_values: list[float] = []
        put_through_shares: list[float] = []
        put_through_statuses: list[str] = []
        for e in covered_entries:
            comp = record_map[e["ticker"]]["fhsc_value_volume_composition"]
            mv = comp.get("matched_traded_value_vnd")
            pv = comp.get("put_through_traded_value_vnd")
            if mv is not None:
                matched_values.append(mv)
            put_through_statuses.append(_put_through_status(pv))
            ratio = comp.get("put_through_value_ratio")
            if ratio is not None:
                put_through_shares.append(ratio)

        recorded_count = sum(1 for s in put_through_statuses if s == PUT_THROUGH_RECORDED)
        none_recorded_count = sum(1 for s in put_through_statuses if s == NO_PUT_THROUGH_RECORDED)
        unknown_count = sum(1 for s in put_through_statuses if s == PUT_THROUGH_UNKNOWN)

        above_ma20 = sum(
            1 for e in entries
            if e["input_metrics"].get("close_vnd") is not None
            and e["input_metrics"].get("ma_20_vnd") is not None
            and e["input_metrics"]["close_vnd"] > e["input_metrics"]["ma_20_vnd"]
        )

        ranked = sorted(
            (e for e in entries if e["input_metrics"].get("return_1d") is not None),
            key=lambda e: e["input_metrics"]["return_1d"],
            reverse=True,
        )
        top_positive_tail = [
            {"ticker": e["ticker"], "return_1d": e["input_metrics"]["return_1d"]} for e in ranked[:3]
        ]
        top_negative_tail = (
            [{"ticker": e["ticker"], "return_1d": e["input_metrics"]["return_1d"]} for e in ranked[-3:][::-1]]
            if ranked else []
        )

        overlap_counts = {other: 0 for other in ACTIVE_COHORT_NAMES if other != cohort_name}
        for ticker in member_tickers:
            for other_cohort in membership_map.get(ticker, []):
                if other_cohort in overlap_counts:
                    overlap_counts[other_cohort] += 1

        profiles[cohort_name] = {
            "cohort": cohort_name,
            "inclusion_rule_description": cohort_summaries_all.get(cohort_name, {}).get("description"),
            "scope": "FULL_RESEARCH_UNIVERSE",
            "universe_denominator": universe_count,
            "total_member_count": total_member_count,
            "member_tickers": member_tickers,
            "trading_history_covered_count": covered_count,
            "trading_history_coverage_ratio": coverage_ratio,
            "return_distribution": _distribution_stats(returns),
            "relative_volume_distribution": _distribution_stats(rel_vols),
            "above_ma20_within_cohort": {
                "count": above_ma20,
                "denominator": total_member_count,
                "ratio": round(above_ma20 / total_member_count, 6) if total_member_count else None,
            },
            "matched_traded_value_distribution_among_covered": {
                **_distribution_stats(matched_values),
                "scope": "ACQUIRED_ENRICHMENT_COHORT",
                "denominator": covered_count,
            },
            "put_through_prevalence_among_covered": {
                "scope": "ACQUIRED_ENRICHMENT_COHORT",
                "covered_denominator": covered_count,
                "put_through_recorded_count": recorded_count,
                "no_put_through_recorded_count": none_recorded_count,
                "put_through_unknown_count": unknown_count,
                "put_through_recorded_ratio": round(recorded_count / covered_count, 6) if covered_count else None,
                "median_put_through_share_among_recorded": _distribution_stats(put_through_shares)["median"],
            },
            "other_cohort_membership_overlap": overlap_counts,
            "representative_tails": {
                "strongest_positive_return": top_positive_tail,
                "strongest_negative_return": top_negative_tail,
            },
        }

    return profiles


def build_cohort_comparison(cohort_profiles: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic cross-cohort comparisons; every cell carries its own denominator.

    Sufficiency contract (explicit, not a hidden threshold): a cell is SAMPLE_DESCRIPTIVE
    whenever its observed denominator is >= MINIMUM_DENOMINATOR_FOR_DESCRIPTIVE_COMPARISON (1);
    it is never extrapolated to the full cohort or universe. INSUFFICIENT_COVERAGE_FOR_COMPARISON
    fires only when the observed denominator is exactly 0.
    """

    def _cell(value: Any, denominator: int | None) -> dict[str, Any]:
        effective_denominator = denominator or 0
        if effective_denominator < MINIMUM_DENOMINATOR_FOR_DESCRIPTIVE_COMPARISON or value is None:
            return {
                "value": INSUFFICIENT_COVERAGE,
                "denominator": effective_denominator,
                "comparison_status": INSUFFICIENT_COVERAGE,
            }
        return {"value": value, "denominator": effective_denominator, "comparison_status": SAMPLE_DESCRIPTIVE}

    extractors: dict[str, Any] = {
        "trading_history_coverage_ratio": lambda p: (p["trading_history_coverage_ratio"], p["total_member_count"]),
        "median_relative_volume": lambda p: (
            p["relative_volume_distribution"]["median"], p["relative_volume_distribution"]["n"],
        ),
        "median_matched_traded_value_vnd_among_covered": lambda p: (
            p["matched_traded_value_distribution_among_covered"]["median"],
            p["matched_traded_value_distribution_among_covered"]["denominator"],
        ),
        "put_through_incidence_ratio_among_covered": lambda p: (
            p["put_through_prevalence_among_covered"]["put_through_recorded_ratio"],
            p["put_through_prevalence_among_covered"]["covered_denominator"],
        ),
        "above_ma20_ratio_within_cohort": lambda p: (
            p["above_ma20_within_cohort"]["ratio"], p["above_ma20_within_cohort"]["denominator"],
        ),
    }

    metrics: dict[str, Any] = {}
    for metric_name, extractor in extractors.items():
        row: dict[str, Any] = {}
        for cohort_name, profile in cohort_profiles.items():
            value, denominator = extractor(profile)
            row[cohort_name] = _cell(value, denominator)
        metrics[metric_name] = row

    return {
        "comparison_schema_version": "1.0.0",
        "comparison_contract": {
            "rule": "SAMPLE_DESCRIPTIVE_WHEN_DENOMINATOR_GTE_MINIMUM_ELSE_INSUFFICIENT_COVERAGE",
            "minimum_denominator_for_descriptive_comparison": MINIMUM_DENOMINATOR_FOR_DESCRIPTIVE_COMPARISON,
            "extrapolates_to_full_cohort_or_universe": False,
        },
        "disclaimer": (
            "Every cell exposes its own observed denominator and is labelled SAMPLE_DESCRIPTIVE or "
            f"{INSUFFICIENT_COVERAGE}; a cohort with zero observed values for a metric reports "
            f"{INSUFFICIENT_COVERAGE} rather than an extrapolated ratio."
        ),
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# 3. TRADING ACTIVITY / VALUE PROFILES
# ---------------------------------------------------------------------------

def build_trading_activity_section(capability_digest: Mapping[str, Any]) -> dict[str, Any]:
    universe_count = capability_digest["market_wide_core"]["universe_count"]
    records = capability_digest["records"]

    acquired = [r for r in records if r.get("fhsc_value_volume_composition", {}).get("status") == "ACQUIRED"]
    sample_n = len(acquired)

    raw_entries = []
    total_values: list[float] = []
    for r in acquired:
        comp = r["fhsc_value_volume_composition"]
        mv = comp.get("matched_traded_value_vnd")
        pv = comp.get("put_through_traded_value_vnd")
        total_v = (mv + pv) if (mv is not None and pv is not None) else None
        if total_v is not None:
            total_values.append(total_v)
        raw_entries.append({
            "ticker": r["ticker"],
            "matched_traded_value_vnd": mv,
            "put_through_traded_value_vnd": pv,
            "total_traded_value_vnd": total_v,
            "put_through_share_ratio": comp.get("put_through_value_ratio"),
            "relative_volume_provider_scoped": r.get("dnse_market_data", {}).get("relative_volume_provider_scoped"),
        })

    sorted_totals = sorted(total_values)
    n = len(sorted_totals)
    p25_threshold = sorted_totals[int(n * 0.25)] if n else None
    p75_threshold = sorted_totals[int(n * 0.75)] if n else None

    classified = []
    for e in raw_entries:
        labels: list[dict[str, Any]] = []
        pt_share = e["put_through_share_ratio"]

        if pt_share is not None and pt_share >= THRESHOLD_DOMINANT_PUT_THROUGH:
            labels.append({
                "label": "PUT_THROUGH_DOMINANT",
                "band_type": "ESTABLISHED_CONTRACT_THRESHOLD",
                "threshold": THRESHOLD_DOMINANT_PUT_THROUGH,
            })
        if pt_share is not None and pt_share >= THRESHOLD_SIGNIFICANT_PUT_THROUGH:
            labels.append({
                "label": "SIGNIFICANT_PUT_THROUGH_SHARE",
                "band_type": "ESTABLISHED_CONTRACT_THRESHOLD",
                "threshold": THRESHOLD_SIGNIFICANT_PUT_THROUGH,
            })

        if e["total_traded_value_vnd"] is None:
            labels.append({
                "label": "UNKNOWN",
                "band_type": "NOT_CLASSIFIABLE",
                "reason": "total_traded_value_vnd (matched + put-through) unavailable for this symbol",
            })
        else:
            if p75_threshold is not None and e["total_traded_value_vnd"] >= p75_threshold:
                labels.append({
                    "label": "HIGH_MATCHED_VALUE",
                    "band_type": "SAMPLE_RELATIVE",
                    "threshold": p75_threshold,
                    "threshold_definition": f"p75 of total_traded_value_vnd across the {n}-symbol acquired cohort",
                })
            if p25_threshold is not None and e["total_traded_value_vnd"] <= p25_threshold:
                labels.append({
                    "label": "LOW_ABSOLUTE_TRADING_ACTIVITY",
                    "band_type": "SAMPLE_RELATIVE",
                    "threshold": p25_threshold,
                    "threshold_definition": f"p25 of total_traded_value_vnd across the {n}-symbol acquired cohort",
                })

        classified.append({**e, "classifications": labels})

    classified.sort(key=lambda x: x["ticker"])

    return {
        "scope": "ACQUIRED_ENRICHMENT_COHORT",
        "universe_denominator": universe_count,
        "sample_denominator": sample_n,
        "coverage_ratio": round(sample_n / universe_count, 6) if universe_count else None,
        "sample_relative_bands": {
            "total_traded_value_p25_vnd": p25_threshold,
            "total_traded_value_p75_vnd": p75_threshold,
            "band_type": "SAMPLE_RELATIVE",
            "disclaimer": (
                "These bands describe relative position within the acquired sample only; they carry "
                "no liquidity, sizing, or market-wide traded-value authority."
            ),
        },
        "entries": classified,
    }


# ---------------------------------------------------------------------------
# 4. PUT-THROUGH DIGEST
# ---------------------------------------------------------------------------

def build_put_through_digest(
    capability_digest: Mapping[str, Any],
    membership_map: Mapping[str, list[str]],
) -> dict[str, Any]:
    universe_count = capability_digest["market_wide_core"]["universe_count"]
    records = capability_digest["records"]

    entries = []
    for r in records:
        comp = r.get("fhsc_value_volume_composition", {})
        if comp.get("status") != "ACQUIRED":
            continue
        mv = comp.get("matched_traded_value_vnd")
        pv = comp.get("put_through_traded_value_vnd")
        entries.append({
            "ticker": r["ticker"],
            "cohort_memberships": sorted(membership_map.get(r["ticker"], [])),
            "matched_traded_value_vnd": mv,
            "put_through_traded_value_vnd": pv,
            "total_traded_value_vnd": (mv + pv) if (mv is not None and pv is not None) else None,
            "put_through_share_ratio": comp.get("put_through_value_ratio"),
            "return_1d": r.get("dnse_market_data", {}).get("return_1d"),
            "relative_volume_provider_scoped": r.get("dnse_market_data", {}).get("relative_volume_provider_scoped"),
            "put_through_status": _put_through_status(pv),
        })

    entries.sort(key=lambda e: e["ticker"])
    n = len(entries)
    recorded = sum(1 for e in entries if e["put_through_status"] == PUT_THROUGH_RECORDED)
    none_recorded = sum(1 for e in entries if e["put_through_status"] == NO_PUT_THROUGH_RECORDED)
    unknown = sum(1 for e in entries if e["put_through_status"] == PUT_THROUGH_UNKNOWN)

    return {
        "scope": "ACQUIRED_ENRICHMENT_COHORT",
        "universe_denominator": universe_count,
        "sample_denominator": n,
        "prevalence": {
            "put_through_recorded_count": recorded,
            "no_put_through_recorded_count": none_recorded,
            "put_through_unknown_count": unknown,
            "put_through_recorded_ratio": round(recorded / n, 6) if n else None,
        },
        "disclaimer": (
            f"{NO_PUT_THROUGH_RECORDED} means retained provider evidence shows an exact zero "
            "put-through value for that symbol this session -- a per-symbol factual absence, not a "
            "market-wide or off-market-activity claim, and it names no actor or activity type."
        ),
        "entries": entries,
    }


# ---------------------------------------------------------------------------
# 5. CROSS-DIMENSION CASES (consumed, not recreated)
# ---------------------------------------------------------------------------

def build_cross_dimension_cases(cross_dimension_digest: Mapping[str, Any]) -> dict[str, Any]:
    targets = cross_dimension_digest["target_records"]
    coverage = cross_dimension_digest["coverage_reconciliation"]

    def _slice(t: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "ticker": t["ticker"],
            "enrichment_tier": t["enrichment_tier"],
            "acquired_capabilities": list(t["acquired_capabilities"]),
            "missing_or_failed_capabilities": dict(t["missing_or_failed_capabilities"]),
            "active_research_cohorts": list(t["active_research_cohorts"]),
            "reason_codes": list(t["reason_codes"]),
            "cross_dimension_analysis": dict(t["cross_dimension_analysis"]),
            "price_and_trend": dict(t["price_and_trend"]),
            "traded_value_composition": dict(t["traded_value_composition"]),
            "foreign_room": dict(t["foreign_room"]),
            "proprietary_flow": dict(t["proprietary_flow"]),
            "microstructure": dict(t["microstructure"]),
        }

    cases: dict[str, list[dict[str, Any]]] = {name: [] for name in CROSS_DIMENSION_CASE_NAMES}

    for t in targets:
        codes = t["reason_codes"]
        cd = t["cross_dimension_analysis"]
        sliced = _slice(t)

        if "MOMENTUM_WITH_PROP_BUY" in codes:
            cases[CASE_MOMENTUM_WITH_PROP_BUY].append(sliced)
        if "MOMENTUM_WITH_PROP_SELL" in codes:
            cases[CASE_MOMENTUM_WITH_PROP_SELL].append(sliced)
        if "REVERSAL_WITH_ACTIVE_SELLING" in codes:
            cases[CASE_REVERSAL_WITH_ACTIVE_SELLING].append(sliced)
        if "MATERIAL_ACTIVE_BUY_IMBALANCE" in codes and cd.get("price_vs_order_imbalance_alignment") == "PRICE_UP_WITH_ACTIVE_BUY_SKEW":
            cases[CASE_PRICE_UP_WITH_ACTIVE_BUY_IMBALANCE].append(sliced)
        if "PUT_THROUGH_DOMINANT" in codes:
            cases[CASE_PUT_THROUGH_DOMINANCE].append(sliced)
        if "HIGH_FOREIGN_ROOM_UTILIZATION" in codes or "FULL_FOREIGN_ROOM_SATURATION" in codes:
            cases[CASE_HIGH_FOREIGN_ROOM].append(sliced)
        if (
            cd.get("price_vs_prop_alignment") in ("PRICE_UP_WITH_PROP_NET_SELL", "PRICE_DOWN_WITH_PROP_NET_BUY")
            or cd.get("price_vs_order_imbalance_alignment") in ("PRICE_UP_WITH_ACTIVE_SELL_SKEW", "PRICE_DOWN_WITH_ACTIVE_BUY_SKEW")
        ):
            cases[CASE_EXPLICIT_DIVERGENCE].append(sliced)

    for name in cases:
        cases[name].sort(key=lambda x: x["ticker"])

    return {
        "scope": "ACQUIRED_ENRICHMENT_COHORT",
        "sample_denominator": len(targets),
        "universe_denominator": coverage["total_universe_count"],
        "source_digest_identity": cross_dimension_digest["digest_identity"],
        "disclaimer": (
            "Cases below are filtered strictly from reason codes and alignment states already computed "
            "by the cross-dimension digest; no accumulation, distribution, smart-money, retail, or causal "
            "price-driver inference is added here."
        ),
        "cases": {name: {"count": len(entries), "members": entries} for name, entries in cases.items()},
    }


# ---------------------------------------------------------------------------
# 7. RESEARCH FOLLOW-UP FLAGS
# ---------------------------------------------------------------------------

def build_follow_up_flags(
    market_state_artifact: Mapping[str, Any],
    cross_dimension_cases: Mapping[str, Any],
    trading_activity_section: Mapping[str, Any],
) -> dict[str, Any]:
    """Evidence-supported analytical observations only.

    Every flag here is anchored to an ACQUIRED, observed fact (a real cross-dimension case or a
    real trading-activity classification). Symbols merely lacking FHSC enrichment are never
    listed here one-by-one; that aggregate/bounded inventory lives in
    build_data_coverage_backlog instead.
    """
    flags: list[dict[str, Any]] = []

    for m in cross_dimension_cases["cases"][CASE_PUT_THROUGH_DOMINANCE]["members"]:
        flags.append({
            "flag_type": FLAG_PUT_THROUGH_DOMINANCE,
            "ticker": m["ticker"],
            "reason_codes": list(m["reason_codes"]),
            "facts": {
                "put_through_share_ratio": m["traded_value_composition"]["put_through_share_ratio"],
                "put_through_traded_value_vnd": m["traded_value_composition"]["put_through_traded_value_vnd"],
                "matched_traded_value_vnd": m["traded_value_composition"]["matched_traded_value_vnd"],
            },
            "missing_data_context": None,
            "research_rationale": (
                "Recorded put-through value is at least half of this symbol's total recorded traded "
                "value for the session; worth reviewing the underlying trade prints."
            ),
        })

    for m in cross_dimension_cases["cases"][CASE_EXPLICIT_DIVERGENCE]["members"]:
        flags.append({
            "flag_type": FLAG_PRICE_FLOW_DIVERGENCE,
            "ticker": m["ticker"],
            "reason_codes": list(m["reason_codes"]),
            "facts": {
                "return_1d": m["price_and_trend"]["return_1d"],
                "price_vs_prop_alignment": m["cross_dimension_analysis"]["price_vs_prop_alignment"],
                "price_vs_order_imbalance_alignment": m["cross_dimension_analysis"]["price_vs_order_imbalance_alignment"],
            },
            "missing_data_context": None,
            "research_rationale": (
                "Same-session price direction and proprietary or active-order-flow direction point "
                "opposite ways; worth reviewing what sits behind the divergence."
            ),
        })

    for e in trading_activity_section["entries"]:
        labels = {c["label"] for c in e["classifications"]}
        rel_vol = e["relative_volume_provider_scoped"]
        if "HIGH_MATCHED_VALUE" in labels and rel_vol is not None and rel_vol <= THRESHOLD_DEPRESSED_REL_VOL:
            flags.append({
                "flag_type": FLAG_LOW_REL_VOL_WITH_ACTIVITY,
                "ticker": e["ticker"],
                "reason_codes": ["HIGH_MATCHED_VALUE_SAMPLE_RELATIVE", "DEPRESSED_RELATIVE_VOLUME"],
                "facts": {
                    "total_traded_value_vnd": e["total_traded_value_vnd"],
                    "relative_volume_provider_scoped": rel_vol,
                },
                "missing_data_context": None,
                "research_rationale": (
                    "Total traded value sits in the upper quartile of the acquired sample while this "
                    "symbol's own relative-volume baseline reads depressed; worth reconciling the two readings."
                ),
            })

    hv_cohort = market_state_artifact["research_candidate_cohorts"]["cohort_entries"].get(COHORT_HIGH_VOLATILITY_WATCH, [])
    trading_entries_by_ticker = {e["ticker"]: e for e in trading_activity_section["entries"]}

    for entry in hv_cohort:
        ticker = entry["ticker"]
        te = trading_entries_by_ticker.get(ticker)
        if te is not None and any(c["label"] == "LOW_ABSOLUTE_TRADING_ACTIVITY" for c in te["classifications"]):
            flags.append({
                "flag_type": FLAG_HIGH_VOL_LOW_VALUE,
                "ticker": ticker,
                "reason_codes": ["UPPER_TAIL_20D_VOLATILITY", "LOW_ABSOLUTE_TRADING_ACTIVITY_SAMPLE_RELATIVE"],
                "facts": {
                    "volatility_20d": entry["input_metrics"].get("volatility_20d"),
                    "total_traded_value_vnd": te["total_traded_value_vnd"],
                },
                "missing_data_context": None,
                "research_rationale": (
                    "Realized volatility sits in the upper tail of the full universe while acquired "
                    "traded value sits in the lower quartile of the enrichment sample; worth checking "
                    "whether the move was thinly traded."
                ),
            })

    flags.sort(key=lambda f: (f["flag_type"], f["ticker"]))

    return {
        "authority_disclaimer": FOLLOW_UP_FLAGS_DISCLAIMER,
        "scope": "EVIDENCE_SUPPORTED_OBSERVATIONS_ONLY_NOT_A_COVERAGE_BACKLOG",
        "flag_count": len(flags),
        "flag_counts_by_type": {
            flag_type: sum(1 for f in flags if f["flag_type"] == flag_type)
            for flag_type in (
                FLAG_PUT_THROUGH_DOMINANCE, FLAG_PRICE_FLOW_DIVERGENCE, FLAG_LOW_REL_VOL_WITH_ACTIVITY,
                FLAG_HIGH_VOL_LOW_VALUE,
            )
        },
        "flags": flags,
    }


# ---------------------------------------------------------------------------
# Data coverage backlog: separate, bounded, descriptive-only. Never a priority queue.
# ---------------------------------------------------------------------------

def build_data_coverage_backlog(
    market_state_artifact: Mapping[str, Any],
    record_map: Mapping[str, Mapping[str, Any]],
    capability_digest: Mapping[str, Any],
) -> dict[str, Any]:
    """Aggregate, non-actionable coverage-gap facts, kept separate from analytical follow-up flags.

    This section describes what FHSC trading-history evidence is missing for the active research
    cohorts; it never recommends acquiring it, ranks symbols by acquisition priority, or implies a
    next-wave authorization. Any bounded examples are illustrative only. The exact upstream
    acquisition-status string for every example is preserved verbatim -- never normalized into a
    generic "missing" label -- alongside an optional coarse status_group for quick scanning.
    """
    decomp = capability_digest["coverage_summary"]["trading_history_scaleout_decomposition"]
    universe_count = capability_digest["market_wide_core"]["universe_count"]

    by_cohort: dict[str, dict[str, int]] = {}
    gap_records_by_ticker: dict[str, dict[str, Any]] = {}

    for cohort_name in ACTIVE_COHORT_NAMES:
        entries = market_state_artifact["research_candidate_cohorts"]["cohort_entries"].get(cohort_name, [])
        gap_count = 0
        for entry in entries:
            ticker = entry["ticker"]
            status = record_map.get(ticker, {}).get("fhsc_value_volume_composition", {}).get("status")
            if status != "ACQUIRED":
                gap_count += 1
                existing = gap_records_by_ticker.get(ticker)
                if existing is None:
                    gap_records_by_ticker[ticker] = {
                        "ticker": ticker,
                        "active_research_cohorts": [cohort_name],
                        "exact_upstream_status": status,
                        "status_group": _normalize_status_group(status),
                    }
                else:
                    existing["active_research_cohorts"].append(cohort_name)
        by_cohort[cohort_name] = {
            "cohort_total_members": len(entries),
            "members_lacking_fhsc_trading_history": gap_count,
        }

    gap_records = sorted(gap_records_by_ticker.values(), key=lambda r: r["ticker"])
    for r in gap_records:
        r["active_research_cohorts"] = sorted(r["active_research_cohorts"])

    bounded_examples = [
        {**r, "label": COVERAGE_GAP_EXAMPLE_LABEL, "note": "Illustrative only; not a priority ranking or acquisition recommendation."}
        for r in gap_records[:MAX_COVERAGE_GAP_EXAMPLES]
    ]

    return {
        "disclaimer": DATA_COVERAGE_BACKLOG_DISCLAIMER,
        "scope": "ACTIVE_RESEARCH_COHORTS_WITHIN_FULL_RESEARCH_UNIVERSE",
        "universe_denominator": universe_count,
        "acquisition_status_counts": {
            "ACQUIRED_TRADING_HISTORY_COHORT": decomp["acquired_count"],
            "PROVIDER_RATE_LIMITED": decomp["rate_limited_count"],
            "REQUESTED_BUT_MISSING": decomp["missing_requested_session_count"],
            "BUDGET_EXHAUSTED": decomp["budget_exhausted_count"],
            "NOT_ACQUIRED_IN_THIS_SCALEOUT": decomp["unattempted_count"],
        },
        "active_cohort_members_lacking_fhsc_trading_history": {
            "total_distinct_symbols": len(gap_records),
            "by_cohort": by_cohort,
        },
        "coverage_gap_examples": {
            "max_examples": MAX_COVERAGE_GAP_EXAMPLES,
            "returned_count": len(bounded_examples),
            "total_available_count": len(gap_records),
            "examples": bounded_examples,
        },
    }


# ---------------------------------------------------------------------------
# 8. COVERAGE / DATA QUALITY
# ---------------------------------------------------------------------------

def build_coverage_and_data_quality(
    capability_digest: Mapping[str, Any],
    cross_dimension_digest: Mapping[str, Any],
) -> dict[str, Any]:
    decomp = capability_digest["coverage_summary"]["trading_history_scaleout_decomposition"]
    cross_rec = cross_dimension_digest["coverage_reconciliation"]

    return {
        "tiers": {
            "FULL_RESEARCH_UNIVERSE": decomp["total_universe_count"],
            "ACQUIRED_TRADING_HISTORY_COHORT": decomp["acquired_count"],
            "FULLY_ENRICHED_COHORT": cross_rec["fully_enriched_count"],
            "PARTIALLY_ENRICHED": cross_rec["partially_enriched_count"],
            "TRADING_HISTORY_ONLY": cross_rec["trading_history_only_count"],
            "PROVIDER_RATE_LIMITED": decomp["rate_limited_count"],
            "REQUESTED_BUT_MISSING": decomp["missing_requested_session_count"],
            "BUDGET_EXHAUSTED": decomp["budget_exhausted_count"],
            "NOT_ACQUIRED_IN_THIS_SCALEOUT": decomp["unattempted_count"],
        },
        "reconciliation": {
            "capability_digest_reconciled_sum": decomp["reconciled_sum"],
            "capability_digest_reconciliation_valid": decomp["reconciliation_valid"],
            "cross_dimension_reconciled_sum": cross_rec["reconciled_sum"],
            "cross_dimension_reconciliation_valid": cross_rec["reconciliation_valid"],
        },
        "disclaimer": (
            "NOT_ACQUIRED_IN_THIS_SCALEOUT (genuinely unattempted) is never collapsed into "
            "REQUESTED_BUT_MISSING or PROVIDER_RATE_LIMITED (both attempted-but-blocked); every tier "
            "above is mutually exclusive and the tiers sum to the full research universe."
        ),
    }


def build_narrative_scope_notes(
    market_state_section: Mapping[str, Any],
    trading_activity_section: Mapping[str, Any],
    put_through_section: Mapping[str, Any],
    cross_dimension_section: Mapping[str, Any],
    cohort_comparison: Mapping[str, Any],
) -> list[str]:
    """Deterministic plain-English scope notes so the digest never presents a sample as market-wide."""
    notes: list[str] = []
    uc = market_state_section["universe_count"]
    notes.append(
        f"Market state, breadth, and return/volatility distributions cover the FULL_RESEARCH_UNIVERSE: "
        f"{uc}/{uc} symbols (100% DNSE coverage)."
    )
    ta = trading_activity_section
    notes.append(
        f"Trading-activity value/put-through classifications cover only the ACQUIRED_ENRICHMENT_COHORT "
        f"sample: {ta['sample_denominator']}/{ta['universe_denominator']} symbols "
        f"({(ta['coverage_ratio'] or 0) * 100:.1f}% of universe); they are not market-wide statistics."
    )
    pt = put_through_section
    notes.append(
        f"Put-through digest covers the same acquired sample: {pt['sample_denominator']}/{pt['universe_denominator']} "
        "symbols; a NO_PUT_THROUGH_RECORDED entry is a per-symbol fact, never a market-wide claim."
    )
    cd = cross_dimension_section
    cd_ratio = (cd["sample_denominator"] / cd["universe_denominator"]) if cd["universe_denominator"] else 0.0
    notes.append(
        f"Cross-dimension multi-endpoint cases cover a smaller sample still: "
        f"{cd['sample_denominator']}/{cd['universe_denominator']} symbols ({cd_ratio * 100:.2f}% of universe)."
    )
    corroborating = (
        cd["cases"][CASE_MOMENTUM_WITH_PROP_BUY]["count"] + cd["cases"][CASE_MOMENTUM_WITH_PROP_SELL]["count"]
    )
    divergent = cd["cases"][CASE_EXPLICIT_DIVERGENCE]["count"]
    notes.append(
        f"{corroborating} cross-dimension case(s) show cohort trend and proprietary flow direction agreeing "
        f"(corroborating); {divergent} case(s) show price direction and flow direction disagreeing (divergent)."
    )
    insufficient = sum(
        1 for row in cohort_comparison["metrics"].values() for cell in row.values()
        if cell["value"] == INSUFFICIENT_COVERAGE
    )
    if insufficient:
        notes.append(
            f"{insufficient} cohort-comparison cell(s) reported {INSUFFICIENT_COVERAGE} rather than an "
            "extrapolated figure, because the covered denominator was zero for that cohort/metric pair."
        )
    else:
        notes.append("Every cohort-comparison cell this session had a non-zero covered denominator.")
    return notes


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

def build_research_intelligence_digest(
    capability_digest: Mapping[str, Any],
    market_state_artifact: Mapping[str, Any],
    cross_dimension_digest: Mapping[str, Any],
) -> dict[str, Any]:
    validate_identity_chain(capability_digest, market_state_artifact, cross_dimension_digest)

    session_date = capability_digest["session_date"]
    record_map = _build_capability_record_map(capability_digest)
    membership_map = _build_cohort_membership_map(market_state_artifact)

    market_state_section = build_market_state_section(market_state_artifact)
    cohort_profiles = build_cohort_profiles(market_state_artifact, record_map, membership_map)
    cohort_comparison = build_cohort_comparison(cohort_profiles)
    trading_activity_section = build_trading_activity_section(capability_digest)
    put_through_section = build_put_through_digest(capability_digest, membership_map)
    cross_dimension_section = build_cross_dimension_cases(cross_dimension_digest)
    follow_up_flags = build_follow_up_flags(
        market_state_artifact, cross_dimension_section, trading_activity_section,
    )
    data_coverage_backlog = build_data_coverage_backlog(market_state_artifact, record_map, capability_digest)
    coverage_section = build_coverage_and_data_quality(capability_digest, cross_dimension_digest)
    narrative_scope_notes = build_narrative_scope_notes(
        market_state_section, trading_activity_section, put_through_section,
        cross_dimension_section, cohort_comparison,
    )

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "session_date": session_date,
        "execution_timestamp": datetime.now(UTC).isoformat(),
        "source_artifacts": {
            "capability_research_digest_identity": capability_digest["digest_identity"],
            "market_state_and_candidates_identity": market_state_artifact["artifact_identity"],
            "cross_dimension_research_digest_identity": cross_dimension_digest["digest_identity"],
        },
        "market_state": market_state_section,
        "cohort_profiles": cohort_profiles,
        "cohort_comparison": cohort_comparison,
        "trading_activity": trading_activity_section,
        "put_through_digest": put_through_section,
        "cross_dimension_cases": cross_dimension_section,
        "follow_up_flags": follow_up_flags,
        "data_coverage_backlog": data_coverage_backlog,
        "coverage_and_data_quality": coverage_section,
        "narrative_scope_notes": narrative_scope_notes,
        "authority_boundaries": AUTHORITY_BOUNDARIES,
    }

    digest_sha256 = _sha256_json({
        k: v for k, v in artifact.items()
        if k not in {"digest_sha256", "digest_identity", "execution_timestamp"}
    })
    artifact["digest_sha256"] = digest_sha256
    artifact["digest_identity"] = f"research_intelligence_digest_v1:{digest_sha256}"

    return artifact


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def generate_research_intelligence_markdown_summary(artifact: Mapping[str, Any]) -> str:
    session = artifact["session_date"]
    ms = artifact["market_state"]
    regime = ms["regime_classification"]
    breadth = ms["breadth"]
    ma_breadth = ms["moving_average_breadth"]
    cohort_profiles = artifact["cohort_profiles"]
    comparison = artifact["cohort_comparison"]["metrics"]
    ta = artifact["trading_activity"]
    pt = artifact["put_through_digest"]
    cd = artifact["cross_dimension_cases"]
    flags = artifact["follow_up_flags"]
    backlog = artifact["data_coverage_backlog"]
    cov = artifact["coverage_and_data_quality"]
    notes = artifact["narrative_scope_notes"]

    md: list[str] = [
        f"# Research Intelligence Digest V1 — Session {session}",
        "",
        f"- **Digest Identity**: `{artifact['digest_identity']}`",
        f"- **Contract Version**: `{artifact['contract_version']}`",
        f"- **Source Capability Digest**: `{artifact['source_artifacts']['capability_research_digest_identity']}`",
        f"- **Source Market State**: `{artifact['source_artifacts']['market_state_and_candidates_identity']}`",
        f"- **Source Cross-Dimension Digest**: `{artifact['source_artifacts']['cross_dimension_research_digest_identity']}`",
        f"- **Authority**: `{AUTHORITY_DISCLAIMER}`",
        "",
        "---",
        "",
        "## MARKET STATE",
        "",
        f"> **Descriptive Regime**: `{regime['regime_label']}` — {regime['derivation_reason']}",
        "",
        f"- Universe analyzed: `{ms['universe_count']}/{ms['universe_count']}` (100% DNSE coverage)",
        f"- Advancers `{breadth['advancers_count']}` / Decliners `{breadth['decliners_count']}` / Unchanged `{breadth['unchanged_count']}` (A/D ratio `{breadth['advance_decline_ratio']}`)",
        f"- Above 20D MA: `{ma_breadth['above_ma20_count']}/{ms['universe_count']}` ({ma_breadth['above_ma20_ratio'] * 100:.1f}%)",
        f"- 1D return: mean `{ms['return_distribution']['mean_return_1d'] * 100:+.2f}%`, median `{ms['return_distribution']['median_return_1d'] * 100:+.2f}%`",
        f"- 20D volatility: median `{ms['volatility_distribution']['median_volatility_20d']:.4f}`",
        "",
        "---",
        "",
        "## WHAT IS BROADLY HAPPENING",
        "",
    ]
    md.extend(f"- {n}" for n in notes)
    md.extend([
        "",
        "---",
        "",
        "## ACTIVE RESEARCH COHORTS",
        "",
        "### Cohort Profiles",
        "",
        "| Cohort | Members | FHSC Covered | Coverage % | Median Return | Median Rel Vol | Median Matched Value (VND, covered) | PT Recorded % (covered) |",
        "|:---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for name, p in cohort_profiles.items():
        cov_pct = f"{p['trading_history_coverage_ratio'] * 100:.1f}%" if p["trading_history_coverage_ratio"] is not None else "N/A"
        med_ret = p["return_distribution"]["median"]
        med_ret_s = f"{med_ret * 100:+.2f}%" if med_ret is not None else "N/A"
        med_rv = p["relative_volume_distribution"]["median"]
        med_rv_s = f"{med_rv:.2f}x" if med_rv is not None else "N/A"
        med_mv = p["matched_traded_value_distribution_among_covered"]["median"]
        med_mv_s = f"{med_mv:,.0f}" if med_mv is not None else "N/A"
        pt_ratio = p["put_through_prevalence_among_covered"]["put_through_recorded_ratio"]
        pt_ratio_s = f"{pt_ratio * 100:.1f}%" if pt_ratio is not None else "N/A"
        md.append(f"| **{name}** | {p['total_member_count']} | {p['trading_history_covered_count']} | {cov_pct} | {med_ret_s} | {med_rv_s} | {med_mv_s} | {pt_ratio_s} |")

    contract = artifact["cohort_comparison"]["comparison_contract"]
    md.extend([
        "",
        "### Cohort Comparison (every cell exposes its own denominator)",
        "",
        f"> Comparison contract: `{contract['rule']}` -- minimum denominator = "
        f"`{contract['minimum_denominator_for_descriptive_comparison']}`; never extrapolated to the "
        "full cohort or universe.",
        "",
        "| Metric | " + " | ".join(cohort_profiles.keys()) + " |",
        "|:---|" + "---:|" * len(cohort_profiles),
    ])
    for metric_name, row in comparison.items():
        cells = []
        for name in cohort_profiles:
            cell = row[name]
            if cell["value"] == INSUFFICIENT_COVERAGE:
                cells.append(f"`{INSUFFICIENT_COVERAGE}` (n={cell['denominator']})")
            elif isinstance(cell["value"], float) and abs(cell["value"]) >= 1000:
                cells.append(f"{cell['value']:,.0f} (n={cell['denominator']})")
            elif isinstance(cell["value"], float):
                cells.append(f"{cell['value']:.4f} (n={cell['denominator']})")
            else:
                cells.append(f"{cell['value']} (n={cell['denominator']})")
        md.append(f"| {metric_name} | " + " | ".join(cells) + " |")

    md.extend([
        "",
        "---",
        "",
        "## TRADING ACTIVITY",
        "",
        f"> Scope: `{ta['scope']}` — {ta['sample_denominator']}/{ta['universe_denominator']} symbols ({(ta['coverage_ratio'] or 0) * 100:.2f}% of universe). "
        f"SAMPLE_RELATIVE bands: p25=`{ta['sample_relative_bands']['total_traded_value_p25_vnd']:,.0f} VND`, "
        f"p75=`{ta['sample_relative_bands']['total_traded_value_p75_vnd']:,.0f} VND`.",
        "",
        "| Ticker | Matched (VND) | Put-Through (VND) | PT Share | Rel Vol | Classifications |",
        "|:---|---:|---:|---:|---:|:---|",
    ])
    for e in ta["entries"][:20]:
        mv_s = f"{e['matched_traded_value_vnd']:,.0f}" if e["matched_traded_value_vnd"] is not None else "N/A"
        pv_s = f"{e['put_through_traded_value_vnd']:,.0f}" if e["put_through_traded_value_vnd"] is not None else "N/A"
        pt_s = f"{e['put_through_share_ratio'] * 100:.1f}%" if e["put_through_share_ratio"] is not None else "N/A"
        rv_s = f"{e['relative_volume_provider_scoped']:.2f}x" if e["relative_volume_provider_scoped"] is not None else "N/A"
        labels_s = ", ".join(c["label"] for c in e["classifications"]) or "NONE"
        md.append(f"| **{e['ticker']}** | {mv_s} | {pv_s} | {pt_s} | {rv_s} | {labels_s} |")
    if len(ta["entries"]) > 20:
        md.append(f"| ... *({len(ta['entries']) - 20} additional acquired symbols omitted)* | | | | | |")

    md.extend([
        "",
        "---",
        "",
        "## PUT-THROUGH WATCH",
        "",
        f"> Scope: `{pt['scope']}` — {pt['sample_denominator']}/{artifact['market_state']['universe_count']} symbols. "
        f"Recorded: `{pt['prevalence']['put_through_recorded_count']}`, "
        f"None recorded: `{pt['prevalence']['no_put_through_recorded_count']}`, "
        f"Unknown: `{pt['prevalence']['put_through_unknown_count']}`.",
        "",
        f"*{pt['disclaimer']}*",
        "",
        "| Ticker | Cohorts | PT Share | PT Value (VND) | Status |",
        "|:---|:---|---:|---:|:---|",
    ])
    notable_pt = sorted(
        (e for e in pt["entries"] if e["put_through_status"] == PUT_THROUGH_RECORDED),
        key=lambda e: e["put_through_share_ratio"] or 0.0, reverse=True,
    )
    for e in notable_pt[:15]:
        cohorts_s = ", ".join(e["cohort_memberships"]) or "NONE"
        pt_s = f"{e['put_through_share_ratio'] * 100:.1f}%" if e["put_through_share_ratio"] is not None else "N/A"
        pv_s = f"{e['put_through_traded_value_vnd']:,.0f}" if e["put_through_traded_value_vnd"] is not None else "N/A"
        md.append(f"| **{e['ticker']}** | {cohorts_s} | {pt_s} | {pv_s} | `{e['put_through_status']}` |")

    md.extend([
        "",
        "---",
        "",
        "## CROSS-DIMENSION CASES",
        "",
        f"> Scope: `{cd['scope']}` — {cd['sample_denominator']}/{cd['universe_denominator']} symbols. {cd['disclaimer']}",
        "",
        "| Case | Count |",
        "|:---|---:|",
    ])
    for name in CROSS_DIMENSION_CASE_NAMES:
        md.append(f"| `{name}` | {cd['cases'][name]['count']} |")

    md.extend([
        "",
        "---",
        "",
        "## QUESTIONS WORTH INVESTIGATING",
        "",
        f"> {FOLLOW_UP_FLAGS_DISCLAIMER}",
        "",
        "| Flag Type | Count |",
        "|:---|---:|",
    ])
    for flag_type, count in flags["flag_counts_by_type"].items():
        md.append(f"| `{flag_type}` | {count} |")
    md.extend(["", "| Ticker | Flag Type | Reason Codes | Rationale |", "|:---|:---|:---|:---|"])
    for f in flags["flags"][:25]:
        codes_s = "; ".join(f["reason_codes"])
        md.append(f"| **{f['ticker']}** | `{f['flag_type']}` | {codes_s} | {f['research_rationale']} |")
    if len(flags["flags"]) > 25:
        md.append(f"| ... *({len(flags['flags']) - 25} additional flags omitted; see JSON artifact)* | | | |")

    md.extend([
        "",
        "---",
        "",
        "## DATA QUALITY / COVERAGE",
        "",
        "| Tier | Count |",
        "|:---|---:|",
    ])
    for tier_name, count in cov["tiers"].items():
        md.append(f"| `{tier_name}` | {count} |")
    md.append("")
    md.append(f"*{cov['disclaimer']}*")

    gap_by_cohort = backlog["active_cohort_members_lacking_fhsc_trading_history"]["by_cohort"]
    examples = backlog["coverage_gap_examples"]
    md.extend([
        "",
        f"### Data Coverage Backlog ({backlog['active_cohort_members_lacking_fhsc_trading_history']['total_distinct_symbols']} active-cohort symbols lacking FHSC trading-history)",
        "",
        f"> {backlog['disclaimer']}",
        "",
        "| Cohort | Total Members | Lacking FHSC Trading-History |",
        "|:---|---:|---:|",
    ])
    for cohort_name, counts in gap_by_cohort.items():
        md.append(f"| {cohort_name} | {counts['cohort_total_members']} | {counts['members_lacking_fhsc_trading_history']} |")
    md.extend([
        "",
        f"Showing `{examples['returned_count']}` of `{examples['total_available_count']}` total (max `{examples['max_examples']}` examples; illustrative only, not a priority order):",
        "",
        "| Ticker | Exact Upstream Status | Status Group | Cohorts |",
        "|:---|:---|:---|:---|",
    ])
    for ex in examples["examples"]:
        cohorts_s = ", ".join(ex["active_research_cohorts"])
        md.append(f"| **{ex['ticker']}** | `{ex['exact_upstream_status']}` | `{ex['status_group']}` | {cohorts_s} |")

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
        description="Build the deterministic Research Intelligence Digest V1 from three retained artifacts."
    )
    parser.add_argument(
        "--capability-digest-path",
        default="operations-review/capability-first-research-digest-2026-08-21/capability_research_digest.json",
    )
    parser.add_argument(
        "--market-state-path",
        default="operations-review/market-state-and-candidates-2026-08-21/market_state_and_candidates.json",
    )
    parser.add_argument(
        "--cross-dimension-path",
        default="operations-review/cross-dimension-research-digest-2026-08-21/cross_dimension_research_digest.json",
    )
    parser.add_argument(
        "--out-dir",
        default="operations-review/research-intelligence-digest-2026-08-21",
    )
    args = parser.parse_args(argv)

    def _resolve(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else ROOT / path

    capability_digest_path = _resolve(args.capability_digest_path)
    market_state_path = _resolve(args.market_state_path)
    cross_dimension_path = _resolve(args.cross_dimension_path)
    out_dir = _resolve(args.out_dir)

    print(f"Loading capability research digest from: {capability_digest_path}")
    capability_digest = json.loads(capability_digest_path.read_text(encoding="utf-8"))

    print(f"Loading market state & candidates from: {market_state_path}")
    market_state_artifact = json.loads(market_state_path.read_text(encoding="utf-8"))

    print(f"Loading cross-dimension research digest from: {cross_dimension_path}")
    cross_dimension_digest = json.loads(cross_dimension_path.read_text(encoding="utf-8"))

    print("Building research intelligence digest...")
    artifact = build_research_intelligence_digest(capability_digest, market_state_artifact, cross_dimension_digest)

    summary_md = generate_research_intelligence_markdown_summary(artifact)

    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / "research_intelligence_digest_v1.json"
    summary_path = out_dir / "research_intelligence_digest_v1_summary.md"
    manifest_path = out_dir / "manifest.json"

    atomic_write_json(artifact_path, artifact)
    atomic_write_file(summary_path, summary_md)

    manifest = {
        "manifest_schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "session_date": artifact["session_date"],
        "created_at": datetime.now(UTC).isoformat(),
        "digest_identity": artifact["digest_identity"],
        "digest_sha256": artifact["digest_sha256"],
        "source_artifacts": artifact["source_artifacts"],
        "files": {
            "research_intelligence_digest_v1.json": {
                "size_bytes": artifact_path.stat().st_size,
                "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            },
            "research_intelligence_digest_v1_summary.md": {
                "size_bytes": summary_path.stat().st_size,
                "sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
            },
        },
        "authority_boundaries": AUTHORITY_BOUNDARIES,
    }
    atomic_write_json(manifest_path, manifest)

    print(json.dumps({
        "status": "RESEARCH_INTELLIGENCE_DIGEST_COMPLETE",
        "digest_identity": artifact["digest_identity"],
        "session_date": artifact["session_date"],
        "coverage_tiers": artifact["coverage_and_data_quality"]["tiers"],
        "follow_up_flag_count": artifact["follow_up_flags"]["flag_count"],
        "follow_up_flag_counts_by_type": artifact["follow_up_flags"]["flag_counts_by_type"],
        "data_coverage_backlog_total_distinct_symbols": (
            artifact["data_coverage_backlog"]["active_cohort_members_lacking_fhsc_trading_history"]["total_distinct_symbols"]
        ),
        "data_coverage_backlog_examples_returned": artifact["data_coverage_backlog"]["coverage_gap_examples"]["returned_count"],
        "out_dir": str(out_dir),
    }, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    sys.exit(main())
