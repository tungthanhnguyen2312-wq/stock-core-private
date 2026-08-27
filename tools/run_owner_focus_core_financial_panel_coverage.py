"""Materialize the deterministic owner-focus coverage artifact from retained evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from owner_focus_core_financial_panel_coverage import execute


OUTPUT = ROOT / "operations-review" / "owner-focus-core-financial-panel-coverage-v1-20260827" / "artifact.json"


def main() -> int:
    artifact = execute()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact_identity": artifact["artifact_identity"], "residual_checks": artifact["residual_checks"], "next_evidence_target": artifact["next_milestone_recommendation"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
