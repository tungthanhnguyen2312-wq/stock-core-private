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
def _git_bytes(repo: Path, *args: str) -> bytes:
    result=subprocess.run(["git","-C",str(repo),*args],capture_output=True,check=False)
    if result.returncode:
        raise HandoffPublicationError("GIT_"+args[0].upper()+":"+result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout
def _unsafe(value: Any) -> bool:
    if isinstance(value,str): return bool(_ABSOLUTE_PATH.match(value))
    if isinstance(value,dict): return any(_unsafe(v) for v in value.values())
    if isinstance(value,list): return any(_unsafe(v) for v in value)
    return False
def _manifest_lineage(source: Path, producer_checkpoint: str) -> dict[str, Any]:
    manifest=json.loads((source/"ai_research_bundle_manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, Mapping): raise HandoffPublicationError("HANDOFF_MANIFEST_NOT_OBJECT")
    res = {"producer_checkpoint":producer_checkpoint,"producer_head":manifest.get("producer_head"),"operation_identity":manifest.get("operation_identity"),"daily_product_identity":manifest.get("daily_product_identity")}
    if manifest.get("integrated_investment_decision_product_identity"):
        res["integrated_investment_decision_product_identity"] = manifest.get("integrated_investment_decision_product_identity")
    return res
def _financial_lineage(parsed: Mapping[str, Any]) -> str | None:
    """Validate the optional compact V2 identity chain without publishing its full replay."""
    primary = parsed.get("ai_research_session_bundle.json") or {}
    manifest = parsed.get("ai_research_bundle_manifest.json") or {}
    financial = primary.get("financial_analysis") if isinstance(primary, Mapping) else None
    if not isinstance(financial, Mapping): return None
    source_identity = financial.get("source_context_identity")
    if source_identity is None: return None
    summary = financial.get("market_summary") or {}
    if (not isinstance(summary, Mapping) or summary.get("source_context_identity") != source_identity
            or manifest.get("financial_analysis_source_context_identity") != source_identity):
        raise HandoffPublicationError("HANDOFF_FINANCIAL_ANALYSIS_IDENTITY_CHAIN_INVALID")
    return str(source_identity)
def _identity(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",", ":")).encode("utf-8")).hexdigest()
def _presentation_observer_payload(session: str, attestation: Mapping[str, Any]) -> dict[str, Any]:
    """Additive, presentation/research-observer state only -- never analytical decision
    authority. Derived entirely from the dedicated ``post_handoff_presentation_attestation``
    artifact; never reads or mutates sealed Producer evidence. See
    CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1 section 3. A legitimately
    unavailable observer is published as an explicit UNAVAILABLE status here, never fabricated."""
    projection = attestation.get("presentation_projection") or {}
    velocity = attestation.get("signal_velocity") or {}
    foreign_flow = attestation.get("current_foreign_flow_enrichment") or {}
    flow_price = attestation.get("flow_price_divergence_shadow") or {}
    feedback = attestation.get("post_handoff_prospective_decision_feedback") or {}
    return {
        "schema_version": "post_handoff_presentation_state/v1",
        "authority_boundary": "PRESENTATION_RESEARCH_OBSERVER_STATE_NOT_ANALYTICAL_DECISION_AUTHORITY",
        "session": session,
        "sealed_producer_workspace_artifact_identity": attestation.get("sealed_producer_workspace_artifact_identity"),
        "post_handoff_presentation_status": projection.get("status"),
        "post_handoff_presentation_workspace_artifact_identity": projection.get("workspace_artifact_identity"),
        "post_handoff_presentation_lineage_status": projection.get("lineage_status"),
        "signal_velocity": {"status": velocity.get("status"), "identity": velocity.get("artifact_identity")},
        "current_foreign_flow_enrichment": {
            "status": foreign_flow.get("status"),
            "complete_count": foreign_flow.get("complete_count"),
            "requested_count": foreign_flow.get("requested_count"),
            "network_calls_made": foreign_flow.get("network_calls_made"),
            "reason": foreign_flow.get("reason"),
        },
        "flow_price_divergence_shadow": {"status": flow_price.get("status"), "identity": flow_price.get("artifact_identity")},
        "post_handoff_prospective_decision_feedback": {"status": feedback.get("status"), "identity": feedback.get("artifact_identity")},
    }
def build_package(source: Path, session: str, previous: Path|None=None, *, producer_checkpoint: str="UNKNOWN", decision_brief: Path|None=None, daily_integrated_decision_brief: Path|None=None, post_handoff_presentation: Mapping[str, Any]|None=None) -> tuple[dict[str,Any],dict[str,Any]]:
    files: dict[str, Any] = {name: source / name for name in REQUIRED}
    if previous: files[f"previous_session_bundle_{previous.parent.parent.name}.json"]=previous
    # next_session_decision_brief.json is a pure package-local derived projection (see
    # next_session_decision_brief.py) -- optional and additive, exactly like `previous`, so a
    # caller/test that never supplies one sees no behavior change at all.
    if decision_brief: files["next_session_decision_brief.json"]=decision_brief
    # daily_integrated_decision_brief.json (see daily_integrated_decision_brief.py) is the compact
    # AI-facing daily product -- optional and additive on the exact same pattern as decision_brief,
    # so ChatGPT can answer the owner's 11-watchlist review from the published handoff directly.
    if daily_integrated_decision_brief: files["daily_integrated_decision_brief.json"]=daily_integrated_decision_brief
    # post_handoff_presentation_state.json is generated in-memory (never read from or written
    # into the sealed Producer `source` directory) -- `files` may hold `bytes` here instead of a
    # `Path`, handled below and in `publish()`.
    if post_handoff_presentation is not None:
        files["post_handoff_presentation_state.json"] = (
            json.dumps(_presentation_observer_payload(session, post_handoff_presentation),
                       ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
    parsed: dict[str, Any] = {}
    for name,entry in files.items():
        if isinstance(entry, (bytes, bytearray)):
            parsed[name] = json.loads(entry.decode("utf-8"))
        else:
            if not entry.is_file(): raise HandoffPublicationError("HANDOFF_SOURCE_MISSING:"+name)
            parsed[name]=json.loads(entry.read_text(encoding="utf-8"))
        if _unsafe(parsed[name]): raise HandoffPublicationError("HANDOFF_ABSOLUTE_PATH_FORBIDDEN:"+name)
    hashes={name:(hashlib.sha256(entry).hexdigest() if isinstance(entry, (bytes, bytearray)) else sha(entry)) for name,entry in files.items()}
    package_identity=_identity({"session":session,"files":hashes})
    lineage=_manifest_lineage(source,producer_checkpoint)
    financial_source_identity = _financial_lineage(parsed)
    if financial_source_identity is not None: lineage["financial_analysis_source_context_identity"] = financial_source_identity
    if decision_brief:
        lineage["next_session_decision_brief_identity"]=parsed["next_session_decision_brief.json"].get("artifact_identity")
        lineage["comparison_metadata"]=parsed["next_session_decision_brief.json"].get("comparison_metadata")
    if daily_integrated_decision_brief:
        brief_parsed=parsed["daily_integrated_decision_brief.json"]
        lineage["daily_integrated_decision_brief_identity"]=brief_parsed.get("artifact_identity")
        lineage["daily_integrated_decision_brief_previous_qualified_session"]=brief_parsed.get("previous_qualified_session")
    if post_handoff_presentation is not None:
        presentation_parsed = parsed["post_handoff_presentation_state.json"]
        lineage["post_handoff_presentation_state"] = {
            "status": presentation_parsed.get("post_handoff_presentation_status"),
            "workspace_artifact_identity": presentation_parsed.get("post_handoff_presentation_workspace_artifact_identity"),
            "sealed_producer_workspace_artifact_identity": presentation_parsed.get("sealed_producer_workspace_artifact_identity"),
            "signal_velocity_status": (presentation_parsed.get("signal_velocity") or {}).get("status"),
            "current_foreign_flow_enrichment_status": (presentation_parsed.get("current_foreign_flow_enrichment") or {}).get("status"),
            "flow_price_divergence_shadow_status": (presentation_parsed.get("flow_price_divergence_shadow") or {}).get("status"),
            "post_handoff_prospective_decision_feedback_status": (presentation_parsed.get("post_handoff_prospective_decision_feedback") or {}).get("status"),
        }
    handoff_build_id="handoff_build_"+_identity({"session":session,"package_sha256":package_identity,"lineage":lineage})
    payload={"schema_version":CONTRACT_VERSION,"session":session,"status":"READY_FOR_AI","files":hashes,"package_sha256":package_identity,"lineage":lineage,"handoff_build_id":handoff_build_id}
    return files,payload
def _latest_payload(session: str, payload: Mapping[str, Any], *, immutable_session_path: str, handoff_commit: str, previous: Path|None) -> dict[str, Any]:
    latest={"schema_version":"stocklookup_ai_handoff_latest/v2","latest_session":session,"status":"READY_FOR_AI","handoff_build_id":payload["handoff_build_id"],"immutable_session_path":immutable_session_path,"handoff_commit":handoff_commit,"producer_checkpoint":payload["lineage"]["producer_checkpoint"],"producer_lineage":payload["lineage"],"session_bundle_sha256":payload["files"]["ai_research_session_bundle.json"],"opportunity_artifact_sha256":payload["files"]["daily_opportunity_decision_queue_artifact.json"],"manifest_sha256":payload["files"]["ai_research_bundle_manifest.json"],"previous_session":previous.parent.parent.name if previous else None}
    if "next_session_decision_brief.json" in payload["files"]:
        latest["decision_brief_sha256"]=payload["files"]["next_session_decision_brief.json"]
        latest["comparison_metadata"]=payload["lineage"].get("comparison_metadata")
    if "daily_integrated_decision_brief.json" in payload["files"]: latest["daily_integrated_decision_brief_sha256"]=payload["files"]["daily_integrated_decision_brief.json"]
    return latest
def publish(repo: Path, source: Path, session: str, *, previous: Path|None=None, producer_checkpoint: str="UNKNOWN", push: bool=True, local_only: bool=False, decision_brief: Path|None=None, daily_integrated_decision_brief: Path|None=None, post_handoff_presentation: Mapping[str, Any]|None=None) -> dict[str,Any]:
    """``local_only=True`` builds and validates the package (proving it is genuinely
    publishable -- every required file present, every hash computed, the manifest lineage
    chain checked) but returns before touching ``repo`` at all: no ``mkdir``, no file copy, no
    ``git`` call of any kind, not even a commit. This is distinct from ``push=False``, which
    still performs two real local commits (see the module docstring incident this parameter
    exists to close) -- ``local_only`` is the genuine zero-Git-mutation contract. ``local_only``
    always takes precedence over ``push`` -- including ``push``'s own default of ``True`` -- so
    a caller never needs to remember to also pass ``push=False``; there is exactly one way to
    ask for zero Git mutation, not two flags that must agree."""
    files,payload=build_package(source,session,previous,producer_checkpoint=producer_checkpoint,decision_brief=decision_brief,daily_integrated_decision_brief=daily_integrated_decision_brief,post_handoff_presentation=post_handoff_presentation)
    target=repo/"sessions"/session/"builds"/payload["handoff_build_id"]
    if local_only:
        return {"status":"LOCAL_VALIDATED_NO_GIT_MUTATION","session":session,"package":payload,"immutable_session_path":target.relative_to(repo).as_posix()}
    if target.exists():
        current={name:sha(target/name) for name in files if (target/name).is_file()}
        if current==payload["files"]:
            latest_path = repo / "LATEST.json"
            latest = json.loads(latest_path.read_text(encoding="utf-8")) if latest_path.is_file() else {}
            return {"status":"NO_OP_ALREADY_PUBLISHED","session":session,"package":payload,
                    "immutable_session_path":target.relative_to(repo).as_posix(),
                    "handoff_commit":latest.get("handoff_commit"),
                    "immutable_handoff_commit":latest.get("handoff_commit")}
        raise HandoffPublicationError("FAIL_CLOSED_HANDOFF_BUILD_CONFLICT:"+payload["handoff_build_id"])
    target.mkdir(parents=True,exist_ok=False)
    for name,entry in files.items():
        if isinstance(entry, (bytes, bytearray)): (target/name).write_bytes(entry)
        else: shutil.copyfile(entry,target/name)
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


def verify_remote_publication(repo: Path, published: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the handoff from ``origin/main``, never just the working tree."""
    _git(repo, "fetch", "origin")
    remote_sha = _git(repo, "rev-parse", "origin/main")
    expected_commit = str(published.get("handoff_commit") or "")
    if expected_commit and remote_sha != expected_commit:
        raise HandoffPublicationError(f"REMOTE_HANDOFF_SHA_MISMATCH:{expected_commit}:{remote_sha}")
    try:
        latest = json.loads(_git(repo, "show", "origin/main:LATEST.json"))
    except (json.JSONDecodeError, HandoffPublicationError) as exc:
        raise HandoffPublicationError("REMOTE_LATEST_JSON_INVALID") from exc
    package = published.get("package") or {}
    session = str(published.get("session") or "")
    path = str(published.get("immutable_session_path") or "")
    if (latest.get("status") != "READY_FOR_AI" or latest.get("latest_session") != session
            or latest.get("immutable_session_path") != path
            or latest.get("handoff_build_id") != package.get("handoff_build_id")):
        raise HandoffPublicationError("REMOTE_LATEST_POINTER_MISMATCH")
    names = set(_git(repo, "ls-tree", "-r", "--name-only", "origin/main", path).splitlines())
    expected_files = set((package.get("files") or {}).keys())
    missing = sorted(f"{path}/{name}" for name in expected_files if f"{path}/{name}" not in names)
    if missing:
        raise HandoffPublicationError("REMOTE_IMMUTABLE_FILES_MISSING:" + ",".join(missing))
    for name, expected_hash in (package.get("files") or {}).items():
        remote_name = f"{path}/{name}"
        # Resolve the blob first: Windows Git treats a long ``rev:path`` argument to
        # ``show`` as a filesystem path, while object IDs are platform-neutral.
        tree = _git(repo, "ls-tree", "origin/main", "--", remote_name)
        fields = tree.split("\t", 1)[0].split()
        if len(fields) < 3:
            raise HandoffPublicationError("REMOTE_IMMUTABLE_BLOB_MISSING:" + name)
        data = _git_bytes(repo, "cat-file", "blob", fields[2])
        if hashlib.sha256(data).hexdigest() != expected_hash:
            raise HandoffPublicationError("REMOTE_FILE_HASH_MISMATCH:" + name)
    if latest.get("producer_lineage") != package.get("lineage"):
        raise HandoffPublicationError("REMOTE_LINEAGE_MISMATCH")
    return {"status": "READY_FOR_AI", "latest_session": session,
            "latest_pointer": path, "remote_sha": remote_sha}
