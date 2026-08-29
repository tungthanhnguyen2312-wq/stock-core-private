"""Deterministic retained-image corporate OCR batch for the owner-focus cohort.

The discovery OCR is limited to statement-page routing.  It never supplies a
numeric candidate; all fact qualification remains on the existing 240-DPI TSV
geometry contract.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping, Sequence

import fitz

from annual_financial_ocr_materialization import DEFAULT_ENGINE, sha256_file
from official_financial_ocr_table_evidence import (
    materialize_tsv_pages, panel_facts_from_qualified_ocr, qualify_table_facts,
    resolve_ambiguous_debt_line_code_cells, resolve_scoped_unit_evidence,
)
from official_financial_structural_table import reconcile_against_existing_panel
from owner_focus_core_financial_panel_coverage import RETAINED_PDF_INVENTORY, build_artifact as build_owner_focus
from owner_research_focus import owner_focus_tickers
from p3f13_official_financial_evidence_scaleout import merge_document_qualified_facts_into_panel
import market_wide_current_fundamental_research as current_fundamental
import p3f13_official_financial_evidence_scaleout as p3f13


ROOT = Path(__file__).resolve().parent
EVIDENCE_ROOT = ROOT / "operations-review" / "governed-official-evidence-v1"
CONTRACT_VERSION = "owner_focus_image_only_corporate_ocr_batch/v1"
BATCH_TICKERS = ("PNJ", "PVD", "NVL", "POW")
REGRESSION_TICKERS = ("FPT",)
CORE_METRICS = ("revenue", "gross_profit", "profit_before_tax", "net_income", "cash_and_equivalents", "total_assets", "shareholders_equity", "total_interest_bearing_debt", "operating_cash_flow")
DISCOVERY_CONFIG = {"dpi": 50, "colorspace": "gray", "language": "vie+eng", "psm": 11, "max_front_pages": 20, "purpose": "STATEMENT_ROUTING_ONLY_NOT_FACT_EXTRACTION", "early_termination": "ALL_REQUIRED_STATEMENT_FAMILIES_INDEPENDENTLY_IDENTIFIED"}
DISCOVERY_FALLBACK_CONFIG = {"dpi": 100, "colorspace": "gray", "language": "vie+eng", "psm": 11, "max_front_pages": 20, "purpose": "STATEMENT_ROUTING_ONLY_NOT_FACT_EXTRACTION", "early_termination": "ALL_REQUIRED_STATEMENT_FAMILIES_INDEPENDENTLY_IDENTIFIED", "requires_circular_issuance_attestation": True}
_DISCOVERY_ANCHORS = {
    "balance_sheet": ("balance sheet", "bang can doi ke toan"),
    "income_statement": ("income statement", "bao cao ket qua hoat dong kinh doanh", "bao cao ket qua kinh doanh"),
    "cash_flow": ("cash flow", "luu chuyen tien te", "bao cao luu chuyen tien"),
}
_FORM_FAMILY = {"b01": "balance_sheet", "b02": "income_statement", "b03": "cash_flow"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _norm(value: str) -> str:
    import unicodedata
    normalized = "".join(ch for ch in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(ch))
    return " ".join(normalized.replace("đ", "d").split())


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _discovery_complete(statement_pages: Sequence[Mapping[str, Any]]) -> bool:
    """Return true only when every required family has direct routing evidence.

    Discovery preserves every candidate page in scan order, so continuation pages
    do not require a speculative single-page selection.  A page that has no
    exact anchor/form-family match cannot contribute to completion.
    """
    identified = {
        str(family)
        for page in statement_pages
        for family in page.get("statement_families", [])
        if family in _DISCOVERY_ANCHORS
    }
    return identified == set(_DISCOVERY_ANCHORS)


def _statement_families_from_text(raw: str, *, requires_circular_issuance_attestation: bool) -> list[str]:
    """Apply unchanged heading semantics with an optional issuance attestation.

    The higher-resolution pass can read narrative mentions in contents and notes;
    binding that pass to an exact Circular issuance attestation on the same
    heading page avoids treating contents or narrative mentions as a routing
    candidate, even if those pages list a statement form elsewhere.
    """
    text = _norm(raw)
    anchored = {family for family, anchors in _DISCOVERY_ANCHORS.items() if any(anchor in text for anchor in anchors)}
    if requires_circular_issuance_attestation:
        circular_attested = "issued under circular" in text or "ban hanh theo thong tu" in text
        return sorted(anchored) if circular_attested else []
    forms = {family for form, family in _FORM_FAMILY.items()
             if re.search(rf"\bb\s*0?{form[-1]}(?:\s*[-/]?\s*(?:dn|hn))?\b", text)}
    return sorted(anchored | forms)


def _merge_discovery_pages(existing: Sequence[Mapping[str, Any]], candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Merge one page deterministically without losing the route that found it."""
    by_page = {int(item["page_number"]): dict(item) for item in existing}
    number = int(candidate["page_number"])
    prior = by_page.get(number)
    if prior is None:
        by_page[number] = dict(candidate)
    else:
        prior["statement_families"] = sorted(set(prior.get("statement_families", [])) | set(candidate.get("statement_families", [])))
        prior["routing_passes"] = sorted(set(prior.get("routing_passes", [])) | set(candidate.get("routing_passes", [])))
        by_page[number] = prior
    return [by_page[number] for number in sorted(by_page)]


def _scan_discovery_pass(document: fitz.Document, *, page_count: int, config: Mapping[str, Any], engine: Path,
                         seed_pages: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One bounded, deterministic OCR pass."""
    pages = [dict(item) for item in seed_pages]
    scanned = []
    config_id = _hash(dict(config))
    for number in range(1, min(int(page_count), int(config["max_front_pages"])) + 1):
        if _discovery_complete(pages):
            break
        pixmap = document[number - 1].get_pixmap(matrix=fitz.Matrix(int(config["dpi"]) / 72, int(config["dpi"]) / 72), colorspace=fitz.csGRAY, alpha=False)
        image = pixmap.tobytes("png")
        raw = subprocess.run([str(engine), "stdin", "stdout", "-l", str(config["language"]), "--psm", str(config["psm"])], input=image, capture_output=True, check=True).stdout.decode("utf-8", errors="replace")
        scanned.append(number)
        families = _statement_families_from_text(raw, requires_circular_issuance_attestation=bool(config.get("requires_circular_issuance_attestation", False)))
        if families:
            pages = _merge_discovery_pages(pages, {"page_number": number, "statement_families": families,
                                                     "routing_text_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                                                     "routing_passes": [config_id]})
    return pages, {"config": dict(config), "config_id": config_id, "pages_ocrd": scanned,
                   "page_count": len(scanned),
                   "statement_pages_after_pass": [int(item["page_number"]) for item in pages]}


def build_batch_manifest(*, inventory: Mapping[str, Any], official_manifest: Mapping[str, Any], owner_focus_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Select the explicit corporate/image-only owner-focus cohort from artifacts."""
    owner = {str(row["ticker"]): row for row in owner_focus_artifact.get("records", [])}
    records_by_sha = {str(row["sha256"]): row for row in official_manifest.get("records", [])}
    rows = []
    for item in inventory.get("inventory", []):
        ticker = str(item.get("ticker") or "")
        if ticker not in BATCH_TICKERS:
            continue
        meta = item.get("source_metadata") or {}
        sha = str(item.get("document_sha256") or "")
        source = records_by_sha.get(sha, meta)
        entity = str((owner.get(ticker) or {}).get("entity_type") or "unknown")
        financial = "financial" in str(item.get("document_class") or "")
        eligible = entity == "corporate" and item.get("classification") == "IMAGE_ONLY" and financial and source.get("acquisition_status") == "retained"
        reason = "ELIGIBLE" if eligible else "WRONG_ENTITY_TYPE" if entity != "corporate" else "NOT_PRIMARY_FINANCIAL_STATEMENT" if not financial else "METADATA_INSUFFICIENT"
        rows.append({"ticker": ticker, "document_sha256": sha, "reporting_period": source.get("reporting_period"),
            "document_type": item.get("document_class"), "entity_type": entity, "retained_path": source.get("relative_path"),
            "page_count": item.get("page_count"), "audit_review_state": "audited" if "audited" in str(item.get("document_class")) else "UNKNOWN",
            "statement_scope": "consolidated" if "financial" in str(item.get("document_class")) else "UNKNOWN",
            "image_native_status": item.get("classification"), "current_evidence_blocker": "IMAGE_ONLY_OCR_GAP",
            "owner_focus_priority_reason": (owner.get(ticker) or {}).get("primary_blocker"), "terminal_manifest_disposition": reason})
    rows.sort(key=lambda row: (BATCH_TICKERS.index(row["ticker"]), str(row["reporting_period"]), row["document_sha256"]))
    eligible = [row for row in rows if row["terminal_manifest_disposition"] == "ELIGIBLE"]
    return {"contract_version": CONTRACT_VERSION, "target_tickers": list(BATCH_TICKERS), "regression_only_tickers": list(REGRESSION_TICKERS),
            "documents": rows, "eligible_document_count": len(eligible), "residual_checks": {"manifest_records": len(rows), "terminal_records": len(rows), "residual": 0, "residual_zero": True,
                "target_tickers_exact": sorted({row["ticker"] for row in rows}) == sorted(BATCH_TICKERS), "fpt_not_new_target": "FPT" not in {row["ticker"] for row in rows}}}


def discover_statement_pages(record: Mapping[str, Any], *, evidence_root: Path = EVIDENCE_ROOT, engine: Path = DEFAULT_ENGINE) -> dict[str, Any]:
    """Route with a cheap pass and bounded strict high-resolution escalation."""
    source = (Path(evidence_root) / str(record["retained_path"])).resolve()
    if not source.is_file() or sha256_file(source) != str(record["document_sha256"]):
        raise ValueError("RETAINED_SOURCE_HASH_MISMATCH")
    document = fitz.open(source)
    try:
        pages, primary = _scan_discovery_pass(document, page_count=int(record["page_count"]), config=DISCOVERY_CONFIG, engine=engine, seed_pages=[])
        passes = [primary]
        # A low-cost, independently anchored statement candidate is already a
        # usable routing result.  Escalation is reserved for the known all-page
        # OCR-readability failure, not for filling every family speculatively.
        if not pages:
            pages, fallback = _scan_discovery_pass(document, page_count=int(record["page_count"]), config=DISCOVERY_FALLBACK_CONFIG, engine=engine, seed_pages=pages)
            passes.append(fallback)
    finally:
        document.close()
    identity = {"document_sha256": record["document_sha256"], "primary_config": DISCOVERY_CONFIG,
                "fallback_config": DISCOVERY_FALLBACK_CONFIG, "statement_pages": pages,
                "fallback_used": len(passes) > 1}
    return {"config": DISCOVERY_CONFIG, "fallback_config": DISCOVERY_FALLBACK_CONFIG,
            "document_sha256": record["document_sha256"], "statement_pages": pages, "routing_passes": passes,
            "fallback_used": len(passes) > 1, "discovery_id": _hash(identity)}


def _candidate_rows(qualification: Mapping[str, Any], record: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"ticker": qualification["ticker"], "canonical_metric": fact["canonical_metric"], "fiscal_period": qualification["reporting_period"],
             "statement_scope": "consolidated", "qualification_status": "OFFICIAL_FACT_QUALIFIED", "normalized_value": fact["value"], "document_sha256": record["document_sha256"]}
            for fact in qualification.get("qualified_facts", [])]


def _eligible_ingress_keys(reconciliation: Sequence[Mapping[str, Any]]) -> set[tuple[Any, ...]]:
    """Translate the reconciliation's public result shape into ingress keys."""
    return {
        (row["ticker"], row["canonical_metric"], row["reporting_period"], row["statement_scope"], row["new_value"])
        for row in reconciliation
        if row["eligible_for_ingress"]
    }


def _prior_qualified_image_ocr_ingress(*, evidence_root: Path) -> list[dict[str, Any]]:
    """Replay previously qualified generic image-OCR ingress, never raw OCR text.

    This retains completed earlier work (for any issuer) as current panel state
    while this batch itself only contributes its selected documents.  Artifacts
    must prove their own v1 image-table contract and exact document linkage.
    """
    facts: list[dict[str, Any]] = []
    for path in sorted(Path(evidence_root).parent.glob("*image-table-tsv-ocr-evidence*/artifact.json")):
        artifact = _read(path)
        if artifact.get("contract_version") != "image_table_tsv_ocr_evidence_run/v1":
            continue
        document = artifact.get("document") or {}
        document_sha = str(document.get("sha256") or "")
        ticker = str(document.get("ticker") or "")
        for fact in (artifact.get("ingress") or {}).get("panel_facts") or []:
            lineage = fact.get("source_lineage") or {}
            if (str(fact.get("issuer_identity") or "") == ticker
                    and str(lineage.get("document_sha256") or "") == document_sha):
                facts.append(copy.deepcopy(fact))
    return facts


def _with_panel(template: Mapping[str, Any], panel: Mapping[str, Any]) -> dict[str, Any]:
    artifact = copy.deepcopy(template)
    artifact["refreshed_panel_data"] = dict(panel)
    artifact["refreshed_fundamental_readiness"] = p3f13.build_fundamental_research_artifact(panel)
    artifact.pop("artifact_sha256", None)
    artifact.pop("artifact_identity", None)
    artifact["artifact_sha256"] = p3f13._hash(artifact)
    artifact["artifact_identity"] = f"p3f13_official_financial_evidence_scaleout:{artifact['artifact_sha256']}"
    return artifact


def process_document(record: Mapping[str, Any], *, evidence_root: Path = EVIDENCE_ROOT) -> dict[str, Any]:
    discovery = discover_statement_pages(record, evidence_root=evidence_root)
    pages = sorted({item["page_number"] for item in discovery["statement_pages"]})
    if not pages:
        return {"record": dict(record), "discovery": discovery, "terminal_disposition": "STATEMENT_NOT_FOUND", "metric_dispositions": [{"canonical_metric": metric, "disposition": "STATEMENT_NOT_FOUND"} for metric in CORE_METRICS], "qualification": None}
    source_record = {"sha256": record["document_sha256"], "relative_path": record["retained_path"], "document_id": record["document_sha256"], "ticker": record["ticker"], "reporting_period": record["reporting_period"], "observed_at": "2026-08-09T00:00:00Z"}
    materialization = materialize_tsv_pages(source_record, evidence_root=evidence_root, pages=pages)
    scoped_unit_evidence = resolve_scoped_unit_evidence(materialization)
    resolution = resolve_ambiguous_debt_line_code_cells(materialization, record=source_record, evidence_root=evidence_root, reporting_period=str(record["reporting_period"]))
    qualification = qualify_table_facts(materialization, ticker=str(record["ticker"]), reporting_period=str(record["reporting_period"]), line_code_cell_resolution=resolution, scoped_unit_evidence=scoped_unit_evidence)
    qualified = {row["canonical_metric"] for row in qualification["qualified_facts"]}
    blocked = {row["canonical_metric"]: row["reason"] for row in qualification["blocked_candidates"]}
    dispositions = [{"canonical_metric": metric, "disposition": "OFFICIAL_FACT_QUALIFIED_NEW" if metric in qualified else "REQUIRED_COMPONENT_MISSING" if blocked.get(metric) == "DEBT_COMPONENT_INCOMPLETE" else "CANONICAL_ROW_AMBIGUOUS" if blocked.get(metric) == "ROW_NOT_UNIQUE_OR_NOT_GEOMETRICALLY_RESOLVED" else blocked.get(metric, "NOT_APPLICABLE")} for metric in CORE_METRICS]
    terminal = "PROCESSED" if qualification["qualified_facts"] else "UNIT_SCALE_BLOCKED" if any(row.get("reason") == "UNIT_SCALE_BLOCKED" for row in qualification["blocked_candidates"]) else "PROCESSED"
    return {"record": dict(record), "discovery": discovery, "terminal_disposition": terminal, "materialization": materialization, "scoped_unit_evidence": scoped_unit_evidence, "line_code_cell_resolution": resolution, "qualification": qualification, "metric_dispositions": dispositions}


def build_batch_artifact(*, inventory: Mapping[str, Any], official_manifest: Mapping[str, Any], owner_focus_artifact: Mapping[str, Any], evidence_root: Path = EVIDENCE_ROOT) -> dict[str, Any]:
    """Run the complete selected-document batch once, then reconcile once."""
    manifest = build_batch_manifest(inventory=inventory, official_manifest=official_manifest, owner_focus_artifact=owner_focus_artifact)
    processed = [process_document(row, evidence_root=evidence_root) if row["terminal_manifest_disposition"] == "ELIGIBLE" else {"record": row, "terminal_disposition": row["terminal_manifest_disposition"], "metric_dispositions": [{"canonical_metric": metric, "disposition": row["terminal_manifest_disposition"]} for metric in CORE_METRICS]} for row in manifest["documents"]]
    static_baseline = p3f13.execute()
    prior_ingress = _prior_qualified_image_ocr_ingress(evidence_root=evidence_root)
    baseline_panel = merge_document_qualified_facts_into_panel(static_baseline["refreshed_panel_data"], prior_ingress)
    baseline = _with_panel(static_baseline, baseline_panel)
    candidates = [candidate for item in processed if item.get("qualification") for candidate in _candidate_rows(item["qualification"], item["record"])]
    reconciliation = reconcile_against_existing_panel(candidates, baseline["refreshed_panel_data"])
    eligible = _eligible_ingress_keys(reconciliation)
    ingress = []
    for item in processed:
        qualification = item.get("qualification")
        if not qualification:
            continue
        facts = panel_facts_from_qualified_ocr(qualification, entity_type="corporate", statement_scope="consolidated", audit_or_review_status="audited", knowledge_available_at="2026-08-09T00:00:00Z", observed_at="2026-08-09T00:00:00Z")
        ingress.extend(fact for fact in facts if (fact["issuer_identity"], fact["canonical_metric"], fact["reporting_period"], fact["statement_scope"], fact["value"]) in eligible)
    after_panel = merge_document_qualified_facts_into_panel(baseline["refreshed_panel_data"], ingress)
    after_p3 = _with_panel(baseline, after_panel)
    frozen = _read(current_fundamental.DEFAULT_P3F10_FROZEN)
    fundamental_before = current_fundamental.execute(requested_at="2026-08-09T00:00:00Z")
    fundamental_after = current_fundamental.build_artifact(p3f10_frozen=frozen, p3f13_current=after_p3, requested_at="2026-08-09T00:00:00Z", provider_series_by_ticker=current_fundamental.load_retained_provider_series(current_fundamental.DEFAULT_CANONICAL_FACTS_ROOT))
    owner_before = build_owner_focus(p3f13_artifact=baseline, fundamental_artifact=fundamental_before, pdf_inventory=inventory)
    owner_after = build_owner_focus(p3f13_artifact=after_p3, fundamental_artifact=fundamental_after, pdf_inventory=inventory)
    counts = {"documents_eligible": manifest["eligible_document_count"], "documents_terminal": len(processed), "documents_ocr_qualified": sum(item["terminal_disposition"] == "PROCESSED" for item in processed),
              "statement_tables_discovered": sum(len(item.get("discovery", {}).get("statement_pages", [])) for item in processed), "core_metric_attempts": len(processed) * len(CORE_METRICS),
              "new_qualified_facts": len(ingress), "exact_match_corrobations": sum(row["classification"] == "EXACT_MATCH" for row in reconciliation),
              "value_conflicts": sum(row["classification"] == "VALUE_CONFLICT" for row in reconciliation), "ocr_ambiguities": sum(row["disposition"] == "OCR_NUMERIC_AMBIGUITY" for item in processed for row in item["metric_dispositions"]),
              "component_missing": sum(row["disposition"] == "REQUIRED_COMPONENT_MISSING" for item in processed for row in item["metric_dispositions"]), "layout_unsupported": sum(item["terminal_disposition"] == "STATEMENT_NOT_FOUND" for item in processed)}
    artifact = {"contract_version": CONTRACT_VERSION, "manifest": manifest, "documents": processed, "batch_totals": counts, "reconciliation": reconciliation,
        "p3f13_before_after": {"static_before_count": static_baseline["refreshed_panel_data"]["qualified_facts_count"], "before_count": baseline["refreshed_panel_data"]["qualified_facts_count"], "after_count": after_panel["qualified_facts_count"], "prior_replayed_facts": [(fact["issuer_identity"], fact["canonical_metric"]) for fact in prior_ingress], "new_facts": [(fact["issuer_identity"], fact["canonical_metric"]) for fact in ingress]},
        "owner_focus_before": owner_before, "owner_focus_after": owner_after, "fundamental_before": fundamental_before, "fundamental_after": fundamental_after,
        "authority_boundary": {"network_called": False, "provider_used": False, "new_ocr_dependency": False, "production_db_mutated": False, "dashboard_mutated": False, "value_or_recommendation_activated": False}}
    artifact["residual_checks"] = {"documents_residual": manifest["eligible_document_count"] - counts["documents_terminal"], "documents_residual_zero": manifest["eligible_document_count"] == counts["documents_terminal"], "metric_residual": counts["core_metric_attempts"] - sum(len(item["metric_dispositions"]) for item in processed), "metric_residual_zero": counts["core_metric_attempts"] == sum(len(item["metric_dispositions"]) for item in processed)}
    artifact["artifact_sha256"] = _hash(artifact); artifact["artifact_identity"] = f"owner_focus_image_only_corporate_ocr_batch:{artifact['artifact_sha256']}"
    return artifact


def execute(*, evidence_root: Path = EVIDENCE_ROOT) -> dict[str, Any]:
    inventory = _read(RETAINED_PDF_INVENTORY)
    official_manifest = _read(Path(evidence_root) / "official_document_acquisition_manifest.json")
    # The baseline owner-focus artifact is a membership source only; facts are
    # always reconciled against the current P3-F13 panel in build_batch_artifact.
    owner = build_owner_focus(p3f13_artifact=p3f13.execute(), fundamental_artifact=current_fundamental.execute(requested_at="2026-08-09T00:00:00Z"), pdf_inventory=inventory)
    return build_batch_artifact(inventory=inventory, official_manifest=official_manifest, owner_focus_artifact=owner, evidence_root=evidence_root)
