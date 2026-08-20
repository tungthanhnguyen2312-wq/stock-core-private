from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));from p3f19_liquidity_authority_terminal_resolution import run
p=ROOT/'operations-review/p3f19-liquidity-authority-terminal-resolution-20260820/p3f19_liquidity_authority_terminal_resolution_artifact.json';p.parent.mkdir(parents=True,exist_ok=True);a=run();p.write_text(json.dumps(a,indent=2,sort_keys=True)+'\n');print(a['artifact_identity'])
