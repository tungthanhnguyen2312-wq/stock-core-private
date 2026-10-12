"""Same official filing, different machine representation.

Source authority and representation fitness stay separate. A parallel-language
scan is still official. It does not become a better authority because a later
reader hopes it will OCR more cleanly, and it does not authorize a repair of
the corrupted scan it sits beside.

This module does not fetch, OCR, or rewrite a numeric token.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

CONTRACT = "official_financial_representation/v1"
MILESTONE_ID = "OFFICIAL_FINANCIAL_DOCUMENT_REPRESENTATION_RECOVERY_V1"
DISPOSITION = "OFFICIAL_REPRESENTATION_BOTTLENECK_CONFIRMED"
NORMALIZATION = "SOURCE_FAITHFUL_NORMALIZATION_NOT_YET_PROVABLE"
KNOWLEDGE_AVAILABLE_AT = "2026-10-08T05:25:33.387067Z"
OCTOBER_7_CUTOFF = "2026-10-08T00:00:00Z"

REPRESENTATION_CLASSES = (
    "PRIMARY_OFFICIAL_PDF_SCAN",
    "PRIMARY_OFFICIAL_PDF_NATIVE_TEXT",
    "OFFICIAL_PARALLEL_LANGUAGE_PDF",
    "OFFICIAL_HTML_STATEMENT",
    "OFFICIAL_SPREADSHEET",
    "OFFICIAL_EXCHANGE_MIRROR",
    "OFFICIAL_ATTACHMENT_VARIANT",
)
PARSEABLE_FITNESS = frozenset({
    "PRIMARY_OFFICIAL_PDF_NATIVE_TEXT",
    "OFFICIAL_HTML_STATEMENT",
    "OFFICIAL_SPREADSHEET",
})
IMAGE_ONLY_CLASSES = frozenset({
    "PRIMARY_OFFICIAL_PDF_SCAN",
    "OFFICIAL_PARALLEL_LANGUAGE_PDF",
    "OFFICIAL_EXCHANGE_MIRROR",
    "OFFICIAL_ATTACHMENT_VARIANT",
})
IDENTITY_FIELDS = ("issuer", "reporting_period", "scope", "assurance", "statement_family")
IDENTITY_PROOFS = frozenset({
    "EXPLICIT_OFFICIAL_CROSS_LINK",
    "SAME_FILING_PUBLICATION",
    "OFFICIAL_LANGUAGE_COUNTERPART",
    "OFFICIAL_EXCHANGE_MIRROR",
    "SAME_TITLE_DATE_AND_REFERENCE",
})
RECOVERED = "RECOVERED_FROM_INDEPENDENT_OFFICIAL_REPRESENTATION"
NO_ALTERNATE = "NO_ALTERNATE_REPRESENTATION_FOUND"
IDENTITY_NOT_PROVABLE = "REPRESENTATION_IDENTITY_NOT_PROVABLE"
STILL_AMBIGUOUS = "ALTERNATE_REPRESENTATION_STILL_AMBIGUOUS"
IMAGE_ONLY = "ALTERNATE_OFFICIAL_REPRESENTATION_IMAGE_ONLY"


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def source_document_identity(document: Mapping[str, Any]) -> dict[str, str]:
    """The filing, independent of which file bytes carry it."""
    return {field: _text(document.get(field)) for field in IDENTITY_FIELDS}


def representation_identity(document: Mapping[str, Any]) -> dict[str, Any]:
    """The bytes and machine-readable form of one copy."""
    return {
        "representation_class": _text(document.get("representation_class")),
        "sha256": _text(document.get("sha256")),
        "native_text_characters": int(document.get("native_text_characters") or 0),
        "ocr_engine": _text(document.get("ocr_engine")),
        "pixel_sha256": _text(document.get("pixel_sha256")),
    }


def filing_identity_decision(candidate: Mapping[str, Any], original: Mapping[str, Any]) -> dict[str, Any]:
    """Prove or refuse that two documents are the same filing."""
    left = source_document_identity(original)
    right = source_document_identity(candidate)
    mismatches = [field for field in IDENTITY_FIELDS if left[field] != right[field] or not left[field]]
    proof = _text(candidate.get("identity_proof"))
    reasons: list[str] = []
    if candidate.get("official_source") is not True:
        reasons.append("UNOFFICIAL_MIRROR")
    if "reporting_period" in mismatches:
        reasons.append("DIFFERENT_PERIOD")
    if "scope" in mismatches:
        reasons.append("DIFFERENT_SCOPE")
    if mismatches:
        reasons.append("SOURCE_DOCUMENT_IDENTITY_MISMATCH")
    if proof not in IDENTITY_PROOFS:
        reasons.append("IDENTITY_PROOF_ABSENT")
    same = not reasons
    return {
        "same_filing": same,
        "source_document_identity": left if same else None,
        "representation_identities_distinct": representation_identity(candidate) != representation_identity(original),
        "identity_proof": proof if same else None,
        "reasons": reasons,
    }


def independently_parseable(candidate: Mapping[str, Any], original: Mapping[str, Any]) -> dict[str, Any]:
    """Two OCR passes of the same pixels are one representation."""
    same_pixels = bool(candidate.get("pixel_sha256")) and candidate.get("pixel_sha256") == original.get("pixel_sha256")
    same_engine = bool(candidate.get("ocr_engine")) and candidate.get("ocr_engine") == original.get("ocr_engine")
    if same_pixels and same_engine:
        return {"independent": False, "reason": "SAME_OCR_PIXELS"}
    if int(candidate.get("native_text_characters") or 0) > 0 and candidate.get("representation_class") in {
        "PRIMARY_OFFICIAL_PDF_NATIVE_TEXT", "OFFICIAL_PARALLEL_LANGUAGE_PDF", "OFFICIAL_EXCHANGE_MIRROR",
    }:
        return {"independent": True, "reason": "NATIVE_TEXT_LAYER"}
    if candidate.get("representation_class") in {"OFFICIAL_HTML_STATEMENT", "OFFICIAL_SPREADSHEET"}:
        return {"independent": True, "reason": candidate["representation_class"]}
    if int(candidate.get("native_text_characters") or 0) == 0:
        return {"independent": False, "reason": "IMAGE_ONLY_NO_NATIVE_TEXT"}
    return {"independent": False, "reason": "REPRESENTATION_NOT_PARSEABLE"}


def compare_exposed_values(original: Mapping[str, Any] | None, alternate: Mapping[str, Any] | None) -> dict[str, Any]:
    """Compare two already-exposed values. No side wins a true conflict."""
    if not original or not alternate:
        return {"classification": "NOT_COMPARABLE", "reason": "VALUE_NOT_EXPOSED"}
    keys = ("sign", "magnitude", "unit", "currency", "reporting_period", "scope")
    if any(original.get(key) != alternate.get(key) for key in ("sign", "magnitude")) and original.get("unit") != alternate.get("unit"):
        return {"classification": "PRESENTATION_SCALE_DIFFERENCE", "winner": None}
    if original.get("currency") != alternate.get("currency"):
        return {"classification": "CURRENCY_PRESENTATION_DIFFERENCE", "winner": None}
    if original.get("scope") != alternate.get("scope"):
        return {"classification": "SCOPE_DIFFERENCE", "winner": None}
    if all(original.get(key) == alternate.get(key) for key in keys):
        return {"classification": "EXACT_MATCH", "winner": None}
    return {"classification": "TRUE_CONFLICT", "winner": None}


def extraction_preference(listed: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Prefer a parseable copy only inside one explicitly listed filing.

    Image-only twins get no extraction preference. Authority is not ranked.
    """
    if len(listed) < 2:
        return {"prefer": None, "reason": "NO_EXPLICIT_ALTERNATIVE", "authority_changed": False}
    identities = {tuple(source_document_identity(item).values()) for item in listed}
    proofs = {item.get("identity_proof") for item in listed}
    if len(identities) != 1 or not identities.pop()[0] or not proofs <= IDENTITY_PROOFS:
        return {"prefer": None, "reason": "SAME_FILING_NOT_EXPLICIT", "authority_changed": False}
    parseable = [item for item in listed if item.get("representation_class") in PARSEABLE_FITNESS
                 or int(item.get("native_text_characters") or 0) > 0]
    if not parseable:
        return {"prefer": None, "reason": "NO_FITTER_REPRESENTATION", "authority_changed": False}
    chosen = parseable[0]
    return {
        "prefer": chosen.get("sha256"),
        "reason": "REPRESENTATION_FITNESS_ONLY",
        "authority_changed": False,
        "source_authority": "EQUAL_WHEN_SAME_OFFICIAL_FILING",
    }


def assess_target(target: Mapping[str, Any]) -> dict[str, Any]:
    """Classify one blocked fact. Never repair the original token."""
    original = target["original"]
    alternate = target.get("alternate")
    raw_token = original.get("raw_token")
    base = {
        "issuer": target["issuer"],
        "fact": target["fact"],
        "reporting_period": target["reporting_period"],
        "original_representation": original.get("representation_class"),
        "original_sha256": original.get("sha256"),
        "raw_token_preserved": raw_token,
        "normalization": NORMALIZATION,
        "superscript_repair_applied": False,
        "knowledge_available_at": KNOWLEDGE_AVAILABLE_AT,
        "excluded_from_completed_october_7": True,
        "valuation_effect": "NONE",
        "share_continuity_inferred": False,
    }
    if alternate is None:
        return {**base, "outcome": NO_ALTERNATE, "alternate_representation": None,
                "value_comparison": compare_exposed_values(None, None), "recovered_fact": None}
    identity = filing_identity_decision(alternate, original)
    independence = independently_parseable(alternate, original)
    comparison = compare_exposed_values(target.get("original_exposed_value"), target.get("alternate_exposed_value"))
    record = {
        **base,
        "alternate_representation": alternate.get("representation_class"),
        "alternate_sha256": alternate.get("sha256"),
        "identity": identity,
        "independence": independence,
        "value_comparison": comparison,
        "recovered_fact": None,
    }
    if not identity["same_filing"]:
        record["outcome"] = IDENTITY_NOT_PROVABLE
        return record
    if not independence["independent"]:
        record["outcome"] = IMAGE_ONLY if independence["reason"] == "IMAGE_ONLY_NO_NATIVE_TEXT" else STILL_AMBIGUOUS
        return record
    if comparison["classification"] == "TRUE_CONFLICT":
        record["outcome"] = "TRUE_CONFLICT_PRESERVED"
        return record
    exposed = target.get("alternate_exposed_value")
    if not exposed or exposed.get("magnitude") is None:
        record["outcome"] = STILL_AMBIGUOUS
        return record
    record["outcome"] = RECOVERED
    record["recovered_fact"] = {
        "issuer": target["issuer"],
        "fact": target["fact"],
        "magnitude": exposed["magnitude"],
        "currency": exposed.get("currency"),
        "unit": exposed.get("unit"),
        "scope": alternate.get("scope"),
        "reporting_period": alternate.get("reporting_period"),
        "citation_sha256": alternate.get("sha256"),
        "citation_representation_class": alternate.get("representation_class"),
        "original_scan_sha256": original.get("sha256"),
        "original_raw_token_not_used": raw_token,
        "knowledge_available_at": KNOWLEDGE_AVAILABLE_AT,
        "excluded_from_completed_october_7": KNOWLEDGE_AVAILABLE_AT >= OCTOBER_7_CUTOFF,
    }
    return record


def packet_provenance(assessment: Mapping[str, Any]) -> list[dict[str, Any]]:
    """A packet row cites the representation that supplied the value."""
    fact = assessment.get("recovered_fact")
    if assessment.get("outcome") != RECOVERED or not fact:
        return []
    if fact.get("citation_sha256") == assessment.get("original_sha256"):
        return []
    return [{
        "issuer": fact["issuer"],
        "fact": fact["fact"],
        "citation_sha256": fact["citation_sha256"],
        "citation_representation_class": fact["citation_representation_class"],
        "knowledge_available_at": fact["knowledge_available_at"],
        "valuation_authority": "NONE",
        "share_continuity": "NOT_INFERRED",
    }]


# Retained-first result for the fixed five. Alternate bytes were fetched only
# where a retained official page already named the same filing. None has a
# native text layer. No amount below was read from an image.
EMPIRICAL_COHORT: tuple[dict[str, Any], ...] = (
    {
        "issuer": "FPT",
        "fact": "attributable_net_income",
        "reporting_period": "2025",
        "original": {
            "representation_class": "PRIMARY_OFFICIAL_PDF_SCAN",
            "sha256": "bb14bafff1a7849217f34cf4b50e0e3d69d91968f217a66d7c68f07d4c1af284",
            "issuer": "FPT", "reporting_period": "2025", "scope": "consolidated",
            "assurance": "audited", "statement_family": "income_statement",
            "native_text_characters": 0, "official_source": True,
            "raw_token": "9,376,1²7,6²9,501",
            "identity_proof": "SAME_FILING_PUBLICATION",
        },
        "alternate": {
            "representation_class": "OFFICIAL_PARALLEL_LANGUAGE_PDF",
            "sha256": "630f61f6ef9f07d5c593c3bf8f65bad1d56ecbb091921296ed5c4e830ea070a4",
            "issuer": "FPT", "reporting_period": "2025", "scope": "consolidated",
            "assurance": "audited", "statement_family": "income_statement",
            "native_text_characters": 0, "official_source": True,
            "identity_proof": "OFFICIAL_LANGUAGE_COUNTERPART",
            "listed_name": "Báo cáo tài chính hợp nhất năm 2025 đã kiểm toán",
            "url": "https://fpt.com/api/media/20260319_fpt_bctc_hop_nhat_nam_2025_da_kiem_toan_d94e52399c.pdf",
        },
    },
    {
        "issuer": "PNJ",
        "fact": "operating_cash_flow",
        "reporting_period": "2026-H1",
        "original": {
            "representation_class": "PRIMARY_OFFICIAL_PDF_SCAN",
            "sha256": "db877169e7c19b4b81d60b37d5aab8f9938129a66b582c2229ffffebdca2a43d",
            "issuer": "PNJ", "reporting_period": "2026-H1", "scope": "consolidated",
            "assurance": "reviewed", "statement_family": "cash_flow",
            "native_text_characters": 0, "official_source": True,
            "raw_token": "1.991.053.934.²37",
            "identity_proof": "EXPLICIT_OFFICIAL_CROSS_LINK",
        },
        "alternate": {
            "representation_class": "OFFICIAL_PARALLEL_LANGUAGE_PDF",
            "sha256": "cc0baaf7bfb938a898e9f23f1509bae0b8b25c7a045973ffc2086eb88d5db39c",
            "issuer": "PNJ", "reporting_period": "2026-H1", "scope": "consolidated",
            "assurance": "reviewed", "statement_family": "cash_flow",
            "native_text_characters": 0, "official_source": True,
            "identity_proof": "EXPLICIT_OFFICIAL_CROSS_LINK",
            "url": "https://cdn.pnj.io/images/quan-he-co-dong/2026/79c_-_20260903_-_PNJ_-_Interim_Consolidated_Financial_Statements_for_the_first_six_month_.pdf",
        },
    },
    {
        "issuer": "PVD",
        "fact": "cash_and_equivalents",
        "reporting_period": "2025",
        "original": {
            "representation_class": "PRIMARY_OFFICIAL_PDF_SCAN",
            "sha256": "6ee20a554891c449a8ee72fffe6358bc9b32145d066a7e52d8492d88f305139c",
            "issuer": "PVD", "reporting_period": "2025", "scope": "consolidated",
            "assurance": "audited", "statement_family": "balance_sheet",
            "native_text_characters": 0, "official_source": True,
            "raw_token": "1.8²1.²73.980.²43",
            "identity_proof": "OFFICIAL_LANGUAGE_COUNTERPART",
        },
        "alternate": {
            "representation_class": "OFFICIAL_PARALLEL_LANGUAGE_PDF",
            "sha256": "67c030b9af3341b83551e8b3ed1c46696dfa823a5c49653a3a9316800d2cf2b2",
            "issuer": "PVD", "reporting_period": "2025", "scope": "consolidated",
            "assurance": "audited", "statement_family": "balance_sheet",
            "native_text_characters": 0, "official_source": True,
            "identity_proof": "OFFICIAL_LANGUAGE_COUNTERPART",
            "listed_name": "Audited Consolidated Financial Statements 2025",
            "url": "https://www.pvdrilling.com.vn/Data/Sites/1/media/qhcd/bao-cao-tai-chinh/2025/20260331%20-%20PVD%20-%20Audited%20FS%20-%20Consolidated%202025_Signed.pdf",
        },
    },
    {
        "issuer": "HPG",
        "fact": "attributable_net_income",
        "reporting_period": "2025",
        "original": {
            "representation_class": "PRIMARY_OFFICIAL_PDF_SCAN",
            "sha256": "f38c5f75becf7d3f145d27183eec81f119fd4f75e378b983a2763ddc3f7e0c07",
            "issuer": "HPG", "reporting_period": "2025", "scope": "consolidated",
            "assurance": "audited", "statement_family": "income_statement",
            "native_text_characters": 0, "official_source": True,
            "raw_token": "15.453.174.006.²²3",
            "identity_proof": "SAME_FILING_PUBLICATION",
        },
        "alternate": None,
        "rejected_sibling": {
            "reason": "DIFFERENT_SCOPE",
            "listed_name": "parent company audited financial statements 2025",
        },
    },
    {
        "issuer": "QNS",
        "fact": "cash_and_equivalents",
        "reporting_period": "2026-H1",
        "original": {
            "representation_class": "PRIMARY_OFFICIAL_PDF_SCAN",
            "sha256": "5a06a40f34a6d9b30233926f9c9d909d684744de2bf2ad0956edd367d5f7b068",
            "issuer": "QNS", "reporting_period": "2026-H1", "scope": "consolidated",
            "assurance": "reviewed", "statement_family": "balance_sheet",
            "native_text_characters": 0, "official_source": True,
            "identity_proof": "SAME_FILING_PUBLICATION",
        },
        "alternate": None,
        "rejected_sibling": {
            "reason": "DIFFERENT_SCOPE",
            "listed_name": "2026q2-bctc-tong-hop",
            "language_switch": "unstable_redirect_no_body",
        },
    },
)


def empirical_assessments() -> list[dict[str, Any]]:
    return [assess_target(item) for item in EMPIRICAL_COHORT]


def milestone_report() -> dict[str, Any]:
    assessments = empirical_assessments()
    found = [item for item in assessments if item.get("alternate_sha256")]
    recovered = [item for item in assessments if item["outcome"] == RECOVERED]
    return {
        "milestone_id": MILESTONE_ID,
        "contract": CONTRACT,
        "disposition": DISPOSITION,
        "normalization": NORMALIZATION,
        "knowledge_available_at": KNOWLEDGE_AVAILABLE_AT,
        "cohort_size": len(assessments),
        "alternate_official_representations_found": len(found),
        "facts_recovered": len(recovered),
        "root_bottleneck": "REPRESENTATION",
        "future_acquisition_rule": "PREFER_PARSEABLE_COPY_ONLY_WHEN_THE_SAME_FILING_EXPLICITLY_LISTS_ONE",
        "discovery_path_changed": False,
        "issuer_by_issuer_scan_extraction_continues": False,
        "strict_shares": 0,
        "strict_valuation": 0,
        "october_7_records_changed": False,
        "network": {
            "targets": 5,
            "discovery_requests_per_target_max": 2,
            "alternate_document_fetches_per_target_max": 1,
            "concurrency": 1,
            "new_retained_bytes": 27855577,
            "storage_ceiling_bytes": 150 * 1024 * 1024,
            "counted_completed_gets": 5,
            "qns_language_switch": "unstable_redirect_hops_not_logged_at_most_6",
            "total_http_upper_bound": 11,
            "http_ceiling": 15,
        },
        "assessments": assessments,
        "packet_rows": [row for item in assessments for row in packet_provenance(item)],
    }
