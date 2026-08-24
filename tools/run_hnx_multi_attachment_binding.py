from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from hnx_multi_attachment_binding import build,replay
RETAINED=ROOT/'operations-review'/'official-financial-filings-and-canonical-history-scaleout-v1-20260824-r3'
BASELINE=ROOT/'operations-review'/'p3f13-official-financial-evidence-scaleout-20260820'/'p3f13_official_financial_evidence_scaleout_artifact.json'
OUT=ROOT/'operations-review'/'hnx-multi-attachment-binding-and-citable-extraction-v1-20260824-r3'/'hnx_multi_attachment_binding_artifact.json'
def load(path:Path)->dict:return json.loads(path.read_text(encoding='utf-8'))
def main()->None:
 artifact=build(retained_artifact=load(RETAINED/'official_financial_filings_scaleout_artifact.json'),raw_root=RETAINED,baseline=load(BASELINE));data=json.dumps(artifact,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n';OUT.parent.mkdir(parents=True,exist_ok=True)
 if OUT.exists() and OUT.read_text(encoding='utf-8')!=data:raise ValueError('IMMUTABLE_CONTENT_CONFLICT')
 OUT.write_text(data,encoding='utf-8');replay(retained_artifact=load(RETAINED/'official_financial_filings_scaleout_artifact.json'),raw_root=RETAINED,baseline=load(BASELINE),artifact=load(OUT));print(artifact['artifact_identity'])
if __name__=='__main__':main()
