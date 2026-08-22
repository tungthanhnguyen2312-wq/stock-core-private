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


def sample_canonical_packet() -> dict:
    """Build a deterministic synthetic multi-source session packet."""
    return {
        "packet_schema_version": "1.0.0",
        "contract_version": "capability_first_eod_collector/v1",
        "session_date": "2026-08-20",
        "created_at": "2026-08-20T18:05:00.000Z",
        "execution_mode": "SYNTHETIC_TEST",
        "request_budget": {
            "max_requests": 50,
            "used_requests": 8,
            "rate_limited_requests": 1,
            "budget_exhausted": False,
            "planned_requests_count": 8,
        },
        "source_routing": {
            "routed_capabilities": {},
            "single_source_capabilities": ["PUT_THROUGH_VOLUME_SHARES", "MATCHED_TRADED_VALUE_VND"],
            "missing_capabilities": ["FREE_FLOAT"],
        },
        "rate_limit_events": [],
        "revision_events": [],
        "observations": [
            # 1. HPG DNSE OHLC
            {
                "session": "2026-08-20",
                "instrument": "HPG",
                "source": "DNSE",
                "endpoint_id": "ohlc",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "revision_state": "INITIAL_OBSERVATION",
                "raw_response_retained": True,
                "raw_path": "raw/dnse_ohlc_HPG_11111111.json",
                "raw_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
                "native_fields": {
                    "OPEN_KVND": {"value": "21.5", "unit": "thousands_of_vnd_per_share", "raw_field": "o"},
                    "HIGH_KVND": {"value": "22.0", "unit": "thousands_of_vnd_per_share", "raw_field": "h"},
                    "LOW_KVND": {"value": "21.3", "unit": "thousands_of_vnd_per_share", "raw_field": "l"},
                    "CLOSE_KVND": {"value": "21.85", "unit": "thousands_of_vnd_per_share", "raw_field": "c"},
                    "MATCHED_VOLUME_SHARES": {"value": 2500000, "unit": "shares", "raw_field": "v"},
                },
                "canonical_fields": {
                    "OPEN_VND": {
                        "value": "21500",
                        "unit": "vnd_per_share",
                        "derived_from": "OPEN_KVND",
                        "contract_id": "DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1",
                    },
                    "HIGH_VND": {
                        "value": "22000",
                        "unit": "vnd_per_share",
                        "derived_from": "HIGH_KVND",
                        "contract_id": "DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1",
                    },
                    "LOW_VND": {
                        "value": "21300",
                        "unit": "vnd_per_share",
                        "derived_from": "LOW_KVND",
                        "contract_id": "DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1",
                    },
                    "CLOSE_VND": {
                        "value": "21850",
                        "unit": "vnd_per_share",
                        "derived_from": "CLOSE_KVND",
                        "contract_id": "DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1",
                    },
                    "MATCHED_VOLUME_SHARES": {
                        "value": 2500000,
                        "unit": "shares",
                    },
                },
                "authority_effect": "NONE",
            },
            # 2. HPG FHSC Trading History (volume + traded value)
            {
                "session": "2026-08-20",
                "instrument": "HPG",
                "source": "FHSC",
                "endpoint_id": "trading_history",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "revision_state": "INITIAL_OBSERVATION",
                "raw_response_retained": True,
                "raw_path": "raw/fhsc_trading_history_HPG_22222222.json",
                "raw_sha256": "2222222222222222222222222222222222222222222222222222222222222222",
                "native_fields": {
                    "MATCHED_VOLUME_SHARES": {"value": 2200000, "unit": "shares"},
                    "PUT_THROUGH_VOLUME_SHARES": {"value": 300000, "unit": "shares"},
                    "TOTAL_VOLUME_SHARES": {"value": 2500000, "unit": "shares"},
                    "MATCHED_TRADED_VALUE_VND": {"value": 47300000000, "unit": "vnd"},
                    "PUT_THROUGH_TRADED_VALUE_VND": {"value": 6450000000, "unit": "vnd"},
                    "TOTAL_TRADED_VALUE_VND": {"value": 53750000000, "unit": "vnd"},
                },
                "canonical_fields": {
                    "MATCHED_VOLUME_SHARES": {"value": 2200000, "unit": "shares"},
                    "PUT_THROUGH_VOLUME_SHARES": {"value": 300000, "unit": "shares"},
                    "TOTAL_VOLUME_SHARES": {"value": 2500000, "unit": "shares"},
                    "MATCHED_TRADED_VALUE_VND": {"value": 47300000000, "unit": "vnd_raw_not_thousands"},
                    "PUT_THROUGH_TRADED_VALUE_VND": {"value": 6450000000, "unit": "vnd_raw_not_thousands"},
                    "TOTAL_TRADED_VALUE_VND": {"value": 53750000000, "unit": "vnd_raw_not_thousands"},
                },
                "authority_effect": "NONE",
            },
            # 3. HPG FHSC Foreign Room
            {
                "session": "2026-08-20",
                "instrument": "HPG",
                "source": "FHSC",
                "endpoint_id": "foreign_room",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "raw_response_retained": True,
                "raw_path": "raw/fhsc_foreign_room_HPG_33333333.json",
                "raw_sha256": "3333333333333333333333333333333333333333333333333333333333333333",
                "native_fields": {
                    "FOREIGN_ROOM_MAX": {"value": 2089955445, "unit": "shares"},
                    "FOREIGN_ROOM_OWNED": {"value": 1969955445, "unit": "shares"},
                    "FOREIGN_ROOM_AVAILABLE": {"value": 120000000, "unit": "shares"},
                },
                "canonical_fields": {
                    "FOREIGN_ROOM_MAX": {"value": 2089955445, "unit": "shares"},
                    "FOREIGN_ROOM_OWNED": {"value": 1969955445, "unit": "shares"},
                    "FOREIGN_ROOM_AVAILABLE": {"value": 120000000, "unit": "shares"},
                },
                "authority_effect": "NONE",
            },
            # 4. HPG FHSC Proprietary Trading
            {
                "session": "2026-08-20",
                "instrument": "HPG",
                "source": "FHSC",
                "endpoint_id": "proprietary_trading",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "raw_response_retained": True,
                "raw_path": "raw/fhsc_proprietary_HPG_44444444.json",
                "raw_sha256": "4444444444444444444444444444444444444444444444444444444444444444",
                "native_fields": {
                    "PROPRIETARY_BUY_VOLUME": {"value": 850000, "unit": "shares"},
                    "PROPRIETARY_SELL_VOLUME": {"value": 320000, "unit": "shares"},
                    "PROPRIETARY_NET_VOLUME": {"value": 530000, "unit": "shares"},
                    "PROPRIETARY_BUY_VALUE": {"value": 18275000000, "unit": "vnd"},
                    "PROPRIETARY_SELL_VALUE": {"value": 6880000000, "unit": "vnd"},
                    "PROPRIETARY_NET_VALUE": {"value": 11395000000, "unit": "vnd"},
                },
                "canonical_fields": {
                    "PROPRIETARY_BUY_VOLUME": {"value": 850000, "unit": "shares"},
                    "PROPRIETARY_SELL_VOLUME": {"value": 320000, "unit": "shares"},
                    "PROPRIETARY_NET_VOLUME": {"value": 530000, "unit": "shares"},
                    "PROPRIETARY_BUY_VALUE": {"value": 18275000000, "unit": "vnd_raw_not_thousands"},
                    "PROPRIETARY_SELL_VALUE": {"value": 6880000000, "unit": "vnd_raw_not_thousands"},
                    "PROPRIETARY_NET_VALUE": {"value": 11395000000, "unit": "vnd_raw_not_thousands"},
                },
                "authority_effect": "NONE",
            },
            # 5. HPG FHSC Order Statistics
            {
                "session": "2026-08-20",
                "instrument": "HPG",
                "source": "FHSC",
                "endpoint_id": "order_statistics",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "raw_response_retained": True,
                "raw_path": "raw/fhsc_orders_HPG_55555555.json",
                "raw_sha256": "5555555555555555555555555555555555555555555555555555555555555555",
                "native_fields": {
                    "ACTIVE_BUY_ORDER_COUNT": {"value": 18422, "unit": "orders"},
                    "ACTIVE_SELL_ORDER_COUNT": {"value": 14205, "unit": "orders"},
                    "ACTIVE_BUY_VOLUME": {"value": 9871300, "unit": "shares"},
                    "ACTIVE_SELL_VOLUME": {"value": 5285100, "unit": "shares"},
                    "ACTIVE_NET_VOLUME": {"value": 4586200, "unit": "shares"},
                },
                "canonical_fields": {
                    "ACTIVE_BUY_ORDER_COUNT": {"value": 18422, "unit": "orders"},
                    "ACTIVE_SELL_ORDER_COUNT": {"value": 14205, "unit": "orders"},
                    "ACTIVE_BUY_VOLUME": {"value": 9871300, "unit": "shares"},
                    "ACTIVE_SELL_VOLUME": {"value": 5285100, "unit": "shares"},
                    "ACTIVE_NET_VOLUME": {"value": 4586200, "unit": "shares"},
                },
                "authority_effect": "NONE",
            },
            # 6. VCB Missing Requested Session
            {
                "session": "2026-08-20",
                "instrument": "VCB",
                "source": "DNSE",
                "endpoint_id": "ohlc",
                "status": "MISSING_REQUESTED_SESSION",
                "usability_state": "MISSING",
                "raw_response_retained": False,
                "authority_effect": "NONE",
            },
            # 7. SSI Provider Rate Limited (DNSE) & Budget Exhausted (FHSC)
            {
                "session": "2026-08-20",
                "instrument": "SSI",
                "source": "DNSE",
                "endpoint_id": "ohlc",
                "status": "PROVIDER_RATE_LIMITED",
                "usability_state": "PROVIDER_RATE_LIMITED",
                "raw_response_retained": False,
            },
            {
                "session": "2026-08-20",
                "instrument": "SSI",
                "source": "FHSC",
                "endpoint_id": "trading_history",
                "status": "BUDGET_EXHAUSTED",
                "usability_state": "BUDGET_EXHAUSTED",
                "raw_response_retained": False,
            },
            # 8. VNM Conflicting volume arithmetic
            {
                "session": "2026-08-20",
                "instrument": "VNM",
                "source": "FHSC",
                "endpoint_id": "trading_history",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "raw_response_retained": True,
                "raw_path": "raw/conflict_vnm.json",
                "raw_sha256": "vnm_conflict_sha",
                "native_fields": {
                    "MATCHED_VOLUME_SHARES": {"value": 2000000, "unit": "shares"},
                    "PUT_THROUGH_VOLUME_SHARES": {"value": 300000, "unit": "shares"},
                    "TOTAL_VOLUME_SHARES": {"value": 10000000, "unit": "shares"},
                },
                "canonical_fields": {
                    "TOTAL_VOLUME_SHARES": {"value": 10000000, "unit": "shares"},
                },
            },
        ],
        "authority_boundaries": {
            "authority_effect": "NONE",
            "raw_as_traded_promoted": False,
            "pit_backtest_eligible": False,
            "liquidity_sizing_authority": "BLOCKED",
            "valuation_authority": False,
            "recommendation_authority": False,
            "database_mutated": False,
        },
        "packet_sha256": "8888888888888888888888888888888888888888888888888888888888888888",
        "packet_identity": "capability_first_eod_packet:8888888888888888888888888888888888888888888888888888888888888888",
    }


class CanonicalIntegrationConsumerActivationTests(unittest.TestCase):
    """Validation test suite proving consumer activation on capability-first canonical integration."""

    def setUp(self):
        self.packet = sample_canonical_packet()
        self.artifact = build_market_research_artifact(
            canonical_session_packet=self.packet,
            permitted_use="within_series_analytics",
            reference_at="2026-08-20T18:05:00+07:00",
        )

    # 1. DNSE canonical price reaches the consumer with native/canonical lineage intact
    def test_dnse_canonical_price_reaches_consumer_with_lineage(self):
        hpg_rec = next(r for r in self.artifact["records"] if r["instrument_identity"]["symbol"] == "HPG")
        evidence = hpg_rec["canonical_market_evidence"]
        self.assertIn("DNSE", evidence["prices"])
        dnse_prices = evidence["prices"]["DNSE"]

        close_entry = dnse_prices["CLOSE_VND"]
        self.assertEqual("21850", close_entry["value"])
        self.assertEqual("vnd_per_share", close_entry["unit"])
        self.assertEqual("21.85", close_entry["provider_native_value"])
        self.assertEqual("thousands_of_vnd_per_share", close_entry["provider_native_unit"])
        self.assertEqual("DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1", close_entry["contract_id"])
        self.assertEqual("1111111111111111111111111111111111111111111111111111111111111111", close_entry["raw_sha256"])

    # 2. FHSC-only capability reaches the same consumer without DNSE parity
    def test_fhsc_only_capability_reaches_consumer_without_dnse_parity(self):
        hpg_rec = next(r for r in self.artifact["records"] if r["instrument_identity"]["symbol"] == "HPG")
        evidence = hpg_rec["canonical_market_evidence"]

        # Traded values & foreign room are FHSC-only
        self.assertIn("FHSC", evidence["traded_values"])
        self.assertNotIn("DNSE", evidence["traded_values"])
        self.assertIn("FHSC", evidence["foreign_room"])
        self.assertNotIn("DNSE", evidence["foreign_room"])

        self.assertEqual(53750000000, evidence["traded_values"]["FHSC"]["TOTAL_TRADED_VALUE_VND"]["value"])
        self.assertEqual(2089955445, evidence["foreign_room"]["FHSC"]["FOREIGN_ROOM_MAX"]["value"])

    # 3. Traded-value identities remain distinct
    def test_traded_value_identities_remain_distinct(self):
        hpg_rec = next(r for r in self.artifact["records"] if r["instrument_identity"]["symbol"] == "HPG")
        tv = hpg_rec["canonical_market_evidence"]["traded_values"]["FHSC"]

        m_val = tv["MATCHED_TRADED_VALUE_VND"]["value"]
        pt_val = tv["PUT_THROUGH_TRADED_VALUE_VND"]["value"]
        tot_val = tv["TOTAL_TRADED_VALUE_VND"]["value"]

        self.assertNotEqual(m_val, tot_val)
        self.assertNotEqual(pt_val, tot_val)
        self.assertEqual(m_val + pt_val, tot_val)
        self.assertEqual("vnd_raw_not_thousands", tv["TOTAL_TRADED_VALUE_VND"]["unit"])

    # 4. Proprietary and microstructure data is not mislabeled as total market volume
    def test_proprietary_and_microstructure_data_not_mislabeled_as_total_volume(self):
        hpg_rec = next(r for r in self.artifact["records"] if r["instrument_identity"]["symbol"] == "HPG")
        evidence = hpg_rec["canonical_market_evidence"]

        # Check proprietary flow is distinct
        self.assertIn("FHSC", evidence["proprietary_flow"])
        prop = evidence["proprietary_flow"]["FHSC"]
        self.assertEqual(530000, prop["PROPRIETARY_NET_VOLUME"]["value"])
        self.assertEqual("shares", prop["PROPRIETARY_NET_VOLUME"]["unit"])

        # Check microstructure is distinct
        self.assertIn("FHSC", evidence["microstructure"])
        micro = evidence["microstructure"]["FHSC"]
        self.assertEqual(18422, micro["ACTIVE_BUY_ORDER_COUNT"]["value"])
        self.assertEqual(4586200, micro["ACTIVE_NET_VOLUME"]["value"])

        # Verify active volume is NOT present in canonical_volumes
        vols = evidence["volumes"]["FHSC"]
        self.assertNotIn("ACTIVE_NET_VOLUME", vols)
        self.assertNotIn("PROPRIETARY_NET_VOLUME", vols)

    # 5. Missing requested session produces no fabricated feature
    def test_missing_requested_session_produces_no_fabricated_feature(self):
        vcb_rec = next(r for r in self.artifact["records"] if r["instrument_identity"]["symbol"] == "VCB")
        evidence = vcb_rec["canonical_market_evidence"]

        # No fabricated prices
        self.assertEqual({}, evidence["prices"])
        self.assertEqual({}, evidence["volumes"])

        # Recorded under unacquired capabilities
        unacquired = evidence["unacquired_capabilities"]
        self.assertEqual(1, len(unacquired))
        self.assertEqual("MISSING_REQUESTED_SESSION", unacquired[0]["status"])

    # 6. Conflicting observation remains non-usable for affected research output
    def test_conflicting_observation_fails_closed_for_affected_research(self):
        vnm_rec = next(r for r in self.artifact["records"] if r["instrument_identity"]["symbol"] == "VNM")
        evidence = vnm_rec["canonical_market_evidence"]

        # Recorded under conflicts
        self.assertTrue(len(evidence["conflicts"]) >= 1)
        self.assertEqual("CONFLICTING_VOLUME_ARITHMETIC", evidence["conflicts"][0]["conflict_state"])

        # Value withheld (None) for research display/analytics
        tot_vol_entry = evidence["volumes"]["FHSC"]["TOTAL_VOLUME_SHARES"]
        self.assertIsNone(tot_vol_entry["value"])
        self.assertFalse(tot_vol_entry["is_usable"])

    # 7. Provider-rate-limit and local-budget exhaustion remain distinguishable
    def test_rate_limit_and_budget_exhaustion_distinguishable(self):
        ssi_rec = next(r for r in self.artifact["records"] if r["instrument_identity"]["symbol"] == "SSI")
        evidence = ssi_rec["canonical_market_evidence"]

        unacquired = evidence["unacquired_capabilities"]
        statuses = {u["source"]: u["status"] for u in unacquired}

        self.assertEqual("PROVIDER_RATE_LIMITED", statuses["DNSE"])
        self.assertEqual("BUDGET_EXHAUSTED", statuses["FHSC"])
        self.assertNotEqual(statuses["DNSE"], statuses["FHSC"])

    # 8. Prohibited liquidity/sizing/PIT/valuation/recommendation requests fail closed
    def test_prohibited_uses_fail_closed(self):
        prohibited_uses = ("liquidity_sizing", "valuation", "raw_as_traded_pit_backtest", "recommendation_authority")
        for prohibited in prohibited_uses:
            art = build_market_research_artifact(
                canonical_session_packet=self.packet,
                permitted_use=prohibited,
            )
            self.assertEqual("PROHIBITED_USE_REJECTED", art["status"])
            self.assertFalse(art["is_actionable"])
            self.assertEqual("NONE", art["authority_effect"])
            self.assertEqual(0, len(art["records"]))

    # 9. Deterministic replay produces identical consumer artifact identity
    def test_deterministic_replay_produces_identical_artifact_identity(self):
        art1 = build_market_research_artifact(
            canonical_session_packet=self.packet,
            permitted_use="within_series_analytics",
            reference_at="2026-08-20T18:05:00+07:00",
        )
        art2 = build_market_research_artifact(
            canonical_session_packet=self.packet,
            permitted_use="within_series_analytics",
            reference_at="2026-08-20T18:05:00+07:00",
        )

        self.assertEqual(art1["content_hash"], art2["content_hash"])
        self.assertEqual(art1["artifact_id"], art2["artifact_id"])
        self.assertEqual(len(art1["records"]), len(art2["records"]))

    # 10. No secret material appears in artifact output
    def test_no_secret_leakage_in_artifact(self):
        import json
        dumped = json.dumps(self.artifact)
        sensitive_patterns = ("api_key", "x-fh-apikey", "authorization", "secret", "passwd")
        for pat in sensitive_patterns:
            self.assertNotIn(pat, dumped.lower())


if __name__ == "__main__":
    unittest.main()
