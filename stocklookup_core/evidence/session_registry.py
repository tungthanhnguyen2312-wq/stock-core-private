"""Explicit read-only Daily input-registry loading; no orchestration or discovery."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Mapping


def load_registry(root: Path, registry_path: Path | None = None) -> Mapping[str, Any]:
    path = registry_path or root / "config" / "daily_research_session_input_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("contract_version") != "daily_research_session_input_registry/v1":
        raise ValueError("SESSION_INPUT_REGISTRY_CONTRACT_INVALID")
    return registry
