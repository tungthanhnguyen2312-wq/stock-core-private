"""Materialize the additive current-evidence scenario artifact from retained inputs only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from current_evidence_bound_scenario import build, content_identity

OPERATIONS = ROOT / "operations-review"
PATHS = {
    "descriptive": OPERATIONS / "market-wide-current-descriptive-research-v1-20260823/market_wide_current_descriptive_research_artifact.json",
    "tactical": OPERATIONS / "watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json",
    "peer_relative": OPERATIONS / "sector-aware-relative-research-v1-20260824/sector_aware_relative_research_artifact.json",
    "fundamental": OPERATIONS / "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json",
    "valuation": OPERATIONS / "market-wide-current-valuation-v1-20260824/market_wide_current_valuation_artifact.json",
    "triage": OPERATIONS / "full-universe-entry-candidate-triage-20260824/full_universe_entry_candidate_triage_20260824.json",
    "catalyst": OPERATIONS / "catalyst-event-research-context-v1-20260820/catalyst_event_research_context_artifact.json",
    "screening": OPERATIONS / "current-market-screening-opportunity-comparison-foundation-v1-20260823/current_market_screening_opportunity_comparison_foundation_artifact.json",
}
OUTPUT = OPERATIONS / "current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json"


def main() -> None:
    artifact = build(**{name: json.loads(path.read_text(encoding="utf-8")) for name, path in PATHS.items()})
    assert content_identity(artifact)["artifact_sha256"] == artifact["artifact_sha256"]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])


if __name__ == "__main__":
    main()
