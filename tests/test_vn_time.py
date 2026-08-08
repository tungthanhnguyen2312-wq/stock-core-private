"""Tests for vn_time.py: the deterministic Vietnam operational-time helper.

Proves the fix for the host-OS-dependent `datetime.now().astimezone()` pattern: explicit
+07:00 offset, no DST, fixed-instant determinism, and independence from whatever timezone the
executing host happens to be in.
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import vn_time  # noqa: E402

VN_OFFSET = timedelta(hours=7)


class ExplicitVietnamOffsetTests(unittest.TestCase):
    def test_vn_now_is_timezone_aware(self):
        self.assertIsNotNone(vn_time.vn_now().tzinfo)

    def test_vn_now_offset_is_plus_seven(self):
        self.assertEqual(vn_time.vn_now().utcoffset(), VN_OFFSET)

    def test_iso_string_carries_explicit_offset_suffix(self):
        self.assertRegex(vn_time.vn_now_iso(), r"\+07:00$")

    def test_no_dst_in_january_and_july(self):
        # Vietnam observes no DST; the offset must not vary by time of year (unlike zones that do).
        january = datetime(2026, 1, 15, 4, 0, 0, tzinfo=timezone.utc).astimezone(vn_time.VN_TZ)
        july = datetime(2026, 7, 15, 4, 0, 0, tzinfo=timezone.utc).astimezone(vn_time.VN_TZ)
        self.assertEqual(january.utcoffset(), VN_OFFSET)
        self.assertEqual(july.utcoffset(), VN_OFFSET)

    def test_output_matches_hand_computed_conversion(self):
        # UTC 03:30 -> Vietnam 10:30 the same day (+7h, no DST crossing to reason about).
        fixed_utc = datetime(2026, 1, 15, 3, 30, 0, tzinfo=timezone.utc)
        with mock.patch.object(vn_time, "datetime") as fake:
            fake.now.side_effect = lambda tz=None: fixed_utc.astimezone(tz) if tz else fixed_utc
            self.assertEqual(vn_time.vn_now_iso(), "2026-01-15T10:30:00+07:00")


class FixedInstantDeterminismTests(unittest.TestCase):
    def test_repeated_calls_for_the_same_frozen_instant_match(self):
        fixed_utc = datetime(2026, 3, 1, 23, 59, 59, tzinfo=timezone.utc)
        with mock.patch.object(vn_time, "datetime") as fake:
            fake.now.side_effect = lambda tz=None: fixed_utc.astimezone(tz) if tz else fixed_utc
            first = vn_time.vn_now_iso()
            second = vn_time.vn_now_iso()
        self.assertEqual(first, second)
        self.assertEqual(first, "2026-03-02T06:59:59+07:00")


class HostIndependenceTests(unittest.TestCase):
    def test_always_calls_datetime_now_with_explicit_vn_tz(self):
        """vn_now() must pass the zone explicitly -- datetime.now(tz) with an explicit tz is
        defined (per the datetime docs) as fromtimestamp(time.time(), tz): a pure function of
        the tz-independent epoch, never of host-local state. A bare .now()/.astimezone() call
        (no argument) is the only path that reads host-local settings, and this asserts that
        path is never taken."""
        with mock.patch.object(vn_time, "datetime", wraps=datetime) as spy:
            vn_time.vn_now()
            spy.now.assert_called_once_with(vn_time.VN_TZ)

    def test_output_unaffected_by_a_simulated_different_host(self):
        fixed_utc = datetime(2026, 5, 20, 1, 0, 0, tzinfo=timezone.utc)

        class HostSimulatingClock:
            """now(tz): explicit-tz calls always resolve the fixed instant correctly; a bare
            call (no tz) simulates whatever a different host's local wall clock would show --
            vn_now() must never take that branch, so varying it must never change the result."""

            @staticmethod
            def now(tz=None):
                if tz is not None:
                    return fixed_utc.astimezone(tz)
                raise AssertionError("vn_now() must always pass an explicit tz, never call datetime.now() bare")

        with mock.patch.object(vn_time, "datetime", HostSimulatingClock):
            results = {vn_time.vn_now_iso() for _ in range(3)}
        self.assertEqual(results, {"2026-05-20T08:00:00+07:00"})

    @unittest.skipUnless(hasattr(time, "tzset"), "time.tzset is POSIX-only; not available on this host")
    def test_changing_real_process_timezone_leaves_vn_offset_unchanged(self):
        """Empirical contrast on POSIX: actually flips the process TZ across several zones and
        shows the OLD buggy pattern's offset moves with it while vn_now()'s does not -- both
        sampled within the same instant, so only the host tz setting differs between them."""
        original_tz = os.environ.get("TZ")
        try:
            new_offsets, old_offsets = set(), set()
            for zone in ("America/New_York", "UTC", "Asia/Kolkata", "Pacific/Auckland"):
                os.environ["TZ"] = zone
                time.tzset()
                new_offsets.add(vn_time.vn_now().utcoffset())
                old_offsets.add(datetime.now().astimezone().utcoffset())
            self.assertEqual(new_offsets, {VN_OFFSET}, "vn_now() must stay +07:00 regardless of host TZ")
            self.assertGreater(len(old_offsets), 1, "sanity check: the old bare-astimezone() pattern "
                                                      "should actually vary with host TZ on this platform")
        finally:
            if original_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_tz
            time.tzset()


if __name__ == "__main__":
    unittest.main()
