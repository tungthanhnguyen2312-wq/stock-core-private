"""Deterministic private-Git transport for already-authoritative daily AI artifacts."""
from __future__ import annotations
import hashlib, json, shutil, subprocess
from pathlib import Path
from typing import Any, Mapping

CONTRACT_VERSION = "stocklookup_ai_handoff_publication/v1"
REQUIRED = ("ai_research_session_bundle.json", "daily_opportunity_decision_queue_artifact.json", "ai_research_bundle_manifest.json")

class HandoffPublicationError(ValueError): pass
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _git(repo: Path, *args: str) -> str:
    result=subprocess.run(["git","-C",str(repo),*args],capture_output=True,text=True,encoding="utf-8")
    if result.returncode: raise HandoffPublicationError("GIT_"+args[0].upper()+":"+(result.stderr.strip() or result.stdout.strip()))
    return result.stdout.strip()
def _unsafe(value: Any) -> bool:
    if isinstance(value,str): return value.startswith(("C:\\","c:\\","/"))
    if isinstance(value,dict): return any(_unsafe(v) for v in value.values())
    if isinstance(value,list): return any(_unsafe(v) for v in value)
    return False
def build_package(source: Path, session: str, previous: Path|None=None) -> tuple[dict[str,Path],dict[str,Any]]:
    files={name:source/name for name in REQUIRED}
    if previous: files[f"previous_session_bundle_{previous.parent.parent.name}.json"]=previous
    for name,path in files.items():
        if not path.is_file(): raise HandoffPublicationError("HANDOFF_SOURCE_MISSING:"+name)
        if _unsafe(json.loads(path.read_text(encoding="utf-8"))): raise HandoffPublicationError("HANDOFF_ABSOLUTE_PATH_FORBIDDEN:"+name)
    hashes={name:sha(path) for name,path in files.items()}
    payload={"schema_version":CONTRACT_VERSION,"session":session,"status":"READY_FOR_AI","files":hashes}
    payload["package_sha256"]=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return files,payload
def publish(repo: Path, source: Path, session: str, *, previous: Path|None=None, producer_checkpoint: str="UNKNOWN", push: bool=True) -> dict[str,Any]:
    files,payload=build_package(source,session,previous)
    target=repo/"sessions"/session
    existing=target/"ai_research_bundle_manifest.json"
    if existing.exists():
        current={name:sha(target/name) for name in files if (target/name).is_file()}
        if current==payload["files"]: return {"status":"NO_OP_ALREADY_PUBLISHED","session":session,"package":payload}
        raise HandoffPublicationError("FAIL_CLOSED_SESSION_PUBLICATION_CONFLICT:"+session)
    target.mkdir(parents=True,exist_ok=False)
    for name,path in files.items(): shutil.copyfile(path,target/name)
    (target/"HANDOFF.md").write_text(f"# Stock Lookup AI handoff\n\nSession: {session}\n\nStatus: READY_FOR_AI\n",encoding="utf-8")
    latest={"schema_version":"stocklookup_ai_handoff_latest/v1","latest_session":session,"status":"READY_FOR_AI","session_path":f"sessions/{session}","producer_checkpoint":producer_checkpoint,"session_bundle_sha256":payload["files"]["ai_research_session_bundle.json"],"opportunity_artifact_sha256":payload["files"]["daily_opportunity_decision_queue_artifact.json"],"manifest_sha256":payload["files"]["ai_research_bundle_manifest.json"],"previous_session":previous.parent.parent.name if previous else None}
    (repo/"LATEST.json").write_text(json.dumps(latest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    (repo/"LATEST.md").write_text(f"# Latest Stock Lookup handoff\n\nSession: {session}\n\nStatus: READY_FOR_AI\n",encoding="utf-8")
    latest["handoff_commit"]="SELF_REFERENTIAL_COMMIT"
    (repo/"LATEST.json").write_text(json.dumps(latest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    _git(repo,"add","sessions", "LATEST.json", "LATEST.md"); _git(repo,"commit","-m",f"handoff: {session} READY_FOR_AI")
    commit=_git(repo,"rev-parse","HEAD")
    if push: _git(repo,"push")
    return {"status":"PUBLISHED_READY_FOR_AI","session":session,"handoff_commit":commit,"package":payload}
