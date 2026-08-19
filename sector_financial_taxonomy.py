"""Phase 2 / P2-F1: Sector Financial Taxonomy & Contract.

Defines the deterministic sector-financial taxonomy schema, applicable statement-form
families, canonical metric vocabulary, note/disclosure families, and explicit sector
inapplicability matrices across:
- corporate
- bank
- securities
- insurance
- finance_company

Guarantees:
1. No cross-sector semantic collapse (bank liabilities != corporate debt,
   securities margin lending != trade receivables, insurance reserves != corporate borrowings).
2. Explicit real-data proof corpus vs schema-only sector boundaries:
   - REAL_DATA_VALIDATED_SECTORS = ("bank", "securities")
   - SCHEMA_ONLY_SECTORS = ("insurance", "finance_company")
3. Strict fail-closed semantics for unsupported sector metrics or unclassified entities.
4. TICKER_SPECIFIC_SECTOR_EXTRACTION_BRANCH_COUNT = 0
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import hashlib
import json
from typing import Any, Mapping, Sequence
import unicodedata

from entity_classification_contract import EntityClass

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "sector_financial_taxonomy/v1"
TICKER_SPECIFIC_SECTOR_EXTRACTION_BRANCH_COUNT = 0


class StatementFormFamily(StrEnum):
    """Statutory statement-form families recognized under Vietnamese accounting standards."""
    CORPORATE_VAS_200 = "circular_200_2014_btc"              # Corporate VAS (Circular 200/2014 & 202/2014/TT-BTC)
    BANK_VAS_49 = "circular_49_2014_nhnn"                     # Commercial Banks (Circular 49/2014/TT-NHNN)
    SECURITIES_VAS_334 = "circular_334_2016_btc"              # Securities Companies (Circular 334/2016/TT-BTC)
    INSURANCE_VAS_199 = "circular_199_2014_btc"               # Insurance Entities (Circular 199/2014 & 232/2012/TT-BTC)
    FINANCE_COMPANY_VAS_49 = "circular_49_2014_nhnn_non_bank" # Non-bank Credit Institutions (Circular 49/2014/TT-NHNN)


class SectorProofStatus(StrEnum):
    REAL_DATA_VALIDATED = "REAL_DATA_VALIDATED"
    SCHEMA_SUPPORTED_BUT_NOT_REAL_DATA_VALIDATED = "SCHEMA_SUPPORTED_BUT_NOT_REAL_DATA_VALIDATED"


class MetricApplicabilityState(StrEnum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNSUPPORTED_SECTOR_METRIC = "UNSUPPORTED_SECTOR_METRIC"
    UNKNOWN_ENTITY_CLASS = "UNKNOWN_ENTITY_CLASS"


@dataclass(frozen=True)
class MetricDefinition:
    """Metadata specification for a sector canonical metric."""
    canonical_metric: str
    entity_class: EntityClass
    statement_family: str  # balance_sheet, income_statement, cash_flow, notes_and_disclosures
    temporal_nature: str   # instant vs duration
    standard_line_code: str | None
    raw_label_aliases_vi: tuple[str, ...]
    raw_label_aliases_en: tuple[str, ...]
    description: str
    disclosure_family: str | None = None
    is_parent_attributable: bool = False
    sign_multiplier: int = 1


@dataclass(frozen=True)
class MetricApplicabilityResult:
    canonical_metric: str
    entity_class: EntityClass
    applicability: MetricApplicabilityState
    reason_codes: tuple[str, ...]
    statement_family: str | None = None
    temporal_nature: str | None = None
    is_ordinary_corporate_metric: bool = False


# Retained real-data proof corpus declaration
REAL_DATA_PROOF_CORPUS: dict[EntityClass, dict[str, Any]] = {
    EntityClass.BANK: {
        "status": SectorProofStatus.REAL_DATA_VALIDATED.value,
        "proof_available": True,
        "proof_reporting_period": "2024",
        "statement_scope": "consolidated",
        "document_sha256": "9deccc3518e23302d00353b4d371a9dd251b67b12f9fe58a4da4ad3c727e99f8",
        "qualification_state": "QUALIFIED",
        "currency": "VND",
        "form_family": StatementFormFamily.BANK_VAS_49.value,
        "retained_citation_count": 22,
    },
    EntityClass.SECURITIES: {
        "status": SectorProofStatus.REAL_DATA_VALIDATED.value,
        "proof_available": True,
        "proof_reporting_period": "2024",
        "statement_scope": "consolidated",
        "document_sha256": "38e5b9ba2fc951120be813b09df05fa2d8b152b3b95443c6cd108de8abf03b74",
        "qualification_state": "QUALIFIED",
        "currency": "VND",
        "form_family": StatementFormFamily.SECURITIES_VAS_334.value,
        "retained_citation_count": 17,
    },
    EntityClass.INSURANCE: {
        "status": SectorProofStatus.SCHEMA_SUPPORTED_BUT_NOT_REAL_DATA_VALIDATED.value,
        "proof_available": False,
        "proof_reporting_period": None,
        "statement_scope": None,
        "document_sha256": None,
        "qualification_state": "NO_RETAINED_PROOF_FILING",
        "currency": None,
        "form_family": StatementFormFamily.INSURANCE_VAS_199.value,
        "retained_citation_count": 0,
    },
    EntityClass.FINANCE_COMPANY: {
        "status": SectorProofStatus.SCHEMA_SUPPORTED_BUT_NOT_REAL_DATA_VALIDATED.value,
        "proof_available": False,
        "proof_reporting_period": None,
        "statement_scope": None,
        "document_sha256": None,
        "qualification_state": "NO_RETAINED_PROOF_FILING",
        "currency": None,
        "form_family": StatementFormFamily.FINANCE_COMPANY_VAS_49.value,
        "retained_citation_count": 0,
    },
}

REAL_DATA_VALIDATED_SECTORS: tuple[str, ...] = ("bank", "securities")
SCHEMA_ONLY_SECTORS: tuple[str, ...] = ("insurance", "finance_company")


# Statutory primary statement forms by sector
SECTOR_PRIMARY_STATEMENT_FORMS: dict[EntityClass, dict[str, tuple[str, ...]]] = {
    EntityClass.CORPORATE: {
        "balance_sheet": ("b 01-dn", "b 01-dn/hn", "b 01—dn"),
        "income_statement": ("b 02-dn", "b 02-dn/hn", "b 02—dn"),
        "cash_flow": ("b 03-dn", "b 03-dn/hn", "b 03—dn"),
        "notes": ("b 09-dn", "b 09-dn/hn", "b 09a-dn"),
    },
    EntityClass.BANK: {
        "balance_sheet": ("b 01-nh", "b 01-nh/hn", "b 02/tctd-hn", "b 02/tctd"),
        "income_statement": ("b 02-nh", "b 02-nh/hn", "b 03/tctd-hn", "b 03/tctd"),
        "cash_flow": ("b 03-nh", "b 03-nh/hn", "b 04/tctd-hn", "b 04/tctd"),
        "notes": ("b 05-nh", "b 05-nh/hn", "b 05/tctd-hn", "b 05/tctd"),
    },
    EntityClass.SECURITIES: {
        "balance_sheet": ("b 01-ck", "b 01-ctck", "b 01-ctck/hn", "b 01-ctc/hn"),
        "income_statement": ("b 02-ck", "b 02-ctck", "b 02-ctck/hn", "b 02-ctc/hn"),
        "cash_flow": ("b 03-ck", "b 03-ctck", "b 03-ctck/hn", "b 03-ctc/hn"),
        "notes": ("b 09-ck", "b 09-ctck", "b 09-ctck/hn", "b 09-ctc/hn"),
    },
    EntityClass.INSURANCE: {
        "balance_sheet": ("b 01-bh", "b 01-bh/hn"),
        "income_statement": ("b 02-bh", "b 02-bh/hn"),
        "cash_flow": ("b 03-bh", "b 03-bh/hn"),
        "notes": ("b 09-bh", "b 09-bh/hn"),
    },
    EntityClass.FINANCE_COMPANY: {
        "balance_sheet": ("b 01-tctd", "b 01-tctd/hn", "b 02/tctd-hn"),
        "income_statement": ("b 02-tctd", "b 02-tctd/hn", "b 03/tctd-hn"),
        "cash_flow": ("b 03-tctd", "b 03-tctd/hn", "b 04/tctd-hn"),
        "notes": ("b 05-tctd", "b 05-tctd/hn", "b 05/tctd-hn"),
    },
}


# Ordinary corporate metrics that are explicitly NOT_APPLICABLE for financial intermediaries
SECTOR_INAPPLICABLE_CORPORATE_METRICS: dict[EntityClass, set[str]] = {
    EntityClass.BANK: {
        "cost_of_goods_sold",
        "gross_profit",
        "selling_expense",
        "ebitda",
        "ev_ebitda",
        "ev_sales",
        "fcff",
        "net_net",
        "total_interest_bearing_debt",  # Ordinary corporate debt meaning
        "debt_to_equity",               # Ordinary corporate debt ratio
        "net_debt",                     # Ordinary corporate net debt
        "working_capital",
        "current_ratio",
        "quick_ratio",
        "altman_z_prime",
    },
    EntityClass.SECURITIES: {
        "cost_of_goods_sold",
        "gross_profit",
        "ebitda",
        "ev_ebitda",
        "ev_sales",
        "fcff",
        "net_net",
        "total_interest_bearing_debt",  # Ordinary corporate debt meaning
        "debt_to_equity",               # Ordinary corporate debt ratio
        "net_debt",
        "working_capital",
        "altman_z_prime",
    },
    EntityClass.INSURANCE: {
        "cost_of_goods_sold",
        "gross_profit",
        "ebitda",
        "ev_ebitda",
        "ev_sales",
        "fcff",
        "net_net",
        "total_interest_bearing_debt",
        "debt_to_equity",
        "net_debt",
        "working_capital",
        "altman_z_prime",
    },
    EntityClass.FINANCE_COMPANY: {
        "cost_of_goods_sold",
        "gross_profit",
        "selling_expense",
        "ebitda",
        "ev_ebitda",
        "ev_sales",
        "fcff",
        "net_net",
        "total_interest_bearing_debt",
        "debt_to_equity",
        "net_debt",
        "working_capital",
        "altman_z_prime",
    },
    EntityClass.CORPORATE: set(),
    EntityClass.UNKNOWN: set(),
}


# Sector-specific canonical metric vocabularies
BANK_METRICS: dict[str, MetricDefinition] = {
    "interest_income": MetricDefinition(
        canonical_metric="interest_income",
        entity_class=EntityClass.BANK,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="1",
        raw_label_aliases_vi=("thu nhập lãi và các khoản thu nhập tương tự", "thu nhập lãi"),
        raw_label_aliases_en=("interest and similar income", "interest income"),
        description="Interest and similar income earned by commercial bank",
        disclosure_family="interest_and_similar_income",
    ),
    "interest_expense": MetricDefinition(
        canonical_metric="interest_expense",
        entity_class=EntityClass.BANK,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="2",
        raw_label_aliases_vi=("chi phí lãi và các chi phí tương tự", "chi phí lãi"),
        raw_label_aliases_en=("interest and similar expenses", "interest expense"),
        description="Interest and similar expenses incurred by commercial bank",
        disclosure_family="interest_and_similar_expenses",
        sign_multiplier=1,
    ),
    "net_interest_income": MetricDefinition(
        canonical_metric="net_interest_income",
        entity_class=EntityClass.BANK,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="I",
        raw_label_aliases_vi=("thu nhập lãi thuần",),
        raw_label_aliases_en=("net interest and similar income", "net interest income"),
        description="Net interest income (Interest income minus Interest expense)",
    ),
    "net_fee_and_commission_income": MetricDefinition(
        canonical_metric="net_fee_and_commission_income",
        entity_class=EntityClass.BANK,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="II",
        raw_label_aliases_vi=("lãi/lỗ thuần từ hoạt động dịch vụ", "thu nhập thuần từ hoạt động dịch vụ"),
        raw_label_aliases_en=("net fee and commission income", "net service income"),
        description="Net fee and commission income",
        disclosure_family="fee_and_commission_income",
    ),
    "net_gain_loss_fx_and_gold": MetricDefinition(
        canonical_metric="net_gain_loss_fx_and_gold",
        entity_class=EntityClass.BANK,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="III",
        raw_label_aliases_vi=("lãi/lỗ thuần từ hoạt động kinh doanh ngoại hối và vàng", "lãi thuần từ kinh doanh ngoại hối"),
        raw_label_aliases_en=("net gain/loss from foreign exchange and gold trading", "net fx gain"),
        description="Net gain or loss from foreign currencies and gold dealing",
        disclosure_family="fx_and_gold_trading",
    ),
    "net_gain_loss_trading_securities": MetricDefinition(
        canonical_metric="net_gain_loss_trading_securities",
        entity_class=EntityClass.BANK,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="IV",
        raw_label_aliases_vi=("lãi/lỗ thuần từ mua bán chứng khoán kinh doanh",),
        raw_label_aliases_en=("net gain/loss from trading securities",),
        description="Net gain or loss from trading securities",
        disclosure_family="trading_securities",
    ),
    "net_gain_loss_investment_securities": MetricDefinition(
        canonical_metric="net_gain_loss_investment_securities",
        entity_class=EntityClass.BANK,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="V",
        raw_label_aliases_vi=("lãi/lỗ thuần từ mua bán chứng khoán đầu tư",),
        raw_label_aliases_en=("net gain/loss from investment securities",),
        description="Net gain or loss from investment securities",
        disclosure_family="investment_securities",
    ),
    "total_operating_income": MetricDefinition(
        canonical_metric="total_operating_income",
        entity_class=EntityClass.BANK,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code=None,
        raw_label_aliases_vi=("tổng thu nhập hoạt động",),
        raw_label_aliases_en=("total operating income",),
        description="Total operating income before operating expenses",
    ),
    "operating_expenses": MetricDefinition(
        canonical_metric="operating_expenses",
        entity_class=EntityClass.BANK,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="VIII",
        raw_label_aliases_vi=("chi phí hoạt động",),
        raw_label_aliases_en=("operating expenses",),
        description="General operating expenses of the bank",
        disclosure_family="operating_expenses",
        sign_multiplier=1,
    ),
    "operating_profit_before_provision_for_credit_losses": MetricDefinition(
        canonical_metric="operating_profit_before_provision_for_credit_losses",
        entity_class=EntityClass.BANK,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="IX",
        raw_label_aliases_vi=("lợi nhuận thuần từ hoạt động kinh doanh trước chi phí dự phòng rủi ro tín dụng",),
        raw_label_aliases_en=("operating profit before provision for credit losses",),
        description="Net operating profit before provision expenses",
    ),
    "provision_for_credit_losses": MetricDefinition(
        canonical_metric="provision_for_credit_losses",
        entity_class=EntityClass.BANK,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="X",
        raw_label_aliases_vi=("chi phí dự phòng rủi ro tín dụng", "dự phòng rủi ro tín dụng"),
        raw_label_aliases_en=("provision for credit losses", "credit risk provision expenses"),
        description="Provision expense for credit losses",
        disclosure_family="credit_loss_provisions",
        sign_multiplier=1,
    ),
    "profit_before_tax": MetricDefinition(
        canonical_metric="profit_before_tax",
        entity_class=EntityClass.BANK,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="XI",
        raw_label_aliases_vi=("tổng lợi nhuận trước thuế", "lợi nhuận trước thuế"),
        raw_label_aliases_en=("total profit before tax", "profit before tax"),
        description="Total profit before corporate income tax",
    ),
    "net_profit_total": MetricDefinition(
        canonical_metric="net_profit_total",
        entity_class=EntityClass.BANK,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="XIV",
        raw_label_aliases_vi=("lợi nhuận sau thuế", "lợi nhuận thuần sau thuế"),
        raw_label_aliases_en=("net profit after tax", "total net profit"),
        description="Total net profit after tax",
    ),
    "net_profit_parent": MetricDefinition(
        canonical_metric="net_profit_parent",
        entity_class=EntityClass.BANK,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="XIV.1",
        raw_label_aliases_vi=(
            "lợi nhuận sau thuế của cổ đông ngân hàng mẹ",
            "lợi nhuận sau thuế thuộc về cổ đông ngân hàng mẹ",
            "lợi nhuận thuộc về cổ đông của ngân hàng",
        ),
        raw_label_aliases_en=(
            "net profit attributable to the equity holders of the bank",
            "profit attributable to parent company shareholders",
        ),
        description="Net profit after tax attributable to equity holders of parent bank",
        is_parent_attributable=True,
    ),
    "total_assets": MetricDefinition(
        canonical_metric="total_assets",
        entity_class=EntityClass.BANK,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="B",
        raw_label_aliases_vi=("tổng cộng tài sản", "tổng tài sản"),
        raw_label_aliases_en=("total assets",),
        description="Total banking assets at period end",
    ),
    "total_liabilities": MetricDefinition(
        canonical_metric="total_liabilities",
        entity_class=EntityClass.BANK,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="B.LIAB",
        raw_label_aliases_vi=("nợ phải trả", "tổng nợ phải trả"),
        raw_label_aliases_en=("total liabilities", "liabilities"),
        description="Total liabilities of the bank at period end",
    ),
    "total_equity": MetricDefinition(
        canonical_metric="total_equity",
        entity_class=EntityClass.BANK,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="VIII",
        raw_label_aliases_vi=("vốn chủ sở hữu", "vốn và các quỹ"),
        raw_label_aliases_en=("owners' equity", "total equity", "equity and funds"),
        description="Total equity and funds at period end",
        disclosure_family="equity_and_funds",
    ),
    "minority_interest": MetricDefinition(
        canonical_metric="minority_interest",
        entity_class=EntityClass.BANK,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="VIII.5",
        raw_label_aliases_vi=("lợi ích của cổ đông không kiểm soát", "lợi ích cổ đông thiểu số"),
        raw_label_aliases_en=("non-controlling interests", "minority interest"),
        description="Non-controlling interests",
    ),
    "parent_equity": MetricDefinition(
        canonical_metric="parent_equity",
        entity_class=EntityClass.BANK,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="VIII.PAR",
        raw_label_aliases_vi=("vốn chủ sở hữu của ngân hàng mẹ", "vốn thuộc về ngân hàng mẹ"),
        raw_label_aliases_en=("equity attributable to parent bank", "parent equity"),
        description="Equity attributable to parent bank shareholders",
        is_parent_attributable=True,
    ),
    "customer_deposits": MetricDefinition(
        canonical_metric="customer_deposits",
        entity_class=EntityClass.BANK,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="III.DEP",
        raw_label_aliases_vi=("tiền gửi của khách hàng", "tiền gửi khách hàng"),
        raw_label_aliases_en=("deposits from customers", "customer deposits"),
        description="Customer deposits held by the bank",
        disclosure_family="customer_deposits",
    ),
    "customer_loans_net": MetricDefinition(
        canonical_metric="customer_loans_net",
        entity_class=EntityClass.BANK,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="III.LOAN",
        raw_label_aliases_vi=("cho vay khách hàng", "cho vay khách hàng thuần"),
        raw_label_aliases_en=("loans and advances to customers", "loans to customers net"),
        description="Net loans and advances to customers after credit loss allowances",
        disclosure_family="customer_loans",
    ),
}


SECURITIES_METRICS: dict[str, MetricDefinition] = {
    "financial_assets_fvtpl": MetricDefinition(
        canonical_metric="financial_assets_fvtpl",
        entity_class=EntityClass.SECURITIES,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="111",
        raw_label_aliases_vi=(
            "tài sản tài chính ghi nhận thông qua lãi/lỗ (fvtpl)",
            "tài sản tài chính fvtpl",
        ),
        raw_label_aliases_en=(
            "financial assets at fair value through profit or loss (fvtpl)",
            "financial assets fvtpl",
        ),
        description="Financial assets at fair value through profit or loss (FVTPL)",
        disclosure_family="financial_assets_fvtpl",
    ),
    "loans_balance": MetricDefinition(
        canonical_metric="loans_balance",
        entity_class=EntityClass.SECURITIES,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="114",
        raw_label_aliases_vi=("các khoản cho vay", "cho vay"),
        raw_label_aliases_en=("loans", "loans balance"),
        description="Loans balance on securities balance sheet (including margin lending and advances)",
        disclosure_family="securities_loans_and_margin",
    ),
    "total_assets": MetricDefinition(
        canonical_metric="total_assets",
        entity_class=EntityClass.SECURITIES,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="270",
        raw_label_aliases_vi=("tổng cộng tài sản", "tổng tài sản"),
        raw_label_aliases_en=("total assets",),
        description="Total assets of securities company",
    ),
    "short_term_borrowings_and_financial_leases": MetricDefinition(
        canonical_metric="short_term_borrowings_and_financial_leases",
        entity_class=EntityClass.SECURITIES,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="311",
        raw_label_aliases_vi=("vay và nợ thuê tài chính ngắn hạn",),
        raw_label_aliases_en=("short-term borrowings and financial leases",),
        description="Short-term borrowings of securities company",
        disclosure_family="borrowings_and_leases",
    ),
    "current_liabilities": MetricDefinition(
        canonical_metric="current_liabilities",
        entity_class=EntityClass.SECURITIES,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="310",
        raw_label_aliases_vi=("nợ ngắn hạn",),
        raw_label_aliases_en=("current liabilities",),
        description="Total current short-term liabilities of securities company",
    ),
    "total_equity": MetricDefinition(
        canonical_metric="total_equity",
        entity_class=EntityClass.SECURITIES,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="400",
        raw_label_aliases_vi=("vốn chủ sở hữu",),
        raw_label_aliases_en=("owners' equity", "total equity"),
        description="Total equity of securities company",
        disclosure_family="owners_equity",
    ),
    "share_capital": MetricDefinition(
        canonical_metric="share_capital",
        entity_class=EntityClass.SECURITIES,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="411",
        raw_label_aliases_vi=("vốn đầu tư của chủ sở hữu", "vốn góp của chủ sở hữu"),
        raw_label_aliases_en=("share capital", "capital contribution"),
        description="Contributed share capital",
        disclosure_family="share_capital",
    ),
    "total_operating_revenue": MetricDefinition(
        canonical_metric="total_operating_revenue",
        entity_class=EntityClass.SECURITIES,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="20",
        raw_label_aliases_vi=("tổng doanh thu hoạt động", "doanh thu hoạt động"),
        raw_label_aliases_en=("total operating revenue", "operating revenue"),
        description="Total operating revenue of securities company",
    ),
    "brokerage_revenue": MetricDefinition(
        canonical_metric="brokerage_revenue",
        entity_class=EntityClass.SECURITIES,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="06",
        raw_label_aliases_vi=("doanh thu nghiệp vụ môi giới chứng khoán", "doanh thu môi giới"),
        raw_label_aliases_en=("revenue from brokerage services", "brokerage revenue"),
        description="Revenue from securities brokerage operations",
        disclosure_family="brokerage_operations",
    ),
    "fvtpl_gain": MetricDefinition(
        canonical_metric="fvtpl_gain",
        entity_class=EntityClass.SECURITIES,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="01",
        raw_label_aliases_vi=("lãi từ các tài sản tài chính ghi nhận thông qua lãi/lỗ (fvtpl)", "lãi fvtpl"),
        raw_label_aliases_en=("gain from financial assets at fair value through profit or loss (fvtpl)", "fvtpl gain"),
        description="Realized and unrealized gains from FVTPL financial assets",
        disclosure_family="financial_assets_fvtpl",
    ),
    "fvtpl_loss": MetricDefinition(
        canonical_metric="fvtpl_loss",
        entity_class=EntityClass.SECURITIES,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="21",
        raw_label_aliases_vi=("lỗ từ các tài sản tài chính ghi nhận thông qua lãi/lỗ (fvtpl)", "lỗ fvtpl"),
        raw_label_aliases_en=("loss from financial assets at fair value through profit or loss (fvtpl)", "fvtpl loss"),
        description="Realized and unrealized losses from FVTPL financial assets",
        disclosure_family="financial_assets_fvtpl",
        sign_multiplier=1,
    ),
    "borrowing_costs": MetricDefinition(
        canonical_metric="borrowing_costs",
        entity_class=EntityClass.SECURITIES,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="52",
        raw_label_aliases_vi=("chi phí đi vay", "chi phí lãi vay"),
        raw_label_aliases_en=("borrowing costs", "interest expense"),
        description="Financing borrowing costs incurred by securities company",
        disclosure_family="borrowing_costs",
    ),
    "profit_after_tax_total": MetricDefinition(
        canonical_metric="profit_after_tax_total",
        entity_class=EntityClass.SECURITIES,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="70",
        raw_label_aliases_vi=("lợi nhuận sau thuế thu nhập doanh nghiệp", "lợi nhuận sau thuế"),
        raw_label_aliases_en=("profit after tax", "total profit after tax"),
        description="Total profit after corporate income tax",
    ),
    "profit_after_tax_parent": MetricDefinition(
        canonical_metric="profit_after_tax_parent",
        entity_class=EntityClass.SECURITIES,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="71",
        raw_label_aliases_vi=(
            "lợi nhuận sau thuế phân bổ cho chủ sở hữu công ty mẹ",
            "lợi nhuận sau thuế của công ty mẹ",
        ),
        raw_label_aliases_en=(
            "profit after tax attributable to the parent company's owners",
            "profit attributable to parent company owners",
        ),
        description="Net profit attributable to parent company equity holders",
        is_parent_attributable=True,
    ),
    "basic_eps": MetricDefinition(
        canonical_metric="basic_eps",
        entity_class=EntityClass.SECURITIES,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="72",
        raw_label_aliases_vi=("lãi cơ bản trên cổ phiếu",),
        raw_label_aliases_en=("basic earnings per share", "earnings per share"),
        description="Basic earnings per share (VND/share)",
    ),
    "operating_cash_flow": MetricDefinition(
        canonical_metric="operating_cash_flow",
        entity_class=EntityClass.SECURITIES,
        statement_family="cash_flow",
        temporal_nature="duration",
        standard_line_code="20",
        raw_label_aliases_vi=("lưu chuyển tiền thuần từ hoạt động kinh doanh",),
        raw_label_aliases_en=("net cash flows from operating activities", "net cash used in operating activities"),
        description="Net cash flow from operating activities",
    ),
    "period_end_outstanding_ordinary_shares": MetricDefinition(
        canonical_metric="period_end_outstanding_ordinary_shares",
        entity_class=EntityClass.SECURITIES,
        statement_family="notes_and_disclosures",
        temporal_nature="instant",
        standard_line_code=None,
        raw_label_aliases_vi=("số lượng cổ phiếu phổ thông đang lưu hành", "cổ phiếu phổ thông"),
        raw_label_aliases_en=("outstanding shares - ordinary shares", "ordinary shares outstanding"),
        description="Number of outstanding ordinary shares at period end",
        disclosure_family="share_capital",
    ),
}


# Schema definitions for Insurance (Schema-only until real-data proof filing is acquired)
INSURANCE_METRICS: dict[str, MetricDefinition] = {
    "net_insurance_revenue": MetricDefinition(
        canonical_metric="net_insurance_revenue",
        entity_class=EntityClass.INSURANCE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="10",
        raw_label_aliases_vi=("doanh thu thuần hoạt động kinh doanh bảo hiểm",),
        raw_label_aliases_en=("net revenue from insurance activities",),
        description="Net premium and insurance revenue",
    ),
    "claim_expenses": MetricDefinition(
        canonical_metric="claim_expenses",
        entity_class=EntityClass.INSURANCE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="11",
        raw_label_aliases_vi=("chi phí bồi thường và trả tiền bảo hiểm",),
        raw_label_aliases_en=("insurance claim expenses",),
        description="Gross claim and insurance benefit payments",
        disclosure_family="claim_reserves",
    ),
    "technical_reserves": MetricDefinition(
        canonical_metric="technical_reserves",
        entity_class=EntityClass.INSURANCE,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="318",
        raw_label_aliases_vi=("dự phòng nghiệp vụ bảo hiểm",),
        raw_label_aliases_en=("technical reserves", "insurance contract reserves"),
        description="Mathematical, unearned premium, and claim reserves",
        disclosure_family="technical_reserves",
    ),
    "total_assets": MetricDefinition(
        canonical_metric="total_assets",
        entity_class=EntityClass.INSURANCE,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="270",
        raw_label_aliases_vi=("tổng cộng tài sản", "tổng tài sản"),
        raw_label_aliases_en=("total assets",),
        description="Total insurance assets",
    ),
    "total_equity": MetricDefinition(
        canonical_metric="total_equity",
        entity_class=EntityClass.INSURANCE,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="400",
        raw_label_aliases_vi=("vốn chủ sở hữu",),
        raw_label_aliases_en=("owners' equity", "total equity"),
        description="Total equity of insurance entity",
    ),
    "net_income": MetricDefinition(
        canonical_metric="net_income",
        entity_class=EntityClass.INSURANCE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="60",
        raw_label_aliases_vi=("lợi nhuận sau thuế",),
        raw_label_aliases_en=("net profit after tax",),
        description="Net profit after tax of insurance entity",
    ),
}


# Schema definitions for Finance Company (Schema-only until real-data proof filing is acquired)
FINANCE_COMPANY_METRICS: dict[str, MetricDefinition] = {
    "interest_income": MetricDefinition(
        canonical_metric="interest_income",
        entity_class=EntityClass.FINANCE_COMPANY,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="1",
        raw_label_aliases_vi=("thu nhập lãi và các khoản thu nhập tương tự",),
        raw_label_aliases_en=("interest and similar income",),
        description="Interest income from consumer lending / leasing",
    ),
    "customer_loans_net": MetricDefinition(
        canonical_metric="customer_loans_net",
        entity_class=EntityClass.FINANCE_COMPANY,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="III.LOAN",
        raw_label_aliases_vi=("cho vay khách hàng",),
        raw_label_aliases_en=("loans to customers net",),
        description="Net consumer loan and finance lease receivables",
    ),
    "total_assets": MetricDefinition(
        canonical_metric="total_assets",
        entity_class=EntityClass.FINANCE_COMPANY,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="B",
        raw_label_aliases_vi=("tổng cộng tài sản", "tổng tài sản"),
        raw_label_aliases_en=("total assets",),
        description="Total finance company assets",
    ),
    "total_equity": MetricDefinition(
        canonical_metric="total_equity",
        entity_class=EntityClass.FINANCE_COMPANY,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="VIII",
        raw_label_aliases_vi=("vốn chủ sở hữu",),
        raw_label_aliases_en=("owners' equity",),
        description="Total equity of finance company",
    ),
    "profit_before_tax": MetricDefinition(
        canonical_metric="profit_before_tax",
        entity_class=EntityClass.FINANCE_COMPANY,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="XI",
        raw_label_aliases_vi=("tổng lợi nhuận trước thuế",),
        raw_label_aliases_en=("profit before tax",),
        description="Profit before tax of finance company",
    ),
}


# Ordinary corporate standard metrics
CORPORATE_METRICS: dict[str, MetricDefinition] = {
    "ebitda": MetricDefinition(
        canonical_metric="ebitda",
        entity_class=EntityClass.CORPORATE,
        statement_family="derived",
        temporal_nature="duration",
        standard_line_code=None,
        raw_label_aliases_vi=("ebitda",),
        raw_label_aliases_en=("ebitda",),
        description="Earnings before interest, taxes, depreciation, and amortization",
    ),
    "revenue": MetricDefinition(
        canonical_metric="revenue",
        entity_class=EntityClass.CORPORATE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="10",
        raw_label_aliases_vi=("doanh thu bán hàng và cung cấp dịch vụ", "doanh thu thuần"),
        raw_label_aliases_en=("revenue from sales of goods and rendering of services", "net revenue"),
        description="Net revenue from goods and services",
    ),
    "cost_of_goods_sold": MetricDefinition(
        canonical_metric="cost_of_goods_sold",
        entity_class=EntityClass.CORPORATE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="11",
        raw_label_aliases_vi=("giá vốn hàng bán",),
        raw_label_aliases_en=("cost of goods sold", "cost of sales"),
        description="Cost of goods sold",
        sign_multiplier=1,
    ),
    "gross_profit": MetricDefinition(
        canonical_metric="gross_profit",
        entity_class=EntityClass.CORPORATE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="20",
        raw_label_aliases_vi=("lợi nhuận gộp về bán hàng và cung cấp dịch vụ", "lợi nhuận gộp"),
        raw_label_aliases_en=("gross profit from sales of goods and rendering of services", "gross profit"),
        description="Gross operating profit",
    ),
    "financial_income": MetricDefinition(
        canonical_metric="financial_income",
        entity_class=EntityClass.CORPORATE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="21",
        raw_label_aliases_vi=("doanh thu hoạt động tài chính",),
        raw_label_aliases_en=("financial income", "finance income"),
        description="Financial income",
    ),
    "financial_expenses": MetricDefinition(
        canonical_metric="financial_expenses",
        entity_class=EntityClass.CORPORATE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="22",
        raw_label_aliases_vi=("chi phí tài chính",),
        raw_label_aliases_en=("financial expenses", "finance costs"),
        description="Total financial expenses",
        sign_multiplier=1,
    ),
    "interest_expense": MetricDefinition(
        canonical_metric="interest_expense",
        entity_class=EntityClass.CORPORATE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="23",
        raw_label_aliases_vi=("chi phí lãi vay", "trong đó: chi phí lãi vay"),
        raw_label_aliases_en=("interest expenses", "of which: interest expense"),
        description="Interest expenses incurred on borrowings",
        sign_multiplier=1,
    ),
    "selling_expense": MetricDefinition(
        canonical_metric="selling_expense",
        entity_class=EntityClass.CORPORATE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="25",
        raw_label_aliases_vi=("chi phí bán hàng",),
        raw_label_aliases_en=("selling expenses",),
        description="Selling and distribution expenses",
        sign_multiplier=1,
    ),
    "general_admin_expense": MetricDefinition(
        canonical_metric="general_admin_expense",
        entity_class=EntityClass.CORPORATE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="26",
        raw_label_aliases_vi=("chi phí quản lý doanh nghiệp",),
        raw_label_aliases_en=("general and administrative expenses", "administrative expenses"),
        description="General and administrative overhead expenses",
        sign_multiplier=1,
    ),
    "operating_profit": MetricDefinition(
        canonical_metric="operating_profit",
        entity_class=EntityClass.CORPORATE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="30",
        raw_label_aliases_vi=("lợi nhuận thuần từ hoạt động kinh doanh",),
        raw_label_aliases_en=("net operating profit", "operating profit"),
        description="Net operating profit",
    ),
    "profit_before_tax": MetricDefinition(
        canonical_metric="profit_before_tax",
        entity_class=EntityClass.CORPORATE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="50",
        raw_label_aliases_vi=("tổng lợi nhuận kế toán trước thuế", "lợi nhuận trước thuế"),
        raw_label_aliases_en=("total accounting profit before tax", "profit before tax"),
        description="Total accounting profit before corporate income tax",
    ),
    "net_income": MetricDefinition(
        canonical_metric="net_income",
        entity_class=EntityClass.CORPORATE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="60",
        raw_label_aliases_vi=("lợi nhuận sau thuế thu nhập doanh nghiệp", "lợi nhuận sau thuế"),
        raw_label_aliases_en=("net profit after corporate income tax", "profit after tax"),
        description="Total net profit after tax",
    ),
    "net_income_parent": MetricDefinition(
        canonical_metric="net_income_parent",
        entity_class=EntityClass.CORPORATE,
        statement_family="income_statement",
        temporal_nature="duration",
        standard_line_code="61",
        raw_label_aliases_vi=(
            "lợi nhuận sau thuế của công ty mẹ",
            "lợi nhuận sau thuế của cổ đông công ty mẹ",
            "lợi nhuận sau thuế thuộc về chủ sở hữu công ty mẹ",
        ),
        raw_label_aliases_en=(
            "profit after tax attributable to the parent company",
            "net profit attributable to owners of the parent",
        ),
        description="Net profit attributable to parent company shareholders",
        is_parent_attributable=True,
    ),
    "total_assets": MetricDefinition(
        canonical_metric="total_assets",
        entity_class=EntityClass.CORPORATE,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="270",
        raw_label_aliases_vi=("tổng cộng tài sản", "tổng tài sản"),
        raw_label_aliases_en=("total assets",),
        description="Total corporate assets",
    ),
    "current_assets": MetricDefinition(
        canonical_metric="current_assets",
        entity_class=EntityClass.CORPORATE,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="100",
        raw_label_aliases_vi=("tài sản ngắn hạn",),
        raw_label_aliases_en=("current assets",),
        description="Total current short-term assets",
    ),
    "cash_and_equivalents": MetricDefinition(
        canonical_metric="cash_and_equivalents",
        entity_class=EntityClass.CORPORATE,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="110",
        raw_label_aliases_vi=("tiền và các khoản tương đương tiền",),
        raw_label_aliases_en=("cash and cash equivalents",),
        description="Cash and short-term cash equivalents",
    ),
    "total_liabilities": MetricDefinition(
        canonical_metric="total_liabilities",
        entity_class=EntityClass.CORPORATE,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="300",
        raw_label_aliases_vi=("nợ phải trả", "tổng nợ phải trả"),
        raw_label_aliases_en=("total liabilities", "liabilities"),
        description="Total liabilities",
    ),
    "current_liabilities": MetricDefinition(
        canonical_metric="current_liabilities",
        entity_class=EntityClass.CORPORATE,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="310",
        raw_label_aliases_vi=("nợ ngắn hạn",),
        raw_label_aliases_en=("current liabilities",),
        description="Total current liabilities",
    ),
    "total_interest_bearing_debt": MetricDefinition(
        canonical_metric="total_interest_bearing_debt",
        entity_class=EntityClass.CORPORATE,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="320+338",
        raw_label_aliases_vi=("vay và nợ thuê tài chính",),
        raw_label_aliases_en=("borrowings and finance lease liabilities", "total interest bearing debt"),
        description="Total short-term and long-term interest-bearing loans and borrowings",
        disclosure_family="borrowings_and_finance_leases",
    ),
    "shareholders_equity": MetricDefinition(
        canonical_metric="shareholders_equity",
        entity_class=EntityClass.CORPORATE,
        statement_family="balance_sheet",
        temporal_nature="instant",
        standard_line_code="400",
        raw_label_aliases_vi=("vốn chủ sở hữu",),
        raw_label_aliases_en=("owners' equity", "total equity"),
        description="Total shareholders' equity",
        disclosure_family="owners_equity",
    ),
    "operating_cash_flow": MetricDefinition(
        canonical_metric="operating_cash_flow",
        entity_class=EntityClass.CORPORATE,
        statement_family="cash_flow",
        temporal_nature="duration",
        standard_line_code="20",
        raw_label_aliases_vi=("lưu chuyển tiền thuần từ hoạt động kinh doanh",),
        raw_label_aliases_en=("net cash flows from operating activities", "net cash flows from/(used in) operating activities"),
        description="Net cash flows from operating activities",
    ),
}

ALL_SECTOR_METRICS: dict[EntityClass, dict[str, MetricDefinition]] = {
    EntityClass.BANK: BANK_METRICS,
    EntityClass.SECURITIES: SECURITIES_METRICS,
    EntityClass.INSURANCE: INSURANCE_METRICS,
    EntityClass.FINANCE_COMPANY: FINANCE_COMPANY_METRICS,
    EntityClass.CORPORATE: CORPORATE_METRICS,
}


def evaluate_metric_sector_applicability(
    entity_class: EntityClass | str,
    canonical_metric: str,
) -> MetricApplicabilityResult:
    """Evaluate whether a canonical metric is applicable to a specific entity class.

    Enforces:
    1. Financial intermediaries fail closed on ordinary-corporate EBITDA/debt concepts.
    2. Unknown entity classes fail closed.
    3. Metrics not declared in the sector vocabulary return UNSUPPORTED_SECTOR_METRIC.
    4. Zero silent semantic conversions.
    """
    clean_metric = str(canonical_metric).strip().lower()
    
    # Parse entity class
    if isinstance(entity_class, EntityClass):
        e_class = entity_class
    else:
        try:
            e_class = EntityClass(str(entity_class).strip().lower())
        except ValueError:
            e_class = EntityClass.UNKNOWN

    if e_class == EntityClass.UNKNOWN:
        return MetricApplicabilityResult(
            canonical_metric=clean_metric,
            entity_class=EntityClass.UNKNOWN,
            applicability=MetricApplicabilityState.UNKNOWN_ENTITY_CLASS,
            reason_codes=("UNKNOWN_ENTITY_CLASS; fails closed",),
            is_ordinary_corporate_metric=False,
        )

    # Check explicit inapplicability for financial intermediaries
    inapplicable_set = SECTOR_INAPPLICABLE_CORPORATE_METRICS.get(e_class, set())
    if clean_metric in inapplicable_set:
        return MetricApplicabilityResult(
            canonical_metric=clean_metric,
            entity_class=e_class,
            applicability=MetricApplicabilityState.NOT_APPLICABLE,
            reason_codes=(f"CORPORATE_METRIC_INAPPLICABLE_FOR_{e_class.value.upper()}",),
            is_ordinary_corporate_metric=True,
        )

    # Check sector metric vocabulary
    sector_vocab = ALL_SECTOR_METRICS.get(e_class, {})
    if clean_metric in sector_vocab:
        defn = sector_vocab[clean_metric]
        return MetricApplicabilityResult(
            canonical_metric=clean_metric,
            entity_class=e_class,
            applicability=MetricApplicabilityState.APPLICABLE,
            reason_codes=(f"VALID_SECTOR_METRIC_FOR_{e_class.value.upper()}",),
            statement_family=defn.statement_family,
            temporal_nature=defn.temporal_nature,
            is_ordinary_corporate_metric=(e_class == EntityClass.CORPORATE),
        )

    # Universal financial facts across all sectors (e.g. total_assets, total_equity, profit_before_tax)
    # if defined under generic vocabulary
    if clean_metric in {"total_assets", "total_equity", "profit_before_tax"}:
        if clean_metric in sector_vocab:
            defn = sector_vocab[clean_metric]
            return MetricApplicabilityResult(
                canonical_metric=clean_metric,
                entity_class=e_class,
                applicability=MetricApplicabilityState.APPLICABLE,
                reason_codes=(f"UNIVERSAL_SECTOR_METRIC_FOR_{e_class.value.upper()}",),
                statement_family=defn.statement_family,
                temporal_nature=defn.temporal_nature,
                is_ordinary_corporate_metric=False,
            )

    return MetricApplicabilityResult(
        canonical_metric=clean_metric,
        entity_class=e_class,
        applicability=MetricApplicabilityState.UNSUPPORTED_SECTOR_METRIC,
        reason_codes=(f"UNSUPPORTED_SECTOR_METRIC_FOR_{e_class.value.upper()}",),
        is_ordinary_corporate_metric=False,
    )
