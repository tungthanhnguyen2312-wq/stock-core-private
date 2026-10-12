"""Owned synthetic sources for independent E5/E6 execution; never official evidence."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile

from tests.test_official_financial_source_integrity import proved_fixture


def capture(call):
    try:
        return {"result": call()}
    except Exception as error:
        return {"error": type(error).__name__, "message": str(error)}


def metadata_candidate():
    sha = "a" * 64
    values = {"reporting_period": "2025", "periodicity": "annual",
              "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1}
    return {"issuer_identity": "synthetic", "entity_type": "corporate",
        "document": {"document_id": "owned-synthetic", "sha256": sha,
            "source_locator": "https://synthetic.invalid/test-only.pdf",
            "observed_at": "2026-10-07T00:00:00Z", "immutable_bytes_verified": True},
        "metadata": {name: {"value": value, "evidence_span": {
            "citation_id": "owned:"+name, "document_sha256": sha, "source_page": 1,
            "text": str(value), "citation_kind": "test-only"}} for name, value in values.items()}}


def metadata_cases():
    cases = [metadata_candidate(), {}, {"document": None}, {"metadata": []}]
    for field in ("reporting_period", "periodicity", "statement_scope", "currency", "unit_scale"):
        for change in ("missing", "null", "wrong_hash", "wrong_page", "missing_text"):
            value = metadata_candidate()
            if change == "missing":
                value["metadata"].pop(field)
            elif change == "null":
                value["metadata"][field]["value"] = None
            else:
                key, item = {"wrong_hash": ("document_sha256", "b"*64),
                    "wrong_page": ("source_page", 0), "missing_text": ("text", "")}[change]
                value["metadata"][field]["evidence_span"][key] = item
            cases.append(value)
    for key, item in (("statement_scope", "separate"), ("currency", "USD"),
                      ("unit_scale", 1000000), ("reporting_period", "2026-H1")):
        value = metadata_candidate(); value["metadata"][key]["value"] = item; cases.append(value)
    for key, item in (("sha256", "bad"), ("immutable_bytes_verified", False),
                      ("observed_at", None), ("document_id", None)):
        value = metadata_candidate(); value["document"][key] = item; cases.append(value)
    return cases


LABEL_CASES = [(metric, label) for metric in (
    "total_assets", "net_income", "attributable_net_income", "investment_property_disposal_result",
    "provision_charge_or_reversal_adjustment", "short_term_borrowings",
    "long_term_borrowings_or_finance_leases", "unknown_metric") for label in (
    "", "TỔNG CỘNG TÀI SẢN", "Tài sản dài hạn khác", "Profit after tax of the parent",
    "Lợi nhuận sau thuế", "Provisions", "Provisi²ns", "Provisions extra",
    "thanh lý bất động sản đầu tư", "Vay ngắn hạn", "Phải trả dài hạn khác", None, 42)]


def consumer_outputs(*, include_native=False):
    # Even implicit legacy source replay resolves only this owned empty root.
    # Restore the caller's environment after the contained fixture execution.
    key = 'STOCK_LOOKUP_RUNTIME_ROOT'
    previous = os.environ.get(key)
    with tempfile.TemporaryDirectory(prefix='e6-isolated-replay-') as directory:
        os.environ[key] = directory
        try:
            return _consumer_outputs(include_native=include_native)
        finally:
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


def _consumer_outputs(*, include_native=False):
    import official_financial_filing_evidence as filing
    import financial_evidence_currency_refresh as refresh
    import official_financial_ocr_table_evidence as ocr
    import official_financial_pdf_page_evidence as pdf
    import official_financial_assurance_evidence as assurance
    import official_legacy_precedence as precedence
    import canonical_financial_qualification_policy as policy
    from stocklookup_core.evidence import official_document_qualification as registration
    from tests.test_reviewed_interim_canonical_ingress import _facts, _reviewed_evidence
    import reviewed_interim_canonical_ingress as ingress
    result = {"metadata": [capture(lambda value=value: filing.qualify_document_metadata(value))
                           for value in metadata_cases()],
              "labels": [capture(lambda m=m, label=label: ocr.row_label_supports_metric(m, label))
                         for m, label in LABEL_CASES]}
    result["pages"] = []
    headings = ["financial year ended 31 December 2025\nconsolidated\nUnit: VND",
        "six months ended 30 June 2026\nconsolidated\nUnit: million USD",
        "second quarter 2026\nstandalone\nUnit: thousand VND",
        "third quarter 2026\nconsolidated\nUnit: VND", "²0²6 missing", ""]
    document = {"ticker": "PNJ", "document_id": "owned-synthetic", "sha256": "a"*64,
                "canonical_url": "https://synthetic.invalid/test-only.pdf",
                "observed_at": "2026-10-07T00:00:00Z", "immutable_bytes_verified": True}
    page_inputs = [{1: text} for text in headings]+[{1: headings[0], 2: headings[1]},
        {1: headings[0], 2: "standalone USD Unit: million VND"}, {9: headings[0]}]
    for pages in page_inputs:
        result["pages"].append(capture(lambda: refresh._metadata_from_pages(pages, document)))
    result["admission"] = []; result["extraction"] = []; result["registration"] = []
    for period in ("2025", "2026-H1", "2026-Q2"):
        row, context = proved_fixture(period)
        for use in ("CURRENT_RESEARCH_FACTUAL_AUTHORITY", "CANONICAL_CITATION", "VALUATION_INPUT_WHERE_METRIC_PERMITS", "UNSUPPORTED"):
            result["admission"].append(filing.admit_official_financial_fact(row, intended_use=use, **context))
        for key, value in (("statement_scope", "standalone"), ("currency", "USD"),
            ("line_code", "61"), ("raw_row_label", "Provisi²ns"), ("raw_value_text", "12O"),
            ("knowledge_available_at", "2026-10-09T00:00:00Z"), ("document_metadata", {}),
            ("assurance_evidence", {}), ("source_unit_scale", True), ("citation_id", None)):
            altered = copy.deepcopy(row); altered[key] = value
            result["admission"].append(filing.admit_official_financial_fact(altered, cutoff="2026-10-08T00:00:00Z", **context))
        result["admission"].append(filing.admit_official_financial_fact(row))
        bound = {**context["source_record"], "document_metadata": row["document_metadata"],
            "audit_or_review_status": row["audit_or_review_status"], "assurance_evidence": row["assurance_evidence"],
            "_source_record": context["source_record"], "_retained_bytes": context["retained_bytes"],
            "_source_registry": context["registry"], "_document_pages": context["document_pages"]}
        fact = {**row, "qualification_status": "OFFICIAL_FACT_QUALIFIED", "unit_scale": 1,
                "page_number": 1, "table_id": row["citation_id"]}
        result["extraction"].append(refresh._qualify_extracted_fact(fact, bound))
        result["assurance_"+period] = assurance.resolve_native_document_assurance(row["document_sha256"], context["document_pages"])
        # Native owned PDF registration exercises actual physical hash, parser and
        # metadata/assurance gates. Only this isolated temporary directory is writable.
        if not include_native:
            continue
        native_row, native_context = proved_fixture(period, native_pdf=True)
        with tempfile.TemporaryDirectory(prefix="e6-owned-source-") as directory:
            target = Path(directory); (target/"fixture.pdf").write_bytes(native_context["retained_bytes"])
            source = native_context["source_record"]
            for change in ("intact", "tampered", "missing"):
                if change == "tampered": (target/"fixture.pdf").write_bytes(b"owned invalid PDF")
                if change == "missing": (target/"fixture.pdf").unlink()
                record = registration.qualify_retained_document(source, evidence_root=target,
                    registry=native_context["registry"], verified_at="2026-10-08T00:00:00Z")
                registration.persist_document_qualification(record, target/"qualification.json")
                result["registration"].append({"record": record.to_dict(),
                    "serialized_sha256": hashlib.sha256((target/"qualification.json").read_bytes()).hexdigest()})
            # Actual PDF text extraction is immutable and local, independent of registration.
            (target/"fixture.pdf").write_bytes(native_context["retained_bytes"])
            result["native_"+period] = capture(lambda: pdf.build_artifact(document={**source,
                "official_url": source["canonical_url"], "retrieved_at": source["observed_at"]}, path=target/"fixture.pdf"))
    facts = _facts(evidence=_reviewed_evidence())
    rows, blocked = ingress.overlay_rows_from_panel_facts(facts)
    result["ocr_panel"] = facts; result["ingress"] = {"rows": rows, "blocked": blocked}
    result["precedence"] = [precedence.compare_official_and_legacy(None, None),
        precedence.compare_official_and_legacy(rows[0] if rows else None, None)]
    result["policy"] = policy.evaluate_fact({"ticker": "PNJ", "canonical_metric": "revenue",
        "reporting_period": "2026-H1", "statement_scope": "consolidated", "currency": "VND"}, evidence_index={})
    return result
