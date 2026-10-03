"""Explicit offline production rehearsal. Never run Daily or register real evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
import psutil

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/"tests"))
from bounded_artifact_stream import source_hash
import thesis_evidence_contract as c
import thesis_evidence_production as engine
import thesis_production_runtime as runtime
from tools.run_thesis_evidence_stage2 import retained_only_guard
from tools.run_prospective_pit_capture_acceptance import _receipt_inventory
import prospective_pit_capture_retention as captures
from daily_execution_environment import resolve_roots
from dnse_foreign_flow_store import observations_root

START="d610db689c1f512b3363e86cdf005c248343f422"


def measured(fn):
    process=psutil.Process();baseline=process.memory_info().rss
    peak={"parent_peak_rss_bytes":baseline,"child_peak_rss_bytes":0}
    stop=threading.Event()
    def sample():
        while not stop.wait(.02):
            peak["parent_peak_rss_bytes"]=max(peak["parent_peak_rss_bytes"],process.memory_info().rss)
            for child in process.children(recursive=True):
                try:peak["child_peak_rss_bytes"]=max(peak["child_peak_rss_bytes"],child.memory_info().rss)
                except psutil.Error:pass
    thread=threading.Thread(target=sample,daemon=True);thread.start();start=time.perf_counter()
    try:value=fn()
    finally:stop.set();thread.join()
    return value,{"wall_seconds":time.perf_counter()-start,"parent_baseline_rss_bytes":baseline,
        **peak,"parent_rss_growth_bytes":peak["parent_peak_rss_bytes"]-baseline,"sample_interval_seconds":.02}


def calendar_ready(calendar_root,primary,local_output):
    manifest=json.loads((calendar_root/"operations-review/pit-minimum-viable-evidence-closure-v1-20261002/source_capture_manifest.json").read_bytes())
    entries={r["label"]:r for r in manifest["captures"]}
    raw=entries["working_dates"];doc=entries["working_dates_schema_asset"]
    for item in (raw,doc):
        assert source_hash(calendar_root/item["path"])==item["sha256"] and item["http_status"]==200
    assert raw["sha256"]=="fce46fe3c9003d094ff22910d122622566d33d39076437c06a459f2511c33d6d"
    assert doc["sha256"]==captures.WORKING_DATES_DOCUMENTATION["sha256"]
    assert doc["retrieved_at"]==captures.WORKING_DATES_DOCUMENTATION["known_at"]
    # Analyze the registration tool; never invoke its mutating register function.
    import ast
    source=ROOT/"tools/register_working_dates_receipt.py";tree=ast.parse(source.read_text(encoding="utf-8"))
    assert not any(isinstance(n,ast.Import) and any(a.name.split('.')[0] in {"requests","socket","urllib"} for a in n.names) for n in ast.walk(tree))
    arguments={"source":str(calendar_root/raw["path"]),"source-sha256":raw["sha256"],"retrieved-at":raw["retrieved_at"],
        "documentation-sha256":doc["sha256"],"documentation-known-at":doc["retrieved_at"],"destination-root":str(primary)}
    command="python '"+str(primary/"tools/register_working_dates_receipt.py")+"' "+" ".join("--"+k+" '"+v.replace("'","''")+"'" for k,v in arguments.items())
    local_output.mkdir(parents=True,exist_ok=True)
    (local_output/"calendar_registration_ready.ps1").write_text(command+"\n",encoding="utf-8")
    (local_output/"calendar_registration_ready.json").write_text(json.dumps(arguments,indent=2)+"\n",encoding="utf-8")
    return {"disposition":"CALENDAR_REGISTRATION_READY_FOR_OWNER_APPROVAL","original_source_sha256":raw["sha256"],
        "original_retrieved_at":raw["retrieved_at"],"documentation_sha256":doc["sha256"],"documentation_known_at":doc["retrieved_at"],
        "registration_executed":False,"network_requests":0,"historical_extension":False,
        "registration_tool_sha256":source_hash(source),"local_command_prepared":True}


def run(args):
    primary=args.primary_root.resolve();scratch=args.output_root.resolve()
    if scratch.is_relative_to(primary/"operations-review"):raise ValueError("DIAGNOSTIC_OUTPUT_MUST_BE_SEPARATE_FROM_AUTHORITY")
    paths={"decision":args.decision,"technical":args.technical,"flow":args.flow,"stage_1_matrix":args.stage1_matrix}
    before={k:source_hash(p) for k,p in paths.items()}
    old=json.loads((ROOT/"docs/internal/THESIS_EVIDENCE_MATRIX_STAGE_1_ACCEPTANCE.json").read_bytes())
    assert before["stage_1_matrix"]==old["matrix_artifact"]["sha256"]
    previous=json.loads((ROOT/"docs/internal/MONDAY_LIVE_READINESS_CLOSEOUT_ACCEPTANCE.json").read_bytes())
    protected=previous["historical_t0"]["source_hashes"]
    frozen=("thesis_evidence_contract.py","thesis_evidence_adapters.py","thesis_evidence_matrix.py",
        "docs/thesis_evidence_matrix_stage_1_contract.md","docs/internal/THESIS_EVIDENCE_MATRIX_STAGE_1_ACCEPTANCE.json",
        "contextual_technical_features_v2.py","volume_and_flow_context_v2.py","prospective_daily_rollforward.py")
    for name in frozen:
        baseline=subprocess.check_output(["git","show",START+":"+name],cwd=ROOT).replace(b"\r\n",b"\n")
        assert (ROOT/name).read_bytes().replace(b"\r\n",b"\n")==baseline,name
    print("VERIFY_ORIGINAL_T0",flush=True)
    assert protected=={p:source_hash(primary/p) for p in protected}
    foreign_paths=list(observations_root(resolve_roots(primary).runtime_root).glob("*.json"))
    foreign_before={p.name:source_hash(p) for p in foreign_paths}
    receipts=_receipt_inventory(primary)
    with retained_only_guard() as calls:
        readiness=captures.CaptureIndex(primary,cutoff="2026-10-03T23:59:59Z").readiness(session="2026-10-02")
        assert readiness["complete_session_count"]==0 and readiness["first_complete_capture_session"] is None
        calendar=calendar_ready(args.calendar_root.resolve(),primary,scratch)
        options=dict(root=primary,session="2026-10-02",output_root=scratch,decision_path=args.decision,
            technical_path=args.technical,flow_path=args.flow,diagnostic=True)
        print("CURRENT_PRODUCTION_CHILD",flush=True)
        current,current_perf=measured(lambda:runtime.run_component(**options,stage="current"))
        assert current["status"]=="COLLECTED" and current["built_count"]==1683 and current["unavailable_count"]==0,current
        manifest_path=primary/current["path"];manifest=engine.verify_complete(manifest_path.parent)
        compact={r["ticker"]:r for line in (manifest_path.parent/"views.ndjson").open(encoding="utf-8") if (r:=json.loads(line))}
        matched=0
        print("FROZEN_STAGE_ONE_PARITY",flush=True)
        with args.stage1_matrix.open(encoding="utf-8") as source:
            header=json.loads(next(source))
            assert header["evaluation_scope"]=="REPLAY_DIAGNOSTIC"
            for line in source:
                full=json.loads(line);new=compact[full["ticker"]]
                assert new["matrix_identity"]==full["artifact_identity"]
                assert new["lenses"]==engine.compact_lenses(full["views"]["CURRENT_RESEARCH_VIEW"])
                assert new["registers"]==full["decision_card"]["registers"]
                assert full["decision_card"]["ACTION SUPPORT REFERENCE"]["decision_identity"]==new["decision_identity"]
                matched+=1
        assert matched==len(compact)==1683
        del compact
        t0,t0_perf=measured(lambda:runtime.run_component(**options,stage="t0"))
        assert t0["status"]=="UNAVAILABLE" and t0["reason"]=="VERIFIED_T0_SEAL_INDEX_UNAVAILABLE"
        retained_hashes={p.name:source_hash(p) for p in manifest_path.parent.iterdir() if p.name in {"views.ndjson","cards.ndjson","manifest.json","COMPLETE.json"}}
        retry,retry_perf=measured(lambda:runtime.run_component(**options,stage="current"))
        assert retry["artifact_identity"]==current["artifact_identity"]
        assert retained_hashes=={p.name:source_hash(p) for p in manifest_path.parent.iterdir() if p.name in retained_hashes}
        print("ONE_TICKER_REBUILD",flush=True)
        verify_command=[sys.executable,str(ROOT/"tools/run_thesis_evidence_stage2.py"),"--session","2026-10-02","--stage","current",
            "--source-root",str(primary),"--output-root",str(scratch),"--manifest",str(manifest_path),"--verify-ticker","FPT"]
        child,verifier_perf=measured(lambda:subprocess.run(verify_command,cwd=ROOT,capture_output=True,text=True,check=True))
        verified=json.loads(child.stdout);assert verified["status"]=="PASS"
        from test_thesis_evidence_stage2 import fixture,DAY,records
        synthetic={}
        for basis in ("RETROSPECTIVE_ADJUSTED","PIT_CA_ADJUSTED"):
            with tempfile.TemporaryDirectory(prefix="stage2-exact-t0-rehearsal-") as temporary:
                root=Path(temporary);options2,*_=fixture(root,basis=basis,two=True)
                built,perf=measured(lambda:engine.build(**options2,stage="t0",origin="SEAL_TIME"))
                post,_=measured(lambda:engine.build(**options2,stage="current"))
                summary=runtime.read_product_report(root/built["path"])
                assert summary["post_in_t0"]==0 and summary["action_policy_delta"]==0
                synthetic[basis]={"t0_status":built["status"],"current_status":post["status"],"t0_report":summary,"t0_performance":perf,
                    "index_lookup_snapshot_payload_parses":0,"origin":"SEAL_TIME","only_seal_time_learning_eligible":True}
        print("FAILURE_AND_PRESENTATION_TESTS",flush=True)
        junit=scratch/"stage2-tests.xml"
        result=subprocess.run([sys.executable,"-m","pytest","-q","tests/test_thesis_evidence_stage2.py","--junitxml="+str(junit)],cwd=ROOT,capture_output=True,text=True)
        assert result.returncode==0,result.stdout+result.stderr
        cases=list(ET.parse(junit).iter("testcase"))
        assert _receipt_inventory(primary)==receipts
        assert before=={k:source_hash(p) for k,p in paths.items()}
        print("VERIFY_PROTECTED_BYTES_AFTER",flush=True)
        assert protected=={p:source_hash(primary/p) for p in protected}
        assert foreign_before=={p.name:source_hash(p) for p in foreign_paths}
        assert calls=={"network":0,"provider":0,"vnstock_import":0}
    total=sum((manifest_path.parent/n).stat().st_size for n in retained_hashes)
    body={"contract_version":"thesis_stage_2_production_acceptance/v1","starting_main":START,"all_assertions_passed":True,
        "authority_effect":engine.AUTHORITY,"evaluation_scope":"REPLAY_DIAGNOSTIC / NON_AUTHORITATIVE",
        "current":{"status":current["status"],"identity":current["artifact_identity"],"records":matched,"source_parse_passes":current["performance"]["source_parse_passes"],
            "stage_1_exact_matrix_and_lens_parity":matched,"distributions":manifest["distributions"],"pathology_fail_conditions":manifest["pathology_fail_conditions"],"descriptive_warnings":manifest["descriptive_warnings"]},
        "t0":{"disposition":t0,"performance":t0_perf},"synthetic_exact_t0":synthetic,"retry":{"identity_unchanged":True,"complete_bytes_unchanged":True,"performance":retry_perf},
        "one_ticker_verifier":{"result":verified,"performance":verifier_perf},"performance":{"current":current_perf,"engine":current["performance"],"artifact_bytes":{**{n:(manifest_path.parent/n).stat().st_size for n in retained_hashes},"compact_total":total,"stage_1_full":old["matrix_artifact"]["bytes"]},
            "reduction_fraction":1-total/old["matrix_artifact"]["bytes"]},"historical_t0":{"files":len(protected),"bytes_unchanged":True,"writes":0},
        "old_receipts":{"versions":len(receipts[0]),"bytes_unchanged":True},"foreign_sources":{"files":len(foreign_paths),"bytes_unchanged":True},
        "real_release_readiness":{k:readiness[k] for k in ("status","first_complete_capture_session","complete_session_count","counts_at_depth","new_signals_declared","evaluation_authorized")},
        "source_hashes":before,"source_mutation":0,"action_policy_delta":0,"frozen_stage_1_and_v2_sources_unchanged":True,"real_calendar_registration":calendar,
        "live_daily_runs":0,"capture_marker_writes":0,"network_provider_calls":calls,"failure_and_presentation_tests":{"passed":len(cases),"names":[case.attrib["name"] for case in cases]},
        "next_gate":"FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE","next_gate_started":False}
    assert total<old["matrix_artifact"]["bytes"]
    body=c.seal(body,body["contract_version"]);args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(body,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"passed":True,"performance":body["performance"]},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("primary-root","calendar-root","decision","technical","flow","stage1-matrix","output-root","report"):
        parser.add_argument("--"+name,type=Path,required=True)
    run(parser.parse_args())
