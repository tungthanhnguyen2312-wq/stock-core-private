"""Contract tests for the KBS trading-value coverage and safe-aggregation contract.

No test here opens a socket. The retained raw payloads are read read-only to prove the
inventory replays deterministically; they are never rewritten. Live acquisition is not a
dependency of any test in this module.

Numbering matches the milestone's required-test list.
"""

from __future__ import annotations

import ast
import hashlib
import json
import unittest
from pathlib import Path

import evidence_qualification_tiers as tiers
import kbs_capability_matrix as caps
import kbs_empirical_basis as kbs
import kbs_trading_value_coverage as coverage
import provider_price_basis_registry as registry

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = REPO_ROOT / "operations-review" / "kbs-empirical-basis-20260804"
CLOSEOUT_DIR = REPO_ROOT / "operations-review" / "kbs-trading-value-coverage-20260804"


def raw_row(session, *, va="omit", v=1_000_000, price=20_000):
    row = {"t": f"{session} 07:00", "o": price, "h": price + 50, "l": price - 50,
           "c": price, "v": v}
    if va != "omit":
        row["va"] = va
    return row


def parse(rows):
    return kbs.normalize_daily(kbs.parse_daily_payload({"data_day": rows}, symbol="HPG"))["rows"]


def records(rows):
    return [coverage.row_coverage_from_normalized(row) for row in rows]


# ---------------------------------------------------------------------------------
# 1-3: the states stay apart
# ---------------------------------------------------------------------------------


class RowStateTest(unittest.TestCase):
    def test_01_states_remain_distinct(self):
        rows = parse([
            raw_row("2026-07-20", va=1_000_000_000),   # present_numeric
            raw_row("2026-07-21", va=0),               # present_zero
            raw_row("2026-07-22", va=None),            # present_null
            raw_row("2026-07-23"),                     # field_omitted
            raw_row("2026-07-24", va="not-a-number"),  # malformed
        ])
        states = [row["kbs.observed_daily_trading_value_state"] for row in rows]
        self.assertEqual(states, [
            coverage.STATE_PRESENT_NUMERIC,
            coverage.STATE_PRESENT_ZERO,
            coverage.STATE_PRESENT_NULL,
            coverage.STATE_FIELD_OMITTED,
            coverage.STATE_MALFORMED,
        ])
        # The distinction survives into the coverage record.
        self.assertEqual(
            [r["trading_value_field_state"] for r in records(rows)], states
        )
        # row_missing is a sixth state and is not any of the above.
        self.assertIn(coverage.STATE_ROW_MISSING, coverage.ROW_STATES)
        self.assertNotIn(coverage.STATE_ROW_MISSING, states)
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.assert_row_state("missing_ish")

    def test_02_zero_is_not_converted_to_missing(self):
        rows = parse([raw_row("2026-07-21", va=0)])
        record = records(rows)[0]
        self.assertEqual(record["trading_value_field_state"], coverage.STATE_PRESENT_ZERO)
        self.assertTrue(record["trading_value_observed"])
        self.assertTrue(record["trading_value_usable_for_row_statistics"])
        self.assertEqual(record["trading_value_value"], 0.0)
        self.assertIsNone(record["exclusion_reason"])
        self.assertIn(coverage.STATE_PRESENT_ZERO, coverage.USABLE_STATES)
        # A zero counts toward coverage, so a window of zeros is complete, not absent.
        window = coverage.window_coverage(
            ticker="HPG", requested_window=["2026-07-21", "2026-07-21"], row_records=[record]
        )
        self.assertEqual(window["coverage_state"], coverage.COVERAGE_COMPLETE)
        self.assertEqual(window["present_zero_count"], 1)
        self.assertEqual(window["usable_count"], 1)

    def test_03_raw_omission_is_distinct_from_normalized_pipeline_omission(self):
        record = coverage.row_coverage(
            session_date="2026-07-23",
            raw_state=coverage.STATE_PRESENT_NUMERIC,
            value=1.0,
            normalized_field_present=False,
        )
        # The pipeline dropped it; the provider did not.
        self.assertFalse(record["normalized_field_present"])
        self.assertEqual(record["trading_value_field_state"], coverage.STATE_PRESENT_NUMERIC)
        self.assertTrue(record["trading_value_observed"])
        self.assertTrue(record["raw_state_is_not_normalized_state"])
        # The adapter drops va for every row regardless of what the provider sent, which is
        # why the normalized absence proves nothing about the source.
        drop = [t for t in kbs.ADAPTER_TRANSFORMATIONS if t["source_field"] == "va"][0]
        self.assertEqual(drop["operation"], "drop")
        self.assertFalse(drop["provider_declared"])
        # A row with no state at all cannot be classified by guessing from the value.
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.row_coverage_from_normalized(
                {"kbs.session_date": "2026-07-23", coverage.FIELD: None}
            )


# ---------------------------------------------------------------------------------
# 4-6: row-level use, and no synthesis
# ---------------------------------------------------------------------------------


class RowLevelAndSynthesisTest(unittest.TestCase):
    def partial_window(self):
        rows = parse([
            raw_row("2026-07-20", va=20_000_000_000),
            raw_row("2026-07-21", va=21_000_000_000),
            raw_row("2026-07-22"),
        ])
        return coverage.window_coverage(
            ticker="HPG", requested_window=["2026-07-20", "2026-07-22"],
            row_records=records(rows),
        )

    def test_04_row_level_display_remains_available_for_present_values(self):
        window = self.partial_window()
        self.assertEqual(window["coverage_state"], coverage.COVERAGE_PARTIAL_KNOWN)
        for operation in ("display_observed_trading_value", "row_implied_average_price",
                          "trading_value_chart_with_gaps", "coverage_report",
                          "trading_value_presence_anomaly_detection"):
            decision = coverage.evaluate_operation(operation, coverage=window)
            self.assertTrue(decision["allowed"], operation)
            self.assertEqual(decision["statistic_scope"], coverage.SCOPE_OBSERVED_ROWS_ONLY)

    def test_05_missing_va_is_never_silently_imputed(self):
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.impute(session_date="2026-07-22")
        dataset = coverage.dataset_coverage_contract([self.partial_window()])
        self.assertFalse(dataset["automatic_imputation_authorized"])
        self.assertFalse(dataset["missing_as_zero_authorized"])
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.assert_contract_fail_closed({
                **coverage.contract_snapshot(),
                "dataset": {**dataset, "automatic_imputation_authorized": True},
            })
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.assert_no_synthetic_trading_value({"imputed": True})
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.assert_no_synthetic_trading_value({"filled_from_price_times_volume": True})
        # An omitted row yields no value, and constructing one that carries a value fails.
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.row_coverage(
                session_date="2026-07-22", raw_state=coverage.STATE_FIELD_OMITTED, value=1.0
            )

    def test_06_adjusted_price_times_volume_cannot_impersonate_observed_va(self):
        contract = coverage.RECONSTRUCTED_FIELD_CONTRACT
        self.assertEqual(contract["source_field"], "derived")
        self.assertFalse(contract["provider_observed_trading_value"])
        self.assertEqual(contract["historical_interpretation"], "unsupported")
        self.assertFalse(contract["implemented"])
        self.assertFalse(contract["authorized"])
        self.assertNotEqual(coverage.RECONSTRUCTED_FIELD, coverage.FIELD)
        coverage.assert_no_synthetic_trading_value(contract)
        for bad in ({**contract, "provider_observed_trading_value": True},
                    {**contract, "historical_interpretation": "supported"},
                    {**contract, "authorized": True}):
            with self.assertRaises(coverage.TradingValueCoverageError):
                coverage.assert_no_synthetic_trading_value(bad)
        # Writing a derived number into the observed field is refused outright.
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.assert_no_synthetic_trading_value(
                {coverage.FIELD: 4.2e11, "source_field": "derived"}
            )
        # And the operation itself is unavailable by contract.
        decision = coverage.evaluate_operation(
            "synthesize_missing_trading_value_from_price_times_volume",
            coverage=self.partial_window(),
        )
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], coverage.REASON_SYNTHESIS)


# ---------------------------------------------------------------------------------
# 7-11: aggregation gates
# ---------------------------------------------------------------------------------


class AggregationTest(unittest.TestCase):
    def windows(self):
        complete = coverage.window_coverage(
            ticker="HPG", requested_window=["2026-07-20", "2026-07-21"],
            row_records=records(parse([
                raw_row("2026-07-20", va=20_000_000_000),
                raw_row("2026-07-21", va=21_000_000_000),
            ])),
        )
        partial = coverage.window_coverage(
            ticker="HPG", requested_window=["2026-07-20", "2026-07-22"],
            row_records=records(parse([
                raw_row("2026-07-20", va=20_000_000_000),
                raw_row("2026-07-21", va=21_000_000_000),
                raw_row("2026-07-22"),
            ])),
        )
        return complete, partial

    def test_07_a_complete_window_total_requires_complete_coverage(self):
        complete, partial = self.windows()
        allowed = coverage.evaluate_operation("period_total_trading_value", coverage=complete)
        self.assertTrue(allowed["allowed"])
        self.assertEqual(allowed["statistic_scope"], coverage.SCOPE_COMPLETE_WINDOW)
        refused = coverage.evaluate_operation("period_total_trading_value", coverage=partial)
        self.assertFalse(refused["allowed"])
        self.assertEqual(refused["reason"], coverage.REASON_COVERAGE)
        self.assertEqual(refused["alternative"], "rename_and_structure_the_output_as_partial")
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.build_result(
                operation="period_total_trading_value", value=4.1e10, coverage=partial
            )
        for name in ("turnover_for_period", "trading_value_growth",
                     "cross_period_trading_value_comparison",
                     "trading_value_technical_indicator"):
            self.assertFalse(
                coverage.evaluate_operation(name, coverage=partial)["allowed"], name
            )

    def test_08_partial_totals_must_be_labelled_observed_rows_only(self):
        _, partial = self.windows()
        result = coverage.build_result(
            operation="average_trading_value",
            value=coverage.mean_observed(records(parse([
                raw_row("2026-07-20", va=20_000_000_000),
                raw_row("2026-07-21", va=21_000_000_000),
                raw_row("2026-07-22"),
            ]))),
            coverage=partial,
        )
        self.assertEqual(result["statistic_scope"], coverage.SCOPE_OBSERVED_ROWS_ONLY)
        self.assertEqual(result["coverage_state"], coverage.COVERAGE_PARTIAL_KNOWN)
        self.assertTrue(result["not_comparable_to_complete_period_total"])
        self.assertIsNotNone(result["partial_coverage_warning"])
        self.assertEqual(result["covered_session_count"], 2)
        self.assertEqual(result["requested_session_count"], 3)
        for field in coverage.PARTIAL_RESULT_FIELDS:
            self.assertIn(field, result)

    def test_09_a_partial_average_cannot_be_labelled_a_complete_window_average(self):
        _, partial = self.windows()
        result = coverage.build_result(
            operation="average_trading_value", value=2.05e10, coverage=partial
        )
        for tampered, _ in (
            ({**result, "statistic_scope": coverage.SCOPE_COMPLETE_WINDOW}, "scope"),
            ({**result, "not_comparable_to_complete_period_total": False}, "comparability"),
            ({**result, "partial_coverage_warning": None}, "warning"),
            ({**result, "coverage_state": coverage.COVERAGE_COMPLETE,
              "statistic_scope": coverage.SCOPE_COMPLETE_WINDOW}, "state"),
        ):
            with self.assertRaises(coverage.TradingValueCoverageError):
                coverage.assert_result_labelled(tampered)
        stripped = {k: v for k, v in result.items() if k != "excluded_sessions"}
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.assert_result_labelled(stripped)

    def test_10_missing_sessions_remain_visible_in_exports(self):
        rows = parse([raw_row("2026-07-20", va=20_000_000_000), raw_row("2026-07-22")])
        window = coverage.window_coverage(
            ticker="HPG",
            requested_window=["2026-07-20", "2026-07-22"],
            row_records=records(rows),
            expected_sessions=["2026-07-20", "2026-07-21", "2026-07-22"],
            expected_session_source="dashboard-runtime/vn_stock.db:ohlcv[source=VCI]",
        )
        self.assertEqual(window["missing_sessions"], ["2026-07-21"])
        self.assertEqual(window["row_missing_count"], 1)
        self.assertEqual(window["requested_session_count"], 3)
        self.assertEqual(window["returned_row_count"], 2)
        result = coverage.build_result(
            operation="average_trading_value", value=2.0e10, coverage=window
        )
        self.assertIn("2026-07-21", result["missing_or_excluded_sessions"])
        self.assertIn("2026-07-22", result["missing_or_excluded_sessions"])
        # An expected-session list must say where it came from.
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.window_coverage(
                ticker="HPG", requested_window=["2026-07-20", "2026-07-22"],
                row_records=records(rows), expected_sessions=["2026-07-20"],
            )

    def test_11_coverage_ratio_is_deterministic(self):
        rows = records(parse([
            raw_row("2026-07-20", va=1), raw_row("2026-07-21"), raw_row("2026-07-22", va=2),
        ]))
        first = coverage.window_coverage(
            ticker="HPG", requested_window=["2026-07-20", "2026-07-22"], row_records=rows)
        second = coverage.window_coverage(
            ticker="HPG", requested_window=["2026-07-20", "2026-07-22"],
            row_records=list(reversed(rows)))
        self.assertEqual(first["coverage_ratio"], second["coverage_ratio"])
        self.assertEqual(first["coverage_ratio"], round(2 / 3, 6))
        self.assertEqual(first["covered_sessions"], second["covered_sessions"])
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
        )


# ---------------------------------------------------------------------------------
# 12-16: the association stays an association
# ---------------------------------------------------------------------------------


class AssociationTest(unittest.TestCase):
    def test_12_the_observed_association_does_not_populate_a_causal_explanation(self):
        association = coverage.OBSERVED_ASSOCIATION
        self.assertEqual(association["association"], "va_missing_on_tested_empirically_adjusted_rows")
        self.assertEqual(association["causal_explanation"], "unknown")
        self.assertEqual(association["provider_methodology"], "unknown")
        self.assertEqual(association["qualification"], tiers.OBSERVED_ONLY)
        coverage.assert_no_causal_claim(association)
        for bad in ({**association, "causal_explanation": "kbs strips va when it adjusts"},
                    {**association, "provider_methodology": "adjusted_rows_use_a_second_store"}):
            with self.assertRaises(coverage.TradingValueCoverageError):
                coverage.assert_no_causal_claim(bad)

    def test_12b_no_active_source_asserts_the_mechanism(self):
        """The Part G audit, as a standing check rather than a one-time reading.

        Scans active modules and docs only. The frozen evidence packages under
        `operations-review/` are deliberately excluded: they are not edited when the
        reasoning improves, and corrections against them are recorded separately.
        """
        targets = [REPO_ROOT / name for name in (
            "kbs_trading_value_coverage.py", "kbs_capability_matrix.py",
            "kbs_empirical_basis.py", "provider_price_basis_registry.py",
            "kbs_mutability_protocol.py",
            "docs/kbs_empirical_basis_qualification.md", "docs/STATE.md",
            "docs/ROADMAP.md", "docs/DECISIONS.md", "docs/AI_RULES.md",
        )]
        offenders = []
        for path in targets:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8").lower()
            for pattern in coverage.CAUSAL_OVERCLAIM_PATTERNS:
                for index, line in enumerate(text.splitlines(), 1):
                    if pattern in line and "does not establish" not in line:
                        offenders.append(f"{path.name}:{index}:{pattern}")
        # The coverage module itself holds the patterns as data; that is the one file
        # allowed to contain them verbatim.
        offenders = [o for o in offenders if not o.startswith("kbs_trading_value_coverage.py")]
        self.assertEqual(offenders, [], f"causal overclaim in active source: {offenders}")

        # The frozen artifacts keep their wording, and the correction is recorded instead.
        record = coverage.CORRECTED_CAUSAL_FRAMING
        self.assertFalse(record["measurements_changed"])
        self.assertFalse(record["evidence_changed"])
        self.assertFalse(record["artifacts_rewritten"])
        frozen = EVIDENCE_DIR / "KBS_EMPIRICAL_BASIS.md"
        self.assertTrue(frozen.exists())
        self.assertIn("Presence tracks the ex-right boundary", frozen.read_text(encoding="utf-8"))

    def test_13_the_association_cannot_be_generalized_universally(self):
        self.assertEqual(
            coverage.OBSERVED_ASSOCIATION["coverage_generalization"], "limited_to_retained_windows"
        )
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.assert_no_causal_claim(
                {**coverage.OBSERVED_ASSOCIATION, "coverage_generalization": "all_kbs_history"}
            )
        dataset = coverage.dataset_coverage_contract([])
        self.assertEqual(dataset["coverage_generalization"], "limited_to_retained_windows")
        self.assertEqual(dataset["causal_explanation"], "unknown")

    def test_14_unit_qualification_remains_empirically_deduced(self):
        dataset = coverage.dataset_coverage_contract([])
        self.assertEqual(dataset["trading_value_unit"], "VND")
        self.assertEqual(dataset["trading_value_unit_qualification"], tiers.EMPIRICALLY_DEDUCED)
        self.assertFalse(tiers.may_claim_official_semantics(tiers.EMPIRICALLY_DEDUCED))
        active = registry.active_verdict("KBS")
        self.assertEqual(active["trading_value_unit"], "VND")
        self.assertEqual(active["trading_value_unit_qualification"], tiers.EMPIRICALLY_DEDUCED)

    def test_15_trading_value_coverage_does_not_qualify_market_scope(self):
        dataset = coverage.dataset_coverage_contract([
            coverage.window_coverage(
                ticker="HPG", requested_window=["2026-07-20", "2026-07-20"],
                row_records=records(parse([raw_row("2026-07-20", va=1)])),
            )
        ])
        self.assertEqual(dataset["volume_market_scope"], "unknown")
        self.assertEqual(kbs.market_scope_contract()["volume_market_scope"], "unknown")
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.assert_contract_fail_closed({
                **coverage.contract_snapshot(),
                "dataset": {**dataset, "volume_market_scope": "qualified"},
            })

    def test_16_trading_value_coverage_does_not_unlock_liquidity(self):
        complete = coverage.window_coverage(
            ticker="HPG", requested_window=["2026-07-20", "2026-07-20"],
            row_records=records(parse([raw_row("2026-07-20", va=1)])),
        )
        self.assertEqual(complete["coverage_state"], coverage.COVERAGE_COMPLETE)
        for name in ("trading_value_liquidity_metric", "trading_value_capacity_metric",
                     "market_impact_from_trading_value", "official_market_turnover",
                     "official_vwap_claim", "negotiated_versus_matched_value_decomposition",
                     "cross_ticker_trading_value_ranking"):
            decision = coverage.evaluate_operation(name, coverage=complete)
            self.assertFalse(decision["allowed"], name)
            self.assertFalse(decision["liquidity_actionable"], name)
        self.assertFalse(coverage.dataset_coverage_contract([complete])["liquidity_actionable"])


# ---------------------------------------------------------------------------------
# 17-22: capabilities, consumers, provider scope, production
# ---------------------------------------------------------------------------------


class CapabilityAndConsumerTest(unittest.TestCase):
    def test_17_technical_price_indicators_remain_available(self):
        for name in ("kbs_moving_average", "kbs_rsi", "kbs_macd", "kbs_bollinger_bands",
                     "kbs_technical_pattern_research", "kbs_historical_chart",
                     "kbs_ohlcv_display"):
            self.assertTrue(caps.evaluate(name, existing_gates_passed=True)["available"], name)

    def test_18_volume_only_descriptive_capabilities_remain_available(self):
        for name in ("kbs_descriptive_volume_statistics", "kbs_provider_relative_volume",
                     "kbs_anomaly_detection", "kbs_descriptive_price_statistics",
                     "kbs_provider_price_momentum", "kbs_cross_provider_corroboration",
                     "kbs_descriptive_trading_value_statistics"):
            self.assertTrue(caps.evaluate(name, existing_gates_passed=True)["available"], name)
        caps.assert_matrix_fail_closed()

    def test_19_a_consumer_cannot_upgrade_partial_coverage(self):
        producer = coverage.window_coverage(
            ticker="HPG", requested_window=["2026-07-20", "2026-07-22"],
            row_records=records(parse([
                raw_row("2026-07-20", va=1), raw_row("2026-07-21"), raw_row("2026-07-22", va=2),
            ])),
        )
        coverage.assert_consumer_did_not_upgrade(
            producer_coverage=producer, consumer_coverage=producer
        )
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.assert_consumer_did_not_upgrade(
                producer_coverage=producer,
                consumer_coverage={**producer, "coverage_state": coverage.COVERAGE_COMPLETE},
            )
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.assert_consumer_did_not_upgrade(
                producer_coverage=producer,
                consumer_coverage={**producer, "usable_count": producer["usable_count"] + 1},
            )
        self.assertFalse(coverage.classify_consumer("some.new.reader")["allowed"])
        self.assertFalse(coverage.classify_consumer("opportunity_ranking.turnover_rank")["allowed"])
        # There are no permitted va consumers, because nothing reads va: the register holds
        # only the forbidden uses. Asserted so a future entry has to be justified by a trace.
        self.assertEqual(
            sorted(coverage.CONSUMER_REQUIREMENTS),
            ["opportunity_ranking.turnover_rank", "risk_liquidity.turnover_liquidity"],
        )
        self.assertTrue(
            all(req == coverage.UNAVAILABLE_BY_CONTRACT
                for req in coverage.CONSUMER_REQUIREMENTS.values())
        )

    def test_19b_the_derived_price_times_volume_quantity_is_registered_not_hidden(self):
        """gtgd20_ty exists, is derived, and is not observed va -- correcting ee057b9."""
        record = coverage.classify_derived_quantity("candlestick_patterns.gtgd20_ty_calc")
        self.assertFalse(record["reads_kbs_va"])
        self.assertFalse(record["provider_observed_trading_value"])
        self.assertFalse(record["is_official_turnover"])
        self.assertEqual(record["source_field"], "derived")
        self.assertIn("close * volume", record["expression"])
        for label in ("kbs.observed_daily_trading_value", "official_market_turnover",
                      "qualified_liquidity"):
            with self.assertRaises(coverage.TradingValueCoverageError):
                coverage.assert_derived_quantity_not_relabelled(
                    "candlestick_patterns.gtgd20_ty_calc", label=label
                )
        with self.assertRaises(coverage.TradingValueCoverageError):
            coverage.classify_derived_quantity("something.invented")

    def test_20_legacy_payloads_without_coverage_metadata_fail_closed_for_aggregates(self):
        legacy = {"provider": "KBS", "trading_value": 1.2e12}
        for aggregate in ("period_total_trading_value", "average_trading_value",
                          "turnover_for_period", "trading_value_growth"):
            decision = coverage.gate_legacy_payload(legacy, operation=aggregate)
            self.assertFalse(decision["allowed"], aggregate)
            self.assertEqual(decision["coverage_state"], coverage.COVERAGE_UNKNOWN)
        # Row-level display still works: the numbers in it are real.
        row_level = coverage.gate_legacy_payload(legacy, operation="display_observed_trading_value")
        self.assertTrue(row_level["allowed"])
        self.assertTrue(row_level["legacy"])
        modern = coverage.gate_legacy_payload(
            {"coverage_state": coverage.COVERAGE_COMPLETE}, operation="period_total_trading_value"
        )
        self.assertTrue(modern["allowed"])
        self.assertFalse(modern["legacy"])

    def test_21_other_providers_do_not_inherit_the_kbs_coverage_verdict(self):
        coverage.assert_no_provider_inheritance("KBS")
        for other in ("VCI", "TCBS", "SSI", "HOSE"):
            with self.assertRaises(coverage.TradingValueCoverageError):
                coverage.assert_no_provider_inheritance(other)
        for field in ("value", "trading_value", "turnover", "official_market_turnover",
                      "market_turnover", "exchange_turnover"):
            with self.assertRaises(coverage.TradingValueCoverageError):
                coverage.assert_no_generic_field_upgrade(field)
        coverage.assert_no_generic_field_upgrade("kbs.observed_daily_trading_value")

    def test_22_production_outputs_and_is_actionable_remain_unchanged(self):
        snapshot = caps.matrix_snapshot()
        self.assertEqual(snapshot["is_actionable_effect"], "none")
        self.assertFalse(snapshot["liquidity_actionable"])
        active = registry.active_verdict("KBS")
        self.assertFalse(active["raw_as_traded_eligible"])
        self.assertFalse(active["liquidity_actionable"])
        self.assertEqual(active["volume_market_scope"], "unknown")
        self.assertEqual(active["price_basis"], "empirically_event_adjusted")
        self.assertEqual(active["historical_mutability"], "not_observed")
        self.assertEqual(active["volume_adjustment_basis"], "not_observed")
        # The VCI verdict is untouched.
        self.assertEqual(
            registry.active_verdict("VCI")["historical_mutability"], "retrospectively_rewritten"
        )
        source = Path(coverage.__file__).read_text(encoding="utf-8")
        for forbidden in ("INSERT INTO", "UPDATE ", "write_text(", "write_bytes("):
            self.assertNotIn(forbidden, source, forbidden)


# ---------------------------------------------------------------------------------
# 23-24: replay determinism and network-free proof
# ---------------------------------------------------------------------------------


class ReplayTest(unittest.TestCase):
    def setUp(self):
        self.inventory_path = CLOSEOUT_DIR / "coverage_inventory.json"
        if not self.inventory_path.exists():
            self.skipTest("coverage inventory was not generated in this working tree")
        self.inventory = json.loads(self.inventory_path.read_text(encoding="utf-8"))

    def test_23_offline_replay_is_deterministic(self):
        observations = json.loads(
            (EVIDENCE_DIR / "observations.json").read_text(encoding="utf-8")
        )["observations"]
        rebuilt = []
        for observation in observations:
            raw = (EVIDENCE_DIR / observation["artifact"]).read_bytes()
            self.assertEqual(
                hashlib.sha256(raw).hexdigest(), observation["raw_response_sha256"]
            )
            rows = kbs.normalize_daily(
                kbs.parse_daily_payload(json.loads(raw.decode("utf-8")),
                                        symbol=observation["ticker"])
            )["rows"]
            rebuilt.append(
                coverage.window_coverage(
                    ticker=observation["ticker"],
                    requested_window=observation["requested_date_range"],
                    row_records=[coverage.row_coverage_from_normalized(row) for row in rows],
                )
            )
        recorded = {w["ticker"] + str(w["requested_window"]): w for w in self.inventory["windows"]}
        for window in rebuilt:
            key = window["ticker"] + str(window["requested_window"])
            self.assertIn(key, recorded)
            for field in ("coverage_state", "coverage_ratio", "usable_count",
                          "field_omitted_count", "present_numeric_count",
                          "present_zero_count", "present_null_count", "malformed_count"):
                self.assertEqual(window[field], recorded[key][field], f"{key}:{field}")
        # Totals match the recorded inventory exactly.
        self.assertEqual(
            sum(w["present_numeric_count"] for w in rebuilt),
            self.inventory["totals"]["present_numeric"],
        )
        self.assertEqual(
            sum(w["field_omitted_count"] for w in rebuilt),
            self.inventory["totals"]["field_omitted"],
        )

    def test_23b_immutable_raw_evidence_is_unchanged(self):
        manifest = json.loads(
            (EVIDENCE_DIR / "evidence_manifest.json").read_text(encoding="utf-8")
        )
        for entry in manifest["artifacts"]:
            raw = (EVIDENCE_DIR / entry["artifact"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["sha256"], entry["artifact"])

    def test_24_no_network_request_occurs(self):
        source = Path(coverage.__file__).read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in ("requests", "urllib", "urllib3", "http", "socket", "ssl",
                          "sqlite3", "subprocess", "asyncio"):
            self.assertNotIn(forbidden, imported, forbidden)
        self.assertEqual(
            imported,
            {"__future__", "typing", "evidence_qualification_tiers", "kbs_empirical_basis"},
        )


if __name__ == "__main__":
    unittest.main()
