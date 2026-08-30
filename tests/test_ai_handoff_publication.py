from __future__ import annotations
import json, subprocess
import pytest
from ai_handoff_publication import HandoffPublicationError, publish

def git(path,*args): subprocess.run(["git","-C",str(path),*args],check=True,capture_output=True)
def source(path):
    path.mkdir();
    for name in ("ai_research_session_bundle.json","daily_opportunity_decision_queue_artifact.json","ai_research_bundle_manifest.json"):
        (path/name).write_text(json.dumps({"artifact_identity":name}),encoding="utf-8")
def repo(path):
    path.mkdir(); git(path,"init","-q"); git(path,"config","user.email","test@example.com"); git(path,"config","user.name","Test"); (path/"README.md").write_text("x\n"); git(path,"add","README.md"); git(path,"commit","-qm","init")
def test_publish_noop_conflict_and_latest(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    first=publish(r,s,"2026-08-28",producer_checkpoint="abc",push=False)
    assert first["status"]=="PUBLISHED_READY_FOR_AI"
    assert json.loads((r/"LATEST.json").read_text())["latest_session"]=="2026-08-28"
    assert publish(r,s,"2026-08-28",push=False)["status"]=="NO_OP_ALREADY_PUBLISHED"
    (s/"ai_research_session_bundle.json").write_text('{"changed":true}',encoding="utf-8")
    with pytest.raises(HandoffPublicationError,match="PUBLICATION_CONFLICT"): publish(r,s,"2026-08-28",push=False)
