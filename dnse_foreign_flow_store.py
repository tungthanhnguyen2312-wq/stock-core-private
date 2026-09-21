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
from datetime import date as _date
from pathlib import Path
from typing import Any, Mapping, Sequence

from atomic_io import atomic_write_file, validate_json_file
from daily_session_completion_reference import load_qualified_completed_sessions
from dnse_foreign_flow_capability import PROVIDER, SOURCE_CONTRACT_VERSION

STORE_SCHEMA_VERSION = "1.0.0"
SERIES_SCHEMA_VERSION = "1.0.0"
STORE_RELATIVE = Path("data") / "dnse-foreign-flow"
OBSERVATIONS_RELATIVE = STORE_RELATIVE / "observations"

STATUS_MISSING = "missing"
STATUS_AVAILABLE = "available"
VALUE_QUALIFICATION_STATUS = "QUALIFIED_VALUE_ONLY"
POINT_IN_TIME_STATUS = "qualified"

# Session-continuity proof: two distinct authority scopes, never conflated (see
# daily_session_completion_reference.py's module docstring for the boundary this
# encodes). A caller can always tell, from `continuity_reference["authority_scope"]`,
# whether a "complete"/"gap" verdict came from the exhaustive vn_stock.db OHLCV
# reference or from the non-exhaustive Daily completed-session registry fallback.
AUTHORITY_SCOPE_EXHAUSTIVE = "EXHAUSTIVE_TRADING_DATE_REFERENCE"
AUTHORITY_SCOPE_QUALIFIED_NONEXHAUSTIVE = "QUALIFIED_COMPLETED_SESSION_SET"
CONTINUITY_SOURCE_VN_STOCK_DB = "vn_stock_db_ohlcv"
CONTINUITY_SOURCE_DAILY_SESSION_REGISTRY = "daily_research_session_input_registry"
PROOF_CONTINUOUS = "PROVEN_CONTINUOUS"
PROOF_GAP = "PROVEN_GAP"
PROOF_UNVERIFIABLE = "UNVERIFIABLE"

# A ticker can have a real, non-empty exhaustive OHLCV history that is simply stale
# relative to the candidate interval (e.g. vn_stock.db retained through 2026-08-25,
# candidate window 2026-09-14..18). Non-empty is not the same as CAPABLE of proving
# THIS interval -- see `_exhaustive_reference_covers_interval`.
EXHAUSTIVE_REFERENCE_INTERVAL_COVERED = "EXHAUSTIVE_REFERENCE_INTERVAL_COVERED"
EXHAUSTIVE_REFERENCE_INTERVAL_NOT_COVERED = "EXHAUSTIVE_REFERENCE_INTERVAL_NOT_COVERED"

_STANDING_WARNINGS: tuple[str, ...] = (
    "foreign_volume_not_represented_here_unqualified_by_contract",
    "foreign_room_not_represented_here_unqualified_by_contract",
    "no_ownership_or_free_float_percentage_is_derived",
    "flow_relative_to_trading_value_is_not_computed_denominator_unqualified",
    "dnse_ohlc_price_basis_and_market_volume_basis_remain_unqualified_separately",
    "a_single_session_net_value_is_an_observation_not_a_trend_evaluate_the_full_observations_sequence",
    "no_score_ranking_or_bullish_bearish_label_is_computed_or_implied_by_this_contract",
    "foreign_value_flow_is_not_evidence_that_foreign_investors_caused_any_price_movement",
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


def _civil_day_gap(prev_date: str, date: str) -> int:
    """Calendar-day difference between two ISO dates.

    Used ONLY to prove that no OTHER calendar date exists between two market
    sessions that are ALREADY individually qualified by some proof source -- e.g. a
    diff of exactly 1 means there is no date at all in between, so nothing could be
    "missing" there. This is never used to infer that any date, adjacent or not, IS
    itself a trading session; that inference is never made anywhere in this module.
    """
    return (_date.fromisoformat(date) - _date.fromisoformat(prev_date)).days


def _exhaustive_reference_covers_interval(exhaustive_dates: set[str], candidate_dates: Sequence[str]) -> bool:
    """A non-empty exhaustive OHLCV reference is only CAPABLE of proving a candidate
    interval when its own retained range actually spans it. A real, non-empty vn_
    stock.db that simply stopped updating before the candidate window began (stale,
    not absent) must never be treated as authoritative for that window -- it has no
    opinion on dates outside its own retained range, which is different from having
    checked them and found no gap."""
    if not exhaustive_dates:
        return False
    return min(exhaustive_dates) <= candidate_dates[0] and max(exhaustive_dates) >= candidate_dates[-1]


def _prove_continuity(
    candidate_dates: Sequence[str], *, exhaustive_dates: set[str], registry_dates: frozenset[str],
) -> dict[str, Any]:
    """Decide whether no real trading session could have fallen between any adjacent
    pair in `candidate_dates` (sorted, len >= 2), and name exactly which authority
    proved it.

    Precedence: the EXHAUSTIVE vn_stock.db OHLCV reference is used only when it is
    both non-empty AND actually spans the candidate interval (existing exact-
    comparison semantics, unchanged, once that capability check passes) -- a stale-
    but-nonempty reference whose own retained range ends before the candidate window
    starts is NOT_COVERED, never treated as a gap, and falls through exactly like an
    entirely absent reference would. Only then does this fall back to the non-
    exhaustive Daily completed-session registry, which may prove continuity ONLY
    when every candidate date is itself registry-qualified AND every adjacent pair
    is exactly one civil day apart (so there is no calendar date in between for a
    market session to have gone unrecorded). A registry gap wider than one civil day
    can never be resolved to "complete" or "incomplete" -- it is always
    UNVERIFIABLE, because the registry's silence about an intervening date is not
    proof that date was not a trading day.
    """
    if _exhaustive_reference_covers_interval(exhaustive_dates, candidate_dates):
        expected = sorted(d for d in exhaustive_dates if candidate_dates[0] <= d <= candidate_dates[-1])
        if expected == list(candidate_dates):
            return {"proof_state": PROOF_CONTINUOUS, "source": CONTINUITY_SOURCE_VN_STOCK_DB,
                    "authority_scope": AUTHORITY_SCOPE_EXHAUSTIVE, "exhaustive": True, "reason": None,
                    "interval_capability": EXHAUSTIVE_REFERENCE_INTERVAL_COVERED}
        missing = sorted(set(expected) - set(candidate_dates))
        return {"proof_state": PROOF_GAP, "source": CONTINUITY_SOURCE_VN_STOCK_DB,
                "authority_scope": AUTHORITY_SCOPE_EXHAUSTIVE, "exhaustive": True,
                "reason": f"gap detected -- missing session(s): {missing}",
                "interval_capability": EXHAUSTIVE_REFERENCE_INTERVAL_COVERED}
    unqualified = [d for d in candidate_dates if d not in registry_dates]
    interval_capability = (EXHAUSTIVE_REFERENCE_INTERVAL_NOT_COVERED if exhaustive_dates else None)
    if unqualified:
        return {"proof_state": PROOF_UNVERIFIABLE, "source": CONTINUITY_SOURCE_DAILY_SESSION_REGISTRY,
                "authority_scope": AUTHORITY_SCOPE_QUALIFIED_NONEXHAUSTIVE, "exhaustive": False,
                "interval_capability": interval_capability,
                "reason": ("no vn_stock.db trading-date reference covers this interval, and session(s) "
                           "not registry-qualified as COMPLETED_RETAINED_EVIDENCE/trading_day_valid=true: "
                           f"{unqualified}")}
    for prev_date, date in zip(candidate_dates, candidate_dates[1:]):
        if _civil_day_gap(prev_date, date) != 1:
            return {"proof_state": PROOF_UNVERIFIABLE, "source": CONTINUITY_SOURCE_DAILY_SESSION_REGISTRY,
                    "authority_scope": AUTHORITY_SCOPE_QUALIFIED_NONEXHAUSTIVE, "exhaustive": False,
                    "interval_capability": interval_capability,
                    "reason": (f"calendar gap between {prev_date} and {date} exceeds one civil day; "
                               "the non-exhaustive Daily completed-session registry cannot prove no "
                               "market session fell in between -- its silence about an intervening "
                               "date is never treated as proof that date was not a trading day")}
    return {"proof_state": PROOF_CONTINUOUS, "source": CONTINUITY_SOURCE_DAILY_SESSION_REGISTRY,
            "authority_scope": AUTHORITY_SCOPE_QUALIFIED_NONEXHAUSTIVE, "exhaustive": False, "reason": None,
            "interval_capability": interval_capability}


def _streaks_and_counts(
    observations: Sequence[Mapping[str, Any]], *, exhaustive_dates: set[str], registry_dates: frozenset[str],
) -> dict[str, Any]:
    positive = negative = neutral = 0
    consecutive_buy = consecutive_sell = 0
    prev_date: str | None = None
    for obs in observations:
        date = obs["session_date"]
        if prev_date is not None:
            proof = _prove_continuity([prev_date, date], exhaustive_dates=exhaustive_dates,
                                       registry_dates=registry_dates)
            if proof["proof_state"] != PROOF_CONTINUOUS:
                # Continuity unproven (a real gap, or simply unknown) -- never fabricate it.
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


def _continuity_reference_provenance(proof: Mapping[str, Any]) -> dict[str, Any]:
    """The bounded provenance surfaced on every window summary -- enough for a
    caller to tell which authority produced the coverage verdict, and whether a
    non-empty exhaustive reference was actually capable of covering this interval
    (never internal implementation detail: no raw date sets, no registry contents)."""
    return {"source": proof["source"], "authority_scope": proof["authority_scope"],
            "exhaustive": proof["exhaustive"], "proof_state": proof["proof_state"],
            "interval_capability": proof.get("interval_capability")}


def _window_summary(
    observations: Sequence[Mapping[str, Any]], *, window_size: int,
    exhaustive_dates: set[str], registry_dates: frozenset[str],
) -> dict[str, Any]:
    """The most recent `window_size` qualified sessions -- but only counted
    "complete" when they are exactly the most recent `window_size` retained
    trading dates for this ticker with no gap between them, as proven by either the
    exhaustive vn_stock.db OHLCV reference or (only when that is unavailable) the
    non-exhaustive Daily completed-session registry fallback -- see
    `_prove_continuity`. Fails closed (coverage != "complete", cumulative value
    None) otherwise. Never fills a missing session and never treats a calendar date
    as a trading session."""
    base = {"window_size": window_size, "sessions": [], "cumulative_net_value_vnd": None,
            "buy_value_vnd": None, "sell_value_vnd": None, "continuity_reference": None}
    if len(observations) < window_size:
        return {**base, "coverage": "incomplete",
                "reason": f"only {len(observations)} qualified session(s) retained, need {window_size}"}
    candidate = list(observations[-window_size:])
    candidate_dates = [o["session_date"] for o in candidate]
    proof = _prove_continuity(candidate_dates, exhaustive_dates=exhaustive_dates, registry_dates=registry_dates)
    continuity_reference = _continuity_reference_provenance(proof)
    if proof["proof_state"] == PROOF_GAP:
        return {**base, "sessions": candidate_dates, "coverage": "incomplete",
                "reason": proof["reason"], "continuity_reference": continuity_reference}
    if proof["proof_state"] == PROOF_UNVERIFIABLE:
        return {**base, "sessions": candidate_dates, "coverage": "unverifiable",
                "reason": proof["reason"], "continuity_reference": continuity_reference}
    net_values = [o.get("foreign_net_value_vnd") for o in candidate]
    if any(v is None for v in net_values):
        return {**base, "sessions": candidate_dates, "coverage": "incomplete",
                "reason": "at least one session in this window has no qualified net value",
                "continuity_reference": continuity_reference}
    return {
        "window_size": window_size,
        "sessions": candidate_dates,
        "coverage": "complete",
        "reason": None,
        "cumulative_net_value_vnd": sum(net_values),
        "buy_value_vnd": sum(o["foreign_buy_value_vnd"] for o in candidate),
        "sell_value_vnd": sum(o["foreign_sell_value_vnd"] for o in candidate),
        "continuity_reference": continuity_reference,
    }


FRESHNESS_CURRENT = "current"
FRESHNESS_STALE = "stale"
FRESHNESS_NOT_APPLICABLE = "not_applicable"
FRESHNESS_UNKNOWN = "unknown"


def _freshness(
    latest_qualified_session_date: str | None,
    reference_session_date: str | None,
    trading_dates: set[str],
) -> dict[str, Any]:
    """Compare the latest retained foreign-flow session against the release's own exact
    reference trading session -- never calendar-day arithmetic, and never a wall-clock read.

    `reference_session_date` is the caller's already-resolved exact session identity (for
    `export_ai_bundle.py`, the same `latest_session` bound into the bundle's own
    `reference_session_date`). `trading_dates` is the same vn_stock.db-derived set
    `_window_summary`/`_streaks_and_counts` already use, so "how many sessions behind" is
    counted in real retained trading sessions, not elapsed calendar days. This never fills,
    guesses, or backdates a missing current session -- a lag is reported, never hidden."""
    base = {
        "reference_session_date": reference_session_date,
        "latest_qualified_session_date": latest_qualified_session_date,
        "sessions_behind": None,
    }
    if reference_session_date is None:
        return {**base, "status": FRESHNESS_UNKNOWN, "reason": "no_reference_session_date_provided"}
    if latest_qualified_session_date is None:
        return {**base, "status": FRESHNESS_NOT_APPLICABLE,
                "reason": "no_qualified_foreign_flow_session_retained"}
    if latest_qualified_session_date == reference_session_date:
        return {**base, "status": FRESHNESS_CURRENT, "sessions_behind": 0, "reason": None}
    if latest_qualified_session_date > reference_session_date:
        # Not expected under the documented offline/bounded ingestion pipeline (it never
        # writes a session ahead of the market data chain) -- fail closed rather than assume
        # what an out-of-order retained session means.
        return {**base, "status": FRESHNESS_UNKNOWN,
                "reason": "latest_qualified_session_is_after_the_reference_session"}
    # A real, non-empty `trading_dates` that simply stopped updating before
    # `reference_session_date` (stale, not absent -- the same shape
    # `_exhaustive_reference_covers_interval` guards against for window/streak
    # proof) is NOT capable of proving an exact lag count either: it has no
    # opinion on whether real trading sessions exist beyond its own retained
    # range, so silently counting only the dates it happens to have (here, zero)
    # would misreport an unverifiable lag as "0 sessions behind" right next to a
    # "stale" status. Only trust the count when the exhaustive reference's own
    # range actually reaches at least as far as the reference session.
    if not trading_dates or max(trading_dates) < reference_session_date:
        # The non-exhaustive Daily completed-session registry is deliberately never
        # consulted here either: it cannot prove an EXACT trading-session lag count,
        # only that specific individual dates were sessions -- see
        # _prove_continuity's docstring. A lag is reported (stale, never silently
        # current), but the exact count stays None rather than an unprovable guess.
        return {**base, "status": FRESHNESS_STALE,
                "reason": "retained foreign-flow data predates the reference session; exact "
                          "trading-session lag could not be verified against vn_stock.db (absent, or "
                          "stale and not reaching the reference session), and the non-exhaustive Daily "
                          "completed-session registry cannot prove an exact count"}
    sessions_behind = len(sorted(d for d in trading_dates
                                 if latest_qualified_session_date < d <= reference_session_date))
    return {**base, "status": FRESHNESS_STALE, "sessions_behind": sessions_behind,
            "reason": f"retained foreign-flow data is {sessions_behind} trading session(s) "
                      "behind the reference session"}


def build_series(
    runtime_root: Path | str, ticker: str, *, reference_session_date: str | None = None,
    qualified_session_registry_path: Path | str | None = None,
) -> dict[str, Any]:
    """The canonical per-ticker foreign_flow contract: raw session observations plus
    bounded, fail-closed deterministic summaries. Generic across tickers -- identical
    code path regardless of which ticker is passed.

    `reference_session_date` is optional and defaults to None (freshness reports
    "unknown") so every existing caller/test that does not pass it keeps its prior
    behavior unchanged; a production caller (export_ai_bundle.py) always supplies the
    bundle's own already-resolved exact session identity.

    `qualified_session_registry_path` is optional and defaults to None (no registry
    fallback -- window/streak continuity is provable only via vn_stock.db, exactly
    the pre-existing behavior every caller that omits it keeps). When a caller passes
    the explicit path to Daily's own config/daily_research_session_input_registry.json
    (never discovered from CWD or a guessed location -- see
    daily_session_completion_reference.py), this ticker's window/streak continuity
    may ALSO be proven via that non-exhaustive, fail-closed fallback whenever
    vn_stock.db has no OHLCV rows for this ticker. See `_prove_continuity`."""
    raw_observations = read_observations(runtime_root, ticker)
    observations = [_value_observation(raw) for raw in raw_observations]
    observations.sort(key=lambda o: o["session_date"])
    exhaustive_dates = _retained_trading_dates(runtime_root, ticker)
    registry_dates = (
        load_qualified_completed_sessions(qualified_session_registry_path)
        if qualified_session_registry_path is not None else frozenset()
    )

    status = STATUS_AVAILABLE if observations else STATUS_MISSING
    qualified_with_net = [o for o in observations if o["foreign_net_value_vnd"] is not None]

    counts = _streaks_and_counts(observations, exhaustive_dates=exhaustive_dates, registry_dates=registry_dates)
    window_summaries = {
        "5_session": _window_summary(qualified_with_net, window_size=5,
                                      exhaustive_dates=exhaustive_dates, registry_dates=registry_dates),
        "10_session": _window_summary(qualified_with_net, window_size=10,
                                       exhaustive_dates=exhaustive_dates, registry_dates=registry_dates),
    }
    freshness = _freshness(
        observations[-1]["session_date"] if observations else None,
        reference_session_date, exhaustive_dates,
    )

    limitations = list(_STANDING_LIMITATIONS)
    if not exhaustive_dates:
        limitations.append(
            "vn_stock.db has no retained OHLCV rows for this ticker; window completeness "
            "could not be independently verified against a trading-day reference"
            + (", falling back to the non-exhaustive Daily completed-session registry where it "
               "can prove continuity." if registry_dates else ".")
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
        "freshness": freshness,
        "warnings": list(_STANDING_WARNINGS),
        "limitations": limitations,
        "is_actionable": False,
    }
