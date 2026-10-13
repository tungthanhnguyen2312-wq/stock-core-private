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


def resolve_reported_row_identity(statement_family: str, line_code: str, label: str) -> dict:
    """Candidate-only literal row mapping; never changes standing fact admission.

    Codes are scoped to the statement. Total equity and lease-inclusive debt keep
    their distinct source concepts, even where the canonical vocabulary is narrower.
    """
    folded = _identity_fold(label)
    if statement_family == "eps_note":
        for phrase, concept in (("profit attributable to ordinary shareholders", "EPS_ORDINARY_SHAREHOLDER_PROFIT"),
                ("shares in circulation for the period", "EPS_DENOMINATOR_SHARES"),
                ("shares in circulation at the beginning", "EPS_OPENING_SHARES"),
                ("impact of the stock dividend", "EPS_RESTATED_DIVIDEND_IMPACT")):
            if phrase in folded:
                return dict(canonical_metric=None, accounting_identity=concept, blockers=[])
    if statement_family == "balance_sheet" and str(line_code) in {"321", "339"} and "loans" in folded and "finance lease" not in folded:
        return dict(canonical_metric=None, accounting_identity=("SHORT_TERM" if str(line_code) == "321" else "LONG_TERM") + "_LOANS_LEASE_CONTENT_UNKNOWN", blockers=[])
    entries = {
        ("income_statement", "10"): ("revenue", "NET_REVENUE", ("net sales", "net revenue", "doanh thu thuan")),
        ("income_statement", "01"): (None, "GROSS_REVENUE", ("revenue", "sales", "doanh thu")),
        ("income_statement", "02"): (None, "REVENUE_DEDUCTIONS", ("deductions", "giam tru")),
        ("income_statement", "24"): (None, "REPORTED_BORROWING_COSTS", ("borrowing costs", "chi phi lai vay")),
        ("income_statement", "60"): ("net_income", "TOTAL_PROFIT_AFTER_TAX", ("profit after tax", "profit after corporate income tax", "loi nhuan sau thue")),
        ("income_statement", "20"): ("gross_profit", "GROSS_PROFIT", ("gross profit", "loi nhuan gop")),
        ("income_statement", "50"): (None, "PROFIT_BEFORE_TAX", ("profit before tax", "loi nhuan truoc thue")),
        ("income_statement", "62"): (None, "NCI_PROFIT_AFTER_TAX", ("non-controlling", "non controlling", "khong kiem soat")),
        ("income_statement", "70"): (None, "REPORTED_BASIC_EPS", ("earnings per share", "lai co ban tren co phieu")),
        ("income_statement", "61"): ("attributable_net_income", "PARENT_PROFIT_AFTER_TAX", ("parent", "cong ty me")),
        ("balance_sheet", "110"): ("cash_and_cash_equivalents", "CASH_AND_EQUIVALENTS", ("cash and cash equivalents", "tien va cac khoan tuong duong")),
        ("balance_sheet", "111"): (None, "CASH_ONLY_NOT_CASH_AND_EQUIVALENTS", ("cash", "tien")),
        ("balance_sheet", "200"): (None, "NON_CURRENT_ASSETS", ("non-current assets", "non current assets", "tai san dai han")),
        ("balance_sheet", "100"): ("current_assets", "CURRENT_ASSETS", ("current assets", "tai san ngan han")),
        ("balance_sheet", "280"): ("total_assets", "TOTAL_ASSETS", ("total assets", "tong cong tai san")),
        ("balance_sheet", "400"): ("shareholders_equity", "TOTAL_EQUITY_INCLUDING_NCI", ("owners' equity", "owners equity", "d. equity", "chu so huu")),
        ("balance_sheet", "140"): (None, "INVENTORIES", ("inventor", "hang ton kho")),
        ("balance_sheet", "300"): ("total_liabilities", "TOTAL_LIABILITIES", ("liabilities", "no phai tra")),
        ("balance_sheet", "411"): (None, "CONTRIBUTED_SHARE_CAPITAL", ("share capital", "contributed capital", "von gop")),
        ("balance_sheet", "411a"): (None, "ORDINARY_VOTING_SHARE_CAPITAL_AMOUNT", ("ordinary shares carrying voting rights",)),
        ("balance_sheet", "429"): (None, "NON_CONTROLLING_INTERESTS", ("non-controlling", "non controlling", "khong kiem soat")),
        ("balance_sheet", "321"): (None, "SHORT_TERM_LOANS_AND_FINANCE_LEASES", ("borrowings and finance lease", "loans and finance lease", "loans and obligations under finance lease", "vay va no thue")),
        ("balance_sheet", "339"): (None, "LONG_TERM_LOANS_AND_FINANCE_LEASES", ("borrowings and finance lease", "loans and finance lease", "loans and obligations under finance lease", "vay va no thue")),
        ("cash_flow", "20"): ("operating_cash_flow", "OPERATING_CASH_FLOW", ("operating activities", "hoat dong kinh doanh")),
        ("cash_flow", "02"): (None, "COMPOSITE_CASH_FLOW_DEPRECIATION_ADJUSTMENT", ("depreciation and amortisation", "khau hao")),
    }
    entry = entries.get((statement_family, str(line_code)))
    blockers = []
    if entry is None:
        return dict(canonical_metric=None, accounting_identity="UNKNOWN", blockers=["ROW_IDENTITY_NOT_MAPPED"])
    metric, concept, phrases = entry
    if not any(term in folded for term in phrases):
        blockers.append("LITERAL_ROW_LABEL_MISMATCH")
    if (statement_family == "income_statement" and str(line_code) == "60"
            and any(term in folded for term in ("parent", "cong ty me", "non-controlling", "non controlling", "khong kiem soat"))):
        blockers.append("TOTAL_PARENT_PROFIT_IDENTITY_CONFLICT")
    if statement_family == "income_statement" and str(line_code) == "61" and any(term in folded for term in ("non-controlling", "non controlling", "khong kiem soat")):
        blockers.append("PARENT_NCI_PROFIT_IDENTITY_CONFLICT")
    if concept == "TOTAL_ASSETS" and any(term in folded for term in ("current assets", "non-current", "non current", "other assets")):
        blockers.append("SUBTOTAL_IS_NOT_TOTAL_ASSETS")
    if concept == "TOTAL_LIABILITIES" and any(term in folded for term in ("current liabilities", "non-current", "other liabilities")):
        blockers.append("SUBTOTAL_IS_NOT_TOTAL_LIABILITIES")
    return dict(canonical_metric=metric, accounting_identity=concept, blockers=blockers)
