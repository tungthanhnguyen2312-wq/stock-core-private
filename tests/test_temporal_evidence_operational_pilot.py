import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from temporal_evidence_operational_pilot import OperationalLockError,run_operational_pilot

def base():
 return {"record_id":"r1","record_type":"qualification","ticker":"VNM","period":"2024","metric":"sales","source":"qualification","temporal":{"observed_at":None,"published_at":"2025-01-01","effective_at":None,"period_end":None,"calculated_at":"2025-01-02"}}
def replay():return {"base_count":1,"promotion_count":1,"replay_hash":"replay"}
def parity():return {"MISSING":0,"CONFLICT":0,"UNEXPECTED_EXTRA":0,"EXACT":1,"EXPECTED_ENRICHMENT":1,"REPLAY_HASH":"parity"}
def dual():return {"SEMANTIC_MISMATCH":0,"AUTHORITY_ONLY":0,"REGISTRY_ONLY":0,"QUERY_UNSUPPORTED":0,"FALLBACK_TO_AUTHORITY":True,"EXACT":1,"EXPECTED_ENRICHMENT":1,"REPLAY_HASH":"dual"}
class OperationalPilotTests(unittest.TestCase):
 def _run(self,root,report,run_id="r",inject=False):
  with patch("temporal_evidence_operational_pilot.authority_read",return_value=[base()]),patch("temporal_evidence_operational_pilot.run_promoted_vertical_slice",return_value=replay()),patch("temporal_evidence_operational_pilot.run_replay_parity",return_value=parity()),patch("temporal_evidence_operational_pilot.run_shadow_dual_read",return_value=dual()):
   return run_operational_pilot(root,report,run_id,inject,"2026-07-29T00:00:00+00:00")
 def test_stage_order_atomic_report_cleanup_and_authority_baseline(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/"runtime";report=Path(d)/"reports";ledger=self._run(root,report)
   self.assertEqual(ledger["status"],"PASS");self.assertEqual([x["stage"] for x in ledger["stages"]],["temporary_registry_replay","parity_validation","shadow_dual_read_validation","cutover_gate_evaluation","cleanup_authority_baseline_verification"]);self.assertTrue(ledger["diagnostics"]["authority_bytes_unchanged"]);self.assertTrue(Path(ledger["report_path"]).exists());self.assertFalse((report/".temporal-evidence-operational.lock").exists());self.assertFalse(list(report.glob("*.tmp")));self.assertEqual(json.loads(Path(ledger["report_path"]).read_text()),ledger)
 def test_failure_ledger_recovery_and_idempotent_temporary_replay(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/"runtime";report=Path(d)/"reports";failed=self._run(root,report,"recover",True);recovered=self._run(root,report,"recover",False)
   self.assertEqual(failed["status"],"FAILED");self.assertIn("temporary_registry_replay",failed["failure_reason"]);self.assertEqual(recovered["status"],"PASS");self.assertNotEqual(failed["report_path"],recovered["report_path"]);self.assertEqual(recovered["record_counts"]["replay_base"],1);self.assertFalse((report/".temporal-evidence-operational.lock").exists())
 def test_lock_contention_and_deterministic_ledger(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/"runtime";report=Path(d)/"reports";report.mkdir();(report/".temporal-evidence-operational.lock").write_text("other")
   with self.assertRaises(OperationalLockError):self._run(root,report)
   (report/".temporal-evidence-operational.lock").unlink();first=self._run(root,report,"stable");second=self._run(root,report,"stable");self.assertEqual(first,second)
if __name__=="__main__":unittest.main()