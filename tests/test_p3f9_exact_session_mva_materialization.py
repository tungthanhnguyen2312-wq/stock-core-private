from __future__ import annotations
from datetime import datetime, timedelta, timezone
import unittest

import mva_exact_session_snapshot as m


VN = timezone(timedelta(hours=7))


def fetcher(_capability, **kwargs):
    target = datetime(2026, 8, 20, 9, tzinfo=VN)
    previous = target - timedelta(days=1)
    return {"ok": True, "endpoint": "/price/ohlc", "body": {"t": [int(previous.timestamp()), int(target.timestamp())], "o": [1, 1], "h": [1, 1], "l": [1, 1], "c": [1, 1], "v": [10, 10]}}


class TestP3F9ExactSessionSnapshot(unittest.TestCase):
    def test_exact_session_and_generic_mapping(self):
        snap = m.materialize_snapshot(candidates=["AAA", "BBB"], requested_at=datetime(2026, 8, 20, 16, tzinfo=VN), api_key="x", api_secret="y", fetcher=fetcher, workers=1)
        self.assertEqual("2026-08-20", snap["resolved_completed_session"])
        self.assertEqual(2, snap["exact_session_observed_count"])
        self.assertEqual(0, snap["missing_current_session_count"])
        self.assertFalse(snap["is_actionable_for_execution"])
        self.assertEqual("NOT_PROMOTED", snap["authority_boundary"]["RAW_AS_TRADED"])

    def test_missing_exact_session_fails_closed_without_prior_substitution(self):
        def old_only(*args, **kwargs):
            return {"ok": True, "endpoint": "/price/ohlc", "body": {"t": [int(datetime(2026, 8, 19, 9, tzinfo=VN).timestamp())], "o": [1], "h": [1], "l": [1], "c": [1], "v": [10]}}
        snap = m.materialize_snapshot(candidates=["AAA"], requested_at=datetime(2026, 8, 20, 16, tzinfo=VN), api_key="x", api_secret="y", fetcher=old_only, workers=1)
        self.assertEqual("EXACT_SESSION_MISSING", snap["records"]["AAA"]["status"])
        self.assertEqual(0, snap["exact_session_observed_count"])

    def test_intraday_and_malformed_are_rejected(self):
        def malformed(*args, **kwargs): return {"ok": True, "body": {"t": [], "c": []}}
        snap = m.materialize_snapshot(candidates=["AAA"], requested_at=datetime(2026, 8, 20, 16, tzinfo=VN), api_key="x", api_secret="y", fetcher=malformed, workers=1)
        self.assertEqual("MALFORMED_RESPONSE", snap["records"]["AAA"]["status"])
        self.assertFalse(snap["source"]["intraday_observations_used"])
