"""Materialize current strategy classification from explicit retained artifacts."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from polymorphic_current_strategy_classification import build, content_identity

PATHS = {"descriptive": "market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json", "tactical": "watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json", "peer_relative": "sector-aware-relative-research-v1-20260824/sector_aware_relative_research_artifact.json", "fundamental": "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json", "valuation": "market-wide-current-valuation-v1-20260824/market_wide_current_valuation_artifact.json", "scenario": "current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json", "corporate_intelligence": "market-wide-current-corporate-intelligence-v1-20260824/market_wide_current_corporate_intelligence_artifact.json"}
def main() -> None:
 parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path,default=ROOT/"operations-review/polymorphic-current-strategy-classification-v1-20260824/polymorphic_current_strategy_classification_artifact.json"); args=parser.parse_args(); ops=ROOT/"operations-review"
 artifact=build(**{name:json.loads((ops/path).read_text(encoding="utf-8")) for name,path in PATHS.items()})
 if content_identity(artifact)["artifact_sha256"] != artifact["artifact_sha256"]: raise ValueError("STRATEGY_ARTIFACT_SELF_VERIFICATION_FAILED")
 args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(artifact,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(artifact["artifact_identity"])
if __name__ == "__main__": main()
