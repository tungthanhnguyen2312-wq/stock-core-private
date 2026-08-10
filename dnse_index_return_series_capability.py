"""DNSE index return-series qualification: current-state benchmark returns.

Evidence base: the 2026-08-10 bounded index return-series pilot,
`operations-review/dnse-index-return-series-qualification-20260810/probe_results.json`
(3 calls: 1 auth check + 2 *identical* resolution="1D" type="INDEX" ohlc
calls for VNINDEX, same window twice -- see
tools/dnse_market_data_probe.py::build_index_return_series_call_plan()).
This module performs no network I/O; it carries the qualification verdict
that bounded empirical evidence established, plus generic classification
primitives, so a future session can extend the benchmark set without
re-deriving the method.

TERMINOLOGY, DELIBERATELY DIFFERENT FROM THE STOCK PRICE-BASIS CONTRACT
    Indices do not have corporate actions the way stocks do -- there is no
    ex-dividend or stock-split event to test raw-vs-adjusted against. This
    module never uses `price_basis = adjusted/raw` vocabulary. What it
    qualifies instead is: published index-level identity, point scale
    (index points, not VND), session semantics, historical continuity, and
    whether a deterministic return series can be safely constructed from the
    published levels. See dnse_ohlc_price_basis_capability.py for the
    stock-side analog (architectural reference only -- not reused directly,
    since its verdict vocabulary and evidence shape do not apply here).

WHAT WAS DEMONSTRATED, AND WHAT WAS NOT
    VNINDEX, window 2026-07-14 to 2026-08-07 (19 sessions, the same
    vn_stock.db-confirmed gap-free window already used for the HPG
    current-state pilot):
    - Endpoint/index availability: the `ohlc` endpoint accepts
      `type="INDEX", symbol="VNINDEX"`. `resolution="1D"` returns 19 real
      rows; `resolution="D"` was already shown (general qualification pass,
      2026-08-10) to return null/empty arrays for VNINDEX -- not retested
      here, reused as-is.
    - Repeated-query determinism: the same call, issued twice back-to-back,
      returned byte-identical response bodies (all of o/h/l/c/t/v).
    - Session semantics: 19/19 sessions, strictly ascending, no duplicates,
      exactly matching vn_stock.db's own retained VNINDEX trading-date
      calendar for this window (zero gaps, zero extra sessions).
    - OHLC internal consistency: `low <= open, close <= high` holds for
      19/19 sessions.
    - Level/unit qualification: DNSE's close level matches
      vn_stock.db's retained VNINDEX close (VCI-sourced, already the series
      `point_in_time_benchmark.py` uses in production) **exactly** --
      absolute difference 0.0 on all 19 sessions -- and every level falls
      within the plausible real-world VNINDEX point range. This establishes
      DNSE-vs-VCI *consistency*, not independent HOSE source authority:
      neither DNSE nor VCI *is* the index administrator (HOSE); both are
      republishing/computing the same published value. The exactness of the
      match (0.0 difference, not merely "close") is what makes this strong
      corroborating evidence rather than a coincidence of scale.

    NOT tested: VN30 (structural constituent-list evidence exists from the
    general qualification pass, but no VN30 *level* data was fetched this
    milestone -- Step 3 of this milestone explicitly limits formal
    qualification to one benchmark). Point-in-time safety (no pre-query
    historical snapshot exists for VNINDEX to test retrospective rewriting
    against, unlike VCB's archived snapshot in the stock price-basis
    milestone) -- deliberately left unqualified, not inferred safe merely
    because indices structurally lack a dividend-style adjustment mechanism.
    Index divisor/rebalancing/free-float mechanics are not modeled; this
    module consumes published index levels as-is.

    Coverage generalization beyond VNINDEX is explicitly NOT authorized --
    see EVIDENCE_QUALIFIED_BENCHMARKS below.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import dnse_current_state_price_analytics as price_analytics
from vn_time import VN_TZ

VERSION = "1.0.0"
PROVIDER = "DNSE"
SOURCE_CONTRACT_VERSION = "dnse_index_return_series/2026-08-10"

# Step 7/12's formal verdict vocabulary -- a binary qualification question
# (unlike the stock contract's 4-way raw/adjusted vocabulary): can a
# deterministic current-state return series be safely constructed at all.
QUALIFIED_CURRENT_STATE = "QUALIFIED_CURRENT_STATE"
INCONCLUSIVE = "INCONCLUSIVE"
RETURN_SERIES_VERDICTS = frozenset({QUALIFIED_CURRENT_STATE, INCONCLUSIVE})

# Step 8's mandatory semantics, carried verbatim on every result.
ANALYSIS_TIME_SEMANTICS = "current_state_benchmark_history"
# Not investigated this milestone (no pre-query archive exists for VNINDEX to
# test against) -- must not be inferred True merely because indices lack a
# stock-style adjustment mechanism. See module docstring.
PIT_BACKTEST_ELIGIBLE = False

INDEX_LEVEL_UNIT_QUALIFIED = "index_points"
INDEX_LEVEL_UNIT_UNQUALIFIED = "unqualified"

STATUS_QUALIFIED = "QUALIFIED_CURRENT_STATE_BENCHMARK_RETURN_SERIES"
STATUS_QUALIFIED_INCOMPLETE_WINDOW = "QUALIFIED_BENCHMARK_INCOMPLETE_WINDOW"
STATUS_NOT_QUALIFIED = "NOT_QUALIFIED_FOR_DNSE_INDEX_RETURN_SERIES"

# The active, evidence-grounded verdict. A caller may not upgrade this
# locally -- reaching a different verdict, or extending
# EVIDENCE_QUALIFIED_BENCHMARKS, requires new evidence, which requires
# editing these constants alongside it.
ACTIVE_RETURN_SERIES_VERDICT = QUALIFIED_CURRENT_STATE

# Step 3: VNINDEX only. Evidence-bounded, exactly like the stock contract's
# EVIDENCE_QUALIFIED_TICKERS -- a benchmark outside this set is not qualified,
# regardless of whether the same endpoint shape plausibly extends to it.
EVIDENCE_QUALIFIED_BENCHMARKS = ("VNINDEX",)

CROSS_CHECK_EVIDENCE: tuple[dict[str, Any], ...] = (
    {
        "benchmark_id": "VNINDEX",
        "window": {"from": "2026-07-14", "to": "2026-08-07"},
        "sessions_compared": 19,
        "comparison_source": (
            "vn_stock.db retained VNINDEX series (provider VCI, already the series "
            "point_in_time_benchmark.py consumes in production)"
        ),
        "max_absolute_difference": 0.0,
        "max_relative_difference": 0.0,
        "sessions_matching_exactly": 19,
        "ohlc_internal_consistency": "19/19 sessions: low <= open, close <= high",
        "repeated_query_determinism": "2 identical live calls, byte-identical response bodies",
        "plausible_index_point_range_checked": [200.0, 5000.0],
    },
)

WARNINGS = (
    "dnse_index_return_series_qualified_for_exactly_one_benchmark_vnindex_only",
    "coverage_generalization_beyond_vnindex_not_authorized_vn30_untested",
    "level_unit_established_by_exact_cross_reference_consistency_with_vn_stock_db_"
    "not_independent_hose_source_authority",
    "index_divisor_rebalancing_and_free_float_mechanics_not_modeled_published_levels_consumed_as_is",
    "point_in_time_backtest_safety_not_investigated_this_milestone_remains_unqualified",
    "not_wired_into_production_beta_correlation_or_provider_routing",
)


class DnseIndexReturnSeriesError(ValueError):
    """Fail-closed rejection for an out-of-vocabulary or unearned index-return claim."""


# --------------------------------------------------------------------- eligibility

def benchmark_current_state_eligible(benchmark_id: str) -> bool:
    """Fail-closed benchmark-level gate. True only when BOTH hold: (1) the
    active evidence-grounded verdict is QUALIFIED_CURRENT_STATE, and (2)
    `benchmark_id` is in EVIDENCE_QUALIFIED_BENCHMARKS (currently VNINDEX
    only). A benchmark sharing the same endpoint shape (e.g. VN30) does not
    thereby qualify -- see module docstring."""
    if ACTIVE_RETURN_SERIES_VERDICT != QUALIFIED_CURRENT_STATE:
        return False
    return str(benchmark_id).strip().upper() in EVIDENCE_QUALIFIED_BENCHMARKS


def current_state_eligibility(benchmark_id: str) -> dict[str, Any]:
    """The single, centralized eligibility record for "can a DNSE current-state
    index return series be built for this benchmark" -- callers should read
    this rather than re-deriving benchmark scope elsewhere."""
    normalized = str(benchmark_id).strip().upper()
    eligible = benchmark_current_state_eligible(normalized)
    record: dict[str, Any] = {
        "benchmark_id": normalized,
        "eligible_for_current_state_return_series": eligible,
        "qualification_scope": "evidence_bounded_benchmark",
        "source_contract_version": SOURCE_CONTRACT_VERSION,
    }
    if eligible:
        evidence = next(e for e in CROSS_CHECK_EVIDENCE if e["benchmark_id"] == normalized)
        record.update(
            status="QUALIFIED_FOR_DNSE_CURRENT_STATE_INDEX_RETURN_SERIES",
            reason=None,
            evidence_window=evidence["window"],
            evidence_sessions_compared=evidence["sessions_compared"],
        )
    else:
        reason = (
            "active_return_series_verdict_is_not_qualified_current_state"
            if ACTIVE_RETURN_SERIES_VERDICT != QUALIFIED_CURRENT_STATE
            else "no_retained_cross_check_evidence_for_this_benchmark_coverage_generalization_not_authorized"
        )
        record.update(
            status="NOT_QUALIFIED_FOR_DNSE_INDEX_RETURN_SERIES",
            reason=reason,
            evidence_window=None,
            evidence_sessions_compared=None,
        )
    return record


# --------------------------------------------------------------------- Step 5 semantic checks

def ohlc_internally_consistent(observation: Mapping[str, Any]) -> bool:
    """A candle sanity check: low is the minimum and high the maximum of the
    session's own open/close. Fails closed (False) on a missing field."""
    try:
        o, h, l, c = (observation["open"], observation["high"],
                      observation["low"], observation["close"])
    except KeyError:
        return False
    return l <= o <= h and l <= c <= h


def classify_level_unit(
    cross_check_rows: Sequence[Mapping[str, Any]],
    *,
    relative_tolerance: float = 0.005,
    plausible_range: tuple[float, float] = (200.0, 5000.0),
) -> str:
    """Classify whether a compared window's levels are qualified index
    points. Fails closed (INDEX_LEVEL_UNIT_UNQUALIFIED) if: no comparison
    rows exist, any row lacks a retained reference, any row falls outside
    `relative_tolerance` of its reference, or any level falls outside a
    plausible real-world index-point range. "Looks plausible" alone (in
    range) is never sufficient without the cross-reference match -- see
    module docstring."""
    if not cross_check_rows:
        return INDEX_LEVEL_UNIT_UNQUALIFIED
    for row in cross_check_rows:
        if row.get("retained_close") is None or row.get("verdict") != "consistent":
            return INDEX_LEVEL_UNIT_UNQUALIFIED
        level = row.get("dnse_close")
        if not isinstance(level, (int, float)) or isinstance(level, bool):
            return INDEX_LEVEL_UNIT_UNQUALIFIED
        if not (plausible_range[0] <= level <= plausible_range[1]):
            return INDEX_LEVEL_UNIT_UNQUALIFIED
        if row.get("relative_difference") is not None and row["relative_difference"] > relative_tolerance:
            return INDEX_LEVEL_UNIT_UNQUALIFIED
    return INDEX_LEVEL_UNIT_QUALIFIED


def cross_check_against_retained(
    observations: Sequence[Mapping[str, Any]],
    retained_close_by_date: Mapping[str, float],
    *,
    relative_tolerance: float = 0.005,
) -> list[dict[str, Any]]:
    """Session-by-session comparison against an already-retained reference
    close series (Step 6). Provider equality alone is not authority -- this
    records the comparison; `classify_level_unit` decides what it proves.
    Never makes a new network call; `retained_close_by_date` must already be
    in hand (e.g. read from vn_stock.db)."""
    rows: list[dict[str, Any]] = []
    for obs in observations:
        date = obs["session_date"]
        dnse_close = obs["close"]
        retained_close = retained_close_by_date.get(date)
        if retained_close is None:
            rows.append({
                "session_date": date, "dnse_close": dnse_close, "retained_close": None,
                "absolute_difference": None, "relative_difference": None,
                "verdict": "no_retained_reference_for_this_session",
            })
            continue
        abs_diff = abs(dnse_close - retained_close)
        rel_diff = (abs_diff / retained_close) if retained_close else None
        verdict = "consistent" if (rel_diff is not None and rel_diff <= relative_tolerance) else "inconsistent"
        rows.append({
            "session_date": date, "dnse_close": dnse_close, "retained_close": retained_close,
            "absolute_difference": abs_diff, "relative_difference": rel_diff, "verdict": verdict,
        })
    return rows


def assert_fail_closed(verdict: str) -> None:
    """Refuse an out-of-vocabulary formal return-series verdict."""
    if verdict not in RETURN_SERIES_VERDICTS:
        raise DnseIndexReturnSeriesError(f"return_series_verdict_invalid:{verdict}")


# --------------------------------------------------------------------- Step 2 series contract

def _observed_at_by_session_date(raw_ohlc: Mapping[str, Any]) -> dict[str, str]:
    """Maps each session's derived calendar date to DNSE's own raw bar
    timestamp (ISO-8601, Asia/Ho_Chi_Minh) -- kept as separate provenance
    from the canonical `session_date` used for ordering/gap logic. Matched by
    date (not array position) so it stays correct regardless of input
    ordering; safe to call on the same raw payload already validated by
    `dnse_current_state_price_analytics.normalize_bars` (duplicate/invalid
    rows are that function's job, not this one's)."""
    out: dict[str, str] = {}
    for epoch in raw_ohlc.get("t") or []:
        dt = datetime.fromtimestamp(int(epoch), tz=VN_TZ)
        out[dt.date().isoformat()] = dt.isoformat(timespec="seconds")
    return out


def _retained_trading_dates(runtime_root: Path | str, benchmark_id: str) -> set[str]:
    """Calendar dates vn_stock.db's own OHLCV table has a row for this
    benchmark -- used only to detect session gaps, never to read a level
    value from that table for gap-detection purposes (a separate, explicit
    read is used for the actual cross-check). Read-only; never writes."""
    import sqlite3

    db_path = Path(runtime_root) / "vn_stock.db"
    if not db_path.exists():
        return set()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = 1")
        rows = conn.execute(
            "SELECT DISTINCT date FROM ohlcv WHERE ticker = ?", (benchmark_id,)
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def build_index_return_series(
    benchmark_id: str,
    raw_ohlc: Mapping[str, Any] | None,
    *,
    runtime_root: Path | str | None = None,
    fetch_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The canonical DNSE index current-state series contract (Step 2).

    Reuses `dnse_current_state_price_analytics.normalize_bars()` and
    `.validate_session_sequence()` as-is for the generic DNSE-OHLC-shape
    parsing and gap detection (identical response shape for `type="INDEX"`
    as for `type="STOCK"`) -- not a parallel architecture, the smallest
    current-state adapter reusing already-tested pure components. Stock
    ticker data cannot enter this contract: eligibility is keyed to
    EVIDENCE_QUALIFIED_BENCHMARKS (currently VNINDEX only), entirely
    independent of dnse_ohlc_price_basis_capability.EVIDENCE_QUALIFIED_TICKERS
    (currently HPG/VCB) -- the two sets do not intersect and neither module
    reads the other's set.

    Always returns a dict; never raises for an ineligible benchmark. An
    ineligible benchmark's eligibility is decided before `raw_ohlc` is even
    inspected.
    """
    normalized_id = str(benchmark_id).strip().upper()
    eligibility = current_state_eligibility(normalized_id)
    record: dict[str, Any] = {
        "schema_version": VERSION,
        "benchmark_id": normalized_id,
        "source": PROVIDER,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "index_level_unit": INDEX_LEVEL_UNIT_UNQUALIFIED,
        "analysis_time_semantics": ANALYSIS_TIME_SEMANTICS,
        "pit_backtest_eligible": PIT_BACKTEST_ELIGIBLE,
        "eligibility": eligibility,
        "as_of_session": None,
        "observations": [],
        "coverage": {"status": "not_qualified", "session_count": 0,
                     "reason": eligibility.get("reason")},
        "current_state_qualified": False,
        "warnings": list(WARNINGS),
        "provenance": {"fetch": dict(fetch_provenance or {}), "dropped_sessions": []},
    }
    if not eligibility["eligible_for_current_state_return_series"]:
        record["status"] = STATUS_NOT_QUALIFIED
        return record

    normalized = price_analytics.normalize_bars(normalized_id, raw_ohlc or {})
    full_observations = normalized["observations"]
    observed_at_by_date = _observed_at_by_session_date(raw_ohlc or {})

    reference_dates = (
        _retained_trading_dates(runtime_root, normalized_id) if runtime_root is not None else set()
    )
    coverage = price_analytics.validate_session_sequence(
        full_observations, reference_trading_dates=reference_dates
    )
    ohlc_ok = bool(full_observations) and all(
        ohlc_internally_consistent(o) for o in full_observations
    )

    # Step 2: no open/high/low in the persisted contract -- an index return
    # series only needs the published close level per session.
    lean_observations = [
        {
            "session_date": o["session_date"],
            "observed_at": observed_at_by_date.get(o["session_date"]),
            "close_level": o["close"],
        }
        for o in full_observations
    ]

    record["observations"] = lean_observations
    record["as_of_session"] = lean_observations[-1]["session_date"] if lean_observations else None
    record["coverage"] = coverage
    record["provenance"]["dropped_sessions"] = normalized["dropped_sessions"]
    record["index_level_unit"] = INDEX_LEVEL_UNIT_QUALIFIED
    record["current_state_qualified"] = coverage["status"] == "complete" and ohlc_ok
    record["status"] = (
        STATUS_QUALIFIED if record["current_state_qualified"] else STATUS_QUALIFIED_INCOMPLETE_WINDOW
    )
    if not ohlc_ok and full_observations:
        record["warnings"] = record["warnings"] + [
            "ohlc_internal_consistency_check_failed_for_at_least_one_session"
        ]
    if normalized["dropped_sessions"]:
        record["warnings"] = record["warnings"] + [
            "one_or_more_sessions_dropped_for_missing_or_non_positive_level_never_interpolated"
        ]
    return record


def compute_returns_for_series(series: Mapping[str, Any]) -> dict[str, Any]:
    """Adapts this module's lean `{session_date, observed_at, close_level}`
    observation shape to `dnse_current_state_price_analytics.compute_returns()`'s
    expected `{session_date, close}` shape (same `r_t = close_t/close_(t-1) - 1`
    formula, reused unmodified rather than reimplemented)."""
    adapted = {
        "coverage": series.get("coverage"),
        "observations": [
            {"session_date": o["session_date"], "close": o["close_level"]}
            for o in series.get("observations") or []
        ],
        "analysis_time_semantics": series.get("analysis_time_semantics"),
        "pit_backtest_eligible": series.get("pit_backtest_eligible"),
    }
    return price_analytics.compute_returns(adapted)


def serialize(record: Mapping[str, Any]) -> str:
    """Deterministic JSON serialization -- same input always produces the
    same bytes, so a caller can hash/compare/replay a retained record."""
    return json.dumps(record, sort_keys=True, default=str)


def active_capability_contract() -> dict[str, Any]:
    """The canonical, active DNSE index return-series verdict, assembled once
    from the 2026-08-10 bounded pilot's evidence. Deliberately carries no
    provider-routing or beta/correlation-production flag: this stays a
    qualification record -- point_in_time_market_risk.py is untouched."""
    return {
        "schema_version": VERSION,
        "source": PROVIDER,
        "contract_version": SOURCE_CONTRACT_VERSION,
        "return_series_verdict": ACTIVE_RETURN_SERIES_VERDICT,
        "evidence_qualified_benchmarks": list(EVIDENCE_QUALIFIED_BENCHMARKS),
        "analysis_time_semantics": ANALYSIS_TIME_SEMANTICS,
        "pit_backtest_eligible": PIT_BACKTEST_ELIGIBLE,
        "cross_check_evidence": [dict(e) for e in CROSS_CHECK_EVIDENCE],
        "warnings": list(WARNINGS),
        "qualification_status": "SOURCE_QUALIFICATION_COMPLETE_NOT_INTEGRATED",
        "evidence": (
            "operations-review/dnse-index-return-series-qualification-20260810/probe_results.json"
        ),
    }
