"""Offline contracts, source vocabulary, semantic reducers and adversarial boundaries."""
import ast
import copy
from pathlib import Path
import pytest
import stocklookup_core.research.thesis_evidence_contract as c
import stocklookup_core.research.thesis_evidence_adapters as a
import stocklookup_core.research.thesis_evidence_matrix as m
import stocklookup_core.decision.integrated_investment_decision_product as product

LONG,SHORT=c.LENSES
REF={"decision_identity":"decision:FPT:one","research_action_posture":"WAIT_FOR_CONFIRMATION"}


def item(state="SUPPORTS",axis="TECHNICAL",sub="trend",role="PRIMARY",cause=None,tf="1D",**changes):
    args=dict(ticker="FPT",session="2026-10-02",source=a.source("source:"+sub,"test_source/v1",sub),axis=axis,
        sub_axis=sub,state=state,unknown_class="UNRESOLVED",role=role,horizon=tf,
        correlation_group=cause or axis+":"+sub,freshness="CURRENT_SESSION",
        fact_eligible=state not in {"UNKNOWN","NOT_APPLICABLE"},direction_eligible=role!="CONTEXT" and state not in {"UNKNOWN","NOT_APPLICABLE"})
    args.update(changes)
    return c.make_item(**args)


def matrix(items,**kw):
    return m.build_matrix(ticker="FPT",session="2026-10-02",items=items,decision_reference=REF,**kw)


@pytest.mark.parametrize("state",c.STATES)
def test_all_evidence_states(state):
    i=item(state)
    assert c.verify_item(i)["state"]==state
    result=matrix([i]);m.verify_matrix(result)
    assert not result["is_actionable"]


@pytest.mark.parametrize("unknown",c.UNKNOWN_CLASSES)
def test_all_unknown_classes_never_oppose(unknown):
    i=item("UNKNOWN",unknown_class=unknown)
    result=matrix([i])["views"]["CURRENT_RESEARCH_VIEW"]["lenses"][SHORT]
    assert result["axes"]["TECHNICAL"]["state"]=="UNKNOWN"
    assert not result["counter_thesis"]["opposing_evidence"]
    assert not result["conflicts"]


@pytest.mark.parametrize("key",["score","confidence","probability","rank","rating","conviction","target",
    "weight","priority_score","overall","overall_rating","signalStrength","forecast_return","weightedMean",
    "certainty","likelihood","targetPrice","confidence_interval","ratingStars"])
def test_recursive_forbidden_aliases(key):
    with pytest.raises(ValueError,match="FORBIDDEN"): c.scan_forbidden({"nested":[{key:1}]})


def test_numbers_need_fact_metadata_and_finite_values():
    with pytest.raises(ValueError,match="FACT_METADATA"): item(facts=[{"value":100}])
    with pytest.raises(ValueError,match="NON_FINITE"): item(facts=[a.fact("close",float("nan"),"PRICE","VND","close")])
    assert item(facts=[a.fact("close",100,"PRICE","VND","close")])["facts_present"]
    with pytest.raises(ValueError,match="FORBIDDEN"):item(facts=[a.fact("confidence",0.9,"RESEARCH","DIMENSIONLESS","source")])


@pytest.mark.parametrize("states,expected",[( ["SUPPORTS"],"SUPPORTS"),(["OPPOSES"],"OPPOSES"),
    (["SUPPORTS","OPPOSES"],"MIXED"),(["SUPPORTS","NEUTRAL"],"SUPPORTS"),
    (["OPPOSES","NEUTRAL"],"OPPOSES"),(["NEUTRAL"],"NEUTRAL"),(["MIXED","SUPPORTS"],"MIXED"),
    (["NOT_APPLICABLE"],"NOT_APPLICABLE"),(["UNKNOWN","SUPPORTS"],"SUPPORTS")])
def test_axis_rules(states,expected):
    groups=m.semantic_groups([item(s,sub=str(n)) for n,s in enumerate(states)],SHORT)
    assert m.reduce_axis(groups,"TECHNICAL")["state"]==expected


@pytest.mark.parametrize("role,reason",[("SECONDARY","PRIMARY_EVIDENCE_MISSING"),("CONTEXT","CONTEXT_ONLY")])
def test_no_primary(role,reason):
    groups=m.semantic_groups([item(role=role)],SHORT)
    result=m.reduce_axis(groups,"TECHNICAL")
    assert result["state"]=="UNKNOWN" and result["unknown_class"]==reason


def test_nested_windows_group_without_hidden_priority_and_order_invariance():
    one=item("SUPPORTS",sub="5",tf="1D/5",cause="same")
    two=item("OPPOSES",sub="20",tf="1D/20",cause="same")
    group=m.semantic_groups([one,two],SHORT)
    assert len(group)==1 and group[0]["state"]=="MIXED"
    assert group[0]["representative_policy"]=="SEMANTIC_GROUP_NO_MEMBER_PRECEDENCE"
    assert matrix([one,two])==matrix([two,one,one,two])


def test_input_duplication_invariant_even_neutral_and_unknown():
    inputs=[item(),item("NEUTRAL",sub="range"),item("UNKNOWN",sub="missing")]
    assert matrix(inputs)==matrix(inputs*10)


def test_long_supportive_short_not_confirmed_is_normal_horizon_separation():
    inputs=[item(axis="FUNDAMENTAL",lens_roles={LONG:"PRIMARY",SHORT:"CONTEXT"}),
        item(axis="VALUATION",lens_roles={LONG:"PRIMARY",SHORT:"CONTEXT"}),
        item(tf="1W",sub="weekly",lens_roles={LONG:"PRIMARY",SHORT:"CONTEXT"}),
        item("NEUTRAL",tf="1D",sub="daily",lens_roles={LONG:"CONTEXT",SHORT:"PRIMARY"})]
    result=matrix(inputs)["views"]["CURRENT_RESEARCH_VIEW"]["lenses"]
    assert result[LONG]["lens"]["state"]=="SUPPORTIVE"
    assert result[SHORT]["lens"]["state"]=="NOT_CONFIRMED"
    assert not result[LONG]["conflicts"] and not result[SHORT]["conflicts"]


@pytest.mark.parametrize("anchor,other,expected",[("UNKNOWN","SUPPORTS","INSUFFICIENT_EVIDENCE"),
    ("SUPPORTS","OPPOSES","CONTESTED"),("OPPOSES","NEUTRAL","ADVERSE"),("SUPPORTS","UNKNOWN","NOT_CONFIRMED"),
    ("SUPPORTS","SUPPORTS","SUPPORTIVE"),("MIXED","NEUTRAL","CONTESTED")])
def test_long_lens_states(anchor,other,expected):
    axes={axis:{"state":"NEUTRAL"} for axis in c.AXES}
    axes["FUNDAMENTAL"]["state"]=anchor;axes["TECHNICAL"]["state"]=other
    assert m.reduce_lens(axes,LONG)["state"]==expected


def test_genuine_seal_and_post_stage_isolation():
    from test_prospective_decision_retention import _snapshot
    snapshot=_snapshot("2026-10-02",100)
    bindings=c.SealedEvidenceBindings(snapshot)
    sealed=item(axis="FUNDAMENTAL",source=a.source("decision:FPT:one",product.CONTRACT_VERSION,"evidence_axes.FUNDAMENTAL"),
        stage="T0_SEALED",seal_reference=bindings.identity)
    before=matrix([sealed],sealed_bindings=bindings)
    after=matrix([sealed,item("OPPOSES",axis="FUNDAMENTAL",sub="post")],sealed_bindings=bindings)
    assert before["views"]["T0_THESIS_VIEW"]==after["views"]["T0_THESIS_VIEW"]
    with pytest.raises(ValueError,match="GENUINE_T0"): matrix([sealed])
    wrong=c.seal({**sealed,"source":a.source("wrong",product.CONTRACT_VERSION,"axis")},c.ITEM_VERSION)
    with pytest.raises(ValueError,match="NOT_SEALED"): matrix([wrong],sealed_bindings=bindings)


def test_retro_never_enters_t0_and_stale_direction_rejected():
    with pytest.raises(ValueError,match="T0_SEAL_OR_BASIS"): item(stage="T0_SEALED",seal_reference="fake",basis="RETROSPECTIVE_ADJUSTED")
    with pytest.raises(ValueError,match="DIRECTION_FITNESS"): item(freshness="STALE")
    with pytest.raises(ValueError,match="RAW_DIRECTION"): item(basis="RAW_AS_TRADED")


@pytest.mark.parametrize("axis,sub",[("VOLUME","native"),("PARTICIPANT_FLOW","foreign"),("TECHNICAL","patterns"),("TECHNICAL","volatility")])
def test_context_never_direction(axis,sub):
    with pytest.raises(ValueError): item(axis=axis,sub=sub)


@pytest.mark.parametrize("version",[1,2])
def test_actual_technical_v1_v2_dispatch(version):
    from test_technical_volume_flow_v2 import context
    import contextual_technical_features as v1
    import contextual_technical_features_v2 as v2
    inputs=context(v1 if version==1 else v2)
    records=a.adapt_technical(inputs)
    assert len(records)==18 and all(i["knowledge_stage"]=="POST_T0_ENRICHED" for i in records)
    assert all(not i["fitness"]["direction_eligible"] for i in records if i["sub_axis"] in {"patterns","volatility","technical_native_volume_copy"})
    bad=copy.deepcopy(inputs);bad["contract_version"]="future/v9"
    with pytest.raises(ValueError): a.adapt_technical(bad)


@pytest.mark.parametrize("net,state,unknown",[(0,"NEUTRAL",None),(100,"UNKNOWN","POLICY_NOT_AUTHORIZED"),(-100,"UNKNOWN","POLICY_NOT_AUTHORIZED")])
def test_actual_foreign_fact_only(net,state,unknown):
    from test_volume_and_flow_context import foreign
    import volume_and_flow_context_v2 as flow
    series,dates=foreign(5,[net]*5)
    items=flow.foreign_items("VNM","2026-10-02",series,in_cohort=True,exhaustive_dates=dates)
    native=flow.seal({"items":items},"volume_flow_instrument/v2")
    result=a.adapt_flow_record(native)
    one=next(i for i in result if i["horizon"]=="1D/1")
    assert one["state"]==state and one["unknown_class"]==unknown and one["facts_present"]
    assert all(not i["fitness"]["direction_eligible"] for i in result)
    assert next(i for i in result if i["horizon"]=="1D/20")["unknown_class"]=="IMMATURE"


def test_registry_matches_current_main_closed_vocabularies():
    import stocklookup_core.financial.fundamental_signal_consumption_contract as fundamental
    import tactical_confirmation_context as confirmation
    import technical_relationship_view as bridge
    assert set(a.FUNDAMENTAL)==set(product.FUNDAMENTAL_STATES)
    assert set(a.AVAILABILITY)==set(fundamental.EVIDENCE_AVAILABILITY_STATES)
    assert set(a.LEGACY_PARTICIPATION)==set(confirmation._CONFIRMATION_STATES)
    assert set(bridge.TREND_READINGS)=={"UP","DOWN","NO_CLEAN_AGREEMENT","UNKNOWN"}
    assert a.REGISTRY["participant_policy"]=="FACTS_ONLY"


def test_missing_registers_and_exact_condition_references():
    from test_prospective_decision_retention import _decision
    row=_decision("2026-10-02")
    registers=a.registers(row)
    assert registers["thesis_confirmation"]["state"]=="UNKNOWN"
    assert registers["setup_confirmation"]["entries"][0]["condition_identity"]==row["trigger"]["condition"]["condition_identity"]
    result=matrix([] ,registers=registers)
    assert set(result["decision_card"]["registers"])=={"thesis_confirmation","setup_confirmation","thesis_invalidation","setup_invalidation","evidence_staleness"}
    assert result["decision_card"]["ACTION SUPPORT REFERENCE"]=={**REF,"second_posture":False}


def test_no_production_import_of_offline_stage_1():
    root=Path(__file__).resolve().parents[1]
    for path in root.glob("*.py"):
        if path.name.startswith("thesis_evidence_"): continue
        tree=ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            names=[alias.name for alias in node.names] if isinstance(node,ast.Import) else [node.module or ""] if isinstance(node,ast.ImportFrom) else []
            assert not any(name.startswith("thesis_evidence_") for name in names),path.name
            if isinstance(node,ast.Constant) and isinstance(node.value,str):
                assert not node.value.startswith("thesis_evidence_"),path.name


def test_verifier_detects_tampered_lens_even_if_outer_hash_resealed():
    result=matrix([item()]);result["views"]["CURRENT_RESEARCH_VIEW"]["lenses"][SHORT]["lens"]["state"]="ADVERSE"
    result["decision_card"]=c.seal(result["decision_card"],m.CARD_VERSION)
    result=c.seal(result,m.CONTRACT_VERSION)
    with pytest.raises(ValueError,match="DERIVED_PROJECTION"): m.verify_matrix(result)


@pytest.mark.parametrize("kind",m.ACTIVE_CONFLICTS)
def test_all_active_conflict_predicates(kind):
    inputs=[];lens=LONG
    if kind=="TECHNICAL_INTRA_TIMEFRAME_CONFLICT": inputs=[item(cause="same"),item("OPPOSES",sub="event",cause="same")]
    elif kind=="TECHNICAL_TIMEFRAME_DIVERGENCE": inputs=[item(tf="1W"),item("OPPOSES",tf="1M",sub="monthly")]
    elif kind in {"TECHNICAL_FUNDAMENTAL_DIVERGENCE","FUNDAMENTAL_VALUATION_DIVERGENCE","MACRO_SECTOR_DIVERGENCE"}:
        left,right={"TECHNICAL_FUNDAMENTAL_DIVERGENCE":("TECHNICAL","FUNDAMENTAL"),"FUNDAMENTAL_VALUATION_DIVERGENCE":("FUNDAMENTAL","VALUATION"),"MACRO_SECTOR_DIVERGENCE":("TECHNICAL","MACRO_SECTOR")}[kind]
        inputs=[item(axis=left),item("OPPOSES",axis=right)];lens=SHORT if right=="MACRO_SECTOR" else LONG
    elif kind=="PRICE_FLOW_DIVERGENCE": inputs=[item("NEUTRAL",axis="PARTICIPANT_FLOW",role="CONTEXT",relations=[{"owner_contract":"flow_price_divergence_shadow/v1","source_identity":"relation:1","fitness":"COMPLETE_RETAINED_EVIDENCE","state":"FOREIGN_BUYING_PRICE_WEAKNESS"}])]
    elif kind=="TIME_HORIZON_MISMATCH": inputs=[item(tf="1D")]
    elif kind=="AUTHORITY_MISMATCH": inputs=[item(relations=[{"requested_view":"T0_THESIS_VIEW"}])]
    elif kind=="PORTFOLIO_FIT_THESIS_MISMATCH": inputs=[item(axis="FUNDAMENTAL"),item("NEUTRAL",axis="LIQUIDITY_PORTFOLIO",role="CONTEXT",relations=[{"state":"PORTFOLIO_CONSTRAINT_VIOLATED"}])]
    elif kind=="EVIDENCE_FRESHNESS_MISMATCH": inputs=[item("NEUTRAL",role="CONTEXT",canonical_evidence_key="same"),item("NEUTRAL",role="CONTEXT",sub="old",canonical_evidence_key="same",freshness="STALE")]
    groups=m.semantic_groups(inputs,lens);axes={axis:m.reduce_axis(groups,axis) for axis in c.AXES}
    events=m.conflicts(inputs,groups,axes,lens)
    assert kind in {e["kind"] for e in events}
    assert not set(m.DORMANT_CONFLICTS)&{e["kind"] for e in events}


def test_unknown_relations_never_fire_conflicts():
    inputs=[item("UNKNOWN",relations=[{"requested_view":"T0_THESIS_VIEW"},{"state":"PORTFOLIO_CONSTRAINT_VIOLATED"}])]
    assert not matrix(inputs)["views"]["CURRENT_RESEARCH_VIEW"]["lenses"][LONG]["conflicts"]


def test_second_posture_and_extra_item_fields_rejected():
    extra=c.seal({**item(),"merit":9},c.ITEM_VERSION)
    with pytest.raises(ValueError,match="SCHEMA_UNSUPPORTED"):c.verify_item(extra)
    with pytest.raises(ValueError,match="ACTION_REFERENCE_SCOPE"):m.build_matrix(ticker="FPT",session="2026-10-02",items=[],decision_reference={**REF,"second_posture":True})


def integrated_row():
    row={"ticker":"FPT","as_of_session":"2026-10-02","research_action_posture":"WAIT_FOR_CONFIRMATION",
        "evidence_currency":"CURRENT_SESSION","fundamental_evidence_availability":"CURRENT_DIRECTIONAL",
        "evidence_axes":{
            "FUNDAMENTAL":{"state":"IMPROVING","fitness":"AVAILABLE","method":a.METHODS["FUNDAMENTAL"][0],"context":{"fundamental_evidence_availability":"CURRENT_DIRECTIONAL"}},
            "VALUATION":{"state":"AVAILABLE","fitness":"AVAILABLE","method":a.METHODS["VALUATION"][0],"context":{"peer_relative_state":"CHEAP_VS_PEERS"}},
            "MARKET_SECTOR":{"state":"BROAD_PARTICIPATION","fitness":"AVAILABLE","method":a.METHODS["MARKET_SECTOR"][0],"context":{"market_regime":"BROAD_PARTICIPATION","sector_leadership":"LEADING","sector_leadership_status":"AVAILABLE","market_breadth":{"observation":{"session":"2026-10-02","exact_session_observed_count":10}}}},
            "PARTICIPATION_CONFIRMATION":{"state":"CONFIRMED","method":a.METHODS["PARTICIPATION_CONFIRMATION"][0]},
            "CORPORATE_INTELLIGENCE":{"state":"NO_QUALIFIED_CORPORATE_EVENT","fitness":"NO_QUALIFIED_CORPORATE_EVENT","method":a.METHODS["CORPORATE_INTELLIGENCE"][0]}}}
    row["decision_identity"]=product.decision_identity(row)
    return row


@pytest.mark.parametrize("raw,expected",list(a.FUNDAMENTAL.items()))
def test_integrated_fundamental_mapping(raw,expected):
    row=integrated_row();row["evidence_axes"]["FUNDAMENTAL"]["state"]=raw;row["decision_identity"]=product.decision_identity(row)
    result=next(i for i in a.adapt_integrated(row) if i["axis"]=="FUNDAMENTAL")
    assert result["state"]==expected
    assert result["lens_binding"]=={LONG:"PRIMARY",SHORT:"CONTEXT"}


@pytest.mark.parametrize("availability,reason",[("STALE_ONLY","STALE"),("CURRENT_NON_DIRECTIONAL","UNRESOLVED"),("ABSENT","MISSING")])
def test_fundamental_availability_gates(availability,reason):
    row=integrated_row();row["evidence_axes"]["FUNDAMENTAL"]["context"]["fundamental_evidence_availability"]=availability
    result=next(i for i in a.adapt_integrated(row) if i["axis"]=="FUNDAMENTAL")
    assert result["state"]=="UNKNOWN" and result["unknown_class"]==reason


@pytest.mark.parametrize("state,expected",list(a.PEER.items()))
def test_peer_mapping_uses_exact_producer_read(state,expected):
    row=integrated_row();row["evidence_axes"]["VALUATION"]["context"]["peer_relative_state"]=state
    assert next(i for i in a.adapt_integrated(row) if i["axis"]=="VALUATION")["state"]==expected


@pytest.mark.parametrize("state",a.LEGACY_PARTICIPATION)
def test_legacy_participation_never_adds_vote(state):
    row=integrated_row();row["evidence_axes"]["PARTICIPATION_CONFIRMATION"]["state"]=state
    result=next(i for i in a.adapt_integrated(row) if i["sub_axis"]=="legacy_participation_context")
    assert result["role"]=="CONTEXT" and not result["fitness"]["direction_eligible"]


def test_future_unmapped_source_vocabulary_rejected():
    row=integrated_row();row["evidence_axes"]["FUNDAMENTAL"]["state"]="NEW_VALUE"
    with pytest.raises(ValueError,match="UNMAPPED"): a.adapt_integrated(row)


def test_exact_future_integrated_seal_is_readable_and_missing_seal_demotes():
    import prospective_decision_retention as retention
    from test_prospective_decision_retention import _price_snapshot
    row=integrated_row()
    package={"contract_version":product.CONTRACT_VERSION,"session":"2026-10-02","records":{"FPT":row},"artifact_identity":"fixture:integrated"}
    snapshot=retention.build_snapshot(session="2026-10-02",operation_identity="fixture:operation",producer_run_identity="fixture:run",
        integrated_artifact=package,exact_session_snapshot=_price_snapshot("2026-10-02",100))
    bindings=c.SealedEvidenceBindings(snapshot)
    sealed=a.adapt_integrated(row,bindings=bindings)
    assert all(i["knowledge_stage"]=="T0_SEALED" for i in sealed)
    assert all(i["knowledge_stage"]=="POST_T0_ENRICHED" for i in a.adapt_integrated(row))


def test_qualified_owned_price_flow_annotation_can_conflict_without_directional_flow():
    from test_volume_and_flow_context import foreign
    import volume_and_flow_context_v2 as flow
    series,dates=foreign(5,[10]*5)
    for observation in series["observations"]: observation["ticker"]="FPT"
    natives=flow.foreign_items("FPT","2026-10-02",series,in_cohort=True,exhaustive_dates=dates)
    for native in natives:
        native["price_flow_relationship"].update(state="FOREIGN_BUYING_PRICE_WEAKNESS",evidence_quality="COMPLETE_RETAINED_EVIDENCE")
        native.update(flow.seal(native,flow.ITEM_VERSION))
    records=a.adapt_flow_record(flow.seal({"items":natives},"volume_flow_instrument/v2"))
    assert all(not i["fitness"]["direction_eligible"] for i in records)
    assert next(i for i in records if i["sub_axis"]=="FOREIGN_VALUE:FOREIGN" and i["horizon"]=="1D/1")["state"]=="UNKNOWN"
    assert "PRICE_FLOW_DIVERGENCE" in {e["kind"] for e in matrix(records)["views"]["CURRENT_RESEARCH_VIEW"]["lenses"][SHORT]["conflicts"]}
