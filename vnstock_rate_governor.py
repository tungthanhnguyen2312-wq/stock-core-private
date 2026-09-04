"""Global, invocation-scoped rate governor for all Vnstock-backed (VCI/KBS) requests.

WHY THIS MODULE EXISTS (DAILY_GLOBAL_VNSTOCK_RATE_GOVERNOR_V1, 2026-09-04)
    The first real canonical Daily run for 2026-09-04 passed every Stock Lookup gate (raw
    exact-session coverage 56.92%, well above the 0.20 floor) and was then hard-killed by
    vnai's OWN Community-tier limiter: "Gioi han: 60 requests/phut -- Da su dung: 60/60" --
    before Stock Lookup's own exception handling ever ran (the library terminates the process
    itself; it does not raise a catchable Python exception). vnai's own internal tier table
    (``vnai.beam.auth``'s ``"free"`` tier: ``{"min": 60, "hour": 3600, "day": 10000}``) records
    the identical 60/minute figure -- corroborating, not contradicting, the live failure
    evidence. This module encodes that observed ceiling explicitly rather than importing
    vnai's private internals (a third-party library's undocumented module layout is not a
    contract this project pins runtime behavior to).

    Root cause of the crash: KBS and VCI were paced independently
    (``multi_source_exact_session_resolver._recovery_provider_policies``), each against its own
    local budget. vnai's limiter is process/library-wide, not provider-specific, so the
    *combined* concurrent request rate could exceed it even though each provider looked
    individually well-paced. This module is the single shared budget both providers must draw
    from so that can never happen again.

DESIGN
    One process-wide, thread-safe sliding-window limiter. Every actual outbound VCI/KBS HTTP
    call -- regardless of which pass, sentinel, or retry issued it -- calls ``acquire()``
    immediately before the request leaves the process. It is wired in at the single lowest real
    transport chokepoint, ``vn_stock_pipeline._bounded_send_request_direct`` (the process-wide
    monkeypatch target for ``vnstock.core.utils.client.send_request_direct``): every VCI/KBS
    call in this codebase already funnels through it by construction, including
    ``vn_stock_pipeline.fetch_single_source``'s own internal retry loop (each retry re-enters
    this same function, so retries consume slots for free, with no separate accounting needed).

    Foreground only: ``acquire()`` blocks the calling thread with a plain, injectable
    ``sleep_fn`` call when the window is full -- no timer thread, no background worker, no
    async daemon. A ``threading.Lock`` makes this safe for KBS's existing bounded-concurrency
    (2 worker threads): both threads call into the SAME governor instance, so the shared budget
    is enforced regardless of how many workers are dispatching concurrently.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Callable

# vnai.beam.auth's own "free" tier table records min=60/hour=3600/day=10000 -- byte-identical
# to this project's own live 2026-09-04 failure evidence. Encoded explicitly (see module
# docstring) rather than imported from vnai's private internals.
VNSTOCK_OBSERVED_HARD_CEILING_RPM = 60
# 25% safety margin below the observed hard ceiling. This absorbs: this governor's own
# window-boundary rounding, monotonic/wall-clock skew between this process and vnai's own
# counter, and the fact that vnai's window may not start at exactly the same instant as ours.
# Effective throughput (45/min) still clears a full 548-ticker market-wide expansion within the
# existing 45-minute runtime budget (548 / 45 * 60s =~ 12.2 minutes at steady state).
DEFAULT_EFFECTIVE_RPM = 45
RATE_WINDOW_SECONDS = 60.0


class VnstockRateGovernor:
    """Thread-safe sliding-window limiter shared by every Vnstock-backed request in one
    canonical Daily invocation (or one standalone diagnostic run)."""

    def __init__(
        self,
        *,
        limit: int = DEFAULT_EFFECTIVE_RPM,
        window_seconds: float = RATE_WINDOW_SECONDS,
        hard_ceiling: int = VNSTOCK_OBSERVED_HARD_CEILING_RPM,
        clock: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        if limit <= 0:
            raise ValueError("VNSTOCK_RATE_GOVERNOR_LIMIT_MUST_BE_POSITIVE")
        if limit >= hard_ceiling:
            raise ValueError("VNSTOCK_RATE_GOVERNOR_LIMIT_MUST_STAY_BELOW_HARD_CEILING")
        self.limit = limit
        self.hard_ceiling = hard_ceiling
        self.window_seconds = window_seconds
        self._clock = clock
        self._sleep = sleep_fn
        self._lock = threading.Lock()
        self._timestamps: deque[float] = deque()
        self.attempts = 0
        self.retry_attempts = 0
        self.waits = 0
        self.total_wait_seconds = 0.0
        self.cache_hits = 0
        self.provider_counts: dict[str, int] = {}
        self.max_window_utilization = 0

    def _prune(self, now: float) -> None:
        while self._timestamps and now - self._timestamps[0] >= self.window_seconds:
            self._timestamps.popleft()

    def acquire(self, *, provider: str | None = None, is_retry: bool = False) -> float:
        """Block until issuing one more request cannot breach the configured rolling budget,
        then reserve the slot. Returns the wait time actually imposed (0.0 if none)."""
        waited = 0.0
        while True:
            with self._lock:
                now = self._clock()
                self._prune(now)
                if len(self._timestamps) < self.limit:
                    self._timestamps.append(now)
                    self.attempts += 1
                    if is_retry:
                        self.retry_attempts += 1
                    label = provider or "UNKNOWN"
                    self.provider_counts[label] = self.provider_counts.get(label, 0) + 1
                    self.max_window_utilization = max(self.max_window_utilization, len(self._timestamps))
                    return waited
                wait_needed = max(0.0, self.window_seconds - (now - self._timestamps[0]))
            # Sleep OUTSIDE the lock so other threads can keep checking/waiting independently;
            # re-loop afterward since another thread may have taken the freed slot first.
            self.waits += 1
            self.total_wait_seconds += wait_needed
            waited += wait_needed
            if wait_needed > 0:
                self._sleep(wait_needed)

    def record_cache_hit(self) -> None:
        self.cache_hits += 1

    def estimated_minimum_seconds_for(self, additional_requests: int) -> float:
        """Minimum wall-clock time this governor alone would impose on ``additional_requests``
        more requests, given its own steady-state pacing -- used by the runtime forecast guard,
        never by request dispatch itself."""
        if additional_requests <= 0:
            return 0.0
        return additional_requests * (self.window_seconds / self.limit)

    def diagnostic(self) -> dict[str, Any]:
        return {
            "contract_version": "vnstock_rate_governor/v1",
            "hard_ceiling_rpm": self.hard_ceiling,
            "effective_limit_rpm": self.limit,
            "window_seconds": self.window_seconds,
            "attempts": self.attempts,
            "retry_attempts": self.retry_attempts,
            "waits_imposed": self.waits,
            "total_wait_seconds": round(self.total_wait_seconds, 3),
            "cache_hits": self.cache_hits,
            "provider_breakdown": dict(self.provider_counts),
            "max_observed_window_utilization": self.max_window_utilization,
            "not_authoritative": True,
            "production_db_authority": False,
        }


_ACTIVE_GOVERNOR: VnstockRateGovernor | None = None
_ACTIVE_GOVERNOR_LOCK = threading.Lock()


def set_active_governor(governor: VnstockRateGovernor | None) -> VnstockRateGovernor | None:
    """Install (or clear, with None) the governor ``_bounded_send_request_direct`` consults for
    every subsequent call in this process. Returns whatever was active before, so a caller that
    is nesting (e.g. resolve_exact_session_with_autorecovery wrapping resolve_multi_source_
    exact_session_snapshot) can restore it afterward rather than clobbering an outer scope."""
    global _ACTIVE_GOVERNOR
    with _ACTIVE_GOVERNOR_LOCK:
        previous = _ACTIVE_GOVERNOR
        _ACTIVE_GOVERNOR = governor
        return previous


def get_active_governor() -> VnstockRateGovernor | None:
    with _ACTIVE_GOVERNOR_LOCK:
        return _ACTIVE_GOVERNOR
