"""Offline retained non-mutation and synthetic corrective acceptance/performance."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/"tests"))
import prospective_pit_capture_retention as store
import prospective_market_snapshot_contract as market
import prospective_t0_seal_index as seals
import governed_session_chain as calendars
from bounded_artifact_stream import source_hash
from test_production_call_shape_smoke import _offline_smoke_guard
from test_prospective_pit_capture import capture_session,DAY
from test_monday_live_readiness import sealed_fixture
from tools.run_first_real_session_acceptance import dry_run
from tools.run_prospective_pit_capture_acceptance import _receipt_inventory


def timed(fn):
    start=time.perf_counter(); value=fn(); return value,time.perf_counter()-start


def run(primary, calendar_root, *, protected, report):
    primary=Path(primary).resolve();calendar_root=Path(calendar_root).resolve();report=Path(report).resolve()
    if report.is_relative_to(primary/"operations-review") or report.is_relative_to(calendar_root/"operations-review"):
        raise ValueError("ACCEPTANCE_REPORT_MUST_BE_SEPARATE_FROM_AUTHORITY")
    start=time.perf_counter()
    prior=json.loads((ROOT/"docs/internal/PROSPECTIVE_PIT_CAPTURE_COMPLETENESS_ACCEPTANCE.json").read_bytes())
    t0={primary/path:sha for path,sha in prior["historical_t0"]["source_hashes"].items()}
    protected={label:Path(path).resolve() for label,path in protected.items()}
    frozen=("thesis_evidence_contract.py","thesis_evidence_adapters.py","thesis_evidence_matrix.py",
        "docs/thesis_evidence_matrix_stage_1_contract.md","docs/internal/THESIS_EVIDENCE_MATRIX_STAGE_1_ACCEPTANCE.json",
        "tests/test_thesis_evidence_matrix.py","contextual_technical_features.py","contextual_technical_features_v2.py",
        "volume_and_flow_context.py","technical_structure_context.py","prospective_decision_outcome_measurement.py",
        "integrated_decision_prospective_feedback.py","prospective_daily_rollforward.py")
    frozen_hashes={name:hashlib.sha256((ROOT/name).read_text(encoding="utf-8").encode()).hexdigest() for name in frozen}
    for name,digest in frozen_hashes.items():
        baseline=subprocess.check_output(["git","show","97a19163f66f3d3d4f412e8bedeafbb47ea4bd25:"+name],cwd=ROOT)
        if hashlib.sha256(baseline.replace(b"\r\n",b"\n")).hexdigest()!=digest:raise ValueError("FROZEN_SOURCE_CHANGED:"+name)
    print("HASHING_ORIGINAL_T0_AND_PROTECTED",flush=True)
    before={label:source_hash(path) for label,path in protected.items()}
    actual_t0={path:source_hash(path) for path in t0}
    if actual_t0!=t0:raise ValueError("HISTORICAL_T0_BASELINE_CHANGED")
    with _offline_smoke_guard() as network:
        receipts,classes,receipt_digest=_receipt_inventory(primary)
        original_calendars=store.load_calendars(calendar_root)
        c,calendar_seconds=timed(lambda:calendars.governed_calendar_evidence_at_cutoff(
            json.loads((ROOT/"config/governed_trading_session_calendar_v1.json").read_bytes()),original_calendars,cutoff="2026-10-03T23:59:59Z"))
        proof,continuity_seconds=timed(lambda:calendars.are_consecutive_governed_sessions("2026-10-02",DAY,"2026-10-03T23:59:59Z",c))
        unknown=calendars.are_consecutive_governed_sessions("2026-10-02",DAY,"2026-10-03T23:59:59Z",None)
        assert proof["state"]=="TRUE" and unknown["state"]=="UNKNOWN"
        assert c["unsupported_gaps"]==[{"after":"2026-09-04","before":"2026-10-02","state":"UNSUPPORTED_CALENDAR_GAP"}]
        readiness=store.CaptureIndex(primary,cutoff="2026-10-03T23:59:59Z").readiness(session="2026-10-02")
        assert readiness["complete_session_count"]==0 and readiness["first_complete_capture_session"] is None
        assert all(n==0 for n in readiness["counts_at_depth"].values())
        with tempfile.TemporaryDirectory(prefix="stocklookup-readiness-acceptance-") as temporary:
            root=Path(temporary)
            _,evidence,gate,_=capture_session(root,calendar_days=[DAY,"2026-10-06"])
            (root/store.STORE/"first_complete_capture_session.json").unlink()
            recovered,recovery_seconds=timed(lambda:store.daily_boundary(root,session=DAY,gate=gate,evidence=evidence,
                known_at=DAY+"T12:10:00Z",t0_snapshot_identity="sealed:actual-fixture"))
            assert recovered["session_capture"]["marker_status"]=="PUBLISHED"
            generation_measurements=[]
            original_generation=seals.from_snapshot
            def measured_generation(*args,**kwargs):
                result,elapsed=timed(lambda:original_generation(*args,**kwargs))
                generation_measurements.append(elapsed)
                return result
            with patch.object(seals,"from_snapshot",measured_generation):
                (context,snapshot,path,ref),generation_seconds=timed(lambda:sealed_fixture(root))
            assert len(generation_measurements)==1
            bound,lookup_seconds=timed(lambda:seals.load_verified(ref,expected_snapshot_identity=snapshot["snapshot_identity"],session=DAY))
            assert bound.bindings["VNM"][2]==context["artifact_identity"]
            sizes={"snapshot_bytes":path.stat().st_size,"index_bytes":Path(ref["path"]).stat().st_size,
                "ordinary_snapshot_payload_bytes_read":0,"ordinary_snapshot_json_parses":0}
        dry,harness_seconds=timed(lambda:dry_run(session=DAY,cutoff=DAY+"T12:10:00Z"))
        assert {row["state"] for row in dry["rows"]}=={"OPEN","PROGRESSED","STILL_BLOCKED","NOT_EVALUABLE"}
        new_receipts,new_classes,new_digest=_receipt_inventory(primary)
        assert (receipts,classes,receipt_digest)==(new_receipts,new_classes,new_digest)
        print("VERIFYING_ORIGINAL_T0_AND_PROTECTED",flush=True)
        assert before=={label:source_hash(path) for label,path in protected.items()}
        assert t0=={path:source_hash(path) for path in t0}
        assert network=={"network":0,"provider":0,"vnstock_import":0}
    body={"contract_version":"monday_live_readiness_closeout_acceptance/v1","starting_main":"97a19163f66f3d3d4f412e8bedeafbb47ea4bd25",
        "authority_effect":"NONE / MONDAY_LIVE_READINESS_ENGINEERING_ONLY","evaluation_scope":"OFFLINE_RETAINED_AND_SYNTHETIC_DIAGNOSTIC",
        "all_assertions_passed":True,"calendar":{"resolver":c,"friday_monday_proof":proof,"without_proof":unknown,
            "registration_executed":False,"existing_probe_requests_added":0,"prior_overlap_request_supported":False},
        "historical_t0":{"files":len(t0),"source_hashes":{p.relative_to(primary).as_posix():s for p,s in t0.items()},"bytes_unchanged":True,"writes":0},
        "old_receipts":{"versions":len(receipts),"classes":classes,"before_after_digest":receipt_digest,"bytes_unchanged":True},
        "protected_source_hashes":before,"protected_source_bytes_unchanged":True,"frozen_source_text_sha256":frozen_hashes,
        "real_release_readiness":{k:readiness[k] for k in ("status","first_complete_capture_session","complete_session_count","counts_at_depth","new_signals_declared","evaluation_authorized")},
        "synthetic_marker_recovery":{"status":"PASS","publication":"RECOVERED_FROM_ORIGINAL_COMPLETE_RECORD","real_marker_writes":0},
        "seal_index":sizes,"dry_run":dry,"network_provider_calls":network,"live_daily_runs":0,
        "action_posture_policy_delta":0,"thesis_stage_1":"FROZEN_OFFLINE","retained_diagnostic_recomputation":"NOT_PERFORMED_OR_MODIFIED",
        "performance_seconds":{"calendar_resolution":calendar_seconds,"continuity_lookup":continuity_seconds,"marker_recovery":recovery_seconds,
            "snapshot_and_index_generation":generation_seconds,"seal_index_generation":generation_measurements[0],
            "ordinary_seal_lookup":lookup_seconds,"acceptance_harness_dry_run":harness_seconds,
            "whole_acceptance":time.perf_counter()-start},
        "first_real_acceptance":"PENDING","next_gate":"THESIS_EVIDENCE_MATRIX_AND_CONFLICT_ENGINE_V1_STAGE_2_PRODUCTION_INTEGRATION","next_gate_started":False}
    body.update(market.content_identity(body,kind="monday_live_readiness_closeout_acceptance"))
    report.parent.mkdir(parents=True,exist_ok=True); report.write_text(json.dumps(body,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return body


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--primary-root",type=Path,required=True);p.add_argument("--calendar-root",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True);p.add_argument("--protected",action="append",default=[])
    args=p.parse_args(); r=run(args.primary_root,args.calendar_root,protected=dict(x.split("=",1) for x in args.protected),report=args.report)
    print(json.dumps({"all_assertions_passed":r["all_assertions_passed"],"performance":r["performance_seconds"]},indent=2))
