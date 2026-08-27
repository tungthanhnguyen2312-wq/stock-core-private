"""Bounded retained-PDF TSV-OCR evidence qualification and no-write panel replay."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from official_financial_ocr_table_evidence import materialize_tsv_pages, panel_facts_from_qualified_ocr, qualify_table_facts
from official_financial_structural_table import reconcile_against_existing_panel
from owner_focus_core_financial_panel_coverage import RETAINED_PDF_INVENTORY, build_artifact as build_owner_focus
from p3f13_official_financial_evidence_scaleout import merge_document_qualified_facts_into_panel
import p3f13_official_financial_evidence_scaleout as p3f13
import market_wide_current_fundamental_research as current_fundamental


DEFAULT_EVIDENCE_ROOT = ROOT / "operations-review" / "governed-official-evidence-v1"
# The FPT run is intentionally the smallest primary-statement slice: cash/debt
# balance-sheet page, income statement, and cash-flow statement.  Adjacent
# balance-sheet continuation pages are not silently OCR'd merely for coverage.
DEFAULT_PAGES = (8, 10, 12, 13)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _record(evidence_root: Path, document_sha256: str) -> dict[str, Any]:
    manifest = json.loads((evidence_root / "official_document_acquisition_manifest.json").read_text(encoding="utf-8"))
    matches = [dict(row) for row in manifest.get("records", []) if row.get("sha256") == document_sha256]
    if len(matches) != 1 or matches[0].get("acquisition_status") != "retained":
        raise ValueError("RETAINED_DOCUMENT_NOT_UNIQUE")
    return matches[0]


def _qualified_candidates(qualification: dict[str, Any], record: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "ticker": qualification["ticker"], "canonical_metric": fact["canonical_metric"],
        "fiscal_period": qualification["reporting_period"], "statement_scope": "consolidated",
        "qualification_status": "OFFICIAL_FACT_QUALIFIED", "normalized_value": fact["value"],
        "document_sha256": record["sha256"],
    } for fact in qualification["qualified_facts"]]


def run(*, document_sha256: str, evidence_root: Path = DEFAULT_EVIDENCE_ROOT, pages: tuple[int, ...] = DEFAULT_PAGES) -> dict[str, Any]:
    """Replay a single immutable audited annual statement without mutating any store."""
    record = _record(evidence_root, document_sha256)
    baseline_p3f13 = p3f13.execute()
    materialization = materialize_tsv_pages(record, evidence_root=evidence_root, pages=pages)
    qualification = qualify_table_facts(materialization, ticker=record["ticker"], reporting_period=record["reporting_period"])
    candidates = _qualified_candidates(qualification, record)
    reconciliation = reconcile_against_existing_panel(candidates, baseline_p3f13["refreshed_panel_data"])
    eligible_metrics = {row["canonical_metric"] for row in reconciliation if row["eligible_for_ingress"]}
    panel_facts = panel_facts_from_qualified_ocr(
        qualification, entity_type="corporate", statement_scope="consolidated", audit_or_review_status="audited",
        knowledge_available_at=record["observed_at"], observed_at=record["observed_at"],
    )
    ingress_facts = [row for row in panel_facts if row["canonical_metric"] in eligible_metrics]
    refreshed_panel = merge_document_qualified_facts_into_panel(baseline_p3f13["refreshed_panel_data"], ingress_facts)
    refreshed_readiness = p3f13.build_fundamental_research_artifact(refreshed_panel)
    after_p3f13 = copy.deepcopy(baseline_p3f13)
    after_p3f13["refreshed_panel_data"] = refreshed_panel
    after_p3f13["refreshed_fundamental_readiness"] = refreshed_readiness
    after_p3f13.pop("artifact_sha256", None); after_p3f13.pop("artifact_identity", None)
    after_p3f13["artifact_sha256"] = p3f13._hash(after_p3f13)
    after_p3f13["artifact_identity"] = f"p3f13_official_financial_evidence_scaleout:{after_p3f13['artifact_sha256']}"
    frozen = json.loads(current_fundamental.DEFAULT_P3F10_FROZEN.read_text(encoding="utf-8"))
    after_current = current_fundamental.build_artifact(
        p3f10_frozen=frozen, p3f13_current=after_p3f13, requested_at=record["observed_at"],
        provider_series_by_ticker=current_fundamental.load_retained_provider_series(current_fundamental.DEFAULT_CANONICAL_FACTS_ROOT),
    )
    owner_before = build_owner_focus(p3f13_artifact=baseline_p3f13, fundamental_artifact=current_fundamental.execute(requested_at=record["observed_at"]), pdf_inventory=json.loads(RETAINED_PDF_INVENTORY.read_text(encoding="utf-8")))
    owner_after = build_owner_focus(p3f13_artifact=after_p3f13, fundamental_artifact=after_current, pdf_inventory=json.loads(RETAINED_PDF_INVENTORY.read_text(encoding="utf-8")))
    output = {"contract_version": "image_table_tsv_ocr_evidence_run/v1", "document": record,
              "pages_requested": list(pages), "materialization": materialization, "qualification": qualification,
              "reconciliation": reconciliation, "ingress": {"eligible_metrics": sorted(eligible_metrics), "panel_facts": ingress_facts,
                  "duplicate_or_conflict_metrics": sorted(row["canonical_metric"] for row in reconciliation if not row["eligible_for_ingress"])},
              "p3f13_before_after": {"before_count": baseline_p3f13["refreshed_panel_data"]["qualified_facts_count"], "after_count": refreshed_panel["qualified_facts_count"],
                  "before_identity": baseline_p3f13["artifact_identity"], "after_identity": after_p3f13["artifact_identity"]},
              "current_fundamental_after": after_current, "owner_focus_before": owner_before, "owner_focus_after": owner_after,
              "authority_boundary": {"network_used": False, "provider_used": False, "production_db_mutated": False, "value_or_recommendation_activated": False}}
    output["artifact_sha256"] = _hash(output)
    output["artifact_identity"] = f"image_table_tsv_ocr_evidence_run:{output['artifact_sha256']}"
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-sha256", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    artifact = run(document_sha256=args.document_sha256)
    rendered = json.dumps(artifact, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
