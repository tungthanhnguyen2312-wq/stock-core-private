"""Run the P3-D residual comparative financial evidence closeout deterministically."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from p3d_residual_comparative_financial_evidence import build_p3d_closeout, build_reconciled_residual_gap_inventory

P2_INPUT = repo_root / "operations-review" / "p2-closeout-financial-fact-panel-20260820" / "p2_closeout_financial_panel_artifact.json"
P3C_INPUT = repo_root / "operations-review" / "p3c-comparative-financial-evidence-20260820" / "p3c_comparative_evidence_scaleout_artifact.json"
MANIFEST = repo_root / "config" / "promoted_residual_comparative_financial_evidence.json"
OUTPUT_DIR = repo_root / "operations-review" / "p3d-residual-comparative-financial-evidence-20260820"


def run_p3d_residual_comparative_financial_evidence(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    p2 = json.loads(P2_INPUT.read_text(encoding="utf-8"))
    p3c = json.loads(P3C_INPUT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    starting = build_reconciled_residual_gap_inventory(p3c)
    (output_dir / "p3d_reconciled_starting_residual_gap_inventory.json").write_text(json.dumps(starting, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact = build_p3d_closeout(repo_root=repo_root, p2_artifact=p2, p3c_artifact=p3c, manifest=manifest)
    (output_dir / "p3d_residual_comparative_evidence_scaleout_artifact.json").write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


if __name__ == "__main__":
    result = run_p3d_residual_comparative_financial_evidence()
    print(result["artifact_identity"])
