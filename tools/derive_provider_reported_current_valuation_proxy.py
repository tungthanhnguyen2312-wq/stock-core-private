from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from provider_reported_current_valuation_proxy import build_proxy
P6=ROOT/'operations-review/p3f6-mva-provider-share-proxy-20260820/p3f6_mva_provider_share_proxy_artifact.json';P3=ROOT/'operations-review/p3f3-operational-valuation-input-scaleout-20260820/p3f3_operational_valuation_input_scaleout_artifact.json'
def build():return build_proxy(json.loads(P6.read_text(encoding='utf-8')),json.loads(P3.read_text(encoding='utf-8')))
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args(argv);v=build();path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(v['artifact_identity']);return 0
if __name__=='__main__':raise SystemExit(main())
