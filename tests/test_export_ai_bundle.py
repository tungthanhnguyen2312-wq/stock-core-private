# ==========================================================================
# TEST cho P0-1 (vn_indicators.py: is_live/days_stale/rs_rating live-only) và
# P0-2/P0-3 (export_ai_bundle.py: focus_extract + manifest + freshness gate).
# Chạy: `python -m unittest discover tests` hoặc `python -m unittest tests.test_export_ai_bundle`.
#
# Test tích hợp chạy trên DỮ LIỆU THẬT của repo (screen_snapshot_live.csv, vn_stock.db, ta_signals.csv
# ...) — cùng phong cách test_snapshot_rebuild.py, KHÔNG dùng fixture bịa, vì mục tiêu là xác nhận
# pipeline thật hoạt động đúng trên dữ liệu thật. export_ai_bundle.main() được gọi TRỰC TIẾP trong
# tiến trình với OUT_DIR trỏ vào thư mục tạm (mock) — không bao giờ ghi đè focus_extract.json/
# bundle_manifest.json thật của repo, và không copy vn_stock.db (177MB) đi đâu cả.
# ==========================================================================

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _resolve_runtime_root() -> Path:
    candidates = (
        ROOT.parent / "dashboard-runtime",
        ROOT.parent / "VNSTOCK",
        ROOT.parent.parent / "VNSTOCK",
    )
    return next((path.resolve() for path in candidates if path.exists()), candidates[0].resolve())


RUNTIME_ROOT = _resolve_runtime_root()
os.environ["STOCK_LOOKUP_RUNTIME_ROOT"] = str(RUNTIME_ROOT)

import export_ai_bundle as bundle  # noqa: E402

# Mã ĐÃ BIẾT là chết (nến gần nhất 2026-06-11, xa phiên hiện hành hàng chục ngày) — dùng làm
# regression cố định cho bug RS ảo (P0-1): trước khi sửa, mã này từng lọt RS 94-99 lên đầu bảng.
KNOWN_STALE_TICKER = "CH5"

SOURCE_FILES_MUST_NOT_CHANGE = [
    "vn_stock.db", "ta_signals.csv", "analysis_latest.json",
    "financial_snapshot.parquet", "screen_snapshot.csv",
    "screen_snapshot_live.csv", "Focus_Analysis.md",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _runtime_path(name: str) -> Path:
    return RUNTIME_ROOT / name


class RuntimeRootTests(unittest.TestCase):
    def test_runtime_root_defaults_to_legacy_cwd(self):
        with mock.patch.dict(os.environ, {bundle.RUNTIME_ROOT_ENV: ""}, clear=False):
            self.assertEqual(bundle.runtime_path(bundle.DB_PATH), Path(bundle.DB_PATH))

    def test_runtime_root_override_targets_public_runtime(self):
        self.assertEqual(bundle.runtime_path(bundle.DB_PATH), _runtime_path(bundle.DB_PATH))


def run_bundle_main(argv: list[str], out_dir: Path) -> int:
    """Gọi bundle.main() trong tiến trình; CHỈ đổi hướng nơi GHI output (OUT_DIR) sang thư mục
    tạm. Mọi nguồn ĐỌC (DB, CSV, JSON, parquet, Focus_Analysis.md, context package) vẫn là dữ liệu
    thật của repo."""
    with mock.patch.object(bundle, "OUT_DIR", str(out_dir)), \
         mock.patch.object(sys, "argv", ["export_ai_bundle.py", *argv]):
        return bundle.main()


class ScreenSnapshotLiveTests(unittest.TestCase):
    """P0-1: is_live/days_stale + rs_rating chỉ xếp hạng trong mã live."""

    @classmethod
    def setUpClass(cls):
        cls.full = pd.read_csv(_runtime_path("screen_snapshot.csv"), encoding="utf-8-sig")
        cls.live = pd.read_csv(_runtime_path("screen_snapshot_live.csv"), encoding="utf-8-sig")

    def test_live_file_has_only_live_rows_with_zero_days_stale(self):
        self.assertGreater(len(self.live), 0)
        self.assertTrue((self.live["is_live"] == True).all())  # noqa: E712
        self.assertTrue((self.live["days_stale"] == 0).all())

    def test_known_stale_ticker_excluded_from_live_file_but_kept_in_full(self):
        self.assertNotIn(KNOWN_STALE_TICKER, set(self.live["ticker"]),
                         f"{KNOWN_STALE_TICKER} là mã chết — không được lọt vào bản live")
        full_row = self.full[self.full["ticker"] == KNOWN_STALE_TICKER]
        self.assertEqual(len(full_row), 1, "Mã chết vẫn phải còn trong bản đầy đủ (tương thích cũ)")
        self.assertFalse(bool(full_row.iloc[0]["is_live"]))
        self.assertGreater(int(full_row.iloc[0]["days_stale"]), 1)
        self.assertTrue(pd.isna(full_row.iloc[0]["rs_rating"]),
                        "Mã chết không được có rs_rating (bug cũ: RS ảo 94-99 chiếm đầu bảng)")

    def test_full_snapshot_keeps_all_rows_and_gains_new_columns(self):
        self.assertGreaterEqual(len(self.full), len(self.live))
        self.assertTrue({"is_live", "days_stale", "rs_rating"} <= set(self.full.columns))

    def test_focus_tickers_are_all_live_with_a_real_rs_rating(self):
        for tk in bundle.DEFAULT_TICKERS:
            row = self.live[self.live["ticker"] == tk]
            self.assertEqual(len(row), 1, f"{tk} phải có đúng 1 dòng trong screen_snapshot_live.csv")
            self.assertTrue(bool(row.iloc[0]["is_live"]))
            self.assertFalse(pd.isna(row.iloc[0]["rs_rating"]))

    def test_live_count_matches_market_breadth_all_row(self):
        breadth = pd.read_csv(_runtime_path("market_breadth.csv"), encoding="utf-8-sig")
        all_row = breadth[breadth["group"] == "ALL"].iloc[0]
        self.assertEqual(len(self.live), int(all_row["n_symbols"]))


class FreshnessGateLogicTests(unittest.TestCase):
    """P0-3 / Phase 0B.1: check_freshness() session coherence gate tests."""

    def test_bundle_session_2026_07_30_plus_asset_session_2026_07_29_fails_freshness(self):
        categories = {
            "screen_snapshot_live": "2026-07-30",
            "ta_signals": "2026-07-30",
            "analysis_latest": "2026-07-30",
            "focus_analysis": "2026-07-29",
            "context_package": "2026-07-30",
        }
        result = bundle.check_freshness(
            categories, prior_session="2026-07-29", reference_session="2026-07-30"
        )
        self.assertTrue(result["blocked"])
        stale_categories = [s["category"] for s in result["stale"]]
        self.assertIn("focus_analysis", stale_categories)

    def test_matching_2026_07_30_sessions_pass(self):
        categories = {
            "screen_snapshot_live": "2026-07-30",
            "ta_signals": "2026-07-30",
            "analysis_latest": "2026-07-30",
            "focus_analysis": "2026-07-30",
            "context_package": "2026-07-30",
        }
        result = bundle.check_freshness(
            categories, prior_session="2026-07-29", reference_session="2026-07-30"
        )
        self.assertFalse(result["blocked"])
        self.assertEqual(result["stale"], [])

    def test_missing_session_identity_fails_closed(self):
        categories = {
            "screen_snapshot_live": "2026-07-30",
            "context_package": None,
        }
        result = bundle.check_freshness(
            categories, prior_session="2026-07-29", reference_session="2026-07-30"
        )
        self.assertTrue(result["blocked"])
        self.assertIn("context_package", result["unknown"])
        stale_categories = [s["category"] for s in result["stale"]]
        self.assertIn("context_package", stale_categories)

    def test_financial_period_freshness_behavior_unchanged(self):
        categories = {
            "financial_statements": "2026-03-31",
        }
        result = bundle.check_freshness(
            categories,
            prior_session="2026-03-01",
            reference_session="2026-07-30",
            session_scoped_categories={"screen_snapshot_live", "ta_signals", "focus_analysis", "context_package"},
        )
        self.assertFalse(result["blocked"])


class RiskScoreSemanticsTests(unittest.TestCase):
    """Phase 0B.3: analysis_score risk semantic safety contract tests."""

    def test_value_100_is_described_as_maximum_configured_safety_not_maximum_risk(self):
        values = {"score": 50, "fundamental": 60, "technical": 70, "momentum": 80, "liquidity": 90, "macro": 50, "risk": 100}
        session_info = {"session_date": "2026-07-30", "regime": "phòng thủ"}
        contract = bundle.build_analysis_score_contract(values, session_info)
        semantics = contract["risk_semantics"]
        self.assertIsNotNone(semantics)
        self.assertEqual(semantics["polarity"], "higher_is_safer")
        self.assertIn("maximum configured safety", semantics["interpretation"])
        self.assertNotIn("maximum risk", semantics["interpretation"].lower())

    def test_polarity_is_higher_is_safer(self):
        values = {"risk": 80}
        session_info = {"session_date": "2026-07-30", "regime": "phòng thủ"}
        contract = bundle.build_analysis_score_contract(values, session_info)
        self.assertEqual(contract["risk_semantics"]["polarity"], "higher_is_safer")

    def test_actionability_is_false(self):
        values = {"risk": 100}
        session_info = {"session_date": "2026-07-30", "regime": "phòng thủ"}
        contract = bundle.build_analysis_score_contract(values, session_info)
        self.assertFalse(contract["risk_semantics"]["is_actionable"])

    def test_missing_input_does_not_become_100(self):
        session_info = {"session_date": "2026-07-30", "regime": "phòng thủ"}
        contract = bundle.build_analysis_score_contract(None, session_info)
        self.assertIsNone(contract["values"])
        self.assertIsNone(contract["risk_semantics"])

    def test_unrelated_analysis_score_fields_remain_unchanged(self):
        values = {"score": 50.9, "fundamental": 54, "technical": 8, "momentum": 38, "liquidity": 100, "macro": 32, "risk": 100}
        session_info = {"session_date": "2026-07-30", "regime": "phòng thủ"}
        contract = bundle.build_analysis_score_contract(values, session_info)
        self.assertEqual(contract["session_date"], "2026-07-30")
        self.assertEqual(contract["regime"], "phòng thủ")
        self.assertEqual(contract["values"]["score"], 50.9)
        self.assertEqual(contract["values"]["fundamental"], 54)
        self.assertEqual(contract["values"]["technical"], 8)
        self.assertEqual(contract["values"]["momentum"], 38)
        self.assertEqual(contract["values"]["liquidity"], 100)
        self.assertEqual(contract["values"]["macro"], 32)
        self.assertEqual(contract["values"]["risk"], 100)


class OpportunityRankingSemanticsTests(unittest.TestCase):
    """Phase 0B.4: opportunity_ranking semantic safety contract tests."""

    def test_original_ordering_and_values_are_preserved(self):
        raw_ranking = {
            "schema_version": "1.0.0",
            "state": "available",
            "ranking_basis": ["financial_quality", "ticker"],
            "ranking_kind": "evidence_availability_ordering_only",
            "ordered_tickers": [{"ticker": "HPG", "state": "available"}, {"ticker": "VNM", "state": "partial"}],
            "is_actionable": False,
        }
        contract = bundle.build_opportunity_ranking_contract(raw_ranking)
        self.assertEqual(contract["ordered_tickers"], raw_ranking["ordered_tickers"])
        self.assertEqual(contract["state"], "available")

    def test_ordering_basis_is_evidence_availability(self):
        raw_ranking = {"ordered_tickers": []}
        contract = bundle.build_opportunity_ranking_contract(raw_ranking)
        self.assertEqual(contract["ordering_basis"], "evidence_availability")

    def test_ranking_type_is_evidence_availability_ordering_only(self):
        raw_ranking = {"ordered_tickers": []}
        contract = bundle.build_opportunity_ranking_contract(raw_ranking)
        self.assertEqual(contract["ranking_type"], "evidence_availability_ordering_only")
        self.assertEqual(contract["ranking_kind"], "evidence_availability_ordering_only")

    def test_investment_ranking_and_actionability_flags_are_false(self):
        raw_ranking = {"ordered_tickers": []}
        contract = bundle.build_opportunity_ranking_contract(raw_ranking)
        self.assertFalse(contract["is_investment_ranking"])
        self.assertFalse(contract["is_actionable"])

    def test_limitations_prevent_investment_attractiveness_interpretation(self):
        raw_ranking = {"ordered_tickers": []}
        contract = bundle.build_opportunity_ranking_contract(raw_ranking)
        limits_text = " ".join(contract["interpretation_limits"])
        self.assertIn("not an investment-attractiveness score", limits_text)
        self.assertIn("portfolio priority", limits_text)

    def test_missing_input_does_not_create_valid_looking_ranking(self):
        self.assertIsNone(bundle.build_opportunity_ranking_contract(None))
        self.assertIsNone(bundle.build_opportunity_ranking_contract({}))

    def test_unrelated_fields_remain_unchanged(self):
        raw_ranking = {
            "schema_version": "1.0.0",
            "state": "available",
            "ranking_basis": ["financial_quality", "ticker"],
            "ordered_tickers": [{"ticker": "HPG", "state": "available"}],
            "custom_metadata": {"key": "value"},
        }
        contract = bundle.build_opportunity_ranking_contract(raw_ranking)
        self.assertEqual(contract["schema_version"], "1.0.0")
        self.assertEqual(contract["custom_metadata"], {"key": "value"})


class TaSignalSemanticsTests(unittest.TestCase):
    """Phase 0B.5: ta_signal semantic safety contract tests."""

    def test_existing_ta_signal_is_preserved_and_marked_available(self):
        ta_row = {"ticker": "POW", "date": "2026-07-30", "direction": "bullish"}
        semantics = bundle.build_ta_signal_semantics(ta_row)
        self.assertEqual(semantics["coverage_status"], "available")
        self.assertEqual(semantics["evaluation_status"], "record_available")
        self.assertFalse(semantics["is_actionable"])
        self.assertFalse(semantics["is_no_signal_claim"])
        self.assertIn("not an investment action", semantics["presence_interpretation"])

    def test_missing_ta_row_remains_null_semantics(self):
        semantics = bundle.build_ta_signal_semantics(None)
        self.assertEqual(semantics["coverage_status"], "missing")
        self.assertEqual(semantics["evaluation_status"], "unqualified")
        self.assertEqual(semantics["reason"], "absent_from_ta_signals_csv")
        self.assertFalse(semantics["is_actionable"])

    def test_missing_ta_is_not_represented_as_confirmed_no_signal_result(self):
        semantics = bundle.build_ta_signal_semantics(None)
        self.assertFalse(semantics["is_no_signal_claim"])
        self.assertIn("not a confirmed no-signal claim", semantics["null_interpretation"])

    def test_missing_evaluation_evidence_remains_unqualified_and_non_actionable(self):
        semantics = bundle.build_ta_signal_semantics(None)
        self.assertEqual(semantics["evaluation_status"], "unqualified")
        self.assertFalse(semantics["is_actionable"])

    def test_unrelated_fields_remain_unchanged(self):
        ta_row = {"ticker": "HPG", "patterns": "doji", "rs_rating": 80}
        semantics = bundle.build_ta_signal_semantics(ta_row)
        self.assertEqual(ta_row["ticker"], "HPG")
        self.assertEqual(ta_row["patterns"], "doji")
        self.assertEqual(ta_row["rs_rating"], 80)


class NewsWindowSemanticsTests(unittest.TestCase):
    """Phase 0B.6: news_related cutoff semantic safety contract tests."""

    def test_original_cutoff_value_is_preserved(self):
        news_data = {
            "status": "no_company_specific_news",
            "company_news_count": 0,
            "cutoff": "2026-06-29T15:36:20Z",
            "latest_published_utc": None,
        }
        semantics = bundle.build_news_window_semantics(news_data)
        self.assertEqual(semantics["cutoff_timestamp"], "2026-06-29T15:36:20Z")

    def test_cutoff_semantics_are_lookback_window_start(self):
        news_data = {"cutoff": "2026-06-29T15:36:20Z"}
        semantics = bundle.build_news_window_semantics(news_data)
        self.assertEqual(semantics["cutoff_semantics"], "lookback_window_start")

    def test_cutoff_is_not_labeled_as_latest_update(self):
        news_data = {"cutoff": "2026-06-29T15:36:20Z"}
        semantics = bundle.build_news_window_semantics(news_data)
        self.assertIn("start of the lookback window", semantics["cutoff_interpretation"])
        self.assertNotIn("latest update", semantics["cutoff_semantics"])

    def test_missing_latest_publication_or_retrieval_timestamps_remain_missing(self):
        news_data = {"cutoff": "2026-06-29T15:36:20Z", "latest_published_utc": None}
        semantics = bundle.build_news_window_semantics(news_data)
        self.assertIsNone(semantics["latest_published_utc"])
        self.assertNotIn("retrieved_at", semantics)
        self.assertNotIn("fetched_at", semantics)

    def test_zero_mapped_articles_does_not_become_confirmed_no_news_claim(self):
        news_data = {"company_news_count": 0, "cutoff": "2026-06-29T15:36:20Z"}
        semantics = bundle.build_news_window_semantics(news_data)
        self.assertFalse(semantics["is_no_relevant_news_claim"])
        limits_text = " ".join(semantics["interpretation_limits"])
        self.assertIn("zero mapped articles does not prove that no relevant company news exists", limits_text)

    def test_mapping_coverage_remains_unqualified_and_non_actionable(self):
        news_data = {"cutoff": "2026-06-29T15:36:20Z"}
        semantics = bundle.build_news_window_semantics(news_data)
        self.assertEqual(semantics["mapping_coverage_status"], "unqualified")
        self.assertFalse(semantics["is_actionable"])

    def test_unrelated_fields_remain_unchanged(self):
        news_data = {
            "status": "no_company_specific_news",
            "company_news_count": 0,
            "cutoff": "2026-06-29T15:36:20Z",
            "market_news_count": 30,
        }
        semantics = bundle.build_news_window_semantics(news_data)
        self.assertEqual(news_data["status"], "no_company_specific_news")
        self.assertEqual(news_data["market_news_count"], 30)


class FinancialPeriodCoverageTests(unittest.TestCase):
    """Phase 2A hardened: per-ticker financial period coverage contract tests."""

    def test_ticker_a_q2_does_not_cause_ticker_b_q1_to_report_q2(self):
        fin_a = {"period_used": "2026-Q2", "row": {"period": "2026-Q2", "revenue": 100}, "excluded_unverified_periods": []}
        fin_b = {"period_used": "2026-Q1", "row": {"period": "2026-Q1", "revenue": 80}, "excluded_unverified_periods": []}
        cov_a = bundle.build_financial_period_coverage_contract("TICK_A", fin_a)
        cov_b = bundle.build_financial_period_coverage_contract("TICK_B", fin_b)
        self.assertEqual(cov_a["latest_calendar_eligible_period"], "2026-Q2")
        self.assertEqual(cov_b["latest_calendar_eligible_period"], "2026-Q1")

    def test_global_max_does_not_populate_missing_ticker_period(self):
        cov_missing = bundle.build_financial_period_coverage_contract("TICK_MISSING", None)
        self.assertIsNone(cov_missing["latest_raw_period"])
        self.assertIsNone(cov_missing["latest_calendar_eligible_period"])
        self.assertIsNone(cov_missing["latest_verified_period"])
        self.assertIsNone(cov_missing["latest_complete_period"])
        self.assertEqual(cov_missing["coverage_status"], "unavailable")

    def test_calendar_eligibility_does_not_populate_latest_verified_period(self):
        fin = {"period_used": "2026-Q1", "row": {"period": "2026-Q1", "revenue": 50}, "excluded_unverified_periods": []}
        cov = bundle.build_financial_period_coverage_contract("TICK_V", fin)
        self.assertEqual(cov["latest_calendar_eligible_period"], "2026-Q1")
        self.assertIsNone(cov["latest_verified_period"])
        self.assertEqual(cov["coverage_status"], "calendar_eligible_only")
        limits_text = " ".join(cov["limitations"])
        self.assertIn("calendar eligibility is not source verification", limits_text)

    def test_explicit_verification_evidence_populates_latest_verified_period(self):
        fin = {"period_used": "2026-Q1", "row": {"period": "2026-Q1", "revenue": 50, "source_verified": True}}
        cov = bundle.build_financial_period_coverage_contract("TICK_VERIFIED", fin)
        self.assertEqual(cov["latest_verified_period"], "2026-Q1")
        self.assertEqual(cov["coverage_status"], "verified_only")

    def test_verified_does_not_populate_latest_complete_period(self):
        fin = {"period_used": "2026-Q1", "row": {"period": "2026-Q1", "source_verified": True}}
        cov = bundle.build_financial_period_coverage_contract("TICK_VERIFIED", fin)
        self.assertIsNone(cov["latest_complete_period"])
        self.assertFalse(cov["is_actionable"])

    def test_missing_data_remains_null_and_unavailable(self):
        cov = bundle.build_financial_period_coverage_contract("EMPTY", {})
        self.assertIsNone(cov["latest_raw_period"])
        self.assertIsNone(cov["latest_calendar_eligible_period"])
        self.assertIsNone(cov["latest_verified_period"])
        self.assertIsNone(cov["latest_complete_period"])
        self.assertEqual(cov["statement_coverage"], "missing")
        self.assertEqual(cov["coverage_status"], "unavailable")
        self.assertFalse(cov["is_actionable"])

    def test_annual_quarterly_ttm_identities_remain_separate(self):
        fin_q = {"period_used": "2026-Q1", "row": {"period": "2026-Q1"}}
        fin_a = {"period_used": "2025", "row": {"period": "2025"}}
        fin_ttm = {"period_used": "2026-TTM", "row": {"period": "2026-TTM"}}
        self.assertEqual(bundle.build_financial_period_coverage_contract("Q", fin_q)["period_type"], "quarterly")
        self.assertEqual(bundle.build_financial_period_coverage_contract("A", fin_a)["period_type"], "annual")
        self.assertEqual(bundle.build_financial_period_coverage_contract("T", fin_ttm)["period_type"], "ttm")

    def test_conflicting_period_identities_return_incomparable(self):
        fin_conflict = {"period_used": "2026-Q1", "row": {"period": "2026-Q1"}, "warning": "conflicting_period_identities"}
        cov = bundle.build_financial_period_coverage_contract("CONFLICT", fin_conflict)
        self.assertEqual(cov["coverage_status"], "incomparable")


class GenericVerifiedFinancialPeriodTests(unittest.TestCase):
    """Phase 5C: resolve_verified_financial_periods() -- the fully generic,
    data-driven replacement for Phase 5B's HPG/FY2024-hardcoded resolver -- plus the
    (unchanged) verified_evidence_period parameter on
    build_financial_period_coverage_contract(). Mixes real-retained-data proofs (this
    repo's established convention) with controlled/mocked proofs for fail-closed paths
    real data cannot exercise (hash mismatch, wrong period, unknown observation,
    conflicting scope) without corrupting a fixture."""

    FIN = {"period_used": "2026-Q1", "row": {"period": "2026-Q1", "revenue": 1}}
    SEPARATE_STATEMENT_EVIDENCE_ID = "cd4c4754fb807ef05610e62456010e8fffe22ac3a86f7125cc6f74ca9354aadc"

    # -- 1/9. Real evidence qualifies HPG (regression) and VNM (new second slice) -----

    def test_real_hpg_fy2024_qualification_is_unchanged_from_phase_5b(self):
        result = bundle.resolve_verified_financial_periods(RUNTIME_ROOT).get("HPG")
        self.assertIsNotNone(result)
        self.assertEqual(result["ticker"], "HPG")
        self.assertEqual(result["period"], "2024")
        self.assertEqual(result["statement_scope"], "consolidated")
        self.assertGreater(len(result["observation_ids"]), 0)
        cov = bundle.build_financial_period_coverage_contract("HPG", self.FIN, None, result)
        self.assertEqual(cov["coverage_status"], "verified_only")
        self.assertEqual(cov["latest_verified_period"], "2024")
        self.assertIsNone(cov["latest_complete_period"])
        # The independent, more recent calendar-eligible period is preserved, not overwritten.
        self.assertEqual(cov["latest_calendar_eligible_period"], "2026-Q1")

    def test_real_vnm_fy2024_consolidated_evidence_qualifies_as_the_second_slice(self):
        generic = bundle.resolve_verified_financial_periods(RUNTIME_ROOT)
        result = generic.get("VNM")
        self.assertIsNotNone(result)
        self.assertEqual(result["period"], "2024")
        self.assertEqual(result["statement_scope"], "consolidated")
        self.assertGreater(len(result["observation_ids"]), 0)
        self.assertIn("VNM", bundle._PHASE_5C_ENABLED_TICKERS)
        cov = bundle.build_financial_period_coverage_contract("VNM", self.FIN, None, result)
        self.assertEqual(cov["coverage_status"], "verified_only")
        self.assertEqual(cov["latest_verified_period"], "2024")
        self.assertIsNone(cov["latest_complete_period"])

    def test_real_vcb_evidence_also_qualifies_generically_but_is_not_in_this_milestones_rollout(self):
        # Proves the resolver is genuinely generic (VCB's independently-qualifying
        # evidence is found on equal footing with HPG/VNM) while confirming the
        # deliberate, separately-applied Phase 5C rollout scope excludes it.
        generic = bundle.resolve_verified_financial_periods(RUNTIME_ROOT)
        self.assertIn("VCB", generic)
        self.assertNotIn("VCB", bundle._PHASE_5C_ENABLED_TICKERS)

    # -- 2. No ticker/period-specific qualification branch (proven with a synthetic ticker) --

    def test_resolver_qualifies_a_wholly_synthetic_ticker_period_with_no_special_casing(self):
        fake_verified = {
            "status": "available",
            "by_observation_id": {"obs-synthetic": {"statement_scope": "consolidated"}},
        }
        fake_observations = [{"observation_id": "obs-synthetic", "ticker": "ZZZZ",
                               "reporting_period": "2099", "reporting_frequency": "annual"}]
        with mock.patch.object(bundle, "load_verified_citations", return_value=fake_verified), \
             mock.patch.object(bundle, "read_observations", return_value=fake_observations):
            result = bundle.resolve_verified_financial_periods(RUNTIME_ROOT)
        self.assertEqual(result, {"ZZZZ": {"ticker": "ZZZZ", "period": "2099", "period_type": "annual",
                                            "statement_scope": "consolidated", "observation_ids": ["obs-synthetic"]}})

    # -- 3. Separate/parent statement evidence must not qualify the consolidated period -

    def test_real_verified_observation_ids_exclude_the_separate_statement_evidence(self):
        generic = bundle.resolve_verified_financial_periods(RUNTIME_ROOT)
        verified = bundle.load_verified_citations(RUNTIME_ROOT)
        for result in generic.values():
            for obs_id in result["observation_ids"]:
                self.assertNotEqual(verified["by_observation_id"][obs_id]["evidence_id"], self.SEPARATE_STATEMENT_EVIDENCE_ID)

    def test_separate_scope_override_is_rejected_at_contract_level(self):
        fake_override = {
            "ticker": "HPG", "period": "2024", "period_type": "annual",
            "statement_scope": "separate", "observation_ids": ["deadbeef"],
        }
        cov = bundle.build_financial_period_coverage_contract("HPG", self.FIN, None, fake_override)
        self.assertEqual(cov["coverage_status"], "calendar_eligible_only")
        self.assertIsNone(cov["latest_verified_period"])

    # -- 4/5. Hash mismatch / unknown citation or observation identity fail closed -----

    def test_no_verified_citations_available_fails_closed(self):
        with mock.patch.object(bundle, "load_verified_citations", return_value={"status": "unavailable", "by_observation_id": {}, "rejected": []}):
            result = bundle.resolve_verified_financial_periods(RUNTIME_ROOT)
        self.assertEqual(result, {})

    def test_verified_citation_with_unknown_observation_identity_fails_closed(self):
        fake_verified = {"status": "available", "by_observation_id": {"obs-unknown": {"statement_scope": "consolidated"}}}
        with mock.patch.object(bundle, "load_verified_citations", return_value=fake_verified), \
             mock.patch.object(bundle, "read_observations", return_value=[]):  # observation store empty -> unknown identity
            result = bundle.resolve_verified_financial_periods(RUNTIME_ROOT)
        self.assertEqual(result, {})

    # -- 6. Ambiguous or conflicting statement scope fails closed ----------------------

    def test_conflicting_scope_for_the_same_period_fails_closed(self):
        fake_verified = {
            "status": "available",
            "by_observation_id": {
                "obs-a": {"statement_scope": "consolidated"},
                "obs-b": {"statement_scope": "separate"},
            },
        }
        fake_observations = [
            {"observation_id": "obs-a", "ticker": "ZZZZ", "reporting_period": "2099", "reporting_frequency": "annual"},
            {"observation_id": "obs-b", "ticker": "ZZZZ", "reporting_period": "2099", "reporting_frequency": "annual"},
        ]
        with mock.patch.object(bundle, "load_verified_citations", return_value=fake_verified), \
             mock.patch.object(bundle, "read_observations", return_value=fake_observations):
            result = bundle.resolve_verified_financial_periods(RUNTIME_ROOT)
        self.assertNotIn("ZZZZ", result)

    # -- 7. Period/frequency mismatch fails closed --------------------------------------

    def test_verified_citation_for_a_different_period_does_not_qualify_the_requested_one(self):
        fake_verified = {"status": "available", "by_observation_id": {"obs-2023": {"statement_scope": "consolidated"}}}
        fake_observations = [{"observation_id": "obs-2023", "ticker": "HPG",
                               "reporting_period": "2023", "reporting_frequency": "annual"}]
        with mock.patch.object(bundle, "load_verified_citations", return_value=fake_verified), \
             mock.patch.object(bundle, "read_observations", return_value=fake_observations):
            result = bundle.resolve_verified_financial_periods(RUNTIME_ROOT)
        self.assertEqual(result["HPG"]["period"], "2023")  # qualifies 2023, not some other requested period
        cov_for_2024_row = bundle.build_financial_period_coverage_contract(
            "HPG", {"period_used": "2024", "row": {"period": "2024"}}, None, result["HPG"],
        )
        # The override's own period ("2023") is what gets set -- it never silently
        # adopts period_used ("2024") just because that's the ticker's current row.
        self.assertEqual(cov_for_2024_row["latest_verified_period"], "2023")

    # -- 8. Verified remains distinct from complete -------------------------------------

    def test_verified_does_not_populate_latest_complete_period_for_either_qualified_ticker(self):
        generic = bundle.resolve_verified_financial_periods(RUNTIME_ROOT)
        for tk in ("HPG", "VNM"):
            cov = bundle.build_financial_period_coverage_contract(tk, self.FIN, None, generic.get(tk))
            self.assertIsNone(cov["latest_complete_period"])
            self.assertFalse(cov["is_actionable"])

    # -- 10. Unsupported VNM/VCB periods (and VCB itself, per rollout scope) unchanged -

    def test_vcb_remains_unchanged_under_this_milestones_rollout_scope(self):
        generic = bundle.resolve_verified_financial_periods(RUNTIME_ROOT)
        filtered = {tk: v for tk, v in generic.items() if tk in bundle._PHASE_5C_ENABLED_TICKERS}
        cov = bundle.build_financial_period_coverage_contract("VCB", self.FIN, None, filtered.get("VCB"))
        self.assertEqual(cov["coverage_status"], "calendar_eligible_only")
        self.assertIsNone(cov["latest_verified_period"])

    def test_unrelated_ticker_unaffected_by_hpg_or_vnm_verified_evidence(self):
        generic = bundle.resolve_verified_financial_periods(RUNTIME_ROOT)
        cov = bundle.build_financial_period_coverage_contract("POW", self.FIN, None, generic.get("HPG"))
        self.assertEqual(cov["coverage_status"], "calendar_eligible_only")
        self.assertIsNone(cov["latest_verified_period"])

    # -- 11. Existing no-evidence / two-argument call behavior remains backward-compatible --

    def test_existing_two_argument_call_signature_still_works_unchanged(self):
        cov = bundle.build_financial_period_coverage_contract("HPG", self.FIN)
        self.assertEqual(cov["coverage_status"], "calendar_eligible_only")
        self.assertIsNone(cov["latest_verified_period"])

    def test_override_with_no_observation_ids_is_rejected(self):
        fake_override = {"ticker": "HPG", "period": "2024", "period_type": "annual",
                          "statement_scope": "consolidated", "observation_ids": []}
        cov = bundle.build_financial_period_coverage_contract("HPG", self.FIN, None, fake_override)
        self.assertIsNone(cov["latest_verified_period"])

    # -- 12. Determinism and no mutation of retained evidence/observation files -------

    def test_real_resolver_is_deterministic(self):
        first = bundle.resolve_verified_financial_periods(RUNTIME_ROOT)
        second = bundle.resolve_verified_financial_periods(RUNTIME_ROOT)
        self.assertEqual(first, second)

    def test_real_resolver_does_not_mutate_evidence_or_observation_files(self):
        targets = [
            _runtime_path("data/official-evidence/qualification_citations.jsonl"),
            _runtime_path("data/official-evidence/manifest.json"),
            _runtime_path("data/financial-observations/observations.jsonl"),
        ]
        before = {p: (_sha256(p) if p.exists() else None) for p in targets}
        bundle.resolve_verified_financial_periods(RUNTIME_ROOT)
        after = {p: (_sha256(p) if p.exists() else None) for p in targets}
        self.assertEqual(before, after)


class ValuationNamespaceTests(unittest.TestCase):
    """Phase 2B hardened: metric-specific valuation namespace and comparability contract tests."""

    def test_historical_pe_from_methods_pe_observed_multiple_is_preserved(self):
        snapshot_row = {"pe": 11.98, "pb": 1.45, "date": "2026-07-30", "source": "KBS"}
        relative_val = {
            "methods": {
                "pe": {
                    "state": "available",
                    "observed_multiple": 10.55,
                    "price_as_of_date": "2024-12-31",
                    "financial_period": {"period": "FY2024"},
                    "provenance": {
                        "share_count_weighted_average_basic": {"semantics": "weighted_average_basic"},
                    },
                },
                "pb": {
                    "state": "available",
                    "observed_multiple": 1.25,
                    "price_as_of_date": "2024-12-31",
                    "financial_period": {"period": "FY2024"},
                    "provenance": {
                        "share_count_period_end": {"semantics": "period_end"},
                    },
                },
            },
        }
        contract = bundle.build_valuation_namespaces_contract("HPG", snapshot_row, relative_val)
        pe_live = contract["live_vendor"]["metrics"]["pe"]
        pb_live = contract["live_vendor"]["metrics"]["pb"]
        pe_hist = contract["historical_calculated"]["metrics"]["pe"]
        pb_hist = contract["historical_calculated"]["metrics"]["pb"]
        self.assertEqual(pe_live["value"], 11.98)
        self.assertEqual(pb_live["value"], 1.45)
        self.assertEqual(pe_hist["value"], 10.55)
        self.assertEqual(pb_hist["value"], 1.25)
        self.assertEqual(contract["comparability"]["metrics"]["pe"]["status"], "incomparable")
        self.assertFalse(contract["comparability"]["metrics"]["pe"]["is_actionable"])

    def test_pe_and_pb_identities_are_stored_separately(self):
        snapshot_row = {"pe": 11.98, "pb": 1.45, "date": "2026-07-30", "source": "KBS"}
        relative_val = {
            "methods": {
                "pe": {"state": "available", "observed_multiple": 10.55},
                "pb": {"state": "available", "observed_multiple": 1.25},
            },
            "inputs": {
                "current_price": {"evidence": {"trading_date": "2024-12-31"}},
                "share_count_weighted_average_basic": {"semantics": "weighted_average_basic"},
                "share_count_period_end": {"semantics": "period_end"},
                "financial": {"period_identity": {"period": "FY2024"}},
            },
        }
        contract = bundle.build_valuation_namespaces_contract("HPG", snapshot_row, relative_val)
        pe_live = contract["live_vendor"]["metrics"]["pe"]
        pb_live = contract["live_vendor"]["metrics"]["pb"]
        pe_hist = contract["historical_calculated"]["metrics"]["pe"]
        pb_hist = contract["historical_calculated"]["metrics"]["pb"]
        self.assertEqual(pe_live["value"], 11.98)
        self.assertEqual(pb_live["value"], 1.45)
        self.assertEqual(pe_hist["value"], 10.55)
        self.assertEqual(pb_hist["value"], 1.25)
        self.assertNotEqual(pe_hist["denominator_measure"], pb_hist["denominator_measure"])

    def test_pe_and_pb_may_have_different_share_bases(self):
        relative_val = {
            "methods": {
                "pe": {
                    "state": "available",
                    "observed_multiple": 10.55,
                    "provenance": {"share_count_weighted_average_basic": {"semantics": "weighted_average_basic"}},
                },
                "pb": {
                    "state": "available",
                    "observed_multiple": 1.25,
                    "provenance": {"share_count_period_end": {"semantics": "period_end"}},
                },
            },
        }
        contract = bundle.build_valuation_namespaces_contract("HPG", None, relative_val)
        self.assertEqual(contract["historical_calculated"]["metrics"]["pe"]["share_basis"], "weighted_average_basic")
        self.assertEqual(contract["historical_calculated"]["metrics"]["pb"]["share_basis"], "period_end")

    def test_missing_live_vendor_methodology_remains_unknown(self):
        snapshot_row = {"pe": 11.98}
        contract = bundle.build_valuation_namespaces_contract("HPG", snapshot_row, None)
        pe_live = contract["live_vendor"]["metrics"]["pe"]
        self.assertEqual(pe_live["denominator_measure"], "vendor_unspecified")
        self.assertEqual(pe_live["share_basis"], "vendor_unspecified")

    def test_bundle_session_is_not_silently_promoted_to_proven_price_date(self):
        snapshot_row = {"pe": 11.98}
        contract = bundle.build_valuation_namespaces_contract("HPG", snapshot_row, None)
        self.assertIsNone(contract["live_vendor"]["metrics"]["pe"]["price_date"])

    def test_pe_comparability_is_evaluated_independently_from_pb(self):
        snapshot_row = {"pe": 11.98, "pb": 1.45, "date": "2026-07-30"}
        relative_val = {
            "methods": {
                "pe": {"state": "available", "observed_multiple": 10.55, "price_as_of_date": "2024-12-31"},
            },
        }
        contract = bundle.build_valuation_namespaces_contract("HPG", snapshot_row, relative_val)
        pe_comp = contract["comparability"]["metrics"]["pe"]
        pb_comp = contract["comparability"]["metrics"]["pb"]
        self.assertEqual(pe_comp["status"], "incomparable")
        self.assertEqual(pb_comp["status"], "insufficient_identity")
        self.assertFalse(pe_comp["is_actionable"])
        self.assertFalse(pb_comp["is_actionable"])

    def test_hpg_values_are_preserved_and_pe_incomparable(self):
        snapshot_row = {"pe": 11.98, "date": "2026-07-30"}
        relative_val = {
            "methods": {
                "pe": {"state": "available", "observed_multiple": 10.55, "price_as_of_date": "2024-12-31"},
            },
        }
        contract = bundle.build_valuation_namespaces_contract("HPG", snapshot_row, relative_val)
        self.assertEqual(contract["live_vendor"]["metrics"]["pe"]["value"], 11.98)
        self.assertEqual(contract["historical_calculated"]["metrics"]["pe"]["value"], 10.55)
        self.assertEqual(contract["comparability"]["metrics"]["pe"]["status"], "incomparable")

    def test_missing_identity_produces_insufficient_identity(self):
        snapshot_row = {"pe": 11.98}
        contract = bundle.build_valuation_namespaces_contract("HPG", snapshot_row, None)
        self.assertEqual(contract["comparability"]["metrics"]["pe"]["status"], "insufficient_identity")

    def test_missing_metric_produces_not_available(self):
        contract = bundle.build_valuation_namespaces_contract("EMPTY", None, None)
        self.assertEqual(contract["comparability"]["metrics"]["pe"]["status"], "not_available")
        self.assertEqual(contract["comparability"]["metrics"]["pb"]["status"], "not_available")

    def test_matching_metric_names_alone_do_not_establish_comparability(self):
        snapshot_row = {"pe": 11.98}
        relative_val = {"methods": {"pe": {"state": "available", "observed_multiple": 10.55}}}
        contract = bundle.build_valuation_namespaces_contract("HPG", snapshot_row, relative_val)
        self.assertNotEqual(contract["comparability"]["metrics"]["pe"]["status"], "comparable")

    def test_legacy_valuation_fields_remain_unchanged(self):
        snapshot_row = {"pe": 11.98, "ticker": "HPG"}
        relative_val = {"methods": {"pe": {"state": "available", "observed_multiple": 10.55}}}
        contract = bundle.build_valuation_namespaces_contract("HPG", snapshot_row, relative_val)
        self.assertEqual(snapshot_row["pe"], 11.98)
        self.assertEqual(relative_val["methods"]["pe"]["observed_multiple"], 10.55)


class ShareBasisIdentitiesTests(unittest.TestCase):
    """Phase 3A: dated share-basis identity contract tests."""

    def test_current_period_end_and_weighted_average_shares_remain_separate(self):
        snapshot_row = {"shares_outstanding": 334000000, "date": "2026-07-30", "source": "KBS"}
        contract = bundle.build_share_basis_identities_contract("PNJ", snapshot_row)
        self.assertIn("current_market", contract)
        self.assertIn("financial_period_end", contract)
        self.assertIn("weighted_average", contract)
        self.assertEqual(contract["current_market"]["value"], 334000000)
        self.assertEqual(contract["current_market"]["basis_type"], "current_market_shares_outstanding")

    def test_different_effective_dates_produce_incomparable(self):
        snapshot_row = {"shares_outstanding": 334000000, "date": "2026-07-30"}
        contract = bundle.build_share_basis_identities_contract("PNJ", snapshot_row)
        pair = contract["comparability"]["pairs"]["current_vs_period_end"]
        self.assertIn(pair["status"], ("incomparable", "insufficient_identity"))
        self.assertFalse(pair["is_actionable"])

    def test_different_basis_types_produce_incomparable(self):
        snapshot_row = {"shares_outstanding": 334000000, "date": "2026-07-30"}
        contract = bundle.build_share_basis_identities_contract("PNJ", snapshot_row)
        pair = contract["comparability"]["pairs"]["current_vs_period_end"]
        self.assertFalse(pair["is_actionable"])

    def test_equal_numeric_values_alone_do_not_establish_comparability(self):
        snapshot_row = {"shares_outstanding": 1000000, "date": "2026-07-30"}
        contract = bundle.build_share_basis_identities_contract("TEST", snapshot_row)
        pairs = contract["comparability"]["pairs"]
        for p in pairs.values():
            self.assertNotEqual(p["status"], "comparable")

    def test_missing_identity_metadata_produces_insufficient_identity(self):
        snapshot_row = {"shares_outstanding": 334000000, "date": "2026-07-30"}
        contract = bundle.build_share_basis_identities_contract("TEST_MISSING", snapshot_row)
        pair = contract["comparability"]["pairs"]["current_vs_period_end"]
        self.assertIn(pair["status"], ("insufficient_identity", "incomparable"))

    def test_missing_share_identity_produces_not_available(self):
        contract = bundle.build_share_basis_identities_contract("NONE", None)
        pair = contract["comparability"]["pairs"]["current_vs_period_end"]
        self.assertEqual(pair["status"], "not_available")
        self.assertFalse(pair["is_actionable"])

    def test_current_market_cap_confirmation_does_not_qualify_period_end_or_weighted_average_shares(self):
        snapshot_row = {"shares_outstanding": 334000000, "date": "2026-07-30"}
        contract = bundle.build_share_basis_identities_contract("PNJ", snapshot_row)
        self.assertEqual(contract["current_market"]["qualification_status"], "unverified")
        self.assertEqual(contract["financial_period_end"]["qualification_status"], "missing")
        self.assertEqual(contract["weighted_average"]["qualification_status"], "missing")

    def test_pnj_current_shares_and_q1_period_end_shares_remain_distinct(self):
        snapshot_row = {"shares_outstanding": 334000000, "date": "2026-07-30"}
        contract = bundle.build_share_basis_identities_contract("PNJ", snapshot_row)
        self.assertEqual(contract["current_market"]["basis_type"], "current_market_shares_outstanding")
        self.assertEqual(contract["financial_period_end"]["basis_type"], "period_end_shares_outstanding")
        self.assertNotEqual(contract["current_market"]["basis_type"], contract["financial_period_end"]["basis_type"])

    def test_existing_valuation_and_legacy_share_fields_remain_unchanged(self):
        snapshot_row = {"shares_outstanding": 334000000}
        contract = bundle.build_share_basis_identities_contract("PNJ", snapshot_row)
        self.assertEqual(snapshot_row["shares_outstanding"], 334000000)

    def test_unrelated_fields_remain_unchanged(self):
        contract = bundle.build_share_basis_identities_contract("PNJ", {"shares_outstanding": 334000000})
        self.assertIn("ticker", contract)
        self.assertEqual(contract["ticker"], "PNJ")


class EarningsAnomalyTests(unittest.TestCase):
    """Phase 3B hardened: NVL earnings anomaly semantic contract tests."""

    def test_nvl_like_pat_greater_than_revenue_triggers_anomaly(self):
        fin_nvl = {
            "period_used": "2026-Q1",
            "row": {"period": "2026-Q1", "revenue": 500.0, "net_profit": 1200.0},
        }
        contract = bundle.build_earnings_anomaly_contract("NVL", fin_nvl)
        self.assertEqual(contract["status"], "anomaly_observed")
        self.assertEqual(contract["trigger"], "profit_after_tax_exceeds_revenue")
        self.assertEqual(contract["period"], "2026-Q1")

    def test_anomaly_condition_is_not_labeled_automatically_as_data_error(self):
        fin = {"period_used": "2026-Q1", "row": {"revenue": 100.0, "net_profit": 300.0}}
        contract = bundle.build_earnings_anomaly_contract("NVL", fin)
        self.assertEqual(contract["data_quality_status"], "source_values_observed_verification_unavailable")
        self.assertNotEqual(contract["status"], "data_error")

    def test_anomaly_is_not_represented_as_recurring_profitability(self):
        fin = {"period_used": "2026-Q1", "row": {"revenue": 100.0, "net_profit": 300.0}}
        contract = bundle.build_earnings_anomaly_contract("NVL", fin)
        self.assertEqual(contract["recurrence_status"], "unproven_single_period")

    def test_available_decomposition_fields_are_preserved_without_invention(self):
        fin = {
            "period_used": "2026-Q1",
            "row": {"revenue": 100.0, "net_profit": 300.0, "financial_income": 400.0},
        }
        contract = bundle.build_earnings_anomaly_contract("NVL", fin)
        decomp = contract["decomposition"]
        self.assertEqual(decomp["financial_income"], 400.0)
        self.assertIsNone(decomp["operating_profit"])
        self.assertEqual(decomp["availability_status"], "partially_available")
        self.assertEqual(contract["explanation_status"], "decomposition_available_unreconciled")

    def test_missing_decomposition_evidence_remains_unavailable(self):
        fin = {"period_used": "2026-Q1", "row": {"revenue": 100.0, "net_profit": 300.0}}
        contract = bundle.build_earnings_anomaly_contract("NVL", fin)
        decomp = contract["decomposition"]
        self.assertIsNone(decomp["operating_profit"])
        self.assertIsNone(decomp["financial_income"])
        self.assertIsNone(decomp["other_profit"])
        self.assertEqual(decomp["availability_status"], "unavailable")
        self.assertEqual(contract["explanation_status"], "insufficient_statement_detail")

    def test_pat_over_revenue_ratio_is_not_labeled_as_normal_operating_margin(self):
        fin = {"period_used": "2026-Q1", "row": {"revenue": 100.0, "net_profit": 300.0}}
        contract = bundle.build_earnings_anomaly_contract("NVL", fin)
        obs = contract["observed_relationships"]
        self.assertEqual(obs["relationship_type"], "pat_exceeds_revenue")
        self.assertNotEqual(obs["relationship_type"], "normal_operating_margin")

    def test_is_actionable_is_false(self):
        fin = {"period_used": "2026-Q1", "row": {"revenue": 100.0, "net_profit": 300.0}}
        contract = bundle.build_earnings_anomaly_contract("NVL", fin)
        self.assertFalse(contract["is_actionable"])

    def test_non_trigger_ticker_uses_not_observed_status(self):
        fin_normal = {"period_used": "2026-Q1", "row": {"revenue": 1000.0, "net_profit": 150.0}}
        contract = bundle.build_earnings_anomaly_contract("HPG", fin_normal)
        self.assertEqual(contract["status"], "not_observed")
        self.assertIsNone(contract["trigger"])
        self.assertEqual(contract["data_quality_status"], "source_values_observed_verification_unavailable")

    def test_missing_revenue_or_pat_fails_closed(self):
        fin_missing = {"period_used": "2026-Q1", "row": {"revenue": None, "net_profit": 100.0}}
        contract = bundle.build_earnings_anomaly_contract("MISSING", fin_missing)
        self.assertEqual(contract["status"], "not_observed")

    def test_legacy_financial_fields_remain_unchanged(self):
        fin_nvl = {"period_used": "2026-Q1", "row": {"revenue": 500.0, "net_profit": 1200.0}}
        contract = bundle.build_earnings_anomaly_contract("NVL", fin_nvl)
        self.assertEqual(fin_nvl["row"]["revenue"], 500.0)
        self.assertEqual(fin_nvl["row"]["net_profit"], 1200.0)


class PriceBasisContractTests(unittest.TestCase):
    """Pure contract tests: no runtime snapshots, database, or network required."""

    def test_verified_raw_is_preserved(self):
        contract = bundle.build_price_basis_contract({"price_basis": "raw", "price_basis_verified": True})
        self.assertEqual(contract["price_basis"], "raw")
        self.assertTrue(contract["price_basis_verified"])

    def test_verified_adjusted_is_preserved(self):
        contract = bundle.build_price_basis_contract({"price_basis": "adjusted", "price_basis_verified": True})
        self.assertEqual(contract["price_basis"], "adjusted")
        self.assertTrue(contract["price_basis_verified"])

    def test_unknown_is_unverified(self):
        contract = bundle.build_price_basis_contract({"price_basis": "unknown", "price_basis_verified": True})
        self.assertEqual(contract["price_basis"], "unknown")
        self.assertFalse(contract["price_basis_verified"])

    def test_missing_or_unverified_basis_falls_back_to_unknown(self):
        c = bundle.build_price_basis_contract()
        self.assertEqual(c["price_basis"], "unknown")
        self.assertFalse(c["price_basis_verified"])
        self.assertFalse(c["is_actionable"])
        self.assertEqual(c["volume_basis"], "unknown")
        self.assertFalse(c["volume_basis_verified"])
        self.assertEqual(c["source"], "no_verified_price_basis_metadata")
        self.assertEqual(
            bundle.normalize_price_basis("raw", False),
            ("unknown", False),
        )

    def test_unknown_adds_quality_flag_and_verified_basis_does_not(self):
        unknown_flags = bundle.build_data_quality_flags([], {}, [], bundle.build_price_basis_contract())
        self.assertIn(bundle.PRICE_BASIS_UNVERIFIED_CODE, [flag["code"] for flag in unknown_flags])

        verified_flags = bundle.build_data_quality_flags(
            [], {}, [], bundle.build_price_basis_contract({"price_basis": "raw", "price_basis_verified": True}),
        )
        self.assertNotIn(bundle.PRICE_BASIS_UNVERIFIED_CODE, [flag["code"] for flag in verified_flags])

    def test_contract_is_json_serializable_with_only_canonical_values(self):
        for value, verified in (("raw", True), ("adjusted", True), ("unknown", False), (None, False)):
            contract = bundle.build_price_basis_contract({"price_basis": value, "price_basis_verified": verified})
            payload = json.loads(json.dumps(contract, allow_nan=False))
            self.assertIn(payload["price_basis"], bundle.PRICE_BASIS_VALUES)
            self.assertIsInstance(payload["price_basis_verified"], bool)


class ExportAiBundleIntegrationTests(unittest.TestCase):
    """Chạy export_ai_bundle.py thật (--allow-stale để không phụ thuộc trạng thái fresh/stale hôm
    nay) trên dữ liệu thật, ghi ra thư mục tạm, rồi đối chiếu với nguồn."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.out_dir = Path(cls.tmpdir.name)
        cls.before_hashes = {name: _sha256(_runtime_path(name)) for name in SOURCE_FILES_MUST_NOT_CHANGE
                             if _runtime_path(name).exists()}
        cls.returncode = run_bundle_main(["--allow-stale"], cls.out_dir)
        with (cls.out_dir / "focus_extract.json").open(encoding="utf-8") as f:
            cls.extract = json.load(f)
        with (cls.out_dir / "bundle_manifest.json").open(encoding="utf-8") as f:
            cls.manifest = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_allow_stale_run_succeeds(self):
        self.assertEqual(self.returncode, 0)

    def test_source_files_are_not_modified(self):
        for name, before in self.before_hashes.items():
            after = _sha256(_runtime_path(name))
            self.assertEqual(before, after, f"{name} bị export_ai_bundle.py sửa — script phải chỉ đọc")

    def test_focus_extract_has_all_five_default_tickers_with_no_warnings(self):
        self.assertEqual(set(self.extract["tickers"].keys()), set(bundle.DEFAULT_TICKERS))
        for tk in bundle.DEFAULT_TICKERS:
            self.assertEqual(self.extract["tickers"][tk]["warnings"], [],
                             f"{tk} không nên có cảnh báo thiếu dữ liệu với 5 mã mặc định hôm nay")

    def test_price_and_date_of_each_ticker_match_db_source(self):
        conn = bundle._connect_db_readonly(_runtime_path("vn_stock.db"))
        try:
            for tk in bundle.DEFAULT_TICKERS:
                row = conn.execute(
                    "SELECT date, close, volume FROM ohlcv WHERE ticker=? ORDER BY date DESC LIMIT 1",
                    (tk,)).fetchone()
                last_candle = self.extract["tickers"][tk]["ohlcv_recent"][-1]
                self.assertEqual(last_candle["date"], row[0])
                self.assertEqual(last_candle["close"], row[1])
                self.assertEqual(last_candle["volume"], row[2])
                snap = self.extract["tickers"][tk]["snapshot"]
                self.assertEqual(snap["date"], row[0])
                self.assertEqual(snap["close"], row[1])
        finally:
            conn.close()

    def test_ohlcv_recent_has_30_candles_per_ticker(self):
        for tk in bundle.DEFAULT_TICKERS:
            self.assertEqual(self.extract["tickers"][tk]["ohlcv_recent_count"], 30)
            self.assertEqual(len(self.extract["tickers"][tk]["ohlcv_recent"]), 30)

    def test_manifest_record_counts_match_real_files(self):
        by_file = {f["file"]: f for f in self.manifest["files"]}
        live_df = pd.read_csv(_runtime_path("screen_snapshot_live.csv"), encoding="utf-8-sig")
        self.assertEqual(by_file["screen_snapshot_live.csv"]["row_or_record_count"], len(live_df))
        ta_df = pd.read_csv(_runtime_path("ta_signals.csv"), encoding="utf-8-sig")
        self.assertEqual(by_file["ta_signals.csv"]["row_or_record_count"], len(ta_df))
        with _runtime_path("analysis_latest.json").open(encoding="utf-8") as f:
            analysis = json.load(f)
        self.assertEqual(by_file["analysis_latest.json"]["row_or_record_count"], len(analysis["scores"]))
        self.assertEqual(by_file["focus_extract.json"]["row_or_record_count"], 5)

    def test_manifest_sha256_matches_actual_source_files(self):
        by_file = {f["file"]: f for f in self.manifest["files"]}
        for name in ("screen_snapshot_live.csv", "ta_signals.csv", "analysis_latest.json"):
            self.assertEqual(by_file[name]["sha256"], _sha256(_runtime_path(name)))
        self.assertEqual(by_file["focus_extract.json"]["sha256"],
                         _sha256(self.out_dir / "focus_extract.json"))

    def test_manifest_status_and_stale_warning_are_consistent(self):
        # [SỬA 2026-07-17 chiều] Bản gốc giả định --allow-stale LUÔN tạo ra status="stale_override"
        # — đúng tại thời điểm viết test (dữ liệu repo khi đó thực sự lệch phiên/lệch thứ tự
        # artifact). Sau khi các lỗi staleness thực tế được sửa (regenerate ta_signals.csv +
        # analysis_latest.json cùng phiên), --allow-stale trên dữ liệu SẠCH hợp lệ trả về "fresh"
        # — đây là hành vi ĐÚNG (cờ --allow-stale chỉ có tác dụng khi thực sự có gì đó stale để ghi
        # đè). Test kiểm tra BẤT BIẾN cấu trúc thay vì giả định trạng thái dữ liệu hôm nay, đúng với
        # chủ đích ban đầu của class này: "không phụ thuộc trạng thái fresh/stale hôm nay".
        status = self.manifest["freshness"]["status"]
        self.assertIn(status, ("fresh", "stale_override"))
        if status == "stale_override":
            self.assertIn("STALE_DATA_WARNING", self.manifest)
        else:
            self.assertNotIn("STALE_DATA_WARNING", self.manifest)


class DefaultRunIsAllOrNothingTests(unittest.TestCase):
    """Bất biến của freshness gate, không phụ thuộc trạng thái fresh/stale thật hôm nay: CHẶN ->
    không file nào được ghi + exit != 0; KHÔNG chặn -> cả 2 file được ghi + exit == 0. Không bao giờ
    ở trạng thái lửng lơ (ghi 1 phần, hoặc ghi file nhưng vẫn báo lỗi)."""

    def test_default_invocation_all_or_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            rc = run_bundle_main([], out_dir)
            extract_exists = (out_dir / "focus_extract.json").exists()
            manifest_exists = (out_dir / "bundle_manifest.json").exists()
            if rc == 0:
                self.assertTrue(extract_exists)
                self.assertTrue(manifest_exists)
            else:
                self.assertFalse(extract_exists, "Bị chặn nhưng vẫn ghi focus_extract.json"
                                 " — vi phạm 'mặc định không xuất bundle khi lệch phiên'")
                self.assertFalse(manifest_exists)


class NoSourceMutationTests(unittest.TestCase):
    """'Không sửa dữ liệu nguồn': export_ai_bundle.py mở DB read-only; cả hai script không chứa
    lệnh SQL ghi."""

    WRITE_SQL_RE = re.compile(
        r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+TABLE|ALTER\s+TABLE|CREATE\s+TABLE)\b",
        re.IGNORECASE)

    def test_vn_indicators_source_has_no_write_sql(self):
        text = (ROOT / "vn_indicators.py").read_text(encoding="utf-8")
        self.assertIsNone(self.WRITE_SQL_RE.search(text))

    def test_export_ai_bundle_source_has_no_write_sql(self):
        text = (ROOT / "export_ai_bundle.py").read_text(encoding="utf-8")
        self.assertIsNone(self.WRITE_SQL_RE.search(text))

    def test_export_ai_bundle_opens_db_strictly_read_only(self):
        text = (ROOT / "export_ai_bundle.py").read_text(encoding="utf-8")
        self.assertIn("mode=ro", text)
        self.assertIn("PRAGMA query_only", text)

    def test_vn_stock_db_mtime_unchanged_by_bundle_run(self):
        before = _runtime_path("vn_stock.db").stat().st_mtime_ns
        with tempfile.TemporaryDirectory() as tmp:
            run_bundle_main(["--allow-stale"], Path(tmp))
        after = _runtime_path("vn_stock.db").stat().st_mtime_ns
        self.assertEqual(before, after)


# ==========================================================================
# TEST cho nâng cấp workflow 2026-07-17 chiều (bỏ Gemini): canonical_rs_rating (mục 3),
# freshness gate nâng cấp (mục 4), analysis_bundle.json (mục 1-2), fiscal period flag ở
# consumer export_ai_bundle.py (mục 6 — bản thân flag được test riêng ở test_fiscal_period_flag.py).
# ==========================================================================

class CanonicalRsRatingTests(unittest.TestCase):
    """Mục 3: canonical_rs_rating phải khớp screen_snapshot_live.csv cho MỌI mã mặc định, và
    reconcile_rs_rating() không bao giờ trả 2 số khác nhau mà không có 'explanation'."""

    @classmethod
    def setUpClass(cls):
        cls.live = pd.read_csv(_runtime_path("screen_snapshot_live.csv"), encoding="utf-8-sig")

    def test_canonical_matches_screen_snapshot_live_for_default_tickers(self):
        snapshot_rows, snapshot_info = bundle.load_live_snapshot_rows(bundle.DEFAULT_TICKERS)
        ta_rows, ta_info = bundle.load_ta_signal_rows(bundle.DEFAULT_TICKERS)
        for tk in bundle.DEFAULT_TICKERS:
            reconciliation = bundle.reconcile_rs_rating(tk, snapshot_rows, ta_rows, snapshot_info, ta_info)
            expected = self.live.loc[self.live["ticker"] == tk, "rs_rating"].iloc[0]
            self.assertEqual(reconciliation["canonical_rs_rating"], expected)
            self.assertEqual(reconciliation["canonical_source"], bundle.CANONICAL_RS_RATING_SOURCE)

    def test_reconciliation_mismatch_case_always_explains_itself(self):
        snapshot_rows = {"XYZ": {"rs_rating": 80}}
        ta_rows = {"XYZ": {"rs_rating": 60}}
        snapshot_info = {"mtime": 200, "mtime_iso": "2026-01-01T20:00:00+07:00"}
        ta_info = {"mtime": 100, "mtime_iso": "2026-01-01T19:00:00+07:00"}
        r = bundle.reconcile_rs_rating("XYZ", snapshot_rows, ta_rows, snapshot_info, ta_info)
        self.assertFalse(r["matches_canonical"])
        self.assertTrue(r["explanation"])
        self.assertIn("KHÔNG khớp", r["explanation"])

    def test_reconciliation_matching_case_also_explains_itself(self):
        snapshot_rows, ta_rows = {"XYZ": {"rs_rating": 80}}, {"XYZ": {"rs_rating": 80}}
        info = {"mtime_iso": "t1"}
        r = bundle.reconcile_rs_rating("XYZ", snapshot_rows, ta_rows, info, info)
        self.assertTrue(r["matches_canonical"])
        self.assertTrue(r["explanation"])

    def test_all_consumers_use_same_canonical_rs_rating(self):
        """'Mọi consumer dùng cùng nguồn canonical' (yêu cầu tường minh mục 3): đối chiếu chéo
        export_ai_bundle.py với context package AI ANALYZE (build_ticker_context.py) cho cùng mã."""
        checked = 0
        for tk in bundle.DEFAULT_TICKERS:
            path = bundle.CONTEXT_PACKAGES_DIR / f"{tk}_context.json"
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as f:
                package = json.load(f)
            expected = self.live.loc[self.live["ticker"] == tk, "rs_rating"].iloc[0]
            self.assertEqual(package["technical_summary"]["rs_rating"], expected,
                             f"{tk}: context package rs_rating lệch canonical (screen_snapshot_live.csv)")
            checked += 1
        self.assertGreater(checked, 0, "Không tìm thấy context package nào để đối chiếu chéo")


class ArtifactOrderTests(unittest.TestCase):
    """Mục 4: chặn khi downstream được tạo TRƯỚC file nguồn mới nhất nó phụ thuộc."""

    def test_detects_downstream_older_than_upstream(self):
        import os
        import time
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream, downstream = root / "screen_snapshot.csv", root / "ta_signals.csv"
            upstream.write_text("x"); downstream.write_text("y")
            now = time.time()
            os.utime(downstream, (now - 100, now - 100))   # downstream CŨ HƠN upstream
            os.utime(upstream, (now, now))
            violations = bundle.check_artifact_order(root, {"ta_signals.csv": ["screen_snapshot.csv"]})
            self.assertEqual(len(violations), 1)
            self.assertEqual(violations[0]["downstream"], "ta_signals.csv")
            self.assertEqual(violations[0]["upstream"], "screen_snapshot.csv")

    def test_no_violation_when_downstream_newer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "screen_snapshot.csv").write_text("x")
            (root / "ta_signals.csv").write_text("y")
            violations = bundle.check_artifact_order(root, {"ta_signals.csv": ["screen_snapshot.csv"]})
            self.assertEqual(violations, [])

    def test_missing_files_are_skipped_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            violations = bundle.check_artifact_order(Path(tmp), {"a.csv": ["b.csv"]})
            self.assertEqual(violations, [])

    def test_default_graph_excludes_own_outputs(self):
        """focus_extract.json/analysis_bundle.json KHÔNG được nằm trong graph mặc định — so mtime
        BẢN CŨ của output với nguồn mới ngay trước khi lần chạy này ghi đè chúng sẽ luôn tự chặn
        vô nghĩa (xem comment tại định nghĩa ARTIFACT_DEPENDENCY_GRAPH)."""
        self.assertNotIn("focus_extract.json", bundle.ARTIFACT_DEPENDENCY_GRAPH)
        self.assertNotIn("analysis_bundle.json", bundle.ARTIFACT_DEPENDENCY_GRAPH)


class VerifyManifestChecksumDependencyTests(unittest.TestCase):
    """Mục 4 'checksum dependency': verify_manifest() phát hiện khi file nguồn đã đổi kể từ khi
    manifest được ghi."""

    def test_no_drift_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.csv"
            src.write_text("version-1")
            manifest_path = root / "bundle_manifest.json"
            manifest_path.write_text(json.dumps(
                {"files": [{"file": "source.csv", "sha256": bundle.sha256_file(src), "exists": True}]}))
            self.assertEqual(bundle.verify_manifest(manifest_path, root), [])

    def test_detects_sha256_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.csv"
            src.write_text("version-1")
            manifest_path = root / "bundle_manifest.json"
            manifest_path.write_text(json.dumps(
                {"files": [{"file": "source.csv", "sha256": bundle.sha256_file(src), "exists": True}]}))
            src.write_text("version-2-changed")
            mismatches = bundle.verify_manifest(manifest_path, root)
            self.assertEqual(len(mismatches), 1)
            self.assertEqual(mismatches[0]["issue"], "sha256_changed")

    def test_detects_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "bundle_manifest.json"
            manifest_path.write_text(json.dumps(
                {"files": [{"file": "gone.csv", "sha256": "deadbeef", "exists": True}]}))
            mismatches = bundle.verify_manifest(manifest_path, root)
            self.assertEqual(mismatches[0]["issue"], "file_no_longer_exists")


class AnalysisBundleIntegrationTests(unittest.TestCase):
    """Mục 1-2: analysis_bundle.json phải gộp market breadth + macro + context package +
    provenance + data_quality_flags cho các mã mặc định."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.out_dir = Path(cls.tmpdir.name)
        cls.returncode = run_bundle_main(["--allow-stale"], cls.out_dir)
        with (cls.out_dir / "analysis_bundle.json").open(encoding="utf-8") as f:
            cls.bundle = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_run_succeeds(self):
        self.assertEqual(self.returncode, 0)

    def test_contains_market_breadth_and_macro_snapshot(self):
        self.assertIsInstance(self.bundle["market_breadth"], list)
        self.assertGreater(len(self.bundle["market_breadth"]), 0)
        self.assertIsInstance(self.bundle["macro_snapshot"], dict)
        self.assertGreater(len(self.bundle["macro_snapshot"]), 0)

    def test_each_ticker_has_canonical_rs_rating_and_context_package_slot(self):
        for tk in bundle.DEFAULT_TICKERS:
            entry = self.bundle["tickers"][tk]
            self.assertIn("canonical_rs_rating", entry)
            self.assertIn("rs_rating_reconciliation", entry)
            self.assertIn("context_package", entry)   # key luôn có mặt, giá trị có thể None
            self.assertIn("financial_latest_quality", entry)

    def test_has_provenance_and_data_quality_flags(self):
        self.assertIsInstance(self.bundle["provenance"], list)
        self.assertGreater(len(self.bundle["provenance"]), 0)
        self.assertIsInstance(self.bundle["data_quality_flags"], list)

    def test_manifest_registers_both_outputs(self):
        with (self.out_dir / "bundle_manifest.json").open(encoding="utf-8") as f:
            manifest = json.load(f)
        files = {f["file"] for f in manifest["files"]}
        self.assertIn("focus_extract.json", files)
        self.assertIn("analysis_bundle.json", files)

    def test_data_quality_flags_have_full_contract_shape(self):
        # item F: every flag must carry code/severity/scope/ticker/metric/message/evidence/
        # consumer_action — not just the legacy scope/ticker/code/severity/detail shape.
        self.assertGreater(len(self.bundle["data_quality_flags"]), 0)
        for flag in self.bundle["data_quality_flags"]:
            for key in ("code", "severity", "scope", "ticker", "metric", "message", "evidence", "consumer_action"):
                self.assertIn(key, flag)
            self.assertEqual(flag["message"], flag["detail"])
            self.assertIn(flag["severity"], ("error", "warning", "info"))

    def test_hpg_material_share_mismatch_is_promoted_to_root_flags(self):
        # item F/D: HPG's real share_reconciliation.material_warning (context package) must
        # reach root data_quality_flags — this was empty before the promotion fix.
        codes_for_hpg = [
            f["code"] for f in self.bundle["data_quality_flags"] if f["ticker"] == "HPG"
        ]
        self.assertIn("share_count_material_mismatch", codes_for_hpg)

    def test_manifest_financial_snapshot_entry_carries_new_date_fields(self):
        # item G: the fields load_financial_latest() computes must actually reach the
        # bundle_manifest.json output via build_manifest_files() — a prior version of this
        # fix computed the fields correctly but build_manifest_files() silently dropped them
        # (it constructs its own dict literal from an explicit key allowlist).
        with (self.out_dir / "bundle_manifest.json").open(encoding="utf-8") as f:
            manifest = json.load(f)
        entry = next(f for f in manifest["files"] if f["file"] == "financial_snapshot.parquet")
        for field in (
            "latest_verified_calendar_end", "latest_raw_fiscal_label",
            "verified_period_count", "unverified_period_count", "future_relative_to_calendar_count",
        ):
            self.assertIn(field, entry)
        self.assertEqual(entry["data_date"], entry["latest_verified_calendar_end"])
        if entry["data_date"] is not None:
            self.assertRegex(entry["data_date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_macro_snapshot_carries_per_series_freshness(self):
        # item H: macro_snapshot.csv (what this bundle actually loads) must carry each
        # series' own freshness — not a single file-wide verdict.
        macro = self.bundle["macro_snapshot"]
        self.assertGreater(len(macro), 0)
        for series, entry in macro.items():
            for field in ("freshness_status", "age_days", "expected_frequency", "as_of"):
                self.assertIn(field, entry, f"{series} missing {field}")
            self.assertIn(entry["freshness_status"], ("current", "stale", "unknown"))

    def test_not_applicable_metrics_are_never_promoted_to_flags(self):
        # not_applicable is a confirmed, non-problematic status by contract — must never appear
        # as a data-quality flag (would be noise, and self-contradictory with its own meaning).
        for flag in self.bundle["data_quality_flags"]:
            evidence = flag.get("evidence")
            if isinstance(evidence, dict):
                self.assertNotEqual(evidence.get("status"), "not_applicable", flag)


class IntrinsicValuationEntityTypeWiringTests(unittest.TestCase):
    """build_ticker_entry's evaluate_intrinsic_valuation call must pass entity_type through
    (mirroring the relative_valuation/fundamental_quality calls a few lines away) so a bank's
    Net-Net/FCFF report inapplicable, not unavailable -- previously this key was omitted, so
    entity_type always resolved to "unknown" inside intrinsic_valuation.py regardless of the
    ticker's real registry classification."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.out_dir = Path(cls.tmpdir.name)
        cls.returncode = run_bundle_main(["--tickers", "VCB,HPG", "--allow-stale"], cls.out_dir)
        with (cls.out_dir / "analysis_bundle.json").open(encoding="utf-8") as f:
            cls.bundle = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_bank_entity_type_reaches_intrinsic_valuation(self):
        methods = self.bundle["tickers"]["VCB"]["intrinsic_valuation"]["methods"]
        self.assertEqual(methods["net_net"]["state"], "inapplicable")
        self.assertEqual(methods["fcff_dcf"]["state"], "inapplicable")

    def test_corporate_entity_type_unaffected(self):
        # HPG is entity_type=corporate: passing entity_type through must not change its
        # pre-existing, already-qualified applicability at all.
        methods = self.bundle["tickers"]["HPG"]["intrinsic_valuation"]["methods"]
        self.assertNotEqual(methods["net_net"]["state"], "inapplicable")
        self.assertNotEqual(methods["fcff_dcf"]["state"], "inapplicable")


class FiscalPeriodQualityIntegrationTests(unittest.TestCase):
    """Mục 6 (phía consumer): load_financial_latest() phải khai has_fiscal_period_flag và luôn có
    excluded_unverified_periods (danh sách rỗng nếu financial_snapshot.parquet hiện hành chưa có
    cột fiscal_period_status — tương thích ngược, xem docstring load_financial_latest)."""

    def test_load_financial_latest_reports_fiscal_flag_presence(self):
        by_ticker, info = bundle.load_financial_latest(bundle.DEFAULT_TICKERS)
        self.assertIn("has_fiscal_period_flag", info)
        for tk in bundle.DEFAULT_TICKERS:
            self.assertIn("excluded_unverified_periods", by_ticker[tk])

    def test_data_date_is_never_a_raw_fiscal_label(self):
        # item G, Data Contract Hardening v1.1: data_date must be a real calendar-verified
        # date (or None) — never the max raw "YYYY-Qn"/"YYYY" label across the whole snapshot
        # (the exact "2026-Q4 used as a financial date" trap).
        _, info = bundle.load_financial_latest(bundle.DEFAULT_TICKERS)
        for field in (
            "latest_verified_calendar_end", "latest_raw_fiscal_label",
            "verified_period_count", "unverified_period_count", "future_relative_to_calendar_count",
        ):
            self.assertIn(field, info)
        self.assertEqual(info["data_date"], info["latest_verified_calendar_end"])
        if info["data_date"] is not None:
            self.assertRegex(info["data_date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertNotRegex(str(info["data_date"]), r"^\d{4}-Q[1-4]$")


REQUIRED_LANE_FIELDS = {
    "lane", "status", "eligible", "blocking_reasons", "data_warnings",
    "required_evidence", "supporting_paths", "limitations", "is_actionable",
}
EXPECTED_LANE_ORDER = [
    "quality_growth", "income_defensive", "structural_catalyst", "distressed_high_risk", "blocked_avoid",
]

_VERIFIED_BASIS = {
    "price_basis": "raw", "price_basis_verified": True,
    "volume_basis": "raw", "volume_basis_verified": True, "is_actionable": False,
}
_UNKNOWN_BASIS = {
    "price_basis": "unknown", "price_basis_verified": False,
    "volume_basis": "unknown", "volume_basis_verified": False, "is_actionable": False,
}


class AnalysisLaneEligibilityUnitTests(unittest.TestCase):
    """Phase 5A opt-in wiring: build_analysis_lane_eligibility_for_ticker() /
    attach_analysis_lane_eligibility(). Pure synthetic-dict unit tests -- no real data,
    no DB, no CLI -- proving the wiring layer itself (not re-testing
    analysis_lane_eligibility.py's own already-committed gate logic)."""

    def _entry(self, **overrides) -> dict:
        entry = {
            "entity_type": "corporate",
            "financial_period_coverage": {"coverage_status": "verified_only", "latest_verified_period": "2026-Q1"},
            "earnings_anomaly": {"status": "not_observed", "explanation_status": "not_applicable"},
            "valuation_namespaces": None,
            "share_basis_identities": None,
            "opportunity_ranking": {"dimensions": {"financial_quality": {"state": "available"}}},
            "ta_signal_semantics": None,
            "news_related": None,
            "analysis_score": {"risk_semantics": None},
        }
        entry.update(overrides)
        return entry

    def test_enabled_result_preserves_all_lane_fields_and_ordering(self):
        result = bundle.build_analysis_lane_eligibility_for_ticker("HPG", self._entry(), _VERIFIED_BASIS)
        self.assertIsInstance(result, list)
        self.assertEqual([r["lane"] for r in result], EXPECTED_LANE_ORDER)
        for lane_result in result:
            self.assertEqual(set(lane_result.keys()), REQUIRED_LANE_FIELDS)

    def test_all_emitted_lanes_remain_non_actionable(self):
        result = bundle.build_analysis_lane_eligibility_for_ticker("HPG", self._entry(), _VERIFIED_BASIS)
        for lane_result in result:
            self.assertIs(lane_result["is_actionable"], False)

    def test_bundle_level_price_and_volume_basis_reach_the_evaluator(self):
        verified = bundle.build_analysis_lane_eligibility_for_ticker("HPG", self._entry(), _VERIFIED_BASIS)
        unverified = bundle.build_analysis_lane_eligibility_for_ticker("HPG", self._entry(), _UNKNOWN_BASIS)
        verified_warnings = " ".join(w for r in verified for w in r["data_warnings"])
        unverified_warnings = " ".join(w for r in unverified for w in r["data_warnings"])
        self.assertNotIn("adjusted_return_claims_blocked", verified_warnings)
        self.assertIn("adjusted_return_claims_blocked", unverified_warnings)

    def test_no_score_ranking_recommendation_scenario_or_target_price_introduced(self):
        result = bundle.build_analysis_lane_eligibility_for_ticker("HPG", self._entry(), _VERIFIED_BASIS)
        for lane_result in result:
            for forbidden in ("score", "rank", "recommendation", "scenario", "target_price", "preferred"):
                self.assertNotIn(forbidden, lane_result)

    def test_malformed_optional_ticker_contract_fails_closed_locally(self):
        entry = self._entry(financial_period_coverage="not_a_dict")
        result = bundle.build_analysis_lane_eligibility_for_ticker("HPG", entry, _VERIFIED_BASIS)
        self.assertIsInstance(result, list)  # analysis_lane_eligibility.py itself fails closed per-lane, not per-call
        quality_growth = next(r for r in result if r["lane"] == "quality_growth")
        self.assertEqual(quality_growth["status"], "blocked")

    def test_local_evaluator_exception_fails_closed_without_corrupting_other_tickers(self):
        """A hard exception during one ticker's evaluation must be swallowed by the wiring
        layer (return None, no key attached) and must not affect any other ticker's entry."""
        bundle_entries = {
            "BROKEN": self._entry(),
            "HPG": self._entry(),
        }
        original = bundle.evaluate_ticker_lanes

        def _raising(ticker, **kwargs):
            if ticker == "BROKEN":
                raise RuntimeError("simulated evaluator failure")
            return original(ticker, **kwargs)

        with mock.patch.object(bundle, "evaluate_ticker_lanes", side_effect=_raising):
            bundle.attach_analysis_lane_eligibility(bundle_entries, _VERIFIED_BASIS, include=True)

        self.assertNotIn("analysis_lane_eligibility", bundle_entries["BROKEN"])
        self.assertIn("analysis_lane_eligibility", bundle_entries["HPG"])
        self.assertEqual(
            [r["lane"] for r in bundle_entries["HPG"]["analysis_lane_eligibility"]], EXPECTED_LANE_ORDER,
        )

    def test_disabled_include_never_calls_evaluator_or_attaches_field(self):
        bundle_entries = {"HPG": self._entry()}
        with mock.patch.object(bundle, "evaluate_ticker_lanes") as mocked:
            bundle.attach_analysis_lane_eligibility(bundle_entries, _VERIFIED_BASIS, include=False)
        mocked.assert_not_called()
        self.assertNotIn("analysis_lane_eligibility", bundle_entries["HPG"])


class AnalysisLaneEligibilityPipelineIntegrationTests(unittest.TestCase):
    """Phase 5A opt-in wiring exercised through the real export_ai_bundle.main() pipeline
    against real retained data (same convention as the rest of this file) -- proves the
    default-disabled/enabled behavior and end-to-end determinism, not just the unit layer."""

    FIXED_EVALUATION_AT = "2026-08-01T00:00:00+00:00"

    def _run(self, extra_argv: list[str]) -> tuple[int, Path, dict]:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        out_dir = Path(tmpdir.name)
        rc = run_bundle_main(["--tickers", "HPG", "--allow-stale", *extra_argv], out_dir)
        with (out_dir / "analysis_bundle.json").open(encoding="utf-8") as f:
            data = json.load(f)
        return rc, out_dir, data

    def test_default_disabled_output_has_no_analysis_lane_eligibility(self):
        rc, _, data = self._run([])
        self.assertEqual(rc, 0)
        self.assertNotIn("analysis_lane_eligibility", data["tickers"]["HPG"])

    def test_enabled_flag_produces_complete_five_lane_result_for_real_ticker(self):
        rc, _, data = self._run(["--include-analysis-lane-eligibility"])
        self.assertEqual(rc, 0)
        result = data["tickers"]["HPG"]["analysis_lane_eligibility"]
        self.assertEqual([r["lane"] for r in result], EXPECTED_LANE_ORDER)
        for lane_result in result:
            self.assertEqual(set(lane_result.keys()), REQUIRED_LANE_FIELDS)
            self.assertIs(lane_result["is_actionable"], False)

    def test_existing_ticker_contracts_unchanged_between_disabled_and_enabled_runs(self):
        _, _, disabled = self._run(["--evaluation-at", self.FIXED_EVALUATION_AT])
        _, _, enabled = self._run(["--evaluation-at", self.FIXED_EVALUATION_AT, "--include-analysis-lane-eligibility"])
        disabled_hpg = dict(disabled["tickers"]["HPG"])
        enabled_hpg = dict(enabled["tickers"]["HPG"])
        enabled_hpg.pop("analysis_lane_eligibility", None)
        self.assertEqual(disabled_hpg, enabled_hpg)

    def test_repeated_fixed_time_enabled_builds_are_deterministic(self):
        _, _, first = self._run(["--evaluation-at", self.FIXED_EVALUATION_AT, "--include-analysis-lane-eligibility"])
        _, _, second = self._run(["--evaluation-at", self.FIXED_EVALUATION_AT, "--include-analysis-lane-eligibility"])
        self.assertEqual(
            first["tickers"]["HPG"]["analysis_lane_eligibility"],
            second["tickers"]["HPG"]["analysis_lane_eligibility"],
        )


if __name__ == "__main__":
    unittest.main()
