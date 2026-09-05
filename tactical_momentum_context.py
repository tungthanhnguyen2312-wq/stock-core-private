"""Deterministic current-research momentum measurements (TACTICAL_MOMENTUM_PARTICIPATION_CONFIRMATION_V1).

Same retained close series as ``technical_structure_context.py`` (shared resolver:
``technical_structure_context.resolve_target_session_observations``), so a ticker's momentum
reads never disagree with its structure reads about which close series is authoritative for the
session. Close-only by design -- no high/low/open input, matching the established
``HIGH_LOW_BASIS_NOT_COMPATIBLE`` limitation.

Feature engine only: this module emits values, zones, and directional/event states. It never
asserts a buy/sell threshold (e.g. "RSI < 30 = BUY") -- that interpretation, if any, belongs to
the strategy layer.

Divergence pivots reuse ``technical_structure_context._confirm_swings`` (the existing no-lookahead
confirmed-swing machinery) rather than a second pivot algorithm; a divergence is available only
once both confirmed price pivots exist, and it is always reported as of the target session, never
backdated to an earlier one.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from technical_structure_context import (
    MAX_LOOKBACK_SESSIONS,
    SWING_N,
    _closes,
    _confirm_swings,
    _verify_descriptive_identity,
    _verify_p3f9b_identity,
    _recovery_overrides,
    resolve_target_session_observations,
)

CONTRACT_VERSION = "tactical_momentum_context/v1"
MILESTONE = "TACTICAL_MOMENTUM_PARTICIPATION_CONFIRMATION_V1"

RSI_PERIOD = 14
RSI_MIN_SESSIONS = RSI_PERIOD + 1
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
RSI_METHOD = "WILDER_RSI_14"

MA_LENGTHS = (20, 50, 100, 200)
MA_SLOPE_LOOKBACK_SESSIONS = 5

MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
MACD_MIN_SESSIONS = MACD_SLOW + MACD_SIGNAL - 1  # 34: first index with a valid signal-line value
MACD_METHOD = "EMA_12_26_9_MACD"

_MOMENTUM_AUTHORITY_BOUNDARY: dict[str, Any] = {
    "rsi_zone_is_measurement_not_buy_sell_signal": True,
    "macd_cross_is_measurement_not_confirmation_signal": True,
    "divergence_is_technical_inference_not_institutional_activity": True,
    "no_universal_threshold_gate": True,
    "ranking_recommendation_sizing_execution": "NOT_EMITTED",
}


class TacticalMomentumContextError(ValueError):
    """A retained input or an invariant of this contract is violated."""


# ── Canonical identity helpers (matches technical_structure_context.py) ───────

def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


_IDENTITY_EXCLUDED_KEYS = {"artifact_sha256", "artifact_identity", "requested_at"}


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in _IDENTITY_EXCLUDED_KEYS}
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"tactical_momentum_context:{digest}"}


def _insufficient_record(ticker: str, reason: str, depth: int) -> dict[str, Any]:
    return {
        "ticker": ticker, "eligibility": {"status": "NOT_ELIGIBLE", "reason": reason},
        "close_history_depth": depth, "price_direction_1d": "NOT_AVAILABLE",
        "rsi": {"status": "NOT_AVAILABLE", "reason": reason},
        "rsi_divergence": {"status": "NOT_AVAILABLE", "reason": reason},
        "moving_averages": {str(n): {"status": "NOT_AVAILABLE", "reason": reason} for n in MA_LENGTHS},
        "macd": {"status": "NOT_AVAILABLE", "reason": reason},
        "authority_boundary": _MOMENTUM_AUTHORITY_BOUNDARY,
    }


# ── RSI (Wilder) ────────────────────────────────────────────────────────────

def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_gain == 0 and avg_loss == 0:
        return 50.0  # perfectly flat window: neither gain nor loss occurred
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _rsi_series(closes: list[float], period: int = RSI_PERIOD) -> list[float | None]:
    """One Wilder RSI value per index in ``closes``; ``None`` before the first valid computation."""
    n = len(closes)
    result: list[float | None] = [None] * n
    if n < period + 1:
        return result
    diffs = [closes[i] - closes[i - 1] for i in range(1, n)]
    gains = [max(d, 0.0) for d in diffs]
    losses = [max(-d, 0.0) for d in diffs]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result[period] = _rsi_from_averages(avg_gain, avg_loss)
    for i in range(period, len(diffs)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result[i + 1] = _rsi_from_averages(avg_gain, avg_loss)
    return result


def _rsi_zone(value: float) -> str:
    if value >= RSI_OVERBOUGHT:
        return "OVERBOUGHT"
    if value <= RSI_OVERSOLD:
        return "OVERSOLD"
    return "NEUTRAL"


def _rsi_level_cross_event(prior: float | None, current: float) -> str:
    if not isinstance(prior, (int, float)):
        return "NONE"
    for level in (RSI_OVERSOLD, RSI_OVERBOUGHT):
        if prior < level <= current:
            return f"CROSSED_ABOVE_{int(level)}"
        if prior >= level > current:
            return f"CROSSED_BELOW_{int(level)}"
    return "NONE"


def _rsi_context(closes: list[float], sessions: list[str]) -> tuple[dict[str, Any], list[float | None]]:
    depth = len(closes)
    series = _rsi_series(closes)
    if depth < RSI_MIN_SESSIONS or series[-1] is None:
        return {
            "status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_HISTORY_FOR_RSI_14",
            "sessions_required": RSI_MIN_SESSIONS, "sessions_available": depth, "method": RSI_METHOD,
        }, series
    current = series[-1]
    prior = series[-2] if depth >= 2 else None
    direction = "FLAT" if prior is None or current == prior else "RISING" if current > prior else "FALLING"
    return {
        "status": "AVAILABLE", "method": RSI_METHOD, "value": current, "zone": _rsi_zone(current),
        "prior_value": prior, "direction": direction,
        "level_cross_event": _rsi_level_cross_event(prior, current),
        "reference_levels": {"overbought": RSI_OVERBOUGHT, "oversold": RSI_OVERSOLD},
        "as_of_session": sessions[-1],
    }, series


# ── RSI divergence (confirmed price pivots via existing swing machinery) ──────

def _rsi_divergence_context(closes: list[float], sessions: list[str], rsi_series: list[float | None]) -> dict[str, Any]:
    swings = _confirm_swings(closes, sessions, n=SWING_N)
    highs = [s for s in swings if s["kind"] == "HIGH"]
    lows = [s for s in swings if s["kind"] == "LOW"]
    if len(highs) < 2 and len(lows) < 2:
        return {
            "status": "INSUFFICIENT_HISTORY", "reason": "FEWER_THAN_TWO_CONFIRMED_SWINGS_EACH_SIDE",
            "confirmation_lag_sessions": SWING_N, "as_of_session": sessions[-1] if sessions else None,
        }

    def _pivot_with_rsi(pivot: Mapping[str, Any]) -> dict[str, Any]:
        return {"session": pivot["session"], "index": pivot["index"], "price": pivot["price"], "rsi": rsi_series[pivot["index"]]}

    candidates: list[dict[str, Any]] = []
    bearish = None
    if len(highs) >= 2:
        h2, h1 = highs[-2], highs[-1]
        r2, r1 = rsi_series[h2["index"]], rsi_series[h1["index"]]
        if h1["price"] > h2["price"] and isinstance(r1, (int, float)) and isinstance(r2, (int, float)) and r1 < r2:
            bearish = {
                "kind": "BEARISH_DIVERGENCE_CANDIDATE",
                "price_higher_high": True, "rsi_lower_high": True,
                "prior_pivot": _pivot_with_rsi(h2), "latest_pivot": _pivot_with_rsi(h1),
            }
            candidates.append(bearish)
    bullish = None
    if len(lows) >= 2:
        l2, l1 = lows[-2], lows[-1]
        r2, r1 = rsi_series[l2["index"]], rsi_series[l1["index"]]
        if l1["price"] < l2["price"] and isinstance(r1, (int, float)) and isinstance(r2, (int, float)) and r1 > r2:
            bullish = {
                "kind": "BULLISH_DIVERGENCE_CANDIDATE",
                "price_lower_low": True, "rsi_higher_low": True,
                "prior_pivot": _pivot_with_rsi(l2), "latest_pivot": _pivot_with_rsi(l1),
            }
            candidates.append(bullish)

    return {
        "status": "AVAILABLE", "as_of_session": sessions[-1],
        "confirmation_lag_sessions": SWING_N,
        "confirmed_swing_high_count": len(highs), "confirmed_swing_low_count": len(lows),
        "bullish_divergence_candidate": bullish, "bearish_divergence_candidate": bearish,
        "divergence_state": (
            "BOTH_BULLISH_AND_BEARISH_CANDIDATES" if bullish and bearish
            else bullish["kind"] if bullish else bearish["kind"] if bearish else "NO_DIVERGENCE_CANDIDATE"
        ),
    }


# ── Moving averages ────────────────────────────────────────────────────────

def _ma(values: list[float]) -> float:
    return sum(values) / len(values)


def _ma_slope(closes: list[float], length: int) -> dict[str, Any]:
    needed = length + MA_SLOPE_LOOKBACK_SESSIONS
    if len(closes) < needed:
        return {"status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_HISTORY_FOR_MA_SLOPE", "sessions_required": needed, "sessions_available": len(closes)}
    today = _ma(closes[-length:])
    prior = _ma(closes[-(length + MA_SLOPE_LOOKBACK_SESSIONS):-MA_SLOPE_LOOKBACK_SESSIONS])
    state = "RISING" if today > prior else "FALLING" if today < prior else "FLAT"
    return {"status": "AVAILABLE", "slope_state": state, "lookback_sessions": MA_SLOPE_LOOKBACK_SESSIONS, "today_value": today, "prior_value": prior}


def _moving_average_context(closes: list[float]) -> dict[str, dict[str, Any]]:
    current_close = closes[-1]
    result: dict[str, dict[str, Any]] = {}
    for length in MA_LENGTHS:
        key = str(length)
        if len(closes) < length:
            result[key] = {"status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_HISTORY", "sessions_required": length, "sessions_available": len(closes)}
            continue
        value = _ma(closes[-length:])
        result[key] = {
            "status": "AVAILABLE", "value": value, "price_above": current_close > value, "price_below": current_close < value,
            "slope": _ma_slope(closes, length),
        }
    return result


def _ma_ordering(ma_context: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    available = [(length, ma_context[str(length)]["value"]) for length in MA_LENGTHS if ma_context[str(length)]["status"] == "AVAILABLE"]
    if len(available) < 2:
        return {"status": "NOT_AVAILABLE", "reason": "FEWER_THAN_TWO_MOVING_AVERAGES_AVAILABLE"}
    values = [value for _length, value in available]
    ascending_short_to_long = all(values[i] >= values[i + 1] for i in range(len(values) - 1))   # MA20 highest -> MA200 lowest
    descending_short_to_long = all(values[i] <= values[i + 1] for i in range(len(values) - 1))  # MA20 lowest -> MA200 highest
    ordering = "ASCENDING_SHORT_OVER_LONG" if ascending_short_to_long else "DESCENDING_SHORT_UNDER_LONG" if descending_short_to_long else "MIXED"
    return {"status": "AVAILABLE", "ma_ordering": ordering, "lengths_compared": [length for length, _v in available]}


# ── MACD ────────────────────────────────────────────────────────────────────

def _ema_series(values: list[float], period: int) -> list[float | None]:
    n = len(values)
    result: list[float | None] = [None] * n
    if n < period:
        return result
    alpha = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    result[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = values[i] * alpha + prev * (1.0 - alpha)
        result[i] = prev
    return result


def _macd_lines(closes: list[float]) -> tuple[list[float | None], list[float | None], list[float | None]]:
    ema_fast = _ema_series(closes, MACD_FAST)
    ema_slow = _ema_series(closes, MACD_SLOW)
    macd_line: list[float | None] = [None if a is None or b is None else a - b for a, b in zip(ema_fast, ema_slow)]
    valid_start = next((i for i, v in enumerate(macd_line) if v is not None), None)
    if valid_start is None:
        return macd_line, [None] * len(closes), [None] * len(closes)
    signal_tail = _ema_series(macd_line[valid_start:], MACD_SIGNAL)
    signal_line: list[float | None] = [None] * valid_start + signal_tail
    histogram: list[float | None] = [None if m is None or s is None else m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, histogram


def _macd_cross_event(macd_line: list[float | None], signal_line: list[float | None]) -> str:
    if len(macd_line) < 2 or macd_line[-1] is None or signal_line[-1] is None or macd_line[-2] is None or signal_line[-2] is None:
        return "NONE"
    prior_diff, current_diff = macd_line[-2] - signal_line[-2], macd_line[-1] - signal_line[-1]
    if prior_diff <= 0 < current_diff:
        return "BULLISH_CROSS"
    if prior_diff >= 0 > current_diff:
        return "BEARISH_CROSS"
    return "NONE"


def _macd_context(closes: list[float], sessions: list[str]) -> dict[str, Any]:
    depth = len(closes)
    if depth < MACD_MIN_SESSIONS:
        return {"status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_HISTORY_FOR_MACD", "sessions_required": MACD_MIN_SESSIONS, "sessions_available": depth, "method": MACD_METHOD}
    macd_line, signal_line, histogram = _macd_lines(closes)
    if macd_line[-1] is None or signal_line[-1] is None:
        return {"status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_HISTORY_FOR_MACD", "sessions_required": MACD_MIN_SESSIONS, "sessions_available": depth, "method": MACD_METHOD}
    current_hist = histogram[-1]
    prior_hist = histogram[-2] if len(histogram) >= 2 else None
    hist_direction = (
        "NOT_AVAILABLE" if not isinstance(prior_hist, (int, float))
        else "EXPANDING" if abs(current_hist) > abs(prior_hist)
        else "CONTRACTING" if abs(current_hist) < abs(prior_hist) else "FLAT"
    )
    return {
        "status": "AVAILABLE", "method": MACD_METHOD,
        "macd_line": macd_line[-1], "signal_line": signal_line[-1], "histogram": current_hist,
        "sign": "POSITIVE" if macd_line[-1] > 0 else "NEGATIVE" if macd_line[-1] < 0 else "ZERO",
        "cross_event": _macd_cross_event(macd_line, signal_line),
        "histogram_direction": hist_direction,
        "fast_period": MACD_FAST, "slow_period": MACD_SLOW, "signal_period": MACD_SIGNAL,
        "as_of_session": sessions[-1],
    }


def _price_direction_1d(closes: list[float]) -> str:
    if len(closes) < 2:
        return "NOT_AVAILABLE"
    if closes[-1] > closes[-2]:
        return "UP"
    if closes[-1] < closes[-2]:
        return "DOWN"
    return "FLAT"


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

    winning_record, history_source = resolve_target_session_observations(
        pf_record=pf_record, recovery_override=recovery_override, target_session=target_session,
    )
    history_record = {"observations": winning_record.get("observations")} if history_source == "RETAINED_TECHNICAL_HISTORY_RECOVERY" else winning_record
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

    rsi_context, rsi_series = _rsi_context(closes, sessions)
    ma_context = _moving_average_context(closes)

    return {
        "ticker": ticker, "eligibility": {"status": "ELIGIBLE"}, "close_history_depth": depth,
        "technical_history_lineage": {
            "source": history_source, "recovery_artifact_identity": recovery_identity,
            "recovery_payload_sha256": recovery_override.get("payload_sha256") if isinstance(recovery_override, Mapping) else None,
        },
        "price_direction_1d": _price_direction_1d(closes),
        "rsi": rsi_context,
        "rsi_divergence": _rsi_divergence_context(closes, sessions, rsi_series),
        "moving_averages": ma_context,
        "moving_average_ordering": _ma_ordering(ma_context),
        "macd": _macd_context(closes, sessions),
        "authority_boundary": _MOMENTUM_AUTHORITY_BOUNDARY,
    }


# ── Public build_artifact ─────────────────────────────────────────────────────

def build_artifact(
    *, current_descriptive: Mapping[str, Any], p3f9b_snapshot: Mapping[str, Any], requested_at: str,
    technical_history_recovery_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the complete momentum context artifact. Zero silent drops: every candidate gets a
    record, eligible or not. Same eligibility gate and close-series resolution as
    ``technical_structure_context.build_artifact`` so the two contracts never silently disagree
    about which observations were authoritative for a session."""
    _verify_descriptive_identity(current_descriptive)
    target_session = current_descriptive.get("session")
    if not target_session:
        raise TacticalMomentumContextError("SESSION_MISSING")

    _verify_p3f9b_identity(p3f9b_snapshot)
    expected_snapshot_identity = current_descriptive.get("source_artifacts", {}).get("p3f9b_snapshot")
    if expected_snapshot_identity and expected_snapshot_identity != p3f9b_snapshot.get("snapshot_identity"):
        raise TacticalMomentumContextError("P3F9B_SNAPSHOT_LINEAGE_MISMATCH")

    recovery_overrides, recovery_identity = _recovery_overrides(
        technical_history_recovery_artifact, target_session=target_session,
        snapshot_identity=p3f9b_snapshot.get("snapshot_identity"),
    )

    descriptive_records = current_descriptive.get("records")
    pf_records = p3f9b_snapshot.get("records")
    if not isinstance(descriptive_records, Mapping) or not isinstance(pf_records, Mapping):
        raise TacticalMomentumContextError("SOURCE_RECORDS_INVALID")

    records: dict[str, dict[str, Any]] = {}
    for ticker in sorted(descriptive_records):
        records[ticker] = _classify_ticker(
            ticker, descriptive_record=descriptive_records[ticker],
            pf_record=pf_records.get(ticker), target_session=target_session,
            recovery_override=recovery_overrides.get(ticker), recovery_identity=recovery_identity,
        )

    eligible_count = sum(1 for r in records.values() if r["eligibility"]["status"] == "ELIGIBLE")
    rsi_available = sum(1 for r in records.values() if r["rsi"]["status"] == "AVAILABLE")
    divergence_bullish = sum(1 for r in records.values() if (r["rsi_divergence"] or {}).get("bullish_divergence_candidate"))
    divergence_bearish = sum(1 for r in records.values() if (r["rsi_divergence"] or {}).get("bearish_divergence_candidate"))
    macd_available = sum(1 for r in records.values() if r["macd"]["status"] == "AVAILABLE")
    ma_available_counts = {
        str(length): sum(1 for r in records.values() if r["moving_averages"].get(str(length), {}).get("status") == "AVAILABLE")
        for length in MA_LENGTHS
    }

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "milestone": MILESTONE,
        "requested_at": requested_at, "target_session": target_session,
        "source_artifacts": {
            "current_descriptive": current_descriptive.get("artifact_identity"),
            "p3f9b_snapshot": p3f9b_snapshot.get("snapshot_identity"),
            "technical_history_recovery": recovery_identity,
        },
        "coverage": {
            "candidate_count": len(records), "eligible_count": eligible_count,
            "not_eligible_count": len(records) - eligible_count,
            "rsi_available_count": rsi_available,
            "rsi_divergence_bullish_candidate_count": divergence_bullish,
            "rsi_divergence_bearish_candidate_count": divergence_bearish,
            "macd_available_count": macd_available,
            "moving_average_available_counts": ma_available_counts,
        },
        "authority_boundary": _MOMENTUM_AUTHORITY_BOUNDARY,
        "records": records,
    }
    identity = content_identity(artifact)
    artifact["artifact_sha256"], artifact["artifact_identity"] = identity["artifact_sha256"], identity["artifact_identity"]
    return artifact
