"""Deterministic audit/review-opinion classification from already-retained official filings.

WHAT THIS IS
    A two-stage, citation-bound classifier over page text already produced by the existing
    `pypdf`-based extraction path (`official_document_store.assess_parser_state` /
    `official_document_acquisition._extraction_state`). It acquires nothing and OCRs nothing:
    it reads whatever text the existing governed extraction already produced for a retained
    `audited_annual_financial_statements` or `reviewed_interim_financial_statements` document,
    and only ever runs on documents that store already marked `ready_for_direct_citations`.

WHY TWO STAGES, NOT ONE REGEX
    A bare keyword match on "opinion" or "except for" is not a classification -- "ngoại trừ"
    (except for) appears constantly in footnotes unrelated to the audit opinion, and "opinion"
    appears in a director's report too. Stage 1 requires an auditor's-report section *heading*
    cue (Vietnamese or English) to anchor a page as plausibly containing the opinion at all.
    Stage 2 only looks for a classification cue inside a bounded window after that anchor.
    Neither stage alone is authoritative; a result without both is `UNKNOWN`, never a guess.

WHAT A POSITIVE RESULT MEANS, AND WHAT IT DOES NOT
    `opinion_type` reports what the retained document's own text says under its own
    auditor's-report heading, with the exact page, character offset and excerpt that produced
    the classification. It creates no downstream strategy, eligibility, or ranking effect --
    that is an explicit, separate, later policy decision this milestone does not make.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

VERSION = "1.0.0"

UNMODIFIED = "UNMODIFIED"
QUALIFIED = "QUALIFIED"
ADVERSE = "ADVERSE"
DISCLAIMER = "DISCLAIMER"
GOING_CONCERN_MATERIAL_UNCERTAINTY = "GOING_CONCERN_MATERIAL_UNCERTAINTY"
UNKNOWN = "UNKNOWN"

#: Stage 1: is this page even plausibly the auditor's own report, not a director's report, a
#: supervisory-board report, or the notes to the financial statements (all of which can contain
#: the word "opinion"/"ý kiến" without being the auditor's opinion section)?
_SECTION_ANCHORS = (
    "independent auditor's report", "independent auditors' report", "report of independent auditors",
    "báo cáo kiểm toán độc lập", "báo cáo của kiểm toán viên độc lập",
)

#: Stage 2, most specific first so e.g. a going-concern qualification is not mis-read as a bare
#: qualified opinion. Every cue is checked only inside a bounded window after a Stage-1 anchor.
_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (DISCLAIMER, ("disclaimer of opinion", "we do not express an opinion",
                 "từ chối đưa ra ý kiến", "không thể đưa ra ý kiến", "từ chối nhận xét")),
    (ADVERSE, ("adverse opinion", "do not present fairly, in all material respects",
              "ý kiến trái ngược", "không phản ánh trung thực và hợp lý")),
    (GOING_CONCERN_MATERIAL_UNCERTAINTY,
     ("material uncertainty related to going concern", "material uncertainty relating to going concern",
      "significant doubt", "yếu tố không chắc chắn trọng yếu", "khả năng hoạt động liên tục",
      "nghi ngờ đáng kể về khả năng hoạt động liên tục")),
    (QUALIFIED, ("qualified opinion", "except for the effects of", "except for the possible effects of",
                "ý kiến kiểm toán ngoại trừ", "ngoại trừ ảnh hưởng của")),
    (UNMODIFIED, ("unqualified opinion", "in our opinion", "present fairly, in all material respects",
                 "give a true and fair view", "theo ý kiến của chúng tôi",
                 "đã phản ánh trung thực và hợp lý")),
)

_WINDOW_CHARS = 4000


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def find_section_anchor(page_text: str) -> dict[str, Any] | None:
    """First auditor's-report heading cue on this page, with its character offset, or None."""
    lowered = page_text.lower()
    best: tuple[int, str] | None = None
    for cue in _SECTION_ANCHORS:
        index = lowered.find(cue)
        if index != -1 and (best is None or index < best[0]):
            best = (index, cue)
    if best is None:
        return None
    offset, cue = best
    return {"cue": cue, "offset": offset,
           "excerpt": _normalize(page_text[offset:offset + 200])}


def classify_page(page_text: str) -> dict[str, Any]:
    """Two-stage classification of one already-extracted page's text. Never OCRs, never guesses
    past what the two stages both confirm."""
    anchor = find_section_anchor(page_text)
    if anchor is None:
        return {"opinion_type": UNKNOWN, "reason": "no_auditors_report_section_heading_found",
                "section_anchor": None, "cue": None, "citation_excerpt": None}
    window = page_text[anchor["offset"]: anchor["offset"] + _WINDOW_CHARS]
    lowered_window = window.lower()
    for opinion_type, cues in _CUES:
        for cue in cues:
            index = lowered_window.find(cue)
            if index != -1:
                absolute = anchor["offset"] + index
                excerpt = _normalize(page_text[max(0, absolute - 80): absolute + len(cue) + 80])
                return {"opinion_type": opinion_type, "reason": "section_anchor_and_cue_both_found",
                       "section_anchor": anchor, "cue": cue,
                       "citation_offset": absolute, "citation_excerpt": excerpt}
    return {"opinion_type": UNKNOWN,
           "reason": "auditors_report_heading_found_but_no_classification_cue_in_window",
           "section_anchor": anchor, "cue": None, "citation_excerpt": None}


def evaluate_document(*, document_id: str, content_sha256: str, ticker: str,
                      reporting_period: str, document_type: str, parser_status: str,
                      page_texts: Iterable[str]) -> dict[str, Any]:
    """Classify one retained document's opinion, or report exactly why it cannot be, citing
    the page. `page_texts` must come from the document's own already-extracted text -- this
    function performs no extraction and no OCR itself."""
    base = {"schema_version": VERSION, "document_id": document_id, "document_sha256": content_sha256,
           "ticker": str(ticker).upper(), "reporting_period": str(reporting_period),
           "document_type": document_type}
    if parser_status != "ready_for_direct_citations":
        return base | {"opinion_type": UNKNOWN, "qualification": "EXTRACTION_BLOCKED",
                       "reason": f"store parser_status={parser_status!r}; this module never OCRs",
                       "page": None, "citation_excerpt": None}
    pages = list(page_texts)
    for page_index, text in enumerate(pages):
        if not text or not text.strip():
            continue
        result = classify_page(text)
        if result["opinion_type"] != UNKNOWN:
            return base | {"opinion_type": result["opinion_type"], "qualification": "EXTRACTED",
                           "reason": result["reason"], "page": page_index,
                           "section_anchor": result["section_anchor"], "cue": result["cue"],
                           "citation_excerpt": result["citation_excerpt"]}
    non_empty = sum(1 for text in pages if text and text.strip())
    return base | {
        "opinion_type": UNKNOWN, "qualification": "NOT_IDENTIFIED",
        "reason": ("no_extractable_text_on_any_page" if non_empty == 0 else
                  "no_auditors_report_section_heading_found_on_any_extracted_page"),
        "pages_with_text": non_empty, "pages_total": len(pages),
        "page": None, "citation_excerpt": None,
    }
