"""Multi-source exact-session market evidence resolver (DNSE + VCI + KBS).

CURRENT RESEARCH / DAILY PRODUCT MODE only -- never Audit/PIT/Execution Mode. Serves
canonical Daily's product-critical resilience requirement: a single-provider (DNSE)
exact-session gap must not stop the whole Daily chain when this project's own existing
VCI/KBS acquisition capability (vn_stock_pipeline.py) can independently supply the same
session for the tickers DNSE is missing.

FOUR-PASS ACQUISITION STRATEGY (never re-fetches an already-resolved ticker)
    PASS 1  DNSE exact-session acquisition -- unmodified, supplied by the caller as
            ``dnse_snapshot`` (mva_exact_session_snapshot.materialize_snapshot()'s own
            output; this module never re-implements DNSE's fetch).
    PASS 2  Identify candidates DNSE did not resolve (disposition != EXACT_SESSION_RETAINED).
    PASS 3  KBS recovery for exactly those candidates, one bounded sequential request per
            ticker (vn_stock_pipeline.fetch_single_source, reused unmodified -- same
            retry budget, same circuit breaker, same REQUEST_DELAY pacing already proven
            safe for this provider family; see docs/DECISIONS.md
            MARKET_WIDE_ENRICHMENT_AND_CANONICALIZATION_V1 = PAUSED_RATE_LIMIT_CONSTRAINED).
            No concurrency: this repository has zero evidence VCI/KBS tolerate concurrent
            access, so Pass 3/4 stay exactly as sequential/paced as vn_stock_pipeline.py's
            own existing cmd_backfill/cmd_update commands.
    PASS 4  VCI recovery only for candidates still missing after Pass 3.

RESOLUTION POLICY -- see multi_source_market_evidence_contract.resolve_ticker(). Per
ticker: RESOLVED_SINGLE_SOURCE_RESEARCH (the overwhelmingly common case, by design --
this module only ever queries enough sources to get one answer), RESOLVED_CORROBORATED
or SOURCE_CONFLICT (only possible if a ticker happens to collect 2+ EXACT_SESSION_OBSERVED
entries), or SESSION_MISSING_ALL_SOURCES.

OUTPUT -- two artifacts, never one conflated shape:
    1. multi_source_exact_session_market_evidence/v1 (full per-source, per-ticker
       evidence -- "For HPG: which source(s) supplied the bar? which value was used?
       did sources agree? what was blocked?").
    2. A drop-in PROJECTION into mva_exact_session_snapshot's own
       "p3f9_exact_session_mva_snapshot/v2" shape (same contract_version -- verified
       against this repository's own consumers, none of which key behavior off that
       string except canonical_post_close_pipeline.assert_post_close_eligible, which
       only requires it be present and unchanged; per-ticker provenance lives honestly
       in each record's provider field, exactly where every existing consumer already
       looks). This is what every existing Level-2 tool (breadth foundation, universe
       status, liquidity research, technical recovery, descriptive research, valuation,
       tactical classifier, corporate intelligence, sector leadership) keeps consuming
       completely unmodified -- see daily_session_level2_package.ensure_exact_session_snapshot.

PRICE/VOLUME BASIS CAUTION (empirical, from this milestone's own bounded qualification
against 2026-09-03): DNSE's own retained close/low for MWG and GMD -- two of the 17
tickers DNSE DID resolve that day -- differ from VCI/KBS's independently-observed
values (open/high identical; low/close differ by more than one HOSE tick; VCI/KBS
volume ~30-44x DNSE's), consistent with DNSE's snapshot possibly predating ATC-auction
settlement for at least some sessions. This module therefore NEVER re-queries or
second-guesses a ticker DNSE already resolved (Pass 2 only ever targets DNSE's own
gaps), and volume is never synthesized across provider families (see
multi_source_market_evidence_contract.VOLUME_COMPARABLE_SOURCE_FAMILIES) -- flagged in
the qualification report as a genuine follow-up, not something this milestone's bounded
scope authorizes fixing.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from field_temporal_contract import stable_id
from multi_source_market_evidence_contract import (
    DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD,
    NATIVE_PRICE_UNIT_SCALE,
    RESOLUTION_ALL_MISSING,
    RESOLUTION_CONFLICT,
    RESOLUTION_CORROBORATED,
    RESOLUTION_CORROBORATED_NON_DNSE,
    STATUS_EXACT_SESSION_OBSERVED,
    STATUS_MALFORMED,
    STATUS_NOT_APPLICABLE,
    STATUS_SESSION_MISSING,
    STATUS_SOURCE_REJECTED,
    STATUS_TRANSPORT_FAILED,
    build_source_observation,
    classify_dnse_provider_health,
    resolve_ticker,
    resolve_ticker_degraded_dnse,
)

DNSE_EXACT_SESSION_DISPOSITION = "EXACT_SESSION_RETAINED"
# All qualified secondary sources, kept in established observation/tie-break order.
RECOVERY_SOURCES = ("VCI", "KBS")
# The small provider-health classifier always checks both independently. Its source order is
# deliberately separate from market-wide routing: a sentinel is corroboration, not a recovery
# preference.
SENTINEL_SOURCES = ("VCI", "KBS")
# 2026-09-04 bounded 30-ticker live evidence: KBS matched VCI's 27/30 exact coverage with no
# retries/timeouts and materially lower p95. This is Current Research routing only; it neither
# changes SOURCE_PREFERENCE_ORDER nor promotes either source beyond its existing contract.
MARKET_WIDE_RECOVERY_SOURCE_ORDER = ("KBS", "VCI")
DEFAULT_RECOVERY_WINDOW_CALENDAR_DAYS = 15
ARTIFACT_TYPE = "MULTI_SOURCE_EXACT_SESSION_MARKET_EVIDENCE"

# Daily remains a one-command foreground operation, but it must not silently turn a
# degraded provider into an unbounded multi-hour foreground job.  The guard is
# intentionally sequential: it forecasts the selected primary/failover topology and never
# creates an inference that either provider permits concurrency.
DAILY_RECOVERY_RUNTIME_BUDGET_SECONDS = 45 * 60
MIN_TIMED_REQUESTS_FOR_RUNTIME_PROJECTION = 5

# Owner-directed watch cohort (canonical home -- tools/run_multi_source_exact_session_resolver.py
# imports this rather than keeping its own copy).
WATCHLIST_11 = ("SSI", "EVF", "PAN", "HPG", "FPT", "PVD", "QNS", "VNM", "POW", "PDR", "NLG")

# ---------------------------------------------------------------------------
# DNSE quality sentinel cohort -- see select_sentinel_cohort. Versioned because the cohort
# composition rule is itself part of this artifact's evidence contract: a health verdict is only
# reproducible if the cohort that produced it is identified alongside it.
# ---------------------------------------------------------------------------
SENTINEL_COHORT_VERSION = "dnse_quality_sentinel_cohort/v1"
DEFAULT_GOVERNED_LIQUID_SAMPLE_SIZE = 5
DEFAULT_PER_EXCHANGE_SAMPLE_SIZE = 3
DEFAULT_DNSE_EXACT_SAMPLE_SIZE = 18
SENTINEL_EXCHANGES = ("HOSE", "HNX", "UPCOM")

WHEN_DNSE_HEALTHY_POLICY = (
    "DNSE_EXACT_AND_CORROBORATED or isolated DNSE_MATERIAL_CONFLICT (not broad/systemic): Lane A "
    "gap recovery stays scoped to DNSE's own SESSION_MISSING/rejected/failed tickers only. A "
    "DNSE-exact ticker outside the sentinel cohort is never queried against VCI/KBS -- this is "
    "the cheap path and remains the default for a healthy provider day."
)
WHEN_DNSE_DEGRADED_POLICY = (
    "DNSE_BROAD_STALE_OR_INCOMPLETE_EOD: the bare resolve_multi_source_exact_session_snapshot "
    "call (this function's own low-level contract, unchanged -- still what the standalone "
    "tools/run_multi_source_exact_session_resolver.py diagnostic uses) never resolves remaining "
    "DNSE-exact tickers from DNSE's own unverified same-date bars by itself; a caller wanting "
    "fail-closed-on-degraded semantics still calls assert_dnse_quality_acceptable(evidence) "
    "explicitly. The product-critical Daily entrypoint "
    "(daily_session_level2_package.ensure_exact_session_snapshot) instead calls "
    "resolve_exact_session_with_autorecovery, which automatically enters "
    "DEGRADED_PROVIDER_RECOVERY_MODE in the SAME foreground invocation -- no operator flag, no "
    "second command -- keeping the small VCI+KBS sentinel while recovering every other DNSE-exact "
    "ticker KBS-first, with VCI only after a KBS missing/failed/unusable result, before the "
    "caller\'s own MIN_EXACT_SESSION_COVERAGE_RATIO gate makes the final decision."
)


class DnseProviderWideQualityDegraded(RuntimeError):
    """The DNSE quality sentinel found DNSE_BROAD_STALE_OR_INCOMPLETE_EOD for this session.

    Raise this (via assert_dnse_quality_acceptable, AFTER persisting evidence/projected --
    never in place of persisting them) instead of either (a) silently resolving every other
    DNSE-exact ticker from DNSE's own unverified same-date bar, or (b) automatically launching
    a full-universe VCI/KBS recovery pass inline. Scope expansion to all DNSE-exact tickers is
    a bounded foreground Daily operation an operator explicitly chooses (re-run with an
    expanded sentinel_cohort), never an automatic side effect of a single acceptance call.

    ``dnse_quality_sentinel`` carries the full cohort/health verdict that triggered this, so a
    caller can report exact scope/counts without re-deriving them from the evidence artifact.
    """

    def __init__(self, message: str, *, dnse_quality_sentinel: Mapping[str, Any]):
        super().__init__(message)
        self.dnse_quality_sentinel = dnse_quality_sentinel


def assert_dnse_quality_acceptable(evidence: Mapping[str, Any]) -> None:
    """Fail-closed policy check a caller runs AFTER persisting ``evidence``/``projected`` from
    ``resolve_multi_source_exact_session_snapshot`` (never before -- this milestone's own real
    2026-09-03 validation found DNSE_BROAD_STALE_OR_INCOMPLETE_EOD on its very first live
    sentinel run; discarding that real, hard-won VCI/KBS evidence by raising before it was
    written would have thrown away the only genuine record of why the day degraded).

    No-op when ``dnse_quality_sentinel`` is absent (no sentinel_cohort was supplied) or the
    verdict is anything other than DNSE_BROAD_STALE_OR_INCOMPLETE_EOD.
    """
    sentinel = evidence.get("dnse_quality_sentinel")
    if sentinel is None:
        return
    health = sentinel["health"]
    if health["state"] == DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD:
        raise DnseProviderWideQualityDegraded(
            "DNSE_BROAD_STALE_OR_INCOMPLETE_EOD:"
            f"conflict={health['conflict_count']}/{health['dnse_assessed_count']}:"
            "operator_must_explicitly_expand_recovery_scope",
            dnse_quality_sentinel=sentinel,
        )


def select_sentinel_cohort(
    *,
    candidate_metadata: Mapping[str, Mapping[str, Any]],
    dnse_exact_tickers: Sequence[str],
    watchlist: Sequence[str] = WATCHLIST_11,
    governed_liquid_sample_size: int = DEFAULT_GOVERNED_LIQUID_SAMPLE_SIZE,
    per_exchange_sample_size: int = DEFAULT_PER_EXCHANGE_SAMPLE_SIZE,
    dnse_exact_sample_size: int = DEFAULT_DNSE_EXACT_SAMPLE_SIZE,
) -> dict[str, Any]:
    """Deterministic, versioned DNSE quality-sentinel cohort. Never random sampling: every
    member is selected by a fixed rule over inputs the caller supplies, so the same inputs
    always produce the same cohort.

    Composition (a ticker may qualify via more than one reason -- ``reasons`` records all of
    them, the flat ``tickers`` list is deduplicated):
      - OWNER_WATCHLIST_11: the fixed 11-ticker owner watch cohort.
      - GOVERNED_LIQUID_TOP: the ``governed_liquid_sample_size`` candidates with the largest
        market_cap in ``candidate_metadata`` (a governed field already retained in this
        project's own runtime metadata -- no new liquidity computation invented here).
      - CROSS_EXCHANGE_<HOSE|HNX|UPCOM>: the ``per_exchange_sample_size`` largest-market-cap
        candidates on each exchange, so a systemic issue confined to one exchange is still
        detectable even if the watchlist/governed-liquid sets happen to skew toward another.
      - DNSE_EXACT_SESSION_SAMPLE: up to ``dnse_exact_sample_size`` of DNSE's own exact-session
        tickers for this session (sorted, first N) -- the sentinel must include names DNSE
        itself resolved, since those are exactly what a same-date-but-wrong-value failure
        would otherwise hide.
    All rankings break ties on the ticker symbol itself, never on iteration/insertion order.
    """
    def _market_cap(ticker: str) -> float:
        raw = candidate_metadata.get(ticker, {}).get("market_cap")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return -1.0
        return value if value == value else -1.0  # NaN guard, still deterministic

    reasons: dict[str, set[str]] = {}

    def _add(tickers: Sequence[str], reason: str) -> None:
        for ticker in tickers:
            reasons.setdefault(ticker, set()).add(reason)

    _add([t for t in watchlist if t in candidate_metadata], "OWNER_WATCHLIST_11")

    ranked_all = sorted(candidate_metadata, key=lambda t: (-_market_cap(t), t))
    _add(ranked_all[:governed_liquid_sample_size], "GOVERNED_LIQUID_TOP")

    for exchange in SENTINEL_EXCHANGES:
        ranked_exchange = sorted(
            (t for t in candidate_metadata if candidate_metadata[t].get("exchange") == exchange),
            key=lambda t: (-_market_cap(t), t),
        )
        _add(ranked_exchange[:per_exchange_sample_size], f"CROSS_EXCHANGE_{exchange}")

    _add(sorted(dnse_exact_tickers)[:dnse_exact_sample_size], "DNSE_EXACT_SESSION_SAMPLE")

    tickers = sorted(reasons)
    return {
        "cohort_version": SENTINEL_COHORT_VERSION,
        "tickers": tickers,
        "size": len(tickers),
        "reasons": {ticker: sorted(rs) for ticker, rs in reasons.items()},
    }


def read_candidate_metadata(runtime_root: Path, tickers: Sequence[str] | None = None) -> dict[str, dict[str, Any]]:
    """Read-only ``exchange``/``market_cap`` lookup from this project's own retained runtime
    metadata (same ``vn_stock.db`` table and read-only connection pattern as
    ``mva_exact_session_snapshot.canonical_candidates``). Never opened for writing; never
    called while a governed acquisition holds the write lock on this same database file.
    """
    database = runtime_root / "vn_stock.db"
    if not database.exists():
        # Sentinel cohort selection is a best-effort quality enhancement, never a new hard
        # dependency for the core DNSE/VCI/KBS acquisition: a runtime without this project's
        # own metadata database (a bounded test fixture, or a not-yet-synced runtime) degrades
        # to an empty metadata set -- select_sentinel_cohort still returns the watchlist and
        # DNSE-exact-sample members, only GOVERNED_LIQUID_TOP/CROSS_EXCHANGE_* are unavailable
        # -- rather than failing the whole acquisition on a missing side-input.
        return {}
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute("SELECT ticker, exchange, market_cap FROM metadata").fetchall()
    finally:
        connection.close()
    wanted = set(tickers) if tickers is not None else None
    return {
        str(ticker).upper(): {"exchange": exchange, "market_cap": market_cap}
        for ticker, exchange, market_cap in rows
        if wanted is None or str(ticker).upper() in wanted
    }

PROVIDER_INTERFACE = {
    "DNSE": "dnse_openapi_rest_unversioned_2026",
    "VCI": "vnstock_quote_history/v4",
    "KBS": "vnstock_quote_history/v4",
}
PROVIDER_ENDPOINT = {
    "VCI": "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",
    "KBS": "https://kbbuddywts.kbsec.com.vn/iis-server/investment/history",
}


class MultiSourceResolverError(ValueError):
    """A caller-supplied input violates this module's own invariants."""


class DailyRecoveryRuntimeBudgetExceeded(RuntimeError):
    """The bounded Daily recovery forecast exceeds its deterministic wall-time budget.

    ``diagnostic`` is deliberately complete enough for the Daily entrypoint to retain an
    immutable abort record without writing a partially-resolved canonical snapshot.
    """

    def __init__(self, diagnostic: Mapping[str, Any]):
        self.diagnostic = dict(diagnostic)
        super().__init__(
            "DAILY_RECOVERY_RUNTIME_BUDGET_EXCEEDED:"
            f"stage={self.diagnostic['stage']}:"
            f"projected_seconds={self.diagnostic['projected_total_seconds']:.1f}:"
            f"budget_seconds={self.diagnostic['runtime_budget_seconds']:.1f}"
        )


class _DailyRecoveryRuntimeGuard:
    """Sequential throughput accounting and fail-closed runtime projection.

    The forecast starts with a pacing-only lower bound, then switches to provider-specific
    median observed elapsed time after a small sample.  It is deterministic for a given
    request trace, does not assume provider parallelism, and is deliberately re-planned at
    the selected primary->fallback boundary once the real fallback count is known.
    """

    def __init__(self, *, request_delay: float, runtime_budget_seconds: float = DAILY_RECOVERY_RUNTIME_BUDGET_SECONDS,
                 clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._started = clock()
        self.request_delay = float(request_delay)
        self.runtime_budget_seconds = float(runtime_budget_seconds)
        self.stage = "NOT_STARTED"
        self.remaining_by_source = {source: 0 for source in RECOVERY_SOURCES}
        self._elapsed_by_source: dict[str, list[float]] = {source: [] for source in RECOVERY_SOURCES}
        self._network_calls = {source: 0 for source in RECOVERY_SOURCES}
        self._provider_attempts = {source: 0 for source in RECOVERY_SOURCES}
        self._retries = {source: 0 for source in RECOVERY_SOURCES}
        self._timeouts = {source: 0 for source in RECOVERY_SOURCES}
        self._circuit_skips = {source: 0 for source in RECOVERY_SOURCES}
        self._target_session_usable = {source: 0 for source in RECOVERY_SOURCES}
        self._target_session_unusable = {source: 0 for source in RECOVERY_SOURCES}
        self._conditional_failover: tuple[str, str] | None = None
        self._cache_hits = 0
        self._pacing_seconds_scheduled = 0.0

    @staticmethod
    def _median(values: Sequence[float]) -> float:
        ordered = sorted(values)
        if not ordered:
            return 0.0
        midpoint = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[midpoint]
        return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0

    def set_plan(self, *, stage: str, remaining_by_source: Mapping[str, int]) -> None:
        self.stage = stage
        self.remaining_by_source = {
            source: max(0, int(remaining_by_source.get(source, 0)))
            for source in RECOVERY_SOURCES
        }
        self._assert_within_budget()

    def cache_hit(self, _ticker: str, _source: str) -> None:
        self._cache_hits += 1

    def set_primary_failover(self, primary: str, fallback: str) -> None:
        """Forecast fallback only to the extent completed primary calls actually need it."""
        if primary not in RECOVERY_SOURCES or fallback not in RECOVERY_SOURCES:
            raise MultiSourceResolverError(f"UNKNOWN_RECOVERY_SOURCE_PAIR:{primary}:{fallback}")
        self._conditional_failover = (primary, fallback)

    def clear_conditional_failover(self) -> None:
        self._conditional_failover = None

    def record_target_session_result(self, *, source: str, usable: bool) -> None:
        if source not in RECOVERY_SOURCES:
            return
        bucket = self._target_session_usable if usable else self._target_session_unusable
        bucket[source] += 1
        self._assert_within_budget()

    def observe(self, *, ticker: str, source: str, outcome: Any, elapsed_seconds: float) -> None:
        del ticker
        if source not in RECOVERY_SOURCES:
            return
        self._network_calls[source] += 1
        self._elapsed_by_source[source].append(float(elapsed_seconds))
        self._pacing_seconds_scheduled += self.request_delay
        self.remaining_by_source[source] = max(0, self.remaining_by_source[source] - 1)

        errors = list(getattr(outcome, "errors", None) or [])
        attempts = int(getattr(outcome, "request_attempts", 0) or 0)
        if attempts == 0 and not (len(errors) == 1 and errors[0].endswith(":circuit_open")):
            attempts = max(1, len(errors))
        retries = getattr(outcome, "retry_count", None)
        if retries is None or int(retries) == 0 and attempts > 1:
            retries = max(0, attempts - 1)
        timeouts = getattr(outcome, "timeout_count", None)
        if timeouts is None or int(timeouts) == 0 and errors:
            timeouts = sum("timeout" in str(error).lower() for error in errors)
        self._provider_attempts[source] += attempts
        self._retries[source] += int(retries or 0)
        self._timeouts[source] += int(timeouts or 0)
        if len(errors) == 1 and errors[0].endswith(":circuit_open"):
            self._circuit_skips[source] += 1
        self._assert_within_budget()

    def _estimated_call_seconds(self, source: str) -> float:
        own = self._elapsed_by_source[source]
        if len(own) >= MIN_TIMED_REQUESTS_FOR_RUNTIME_PROJECTION:
            return self._median(own) + self.request_delay
        all_samples = [elapsed for values in self._elapsed_by_source.values() for elapsed in values]
        if len(all_samples) >= MIN_TIMED_REQUESTS_FOR_RUNTIME_PROJECTION:
            return self._median(all_samples) + self.request_delay
        return self.request_delay

    def _projection(self) -> tuple[float, float, float]:
        elapsed = self._clock() - self._started
        # The last request's pacing has been scheduled but may not yet have happened when the
        # post-request guard runs, so account for every genuine call exactly once here.
        pending_pacing = max(0.0, self._pacing_seconds_scheduled - elapsed)
        remaining = sum(
            self.remaining_by_source[source] * self._estimated_call_seconds(source)
            for source in RECOVERY_SOURCES
        )
        # During primary-first recovery, a target-session-missing primary response is the relevant
        # failure signal, not merely FetchOutcome.status (a history request can succeed while
        # legitimately lacking the requested session).  Once five such outcomes are known,
        # include the deterministic observed fallback rate in the pre-completion forecast.
        if self._conditional_failover is not None:
            primary, fallback = self._conditional_failover
            assessed = self._target_session_usable[primary] + self._target_session_unusable[primary]
            if assessed >= MIN_TIMED_REQUESTS_FOR_RUNTIME_PROJECTION:
                estimated_fallback = (
                    self.remaining_by_source[primary] * self._target_session_unusable[primary] / assessed
                )
                remaining += estimated_fallback * self._estimated_call_seconds(fallback)
        projected = elapsed + pending_pacing + remaining
        return elapsed, remaining, projected

    def _assert_within_budget(self) -> None:
        elapsed, remaining, projected = self._projection()
        if projected > self.runtime_budget_seconds:
            raise DailyRecoveryRuntimeBudgetExceeded(self.diagnostic(
                elapsed_seconds=elapsed,
                projected_remaining_seconds=remaining,
                projected_total_seconds=projected,
            ))

    def diagnostic(self, *, elapsed_seconds: float | None = None,
                   projected_remaining_seconds: float | None = None,
                   projected_total_seconds: float | None = None) -> dict[str, Any]:
        if elapsed_seconds is None or projected_remaining_seconds is None or projected_total_seconds is None:
            elapsed_seconds, projected_remaining_seconds, projected_total_seconds = self._projection()
        by_provider = {}
        for source in RECOVERY_SOURCES:
            samples = self._elapsed_by_source[source]
            by_provider[source] = {
                "network_calls": self._network_calls[source],
                "provider_attempts": self._provider_attempts[source],
                "retries": self._retries[source],
                "timeouts": self._timeouts[source],
                "circuit_skips": self._circuit_skips[source],
                "target_session_usable": self._target_session_usable[source],
                "target_session_unusable": self._target_session_unusable[source],
                "elapsed_seconds_total": round(sum(samples), 6),
                "elapsed_seconds_min": round(min(samples), 6) if samples else None,
                "elapsed_seconds_median": round(self._median(samples), 6) if samples else None,
                "elapsed_seconds_max": round(max(samples), 6) if samples else None,
                "projected_seconds_per_sequential_call": round(self._estimated_call_seconds(source), 6),
                "remaining_planned_calls": self.remaining_by_source[source],
            }
        return {
            "contract_version": "daily_multi_source_recovery_throughput/v1",
            "concurrency": {"enabled": False, "reason": "NO_BOUNDED_LIVE_CONCURRENCY_SAFETY_EVIDENCE"},
            "stage": self.stage,
            "runtime_budget_seconds": self.runtime_budget_seconds,
            "elapsed_seconds": round(elapsed_seconds, 6),
            "projected_remaining_seconds": round(projected_remaining_seconds, 6),
            "projected_total_seconds": round(projected_total_seconds, 6),
            "request_count": sum(self._network_calls.values()),
            "provider_attempt_count": sum(self._provider_attempts.values()),
            "pacing_seconds_scheduled": round(self._pacing_seconds_scheduled, 6),
            "duplicate_work": {"cache_hits_prevented": self._cache_hits, "network_pair_duplicates": 0},
            "providers": by_provider,
        }


def _default_fetch_single_source():
    import vn_stock_pipeline as vsp
    vsp._install_bounded_http()
    return vsp.fetch_single_source


def _default_request_delay() -> float:
    import vn_stock_pipeline as vsp
    return vsp.REQUEST_DELAY


def _lineage_hash_for_session(lineage: list[Mapping[str, Any]], session: str) -> str | None:
    for record in lineage:
        if record.get("trading_session_date") == session:
            hash_value = record.get("source_record_hash")
            return hash_value if isinstance(hash_value, str) else None
    return None


def _classify_recovery_outcome(
    *, outcome: Any, source: str, ticker: str, target_session: str,
) -> tuple[str, str | None, Mapping[str, Any] | None, list[Mapping[str, Any]]]:
    """Map a vn_stock_pipeline.FetchOutcome to this module's status vocabulary.

    Returns (status, reason_code, native_ohlcv_or_None, lineage_records).
    """
    if outcome.status == "success":
        df = outcome.data
        row = df[df["date"] == target_session]
        if len(row):
            r = row.iloc[0]
            native = {
                "open": float(r["open"]) / df.attrs["unit_scale"],
                "high": float(r["high"]) / df.attrs["unit_scale"],
                "low": float(r["low"]) / df.attrs["unit_scale"],
                "close": float(r["close"]) / df.attrs["unit_scale"],
                "volume": int(r["volume"]),
            }
            return STATUS_EXACT_SESSION_OBSERVED, None, native, outcome.lineage
        return STATUS_SESSION_MISSING, "TARGET_SESSION_ABSENT_FROM_RETURNED_HISTORY", None, []
    if outcome.status == "empty":
        return STATUS_SESSION_MISSING, "SOURCE_CONFIRMED_EMPTY_HISTORY", None, []
    # status == "failed"
    errors = ",".join(outcome.errors or [])
    if outcome.transient_failure:
        return STATUS_TRANSPORT_FAILED, errors or "TRANSIENT_FAILURE", None, []
    if "invalid_schema" in errors:
        return STATUS_MALFORMED, errors, None, []
    return STATUS_SOURCE_REJECTED, errors or "PERMANENT_FAILURE", None, []


def resolve_multi_source_exact_session_snapshot(
    *,
    dnse_snapshot: Mapping[str, Any],
    target_session: str,
    requested_at: str,
    recovery_window_days: int = DEFAULT_RECOVERY_WINDOW_CALENDAR_DAYS,
    fetch_single_source: Callable[..., Any] | None = None,
    request_delay: float | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    max_recovery_candidates: int | None = None,
    sentinel_cohort: Sequence[str] | None = None,
    recovery_runtime_guard: _DailyRecoveryRuntimeGuard | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run Passes 2-4 over an already-materialized DNSE snapshot (Pass 1), plus an optional
    Pass 5 DNSE quality sentinel.

    Returns ``(evidence_artifact, projected_snapshot)``. Never mutates ``dnse_snapshot``.
    ``max_recovery_candidates`` bounds how many DNSE-missing tickers get a live VCI/KBS
    request -- for tests and bounded diagnostic probes only; production callers must
    leave it ``None`` (no ticker-specific/partial-universe branch in the real Daily path).

    ``sentinel_cohort`` (see ``select_sentinel_cohort``), when given, is a small deterministic
    ticker list independent of Pass 2-4's gap-recovery scope. For each sentinel member DNSE
    already resolved (Pass 2-4 would otherwise never touch it -- see this module's docstring),
    Pass 5 queries VCI/KBS anyway, purely to check whether DNSE's own same-date value agrees.
    A sentinel member DNSE did NOT resolve reuses its existing Pass 3/4 observations -- never
    re-queried twice. ``evidence["dnse_quality_sentinel"]`` carries the resulting
    ``classify_dnse_provider_health`` verdict, always -- this function never raises on a
    degraded verdict itself; it always returns real evidence/projected artifacts so a caller
    can persist them. A caller that must fail closed on ``DNSE_BROAD_STALE_OR_INCOMPLETE_EOD``
    calls ``assert_dnse_quality_acceptable(evidence)`` explicitly, AFTER persisting both
    artifacts. ``sentinel_cohort=None`` (the default) runs no Pass 5 at all and preserves this
    function's pre-sentinel behavior exactly.
    """
    fetch = fetch_single_source or _default_fetch_single_source()
    delay = request_delay if request_delay is not None else _default_request_delay()

    dnse_records = dnse_snapshot.get("records")
    if not isinstance(dnse_records, Mapping):
        raise MultiSourceResolverError("DNSE_SNAPSHOT_RECORDS_MISSING")
    if dnse_snapshot.get("resolved_completed_session") != target_session:
        raise MultiSourceResolverError("DNSE_SNAPSHOT_SESSION_MISMATCH")

    end_date = datetime.fromisoformat(target_session).date()
    start_date = end_date - timedelta(days=recovery_window_days)
    window = {"start": start_date.isoformat(), "end": end_date.isoformat()}

    all_tickers = sorted(dnse_records)
    all_dnse_missing_tickers = [
        t for t in all_tickers if dnse_records[t].get("disposition") != DNSE_EXACT_SESSION_DISPOSITION
    ]
    all_dnse_missing_set = set(all_dnse_missing_tickers)
    missing_tickers = (
        all_dnse_missing_tickers[:max_recovery_candidates]
        if max_recovery_candidates is not None
        else all_dnse_missing_tickers
    )
    missing_set = set(missing_tickers)
    # Tickers this run is deliberately NOT attempting recovery for, distinct from tickers
    # DNSE already resolved -- only possible when max_recovery_candidates bounds a
    # diagnostic/test probe; always empty in production (max_recovery_candidates=None).
    excluded_by_bound_set = all_dnse_missing_set - missing_set

    # Sentinel members DNSE already resolved -- these get a genuine Pass 5 VCI/KBS query below
    # instead of the usual "DNSE already resolved, never queried" stub. A sentinel member DNSE
    # did NOT resolve needs no special handling here: it is already in missing_set and gets a
    # real Pass 3/4 attempt like any other gap.
    sentinel_set = set(sentinel_cohort or [])
    sentinel_dnse_exact_targets = {t for t in sentinel_set if t in all_tickers} - missing_set - excluded_by_bound_set

    per_ticker_observations: dict[str, list[dict[str, Any]]] = {t: [] for t in all_tickers}

    # DNSE observation (Pass 1) projected into the shared contract shape for every ticker.
    for ticker in all_tickers:
        dnse_record = dnse_records[ticker]
        dnse_disposition = dnse_record.get("disposition")
        if dnse_disposition == DNSE_EXACT_SESSION_DISPOSITION:
            row = next((o for o in (dnse_record.get("observations") or []) if o.get("session") == target_session), None)
            native = {"open": row.get("open"), "high": row.get("high"), "low": row.get("low"),
                      "close": row.get("close"), "volume": row.get("volume")} if row else None
            status = STATUS_EXACT_SESSION_OBSERVED if native else STATUS_MALFORMED
        elif dnse_disposition == "SESSION_MISSING":
            status, native = STATUS_SESSION_MISSING, None
        elif dnse_disposition == "PROVIDER_REJECTED":
            status, native = STATUS_SOURCE_REJECTED, None
        elif dnse_disposition == "TRANSPORT_FAILED":
            status, native = STATUS_TRANSPORT_FAILED, None
        elif dnse_disposition == "MALFORMED":
            status, native = STATUS_MALFORMED, None
        else:
            status, native = STATUS_NOT_APPLICABLE, None
        per_ticker_observations[ticker].append(build_source_observation(
            ticker=ticker, requested_session=target_session, observed_session=target_session if native else None,
            source="DNSE", provider_interface=PROVIDER_INTERFACE["DNSE"], retrieved_at=dnse_snapshot.get("requested_at") or requested_at,
            status=status, native=native, unit_scale=NATIVE_PRICE_UNIT_SCALE["DNSE"],
            price_basis="CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED",
            provenance={"endpoint": dnse_record.get("provider_endpoint"), "request": dnse_record.get("request")},
            payload_hash=dnse_record.get("payload_hash"), reason_code=dnse_record.get("reason"),
        ))
        # Every non-DNSE source gets an explicit NOT_APPLICABLE stub for a DNSE-resolved
        # ticker -- full per-source accounting, never a silent gap in the evidence record.
        # A ticker DNSE did NOT resolve but that this bounded run excluded via
        # max_recovery_candidates gets its own honest reason code -- never conflated with
        # "DNSE already resolved" (that conflation previously corrupted dnse_exact_session_count
        # under a bounded probe; see the accompanying test).
        if ticker in excluded_by_bound_set:
            for source in RECOVERY_SOURCES:
                per_ticker_observations[ticker].append(build_source_observation(
                    ticker=ticker, requested_session=target_session, observed_session=None,
                    source=source, provider_interface=PROVIDER_INTERFACE[source], retrieved_at=requested_at,
                    status=STATUS_NOT_APPLICABLE, reason_code="NOT_ATTEMPTED_BOUNDED_RECOVERY_LIMIT",
                ))
        elif ticker not in missing_set and ticker not in sentinel_dnse_exact_targets:
            for source in RECOVERY_SOURCES:
                per_ticker_observations[ticker].append(build_source_observation(
                    ticker=ticker, requested_session=target_session, observed_session=None,
                    source=source, provider_interface=PROVIDER_INTERFACE[source], retrieved_at=requested_at,
                    status=STATUS_NOT_APPLICABLE, reason_code="NOT_ATTEMPTED_DNSE_ALREADY_RESOLVED",
                ))
        # ticker in sentinel_dnse_exact_targets: no stub -- Pass 5 below genuinely queries it.

    # Pass 3: selected-primary recovery for DNSE-missing tickers.
    still_missing = list(missing_tickers)
    recovery_attempts = {source: 0 for source in RECOVERY_SOURCES}
    recovery_successes = {source: 0 for source in RECOVERY_SOURCES}
    primary_source, fallback_source = MARKET_WIDE_RECOVERY_SOURCE_ORDER
    if recovery_runtime_guard is not None:
        recovery_runtime_guard.set_plan(
            stage=f"DNSE_GAP_RECOVERY_{primary_source}_FIRST",
            remaining_by_source={primary_source: len(still_missing), fallback_source: 0},
        )
        recovery_runtime_guard.set_primary_failover(primary_source, fallback_source)
    for pass_index, source in enumerate(MARKET_WIDE_RECOVERY_SOURCE_ORDER):
        next_round: list[str] = []
        for ticker in still_missing:
            recovery_attempts[source] += 1
            outcome = fetch(ticker, source, window["start"], window["end"])
            status, reason, native, lineage = _classify_recovery_outcome(
                outcome=outcome, source=source, ticker=ticker, target_session=target_session,
            )
            if recovery_runtime_guard is not None and source == primary_source:
                recovery_runtime_guard.record_target_session_result(
                    source=primary_source, usable=status == STATUS_EXACT_SESSION_OBSERVED,
                )
            payload_hash = _lineage_hash_for_session(lineage, target_session) if lineage else None
            per_ticker_observations[ticker].append(build_source_observation(
                ticker=ticker, requested_session=target_session,
                observed_session=target_session if status == STATUS_EXACT_SESSION_OBSERVED else None,
                source=source, provider_interface=PROVIDER_INTERFACE[source], retrieved_at=requested_at,
                status=status, native=native, unit_scale=NATIVE_PRICE_UNIT_SCALE[source],
                price_basis="CURRENT_DESCRIPTIVE_NOT_PROMOTED_RAW_AS_TRADED",
                provenance={"endpoint": PROVIDER_ENDPOINT[source], "request": window},
                payload_hash=payload_hash, reason_code=reason,
            ))
            if status == STATUS_EXACT_SESSION_OBSERVED:
                recovery_successes[source] += 1
            else:
                next_round.append(ticker)
            if ticker != still_missing[-1] or pass_index < len(MARKET_WIDE_RECOVERY_SOURCE_ORDER) - 1:
                sleep_fn(delay)
        # Every ticker not carried into the next round gets an explicit NOT_APPLICABLE
        # stub for the remaining, un-attempted recovery source(s).
        resolved_this_round = set(still_missing) - set(next_round)
        for remaining_source in MARKET_WIDE_RECOVERY_SOURCE_ORDER[pass_index + 1:]:
            for ticker in resolved_this_round:
                per_ticker_observations[ticker].append(build_source_observation(
                    ticker=ticker, requested_session=target_session, observed_session=None,
                    source=remaining_source, provider_interface=PROVIDER_INTERFACE[remaining_source], retrieved_at=requested_at,
                    status=STATUS_NOT_APPLICABLE, reason_code=f"NOT_ATTEMPTED_RESOLVED_BY_{source}",
                ))
        still_missing = next_round
        if recovery_runtime_guard is not None and source == primary_source:
            # The fallback is deliberately planned only after the primary's actual missing/failed outcomes are
            # known.  This is both the recovery topology and the runtime forecast boundary.
            recovery_runtime_guard.set_plan(
                stage=f"DNSE_GAP_RECOVERY_{fallback_source}_FAILOVER",
                remaining_by_source={primary_source: 0, fallback_source: len(still_missing)},
            )
            recovery_runtime_guard.clear_conditional_failover()

    # Pass 5: DNSE quality sentinel. Independent of Pass 2-4's gap-recovery scope -- queries
    # VCI/KBS for sentinel members DNSE already resolved, purely to check same-date agreement.
    sentinel_targets_needing_fetch = sorted(sentinel_dnse_exact_targets)
    if recovery_runtime_guard is not None:
        recovery_runtime_guard.clear_conditional_failover()
        recovery_runtime_guard.set_plan(
            stage="DNSE_HEALTH_SENTINEL_DUAL_SOURCE",
            remaining_by_source={source: len(sentinel_targets_needing_fetch) for source in SENTINEL_SOURCES},
        )
    for ticker in sentinel_targets_needing_fetch:
        for source in SENTINEL_SOURCES:
            outcome = fetch(ticker, source, window["start"], window["end"])
            status, reason, native, lineage = _classify_recovery_outcome(
                outcome=outcome, source=source, ticker=ticker, target_session=target_session,
            )
            payload_hash = _lineage_hash_for_session(lineage, target_session) if lineage else None
            per_ticker_observations[ticker].append(build_source_observation(
                ticker=ticker, requested_session=target_session,
                observed_session=target_session if status == STATUS_EXACT_SESSION_OBSERVED else None,
                source=source, provider_interface=PROVIDER_INTERFACE[source], retrieved_at=requested_at,
                status=status, native=native, unit_scale=NATIVE_PRICE_UNIT_SCALE[source],
                price_basis="CURRENT_DESCRIPTIVE_NOT_PROMOTED_RAW_AS_TRADED",
                provenance={"endpoint": PROVIDER_ENDPOINT[source], "request": window, "purpose": "DNSE_QUALITY_SENTINEL"},
                payload_hash=payload_hash, reason_code=reason,
            ))
            sleep_fn(delay)
    if recovery_runtime_guard is not None:
        recovery_runtime_guard.set_plan(stage="INITIAL_RESOLUTION_COMPLETE", remaining_by_source={})

    resolutions = {ticker: resolve_ticker(ticker, per_ticker_observations[ticker]) for ticker in all_tickers}

    resolution_counts = {
        RESOLUTION_CORROBORATED: 0, "RESOLVED_SINGLE_SOURCE_RESEARCH": 0,
        RESOLUTION_CONFLICT: 0, RESOLUTION_CORROBORATED_NON_DNSE: 0, RESOLUTION_ALL_MISSING: 0,
    }
    for record in resolutions.values():
        resolution_counts[record["resolution"]] += 1

    dnse_quality_sentinel = None
    if sentinel_cohort is not None:
        sentinel_observations = {t: per_ticker_observations[t] for t in sentinel_set if t in per_ticker_observations}
        health = classify_dnse_provider_health(sentinel_observations)
        dnse_quality_sentinel = {
            "cohort_version": SENTINEL_COHORT_VERSION,
            "cohort_size": len(sentinel_set),
            "cohort_tickers": sorted(sentinel_set),
            "health": health,
        }
        # No raise here: this function's job is to resolve and honestly report evidence, never
        # to decide whether a degraded verdict should stop Daily -- that policy decision (and
        # persisting this real, hard-won evidence regardless of the verdict) belongs to the
        # caller, exactly like canonical_post_close_pipeline.py's own MIN_EXACT_SESSION_COVERAGE_
        # RATIO gate already lives one layer up from acquisition. See
        # assert_dnse_quality_acceptable below -- callers that must fail closed on
        # DNSE_BROAD_STALE_OR_INCOMPLETE_EOD call it explicitly, AFTER persisting evidence/
        # projected, never silently inside this function discarding real live-call results.

    evidence: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": "multi_source_exact_session_market_evidence/v1",
        "artifact_type": ARTIFACT_TYPE,
        "is_actionable_for_execution": False,
        "pit_backtest_eligible": False,
        "liquidity_sizing_authority": "BLOCKED",
        "valuation_scope": "CURRENT_DESCRIPTIVE_ONLY",
        "target_session": target_session,
        "requested_at": requested_at,
        "candidate_count": len(all_tickers),
        "dnse_source_snapshot_identity": dnse_snapshot.get("snapshot_identity"),
        "dnse_exact_session_count": len(all_tickers) - len(all_dnse_missing_tickers),
        "dnse_missing_total_count": len(all_dnse_missing_tickers),
        "dnse_missing_excluded_by_recovery_bound_count": len(excluded_by_bound_set),
        "recovery_window": window,
        "recovery_attempts": recovery_attempts,
        "recovery_successes": recovery_successes,
        "resolution_counts": resolution_counts,
        "resolved_exact_session_count": sum(1 for r in resolutions.values() if r["resolution"] != RESOLUTION_ALL_MISSING),
        "cross_source_conflict_count": sum(1 for r in resolutions.values() if r["cross_source_conflict"]),
        "dnse_quality_sentinel": dnse_quality_sentinel,
        "recovery_throughput": recovery_runtime_guard.diagnostic() if recovery_runtime_guard is not None else None,
        "authority_boundary": {
            "RAW_AS_TRADED": "NOT_PROMOTED", "HISTORICAL_PIT": "BLOCKED",
            "runtime_database_mutated": False,
            "cross_provider_volume_synthesis": "NEVER_PERFORMED",
        },
        "records": {
            ticker: {
                "observations": per_ticker_observations[ticker],
                "resolution": resolutions[ticker],
            }
            for ticker in all_tickers
        },
    }
    evidence["evidence_sha256"] = stable_id(evidence)
    evidence["evidence_identity"] = f"multi_source_exact_session_market_evidence:{evidence['evidence_sha256']}"

    projected = _project_to_p3f9_shape(
        dnse_snapshot=dnse_snapshot, target_session=target_session, resolutions=resolutions,
        per_ticker_observations=per_ticker_observations, requested_at=requested_at,
    )
    return evidence, projected


def _project_to_p3f9_shape(
    *, dnse_snapshot: Mapping[str, Any], target_session: str, resolutions: Mapping[str, Mapping[str, Any]],
    per_ticker_observations: Mapping[str, list[Mapping[str, Any]]], requested_at: str,
) -> dict[str, Any]:
    """Deterministic adapter/projection: same shape/contract_version every existing
    Level-2 consumer already reads (mva_exact_session_snapshot's own
    "p3f9_exact_session_mva_snapshot/v2"), enriched with recovered records. Never
    duplicates the disposition/session-membership formulas -- reuses this module's own
    already-computed resolutions.
    """
    import copy

    projected = copy.deepcopy(dict(dnse_snapshot))
    records = projected["records"]
    lookback_sessions = 20

    for ticker, resolution in resolutions.items():
        if resolution["resolved_source"] is None:
            # No justified value: either RESOLUTION_ALL_MISSING (no source at all -- DNSE's own
            # record, whatever it independently is, already carries a non-retained disposition,
            # so leaving it unchanged is already correct) or, once DNSE is quarantined for a
            # broadly degraded session (resolve_ticker_degraded_dnse), a SOURCE_CONFLICT between
            # VCI and KBS themselves with no DNSE fallback -- see docs brief P0 DEFECT B. In the
            # quarantine case DNSE's ORIGINAL disposition here is still EXACT_SESSION_RETAINED
            # (that is WHY it was quarantined at all), so it must be explicitly downgraded --
            # never left standing as a retained bar this session no longer trusts as final -- and
            # the target session's own now-untrusted DNSE row is stripped from `observations`
            # (older lookback rows, if any, are preserved unchanged). DNSE's full observation is
            # never lost: it remains verbatim in the caller's evidence["records"][ticker]
            # ["observations"] artifact throughout -- this function only ever builds the
            # DOWNSTREAM PROJECTION, never the evidence artifact itself.
            quarantined = bool(resolution.get("resolved_under_quarantine"))
            if quarantined:
                original = records[ticker]
                records[ticker] = {
                    **original,
                    "disposition": "SESSION_MISSING",
                    "observations": [
                        row for row in (original.get("observations") or [])
                        if row.get("session") != target_session
                    ],
                }
            records[ticker]["multi_source_recovery_attempted"] = list(RECOVERY_SOURCES)
            records[ticker]["multi_source_recovery_result"] = (
                "DEGRADED_DNSE_QUARANTINED_UNRESOLVED_SOURCE_CONFLICT" if quarantined
                else "ALL_SOURCES_MISSING"
            )
            records[ticker]["multi_source_resolution_outcome"] = resolution["resolution"]
            records[ticker]["cross_source_conflict"] = resolution["cross_source_conflict"]
            records[ticker]["dnse_observation_overridden"] = quarantined
            continue
        source = resolution["resolved_source"]
        is_sentinel_override = resolution["resolution"] == RESOLUTION_CORROBORATED_NON_DNSE
        resolved_under_quarantine = bool(resolution.get("resolved_under_quarantine"))
        if source == "DNSE":
            records[ticker]["multi_source_recovery_result"] = (
                # DNSE, VCI, and KBS were all observed (sentinel ran) but there was no clean
                # VCI==KBS pair to corroborate against -- conflict stays visible, DNSE's own
                # bar is not promoted over an unresolved disagreement, but no source disproved
                # it either, so DNSE's descriptive value is kept as the projected row. Only
                # reachable when NOT quarantined (resolve_ticker_degraded_dnse never returns
                # source="DNSE" -- see its own docstring: DNSE is never a resolution candidate
                # once quarantined).
                "DNSE_RESOLVED_SENTINEL_CONFLICT_UNRESOLVED" if resolution["cross_source_conflict"]
                else "DNSE_RESOLVED_NO_RECOVERY_NEEDED"
            )
            records[ticker]["multi_source_resolution_outcome"] = resolution["resolution"]
            records[ticker]["cross_source_conflict"] = resolution["cross_source_conflict"]
            continue
        # A recovery source (VCI/KBS) supplied the target-session bar -- because DNSE was missing
        # it (ordinary gap recovery), because the DNSE quality sentinel found DNSE's own bar
        # conflicting with a corroborated VCI==KBS pair (is_sentinel_override), or because DNSE is
        # quarantined for this degraded session (resolved_under_quarantine, single-source or
        # corroborated-non-DNSE alike). Either way the DNSE observation, if any, remains untouched
        # in this ticker's full evidence record (evidence["records"][ticker]["observations"]) --
        # never erased, only outranked.
        winning = next(
            o for o in per_ticker_observations[ticker]
            if o["source"] == source and o["status"] == STATUS_EXACT_SESSION_OBSERVED
        )
        native = winning["native"]
        if is_sentinel_override:
            recovery_result = "CORROBORATED_NON_DNSE_CURRENT_RESEARCH_SENTINEL_OVERRIDE"
        elif resolved_under_quarantine:
            recovery_result = f"DEGRADED_DNSE_QUARANTINED_SINGLE_SOURCE_{source}"
        else:
            recovery_result = f"RECOVERED_BY_{source}"
        records[ticker] = {
            "status": "OBSERVED",
            "reason": None,
            "disposition": DNSE_EXACT_SESSION_DISPOSITION,
            "observations": [{
                "session": target_session,
                "open": native["open"], "high": native["high"], "low": native["low"], "close": native["close"],
                "volume": native["volume"],
                "provider": source, "dataset": f"{source}_OHLC_1D",
                "field_identity": {field: f"{source}_QUOTE.{field}" for field in ("open", "high", "low", "close", "volume")},
                "field_representation": {field: f"{source}_NATIVE_SCALE" for field in ("open", "high", "low", "close")},
                "transformation_identity": "vn_stock_pipeline_normalize_native_rescale/v1",
                "price_unit": "SOURCE_PRICE_UNIT_UNDOCUMENTED",
                "request": winning["provenance"].get("request"),
                "retrieved_at": requested_at,
                "price_basis": "CURRENT_DESCRIPTIVE_NOT_PROMOTED_RAW_AS_TRADED",
                "qualification": "CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY",
            }],
            "payload_hash": winning.get("payload_hash"),
            "request": winning["provenance"].get("request"),
            "provider_endpoint": winning["provenance"].get("endpoint"),
            "multi_source_recovery_result": recovery_result,
            "multi_source_resolution_outcome": resolution["resolution"],
            "cross_source_conflict": resolution["cross_source_conflict"],
            "dnse_observation_overridden": is_sentinel_override or resolved_under_quarantine,
        }

    disposition_counts = {
        "EXACT_SESSION_RETAINED": 0, "SESSION_MISSING": 0, "MALFORMED": 0,
        "PROVIDER_REJECTED": 0, "TRANSPORT_FAILED": 0, "INSTRUMENT_UNRESOLVED": 0,
        "NOT_APPLICABLE": 0, "NOT_ATTEMPTED": 0,
    }
    for record in records.values():
        disp = record.get("disposition")
        if disp in disposition_counts:
            disposition_counts[disp] += 1

    session_counts: dict[str, int] = {}
    for record in records.values():
        for row in record.get("observations") or []:
            if row["session"] <= target_session:
                session_counts[row["session"]] = session_counts.get(row["session"], 0) + 1
    sessions = list(reversed(sorted(session_counts, reverse=True)[:lookback_sessions]))
    complete = sum(
        record.get("status") == "OBSERVED"
        and all(any(row["session"] == s for row in (record.get("observations") or [])) for s in sessions)
        for record in records.values()
    ) if len(sessions) == lookback_sessions else 0

    observed = disposition_counts["EXACT_SESSION_RETAINED"]
    candidate_count = projected.get("candidate_count") or len(records)
    projected.update(
        exact_session_observed_count=observed,
        empirical_20_session_complete_count=complete,
        missing_current_session_count=candidate_count - observed,
        disposition_counts=disposition_counts,
        sessions=sessions,
        multi_source_resolution_authority="MULTI_SOURCE_EXACT_SESSION_MARKET_EVIDENCE_RESOLVER_V1",
    )
    projected.pop("snapshot_sha256", None)
    projected.pop("snapshot_identity", None)
    projected["snapshot_sha256"] = stable_id(projected)
    projected["snapshot_identity"] = f"p3f9_exact_session_snapshot:{projected['snapshot_sha256']}"
    return projected


# ---------------------------------------------------------------------------
# DEGRADED_PROVIDER_RECOVERY_MODE -- product-critical Daily auto-recovery (see
# WHEN_DNSE_DEGRADED_POLICY above). Corrective fix for the P0 defect where a broadly
# degraded DNSE day required an operator to explicitly re-run with an expanded scope:
# the owner's normal `.\stocklookup.ps1 daily` / `--session` command must handle this
# internally, in the same foreground invocation, with no second command.
# ---------------------------------------------------------------------------
DEGRADED_RECOVERY_NOT_TRIGGERED = "NOT_TRIGGERED"
DEGRADED_RECOVERY_COMPLETED = "COMPLETED"


def _memoizing_fetch(
    fetch_single_source: Callable[..., Any], *, delay: float, sleep_fn: Callable[[float], None],
    runtime_guard: _DailyRecoveryRuntimeGuard | None = None,
) -> Callable[..., Any]:
    """Wrap ``fetch_single_source`` so a (ticker, source) pair already fetched THIS RUN is never
    requested twice, and so the pacing delay is only ever spent on a genuine network call.

    ``resolve_exact_session_with_autorecovery`` may call resolve_multi_source_exact_session_
    snapshot a second time over an expanded, overlapping candidate set (see its own docstring).
    Passing this shared cache as both calls' fetch_single_source is what makes "Do NOT re-query a
    source/ticker observation already retained for this run" (a hard milestone requirement, not
    an optimization) hold across passes/calls rather than just within one. Both calls are given
    sleep_fn=lambda s: None (their own internal pacing becomes a no-op) so the real REQUEST_DELAY
    is spent exactly once per genuine fetch, here, rather than once per call that merely asks for
    an already-cached pair -- otherwise a fully-cached second pass would still burn the entire
    original pacing budget (thousands of seconds on a real ~1683-candidate universe) for zero new
    network activity.
    """
    cache: dict[tuple[str, str], Any] = {}

    def wrapped(ticker: str, source: str, start: str, end: str) -> Any:
        key = (ticker, source)
        if key in cache:
            if runtime_guard is not None:
                runtime_guard.cache_hit(ticker, source)
            return cache[key]
        started = time.monotonic()
        result = fetch_single_source(ticker, source, start, end)
        elapsed = time.monotonic() - started
        cache[key] = result
        if runtime_guard is not None:
            runtime_guard.observe(ticker=ticker, source=source, outcome=result, elapsed_seconds=elapsed)
        sleep_fn(delay)
        return result

    return wrapped


def _no_sleep(_seconds: float) -> None:
    return None


def _has_live_observation(observations: Sequence[Mapping[str, Any]], source: str) -> bool:
    """Was this source actually queried, rather than represented by a bookkeeping stub?"""
    return any(
        observation.get("source") == source and observation.get("status") != STATUS_NOT_APPLICABLE
        for observation in observations
    )


def _replace_source_stub(observations: list[dict[str, Any]], *, source: str,
                         replacement: Mapping[str, Any]) -> None:
    """Replace only an explicit NOT_APPLICABLE bookkeeping row, never a retained result."""
    observations[:] = [
        observation for observation in observations
        if not (observation.get("source") == source and observation.get("status") == STATUS_NOT_APPLICABLE)
    ]
    observations.append(dict(replacement))


def _mark_fallback_not_needed_after_primary(
    observations: list[dict[str, Any]], *, primary: str, fallback: str,
) -> None:
    """Keep full source accounting honest when the primary supplied the usable bar."""
    for observation in observations:
        if observation.get("source") == fallback and observation.get("status") == STATUS_NOT_APPLICABLE:
            observation["reason_code"] = f"NOT_ATTEMPTED_{primary}_RECOVERED_DEGRADED_DNSE"


def _marketwide_degraded_primary_first_recovery(
    *, evidence: dict[str, Any], dnse_snapshot: Mapping[str, Any], target_session: str,
    requested_at: str, original_sentinel_cohort: Sequence[str], fetch: Callable[..., Any],
    runtime_guard: _DailyRecoveryRuntimeGuard,
) -> dict[str, Any]:
    """Recover DNSE-exact names once a small sentinel proves broad degradation.

    The sentinel itself remains deliberately VCI+KBS. Every other DNSE-exact name receives the
    selected primary first and receives its fallback only when the primary is missing, failed, or
    unusable for the target session. This is intentionally not implemented as a giant second
    sentinel, because a sentinel is a health-classification tool whereas this is market-wide
    recovery.
    """
    dnse_records = dnse_snapshot.get("records") or {}
    all_dnse_exact_tickers = {
        ticker for ticker, record in dnse_records.items()
        if record.get("disposition") == DNSE_EXACT_SESSION_DISPOSITION
    }
    original_sentinel_set = set(original_sentinel_cohort)
    expanded_tickers = sorted(all_dnse_exact_tickers - original_sentinel_set)
    window = evidence["recovery_window"]
    expanded_attempts = {source: 0 for source in RECOVERY_SOURCES}
    primary_source, fallback_source = MARKET_WIDE_RECOVERY_SOURCE_ORDER
    primary_missing: list[str] = []

    primary_targets = [
        ticker for ticker in expanded_tickers
        if not _has_live_observation(evidence["records"][ticker]["observations"], primary_source)
    ]
    runtime_guard.set_plan(
        stage=f"DEGRADED_DNSE_MARKET_WIDE_{primary_source}_FIRST",
        remaining_by_source={primary_source: len(primary_targets), fallback_source: 0},
    )
    runtime_guard.set_primary_failover(primary_source, fallback_source)
    for ticker in primary_targets:
        outcome = fetch(ticker, primary_source, window["start"], window["end"])
        expanded_attempts[primary_source] += 1
        status, reason, native, lineage = _classify_recovery_outcome(
            outcome=outcome, source=primary_source, ticker=ticker, target_session=target_session,
        )
        runtime_guard.record_target_session_result(
            source=primary_source, usable=status == STATUS_EXACT_SESSION_OBSERVED,
        )
        payload_hash = _lineage_hash_for_session(lineage, target_session) if lineage else None
        observations = evidence["records"][ticker]["observations"]
        _replace_source_stub(observations, source=primary_source, replacement=build_source_observation(
            ticker=ticker, requested_session=target_session,
            observed_session=target_session if status == STATUS_EXACT_SESSION_OBSERVED else None,
            source=primary_source, provider_interface=PROVIDER_INTERFACE[primary_source], retrieved_at=requested_at,
            status=status, native=native, unit_scale=NATIVE_PRICE_UNIT_SCALE[primary_source],
            price_basis="CURRENT_DESCRIPTIVE_NOT_PROMOTED_RAW_AS_TRADED",
            provenance={"endpoint": PROVIDER_ENDPOINT[primary_source], "request": window,
                        "purpose": f"DEGRADED_DNSE_MARKET_WIDE_{primary_source}_FIRST"},
            payload_hash=payload_hash, reason_code=reason,
        ))
        if status == STATUS_EXACT_SESSION_OBSERVED:
            _mark_fallback_not_needed_after_primary(
                observations, primary=primary_source, fallback=fallback_source,
            )
        else:
            primary_missing.append(ticker)

    runtime_guard.set_plan(
        stage=f"DEGRADED_DNSE_MARKET_WIDE_{fallback_source}_FAILOVER",
        remaining_by_source={primary_source: 0, fallback_source: len(primary_missing)},
    )
    runtime_guard.clear_conditional_failover()
    for ticker in primary_missing:
        outcome = fetch(ticker, fallback_source, window["start"], window["end"])
        expanded_attempts[fallback_source] += 1
        status, reason, native, lineage = _classify_recovery_outcome(
            outcome=outcome, source=fallback_source, ticker=ticker, target_session=target_session,
        )
        payload_hash = _lineage_hash_for_session(lineage, target_session) if lineage else None
        observations = evidence["records"][ticker]["observations"]
        _replace_source_stub(observations, source=fallback_source, replacement=build_source_observation(
            ticker=ticker, requested_session=target_session,
            observed_session=target_session if status == STATUS_EXACT_SESSION_OBSERVED else None,
            source=fallback_source, provider_interface=PROVIDER_INTERFACE[fallback_source], retrieved_at=requested_at,
            status=status, native=native, unit_scale=NATIVE_PRICE_UNIT_SCALE[fallback_source],
            price_basis="CURRENT_DESCRIPTIVE_NOT_PROMOTED_RAW_AS_TRADED",
            provenance={"endpoint": PROVIDER_ENDPOINT[fallback_source], "request": window,
                        "purpose": f"DEGRADED_DNSE_MARKET_WIDE_{fallback_source}_FAILOVER"},
            payload_hash=payload_hash, reason_code=reason,
        ))

    runtime_guard.set_plan(stage="DEGRADED_DNSE_MARKET_WIDE_RECOVERY_COMPLETE", remaining_by_source={})
    return {
        "mode": DEGRADED_RECOVERY_COMPLETED,
        "topology": "SMALL_SENTINEL_VCI_PLUS_KBS_THEN_MARKET_WIDE_KBS_FIRST_VCI_ON_KBS_MISSING_FAILED_OR_UNUSABLE",
        "expanded_ticker_count": len(expanded_tickers),
        "expanded_recovery_attempts": expanded_attempts,
        "expanded_primary_source": primary_source,
        "expanded_fallback_source": fallback_source,
        "expanded_primary_recovered_count": len(expanded_tickers) - len(primary_missing),
        "expanded_fallback_candidate_count": len(primary_missing),
    }


def resolve_exact_session_with_autorecovery(
    *,
    dnse_snapshot: Mapping[str, Any],
    target_session: str,
    requested_at: str,
    sentinel_cohort: Sequence[str],
    recovery_window_days: int = DEFAULT_RECOVERY_WINDOW_CALENDAR_DAYS,
    fetch_single_source: Callable[..., Any] | None = None,
    request_delay: float | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    max_recovery_candidates: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Product-critical Daily entrypoint (see daily_session_level2_package.
    ensure_exact_session_snapshot): Passes 1-5 exactly as resolve_multi_source_exact_session_
    snapshot, automatically followed by Pass 6 DEGRADED_PROVIDER_RECOVERY_MODE in the SAME
    invocation whenever Pass 5's sentinel finds DNSE_BROAD_STALE_OR_INCOMPLETE_EOD -- no operator
    flag, no second command.

    HEALTHY DAY (or no sentinel_cohort correlation to broad degradation): behaves exactly like a
    single resolve_multi_source_exact_session_snapshot call -- the cheap path, no broader VCI/KBS
    fetch, matching WHEN_DNSE_HEALTHY_POLICY.

    DEGRADED DAY: keeps the small VCI+KBS sentinel that produced the health verdict, then recovers
    every other DNSE-exact ticker through the selected primary source. Its fallback is attempted
    only when that primary result is missing, failed, or unusable for the target session -- no
    full-universe dual-source sentinel.
    A shared memoizing fetch cache (_memoizing_fetch) still guarantees a (ticker, source) pair is
    never re-requested within this invocation. Every DNSE-exact ticker's resolution is then
    quarantine-re-resolved via
    multi_source_market_evidence_contract.resolve_ticker_degraded_dnse -- DNSE's own value is
    never again a resolution candidate for this session, regardless of whether secondary
    corroboration is complete, partial, conflicting, or entirely absent (P0 DEFECT B); DNSE's
    observation itself is never dropped from the evidence artifact.

    Returns (evidence, projected) exactly like resolve_multi_source_exact_session_snapshot, with
    an added top-level ``degraded_provider_recovery`` block on both:
        {"mode": "NOT_TRIGGERED" | "COMPLETED", "expanded_ticker_count": int,
         "expanded_recovery_attempts": {"VCI": int, "KBS": int}}
    and ``projected["dnse_provider_health_state"]`` mirroring the sentinel's own health state (or
    None when no sentinel ran), so a canonical snapshot is self-describing about whether it was
    ever subject to degraded-provider recovery -- see canonical_post_close_pipeline.
    assert_post_close_eligible's own provider-health reuse check.

    This function never raises on a degraded verdict, and never decides sufficiency -- exactly
    like the function it wraps, it always returns real, honest evidence for the caller to persist;
    coverage sufficiency remains the caller's own, unchanged, MIN_EXACT_SESSION_COVERAGE_RATIO
    gate (docs brief: "Preserve the existing 0.20 coverage threshold").
    """
    real_fetch = fetch_single_source or _default_fetch_single_source()
    delay = request_delay if request_delay is not None else _default_request_delay()
    runtime_guard = _DailyRecoveryRuntimeGuard(request_delay=delay)
    memoized_fetch = _memoizing_fetch(
        real_fetch, delay=delay, sleep_fn=sleep_fn, runtime_guard=runtime_guard,
    )

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse_snapshot, target_session=target_session, requested_at=requested_at,
        recovery_window_days=recovery_window_days, fetch_single_source=memoized_fetch,
        request_delay=0.0, sleep_fn=_no_sleep, max_recovery_candidates=max_recovery_candidates,
        sentinel_cohort=sentinel_cohort, recovery_runtime_guard=runtime_guard,
    )
    sentinel = evidence.get("dnse_quality_sentinel")
    health_state = sentinel["health"]["state"] if sentinel else None

    if health_state != DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD:
        recovery_info = {
            "mode": DEGRADED_RECOVERY_NOT_TRIGGERED,
            "topology": "DNSE_GAPS_KBS_FIRST_VCI_ON_KBS_MISSING_FAILED_OR_UNUSABLE_PLUS_SMALL_VCI_KBS_SENTINEL",
            "expanded_ticker_count": 0,
            "expanded_recovery_attempts": {source: 0 for source in RECOVERY_SOURCES},
        }
        evidence["degraded_provider_recovery"] = recovery_info
        evidence["recovery_throughput"] = runtime_guard.diagnostic()
        evidence["evidence_sha256"] = stable_id({k: v for k, v in evidence.items() if k != "evidence_sha256" and k != "evidence_identity"})
        evidence["evidence_identity"] = f"multi_source_exact_session_market_evidence:{evidence['evidence_sha256']}"
        projected["degraded_provider_recovery"] = dict(recovery_info)
        projected["dnse_provider_health_state"] = health_state
        projected.pop("snapshot_sha256", None)
        projected.pop("snapshot_identity", None)
        projected["snapshot_sha256"] = stable_id(projected)
        projected["snapshot_identity"] = f"p3f9_exact_session_snapshot:{projected['snapshot_sha256']}"
        return evidence, projected

    recovery_info = _marketwide_degraded_primary_first_recovery(
        evidence=evidence, dnse_snapshot=dnse_snapshot, target_session=target_session,
        requested_at=requested_at, original_sentinel_cohort=sentinel_cohort,
        fetch=memoized_fetch, runtime_guard=runtime_guard,
    )
    dnse_records = dnse_snapshot.get("records") or {}

    # P0 DEFECT B: DNSE has been classified provider-wide degraded for this session -- its
    # same-date bar must not remain a resolving source merely because secondary corroboration is
    # incomplete (docs brief). Re-resolve every ticker DNSE ORIGINALLY claimed
    # (EXACT_SESSION_RETAINED) via resolve_ticker_degraded_dnse, which never consults DNSE's own
    # value; a ticker DNSE never claimed keeps its already-DNSE-free gap-recovery resolution.
    # Every DNSE-exact name now has a selected-primary attempt; its fallback is present only for
    # the sentinel or where the primary was unusable, which is the explicit recovery contract.
    quarantined_resolutions: dict[str, dict[str, Any]] = {}
    for ticker, record in evidence["records"].items():
        if dnse_records.get(ticker, {}).get("disposition") == DNSE_EXACT_SESSION_DISPOSITION:
            quarantined_resolutions[ticker] = resolve_ticker_degraded_dnse(ticker, record["observations"])
        else:
            quarantined_resolutions[ticker] = record["resolution"]
    per_ticker_observations = {t: r["observations"] for t, r in evidence["records"].items()}
    projected = _project_to_p3f9_shape(
        dnse_snapshot=dnse_snapshot, target_session=target_session,
        resolutions=quarantined_resolutions, per_ticker_observations=per_ticker_observations,
        requested_at=requested_at,
    )
    for ticker, resolution in quarantined_resolutions.items():
        evidence["records"][ticker]["resolution"] = resolution
    evidence["resolution_counts"] = {
        RESOLUTION_CORROBORATED: 0, "RESOLVED_SINGLE_SOURCE_RESEARCH": 0,
        RESOLUTION_CONFLICT: 0, RESOLUTION_CORROBORATED_NON_DNSE: 0, RESOLUTION_ALL_MISSING: 0,
    }
    for resolution in quarantined_resolutions.values():
        evidence["resolution_counts"][resolution["resolution"]] += 1
    # "Resolved" means a justified value exists (resolved_source is not None) -- for the ORIGINAL,
    # non-quarantined resolve_ticker this is exactly equivalent to "resolution != ALL_MISSING"
    # (resolved_source is None only in that one branch), but under quarantine a SOURCE_CONFLICT
    # between VCI/KBS themselves is ALSO unresolved (resolved_source is None) despite carrying a
    # different resolution label -- see resolve_ticker_degraded_dnse.
    evidence["resolved_exact_session_count"] = sum(
        1 for r in quarantined_resolutions.values() if r["resolved_source"] is not None
    )
    evidence["cross_source_conflict_count"] = sum(
        1 for r in quarantined_resolutions.values() if r["cross_source_conflict"]
    )

    evidence["degraded_provider_recovery"] = recovery_info
    evidence["recovery_throughput"] = runtime_guard.diagnostic()
    evidence["evidence_sha256"] = stable_id({k: v for k, v in evidence.items() if k != "evidence_sha256" and k != "evidence_identity"})
    evidence["evidence_identity"] = f"multi_source_exact_session_market_evidence:{evidence['evidence_sha256']}"
    projected["degraded_provider_recovery"] = dict(recovery_info)
    projected["dnse_provider_health_state"] = evidence["dnse_quality_sentinel"]["health"]["state"]
    projected.pop("snapshot_sha256", None)
    projected.pop("snapshot_identity", None)
    projected["snapshot_sha256"] = stable_id(projected)
    projected["snapshot_identity"] = f"p3f9_exact_session_snapshot:{projected['snapshot_sha256']}"
    return evidence, projected
