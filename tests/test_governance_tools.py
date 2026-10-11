from __future__ import annotations
import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from tools.gate_check import evaluate
from unittest.mock import patch
from tools.handoff import build_handoff
class GovernanceToolsTests(unittest.TestCase):
 def test_default_handoff_does_not_read_historical_files(self):
  reads = []
  real = Path.read_text
  def wrapped(self, *args, **kwargs):
   reads.append(self.name)
   return real(self, *args, **kwargs)
  with patch.object(Path, "read_text", wrapped):
   result = build_handoff()
  self.assertFalse(result["historical_files_read"])
  self.assertNotIn("STATE.md", reads)
  self.assertNotIn("ROADMAP.md", reads)
  self.assertNotIn("DECISIONS.md", reads)
  self.assertTrue(result["native_milestone"])
  self.assertIn(result["worktree_tracked_status"], ("CLEAN", "DIRTY", "UNKNOWN"))
  self.assertEqual(result["hosted_ci"], "UNKNOWN")
  self.assertIn("exact_head_merge", result["owner_gates"])
 def test_historical_mode_is_explicit(self):
  reads = []
  real = Path.read_text
  def wrapped(self, *args, **kwargs):
   reads.append(self.name)
   return real(self, *args, **kwargs)
  with patch.object(Path, "read_text", wrapped):
   try:
    result = build_handoff(historical=True)
   except ValueError as exc:
    self.assertIn("missing_canonical_state", str(exc))
   else:
    self.assertTrue(result["historical_files_read"])
  self.assertIn("STATE.md", reads)
  self.assertIn("ROADMAP.md", reads)
 def test_unknown_basis_fails_market_gate(self):
  result = evaluate(); self.assertEqual(result["P0_basis_and_lineage"], "INCOMPLETE"); self.assertEqual(result["market_dependent_readiness"], "FAIL"); self.assertEqual(result["historical_only_hpg_vnm_readiness"], "PASS")
if __name__ == "__main__": unittest.main()
