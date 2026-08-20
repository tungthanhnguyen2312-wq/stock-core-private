"""Write the deterministic, read-only P3-F12 artifact."""
from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from p3f12_value_level_financial_evidence import execute
output = ROOT / "operations-review" / "p3f12-value-level-financial-evidence-20260820" / "p3f12_value_level_financial_evidence_artifact.json"
output.parent.mkdir(parents=True, exist_ok=True)
artifact = execute(); output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(artifact["artifact_identity"])
