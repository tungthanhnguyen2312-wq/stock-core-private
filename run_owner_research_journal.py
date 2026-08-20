"""Create the owner-feedback overlay for the retained human review pack."""
from __future__ import annotations

import json
from pathlib import Path

from owner_research_journal import build, load_events, markdown

ROOT = Path(__file__).resolve().parent
PACK = ROOT / "operations-review/human-research-review-pack-v1-20260820/human_research_review_pack_artifact.json"
OUTPUT = ROOT / "operations-review/owner-research-journal-v1-20260820"
EVENTS = OUTPUT / "events"


def run() -> dict:
    review_pack = json.loads(PACK.read_text(encoding="utf-8"))
    return build(review_pack, load_events(EVENTS))


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifact = run()
    (OUTPUT / "owner_research_journal_artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT / "owner_research_journal.md").write_text(markdown(artifact), encoding="utf-8")
    print(artifact["artifact_identity"])
