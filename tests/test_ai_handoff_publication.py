from __future__ import annotations
import json, subprocess
import pytest
from ai_handoff_publication import HandoffPublicationError, build_package, publish, verify_remote_publication

def git(path,*args): subprocess.run(["git","-C",str(path),*args],check=True,capture_output=True)
def source(path, *, version="one"):
    path.mkdir()
    (path/"ai_research_session_bundle.json").write_text(json.dumps({"artifact_identity":"bundle:"+version}),encoding="utf-8")
    (path/"daily_opportunity_decision_queue_artifact.json").write_text(json.dumps({"artifact_identity":"queue:"+version}),encoding="utf-8")
    (path/"ai_research_bundle_manifest.json").write_text(json.dumps({"artifact_identity":"manifest:"+version,"producer_head":"producer:"+version,"operation_identity":"operation:"+version,"daily_product_identity":"product:"+version}),encoding="utf-8")
def repo(path):
    path.mkdir(); git(path,"init","-q"); git(path,"config","user.email","test@example.com"); git(path,"config","user.name","Test"); (path/"README.md").write_text("x\n"); git(path,"add","README.md"); git(path,"commit","-qm","init")
def legacy(path):
    old=path/"sessions"/"2026-08-28"; old.mkdir(parents=True)
    for name in ("ai_research_session_bundle.json","daily_opportunity_decision_queue_artifact.json","ai_research_bundle_manifest.json"):
        (old/name).write_text(json.dumps({"legacy":name}),encoding="utf-8")
    (old/"HANDOFF.md").write_text("legacy\n",encoding="utf-8")
    git(path,"add","sessions"); git(path,"commit","-qm","legacy session")
    return {p.name:p.read_bytes() for p in old.iterdir()}
def prior(path):
    bundle=path/"2026-08-27"/"prior-build"/"ai_research_session_bundle.json"; bundle.parent.mkdir(parents=True); bundle.write_text(json.dumps({"session":"2026-08-27"}),encoding="utf-8"); return bundle

def test_versioned_build_preserves_legacy_updates_latest_and_is_idempotent(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r); old=legacy(r); previous=prior(tmp_path/"prior")
    first=publish(r,s,"2026-08-28",previous=previous,producer_checkpoint="abc",push=False)
    build=first["package"]["handoff_build_id"]; target=r/first["immutable_session_path"]
    assert target.is_dir() and build in target.as_posix()
    assert {p.name:p.read_bytes() for p in (r/"sessions"/"2026-08-28").iterdir() if p.is_file()} == old
    latest=json.loads((r/"LATEST.json").read_text())
    assert latest["handoff_build_id"] == build
    assert latest["immutable_session_path"] == first["immutable_session_path"]
    assert latest["handoff_commit"] == first["immutable_handoff_commit"]
    assert latest["previous_session"] == "2026-08-27"
    assert publish(r,s,"2026-08-28",previous=previous,producer_checkpoint="abc",push=False)["status"] == "NO_OP_ALREADY_PUBLISHED"

def test_same_build_with_mutated_bytes_fails_closed(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    first=publish(r,s,"2026-08-28",producer_checkpoint="abc",push=False)
    target=r/first["immutable_session_path"]/"ai_research_session_bundle.json"; target.write_text('{"mutated":true}',encoding="utf-8")
    with pytest.raises(HandoffPublicationError,match="HANDOFF_BUILD_CONFLICT"):
        publish(r,s,"2026-08-28",producer_checkpoint="abc",push=False)

def test_second_legitimate_build_for_same_session_is_separate_and_deterministic(tmp_path):
    one,two,r=tmp_path/"one",tmp_path/"two",tmp_path/"repo"; source(one,version="one"); source(two,version="two"); repo(r)
    assert build_package(one,"2026-08-28",producer_checkpoint="abc")[1]["handoff_build_id"] == build_package(one,"2026-08-28",producer_checkpoint="abc")[1]["handoff_build_id"]
    first=publish(r,one,"2026-08-28",producer_checkpoint="abc",push=False)
    first_bytes={p.name:p.read_bytes() for p in (r/first["immutable_session_path"]).iterdir()}
    second=publish(r,two,"2026-08-28",producer_checkpoint="def",push=False)
    assert first["immutable_session_path"] != second["immutable_session_path"]
    assert {p.name:p.read_bytes() for p in (r/first["immutable_session_path"]).iterdir()} == first_bytes
    assert json.loads((r/"LATEST.json").read_text())["handoff_build_id"] == second["package"]["handoff_build_id"]

def test_absolute_paths_are_rejected(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    (s/"ai_research_session_bundle.json").write_text(json.dumps({"path":"D:\\private\\bundle"}),encoding="utf-8")
    with pytest.raises(HandoffPublicationError,match="ABSOLUTE_PATH"):
        publish(r,s,"2026-08-28",push=False)

def test_compact_financial_identity_chain_is_validated_without_full_engine_dump(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    identity="financial_analysis_context/v2:abc"
    (s/"ai_research_session_bundle.json").write_text(json.dumps({"financial_analysis":{"source_context_identity":identity,"market_summary":{"source_context_identity":identity},"ticker_index":{"AAA":{"status":"AVAILABLE"}}}}),encoding="utf-8")
    (s/"ai_research_bundle_manifest.json").write_text(json.dumps({"producer_head":"p","operation_identity":"o","daily_product_identity":"d","financial_analysis_source_context_identity":identity}),encoding="utf-8")
    _, payload=build_package(s,"2026-08-28",producer_checkpoint="abc")
    assert payload["lineage"]["financial_analysis_source_context_identity"] == identity
    (s/"ai_research_bundle_manifest.json").write_text(json.dumps({"financial_analysis_source_context_identity":"other"}),encoding="utf-8")
    with pytest.raises(HandoffPublicationError,match="FINANCIAL_ANALYSIS_IDENTITY_CHAIN"):
        build_package(s,"2026-08-28",producer_checkpoint="abc")

def test_decision_brief_is_optional_and_additive(tmp_path):
    """A caller that never passes decision_brief sees byte-identical behavior (opt-in only)."""
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    without=build_package(s,"2026-08-28",producer_checkpoint="abc")
    assert "next_session_decision_brief.json" not in without[0]
    assert "next_session_decision_brief.json" not in without[1]["files"]

def test_decision_brief_included_when_supplied(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    brief=tmp_path/"next_session_decision_brief.json"; brief.write_text(json.dumps({"artifact_identity":"next_session_decision_brief:abc123"}),encoding="utf-8")
    result=publish(r,s,"2026-08-28",producer_checkpoint="abc",push=False,decision_brief=brief)
    assert (r/result["immutable_session_path"]/"next_session_decision_brief.json").is_file()
    assert result["package"]["lineage"]["next_session_decision_brief_identity"]=="next_session_decision_brief:abc123"
    latest=json.loads((r/"LATEST.json").read_text())
    assert latest["decision_brief_sha256"]==result["package"]["files"]["next_session_decision_brief.json"]

def test_comparison_metadata_propagates_into_lineage_and_latest_json(tmp_path):
    """SESSION_REGISTRY_PROMOTION_AND_COMPARISON_SEMANTICS_CORRECTIVE_V1: whatever
    comparison_metadata next_session_decision_brief.json carries must survive, additively,
    into both the handoff package's lineage and the published LATEST.json pointer."""
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    comparison_metadata={"comparison_session":"2026-08-26","comparison_session_role":"DISTANT_PREVIOUS_GOVERNED_SESSION","session_gap_trading_sessions":5,"is_immediate_previous_completed_session":False,"comparison_fitness":"DEGRADED_MULTI_SESSION_GAP","comparison_reason_codes":["PREVIOUS_SESSION_REGISTRY_GAP"],"skipped_known_sessions":["2026-08-27","2026-08-28","2026-09-03","2026-09-04","2026-09-10"],"notice":"..."}
    brief=tmp_path/"next_session_decision_brief.json"
    brief.write_text(json.dumps({"artifact_identity":"next_session_decision_brief:abc123","comparison_metadata":comparison_metadata}),encoding="utf-8")
    result=publish(r,s,"2026-09-11",producer_checkpoint="abc",push=False,decision_brief=brief)
    assert result["package"]["lineage"]["comparison_metadata"]==comparison_metadata
    latest=json.loads((r/"LATEST.json").read_text())
    assert latest["comparison_metadata"]==comparison_metadata

def test_daily_integrated_decision_brief_is_optional_and_additive(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    without=build_package(s,"2026-08-28",producer_checkpoint="abc")
    assert "daily_integrated_decision_brief.json" not in without[0]
    assert "daily_integrated_decision_brief.json" not in without[1]["files"]
    assert "daily_integrated_decision_brief_identity" not in without[1]["lineage"]

def test_daily_integrated_decision_brief_included_when_supplied(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    brief=tmp_path/"daily_integrated_decision_brief.json"
    brief.write_text(json.dumps({"artifact_identity":"daily_integrated_decision_brief/v1:abc123","previous_qualified_session":"2026-08-27"}),encoding="utf-8")
    result=publish(r,s,"2026-08-28",producer_checkpoint="abc",push=False,daily_integrated_decision_brief=brief)
    assert (r/result["immutable_session_path"]/"daily_integrated_decision_brief.json").is_file()
    assert result["package"]["lineage"]["daily_integrated_decision_brief_identity"]=="daily_integrated_decision_brief/v1:abc123"
    assert result["package"]["lineage"]["daily_integrated_decision_brief_previous_qualified_session"]=="2026-08-27"
    latest=json.loads((r/"LATEST.json").read_text())
    assert latest["daily_integrated_decision_brief_sha256"]==result["package"]["files"]["daily_integrated_decision_brief.json"]

def test_local_only_makes_zero_git_mutation(tmp_path):
    """The exact defect this parameter exists to close: push=False alone still leaves two real
    commits in the handoff repo (see test_versioned_build... below); local_only=True must leave
    the repository's HEAD, working tree, and sessions/ directory completely untouched."""
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    head_before = subprocess.run(["git","-C",str(r),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
    status_before = subprocess.run(["git","-C",str(r),"status","--porcelain"],capture_output=True,text=True,check=True).stdout
    result = publish(r,s,"2026-08-28",producer_checkpoint="abc",local_only=True)
    assert result["status"] == "LOCAL_VALIDATED_NO_GIT_MUTATION"
    head_after = subprocess.run(["git","-C",str(r),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
    status_after = subprocess.run(["git","-C",str(r),"status","--porcelain"],capture_output=True,text=True,check=True).stdout
    assert head_after == head_before
    assert status_after == status_before
    assert not (r/"sessions").exists()
    assert not (r/"LATEST.json").exists()

def test_local_only_still_computes_the_real_publishable_identity(tmp_path):
    """local_only is genuine validation, not a stub: it must compute the exact same
    handoff_build_id/package hashes a real publish would, proving the package is actually
    publish-ready without ever publishing it."""
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    _files, direct_payload = build_package(s,"2026-08-28",producer_checkpoint="abc")
    local_result = publish(r,s,"2026-08-28",producer_checkpoint="abc",local_only=True)
    assert local_result["package"] == direct_payload
    real_result = publish(r,s,"2026-08-28",producer_checkpoint="abc",push=False)
    assert local_result["package"]["handoff_build_id"] == real_result["package"]["handoff_build_id"]
    assert local_result["immutable_session_path"] == real_result["immutable_session_path"]

def test_local_only_wins_even_when_push_defaults_true(tmp_path):
    """push defaults to True; a caller must not need to remember push=False on top of
    local_only=True for this to be genuinely zero-Git-mutation -- local_only alone is enough."""
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    head_before = subprocess.run(["git","-C",str(r),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
    result = publish(r,s,"2026-08-28",producer_checkpoint="abc",local_only=True,push=True)
    assert result["status"] == "LOCAL_VALIDATED_NO_GIT_MUTATION"
    head_after = subprocess.run(["git","-C",str(r),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
    assert head_after == head_before

def test_local_only_still_fails_closed_on_invalid_package(tmp_path):
    """local_only skips Git, never validation -- a genuinely broken source package must still
    raise, not be silently reported as LOCAL_VALIDATED."""
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    (s/"ai_research_session_bundle.json").write_text(json.dumps({"path":"D:\\private\\bundle"}),encoding="utf-8")
    with pytest.raises(HandoffPublicationError,match="ABSOLUTE_PATH"):
        publish(r,s,"2026-08-28",local_only=True)

def test_daily_integrated_decision_brief_alongside_decision_brief(tmp_path):
    """Both optional artifacts can be published together; each is independently identified."""
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    decision_brief=tmp_path/"next_session_decision_brief.json"; decision_brief.write_text(json.dumps({"artifact_identity":"next_session_decision_brief:abc"}),encoding="utf-8")
    daily_brief=tmp_path/"daily_integrated_decision_brief.json"; daily_brief.write_text(json.dumps({"artifact_identity":"daily_integrated_decision_brief/v1:xyz"}),encoding="utf-8")
    result=publish(r,s,"2026-08-28",producer_checkpoint="abc",push=False,decision_brief=decision_brief,daily_integrated_decision_brief=daily_brief)
    assert result["package"]["lineage"]["next_session_decision_brief_identity"]=="next_session_decision_brief:abc"
    assert result["package"]["lineage"]["daily_integrated_decision_brief_identity"]=="daily_integrated_decision_brief/v1:xyz"

def test_remote_verification_binds_latest_pointer_session_hashes_and_lineage(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    remote=tmp_path/"remote.git"; subprocess.run(["git","init","--bare","-q",str(remote)],check=True)
    git(r,"branch","-M","main"); git(r,"remote","add","origin",str(remote)); git(r,"push","-u","origin","main")
    result=publish(r,s,"2026-08-28",producer_checkpoint="abc",push=True)
    verified=verify_remote_publication(r,result)
    assert verified["status"]=="READY_FOR_AI"
    assert verified["latest_session"]=="2026-08-28"
    assert verified["remote_sha"]==result["handoff_commit"]


# =====================================================================================
# CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1 section 3 / section 10 item
# E: the AI handoff additively consumes the dedicated post-handoff presentation attestation --
# never mutating the sealed Producer `source` directory -- and exposes its identities/statuses.
# =====================================================================================

def _attestation(*, bound=True):
    projection = (
        {"status": "COLLECTED", "session": "2026-08-28", "lineage_status": "VERIFIED_AGAINST_SEALED_PRODUCER_WORKSPACE",
         "workspace_artifact_identity": "workspace:enriched"}
        if bound else {"status": "UNAVAILABLE", "session": "2026-08-28", "reason": "TEST"}
    )
    return {
        "contract_version": "post_handoff_presentation_attestation/v1", "session": "2026-08-28",
        "presentation_projection": projection,
        "sealed_producer_workspace_artifact_identity": "workspace:sealed",
        "signal_velocity": {"status": "COLLECTED", "artifact_identity": "velocity:1"},
        "current_foreign_flow_enrichment": {
            "status": "COMPLETE", "complete_count": 11, "requested_count": 11, "network_calls_made": 11,
        },
        "flow_price_divergence_shadow": {"status": "COLLECTED", "artifact_identity": "flow_price:1"},
        "post_handoff_prospective_decision_feedback": {"status": "COLLECTED", "artifact_identity": "feedback:1"},
    }


def test_build_package_is_unaffected_when_no_presentation_attestation_supplied(tmp_path):
    s, r = tmp_path / "source", tmp_path / "repo"; source(s); repo(r)
    files, payload = build_package(s, "2026-08-28", producer_checkpoint="abc")
    assert "post_handoff_presentation_state.json" not in files
    assert "post_handoff_presentation_state" not in payload["lineage"]


def test_build_package_adds_additive_presentation_state_without_touching_sealed_source(tmp_path):
    s, r = tmp_path / "source", tmp_path / "repo"; source(s); repo(r)
    before = {p.name: p.read_bytes() for p in s.iterdir()}
    files, payload = build_package(s, "2026-08-28", producer_checkpoint="abc", post_handoff_presentation=_attestation())
    assert {p.name: p.read_bytes() for p in s.iterdir()} == before  # sealed source untouched
    assert "post_handoff_presentation_state.json" in files
    assert isinstance(files["post_handoff_presentation_state.json"], (bytes, bytearray))
    lineage = payload["lineage"]["post_handoff_presentation_state"]
    assert lineage["status"] == "COLLECTED"
    assert lineage["workspace_artifact_identity"] == "workspace:enriched"
    assert lineage["sealed_producer_workspace_artifact_identity"] == "workspace:sealed"
    assert lineage["signal_velocity_status"] == "COLLECTED"
    assert lineage["current_foreign_flow_enrichment_status"] == "COMPLETE"
    assert lineage["flow_price_divergence_shadow_status"] == "COLLECTED"
    presentation = json.loads(files["post_handoff_presentation_state.json"].decode("utf-8"))
    assert presentation["current_foreign_flow_enrichment"]["status"] == "COMPLETE"
    assert presentation["current_foreign_flow_enrichment"]["complete_count"] == 11
    assert lineage["post_handoff_prospective_decision_feedback_status"] == "COLLECTED"


def test_build_package_publishes_legitimate_unavailable_presentation_state_not_fabricated(tmp_path):
    s, r = tmp_path / "source", tmp_path / "repo"; source(s); repo(r)
    _files, payload = build_package(s, "2026-08-28", producer_checkpoint="abc", post_handoff_presentation=_attestation(bound=False))
    assert payload["lineage"]["post_handoff_presentation_state"]["status"] == "UNAVAILABLE"
    assert payload["lineage"]["post_handoff_presentation_state"]["workspace_artifact_identity"] is None


def test_publish_writes_presentation_state_file_and_sealed_source_stays_unchanged(tmp_path):
    s, r = tmp_path / "source", tmp_path / "repo"; source(s); repo(r)
    before = {p.name: p.read_bytes() for p in s.iterdir()}
    result = publish(r, s, "2026-08-28", producer_checkpoint="abc", push=False, post_handoff_presentation=_attestation())
    target = r / result["immutable_session_path"]
    written = json.loads((target / "post_handoff_presentation_state.json").read_text(encoding="utf-8"))
    assert written["authority_boundary"] == "PRESENTATION_RESEARCH_OBSERVER_STATE_NOT_ANALYTICAL_DECISION_AUTHORITY"
    assert written["sealed_producer_workspace_artifact_identity"] == "workspace:sealed"
    assert written["post_handoff_presentation_workspace_artifact_identity"] == "workspace:enriched"
    assert written["signal_velocity"] == {"status": "COLLECTED", "identity": "velocity:1"}
    assert {p.name: p.read_bytes() for p in s.iterdir()} == before


def test_publish_no_op_replay_still_matches_with_presentation_state_present(tmp_path):
    s, r = tmp_path / "source", tmp_path / "repo"; source(s); repo(r)
    first = publish(r, s, "2026-08-28", producer_checkpoint="abc", push=False, post_handoff_presentation=_attestation())
    second = publish(r, s, "2026-08-28", producer_checkpoint="abc", push=False, post_handoff_presentation=_attestation())
    assert second["status"] == "NO_OP_ALREADY_PUBLISHED"
    assert second["package"]["handoff_build_id"] == first["package"]["handoff_build_id"]
