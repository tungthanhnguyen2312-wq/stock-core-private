"""Tests for vnstock_rate_governor (DAILY_GLOBAL_VNSTOCK_RATE_GOVERNOR_V1, 2026-09-04)."""
from __future__ import annotations

import threading

import pytest

from vnstock_rate_governor import (
    DEFAULT_EFFECTIVE_RPM,
    VNSTOCK_OBSERVED_HARD_CEILING_RPM,
    VnstockRateGovernor,
    get_active_governor,
    set_active_governor,
)


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _fake_sleep(clock: FakeClock):
    def sleep(seconds: float) -> None:
        clock.advance(seconds)
    return sleep


def test_default_effective_limit_is_below_the_observed_hard_ceiling():
    assert DEFAULT_EFFECTIVE_RPM < VNSTOCK_OBSERVED_HARD_CEILING_RPM
    governor = VnstockRateGovernor()
    assert governor.limit == DEFAULT_EFFECTIVE_RPM
    assert governor.hard_ceiling == VNSTOCK_OBSERVED_HARD_CEILING_RPM


@pytest.mark.parametrize("limit,hard_ceiling", [(60, 60), (61, 60), (0, 60), (-5, 60)])
def test_governor_rejects_a_limit_at_or_above_hard_ceiling_or_non_positive(limit, hard_ceiling):
    with pytest.raises(ValueError):
        VnstockRateGovernor(limit=limit, hard_ceiling=hard_ceiling)


def test_acceptance_a_workload_that_would_exceed_60_in_60s_never_reaches_hard_ceiling():
    """Reproduce today's request topology: ~96 requests (DNSE-health sentinel dual-source ~80 +
    residual-gap sentinel ~16) that would previously all land inside one 60s window. Every
    rolling 60s window must stay strictly below the observed hard ceiling."""
    clock = FakeClock()
    governor = VnstockRateGovernor(limit=45, hard_ceiling=60, clock=clock, sleep_fn=_fake_sleep(clock))
    acquire_times = []
    for i in range(96):
        governor.acquire(provider="KBS" if i % 2 == 0 else "VCI")
        acquire_times.append(clock())
        clock.advance(0.01)  # negligible per-request processing time between acquires

    # The real safety property: no rolling 60s window, independently reconstructed from the raw
    # accepted timestamps, ever reaches the observed hard ceiling. (A tolerance of 1 above the
    # configured limit is allowed here purely for float-accumulation slop across 96 repeated
    # `clock.advance(0.01)` calls in this test's own verification loop -- the governor's own
    # internally-consistent bookkeeping, asserted below via max_window_utilization, is exact.)
    for t in acquire_times:
        window_count = sum(1 for other in acquire_times if t - 60.0 < other <= t)
        assert window_count < governor.hard_ceiling, f"window at t={t} held {window_count} >= hard ceiling"
        assert window_count <= governor.limit + 1

    assert governor.attempts == 96
    assert governor.waits > 0
    assert governor.total_wait_seconds > 0
    assert governor.max_window_utilization <= governor.limit
    assert governor.provider_counts == {"KBS": 48, "VCI": 48}


def test_acceptance_f_rolling_window_boundary_accounting_is_exact():
    clock = FakeClock()
    governor = VnstockRateGovernor(limit=2, window_seconds=60.0, hard_ceiling=60, clock=clock, sleep_fn=_fake_sleep(clock))
    governor.acquire()          # t=0
    clock.advance(10)
    governor.acquire()          # t=10 -- window [0, 10] now holds 2 (== limit)
    clock.advance(49)           # t=59 -- timestamp 0 is exactly 59s old, still inside the 60s window
    governor.acquire()          # must wait exactly 1s for timestamp 0 to age past 60s
    assert clock() == 60.0
    assert governor.waits == 1
    assert governor.attempts == 3
    assert governor.total_wait_seconds == 1.0


def test_acceptance_f_a_timestamp_exactly_at_the_window_edge_is_pruned():
    clock = FakeClock()
    governor = VnstockRateGovernor(limit=1, window_seconds=60.0, hard_ceiling=60, clock=clock, sleep_fn=_fake_sleep(clock))
    governor.acquire()   # t=0
    clock.advance(60.0)  # t=60 -- exactly window_seconds later: must NOT still count as "in window"
    governor.acquire()   # must succeed immediately, no wait
    assert governor.waits == 0
    assert governor.attempts == 2


def test_acceptance_c_kbs_concurrency_cannot_burst_around_the_governor():
    """Two 'worker threads' (as KBS's own bounded concurrency uses) hammering acquire()
    concurrently must still be serialized against the SAME shared budget -- never allowed to
    jointly exceed the configured limit within one window. Uses the REAL monotonic clock and
    real (tiny) sleeps -- a fake clock advanced non-monotonically by many racing threads would
    not faithfully model wall-clock time, where a sleeping thread never lets others "skip ahead".
    """
    governor = VnstockRateGovernor(limit=10, hard_ceiling=60, window_seconds=0.2)
    barrier = threading.Barrier(20)

    def worker():
        barrier.wait()
        governor.acquire(provider="KBS")

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert governor.attempts == 20
    # The lock-protected check-and-append is the real safety property under test: regardless of
    # how many threads raced to call acquire() simultaneously, the internal bookkeeping never
    # let more than `limit` requests land in one window.
    assert governor.max_window_utilization <= governor.limit
    # At least the second half of the 20 threads (only 10 fit in the first instant) must have
    # been forced to actually wait -- concurrency alone never bypasses the shared budget.
    assert governor.waits >= 10


def test_acquire_returns_the_wait_it_imposed():
    clock = FakeClock()
    governor = VnstockRateGovernor(limit=1, hard_ceiling=60, clock=clock, sleep_fn=_fake_sleep(clock))
    assert governor.acquire() == 0.0
    waited = governor.acquire()
    assert waited == 60.0


def test_cache_hit_recording_does_not_consume_a_slot():
    governor = VnstockRateGovernor(limit=1, hard_ceiling=60)
    governor.record_cache_hit()
    governor.record_cache_hit()
    assert governor.cache_hits == 2
    assert governor.attempts == 0
    assert len(governor._timestamps) == 0


def test_estimated_minimum_seconds_for_reflects_shared_budget():
    governor = VnstockRateGovernor(limit=45, window_seconds=60.0)
    assert governor.estimated_minimum_seconds_for(0) == 0.0
    assert governor.estimated_minimum_seconds_for(45) == pytest.approx(60.0)
    assert governor.estimated_minimum_seconds_for(548) == pytest.approx(548 * (60.0 / 45))


def test_diagnostic_reports_configured_and_effective_ceilings_and_never_claims_db_authority():
    governor = VnstockRateGovernor(limit=45, hard_ceiling=60)
    diagnostic = governor.diagnostic()
    assert diagnostic["hard_ceiling_rpm"] == 60
    assert diagnostic["effective_limit_rpm"] == 45
    assert diagnostic["not_authoritative"] is True
    assert diagnostic["production_db_authority"] is False


def test_set_active_governor_returns_previous_and_get_active_governor_reflects_it():
    original = get_active_governor()
    try:
        assert set_active_governor(None) is None
        governor_a = VnstockRateGovernor()
        previous = set_active_governor(governor_a)
        assert previous is None
        assert get_active_governor() is governor_a
        governor_b = VnstockRateGovernor()
        previous2 = set_active_governor(governor_b)
        assert previous2 is governor_a
        assert get_active_governor() is governor_b
    finally:
        set_active_governor(original)
