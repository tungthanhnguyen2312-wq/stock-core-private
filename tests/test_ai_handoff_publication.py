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
