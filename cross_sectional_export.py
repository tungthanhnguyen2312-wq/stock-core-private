"""P1: Multi-Session Cross-Sectional Research Export & Feature Store Normalization.

This module provides pure, deterministic normalization and multi-session export
capabilities for Vietnamese equities research:
1. Normalizes feature records into explicit semantic domains:
   - market_features
   - foreign_flow_features
   - financial_statement_features
   - corporate_action_features
   - qualification_and_capabilities (capability_flags & blocked_capabilities)
   - temporal_fields (bound field-level TemporalField envelopes)
2. Enforces explicit fail-closed boundaries:
   - Denominator is CANONICAL_CANDIDATE_UNIVERSE (never falsely labeled ACTIVE_UNIVERSE)
   - RAW_AS_TRADED = NOT_PROMOTED (price fields fail closed as pit_eligible=False)
   - QUALIFIED_LIQUIDITY_INPUTS = NO (market liquidity & turnover strictly blocked)
   - POSITION_SIZING_IS_SAFE = NO (execution sizing strictly prohibited)
   - Missing observations remain missing (no silent forward-fill)
3. Produces deterministic, byte-stable cross-sectional session and multi-session exports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from canonical_universe_tiers import (
    ACTIVE_UNIVERSE,
    EXCLUDED,
    INCLUDED,
    LISTED_EQUITY_CANDIDATE,
    MASTER_OBSERVED,
    NOT_APPLICABLE,
    UNKNOWN,
)
from field_temporal_contract import (
    FreshnessState,
    PitStatus,
    TemporalField,
    canonical_json,
    stable_id,
    wrap_temporal_fields,
)
from market_analysis_artifact import (
    CandidateIdentity,
    evaluate_universe_membership,
    normalize_candidate_identity,
)
from market_data_contracts import FeatureStatus, PriceBasis
from market_feature_store import (
    REQUIRED_MARKET_COLUMNS,
    build_historical_features,
    validate_market_frame,
)


SCHEMA_VERSION = "1.0.0"
SESSION_EXPORT_ARTIFACT_TYPE = "MARKET_WIDE_CROSS_SECTIONAL_SESSION_EXPORT"
MULTI_SESSION_EXPORT_ARTIFACT_TYPE = "MULTI_SESSION_CROSS_SECTIONAL_RESEARCH_EXPORT"
UNIVERSE_TYPE = "CANONICAL_CANDIDATE_UNIVERSE"
CONTRACT_VERSION = "cross_sectional_export/v1"


class CrossSectionalExportError(ValueError):
    """Raised when an invariant or input violates the export contract."""


def _sanitize(val: Any) -> Any:
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    if isinstance(val, dict):
        return {k: _sanitize(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_sanitize(v) for v in val]
    return val


def compute_vectorized_market_features(
    market_frame: pd.DataFrame,
    *,
    price_basis: PriceBasis = PriceBasis.ADJUSTED_RETROSPECTIVE,
    window_short: int = 3,
    window_medium: int = 5,
    window_long: int = 20,
) -> pd.DataFrame:
    """Vectorized calculation of permitted provider-scoped technical features across all instruments."""
    result = validate_market_frame(market_frame)
    grouped = result.groupby("ticker", sort=False, group_keys=False)

    result["market.close"] = result["close"]
    result["market.return_1d"] = grouped["close"].pct_change(fill_method=None)
    result[f"market.ma_{window_short}"] = grouped["close"].transform(
        lambda s: s.rolling(window_short, min_periods=window_short).mean()
    )
    result[f"market.ma_{window_medium}"] = grouped["close"].transform(
        lambda s: s.rolling(window_medium, min_periods=window_medium).mean()
    )
    result[f"market.ma_{window_long}"] = grouped["close"].transform(
        lambda s: s.rolling(window_long, min_periods=window_long).mean()
    )
    result[f"market.volatility_{window_short}"] = grouped["market.return_1d"].transform(
        lambda s: s.rolling(window_short, min_periods=window_short).std(ddof=0)
    )
    result[f"market.volatility_{window_long}"] = grouped["market.return_1d"].transform(
        lambda s: s.rolling(window_long, min_periods=window_long).std(ddof=0)
    )

    # Provider-scoped relative volume (within-series 20-day median ratio)
    result["market.volume_ratio"] = result["volume"] / grouped["volume"].transform(
        lambda s: s.rolling(window_long, min_periods=max(2, window_short)).median()
    )
    result["legacy.rel_vol"] = result["market.volume_ratio"]

    result["feature_status"] = FeatureStatus.DERIVED.value
    result["price_basis"] = price_basis.value
    result["pit_status"] = (
        FeatureStatus.QUALIFIED.value
        if price_basis in {PriceBasis.PIT_OBSERVED, PriceBasis.RAW_AS_TRADED}
        else FeatureStatus.HISTORICAL_ONLY.value
    )
    return result


def _date_str(val: Any) -> str:
    if val is None:
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    return s[:10]


def build_cross_sectional_session_export(
    *,
    candidates: Sequence[Mapping[str, Any]],
    market_frame: pd.DataFrame | None = None,
    foreign_flows_frame: pd.DataFrame | None = None,
    as_of_session: str,
    reference_at: Any = None,
    knowledge_cutoff: Any = None,
    generated_at: str | None = None,
    price_basis: PriceBasis = PriceBasis.ADJUSTED_RETROSPECTIVE,
    volume_basis: str = "UNPROMOTED_SHADOW_ONLY",
    domain: str = "daily_market",
) -> dict[str, Any]:
    """Construct deterministic normalized cross-sectional export for one market session."""
    normalized_candidates = [normalize_candidate_identity(c) for c in candidates]
    sorted_candidates = sorted(normalized_candidates, key=lambda c: (c.symbol, c.instrument_identity_key))

    # Reject lookahead
    session_date_str = _date_str(as_of_session)
    if reference_at is not None:
        ref_date_str = _date_str(reference_at)
        if session_date_str > ref_date_str:
            raise CrossSectionalExportError(
                f"lookahead_violation: session {as_of_session} is after reference_at {reference_at}"
            )

    # Calculate market features
    latest_feature_map: dict[str, dict[str, Any]] = {}
    if market_frame is not None and not market_frame.empty:
        calculated_df = compute_vectorized_market_features(market_frame, price_basis=price_basis)
        target_date = pd.to_datetime(as_of_session)
        # Exact session match only (no forward fill)
        latest_df = calculated_df[calculated_df["date"].eq(target_date)].copy()
        for row in latest_df.to_dict(orient="records"):
            ticker = str(row["ticker"]).upper()
            latest_feature_map[ticker] = row

    # Foreign flows map
    foreign_map: dict[str, dict[str, Any]] = {}
    if foreign_flows_frame is not None and not foreign_flows_frame.empty:
        f_df = foreign_flows_frame.copy()
        f_df["ticker"] = f_df["ticker"].astype(str).str.upper()
        target_date = pd.to_datetime(as_of_session)
        if "date" in f_df.columns:
            f_df["date"] = pd.to_datetime(f_df["date"])
            f_sub = f_df[f_df["date"].eq(target_date)]
        else:
            f_sub = f_df
        for row in f_sub.to_dict(orient="records"):
            ticker = str(row["ticker"]).upper()
            foreign_map[ticker] = row

    records: list[dict[str, Any]] = []
    freshness_dist: dict[str, int] = {s.value: 0 for s in FreshnessState}
    pit_dist: dict[str, int] = {s.value: 0 for s in PitStatus}
    class_dist: dict[str, int] = {}
    blocked_reasons_dist: dict[str, int] = {}
    field_coverage: dict[str, int] = {}

    observed_count = 0
    missing_count = 0

    for cand in sorted_candidates:
        symbol = cand.symbol
        class_dist[cand.instrument_class] = class_dist.get(cand.instrument_class, 0) + 1
        tier_membership = evaluate_universe_membership(cand)

        # Market features
        m_row = latest_feature_map.get(symbol, {})
        has_market_data = bool(m_row)
        if has_market_data:
            observed_count += 1
        else:
            missing_count += 1

        observed_date = m_row.get("date") if has_market_data else None
        if hasattr(observed_date, "strftime"):
            observed_at_str = observed_date.strftime("%Y-%m-%d")
        elif observed_date:
            observed_at_str = str(observed_date)[:10]
        else:
            observed_at_str = None

        raw_market_features = _sanitize({
            "market.close": m_row.get("market.close"),
            "market.return_1d": m_row.get("market.return_1d"),
            "market.ma_3": m_row.get("market.ma_3"),
            "market.ma_5": m_row.get("market.ma_5"),
            "market.ma_20": m_row.get("market.ma_20"),
            "market.volatility_3": m_row.get("market.volatility_3"),
            "market.volatility_20": m_row.get("market.volatility_20"),
            "market.volume_ratio": m_row.get("market.volume_ratio"),
            "legacy.rel_vol": m_row.get("legacy.rel_vol"),
        })

        # Track field coverage
        for k, v in raw_market_features.items():
            if v is not None:
                field_coverage[k] = field_coverage.get(k, 0) + 1

        # Foreign flows (Clean taxonomy: foreign_flow_features, NOT financial statements)
        f_row = foreign_map.get(symbol, {})
        has_foreign_data = bool(f_row)
        f_obs_date = f_row.get("date") if has_foreign_data else None
        if hasattr(f_obs_date, "strftime"):
            f_obs_str = f_obs_date.strftime("%Y-%m-%d")
        elif f_obs_date:
            f_obs_str = str(f_obs_date)[:10]
        else:
            f_obs_str = observed_at_str if has_foreign_data else None

        raw_foreign_features = _sanitize({
            "dnse.foreign_buy_value": f_row.get("foreign_buy_value") or f_row.get("buy_value"),
            "dnse.foreign_sell_value": f_row.get("foreign_sell_value") or f_row.get("sell_value"),
            "dnse.foreign_net_value": f_row.get("foreign_net_value") or f_row.get("net_value"),
        })

        for k, v in raw_foreign_features.items():
            if v is not None:
                field_coverage[k] = field_coverage.get(k, 0) + 1

        # Financial statements & corporate actions are empty/omitted unless qualified
        financial_statement_features: dict[str, Any] = {}
        corporate_action_features: dict[str, Any] = {}

        cutoff_to_use = knowledge_cutoff if knowledge_cutoff is not None else reference_at

        # Wrap temporal envelopes
        market_envelopes = wrap_temporal_fields(
            raw_market_features,
            observed_at=observed_at_str,
            as_of=as_of_session if has_market_data else None,
            domain=domain,
            reference_at=reference_at,
            knowledge_cutoff=cutoff_to_use,
            price_basis=price_basis.value,
            quality_status=FeatureStatus.DERIVED.value if has_market_data else FeatureStatus.UNQUALIFIED.value,
            source="market_feature_store",
        )

        foreign_envelopes = wrap_temporal_fields(
            raw_foreign_features,
            observed_at=f_obs_str,
            as_of=as_of_session if has_foreign_data else None,
            domain="foreign_trading",
            reference_at=reference_at,
            knowledge_cutoff=cutoff_to_use,
            price_basis=None,
            quality_status=FeatureStatus.QUALIFIED.value if has_foreign_data else FeatureStatus.UNQUALIFIED.value,
            source="dnse_foreign_flows",
        )

        temporal_envelopes = {**market_envelopes, **foreign_envelopes}

        for tf in temporal_envelopes.values():
            freshness_dist[tf.freshness_status] = freshness_dist.get(tf.freshness_status, 0) + 1
            pit_dist[tf.pit_status] = pit_dist.get(tf.pit_status, 0) + 1

        # Blocked capabilities
        blocked_capabilities = {
            "market_wide_turnover": {
                "status": "BLOCKED",
                "reason_code": "NO_MARKET_WIDE_TURNOVER_AUTHORITY",
                "governance_rule": "P0-B terminal closeout: volume fields lack certified market-wide authority",
            },
            "market_liquidity": {
                "status": "BLOCKED",
                "reason_code": "LIQUIDITY_INPUTS_UNQUALIFIED",
                "governance_rule": "P0-B negative proof: QUALIFIED_LIQUIDITY_INPUTS = NO",
            },
            "execution_sizing": {
                "status": "BLOCKED",
                "reason_code": "POSITION_SIZING_PROHIBITED",
                "governance_rule": "P0-B negative proof: POSITION_SIZING_IS_SAFE = NO",
            },
            "pit_backtest": {
                "status": "BLOCKED",
                "reason_code": "UNQUALIFIED_PRICE_BASIS",
                "governance_rule": "P0-A price basis invariant: RAW_AS_TRADED is not promoted",
            },
        }

        for cap_info in blocked_capabilities.values():
            rc = cap_info["reason_code"]
            blocked_reasons_dist[rc] = blocked_reasons_dist.get(rc, 0) + 1

        # Capability flags
        capability_flags = {
            "display_eligible": True,
            "provider_scoped_analytics_eligible": has_market_data,
            "within_series_rel_vol_eligible": has_market_data,
            "market_wide_turnover_eligible": False,
            "market_liquidity_eligible": False,
            "execution_sizing_eligible": False,
            "pit_backtest_eligible": False,
        }

        records.append({
            "instrument_identity": {
                "candidate_id": cand.candidate_id,
                "instrument_identity_key": cand.instrument_identity_key,
                "symbol": cand.symbol,
                "provider_identities": list(cand.provider_identities),
            },
            "classification_status": {
                "instrument_class": cand.instrument_class,
                "exchange": cand.exchange,
                "listing_status": cand.listing_status,
                "raw_security_group_id": cand.raw_security_group_id,
            },
            "universe_tier_membership": tier_membership,
            "as_of": as_of_session,
            "observed_at": observed_at_str,
            "source_lineage": {
                "price_basis": price_basis.value,
                "volume_basis": volume_basis,
                "contract_version": CONTRACT_VERSION,
                "source": "market_feature_store",
            },
            "market_features": _sanitize(raw_market_features),
            "foreign_flow_features": _sanitize(raw_foreign_features),
            "financial_statement_features": financial_statement_features,
            "corporate_action_features": corporate_action_features,
            "qualification_and_capabilities": {
                "capability_flags": capability_flags,
                "blocked_capabilities": blocked_capabilities,
            },
            "temporal_fields": {k: tf.record() for k, tf in temporal_envelopes.items()},
        })

    gen_time = generated_at or (str(reference_at) if reference_at else datetime.now(timezone.utc).isoformat())
    raw_payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": SESSION_EXPORT_ARTIFACT_TYPE,
        "universe_type": UNIVERSE_TYPE,
        "as_of_session": as_of_session,
        "generated_at": gen_time,
        "total_candidates_processed": len(sorted_candidates),
        "observed_instruments_count": observed_count,
        "missing_instruments_count": missing_count,
        "field_coverage_summary": field_coverage,
        "candidates_by_class": class_dist,
        "freshness_distribution": freshness_dist,
        "pit_eligibility_distribution": pit_dist,
        "blocked_reasons_distribution": blocked_reasons_dist,
        "records": records,
    }

    content_hash = stable_id(raw_payload)
    artifact_id = f"cross-sectional-session-export:{as_of_session}:{content_hash}"

    return {
        **raw_payload,
        "content_hash": content_hash,
        "artifact_id": artifact_id,
    }


def build_multi_session_cross_sectional_export(
    *,
    candidates: Sequence[Mapping[str, Any]],
    market_frame: pd.DataFrame,
    foreign_flows_frame: pd.DataFrame | None = None,
    session_dates: Sequence[str] | None = None,
    reference_at: Any = None,
    knowledge_cutoff: Any = None,
    generated_at: str | None = None,
    price_basis: PriceBasis = PriceBasis.ADJUSTED_RETROSPECTIVE,
    volume_basis: str = "UNPROMOTED_SHADOW_ONLY",
) -> dict[str, Any]:
    """Construct deterministic multi-session cross-sectional research export."""
    validated_market = validate_market_frame(market_frame)
    available_dates = sorted(validated_market["date"].dt.strftime("%Y-%m-%d").unique())

    if session_dates is None:
        target_dates = available_dates
    else:
        target_dates = sorted(set(session_dates))

    if not target_dates:
        raise CrossSectionalExportError("no session dates provided or found in market frame")

    # Reject lookahead if reference_at is given
    if reference_at is not None:
        ref_date_str = _date_str(reference_at)
        future_dates = [d for d in target_dates if _date_str(d) > ref_date_str]
        if future_dates:
            raise CrossSectionalExportError(
                f"lookahead_violation: session dates {future_dates} exceed reference_at {reference_at}"
            )

    session_exports: list[dict[str, Any]] = []
    coverage_by_session: dict[str, dict[str, Any]] = {}
    overall_field_coverage: dict[str, int] = {}
    overall_freshness: dict[str, int] = {s.value: 0 for s in FreshnessState}
    overall_pit: dict[str, int] = {s.value: 0 for s in PitStatus}
    overall_blocked_reasons: dict[str, int] = {}
    total_observations = 0

    for s_date in target_dates:
        s_export = build_cross_sectional_session_export(
            candidates=candidates,
            market_frame=market_frame,
            foreign_flows_frame=foreign_flows_frame,
            as_of_session=s_date,
            reference_at=reference_at or f"{s_date}T16:00:00+07:00",
            knowledge_cutoff=knowledge_cutoff or f"{s_date}T16:00:00+07:00",
            generated_at=generated_at,
            price_basis=price_basis,
            volume_basis=volume_basis,
        )
        session_exports.append(s_export)

        obs = s_export["observed_instruments_count"]
        tot = s_export["total_candidates_processed"]
        miss = s_export["missing_instruments_count"]
        cov_rate = round(obs / tot, 4) if tot else 0.0

        coverage_by_session[s_date] = {
            "total_candidates": tot,
            "observed_count": obs,
            "missing_count": miss,
            "coverage_rate": cov_rate,
            "session_content_hash": s_export["content_hash"],
        }
        total_observations += obs

        for k, v in s_export["field_coverage_summary"].items():
            overall_field_coverage[k] = overall_field_coverage.get(k, 0) + v
        for k, v in s_export["freshness_distribution"].items():
            overall_freshness[k] = overall_freshness.get(k, 0) + v
        for k, v in s_export["pit_eligibility_distribution"].items():
            overall_pit[k] = overall_pit.get(k, 0) + v
        for k, v in s_export["blocked_reasons_distribution"].items():
            overall_blocked_reasons[k] = overall_blocked_reasons.get(k, 0) + v

    gen_time = generated_at or (str(reference_at) if reference_at else datetime.now(timezone.utc).isoformat())
    start_session = target_dates[0]
    end_session = target_dates[-1]

    raw_payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": MULTI_SESSION_EXPORT_ARTIFACT_TYPE,
        "universe_type": UNIVERSE_TYPE,
        "session_count": len(target_dates),
        "session_dates": target_dates,
        "date_range": {
            "start_session": start_session,
            "end_session": end_session,
        },
        "generated_at": gen_time,
        "total_canonical_candidates": len(candidates),
        "total_observations_emitted": total_observations,
        "coverage_by_session": coverage_by_session,
        "overall_field_coverage": overall_field_coverage,
        "freshness_distribution_overall": overall_freshness,
        "pit_distribution_overall": overall_pit,
        "blocked_reasons_overall": overall_blocked_reasons,
        "sessions": session_exports,
    }

    content_hash = stable_id(raw_payload)
    artifact_id = f"multi-session-cross-sectional-export:{start_session}_to_{end_session}:{content_hash}"

    return {
        **raw_payload,
        "content_hash": content_hash,
        "artifact_id": artifact_id,
    }
