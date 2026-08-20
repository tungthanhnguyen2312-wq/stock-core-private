"""Focused P3-F6 tests for the MVA-only provider-issued-share proxy lane."""
from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from field_temporal_contract import stable_id  # noqa: E402
import mva_provider_share_proxy as m  # noqa: E402
import p3f_current_market_valuation as p3f  # noqa: E402
import tools.run_p3f6_mva_provider_share_proxy as runner  # noqa: E402


def _envelope():
    return dict(m.REQUIRED_ENVELOPE)


def _instrument(ticker="ABC"):
    return {"canonical_ticker": ticker, "provider_symbols": {"DNSE": ticker}}


def _observation(ticker="ABC", value=100):
    return {"canonical_ticker": ticker, "value": value, "observation_date": "2026-08-14",
            "retrieved_at": "2026-08-14T16:45:00+07:00", "semantic_identity": "ISSUED_SHARES",
            "provider_source": "VCI.overview.issue_share",
            "provider_field_lineage": "Company(source='VCI').overview().issue_share"}


def _price():
    return {"status": "PRICE_READY", "value": 20_000, "session": "2026-08-19", "valuation_date": "2026-08-19",
            "reason_codes": [], "provider": "DNSE", "field_identity": "close", "price_basis": "ADJUSTED_RETROSPECTIVE",
            "price_namespace": "CURRENT_MARKET", "raw_as_traded": "NOT_PROMOTED", "payload_identity": "price-payload"}


def _issuer(entity="corporate"):
    facts = [{"canonical_metric": "net_income", "value": 1000, "qualification_state": "QUALIFIED", "reporting_period": "2024", "observed_at": "2025-01-01"},
             {"canonical_metric": "shareholders_equity", "value": 10_000, "qualification_state": "QUALIFIED", "reporting_period": "2024", "observed_at": "2025-01-01"},
             {"canonical_metric": "revenue", "value": 20_000, "qualification_state": "QUALIFIED", "reporting_period": "2024", "observed_at": "2025-01-01"},
             {"canonical_metric": "total_interest_bearing_debt", "value": 500, "qualification_state": "QUALIFIED", "reporting_period": "2024", "observed_at": "2025-01-01"},
             {"canonical_metric": "cash_and_equivalents", "value": 100, "qualification_state": "QUALIFIED", "reporting_period": "2024", "observed_at": "2025-01-01"}]
    if entity == "bank":
        facts = [{"canonical_metric": "net_profit_parent", "value": 1000, "qualification_state": "QUALIFIED", "reporting_period": "2024", "observed_at": "2025-01-01"},
                 {"canonical_metric": "total_equity", "value": 10_000, "qualification_state": "QUALIFIED", "reporting_period": "2024", "observed_at": "2025-01-01"}]
    return {"issuer_identity": {"ticker": "ABC", "entity_type": entity}, "facts": facts}


class ProxyPolicyTests(unittest.TestCase):
    def test_issued_share_proxy_never_aliases_common_or_promotes_source(self):
        result = m.qualify_provider_issued_shares_proxy(_instrument(), _observation(), valuation_date="2026-08-19", safety_state={"authority": "provider_reported_lagged"}, envelope=_envelope())
        self.assertEqual("ISSUED_SHARES", result["semantic_identity"])
        self.assertEqual("NOT_PROMOTED", result["source_authority"])
        self.assertFalse(result["official_share_authority"])
        self.assertFalse(result["common_outstanding_equivalence"])
        self.assertEqual("PROXY_STALE", result["status"])
        self.assertTrue(result["mva_proxy_eligible"])

    def test_shadow_envelope_and_corporate_action_ambiguity_fail_closed(self):
        denied = m.qualify_provider_issued_shares_proxy(_instrument(), _observation(), valuation_date="2026-08-19", safety_state={"authority": "provider_reported_lagged"}, envelope={})
        blocked = m.qualify_provider_issued_shares_proxy(_instrument(), _observation(), valuation_date="2026-08-19", safety_state={"authority": "provider_reported_unverifiable_freshness"}, envelope=_envelope())
        self.assertEqual("PROXY_NOT_ALLOWED", denied["status"])
        self.assertEqual("PROXY_CORPORATE_ACTION_BLOCKED", blocked["status"])
        self.assertFalse(blocked["mva_proxy_eligible"])

    def test_distinct_proxy_market_cap_and_formula_reuse(self):
        share_proxy = m.qualify_provider_issued_shares_proxy(_instrument(), _observation(), valuation_date="2026-08-19", safety_state={"authority": "provider_reported_lagged"}, envelope=_envelope())
        cap = m.build_provider_proxy_market_cap(_price(), share_proxy, envelope=_envelope())
        row = m.evaluate_mva_proxy_issuer(_issuer(), price=_price(), proxy=share_proxy, envelope=_envelope())
        direct = p3f._evaluate_issuer(_issuer(), price=_price(), shares={"status": "PROXY_SHARE_READY", "value": 100, "reason_codes": []})
        self.assertEqual("market_cap_provider_issued_share_proxy", cap["metric_identity"])
        self.assertEqual(2_000_000, cap["value"])
        self.assertNotIn("market_cap", row)
        self.assertEqual("MVA_PROXY_READY", row["methods"]["P/E"]["status"])
        self.assertEqual(direct["methods"]["P/E"]["value"], row["methods"]["P/E"]["value"])

    def test_sector_gating_is_preserved(self):
        share_proxy = m.qualify_provider_issued_shares_proxy(_instrument(), _observation(), valuation_date="2026-08-19", safety_state={"authority": "provider_reported_lagged"}, envelope=_envelope())
        bank = m.evaluate_mva_proxy_issuer(_issuer("bank"), price=_price(), proxy=share_proxy, envelope=_envelope())
        self.assertEqual("MVA_PROXY_READY", bank["methods"]["P/E"]["status"])
        self.assertEqual("NOT_APPLICABLE", bank["methods"]["EV/Sales"]["status"])


class ArtifactTests(unittest.TestCase):
    def test_artifact_separates_authority_and_proxy_and_is_deterministic(self):
        path = runner.DEFAULT_OUTPUT_DIR / "p3f6_mva_provider_share_proxy_artifact.json"
        artifact = json.loads(path.read_text(encoding="utf-8"))
        payload = dict(artifact); digest = payload.pop("artifact_sha256"); identity = payload.pop("artifact_identity")
        self.assertEqual(digest, stable_id(payload))
        self.assertEqual(f"p3f6_mva_provider_share_proxy:{digest}", identity)
        self.assertEqual(0, artifact["authoritative_coverage_unchanged"]["share_ready"])
        self.assertEqual(0, artifact["authoritative_coverage_unchanged"]["both_ready"])
        self.assertGreater(artifact["mva_proxy_valuation_coverage"]["proxy_both_ready"], 0)
        self.assertNotIn("authoritative_both_ready", artifact["mva_proxy_valuation_coverage"])
        self.assertEqual("MINIMUM_VIABLE_ANALYSIS_SHADOW", artifact["runtime_mode"])
        self.assertFalse(artifact["is_actionable_for_execution"])

    def test_no_ticker_specific_production_branch_or_actionable_recommendation_output(self):
        for source in (inspect.getsource(m), inspect.getsource(runner)):
            for ticker in ("HPG", "VCB", "SSI", "GAS", "VNM"):
                self.assertNotIn(f'== "{ticker}"', source)
                self.assertNotIn(f"== '{ticker}'", source)
        artifact = json.loads((runner.DEFAULT_OUTPUT_DIR / "p3f6_mva_provider_share_proxy_artifact.json").read_text(encoding="utf-8"))
        self.assertEqual("PASS", artifact["ticker_specific_branch_audit"]["status"])
        self.assertNotIn("recommendation", json.dumps(artifact).lower())


if __name__ == "__main__":
    unittest.main()
