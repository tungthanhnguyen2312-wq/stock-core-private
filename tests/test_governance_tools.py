from __future__ import annotations
import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from tools.gate_check import evaluate
from tools.handoff import build_handoff
class GovernanceToolsTests(unittest.TestCase):
 def test_handoff_reads_canonical_state_and_contract(self):
  result = build_handoff(); self.assertIn("P0", result["active_phase"]); self.assertEqual(result["price_basis_status"], "INCONCLUSIVE"); self.assertIn("no replacement price-source authority is approved", result["active_milestone"])
 def test_unknown_basis_fails_market_gate(self):
  result = evaluate(); self.assertEqual(result["P0_basis_and_lineage"], "INCOMPLETE"); self.assertEqual(result["market_dependent_readiness"], "FAIL"); self.assertEqual(result["historical_only_hpg_vnm_readiness"], "PASS")
if __name__ == "__main__": unittest.main()
