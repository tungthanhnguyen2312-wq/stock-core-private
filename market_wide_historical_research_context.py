"""Market-wide retrospective descriptive historical context for current research.

Uses already-retained DNSE OHLC (P3F9B exact-session snapshot, plus extended-history
recovery overrides where present). This is within-ticker descriptive research over
actual retained trading observations. It is not PIT backtesting, not historical
strategy performance, and not a modifier of research_priority, entry_action,
strategy eligibility, or sizing.

Rolling technical primitives reuse ``mva_daily_research_bundle.market_features``
unmodified on explicit 20-observation slices. Adjusted/retrospective provider
history is labelled as such and never promoted to RAW_AS_TRADED or PIT-safe.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping, Sequence

from field_temporal_contract import stable_id as _p3f9b_stable_id
from market_wide_current_technical_coverage_scaleout import (
    content_identity as recovery_content_identity,
)
from mva_daily_research_bundle import LOOKBACK_SESSIONS, _as_float, market_features
from price_structure_breakout_context import NEAR

CONTRACT_VERSION = "market_wide_historical_research_context/v1"
FIFTY_TWO_WEEK_OBSERVATIONS = 252
MIN_TRAILING_RANGE_OBSERVATIONS = 20
MIN_PERCENTILE_AVAILABLE = 20
MIN_PERCENTILE_PARTIAL = 10
MATURE_MA_PERSISTENCE_WINDOWS = 10
EARLY_REVERSAL_MAX_MOMENTUM_AGE = 5

IN_SCOPE_ACTIVITY_STATES = frozenset({
    "ACTIVE_LISTED_OBSERVED",
    "ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION",
})

PRICE_BASIS = "ADJUSTED_RETROSPECTIVE"
SOURCE_PRICE_BASIS_LABEL = (
    "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED"
)

BLOCKED_OUTPUTS = {
    "stock_rankings": "RANKING_PROHIBITED",
    "buy_sell_recommendations": "RECOMMENDATION_PROHIBITED",
    "probabilities_or_target_prices": "FORECAST_PROHIBITED",
    "historical_strategy_performance_win_rate_alpha": "HISTORICAL_PERFORMANCE_PROHIBITED",
    "executable_returns_or_backtest": "BACKTEST_PROHIBITED",
    "calibrated_probability": "UNCALIBRATED_FREQUENCY_ONLY",
    "portfolio_weights_or_position_sizes": "SIZING_EXECUTION_PROHIBITED",
    "historical_raw_as_traded_or_pit": "RAW_AS_TRADED_NOT_PROMOTED",
    "historical_active_universe_or_pit_membership": "PIT_MEMBERSHIP_UNAVAILABLE",
    "cross_sectional_historical_comparison": "HISTORICAL_PIT_MEMBERSHIP_UNAVAILABLE",
    "research_priority_entry_action_strategy_eligibility_sizing": "SEMANTICALLY_SEPARATE_NOT_MODIFIED",
}

FORBIDDEN_PAYLOAD_TOKENS = (
    "win_rate",
    "alpha",
    "sharpe",
    "expected_return",
    "hit_rate",
    "backtest_return",
    "calibrated_probability",
    "target_price",
    "position_size",
    "buy_signal",
    "sell_signal",
)


class MarketWideHistoricalResearchContextError(ValueError):
    """A retained input or an invariant of this contract is violated."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = _hash(payload)
    return {
        "artifact_sha256": digest,
        "artifact_identity": f"market_wide_historical_research_context:{digest}",
    }


def _verify_p3f9b_identity(snapshot: Mapping[str, Any]) -> None:
    payload = {key: value for key, value in snapshot.items() if key not in {"snapshot_sha256", "snapshot_identity"}}
    if snapshot.get("snapshot_sha256") != _p3f9b_stable_id(payload):
        raise MarketWideHistoricalResearchContextError("P3F9B_SNAPSHOT_IDENTITY_MISMATCH")


def _verify_hashed_identity(artifact: Mapping[str, Any], *, label: str) -> None:
    if artifact.get("artifact_sha256") != content_identity(artifact)["artifact_sha256"]:
        raise MarketWideHistoricalResearchContextError(f"{label}_IDENTITY_MISMATCH")


def _percentile(current: float | None, history: Sequence[float]) -> float | None:
    if current is None or not history:
        return None
    below = sum(1 for value in history if value < current)
    equal = sum(1 for value in history if value == current)
    return (below + 0.5 * equal) / len(history)


def _sample_status(count: int) -> str:
    if count >= MIN_PERCENTILE_AVAILABLE:
        return "AVAILABLE"
    if count >= MIN_PERCENTILE_PARTIAL:
        return "PARTIAL"
    return "INSUFFICIENT_HISTORY"


def _tertile_regime(percentile: float | None) -> str | None:
    if percentile is None:
        return None
    if percentile < 1.0 / 3.0:
        return "LOW"
    if percentile < 2.0 / 3.0:
        return "MID"
    return "HIGH"


def _rarity_bucket(frequency: float | None) -> str | None:
    if frequency is None:
        return None
    if frequency >= 0.20:
        return "COMMON_IN_RETAINED_HISTORY"
    if frequency >= 0.05:
        return "UNCOMMON_IN_RETAINED_HISTORY"
    return "RARE_IN_RETAINED_HISTORY"


def _momentum_sign(value: float | None) -> str | None:
    if value is None:
        return None
    if value > 0:
        return "POSITIVE"
    if value < 0:
        return "NEGATIVE"
    return "FLAT"


def _trend_state(close: float | None, ma20: float | None) -> str | None:
    if not isinstance(close, (int, float)) or not isinstance(ma20, (int, float)):
        return None
    return "ABOVE_MA20" if close > ma20 else "AT_OR_BELOW_MA20"


def _persistence(values: Sequence[Any]) -> int | None:
    if not values or values[-1] is None:
        return None
    current = values[-1]
    age = 0
    for value in reversed(values):
        if value != current:
            break
        age += 1
    return age


def _blocked_field(status: str, reason: str, **extra: Any) -> dict[str, Any]:
    payload = {"status": status, "reason": reason, "value": None}
    payload.update(extra)
    return payload


def _observation_bars(observations: Sequence[Any]) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for row in observations:
        if not isinstance(row, Mapping):
            continue
        session = row.get("session")
        close = _as_float(row.get("close"))
        if not session or close is None or close <= 0:
            continue
        bar = {
            "session": str(session),
            "open": _as_float(row.get("open")),
            "high": _as_float(row.get("high")),
            "low": _as_float(row.get("low")),
            "close": close,
            "volume": _as_float(row.get("volume")),
            "price_basis": row.get("price_basis"),
            "provider": row.get("provider"),
        }
        seen[bar["session"]] = bar
    for session in sorted(seen):
        bars.append(seen[session])
    return bars


def _feature_rows(bars: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"date": bar["session"], "close": bar["close"], "volume": bar["volume"]}
        for bar in bars
    ]


def _rolling_feature_windows(bars: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    rows = _feature_rows(bars)
    for index in range(LOOKBACK_SESSIONS - 1, len(rows)):
        sliced = rows[index - LOOKBACK_SESSIONS + 1: index + 1]
        features = market_features(sliced)
        values = features.get("values") if features.get("status") == "SHADOW_ONLY" else {}
        close = values.get("close") if isinstance(values, Mapping) else None
        ma20 = values.get("ma_20") if isinstance(values, Mapping) else None
        momentum = values.get("momentum_20d") if isinstance(values, Mapping) else None
        windows.append({
            "session": bars[index]["session"],
            "status": features.get("status"),
            "values": dict(values) if isinstance(values, Mapping) else {},
            "trend_state": _trend_state(close, ma20),
            "momentum_sign": _momentum_sign(momentum),
            "state_key": (
                f"{_trend_state(close, ma20)}|{_momentum_sign(momentum)}"
                if _trend_state(close, ma20) and _momentum_sign(momentum) else None
            ),
        })
    return windows


def _range_extent(bars: Sequence[Mapping[str, Any]]) -> tuple[str, float | None, float | None]:
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    high_low_complete = True
    for bar in bars:
        closes.append(float(bar["close"]))
        high = bar.get("high")
        low = bar.get("low")
        if isinstance(high, (int, float)) and isinstance(low, (int, float)) and high > 0 and low > 0:
            highs.append(float(high))
            lows.append(float(low))
        else:
            high_low_complete = False
    if high_low_complete and highs and lows:
        return "high_low", max(highs), min(lows)
    if closes:
        return "close_only", max(closes), min(closes)
    return "unavailable", None, None


def _drawdown_path(bars: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    path: list[dict[str, Any]] = []
    peak = None
    peak_session = None
    for bar in bars:
        close = float(bar["close"])
        if peak is None or close >= peak:
            peak = close
            peak_session = bar["session"]
        path.append({
            "session": bar["session"],
            "close": close,
            "peak_close": peak,
            "peak_session": peak_session,
            "drawdown": (close / peak) - 1.0 if peak else None,
        })
    return path


def _trailing_range(bars: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(bars) < MIN_TRAILING_RANGE_OBSERVATIONS:
        return _blocked_field(
            "INSUFFICIENT_HISTORY",
            "RETAINED_OBSERVED_SESSIONS_BELOW_TRAILING_RANGE_MINIMUM",
            observation_count=len(bars),
            minimum_observations=MIN_TRAILING_RANGE_OBSERVATIONS,
            window_rule="ACTUAL_RETAINED_TRADING_OBSERVATIONS_NO_CALENDAR_IMPUTATION",
        )
    series, high, low = _range_extent(bars)
    close = float(bars[-1]["close"])
    span = (high - low) if high is not None and low is not None else None
    position = ((close - low) / span) if span else None
    return {
        "status": "AVAILABLE",
        "series": series,
        "high": high,
        "low": low,
        "close": close,
        "position": position,
        "pct_from_high": (close / high - 1.0) if high else None,
        "pct_from_low": (close / low - 1.0) if low else None,
        "observation_count": len(bars),
        "first_session": bars[0]["session"],
        "last_session": bars[-1]["session"],
        "window_rule": "ACTUAL_RETAINED_TRADING_OBSERVATIONS_NO_CALENDAR_IMPUTATION",
    }


def _fifty_two_week_range(bars: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(bars) < FIFTY_TWO_WEEK_OBSERVATIONS:
        return _blocked_field(
            "INSUFFICIENT_HISTORY",
            "RETAINED_OBSERVED_SESSIONS_BELOW_252",
            observation_count=len(bars),
            minimum_observations=FIFTY_TWO_WEEK_OBSERVATIONS,
            window_rule="ACTUAL_RETAINED_TRADING_OBSERVATIONS_NO_CALENDAR_IMPUTATION",
        )
    window = bars[-FIFTY_TWO_WEEK_OBSERVATIONS:]
    series, high, low = _range_extent(window)
    close = float(window[-1]["close"])
    span = (high - low) if high is not None and low is not None else None
    return {
        "status": "AVAILABLE",
        "series": series,
        "high": high,
        "low": low,
        "close": close,
        "position": ((close - low) / span) if span else None,
        "pct_from_high": (close / high - 1.0) if high else None,
        "pct_from_low": (close / low - 1.0) if low else None,
        "observation_count": len(window),
        "first_session": window[0]["session"],
        "last_session": window[-1]["session"],
        "window_rule": "LAST_252_RETAINED_TRADING_OBSERVATIONS_NO_CALENDAR_IMPUTATION",
    }


def _structural_state(
    *,
    trend_state: str | None,
    momentum_sign: str | None,
    momentum_age: int | None,
    ma_age: int | None,
    near_ma20: bool | None,
    vol_regime: str | None,
) -> dict[str, Any]:
    if trend_state is None or momentum_sign is None:
        return _blocked_field("INSUFFICIENT_HISTORY", "COMPLETE_20_SESSION_FEATURE_WINDOW_REQUIRED")
    value = "INDETERMINATE"
    if (
        trend_state == "AT_OR_BELOW_MA20"
        and momentum_sign == "POSITIVE"
        and momentum_age is not None
        and momentum_age <= EARLY_REVERSAL_MAX_MOMENTUM_AGE
    ):
        value = "EARLY_REVERSAL"
    elif (
        near_ma20 is True
        and vol_regime in {None, "LOW", "MID"}
        and momentum_sign != "NEGATIVE"
    ):
        value = "BASE"
    elif (
        trend_state == "ABOVE_MA20"
        and momentum_sign == "POSITIVE"
        and ma_age is not None
        and ma_age >= MATURE_MA_PERSISTENCE_WINDOWS
    ):
        value = "MATURE_TREND"
    elif trend_state == "ABOVE_MA20" and momentum_sign == "POSITIVE":
        value = "TREND_CONTINUATION"
    elif momentum_sign in {"NEGATIVE", "FLAT"} or trend_state == "AT_OR_BELOW_MA20":
        value = "DETERIORATION"
    return {
        "status": "AVAILABLE",
        "value": value,
        "method": "within_ticker_existing_primitives_first_match",
        "primitives": {
            "trend_state": trend_state,
            "momentum_sign": momentum_sign,
            "momentum_persistence_windows": momentum_age,
            "ma_alignment_persistence_windows": ma_age,
            "near_ma20": near_ma20,
            "volatility_regime": vol_regime,
            "near_threshold": NEAR,
            "mature_ma_persistence_windows": MATURE_MA_PERSISTENCE_WINDOWS,
            "early_reversal_max_momentum_age": EARLY_REVERSAL_MAX_MOMENTUM_AGE,
        },
        "not_entry_state": True,
        "not_strategy_eligibility": True,
    }


def evaluate_historical_context(
    observations: Sequence[Any],
    *,
    target_session: str,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure within-ticker descriptive context over retained observations."""
    bars = _observation_bars(observations)
    provenance = dict(provenance or {"source": "RETAINED_P3F9B_EXACT_SESSION_SNAPSHOT"})
    if not bars:
        return {
            "context_status": "MISSING",
            "as_of_session": None,
            "is_current_session": False,
            "history": {
                "observation_count": 0,
                "first_session": None,
                "last_session": None,
                "price_basis": PRICE_BASIS,
                "price_basis_source_label": SOURCE_PRICE_BASIS_LABEL,
                "historical_pit_eligible": False,
                "raw_as_traded": "NOT_PROMOTED",
                "window_rule": "ACTUAL_RETAINED_TRADING_OBSERVATIONS_NO_CALENDAR_IMPUTATION",
                **provenance,
            },
            "trailing_range": _blocked_field("MISSING", "NO_RETAINED_TRADING_OBSERVATIONS"),
            "fifty_two_week_range": _blocked_field("MISSING", "NO_RETAINED_TRADING_OBSERVATIONS"),
            "drawdown": _blocked_field("MISSING", "NO_RETAINED_TRADING_OBSERVATIONS"),
            "volatility_regime": _blocked_field("MISSING", "NO_RETAINED_TRADING_OBSERVATIONS"),
            "momentum": _blocked_field("MISSING", "NO_RETAINED_TRADING_OBSERVATIONS"),
            "ma_alignment": _blocked_field("MISSING", "NO_RETAINED_TRADING_OBSERVATIONS"),
            "relative_volume": _blocked_field("MISSING", "NO_RETAINED_TRADING_OBSERVATIONS"),
            "technical_state_frequency": _blocked_field("MISSING", "NO_RETAINED_TRADING_OBSERVATIONS"),
            "structural_state": _blocked_field("MISSING", "NO_RETAINED_TRADING_OBSERVATIONS"),
            "cross_sectional_historical_comparison": _blocked_field(
                "BLOCKED", "HISTORICAL_PIT_MEMBERSHIP_UNAVAILABLE",
            ),
        }

    as_of = bars[-1]["session"]
    windows = _rolling_feature_windows(bars)
    usable = [window for window in windows if window["status"] == "SHADOW_ONLY"]
    current = usable[-1] if usable else None
    values = dict(current["values"]) if current else {}
    vol_history = [
        window["values"]["volatility_20d"]
        for window in usable
        if isinstance(window["values"].get("volatility_20d"), (int, float))
    ]
    rvol_history = [
        window["values"]["relative_volume_provider_scoped"]
        for window in usable
        if isinstance(window["values"].get("relative_volume_provider_scoped"), (int, float))
    ]
    current_vol = values.get("volatility_20d")
    current_rvol = values.get("relative_volume_provider_scoped")
    vol_percentile = _percentile(current_vol, vol_history)
    rvol_percentile = _percentile(current_rvol, rvol_history)
    vol_status = _sample_status(len(vol_history)) if current else "INSUFFICIENT_HISTORY"
    rvol_status = _sample_status(len(rvol_history)) if current else "INSUFFICIENT_HISTORY"
    vol_regime = _tertile_regime(vol_percentile) if vol_status != "INSUFFICIENT_HISTORY" else None

    drawdowns = _drawdown_path(bars)
    current_dd = drawdowns[-1]
    magnitudes = [-item["drawdown"] for item in drawdowns if item["drawdown"] is not None]
    current_magnitude = -current_dd["drawdown"] if current_dd["drawdown"] is not None else None
    dd_percentile = _percentile(current_magnitude, magnitudes)
    dd_status = _sample_status(len(magnitudes))

    trend_states = [window["trend_state"] for window in usable]
    momentum_signs = [window["momentum_sign"] for window in usable]
    ma_age = _persistence(trend_states)
    momentum_age = _persistence(momentum_signs)
    close = values.get("close")
    ma20 = values.get("ma_20")
    near_ma20 = None
    ma_distance_pct = None
    if isinstance(close, (int, float)) and isinstance(ma20, (int, float)) and ma20:
        ma_distance_pct = (close - ma20) / ma20
        near_ma20 = abs(ma_distance_pct) <= NEAR

    state_key = current["state_key"] if current else None
    match_count = sum(1 for window in usable if window["state_key"] == state_key) if state_key else 0
    frequency = (match_count / len(usable)) if usable and state_key else None
    freq_status = _sample_status(len(usable)) if current else "INSUFFICIENT_HISTORY"

    trailing = _trailing_range(bars)
    fifty_two = _fifty_two_week_range(bars)
    structural = _structural_state(
        trend_state=current["trend_state"] if current else None,
        momentum_sign=current["momentum_sign"] if current else None,
        momentum_age=momentum_age,
        ma_age=ma_age,
        near_ma20=near_ma20,
        vol_regime=vol_regime,
    )

    if current and trailing.get("status") == "AVAILABLE":
        context_status = "AVAILABLE" if vol_status == "AVAILABLE" and rvol_status == "AVAILABLE" else "PARTIAL"
    elif bars:
        context_status = "PARTIAL" if trailing.get("status") == "AVAILABLE" else "INSUFFICIENT_HISTORY"
    else:
        context_status = "MISSING"

    source_label = next(
        (bar.get("price_basis") for bar in bars if bar.get("price_basis")),
        SOURCE_PRICE_BASIS_LABEL,
    )
    if source_label and source_label != SOURCE_PRICE_BASIS_LABEL:
        # Preserve the retained observation label; still never RAW_AS_TRADED / PIT.
        pass

    return {
        "context_status": context_status,
        "as_of_session": as_of,
        "is_current_session": as_of == target_session,
        "history": {
            "observation_count": len(bars),
            "complete_20_session_feature_windows": len(usable),
            "first_session": bars[0]["session"],
            "last_session": as_of,
            "price_basis": PRICE_BASIS,
            "price_basis_source_label": source_label or SOURCE_PRICE_BASIS_LABEL,
            "historical_pit_eligible": False,
            "raw_as_traded": "NOT_PROMOTED",
            "window_rule": "ACTUAL_RETAINED_TRADING_OBSERVATIONS_NO_CALENDAR_IMPUTATION",
            **provenance,
        },
        "trailing_range": trailing,
        "fifty_two_week_range": fifty_two,
        "drawdown": {
            "status": "AVAILABLE" if current_dd["drawdown"] is not None else "MISSING",
            "current_drawdown": current_dd["drawdown"],
            "peak_close": current_dd["peak_close"],
            "peak_session": current_dd["peak_session"],
            "magnitude_percentile": dd_percentile if dd_status != "INSUFFICIENT_HISTORY" else None,
            "percentile_status": dd_status,
            "sample_count": len(magnitudes),
            "method": "close_over_running_peak_of_retained_observed_closes",
        },
        "volatility_regime": {
            "status": vol_status if current else "INSUFFICIENT_HISTORY",
            "current_volatility_20d": current_vol,
            "percentile": vol_percentile if vol_status != "INSUFFICIENT_HISTORY" else None,
            "regime": vol_regime,
            "sample_count": len(vol_history),
            "method": "mva_daily_research_bundle.market_features.volatility_20d on rolling 20-observation windows",
            "cross_section": "BLOCKED_WITHIN_TICKER_ONLY",
        },
        "momentum": {
            "status": "AVAILABLE" if current else "INSUFFICIENT_HISTORY",
            "momentum_20d": values.get("momentum_20d"),
            "sign": current["momentum_sign"] if current else None,
            "persistence_windows": momentum_age,
            "method": "mva_daily_research_bundle.market_features.momentum_20d on rolling 20-observation windows",
        },
        "ma_alignment": {
            "status": "AVAILABLE" if current else "INSUFFICIENT_HISTORY",
            "trend_state": current["trend_state"] if current else None,
            "persistence_windows": ma_age,
            "near_ma20": near_ma20,
            "ma20_distance_pct": ma_distance_pct,
            "ma_20": ma20,
            "close": close,
            "method": "close vs market_features.ma_20 on explicit last-20 observed sessions",
        },
        "relative_volume": {
            "status": rvol_status if current else "INSUFFICIENT_HISTORY",
            "current_relative_volume_provider_scoped": current_rvol,
            "percentile": rvol_percentile if rvol_status != "INSUFFICIENT_HISTORY" else None,
            "regime": _tertile_regime(rvol_percentile) if rvol_status != "INSUFFICIENT_HISTORY" else None,
            "sample_count": len(rvol_history),
            "semantic": "PROVIDER_SCOPED_NOT_LIQUIDITY_AUTHORITY",
            "method": "mva_daily_research_bundle.market_features.relative_volume_provider_scoped",
            "warning": "RELATIVE_VOLUME_IS_PROVIDER_SCOPED_NOT_LIQUIDITY_AUTHORITY",
        },
        "technical_state_frequency": {
            "status": freq_status if current else "INSUFFICIENT_HISTORY",
            "current_state": state_key,
            "historical_match_count": match_count if state_key else 0,
            "window_count": len(usable),
            "frequency_in_retained_history": frequency if freq_status != "INSUFFICIENT_HISTORY" else None,
            "rarity_bucket": _rarity_bucket(frequency) if freq_status != "INSUFFICIENT_HISTORY" else None,
            "method": "within_ticker_count_of_same_trend_state_and_momentum_sign",
            "probability_claim": "NONE",
        },
        "structural_state": structural,
        "cross_sectional_historical_comparison": _blocked_field(
            "BLOCKED", "HISTORICAL_PIT_MEMBERSHIP_UNAVAILABLE",
        ),
        "current_feature_window": {
            "status": current["status"] if current else "MISSING",
            "price_basis": PRICE_BASIS,
            "historical_pit_eligible": False,
            "method": "retained_20_completed_session_window; no_imputation; explicit_last_20_observed_sessions",
            "values": values,
            "warnings": [
                "ADJUSTED_RETROSPECTIVE_NOT_RAW_AS_TRADED",
                "RELATIVE_VOLUME_IS_PROVIDER_SCOPED_NOT_LIQUIDITY_AUTHORITY",
            ],
        } if current else _blocked_field("INSUFFICIENT_HISTORY", "COMPLETE_20_SESSION_WINDOW_REQUIRED"),
    }


def _strategy_examples(strategy_artifact: Mapping[str, Any] | None, records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    lanes = ("TREND_MOMENTUM", "BREAKOUT", "EARLY_REVERSAL", "BASE_ACCUMULATION")
    empty = {
        "status": "NOT_ATTACHED",
        "note": "Optional retained current-session strategy artifact was not supplied; historical context does not require it.",
        "lanes": {lane: [] for lane in lanes},
    }
    if strategy_artifact is None:
        return empty
    strategy_records = strategy_artifact.get("records")
    if not isinstance(strategy_records, Mapping):
        return empty
    examples = {lane: [] for lane in lanes}
    for ticker in sorted(strategy_records):
        item = strategy_records[ticker]
        if not isinstance(item, Mapping):
            continue
        eligible = item.get("eligible_strategy_ids") or []
        hist = records.get(ticker) or {}
        for lane in lanes:
            if lane in eligible and len(examples[lane]) < 5:
                examples[lane].append({
                    "ticker": ticker,
                    "context_status": hist.get("context_status"),
                    "structural_state": (hist.get("structural_state") or {}).get("value"),
                    "as_of_session": hist.get("as_of_session"),
                    "is_current_session": hist.get("is_current_session"),
                    "observation_count": (hist.get("history") or {}).get("observation_count"),
                })
    return {
        "status": "REFERENCE_ONLY",
        "strategy_artifact_identity": strategy_artifact.get("artifact_identity"),
        "strategy_session": strategy_artifact.get("session"),
        "note": (
            "Current-session strategy eligibility from the retained strategy artifact. "
            "Examples do not confer historical performance, do not change strategy eligibility, "
            "and are not an input to historical context."
        ),
        "lanes": examples,
    }


def build_artifact(
    *,
    universe_resolution_artifact: Mapping[str, Any],
    p3f9b_snapshot: Mapping[str, Any],
    technical_history_recovery_artifact: Mapping[str, Any] | None = None,
    strategy_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _verify_hashed_identity(universe_resolution_artifact, label="UNIVERSE_RESOLUTION_ARTIFACT")
    _verify_p3f9b_identity(p3f9b_snapshot)

    ur_records = universe_resolution_artifact.get("records")
    pf_records = p3f9b_snapshot.get("records")
    if not isinstance(ur_records, Mapping) or not isinstance(pf_records, Mapping):
        raise MarketWideHistoricalResearchContextError("INPUT_RECORDS_INVALID")
    if set(ur_records) != set(pf_records):
        raise MarketWideHistoricalResearchContextError("CANDIDATE_DENOMINATOR_MISMATCH")

    target_session = p3f9b_snapshot.get("resolved_completed_session")
    if not target_session or target_session != universe_resolution_artifact.get("input_candidates", {}).get("resolved_completed_session"):
        raise MarketWideHistoricalResearchContextError("SESSION_MISMATCH_BETWEEN_UNIVERSE_RESOLUTION_AND_P3F9B_SNAPSHOT")

    recovery_overrides: Mapping[str, Any] = {}
    recovery_identity = None
    if technical_history_recovery_artifact is not None:
        recovered_identity = recovery_content_identity(technical_history_recovery_artifact)
        if technical_history_recovery_artifact.get("artifact_sha256") != recovered_identity["artifact_sha256"]:
            raise MarketWideHistoricalResearchContextError("TECHNICAL_HISTORY_RECOVERY_IDENTITY_MISMATCH")
        if technical_history_recovery_artifact.get("target_session") != target_session:
            raise MarketWideHistoricalResearchContextError("TECHNICAL_HISTORY_RECOVERY_SESSION_MISMATCH")
        if technical_history_recovery_artifact.get("source_lineage", {}).get("p3f9b_snapshot_identity") != p3f9b_snapshot.get("snapshot_identity"):
            raise MarketWideHistoricalResearchContextError("TECHNICAL_HISTORY_RECOVERY_SNAPSHOT_IDENTITY_MISMATCH")
        recovery_overrides = technical_history_recovery_artifact.get("recovered_history_overrides", {})
        if not isinstance(recovery_overrides, Mapping):
            raise MarketWideHistoricalResearchContextError("TECHNICAL_HISTORY_RECOVERY_OVERRIDES_INVALID")
        recovery_identity = technical_history_recovery_artifact.get("artifact_identity")

    if strategy_artifact is not None:
        from polymorphic_current_strategy_classification import content_identity as strategy_content_identity
        recomputed = strategy_content_identity(strategy_artifact)
        if strategy_artifact.get("artifact_sha256") != recomputed["artifact_sha256"]:
            raise MarketWideHistoricalResearchContextError("STRATEGY_ARTIFACT_IDENTITY_MISMATCH")
        if strategy_artifact.get("session") != target_session:
            raise MarketWideHistoricalResearchContextError("STRATEGY_ARTIFACT_SESSION_MISMATCH")

    current_active_equity_denominator = universe_resolution_artifact["current_active_equity_denominator"]["count"]
    observed_session_cohort_count = universe_resolution_artifact["observed_session_cohort"]["count"]

    records: dict[str, dict[str, Any]] = {}
    for ticker in sorted(ur_records):
        ur = ur_records[ticker]
        activity_state = ur["activity_and_session_state"]
        in_scope = activity_state in IN_SCOPE_ACTIVITY_STATES
        if not in_scope:
            records[ticker] = {
                "ticker": ticker,
                "activity_and_session_state": activity_state,
                "membership_state": ur.get("membership_state"),
                "in_current_descriptive_scope": False,
                "context_status": "NOT_APPLICABLE",
                "as_of_session": None,
                "is_current_session": False,
                "reason": "OUT_OF_CURRENT_DESCRIPTIVE_SCOPE",
                "cross_sectional_historical_comparison": _blocked_field(
                    "BLOCKED", "HISTORICAL_PIT_MEMBERSHIP_UNAVAILABLE",
                ),
            }
            continue

        override = recovery_overrides.get(ticker)
        if isinstance(override, Mapping) and override.get("state") == "RECOVERED_COMPLETE_TECHNICAL_HISTORY":
            observations = override.get("observations", [])
            provenance = {
                "source": "RETAINED_DNSE_EXTENDED_HISTORY_RECOVERY",
                "provider": "DNSE",
                "recovery_artifact_identity": recovery_identity,
                "recovery_payload_sha256": override.get("payload_sha256"),
            }
        else:
            observations = (pf_records[ticker] or {}).get("observations", [])
            provenance = {
                "source": "RETAINED_P3F9B_EXACT_SESSION_SNAPSHOT",
                "provider": "DNSE",
                "snapshot_disposition": (pf_records[ticker] or {}).get("disposition"),
            }
        context = evaluate_historical_context(
            observations if isinstance(observations, list) else [],
            target_session=target_session,
            provenance=provenance,
        )
        records[ticker] = {
            "ticker": ticker,
            "activity_and_session_state": activity_state,
            "membership_state": ur.get("membership_state"),
            "in_current_descriptive_scope": True,
            **context,
        }

    in_scope = [record for record in records.values() if record["in_current_descriptive_scope"]]
    status_counts = Counter(record["context_status"] for record in records.values())
    structural_counts = Counter(
        (record.get("structural_state") or {}).get("value") or "UNAVAILABLE"
        for record in in_scope
        if (record.get("structural_state") or {}).get("status") == "AVAILABLE"
    )
    observation_buckets = Counter()
    for record in in_scope:
        count = (record.get("history") or {}).get("observation_count") or 0
        if count <= 0:
            observation_buckets["0"] += 1
        elif count < 20:
            observation_buckets["1-19"] += 1
        elif count < 60:
            observation_buckets["20-59"] += 1
        elif count < 120:
            observation_buckets["60-119"] += 1
        elif count < 252:
            observation_buckets["120-251"] += 1
        else:
            observation_buckets["252+"] += 1
    fifty_two_available = sum(
        1 for record in in_scope
        if (record.get("fifty_two_week_range") or {}).get("status") == "AVAILABLE"
    )
    current_session_available = sum(1 for record in in_scope if record.get("is_current_session") is True and record.get("context_status") in {"AVAILABLE", "PARTIAL"})

    validation = {
        "coverage": {
            "input_candidates": len(records),
            "current_active_equity_denominator": current_active_equity_denominator,
            "observed_session_cohort": observed_session_cohort_count,
            "in_scope_count": len(in_scope),
            "current_session_context_count": current_session_available,
            "fifty_two_week_available_count": fifty_two_available,
            "context_status_counts": dict(sorted(status_counts.items())),
            "structural_state_counts": dict(sorted(structural_counts.items())),
            "observation_count_buckets": dict(sorted(observation_buckets.items())),
            "universe_status_counts": dict(sorted(Counter(record["activity_and_session_state"] for record in records.values()).items())),
        },
        "available_outputs": [
            "trailing_range", "fifty_two_week_range", "drawdown", "volatility_regime",
            "momentum", "ma_alignment", "relative_volume", "technical_state_frequency",
            "structural_state",
        ],
        "blocked_outputs": dict(sorted(BLOCKED_OUTPUTS.items())),
        "lineage": {
            "universe_resolution_artifact_identity": universe_resolution_artifact.get("artifact_identity"),
            "p3f9b_snapshot_identity": p3f9b_snapshot.get("snapshot_identity"),
            "technical_history_recovery_artifact_identity": recovery_identity,
            "strategy_artifact_identity": None if strategy_artifact is None else strategy_artifact.get("artifact_identity"),
            "session": target_session,
        },
        "session": target_session,
    }

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "session": target_session,
        "research_mode": "RETROSPECTIVE_DESCRIPTIVE_WITHIN_TICKER",
        "input_lineage": validation["lineage"],
        "coverage": validation["coverage"],
        "pilot_diagnostics": {
            "current_strategy_lane_examples": _strategy_examples(strategy_artifact, records),
        },
        "validation": validation,
        "promotion_recommendation": {
            "state": "OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE",
            "reason": (
                "Retrospective descriptive historical context only; adjusted provider history "
                "is not RAW_AS_TRADED or PIT, and no historical performance, ranking, or sizing authority is created."
            ),
        },
        "authority_boundary": {
            "research_mode": "RETROSPECTIVE_DESCRIPTIVE_WITHIN_TICKER",
            "price_basis": PRICE_BASIS,
            "RAW_AS_TRADED": "NOT_PROMOTED",
            "PIT": "BLOCKED",
            "historical_performance_backtest_alpha": "NOT_EMITTED",
            "ranking_recommendation_valuation": "NOT_EMITTED",
            "portfolio_sizing_execution": "NOT_EMITTED",
            "research_priority_entry_action_strategy_eligibility": "NOT_MODIFIED",
            "cross_sectional_historical_comparison": "BLOCKED_HISTORICAL_PIT_MEMBERSHIP_UNAVAILABLE",
            "calendar_imputation": "NOT_USED",
            "governed_2026_08_24_session_and_2026_08_21_freeze": "NOT_MUTATED",
        },
        "blocked_outputs": dict(sorted(BLOCKED_OUTPUTS.items())),
        "records": records,
    }
    return {**artifact, **content_identity(artifact)}
