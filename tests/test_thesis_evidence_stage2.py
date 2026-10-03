"""Stage-2 compact sidecars, frozen semantics and production failure boundaries."""
import copy
import json
from pathlib import Path
import pytest
import thesis_evidence_production as engine
import thesis_evidence_contract as c
import thesis_evidence_adapters as adapters
import thesis_evidence_matrix as matrix
import prospective_t0_seal_index as seals
import prospective_decision_retention as retention
import integrated_investment_decision_product as product
import contextual_technical_features_v2 as technical
import technical_relationship_view as bridge
import volume_and_flow_context_v2 as flow
import thesis_production_runtime as runtime
from test_thesis_evidence_matrix import integrated_row
from test_contextual_technical_features import series,seal
from test_prospective_pit_capture import capture_session,DAY,TIME


def fixture(root,*,basis="RETROSPECTIVE_ADJUSTED",two=False):
    rows=series(45,basis=basis)
    rows[-1].update(period_start=DAY,period_end=DAY,first_trading_session=DAY,last_trading_session=DAY,
        constituent_sessions=[DAY],knowledge_available_at=DAY+"T09:00:00Z");seal(rows[-1])
    context=technical.build_context({"1D":rows},ticker="VNM",as_of_session=DAY,knowledge_cutoff=TIME)
    row=integrated_row();row.update(ticker="VNM",as_of_session=DAY)
    row["evidence_axes"]["MARKET_SECTOR"]["context"]["market_breadth"]["observation"]["session"]=DAY
    row["contextual_technical_context"]={"projection":context};row["decision_identity"]=product.decision_identity(row)
    records={"VNM":row}
    if two:
        extra=copy.deepcopy(row);extra.update(ticker="AAA");extra.pop("contextual_technical_context")
        extra["decision_identity"]=product.decision_identity(extra);records["AAA"]=extra
    iid={"contract_version":product.CONTRACT_VERSION,"session":DAY,"records":records,"requested_at":TIME}
    iid.update(product.content_identity(iid))
    decision_path=root/"iid.json";decision_path.write_bytes(c.canonical(iid).encode())
    snapshot=retention.build_snapshot(session=DAY,operation_identity="fixture:operation",producer_run_identity="fixture:run",integrated_artifact=iid)
    path=retention.write_immutable_snapshot(root,snapshot,on_written=lambda p,h:seals.from_snapshot(snapshot,p,created_at=TIME,file_sha256=h))
    index_path=path.parent/"prospective_t0_seal_index.json";index=json.loads(index_path.read_bytes())
    receipt=json.loads((path.parent/"prospective_t0_snapshot_write_receipt.json").read_bytes())
    ref={"path":str(index_path),"artifact_identity":index["artifact_identity"],"write_receipt_identity":receipt["artifact_identity"]}
    bound=seals.load_verified(ref,expected_snapshot_identity=snapshot["snapshot_identity"],session=DAY)
    f=flow.build_artifact(session=DAY,tickers=records,relationship_views={"VNM":bridge.build_views(context)},flow_series={},sealed_snapshot=bound)
    flow_path=root/"flow.json";flow_path.write_bytes(c.canonical(f).encode())
    return dict(root=root,output_root=root,session=DAY,decision_path=decision_path,flow_path=flow_path,
        index_ref=ref,snapshot_identity=snapshot["snapshot_identity"]),row,context,bound,path,f


def records(result,root):
    path=(root/result["path"]).parent/"views.ndjson"
    return {r["ticker"]:r for line in path.read_text(encoding="utf-8").splitlines() if (r:=json.loads(line))}


def test_generalized_binding_exact_and_no_snapshot_parse(tmp_path,monkeypatch):
    args,row,context,bound,path,_=fixture(tmp_path,two=True)
    original=Path.read_bytes
    monkeypatch.setattr(Path,"read_bytes",lambda p:(_ for _ in ()).throw(AssertionError("FULL_T0_READ")) if p==path else original(p))
    bound=seals.load_verified(args["index_ref"],expected_snapshot_identity=args["snapshot_identity"],session=DAY)
    assert bound.contains_integrated_decision("VNM",DAY,row["decision_identity"])
    assert not bound.contains_integrated_decision("VNM",DAY,"wrong")
    assert bound.contains_technical_context("VNM",DAY,technical.CONTRACT_VERSION,context["artifact_identity"])
    assert not bound.contains_technical_context("VNM",DAY,"contextual_technical_feature_set/v1",context["artifact_identity"])
    assert "AAA" in bound.records and "AAA" not in bound.bindings
    assert bound.index_identity==args["index_ref"]["artifact_identity"]
    result=engine.build(**args,stage="t0",origin="SEAL_TIME")
    assert result["built_count"]==2


@pytest.mark.parametrize("basis,t0_technical",[("RETROSPECTIVE_ADJUSTED",False),("PIT_CA_ADJUSTED",True)])
def test_exact_seal_does_not_override_stage_one_basis_policy(tmp_path,basis,t0_technical):
    args,row,context,bound,_,f=fixture(tmp_path,basis=basis)
    original=c.canonical(row)
    record,card,full=engine.compute("VNM",row,session=DAY,stage="current",technical=context,flow=f["records"]["VNM"],bindings=bound,sealed_row=row,origin="SEAL_TIME")
    natives=[i for i in full["items"] if i["axis"]=="TECHNICAL" and i["horizon"]=="1D"]
    assert bool(any(i["knowledge_stage"]=="T0_SEALED" for i in natives))==t0_technical
    assert all(i["knowledge_stage"]=="POST_T0_ENRICHED" for i in full["items"] if i["source"]["contract_version"]==flow.ITEM_VERSION)
    assert any(i["knowledge_stage"]=="T0_SEALED" and i["axis"]=="FUNDAMENTAL" for i in full["items"])
    if not t0_technical:
        assert record["t0_basis"]["lenses"][c.LENSES[1]]["state"]=="INSUFFICIENT_EVIDENCE"
        assert record["expected_retrospective_technical_exclusion"]
    assert record["lenses"]==card["lenses"] and original==c.canonical(row)
    assert card["offline_stage_1_card_identity"]==full["decision_card"]["artifact_identity"]
    assert "overall" not in c.canonical(card).lower() and not card["second_posture"]


def test_t0_compact_product_contains_no_post_and_retry_is_immutable(tmp_path):
    args,row,context,bound,path,f=fixture(tmp_path)
    result=engine.build(**args,stage="t0",origin="SEAL_TIME")
    record=records(result,tmp_path)["VNM"]
    assert record["post_items_in_t0"]==0 and record["learning_cohort_eligible"]
    before={p:p.read_bytes() for p in (tmp_path/result["path"]).parent.iterdir() if p.is_file()}
    retry=engine.build(**args,stage="t0",origin="LATE_REBUILD")
    assert retry["status"]=="ALREADY_RETAINED" and before=={p:p.read_bytes() for p in before}
    assert engine.verify_ticker(tmp_path/result["path"],root=tmp_path,ticker="VNM")["status"]=="PASS"


def test_late_rebuild_streams_original_and_is_excluded_from_learning(tmp_path,monkeypatch):
    args,_,_,_,path,_=fixture(tmp_path)
    monkeypatch.setattr(retention,"validate_snapshot",lambda *a:(_ for _ in ()).throw(AssertionError("WHOLE_SNAPSHOT_VALIDATION_FORBIDDEN")))
    result=engine.build(**args,stage="t0",snapshot_path=path,origin="LATE_REBUILD")
    record=records(result,tmp_path)["VNM"]
    assert record["origin"]=="LATE_REBUILD" and not record["learning_cohort_eligible"]
    assert result["performance"]["source_parse_passes"]["snapshot"]==1


def test_t0_unavailable_is_component_state_not_invented_lenses(tmp_path):
    result=engine.build(root=tmp_path,output_root=tmp_path,session=DAY,stage="t0")
    assert result["status"]=="UNAVAILABLE" and "lenses" not in result


def test_current_new_post_inputs_get_new_digest_and_t0_bytes_unchanged(tmp_path):
    args,row,_,_,path,f=fixture(tmp_path)
    t0=engine.build(**args,stage="t0",origin="SEAL_TIME")
    protected={p:p.read_bytes() for p in (tmp_path/t0["path"]).parent.iterdir() if p.is_file()};protected[path]=path.read_bytes()
    first=engine.build(**args,stage="current")
    f["source_artifact_identities"].append("fixture:later-post");f=flow.seal(f,flow.CONTRACT_VERSION)
    args["flow_path"].write_bytes(c.canonical(f).encode())
    second=engine.build(**args,stage="current")
    assert first["input_digest"]!=second["input_digest"] and first["path"]!=second["path"]
    assert protected=={p:p.read_bytes() for p in protected}
    assert all(a["class"] in engine.ANNOTATIONS for a in records(second,tmp_path)["VNM"]["post_t0_annotations"])


@pytest.mark.parametrize("failure",[ValueError,MemoryError])
def test_per_ticker_failure_isolated_and_no_fabricated_lens(tmp_path,monkeypatch,failure):
    args,*_=fixture(tmp_path,two=True);original=engine.compute
    def fail(t,*a,**k):
        if t=="VNM":raise failure("fixture computation unavailable")
        return original(t,*a,**k)
    monkeypatch.setattr(engine,"compute",fail)
    result=engine.build(**args,stage="current")
    assert result["component_status"]=="PARTIAL" and result["unavailable_count"]==1
    record=records(result,tmp_path)["VNM"]
    assert record["matrix_status"]=="UNAVAILABLE" and record["lenses"] is None and record["reason_class"]


def test_partial_publication_rebuild_and_complete_conflict(tmp_path):
    args,*_=fixture(tmp_path);result=engine.build(**args,stage="current")
    folder=(tmp_path/result["path"]).parent
    (folder/"COMPLETE.json").unlink();(folder/"views.ndjson").write_text('partial',encoding='utf-8')
    repaired=engine.build(**args,stage="current")
    assert repaired["component_status"]=="BUILT"
    (folder/"cards.ndjson").write_text('tampered',encoding='utf-8')
    with pytest.raises(ValueError,match="IMMUTABLE_CONFLICT"):engine.build(**args,stage="current")


@pytest.mark.parametrize("failure",[OSError,MemoryError])
def test_child_failure_does_not_change_capture_marker_or_t0(tmp_path,monkeypatch,failure):
    capture_session(tmp_path,calendar_days=[DAY,"2026-10-06"])
    args,_,_,_,path,_=fixture(tmp_path)
    marker=tmp_path/"operations-review/prospective-pit-capture-v1/first_complete_capture_session.json"
    import prospective_pit_capture_retention as captures
    marker=tmp_path/captures.STORE/"first_complete_capture_session.json"
    before={p:p.read_bytes() for p in (marker,path)}
    monkeypatch.setattr(runtime,"AUTOMATIC_HOOK_ENABLED",True)
    monkeypatch.setattr(runtime.subprocess,"run",lambda *a,**k:(_ for _ in ()).throw(failure("fixture child failure")))
    result=runtime.run_component(tmp_path,DAY,stage="t0",decision_path=args["decision_path"],
        snapshot_binding={"identity":args["snapshot_identity"],"seal_index":{"status":"RETAINED",**args["index_ref"]}})
    assert result["status"]=="UNAVAILABLE" and before=={p:p.read_bytes() for p in before}


def test_actual_child_is_offline_and_bounded_result(tmp_path,monkeypatch):
    args,*_=fixture(tmp_path);monkeypatch.setattr(runtime,"AUTOMATIC_HOOK_ENABLED",True)
    result=runtime.run_component(tmp_path,DAY,stage="t0",decision_path=args["decision_path"],snapshot_binding={
        "identity":args["snapshot_identity"],"seal_index":{"status":"RETAINED",**args["index_ref"]}})
    assert result["status"]=="COLLECTED",result
    assert result["network_provider_calls"]=={"network":0,"provider":0,"vnstock_import":0}
    assert result["performance"]["source_parse_passes"]=={"decision":1}


def test_separate_output_root_keeps_source_relative_handoff_reference(tmp_path,monkeypatch):
    args,*_=fixture(tmp_path);monkeypatch.setattr(runtime,"AUTOMATIC_HOOK_ENABLED",True)
    output=tmp_path/"output"
    result=runtime.run_component(tmp_path,DAY,stage="current",output_root=output,decision_path=args["decision_path"],flow_path=args["flow_path"],
        snapshot_binding={"identity":args["snapshot_identity"],"seal_index":{"status":"RETAINED",**args["index_ref"]}})
    assert result["status"]=="COLLECTED" and (tmp_path/result["path"]).is_file()
    assert (tmp_path/result["path"]).is_relative_to(output) and not Path(result["path"]).is_absolute()
    assert len(runtime.focus_cards(tmp_path,result,tickers=["VNM"]))==1


def test_unknown_never_action_and_independent_lenses(tmp_path):
    args,row,context,bound,_,f=fixture(tmp_path)
    record,card,full=engine.compute("VNM",row,session=DAY,stage="current",technical=context,flow=f["records"]["VNM"],bindings=bound,sealed_row=row)
    assert card["lenses"][c.LENSES[1]]["state"] in c.LENS_STATES
    assert all(p["state"] not in {"BUY","SELL","WAIT","HOLD","AVOID"} for p in card["lenses"].values())
    assert all(not i["fitness"]["direction_eligible"] for i in full["items"] if i["axis"] in {"VOLUME","PARTICIPANT_FLOW"})


def test_compact_handoff_dashboard_ai_share_exact_cards(tmp_path):
    import dashboard_session_companions as dashboard
    import ai_handoff_publication as ai
    args,*_=fixture(tmp_path)
    result=engine.build(**args,stage="current");result["status"]="COLLECTED"
    focus=runtime.focus_cards(tmp_path,result,tickers=["VNM"])
    assert len(focus)==1 and "conflict_kinds" in focus[0]["lenses"][c.LENSES[0]]
    block={"t0":{"status":"UNAVAILABLE"},"current":runtime.summary(result),"focus_cards":focus}
    assert str(tmp_path) not in json.dumps(block)
    payload=ai._presentation_observer_payload(DAY,{"thesis_evidence":block})
    assert payload["thesis_evidence"]==block
    html=dashboard._build_report_html({"dashboard_session":DAY,"thesis_evidence":block},build_id="fixture")
    for lens,p in focus[0]["lenses"].items():assert lens in html and p["state"] in html
    assert focus[0]["card_identity"] in html and focus[0]["matrix_identity"] in html
    assert "conflicts:" in html and "blockers:" in html
    bad={**result,"artifact_identity":"wrong"}
    assert runtime.focus_cards(tmp_path,bad,tickers=["VNM"])==[]


def test_monday_thesis_rows_are_independent_of_capture_success(tmp_path):
    import first_real_session_acceptance as harness
    from test_monday_live_readiness import governed
    args,_,_,bound,_,_=fixture(tmp_path)
    t0=engine.build(**args,stage="t0");current=engine.build(**args,stage="current")
    products={k:runtime.read_product_report(tmp_path/v["path"]) for k,v in (("t0",t0),("current",current))}
    base=dict(session=DAY,cutoff=TIME,calendar=governed(cutoff=TIME),capture_record={"capture_complete_tickers":["VNM"]},
        marker={"session":DAY},thesis_state={"stage_1":"COMPLETE","stage_1_offline":True,"stage_2":"COMPLETE"},sealed_bindings=bound)
    result=harness.evaluate(**base,thesis_products=products)
    rows={r["capability"]:r for r in result["rows"]}
    assert len(result["rows"])==41 and rows["thesis_t0_component"]["state"]=="OPEN"
    assert rows["thesis_t0_zero_post"]["state"]=="OPEN" and rows["thesis_t0_exact_snapshot_index_binding"]["state"]=="OPEN"
    assert rows["thesis_retrospective_technical_t0_exclusion"]["state"]=="OPEN"
    absent={r["capability"]:r for r in harness.evaluate(**base)["rows"]}
    assert absent["capture_session"]["state"]==absent["first_marker"]["state"]=="OPEN"
    assert absent["thesis_current_component"]["state"]=="NOT_EVALUABLE"
    with pytest.raises(ValueError,match="REFERENCE_MISMATCH"):
        runtime.read_product_report(tmp_path/t0["path"],expected_identity="wrong")


def test_later_integrated_source_uses_original_exact_t0_basis(tmp_path):
    args,row,_,_,_,_=fixture(tmp_path)
    original_path=args["decision_path"]
    iid=json.loads(original_path.read_bytes());new=copy.deepcopy(row)
    new["registers"]={"fixture":"later retained research"};new["decision_identity"]=product.decision_identity(new)
    iid["records"]["VNM"]=new;iid.update(product.content_identity(iid))
    later=tmp_path/"later-iid.json";later.write_bytes(c.canonical(iid).encode())
    result=engine.build(**{**args,"decision_path":later},stage="current",sealed_decision_path=original_path)
    record=records(result,tmp_path)["VNM"]
    assert record["decision_identity"]==new["decision_identity"] and record["t0_basis"]["availability"]=="AVAILABLE"
    t0=engine.build(**{**args,"decision_path":later},stage="t0",sealed_decision_path=original_path)
    assert records(t0,tmp_path)["VNM"]["decision_identity"]==row["decision_identity"]


def test_snapshot_index_mismatch_and_tamper_fail_closed(tmp_path):
    args,*_=fixture(tmp_path)
    with pytest.raises(ValueError):engine.build(**{**args,"snapshot_identity":"wrong"},stage="t0")
    path=Path(args["index_ref"]["path"]);value=json.loads(path.read_bytes())
    value["records"]["VNM"]["integrated_decision_identity"]="wrong";path.write_text(json.dumps(value))
    with pytest.raises(ValueError):engine.build(**args,stage="t0")


def test_concurrent_retry_cannot_replace_incomplete_writer(tmp_path):
    import sqlite3
    args,*_=fixture(tmp_path);result=engine.build(**args,stage="current")
    folder=(tmp_path/result["path"]).parent;(folder/"COMPLETE.json").unlink()
    before=(folder/"views.ndjson").read_bytes()
    with sqlite3.connect(str(folder/".writer.sqlite")) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        with pytest.raises(sqlite3.OperationalError):engine.build(**args,stage="current")
    assert (folder/"views.ndjson").read_bytes()==before
    assert engine.build(**args,stage="current")["component_status"]=="BUILT"


def test_production_sequence_places_thesis_after_marker_and_flow_before_feedback():
    root=Path(__file__).resolve().parents[1]
    daily=(root/"canonical_daily_operation.py").read_text(encoding="utf-8")
    portion=daily[daily.index("capture_retention.daily_boundary"):]
    assert portion.index("run_thesis_t0_sidecar")<portion.index("build_tiered_bundle")
    pipeline=(root/"canonical_post_close_pipeline.py").read_text(encoding="utf-8")
    portion=pipeline[pipeline.index("def run_post_handoff_observers"):pipeline.index("def run_thesis_t0_sidecar")]
    assert portion.index("volume_flow_context = run_volume_and_flow_context")<portion.index('stage="current"')


def test_real_child_nonzero_exit_is_bounded_unavailable_and_never_insufficient(tmp_path,monkeypatch):
    args,*_=fixture(tmp_path);monkeypatch.setattr(runtime,"AUTOMATIC_HOOK_ENABLED",True)
    bad=tmp_path/"corrupt.json";bad.write_text("{"+"x"*200000,encoding="utf-8")
    result=runtime.run_component(tmp_path,DAY,stage="current",decision_path=bad,snapshot_binding={
        "identity":args["snapshot_identity"],"seal_index":{"status":"RETAINED",**args["index_ref"]}})
    assert result["status"]=="UNAVAILABLE" and result["reason"].startswith("THESIS_CHILD_FAILED:")
    assert len(json.dumps(result))<4096 and "INSUFFICIENT_EVIDENCE" not in json.dumps(result)


def test_component_wide_exception_in_both_hooks_is_component_local(tmp_path,monkeypatch):
    import canonical_post_close_pipeline as pipeline
    monkeypatch.setattr(runtime,"AUTOMATIC_HOOK_ENABLED",True)
    result=pipeline.run_thesis_t0_sidecar(tmp_path,DAY,object(),None)
    assert result["status"]=="UNAVAILABLE" and result["reason"].startswith("THESIS_T0_COMPONENT_FAILED:")
    monkeypatch.setattr(runtime,"run_component",lambda *a,**k:(_ for _ in ()).throw(MemoryError("fixture")))
    result=pipeline.run_thesis_t0_sidecar(tmp_path,DAY,{"artifact":{}},{})
    assert result["status"]=="UNAVAILABLE" and "MemoryError" in result["reason"]


def test_hook_disabled_disposition_is_explicit_unavailable_not_computed(tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,"AUTOMATIC_HOOK_ENABLED",False)
    result=runtime.run_component(tmp_path,DAY,stage="current",decision_path=tmp_path/"absent.json")
    assert result["status"]=="UNAVAILABLE" and result["reason"]=="AUTOMATIC_THESIS_HOOK_DISABLED_FAIL_SOFT"


def test_missing_seal_index_never_upgrades_current_evidence_and_flow_absence_is_partial(tmp_path):
    args,*_=fixture(tmp_path)
    no_index={k:v for k,v in args.items() if k not in {"index_ref","snapshot_identity","flow_path"}}
    result=engine.build(**no_index,stage="current")
    record=records(result,tmp_path)["VNM"]
    assert record["matrix_status"]=="PARTIAL" and result["component_status"]=="PARTIAL"
    assert record["t0_basis"]["availability"]!="AVAILABLE" and record["seal_index_identity"] is None
    assert all(not n.endswith("/T0_SEALED") for n in record["stage_coverage_by_axis"])
    assert not record["learning_cohort_eligible"] and record["second_posture"] is False


def test_stale_pending_files_from_killed_writer_do_not_block_or_leak_into_product(tmp_path):
    args,*_=fixture(tmp_path);first=engine.build(**args,stage="current")
    folder=(tmp_path/first["path"]).parent;(folder/"COMPLETE.json").unlink()
    (folder/".pending-stale-views").write_text("partial",encoding="utf-8")
    repaired=engine.build(**args,stage="current")
    assert repaired["component_status"]=="BUILT" and repaired["status"]!="ALREADY_RETAINED"
    assert engine.verify_complete(folder)["files"].keys()=={"views.ndjson","cards.ndjson"}


def test_child_retry_reports_already_retained_without_losing_collected_state(tmp_path,monkeypatch):
    args,*_=fixture(tmp_path);monkeypatch.setattr(runtime,"AUTOMATIC_HOOK_ENABLED",True)
    kwargs=dict(decision_path=args["decision_path"],snapshot_binding={"identity":args["snapshot_identity"],"seal_index":{"status":"RETAINED",**args["index_ref"]}})
    first=runtime.run_component(tmp_path,DAY,stage="t0",**kwargs);second=runtime.run_component(tmp_path,DAY,stage="t0",**kwargs)
    assert first["status"]==second["status"]=="COLLECTED" and second["retention"]=="ALREADY_RETAINED" and "retention" not in first
    assert first["artifact_identity"]==second["artifact_identity"] and runtime.summary(second)["retention"]=="ALREADY_RETAINED"
