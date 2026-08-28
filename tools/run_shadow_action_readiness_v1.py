"""Offline materialization for the experiment-only shadow action-readiness artifact."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import shadow_action_readiness as shadow


OUTPUT = ROOT / "operations-review" / "shadow-action-readiness-v1-20260828" / "artifact.json"


def run(output: Path = OUTPUT) -> dict:
    artifact = shadow.execute()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


if __name__ == "__main__":
    run()
