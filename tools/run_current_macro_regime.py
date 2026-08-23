from __future__ import annotations
import json
from pathlib import Path
from current_macro_regime import acquire

ROOT=Path(__file__).resolve().parents[1]
def main():
 artifact=acquire(); out=ROOT/'operations-review'/'current-macro-regime-v1-20260824'; out.mkdir(parents=True,exist_ok=True)
 path=out/'current_macro_regime_artifact.json'; payload=json.dumps(artifact,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n'
 if path.exists() and path.read_text(encoding='utf-8')!=payload: raise ValueError('IMMUTABLE_MACRO_ARTIFACT_CONTENT_CONFLICT')
 path.write_text(payload,encoding='utf-8'); print(artifact['artifact_identity']); print(path)
if __name__=='__main__': main()
