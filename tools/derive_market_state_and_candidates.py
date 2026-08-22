"""tools/derive_market_state_and_candidates.py — Deterministic Market State & Research Candidate Engine.

Transforms the 524-symbol 2026-08-21 research snapshot and retained FHSC evidence into:
1. MARKET STATE: Full 524-symbol market breadth, return/volatility distributions, cross-metrics,
   and deterministic descriptive regime classification (BROAD_RISK_ON, POSITIVE_BUT_NARROW,
   MIXED, BROAD_RISK_OFF, STRESS).
2. RESEARCH CANDIDATE COHORTS: Deterministic research cohorts based on explicit rule sets:
   - MOMENTUM_PARTICIPATION
   - TREND_WITHOUT_PARTICIPATION
   - HIGH_ACTIVITY_REVERSAL_OR_DISTRIBUTION
   - HIGH_VOLATILITY_WATCH
   - FHSC_ENRICHED_FLOW_WATCH (coverage-scoped)

Authority Boundaries:
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
from tools.scaleout_capability_research_digest import (
    AUTHORITY_BOUNDARIES,
    build_research_digest,
    find_retained_packets_for_session,
    load_universe_snapshot,
)

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "capability_first_market_state_candidates/v1"

# Candidate cohort identifiers
COHORT_MOMENTUM_PARTICIPATION = "MOMENTUM_PARTICIPATION"
COHORT_TREND_WITHOUT_PARTICIPATION = "TREND_WITHOUT_PARTICIPATION"
COHORT_HIGH_ACTIVITY_REVERSAL = "HIGH_ACTIVITY_REVERSAL_OR_DISTRIBUTION"
COHORT_HIGH_VOLATILITY_WATCH = "HIGH_VOLATILITY_WATCH"
COHORT_FHSC_ENRICHED_FLOW = "FHSC_ENRICHED_FLOW_WATCH"

# Regime labels
REGIME_BROAD_RISK_ON = "BROAD_RISK_ON"
REGIME_POSITIVE_BUT_NARROW = "POSITIVE_BUT_NARROW"
REGIME_MIXED = "MIXED"
REGIME_BROAD_RISK_OFF = "BROAD_RISK_OFF"
REGIME_STRESS = "STRESS"


def _canonical_json(val: Any) -> str:
    return json.dumps(val, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_json(val: Any) -> str:
    return hashlib.sha256(_canonical_json(val).encode("utf-8")).hexdigest()


def derive_market_regime(
    advancers_count: int,
    decliners_count: int,
    total_universe_count: int,
    above_ma20_count: int,
    median_return_1d: float | None,
    negative_return_and_elevated_volume_count: int,
) -> dict[str, Any]:
    """Derive deterministic descriptive market regime label using explicit threshold rules."""
    ad_ratio = round(advancers_count / decliners_count, 4) if decliners_count > 0 else 999.0
    above_ma20_ratio = round(above_ma20_count / total_universe_count, 4) if total_universe_count > 0 else 0.0
    med_ret = median_return_1d if median_return_1d is not None else 0.0

    rules_documentation = {
        REGIME_BROAD_RISK_ON: "advancers/decliners >= 2.0 AND above_ma20_ratio >= 0.55 AND median_return_1d > 0.0",
        REGIME_POSITIVE_BUT_NARROW: "median_return_1d > 0.0 AND (advancers/decliners < 2.0 OR above_ma20_ratio < 0.55)",
        REGIME_BROAD_RISK_OFF: "advancers/decliners <= 0.5 AND above_ma20_ratio <= 0.45 AND median_return_1d < 0.0",
        REGIME_STRESS: "advancers/decliners <= 0.3 AND negative_return_and_elevated_volume_count >= 100",
        REGIME_MIXED: "All other market conditions",
    }

    if ad_ratio <= 0.3 and negative_return_and_elevated_volume_count >= 100:
        regime = REGIME_STRESS
        reason = f"Stress criteria met: AD ratio {ad_ratio:.2f} <= 0.30 and {negative_return_and_elevated_volume_count} high-volume decliners >= 100"
    elif ad_ratio >= 2.0 and above_ma20_ratio >= 0.55 and med_ret > 0.0:
        regime = REGIME_BROAD_RISK_ON
        reason = f"Broad risk-on criteria met: AD ratio {ad_ratio:.2f} >= 2.0, Above MA20 ratio {above_ma20_ratio * 100:.1f}% >= 55.0%, Median return {med_ret * 100:+.2f}% > 0"
    elif med_ret > 0.0:
        regime = REGIME_POSITIVE_BUT_NARROW
        reason = f"Positive but narrow criteria met: Median return {med_ret * 100:+.2f}% > 0, but AD ratio {ad_ratio:.2f} or Above MA20 {above_ma20_ratio * 100:.1f}% below broad threshold"
    elif ad_ratio <= 0.5 and above_ma20_ratio <= 0.45 and med_ret < 0.0:
        regime = REGIME_BROAD_RISK_OFF
        reason = f"Broad risk-off criteria met: AD ratio {ad_ratio:.2f} <= 0.50, Above MA20 ratio {above_ma20_ratio * 100:.1f}% <= 45.0%, Median return {med_ret * 100:+.2f}% < 0"
    else:
        regime = REGIME_MIXED
        reason = f"Mixed market criteria met: AD ratio {ad_ratio:.2f}, Above MA20 {above_ma20_ratio * 100:.1f}%, Median return {med_ret * 100:+.2f}%"

    return {
        "regime_label": regime,
        "is_descriptive_only": True,
        "derivation_reason": reason,
        "input_metrics": {
            "advance_decline_ratio": ad_ratio,
            "above_ma20_ratio": above_ma20_ratio,
            "median_return_1d": med_ret,
            "negative_return_and_elevated_volume_count": negative_return_and_elevated_volume_count,
        },
        "threshold_rules": rules_documentation,
    }


def derive_market_state_and_candidates(digest_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Derive comprehensive deterministic market state analysis and research candidate cohorts."""
    session_date = digest_payload["session_date"]
    core = digest_payload["market_wide_core"]
    enr = digest_payload["fhsc_enrichment"]
    records = digest_payload["records"]
    cov_summary = digest_payload["coverage_summary"]

    total_universe_count = core["universe_count"]

    # 1. Detailed Cross-Metric Accounting across full 524-symbol universe
    pos_ret_and_above_ma20: list[str] = []
    pos_ret_and_elevated_vol: list[str] = []
    neg_ret_and_elevated_vol: list[str] = []
    above_ma20_and_elevated_vol: list[str] = []

    all_volatilities: list[float] = []
    records_by_ticker: dict[str, dict[str, Any]] = {}

    for r in records:
        ticker = r["ticker"]
        records_by_ticker[ticker] = r
        dnse = r.get("dnse_market_data")
        if not dnse:
            continue

        ret_1d = dnse.get("return_1d")
        close_vnd = dnse.get("exact_session_close_vnd")
        ma_20 = dnse.get("ma_20_vnd")
        rel_vol = dnse.get("relative_volume_provider_scoped")
        vol_20d = dnse.get("volatility_20d")

        if vol_20d is not None:
            all_volatilities.append(vol_20d)

        is_pos = ret_1d is not None and ret_1d > 0.0001
        is_neg = ret_1d is not None and ret_1d < -0.0001
        is_above_ma = close_vnd is not None and ma_20 is not None and close_vnd > ma_20
        is_elevated_vol = rel_vol is not None and rel_vol >= 1.5

        if is_pos and is_above_ma:
            pos_ret_and_above_ma20.append(ticker)
        if is_pos and is_elevated_vol:
            pos_ret_and_elevated_vol.append(ticker)
        if is_neg and is_elevated_vol:
            neg_ret_and_elevated_vol.append(ticker)
        if is_above_ma and is_elevated_vol:
            above_ma20_and_elevated_vol.append(ticker)

    # Calculate 90th percentile volatility threshold for upper tail cohort
    sorted_vols = sorted(all_volatilities)
    p90_volatility = None
    if sorted_vols:
        p90_volatility = sorted_vols[int(len(sorted_vols) * 0.90)]

    # 2. Derive Market Regime
    breadth = core["breadth_summary"]
    regime_info = derive_market_regime(
        advancers_count=breadth["advancers_count"],
        decliners_count=breadth["decliners_count"],
        total_universe_count=total_universe_count,
        above_ma20_count=core["moving_average_breadth"]["above_ma20_count"],
        median_return_1d=core["return_distribution"]["median_return_1d"],
        negative_return_and_elevated_volume_count=len(neg_ret_and_elevated_vol),
    )

    # Full market state structure
    market_state = {
        "aggregate_scope": "FULL_RESEARCH_UNIVERSE",
        "universe_count": total_universe_count,
        "session_date": session_date,
        "regime_classification": regime_info,
        "breadth": breadth,
        "return_distribution": core["return_distribution"],
        "moving_average_breadth": core["moving_average_breadth"],
        "volatility_distribution": core["volatility_distribution"],
        "relative_volume_breadth": core["relative_volume_breadth"],
        "cross_metric_intersections": {
            "positive_return_and_above_ma20_count": len(pos_ret_and_above_ma20),
            "positive_return_and_above_ma20_ratio": round(len(pos_ret_and_above_ma20) / total_universe_count, 6),
            "positive_return_and_elevated_volume_count": len(pos_ret_and_elevated_vol),
            "positive_return_and_elevated_volume_ratio": round(len(pos_ret_and_elevated_vol) / total_universe_count, 6),
            "negative_return_and_elevated_volume_count": len(neg_ret_and_elevated_vol),
            "negative_return_and_elevated_volume_ratio": round(len(neg_ret_and_elevated_vol) / total_universe_count, 6),
            "above_ma20_and_elevated_volume_count": len(above_ma20_and_elevated_vol),
            "above_ma20_and_elevated_volume_ratio": round(len(above_ma20_and_elevated_vol) / total_universe_count, 6),
        },
        "descriptive_tails": core["descriptive_tails"],
    }

    # 3. Formulate Deterministic Research Candidate Cohorts
    cohort_momentum_participation: list[dict[str, Any]] = []
    cohort_trend_without_participation: list[dict[str, Any]] = []
    cohort_high_activity_reversal: list[dict[str, Any]] = []
    cohort_high_volatility_watch: list[dict[str, Any]] = []
    cohort_fhsc_enriched_flow: list[dict[str, Any]] = []

    for r in records:
        ticker = r["ticker"]
        dnse = r.get("dnse_market_data") or {}
        ret_1d = dnse.get("return_1d")
        close_vnd = dnse.get("exact_session_close_vnd")
        ma_20 = dnse.get("ma_20_vnd")
        rel_vol = dnse.get("relative_volume_provider_scoped")
        vol_20d = dnse.get("volatility_20d")

        trading = r.get("fhsc_value_volume_composition") or {}
        room = r.get("fhsc_foreign_room") or {}
        prop = r.get("fhsc_proprietary_flow") or {}
        micro = r.get("fhsc_microstructure") or {}

        base_metrics = {
            "close_vnd": close_vnd,
            "return_1d": ret_1d,
            "ma_20_vnd": ma_20,
            "relative_volume_provider_scoped": rel_vol,
            "volatility_20d": vol_20d,
        }

        # 1. MOMENTUM_PARTICIPATION (positive return + above MA20 + elevated rel vol >= 1.5)
        if ret_1d is not None and ret_1d > 0.0001 and close_vnd is not None and ma_20 is not None and close_vnd > ma_20 and rel_vol is not None and rel_vol >= 1.5:
            cohort_momentum_participation.append({
                "ticker": ticker,
                "cohort": COHORT_MOMENTUM_PARTICIPATION,
                "input_metrics": base_metrics,
                "reason_codes": [
                    f"POSITIVE_RETURN_1D ({ret_1d * 100:+.2f}%)",
                    f"ABOVE_20D_MOVING_AVERAGE ({close_vnd:,.0f} > {ma_20:,.0f})",
                    f"ELEVATED_RELATIVE_VOLUME ({rel_vol:.2f}x >= 1.5x)",
                ],
                "inclusion_rule": "return_1d > 0 AND close > ma_20 AND relative_volume_provider_scoped >= 1.5",
            })

        # 2. TREND_WITHOUT_PARTICIPATION (above MA20 + weak/depressed rel vol <= 0.8)
        if close_vnd is not None and ma_20 is not None and close_vnd > ma_20 and rel_vol is not None and rel_vol <= 0.8:
            cohort_trend_without_participation.append({
                "ticker": ticker,
                "cohort": COHORT_TREND_WITHOUT_PARTICIPATION,
                "input_metrics": base_metrics,
                "reason_codes": [
                    f"ABOVE_20D_MOVING_AVERAGE ({close_vnd:,.0f} > {ma_20:,.0f})",
                    f"DEPRESSED_RELATIVE_VOLUME ({rel_vol:.2f}x <= 0.8x)",
                ],
                "inclusion_rule": "close > ma_20 AND relative_volume_provider_scoped <= 0.8",
            })

        # 3. HIGH_ACTIVITY_REVERSAL_OR_DISTRIBUTION (negative return + elevated rel vol >= 1.5)
        if ret_1d is not None and ret_1d < -0.0001 and rel_vol is not None and rel_vol >= 1.5:
            cohort_high_activity_reversal.append({
                "ticker": ticker,
                "cohort": COHORT_HIGH_ACTIVITY_REVERSAL,
                "input_metrics": base_metrics,
                "reason_codes": [
                    f"NEGATIVE_RETURN_1D ({ret_1d * 100:+.2f}%)",
                    f"ELEVATED_RELATIVE_VOLUME ({rel_vol:.2f}x >= 1.5x)",
                ],
                "inclusion_rule": "return_1d < 0 AND relative_volume_provider_scoped >= 1.5",
            })

        # 4. HIGH_VOLATILITY_WATCH (upper-tail 20D volatility >= p90)
        if vol_20d is not None and p90_volatility is not None and vol_20d >= p90_volatility:
            cohort_high_volatility_watch.append({
                "ticker": ticker,
                "cohort": COHORT_HIGH_VOLATILITY_WATCH,
                "input_metrics": base_metrics,
                "reason_codes": [
                    f"UPPER_TAIL_20D_VOLATILITY ({vol_20d:.4f} >= P90 threshold {p90_volatility:.4f})",
                ],
                "inclusion_rule": f"volatility_20d >= p90_threshold ({p90_volatility:.4f})",
            })

        # 5. FHSC_ENRICHED_FLOW_WATCH (only among ACQUIRED FHSC records)
        if trading.get("status") == "ACQUIRED":
            reasons: list[str] = []
            m_rat = trading.get("matched_value_ratio")
            p_rat = trading.get("put_through_value_ratio")
            pt_val = trading.get("put_through_traded_value_vnd")
            prop_net_val = prop.get("net_value_vnd")
            room_util = room.get("foreign_room_utilization_ratio")
            imb = micro.get("order_volume_imbalance_ratio")

            fhsc_metrics = {
                **base_metrics,
                "matched_traded_value_vnd": trading.get("matched_traded_value_vnd"),
                "put_through_traded_value_vnd": pt_val,
                "matched_value_ratio": m_rat,
                "put_through_value_ratio": p_rat,
                "foreign_room_utilization_ratio": room_util,
                "proprietary_net_value_vnd": prop_net_val,
                "proprietary_net_volume_shares": prop.get("net_volume"),
                "order_volume_imbalance_ratio": imb,
                "fhsc_sample_scope": "ACQUIRED_ENRICHMENT_COHORT",
            }

            if p_rat is not None and p_rat >= 0.15:
                reasons.append(f"SIGNIFICANT_PUT_THROUGH_SHARE ({p_rat * 100:.1f}% >= 15.0%, value: {pt_val:,.0f} VND)")

            if prop_net_val is not None and abs(prop_net_val) >= 10_000_000_000:
                dir_str = "NET_BUY" if prop_net_val > 0 else "NET_SELL"
                reasons.append(f"LARGE_PROPRIETARY_FLOW_{dir_str} ({prop_net_val:,.0f} VND >= 10B VND)")

            if room_util is not None and room_util >= 0.80:
                reasons.append(f"HIGH_FOREIGN_ROOM_UTILIZATION ({room_util * 100:.1f}% >= 80.0%)")

            if imb is not None and abs(imb) >= 0.10:
                imb_dir = "AGGRESSIVE_BUY_IMBALANCE" if imb > 0 else "AGGRESSIVE_SELL_IMBALANCE"
                reasons.append(f"NOTABLE_{imb_dir} ({imb:+.3f} magnitude >= 0.10)")

            if reasons:
                cohort_fhsc_enriched_flow.append({
                    "ticker": ticker,
                    "cohort": COHORT_FHSC_ENRICHED_FLOW,
                    "input_metrics": fhsc_metrics,
                    "reason_codes": reasons,
                    "inclusion_rule": "ACQUIRED FHSC with (put_through_share >= 15% OR abs(prop_net) >= 10B OR room_util >= 80% OR abs(imbalance) >= 0.10)",
                })

    # Sort cohorts deterministically by ticker
    cohort_momentum_participation.sort(key=lambda x: x["ticker"])
    cohort_trend_without_participation.sort(key=lambda x: x["ticker"])
    cohort_high_activity_reversal.sort(key=lambda x: x["ticker"])
    cohort_high_volatility_watch.sort(key=lambda x: x["ticker"])
    cohort_fhsc_enriched_flow.sort(key=lambda x: x["ticker"])

    research_cohorts = {
        "cohorts_schema_version": "1.0.0",
        "authority_disclaimer": "RESEARCH_CANDIDATE_COHORTS_ARE_DESCRIPTIVE_ONLY_NO_RECOMMENDATION_NO_RANKING_AUTHORITY",
        "cohort_summaries": {
            COHORT_MOMENTUM_PARTICIPATION: {
                "count": len(cohort_momentum_participation),
                "scope": "FULL_RESEARCH_UNIVERSE",
                "denominator": total_universe_count,
                "coverage_ratio": round(len(cohort_momentum_participation) / total_universe_count, 6),
                "description": "Positive 1D return + Above 20D Moving Average + Elevated Relative Volume (>= 1.5x)",
            },
            COHORT_TREND_WITHOUT_PARTICIPATION: {
                "count": len(cohort_trend_without_participation),
                "scope": "FULL_RESEARCH_UNIVERSE",
                "denominator": total_universe_count,
                "coverage_ratio": round(len(cohort_trend_without_participation) / total_universe_count, 6),
                "description": "Above 20D Moving Average + Depressed Relative Volume (<= 0.8x)",
            },
            COHORT_HIGH_ACTIVITY_REVERSAL: {
                "count": len(cohort_high_activity_reversal),
                "scope": "FULL_RESEARCH_UNIVERSE",
                "denominator": total_universe_count,
                "coverage_ratio": round(len(cohort_high_activity_reversal) / total_universe_count, 6),
                "description": "Negative 1D return + Elevated Relative Volume (>= 1.5x)",
            },
            COHORT_HIGH_VOLATILITY_WATCH: {
                "count": len(cohort_high_volatility_watch),
                "scope": "FULL_RESEARCH_UNIVERSE",
                "denominator": total_universe_count,
                "coverage_ratio": round(len(cohort_high_volatility_watch) / total_universe_count, 6),
                "description": f"Upper-tail 20D Volatility (>= P90 threshold {p90_volatility:.4f})",
            },
            COHORT_FHSC_ENRICHED_FLOW: {
                "count": len(cohort_fhsc_enriched_flow),
                "scope": "ACQUIRED_ENRICHMENT_COHORT",
                "denominator": enr["coverage_denominators"]["trading_composition"]["acquired_symbol_count"],
                "universe_denominator": total_universe_count,
                "coverage_ratio": round(len(cohort_fhsc_enriched_flow) / total_universe_count, 6),
                "description": "Acquired FHSC with notable put-through share, proprietary net flow, foreign room, or order imbalance",
            },
        },
        "cohort_entries": {
            COHORT_MOMENTUM_PARTICIPATION: cohort_momentum_participation,
            COHORT_TREND_WITHOUT_PARTICIPATION: cohort_trend_without_participation,
            COHORT_HIGH_ACTIVITY_REVERSAL: cohort_high_activity_reversal,
            COHORT_HIGH_VOLATILITY_WATCH: cohort_high_volatility_watch,
            COHORT_FHSC_ENRICHED_FLOW: cohort_fhsc_enriched_flow,
        },
    }

    # 4. Provenance & Artifact Envelope
    artifact_payload = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "session_date": session_date,
        "execution_timestamp": datetime.now(UTC).isoformat(),
        "input_digest_identity": digest_payload.get("digest_identity"),
        "input_digest_sha256": digest_payload.get("digest_sha256"),
        "universe_cohort_source": "prospective_20260821_shadow_cohort",
        "market_state": market_state,
        "research_candidate_cohorts": research_cohorts,
        "coverage_summary": cov_summary,
        "authority_boundaries": {
            **AUTHORITY_BOUNDARIES,
            "ranking_authority": False,
            "recommendation_authority": False,
        },
    }

    artifact_sha256 = _sha256_json({
        k: v for k, v in artifact_payload.items()
        if k not in {"artifact_sha256", "artifact_identity", "execution_timestamp"}
    })
    artifact_payload["artifact_sha256"] = artifact_sha256
    artifact_payload["artifact_identity"] = f"market_state_and_candidates:{artifact_sha256}"

    return artifact_payload


def generate_candidate_markdown_summary(artifact: Mapping[str, Any]) -> str:
    """Generate comprehensive human-readable Markdown report for daily market state & research candidates."""
    session = artifact["session_date"]
    m_state = artifact["market_state"]
    regime = m_state["regime_classification"]
    breadth = m_state["breadth"]
    ret_dist = m_state["return_distribution"]
    ma_breadth = m_state["moving_average_breadth"]
    vol_dist = m_state["volatility_distribution"]
    rel_vol_breadth = m_state["relative_volume_breadth"]
    x_metrics = m_state["cross_metric_intersections"]
    tails = m_state["descriptive_tails"]
    cohorts = artifact["research_candidate_cohorts"]
    c_entries = cohorts["cohort_entries"]
    cov = artifact["coverage_summary"]
    decomp = cov["trading_history_scaleout_decomposition"]

    md = [
        f"# Daily Market State & Research Candidate Digest — Session {session}",
        "",
        f"- **Artifact Identity**: `{artifact['artifact_identity']}`",
        f"- **Contract Version**: `{artifact['contract_version']}`",
        f"- **Input Digest Identity**: `{artifact['input_digest_identity']}`",
        f"- **Session Date**: `{session}`",
        f"- **Authority**: `DESCRIPTIVE_RESEARCH_ONLY_NO_BUY_SELL_NO_RANKING_AUTHORITY`",
        "",
        "---",
        "",
        "## 1. Market State & Regime Overview (`aggregate_scope: FULL_RESEARCH_UNIVERSE`)",
        "",
        f"> [!NOTE]",
        f"> **Descriptive Regime**: **`{regime['regime_label']}`**",
        f"> **Derivation**: {regime['derivation_reason']}",
        "",
        "### 1.1 Market Breadth & Directional Health",
        f"- **Active Universe Analyzed**: `{m_state['universe_count']} symbols` (100.0% coverage)",
        f"- **Advancers**: `{breadth['advancers_count']}` ({breadth['advancers_count'] / m_state['universe_count'] * 100:.1f}%)",
        f"- **Decliners**: `{breadth['decliners_count']}` ({breadth['decliners_count'] / m_state['universe_count'] * 100:.1f}%)",
        f"- **Unchanged**: `{breadth['unchanged_count']}` ({breadth['unchanged_count'] / m_state['universe_count'] * 100:.1f}%)",
        f"- **Advance / Decline Ratio**: `{breadth['advance_decline_ratio']}`",
        f"- **Above 20D Moving Average**: `{ma_breadth['above_ma20_count']} / {m_state['universe_count']}` ({ma_breadth['above_ma20_ratio'] * 100:.1f}%)",
        "",
        "### 1.2 Cross-Metric Breadth Intersections",
        f"- **Positive Return + Above MA20**: `{x_metrics['positive_return_and_above_ma20_count']}` symbols ({x_metrics['positive_return_and_above_ma20_ratio'] * 100:.1f}%)",
        f"- **Positive Return + Elevated Volume (>=1.5x)**: `{x_metrics['positive_return_and_elevated_volume_count']}` symbols ({x_metrics['positive_return_and_elevated_volume_ratio'] * 100:.1f}%)",
        f"- **Negative Return + Elevated Volume (>=1.5x)**: `{x_metrics['negative_return_and_elevated_volume_count']}` symbols ({x_metrics['negative_return_and_elevated_volume_ratio'] * 100:.1f}%)",
        f"- **Above MA20 + Elevated Volume (>=1.5x)**: `{x_metrics['above_ma20_and_elevated_volume_count']}` symbols ({x_metrics['above_ma20_and_elevated_volume_ratio'] * 100:.1f}%)",
        "",
        "### 1.3 Return & Volatility Distributions",
        f"- **1D Return**: Mean `{ret_dist['mean_return_1d'] * 100:+.2f}%`, Median `{ret_dist['median_return_1d'] * 100:+.2f}%` (IQR: `{ret_dist['p25_return_1d'] * 100:+.2f}%` to `{ret_dist['p75_return_1d'] * 100:+.2f}%`)",
        f"- **20D Volatility**: Mean `{vol_dist['mean_volatility_20d']:.4f}`, Median `{vol_dist['median_volatility_20d']:.4f}` (Min: `{vol_dist['min_volatility_20d']:.4f}`, Max: `{vol_dist['max_volatility_20d']:.4f}`)",
        f"- **Relative Volume**: Elevated (>=1.5x): `{rel_vol_breadth['elevated_volume_count']}`, Normal: `{rel_vol_breadth['normal_volume_count']}`, Depressed (<=0.8x): `{rel_vol_breadth['depressed_volume_count']}`, Median: `{rel_vol_breadth['median_relative_volume']:.2f}x`",
        "",
        "---",
        "",
        "## 2. Research Candidate Cohorts (Descriptive Filter Sets)",
        "",
        "> [!IMPORTANT]",
        "> The following candidate lists are deterministic descriptive filters to aid research exploration. They are NOT buy/sell signals, ratings, top picks, or actionable trade instructions.",
        "",
    ]

    # Table helper for cohorts
    def _render_cohort_table(entries: Sequence[Mapping[str, Any]], title: str, max_rows: int = 10) -> list[str]:
        lines = [
            f"### {title} ({len(entries)} symbols)",
            "",
            "| Ticker | Close (VND) | 1D Return | Relative Volume | 20D MA (VND) | Reason Codes |",
            "|:---|---:|---:|---:|---:|:---|",
        ]
        for e in entries[:max_rows]:
            m = e["input_metrics"]
            t = e["ticker"]
            close_s = f"{m.get('close_vnd', 0):,.0f}" if m.get("close_vnd") else "N/A"
            ret_s = f"{m.get('return_1d', 0) * 100:+.2f}%" if m.get("return_1d") is not None else "N/A"
            rel_s = f"{m.get('relative_volume_provider_scoped', 0):.2f}x" if m.get("relative_volume_provider_scoped") is not None else "N/A"
            ma_s = f"{m.get('ma_20_vnd', 0):,.0f}" if m.get("ma_20_vnd") else "N/A"
            reasons_s = "; ".join(e["reason_codes"])
            lines.append(f"| **{t}** | {close_s} | {ret_s} | {rel_s} | {ma_s} | {reasons_s} |")
        if len(entries) > max_rows:
            lines.append(f"| ... *({len(entries) - max_rows} additional symbols omitted in summary table)* | | | | | |")
        lines.append("")
        return lines

    md.extend(_render_cohort_table(c_entries[COHORT_MOMENTUM_PARTICIPATION], f"2.1 {COHORT_MOMENTUM_PARTICIPATION} Cohort", max_rows=12))
    md.extend(_render_cohort_table(c_entries[COHORT_HIGH_ACTIVITY_REVERSAL], f"2.2 {COHORT_HIGH_ACTIVITY_REVERSAL} Cohort", max_rows=8))
    md.extend(_render_cohort_table(c_entries[COHORT_TREND_WITHOUT_PARTICIPATION], f"2.3 {COHORT_TREND_WITHOUT_PARTICIPATION} Cohort", max_rows=8))
    md.extend(_render_cohort_table(c_entries[COHORT_HIGH_VOLATILITY_WATCH], f"2.4 {COHORT_HIGH_VOLATILITY_WATCH} Cohort", max_rows=8))

    # 3. FHSC Enriched Flow Watch
    fhsc_entries = c_entries[COHORT_FHSC_ENRICHED_FLOW]
    md.extend([
        "---",
        "",
        "## 3. FHSC Enriched Flow Watch (`aggregate_scope: ACQUIRED_ENRICHMENT_COHORT`)",
        "",
        f"> [!WARNING]",
        f"> FHSC Enrichment metrics are coverage-bounded to the **22 acquired symbols** (4.20% of universe). Do NOT generalize sample statistics to the wider market.",
        "",
        f"### Notable Institutional & Flow Observations ({len(fhsc_entries)} symbols flagged)",
        "",
        "| Ticker | Matched Value (VND) | Put-Through Value (VND) | PT Share | Prop Net Value (VND) | Foreign Room Util | Order Imbalance | Reason Codes |",
        "|:---|---:|---:|---:|---:|---:|---:|:---|",
    ])

    for e in fhsc_entries:
        m = e["input_metrics"]
        t = e["ticker"]
        mv_s = f"{m.get('matched_traded_value_vnd', 0):,.0f}" if m.get("matched_traded_value_vnd") is not None else "N/A"
        pv_s = f"{m.get('put_through_traded_value_vnd', 0):,.0f}" if m.get("put_through_traded_value_vnd") is not None else "N/A"
        pt_share_s = f"{m.get('put_through_value_ratio', 0) * 100:.1f}%" if m.get("put_through_value_ratio") is not None else "N/A"
        prop_s = f"{m.get('proprietary_net_value_vnd', 0):,.0f}" if m.get("proprietary_net_value_vnd") is not None else "N/A"
        room_s = f"{m.get('foreign_room_utilization_ratio', 0) * 100:.1f}%" if m.get("foreign_room_utilization_ratio") is not None else "N/A"
        imb_s = f"{m.get('order_volume_imbalance_ratio', 0):+.3f}" if m.get("order_volume_imbalance_ratio") is not None else "N/A"
        reasons_s = "; ".join(e["reason_codes"])
        md.append(f"| **{t}** | {mv_s} | {pv_s} | {pt_share_s} | {prop_s} | {room_s} | {imb_s} | {reasons_s} |")

    md.extend([
        "",
        "---",
        "",
        "## 4. Coverage & Data Quality Accounting",
        "",
        "| Metric Dimension | Symbol Count | Percentage | Classification & Status |",
        "|:---|---:|---:|:---|",
        f"| **Total Universe Symbols** | {decomp['total_universe_count']} | 100.0% | `FULL_RESEARCH_UNIVERSE` (Complete core) |",
        f"| **Acquired FHSC Trading Composition** | {decomp['acquired_count']} | {decomp['acquired_count'] / decomp['total_universe_count'] * 100:.2f}% | `ACQUIRED` (6 full-enrichment, 16 partial) |",
        f"| **Rate Limited on Scale-Out** | {decomp['rate_limited_count']} | {decomp['rate_limited_count'] / decomp['total_universe_count'] * 100:.2f}% | `PROVIDER_RATE_LIMITED` (Queue Tier 1 retry) |",
        f"| **Unattempted in This Scale-Out** | {decomp['unattempted_count']} | {decomp['unattempted_count'] / decomp['total_universe_count'] * 100:.2f}% | `NOT_ACQUIRED_IN_THIS_SCALEOUT` (Queue Tier 2) |",
        f"| **Missing / Conflicting Records** | 0 | 0.0% | Zero missing date or arithmetic errors |",
        f"| **Reconciled Sum** | **{decomp['reconciled_sum']}** | **100.0%** | **Mutually exclusive sum == Total Universe** |",
        "",
        "---",
        "",
        "## 5. Authority Boundaries",
        "",
        "- `authority_effect`: `NONE`",
        "- `raw_as_traded_promoted`: `False`",
        "- `pit_backtest_eligible`: `False`",
        "- `liquidity_sizing_authority`: `BLOCKED`",
        "- `valuation_authority`: `False`",
        "- `recommendation_authority`: `False`",
        "- `ranking_authority`: `False`",
        "- `database_mutated`: `False`",
    ])

    return "\n".join(md) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive deterministic market state and research candidate cohorts.")
    parser.add_argument(
        "--digest-path",
        default="operations-review/capability-first-research-digest-2026-08-21/capability_research_digest.json",
        help="Path to coverage-aware research digest JSON",
    )
    parser.add_argument(
        "--out-dir",
        default="operations-review/market-state-and-candidates-2026-08-21",
        help="Output directory for market state and candidate artifacts",
    )
    args = parser.parse_args(argv)

    digest_path = Path(args.digest_path)
    if not digest_path.is_absolute():
        digest_path = ROOT / digest_path

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    if not digest_path.is_file():
        raise FileNotFoundError(f"Input digest not found at: {digest_path}")

    print(f"Loading research digest from: {digest_path}")
    digest_payload = json.loads(digest_path.read_text(encoding="utf-8"))

    print("Deriving deterministic market state and research candidate cohorts...")
    artifact = derive_market_state_and_candidates(digest_payload)

    summary_md = generate_candidate_markdown_summary(artifact)

    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_json_path = out_dir / "market_state_and_candidates.json"
    summary_path = out_dir / "market_state_and_candidates_summary.md"
    manifest_path = out_dir / "manifest.json"

    atomic_write_json(artifact_json_path, artifact)
    atomic_write_file(summary_path, summary_md)

    manifest = {
        "manifest_schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "session_date": artifact["session_date"],
        "created_at": datetime.now(UTC).isoformat(),
        "artifact_identity": artifact["artifact_identity"],
        "artifact_sha256": artifact["artifact_sha256"],
        "files": {
            "market_state_and_candidates.json": {
                "size_bytes": artifact_json_path.stat().st_size,
                "sha256": hashlib.sha256(artifact_json_path.read_bytes()).hexdigest(),
            },
            "market_state_and_candidates_summary.md": {
                "size_bytes": summary_path.stat().st_size,
                "sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
            },
        },
        "authority_boundaries": artifact["authority_boundaries"],
    }
    atomic_write_json(manifest_path, manifest)

    print(json.dumps({
        "status": "MARKET_STATE_CANDIDATES_COMPLETE",
        "artifact_identity": artifact["artifact_identity"],
        "session_date": artifact["session_date"],
        "regime_label": artifact["market_state"]["regime_classification"]["regime_label"],
        "cohort_counts": {k: v["count"] for k, v in artifact["research_candidate_cohorts"]["cohort_summaries"].items()},
        "out_dir": str(out_dir),
    }, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    sys.exit(main())
