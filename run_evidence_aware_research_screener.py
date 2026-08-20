from pathlib import Path
import json
from evidence_aware_research_screener import build,review_overlay,query
from persistent_research_dossier import load_latest_versions
from run_sector_relative_research_context import run as run_relative_context
from run_strategy_research_eligibility import run as run_eligibility
from run_catalyst_event_research_context import run as run_event_context
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'operations-review/evidence-aware-research-screener-v1-20260820'
def run():
 p=json.loads((ROOT/'operations-review/mva-daily-investment-research-20260820/mva_daily_investment_research_artifact.json').read_text(encoding='utf-8'));e,_=run_eligibility();c,_=run_relative_context();v,_=run_event_context();pack=json.loads((ROOT/'operations-review/human-research-review-pack-v1-20260820/human_research_review_pack_artifact.json').read_text(encoding='utf-8'));a=build(p,e,c,load_latest_versions(ROOT/'operations-review/persistent-research-dossier-v1-20260820'),v);return a,review_overlay(pack,a)
if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True);a,o=run();(OUT/'evidence_aware_research_screener_artifact.json').write_text(json.dumps(a,indent=2,sort_keys=True)+'\n');(OUT/'screener_review_pack_overlay.json').write_text(json.dumps(o,indent=2,sort_keys=True)+'\n');print(a['artifact_identity'])
