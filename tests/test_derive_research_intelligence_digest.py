"""tests/test_derive_research_intelligence_digest.py — Unit tests for the Research Intelligence Digest V1."""
from __future__ import annotations

import copy
import unittest

from tools.derive_research_intelligence_digest import (
    CASE_EXPLICIT_DIVERGENCE,
    CASE_HIGH_FOREIGN_ROOM,
    CASE_MOMENTUM_WITH_PROP_BUY,
    CASE_PRICE_UP_WITH_ACTIVE_BUY_IMBALANCE,
    CASE_PUT_THROUGH_DOMINANCE,
    CASE_REVERSAL_WITH_ACTIVE_SELLING,
    FLAG_HIGH_VOL_LOW_VALUE,
    FLAG_LOW_REL_VOL_WITH_ACTIVITY,
    FLAG_PRICE_FLOW_DIVERGENCE,
    FLAG_PUT_THROUGH_DOMINANCE,
    INSUFFICIENT_COVERAGE,
    MAX_COVERAGE_GAP_EXAMPLES,
    NO_PUT_THROUGH_RECORDED,
    PUT_THROUGH_RECORDED,
    PUT_THROUGH_UNKNOWN,
    SAMPLE_DESCRIPTIVE,
    IdentityChainMismatchError,
    build_research_intelligence_digest,
    generate_research_intelligence_markdown_summary,
    validate_identity_chain,
)

CAP_IDENTITY = "capability_research_digest:mock_sha_cap"
MS_IDENTITY = "market_state_and_candidates:mock_sha_ms"
CD_IDENTITY = "cross_dimension_research_digest:mock_sha_cd"


def _dnse(close, ma20, ret, rel_vol, vol20):
    return {
        "exact_session_close_vnd": close,
        "ma_20_vnd": ma20,
        "return_1d": ret,
        "relative_volume_provider_scoped": rel_vol,
        "volatility_20d": vol20,
    }


def _input_metrics(close, ret, ma20, rel_vol, vol20):
    return {
        "close_vnd": close,
        "return_1d": ret,
        "ma_20_vnd": ma20,
        "relative_volume_provider_scoped": rel_vol,
        "volatility_20d": vol20,
    }


class TestResearchIntelligenceDigest(unittest.TestCase):
    def setUp(self) -> None:
        # ---- 8-symbol mock universe -------------------------------------------------
        # SYM_A: MOMENTUM_PARTICIPATION, FULLY_ENRICHED, exact-zero put-through, high value.
        # SYM_B: MOMENTUM_PARTICIPATION, FULLY_ENRICHED, dominant put-through, low value.
        # SYM_D: HIGH_VOLATILITY_WATCH, trading-history-only acquired, very low value.
        # SYM_E: HIGH_ACTIVITY_REVERSAL_OR_DISTRIBUTION, FULLY_ENRICHED, price/prop divergence.
        # SYM_F: no cohort, ACQUIRED with put_through missing (None, not zero).
        # SYM_G: PROVIDER_RATE_LIMITED, no cohort.
        # SYM_H: REQUESTED_BUT_MISSING, no cohort.
        # SYM_I: sole TREND_WITHOUT_PARTICIPATION member, NOT_ACQUIRED_IN_THIS_SCALEOUT.
        records = [
            {
                "ticker": "SYM_A",
                "dnse_market_data": _dnse(10000.0, 9000.0, 0.05, 2.0, 0.02),
                "fhsc_value_volume_composition": {
                    "status": "ACQUIRED",
                    "matched_traded_value_vnd": 20_000_000_000.0,
                    "put_through_traded_value_vnd": 0.0,
                    "put_through_value_ratio": 0.0,
                },
            },
            {
                "ticker": "SYM_B",
                "dnse_market_data": _dnse(5000.0, 4500.0, 0.02, 1.6, 0.015),
                "fhsc_value_volume_composition": {
                    "status": "ACQUIRED",
                    "matched_traded_value_vnd": 400_000_000.0,
                    "put_through_traded_value_vnd": 600_000_000.0,
                    "put_through_value_ratio": 0.6,
                },
            },
            {
                "ticker": "SYM_D",
                "dnse_market_data": _dnse(3000.0, 3100.0, 0.001, 1.0, 0.09),
                "fhsc_value_volume_composition": {
                    "status": "ACQUIRED",
                    "matched_traded_value_vnd": 10_000_000.0,
                    "put_through_traded_value_vnd": 0.0,
                    "put_through_value_ratio": 0.0,
                },
            },
            {
                "ticker": "SYM_E",
                "dnse_market_data": _dnse(2000.0, 2100.0, -0.03, 2.5, 0.03),
                "fhsc_value_volume_composition": {
                    "status": "ACQUIRED",
                    "matched_traded_value_vnd": 4_000_000_000.0,
                    "put_through_traded_value_vnd": 0.0,
                    "put_through_value_ratio": 0.0,
                },
            },
            {
                "ticker": "SYM_F",
                "dnse_market_data": _dnse(1000.0, 900.0, 0.01, 1.0, 0.01),
                "fhsc_value_volume_composition": {
                    "status": "ACQUIRED",
                    "matched_traded_value_vnd": 500_000_000.0,
                    "put_through_traded_value_vnd": None,
                    "put_through_value_ratio": None,
                },
            },
            {
                "ticker": "SYM_G",
                "dnse_market_data": _dnse(1500.0, 1500.0, 0.0, 1.0, 0.01),
                "fhsc_value_volume_composition": {"status": "PROVIDER_RATE_LIMITED"},
            },
            {
                "ticker": "SYM_H",
                "dnse_market_data": _dnse(1500.0, 1500.0, 0.0, 1.0, 0.01),
                "fhsc_value_volume_composition": {"status": "REQUESTED_BUT_MISSING"},
            },
            {
                "ticker": "SYM_I",
                "dnse_market_data": _dnse(1500.0, 1400.0, 0.0, 1.0, 0.01),
                "fhsc_value_volume_composition": {"status": "NOT_ACQUIRED_IN_THIS_SCALEOUT"},
            },
            # SYM_J: a distinct raw non-acquired status from SYM_H's -- must never be merged
            # into a generic "missing" label by the integration layer.
            {
                "ticker": "SYM_J",
                "dnse_market_data": _dnse(1500.0, 1500.0, 0.0, 1.0, 0.01),
                "fhsc_value_volume_composition": {"status": "MISSING_REQUESTED_SESSION"},
            },
        ]

        self.mock_capability_digest = {
            "schema_version": "1.0.0",
            "session_date": "2026-08-21",
            "digest_identity": CAP_IDENTITY,
            "market_wide_core": {"aggregate_scope": "FULL_RESEARCH_UNIVERSE", "universe_count": 9},
            "coverage_summary": {
                "trading_history_scaleout_decomposition": {
                    "total_universe_count": 9,
                    "acquired_count": 5,
                    "rate_limited_count": 1,
                    "missing_requested_session_count": 2,
                    "budget_exhausted_count": 0,
                    "unattempted_count": 1,
                    "reconciled_sum": 9,
                    "reconciliation_valid": True,
                },
            },
            "records": records,
        }

        self.mock_market_state_artifact = {
            "schema_version": "1.0.0",
            "session_date": "2026-08-21",
            "artifact_identity": MS_IDENTITY,
            "input_digest_identity": CAP_IDENTITY,
            "market_state": {
                "aggregate_scope": "FULL_RESEARCH_UNIVERSE",
                "universe_count": 9,
                "session_date": "2026-08-21",
                "regime_classification": {"regime_label": "MIXED", "derivation_reason": "mock"},
                "breadth": {"advancers_count": 4, "decliners_count": 1, "unchanged_count": 3, "advance_decline_ratio": 4.0},
                "return_distribution": {"mean_return_1d": 0.01, "median_return_1d": 0.01},
                "moving_average_breadth": {"above_ma20_count": 3, "at_or_below_ma20_count": 5, "above_ma20_ratio": 0.375},
                "volatility_distribution": {"mean_volatility_20d": 0.03, "median_volatility_20d": 0.03},
                "relative_volume_breadth": {"elevated_volume_count": 3},
                "cross_metric_intersections": {"positive_return_and_above_ma20_count": 2},
                "descriptive_tails": {"top_5_gainers": [], "top_5_decliners": []},
            },
            "research_candidate_cohorts": {
                "cohort_summaries": {
                    "MOMENTUM_PARTICIPATION": {"description": "mock momentum rule"},
                    "HIGH_ACTIVITY_REVERSAL_OR_DISTRIBUTION": {"description": "mock reversal rule"},
                    "HIGH_VOLATILITY_WATCH": {"description": "mock volatility rule"},
                    "TREND_WITHOUT_PARTICIPATION": {"description": "mock trend rule"},
                    "FHSC_ENRICHED_FLOW_WATCH": {"description": "mock flow watch rule"},
                },
                "cohort_entries": {
                    "MOMENTUM_PARTICIPATION": [
                        {"ticker": "SYM_A", "input_metrics": _input_metrics(10000.0, 0.05, 9000.0, 2.0, 0.02)},
                        {"ticker": "SYM_B", "input_metrics": _input_metrics(5000.0, 0.02, 4500.0, 1.6, 0.015)},
                    ],
                    "HIGH_ACTIVITY_REVERSAL_OR_DISTRIBUTION": [
                        {"ticker": "SYM_E", "input_metrics": _input_metrics(2000.0, -0.03, 2100.0, 2.5, 0.03)},
                    ],
                    "HIGH_VOLATILITY_WATCH": [
                        {"ticker": "SYM_D", "input_metrics": _input_metrics(3000.0, 0.001, 3100.0, 1.0, 0.09)},
                        {"ticker": "SYM_G", "input_metrics": _input_metrics(1500.0, 0.0, 1500.0, 1.0, 0.01)},
                    ],
                    "TREND_WITHOUT_PARTICIPATION": [
                        {"ticker": "SYM_I", "input_metrics": _input_metrics(1500.0, 0.0, 1400.0, 1.0, 0.01)},
                        {"ticker": "SYM_H", "input_metrics": _input_metrics(1500.0, 0.0, 1500.0, 1.0, 0.01)},
                        {"ticker": "SYM_J", "input_metrics": _input_metrics(1500.0, 0.0, 1500.0, 1.0, 0.01)},
                    ],
                    "FHSC_ENRICHED_FLOW_WATCH": [
                        {"ticker": "SYM_A", "input_metrics": _input_metrics(10000.0, 0.05, 9000.0, 2.0, 0.02)},
                        {"ticker": "SYM_B", "input_metrics": _input_metrics(5000.0, 0.02, 4500.0, 1.6, 0.015)},
                        {"ticker": "SYM_E", "input_metrics": _input_metrics(2000.0, -0.03, 2100.0, 2.5, 0.03)},
                    ],
                },
            },
        }

        def _target_record(ticker, ret_1d, prop_alignment, imbalance_alignment, reason_codes, cohorts, foreign_util=0.5, foreign_char="MODERATE_FOREIGN_ROOM_UTILIZATION"):
            return {
                "ticker": ticker,
                "enrichment_tier": "FULLY_ENRICHED",
                "acquired_capabilities": ["TRADING_HISTORY", "FOREIGN_ROOM", "PROPRIETARY_FLOW", "MICROSTRUCTURE"],
                "missing_or_failed_capabilities": {},
                "active_research_cohorts": cohorts,
                "reason_codes": reason_codes,
                "cross_dimension_analysis": {
                    "price_vs_prop_alignment": prop_alignment,
                    "price_vs_order_imbalance_alignment": imbalance_alignment,
                    "put_through_character": "NO_MATERIAL_PUT_THROUGH_SIGNAL",
                    "foreign_room_character": foreign_char,
                },
                "price_and_trend": {"close_vnd": 1.0, "ma_20_vnd": 1.0, "return_1d": ret_1d, "relative_volume": 1.0, "above_ma20": True},
                "traded_value_composition": {
                    "matched_traded_value_vnd": 1.0, "put_through_traded_value_vnd": 0.0,
                    "total_traded_value_vnd": 1.0, "put_through_share_ratio": 0.0,
                },
                "volume_composition": {"matched_volume_shares": 1.0, "put_through_volume_shares": 0.0, "total_volume_shares": 1.0},
                "foreign_room": {"status": "ACQUIRED", "max_shares": 100, "owned_shares": 50, "available_shares": 50, "utilization_ratio": foreign_util},
                "proprietary_flow": {"status": "ACQUIRED", "buy_value_vnd": 1.0, "sell_value_vnd": 0.0, "net_value_vnd": 1.0, "buy_volume": 1.0, "sell_volume": 0.0, "net_volume": 1.0},
                "microstructure": {"status": "ACQUIRED", "active_buy_orders": 1, "active_sell_orders": 1, "active_buy_volume": 1.0, "active_sell_volume": 1.0, "active_net_volume": 0.0, "imbalance_ratio": 0.0},
            }

        target_records = [
            _target_record(
                "SYM_A", 0.05, "PRICE_UP_WITH_PROP_NET_BUY", "PRICE_UP_WITH_ACTIVE_BUY_SKEW",
                ["MOMENTUM_WITH_PROP_BUY", "MATERIAL_ACTIVE_BUY_IMBALANCE", "PROP_NET_BUY"],
                ["MOMENTUM_PARTICIPATION", "FHSC_ENRICHED_FLOW_WATCH"],
            ),
            _target_record(
                "SYM_B", 0.02, "PRICE_UP_WITH_PROP_NET_BUY", "NOT_APPLICABLE",
                ["PUT_THROUGH_DOMINANT", "SIGNIFICANT_PUT_THROUGH_SHARE", "HIGH_FOREIGN_ROOM_UTILIZATION"],
                ["MOMENTUM_PARTICIPATION", "FHSC_ENRICHED_FLOW_WATCH"],
                foreign_util=0.85, foreign_char="HIGH_FOREIGN_ROOM_UTILIZATION",
            ),
            _target_record(
                "SYM_E", -0.03, "PRICE_DOWN_WITH_PROP_NET_BUY", "NOT_APPLICABLE",
                ["REVERSAL_WITH_ACTIVE_SELLING", "PROP_NET_BUY"],
                ["HIGH_ACTIVITY_REVERSAL_OR_DISTRIBUTION", "FHSC_ENRICHED_FLOW_WATCH"],
            ),
        ]

        self.mock_cross_dimension_digest = {
            "schema_version": "1.0.0",
            "session_date": "2026-08-21",
            "digest_identity": CD_IDENTITY,
            "input_digest_identity": CAP_IDENTITY,
            "input_candidates_identity": MS_IDENTITY,
            "coverage_reconciliation": {
                "total_universe_count": 9,
                "trading_history_acquired_count": 5,
                "fully_enriched_count": 3,
                "fully_enriched_symbols": ["SYM_A", "SYM_B", "SYM_E"],
                "partially_enriched_count": 0,
                "partially_enriched_symbols": [],
                "trading_history_only_count": 2,
                "provider_rate_limited_count": 1,
                "provider_rate_limited_symbols": ["SYM_G"],
                "transport_failure_count": 2,
                "transport_failure_symbols": ["SYM_H", "SYM_J"],
                "genuinely_unattempted_count": 1,
                "reconciled_sum": 9,
                "reconciliation_valid": True,
            },
            "target_records": target_records,
        }

    def _build(self):
        return build_research_intelligence_digest(
            self.mock_capability_digest, self.mock_market_state_artifact, self.mock_cross_dimension_digest,
        )

    # 1. Full-market metrics retain their own (524-analog = 8) denominator, unrecomputed.
    def test_full_market_metrics_retain_universe_denominator_and_are_passthrough(self) -> None:
        artifact = self._build()
        ms = artifact["market_state"]
        self.assertEqual(ms["universe_count"], 9)
        # Exact pass-through, not recomputation.
        self.assertEqual(ms["breadth"], self.mock_market_state_artifact["market_state"]["breadth"])
        self.assertEqual(ms["return_distribution"], self.mock_market_state_artifact["market_state"]["return_distribution"])

    # 2. FHSC metrics retain their own actual sample denominator (5), distinct from the universe (8).
    def test_fhsc_sample_denominator_distinct_from_universe_denominator(self) -> None:
        artifact = self._build()
        ta = artifact["trading_activity"]
        self.assertEqual(ta["universe_denominator"], 9)
        self.assertEqual(ta["sample_denominator"], 5)
        self.assertNotEqual(ta["sample_denominator"], ta["universe_denominator"])
        pt = artifact["put_through_digest"]
        self.assertEqual(pt["sample_denominator"], 5)

    # 3. Unacquired/missing data never becomes zero.
    def test_unacquired_and_missing_never_become_zero(self) -> None:
        artifact = self._build()
        # SYM_I (unacquired) must not appear as a trading_activity or put_through entry at all.
        ta_tickers = {e["ticker"] for e in artifact["trading_activity"]["entries"]}
        pt_tickers = {e["ticker"] for e in artifact["put_through_digest"]["entries"]}
        self.assertNotIn("SYM_I", ta_tickers)
        self.assertNotIn("SYM_I", pt_tickers)

        # TREND_WITHOUT_PARTICIPATION's sole member (SYM_I) is unacquired -> covered denominator is 0,
        # and the matched-value distribution reports None, never a fabricated 0.
        trend_profile = artifact["cohort_profiles"]["TREND_WITHOUT_PARTICIPATION"]
        self.assertEqual(trend_profile["trading_history_covered_count"], 0)
        self.assertEqual(trend_profile["matched_traded_value_distribution_among_covered"]["denominator"], 0)
        self.assertIsNone(trend_profile["matched_traded_value_distribution_among_covered"]["median"])

        # SYM_F has put_through_traded_value_vnd = None (missing) -> total must stay None, not 0.
        sym_f = next(e for e in artifact["put_through_digest"]["entries"] if e["ticker"] == "SYM_F")
        self.assertIsNone(sym_f["put_through_traded_value_vnd"])
        self.assertIsNone(sym_f["total_traded_value_vnd"])
        self.assertEqual(sym_f["put_through_status"], PUT_THROUGH_UNKNOWN)

    # 4. Zero put-through becomes NO_PUT_THROUGH_RECORDED, not a broader inference.
    def test_zero_put_through_becomes_no_put_through_recorded(self) -> None:
        artifact = self._build()
        entries_by_ticker = {e["ticker"]: e for e in artifact["put_through_digest"]["entries"]}

        sym_a = entries_by_ticker["SYM_A"]
        self.assertEqual(sym_a["put_through_traded_value_vnd"], 0.0)
        self.assertEqual(sym_a["put_through_status"], NO_PUT_THROUGH_RECORDED)

        sym_b = entries_by_ticker["SYM_B"]
        self.assertEqual(sym_b["put_through_status"], PUT_THROUGH_RECORDED)

        # The disclaimer must scope the claim to this symbol/session, not a market-wide inference,
        # and must not name an actor.
        disclaimer = artifact["put_through_digest"]["disclaimer"].lower()
        self.assertIn("per-symbol", disclaimer)
        self.assertNotIn("institutional", disclaimer)
        self.assertNotIn("all off-market", disclaimer)

    # 5 & 6. Cohort comparisons expose coverage, and insufficient coverage fails closed.
    def test_cohort_comparison_exposes_coverage_and_fails_closed_when_insufficient(self) -> None:
        artifact = self._build()
        metrics = artifact["cohort_comparison"]["metrics"]

        # Every cell in every comparison row must carry an explicit denominator.
        for _metric_name, row in metrics.items():
            for _cohort_name, cell in row.items():
                self.assertIn("denominator", cell)
                self.assertIn("value", cell)

        # TREND_WITHOUT_PARTICIPATION's sole member is unacquired -> covered-dependent metrics
        # must fail closed to INSUFFICIENT_COVERAGE_FOR_COMPARISON rather than extrapolate.
        trend_col = "TREND_WITHOUT_PARTICIPATION"
        self.assertEqual(
            metrics["median_matched_traded_value_vnd_among_covered"][trend_col]["value"], INSUFFICIENT_COVERAGE,
        )
        self.assertEqual(
            metrics["put_through_incidence_ratio_among_covered"][trend_col]["value"], INSUFFICIENT_COVERAGE,
        )
        # But its total-member-count-based metrics (real denominator of 1) are NOT insufficient.
        self.assertNotEqual(metrics["trading_history_coverage_ratio"][trend_col]["value"], INSUFFICIENT_COVERAGE)
        self.assertEqual(metrics["trading_history_coverage_ratio"][trend_col]["value"], 0.0)

    # 7. Cross-dimension reason codes are consumed without semantic mutation.
    def test_cross_dimension_reason_codes_consumed_verbatim(self) -> None:
        artifact = self._build()
        cd = artifact["cross_dimension_cases"]

        source_by_ticker = {r["ticker"]: r for r in self.mock_cross_dimension_digest["target_records"]}
        for bucket in cd["cases"].values():
            for member in bucket["members"]:
                source = source_by_ticker[member["ticker"]]
                self.assertEqual(member["reason_codes"], source["reason_codes"])
                self.assertEqual(member["cross_dimension_analysis"], source["cross_dimension_analysis"])

        self.assertEqual(cd["cases"][CASE_MOMENTUM_WITH_PROP_BUY]["count"], 1)
        self.assertEqual(cd["cases"][CASE_PRICE_UP_WITH_ACTIVE_BUY_IMBALANCE]["count"], 1)
        self.assertEqual(cd["cases"][CASE_PUT_THROUGH_DOMINANCE]["count"], 1)
        self.assertEqual(cd["cases"][CASE_HIGH_FOREIGN_ROOM]["count"], 1)
        self.assertEqual(cd["cases"][CASE_REVERSAL_WITH_ACTIVE_SELLING]["count"], 1)
        # SYM_E: price down (-3%) with proprietary net buy is an explicit divergence.
        self.assertEqual(cd["cases"][CASE_EXPLICIT_DIVERGENCE]["count"], 1)
        self.assertEqual(cd["cases"][CASE_EXPLICIT_DIVERGENCE]["members"][0]["ticker"], "SYM_E")

    # 8. No recommendation/ranking/sizing/valuation/PIT authority leaks.
    def test_no_recommendation_ranking_sizing_valuation_pit_authority(self) -> None:
        artifact = self._build()
        self.assertEqual(artifact["authority_boundaries"], {
            "authority_effect": "NONE",
            "raw_as_traded_promoted": False,
            "pit_backtest_eligible": False,
            "liquidity_sizing_authority": "BLOCKED",
            "valuation_authority": False,
            "recommendation_authority": False,
            "ranking_authority": False,
            "database_mutated": False,
        })

    # 9. Follow-up flags remain research-only (no BUY/SELL/TOP PICK/OPPORTUNITY authored language).
    def test_follow_up_flags_remain_research_only(self) -> None:
        artifact = self._build()
        flags = artifact["follow_up_flags"]["flags"]
        self.assertGreater(len(flags), 0)

        forbidden = ("top pick", "opportunity", " buy ", " sell ", "buy now", "sell now")
        for f in flags:
            authored_text = f"{f['flag_type']} {f['research_rationale']}".lower()
            for token in forbidden:
                self.assertNotIn(token, authored_text)

        # SYM_D: HIGH_VOLATILITY_WATCH member, acquired, low absolute value -> specific flag fires.
        flag_types_by_ticker = {}
        for f in flags:
            flag_types_by_ticker.setdefault(f["ticker"], set()).add(f["flag_type"])
        self.assertIn(FLAG_HIGH_VOL_LOW_VALUE, flag_types_by_ticker.get("SYM_D", set()))
        # SYM_B: put-through dominant -> flagged.
        self.assertIn(FLAG_PUT_THROUGH_DOMINANCE, flag_types_by_ticker.get("SYM_B", set()))
        # SYM_E: explicit divergence -> flagged.
        self.assertIn(FLAG_PRICE_FLOW_DIVERGENCE, flag_types_by_ticker.get("SYM_E", set()))
        # SYM_I/SYM_H/SYM_J are cohort members but unacquired -> they belong in the separate
        # data_coverage_backlog, never as a per-symbol entry in the research follow-up list.
        self.assertNotIn("SYM_I", flag_types_by_ticker)
        self.assertNotIn("SYM_H", flag_types_by_ticker)
        self.assertNotIn("SYM_J", flag_types_by_ticker)

    # 10. Deterministic replay identity is stable.
    def test_deterministic_replay_identity_stable(self) -> None:
        first = self._build()
        second = self._build()
        self.assertEqual(first["digest_sha256"], second["digest_sha256"])
        self.assertEqual(first["digest_identity"], second["digest_identity"])

    # 11. Changed input identity changes output identity.
    def test_changed_input_identity_changes_output_identity(self) -> None:
        baseline = self._build()

        mutated_cap = copy.deepcopy(self.mock_capability_digest)
        mutated_cap["records"][0]["dnse_market_data"]["return_1d"] = 0.99
        mutated_cap["digest_identity"] = "capability_research_digest:mock_sha_cap_v2"

        mutated_ms = copy.deepcopy(self.mock_market_state_artifact)
        mutated_ms["input_digest_identity"] = "capability_research_digest:mock_sha_cap_v2"

        mutated_cd = copy.deepcopy(self.mock_cross_dimension_digest)
        mutated_cd["input_digest_identity"] = "capability_research_digest:mock_sha_cap_v2"

        mutated = build_research_intelligence_digest(mutated_cap, mutated_ms, mutated_cd)

        self.assertNotEqual(baseline["digest_sha256"], mutated["digest_sha256"])
        self.assertNotEqual(baseline["digest_identity"], mutated["digest_identity"])

    def test_identity_chain_mismatch_fails_closed(self) -> None:
        mismatched_ms = copy.deepcopy(self.mock_market_state_artifact)
        mismatched_ms["input_digest_identity"] = "capability_research_digest:some_other_sha"

        with self.assertRaises(IdentityChainMismatchError):
            validate_identity_chain(self.mock_capability_digest, mismatched_ms, self.mock_cross_dimension_digest)

        with self.assertRaises(IdentityChainMismatchError):
            build_research_intelligence_digest(self.mock_capability_digest, mismatched_ms, self.mock_cross_dimension_digest)

    def test_multi_cohort_membership_preserved_explicitly(self) -> None:
        artifact = self._build()
        pt_entries_by_ticker = {e["ticker"]: e for e in artifact["put_through_digest"]["entries"]}
        sym_a = pt_entries_by_ticker["SYM_A"]
        self.assertIn("MOMENTUM_PARTICIPATION", sym_a["cohort_memberships"])
        self.assertIn("FHSC_ENRICHED_FLOW_WATCH", sym_a["cohort_memberships"])
        self.assertEqual(len(sym_a["cohort_memberships"]), 2)

    def test_trading_activity_sample_relative_bands_are_labelled_and_unknown_when_uncomputable(self) -> None:
        artifact = self._build()
        entries_by_ticker = {e["ticker"]: e for e in artifact["trading_activity"]["entries"]}

        sym_a = entries_by_ticker["SYM_A"]
        labels_a = {c["label"] for c in sym_a["classifications"]}
        self.assertIn("HIGH_MATCHED_VALUE", labels_a)
        high_value_label = next(c for c in sym_a["classifications"] if c["label"] == "HIGH_MATCHED_VALUE")
        self.assertEqual(high_value_label["band_type"], "SAMPLE_RELATIVE")

        # SYM_F's total is unknown (put-through missing) -> classification is UNKNOWN, not silently dropped.
        sym_f = entries_by_ticker["SYM_F"]
        labels_f = {c["label"] for c in sym_f["classifications"]}
        self.assertIn("UNKNOWN", labels_f)

    def test_markdown_summary_renders_required_sections_in_order(self) -> None:
        artifact = self._build()
        md = generate_research_intelligence_markdown_summary(artifact)
        headings = (
            "MARKET STATE", "WHAT IS BROADLY HAPPENING", "ACTIVE RESEARCH COHORTS",
            "TRADING ACTIVITY", "PUT-THROUGH WATCH", "CROSS-DIMENSION CASES",
            "QUESTIONS WORTH INVESTIGATING", "DATA QUALITY / COVERAGE",
        )
        positions = []
        for heading in headings:
            self.assertIn(heading, md)
            positions.append(md.index(heading))
        # Desired order: QUESTIONS WORTH INVESTIGATING precedes DATA QUALITY / COVERAGE, and the
        # coverage backlog is rendered only inside the DATA QUALITY / COVERAGE section.
        self.assertEqual(positions, sorted(positions))
        self.assertIn("SYM_A", md)
        self.assertIn("Data Coverage Backlog", md)
        self.assertGreater(md.index("Data Coverage Backlog"), md.index("DATA QUALITY / COVERAGE"))
        self.assertGreater(md.index("Data Coverage Backlog"), md.index("QUESTIONS WORTH INVESTIGATING"))


    # 1. Research follow-up list contains only evidence-supported flag types -- never a
    #    per-symbol "no data yet" entry.
    def test_follow_up_list_contains_only_evidence_supported_flag_types(self) -> None:
        artifact = self._build()
        allowed_flag_types = {
            FLAG_PUT_THROUGH_DOMINANCE, FLAG_PRICE_FLOW_DIVERGENCE,
            FLAG_LOW_REL_VOL_WITH_ACTIVITY, FLAG_HIGH_VOL_LOW_VALUE,
        }
        flags = artifact["follow_up_flags"]["flags"]
        self.assertGreater(len(flags), 0)
        for f in flags:
            self.assertIn(f["flag_type"], allowed_flag_types)
        self.assertEqual(set(artifact["follow_up_flags"]["flag_counts_by_type"].keys()), allowed_flag_types)

    # 2. Coverage backlog is a separate, aggregated section (not folded into follow_up_flags).
    def test_data_coverage_backlog_is_separate_and_aggregated(self) -> None:
        artifact = self._build()
        self.assertIn("data_coverage_backlog", artifact)
        backlog = artifact["data_coverage_backlog"]

        # SYM_I, SYM_H, SYM_J (unacquired cohort members) are accounted for here, aggregated,
        # not as individual entries in follow_up_flags.
        # SYM_I, SYM_H, SYM_J (TREND_WITHOUT_PARTICIPATION) + SYM_G (HIGH_VOLATILITY_WATCH) = 4.
        gap = backlog["active_cohort_members_lacking_fhsc_trading_history"]
        self.assertEqual(gap["total_distinct_symbols"], 4)
        self.assertEqual(gap["by_cohort"]["TREND_WITHOUT_PARTICIPATION"]["members_lacking_fhsc_trading_history"], 3)
        self.assertEqual(gap["by_cohort"]["HIGH_VOLATILITY_WATCH"]["members_lacking_fhsc_trading_history"], 1)
        self.assertIn("acquisition_status_counts", backlog)

    # 3. Coverage-gap examples are bounded to <= MAX_COVERAGE_GAP_EXAMPLES (10), even when the
    #    real gap population is much larger.
    def test_coverage_gap_examples_bounded_to_ten(self) -> None:
        big_records = []
        cohort_entries = []
        for i in range(15):
            ticker = f"BIG_{i:02d}"
            big_records.append({
                "ticker": ticker,
                "dnse_market_data": _dnse(1000.0, 1000.0, 0.0, 1.0, 0.01),
                "fhsc_value_volume_composition": {"status": "NOT_ACQUIRED_IN_THIS_SCALEOUT"},
            })
            cohort_entries.append({"ticker": ticker, "input_metrics": _input_metrics(1000.0, 0.0, 1000.0, 1.0, 0.01)})

        big_cap = {
            "schema_version": "1.0.0", "session_date": "2026-08-21", "digest_identity": CAP_IDENTITY,
            "market_wide_core": {"aggregate_scope": "FULL_RESEARCH_UNIVERSE", "universe_count": 15},
            "coverage_summary": {"trading_history_scaleout_decomposition": {
                "total_universe_count": 15, "acquired_count": 0, "rate_limited_count": 0,
                "missing_requested_session_count": 0, "budget_exhausted_count": 0,
                "unattempted_count": 15, "reconciled_sum": 15, "reconciliation_valid": True,
            }},
            "records": big_records,
        }
        big_ms = {
            "schema_version": "1.0.0", "session_date": "2026-08-21",
            "artifact_identity": MS_IDENTITY, "input_digest_identity": CAP_IDENTITY,
            "market_state": {
                "aggregate_scope": "FULL_RESEARCH_UNIVERSE", "universe_count": 15, "session_date": "2026-08-21",
                "regime_classification": {"regime_label": "MIXED", "derivation_reason": "mock"},
                "breadth": {"advancers_count": 0, "decliners_count": 0, "unchanged_count": 15, "advance_decline_ratio": None},
                "return_distribution": {"mean_return_1d": 0.0, "median_return_1d": 0.0},
                "moving_average_breadth": {"above_ma20_count": 0, "at_or_below_ma20_count": 15, "above_ma20_ratio": 0.0},
                "volatility_distribution": {"mean_volatility_20d": 0.01, "median_volatility_20d": 0.01},
                "relative_volume_breadth": {"elevated_volume_count": 0},
                "cross_metric_intersections": {},
                "descriptive_tails": {"top_5_gainers": [], "top_5_decliners": []},
            },
            "research_candidate_cohorts": {
                "cohort_summaries": {
                    "MOMENTUM_PARTICIPATION": {"description": "d"}, "HIGH_ACTIVITY_REVERSAL_OR_DISTRIBUTION": {"description": "d"},
                    "HIGH_VOLATILITY_WATCH": {"description": "d"}, "TREND_WITHOUT_PARTICIPATION": {"description": "d"},
                    "FHSC_ENRICHED_FLOW_WATCH": {"description": "d"},
                },
                "cohort_entries": {
                    "MOMENTUM_PARTICIPATION": [], "HIGH_ACTIVITY_REVERSAL_OR_DISTRIBUTION": [],
                    "HIGH_VOLATILITY_WATCH": [], "TREND_WITHOUT_PARTICIPATION": cohort_entries,
                    "FHSC_ENRICHED_FLOW_WATCH": [],
                },
            },
        }
        big_cd = {
            "schema_version": "1.0.0", "session_date": "2026-08-21", "digest_identity": CD_IDENTITY,
            "input_digest_identity": CAP_IDENTITY, "input_candidates_identity": MS_IDENTITY,
            "coverage_reconciliation": {
                "total_universe_count": 15, "trading_history_acquired_count": 0,
                "fully_enriched_count": 0, "fully_enriched_symbols": [],
                "partially_enriched_count": 0, "partially_enriched_symbols": [],
                "trading_history_only_count": 0, "provider_rate_limited_count": 0,
                "provider_rate_limited_symbols": [], "transport_failure_count": 0,
                "transport_failure_symbols": [], "genuinely_unattempted_count": 15,
                "reconciled_sum": 15, "reconciliation_valid": True,
            },
            "target_records": [],
        }

        artifact = build_research_intelligence_digest(big_cap, big_ms, big_cd)
        backlog = artifact["data_coverage_backlog"]
        examples = backlog["coverage_gap_examples"]

        self.assertEqual(examples["total_available_count"], 15)
        self.assertEqual(examples["max_examples"], MAX_COVERAGE_GAP_EXAMPLES)
        self.assertEqual(examples["returned_count"], MAX_COVERAGE_GAP_EXAMPLES)
        self.assertLessEqual(len(examples["examples"]), 10)
        for ex in examples["examples"]:
            self.assertEqual(ex["exact_upstream_status"], "NOT_ACQUIRED_IN_THIS_SCALEOUT")
            # The note explicitly disclaims priority/recommendation semantics; it must not
            # assert an actual priority (only ever negate one).
            self.assertIn("not a priority", ex["note"].lower())

    # 4. The digest must not recommend reopening a broad FHSC acquisition wave anywhere in its
    #    own authored text.
    def test_digest_does_not_recommend_acquisition_wave(self) -> None:
        artifact = self._build()
        forbidden = ("prioritize", "next wave", "acquisition wave", "recommend acquiring", "should acquire")

        def _walk_strings(obj):
            if isinstance(obj, str):
                yield obj
            elif isinstance(obj, dict):
                for v in obj.values():
                    yield from _walk_strings(v)
            elif isinstance(obj, list):
                for v in obj:
                    yield from _walk_strings(v)

        for section_name in ("follow_up_flags", "data_coverage_backlog"):
            for s in _walk_strings(artifact[section_name]):
                low = s.lower()
                for token in forbidden:
                    self.assertNotIn(token, low, f"forbidden acquisition-recommendation language in {section_name}: {s!r}")

    # 5, 6, 7. Exact upstream acquisition status is preserved and distinguishable: transport
    # failure/missing-session != provider rate limit != genuinely unattempted.
    def test_exact_upstream_acquisition_status_preserved_and_distinguishable(self) -> None:
        artifact = self._build()
        examples_by_ticker = {
            ex["ticker"]: ex for ex in artifact["data_coverage_backlog"]["coverage_gap_examples"]["examples"]
        }

        self.assertEqual(examples_by_ticker["SYM_H"]["exact_upstream_status"], "REQUESTED_BUT_MISSING")
        self.assertEqual(examples_by_ticker["SYM_J"]["exact_upstream_status"], "MISSING_REQUESTED_SESSION")
        self.assertEqual(examples_by_ticker["SYM_G"]["exact_upstream_status"], "PROVIDER_RATE_LIMITED")
        self.assertEqual(examples_by_ticker["SYM_I"]["exact_upstream_status"], "NOT_ACQUIRED_IN_THIS_SCALEOUT")

        # None of the four distinct raw statuses collapse onto each other.
        statuses = {
            examples_by_ticker["SYM_H"]["exact_upstream_status"],
            examples_by_ticker["SYM_J"]["exact_upstream_status"],
            examples_by_ticker["SYM_G"]["exact_upstream_status"],
            examples_by_ticker["SYM_I"]["exact_upstream_status"],
        }
        self.assertEqual(len(statuses), 4)

        # The optional coarse grouping distinguishes rate-limited and unattempted as different
        # groups too, while H and J (both "attempted but missing", by different raw reasons)
        # may legitimately share a status_group without losing their distinct raw status.
        self.assertNotEqual(examples_by_ticker["SYM_G"]["status_group"], examples_by_ticker["SYM_I"]["status_group"])
        self.assertNotEqual(examples_by_ticker["SYM_H"]["exact_upstream_status"], examples_by_ticker["SYM_J"]["exact_upstream_status"])

    # 8, 9. Descriptive cohort comparisons expose the exact observed denominator and are labelled
    # explicitly; a metric with zero observed values fails closed rather than using a hidden
    # minimum-N threshold.
    def test_comparison_contract_is_explicit_and_labels_cells(self) -> None:
        artifact = self._build()
        contract = artifact["cohort_comparison"]["comparison_contract"]
        self.assertEqual(contract["minimum_denominator_for_descriptive_comparison"], 1)
        self.assertFalse(contract["extrapolates_to_full_cohort_or_universe"])

        metrics = artifact["cohort_comparison"]["metrics"]
        # MOMENTUM_PARTICIPATION has real observed coverage (n=2) -> SAMPLE_DESCRIPTIVE with the
        # exact observed denominator, never extrapolated to the cohort's full member count.
        momentum_cell = metrics["median_matched_traded_value_vnd_among_covered"]["MOMENTUM_PARTICIPATION"]
        self.assertEqual(momentum_cell["comparison_status"], SAMPLE_DESCRIPTIVE)
        self.assertEqual(momentum_cell["denominator"], 2)

        # TREND_WITHOUT_PARTICIPATION's 3 members are all unacquired -> zero observed values ->
        # fails closed, it does not silently reuse another cohort's threshold.
        trend_cell = metrics["median_matched_traded_value_vnd_among_covered"]["TREND_WITHOUT_PARTICIPATION"]
        self.assertEqual(trend_cell["comparison_status"], INSUFFICIENT_COVERAGE)
        self.assertEqual(trend_cell["denominator"], 0)


if __name__ == "__main__":
    unittest.main()
