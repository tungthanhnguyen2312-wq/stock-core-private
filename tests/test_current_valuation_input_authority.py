"""P3-F2 generic current valuation-input authority contracts."""
from __future__ import annotations

import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import current_valuation_input_authority as m  # noqa: E402
from p3f_current_market_valuation import market_cap_from_authority_resolver  # noqa: E402


def _instrument(ticker="ABC", symbol=None):
    return m.canonical_instrument(ticker, provider_symbol=symbol)


def _evidence(symbol="ABC", sessions=("2026-08-07",), closes=(20.0,)):
    return {"status": "OBSERVED", "provider": "DNSE", "endpoint": "/price/ohlc", "provider_symbol": symbol,
            "observations": [{"session": d, "close": c} for d, c in zip(sessions, closes)],
            "retrieved_at": "2026-08-08T01:00:00+00:00", "payload_identity": "payload", "provenance": {}}


def _share(value=100, coverage="2026-08-07"):
    return {"canonical_ticker": "ABC", "identity": m.COMMON_OUTSTANDING, "value": value,
            "effective_date": "2026-08-01", "coverage_through": coverage,
            "qualification_state": "QUALIFIED", "payload_identity": f"share-{value}"}


class SessionPolicyTests(unittest.TestCase):
    def test_after_close_uses_same_completed_session(self):
        result = m.latest_completed_vietnam_session("2026-08-07T16:00:00+07:00", ["2026-08-06", "2026-08-07"])
        self.assertEqual("2026-08-07", result["session"])
        self.assertEqual("QUALIFIED", result["status"])

    def test_before_close_rejects_incomplete_intraday_day(self):
        result = m.latest_completed_vietnam_session("2026-08-07T10:00:00+07:00", ["2026-08-06", "2026-08-07"])
        self.assertEqual("2026-08-06", result["session"])

    def test_weekend_resolves_prior_completed_weekday(self):
        result = m.latest_completed_vietnam_session("2026-08-09T12:00:00+07:00", ["2026-08-07"])
        self.assertEqual("2026-08-07", result["session"])


class PriceAuthorityTests(unittest.TestCase):
    def test_arbitrary_canonical_instrument_price_qualifies(self):
        price = m.qualify_current_market_price(_instrument("ABC"), _evidence(), requested_at="2026-08-08T12:00:00+07:00")
        self.assertEqual(m.PRICE_READY, price["status"])
        self.assertEqual(20_000.0, price["value"])
        self.assertFalse(price["historical_pit_eligible"])
        self.assertEqual("NOT_PROMOTED", price["raw_as_traded"])

    def test_incomplete_session_is_not_selected(self):
        price = m.qualify_current_market_price(_instrument(), _evidence(sessions=("2026-08-06", "2026-08-07"), closes=(19, 20)), requested_at="2026-08-07T10:00:00+07:00")
        self.assertEqual("2026-08-06", price["session"])
        self.assertEqual(m.PRICE_READY, price["status"])

    def test_missing_latest_completed_session_is_stale(self):
        price = m.qualify_current_market_price(_instrument(), _evidence(sessions=("2026-08-06",)), requested_at="2026-08-08T12:00:00+07:00")
        self.assertEqual(m.PRICE_BLOCKED, price["status"])
        self.assertEqual("STALE", price["qualification_state"])

    def test_malformed_and_instrument_mismatch_fail_closed(self):
        malformed = m.qualify_current_market_price(_instrument(), {"status": "MALFORMED", "reason_codes": ["bad"]}, requested_at="2026-08-08T12:00:00+07:00")
        mismatch = m.qualify_current_market_price(_instrument(), _evidence(symbol="OTHER"), requested_at="2026-08-08T12:00:00+07:00")
        self.assertEqual("MALFORMED", malformed["qualification_state"])
        self.assertEqual("INSTRUMENT_UNRESOLVED", mismatch["qualification_state"])

    def test_runtime_adapter_validates_payload_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / "data/dnse-market-risk-evidence/stock-ohlc"; path.mkdir(parents=True)
            (path / "XYZ.json").write_text(json.dumps({"provider": "DNSE", "symbol": "XYZ", "raw_ohlc": {"c": [1]}}), encoding="utf-8")
            result = m.dnse_current_market_observations(root, _instrument("XYZ"))
        self.assertEqual("MALFORMED", result["status"])


class ShareAuthorityTests(unittest.TestCase):
    def test_semantic_identity_separation_and_coverage(self):
        period_end = {**_share(), "identity": "period_end_shares", "value": 100}
        result = m.qualify_current_share_basis(_instrument(), [period_end], valuation_date="2026-08-07")
        self.assertEqual(m.SHARE_BLOCKED, result["status"])
        self.assertIn("period_end_shares", result["observed_identities"])

    def test_stale_and_conflicting_share_candidates_fail_closed(self):
        stale = m.qualify_current_share_basis(_instrument(), [_share(coverage="2026-08-06")], valuation_date="2026-08-07")
        conflict = m.qualify_current_share_basis(_instrument(), [_share(100), _share(101)], valuation_date="2026-08-07")
        self.assertEqual("STALE_OR_MISSING", stale["qualification_state"])
        self.assertEqual("CONFLICT", conflict["qualification_state"])

    def test_corporate_action_invalidation_never_infers_ex_date(self):
        missing_date = m.qualify_current_share_basis(_instrument(), [_share()], valuation_date="2026-08-07", corporate_actions=[{"potential_share_change": True, "lifecycle": "announced"}])
        dated = m.qualify_current_share_basis(_instrument(), [_share()], valuation_date="2026-08-07", corporate_actions=[{"potential_share_change": True, "effective_date": "2026-08-06", "lifecycle": "announced"}])
        self.assertIn("NO_EX_DATE_INFERRED", missing_date["reason_codes"][0])
        self.assertIn("INVALIDATES", dated["reason_codes"][0])


class ResolverAndScannerTests(unittest.TestCase):
    def test_resolver_is_deterministic_and_p3f_consumes_market_cap(self):
        args = {"instrument": _instrument(), "requested_at": "2026-08-08T12:00:00+07:00", "financial_input_state": {"families": {"P/E": "READY"}}, "market_evidence": _evidence(), "share_evidence": [_share()]}
        first = m.resolve_current_valuation_inputs(**args)
        second = m.resolve_current_valuation_inputs(**args)
        self.assertEqual(first, second)
        self.assertEqual(2_000_000.0, first["market_cap"])
        consumed = market_cap_from_authority_resolver(first)
        self.assertEqual("MARKET_CAP_READY", consumed["status"])
        self.assertEqual(first["market_cap"], consumed["value"])

    def test_scanner_uses_reason_codes_without_authority_widening(self):
        with tempfile.TemporaryDirectory() as tmp:
            scan = m.scan_current_valuation_input_coverage([_instrument("ABC"), _instrument("DEF")], runtime_root=Path(tmp), requested_at="2026-08-08T12:00:00+07:00")
        self.assertEqual(2, scan["counts"][m.PRICE_BLOCKED])
        self.assertIn("PRICE_EVIDENCE_MISSING", scan["blocker_distribution"])

    def test_production_module_has_zero_ticker_specific_branches(self):
        source = inspect.getsource(m)
        for ticker in ("HPG", "VCB", "SSI"):
            self.assertNotIn(f'== "{ticker}"', source)
            self.assertNotIn(f"== '{ticker}'", source)


if __name__ == "__main__":
    unittest.main()
