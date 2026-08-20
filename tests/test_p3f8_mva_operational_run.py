"""Tests for P3-F8 MVA Operational Daily Run & Research Quality Validation."""
from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from field_temporal_contract import stable_id
import tools.run_p3f8_mva_operational_run as runner


class TestP3F8MVAOperationalRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact_path = runner.DEFAULT_OUTPUT_DIR / "p3f8_mva_operational_run_artifact.json"
        cls.assertTrue(cls.artifact_path.exists(), "P3-F8 artifact must exist for testing")
        cls.artifact = json.loads(cls.artifact_path.read_text(encoding="utf-8"))

    def test_artifact_schema_and_verdict(self):
        self.assertEqual("P3F8_MVA_OPERATIONAL_RUN", self.artifact["artifact_type"])
        self.assertEqual("p3f8_mva_operational_run/v1", self.artifact["contract_version"])
        self.assertEqual("P3F8_MVA_OPERATIONAL_VALIDATION_COMPLETE", self.artifact["verdict"])
        self.assertEqual("MVA_OPERATIONALLY_USABLE", self.artifact["mva_quality_gate"])

    def test_deterministic_identity_and_sha256(self):
        payload = dict(self.artifact)
        digest = payload.pop("artifact_sha256")
        identity = payload.pop("artifact_identity")
        self.assertEqual(digest, stable_id(payload))
        self.assertEqual(f"p3f8_mva_operational_run:{digest}", identity)

    def test_breadth_reconciliation_exact(self):
        breadth = self.artifact["market_summary"]["breadth"]
        advancing = breadth["advancing"]
        declining = breadth["declining"]
        unchanged = breadth["unchanged"]
        missing = breadth["missing_count"]
        denom = breadth["denominator"]
        self.assertEqual(denom, advancing + declining + unchanged + missing)
        self.assertEqual(527, denom)
        self.assertEqual(0, missing)
        self.assertTrue(self.artifact["quality_gate_checks"]["breadth_denominator_reconciles"])

    def test_proxy_and_authoritative_separation_preserved(self):
        summary = self.artifact["market_summary"]
        self.assertEqual(0, summary["authoritative_valuation_coverage"])
        self.assertEqual(9, summary["proxy_valuation_coverage"])
        self.assertTrue(self.artifact["quality_gate_checks"]["proxy_authority_separation_preserved"])

    def test_mandatory_boundaries_and_envelope(self):
        boundaries = self.artifact["boundaries"]
        self.assertEqual("MINIMUM_VIABLE_ANALYSIS_SHADOW", boundaries["runtime_mode"])
        self.assertFalse(boundaries["is_actionable_for_execution"])
        self.assertFalse(boundaries["pit_backtest_eligible"])
        self.assertEqual("BLOCKED", boundaries["liquidity_sizing_authority"])
        self.assertEqual("CURRENT_DESCRIPTIVE_ONLY", boundaries["valuation_scope"])
        self.assertFalse(boundaries["active_universe_promoted"])
        self.assertEqual("RESERVED_NOT_STARTED", boundaries["p3g"])

    def test_representative_samples_coverage(self):
        samples = self.artifact["representative_instrument_reviews"]
        categories = {s["category"][0] for s in samples}
        self.assertEqual({"A", "B", "C", "D", "E"}, categories)

    def test_zero_ticker_specific_production_branches(self):
        source = inspect.getsource(runner)
        for ticker in ("HPG", "VCB", "SSI", "GAS", "VNM"):
            self.assertNotIn(f'== "{ticker}"', source)
            self.assertNotIn(f"== '{ticker}'", source)


if __name__ == "__main__":
    unittest.main()
