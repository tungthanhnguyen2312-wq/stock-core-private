"""Run persistent research-question task derivation from retained dossier versions."""
from __future__ import annotations

import json
from pathlib import Path

from persistent_research_dossier import load_latest_versions
from research_question_tasking import build, load_latest_tasks, markdown, write_task_states

ROOT = Path(__file__).resolve().parent
DOSSIER_ROOT = ROOT / "operations-review" / "persistent-research-dossier-v1-20260820"
OUTPUT = ROOT / "operations-review" / "research-question-tasking-v1-20260820"


def run(previous_by_task: dict | None = None) -> dict:
    return build(load_latest_versions(DOSSIER_ROOT), previous_by_task=previous_by_task)


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    daily = run(load_latest_tasks(OUTPUT))
    write_task_states(OUTPUT, daily)
    replay = run(load_latest_tasks(OUTPUT))
    daily["replay_validation"] = {
        "all_task_states_unchanged": {task["task_state_identity"] for task in daily["tasks"]} ==
                                     {task["task_state_identity"] for task in replay["tasks"]},
        "replay_artifact_identity": replay["artifact_identity"],
        "replay_total_tasks": replay["coverage"]["total_tasks"],
    }
    (OUTPUT / "research_question_tasking_artifact.json").write_text(
        json.dumps(daily, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT / "research_question_follow_up_queue.md").write_text(markdown(daily), encoding="utf-8")
    print(daily["artifact_identity"])
