"""Qualify the fixed VNM/QNS/POW current-interim probe from retained official evidence only.

VNM's reviewed consolidated Q2/six-month statement was already retained (2026-08-02); it
is bound to 2026-H1 by its own body and re-read under the canonical fixed OCR profile.
QNS's reviewed consolidated semi-annual statement was retained through the owner-authorized
index -> detail page -> PDF chain; its embedded text layer yields zero native candidates,
so the explicit fallback reads it under the same fixed profile. POW ends at its route
state. This replay makes no HTTP request. Each issuer's facts are known at its own
recorded qualification time, never at retention time.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from financial_evidence_currency_contract import PUBLIC_ARTIFACT_DIR
from tools.run_reviewed_interim_canonical_ingress import DEFAULT_LANDING_ROOT, run, write_outputs

MILESTONE_ID = "VNM_QNS_POW_CURRENT_OFFICIAL_FINANCIAL_EVIDENCE_ACQUISITION_V1"
REPORT_NAME = "triad_current_h1_evidence_report.json"
EVIDENCE_SUBDIR = "triad-h1-evidence-20261008"
VNM_SHA256 = "a6155aa757b320b893a78093b0454473f4a581aead225af4eb4ef1fbd6628561"
QNS_SHA256 = "5a06a40f34a6d9b30233926f9c9d909d684744de2bf2ad0956edd367d5f7b068"
# VNM: PDF 5-6 KPMG review report; 7-10 balance sheet, 11-12 income, 13-15 cash flow.
# QNS: PDF 5 AAC review report; 6-7 balance sheet, 8 income, 9 cash flow.
PASSES = (
    {"documents": ({"ticker": "VNM", "sha256": VNM_SHA256, "pages": tuple(range(7, 16))},),
     "front_matter_pages": (5, 6), "native_fallback": False,
     "qualified_at": "2026-10-08T03:11:09.934237+00:00"},
    {"documents": ({"ticker": "QNS", "sha256": QNS_SHA256, "pages": (6, 7, 8, 9)},),
     "front_matter_pages": (5,), "native_fallback": True, "qualified_at": None},
)
# Literal source observations kept as context only; nothing below is a value.
VNM_SOURCE_NOTES = {
    "template": "Mau B 01a - DN/HN, Thong tu so 43/2026/TT-BTC (PDF page 7 header)",
    "comparative_column": "1/1/2026 VND (Da phan loai lai) - comparative literally reclassified; current column unaffected",
    "income_statement": "four date columns (Quy II and giai doan sau thang); six-month heading OCR-damaged, column not bound",
    "cash_flow_page_13": "statement title OCR-damaged; page not admitted as cash flow; OCF and line 03 not read",
    "shareholders_equity": "row 400 current cell OCR '—-35.666.334.973.929'; leading dash artefact not repaired",
    "total_assets": "total is row 280 under the 2026 template; fixed rule reads row 270 (Tai san dai han khac) and refuses it",
    "debt": "borrowings are rows 323/339 under the 2026 template; rows 320/338 are other payables and are refused",
}
QNS_SOURCE_NOTES = {
    "route": ("index 8921d8e7... -> owner-authorized ISSUER_IR_DETAIL_PAGE_RESOLVER a3da3950... -> anchor "
              "'Bao cao tai chinh hop nhat ban nien nam 2026' -> one PDF; separate (tong hop) PDF not fetched"),
    "text_layer": "embedded text layer with corrupted labels; native extractor 0 candidates; explicit fallback",
    "balance_sheet_page_6": "header OCR '30/06/²0²6 01/01/²0²6'; cash and total assets not read",
    "income_statement_page_8": "years literal but code header OCR-damaged; revenue and profit lines not read",
    "cash_flow_page_9": "header years OCR '²0²6 ²0²5'; OCF and line 03 not read",
    "debt": "rows 320/338 are other payables under the 2026 template and are refused; borrowings not read",
}
TERMINAL_STATES = {
    "POW": {"state": "APPROVED_ROUTE_BLOCKED", "reason": "access_denied",
            "detail": ("Registry-seeded index https://www.pvpower.vn/quan-he-co-dong/bao-cao-tai-chinh answered 404 "
                       "(as on 2026-09-29); no retained exact 2026 locator; no other route guessed.")},
}


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _state(document: dict) -> dict:
    return {"state": ("CURRENT_OFFICIAL_FACTS_QUALIFIED" if document["canonical_facts"] else
                      "DOCUMENT_RETAINED_FACTS_BLOCKED" if document["assurance"]["state"] == "QUALIFIED" else
                      "DOCUMENT_RETAINED_ASSURANCE_BLOCKED"),
            "document_sha256": document["document_sha256"], "knowledge_available_at": document["knowledge_available_at"],
            "qualified_metrics": sorted(f["metric"] for f in document["canonical_facts"])}


def build(landing_root: Path, qualified_at: str) -> dict:
    results = [run(landing_root=landing_root, document_specs=spec["documents"], reporting_period="2026-H1",
                   evidence_subdir=EVIDENCE_SUBDIR, front_matter_pages=spec["front_matter_pages"],
                   allow_unqualified_native_fallback=spec["native_fallback"],
                   interim_qualified_at=spec["qualified_at"] or qualified_at) for spec in PASSES]
    result = {"report": results[0]["report"],
              "overlay_rows": [row for r in results for row in r["overlay_rows"]],
              "precedence_rows": [row for r in results for row in r["precedence_rows"]],
              "materializations": [m for r in results for m in r["materializations"]]}
    report = result["report"]
    report["documents"] = [d for r in results for d in r["report"]["documents"]]
    report["ocr_reads"] = {"front_matter_and_statement_pages": sum(
        r["report"]["ocr_reads"]["front_matter_and_statement_pages"] for r in results)}
    report["candidate_fact_count"] = sum(len(d["candidate_facts"]) for d in report["documents"])
    report["canonical_fact_count"] = len(result["overlay_rows"])
    report["precedence_statuses"] = sorted({row["status"] for row in result["precedence_rows"]})
    by_ticker = {d["ticker"]: d for d in report["documents"]}
    report["milestone_id"] = MILESTONE_ID
    report["qualified_at"] = {t: d["knowledge_available_at"] for t, d in by_ticker.items()}
    report["source_notes"] = {"VNM": VNM_SOURCE_NOTES, "QNS": QNS_SOURCE_NOTES}
    report["issuer_terminal_states"] = {
        "VNM": {**_state(by_ticker["VNM"]), "network_requests": 0},
        "QNS": {**_state(by_ticker["QNS"]), "network_requests": 3},
        **TERMINAL_STATES,
    }
    report.pop("artifact_sha256", None)
    report["artifact_sha256"] = _hash(report)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing-root", type=Path, default=Path(DEFAULT_LANDING_ROOT))
    parser.add_argument("--public-root", type=Path, default=ROOT / PUBLIC_ARTIFACT_DIR)
    parser.add_argument("--qualified-at", default=None, help="Explicit replay time; defaults to now (UTC).")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = build(args.landing_root, args.qualified_at or datetime.now(timezone.utc).isoformat())
    if args.write:
        write_outputs(result, args.public_root, append_new_facts_only=True, report_name=REPORT_NAME)
    print(json.dumps(result["report"], ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
