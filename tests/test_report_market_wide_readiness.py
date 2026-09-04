"""tools/report_market_wide_readiness.py --session-date wiring.

Verifies: (1) without --session-date, behavior is byte-identical to before that flag existed
(evaluate_ticker still receives session_price=None/effective_shares=None); (2) with
--session-date, real per-ticker price/shares are resolved via
canonical_financial_bundle_section._resolve_session_inputs (reused, not reimplemented) and
threaded into evaluate_ticker; (3) an unresolvable ticker fails closed to blocked, not a crash.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import report_market_wide_readiness as runner


_STATE = {
    "state_fingerprint": "fp1",
    "tickers": [
        {"ticker": "AAA", "issuer_entity_type": "corporate", "template_family": None, "archetype_authority": None},
    ],
}
_FACTS = [{"canonical_metric": "net_income", "reporting_period": "2025-Q4", "status": "provider_reported"}]


class NoSessionDateUnchangedTests(unittest.TestCase):
    def test_evaluate_ticker_receives_none_price_and_shares_without_session_date(self):
        with mock.patch.object(runner, "_load_state", return_value=_STATE), \
             mock.patch.object(runner, "read_facts", return_value=_FACTS), \
             mock.patch.object(runner, "evaluate_ticker") as mocked_evaluate, \
             mock.patch.object(runner, "build_readiness_report", return_value={
                 "ticker_count": 1, "ready_ticker_counts": {n: 0 for n in runner.CAPABILITIES},
                 "not_applicable_ticker_counts": {n: 0 for n in runner.CAPABILITIES},
                 "enterprise_value_balance_sheet_components_ready": 0}):
            mocked_evaluate.return_value = {"ticker": "AAA", "periods": []}
            runner.main(["--runtime-root", str(ROOT)])
        mocked_evaluate.assert_called_once()
        _, kwargs = mocked_evaluate.call_args
        self.assertIsNone(kwargs["session_price"])
        self.assertIsNone(kwargs["effective_shares"])
        self.assertFalse(kwargs["price_basis_verified"])


class SessionDateWiresRealInputsTests(unittest.TestCase):
    def test_session_date_resolves_and_threads_price_and_shares(self):
        with mock.patch.object(runner, "_load_state", return_value=_STATE), \
             mock.patch.object(runner, "read_facts", return_value=_FACTS), \
             mock.patch.object(runner, "evaluate_ticker") as mocked_evaluate, \
             mock.patch.object(runner, "build_readiness_report", return_value={
                 "ticker_count": 1, "ready_ticker_counts": {n: 0 for n in runner.CAPABILITIES},
                 "not_applicable_ticker_counts": {n: 0 for n in runner.CAPABILITIES},
                 "enterprise_value_balance_sheet_components_ready": 0}):
            mocked_evaluate.return_value = {"ticker": "AAA", "periods": []}
            with mock.patch("canonical_financial_bundle_section._resolve_session_inputs",
                            return_value=(21800.0, {"value": 1000, "status": "qualified"})) as mocked_resolve, \
                 mock.patch("market_wide_current_shares_resolver._Store", return_value=object()):
                runner.main(["--runtime-root", str(ROOT), "--session-date", "2026-08-25"])
        mocked_resolve.assert_called_once()
        self.assertEqual(mocked_resolve.call_args[0][0], "AAA")
        self.assertEqual(mocked_resolve.call_args[0][3], "2026-08-25")
        _, kwargs = mocked_evaluate.call_args
        self.assertEqual(kwargs["session_price"], 21800.0)
        self.assertEqual(kwargs["effective_shares"], {"value": 1000, "status": "qualified"})
        self.assertFalse(kwargs["price_basis_verified"])

    def test_unresolvable_ticker_fails_closed_not_crash(self):
        with mock.patch.object(runner, "_load_state", return_value=_STATE), \
             mock.patch.object(runner, "read_facts", return_value=_FACTS), \
             mock.patch.object(runner, "evaluate_ticker") as mocked_evaluate, \
             mock.patch.object(runner, "build_readiness_report", return_value={
                 "ticker_count": 1, "ready_ticker_counts": {n: 0 for n in runner.CAPABILITIES},
                 "not_applicable_ticker_counts": {n: 0 for n in runner.CAPABILITIES},
                 "enterprise_value_balance_sheet_components_ready": 0}):
            mocked_evaluate.return_value = {"ticker": "AAA", "periods": []}
            with mock.patch("canonical_financial_bundle_section._resolve_session_inputs",
                            side_effect=RuntimeError("boom")), \
                 mock.patch("market_wide_current_shares_resolver._Store", return_value=object()):
                exit_code = runner.main(["--runtime-root", str(ROOT), "--session-date", "2026-08-25"])
        self.assertEqual(exit_code, 0)
        _, kwargs = mocked_evaluate.call_args
        self.assertIsNone(kwargs["session_price"])
        self.assertIsNone(kwargs["effective_shares"])


if __name__ == "__main__":
    unittest.main()
