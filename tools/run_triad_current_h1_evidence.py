"""Qualify the fixed VNM/QNS/POW current-interim probe from retained official evidence only.

VNM's reviewed consolidated Q2/six-month statement was already retained (2026-08-02); it
is bound to 2026-H1 by its own body and re-read under the canonical fixed OCR profile.
QNS and POW end at their recorded route states; this replay makes no HTTP request.
Facts first qualified by this run are known at run time, never at retention time.
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
# PDF 5-6 are the KPMG review report; 7-10 balance sheet, 11-12 income statement, 13-15 cash flow.
DOCUMENTS = ({"ticker": "VNM", "sha256": VNM_SHA256, "pages": tuple(range(7, 16))},)
FRONT_MATTER_PAGES = (5, 6)
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
TERMINAL_STATES = {
    "QNS": {"state": "ROUTE_DECISION_REQUIRED",
            "reason": "INDEX_EXPOSES_DETAIL_PAGE_NOT_DOCUMENT_LOCATOR",
            "detail": ("Refreshed issuer index lists 'QNS cong bo bao cao tai chinh ban nien nam 2026' "
                       "(15-08-2026) only as the first-party detail page /qns-cong-bo-bao-cao-tai-chinh-ban-nien-nam-2026; "
                       "the PDF locator needs a second discovery request beyond the one-index-per-issuer cap."),
            "index_sha256": "8921d8e7148425222e8b953941f51783fe8595731e537556dbb49c84fa067d0a"},
    "POW": {"state": "APPROVED_ROUTE_BLOCKED", "reason": "access_denied",
            "detail": ("Registry-seeded index https://www.pvpower.vn/quan-he-co-dong/bao-cao-tai-chinh answered 404 "
                       "(as on 2026-09-29); no retained exact 2026 locator; no other route guessed.")},
}


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build(landing_root: Path, qualified_at: str) -> dict:
    result = run(landing_root=landing_root, document_specs=DOCUMENTS, reporting_period="2026-H1",
                 evidence_subdir=EVIDENCE_SUBDIR, front_matter_pages=FRONT_MATTER_PAGES,
                 interim_qualified_at=qualified_at)
    report = result["report"]
    vnm = report["documents"][0]
    report["milestone_id"] = MILESTONE_ID
    report["qualified_at"] = qualified_at
    report["source_notes"] = {"VNM": VNM_SOURCE_NOTES}
    report["issuer_terminal_states"] = {
        "VNM": {"state": "CURRENT_OFFICIAL_FACTS_QUALIFIED" if vnm["canonical_facts"] else "DOCUMENT_RETAINED_OCR_BLOCKED",
                "document_sha256": VNM_SHA256, "network_requests": 0,
                "qualified_metrics": sorted(f["metric"] for f in vnm["canonical_facts"])},
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
