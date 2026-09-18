"""Retained-only multi-session velocity research; semantic corrective V1.1."""
from __future__ import annotations
from collections import Counter
import hashlib, json
from pathlib import Path
from typing import Any, Mapping, Sequence
import prospective_decision_retention as retention

CONTRACT_VERSION="multi_session_signal_velocity/v1.1"
RESEARCH_TIER="PIT_SAFE_RETAINED_SESSION_TRANSITION_RESEARCH_ONLY"
AXES=("price_momentum","structural_repair","participation_confirmation","setup_maturation","market_support","sector_support","fundamental_trajectory")

def _canon(value: Any)->str: return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)
def _identity(payload:dict[str,Any])->dict[str,Any]:
    body={k:v for k,v in payload.items() if k not in {"artifact_identity","artifact_sha256"}}; digest=hashlib.sha256(_canon(body).encode()).hexdigest()
    payload.update(artifact_sha256=digest,artifact_identity="multi_session_signal_velocity:"+digest); return payload
def _load(path:Path)->dict[str,Any]|None:
    try: value=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError): return None
    return value if isinstance(value,dict) else None
def _rel(root:Path,path:Path)->str:
    try:return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:return str(path)

def _operation(root:Path,session:str,identity:str)->dict[str,Any]|None:
    base=root/"operations-review"/"daily-research-session-operations-v1"/session
    rows=[(p,_load(p)) for p in sorted(base.glob("*/run_manifest.json"))] if base.is_dir() else []
    rows=[(p,m) for p,m in rows if m and m.get("operation_identity")==identity]
    if len(rows)!=1:return None
    path,manifest=rows[0]
    return {"path":_rel(root,path)} if manifest.get("market_session")==session and manifest.get("generation_context")=="DAILY_PRODUCER_RETAINED_COMPLETED_SESSION" else None

def discover_retained_snapshots(root:str|Path)->dict[str,Any]:
    """Completed-session ledger -> exact handoff -> exact immutable snapshot only."""
    repo=Path(root); registry=_load(repo/"config"/"daily_research_session_input_registry.json") or {}; completed=registry.get("completed_sessions") or {}
    inventory=[]; qualified=[]
    for session in sorted(str(s) for s,e in completed.items() if isinstance(s,str) and isinstance(e,Mapping) and e.get("status")=="COMPLETED_RETAINED_EVIDENCE"):
        handoff_path=repo/"operations-review"/"canonical-post-close-v1"/session/"session_handoff_bundle.json"; handoff=_load(handoff_path); declared=(handoff or {}).get("prospective_decision_snapshot") or {}; ident=declared.get("identity") if isinstance(declared,Mapping) else None
        digest=ident.removeprefix(retention.SNAPSHOT_PREFIX) if isinstance(ident,str) else ""; path=repo/"operations-review"/"prospective-decision-retention-v1"/session/digest/"prospective_decision_snapshot.json"; snap=_load(path); reasons=[]; operation=None
        if not snap: reasons.append("EXACT_HANDOFF_SNAPSHOT_NOT_RETAINED_OR_UNREADABLE")
        else:
            source=snap.get("source_integrated_decision_artifact") or {}; operation=_operation(repo,session,str(snap.get("daily_session_operation_identity") or ""))
            if not retention.validate_snapshot(snap):reasons.append("SNAPSHOT_CONTENT_IDENTITY_INVALID")
            if snap.get("session")!=session:reasons.append("HANDOFF_SESSION_MISMATCH")
            if not handoff:reasons.append("CANONICAL_HANDOFF_NOT_RETAINED")
            else:
                if ident!=snap.get("snapshot_identity"):reasons.append("HANDOFF_SNAPSHOT_IDENTITY_MISMATCH")
                if handoff.get("daily_session_operation_identity")!=snap.get("daily_session_operation_identity"):reasons.append("HANDOFF_OPERATION_IDENTITY_MISMATCH")
                if handoff.get("integrated_investment_decision_product_identity")!=source.get("artifact_identity"):reasons.append("HANDOFF_SOURCE_DECISION_IDENTITY_MISMATCH")
            if operation is None:reasons.append("COMPLETED_DAILY_OPERATION_NOT_RETAINED")
        row={"session":session,"snapshot_path":_rel(repo,path),"snapshot_identity":(snap or {}).get("snapshot_identity") or ident,"classification":"QUALIFIED" if not reasons else "EXCLUDED","reason_codes":reasons or ["EXACT_T0_SNAPSHOT_AND_HANDOFF_BOUND"],"canonical_handoff_path":_rel(repo,handoff_path) if handoff else None,"operation_manifest_path":operation.get("path") if operation else None}
        inventory.append(row)
        if snap and not reasons:qualified.append({"snapshot":snap,"inventory":row})
    return {"contract_version":CONTRACT_VERSION,"inventory":inventory,"qualified_snapshots":qualified,"qualified_session_chain":[x["snapshot"]["session"] for x in qualified],"classification_counts":dict(sorted(Counter(x["classification"] for x in inventory).items()))}

def _state(value:Any,table:Mapping[str,str])->str:
    text=str(value or "").upper()
    if not text or text in {"UNKNOWN","UNAVAILABLE","INSUFFICIENT","NONE","NOT_PROVIDED","FIELD_NOT_RETAINED_AT_T0"}:return "UNAVAILABLE"
    return next((state for needle,state in table.items() if needle in text),"NEUTRAL")

def _axis(record:Mapping[str,Any],name:str)->dict[str,Any]:
    axes=record.get("evidence_axes") or {}; technical=axes.get("TACTICAL_STRUCTURE") or {}; momentum=record.get("momentum_context") or {}; participation=axes.get("PARTICIPATION_CONFIRMATION") or {}; market=axes.get("MARKET_SECTOR") or {}; fundamental=axes.get("FUNDAMENTAL") or {}
    if name=="price_momentum":
        raw=momentum.get("price_direction_1d"); return {"state":_state(raw,{"UP":"IMPROVING","DOWN":"DETERIORATING"}),"source_field":"momentum_context.price_direction_1d","source_identity":(axes.get("MOMENTUM") or {}).get("lineage",{}).get("source_artifact_identity"),"source_state":raw}
    if name=="structural_repair":
        c=technical.get("context") or {}; raw=c.get("market_structure_state") or record.get("market_structure_state"); breakout=c.get("breakout_state_v3") or record.get("breakout_state_v3"); text=" ".join(str(x or "") for x in (raw,breakout))
        return {"state":_state(text,{"BREAKDOWN":"ADVERSE","BEARISH":"ADVERSE","FAILED":"ADVERSE","BASE":"REPAIRING","EARLY_BULLISH":"REPAIRING","UPTREND":"CONSTRUCTIVE","CONFIRMED":"CONSTRUCTIVE","BREAKOUT":"CONSTRUCTIVE"}),"source_field":"TACTICAL_STRUCTURE.context.market_structure_state+breakout_state_v3","source_identity":technical.get("lineage",{}).get("source_artifact_identity"),"source_state":{"market_structure_state":raw,"breakout_state_v3":breakout}}
    if name=="participation_confirmation":
        c=participation.get("context") or {}; raw=(c.get("participation_detail") or {}).get("participation_state") or participation.get("state")
        return {"state":_state(raw,{"EXPANDING":"IMPROVING","CONTRACTING":"DETERIORATING","CONTRADICTION":"DIVERGENT"}),"source_field":"PARTICIPATION_CONFIRMATION.context.participation_detail.participation_state","source_identity":participation.get("lineage",{}).get("participation_artifact_identity") or participation.get("lineage",{}).get("source_artifact_identity"),"source_state":raw}
    if name=="setup_maturation":
        raw=(technical.get("context") or {}).get("breakout_state_v3") or record.get("breakout_state_v3")
        return {"state":_state(raw,{"FAILED":"INVALID","BREAKDOWN":"INVALID","DOWNTREND":"INVALID","BASE":"BUILDING","EARLY":"EARLY","READY":"CONFIRMED","CONFIRMED":"CONFIRMED"}),"source_field":"TACTICAL_STRUCTURE.context.breakout_state_v3","source_identity":technical.get("lineage",{}).get("source_artifact_identity"),"source_state":raw}
    if name in {"market_support","sector_support"}:
        c=market.get("context") or {}; field="market_regime" if name=="market_support" else "sector_leadership"; raw=c.get(field) or (record.get("market_sector_context") or {}).get(field)
        return {"state":_state(raw,{"SUPPORT":"SUPPORTIVE","LEADING":"SUPPORTIVE","ADVERSE":"ADVERSE","LAGGING":"ADVERSE","MIXED":"MIXED"}),"source_field":"MARKET_SECTOR.context."+field,"source_identity":market.get("lineage",{}).get("source_artifact_identity"),"source_state":raw}
    raw=fundamental.get("state") or record.get("fundamental_state")
    return {"state":_state(raw,{"IMPROV":"IMPROVING","REPAIR":"IMPROVING","DETERIORAT":"DETERIORATING","WEAK":"DETERIORATING"}),"source_field":"FUNDAMENTAL.state","source_identity":fundamental.get("lineage",{}).get("source_artifact_identity"),"source_state":raw}

RANK={"price_momentum":{"DETERIORATING":0,"NEUTRAL":1,"IMPROVING":2},"structural_repair":{"ADVERSE":0,"NEUTRAL":1,"REPAIRING":2,"CONSTRUCTIVE":3},"participation_confirmation":{"DETERIORATING":0,"DIVERGENT":1,"NEUTRAL":1,"IMPROVING":2},"setup_maturation":{"INVALID":0,"NEUTRAL":1,"BUILDING":2,"EARLY":3,"CONFIRMED":4},"market_support":{"ADVERSE":0,"MIXED":1,"NEUTRAL":1,"SUPPORTIVE":2},"sector_support":{"ADVERSE":0,"MIXED":1,"NEUTRAL":1,"SUPPORTIVE":2},"fundamental_trajectory":{"DETERIORATING":0,"NEUTRAL":1,"IMPROVING":2}}
def _trajectory(name:str,history:Sequence[Mapping[str,Any]])->dict[str,Any]:
    valid=[x["state"] for x in history if x["state"]!="UNAVAILABLE"]; changes=[RANK[name][b]-RANK[name][a] for a,b in zip(valid,valid[1:])]; last=changes[-1] if changes else None
    direction="IMPROVING" if last and last>0 else "DETERIORATING" if last and last<0 else "UNCHANGED" if last==0 else "NOT_COMPARABLE"
    def persist(window:list[int])->str:
        if len(window)<2:return "INSUFFICIENT_HISTORY"
        if all(x>0 for x in window):return "IMPROVEMENT_PERSISTENT"
        if all(x<0 for x in window):return "DETERIORATION_PERSISTENT"
        if any(x>0 for x in window) and any(x<0 for x in window):return "MIXED"
        return "NO_CLEAR_DIRECTION"
    if len(changes)<3:acc="INSUFFICIENT_HISTORY"
    elif changes[-1]>0 and changes[-2]>0:acc="ACCELERATING"
    elif changes[-1]<0 and changes[-2]<0:acc="ACCELERATING_DETERIORATION"
    elif changes[-1]*changes[-2]<0:acc="REVERSING"
    elif changes[-1]==0 and changes[-2]>0:acc="DECELERATING"
    else:acc="STABLE"
    return {"latest_transition":direction,"recent_direction":direction,"observation_count":len(valid),"window_3_state":persist(changes[-2:]),"window_5_state":persist(changes[-4:]),"persistence":persist(changes[-2:]),"acceleration_state":acc,"improving_transitions":sum(x>0 for x in changes),"deteriorating_transitions":sum(x<0 for x in changes),"unchanged_transitions":sum(x==0 for x in changes),"recent_reversal":bool(len(changes)>1 and changes[-1]*changes[-2]<0)}

def _overall(axes:Mapping[str,Any],quality:str)->tuple[str,list[str],list[str]]:
    if quality=="INSUFFICIENT_RETAINED_EVIDENCE":return "INSUFFICIENT_EVIDENCE",[],[]
    veto=[n for n,x in axes.items() if n in {"structural_repair","setup_maturation"} and x["state"] in {"ADVERSE","INVALID"}]
    supporting=[n for n,x in axes.items() if x["trajectory"]["persistence"]=="IMPROVEMENT_PERSISTENT" and x.get("source_identity")]
    unique={axes[n]["source_identity"] for n in supporting}
    if veto:return "DETERIORATING",supporting,veto
    if len(unique)>=2:return ("ACCELERATING_IMPROVEMENT" if any(axes[n]["trajectory"]["acceleration_state"]=="ACCELERATING" for n in supporting) else "PERSISTENT_IMPROVEMENT"),supporting,[]
    positive=[n for n,x in axes.items() if x["trajectory"]["latest_transition"]=="IMPROVING"]; negative=[n for n,x in axes.items() if x["trajectory"]["latest_transition"]=="DETERIORATING"]
    if positive and negative:return "MIXED_TRANSITION",positive,negative
    if positive:return "EARLY_IMPROVEMENT",positive,[]
    if negative:return "DETERIORATING",[],negative
    return "STABLE",[],[]

def build_artifact(*,qualified_snapshots:Sequence[Mapping[str,Any]],source_inventory:Sequence[Mapping[str,Any]]|None=None)->dict[str,Any]:
    histories={}; records=[]
    for item in sorted(qualified_snapshots,key=lambda x:str(x["snapshot"].get("session"))):
        snapshot=item["snapshot"]; inv=item["inventory"]; session=snapshot["session"]
        for ticker,sealed in sorted((snapshot.get("records") or {}).items()):
            decision=(sealed or {}).get("integrated_decision_at_t0") if isinstance(sealed,Mapping) else None
            if not isinstance(decision,Mapping) or decision.get("ticker")!=ticker:continue
            prior=histories.setdefault(ticker,{n:[] for n in AXES}); axes={n:_axis(decision,n) for n in AXES}
            for n in AXES:axes[n]["trajectory"]=_trajectory(n,prior[n]+[axes[n]])
            unavailable=[n for n,x in axes.items() if x["state"]=="UNAVAILABLE"]; quality="COMPLETE_RETAINED_EVIDENCE" if not unavailable else "PARTIAL_RETAINED_EVIDENCE" if len(unavailable)<len(AXES) else "INSUFFICIENT_RETAINED_EVIDENCE"; overall,support,contradict=_overall(axes,quality)
            records.append({"ticker":ticker,"session":session,"source_sequence_index":len(prior[AXES[0]])+1,"source_snapshot_identity":snapshot.get("snapshot_identity"),"source_integrated_decision_identity":sealed.get("integrated_decision_identity"),"source_operation_identity":snapshot.get("daily_session_operation_identity"),"source_paths":{"snapshot":inv.get("snapshot_path"),"canonical_handoff":inv.get("canonical_handoff_path"),"operation_manifest":inv.get("operation_manifest_path")},"axes":axes,"evidence_quality":{"state":quality,"unavailable_axes":unavailable},"overall_transition_state":overall,"independent_supporting_axes":support,"contradicting_axes":contradict,"research_tier":RESEARCH_TIER,"is_actionable":False})
            for n in AXES:prior[n].append(axes[n])
    latest=records[-1]["session"] if records else None; cohort=[r for r in records if r["session"]==latest]
    artifact={"schema_version":"1.1.0","contract_version":CONTRACT_VERSION,"supersedes":{"contract_version":"multi_session_signal_velocity/v1","status":"SUPERSEDED_BY_SEMANTIC_CORRECTIVE","old_artifacts_immutable":True},"research_tier":RESEARCH_TIER,"source_inventory":list(source_inventory or []),"records":records,"validation":{"retained_session_count":len(qualified_snapshots),"retained_sessions":[x["snapshot"]["session"] for x in qualified_snapshots],"record_count":len(records),"latest_session":latest,"latest_session_cohort_counts":dict(sorted(Counter(r["overall_transition_state"] for r in cohort).items())),"lead_time_diagnostic":{"status":"NOT_EVALUABLE_NO_FORWARD_OUTCOME_CONTRACT"},"false_transition_diagnostic":{"status":"NOT_EVALUABLE_NO_FORWARD_OUTCOME_CONTRACT"},"limits":["NO_FUTURE_PRICE_OR_OUTCOME_DATA","NO_SCORE_OR_PROBABILITY","MISSING_OBSERVATIONS_NOT_INTERPOLATED"]},"authority_boundary":{"retained_t0_only":True,"no_provider_or_network":True,"no_historical_reconstruction":True,"no_score_probability_or_recommendation":True,"no_execution_or_sizing":True,"is_actionable":False}}
    return _identity(artifact)
def build_from_retained_root(root:str|Path)->dict[str,Any]:
    discovery=discover_retained_snapshots(root);return build_artifact(qualified_snapshots=discovery["qualified_snapshots"],source_inventory=discovery["inventory"])
def write_immutable(path:str|Path,artifact:Mapping[str,Any])->Path:
    destination=Path(path); text=json.dumps(artifact,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    if destination.exists() and destination.read_text(encoding="utf-8")!=text:raise ValueError("IMMUTABLE_ARTIFACT_CONFLICT:"+str(destination))
    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(text,encoding="utf-8");return destination
