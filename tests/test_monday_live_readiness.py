"""Corrective boundaries under synthetic evidence, never real authority roots."""
import copy
import json
from pathlib import Path
import pytest
import governed_session_chain as calendar
import prospective_pit_capture_retention as store
import prospective_pit_capture as capture
import prospective_decision_retention as retention
import prospective_t0_seal_index as index
import canonical_market_bars as bars
import dnse_foreign_flow_store as foreign
import volume_and_flow_context_v2 as flow
import technical_relationship_view as bridge
import first_real_session_acceptance as harness
from test_prospective_pit_capture import capture_session, calendar as receipt, DAY, TIME
from test_canonical_market_bars import daily
from test_technical_volume_flow_v2 import context
from test_prospective_decision_retention import _decision


def governed(days=None, *, cutoff="2026-10-12T12:00:00Z", known="2026-10-02T04:00:00Z"):
    return calendar.governed_calendar_evidence_at_cutoff(receipts=[receipt(days or ["2026-10-02","2026-10-05","2026-10-06","2026-10-07","2026-10-08","2026-10-09","2026-10-12"],known=known)],cutoff=cutoff)


def test_segments_never_stitch_september_and_cutoff_excludes_later_receipt():
    static=json.loads((Path(__file__).resolve().parents[1]/"config/governed_trading_session_calendar_v1.json").read_text())
    c=calendar.governed_calendar_evidence_at_cutoff(static,[receipt(["2026-10-02","2026-10-05","2026-10-12"],known="2026-10-02T04:00:00Z")],cutoff=TIME)
    assert len(c["segments"])==2 and c["unsupported_gaps"]==[{"after":"2026-09-04","before":"2026-10-02","state":"UNSUPPORTED_CALENDAR_GAP"}]
    for day,tf in (("2026-09-30","1M"),("2026-09-28","1W")):
        bar=bars.derive([daily("2026-10-02")],ticker="VNM",timeframe=tf,period_session=day,knowledge_cutoff=TIME,source_identity="fixture",calendar_evidence=c)
        assert bar["period_completeness"]=="CALENDAR_SCOPE_UNKNOWN"
    earlier=governed(cutoff="2026-10-02T03:00:00Z")
    assert not earlier["sessions"]
    assert calendar.governed_calendar_evidence_at_cutoff(receipts=[receipt([DAY,"2026-10-06"])],cutoff=TIME,scope="HOSE")["status"]=="UNAVAILABLE"


def test_future_week_complete_only_after_final_governed_session_and_all_rows_known():
    days=[DAY,"2026-10-06","2026-10-07","2026-10-08","2026-10-09"]
    rows=[daily(d,retrieved_at=d+"T09:00:00Z") for d in days]
    def project(cutoff,observations=rows):
        return bars.derive(observations,ticker="VNM",timeframe="1W",period_session=DAY,knowledge_cutoff=cutoff,source_identity="fixture",calendar_evidence=governed(cutoff=cutoff))
    assert project("2026-10-09T09:00:00Z")["period_completeness"]=="COMPLETE"
    assert project("2026-10-09T08:00:00Z")["period_completeness"]=="PARTIAL_CURRENT_PERIOD"
    assert project("2026-10-12T12:00:00Z",rows[:-1])["period_completeness"]=="INCOMPLETE_SESSION_COVERAGE"


def test_overlap_disagreement_blocks_continuity_without_hiding_source_revision():
    a=receipt(["2026-10-02",DAY,"2026-10-06"],known="2026-10-02T04:00:00Z")
    b=receipt(["2026-10-02","2026-10-06"],known="2026-10-02T05:00:00Z")
    c=calendar.governed_calendar_evidence_at_cutoff(receipts=[a,b],cutoff=TIME)
    assert c["overlap_disagreements"]
    assert calendar.are_consecutive_governed_sessions("2026-10-02",DAY,TIME,c)["state"]=="UNKNOWN"


@pytest.mark.parametrize("supplied,expected",[(True,"TRUE"),(False,"UNKNOWN")])
def test_friday_monday_governed_proof_only(supplied,expected):
    assert calendar.are_consecutive_governed_sessions("2026-10-02",DAY,TIME,governed(cutoff=TIME) if supplied else None)["state"]==expected
    proof=foreign._prove_continuity(["2026-10-02",DAY],exhaustive_dates={"2026-10-02",DAY},registry_dates=frozenset({"2026-10-02",DAY}),calendar_evidence=governed(cutoff=TIME) if supplied else None)
    assert proof["proof_state"]==("PROVEN_CONTINUOUS" if supplied else "UNVERIFIABLE")


def test_five_foreign_sessions_preserve_values_with_exact_overlap_and_fail_without_it():
    days=["2026-09-29","2026-09-30","2026-10-01","2026-10-02",DAY]
    c=governed(days,cutoff=TIME,known="2026-09-29T04:00:00Z")
    observations=[foreign._value_observation({"ticker":"VNM","session_date":d,"source":"DNSE","source_contract_version":foreign.SOURCE_CONTRACT_VERSION,"foreign_buy_value":110,"foreign_sell_value":100}) for d in days]
    source=copy.deepcopy(observations)
    for evidence,expected in ((c,"DESCRIPTIVE_ONLY"),(None,"INSUFFICIENT_HISTORY")):
        items=flow.foreign_items("VNM",DAY,{"observations":observations},in_cohort=True,calendar_evidence=evidence)
        item=next(i for i in items if i["required_observations"]==5)
        assert item["status"]==expected
        if evidence: assert item["values"]["net_value_vnd"]==50 and item["session_continuity"]["source"]==calendar.CALENDAR_RESOLVER_VERSION
    assert observations==source


@pytest.mark.parametrize("point",["before_session","before_marker","marker_fsync","after_marker","readiness_fsync"])
def test_atomic_failure_injection_and_normal_rerun_recovers(tmp_path,monkeypatch,point):
    original=store.retention._retain
    fired=False
    def fail(path,value):
        nonlocal fired
        path=Path(path)
        selected=((point=="before_session" and path.parent.name=="sessions") or
            (point in {"before_marker","marker_fsync"} and path.name=="first_complete_capture_session.json") or
            (point in {"after_marker","readiness_fsync"} and "readiness" in path.parts))
        if selected and not fired:
            fired=True
            if point.endswith("fsync"):
                import atomic_io
                with monkeypatch.context() as m:
                    m.setattr(atomic_io.os,"fsync",lambda *_: (_ for _ in ()).throw(OSError("INJECTED_TEMP_FSYNC")))
                    return original(path,value)
            raise OSError("INJECTED_BOUNDARY_CRASH")
        return original(path,value)
    monkeypatch.setattr(store.retention,"_retain",fail)
    with pytest.raises(Exception,match="INJECTED"):
        capture_session(tmp_path,calendar_days=[DAY,"2026-10-06"])
    monkeypatch.setattr(store.retention,"_retain",original)
    _,_,_,result=capture_session(tmp_path,calendar_days=[DAY,"2026-10-06"])
    marker=store.load_marker(tmp_path)
    assert marker["session"]==DAY and result["readiness"]["complete_session_count"]==1
    before=(tmp_path/store.STORE/"first_complete_capture_session.json").read_bytes()
    capture_session(tmp_path,calendar_days=[DAY,"2026-10-06"])
    assert (tmp_path/store.STORE/"first_complete_capture_session.json").read_bytes()==before


@pytest.mark.parametrize("field,value",[("completion_gate_status","BLOCKED"),("capture_complete_tickers",0),("completion_known_at","2026-10-06T12:00:00Z"),("t0_market_snapshot_identity","tampered")])
def test_invalid_original_capture_cannot_recover_marker(tmp_path,field,value):
    _,evidence,g,_=capture_session(tmp_path,calendar_days=[DAY,"2026-10-06"])
    (tmp_path/store.STORE/"first_complete_capture_session.json").unlink()
    path=tmp_path/store.STORE/"sessions"/(DAY+".json")
    record=json.loads(path.read_bytes());record[field]=value
    record=capture.identified(record,"prospective_capture_complete_session");path.write_bytes(capture.market.canonical(record))
    with pytest.raises(ValueError): store.daily_boundary(tmp_path,session=DAY,gate=g,evidence=evidence,known_at=TIME)
    assert not (tmp_path/store.STORE/"first_complete_capture_session.json").exists()


def sealed_fixture(root):
    c=context(session=DAY)
    decision=_decision(DAY);decision["ticker"]="VNM";decision["contextual_technical_context"]={"projection":c}
    snapshot=retention.build_snapshot(session=DAY,operation_identity="fixture:operation",producer_run_identity="fixture:run",
        integrated_artifact={"contract_version":"integrated_investment_decision_product/v1","session":DAY,"artifact_identity":"fixture:iid","records":{"VNM":decision}})
    path=retention.write_immutable_snapshot(root,snapshot)
    from bounded_artifact_stream import source_hash
    ref=index.from_snapshot(snapshot,path,created_at=TIME,file_sha256=source_hash(path))
    return c,snapshot,path,ref


def test_exact_seal_index_and_constant_snapshot_lookup(tmp_path,monkeypatch):
    c,snapshot,path,ref=sealed_fixture(tmp_path)
    original=Path.read_bytes
    def guarded(p):
        if p==path: raise AssertionError("FULL_T0_READ_FORBIDDEN")
        return original(p)
    monkeypatch.setattr(Path,"read_bytes",guarded)
    bindings=index.load_verified(ref,expected_snapshot_identity=snapshot["snapshot_identity"],session=DAY)
    assert bindings.bindings["VNM"]==(DAY,c["contract_version"],c["artifact_identity"])
    items=flow.volume_items(bridge.build_views(c),sealed_snapshot=bindings)
    assert any(i["knowledge_stage"]==flow.T0 for i in items)
    missing=flow.volume_items(bridge.build_views(c))
    assert all(i["knowledge_stage"]==flow.POST for i in missing)
    assert "T0_SEAL_INDEX_UNAVAILABLE" in missing[0]["reason_codes"]


@pytest.mark.parametrize("tamper",["index","snapshot","reference","receipt"])
def test_tampered_seal_binding_rejected(tmp_path,tamper):
    _,snapshot,path,ref=sealed_fixture(tmp_path)
    if tamper=="snapshot": path.write_bytes(path.read_bytes()+b" ")
    elif tamper=="reference": ref["artifact_identity"]="wrong"
    else:
        target=Path(ref["path"]) if tamper=="index" else path.parent/"prospective_t0_snapshot_write_receipt.json"
        value=json.loads(target.read_bytes()); value["snapshot_identity"]="wrong";target.write_bytes(capture.market.canonical(value))
    with pytest.raises(ValueError): index.load_verified(ref,expected_snapshot_identity=snapshot["snapshot_identity"],session=DAY)


def test_index_recovery_from_original_stream_and_partial_publication(tmp_path):
    c,snapshot,path,ref=sealed_fixture(tmp_path)
    original=path.read_bytes(); Path(ref["path"]).unlink()
    recovered=index.recover(path,created_at="2026-10-06T12:00:00Z")
    assert recovered==ref and path.read_bytes()==original
    assert index.load_verified(ref,expected_snapshot_identity=snapshot["snapshot_identity"],session=DAY).bindings["VNM"][2]==c["artifact_identity"]


@pytest.mark.parametrize("state,kwargs",[("OPEN",dict(evidence_present=True)),("PROGRESSED",dict(evidence_present=True,progressed=True)),("STILL_BLOCKED",dict(evidence_present=True)),("NOT_EVALUABLE",dict(evidence_present=False))])
def test_harness_capability_specific_open_for_any_capability(state,kwargs):
    row=harness.capability("any_existing_capability",{"source":state=="OPEN","cutoff":True},**kwargs)
    assert row["state"]==state


def test_full_fixture_harness_read_only_and_thesis_not_imported(tmp_path):
    _,_,_,r=capture_session(tmp_path,calendar_days=[DAY,"2026-10-06"])
    before={p:p.read_bytes() for p in tmp_path.rglob("*.json")}
    result=harness.collect(tmp_path,session=DAY,cutoff=DAY+"T12:10:00Z")
    states={row["capability"]:row["state"] for row in result["rows"]}
    assert states["capture_session"]==states["positive_listing"]=="OPEN"
    assert states["readiness_state"]=="PROGRESSED" and states["raw_as_traded"]=="STILL_BLOCKED"
    assert states["technical_v2_production_routing"]=="NOT_EVALUABLE"
    assert before=={p:p.read_bytes() for p in tmp_path.rglob("*.json")}
    assert not result["authority_publication"]


@pytest.mark.parametrize("tier",[capture.UNKNOWN,"UNKNOWN","UNDECLARED_TIER"])
def test_harness_unknown_representation_never_opens(tmp_path,tier):
    capture_session(tmp_path,calendar_days=[DAY,"2026-10-06"])
    readiness=store.CaptureIndex(tmp_path,cutoff=DAY+"T12:10:00Z").readiness(session=DAY)
    for facts in readiness["per_ticker"].values(): facts["representation_tier"]=tier
    result=harness.evaluate(session=DAY,cutoff=DAY+"T12:10:00Z",calendar=governed(cutoff=DAY+"T12:10:00Z"),readiness=readiness)
    row=next(r for r in result["rows"] if r["capability"]=="representation_tier")
    assert row["state"]=="STILL_BLOCKED" and row["opening_predicates"]["all_names_have_source_representation"] is False


def test_prior_volume_trajectory_uses_same_governed_primitive(monkeypatch):
    from test_contextual_technical_features import series,seal
    import contextual_technical_features_v2 as v2
    rows=series(45)
    rows[-1].update(period_start=DAY,period_end=DAY,first_trading_session=DAY,last_trading_session=DAY,
        constituent_sessions=[DAY],knowledge_available_at=DAY+"T09:00:00Z")
    seal(rows[-1])
    c=v2.build_context({"1D":rows},ticker="VNM",as_of_session=DAY,knowledge_cutoff=TIME)
    days=[r["last_trading_session"] for r in rows]
    proof=governed(days,cutoff=TIME,known=days[0]+"T04:00:00Z")
    calls=[];original=calendar.are_consecutive_governed_sessions
    def watched(a,b,cutoff,c):calls.append((a,b));return original(a,b,cutoff,c)
    monkeypatch.setattr(calendar,"are_consecutive_governed_sessions",watched)
    items=flow.volume_items(bridge.build_views(c),series={"1D":rows},calendar_evidence=proof)
    trajectory=next(i for i in items if i["horizon"]=="1D/5")
    assert trajectory["status"] in flow.USABLE and ("2026-10-01",DAY) in calls
    assert trajectory["session_continuity"]["source"]==calendar.CALENDAR_RESOLVER_VERSION
    unproven=flow.volume_items(bridge.build_views(c),series={"1D":rows})
    assert next(i for i in unproven if i["horizon"]=="1D/5")["status"]=="BLOCKED_SESSION_CONTINUITY"


def test_recovery_cannot_skip_earlier_qualifying_record_or_conflicting_marker(tmp_path):
    _,evidence,g,_=capture_session(tmp_path,calendar_days=[DAY,"2026-10-06"])
    _,later_evidence,later_gate,_=capture_session(tmp_path,"2026-10-06",calendar_days=[DAY,"2026-10-06"])
    marker_path=tmp_path/store.STORE/"first_complete_capture_session.json"
    marker_path.unlink()
    with pytest.raises(ValueError,match="EARLIER_COMPLETE"):
        store.daily_boundary(tmp_path,session="2026-10-06",gate=later_gate,evidence=later_evidence,known_at="2026-10-06T12:10:00Z")
    later=json.loads((tmp_path/store.STORE/"sessions/2026-10-06.json").read_bytes())
    marker=capture.identified({"contract_version":"first_complete_capture_session/v1","session":"2026-10-06",
        "written_at":later["completion_known_at"],"capture_session_identity":later["artifact_identity"]},"first_complete_capture_session")
    marker_path.write_bytes(capture.market.canonical(marker))
    with pytest.raises(ValueError,match="FIRST_CAPTURE_MARKER_CONFLICT"):
        store.daily_boundary(tmp_path,session=DAY,gate=g,evidence=evidence,known_at=TIME)


def test_original_calendar_registration_is_explicit_and_preserves_bytes(tmp_path):
    from tools.register_working_dates_receipt import register
    raw=capture.market.canonical({"workingDates":["2026-10-02",DAY]})
    source=tmp_path/"original.json";source.write_bytes(raw)
    destination=tmp_path/"isolated-registration-fixture"
    r=register(source,source_sha256=capture.market.sha256_hex(raw),retrieved_at="2026-10-02T04:00:00Z",
        documentation_sha256="a"*64,documentation_known_at="2026-10-02T03:40:00Z",destination_root=destination)
    assert source.read_bytes()==raw and r["original_retrieved_at"]=="2026-10-02T04:00:00Z" and not r["historical_extension"]
    c=store.calendar_evidence_at_cutoff(destination,cutoff=TIME)
    assert calendar.are_consecutive_governed_sessions("2026-10-02",DAY,TIME,c)["state"]=="TRUE"


def test_harness_no_capture_lookahead_and_dry_run_all_states(tmp_path):
    capture_session(tmp_path,calendar_days=[DAY,"2026-10-06"])
    earlier=harness.collect(tmp_path,session=DAY,cutoff=TIME)
    assert next(r for r in earlier["rows"] if r["capability"]=="capture_session")["state"]=="NOT_EVALUABLE"
    from tools.run_first_real_session_acceptance import dry_run
    r=dry_run(session=DAY,cutoff=DAY+"T12:10:00Z")
    assert {row["state"] for row in r["rows"]}==set(harness.STATES)
    assert r["network_provider_calls"]=={"network":0,"provider":0,"vnstock_import":0}


def test_large_snapshot_payload_does_not_enlarge_index_or_get_deserialized(tmp_path,monkeypatch):
    c,snapshot,path,ref=sealed_fixture(tmp_path/"small")
    baseline=Path(ref["path"]).stat().st_size
    decision=copy.deepcopy(snapshot["records"]["VNM"]["integrated_decision_at_t0"])
    decision["synthetic_explanation_padding"]="x"*(2*1024*1024)
    large=retention.build_snapshot(session=DAY,operation_identity="fixture:operation",producer_run_identity="fixture:run",
        integrated_artifact={"contract_version":"integrated_investment_decision_product/v1","session":DAY,"artifact_identity":"fixture:iid","records":{"VNM":decision}})
    from bounded_artifact_stream import source_hash
    large_path=retention.write_immutable_snapshot(tmp_path/"large",large)
    large_ref=index.from_snapshot(large,large_path,created_at=TIME,file_sha256=source_hash(large_path))
    assert large_path.stat().st_size>2*1024*1024 and Path(large_ref["path"]).stat().st_size==baseline
    original=Path.read_bytes
    def guarded(p):
        if p==large_path:raise AssertionError("FULL_T0_PARSE_FORBIDDEN")
        return original(p)
    monkeypatch.setattr(Path,"read_bytes",guarded)
    assert index.load_verified(large_ref,expected_snapshot_identity=large["snapshot_identity"],session=DAY).bindings["VNM"][2]==c["artifact_identity"]


def test_portable_corrective_acceptance():
    p=json.loads((Path(__file__).resolve().parents[1]/"docs/internal/MONDAY_LIVE_READINESS_CLOSEOUT_ACCEPTANCE.json").read_bytes())
    assert all(p.get(k)==v for k,v in capture.market.content_identity(p,kind="monday_live_readiness_closeout_acceptance").items())
    assert p["all_assertions_passed"] and p["historical_t0"]["files"]==19 and p["old_receipts"]["versions"]==908
    assert p["real_release_readiness"]["complete_session_count"]==0 and p["real_release_readiness"]["first_complete_capture_session"] is None
    assert p["calendar"]["registration_executed"] is False and p["seal_index"]["ordinary_snapshot_json_parses"]==0
    assert p["action_posture_policy_delta"]==0 and p["thesis_stage_1"]=="FROZEN_OFFLINE"
    assert p["network_provider_calls"]=={"network":0,"provider":0,"vnstock_import":0} and not p["next_gate_started"]


@pytest.mark.parametrize("missing",[False,True])
def test_normal_v2_observer_uses_index_and_never_loads_snapshot(tmp_path,monkeypatch,missing):
    import canonical_post_close_pipeline as pipeline
    import volume_and_flow_retained_v2 as adapter
    c,snapshot,path,ref=sealed_fixture(tmp_path)
    if missing:Path(ref["path"]).unlink()
    binding={"status":"RETAINED","path":str(path),"identity":snapshot["snapshot_identity"],"seal_index":{"status":"RETAINED",**ref}}
    def collect(**kwargs):
        bound=kwargs["sealed_snapshot"]
        assert (bound is None)==missing
        a=flow.build_artifact(session=DAY,tickers=["VNM"],relationship_views={"VNM":bridge.build_views(c)},flow_series={},sealed_snapshot=bound)
        assert all(i["knowledge_stage"]==flow.POST for i in a["records"]["VNM"]["items"]) if missing else any(i["knowledge_stage"]==flow.T0 for i in a["records"]["VNM"]["items"])
        return a,{}
    monkeypatch.setattr(adapter,"collect",collect)
    monkeypatch.setattr(pipeline,"_load",lambda p: (_ for _ in ()).throw(AssertionError("FULL_SNAPSHOT_LOAD_FORBIDDEN")))
    r=pipeline.run_volume_and_flow_context(tmp_path,tmp_path,DAY,{"status":"UNAVAILABLE"},binding)
    assert r["status"]=="COLLECTED" and r["contract_version"]==flow.CONTRACT_VERSION


@pytest.mark.parametrize("failed_index",[False,True])
def test_normal_snapshot_write_creates_index_without_second_parse(tmp_path,monkeypatch,failed_index):
    import canonical_post_close_pipeline as pipeline
    c=context(session=DAY)
    decision=_decision(DAY);decision["ticker"]="VNM";decision["contextual_technical_context"]={"projection":c}
    integrated={"contract_version":"integrated_investment_decision_product/v1","session":DAY,
        "artifact_identity":"fixture:iid","records":{"VNM":decision}}
    original=Path.read_bytes
    def guarded(path):
        if path.name=="prospective_decision_snapshot.json":raise AssertionError("SECOND_T0_PARSE_FORBIDDEN")
        return original(path)
    monkeypatch.setattr(Path,"read_bytes",guarded)
    monkeypatch.setattr(store,"io_known_at",lambda:TIME)
    if failed_index:
        monkeypatch.setattr(index,"from_snapshot",lambda *a,**k:(_ for _ in ()).throw(OSError("fixture_index_publication_failure")))
    result=pipeline.retain_prospective_decision_snapshot(tmp_path,DAY,
        producer_result={"operation":{"manifest":{"operation_identity":"fixture:operation"}},"run_identity":"fixture:run"},
        enrichment={"integrated_investment_decision_product":{"artifact":integrated}})
    assert result["status"]=="RETAINED" and result["path"].exists()
    if failed_index:
        assert result["seal_index"]["status"]=="UNAVAILABLE" and "PUBLICATION_FAILED" in result["seal_index"]["reason"]
    else:
        bound=index.load_verified(result["seal_index"],expected_snapshot_identity=result["artifact"]["snapshot_identity"],session=DAY)
        assert bound.bindings["VNM"][2]==c["artifact_identity"]


@pytest.mark.parametrize("missing_index",[False,True])
def test_harness_streams_verified_artifacts_and_reports_missing_index(tmp_path,missing_index):
    capture_session(tmp_path,calendar_days=[DAY,"2026-10-06"])
    c,snapshot,path,ref=sealed_fixture(tmp_path)
    bound=index.load_verified(ref,expected_snapshot_identity=snapshot["snapshot_identity"],session=DAY)
    technical_artifact={"contract_version":"market_wide_historical_research_context/v1","session":DAY,
        "records":{"VNM":{"contextual_technical":c}}}
    technical_artifact.update(capture.market.content_identity(technical_artifact,kind="market_wide_historical_research_context"))
    flow_artifact=flow.build_artifact(session=DAY,tickers=["VNM"],relationship_views={"VNM":bridge.build_views(c)},flow_series={},sealed_snapshot=bound)
    technical_path=tmp_path/"technical.json";flow_path=tmp_path/"flow.json"
    technical_path.write_bytes(capture.market.canonical(technical_artifact));flow_path.write_bytes(capture.market.canonical(flow_artifact))
    if missing_index:Path(ref["path"]).unlink()
    result=harness.collect(tmp_path,session=DAY,cutoff=DAY+"T12:10:00Z",technical_path=technical_path,flow_path=flow_path,
        snapshot_binding={"identity":snapshot["snapshot_identity"],"seal_index":{"status":"RETAINED",**ref}})
    states={r["capability"]:r["state"] for r in result["rows"]}
    assert states["technical_v2_production_routing"]==states["volume_flow_v2_production_routing"]=="OPEN"
    assert states["exact_t0_v2_seal_index"]==("STILL_BLOCKED" if missing_index else "OPEN")
    assert states["post_to_t0_leakage"]==("NOT_EVALUABLE" if missing_index else "OPEN")


def test_harness_and_index_do_not_import_thesis_stage_one():
    import ast
    for module in (harness,index):
        tree=ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        modules=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        modules += [alias.name for n in ast.walk(tree) if isinstance(n,ast.Import) for alias in n.names]
        assert not any(name and name.rsplit(".", 1)[-1].startswith("thesis_evidence") for name in modules)


def test_t0less_first_session_preserves_capture_marker_and_depth(tmp_path,monkeypatch):
    capture_session(tmp_path,calendar_days=[DAY,"2026-10-06"],t0_snapshot_identity=None)
    assert json.loads((tmp_path/store.STORE/"sessions"/(DAY+".json")).read_bytes())["t0_decision_snapshot_identity"] is None
    assert store.load_marker(tmp_path)["session"]==DAY
    import socket
    monkeypatch.setattr(socket,"socket",lambda *a,**k:pytest.fail("NETWORK_FORBIDDEN"))
    monkeypatch.setattr(Path,"write_bytes",lambda *a,**k:pytest.fail("EVIDENCE_WRITE_FORBIDDEN"))
    monkeypatch.setattr(Path,"write_text",lambda *a,**k:pytest.fail("EVIDENCE_WRITE_FORBIDDEN"))
    report=harness.collect(tmp_path,session=DAY,cutoff=DAY+"T12:10:00Z")
    rows={r["capability"]:r for r in report["rows"]}
    assert rows["capture_session"]["state"]==rows["first_marker"]["state"]=="OPEN"
    assert rows["readiness_state"]["details"]["complete_session_count"]==1
    assert rows["t0_snapshot_availability"]["state"]=="STILL_BLOCKED"
    assert rows["t0_snapshot_availability"]["details"]["availability"]=="UNAVAILABLE"
    assert rows["t0_snapshot_availability"]["details"]["gates_capture"] is False
    assert rows["post_to_t0_leakage"]["state"]=="NOT_EVALUABLE"
    assert rows["post_to_t0_leakage"]["details"]["reason"]=="T0_UNAVAILABLE_FOR_LEAKAGE_EVALUATION"
    assert all(rows[n]["state"]!="OPEN" for n in ("exact_t0_v2_seal_index","t0_native_volume","pit_continuous_price","raw_as_traded","ca"))
    assert all(row["state"]=="NOT_EVALUABLE" for name,row in rows.items() if name.startswith("thesis_t0_"))


@pytest.mark.parametrize("t0_present,has_content,leak,expected",[
    (True,True,False,"OPEN"),(False,True,False,"NOT_EVALUABLE"),
    (True,False,False,"NOT_EVALUABLE"),(True,True,True,"STILL_BLOCKED"),
])
def test_leakage_requires_verified_t0_and_nonempty_evaluation(tmp_path,t0_present,has_content,leak,expected):
    c,snapshot,path,ref=sealed_fixture(tmp_path)
    bound=index.load_verified(ref,expected_snapshot_identity=snapshot["snapshot_identity"],session=DAY)
    artifact=flow.build_artifact(session=DAY,tickers=["VNM"],relationship_views={"VNM":bridge.build_views(c)},flow_series={},sealed_snapshot=bound)
    records=harness.VerifiedFlowSummary(copy.deepcopy(artifact["records"]))
    t0_items=[i for row in records.values() for i in row["items"] if i["knowledge_stage"]==flow.T0]
    assert t0_items
    if not has_content:
        for item in t0_items:item["knowledge_stage"]=flow.POST
    if leak:t0_items[0]["source_artifact_identities"]=[]
    report=harness.evaluate(session=DAY,cutoff=TIME,calendar=governed(cutoff=TIME),
        sealed_bindings=bound if t0_present else None,flow_records=records)
    rows={r["capability"]:r for r in report["rows"]}
    assert rows["post_to_t0_leakage"]["state"]==expected
    assert rows["post_to_t0_leakage"]["details"]["evaluation_performed"]==(t0_present and has_content)
    assert rows["t0_snapshot_availability"]["details"]["availability"]==("AVAILABLE" if t0_present else "UNAVAILABLE")
    if leak:assert rows["post_to_t0_leakage"]["details"]["count"]>0


def test_unavailable_thesis_report_cannot_open_t0_zero_guards():
    report=harness.evaluate(session=DAY,cutoff=TIME,calendar=governed(cutoff=TIME),
        capture_record={"capture_complete_tickers":["VNM"]},marker={"session":DAY},
        thesis_state={"stage_2":"COMPLETE"},thesis_products={"t0":{
            "status":"UNAVAILABLE","reason":"VERIFIED_T0_SEAL_INDEX_UNAVAILABLE","records":0,
            "counts":{"built_count":0,"partial_count":0,"unavailable_count":1},
            "post_in_t0":0,"guards":{"retrospective_item_in_t0":0}}})
    rows={r["capability"]:r for r in report["rows"]}
    assert rows["capture_session"]["state"]==rows["first_marker"]["state"]=="OPEN"
    assert all(row["state"]=="NOT_EVALUABLE" for name,row in rows.items() if name.startswith("thesis_t0_"))
