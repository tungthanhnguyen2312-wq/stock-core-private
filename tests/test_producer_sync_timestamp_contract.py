"""Focused tests for the 2026-08-08 "Producer sync timestamp/session contract" milestone.

Scope: meta_sync.py and its 7 sibling sync scripts wrote naive, host-OS-dependent
`datetime.now()` timestamps (see docs/... audit trail). This milestone repointed every
occurrence classified OPERATIONAL_GENERATED_AT / FILENAME_ONLY at vn_time.py's
vn_now()/vn_now_iso() -- already proven host-independent and deterministic by
tests/test_vn_time.py, which this file does not re-prove. What *is* new here:

  1. each patched call site actually delegates to vn_time (not the old bare pattern), and a
     frozen instant flows through deterministically end to end;
  2. the one field with real downstream freshness-gate readers -- metadata.updated, upgraded
     to full ISO+offset via vn_now_iso() instead of a same-shape strftime -- is still safely
     and correctly consumed by both real readers (market_wide_current_shares_resolver._as_date,
     freshness_history.parse_timestamp), for both the new format AND legacy naive rows already
     sitting in the database;
  3. occurrences deliberately left untouched (DATA_AS_OF / SOURCE_OBSERVED_AT / FRESHNESS_INPUT)
     remain wall-clock-independent -- rerunning must not manufacture a newer data_as_of.

news_sync.sync_feed's `fetched` column and shareholders_sync.persist_summary's `updated` column
use the identical vn_now().strftime(...) idiom already given full behavioral coverage below via
blacklist_sync/bctc_sync/vn_stock_pipeline/shareholders_sync.set_progress; for those two they are
checked structurally (source no longer contains the bare no-arg pattern) rather than re-built
behaviorally, since a full RSS-feed / multi-table shareholder-summary fixture would not exercise
a materially different code path for the one line under test.
"""
from __future__ import annotations

import inspect
import re
import sqlite3
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ai_analyzer  # noqa: E402
import bctc_sync  # noqa: E402
import blacklist_sync  # noqa: E402
import market_wide_current_shares_resolver as shares_resolver  # noqa: E402
import meta_sync  # noqa: E402
import news_sync  # noqa: E402
import shareholders_sync  # noqa: E402
import vn_stock_pipeline  # noqa: E402
import vn_time  # noqa: E402
from freshness_history import RULES, freshness_envelope, parse_timestamp  # noqa: E402

FIXED_UTC = datetime(2026, 8, 8, 3, 0, 0, tzinfo=timezone.utc)
FIXED_VN = FIXED_UTC.astimezone(vn_time.VN_TZ)          # 2026-08-08 10:00:00+07:00
FIXED_VN_ISO = "2026-08-08T10:00:00+07:00"
LEGACY_NAIVE = "2026-08-05 14:32"                        # pre-fix format already stored in prod
BARE_NOW_RE = re.compile(r"datetime\.now\(\)")            # empty parens only -- not datetime.now(timezone.utc)


class MetadataUpdatedTests(unittest.TestCase):
    """meta_sync.py: metadata.updated -- the one field upgraded to full ISO+offset because it
    feeds two real freshness/observation-date readers (traced, not assumed)."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        meta_sync.init_metadata(self.conn)

    def tearDown(self):
        self.conn.close()

    def _run_with_frozen_clock(self, iso_value, tickers=("ABC",), refresh=False):
        with mock.patch.object(meta_sync, "vn_now_iso", return_value=iso_value), \
             mock.patch.object(meta_sync, "call_api", return_value=None):
            meta_sync.sync_fundamentals(self.conn, list(tickers), refresh=refresh)

    def test_write_path_uses_vn_now_iso_not_host_clock(self):
        self._run_with_frozen_clock(FIXED_VN_ISO)
        row = self.conn.execute("SELECT updated FROM metadata WHERE ticker='ABC'").fetchone()
        self.assertEqual(row[0], FIXED_VN_ISO)

    def test_repeated_calls_for_the_same_frozen_instant_are_identical(self):
        self._run_with_frozen_clock(FIXED_VN_ISO, tickers=("ABC",))
        first = self.conn.execute("SELECT updated FROM metadata WHERE ticker='ABC'").fetchone()[0]
        self._run_with_frozen_clock(FIXED_VN_ISO, tickers=("ABC",), refresh=True)
        second = self.conn.execute("SELECT updated FROM metadata WHERE ticker='ABC'").fetchone()[0]
        self.assertEqual(first, second)

    def test_source_no_longer_calls_bare_datetime_now(self):
        source = inspect.getsource(meta_sync.sync_fundamentals)
        self.assertNotRegex(source, BARE_NOW_RE)
        self.assertIn("vn_now_iso", source)


class FreshnessGateCompatibilityTests(unittest.TestCase):
    """Both real downstream readers of metadata.updated (traced via grep, not assumed) must
    keep working -- for the new explicit-offset format AND for legacy naive rows already in
    the database, without crashing or silently reinterpreting them."""

    def test_as_date_extracts_correct_day_from_new_iso_format(self):
        self.assertEqual(shares_resolver._as_date(FIXED_VN_ISO), shares_resolver._as_date("2026-08-08"))

    def test_as_date_still_extracts_correct_day_from_legacy_naive_format(self):
        self.assertEqual(shares_resolver._as_date(LEGACY_NAIVE), shares_resolver._as_date("2026-08-05"))

    def test_as_date_unparseable_value_still_fails_closed_to_none(self):
        self.assertIsNone(shares_resolver._as_date("not-a-date"))
        self.assertIsNone(shares_resolver._as_date(None))

    def test_parse_timestamp_preserves_explicit_vn_offset_for_new_format(self):
        parsed = parse_timestamp(FIXED_VN_ISO)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.utcoffset(), FIXED_VN.utcoffset())
        self.assertEqual(parsed.astimezone(timezone.utc), FIXED_UTC)

    def test_parse_timestamp_still_safely_parses_legacy_naive_value(self):
        """Legacy naive rows must not crash and must not be speculatively reinterpreted --
        parse_timestamp's own pre-existing (unchanged by this milestone) UTC-assumption for
        naive input is a separate, out-of-scope concern; this only proves it still runs."""
        parsed = parse_timestamp(LEGACY_NAIVE)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.date().isoformat(), "2026-08-05")

    def test_mandatory_subsource_freshness_gate_still_reports_current_for_a_fresh_new_format_value(self):
        rule = RULES["vnstock_metadata_snapshot"]
        reference_at = FIXED_UTC
        envelope = freshness_envelope(domain="vnstock_metadata_snapshot", as_of_date=FIXED_VN_ISO,
                                       generated_at=FIXED_VN_ISO, source="metadata.updated",
                                       reference_at=reference_at)
        self.assertEqual(envelope["freshness_status"], "current")
        self.assertEqual(envelope["as_of_date"], "2026-08-08")

    def test_mandatory_subsource_freshness_gate_still_fails_closed_when_genuinely_stale(self):
        rule = RULES["vnstock_metadata_snapshot"]
        self.assertGreater(rule.cadence_days + rule.grace_days, 0)
        stale_dt = FIXED_UTC.replace(year=FIXED_UTC.year - 1)  # >1 year old: stale under any real cadence
        envelope = freshness_envelope(domain="vnstock_metadata_snapshot", as_of_date=stale_dt.isoformat(),
                                       generated_at=stale_dt.isoformat(), source="metadata.updated",
                                       reference_at=FIXED_UTC)
        self.assertEqual(envelope["freshness_status"], "stale")


class OperationalGeneratedAtBehavioralTests(unittest.TestCase):
    """Direct behavioral proof, per patched file, that the write now goes through vn_time and
    is deterministic for a frozen instant -- the same technique test_vn_time.py already uses to
    prove vn_time itself is host-independent, applied here at each integration point."""

    def test_blacklist_sync_build_auto_rows_uses_frozen_vn_time(self):
        with mock.patch.object(blacklist_sync, "vn_now", return_value=FIXED_VN):
            df = blacklist_sync.build_auto_rows({"ABC": "TRADING_SUSPENSION"})
        self.assertEqual(df.iloc[0]["updated"], "2026-08-08")
        source = inspect.getsource(blacklist_sync.build_auto_rows)
        self.assertNotRegex(source, BARE_NOW_RE)

    def test_bctc_sync_normalize_report_scraped_at_uses_frozen_vn_time(self):
        with mock.patch.object(bctc_sync, "vn_now", return_value=FIXED_VN):
            out = bctc_sync.normalize_report(pd.DataFrame({"a": [1]}), "abc", "balance", "VCI")
        self.assertEqual(out.iloc[0]["scraped_at"], "2026-08-08 10:00")

    def test_bctc_sync_upsert_meta_updated_uses_frozen_vn_time(self):
        with mock.patch.object(bctc_sync, "vn_now", return_value=FIXED_VN):
            with mock.patch.object(bctc_sync, "META_FILE", Path(self._tmp_csv())):
                bctc_sync.upsert_meta("abc", "balance", "quarter", "done", 4)
                meta = bctc_sync.load_meta()
        self.assertEqual(meta.iloc[0]["updated"], "2026-08-08 10:00")

    @staticmethod
    def _tmp_csv():
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".csv")
        import os
        os.close(fd)
        os.unlink(path)  # upsert_meta/load_meta create it fresh
        return path

    def test_ai_analyzer_render_md_heading_uses_frozen_vn_time(self):
        report = {"market_regime": "neutral", "portfolio_risk": "medium", "regime_reason": "r",
                  "macro_summary": "m", "news_themes": [], "sector_view": "s",
                  "stock_notes": [], "action_plan": []}
        with mock.patch.object(ai_analyzer, "vn_now", return_value=FIXED_VN):
            md = ai_analyzer.render_md(report, "test-model")
        self.assertIn("2026-08-08", md.splitlines()[0])

    def test_ai_analyzer_filename_stamp_uses_frozen_vn_time(self):
        with mock.patch.object(ai_analyzer, "vn_now", return_value=FIXED_VN):
            stamp = ai_analyzer.vn_now().strftime("%Y%m%d")
        self.assertEqual(stamp, "20260808")
        source = inspect.getsource(ai_analyzer)
        self.assertIn('stamp = vn_now().strftime("%Y%m%d")', source)

    def test_vn_stock_pipeline_set_meta_updated_uses_frozen_vn_time(self):
        conn = sqlite3.connect(":memory:")
        try:
            vn_stock_pipeline.init_db(conn)
            with mock.patch.object(vn_stock_pipeline, "vn_now", return_value=FIXED_VN):
                vn_stock_pipeline.set_meta(conn, "ABC", "done", 100)
            row = conn.execute("SELECT updated FROM meta WHERE ticker='ABC'").fetchone()
            self.assertEqual(row[0], "2026-08-08 10:00")
        finally:
            conn.close()

    def test_shareholders_sync_normalize_updated_at_uses_frozen_vn_time(self):
        df = pd.DataFrame({"share_holder": ["Nguyen Van A"], "quantity": [1000],
                            "share_own_percent": [0.05]})
        with mock.patch.object(shareholders_sync, "vn_now", return_value=FIXED_VN):
            out = shareholders_sync.normalize(df, "abc", "VCI")
        self.assertEqual(out.iloc[0]["updated_at"], "2026-08-08 10:00")

    def test_shareholders_sync_log_line_uses_frozen_vn_time(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "shareholders_sync.log"
            with mock.patch.object(shareholders_sync, "vn_now", return_value=FIXED_VN), \
                 mock.patch.object(shareholders_sync, "LOG_FILE", str(log_path)):
                shareholders_sync.log("hello")
            content = log_path.read_text(encoding="utf-8")
        self.assertIn("[2026-08-08 10:00:00] hello", content)

    def test_shareholders_sync_set_progress_updated_uses_frozen_vn_time(self):
        conn = sqlite3.connect(":memory:")
        try:
            shareholders_sync.init_db(conn)
            with mock.patch.object(shareholders_sync, "vn_now", return_value=FIXED_VN):
                shareholders_sync.set_progress(conn, "ABC", "done", 10)
            row = conn.execute("SELECT updated FROM shareholders_progress WHERE ticker='ABC'").fetchone()
            self.assertEqual(row[0], "2026-08-08 10:00")
        finally:
            conn.close()

    def test_news_sync_fetched_column_source_uses_vn_now_not_bare_clock(self):
        """Structural check: the exact same vn_now().strftime(...) idiom given full behavioral
        proof above (blacklist_sync/bctc_sync/vn_stock_pipeline/shareholders_sync); a full
        RSS-feed fixture here would not exercise a materially different code path."""
        source = inspect.getsource(news_sync.sync_feed)
        self.assertIn("fetched = vn_now().strftime", source)
        # now_utc's own datetime.now(timezone.utc) is deliberately untouched (already explicit UTC):
        self.assertIn("datetime.now(timezone.utc)", source)
        # ...but no bare no-arg datetime.now() should remain anywhere in this function:
        self.assertNotRegex(source, BARE_NOW_RE)

    def test_shareholders_sync_persist_summary_updated_source_uses_vn_now(self):
        source = inspect.getsource(shareholders_sync.persist_summary)
        self.assertIn("vn_now()", source)
        self.assertNotRegex(source, BARE_NOW_RE)


class UntouchedDataAsOfIsWallClockIndependentTests(unittest.TestCase):
    """Occurrences classified DATA_AS_OF / SOURCE_OBSERVED_AT / FRESHNESS_INPUT were
    deliberately left untouched. Proves rerunning does not manufacture a newer data_as_of, and
    that the "now" used at test time cannot leak into a content-derived date."""

    def test_vn_stock_pipeline_ohlcv_date_is_derived_from_source_column_not_wall_clock(self):
        df = pd.DataFrame({"time": ["2026-08-01", "2026-08-02"], "open": [1, 2], "high": [1, 2],
                            "low": [1, 2], "close": [1, 2], "volume": [100, 200]})
        with mock.patch.object(vn_stock_pipeline, "vn_now", return_value=FIXED_VN):
            first = vn_stock_pipeline.normalize(df.copy(), "ABC", "VCI")
        later_instant = FIXED_VN.replace(year=FIXED_VN.year + 1)
        with mock.patch.object(vn_stock_pipeline, "vn_now", return_value=later_instant):
            second = vn_stock_pipeline.normalize(df.copy(), "ABC", "VCI")
        self.assertListEqual(list(first["date"]), ["2026-08-01", "2026-08-02"])
        self.assertListEqual(list(first["date"]), list(second["date"]))

    def test_vn_stock_pipeline_fetch_window_boundary_resolved_by_the_session_boundary_milestone(self):
        """cmd_backfill/cmd_update's `today` was FRESHNESS_INPUT, deliberately left unpatched by
        this milestone (a fetch-window boundary, not a cosmetic timestamp) and flagged as the
        named next milestone. That milestone ("VN Stock Fetch-Window Session-Boundary Contract")
        has since resolved it via vn_time.vn_today() (VN_CIVIL_DATE contract) -- superseding the
        prior assertion that the bare pattern was still present. Full contract/safety coverage
        lives in tests/test_vn_stock_pipeline_session_boundary_contract.py, not duplicated here."""
        source = inspect.getsource(vn_stock_pipeline.cmd_backfill) + inspect.getsource(vn_stock_pipeline.cmd_update)
        self.assertNotRegex(source, BARE_NOW_RE)
        self.assertIn("vn_today()", source)

    def test_macro_sync_untouched_entirely_no_diff_this_milestone(self):
        """macro_sync.py's freshness engine already separates content-derived `date` from
        operational `as_of` (own docstring), and its two naive `today` occurrences both become
        a stored data point's own as-of label (DATA_AS_OF) rather than an operational stamp --
        protected, not patched. Sanity-checked structurally rather than re-deriving the full
        Stage A trace here."""
        import macro_sync
        self.assertNotIn("from vn_time import", inspect.getsource(macro_sync))


if __name__ == "__main__":
    unittest.main()
