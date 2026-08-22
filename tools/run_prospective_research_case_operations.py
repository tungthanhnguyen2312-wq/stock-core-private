"""Build the deterministic real prospective research operating manifest."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analyst_research_workbench import build_current_workbench
from prospective_research_case_operations import build_operating_manifest


def run() -> dict:
    return build_operating_manifest(build_current_workbench())


if __name__ == "__main__":
    artifact = run()
    output = ROOT / "operations-review/prospective-research-case-operations-v1-20260822/operating_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["manifest_identity"])
