from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from hnx_official_issuer_profile_multi_gate import build,replay
OUT=ROOT/'operations-review'/'hnx-official-issuer-profile-multi-gate-data-unlock-v1-20260824-r3'/'hnx_official_issuer_profile_multi_gate_artifact.json'
def main()->None:
 if '--replay' in sys.argv:
  replay(json.loads(OUT.read_text(encoding='utf-8')),destination=OUT.parent);print('replay_ok');return
 artifact=build(destination=OUT.parent,execute=True);data=json.dumps(artifact,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n';OUT.parent.mkdir(parents=True,exist_ok=True)
 if OUT.exists() and OUT.read_text(encoding='utf-8')!=data:raise ValueError('IMMUTABLE_CONTENT_CONFLICT')
 OUT.write_text(data,encoding='utf-8');replay(json.loads(OUT.read_text(encoding='utf-8')),destination=OUT.parent);print(artifact['artifact_identity'])
if __name__=='__main__':main()
