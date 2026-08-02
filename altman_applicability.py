"""Fail-closed applicability gate for the Altman Z'-score.

`entity_type == "corporate"` is NOT sufficient to run Z'. Altman's 1983 Z' revision was
estimated on manufacturing firms and retains X5 = sales / total assets, the most
industry-sensitive of the five terms: asset turnover differs by an order of magnitude
between a steel mill and a property developer or a utility, so the same score means
different things across industries. The four-variable Z'' variant exists precisely because
Z' does not transfer to non-manufacturers. Z'' is deliberately NOT implemented here --
the immediate requirement is that Z' must not fail open across a whole universe of
"non-financial" issuers.

Three outcomes, never collapsed:
    not_applicable        -- confirmed financial institution; the corporate model does not
                             apply regardless of how complete the inputs are.
    eligible              -- confirmed non-financial AND industry qualified as manufacturing.
    insufficient_evidence -- entity type unknown, industry unknown, or industry known but
                             not manufacturing (Z'' would be the correct model and no
                             approved Z'' contract exists).

Industry qualification uses the retained ICB-style Vietnamese industry label already held
in `vn_stock.db:metadata.industry` (1,678 of 1,683 tickers carry one). Only industries whose
constituents are unambiguously goods-producing are whitelisted. Mixed labels are excluded
on purpose:
  - "Xay dung va Vat lieu" mixes construction contractors with building-materials makers.
  - "Hang & Dich vu Cong nghiep" mixes industrial goods with industrial services.
  - "Y te" mixes pharmaceutical manufacturing with hospitals and distribution.
Excluding a genuine manufacturer costs a missing score; including a non-manufacturer
produces a wrong one, so the ambiguity is resolved toward abstention.
"""
from __future__ import annotations

import unicodedata
from typing import Any

VERSION = "1.0.0"

FINANCIAL_ENTITY_TYPES = frozenset({"bank", "securities", "insurance", "finance_company"})
UNQUALIFIED_ENTITY_TYPES = frozenset({"", "unknown", "none", "null"})

# Vietnamese ICB level-2 labels whose constituents are unambiguously goods-producing.
# Compared diacritic-insensitively so a provider accent/spacing change does not silently
# drop a whitelist entry into abstention.
MANUFACTURING_INDUSTRIES = (
    "Tai nguyen Co ban",              # Basic Resources (HPG: steel)
    "Thuc pham va do uong",           # Food & Beverage (VNM: dairy)
    "Hoa chat",                       # Chemicals
    "O to va phu tung",               # Automobiles & Parts
    "Hang ca nhan & Gia dung",        # Personal & Household Goods
)


def _fold(value: Any) -> str:
    """Lowercase, strip diacritics, collapse whitespace."""
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "d")
    return " ".join(text.lower().split())


_MANUFACTURING_FOLDED = frozenset(_fold(name) for name in MANUFACTURING_INDUSTRIES)


def is_manufacturing_industry(industry: Any) -> bool:
    """True only for a whitelisted, unambiguously goods-producing industry label."""
    return _fold(industry) in _MANUFACTURING_FOLDED


def evaluate_altman_applicability(entity_type: Any, industry: Any) -> dict[str, Any]:
    """Pure. Returns {"applicability", "reason", "entity_type", "industry",
    "industry_qualified_manufacturing", "version"}.

    applicability is one of "not_applicable" | "eligible" | "insufficient_evidence".
    """
    normalized_entity = _fold(entity_type)
    result = {
        "version": VERSION, "entity_type": entity_type, "industry": industry,
        "industry_qualified_manufacturing": is_manufacturing_industry(industry),
    }

    if normalized_entity in FINANCIAL_ENTITY_TYPES:
        return {**result, "applicability": "not_applicable",
                "reason": (f"entity_type={entity_type!r} is a financial institution; Altman's corporate "
                           "Z'-score was estimated on non-financial firms and its working-capital and "
                           "asset-turnover terms have no equivalent meaning here.")}

    if normalized_entity in UNQUALIFIED_ENTITY_TYPES:
        return {**result, "applicability": "insufficient_evidence",
                "reason": (f"entity_type is not qualified (got {entity_type!r}); an absent archetype is "
                           "never read as corporate, because that would apply a non-financial model to "
                           "what may be a bank.")}

    if not industry or not str(industry).strip():
        return {**result, "applicability": "insufficient_evidence",
                "reason": "industry is unknown; Z' is estimated on manufacturing firms and its X5 "
                          "(sales / total assets) term is industry-sensitive, so it cannot be asserted "
                          "to apply without one."}

    if not result["industry_qualified_manufacturing"]:
        return {**result, "applicability": "insufficient_evidence",
                "reason": (f"industry={industry!r} is not a qualified manufacturing industry. Z' retains "
                           "the industry-sensitive X5 term and does not transfer to non-manufacturers; "
                           "the four-variable Z'' variant would be the correct model and no approved Z'' "
                           "contract exists in this project.")}

    return {**result, "applicability": "eligible",
            "reason": f"entity_type={entity_type!r} is non-financial and industry={industry!r} is a "
                      "qualified manufacturing industry."}
