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

 def test_summary_does_not_repeat_live_repository_preflight(self):
  from tools import handoff
  real = handoff.res.evaluate
  with patch.object(handoff.res, "evaluate", wraps=real) as checked:
   result = build_handoff()
  self.assertTrue(all(call.kwargs.get("repo") is None for call in checked.call_args_list))
  self.assertEqual(result["overall"], "GIT_NOT_CHECKED")
  self.assertEqual(result["git_verification"], "SKIPPED")
  self.assertIn("native_git_checkpoints", result["facts_not_checked"])
  self.assertIn("--check", result["native_preflight_argv"])

 def test_exact_coordinator_and_lane_are_passed_to_the_native_scope_check(self):
  from tools import handoff
  state_path = ROOT / "explicit-coordinator" / "docs" / "ROADMAP_STATE.json"
  lane = dict(milestone_id="EXACT_LANE", responsible_agent="Codex", state="ACTIVE", allowed_paths=["tools/handoff.py"])
  with patch.object(handoff.res, "load_state", return_value={"development_control":{"revision":81}}) as loaded, \
       patch.object(handoff.res, "evaluate", return_value=None), \
       patch.object(handoff.res, "lane_by_id", return_value=lane) as selected, \
       patch.object(handoff.res, "check_lane", return_value={"errors":[]}) as checked:
   result = build_handoff(state_file=state_path, lane_id="EXACT_LANE")
  loaded.assert_called_once_with(state_path)
  self.assertEqual(selected.call_args.args[1], "EXACT_LANE")
  self.assertEqual(checked.call_args.args[1], "EXACT_LANE")
  self.assertEqual(result["coordinator_revision"],81)
  self.assertEqual(result["lane_scope"]["state"],"ACTIVE")
  self.assertFalse(result["lane_scope"]["runtime_authorized"])

 def test_missing_or_wrong_lane_never_becomes_admitted_from_a_copied_state(self):
  from tools import handoff
  with patch.object(handoff.res, "load_state", return_value={}), \
       self.assertRaises(handoff.res.RoadmapStateError):
   build_handoff(lane_id="WRONG_LANE")
  with patch.object(handoff.res,"lane_by_id",return_value={}), \
       patch.object(handoff.res,"check_lane",return_value={"errors":["LANE_BRANCH_MISMATCH"]}), \
       self.assertRaisesRegex(handoff.res.RoadmapStateError,"LANE_BRANCH_MISMATCH"):
   build_handoff(lane_id="EXACT_LANE")

 def test_historical_parser_reads_each_file_once_and_keeps_fields_and_error_shape(self):
  from tools import handoff
  reads=[]
  def text(path, *args, **kwargs):
   reads.append(path.name)
   return "- Exit gates: old gate\n" if path.name=="ROADMAP.md" else \
    "- Active phase: OLD\n- Active milestone: OLD_ID\n- Production state: BLOCKED\n"
  with patch.object(Path, "read_text", text):
   result=build_handoff(historical=True)
  self.assertEqual(result,dict(historical_files_read=True,active_phase="OLD",active_milestone="OLD_ID",production_state="BLOCKED",p0_exit_gates=["Exit gates: old gate"]))
  self.assertEqual(reads.count("STATE.md"),1)
  self.assertEqual(reads.count("ROADMAP.md"),1)
  with patch.object(Path,"read_text",return_value=""), self.assertRaisesRegex(ValueError,"missing_canonical_state:- Active phase"):
   build_handoff(historical=True)
if __name__ == "__main__": unittest.main()
