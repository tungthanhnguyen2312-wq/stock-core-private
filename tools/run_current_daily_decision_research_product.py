"""Materialize the current daily human-review product from retained artifacts only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from current_daily_decision_research_product import build, content_identity, markdown

OPERATIONS = ROOT / "operations-review"
PATHS = {
    "descriptive": "market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json",
    "tactical": "watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json",
    "peer_relative": "sector-aware-relative-research-v1-20260824/sector_aware_relative_research_artifact.json",
    "fundamental": "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json",
    "valuation": "market-wide-current-valuation-v1-20260824/market_wide_current_valuation_artifact.json",
    "scenario": "current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json",
    "triage": "full-universe-entry-candidate-triage-20260824/full_universe_entry_candidate_triage_20260824.json",
}
OUTPUT = OPERATIONS / "current-daily-decision-research-product-v2-20260824"
SHADOW_OUTPUT = OPERATIONS / "current-research-decision-packet-dashboard-shadow-v1"
DEFAULT_PACKET = OPERATIONS / "current-research-decision-packet-v1/current_research_decision_packet_artifact.json"


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-current-research-decision-packet", action="store_true",
                        help="Opt-in shadow attach of current_research_decision_packet/v1. Default off.")
    parser.add_argument("--current-research-decision-packet-path", default=str(DEFAULT_PACKET))
    args = parser.parse_args(argv)
    inputs = {name: json.loads((OPERATIONS / path).read_text(encoding="utf-8")) for name, path in PATHS.items()}
    packet = None
    output = OUTPUT
    if args.include_current_research_decision_packet:
        packet = json.loads(Path(args.current_research_decision_packet_path).read_text(encoding="utf-8"))
        output = SHADOW_OUTPUT
    artifact = build(**inputs, current_research_decision_packet=packet)
    assert content_identity(artifact)["artifact_sha256"] == artifact["artifact_sha256"]
    output.mkdir(parents=True, exist_ok=True)
    (output / "current_daily_decision_research_product_artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "current_daily_decision_research_brief.md").write_text(markdown(artifact), encoding="utf-8")
    print(artifact["artifact_identity"])


if __name__ == "__main__":
    main()
