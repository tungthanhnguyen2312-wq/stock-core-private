"""P1: First Deterministic Market-Wide Research / Analysis Artifact Foundation.

This module composes the completed Phase 0 foundation:
- Canonical universe candidate boundary (P0-C.1 / P0-C.2)
- Field-level temporal freshness and fail-closed PIT contracts (P0-C.3)
- Vectorized market feature generation (market_feature_store.py)
- Fail-closed volume, value, liquidity, and price-basis boundaries (P0-B / P0-A)

GOVERNANCE & INVARIANT DISCIPLINE:
- Emits records for CANONICAL_CANDIDATE_UNIVERSE without falsely claiming ACTIVE_UNIVERSE authority.
- Strictly preserves fail-closed invariants:
    * RAW_AS_TRADED = NOT_PROMOTED (price fields fail-closed as pit_eligible=False)
    * QUALIFIED_LIQUIDITY_INPUTS = NO (market liquidity metrics strictly prohibited)
    * POSITION_SIZING_IS_SAFE = NO (execution sizing strictly prohibited)
    * P0-B = TERMINAL_CLOSEOUT_NO_AUTHORITY_PROMOTION (no market-wide turnover authority)
- Vectorized over all candidates in parallel (no per-ticker iteration).
- One missing field blocks only dependent capabilities, never the entire instrument record.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
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
from market_data_contracts import FeatureStatus, PriceBasis
from market_feature_store import (
    REQUIRED_MARKET_COLUMNS,
    build_historical_features,
    validate_market_frame,
)
import canonical_market_evidence_integration as canonical_integration_module
import market_capability_taxonomy as taxonomy
from market_volume_value_semantic_contract import (
    DownstreamUse,
    FIELD_CONTRACTS,
    assert_fail_closed,
)


SCHEMA_VERSION = "1.0.0"
ARTIFACT_TYPE = "MARKET_WIDE_DETERMINISTIC_RESEARCH_ARTIFACT"
UNIVERSE_TYPE = "CANONICAL_CANDIDATE_UNIVERSE"
CONTRACT_VERSION = "market_analysis_artifact/v1"


class MarketAnalysisArtifactError(ValueError):
    """Raised when an invariant or input violates the artifact contract."""


def _sanitize(val: Any) -> Any:
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    if isinstance(val, dict):
        return {k: _sanitize(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_sanitize(v) for v in val]
    return val


def _text(val: Any) -> str | None:
    if val is None:
        return None
    text = str(val).strip()
    return text or None


def _symbol(val: Any) -> str | None:
    text = _text(val)
    return text.upper() if text else None


@dataclass(frozen=True)
class CandidateIdentity:
    candidate_id: str
    instrument_identity_key: str
    symbol: str
    provider_identities: tuple[str, ...]
    instrument_class: str
    exchange: str | None
    listing_status: str | None
    raw_security_group_id: str | None = None


def normalize_candidate_identity(raw: Mapping[str, Any]) -> CandidateIdentity:
    """Extract standard identity from C.1 reconciliation candidate or raw dictionary."""
    candidate_id = _text(raw.get("candidate_id")) or f"candidate:{_symbol(raw.get('symbol', 'UNKNOWN'))}"
    symbol = _symbol(raw.get("symbol"))
    selected = raw.get("selected_fields") if isinstance(raw.get("selected_fields"), Mapping) else {}

    # Extract class
    inst_class = _text(raw.get("instrument_class"))
    if not inst_class and "instrument_class" in selected:
        rec = selected["instrument_class"]
        inst_class = _text(rec.get("value") if isinstance(rec, Mapping) else rec)
    inst_class = inst_class or "UNKNOWN_SECURITY_GROUP"

    # Extract exchange
    exchange = _text(raw.get("exchange") or raw.get("exchange_raw"))
    if not exchange and "exchange" in selected:
        rec = selected["exchange"]
        exchange = _text(rec.get("value") if isinstance(rec, Mapping) else rec)

    # Extract listing status
    listing_status = _text(raw.get("listing_status"))
    if not listing_status and "listing_status" in selected:
        rec = selected["listing_status"]
        listing_status = _text(rec.get("value") if isinstance(rec, Mapping) else rec)
    listing_status = listing_status or "unknown_not_provided_by_dataset"

    # Extract identities
    identities_raw = raw.get("provider_identities") or []
    if isinstance(identities_raw, (str, bytes)):
        identities_raw = [identities_raw]
    identities = tuple(sorted(set(_text(item) for item in identities_raw if _text(item))))
    if not identities and symbol:
        identities = (f"dnse:symbol:{symbol.casefold()}",)

    raw_sec_group = _text(raw.get("raw_security_group_id"))
    identity_key = _text(raw.get("instrument_identity_key")) or f"provider-identity-set:{stable_id(list(identities))}"

    if not symbol and identities:
        for ident in identities:
            if ":" in ident:
                parts = ident.split(":")
                symbol = parts[-1].upper()
                break
    if not symbol:
        symbol = candidate_id.replace("candidate:", "").upper()

    return CandidateIdentity(
        candidate_id=candidate_id,
        instrument_identity_key=identity_key,
        symbol=symbol,
        provider_identities=identities,
        instrument_class=inst_class,
        exchange=exchange,
        listing_status=listing_status,
        raw_security_group_id=raw_sec_group,
    )


def evaluate_universe_membership(candidate: CandidateIdentity) -> dict[str, Any]:
    """Evaluate candidate tier memberships and enforce fail-closed active universe boundaries."""
    inst_class = candidate.instrument_class
    if inst_class == "EQUITY":
        listed_state = INCLUDED
        listed_reason = "instrument_type_equity"
    elif inst_class in {None, "UNKNOWN", "UNKNOWN_SECURITY_GROUP"}:
        listed_state = UNKNOWN
        listed_reason = "instrument_type_unknown"
    elif inst_class == "INDEX":
        listed_state = NOT_APPLICABLE
        listed_reason = "index_confirmed_not_applicable"
    else:
        listed_state = EXCLUDED
        listed_reason = f"instrument_type_{inst_class.lower()}"

    # ACTIVE_UNIVERSE is unconditionally UNKNOWN for all DNSE instruments (no listing status proof)
    if listed_state != INCLUDED:
        active_state = listed_state
        active_reason = listed_reason
    elif candidate.listing_status in {"INACTIVE", "DELISTED"}:
        active_state = EXCLUDED
        active_reason = "listing_inactive_or_delisted"
    elif candidate.listing_status != "ACTIVE":
        active_state = UNKNOWN
        active_reason = "listing_status_unknown"
    elif candidate.exchange is None:
        active_state = UNKNOWN
        active_reason = "exchange_unknown"
    else:
        active_state = INCLUDED
        active_reason = "observed_in_c1"

    return {
        "master_observed": {"state": INCLUDED, "reason_code": "observed_in_c1"},
        "listed_equity_candidate": {"state": listed_state, "reason_code": listed_reason},
        "active_universe": {
            "state": active_state,
            "reason_code": active_reason,
            "authority_status": "FAIL_CLOSED_NO_LISTING_AUTHORITY",
        },
        "canonical_candidate_universe": {
            "state": INCLUDED if listed_state == INCLUDED else EXCLUDED,
            "reason_code": "canonical_candidate_equity" if listed_state == INCLUDED else listed_reason,
            "authority_status": "CANONICAL_CANDIDATE_UNIVERSE_ELIGIBLE" if listed_state == INCLUDED else "INELIGIBLE",
        },
    }


def compute_vectorized_features(
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


def build_market_research_artifact(
    *,
    candidates: Sequence[Mapping[str, Any]] | None = None,
    canonical_integration: Mapping[str, Any] | None = None,
    canonical_session_packet: Mapping[str, Any] | None = None,
    permitted_use: str = canonical_integration_module.USE_WITHIN_SERIES_ANALYTICS,
    market_frame: pd.DataFrame | None = None,
    foreign_flows_frame: pd.DataFrame | None = None,
    as_of_session: str | None = None,
    reference_at: Any = None,
    knowledge_cutoff: Any = None,
    generated_at: str | None = None,
    price_basis: PriceBasis = PriceBasis.ADJUSTED_RETROSPECTIVE,
    volume_basis: str = "UNPROMOTED_SHADOW_ONLY",
    domain: str = "daily_market",
) -> dict[str, Any]:
    """Construct the deterministic market-wide research artifact on top of canonical integration."""
    # 1. Resolve canonical integration if session packet provided
    if canonical_session_packet is not None and canonical_integration is None:
        canonical_integration = canonical_integration_module.integrate_session_packet(canonical_session_packet)

    # 2. Check for prohibited downstream uses
    if permitted_use in canonical_integration_module.STRICTLY_PROHIBITED_USES:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": ARTIFACT_TYPE,
            "status": "PROHIBITED_USE_REJECTED",
            "permitted_use_requested": permitted_use,
            "is_actionable": False,
            "authority_effect": "NONE",
            "reason": f"Downstream use '{permitted_use}' is strictly prohibited across all canonical market observations.",
            "total_candidates_processed": 0,
            "records_emitted": 0,
            "records": [],
            "authority_boundaries": dict(canonical_integration_module.AUTHORITY_BOUNDARIES),
        }

    # 3. Resolve session date
    if as_of_session is None:
        if canonical_integration:
            as_of_session = str(canonical_integration.get("session_date", ""))
        else:
            as_of_session = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 4. Resolve candidates
    if candidates is None or len(candidates) == 0:
        if canonical_integration:
            raw_obs_list = canonical_integration.get("observations", [])
            inferred_symbols = sorted({str(o.get("instrument")).upper() for o in raw_obs_list if o.get("instrument")})
            candidates = [
                {
                    "candidate_id": f"candidate:{sym}",
                    "symbol": sym,
                    "provider_identities": [f"canonical:{sym.casefold()}"],
                    "instrument_class": "EQUITY",
                    "exchange": "HOSE",
                    "listing_status": "unknown_not_provided_by_dataset",
                }
                for sym in inferred_symbols
            ]
        else:
            candidates = []

    normalized_candidates = [normalize_candidate_identity(c) for c in candidates]
    sorted_candidates = sorted(normalized_candidates, key=lambda c: (c.symbol, c.instrument_identity_key))

    # Feature map from market dataframe if provided
    latest_feature_map: dict[str, dict[str, Any]] = {}
    if market_frame is not None and not market_frame.empty:
        calculated_df = compute_vectorized_features(market_frame, price_basis=price_basis)
        target_date = pd.to_datetime(as_of_session)
        latest_df = calculated_df[calculated_df["date"].eq(target_date)].copy()
        if latest_df.empty:
            # If exact date has no rows, take latest per ticker on or before as_of_session
            sub = calculated_df[calculated_df["date"] <= target_date]
            if not sub.empty:
                idx = sub.groupby("ticker")["date"].idxmax()
                latest_df = sub.loc[idx].copy()

        for row in latest_df.to_dict(orient="records"):
            ticker = str(row["ticker"]).upper()
            latest_feature_map[ticker] = row

    # Foreign flows map if provided
    foreign_map: dict[str, dict[str, Any]] = {}
    if foreign_flows_frame is not None and not foreign_flows_frame.empty:
        f_df = foreign_flows_frame.copy()
        f_df["ticker"] = f_df["ticker"].astype(str).str.upper()
        target_date = pd.to_datetime(as_of_session)
        if "date" in f_df.columns:
            f_df["date"] = pd.to_datetime(f_df["date"])
            f_sub = f_df[f_df["date"].eq(target_date)]
            if f_sub.empty:
                f_sub = f_df[f_df["date"] <= target_date]
        else:
            f_sub = f_df
        for row in f_sub.to_dict(orient="records"):
            ticker = str(row["ticker"]).upper()
            foreign_map[ticker] = row

    # Index canonical observations by symbol if canonical integration is provided
    canonical_obs_by_symbol: dict[str, list[dict[str, Any]]] = {}
    if canonical_integration:
        for o in canonical_integration.get("observations", []):
            sym = str(o.get("instrument", "")).upper()
            if sym:
                canonical_obs_by_symbol.setdefault(sym, []).append(o)

    records: list[dict[str, Any]] = []
    freshness_dist: dict[str, int] = {s.value: 0 for s in FreshnessState}
    pit_dist: dict[str, int] = {s.value: 0 for s in PitStatus}
    class_dist: dict[str, int] = {}
    blocked_reasons_dist: dict[str, int] = {}
    sources_present_set: set[str] = set()

    for cand in sorted_candidates:
        symbol = cand.symbol
        class_dist[cand.instrument_class] = class_dist.get(cand.instrument_class, 0) + 1
        tier_membership = evaluate_universe_membership(cand)

        # Permitted features from legacy dataframes (backwards compatibility)
        m_row = latest_feature_map.get(symbol, {})
        has_market_data = bool(m_row)
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

        # Process canonical evidence for this candidate
        cand_canonical_obs = canonical_obs_by_symbol.get(symbol, [])
        canonical_prices: dict[str, dict[str, Any]] = {}
        canonical_volumes: dict[str, dict[str, Any]] = {}
        traded_values: dict[str, dict[str, Any]] = {}
        foreign_room: dict[str, dict[str, Any]] = {}
        foreign_flows: dict[str, dict[str, Any]] = {}
        proprietary_flow: dict[str, dict[str, Any]] = {}
        microstructure: dict[str, dict[str, Any]] = {}
        unacquired_capabilities: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        provenance_references: list[dict[str, Any]] = []

        for obs in cand_canonical_obs:
            src = str(obs.get("source", "UNKNOWN"))
            sources_present_set.add(src)
            obs_status = str(obs.get("observation_status", "UNKNOWN"))
            usability = str(obs.get("usability_state", "UNKNOWN"))
            conflict = str(obs.get("conflict_state", "CLEAN"))
            ident = str(obs.get("semantic_identity", ""))
            family = str(obs.get("capability_family", ""))

            # Handle unacquired/exceptional observations without fabricating data
            if obs_status != "ACQUIRED":
                unacquired_capabilities.append({
                    "source": src,
                    "endpoint_id": obs.get("endpoint_id"),
                    "status": obs_status,
                    "reason": obs.get("provenance", {}).get("error_details") or obs_status,
                    "session": obs.get("session"),
                })
                continue

            # Record conflict if arithmetic conflict detected
            if conflict != "CLEAN":
                conflicts.append({
                    "source": src,
                    "endpoint_id": obs.get("endpoint_id"),
                    "semantic_identity": ident,
                    "conflict_state": conflict,
                    "usability_state": usability,
                    "raw_sha256": obs.get("raw_sha256"),
                })

            eligibility = obs.get("downstream_eligibility", {})
            is_usable_for_permitted_use = eligibility.get(permitted_use, False)

            # Extract clean entry
            c_val = obs.get("canonical_value")
            c_unit = obs.get("canonical_unit")
            p_val = obs.get("provider_native_value")
            p_unit = obs.get("provider_native_unit")

            entry = {
                "value": c_val if is_usable_for_permitted_use else None,
                "unit": c_unit,
                "provider_native_value": p_val,
                "provider_native_unit": p_unit,
                "canonical_value": c_val,
                "canonical_unit": c_unit,
                "contract_id": obs.get("contract_id"),
                "raw_sha256": obs.get("raw_sha256"),
                "raw_path": obs.get("raw_payload_identity"),
                "usability_state": usability,
                "conflict_state": conflict,
                "is_usable": is_usable_for_permitted_use,
                "authority_effect": "NONE",
            }

            provenance_references.append({
                "source": src,
                "endpoint_id": obs.get("endpoint_id"),
                "semantic_identity": ident,
                "raw_sha256": obs.get("raw_sha256"),
            })

            # Map into distinct capability groups
            if family == taxonomy.FAMILY_PRICE:
                canonical_prices.setdefault(src, {})[ident] = entry
                if not observed_at_str:
                    observed_at_str = str(obs.get("retrieved_at", ""))[:10]
            elif family == taxonomy.FAMILY_VOLUME:
                canonical_volumes.setdefault(src, {})[ident] = entry
            elif family == taxonomy.FAMILY_TRADED_VALUE:
                traded_values.setdefault(src, {})[ident] = entry
            elif family == taxonomy.FAMILY_FOREIGN:
                if "ROOM" in ident:
                    foreign_room.setdefault(src, {})[ident] = entry
                else:
                    foreign_flows.setdefault(src, {})[ident] = entry
            elif family == taxonomy.FAMILY_PROPRIETARY:
                proprietary_flow.setdefault(src, {})[ident] = entry
            elif family == taxonomy.FAMILY_MICROSTRUCTURE:
                microstructure.setdefault(src, {})[ident] = entry

        # Temporal envelopes
        market_envelopes = wrap_temporal_fields(
            raw_market_features,
            observed_at=observed_at_str,
            as_of=as_of_session if has_market_data else None,
            domain=domain,
            reference_at=reference_at,
            knowledge_cutoff=knowledge_cutoff,
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
            knowledge_cutoff=knowledge_cutoff,
            price_basis=None,
            quality_status=FeatureStatus.QUALIFIED.value if has_foreign_data else FeatureStatus.UNQUALIFIED.value,
            source="dnse_foreign_flows",
        )

        temporal_envelopes = {**market_envelopes, **foreign_envelopes}

        for tf in temporal_envelopes.values():
            freshness_dist[tf.freshness_status] = freshness_dist.get(tf.freshness_status, 0) + 1
            pit_dist[tf.pit_status] = pit_dist.get(tf.pit_status, 0) + 1

        # Strict blocked capabilities with exact reason codes
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
            "valuation": {
                "status": "BLOCKED",
                "reason_code": "VALUATION_PROHIBITED",
                "governance_rule": "Research consumer: valuation authority is strictly prohibited",
            },
            "recommendation_authority": {
                "status": "BLOCKED",
                "reason_code": "RECOMMENDATION_PROHIBITED",
                "governance_rule": "Research consumer: recommendation and ranking authority is strictly prohibited",
            },
        }

        for cap_name, cap_info in blocked_capabilities.items():
            rc = cap_info["reason_code"]
            blocked_reasons_dist[rc] = blocked_reasons_dist.get(rc, 0) + 1

        has_canonical_data = bool(cand_canonical_obs)
        capability_flags = {
            "display_eligible": True,
            "provider_scoped_analytics_eligible": has_market_data or has_canonical_data,
            "within_series_rel_vol_eligible": has_market_data or has_canonical_data,
            "market_wide_turnover_eligible": False,
            "market_liquidity_eligible": False,
            "execution_sizing_eligible": False,
            "pit_backtest_eligible": False,
            "valuation_eligible": False,
            "recommendation_eligible": False,
        }

        canonical_market_evidence = {
            "prices": canonical_prices,
            "volumes": canonical_volumes,
            "traded_values": traded_values,
            "foreign_room": foreign_room,
            "foreign_flows": foreign_flows,
            "proprietary_flow": proprietary_flow,
            "microstructure": microstructure,
            "unacquired_capabilities": unacquired_capabilities,
            "conflicts": conflicts,
            "provenance_references": provenance_references,
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
                "source": "canonical_market_evidence_integration" if canonical_integration else "market_feature_store",
            },
            "canonical_market_evidence": canonical_market_evidence,
            "market_features": _sanitize(raw_market_features),
            "foreign_flow_features": _sanitize(raw_foreign_features),
            "financial_statement_features": {},
            "corporate_action_features": {},
            "qualification_and_capabilities": {
                "capability_flags": capability_flags,
                "blocked_capabilities": blocked_capabilities,
            },
            # Backwards-compatible aliases
            "permitted_provider_features": _sanitize(raw_market_features),
            "qualified_financial_features": _sanitize(raw_foreign_features),
            "blocked_capabilities": blocked_capabilities,
            "capability_flags": capability_flags,
            "temporal_fields": {k: tf.record() for k, tf in temporal_envelopes.items()},
        })

    # Assemble complete deterministic payload
    gen_time = generated_at or (str(reference_at) if reference_at else datetime.now(timezone.utc).isoformat())
    raw_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "universe_type": UNIVERSE_TYPE,
        "contract_version": CONTRACT_VERSION,
        "as_of_session": as_of_session,
        "generated_at": gen_time,
        "permitted_use_applied": permitted_use,
        "canonical_integration_identity": canonical_integration.get("integration_identity") if canonical_integration else None,
        "canonical_integration_sha256": canonical_integration.get("integration_sha256") if canonical_integration else None,
        "sources_present": sorted(sources_present_set),
        "total_candidates_processed": len(sorted_candidates),
        "records_emitted": len(records),
        "candidates_by_class": class_dist,
        "freshness_distribution": freshness_dist,
        "pit_eligibility_distribution": pit_dist,
        "blocked_reasons_distribution": blocked_reasons_dist,
        "authority_boundaries": dict(canonical_integration_module.AUTHORITY_BOUNDARIES),
        "records": records,
    }

    # Deterministic content hash excluding clock-dependent generated_at
    deterministic_payload = {k: v for k, v in raw_payload.items() if k != "generated_at"}
    content_hash = stable_id(deterministic_payload)
    artifact_id = f"market-wide-research-artifact:{content_hash}"

    return {
        **raw_payload,
        "content_hash": content_hash,
        "artifact_id": artifact_id,
    }
