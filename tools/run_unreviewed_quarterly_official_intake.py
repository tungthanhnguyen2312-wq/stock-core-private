"""Owner D-1 tier: official *unreviewed* quarterly income statements as research facts.

OFFICIAL_UNREVIEWED_QUARTERLY_STATEMENT_INTAKE_V1.  Vietnamese quarterly statements are
neither reviewed nor audited, so the reviewed ingress refuses them.  The Owner admitted them
(2026-10-19) into a separate research tier: every fact carries
``evidence_tier = UNREVIEWED_QUARTERLY`` and ``audit_or_review_status = unreviewed`` and is
written to its own public file.  Nothing here is promoted to reviewed/audited, enters the
reviewed overlay, derives Q1 by subtraction, annualizes or builds a TTM.

Retained documents only (no network).  OCR runs through the existing materialization with the
opt-in orientation and non-amount superscript-digit adapters; amounts are never repaired.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from financial_evidence_currency_contract import DEFAULT_LANDING_ROOT, PUBLIC_ARTIFACT_DIR  # noqa: E402
from official_financial_assurance_evidence import resolve_document_assurance_evidence  # noqa: E402
from official_financial_ocr_table_evidence import (  # noqa: E402
    materialize_tsv_pages, qualify_table_facts, resolve_scoped_statement_scope_evidence, resolve_scoped_unit_evidence,
)
from tools.run_reviewed_interim_canonical_ingress import _record  # noqa: E402

MILESTONE_ID = "OFFICIAL_UNREVIEWED_QUARTERLY_STATEMENT_INTAKE_V1"
CONTRACT_VERSION = "unreviewed_quarterly_official_facts/v1"
EVIDENCE_TIER = "UNREVIEWED_QUARTERLY"
QUALIFICATION_STATE = "QUALIFIED_UNREVIEWED_QUARTERLY_RESEARCH"
PUBLIC_FACTS = "unreviewed_quarterly_official_facts.jsonl"
REPORT_NAME = "unreviewed_quarterly_official_intake_report.json"
PERIOD = "2026-Q2"
_QUARTER_BOUNDS = {"Q1": ("01-01", "03-31"), "Q2": ("04-01", "06-30"), "Q3": ("07-01", "09-30"), "Q4": ("10-01", "12-31")}
# Retained Q2/2026 reports (front-matter pages checked for an assurance report; the income
# statement page is the only statement page in scope).
DOCUMENTS = (
    {"ticker": "HPG", "subdir": "currency-refresh-20260929", "sha256": "1f5c4b14f867d2683fd3a84fe0f31fed6fc9920fdcd768c0eaaa1a6e9d19ea71", "front": (1, 2, 3), "pages": (6,)},
    {"ticker": "NVL", "subdir": "currency-refresh-20260929", "sha256": "52d827fa2a5f8d07e07a08a6b57251d172d06aa4d4c7cd80127df2079e12d182", "front": (1, 2, 3), "pages": (8,)},
    {"ticker": "PVD", "subdir": "currency-refresh-20260929", "sha256": "535967018d6704bca01f0bc19ddce55a6d5b72c091a1bcdcd9129e29274c5c98", "front": (1, 2, 3), "pages": (5,)},
    {"ticker": "PNJ", "subdir": "currency-refresh-20260929", "sha256": "a5d860ad579820f9532d037d476ce0d09ce8a078572159a6dfebac0c7b32cbf3", "front": (1, 2, 3), "pages": (6,)},
    {"ticker": "FPT", "subdir": "fpt-evidence-20261008", "sha256": "024b14f8ceffa46d1df30180c8dee17c2f191a8c6dbe839aa9254afe051fdb60", "front": (1, 2, 3), "pages": (7,)},
)


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _bounds(period: str) -> tuple[str, str]:
    year, quarter = period.split("-")
    start, end = _QUARTER_BOUNDS[quarter]
    return f"{year}-{start}", f"{year}-{end}"


def fact_row(fact: dict[str, Any], *, ticker: str, record: dict[str, Any], assurance: dict[str, Any],
             adapters: dict[str, Any]) -> dict[str, Any]:
    lineage = fact["source_lineage"]
    start, end = _bounds(fact["reporting_period"])
    row = {
        "contract_version": CONTRACT_VERSION, "milestone_id": MILESTONE_ID, "ticker": ticker,
        "canonical_metric": fact["canonical_metric"], "value": fact["value"], "currency": fact["currency"],
        "unit_scale": fact["unit_scale"], "reporting_period": fact["reporting_period"], "period_type": "quarter",
        "period_start": start, "period_end": end, "temporal_nature": "duration", "statement_family": fact["statement_family"],
        "statement_scope": (lineage.get("statement_scope_evidence") or {}).get("statement_scope"),
        "column_role": fact["column_role"], "evidence_tier": EVIDENCE_TIER, "audit_or_review_status": "unreviewed",
        "qualification_state": QUALIFICATION_STATE, "research_use_restrictions": [
            "UNREVIEWED_QUARTERLY_NOT_REVIEWED_OR_AUDITED", "NOT_ANNUALIZED_NO_TTM", "NO_Q1_BY_SUBTRACTION",
            "PUBLICATION_DATE_UNKNOWN_NOT_PIT"],
        "reason_codes": fact["reason_codes"], "line_code": lineage["line_code"], "source_page": lineage["source_page"],
        "document_sha256": record["sha256"], "document_class_claimed": record.get("document_class"),
        "source_family": record.get("source_id"), "canonical_url": record.get("canonical_url"),
        "observed_at": record["observed_at"], "knowledge_available_at": record["observed_at"], "publication_date": None,
        "assurance_observation": {key: assurance.get(key) for key in ("state", "reason", "audit_or_review_status")},
        "raw_values": {"current": lineage["ocr_derived_text_evidence"]["current_raw"],
                       "comparative": lineage["ocr_derived_text_evidence"]["comparative_raw"]},
        "row_object": lineage["row_object"], "unit_evidence_id": ((lineage.get("unit_evidence") or {}).get("evidence") or {}).get("evidence_id"),
        "materialization_id": lineage["ocr_derived_text_evidence"]["materialization_id"], "ocr_adapters": adapters,
    }
    row["fact_id"] = _hash({k: row[k] for k in ("ticker", "canonical_metric", "reporting_period", "document_sha256", "column_role", "value")})
    return row


def run(*, landing_root: Path, documents=DOCUMENTS, period: str = PERIOD) -> dict[str, Any]:
    rows, entries = [], []
    for spec in documents:
        evidence_root = Path(landing_root) / spec["subdir"]
        record = _record(evidence_root, spec["sha256"])
        if record.get("reporting_period") != period:
            raise ValueError("RETAINED_DOCUMENT_PERIOD_BINDING_MISMATCH")
        front = materialize_tsv_pages(record, evidence_root=evidence_root, pages=spec["front"], allow_unqualified_native_fallback=True,
                                      detect_orientation=True)
        assurance = resolve_document_assurance_evidence(front)
        entry = {"ticker": spec["ticker"], "document_sha256": spec["sha256"], "assurance": {k: assurance.get(k) for k in ("state", "reason", "audit_or_review_status")}}
        if assurance.get("state") == "QUALIFIED":
            # A reviewed/audited document belongs to the reviewed ingress; never relabel it.
            entry["disposition"] = "REVIEWED_DOCUMENT_REFUSED_BELONGS_TO_REVIEWED_INGRESS"
            entries.append(entry)
            continue
        statements = materialize_tsv_pages(record, evidence_root=evidence_root, pages=spec["pages"], allow_unqualified_native_fallback=True,
                                           detect_orientation=True, normalize_superscript_digits=True)
        qualification = qualify_table_facts(
            statements, ticker=spec["ticker"], reporting_period=period,
            scoped_unit_evidence=resolve_scoped_unit_evidence(statements),
            scoped_statement_scope_evidence=resolve_scoped_statement_scope_evidence(statements), quarterly_four_column=True)
        adapters = {str(page["page_number"]): page.get("ocr_adapters") or {} for page in statements["pages"]}
        new = [fact_row(fact, ticker=spec["ticker"], record=record, assurance=assurance, adapters=adapters.get(str(fact["source_lineage"]["source_page"]), {}))
               for fact in qualification["qualified_facts"]]
        rows.extend(new)
        entry.update(disposition="UNREVIEWED_QUARTERLY_TIER", facts=[(r["canonical_metric"], r["reporting_period"], r["value"]) for r in new],
                     blocked=[{k: b.get(k) for k in ("canonical_metric", "line_code", "reason", "column_role")} for b in qualification["blocked_candidates"]])
        entries.append(entry)
    rows.sort(key=lambda r: (r["ticker"], r["reporting_period"], r["canonical_metric"]))
    report = {"contract_version": CONTRACT_VERSION, "milestone_id": MILESTONE_ID, "network_used": False, "period": period,
              "documents": entries, "fact_count": len(rows),
              "coverage": sorted({(r["ticker"], r["reporting_period"], r["canonical_metric"]) for r in rows}),
              "facts_identity": _hash([r["fact_id"] for r in rows])}
    return {"report": report, "rows": rows}


def write_outputs(result: dict[str, Any], public_root: Path) -> None:
    public_root.mkdir(parents=True, exist_ok=True)
    with (public_root / PUBLIC_FACTS).open("w", encoding="utf-8", newline="\n") as handle:
        for row in result["rows"]:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    (public_root / REPORT_NAME).write_text(json.dumps(result["report"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_unreviewed_quarterly_facts(public_root: Path) -> list[dict[str, Any]]:
    """Research consumers read this tier explicitly; it never merges into reviewed facts."""
    path = Path(public_root) / PUBLIC_FACTS
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if row.get("evidence_tier") != EVIDENCE_TIER or row.get("audit_or_review_status") != "unreviewed" \
                or row.get("qualification_state") != QUALIFICATION_STATE:
            raise ValueError("UNREVIEWED_QUARTERLY_TIER_LABEL_INVALID")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing-root", type=Path, default=Path(DEFAULT_LANDING_ROOT))
    parser.add_argument("--public-root", type=Path, default=ROOT / PUBLIC_ARTIFACT_DIR)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = run(landing_root=args.landing_root)
    if args.write:
        write_outputs(result, args.public_root)
    print(json.dumps(result["report"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
