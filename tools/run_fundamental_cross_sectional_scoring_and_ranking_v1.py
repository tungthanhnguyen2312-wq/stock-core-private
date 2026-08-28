from __future__ import annotations
import json,sys,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import fundamental_cross_sectional_scoring as scoring
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();x=scoring.execute();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(x['coverage']))
