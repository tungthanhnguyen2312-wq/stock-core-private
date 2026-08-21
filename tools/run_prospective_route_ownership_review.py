"""Write the deterministic prospective route owner-review artifact."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from prospective_route_ownership_review import execute


OUTPUT = (
    ROOT / "operations-review" / "prospective-route-ownership-review-v1-20260821"
    / "prospective_route_ownership_review_artifact.json"
)


def run(output: Path = OUTPUT) -> dict:
    artifact = execute()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return artifact


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
