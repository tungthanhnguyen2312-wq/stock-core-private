"""tests/test_derive_capability_first_scenario_distribution.py — Unit tests for the Capability-First
Scenario Distribution V1 engine."""
from __future__ import annotations

import copy
import unittest

from tools.derive_capability_first_scenario_distribution import (
    AXIS_FOREIGN_ROOM,
    CLASSIFICATIONS,
    DATA_WARNING,
    FACT,
    DigestIdentityError,
    _sha256_json,
    assess_evidence_depth,
    build_capability_first_scenario_distribution,
    validate_digest_identity,
)

DIGEST_CONTRACT_VERSION = "capability_first_research_intelligence_digest/v1"


def _member(ticker, *, above_ma20=True, close=10000.0, ma20=9500.0, ret=0.02, rel_vol=1.5,
            net_value=None, buy_vol=0.0, sell_vol=0.0, no_prop_activity_code=False,
            buy_skew=False, sell_skew=False, imbalance_ratio=0.0,
            put_through_ratio=0.0, put_through_character="NO_MATERIAL_PUT_THROUGH_SIGNAL",
            foreign_util=0.3, foreign_char="MODERATE_FOREIGN_ROOM_UTILIZATION", foreign_status="ACQUIRED",
            enrichment_tier="FULLY_ENRICHED", missing_caps=None, cohorts=None):
    reason_codes = []
    if above_ma20:
        reason_codes.append("ABOVE_20D_MA")
    else:
        reason_codes.append("BELOW_20D_MA")
    if no_prop_activity_code:
        reason_codes.append("NO_PROPRIETARY_TRADING_ACTIVITY")
    if buy_skew:
        reason_codes.append("ACTIVE_BUY_SKEW")
    if sell_skew:
        reason_codes.append("ACTIVE_SELL_SKEW")

    matched = 1_000_000_000.0
    put_through_value = matched * put_through_ratio / (1 - put_through_ratio) if put_through_ratio else 0.0
    total = matched + put_through_value

    return {
        "ticker": ticker,
        "enrichment_tier": enrichment_tier,
        "acquired_capabilities": ["TRADING_HISTORY", "FOREIGN_ROOM", "PROPRIETARY_FLOW", "MICROSTRUCTURE"],
        "missing_or_failed_capabilities": missing_caps or {},
        "active_research_cohorts": cohorts or [],
        "reason_codes": reason_codes,
        "cross_dimension_analysis": {
            "price_vs_prop_alignment": "MOCK_ALIGNMENT",
            "price_vs_order_imbalance_alignment": "MOCK_ALIGNMENT",
            "put_through_character": put_through_character,
            "foreign_room_character": foreign_char,
        },
        "price_and_trend": {"close_vnd": close, "ma_20_vnd": ma20, "return_1d": ret, "relative_volume": rel_vol, "above_ma20": above_ma20},
        "traded_value_composition": {
            "matched_traded_value_vnd": matched, "put_through_traded_value_vnd": put_through_value,
            "total_traded_value_vnd": total, "put_through_share_ratio": put_through_ratio,
        },
        "foreign_room": {
            "status": foreign_status, "max_shares": None, "owned_shares": None, "available_shares": None,
            "utilization_ratio": foreign_util if foreign_status == "ACQUIRED" else None,
        },
        "proprietary_flow": {
            "status": "ACQUIRED", "buy_value_vnd": 1.0, "sell_value_vnd": 1.0,
            "net_value_vnd": net_value, "buy_volume": buy_vol, "sell_volume": sell_vol,
            "net_volume": buy_vol - sell_vol,
        },
        "microstructure": {
            "status": "ACQUIRED", "active_buy_orders": 500.0, "active_sell_orders": 400.0,
            "active_buy_volume": 5000.0, "active_sell_volume": 4000.0, "active_net_volume": 1000.0,
            "imbalance_ratio": imbalance_ratio,
        },
    }


# SYM_BULL: trend/prop/imbalance all bullish, no caveats.
SYM_BULL = _member("SYM_BULL", above_ma20=True, ret=0.05, net_value=500_000_000.0, buy_vol=10.0, sell_vol=1.0,
                    buy_skew=True, imbalance_ratio=0.3, cohorts=["MOMENTUM_PARTICIPATION"])

# SYM_BEAR: trend/prop/imbalance all bearish, no caveats.
SYM_BEAR = _member("SYM_BEAR", above_ma20=False, ret=-0.04, net_value=-500_000_000.0, buy_vol=1.0, sell_vol=10.0,
                    sell_skew=True, imbalance_ratio=-0.3)

# SYM_DIVERGE: price above MA20 (bullish trend) but active sell-skew (bearish order flow) and no
# proprietary activity -- an explicit divergence, structurally different from SYM_BULL.
SYM_DIVERGE = _member("SYM_DIVERGE", above_ma20=True, ret=0.01, no_prop_activity_code=True, buy_vol=0.0, sell_vol=0.0,
                       sell_skew=True, imbalance_ratio=-0.1)

# SYM_MISSING_FOREIGN: foreign-room capability was requested but never returned (mirrors real DHM).
SYM_MISSING_FOREIGN = _member("SYM_MISSING_FOREIGN", above_ma20=True, ret=0.0, no_prop_activity_code=True,
                               foreign_status="REQUESTED_BUT_MISSING", foreign_char="NOT_APPLICABLE",
                               enrichment_tier="PARTIALLY_ENRICHED", missing_caps={"FOREIGN_ROOM": "REQUESTED_BUT_MISSING"})

# SYM_PUT_THROUGH_DOMINANT: put-through is the majority of session value.
SYM_PUT_THROUGH_DOMINANT = _member("SYM_PUT_THROUGH_DOMINANT", above_ma20=True, ret=0.0, no_prop_activity_code=True,
                                    put_through_ratio=0.9, put_through_character="PUT_THROUGH_DOMINANT_ACTIVITY")

# SYM_FOREIGN_SATURATED: all three directional axes bullish, but foreign room is saturated -- a
# present-tense structural ceiling that must still show up as countervailing evidence against BULL.
SYM_FOREIGN_SATURATED = _member("SYM_FOREIGN_SATURATED", above_ma20=True, ret=0.03, net_value=100_000_000.0,
                                 buy_vol=5.0, sell_vol=1.0, buy_skew=True, imbalance_ratio=0.2,
                                 foreign_util=0.999997, foreign_char="FOREIGN_ROOM_SATURATED_100PCT")


def _raw_digest(cases_by_ticker=None, *, universe_count=50, fully_enriched_count=7, partially_enriched_count=1,
                 sample_denominator=None, cohort_profiles=None):
    members = cases_by_ticker or {
        "mock_case_alpha": [SYM_BULL, SYM_DIVERGE],
        "mock_case_beta": [SYM_BEAR, SYM_MISSING_FOREIGN, SYM_PUT_THROUGH_DOMINANT, SYM_FOREIGN_SATURATED],
    }
    if sample_denominator is None:
        sample_denominator = fully_enriched_count + partially_enriched_count

    return {
        "schema_version": "1.0.0",
        "contract_version": DIGEST_CONTRACT_VERSION,
        "session_date": "2026-08-21",
        "source_artifacts": {
            "capability_research_digest_identity": "capability_research_digest:mock",
            "market_state_and_candidates_identity": "market_state_and_candidates:mock",
            "cross_dimension_research_digest_identity": "cross_dimension_research_digest:mock",
        },
        "market_state": {
            "aggregate_scope": "FULL_RESEARCH_UNIVERSE",
            "universe_count": universe_count,
            "session_date": "2026-08-21",
            "regime_classification": {"regime_label": "MIXED", "derivation_reason": "mock derivation", "is_descriptive_only": True},
            "breadth": {"advancers_count": 20, "decliners_count": 15, "unchanged_count": 15, "advance_decline_ratio": 1.3333},
            "return_distribution": {"mean_return_1d": 0.01, "median_return_1d": 0.005},
            "moving_average_breadth": {"above_ma20_count": 25, "above_ma20_ratio": 0.5, "at_or_below_ma20_count": 25},
            "volatility_distribution": {"mean_volatility_20d": 0.02, "median_volatility_20d": 0.018},
            "relative_volume_breadth": {"elevated_volume_count": 10},
            "cross_metric_intersections": {},
            "descriptive_tails": {"top_5_gainers": [], "top_5_decliners": []},
        },
        "cohort_profiles": cohort_profiles or {
            "MOMENTUM_PARTICIPATION": {
                "cohort": "MOMENTUM_PARTICIPATION", "total_member_count": 10,
                "return_distribution": {"n": 10, "mean": 0.02, "median": 0.015, "p25": 0.0, "p75": 0.03, "min": -0.01, "max": 0.05},
                "relative_volume_distribution": {"n": 10, "mean": 1.8, "median": 1.6, "p25": 1.0, "p75": 2.2, "min": 0.5, "max": 3.0},
            },
        },
        "cohort_comparison": {"comparison_schema_version": "1.0.0", "metrics": {}},
        "trading_activity": {"scope": "ACQUIRED_ENRICHMENT_COHORT", "entries": []},
        "put_through_digest": {"scope": "ACQUIRED_ENRICHMENT_COHORT", "entries": []},
        "cross_dimension_cases": {
            "scope": "ACQUIRED_ENRICHMENT_COHORT",
            "sample_denominator": sample_denominator,
            "universe_denominator": universe_count,
            "source_digest_identity": "cross_dimension_research_digest:mock_cd_identity",
            "disclaimer": "mock disclaimer",
            "cases": {
                name: {"count": len(m), "members": m} for name, m in members.items()
            },
        },
        "follow_up_flags": {"flags": []},
        "data_coverage_backlog": {},
        "coverage_and_data_quality": {
            "tiers": {
                "FULL_RESEARCH_UNIVERSE": universe_count,
                "ACQUIRED_TRADING_HISTORY_COHORT": 30,
                "FULLY_ENRICHED_COHORT": fully_enriched_count,
                "PARTIALLY_ENRICHED": partially_enriched_count,
                "TRADING_HISTORY_ONLY": 22,
                "PROVIDER_RATE_LIMITED": 0,
                "REQUESTED_BUT_MISSING": 0,
                "BUDGET_EXHAUSTED": 0,
                "NOT_ACQUIRED_IN_THIS_SCALEOUT": universe_count - 30,
            },
            "reconciliation": {},
        },
        "narrative_scope_notes": [],
        "authority_boundaries": {
            "authority_effect": "NONE", "raw_as_traded_promoted": False, "pit_backtest_eligible": False,
            "liquidity_sizing_authority": "BLOCKED", "valuation_authority": False,
            "recommendation_authority": False, "ranking_authority": False, "database_mutated": False,
        },
    }


def _finalize(raw: dict) -> dict:
    raw = copy.deepcopy(raw)
    raw.pop("digest_sha256", None)
    raw.pop("digest_identity", None)
    raw.pop("execution_timestamp", None)
    sha = _sha256_json(raw)
    raw["digest_sha256"] = sha
    raw["digest_identity"] = f"research_intelligence_digest_v1:{sha}"
    return raw


def _digest(**kwargs) -> dict:
    return _finalize(_raw_digest(**kwargs))


def _walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


class TestCapabilityFirstScenarioDistribution(unittest.TestCase):
    def setUp(self) -> None:
        self.digest = _digest()

    def _build(self):
        return build_capability_first_scenario_distribution(self.digest)

    def _by_ticker(self, artifact):
        return {s["ticker"]: s for s in artifact["scenarios"]}

    # -- Cohort reconciliation: 8 enriched, only 6 surfaced via cross_dimension_cases, 2 unsurfaced;
    #    the full 50-symbol universe is never conflated with either number. --------------------------
    def test_cohort_reconciliation_distinguishes_universe_enriched_and_surfaced_denominators(self) -> None:
        artifact = self._build()
        rec = artifact["cohort_reconciliation"]
        self.assertEqual(rec["full_universe_denominator"], 50)
        self.assertEqual(rec["fully_or_partially_enriched_denominator"], 8)
        self.assertEqual(rec["cross_dimension_case_surfaced_denominator"], 6)
        self.assertEqual(rec["unsurfaced_enriched_count"], 2)
        self.assertNotEqual(rec["unsurfaced_ticker_identities"], "NONE_UNSURFACED")
        self.assertTrue(rec["reconciliation_valid"])
        self.assertEqual(len(artifact["scenarios"]), 6)
        self.assertNotEqual(rec["scenario_produced_count"], rec["full_universe_denominator"])

    # -- All-bullish evidence produces a fully confirmed BULL lane and an empty BEAR lane. -----------
    def test_bull_confirmation_for_all_bullish_axes(self) -> None:
        artifact = self._build()
        sym = self._by_ticker(artifact)["SYM_BULL"]
        bull, bear = sym["scenarios"]["BULL"], sym["scenarios"]["BEAR"]
        self.assertEqual(len(bull["confirming_conditions"]), 3)
        self.assertEqual(bull["countervailing_evidence"], [])
        self.assertEqual(bear["confirming_conditions"], [])
        self.assertEqual(len(bear["countervailing_evidence"]), 3)
        for item in bull["confirming_conditions"]:
            self.assertEqual(item["classification"], "INFERENCE")

    # -- All-bearish evidence mirrors the bull case. --------------------------------------------------
    def test_bear_confirmation_for_all_bearish_axes(self) -> None:
        artifact = self._build()
        sym = self._by_ticker(artifact)["SYM_BEAR"]
        bull, bear = sym["scenarios"]["BULL"], sym["scenarios"]["BEAR"]
        self.assertEqual(len(bear["confirming_conditions"]), 3)
        self.assertEqual(bear["countervailing_evidence"], [])
        self.assertEqual(bull["confirming_conditions"], [])
        self.assertEqual(len(bull["countervailing_evidence"]), 3)

    # -- A genuine price/flow divergence produces countervailing evidence and a distinct signature. --
    def test_divergence_produces_countervailing_evidence_and_differs_from_pure_bull(self) -> None:
        artifact = self._build()
        by_ticker = self._by_ticker(artifact)
        diverge, bull = by_ticker["SYM_DIVERGE"], by_ticker["SYM_BULL"]

        bull_lane = diverge["scenarios"]["BULL"]
        countervailing_axes = {c["axis"] for c in bull_lane["countervailing_evidence"]}
        self.assertIn("ORDER_IMBALANCE", countervailing_axes)
        self.assertLess(len(bull_lane["confirming_conditions"]), 3)  # not all three axes are bullish

        self.assertNotEqual(diverge["scenario_content_identity"], bull["scenario_content_identity"])
        self.assertNotEqual(
            tuple(diverge["evidence_axes"][a]["direction"] for a in ("trend", "proprietary_flow", "order_imbalance")),
            tuple(bull["evidence_axes"][a]["direction"] for a in ("trend", "proprietary_flow", "order_imbalance")),
        )

    # -- Missing foreign-room evidence becomes an explicit DATA_WARNING, never a fabricated fact. ----
    def test_missing_foreign_room_becomes_data_warning_not_fabricated_fact(self) -> None:
        artifact = self._build()
        sym = self._by_ticker(artifact)["SYM_MISSING_FOREIGN"]

        fr_axis = sym["evidence_axes"][AXIS_FOREIGN_ROOM]
        self.assertEqual(fr_axis["classification"], DATA_WARNING)
        self.assertEqual(fr_axis["constraint"], "UNKNOWN")  # never fabricated as BULL_LIMITING/NONE when the capability itself is missing

        gap_refs = [w["evidence_reference"] for w in sym["warnings_and_data_gaps"]]
        self.assertIn("cross_dimension_cases[ticker=SYM_MISSING_FOREIGN].foreign_room", gap_refs)
        self.assertIn("cross_dimension_cases[ticker=SYM_MISSING_FOREIGN].missing_or_failed_capabilities.FOREIGN_ROOM", gap_refs)

        # FOREIGN_ROOM is never a directional axis, so it must never appear as confirming/countervailing
        # evidence in any lane -- missing evidence cannot silently become a directional signal.
        for lane in sym["scenarios"].values():
            for bucket in ("confirming_conditions", "countervailing_evidence"):
                self.assertFalse(any(item.get("axis") == "FOREIGN_ROOM" for item in lane[bucket]))
        # And BASE must not promote the missing axis into a FACT.
        self.assertFalse(any(item.get("axis") == "FOREIGN_ROOM" for item in sym["scenarios"]["BASE"]["confirming_conditions"]))

    # -- Dominant put-through becomes a DATA_WARNING caveat, distinct from a directional read. -------
    def test_put_through_dominance_becomes_data_warning(self) -> None:
        artifact = self._build()
        sym = self._by_ticker(artifact)["SYM_PUT_THROUGH_DOMINANT"]
        pt_axis = sym["evidence_axes"]["put_through_composition"]
        self.assertEqual(pt_axis["classification"], DATA_WARNING)
        self.assertEqual(pt_axis["severity"], "DOMINANT")
        self.assertTrue(any("put-through" in w["claim"] for w in sym["warnings_and_data_gaps"]))

    # -- Foreign-room saturation limits BULL even though all three directional axes read bullish. ----
    def test_foreign_room_saturation_limits_bull_even_with_bullish_directional_axes(self) -> None:
        artifact = self._build()
        sym = self._by_ticker(artifact)["SYM_FOREIGN_SATURATED"]
        bull = sym["scenarios"]["BULL"]
        self.assertEqual(len(bull["confirming_conditions"]), 3)
        foreign_items = [c for c in bull["countervailing_evidence"] if c["axis"] == "FOREIGN_ROOM"]
        self.assertEqual(len(foreign_items), 1)
        self.assertEqual(foreign_items[0]["classification"], FACT)

    # -- Determinism: replaying the same input twice yields identical content identities. ------------
    def test_deterministic_content_identity_across_repeated_runs(self) -> None:
        first = self._build()
        second = self._build()
        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(first["artifact_identity"], second["artifact_identity"])
        first_ids = sorted(s["scenario_content_identity"] for s in first["scenarios"])
        second_ids = sorted(s["scenario_content_identity"] for s in second["scenarios"])
        self.assertEqual(first_ids, second_ids)

    # -- Fail-closed identity checks. -------------------------------------------------------------
    def test_fails_closed_on_tampered_digest_sha256(self) -> None:
        tampered = copy.deepcopy(self.digest)
        tampered["digest_sha256"] = "0" * 64
        with self.assertRaises(DigestIdentityError):
            validate_digest_identity(tampered)
        with self.assertRaises(DigestIdentityError):
            build_capability_first_scenario_distribution(tampered)

    def test_fails_closed_on_missing_required_key(self) -> None:
        broken = copy.deepcopy(self.digest)
        del broken["coverage_and_data_quality"]
        with self.assertRaises(DigestIdentityError):
            validate_digest_identity(broken)

    def test_fails_closed_on_universe_denominator_mismatch(self) -> None:
        raw = _raw_digest()
        raw["cross_dimension_cases"]["universe_denominator"] = 999
        mismatched = _finalize(raw)
        with self.assertRaisesRegex(DigestIdentityError, "universe_denominator"):
            build_capability_first_scenario_distribution(mismatched)

    def test_fails_closed_on_sample_denominator_reconciliation_mismatch(self) -> None:
        raw = _raw_digest()
        raw["cross_dimension_cases"]["sample_denominator"] = 999
        mismatched = _finalize(raw)
        with self.assertRaisesRegex(DigestIdentityError, "sample_denominator"):
            build_capability_first_scenario_distribution(mismatched)

    def test_fails_closed_on_case_bucket_record_mismatch_for_same_ticker(self) -> None:
        conflicting_bull = {**SYM_BULL, "price_and_trend": {**SYM_BULL["price_and_trend"], "return_1d": 0.99}}
        raw = _raw_digest(cases_by_ticker={
            "mock_case_alpha": [SYM_BULL],
            "mock_case_beta": [conflicting_bull],
        }, fully_enriched_count=1, partially_enriched_count=0)
        digest = _finalize(raw)
        with self.assertRaises(DigestIdentityError):
            build_capability_first_scenario_distribution(digest)

    # -- No probability, target-price, recommendation, or expected-return language anywhere. ---------
    def test_forbidden_language_absent_from_all_authored_strings(self) -> None:
        artifact = self._build()
        forbidden = (
            "target price", "price target", "recommend", "buy rating", "sell rating", "buy signal",
            "sell signal", "expected return", "overweight", "underweight", "outperform", "underperform",
            "top pick", "chance of", "likely to",
        )
        for s in _walk_strings(artifact):
            low = s.lower()
            for token in forbidden:
                self.assertNotIn(token, low, f"forbidden language {token!r} found in: {s!r}")

    # -- Every authored item carries exactly one of the four allowed classifications, and no lane
    #    ever asserts a numeric probability/confidence value. -----------------------------------------
    def test_classification_values_are_always_one_of_the_four_allowed(self) -> None:
        artifact = self._build()
        for sym in artifact["scenarios"]:
            self.assertEqual(sym["probability_status"], "UNQUALIFIED")
            for lane in sym["scenarios"].values():
                for bucket in ("confirming_conditions", "countervailing_evidence", "invalidating_conditions"):
                    for item in lane[bucket]:
                        self.assertIn(item["classification"], CLASSIFICATIONS)
            for w in sym["warnings_and_data_gaps"]:
                self.assertIn(w["classification"], CLASSIFICATIONS)
            for c in sym["cohort_context"]:
                self.assertIn(c["classification"], CLASSIFICATIONS)
            self.assertIn(sym["market_context"]["classification"], CLASSIFICATIONS)

    # -- Evidence-depth assessment: a genuinely varied cohort is SUFFICIENT; a degenerate one is not. -
    def test_evidence_depth_sufficient_for_genuinely_differentiated_cohort(self) -> None:
        artifact = self._build()
        self.assertEqual(artifact["evidence_depth_assessment"]["verdict"], "SUFFICIENT")

    def test_evidence_depth_insufficient_for_zero_surfaced_tickers(self) -> None:
        raw = _raw_digest(cases_by_ticker={"mock_case_alpha": []}, fully_enriched_count=0, partially_enriched_count=0)
        digest = _finalize(raw)
        artifact = build_capability_first_scenario_distribution(digest)
        self.assertEqual(artifact["evidence_depth_assessment"]["verdict"], "INSUFFICIENT")
        self.assertEqual(artifact["cohort_reconciliation"]["scenario_produced_count"], 0)

    def test_evidence_depth_insufficient_for_identical_axis_signatures(self) -> None:
        twin_a = _member("TWIN_A", above_ma20=True, ret=0.02, net_value=1.0, buy_vol=1.0, sell_vol=0.0, buy_skew=True, imbalance_ratio=0.1)
        twin_b = _member("TWIN_B", above_ma20=True, ret=0.02, net_value=1.0, buy_vol=1.0, sell_vol=0.0, buy_skew=True, imbalance_ratio=0.1)
        raw = _raw_digest(cases_by_ticker={"mock_case_alpha": [twin_a, twin_b]}, fully_enriched_count=2, partially_enriched_count=0)
        digest = _finalize(raw)
        artifact = build_capability_first_scenario_distribution(digest)
        self.assertEqual(artifact["evidence_depth_assessment"]["verdict"], "INSUFFICIENT")

    # -- Multi-bucket membership is preserved as lineage, not lost or duplicated. ---------------------
    def test_multi_case_bucket_membership_recorded_in_lineage(self) -> None:
        raw = _raw_digest(cases_by_ticker={
            "mock_case_alpha": [SYM_BULL],
            "mock_case_beta": [SYM_BULL],
        }, fully_enriched_count=1, partially_enriched_count=0)
        digest = _finalize(raw)
        artifact = build_capability_first_scenario_distribution(digest)
        self.assertEqual(len(artifact["scenarios"]), 1)
        sym = artifact["scenarios"][0]
        self.assertEqual(sym["lineage"]["matched_cross_dimension_case_types"], ["mock_case_alpha", "mock_case_beta"])

    # -- Cohort context uses cohort_profiles for real comparative facts, not a generic template. ------
    def test_cohort_context_uses_cohort_profiles_for_real_comparison(self) -> None:
        artifact = self._build()
        sym = self._by_ticker(artifact)["SYM_BULL"]
        self.assertEqual(len(sym["cohort_context"]), 1)
        ctx = sym["cohort_context"][0]
        self.assertEqual(ctx["cohort"], "MOMENTUM_PARTICIPATION")
        self.assertIn("+5.00%", ctx["claim"])  # SYM_BULL's own return_1d, not a generic template
        self.assertIn("MOMENTUM_PARTICIPATION", ctx["claim"])
        self.assertIn("cohort median", ctx["claim"])

    def test_py_compile_smoke(self) -> None:
        import py_compile
        import tools.derive_capability_first_scenario_distribution as mod
        py_compile.compile(mod.__file__, doraise=True)


if __name__ == "__main__":
    unittest.main()
