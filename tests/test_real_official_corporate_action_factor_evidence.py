import unittest

from real_official_corporate_action_factor_evidence import index_gap_classification, select_candidates


def _event(ticker, event_type, ex_date, **more):
    return {"ticker": ticker, "event_id": ticker + ex_date, "event_type": event_type,
            "ex_date": ex_date, "event_state": "PAST", "source": "hnx_official_rights_event_index/v1", **more}


class CandidateSelectionTests(unittest.TestCase):
    def test_explicit_ex_date_is_other_evidence_gap_not_missing_ex_date(self):
        classification, reasons = index_gap_classification(_event("VC3", "STOCK_DIVIDEND", "2026-08-27"))
        self.assertEqual(classification, "OTHER_EVIDENCE_GAP")
        self.assertIn("explicit_official_ex_date_present", reasons)

    def test_selection_prefers_stock_dividend_and_refuses_future_execution_as_executed(self):
        selected = select_candidates([
            _event("D11", "STOCK_DIVIDEND", "2026-08-21", execution_date="2026-11-19"),
            _event("IPA", "BONUS", "2026-08-21"),
            _event("VC3", "STOCK_DIVIDEND", "2026-08-27"),
            _event("NAG", "STOCK_DIVIDEND", "2026-08-19"),
            _event("HCC", "STOCK_DIVIDEND", "2026-08-19"),
        ], reference_tickers={"D11", "IPA", "VC3", "NAG", "HCC"}, cutoff_date="2026-09-15")
        self.assertEqual([row["ticker"] for row in selected["candidates"]], ["VC3", "HCC", "NAG"])
        self.assertIn("future_execution_date_not_treated_as_executed",
                      {row["reason"] for row in selected["excluded_completed_event_reasons"]})
        for row in selected["candidates"]:
            self.assertEqual(row["official_ex_date_status"], "EXPLICIT_OFFICIAL")
            self.assertEqual(row["ledger_qualification"], "NOT_EVALUATED_NOT_LEDGER_OBSERVATION")
            self.assertEqual(row["factor_chain_classification"], "OTHER_EVIDENCE_GAP")
            self.assertEqual(row["pit_series_status"], "NOT_EVALUATED_NO_REAL_FACTOR_CHAIN_QUALIFIED")


if __name__ == "__main__":
    unittest.main()
