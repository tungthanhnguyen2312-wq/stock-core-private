"""Evaluate prospective case readiness without creating or backfilling cases."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from prospective_research_case_learning_ledger import case_readiness
from tools.run_evidence_bound_ai_research_human_review import run as ai_run
from tools.run_evidence_gated_research_decision_workflow import run as decision_run


def run() -> dict:
    return case_readiness(decision_run(), ai_run())


if __name__ == "__main__":
    artifact = run()
    output = ROOT / "operations-review/prospective-research-case-learning-ledger-v1-20260822/case_readiness_artifact.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])
