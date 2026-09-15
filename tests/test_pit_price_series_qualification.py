"""Tests for pit_price_series_qualification.py.

DNSE's real bounded price-basis authority windows (HPG 2026-05-15..2026-06-03,
VCB 2026-07-13..2026-07-31; both ADJUSTED_RETROSPECTIVE) come from
dnse_ohlc_price_basis_capability.EVIDENCE_EVENTS -- real, retained evidence, not synthetic.
The corporate-action factor-chain entries combined with them are SYNTHETIC (ticker "TST" /
event ids), built the same way as test_qualified_corporate_action_factor_chain.py, so this
file can exercise QUALIFIED-series mechanics that the real retained corpus never reaches.
"""
import unittest

import official_corporate_action_ledger as ledger
import pit_price_series_qualification as pit
import price_basis_feature_fitness as fitness
import qualified_corporate_action_factor_chain as factor_chain


def _hpg_qualified_factor(ex_date="2026-05-26", knowledge_cutoff="2026-05-25T18:00:00+07:00"):
    observation = {
        "observation_id": "hpg-o1", "ticker": "HPG", "event_type": "stock_dividend",
        "lifecycle_state": "executed", "document_id": "hpg-d1", "document_type": "listing_change_notice",
        "source_authority": "HNX", "source_url": "https://www.hnx.vn/hpg",
        "content_sha256": "f" * 64, "announcement_date": "2026-05-10",
        "ex_date": ex_date, "record_date": None, "payment_or_execution_date": "2026-05-20",
        "shares_before": None, "shares_issued": 100_000, "shares_after": 1_100_000,
        "cash_amount_per_share": None, "stock_ratio": 0.1, "ratio_basis": "new_shares_per_existing_share",
        "citations": [], "absent_fields": {}, "warnings": [],
    }
    entry = ledger.build_ledger([observation])["entries"][0]
    return factor_chain.build_factor_chain_entry(entry, knowledge_cutoff=knowledge_cutoff)


class SessionQualificationTests(unittest.TestCase):
    def test_session_inside_bounded_window_with_no_applicable_event_is_qualified(self):
        result = pit.qualify_session(provider="DNSE", dataset="ohlc_1D", instrument="HPG",
                                     session="2026-05-16", decision_as_of="2026-06-01")
        self.assertEqual(result["state"], pit.QUALIFIED)
        self.assertEqual(result["raw_input_basis"], "ADJUSTED_RETROSPECTIVE")

    def test_session_outside_any_bounded_window_is_blocked(self):
        result = pit.qualify_session(provider="DNSE", dataset="ohlc_1D", instrument="HPG",
                                     session="2026-06-10", decision_as_of="2026-06-15")
        self.assertEqual(result["state"], pit.BLOCKED)
        self.assertIn(pit.REASON_RAW_INPUT_BASIS_UNQUALIFIED, result["reason_codes"])

    def test_no_provider_series_splicing_across_adjacent_windows(self):
        # A session strictly between HPG's window end (2026-06-03) and VCB's window start
        # (2026-07-13) must not borrow either neighbor's basis.
        result = pit.qualify_session(provider="DNSE", dataset="ohlc_1D", instrument="HPG",
                                     session="2026-06-20", decision_as_of="2026-06-25")
        self.assertEqual(result["state"], pit.BLOCKED)

    def test_dnse_bounded_authority_remains_bounded_to_named_tickers(self):
        result = pit.qualify_session(provider="DNSE", dataset="ohlc_1D", instrument="SSI",
                                     session="2026-05-20", decision_as_of="2026-05-25")
        self.assertEqual(result["state"], pit.BLOCKED)

    def test_qualified_applicable_factor_within_knowledge_cutoff(self):
        chain = _hpg_qualified_factor()
        self.assertEqual(chain["status"], "QUALIFIED")
        result = pit.qualify_session(provider="DNSE", dataset="ohlc_1D", instrument="HPG",
                                     session="2026-05-16", decision_as_of="2026-06-01",
                                     factor_chain_entries=[chain])
        self.assertEqual(result["state"], pit.QUALIFIED)
        self.assertIn(chain["source_event_id"], result["applicable_factor_event_ids"])

    def test_future_known_factor_rejected_for_earlier_decision_date(self):
        chain = _hpg_qualified_factor(knowledge_cutoff="2026-05-25T18:00:00+07:00")
        result = pit.qualify_session(provider="DNSE", dataset="ohlc_1D", instrument="HPG",
                                     session="2026-05-16", decision_as_of="2026-05-20",  # before knowledge_cutoff
                                     factor_chain_entries=[chain])
        self.assertEqual(result["state"], pit.BLOCKED)
        self.assertIn(pit.REASON_KNOWLEDGE_CUTOFF_AFTER_DECISION, result["reason_codes"])

    def test_unqualified_factor_blocks_the_session(self):
        unqualified_observation = {
            "observation_id": "hpg-o2", "ticker": "HPG", "event_type": "stock_dividend",
            "lifecycle_state": "announced", "document_id": "hpg-d2",
            "source_authority": "HNX", "source_url": "https://www.hnx.vn/hpg",
            "content_sha256": "e" * 64, "ex_date": "2026-05-26", "record_date": None,
            "shares_issued": 100_000, "shares_after": 1_100_000, "stock_ratio": 0.1,
            "citations": [], "absent_fields": {}, "warnings": [],
        }
        entry = ledger.build_ledger([unqualified_observation])["entries"][0]
        chain = factor_chain.build_factor_chain_entry(entry, knowledge_cutoff="2026-05-25T18:00:00+07:00")
        self.assertEqual(chain["status"], "NOT_QUALIFIED")
        result = pit.qualify_session(provider="DNSE", dataset="ohlc_1D", instrument="HPG",
                                     session="2026-05-16", decision_as_of="2026-06-01",
                                     factor_chain_entries=[chain])
        self.assertEqual(result["state"], pit.BLOCKED)
        self.assertIn(pit.REASON_FACTOR_CHAIN_INCOMPATIBLE, result["reason_codes"])


class SeriesQualificationTests(unittest.TestCase):
    def test_no_sessions_requested_is_blocked_not_filled(self):
        result = pit.qualify_pit_price_series(ticker="HPG", provider="DNSE", dataset="ohlc_1D",
                                              instrument="HPG", sessions=[], decision_as_of="2026-06-01")
        self.assertEqual(result["state"], pit.BLOCKED)
        self.assertIn(pit.REASON_NO_SESSIONS_REQUESTED, result["reason_codes"])

    def test_all_sessions_inside_window_qualify_series(self):
        sessions = ["2026-05-16", "2026-05-17", "2026-05-18"]
        chain = _hpg_qualified_factor()
        result = pit.qualify_pit_price_series(ticker="HPG", provider="DNSE", dataset="ohlc_1D",
                                              instrument="HPG", sessions=sessions,
                                              decision_as_of="2026-06-01", factor_chain_entries=[chain])
        self.assertEqual(result["state"], pit.QUALIFIED)
        self.assertEqual(result["qualified_session_count"], 3)

    def test_mixed_sessions_are_partial_not_silently_filled(self):
        sessions = ["2026-05-16", "2026-06-10"]  # second is outside the bounded window
        result = pit.qualify_pit_price_series(ticker="HPG", provider="DNSE", dataset="ohlc_1D",
                                              instrument="HPG", sessions=sessions, decision_as_of="2026-06-11")
        self.assertEqual(result["state"], pit.PARTIAL)
        self.assertEqual(result["qualified_session_count"], 1)
        self.assertEqual(result["total_session_count"], 2)

    def test_series_is_idempotent(self):
        sessions = ["2026-05-16", "2026-05-17"]
        chain = _hpg_qualified_factor()
        first = pit.qualify_pit_price_series(ticker="HPG", provider="DNSE", dataset="ohlc_1D",
                                             instrument="HPG", sessions=sessions,
                                             decision_as_of="2026-06-01", factor_chain_entries=[chain])
        second = pit.qualify_pit_price_series(ticker="HPG", provider="DNSE", dataset="ohlc_1D",
                                              instrument="HPG", sessions=sessions,
                                              decision_as_of="2026-06-01", factor_chain_entries=[chain])
        self.assertEqual(first, second)


class FeatureFitnessIntegrationTests(unittest.TestCase):
    def test_qualified_series_never_reconstructs_raw_as_traded(self):
        sessions = ["2026-05-16", "2026-05-17"]
        chain = _hpg_qualified_factor()
        series = pit.qualify_pit_price_series(ticker="HPG", provider="DNSE", dataset="ohlc_1D",
                                               instrument="HPG", sessions=sessions,
                                               decision_as_of="2026-06-01", factor_chain_entries=[chain])
        context = pit.price_series_context_for_pit(
            ticker="HPG", provider="DNSE", source_identity="test_pit_series",
            session_start=sessions[0], session_end=sessions[-1],
            series_qualification=series, factor_chain_entry=chain)
        self.assertEqual(context["observed_basis"], fitness.POINT_IN_TIME_ADJUSTED)
        self.assertNotEqual(context["observed_basis"], fitness.RAW_AS_TRADED)

    def test_pit_backtest_compatible_only_when_series_fully_qualified(self):
        sessions = ["2026-05-16", "2026-05-17"]
        chain = _hpg_qualified_factor()
        series = pit.qualify_pit_price_series(ticker="HPG", provider="DNSE", dataset="ohlc_1D",
                                               instrument="HPG", sessions=sessions,
                                               decision_as_of="2026-06-01", factor_chain_entries=[chain])
        context = pit.price_series_context_for_pit(
            ticker="HPG", provider="DNSE", source_identity="test_pit_series",
            session_start=sessions[0], session_end=sessions[-1],
            series_qualification=series, factor_chain_entry=chain)
        verdict = fitness.evaluate_feature_fitness(
            feature=fitness.PIT_BACKTEST, current_context=context, decision_as_of="2026-06-01")
        self.assertEqual(verdict["state"], fitness.BASIS_COMPATIBLE)

    def test_partial_series_never_claims_a_usable_basis_for_any_feature(self):
        # A PARTIAL series (some but not all requested sessions qualified) is deliberately
        # rendered as BASIS_UNKNOWN, not POINT_IN_TIME_ADJUSTED: this fails every price-derived
        # feature closed (BASIS_UNVERIFIED), not just PIT_BACKTEST, because the series does not
        # have one well-defined basis across the whole requested window.
        sessions = ["2026-05-16", "2026-06-10"]
        series = pit.qualify_pit_price_series(ticker="HPG", provider="DNSE", dataset="ohlc_1D",
                                               instrument="HPG", sessions=sessions, decision_as_of="2026-06-11")
        self.assertEqual(series["state"], pit.PARTIAL)
        context = pit.price_series_context_for_pit(
            ticker="HPG", provider="DNSE", source_identity="test_pit_series",
            session_start=sessions[0], session_end=sessions[-1],
            series_qualification=series, factor_chain_entry=None)
        self.assertEqual(context["observed_basis"], fitness.BASIS_UNKNOWN)
        verdict = fitness.evaluate_feature_fitness(
            feature=fitness.PIT_BACKTEST, current_context=context, decision_as_of="2026-06-11")
        self.assertEqual(verdict["state"], fitness.BASIS_UNVERIFIED)

    def test_pit_backtest_unqualified_when_chain_incomplete_but_basis_declared_pit(self):
        # The complementary case: observed_basis IS declared POINT_IN_TIME_ADJUSTED (context
        # passes the basic shape checks) but the factor chain itself is not QUALIFIED -- this is
        # the PIT-specific gate, distinct from the series-level BASIS_UNKNOWN case above.
        context = fitness.price_series_context(
            ticker="HPG", provider="DNSE", source_identity="test_pit_series",
            session_start="2026-05-16", session_end="2026-05-17",
            observed_basis=fitness.POINT_IN_TIME_ADJUSTED,
            basis_provenance=["test_pit_series"],
            factor_chain={"status": "UNQUALIFIED"},
        )
        verdict = fitness.evaluate_feature_fitness(
            feature=fitness.PIT_BACKTEST, current_context=context, decision_as_of="2026-06-11")
        self.assertEqual(verdict["state"], fitness.POINT_IN_TIME_SEMANTICS_UNQUALIFIED)

    def test_execution_raw_replay_stays_blocked_even_for_fully_qualified_pit_series(self):
        sessions = ["2026-05-16", "2026-05-17"]
        chain = _hpg_qualified_factor()
        series = pit.qualify_pit_price_series(ticker="HPG", provider="DNSE", dataset="ohlc_1D",
                                               instrument="HPG", sessions=sessions,
                                               decision_as_of="2026-06-01", factor_chain_entries=[chain])
        context = pit.price_series_context_for_pit(
            ticker="HPG", provider="DNSE", source_identity="test_pit_series",
            session_start=sessions[0], session_end=sessions[-1],
            series_qualification=series, factor_chain_entry=chain)
        verdict = fitness.evaluate_feature_fitness(feature=fitness.EXECUTION_RAW_REPLAY, current_context=context)
        self.assertEqual(verdict["state"], fitness.BASIS_INCOMPATIBLE)

    def test_ma_and_rsi_current_research_fitness_unchanged(self):
        # Regression: the vocabulary-alias addition in price_basis_feature_fitness.py must not
        # change existing CURRENT_RETROSPECTIVE_ADJUSTED research-only behavior for MA/RSI.
        context = fitness.price_series_context(
            ticker="TST", provider=None, source_identity="regression_series",
            session_start="2026-05-16", session_end="2026-05-16",
            observed_basis=fitness.CURRENT_RETROSPECTIVE_ADJUSTED,
            basis_provenance=["regression_series"],
        )
        for feature in (fitness.MA20, fitness.RSI):
            verdict = fitness.evaluate_feature_fitness(feature=feature, current_context=context)
            self.assertEqual(verdict["state"], fitness.BASIS_COMPATIBLE_RESEARCH_ONLY)


if __name__ == "__main__":
    unittest.main()
