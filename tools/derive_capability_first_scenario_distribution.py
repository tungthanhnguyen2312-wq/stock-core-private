"""tools/derive_capability_first_scenario_distribution.py — Capability-First Scenario Distribution V1.

The first deterministic Bear/Base/Bull scenario engine over the capability-first research
foundation. Consumes exactly one retained artifact -- research_intelligence_digest_v1.json --
and reorganizes its own `cross_dimension_cases`, `cohort_profiles`, and `market_state` sections
into per-symbol scenario records. It does not recompute reason codes, cohort membership, or
market breadth: those remain the sole authority of the digest and its own upstream producers.

Scenario-eligible cohort: `research_intelligence_digest_v1.cross_dimension_cases.sample_denominator`
reports the full count of fully/partially-enriched symbols evaluated upstream, but the digest only
*exposes* a structured per-symbol evidence bundle (price/trend, traded-value composition, foreign
room, proprietary flow, microstructure) for symbols that matched at least one retained cross-dimension
case bucket. This tool produces a scenario only for that surfaced subset; any enriched symbol absent
from every case bucket is explicitly counted and reported as unsurfaced -- never silently dropped,
never backfilled from a different digest section, and never confused with the full research universe.

Authority boundary (identical in kind to every capability-first producer in this repository):
- authority_effect: "NONE"
- raw_as_traded_promoted / pit_backtest_eligible / valuation_authority / recommendation_authority /
  ranking_authority / database_mutated: False (liquidity_sizing_authority: "BLOCKED")
- probability_authority / target_price_authority / expected_return_authority: False

Bear/Base/Bull are conditional evidence records, never probabilities, target prices, expected
returns, or recommendations (docs/scenario_analysis_contract.md). Every authored claim carries
exactly one of four classifications -- FACT, DATA_WARNING, INFERENCE, HYPOTHESIS -- and one class
is never silently turned into another.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_json

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "capability_first_scenario_distribution/v1"

FACT = "FACT"
DATA_WARNING = "DATA_WARNING"
INFERENCE = "INFERENCE"
HYPOTHESIS = "HYPOTHESIS"
CLASSIFICATIONS = (FACT, DATA_WARNING, INFERENCE, HYPOTHESIS)

BULLISH = "BULLISH"
BEARISH = "BEARISH"
NEUTRAL = "NEUTRAL"
UNKNOWN = "UNKNOWN"

AXIS_TREND = "trend"
AXIS_PROP_FLOW = "proprietary_flow"
AXIS_ORDER_IMBALANCE = "order_imbalance"
AXIS_PUT_THROUGH = "put_through_composition"
AXIS_FOREIGN_ROOM = "foreign_room"
DIRECTIONAL_AXIS_NAMES = (AXIS_TREND, AXIS_PROP_FLOW, AXIS_ORDER_IMBALANCE)

UNSURFACED_IDENTITIES_LABEL = "NOT_EXPOSED_BY_RESEARCH_INTELLIGENCE_DIGEST_V1_CROSS_DIMENSION_CASES"

AUTHORITY_BOUNDARIES = {
    "authority_effect": "NONE",
    "raw_as_traded_promoted": False,
    "pit_backtest_eligible": False,
    "liquidity_sizing_authority": "BLOCKED",
    "valuation_authority": False,
    "recommendation_authority": False,
    "ranking_authority": False,
    "database_mutated": False,
    "probability_authority": False,
    "target_price_authority": False,
    "expected_return_authority": False,
}

TICKER_AUTHORITY_BOUNDARY = {
    "probabilities": "UNQUALIFIED",
    "targets_expected_returns_recommendations": "NOT_EMITTED",
    "ranking_or_sizing": "NOT_EMITTED",
    "ai_may_not_add_evidence_or_resolve_gaps": True,
}

_REQUIRED_TOP_LEVEL_KEYS = (
    "schema_version", "contract_version", "session_date", "digest_identity", "digest_sha256",
    "market_state", "cohort_profiles", "cross_dimension_cases", "coverage_and_data_quality",
    "authority_boundaries", "source_artifacts",
)


class DigestIdentityError(ValueError):
    """Raised when research_intelligence_digest_v1 fails self-consistency or identity validation."""


# ---------------------------------------------------------------------------
# Canonicalization (byte-identical to tools/derive_research_intelligence_digest.py)
# ---------------------------------------------------------------------------

def _canonical_json(val: Any) -> str:
    return json.dumps(val, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_json(val: Any) -> str:
    return hashlib.sha256(_canonical_json(val).encode("utf-8")).hexdigest()


def _fmt_num(x: float | None, digits: int = 0) -> str:
    return f"{x:,.{digits}f}" if x is not None else "UNKNOWN"


def _fmt_vnd(x: float | None) -> str:
    return f"{_fmt_num(x)} VND" if x is not None else "UNKNOWN"


def _fmt_pct(x: float | None) -> str:
    """Signed percentage, for values that can be negative (e.g. return_1d)."""
    return f"{x * 100:+.2f}%" if x is not None else "UNKNOWN"


def _fmt_pct_abs(x: float | None) -> str:
    """Unsigned percentage, for non-negative ratios (e.g. put-through share, foreign-room utilization)."""
    return f"{x * 100:.2f}%" if x is not None else "UNKNOWN"


def _fmt_ratio(x: float | None) -> str:
    return f"{x:.4f}" if x is not None else "UNKNOWN"


# ---------------------------------------------------------------------------
# Fail-closed input validation
# ---------------------------------------------------------------------------

def validate_digest_identity(digest: Mapping[str, Any]) -> None:
    """Fail closed if the loaded digest is incomplete, tampered, or internally inconsistent.

    Recomputes the digest's own content hash using the exact algorithm its producer used, so a
    hand-edited or corrupted file is refused rather than silently trusted. Also reconciles two
    pairs of fields that must agree within one digest (universe denominator; enriched-cohort
    denominator) so this tool never builds scenarios from a self-contradictory artifact.
    """
    if not isinstance(digest, Mapping):
        raise DigestIdentityError("research_intelligence_digest_v1 input is not a JSON object.")

    missing = [k for k in _REQUIRED_TOP_LEVEL_KEYS if k not in digest]
    if missing:
        raise DigestIdentityError(f"research_intelligence_digest_v1 is missing required key(s): {missing}")

    recomputed_sha = _sha256_json({
        k: v for k, v in digest.items() if k not in {"digest_sha256", "digest_identity", "execution_timestamp"}
    })
    if recomputed_sha != digest["digest_sha256"]:
        raise DigestIdentityError(
            "research_intelligence_digest_v1['digest_sha256'] does not match its own recomputed content "
            "hash; refusing to build scenarios from a corrupted, hand-edited, or tampered input."
        )
    expected_identity = f"research_intelligence_digest_v1:{recomputed_sha}"
    if digest["digest_identity"] != expected_identity:
        raise DigestIdentityError(
            f"research_intelligence_digest_v1['digest_identity'] ({digest['digest_identity']!r}) does not "
            f"match its own digest_sha256 ({expected_identity!r})."
        )

    cd = digest["cross_dimension_cases"]
    ms = digest["market_state"]
    cov = digest["coverage_and_data_quality"].get("tiers", {})

    if cd.get("universe_denominator") != ms.get("universe_count"):
        raise DigestIdentityError(
            "cross_dimension_cases.universe_denominator does not match market_state.universe_count "
            "within the same research_intelligence_digest_v1 artifact."
        )
    expected_enriched = (cov.get("FULLY_ENRICHED_COHORT") or 0) + (cov.get("PARTIALLY_ENRICHED") or 0)
    if cd.get("sample_denominator") != expected_enriched:
        raise DigestIdentityError(
            "cross_dimension_cases.sample_denominator does not reconcile against "
            "coverage_and_data_quality.tiers (FULLY_ENRICHED_COHORT + PARTIALLY_ENRICHED)."
        )


def _collect_cross_dimension_members(digest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Union every case-bucket's members by ticker; fail closed if buckets disagree on a record."""
    cases = digest["cross_dimension_cases"]["cases"]
    by_ticker: dict[str, dict[str, Any]] = {}
    for case_name in sorted(cases):
        for member in cases[case_name]["members"]:
            ticker = member["ticker"]
            if ticker in by_ticker:
                if by_ticker[ticker]["record"] != member:
                    raise DigestIdentityError(
                        f"cross_dimension_cases carries two different evidence records for ticker "
                        f"{ticker!r} across case buckets within the same digest; refusing to pick one "
                        "arbitrarily."
                    )
                by_ticker[ticker]["matched_case_types"].append(case_name)
            else:
                by_ticker[ticker] = {"record": member, "matched_case_types": [case_name]}
    for entry in by_ticker.values():
        entry["matched_case_types"] = sorted(entry["matched_case_types"])
    return by_ticker


# ---------------------------------------------------------------------------
# Per-symbol evidence axes -- each strictly re-expresses an already-retained field/reason code.
# ---------------------------------------------------------------------------

def _trend_axis(ticker: str, price_and_trend: Mapping[str, Any]) -> dict[str, Any]:
    ref = f"cross_dimension_cases[ticker={ticker}].price_and_trend"
    above = price_and_trend.get("above_ma20")
    close, ma20, ret = price_and_trend.get("close_vnd"), price_and_trend.get("ma_20_vnd"), price_and_trend.get("return_1d")
    if above is None or close is None or ma20 is None:
        return {"axis": "TREND", "direction": UNKNOWN, "classification": DATA_WARNING,
                "claim": f"{ticker}: trend evidence (close and/or 20-day moving average) is incomplete in retained price_and_trend.",
                "evidence_reference": ref}
    direction = BULLISH if above else BEARISH
    claim = (f"{ticker} close {_fmt_vnd(close)} is {'above' if above else 'at or below'} its 20-day moving "
             f"average {_fmt_vnd(ma20)} (1D return {_fmt_pct(ret)}).")
    return {"axis": "TREND", "direction": direction, "classification": FACT, "claim": claim, "evidence_reference": ref}


def _proprietary_flow_axis(ticker: str, proprietary_flow: Mapping[str, Any], reason_codes: Sequence[str]) -> dict[str, Any]:
    ref = f"cross_dimension_cases[ticker={ticker}].proprietary_flow"
    status = proprietary_flow.get("status")
    if status != "ACQUIRED":
        return {"axis": "PROPRIETARY_FLOW", "direction": UNKNOWN, "classification": DATA_WARNING,
                "claim": f"{ticker}: proprietary-flow capability status is {status!r}, not ACQUIRED.",
                "evidence_reference": ref}
    buy_vol, sell_vol = proprietary_flow.get("buy_volume"), proprietary_flow.get("sell_volume")
    if "NO_PROPRIETARY_TRADING_ACTIVITY" in reason_codes or (buy_vol == 0 and sell_vol == 0):
        return {"axis": "PROPRIETARY_FLOW", "direction": NEUTRAL, "classification": FACT,
                "claim": f"{ticker}: no proprietary trading activity is recorded this session (buy and sell volume both zero).",
                "evidence_reference": ref}
    net_value = proprietary_flow.get("net_value_vnd")
    if net_value is None:
        return {"axis": "PROPRIETARY_FLOW", "direction": UNKNOWN, "classification": DATA_WARNING,
                "claim": f"{ticker}: proprietary net value is absent despite an ACQUIRED capability status.",
                "evidence_reference": ref}
    direction = BULLISH if net_value > 0 else (BEARISH if net_value < 0 else NEUTRAL)
    verb = "buying" if net_value > 0 else ("selling" if net_value < 0 else "flat flow")
    claim = f"{ticker}: proprietary desks recorded net {verb} of {_fmt_vnd(abs(net_value))} this session."
    return {"axis": "PROPRIETARY_FLOW", "direction": direction, "classification": FACT, "claim": claim, "evidence_reference": ref}


def _order_imbalance_axis(ticker: str, microstructure: Mapping[str, Any], reason_codes: Sequence[str]) -> dict[str, Any]:
    ref = f"cross_dimension_cases[ticker={ticker}].microstructure"
    status = microstructure.get("status")
    if status != "ACQUIRED":
        return {"axis": "ORDER_IMBALANCE", "direction": UNKNOWN, "classification": DATA_WARNING,
                "claim": f"{ticker}: microstructure capability status is {status!r}, not ACQUIRED.",
                "evidence_reference": ref}
    buy_skew, sell_skew = "ACTIVE_BUY_SKEW" in reason_codes, "ACTIVE_SELL_SKEW" in reason_codes
    ratio = microstructure.get("imbalance_ratio")
    buy_o, sell_o = microstructure.get("active_buy_orders"), microstructure.get("active_sell_orders")
    claim = (f"{ticker}: active order-flow imbalance ratio is {_fmt_ratio(ratio)} "
             f"({_fmt_num(buy_o)} active buy orders vs {_fmt_num(sell_o)} active sell orders).")
    if buy_skew and not sell_skew:
        direction = BULLISH
    elif sell_skew and not buy_skew:
        direction = BEARISH
    else:
        direction = NEUTRAL
    return {"axis": "ORDER_IMBALANCE", "direction": direction, "classification": FACT, "claim": claim, "evidence_reference": ref}


def _put_through_axis(ticker: str, traded_value_composition: Mapping[str, Any], cross_dimension_analysis: Mapping[str, Any]) -> dict[str, Any]:
    ref = f"cross_dimension_cases[ticker={ticker}].traded_value_composition"
    character = cross_dimension_analysis.get("put_through_character")
    ratio = traded_value_composition.get("put_through_share_ratio")
    if character == "PUT_THROUGH_DOMINANT_ACTIVITY":
        return {"axis": "PUT_THROUGH_COMPOSITION", "severity": "DOMINANT", "classification": DATA_WARNING,
                "claim": (f"{ticker}: put-through value is {_fmt_pct_abs(ratio)} of total traded value this session -- "
                          "the majority of recorded value bypassed continuous order-book price discovery."),
                "evidence_reference": ref}
    if character == "SIGNIFICANT_PUT_THROUGH_ACTIVITY":
        return {"axis": "PUT_THROUGH_COMPOSITION", "severity": "SIGNIFICANT", "classification": DATA_WARNING,
                "claim": (f"{ticker}: put-through value is {_fmt_pct_abs(ratio)} of total traded value this session -- "
                          "a significant share bypassed continuous order-book price discovery."),
                "evidence_reference": ref}
    return {"axis": "PUT_THROUGH_COMPOSITION", "severity": "NONE", "classification": FACT,
            "claim": f"{ticker}: put-through character is {character!r} ({_fmt_pct_abs(ratio)} of total traded value); no material put-through caveat applies.",
            "evidence_reference": ref}


def _foreign_room_axis(ticker: str, foreign_room: Mapping[str, Any], cross_dimension_analysis: Mapping[str, Any]) -> dict[str, Any]:
    ref = f"cross_dimension_cases[ticker={ticker}].foreign_room"
    status = foreign_room.get("status")
    character = cross_dimension_analysis.get("foreign_room_character")
    if status != "ACQUIRED":
        return {"axis": "FOREIGN_ROOM", "constraint": UNKNOWN, "classification": DATA_WARNING,
                "claim": f"{ticker}: foreign-room capability status is {status!r}, not ACQUIRED; utilization is unavailable.",
                "evidence_reference": ref}
    ratio = foreign_room.get("utilization_ratio")
    if character in ("HIGH_FOREIGN_ROOM_UTILIZATION", "FOREIGN_ROOM_SATURATED_100PCT"):
        return {"axis": "FOREIGN_ROOM", "constraint": "BULL_LIMITING", "classification": FACT,
                "claim": (f"{ticker}: foreign-room utilization is {_fmt_pct_abs(ratio)} ({character}), a structural "
                          "ceiling on further foreign net inflows regardless of other signals."),
                "evidence_reference": ref}
    if character == "NOT_APPLICABLE":
        return {"axis": "FOREIGN_ROOM", "constraint": "NOT_APPLICABLE", "classification": FACT,
                "claim": f"{ticker}: foreign-room character is NOT_APPLICABLE for this instrument this session.",
                "evidence_reference": ref}
    return {"axis": "FOREIGN_ROOM", "constraint": "NONE", "classification": FACT,
            "claim": f"{ticker}: foreign-room utilization is {_fmt_pct_abs(ratio)} ({character}); no structural ceiling applies.",
            "evidence_reference": ref}


def _build_evidence_axes(ticker: str, record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    reason_codes = list(record.get("reason_codes") or [])
    cda = record.get("cross_dimension_analysis") or {}
    return {
        AXIS_TREND: _trend_axis(ticker, record.get("price_and_trend") or {}),
        AXIS_PROP_FLOW: _proprietary_flow_axis(ticker, record.get("proprietary_flow") or {}, reason_codes),
        AXIS_ORDER_IMBALANCE: _order_imbalance_axis(ticker, record.get("microstructure") or {}, reason_codes),
        AXIS_PUT_THROUGH: _put_through_axis(ticker, record.get("traded_value_composition") or {}, cda),
        AXIS_FOREIGN_ROOM: _foreign_room_axis(ticker, record.get("foreign_room") or {}, cda),
    }


# ---------------------------------------------------------------------------
# Cohort- and market-level context (cohort_profiles, market_state)
# ---------------------------------------------------------------------------

def _cohort_context(ticker: str, cohorts: Sequence[str], price_and_trend: Mapping[str, Any],
                     cohort_profiles: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = []
    for cohort in sorted(cohorts):
        profile = cohort_profiles.get(cohort)
        if profile is None:
            continue  # e.g. FHSC_ENRICHED_FLOW_WATCH, which is coverage-scoped, not a profiled cohort
        ref = f"cohort_profiles[{cohort}]"
        med_ret = profile["return_distribution"]["median"]
        med_rv = profile["relative_volume_distribution"]["median"]
        claim = (
            f"{ticker}'s 1D return {_fmt_pct(price_and_trend.get('return_1d'))} vs {cohort} cohort median "
            f"{_fmt_pct(med_ret)} (n={profile['return_distribution']['n']}); relative volume "
            f"{_fmt_ratio(price_and_trend.get('relative_volume'))}x vs cohort median {_fmt_ratio(med_rv)}x."
        )
        items.append({"classification": FACT, "cohort": cohort, "claim": claim, "evidence_reference": ref})
    return items


def _market_context(market_state: Mapping[str, Any]) -> dict[str, Any]:
    regime = market_state["regime_classification"]
    breadth = market_state["breadth"]
    ma = market_state["moving_average_breadth"]
    claim = (
        f"Session-wide descriptive regime is {regime['regime_label']} ({regime['derivation_reason']}); "
        f"advance/decline ratio {breadth['advance_decline_ratio']}, {ma['above_ma20_count']}/{market_state['universe_count']} "
        f"({ma['above_ma20_ratio'] * 100:.1f}%) of the full research universe above its 20-day moving average."
    )
    return {"classification": FACT, "claim": claim, "evidence_reference": "market_state.regime_classification",
            "is_descriptive_only": regime.get("is_descriptive_only", True)}


# ---------------------------------------------------------------------------
# Bear / Base / Bull lane construction
# ---------------------------------------------------------------------------

def _build_base_lane(ticker: str, axes: Mapping[str, dict[str, Any]], session_date: str) -> dict[str, Any]:
    confirming = [
        {"classification": FACT, "claim": axis["claim"], "evidence_reference": axis["evidence_reference"], "axis": name.upper()}
        for name, axis in axes.items() if axis["classification"] == FACT
    ]
    invalidating = [{
        "classification": HYPOTHESIS,
        "claim": (f"A later research_intelligence_digest_v1 session (a session_date different from {session_date}) "
                  f"retains different reason_codes or evidence values for {ticker}; this record is a single-session "
                  "descriptive snapshot only."),
        "evidence_reference": f"cross_dimension_cases[ticker={ticker}].reason_codes",
    }]
    return {"label": "BASE", "confirming_conditions": confirming, "countervailing_evidence": [], "invalidating_conditions": invalidating}


def _build_directional_lane(label: str, ticker: str, axes: Mapping[str, dict[str, Any]], session_date: str) -> dict[str, Any]:
    want = BULLISH if label == "BULL" else BEARISH
    opposite = BEARISH if label == "BULL" else BULLISH
    participation = "upward" if label == "BULL" else "downward"

    confirming: list[dict[str, Any]] = []
    countervailing: list[dict[str, Any]] = []
    invalidating: list[dict[str, Any]] = []
    for name in DIRECTIONAL_AXIS_NAMES:
        axis = axes[name]
        if axis["direction"] == want:
            confirming.append({
                "classification": INFERENCE,
                "claim": (f"This session's {name.replace('_', ' ')} reading -- {axis['claim']} -- is consistent "
                          f"with continued {participation} participation if it persists in later sessions."),
                "evidence_reference": axis["evidence_reference"], "axis": name.upper(),
            })
            invalidating.append({
                "classification": HYPOTHESIS,
                "claim": (f"A later retained session shows {ticker}'s {name.replace('_', ' ')} reading has reversed "
                          f"to {opposite.lower()} from this session's ({session_date}) {want.lower()} reading."),
                "evidence_reference": axis["evidence_reference"], "axis": name.upper(),
            })
        elif axis["direction"] == opposite:
            countervailing.append({
                "classification": FACT, "claim": axis["claim"],
                "evidence_reference": axis["evidence_reference"], "axis": name.upper(),
            })

    if label == "BULL" and axes[AXIS_FOREIGN_ROOM].get("constraint") == "BULL_LIMITING":
        fr = axes[AXIS_FOREIGN_ROOM]
        countervailing.append({
            "classification": FACT, "claim": fr["claim"],
            "evidence_reference": fr["evidence_reference"], "axis": "FOREIGN_ROOM",
        })

    return {"label": label, "confirming_conditions": confirming, "countervailing_evidence": countervailing, "invalidating_conditions": invalidating}


def _build_warnings(ticker: str, record: Mapping[str, Any], axes: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
    warnings = [
        {"classification": DATA_WARNING, "claim": axis["claim"], "evidence_reference": axis["evidence_reference"]}
        for axis in axes.values() if axis["classification"] == DATA_WARNING
    ]
    for capability, status in sorted((record.get("missing_or_failed_capabilities") or {}).items()):
        warnings.append({
            "classification": DATA_WARNING,
            "claim": f"{ticker}: capability {capability} is {status}, not ACQUIRED.",
            "evidence_reference": f"cross_dimension_cases[ticker={ticker}].missing_or_failed_capabilities.{capability}",
        })
    if record.get("enrichment_tier") == "PARTIALLY_ENRICHED":
        warnings.append({
            "classification": DATA_WARNING,
            "claim": (f"{ticker}: enrichment_tier is PARTIALLY_ENRICHED; at least one cross-dimension capability "
                      "is missing or failed for this session."),
            "evidence_reference": f"cross_dimension_cases[ticker={ticker}].enrichment_tier",
        })
    return warnings


# ---------------------------------------------------------------------------
# Per-ticker scenario record
# ---------------------------------------------------------------------------

def build_ticker_scenario(
    ticker: str, record: Mapping[str, Any], matched_case_types: Sequence[str],
    cohort_profiles: Mapping[str, Any], market_state: Mapping[str, Any], session_date: str,
    digest_identity: str, cross_dimension_source_identity: str | None,
) -> dict[str, Any]:
    axes = _build_evidence_axes(ticker, record)
    cohorts = sorted(record.get("active_research_cohorts") or [])
    cohort_ctx = _cohort_context(ticker, cohorts, record.get("price_and_trend") or {}, cohort_profiles)
    market_ctx = _market_context(market_state)
    warnings = _build_warnings(ticker, record, axes)

    base = _build_base_lane(ticker, axes, session_date)
    bull = _build_directional_lane("BULL", ticker, axes, session_date)
    bear = _build_directional_lane("BEAR", ticker, axes, session_date)

    evidence_refs = {axis["evidence_reference"] for axis in axes.values()}
    evidence_refs.update(c["evidence_reference"] for c in cohort_ctx)
    evidence_refs.add(market_ctx["evidence_reference"])

    content: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "ticker": ticker,
        "session_date": session_date,
        "enrichment_tier": record.get("enrichment_tier"),
        "active_research_cohorts": cohorts,
        "evidence_axes": axes,
        "cohort_context": cohort_ctx,
        "market_context": market_ctx,
        "scenarios": {"BEAR": bear, "BASE": base, "BULL": bull},
        "warnings_and_data_gaps": warnings,
        "lineage": {
            "source_research_intelligence_digest_identity": digest_identity,
            "source_cross_dimension_research_digest_identity": cross_dimension_source_identity,
            "matched_cross_dimension_case_types": list(matched_case_types),
            "evidence_field_references": sorted(evidence_refs),
        },
        "probability_status": "UNQUALIFIED",
        "authority_boundary": TICKER_AUTHORITY_BOUNDARY,
        "scenario_qualification_status": "CROSS_DIMENSION_EVIDENCE_BOUND_SCENARIO",
    }
    content["scenario_content_identity"] = "scenario_content:" + _sha256_json(content)
    return content


# ---------------------------------------------------------------------------
# Cohort reconciliation and evidence-depth assessment
# ---------------------------------------------------------------------------

def _build_cohort_reconciliation(digest: Mapping[str, Any], by_ticker: Mapping[str, Any]) -> dict[str, Any]:
    cov = digest["coverage_and_data_quality"]["tiers"]
    full_universe = digest["market_state"]["universe_count"]
    fully, partially = cov["FULLY_ENRICHED_COHORT"], cov["PARTIALLY_ENRICHED"]
    enriched_total = fully + partially
    surfaced = len(by_ticker)
    unsurfaced = enriched_total - surfaced
    surfaced_fully = sum(1 for e in by_ticker.values() if e["record"].get("enrichment_tier") == "FULLY_ENRICHED")
    surfaced_partially = sum(1 for e in by_ticker.values() if e["record"].get("enrichment_tier") == "PARTIALLY_ENRICHED")
    return {
        "full_universe_denominator": full_universe,
        "cross_dimension_sample_denominator": digest["cross_dimension_cases"]["sample_denominator"],
        "fully_enriched_count": fully,
        "partially_enriched_count": partially,
        "fully_or_partially_enriched_denominator": enriched_total,
        "cross_dimension_case_surfaced_denominator": surfaced,
        "cross_dimension_case_surfaced_fully_enriched_count": surfaced_fully,
        "cross_dimension_case_surfaced_partially_enriched_count": surfaced_partially,
        "unsurfaced_enriched_count": unsurfaced,
        "unsurfaced_ticker_identities": UNSURFACED_IDENTITIES_LABEL if unsurfaced > 0 else "NONE_UNSURFACED",
        "scenario_produced_count": surfaced,
        "reconciliation_valid": (surfaced + unsurfaced == enriched_total) and (enriched_total <= full_universe),
        "never_extrapolated_to_full_universe": True,
    }


def _axis_signature(scenario: Mapping[str, Any]) -> tuple[str, ...]:
    axes = scenario["evidence_axes"]
    return tuple(axes[name]["direction"] for name in DIRECTIONAL_AXIS_NAMES)


def assess_evidence_depth(scenarios: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Distinguish genuinely evidence-differentiated output from a degenerate/templated cohort."""
    if not scenarios:
        return {"verdict": "INSUFFICIENT", "reason": "ZERO_TICKERS_SURFACED_WITH_CROSS_DIMENSION_EVIDENCE"}
    signatures = {_axis_signature(s) for s in scenarios}
    if len(scenarios) > 1 and len(signatures) <= 1:
        return {
            "verdict": "INSUFFICIENT",
            "reason": "ALL_SURFACED_TICKERS_SHARE_AN_IDENTICAL_AXIS_DIRECTION_SIGNATURE_NO_GENUINE_DIFFERENTIATION",
        }
    return {
        "verdict": "SUFFICIENT",
        "reason": f"{len(signatures)} distinct axis-direction signature(s) observed across {len(scenarios)} ticker(s).",
    }


def _build_narrative_scope_notes(reconciliation: Mapping[str, Any], depth: Mapping[str, Any]) -> list[str]:
    notes = [
        (f"Full research universe is {reconciliation['full_universe_denominator']}; this artifact's scenario "
         "cohort is never extrapolated to that denominator."),
        (f"{reconciliation['fully_or_partially_enriched_denominator']} symbols are fully or partially enriched "
         f"this session; {reconciliation['cross_dimension_case_surfaced_denominator']} of those are surfaced with "
         "structured per-symbol cross-dimension evidence in research_intelligence_digest_v1.cross_dimension_cases "
         "and receive a scenario record here."),
    ]
    if reconciliation["unsurfaced_enriched_count"]:
        notes.append(
            f"{reconciliation['unsurfaced_enriched_count']} enriched symbol(s) are not surfaced in "
            "cross_dimension_cases (no reason code matched any retained case bucket); their identities are "
            f"{reconciliation['unsurfaced_ticker_identities']} and no scenario is produced for them by this tool."
        )
    notes.append(f"Evidence-depth assessment: {depth['verdict']} -- {depth['reason']}")
    return notes


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

def build_capability_first_scenario_distribution(digest: Mapping[str, Any]) -> dict[str, Any]:
    validate_digest_identity(digest)

    session_date = digest["session_date"]
    market_state = digest["market_state"]
    cohort_profiles = digest["cohort_profiles"]
    cross_dimension_source_identity = digest["cross_dimension_cases"].get("source_digest_identity")

    by_ticker = _collect_cross_dimension_members(digest)

    scenarios = [
        build_ticker_scenario(
            ticker, by_ticker[ticker]["record"], by_ticker[ticker]["matched_case_types"],
            cohort_profiles, market_state, session_date, digest["digest_identity"], cross_dimension_source_identity,
        )
        for ticker in sorted(by_ticker)
    ]

    reconciliation = _build_cohort_reconciliation(digest, by_ticker)
    depth = assess_evidence_depth(scenarios)

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "session_date": session_date,
        "execution_timestamp": datetime.now(UTC).isoformat(),
        "source_artifacts": {"research_intelligence_digest_identity": digest["digest_identity"]},
        "cohort_reconciliation": reconciliation,
        "evidence_depth_assessment": depth,
        "scenarios": scenarios,
        "authority_boundaries": AUTHORITY_BOUNDARIES,
        "narrative_scope_notes": _build_narrative_scope_notes(reconciliation, depth),
    }
    artifact_sha = _sha256_json({
        k: v for k, v in artifact.items() if k not in {"artifact_sha256", "artifact_identity", "execution_timestamp"}
    })
    artifact["artifact_sha256"] = artifact_sha
    artifact["artifact_identity"] = f"capability_first_scenario_distribution:{artifact_sha}"
    return artifact


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Derive deterministic Bear/Base/Bull scenarios from research_intelligence_digest_v1."
    )
    parser.add_argument(
        "--digest-path",
        default="operations-review/research-intelligence-digest-2026-08-21/research_intelligence_digest_v1.json",
    )
    parser.add_argument(
        "--out-dir",
        default="operations-review/capability-first-scenario-distribution-2026-08-22",
    )
    args = parser.parse_args(argv)

    def _resolve(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else ROOT / path

    digest_path = _resolve(args.digest_path)
    out_dir = _resolve(args.out_dir)

    print(f"Loading research intelligence digest from: {digest_path}")
    digest = json.loads(digest_path.read_text(encoding="utf-8"))

    print("Deriving capability-first scenario distribution...")
    artifact = build_capability_first_scenario_distribution(digest)

    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / "capability_first_scenario_distribution_v1.json"
    atomic_write_json(artifact_path, artifact)

    manifest_path = out_dir / "manifest.json"
    manifest = {
        "manifest_schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "session_date": artifact["session_date"],
        "created_at": datetime.now(UTC).isoformat(),
        "artifact_identity": artifact["artifact_identity"],
        "artifact_sha256": artifact["artifact_sha256"],
        "source_artifacts": artifact["source_artifacts"],
        "files": {
            "capability_first_scenario_distribution_v1.json": {
                "size_bytes": artifact_path.stat().st_size,
                "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            },
        },
        "authority_boundaries": AUTHORITY_BOUNDARIES,
    }
    atomic_write_json(manifest_path, manifest)

    print(json.dumps({
        "status": "CAPABILITY_FIRST_SCENARIO_DISTRIBUTION_COMPLETE",
        "artifact_identity": artifact["artifact_identity"],
        "session_date": artifact["session_date"],
        "cohort_reconciliation": artifact["cohort_reconciliation"],
        "evidence_depth_assessment": artifact["evidence_depth_assessment"],
        "scenario_count": len(artifact["scenarios"]),
        "out_dir": str(out_dir),
    }, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    sys.exit(main())
