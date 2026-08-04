"""Contract tests for the KBS trading-value export seam.

No test opens a socket, writes a database, or touches a runtime artifact. Live acquisition
is not a dependency. Numbering matches the milestone's required-test list; Consumer-side
items (11-13, 18-19) are proved in the Consumer repository and cross-checked here through
the frozen fixture.
"""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

import evidence_qualification_tiers as tiers
import kbs_capability_matrix as caps
import kbs_empirical_basis as kbs
import kbs_trading_value_coverage as cov
import kbs_trading_value_export as ex
import provider_price_basis_registry as registry

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "kbs_trading_value_export_block.json"


def raw_row(session, *, va="omit", v=1_000_000, price=20_000):
    row = {"t": f"{session} 07:00", "o": price, "h": price + 50, "l": price - 50,
           "c": price, "v": v}
    if va != "omit":
        row["va"] = va
    return row


def records(rows):
    normalized = kbs.normalize_daily(kbs.parse_daily_payload({"data_day": rows}, symbol="HPG"))["rows"]
    return [cov.row_coverage_from_normalized(row) for row in normalized]


def window(rows, *, start="2026-07-20", end="2026-07-22", expected=None):
    return cov.window_coverage(
        ticker="HPG", requested_window=[start, end], row_records=records(rows),
        expected_sessions=expected,
        expected_session_source="fixture" if expected else None,
    )


PARTIAL_ROWS = [
    raw_row("2026-07-20", va=20_000_000_000),
    raw_row("2026-07-21", va=21_000_000_000),
    raw_row("2026-07-22"),
]
COMPLETE_ROWS = [
    raw_row("2026-07-20", va=20_000_000_000),
    raw_row("2026-07-21", va=21_000_000_000),
]


class ExportBlockTest(unittest.TestCase):
    def test_01_producer_exports_the_canonical_block_with_a_value_observation(self):
        block = ex.build_row_block(records([raw_row("2026-07-20", va=2e10)])[0])
        for key in ex.BLOCK_KEYS:
            self.assertIn(key, block, key)
        for key in ex.COVERAGE_KEYS:
            self.assertIn(key, block["coverage"], key)
        self.assertEqual(block["provider"], "KBS")
        self.assertEqual(block["source_field"], "va")
        self.assertEqual(block["trading_value_unit"], "VND")
        self.assertEqual(block["trading_value_unit_qualification"], tiers.EMPIRICALLY_DEDUCED)
        self.assertEqual(block["coverage"]["statistic_scope"], cov.SCOPE_SINGLE_ROW)

    def test_02_the_block_uses_canonical_coverage_logic_not_a_parallel_recomputation(self):
        """Every exported count is copied from the canonical window record."""
        canonical = window(PARTIAL_ROWS)
        block = ex.build_window_block(canonical, statistic_scope=cov.SCOPE_OBSERVED_ROWS_ONLY)
        for key in ("coverage_state", "requested_session_count", "returned_row_count",
                    "present_numeric_count", "present_zero_count", "present_null_count",
                    "field_omitted_count", "malformed_count", "row_missing_count",
                    "usable_count", "coverage_ratio", "covered_sessions"):
            self.assertEqual(block["coverage"][key], canonical[key], key)

    def test_03_exported_counts_reconcile_with_the_exact_rows_used(self):
        block = ex.build_window_block(
            window(PARTIAL_ROWS), statistic_scope=cov.SCOPE_OBSERVED_ROWS_ONLY
        )
        c = block["coverage"]
        self.assertEqual(c["usable_count"], 2)
        self.assertEqual(c["requested_session_count"], 3)
        self.assertEqual(c["present_numeric_count"], 2)
        self.assertEqual(c["field_omitted_count"], 1)
        self.assertEqual(len(c["covered_sessions"]), c["usable_count"])
        self.assertEqual(c["covered_sessions"], ["2026-07-20", "2026-07-21"])
        self.assertEqual([e["session_date"] for e in c["excluded_sessions"]], ["2026-07-22"])

    def test_04_present_zero_survives_export(self):
        block = ex.build_row_block(records([raw_row("2026-07-21", va=0)])[0])
        self.assertEqual(block["trading_value_value"], 0.0)
        self.assertEqual(block["trading_value_field_state"], cov.STATE_PRESENT_ZERO)
        self.assertEqual(block["coverage"]["present_zero_count"], 1)
        self.assertEqual(block["coverage"]["usable_count"], 1)
        self.assertEqual(block["coverage"]["coverage_state"], cov.COVERAGE_COMPLETE)

    def test_05_field_omitted_remains_distinct_from_null(self):
        omitted = ex.build_row_block(records([raw_row("2026-07-22")])[0])
        null = ex.build_row_block(records([raw_row("2026-07-22", va=None)])[0])
        self.assertEqual(omitted["coverage"]["field_omitted_count"], 1)
        self.assertEqual(omitted["coverage"]["present_null_count"], 0)
        self.assertEqual(null["coverage"]["present_null_count"], 1)
        self.assertEqual(null["coverage"]["field_omitted_count"], 0)
        self.assertNotEqual(
            omitted["trading_value_field_state"], null["trading_value_field_state"]
        )

    def test_06_missing_rows_remain_explicit(self):
        canonical = window(
            [raw_row("2026-07-20", va=2e10), raw_row("2026-07-22")],
            expected=["2026-07-20", "2026-07-21", "2026-07-22"],
        )
        block = ex.build_window_block(canonical, statistic_scope=cov.SCOPE_OBSERVED_ROWS_ONLY)
        self.assertEqual(block["coverage"]["missing_sessions"], ["2026-07-21"])
        self.assertEqual(block["coverage"]["row_missing_count"], 1)
        self.assertEqual(block["coverage"]["returned_row_count"], 2)

    def test_07_partial_coverage_cannot_be_exported_as_complete(self):
        partial = window(PARTIAL_ROWS)
        with self.assertRaises(ex.TradingValueExportError):
            ex.build_window_block(partial, statistic_scope=cov.SCOPE_COMPLETE_WINDOW)
        with self.assertRaises(ex.TradingValueExportError):
            ex.build_window_block(partial, statistic_scope=cov.SCOPE_SINGLE_ROW)
        ok = ex.build_window_block(partial, statistic_scope=cov.SCOPE_OBSERVED_ROWS_ONLY)
        self.assertTrue(ok["not_comparable_to_complete_period_total"])
        self.assertIn(ex.TOKEN_PARTIAL_COVERAGE, ok["warning_tokens"])

    def test_08_a_complete_label_with_inconsistent_counts_is_rejected(self):
        block = ex.build_window_block(
            window(COMPLETE_ROWS, end="2026-07-21"), statistic_scope=cov.SCOPE_COMPLETE_WINDOW
        )
        ex.assert_block_valid(block)
        tampered = json.loads(json.dumps(block))
        tampered["coverage"]["requested_session_count"] = 11
        with self.assertRaises(ex.TradingValueExportError):
            ex.assert_block_valid(tampered)
        relabelled = json.loads(json.dumps(
            ex.build_window_block(window(PARTIAL_ROWS),
                                  statistic_scope=cov.SCOPE_OBSERVED_ROWS_ONLY)))
        relabelled["coverage"]["coverage_state"] = cov.COVERAGE_COMPLETE
        relabelled["coverage"]["statistic_scope"] = cov.SCOPE_COMPLETE_WINDOW
        with self.assertRaises(ex.TradingValueExportError):
            ex.assert_block_valid(relabelled)

    def test_09_missing_va_is_not_reconstructed_from_price_times_volume(self):
        block = ex.build_row_block(records([raw_row("2026-07-22")])[0])
        self.assertIsNone(block["trading_value_value"])
        self.assertFalse(block["coverage"]["automatic_imputation_authorized"])
        self.assertFalse(block["coverage"]["missing_as_zero_authorized"])
        with self.assertRaises(ex.TradingValueExportError):
            ex.assert_no_bare_value({"trading_value_value": 4.2e11})
        ex.assert_no_bare_value({"trading_value_value": 4.2e11, "coverage": {}})
        ex.assert_no_bare_value({"trading_value_value": None})
        # The derived quantity that does exist is registered as derived, not as va.
        self.assertFalse(
            cov.classify_derived_quantity("candlestick_patterns.gtgd20_ty_calc")["reads_kbs_va"]
        )

    def test_10_causal_explanation_remains_unknown(self):
        for block in (
            ex.build_row_block(records([raw_row("2026-07-20", va=2e10)])[0]),
            ex.build_window_block(window(PARTIAL_ROWS),
                                  statistic_scope=cov.SCOPE_OBSERVED_ROWS_ONLY),
        ):
            self.assertEqual(block["coverage"]["causal_explanation"], "unknown")
            self.assertEqual(
                block["coverage"]["coverage_generalization"], "limited_to_retained_windows"
            )
            tampered = json.loads(json.dumps(block))
            tampered["coverage"]["causal_explanation"] = "kbs strips va when it adjusts"
            with self.assertRaises(ex.TradingValueExportError):
                ex.assert_block_valid(tampered)


class LegacyTest(unittest.TestCase):
    def test_14_legacy_aggregate_without_coverage_fails_closed(self):
        result = ex.classify_legacy_payload({"trading_value": 1.2e12})
        self.assertEqual(result["legacy_class"], ex.LEGACY_AGGREGATE_WITHOUT_COVERAGE)
        self.assertFalse(result["aggregate_allowed"])
        self.assertFalse(result["display_allowed"])
        self.assertEqual(result["coverage_state"], cov.COVERAGE_UNKNOWN)
        for claim in ex.LEGACY_BLOCKED_CLAIMS:
            with self.assertRaises(ex.TradingValueExportError):
                ex.assert_legacy_claim_refused(result, claim=claim)

    def test_15_legacy_row_observation_remains_displayable_with_a_warning(self):
        result = ex.classify_legacy_payload(
            {"session_date": "2026-07-20", "trading_value_value": 1.1e12}
        )
        self.assertEqual(result["legacy_class"], ex.LEGACY_ROW_OBSERVATION)
        self.assertTrue(result["display_allowed"])
        self.assertFalse(result["aggregate_allowed"])
        self.assertIn(ex.TOKEN_PROVIDER_AUTHORITY, result["warning_tokens"])
        self.assertIn("cannot support any statement about an interval",
                      result["legacy_provenance_warning"])
        with self.assertRaises(ex.TradingValueExportError):
            ex.assert_legacy_claim_refused(result, claim="period_total_trading_value")

    def test_15b_absence_of_metadata_never_defaults_to_complete(self):
        for payload in ({"trading_value": 1.0}, {"session_date": "2026-07-20", "va": 1.0},
                        {"close": 20000}):
            result = ex.classify_legacy_payload(payload)
            self.assertNotEqual(result["coverage_state"], cov.COVERAGE_COMPLETE)
            self.assertEqual(result["coverage_state"], cov.COVERAGE_UNKNOWN)
        self.assertEqual(
            ex.classify_legacy_payload({"close": 20000})["legacy_class"],
            ex.LEGACY_NO_TRADING_VALUE,
        )
        self.assertTrue(ex.classify_legacy_payload({"close": 20000})["unaffected"])


class AggregateGateTest(unittest.TestCase):
    def test_16_complete_window_totals_require_complete_coverage(self):
        complete = window(COMPLETE_ROWS, end="2026-07-21")
        block = ex.build_window_block(complete, statistic_scope=cov.SCOPE_COMPLETE_WINDOW)
        self.assertEqual(block["coverage"]["statistic_scope"], cov.SCOPE_COMPLETE_WINDOW)
        self.assertFalse(block["not_comparable_to_complete_period_total"])
        self.assertFalse(
            cov.evaluate_operation("period_total_trading_value",
                                   coverage=window(PARTIAL_ROWS))["allowed"]
        )

    def test_17_partial_aggregates_are_labelled_observed_rows_only(self):
        block = ex.build_window_block(
            window(PARTIAL_ROWS), statistic_scope=cov.SCOPE_OBSERVED_ROWS_ONLY
        )
        self.assertEqual(block["coverage"]["statistic_scope"], cov.SCOPE_OBSERVED_ROWS_ONLY)
        self.assertEqual(block["coverage"]["partial_coverage_warning"],
                         ex.warning_text(ex.TOKEN_PARTIAL_COVERAGE))
        self.assertTrue(block["not_comparable_to_complete_period_total"])


class WarningAndCapabilityTest(unittest.TestCase):
    def test_18_the_authority_warning_distinguishes_observation_from_official_turnover(self):
        text = ex.warning_text(ex.TOKEN_PROVIDER_AUTHORITY)
        self.assertIn("provider observation", text)
        self.assertIn("not an official exchange trading-value contract", text)
        partial = ex.warning_text(ex.TOKEN_PARTIAL_COVERAGE)
        self.assertIn("observed rows only", partial)
        self.assertIn("not imputed or treated as zero", partial)
        self.assertIn("not official market turnover", partial)
        # The authority token is unconditional, not replaced by the partial one.
        self.assertIn(ex.TOKEN_PROVIDER_AUTHORITY, ex.warnings_for(cov.COVERAGE_PARTIAL_KNOWN))
        self.assertIn(ex.TOKEN_PARTIAL_COVERAGE, ex.warnings_for(cov.COVERAGE_PARTIAL_KNOWN))
        self.assertEqual(ex.warnings_for(cov.COVERAGE_COMPLETE), [ex.TOKEN_PROVIDER_AUTHORITY])
        with self.assertRaises(ex.TradingValueExportError):
            ex.warning_text("invented_token")

    def test_19_no_export_infers_liquidity_from_trading_value(self):
        text = " ".join(ex.CANONICAL_WARNINGS.values()).lower()
        self.assertIn("not", text)
        self.assertIn("qualified liquidity evidence", text)
        snapshot = ex.assert_export_fail_closed()
        self.assertFalse(snapshot["liquidity_actionable"])
        self.assertEqual(snapshot["is_actionable_effect"], "none")
        self.assertEqual(kbs.market_scope_contract()["volume_market_scope"], "unknown")

    def test_20_technical_price_capabilities_remain_available(self):
        for name in ("kbs_moving_average", "kbs_rsi", "kbs_macd", "kbs_bollinger_bands",
                     "kbs_ohlcv_display", "kbs_historical_chart",
                     "kbs_technical_pattern_research"):
            self.assertTrue(caps.evaluate(name, existing_gates_passed=True)["available"], name)

    def test_21_volume_only_descriptive_capabilities_remain_available(self):
        for name in ("kbs_descriptive_volume_statistics", "kbs_provider_relative_volume",
                     "kbs_provider_price_momentum", "kbs_anomaly_detection",
                     "kbs_descriptive_trading_value_statistics"):
            self.assertTrue(caps.evaluate(name, existing_gates_passed=True)["available"], name)
        caps.assert_matrix_fail_closed()

    def test_22_other_providers_do_not_inherit_kbs_coverage_semantics(self):
        for other in ("VCI", "TCBS", "SSI", "HOSE"):
            with self.assertRaises(cov.TradingValueCoverageError):
                cov.assert_no_provider_inheritance(other)
        for field in ("trading_value", "turnover", "official_market_turnover", "value"):
            with self.assertRaises(cov.TradingValueCoverageError):
                cov.assert_no_generic_field_upgrade(field)
        block = ex.build_row_block(records([raw_row("2026-07-20", va=2e10)])[0])
        with self.assertRaises(ex.TradingValueExportError):
            ex.assert_block_valid({**block, "provider": "VCI"})


class DeterminismAndAbsenceTest(unittest.TestCase):
    def test_23_export_is_deterministic_and_matches_the_frozen_fixture(self):
        first = ex.build_window_block(window(PARTIAL_ROWS),
                                      statistic_scope=cov.SCOPE_OBSERVED_ROWS_ONLY)
        second = ex.build_window_block(window(PARTIAL_ROWS),
                                       statistic_scope=cov.SCOPE_OBSERVED_ROWS_ONLY)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertTrue(FIXTURE.exists(), "cross-repository fixture is missing")
        frozen = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(frozen["partial_window_block"], first)
        self.assertEqual(frozen["warnings_fingerprint"], ex.warnings_fingerprint())
        self.assertEqual(
            frozen["row_block"],
            ex.build_row_block(records([raw_row("2026-07-20", va=2e10)])[0]),
        )

    def test_23b_the_absence_of_an_active_value_path_is_recorded_not_implied(self):
        self.assertIsNone(ex.ACTIVE_EXPORT_PATH)
        absence = ex.ABSENCE_OF_ACTIVE_VALUE_PATH
        self.assertFalse(absence["kbs_va_exported"])
        self.assertTrue(absence["seam_is_future_safe"])
        self.assertGreaterEqual(len(absence["trace"]), 5)
        compat = ex.compatibility()
        self.assertFalse(compat["bundle_schema_version_bumped"])
        self.assertTrue(compat["backward_readable"])
        self.assertEqual(compat["unrelated_schemas_bumped"], [])

    def test_24_production_artifacts_and_is_actionable_remain_unchanged(self):
        self.assertEqual(caps.matrix_snapshot()["is_actionable_effect"], "none")
        active = registry.active_verdict("KBS")
        self.assertFalse(active["liquidity_actionable"])
        self.assertFalse(active["raw_as_traded_eligible"])
        self.assertEqual(active["trading_value_unit"], "VND")
        self.assertEqual(active["volume_market_scope"], "unknown")
        self.assertEqual(
            registry.active_verdict("VCI")["historical_mutability"], "retrospectively_rewritten"
        )
        source = Path(ex.__file__).read_text(encoding="utf-8")
        for forbidden in ("INSERT INTO", "UPDATE ", "write_text(", "write_bytes("):
            self.assertNotIn(forbidden, source, forbidden)

    def test_25_no_network_request_occurs(self):
        source = Path(ex.__file__).read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in ("requests", "urllib", "http", "socket", "ssl", "sqlite3",
                          "subprocess", "asyncio"):
            self.assertNotIn(forbidden, imported, forbidden)
        self.assertEqual(
            imported,
            {"__future__", "hashlib", "json", "typing",
             "evidence_qualification_tiers", "kbs_trading_value_coverage"},
        )


if __name__ == "__main__":
    unittest.main()
