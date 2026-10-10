"""Technical V2: pure descriptive semantics; the tactical owner remains frozen."""
from __future__ import annotations
import statistics
from collections import Counter
import canonical_market_bars as bars
import prospective_market_snapshot_contract as market
import technical_structure_context as structure
import technical_relationship_view as bridge
from contextual_technical_primitives import (USABLE, morphology, finite_number as _number,
    valid_ohlc as _ohlc_valid, series_signature as _signature, canonical_window_fitness as _gate,
    true_range as _true_range, distribution as _distribution, bar_units as _bar_units,
    level_observation as _level, morphology_labels as _pattern_labels)

CONTRACT_VERSION = "contextual_technical_feature_set/v2"
INPUT_VERSION = "contextual_technical_inputs/v2"
AUTHORITY_EFFECT = "NONE / DETERMINISTIC_DESCRIPTIVE_TECHNICAL_CONTEXT_ONLY"
TIMEFRAMES = ("1D", "1W", "1M")
MAX_BARS = 252
FAMILIES = ("candle", "gaps", "volatility", "structure", "levels", "range_consolidation",
    "volume", "continuous_indicators", "patterns", "setup_state")
CLOSE_RANGE_MAP = {"RANGE_COMPRESSION": "CLOSE_RANGE_COMPRESSION", "RANGE_EXPANSION": "CLOSE_RANGE_EXPANSION", "RANGE_STABLE": "CLOSE_RANGE_STABLE"}
CONTEXT_OBSERVATIONS = ("AT_OR_NEAR_SUPPORT", "AT_OR_NEAR_RESISTANCE", "TESTED_SUPPORT_CLOSED_ABOVE",
    "TESTED_RESISTANCE_CLOSED_BELOW", "INSIDE_BOUNDED_RANGE", "NEAR_RANGE_UPPER_BOUNDARY",
    "NEAR_RANGE_LOWER_BOUNDARY", "PIVOT_RETEST_AFTER_PRIOR_CLOSE_ABOVE")
MTF_STATES = ("NO_ELIGIBLE_TIMEFRAME", "SINGLE_TIMEFRAME_AVAILABLE", "SAME_READING", "OPPOSING_READINGS",
    "DIFFERENT_NON_OPPOSING_READINGS", "OPPOSING_READINGS_PRESENT", "BASIS_MISMATCH_NOT_EVALUATED")
VOCABULARY_MANIFEST = {**bridge.VOCABULARY_MANIFEST, "range_state": tuple(bridge.V2_RANGE_MAP),
    "context_observations": CONTEXT_OBSERVATIONS, "close_range_state": tuple(CLOSE_RANGE_MAP.values()),
    "ohlc_range_context": ("OHLC_RANGE_COMPRESSION", "OHLC_RANGE_EXPANSION", "OHLC_RANGE_STABLE", "NOT_APPLICABLE_ZERO_PRIOR_RANGE"),
    "realized_volatility": ("REALIZED_VOLATILITY_CONTRACTION", "REALIZED_VOLATILITY_EXPANSION", "REALIZED_VOLATILITY_STABLE"),
    "multi_timeframe": MTF_STATES, "setup_rule": tuple("R" + str(i) for i in range(12)),
    "feature_status": ("AVAILABLE", "DESCRIPTIVE_ONLY", "INSUFFICIENT_HISTORY", "SOURCE_FIELD_UNAVAILABLE", "BLOCKED_BASIS", "BLOCKED_CA_COMPARABILITY"),
    "owner_bos": tuple(structure.BOS_STATES), "owner_choch": tuple(structure.CHOCH_STATES),
    "owner_breakout": tuple(structure.BREAKOUT_STATES_V3), "owner_event": tuple(structure.BREAKOUT_EVENT_STATES)}

def identity(value, *, kind=CONTRACT_VERSION):
    return market.content_identity(value, kind=kind)

def _seal(value, *, kind=CONTRACT_VERSION):
    value.update(identity(value, kind=kind))
    return value

def realized_volatility(window):
    result = _bar_units(structure._self_relative_volatility([b["close"] for b in window]))
    state = result.pop("self_relative_volatility_state", None)
    if state is not None:
        result["realized_volatility_state"] = "REALIZED_VOLATILITY_" + bridge.checked(state, ("CONTRACTION", "EXPANSION", "STABLE"), "owner_realized_volatility")
    return result

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
               "temporal": bridge.temporal_reading(timeframe=timeframe, as_of_session=as_of_session,
                   last_observed_session=current.get("last_trading_session") if current else None,
                   selected_period=(current["period_start"], current["period_end"]) if current else None,
                   later_periods=[b for b in ordered if not current or b["period_start"] > current["period_start"]]),
               "last_observed_session": current.get("last_trading_session") if current else None,
               "latest_period": {k: ordered[-1].get(k) for k in ("artifact_identity", "period_completeness", "period_start", "period_end")} if ordered else None,
               "historical_pit_authority": False, "non_voting": True, "authority_effect": AUTHORITY_EFFECT}
    context = _seal(context, kind="contextual_technical_inputs/v2")
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
                      "ohlc_range_context": "OHLC_RANGE_COMPRESSION" if ratio is not None and ratio <= structure.COMPRESSION_RATIO else "OHLC_RANGE_EXPANSION" if ratio is not None and ratio >= structure.EXPANSION_RATIO else "OHLC_RANGE_STABLE" if ratio is not None else "NOT_APPLICABLE_ZERO_PRIOR_RANGE"}
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
        direction = "UP" if slope.get("slope_state") == "RISING" and closes[-1] > ma20 else "DOWN" if slope.get("slope_state") == "FALLING" and closes[-1] < ma20 else "NO_CLEAN_AGREEMENT" if slope.get("status") == "AVAILABLE" else "UNKNOWN"
        reading = bridge.swing_reading(swing_context)
        reference = "SMA20_PLUS_EXISTING_5_BAR_SLOPE"
        if _gate(selected[-250:], 20, continuous=True)[0] not in USABLE:
            direction = {"HIGHER_HIGHS_HIGHER_LOWS": "UP", "LOWER_HIGHS_LOWER_LOWS": "DOWN"}.get(reading["swing_relation"],
                "UNKNOWN" if reading["swing_relation"] in {"UNKNOWN", "INSUFFICIENT_CONFIRMED_SWINGS"} else "NO_CLEAN_AGREEMENT")
            slope = {"status": "UNAVAILABLE", "reason_codes": ["CONTINUOUS_REFERENCE_BLOCKED"]}
            reference = "RAW_CONFIRMED_SWING_SEQUENCE_ONLY_CONTINUOUS_REFERENCE_BLOCKED"
        structural = {"method": structure.CONTRACT_VERSION, "close_only_structure": owned,
                      "swing_sequence": swings, **reading,
                      "retained_swing_prices": {k: v for k, v in swing_context.items() if "confirmed_swing" in k},
                      "tactical_owner_market_structure_state": swing_context["market_structure_state"], "bos": bos,
                      "choch": structure._choch_v3(swing_context, bos), "pivot": pivot,
                      "breakout": breakout, "breakout_event": structure._breakout_event(closes),
                      "trend_reading": direction, "trend_reference": reference, "ma20_slope": _bar_units(slope),
                      "close_range_state": CLOSE_RANGE_MAP[structure._range_state(window)]}
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
                  "pivot_test": bridge.pivot_reading(breakout)["pivot_test"],
                  "location": owned["structure_status"]}
        duration = structure._base_duration(window, closes, owned["support"]["value"], owned["resistance"]["value"])
        width = owned["resistance"]["value"] - owned["support"]["value"]
        base = {"range_duration_bars": duration["base_duration_sessions"],
                "bounded_range_membership": "IN_RANGE" if duration["base_status"] == "IN_BASE" else "FORMING",
                "algorithm": "BOUNDED_CLOSE_RANGE_DURATION", "lower_boundary": owned["support"]["value"], "upper_boundary": owned["resistance"]["value"],
                "width": width, "width_over_close": width / closes[-1], "position": owned["range_position"],
                "distance_to_upper": closes[-1] - owned["resistance"]["value"], "distance_to_lower": closes[-1] - owned["support"]["value"],
                "close_range_state": CLOSE_RANGE_MAP[structure._range_state(window)], "breakout_state": breakout.get("breakout_state"),
                "state": "FAILED_BREAKOUT_CONTEXT" if breakout.get("breakout_state") == "FAILED_BREAKOUT" else "RANGE_EXITED_BY_CLOSE" if owned["structure_status"] in ("BREAKOUT_CONFIRMED_BY_RULE", "BREAKDOWN_CONFIRMED_BY_RULE") else "RANGE_ESTABLISHED" if duration["base_status"] == "IN_BASE" else "RANGE_FORMING"}
    # These owners use up to 250 bars; every required constituent is checked, not
    # just today's bar or the final 20 closes.
    result("structure", 20, structural, window_size=250)
    result("levels", 20, levels, window_size=250)
    result("range_consolidation", 20, base, window_size=250)
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
    continuous_part("self_relative_volatility", 31, lambda w: realized_volatility(w))
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
        volume_values = {"current_native_volume": volumes[-1], "native_unit": current["volume_unit"],
                         "distribution": distribution, "relative_to_median": distribution["normalized_by_median"],
                         "relative_to_mean": volumes[-1] / distribution["mean"] if distribution["mean"] else None,
                         "ratio_status": "AVAILABLE" if distribution["median"] else "NOT_APPLICABLE_ZERO_VOLUME_REFERENCE",
                         "window_basis": "LAST_20_INCLUDING_CURRENT",
                         "source_bar_identity": current["artifact_identity"],
                         "participant_inference": "NONE", "economic_value_or_shares_conversion": "NONE"}
    result("volume", 20, volume_values, volume=True)
    labels = _pattern_labels(geometry, current, comparable_previous,
        gaps.get("observed_open_minus_prior_close") if gaps and gap_result["status"] in USABLE else None) if geometry else None
    pattern = result("patterns", 1, {"labels": labels} if labels is not None else None, window_size=2)
    # A prior incompatible/unusable bar blocks only two-bar labels, never the
    # independent current candle morphology. Preserve that per-label boundary.
    if geometry and features["candle"]["status"] in USABLE:
        pattern.update(status=features["candle"]["status"], values={"labels": labels},
                       allowed_use="CURRENT_RESEARCH_DESCRIPTIVE_ONLY", reason_codes=features["candle"]["reason_codes"][:])
    if labels is not None:
        pattern["reason_codes"] = sorted(set(pattern["reason_codes"] + ["MORPHOLOGY_HAS_ZERO_ACTION_AUTHORITY"]))
    observations = []
    if features["levels"]["status"] in USABLE:
        for role in ("support", "resistance"):
            level = levels[f"nearest_{role}"]
            if level["tests"] or abs(level["distance_from_close_pct"]) <= structure.NEAR:
                observations.append("AT_OR_NEAR_" + role.upper())
            if level["rejects"]:
                observations.append("TESTED_SUPPORT_CLOSED_ABOVE" if role == "support" else "TESTED_RESISTANCE_CLOSED_BELOW")
        if levels["pivot_test"] == "TESTING_AFTER_PRIOR_CLOSE_ABOVE_PIVOT":
            observations.append("PIVOT_RETEST_AFTER_PRIOR_CLOSE_ABOVE")
    if features["range_consolidation"]["status"] in USABLE:
        if base["lower_boundary"] <= closes[-1] <= base["upper_boundary"]:
            observations.append("INSIDE_BOUNDED_RANGE")
        for side, boundary in (("UPPER", "upper_boundary"), ("LOWER", "lower_boundary")):
            if abs(closes[-1] / base[boundary] - 1) <= structure.NEAR:
                observations.append("NEAR_RANGE_" + side + "_BOUNDARY")
    clean_structure = structural or {}
    setup = bridge.setup_reading(clean_structure, structure_status=features["structure"]["status"],
        trend=clean_structure.get("trend_reading", "UNKNOWN"), swing=clean_structure.get("swing_relation", "UNKNOWN"),
        range_state=bridge.V2_RANGE_MAP[base["state"]] if base else "UNKNOWN")
    setup["context_observations"] = sorted(set(observations))
    setup["pattern_interpretation"] = "CONTEXT_DOES_NOT_ESTABLISH_PREDICTIVE_OR_ACTION_MEANING"
    setup_feature = result("setup_state", 20, setup, window_size=250)
    if setup_feature["values"] is None:
        setup_feature["diagnostics"] = setup
    for label in labels or []:
        label.update(timeframe=timeframe, feature_fitness=pattern["status"], context_observations=sorted(set(observations)),
                     interpretation="DOES_NOT_ESTABLISH_ACTION_OR_PREDICTION",
                     source_bar_identities=[current["artifact_identity"]] + ([previous["artifact_identity"]] if label["label"] in {"INSIDE_BAR", "OUTSIDE_BAR", "BULLISH_ENGULFING_MORPHOLOGY", "BEARISH_ENGULFING_MORPHOLOGY", "GAP_UP_MORPHOLOGY", "GAP_DOWN_MORPHOLOGY"} and previous else []))
    return _seal({"contract_version": CONTRACT_VERSION, "context": context, "features": features,
                  "status": "DESCRIPTIVE_ONLY" if any(f["status"] in USABLE for f in features.values()) else "UNAVAILABLE",
                  "non_voting": True, "authority_effect": AUTHORITY_EFFECT})


def multi_timeframe(frames):
    readings, exclusions, signatures = {}, {}, set()
    for tf, frame in frames.items():
        context, feature = frame["context"], frame["features"]["structure"]
        fresh = context["temporal"]["state"] in {"CURRENT_SESSION", "CURRENT_PERIOD_COMPLETED", "IMMEDIATELY_PREVIOUS_COMPLETED_PERIOD"}
        if feature["status"] not in USABLE:
            exclusions[tf] = "STRUCTURE_UNUSABLE"
        elif not fresh:
            exclusions[tf] = "TEMPORAL_FITNESS_INELIGIBLE"
        else:
            readings[tf] = feature["values"]["trend_reading"]
            signatures.add(market.canonical({k: context.get(k) for k in ("price_basis", "price_unit", "source", "instrument")}))
    count = len(readings)
    opposing = {"UP", "DOWN"}.issubset(readings.values())
    state = ("BASIS_MISMATCH_NOT_EVALUATED" if len(signatures) > 1 else "NO_ELIGIBLE_TIMEFRAME" if count == 0 else
        "SINGLE_TIMEFRAME_AVAILABLE" if count == 1 else "SAME_READING" if len(set(readings.values())) == 1 else
        "OPPOSING_READINGS" if opposing and count == 2 else "OPPOSING_READINGS_PRESENT" if opposing else "DIFFERENT_NON_OPPOSING_READINGS")
    return {"state": state, "eligible_count": count, "readings": readings, "exclusions": exclusions,
        "roles": {"1D": "SESSION", "1W": "WEEK", "1M": "MONTH"}, "non_voting": True}

def build_context(series, *, ticker, as_of_session, knowledge_cutoff):
    frames = {tf: evaluate_timeframe(series.get(tf, []), ticker=ticker, timeframe=tf,
        as_of_session=as_of_session, knowledge_cutoff=knowledge_cutoff) for tf in TIMEFRAMES}
    return _seal({"contract_version": CONTRACT_VERSION, "ticker": ticker, "as_of_session": as_of_session,
        "knowledge_cutoff": knowledge_cutoff, "timeframes": frames, "multi_timeframe": multi_timeframe(frames),
        "evaluation_scope": "REPLAY_DIAGNOSTIC" if as_of_session < "2026-10-03" else "CURRENT_RESEARCH",
        "authority_status": "NON_AUTHORITATIVE",
        "non_voting": True, "authority_effect": AUTHORITY_EFFECT})

def verify_context(context, ticker=None, session=None):
    ticker, session = ticker or context.get("ticker"), session or context.get("as_of_session")
    if (context.get("contract_version") != CONTRACT_VERSION or context.get("ticker") != ticker or context.get("as_of_session") != session
        or context.get("non_voting") is not True or context.get("authority_effect") != AUTHORITY_EFFECT
        or set(context.get("timeframes", {})) != set(TIMEFRAMES) or any(context.get(k) != v for k, v in identity(context).items())):
        raise ValueError("TECHNICAL_V2_PARENT_BINDING_INVALID")
    cutoff = market._utc(context["knowledge_cutoff"], "technical_cutoff")
    for tf, frame in context["timeframes"].items():
        inputs = frame["context"]
        if (any(frame.get(k) != v for k, v in identity(frame).items()) or
            frame.get("contract_version") != CONTRACT_VERSION or inputs.get("instrument", {}).get("ticker") != ticker or
            any(inputs.get(k) != v for k, v in identity(inputs, kind=INPUT_VERSION).items()) or
            inputs.get("ticker") != ticker or inputs.get("as_of_session") != session or inputs.get("timeframe") != tf or
            inputs.get("non_voting") is not True or inputs.get("historical_pit_authority") is not False or
            inputs.get("knowledge_cutoff") != context["knowledge_cutoff"] or frame.get("non_voting") is not True or
            frame.get("authority_effect") != AUTHORITY_EFFECT or set(frame["features"]) != set(FAMILIES)):
            raise ValueError("TECHNICAL_V2_FRAME_BINDING_INVALID")
        if inputs.get("knowledge_available_at") and market._utc(inputs["knowledge_available_at"], "technical_known") > cutoff:
            raise ValueError("TECHNICAL_V2_FUTURE_INPUTS")
        source_ids = inputs["source_bar_identities"]
        if (len(source_ids) > MAX_BARS or len(source_ids) != len(set(source_ids)) or
            inputs["canonical_source_bar_identity"] != (source_ids[-1] if source_ids else None)):
            raise ValueError("TECHNICAL_V2_SOURCE_BAR_BINDING_INVALID")
        bridge.checked(inputs["temporal"]["state"], bridge.DAILY_TEMPORAL_STATES if tf == "1D" else bridge.PERIOD_TEMPORAL_STATES, "temporal")
        for name, feature in frame["features"].items():
            if feature.get("input_context_identity") != inputs["artifact_identity"] or feature.get("non_voting") is not True:
                raise ValueError("TECHNICAL_V2_FEATURE_BINDING_INVALID")
            bridge.checked(feature["status"], VOCABULARY_MANIFEST["feature_status"], "feature_status")
            if feature["status"] not in USABLE and feature.get("values") is not None:
                raise ValueError("TECHNICAL_V2_BLOCKED_VALUES")
        structural = frame["features"]["structure"].get("values") or {}
        if structural:
            for key, vocabulary in (("trend_reading", bridge.TREND_READINGS), ("swing_relation", bridge.SWING_RELATIONS),
                ("swing_high_relation", bridge.ATOMIC_SWING_RELATIONS), ("swing_low_relation", bridge.ATOMIC_SWING_RELATIONS),
                ("close_range_state", VOCABULARY_MANIFEST["close_range_state"])):
                bridge.checked(structural[key], vocabulary, key)
            for name, key, vocabulary in (("bos", "bos_state", structure.BOS_STATES),
                ("choch", "choch_state", structure.CHOCH_STATES), ("breakout", "breakout_state", structure.BREAKOUT_STATES_V3),
                ("breakout_event", "event", structure.BREAKOUT_EVENT_STATES)):
                value = (structural.get(name) or {}).get(key)
                if value is not None: bridge.checked(value, vocabulary, name)
        volatility = frame["features"]["volatility"].get("values")
        if volatility: bridge.checked(volatility["ohlc_range_context"], VOCABULARY_MANIFEST["ohlc_range_context"], "ohlc_range_context")
        components = frame["features"]["continuous_indicators"].get("values") or frame["features"]["continuous_indicators"].get("components") or {}
        realized = (components.get("self_relative_volatility") or {}).get("values") or {}
        if realized.get("realized_volatility_state") is not None:
            bridge.checked(realized["realized_volatility_state"], VOCABULARY_MANIFEST["realized_volatility"], "realized_volatility")
        ranges = frame["features"]["range_consolidation"].get("values")
        if ranges: bridge.checked(ranges["state"], VOCABULARY_MANIFEST["range_state"], "range_state")
        setup = frame["features"]["setup_state"].get("values") or frame["features"]["setup_state"].get("diagnostics")
        bridge.checked(setup["state"], bridge.SETUP_STATES, "setup_state")
        bridge.checked(setup["rule"], VOCABULARY_MANIFEST["setup_rule"], "setup_rule")
        for conflict in setup["setup_conflicts"]: bridge.checked(conflict, bridge.SETUP_CONFLICTS, "setup_conflict")
        for observation in setup["context_observations"]: bridge.checked(observation, CONTEXT_OBSERVATIONS, "context_observation")
        for value in setup["primitive_availability"].values(): bridge.checked(value, bridge.PRIMITIVE_AVAILABILITY, "primitive_availability")
        volume = frame["features"]["volume"].get("values") or {}
        if {"trend", "participation_context", "breakout_retest_context"}.intersection(volume):
            raise ValueError("TECHNICAL_V2_VOLUME_OWNERSHIP_INVALID")
    if context["multi_timeframe"] != multi_timeframe(context["timeframes"]):
        raise ValueError("TECHNICAL_V2_MTF_BINDING_INVALID")
    return CONTRACT_VERSION

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
                      "temporal_fitness": dict(sorted(Counter(c["context"]["temporal"]["state"] for c in contexts).items()))}
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
            verify_context(feature, ticker, session)
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
                        or any(context.get(k) != v for k, v in identity(context, kind=INPUT_VERSION).items())
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
