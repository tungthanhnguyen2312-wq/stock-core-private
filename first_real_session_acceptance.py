"""Read-only capability-specific post-Daily acceptance; no authority publication.

All OPEN states are conjunctions of explicit capability predicates. Diagnostics
never import Thesis, run Daily, register receipts, recover indexes or write clocks.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import json
import time
import prospective_market_snapshot_contract as market
import prospective_pit_capture as capture
import prospective_pit_capture_retention as capture_store
import contextual_technical_dispatch as technical
import volume_and_flow_context_v2 as flow
from governed_session_chain import are_consecutive_governed_sessions

CONTRACT_VERSION = "first_real_session_acceptance/v1"
STATES = ("OPEN", "PROGRESSED", "STILL_BLOCKED", "NOT_EVALUABLE")

class VerifiedContextSummary(dict):
    """Only populated after full per-record and source-stream verification."""

class VerifiedFlowSummary(dict):
    """Compact verified facts/pointers; full source payloads are discarded."""


def capability(name, predicates, *, evidence_present, progressed=False, details=None):
    if any(v is not None and not isinstance(v,bool) for v in predicates.values()):
        raise ValueError("CAPABILITY_BOOLEAN_PREDICATES_REQUIRED")
    state = ("NOT_EVALUABLE" if not evidence_present else "OPEN" if predicates and all(v is True for v in predicates.values())
             else "PROGRESSED" if progressed else "STILL_BLOCKED")
    return {"capability":name,"state":state,"opening_predicates":predicates,
            "blockers":[k for k,v in predicates.items() if v is not True],"details":details or {}}


def evaluate(*, session, cutoff, calendar, capture_record=None, marker=None, readiness=None,
             technical_contexts=None, sealed_bindings=None, flow_records=None, thesis_state=None,
             valuation=None, liquidity=None, diagnostic=False):
    market._utc(cutoff,"cutoff")
    rows=[]
    def add(name,predicates,present,progress=False,details=None):
        rows.append(capability(name,predicates,evidence_present=bool(present),progressed=progress,details=details))
    parts=[p for p in calendar["segments"] if session in p["sessions"]]
    add("calendar_receipt",{"session_supported":bool(parts),"no_disagreement":not any(session in c["sessions"] for c in calendar["overlap_disagreements"])},calendar["sources"],details={"calendar_identity":calendar["artifact_identity"],"unsupported_gaps":calendar["unsupported_gaps"]})
    days=[d for p in parts for d in p["sessions"] if d<=session]
    proof=are_consecutive_governed_sessions(days[-2],session,cutoff,calendar) if len(days)>1 else {"state":"UNKNOWN","reason":"PRIOR_SUPPORTED_SESSION_UNAVAILABLE"}
    add("calendar_continuity",{"immediate_next_governed_session":proof["state"]=="TRUE"},parts,details=proof)
    add("capture_session",{"verified_complete_session":bool(capture_record and capture_record.get("capture_complete_tickers"))},capture_record,details={"identity":(capture_record or {}).get("artifact_identity")})
    add("first_marker",{"bound_first_complete_record":bool(marker and capture_record and marker["session"]<=session)},capture_record,details={"session":(marker or {}).get("session")})
    r=readiness or {}; tickers=list(r.get("per_ticker",{}).values())
    add("readiness_state",{"bounded_evaluation_depth":r.get("status")=="READY_FOR_BOUNDED_EVALUATION","no_chain_gap":not r.get("session_chain_gaps",[])},readiness,bool(r.get("complete_session_count")),{"status":r.get("status"),"complete_session_count":r.get("complete_session_count",0),"counts_at_depth":r.get("counts_at_depth",{})})
    add("positive_listing",{"all_current_capture_names_positive":bool(tickers) and all(t["positive_listing_depth"]>=1 and t["exchange"]!="UNKNOWN" for t in tickers)},tickers,details={"exchange_counts":r.get("exchange_binding_counts",{})})
    add("representation_tier",{"all_names_have_source_representation":bool(tickers) and all(t["representation_tier"] in {capture.NATIVE,capture.ECONOMIC} for t in tickers)},tickers,details={"tier_counts":r.get("representation_tier_counts",{})})
    add("official_verification",{"all_current_names_officially_matched":bool(tickers) and all((t.get("raw_use_state") or {}).get("official_match_status")=="VERIFIED_MATCH" for t in tickers)},tickers,details={"states":r.get("official_verification_state_counts",{})})
    contexts=technical_contexts or {}; exact={}
    for ticker,c in contexts.items():
        if not isinstance(technical_contexts,VerifiedContextSummary): technical.verify_context(c,ticker=ticker,session=session)
        exact[ticker]=(session,c["contract_version"],c["artifact_identity"])
    add("technical_v2_production_routing",{"all_contexts_v2":bool(contexts) and all(c["contract_version"]==technical.V2 for c in contexts.values()),"production_session":session>=technical.PRODUCTION_V2_START_SESSION},contexts,details={"contexts":len(contexts)})
    add("exact_t0_v2_seal_index",{"all_exact_contexts_sealed":bool(exact and sealed_bindings) and all(sealed_bindings.bindings.get(t)==identity for t,identity in exact.items())},contexts,details={"snapshot_identity":getattr(sealed_bindings,"snapshot_identity",None)})
    records=flow_records or {}; items=[]
    for ticker,row in records.items():
        if not isinstance(flow_records,VerifiedFlowSummary): flow.verify(row,"volume_flow_instrument/v2")
        if row["ticker"]!=ticker or row["session"]!=session: raise ValueError("ACCEPTANCE_FLOW_SCOPE_INVALID")
        for i in row["items"]:
            if not isinstance(flow_records,VerifiedFlowSummary): flow.verify(i,flow.ITEM_VERSION)
            items.append(i)
    add("volume_flow_v2_production_routing",{"all_rows_v2":bool(records) and all(row["technical_contract_version"]==technical.V2 or not row["in_current_research_scope"] for row in records.values())},records,details={"records":len(records)})
    native=[i for i in items if i["sub_domain"]=="NATIVE_VOLUME_REFERENCE"]
    native_t0=[i for i in native if i["knowledge_stage"]==flow.T0]
    leaks=[i for i in items if i["knowledge_stage"]==flow.T0 and (i["sub_domain"]!="NATIVE_VOLUME_REFERENCE" or not sealed_bindings or
        sealed_bindings.bindings.get(i["instrument"]["ticker"])!=(session,technical.V2,i["technical_context_identity"]) or
        sealed_bindings.snapshot_identity not in i["source_artifact_identities"])]
    add("t0_native_volume",{"nonempty_exact_native_seals":bool(native_t0),"no_false_seals":not leaks},records,details={"count":len(native_t0)})
    add("post_to_t0_leakage",{"zero_leakage":not leaks},records,details={"count":len(leaks)})
    foreign=[i for i in items if i["sub_domain"]=="FOREIGN_VALUE" and i["coverage_scope"]["in_cohort"]]
    for n in (1,5,10,20):
        window=[i for i in foreign if i["required_observations"]==n]
        eligible=[i for i in window if i["status"] in flow.USABLE and i["freshness"]=="CURRENT_SESSION"]
        add("foreign_"+str(n)+"_session_maturity",{"whole_retained_cohort_mature":bool(window) and len(eligible)==len(window)},window,bool(eligible) and len(eligible)<len(window),{"qualified":len(eligible),"cohort":len(window)})
    proofs=[i.get("session_continuity") or {} for i in foreign if i["required_observations"]==5]
    add("foreign_continuity",{"governed_five_session_proof":bool(proofs) and all(p.get("proof_state")=="PROVEN_CONTINUOUS" and p.get("source")=="governed_calendar_evidence_at_cutoff/v1" for p in proofs)},foreign,details={"proofs":proofs})
    relationships=[i.get("price_flow_relationship") or {} for i in foreign]
    add("price_flow_relationships",{"qualified_owner_relations":bool(relationships) and all(p.get("evidence_quality")=="COMPLETE_RETAINED_EVIDENCE" for p in relationships)},foreign,details={"states":dict(Counter(p.get("state","UNKNOWN") for p in relationships))})
    for tf in ("1W","1M"):
        states=[c["timeframes"][tf]["context"].get("temporal",{}).get("state","UNKNOWN") for c in contexts.values()]
        add(tf+"_period_states",{"qualified_current_completed_period":bool(states) and all(s in {"CURRENT_PERIOD_COMPLETED","IMMEDIATELY_PREVIOUS_COMPLETED_PERIOD"} for s in states)},contexts,details={"states":dict(Counter(states))})
    thesis=thesis_state or {}
    add("thesis_stage_1_presence",{"released_complete":thesis.get("stage_1")=="COMPLETE","offline_boundary":thesis.get("stage_1_offline") is True},thesis,details=thesis)
    add("thesis_stage_2_status",{"installed_complete":thesis.get("stage_2")=="COMPLETE"},thesis.get("stage_2") not in {None,"NOT_STARTED"},details={"status":thesis.get("stage_2","NOT_STARTED")})
    add("pit_continuous_price",{"continuous_price_and_membership":bool(tickers) and all(t["pit_component_readiness"]["continuous_price"] and t["pit_component_readiness"]["observed_price_and_membership"] for t in tickers)},readiness,bool(tickers))
    add("raw_as_traded",{"all_names_exact_raw_authorized":bool(tickers) and all("PROSPECTIVE_RAW_AS_TRADED_PRICE" in (t.get("raw_use_state") or {}).get("allowed_uses",[]) for t in tickers)},tickers)
    add("ca",{"qualified_factor_chain_or_nonapplicability":bool(tickers) and all(t.get("ca_comparability")=="QUALIFIED_COMPARABLE" for t in tickers)},readiness,details={"blockers":r.get("ca_blockers",[])})
    for name,data in (("valuation",valuation),("liquidity_execution",liquidity)):
        add(name,{"qualified_requested_use":bool(data and data.get("requested_use_allowed")),"source_fitness_available":bool(data and data.get("status")=="AVAILABLE")},data,
            bool(data and data.get("qualified_count")),details=data)
    body={"contract_version":CONTRACT_VERSION,"session":session,"knowledge_cutoff":cutoff,"rows":rows,
        "evaluation_scope":"SYNTHETIC_FIXTURE_DIAGNOSTIC" if diagnostic else "READ_ONLY_POST_DAILY_DIAGNOSTIC",
        "authority_effect":"NONE / MONDAY_LIVE_READINESS_ENGINEERING_ONLY","authority_publication":False}
    body.update(market.content_identity(body,kind="first_real_session_acceptance")); return body


def collect(root, *, session, cutoff, technical_path=None, flow_path=None, snapshot_binding=None, decision_path=None):
    """Explicit artifacts only; large corpora parsed once with bounded members."""
    from bounded_artifact_stream import stream_artifact
    from prospective_t0_seal_index import load_verified
    root=Path(root); calendar=capture_store.calendar_evidence_at_cutoff(root,cutoff=cutoff)
    record_path=root/capture_store.STORE/"sessions"/(session+".json")
    record=capture_store.verify_complete_session(root,capture_store._read(record_path)) if record_path.exists() else None
    marker=capture_store.load_marker(root)
    if record and market._utc(record["completion_known_at"],"known_at")>market._utc(cutoff,"cutoff"): record=None
    if marker and market._utc(marker["written_at"],"known_at")>market._utc(cutoff,"cutoff"): marker=None
    readiness=capture_store.CaptureIndex(root,cutoff=cutoff).readiness(session=session)
    contexts={}; records={}
    for path,kind,target in ((technical_path,"TECHNICAL",contexts),(flow_path,"FLOW",records)):
        if not path: continue
        def retain(t,r):
            if kind=="TECHNICAL" and r.get("contextual_technical"):
                c=r["contextual_technical"]
                technical.verify_context(c,ticker=t,session=session)
                if market._utc(c["knowledge_cutoff"],"source_cutoff")>market._utc(cutoff,"cutoff"):
                    raise ValueError("ACCEPTANCE_TECHNICAL_LOOKAHEAD")
                target[t]={k:c[k] for k in ("contract_version","artifact_identity")}
                target[t]["timeframes"]={tf:{"context":{"temporal":{"state":frame["context"].get("temporal",{}).get("state","UNKNOWN")}}} for tf,frame in c["timeframes"].items()}
            elif kind=="FLOW":
                flow.verify(r,"volume_flow_instrument/v2")
                if r.get("contract_version") is not None and r["contract_version"]!="volume_flow_instrument/v2":
                    raise ValueError("ACCEPTANCE_FLOW_RECORD_VERSION_INVALID")
                target[t]={k:r[k] for k in ("ticker","session","technical_contract_version","in_current_research_scope")}
                target[t]["items"]=[]
                for item in r["items"]:
                    flow.verify(item,flow.ITEM_VERSION)
                    if item.get("contract_version")!=flow.ITEM_VERSION: raise ValueError("ACCEPTANCE_FLOW_ITEM_VERSION_INVALID")
                    target[t]["items"].append({k:item[k] for k in ("sub_domain","knowledge_stage","instrument","technical_context_identity","source_artifact_identities","coverage_scope","required_observations","status","freshness","session_continuity","price_flow_relationship") if k in item})
        meta,digest,_=stream_artifact(Path(path),excluded={"artifact_identity","artifact_sha256"},on_record=retain)
        if meta.get("artifact_sha256")!=digest or meta.get("session")!=session:
            raise ValueError("ACCEPTANCE_SOURCE_ARTIFACT_INVALID")
        if kind=="FLOW" and meta.get("contract_version")!=flow.CONTRACT_VERSION:
            raise ValueError("ACCEPTANCE_FLOW_SOURCE_VERSION_INVALID")
    contexts=VerifiedContextSummary(contexts);records=VerifiedFlowSummary(records)
    valuation=liquidity=None
    if decision_path:
        import integrated_investment_decision_product as decisions
        counts=Counter()
        def inspect_decision(t,row):
            if row.get("ticker")!=t or row.get("as_of_session")!=session or decisions.decision_identity(row)!=row.get("decision_identity"):
                raise ValueError("ACCEPTANCE_DECISION_IDENTITY_INVALID")
            dimensions=(row.get("current_research_decision_input") or {}).get("dimensions") or {}
            counts["valuation/"+(dimensions.get("VALUATION") or {}).get("state","UNKNOWN")]+=1
            counts["liquidity/"+((dimensions.get("LIQUIDITY") or {}).get("execution") or {}).get("state","UNKNOWN")]+=1
        meta,digest,total=stream_artifact(Path(decision_path),excluded={"artifact_identity","artifact_sha256"},on_record=inspect_decision)
        if meta.get("artifact_sha256")!=digest or meta.get("session")!=session or meta.get("contract_version")!="integrated_investment_decision_product/v1":
            raise ValueError("ACCEPTANCE_DECISION_ARTIFACT_INVALID")
        def fitness(name):
            qualified=counts[name+"/AVAILABLE"]
            return {"status":"AVAILABLE" if total and qualified==total else "BLOCKED","requested_use_allowed":bool(total and qualified==total),
                "qualified_count":qualified,"denominator":total,"states":{k.split("/",1)[1]:v for k,v in counts.items() if k.startswith(name+"/")},
                "source_identity":meta["artifact_identity"]}
        valuation,liquidity=fitness("valuation"),fitness("liquidity")
    bound=None
    if snapshot_binding and (snapshot_binding.get("seal_index") or {}).get("status")=="RETAINED":
        ref=snapshot_binding["seal_index"]
        try:
            bound=load_verified({**ref,"path":str(root/ref["path"])},expected_snapshot_identity=snapshot_binding["identity"],session=session)
        except FileNotFoundError:
            bound=None
    roadmap=json.loads((Path(__file__).parent/"docs/ROADMAP_STATE.json").read_text(encoding="utf-8"))
    states={m["milestone_id"]:m["state"] for m in roadmap["milestones"]}
    return evaluate(session=session,cutoff=cutoff,calendar=calendar,capture_record=record,marker=marker,readiness=readiness,
        technical_contexts=contexts,sealed_bindings=bound,flow_records=records,valuation=valuation,liquidity=liquidity,
        thesis_state={"stage_1":states.get("THESIS_EVIDENCE_MATRIX_AND_CONFLICT_ENGINE_V1_STAGE_1"),"stage_1_offline":True,
                      "stage_2":states.get("THESIS_EVIDENCE_MATRIX_AND_CONFLICT_ENGINE_V1_STAGE_2_PRODUCTION_INTEGRATION","NOT_STARTED")})
