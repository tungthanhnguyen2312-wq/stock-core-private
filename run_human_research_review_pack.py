"""Render an owner-facing review pack from retained daily research artifacts."""
from __future__ import annotations

import json
from pathlib import Path

from human_research_review_pack import build, markdown
from persistent_research_dossier import load_latest_versions
from prospective_research_learning import attribute, freeze
from research_question_tasking import load_latest_tasks
from run_prospective_research_learning import ROOT as REPO_ROOT

ROOT = REPO_ROOT
DOSSIER_ROOT = ROOT / "operations-review" / "persistent-research-dossier-v1-20260820"
TASK_ROOT = ROOT / "operations-review" / "research-question-tasking-v1-20260820"
OUTPUT = ROOT / "operations-review" / "human-research-review-pack-v1-20260820"


def run() -> dict:
    product = json.loads((ROOT / "operations-review/mva-daily-investment-research-20260820/"
                          "mva_daily_investment_research_artifact.json").read_text(encoding="utf-8"))
    analyst = json.loads((ROOT / "operations-review/ai-research-analyst-v1-20260820/"
                          "ai_research_analyst_artifact.json").read_text(encoding="utf-8"))
    snapshot = freeze(product, analyst)
    prospective = attribute(snapshot)
    prospective["snapshot_id"] = snapshot["snapshot_id"]
    return build(product=product, dossiers=load_latest_versions(DOSSIER_ROOT), tasks=load_latest_tasks(TASK_ROOT), prospective=prospective)


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifact = run()
    (OUTPUT / "human_research_review_pack_artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT / "human_research_review_pack.md").write_text(markdown(artifact), encoding="utf-8")
    print(artifact["artifact_identity"])
