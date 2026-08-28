"""Offline materialization of the action-instrumentation research artifact."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import action_instrumentation as instrumentation


OUTPUT = ROOT / "operations-review" / "action-instrumentation-and-invalidation-precision-v1-20260828" / "artifact.json"


def run(output: Path = OUTPUT) -> dict:
    artifact = instrumentation.execute()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


if __name__ == "__main__":
    run()
