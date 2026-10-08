"""Requalify retained PNJ/VRE reviewed H1 statements under the provision-component rule.

Same fixed pages as the original reviewed-interim ingress; no network.  Facts first
qualified by this run are known at run time, never at the documents' 2026-09-29
retention time.  Writes append only new exact keys; existing rows stay byte-identical.
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
from tools.run_reviewed_interim_canonical_ingress import DOCUMENTS, DEFAULT_LANDING_ROOT, run, write_outputs

REPORT_NAME = "retained_h1_component_context_report.json"
SPECS = tuple(spec for spec in DOCUMENTS if spec["ticker"] in {"PNJ", "VRE"})
EMPHASIS_HEADING = ("van", "de", "can", "nhan", "manh")


def _fold(text: str) -> str:
    import unicodedata
    folded = "".join(ch for ch in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(ch))
    return " ".join("".join(ch if ch.isalnum() else " " for ch in folded.replace("đ", "d")).split())


def emphasis_of_matter_evidence(front: dict) -> list[dict]:
    """Literal reviewer emphasis paragraph: positioned OCR lines only, no interpretation."""
    found = []
    for page in front["pages"]:
        tokens = (page.get("ocr_derived_text_evidence") or {}).get("tokens") or []
        lines: dict[tuple, list] = {}
        for token in tokens:
            h = token.get("tsv_hierarchy") or {}
            lines.setdefault((h.get("block_num"), h.get("par_num"), h.get("line_num")), []).append(token)
        ordered = sorted(lines.values(), key=lambda ts: min(t["top"] for t in ts))
        for index, line in enumerate(ordered):
            if _fold(" ".join(t["text"] for t in line)).split() != list(EMPHASIS_HEADING):
                continue
            body = [t for ts in ordered[index + 1:index + 7] for t in sorted(ts, key=lambda t: t["x0"])]
            text = " ".join(t["text"] for t in body)
            found.append({"page_number": int(page["page_number"]),
                          "rendered_image_sha256": page["source_image_evidence"]["rendered_image_sha256"],
                          "heading_token_ids": [t["token_id"] for t in line],
                          "body_token_ids": [t["token_id"] for t in body], "literal_ocr_text": text,
                          "body_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                          "state": "EMPHASIS_OF_MATTER_PRESENT_REVIEW_CONCLUSION_NOT_MODIFIED_PER_SOURCE",
                          "interpretation": "NONE_RECURRENCE_AND_FINANCIAL_EFFECT_NOT_INFERRED"})
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing-root", type=Path, default=Path(DEFAULT_LANDING_ROOT))
    parser.add_argument("--public-root", type=Path, default=ROOT / PUBLIC_ARTIFACT_DIR)
    parser.add_argument("--qualified-at", default=None, help="Explicit replay time; defaults to now (UTC).")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    qualified_at = args.qualified_at or datetime.now(timezone.utc).isoformat()
    result = run(landing_root=args.landing_root, document_specs=SPECS, interim_qualified_at=qualified_at)
    report = result["report"]
    report["milestone_id"] = "PNJ_VRE_REVIEWED_H1_PROVISION_COMPONENT_AND_TOTAL_ASSET_IDENTITY_V1"
    report["qualified_at"] = qualified_at
    report["assurance_emphasis_evidence"] = {
        m["ticker"]: emphasis_of_matter_evidence(m["front"]) for m in result["materializations"]}
    report.pop("artifact_sha256", None)
    report["artifact_sha256"] = hashlib.sha256(json.dumps(report, ensure_ascii=False, sort_keys=True,
                                                          separators=(",", ":")).encode("utf-8")).hexdigest()
    result["report"] = report
    if args.write:
        write_outputs(result, args.public_root, append_new_facts_only=True, report_name=REPORT_NAME)
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
