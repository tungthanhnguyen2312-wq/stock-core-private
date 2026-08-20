"""P3-F current-market valuation boundary and sector-gating tests."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import p3f_current_market_valuation as m  # noqa: E402


def _fact(name: str, value: int, period: str = "2024") -> dict:
    return {"canonical_metric": name, "value": value, "qualification_state": "QUALIFIED",
            "reporting_period": period, "period_end": f"{period}-12-31", "period_type": "annual",
            "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1,
            "source_lineage": {"citation_id": f"{name}-citation"}}


def _issuer(ticker="HPG", entity="corporate", facts=None) -> dict:
    return {"issuer_identity": {"ticker": ticker, "entity_type": entity}, "facts": facts or [
        _fact("net_income", 10), _fact("shareholders_equity", 100), _fact("revenue", 200),
        _fact("cash_and_equivalents", 20), _fact("total_interest_bearing_debt", 50),
    ]}


def _price(status="PRICE_READY", value=100) -> dict:
    return {"valuation_date": "2026-07-30", "status": status, "reason_codes": [] if status == "PRICE_READY" else ["PRICE_BLOCK"], "observed_value": value}


def _shares(status="SHARE_BASIS_READY", value=10) -> dict:
    return {"valuation_date": "2026-07-30", "status": status, "reason_codes": [] if status == "SHARE_BASIS_READY" else ["SHARE_BLOCK"], "value": value}


class P3FMethodTests(unittest.TestCase):
    def test_corporate_exact_methods_and_ev_components(self):
        row = m._evaluate_issuer(_issuer(), price=_price(), shares=_shares())
        self.assertEqual(1000, row["market_cap"])
        self.assertEqual("VALUATION_READY", row["methods"]["P/E"]["status"])
        self.assertEqual(100.0, row["methods"]["P/E"]["value"])
        self.assertEqual(10.0, row["methods"]["P/B"]["value"])
        self.assertEqual(5.0, row["methods"]["P/S"]["value"])
        self.assertEqual(1030, row["methods"]["EV/Sales"]["enterprise_value"])
        self.assertAlmostEqual(5.15, row["methods"]["EV/Sales"]["value"])

    def test_missing_debt_blocks_only_ev_family(self):
        facts = [fact for fact in _issuer()["facts"] if fact["canonical_metric"] != "total_interest_bearing_debt"]
        row = m._evaluate_issuer(_issuer(facts=facts), price=_price(), shares=_shares())
        self.assertEqual("VALUATION_READY", row["methods"]["P/E"]["status"])
        self.assertEqual("VALUATION_READY", row["methods"]["P/B"]["status"])
        self.assertEqual("VALUATION_READY", row["methods"]["P/S"]["status"])
        self.assertIn("FINANCIAL_IDENTITY_MISSING:total_interest_bearing_debt", row["methods"]["EV/Sales"]["blockers"])
        self.assertEqual("FINANCIAL_INPUT_READY", row["financial_readiness_by_method"]["P/S"])
        self.assertEqual("FINANCIAL_INPUT_PARTIAL", row["financial_readiness_by_method"]["EV/Sales"])

    def test_period_end_or_stale_shares_cannot_masquerade_as_current(self):
        row = m._evaluate_issuer(_issuer(), price=_price(), shares=_shares("SHARE_BASIS_BLOCKED"))
        for method in row["methods"].values():
            self.assertNotEqual("VALUATION_READY", method["status"])
            if method["valuation_method"] != "EV/EBITDA":
                self.assertIn("SHARE_BLOCK", method["blockers"])

    def test_bank_and_securities_sector_gating(self):
        bank = m._evaluate_issuer(_issuer("VCB", "bank", [
            _fact("net_profit_parent", 20), _fact("total_equity", 200)]), price=_price(), shares=_shares())
        securities = m._evaluate_issuer(_issuer("SSI", "securities", [
            _fact("profit_after_tax_parent", 10), _fact("total_equity", 100)]), price=_price(), shares=_shares())
        for row in (bank, securities):
            self.assertEqual("VALUATION_READY", row["methods"]["P/E"]["status"])
            self.assertEqual("VALUATION_READY", row["methods"]["P/B"]["status"])
            self.assertEqual("NOT_APPLICABLE", row["methods"]["EV/Sales"]["status"])
            self.assertEqual("NOT_APPLICABLE", row["methods"]["EV/EBITDA"]["status"])

    def test_bank_pe_requires_parent_profit_not_total_profit_alias(self):
        row = m._evaluate_issuer(_issuer("VCB", "bank", [_fact("net_profit_total", 20), _fact("total_equity", 200)]), price=_price(), shares=_shares())
        self.assertIn("FINANCIAL_IDENTITY_MISSING:net_profit_parent", row["methods"]["P/E"]["blockers"])
        self.assertEqual("VALUATION_READY", row["methods"]["P/B"]["status"])

    def test_all_outputs_are_non_actionable_and_non_pit(self):
        row = m._evaluate_issuer(_issuer(), price=_price(), shares=_shares())
        self.assertFalse(row["is_actionable"])
        for method in row["methods"].values():
            self.assertFalse(method["is_actionable"])
            self.assertFalse(method["historical_pit_eligible"])


class PriceAuthorityTests(unittest.TestCase):
    def test_retained_missing_frozen_session_is_blocked(self):
        report = {"status": "QUALIFIED_FOR_DNSE_CURRENT_STATE_PRICE_ANALYTICS", "observations": [], "price_basis": "ADJUSTED_CONFIRMED", "provenance": {}}
        with patch.object(m.price_basis, "current_state_eligibility", return_value={"eligible_for_current_state_price_analytics": True}), \
             patch.object(m, "_source_time", return_value="2026-08-10T11:50:20+00:00"), \
             patch.object(m, "build_current_state_price_analytics_from_evidence_store", return_value=report):
            price = m._market_price_at("HPG", Path("runtime"), "2026-07-30")
        self.assertEqual("PRICE_BLOCKED", price["status"])
        self.assertEqual(["FROZEN_VALUATION_SESSION_NOT_RETAINED"], price["reason_codes"])

    def test_current_market_never_becomes_raw_or_pit(self):
        report = {"status": "QUALIFIED_FOR_DNSE_CURRENT_STATE_PRICE_ANALYTICS", "observations": [{"session_date": "2026-07-30", "close": 21.8}], "price_basis": "ADJUSTED_CONFIRMED", "provenance": {}}
        with patch.object(m.price_basis, "current_state_eligibility", return_value={"eligible_for_current_state_price_analytics": True}), \
             patch.object(m, "_source_time", return_value="2026-08-10T11:50:20+00:00"), \
             patch.object(m, "build_current_state_price_analytics_from_evidence_store", return_value=report):
            price = m._market_price_at("HPG", Path("runtime"), "2026-07-30")
        self.assertEqual(m.CURRENT_MARKET, price["price_namespace"])
        self.assertFalse(price["historical_pit_eligible"])
        self.assertEqual("NOT_PROMOTED", price["raw_as_traded"])


class ArtifactTests(unittest.TestCase):
    def _p3e(self):
        return {"artifact_identity": "p3e:test", "refreshed_panel_data": {"issuers": [_issuer()]}}

    def test_frozen_common_session_and_deterministic_identity(self):
        with patch.object(m, "_latest_common_session", return_value="2026-07-30"), \
             patch.object(m, "_market_price_at", return_value=_price()), \
             patch.object(m, "_share_basis_at", return_value=_shares()):
            first = m.build_p3f_valuation_artifact(p3e_artifact=self._p3e(), runtime_root=Path("runtime"))
            second = m.build_p3f_valuation_artifact(p3e_artifact=self._p3e(), runtime_root=Path("runtime"))
        self.assertEqual("2026-07-30", first["frozen_valuation_session"]["valuation_date"])
        self.assertEqual(first["artifact_identity"], second["artifact_identity"])
        self.assertEqual(m.serialize(first), m.serialize(second))
        self.assertEqual(1, first["aggregate"]["metric_ready_counts"]["P/E"])

    def test_artifact_has_historical_and_dcf_blockers(self):
        with patch.object(m, "_latest_common_session", return_value=None):
            artifact = m.build_p3f_valuation_artifact(p3e_artifact=self._p3e(), runtime_root=Path("runtime"))
        self.assertEqual("HISTORICAL_VALUATION_BLOCKED", artifact["temporal_boundary"]["historical_valuation"])
        self.assertEqual("CAPEX_FCF_BLOCKED_MISSING_EXACT_IDENTITY", artifact["blocked_boundaries"]["dcf_fcff"])
        self.assertEqual("P3F_VALUATION_RESEARCH_BLOCKED", artifact["verdict"])


if __name__ == "__main__":
    unittest.main()
