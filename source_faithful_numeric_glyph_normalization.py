"""Fail-closed record for superscript digits inside an already identified amount.

Identity is never discovered here.  No retained cell has an independent
confirmation, so the public decision never returns a normalized amount and
qualification does not call this module.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Mapping, Sequence

CONTRACT = "source_faithful_numeric_glyph_normalization/v1"
DISPOSITION = "SOURCE_FAITHFUL_NORMALIZATION_NOT_YET_PROVABLE"
SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
# Compatibility decomposition maps these to ASCII digits.  That mapping is
# evidence about Unicode, not permission to rewrite a source token.
INDEPENDENT_CONFIRMATIONS = frozenset({
    "NATIVE_PDF_TEXT_LAYER",
    "ALTERNATE_LITERAL_SOURCE",
    "DISTINCT_REPRESENTATION_EXTRACTOR",
    "RETAINED_GLYPH_FIXTURE",
    "PARALLEL_LANGUAGE_EXACT_IDENTITY",
})


def unicode_compatibility_folds_superscript_digits(token: str) -> bool:
    folded = unicodedata.normalize("NFKC", token)
    return folded != token and any(ch in SUPERSCRIPT_DIGITS for ch in token) and folded.isascii()


def normalization_decision(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Return the blocked decision for one already-named amount cell.

    ``candidate`` states gates that were established before this call.  This
    function does not read an image, choose a row, or repair a header.
    """
    raw = str(candidate.get("raw_token") or "")
    reasons: list[str] = []
    if candidate.get("token_class") != "NUMERIC_AMOUNT":
        reasons.append("TOKEN_CLASS_NOT_NUMERIC_AMOUNT")
    if candidate.get("row_identity_qualified") is not True:
        reasons.append("ROW_IDENTITY_UNKNOWN")
    if candidate.get("column_identity_qualified") is not True:
        reasons.append("COLUMN_IDENTITY_UNKNOWN")
    if candidate.get("competing_numeric_token") is True:
        reasons.append("COMPETING_NUMERIC_TOKEN")
    if candidate.get("footnote_ambiguity") is True:
        reasons.append("FOOTNOTE_SUPERSCRIPT_AMBIGUITY")
    confirmation = str(candidate.get("independent_confirmation") or "")
    if confirmation not in INDEPENDENT_CONFIRMATIONS:
        reasons.append("INDEPENDENT_CONFIRMATION_ABSENT")
    if not any(ch in SUPERSCRIPT_DIGITS for ch in raw):
        reasons.append("NO_SUPERSCRIPT_DIGIT")
    folded = unicodedata.normalize("NFKC", raw)
    from annual_financial_ocr_materialization import parse_accounting_integer
    try:
        parse_accounting_integer(folded)
        deterministic = True
    except ValueError:
        deterministic = False
        reasons.append("NORMALIZED_TOKEN_NOT_A_NUMERIC_AMOUNT")
    # Retained proof did not clear every gate for any real cell.  A synthetic
    # gate pass still does not emit a value from this boundary.
    reasons.append(DISPOSITION)
    return {
        "contract": CONTRACT,
        "state": "STILL_BLOCKED",
        "disposition": DISPOSITION,
        "raw_token": raw,
        "normalized_token": None,
        "normalization_method": None,
        "deterministic_nfkc_available": deterministic,
        "reasons": sorted(set(reasons)),
        "admitted": False,
    }


def cohort_decisions(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [normalization_decision(item) for item in candidates]
