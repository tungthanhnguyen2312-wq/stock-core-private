"""Regression tests for the additive, non-scoring current research risk register."""
from __future__ import annotations
import copy
import json
import tempfile
import unittest
from pathlib import Path

import current_research_risk_register as register
import export_ai_bundle as bundle

ROOT = Path(__file__).resolve().parents[1]
PATHS = {
    "current_official_universe": ROOT / "operations-review/current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json",
    "historical_context": ROOT / "operations-review/market-wide-historical-research-context-v1-20260824/market_wide_historical_research_context_artifact.json",
    "leadership_context": ROOT / "operations-review/current-market-sector-leadership-context-v1-20260825/current_market_sector_leadership_context_artifact.json",
    "financial_context": ROOT / "operations-review/current-financial-momentum-context-v1/current_financial_momentum_context_artifact.json",
    "corporate_event_context": ROOT / "operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json",
    "valuation_context": ROOT / "operations-review/market-wide-current-valuation-research-scaleout-v1/market_wide_current_valuation_artifact.json",
}

def _inputs() -> dict:
    return {name: json.loads(path.read_bytes().decode("utf-8")) for name, path in PATHS.items()}

class RiskMappingTests(unittest.TestCase):
    def test_technical_financial_sector_and_event_rules_preserve_their_meaning(self) -> None:
        m, w, l = register._technical_items("T", {"context_status": "AVAILABLE", "is_current_session": True, "as_of_session": "S", "structural_state": {"value": "DETERIORATION"}, "volatility_regime": {"regime": "HIGH"}, "momentum": {"sign": "NEGATIVE"}}, "h", "S")
        self.assertEqual([x["risk_type"] for x in m], ["STRUCTURAL_DETERIORATION"])
        self.assertEqual({x["risk_type"] for x in w}, {"ELEVATED_HISTORICAL_VOLATILITY_REGIME", "NEGATIVE_CURRENT_MOMENTUM"})
        self.assertFalse(l)
        m, w, l = register._financial_items("T", {"financial_momentum_state": "LOSS_MAKING_OR_STRESSED", "state_rule": "LOSS", "coverage_status": "FULL", "evidence_tier": "OFFICIAL_QUALIFIED"}, "f", "S")
        self.assertEqual(m[0]["risk_type"], "FINANCIAL_STRESS")
        self.assertFalse(w); self.assertFalse(l)
        m, w, _ = register._financial_items("T", {"financial_momentum_state": "MIXED", "state_rule": "MIX", "coverage_status": "FULL", "evidence_tier": "OFFICIAL_QUALIFIED"}, "f", "S")
        self.assertFalse(m); self.assertEqual(w[0]["severity_band"], "WATCH")
        w, l = register._leadership_items("T", {"sector_leadership_context": {"status": "UNAVAILABLE", "reason": "SECTOR_IDENTITY_UNKNOWN"}, "sector_relative_momentum": {}}, {"current_breadth_state": "BROAD_PARTICIPATION"}, "s", "S")
        self.assertFalse(w); self.assertEqual(l[0]["risk_type"], "SECTOR_CONTEXT_UNAVAILABLE")
        w, l, c = register._event_items("T", {"planned_unresolved_count": 1, "temporal_incomplete_count": 0, "data_limited_count": 0, "conflicting_count": 1}, "e", "S")
        self.assertEqual(w[0]["risk_type"], "PLANNED_NOT_EXECUTED_EVENT")
        self.assertFalse(l); self.assertEqual(c[0]["status"], "UNRESOLVED_CONFLICT")

    def test_valuation_authority_is_a_limitation_not_a_cheapness_claim(self) -> None:
        items = register._valuation_items("T", {"price_input": {"session": "S"}, "metrics": {"P/E": {"status": "RESEARCH_USABLE"}, "P/B": {"status": "BLOCKED"}}, "share_basis_input": {"authoritative_current_market_cap_eligible": False, "status": "PROVIDER_REPORTED_LAGGED", "authority": "provider"}}, "v", "S")
        self.assertEqual({x["status"] for x in items}, {"DATA_LIMITATION"})
        self.assertIn("RESEARCH_USABLE_VALUATION_NOT_AUTHORITATIVE", {x["risk_type"] for x in items})
        self.assertIn("VALUATION_METRICS_BLOCKED", {x["risk_type"] for x in items})

class CurrentRiskRegisterArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = _inputs()
        cls.artifact = register.build_artifact(**cls.inputs)

    def test_deterministic_replay_and_real_source_cases(self) -> None:
        before = copy.deepcopy(self.inputs)
        self.assertEqual(self.artifact["artifact_identity"], register.build_artifact(**self.inputs)["artifact_identity"])
        self.assertEqual(self.inputs, before)
        register.replay(self.artifact)
        self.assertTrue(any(x["risk_type"] == "FINANCIAL_STRESS" for x in self.artifact["records"]["NVL"]["material_risks"]))
        self.assertTrue(any(x["risk_type"] == "RESEARCH_USABLE_VALUATION_NOT_AUTHORITATIVE" for x in self.artifact["records"]["AAA"]["data_authority_limitations"]))
        self.assertEqual(self.artifact["official_universe_denominator"], 1507)
        self.assertEqual(self.artifact["coverage"]["ticker_coverage"], 1507)

    def test_no_scalar_probability_or_upstream_mutation(self) -> None:
        boundary = self.artifact["authority_boundary"]
        self.assertTrue(boundary["no_numeric_risk_score"])
        self.assertTrue(boundary["absence_is_not_low_risk"])
        self.assertTrue(boundary["no_upstream_decision_mutation"])
        self.assertTrue(boundary["no_sizing_or_participation"])
        self.assertNotIn("LOW_RISK", json.dumps(self.artifact))
        self.assertIn("strategy_eligibility", self.artifact["blocked_outputs"])
        self.assertIn("research_priority", self.artifact["blocked_outputs"])
        self.assertIn("entry_action", self.artifact["blocked_outputs"])
        self.assertEqual(self.artifact["source_contexts"]["historical"]["as_of"], "2026-08-24")
        self.assertEqual(self.artifact["source_contexts"]["valuation"]["as_of"], "2026-08-21")

    def test_missing_context_is_limitation_not_low_risk_and_blocked_metric_does_not_stop_register(self) -> None:
        row = self.artifact["records"]["ACM"]
        self.assertTrue(any(x["risk_type"] == "EXACT_SESSION_TECHNICAL_CONTEXT_UNAVAILABLE" for x in row["data_authority_limitations"]))
        self.assertTrue(any(x["risk_type"] == "VALUATION_METRICS_BLOCKED" for x in row["data_authority_limitations"]))
        self.assertEqual(row["risk_register_status"], "NO_MATERIAL_RISK_ESTABLISHED_FROM_AVAILABLE_EVIDENCE")

    def test_opt_in_bundle_attachment_verifies_and_preserves_decisions(self) -> None:
        entries = {"AAA": {"strategy_eligibility": "keep", "research_priority": "keep", "entry_action": "keep"}}
        original = copy.deepcopy(entries)
        self.assertEqual(bundle.attach_current_research_risk_register(entries, False, "not-read.json"), original)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "risk.json"; path.write_text(json.dumps(self.artifact), encoding="utf-8")
            result = bundle.attach_current_research_risk_register(entries, True, str(path))
            self.assertFalse(result["AAA"]["current_research_risk_register"]["is_actionable"])
            self.assertEqual(result["AAA"]["strategy_eligibility"], "keep")
            self.assertEqual(result["AAA"]["research_priority"], "keep")
            self.assertEqual(result["AAA"]["entry_action"], "keep")
            tampered = json.loads(path.read_text(encoding="utf-8")); tampered["coverage"]["watch_count"] += 1; path.write_text(json.dumps(tampered), encoding="utf-8")
            self.assertNotIn("current_research_risk_register", bundle.attach_current_research_risk_register({"AAA": {}}, True, str(path))["AAA"])

if __name__ == "__main__":
    unittest.main()
