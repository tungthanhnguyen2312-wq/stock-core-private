"""Basis-aware descriptive features over verified canonical bars; no action policy.

Tactical V3 owns close structure/base/pivot methodology. This adapter invokes those
same pure methods on each qualified timeframe; morphology and ATR add OHLC evidence.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter

import canonical_market_bars as bars
import prospective_market_snapshot_contract as market
import technical_structure_context as structure

CONTRACT_VERSION = "contextual_technical_feature_set/v1"
AUTHORITY_EFFECT = "NONE / DETERMINISTIC_DESCRIPTIVE_TECHNICAL_CONTEXT_ONLY"
TIMEFRAMES = ("1D", "1W", "1M")
MAX_BARS = 252
ATR_LOOKBACK = 14
FAMILIES = ("candle", "gaps", "volatility", "structure", "levels", "base",
            "volume", "continuous_indicators", "patterns", "interpretation")
USABLE = {"AVAILABLE", "DESCRIPTIVE_ONLY"}


def identity(value, *, kind=CONTRACT_VERSION):
    return market.content_identity(value, kind=kind)


def _seal(value, *, kind=CONTRACT_VERSION):
    value.update(identity(value, kind=kind))
    return value


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _ohlc_valid(bar):
    o, h, l, c = (bar.get(k) for k in ("open", "high", "low", "close"))
    return all(_number(v) and v > 0 for v in (o, h, l, c)) and l <= min(o, c) <= max(o, c) <= h


def _signature(bar, *, volume=False):
    fields = ("volume_unit", "volume_basis", "source") if volume else ("price_basis", "price_unit", "source", "instrument")
    return market.canonical({k: bar.get(k) for k in fields})


def _gate(window, required, *, continuous=False, volume=False):
    if len(window) < required:
        return "INSUFFICIENT_HISTORY", ["INSUFFICIENT_LOOKBACK"]
    if any(b.get("status") != "AVAILABLE" or not _ohlc_valid(b)
           or bars.RESEARCH not in b.get("fitness", {}).get("allowed_uses", []) for b in window):
        return "SOURCE_FIELD_UNAVAILABLE", ["SOURCE_OHLC_OR_RESEARCH_USE_UNAVAILABLE"]
    if any(b["timeframe"] != "1D" and b["period_completeness"] != "COMPLETE" for b in window):
        return "INSUFFICIENT_HISTORY", ["INCOMPLETE_AGGREGATE_CONSTITUENTS"]
    if len({_signature(b) for b in window}) != 1 or window[-1].get("price_basis") not in {
            "RAW_AS_TRADED", "PIT_CA_ADJUSTED", "RETROSPECTIVE_ADJUSTED"}:
        return "BLOCKED_BASIS", ["INCOMPATIBLE_PRICE_BASIS_OR_SOURCE"]
    basis = window[-1]["price_basis"]
    if len(window) > 1 and any(b.get("corporate_action_crossing", {}).get("state") == "EVENTS_OBSERVED"
                             and b.get("corporate_action_crossing", {}).get("comparability") != "PIT_NORMALIZED" for b in window):
        return "BLOCKED_CA_COMPARABILITY", ["CORPORATE_ACTION_WINDOW_NOT_COMPARABLE"]
    if continuous and basis == "RAW_AS_TRADED" and any(
            b.get("fitness", {}).get("continuous_indicator_use") != "QUALIFIED" for b in window):
        return "BLOCKED_CA_COMPARABILITY", ["RAW_CONTINUOUS_COMPARABILITY_NOT_ESTABLISHED"]
    if volume:
        if len({_signature(b, volume=True) for b in window}) != 1:
            return "BLOCKED_BASIS", ["INCOMPATIBLE_VOLUME_SERIES_OR_UNIT"]
        if any(not _number(b.get("volume")) or b["volume"] < 0 for b in window):
            return "SOURCE_FIELD_UNAVAILABLE", ["VOLUME_UNAVAILABLE"]
    # Unknown source units and raw continuity remain descriptive, never PIT authority.
    warnings = []
    if basis == "RETROSPECTIVE_ADJUSTED":
        warnings.append("RETROSPECTIVE_CURRENT_RESEARCH_ONLY_NOT_HISTORICAL_AS_KNOWN")
    if basis == "RAW_AS_TRADED" and any(b.get("corporate_action_crossing", {}).get("state") == "UNKNOWN_EVENT_COVERAGE" for b in window):
        warnings.append("RAW_TRADED_OBSERVATION_ECONOMIC_CONTINUITY_UNQUALIFIED")
    if volume and window[-1].get("volume_unit") in (None, "UNKNOWN"):
        warnings.append("UNKNOWN_NATIVE_VOLUME_UNIT_DIMENSIONLESS_CONTEXT_ONLY")
    return ("DESCRIPTIVE_ONLY" if warnings else "AVAILABLE"), warnings


def morphology(bar):
    """Primitive geometry, including explicit undefined zero-range ratios."""
    if not _ohlc_valid(bar):
        return None
    o, h, l, c = (bar[k] for k in ("open", "high", "low", "close"))
    span, body = h - l, abs(c - o)
    upper, lower = h - max(o, c), min(o, c) - l
    midpoint = l + span / 2
    return {"open": o, "high": h, "low": l, "close": c, "range": span,
            "body_size": body, "body_direction": "BULLISH" if c > o else "BEARISH" if c < o else "FLAT",
            "body_range_ratio": body / span if span else None, "upper_wick": upper, "lower_wick": lower,
            "upper_wick_range_ratio": upper / span if span else None,
            "lower_wick_range_ratio": lower / span if span else None,
            "close_location": (c - l) / span if span else None,
            "open_location": (o - l) / span if span else None,
            "midpoint": midpoint, "distance_from_midpoint": c - midpoint,
            "ratio_status": "AVAILABLE" if span else "NOT_APPLICABLE_ZERO_RANGE"}


def _true_range(current, previous):
    return max(current["high"] - current["low"], abs(current["high"] - previous["close"]),
               abs(current["low"] - previous["close"]))


def _distribution(values, current):
    median = statistics.median(values)
    return {"minimum": min(values), "maximum": max(values), "mean": statistics.mean(values),
            "median": median, "percentile": sum(v <= current for v in values) / len(values),
            "normalized_by_median": current / median if median else None}


def _bar_units(value):
    """Existing daily-owner methods count supplied observations, now D/W/M bars."""
    names = {"confirmation_lag_sessions": "confirmation_lag_bars",
             "base_duration_sessions": "base_duration_bars", "duration_cap_sessions": "duration_cap_bars",
             "lookback_sessions": "lookback_bars", "prior_window_offset_sessions": "prior_window_offset_bars",
             "recent_realized_volatility_20d": "recent_realized_volatility_20_bars",
             "prior_realized_volatility_20d": "prior_realized_volatility_20_bars",
             "sessions_required": "bars_required", "sessions_available": "bars_available"}
    return {names.get(k, k): v for k, v in value.items()}


def _level(level, window, *, role):
    price = level["value"]
    hits = [i for i, b in enumerate(window[:-1]) if b["close"] == price]
    current = window[-1]
    tested = current["low"] <= price <= current["high"]
    beyond = current["close"] < price if role == "support" else current["close"] > price
    rejection = tested and (current["close"] > price if role == "support" else current["close"] < price)
    return {"price": price, "method": "TACTICAL_V1_PRIOR_WINDOW_CLOSE_EXTREMUM",
            "source_bar_identities": [window[i]["artifact_identity"] for i in hits],
            "observation_count": len(hits), "age_bars": len(window) - 1 - hits[-1] if hits else None,
            "distance_from_close": current["close"] - price,
            "distance_from_close_pct": current["close"] / price - 1,
            "tests": tested, "closes_beyond": beyond, "rejects": rejection,
            "touch_method": "EXACT_CLOSE_EXTREMUM_OBSERVATIONS_NOT_INFERRED_TOUCHES"}


def _pattern_labels(geometry, current, previous, gap):
    labels = []
    def add(name, conditions):
        labels.append({"label": name, "primitive_conditions": conditions, "action_authority": "NONE"})
    ratio = geometry["body_range_ratio"]
    if ratio is not None and ratio <= 0.1:
        add("DOJI_LIKE", {"body_range_ratio_lte": 0.1})
    if ratio is not None and ratio >= 0.7:
        add("LONG_BODY", {"body_range_ratio_gte": 0.7})
    for side in ("upper", "lower"):
        wick = geometry[f"{side}_wick_range_ratio"]
        if wick is not None and wick >= 0.5:
            add(f"{side.upper()}_REJECTION_MORPHOLOGY", {f"{side}_wick_range_ratio_gte": 0.5})
    if previous:
        if current["high"] <= previous["high"] and current["low"] >= previous["low"]:
            add("INSIDE_BAR", {"high_lte_prior_high": True, "low_gte_prior_low": True})
        if current["high"] > previous["high"] and current["low"] < previous["low"]:
            add("OUTSIDE_BAR", {"high_gt_prior_high": True, "low_lt_prior_low": True})
        bullish = current["close"] > current["open"] and previous["close"] < previous["open"]
        bearish = current["close"] < current["open"] and previous["close"] > previous["open"]
        if (bullish or bearish) and min(current["open"], current["close"]) <= min(previous["open"], previous["close"]) and max(current["open"], current["close"]) >= max(previous["open"], previous["close"]):
            add("BULLISH_ENGULFING_MORPHOLOGY" if bullish else "BEARISH_ENGULFING_MORPHOLOGY",
                {"opposite_body_direction": True, "current_body_contains_prior_body": True})
    if gap is not None and gap != 0:
        add("GAP_UP_MORPHOLOGY" if gap > 0 else "GAP_DOWN_MORPHOLOGY", {"observed_open_minus_prior_close": gap})
    return labels


def evaluate_timeframe(series, *, ticker, timeframe, as_of_session, knowledge_cutoff):
    """No unusable row is silently skipped inside a feature's bounded window."""
    cutoff = market._utc(knowledge_cutoff, "feature_cutoff")
    ordered = sorted(series, key=lambda b: (b["period_start"], b["artifact_identity"]))
    seen = {}
    for bar in ordered:
        if (bar.get("contract_version") != bars.CONTRACT_VERSION or bar.get("timeframe") != timeframe
                or bar.get("instrument", {}).get("ticker") != ticker
                or any(bar.get(k) != v for k, v in identity(bar, kind="canonical_market_bar").items())):
            raise ValueError("FEATURE_CANONICAL_BAR_IDENTITY_INVALID")
        known = bar.get("knowledge_available_at")
        if (bar.get("last_trading_session") and bar["last_trading_session"] > as_of_session
                or known and market._utc(known, "bar_known") > cutoff
                or market._utc(bar["knowledge_cutoff"], "bar_cutoff") > cutoff):
            raise ValueError("FEATURE_FUTURE_BAR_OR_CUTOFF")
        key = bar["period_start"]
        if key in seen and seen[key] != bar:
            raise ValueError("FEATURE_CONFLICTING_PERIOD")
        seen[key] = bar
    ordered = list(seen.values())
    eligible = [i for i, b in enumerate(ordered) if timeframe == "1D" or b["period_completeness"] == "COMPLETE"]
    selected = ordered[:eligible[-1] + 1][-MAX_BARS:] if eligible else []
    current = selected[-1] if selected else None
    source_ids = [b["artifact_identity"] for b in selected]
    context = {"ticker": ticker, "instrument": current.get("instrument") if current else {"ticker": ticker},
               "as_of_session": as_of_session, "timeframe": timeframe, "knowledge_cutoff": knowledge_cutoff,
               "knowledge_available_at": max((b["knowledge_available_at"] for b in selected if b.get("knowledge_available_at")), default=None),
               "canonical_source_bar_identity": current.get("artifact_identity") if current else None,
               "source_bar_identities": source_ids,
               "source_constituent_identity_digest": market.sha256_hex(market.canonical([
                   b.get("constituent_observation_identities", []) for b in selected])),
               "price_basis": current.get("price_basis") if current else None,
               "price_unit": current.get("price_unit") if current else None,
               "volume_unit": current.get("volume_unit") if current else None,
               "volume_basis": current.get("volume_basis") if current else None,
               "source": current.get("source") if current else None,
               "corporate_action_comparability": current.get("corporate_action_crossing") if current else None,
               "available_lookback": len(selected), "history_cap_bars": MAX_BARS,
               "freshness": "CURRENT_SESSION" if current and current["last_trading_session"] == as_of_session else "COMPLETED_PERIOD_CONTEXT" if current and timeframe != "1D" else "STALE_OR_UNAVAILABLE",
               "temporal_fitness": "UNAVAILABLE" if not current else "CURRENT_SESSION" if timeframe == "1D" and current["last_trading_session"] == as_of_session else "STALE_LAST_OBSERVATION" if timeframe == "1D" else "LATEST_COMPLETE_PERIOD_WITH_NEWER_UNQUALIFIED_PERIOD" if current["artifact_identity"] != ordered[-1]["artifact_identity"] else "LATEST_COMPLETE_PERIOD",
               "last_observed_session": current.get("last_trading_session") if current else None,
               "latest_period": {k: ordered[-1].get(k) for k in ("artifact_identity", "period_completeness", "period_start", "period_end")} if ordered else None,
               "historical_pit_authority": False, "non_voting": True, "authority_effect": AUTHORITY_EFFECT}
    context = _seal(context, kind="contextual_technical_inputs/v1")
    features = {}
    def result(name, required, values=None, *, continuous=False, volume=False, window_size=None):
        window = selected[-(window_size or required):]
        status, codes = _gate(window, required, continuous=continuous, volume=volume)
        if not selected and timeframe != "1D":
            status, codes = "INSUFFICIENT_HISTORY", ["NO_COMPLETE_CALENDAR_QUALIFIED_PERIOD"]
        if current and timeframe == "1D" and current["last_trading_session"] != as_of_session:
            codes = sorted(set(codes + ["NOT_CURRENT_SESSION"]))
            if status == "AVAILABLE":
                status = "DESCRIPTIVE_ONLY"
        features[name] = {"status": status, "reason_codes": sorted(codes), "values": values if status in USABLE else None,
                          "required_lookback": required, "actual_available_lookback": len(window),
                          "input_context_identity": context["artifact_identity"],
                          "calculation_inputs": {"first_bar_identity": window[0]["artifact_identity"] if window else None,
                              "last_bar_identity": current.get("artifact_identity") if current else None,
                              "window_bar_count": len(window)},
                          "allowed_use": "CURRENT_RESEARCH_DESCRIPTIVE_ONLY" if status in USABLE else "NONE",
                          "non_voting": True}
        return features[name]
    geometry = morphology(current) if current else None
    result("candle", 1, geometry)
    previous = selected[-2] if len(selected) >= 2 else None
    prior_status, _ = _gate(selected[-2:], 2)
    comparable_previous = previous if prior_status in USABLE else None
    true_range_previous = previous if _gate(selected[-2:], 2, continuous=True)[0] in USABLE else None
    observed_previous = previous if previous and _ohlc_valid(previous) and current and _ohlc_valid(current) and _signature(previous) == _signature(current) else None
    gaps = {"observed_open_minus_prior_close": current["open"] - observed_previous["close"],
            "observed_open_vs_prior_close_pct": current["open"] / observed_previous["close"] - 1,
            "observed_low_minus_prior_high": current["low"] - observed_previous["high"],
            "observed_high_minus_prior_low": current["high"] - observed_previous["low"],
            "true_range": _true_range(current, true_range_previous) if true_range_previous else None,
            "true_range_status": "SOURCE_SCOPED_RESEARCH_ONLY" if true_range_previous else "COMPARABLE_PREVIOUS_CLOSE_UNQUALIFIED",
            "economic_gap_interpretation": "UNQUALIFIED" if not true_range_previous or current["price_basis"] == "RAW_AS_TRADED" else "SOURCE_SCOPED_RESEARCH_ONLY"} if observed_previous else None
    gap_result = result("gaps", 2, gaps)
    if observed_previous and gap_result["status"] == "BLOCKED_CA_COMPARABILITY":
        gap_result.update(status="DESCRIPTIVE_ONLY", values=gaps, allowed_use="RAW_OBSERVED_GAP_DESCRIPTION_ONLY")
    ranges = [b["high"] - b["low"] for b in selected[-20:] if _ohlc_valid(b)]
    vol_values = None
    if len(ranges) == 20:
        old, new = statistics.mean(ranges[:10]), statistics.mean(ranges[10:])
        ratio = new / old if old else None
        vol_values = {"current_true_range": gaps.get("true_range") if gaps else None,
                      "rolling_range_distribution": _distribution(ranges, ranges[-1]),
                      "recent_over_prior_mean_range": ratio,
                      "range_context": "COMPRESSION" if ratio is not None and ratio <= structure.COMPRESSION_RATIO else "EXPANSION" if ratio is not None and ratio >= structure.EXPANSION_RATIO else "STABLE" if ratio is not None else "NOT_APPLICABLE_ZERO_PRIOR_RANGE"}
    result("volatility", 20, vol_values)
    closes = [b["close"] for b in selected if _ohlc_valid(b)]
    sessions = [b["last_trading_session"] for b in selected if _ohlc_valid(b)]
    structural = levels = base = None
    if _gate(selected[-250:], 20)[0] in USABLE:
        window = closes[-20:]
        owned = structure._structure(window)
        swings = structure._confirm_swings(closes[-250:], sessions[-250:])
        swing_context = structure._swing_structure_context(swings)
        bos = structure._bos_v3(closes, sessions, swing_context)
        pivot = structure._pivot_v3(closes, owned, swing_context)
        breakout = structure._breakout_state_v3(closes, pivot)
        slope = structure._ma20_slope(closes)
        ma20 = structure._ma(window)
        direction = "UP" if slope.get("slope_state") == "RISING" and closes[-1] > ma20 else "DOWN" if slope.get("slope_state") == "FALLING" and closes[-1] < ma20 else "RANGE" if slope.get("status") == "AVAILABLE" else "UNKNOWN"
        reference = "SMA20_PLUS_EXISTING_5_BAR_SLOPE"
        if _gate(selected[-250:], 20, continuous=True)[0] not in USABLE:
            direction = {"UPTREND": "UP", "DOWNTREND": "DOWN", "RANGE": "RANGE"}.get(swing_context["market_structure_state"], "UNKNOWN")
            reference = "RAW_CONFIRMED_SWING_SEQUENCE_ONLY_CONTINUOUS_REFERENCE_BLOCKED"
        structural = {"method": structure.CONTRACT_VERSION, "close_only_structure": owned,
                      "swing_sequence": swings, "swing_structure": _bar_units(swing_context), "bos": bos,
                      "choch": structure._choch_v3(swing_context, bos), "pivot": pivot,
                      "breakout": breakout, "breakout_event": structure._breakout_event(closes),
                      "direction": direction, "trend_reference": reference,
                      "range_state": structure._range_state(window)}
        recent_high, recent_low = max(b["high"] for b in selected[-20:]), min(b["low"] for b in selected[-20:])
        structural["recent_traded_range_location"] = {"high": recent_high, "low": recent_low,
            "distance_from_high_pct": closes[-1] / recent_high - 1,
            "distance_from_low_pct": closes[-1] / recent_low - 1,
            "position": (closes[-1] - recent_low) / (recent_high - recent_low) if recent_high != recent_low else None}
        high_status, high_reasons = _gate(selected[-252:], 252)
        high_window = selected[-252:]
        structural["high_window_252"] = {"status": high_status, "reason_codes": high_reasons,
            "required_lookback": 252, "actual_available_lookback": len(high_window),
            "values": {"high": max(b["high"] for b in high_window), "low": min(b["low"] for b in high_window),
                "close_distance_from_high_pct": closes[-1] / max(b["high"] for b in high_window) - 1,
                "close_distance_from_low_pct": closes[-1] / min(b["low"] for b in high_window) - 1} if high_status in USABLE else None}
        levels = {"nearest_support": _level(owned["support"], selected[-20:], role="support"),
                  "nearest_resistance": _level(owned["resistance"], selected[-20:], role="resistance"),
                  "retest_state": "RETEST" if breakout.get("breakout_state") == "TESTING_PIVOT" and breakout.get("prior_close_above_pivot") else "NOT_ESTABLISHED",
                  "location": owned["structure_status"]}
        duration = structure._base_duration(window, closes, owned["support"]["value"], owned["resistance"]["value"])
        width = owned["resistance"]["value"] - owned["support"]["value"]
        base = {**_bar_units(duration), "lower_boundary": owned["support"]["value"], "upper_boundary": owned["resistance"]["value"],
                "width": width, "width_over_close": width / closes[-1], "position": owned["range_position"],
                "distance_to_upper": closes[-1] - owned["resistance"]["value"], "distance_to_lower": closes[-1] - owned["support"]["value"],
                "compression": structure._range_state(window), "breakout_state": breakout.get("breakout_state"),
                "state": "NO_LONGER_VALID" if breakout.get("breakout_state") == "FAILED_BREAKOUT" else "EXPANDING_OR_BREAKING" if owned["structure_status"] in ("BREAKOUT_CONFIRMED_BY_RULE", "BREAKDOWN_CONFIRMED_BY_RULE") else "ESTABLISHED" if duration["base_status"] == "IN_BASE" else "NEWLY_FORMING"}
    # These owners use up to 250 bars; every required constituent is checked, not
    # just today's bar or the final 20 closes.
    result("structure", 20, structural, window_size=250)
    result("levels", 20, levels, window_size=250)
    result("base", 20, base, window_size=250)
    continuous_parts = {}
    def continuous_part(name, required, compute):
        window = selected[-required:]
        status, reasons = _gate(window, required, continuous=True)
        continuous_parts[name] = {"status": status, "reason_codes": sorted(reasons),
            "required_lookback": required, "actual_available_lookback": len(window),
            "values": compute(window) if status in USABLE else None}
    continuous_part("atr14", 15, lambda w: statistics.mean([_true_range(w[i], w[i-1]) for i in range(1, 15)]))
    continuous_part("sma20", 20, lambda w: structure._ma([b["close"] for b in w]))
    continuous_part("sma20_slope", 25, lambda w: _bar_units(structure._ma20_slope([b["close"] for b in w])))
    continuous_part("momentum_20_bars", 20, lambda w: w[-1]["close"] / w[0]["close"] - 1)
    continuous_part("realized_close_volatility_19_returns", 20, lambda w: statistics.pstdev([w[i]["close"] / w[i-1]["close"] - 1 for i in range(1, 20)]))
    continuous_part("self_relative_volatility", 31, lambda w: _bar_units(structure._self_relative_volatility([b["close"] for b in w])))
    continuous_part("high_low_252", 252, lambda w: {"high": max(b["high"] for b in w), "low": min(b["low"] for b in w),
        "close_distance_from_high_pct": w[-1]["close"] / max(b["high"] for b in w) - 1,
        "close_distance_from_low_pct": w[-1]["close"] / min(b["low"] for b in w) - 1})
    continuous_feature = result("continuous_indicators", 15, continuous_parts, continuous=True, window_size=15)
    usable_parts = [v for v in continuous_parts.values() if v["status"] in USABLE]
    if usable_parts:
        continuous_feature.update(status="DESCRIPTIVE_ONLY" if len(usable_parts) < len(continuous_parts) or any(v["status"] == "DESCRIPTIVE_ONLY" for v in usable_parts) else "AVAILABLE",
                                  values=continuous_parts, reason_codes=sorted(set(continuous_feature["reason_codes"] + (["PARTIAL_CONTINUOUS_FEATURE_LOOKBACK"] if len(usable_parts) < len(continuous_parts) else []))))
    else:
        # Keep independently blocked component statuses visible, without numeric imputation.
        continuous_feature["components"] = continuous_parts
    if base is not None:
        atr = continuous_parts["atr14"]["values"]
        base["width_over_atr14"] = base["width"] / atr if atr else None
        base["atr_normalization_status"] = continuous_parts["atr14"]["status"]
    volumes = [b.get("volume") for b in selected[-20:]]
    volume_values = None
    if len(volumes) == 20 and all(_number(v) and v >= 0 for v in volumes):
        distribution = _distribution(volumes, volumes[-1])
        old, new = statistics.mean(volumes[:10]), statistics.mean(volumes[10:])
        volume_values = {"current_native_volume": volumes[-1], "native_unit": current["volume_unit"],
                         "distribution": distribution, "relative_to_median": distribution["normalized_by_median"],
                         "relative_to_mean": volumes[-1] / distribution["mean"] if distribution["mean"] else None,
                         "ratio_status": "AVAILABLE" if distribution["median"] else "NOT_APPLICABLE_ZERO_VOLUME_REFERENCE",
                         "trend": "RISING" if new > old else "FALLING" if new < old else "FLAT",
                         "participation_context": "EXPANSION" if new > old else "CONTRACTION" if new < old else "STABLE",
                         "breakout_retest_context": structural["breakout"]["breakout_state"] if structural else "UNKNOWN",
                         "participant_inference": "NONE", "economic_value_or_shares_conversion": "NONE"}
    result("volume", 20, volume_values, volume=True)
    labels = _pattern_labels(geometry, current, comparable_previous, gaps.get("observed_open_minus_prior_close") if gaps else None) if geometry else None
    pattern = result("patterns", 1, {"labels": labels} if labels is not None else None, window_size=2)
    # A prior incompatible/unusable bar blocks only two-bar labels, never the
    # independent current candle morphology. Preserve that per-label boundary.
    if geometry and features["candle"]["status"] in USABLE:
        pattern.update(status=features["candle"]["status"], values={"labels": labels},
                       allowed_use="CURRENT_RESEARCH_DESCRIPTIVE_ONLY", reason_codes=features["candle"]["reason_codes"][:])
    if labels is not None:
        pattern["reason_codes"] = sorted(set(pattern["reason_codes"] + ["MORPHOLOGY_HAS_ZERO_ACTION_AUTHORITY"]))
    evidence = []
    if features["levels"]["status"] in USABLE:
        for role in ("support", "resistance"):
            level = levels[f"nearest_{role}"]
            if level["tests"] or abs(level["distance_from_close_pct"]) <= structure.NEAR:
                evidence.append(f"AT_{role.upper()}")
            if level["rejects"]:
                evidence.append(f"REJECTS_{role.upper()}")
    if features["base"]["status"] in USABLE:
        evidence.append("INSIDE_BASE" if base["state"] == "ESTABLISHED" else base["state"])
        if abs(closes[-1] / base["upper_boundary"] - 1) <= structure.NEAR:
            evidence.append("NEAR_BASE_UPPER_BOUNDARY")
        if abs(closes[-1] / base["lower_boundary"] - 1) <= structure.NEAR:
            evidence.append("NEAR_BASE_LOWER_BOUNDARY")
    repair = "UNKNOWN"
    if features["structure"]["status"] in USABLE:
        brk = structural["breakout"]["breakout_state"]
        state = structural["swing_structure"]["market_structure_state"]
        event = structural["breakout_event"].get("event")
        repair = "CONTINUING_DETERIORATION" if structural["direction"] == "DOWN" else "SIDEWAYS_RANGE"
        if brk in ("FAILED_BREAKOUT",) or event == "BREAKDOWN_CONFIRMED": repair = "DETERIORATION_AFTER_EXTENSION" if brk == "FAILED_BREAKOUT" else "CONTINUING_DETERIORATION"
        elif structural["choch"].get("choch_state") == "BULLISH_CHOCH_DETECTED_BY_RULE": repair = "REVERSAL_ATTEMPT"
        elif structural["bos"].get("bos_state") == "BULLISH_BOS_DETECTED_BY_RULE": repair = "CONFIRMED_STRUCTURAL_IMPROVEMENT"
        elif state == "UPTREND" and structural["direction"] == "UP": repair = "MATURE_TREND"
        elif state == "EARLY_BULLISH_REVERSAL" or event == "RE_ENTRY_ABOVE_SUPPORT": repair = "EARLY_REPAIR"
        elif features["base"]["status"] in USABLE and base["state"] == "ESTABLISHED": repair = "BASE_FORMATION"
        elif structural["range_state"] == "RANGE_COMPRESSION": repair = "STABILIZATION"
        evidence.append("ON_RETEST" if levels and levels["retest_state"] == "RETEST" else "ON_BREAKOUT" if brk == "BREAKOUT" else "NO_CONFIRMED_BREAKOUT_OR_RETEST")
        if brk == "EXTENDED_AFTER_BREAKOUT": evidence.append("AFTER_EXTENDED_TREND")
        if structural["direction"] == "UP" and closes[-1] < closes[-2]: evidence.append("AFTER_PULLBACK_IN_UPWARD_CONTEXT")
    if features["volatility"]["status"] in USABLE:
        evidence.append("DURING_COMPRESSION" if vol_values["range_context"] == "COMPRESSION" else "AFTER_EXPANSION" if vol_values["range_context"] == "EXPANSION" else "RANGE_VOLATILITY_STABLE")
    interpretation = result("interpretation", 20, {"evidence_states": sorted(set(evidence)), "repair_context": repair,
                              "pattern_interpretation": "CONTEXT_DOES_NOT_ESTABLISH_PREDICTIVE_OR_ACTION_MEANING",
                              "confirmation_evidence": structural.get("bos") if structural else None,
                              "invalidation_evidence": {"owner": structure.CONTRACT_VERSION,
                                  "support_location": levels.get("nearest_support") if levels else None,
                                  "resistance_location": levels.get("nearest_resistance") if levels else None,
                                  "action_boundary": "NONE_EXISTING_POLICY_ONLY"},
                              "supporting_observations": [v for v in sorted(set(evidence)) if v in {"AT_SUPPORT", "REJECTS_SUPPORT", "ON_RETEST", "ON_BREAKOUT", "INSIDE_BASE"}],
                              "contradicting_observations": [v for v in sorted(set(evidence)) if v in {"REJECTS_RESISTANCE", "NO_LONGER_VALID", "AT_RESISTANCE"}]}, window_size=250)
    if any(features[k]["status"] not in USABLE for k in ("structure", "levels", "base", "volatility")) and interpretation["status"] in USABLE:
        interpretation.update(status="DESCRIPTIVE_ONLY", reason_codes=sorted(set(interpretation["reason_codes"] + ["PARTIAL_CONTEXT_DEPENDENCIES"])))
    for label in labels or []:
        label.update(timeframe=timeframe, feature_fitness=pattern["status"], contextual_evidence_states=sorted(set(evidence)),
                     interpretation="DOES_NOT_ESTABLISH_ACTION_OR_PREDICTION",
                     source_bar_identities=[current["artifact_identity"]] + ([previous["artifact_identity"]] if label["label"] in {"INSIDE_BAR", "OUTSIDE_BAR", "BULLISH_ENGULFING_MORPHOLOGY", "BEARISH_ENGULFING_MORPHOLOGY", "GAP_UP_MORPHOLOGY", "GAP_DOWN_MORPHOLOGY"} and previous else []))
    return _seal({"contract_version": CONTRACT_VERSION, "context": context, "features": features,
                  "status": "DESCRIPTIVE_ONLY" if any(f["status"] in USABLE for f in features.values()) else "UNAVAILABLE",
                  "non_voting": True, "authority_effect": AUTHORITY_EFFECT})


def build_context(series, *, ticker, as_of_session, knowledge_cutoff):
    frames = {tf: evaluate_timeframe(series.get(tf, []), ticker=ticker, timeframe=tf,
                                    as_of_session=as_of_session, knowledge_cutoff=knowledge_cutoff) for tf in TIMEFRAMES}
    directions = {tf: f["features"]["structure"]["values"]["direction"] for tf, f in frames.items()
                  if f["features"]["structure"]["status"] in USABLE and f["features"]["structure"]["values"]["direction"] != "UNKNOWN"}
    state = "UNKNOWN_UNAVAILABLE" if not directions else "MIXED_DIVERGENT" if len(set(directions.values())) > 1 else "ALIGNED" if len(directions) == 3 else "PARTIALLY_ALIGNED"
    return _seal({"contract_version": CONTRACT_VERSION, "ticker": ticker, "as_of_session": as_of_session,
                  "knowledge_cutoff": knowledge_cutoff, "timeframes": frames,
                  "multi_timeframe": {"state": state, "directions": directions, "roles": {"1D": "TACTICAL_SESSION", "1W": "TREND_BASE", "1M": "STRUCTURAL"},
                      "status": "DESCRIPTIVE_ONLY" if len(directions) == 3 else "PARTIAL_OR_UNAVAILABLE",
                      "missing_timeframes": sorted(set(TIMEFRAMES) - set(directions)), "weights": None},
                  "non_voting": True, "authority_effect": AUTHORITY_EFFECT})


def build_research_projections(observations, *, ticker, target_session, knowledge_cutoff,
                               source_identity, calendar_evidence=None, ca_events=()):
    """Single normal/replay construction seam; retained observations parsed once."""
    series = bars.research_series(observations, ticker=ticker, target_session=target_session,
        knowledge_cutoff=knowledge_cutoff, source_identity=source_identity,
        calendar_evidence=calendar_evidence, ca_events=ca_events)
    return {"multi_timeframe": bars.project_research_series(series, target_session=target_session,
                                                            knowledge_cutoff=knowledge_cutoff),
            "contextual_technical": build_context(series, ticker=ticker,
                as_of_session=target_session, knowledge_cutoff=knowledge_cutoff)}


def coverage(records):
    result = {}
    for tf in TIMEFRAMES:
        contexts = [r.get("contextual_technical", {}).get("timeframes", {}).get(tf) for r in records.values()]
        contexts = [c for c in contexts if c]
        result[tf] = {"price_basis": dict(sorted(Counter(c["context"]["price_basis"] or "UNAVAILABLE" for c in contexts).items())),
                      "families": {family: {"status_counts": dict(sorted(Counter(c["features"][family]["status"] for c in contexts).items())),
                          "usable_count": sum(c["features"][family]["status"] in USABLE for c in contexts),
                          "primary_blockers": dict(sorted(Counter(next((r for r in c["features"][family]["reason_codes"] if r != "NOT_CURRENT_SESSION"), "NONE") if c["features"][family]["status"] not in USABLE else "NONE" for c in contexts).items()))} for family in FAMILIES},
                      "temporal_fitness": dict(sorted(Counter(c["context"]["temporal_fitness"] for c in contexts).items()))}
        continuous_parts = [(c["features"]["continuous_indicators"].get("values") or
                             c["features"]["continuous_indicators"].get("components") or {}) for c in contexts]
        names = sorted({name for parts in continuous_parts for name in parts})
        result[tf]["continuous_components"] = {name: {
            "status_counts": dict(sorted(Counter(parts.get(name, {}).get("status", "UNAVAILABLE") for parts in continuous_parts).items())),
            "usable_count": sum(parts.get(name, {}).get("status") in USABLE for parts in continuous_parts),
            "qualified_pit_basis_count": sum(c["context"]["price_basis"] == "PIT_CA_ADJUSTED" and parts.get(name, {}).get("status") in USABLE for c, parts in zip(contexts, continuous_parts))}
            for name in names}
    return result


def verified_context_records(artifact, *, session, knowledge_cutoff, verified_bar_contexts):
    """Attach only after the existing parent/bar verifier; never enter decision policy."""
    result = {}
    cutoff = market._utc(knowledge_cutoff, "product_cutoff")
    for ticker, source in (artifact or {}).get("records", {}).items():
        feature = source.get("contextual_technical")
        if feature is None:
            continue
        try:
            bar_context = verified_bar_contexts.get(ticker, {})
            if (bar_context.get("status") != "AVAILABLE" or feature.get("contract_version") != CONTRACT_VERSION
                    or feature.get("ticker") != ticker or feature.get("as_of_session") != session
                    or feature.get("non_voting") is not True or feature.get("authority_effect") != AUTHORITY_EFFECT
                    or market._utc(feature["knowledge_cutoff"], "feature_cutoff") > cutoff
                    or any(feature.get(k) != v for k, v in identity(feature).items())):
                raise ValueError("FEATURE_PARENT_BINDING_INVALID")
            for tf in TIMEFRAMES:
                frame = feature["timeframes"][tf]
                context = frame["context"]
                if (any(frame.get(k) != v for k, v in identity(frame).items())
                        or any(context.get(k) != v for k, v in identity(context, kind="contextual_technical_inputs/v1").items())
                        or context.get("ticker") != ticker or context.get("timeframe") != tf
                        or context.get("as_of_session") != session or context.get("non_voting") is not True
                        or frame.get("non_voting") is not True or frame.get("authority_effect") != AUTHORITY_EFFECT
                        or context.get("historical_pit_authority") is not False
                        or context.get("knowledge_cutoff") != feature["knowledge_cutoff"]):
                    raise ValueError("FEATURE_NESTED_BINDING_INVALID")
                if context.get("knowledge_available_at") and market._utc(context["knowledge_available_at"], "feature_known") > market._utc(feature["knowledge_cutoff"], "feature_cutoff"):
                    raise ValueError("FEATURE_FUTURE_INPUT_CONTEXT")
                projected = bar_context["projection"][tf]["latest_observed" if tf == "1D" else "latest_completed"]
                if context["canonical_source_bar_identity"] != (projected or {}).get("artifact_identity"):
                    # The canonical research summary withholds a malformed source
                    # bar; a verified all-blocked diagnostic must not invent one.
                    diagnostic_only = (projected is None and frame.get("status") == "UNAVAILABLE"
                        and context["canonical_source_bar_identity"] == (context.get("latest_period") or {}).get("artifact_identity")
                        and all(v.get("status") not in USABLE and v.get("values") is None for v in frame["features"].values()))
                    if not diagnostic_only:
                        raise ValueError("FEATURE_CANONICAL_SOURCE_BINDING_INVALID")
                if projected is not None and any(context.get(k) != projected.get(k)
                        for k in ("instrument", "price_basis", "price_unit", "volume_unit", "volume_basis", "source")):
                    raise ValueError("FEATURE_SOURCE_SEMANTICS_MISMATCH")
                if set(frame["features"]) != set(FAMILIES):
                    raise ValueError("FEATURE_FAMILY_CONTRACT_INVALID")
                for value in frame["features"].values():
                    if value.get("input_context_identity") != context["artifact_identity"] or value.get("non_voting") is not True:
                        raise ValueError("FEATURE_INPUT_BINDING_INVALID")
            result[ticker] = {"status": "AVAILABLE", "non_voting": True,
                              "source_artifact_identity": artifact["artifact_identity"], "projection": feature}
        except (ValueError, TypeError, KeyError, AttributeError):
            result[ticker] = {"status": "UNAVAILABLE", "non_voting": True, "reason": "CONTEXTUAL_TECHNICAL_IDENTITY_OR_BINDING_INVALID"}
    return result
