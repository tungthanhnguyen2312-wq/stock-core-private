"""Proofs for kbs_trade_scope_qualification.py -- the new price-board + intraday-tape
market-composition finding for KBS.

Covers: the frozen contract matches what re-deriving from retained raw evidence produces;
put-through is demonstrated excluded, not merely absent by construction; odd-lot stays
unknown no matter what; a truncated or residual-carrying reconciliation never resolves a
dimension; and the module never claims documented_verified or touches liquidity_actionable.
"""

from __future__ import annotations

import unittest

import evidence_qualification_tiers as tiers
import kbs_trade_scope_qualification as scope


def _board(ticker="HPG", tt=1_000_000, ptq=0, ptv=0, date="07/08/2026"):
    return {"ticker": ticker, "trading_date": date, "volume_accumulated": tt,
            "put_through_qty": ptq, "put_through_value": ptv}


def _tape_row(volume, side, avo, ts="2026-08-07 09:15:06"):
    return {"timestamp": ts, "volume": volume, "accumulated_volume": avo, "side": side}


class FrozenContractMatchesRetainedEvidence(unittest.TestCase):
    def test_frozen_reconciliations_are_reproduced_from_retained_raw_artifacts(self):
        self.assertTrue(scope.verify_against_retained_evidence())

    def test_active_contract_does_not_require_the_evidence_directory_to_exist(self):
        # Regression guard: active_contract() must work even if operations-review/ moves or
        # is pruned, because kbs_capability_matrix.py depends on it at import-adjacent time.
        contract = scope.active_contract()
        self.assertEqual(contract["provider"], "KBS")

    def test_active_contract_is_deterministic(self):
        self.assertEqual(scope.active_contract(), scope.active_contract())


class ParsingFailsClosed(unittest.TestCase):
    def test_price_board_missing_ticker_refused(self):
        with self.assertRaises(scope.TradeScopeError):
            scope.parse_price_board([_board(ticker="HPG")], ticker="VNM")

    def test_price_board_missing_field_refused(self):
        with self.assertRaises(scope.TradeScopeError):
            scope.parse_price_board([{"SB": "HPG", "TD": "07/08/2026", "PTQ": 0, "PTV": 0}], ticker="HPG")

    def test_intraday_row_ticker_mismatch_refused(self):
        raw = [{"SB": "VNM", "t": "2026-08-07 09:15:06", "FV": 100, "AVO": 100}]
        with self.assertRaises(scope.TradeScopeError):
            scope.parse_intraday_tape(raw, ticker="HPG")

    def test_intraday_missing_field_refused(self):
        raw = [{"SB": "HPG", "t": "2026-08-07 09:15:06"}]
        with self.assertRaises(scope.TradeScopeError):
            scope.parse_intraday_tape(raw, ticker="HPG")

    def test_blank_side_preserved_as_none_not_coerced(self):
        raw = [{"SB": "HPG", "t": "2026-08-07 09:15:06", "LC": "", "FV": 100, "AVO": 100}]
        rows = scope.parse_intraday_tape(raw, ticker="HPG")
        self.assertIsNone(rows[0]["side"])

    def test_real_side_preserved(self):
        raw = [{"SB": "HPG", "t": "2026-08-07 09:15:06", "LC": "B", "FV": 100, "AVO": 100}]
        rows = scope.parse_intraday_tape(raw, ticker="HPG")
        self.assertEqual(rows[0]["side"], "B")


class SessionCoverageGuard(unittest.TestCase):
    def test_empty_tape_refused(self):
        with self.assertRaises(scope.TradeScopeError):
            scope.assert_full_session_coverage([])

    def test_tape_not_starting_near_open_refused(self):
        tape = [_tape_row(100, "B", 100, ts="2026-08-07 10:00:00"), _tape_row(100, "B", 200, ts="2026-08-07 14:45:00")]
        with self.assertRaises(scope.TradeScopeError):
            scope.assert_full_session_coverage(tape)

    def test_tape_not_ending_near_close_refused(self):
        tape = [_tape_row(100, "B", 100, ts="2026-08-07 09:15:00"), _tape_row(100, "B", 200, ts="2026-08-07 11:00:00")]
        with self.assertRaises(scope.TradeScopeError):
            scope.assert_full_session_coverage(tape)

    def test_full_session_tape_accepted(self):
        tape = [_tape_row(100, "B", 100, ts="2026-08-07 09:15:06"), _tape_row(100, "S", 200, ts="2026-08-07 14:45:09")]
        scope.assert_full_session_coverage(tape)  # must not raise


class ReconciliationLogic(unittest.TestCase):
    def test_exact_reconciliation_with_put_through_demonstrates_exclusion(self):
        tape = [_tape_row(900_000, "B", 900_000), _tape_row(100_000, None, 1_000_000)]
        board = _board(tt=1_000_000, ptq=50_000)
        result = scope.reconcile_session(tape=tape, board=board)
        self.assertEqual(result["residual"], 0)
        self.assertTrue(result["tape_matches_accumulated_exactly"])
        self.assertTrue(result["put_through_demonstrated_excluded"])

    def test_residual_present_does_not_demonstrate_exclusion(self):
        """A truncated or mismatched tape must never be read as proving exclusion --
        there is room inside the residual for put-through to be hiding."""
        tape = [_tape_row(900_000, "B", 900_000)]
        board = _board(tt=1_000_000, ptq=50_000)  # tape only covers 900,000 of 1,000,000
        result = scope.reconcile_session(tape=tape, board=board)
        self.assertNotEqual(result["residual"], 0)
        self.assertFalse(result["tape_matches_accumulated_exactly"])
        self.assertFalse(result["put_through_demonstrated_excluded"])

    def test_zero_put_through_exact_match_is_not_a_demonstrated_exclusion(self):
        """No put-through reported at all is a session with nothing to exclude, not
        evidence of exclusion -- the finding requires put_through_qty > 0 and unaccounted."""
        tape = [_tape_row(1_000_000, "B", 1_000_000)]
        board = _board(tt=1_000_000, ptq=0)
        result = scope.reconcile_session(tape=tape, board=board)
        self.assertTrue(result["tape_matches_accumulated_exactly"])
        self.assertFalse(result["put_through_demonstrated_excluded"])


class DimensionQualification(unittest.TestCase):
    def _two_exact_reconciliations(self, ptq=(50_000, 60_000)):
        tapes = [
            (
                [_tape_row(800_000, "B", 800_000), _tape_row(200_000, None, 1_000_000)],
                _board(ticker="HPG", tt=1_000_000, ptq=ptq[0]),
            ),
            (
                [_tape_row(700_000, "S", 700_000), _tape_row(300_000, None, 1_000_000)],
                _board(ticker="VNM", tt=1_000_000, ptq=ptq[1]),
            ),
        ]
        return [scope.reconcile_session(tape=t, board=b) for t, b in tapes]

    def test_two_independent_exact_reconciliations_resolve_continuous_auction_negotiated(self):
        recons = self._two_exact_reconciliations()
        dims = scope.qualify_dimensions(recons)
        self.assertEqual(dims[scope.DIMENSION_CONTINUOUS]["inclusion_state"], scope.INCLUDED)
        self.assertEqual(dims[scope.DIMENSION_AUCTION]["inclusion_state"], scope.INCLUDED)
        self.assertEqual(dims[scope.DIMENSION_NEGOTIATED]["inclusion_state"], scope.EXCLUDED)

    def test_odd_lot_never_resolves_from_this_evidence(self):
        recons = self._two_exact_reconciliations()
        dims = scope.qualify_dimensions(recons)
        self.assertEqual(dims[scope.DIMENSION_ODD_LOT]["inclusion_state"], scope.UNKNOWN)
        self.assertEqual(dims[scope.DIMENSION_ODD_LOT]["qualification"], tiers.UNKNOWN)

    def test_single_observation_is_insufficient(self):
        recons = self._two_exact_reconciliations()[:1]
        dims = scope.qualify_dimensions(recons)
        for record in dims.values():
            self.assertEqual(record["inclusion_state"], scope.UNKNOWN)

    def test_resolved_dimensions_carry_empirically_deduced_never_documented_verified(self):
        recons = self._two_exact_reconciliations()
        dims = scope.qualify_dimensions(recons)
        for dimension, record in dims.items():
            if record["inclusion_state"] != scope.UNKNOWN:
                self.assertEqual(record["qualification"], tiers.EMPIRICALLY_DEDUCED)
                self.assertFalse(tiers.may_claim_official_semantics(record["qualification"]))


class ContractFailClosed(unittest.TestCase):
    def test_liquidity_actionable_always_false(self):
        contract = scope.active_contract()
        self.assertFalse(contract["liquidity_actionable"])

    def test_assert_contract_fail_closed_refuses_wrong_provider(self):
        contract = dict(scope.active_contract())
        contract["provider"] = "VCI"
        with self.assertRaises(scope.TradeScopeError):
            scope.assert_contract_fail_closed(contract)

    def test_assert_contract_fail_closed_refuses_liquidity_actionable_true(self):
        contract = dict(scope.active_contract())
        contract["liquidity_actionable"] = True
        with self.assertRaises(scope.TradeScopeError):
            scope.assert_contract_fail_closed(contract)

    def test_assert_contract_fail_closed_refuses_odd_lot_resolved(self):
        contract = {k: dict(v) if k == "dimensions" else v for k, v in scope.active_contract().items()}
        contract["dimensions"] = dict(contract["dimensions"])
        contract["dimensions"][scope.DIMENSION_ODD_LOT] = {
            **contract["dimensions"][scope.DIMENSION_ODD_LOT],
            "inclusion_state": scope.INCLUDED,
        }
        with self.assertRaises(scope.TradeScopeError):
            scope.assert_contract_fail_closed(contract)

    def test_overall_state_is_partial_not_full_qualification(self):
        contract = scope.active_contract()
        self.assertEqual(contract["overall_composition_state"], "partial_composition_qualified")
        self.assertNotEqual(contract["overall_composition_state"], "qualified")


if __name__ == "__main__":
    unittest.main()
