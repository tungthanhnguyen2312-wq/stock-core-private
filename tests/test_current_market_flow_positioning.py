import unittest

from current_market_flow_positioning import build, content_identity, prospective_context


def obs(semantic, value, *, source="FHSC", status="ACQUIRED", session="2026-08-21"):
    return {"instrument": "HPG", "session": session, "retrieved_at": "2026-08-21T10:00:00+07:00", "source": source, "endpoint_id": "test", "semantic_identity": semantic, "canonical_value": value, "canonical_unit": "vnd" if "VALUE" in semantic else "shares", "provider_native_value": value, "provider_native_unit": "native", "raw_sha256": semantic, "observation_status": status, "conflict_state": "CLEAN", "downstream_eligibility": {"descriptive_research_display": status == "ACQUIRED", "flow_research": status == "ACQUIRED"}}


class CurrentMarketFlowPositioningTests(unittest.TestCase):
    def setUp(self):
        self.packet = {"session_date": "2026-08-21", "integration_identity": "canonical:test", "observations": [
            obs("MATCHED_TRADED_VALUE_VND", 80), obs("PUT_THROUGH_TRADED_VALUE_VND", 20), obs("TOTAL_TRADED_VALUE_VND", 100),
            obs("FOREIGN_BUY_VALUE", 50, source="DNSE"), obs("FOREIGN_SELL_VALUE", 20, source="DNSE"), obs("FOREIGN_NET_VALUE", 30, source="DNSE"),
            obs("FOREIGN_ROOM_MAX", 1000), obs("FOREIGN_ROOM_OWNED", 960), obs("FOREIGN_ROOM_AVAILABLE", 40),
            obs("PROPRIETARY_BUY_VALUE", 40), obs("PROPRIETARY_SELL_VALUE", 10), obs("PROPRIETARY_NET_VALUE", 30),
            obs("ACTIVE_BUY_VOLUME", 90), obs("ACTIVE_SELL_VOLUME", 10), obs("ACTIVE_BUY_ORDER_COUNT", 9), obs("ACTIVE_SELL_ORDER_COUNT", 1),
        ]}

    def test_full_projection_preserves_invariants_and_noncausal_boundary(self):
        artifact = build(canonical_integration=self.packet, tactical={"artifact_identity": "tactical:test", "records": {"HPG": {"entry_state": "BREAKOUT_READY"}}})
        row = artifact["records"]["HPG"]
        self.assertEqual(row["traded_value"]["state"], "MIXED_COMPOSITION")
        self.assertEqual(row["foreign_flow"]["state"], "NET_FOREIGN_BUY")
        self.assertEqual(row["foreign_room"]["state"], "NEAR_LIMIT")
        self.assertEqual(row["proprietary_flow"]["state"], "NET_PROP_BUY")
        self.assertEqual(row["active_order_context"]["state"], "ACTIVE_BUY_SKEW")
        self.assertIn("BREAKOUT_WITH_FLOW_CONFIRMATION", row["price_flow_relationships"])
        self.assertEqual(artifact["coverage"]["MULTI_DIMENSION_READY"], 1)
        self.assertEqual(artifact["authority_boundary"]["liquidity_sizing_execution"], "BLOCKED")
        self.assertEqual(content_identity(artifact)["artifact_sha256"], artifact["artifact_sha256"])

    def test_missing_or_invalid_component_fails_closed_not_zero(self):
        packet = {"session_date": "2026-08-21", "observations": [obs("MATCHED_TRADED_VALUE_VND", 50), obs("PUT_THROUGH_TRADED_VALUE_VND", 20), obs("TOTAL_TRADED_VALUE_VND", 80), obs("ACTIVE_BUY_VOLUME", 1, status="PROVIDER_RATE_LIMITED")]}
        row = build(canonical_integration=packet)["records"]["HPG"]
        self.assertEqual(row["traded_value"]["status"], "SEMANTIC_BLOCKED")
        self.assertEqual(row["active_order_context"]["status"], "RATE_LIMITED")
        self.assertNotEqual(row["active_order_context"]["state"], "BALANCED_ACTIVE_FLOW")

    def test_prospective_context_freezes_states_only(self):
        artifact = build(canonical_integration=self.packet)
        frozen = prospective_context(artifact)
        self.assertEqual(frozen["future_outcomes"], "PENDING_FUTURE_OBSERVATION")
        self.assertEqual(frozen["frozen_records"][0]["foreign_flow_state"], "NET_FOREIGN_BUY")

