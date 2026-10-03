"""The actual source adapter, post-handoff observer and retained output gates."""
import json
import sqlite3
from pathlib import Path

import pytest

import canonical_market_bars as bars
import canonical_post_close_pipeline as pipeline
import contextual_technical_features as technical
import volume_and_flow_context as context
import volume_and_flow_retained as adapter
from bounded_artifact_stream import source_hash
from test_canonical_market_bars import daily
from test_volume_and_flow_context import ASOF,CUTOFF


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True,indent=2),encoding="utf-8")


def fixture(tmp_path,monkeypatch):
    root=tmp_path/"source";runtime=tmp_path/"runtime"
    runtime.mkdir()
    from datetime import date,timedelta
    days=[(date(2026,10,2)-timedelta(days=44-i)).isoformat() for i in range(45)]
    rows=[daily(day,open=10,high=15,low=9,close=12,volume=100+i,retrieved_at=day+"T09:00:00Z") for i,day in enumerate(days)]
    paths={k:root/(k+".json") for k in ("exact_session_snapshot","universe_resolution","technical_recovery")}
    snapshot={"resolved_completed_session":ASOF,"requested_at":CUTOFF,"records":{"VNM":{"observations":rows}}}
    from field_temporal_contract import stable_id
    digest=stable_id(snapshot);snapshot.update(snapshot_identity="p3f9_exact_session_snapshot:"+digest,snapshot_sha256=digest)
    write(paths["exact_session_snapshot"],snapshot)
    universe=context.seal({"records":{"VNM":{"activity_and_session_state":"ACTIVE_LISTED_OBSERVED"}}},"test:universe")
    recovery=context.seal({"source_lineage":{"p3f9b_snapshot_identity":snapshot["snapshot_identity"]}},"test:recovery")
    write(paths["universe_resolution"],universe);write(paths["technical_recovery"],recovery)
    import current_official_event_context as events
    event={"records":{}};event.update(events._identity(event));write(root/"events.json",event)
    descriptive=context.seal({"records":{"VNM":{"sector_classification":{"entity_class":"FOOD","classification_authority":"test"}}}},"test:descriptive")
    write(root/"descriptive.json",descriptive)
    write(root/"config/daily_research_session_input_registry.json",{"sessions":{ASOF:{"event_context":{"path":"events.json","artifact_identity":event["artifact_identity"]},"descriptive":{"path":"descriptive.json","artifact_identity":descriptive["artifact_identity"]}}}})
    original=Path(__file__).resolve().parents[1]/"config/governed_trading_session_calendar_v1.json"
    calendar=json.loads(original.read_text());write(root/"config/governed_trading_session_calendar_v1.json",calendar)
    series=bars.research_series(rows,ticker="VNM",target_session=ASOF,knowledge_cutoff=CUTOFF,
        source_identity=snapshot["snapshot_identity"],calendar_evidence=bars.governed_calendar_projection(calendar))
    tech=technical.build_context(series,ticker="VNM",as_of_session=ASOF,knowledge_cutoff=CUTOFF)
    history=context.seal({"session":ASOF,"records":{"VNM":{"contextual_technical":tech}}},"test:history")
    write(root/"operations-review/canonical-post-close-v1"/ASOF/"enrichment/historical_context.json",history)
    batch=root/"batch.ndjson";batch.write_text(json.dumps({"ticker":"VNM","contextual_technical":tech})+"\n")
    with sqlite3.connect(runtime/"vn_stock.db") as db:
        db.execute("CREATE TABLE ohlcv(ticker TEXT,date TEXT)")
        db.executemany("INSERT INTO ohlcv VALUES(?,?)",[("VNM",d) for d in days])
    monkeypatch.setattr(adapter.level2,"session_artifact_paths",lambda *_:paths)
    return root,runtime,batch


@pytest.mark.parametrize("batch_mode",[False,True])
def test_real_adapter_builds_identical_references_and_preserves_sources(tmp_path,monkeypatch,batch_mode):
    root,runtime,batch=fixture(tmp_path,monkeypatch)
    before={str(p):source_hash(p) for p in root.rglob("*.json")}
    args={"feature_batch":batch,"feature_batch_sha256":source_hash(batch)} if batch_mode else {}
    artifact,stats=adapter.collect(source_root=root,runtime_root=runtime,session=ASOF,**args)
    assert artifact["universe_denominator"]==1 and stats["source_bytes_unchanged"]
    assert before=={str(p):source_hash(p) for p in root.rglob("*.json")}
    assert stats["price_corpora_parsed"]==1
    short=next(i for i in artifact["records"]["VNM"]["items"] if i["horizon"]=="1D/5" and i["domain"]=="VOLUME")
    assert short["status"] in context.USABLE and short["knowledge_stage"]==context.POST
    assert artifact["records"]["VNM"]["sector"].endswith("FOOD")


def test_batch_digest_source_binding_fail_closed(tmp_path,monkeypatch):
    root,runtime,batch=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match="BATCH_HASH"):
        adapter.collect(source_root=root,runtime_root=runtime,session=ASOF,feature_batch=batch,feature_batch_sha256="wrong")


def test_foreign_raw_shares_cannot_be_substituted_for_vnd(tmp_path):
    from dnse_foreign_flow_store import observations_root,SOURCE_CONTRACT_VERSION
    write(observations_root(tmp_path)/"VNM.json",{"observations":[{"ticker":"VNM","session_date":ASOF,"value_unit":"shares","source":"DNSE","source_contract_version":SOURCE_CONTRACT_VERSION}]})
    with pytest.raises(ValueError,match="SOURCE_SEMANTICS"):
        adapter.flow_index(tmp_path,ASOF,{},frozenset())


def test_foreign_adapter_sorts_and_does_not_retain_volume_fields(tmp_path):
    from dnse_foreign_flow_store import observations_root,SOURCE_CONTRACT_VERSION
    raw=[{"ticker":"VNM","session_date":day,"value_unit":"vnd","source":"DNSE","source_contract_version":SOURCE_CONTRACT_VERSION,
        "foreign_buy_value":100,"foreign_sell_value":20,"foreign_buy_volume":999} for day in (ASOF,"2026-10-01")]
    write(observations_root(tmp_path)/"VNM.json",{"observations":raw})
    index=adapter.flow_index(tmp_path,ASOF,{},frozenset())
    assert [o["session_date"] for o in index["VNM"]["observations"]]==["2026-10-01",ASOF]
    assert all("foreign_buy_volume" not in o for o in index["VNM"]["observations"])
    raw.reverse();write(observations_root(tmp_path)/"VNM.json",{"observations":raw})
    assert adapter.flow_index(tmp_path,ASOF,{},frozenset())==index


def test_post_handoff_observer_writes_separate_artifact_and_failure_is_nonblocking(tmp_path,monkeypatch):
    root,runtime,batch=fixture(tmp_path,monkeypatch)
    result=pipeline.run_volume_and_flow_context(root,runtime,ASOF,{"status":"UNAVAILABLE"})
    assert result["status"]=="COLLECTED" and result["non_voting"]
    artifact=json.loads((root/result["path"]).read_text())
    assert artifact["build_stage"]==context.POST
    monkeypatch.setattr(adapter,"collect",lambda **_:(_ for _ in ()).throw(ValueError("MISSING_SOURCE")))
    result=pipeline.run_volume_and_flow_context(root,runtime,ASOF,{"status":"UNAVAILABLE"})
    assert result["status"]=="UNAVAILABLE" and "MISSING_SOURCE" in result["reason"]


def test_post_handoff_order_and_surface_reference_preserve_decision(tmp_path,monkeypatch):
    order=[]
    monkeypatch.setattr(pipeline,"run_multi_session_signal_velocity_shadow",lambda *_:order.append("velocity") or {})
    monkeypatch.setattr(pipeline,"run_current_foreign_flow_enrichment",lambda *a,**kw:order.append("existing_foreign") or {})
    monkeypatch.setattr(pipeline,"run_flow_price_divergence_shadow",lambda *_:order.append("existing_relationship") or {})
    monkeypatch.setattr(pipeline,"run_volume_and_flow_context",lambda *_:order.append("volume_flow") or {"status":"COLLECTED","artifact_identity":"test:new"})
    tiers={"session_handoff_bundle":{"decision_identity":"test:sealed"},"bundle_dir":tmp_path}
    result=pipeline.run_post_handoff_observers(tmp_path,tmp_path,ASOF,tiers)
    assert order==["velocity","existing_foreign","existing_relationship","volume_flow"]
    assert tiers["session_handoff_bundle"]["decision_identity"]=="test:sealed"
    assert result["volume_and_flow_context"]["artifact_identity"]=="test:new"


def test_acceptance_coverage_accounts_outside_cohort(tmp_path,monkeypatch):
    from tools.run_volume_and_flow_context import coverage,representative_cases
    root,runtime,batch=fixture(tmp_path,monkeypatch)
    artifact,_=adapter.collect(source_root=root,runtime_root=runtime,session=ASOF)
    stats=coverage(artifact)
    assert stats["foreign"]["1"]["outside_cohort_count"]==1
    assert stats["volume"]["1D"]["in_scope_denominator"]==1
    assert representative_cases(artifact)["outside_foreign_cohort"]["ticker"]=="VNM"

