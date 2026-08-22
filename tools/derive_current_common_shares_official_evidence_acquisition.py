"""Materialize the deterministic result of the bounded current-share evidence batch."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from current_common_shares_official_evidence_acquisition import build_acquisition_result

P4 = ROOT / "operations-review/p3f4-generic-current-share-authority-20260820/p3f4_generic_current_share_authority_artifact.json"
P5 = ROOT / "operations-review/p3f5-current-share-promotion-review-20260820/p3f5_current_share_promotion_review_artifact.json"
P6 = ROOT / "operations-review/p3f6-mva-provider-share-proxy-20260820/p3f6_mva_provider_share_proxy_artifact.json"
P3 = ROOT / "operations-review/p3f3-operational-valuation-input-scaleout-20260820/p3f3_operational_valuation_input_scaleout_artifact.json"
MANIFESTS = (ROOT / "operations-review/governed-official-evidence-v1/official_document_acquisition_manifest.json", ROOT / "operations-review/hpg-vnm-current-share-bridge-20260802/official_document_acquisition_manifest.json", ROOT / "operations-review/ssi-vsdc-ex-date-notice-acquisition-20260811/official_document_acquisition_manifest.json", ROOT / "operations-review/current-common-shares-official-evidence-acquisition-v1-20260822/retry-complete-stream/official_document_acquisition_manifest.json")
DEFAULT_OUTPUT = ROOT / "operations-review/current-common-shares-official-evidence-acquisition-v1-20260822/current_common_shares_official_evidence_acquisition_manifest.json"
def build() -> dict:
    load=lambda path: json.loads(path.read_text(encoding="utf-8"))
    return build_acquisition_result(p3f3=load(P3),p3f4=load(P4),p3f5=load(P5),p3f6=load(P6),manifests=[load(path) for path in MANIFESTS])
def main(argv: list[str]|None=None)->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--output",default=str(DEFAULT_OUTPUT)); args=parser.parse_args(argv)
    artifact=build(); path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(artifact,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(artifact["artifact_identity"]); return 0
if __name__=="__main__": raise SystemExit(main())
