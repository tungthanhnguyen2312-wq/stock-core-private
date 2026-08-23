"""Tests for dnse_trades_liquidity_basis.py (DNSE_TRADES_AND_LIQUIDITY_BASIS_QUALIFICATION_V1).

Fixtures below reproduce this milestone's own bounded live-probe observations (HPG/VCB/SSI/FPT/QNS,
session 2026-08-21) as literal data so these tests stay hermetic and offline -- no network, no
credential, no dependency on the gitignored operations-review/ evidence directory.
"""
from __future__ import annotations

import unittest

import dnse_trades_liquidity_basis as basis
import market_phase2_foundation
from dnse_volume_composition_reconciliation import C5_CANDIDATE, ScaleStatus


def _raw_tick(board_id: str, *, time: str, match_price: float, match_qtty: float, avg_price: float,
              total_volume: float, gross_amount: float, side: str = "BUY", symbol: str = "HPG") -> dict:
    return {
        "avgPrice": avg_price, "boardId": board_id, "grossTradeAmount": gross_amount,
        "highestPrice": 0, "isin": f"VN000000{symbol}4", "lowestPrice": 0, "marketId": "STO",
        "matchPrice": match_price, "matchQtty": match_qtty, "openPrice": 0, "side": side,
        "symbol": symbol, "time": time, "totalVolumeTraded": total_volume,
    }


# Real observed HPG trades_latest rows, 2026-08-21 (this milestone's own bounded live probe).
HPG_G1_RAW = _raw_tick("G1", time="2026-08-21 14:45:03.583", match_price=21.7, match_qtty=430,
                        avg_price=21.456, total_volume=2513840, gross_amount=539.379775)
HPG_G4_RAW = _raw_tick("G4", time="2026-08-21 14:45:01.091", match_price=21.65, match_qtty=14,
                        avg_price=21.366, total_volume=31992, gross_amount=0.6835365, side="SELL")
HPG_T1_STALE_RAW = _raw_tick("T1", time="2026-08-20 13:15:11.105", match_price=22.0, match_qtty=20000,
                              avg_price=22.0, total_volume=20000, gross_amount=4.4, side="UNSPECIFIED")
HPG_OHLC_V_2026_08_21 = 25138400


class CanonicalizeTradeTickTests(unittest.TestCase):
    def test_valid_record_parses_and_derives_session_date(self) -> None:
        record = basis.canonicalize_trade_tick(HPG_G1_RAW, symbol="hpg", endpoint="trades_latest")
        self.assertEqual(record["parse_status"], "PARSED")
        self.assertEqual(record["symbol"], "HPG")
        self.assertEqual(record["board_id"], "G1")
        self.assertEqual(record["board_semantic"], "ROUND_LOT")
        self.assertEqual(record["session_date"], "2026-08-21")
        self.assertEqual(record["cumulative_volume_raw"], 2513840.0)
        self.assertEqual(record["side_raw"], "BUY")

    def test_unrecognized_board_id_fails_closed_not_invented(self) -> None:
        raw = dict(HPG_G1_RAW, boardId="Z9")
        record = basis.canonicalize_trade_tick(raw, symbol="HPG", endpoint="trades_latest")
        self.assertEqual(record["parse_status"], "UNRECOGNIZED_BOARD_ID")

    def test_missing_required_numeric_field_fails_closed(self) -> None:
        raw = dict(HPG_G1_RAW)
        del raw["totalVolumeTraded"]
        record = basis.canonicalize_trade_tick(raw, symbol="HPG", endpoint="trades_latest")
        self.assertEqual(record["parse_status"], "REQUIRED_FIELD_MISSING_OR_INVALID")
        self.assertEqual(record["field"], "totalVolumeTraded")

    def test_non_numeric_required_field_fails_closed_no_coercion(self) -> None:
        raw = dict(HPG_G1_RAW, matchQtty="ten")
        record = basis.canonicalize_trade_tick(raw, symbol="HPG", endpoint="trades_latest")
        self.assertEqual(record["parse_status"], "REQUIRED_FIELD_MISSING_OR_INVALID")

    def test_malformed_time_field_fails_closed(self) -> None:
        raw = dict(HPG_G1_RAW, time="not-a-time")
        record = basis.canonicalize_trade_tick(raw, symbol="HPG", endpoint="trades_latest")
        self.assertEqual(record["parse_status"], "TIME_FIELD_MISSING_OR_INVALID")

    def test_side_is_carried_through_never_reinterpreted(self) -> None:
        record = basis.canonicalize_trade_tick(HPG_T1_STALE_RAW, symbol="HPG", endpoint="trades_latest")
        self.assertEqual(record["side_raw"], "UNSPECIFIED")


class ParseTradesResponseTests(unittest.TestCase):
    def test_parses_trades_array_and_reports_next_page_token(self) -> None:
        body = {"trades": [HPG_G1_RAW, HPG_G4_RAW], "nextPageToken": "abc"}
        parsed = basis.parse_trades_response(body, symbol="HPG", endpoint="trades_latest")
        self.assertEqual(parsed["parse_status"], "PARSED")
        self.assertEqual(parsed["parsed_count"], 2)
        self.assertEqual(parsed["rejected_count"], 0)
        self.assertTrue(parsed["next_page_token_present"])

    def test_absent_trades_array_fails_closed(self) -> None:
        parsed = basis.parse_trades_response({"nextPageToken": None}, symbol="HPG", endpoint="trades_latest")
        self.assertEqual(parsed["parse_status"], "TRADES_ARRAY_ABSENT_OR_INVALID")

    def test_falsy_next_page_token_is_not_present(self) -> None:
        parsed = basis.parse_trades_response({"trades": [], "nextPageToken": None}, symbol="HPG", endpoint="trades_history")
        self.assertFalse(parsed["next_page_token_present"])


class BoardLatestSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = [
            basis.canonicalize_trade_tick(HPG_G1_RAW, symbol="HPG", endpoint="trades_latest"),
            basis.canonicalize_trade_tick(HPG_G4_RAW, symbol="HPG", endpoint="trades_latest"),
            basis.canonicalize_trade_tick(HPG_T1_STALE_RAW, symbol="HPG", endpoint="trades_latest"),
        ]

    def test_target_session_date_auto_resolves_to_max_observed(self) -> None:
        snapshot = basis.board_latest_snapshot(self.records)
        self.assertEqual(snapshot["target_session_date"], "2026-08-21")

    def test_active_vs_stale_classification(self) -> None:
        snapshot = basis.board_latest_snapshot(self.records)
        self.assertEqual(snapshot["boards"]["G1"]["activity_state"], basis.OBSERVED_ACTIVE_THIS_SESSION)
        self.assertEqual(snapshot["boards"]["G4"]["activity_state"], basis.OBSERVED_ACTIVE_THIS_SESSION)
        self.assertEqual(snapshot["boards"]["T1"]["activity_state"], basis.OBSERVED_INACTIVE_STALE)
        self.assertEqual(snapshot["boards"]["T1"]["last_active_session_date"], "2026-08-20")

    def test_board_never_observed_is_distinct_from_stale(self) -> None:
        snapshot = basis.board_latest_snapshot(self.records)
        self.assertEqual(snapshot["boards"]["T3"]["activity_state"], basis.NOT_OBSERVED)
        self.assertNotIn("cumulative_volume_raw", snapshot["boards"]["T3"])

    def test_explicit_target_session_date_overrides_autoresolution(self) -> None:
        snapshot = basis.board_latest_snapshot(self.records, target_session_date="2026-08-20")
        self.assertEqual(snapshot["boards"]["G1"]["activity_state"], basis.OBSERVED_INACTIVE_STALE)
        self.assertEqual(snapshot["boards"]["T1"]["activity_state"], basis.OBSERVED_ACTIVE_THIS_SESSION)

    def test_tie_break_keeps_highest_cumulative_volume(self) -> None:
        earlier_g1 = basis.canonicalize_trade_tick(
            _raw_tick("G1", time="2026-08-21 10:00:00.000", match_price=21.0, match_qtty=10,
                      avg_price=21.0, total_volume=1000000, gross_amount=100.0),
            symbol="HPG", endpoint="trades_latest")
        snapshot = basis.board_latest_snapshot([earlier_g1] + self.records)
        self.assertEqual(snapshot["boards"]["G1"]["cumulative_volume_raw"], 2513840.0)


class BoardCategoryTotalsTests(unittest.TestCase):
    def test_matched_and_put_through_are_kept_separate(self) -> None:
        records = [
            basis.canonicalize_trade_tick(HPG_G1_RAW, symbol="HPG", endpoint="trades_latest"),
            basis.canonicalize_trade_tick(HPG_T1_STALE_RAW, symbol="HPG", endpoint="trades_latest"),
        ]
        snapshot = basis.board_latest_snapshot(records)  # target = 2026-08-21; T1 is stale
        categories = basis.board_category_totals(snapshot)
        self.assertEqual(categories["MATCHED_ROUND_LOT"]["active_volume_raw_total"], 2513840.0)
        self.assertEqual(categories["PUT_THROUGH_ROUND_LOT"]["active_volume_raw_total"], 0.0)
        not_counted_codes = {entry["board_id"] for entry in categories["PUT_THROUGH_ROUND_LOT"]["boards_not_counted"]}
        self.assertIn("T1", not_counted_codes)

    def test_stale_and_not_observed_boards_are_disclosed_not_silently_zeroed(self) -> None:
        records = [basis.canonicalize_trade_tick(HPG_G1_RAW, symbol="HPG", endpoint="trades_latest")]
        snapshot = basis.board_latest_snapshot(records)
        categories = basis.board_category_totals(snapshot)
        odd_lot_not_counted = categories["MATCHED_ODD_LOT"]["boards_not_counted"]
        self.assertEqual(len(odd_lot_not_counted), 1)
        self.assertEqual(odd_lot_not_counted[0]["board_id"], "G4")
        self.assertEqual(odd_lot_not_counted[0]["activity_state"], basis.NOT_OBSERVED)

    def test_four_categories_cover_all_six_board_codes_exactly_once(self) -> None:
        snapshot = basis.board_latest_snapshot([])
        categories = basis.board_category_totals(snapshot)
        all_codes = [code for cat in categories.values() for code in cat["boards"]]
        self.assertEqual(sorted(all_codes), sorted(market_phase2_foundation.DNSE_BOARD_SEMANTICS))
        self.assertEqual(len(all_codes), len(set(all_codes)))


class G1ScaleCrossCheckTests(unittest.TestCase):
    """Reproduces this milestone's own live finding: 10 x G1 == OHLC daily v, exactly."""

    def test_exact_match_on_real_observed_hpg_session(self) -> None:
        records = [basis.canonicalize_trade_tick(HPG_G1_RAW, symbol="HPG", endpoint="trades_latest")]
        snapshot = basis.board_latest_snapshot(records)
        result = basis.g1_scale_cross_check(snapshot, ohlc_v=HPG_OHLC_V_2026_08_21)
        self.assertEqual(result["verdict"], "EXACT_MATCH")
        self.assertTrue(result["exact_match"])
        self.assertEqual(result["delta"], 0.0)
        self.assertEqual(result["candidate"]["scale_status"], ScaleStatus.EMPIRICAL_CANDIDATE.value)
        self.assertEqual(result["candidate"]["semantic_unit_interpretation"], "UNKNOWN")

    def test_never_promotes_the_candidate_even_on_exact_match(self) -> None:
        records = [basis.canonicalize_trade_tick(HPG_G1_RAW, symbol="HPG", endpoint="trades_latest")]
        snapshot = basis.board_latest_snapshot(records)
        result = basis.g1_scale_cross_check(snapshot, ohlc_v=HPG_OHLC_V_2026_08_21)
        self.assertEqual(result["candidate"], C5_CANDIDATE.record())

    def test_residual_classification_reused_not_reimplemented(self) -> None:
        records = [basis.canonicalize_trade_tick(HPG_G1_RAW, symbol="HPG", endpoint="trades_latest")]
        snapshot = basis.board_latest_snapshot(records)
        # 100 shares off -> POSITIVE_DELTA_MULTIPLE_OF_100 per the existing C5 residual classifier.
        result = basis.g1_scale_cross_check(snapshot, ohlc_v=HPG_OHLC_V_2026_08_21 + 100)
        self.assertEqual(result["verdict"], "POSITIVE_DELTA_MULTIPLE_OF_100")
        self.assertFalse(result["exact_match"])

    def test_unavailable_when_g1_not_active_this_session(self) -> None:
        snapshot = basis.board_latest_snapshot([])
        result = basis.g1_scale_cross_check(snapshot, ohlc_v=HPG_OHLC_V_2026_08_21)
        self.assertEqual(result["verdict"], "UNAVAILABLE")

    def test_unavailable_when_ohlc_v_missing(self) -> None:
        records = [basis.canonicalize_trade_tick(HPG_G1_RAW, symbol="HPG", endpoint="trades_latest")]
        snapshot = basis.board_latest_snapshot(records)
        result = basis.g1_scale_cross_check(snapshot, ohlc_v=None)
        self.assertEqual(result["verdict"], "UNAVAILABLE")

    def test_lineage_distinct_from_orphaned_generator(self) -> None:
        records = [basis.canonicalize_trade_tick(HPG_G1_RAW, symbol="HPG", endpoint="trades_latest")]
        snapshot = basis.board_latest_snapshot(records)
        result = basis.g1_scale_cross_check(snapshot, ohlc_v=HPG_OHLC_V_2026_08_21)
        self.assertEqual(result["lineage_status"], basis.LIVE_ADAPTER_LINEAGE_STATUS)
        self.assertNotEqual(result["lineage_status"],
                            result["contrast_with_orphaned_generator"]["orphaned_lineage_status"])


class GrossTradeAmountConsistencyTests(unittest.TestCase):
    def test_g1_gross_trade_amount_is_consistent_with_uniform_formula(self) -> None:
        record = basis.canonicalize_trade_tick(HPG_G1_RAW, symbol="HPG", endpoint="trades_latest")
        result = basis.gross_trade_amount_uniform_formula_check(record)
        self.assertEqual(result["verdict"], "CONSISTENT_WITH_UNIFORM_FORMULA")

    def test_detects_inconsistency_when_forced(self) -> None:
        raw = dict(HPG_G1_RAW, grossTradeAmount=99999.0)
        record = basis.canonicalize_trade_tick(raw, symbol="HPG", endpoint="trades_latest")
        result = basis.gross_trade_amount_uniform_formula_check(record)
        self.assertEqual(result["verdict"], "INCONSISTENT")


class TradedValueCandidateTests(unittest.TestCase):
    def test_direct_candidate_is_never_authoritative(self) -> None:
        record = basis.canonicalize_trade_tick(HPG_G1_RAW, symbol="HPG", endpoint="trades_latest")
        candidate = basis.traded_value_candidate(record)
        self.assertFalse(candidate["authoritative"])
        self.assertEqual(candidate["semantic_unit_interpretation"], "UNKNOWN")
        self.assertFalse(candidate["cross_board_scale_ambiguity_open"])  # G1 itself

    def test_non_g1_board_flags_open_scale_ambiguity(self) -> None:
        record = basis.canonicalize_trade_tick(HPG_T1_STALE_RAW, symbol="HPG", endpoint="trades_latest")
        candidate = basis.traded_value_candidate(record)
        self.assertTrue(candidate["cross_board_scale_ambiguity_open"])

    def test_derived_value_blocked_without_explicit_lot_multiplier(self) -> None:
        record = basis.canonicalize_trade_tick(HPG_G1_RAW, symbol="HPG", endpoint="trades_latest")
        result = basis.derived_value_price_times_shares(record)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["reason"], "lot_multiplier_ambiguity_unresolved")

    def test_derived_value_computed_only_with_explicit_multiplier_and_stays_non_authoritative(self) -> None:
        record = basis.canonicalize_trade_tick(HPG_G1_RAW, symbol="HPG", endpoint="trades_latest")
        result = basis.derived_value_price_times_shares(record, lot_multiplier=10.0)
        self.assertEqual(result["state"], "COMPUTED")
        self.assertFalse(result["authoritative"])
        self.assertEqual(result["true_shares"], 25138400.0)


class ScanCompletenessTests(unittest.TestCase):
    def test_exhausted_scan_confirms_absence(self) -> None:
        result = basis.scan_completeness(boards_seen=["G1", "G4"], pages_fetched=4, page_cap=4, exhausted=True)
        self.assertEqual(result["state"], basis.COMPLETE)
        self.assertFalse(result["lower_bound_only"])
        self.assertEqual(result["boards_confirmed_absent"], ["T1", "T3", "T4", "T6"])
        self.assertEqual(result["boards_unscanned"], [])

    def test_unexhausted_scan_never_confirms_absence(self) -> None:
        result = basis.scan_completeness(boards_seen=["G1"], pages_fetched=4, page_cap=4, exhausted=False)
        self.assertEqual(result["state"], basis.PARTIAL_BOUNDED_SCAN)
        self.assertTrue(result["lower_bound_only"])
        self.assertEqual(result["boards_confirmed_absent"], [])
        self.assertIn("T1", result["boards_unscanned"])


class SessionLiquidityResearchContractTests(unittest.TestCase):
    def test_current_session_eligible_does_not_leak_into_historical(self) -> None:
        contract = basis.session_liquidity_research_contract(
            current_session_boards_active=True, historical_scan_state=None)
        self.assertEqual(contract[basis.CURRENT_SESSION_LIQUIDITY_RESEARCH]["state"], basis.ELIGIBLE)
        self.assertEqual(contract[basis.HISTORICAL_LIQUIDITY_RESEARCH]["state"], basis.UNKNOWN)
        self.assertEqual(contract[basis.ADV_VOLUME_RESEARCH]["state"], basis.BLOCKED)
        self.assertEqual(contract[basis.ADTV_RESEARCH]["state"], basis.BLOCKED)

    def test_complete_historical_scan_yields_partial_never_eligible(self) -> None:
        contract = basis.session_liquidity_research_contract(
            current_session_boards_active=True, historical_scan_state=basis.COMPLETE)
        self.assertEqual(contract[basis.HISTORICAL_LIQUIDITY_RESEARCH]["state"], basis.PARTIAL)

    def test_partial_bounded_scan_yields_blocked(self) -> None:
        contract = basis.session_liquidity_research_contract(
            current_session_boards_active=True, historical_scan_state=basis.PARTIAL_BOUNDED_SCAN)
        self.assertEqual(contract[basis.HISTORICAL_LIQUIDITY_RESEARCH]["state"], basis.BLOCKED)

    def test_sizing_execution_pit_always_blocked_regardless_of_current_session_success(self) -> None:
        contract = basis.session_liquidity_research_contract(
            current_session_boards_active=True, historical_scan_state=basis.COMPLETE)
        self.assertEqual(contract[basis.POSITION_SIZING]["state"], basis.BLOCKED)
        self.assertEqual(contract[basis.EXECUTION_CAPACITY]["state"], basis.BLOCKED)
        self.assertEqual(contract[basis.PIT_BACKTEST]["state"], basis.BLOCKED)

    def test_no_board_active_blocks_current_session_too(self) -> None:
        contract = basis.session_liquidity_research_contract(
            current_session_boards_active=False, historical_scan_state=None)
        self.assertEqual(contract[basis.CURRENT_SESSION_LIQUIDITY_RESEARCH]["state"], basis.BLOCKED)


class AssertFailClosedTests(unittest.TestCase):
    def test_passes_on_a_real_contract(self) -> None:
        contract = basis.session_liquidity_research_contract(
            current_session_boards_active=True, historical_scan_state=basis.COMPLETE)
        basis.assert_fail_closed(contract)

    def test_rejects_missing_dimension(self) -> None:
        contract = basis.session_liquidity_research_contract(
            current_session_boards_active=True, historical_scan_state=None)
        incomplete = dict(contract)
        del incomplete[basis.PIT_BACKTEST]
        with self.assertRaises(basis.TradesLiquidityBasisError):
            basis.assert_fail_closed(incomplete)

    def test_rejects_tampered_contract_that_opens_position_sizing(self) -> None:
        contract = basis.session_liquidity_research_contract(
            current_session_boards_active=True, historical_scan_state=basis.COMPLETE)
        tampered = dict(contract)
        tampered[basis.POSITION_SIZING] = {"state": basis.ELIGIBLE, "reason": "tampered", "cites": ["x"]}
        with self.assertRaises(basis.TradesLiquidityBasisError):
            basis.assert_fail_closed(tampered)

    def test_rejects_uncited_verdict(self) -> None:
        with self.assertRaises(basis.TradesLiquidityBasisError):
            basis._fitness(basis.BLOCKED, reason="x", cites=[])

    def test_rejects_unregistered_state(self) -> None:
        with self.assertRaises(basis.TradesLiquidityBasisError):
            basis._fitness("MAYBE", reason="x", cites=["y"])


class BoardSemanticReuseRegressionTests(unittest.TestCase):
    """Pins that this module never redefines board semantics or the category split."""

    def test_known_board_codes_match_market_phase2_foundation(self) -> None:
        self.assertEqual(basis.KNOWN_BOARD_CODES, frozenset(market_phase2_foundation.DNSE_BOARD_SEMANTICS))

    def test_category_split_is_the_same_object_market_price_volume_basis_authority_uses(self) -> None:
        import market_price_volume_basis_authority as capstone
        self.assertEqual(basis.assert_lot_and_route_not_conflated, capstone.assert_lot_and_route_not_conflated)


class DeterministicIdentityTests(unittest.TestCase):
    def test_content_identity_is_stable_across_two_calls(self) -> None:
        payload = {"a": 1, "b": [1, 2, 3]}
        first = basis.content_identity(payload)
        second = basis.content_identity(payload)
        self.assertEqual(first, second)
        self.assertTrue(first["artifact_identity"].startswith("dnse_trades_liquidity_basis:"))

    def test_content_identity_ignores_prior_identity_fields(self) -> None:
        payload = {"a": 1}
        first = basis.content_identity(payload)
        payload_with_identity = dict(payload, **first)
        second = basis.content_identity(payload_with_identity)
        self.assertEqual(first, second)


class ExistingRegressionSmokeTests(unittest.TestCase):
    """Confirms this milestone's read-only reuse did not disturb the capstone matrix it cites."""

    def test_market_price_volume_basis_authority_still_fail_closed(self) -> None:
        import market_price_volume_basis_authority as capstone
        capstone.assert_registry_fail_closed()


if __name__ == "__main__":
    unittest.main()
