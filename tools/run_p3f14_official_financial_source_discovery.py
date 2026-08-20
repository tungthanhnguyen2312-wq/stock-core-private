from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from p3f14_official_financial_source_discovery import execute
p=ROOT/'operations-review/p3f14-official-financial-source-discovery-20260820/p3f14_official_financial_source_discovery_artifact.json';p.parent.mkdir(parents=True,exist_ok=True);a=execute();p.write_text(json.dumps(a,indent=2,sort_keys=True)+'\n');print(a['artifact_identity'])
