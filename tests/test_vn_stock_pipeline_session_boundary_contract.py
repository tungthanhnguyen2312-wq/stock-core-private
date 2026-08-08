"""Focused tests for the "VN Stock Fetch-Window Session-Boundary Contract" milestone.

Contract chosen (see the milestone's SESSION CONTRACT write-up, not repeated here): both
cmd_backfill's and cmd_update's `today` -- the upper bound passed to fetch_one() and, in
cmd_update, the catch-up skip-guard comparator -- are VN_CIVIL_DATE (vn_time.vn_today()), not a
trading-session-aware boundary. This repo has no exchange-holiday calendar and no shared,
importable trading-session helper (freshness_history.latest_completed_market_day is a private,
weekday-only helper used nowhere outside freshness_history.py itself); fetch_one()'s own
established empty-result handling already absorbs "asked for a non-trading/incomplete day"
safely (proven by reading its source, not assumed), so VN_CIVIL_DATE is the smallest contract
that fixes the actual bug (a host-timezone-lagging-behind-VN date causing the skip-guard to fire
one day early, silently dropping a genuinely available session) without inventing session
semantics the project hasn't established.

Does not re-prove vn_now()'s own host-independence (test_vn_time.py already does that
exhaustively); proves vn_today() correctly delegates to it, and that cmd_backfill/cmd_update
correctly consume vn_today() end to end. Uses mocks/temp DB only -- no provider calls.
"""
from __future__ import annotations

import io
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import vn_stock_pipeline as pipeline  # noqa: E402
import vn_time  # noqa: E402

# UTC 2026-08-08 20:00 -> VN (+07:00) 2026-08-09 03:00: VN is already the *next* calendar day.
# This is the exact dangerous instant: a bare host-local read on a UTC-configured machine would
# compute "2026-08-08", one day behind the true VN date.
FIXED_UTC_NEXT_DAY = datetime(2026, 8, 8, 20, 0, 0, tzinfo=timezone.utc)
VN_DATE_AT_THAT_INSTANT = "2026-08-09"
HOST_LOCAL_UTC_WOULD_READ = "2026-08-08"


class VnTodayHostIndependenceTests(unittest.TestCase):
    """vn_today() itself: proves delegation to vn_now() (never a bare/naive call) and correctness
    at the concrete UTC-vs-VN-next-day boundary named by this milestone."""

    def test_delegates_to_vn_now_not_a_bare_or_naive_call(self):
        with mock.patch.object(vn_time, "vn_now", wraps=vn_time.vn_now) as spy:
            vn_time.vn_today()
            spy.assert_called_once_with()

    def test_utc_host_already_next_day_in_vietnam(self):
        with mock.patch.object(vn_time, "datetime") as fake:
            fake.now.side_effect = lambda tz=None: (
                FIXED_UTC_NEXT_DAY.astimezone(tz) if tz else FIXED_UTC_NEXT_DAY
            )
            self.assertEqual(vn_time.vn_today(), VN_DATE_AT_THAT_INSTANT)

    def test_host_reading_bare_utc_would_have_been_one_day_behind(self):
        """Documents the bug this milestone fixes: a naive `datetime.now()` on a UTC-configured
        host reads the wrong (earlier) civil date at this exact instant. vn_today() must not."""
        self.assertNotEqual(HOST_LOCAL_UTC_WOULD_READ, VN_DATE_AT_THAT_INSTANT)
        self.assertEqual(FIXED_UTC_NEXT_DAY.strftime("%Y-%m-%d"), HOST_LOCAL_UTC_WOULD_READ)

    def test_another_host_timezone_where_local_date_also_differs_from_vietnam(self):
        """A second, distinct host-timezone scenario (US Eastern, real IANA DST rules, not bare
        UTC): at the same frozen instant its bare local reading would also read "2026-08-08",
        one day behind vn_today()'s correct VN answer."""
        us_eastern = FIXED_UTC_NEXT_DAY.astimezone(ZoneInfo("America/New_York"))
        self.assertEqual(us_eastern.strftime("%Y-%m-%d"), HOST_LOCAL_UTC_WOULD_READ)
        with mock.patch.object(vn_time, "datetime") as fake:
            fake.now.side_effect = lambda tz=None: (
                FIXED_UTC_NEXT_DAY.astimezone(tz) if tz else us_eastern
            )
            self.assertEqual(vn_time.vn_today(), VN_DATE_AT_THAT_INSTANT)

    def test_repeated_calls_for_the_same_frozen_instant_are_deterministic(self):
        with mock.patch.object(vn_time, "datetime") as fake:
            fake.now.side_effect = lambda tz=None: (
                FIXED_UTC_NEXT_DAY.astimezone(tz) if tz else FIXED_UTC_NEXT_DAY
            )
            first, second = vn_time.vn_today(), vn_time.vn_today()
        self.assertEqual(first, second)
        self.assertEqual(first, VN_DATE_AT_THAT_INSTANT)

    def test_intraday_invariant_not_session_boundary_aware(self):
        """Documents the chosen contract: VN_CIVIL_DATE, not a market-session boundary. The
        result must NOT change between before/after the VN 15:15 close on the same calendar day
        -- if it did, that would mean session-boundary logic had crept in unintentionally."""
        before_close = datetime(2026, 8, 10, 8, 0, 0, tzinfo=vn_time.VN_TZ)
        after_close = datetime(2026, 8, 10, 20, 0, 0, tzinfo=vn_time.VN_TZ)
        with mock.patch.object(vn_time, "datetime") as fake:
            fake.now.side_effect = lambda tz=None: before_close.astimezone(tz) if tz else before_close
            before = vn_time.vn_today()
        with mock.patch.object(vn_time, "datetime") as fake:
            fake.now.side_effect = lambda tz=None: after_close.astimezone(tz) if tz else after_close
            after = vn_time.vn_today()
        self.assertEqual(before, after)
        self.assertEqual(before, "2026-08-10")


class FetchWindowIntegrationTests(unittest.TestCase):
    """cmd_backfill / cmd_update: proves the actual orchestration functions consume vn_today()
    correctly, and the three required safety properties (ordering, no premature skip, no
    unnecessary re-fetch)."""

    def setUp(self):
        self.stdout_patch = mock.patch("sys.stdout", new_callable=io.StringIO)
        self.stdout_patch.start()
        self.addCleanup(self.stdout_patch.stop)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.db_patch = mock.patch.object(pipeline, "DB_PATH", self.db_path)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        with closing(sqlite3.connect(self.db_path)) as conn:
            pipeline.init_db(conn)
        self.sleep_patch = mock.patch.object(pipeline.time, "sleep")
        self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)

    def _seed_last(self, ticker, date_):
        with closing(sqlite3.connect(self.db_path)) as conn:
            pipeline.upsert(
                conn,
                pipeline.normalize(
                    pd.DataFrame({"time": [date_], "open": [1], "high": [1], "low": [1],
                                  "close": [1], "volume": [100]}),
                    ticker, "VCI",
                ),
            )

    def test_cmd_backfill_passes_vn_today_as_fetch_end_date(self):
        calls = []
        with mock.patch.object(pipeline, "vn_today", return_value=VN_DATE_AT_THAT_INSTANT), \
             mock.patch.object(pipeline, "get_universe", return_value=["AAA"]), \
             mock.patch.object(pipeline, "fetch_one",
                                side_effect=lambda tk, s, e: calls.append((tk, s, e)) or pipeline.FetchOutcome("empty")):
            pipeline.cmd_backfill()
        self.assertEqual(calls, [("AAA", pipeline.START_DATE, VN_DATE_AT_THAT_INSTANT)])

    def test_cmd_update_passes_vn_today_as_fetch_end_date_when_behind(self):
        self._seed_last("AAA", "2026-08-08")
        calls = []
        with mock.patch.object(pipeline, "vn_today", return_value=VN_DATE_AT_THAT_INSTANT), \
             mock.patch.object(pipeline, "get_universe", return_value=["AAA"]), \
             mock.patch.object(pipeline, "fetch_one",
                                side_effect=lambda tk, s, e: calls.append((tk, s, e)) or pipeline.FetchOutcome("empty")):
            pipeline.cmd_update()
        self.assertEqual(calls, [("AAA", "2026-08-08", VN_DATE_AT_THAT_INSTANT)])

    def test_query_start_end_dates_remain_ordered(self):
        self._seed_last("AAA", "2026-08-08")
        calls = []
        with mock.patch.object(pipeline, "vn_today", return_value=VN_DATE_AT_THAT_INSTANT), \
             mock.patch.object(pipeline, "get_universe", return_value=["AAA"]), \
             mock.patch.object(pipeline, "fetch_one",
                                side_effect=lambda tk, s, e: calls.append((s, e)) or pipeline.FetchOutcome("empty")):
            pipeline.cmd_update()
        for start, end in calls:
            self.assertLessEqual(start, end)

    def test_rerun_does_not_skip_a_genuinely_missing_session_at_the_utc_vs_vn_boundary(self):
        """The regression this milestone fixes: last-known date "2026-08-08" with the true VN
        date already "2026-08-09" (per FIXED_UTC_NEXT_DAY) must NOT be treated as caught up --
        a host-local check on a UTC-configured host would have wrongly skipped this."""
        self._seed_last("AAA", "2026-08-08")
        called = []
        with mock.patch.object(vn_time, "datetime") as fake:
            fake.now.side_effect = lambda tz=None: (
                FIXED_UTC_NEXT_DAY.astimezone(tz) if tz else FIXED_UTC_NEXT_DAY
            )
            with mock.patch.object(pipeline, "get_universe", return_value=["AAA"]), \
                 mock.patch.object(pipeline, "fetch_one",
                                    side_effect=lambda tk, s, e: called.append(tk) or pipeline.FetchOutcome("empty")):
                pipeline.cmd_update()
        self.assertEqual(called, ["AAA"], "genuinely missing 2026-08-09 session must not be skipped")

    def test_rerun_skips_a_ticker_already_caught_up_through_today(self):
        """Efficiency/no-op property: once start == today, no fetch is issued."""
        self._seed_last("AAA", VN_DATE_AT_THAT_INSTANT)
        called = []
        with mock.patch.object(pipeline, "vn_today", return_value=VN_DATE_AT_THAT_INSTANT), \
             mock.patch.object(pipeline, "get_universe", return_value=["AAA"]), \
             mock.patch.object(pipeline, "fetch_one",
                                side_effect=lambda tk, s, e: called.append(tk) or pipeline.FetchOutcome("empty")):
            pipeline.cmd_update()
        self.assertEqual(called, [], "a ticker already caught up through today must not be re-fetched")

    def test_weekend_today_does_not_crash_and_does_not_wrongly_skip(self):
        """No qualified weekend/holiday handling exists (documented, not invented here) -- proves
        the skip-guard still behaves safely (no premature skip) when `today` lands on a
        Saturday, rather than special-casing or crashing on it."""
        saturday = "2026-08-08"  # a Saturday
        self._seed_last("AAA", "2026-08-07")  # Friday's session already stored
        called = []
        with mock.patch.object(pipeline, "vn_today", return_value=saturday), \
             mock.patch.object(pipeline, "get_universe", return_value=["AAA"]), \
             mock.patch.object(pipeline, "fetch_one",
                                side_effect=lambda tk, s, e: called.append((tk, s, e)) or pipeline.FetchOutcome("empty")):
            code = pipeline.cmd_update()
        self.assertEqual(pipeline.EXIT_SUCCESS, code)
        self.assertEqual(called, [("AAA", "2026-08-07", saturday)])

    def test_source_derived_ohlcv_date_remains_untouched_by_this_contract(self):
        """This milestone only changes the query boundary, never the OHLCV date column itself
        (already proven wall-clock-independent in test_producer_sync_timestamp_contract.py;
        reconfirmed here as this milestone's own self-contained evidence)."""
        df = pd.DataFrame({"time": ["2026-08-07"], "open": [1], "high": [1], "low": [1],
                            "close": [1], "volume": [100]})
        with mock.patch.object(pipeline, "vn_today", return_value=VN_DATE_AT_THAT_INSTANT):
            out = pipeline.normalize(df, "AAA", "VCI")
        self.assertEqual(list(out["date"]), ["2026-08-07"])


if __name__ == "__main__":
    unittest.main()
