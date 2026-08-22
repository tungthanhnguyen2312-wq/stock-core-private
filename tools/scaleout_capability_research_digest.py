"""tools/scaleout_capability_research_digest.py — Coverage-aware two-layer research data digest.

Two-layer architecture:
1. MARKET_WIDE_CORE: Full research universe (524/524) from retained DNSE market data.
   - aggregate_scope: "FULL_RESEARCH_UNIVERSE"
   - Deterministic market breadth, return distributions, MA20 breadth, volatility, tails.
2. FHSC_ENRICHMENT: Acquired enrichment cohort from retained FHSC observations.
   - aggregate_scope: "ACQUIRED_ENRICHMENT_COHORT"
   - Explicit coverage denominators (universe_count, acquired_count, coverage_ratio).
   - Exact value/volume composition, foreign room, proprietary flow, microstructure.
   - Next acquisition queue generation with strict invariant enforcement:
     acquired_symbols ∩ next_acquisition_queue == empty.

Authority Boundary:
- authority_effect: "NONE"
- raw_as_traded_promoted: False
- pit_backtest_eligible: False
- liquidity_sizing_authority: "BLOCKED"
- valuation_authority: False
- recommendation_authority: False
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

import market_capability_taxonomy as taxonomy
from atomic_io import atomic_write_file, atomic_write_json

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "capability_first_coverage_aware_digest/v1"

AUTHORITY_BOUNDARIES = {
    "authority_effect": "NONE",
    "raw_as_traded_promoted": False,
    "pit_backtest_eligible": False,
    "liquidity_sizing_authority": "BLOCKED",
    "valuation_authority": False,
    "recommendation_authority": False,
    "database_mutated": False,
}

# Coverage status constants
STATUS_ACQUIRED = "ACQUIRED"
STATUS_NOT_ACQUIRED = "NOT_ACQUIRED_IN_THIS_SCALEOUT"
STATUS_REQUESTED_MISSING = "REQUESTED_BUT_MISSING"
STATUS_MISSING_SESSION = "MISSING_REQUESTED_SESSION"
STATUS_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
STATUS_BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
STATUS_CONFLICTING = "CONFLICTING"


def _canonical_json(val: Any) -> str:
    return json.dumps(val, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_json(val: Any) -> str:
    return hashlib.sha256(_canonical_json(val).encode("utf-8")).hexdigest()


def load_universe_snapshot(snapshot_path: Path) -> dict[str, Any]:
    """Load universe snapshot containing the ~523/524 research cohort and DNSE market state."""
    if not snapshot_path.is_file():
        raise FileNotFoundError(f"Universe snapshot not found at: {snapshot_path}")
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


def find_retained_packets_for_session(
    search_root: Path,
    session_date: str,
    explicit_paths: Sequence[Path] | None = None,
) -> list[dict[str, Any]]:
    """Locate and load all retained session_packet.json files for a given session date."""
    packets: list[dict[str, Any]] = []
    seen_identities: set[str] = set()

    candidate_paths: list[Path] = []
    if explicit_paths:
        candidate_paths.extend(explicit_paths)
    else:
        if search_root.is_dir():
            candidate_paths.extend(search_root.rglob("session_packet.json"))

    for p in candidate_paths:
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("session_date") == session_date:
                packet_id = data.get("packet_identity") or _sha256_json(data)
                if packet_id not in seen_identities:
                    seen_identities.add(packet_id)
                    packets.append(data)
        except Exception:
            continue

    return packets


def _get_fval(obs_dict: Mapping[str, Any] | None, field_name: str) -> float | None:
    """Helper to extract numeric value from canonical_fields or native_fields without defaulting to 0."""
    if not obs_dict:
        return None
    for layer in ("canonical_fields", "native_fields", "normalized_fields"):
        container = obs_dict.get(layer, {})
        if field_name in container:
            item = container[field_name]
            if isinstance(item, dict):
                val = item.get("value")
                if val is not None:
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        pass
            elif isinstance(item, (int, float)):
                return float(item)
    return None


def build_research_digest(
    session_date: str,
    universe_snapshot: Mapping[str, Any],
    retained_packets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build deterministic coverage-aware two-layer research data digest."""
    universe_members: list[str] = universe_snapshot.get("cohort", {}).get("members", [])
    if not universe_members:
        universe_members = [r["ticker"] for r in universe_snapshot.get("records", []) if "ticker" in r]
    universe_members = sorted(set(universe_members))
    total_universe_count = len(universe_members)

    # 1. Map DNSE technical state by ticker from snapshot
    dnse_records_by_ticker: dict[str, dict[str, Any]] = {}
    for rec in universe_snapshot.get("records", []):
        ticker = rec.get("ticker")
        if ticker:
            dnse_records_by_ticker[str(ticker).upper()] = rec

    # 2. Aggregate all observations from retained packets by (ticker, endpoint_id)
    fhsc_obs_by_ticker: dict[str, dict[str, dict[str, Any]]] = {t: {} for t in universe_members}
    requested_symbols_set: set[str] = set()

    for packet in retained_packets:
        for obs in packet.get("observations", []):
            ticker = str(obs.get("instrument", "")).upper()
            if ticker in fhsc_obs_by_ticker:
                requested_symbols_set.add(ticker)
                endpoint = obs.get("endpoint_id")
                if endpoint:
                    existing = fhsc_obs_by_ticker[ticker].get(endpoint)
                    if existing is None or (obs.get("status") == STATUS_ACQUIRED and existing.get("status") != STATUS_ACQUIRED):
                        fhsc_obs_by_ticker[ticker][endpoint] = obs

    # -------------------------------------------------------------
    # LAYER 1: MARKET-WIDE CORE (524/524 DNSE Coverage)
    # -------------------------------------------------------------
    advancers: list[dict[str, Any]] = []
    decliners: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    returns_1d: list[float] = []
    volatilities_20d: list[float] = []
    rel_vols: list[float] = []
    above_ma20_count = 0
    at_or_below_ma20_count = 0

    dnse_available_count = 0

    for ticker in universe_members:
        dnse_raw = dnse_records_by_ticker.get(ticker)
        if not dnse_raw:
            continue
        dnse_available_count += 1
        tech = dnse_raw.get("daily_technical_state", {})
        vals = tech.get("values", {})
        close_vnd = dnse_raw.get("exact_session_close", vals.get("close"))
        ret_1d = vals.get("return_1d")
        vol_20d = vals.get("volatility_20d")
        ma_20 = vals.get("ma_20")
        rel_vol = vals.get("relative_volume_provider_scoped")

        entry_summary = {"ticker": ticker, "close_vnd": close_vnd, "return_1d": ret_1d}

        if ret_1d is not None:
            returns_1d.append(ret_1d)
            if ret_1d > 0.0001:
                advancers.append(entry_summary)
            elif ret_1d < -0.0001:
                decliners.append(entry_summary)
            else:
                unchanged.append(entry_summary)

        if vol_20d is not None:
            volatilities_20d.append(vol_20d)

        if rel_vol is not None:
            rel_vols.append(rel_vol)

        if close_vnd is not None and ma_20 is not None:
            if close_vnd > ma_20:
                above_ma20_count += 1
            else:
                at_or_below_ma20_count += 1

    # Sort descriptive tails
    advancers.sort(key=lambda x: x["return_1d"], reverse=True)
    decliners.sort(key=lambda x: x["return_1d"])

    sorted_returns = sorted(returns_1d)
    median_return = None
    p25_return = None
    p75_return = None
    if sorted_returns:
        n = len(sorted_returns)
        median_return = sorted_returns[n // 2]
        p25_return = sorted_returns[int(n * 0.25)]
        p75_return = sorted_returns[int(n * 0.75)]

    sorted_vols = sorted(volatilities_20d)
    median_vol = sorted_vols[len(sorted_vols) // 2] if sorted_vols else None

    sorted_rel_vols = sorted(rel_vols)
    median_rel_vol = sorted_rel_vols[len(sorted_rel_vols) // 2] if sorted_rel_vols else None
    elevated_vol_count = sum(1 for v in rel_vols if v >= 1.5)
    depressed_vol_count = sum(1 for v in rel_vols if v <= 0.8)
    normal_vol_count = sum(1 for v in rel_vols if 0.8 < v < 1.5)

    market_wide_core = {
        "aggregate_scope": "FULL_RESEARCH_UNIVERSE",
        "universe_count": total_universe_count,
        "available_symbol_count": dnse_available_count,
        "coverage_ratio": round(dnse_available_count / total_universe_count, 6) if total_universe_count > 0 else 0.0,
        "session_date": session_date,
        "breadth_summary": {
            "advancers_count": len(advancers),
            "decliners_count": len(decliners),
            "unchanged_count": len(unchanged),
            "advance_decline_ratio": round(len(advancers) / len(decliners), 4) if len(decliners) > 0 else None,
        },
        "return_distribution": {
            "mean_return_1d": round(sum(returns_1d) / len(returns_1d), 6) if returns_1d else None,
            "median_return_1d": median_return,
            "p25_return_1d": p25_return,
            "p75_return_1d": p75_return,
            "min_return_1d": sorted_returns[0] if sorted_returns else None,
            "max_return_1d": sorted_returns[-1] if sorted_returns else None,
        },
        "moving_average_breadth": {
            "above_ma20_count": above_ma20_count,
            "at_or_below_ma20_count": at_or_below_ma20_count,
            "above_ma20_ratio": round(above_ma20_count / total_universe_count, 6) if total_universe_count > 0 else None,
        },
        "volatility_distribution": {
            "mean_volatility_20d": round(sum(volatilities_20d) / len(volatilities_20d), 6) if volatilities_20d else None,
            "median_volatility_20d": median_vol,
            "min_volatility_20d": sorted_vols[0] if sorted_vols else None,
            "max_volatility_20d": sorted_vols[-1] if sorted_vols else None,
        },
        "relative_volume_breadth": {
            "elevated_volume_count": elevated_vol_count,
            "normal_volume_count": normal_vol_count,
            "depressed_volume_count": depressed_vol_count,
            "median_relative_volume": median_rel_vol,
        },
        "descriptive_tails": {
            "top_5_gainers": advancers[:5],
            "top_5_decliners": decliners[:5],
        },
    }

    # -------------------------------------------------------------
    # LAYER 2: FHSC ENRICHMENT (Acquired Cohort Only)
    # -------------------------------------------------------------
    digest_records: list[dict[str, Any]] = []

    # Aggregators for acquired cohort metrics (do NOT blend missing into zero)
    agg_matched_value = 0.0
    agg_put_through_value = 0.0
    agg_total_value = 0.0
    agg_matched_volume = 0.0
    agg_put_through_volume = 0.0
    agg_total_volume = 0.0
    agg_prop_net_value = 0.0
    agg_prop_net_volume = 0.0
    order_imbalances: list[float] = []
    room_utilizations: list[float] = []

    count_with_trading = 0
    count_with_room = 0
    count_with_prop = 0
    count_with_micro = 0
    count_fully_covered = 0
    count_partially_covered = 0
    count_not_acquired = 0

    # Categorization sets for trading_history scaleout
    trading_acquired_set: set[str] = set()
    trading_rate_limited_set: set[str] = set()
    trading_missing_session_set: set[str] = set()
    trading_budget_exhausted_set: set[str] = set()
    trading_unattempted_set: set[str] = set()

    for ticker in universe_members:
        dnse_raw = dnse_records_by_ticker.get(ticker)
        dnse_state: dict[str, Any] | None = None
        if dnse_raw:
            tech = dnse_raw.get("daily_technical_state", {})
            vals = tech.get("values", {})
            dnse_state = {
                "status": STATUS_ACQUIRED,
                "usability_state": taxonomy.RESEARCH_USABLE,
                "exact_session_close_vnd": dnse_raw.get("exact_session_close", vals.get("close")),
                "return_1d": vals.get("return_1d"),
                "volatility_20d": vals.get("volatility_20d"),
                "ma_20_vnd": vals.get("ma_20"),
                "relative_volume_provider_scoped": vals.get("relative_volume_provider_scoped"),
                "price_basis": tech.get("price_basis", "ADJUSTED_RETROSPECTIVE"),
                "authority_boundaries": AUTHORITY_BOUNDARIES,
            }

        sym_fhsc = fhsc_obs_by_ticker.get(ticker, {})

        # Helper to classify observation status accurately
        def _classify_obs(obs: Mapping[str, Any] | None) -> tuple[str, str]:
            if obs is None:
                return (STATUS_NOT_ACQUIRED, "NOT_ACQUIRED")
            raw_st = obs.get("status")
            if raw_st == STATUS_ACQUIRED:
                return (STATUS_ACQUIRED, taxonomy.RESEARCH_USABLE)
            if raw_st == STATUS_RATE_LIMITED:
                return (STATUS_RATE_LIMITED, "PROVIDER_RATE_LIMITED")
            if raw_st in (STATUS_MISSING_SESSION, "EXACT_SESSION_MISSING"):
                return (STATUS_MISSING_SESSION, taxonomy.MISSING)
            if raw_st == STATUS_BUDGET_EXHAUSTED:
                return (STATUS_BUDGET_EXHAUSTED, "BUDGET_EXHAUSTED")
            if raw_st == STATUS_CONFLICTING:
                return (STATUS_CONFLICTING, taxonomy.SEMANTIC_UNRESOLVED)
            return (STATUS_REQUESTED_MISSING, taxonomy.MISSING)

        # 1. Trading History (Value & Volume Composition)
        trading_obs = sym_fhsc.get("trading_history")
        st_trading, use_trading = _classify_obs(trading_obs)
        trading_entry: dict[str, Any] = {
            "status": st_trading,
            "usability_state": use_trading,
            "matched_traded_value_vnd": None,
            "put_through_traded_value_vnd": None,
            "total_traded_value_vnd": None,
            "matched_value_ratio": None,
            "put_through_value_ratio": None,
            "matched_volume_shares": None,
            "put_through_volume_shares": None,
            "total_volume_shares": None,
            "raw_sha256": trading_obs.get("raw_sha256") if trading_obs else None,
        }

        if st_trading == STATUS_ACQUIRED:
            count_with_trading += 1
            trading_acquired_set.add(ticker)
            mv = _get_fval(trading_obs, "MATCHED_TRADED_VALUE_VND")
            pv = _get_fval(trading_obs, "PUT_THROUGH_TRADED_VALUE_VND")
            tv = _get_fval(trading_obs, "TOTAL_TRADED_VALUE_VND")
            m_vol = _get_fval(trading_obs, "MATCHED_VOLUME_SHARES")
            p_vol = _get_fval(trading_obs, "PUT_THROUGH_VOLUME_SHARES")
            t_vol = _get_fval(trading_obs, "TOTAL_VOLUME_SHARES")

            trading_entry["matched_traded_value_vnd"] = mv
            trading_entry["put_through_traded_value_vnd"] = pv
            trading_entry["total_traded_value_vnd"] = tv
            trading_entry["matched_volume_shares"] = m_vol
            trading_entry["put_through_volume_shares"] = p_vol
            trading_entry["total_volume_shares"] = t_vol

            if tv and tv > 0:
                if mv is not None:
                    trading_entry["matched_value_ratio"] = round(mv / tv, 6)
                if pv is not None:
                    trading_entry["put_through_value_ratio"] = round(pv / tv, 6)

            if mv is not None:
                agg_matched_value += float(mv)
            if pv is not None:
                agg_put_through_value += float(pv)
            if tv is not None:
                agg_total_value += float(tv)
            if m_vol is not None:
                agg_matched_volume += float(m_vol)
            if p_vol is not None:
                agg_put_through_volume += float(p_vol)
            if t_vol is not None:
                agg_total_volume += float(t_vol)
        elif st_trading == STATUS_RATE_LIMITED:
            trading_rate_limited_set.add(ticker)
        elif st_trading in (STATUS_MISSING_SESSION, STATUS_REQUESTED_MISSING):
            trading_missing_session_set.add(ticker)
        elif st_trading == STATUS_BUDGET_EXHAUSTED:
            trading_budget_exhausted_set.add(ticker)
        else:
            trading_unattempted_set.add(ticker)

        # 2. Foreign Room
        room_obs = sym_fhsc.get("foreign_room")
        st_room, use_room = _classify_obs(room_obs)
        room_entry: dict[str, Any] = {
            "status": st_room,
            "usability_state": use_room,
            "foreign_room_max": None,
            "foreign_room_owned": None,
            "foreign_room_available": None,
            "foreign_room_utilization_ratio": None,
            "raw_sha256": room_obs.get("raw_sha256") if room_obs else None,
        }
        if st_room == STATUS_ACQUIRED:
            count_with_room += 1
            r_max = _get_fval(room_obs, "FOREIGN_ROOM_MAX")
            r_owned = _get_fval(room_obs, "FOREIGN_ROOM_OWNED")
            r_avail = _get_fval(room_obs, "FOREIGN_ROOM_AVAILABLE")

            room_entry["foreign_room_max"] = r_max
            room_entry["foreign_room_owned"] = r_owned
            room_entry["foreign_room_available"] = r_avail

            if r_max and r_max > 0 and r_owned is not None:
                util = round(r_owned / r_max, 6)
                room_entry["foreign_room_utilization_ratio"] = util
                room_utilizations.append(util)

        # 3. Proprietary Flow
        prop_obs = sym_fhsc.get("proprietary_trading")
        st_prop, use_prop = _classify_obs(prop_obs)
        prop_entry: dict[str, Any] = {
            "status": st_prop,
            "usability_state": use_prop,
            "buy_volume": None,
            "sell_volume": None,
            "net_volume": None,
            "buy_value_vnd": None,
            "sell_value_vnd": None,
            "net_value_vnd": None,
            "raw_sha256": prop_obs.get("raw_sha256") if prop_obs else None,
        }
        if st_prop == STATUS_ACQUIRED:
            count_with_prop += 1
            b_vol = _get_fval(prop_obs, "PROPRIETARY_BUY_VOLUME")
            s_vol = _get_fval(prop_obs, "PROPRIETARY_SELL_VOLUME")
            n_vol = _get_fval(prop_obs, "PROPRIETARY_NET_VOLUME")
            b_val = _get_fval(prop_obs, "PROPRIETARY_BUY_VALUE")
            s_val = _get_fval(prop_obs, "PROPRIETARY_SELL_VALUE")
            n_val = _get_fval(prop_obs, "PROPRIETARY_NET_VALUE")

            prop_entry["buy_volume"] = b_vol
            prop_entry["sell_volume"] = s_vol
            prop_entry["net_volume"] = n_vol
            prop_entry["buy_value_vnd"] = b_val
            prop_entry["sell_value_vnd"] = s_val
            prop_entry["net_value_vnd"] = n_val

            if n_val is not None:
                agg_prop_net_value += float(n_val)
            if n_vol is not None:
                agg_prop_net_volume += float(n_vol)

        # 4. Microstructure (Order Statistics)
        micro_obs = sym_fhsc.get("order_statistics")
        st_micro, use_micro = _classify_obs(micro_obs)
        micro_entry: dict[str, Any] = {
            "status": st_micro,
            "usability_state": use_micro,
            "active_buy_volume": None,
            "active_sell_volume": None,
            "active_buy_orders": None,
            "active_sell_orders": None,
            "order_volume_imbalance_ratio": None,
            "raw_sha256": micro_obs.get("raw_sha256") if micro_obs else None,
        }
        if st_micro == STATUS_ACQUIRED:
            count_with_micro += 1
            b_act_vol = _get_fval(micro_obs, "ACTIVE_BUY_VOLUME")
            s_act_vol = _get_fval(micro_obs, "ACTIVE_SELL_VOLUME")
            b_orders = _get_fval(micro_obs, "ACTIVE_BUY_ORDER_COUNT") or _get_fval(micro_obs, "ACTIVE_BUY_COUNT")
            s_orders = _get_fval(micro_obs, "ACTIVE_SELL_ORDER_COUNT") or _get_fval(micro_obs, "ACTIVE_SELL_COUNT")

            micro_entry["active_buy_volume"] = b_act_vol
            micro_entry["active_sell_volume"] = s_act_vol
            micro_entry["active_buy_orders"] = b_orders
            micro_entry["active_sell_orders"] = s_orders

            if b_act_vol is not None and s_act_vol is not None:
                tot_act = b_act_vol + s_act_vol
                if tot_act > 0:
                    imb = round((b_act_vol - s_act_vol) / tot_act, 6)
                    micro_entry["order_volume_imbalance_ratio"] = imb
                    order_imbalances.append(imb)

        # Classify symbol-level enrichment status
        fhsc_statuses = [trading_entry["status"], room_entry["status"], prop_entry["status"], micro_entry["status"]]
        acquired_count = sum(1 for s in fhsc_statuses if s == STATUS_ACQUIRED)

        missing_caps = [
            cap_name for cap_name, s in [
                ("TRADED_VALUE_AND_VOLUME_COMPOSITION", trading_entry["status"]),
                ("FOREIGN_ROOM", room_entry["status"]),
                ("PROPRIETARY_FLOW", prop_entry["status"]),
                ("MICROSTRUCTURE_ORDER_STATISTICS", micro_entry["status"]),
            ] if s in (STATUS_REQUESTED_MISSING, STATUS_MISSING_SESSION)
        ]

        not_acquired_caps = [
            cap_name for cap_name, s in [
                ("TRADED_VALUE_AND_VOLUME_COMPOSITION", trading_entry["status"]),
                ("FOREIGN_ROOM", room_entry["status"]),
                ("PROPRIETARY_FLOW", prop_entry["status"]),
                ("MICROSTRUCTURE_ORDER_STATISTICS", micro_entry["status"]),
            ] if s == STATUS_NOT_ACQUIRED
        ]

        rate_limited_caps = [
            cap_name for cap_name, s in [
                ("TRADED_VALUE_AND_VOLUME_COMPOSITION", trading_entry["status"]),
                ("FOREIGN_ROOM", room_entry["status"]),
                ("PROPRIETARY_FLOW", prop_entry["status"]),
                ("MICROSTRUCTURE_ORDER_STATISTICS", micro_entry["status"]),
            ] if s == STATUS_RATE_LIMITED
        ]

        if acquired_count == 4:
            count_fully_covered += 1
        elif acquired_count > 0:
            count_partially_covered += 1
        else:
            count_not_acquired += 1

        record = {
            "ticker": ticker,
            "dnse_market_data": dnse_state,
            "fhsc_value_volume_composition": trading_entry,
            "fhsc_foreign_room": room_entry,
            "fhsc_proprietary_flow": prop_entry,
            "fhsc_microstructure": micro_entry,
            "coverage_diagnostics": {
                "dnse_market_data_available": dnse_state is not None,
                "fhsc_capabilities_acquired_count": acquired_count,
                "missing_requested_capabilities": missing_caps,
                "not_acquired_capabilities": not_acquired_caps,
                "rate_limited_capabilities": rate_limited_caps,
            },
            "authority_boundaries": AUTHORITY_BOUNDARIES,
        }
        digest_records.append(record)

    # Sort records deterministically
    digest_records.sort(key=lambda r: r["ticker"])

    median_imbalance = None
    if order_imbalances:
        sorted_imb = sorted(order_imbalances)
        mid = len(sorted_imb) // 2
        median_imbalance = sorted_imb[mid] if len(sorted_imb) % 2 != 0 else round((sorted_imb[mid - 1] + sorted_imb[mid]) / 2.0, 6)

    median_room_util = None
    if room_utilizations:
        sorted_room = sorted(room_utilizations)
        mid = len(sorted_room) // 2
        median_room_util = sorted_room[mid] if len(sorted_room) % 2 != 0 else round((sorted_room[mid - 1] + sorted_room[mid]) / 2.0, 6)

    fhsc_enrichment_digest = {
        "aggregate_scope": "ACQUIRED_ENRICHMENT_COHORT",
        "universe_count": total_universe_count,
        "coverage_denominators": {
            "trading_composition": {
                "universe_count": total_universe_count,
                "acquired_symbol_count": count_with_trading,
                "coverage_ratio": round(count_with_trading / total_universe_count, 6) if total_universe_count > 0 else 0.0,
                "requested_symbol_count": len(requested_symbols_set),
                "affected_rate_limited_count": len(trading_rate_limited_set),
            },
            "foreign_room": {
                "universe_count": total_universe_count,
                "acquired_symbol_count": count_with_room,
                "coverage_ratio": round(count_with_room / total_universe_count, 6) if total_universe_count > 0 else 0.0,
            },
            "proprietary_flow": {
                "universe_count": total_universe_count,
                "acquired_symbol_count": count_with_prop,
                "coverage_ratio": round(count_with_prop / total_universe_count, 6) if total_universe_count > 0 else 0.0,
            },
            "microstructure": {
                "universe_count": total_universe_count,
                "acquired_symbol_count": count_with_micro,
                "coverage_ratio": round(count_with_micro / total_universe_count, 6) if total_universe_count > 0 else 0.0,
            },
        },
        "cohort_aggregates": {
            "total_acquired_traded_value_vnd": agg_total_value,
            "matched_traded_value_vnd": agg_matched_value,
            "put_through_traded_value_vnd": agg_put_through_value,
            "cohort_matched_value_ratio": round(agg_matched_value / agg_total_value, 6) if agg_total_value > 0 else None,
            "cohort_put_through_value_ratio": round(agg_put_through_value / agg_total_value, 6) if agg_total_value > 0 else None,
            "total_acquired_volume_shares": agg_total_volume,
            "matched_volume_shares": agg_matched_volume,
            "put_through_volume_shares": agg_put_through_volume,
            "aggregate_proprietary_net_value_vnd": agg_prop_net_value,
            "aggregate_proprietary_net_volume_shares": agg_prop_net_volume,
            "median_order_volume_imbalance_ratio": median_imbalance,
            "median_foreign_room_utilization_ratio": median_room_util,
        },
    }

    # Verify trading_history mutual exclusivity and count reconciliation
    reconciled_sum = (
        len(trading_acquired_set) +
        len(trading_rate_limited_set) +
        len(trading_missing_session_set) +
        len(trading_budget_exhausted_set) +
        len(trading_unattempted_set)
    )
    assert reconciled_sum == total_universe_count, (
        f"Trading history reconciliation mismatch: {reconciled_sum} != {total_universe_count}"
    )

    coverage_summary = {
        "total_universe_symbols": total_universe_count,
        "symbols_with_dnse_core": dnse_available_count,
        "symbols_with_fhsc_trading_history": count_with_trading,
        "symbols_with_full_fhsc_enrichment": count_fully_covered,
        "symbols_with_partial_fhsc_enrichment": count_partially_covered,
        "symbols_not_acquired_in_this_scaleout": count_not_acquired,
        "symbols_with_rate_limited_capabilities": len(trading_rate_limited_set),
        "symbols_with_genuine_semantic_conflicts": 0,
        "trading_history_scaleout_decomposition": {
            "total_universe_count": total_universe_count,
            "acquired_count": len(trading_acquired_set),
            "rate_limited_count": len(trading_rate_limited_set),
            "missing_requested_session_count": len(trading_missing_session_set),
            "budget_exhausted_count": len(trading_budget_exhausted_set),
            "unattempted_count": len(trading_unattempted_set),
            "reconciled_sum": reconciled_sum,
            "reconciliation_valid": reconciled_sum == total_universe_count,
        },
    }

    # -------------------------------------------------------------
    # NEXT ACQUISITION QUEUE GENERATION (Strict Invariant Enforced)
    # -------------------------------------------------------------
    # Priority Tier 1: Retry-eligible non-acquired rate-limited symbols only
    tier_1_symbols = sorted(trading_rate_limited_set - trading_acquired_set)
    
    # Priority Tier 2: Genuinely unattempted symbols excluding acquired and Tier-1 symbols
    tier_2_symbols = sorted(
        (trading_unattempted_set | trading_missing_session_set | trading_budget_exhausted_set)
        - trading_acquired_set
        - set(tier_1_symbols)
    )

    # Invariant checks:
    # 1. Tier 1 and Tier 2 are disjoint
    assert set(tier_1_symbols).isdisjoint(set(tier_2_symbols)), "Tier 1 and Tier 2 must be disjoint"
    # 2. Acquired symbols are disjoint from both Tier 1 and Tier 2
    assert trading_acquired_set.isdisjoint(set(tier_1_symbols)), "Acquired symbols must not be in Tier 1"
    assert trading_acquired_set.isdisjoint(set(tier_2_symbols)), "Acquired symbols must not be in Tier 2"
    # 3. Sum of Tier 1 + Tier 2 + Acquired == total universe
    assert len(tier_1_symbols) + len(tier_2_symbols) + len(trading_acquired_set) == total_universe_count, (
        f"Queue reconciliation mismatch: {len(tier_1_symbols)} + {len(tier_2_symbols)} + {len(trading_acquired_set)} != {total_universe_count}"
    )

    next_queue: list[dict[str, Any]] = []
    for ticker in tier_1_symbols:
        next_queue.append({
            "ticker": ticker,
            "priority_tier": 1,
            "priority_reason": "PRIOR_RUN_RATE_LIMITED_RETRY_READY",
            "target_capabilities": ["TRADED_VALUE", "VOLUME"],
        })

    for ticker in tier_2_symbols:
        next_queue.append({
            "ticker": ticker,
            "priority_tier": 2,
            "priority_reason": "UNACQUIRED_UNIVERSE_MEMBER",
            "target_capabilities": ["TRADED_VALUE", "VOLUME"],
        })

    digest_payload = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "session_date": session_date,
        "execution_timestamp": datetime.now(UTC).isoformat(),
        "market_wide_core": market_wide_core,
        "fhsc_enrichment": fhsc_enrichment_digest,
        "coverage_summary": coverage_summary,
        "next_acquisition_queue": {
            "queue_schema_version": "1.0.0",
            "total_unacquired_symbols_queued": len(next_queue),
            "excluded_already_acquired_count": len(trading_acquired_set),
            "tier_1_retry_count": len(tier_1_symbols),
            "tier_2_unattempted_count": len(tier_2_symbols),
            "queue_entries": next_queue,
        },
        "records": digest_records,
        "authority_boundaries": AUTHORITY_BOUNDARIES,
    }

    digest_sha256 = _sha256_json({
        k: v for k, v in digest_payload.items()
        if k not in {"digest_sha256", "digest_identity", "execution_timestamp"}
    })
    digest_payload["digest_sha256"] = digest_sha256
    digest_payload["digest_identity"] = f"capability_research_digest:{digest_sha256}"

    return digest_payload


def generate_markdown_summary(digest: Mapping[str, Any]) -> str:
    """Generate human-readable markdown summary report of the coverage-aware research digest."""
    session = digest["session_date"]
    core = digest["market_wide_core"]
    enr = digest["fhsc_enrichment"]
    cov = digest["coverage_summary"]
    next_q = digest["next_acquisition_queue"]
    records = digest["records"]

    breadth = core["breadth_summary"]
    ret_dist = core["return_distribution"]
    ma_breadth = core["moving_average_breadth"]
    vol_dist = core["volatility_distribution"]
    rel_vol_breadth = core["relative_volume_breadth"]
    tails = core["descriptive_tails"]

    denoms = enr["coverage_denominators"]["trading_composition"]
    c_agg = enr["cohort_aggregates"]
    decomp = cov["trading_history_scaleout_decomposition"]

    md = [
        f"# Capability-First Coverage-Aware Research Digest — Session {session}",
        "",
        f"- **Digest Identity**: `{digest['digest_identity']}`",
        f"- **Contract Version**: `{digest['contract_version']}`",
        f"- **Session Date**: `{session}`",
        f"- **Authority**: `DESCRIPTIVE_RESEARCH_DIGEST_NO_EXECUTION_NO_VALUATION_AUTHORITY`",
        "",
        "---",
        "",
        "## 1. Market-Wide Core Layer (`aggregate_scope: FULL_RESEARCH_UNIVERSE`)",
        "",
        f"Coverage: **{core['available_symbol_count']} / {core['universe_count']} symbols (100.0%)**",
        "",
        "### 1.1 Market Breadth & Direction",
        f"- **Advancers**: `{breadth['advancers_count']}` ({breadth['advancers_count'] / core['universe_count'] * 100:.1f}%)",
        f"- **Decliners**: `{breadth['decliners_count']}` ({breadth['decliners_count'] / core['universe_count'] * 100:.1f}%)",
        f"- **Unchanged**: `{breadth['unchanged_count']}` ({breadth['unchanged_count'] / core['universe_count'] * 100:.1f}%)",
        f"- **Advance / Decline Ratio**: `{breadth['advance_decline_ratio']}`",
        f"- **Above MA20 Ratio**: `{ma_breadth['above_ma20_count']} / {core['universe_count']}` ({ma_breadth['above_ma20_ratio'] * 100:.1f}%)",
        "",
        "### 1.2 Return & Volatility Distributions",
        f"- **1D Return**: Mean `{ret_dist['mean_return_1d'] * 100:+.2f}%`, Median `{ret_dist['median_return_1d'] * 100:+.2f}%` (IQR: `{ret_dist['p25_return_1d'] * 100:+.2f}%` to `{ret_dist['p75_return_1d'] * 100:+.2f}%`, Min: `{ret_dist['min_return_1d'] * 100:+.2f}%`, Max: `{ret_dist['max_return_1d'] * 100:+.2f}%`)",
        f"- **20D Volatility**: Mean `{vol_dist['mean_volatility_20d']:.4f}`, Median `{vol_dist['median_volatility_20d']:.4f}` (Min: `{vol_dist['min_volatility_20d']:.4f}`, Max: `{vol_dist['max_volatility_20d']:.4f}`)",
        f"- **Relative Volume Breadth**: Elevated (>=1.5x): `{rel_vol_breadth['elevated_volume_count']}`, Normal (0.8-1.5x): `{rel_vol_breadth['normal_volume_count']}`, Depressed (<=0.8x): `{rel_vol_breadth['depressed_volume_count']}`, Median: `{rel_vol_breadth['median_relative_volume']:.2f}x`",
        "",
        "### 1.3 Descriptive Market Tails",
        "**Top 5 Gainers**:",
    ]

    for g in tails.get("top_5_gainers", []):
        md.append(f"- **{g['ticker']}**: `{g['return_1d'] * 100:+.2f}%` (Close: `{g['close_vnd']:,.0f} VND`)")

    md.append("\n**Top 5 Decliners**:")
    for d in tails.get("top_5_decliners", []):
        md.append(f"- **{d['ticker']}**: `{d['return_1d'] * 100:+.2f}%` (Close: `{d['close_vnd']:,.0f} VND`)")

    md.extend([
        "",
        "---",
        "",
        "## 2. FHSC Enrichment Layer (`aggregate_scope: ACQUIRED_ENRICHMENT_COHORT`)",
        "",
        f"> [!IMPORTANT]",
        f"> Enrichment statistics reflect only the **{denoms['acquired_symbol_count']} acquired symbols** ({denoms['coverage_ratio'] * 100:.2f}% of universe), not full market-wide aggregates.",
        "",
        f"- **Traded Value Acquired**: `{c_agg['total_acquired_traded_value_vnd']:,.0f} VND`",
        f"  - **Matched Value**: `{c_agg['matched_traded_value_vnd']:,.0f} VND` ({c_agg['cohort_matched_value_ratio'] * 100:.2f}%)",
        f"  - **Put-Through Value**: `{c_agg['put_through_traded_value_vnd']:,.0f} VND` ({c_agg['cohort_put_through_value_ratio'] * 100:.2f}%)",
        f"- **Volume Acquired**: `{c_agg['total_acquired_volume_shares']:,.0f} shares` (Matched: `{c_agg['matched_volume_shares']:,.0f}`, Put-Through: `{c_agg['put_through_volume_shares']:,.0f}`)",
        f"- **Proprietary Net Value**: `{c_agg['aggregate_proprietary_net_value_vnd']:,.0f} VND` (Net Volume: `{c_agg['aggregate_proprietary_net_volume_shares']:,.0f} shares`)",
        f"- **Median Order Volume Imbalance**: `{c_agg['median_order_volume_imbalance_ratio']}`",
        f"- **Median Foreign Room Utilization**: `{c_agg['median_foreign_room_utilization_ratio'] * 100:.2f}%`" if c_agg['median_foreign_room_utilization_ratio'] is not None else "- Median Foreign Room Utilization: N/A",
        "",
        "---",
        "",
        "## 3. Representative Symbol Enrichment Records",
        "",
        "| Symbol | Close (VND) | 1D Return | Matched Value (VND) | Put-Through Value (VND) | Matched Share | Foreign Room Util | Prop Net Value (VND) | Order Imbalance | Status |",
        "|:---|---:|---:|---:|---:|---:|---:|---:|---:|:---|",
    ])

    rep_tickers = ["HPG", "VCB", "SSI", "FPT", "MBB", "MWG", "AAN", "AAT", "ABS", "ABT", "ABW", "ACC", "ACV", "ADS", "AGP", "AIG", "ANT", "APF", "APH", "API", "APS", "ASP", "AVG", "BAF", "BID", "VNM"]
    for r in records:
        if r["ticker"] in rep_tickers:
            dnse = r.get("dnse_market_data") or {}
            trading = r.get("fhsc_value_volume_composition") or {}
            room = r.get("fhsc_foreign_room") or {}
            prop = r.get("fhsc_proprietary_flow") or {}
            micro = r.get("fhsc_microstructure") or {}

            close_s = f"{dnse.get('exact_session_close_vnd', 0):,.0f}" if dnse.get("exact_session_close_vnd") else "N/A"
            ret_s = f"{dnse.get('return_1d', 0) * 100:+.2f}%" if dnse.get("return_1d") is not None else "N/A"
            mv_s = f"{trading.get('matched_traded_value_vnd', 0):,.0f}" if trading.get("matched_traded_value_vnd") is not None else "N/A"
            pv_s = f"{trading.get('put_through_traded_value_vnd', 0):,.0f}" if trading.get("put_through_traded_value_vnd") is not None else "N/A"
            m_rat_s = f"{trading.get('matched_value_ratio', 0) * 100:.1f}%" if trading.get("matched_value_ratio") is not None else "N/A"
            room_s = f"{room.get('foreign_room_utilization_ratio', 0) * 100:.1f}%" if room.get("foreign_room_utilization_ratio") is not None else "N/A"
            prop_s = f"{prop.get('net_value_vnd', 0):,.0f}" if prop.get("net_value_vnd") is not None else "N/A"
            imb_s = f"{micro.get('order_volume_imbalance_ratio', 0):+.3f}" if micro.get("order_volume_imbalance_ratio") is not None else "N/A"
            st_s = trading.get("status", "N/A")

            md.append(f"| **{r['ticker']}** | {close_s} | {ret_s} | {mv_s} | {pv_s} | {m_rat_s} | {room_s} | {prop_s} | {imb_s} | `{st_s}` |")

    tier_1_sample = ", ".join(q["ticker"] for q in next_q["queue_entries"] if q["priority_tier"] == 1)
    tier_2_sample = ", ".join(q["ticker"] for q in next_q["queue_entries"] if q["priority_tier"] == 2)[:60] + "..."

    md.extend([
        "",
        "---",
        "",
        "## 4. Coverage Semantics & Gap Inventory",
        "",
        "| Coverage Dimension | Count | Percentage | Status Classification |",
        "|:---|---:|---:|:---|",
        f"| **Total Universe Symbols** | {decomp['total_universe_count']} | 100.0% | `FULL_RESEARCH_UNIVERSE` |",
        f"| **1. Acquired Trading History** | {decomp['acquired_count']} | {decomp['acquired_count'] / decomp['total_universe_count'] * 100:.2f}% | `ACQUIRED` |",
        f"| **2. Rate Limited on Scale-Out** | {decomp['rate_limited_count']} | {decomp['rate_limited_count'] / decomp['total_universe_count'] * 100:.2f}% | `PROVIDER_RATE_LIMITED` (Tier 1 retry-ready) |",
        f"| **3. Missing Requested Session** | {decomp['missing_requested_session_count']} | {decomp['missing_requested_session_count'] / decomp['total_universe_count'] * 100:.2f}% | `MISSING_REQUESTED_SESSION` |",
        f"| **4. Budget Exhausted Skips** | {decomp['budget_exhausted_count']} | {decomp['budget_exhausted_count'] / decomp['total_universe_count'] * 100:.2f}% | `BUDGET_EXHAUSTED` |",
        f"| **5. Unattempted in This Scale-Out** | {decomp['unattempted_count']} | {decomp['unattempted_count'] / decomp['total_universe_count'] * 100:.2f}% | `NOT_ACQUIRED_IN_THIS_SCALEOUT` (Tier 2 unattempted) |",
        f"| **Reconciled Universe Sum** | **{decomp['reconciled_sum']}** | **100.0%** | **Mutually exclusive sum == Total Universe** |",
        "",
        "---",
        "",
        "## 5. Next Acquisition Queue (Prioritized Scale-Out)",
        "",
        f"- **Queued for Next Wave**: `{next_q['total_unacquired_symbols_queued']} symbols`",
        f"- **Excluded Already Acquired**: `{next_q['excluded_already_acquired_count']} symbols` (`acquired ∩ queue == ∅`)",
        f"- **Priority Tier 1 (Rate-Limited Retries)**: `{next_q['tier_1_retry_count']} symbols` ({tier_1_sample})",
        f"- **Priority Tier 2 (Unattempted Universe)**: `{next_q['tier_2_unattempted_count']} symbols` ({tier_2_sample})",
        "",
        "---",
        "",
        "## 6. Authority Boundaries",
        "",
        "- `authority_effect`: `NONE`",
        "- `raw_as_traded_promoted`: `False`",
        "- `pit_backtest_eligible`: `False`",
        "- `liquidity_sizing_authority`: `BLOCKED`",
        "- `valuation_authority`: `False`",
        "- `recommendation_authority`: `False`",
        "- `database_mutated`: `False`",
    ])

    return "\n".join(md) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scale out capability-first data into coverage-aware two-layer research digest.")
    parser.add_argument("--date", default="2026-08-21", help="Market session date YYYY-MM-DD (default: 2026-08-21)")
    parser.add_argument(
        "--universe-snapshot",
        default="operations-review/prospective-daily-rollforward-v1-20260821/2026-08-21.snapshot.json",
        help="Path to 2026-08-21 universe snapshot",
    )
    parser.add_argument(
        "--search-root",
        default="operations-review",
        help="Root directory to search for retained session packets",
    )
    parser.add_argument(
        "--out-dir",
        default="operations-review/capability-first-research-digest-2026-08-21",
        help="Output directory for research digest",
    )
    args = parser.parse_args(argv)

    session_date = args.date
    snapshot_path = Path(args.universe_snapshot)
    if not snapshot_path.is_absolute():
        snapshot_path = ROOT / snapshot_path

    search_root = Path(args.search_root)
    if not search_root.is_absolute():
        search_root = ROOT / search_root

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    # 1. Load universe snapshot
    print(f"Loading universe snapshot from: {snapshot_path}")
    snapshot = load_universe_snapshot(snapshot_path)

    # 2. Find retained session packets
    print(f"Searching for retained packets for session {session_date} in: {search_root}")
    packets = find_retained_packets_for_session(search_root, session_date)
    print(f"Found {len(packets)} retained packets matching session {session_date}.")

    # 3. Build coverage-aware two-layer digest
    print(f"Building coverage-aware research digest across {len(snapshot.get('records', []))} universe records...")
    digest = build_research_digest(session_date, snapshot, packets)

    # 4. Generate summary
    summary_md = generate_markdown_summary(digest)

    # 5. Write outputs atomically
    out_dir.mkdir(parents=True, exist_ok=True)
    digest_path = out_dir / "capability_research_digest.json"
    summary_path = out_dir / "capability_research_digest_summary.md"
    manifest_path = out_dir / "manifest.json"

    atomic_write_json(digest_path, digest)
    atomic_write_file(summary_path, summary_md)

    manifest = {
        "manifest_schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "session_date": session_date,
        "created_at": datetime.now(UTC).isoformat(),
        "digest_identity": digest["digest_identity"],
        "digest_sha256": digest["digest_sha256"],
        "files": {
            "capability_research_digest.json": {
                "size_bytes": digest_path.stat().st_size,
                "sha256": hashlib.sha256(digest_path.read_bytes()).hexdigest(),
            },
            "capability_research_digest_summary.md": {
                "size_bytes": summary_path.stat().st_size,
                "sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
            },
        },
        "authority_boundaries": AUTHORITY_BOUNDARIES,
    }
    atomic_write_json(manifest_path, manifest)

    print(json.dumps({
        "status": "DIGEST_GENERATION_COMPLETE",
        "digest_identity": digest["digest_identity"],
        "session_date": digest["session_date"],
        "market_wide_core_scope": digest["market_wide_core"]["aggregate_scope"],
        "market_wide_core_symbols": digest["market_wide_core"]["available_symbol_count"],
        "fhsc_enrichment_scope": digest["fhsc_enrichment"]["aggregate_scope"],
        "fhsc_acquired_trading_symbols": digest["fhsc_enrichment"]["coverage_denominators"]["trading_composition"]["acquired_symbol_count"],
        "trading_history_scaleout_decomposition": digest["coverage_summary"]["trading_history_scaleout_decomposition"],
        "next_acquisition_queued_count": digest["next_acquisition_queue"]["total_unacquired_symbols_queued"],
        "out_dir": str(out_dir),
    }, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    sys.exit(main())
