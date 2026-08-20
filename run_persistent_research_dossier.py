"""Run persistent dossier initialization/change detection against retained daily inputs."""
from __future__ import annotations

import json
from pathlib import Path

from persistent_research_dossier import build, load_latest_versions, markdown, write_new_versions

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "operations-review" / "persistent-research-dossier-v1-20260820"


def inputs() -> tuple[dict, dict]:
    product = json.loads((ROOT / "operations-review/mva-daily-investment-research-20260820/"
                          "mva_daily_investment_research_artifact.json").read_text(encoding="utf-8"))
    analyst = json.loads((ROOT / "operations-review/ai-research-analyst-v1-20260820/"
                          "ai_research_analyst_artifact.json").read_text(encoding="utf-8"))
    return product, analyst


def run(previous_by_ticker: dict | None = None) -> dict:
    product, analyst = inputs()
    return build(product, analyst, previous_by_ticker=previous_by_ticker)


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    daily = run(load_latest_versions(OUTPUT))
    write_new_versions(OUTPUT, daily)
    replay = run(load_latest_versions(OUTPUT))
    daily["replay_validation"] = {
        "all_no_material_change": all(item["change_set"]["categories"] == ["NO_MATERIAL_CHANGE"]
                                      for item in replay["dossiers"]),
        "replay_artifact_identity": replay["artifact_identity"],
        "replay_change_category_counts": replay["coverage"]["change_category_counts"],
    }
    (OUTPUT / "persistent_research_dossier_artifact.json").write_text(
        json.dumps(daily, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT / "research_follow_up_queue.md").write_text(markdown(daily), encoding="utf-8")
    print(daily["artifact_identity"])
