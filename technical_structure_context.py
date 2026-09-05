"""Deterministic current-research close-based structure context.

**V1 (TACTICAL_AND_BEHAVIORAL_ENGINE_V2):** close-based 20-session structure, contraction,
MA20-slope, self-relative volatility, base duration, session-over-session breakout event,
relative-volume pass-through.

**V2 (TACTICAL_MARKET_STRUCTURE_AND_BREAKOUT_V3):** additive extension — confirmed fractal
swings (N=2, no lookahead), HH/HL/LH/LL sequence, market structure state, BOS, CHoCH, pivot,
pivot-relative breakout state, trigger context, structural invalidation.  All V1 output keys
are preserved unchanged.  V2 adds new keys alongside them.

Close-only by design throughout.  The retained exact-session snapshot carries a documented
``RETAINED_HIGH_LOW_SCALE_INCOMPATIBLE_NOT_USED`` limitation: no true ATR, Donchian channel, or
wick-based geometry is computed.  ATR-dependent V3 fields carry an explicit
``NOT_AVAILABLE_HIGH_LOW_BASIS_NOT_COMPATIBLE`` string, not ``None``.  Every record carries an
explicit ``high_low_basis`` block naming the blocked feature classes, without blocking
any close-only fact.

Retained close-history depth is heterogeneous per ticker (confirmed against real 2026-08-28 data).
``MAX_LOOKBACK_SESSIONS = 250`` is the established convention from V1; V3 uses the same cap.
No feature is computed by padding, imputing, or extrapolating missing history.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from statistics import pstdev
from typing import Any, Mapping, Sequence

from field_temporal_contract import stable_id as _p3f9b_stable_id
from price_structure_breakout_context import NEAR

# ── Contract versioning ───────────────────────────────────────────────────────
CONTRACT_VERSION = "technical_structure_context/v2"
MILESTONE = "TACTICAL_MARKET_STRUCTURE_AND_BREAKOUT_V3"

# ── V1 constants (unchanged) ──────────────────────────────────────────────────
MIN_STRUCTURE_LOOKBACK = 20
RANGE_SPLIT = 10
SLOPE_LOOKBACK_SESSIONS = 5
VOLATILITY_WINDOW = 20
VOLATILITY_OFFSET_SESSIONS = 10
MAX_LOOKBACK_SESSIONS = 250       # established convention from V1; V3 uses same cap
COMPRESSION_RATIO = 0.7
EXPANSION_RATIO = 1.3
BASE_DURATION_CAP_SESSIONS = 60

HIGH_LOW_BLOCKED_FEATURES = ("true_atr", "donchian_channel_breakout", "wick_based_pattern_geometry")

STRUCTURE_STATUSES = (
    "BREAKOUT_CONFIRMED_BY_RULE", "NEAR_RECENT_RESISTANCE", "IN_RANGE",
    "NEAR_RECENT_SUPPORT", "BREAKDOWN_CONFIRMED_BY_RULE",
)
RANGE_STATES = ("RANGE_COMPRESSION", "RANGE_EXPANSION", "RANGE_STABLE")
CONTRACTION_STATES = ("CONTRACTION", "EXPANSION", "STABLE")
SLOPE_STATES = ("RISING", "FALLING", "FLAT")
BREAKOUT_EVENT_STATES = (
    "BREAKOUT_CONFIRMED", "BREAKOUT_FAILURE", "BREAKDOWN_CONFIRMED",
    "RE_ENTRY_ABOVE_SUPPORT", "NONE",
)

# ── V3 constants ──────────────────────────────────────────────────────────────
SWING_N = 2                        # fractal bars each side; confirmation lag = SWING_N sessions
EXTENDED_THRESHOLD = 0.05          # > 5 % above pivot → EXTENDED_AFTER_BREAKOUT

MARKET_STRUCTURE_STATES = (
    "UPTREND", "DOWNTREND", "RANGE",
    "EARLY_BULLISH_REVERSAL", "EARLY_BEARISH_REVERSAL", "INSUFFICIENT_HISTORY",
)
BOS_STATES = (
    "BULLISH_BOS_DETECTED_BY_RULE", "BEARISH_BOS_DETECTED_BY_RULE",
    "NO_BOS", "INSUFFICIENT_STRUCTURE",
)
CHOCH_STATES = (
    "BULLISH_CHOCH_DETECTED_BY_RULE", "BEARISH_CHOCH_DETECTED_BY_RULE",
    "NO_CHOCH", "INSUFFICIENT_STRUCTURE",
)
BREAKOUT_STATES_V3 = (
    "BREAKOUT", "TESTING_PIVOT", "BELOW_PIVOT",
    "EXTENDED_AFTER_BREAKOUT", "FAILED_BREAKOUT", "NO_VALID_PIVOT",
)
TRIGGER_TYPES = (
    "PIVOT_BREAKOUT_TRIGGER", "CONFIRMED_BOS_TRIGGER",
    "RETEST_BROKEN_PIVOT", "RECLAIM_STRUCTURAL_LEVEL", "NO_TRIGGER",
)
TRIGGER_STATES = ("TRIGGERED", "APPROACHING", "BELOW_TRIGGER")

_V3_AUTHORITY_BOUNDARY: dict[str, Any] = {
    "bos_choch_are_close_based_rule_inference_not_institutional_activity": True,
    "invalidation_level_is_not_a_stop_loss": True,
    "trigger_context_is_not_execution_authority": True,
    "breakout_state_v3_is_measurement_not_buy_signal": True,
    "volume_is_dimensionless_relative_not_adv": True,
}


class TechnicalStructureContextError(ValueError):
    """A retained input or an invariant of this contract is violated."""


# ── Canonical identity helpers (V1 unchanged) ─────────────────────────────────

def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


_IDENTITY_EXCLUDED_KEYS = {"artifact_sha256", "artifact_identity", "requested_at"}


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in _IDENTITY_EXCLUDED_KEYS}
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"technical_structure_context:{digest}"}


def _verify_descriptive_identity(source: Mapping[str, Any]) -> None:
    import market_wide_current_descriptive_research as descriptive_module
    identity = descriptive_module.content_identity(source)
    if source.get("artifact_sha256") != identity["artifact_sha256"]:
        raise TechnicalStructureContextError("DESCRIPTIVE_SOURCE_IDENTITY_MISMATCH")


def _verify_p3f9b_identity(snapshot: Mapping[str, Any]) -> None:
    payload = {key: value for key, value in snapshot.items() if key not in {"snapshot_sha256", "snapshot_identity"}}
    if snapshot.get("snapshot_sha256") != _p3f9b_stable_id(payload):
        raise TechnicalStructureContextError("P3F9B_SNAPSHOT_IDENTITY_MISMATCH")


def _recovery_overrides(
    recovery: Mapping[str, Any] | None, *, target_session: str, snapshot_identity: str | None,
) -> tuple[Mapping[str, Any], str | None]:
    """Validate the exact retained-history recovery contract before consuming it.

    The descriptive-research builder already uses this recovery artifact to calculate
    same-session features.  Tactical structure must use the *same retained close
    series*, rather than the one-bar exact-session projection, otherwise a ticker can
    be eligible for Tactical V3 while every structural field is necessarily blocked.
    """
    if recovery is None:
        return {}, None
    import market_wide_current_technical_coverage_scaleout as recovery_module

    identity = recovery_module.content_identity(recovery)
    if recovery.get("artifact_sha256") != identity["artifact_sha256"]:
        raise TechnicalStructureContextError("TECHNICAL_HISTORY_RECOVERY_IDENTITY_MISMATCH")
    if recovery.get("target_session") != target_session:
        raise TechnicalStructureContextError("TECHNICAL_HISTORY_RECOVERY_SESSION_MISMATCH")
    if recovery.get("source_lineage", {}).get("p3f9b_snapshot_identity") != snapshot_identity:
        raise TechnicalStructureContextError("TECHNICAL_HISTORY_RECOVERY_SNAPSHOT_IDENTITY_MISMATCH")
    overrides = recovery.get("recovered_history_overrides")
    if not isinstance(overrides, Mapping):
        raise TechnicalStructureContextError("TECHNICAL_HISTORY_RECOVERY_OVERRIDES_INVALID")
    return overrides, recovery.get("artifact_identity")


# ── Close series extraction (V1 unchanged) ────────────────────────────────────

def _closes(pf_record: Mapping[str, Any] | None) -> tuple[list[str], list[float]]:
    observations = (pf_record or {}).get("observations")
    if not isinstance(observations, list) or not observations:
        return [], []
    ordered = sorted(
        (row for row in observations if isinstance(row, Mapping) and row.get("session") and isinstance(row.get("close"), (int, float))),
        key=lambda row: str(row["session"]),
    )
    return [str(row["session"]) for row in ordered], [float(row["close"]) for row in ordered]


# ── V1 structure helpers (all unchanged) ──────────────────────────────────────

def _structure(window: Sequence[float]) -> dict[str, Any]:
    """Exact ``price_structure_breakout_context`` algorithm over an explicit trailing window."""
    prior, current = window[:-1], window[-1]
    high, low = max(prior), min(prior)
    rng = high - low
    if current > high:
        status = "BREAKOUT_CONFIRMED_BY_RULE"
    elif current >= high * (1 - NEAR):
        status = "NEAR_RECENT_RESISTANCE"
    elif current < low:
        status = "BREAKDOWN_CONFIRMED_BY_RULE"
    elif current <= low * (1 + NEAR):
        status = "NEAR_RECENT_SUPPORT"
    else:
        status = "IN_RANGE"
    return {
        "structure_status": status,
        "resistance": {"value": high, "distance_from_close_pct": (current / high) - 1},
        "support": {"value": low, "distance_from_close_pct": (current / low) - 1},
        "range_position": (current - low) / rng if rng else None,
    }


def _range_state(window: Sequence[float]) -> str:
    first, last = window[:RANGE_SPLIT], window[RANGE_SPLIT:]
    old_range, new_range = max(first) - min(first), max(last) - min(last)
    if new_range <= old_range * COMPRESSION_RATIO:
        return "RANGE_COMPRESSION"
    if new_range >= old_range * EXPANSION_RATIO:
        return "RANGE_EXPANSION"
    return "RANGE_STABLE"


def _ma(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _ma20_slope(closes: list[float]) -> dict[str, Any]:
    needed = MIN_STRUCTURE_LOOKBACK + SLOPE_LOOKBACK_SESSIONS
    if len(closes) < needed:
        return {"status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_HISTORY_FOR_MA20_SLOPE", "sessions_required": needed, "sessions_available": len(closes)}
    today_ma20 = _ma(closes[-MIN_STRUCTURE_LOOKBACK:])
    prior_ma20 = _ma(closes[-(MIN_STRUCTURE_LOOKBACK + SLOPE_LOOKBACK_SESSIONS):-SLOPE_LOOKBACK_SESSIONS])
    slope_state = "RISING" if today_ma20 > prior_ma20 else "FALLING" if today_ma20 < prior_ma20 else "FLAT"
    return {
        "status": "AVAILABLE", "slope_state": slope_state, "lookback_sessions": SLOPE_LOOKBACK_SESSIONS,
        "today_ma20": today_ma20, "prior_ma20": prior_ma20,
    }


def _self_relative_volatility(closes: list[float]) -> dict[str, Any]:
    needed = VOLATILITY_WINDOW + VOLATILITY_OFFSET_SESSIONS + 1
    if len(closes) < needed:
        return {"status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_HISTORY_FOR_SELF_RELATIVE_VOLATILITY", "sessions_required": needed, "sessions_available": len(closes)}

    def _realized_vol(window: Sequence[float]) -> float:
        returns = [(window[i] / window[i - 1]) - 1 for i in range(1, len(window))]
        return pstdev(returns)

    recent_window = closes[-(VOLATILITY_WINDOW + 1):]
    prior_window = closes[-(VOLATILITY_WINDOW + VOLATILITY_OFFSET_SESSIONS + 1):-VOLATILITY_OFFSET_SESSIONS]
    recent_vol, prior_vol = _realized_vol(recent_window), _realized_vol(prior_window)
    if prior_vol == 0:
        return {"status": "NOT_AVAILABLE", "reason": "PRIOR_WINDOW_ZERO_VOLATILITY_RATIO_UNDEFINED", "recent_realized_volatility_20d": recent_vol, "prior_realized_volatility_20d": prior_vol}
    ratio = recent_vol / prior_vol
    state = "CONTRACTION" if ratio <= COMPRESSION_RATIO else "EXPANSION" if ratio >= EXPANSION_RATIO else "STABLE"
    return {
        "status": "AVAILABLE", "self_relative_volatility_state": state, "ratio_recent_over_prior": ratio,
        "recent_realized_volatility_20d": recent_vol, "prior_realized_volatility_20d": prior_vol,
        "prior_window_offset_sessions": VOLATILITY_OFFSET_SESSIONS,
    }


def _base_duration(window: Sequence[float], full_closes: list[float], support: float, resistance: float) -> dict[str, Any]:
    scan = full_closes[-BASE_DURATION_CAP_SESSIONS:] if len(full_closes) > BASE_DURATION_CAP_SESSIONS else full_closes
    count = 0
    for close in reversed(scan):
        if support <= close <= resistance:
            count += 1
        else:
            break
    truncated = count == len(scan) and len(full_closes) > BASE_DURATION_CAP_SESSIONS
    return {
        "status": "AVAILABLE", "base_duration_sessions": count,
        "base_status": "IN_BASE" if count >= RANGE_SPLIT else "NOT_IN_BASE",
        "duration_cap_sessions": BASE_DURATION_CAP_SESSIONS, "duration_possibly_longer_than_reported": truncated,
    }


def _breakout_event(closes: list[float]) -> dict[str, Any]:
    needed = MIN_STRUCTURE_LOOKBACK + 1
    if len(closes) < needed:
        return {"status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_HISTORY_FOR_BREAKOUT_EVENT_READ", "sessions_required": needed, "sessions_available": len(closes)}
    today = _structure(closes[-MIN_STRUCTURE_LOOKBACK:])
    yesterday = _structure(closes[-(MIN_STRUCTURE_LOOKBACK + 1):-1])
    today_status, yesterday_status = today["structure_status"], yesterday["structure_status"]
    if today_status == "BREAKOUT_CONFIRMED_BY_RULE" and yesterday_status != "BREAKOUT_CONFIRMED_BY_RULE":
        event = "BREAKOUT_CONFIRMED"
    elif yesterday_status == "BREAKOUT_CONFIRMED_BY_RULE" and today_status != "BREAKOUT_CONFIRMED_BY_RULE" and closes[-1] < yesterday["resistance"]["value"]:
        event = "BREAKOUT_FAILURE"
    elif today_status == "BREAKDOWN_CONFIRMED_BY_RULE" and yesterday_status != "BREAKDOWN_CONFIRMED_BY_RULE":
        event = "BREAKDOWN_CONFIRMED"
    elif yesterday_status == "BREAKDOWN_CONFIRMED_BY_RULE" and today_status != "BREAKDOWN_CONFIRMED_BY_RULE" and closes[-1] > yesterday["support"]["value"]:
        event = "RE_ENTRY_ABOVE_SUPPORT"
    else:
        event = "NONE"
    return {"status": "AVAILABLE", "event": event, "today_structure_status": today_status, "yesterday_structure_status": yesterday_status}


# ── V3 helpers ────────────────────────────────────────────────────────────────

def _confirm_swings(closes: list[float], sessions: list[str], *, n: int = SWING_N) -> list[dict[str, Any]]:
    """Return all confirmed swings in chronological order.

    A swing candidate at index i is confirmed only when ``closes[i + n]`` exists.
    ``kind`` ∈ {``"HIGH"``, ``"LOW"``}.  No future data: the candidate must have
    n bars on each side within the provided series.
    """
    swings: list[dict[str, Any]] = []
    for i in range(n, len(closes) - n):
        price = closes[i]
        if all(price > closes[i - j] and price > closes[i + j] for j in range(1, n + 1)):
            swings.append({"kind": "HIGH", "price": price, "session": sessions[i], "index": i})
        elif all(price < closes[i - j] and price < closes[i + j] for j in range(1, n + 1)):
            swings.append({"kind": "LOW", "price": price, "session": sessions[i], "index": i})
    return swings


def _swing_structure_context(swings: list[dict[str, Any]]) -> dict[str, Any]:
    """Determine HH/HL/LH/LL sequence and market structure state."""
    highs = [s for s in swings if s["kind"] == "HIGH"]
    lows = [s for s in swings if s["kind"] == "LOW"]

    if len(highs) < 2 or len(lows) < 2:
        return {
            "status": "INSUFFICIENT_HISTORY",
            "market_structure_state": "INSUFFICIENT_HISTORY",
            "swing_high_sequence": None,
            "swing_low_sequence": None,
            "confirmed_swing_count": len(swings),
            "last_confirmed_swing_high": highs[-1] if highs else None,
            "last_confirmed_swing_low": lows[-1] if lows else None,
            "confirmation_lag_sessions": SWING_N,
        }

    h2, h1 = highs[-2], highs[-1]
    l2, l1 = lows[-2], lows[-1]
    hh = h1["price"] > h2["price"]
    hl = l1["price"] > l2["price"]

    if hh and hl:
        state = "UPTREND"
    elif not hh and not hl:
        state = "DOWNTREND"
    elif hh and not hl:
        state = "EARLY_BULLISH_REVERSAL"
    elif not hh and hl:
        state = "EARLY_BEARISH_REVERSAL"
    else:
        state = "RANGE"

    return {
        "status": "AVAILABLE",
        "market_structure_state": state,
        "swing_high_sequence": "HH" if hh else "LH",
        "swing_low_sequence": "HL" if hl else "LL",
        "confirmed_swing_count": len(swings),
        "last_confirmed_swing_high": h1,
        "last_confirmed_swing_low": l1,
        "previous_confirmed_swing_high": h2,
        "previous_confirmed_swing_low": l2,
        "confirmation_lag_sessions": SWING_N,
    }


def _bos_v3(closes: list[float], sessions: list[str], swing_ctx: dict[str, Any]) -> dict[str, Any]:
    """Break of Structure — close-through confirmed level by rule."""
    if swing_ctx["status"] == "INSUFFICIENT_HISTORY":
        return {"status": "INSUFFICIENT_STRUCTURE", "bos_state": "INSUFFICIENT_STRUCTURE"}

    current = closes[-1]
    ms = swing_ctx["market_structure_state"]
    last_high = swing_ctx.get("last_confirmed_swing_high") or {}
    last_low = swing_ctx.get("last_confirmed_swing_low") or {}

    if ms in ("DOWNTREND", "RANGE", "EARLY_BULLISH_REVERSAL") and last_high.get("price") is not None:
        if current > last_high["price"]:
            return {
                "status": "AVAILABLE", "bos_state": "BULLISH_BOS_DETECTED_BY_RULE",
                "bos_direction": "BULLISH", "broken_level": last_high["price"],
                "broken_level_session": last_high.get("session"),
                "break_distance_pct": (current / last_high["price"]) - 1,
                "confirmation_method": "CLOSE_THROUGH_CONFIRMED_LEVEL_BY_RULE",
                "warning": "CLOSE_BASED_RULE_INFERENCE_NOT_INSTITUTIONAL_ACTIVITY",
            }

    if ms in ("UPTREND", "RANGE", "EARLY_BEARISH_REVERSAL") and last_low.get("price") is not None:
        if current < last_low["price"]:
            return {
                "status": "AVAILABLE", "bos_state": "BEARISH_BOS_DETECTED_BY_RULE",
                "bos_direction": "BEARISH", "broken_level": last_low["price"],
                "broken_level_session": last_low.get("session"),
                "break_distance_pct": (current / last_low["price"]) - 1,
                "confirmation_method": "CLOSE_THROUGH_CONFIRMED_LEVEL_BY_RULE",
                "warning": "CLOSE_BASED_RULE_INFERENCE_NOT_INSTITUTIONAL_ACTIVITY",
            }

    return {"status": "AVAILABLE", "bos_state": "NO_BOS", "bos_direction": None}


def _choch_v3(swing_ctx: dict[str, Any], bos: dict[str, Any]) -> dict[str, Any]:
    """Change of Character — first structural break against the established structure."""
    if swing_ctx["status"] == "INSUFFICIENT_HISTORY":
        return {"status": "INSUFFICIENT_STRUCTURE", "choch_state": "INSUFFICIENT_STRUCTURE"}

    ms = swing_ctx["market_structure_state"]
    bos_st = bos.get("bos_state")

    if ms == "DOWNTREND" and bos_st == "BULLISH_BOS_DETECTED_BY_RULE":
        return {
            "status": "AVAILABLE", "choch_state": "BULLISH_CHOCH_DETECTED_BY_RULE",
            "direction": "BULLISH",
            "warning": "CLOSE_BASED_RULE_INFERENCE_ONLY_NOT_SMART_MONEY_CONFIRMATION",
        }
    if ms == "UPTREND" and bos_st == "BEARISH_BOS_DETECTED_BY_RULE":
        return {
            "status": "AVAILABLE", "choch_state": "BEARISH_CHOCH_DETECTED_BY_RULE",
            "direction": "BEARISH",
            "warning": "CLOSE_BASED_RULE_INFERENCE_ONLY_NOT_SMART_MONEY_CONFIRMATION",
        }
    return {"status": "AVAILABLE", "choch_state": "NO_CHOCH", "direction": None}


def _pivot_v3(closes: list[float], v1_base_ctx: dict[str, Any], swing_ctx: dict[str, Any]) -> dict[str, Any]:
    """Candidate pivot from confirmed-swing or V1 base boundaries.

    Primary: last confirmed swing high.
    Secondary: V1 ``resistance`` level (top of the 20-session window) if swing is unavailable.
    """
    current = closes[-1]
    # Primary: last confirmed swing high
    last_high = swing_ctx.get("last_confirmed_swing_high") or {}
    pivot_price = last_high.get("price")
    method = "LAST_CONFIRMED_SWING_HIGH" if pivot_price is not None else None

    # Fallback: V1 resistance (20-session prior high)
    if pivot_price is None:
        v1_resistance = (v1_base_ctx.get("resistance") or {}).get("value")
        if v1_resistance is not None:
            pivot_price = v1_resistance
            method = "V1_PRIOR_20_SESSION_RESISTANCE_FALLBACK"

    if pivot_price is None:
        return {
            "status": "NO_VALID_PIVOT", "pivot_price": None, "pivot_method": None,
            "distance_to_pivot_pct": None,
            "distance_to_pivot_atr": "NOT_AVAILABLE_HIGH_LOW_BASIS_NOT_COMPATIBLE",
        }

    return {
        "status": "AVAILABLE", "pivot_price": pivot_price, "pivot_method": method,
        "distance_to_pivot_pct": (current / pivot_price) - 1,
        "distance_to_pivot_atr": "NOT_AVAILABLE_HIGH_LOW_BASIS_NOT_COMPATIBLE",
        "qualification": "DETERMINISTIC_CANDIDATE_NOT_PREDICTIVE",
    }


def _breakout_state_v3(closes: list[float], pivot_ctx: dict[str, Any]) -> dict[str, Any]:
    """Pivot-relative breakout state (V3); distinct from V1 session-over-session ``breakout_context``."""
    if pivot_ctx["status"] == "NO_VALID_PIVOT":
        return {"status": "NO_VALID_PIVOT", "breakout_state": "NO_VALID_PIVOT"}

    current = closes[-1]
    pivot = pivot_ctx["pivot_price"]
    dist_pct = (current / pivot) - 1

    prior_was_above = len(closes) >= 2 and (closes[-2] / pivot) - 1 > 0

    if dist_pct > EXTENDED_THRESHOLD:
        state = "EXTENDED_AFTER_BREAKOUT"
    elif dist_pct > 0:
        state = "BREAKOUT"
    elif dist_pct >= -NEAR:
        state = "TESTING_PIVOT"
    elif prior_was_above:
        state = "FAILED_BREAKOUT"
    else:
        state = "BELOW_PIVOT"

    return {
        "status": "AVAILABLE", "breakout_state": state,
        "distance_to_pivot_pct": dist_pct,
        "warning": "BREAKOUT_STATE_IS_MEASUREMENT_NOT_BUY_SIGNAL",
        "blocked": {
            "break_distance_atr": "NOT_AVAILABLE_HIGH_LOW_BASIS_NOT_COMPATIBLE",
            "candle_body_fraction": "NOT_AVAILABLE_OPEN_NOT_IN_RETAINED_SERIES",
            "close_location_value": "NOT_AVAILABLE_HIGH_LOW_BASIS_NOT_COMPATIBLE",
        },
    }


def _trigger_v3(
    closes: list[float],
    breakout: dict[str, Any],
    bos: dict[str, Any],
    pivot_ctx: dict[str, Any],
) -> dict[str, Any]:
    """Trigger context: measurement only, no execution authority."""
    current = closes[-1]
    bst = breakout.get("breakout_state")
    bos_st = bos.get("bos_state")

    if bst in ("BREAKOUT", "EXTENDED_AFTER_BREAKOUT"):
        ttype, tlevel, tstate = "PIVOT_BREAKOUT_TRIGGER", pivot_ctx.get("pivot_price"), "TRIGGERED"
    elif bos_st in ("BULLISH_BOS_DETECTED_BY_RULE", "BEARISH_BOS_DETECTED_BY_RULE"):
        ttype, tlevel, tstate = "CONFIRMED_BOS_TRIGGER", bos.get("broken_level"), "TRIGGERED"
    elif bst == "FAILED_BREAKOUT":
        ttype, tlevel, tstate = "RETEST_BROKEN_PIVOT", pivot_ctx.get("pivot_price"), "BELOW_TRIGGER"
    elif bst == "TESTING_PIVOT":
        ttype, tlevel, tstate = "PIVOT_BREAKOUT_TRIGGER", pivot_ctx.get("pivot_price"), "APPROACHING"
    else:
        ttype, tlevel, tstate = "NO_TRIGGER", None, "BELOW_TRIGGER"

    dist = ((current / tlevel) - 1) if tlevel else None
    return {
        "status": "AVAILABLE", "trigger_type": ttype, "trigger_level": tlevel,
        "trigger_state": tstate, "distance_to_trigger_pct": dist,
        "warning": "TRIGGER_CONTEXT_IS_NOT_EXECUTION_AUTHORITY",
    }


def _invalidation_v3(
    closes: list[float],
    swing_ctx: dict[str, Any],
    v1_structure: dict[str, Any],
) -> dict[str, Any]:
    """Structural invalidation level.  NOT a stop-loss; analytical context only."""
    if swing_ctx["status"] == "INSUFFICIENT_HISTORY":
        return {"status": "INSUFFICIENT_STRUCTURE", "invalidation_level": None}

    current = closes[-1]
    ms = swing_ctx["market_structure_state"]
    last_low = swing_ctx.get("last_confirmed_swing_low") or {}
    last_high = swing_ctx.get("last_confirmed_swing_high") or {}

    bullish = ms in ("UPTREND", "EARLY_BULLISH_REVERSAL", "RANGE")

    if bullish:
        level = last_low.get("price")
        # Fallback to V1 support if no swing low
        if level is None:
            level = (v1_structure.get("support") or {}).get("value")
        method = "CONFIRMED_SWING_LOW_BY_RULE_OR_V1_SUPPORT_FALLBACK"
    else:
        level = last_high.get("price")
        if level is None:
            level = (v1_structure.get("resistance") or {}).get("value")
        method = "CONFIRMED_SWING_HIGH_BY_RULE_OR_V1_RESISTANCE_FALLBACK"

    if level is None:
        return {"status": "NO_DEFENSIBLE_LEVEL", "invalidation_level": None}

    return {
        "status": "AVAILABLE", "invalidation_level": level, "invalidation_method": method,
        "distance_to_invalidation_pct": (current / level) - 1,
        "warning": "INVALIDATION_LEVEL_IS_ANALYTICAL_CONTEXT_NOT_A_STOP_LOSS",
    }


# ── Insufficient stub (extended for V3 keys) ──────────────────────────────────

def _insufficient_record(ticker: str, reason: str, depth: int) -> dict[str, Any]:
    stub: dict[str, Any] = {"status": "NOT_AVAILABLE"}
    return {
        "ticker": ticker, "eligibility": {"status": "NOT_ELIGIBLE", "reason": reason},
        "close_history_depth": depth,
        # V1 keys
        "trend_context": stub, "structure_context": stub,
        "contraction_context": stub, "base_context": stub,
        "breakout_context": stub, "relative_volume": stub,
        # V3 keys
        "swing_structure": stub, "bos_context": stub, "choch_context": stub,
        "pivot_context": stub, "breakout_state_v3": stub,
        "trigger_context": stub, "invalidation_context": stub,
        "high_low_basis": {"status": "NOT_APPLICABLE", "reason": "NO_ELIGIBLE_CLOSE_SERIES"},
        "blockers": [reason], "warnings": [], "authority_tier": None,
    }


# ── Per-ticker classification ─────────────────────────────────────────────────

def _classify_ticker(
    ticker: str, *, descriptive_record: Mapping[str, Any],
    pf_record: Mapping[str, Any] | None, target_session: str,
    recovery_override: Mapping[str, Any] | None = None, recovery_identity: str | None = None,
) -> dict[str, Any]:
    technical = descriptive_record.get("technical_features", {})
    eligible = technical.get("status") == "SHADOW_ONLY" and technical.get("is_current_session") is True
    if not eligible:
        return _insufficient_record(ticker, "TECHNICAL_FEATURES_UNAVAILABLE_OR_NOT_CURRENT_SESSION", 0)

    history_source = "P3F9B_EXACT_SESSION_RECORD"
    history_record = pf_record
    if isinstance(recovery_override, Mapping) and recovery_override.get("state") == "RECOVERED_COMPLETE_TECHNICAL_HISTORY":
        history_record = {"observations": recovery_override.get("observations")}
        history_source = "RETAINED_TECHNICAL_HISTORY_RECOVERY"
    sessions, closes = _closes(history_record)
    if not sessions or sessions[-1] != target_session:
        record = _insufficient_record(ticker, "RETAINED_CLOSE_SERIES_MISSING_OR_NOT_CURRENT_SESSION", len(closes))
        record["technical_history_lineage"] = {
            "source": history_source, "recovery_artifact_identity": recovery_identity,
            "recovery_payload_sha256": recovery_override.get("payload_sha256") if isinstance(recovery_override, Mapping) else None,
        }
        return record
    if len(closes) > MAX_LOOKBACK_SESSIONS:
        closes = closes[-MAX_LOOKBACK_SESSIONS:]
        sessions = sessions[-MAX_LOOKBACK_SESSIONS:]
    depth = len(closes)

    blockers: list[str] = []
    values = technical.get("values", {})

    # ── V1 computations (all unchanged) ──────────────────────────────────────
    trend_context = {
        "status": "AVAILABLE", "trend_state": descriptive_record.get("trend_state"),
        "close": values.get("close"), "ma_20": values.get("ma_20"), "momentum_20d": values.get("momentum_20d"),
        "ma20_slope": _ma20_slope(closes),
    }

    if depth < MIN_STRUCTURE_LOOKBACK:
        structure_context: dict[str, Any] = {"status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_HISTORY_FOR_STRUCTURE", "sessions_required": MIN_STRUCTURE_LOOKBACK, "sessions_available": depth}
        contraction_context: dict[str, Any] = {"status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_HISTORY_FOR_STRUCTURE"}
        base_context: dict[str, Any] = {"status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_HISTORY_FOR_STRUCTURE"}
        blockers.append("INSUFFICIENT_HISTORY_FOR_STRUCTURE")
        v1_structure: dict[str, Any] = {}
    else:
        window = closes[-MIN_STRUCTURE_LOOKBACK:]
        v1_structure = _structure(window)
        structure_context = {"status": "AVAILABLE", **v1_structure}
        contraction_context = {
            "status": "AVAILABLE", "range_state": _range_state(window),
            "self_relative_volatility": _self_relative_volatility(closes),
        }
        base_context = _base_duration(window, closes, v1_structure["support"]["value"], v1_structure["resistance"]["value"])

    breakout_context = _breakout_event(closes)

    relative_volume_value = values.get("relative_volume_provider_scoped")
    relative_volume = {
        "status": "AVAILABLE" if isinstance(relative_volume_value, (int, float)) else "NOT_AVAILABLE",
        "relative_volume_provider_scoped": relative_volume_value,
        "authority_tier": "DERIVED_PROXY",
        "warning": "NOT_LIQUIDITY_OR_TURNOVER; provider-scoped, own-20-session-median basis",
    }

    # ── V3 computations (additive) ────────────────────────────────────────────
    swings = _confirm_swings(closes, sessions)
    swing_ctx = _swing_structure_context(swings)

    if swing_ctx["status"] == "INSUFFICIENT_HISTORY":
        blockers.append("INSUFFICIENT_SWINGS_FOR_V3_STRUCTURE")

    bos = _bos_v3(closes, sessions, swing_ctx)
    choch = _choch_v3(swing_ctx, bos)
    pivot = _pivot_v3(closes, v1_structure, swing_ctx)
    brk_v3 = _breakout_state_v3(closes, pivot)
    trigger = _trigger_v3(closes, brk_v3, bos, pivot)
    invalidation = _invalidation_v3(closes, swing_ctx, v1_structure)

    return {
        "ticker": ticker, "eligibility": {"status": "ELIGIBLE"}, "close_history_depth": depth,
        "technical_history_lineage": {
            "source": history_source, "recovery_artifact_identity": recovery_identity,
            "recovery_payload_sha256": recovery_override.get("payload_sha256") if isinstance(recovery_override, Mapping) else None,
        },
        # V1 keys (unchanged)
        "trend_context": trend_context, "structure_context": structure_context,
        "contraction_context": contraction_context, "base_context": base_context,
        "breakout_context": breakout_context, "relative_volume": relative_volume,
        # V3 keys (additive)
        "swing_structure": swing_ctx,
        "bos_context": bos,
        "choch_context": choch,
        "pivot_context": pivot,
        "breakout_state_v3": brk_v3,
        "trigger_context": trigger,
        "invalidation_context": invalidation,
        # Shared
        "high_low_basis": {
            "status": "NOT_COMPATIBLE", "reason": "HIGH_LOW_BASIS_NOT_COMPATIBLE",
            "affected_feature_classes": list(HIGH_LOW_BLOCKED_FEATURES),
            "fallback": "CLOSE_ONLY_PROXY_USED_FOR_STRUCTURE_AND_CONTRACTION",
        },
        "blockers": blockers,
        "warnings": ["ADJUSTED_RETROSPECTIVE_NOT_RAW_AS_TRADED", "CLOSE_ONLY_STRUCTURE_NOT_HIGH_LOW_GEOMETRY"],
        "authority_tier": "SHADOW_ONLY",
        "method": {
            "identity": CONTRACT_VERSION, "swing_n": SWING_N,
            "min_structure_lookback_sessions": MIN_STRUCTURE_LOOKBACK,
            "max_lookback_sessions_cap": MAX_LOOKBACK_SESSIONS, "near_threshold": NEAR,
            "extended_threshold": EXTENDED_THRESHOLD,
        },
        "authority_boundary": _V3_AUTHORITY_BOUNDARY,
    }


# ── Public build_artifact ─────────────────────────────────────────────────────

def build_artifact(
    *, current_descriptive: Mapping[str, Any], p3f9b_snapshot: Mapping[str, Any], requested_at: str,
    technical_history_recovery_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the complete technical structure context artifact.

    Zero silent drops: every candidate gets a record, eligible or not.
    V1 output keys are preserved unchanged; V3 keys are additive.
    """
    _verify_descriptive_identity(current_descriptive)
    _verify_p3f9b_identity(p3f9b_snapshot)

    target_session = current_descriptive.get("session")
    if not target_session or p3f9b_snapshot.get("resolved_completed_session") != target_session:
        raise TechnicalStructureContextError("P3F9B_SESSION_MISMATCH")
    expected_snapshot_identity = current_descriptive.get("input_lineage", {}).get("p3f9b_snapshot_identity")
    if expected_snapshot_identity and expected_snapshot_identity != p3f9b_snapshot.get("snapshot_identity"):
        raise TechnicalStructureContextError("P3F9B_SNAPSHOT_LINEAGE_MISMATCH")

    recovery_overrides, recovery_identity = _recovery_overrides(
        technical_history_recovery_artifact, target_session=target_session,
        snapshot_identity=p3f9b_snapshot.get("snapshot_identity"),
    )

    descriptive_records = current_descriptive.get("records")
    pf_records = p3f9b_snapshot.get("records")
    if not isinstance(descriptive_records, Mapping) or not isinstance(pf_records, Mapping):
        raise TechnicalStructureContextError("SOURCE_RECORDS_INVALID")

    records: dict[str, dict[str, Any]] = {}
    for ticker in sorted(descriptive_records):
        records[ticker] = _classify_ticker(
            ticker, descriptive_record=descriptive_records[ticker],
            pf_record=pf_records.get(ticker), target_session=target_session,
            recovery_override=recovery_overrides.get(ticker), recovery_identity=recovery_identity,
        )

    eligible_count = sum(1 for r in records.values() if r["eligibility"]["status"] == "ELIGIBLE")

    # V1 coverage counts (unchanged)
    structure_counts = Counter(r["structure_context"].get("structure_status", "NOT_AVAILABLE") for r in records.values())
    range_counts = Counter(r["contraction_context"].get("range_state", "NOT_AVAILABLE") for r in records.values())
    contraction_counts = Counter((r["contraction_context"].get("self_relative_volatility") or {}).get("self_relative_volatility_state", "NOT_AVAILABLE") for r in records.values())
    slope_counts = Counter(r["trend_context"].get("ma20_slope", {}).get("slope_state", "NOT_AVAILABLE") for r in records.values())
    breakout_event_counts = Counter(r["breakout_context"].get("event", "NOT_AVAILABLE") for r in records.values())
    base_status_counts = Counter(r["base_context"].get("base_status", "NOT_AVAILABLE") for r in records.values())

    # V3 coverage counts (additive)
    ms_counts = Counter((r.get("swing_structure") or {}).get("market_structure_state", "NOT_AVAILABLE") for r in records.values())
    bos_counts = Counter((r.get("bos_context") or {}).get("bos_state", "NOT_AVAILABLE") for r in records.values())
    choch_counts = Counter((r.get("choch_context") or {}).get("choch_state", "NOT_AVAILABLE") for r in records.values())
    brk_v3_counts = Counter((r.get("breakout_state_v3") or {}).get("breakout_state", "NOT_AVAILABLE") for r in records.values())
    trigger_counts = Counter((r.get("trigger_context") or {}).get("trigger_type", "NOT_AVAILABLE") for r in records.values())

    artifact: dict[str, Any] = {
        "schema_version": "2.0.0", "contract_version": CONTRACT_VERSION, "milestone": MILESTONE,
        "requested_at": requested_at, "session": target_session,
        "source_artifacts": {
            "current_descriptive": current_descriptive.get("artifact_identity"),
            "p3f9b_snapshot": p3f9b_snapshot.get("snapshot_identity"),
            "technical_history_recovery": recovery_identity,
        },
        "coverage": {
            "candidate_count": len(records), "eligible_count": eligible_count,
            "not_eligible_count": len(records) - eligible_count,
            # V1
            "structure_status_counts": dict(sorted(structure_counts.items())),
            "range_state_counts": dict(sorted(range_counts.items())),
            "self_relative_volatility_state_counts": dict(sorted(contraction_counts.items())),
            "ma20_slope_state_counts": dict(sorted(slope_counts.items())),
            "breakout_event_counts": dict(sorted(breakout_event_counts.items())),
            "base_status_counts": dict(sorted(base_status_counts.items())),
            # V3
            "market_structure_state_counts": dict(sorted(ms_counts.items())),
            "bos_state_counts": dict(sorted(bos_counts.items())),
            "choch_state_counts": dict(sorted(choch_counts.items())),
            "breakout_state_v3_counts": dict(sorted(brk_v3_counts.items())),
            "trigger_type_counts": dict(sorted(trigger_counts.items())),
            "insufficient_reason_counts": dict(sorted(Counter(
                reason for r in records.values() for reason in r["blockers"]
            ).items())),
        },
        "blocked_outputs": {
            "true_atr_or_donchian_high_low_geometry": "HIGH_LOW_BASIS_NOT_COMPATIBLE",
            "ordinal_market_ranking": "RANKING_PROHIBITED", "opportunity_score": "SCORING_PROHIBITED",
            "probabilities_or_target_prices": "FORECAST_PROHIBITED",
            "fixed_stop_percentage": "NOT_IMPLEMENTED_NOT_A_STOP",
            "historical_raw_as_traded_or_pit": "RAW_AS_TRADED_NOT_PROMOTED",
            "backtesting": "OUT_OF_SCOPE_THIS_MILESTONE",
        },
        "authority_boundary": {
            "is_actionable": False, "not_a_recommendation_or_execution_instruction": True,
            "requires_human_review": True, "close_only_structure_not_high_low_geometry": True,
            "self_relative_volatility_is_not_a_forecast": True,
            **_V3_AUTHORITY_BOUNDARY,
        },
        "records": records,
    }
    identity = content_identity(artifact)
    artifact["artifact_sha256"], artifact["artifact_identity"] = identity["artifact_sha256"], identity["artifact_identity"]
    return artifact
