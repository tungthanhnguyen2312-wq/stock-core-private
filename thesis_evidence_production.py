"""Bounded retained-source production sidecars over frozen Stage-1 semantics.

Run in a child of Daily. Sources are staged on disk, verified before computation,
then processed one ticker at a time. No evidence ledger or snapshot is materialized.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

import thesis_evidence_contract as c
import thesis_evidence_adapters as adapters
import thesis_evidence_matrix as matrix
import prospective_t0_seal_index as seals
import prospective_decision_retention as retention
from bounded_artifact_stream import stream_artifact, source_hash
from atomic_io import atomic_write_json, retain_immutable_bytes

CONTRACT_VERSION="thesis_production_projection/v1"
AUTHORITY="NONE / NON_VOTING_THESIS_PRODUCTION_PROJECTION_ONLY"
REGISTRY=c.seal(adapters.REGISTRY,c.REGISTRY_VERSION)["artifact_identity"]
VIEWS={"t0":"thesis_t0_view/v1","current":"thesis_current_view/v1"}
CARDS={"t0":"thesis_t0_card/v1","current":"thesis_decision_card/v2"}
ANNOTATIONS=("ENRICHES_UNKNOWN","ADDS_FACTS_ONLY","SAME_DIRECTION_AS_T0","OPPOSES_T0","REFRESHES_STALE")


def compact_lenses(view):
    result={}
    for name,p in view["lenses"].items():
        anchor=p["lens"]["anchor_axis"]
        result[name]={**p["lens"],"anchor_state":p["axes"][anchor]["state"],
            "lens_cap":{"reason_class":p["axes"][anchor]["unknown_class"],"anchor_axis":anchor},
            "axis_states":{a:{"state":v["state"],"unknown_class":v["unknown_class"],"qualifiers":v["qualifiers"]} for a,v in p["axes"].items()},
            "group_references":[g["artifact_identity"] for g in p["groups"]],
            "conflicts":p["conflicts"],"counter_thesis":p["counter_thesis"],
            "contest_basis":[e["artifact_identity"] for e in p["conflicts"] if e["state_changing"]]}
    return result


def annotations(t0,current,items):
    result=[]
    if t0 and t0.get("availability")=="AVAILABLE":
        for lens in c.LENSES:
            for axis,new in current["lenses"][lens]["axes"].items():
                old=t0["lenses"][lens]["axes"][axis]
                state=("ENRICHES_UNKNOWN" if old["state"]=="UNKNOWN" and new["state"]!="UNKNOWN" else
                    "OPPOSES_T0" if {old["state"],new["state"]}=={"SUPPORTS","OPPOSES"} else
                    "SAME_DIRECTION_AS_T0" if new["state"] in {"SUPPORTS","OPPOSES"} and new["state"]==old["state"] else None)
                if state:result.append({"class":state,"lens":lens,"axis":axis,"t0_state":old["state"],"current_state":new["state"]})
        t0_stale={i["canonical_evidence_key"] for i in items if i["knowledge_stage"]=="T0_SEALED" and i["freshness"] not in c.FRESH}
        for i in items:
            if i["knowledge_stage"]=="POST_T0_ENRICHED" and i["freshness"] in c.FRESH and i["canonical_evidence_key"] in t0_stale:
                result.append({"class":"REFRESHES_STALE","item_identity":i["artifact_identity"],"axis":i["axis"]})
    facts=[i["artifact_identity"] for i in items if i["knowledge_stage"]=="POST_T0_ENRICHED" and i["fitness"]["fact_eligible"] and not i["fitness"]["direction_eligible"]]
    if facts:result.append({"class":"ADDS_FACTS_ONLY","item_references":facts})
    return result


def compute(ticker,row,*,session,stage,technical=None,flow=None,bindings=None,sealed_row=None,sealed_technical=None,
            origin="LATE_REBUILD",diagnostic=False,source_pointers=None):
    """One ticker, unchanged adapters/reducers; failures stay outside this function."""
    scope="REPLAY_DIAGNOSTIC" if diagnostic else "OFFLINE_RESEARCH"
    source_row=sealed_row if stage=="t0" else row
    if stage=="t0" and (not bindings or not source_row or not bindings.contains_integrated_decision(ticker,session,source_row["decision_identity"])):
        raise ValueError("EXACT_T0_INTEGRATED_DECISION_UNAVAILABLE")
    items=adapters.adapt_integrated(source_row,bindings=bindings)
    if technical:items+=adapters.adapt_technical(technical,bindings=bindings)
    if stage=="current" and flow:items+=adapters.adapt_flow_record(flow)
    if stage=="current" and sealed_row and sealed_row["decision_identity"]!=row["decision_identity"]:
        items+=adapters.adapt_integrated(sealed_row,bindings=bindings)
    if stage=="current" and sealed_technical and (not technical or technical["artifact_identity"]!=sealed_technical["artifact_identity"]):
        items+=adapters.adapt_technical(sealed_technical,bindings=bindings)
    if stage=="t0":items=[i for i in items if i["knowledge_stage"]=="T0_SEALED"]
    reference={"decision_identity":source_row["decision_identity"],"research_action_posture":source_row["research_action_posture"]}
    result=matrix.build_matrix(ticker=ticker,session=session,items=items,decision_reference=reference,
        registers=adapters.registers(source_row),sealed_bindings=bindings,evaluation_scope=scope)
    view=result["views"]["T0_THESIS_VIEW" if stage=="t0" else "CURRENT_RESEARCH_VIEW"]
    t0=result["views"]["T0_THESIS_VIEW"]
    lenses=compact_lenses(view)
    stage_counts=Counter(i["axis"]+"/"+i["knowledge_stage"] for i in result["items"])
    post=[i for i in result["items"] if i["knowledge_stage"]=="POST_T0_ENRICHED"]
    technical_excluded=bool(technical and "RETROSPECTIVE" in c.canonical(technical) and bindings and
        bindings.contains_technical_context(ticker,session,technical["contract_version"],technical["artifact_identity"]))
    t0_basis={"availability":t0["availability"],"snapshot_identity":getattr(bindings,"snapshot_identity",None),
        "index_identity":getattr(bindings,"index_identity",None),"lenses":compact_lenses(t0) if t0["availability"]=="AVAILABLE" else None,
        "evidence_references":t0["evidence_identities"],"reason":None if t0["availability"]=="AVAILABLE" else "NO_ADAPTER_ELIGIBLE_EXACT_T0_EVIDENCE"}
    delta={"t0_available":t0["availability"]=="AVAILABLE","lens_states":{l:{"t0":t0_basis["lenses"][l]["state"] if t0_basis["lenses"] else None,
        "current":lenses[l]["state"]} for l in c.LENSES}}
    notes=annotations(t0,view,result["items"]) if stage=="current" else []
    base={"ticker":ticker,"session":session,"decision_identity":source_row["decision_identity"],"matrix_status":"PARTIAL" if stage=="current" and flow is None else "BUILT",
        "matrix_identity":result["artifact_identity"],"matrix_contract_version":matrix.CONTRACT_VERSION,"adapter_registry_identity":REGISTRY,
        "snapshot_identity":getattr(bindings,"snapshot_identity",None),"seal_index_identity":getattr(bindings,"index_identity",None),
        "write_receipt_identity":getattr(bindings,"write_receipt_identity",None),"lenses":lenses,
        "blocker_families":view["evidence_quality"]["blocker_codes"],"registers":result["decision_card"]["registers"],
        "evidence_references":view["evidence_identities"],"stage_coverage_by_axis":dict(stage_counts),
        "t0_direction_coverage_by_axis":dict(Counter(i["axis"] for i in result["items"] if i["knowledge_stage"]=="T0_SEALED" and i["fitness"]["direction_eligible"])),
        "source_pointers":source_pointers or {},"evaluation_scope":scope,"authority_status":"NON_AUTHORITATIVE",
        "authority_effect":AUTHORITY,"non_voting":True,"is_actionable":False,"origin":origin,
        "learning_cohort_eligible":stage=="t0" and origin=="SEAL_TIME",
        "expected_retrospective_technical_exclusion":technical_excluded,"post_items_in_t0":0 if stage=="t0" else None,
        "flow_facts_only":all(not i["fitness"]["direction_eligible"] for i in result["items"] if i["axis"] in {"VOLUME","PARTICIPANT_FLOW"}),
        "second_posture":False,"action_policy_delta":0}
    if stage=="current":base.update(t0_basis=t0_basis,current_basis={"matrix_identity":result["artifact_identity"],"evidence_references":view["evidence_identities"]},
        delta_vs_t0=delta,post_t0_annotations=notes,flow_facts_ref=[i["artifact_identity"] for i in post if i["axis"] in {"VOLUME","PARTICIPANT_FLOW"}])
    card=c.seal({"contract_version":CARDS[stage],**{k:base[k] for k in ("ticker","session","decision_identity","matrix_status","matrix_identity","adapter_registry_identity","lenses","blocker_families","second_posture","action_policy_delta","non_voting","is_actionable","evaluation_scope","authority_status")},
        "register_references":{k:v for k,v in base["registers"].items()},"delta_vs_t0":delta if stage=="current" else None,
        "flow_facts_ref":base.get("flow_facts_ref",[]),"evidence_source":"DETERMINISTIC_RETAINED_REFERENCES_ONLY",
        "offline_stage_1_card_identity":result["decision_card"]["artifact_identity"]},CARDS[stage])
    record=c.seal({"contract_version":VIEWS[stage],**base,"card_identity":card["artifact_identity"]},VIEWS[stage])
    c.scan_forbidden(record);c.scan_forbidden(card)
    return record,card,result


def unavailable(ticker,session,stage,reason,decision_identity=None):
    if not reason:raise ValueError("UNAVAILABLE_REASON_REQUIRED")
    body={"ticker":ticker,"session":session,"decision_identity":decision_identity,"matrix_status":"UNAVAILABLE",
        "reason_class":reason,"lenses":None,"non_voting":True,"is_actionable":False,"second_posture":False,"action_policy_delta":0}
    card=c.seal({"contract_version":CARDS[stage],**body},CARDS[stage])
    return c.seal({"contract_version":VIEWS[stage],**body,"card_identity":card["artifact_identity"]},VIEWS[stage]),card


def verify_complete(directory):
    directory=Path(directory)
    complete=json.loads((directory/"COMPLETE.json").read_bytes());c.verify_identity(complete,"thesis_product_complete/v1")
    manifest=json.loads((directory/"manifest.json").read_bytes());c.verify_identity(manifest,"thesis_product_manifest/v1")
    if complete["manifest_identity"]!=manifest["artifact_identity"]:raise ValueError("IMMUTABLE_CONFLICT:THESIS_MANIFEST")
    for name,entry in manifest["files"].items():
        if source_hash(directory/name)!=entry["sha256"]:raise ValueError("IMMUTABLE_CONFLICT:THESIS_FILE:"+name)
    return manifest


def status_ref(directory,manifest,root,*,reused=False):
    return {"status":"ALREADY_RETAINED" if reused else manifest["status"],"component_status":manifest["status"],
        "session":manifest["session"],"artifact_identity":manifest["artifact_identity"],
        "path":os.path.relpath(directory/"manifest.json",root).replace("\\","/"),"input_digest":manifest["input_digest"],
        **manifest["counts"],"non_voting":True,"authority_effect":AUTHORITY,"performance":manifest["performance"]}


def build(*,root,output_root,session,stage,decision_path=None,technical_path=None,flow_path=None,index_ref=None,
          snapshot_identity=None,snapshot_path=None,sealed_decision_path=None,origin="LATE_REBUILD",diagnostic=False,observer_identities=None,ticker=None):
    if stage not in VIEWS or origin not in {"SEAL_TIME","LATE_REBUILD"}:raise ValueError("THESIS_STAGE_OR_ORIGIN_INVALID")
    root=Path(root).resolve();output_root=Path(output_root).resolve();started=time.perf_counter()
    bound=seals.load_verified(index_ref,expected_snapshot_identity=snapshot_identity,session=session) if index_ref else None
    if stage=="t0" and not bound:return {"status":"UNAVAILABLE","session":session,"reason":"VERIFIED_T0_SEAL_INDEX_UNAVAILABLE","non_voting":True}
    parses=Counter();sources={};context_digest=hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix="stocklookup-thesis-child-") as scratch, ExitStack() as resources:
        db=sqlite3.connect(str(Path(scratch)/"inputs.sqlite"));db.execute("PRAGMA cache_size=-2048")
        resources.callback(db.close)
        db.execute("CREATE TABLE inputs(kind TEXT,ticker TEXT,payload TEXT,PRIMARY KEY(kind,ticker))")
        def put(kind,t,row):db.execute("INSERT INTO inputs VALUES(?,?,?)",(kind,t,c.canonical(row)))
        def stage_source(path,kind):
            if not path:return
            path=Path(path);parses[kind]+=1
            fingerprint_before=seals.fingerprint(path)
            if kind=="technical" and path.suffix==".ndjson":
                with path.open(encoding="utf-8") as source:
                    for line in iter(lambda:source.readline(16*1024*1024+1),""):
                        if len(line)>16*1024*1024:raise ValueError("THESIS_SOURCE_MEMBER_LIMIT")
                        row=json.loads(line);context=row["contextual_technical"]
                        import contextual_technical_dispatch as dispatch
                        dispatch.verify_context(context,ticker=row["ticker"],session=session)
                        context_digest.update(c.canonical([row["ticker"],context["contract_version"],context["artifact_identity"]]).encode())
                        put(kind,row["ticker"],context)
                metadata={"artifact_identity":"verified_context_stream:"+context_digest.hexdigest(),"session":session}
            else:
                def retain(t,row):
                    if kind=="technical":
                        context=row.get("contextual_technical")
                        if context:
                            import contextual_technical_dispatch as dispatch
                            dispatch.verify_context(context,ticker=t,session=session)
                            context_digest.update(c.canonical([t,context["contract_version"],context["artifact_identity"]]).encode());put(kind,t,context)
                    else:put(kind,t,row)
                excluded={"artifact_identity","artifact_sha256"}
                if kind in {"decision","sealed_decision"}:
                    import integrated_investment_decision_product as product
                    excluded=product._IDENTITY_EXCLUDED
                metadata,digest,_=stream_artifact(path,excluded=excluded,on_record=retain)
                if metadata.get("artifact_sha256")!=digest or metadata.get("session")!=session:raise ValueError("THESIS_SOURCE_HASH_OR_SESSION_INVALID:"+kind)
                expected={"decision":"integrated_investment_decision_product/v1","sealed_decision":"integrated_investment_decision_product/v1","flow":"volume_and_flow_context/v2"}
                if kind in expected and metadata.get("contract_version")!=expected[kind]:raise ValueError("THESIS_SOURCE_VERSION_INVALID:"+kind)
            sha256=source_hash(path)
            if seals.fingerprint(path)!=fingerprint_before:raise ValueError("THESIS_SOURCE_CHANGED_DURING_READ:"+kind)
            sources[kind]={"identity":metadata["artifact_identity"],"sha256":sha256,"path":os.path.relpath(path,root).replace("\\","/")}
        stage_source(decision_path,"decision");stage_source(technical_path,"technical")
        if stage=="current":stage_source(flow_path,"flow")
        if sealed_decision_path:
            if not bound:raise ValueError("THESIS_SEALED_DECISION_INDEX_REQUIRED")
            stage_source(sealed_decision_path,"sealed_decision")
            if sources["sealed_decision"]["identity"]!=bound.source_integrated_decision_artifact["artifact_identity"]:
                raise ValueError("THESIS_SEALED_DECISION_SOURCE_INVALID")
            db.execute("INSERT INTO inputs SELECT 'sealed',ticker,payload FROM inputs WHERE kind='sealed_decision'")
        # Ordinary seal-time/current path uses the already retained exact IID source.
        # Only explicit retained retry streams T0; never whole-snapshot validation.
        if snapshot_path:
            if not bound:raise ValueError("THESIS_SNAPSHOT_RETRY_INDEX_REQUIRED")
            parses["snapshot"]+=1
            def sealed(t,row):
                seals.entry(t,row);put("sealed",t,row["integrated_decision_at_t0"])
            meta,digest,count=stream_artifact(Path(snapshot_path),excluded={"snapshot_identity"},on_record=sealed)
            if meta["snapshot_identity"]!=snapshot_identity or retention.SNAPSHOT_PREFIX+digest!=snapshot_identity or count!=meta["decision_count"]:
                raise ValueError("THESIS_SNAPSHOT_STREAM_BINDING_INVALID")
            sources["sealed"]={"identity":snapshot_identity,"sha256":source_hash(Path(snapshot_path)),"path":os.path.relpath(snapshot_path,root).replace("\\","/")}
        elif sealed_decision_path:pass
        elif bound and sources.get("decision",{}).get("identity")==bound.source_integrated_decision_artifact["artifact_identity"]:
            db.execute("INSERT INTO inputs SELECT 'sealed',ticker,payload FROM inputs WHERE kind='decision'")
        elif stage=="t0":raise ValueError("THESIS_EXACT_T0_SOURCE_IDENTITY_REQUIRED")
        db.commit()
        inputs={"contract_version":CONTRACT_VERSION,"stage":stage,"session":session,"sources":sources,
            "snapshot_identity":getattr(bound,"snapshot_identity",None),"index_identity":getattr(bound,"index_identity",None),
            "write_receipt_identity":getattr(bound,"write_receipt_identity",None),"technical_context_digest":context_digest.hexdigest(),
            "observer_identities":observer_identities or {},"adapter_registry_identity":REGISTRY,"diagnostic":diagnostic,"ticker":ticker}
        if index_ref:inputs["seal_index_ref"]={**index_ref,"path":os.path.relpath(index_ref["path"],root).replace("\\","/")}
        digest=hashlib.sha256(c.canonical(inputs).encode()).hexdigest()
        folder=output_root/"operations-review"/("thesis-evidence-t0-v1" if stage=="t0" else "thesis-evidence-current-v1")/session/digest
        if (folder/"COMPLETE.json").exists():
            manifest=verify_complete(folder)
            if manifest["input_digest"]!=digest or manifest["inputs"]!=inputs:raise ValueError("IMMUTABLE_CONFLICT:THESIS_INPUTS")
            return status_ref(folder,manifest,output_root,reused=True)
        folder.mkdir(parents=True,exist_ok=True)
        # OS-released SQLite lock survives a killed worker without stale lock files.
        # Concurrent publication never replaces a product which another worker sealed.
        writer=sqlite3.connect(str(folder/".writer.sqlite"),timeout=0)
        resources.callback(writer.close)
        writer.execute("BEGIN EXCLUSIVE")
        if (folder/"COMPLETE.json").exists():
            manifest=verify_complete(folder)
            if manifest["inputs"]!=inputs:raise ValueError("IMMUTABLE_CONFLICT:THESIS_INPUTS")
            return status_ref(folder,manifest,output_root,reused=True)
        counts=Counter(built_count=0,partial_count=0,unavailable_count=0);distributions=defaultdict(Counter);guards=Counter(forbidden_judgment_field=0,missing_unavailable_reason=0)
        product_hashes={};matrix_identities=hashlib.sha256();t0_coverage=Counter();t0_direction=Counter();warnings=[];conflicts=Counter();identical_lenses=0
        def get(kind,t):
            found=db.execute("SELECT payload FROM inputs WHERE kind=? AND ticker=?",(kind,t)).fetchone()
            return json.loads(found[0]) if found else None
        members=db.execute("SELECT ticker FROM inputs WHERE kind=? ORDER BY ticker",("sealed" if stage=="t0" else "decision",)).fetchall()
        if ticker:members=[(t,) for (t,) in members if t==ticker]
        if not members:raise ValueError("THESIS_SOURCE_RECORDS_UNAVAILABLE")
        files={name:tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",newline="\n",dir=folder,prefix=".pending-",delete=False) for name in ("views.ndjson","cards.ndjson")}
        try:
            for (t,) in members:
                row=get("decision",t) or get("sealed",t);sealed_row=get("sealed",t)
                technical=get("technical",t) or ((row.get("contextual_technical_context") or {}).get("projection"))
                sealed_technical=((sealed_row or {}).get("contextual_technical_context") or {}).get("projection")
                if stage=="t0":technical=sealed_technical
                try:
                    record,card,full=compute(t,row,session=session,stage=stage,technical=technical,flow=get("flow",t),bindings=bound,
                        sealed_row=sealed_row,sealed_technical=sealed_technical,origin=origin,diagnostic=diagnostic,source_pointers=sources)
                    if stage=="current":
                        record["t0_basis"]["manifest_identity"]=inputs["observer_identities"].get("t0_thesis_manifest")
                        record=c.seal(record,VIEWS[stage])
                    counts["partial_count" if record["matrix_status"]=="PARTIAL" else "built_count"]+=1
                    matrix_identities.update(c.canonical([t,full["artifact_identity"]]).encode())
                    for lens in c.LENSES:distributions[lens][record["lenses"][lens]["state"]]+=1
                    identical_lenses+=len({record["lenses"][l]["state"] for l in c.LENSES})==1
                    for lens in c.LENSES:
                        for conflict in record["lenses"][lens]["conflicts"]:conflicts[conflict["kind"]]+=1
                    for i in full["items"]:
                        guards["post_in_t0"]+=stage=="t0" and i["knowledge_stage"]!="T0_SEALED"
                        guards["flow_directional_vote"]+=i["axis"] in {"VOLUME","PARTICIPANT_FLOW"} and i["fitness"]["direction_eligible"]
                        guards["foreign_breadth_overclaim"]+=i["axis"]=="PARTICIPANT_FLOW" and i["coverage"].get("is_market_representative") is True
                        t0_coverage[i["axis"]]+=i["knowledge_stage"]=="T0_SEALED"
                        t0_direction[i["axis"]]+=i["knowledge_stage"]=="T0_SEALED" and i["fitness"]["direction_eligible"]
                        guards["retrospective_item_in_t0"]+=i["knowledge_stage"]=="T0_SEALED" and "RETROSPECTIVE" in c.canonical(i["basis"])
                    guards["state_card_mismatch"]+=record["lenses"]!=card["lenses"]
                    action_source=sealed_row if stage=="t0" else row
                    guards["action_posture_delta"]+=full["decision_card"]["ACTION SUPPORT REFERENCE"]!={"decision_identity":action_source["decision_identity"],"research_action_posture":action_source["research_action_posture"],"second_posture":False}
                    guards["duplicate_vote"]+=any(len({(g["correlation_group"],g["knowledge_stage"]) for g in p["groups"]})!=len(p["groups"]) for p in full["views"]["CURRENT_RESEARCH_VIEW"]["lenses"].values())
                except Exception as exc:
                    counts["unavailable_count"]+=1
                    record,card=unavailable(t,session,stage,type(exc).__name__+":"+str(exc),row.get("decision_identity"))
                files["views.ndjson"].write(c.canonical(record)+"\n");files["cards.ndjson"].write(c.canonical(card)+"\n")
            for name,stream in files.items():
                stream.flush();os.fsync(stream.fileno());stream.close()
                target=folder/name;os.replace(stream.name,target)
                product_hashes[name]={"sha256":source_hash(target),"bytes":target.stat().st_size}
        finally:
            for stream in files.values():
                stream.close();Path(stream.name).unlink(missing_ok=True)
            db.close()
        if any(guards.values()):raise ValueError("THESIS_PRODUCTION_CORRECTNESS_FAIL:"+c.canonical(dict(guards)))
        # Descriptive facts only; warnings never tune reducers or alter publication.
        for lens,dist in distributions.items():
            if dist.get("CONTESTED"):warnings.append({"kind":"CONTESTED_CONCENTRATION","lens":lens,"count":dist["CONTESTED"],"denominator":len(members)})
        identical=sum(distributions[c.LENSES[0]].get(s,0)==distributions[c.LENSES[1]].get(s,0) for s in c.LENS_STATES)==len(c.LENS_STATES)
        warnings.append({"kind":"LENS_DISTRIBUTIONS_IDENTICAL","observed":identical})
        warnings.extend([
            {"kind":"SHORT_SUPPORTIVE_COLLAPSE","supportive_count":distributions[c.LENSES[1]].get("SUPPORTIVE",0),"denominator":len(members),"comparison":"NOT_EVALUABLE_WITHOUT_EXPLICIT_PRIOR_PRODUCT"},
            {"kind":"LENS_STATES_IDENTICAL","count":identical_lenses,"denominator":len(members)},
            {"kind":"CONFLICT_EXPLOSION","total":sum(conflicts.values()),"kinds":dict(conflicts),"comparison":"NOT_EVALUABLE_WITHOUT_EXPLICIT_PRIOR_PRODUCT"},
            {"kind":"STATE_CHURN_ACROSS_SESSIONS","status":"NOT_EVALUABLE_WITHOUT_EXPLICIT_PRIOR_PRODUCT"},
            {"kind":"AVAILABILITY_EPOCH_TRANSITIONS","current":{"t0":bool(bound),"flow":bool(flow_path)},"comparison":"NOT_EVALUABLE_WITHOUT_EXPLICIT_PRIOR_PRODUCT"}])
        import psutil
        from prospective_pit_capture_retention import io_known_at
        info=psutil.Process().memory_info()
        status="UNAVAILABLE" if not counts["built_count"]+counts["partial_count"] else "PARTIAL" if counts["unavailable_count"] or counts["partial_count"] else "BUILT"
        manifest=c.seal({"contract_version":"thesis_product_manifest/v1","session":session,"stage":stage,"input_digest":digest,"inputs":inputs,
            "status":status,"counts":dict(counts),"records":len(members),"files":product_hashes,"distributions":dict(distributions),
            "t0_coverage_by_axis":dict(t0_coverage),"matrix_identity_digest":matrix_identities.hexdigest(),"pathology_fail_conditions":dict(guards),
            "t0_direction_coverage_by_axis":dict(t0_direction),
            "descriptive_warnings":warnings,"availability_epoch":{"t0":bool(bound),"flow":bool(flow_path)},
            "comparison_to_prior_session":"NOT_EVALUABLE_WITHOUT_EXPLICIT_PRIOR_PRODUCT","authority_effect":AUTHORITY,
            "origin":origin,"evaluation_scope":"REPLAY_DIAGNOSTIC" if diagnostic else "PRODUCTION_NON_VOTING",
            "created_at":io_known_at(),
            "performance":{"wall_seconds":time.perf_counter()-started,"rss_bytes":info.rss,"peak_rss_bytes":getattr(info,"peak_wset",info.rss),"source_parse_passes":dict(parses),"source_member_limit_bytes":16*1024*1024}},"thesis_product_manifest/v1")
        atomic_write_json(folder/"manifest.json",manifest)
        complete=c.seal({"contract_version":"thesis_product_complete/v1","session":session,"manifest_identity":manifest["artifact_identity"]},"thesis_product_complete/v1")
        retain_immutable_bytes(folder/"COMPLETE.json",c.canonical(complete).encode())
        if stage=="current" and not diagnostic:
            atomic_write_json(folder.parent/"current_pointer.json",{"session":session,"input_digest":digest,"manifest_identity":manifest["artifact_identity"],"path":digest+"/manifest.json"})
        return status_ref(folder,manifest,output_root)


def verify_ticker(manifest_path,*,root,ticker):
    """Retained-only independent rebuild from original inputs; no authority writes."""
    manifest_path=Path(manifest_path);manifest=verify_complete(manifest_path.parent);inputs=manifest["inputs"]
    original=None
    with (manifest_path.parent/"views.ndjson").open(encoding="utf-8") as source:
        for line in iter(lambda:source.readline(1024*1024+1),""):
            if len(line)>1024*1024:raise ValueError("THESIS_VERIFIER_MEMBER_LIMIT")
            record=json.loads(line)
            if record["ticker"]==ticker:original=record;break
    if not original:raise ValueError("THESIS_VERIFICATION_TICKER_ABSENT")
    root=Path(root);paths={k:root/v["path"] for k,v in inputs["sources"].items()}
    ref=inputs.get("seal_index_ref")
    if ref:ref={**ref,"path":str(root/ref["path"])}
    with tempfile.TemporaryDirectory(prefix="stocklookup-thesis-verifier-") as temporary:
        result=build(root=root,output_root=temporary,session=manifest["session"],stage=manifest["stage"],
            decision_path=paths.get("decision"),technical_path=paths.get("technical"),flow_path=paths.get("flow"),
            sealed_decision_path=paths.get("sealed_decision"),snapshot_path=paths.get("sealed"),
            index_ref=ref,snapshot_identity=inputs.get("snapshot_identity"),origin=manifest["origin"],
            diagnostic=inputs["diagnostic"],observer_identities=inputs["observer_identities"],ticker=ticker)
        rebuilt=json.loads((Path(temporary)/result["path"]).parent.joinpath("views.ndjson").read_text(encoding="utf-8"))
        if rebuilt!=original:raise ValueError("THESIS_SINGLE_TICKER_REBUILD_MISMATCH")
    return {"status":"PASS","ticker":ticker,"matrix_identity":original.get("matrix_identity"),"view_identity":original["artifact_identity"]}
