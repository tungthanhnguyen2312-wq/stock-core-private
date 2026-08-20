"""Run same-session qualified-archetype relative context and Review Pack overlay."""
from __future__ import annotations

import json
from pathlib import Path

from persistent_research_dossier import load_latest_versions
from sector_relative_research_context import build, load_qualified_entity_classes, markdown_overlay, review_pack_overlay

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "operations-review" / "sector-relative-research-context-v1-20260820"


def run() -> tuple[dict, dict]:
    product = json.loads((ROOT / "operations-review/mva-daily-investment-research-20260820/"
                          "mva_daily_investment_research_artifact.json").read_text(encoding="utf-8"))
    review_pack = json.loads((ROOT / "operations-review/human-research-review-pack-v1-20260820/"
                              "human_research_review_pack_artifact.json").read_text(encoding="utf-8"))
    context = build(product, load_latest_versions(ROOT / "operations-review/persistent-research-dossier-v1-20260820"),
                    load_qualified_entity_classes(ROOT))
    return context, review_pack_overlay(review_pack, context)


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    context, overlay = run()
    (OUTPUT / "sector_relative_research_context_artifact.json").write_text(json.dumps(context, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT / "sector_relative_review_pack_overlay.json").write_text(json.dumps(overlay, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT / "sector_relative_review_pack_overlay.md").write_text(markdown_overlay(overlay), encoding="utf-8")
    print(context["artifact_identity"])
