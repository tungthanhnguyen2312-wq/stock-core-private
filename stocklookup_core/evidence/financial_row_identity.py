"""Literal financial-row identity rules shared by extraction and admission.

Mutable label policy and the exact two crossed income line-code pairs retain
their existing semantics. Normalizer injection is only the legacy OCR function
slot compatibility seam; no parsing, extraction or authority is added.
"""
from __future__ import annotations
from stocklookup_core.evidence.financial_document_text import _normalize


# Line code alone is not identity: the matched row's own label must support the concept.
# ``any_of`` phrases are normalized (accent-free) label substrings; ``forbidden`` phrases block.
ROW_LABEL_CONTRACT = {
    # Templates effective 2026 renumber the long-term asset block: code 270 is
    # ``Tài sản dài hạn khác`` and the total moves to 280.  A code-only bind would
    # promote a sub-total as total assets, so the row must literally say total.
    "total_assets": {"any_of": ("tong cong tai san", "tong tai san", "total assets"),
                     "forbidden": ("ngan han", "dai han", "khac", "non current", "current assets")},
    "investment_property_disposal_result": {"any_of": ("thanh ly",),
        "all_of": ("bat dong san dau tu",), "forbidden": ()},
    # Indirect cash-flow adjustment line 03.  Only surviving literal words are
    # required (OCR may read ``dự`` as ``dy``); letters are never repaired.
    "provision_charge_or_reversal_adjustment": {"any_of": ("phong",), "all_of": ("khoan",),
        "forbidden": ("khau hao", "ty gia", "lai vay", "dau tu")},
    # The same 2026 renumbering moves borrowings to 323/339; 320 and 338 become
    # ``Phải trả ngắn/dài hạn khác``.  A debt component must literally be a loan.
    "short_term_borrowings": {"any_of": ("vay",), "all_of": ("ngan", "han"), "forbidden": ("phai tra",)},
    "long_term_borrowings_or_finance_leases": {"any_of": ("vay",), "all_of": ("dai", "han"), "forbidden": ("phai tra",)},
    "net_income": {"any_of": ("loi nhuan sau thue", "profit after tax"),
                   "forbidden": ("cong ty me", "chu so huu", "co dong", "parent", "khong kiem soat")},
    "attributable_net_income": {"any_of": ("cong ty me", "of the parent", "parent company"),
                                "forbidden": ("khong kiem soat", "non controlling", "non-controlling")},
}


def _identity_fold(value: str) -> str:
    """Fold case and diacritics without compatibility decomposition.

    NFKC/NFKD map superscript digits onto base digits.  Label identity must not
    use that mapping: ``Provisi²ns`` is not the literal word Provisions.
    """
    import unicodedata
    folded = unicodedata.normalize("NFD", str(value).casefold())
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")
    return " ".join(folded.replace("đ", "d").replace("’", "'").split())


def row_label_supports_metric(metric: str, label: str, *, normalizer=None) -> bool:
    # English indirect cash-flow line 03 is the single literal word.  A longer
    # phrase, or any superscript inside the word, stays unqualified.
    if metric == "provision_charge_or_reversal_adjustment" and _identity_fold(label) == "provisions":
        return True
    contract = ROW_LABEL_CONTRACT.get(metric)
    if contract is None:
        return True
    normalized = (_normalize if normalizer is None else normalizer)(label)
    # OCR may join adjacent words (``Loinhuan``). Ignore word spacing only;
    # never repair letters, digits or replace a missing identity-bearing word.
    compact = normalized.replace(" ", "")
    return any(term.replace(" ", "") in compact for term in contract["any_of"]) and all(
        term.replace(" ", "") in compact for term in contract.get("all_of", ())) and not any(
        term.replace(" ", "") in compact for term in contract["forbidden"])



# Crossed total-versus-parent income line identities are never admitted.
LINE_CODE_IDENTITY_CONFLICTS = frozenset({("net_income", "61"), ("attributable_net_income", "60")})
