"""Fail-soft child runner and compact presentation reader. No reducer imports."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

AUTOMATIC_HOOK_ENABLED=True  # Measured retained rehearsal: 74.1 MB child peak, 0.22 MB parent growth; component-local failures.


def _identity(value,*,kind):
    # Projection hashes include snapshot_identity; the market-source hash excludes it.
    import hashlib
    body={k:v for k,v in value.items() if k not in {"artifact_identity","artifact_sha256"}}
    digest=hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return {"artifact_identity":kind+":"+digest,"artifact_sha256":digest}


def run_component(root,session,*,stage,snapshot_binding=None,output_root=None,decision_path=None,
                  technical_path=None,flow_path=None,observer_identities=None,origin="SEAL_TIME",diagnostic=False):
    from stocklookup_core.tactical.contextual_technical_dispatch import PRODUCTION_V2_START_SESSION
    if session<PRODUCTION_V2_START_SESSION and not diagnostic:return {"status":"NOT_APPLICABLE","reason":"PRE_STAGE_2_PRODUCTION_COHORT","session":session}
    if not AUTOMATIC_HOOK_ENABLED and not diagnostic:return {"status":"UNAVAILABLE","reason":"AUTOMATIC_THESIS_HOOK_DISABLED_FAIL_SOFT","session":session}
    root=Path(root);output_root=Path(output_root or root);binding=snapshot_binding or {}
    try:
        index=binding.get("seal_index") or {}
        ref=None
        if index.get("status")=="RETAINED":ref={k:index[k] for k in ("path","artifact_identity","write_receipt_identity")}
        if ref:ref["path"]=str(root/ref["path"])
        if stage=="t0" and not ref:return {"status":"UNAVAILABLE","session":session,"reason":"VERIFIED_T0_SEAL_INDEX_UNAVAILABLE"}
        decision_path=Path(decision_path or root/"operations-review/canonical-post-close-v1"/session/"enrichment/integrated_investment_decision_product.json")
        if not decision_path.exists():return {"status":"UNAVAILABLE","session":session,"reason":"THESIS_RETAINED_DECISION_SOURCE_UNAVAILABLE"}
        with tempfile.TemporaryDirectory(prefix="stocklookup-thesis-runtime-") as temporary:
            request=Path(temporary)/"request.json";result_path=Path(temporary)/"result.json"
            request.write_text(json.dumps({"index_ref":ref,"snapshot_identity":binding.get("identity"),"observer_identities":observer_identities or {}}),encoding="utf-8")
            command=[sys.executable,str(Path(__file__).resolve().parents[2]/"tools/run_thesis_evidence_stage2.py"),"--session",session,"--stage",stage,
                "--source-root",str(root),"--output-root",str(output_root),"--decision",str(decision_path),"--origin",origin,
                "--request",str(request),"--result",str(result_path)]
            if diagnostic:command.append("--diagnostic")
            for name,path in (("technical",technical_path),("flow",flow_path)):
                if path:command.extend(["--"+name,str(path)])
            child=subprocess.run(command,cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,timeout=1800)
            if child.returncode or not result_path.exists():
                return {"status":"UNAVAILABLE","session":session,"reason":"THESIS_CHILD_FAILED:"+str(child.returncode)+":"+child.stderr[-1500:],"non_voting":True}
            if result_path.stat().st_size>64*1024:raise ValueError("THESIS_CHILD_RESULT_SIZE_LIMIT")
            result=json.loads(result_path.read_bytes())
            if result.get("path"):
                result["path"]=os.path.relpath(output_root/result["path"],root).replace("\\","/")
            if result.get("status")=="ALREADY_RETAINED":result["retention"]="ALREADY_RETAINED"
            if result.get("component_status") in {"BUILT","PARTIAL"}:result["status"]="COLLECTED"
            return result
    except Exception as exc:
        return {"status":"UNAVAILABLE","session":session,"reason":"THESIS_COMPONENT_FAILED:"+type(exc).__name__+":"+str(exc),"non_voting":True}


def summary(block):
    """Only deterministic status/identity references; portable, no action or sorting."""
    return {k:block.get(k) for k in ("status","component_status","artifact_identity","path","input_digest","built_count","partial_count","unavailable_count","reason","retention") if block.get(k) is not None}


def focus_cards(root,reference,*,tickers=(),limit=12):
    """Bounded read of compact cards, selected by existing owner focus, never ranked."""
    try:
        if reference.get("status")!="COLLECTED" or not tickers:return []
        folder=(Path(root)/reference["path"]).parent
        import hashlib
        import prospective_market_snapshot_contract as market
        manifest=json.loads((folder/"manifest.json").read_bytes())
        if any(manifest.get(k)!=v for k,v in _identity(manifest,kind="thesis_product_manifest/v1").items()):raise ValueError("THESIS_MANIFEST_IDENTITY_INVALID")
        if manifest["artifact_identity"]!=reference["artifact_identity"]:raise ValueError("THESIS_PRESENTATION_BINDING_INVALID")
        from bounded_artifact_stream import source_hash
        path=folder/"cards.ndjson"
        if source_hash(path)!=manifest["files"]["cards.ndjson"]["sha256"]:raise ValueError("THESIS_PRESENTATION_CARDS_INVALID")
        selected=set(list(tickers)[:limit]);cards=[]
        with path.open(encoding="utf-8") as source:
            for line in iter(lambda:source.readline(1024*1024+1),""):
                if len(line)>1024*1024:raise ValueError("THESIS_CARD_SIZE_LIMIT")
                card=json.loads(line)
                if card["ticker"] in selected:
                    if any(card.get(k)!=v for k,v in _identity(card,kind=card["contract_version"]).items()):raise ValueError("THESIS_CARD_IDENTITY_INVALID")
                    cards.append({"ticker":card["ticker"],"matrix_status":card["matrix_status"],"card_identity":card["artifact_identity"],
                        "matrix_identity":card.get("matrix_identity"),"lenses":{l:{**{k:p[k] for k in ("state","lens_cap","contest_basis")},"conflict_kinds":sorted({x["kind"] for x in p["conflicts"]})} for l,p in (card.get("lenses") or {}).items()},
                        "blocker_families":card.get("blocker_families",[]),"reason_class":card.get("reason_class"),"non_voting":True})
        return cards
    except Exception:return []


def read_product_report(manifest_path,*,expected_identity=None):
    """Bounded, read-only accounting for post-Daily acceptance and presentation."""
    import prospective_market_snapshot_contract as market
    from bounded_artifact_stream import source_hash
    manifest_path=Path(manifest_path);folder=manifest_path.parent
    manifest=json.loads(manifest_path.read_bytes())
    if any(manifest.get(k)!=v for k,v in _identity(manifest,kind="thesis_product_manifest/v1").items()):raise ValueError("THESIS_MANIFEST_IDENTITY_INVALID")
    if expected_identity and manifest["artifact_identity"]!=expected_identity:raise ValueError("THESIS_REPORT_REFERENCE_MISMATCH")
    if manifest["inputs"].get("contract_version")!="thesis_production_projection/v1" or manifest["stage"] not in {"t0","current"}:raise ValueError("THESIS_REPORT_CONTRACT_INVALID")
    complete=json.loads((folder/"COMPLETE.json").read_bytes())
    if complete.get("manifest_identity")!=manifest["artifact_identity"] or any(complete.get(k)!=v for k,v in _identity(complete,kind="thesis_product_complete/v1").items()):raise ValueError("THESIS_COMPLETE_BINDING_INVALID")
    for name,entry in manifest["files"].items():
        if source_hash(folder/name)!=entry["sha256"]:raise ValueError("THESIS_PRODUCT_SOURCE_CHANGED")
    facts={"records":0,"post_in_t0":0,"second_posture":0,"action_policy_delta":0,"flow_directional_violation":0,"retrospective_exclusion_count":0,"separate_basis_count":0,"missing_unavailable_reason":0}
    from itertools import zip_longest
    with (folder/"views.ndjson").open(encoding="utf-8") as source,(folder/"cards.ndjson").open(encoding="utf-8") as cards:
        for line,card_line in zip_longest(iter(lambda:source.readline(1024*1024+1),""),iter(lambda:cards.readline(1024*1024+1),"")):
            if line is None or card_line is None:raise ValueError("THESIS_CARD_VIEW_COUNT_MISMATCH")
            if len(line)>1024*1024:raise ValueError("THESIS_VIEW_MEMBER_LIMIT")
            row=json.loads(line)
            if len(card_line)>1024*1024:raise ValueError("THESIS_CARD_MEMBER_LIMIT")
            card=json.loads(card_line)
            if card["ticker"]!=row["ticker"] or row["card_identity"]!=card["artifact_identity"] or card.get("lenses")!=row.get("lenses"):raise ValueError("THESIS_CARD_VIEW_MISMATCH")
            if any(card.get(k)!=v for k,v in _identity(card,kind=card["contract_version"]).items()):raise ValueError("THESIS_CARD_IDENTITY_INVALID")
            if any(row.get(k)!=v for k,v in _identity(row,kind=row["contract_version"]).items()):raise ValueError("THESIS_VIEW_IDENTITY_INVALID")
            if row["session"]!=manifest["session"]:raise ValueError("THESIS_VIEW_SESSION_INVALID")
            facts["records"]+=1;facts["second_posture"]+=row.get("second_posture") is not False
            facts["action_policy_delta"]+=row.get("action_policy_delta",1)
            if row["matrix_status"]=="UNAVAILABLE":facts["missing_unavailable_reason"]+=not row.get("reason_class")
            else:
                if row["snapshot_identity"]!=manifest["inputs"]["snapshot_identity"] or row["seal_index_identity"]!=manifest["inputs"]["index_identity"]:raise ValueError("THESIS_RECORD_SEAL_BINDING_INVALID")
                facts["flow_directional_violation"]+=not row["flow_facts_only"]
                facts["retrospective_exclusion_count"]+=row["expected_retrospective_technical_exclusion"]
                facts["separate_basis_count"]+=bool("t0_basis" in row and "current_basis" in row and "delta_vs_t0" in row)
                if manifest["stage"]=="t0":facts["post_in_t0"]+=sum(n for k,n in row["stage_coverage_by_axis"].items() if k.endswith("POST_T0_ENRICHED"))
    if facts["records"]!=manifest["records"]:raise ValueError("THESIS_PRODUCT_RECORD_COUNT_INVALID")
    return {"identity":manifest["artifact_identity"],"session":manifest["session"],"stage":manifest["stage"],"status":manifest["status"],
        "created_at":manifest["created_at"],
        "snapshot_identity":manifest["inputs"]["snapshot_identity"],"index_identity":manifest["inputs"]["index_identity"],
        "counts":manifest["counts"],"distributions":manifest["distributions"],"guards":manifest["pathology_fail_conditions"],
        "t0_coverage_by_axis":manifest["t0_coverage_by_axis"],"t0_direction_coverage_by_axis":manifest["t0_direction_coverage_by_axis"],**facts}
