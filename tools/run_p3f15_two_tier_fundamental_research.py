from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));from p3f15_two_tier_fundamental_research import run
p=ROOT/'operations-review/p3f15-two-tier-fundamental-research-20260820/p3f15_two_tier_fundamental_research_artifact.json';p.parent.mkdir(parents=True,exist_ok=True);a=run();p.write_text(json.dumps(a,indent=2,sort_keys=True)+'\n');print(a['artifact_identity'])
