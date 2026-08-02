from datetime import datetime, timezone
import unittest

from source_timestamp import resolve_source_datetime, source_timestamp
from candle_scan import WATCHLIST


class SourceTimestampTests(unittest.TestCase):
    def test_explicit_timestamp_is_normalized_deterministically(self):
        self.assertEqual(source_timestamp("2026-08-02T13:00:00+07:00"), "2026-08-02T06:00:00Z")
        self.assertEqual(source_timestamp(datetime(2026, 8, 2, 6, tzinfo=timezone.utc)), "2026-08-02T06:00:00Z")

    def test_naive_or_malformed_timestamp_fails_closed(self):
        for value in ("2026-08-02T06:00:00", "not-a-timestamp"):
            with self.assertRaises(ValueError):
                resolve_source_datetime(value)

    def test_trusted_subset_is_always_scanned_without_implying_a_signal(self):
        self.assertTrue({"HPG", "VNM"}.issubset(WATCHLIST))


if __name__ == "__main__":
    unittest.main()
