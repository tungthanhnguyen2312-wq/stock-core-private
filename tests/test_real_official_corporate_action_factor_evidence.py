import json
import unittest
from pathlib import Path

from real_official_corporate_action_factor_evidence import UNSUPPORTED_EVENT_TYPE_REASON, index_gap_classification, select_candidates


def _event(ticker, event_type, ex_date, **more):
    return {"ticker": ticker, "event_id": ticker + ex_date, "event_type": event_type,
            "ex_date": ex_date, "event_state": "PAST", "source": "hnx_official_rights_event_index/v1", **more}


class CandidateSelectionTests(unittest.TestCase):
    def test_explicit_ex_date_is_other_evidence_gap_not_missing_ex_date(self):
        classification, reasons = index_gap_classification(_event("VC3", "STOCK_DIVIDEND", "2026-08-27"))
        self.assertEqual(classification, "OTHER_EVIDENCE_GAP")
        self.assertIn("explicit_official_ex_date_present", reasons)

    def test_selection_is_date_ranked_and_refuses_future_execution_as_executed(self):
        selected = select_candidates([
            _event("D11", "STOCK_DIVIDEND", "2026-08-21", execution_date="2026-11-19"),
            _event("IPA", "BONUS", "2026-08-21"),
            _event("VC3", "STOCK_DIVIDEND", "2026-08-27"),
            _event("NAG", "STOCK_DIVIDEND", "2026-08-19"),
            _event("HCC", "STOCK_DIVIDEND", "2026-08-19"),
        ], reference_tickers={"D11", "IPA", "VC3", "NAG", "HCC"}, cutoff_date="2026-09-15")
        self.assertEqual([row["ticker"] for row in selected["candidates"]], ["VC3", "IPA", "HCC"])
        self.assertIn("future_execution_date_not_treated_as_executed",
                      {row["reason"] for row in selected["excluded_completed_event_reasons"]})
        for row in selected["candidates"]:
            self.assertEqual(row["official_ex_date_status"], "EXPLICIT_OFFICIAL")
            self.assertEqual(row["ledger_qualification"], "NOT_EVALUATED_NOT_LEDGER_OBSERVATION")
            self.assertEqual(row["factor_chain_classification"], "OTHER_EVIDENCE_GAP")
            self.assertEqual(row["pit_series_status"], "NOT_EVALUATED_NO_REAL_FACTOR_CHAIN_QUALIFIED")

    def test_retained_hose_listing_precedes_newer_non_hose_event(self):
        selected = select_candidates(
            [_event("HNX", "STOCK_DIVIDEND", "2026-08-27"), _event("HOS", "BONUS", "2026-06-26")],
            reference_tickers={"HNX", "HOS"}, cutoff_date="2026-09-29",
            listing_by_ticker={"HNX": {"exchange_or_market": "HNX_LISTED"}, "HOS": {"exchange_or_market": "HOSE"}},
            admitted_route_by_ticker={"HNX": True, "HOS": True},
        )
        self.assertEqual([row["ticker"] for row in selected["candidates"]], ["HOS", "HNX"])
        self.assertIn("hose_listing", selected["selection_order"])

    def test_rights_are_recorded_as_unsupported_not_factor_candidates(self):
        selected = select_candidates(
            [_event("RGT", "RIGHTS", "2026-08-27"), _event("BON", "BONUS_SHARES", "2026-08-26")],
            reference_tickers={"RGT", "BON"}, cutoff_date="2026-09-29",
        )
        self.assertEqual([row["ticker"] for row in selected["candidates"]], ["BON"])
        self.assertEqual(selected["excluded_rights_count"], 1)
        self.assertIn(UNSUPPORTED_EVENT_TYPE_REASON, {row["reason"] for row in selected["excluded_completed_event_reasons"]})

    def test_route_then_horizon_precede_newest_ex_date(self):
        selected = select_candidates(
            [_event("NEW", "BONUS", "2026-08-23"), _event("ROUTE", "BONUS", "2026-06-01"), _event("HORIZON", "BONUS", "2026-08-27")],
            reference_tickers={"NEW", "ROUTE", "HORIZON"}, cutoff_date="2026-09-29",
            admitted_route_by_ticker={"NEW": False, "ROUTE": True, "HORIZON": False},
        )
        self.assertEqual([row["ticker"] for row in selected["candidates"]], ["ROUTE", "HORIZON", "NEW"])

    def test_retained_index_rebuilds_the_corrected_frozen_cohort(self):
        root = Path(__file__).resolve().parents[1]
        events = json.loads((root / "operations-review/current-official-event-context-integration-v1-20260824/current_official_event_context_artifact.json").read_text(encoding="utf-8"))
        universe = json.loads((root / "operations-review/current-official-market-universe-refresh-v1-20260913/current_official_market_universe_artifact.json").read_text(encoding="utf-8"))
        selected = select_candidates(events["all_current_universe_event_records"], reference_tickers=universe["records"],
                                     cutoff_date="2026-09-29", listing_by_ticker=universe["records"])
        self.assertEqual([(row["ticker"], row["event_type"], row["ex_date"]) for row in selected["candidates"]], [
            ("VBB", "BONUS", "2026-06-26"), ("KLB", "STOCK_DIVIDEND", "2025-09-24"), ("VBB", "STOCK_DIVIDEND", "2025-06-27"),
        ])
        self.assertEqual(selected["excluded_rights_count"], 41)


if __name__ == "__main__":
    unittest.main()
