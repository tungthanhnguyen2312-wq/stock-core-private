"""October 2 offline retained acceptance: stream sources, emit one session matrix."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import sys
import time
from collections import Counter,defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/"tests"))
import stocklookup_core.decision.integrated_investment_decision_product as product
import contextual_technical_dispatch as dispatch
import technical_relationship_view as bridge
import volume_and_flow_context_v2 as flow
import prospective_pit_capture_retention as capture
import stocklookup_core.research.thesis_evidence_contract as c
import stocklookup_core.research.thesis_evidence_adapters as adapters
import stocklookup_core.research.thesis_evidence_matrix as matrix
from bounded_artifact_stream import source_hash,stream_artifact
from test_production_call_shape_smoke import _offline_smoke_guard

START="ac50ef09cc2c42b4aa6cd83cc114696269cf2f5d"
NEXT="THESIS_EVIDENCE_MATRIX_AND_CONFLICT_ENGINE_V1_STAGE_2_PRODUCTION_INTEGRATION"
ACCEPTANCE="thesis_evidence_matrix_stage_1_acceptance/v1"
SESSION_ARTIFACT="thesis_evidence_matrix_session/v1"


def memory():
    import psutil
    info=psutil.Process().memory_info()
    return {"rss_bytes":info.rss,"peak_rss_bytes":getattr(info,"peak_wset",info.rss)}


def run(args):
    started=time.perf_counter();timings={};root=Path(args.source_root).resolve()
    runtime=Path(args.runtime_root).resolve();session="2026-10-02"
    baseline=json.loads((ROOT/"docs/internal/TECHNICAL_VOLUME_FLOW_V2_MIGRATION_ACCEPTANCE.json").read_text(encoding="utf-8"))
    paths={"decision":root/"operations-review/canonical-post-close-v1"/session/"enrichment/integrated_investment_decision_product.json",
        "technical_v2":Path(args.technical),"volume_flow_v2":Path(args.flow)}
    outputs=[Path(args.matrix_output).resolve(),Path(args.output).resolve()]
    if len(set(outputs))!=2: raise ValueError("THESIS_OUTPUTS_MUST_DIFFER")
    for output in outputs:
        if output in {p.resolve() for p in paths.values()} or any(output.is_relative_to(p) for p in (root/"operations-review",root/"data",root/"config",runtime)):
            raise ValueError("THESIS_OUTPUT_CANNOT_MUTATE_SOURCE_OR_PRODUCTION")
        output.parent.mkdir(parents=True,exist_ok=True)
    before={k:source_hash(p) for k,p in paths.items()}
    assert before["decision"]==baseline["source_hashes"]["decision"]
    for key,name in (("technical_v2","technical-v2-20261002.ndjson"),("volume_flow_v2","volume-flow-v2-20261002.json")):
        assert before[key]==baseline["output_artifacts"][name]["sha256"]
    protected={root/p:digest for p,digest in baseline["pit_compatibility"]["old_t0_sha256"].items()}
    protected.update({ROOT/p:digest for p,digest in baseline["pit_compatibility"]["modules_sha256"].items()})
    assert all(source_hash(p)==digest for p,digest in protected.items())
    technical_items={};flow_items={};technical_ids={};technical_views={}
    distributions=defaultdict(Counter);roles=Counter();unknowns=Counter();reasons=Counter();blockers=Counter()
    materiality=Counter();correlation=defaultdict(Counter);foreign=Counter();stages=Counter();source_vocab=defaultdict(Counter);factual_coverage=Counter()
    cases={};parity=hashlib.sha256();record_deltas=0;guards=Counter();count=0
    with _offline_smoke_guard() as calls:
        moment=time.perf_counter()
        with paths["technical_v2"].open(encoding="utf-8") as source:
            for line in source:
                row=json.loads(line);ticker=row["ticker"];context=row["contextual_technical"]
                assert ticker not in technical_items and context["as_of_session"]==session
                assert context["evaluation_scope"]=="REPLAY_DIAGNOSTIC" and context["authority_status"]=="NON_AUTHORITATIVE"
                technical_items[ticker]=adapters.adapt_technical(context)
                technical_ids[ticker]=context["artifact_identity"]
                technical_views[ticker]={tf:v["view_identity"] for tf,v in bridge.build_views(context).items()}
        assert len(technical_items)==1503
        timings["technical_adapter_seconds"]=time.perf_counter()-moment
        print("TECHNICAL_ADAPTED",len(technical_items),flush=True)
        moment=time.perf_counter()
        def flow_record(t,row):
            assert t not in flow_items
            for native in row["items"]:
                assert native["session"]==session and native["knowledge_stage"]=="POST_T0_ENRICHED"
                if native["domain"]=="VOLUME":
                    assert native["technical_context_identity"]==technical_ids[t]
                    assert native["technical_participation_relationship"]["view_identity"]==technical_views[t][native["horizon"].split("/")[0]]
                if native["participant"]=="FOREIGN":
                    foreign["in_cohort/"+native["horizon"]]+=bool(native["coverage_scope"]["in_cohort"])
                    foreign["qualified/"+native["horizon"]]+=native["status"] in flow.USABLE
            flow_items[t]=adapters.adapt_flow_record(row)
        meta,digest,flow_count=stream_artifact(paths["volume_flow_v2"],excluded={"artifact_identity","artifact_sha256"},on_record=flow_record)
        assert meta["contract_version"]==flow.CONTRACT_VERSION and digest==meta["artifact_sha256"] and flow_count==1683
        timings["flow_adapter_seconds"]=time.perf_counter()-moment
        print("FLOW_ADAPTED",flow_count,flush=True)
        moment=time.perf_counter()
        target=outputs[0];pending=target.with_suffix(target.suffix+".pending")
        with pending.open("w",encoding="utf-8",newline="\n") as output:
            output.write(c.canonical({"contract_version":SESSION_ARTIFACT,"session":session,"source_hashes":before,
                "evaluation_scope":"REPLAY_DIAGNOSTIC","authority_status":"NON_AUTHORITATIVE","non_voting":True})+"\n")
            def decision_record(t,row):
                nonlocal record_deltas,count
                original=c.canonical(row)
                for name,value in row["evidence_axes"].items():
                    source_vocab[name+"/state"][str(value.get("state"))]+=1
                reference={"decision_identity":row["decision_identity"],"research_action_posture":row["research_action_posture"]}
                items=adapters.adapt_integrated(row)+technical_items.pop(t,[])+flow_items.pop(t)
                result=matrix.build_matrix(ticker=t,session=session,items=items,decision_reference=reference,registers=adapters.registers(row),evaluation_scope="REPLAY_DIAGNOSTIC")
                matrix.verify_matrix(result)
                # Every retained card is invariant to input order and duplicate copies.
                reordered=matrix.build_matrix(ticker=t,session=session,items=list(reversed(items))+items,decision_reference=reference,registers=adapters.registers(row),evaluation_scope="REPLAY_DIAGNOSTIC")
                assert result==reordered
                for item in result["items"]:
                    roles[item["role"]]+=1;materiality[item["materiality"]]+=1;stages[item["knowledge_stage"]]+=1
                    reasons.update(item["reason_codes"]);blockers.update(item["blocker_codes"])
                    if item["state"]=="UNKNOWN": unknowns[item["unknown_class"]]+=1
                    factual_coverage[item["axis"]+"/facts_present"]+=item["facts_present"]
                    factual_coverage[item["axis"]+"/fact_eligible"]+=item["fitness"]["fact_eligible"]
                    factual_coverage[item["axis"]+"/fresh_fact_eligible"]+=item["fitness"]["fact_eligible"] and item["freshness"] in c.FRESH
                    factual_coverage[item["axis"]+"/direction_eligible"]+=item["fitness"]["direction_eligible"]
                    guards["unknown_direction"]+=item["state"]=="UNKNOWN" and item["fitness"]["direction_eligible"]
                    guards["stale_direction"]+=item["freshness"] not in c.FRESH and item["fitness"]["direction_eligible"]
                    guards["context_primitive_direction"]+=item["sub_axis"] in {"patterns","volatility","technical_native_volume_copy"} and item["fitness"]["direction_eligible"]
                    guards["foreign_market_breadth"]+=item["axis"]=="PARTICIPANT_FLOW" and item["coverage"].get("is_market_representative") is True
                for view, body in result["views"].items():
                    distributions[view+"/availability"][body["availability"]]+=1
                    guards["post_in_t0"]+=view=="T0_THESIS_VIEW" and bool(body["evidence_identities"])
                    for lens, projection in body["lenses"].items():
                        prefix=view+"/"+lens
                        distributions[prefix+"/lens"][projection["lens"]["state"]]+=1
                        for axis,state in projection["axes"].items():
                            distributions[prefix+"/axis/"+axis][state["state"]]+=1
                            if state["state"]=="UNKNOWN":distributions[prefix+"/axis_unknown_classes"][state["unknown_class"]]+=1
                        for event in projection["conflicts"]: distributions[prefix+"/conflicts"][event["kind"]]+=1
                        if view=="CURRENT_RESEARCH_VIEW":
                            groups=projection["groups"]
                            correlation[lens]["input_members"]+=len(items)
                            correlation[lens]["semantic_groups"]+=len(groups)
                            correlation[lens]["folded_members"]+=sum(max(0,len(g["member_identities"])-1) for g in groups)
                            correlation[lens]["directional_groups"]+=sum(g["role"]=="PRIMARY" and g["state"] in {"SUPPORTS","OPPOSES","MIXED"} for g in groups)
                            guards["duplicate_directional_group"]+=len({(g["correlation_group"],g["knowledge_stage"]) for g in groups})!=len(groups)
                lenses=result["views"]["CURRENT_RESEARCH_VIEW"]["lenses"]
                signature=" / ".join(lenses[lens]["lens"]["state"] for lens in c.LENSES)
                if signature not in cases:
                    cases[signature]={"ticker":t,"matrix_identity":result["artifact_identity"],"card":result["decision_card"]}
                guards["second_posture"]+=result["decision_card"]["ACTION SUPPORT REFERENCE"]!={**reference,"second_posture":False}
                record_deltas+=c.canonical(row)!=original
                parity.update(c.canonical([t,row["decision_identity"],row["research_action_posture"],row["trigger"],row["invalidation"],row["portfolio_context"]]).encode())
                output.write(c.canonical(result)+"\n")
                count+=1
                if count%250==0: print("MATRICES_VERIFIED",count,flush=True)
            metadata,digest,decision_count=stream_artifact(paths["decision"],excluded=product._IDENTITY_EXCLUDED,on_record=decision_record)
        assert digest==metadata["artifact_sha256"] and decision_count==count==1683 and record_deltas==0
        assert not technical_items and not flow_items and not any(guards.values())
        pending.replace(target)
        timings["decision_stream_matrix_verify_seconds"]=time.perf_counter()-moment
        assert before=={k:source_hash(p) for k,p in paths.items()}
        assert all(source_hash(p)==digest for p,digest in protected.items())
        readiness=capture.CaptureIndex(root,cutoff="2026-10-03T23:59:59Z").readiness(session=session)
        assert readiness["complete_session_count"]==0 and readiness["first_complete_capture_session"] is None
        assert calls=={"network":0,"provider":0,"vnstock_import":0}
    warnings=[]
    for lens in c.LENSES:
        dist=distributions["CURRENT_RESEARCH_VIEW/"+lens+"/lens"]
        if dist["CONTESTED"]>0.9*count:warnings.append(lens+":MORE_THAN_90_PERCENT_CONTESTED")
    if distributions["CURRENT_RESEARCH_VIEW/"+c.LENSES[1]+"/lens"]["NOT_CONFIRMED"]>0.9*count:
        warnings.append("MORE_THAN_90_PERCENT_SHORT_NOT_CONFIRMED")
    total_conflicts=sum(sum(v.values()) for k,v in distributions.items() if k.startswith("CURRENT_RESEARCH") and k.endswith("/conflicts"))
    if total_conflicts>8*count:warnings.append("CONFLICT_EXPLOSION_REVIEW_REQUIRED")
    timings["wall_seconds"]=time.perf_counter()-started
    report=c.seal({"contract_version":ACCEPTANCE,"starting_main":START,"session":session,"authority_effect":c.AUTHORITY,
        "evaluation_scope":"REPLAY_DIAGNOSTIC","authority_status":"NON_AUTHORITATIVE","universe_denominator":count,"technical_scope":1503,
        "contracts":{"item":c.ITEM_VERSION,"matrix":matrix.CONTRACT_VERSION,"card":matrix.CARD_VERSION,"registry":c.REGISTRY_VERSION},
        "adapter_registry":adapters.REGISTRY,"source_vocabulary_counts":dict(source_vocab),"distributions":dict(distributions),
        "unknown_classes":unknowns,"reason_counts":reasons,"blocker_counts":blockers,"role_counts":roles,"materiality_counts":materiality,
        "factual_coverage_by_axis":factual_coverage,
        "knowledge_stage_counts":stages,"correlation_dedup":dict(correlation),"foreign_cohort":foreign,"representative_cases":cases,
        "pathology_guards":dict(guards),"semantic_warnings":warnings,"non_regression":{"all_decision_field_deltas":record_deltas,
            "decision_records_verified":count,"comparison_digest":parity.hexdigest(),"source_bytes_unchanged":True},
        "t0_current_separation":{"october_2_t0":"UNAVAILABLE","protected_t0_files":len(baseline["pit_compatibility"]["old_t0_sha256"]),"readiness":readiness},
        "source_hashes":before,"matrix_artifact":{"bytes":target.stat().st_size,"sha256":source_hash(target),"records":count},
        "performance":{**timings,**memory(),"json_member_limit_bytes":16*1024*1024,"source_parse_passes":{"decision":1,"technical":1,"flow":1}},
        "network_provider_calls":calls,"production_publication_writes":0,"historical_t0_writes":0,"daily_runs":0,
        "next_gate":NEXT,"next_gate_started":False,"all_assertions_passed":True},ACCEPTANCE)
    outputs[1].write_text(json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"count":count,"lens_distributions":{lens:distributions['CURRENT_RESEARCH_VIEW/'+lens+'/lens'] for lens in c.LENSES},"performance":report["performance"]}),flush=True)
    return report


def audit_session(path,report_path):
    """Reopen only the new matrix, retain explicit scope on each standalone card."""
    started=time.perf_counter();path=Path(path);report_path=Path(report_path)
    report=json.loads(report_path.read_text(encoding="utf-8"));c.verify_identity(report,ACCEPTANCE)
    assert source_hash(path)==report["matrix_artifact"]["sha256"]
    pending=path.with_suffix(path.suffix+".verified")
    cases={};count=0
    with path.open(encoding="utf-8") as source,pending.open("w",encoding="utf-8",newline="\n") as output:
        header=json.loads(next(source));assert header["evaluation_scope"]=="REPLAY_DIAGNOSTIC"
        output.write(c.canonical(header)+"\n")
        for line in source:
            old=json.loads(line);c.verify_identity(old,matrix.CONTRACT_VERSION)
            card=old["decision_card"];c.verify_identity(card,matrix.CARD_VERSION)
            reference={k:v for k,v in card["ACTION SUPPORT REFERENCE"].items() if k!="second_posture"}
            registers={k:v for k,v in card["registers"].items() if k!="evidence_staleness"}
            new=matrix.build_matrix(ticker=old["ticker"],session=old["session"],items=old["items"],
                decision_reference=reference,registers=registers,evaluation_scope="REPLAY_DIAGNOSTIC")
            assert new["views"]==old["views"] and new["items"]==old["items"]
            assert new["decision_card"]["ACTION SUPPORT REFERENCE"]==card["ACTION SUPPORT REFERENCE"]
            matrix.verify_matrix(new)
            lenses=new["views"]["CURRENT_RESEARCH_VIEW"]["lenses"]
            signature=" / ".join(lenses[lens]["lens"]["state"] for lens in c.LENSES)
            if signature not in cases:cases[signature]={"ticker":new["ticker"],"matrix_identity":new["artifact_identity"],"card":new["decision_card"]}
            output.write(c.canonical(new)+"\n");count+=1
            if count%500==0:print("FINAL_SCOPE_VERIFIED",count,flush=True)
    assert count==1683
    pending.replace(path)
    report["representative_cases"]=cases
    report["matrix_artifact"].update(bytes=path.stat().st_size,sha256=source_hash(path))
    report["final_public_verification"]={"records":count,"status":"PASS","standalone_scope":"REPLAY_DIAGNOSTIC / NON_AUTHORITATIVE"}
    report["performance"]["final_matrix_scope_and_verification_seconds"]=time.perf_counter()-started
    report["adapter_registry"]=adapters.REGISTRY
    report=c.seal(report,ACCEPTANCE)
    report_path.write_text(json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report["final_public_verification"]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("source-root","runtime-root","technical","flow","matrix-output","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    run(parser.parse_args())


if __name__=="__main__":main()
