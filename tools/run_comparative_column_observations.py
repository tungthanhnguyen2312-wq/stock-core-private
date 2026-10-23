"""Comparative-column observations from already-admitted reviewed/audited statements (candidates only).

QUALIFIED_QUARTERLY_STATEMENT_THROUGHPUT_V1.  For every admitted income fact in the reviewed
overlay, the same retained page is re-read with the existing OCR geometry engine; the row is
accepted only when its current-column value equals the admitted value, and the same row's
comparative column becomes an observation.  Observations support restatement cross-checks in
``official_income_prior_period_pairing``; they are never admitted facts (Owner gate
``OWNER_GATE_COMPARATIVE_COLUMN_AS_PRIOR_PERIOD_FACT``).  Retained documents only, no network,
amounts are never repaired, and the overlay is never written.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from annual_financial_ocr_materialization import parse_accounting_integer  # noqa: E402
from financial_evidence_currency_contract import DEFAULT_LANDING_ROOT, PUBLIC_ARTIFACT_DIR  # noqa: E402
from stocklookup_core.evidence.financial_row_identity import _identity_fold  # noqa: E402
from stocklookup_core.financial.official_income_prior_period_pairing import (  # noqa: E402
    COMPARATIVE_CONTRACT, COMPARATIVE_PUBLIC_FILE, INCOME_METRICS, LINE_IDENTITY, _hash, validate_comparative_observation)

MILESTONE_ID = "QUALIFIED_QUARTERLY_STATEMENT_THROUGHPUT_V1"
REPORT_NAME = "comparative_column_observation_report.json"
MAX_DOCUMENTS = 8
SUBDIRS = ("currency-refresh-20260929", "fpt-evidence-20261008", "nvl-reviewed-evidence-20261008",
           "triad-h1-evidence-20261008", "representation-recovery-20261008")


def period_label_binding(current_label: Any, comparative_label: Any, *, current_year: int) -> str:
    current, prior = _identity_fold(str(current_label or "")), _identity_fold(str(comparative_label or ""))
    if str(current_year) in current and str(current_year - 1) in prior and str(current_year) not in prior:
        return "EXPLICIT_PRIOR_YEAR_LABEL"
    if "nam nay" in current and "nam truoc" in prior:
        return "PRIOR_YEAR_PHRASE"
    if "ky nay" in current and "ky truoc" in prior:
        return "PRIOR_PERIOD_PHRASE_YEAR_NOT_LITERAL"
    return "UNBOUND"


def _admitted_income_facts(public_root: Path) -> dict[tuple, list[dict[str, Any]]]:
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for line in (public_root / "qualified_official_facts.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if (row.get("canonical_metric") in INCOME_METRICS and row.get("statement_family") == "income_statement"
                and row.get("qualification_state") == "QUALIFIED" and row.get("audit_or_review_status") in {"audited", "reviewed"}
                and str(row.get("line_code")) == LINE_IDENTITY[row["canonical_metric"]][0]):
            groups.setdefault((row["ticker"], row["document_sha256"], row["reporting_period"]), []).append(row)
    return groups


def _locate(landing_root: Path, sha256: str) -> tuple[Path, dict[str, Any]]:
    from tools.run_reviewed_interim_canonical_ingress import _record
    found = []
    for subdir in SUBDIRS:
        root = landing_root / subdir
        if (root / "official_document_acquisition_manifest.json").is_file():
            try:
                found.append((root, _record(root, sha256)))
            except ValueError:
                continue
    if len(found) != 1:
        raise ValueError("RETAINED_DOCUMENT_NOT_UNIQUE:" + sha256)
    return found[0]


def observations_for_document(facts: list[dict[str, Any]], qualification: dict[str, Any], *, observed_at: str) -> list[dict[str, Any]]:
    admitted = {(row["canonical_metric"], str(row["line_code"])): row for row in facts}
    rows = []
    for fact in qualification["qualified_facts"]:
        lineage = fact.get("source_lineage") or {}
        key = (fact.get("canonical_metric"), str(lineage.get("line_code")))
        source = admitted.get(key)
        if source is None or fact.get("value") != source["normalized_value"]:
            continue
        row_object = lineage.get("row_object") or {}
        raw = lineage["ocr_derived_text_evidence"]["comparative_raw"]
        blockers = []
        try:
            value = parse_accounting_integer(raw)[0] * int(fact["unit_scale"])
        except (ValueError, TypeError):
            value = None
            blockers.append("OCR_NUMERIC_AMBIGUITY")
        binding = period_label_binding(row_object.get("current_period_label"), row_object.get("comparative_period_label"),
                                       current_year=int(source["period_end"][:4]))
        if binding == "PRIOR_PERIOD_PHRASE_YEAR_NOT_LITERAL":
            blockers.append("COMPARATIVE_PERIOD_LABEL_NOT_YEAR_BOUND")
        elif binding == "UNBOUND":
            blockers.append("COMPARATIVE_PERIOD_LABEL_UNBOUND")
        start, end = source["period_start"], source["period_end"]
        prior_start, prior_end = f"{int(start[:4]) - 1}{start[4:]}", f"{int(end[:4]) - 1}{end[4:]}"
        period = source["reporting_period"]
        row = {
            "contract_version": COMPARATIVE_CONTRACT, "milestone_id": MILESTONE_ID, "ticker": source["ticker"],
            "canonical_metric": source["canonical_metric"], "line_code": str(source["line_code"]),
            "accounting_identity": LINE_IDENTITY[source["canonical_metric"]][1],
            "reporting_period": f"{int(period[:4]) - 1}{period[4:]}", "period_type": source["period_type"],
            "period_start": prior_start, "period_end": prior_end, "column_role": "COMPARATIVE_COLUMN_OF_LATER_REPORT",
            "current_period_label": row_object.get("current_period_label"),
            "comparative_period_label": row_object.get("comparative_period_label"), "period_label_binding": binding,
            "value": value, "raw_token": raw, "currency": fact["currency"], "unit_scale": 1,
            "source_unit_scale": fact["unit_scale"], "statement_scope": source["statement_scope"],
            "statement_family": "income_statement", "source_document_sha256": source["document_sha256"],
            "source_page": lineage.get("source_page"), "source_current_citation_id": source["citation_id"],
            "current_value_bbox": row_object.get("current_value_bbox"),
            "comparative_value_bbox": row_object.get("comparative_value_bbox"),
            "materialization_id": lineage["ocr_derived_text_evidence"]["materialization_id"],
            "assurance_basis": f"PRESENTED_AS_COMPARATIVE_IN_LATER_{source['audit_or_review_status'].upper()}_REPORT",
            # Re-read today: never known before this observation, even if the source fact was.
            "observed_at": observed_at, "knowledge_available_at": max(
                (source["knowledge_available_at"], observed_at),
                key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))),
            "blockers": blockers,
            "admission_state": "CANDIDATE_OWNER_GATE", "existing_consumer_usable": False, "official_fact_admitted": False,
        }
        row["observation_id"] = _hash({k: row.get(k) for k in (
            "ticker", "canonical_metric", "reporting_period", "source_document_sha256", "source_page", "raw_token")})
        rows.append(row)
    # Distinct accounting rows reading one identical comparative token at one box are a row-binding doubt.
    for row in rows:
        twins = [other for other in rows if other is not row and other["raw_token"] == row["raw_token"]
                 and other["accounting_identity"] != row["accounting_identity"]]
        if any(other.get("comparative_value_bbox") == row.get("comparative_value_bbox") for other in twins):
            row["blockers"].append("COMPARATIVE_TOKEN_SHARED_ACROSS_ROWS")
        elif twins:
            row.setdefault("limitations", []).append("IDENTICAL_COMPARATIVE_VALUE_ON_DISTINCT_PHYSICAL_ROWS")
    for row in rows:
        if validate_comparative_observation(row):
            raise ValueError("COMPARATIVE_OBSERVATION_INVALID")
    return rows


def run(*, landing_root: Path, public_root: Path, observed_at: str | None = None) -> dict[str, Any]:
    from official_financial_ocr_table_evidence import (
        materialize_tsv_pages, qualify_table_facts, resolve_scoped_statement_scope_evidence, resolve_scoped_unit_evidence)
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    groups = _admitted_income_facts(public_root)
    if len(groups) > MAX_DOCUMENTS:
        raise ValueError("COMPARATIVE_OBSERVATION_BATCH_OUTSIDE_BOUNDED_CONTRACT")
    rows, documents = [], []
    for (ticker, sha256, period), facts in sorted(groups.items()):
        evidence_root, record = _locate(landing_root, sha256)
        pages = tuple(sorted({int(row["source_page"]) for row in facts}))
        statements = materialize_tsv_pages(record, evidence_root=evidence_root, pages=pages)
        qualification = qualify_table_facts(
            statements, ticker=ticker, reporting_period=period,
            scoped_unit_evidence=resolve_scoped_unit_evidence(statements),
            scoped_statement_scope_evidence=resolve_scoped_statement_scope_evidence(statements))
        new = observations_for_document(facts, qualification, observed_at=observed_at)
        rows.extend(new)
        documents.append({"ticker": ticker, "document_sha256": sha256, "reporting_period": period, "pages": list(pages),
                          "admitted_income_facts": len(facts), "observations": len(new),
                          "blocked": sorted({blocker for row in new for blocker in row["blockers"]})})
    rows.sort(key=lambda row: (row["ticker"], row["reporting_period"], row["canonical_metric"], row["source_document_sha256"]))
    report = {"contract_version": COMPARATIVE_CONTRACT, "milestone_id": MILESTONE_ID, "network_used": False,
              "overlay_written": False, "documents": documents, "observation_count": len(rows),
              "candidate_without_blockers": sum(not row["blockers"] for row in rows),
              "observations_identity": _hash([row["observation_id"] for row in rows])}
    return {"report": report, "rows": rows}


def write_outputs(result: dict[str, Any], public_root: Path) -> None:
    with (public_root / COMPARATIVE_PUBLIC_FILE).open("w", encoding="utf-8", newline="\n") as handle:
        for row in result["rows"]:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    (public_root / REPORT_NAME).write_text(json.dumps(result["report"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing-root", type=Path, default=Path(DEFAULT_LANDING_ROOT))
    parser.add_argument("--public-root", type=Path, default=ROOT / PUBLIC_ARTIFACT_DIR)
    parser.add_argument("--observed-at", help="explicit UTC observation instant; default now")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = run(landing_root=args.landing_root, public_root=args.public_root, observed_at=args.observed_at)
    if args.write:
        write_outputs(result, args.public_root)
    print(json.dumps(result["report"], ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
