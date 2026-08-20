from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));from p3f18_mva_research_synthesis import run
p=ROOT/'operations-review/p3f18-mva-research-synthesis-20260820/p3f18_mva_research_synthesis_artifact.json';p.parent.mkdir(parents=True,exist_ok=True);a=run();p.write_text(json.dumps(a,indent=2,sort_keys=True)+'\n');print(a['artifact_identity'])
