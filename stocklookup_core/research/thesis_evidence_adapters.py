"""Versioned offline adapters. Read producer semantics; never recreate relations."""
from __future__ import annotations
import copy
import stocklookup_core.research.thesis_evidence_contract as c

FUNDAMENTAL = {"IMPROVING": "SUPPORTS", "STABLE": "NEUTRAL", "MIXED": "MIXED",
    "DETERIORATING": "OPPOSES", "TURNAROUND": "SUPPORTS", "INSUFFICIENT": "UNKNOWN"}
AVAILABILITY = {"CURRENT_DIRECTIONAL": None, "CURRENT_NON_DIRECTIONAL": "UNRESOLVED",
    "STALE_ONLY": "STALE", "NOT_APPLICABLE_ENTITY": "NOT_APPLICABLE", "ABSENT": "MISSING"}
PEER = {"CHEAP_VS_PEERS": "SUPPORTS", "EXPENSIVE_VS_PEERS": "OPPOSES", "MID_RANGE_VS_PEERS": "NEUTRAL",
    "NOT_APPLICABLE": "UNKNOWN", "UNAVAILABLE": "UNKNOWN", None: "UNKNOWN"}
MARKET = {"BROAD_PARTICIPATION": "SUPPORTS", "DETERIORATING_BREADTH": "OPPOSES",
    "NARROW_LEADERSHIP": "NEUTRAL", "MIXED_BREADTH": "NEUTRAL", "DATA_LIMITED": "UNKNOWN", "UNAVAILABLE": "UNKNOWN"}
SECTOR = {"LEADING": "SUPPORTS", "WEAKENING": "OPPOSES", "MIXED": "NEUTRAL",
    "IN_LINE": "UNKNOWN", "UNKNOWN": "UNKNOWN", None: "UNKNOWN"}
LEGACY_PARTICIPATION = ("CONFIRMED", "PARTIALLY_CONFIRMED", "NEUTRAL", "CONTRADICTED", "INSUFFICIENT_EVIDENCE")
AXIS_NAMES = ("FUNDAMENTAL", "VALUATION", "TACTICAL_STRUCTURE", "MOMENTUM", "PARTICIPATION_CONFIRMATION",
    "MARKET_SECTOR", "OPPORTUNITY_PRIORITY", "PORTFOLIO_FIT", "CORPORATE_INTELLIGENCE")
FITNESS = ("AVAILABLE", "PARTIAL", "UNAVAILABLE", "INPUT_BLOCKED", "INSUFFICIENT_EVIDENCE", "NOT_PROVIDED",
    "RESEARCH_PROXY_CONTEXT", "CURRENT_RESEARCH_ONLY", "RESEARCH_USABLE", "READY_RESEARCH_ONLY", "ABSENT", "NO_QUALIFIED_CORPORATE_EVENT")
CORPORATE_STATES=("NO_QUALIFIED_CORPORATE_EVENT","CATALYST_PRESENT","RISK_PRESENT","MIXED_EVIDENCE","INFORMATIONAL_ONLY","UNRESOLVED_EVIDENCE","NOT_PROVIDED")
FLOW_STATUSES = ("AVAILABLE", "DESCRIPTIVE_ONLY", "RESEARCH_USABLE", "INSUFFICIENT_HISTORY", "UNAVAILABLE",
    "BLOCKED_CA_COMPARABILITY", "BLOCKED_BASIS", "BLOCKED_SESSION_CONTINUITY", "NOT_APPLICABLE_ZERO_REFERENCE", "SOURCE_FIELD_UNAVAILABLE")
PRICE_FLOW = ("PRICE_EVIDENCE_INSUFFICIENT", "FLOW_UNAVAILABLE", "RELATIONSHIP_NOT_EVALUABLE",
    "PERSISTENT_FOREIGN_SELLING_PRICE_RESILIENCE", "FOREIGN_SELLING_PRICE_RESILIENCE",
    "FOREIGN_SELLING_PRICE_WEAKNESS", "FOREIGN_BUYING_PRICE_CONFIRMATION", "FOREIGN_BUYING_PRICE_WEAKNESS",
    "FLOW_NEUTRAL_PRICE_IMPROVING", "FLOW_NEUTRAL_PRICE_DETERIORATING", "FLOW_PRICE_MIXED")
METHODS = {"FUNDAMENTAL": ("financial_analysis_product_integration/v1", "entity_aware_operational_fundamental_context_integration/v1"),
    "VALUATION": ("current_research_valuation_context/v1",), "MARKET_SECTOR": ("current_market_sector_leadership_context/v1",),
    "PORTFOLIO_FIT": ("integrated_investment_decision_product/portfolio_context/v1",),
    "PARTICIPATION_CONFIRMATION": ("tactical_confirmation_context/v1",),
    "CORPORATE_INTELLIGENCE": ("current_corporate_intelligence_axis/v1",)}
REGISTRY = {"contract_version": c.REGISTRY_VERSION, "fundamental_state": FUNDAMENTAL,
    "fundamental_availability": AVAILABILITY, "peer_relative_state": {str(k): v for k,v in PEER.items()},
    "market_regime": MARKET, "sector_leadership": {str(k):v for k,v in SECTOR.items()},
    "integrated_axis_names": AXIS_NAMES, "integrated_fitness": FITNESS, "axis_methods": METHODS,
    "legacy_participation": LEGACY_PARTICIPATION, "flow_status": FLOW_STATUSES,
    "price_flow_relationship": PRICE_FLOW, "participant_policy": "FACTS_ONLY",
    "corporate_states":CORPORATE_STATES,
    "technical_versions": ("contextual_technical_feature_set/v1", "contextual_technical_feature_set/v2"),
    "flow_versions": ("volume_and_flow_context/v2",), "corporate_forward_direction": "DORMANT"}
REGISTRY.update(technical_feature_status=("AVAILABLE","DESCRIPTIVE_ONLY","INSUFFICIENT_HISTORY","SOURCE_FIELD_UNAVAILABLE","BLOCKED_BASIS","BLOCKED_CA_COMPARABILITY"),
    flow_sub_domains=("NATIVE_VOLUME_REFERENCE","RELATIVE_VOLUME_PERSISTENCE","FOREIGN_VALUE","PARTICIPANT_VALUE"),
    participants=(None,"FOREIGN","PROPRIETARY","DOMESTIC_INSTITUTIONAL","OTHER"),
    condition_status=("MACHINE_EVALUABLE","NOT_MACHINE_EVALUABLE","READY","UNAVAILABLE","CONDITIONAL"),
    liquidity_state=("AVAILABLE","PARTIAL","BLOCKED","NON_APPLICABLE"))


def source(identity, contract, pointer):
    return {"identity": identity, "contract_version": contract, "pointer": pointer}


def fact(name, value, semantic, unit, pointer, fitness="SOURCE_DECLARED"):
    return {"name": name, "value": value, "semantic": semantic, "unit": unit, "source_pointer": pointer, "fitness": fitness}


def _stage(ticker, session, identity, basis, bindings, diagnostic=False):
    if (not diagnostic and bindings and "RETROSPECTIVE" not in c.canonical(basis)
            and bindings.contains(ticker, session, identity)):
        return {"stage": "T0_SEALED", "seal_reference": bindings.identity}
    return {"stage": "POST_T0_ENRICHED"}


def adapt_integrated(row, *, bindings=None):
    import stocklookup_core.decision.integrated_investment_decision_product as product
    if row.get("decision_identity") != product.decision_identity(row): raise ValueError("THESIS_DECISION_IDENTITY_INVALID")
    if not product.is_valid_evidence_currency(row.get("evidence_currency")): raise ValueError("THESIS_EVIDENCE_CURRENCY_INVALID")
    ticker, session, identity = row["ticker"], row["as_of_session"], row["decision_identity"]
    axes = row.get("evidence_axes") or {}
    if set(axes) - set(AXIS_NAMES): raise ValueError("THESIS_UNMAPPED_INTEGRATED_AXIS")
    items = []
    def add(axis, sub, upstream, state, unknown="MISSING", *, role="CONTEXT", eligible=False, fresh="UNAVAILABLE", facts=(), coverage=None):
        a = axes.get(upstream) or {}
        if a:
            c.checked(a.get("method"), METHODS[upstream], "axis_method/" + upstream)
            if isinstance(a.get("fitness"), str): c.checked(a["fitness"], FITNESS, "axis_fitness/" + upstream)
        items.append(c.make_item(ticker=ticker, session=session, source=source(identity, product.CONTRACT_VERSION,
            "evidence_axes." + upstream + (".context." + sub if sub in {"market_regime","sector_leadership"} else "")),
            axis=axis, sub_axis=sub, state=state, unknown_class=unknown, role=role, direction_eligible=eligible,
            fact_eligible=eligible or bool(facts), freshness=fresh, facts=facts,
            reasons=a.get("supporting_reason_codes", []) + a.get("contradicting_reason_codes", []),
            blockers=a.get("blocker_reason_codes", []), coverage=coverage,
            lens_roles={c.LENSES[0]:role if axis in {"FUNDAMENTAL","VALUATION"} else "CONTEXT",
                        c.LENSES[1]:role if axis == "MACRO_SECTOR" else "CONTEXT"},
            **_stage(ticker,session,identity,"SOURCE_DECLARED_RESEARCH",bindings)))
    a = axes.get("FUNDAMENTAL") or {};ctx=a.get("context") or {}
    raw=c.checked(a.get("state","INSUFFICIENT"), FUNDAMENTAL,"fundamental")
    availability=c.checked(ctx.get("fundamental_evidence_availability",row.get("fundamental_evidence_availability","ABSENT")),AVAILABILITY,"fundamental_availability")
    state, unknown=FUNDAMENTAL[raw], AVAILABILITY[availability]
    if unknown == "NOT_APPLICABLE": state="NOT_APPLICABLE"
    elif unknown: state="UNKNOWN"
    eligible=availability == "CURRENT_DIRECTIONAL" and state != "UNKNOWN"
    add("FUNDAMENTAL","producer_synthesis","FUNDAMENTAL",state,unknown or "UNRESOLVED",role="PRIMARY",eligible=eligible,
        fresh="CURRENT_REPORTING_PERIOD" if eligible else "STALE" if availability=="STALE_ONLY" else "UNAVAILABLE")
    a=axes.get("VALUATION") or {};ctx=a.get("context") or {}
    state=PEER[c.checked(ctx.get("peer_relative_state"),PEER,"peer_relative")]
    fresh=row.get("evidence_currency") == "CURRENT_SESSION"
    qualified=a.get("fitness") in {"AVAILABLE","PARTIAL","RESEARCH_USABLE"} and fresh
    if not qualified: state="UNKNOWN"
    add("VALUATION","peer_relative","VALUATION",state,"STALE" if not fresh else "UNQUALIFIED",role="PRIMARY",
        eligible=qualified and state != "UNKNOWN",fresh="CURRENT_SESSION" if fresh else "STALE")
    a=axes.get("MARKET_SECTOR") or {};ctx=a.get("context") or {}
    observation=((ctx.get("market_breadth") or {}).get("observation") or {})
    exact=observation.get("session")==session and observation.get("exact_session_observed_count",0)>0
    for sub, mapping in (("market_regime",MARKET),("sector_leadership",SECTOR)):
        raw=ctx.get(sub,a.get("state","UNAVAILABLE") if sub=="market_regime" else None)
        state=mapping[c.checked(raw,mapping,sub)]
        eligible=exact and (sub=="market_regime" or ctx.get("sector_leadership_status")=="AVAILABLE")
        if not eligible: state="UNKNOWN"
        add("MACRO_SECTOR",sub,"MARKET_SECTOR",state,"UNQUALIFIED",role="PRIMARY",eligible=eligible and state!="UNKNOWN",
            fresh="CURRENT_SESSION" if exact else "UNAVAILABLE",
            coverage={k:observation.get(k) for k in ("exact_session_observed_count","official_universe_count","missing_current_session_count")})
    a=axes.get("PARTICIPATION_CONFIRMATION") or {}
    c.checked(a.get("state","INSUFFICIENT_EVIDENCE"),LEGACY_PARTICIPATION,"legacy_participation")
    add("VOLUME","legacy_participation_context","PARTICIPATION_CONFIRMATION","UNKNOWN","CONTEXT_ONLY")
    c.checked((axes.get("CORPORATE_INTELLIGENCE") or {}).get("state","NOT_PROVIDED"),CORPORATE_STATES,"corporate_state")
    add("CORPORATE_FORWARD","forward_driver_context","CORPORATE_INTELLIGENCE","UNKNOWN","POLICY_NOT_AUTHORIZED")
    a=axes.get("PORTFOLIO_FIT") or {};ctx=a.get("context") or {}
    known=a.get("fitness")=="AVAILABLE"
    add("LIQUIDITY_PORTFOLIO","portfolio_fit","PORTFOLIO_FIT","NEUTRAL" if known else "UNKNOWN","MISSING",
        facts=[fact(k,ctx[k],"PRODUCER_PORTFOLIO_CONTEXT","BOOLEAN_OR_CATEGORY","evidence_axes.PORTFOLIO_FIT.context."+k)
               for k in ("is_held","concentration_flag","sector_overlap") if ctx.get(k) is not None])
    # Retained liquidity fitness is separate from portfolio fit; neither judges the thesis.
    liq=((row.get("current_research_decision_input") or {}).get("dimensions") or {}).get("LIQUIDITY") or {}
    if liq: c.checked(liq.get("state"),REGISTRY["liquidity_state"],"liquidity_state")
    items.append(c.make_item(ticker=ticker,session=session,source=source(identity,product.CONTRACT_VERSION,
        "current_research_decision_input.dimensions.LIQUIDITY"),axis="LIQUIDITY_PORTFOLIO",sub_axis="liquidity_readiness",
        state="NEUTRAL" if liq.get("state") in {"AVAILABLE","PARTIAL"} else "UNKNOWN",unknown_class="UNQUALIFIED" if liq else "MISSING",
        fact_eligible=liq.get("state") in {"AVAILABLE","PARTIAL"},
        blockers=liq.get("reason_codes",[]),**_stage(ticker,session,identity,"SOURCE_DECLARED_RESEARCH",bindings)))
    items.append(c.make_item(ticker=ticker,session=session,source=source(identity,product.CONTRACT_VERSION,"evidence_currency"),
        axis="EVIDENCE_QUALITY",sub_axis="source_temporal_explanation",state="NEUTRAL",fact_eligible=True,
        facts=[fact("evidence_currency",row.get("evidence_currency"),"PRODUCER_CURRENT_RESEARCH_EVIDENCE_CURRENCY","CATEGORY","evidence_currency")],
        reasons=["EXPLANATORY_ONLY_NO_DIRECTIONAL_POLARITY"],**_stage(ticker,session,identity,"SOURCE_DECLARED_RESEARCH",bindings)))
    return items


def adapt_technical(context, *, bindings=None):
    import contextual_technical_dispatch as dispatch
    import technical_relationship_view as bridge
    from contextual_technical_primitives import USABLE
    version=dispatch.verify_context(context)
    views=bridge.build_views(context)
    items=[]
    for tf, view in sorted(views.items()):
        fitness, concepts=view["fitness"],view["concepts"]
        fresh=fitness["temporal"]["state"] in {"CURRENT_SESSION","CURRENT_PERIOD_COMPLETED","IMMEDIATELY_PREVIOUS_COMPLETED_PERIOD"}
        usable=view["availability"]["structure_status"] in USABLE
        for feature in context["timeframes"][tf]["features"].values():
            c.checked(feature["status"],REGISTRY["technical_feature_status"],"technical_feature_status")
        basis=fitness["price_basis"]
        raw_comparable=basis != "RAW_AS_TRADED" or (fitness.get("corporate_action_comparability") or {}).get("comparability") == "PIT_NORMALIZED"
        qualified=usable and fresh and raw_comparable
        kwargs=dict(ticker=context["ticker"],session=context["as_of_session"],source=source(context["artifact_identity"],version,"timeframes."+tf),
            axis="TECHNICAL",horizon=tf,basis={"price_basis":basis,"corporate_action_comparability":fitness.get("corporate_action_comparability")},freshness="CURRENT_SESSION" if tf=="1D" and fresh else "FRESH_COMPLETED_PERIOD" if fresh else "STALE",
            **_stage(context["ticker"],context["as_of_session"],context["artifact_identity"],basis,bindings,
                      context.get("evaluation_scope")=="REPLAY_DIAGNOSTIC" or version==dispatch.V1))
        lens_roles={c.LENSES[0]:"PRIMARY" if tf in {"1W","1M"} else "CONTEXT",c.LENSES[1]:"PRIMARY" if tf=="1D" else "CONTEXT"}
        for sub, mapping in (("trend_reading",{"UP":"SUPPORTS","DOWN":"OPPOSES","NO_CLEAN_AGREEMENT":"NEUTRAL","UNKNOWN":"UNKNOWN"}),
             ("swing_relation",{"HIGHER_HIGHS_HIGHER_LOWS":"SUPPORTS","LOWER_HIGHS_LOWER_LOWS":"OPPOSES",**{s:"NEUTRAL" for s in bridge.SWING_RELATIONS if s not in {"HIGHER_HIGHS_HIGHER_LOWS","LOWER_HIGHS_LOWER_LOWS","UNKNOWN","INSUFFICIENT_CONFIRMED_SWINGS"}},"UNKNOWN":"UNKNOWN","INSUFFICIENT_CONFIRMED_SWINGS":"UNKNOWN"}),
             ("setup_state",{s:("OPPOSES" if s in {"CONTINUING_DETERIORATION","BEARISH_STRUCTURE_BREAK","FAILED_BREAKOUT_DETERIORATION"} else "SUPPORTS" if s in {"CONFIRMED_IMPROVEMENT","ESTABLISHED_TREND"} else "UNKNOWN" if s=="UNKNOWN" else "NEUTRAL") for s in bridge.SETUP_STATES})):
            state=mapping[c.checked(concepts[sub],mapping,sub)] if qualified else "UNKNOWN"
            unknown="STALE" if not fresh else "AUTHORITY_LIMITED" if not raw_comparable else "UNQUALIFIED" if not usable else "UNRESOLVED"
            key=view["evidence_keys"][sub]
            items.append(c.make_item(**kwargs,sub_axis=sub,state=state,unknown_class=unknown,role="PRIMARY",lens_roles=lens_roles,
                fact_eligible=qualified,direction_eligible=qualified and state!="UNKNOWN",**key,
                correlation_group=key["common_cause_key"],reasons=view["unknown_reasons"],
                relations=[{"owner_contract":bridge.CONTRACT_VERSION,"source_identity":view["view_identity"],"pointer":"concepts."+sub,"state":concepts[sub]}]))
        # Geometry/morphology/volatility are context only. No copied raw series.
        for sub in ("patterns","volatility"):
            f=context["timeframes"][tf]["features"][sub]
            items.append(c.make_item(**kwargs,sub_axis=sub,state="NEUTRAL" if f["status"] in USABLE else "UNKNOWN",
                unknown_class="UNQUALIFIED",fact_eligible=f["status"] in USABLE,role="CONTEXT",reasons=f["reason_codes"],
                correlation_group=context["ticker"]+":"+tf+":"+sub))
        key=view["evidence_keys"]["native_volume_reference"]
        items.append(c.make_item(**{**kwargs,"axis":"VOLUME"},sub_axis="technical_native_volume_copy",role="CONTEXT",
            state="UNKNOWN",unknown_class="CONTEXT_ONLY",correlation_group=key["common_cause_key"],**key,
            reasons=["VOLUME_FLOW_OWNS_CANONICAL_PARTICIPATION","CORROBORATING_COPY_ONLY"]))
    return items


def adapt_flow_record(record):
    import volume_and_flow_context_v2 as flow
    from contextual_technical_primitives import USABLE
    flow.verify(record,"volume_flow_instrument/v2")
    items=[]
    owned_relations=set()
    for native in record["items"]:
        flow.verify(native,flow.ITEM_VERSION)
        c.checked(native["status"],FLOW_STATUSES,"flow_status")
        c.checked(native["participant"],REGISTRY["participants"],"participant")
        c.checked(native["sub_domain"],REGISTRY["flow_sub_domains"],"flow_sub_domain")
        c.checked(native["knowledge_stage"],c.STAGES,"flow_stage")
        c.checked(native["horizon"],("1D","1W","1M","1D/1","1D/5","1D/10","1D/20","1W/5","1W/20","1M/5","1M/20"),"flow_horizon")
        axis=c.checked(native["domain"],("VOLUME","PARTICIPANT_FLOW"),"flow_domain")
        if axis=="VOLUME":
            c.checked(native["participation_measure"],flow.PARTICIPATION_MEASURES,"participation_measure")
            c.checked(native["participation_state"],flow.PARTICIPATION_MEASURES[native["participation_measure"]],"participation_state")
        qualified=native["status"] in USABLE
        fresh=native["freshness"] in {"CURRENT_SESSION","FRESH_COMPLETED_PERIOD"}
        state, unknown="UNKNOWN","POLICY_NOT_AUTHORIZED"
        if native["participant"] and native["participant"]!="FOREIGN": unknown="UNQUALIFIED"
        elif axis=="PARTICIPANT_FLOW" and not native["coverage_scope"].get("in_cohort"): unknown="MISSING"
        elif not qualified: unknown="IMMATURE" if native["status"]=="INSUFFICIENT_HISTORY" else "UNQUALIFIED"
        elif not fresh: unknown="STALE"
        elif axis=="PARTICIPANT_FLOW" and (native.get("values") or {}).get("net_value_vnd")==0: state="NEUTRAL"
        elif axis=="VOLUME": state="NEUTRAL" # Facts/context have no approved thesis polarity.
        relations=[]
        if native.get("price_flow_relationship"):
            r=native["price_flow_relationship"]
            c.checked(r["method_contract"],("flow_price_divergence_shadow/v1",),"price_flow_owner")
            c.checked(r["state"],PRICE_FLOW,"price_flow_relationship")
            relations.append({"owner_contract":r["method_contract"],"source_identity":r["record_identity"],
                "pointer":"price_flow_relationship","state":r["state"],"fitness":r["evidence_quality"]})
        if native.get("technical_participation_relationship"):
            r=native["technical_participation_relationship"]
            c.checked(r["state"],flow.VOCABULARY_MANIFEST["relationship_state"],"technical_participation_relationship")
            relations.append({"owner_contract":"volume_and_flow_context/v2","source_identity":native["artifact_identity"],
                "pointer":"technical_participation_relationship","state":r["state"]})
        # Only small factual primitives, never own-history ranking or source payloads.
        allowed={"buy_value_vnd":"VND","sell_value_vnd":"VND","net_value_vnd":"VND","gross_value_vnd":"VND",
                 "relative_to_median":"DIMENSIONLESS","current_state_streak":"OBSERVATIONS"}
        if native["participant"]=="FOREIGN" and qualified:
            import math
            if native["unit_semantics"].get("native")!="VND" or any(not isinstance((native.get("values") or {}).get(k),(int,float))
                or isinstance(native["values"][k],bool) or not math.isfinite(native["values"][k]) for k in ("buy_value_vnd","sell_value_vnd","net_value_vnd","gross_value_vnd")):
                raise ValueError("THESIS_FOREIGN_FACT_UNIT_OR_VALUE_INVALID")
        facts=[fact(k,v,native["measure_semantics"],allowed[k],"values."+k,native["fitness"])
               for k,v in (native.get("values") or {}).items() if k in allowed and v is not None]
        key=native.get("evidence_keys") or {}
        # Both native and nested trajectory windows share the same common cause.
        cause=key.get("common_cause_key") or native["instrument"]["ticker"]+":"+axis+":"+str(native["participant"])
        items.append(c.make_item(ticker=native["instrument"]["ticker"],session=native["session"],
            source=source(native["artifact_identity"],flow.ITEM_VERSION,"records."+native["instrument"]["ticker"]+".items"),
            axis=axis,sub_axis=native["sub_domain"]+":"+str(native["participant"]),state=state,unknown_class=unknown,
            role="CONTEXT",horizon=native["horizon"],correlation_group=cause,**key,
            freshness=native["freshness"],basis=native["basis_fitness"],facts=facts,fact_eligible=qualified,
            reasons=native["reason_codes"],blockers=native["blockers"],relations=relations,
            coverage={"scope":native["coverage_scope"]["kind"],"in_cohort":native["coverage_scope"].get("in_cohort"),
                "actual_observations":native["actual_observations"],"required_observations":native["required_observations"],
                "is_market_representative":False}))
        r=native.get("price_flow_relationship")
        if r and r["record_identity"] not in owned_relations:
            owned_relations.add(r["record_identity"])
            known=r["evidence_quality"] in {"PARTIAL_RETAINED_EVIDENCE","COMPLETE_RETAINED_EVIDENCE"} and r["state"] not in {"PRICE_EVIDENCE_INSUFFICIENT","FLOW_UNAVAILABLE","RELATIONSHIP_NOT_EVALUABLE"}
            items.append(c.make_item(ticker=native["instrument"]["ticker"],session=native["session"],
                source=source(native["artifact_identity"],flow.ITEM_VERSION,"price_flow_relationship"),
                axis="PARTICIPANT_FLOW",sub_axis="owned_price_flow_relationship",state="NEUTRAL" if known else "UNKNOWN",
                unknown_class="UNQUALIFIED",fact_eligible=known,correlation_group=cause,relations=relations[:1],
                canonical_evidence_key=r["record_identity"],common_cause_key=cause,
                facts=[fact("relationship",r["state"],"SOURCE_OWNED_PRICE_FLOW_RELATIONSHIP","CATEGORY","price_flow_relationship.state",r["evidence_quality"])] if known else (),
                freshness=native["freshness"],basis=native["basis_fitness"],reasons=["EXISTING_RELATIONSHIP_OWNER_NO_RECOMPUTATION"] ))
    return items


def registers(row):
    """Reference existing conditions verbatim by pointer and content identity."""
    result={}
    paths={"thesis_confirmation":("thesis_confirmation",),"thesis_invalidation":("thesis_invalidation",),
           "setup_confirmation":("trigger.condition","trigger.watchlist_condition"),
           "setup_invalidation":("invalidation.condition","invalidation.watchlist_condition")}
    for name, candidates in paths.items():
        entries=[]
        for path in candidates:
            value=row
            for part in path.split("."): value=value.get(part) if isinstance(value,dict) else None
            if not value: continue
            c.checked(value.get("status"),REGISTRY["condition_status"],"condition_status")
            entries.append({"source_decision_identity":row["decision_identity"],"pointer":path,
                "condition_identity":value.get("condition_identity") or value.get("artifact_identity"),
                "source_contract":value.get("condition_version") or value.get("contract_version"),
                "source_status":value.get("status"),"source_operator":value.get("operator"),
                "state":"REFERENCED" if value.get("status") in {"MACHINE_EVALUABLE","READY"} else "UNKNOWN"})
        result[name]={"state":"REFERENCED" if any(e["state"]=="REFERENCED" for e in entries) else "UNKNOWN",
            "entries":entries,"reason_codes":[] if entries else ["EXISTING_PRODUCER_CONDITION_ABSENT"]}
    return result
