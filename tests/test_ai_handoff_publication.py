from __future__ import annotations
import json, subprocess
import pytest
from ai_handoff_publication import HandoffPublicationError, build_package, publish

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
