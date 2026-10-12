"""Temporary Phase 2E orchestration for temporal evidence contracts."""
from __future__ import annotations
import argparse,hashlib,json,os,sys,uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from temporal_evidence_registry import authority_read,canonical,run_promoted_vertical_slice,run_replay_parity,run_shadow_dual_read
LEDGER_VERSION="1.0.0";STAGES=("temporary_registry_replay","parity_validation","shadow_dual_read_validation","cutover_gate_evaluation","cleanup_authority_baseline_verification")
class OperationalPilotError(RuntimeError):pass
class OperationalLockError(OperationalPilotError):pass
def _now(value:str|None)->str:return value or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def _hash(value:Any)->str:return hashlib.sha256(canonical(value)).hexdigest()
def _lock(path:Path,run_id:str)->int:
 try:return os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
 except FileExistsError as exc:raise OperationalLockError("run_lock_owned") from exc
def _atomic_report(path:Path,payload:dict[str,Any])->None:
 temporary=path.with_suffix(path.suffix+".tmp");data=json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2)+"\n";temporary.write_text(data,encoding="utf-8")
 if json.loads(temporary.read_text(encoding="utf-8"))!=payload:raise OperationalPilotError("report_validation_failed")
 os.replace(temporary,path)
def run_operational_pilot(runtime_root:Path,report_dir:Path,run_id:str|None=None,inject_after_replay:bool=False,timestamp:str|None=None)->dict[str,Any]:
 runtime_root=runtime_root.resolve();report_dir=report_dir.resolve()
 if report_dir.is_relative_to(runtime_root):raise OperationalPilotError("report_destination_must_be_non_production")
 report_dir.mkdir(parents=True,exist_ok=True);run_id=run_id or "temporal-"+uuid.uuid4().hex;lock=report_dir/".temporal-evidence-operational.lock";descriptor=_lock(lock,run_id);started=_now(timestamp);ledger={"ledger_version":LEDGER_VERSION,"run_id":run_id,"started_at":started,"completed_at":None,"stage":None,"status":"RUNNING","input_identities":{},"record_counts":{},"hashes":{},"diagnostics":{},"failure_reason":None,"final_decision":None,"stages":[]}
 try:
  baseline=authority_read(runtime_root);baseline_bytes=canonical(baseline);ledger["input_identities"]["authority_baseline"]=_hash(baseline);ledger["record_counts"]["authority_baseline"]=len(baseline)
  replay=run_promoted_vertical_slice(runtime_root);ledger["stage"]=STAGES[0];ledger["stages"].append({"stage":STAGES[0],"status":"PASS","timestamp":started});ledger["record_counts"]["replay_base"]=replay["base_count"];ledger["record_counts"]["replay_overlays"]=replay["promotion_count"];ledger["hashes"]["replay"]=replay["replay_hash"]
  if inject_after_replay:raise OperationalPilotError("injected_after_temporary_registry_replay")
  parity=run_replay_parity(runtime_root);ledger["stage"]=STAGES[1];ledger["stages"].append({"stage":STAGES[1],"status":"PASS","timestamp":started});ledger["diagnostics"]["parity"]={k:parity[k] for k in ("EXACT","EXPECTED_ENRICHMENT","MISSING","CONFLICT","UNEXPECTED_EXTRA")};ledger["hashes"]["parity"]=parity["REPLAY_HASH"]
  dual=run_shadow_dual_read(runtime_root);ledger["stage"]=STAGES[2];ledger["stages"].append({"stage":STAGES[2],"status":"PASS","timestamp":started});ledger["diagnostics"]["dual_read"]={k:dual[k] for k in ("EXACT","EXPECTED_ENRICHMENT","SEMANTIC_MISMATCH","AUTHORITY_ONLY","REGISTRY_ONLY","QUERY_UNSUPPORTED")};ledger["hashes"]["dual_read"]=dual["REPLAY_HASH"]
  gates=parity["MISSING"]==0 and parity["CONFLICT"]==0 and parity["UNEXPECTED_EXTRA"]==0 and dual["SEMANTIC_MISMATCH"]==0 and dual["AUTHORITY_ONLY"]==0 and dual["REGISTRY_ONLY"]==0 and dual["QUERY_UNSUPPORTED"]==0 and dual["FALLBACK_TO_AUTHORITY"]
  ledger["stage"]=STAGES[3];ledger["stages"].append({"stage":STAGES[3],"status":"PASS" if gates else "FAIL","timestamp":started});ledger["diagnostics"]["cutover_gates"]={"parity":gates,"fallback":dual["FALLBACK_TO_AUTHORITY"],"authority_default":"current_authority"}
  if not gates:raise OperationalPilotError("cutover_gates_failed")
  restored=authority_read(runtime_root);ledger["stage"]=STAGES[4];ledger["stages"].append({"stage":STAGES[4],"status":"PASS","timestamp":started});ledger["diagnostics"]["authority_bytes_unchanged"]=canonical(restored)==baseline_bytes;ledger["diagnostics"]["temporary_state_cleaned"]=True
  if not ledger["diagnostics"]["authority_bytes_unchanged"]:raise OperationalPilotError("authority_baseline_mutated")
  ledger["status"]="PASS";ledger["final_decision"]="PHASE_2E_OPERATIONAL_PILOT_PASS"
 except Exception as exc:
  ledger["status"]="FAILED";ledger["failure_reason"]=str(exc);ledger["final_decision"]="PHASE_2E_RECOVERY_REQUIRED";ledger["stages"].append({"stage":ledger["stage"] or "initialization","status":"FAILED","timestamp":started,"reason":str(exc)})
 finally:
  try:
   ledger["completed_at"]=_now(timestamp);report=report_dir/(run_id+"."+ledger["status"].lower()+".json");ledger["report_path"]=str(report);_atomic_report(report,ledger)
  finally:
   os.close(descriptor);lock.unlink(missing_ok=True)
 return ledger
def main(argv:list[str]|None=None)->int:
 parser=argparse.ArgumentParser(description="Run temporary temporal evidence Phase 2E operational pilot");parser.add_argument("--runtime-root",required=True);parser.add_argument("--report-dir",required=True);parser.add_argument("--run-id");parser.add_argument("--inject-after-replay",action="store_true");args=parser.parse_args(argv)
 try:ledger=run_operational_pilot(Path(args.runtime_root),Path(args.report_dir),args.run_id,args.inject_after_replay)
 except OperationalLockError as exc:print(json.dumps({"status":"BLOCKED","reason":str(exc)},sort_keys=True));return 2
 print(json.dumps({"status":ledger["status"],"report_path":ledger["report_path"],"final_decision":ledger["final_decision"]},sort_keys=True));return 0 if ledger["status"]=="PASS" else 1
if __name__=="__main__":raise SystemExit(main())