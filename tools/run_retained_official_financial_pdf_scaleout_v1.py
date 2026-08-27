"""Run retained official-financial PDF corpus inventory/extraction; no network or OCR."""
from __future__ import annotations
import json
import sys
import argparse
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import p3f13_official_financial_evidence_scaleout as p3f13
from retained_official_financial_pdf_scaleout import build_artifact

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-sha", action="append", default=[])
    args = parser.parse_args()
    panel = p3f13.execute()["refreshed_panel_data"]
    types = {str(row["issuer_identity"]["ticker"]).upper(): str(row["issuer_identity"].get("entity_type", "unknown")) for row in panel["issuers"]}
    prior_page_evidence = ROOT / "operations-review" / "official-financial-pdf-page-table-extraction-v1-20260827" / "aaa_page_evidence.json"
    if prior_page_evidence.is_file():
        for fact in json.loads(prior_page_evidence.read_text(encoding="utf-8")).get("p3f13_panel_facts", []):
            types.setdefault(str(fact.get("issuer_identity") or "").upper(), str(fact.get("entity_type") or "unknown"))
    artifact = build_artifact(operations_root=ROOT / "operations-review", entity_type_by_ticker=types,
                              replay_hashes=args.replay_sha or None)
    target = ROOT / "operations-review" / "retained-official-financial-pdf-extraction-scaleout-v1-20260827" / "artifact.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(artifact["coverage"], ensure_ascii=False, sort_keys=True))
