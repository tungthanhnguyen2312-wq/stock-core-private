"""Bounded retained-only reviewed-interim canonical ingress (no network, no acquisition).

Re-materializes the front-matter (review report) and statement pages of already retained
H1 2026 PDFs with the governed TSV-OCR path, proves the assurance state from the document,
regenerates the qualified facts, and (with --write) refreshes the existing official overlay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from financial_evidence_currency_contract import DEFAULT_LANDING_ROOT, PUBLIC_ARTIFACT_DIR  # noqa: E402
from financial_evidence_currency_refresh import PUBLIC_FACTS, PUBLIC_PRECEDENCE  # noqa: E402
from official_financial_assurance_evidence import resolve_document_assurance_evidence  # noqa: E402
from official_financial_ocr_table_evidence import (  # noqa: E402
    materialize_tsv_pages, panel_facts_from_qualified_ocr, qualify_table_facts,
    resolve_scoped_statement_scope_evidence, resolve_scoped_unit_evidence,
    resolve_ambiguous_debt_line_code_cells,
)
from reviewed_interim_canonical_ingress import (  # noqa: E402
    CONTRACT_VERSION, MILESTONE_ID, authority_projection, overlay_rows_from_panel_facts, precedence_row,
)

PERIOD = "2026-H1"
REPORT_NAME = "reviewed_interim_canonical_ingress_report.json"
EVIDENCE_SUBDIR = "currency-refresh-20260929"
FRONT_MATTER_PAGES = (1, 2, 3, 4, 5, 6)
# Statement pages already identified by the prior geometry milestone; HPG is intentionally
# excluded (its unit blocker is not resolved by retained evidence).
DOCUMENTS = (
    {"ticker": "PNJ", "sha256": "db877169e7c19b4b81d60b37d5aab8f9938129a66b582c2229ffffebdca2a43d", "pages": (8, 9, 10, 11)},
    {"ticker": "PVD", "sha256": "a7360d2fc9a8a67a1535820813cda2bb8ef288466cd36c949e050c2f2a1b290a", "pages": (6, 7, 8, 9)},
    {"ticker": "VRE", "sha256": "7e9b9e39901a028972fff80bc1a4f9f5cab4c1526ce4029f9b853ccff6aeaac0", "pages": (7, 8, 10, 11, 12, 13)},
)


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _record(evidence_root: Path, sha256: str) -> dict[str, Any]:
    manifest = json.loads((evidence_root / "official_document_acquisition_manifest.json").read_text(encoding="utf-8"))
    matches = [row for row in manifest["records"] if row.get("sha256") == sha256]
    if len(matches) != 1 or matches[0].get("acquisition_status") != "retained":
        raise ValueError("RETAINED_DOCUMENT_NOT_UNIQUE")
    return matches[0]


def run(*, landing_root: Path, document_specs=DOCUMENTS, reporting_period: str = PERIOD,
        allow_audited_annual_context: bool = False, annual_context_known_at: str | None = None,
        resolve_cash_flow_code_cells: bool = False, evidence_subdir: str = EVIDENCE_SUBDIR,
        front_matter_pages=FRONT_MATTER_PAGES, allow_unqualified_native_fallback: bool = False,
        interim_qualified_at: str | None = None) -> dict[str, Any]:
    from financial_evidence_currency_contract import COHORT, TARGET_PERIODS
    if (reporting_period not in TARGET_PERIODS or len(document_specs) > 3
            or any(s["ticker"] not in COHORT for s in document_specs)
            or not 1 <= len(front_matter_pages) <= 8
            or len(set(front_matter_pages)) != len(front_matter_pages)
            or any(not isinstance(p, int) or not 1 <= p <= 8 for p in front_matter_pages)
            or Path(evidence_subdir).name != evidence_subdir or evidence_subdir in {".", ".."}
            or sum(len(front_matter_pages)+len(s["pages"]) for s in document_specs) > 40):
        raise ValueError("RETAINED_OCR_BATCH_OUTSIDE_BOUNDED_CONTRACT")
    if reporting_period == "2025" and not allow_audited_annual_context:
        raise ValueError("AUDITED_ANNUAL_CONTEXT_REQUIRES_EXPLICIT_SCOPE")
    evidence_root = landing_root / evidence_subdir
    annual_known = annual_context_known_at or datetime.now(timezone.utc).isoformat()
    documents, overlay_rows, precedence, ocr_reads, materializations = [], [], [], 0, []
    for spec in document_specs:
        record = _record(evidence_root, spec["sha256"])
        if record.get("reporting_period") != reporting_period:
            raise ValueError("RETAINED_DOCUMENT_PERIOD_BINDING_MISMATCH")
        known_at = record["observed_at"]
        if interim_qualified_at is not None:
            # A rule admitted after the document was first observed makes its facts
            # later-known: qualification time is the floor, never the retained date.
            known_at = max((known_at, interim_qualified_at), key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")))
        if reporting_period == "2025":
            # Qualification is a conservative later bound when the retained batch
            # observation predates individual response completion. Never backdate it.
            known_at = max((known_at, annual_known), key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")))
        fallback = {"allow_unqualified_native_fallback": True} if allow_unqualified_native_fallback else {}
        front = materialize_tsv_pages(record, evidence_root=evidence_root, pages=front_matter_pages, **fallback)
        statements = materialize_tsv_pages(record, evidence_root=evidence_root, pages=spec["pages"], **fallback)
        materializations.append({"ticker": spec["ticker"], "front": front, "statements": statements})
        ocr_reads += len(front_matter_pages) + len(spec["pages"])
        assurance = resolve_document_assurance_evidence(front)
        cells = (resolve_ambiguous_debt_line_code_cells(statements, record=record,
                    evidence_root=evidence_root, reporting_period=reporting_period,
                    include_operating_cash_flow=True) if resolve_cash_flow_code_cells else None)
        qualification = qualify_table_facts(
            statements, ticker=spec["ticker"], reporting_period=reporting_period,
            include_earnings_quality_components=reporting_period != "2025" or allow_audited_annual_context,
            scoped_unit_evidence=resolve_scoped_unit_evidence(statements),
            scoped_statement_scope_evidence=resolve_scoped_statement_scope_evidence(statements),
            line_code_cell_resolution=cells,
        )
        entry: dict[str, Any] = {
            "ticker": spec["ticker"], "document_sha256": spec["sha256"], "reporting_period": reporting_period,
            "observed_at": record["observed_at"], "knowledge_available_at": known_at,
            "assurance": {key: assurance.get(key) for key in (
                "state", "reason", "audit_or_review_status", "page_number", "scope_of_assurance", "matched_anchors",
                "evidence_id", "citation_id", "inheritance", "rendered_image_sha256",
                "title_span", "opinion_evidence", "materialization_id", "page_text_sha256")},
            "candidate_facts": [{"metric": fact["canonical_metric"], "value": fact["value"], "currency": fact["currency"],
                                 "source_unit_scale": fact["unit_scale"], "source_page": fact["source_lineage"]["source_page"],
                                 "line_code": fact["source_lineage"]["line_code"]} for fact in qualification["qualified_facts"]],
            "blocked_candidates": qualification["blocked_candidates"],
            "canonical_facts": [], "ingress_blocked": [],
        }
        if cells:
            entry["line_code_cell_resolution"] = cells
        if allow_unqualified_native_fallback:
            entry["native_fallback_pages"] = [{"page_number": page["page_number"],
                "route": page["route"], "native_failure_evidence": page.get("native_failure_evidence")}
                for materialization in (front, statements) for page in materialization["pages"]]
        if assurance["state"] == "QUALIFIED":
            panel_facts = panel_facts_from_qualified_ocr(
                qualification, entity_type="corporate", statement_scope="consolidated",
                audit_or_review_status=assurance["audit_or_review_status"], assurance_evidence=assurance,
                knowledge_available_at=known_at, observed_at=record["observed_at"],
            )
            rows, blocked = overlay_rows_from_panel_facts(panel_facts,
                allow_audited_annual_context=allow_audited_annual_context)
            entry["ingress_blocked"] = blocked
            for row in rows:
                # No exact-key legacy fact exists for an H1 flow (provider rows are quarterly); a
                # different-period legacy value would be NOT_COMPARABLE, never a match.
                projection = authority_projection(row)
                precedence.append(precedence_row(row, None))
                entry["canonical_facts"].append({
                    "metric": row["canonical_metric"], "value": row["normalized_value"], "currency": row["currency"],
                    "period": row["reporting_period"], "period_type": row["period_type"],
                    "period_start": row["period_start"], "period_end": row["period_end"],
                    "scope": row["statement_scope"], "source_unit_scale": row["source_unit_scale"],
                    "citation_id": row["citation_id"], "source_page": row["source_page"], "line_code": row["line_code"],
                    "audit_or_review_status": row["audit_or_review_status"], **projection})
            overlay_rows.extend(rows)
        documents.append(entry)
    report = {
        "contract_version": CONTRACT_VERSION, "milestone_id": MILESTONE_ID,
        "network_used": False, "raw_pdf_or_image_bytes_committed": False,
        "ocr_reads": {"front_matter_and_statement_pages": ocr_reads},
        "documents": documents,
        "candidate_fact_count": sum(len(item["candidate_facts"]) for item in documents),
        "canonical_fact_count": len(overlay_rows),
        "precedence_statuses": sorted({row["status"] for row in precedence}),
        "financial_v2_pin": {"authority_version": "2026-09-05.1", "changed": False},
        "semantic_identity": {
            "line_60": "net_income (total profit after tax); requires explicit row label",
            "line_61": "attributable_net_income (parent-attributable); requires explicit row label",
            "line_61_as_net_income": "FORBIDDEN",
            "historical_authority": "HISTORICAL_NET_INCOME_SEMANTIC_RECONCILIATION_REQUIRED",
            "historical_affected_known": ["HPG 2022 net_income=line61 (p3f13 semantic correction)",
                                          "HPG 2023 net_income=line61 (p3f13 semantic correction)",
                                          "annual OCR-path facts emitted by the pre-corrective STANDARD_FACT_RULES (line 61 as net_income); exhaustive count not audited"],
            "historical_rows_rewritten": False,
        },
        "valuation": {"pe_ttm_from_h1": False, "ps_ttm_from_h1": False, "pb_effect": "NONE"},
    }
    report["artifact_sha256"] = _hash(report)
    return {"report": report, "overlay_rows": overlay_rows, "precedence_rows": precedence,
            "materializations": materializations}


def write_outputs(result: dict[str, Any], public_root: Path, *, preserve_other_periods: bool = False,
                  report_name: str = REPORT_NAME, preserve_other_documents: bool = False,
                  append_new_facts_only: bool = False) -> None:
    public_root.mkdir(parents=True, exist_ok=True)
    render = lambda rows: "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)  # noqa: E731
    facts, precedence = list(result["overlay_rows"]), list(result["precedence_rows"])
    report = dict(result["report"])
    if append_new_facts_only:
        def fact_key(row):
            return tuple(row.get(k) for k in ("ticker", "canonical_metric", "reporting_period", "statement_scope"))
        old_facts_path, old_precedence_path = public_root / PUBLIC_FACTS, public_root / PUBLIC_PRECEDENCE
        old_facts = [json.loads(line) for line in old_facts_path.read_text(encoding="utf-8").splitlines()] if old_facts_path.exists() else []
        old_precedence = [json.loads(line) for line in old_precedence_path.read_text(encoding="utf-8").splitlines()] if old_precedence_path.exists() else []
        retained = {fact_key(row): row for row in old_facts}
        added = []
        for row in facts:
            prior = retained.get(fact_key(row))
            if prior is not None:
                if any(prior.get(k) != row.get(k) for k in ("normalized_value", "currency", "unit_scale")):
                    raise ValueError("APPEND_ONLY_OFFICIAL_FACT_CONFLICT")
            else:
                added.append(row)
                retained[fact_key(row)] = row
        new_keys = {fact_key(row) for row in added}
        precedence = old_precedence + [row for row in precedence if tuple((row.get("key") or {}).get(k)
            for k in ("ticker", "metric", "period", "scope")) in new_keys]
        facts = old_facts + added
        report["overlay_write"] = {"policy": "APPEND_ONLY_NEW_EXACT_KEYS", "appended_fact_count": len(added),
                                   "prior_fact_count": len(old_facts), "prior_facts_preserved": True}
        report.pop("artifact_sha256", None)
        report["artifact_sha256"] = _hash(report)
    elif preserve_other_periods or preserve_other_documents:
        periods = {d["reporting_period"] for d in result["report"]["documents"]}
        selected = ({(d["ticker"], d["reporting_period"]) for d in result["report"]["documents"]}
                    if preserve_other_documents else set())
        for filename, rows, period in ((PUBLIC_FACTS, facts, lambda r: r["reporting_period"]),
                                      (PUBLIC_PRECEDENCE, precedence, lambda r: r["key"]["period"])):
            path = public_root / filename
            if path.exists():
                rows.extend(r for r in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
                            if ((r.get("ticker", (r.get("key") or {}).get("ticker")), period(r)) not in selected
                                if preserve_other_documents else period(r) not in periods))
    facts.sort(key=lambda row: (row["ticker"], row["reporting_period"], row["canonical_metric"]))
    (public_root / PUBLIC_FACTS).write_text(render(facts), encoding="utf-8", newline="\n")
    (public_root / PUBLIC_PRECEDENCE).write_text(render(precedence), encoding="utf-8", newline="\n")
    (public_root / report_name).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing-root", type=Path, default=Path(DEFAULT_LANDING_ROOT))
    parser.add_argument("--public-root", type=Path, default=ROOT / PUBLIC_ARTIFACT_DIR)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = run(landing_root=args.landing_root)
    if args.write:
        write_outputs(result, args.public_root, preserve_other_periods=True)
    print(json.dumps(result["report"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
