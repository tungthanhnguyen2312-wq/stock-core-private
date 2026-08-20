from pathlib import Path
import json
from market_regime_breadth_context import build, review_overlay
from run_evidence_aware_research_screener import run as run_screener
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'operations-review/market-regime-breadth-context-v1-20260820'
def run():
 p=json.loads((ROOT/'operations-review/mva-daily-investment-research-20260820/mva_daily_investment_research_artifact.json').read_text(encoding='utf8')); s,_=run_screener(); r=json.loads((ROOT/'operations-review/human-research-review-pack-v1-20260820/human_research_review_pack_artifact.json').read_text(encoding='utf8')); return build(p,s,r)
if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True); x=run(); (OUT/'market_regime_breadth_context_artifact.json').write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf8'); (OUT/'market_regime_breadth_review_pack_overlay.json').write_text(json.dumps(review_overlay(x),ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf8'); print(x['artifact_identity'])
