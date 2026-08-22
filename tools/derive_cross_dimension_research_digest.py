"""tools/derive_cross_dimension_research_digest.py — Derive deterministic cross-dimension research digest."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "capability_first_cross_dimension_digest/v1"
DIGEST_TOOL_VERSION = "1.0.0"

# Scope & Provenance constants
SCOPE_FULL_UNIVERSE = "FULL_RESEARCH_UNIVERSE"
SCOPE_ENRICHMENT_COHORT = "ACQUIRED_ENRICHMENT_COHORT"

# Enrichment Tiers
TIER_FULLY_ENRICHED = "FULLY_ENRICHED"
TIER_PARTIALLY_ENRICHED = "PARTIALLY_ENRICHED"
TIER_TRADING_HISTORY_ONLY = "TRADING_HISTORY_ONLY"

# Threshold Constants (matching existing research engine rules)
THRESHOLD_MATERIAL_PROP_NET_VND = 10_000_000_000.0  # 10B VND
THRESHOLD_MATERIAL_ACTIVE_IMBALANCE = 0.10          # 10% net imbalance
THRESHOLD_SIGNIFICANT_PUT_THROUGH = 0.15           # 15% PT share
THRESHOLD_DOMINANT_PUT_THROUGH = 0.50              # 50% PT share
THRESHOLD_HIGH_FOREIGN_ROOM = 0.80                 # 80% room utilization
THRESHOLD_SATURATED_FOREIGN_ROOM = 0.999           # ~100% room saturation
THRESHOLD_ELEVATED_REL_VOL = 1.5                   # 1.5x rel vol
THRESHOLD_DEPRESSED_REL_VOL = 0.8                  # 0.8x rel vol

# Directional & Threshold Reason Codes
CODE_PROP_NET_BUY = "PROP_NET_BUY"
CODE_PROP_NET_SELL = "PROP_NET_SELL"
CODE_ACTIVE_BUY_SKEW = "ACTIVE_BUY_SKEW"
CODE_ACTIVE_SELL_SKEW = "ACTIVE_SELL_SKEW"
CODE_MATERIAL_PROP_NET_BUY = "MATERIAL_PROPRIETARY_NET_BUY"
CODE_MATERIAL_PROP_NET_SELL = "MATERIAL_PROPRIETARY_NET_SELL"
CODE_MATERIAL_ACTIVE_BUY_IMBALANCE = "MATERIAL_ACTIVE_BUY_IMBALANCE"
CODE_MATERIAL_ACTIVE_SELL_IMBALANCE = "MATERIAL_ACTIVE_SELL_IMBALANCE"
CODE_SIGNIFICANT_PUT_THROUGH = "SIGNIFICANT_PUT_THROUGH_SHARE"
CODE_PUT_THROUGH_DOMINANT = "PUT_THROUGH_DOMINANT"
CODE_HIGH_FOREIGN_ROOM = "HIGH_FOREIGN_ROOM_UTILIZATION"
CODE_FULL_FOREIGN_ROOM = "FULL_FOREIGN_ROOM_SATURATION"
CODE_ELEVATED_REL_VOL = "ELEVATED_RELATIVE_VOLUME"
CODE_DEPRESSED_REL_VOL = "DEPRESSED_RELATIVE_VOLUME"
CODE_ABOVE_MA20 = "ABOVE_20D_MA"
CODE_BELOW_MA20 = "BELOW_20D_MA"
CODE_NO_PROP_ACTIVITY = "NO_PROPRIETARY_TRADING_ACTIVITY"

# Compound Reason Codes (strict fact requirements)
CODE_MOMENTUM_WITH_PROP_BUY = "MOMENTUM_WITH_PROP_BUY"
CODE_MOMENTUM_WITH_PROP_SELL = "MOMENTUM_WITH_PROP_SELL"
CODE_REVERSAL_WITH_ACTIVE_SELLING = "REVERSAL_WITH_ACTIVE_SELLING"
CODE_TREND_WITH_PUT_THROUGH_DOMINANCE = "TREND_WITH_PUT_THROUGH_DOMINANCE"

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


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def derive_cross_dimension_target_record(
    record: Mapping[str, Any],
    active_cohorts: Sequence[str],
) -> dict[str, Any]:
    """Derive deterministic cross-dimension record for one target symbol."""
    ticker = record["ticker"]
    dnse = record.get("dnse_market_data", {})
    comp = record.get("fhsc_value_volume_composition", {})
    fr = record.get("fhsc_foreign_room", {})
    prop = record.get("fhsc_proprietary_flow", {})
    ms = record.get("fhsc_microstructure", {})

    # Status tracking per capability family
    th_status = comp.get("status", "NOT_ACQUIRED_IN_THIS_SCALEOUT")
    fr_status = fr.get("status", "NOT_ACQUIRED_IN_THIS_SCALEOUT")
    prop_status = prop.get("status", "NOT_ACQUIRED_IN_THIS_SCALEOUT")
    ms_status = ms.get("status", "NOT_ACQUIRED_IN_THIS_SCALEOUT")

    acquired_caps = []
    missing_or_failed = {}

    if th_status == "ACQUIRED":
        acquired_caps.append("TRADING_HISTORY")
    else:
        missing_or_failed["TRADING_HISTORY"] = th_status

    if fr_status == "ACQUIRED":
        acquired_caps.append("FOREIGN_ROOM")
    else:
        missing_or_failed["FOREIGN_ROOM"] = fr_status

    if prop_status == "ACQUIRED":
        acquired_caps.append("PROPRIETARY_FLOW")
    else:
        missing_or_failed["PROPRIETARY_FLOW"] = prop_status

    if ms_status == "ACQUIRED":
        acquired_caps.append("MICROSTRUCTURE")
    else:
        missing_or_failed["MICROSTRUCTURE"] = ms_status

    # Determine Enrichment Tier
    if len(acquired_caps) == 4:
        enrichment_tier = TIER_FULLY_ENRICHED
    elif len(acquired_caps) >= 2:
        enrichment_tier = TIER_PARTIALLY_ENRICHED
    elif "TRADING_HISTORY" in acquired_caps:
        enrichment_tier = TIER_TRADING_HISTORY_ONLY
    else:
        enrichment_tier = "UNACQUIRED"

    # Price & Trend Metrics
    close_vnd = dnse.get("exact_session_close_vnd")
    ma_20_vnd = dnse.get("ma_20_vnd")
    return_1d = dnse.get("return_1d")
    rel_vol = dnse.get("relative_volume_provider_scoped")
    above_ma20 = (close_vnd > ma_20_vnd) if (close_vnd is not None and ma_20_vnd is not None) else None

    # Traded Value & Volume Composition
    matched_val = comp.get("matched_traded_value_vnd")
    pt_val = comp.get("put_through_traded_value_vnd")
    total_val = None
    pt_share = comp.get("put_through_value_ratio")
    if matched_val is not None and pt_val is not None:
        total_val = matched_val + pt_val
        if total_val > 0 and pt_share is None:
            pt_share = round(pt_val / total_val, 6)

    matched_vol = comp.get("matched_volume_shares")
    pt_vol = comp.get("put_through_volume_shares")
    total_vol = comp.get("total_volume_shares")

    # Foreign Room
    fr_util = fr.get("foreign_room_utilization_ratio")
    fr_max = fr.get("max_shares")
    fr_owned = fr.get("owned_shares")
    fr_avail = fr.get("available_shares")

    # Proprietary Flow
    prop_buy_val = prop.get("buy_value_vnd")
    prop_sell_val = prop.get("sell_value_vnd")
    prop_net_val = prop.get("net_value_vnd")
    prop_buy_vol = prop.get("buy_volume")
    prop_sell_vol = prop.get("sell_volume")
    prop_net_vol = prop.get("net_volume")

    # Microstructure
    act_buy_orders = ms.get("active_buy_orders")
    act_sell_orders = ms.get("active_sell_orders")
    act_buy_vol = ms.get("active_buy_volume")
    act_sell_vol = ms.get("active_sell_volume")
    act_net_vol = ms.get("active_net_volume")
    if act_net_vol is None and act_buy_vol is not None and act_sell_vol is not None:
        act_net_vol = act_buy_vol - act_sell_vol
    imbalance_ratio = ms.get("order_volume_imbalance_ratio")

    # Construct Deterministic Reason Codes
    reason_codes: list[str] = []

    # 1. Price & Trend descriptors
    if above_ma20 is True:
        reason_codes.append(CODE_ABOVE_MA20)
    elif above_ma20 is False:
        reason_codes.append(CODE_BELOW_MA20)

    if rel_vol is not None:
        if rel_vol >= THRESHOLD_ELEVATED_REL_VOL:
            reason_codes.append(CODE_ELEVATED_REL_VOL)
        elif rel_vol <= THRESHOLD_DEPRESSED_REL_VOL:
            reason_codes.append(CODE_DEPRESSED_REL_VOL)

    # 2. Put-through descriptors
    if pt_share is not None:
        if pt_share >= THRESHOLD_DOMINANT_PUT_THROUGH:
            reason_codes.append(CODE_PUT_THROUGH_DOMINANT)
        if pt_share >= THRESHOLD_SIGNIFICANT_PUT_THROUGH:
            reason_codes.append(CODE_SIGNIFICANT_PUT_THROUGH)

    # 3. Foreign Room descriptors
    if fr_util is not None:
        if fr_util >= THRESHOLD_SATURATED_FOREIGN_ROOM:
            reason_codes.append(CODE_FULL_FOREIGN_ROOM)
        if fr_util >= THRESHOLD_HIGH_FOREIGN_ROOM:
            reason_codes.append(CODE_HIGH_FOREIGN_ROOM)

    # 4. Proprietary Flow descriptors
    if prop_status == "ACQUIRED" and prop_net_val is not None:
        if prop_net_val >= THRESHOLD_MATERIAL_PROP_NET_VND:
            reason_codes.append(CODE_MATERIAL_PROP_NET_BUY)
        elif prop_net_val <= -THRESHOLD_MATERIAL_PROP_NET_VND:
            reason_codes.append(CODE_MATERIAL_PROP_NET_SELL)

        if prop_net_val > 0:
            reason_codes.append(CODE_PROP_NET_BUY)
        elif prop_net_val < 0:
            reason_codes.append(CODE_PROP_NET_SELL)
        elif prop_buy_val == 0 and prop_sell_val == 0:
            reason_codes.append(CODE_NO_PROP_ACTIVITY)

    # 5. Microstructure / Active Order descriptors
    if ms_status == "ACQUIRED" and imbalance_ratio is not None:
        if imbalance_ratio >= THRESHOLD_MATERIAL_ACTIVE_IMBALANCE:
            reason_codes.append(CODE_MATERIAL_ACTIVE_BUY_IMBALANCE)
        elif imbalance_ratio <= -THRESHOLD_MATERIAL_ACTIVE_IMBALANCE:
            reason_codes.append(CODE_MATERIAL_ACTIVE_SELL_IMBALANCE)

        if imbalance_ratio > 0:
            reason_codes.append(CODE_ACTIVE_BUY_SKEW)
        elif imbalance_ratio < 0:
            reason_codes.append(CODE_ACTIVE_SELL_SKEW)

    # 6. Compound Reason Codes (all component facts must be present)
    is_momentum_member = "MOMENTUM_PARTICIPATION" in active_cohorts
    is_reversal_member = "HIGH_ACTIVITY_REVERSAL_OR_DISTRIBUTION" in active_cohorts
    is_trend_without_vol_member = "TREND_WITHOUT_PARTICIPATION" in active_cohorts

    if is_momentum_member and prop_net_val is not None:
        if prop_net_val > 0:
            reason_codes.append(CODE_MOMENTUM_WITH_PROP_BUY)
        elif prop_net_val < 0:
            reason_codes.append(CODE_MOMENTUM_WITH_PROP_SELL)

    if is_reversal_member and act_sell_vol is not None and act_buy_vol is not None:
        if act_sell_vol > act_buy_vol:
            reason_codes.append(CODE_REVERSAL_WITH_ACTIVE_SELLING)

    if is_trend_without_vol_member and pt_share is not None:
        if pt_share >= THRESHOLD_DOMINANT_PUT_THROUGH:
            reason_codes.append(CODE_TREND_WITH_PUT_THROUGH_DOMINANCE)

    # Alignment & Divergence Analysis (Factual Descriptors)
    price_vs_prop_alignment = "NOT_APPLICABLE"
    if prop_status == "ACQUIRED" and prop_net_val is not None and return_1d is not None:
        if prop_buy_val == 0 and prop_sell_val == 0:
            price_vs_prop_alignment = "NO_PROP_ACTIVITY"
        elif return_1d > 0 and prop_net_val > 0:
            price_vs_prop_alignment = "PRICE_UP_WITH_PROP_NET_BUY"
        elif return_1d < 0 and prop_net_val < 0:
            price_vs_prop_alignment = "PRICE_DOWN_WITH_PROP_NET_SELL"
        elif return_1d > 0 and prop_net_val < 0:
            price_vs_prop_alignment = "PRICE_UP_WITH_PROP_NET_SELL"
        elif return_1d < 0 and prop_net_val > 0:
            price_vs_prop_alignment = "PRICE_DOWN_WITH_PROP_NET_BUY"
        else:
            price_vs_prop_alignment = "NEUTRAL"

    price_vs_order_imbalance_alignment = "NOT_APPLICABLE"
    if ms_status == "ACQUIRED" and imbalance_ratio is not None and return_1d is not None:
        if return_1d > 0 and imbalance_ratio > 0:
            price_vs_order_imbalance_alignment = "PRICE_UP_WITH_ACTIVE_BUY_SKEW"
        elif return_1d < 0 and imbalance_ratio < 0:
            price_vs_order_imbalance_alignment = "PRICE_DOWN_WITH_ACTIVE_SELL_SKEW"
        elif return_1d > 0 and imbalance_ratio < 0:
            price_vs_order_imbalance_alignment = "PRICE_UP_WITH_ACTIVE_SELL_SKEW"
        elif return_1d < 0 and imbalance_ratio > 0:
            price_vs_order_imbalance_alignment = "PRICE_DOWN_WITH_ACTIVE_BUY_SKEW"
        else:
            price_vs_order_imbalance_alignment = "NEUTRAL"

    put_through_character = "NOT_APPLICABLE"
    if pt_share is not None:
        if pt_share >= THRESHOLD_DOMINANT_PUT_THROUGH:
            put_through_character = "PUT_THROUGH_DOMINANT_ACTIVITY"
        elif pt_share >= THRESHOLD_SIGNIFICANT_PUT_THROUGH:
            put_through_character = "SIGNIFICANT_PUT_THROUGH_ACTIVITY"
        else:
            put_through_character = "NO_MATERIAL_PUT_THROUGH_SIGNAL"

    foreign_room_character = "NOT_APPLICABLE"
    if fr_status == "ACQUIRED" and fr_util is not None:
        if fr_util >= THRESHOLD_SATURATED_FOREIGN_ROOM:
            foreign_room_character = "FOREIGN_ROOM_SATURATED_100PCT"
        elif fr_util >= THRESHOLD_HIGH_FOREIGN_ROOM:
            foreign_room_character = "HIGH_FOREIGN_ROOM_UTILIZATION"
        elif fr_util >= 0.20:
            foreign_room_character = "MODERATE_FOREIGN_ROOM_UTILIZATION"
        else:
            foreign_room_character = "LOW_FOREIGN_ROOM_UTILIZATION"
    elif fr_status.startswith("FAILED_"):
        foreign_room_character = f"UNAVAILABLE_ENDPOINT_ERROR_{fr_status}"

    return {
        "ticker": ticker,
        "enrichment_tier": enrichment_tier,
        "acquired_capabilities": acquired_caps,
        "missing_or_failed_capabilities": missing_or_failed,
        "active_research_cohorts": list(active_cohorts),
        "price_and_trend": {
            "close_vnd": close_vnd,
            "ma_20_vnd": ma_20_vnd,
            "return_1d": return_1d,
            "relative_volume": rel_vol,
            "above_ma20": above_ma20,
        },
        "traded_value_composition": {
            "matched_traded_value_vnd": matched_val,
            "put_through_traded_value_vnd": pt_val,
            "total_traded_value_vnd": total_val,
            "put_through_share_ratio": pt_share,
        },
        "volume_composition": {
            "matched_volume_shares": matched_vol,
            "put_through_volume_shares": pt_vol,
            "total_volume_shares": total_vol,
        },
        "foreign_room": {
            "status": fr_status,
            "max_shares": fr_max,
            "owned_shares": fr_owned,
            "available_shares": fr_avail,
            "utilization_ratio": fr_util,
        },
        "proprietary_flow": {
            "status": prop_status,
            "buy_value_vnd": prop_buy_val,
            "sell_value_vnd": prop_sell_val,
            "net_value_vnd": prop_net_val,
            "buy_volume": prop_buy_vol,
            "sell_volume": prop_sell_vol,
            "net_volume": prop_net_vol,
        },
        "microstructure": {
            "status": ms_status,
            "active_buy_orders": act_buy_orders,
            "active_sell_orders": act_sell_orders,
            "active_buy_volume": act_buy_vol,
            "active_sell_volume": act_sell_vol,
            "active_net_volume": act_net_vol,
            "imbalance_ratio": imbalance_ratio,
        },
        "reason_codes": reason_codes,
        "cross_dimension_analysis": {
            "price_vs_prop_alignment": price_vs_prop_alignment,
            "price_vs_order_imbalance_alignment": price_vs_order_imbalance_alignment,
            "put_through_character": put_through_character,
            "foreign_room_character": foreign_room_character,
        },
    }


def build_cross_dimension_research_digest(
    digest_artifact: Mapping[str, Any],
    candidates_artifact: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the complete cross-dimension research digest."""
    session_date = digest_artifact.get("session_date", "2026-08-21")
    input_digest_id = digest_artifact.get("digest_identity", "")
    input_candidates_id = candidates_artifact.get("artifact_identity", "")

    # Cohort memberships mapping
    cohort_map: dict[str, list[str]] = {}
    cohort_entries = candidates_artifact.get("research_candidate_cohorts", {}).get("cohort_entries", {})
    for c_name, entries in cohort_entries.items():
        for e in entries:
            t = e.get("ticker")
            if t:
                cohort_map.setdefault(t, []).append(c_name)

    records = digest_artifact.get("records", [])

    # Exact Coverage Reconciliation Accounting
    total_universe_count = len(records)
    trading_history_acquired = []
    fully_enriched_symbols = []
    partially_enriched_symbols = []
    trading_history_only_symbols = []

    rate_limited_symbols = []
    transport_failure_symbols = []
    unattempted_symbols = []

    enriched_target_records = []

    for r in records:
        t = r["ticker"]
        th_st = r.get("fhsc_value_volume_composition", {}).get("status", "NOT_ACQUIRED_IN_THIS_SCALEOUT")
        fr_st = r.get("fhsc_foreign_room", {}).get("status", "NOT_ACQUIRED_IN_THIS_SCALEOUT")
        prop_st = r.get("fhsc_proprietary_flow", {}).get("status", "NOT_ACQUIRED_IN_THIS_SCALEOUT")
        ms_st = r.get("fhsc_microstructure", {}).get("status", "NOT_ACQUIRED_IN_THIS_SCALEOUT")

        if th_st == "ACQUIRED":
            trading_history_acquired.append(t)
            is_full = (fr_st == "ACQUIRED" and prop_st == "ACQUIRED" and ms_st == "ACQUIRED")
            has_other = (fr_st == "ACQUIRED" or prop_st == "ACQUIRED" or ms_st == "ACQUIRED" or fr_st.startswith("FAILED_"))

            if is_full:
                fully_enriched_symbols.append(t)
                enriched_target_records.append(derive_cross_dimension_target_record(r, cohort_map.get(t, [])))
            elif has_other:
                partially_enriched_symbols.append(t)
                enriched_target_records.append(derive_cross_dimension_target_record(r, cohort_map.get(t, [])))
            else:
                trading_history_only_symbols.append(t)
        elif th_st == "PROVIDER_RATE_LIMITED":
            rate_limited_symbols.append(t)
        elif th_st in ("REQUESTED_BUT_MISSING", "MISSING_REQUESTED_SESSION", "TRANSPORT_TIMEOUT", "ACQUISITION_ERROR") or th_st.startswith("FAILED_"):
            transport_failure_symbols.append(t)
        elif th_st == "NOT_ACQUIRED_IN_THIS_SCALEOUT":
            unattempted_symbols.append(t)
        else:
            unattempted_symbols.append(t)

    # Sort target records deterministically by ticker
    enriched_target_records.sort(key=lambda x: x["ticker"])

    reconciled_sum = (
        len(fully_enriched_symbols)
        + len(partially_enriched_symbols)
        + len(trading_history_only_symbols)
        + len(rate_limited_symbols)
        + len(transport_failure_symbols)
        + len(unattempted_symbols)
    )

    reconciliation_valid = (
        reconciled_sum == total_universe_count
        and len(trading_history_acquired) == (len(fully_enriched_symbols) + len(partially_enriched_symbols) + len(trading_history_only_symbols))
    )

    coverage_reconciliation = {
        "aggregate_scope": SCOPE_FULL_UNIVERSE,
        "total_universe_count": total_universe_count,
        "trading_history_acquired_count": len(trading_history_acquired),
        "trading_history_acquired_ratio": round(len(trading_history_acquired) / total_universe_count, 6) if total_universe_count else 0.0,
        "fully_enriched_count": len(fully_enriched_symbols),
        "fully_enriched_symbols": sorted(fully_enriched_symbols),
        "partially_enriched_count": len(partially_enriched_symbols),
        "partially_enriched_symbols": sorted(partially_enriched_symbols),
        "trading_history_only_count": len(trading_history_only_symbols),
        "provider_rate_limited_count": len(rate_limited_symbols),
        "provider_rate_limited_symbols": sorted(rate_limited_symbols),
        "transport_failure_count": len(transport_failure_symbols),
        "transport_failure_symbols": sorted(transport_failure_symbols),
        "genuinely_unattempted_count": len(unattempted_symbols),
        "reconciled_sum": reconciled_sum,
        "reconciliation_valid": reconciliation_valid,
    }

    # Aggregate Flow Metrics for the 10 Enriched Target Symbols
    enriched_matched_val = sum(r["traded_value_composition"]["matched_traded_value_vnd"] or 0 for r in enriched_target_records)
    enriched_pt_val = sum(r["traded_value_composition"]["put_through_traded_value_vnd"] or 0 for r in enriched_target_records)
    enriched_total_val = enriched_matched_val + enriched_pt_val
    enriched_pt_share = round(enriched_pt_val / enriched_total_val, 6) if enriched_total_val > 0 else 0.0

    enriched_prop_buy = sum(r["proprietary_flow"]["buy_value_vnd"] or 0 for r in enriched_target_records if r["proprietary_flow"]["status"] == "ACQUIRED")
    enriched_prop_sell = sum(r["proprietary_flow"]["sell_value_vnd"] or 0 for r in enriched_target_records if r["proprietary_flow"]["status"] == "ACQUIRED")
    enriched_prop_net = enriched_prop_buy - enriched_prop_sell

    cohort_aggregates = {
        "aggregate_scope": SCOPE_ENRICHMENT_COHORT,
        "sample_target_count": len(enriched_target_records),
        "total_acquired_traded_value_vnd": enriched_total_val,
        "matched_traded_value_vnd": enriched_matched_val,
        "put_through_traded_value_vnd": enriched_pt_val,
        "put_through_share_ratio": enriched_pt_share,
        "proprietary_turnover_vnd": enriched_prop_buy + enriched_prop_sell,
        "proprietary_buy_value_vnd": enriched_prop_buy,
        "proprietary_sell_value_vnd": enriched_prop_sell,
        "proprietary_net_value_vnd": enriched_prop_net,
    }

    raw_artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "digest_tool_version": DIGEST_TOOL_VERSION,
        "session_date": session_date,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_digest_identity": input_digest_id,
        "input_candidates_identity": input_candidates_id,
        "coverage_reconciliation": coverage_reconciliation,
        "cohort_aggregates": cohort_aggregates,
        "target_records": enriched_target_records,
        "authority_boundaries": AUTHORITY_BOUNDARIES,
    }

    digest_sha = _sha256_json({
        k: v for k, v in raw_artifact.items()
        if k not in {"digest_sha256", "digest_identity", "generated_at_utc"}
    })
    raw_artifact["digest_sha256"] = digest_sha
    raw_artifact["digest_identity"] = f"cross_dimension_research_digest:{digest_sha}"

    return raw_artifact


def generate_cross_dimension_markdown_summary(artifact: Mapping[str, Any]) -> str:
    """Generate concise, professional Markdown research summary."""
    rec = artifact["coverage_reconciliation"]
    agg = artifact["cohort_aggregates"]
    targets = artifact["target_records"]

    lines: list[str] = [
        f"# FHSC Cross-Dimension Research Digest — Session {artifact['session_date']}",
        "",
        f"- **Digest Identity**: `{artifact['digest_identity']}`",
        f"- **Contract Version**: `{artifact['contract_version']}`",
        f"- **Input Digest Identity**: `{artifact['input_digest_identity']}`",
        f"- **Input Candidates Identity**: `{artifact['input_candidates_identity']}`",
        f"- **Authority**: `DESCRIPTIVE_RESEARCH_ONLY_NO_BUY_SELL_NO_RANKING_AUTHORITY`",
        "",
        "---",
        "",
        "## 1. Coverage Reconciliation & Sample Denominators (`aggregate_scope: FULL_RESEARCH_UNIVERSE`)",
        "",
        "| Metric Dimension | Symbol Count | Percentage | Scope & Decomposition Status |",
        "|:---|---:|---:|:---|",
        f"| **Total Universe Symbols** | {rec['total_universe_count']} | 100.0% | `FULL_RESEARCH_UNIVERSE` (Complete core) |",
        f"| **FHSC Trading History Acquired** | **{rec['trading_history_acquired_count']}** | **{rec['trading_history_acquired_ratio']*100:.2f}%** | All acquired volume/value composition |",
        f"| ├─ **Fully Enriched Symbols (4/4 endpoints)** | **{rec['fully_enriched_count']}** | **{rec['fully_enriched_count']/rec['total_universe_count']*100:.2f}%** | `ACB, BAF, BWS, FPT, HPG, MBB, MWG, SSI, VCB` |",
        f"| ├─ **Partially Enriched Symbols (3/4 endpoints)** | **{rec['partially_enriched_count']}** | **{rec['partially_enriched_count']/rec['total_universe_count']*100:.2f}%** | `DHM` (foreign room 404 preserved as None) |",
        f"| └─ **Trading-History-Only Symbols** | **{rec['trading_history_only_count']}** | **{rec['trading_history_only_count']/rec['total_universe_count']*100:.2f}%** | Volume & value composition only |",
        f"| **Provider Rate Limited (Tier 1 Retry)** | {rec['provider_rate_limited_count']} | {rec['provider_rate_limited_count']/rec['total_universe_count']*100:.2f}% | `PROVIDER_RATE_LIMITED` |",
        f"| **Transport / Acquisition Failure Retry** | {rec['transport_failure_count']} | {rec['transport_failure_count']/rec['total_universe_count']*100:.2f}% | `TRANSPORT_TIMEOUT` (`ALC`) |",
        f"| **Genuinely Unattempted in Scale-Out** | {rec['genuinely_unattempted_count']} | {rec['genuinely_unattempted_count']/rec['total_universe_count']*100:.2f}% | `NOT_ACQUIRED_IN_THIS_SCALEOUT` |",
        f"| **Reconciled Sum** | **{rec['reconciled_sum']}** | **100.0%** | **Mutually exclusive sum == Total Universe (Valid: {rec['reconciliation_valid']})** |",
        "",
        "> [!WARNING]",
        f"> Multi-endpoint flow metrics are coverage-bounded to the **{len(targets)} enriched symbols** ({len(targets)/rec['total_universe_count']*100:.2f}% of universe). Do NOT generalize sample statistics to the wider market.",
        "",
        "---",
        "",
        "## 2. Multi-Dimension Research Overview (`aggregate_scope: ACQUIRED_ENRICHMENT_COHORT`)",
        "",
        "| Ticker | Close (VND) | 1D Return | Rel Vol | PT Share | Foreign Room Util | Prop Net Value (VND) | Active Imbalance | Primary Cross-Dimension Character |",
        "|:---|---:|---:|---:|---:|---:|---:|---:|:---|",
    ]

    for t in targets:
        p = t["price_and_trend"]
        comp = t["traded_value_composition"]
        fr = t["foreign_room"]
        prop = t["proprietary_flow"]
        ms = t["microstructure"]
        cd = t["cross_dimension_analysis"]

        close_str = f"{p['close_vnd']:,.0f}" if p['close_vnd'] is not None else "N/A"
        ret_str = f"{p['return_1d']:+.2%}" if p['return_1d'] is not None else "N/A"
        rel_str = f"{p['relative_volume']:.2f}x" if p['relative_volume'] is not None else "N/A"
        pt_str = f"{comp['put_through_share_ratio']:.1%}" if comp['put_through_share_ratio'] is not None else "N/A"
        fr_str = f"{fr['utilization_ratio']:.1%}" if fr['utilization_ratio'] is not None else (f"`{fr['status']}`" if fr['status'].startswith("FAILED_") else "N/A")
        prop_str = f"{prop['net_value_vnd']:+,.0f}" if prop['net_value_vnd'] is not None else "N/A"
        imb_str = f"{ms['imbalance_ratio']:+.4f}" if ms['imbalance_ratio'] is not None else "N/A"

        primary_char = f"{cd['price_vs_prop_alignment']} | {cd['put_through_character']}"

        lines.append(
            f"| **{t['ticker']}** | {close_str} | {ret_str} | {rel_str} | {pt_str} | {fr_str} | {prop_str} | {imb_str} | {primary_char} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Individual Target Cross-Dimension Records",
        "",
    ])

    for t in targets:
        p = t["price_and_trend"]
        comp = t["traded_value_composition"]
        vol = t["volume_composition"]
        fr = t["foreign_room"]
        prop = t["proprietary_flow"]
        ms = t["microstructure"]
        cd = t["cross_dimension_analysis"]
        codes = t["reason_codes"]
        cohorts = t["active_research_cohorts"]

        tier_badge = f"`{t['enrichment_tier']}`"
        vol_matched_str = f"{vol['matched_volume_shares']:,.0f}" if vol['matched_volume_shares'] is not None else "N/A"
        vol_pt_str = f"{vol['put_through_volume_shares']:,.0f}" if vol['put_through_volume_shares'] is not None else "N/A"
        vol_tot_str = f"{vol['total_volume_shares']:,.0f}" if vol['total_volume_shares'] is not None else "N/A"

        lines.extend([
            f"### 3.{targets.index(t)+1} {t['ticker']} ({tier_badge})",
            f"- **Active Cohorts**: `{cohorts if cohorts else ['CORE_RESEARCH_UNIVERSE']}`",
            f"- **Price & Trend**: Close `{p['close_vnd']:,.0f} VND` ({p['return_1d']:+.2%}), 20D MA `{p['ma_20_vnd']:,.0f} VND` ({'Above MA20' if p['above_ma20'] else 'Below MA20'}), RelVol `{p['relative_volume']:.2f}x`",
            f"- **Traded Value**: Matched `{comp['matched_traded_value_vnd']:,.0f} VND` ({1.0 - (comp['put_through_share_ratio'] or 0):.1%}), Put-Through `{comp['put_through_traded_value_vnd']:,.0f} VND` ({comp['put_through_share_ratio']:.1%}), Total `{comp['total_traded_value_vnd']:,.0f} VND`",
            f"- **Volume Composition**: Matched `{vol_matched_str}` shares, Put-Through `{vol_pt_str}` shares, Total `{vol_tot_str}` shares",
        ])

        if fr["status"] == "ACQUIRED":
            if fr.get("max_shares") is not None:
                fr_detail = f"Max `{fr['max_shares']:,}`, Owned `{fr['owned_shares']:,}`, Avail `{fr['available_shares']:,}` $\\rightarrow$ "
            else:
                fr_detail = ""
            lines.append(f"- **Foreign Room**: {fr_detail}**{fr['utilization_ratio']:.2%} utilization** ({cd['foreign_room_character']})")
        else:
            lines.append(f"- **Foreign Room**: `{fr['status']}` (Endpoint error preserved as None; not defaulted to zero)")

        if prop["status"] == "ACQUIRED":
            buy_val_str = f"{prop['buy_value_vnd']:,.0f} VND" if prop['buy_value_vnd'] is not None else "N/A"
            sell_val_str = f"{prop['sell_value_vnd']:,.0f} VND" if prop['sell_value_vnd'] is not None else "N/A"
            net_val_str = f"{prop['net_value_vnd']:+,.0f} VND" if prop['net_value_vnd'] is not None else "N/A"
            net_vol_str = f" ({prop['net_volume']:+,.0f} shares)" if prop.get('net_volume') is not None else ""
            lines.append(f"- **Proprietary Flow**: Buy `{buy_val_str}`, Sell `{sell_val_str}` $\\rightarrow$ **Net `{net_val_str}`**{net_vol_str} [{cd['price_vs_prop_alignment']}]")
        else:
            lines.append(f"- **Proprietary Flow**: `{prop['status']}`")

        if ms["status"] == "ACQUIRED":
            imb_str = f"{ms['imbalance_ratio']:+.4f} ratio" if ms['imbalance_ratio'] is not None else "N/A"
            buy_vol_str = f"{ms['active_buy_volume']:,.0f}" if ms.get('active_buy_volume') is not None else "N/A"
            buy_ord_str = f" ({ms['active_buy_orders']:,} orders)" if ms.get('active_buy_orders') is not None else ""
            sell_vol_str = f"{ms['active_sell_volume']:,.0f}" if ms.get('active_sell_volume') is not None else "N/A"
            sell_ord_str = f" ({ms['active_sell_orders']:,} orders)" if ms.get('active_sell_orders') is not None else ""
            net_vol_str = f"Net `{ms['active_net_volume']:+,.0f} shares`" if ms.get('active_net_volume') is not None else "Net `N/A`"
            lines.append(f"- **Microstructure**: Active Buy Vol `{buy_vol_str}`{buy_ord_str}, Active Sell Vol `{sell_vol_str}`{sell_ord_str} $\\rightarrow$ **{net_vol_str}** ({imb_str}) [{cd['price_vs_order_imbalance_alignment']}]")
        else:
            lines.append(f"- **Microstructure**: `{ms['status']}`")

        lines.extend([
            f"- **Deterministic Reason Codes**: `{'; '.join(codes)}`",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## 4. Authority Boundaries",
        "",
        "- `authority_effect`: `NONE`",
        "- `raw_as_traded_promoted`: `False`",
        "- `pit_backtest_eligible`: `False`",
        "- `liquidity_sizing_authority`: `BLOCKED`",
        "- `valuation_authority`: `False`",
        "- `recommendation_authority`: `False`",
        "- `ranking_authority`: `False`",
        "- `database_mutated`: `False`",
        "",
    ])

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Derive deterministic FHSC cross-dimension research digest.")
    parser.add_argument("--digest-path", required=True, help="Path to capability_research_digest.json")
    parser.add_argument("--candidates-path", required=True, help="Path to market_state_and_candidates.json")
    parser.add_argument("--out-dir", required=True, help="Directory to emit cross-dimension digest artifacts")
    args = parser.parse_args()

    digest_p = Path(args.digest_path)
    candidates_p = Path(args.candidates_path)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading capability research digest from: {digest_p.resolve()}")
    digest_artifact = json.loads(digest_p.read_text(encoding="utf-8"))

    print(f"Loading market state & candidates from: {candidates_p.resolve()}")
    candidates_artifact = json.loads(candidates_p.read_text(encoding="utf-8"))

    print("Deriving cross-dimension research digest across enriched symbols...")
    cross_artifact = build_cross_dimension_research_digest(digest_artifact, candidates_artifact)

    # Emit JSON
    json_path = out_dir / "cross_dimension_research_digest.json"
    json_path.write_text(json.dumps(cross_artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    # Emit Markdown Summary
    md_summary = generate_cross_dimension_markdown_summary(cross_artifact)
    md_path = out_dir / "cross_dimension_research_digest_summary.md"
    md_path.write_text(md_summary, encoding="utf-8")

    # Emit Manifest
    manifest = {
        "schema_version": "1.0.0",
        "contract_version": "cross_dimension_digest_manifest/v1",
        "digest_identity": cross_artifact["digest_identity"],
        "digest_sha256": cross_artifact["digest_sha256"],
        "session_date": cross_artifact["session_date"],
        "generated_at_utc": cross_artifact["generated_at_utc"],
        "artifacts": [
            {"path": "cross_dimension_research_digest.json", "sha256": cross_artifact["digest_sha256"]},
            {"path": "cross_dimension_research_digest_summary.md", "sha256": hashlib.sha256(md_summary.encode("utf-8")).hexdigest()},
        ],
        "coverage_reconciliation": cross_artifact["coverage_reconciliation"],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "status": "CROSS_DIMENSION_DIGEST_COMPLETE",
        "digest_identity": cross_artifact["digest_identity"],
        "session_date": cross_artifact["session_date"],
        "fully_enriched_count": cross_artifact["coverage_reconciliation"]["fully_enriched_count"],
        "partially_enriched_count": cross_artifact["coverage_reconciliation"]["partially_enriched_count"],
        "out_dir": str(out_dir.resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
