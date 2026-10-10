"""Offline semantic groups, lenses, conflicts and deterministic decision cards."""
from __future__ import annotations
from collections import defaultdict
import copy
import stocklookup_core.research.thesis_evidence_contract as c
import stocklookup_core.research.thesis_evidence_adapters as adapters

CONTRACT_VERSION="thesis_evidence_matrix/v1"
CARD_VERSION="offline_thesis_decision_card/v1"
ACTIVE_CONFLICTS=("TECHNICAL_INTRA_TIMEFRAME_CONFLICT","TECHNICAL_TIMEFRAME_DIVERGENCE",
    "TECHNICAL_FUNDAMENTAL_DIVERGENCE","FUNDAMENTAL_VALUATION_DIVERGENCE","PRICE_FLOW_DIVERGENCE",
    "MACRO_SECTOR_DIVERGENCE","TIME_HORIZON_MISMATCH","EVIDENCE_FRESHNESS_MISMATCH",
    "AUTHORITY_MISMATCH","PORTFOLIO_FIT_THESIS_MISMATCH")
DORMANT_CONFLICTS=("FORWARD_EXPECTATION_DIVERGENCE",)
DECISION_AXES={c.LENSES[0]:("FUNDAMENTAL","VALUATION","TECHNICAL"),c.LENSES[1]:("TECHNICAL","MACRO_SECTOR")}
ANCHOR={c.LENSES[0]:"FUNDAMENTAL",c.LENSES[1]:"TECHNICAL"}


def semantic_groups(items,lens):
    """One state per common cause and stage. Identical copies are idempotent."""
    grouped=defaultdict(list)
    unique={item["artifact_identity"]:item for item in items}
    for item in unique.values():
        key=(item["correlation_group"],item["knowledge_stage"])
        grouped[key].append(item)
    result=[]
    for (cause,stage), members in sorted(grouped.items()):
        members=sorted(members,key=lambda i:i["artifact_identity"])
        directional=[i for i in members if i["lens_binding"][lens]!="CONTEXT" and i["fitness"]["direction_eligible"]]
        known={i["state"] for i in directional}
        state="MIXED" if "MIXED" in known or {"SUPPORTS","OPPOSES"}<=known else (
            "SUPPORTS" if "SUPPORTS" in known else "OPPOSES" if "OPPOSES" in known else "NEUTRAL" if known else "UNKNOWN")
        # Volume/Flow owns canonical volume. Context copies remain referenced but cannot vote.
        owners=[i for i in members if i["source"]["contract_version"]=="volume_and_flow_evidence/v2"]
        axis=(owners or directional or members)[0]["axis"]
        if len({i["axis"] for i in directional})>1: raise ValueError("THESIS_CORRELATION_DIRECTION_OWNER_CONFLICT")
        roles={i["lens_binding"][lens] for i in (directional or members)}-{"CONTEXT"}
        if not directional and roles and all(i["state"]=="NOT_APPLICABLE" for i in members): state="NOT_APPLICABLE"
        body={"lens":lens,"knowledge_stage":stage,"correlation_group":cause,"axis":axis,"state":state,
            "role":"PRIMARY" if "PRIMARY" in roles else "SECONDARY" if roles else "CONTEXT",
            "member_identities":[i["artifact_identity"] for i in members],
            "directional_member_identities":[i["artifact_identity"] for i in directional],
            "canonical_evidence_keys":sorted({i["canonical_evidence_key"] for i in members}),
            "timeframes":sorted({i["horizon"].split("/")[0] for i in directional}),
            "unknown_classes":sorted({i["unknown_class"] for i in members if i["state"]=="UNKNOWN"}),
            "neutral_qualifier":"NEUTRAL_GROUP_MEMBERS_PRESENT" if "NEUTRAL" in known and state in {"SUPPORTS","OPPOSES"} else None,
            "representative_policy":"SEMANTIC_GROUP_NO_MEMBER_PRECEDENCE"}
        result.append(c.seal(body,"thesis_correlation_group/v1"))
    return result


def verify_matrix(matrix,*,sealed_bindings=None):
    c.verify_identity(matrix,CONTRACT_VERSION)
    card=matrix["decision_card"]
    c.verify_identity(card,CARD_VERSION)
    reference={k:v for k,v in card["ACTION SUPPORT REFERENCE"].items() if k!="second_posture"}
    registers={k:v for k,v in card["registers"].items() if k!="evidence_staleness"}
    rebuilt=build_matrix(ticker=matrix["ticker"],session=matrix["session"],items=matrix["items"],
        decision_reference=reference,registers=registers,sealed_bindings=sealed_bindings,evaluation_scope=matrix["evaluation_scope"])
    if c.canonical(rebuilt)!=c.canonical(matrix): raise ValueError("THESIS_DERIVED_PROJECTION_INVALID")
    return matrix


def reduce_axis(groups,axis,*,higher_required=False):
    selected=[g for g in groups if g["axis"]==axis]
    primary=[g for g in selected if g["role"]=="PRIMARY"]
    states={g["state"] for g in primary}
    unknown=None;qualifiers=[]
    if "MIXED" in states or {"SUPPORTS","OPPOSES"}<=states: state="MIXED"
    elif "SUPPORTS" in states: state="SUPPORTS"
    elif "OPPOSES" in states: state="OPPOSES"
    elif states=={"NEUTRAL"}: state="NEUTRAL"
    elif states=={"NOT_APPLICABLE"}: state="NOT_APPLICABLE"
    else:
        state="UNKNOWN"
        classes={u for g in primary for u in g["unknown_classes"]}
        unknown="HIGHER_TIMEFRAME_UNKNOWN" if higher_required else next(iter(classes)) if len(classes)==1 else "UNRESOLVED" if classes else "PRIMARY_EVIDENCE_MISSING" if any(g["role"]=="SECONDARY" for g in selected) else "CONTEXT_ONLY" if selected else "MISSING"
    if state in {"SUPPORTS","OPPOSES"} and "NEUTRAL" in states: qualifiers.append("NEUTRAL_PRIMARY_GROUPS_PRESENT")
    if any(g["neutral_qualifier"] for g in primary): qualifiers.append("NEUTRAL_CORRELATED_MEMBERS_PRESENT")
    if state in {"SUPPORTS","OPPOSES","MIXED"} and "UNKNOWN" in states: qualifiers.append("UNKNOWN_PRIMARY_GROUPS_PRESENT")
    return {"state":state,"unknown_class":unknown,"qualifiers":qualifiers,
        "primary_group_identities":[g["artifact_identity"] for g in primary],
        "context_group_identities":[g["artifact_identity"] for g in selected if g["role"]!="PRIMARY"]}


def reduce_lens(axes,lens):
    anchor=axes[ANCHOR[lens]]["state"]
    selected={a:axes[a]["state"] for a in DECISION_AXES[lens]}
    # Macro is a decision input only where its standing directional contract qualifies.
    if lens==c.LENSES[1] and selected["MACRO_SECTOR"]=="UNKNOWN": selected.pop("MACRO_SECTOR")
    states=set(selected.values())
    if anchor in {"UNKNOWN","NOT_APPLICABLE"}: state="INSUFFICIENT_EVIDENCE"
    elif "MIXED" in states or {"SUPPORTS","OPPOSES"}<=states: state="CONTESTED"
    elif anchor=="OPPOSES": state="ADVERSE"
    elif anchor=="SUPPORTS" and states<={"SUPPORTS","NEUTRAL"}: state="SUPPORTIVE"
    else: state="NOT_CONFIRMED"
    return {"state":state,"anchor_axis":ANCHOR[lens],"decision_axes":selected,
        "context_axes":[a for a in c.AXES if a not in selected],"is_actionable":False}


def conflicts(items,groups,axes,lens):
    result=[]
    by_id={i["artifact_identity"]:i for i in items}
    def emit(kind,refs,changing=False):
        c.checked(kind,ACTIVE_CONFLICTS,"conflict")
        refs=sorted(set(refs))
        if not refs: return
        result.append(c.seal({"kind":kind,"lens":lens,"source_references":refs,
            "state_changing":changing,"knowledge_scope":"CURRENT_VIEW_ANNOTATION", "non_voting":True},"thesis_conflict/v1"))
    eligible=[g for g in groups if g["role"]=="PRIMARY" and g["state"] in {"SUPPORTS","OPPOSES","MIXED"}]
    technical=[g for g in eligible if g["axis"]=="TECHNICAL"]
    for group in technical:
        if group["state"]=="MIXED": emit("TECHNICAL_INTRA_TIMEFRAME_CONFLICT",group["directional_member_identities"],True)
    for n,left in enumerate(technical):
        for right in technical[n+1:]:
            if ({left["state"],right["state"]}=={"SUPPORTS","OPPOSES"} and left["knowledge_stage"]==right["knowledge_stage"]
                    and lens==c.LENSES[0] and set(left["timeframes"]+right["timeframes"])<={"1W","1M"}):
                emit("TECHNICAL_TIMEFRAME_DIVERGENCE",left["directional_member_identities"]+right["directional_member_identities"],True)
    for left,right,kind in (("TECHNICAL","FUNDAMENTAL","TECHNICAL_FUNDAMENTAL_DIVERGENCE"),
                           ("FUNDAMENTAL","VALUATION","FUNDAMENTAL_VALUATION_DIVERGENCE"),
                           ("TECHNICAL","MACRO_SECTOR","MACRO_SECTOR_DIVERGENCE")):
        # Context in a different horizon never contests an anchor in this lens.
        if left in DECISION_AXES[lens] and right in DECISION_AXES[lens] and {axes[left]["state"],axes[right]["state"]}=={"SUPPORTS","OPPOSES"}:
            emit(kind,[i for g in eligible if g["axis"] in {left,right} for i in g["directional_member_identities"]],True)
    for item in items:
        if item["state"] in {"UNKNOWN","NOT_APPLICABLE"} or not item["fitness"]["fact_eligible"]: continue
        for relation in item["relations"]:
            # Read owner-produced price × flow relation; never re-evaluate its signs.
            if (relation.get("owner_contract")=="flow_price_divergence_shadow/v1"
                    and relation.get("fitness") in {"PARTIAL_RETAINED_EVIDENCE","COMPLETE_RETAINED_EVIDENCE"}
                    and relation.get("state") in {"PERSISTENT_FOREIGN_SELLING_PRICE_RESILIENCE","FOREIGN_SELLING_PRICE_RESILIENCE","FOREIGN_BUYING_PRICE_WEAKNESS"}):
                emit("PRICE_FLOW_DIVERGENCE",[item["artifact_identity"],relation["source_identity"]])
        # Metadata anomaly predicates require explicit comparable scope; UNKNOWN never participates.
        if item["lens_binding"][lens]=="PRIMARY" and item["axis"]=="TECHNICAL" and (
            lens==c.LENSES[0] and item["horizon"]=="1D" or lens==c.LENSES[1] and item["horizon"] in {"1W","1M"}):
            emit("TIME_HORIZON_MISMATCH",[item["artifact_identity"]])
        if any(r.get("requested_view")=="T0_THESIS_VIEW" for r in item["relations"]) and item["authority_ceiling"]=="CURRENT_RESEARCH_VIEW_ONLY":
            emit("AUTHORITY_MISMATCH",[item["artifact_identity"]])
        if item["axis"]=="LIQUIDITY_PORTFOLIO" and any(r.get("state")=="PORTFOLIO_CONSTRAINT_VIOLATED" for r in item["relations"]) and axes[ANCHOR[lens]]["state"]=="SUPPORTS":
            emit("PORTFOLIO_FIT_THESIS_MISMATCH",[item["artifact_identity"]])
    known=[i for i in items if i["state"] not in {"UNKNOWN","NOT_APPLICABLE"} and i["fitness"]["fact_eligible"]]
    for n,left in enumerate(known):
        for right in known[n+1:]:
            if (left["canonical_evidence_key"]==right["canonical_evidence_key"] and left["knowledge_stage"]==right["knowledge_stage"]
                    and {left["freshness"] in c.FRESH,right["freshness"] in c.FRESH}=={True,False}):
                emit("EVIDENCE_FRESHNESS_MISMATCH",[left["artifact_identity"],right["artifact_identity"]])
    return sorted({r["artifact_identity"]:r for r in result}.values(),key=lambda r:r["artifact_identity"])


def counter_thesis(items,groups,events,lens):
    return {"lens":lens,"opposing_evidence":[i["artifact_identity"] for i in items if i["state"]=="OPPOSES" and i["fitness"]["direction_eligible"] and i["lens_binding"][lens]!="CONTEXT"],
        "contesting_groups":[g["artifact_identity"] for g in groups if g["state"]=="MIXED"],
        "state_changing_conflicts":[e["artifact_identity"] for e in events if e["state_changing"]],
        "missing_or_unverified":[{"evidence_identity":i["artifact_identity"],"unknown_class":i["unknown_class"]} for i in items if i["state"]=="UNKNOWN" and i["lens_binding"][lens]!="CONTEXT"],
        "unknown_is_opposing":False}


def quality(items):
    dimensions={}
    for field in ("authority_ceiling","freshness","basis","knowledge_stage"):
        dimensions[field]=sorted({c.canonical(i[field]) for i in items})
    return {"dimensions":dimensions,"blocker_codes":sorted({r for i in items for r in i["blocker_codes"]+i["reason_codes"]}),
        "coverage_references":[i["artifact_identity"] for i in items if i["coverage"]],
        "missing_denominator_references":[i["artifact_identity"] for i in items if any("DENOMINATOR" in r for r in i["blocker_codes"]+i["reason_codes"])],
        "source_conflict_references":[i["artifact_identity"] for i in items if i["state"]=="MIXED"],
        "directional":False,"is_actionable":False}


def build_matrix(*,ticker,session,items,decision_reference,registers=None,sealed_bindings=None,evaluation_scope="OFFLINE_RESEARCH"):
    c.checked(evaluation_scope,("OFFLINE_RESEARCH","REPLAY_DIAGNOSTIC"),"evaluation_scope")
    if set(decision_reference)!={"decision_identity","research_action_posture"} or not str(decision_reference["decision_identity"]).startswith("decision:"+ticker+":"):
        raise ValueError("THESIS_ACTION_REFERENCE_SCOPE_INVALID")
    c.checked(decision_reference.get("research_action_posture"),
        ("EARLY_WATCH","INITIATE_ON_BREAKOUT","ACCUMULATE_ON_RETEST","WAIT_FOR_CONFIRMATION","HOLD","HOLD_DO_NOT_ADD","REDUCE","AVOID","INSUFFICIENT_CURRENT_RESEARCH"),"action_reference")
    unique={}
    for item in items:
        c.verify_item(item)
        if item["subject"]!={"ticker":ticker,"session":session}: raise ValueError("THESIS_ITEM_SCOPE_MISMATCH")
        if item["knowledge_stage"]=="T0_SEALED":
            if sealed_bindings is None: raise ValueError("THESIS_GENUINE_T0_BINDING_REQUIRED")
            sealed_bindings.verify(item)
        unique[item["artifact_identity"]]=copy.deepcopy(item)
    ordered=sorted(unique.values(),key=lambda i:i["artifact_identity"])
    views={}
    for view in c.VIEWS:
        scoped=[i for i in ordered if view=="CURRENT_RESEARCH_VIEW" or i["knowledge_stage"]=="T0_SEALED"]
        lenses={}
        for lens in c.LENSES:
            groups=semantic_groups(scoped,lens)
            axes={a:reduce_axis(groups,a,higher_required=a=="TECHNICAL" and lens==c.LENSES[0]) for a in c.AXES}
            events=conflicts(scoped,groups,axes,lens)
            cross_stage=[]
            if view=="CURRENT_RESEARCH_VIEW":
                for n,left in enumerate(groups):
                    for right in groups[n+1:]:
                        if (left["correlation_group"]==right["correlation_group"] and left["knowledge_stage"]!=right["knowledge_stage"]
                                and {left["state"],right["state"]}=={"SUPPORTS","OPPOSES"}):
                            cross_stage.append({"kind":"SEALED_VS_POST_DIRECTIONAL_CONTRADICTION",
                                "group_references":sorted([left["artifact_identity"],right["artifact_identity"]]),"current_research_annotation_only":True})
            lenses[lens]={"axes":axes,"groups":groups,"lens":reduce_lens(axes,lens),"conflicts":events,"cross_stage_annotations":cross_stage,
                "counter_thesis":counter_thesis(scoped,groups,events,lens)}
        views[view]={"availability":"AVAILABLE" if scoped else "UNAVAILABLE","evidence_identities":[i["artifact_identity"] for i in scoped],
            "lenses":lenses,"evidence_quality":quality(scoped)}
    base_registers=copy.deepcopy(registers or {k:{"state":"UNKNOWN","entries":[],"reason_codes":["EXISTING_PRODUCER_CONDITION_ABSENT"]} for k in ("thesis_confirmation","setup_confirmation","thesis_invalidation","setup_invalidation")})
    if set(base_registers)!={"thesis_confirmation","setup_confirmation","thesis_invalidation","setup_invalidation"}:
        raise ValueError("THESIS_REGISTER_VOCABULARY_INVALID")
    for register in base_registers.values():
        c.checked(register["state"],("UNKNOWN","REFERENCED"),"register_state")
        if any(e["source_decision_identity"]!=decision_reference["decision_identity"] for e in register["entries"]):
            raise ValueError("THESIS_REGISTER_SOURCE_SCOPE_INVALID")
    base_registers["evidence_staleness"]={"state":"REFERENCED" if any(i["freshness"] not in c.FRESH for i in ordered) else "UNKNOWN",
        "evidence_identities":[i["artifact_identity"] for i in ordered if i["freshness"] not in c.FRESH]}
    current=views["CURRENT_RESEARCH_VIEW"]
    def lens_card(lens):
        projection=current["lenses"][lens]
        return {**projection["lens"],"axis_states":{a:v["state"] for a,v in projection["axes"].items()},
            "supporting_group_references":[g["artifact_identity"] for g in projection["groups"] if g["role"]=="PRIMARY" and g["state"]=="SUPPORTS"],
            "opposing_group_references":[g["artifact_identity"] for g in projection["groups"] if g["role"]=="PRIMARY" and g["state"]=="OPPOSES"],
            "counter_thesis_reference":"views.CURRENT_RESEARCH_VIEW.lenses."+lens+".counter_thesis"}
    card=c.seal({"contract_version":CARD_VERSION,"HEADER":{"ticker":ticker,"session":session,"mode":"OFFLINE_NON_VOTING","evaluation_scope":evaluation_scope,"authority_status":"NON_AUTHORITATIVE"},
        "MARKET / SECTOR CONTEXT":{lens:current["lenses"][lens]["axes"]["MACRO_SECTOR"] for lens in c.LENSES},
        "LONG TERM":lens_card(c.LENSES[0]),"SHORT TERM":lens_card(c.LENSES[1]),
        "CONFLICTS":{lens:current["lenses"][lens]["conflicts"] for lens in c.LENSES},
        "EVIDENCE QUALITY":current["evidence_quality"],"ACTION SUPPORT REFERENCE":{**copy.deepcopy(decision_reference),"second_posture":False},
        "registers":base_registers,"is_actionable":False},CARD_VERSION)
    result=c.seal({"contract_version":CONTRACT_VERSION,"ticker":ticker,"session":session,"authority_effect":c.AUTHORITY,
        "evaluation_scope":evaluation_scope,"authority_status":"NON_AUTHORITATIVE",
        "items":ordered,"views":views,"decision_card":card,"non_voting":True,"is_actionable":False},CONTRACT_VERSION)
    c.scan_forbidden(result)
    return result
