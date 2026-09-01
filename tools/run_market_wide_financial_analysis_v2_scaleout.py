"""Materialize the retained-only Financial Analysis V2 market-wide artifact."""
from __future__ import annotations
import argparse, copy, gzip, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import market_wide_financial_analysis_v2_scaleout as scaleout  # noqa: E402

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--semantic-artifact", type=Path, required=True); p.add_argument("--semantic-rows", type=Path, required=True)
    p.add_argument("--feature-store-artifact", type=Path, required=True); p.add_argument("--feature-store-records", type=Path, required=True)
    p.add_argument("--legacy-engine-artifact", type=Path, help="Optional retained 523 V2 regression oracle.")
    p.add_argument("--depth-recovery-rows", type=Path, help="Optional retained-only recovered rows from structured_financial_depth_context/v1.")
    p.add_argument("--classification-diagnostics", type=Path, help="Optional governed classification-scaleout diagnostics.")
    p.add_argument("--output", type=Path, required=True); p.add_argument("--requested-at", default="2026-09-01T00:00:00+07:00"); a = p.parse_args()
    semantic = json.loads(a.semantic_artifact.read_text(encoding="utf-8")); records, store = scaleout.load_feature_store(a.feature_store_artifact, a.feature_store_records)
    with gzip.open(a.semantic_rows, "rt", encoding="utf-8") as h: rows = [json.loads(line) for line in h if line.strip()]
    if a.depth_recovery_rows:
        with gzip.open(a.depth_recovery_rows, "rt", encoding="utf-8") as h:
            rows.extend(json.loads(line) for line in h if line.strip())
    legacy = json.loads(a.legacy_engine_artifact.read_text(encoding="utf-8")).get("records", {}) if a.legacy_engine_artifact else {}
    if not isinstance(legacy, dict): raise ValueError("LEGACY_ENGINE_RECORDS_INVALID")
    classification_identity = None
    if a.classification_diagnostics:
        diagnostics = json.loads(a.classification_diagnostics.read_text(encoding="utf-8")); classification_identity = diagnostics.get("diagnostics_identity")
        if not classification_identity or not isinstance(diagnostics.get("rows"), list): raise ValueError("CLASSIFICATION_DIAGNOSTICS_INVALID")
        records = copy.deepcopy(records)
        for item in diagnostics["rows"]:
            ticker, outcome = str(item.get("ticker") or "").upper(), str(item.get("outcome") or "")
            if ticker not in records or outcome not in {"corporate", "bank", "securities", "insurance", "finance_company"}: continue
            records[ticker]["entity_type"] = outcome
    artifact = scaleout.build_scaleout(semantic_rows=rows, feature_records=records, feature_store_artifact=store, period_semantics_identity=semantic["artifact_identity"], requested_at=a.requested_at, legacy_records=legacy, classification_diagnostics_identity=classification_identity)
    a.output.parent.mkdir(parents=True, exist_ok=True); a.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact_identity": artifact["artifact_identity"], "coverage": artifact["coverage"]}, ensure_ascii=False, sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
