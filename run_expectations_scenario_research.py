"""Run retained-evidence scenario research and compact Review Pack overlay."""
from __future__ import annotations

import json
from pathlib import Path

from expectations_scenario_research import build, load_latest, markdown, review_pack_overlay, write_versions
from persistent_research_dossier import load_latest_versions
from research_question_tasking import load_latest_tasks

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "operations-review" / "expectations-scenario-research-v1-20260820"


def inputs() -> tuple[dict, dict, dict, dict]:
    pack = json.loads((ROOT / "operations-review/human-research-review-pack-v1-20260820/"
                       "human_research_review_pack_artifact.json").read_text(encoding="utf-8"))
    relative = json.loads((ROOT / "operations-review/sector-relative-research-context-v1-20260820/"
                           "sector_relative_review_pack_overlay.json").read_text(encoding="utf-8"))
    return pack, load_latest_versions(ROOT / "operations-review/persistent-research-dossier-v1-20260820"), load_latest_tasks(ROOT / "operations-review/research-question-tasking-v1-20260820"), relative


def run(previous_by_ticker: dict | None = None) -> tuple[dict, dict]:
    pack, dossiers, tasks, relative = inputs()
    artifact = build(pack, dossiers, tasks, relative, previous_by_ticker=previous_by_ticker)
    return artifact, review_pack_overlay(pack, artifact)


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifact, overlay = run(load_latest(OUTPUT))
    write_versions(OUTPUT, artifact)
    replay, _ = run(load_latest(OUTPUT))
    artifact["replay_validation"] = {"scenario_content_identities_unchanged":
                                      [item["scenario_content_identity"] for item in artifact["scenarios"]] == [item["scenario_content_identity"] for item in replay["scenarios"]],
                                      "replay_artifact_identity": replay["artifact_identity"]}
    (OUTPUT / "expectations_scenario_research_artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT / "scenario_review_pack_overlay.json").write_text(json.dumps(overlay, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT / "scenario_review_pack_overlay.md").write_text(markdown(overlay), encoding="utf-8")
    print(artifact["artifact_identity"])
