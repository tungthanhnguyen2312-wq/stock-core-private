from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from hnx_financial_filing_scaleout import run
OUT=ROOT/'operations-review'/'official-financial-filings-and-canonical-history-scaleout-v1-20260824-r3'
FEED=ROOT/'operations-review'/'official-issuer-disclosure-and-governance-data-v1-20260824'/'raw-feed'/'718c5ffc1de5623614712549d72d28437d2412ba5a5a80e5e0010344f7af161d.rss'
def main():
    artifact=run(feed_path=FEED,destination=OUT); path=OUT/'official_financial_filings_scaleout_artifact.json'; data=json.dumps(artifact,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n'; path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.read_text(encoding='utf-8')!=data: raise ValueError('IMMUTABLE_CONTENT_CONFLICT')
    path.write_text(data,encoding='utf-8'); print(artifact['artifact_identity'])
if __name__=='__main__': main()
