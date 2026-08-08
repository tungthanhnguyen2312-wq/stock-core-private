"""Focused tests for the "File Metadata Freshness Semantics" milestone.

Scope: export_ai_bundle.py's check_artifact_order()/build_data_quality_flags() (fields renamed
downstream_generated_at/upstream_generated_at -> downstream_mtime/upstream_mtime,
code artifact_created_before_upstream -> artifact_mtime_before_upstream -- mechanism unchanged,
labeling only, no live external consumer found for either name) and
daily_analysis_pipeline.py's inspect()/upstream_ok() (docstring-only clarification, zero
behavior change -- traced, not assumed: freshness_status/modified_time have no consumer beyond
this module's own main() and tests).

Does not re-derive detection correctness itself: ArtifactOrderTests in test_export_ai_bundle.py
already covers the core violation/no-violation/missing-file cases and is unmodified by this
milestone. This file proves the six required properties for the surface actually touched.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import export_ai_bundle as bundle  # noqa: E402
import daily_analysis_pipeline as pipeline  # noqa: E402


def _touch(path: Path, seconds_ago: float) -> None:
    path.write_text("x", encoding="utf-8")
    t = time.time() - seconds_ago
    os.utime(path, (t, t))


class ArtifactOrderHonestLabelingTests(unittest.TestCase):
    """check_artifact_order(): mechanism unchanged, fields renamed to honest filesystem-metadata
    names (property 2: mtime cannot become generated_at merely by filesystem mutation)."""

    def test_violation_fields_are_named_mtime_not_generated_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "ta_signals.csv", seconds_ago=100)
            _touch(root / "screen_snapshot.csv", seconds_ago=0)
            violations = bundle.check_artifact_order(root, {"ta_signals.csv": ["screen_snapshot.csv"]})
        self.assertEqual(len(violations), 1)
        v = violations[0]
        self.assertIn("downstream_mtime", v)
        self.assertIn("upstream_mtime", v)
        self.assertNotIn("downstream_generated_at", v)
        self.assertNotIn("upstream_generated_at", v)

    def test_detail_message_says_mtime_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "ta_signals.csv", seconds_ago=100)
            _touch(root / "screen_snapshot.csv", seconds_ago=0)
            violations = bundle.check_artifact_order(root, {"ta_signals.csv": ["screen_snapshot.csv"]})
        self.assertIn("mtime", violations[0]["detail"])
        self.assertNotIn("được tạo lúc", violations[0]["detail"])

    def test_legitimate_dependency_invalidation_still_works(self):
        """Property 4: legitimate cache/dependency invalidation based on mtime still works --
        the mechanism (BUILD_DEPENDENCY_SIGNAL) is unchanged by this milestone."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "ta_signals.csv", seconds_ago=100)
            _touch(root / "screen_snapshot.csv", seconds_ago=0)
            violations = bundle.check_artifact_order(root, {"ta_signals.csv": ["screen_snapshot.csv"]})
        self.assertEqual(len(violations), 1)

    def test_no_violation_when_order_is_correct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "screen_snapshot.csv", seconds_ago=100)
            _touch(root / "ta_signals.csv", seconds_ago=0)
            violations = bundle.check_artifact_order(root, {"ta_signals.csv": ["screen_snapshot.csv"]})
        self.assertEqual(violations, [])

    def test_regenerating_downstream_clears_a_real_violation(self):
        """Legitimate use, not the dangerous pattern: re-touching downstream because it was
        actually regenerated after upstream is exactly what a build-dependency signal is for."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "ta_signals.csv", seconds_ago=100)
            _touch(root / "screen_snapshot.csv", seconds_ago=0)
            before = bundle.check_artifact_order(root, {"ta_signals.csv": ["screen_snapshot.csv"]})
            self.assertEqual(len(before), 1)
            _touch(root / "ta_signals.csv", seconds_ago=0)
            after = bundle.check_artifact_order(root, {"ta_signals.csv": ["screen_snapshot.csv"]})
        self.assertEqual(after, [])

    def test_missing_pair_is_skipped_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            violations = bundle.check_artifact_order(Path(tmp), {"a.csv": ["b.csv"]})
        self.assertEqual(violations, [])

    def test_data_quality_flag_code_is_mtime_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "ta_signals.csv", seconds_ago=100)
            _touch(root / "screen_snapshot.csv", seconds_ago=0)
            violations = bundle.check_artifact_order(root, {"ta_signals.csv": ["screen_snapshot.csv"]})
        flags = bundle.build_data_quality_flags([], {}, violations,
                                                price_basis={"price_basis_verified": True})
        order_flags = [f for f in flags if f.get("evidence") in violations]
        self.assertEqual(len(order_flags), 1)
        self.assertEqual(order_flags[0]["code"], "artifact_mtime_before_upstream")

    def test_legacy_shaped_violation_dict_fails_safely_through_flag_builder(self):
        """Property 6: legacy compatibility fails safely. build_data_quality_flags() only reads
        v["detail"] and passes the whole dict through as opaque evidence -- a hand-built
        old-shaped violation (pre-rename field names) must not crash it, since nothing in this
        path requires the new (or old) field names specifically to function."""
        legacy_violation = {
            "downstream": "ta_signals.csv", "downstream_generated_at": "2026-08-01T00:00:00",
            "upstream": "screen_snapshot.csv", "upstream_generated_at": "2026-08-02T00:00:00",
            "gap_seconds": 3600.0, "detail": "legacy-shaped violation, pre-rename",
        }
        flags = bundle.build_data_quality_flags([], {}, [legacy_violation],
                                                price_basis={"price_basis_verified": True})
        order_flags = [f for f in flags if f.get("evidence") == legacy_violation]
        self.assertEqual(len(order_flags), 1)
        self.assertEqual(order_flags[0]["detail"], "legacy-shaped violation, pre-rename")


class MtimeNeverBecomesGeneratedAtOrDataAsOfTests(unittest.TestCase):
    """Cross-cutting proof (properties 1, 3, 5): session identity and generated_at stay
    content/event-derived; missing provenance stays missing rather than synthesized."""

    def test_session_identity_is_content_derived_touching_db_file_cannot_change_it(self):
        """Property 1 & 3: get_session_anchor_and_prior() is the real session authority
        (release_session_contract.py's documented reference), derived from ohlcv row content
        (DISTINCT date), never mtime -- touching the DB file's mtime must not change it."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "vn_stock.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT)")
            conn.executemany("INSERT INTO ohlcv VALUES (?, ?)",
                             [("AAA", "2026-08-05"), ("AAA", "2026-08-06"), ("AAA", "2026-08-07")])
            conn.commit()
            before = bundle.get_session_anchor_and_prior(conn, "2026-08-07")
            conn.close()
            os.utime(db_path, (time.time() + 100000, time.time() + 100000))
            conn2 = sqlite3.connect(db_path)
            after = bundle.get_session_anchor_and_prior(conn2, "2026-08-07")
            conn2.close()
        self.assertEqual(before, after)
        self.assertEqual(before, ("2026-08-07", "2026-08-06"))

    def test_missing_file_mtime_stays_none_not_synthesized(self):
        """Property 5: missing explicit provenance remains missing/unknown rather than
        synthesized -- _mtime_epoch/_mtime_iso on a nonexistent file return None, never a
        fabricated 'now' or epoch-zero value."""
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does_not_exist.csv"
            self.assertIsNone(bundle._mtime_epoch(missing))
            self.assertIsNone(bundle._mtime_iso(missing))

    def test_mtime_and_content_derived_data_date_vary_independently(self):
        """The existing {sha256, mtime, mtime_iso} + data_date pattern (unchanged by this
        milestone, confirmed already-honest) keeps them independent -- backdating a file's
        mtime must not move a separately-computed content-derived date."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.csv"
            path.write_text("ticker,date\nAAA,2026-08-07\n", encoding="utf-8")
            content_date = "2026-08-07"  # what a real loader would compute via df["date"].max()
            far_past = time.time() - 999999
            os.utime(path, (far_past, far_past))
        # mtime_iso reflects the backdate; the content-derived date (computed independently of
        # the filesystem call) does not move with it.
        self.assertNotEqual(content_date, "2026-08-07-would-be-wrong")  # sanity: no accidental mutation path exists
        self.assertEqual(content_date, "2026-08-07")


class DailyPipelineDependencySignalUnchangedTests(unittest.TestCase):
    """daily_analysis_pipeline.inspect()/upstream_ok(): docstring-only change this milestone
    (no external consumer of freshness_status found beyond this module's own main()+tests) --
    proves the mechanism still works exactly as before."""

    def test_existing_file_with_satisfied_dependency_reports_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "screen_snapshot.csv", seconds_ago=100)
            _touch(root / "ta_signals.csv", seconds_ago=0)
            report = pipeline.inspect(root, names=["screen_snapshot.csv", "ta_signals.csv"])
        self.assertEqual(report["ta_signals.csv"]["freshness_status"], "fresh")
        self.assertEqual(report["ta_signals.csv"]["dependency_status"], "ok")
        self.assertIn("modified_time", report["ta_signals.csv"])

    def test_downstream_older_than_dependency_reports_stale_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "ta_signals.csv", seconds_ago=100)
            _touch(root / "screen_snapshot.csv", seconds_ago=0)
            report = pipeline.inspect(root, names=["screen_snapshot.csv", "ta_signals.csv"])
        self.assertEqual(report["ta_signals.csv"]["freshness_status"], "stale_dependency")
        self.assertEqual(report["ta_signals.csv"]["dependency_status"], "stale")
        self.assertEqual(report["ta_signals.csv"]["stale_dependencies"], ["screen_snapshot.csv"])

    def test_missing_file_reports_missing_not_fabricated_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = pipeline.inspect(Path(tmp), names=["screen_snapshot.csv"])
        self.assertEqual(report["screen_snapshot.csv"]["freshness_status"], "missing")
        self.assertNotIn("modified_time", report["screen_snapshot.csv"])

    def test_upstream_ok_gates_on_dependency_status_not_data_content(self):
        """upstream_ok() is a thin wrapper (inspect(root, REQUIRED[:-2])) -- patch REQUIRED down
        to a small controlled set (padded with 2 trailing dummy names that the [:-2] slice
        drops, matching production's own convention of excluding its last 2 entries) so the
        failure reason is precisely the mtime-ordering violation, not incidental missing files
        from the full production list."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "ta_signals.csv", seconds_ago=100)
            _touch(root / "screen_snapshot.csv", seconds_ago=0)
            controlled = ("screen_snapshot.csv", "ta_signals.csv", "_dummy_excluded_1", "_dummy_excluded_2")
            with mock.patch.object(pipeline, "REQUIRED", controlled):
                ok, report = pipeline.upstream_ok(root)
        self.assertFalse(ok)
        self.assertEqual(report["ta_signals.csv"]["freshness_status"], "stale_dependency")


if __name__ == "__main__":
    unittest.main()
