from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));from p3f16_provider_financial_semantics import run
p=ROOT/'operations-review/p3f16-provider-financial-semantics-20260820/p3f16_provider_financial_semantics_artifact.json';p.parent.mkdir(parents=True,exist_ok=True);a=run();p.write_text(json.dumps(a,indent=2,sort_keys=True)+'\n');print(a['artifact_identity'])
