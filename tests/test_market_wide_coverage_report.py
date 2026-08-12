from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import market_wide_coverage_report as coverage


def _manifest(**overrides):
    base = {
        "dataset": "ohlc", "run_id": "run-1", "run_scope_id": "scope-1",
        "started_at": "t0", "ended_at": "t1",
        "requested_units": ["HPG", "VNM", "QNS"],
        "successful_units": ["HPG", "VNM"],
        "failed_units": [{"unit_id": "QNS", "error_code": "http_status_404"}],
        "skipped_units": [],
        "output_dir": "raw/DNSE/ohlc/run-1", "checkpoint_file": "checkpoints/x.json",
    }
    base.update(overrides)
    return base


class BuildCoverageReportTests(unittest.TestCase):
    def test_basic_shape_and_universe_rollup(self):
        report = coverage.build_coverage_report(
            generated_at="2026-08-11T18:00:00+07:00", universe_status="COMPLETE",
            universe_declared_total=4, universe_discovered_count=4,
            universe_by_exchange={"STO": 3, "UPX": 1},
            universe_by_instrument_class={"EQUITY": 4},
            universe_symbols=["HPG", "VNM", "QNS", "ACB"],
            dataset_manifests=[_manifest()],
        )
        self.assertEqual(coverage.SCHEMA_VERSION, report["schema_version"])
        self.assertEqual(4, report["universe"]["discovered_count"])
        self.assertEqual({"STO": 3, "UPX": 1}, report["universe"]["by_exchange_raw"])
        self.assertFalse(report["is_ticker_qualification_table"])
        self.assertEqual(1, report["dataset_count"])

    def test_dataset_coverage_ratios(self):
        report = coverage.build_coverage_report(
            generated_at="t", universe_status="COMPLETE", universe_declared_total=4,
            universe_discovered_count=4, universe_by_exchange={}, universe_by_instrument_class={},
            universe_symbols=["HPG", "VNM", "QNS", "ACB"], dataset_manifests=[_manifest()],
        )
        entry = report["dataset_coverage"][0]
        self.assertEqual(3, entry["requested_unit_count"])
        self.assertEqual(2, entry["successful_unit_count"])
        self.assertEqual(1, entry["failed_unit_count"])
        self.assertAlmostEqual(2 / 3, entry["coverage_ratio_of_requested"], places=4)
        self.assertAlmostEqual(2 / 4, entry["coverage_ratio_of_universe"], places=4)

    def test_never_requested_symbols_distinguished_from_failed(self):
        report = coverage.build_coverage_report(
            generated_at="t", universe_status="COMPLETE", universe_declared_total=4,
            universe_discovered_count=4, universe_by_exchange={}, universe_by_instrument_class={},
            universe_symbols=["HPG", "VNM", "QNS", "ACB"], dataset_manifests=[_manifest()],
        )
        entry = report["dataset_coverage"][0]
        self.assertEqual(["ACB"], entry["never_requested_symbols"])
        self.assertEqual(["QNS"], entry["failed_symbols"])
        self.assertEqual(sorted(["QNS", "ACB"]), entry["not_yet_covered_symbols"])

    def test_empty_universe_does_not_divide_by_zero(self):
        report = coverage.build_coverage_report(
            generated_at="t", universe_status="COMPLETE", universe_declared_total=0,
            universe_discovered_count=0, universe_by_exchange={}, universe_by_instrument_class={},
            universe_symbols=[], dataset_manifests=[_manifest(requested_units=[], successful_units=[],
                                                              failed_units=[])],
        )
        entry = report["dataset_coverage"][0]
        self.assertIsNone(entry["coverage_ratio_of_requested"])
        self.assertIsNone(entry["coverage_ratio_of_universe"])

    def test_no_dataset_manifests_still_reports_universe(self):
        report = coverage.build_coverage_report(
            generated_at="t", universe_status="COMPLETE", universe_declared_total=2,
            universe_discovered_count=2, universe_by_exchange={"STO": 2},
            universe_by_instrument_class={"EQUITY": 2}, universe_symbols=["HPG", "VNM"],
        )
        self.assertEqual([], report["dataset_coverage"])
        self.assertEqual(0, report["dataset_count"])
        self.assertEqual(2, report["universe"]["discovered_count"])

    def test_unknown_instrument_class_count_surfaced(self):
        report = coverage.build_coverage_report(
            generated_at="t", universe_status="COMPLETE", universe_declared_total=5,
            universe_discovered_count=5,
            universe_by_exchange={"STO": 5},
            universe_by_instrument_class={"EQUITY": 3, "UNKNOWN_SECURITY_GROUP": 2},
            universe_symbols=["A", "B", "C", "D", "E"],
        )
        self.assertEqual(2, report["universe"]["unknown_instrument_class_count"])

    def test_coverage_report_is_content_addressed_and_immutable(self):
        report = coverage.build_coverage_report(
            generated_at="t", universe_status="COMPLETE", universe_declared_total=2,
            universe_discovered_count=2, security_master_discovered_count=5,
            universe_by_exchange={"STO": 5}, universe_by_instrument_class={"EQUITY": 2},
            universe_symbols=["HPG", "VNM"], dataset_manifests=[_manifest()],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            first = coverage.save_coverage_report(
                temp_dir, provider="DNSE", dataset="ohlc", run_id="run-1", report=report,
            )
            second = coverage.save_coverage_report(
                temp_dir, provider="DNSE", dataset="ohlc", run_id="run-1", report=report,
            )
            self.assertEqual(first, second)
            self.assertTrue(Path(first).is_file())
            self.assertEqual(5, json.loads(first.read_text(encoding="utf-8"))[
                "universe"]["security_master_discovered_count"])

    def test_known_semantic_unknowns_always_present_and_non_blocking(self):
        report = coverage.build_coverage_report(
            generated_at="t", universe_status="COMPLETE", universe_declared_total=0,
            universe_discovered_count=0, universe_by_exchange={}, universe_by_instrument_class={},
            universe_symbols=[],
        )
        topics = {item["topic"] for item in report["unresolved_semantic_issues"]}
        self.assertIn("board_code_semantics", topics)
        self.assertIn("ohlc_price_basis", topics)
        self.assertIn("volume_unit_transform", topics)

    def test_multiple_dataset_manifests_are_sorted_deterministically(self):
        report = coverage.build_coverage_report(
            generated_at="t", universe_status="COMPLETE", universe_declared_total=3,
            universe_discovered_count=3, universe_by_exchange={}, universe_by_instrument_class={},
            universe_symbols=["HPG", "VNM", "QNS"],
            dataset_manifests=[_manifest(dataset="quotes", run_id="run-2"), _manifest(dataset="ohlc", run_id="run-1")],
        )
        self.assertEqual(["ohlc", "quotes"], [entry["dataset"] for entry in report["dataset_coverage"]])

    def test_is_deterministic_for_identical_inputs(self):
        kwargs = dict(
            generated_at="t", universe_status="COMPLETE", universe_declared_total=3,
            universe_discovered_count=3, universe_by_exchange={"STO": 3},
            universe_by_instrument_class={"EQUITY": 3}, universe_symbols=["HPG", "VNM", "QNS"],
            dataset_manifests=[_manifest()],
        )
        first = coverage.build_coverage_report(**kwargs)
        second = coverage.build_coverage_report(**kwargs)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
