from __future__ import annotations

import copy
import unittest

import market_volume_value_semantic_contract as contract


class VolumeValueSemanticContractTests(unittest.TestCase):
    def test_traded_volume_cannot_satisfy_a_traded_value_requirement(self):
        with self.assertRaisesRegex(contract.SemanticContractError, "semantic_type_mismatch"):
            contract.require(
                "vci.daily.v", semantic_type=contract.SemanticType.TRADED_VALUE_VND,
                unit=contract.Unit.VND, downstream_use=contract.DownstreamUse.DISPLAY,
            )

    def test_traded_value_cannot_satisfy_a_volume_requirement(self):
        with self.assertRaisesRegex(contract.SemanticContractError, "semantic_type_mismatch"):
            contract.require(
                "kbs.daily.va", semantic_type=contract.SemanticType.TRADED_VOLUME_SHARES,
                unit=contract.Unit.SHARES, downstream_use=contract.DownstreamUse.DISPLAY,
            )

    def test_unestablished_board_and_session_scope_remain_unknown(self):
        record = contract.field_contract("vci.daily.v").record()
        self.assertEqual("unknown", record["board_scope"])
        self.assertEqual("unknown", record["session_scope"])
        self.assertEqual("unknown", record["put_through_inclusion"])
        self.assertEqual("unknown", record["odd_lot_inclusion"])

    def test_foreign_value_cannot_satisfy_a_generic_volume_requirement(self):
        with self.assertRaisesRegex(contract.SemanticContractError, "semantic_type_mismatch"):
            contract.require(
                "dnse.foreign_buy_value", semantic_type=contract.SemanticType.TRADED_VOLUME_SHARES,
                unit=contract.Unit.SHARES, downstream_use=contract.DownstreamUse.PROVIDER_SCOPED_ANALYTICS,
            )

    def test_room_headroom_cannot_satisfy_a_flow_requirement(self):
        with self.assertRaisesRegex(contract.SemanticContractError, "semantic_type_mismatch"):
            contract.require(
                "dnse.foreign_room_headroom", semantic_type=contract.SemanticType.FOREIGN_NET_VALUE_VND,
                unit=contract.Unit.VND, downstream_use=contract.DownstreamUse.FOREIGN_VALUE_FLOW_ANALYTICS,
            )
        snapshot = copy.deepcopy(contract.contract_snapshot())
        snapshot["fields"]["dnse.foreign_room_headroom"]["downstream_eligible_uses"].append(
            "foreign_value_flow_analytics"
        )
        with self.assertRaisesRegex(contract.SemanticContractError, "room_headroom_cannot_become_flow"):
            contract.assert_fail_closed(snapshot)

    def test_raw_share_volume_is_not_implicitly_price_adjusted(self):
        record = contract.field_contract("vci.daily.v").record()
        self.assertEqual("shares", record["unit"])
        self.assertEqual("unknown", record["volume_corporate_action_adjustment"])

    def test_unsupported_downstream_use_fails_closed(self):
        with self.assertRaisesRegex(contract.SemanticContractError, "downstream_use_not_eligible"):
            contract.require(
                "kbs.daily.v", semantic_type=contract.SemanticType.TRADED_VOLUME_SHARES,
                unit=contract.Unit.SHARES, downstream_use=contract.DownstreamUse.EXECUTION_SIZING,
            )

    def test_known_scoped_value_preserves_unit_source_and_identity_deterministically(self):
        first = contract.contract_snapshot()
        second = contract.contract_snapshot()
        self.assertEqual(first, second)
        record = first["fields"]["dnse.foreign_net_value"]
        self.assertEqual("DNSE", record["provider"])
        self.assertEqual("VND", record["unit"])
        self.assertEqual("FOREIGN_NET_VALUE_VND", record["semantic_type"])
        self.assertEqual("included", record["session_scope"])
        self.assertEqual("unknown", record["board_scope"])
        self.assertEqual("qualified_per_observation", record["pit_as_of_identity"]["as_of"])

    def test_fail_closed_guard_rejects_relabelled_derived_value(self):
        snapshot = copy.deepcopy(contract.contract_snapshot())
        snapshot["fields"]["legacy.gtgd20_ty"]["qualification_state"] = "qualified"
        with self.assertRaisesRegex(contract.SemanticContractError, "derived_price_times_volume"):
            contract.assert_fail_closed(snapshot)

    def test_dnse_daily_ohlc_volume_absolute_unit_is_unknown_but_relative_ratios_are_bounded(self):
        record = contract.field_contract("dnse.daily.ohlc.v").record()
        self.assertEqual("DNSE", record["provider"])
        self.assertEqual("daily OHLC v", record["field_identity"])
        self.assertEqual("UNKNOWN_UNQUALIFIED", record["semantic_type"])
        self.assertEqual("unknown", record["unit"])
        for dimension in (
            "session_scope", "board_scope", "put_through_inclusion", "odd_lot_inclusion",
            "auction_inclusion", "ato_inclusion", "atc_inclusion", "continuous_session_inclusion",
        ):
            self.assertEqual("unknown", record[dimension])
        with self.assertRaisesRegex(contract.SemanticContractError, "downstream_use_not_eligible"):
            contract.require(
                "dnse.daily.ohlc.v", semantic_type=contract.SemanticType.UNKNOWN_UNQUALIFIED,
                unit=contract.Unit.UNKNOWN, downstream_use=contract.DownstreamUse.EXECUTION_SIZING,
            )
        relative = contract.require(
            "dnse.daily.ohlc.v.relative_only", semantic_type=contract.SemanticType.RELATIVE_VOLUME,
            unit=contract.Unit.RATIO, downstream_use=contract.DownstreamUse.PROVIDER_SCOPED_ANALYTICS,
        )
        self.assertEqual("ratio", relative.record()["unit"])

    def test_dnse_daily_value_field_stays_explicitly_not_confirmed(self):
        self.assertEqual("UNKNOWN/NOT_CONFIRMED", contract.DNSE_DAILY_TRADED_VALUE_FIELD)
        with self.assertRaisesRegex(contract.SemanticContractError, "scope_must_remain_unknown"):
            snapshot = copy.deepcopy(contract.contract_snapshot())
            snapshot["fields"]["dnse.daily.ohlc.v"]["ato_inclusion"] = "included"
            contract.assert_fail_closed(snapshot)


if __name__ == "__main__":
    unittest.main()
