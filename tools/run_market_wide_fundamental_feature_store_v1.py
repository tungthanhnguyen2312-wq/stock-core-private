"""Materialize the Feature Store from the committed semantics payload; no acquisition."""
from __future__ import annotations
import argparse, gzip, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import market_wide_fundamental_feature_store as store  # noqa: E402
OUT = ROOT / "operations-review" / "market-wide-fundamental-feature-store-v1-20260831"
def main() -> int:
 p=argparse.ArgumentParser(); p.add_argument("--semantics-path", type=Path, default=store.DEFAULT_SEMANTICS); p.add_argument("--requested-at", default="2026-08-31T00:00:00+07:00"); p.add_argument("--output-dir", type=Path, default=OUT); a=p.parse_args()
 summary_path=a.semantics_path.with_name("structured_financial_period_semantics_artifact.json")
 summary=json.loads(summary_path.read_text(encoding="utf-8"))
 with gzip.open(a.semantics_path,"rt",encoding="utf-8") as h: rows=[json.loads(line) for line in h if line.strip()]
 artifact=store.build_artifact(semantic_rows=rows, period_semantics_identity=summary["artifact_identity"], requested_at=a.requested_at)
 a.output_dir.mkdir(parents=True,exist_ok=True)
 records=artifact.pop("records"); digest=hashlib.sha256(); payload=a.output_dir/"market_wide_fundamental_feature_store_records.jsonl.gz"
 with gzip.open(payload,"wt",encoding="utf-8",newline="\n") as h:
  for record in records.values():
   line=json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n"; digest.update(line.encode()); h.write(line)
 artifact["records_payload"]={"path":payload.name,"record_count":len(records),"canonical_jsonl_sha256":digest.hexdigest()}
 artifact.update(store.content_identity(artifact))
 (a.output_dir/"market_wide_fundamental_feature_store_artifact.json").write_text(json.dumps(artifact,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 print(json.dumps({"identity":artifact["artifact_identity"],"coverage":artifact["coverage"],"blockers":artifact["blocker_distribution"]},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
