"""Document-level assurance (audited vs reviewed) evidence for official financial statements.

The OCR panel adapter previously accepted only the literal ``"audited"``.  Reviewed
interim statements (``Báo cáo soát xét``) are a distinct assurance state, not an upgrade
of audited.  This module owns the single allowed-status vocabulary and the recognizer
that proves a status from retained page tokens.  A caller-supplied status string is a
claim, never proof: the reviewed state is only valid together with evidence produced here.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

CONTRACT_VERSION = "official_financial_assurance_evidence/v1"
AUDITED = "audited"
REVIEWED = "reviewed"
ALLOWED_ASSURANCE_STATUSES = frozenset({AUDITED, REVIEWED})

_REVIEW_TITLE = ("bao", "cao", "soat", "xet")
_AUDIT_TITLE = ("bao", "cao", "kiem", "toan", "doc", "lap")
_REVIEW_ENGAGEMENT = ("hop dong dich vu soat xet", "soat xet so 2410")
_REVIEW_DISCLAIMER = "khong dua ra y kien kiem toan"
_AUDIT_OPINION = ("chung toi da kiem toan", "y kien kiem toan cua chung toi")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _normalize(value: str) -> str:
    from official_financial_ocr_table_evidence import _normalize as normalize
    return normalize(value)


def assurance_status_is_qualified(status: Any) -> bool:
    """The one contract: only explicit ``audited`` or ``reviewed`` may ingress."""
    return isinstance(status, str) and status in ALLOWED_ASSURANCE_STATUSES


def _ordered(tokens: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(tokens, key=lambda token: int(token.get("raw_token_order", 0)))


def _title_span(tokens: Sequence[Mapping[str, Any]], title: Sequence[str]) -> list[Mapping[str, Any]] | None:
    """Consecutive OCR tokens whose normalized text equals ``title`` (in reading order)."""
    words = [(_normalize(str(token.get("text", ""))), token) for token in _ordered(tokens)]
    words = [(word, token) for word, token in words if word]
    for start in range(len(words) - len(title) + 1):
        if all(words[start + offset][0] == title[offset] for offset in range(len(title))):
            return [words[start + offset][1] for offset in range(len(title))]
    return None


def _page_text(tokens: Sequence[Mapping[str, Any]]) -> str:
    return _normalize(" ".join(str(token.get("text", "")) for token in _ordered(tokens)))


def resolve_document_assurance_evidence(materialization: Mapping[str, Any]) -> dict[str, Any]:
    """Prove reviewed/audited status from OCR page tokens of one retained document.

    Reviewed requires, on one page: the report title ``BÁO CÁO SOÁT XÉT``, wording that
    scopes it to *consolidated* and *interim* statements, and the review engagement
    (VSRE 2410).  A page that carries the audit-report title is an audit candidate; a
    document with both kinds of page, or none, is not resolved.  Filename, issuer or period
    convention and caller arguments are never consulted.
    """
    document_sha = str(materialization.get("document_sha256") or "")
    reviewed: list[dict[str, Any]] = []
    audited: list[dict[str, Any]] = []
    for page in materialization.get("pages") or []:
        tokens = (page.get("ocr_derived_text_evidence") or {}).get("tokens") or []
        if not tokens:
            continue
        text = _page_text(tokens)
        number = int(page.get("page_number", 0))
        review_title = _title_span(tokens, _REVIEW_TITLE)
        audit_title = _title_span(tokens, _AUDIT_TITLE)
        if review_title and not audit_title:
            engagement = [phrase for phrase in _REVIEW_ENGAGEMENT if phrase in text]
            if engagement and "hop nhat" in text and "giua nien do" in text:
                anchors = ["bao cao soat xet", *engagement, "hop nhat", "giua nien do"]
                if _REVIEW_DISCLAIMER in text:
                    anchors.append(_REVIEW_DISCLAIMER)
                reviewed.append({"page_number": number, "title_tokens": review_title, "anchors": anchors, "text": text, "page": page})
        elif audit_title and not review_title and any(phrase in text for phrase in _AUDIT_OPINION) and _REVIEW_DISCLAIMER not in text:
            audited.append({"page_number": number, "title_tokens": audit_title, "anchors": ["bao cao kiem toan doc lap"], "text": text, "page": page})
    base = {"contract_version": CONTRACT_VERSION, "document_sha256": document_sha}
    if reviewed and audited:
        return {**base, "state": "BLOCKED", "reason": "ASSURANCE_STATUS_AMBIGUOUS", "audit_or_review_status": None}
    hits, status = (reviewed, REVIEWED) if reviewed else (audited, AUDITED)
    if not hits:
        return {**base, "state": "BLOCKED", "reason": "ASSURANCE_STATUS_NOT_EXPLICIT", "audit_or_review_status": None}
    hit = sorted(hits, key=lambda item: item["page_number"])[0]
    image = hit["page"].get("source_image_evidence") or {}
    span = {"token_ids": [str(token.get("token_id", "")) for token in hit["title_tokens"]],
            "raw_token_order": [int(token.get("raw_token_order", 0)) for token in hit["title_tokens"]]}
    evidence_id = _hash({"contract": CONTRACT_VERSION, "document_sha256": document_sha, "page_number": hit["page_number"],
                         "status": status, "anchors": hit["anchors"], "title_span": span,
                         "rendered_image_sha256": image.get("rendered_image_sha256"),
                         "materialization_id": materialization.get("materialization_id")})
    return {**base, "state": "QUALIFIED", "audit_or_review_status": status, "page_number": hit["page_number"],
            "scope_of_assurance": "consolidated_interim_statements" if status == REVIEWED else "consolidated_statements",
            "matched_anchors": hit["anchors"], "title_span": span,
            "page_text_sha256": _hash(hit["text"]), "rendered_image_sha256": image.get("rendered_image_sha256"),
            "materialization_id": materialization.get("materialization_id"),
            "evidence_id": evidence_id, "citation_id": evidence_id,
            "inheritance": "document_level_report_applies_to_all_statements_in_document"}


def validate_assurance_claim(status: Any, evidence: Mapping[str, Any] | None, *, document_sha256: str) -> dict[str, Any] | None:
    """Fail closed unless the claim is an allowed status backed by matching evidence.

    ``audited`` keeps its pre-existing caller contract (evidence optional, but if given it
    must agree).  ``reviewed`` is never accepted on the caller's word.
    """
    if not assurance_status_is_qualified(status):
        raise ValueError("OCR_DOCUMENT_METADATA_NOT_QUALIFIED")
    if evidence is None:
        if status == REVIEWED:
            raise ValueError("REVIEWED_STATUS_REQUIRES_RETAINED_DOCUMENT_EVIDENCE")
        return None
    if (evidence.get("state") != "QUALIFIED" or evidence.get("audit_or_review_status") != status
            or evidence.get("document_sha256") != document_sha256 or not evidence.get("evidence_id")):
        raise ValueError("ASSURANCE_EVIDENCE_DOES_NOT_SUPPORT_STATUS")
    return dict(evidence)
