"""Fetch the one authorized QNS detail page and bind the already retained PDF.

Budget is printed before the request. The index is not refreshed. A matching
retained PDF is not downloaded. No new OCR profile is run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from financial_evidence_currency_contract import DEFAULT_LANDING_ROOT
from stocklookup_core.evidence.official_document_acquisition import fetch_http
import qns_h1_official_detail_resolver as resolver

FIXTURE = ROOT / "tests/fixtures/triad_current_h1/qns_h1_positioned_tokens.json"
PDF = Path(DEFAULT_LANDING_ROOT) / "triad-h1-evidence-20261008/documents/QNS/2026-H1/reviewed_interim_financial_statements" / f"{resolver.RETAINED_PDF_SHA256}.pdf"
REPORT = ROOT / "derived/financial-evidence-currency-refresh-v1/qns_h1_detail_resolver_report.json"


def _content_type(headers: dict) -> str:
    return str(headers.get("Content-Type") or headers.get("content-type") or "").split(";", 1)[0].lower()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--pdf", type=Path, default=PDF)
    args = parser.parse_args(argv)
    budget = resolver.declared_budget()
    print(json.dumps({"budget_declared_before_http": budget}, ensure_ascii=True))
    requests_used = 0

    def before_request() -> None:
        nonlocal requests_used
        requests_used += 1
        if requests_used > budget["total_requests_including_redirects_retries_max"]:
            raise ValueError("HTTP_REQUEST_CAP_REACHED")

    def admit(target: str) -> bool:
        host = (target.split("/")[2] if "://" in target else "").split(":")[0].casefold()
        return host in resolver.ADMITTED_HOSTS

    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "detail.html"
        status, headers, _prefix, final_url = fetch_http(
            resolver.DETAIL_URL, temporary_path=target, before_request=before_request,
            admit_hop=admit, max_redirects=4, max_response_bytes=resolver.STORAGE_CEILING_BYTES,
        )
        body = target.read_bytes() if target.is_file() else _prefix
    if not 200 <= status < 300:
        raise SystemExit(f"DETAIL_PAGE_HTTP_{status}")
    detail = {
        "final_url": final_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(body).hexdigest(),
        "content_type": _content_type(dict(headers)),
    }
    selection = resolver.select_statement(final_url, body)
    if selection["state"] != "PDF_LOCATOR_ON_ADMITTED_QNS_HOST":
        report = {"milestone_id": resolver.MILESTONE_ID, "budget": budget, "detail_page": detail,
                  "selection": selection, "requests_used": requests_used,
                  "terminal_disposition": resolver.terminal_disposition(selection["state"], [])}
    else:
        binding = resolver.bind_retained_pdf(selection["selected_locator"], args.pdf)
        if binding["request_required"]:
            raise SystemExit("PDF_BODY_DIFFERS_FROM_RETAINED_STATEMENT")
        materialization = json.loads(FIXTURE.read_text(encoding="utf-8"))
        if materialization["document_sha256"] != binding["sha256"]:
            raise SystemExit("FIXTURE_DOES_NOT_MATCH_RETAINED_PDF")
        report = resolver.build_report(
            detail=detail, selection=selection, pdf_binding=binding,
            representation=resolver.classify_representation(materialization),
            attempt=resolver.attempt_priority_facts(materialization), requests_used=requests_used,
        )
    if args.write:
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
