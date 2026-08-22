"""Produce deterministic AI-input packets; no model or network call is made."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evidence_bound_ai_research_human_review import build_ai_input_collection
from tools.run_evidence_gated_research_decision_workflow import run as decision_run


def run() -> dict:
    return build_ai_input_collection(decision_run())


if __name__ == "__main__":
    artifact = run()
    output = ROOT / "operations-review/evidence-bound-ai-research-human-review-v1-20260822/ai_input_collection_artifact.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])
