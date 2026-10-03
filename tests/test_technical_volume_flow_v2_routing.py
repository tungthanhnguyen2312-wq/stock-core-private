"""Normal paired retained routing, explicit compatibility and production construction."""
import json
import pytest
import contextual_technical_dispatch as dispatch
import contextual_technical_features_v2 as technical
import volume_and_flow_context_v2 as flow
import volume_and_flow_retained as old_adapter
import volume_and_flow_retained_v2 as adapter
import canonical_market_bars as bars
from bounded_artifact_stream import source_hash
from test_volume_and_flow_retained import fixture, ASOF, CUTOFF
from test_contextual_technical_features import series


@pytest.mark.parametrize("bridge",[False,True])
def test_actual_retained_version_drives_pair_and_explicit_compatibility(tmp_path,monkeypatch,bridge):
    root,runtime,batch=fixture(tmp_path,monkeypatch)
    a,_=adapter.collect(source_root=root,runtime_root=runtime,session=ASOF,feature_batch=batch,feature_batch_sha256=source_hash(batch),allow_legacy_bridge=bridge)
    if bridge:
        assert a["contract_version"]==flow.CONTRACT_VERSION
        assert a["evaluation_scope"]=="REPLAY_DIAGNOSTIC_NON_AUTHORITATIVE"
        assert all(i["knowledge_stage"]==flow.POST for i in a["records"]["VNM"]["items"])
    else:
        old,_=old_adapter.collect(source_root=root,runtime_root=runtime,session=ASOF,feature_batch=batch,feature_batch_sha256=source_hash(batch))
        assert a==old


def test_v2_retained_batch_builds_v2_observer(tmp_path,monkeypatch):
    root,runtime,batch=fixture(tmp_path,monkeypatch)
    paths=adapter.level2.session_artifact_paths(root,ASOF)
    source=json.loads(paths["exact_session_snapshot"].read_text())
    calendar=bars.governed_calendar_projection(json.loads((root/"config/governed_trading_session_calendar_v1.json").read_text()))
    rows=bars.research_series(source["records"]["VNM"]["observations"],ticker="VNM",target_session=ASOF,knowledge_cutoff=CUTOFF,
        source_identity=source["snapshot_identity"],calendar_evidence=calendar)
    c=technical.build_context(rows,ticker="VNM",as_of_session=ASOF,knowledge_cutoff=CUTOFF)
    batch.write_text(json.dumps({"ticker":"VNM","contextual_technical":c})+"\n",encoding="utf-8")
    a,stats=adapter.collect(source_root=root,runtime_root=runtime,session=ASOF,feature_batch=batch,feature_batch_sha256=source_hash(batch))
    assert a["contract_version"]==flow.CONTRACT_VERSION and a["technical_contract_version"]==dispatch.V2
    assert stats["price_corpora_parsed"]==stats["technical_batches_parsed"]==1


def test_new_sessions_construct_v2_without_dual_emission(monkeypatch):
    monkeypatch.setattr(bars,"research_series",lambda *_,**__: {"1D":series(),"1W":[],"1M":[]})
    p=dispatch.build_research_projections([],ticker="VNM",target_session="2026-10-03",knowledge_cutoff=CUTOFF,source_identity="fixture:only")
    assert p["contextual_technical"]["contract_version"]==dispatch.V2
    assert set(p)=={"multi_timeframe","contextual_technical"}


def test_mixed_retained_batch_rejected_before_any_volume_build(tmp_path,monkeypatch):
    root,runtime,batch=fixture(tmp_path,monkeypatch)
    original=json.loads(batch.read_text())
    changed=json.loads(batch.read_text());changed["ticker"]="AAA";changed["contextual_technical"]["contract_version"]=dispatch.V2
    batch.write_text(json.dumps(original)+"\n"+json.dumps(changed)+"\n")
    with pytest.raises(ValueError,match="^TECHNICAL_VERSION_MIXED$"):
        adapter.collect(source_root=root,runtime_root=runtime,session=ASOF,feature_batch=batch,feature_batch_sha256=source_hash(batch))


def test_portable_full_retained_acceptance_identity_and_denominators():
    from pathlib import Path
    p=json.loads((Path(__file__).resolve().parents[1]/"docs/internal/TECHNICAL_VOLUME_FLOW_V2_MIGRATION_ACCEPTANCE.json").read_text(encoding="utf-8"))
    assert all(p.get(k)==v for k,v in technical.identity(p,kind="paired_technical_volume_flow_semantic_migration_acceptance").items())
    assert p["all_assertions_passed"] and p["evaluation_scope"]=="REPLAY_DIAGNOSTIC"
    assert p["universe_denominator"]==1683 and p["technical_scope"]==1503
    for tf in technical.TIMEFRAMES:
        for name in ("swing_relation","setup_state","temporal_states"):
            assert sum(p["technical_v2_distributions"][tf][name].values())==1503
    assert p["non_regression"]["exact_all_other_decision_field_deltas"]==0
    assert p["v1_freeze"]["rebuilt_v1_record_deltas"]==p["v1_freeze"]["tactical_owner_field_deltas"]==0
    assert p["volume_flow_v2_coverage"]["knowledge_stage_counts"]=={flow.POST:25308}
    assert p["explicit_v1_to_v2_compatibility"]["knowledge_stage_counts"]=={flow.POST:13527}
    readiness=p["pit_compatibility"]["readiness"]
    assert readiness["first_complete_capture_session"] is None and readiness["complete_session_count"]==0
    assert all(value==0 for value in readiness["counts_at_depth"].values())
    assert p["network_provider_calls"]=={"network":0,"provider":0,"vnstock_import":0}
    assert p["final_public_verifiers"]=={"technical_contexts":1503,"relationship_views":4509,"volume_flow_records":1683,"status":"PASS"}
