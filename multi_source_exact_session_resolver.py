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
    PASS 3  VCI recovery for exactly those candidates, one bounded sequential request per
            ticker (vn_stock_pipeline.fetch_single_source, reused unmodified -- same
            retry budget, same circuit breaker, same REQUEST_DELAY pacing already proven
            safe for this provider family; see docs/DECISIONS.md
            MARKET_WIDE_ENRICHMENT_AND_CANONICALIZATION_V1 = PAUSED_RATE_LIMIT_CONSTRAINED).
            No concurrency: this repository has zero evidence VCI/KBS tolerate concurrent
            access, so Pass 3/4 stay exactly as sequential/paced as vn_stock_pipeline.py's
            own existing cmd_backfill/cmd_update commands.
    PASS 4  KBS recovery only for candidates still missing after Pass 3.

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
)

DNSE_EXACT_SESSION_DISPOSITION = "EXACT_SESSION_RETAINED"
RECOVERY_SOURCES = ("VCI", "KBS")
DEFAULT_RECOVERY_WINDOW_CALENDAR_DAYS = 15
ARTIFACT_TYPE = "MULTI_SOURCE_EXACT_SESSION_MARKET_EVIDENCE"

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
    "second command -- expanding VCI/KBS verification to every DNSE-exact ticker (not just the "
    "small sentinel sample) before the caller's own MIN_EXACT_SESSION_COVERAGE_RATIO gate makes "
    "the final accept/reject decision over the fully-resolved snapshot."
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

    # Pass 3: VCI recovery for DNSE-missing tickers.
    still_missing = list(missing_tickers)
    recovery_attempts = {"VCI": 0, "KBS": 0}
    recovery_successes = {"VCI": 0, "KBS": 0}
    for pass_index, source in enumerate(RECOVERY_SOURCES):
        next_round: list[str] = []
        for ticker in still_missing:
            recovery_attempts[source] += 1
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
                provenance={"endpoint": PROVIDER_ENDPOINT[source], "request": window},
                payload_hash=payload_hash, reason_code=reason,
            ))
            if status == STATUS_EXACT_SESSION_OBSERVED:
                recovery_successes[source] += 1
            else:
                next_round.append(ticker)
            if ticker != still_missing[-1] or pass_index < len(RECOVERY_SOURCES) - 1:
                sleep_fn(delay)
        # Every ticker not carried into the next round gets an explicit NOT_APPLICABLE
        # stub for the remaining, un-attempted recovery source(s).
        resolved_this_round = set(still_missing) - set(next_round)
        for remaining_source in RECOVERY_SOURCES[pass_index + 1:]:
            for ticker in resolved_this_round:
                per_ticker_observations[ticker].append(build_source_observation(
                    ticker=ticker, requested_session=target_session, observed_session=None,
                    source=remaining_source, provider_interface=PROVIDER_INTERFACE[remaining_source], retrieved_at=requested_at,
                    status=STATUS_NOT_APPLICABLE, reason_code=f"NOT_ATTEMPTED_RESOLVED_BY_{source}",
                ))
        still_missing = next_round

    # Pass 5: DNSE quality sentinel. Independent of Pass 2-4's gap-recovery scope -- queries
    # VCI/KBS for sentinel members DNSE already resolved, purely to check same-date agreement.
    sentinel_targets_needing_fetch = sorted(sentinel_dnse_exact_targets)
    for ticker in sentinel_targets_needing_fetch:
        for source in RECOVERY_SOURCES:
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
        if resolution["resolution"] == RESOLUTION_ALL_MISSING:
            # DNSE's own record (whatever it was) stands unchanged; add honest recovery-
            # attempt metadata without touching status/reason/disposition.
            records[ticker]["multi_source_recovery_attempted"] = list(RECOVERY_SOURCES)
            records[ticker]["multi_source_recovery_result"] = "ALL_SOURCES_MISSING"
            continue
        source = resolution["resolved_source"]
        is_sentinel_override = resolution["resolution"] == RESOLUTION_CORROBORATED_NON_DNSE
        if source == "DNSE":
            records[ticker]["multi_source_recovery_result"] = (
                # DNSE, VCI, and KBS were all observed (sentinel ran) but there was no clean
                # VCI==KBS pair to corroborate against -- conflict stays visible, DNSE's own
                # bar is not promoted over an unresolved disagreement, but no source disproved
                # it either, so DNSE's descriptive value is kept as the projected row.
                "DNSE_RESOLVED_SENTINEL_CONFLICT_UNRESOLVED" if resolution["cross_source_conflict"]
                else "DNSE_RESOLVED_NO_RECOVERY_NEEDED"
            )
            records[ticker]["multi_source_resolution_outcome"] = resolution["resolution"]
            records[ticker]["cross_source_conflict"] = resolution["cross_source_conflict"]
            continue
        # A recovery source (VCI/KBS) supplied the target-session bar -- either because DNSE was
        # missing it (ordinary gap recovery) or because the DNSE quality sentinel found DNSE's
        # own bar conflicting with a corroborated VCI==KBS pair (is_sentinel_override). Either
        # way the DNSE observation, if any, remains untouched in this ticker's full evidence
        # record (evidence["records"][ticker]["observations"]) -- never erased, only outranked.
        winning = next(
            o for o in per_ticker_observations[ticker]
            if o["source"] == source and o["status"] == STATUS_EXACT_SESSION_OBSERVED
        )
        native = winning["native"]
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
            "multi_source_recovery_result": (
                "CORROBORATED_NON_DNSE_CURRENT_RESEARCH_SENTINEL_OVERRIDE" if is_sentinel_override
                else f"RECOVERED_BY_{source}"
            ),
            "multi_source_resolution_outcome": resolution["resolution"],
            "cross_source_conflict": resolution["cross_source_conflict"],
            "dnse_observation_overridden": is_sentinel_override,
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
            return cache[key]
        result = fetch_single_source(ticker, source, start, end)
        cache[key] = result
        sleep_fn(delay)
        return result

    return wrapped


def _no_sleep(_seconds: float) -> None:
    return None


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

    DEGRADED DAY: re-resolves with sentinel_cohort expanded to cover EVERY DNSE-exact ticker (not
    just the small diagnostic sample), so no DNSE-exact ticker is left blindly trusted once the
    provider has been classified broadly degraded (see docs brief step 5: "Do NOT automatically
    trust DNSE for non-sentinel names"). A shared memoizing fetch cache (_memoizing_fetch) is used
    for BOTH resolver calls, so every (ticker, source) pair the first call already fetched --
    normal gap recovery and sentinel corroboration alike -- is reused rather than re-queried, and
    only the genuinely new tickers this expansion adds are fetched live (docs brief steps 1-4).

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
    memoized_fetch = _memoizing_fetch(real_fetch, delay=delay, sleep_fn=sleep_fn)

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse_snapshot, target_session=target_session, requested_at=requested_at,
        recovery_window_days=recovery_window_days, fetch_single_source=memoized_fetch,
        request_delay=0.0, sleep_fn=_no_sleep, max_recovery_candidates=max_recovery_candidates,
        sentinel_cohort=sentinel_cohort,
    )
    sentinel = evidence.get("dnse_quality_sentinel")
    health_state = sentinel["health"]["state"] if sentinel else None

    if health_state != DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD:
        recovery_info = {
            "mode": DEGRADED_RECOVERY_NOT_TRIGGERED,
            "expanded_ticker_count": 0,
            "expanded_recovery_attempts": {"VCI": 0, "KBS": 0},
        }
        evidence["degraded_provider_recovery"] = recovery_info
        evidence["evidence_sha256"] = stable_id({k: v for k, v in evidence.items() if k != "evidence_sha256" and k != "evidence_identity"})
        evidence["evidence_identity"] = f"multi_source_exact_session_market_evidence:{evidence['evidence_sha256']}"
        projected["degraded_provider_recovery"] = dict(recovery_info)
        projected["dnse_provider_health_state"] = health_state
        projected.pop("snapshot_sha256", None)
        projected.pop("snapshot_identity", None)
        projected["snapshot_sha256"] = stable_id(projected)
        projected["snapshot_identity"] = f"p3f9_exact_session_snapshot:{projected['snapshot_sha256']}"
        return evidence, projected

    dnse_records = dnse_snapshot.get("records") or {}
    all_dnse_exact_tickers = {
        t for t, r in dnse_records.items() if r.get("disposition") == DNSE_EXACT_SESSION_DISPOSITION
    }
    original_cohort_set = set(sentinel_cohort)
    expanded_new_tickers = all_dnse_exact_tickers - original_cohort_set
    expanded_cohort = sorted(original_cohort_set | all_dnse_exact_tickers)

    evidence2, projected2 = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse_snapshot, target_session=target_session, requested_at=requested_at,
        recovery_window_days=recovery_window_days, fetch_single_source=memoized_fetch,
        request_delay=0.0, sleep_fn=_no_sleep, max_recovery_candidates=max_recovery_candidates,
        sentinel_cohort=expanded_cohort,
    )
    expanded_recovery_attempts = {"VCI": 0, "KBS": 0}
    for ticker in expanded_new_tickers:
        for obs in evidence2["records"].get(ticker, {}).get("observations", []):
            source = obs.get("source")
            if source in expanded_recovery_attempts and obs.get("status") != STATUS_NOT_APPLICABLE:
                expanded_recovery_attempts[source] += 1

    recovery_info = {
        "mode": DEGRADED_RECOVERY_COMPLETED,
        "expanded_ticker_count": len(expanded_new_tickers),
        "expanded_recovery_attempts": expanded_recovery_attempts,
    }
    evidence2["degraded_provider_recovery"] = recovery_info
    evidence2["evidence_sha256"] = stable_id({k: v for k, v in evidence2.items() if k != "evidence_sha256" and k != "evidence_identity"})
    evidence2["evidence_identity"] = f"multi_source_exact_session_market_evidence:{evidence2['evidence_sha256']}"
    projected2["degraded_provider_recovery"] = dict(recovery_info)
    projected2["dnse_provider_health_state"] = evidence2["dnse_quality_sentinel"]["health"]["state"]
    projected2.pop("snapshot_sha256", None)
    projected2.pop("snapshot_identity", None)
    projected2["snapshot_sha256"] = stable_id(projected2)
    projected2["snapshot_identity"] = f"p3f9_exact_session_snapshot:{projected2['snapshot_sha256']}"
    return evidence2, projected2
