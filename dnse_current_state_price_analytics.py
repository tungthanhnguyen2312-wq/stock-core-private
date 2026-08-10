"""DNSE current-state, price-only analytics: adjusted returns, volatility, drawdown.

SCOPE -- CURRENT-STATE ONLY, NEVER POINT-IN-TIME
    Every result this module produces carries two fields that must never be
    dropped or reinterpreted: ``analysis_time_semantics`` (always
    ``ANALYSIS_TIME_SEMANTICS``) and ``pit_backtest_eligible`` (always
    ``False``). ``dnse_ohlc_price_basis_capability.py`` proved DNSE's
    currently-queryable OHLC history is retrospectively rewritten -- safe for
    a computation run today over today's query, unsafe as a stand-in for what
    a point-in-time backtest would have seen on a past date. This module
    never reuses these series inside PIT/backtest code (``vnm_shadow_backtest.py``,
    ``point_in_time_adjusted_prices.py``, ``point_in_time_market_risk.py``,
    ``point_in_time_benchmark.py``) and never exposes a function whose name
    could be mistaken for PIT-safe.

TICKER ELIGIBILITY IS EVIDENCE-BOUNDED, NOT SOURCE-WIDE
    Every entry point here funnels through
    ``dnse_ohlc_price_basis_capability.current_state_eligibility()`` first.
    That gate is ticker-scoped (currently HPG, VCB only) -- a ticker outside
    that set gets an explicit ``NOT_QUALIFIED_FOR_DNSE_PRICE_ANALYTICS``
    result before its OHLC payload (if any) is even parsed. No ticker
    exception is hard-coded here; the scope lives entirely in the capability
    module, exactly once.

NO VOLUME
    DNSE's normal market volume basis is separately, independently
    unqualified. This module never reads a "v"/volume field from a raw OHLC
    response and never produces a volume-dependent output.

REUSE, NOT REINVENTION
    - Adjusted simple return: ``r_t = close_t / close_(t-1) - 1`` (the same
      formula already used inline in ``risk_liquidity.py::evaluate_market_risk()``).
    - Realized/downside volatility: population standard deviation (ddof=0) of
      simple returns, unannualized (``unit: "per_observation_return"``) --
      the same formula and the same unannualized convention already
      established in ``risk_liquidity.py``. No new annualization convention
      is invented here.
    - Maximum drawdown: the same running peak/trough formula already
      established in ``risk_liquidity.py`` (``mdd = min(mdd, c/peak - 1)``),
      extended to retain peak/trough session lineage.
    - SMA/RSI: ``vn_indicators.sma()``/``vn_indicators.rsi()`` called as-is
      against a minimal price-only DataFrame adapter (verified by reading
      their source: both call only ``_series(df, "close")``, never
      ``_ohlcv()``, so no volume column is required or constructed).
    These are not imported directly from ``risk_liquidity.py`` because that
    function is entangled with a VNM-specific, VCI-sourced PIT/adjusted-price
    gate this milestone must not touch or bypass -- this module is the
    "smallest current-state adapter" reusing the same math independently.

TRADING-SESSION CONTIGUITY, WITHOUT A HISTORICAL DNSE CALENDAR
    Same technique already established by
    ``dnse_foreign_flow_store._retained_trading_dates()``: a date has an
    ``ohlcv`` row for this ticker in ``vn_stock.db`` is treated as the
    trading-session-existence fact used only to detect gaps -- never to read
    a price or volume value from that table. Read-only (``mode=ro`` +
    ``PRAGMA query_only``); this module never writes to ``vn_stock.db``.

NO NETWORK I/O, NO SECRETS
    This module never calls DNSE and never reads secrets.env. Fetching a raw
    OHLC payload is the caller's job (see
    ``tools/dnse_market_data_probe.py --probe current-state`` and
    ``tools/dnse_current_state_analytics_shadow.py``); everything here is a
    pure function of its arguments.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

import dnse_ohlc_price_basis_capability as price_basis
import vn_indicators
from vn_time import VN_TZ

VERSION = "1.0.0"
PROVIDER = "DNSE"

# Step 3's mandatory semantics, carried verbatim on every result this module produces.
ANALYSIS_TIME_SEMANTICS = "current_state_using_retrospectively_adjusted_history"
PIT_BACKTEST_ELIGIBLE = False

STATUS_QUALIFIED = "QUALIFIED_FOR_DNSE_CURRENT_STATE_PRICE_ANALYTICS"
STATUS_QUALIFIED_INCOMPLETE_WINDOW = "QUALIFIED_TICKER_INCOMPLETE_WINDOW"
STATUS_NOT_QUALIFIED = "NOT_QUALIFIED_FOR_DNSE_PRICE_ANALYTICS"

_REQUIRED_OHLC_FIELDS: tuple[str, ...] = ("o", "h", "l", "c", "t")


class DnseCurrentStatePriceAnalyticsError(ValueError):
    """Fail-closed rejection for a structurally malformed OHLC payload."""


# --------------------------------------------------------------------- normalization

def _epoch_to_session_date(epoch_seconds: Any) -> str:
    return datetime.fromtimestamp(int(epoch_seconds), tz=VN_TZ).date().isoformat()


def _is_usable_price(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def normalize_bars(ticker: str, raw_ohlc: Mapping[str, Any]) -> dict[str, Any]:
    """DNSE's own parallel-array ``{"o","h","l","c","t"[,"v"]}`` OHLC response
    -> a ``session_date``-sorted list of per-session observations.

    "v" (volume) is never read, per this module's no-volume scope. A session
    with a missing/non-positive/NaN O, H, L or C is dropped, not fabricated
    or interpolated -- recorded in ``dropped_sessions`` so the drop is
    visible, never silent. Raises on a duplicate ``session_date`` (two rows
    claiming the same calendar day is an ambiguous, unresolvable input, not a
    coverage gap) and on a parallel-array length mismatch.
    """
    for key in _REQUIRED_OHLC_FIELDS:
        if key not in raw_ohlc:
            raise DnseCurrentStatePriceAnalyticsError(f"ohlc_response_missing_field:{key}")
        if not isinstance(raw_ohlc[key], list):
            # A real trap hit during this milestone's own live shadow run:
            # dnse_market_data._bound_large_lists() replaces any list longer
            # than 20 items with a {"list_truncated": True, ...} summary dict
            # when a probe evidence file is written -- a >20-session request
            # silently loses its full array in the *retained* evidence, even
            # though the live response itself was complete. Caught here as an
            # explicit, diagnosable failure instead of a bare KeyError deep in
            # the loop below.
            raise DnseCurrentStatePriceAnalyticsError(
                f"ohlc_response_field_not_a_list_possibly_truncated_by_redaction_layer:{key}"
            )
    lengths = {key: len(raw_ohlc[key]) for key in _REQUIRED_OHLC_FIELDS}
    if len(set(lengths.values())) != 1:
        raise DnseCurrentStatePriceAnalyticsError(f"ohlc_response_field_length_mismatch:{lengths}")

    normalized_ticker = str(ticker).strip().upper()
    seen_dates: set[str] = set()
    observations: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for i in range(lengths["t"]):
        session_date = _epoch_to_session_date(raw_ohlc["t"][i])
        if session_date in seen_dates:
            raise DnseCurrentStatePriceAnalyticsError(
                f"duplicate_session_date:{normalized_ticker}:{session_date}"
            )
        seen_dates.add(session_date)
        values = {"open": raw_ohlc["o"][i], "high": raw_ohlc["h"][i],
                  "low": raw_ohlc["l"][i], "close": raw_ohlc["c"][i]}
        if not all(_is_usable_price(v) for v in values.values()):
            dropped.append({"session_date": session_date, "reason": "missing_or_non_positive_price"})
            continue
        observations.append({
            "ticker": normalized_ticker,
            "session_date": session_date,
            "open": float(values["open"]), "high": float(values["high"]),
            "low": float(values["low"]), "close": float(values["close"]),
        })
    observations.sort(key=lambda row: row["session_date"])
    return {"observations": observations, "dropped_sessions": dropped}


def _retained_trading_dates(runtime_root: Path | str, ticker: str) -> set[str]:
    """Calendar dates ``vn_stock.db``'s own OHLCV table has a row for this
    ticker -- used only to detect session gaps in the DNSE-sourced sequence,
    never to read a price/volume value. Read-only; never writes."""
    db_path = Path(runtime_root) / "vn_stock.db"
    if not db_path.exists():
        return set()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = 1")
        rows = conn.execute(
            "SELECT DISTINCT date FROM ohlcv WHERE ticker = ?", (ticker,)
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def validate_session_sequence(
    observations: Sequence[Mapping[str, Any]],
    *,
    reference_trading_dates: set[str] | None,
) -> dict[str, Any]:
    """All-or-nothing window contiguity check (Step 6), mirroring the
    all-or-nothing convention ``dnse_foreign_flow_store._window_summary``
    already established for DNSE data: complete only when every session in
    ``[first, last]`` is present with no gap, per the same
    vn_stock.db-trading-date reference technique. Never fills a missing
    session and never treats a calendar date as a trading session.

    Fails closed when no reference set is available -- stricter than the
    foreign-flow store's "unverifiable" allowance, because this analytics
    contract's own instructions require a positive trading-calendar
    reference before a return series may be computed at all.
    """
    base = {"status": "incomplete", "session_count": len(observations), "reason": None}
    if len(observations) < 2:
        return {**base, "reason": f"only {len(observations)} session(s) retained, need at least 2"}
    dates = [o["session_date"] for o in observations]
    if dates != sorted(dates):
        return {**base, "reason": "sessions_not_in_ascending_order"}
    if len(set(dates)) != len(dates):
        return {**base, "reason": "duplicate_session_date_survived_normalization"}
    if not reference_trading_dates:
        return {**base, "reason": "no_vn_stock_db_trading_date_reference_available_for_this_ticker"}
    expected = sorted(d for d in reference_trading_dates if dates[0] <= d <= dates[-1])
    if expected != dates:
        missing = sorted(set(expected) - set(dates))
        return {**base, "reason": f"gap detected -- missing session(s): {missing}"}
    return {"status": "complete", "session_count": len(observations), "reason": None}


# --------------------------------------------------------------------- Step 5 series contract

def build_current_state_series(
    ticker: str,
    raw_ohlc: Mapping[str, Any] | None,
    *,
    runtime_root: Path | str | None = None,
    fetch_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The canonical DNSE current-state series contract (Step 5).

    Always returns a dict; never raises for an ineligible ticker -- that is
    an expected, common outcome carried in ``status``/``coverage``, not an
    error. An ineligible ticker's eligibility is decided before ``raw_ohlc``
    is even inspected (``raw_ohlc`` may be ``None`` in that case), so "DNSE
    OHLC exists for this ticker" can never leak into a qualification
    decision. Raises only for a structurally malformed ``raw_ohlc`` on an
    already-eligible ticker (see ``normalize_bars``).
    """
    normalized_ticker = str(ticker).strip().upper()
    eligibility = price_basis.current_state_eligibility(normalized_ticker)
    record: dict[str, Any] = {
        "schema_version": VERSION,
        "ticker": normalized_ticker,
        "source": PROVIDER,
        "price_basis": price_basis.ACTIVE_PRICE_BASIS_VERDICT,
        "price_basis_contract_version": price_basis.SOURCE_CONTRACT_VERSION,
        "qualification_scope": eligibility["qualification_scope"],
        "qualified_action_types": list(price_basis.QUALIFIED_ACTION_TYPES),
        "analysis_time_semantics": ANALYSIS_TIME_SEMANTICS,
        "pit_backtest_eligible": PIT_BACKTEST_ELIGIBLE,
        "eligibility": eligibility,
        "as_of_session": None,
        "observations": [],
        "coverage": {"status": "not_qualified", "session_count": 0,
                     "reason": eligibility.get("reason")},
        "warnings": list(price_basis.WARNINGS),
        "provenance": {"fetch": dict(fetch_provenance or {}), "dropped_sessions": []},
    }
    if not eligibility["eligible_for_current_state_price_analytics"]:
        record["status"] = STATUS_NOT_QUALIFIED
        return record

    normalized = normalize_bars(normalized_ticker, raw_ohlc or {})
    observations = normalized["observations"]
    reference_dates = (
        _retained_trading_dates(runtime_root, normalized_ticker)
        if runtime_root is not None else set()
    )
    coverage = validate_session_sequence(observations, reference_trading_dates=reference_dates)

    record["observations"] = observations
    record["as_of_session"] = observations[-1]["session_date"] if observations else None
    record["coverage"] = coverage
    record["provenance"]["dropped_sessions"] = normalized["dropped_sessions"]
    record["status"] = STATUS_QUALIFIED if coverage["status"] == "complete" else STATUS_QUALIFIED_INCOMPLETE_WINDOW
    if normalized["dropped_sessions"]:
        record["warnings"] = record["warnings"] + [
            "one_or_more_sessions_dropped_for_missing_or_non_positive_price_never_interpolated"
        ]
    return record


# --------------------------------------------------------------------- Step 6 returns contract

def compute_returns(series: Mapping[str, Any]) -> dict[str, Any]:
    """Adjusted simple close-to-close returns: ``r_t = close_t/close_(t-1) - 1``.

    Computed only when ``series["coverage"]["status"] == "complete"`` -- one
    ticker, one source, one price basis throughout by construction (a series
    is built for exactly one ticker). Never fills or interpolates a missing
    price; an incomplete series yields an explicit incomplete result with a
    reason, never a partial best-effort list.
    """
    coverage = series.get("coverage") or {}
    observations = series.get("observations") or []
    common = {
        "analysis_time_semantics": series.get("analysis_time_semantics"),
        "pit_backtest_eligible": series.get("pit_backtest_eligible"),
    }
    if coverage.get("status") != "complete":
        return {
            "status": "incomplete", "returns": [], "cumulative_return": None,
            "return_count": 0,
            "reason": coverage.get("reason") or "series_coverage_not_complete",
            **common,
        }
    returns = [
        {
            "session_date": curr["session_date"],
            "prior_session_date": prev["session_date"],
            "close": curr["close"],
            "prior_close": prev["close"],
            "simple_return": curr["close"] / prev["close"] - 1.0,
        }
        for prev, curr in zip(observations, observations[1:])
    ]
    first_close, last_close = observations[0]["close"], observations[-1]["close"]
    return {
        "status": "complete",
        "returns": returns,
        "cumulative_return": last_close / first_close - 1.0,
        "session_count": len(observations),
        "return_count": len(returns),
        "reason": None,
        **common,
    }


# --------------------------------------------------------------------- Step 7 volatility / drawdown

def compute_volatility(returns_result: Mapping[str, Any]) -> dict[str, Any]:
    """Realized (and downside) volatility: population standard deviation
    (ddof=0) of simple returns -- the same formula already established in
    ``risk_liquidity.py::evaluate_market_risk()``, reused here over a
    current-state DNSE series. Deliberately left unannualized
    (``unit: "per_observation_return"``, matching that same established
    convention) -- no new annualization convention is invented."""
    if returns_result.get("status") != "complete":
        return {"status": "unavailable", "value": None, "downside_value": None, "unit": None,
                "reason": returns_result.get("reason") or "returns_not_available"}
    values = [r["simple_return"] for r in returns_result["returns"]]
    if len(values) < 2:
        return {"status": "unavailable", "value": None, "downside_value": None, "unit": None,
                "reason": f"only {len(values)} return(s), need at least 2"}
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    downside_variance = sum(min(0.0, x) ** 2 for x in values) / len(values)
    return {
        "status": "available",
        "value": variance ** 0.5,
        "downside_value": downside_variance ** 0.5,
        "unit": "per_observation_return",
        "annualized": None,
        "annualization_note": "not_computed_no_authoritative_session_frequency_convention_established_here",
        "method": "population_stdev_of_simple_returns",
        "observation_count": len(values),
        "reason": None,
    }


def compute_drawdown(series: Mapping[str, Any]) -> dict[str, Any]:
    """Maximum drawdown over the qualified current-state close series: the
    same running peak/trough formula already established in
    ``risk_liquidity.py`` (``mdd = min(mdd, c/peak - 1)``), extended to
    retain the peak/trough session lineage rather than the bare fraction."""
    coverage = series.get("coverage") or {}
    observations = series.get("observations") or []
    if coverage.get("status") != "complete":
        return {"status": "unavailable", "reason": coverage.get("reason") or "series_coverage_not_complete"}
    if len(observations) < 2:
        return {"status": "unavailable", "reason": f"only {len(observations)} session(s), need at least 2"}

    peak_date, peak_value = observations[0]["session_date"], observations[0]["close"]
    best = {"drawdown": 0.0, "peak_session_date": peak_date, "peak_value": peak_value,
            "trough_session_date": peak_date, "trough_value": peak_value}
    for obs in observations:
        close = obs["close"]
        if close > peak_value:
            peak_value, peak_date = close, obs["session_date"]
        drawdown = close / peak_value - 1.0
        if drawdown < best["drawdown"]:
            best = {"drawdown": drawdown, "peak_session_date": peak_date, "peak_value": peak_value,
                    "trough_session_date": obs["session_date"], "trough_value": close}
    return {
        "status": "available",
        "maximum_drawdown": best["drawdown"],
        "unit": "fraction",
        "peak_session_date": best["peak_session_date"],
        "peak_value": best["peak_value"],
        "trough_session_date": best["trough_session_date"],
        "trough_value": best["trough_value"],
        "window_session_count": len(observations),
        "window_start_session_date": observations[0]["session_date"],
        "window_end_session_date": observations[-1]["session_date"],
        "reason": None,
    }


# --------------------------------------------------------------------- Step 8 technical indicators

def compute_technical_indicators(
    series: Mapping[str, Any], *, sma_window: int = 20, rsi_window: int = 14,
) -> dict[str, Any]:
    """SMA/RSI only, reusing ``vn_indicators.sma()``/``vn_indicators.rsi()``
    exactly as-is against a minimal price-only DataFrame adapter -- no
    parallel indicator stack. Both functions were verified (by reading their
    source) to need only a "close" column, never volume, so this stays
    within the no-volume-dependency constraint without a placeholder column."""
    coverage = series.get("coverage") or {}
    observations = series.get("observations") or []
    if coverage.get("status") != "complete":
        return {"status": "unavailable", "reason": coverage.get("reason") or "series_coverage_not_complete"}

    closes = [obs["close"] for obs in observations]
    dates = [obs["session_date"] for obs in observations]
    frame = pd.DataFrame({"close": closes}, index=pd.Index(dates, name="session_date"))

    sma_values = vn_indicators.sma(frame, window=sma_window)
    rsi_values = vn_indicators.rsi(frame, window=rsi_window)

    def _latest_available(values: pd.Series, window: int) -> dict[str, Any]:
        valid = values.dropna()
        if valid.empty:
            return {"status": "unavailable", "value": None, "as_of_session": None,
                    "reason": f"fewer than {window} qualified session(s) in this window"}
        return {"status": "available", "value": float(valid.iloc[-1]),
                "as_of_session": str(valid.index[-1]), "reason": None}

    return {
        "status": "available",
        f"sma_{sma_window}": _latest_available(sma_values, sma_window),
        f"rsi_{rsi_window}": _latest_available(rsi_values, rsi_window),
        "volume_dependency": "none",
        "reason": None,
    }


# --------------------------------------------------------------------- Step 13 shadow orchestration

def build_shadow_report(
    ticker: str,
    raw_ohlc: Mapping[str, Any] | None,
    *,
    runtime_root: Path | str | None,
    fetch_provenance: Mapping[str, Any] | None = None,
    include_technical_indicators: bool = True,
) -> dict[str, Any]:
    """Deterministic, pure orchestration: series -> returns -> volatility ->
    drawdown -> (optional) technical indicators, in one call. No network I/O,
    no wall-clock read, no random/set-iteration-order-dependent output --
    calling this twice with identical inputs must produce byte-identical
    serialized JSON."""
    series = build_current_state_series(
        ticker, raw_ohlc, runtime_root=runtime_root, fetch_provenance=fetch_provenance,
    )
    returns = compute_returns(series)
    report: dict[str, Any] = {
        "schema_version": VERSION,
        "ticker": series["ticker"],
        "source": series["source"],
        "status": series["status"],
        "eligibility": series["eligibility"],
        "price_basis": series["price_basis"],
        "price_basis_contract_version": series["price_basis_contract_version"],
        "qualification_scope": series["qualification_scope"],
        "as_of_session": series["as_of_session"],
        "coverage": series["coverage"],
        "analysis_time_semantics": series["analysis_time_semantics"],
        "pit_backtest_eligible": series["pit_backtest_eligible"],
        "observations": series["observations"],
        "returns": returns,
        "volatility": compute_volatility(returns),
        "drawdown": compute_drawdown(series),
        "warnings": series["warnings"],
        "provenance": series["provenance"],
    }
    if include_technical_indicators:
        report["technical_indicators"] = compute_technical_indicators(series)
    return report


def serialize(report: Mapping[str, Any]) -> str:
    """Deterministic JSON serialization -- same input always produces the
    same bytes, so a caller can hash/compare/replay a retained report."""
    return json.dumps(report, sort_keys=True, default=str)
