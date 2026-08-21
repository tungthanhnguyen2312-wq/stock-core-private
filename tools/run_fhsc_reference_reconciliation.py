"""Write the offline FHSC shadow-reference reconciliation artifact."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from provider_reference_reconciliation import build_offline_artifact


OUTPUT = ROOT / "operations-review" / "fhsc-reference-reconciliation-foundation-v1-20260821" / "fhsc_reference_reconciliation_artifact.json"


def run(output: Path = OUTPUT) -> dict:
    artifact = build_offline_artifact()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return artifact


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
