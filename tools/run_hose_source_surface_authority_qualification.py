from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from hose_source_surface_authority_qualification import build,sha
OUT=ROOT/'operations-review'/'hose-source-surface-and-market-data-authority-qualification-v1-20260824'/'hose_source_surface_artifact.json'
a=build(OUT.parent);data=json.dumps(a,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n';OUT.parent.mkdir(parents=True,exist_ok=True)
if OUT.exists() and OUT.read_text(encoding='utf-8')!=data:raise ValueError('IMMUTABLE_CONTENT_CONFLICT')
OUT.write_text(data,encoding='utf-8');print(a['artifact_identity'])
