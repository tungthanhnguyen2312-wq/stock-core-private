from __future__ import annotations

import unittest
from datetime import datetime, timezone

import pandas as pd

from canonical_universe_tiers import INCLUDED, UNKNOWN, EXCLUDED
from field_temporal_contract import FreshnessState, PitStatus
from market_data_contracts import PriceBasis
from market_analysis_artifact import (
    ARTIFACT_TYPE,
    UNIVERSE_TYPE,
    build_market_research_artifact,
    evaluate_universe_membership,
    normalize_candidate_identity,
)


def sample_candidates() -> list[dict]:
    return [
        {
            "candidate_id": "candidate:HPG",
            "symbol": "HPG",
            "provider_identities": ["dnse:symbol:hpg"],
            "instrument_class": "EQUITY",
            "exchange": "HOSE",
            "listing_status": "unknown_not_provided_by_dataset",
        },
        {
            "candidate_id": "candidate:VCB",
            "symbol": "VCB",
            "provider_identities": ["dnse:symbol:vcb"],
            "instrument_class": "EQUITY",
            "exchange": "HOSE",
            "listing_status": "unknown_not_provided_by_dataset",
        },
        {
            "candidate_id": "candidate:VNM",
            "symbol": "VNM",
            "provider_identities": ["dnse:symbol:vnm"],
            "instrument_class": "EQUITY",
            "exchange": "HOSE",
            "listing_status": "unknown_not_provided_by_dataset",
        },
        {
            "candidate_id": "candidate:CW1",
            "symbol": "CW1",
            "provider_identities": ["dnse:symbol:cw1"],
            "instrument_class": "WARRANT",
            "exchange": "HOSE",
            "listing_status": "unknown_not_provided_by_dataset",
        },
        {
            "candidate_id": "candidate:VN30",
            "symbol": "VN30",
            "provider_identities": ["dnse:symbol:vn30"],
            "instrument_class": "INDEX",
            "exchange": None,
            "listing_status": "unknown_not_provided_by_dataset",
        },
        {
            "candidate_id": "candidate:UNK",
            "symbol": "UNK",
            "provider_identities": ["dnse:symbol:unk"],
            "instrument_class": "UNKNOWN_SECURITY_GROUP",
            "exchange": None,
            "listing_status": "unknown_not_provided_by_dataset",
        },
    ]


def sample_market_frame() -> pd.DataFrame:
    rows = []
    dates = ["2026-08-07", "2026-08-08", "2026-08-09", "2026-08-10", "2026-08-11"]
    for d in dates:
        rows.append({"ticker": "HPG", "date": d, "open": 28.0, "high": 29.0, "low": 27.5, "close": 28.5, "volume": 1000000.0})
        rows.append({"ticker": "VCB", "date": d, "open": 88.0, "high": 90.0, "low": 87.5, "close": 89.0, "volume": 500000.0})
        rows.append({"ticker": "VNM", "date": d, "open": 65.0, "high": 66.0, "low": 64.5, "close": 65.5, "volume": 750000.0})
    return pd.DataFrame(rows)


class MarketAnalysisArtifactTests(unittest.TestCase):
    def test_artifact_deterministic_identity_and_sorting(self):
        cands = sample_candidates()
        m_frame = sample_market_frame()
        ref = "2026-08-11T16:00:00+07:00"

        art1 = build_market_research_artifact(
            candidates=cands,
            market_frame=m_frame,
            as_of_session="2026-08-11",
            reference_at=ref,
            knowledge_cutoff="2026-08-11T16:00:00+07:00",
        )
        art2 = build_market_research_artifact(
            candidates=list(reversed(cands)),  # Reversed input order
            market_frame=m_frame,
            as_of_session="2026-08-11",
            reference_at=ref,
            knowledge_cutoff="2026-08-11T16:00:00+07:00",
        )

        # Content hash and ordering must be strictly identical regardless of input order
        self.assertEqual(art1["content_hash"], art2["content_hash"])
        self.assertEqual(art1["artifact_id"], art2["artifact_id"])
        self.assertEqual([r["instrument_identity"]["symbol"] for r in art1["records"]],
                         [r["instrument_identity"]["symbol"] for r in art2["records"]])

    def test_canonical_candidate_vs_active_universe_distinction(self):
        cands = sample_candidates()
        art = build_market_research_artifact(
            candidates=cands,
            as_of_session="2026-08-11",
            reference_at="2026-08-11T16:00:00+07:00",
        )

        self.assertEqual(UNIVERSE_TYPE, art["universe_type"])
        hpg_rec = next(r for r in art["records"] if r["instrument_identity"]["symbol"] == "HPG")
        membership = hpg_rec["universe_tier_membership"]

        # CANONICAL_CANDIDATE_UNIVERSE is INCLUDED for equity
        self.assertEqual(INCLUDED, membership["canonical_candidate_universe"]["state"])
        self.assertEqual("CANONICAL_CANDIDATE_UNIVERSE_ELIGIBLE", membership["canonical_candidate_universe"]["authority_status"])

        # ACTIVE_UNIVERSE is UNKNOWN and fail-closed
        self.assertEqual(UNKNOWN, membership["active_universe"]["state"])
        self.assertEqual("FAIL_CLOSED_NO_LISTING_AUTHORITY", membership["active_universe"]["authority_status"])

    def test_unqualified_price_basis_is_not_pit_eligible(self):
        cands = sample_candidates()
        m_frame = sample_market_frame()
        art = build_market_research_artifact(
            candidates=cands,
            market_frame=m_frame,
            as_of_session="2026-08-11",
            reference_at="2026-08-11T16:00:00+07:00",
            knowledge_cutoff="2026-08-11T16:00:00+07:00",
            price_basis=PriceBasis.ADJUSTED_RETROSPECTIVE,  # Unqualified for PIT
        )

        hpg_rec = next(r for r in art["records"] if r["instrument_identity"]["symbol"] == "HPG")
        t_fields = hpg_rec["temporal_fields"]

        # Price field market.close must be marked pit_eligible=False
        close_tf = t_fields["market.close"]
        self.assertFalse(close_tf["pit_eligible"])
        self.assertEqual(PitStatus.UNQUALIFIED_PRICE_BASIS.value, close_tf["pit_status"])
        self.assertFalse(hpg_rec["capability_flags"]["pit_backtest_eligible"])

    def test_liquidity_and_sizing_strictly_fail_closed(self):
        cands = sample_candidates()
        m_frame = sample_market_frame()
        art = build_market_research_artifact(
            candidates=cands,
            market_frame=m_frame,
            as_of_session="2026-08-11",
            reference_at="2026-08-11T16:00:00+07:00",
        )

        for rec in art["records"]:
            flags = rec["capability_flags"]
            self.assertFalse(flags["market_wide_turnover_eligible"])
            self.assertFalse(flags["market_liquidity_eligible"])
            self.assertFalse(flags["execution_sizing_eligible"])

            blocked = rec["blocked_capabilities"]
            self.assertEqual("NO_MARKET_WIDE_TURNOVER_AUTHORITY", blocked["market_wide_turnover"]["reason_code"])
            self.assertEqual("LIQUIDITY_INPUTS_UNQUALIFIED", blocked["market_liquidity"]["reason_code"])
            self.assertEqual("POSITION_SIZING_PROHIBITED", blocked["execution_sizing"]["reason_code"])

    def test_one_missing_field_does_not_invalidate_entire_instrument(self):
        cands = sample_candidates()
        # Market frame with HPG and VCB only; VNM has no market data
        m_frame = sample_market_frame()
        m_frame = m_frame[m_frame["ticker"].isin(["HPG", "VCB"])].copy()

        art = build_market_research_artifact(
            candidates=cands,
            market_frame=m_frame,
            as_of_session="2026-08-11",
            reference_at="2026-08-11T16:00:00+07:00",
        )

        vnm_rec = next(r for r in art["records"] if r["instrument_identity"]["symbol"] == "VNM")

        # Record exists and is emitted
        self.assertIsNotNone(vnm_rec)
        self.assertTrue(vnm_rec["capability_flags"]["display_eligible"])
        self.assertFalse(vnm_rec["capability_flags"]["provider_scoped_analytics_eligible"])

        # Market close field is None/missing in temporal fields
        close_tf = vnm_rec["temporal_fields"]["market.close"]
        self.assertEqual(FreshnessState.MISSING.value, close_tf["freshness_status"])
        self.assertIsNone(close_tf["value"])

    def test_freshness_stays_attached_to_value(self):
        cands = sample_candidates()
        m_frame = sample_market_frame()
        # Reference is same day as as_of_session
        art = build_market_research_artifact(
            candidates=cands,
            market_frame=m_frame,
            as_of_session="2026-08-11",
            reference_at="2026-08-11T16:00:00+07:00",
        )

        hpg_rec = next(r for r in art["records"] if r["instrument_identity"]["symbol"] == "HPG")
        close_tf = hpg_rec["temporal_fields"]["market.close"]

        self.assertEqual(28.5, close_tf["value"])
        self.assertEqual(FreshnessState.CURRENT.value, close_tf["freshness_status"])
        self.assertTrue(close_tf["observed_at"].startswith("2026-08-11"))
        self.assertEqual("2026-08-11", close_tf["as_of"])
        self.assertEqual("daily_market", close_tf["domain"])

    def test_foreign_flows_composition(self):
        cands = sample_candidates()
        m_frame = sample_market_frame()
        foreign_df = pd.DataFrame([
            {"ticker": "HPG", "date": "2026-08-11", "foreign_buy_value": 50000000.0, "foreign_sell_value": 20000000.0, "foreign_net_value": 30000000.0},
            {"ticker": "VCB", "date": "2026-08-11", "foreign_buy_value": 10000000.0, "foreign_sell_value": 15000000.0, "foreign_net_value": -5000000.0},
        ])

        art = build_market_research_artifact(
            candidates=cands,
            market_frame=m_frame,
            foreign_flows_frame=foreign_df,
            as_of_session="2026-08-11",
            reference_at="2026-08-11T16:00:00+07:00",
        )

        hpg_rec = next(r for r in art["records"] if r["instrument_identity"]["symbol"] == "HPG")
        self.assertEqual(30000000.0, hpg_rec["qualified_financial_features"]["dnse.foreign_net_value"])
        self.assertEqual(30000000.0, hpg_rec["temporal_fields"]["dnse.foreign_net_value"]["value"])


if __name__ == "__main__":
    unittest.main()
