"""Contract tests for the KBS mutability closeout and the prospective observation protocol.

No test here opens a socket, reads a clock or touches a database. The protocol module is
pure by construction and the fixtures below are frozen; live access is never a dependency.

Numbering matches the milestone's required-test list.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

import evidence_qualification_tiers as tiers
import kbs_capability_matrix as caps
import kbs_empirical_basis as kbs
import kbs_mutability_protocol as protocol
import provider_price_basis_registry as registry

REPO_ROOT = Path(__file__).resolve().parent.parent

EX_DATE = "2026-05-25"


def rows(*, close=24_100.0, volume=26_989_100.0, value=653_560_680_000.0, sessions=3):
    return [
        {
            "kbs.session_date": f"2026-05-{18 + index:02d}",
            "kbs.observed_open_vnd": close,
            "kbs.observed_high_vnd": close + 50,
            "kbs.observed_low_vnd": close - 50,
            "kbs.observed_close_vnd": close,
            "kbs.observed_daily_volume": volume,
            "kbs.observed_daily_trading_value": value,
        }
        for index in range(sessions)
    ]


def pre_event_manifest(**overrides):
    record = {
        "protocol_version": protocol.VERSION,
        "provider": "KBS",
        "ticker": "HPG",
        "endpoint": kbs.daily_endpoint("HPG"),
        "request_parameters": {"sdate": "01-05-2026", "edate": "20-05-2026"},
        "historical_window": ["2026-05-01", "2026-05-20"],
        "retrieved_at": "2026-05-22T02:00:00Z",
        "raw_artifact": "pre_event/kbs_daily_HPG_20260522T020000Z_abcdef0123456789.raw.json",
        "raw_sha256": "a" * 64,
        "response_schema_fingerprint": "f" * 64,
        "event_id": "hpg-iss-20260525",
        "event_ex_date": EX_DATE,
        "event_kind": kbs.EVENT_KIND_SHARE,
        "event_evidence_identity": "vn_stock.db:corporate_event_records[record_id=31135d0d...]",
        "control_ticker": "VNM",
        "control_window": ["2026-05-01", "2026-05-20"],
    }
    record.update(overrides)
    return record


# ---------------------------------------------------------------------------------
# 1-4: the three mutability questions stay apart
# ---------------------------------------------------------------------------------


class MutabilityDistinctionTest(unittest.TestCase):
    def test_01_two_post_event_snapshots_cannot_qualify_event_time_rewriting(self):
        """The exact mistake this milestone corrects, asserted directly."""
        result = kbs.historical_rewrite_test(
            prior_rows=rows(),
            current_rows=rows(),
            prior_observed_at="2026-08-01T01:11:52Z",
            current_observed_at="2026-08-04T06:58:05Z",
            prior_artifact="retained.json",
            event_ex_dates=[EX_DATE],
        )
        self.assertEqual(result["snapshot_pair"]["pair_class"], kbs.PAIR_BOTH_POST_EVENT)
        self.assertFalse(result["snapshot_pair"]["event_time_testable"])
        self.assertEqual(result["event_time_rewriting"], "not_testable_from_this_pair")
        # And a much later second observation is still the same class.
        later = kbs.historical_rewrite_test(
            prior_rows=rows(),
            current_rows=rows(),
            prior_observed_at="2026-08-01T01:11:52Z",
            current_observed_at="2027-12-31T00:00:00Z",
            prior_artifact="retained.json",
            event_ex_dates=[EX_DATE],
        )
        self.assertEqual(later["event_time_rewriting"], "not_testable_from_this_pair")

    def test_02_post_event_byte_stability_does_not_imply_historical_immutability(self):
        result = kbs.historical_rewrite_test(
            prior_rows=rows(),
            current_rows=rows(),
            prior_observed_at="2026-08-01T01:11:52Z",
            current_observed_at="2026-08-04T06:58:05Z",
            prior_artifact="retained.json",
            event_ex_dates=[EX_DATE],
        )
        self.assertEqual(
            result["post_event_snapshot_stability"], "observed_for_tested_retrieval_interval"
        )
        self.assertEqual(result["sessions_with_changed_close"], 0)
        # Stability is recorded, and the contract-level field still says nothing was seen.
        self.assertEqual(kbs.contract_historical_mutability(result), "not_observed")
        self.assertIn("stability_is_not_immutability", result)
        self.assertNotEqual(result["event_time_rewriting"], "no_rewrite_observed_for_tested_event")

    def test_02b_a_pair_that_straddles_the_event_can_answer_the_question(self):
        spanning = kbs.historical_rewrite_test(
            prior_rows=rows(),
            current_rows=rows(close=23_800.0),
            prior_observed_at="2026-05-22T02:00:00Z",
            current_observed_at="2026-05-27T02:00:00Z",
            prior_artifact="pre_event.json",
            event_ex_dates=[EX_DATE],
        )
        self.assertEqual(spanning["snapshot_pair"]["pair_class"], kbs.PAIR_SPANS_EVENT)
        self.assertEqual(spanning["event_time_rewriting"], "retrospectively_rewritten")
        self.assertEqual(kbs.contract_historical_mutability(spanning), "retrospectively_rewritten")
        clean = kbs.historical_rewrite_test(
            prior_rows=rows(),
            current_rows=rows(),
            prior_observed_at="2026-05-22T02:00:00Z",
            current_observed_at="2026-05-27T02:00:00Z",
            prior_artifact="pre_event.json",
            event_ex_dates=[EX_DATE],
        )
        self.assertEqual(clean["event_time_rewriting"], "no_rewrite_observed_for_tested_event")
        self.assertEqual(kbs.contract_historical_mutability(clean), "not_observed")

    def test_03_price_stability_does_not_qualify_volume_adjustment(self):
        stable = kbs.historical_rewrite_test(
            prior_rows=rows(),
            current_rows=rows(),
            prior_observed_at="2026-08-01T01:11:52Z",
            current_observed_at="2026-08-04T06:58:05Z",
            prior_artifact="retained.json",
            event_ex_dates=[EX_DATE],
        )
        verdict = kbs.volume_adjustment_verdict(
            rewrite_test=stable,
            share_event_window_tested=False,
            price_basis_verdict="empirically_event_adjusted",
        )
        self.assertEqual(verdict["verdict"], "not_observed")
        self.assertFalse(verdict["derived_from_price_adjustment"])
        self.assertEqual(verdict["snapshot_pair_class"], kbs.PAIR_BOTH_POST_EVENT)
        # A caller asserting otherwise cannot override the pair.
        overclaimed = kbs.volume_adjustment_verdict(
            rewrite_test=stable,
            share_event_window_tested=True,
            price_basis_verdict="empirically_event_adjusted",
        )
        self.assertEqual(overclaimed["verdict"], "not_observed")

    def test_04_price_rewrite_does_not_imply_volume_rewrite(self):
        """A changed volume in a non-straddling pair is a revision, not an adjustment."""
        changed = kbs.historical_rewrite_test(
            prior_rows=rows(volume=26_989_100.0),
            current_rows=rows(volume=27_000_000.0),
            prior_observed_at="2026-08-01T01:11:52Z",
            current_observed_at="2026-08-04T06:58:05Z",
            prior_artifact="retained.json",
            event_ex_dates=[EX_DATE],
        )
        self.assertTrue(changed["sessions_with_changed_volume"])
        verdict = kbs.volume_adjustment_verdict(
            rewrite_test=changed,
            share_event_window_tested=True,
            price_basis_verdict="empirically_event_adjusted",
        )
        self.assertEqual(verdict["verdict"], "not_observed")
        self.assertIn("ordinary provider revision", verdict["note"])
        # The retained divergence result records the independent-schedule finding without
        # letting it become a volume-adjustment verdict.
        divergence = kbs.price_volume_restatement_divergence(
            rows=[
                {**row, "kbs.observed_open_vnd": 61_942.0, "kbs.observed_high_vnd": 62_538.0,
                 "kbs.observed_low_vnd": 61_644.0, "kbs.observed_close_vnd": 62_538.0}
                for row in rows()
            ],
            reference_volumes={row["kbs.session_date"]: 26_989_100.0 for row in rows()},
            reference_identity="stored VCI rows",
        )
        self.assertEqual(divergence["verdict"], "price_restated_while_volume_unchanged")
        self.assertIn("not an input to the volume-adjustment verdict", divergence["note"])


# ---------------------------------------------------------------------------------
# 5-9: the unit anchor
# ---------------------------------------------------------------------------------


class UnitAnchorTest(unittest.TestCase):
    def sample(self):
        def series(price, volume, count):
            return [
                {
                    "kbs.session_date": f"2026-07-{index + 1:02d}",
                    "kbs.observed_open_vnd": price,
                    "kbs.observed_high_vnd": price + 50,
                    "kbs.observed_low_vnd": price - 50,
                    "kbs.observed_close_vnd": price,
                    "kbs.observed_daily_volume": volume + index,
                    "kbs.observed_daily_trading_value": (volume + index) * price,
                }
                for index in range(count)
            ]

        return {"HPG": series(21_000, 20_000_000, 15), "VNM": series(58_000, 5_000_000, 15)}

    def test_05_vwap_geometry_identifies_only_a_quotient(self):
        self.assertEqual(kbs.scale_quotient(1, 1), kbs.scale_quotient(1000, 1000))
        classes = kbs.scale_quotient_class([(1, 1), (1000, 1000), (1, 1000)])
        self.assertEqual(sorted(classes[1.0]), [(1, 1), (1000, 1000)])
        result = kbs.select_unit_scales(self.sample())
        self.assertEqual(result["scale_quotient"], 1.0)
        self.assertEqual(result["unit_scale_ratio"], 1.0)

    def test_06_an_insufficient_anchor_leaves_the_absolute_scale_unresolved(self):
        result = kbs.select_unit_scales(self.sample(), share_count_bounds=None)
        self.assertEqual(result["volume_unit"], "scaled_units")
        self.assertEqual(result["trading_value_unit"], "scaled_units")
        self.assertEqual(result["absolute_scale"], "unresolved")
        self.assertIsNone(result["absolute_scale_anchor"])
        self.assertEqual(result["qualification"], tiers.OBSERVED_ONLY)
        # A share count too large to reject anything is equally insufficient.
        useless = kbs.select_unit_scales(
            self.sample(),
            share_count_bounds={
                "HPG": {"shares_outstanding": 1e15, "evidence_identity": "fixture"},
                "VNM": {"shares_outstanding": 1e15, "evidence_identity": "fixture"},
            },
        )
        self.assertEqual(useless["absolute_scale"], "unresolved")

    def test_07_a_grounded_plausibility_anchor_supports_an_empirical_absolute_scale(self):
        result = kbs.select_unit_scales(
            self.sample(),
            share_count_bounds={
                "HPG": {"shares_outstanding": 8.44e9, "evidence_identity": "fixture"},
                "VNM": {"shares_outstanding": 2.09e9, "evidence_identity": "fixture"},
            },
        )
        self.assertEqual(result["volume_unit"], "shares")
        self.assertEqual(result["trading_value_unit"], "VND")
        self.assertEqual(result["absolute_scale"], "resolved")
        self.assertEqual(result["absolute_scale_anchor"], kbs.ANCHOR_SHARE_COUNT)
        self.assertEqual(result["qualification"], tiers.EMPIRICALLY_DEDUCED)
        self.assertTrue(result["degeneracy_resolution"]["anchor_is_a_falsifier_not_a_measurement"])

    def test_07b_the_identity_anchor_resolves_the_scale_without_any_share_count(self):
        sample = self.sample()
        reference = {
            ticker: {row["kbs.session_date"]: row["kbs.observed_daily_volume"] for row in series}
            for ticker, series in sample.items()
        }
        anchor = kbs.unit_identity_anchor(
            per_ticker_rows=sample,
            reference_volumes=reference,
            reference_identity="stored VCI rows",
            reference_unit="shares",
            reference_unit_qualification=tiers.EMPIRICALLY_DEDUCED,
        )
        self.assertTrue(anchor["available"])
        self.assertEqual(anchor["implied_volume_scale"], 1)
        self.assertEqual(anchor["transfers"], "magnitude_only")
        result = kbs.select_unit_scales(sample, share_count_bounds=None, identity_anchor=anchor)
        self.assertEqual(result["volume_unit"], "shares")
        self.assertEqual(result["absolute_scale_anchor"], kbs.ANCHOR_UNIT_IDENTITY)
        self.assertEqual(result["qualification"], tiers.EMPIRICALLY_DEDUCED)
        # It transfers magnitude and nothing else.
        with self.assertRaises(kbs.KBSBasisError):
            kbs.assert_identity_anchor_is_magnitude_only(
                {**anchor, "volume_market_scope": "qualified"}
            )
        with self.assertRaises(kbs.KBSBasisError):
            kbs.assert_identity_anchor_is_magnitude_only({**anchor, "transfers": "everything"})
        # A reference that is not a share count anchors nothing.
        self.assertFalse(
            kbs.unit_identity_anchor(
                per_ticker_rows=sample,
                reference_volumes=reference,
                reference_identity="stored rows",
                reference_unit="board_lots",
                reference_unit_qualification=tiers.EMPIRICALLY_DEDUCED,
            )["available"]
        )

    def test_08_an_empirical_unit_verdict_cannot_become_documented_verified(self):
        active = registry.active_verdict("KBS")
        self.assertEqual(active["volume_unit_qualification"], tiers.EMPIRICALLY_DEDUCED)
        self.assertEqual(active["trading_value_unit_qualification"], tiers.EMPIRICALLY_DEDUCED)
        self.assertFalse(tiers.may_claim_official_semantics(tiers.EMPIRICALLY_DEDUCED))
        # Even a documented reference cannot lift the identity anchor above empirical.
        anchor = kbs.unit_identity_anchor(
            per_ticker_rows=self.sample(),
            reference_volumes={
                ticker: {row["kbs.session_date"]: row["kbs.observed_daily_volume"] for row in series}
                for ticker, series in self.sample().items()
            },
            reference_identity="stored rows",
            reference_unit="shares",
            reference_unit_qualification=tiers.DOCUMENTED_VERIFIED,
        )
        self.assertEqual(anchor["qualification_ceiling"], tiers.EMPIRICALLY_DEDUCED)

    def test_09_the_unit_anchor_cannot_be_reused_for_valuation(self):
        result = kbs.select_unit_scales(
            self.sample(),
            share_count_bounds={
                "HPG": {"shares_outstanding": 8.44e9, "evidence_identity": "fixture"},
                "VNM": {"shares_outstanding": 2.09e9, "evidence_identity": "fixture"},
            },
        )
        resolution = result["degeneracy_resolution"]
        self.assertFalse(resolution["anchor_admissible_for_valuation"])
        self.assertFalse(registry.active_verdict("KBS")["unit_anchor_admissible_for_valuation"])
        # And the anchor's own tier stays where P1J.1 left provider share counts.
        bounds = result["degeneracy_resolution"]["rejections"][0]["detail"]
        self.assertEqual(bounds["bound_qualification"], tiers.OBSERVED_ONLY)


# ---------------------------------------------------------------------------------
# 10-13: the prospective protocol
# ---------------------------------------------------------------------------------


class ProspectiveProtocolTest(unittest.TestCase):
    def test_10_a_valid_comparison_requires_a_pre_event_snapshot(self):
        manifest = protocol.build_pre_event_manifest(**pre_event_manifest())
        self.assertEqual(manifest["phase"], "pre_event")
        # Retrieved on or after the ex-date is not a pre-event snapshot at all.
        for bad in ("2026-05-25T02:00:00Z", "2026-08-04T06:58:01Z"):
            with self.assertRaises(protocol.MutabilityProtocolError):
                protocol.build_pre_event_manifest(**pre_event_manifest(retrieved_at=bad))
        # The historical window must be closed before the event.
        with self.assertRaises(protocol.MutabilityProtocolError):
            protocol.build_pre_event_manifest(
                **pre_event_manifest(historical_window=["2026-05-01", "2026-05-26"])
            )
        # And the post-event request must be the same request.
        with self.assertRaises(protocol.MutabilityProtocolError):
            protocol.assert_post_event_request_matches(
                pre_event=manifest,
                post_event={**manifest, "request_parameters": {"sdate": "02-05-2026"}},
            )
        with self.assertRaises(protocol.MutabilityProtocolError):
            protocol.assert_post_event_request_matches(
                pre_event=manifest,
                post_event={**manifest, "retrieved_at": "2026-05-24T02:00:00Z"},
            )
        protocol.assert_post_event_request_matches(
            pre_event=manifest, post_event={**manifest, "retrieved_at": "2026-05-27T02:00:00Z"}
        )

    def test_11_missing_pre_event_evidence_yields_observation_incomplete(self):
        comparison = protocol.compare_snapshots(
            pre_event_rows=rows(),
            post_event_rows=rows(close=23_800.0),
            pre_event_schema_fingerprint="a",
            post_event_schema_fingerprint="a",
        )
        verdict = protocol.classify_comparison(
            comparison=comparison, control_comparison=None, pre_event_manifest=None
        )
        self.assertEqual(verdict["verdict"], protocol.INCOMPLETE)
        self.assertIn("Two post-event snapshots cannot substitute", verdict["note"])
        protocol.assert_verdict_scoped(verdict)
        # No overlap is equally incomplete.
        empty = protocol.compare_snapshots(
            pre_event_rows=rows(),
            post_event_rows=[],
            pre_event_schema_fingerprint="a",
            post_event_schema_fingerprint="a",
        )
        self.assertEqual(
            protocol.classify_comparison(
                comparison=empty,
                control_comparison=None,
                pre_event_manifest=pre_event_manifest(),
            )["verdict"],
            protocol.INCOMPLETE,
        )

    def test_11b_the_comparison_separates_the_change_classes(self):
        manifest = pre_event_manifest()
        price_only = protocol.compare_snapshots(
            pre_event_rows=rows(),
            post_event_rows=rows(close=23_800.0),
            pre_event_schema_fingerprint="a",
            post_event_schema_fingerprint="a",
        )
        self.assertTrue(price_only["price_rewrite"])
        self.assertFalse(price_only["volume_rewrite"])
        self.assertEqual(
            protocol.classify_comparison(
                comparison=price_only, control_comparison=None, pre_event_manifest=manifest
            )["verdict"],
            "price_rewrite_without_volume_rewrite",
        )
        volume_too = protocol.compare_snapshots(
            pre_event_rows=rows(),
            post_event_rows=rows(close=23_800.0, volume=29_688_010.0),
            pre_event_schema_fingerprint="a",
            post_event_schema_fingerprint="a",
        )
        self.assertEqual(
            protocol.classify_comparison(
                comparison=volume_too, control_comparison=None, pre_event_manifest=manifest
            )["verdict"],
            "event_time_volume_rewrite_observed",
        )
        # A control that moved too means the event is not isolated.
        control = protocol.compare_snapshots(
            pre_event_rows=rows(),
            post_event_rows=rows(close=23_900.0),
            pre_event_schema_fingerprint="a",
            post_event_schema_fingerprint="a",
        )
        conflicted = protocol.classify_comparison(
            comparison=volume_too, control_comparison=control, pre_event_manifest=manifest
        )
        self.assertEqual(conflicted["verdict"], "comparison_conflicted")
        self.assertIn("unrelated_provider_correction", conflicted["change_classes"])
        # A schema change with no value change is its own verdict.
        schema = protocol.compare_snapshots(
            pre_event_rows=rows(),
            post_event_rows=rows(),
            pre_event_schema_fingerprint="a",
            post_event_schema_fingerprint="b",
        )
        self.assertEqual(
            protocol.classify_comparison(
                comparison=schema, control_comparison=None, pre_event_manifest=manifest
            )["verdict"],
            "provider_schema_changed",
        )

    def test_12_future_event_verdicts_remain_scoped_to_the_tested_event(self):
        manifest = pre_event_manifest()
        clean = protocol.classify_comparison(
            comparison=protocol.compare_snapshots(
                pre_event_rows=rows(),
                post_event_rows=rows(),
                pre_event_schema_fingerprint="a",
                post_event_schema_fingerprint="a",
            ),
            control_comparison=None,
            pre_event_manifest=manifest,
        )
        self.assertEqual(clean["verdict"], "no_rewrite_observed_for_tested_event")
        protocol.assert_verdict_scoped(clean)
        self.assertEqual(clean["scope"]["event_ex_date"], EX_DATE)
        self.assertEqual(clean["scope"]["coverage_generalization"], tiers.COVERAGE_LIMITED)
        for missing in ("event_id", "event_ex_date", "ticker", "historical_window"):
            broken = {**clean, "scope": {**clean["scope"], missing: None}}
            with self.assertRaises(protocol.MutabilityProtocolError):
                protocol.assert_verdict_scoped(broken)

    def test_13_one_event_cannot_establish_universal_kbs_methodology(self):
        manifest = pre_event_manifest()
        verdict = protocol.classify_comparison(
            comparison=protocol.compare_snapshots(
                pre_event_rows=rows(),
                post_event_rows=rows(close=23_800.0),
                pre_event_schema_fingerprint="a",
                post_event_schema_fingerprint="a",
            ),
            control_comparison=None,
            pre_event_manifest=manifest,
        )
        self.assertEqual(verdict["scope"]["provider_methodology"], "unknown")
        generalised = {
            **verdict,
            "scope": {**verdict["scope"], "provider_methodology": "standard_back_adjustment"},
        }
        with self.assertRaises(protocol.MutabilityProtocolError):
            protocol.assert_verdict_scoped(generalised)
        widened = {
            **verdict,
            "scope": {**verdict["scope"], "coverage_generalization": "all_windows"},
        }
        with self.assertRaises(protocol.MutabilityProtocolError):
            protocol.assert_verdict_scoped(widened)

    def test_13b_a_completed_observation_moves_only_the_mutability_dimensions(self):
        manifest = pre_event_manifest()
        rewrote = protocol.classify_comparison(
            comparison=protocol.compare_snapshots(
                pre_event_rows=rows(),
                post_event_rows=rows(close=23_800.0, volume=29_688_010.0),
                pre_event_schema_fingerprint="a",
                post_event_schema_fingerprint="a",
            ),
            control_comparison=None,
            pre_event_manifest=manifest,
        )
        effect = protocol.contract_effect(rewrote)
        self.assertEqual(effect["historical_mutability"], "retrospectively_rewritten")
        self.assertEqual(effect["volume_adjustment_basis"], "share_event_adjusted_volume_observed")
        for closed in ("raw_as_traded_eligible", "official_exchange_price",
                       "liquidity_actionable", "production_write", "capability_activation"):
            self.assertFalse(effect[closed], closed)
        self.assertEqual(effect["volume_market_scope"], "unknown")
        self.assertEqual(effect["is_actionable_effect"], "none")


# ---------------------------------------------------------------------------------
# 14-18: capabilities are preserved, and the closed ones stay closed
# ---------------------------------------------------------------------------------


class CapabilityPreservationTest(unittest.TestCase):
    DESCRIPTIVE = (
        "kbs_ohlcv_display",
        "kbs_historical_chart",
        "kbs_descriptive_price_statistics",
        "kbs_descriptive_volume_statistics",
        "kbs_descriptive_trading_value_statistics",
        "kbs_provider_relative_volume",
        "kbs_provider_price_momentum",
        "kbs_anomaly_detection",
        "kbs_cross_provider_corroboration",
    )
    TECHNICAL = (
        "kbs_moving_average",
        "kbs_rsi",
        "kbs_macd",
        "kbs_bollinger_bands",
        "kbs_technical_pattern_research",
        "kbs_shadow_analytics",
    )

    def test_14_provider_scoped_descriptive_capabilities_remain_available(self):
        for name in self.DESCRIPTIVE:
            result = caps.evaluate(name, existing_gates_passed=True)
            self.assertTrue(result["available"], name)
            self.assertFalse(result["liquidity_actionable"], name)

    def test_15_provider_scoped_technical_capabilities_remain_available(self):
        for name in self.TECHNICAL:
            result = caps.evaluate(name, existing_gates_passed=True)
            self.assertTrue(result["available"], name)
        labelled = caps.evaluate(
            "kbs_provider_series_return",
            existing_gates_passed=True,
            label=caps.PROVIDER_SERIES_RETURN_LABEL,
        )
        self.assertTrue(labelled["available"])

    def test_15b_unobserved_mutability_did_not_regress_any_capability(self):
        """The point of Part E: an open question is not a reason to close a chart."""
        self.assertEqual(registry.active_verdict("KBS")["historical_mutability"], "not_observed")
        snapshot = caps.assert_matrix_fail_closed()
        self.assertEqual(snapshot["descriptive_capability"], "available")
        self.assertEqual(snapshot["technical_capability"], "provider_scoped_available")
        for name in self.DESCRIPTIVE + self.TECHNICAL:
            self.assertIn(name, caps.AVAILABLE_CAPABILITIES, name)

    def test_16_point_in_time_valuation_remains_unavailable(self):
        for name in caps.capabilities_in_class(caps.CLASS_HISTORICAL_TRUTH):
            result = caps.evaluate(name, existing_gates_passed=True)
            self.assertFalse(result["available"], name)
            self.assertEqual(result["availability"], caps.UNAVAILABLE_BY_CONTRACT, name)

    def test_17_liquidity_and_execution_capabilities_remain_unavailable(self):
        for klass in (caps.CLASS_LIQUIDITY, caps.CLASS_EXECUTION):
            for name in caps.capabilities_in_class(klass):
                result = caps.evaluate(name, existing_gates_passed=True)
                self.assertFalse(result["available"], name)
                self.assertFalse(result["liquidity_actionable"], name)
        self.assertEqual(kbs.market_scope_contract()["volume_market_scope"], "unknown")

    def test_18_corporate_action_factor_reapplication_remains_prohibited(self):
        with self.assertRaises(caps.KBSCapabilityError):
            caps.assert_corporate_action_factors_not_reapplied(
                series_already_adjusted=True, factor_source_contract=None
            )
        with self.assertRaises(caps.KBSCapabilityError):
            caps.assert_corporate_action_factors_not_reapplied(
                series_already_adjusted=True, factor_source_contract="corporate_action_factors"
            )
        for forbidden in caps.FORBIDDEN_RETURN_LABELS:
            with self.assertRaises(caps.KBSCapabilityError):
                caps.evaluate(
                    "kbs_provider_series_return", existing_gates_passed=True, label=forbidden
                )


# ---------------------------------------------------------------------------------
# 19-20: inertness and non-effects
# ---------------------------------------------------------------------------------


class InertnessTest(unittest.TestCase):
    def test_19_protocol_registration_makes_no_network_request(self):
        snapshot = protocol.assert_protocol_inert()
        for flag in (
            "network_access_authorized",
            "scheduling_authorized",
            "event_polling_authorized",
            "automatic_acquisition_authorized",
        ):
            self.assertFalse(snapshot[flag], flag)
        self.assertTrue(snapshot["control_required"])
        with self.assertRaises(protocol.MutabilityProtocolError):
            protocol.assert_protocol_inert({**snapshot, "scheduling_authorized": True})
        with self.assertRaises(protocol.MutabilityProtocolError):
            protocol.assert_protocol_inert({**snapshot, "control_required": False})

        # Checked against the parsed import graph rather than by scanning for words: the
        # module's prose is *about* scheduling and networks, so a substring search flags
        # its own documentation. Only what it actually imports can make it act.
        source = Path(protocol.__file__).read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in (
            "requests", "urllib", "urllib3", "http", "socket", "ssl", "ftplib",
            "sched", "threading", "asyncio", "subprocess", "sqlite3", "time", "datetime",
        ):
            self.assertNotIn(forbidden, imported, f"{forbidden} is imported by the protocol")
        self.assertEqual(imported, {"__future__", "hashlib", "json", "typing",
                                    "evidence_qualification_tiers", "kbs_empirical_basis"})
        # No writes either: the protocol describes artifacts, it does not create them.
        for forbidden in ("write_text(", "write_bytes(", "open("):
            self.assertNotIn(forbidden, source, forbidden)
        self.assertEqual(len(protocol.protocol_fingerprint()), 64)

    def test_19c_the_framing_correction_is_recorded_without_editing_the_evidence(self):
        record = protocol.CORRECTED_FRAMING
        self.assertFalse(record["measurements_changed"])
        self.assertFalse(record["evidence_changed"])
        self.assertFalse(record["artifact_rewritten"])
        self.assertIn("BEFORE a future", record["corrected_framing"])
        # The frozen report still exists and still says what it said.
        report = (
            REPO_ROOT / "operations-review" / "kbs-empirical-basis-20260804"
            / "KBS_EMPIRICAL_BASIS.md"
        )
        self.assertTrue(report.exists())
        self.assertIn("spans no qualified share event", report.read_text(encoding="utf-8"))

        superseded = protocol.SUPERSEDED_RECOMMENDATION
        self.assertEqual(superseded["status"], "superseded")
        self.assertEqual(superseded["would_have_settled"], [])
        self.assertIn(
            "historical_mutability_across_the_share_event",
            superseded["must_not_be_claimed_to_settle"],
        )
        # The correction is enforceable, not merely written down.
        with self.assertRaises(protocol.MutabilityProtocolError):
            protocol.assert_not_a_retrospective_substitute(
                prior_observed_at="2026-08-04T06:58:05Z",
                current_observed_at="2027-06-01T00:00:00Z",
                event_ex_dates=[EX_DATE],
            )
        pair = protocol.assert_not_a_retrospective_substitute(
            prior_observed_at="2026-05-22T02:00:00Z",
            current_observed_at="2026-05-27T02:00:00Z",
            event_ex_dates=[EX_DATE],
        )
        self.assertTrue(pair["event_time_testable"])

    def test_19b_artifact_paths_are_deterministic_and_phase_bearing(self):
        first = protocol.artifact_path(
            event_id="hpg-iss-20260525", ex_date=EX_DATE, phase="pre_event",
            ticker="HPG", retrieved_at="2026-05-22T02:00:00Z", sha256="ab" * 32,
        )
        second = protocol.artifact_path(
            event_id="hpg-iss-20260525", ex_date=EX_DATE, phase="pre_event",
            ticker="HPG", retrieved_at="2026-05-22T02:00:00Z", sha256="ab" * 32,
        )
        self.assertEqual(first, second)
        self.assertIn("/pre_event/", first)
        self.assertTrue(first.startswith(protocol.EVIDENCE_ROOT))
        post = protocol.artifact_path(
            event_id="hpg-iss-20260525", ex_date=EX_DATE, phase="post_event",
            ticker="HPG", retrieved_at="2026-05-27T02:00:00Z", sha256="cd" * 32,
        )
        self.assertNotEqual(first, post)
        with self.assertRaises(protocol.MutabilityProtocolError):
            protocol.artifact_path(
                event_id="x", ex_date="25-05-2026", phase="pre_event",
                ticker="HPG", retrieved_at="2026-05-22T02:00:00Z", sha256="ab" * 32,
            )
        with self.assertRaises(protocol.MutabilityProtocolError):
            protocol.artifact_path(
                event_id="x", ex_date=EX_DATE, phase="whenever",
                ticker="HPG", retrieved_at="2026-05-22T02:00:00Z", sha256="ab" * 32,
            )

    def test_20_production_artifacts_and_is_actionable_remain_unchanged(self):
        snapshot = caps.matrix_snapshot()
        self.assertEqual(snapshot["is_actionable_effect"], "none")
        self.assertFalse(snapshot["liquidity_actionable"])
        active = registry.active_verdict("KBS")
        self.assertFalse(active["raw_as_traded_eligible"])
        self.assertFalse(active["official_exchange_price"])
        self.assertFalse(active["liquidity_actionable"])
        self.assertEqual(active["volume_market_scope"], "unknown")
        self.assertEqual(active["price_basis"], "empirically_event_adjusted")
        self.assertEqual(active["volume_unit"], "shares")
        self.assertEqual(active["trading_value_unit"], "VND")
        # The VCI verdict is untouched by this milestone.
        vci = registry.active_verdict("VCI")
        self.assertEqual(vci["historical_mutability"], "retrospectively_rewritten")
        self.assertFalse(vci["raw_as_traded_eligible"])


if __name__ == "__main__":
    unittest.main()
