"""Deterministic private-Git transport for already-authoritative daily AI artifacts."""
from __future__ import annotations
import hashlib, json, re, shutil, subprocess
from pathlib import Path
from typing import Any, Mapping

CONTRACT_VERSION = "stocklookup_ai_handoff_publication/v2"
REQUIRED = ("ai_research_session_bundle.json", "daily_opportunity_decision_queue_artifact.json", "ai_research_bundle_manifest.json")
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]{2}|/)")

class HandoffPublicationError(ValueError): pass
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _git(repo: Path, *args: str) -> str:
    result=subprocess.run(["git","-C",str(repo),*args],capture_output=True,text=True,encoding="utf-8")
    if result.returncode: raise HandoffPublicationError("GIT_"+args[0].upper()+":"+(result.stderr.strip() or result.stdout.strip()))
    return result.stdout.strip()
def _unsafe(value: Any) -> bool:
    if isinstance(value,str): return bool(_ABSOLUTE_PATH.match(value))
    if isinstance(value,dict): return any(_unsafe(v) for v in value.values())
    if isinstance(value,list): return any(_unsafe(v) for v in value)
    return False
def _manifest_lineage(source: Path, producer_checkpoint: str) -> dict[str, Any]:
    manifest=json.loads((source/"ai_research_bundle_manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, Mapping): raise HandoffPublicationError("HANDOFF_MANIFEST_NOT_OBJECT")
    return {"producer_checkpoint":producer_checkpoint,"producer_head":manifest.get("producer_head"),"operation_identity":manifest.get("operation_identity"),"daily_product_identity":manifest.get("daily_product_identity")}
def _identity(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",", ":")).encode("utf-8")).hexdigest()
def build_package(source: Path, session: str, previous: Path|None=None, *, producer_checkpoint: str="UNKNOWN", decision_brief: Path|None=None) -> tuple[dict[str,Path],dict[str,Any]]:
    files={name:source/name for name in REQUIRED}
    if previous: files[f"previous_session_bundle_{previous.parent.parent.name}.json"]=previous
    # next_session_decision_brief.json is a pure package-local derived projection (see
    # next_session_decision_brief.py) -- optional and additive, exactly like `previous`, so a
    # caller/test that never supplies one sees no behavior change at all.
    if decision_brief: files["next_session_decision_brief.json"]=decision_brief
    parsed: dict[str, Any] = {}
    for name,path in files.items():
        if not path.is_file(): raise HandoffPublicationError("HANDOFF_SOURCE_MISSING:"+name)
        parsed[name]=json.loads(path.read_text(encoding="utf-8"))
        if _unsafe(parsed[name]): raise HandoffPublicationError("HANDOFF_ABSOLUTE_PATH_FORBIDDEN:"+name)
    hashes={name:sha(path) for name,path in files.items()}
    package_identity=_identity({"session":session,"files":hashes})
    lineage=_manifest_lineage(source,producer_checkpoint)
    if decision_brief: lineage["next_session_decision_brief_identity"]=parsed["next_session_decision_brief.json"].get("artifact_identity")
    handoff_build_id="handoff_build_"+_identity({"session":session,"package_sha256":package_identity,"lineage":lineage})
    payload={"schema_version":CONTRACT_VERSION,"session":session,"status":"READY_FOR_AI","files":hashes,"package_sha256":package_identity,"lineage":lineage,"handoff_build_id":handoff_build_id}
    return files,payload
def _latest_payload(session: str, payload: Mapping[str, Any], *, immutable_session_path: str, handoff_commit: str, previous: Path|None) -> dict[str, Any]:
    latest={"schema_version":"stocklookup_ai_handoff_latest/v2","latest_session":session,"status":"READY_FOR_AI","handoff_build_id":payload["handoff_build_id"],"immutable_session_path":immutable_session_path,"handoff_commit":handoff_commit,"producer_checkpoint":payload["lineage"]["producer_checkpoint"],"producer_lineage":payload["lineage"],"session_bundle_sha256":payload["files"]["ai_research_session_bundle.json"],"opportunity_artifact_sha256":payload["files"]["daily_opportunity_decision_queue_artifact.json"],"manifest_sha256":payload["files"]["ai_research_bundle_manifest.json"],"previous_session":previous.parent.parent.name if previous else None}
    if "next_session_decision_brief.json" in payload["files"]: latest["decision_brief_sha256"]=payload["files"]["next_session_decision_brief.json"]
    return latest
def publish(repo: Path, source: Path, session: str, *, previous: Path|None=None, producer_checkpoint: str="UNKNOWN", push: bool=True, decision_brief: Path|None=None) -> dict[str,Any]:
    files,payload=build_package(source,session,previous,producer_checkpoint=producer_checkpoint,decision_brief=decision_brief)
    target=repo/"sessions"/session/"builds"/payload["handoff_build_id"]
    if target.exists():
        current={name:sha(target/name) for name in files if (target/name).is_file()}
        if current==payload["files"]: return {"status":"NO_OP_ALREADY_PUBLISHED","session":session,"package":payload,"immutable_session_path":target.relative_to(repo).as_posix()}
        raise HandoffPublicationError("FAIL_CLOSED_HANDOFF_BUILD_CONFLICT:"+payload["handoff_build_id"])
    target.mkdir(parents=True,exist_ok=False)
    for name,path in files.items(): shutil.copyfile(path,target/name)
    (target/"HANDOFF.md").write_text(f"# Stock Lookup AI handoff\n\nSession: {session}\n\nBuild: {payload['handoff_build_id']}\n\nStatus: READY_FOR_AI\n",encoding="utf-8")
    immutable_session_path=target.relative_to(repo).as_posix()
    _git(repo,"add",immutable_session_path)
    _git(repo,"commit","-m",f"handoff: {session} build {payload['handoff_build_id']}")
    build_commit=_git(repo,"rev-parse","HEAD")
    latest=_latest_payload(session,payload,immutable_session_path=immutable_session_path,handoff_commit=build_commit,previous=previous)
    (repo/"LATEST.json").write_text(json.dumps(latest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    (repo/"LATEST.md").write_text(f"# Latest Stock Lookup handoff\n\nSession: {session}\n\nBuild: {payload['handoff_build_id']}\n\nStatus: READY_FOR_AI\n",encoding="utf-8")
    _git(repo,"add","LATEST.json","LATEST.md")
    _git(repo,"commit","-m",f"handoff: {session} latest {payload['handoff_build_id']}")
    pointer_commit=_git(repo,"rev-parse","HEAD")
    if push: _git(repo,"push")
    return {"status":"PUBLISHED_READY_FOR_AI","session":session,"handoff_commit":pointer_commit,"immutable_handoff_commit":build_commit,"immutable_session_path":immutable_session_path,"package":payload}
