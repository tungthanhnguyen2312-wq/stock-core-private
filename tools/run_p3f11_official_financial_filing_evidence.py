"""Generate the deterministic P3-F11 review artifact from retained evidence only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from p3f11_official_financial_filing_evidence import execute

DEFAULT_OUTPUT = ROOT / "operations-review" / "p3f11-official-financial-filing-evidence-20260820" / "p3f11_official_financial_filing_evidence_artifact.json"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
args = parser.parse_args()
artifact = execute()
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(artifact["artifact_identity"])
