"""Deterministic current-research close-based structure context (TACTICAL_AND_BEHAVIORAL_ENGINE_V2).

Supersedes ``price_structure_breakout_context.py`` for the governed V2 lineage: same close-only
philosophy and the same ``NEAR`` (2%) proximity convention (imported, never redefined), but consumes
the current governed artifact shapes (``market_wide_current_descriptive_research`` +
the retained P3F9B exact-session snapshot) instead of the older ``daily_market_research`` bundle, and
adds genuinely new self-referential (this-ticker-vs-its-own-past) facts that did not exist anywhere
in the governed lineage before: a rolling MA20 slope, self-relative realized-volatility contraction,
base duration, and a session-over-session breakout-failure / support-re-entry read.

Close-only by design. The retained exact-session snapshot carries a documented
``RETAINED_HIGH_LOW_SCALE_INCOMPATIBLE_NOT_USED`` limitation: no true ATR, Donchian channel, or any
other high/low-geometry feature is computed here. Every record instead carries an explicit
``high_low_basis`` block naming exactly which feature classes are unavailable for that reason,
without blocking any of this module's close-only facts for the same ticker.

Retained close-history depth is heterogeneous per ticker (confirmed against real 2026-08-28 data:
observed depths ranged from ~20 to 250 sessions for different tickers, driven by each ticker's own
acquisition/recovery history) -- never assumed uniform. Every record reports the exact
``close_history_depth`` used and an explicit per-feature ``NOT_AVAILABLE`` status wherever the
retained depth is insufficient for that feature's own minimum window. No feature is computed by
padding, imputing, or extrapolating missing history.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from statistics import pstdev
from typing import Any, Mapping, Sequence

from field_temporal_contract import stable_id as _p3f9b_stable_id
from price_structure_breakout_context import NEAR

CONTRACT_VERSION = "technical_structure_context/v1"
MILESTONE = "TACTICAL_AND_BEHAVIORAL_ENGINE_V2"

MIN_STRUCTURE_LOOKBACK = 20  # matches price_structure_breakout_context.LOOKBACK; a completed-session count
RANGE_SPLIT = 10  # first-10/last-10 split of the 20-session structure window, same convention as price_structure_breakout_context
SLOPE_LOOKBACK_SESSIONS = 5  # completed sessions back for the MA20-slope comparison
VOLATILITY_WINDOW = 20  # matches market_features()'s own volatility_20d window
VOLATILITY_OFFSET_SESSIONS = 10  # how far back the "prior" volatility window ends, for self-relative contraction
MAX_LOOKBACK_SESSIONS = 250  # explicit completed-session cap on retained history actually used; not a calendar-day convention
COMPRESSION_RATIO = 0.7
EXPANSION_RATIO = 1.3
BASE_DURATION_CAP_SESSIONS = 60  # reporting cap so base_duration_sessions never implies untracked depth

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


class TechnicalStructureContextError(ValueError):
    """A retained input or an invariant of this contract is violated."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


_IDENTITY_EXCLUDED_KEYS = {"artifact_sha256", "artifact_identity", "requested_at"}  # wall-clock never enters canonical identity


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


def _closes(pf_record: Mapping[str, Any] | None) -> tuple[list[str], list[float]]:
    observations = (pf_record or {}).get("observations")
    if not isinstance(observations, list) or not observations:
        return [], []
    ordered = sorted(
        (row for row in observations if isinstance(row, Mapping) and row.get("session") and isinstance(row.get("close"), (int, float))),
        key=lambda row: str(row["session"]),
    )
    return [str(row["session"]) for row in ordered], [float(row["close"]) for row in ordered]


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
    """Self-referential (this ticker vs its own recent past) realized-volatility contraction.

    Deliberately distinct from the existing cross-sectional ``volatility_20d`` regime (this ticker vs
    the market's contemporaneous median): this compares the ticker's own most-recent 20-session
    realized volatility against its own 20-session realized volatility ending
    ``VOLATILITY_OFFSET_SESSIONS`` sessions earlier -- the self-relative measure that did not exist
    anywhere in the governed lineage before this module.
    """
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
    """Trailing consecutive-session count where close stayed within [support, resistance], capped."""
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
    """Session-over-session structure comparison: a fresh breakout vs a failed one, a fresh breakdown
    vs a support re-entry. Needs one additional prior session beyond the baseline structure window."""
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


def _insufficient_record(ticker: str, reason: str, depth: int) -> dict[str, Any]:
    return {
        "ticker": ticker, "eligibility": {"status": "NOT_ELIGIBLE", "reason": reason},
        "close_history_depth": depth,
        "trend_context": {"status": "NOT_AVAILABLE"}, "structure_context": {"status": "NOT_AVAILABLE"},
        "contraction_context": {"status": "NOT_AVAILABLE"}, "base_context": {"status": "NOT_AVAILABLE"},
        "breakout_context": {"status": "NOT_AVAILABLE"}, "relative_volume": {"status": "NOT_AVAILABLE"},
        "high_low_basis": {"status": "NOT_APPLICABLE", "reason": "NO_ELIGIBLE_CLOSE_SERIES"},
        "blockers": [reason], "warnings": [], "authority_tier": None,
    }


def _classify_ticker(ticker: str, *, descriptive_record: Mapping[str, Any], pf_record: Mapping[str, Any] | None, target_session: str) -> dict[str, Any]:
    technical = descriptive_record.get("technical_features", {})
    eligible = technical.get("status") == "SHADOW_ONLY" and technical.get("is_current_session") is True
    if not eligible:
        return _insufficient_record(ticker, "TECHNICAL_FEATURES_UNAVAILABLE_OR_NOT_CURRENT_SESSION", 0)

    sessions, closes = _closes(pf_record)
    if not sessions or sessions[-1] != target_session:
        return _insufficient_record(ticker, "RETAINED_CLOSE_SERIES_MISSING_OR_NOT_CURRENT_SESSION", len(closes))
    if len(closes) > MAX_LOOKBACK_SESSIONS:
        closes = closes[-MAX_LOOKBACK_SESSIONS:]
    depth = len(closes)

    blockers: list[str] = []
    values = technical.get("values", {})
    trend_context = {
        "status": "AVAILABLE", "trend_state": descriptive_record.get("trend_state"),
        "close": values.get("close"), "ma_20": values.get("ma_20"), "momentum_20d": values.get("momentum_20d"),
        "ma20_slope": _ma20_slope(closes),
    }

    if depth < MIN_STRUCTURE_LOOKBACK:
        structure_context = {"status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_HISTORY_FOR_STRUCTURE", "sessions_required": MIN_STRUCTURE_LOOKBACK, "sessions_available": depth}
        contraction_context = {"status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_HISTORY_FOR_STRUCTURE"}
        base_context = {"status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_HISTORY_FOR_STRUCTURE"}
        blockers.append("INSUFFICIENT_HISTORY_FOR_STRUCTURE")
    else:
        window = closes[-MIN_STRUCTURE_LOOKBACK:]
        structure = _structure(window)
        structure_context = {"status": "AVAILABLE", **structure}
        contraction_context = {
            "status": "AVAILABLE", "range_state": _range_state(window),
            "self_relative_volatility": _self_relative_volatility(closes),
        }
        base_context = _base_duration(window, closes, structure["support"]["value"], structure["resistance"]["value"])

    breakout_context = _breakout_event(closes)

    relative_volume_value = values.get("relative_volume_provider_scoped")
    relative_volume = {
        "status": "AVAILABLE" if isinstance(relative_volume_value, (int, float)) else "NOT_AVAILABLE",
        "relative_volume_provider_scoped": relative_volume_value,
        "authority_tier": "DERIVED_PROXY", "warning": "NOT_LIQUIDITY_OR_TURNOVER; provider-scoped, own-20-session-median basis",
    }

    return {
        "ticker": ticker, "eligibility": {"status": "ELIGIBLE"}, "close_history_depth": depth,
        "trend_context": trend_context, "structure_context": structure_context,
        "contraction_context": contraction_context, "base_context": base_context,
        "breakout_context": breakout_context, "relative_volume": relative_volume,
        "high_low_basis": {
            "status": "NOT_COMPATIBLE", "reason": "HIGH_LOW_BASIS_NOT_COMPATIBLE",
            "affected_feature_classes": list(HIGH_LOW_BLOCKED_FEATURES),
            "fallback": "CLOSE_ONLY_PROXY_USED_FOR_STRUCTURE_AND_CONTRACTION",
        },
        "blockers": blockers, "warnings": ["ADJUSTED_RETROSPECTIVE_NOT_RAW_AS_TRADED", "CLOSE_ONLY_STRUCTURE_NOT_HIGH_LOW_GEOMETRY"],
        "authority_tier": "SHADOW_ONLY",
        "method": {"identity": CONTRACT_VERSION, "min_structure_lookback_sessions": MIN_STRUCTURE_LOOKBACK, "max_lookback_sessions_cap": MAX_LOOKBACK_SESSIONS, "near_threshold": NEAR},
    }


def build_artifact(*, current_descriptive: Mapping[str, Any], p3f9b_snapshot: Mapping[str, Any], requested_at: str) -> dict[str, Any]:
    """Build the complete technical structure context artifact over every ticker in
    ``current_descriptive`` (zero silent drops: every candidate gets a record, eligible or not)."""
    _verify_descriptive_identity(current_descriptive)
    _verify_p3f9b_identity(p3f9b_snapshot)

    target_session = current_descriptive.get("session")
    if not target_session or p3f9b_snapshot.get("resolved_completed_session") != target_session:
        raise TechnicalStructureContextError("P3F9B_SESSION_MISMATCH")
    expected_snapshot_identity = current_descriptive.get("input_lineage", {}).get("p3f9b_snapshot_identity")
    if expected_snapshot_identity and expected_snapshot_identity != p3f9b_snapshot.get("snapshot_identity"):
        raise TechnicalStructureContextError("P3F9B_SNAPSHOT_LINEAGE_MISMATCH")

    descriptive_records = current_descriptive.get("records")
    pf_records = p3f9b_snapshot.get("records")
    if not isinstance(descriptive_records, Mapping) or not isinstance(pf_records, Mapping):
        raise TechnicalStructureContextError("SOURCE_RECORDS_INVALID")

    records: dict[str, dict[str, Any]] = {}
    for ticker in sorted(descriptive_records):
        records[ticker] = _classify_ticker(
            ticker, descriptive_record=descriptive_records[ticker], pf_record=pf_records.get(ticker), target_session=target_session,
        )

    eligible_count = sum(1 for record in records.values() if record["eligibility"]["status"] == "ELIGIBLE")
    structure_counts = Counter(record["structure_context"].get("structure_status", "NOT_AVAILABLE") for record in records.values())
    range_counts = Counter(record["contraction_context"].get("range_state", "NOT_AVAILABLE") for record in records.values())
    contraction_counts = Counter((record["contraction_context"].get("self_relative_volatility") or {}).get("self_relative_volatility_state", "NOT_AVAILABLE") for record in records.values())
    slope_counts = Counter(record["trend_context"].get("ma20_slope", {}).get("slope_state", "NOT_AVAILABLE") for record in records.values())
    breakout_event_counts = Counter(record["breakout_context"].get("event", "NOT_AVAILABLE") for record in records.values())
    base_status_counts = Counter(record["base_context"].get("base_status", "NOT_AVAILABLE") for record in records.values())

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "milestone": MILESTONE,
        "requested_at": requested_at, "session": target_session,
        "source_artifacts": {
            "current_descriptive": current_descriptive.get("artifact_identity"),
            "p3f9b_snapshot": p3f9b_snapshot.get("snapshot_identity"),
        },
        "coverage": {
            "candidate_count": len(records), "eligible_count": eligible_count,
            "not_eligible_count": len(records) - eligible_count,
            "structure_status_counts": dict(sorted(structure_counts.items())),
            "range_state_counts": dict(sorted(range_counts.items())),
            "self_relative_volatility_state_counts": dict(sorted(contraction_counts.items())),
            "ma20_slope_state_counts": dict(sorted(slope_counts.items())),
            "breakout_event_counts": dict(sorted(breakout_event_counts.items())),
            "base_status_counts": dict(sorted(base_status_counts.items())),
            "insufficient_reason_counts": dict(sorted(Counter(
                reason for record in records.values() for reason in record["blockers"]
            ).items())),
        },
        "blocked_outputs": {
            "true_atr_or_donchian_high_low_geometry": "HIGH_LOW_BASIS_NOT_COMPATIBLE",
            "ordinal_market_ranking": "RANKING_PROHIBITED", "opportunity_score": "SCORING_PROHIBITED",
            "probabilities_or_target_prices": "FORECAST_PROHIBITED", "fixed_stop_percentage": "NOT_IMPLEMENTED_NO_ARBITRARY_STOP",
            "historical_raw_as_traded_or_pit": "RAW_AS_TRADED_NOT_PROMOTED", "backtesting": "OUT_OF_SCOPE_THIS_MILESTONE",
        },
        "authority_boundary": {
            "is_actionable": False, "not_a_recommendation_or_execution_instruction": True, "requires_human_review": True,
            "close_only_structure_not_high_low_geometry": True, "self_relative_volatility_is_not_a_forecast": True,
        },
        "records": records,
    }
    identity = content_identity(artifact)
    artifact["artifact_sha256"], artifact["artifact_identity"] = identity["artifact_sha256"], identity["artifact_identity"]
    return artifact
