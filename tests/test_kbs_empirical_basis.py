"""Contract tests for the bounded KBS empirical price/volume basis qualification.

Every fixture below is derived from a real, retained KBS payload shape. No test in this
module opens a socket: live acquisition is confined to ``kbs_empirical_basis.acquire`` and
the runner script, neither of which is exercised here against a real endpoint. The retained
evidence artifacts are read only to prove replay determinism and are never rewritten.

The numbering matches the milestone's required-test list so a reader can check coverage
without reverse-engineering it from the method names.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import evidence_qualification_tiers as tiers
import kbs_capability_matrix as caps
import kbs_empirical_basis as kbs
import provider_price_basis_registry as registry

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = REPO_ROOT / "operations-review" / "kbs-empirical-basis-20260804"


# ---------------------------------------------------------------------------------
# Fixtures -- shaped exactly like the retained payloads
# ---------------------------------------------------------------------------------


def payload(rows):
    return {"symbol": "HPG", "data_day": rows}


def on_lattice_rows(*, ticker_price=20000, count=6, start_day=20):
    """Sessions whose prices are all tick multiples, each carrying a coherent ``va``.

    Volumes are session-realistic tens of millions on purpose. At a thousand-share reading
    they would imply tens of billions of shares changing hands in a day, which is what lets
    the degeneracy breaker do its work -- a toy volume would leave both members of the
    quotient class survivable and the fixture would silently stop testing anything.
    """
    rows = []
    for index in range(count):
        close = ticker_price + index * 50
        volume = 20_000_000 + index * 1_000
        rows.append(
            {
                "t": f"2026-07-{start_day + index:02d} 07:00",
                "o": close,
                "h": close + 50,
                "l": close - 50,
                "c": close,
                "v": volume,
                "va": volume * close,
            }
        )
    return rows


def off_lattice_rows(*, count=3):
    """Restated sessions: off the tick lattice and, as the provider does, without ``va``."""
    return [
        {
            "t": f"2026-07-{10 + index:02d} 07:00",
            "o": 19_987 + index,
            "h": 20_013 + index,
            "l": 19_951 + index,
            "c": 19_993 + index,
            "v": 900_000 + index,
        }
        for index in range(count)
    ]


CASH_EVENT = {
    "kind": kbs.EVENT_KIND_CASH,
    "ex_date": "2026-07-20",
    "detail": "DIV cash dividend",
    "evidence_identity": "vn_stock.db:corporate_event_records[ticker=HPG,event_code=DIV]",
}
SHARE_EVENT = {
    "kind": kbs.EVENT_KIND_SHARE,
    "ex_date": "2026-07-20",
    "detail": "ISS share issue",
    "evidence_identity": "vn_stock.db:corporate_event_records[ticker=HPG,event_code=ISS]",
}


def empirical_record(**overrides):
    record = {
        "test_method": "lattice conformance across qualified ex-right boundaries",
        "tested_fields": ["kbs.raw_c"],
        "tested_tickers": ["HPG", "VCB"],
        "tested_date_windows": ["HPG:2026-07-10..2026-07-25", "VCB:2026-07-16..2026-07-30"],
        "event_evidence": [CASH_EVENT],
        "raw_artifact_hashes": ["a" * 64],
        "transformation_version": kbs.TRANSFORMATION_CODE_IDENTITY,
        "alternative_explanations_considered": ["coincidental rounding"],
        "falsification_attempts": ["a no-event control window was requested"],
        "confidence": "moderate",
        "scope_limitations": ["two tickers, 2026 only"],
        "retrieval_timestamps": ["2026-08-04T06:58:01Z"],
        "historical_mutability": "not_observed",
    }
    record.update(overrides)
    return record


def normalized(rows):
    return kbs.normalize_daily(kbs.parse_daily_payload(payload(rows), symbol="HPG"))["rows"]


# ---------------------------------------------------------------------------------
# 1-3: what the qualification ladder does and does not allow
# ---------------------------------------------------------------------------------


class QualificationLadderTest(unittest.TestCase):
    def test_01_field_identity_qualifies_while_basis_stays_unknown(self):
        """A known field identity is compatible with an entirely unknown basis."""
        start = kbs.STARTING_CONTRACT
        for field in ("open", "high", "low", "close", "volume", "trading_value", "time"):
            self.assertEqual(start[f"{field}_field_identity"], "qualified")
        for dimension in (
            "price_basis",
            "historical_mutability",
            "volume_unit",
            "volume_adjustment_basis",
            "volume_market_scope",
            "trading_value_unit",
        ):
            self.assertEqual(start[dimension], "unknown")
        self.assertFalse(start["liquidity_actionable"])

    def test_02_missing_documentation_does_not_make_ohlcv_unusable(self):
        """The Phase 1C premise holds; the conclusion drawn from it does not."""
        snapshot = caps.matrix_snapshot()
        self.assertEqual(snapshot["documented_semantics"], "absent")
        self.assertEqual(snapshot["field_identity"], "qualified")
        self.assertEqual(snapshot["descriptive_capability"], "available")
        for name in ("kbs_ohlcv_display", "kbs_historical_chart"):
            self.assertIn(name, caps.AVAILABLE_CAPABILITIES)

    def test_03_empirical_deduction_requires_reproducible_evidence_and_scope(self):
        """Every retention field is required, and empties are refused as hard as absences."""
        accepted = tiers.assert_empirically_deduced(empirical_record())
        self.assertEqual(accepted["qualification"], tiers.EMPIRICALLY_DEDUCED)
        self.assertEqual(accepted["coverage_generalization"], tiers.COVERAGE_LIMITED)
        for field in tiers.EMPIRICAL_RECORD_FIELDS:
            incomplete = empirical_record()
            del incomplete[field]
            with self.assertRaises(tiers.QualificationError):
                tiers.assert_empirically_deduced(incomplete)
        with self.assertRaises(tiers.QualificationError):
            tiers.assert_empirically_deduced(empirical_record(falsification_attempts=[]))
        with self.assertRaises(tiers.QualificationError):
            tiers.assert_empirically_deduced(empirical_record(confidence="certain"))
        with self.assertRaises(tiers.QualificationError):
            tiers.assert_scope_not_exceeded(accepted, claimed_windows=["HPG:2019-01-01..2019-12-31"])

    def test_04_one_window_cannot_establish_a_provider_methodology(self):
        one_window = empirical_record(
            tested_date_windows=["HPG:2026-07-10..2026-07-25"],
            provider_methodology="standard_back_adjustment",
        )
        with self.assertRaises(tiers.QualificationError):
            tiers.assert_single_window_insufficient(one_window)
        # The same single window is fine as long as it claims no methodology.
        tiers.assert_single_window_insufficient(
            empirical_record(tested_date_windows=["HPG:2026-07-10..2026-07-25"])
        )


# ---------------------------------------------------------------------------------
# 5-7: what a price window can and cannot prove
# ---------------------------------------------------------------------------------


class PriceBasisTest(unittest.TestCase):
    def test_05_smooth_boundary_alone_cannot_prove_complete_adjustment_semantics(self):
        """A fully on-lattice control window is inconclusive, not a clean bill of health."""
        rows = normalized(on_lattice_rows())
        result = kbs.classify_price_basis(
            lattice=kbs.lattice_profile(rows),
            boundary_date=kbs.lattice_boundary(rows),
            qualified_events=[],
            window_contains_event=False,
        )
        self.assertEqual(result["verdict"], "inconclusive")
        self.assertFalse(result["excludes_raw_as_traded"])
        self.assertFalse(result["supports_raw_as_traded"])

    def test_05b_event_adjusted_window_never_claims_a_methodology(self):
        rows = normalized(off_lattice_rows() + on_lattice_rows(count=4))
        result = kbs.classify_price_basis(
            lattice=kbs.lattice_profile(rows),
            boundary_date=kbs.lattice_boundary(rows),
            qualified_events=[CASH_EVENT],
            window_contains_event=True,
        )
        self.assertEqual(result["verdict"], "cash_distribution_adjusted_observed")
        self.assertTrue(result["excludes_raw_as_traded"])
        contract = kbs.price_basis_contract(
            merged=kbs.merge_price_verdicts({"W1": result}),
            historical_mutability="not_observed",
            tested_windows=["HPG:2026-07-10..2026-07-25", "VCB:2026-07-16..2026-07-30"],
            empirical_record=empirical_record(),
        )
        self.assertEqual(contract["provider_methodology"], "unknown")
        self.assertEqual(contract["coverage_generalization"], tiers.COVERAGE_LIMITED)
        kbs.assert_contract_fail_closed(contract)

    def test_06_historical_rewriting_prevents_raw_as_traded_eligibility(self):
        supporting = {
            "W1": {
                "verdict": "raw_as_traded_empirically_supported",
                "supports_raw_as_traded": True,
                "excludes_raw_as_traded": False,
                "matched_events": [SHARE_EVENT],
            }
        }
        merged = kbs.merge_price_verdicts(supporting)
        eligible = kbs.price_basis_contract(
            merged=merged,
            historical_mutability="not_observed",
            tested_windows=["HPG:a..b", "VCB:c..d"],
            empirical_record=empirical_record(),
        )
        self.assertTrue(eligible["raw_as_traded_eligible"])
        rewritten = kbs.price_basis_contract(
            merged=merged,
            historical_mutability="retrospectively_rewritten",
            tested_windows=["HPG:a..b", "VCB:c..d"],
            empirical_record=empirical_record(historical_mutability="retrospectively_rewritten"),
        )
        self.assertFalse(rewritten["raw_as_traded_eligible"])
        with self.assertRaises(kbs.KBSBasisError):
            kbs.assert_contract_fail_closed({**rewritten, "raw_as_traded_eligible": True})

    def test_06b_contradictory_windows_conflict_rather_than_pick_the_newer(self):
        merged = kbs.merge_price_verdicts(
            {
                "W1": {
                    "verdict": "raw_as_traded_empirically_supported",
                    "supports_raw_as_traded": True,
                    "excludes_raw_as_traded": False,
                    "matched_events": [],
                },
                "W2": {
                    "verdict": "cash_distribution_adjusted_observed",
                    "supports_raw_as_traded": False,
                    "excludes_raw_as_traded": True,
                    "matched_events": [CASH_EVENT],
                },
            }
        )
        self.assertEqual(merged["verdict"], "conflicted")
        resolved = tiers.resolve_active(
            [
                {"verdict": "raw_as_traded", "qualification": tiers.EMPIRICALLY_DEDUCED},
                {"verdict": "event_adjusted", "qualification": tiers.OBSERVED_ONLY},
            ]
        )
        self.assertEqual(resolved["qualification"], tiers.CONFLICTED)

    def test_07_cross_provider_equality_cannot_upgrade_authority(self):
        contract = kbs.price_basis_contract(
            merged=kbs.merge_price_verdicts(
                {
                    "W1": {
                        "verdict": "cash_distribution_adjusted_observed",
                        "supports_raw_as_traded": False,
                        "excludes_raw_as_traded": True,
                        "matched_events": [CASH_EVENT],
                    }
                }
            ),
            historical_mutability="not_observed",
            tested_windows=["HPG:a..b", "VCB:c..d"],
            empirical_record=empirical_record(),
        )
        corroborated = kbs.apply_cross_provider_agreement(
            contract, agreement={"counterparty": "VCI", "close_exact_matches": 9}
        )
        self.assertEqual(
            corroborated["price_basis_qualification"], contract["price_basis_qualification"]
        )
        self.assertFalse(corroborated["cross_provider_comparison_upgraded_verdict"])
        self.assertFalse(corroborated["corroboration_upgraded_qualification"])
        self.assertFalse(tiers.may_claim_official_semantics(tiers.EMPIRICALLY_DEDUCED))

    def test_07b_events_are_inputs_and_are_never_inferred(self):
        for bad in ({"kind": "guess", "ex_date": "2026-07-20", "evidence_identity": "x"},
                    {"kind": kbs.EVENT_KIND_CASH, "ex_date": "", "evidence_identity": "x"},
                    {"kind": kbs.EVENT_KIND_CASH, "ex_date": "2026-07-20", "evidence_identity": " "}):
            with self.assertRaises(kbs.KBSBasisError):
                kbs.assert_qualified_event(bad)


# ---------------------------------------------------------------------------------
# 8-12: units, and what a unit result does not settle
# ---------------------------------------------------------------------------------


class UnitScalingTest(unittest.TestCase):
    def test_08_candidate_scaling_must_survive_multiple_rows_and_tickers(self):
        one_ticker = {"HPG": normalized(on_lattice_rows(count=25))}
        result = kbs.select_unit_scales(one_ticker)
        self.assertEqual(result["volume_unit"], "inconclusive")
        self.assertEqual(result["reason"], "insufficient_sample_for_unit_selection")

        too_few_rows = {
            "HPG": normalized(on_lattice_rows(count=5)),
            "VCB": normalized(on_lattice_rows(ticker_price=54_000, count=5)),
        }
        self.assertEqual(
            kbs.select_unit_scales(too_few_rows)["reason"], "insufficient_sample_for_unit_selection"
        )

    def test_09_competing_scale_factors_are_rejected(self):
        rows = {
            "HPG": normalized(on_lattice_rows(count=15)),
            "VCB": normalized(on_lattice_rows(ticker_price=54_000, count=15)),
        }
        result = kbs.select_unit_scales(
            rows,
            share_count_bounds={
                "HPG": {"shares_outstanding": 8.4e9, "evidence_identity": "fixture"},
                "VCB": {"shares_outstanding": 9.0e9, "evidence_identity": "fixture"},
            },
        )
        self.assertEqual(result["volume_unit"], "shares")
        self.assertEqual(result["trading_value_unit"], "VND")
        self.assertEqual(result["qualification"], tiers.EMPIRICALLY_DEDUCED)
        rejected = {
            (item["volume_scale"], item["trading_value_scale"])
            for item in result["rejected_candidates"]
        }
        # Every candidate with a different quotient must have been rejected outright.
        for volume_scale in kbs.VOLUME_SCALES:
            for value_scale in kbs.TRADING_VALUE_SCALES:
                if kbs.scale_quotient(volume_scale, value_scale) != result["scale_quotient"]:
                    self.assertIn((volume_scale, value_scale), rejected)

    def test_09b_the_vwap_test_alone_only_earns_the_quotient(self):
        """Without an absolute anchor the units stay unnamed, and the quotient is reported."""
        rows = {
            "HPG": normalized(on_lattice_rows(count=15)),
            "VCB": normalized(on_lattice_rows(ticker_price=54_000, count=15)),
        }
        result = kbs.select_unit_scales(rows, share_count_bounds=None)
        self.assertEqual(result["volume_unit"], "scaled_units")
        self.assertEqual(result["trading_value_unit"], "scaled_units")
        self.assertEqual(result["qualification"], tiers.OBSERVED_ONLY)
        self.assertEqual(result["scale_quotient"], 1.0)
        self.assertFalse(result["degeneracy_resolution"]["resolved"])

    def test_10_missing_v_or_va_stays_missing(self):
        rows = normalized(off_lattice_rows(count=2) + on_lattice_rows(count=2))
        self.assertEqual(
            [row["kbs.observed_daily_trading_value"] for row in rows[:2]], [None, None]
        )
        self.assertFalse(kbs.row_is_eligible(rows[0]))
        # A zero is an observation and is not merged with a missing value.
        zero_row = dict(rows[-1])
        zero_row["kbs.observed_daily_volume"] = 0
        self.assertFalse(kbs.row_is_eligible(zero_row))
        parsed = kbs.parse_daily_payload(payload(off_lattice_rows(count=1)), symbol="HPG")
        self.assertIsNone(parsed[0]["kbs.raw_va"])

    def test_11_invalid_vwap_geometry_does_not_force_a_unit_conclusion(self):
        """A row no candidate explains is retained as a contradiction, not resolved."""
        broken = on_lattice_rows(count=15)
        broken[0]["va"] = broken[0]["va"] * 3  # implied price far outside the session range
        rows = {
            "HPG": normalized(broken),
            "VCB": normalized(on_lattice_rows(ticker_price=54_000, count=15)),
        }
        bounds = {
            "HPG": {"shares_outstanding": 8.4e9, "evidence_identity": "fixture"},
            "VCB": {"shares_outstanding": 9.0e9, "evidence_identity": "fixture"},
        }
        result = kbs.select_unit_scales(rows, share_count_bounds=bounds)
        self.assertEqual(result["rows_unexplained_by_every_candidate"], 1)
        self.assertEqual(result["unexplained_rows"][0]["rejects_every_candidate"], True)
        self.assertIn(
            "va includes a trading component the OHLC range does not represent",
            result["unexplained_row_alternative_explanations"],
        )
        # Too much unexplained residue stops being residue.
        mostly_broken = on_lattice_rows(count=15)
        for row in mostly_broken[:8]:
            row["va"] = row["va"] * 3
        flooded = kbs.select_unit_scales(
            {"HPG": normalized(mostly_broken), "VCB": rows["VCB"]}, share_count_bounds=bounds
        )
        self.assertEqual(flooded["qualification"], tiers.CONFLICTED)
        self.assertEqual(
            flooded["reason"], "too_many_rows_are_explained_by_no_candidate_scale"
        )

    def test_12_volume_unit_qualification_does_not_qualify_market_scope(self):
        rows = {
            "HPG": normalized(on_lattice_rows(count=15)),
            "VCB": normalized(on_lattice_rows(ticker_price=54_000, count=15)),
        }
        result = kbs.select_unit_scales(
            rows,
            share_count_bounds={
                "HPG": {"shares_outstanding": 8.4e9, "evidence_identity": "fixture"},
                "VCB": {"shares_outstanding": 9.0e9, "evidence_identity": "fixture"},
            },
        )
        self.assertEqual(result["volume_unit"], "shares")
        kbs.assert_unit_does_not_qualify_scope(result)
        with self.assertRaises(kbs.KBSBasisError):
            kbs.assert_unit_does_not_qualify_scope({**result, "volume_market_scope": "qualified"})
        self.assertEqual(kbs.market_scope_contract()["volume_market_scope"], "unknown")

    def test_12b_price_adjustment_never_implies_volume_adjustment(self):
        verdict = kbs.volume_adjustment_verdict(
            rewrite_test={"sessions_compared": 9, "sessions_with_changed_volume": 0},
            share_event_window_tested=False,
            price_basis_verdict="empirically_event_adjusted",
        )
        self.assertEqual(verdict["verdict"], "not_observed")
        self.assertFalse(verdict["derived_from_price_adjustment"])
        self.assertEqual(
            kbs.volume_adjustment_verdict(
                rewrite_test=None,
                share_event_window_tested=False,
                price_basis_verdict="empirically_event_adjusted",
            )["verdict"],
            "unknown",
        )


# ---------------------------------------------------------------------------------
# 13: market scope
# ---------------------------------------------------------------------------------


class MarketScopeTest(unittest.TestCase):
    def test_13_secondary_media_cannot_independently_qualify_negotiated_inclusion(self):
        media = [
            {"evidence_kind": kbs.SECONDARY_CORROBORATION, "note": "portal total looked higher"},
            {"evidence_kind": kbs.SECONDARY_CORROBORATION, "note": "news report of a block trade"},
            {"evidence_kind": kbs.SECONDARY_CORROBORATION, "note": "third article"},
        ]
        result = kbs.qualify_market_scope_dimension(
            dimension="negotiated_trade_inclusion", observations=media
        )
        self.assertEqual(result["verdict"], "unknown")
        self.assertEqual(result["independent_observations"], 0)
        self.assertEqual(result["secondary_corroboration_count"], 3)
        self.assertFalse(result["secondary_corroboration_upgraded_verdict"])

    def test_13b_an_admissible_observation_still_needs_every_confounder_eliminated(self):
        partial = [
            {
                "evidence_kind": "retained_official_exchange_total_matching_ticker_and_date",
                "confounders_eliminated": ["unit_mismatch", "partial_day_data"],
            }
        ] * 3
        self.assertEqual(
            kbs.qualify_market_scope_dimension(
                dimension="negotiated_trade_inclusion", observations=partial
            )["verdict"],
            "unknown",
        )
        complete = [
            {
                "evidence_kind": "retained_official_exchange_total_matching_ticker_and_date",
                "confounders_eliminated": list(kbs.SCOPE_CONFOUNDERS),
            }
        ] * 2
        self.assertEqual(
            kbs.qualify_market_scope_dimension(
                dimension="negotiated_trade_inclusion", observations=complete
            )["verdict"],
            "qualified",
        )


# ---------------------------------------------------------------------------------
# 14-20: the capability matrix
# ---------------------------------------------------------------------------------


class CapabilityMatrixTest(unittest.TestCase):
    def test_14_descriptive_charts_remain_available(self):
        result = caps.evaluate("kbs_historical_chart", existing_gates_passed=True)
        self.assertTrue(result["available"])
        for warning in caps.REQUIRED_WARNINGS:
            self.assertIn(warning, result["required_warnings"])
        # The existing gates still decide.
        self.assertFalse(caps.evaluate("kbs_historical_chart", existing_gates_passed=False)["available"])

    def test_15_provider_scoped_technical_indicators_remain_available(self):
        for name in ("kbs_moving_average", "kbs_rsi", "kbs_macd", "kbs_bollinger_bands"):
            result = caps.evaluate(name, existing_gates_passed=True)
            self.assertTrue(result["available"], name)
            self.assertEqual(result["capability_class"], caps.CLASS_TECHNICAL)
            self.assertFalse(result["liquidity_actionable"])

    def test_16_provider_series_returns_carry_explicit_warnings(self):
        unlabelled = caps.evaluate("kbs_provider_series_return", existing_gates_passed=True)
        self.assertFalse(unlabelled["available"])
        labelled = caps.evaluate(
            "kbs_provider_series_return",
            existing_gates_passed=True,
            label=caps.PROVIDER_SERIES_RETURN_LABEL,
        )
        self.assertTrue(labelled["available"])
        self.assertIn("price_series_event_adjusted_by_an_unknown_method", labelled["required_warnings"])
        for forbidden in caps.FORBIDDEN_RETURN_LABELS:
            with self.assertRaises(caps.KBSCapabilityError):
                caps.evaluate(
                    "kbs_provider_series_return", existing_gates_passed=True, label=forbidden
                )

    def test_17_corporate_action_factors_cannot_be_reapplied_without_compatibility(self):
        caps.assert_corporate_action_factors_not_reapplied(
            series_already_adjusted=False, factor_source_contract=None
        )
        with self.assertRaises(caps.KBSCapabilityError):
            caps.assert_corporate_action_factors_not_reapplied(
                series_already_adjusted=True, factor_source_contract=None
            )
        with self.assertRaises(caps.KBSCapabilityError):
            caps.assert_corporate_action_factors_not_reapplied(
                series_already_adjusted=True, factor_source_contract="corporate_action_factors"
            )

    def test_18_liquidity_actionability_remains_false(self):
        snapshot = caps.assert_matrix_fail_closed()
        self.assertFalse(snapshot["liquidity_actionable"])
        self.assertEqual(snapshot["volume_market_scope"], "unknown")
        for name in caps.capabilities_in_class(caps.CLASS_LIQUIDITY):
            result = caps.evaluate(name, existing_gates_passed=True)
            self.assertFalse(result["available"], name)
            self.assertEqual(result["availability"], caps.UNAVAILABLE_BY_CONTRACT, name)
            self.assertFalse(result["liquidity_actionable"], name)
        with self.assertRaises(caps.KBSCapabilityError):
            caps.assert_matrix_fail_closed({**snapshot, "liquidity_actionable": True})

    def test_19_production_backtesting_remains_unavailable(self):
        result = caps.evaluate("kbs_production_backtest", existing_gates_passed=True)
        self.assertFalse(result["available"])
        self.assertEqual(result["availability"], caps.UNAVAILABLE_BY_CONTRACT)
        # The shadow variant is eligibility only, and is never switched on.
        shadow = caps.evaluate("kbs_shadow_backtest", existing_gates_passed=True)
        self.assertFalse(shadow["available"])
        self.assertEqual(shadow["availability"], caps.ELIGIBILITY_DEFINED_NOT_IMPLEMENTED)
        all_met = caps.shadow_backtest_eligibility(
            {name: True for name in caps.SHADOW_BACKTEST_CONDITIONS}
        )
        self.assertTrue(all_met["eligible"])
        self.assertFalse(all_met["implemented"])
        self.assertFalse(all_met["is_actionable"])
        one_missing = caps.shadow_backtest_eligibility(
            {name: True for name in caps.SHADOW_BACKTEST_CONDITIONS[1:]}
        )
        self.assertFalse(one_missing["eligible"])

    def test_20_point_in_time_valuation_remains_unavailable(self):
        for name in caps.capabilities_in_class(caps.CLASS_HISTORICAL_TRUTH):
            result = caps.evaluate(name, existing_gates_passed=True)
            self.assertFalse(result["available"], name)
            self.assertEqual(result["reason"], caps.REASON_MUTABLE_SERIES, name)
        for consumer in (
            "historical_valuation_snapshot.point_in_time_price",
            "point_in_time_adjusted_prices.reconstruction",
        ):
            self.assertEqual(
                caps.classify_consumer(consumer)["availability"], caps.UNAVAILABLE_BY_CONTRACT
            )

    def test_20b_an_unclassified_consumer_is_refused_not_defaulted_open(self):
        result = caps.classify_consumer("some_module.some_new_kbs_reader")
        self.assertEqual(result["availability"], caps.UNAVAILABLE_PENDING_CLASSIFICATION)
        with self.assertRaises(caps.KBSCapabilityError):
            caps.capability("kbs_invented_capability")


# ---------------------------------------------------------------------------------
# 21-22: scope of the verdict
# ---------------------------------------------------------------------------------


class VerdictScopeTest(unittest.TestCase):
    def test_21_no_other_provider_inherits_the_kbs_verdict(self):
        self.assertTrue(caps.provider_scope("KBS")["contract_applies"])
        for other in ("VCI", "TCBS", "SSI", "HOSE"):
            scope = caps.provider_scope(other)
            self.assertFalse(scope["contract_applies"], other)
            with self.assertRaises(kbs.KBSBasisError):
                kbs.assert_no_provider_inheritance(other)
        for field in ("volume", "close", "official_exchange_volume", "adjusted_close"):
            with self.assertRaises(caps.KBSCapabilityError):
                caps.assert_no_generic_field_upgrade(field)
        with self.assertRaises(kbs.KBSBasisError):
            kbs.assert_no_generic_upgrade({"vci.raw_close": 1})
        with self.assertRaises(kbs.KBSBasisError):
            kbs.assert_no_generic_upgrade({"is_actionable": True})
        kbs.assert_no_generic_upgrade({"kbs.observed_close_vnd": 20600})

    def test_21b_the_vci_verdict_is_untouched_by_this_milestone(self):
        vci = registry.active_verdict("VCI")
        self.assertEqual(vci["price_basis"], "empirically_event_adjusted")
        self.assertEqual(vci["historical_mutability"], "retrospectively_rewritten")
        self.assertFalse(vci["raw_as_traded_eligible"])

    def test_22_is_actionable_remains_unchanged(self):
        snapshot = caps.matrix_snapshot()
        self.assertEqual(snapshot["is_actionable_effect"], "none")
        self.assertIn("is_actionable_remains_false", caps.SHADOW_BACKTEST_CONDITIONS)
        self.assertEqual(
            caps.evaluate("kbs_volume_derived_actionability_upgrade", existing_gates_passed=True)[
                "availability"
            ],
            caps.UNAVAILABLE_BY_CONTRACT,
        )

    def test_22b_the_prior_kbs_verdict_is_retained_not_deleted(self):
        superseded = registry.superseded_verdicts("KBS")
        self.assertEqual(len(superseded), 1)
        record = superseded[0]
        self.assertTrue(registry.is_superseded("phase1c_kbs_fields_unusable"))
        self.assertIn("No documented semantic metadata exists", record["retained_correct_for"])
        self.assertEqual(
            record["root_cause"], "absence_of_documentation_treated_as_absence_of_usable_data"
        )
        # The active verdict is the new one, and it is not raw-as-traded eligible.
        active = registry.active_verdict("KBS")
        self.assertEqual(active["price_basis"], "empirically_event_adjusted")
        self.assertEqual(active["price_basis_qualification"], tiers.EMPIRICALLY_DEDUCED)
        self.assertFalse(active["raw_as_traded_eligible"])
        self.assertTrue(registry.blocks_raw_as_traded("KBS"))
        with self.assertRaises(registry.PriceBasisConflict):
            registry.assert_not_conflated(
                local_adjustment_applied=False, provider="KBS", claimed_basis="raw_as_traded"
            )

    def test_22c_a_justified_supersession_is_not_a_recency_rule(self):
        with self.assertRaises(tiers.QualificationError):
            tiers.supersede(
                prior={"retained_correct_for": "x"}, superseding={}, justification="   "
            )
        with self.assertRaises(tiers.QualificationError):
            tiers.supersede(prior={}, superseding={}, justification="newer evidence")
        result = tiers.supersede(
            prior={"retained_correct_for": "no documented semantics were found"},
            superseding={"verdict": "empirically_event_adjusted"},
            justification="the premise stands; only the inference from it was too broad",
        )
        self.assertFalse(result["resolved_by_recency"])
        self.assertEqual(result["superseded"]["status"], "superseded")


# ---------------------------------------------------------------------------------
# 23-24: replay and production non-effects
# ---------------------------------------------------------------------------------


class ReplayAndProductionTest(unittest.TestCase):
    def setUp(self):
        self.manifest_path = EVIDENCE_DIR / "evidence_manifest.json"
        if not self.manifest_path.exists():
            self.skipTest("KBS evidence artifacts were not generated in this working tree")
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def test_23_offline_replay_is_deterministic(self):
        def load(name):
            return (EVIDENCE_DIR / name).read_bytes()

        first = kbs.replay(self.manifest, load_bytes=load)
        second = kbs.replay(self.manifest, load_bytes=load)
        self.assertEqual(first["replay_fingerprint"], second["replay_fingerprint"])
        self.assertEqual(first["artifacts_replayed"], self.manifest["artifact_count"])
        self.assertGreater(first["artifacts_replayed"], 0)

    def test_23b_a_tampered_artifact_stops_the_replay(self):
        def tampered(name):
            body = (EVIDENCE_DIR / name).read_bytes()
            return body.replace(b"data_day", b"data_dax", 1)

        with self.assertRaises(kbs.KBSBasisError):
            kbs.replay(self.manifest, load_bytes=tampered)

    def test_23c_the_manifest_hash_covers_its_own_entries(self):
        rebuilt = kbs.evidence_manifest(
            [
                {
                    "artifact": entry["artifact"],
                    "raw_response_sha256": entry["sha256"],
                    "ticker": entry["ticker"],
                    "window_role": entry["window_role"],
                    "requested_date_range": entry["requested_date_range"],
                    "retrieved_at": entry["retrieved_at"],
                    "response_schema_fingerprint": entry["response_schema_fingerprint"],
                }
                for entry in self.manifest["artifacts"]
            ]
        )
        self.assertEqual(rebuilt["manifest_sha256"], self.manifest["manifest_sha256"])

    def test_24_production_artifacts_remain_unchanged(self):
        """Nothing in the lane can write anything, and the request boundaries are enforced.

        Checked structurally rather than by scanning for suggestive words: both contract
        modules are pure, so they must not import a database driver and must not contain a
        write call. All I/O in this lane lives in the runner script, which the suite never
        imports.
        """
        for module in (kbs, caps):
            source = Path(module.__file__).read_text(encoding="utf-8")
            for forbidden in (
                "import sqlite3",
                "write_text(",
                "write_bytes(",
                "INSERT INTO",
                "UPDATE ",
            ):
                self.assertNotIn(forbidden, source, f"{module.__name__}:{forbidden}")
        with self.assertRaises(kbs.KBSBasisError):
            kbs.assert_ticker_in_scope("FPT")
        with self.assertRaises(kbs.KBSBasisError):
            kbs.assert_endpoint_in_scope("https://kbbuddywts.kbsec.com.vn/iis-server/other")
        with self.assertRaises(kbs.KBSBasisError):
            kbs.assert_redirect_within_boundary("https://elsewhere.example/x")
        with self.assertRaises(kbs.KBSBasisError):
            kbs.daily_params(start="2026-01-01", end="2026-12-31")
        self.assertEqual(kbs.REQUEST_BUDGET, 6)
        self.assertEqual(kbs.redact_headers({"Cookie": "secret"}), {"Cookie": kbs.REDACTED})
        with self.assertRaises(kbs.KBSBasisError):
            kbs.build_observation(provider="KBS")


if __name__ == "__main__":
    unittest.main()
