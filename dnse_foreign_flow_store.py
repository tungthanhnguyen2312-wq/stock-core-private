"""Retained store for qualified DNSE foreign-investor VALUE observations, and the
multi-session series/summary contract built on top of it.

LAYOUT (beneath the runtime root -- generated runtime data, never the source repo)

    data/dnse-foreign-flow/observations/<TICKER>.json
        one deterministic file per ticker: schema_version, provider, source_contract_version,
        and a session_date-sorted list of normalized observations.

SCOPE -- VALUE ONLY, DELIBERATELY
    This module reads dnse_foreign_flow_capability.normalize_record() output (or
    equivalent already-normalized records) and carries forward ONLY the qualified
    foreign_buy_value / foreign_sell_value / foreign_net_value fields (VND). Foreign
    *volume* and foreign *room* -- both still `AVAILABLE_BUT_SEMANTICS_UNQUALIFIED` per
    dnse_foreign_flow_capability.py -- are never read into the series/summary layer at
    all, not filtered out after the fact. There is no code path here that could
    accidentally promote them.

TRADING-SESSION COMPLETENESS, WITHOUT A HISTORICAL DNSE CALENDAR
    DNSE's own working-dates endpoint is forward-only (qualified 2026-08-10: 256 dates
    from today forward, zero historical coverage) -- it cannot answer "was 2026-08-05 a
    real trading day" for a past date. vn_stock.db's own retained OHLCV table can: by
    construction of the existing daily pipeline it has exactly one row per ticker per
    real trading session. This module treats "a date has an ohlcv row for this ticker"
    as the trading-session-existence fact used only to detect gaps in a requested
    window -- it never reads an OHLCV price or volume value, so this stays fully
    independent of the still-unqualified DNSE/VCI price and volume basis questions.

NO NETWORK I/O, NO SECRETS
    This module never calls DNSE and never reads secrets.env. Ingestion (fetching real
    data via the secret-blind probe/launcher and normalizing it into this store) is a
    separate step -- see tools/ingest_dnse_foreign_flow.py.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

from atomic_io import atomic_write_file, validate_json_file
from dnse_foreign_flow_capability import PROVIDER, SOURCE_CONTRACT_VERSION

STORE_SCHEMA_VERSION = "1.0.0"
SERIES_SCHEMA_VERSION = "1.0.0"
STORE_RELATIVE = Path("data") / "dnse-foreign-flow"
OBSERVATIONS_RELATIVE = STORE_RELATIVE / "observations"

STATUS_MISSING = "missing"
STATUS_AVAILABLE = "available"
VALUE_QUALIFICATION_STATUS = "QUALIFIED_VALUE_ONLY"
POINT_IN_TIME_STATUS = "qualified"

_STANDING_WARNINGS: tuple[str, ...] = (
    "foreign_volume_not_represented_here_unqualified_by_contract",
    "foreign_room_not_represented_here_unqualified_by_contract",
    "no_ownership_or_free_float_percentage_is_derived",
    "flow_relative_to_trading_value_is_not_computed_denominator_unqualified",
    "dnse_ohlc_price_basis_and_market_volume_basis_remain_unqualified_separately",
    "a_single_session_net_value_is_an_observation_not_a_trend_evaluate_the_full_observations_sequence",
    "no_score_ranking_or_bullish_bearish_label_is_computed_or_implied_by_this_contract",
)
_STANDING_LIMITATIONS: tuple[str, ...] = (
    "is_actionable is always false; this contract carries qualified foreign-value flow "
    "evidence only, never an investment signal or recommendation.",
    "Session coverage is bounded to whatever has been explicitly ingested; a missing "
    "session is reported as a gap, never filled or inferred.",
    "Any downstream reading of persistent accumulation/distribution must be stated as an "
    "inference over the observations sequence, not as a fact this contract asserts.",
)


class DnseForeignFlowStoreError(ValueError):
    """Fail-closed rejection in the foreign-flow store or series layer."""


def observations_root(runtime_root: Path | str) -> Path:
    return Path(runtime_root) / OBSERVATIONS_RELATIVE


def observation_path(runtime_root: Path | str, ticker: str) -> Path:
    return observations_root(runtime_root) / f"{ticker.upper()}.json"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_observations(
    runtime_root: Path | str, ticker: str, observations: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Deterministically persist a ticker's normalized foreign-flow observations,
    de-duplicated and sorted by session_date. Re-ingesting the same session
    overwrites (last write wins for that date) rather than duplicating it."""
    by_date: dict[str, dict[str, Any]] = {}
    for obs in observations:
        session_date = obs.get("session_date")
        if not isinstance(session_date, str) or not session_date:
            raise DnseForeignFlowStoreError("observation_missing_session_date")
        if obs.get("ticker") != ticker:
            raise DnseForeignFlowStoreError(
                f"observation_ticker_mismatch:{obs.get('ticker')!r}!={ticker!r}"
            )
        by_date[session_date] = dict(obs)
    ordered = [by_date[date] for date in sorted(by_date)]
    payload = {
        "schema_version": STORE_SCHEMA_VERSION,
        "ticker": ticker,
        "provider": PROVIDER,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "observations": ordered,
    }
    path = observation_path(runtime_root, ticker)
    atomic_write_file(path, _canonical_json(payload), validator=validate_json_file)
    return payload


def read_observations(runtime_root: Path | str, ticker: str) -> list[dict[str, Any]]:
    path = observation_path(runtime_root, ticker)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("observations") or [])


def _retained_trading_dates(runtime_root: Path | str, ticker: str) -> set[str]:
    """Calendar dates vn_stock.db's own OHLCV table has a row for this ticker --
    used only to detect session gaps, never to read a price or volume value."""
    db_path = Path(runtime_root) / "vn_stock.db"
    if not db_path.exists():
        return set()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = 1")
        rows = conn.execute("SELECT DISTINCT date FROM ohlcv WHERE ticker = ?", (ticker,)).fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def _value_observation(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Project one dnse_foreign_flow_capability.normalize_record() result down to the
    value-only canonical shape this milestone's contract specifies -- volume and room
    are read from `raw` never at all, not filtered after copying."""
    buy = raw.get("foreign_buy_value")
    sell = raw.get("foreign_sell_value")
    net = buy - sell if buy is not None and sell is not None else None
    return {
        "ticker": raw.get("ticker"),
        "session_date": raw.get("session_date"),
        "observed_at": raw.get("observed_at"),
        "foreign_buy_value_vnd": buy,
        "foreign_sell_value_vnd": sell,
        "foreign_net_value_vnd": net,
        "source": PROVIDER,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "point_in_time_status": POINT_IN_TIME_STATUS,
        "provenance": dict(raw.get("provenance") or {}),
        "qualification_status": VALUE_QUALIFICATION_STATUS,
    }


def _has_gap(prev_date: str, date: str, trading_dates: set[str]) -> bool:
    return any(prev_date < d < date for d in trading_dates)


def _streaks_and_counts(observations: Sequence[Mapping[str, Any]], trading_dates: set[str]) -> dict[str, Any]:
    positive = negative = neutral = 0
    consecutive_buy = consecutive_sell = 0
    prev_date: str | None = None
    for obs in observations:
        date = obs["session_date"]
        if prev_date is not None and trading_dates and _has_gap(prev_date, date, trading_dates):
            consecutive_buy = consecutive_sell = 0
        net = obs.get("foreign_net_value_vnd")
        if net is None:
            consecutive_buy = consecutive_sell = 0
        elif net > 0:
            positive += 1
            consecutive_buy += 1
            consecutive_sell = 0
        elif net < 0:
            negative += 1
            consecutive_sell += 1
            consecutive_buy = 0
        else:
            neutral += 1
            consecutive_buy = consecutive_sell = 0
        prev_date = date
    return {
        "positive_session_count": positive,
        "negative_session_count": negative,
        "neutral_session_count": neutral,
        "current_consecutive_net_buy_sessions": consecutive_buy,
        "current_consecutive_net_sell_sessions": consecutive_sell,
    }


def _window_summary(
    observations: Sequence[Mapping[str, Any]], *, window_size: int, trading_dates: set[str]
) -> dict[str, Any]:
    """The most recent `window_size` qualified sessions -- but only counted
    "complete" when they are exactly the most recent `window_size` retained
    trading dates for this ticker with no gap between them. Fails closed
    (coverage != "complete", cumulative value None) otherwise. Never fills a
    missing session and never treats a calendar date as a trading session."""
    base = {"window_size": window_size, "sessions": [], "cumulative_net_value_vnd": None,
            "buy_value_vnd": None, "sell_value_vnd": None}
    if len(observations) < window_size:
        return {**base, "coverage": "incomplete",
                "reason": f"only {len(observations)} qualified session(s) retained, need {window_size}"}
    candidate = list(observations[-window_size:])
    candidate_dates = [o["session_date"] for o in candidate]
    if not trading_dates:
        return {**base, "sessions": candidate_dates, "coverage": "unverifiable",
                "reason": "no vn_stock.db trading-date reference available for this ticker"}
    expected = sorted(d for d in trading_dates if candidate_dates[0] <= d <= candidate_dates[-1])
    if expected != candidate_dates:
        missing = sorted(set(expected) - set(candidate_dates))
        return {**base, "sessions": candidate_dates, "coverage": "incomplete",
                "reason": f"gap detected -- missing session(s): {missing}"}
    net_values = [o.get("foreign_net_value_vnd") for o in candidate]
    if any(v is None for v in net_values):
        return {**base, "sessions": candidate_dates, "coverage": "incomplete",
                "reason": "at least one session in this window has no qualified net value"}
    return {
        "window_size": window_size,
        "sessions": candidate_dates,
        "coverage": "complete",
        "reason": None,
        "cumulative_net_value_vnd": sum(net_values),
        "buy_value_vnd": sum(o["foreign_buy_value_vnd"] for o in candidate),
        "sell_value_vnd": sum(o["foreign_sell_value_vnd"] for o in candidate),
    }


def build_series(runtime_root: Path | str, ticker: str) -> dict[str, Any]:
    """The canonical per-ticker foreign_flow contract: raw session observations plus
    bounded, fail-closed deterministic summaries. Generic across tickers -- identical
    code path regardless of which ticker is passed."""
    raw_observations = read_observations(runtime_root, ticker)
    observations = [_value_observation(raw) for raw in raw_observations]
    observations.sort(key=lambda o: o["session_date"])
    trading_dates = _retained_trading_dates(runtime_root, ticker)

    status = STATUS_AVAILABLE if observations else STATUS_MISSING
    qualified_with_net = [o for o in observations if o["foreign_net_value_vnd"] is not None]

    counts = _streaks_and_counts(observations, trading_dates)
    window_summaries = {
        "5_session": _window_summary(qualified_with_net, window_size=5, trading_dates=trading_dates),
        "10_session": _window_summary(qualified_with_net, window_size=10, trading_dates=trading_dates),
    }

    limitations = list(_STANDING_LIMITATIONS)
    if not trading_dates:
        limitations.append(
            "vn_stock.db has no retained OHLCV rows for this ticker; window completeness "
            "could not be independently verified against a trading-day reference."
        )

    return {
        "schema_version": SERIES_SCHEMA_VERSION,
        "ticker": ticker,
        "status": status,
        "source": PROVIDER,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "source_scope": "per_ticker_foreign_investor_value_flow",
        "point_in_time_status": POINT_IN_TIME_STATUS if observations else "not_applicable",
        "latest_session": observations[-1] if observations else None,
        "observations": observations,
        "qualified_session_count": len(qualified_with_net),
        "cumulative_net_value_vnd": (
            sum(o["foreign_net_value_vnd"] for o in qualified_with_net) if qualified_with_net else None
        ),
        "cumulative_window": {
            "first_session": qualified_with_net[0]["session_date"] if qualified_with_net else None,
            "last_session": qualified_with_net[-1]["session_date"] if qualified_with_net else None,
            "session_count": len(qualified_with_net),
        },
        **counts,
        "window_summaries": window_summaries,
        "warnings": list(_STANDING_WARNINGS),
        "limitations": limitations,
        "is_actionable": False,
    }
