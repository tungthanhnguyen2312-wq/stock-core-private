from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from multi_session_thesis_recommendation_lifecycle import build_artifact
def load(path: Path | None):
    if path is None:return None
    raw=path.read_bytes(); value=json.loads(raw); value["source_artifact_sha256"]=hashlib.sha256(raw).hexdigest(); return value
p=argparse.ArgumentParser(description="Retained-only multi-session thesis lifecycle.")
p.add_argument("--previous-bundle",type=Path);p.add_argument("--current-bundle",type=Path,required=True);p.add_argument("--qualified-session",action="append",required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
x=build_artifact(previous_bundle=load(a.previous_bundle),current_bundle=load(a.current_bundle),qualified_session_chain=a.qualified_session)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf8")
print(json.dumps({"denominator":x["denominator"],"coverage":x["coverage"]},ensure_ascii=False))
