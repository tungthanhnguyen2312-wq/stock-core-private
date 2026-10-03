"""Compact deterministic V1/V2 semantic bridge, with no thesis orientation."""
from __future__ import annotations

from datetime import date, timedelta
from collections import Counter

import canonical_market_bars as bars
import prospective_market_snapshot_contract as market
import technical_structure_context as owner
from contextual_technical_primitives import USABLE, finite_number

CONTRACT_VERSION = "technical_participation_relationship_view/v1"
BREAKOUT_RELATIONS = ("ABOVE_PIVOT_WITHIN_EXTENDED_THRESHOLD", "ABOVE_PIVOT_BEYOND_EXTENDED_THRESHOLD",
    "AT_OR_BELOW_PIVOT_WITHIN_NEAR_BAND", "BELOW_PIVOT_BEYOND_NEAR_BAND", "UNKNOWN")
FAILED_BREAKOUT_STATES = ("TRUE", "FALSE", "UNKNOWN")
PIVOT_TEST_STATES = ("TESTING_AFTER_PRIOR_CLOSE_ABOVE_PIVOT", "TESTING_WITHOUT_PRIOR_CLOSE_ABOVE_PIVOT", "NOT_TESTING", "UNKNOWN")
RANGE_STATES = ("FORMING", "ESTABLISHED", "EXITED_BY_CLOSE", "FAILED_BREAKOUT_CONTEXT", "UNKNOWN")
TREND_READINGS = ("UP", "DOWN", "NO_CLEAN_AGREEMENT", "UNKNOWN")
ATOMIC_SWING_RELATIONS = ("HIGHER", "LOWER", "EQUAL", "UNKNOWN")
SWING_RELATIONS = ("HIGHER_HIGHS_HIGHER_LOWS", "LOWER_HIGHS_LOWER_LOWS", "RANGE_EXPANSION_HH_LL",
    "RANGE_CONTRACTION_LH_HL", "EQUAL_SWING_PRICE_UNRESOLVED", "INSUFFICIENT_CONFIRMED_SWINGS", "UNKNOWN")
SETUP_STATES = ("CONTINUING_DETERIORATION", "BEARISH_STRUCTURE_BREAK", "FAILED_BREAKOUT_DETERIORATION",
    "REVERSAL_ATTEMPT", "CONFIRMED_IMPROVEMENT", "EARLY_REPAIR", "EXTENDED", "ESTABLISHED_TREND",
    "RANGE_CONSOLIDATION", "SIDEWAYS", "UNKNOWN")
SETUP_CONFLICTS = ("TREND_UP_WITH_LOWER_HIGHS_LOWER_LOWS", "TREND_DOWN_WITH_HIGHER_HIGHS_HIGHER_LOWS",
    "BEARISH_EVENT_WITH_UP_READING", "BULLISH_EVENT_WITH_DOWN_READING", "BOS_CHOCH_DIRECTION_DISAGREEMENT",
    "FAILED_BREAKOUT_WITH_BULLISH_EVENT")
PRIMITIVE_AVAILABILITY = ("AVAILABLE", "INSUFFICIENT_HISTORY", "UNAVAILABLE")
NATIVE_VOLUME_STATES = ("EXPANSION", "CONTRACTION", "STABLE", "UNDEFINED_ZERO_REFERENCE", "UNKNOWN")
DAILY_TEMPORAL_STATES = ("CURRENT_SESSION", "STALE_LAST_OBSERVATION", "NO_OBSERVATION")
PERIOD_TEMPORAL_STATES = ("CURRENT_PERIOD_COMPLETED", "IMMEDIATELY_PREVIOUS_COMPLETED_PERIOD",
    "STALE_OLDER_COMPLETED_PERIOD", "NO_COMPLETED_PERIOD")
CAUSE_FAMILIES = ("CLOSE_SERIES_STRUCTURE", "OHLC_RANGE", "NATIVE_VOLUME_SERIES", "FOREIGN_VALUE_SERIES")
SETUP_RULES = tuple("R" + str(i) for i in range(12))
COMPLETENESS_KNOWLEDGE = ("OBSERVED_CANONICAL_PERIODS", "UNKNOWN_FROM_V1")
NATIVE_RATIO_STATUS = ("AVAILABLE", "NOT_APPLICABLE_ZERO_VOLUME_REFERENCE", "UNAVAILABLE")
VOCABULARY_MANIFEST = {"breakout_relation": BREAKOUT_RELATIONS, "failed_breakout": FAILED_BREAKOUT_STATES,
    "pivot_test": PIVOT_TEST_STATES, "range_consolidation": RANGE_STATES, "trend_reading": TREND_READINGS,
    "swing_relation": SWING_RELATIONS, "atomic_swing_relation": ATOMIC_SWING_RELATIONS,
    "setup_state": SETUP_STATES, "setup_conflicts": SETUP_CONFLICTS,
    "primitive_availability": PRIMITIVE_AVAILABILITY, "native_volume_state": NATIVE_VOLUME_STATES,
    "daily_temporal": DAILY_TEMPORAL_STATES, "period_temporal": PERIOD_TEMPORAL_STATES,
    "common_cause_family": CAUSE_FAMILIES, "setup_rule": SETUP_RULES,
    "later_period_completeness": COMPLETENESS_KNOWLEDGE, "native_ratio_status": NATIVE_RATIO_STATUS}
V1_TREND_MAP = {"UP": "UP", "DOWN": "DOWN", "RANGE": "NO_CLEAN_AGREEMENT", "UNKNOWN": "UNKNOWN"}
V1_RANGE_MAP = {"NEWLY_FORMING": "FORMING", "ESTABLISHED": "ESTABLISHED", "EXPANDING_OR_BREAKING": "EXITED_BY_CLOSE",
    "NO_LONGER_VALID": "FAILED_BREAKOUT_CONTEXT"}
V2_RANGE_MAP = {"RANGE_FORMING": "FORMING", "RANGE_ESTABLISHED": "ESTABLISHED", "RANGE_EXITED_BY_CLOSE": "EXITED_BY_CLOSE",
    "FAILED_BREAKOUT_CONTEXT": "FAILED_BREAKOUT_CONTEXT"}


def checked(value, vocabulary, concept):
    if value not in vocabulary:
        raise ValueError("TECHNICAL_VOCABULARY_UNKNOWN:" + concept + ":" + str(value))
    return value


def swing_reading(retained):
    """Exact equality of the owner's retained prices, never tolerance or labels."""
    relations, reasons = {}, []
    for side in ("high", "low"):
        previous = (retained.get("previous_confirmed_swing_" + side) or {}).get("price")
        latest = (retained.get("last_confirmed_swing_" + side) or {}).get("price")
        if previous is None or latest is None:
            relations[side] = "UNKNOWN"
            reasons.append("INSUFFICIENT_CONFIRMED_SWING_" + side.upper())
        elif not all(finite_number(v) and v > 0 for v in (previous, latest)):
            relations[side] = "UNKNOWN"
            reasons.append("MALFORMED_RETAINED_SWING_PRICE")
        else:
            relations[side] = "HIGHER" if latest > previous else "LOWER" if latest < previous else "EQUAL"
    high, low = relations["high"], relations["low"]
    if "MALFORMED_RETAINED_SWING_PRICE" in reasons:
        composite = "UNKNOWN"
    elif "UNKNOWN" in (high, low):
        composite = "INSUFFICIENT_CONFIRMED_SWINGS"
    elif "EQUAL" in (high, low):
        composite = "EQUAL_SWING_PRICE_UNRESOLVED"
    else:
        composite = {("HIGHER", "HIGHER"): "HIGHER_HIGHS_HIGHER_LOWS", ("LOWER", "LOWER"): "LOWER_HIGHS_LOWER_LOWS",
            ("HIGHER", "LOWER"): "RANGE_EXPANSION_HH_LL", ("LOWER", "HIGHER"): "RANGE_CONTRACTION_LH_HL"}[(high, low)]
    return {"swing_high_relation": high, "swing_low_relation": low, "swing_relation": composite, "unknown_reasons": sorted(set(reasons))}


def pivot_reading(breakout):
    state = breakout.get("breakout_state")
    if state is not None:
        checked(state, owner.BREAKOUT_STATES_V3, "owner_breakout")
    distance, prior = breakout.get("distance_to_pivot_pct"), breakout.get("prior_close_above_pivot")
    if breakout.get("status") != "AVAILABLE" or not finite_number(distance) or not isinstance(prior, bool):
        return {"breakout_relation": "UNKNOWN", "failed_breakout": "UNKNOWN", "pivot_test": "UNKNOWN"}
    relation = ("ABOVE_PIVOT_BEYOND_EXTENDED_THRESHOLD" if distance > owner.EXTENDED_THRESHOLD else
        "ABOVE_PIVOT_WITHIN_EXTENDED_THRESHOLD" if distance > 0 else
        "AT_OR_BELOW_PIVOT_WITHIN_NEAR_BAND" if distance >= -owner.NEAR else "BELOW_PIVOT_BEYOND_NEAR_BAND")
    testing = -owner.NEAR <= distance <= 0
    return {"breakout_relation": relation, "failed_breakout": "TRUE" if distance < -owner.NEAR and prior else "FALSE",
        "pivot_test": "TESTING_AFTER_PRIOR_CLOSE_ABOVE_PIVOT" if testing and prior else
                      "TESTING_WITHOUT_PRIOR_CLOSE_ABOVE_PIVOT" if testing else "NOT_TESTING"}


def setup_reading(structural, *, structure_status, trend, swing, range_state):
    checked(trend, TREND_READINGS, "trend_reading")
    checked(swing, SWING_RELATIONS, "swing_relation")
    checked(range_state, RANGE_STATES, "range_consolidation")
    structural = structural or {}
    bos, choch, event = (structural.get(k) or {} for k in ("bos", "choch", "breakout_event"))
    bst, cst, est = bos.get("bos_state"), choch.get("choch_state"), event.get("event")
    for value, vocabulary, name in ((bst, owner.BOS_STATES, "owner_bos"), (cst, owner.CHOCH_STATES, "owner_choch"),
                                    (est, owner.BREAKOUT_EVENT_STATES, "owner_event")):
        if value is not None:
            checked(value, vocabulary, name)
    pivot = pivot_reading(structural.get("breakout") or {})
    usable = structure_status in USABLE
    def available(status):
        return "AVAILABLE" if status == "AVAILABLE" else "INSUFFICIENT_HISTORY" if status in {"INSUFFICIENT_HISTORY", "INSUFFICIENT_STRUCTURE", "NOT_AVAILABLE"} else "UNAVAILABLE"
    availability = {"swing": "AVAILABLE" if swing not in {"UNKNOWN", "INSUFFICIENT_CONFIRMED_SWINGS"} else
        "INSUFFICIENT_HISTORY" if swing == "INSUFFICIENT_CONFIRMED_SWINGS" else "UNAVAILABLE",
        "BOS": available(bos.get("status")), "CHoCH": available(choch.get("status")),
        "breakout": "AVAILABLE" if pivot["breakout_relation"] != "UNKNOWN" else "UNAVAILABLE",
        "event": available(event.get("status")), "slope": available((structural.get("ma20_slope") or {}).get("status")),
        "trend_reading": "AVAILABLE" if trend != "UNKNOWN" else "UNAVAILABLE"}
    if not usable:
        return {"state": "UNKNOWN", "rule": "R0", "reason_codes": ["STRUCTURE_UNAVAILABLE"],
                "primitive_availability": {k: "UNAVAILABLE" for k in availability}, "setup_conflicts": []}
    bearish = bst == "BEARISH_BOS_DETECTED_BY_RULE" or cst == "BEARISH_CHOCH_DETECTED_BY_RULE" or est == "BREAKDOWN_CONFIRMED"
    bullish = bst == "BULLISH_BOS_DETECTED_BY_RULE" or cst == "BULLISH_CHOCH_DETECTED_BY_RULE"
    conflicts = []
    if trend == "UP" and swing == "LOWER_HIGHS_LOWER_LOWS": conflicts.append("TREND_UP_WITH_LOWER_HIGHS_LOWER_LOWS")
    if trend == "DOWN" and swing == "HIGHER_HIGHS_HIGHER_LOWS": conflicts.append("TREND_DOWN_WITH_HIGHER_HIGHS_HIGHER_LOWS")
    if bearish and trend == "UP": conflicts.append("BEARISH_EVENT_WITH_UP_READING")
    if bullish and trend == "DOWN": conflicts.append("BULLISH_EVENT_WITH_DOWN_READING")
    if (bst == "BULLISH_BOS_DETECTED_BY_RULE" and cst == "BEARISH_CHOCH_DETECTED_BY_RULE" or
        bst == "BEARISH_BOS_DETECTED_BY_RULE" and cst == "BULLISH_CHOCH_DETECTED_BY_RULE"):
        conflicts.append("BOS_CHOCH_DIRECTION_DISAGREEMENT")
    if pivot["failed_breakout"] == "TRUE" and bullish: conflicts.append("FAILED_BREAKOUT_WITH_BULLISH_EVENT")
    rules = [("R1", pivot["failed_breakout"] == "TRUE", "FAILED_BREAKOUT_DETERIORATION"),
        ("R2", bearish, "BEARISH_STRUCTURE_BREAK"), ("R3", cst == "BULLISH_CHOCH_DETECTED_BY_RULE", "REVERSAL_ATTEMPT"),
        ("R4", bst == "BULLISH_BOS_DETECTED_BY_RULE", "CONFIRMED_IMPROVEMENT"),
        ("R5", est == "RE_ENTRY_ABOVE_SUPPORT", "EARLY_REPAIR"),
        ("R6", swing == "LOWER_HIGHS_LOWER_LOWS" or trend == "DOWN", "CONTINUING_DETERIORATION"),
        ("R7", pivot["breakout_relation"] == "ABOVE_PIVOT_BEYOND_EXTENDED_THRESHOLD", "EXTENDED"),
        ("R8", swing == "HIGHER_HIGHS_HIGHER_LOWS" and trend == "UP", "ESTABLISHED_TREND"),
        ("R9", range_state == "ESTABLISHED", "RANGE_CONSOLIDATION"),
        ("R10", trend == "NO_CLEAN_AGREEMENT" and swing in {"RANGE_EXPANSION_HH_LL", "RANGE_CONTRACTION_LH_HL", "EQUAL_SWING_PRICE_UNRESOLVED"}, "SIDEWAYS")]
    rule, state = next(((rule, state) for rule, matched, state in rules if matched), ("R11", "UNKNOWN"))
    reasons = ["NO_SETUP_RULE_MATCHED"] if rule == "R11" else []
    if trend == "UNKNOWN": reasons.append("TREND_READING_UNKNOWN")
    if swing in {"UNKNOWN", "INSUFFICIENT_CONFIRMED_SWINGS"}: reasons.append(swing)
    return {"state": state, "rule": rule, "reason_codes": sorted(reasons), "primitive_availability": availability,
            "setup_conflicts": sorted(conflicts)}


def temporal_reading(*, timeframe, as_of_session, last_observed_session, selected_period=None, later_periods=None, from_v1=False):
    if last_observed_session and last_observed_session > as_of_session:
        raise ValueError("TECHNICAL_FUTURE_LAST_OBSERVATION")
    reference = bars.period_bounds(as_of_session, timeframe)
    selected = selected_period or (bars.period_bounds(last_observed_session, timeframe) if last_observed_session else None)
    if selected and last_observed_session and tuple(selected) != tuple(bars.period_bounds(last_observed_session, timeframe)):
        raise ValueError("TECHNICAL_SELECTED_PERIOD_BOUNDS_INVALID")
    previous = bars.period_bounds((date.fromisoformat(reference[0]) - timedelta(days=1)).isoformat(), timeframe) if timeframe != "1D" else None
    behind = None
    if timeframe == "1D":
        state = "NO_OBSERVATION" if not last_observed_session else "CURRENT_SESSION" if last_observed_session == as_of_session else "STALE_LAST_OBSERVATION"
        behind = 0 if state == "CURRENT_SESSION" else None
    else:
        if selected:
            if timeframe == "1W": behind = (date.fromisoformat(reference[0]) - date.fromisoformat(selected[0])).days // 7
            else:
                a, b = date.fromisoformat(reference[0]), date.fromisoformat(selected[0])
                behind = 12 * (a.year - b.year) + a.month - b.month
            if behind < 0: raise ValueError("TECHNICAL_FUTURE_SELECTED_PERIOD")
        state = "NO_COMPLETED_PERIOD" if not selected else "CURRENT_PERIOD_COMPLETED" if behind == 0 else "IMMEDIATELY_PREVIOUS_COMPLETED_PERIOD" if behind == 1 else "STALE_OLDER_COMPLETED_PERIOD"
    return {"state": state, "as_of_session": as_of_session, "last_observed_session": last_observed_session,
        "selected_period": {"start": selected[0], "end": selected[1]} if selected else None,
        "reference_period": {"start": reference[0], "end": reference[1]},
        "previous_period": {"start": previous[0], "end": previous[1]} if previous else None,
        "periods_behind": behind, "period_count_semantics": "CANONICAL_CIVIL_PERIODS_NOT_INFERRED_TRADING_SESSIONS",
        "later_period_completeness": {"state": "UNKNOWN_FROM_V1", "counts": None} if from_v1 and timeframe != "1D" else
            {"state": "OBSERVED_CANONICAL_PERIODS", "counts": dict(sorted(Counter(p["period_completeness"] for p in (later_periods or [])).items()))}}


def evidence_keys(ticker, session, timeframe, source_bar_identity, concept, cause="CLOSE_SERIES_STRUCTURE"):
    checked(cause, CAUSE_FAMILIES, "common_cause_family")
    return {"canonical_evidence_key": "canonical_evidence:" + market.sha256_hex(market.canonical(
        [ticker, session, timeframe, source_bar_identity, concept])),
        "common_cause_key": "common_cause:" + market.sha256_hex(market.canonical([ticker, timeframe, cause]))}


def _identity(view):
    return market.content_identity({k: v for k, v in view.items() if k != "view_identity"}, kind=CONTRACT_VERSION)


def _seal(view):
    view.update(_identity(view))
    view["view_identity"] = view["artifact_identity"]
    return view


def build_views(context):
    from contextual_technical_dispatch import verify_context, V1
    version = verify_context(context)
    result = {}
    for tf, frame in context["timeframes"].items():
        inputs, features = frame["context"], frame["features"]
        structural = features["structure"].get("values") if features["structure"]["status"] in USABLE else {}
        structural = structural or {}
        if version == V1:
            trend = V1_TREND_MAP[checked(structural.get("direction", "UNKNOWN"), V1_TREND_MAP, "v1_direction")]
            swing = swing_reading(structural.get("swing_structure") or {})
            ranges = features["base"].get("values") if features["base"]["status"] in USABLE else None
            range_state = V1_RANGE_MAP[checked(ranges["state"], V1_RANGE_MAP, "v1_base")] if ranges else "UNKNOWN"
            continuous = features["continuous_indicators"].get("values") or features["continuous_indicators"].get("components") or {}
            structural = {**structural, "ma20_slope": (continuous.get("sma20_slope") or {}).get("values") or {}}
            setup = setup_reading(structural, structure_status=features["structure"]["status"], trend=trend,
                                  swing=swing["swing_relation"], range_state=range_state)
            temporal = temporal_reading(timeframe=tf, as_of_session=context["as_of_session"],
                last_observed_session=inputs.get("last_observed_session"), from_v1=True)
        else:
            trend = checked(structural.get("trend_reading", "UNKNOWN"), TREND_READINGS, "trend_reading")
            swing = {k: structural.get(k, "UNKNOWN") for k in ("swing_high_relation", "swing_low_relation", "swing_relation")}
            ranges = features["range_consolidation"].get("values") if features["range_consolidation"]["status"] in USABLE else None
            range_state = V2_RANGE_MAP[checked(ranges["state"], V2_RANGE_MAP, "v2_range")] if ranges else "UNKNOWN"
            setup = features["setup_state"].get("values") or features["setup_state"].get("diagnostics") or setup_reading({}, structure_status="UNAVAILABLE",
                trend="UNKNOWN", swing="UNKNOWN", range_state="UNKNOWN")
            temporal = inputs["temporal"]
        volume = features["volume"]
        native = volume.get("values") or {}
        ratio = native.get("relative_to_median")
        state = ("UNKNOWN" if volume["status"] not in USABLE else "UNDEFINED_ZERO_REFERENCE" if ratio is None else
            "EXPANSION" if ratio >= owner.EXPANSION_RATIO else "CONTRACTION" if ratio <= owner.COMPRESSION_RATIO else "STABLE")
        concepts = {**pivot_reading(structural.get("breakout") or {}), "range_consolidation": range_state,
            "range_algorithm": "BOUNDED_CLOSE_RANGE_DURATION", "trend_reading": trend,
            "swing_relation": swing["swing_relation"], "setup_state": setup["state"],
            "native_volume_reference": {"state": state, "ratio_status": native.get("ratio_status", "UNAVAILABLE"),
                "relative_to_median": ratio, "relative_to_mean": native.get("relative_to_mean"),
                "current_native_volume": native.get("current_native_volume"), "distribution": native.get("distribution"),
                "window_basis": "LAST_20_INCLUDING_CURRENT", "required_lookback": volume["required_lookback"],
                "actual_available_lookback": volume["actual_available_lookback"], "reason_codes": volume["reason_codes"],
                "feature_pointer": "timeframes." + tf + ".features.volume"}}
        body = {"contract_version": CONTRACT_VERSION, "instrument": inputs["instrument"], "as_of_session": context["as_of_session"],
            "timeframe": tf, "source": {"technical_contract_version": version, "context_identity": context["artifact_identity"],
                "frame_identity": frame["artifact_identity"], "input_context_identity": inputs["artifact_identity"],
                "canonical_source_bar_identity": inputs["canonical_source_bar_identity"],
                "source_bar_identities": inputs["source_bar_identities"], "provider": inputs.get("source")},
            "availability": {"structure_status": features["structure"]["status"], "volume_status": volume["status"],
                "primitive_availability": setup["primitive_availability"]},
            "fitness": {k: inputs.get(k) for k in ("price_basis", "corporate_action_comparability", "volume_unit", "volume_basis", "historical_pit_authority")},
            "concepts": concepts, "setup_rule": setup["rule"], "setup_conflicts": setup["setup_conflicts"],
            "unknown_reasons": sorted(set(setup["reason_codes"] + swing.get("unknown_reasons", []))),
            "derived_concept_knowledge_stage": "POST_T0_ENRICHED" if version == V1 else "EXACT_TECHNICAL_IDENTITY_REQUIRED",
            "evidence_keys": {name: evidence_keys(context["ticker"], context["as_of_session"], tf, inputs["canonical_source_bar_identity"], name,
                "NATIVE_VOLUME_SERIES" if name == "native_volume_reference" else "CLOSE_SERIES_STRUCTURE") for name in
                ("breakout_relation", "failed_breakout", "pivot_test", "range_consolidation", "trend_reading", "swing_relation", "setup_state", "native_volume_reference")},
            "non_voting": True, "is_actionable": False}
        body["fitness"]["temporal"] = temporal
        result[tf] = _seal(body)
        verify_view(result[tf])
    return result


def verify_view(view):
    if (view.get("contract_version") != CONTRACT_VERSION or view.get("view_identity") != view.get("artifact_identity") or
        any(view.get(k) != v for k, v in _identity(view).items()) or view.get("non_voting") is not True or view.get("is_actionable") is not False):
        raise ValueError("RELATIONSHIP_VIEW_IDENTITY_INVALID")
    from contextual_technical_dispatch import SUPPORTED_VERSIONS
    if view["source"]["technical_contract_version"] not in SUPPORTED_VERSIONS:
        raise ValueError("TECHNICAL_VERSION_UNKNOWN")
    version = view["source"]["technical_contract_version"]
    input_kind = "contextual_technical_inputs/" + version.rsplit("/", 1)[1]
    if any(not isinstance(view["source"].get(key), str) or not view["source"][key].startswith(kind + ":") for key, kind in
        (("context_identity", version), ("frame_identity", version), ("input_context_identity", input_kind))):
        raise ValueError("RELATIONSHIP_VIEW_SOURCE_VERSION_BINDING_INVALID")
    for name in ("breakout_relation", "failed_breakout", "pivot_test", "range_consolidation", "trend_reading", "swing_relation", "setup_state"):
        checked(view["concepts"][name], VOCABULARY_MANIFEST[name], name)
    checked(view["concepts"]["native_volume_reference"]["state"], NATIVE_VOLUME_STATES, "native_volume_state")
    checked(view["concepts"]["native_volume_reference"]["ratio_status"], NATIVE_RATIO_STATUS, "native_ratio_status")
    checked(view["setup_rule"], SETUP_RULES, "setup_rule")
    for conflict in view["setup_conflicts"]: checked(conflict, SETUP_CONFLICTS, "setup_conflict")
    for status in view["availability"]["primitive_availability"].values():
        checked(status, PRIMITIVE_AVAILABILITY, "primitive_availability")
    checked(view["fitness"]["temporal"]["state"], DAILY_TEMPORAL_STATES if view["timeframe"] == "1D" else PERIOD_TEMPORAL_STATES, "temporal")
    checked(view["fitness"]["temporal"]["later_period_completeness"]["state"], COMPLETENESS_KNOWLEDGE, "later_period_completeness")
    expected = {name: evidence_keys(view["instrument"]["ticker"], view["as_of_session"], view["timeframe"],
        view["source"]["canonical_source_bar_identity"], name, "NATIVE_VOLUME_SERIES" if name == "native_volume_reference" else "CLOSE_SERIES_STRUCTURE")
        for name in ("breakout_relation", "failed_breakout", "pivot_test", "range_consolidation", "trend_reading", "swing_relation", "setup_state", "native_volume_reference")}
    if view["evidence_keys"] != expected: raise ValueError("RELATIONSHIP_VIEW_EVIDENCE_KEYS_INVALID")
    return view
