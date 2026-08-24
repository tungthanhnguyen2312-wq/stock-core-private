from __future__ import annotations

import hashlib

from hnx_filing_evidence_binding import parent_binding


def _document(detail: bytes, *, filing_url: str = "https://owa.hnx.vn/a.pdf") -> dict:
    return {
        "document_id": "doc", "document_sha256": "pdf-sha", "detail_url": "https://www.hnx.vn/detail.html",
        "detail_sha256": hashlib.sha256(detail).hexdigest(), "filing_url": filing_url,
        "reporting_period": "2026-H1", "title_scope": "UNKNOWN", "published_at": "2026-08-24",
    }


def test_exact_parent_attachment_and_explicit_ticker_qualifies_binding():
    detail = b'''<div class="Box-Noidung">- M\xc3\xa3 ch\xe1\xbb\xa9ng kho\xc3\xa1n: ABC</div><div class="divLstFileAttach"><a href="https://owa.hnx.vn/a.pdf">a</a></div></div>'''
    binding = parent_binding(_document(detail), detail)
    assert binding["binding_state"] == "QUALIFIED_OFFICIAL_PARENT_BINDING"
    assert binding["parent_ticker"] == "ABC"
    assert binding["document_subject_identity_source"] == "OFFICIAL_PARENT_DISCLOSURE"


def test_empty_parent_content_cannot_bind_from_attachment_filename_or_page_chrome():
    detail = b'''M\xc3\xa3 ch\xe1\xbb\xa9ng kho\xc3\xa1n: ABC<div class="Box-Noidung"></div><div class="divLstFileAttach"><a href="https://owa.hnx.vn/a.pdf">ABC_report.pdf</a></div></div>'''
    binding = parent_binding(_document(detail), detail)
    assert binding["binding_state"] == "OFFICIAL_PARENT_BINDING_UNPROVEN"
    assert binding["binding_reason"] == "PARENT_TICKER_MISSING"


def test_duplicate_parent_attachment_is_not_a_one_to_one_binding():
    detail = b'''<div class="Box-Noidung">- M\xc3\xa3 ch\xe1\xbb\xa9ng kho\xc3\xa1n: ABC</div><div class="divLstFileAttach"><a href="https://owa.hnx.vn/a.pdf">a</a><a href="https://owa.hnx.vn/a.pdf">a</a></div></div>'''
    binding = parent_binding(_document(detail), detail)
    assert binding["binding_reason"] == "ATTACHMENT_RELATION_NOT_ONE_TO_ONE"
