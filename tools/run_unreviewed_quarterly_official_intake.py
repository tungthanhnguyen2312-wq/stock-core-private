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
from annual_financial_ocr_materialization import parse_accounting_integer  # noqa: E402
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
    if (record.get("ticker") != ticker or record.get("reporting_period") != PERIOD
            or lineage.get("document_sha256") != record.get("sha256")
            or assurance.get("state") == "QUALIFIED"):
        raise ValueError("UNREVIEWED_QUARTERLY_SOURCE_BINDING_INVALID")
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
    _validate_row(row)
    return row


def _validate_row(row: dict[str, Any]) -> None:
    if (row.get("evidence_tier") != EVIDENCE_TIER or row.get("audit_or_review_status") != "unreviewed"
            or row.get("qualification_state") != QUALIFICATION_STATE):
        raise ValueError("UNREVIEWED_QUARTERLY_TIER_LABEL_INVALID")
    source = next((spec for spec in DOCUMENTS if spec["sha256"] == row.get("document_sha256")
                   and spec["ticker"] == row.get("ticker")), None)
    obj = row.get("row_object") or {}
    role = row.get("column_role")
    period_key = {"CURRENT_QUARTER": "current_period_label", "PRIOR_YEAR_QUARTER": "comparative_period_label"}.get(role)
    metric_code = {"revenue": "10", "net_income": "60", "attributable_net_income": "61"}.get(row.get("canonical_metric"))
    if (source is None or period_key is None or metric_code is None
            or row.get("source_page") not in source["pages"] or obj.get("page") != row.get("source_page")
            or obj.get("document_sha") != row.get("document_sha256")
            or obj.get("current_period_label") != PERIOD
            or obj.get("comparative_period_label") != "2025-Q2"
            or obj.get(period_key) != row.get("reporting_period")
            or row.get("line_code") != metric_code or obj.get("line_code") != metric_code
            or row.get("statement_family") != "income_statement"
            or obj.get("statement_family") != "income_statement"
            or row.get("statement_scope") != "consolidated"
            or not all(row.get(key) for key in ("materialization_id", "unit_evidence_id", "source_family", "canonical_url"))):
        raise ValueError("UNREVIEWED_QUARTERLY_SOURCE_BINDING_INVALID")
    start, end = _bounds(row["reporting_period"])
    if (row.get("period_type") != "quarter" or row.get("temporal_nature") != "duration"
            or (row.get("period_start"), row.get("period_end")) != (start, end)):
        raise ValueError("UNREVIEWED_QUARTERLY_PERIOD_BINDING_INVALID")
    raw_key = "current" if role == "CURRENT_QUARTER" else "comparative"
    raw = (row.get("raw_values") or {}).get(raw_key)
    if (row.get("currency") != "VND" or type(row.get("unit_scale")) is not int or row["unit_scale"] <= 0
            or type(row.get("value")) is not int
            or raw != obj.get(raw_key + "_raw_value")
            or parse_accounting_integer(raw)[0] * row["unit_scale"] != row["value"]):
        raise ValueError("UNREVIEWED_QUARTERLY_VALUE_BINDING_INVALID")
    restrictions = {"UNREVIEWED_QUARTERLY_NOT_REVIEWED_OR_AUDITED", "NOT_ANNUALIZED_NO_TTM",
                    "NO_Q1_BY_SUBTRACTION", "PUBLICATION_DATE_UNKNOWN_NOT_PIT"}
    if (not restrictions.issubset(row.get("research_use_restrictions") or [])
            or row.get("publication_date") is not None
            or not row.get("observed_at") or row.get("knowledge_available_at") != row.get("observed_at")
            or any(row.get(key) for key in ("official_fact_admitted", "strict_valuation_eligible", "existing_consumer_usable"))):
        raise ValueError("UNREVIEWED_QUARTERLY_AUTHORITY_INVALID")
    if row.get("fact_id") != _hash({k: row[k] for k in ("ticker", "canonical_metric", "reporting_period", "document_sha256", "column_role", "value")}):
        raise ValueError("UNREVIEWED_QUARTERLY_FACT_ID_INVALID")


def run(*, landing_root: Path, documents=DOCUMENTS, period: str = PERIOD) -> dict[str, Any]:
    rows, entries = [], []
    for spec in documents:
        evidence_root = Path(landing_root) / spec["subdir"]
        record = _record(evidence_root, spec["sha256"])
        if record.get("reporting_period") != period or record.get("ticker") != spec["ticker"] or period != PERIOD:
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
        _validate_row(row)
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
