from pathlib import Path
import json
from mva_daily_investment_research import build
ROOT=Path(__file__).resolve().parent
def run():
 s=json.loads((ROOT/'operations-review/p3f18-mva-research-synthesis-20260820/p3f18_mva_research_synthesis_artifact.json').read_text(encoding='utf-8'));return build(s)
if __name__=='__main__':
 p=ROOT/'operations-review/mva-daily-investment-research-20260820/mva_daily_investment_research_artifact.json';p.parent.mkdir(parents=True,exist_ok=True);a=run();p.write_text(json.dumps(a,indent=2,sort_keys=True)+'\n');print(a['artifact_identity'])
