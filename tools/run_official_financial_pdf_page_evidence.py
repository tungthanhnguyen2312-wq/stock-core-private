"""Materialize page/table evidence for the retained AAA FY2024 PDF; no network."""
from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from official_financial_pdf_page_evidence import build_artifact
BASE = ROOT / "operations-review" / "approved-issuer-ir-official-financial-evidence-cohort-v1-20260827"
SOURCE = BASE / "evidence" / "AAA_fa5a765bf5214c56a609361699a04e9d527e99b34c18c2ff52ac12aecd197fd8.bin"
DOC = {"document_id": "issuer-ir:AAA:fa5a765bf5214c56a609361699a04e9d527e99b34c18c2ff52ac12aecd197fd8", "ticker": "AAA", "sha256": "fa5a765bf5214c56a609361699a04e9d527e99b34c18c2ff52ac12aecd197fd8", "official_url": "https://anphatbioplastics.com/wp-content/uploads/2025/10/BCTN-AAA-2024-VIE-2.pdf", "retrieved_at": "2026-08-27T06:52:19.219164Z"}
if __name__ == "__main__":
    out = build_artifact(document=DOC, path=SOURCE); target = ROOT / "operations-review" / "official-financial-pdf-page-table-extraction-v1-20260827" / "aaa_page_evidence.json"; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); print(json.dumps({"identity": out["artifact_identity"], "pages": out["page_count"], "tables": len(out["tables"]), "facts": len(out["fact_candidates"]), "blocked": len(out["blocked_candidates"])}, ensure_ascii=False))
