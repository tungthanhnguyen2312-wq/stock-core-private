from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));from p3f14b_route_ownership_evidence import run
p=ROOT/'operations-review/p3f14b-route-ownership-evidence-20260820/p3f14b_route_ownership_evidence_artifact.json';p.parent.mkdir(parents=True,exist_ok=True);a=run();p.write_text(json.dumps(a,indent=2,sort_keys=True)+'\n');print(a['artifact_identity'])
