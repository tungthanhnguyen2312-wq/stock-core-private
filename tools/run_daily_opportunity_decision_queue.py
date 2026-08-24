"""Build the daily opportunity decision queue from the retained prioritization artifact."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
OPS = ROOT / "operations-review"; OUT = OPS / "daily-opportunity-decision-queue-v1-20260824"
from daily_opportunity_decision_queue import build, replay, prospective_context

P = {
    "opportunity": "current-opportunity-prioritization-v1-20260824/current_opportunity_prioritization_artifact.json",
    "triage": "full-universe-entry-candidate-triage-20260824/full_universe_entry_candidate_triage_20260824.json",
}


def main() -> None:
    d = {k: json.loads((OPS / v).read_text(encoding="utf8")) for k, v in P.items()}
    queue = build(opportunity=d["opportunity"], triage=d["triage"]); replay(queue)
    snapshot = prospective_context(d["opportunity"], queue)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "daily_opportunity_decision_queue_artifact.json").write_text(json.dumps(queue, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf8")
    (OUT / "opportunity_decision_prospective_context.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(queue["artifact_identity"])
    print(queue["entry_relevant_summary"])
    print({"legacy_high_priority": queue["legacy_comparison"]["legacy_high_priority_count"], "agreement": queue["legacy_comparison"]["agreement_count"], "newly_surfaced": len(queue["legacy_comparison"]["newly_surfaced"]), "downgraded": len(queue["legacy_comparison"]["downgraded"])})
    print({lane: info["count"] for lane, info in queue["lane_queues"].items()})
    print("multi_strategy:", queue["multi_strategy"]["count"])
    print(snapshot["snapshot_id"], snapshot["cohort_count"])


if __name__ == "__main__":
    main()
