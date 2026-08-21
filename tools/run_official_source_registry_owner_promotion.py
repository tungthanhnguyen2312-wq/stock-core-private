"""Write the deterministic owner-approved issuer-route activation replay."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from official_source_registry_owner_promotion import build_artifact


OUTPUT = ROOT / "operations-review" / "official-source-registry-owner-promotion-v1-20260821" / "official_source_registry_owner_promotion_artifact.json"


def run(output: Path = OUTPUT) -> dict:
    artifact = build_artifact()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return artifact


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
