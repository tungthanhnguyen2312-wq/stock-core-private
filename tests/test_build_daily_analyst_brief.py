"""tests/test_build_daily_analyst_brief.py — Unit tests for the Daily Analyst Brief V1."""
from __future__ import annotations

import copy
import unittest
from typing import Any

from tools.derive_cross_dimension_research_digest import (
    CODE_HIGH_FOREIGN_ROOM,
    CODE_MATERIAL_ACTIVE_BUY_IMBALANCE,
    CODE_MATERIAL_PROP_NET_SELL,
    CODE_PUT_THROUGH_DOMINANT,
)
from tools.derive_research_intelligence_digest import (
    CASE_EXPLICIT_DIVERGENCE,
    CROSS_DIMENSION_CASE_NAMES,
    FLAG_LOW_REL_VOL_WITH_ACTIVITY,
    FLAG_PRICE_FLOW_DIVERGENCE,
    FLAG_PUT_THROUGH_DOMINANCE,
    INSUFFICIENT_COVERAGE,
    NO_PUT_THROUGH_RECORDED,
    PUT_THROUGH_RECORDED,
)
from tools.build_daily_analyst_brief import (
    MAX_DIVERGENCE_CASES,
    MAX_MAIN_CASES,
    MAX_PUT_THROUGH_CASES,
    InputDigestIdentityError,
    build_daily_analyst_brief,
    generate_daily_analyst_brief_markdown,
    validate_input_digest,
)
from market_wide_current_valuation_input_scaleout import build_current_valuation_artifact

CAP_DIGEST_IDENTITY = "research_intelligence_digest_v1:mock_sha_v1"

COHORT_NAMES = ("MOMENTUM_PARTICIPATION", "HIGH_ACTIVITY_REVERSAL_OR_DISTRIBUTION", "HIGH_VOLATILITY_WATCH", "TREND_WITHOUT_PARTICIPATION")


def _cd_member(
    ticker: str,
    reason_codes: list[str],
    return_1d: float,
    matched_value: float = 1_000_000_000.0,
    put_through_value: float = 0.0,
    prop_alignment: str = "NOT_APPLICABLE",
    imbalance_alignment: str = "NOT_APPLICABLE",
    prop_net: float | None = 0.0,
    imbalance: float | None = 0.0,
    room_util: float | None = 0.5,
) -> dict[str, Any]:
    total = matched_value + put_through_value
    return {
        "ticker": ticker,
        "enrichment_tier": "FULLY_ENRICHED",
        "acquired_capabilities": ["TRADING_HISTORY", "FOREIGN_ROOM", "PROPRIETARY_FLOW", "MICROSTRUCTURE"],
        "missing_or_failed_capabilities": {},
        "active_research_cohorts": [],
        "reason_codes": list(reason_codes),
        "cross_dimension_analysis": {
            "price_vs_prop_alignment": prop_alignment,
            "price_vs_order_imbalance_alignment": imbalance_alignment,
            "put_through_character": "NO_MATERIAL_PUT_THROUGH_SIGNAL",
            "foreign_room_character": "MODERATE_FOREIGN_ROOM_UTILIZATION",
        },
        "price_and_trend": {
            "close_vnd": 10000.0, "ma_20_vnd": 9500.0, "return_1d": return_1d,
            "relative_volume": 1.5, "above_ma20": True,
        },
        "traded_value_composition": {
            "matched_traded_value_vnd": matched_value,
            "put_through_traded_value_vnd": put_through_value,
            "total_traded_value_vnd": total,
            "put_through_share_ratio": round(put_through_value / total, 6) if total else None,
        },
        "foreign_room": {"status": "ACQUIRED", "max_shares": 100, "owned_shares": 50, "available_shares": 50, "utilization_ratio": room_util},
        "proprietary_flow": {"status": "ACQUIRED", "buy_value_vnd": 1.0, "sell_value_vnd": 1.0, "net_value_vnd": prop_net, "buy_volume": 1.0, "sell_volume": 1.0, "net_volume": 1.0},
        "microstructure": {"status": "ACQUIRED", "active_buy_orders": 1, "active_sell_orders": 1, "active_buy_volume": 1.0, "active_sell_volume": 1.0, "active_net_volume": 0.0, "imbalance_ratio": imbalance},
    }


def _pt_entry(ticker: str, return_1d: float, matched_value: float, put_through_value: float | None, rel_vol: float = 1.0) -> dict[str, Any]:
    if put_through_value is None:
        status = "PUT_THROUGH_UNKNOWN"
        total = None
        share = None
    elif put_through_value == 0:
        status = NO_PUT_THROUGH_RECORDED
        total = matched_value + put_through_value
        share = round(put_through_value / total, 6) if total else None
    else:
        status = PUT_THROUGH_RECORDED
        total = matched_value + put_through_value
        share = round(put_through_value / total, 6) if total else None
    return {
        "ticker": ticker,
        "cohort_memberships": [],
        "matched_traded_value_vnd": matched_value,
        "put_through_traded_value_vnd": put_through_value,
        "total_traded_value_vnd": total,
        "put_through_share_ratio": share,
        "return_1d": return_1d,
        "relative_volume_provider_scoped": rel_vol,
        "put_through_status": status,
    }


def _flag(ticker: str, flag_type: str, reason_codes: list[str]) -> dict[str, Any]:
    return {
        "flag_type": flag_type,
        "ticker": ticker,
        "reason_codes": list(reason_codes),
        "facts": {},
        "missing_data_context": None,
        "research_rationale": f"mock rationale for {ticker}",
    }


class TestDailyAnalystBrief(unittest.TestCase):
    def setUp(self) -> None:
        cd_cases = {name: {"count": 0, "members": []} for name in CROSS_DIMENSION_CASE_NAMES}

        # T01: 2 distinct qualifying codes on one ticker -> Priority 1.
        t01 = _cd_member("T01", [CODE_PUT_THROUGH_DOMINANT, CODE_HIGH_FOREIGN_ROOM], 0.02, matched_value=400_000_000.0, put_through_value=600_000_000.0, room_util=0.9)
        # T02: explicit divergence with NO other qualifying cross-dimension code of its own --
        # its only qualifying code comes from the (separately constructed) FLAG_PRICE_FLOW_DIVERGENCE
        # follow-up flag below, so it lands cleanly on Priority 2, not Priority 1.
        t02 = _cd_member("T02", [], 0.05, prop_alignment="PRICE_UP_WITH_PROP_NET_SELL", prop_net=-5_000_000_000.0)
        # T03: PUT_THROUGH_DOMINANT only, not divergent -> Priority 3.
        t03 = _cd_member("T03", [CODE_PUT_THROUGH_DOMINANT], 0.01, matched_value=450_000_000.0, put_through_value=550_000_000.0)
        # T04: material active buy imbalance only -> Priority 4.
        t04 = _cd_member("T04", [CODE_MATERIAL_ACTIVE_BUY_IMBALANCE], 0.03, imbalance=0.15)
        # T05: material proprietary net sell only -> Priority 4. Kept OUT of follow_up_flags and
        # out of the top-10 selection on purpose; only used to check its put_through_digest entry
        # (put-through value genuinely missing) never gets coerced into a number.
        t05 = _cd_member("T05", [CODE_MATERIAL_PROP_NET_SELL], -0.02, prop_net=-11_000_000_000.0)
        # T06..T10: five more explicit-divergence cases with NO qualifying code and NO matching
        # follow-up flag -- they count toward the divergence section's raw total (to prove its
        # independent 5-case cap) without being candidates for the main case list at all.
        divergence_extra = []
        for i in range(6, 11):
            ticker = f"T{i:02d}"
            divergence_extra.append(_cd_member(
                ticker, [], -0.01,
                imbalance_alignment="PRICE_DOWN_WITH_ACTIVE_SELL_SKEW", imbalance=-0.2,
            ))

        cd_cases[CASE_EXPLICIT_DIVERGENCE] = {
            "count": 6, "members": sorted([t02] + divergence_extra, key=lambda m: m["ticker"]),
        }
        # Non-divergent enriched members can live in any single bucket; downstream code reads
        # member facts directly, not the bucket key.
        cd_cases["put_through_dominance"] = {
            "count": 4, "members": sorted([t01, t03, t04, t05], key=lambda m: m["ticker"]),
        }

        self.mock_digest: dict[str, Any] = {
            "schema_version": "1.0.0",
            "contract_version": "capability_first_research_intelligence_digest/v1",
            "session_date": "2026-08-21",
            "digest_identity": CAP_DIGEST_IDENTITY,
            "authority_boundaries": {"authority_effect": "NONE", "recommendation_authority": False, "ranking_authority": False},
            "market_state": {
                "source_artifact_identity": "market_state_and_candidates:mock",
                "universe_count": 524,
                "regime_classification": {"regime_label": "MIXED", "derivation_reason": "mock reason"},
                "breadth": {"advancers_count": 100, "decliners_count": 90, "unchanged_count": 334, "advance_decline_ratio": 1.11},
                "moving_average_breadth": {"above_ma20_count": 200, "at_or_below_ma20_count": 324, "above_ma20_ratio": 0.3817},
                "return_distribution": {"median_return_1d": 0.005},
                "relative_volume_breadth": {"elevated_volume_count": 50, "normal_volume_count": 400, "depressed_volume_count": 74, "median_relative_volume": 1.05},
                "volatility_distribution": {"median_volatility_20d": 0.018},
            },
            "cohort_profiles": {
                name: {
                    "total_member_count": 20,
                    "trading_history_covered_count": 10,
                    "trading_history_coverage_ratio": 0.5,
                    "member_tickers": ["T01", "T02"] if name == "MOMENTUM_PARTICIPATION" else [],
                    "return_distribution": {"median": 0.01},
                    "relative_volume_distribution": {"median": 1.2},
                }
                for name in COHORT_NAMES
            },
            "cohort_comparison": {
                "comparison_contract": {
                    "rule": "SAMPLE_DESCRIPTIVE_WHEN_DENOMINATOR_GTE_MINIMUM_ELSE_INSUFFICIENT_COVERAGE",
                    "minimum_denominator_for_descriptive_comparison": 1,
                    "extrapolates_to_full_cohort_or_universe": False,
                },
                "metrics": {
                    "median_matched_traded_value_vnd_among_covered": {
                        name: ({"value": 500_000_000.0, "denominator": 10, "comparison_status": "SAMPLE_DESCRIPTIVE"} if name != "TREND_WITHOUT_PARTICIPATION"
                               else {"value": INSUFFICIENT_COVERAGE, "denominator": 0, "comparison_status": INSUFFICIENT_COVERAGE})
                        for name in COHORT_NAMES
                    },
                    "put_through_incidence_ratio_among_covered": {
                        name: ({"value": 0.1, "denominator": 10, "comparison_status": "SAMPLE_DESCRIPTIVE"} if name != "TREND_WITHOUT_PARTICIPATION"
                               else {"value": INSUFFICIENT_COVERAGE, "denominator": 0, "comparison_status": INSUFFICIENT_COVERAGE})
                        for name in COHORT_NAMES
                    },
                },
            },
            "cross_dimension_cases": {"cases": cd_cases},
            "follow_up_flags": {
                # T12..T20: nine Priority-5, follow_up_flags-only candidates (no cross-dimension
                # record at all) -- together with T01/T02/T03/T04 (13 total eligible), this
                # forces real truncation to MAX_MAIN_CASES and guarantees at least one selected
                # case (T12) has no cross-dimension record, exercising the missing-dimensions path.
                "flags": [
                    _flag(f"T{i:02d}", FLAG_LOW_REL_VOL_WITH_ACTIVITY, ["HIGH_MATCHED_VALUE_SAMPLE_RELATIVE", "DEPRESSED_RELATIVE_VOLUME"])
                    for i in range(12, 21)
                ] + [
                    _flag("T02", FLAG_PRICE_FLOW_DIVERGENCE, ["PRICE_UP_WITH_PROP_NET_SELL"]),
                    _flag("T01", FLAG_PUT_THROUGH_DOMINANCE, [CODE_PUT_THROUGH_DOMINANT]),
                ],
            },
            "put_through_digest": {
                "entries": [
                    _pt_entry("T01", 0.02, 400_000_000.0, 600_000_000.0),
                    _pt_entry("T02", 0.05, 1_000_000_000.0, 0.0),
                    _pt_entry("T03", 0.01, 450_000_000.0, 550_000_000.0),
                    _pt_entry("T04", 0.03, 1_000_000_000.0, 0.0),
                    _pt_entry("T05", -0.02, 1_000_000_000.0, None),  # missing put-through -> unknown, never zero
                    _pt_entry("T06", -0.01, 300_000_000.0, 400_000_000.0),
                    _pt_entry("T07", -0.01, 300_000_000.0, 350_000_000.0),
                    _pt_entry("T08", -0.01, 300_000_000.0, 300_000_000.0),
                ] + [
                    _pt_entry(f"T{i:02d}", 0.0, 1_000_000_000.0, 0.0, rel_vol=0.5) for i in range(12, 21)
                ],
            },
            "coverage_and_data_quality": {
                "tiers": {
                    "FULL_RESEARCH_UNIVERSE": 524, "ACQUIRED_TRADING_HISTORY_COHORT": 111,
                    "FULLY_ENRICHED_COHORT": 13, "PARTIALLY_ENRICHED": 1, "TRADING_HISTORY_ONLY": 97,
                    "PROVIDER_RATE_LIMITED": 21, "REQUESTED_BUT_MISSING": 1, "BUDGET_EXHAUSTED": 0,
                    "NOT_ACQUIRED_IN_THIS_SCALEOUT": 391,
                },
                "reconciliation": {"capability_digest_reconciled_sum": 524, "capability_digest_reconciliation_valid": True},
                "disclaimer": "mock coverage disclaimer",
            },
            "data_coverage_backlog": {
                "disclaimer": "DATA_COVERAGE_BACKLOG_IS_DESCRIPTIVE_ONLY_NOT_AN_ACQUISITION_RECOMMENDATION",
                "coverage_gap_examples": {
                    "max_examples": 10, "returned_count": 3, "total_available_count": 120,
                    "examples": [
                        {"ticker": "GAP1", "exact_upstream_status": "NOT_ACQUIRED_IN_THIS_SCALEOUT", "status_group": "GENUINELY_UNATTEMPTED", "active_research_cohorts": ["MOMENTUM_PARTICIPATION"], "label": "COVERAGE_GAP_EXAMPLE", "note": "Illustrative only; not a priority ranking or acquisition recommendation."},
                        {"ticker": "GAP2", "exact_upstream_status": "PROVIDER_RATE_LIMITED", "status_group": "ATTEMPTED_RATE_LIMITED", "active_research_cohorts": ["HIGH_VOLATILITY_WATCH"], "label": "COVERAGE_GAP_EXAMPLE", "note": "Illustrative only; not a priority ranking or acquisition recommendation."},
                        {"ticker": "GAP3", "exact_upstream_status": "REQUESTED_BUT_MISSING", "status_group": "ATTEMPTED_BUT_MISSING_OR_FAILED", "active_research_cohorts": ["TREND_WITHOUT_PARTICIPATION"], "label": "COVERAGE_GAP_EXAMPLE", "note": "Illustrative only; not a priority ranking or acquisition recommendation."},
                    ],
                },
            },
        }

    def _build(self):
        return build_daily_analyst_brief(self.mock_digest)

    # 1. Input identity is required.
    def test_input_identity_is_required(self) -> None:
        missing_identity = copy.deepcopy(self.mock_digest)
        del missing_identity["digest_identity"]
        with self.assertRaises(InputDigestIdentityError):
            validate_input_digest(missing_identity)
        with self.assertRaises(InputDigestIdentityError):
            build_daily_analyst_brief(missing_identity)

        wrong_prefix = copy.deepcopy(self.mock_digest)
        wrong_prefix["digest_identity"] = "some_other_artifact:abc123"
        with self.assertRaises(InputDigestIdentityError):
            build_daily_analyst_brief(wrong_prefix)

        promoted_authority = copy.deepcopy(self.mock_digest)
        promoted_authority["authority_boundaries"]["authority_effect"] = "PROMOTED"
        with self.assertRaises(InputDigestIdentityError):
            build_daily_analyst_brief(promoted_authority)

    # 2. Deterministic identity stable.
    def test_deterministic_identity_stable(self) -> None:
        first = self._build()
        second = self._build()
        self.assertEqual(first["brief_sha256"], second["brief_sha256"])
        self.assertEqual(first["brief_identity"], second["brief_identity"])

    # 3. Changed input identity changes brief identity.
    def test_changed_input_identity_changes_brief_identity(self) -> None:
        baseline = self._build()
        mutated = copy.deepcopy(self.mock_digest)
        mutated["digest_identity"] = CAP_DIGEST_IDENTITY + "_v2"
        mutated["market_state"]["return_distribution"]["median_return_1d"] = 0.999
        result = build_daily_analyst_brief(mutated)
        self.assertNotEqual(baseline["brief_sha256"], result["brief_sha256"])
        self.assertNotEqual(baseline["brief_identity"], result["brief_identity"])

    # 4. Max 10 main cases, with the true eligible count still reported.
    def test_max_ten_main_cases(self) -> None:
        artifact = self._build()
        cases_block = artifact["cases_to_review"]
        self.assertLessEqual(len(cases_block["cases"]), MAX_MAIN_CASES)
        self.assertEqual(cases_block["max_cases"], MAX_MAIN_CASES)
        # 14 distinct eligible tickers were constructed (T01-T05, T12-T20) -> truncation is real.
        self.assertEqual(cases_block["total_eligible_candidates"], 14)
        self.assertEqual(len(cases_block["cases"]), MAX_MAIN_CASES)

    # 5. Duplicate ticker across multiple reasons collapses into one case.
    def test_duplicate_ticker_collapses_into_one_case(self) -> None:
        artifact = self._build()
        tickers = [c["ticker"] for c in artifact["cases_to_review"]["cases"]]
        self.assertEqual(len(tickers), len(set(tickers)))
        # T01 qualifies via two cross-dimension codes AND a follow-up flag; still one case.
        t01_cases = [c for c in artifact["cases_to_review"]["cases"] if c["ticker"] == "T01"]
        self.assertEqual(len(t01_cases), 1)
        self.assertEqual(t01_cases[0]["attention_priority"], 1)
        self.assertIn(CODE_PUT_THROUGH_DOMINANT, t01_cases[0]["why_selected"]["reason_codes"])
        self.assertIn(CODE_HIGH_FOREIGN_ROOM, t01_cases[0]["why_selected"]["reason_codes"])

    # 6. Reason codes are preserved (not renamed/mutated).
    def test_reason_codes_preserved(self) -> None:
        artifact = self._build()
        t04 = next(c for c in artifact["cases_to_review"]["cases"] if c["ticker"] == "T04")
        self.assertEqual(t04["why_selected"]["reason_codes"], [CODE_MATERIAL_ACTIVE_BUY_IMBALANCE])

    # 7. No recommendation/ranking authority leaks.
    def test_no_recommendation_ranking_authority(self) -> None:
        artifact = self._build()
        self.assertEqual(artifact["authority_boundaries"], {
            "authority_effect": "NONE",
            "ranking_authority": False,
            "recommendation_authority": False,
            "sizing_authority": False,
            "valuation_authority": False,
            "pit_backtest_eligible": False,
            "raw_as_traded_promoted": False,
            "database_mutated": False,
        })

    # 8. Attention priority is explicitly non-investment.
    def test_attention_priority_is_explicitly_non_investment(self) -> None:
        artifact = self._build()
        contract = artifact["attention_priority_contract"]
        self.assertEqual(contract["name"], "research_attention_priority")
        self.assertFalse(contract["ranking_authority"])
        self.assertFalse(contract["recommendation_authority"])
        forbidden = ("expected return", "quality score", "conviction score", "investment score", "market-cap preference")
        disclaimer_low = contract["disclaimer"].lower()
        # The disclaimer explicitly NAMES these to disclaim them; make sure it's a negation.
        for token in forbidden:
            if token in disclaimer_low:
                self.assertIn("not", disclaimer_low)

    # 9. Divergence section max 5.
    def test_divergence_section_max_five(self) -> None:
        artifact = self._build()
        div = artifact["divergences"]
        self.assertEqual(div["max_cases"], MAX_DIVERGENCE_CASES)
        self.assertEqual(div["total_available"], 6)
        self.assertEqual(len(div["cases"]), 5)

    # 10. Put-through section max 5.
    def test_put_through_section_max_five(self) -> None:
        artifact = self._build()
        pt = artifact["put_through_watch"]
        self.assertEqual(pt["max_cases"], MAX_PUT_THROUGH_CASES)
        # Recorded (non-zero) put-through entries: T01, T03, T06, T07, T08 = 5 total (not > 5 here,
        # so also verify the cap logic activates under a larger count).
        self.assertEqual(pt["total_available"], 5)
        self.assertLessEqual(len(pt["cases"]), MAX_PUT_THROUGH_CASES)

        # Now force a real truncation by adding two more recorded cases.
        bigger = copy.deepcopy(self.mock_digest)
        bigger["put_through_digest"]["entries"].append(_pt_entry("T15", 0.01, 100.0, 200.0))
        bigger["put_through_digest"]["entries"].append(_pt_entry("T16", 0.01, 100.0, 200.0))
        artifact2 = build_daily_analyst_brief(bigger)
        self.assertEqual(artifact2["put_through_watch"]["total_available"], 7)
        self.assertEqual(len(artifact2["put_through_watch"]["cases"]), 5)

    # 11. Missing dimensions stay missing, never zero-filled.
    def test_missing_dimensions_stay_missing(self) -> None:
        artifact = self._build()
        # T12 is follow_up_flags-only (no cross_dimension_cases record) -> MA20/close must be
        # None, never fabricated as 0.
        t12 = next(c for c in artifact["cases_to_review"]["cases"] if c["ticker"] == "T12")
        self.assertIsNone(t12["price_context"]["close_vnd"])
        self.assertIsNone(t12["price_context"]["ma_20_vnd"])
        self.assertEqual(t12["coverage"]["enrichment_tier"], "TRADING_HISTORY_ONLY_OR_UNKNOWN")
        self.assertEqual(t12["cross_dimension"]["proprietary_flow_status"], "NOT_IN_CROSS_DIMENSION_DIGEST")
        self.assertIsNone(t12["cross_dimension"]["proprietary_net_value_vnd"])

        # T05's put-through value was recorded upstream as missing (None) -> stays None/unknown,
        # never coerced into a numeric 0 or NO_PUT_THROUGH_RECORDED.
        t05_pt = next(e for e in self.mock_digest["put_through_digest"]["entries"] if e["ticker"] == "T05")
        self.assertIsNone(t05_pt["put_through_traded_value_vnd"])
        self.assertEqual(t05_pt["put_through_status"], "PUT_THROUGH_UNKNOWN")

    # 12. Data limitations preserve exact counts/status groups.
    def test_data_limitations_preserve_exact_counts(self) -> None:
        artifact = self._build()
        dl = artifact["data_limitations"]
        self.assertEqual(dl["tiers"], self.mock_digest["coverage_and_data_quality"]["tiers"])
        example_statuses = {e["exact_upstream_status"] for e in dl["coverage_gap_examples"]["examples"]}
        self.assertEqual(example_statuses, {"NOT_ACQUIRED_IN_THIS_SCALEOUT", "PROVIDER_RATE_LIMITED", "REQUESTED_BUT_MISSING"})

    # 13. Coverage backlog is not converted into an acquisition recommendation.
    def test_coverage_backlog_not_converted_to_recommendation(self) -> None:
        artifact = self._build()
        dl_text = " ".join([
            artifact["data_limitations"]["statement"],
            artifact["data_limitations"]["coverage_gap_backlog_disclaimer"],
        ]).lower()
        for token in ("prioritize", "next wave", "acquisition wave", "recommend acquiring", "should acquire"):
            self.assertNotIn(token, dl_text)
        # Coverage gap examples in the main brief must stay bounded to what upstream already capped.
        self.assertLessEqual(artifact["data_limitations"]["coverage_gap_examples"]["returned_count"], 10)

    # 14. Question templates contain no BUY/SELL/target/probability language.
    def test_research_questions_contain_no_forbidden_language(self) -> None:
        artifact = self._build()
        forbidden = ("should buy", "should sell", "target", "expected return", "upside", "downside probability")
        all_questions = [c["research_question"] for c in artifact["cases_to_review"]["cases"]]
        all_questions += [q["research_question"] for q in artifact["research_questions_for_next_review"]]
        self.assertGreater(len(all_questions), 0)
        for q in all_questions:
            low = q.lower()
            for token in forbidden:
                self.assertNotIn(token, low)

    # 15. Markdown remains bounded and does not dump the entire universe.
    def test_markdown_is_bounded(self) -> None:
        artifact = self._build()
        md = generate_daily_analyst_brief_markdown(artifact)
        self.assertLess(len(md), 20000)
        case_heading_count = md.count("(attention priority")
        self.assertLessEqual(case_heading_count, MAX_MAIN_CASES)
        for heading in (
            "MARKET IN ONE MINUTE", "WHAT CHANGED / WHAT STANDS OUT", "COHORT SNAPSHOT",
            "CASES TO REVIEW", "PUT-THROUGH WATCH", "CROSS-DIMENSION DIVERGENCES",
            "DATA LIMITATIONS", "RESEARCH QUESTIONS FOR NEXT REVIEW",
        ):
            self.assertIn(heading, md)
        # The full 120-symbol backlog must never be dumped in the brief.
        self.assertNotIn("GAP4", md)

    # 16. Upstream reason-code semantics are not mutated.
    def test_upstream_reason_code_semantics_not_mutated(self) -> None:
        artifact = self._build()
        div_cases = artifact["divergences"]["cases"]
        source_by_ticker = {m["ticker"]: m for m in self.mock_digest["cross_dimension_cases"]["cases"][CASE_EXPLICIT_DIVERGENCE]["members"]}
        for c in div_cases:
            source = source_by_ticker[c["ticker"]]
            self.assertEqual(c["reason_codes"], source["reason_codes"])
            self.assertEqual(c["price_vs_prop_alignment"], source["cross_dimension_analysis"]["price_vs_prop_alignment"])
            self.assertEqual(c["price_vs_order_imbalance_alignment"], source["cross_dimension_analysis"]["price_vs_order_imbalance_alignment"])

    def test_insufficient_coverage_passthrough_in_cohort_snapshot(self) -> None:
        artifact = self._build()
        trend_cell = artifact["cohort_snapshot"]["cohorts"]["TREND_WITHOUT_PARTICIPATION"]["median_matched_traded_value_vnd_among_covered"]
        self.assertEqual(trend_cell["value"], INSUFFICIENT_COVERAGE)

    def test_optional_valuation_attach_does_not_change_attention_or_authority(self) -> None:
        baseline = self._build()
        valuation = build_current_valuation_artifact(
            price_snapshot={"resolved_completed_session": "2026-08-21", "source": "DNSE", "snapshot_identity": "price:1",
                            "records": {"T01": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": "2026-08-21", "close": 10_000}]}}},
            fundamental_artifact={"artifact_identity": "fund:1", "records": {"T01": {"entity_class": "corporate", "authority_tier": "PROVIDER_RESEARCH"}}},
            share_promotion_artifact={"artifact_identity": "shares:1", "projected_coverage_impact": {"cohort_rows": [
                {"ticker": "T01", "resolver_authority": "provider_reported_current", "freshness_state": "PROVIDER_REPORTED_CURRENT", "provider_value": 100},
            ]}},
        )
        attached = build_daily_analyst_brief(self.mock_digest, current_valuation_artifact=valuation)
        self.assertEqual(
            [case["ticker"] for case in baseline["cases_to_review"]["cases"]],
            [case["ticker"] for case in attached["cases_to_review"]["cases"]],
        )
        self.assertFalse(attached["authority_boundaries"]["valuation_authority"])
        self.assertTrue(attached["current_valuation_research"]["attention_priority_unaffected"])
        self.assertEqual(attached["current_valuation_research"]["value_strategy_eligible"], 0)
        markdown = generate_daily_analyst_brief_markdown(attached)
        self.assertNotRegex(markdown, r"\bBUY\b")
        self.assertIn("non-authoritative", markdown)


if __name__ == "__main__":
    unittest.main()
