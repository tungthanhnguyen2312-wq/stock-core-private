"""Resolve the mutable dashboard runtime directory for local producers."""

from __future__ import annotations

import os
import json
from pathlib import Path


RUNTIME_ROOT_ENV = "STOCK_LOOKUP_RUNTIME_ROOT"
WORKSPACE_PROFILE_ENV = "STOCK_LOOKUP_WORKSPACE_PROFILE"
ROLE_NAMES = {"producer": "stock-core-private", "consumer": "ai-core-private",
              "dashboard": "market-dashboard", "runtime": "dashboard-runtime",
              "handoff": "stocklookup-ai-handoffs", "logs": "run-logs",
              "retained": "retained-evidence"}


def workspace_profile(*, observer=None) -> dict | None:
    """Explicit profile only. Every hot path is bound to its observed volume.

    Cold availability is dependency scoped; loading a hot-only profile never probes W.
    A common parent deliberately preserves existing Consumer/Dashboard sibling imports.
    """
    selected = os.environ.get(WORKSPACE_PROFILE_ENV, "").strip()
    if not selected:
        return None
    from retained_evidence_catalog import Refused, native_volume, require
    observer = observer or native_volume
    try:
        profile = json.loads(Path(selected).read_bytes())
        require(profile.get("schema") == "stocklookup_workspace/v1", "workspace schema invalid")
        parent = Path(profile["parent"])
        require(parent.is_absolute() and parent.is_dir(), "workspace parent missing/relative")
        require(all(not node.is_symlink() and not node.is_junction() for node in (parent, *parent.parents)),
                "workspace parent redirected")
        roles = profile["roles"]
        require(set(roles) == set(ROLE_NAMES), "workspace roles incomplete")
        require(observer(parent) == profile["hot_volume"] and profile["hot_volume"].get("healthy") is True,
                "workspace volume wrong/unavailable")
        if "capacity" in profile:
            workload = profile["capacity"]["workload"]
            workload_path = Path(workload["path"])
            require(workload_path.is_absolute() and workload_path.resolve() == parent.resolve()
                    and workload["volume"] == profile["hot_volume"],
                    "workspace workload capacity binding mismatch")
        paths = {}
        for role, name in ROLE_NAMES.items():
            path = Path(roles[role])
            require(path.is_absolute() and path.resolve() == (parent / name).resolve(),
                    "workspace sibling layout mismatch:" + role)
            require(path.is_dir() and not path.is_symlink() and not path.is_junction(),
                    "workspace role missing/redirected:" + role)
            paths[role] = path.resolve()
        require(len(set(paths.values())) == len(paths), "workspace role collision")
        return {**profile, "paths": paths}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Refused("WORKSPACE_PROFILE_UNQUALIFIED:" + str(exc)) from exc


def workspace_path(role: str, legacy: str | os.PathLike[str], *, observer=None) -> Path:
    if role not in ROLE_NAMES:
        raise ValueError("unknown workspace role")
    profile = workspace_profile(observer=observer)
    return profile["paths"][role] if profile else Path(legacy).expanduser().resolve()


def workspace_environment(*, observer=None) -> dict[str, str]:
    """Qualified bindings for the existing execution-root contract; no process launch."""
    profile = workspace_profile(observer=observer)
    if not profile:
        return {}
    paths = profile["paths"]
    bindings = {RUNTIME_ROOT_ENV: str(paths["runtime"]),
                "STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT": str(paths["retained"]),
                "STOCK_LOOKUP_OPERATION_OUTPUT_ROOT": str(paths["retained"]),
                "STOCK_LOOKUP_EVIDENCE_CATALOG_ROOT": str(paths["retained"])}
    for name, value in bindings.items():
        configured = os.environ.get(name)
        if configured and Path(configured).resolve() != Path(value):
            raise ValueError("WORKSPACE_ENVIRONMENT_CONFLICT:" + name)
    return bindings


def runtime_root(default: str | os.PathLike[str] | None = None) -> Path:
    """Use the configured runtime root, or preserve a caller's legacy default."""
    configured = os.getenv(RUNTIME_ROOT_ENV, "").strip()
    fallback = default if default is not None else os.getcwd()
    profile = workspace_profile()
    if profile:
        target = profile["paths"]["runtime"]
        if configured and Path(configured).resolve() != target:
            raise ValueError("RUNTIME_ROOT_PROFILE_CONFLICT")
        return target
    return Path(configured or fallback).expanduser().resolve()
