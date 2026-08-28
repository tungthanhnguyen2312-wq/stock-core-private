"""Offline materialization of the deterministic research-case artifact."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from thesis_catalyst_downside_research_cases import ROOT, execute


OUTPUT = ROOT / "operations-review" / "thesis-catalyst-downside-and-dual-invalidation-v1-20260828" / "artifact.json"


def run(output: Path = OUTPUT) -> dict:
    artifact = execute()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


if __name__ == "__main__":
    run()
