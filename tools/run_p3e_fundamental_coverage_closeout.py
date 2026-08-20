"""Run P3-E fundamental coverage closeout deterministically."""
from __future__ import annotations
import json
from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from p3e_fundamental_coverage_closeout import build_p3e_closeout, classify_p3d_residual_gaps

P2 = repo_root / "operations-review/p2-closeout-financial-fact-panel-20260820/p2_closeout_financial_panel_artifact.json"
P3D = repo_root / "operations-review/p3d-residual-comparative-financial-evidence-20260820/p3d_residual_comparative_evidence_scaleout_artifact.json"
MANIFEST = repo_root / "config/promoted_fundamental_coverage_closeout_evidence.json"
OUTPUT = repo_root / "operations-review/p3e-fundamental-coverage-closeout-20260820"

def run_p3e_fundamental_coverage_closeout(output_dir: Path = OUTPUT) -> dict:
    p2, p3d, manifest = (json.loads(path.read_text(encoding="utf-8")) for path in (P2, P3D, MANIFEST))
    output_dir.mkdir(parents=True, exist_ok=True)
    taxonomy = classify_p3d_residual_gaps(p3d)
    (output_dir / "p3e_reconciled_gap_taxonomy.json").write_text(json.dumps(taxonomy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact = build_p3e_closeout(repo_root=repo_root, p2_artifact=p2, p3d_artifact=p3d, manifest=manifest)
    (output_dir / "p3e_fundamental_coverage_closeout_artifact.json").write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact

if __name__ == "__main__":
    print(run_p3e_fundamental_coverage_closeout()["artifact_identity"])
