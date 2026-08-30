"""Fail-closed owner-command preflight; checks presence only, never secret values."""
from __future__ import annotations
import os, subprocess
from pathlib import Path

class PreflightError(ValueError): pass
def _fail(code: str): raise PreflightError(code)
def check(*, producer_root: Path, runtime_root: Path, transport_root: Path, replay_local: bool=False) -> dict:
    if not producer_root.is_dir() or not (producer_root/"daily_analysis_pipeline.py").is_file(): _fail("FAILED_PREFLIGHT_RUNTIME:PRODUCER_ROOT")
    if not runtime_root.is_dir(): _fail("FAILED_PREFLIGHT_RUNTIME:RUNTIME_ROOT")
    if not replay_local and not any(os.environ.get(k) for k in ("DNSE_USERNAME","DNSE_PASSWORD","DNSE_API_KEY","DNSE_TOKEN")): _fail("FAILED_PREFLIGHT_CREDENTIALS:CONFIGURATION_MISSING")
    lock=producer_root/"locks"/"daily.lock"
    if lock.exists(): _fail("FAILED_PREFLIGHT_LOCK:CONFLICTING_LOCK_PRESENT")
    if not transport_root.is_dir(): _fail("FAILED_PREFLIGHT_TRANSPORT:CHECKOUT_MISSING")
    git=subprocess.run(["git","-C",str(transport_root),"rev-parse","--is-inside-work-tree"],capture_output=True,text=True,encoding="utf-8")
    if git.returncode or git.stdout.strip()!="true": _fail("FAILED_PREFLIGHT_TRANSPORT:NOT_GIT_REPOSITORY")
    dirty=subprocess.run(["git","-C",str(transport_root),"status","--porcelain"],capture_output=True,text=True,encoding="utf-8")
    if dirty.stdout.strip(): _fail("FAILED_PREFLIGHT_TRANSPORT:DIRTY_CHECKOUT")
    return {"status":"PASS","roadmap":"PASS","runtime":"PASS","credentials":"PRESENT" if not replay_local else "REPLAY_NOT_REQUIRED","lock":"PASS","transport":"PASS"}
