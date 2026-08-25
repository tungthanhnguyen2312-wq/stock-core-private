"""Materialize the current decision-support packet from retained artifacts."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from current_research_decision_packet import build_artifact,replay
DEFAULTS={"opportunity":ROOT/"operations-review/current-opportunity-prioritization-v1-20260824/current_opportunity_prioritization_artifact.json","scenario":ROOT/"operations-review/current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json","risk_register":ROOT/"operations-review/current-research-risk-register-v1/current_research_risk_register_artifact.json","market_sector":ROOT/"operations-review/current-market-sector-leadership-context-v1-20260825/current_market_sector_leadership_context_artifact.json","financial_momentum":ROOT/"operations-review/current-financial-momentum-context-v1/current_financial_momentum_context_artifact.json","corporate_event":ROOT/"operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json","valuation":ROOT/"operations-review/market-wide-current-valuation-research-scaleout-v1/market_wide_current_valuation_artifact.json","historical":ROOT/"operations-review/market-wide-historical-research-context-v1-20260824/market_wide_historical_research_context_artifact.json"}
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in DEFAULTS.items():p.add_argument("--"+n.replace("_","-"),default=str(v))
 p.add_argument("--output",default=str(ROOT/"operations-review/current-research-decision-packet-v1/current_research_decision_packet_artifact.json"));a=p.parse_args(argv)
 load=lambda x:json.loads(Path(x).read_bytes().decode("utf-8")); artifact=build_artifact(**{n:load(getattr(a,n)) for n in DEFAULTS});replay(artifact);out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(artifact,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(artifact["artifact_identity"]);print(json.dumps(artifact["coverage"],sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
