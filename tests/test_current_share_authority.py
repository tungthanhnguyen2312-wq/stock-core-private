"""Focused contracts for generic current common-share authority."""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import current_share_authority as shares  # noqa: E402
import current_valuation_input_authority as valuation_inputs  # noqa: E402
from p3f_current_market_valuation import market_cap_from_authority_resolver  # noqa: E402


def _instrument() -> dict:
    return {"canonical_ticker": "ABC", "provider_symbols": {"DNSE": "ABC"}}


def _current(value: int = 100, coverage: str = "2026-08-19") -> dict:
    return {"canonical_ticker": "ABC", "identity": shares.COMMON_OUTSTANDING, "value": value,
            "effective_date": "2026-08-01", "coverage_through": coverage,
            "qualification_state": "QUALIFIED", "source_authority": "official_retained_evidence",
            "evidence_ids": ["evidence-1"], "payload_identity": f"payload-{value}"}


class CurrentShareAuthorityTests(unittest.TestCase):
    def test_exact_identity_is_required_and_distinctions_are_preserved(self):
        candidates = [
            {**_current(), "identity": "issued_shares"},
            {**_current(), "identity": "listed_shares"},
            {**_current(), "identity": "treasury_shares"},
            {**_current(), "identity": "period_end_shares"},
            {**_current(), "identity": "weighted_average_basic_shares"},
            {**_current(), "identity": "diluted_shares"},
        ]
        result = shares.build_current_share_timeline(_instrument(), candidates, valuation_date="2026-08-19")
        self.assertEqual("SHARE_BLOCKED", result["status"])
        self.assertEqual(sorted(row["identity"] for row in candidates), result["observed_identities"])

    def test_period_end_never_becomes_current_and_no_continuity_is_synthesized(self):
        period_end = {**_current(), "identity": "period_end_shares", "effective_date": "2024-12-31",
                      "coverage_through": "2024-12-31"}
        result = shares.build_current_share_timeline(_instrument(), [period_end], valuation_date="2026-08-19")
        self.assertEqual("STALE_OR_MISSING", result["qualification_state"])
        self.assertEqual("CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN", result["reason_codes"][0])

    def test_effective_coverage_and_later_actions_fail_closed(self):
        stale = shares.build_current_share_timeline(_instrument(), [_current(coverage="2026-08-18")], valuation_date="2026-08-19")
        unresolved = shares.build_current_share_timeline(
            _instrument(), [_current()], valuation_date="2026-08-19",
            corporate_actions=[{"potential_share_change": True, "record_date": "2026-08-18", "lifecycle": "planned"}],
        )
        self.assertEqual("SHARE_BLOCKED", stale["status"])
        self.assertIn("NO_EX_DATE_INFERRED", unresolved["reason_codes"][0])

    def test_unresolved_issuance_and_conflicts_are_deterministic(self):
        unresolved = shares.build_current_share_timeline(
            _instrument(), [_current()], valuation_date="2026-08-19",
            corporate_actions=[{"potential_share_change": True, "effective_date": "2026-08-18", "lifecycle": "announced"}],
        )
        conflict = shares.build_current_share_timeline(_instrument(), [_current(100), _current(101)], valuation_date="2026-08-19")
        self.assertEqual("BLOCKED", unresolved["qualification_state"])
        self.assertEqual("CONFLICT", conflict["qualification_state"])

    def test_existing_resolver_and_p3f_seam_consume_only_the_eligible_value(self):
        resolved = valuation_inputs.resolve_current_valuation_inputs(
            _instrument(), requested_at="2026-08-20T14:00:00+07:00", financial_input_state={},
            market_evidence={"status": "OBSERVED", "provider": "DNSE", "endpoint": "/price/ohlc",
                             "provider_symbol": "ABC", "observations": [{"session": "2026-08-19", "close": 20}],
                             "payload_identity": "price", "provenance": {}}, share_evidence=[_current()],
        )
        self.assertEqual(2_000_000.0, resolved["market_cap"])
        self.assertEqual("MARKET_CAP_READY", market_cap_from_authority_resolver(resolved)["status"])

    def test_source_inventory_does_not_promote_provider_or_dnse_share_authority(self):
        self.assertEqual("NOT_PROMOTED", shares.SOURCE_AUTHORITY_INVENTORY["provider_metadata_issue_share"]["authority_state"])
        self.assertEqual("NO_SHARE_FIELD_IN_EXISTING_CONTRACT", shares.SOURCE_AUTHORITY_INVENTORY["dnse_current_market_ohlc"]["authority_state"])

    def test_production_authority_modules_have_no_ticker_specific_branch(self):
        for module in (shares, valuation_inputs):
            source = inspect.getsource(module)
            for ticker in ("HPG", "SSI", "VCB", "VNM"):
                self.assertNotIn(f'== "{ticker}"', source)
                self.assertNotIn(f"== '{ticker}'", source)


if __name__ == "__main__":
    unittest.main()
