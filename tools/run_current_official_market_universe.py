"""Materialize the retained current official market-universe projection (no network)."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from current_official_market_universe import build_artifact, replay

DEFAULT = ROOT / "operations-review"
PATHS = {
 "hnx": DEFAULT / "hnx-enumerable-universe-kllh-event-and-disclosure-scaleout-v1-20260824/hnx_enumerable_universe_artifact.json",
 "hose": DEFAULT / "hose-public-xhr-and-periodic-series-recon-v1-20260824-reconciled/hose_public_xhr_artifact.json",
 "status": DEFAULT / "current-universe-status-and-session-coverage-resolution-v1-20260823/current_universe_status_and_session_coverage_resolution_artifact.json",
 "descriptive": DEFAULT / "market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json",
 "screening": DEFAULT / "current-market-screening-opportunity-comparison-foundation-v1-20260823/current_market_screening_opportunity_comparison_foundation_artifact.json",
 "tactical": DEFAULT / "watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json",
 "strategy": DEFAULT / "polymorphic-current-strategy-classification-v1-20260824/polymorphic_current_strategy_classification_artifact.json",
 "scenario": DEFAULT / "current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json"}
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument("--output", default=str(DEFAULT / "current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json")); args=p.parse_args(argv)
 artifact=build_artifact(**{key: json.loads(path.read_text(encoding="utf-8")) for key,path in PATHS.items()}); replay(artifact)
 out=Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
 print(artifact["artifact_identity"]); print(artifact["reconciliation"])
if __name__ == "__main__": raise SystemExit(main())
