"""Comprehensive test suite for canonical_market_evidence_integration.py.

Validates all 12 core requirements and fail-closed invariants:
1. DNSE price native K-VND + canonical VND survive integration together.
2. FHSC-only capability integrates without DNSE comparator.
3. Matched / put-through / total traded values remain distinct.
4. Foreign-room identities remain distinct.
5. Proprietary and active-order semantics remain source-bound.
6. MISSING_REQUESTED_SESSION survives unchanged and creates no fact.
7. PROVIDER_RATE_LIMITED and BUDGET_EXHAUSTED remain distinct.
8. CONFLICTING observation is retained but affected use cases fail closed.
9. Same semantic from DNSE + FHSC remains two provenance-bound observations, not one averaged/synthetic value.
10. Research usability does not imply RAW_AS_TRADED, liquidity/sizing, valuation or recommendation authority.
11. Deterministic replay produces identical canonical identity/output.
12. No secret material appears in outputs/tests.
"""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from typing import Any

import canonical_market_evidence_integration as integration
from tools import collect_market_evidence as collector
import market_capability_taxonomy as taxonomy
import price_representation_contract as price_contract

MOCK_SESSION = "2026-08-20"


def _sample_packet() -> dict[str, Any]:
    """Build a deterministic synthetic multi-source session packet."""
    return {
        "packet_schema_version": "1.0.0",
        "contract_version": "capability_first_eod_collector/v1",
        "session_date": MOCK_SESSION,
        "created_at": "2026-08-20T18:05:00.000Z",
        "execution_mode": "SYNTHETIC_TEST",
        "request_budget": {
            "max_requests": 50,
            "used_requests": 6,
            "rate_limited_requests": 0,
            "budget_exhausted": False,
            "planned_requests_count": 6,
        },
        "source_routing": {
            "routed_capabilities": {},
            "single_source_capabilities": ["PUT_THROUGH_VOLUME_SHARES", "MATCHED_TRADED_VALUE_VND"],
            "missing_capabilities": ["FREE_FLOAT"],
        },
        "rate_limit_events": [],
        "revision_events": [],
        "observations": [
            # 1. DNSE OHLC observation
            {
                "session": MOCK_SESSION,
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
                        "contract_basis_tier": "owner_directed_contractual_assumption",
                    },
                    "HIGH_VND": {
                        "value": "22000",
                        "unit": "vnd_per_share",
                        "derived_from": "HIGH_KVND",
                        "contract_id": "DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1",
                        "contract_basis_tier": "owner_directed_contractual_assumption",
                    },
                    "LOW_VND": {
                        "value": "21300",
                        "unit": "vnd_per_share",
                        "derived_from": "LOW_KVND",
                        "contract_id": "DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1",
                        "contract_basis_tier": "owner_directed_contractual_assumption",
                    },
                    "CLOSE_VND": {
                        "value": "21850",
                        "unit": "vnd_per_share",
                        "derived_from": "CLOSE_KVND",
                        "contract_id": "DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1",
                        "contract_basis_tier": "owner_directed_contractual_assumption",
                    },
                    "MATCHED_VOLUME_SHARES": {
                        "value": 2500000,
                        "unit": "shares",
                        "derived_from": "MATCHED_VOLUME_SHARES",
                        "contract_id": "identity/shares",
                    },
                },
                "authority_effect": "NONE",
            },
            # 2. FHSC Volume & Traded Value observation
            {
                "session": MOCK_SESSION,
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
            # 3. FHSC Foreign Room observation
            {
                "session": MOCK_SESSION,
                "instrument": "HPG",
                "source": "FHSC",
                "endpoint_id": "foreign_room",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "revision_state": "INITIAL_OBSERVATION",
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
            # 4. FHSC Proprietary Trading observation
            {
                "session": MOCK_SESSION,
                "instrument": "HPG",
                "source": "FHSC",
                "endpoint_id": "proprietary_trading",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "revision_state": "INITIAL_OBSERVATION",
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
            # 5. FHSC Order Statistics observation
            {
                "session": MOCK_SESSION,
                "instrument": "HPG",
                "source": "FHSC",
                "endpoint_id": "order_statistics",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "revision_state": "INITIAL_OBSERVATION",
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
        "packet_sha256": "9999999999999999999999999999999999999999999999999999999999999999",
        "packet_identity": "capability_first_eod_packet:9999999999999999999999999999999999999999999999999999999999999999",
    }


class CanonicalIntegrationValidationTests(unittest.TestCase):
    """Validation test suite matching all 12 milestone requirements."""

    def setUp(self):
        self.packet = _sample_packet()
        self.integrated = integration.integrate_session_packet(self.packet)

    # 1. DNSE price native K-VND + canonical VND survive integration together
    def test_dnse_price_native_kvnd_and_canonical_vnd_survive_together(self):
        obs_list = [o for o in self.integrated["observations"] if o["source"] == "DNSE" and o["semantic_identity"] == "CLOSE_KVND"]
        self.assertEqual(1, len(obs_list))
        obs_kvnd = obs_list[0]
        self.assertEqual("21.85", obs_kvnd["provider_native_value"])
        self.assertEqual("thousands_of_vnd_per_share", obs_kvnd["provider_native_unit"])
        self.assertEqual("21850", obs_kvnd["canonical_value"])
        self.assertEqual("vnd_per_share", obs_kvnd["canonical_unit"])
        self.assertEqual("DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1", obs_kvnd["contract_id"])

    # 2. FHSC-only capability integrates without DNSE comparator
    def test_fhsc_only_capability_integrates_without_dnse_comparator(self):
        obs_list = [o for o in self.integrated["observations"] if o["semantic_identity"] == "PUT_THROUGH_VOLUME_SHARES"]
        self.assertEqual(1, len(obs_list))
        obs = obs_list[0]
        self.assertEqual("FHSC", obs["source"])
        self.assertEqual(300000, obs["canonical_value"])
        self.assertEqual("shares", obs["canonical_unit"])
        self.assertEqual("RESEARCH_USABLE", obs["usability_state"])
        self.assertTrue(obs["downstream_eligibility"][integration.USE_WITHIN_SERIES_ANALYTICS])

    # 3. Matched / put-through / total traded values remain distinct
    def test_matched_put_through_total_traded_values_remain_distinct(self):
        traded_val_obs = {
            o["semantic_identity"]: o
            for o in self.integrated["observations"]
            if o["capability_family"] == "TRADED_VALUE"
        }
        self.assertIn("MATCHED_TRADED_VALUE_VND", traded_val_obs)
        self.assertIn("PUT_THROUGH_TRADED_VALUE_VND", traded_val_obs)
        self.assertIn("TOTAL_TRADED_VALUE_VND", traded_val_obs)

        m = traded_val_obs["MATCHED_TRADED_VALUE_VND"]["canonical_value"]
        p = traded_val_obs["PUT_THROUGH_TRADED_VALUE_VND"]["canonical_value"]
        t = traded_val_obs["TOTAL_TRADED_VALUE_VND"]["canonical_value"]

        self.assertNotEqual(m, t)
        self.assertNotEqual(p, t)
        self.assertEqual(m + p, t)
        self.assertEqual("vnd_raw_not_thousands", traded_val_obs["TOTAL_TRADED_VALUE_VND"]["canonical_unit"])

    # 4. Foreign-room identities remain distinct
    def test_foreign_room_identities_remain_distinct(self):
        room_obs = {
            o["semantic_identity"]: o
            for o in self.integrated["observations"]
            if "ROOM" in o["semantic_identity"]
        }
        self.assertIn("FOREIGN_ROOM_MAX", room_obs)
        self.assertIn("FOREIGN_ROOM_OWNED", room_obs)
        self.assertIn("FOREIGN_ROOM_AVAILABLE", room_obs)

        max_v = room_obs["FOREIGN_ROOM_MAX"]["canonical_value"]
        owned_v = room_obs["FOREIGN_ROOM_OWNED"]["canonical_value"]
        avail_v = room_obs["FOREIGN_ROOM_AVAILABLE"]["canonical_value"]

        self.assertNotEqual(max_v, avail_v)
        self.assertEqual(owned_v + avail_v, max_v)
        self.assertEqual("shares", room_obs["FOREIGN_ROOM_MAX"]["canonical_unit"])

    # 5. Proprietary and active-order semantics remain source-bound
    def test_proprietary_and_active_order_semantics_remain_source_bound(self):
        prop_obs = [o for o in self.integrated["observations"] if o["capability_family"] == "PROPRIETARY"]
        micro_obs = [o for o in self.integrated["observations"] if o["capability_family"] == "MICROSTRUCTURE"]

        self.assertTrue(all(o["source"] == "FHSC" for o in prop_obs))
        self.assertTrue(all(o["source"] == "FHSC" for o in micro_obs))

        # Check net volume arithmetic
        net_prop = next(o for o in prop_obs if o["semantic_identity"] == "PROPRIETARY_NET_VOLUME")
        self.assertEqual(530000, net_prop["canonical_value"])

        # Check active order net volume
        net_act = next(o for o in micro_obs if o["semantic_identity"] == "ACTIVE_NET_VOLUME")
        self.assertEqual(4586200, net_act["canonical_value"])

    # 6. MISSING_REQUESTED_SESSION survives unchanged and creates no fact
    def test_missing_requested_session_survives_unchanged_and_creates_no_fact(self):
        packet_with_missing = dict(self.packet)
        packet_with_missing["observations"] = list(self.packet["observations"]) + [
            {
                "session": MOCK_SESSION,
                "instrument": "VCB",
                "source": "DNSE",
                "endpoint_id": "ohlc",
                "status": "MISSING_REQUESTED_SESSION",
                "usability_state": "MISSING",
                "raw_response_retained": False,
                "authority_effect": "NONE",
            }
        ]
        res = integration.integrate_session_packet(packet_with_missing)
        vcb_obs = [o for o in res["observations"] if o["instrument"] == "VCB"]
        self.assertEqual(1, len(vcb_obs))
        self.assertEqual("MISSING_REQUESTED_SESSION", vcb_obs[0]["observation_status"])
        self.assertIsNone(vcb_obs[0]["canonical_value"])
        self.assertFalse(vcb_obs[0]["downstream_eligibility"][integration.USE_WITHIN_SERIES_ANALYTICS])

    # 7. PROVIDER_RATE_LIMITED and BUDGET_EXHAUSTED remain distinct
    def test_provider_rate_limited_and_budget_exhausted_remain_distinct(self):
        packet_with_limits = dict(self.packet)
        packet_with_limits["observations"] = [
            {
                "session": MOCK_SESSION,
                "instrument": "VCB",
                "source": "DNSE",
                "endpoint_id": "ohlc",
                "status": "PROVIDER_RATE_LIMITED",
                "usability_state": "PROVIDER_RATE_LIMITED",
                "raw_response_retained": False,
            },
            {
                "session": MOCK_SESSION,
                "instrument": "SSI",
                "source": "FHSC",
                "endpoint_id": "trading_history",
                "status": "BUDGET_EXHAUSTED",
                "usability_state": "BUDGET_EXHAUSTED",
                "raw_response_retained": False,
            },
        ]
        res = integration.integrate_session_packet(packet_with_limits)
        statuses = {o["instrument"]: o["observation_status"] for o in res["observations"]}
        self.assertEqual("PROVIDER_RATE_LIMITED", statuses["VCB"])
        self.assertEqual("BUDGET_EXHAUSTED", statuses["SSI"])
        self.assertNotEqual(statuses["VCB"], statuses["SSI"])

    # 8. CONFLICTING observation is retained but affected use cases fail closed
    def test_conflicting_observation_is_retained_but_fails_closed(self):
        packet_with_conflict = dict(self.packet)
        # Create arithmetic conflict: matched (2M) + put_through (300k) != total (10M)
        conflict_raw_obs = {
            "session": MOCK_SESSION,
            "instrument": "HPG",
            "source": "FHSC",
            "endpoint_id": "trading_history",
            "status": "ACQUIRED",
            "usability_state": "RESEARCH_USABLE",
            "raw_response_retained": True,
            "raw_path": "raw/conflict.json",
            "raw_sha256": "conflict123",
            "native_fields": {
                "MATCHED_VOLUME_SHARES": {"value": 2000000, "unit": "shares"},
                "PUT_THROUGH_VOLUME_SHARES": {"value": 300000, "unit": "shares"},
                "TOTAL_VOLUME_SHARES": {"value": 10000000, "unit": "shares"},
            },
            "canonical_fields": {
                "TOTAL_VOLUME_SHARES": {"value": 10000000, "unit": "shares"},
            },
        }
        packet_with_conflict["observations"] = [conflict_raw_obs]
        res = integration.integrate_session_packet(packet_with_conflict)

        obs = res["observations"][0]
        self.assertEqual("CONFLICTING_VOLUME_ARITHMETIC", obs["conflict_state"])
        self.assertEqual(taxonomy.CONFLICTING, obs["usability_state"])
        # Retained but fails closed for descriptive display and within series analytics
        self.assertFalse(obs["downstream_eligibility"][integration.USE_DESCRIPTIVE_RESEARCH_DISPLAY])
        self.assertFalse(obs["downstream_eligibility"][integration.USE_WITHIN_SERIES_ANALYTICS])
        # Reconciliation is still permitted to inspect the conflict
        self.assertTrue(obs["downstream_eligibility"][integration.USE_CROSS_SOURCE_RECONCILIATION])

    # 9. Same semantic from DNSE + FHSC remains two provenance-bound observations, not averaged
    def test_same_semantic_from_multiple_sources_remains_distinct_and_unblended(self):
        volume_obs = [o for o in self.integrated["observations"] if o["semantic_identity"] == "MATCHED_VOLUME_SHARES"]
        self.assertEqual(2, len(volume_obs))
        sources = {o["source"] for o in volume_obs}
        self.assertEqual({"DNSE", "FHSC"}, sources)

        dnse_vol = next(o for o in volume_obs if o["source"] == "DNSE")
        fhsc_vol = next(o for o in volume_obs if o["source"] == "FHSC")

        self.assertEqual("ohlc", dnse_vol["endpoint_id"])
        self.assertEqual("trading_history", fhsc_vol["endpoint_id"])
        self.assertNotEqual(dnse_vol["raw_sha256"], fhsc_vol["raw_sha256"])

    # 10. Research usability does not imply RAW_AS_TRADED, liquidity/sizing, valuation, recommendation
    def test_research_usability_does_not_imply_prohibited_authorities(self):
        for obs in self.integrated["observations"]:
            elig = obs["downstream_eligibility"]
            self.assertFalse(elig[integration.PROHIBITED_LIQUIDITY_SIZING])
            self.assertFalse(elig[integration.PROHIBITED_VALUATION])
            self.assertFalse(elig[integration.PROHIBITED_RAW_AS_TRADED_PIT_BACKTEST])
            self.assertFalse(elig[integration.PROHIBITED_RECOMMENDATION_AUTHORITY])
            self.assertEqual("NONE", obs["authority_effect"])

        # Envelope boundaries
        bounds = self.integrated["authority_boundaries"]
        self.assertEqual("NONE", bounds["authority_effect"])
        self.assertFalse(bounds["raw_as_traded_promoted"])
        self.assertFalse(bounds["pit_backtest_eligible"])
        self.assertEqual("BLOCKED", bounds["liquidity_sizing_authority"])

    # 11. Deterministic replay produces identical canonical identity/output
    def test_deterministic_replay_produces_identical_identity(self):
        res1 = integration.integrate_session_packet(self.packet)
        res2 = integration.integrate_session_packet(self.packet)

        self.assertEqual(res1["integration_sha256"], res2["integration_sha256"])
        self.assertEqual(res1["integration_identity"], res2["integration_identity"])
        self.assertEqual(len(res1["observations"]), len(res2["observations"]))

    # 12. No secret material appears in outputs or tests
    def test_no_secret_material_in_outputs(self):
        dumped = json.dumps(self.integrated)
        sensitive_patterns = ("api_key", "x-fh-apikey", "authorization", "secret", "passwd")
        for pat in sensitive_patterns:
            self.assertNotIn(pat, dumped.lower())

    # Downstream Proof Projection tests
    def test_downstream_proof_projection_within_series(self):
        proj = integration.project_research_market_features(
            self.integrated,
            permitted_use=integration.USE_WITHIN_SERIES_ANALYTICS,
            target_symbols=["HPG"],
        )
        self.assertEqual("SUCCESS", proj["status"])
        self.assertEqual(1, proj["instrument_count"])
        hpg = proj["features_by_instrument"]["HPG"]

        # Check multi-source features are structured and provenance-bound
        self.assertIn("DNSE", hpg["prices"])
        self.assertEqual("21850", hpg["prices"]["DNSE"]["CLOSE_VND"]["value"])
        self.assertIn("FHSC", hpg["traded_values"])
        self.assertEqual(53750000000, hpg["traded_values"]["FHSC"]["TOTAL_TRADED_VALUE_VND"]["value"])
        self.assertIn("FHSC", hpg["foreign_room"])
        self.assertEqual(2089955445, hpg["foreign_room"]["FHSC"]["FOREIGN_ROOM_MAX"]["value"])

    def test_downstream_proof_projection_rejects_prohibited_use(self):
        proj = integration.project_research_market_features(
            self.integrated,
            permitted_use=integration.PROHIBITED_LIQUIDITY_SIZING,
        )
        self.assertEqual("PROHIBITED_USE_REJECTED", proj["status"])
        self.assertFalse(proj["is_actionable"])
        self.assertEqual({}, proj["features_by_instrument"])


if __name__ == "__main__":
    unittest.main()
