"""Generate the P3-B fundamental-only research-readiness artifact from P2 closeout."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from fundamental_research_readiness import build_fundamental_research_artifact

DEFAULT_INPUT = repo_root / "operations-review" / "p2-closeout-financial-fact-panel-20260820" / "p2_closeout_financial_panel_artifact.json"
DEFAULT_OUTPUT = repo_root / "operations-review" / "p3b-fundamental-research-readiness-20260820" / "p3b_fundamental_research_readiness_artifact.json"


def run_p3b_fundamental_research_readiness(input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Read immutable P2 artifact, calculate P3-B output, and write only its review artifact."""
    source = json.loads(input_path.read_text(encoding="utf-8"))
    artifact = build_fundamental_research_artifact(source)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


if __name__ == "__main__":
    result = run_p3b_fundamental_research_readiness()
    print(result["artifact_identity"])
