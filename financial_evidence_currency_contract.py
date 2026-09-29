"""Frozen Cohort-1 contract for official financial-evidence currency refresh.

This module is the milestone vocabulary only.  It does not fetch, parse, or
promote facts.  Official qualification still requires digit-for-digit support plus
currency, scale, scope, period, and citation through the existing
``official_financial_filing_evidence`` / ``official_financial_value_evidence`` /
``canonical_financial_qualification_policy`` path.
"""
from __future__ import annotations

from typing import Mapping

CONTRACT_VERSION = "financial_evidence_currency_refresh/v1"
MILESTONE_ID = "FINANCIAL_EVIDENCE_CURRENCY_AND_OFFICIAL_STATEMENT_REFRESH_V1"
PUBLIC_ARTIFACT_DIR = "derived/financial-evidence-currency-refresh-v1"
DEFAULT_LANDING_ROOT = r"C:\Projects\StockLookup\data-landing\official-financial-filings-v1"

COHORT: tuple[str, ...] = (
    "HPG", "VNM", "FPT", "PNJ", "PAN", "PVD", "NVL",
    "POW", "SSI", "GAS", "VRE", "VCB", "QNS", "EVF",
)

# FY2025 annual, plus one current interim.  H1 2026 is preferred; Q2 2026 is the
# entity-family alternative.  Both names may be requested, but a ticker retains
# at most two target documents total.  Q3 2026 is out of scope.
TARGET_ANNUAL_PERIOD = "2025"
TARGET_INTERIM_PERIODS: tuple[str, ...] = ("2026-H1", "2026-Q2")
TARGET_PERIODS: tuple[str, ...] = (TARGET_ANNUAL_PERIOD, *TARGET_INTERIM_PERIODS)
OUT_OF_SCOPE_PERIODS: frozenset[str] = frozenset({"2026-Q3", "2026-Q4", "2026-H2"})

HTTP_REQUEST_CAP = 40
CONCURRENCY = 1
MAX_DOCUMENTS_PER_ISSUER = 2
MAX_INDEX_PAGES_PER_ISSUER = 1
STORAGE_BUDGET_BYTES = 5 * 1024 * 1024 * 1024
FINANCIAL_V2_PIN_TICKER_THRESHOLD = 5

ENTITY_FAMILY: dict[str, str] = {
    "HPG": "corporate", "VNM": "corporate", "FPT": "corporate", "PNJ": "corporate",
    "PAN": "corporate", "PVD": "corporate", "NVL": "corporate", "POW": "corporate",
    "GAS": "corporate", "VRE": "corporate", "QNS": "corporate",
    "SSI": "securities",
    "VCB": "bank",
    "EVF": "finance_company",
}

CORPORATE_CORE_METRICS: tuple[str, ...] = (
    "revenue", "net_income", "attributable_net_income",
    "shareholders_equity", "total_assets", "cash_and_cash_equivalents",
    "operating_cash_flow", "short_term_interest_bearing_debt",
    "long_term_interest_bearing_debt",
)
BANK_CORE_METRICS: tuple[str, ...] = (
    "net_profit_parent", "total_equity", "total_assets",
    "customer_loans_net", "customer_deposits", "provision_for_credit_losses",
)
SECURITIES_CORE_METRICS: tuple[str, ...] = (
    "total_equity", "total_assets", "brokerage_revenue", "total_operating_revenue",
)
FINANCE_COMPANY_CORE_METRICS: tuple[str, ...] = ()  # EVF is route-discovery only in this cohort.

OPTIONAL_METRICS: frozenset[str] = frozenset({
    "period_end_outstanding_ordinary_shares", "current_common_shares",
    "profit_before_tax", "gross_profit", "current_assets", "current_liabilities",
    "net_interest_income", "fee_income",
})

NOT_APPLICABLE_CORPORATE_DEBT_EBITDA = frozenset({"bank", "securities", "finance_company", "insurance"})

INDEX_DOCUMENT_TYPE = "issuer_ir_index_page"
ANNUAL_DOCUMENT_CLASS = "audited_annual_financial_statements"
INTERIM_DOCUMENT_CLASS = "reviewed_interim_financial_statements"

# Direct first-party locators already evidenced in the retained repository.  These
# are not guessed URL variations.
DIRECT_TARGET_LOCATORS: tuple[dict[str, str], ...] = (
    {
        "ticker": "VRE", "period": "2025",
        "url": "https://ir.vincom.com.vn/wp-content/uploads/2026/03/BCTC-hop-nhat-2025-1.pdf",
        "document_class": "audited_annual_financial_statements",
    },
)

# One admitted IR index/page per issuer.  EVF has no admitted issuer-IR host.
ISSUER_IR_INDEX_SEEDS: dict[str, str] = {
    "HPG": "https://www.hoaphat.com.vn/quan-he-co-dong/bao-cao-tai-chinh",
    "VNM": "https://www.vinamilk.com.vn/vi/nha-dau-tu",
    "FPT": "https://fpt.com/en/ir/report",
    "PNJ": "https://www.pnj.com.vn/quan-he-co-dong/bao-cao-tai-chinh/",
    "PVD": "https://www.pvdrilling.com.vn/quan-he-co-dong/bao-cao-tai-chinh",
    "NVL": "https://www.novaland.com.vn/quan-he-dau-tu/bao-cao-tai-chinh",
    "POW": "https://www.pvpower.vn/quan-he-co-dong/bao-cao-tai-chinh",
    "SSI": "https://www.ssi.com.vn/nha-dau-tu/bao-cao-tai-chinh",
    "GAS": "https://www.pvgas.com.vn/quan-he-co-dong",
    "VRE": "https://ir.vincom.com.vn/",
    "VCB": "https://www.vietcombank.com.vn/vn/nha-dau-tu",
    "QNS": "https://www.qns.com.vn/",
}

EVF_BLOCKER = "NO_ADMITTED_ISSUER_IR_HOST"
PAN_INDEX_BLOCKER = "NO_ADMITTED_IR_INDEX_HOST_STORAGE_ONLY"

LEGACY_PROVIDER_LABEL = "LEGACY_RESEARCH_PROXY"
LEGACY_SOURCE_STATUS = "provider_reported"


def core_metrics_for(ticker: str) -> tuple[str, ...]:
    family = ENTITY_FAMILY[str(ticker).upper()]
    if family == "corporate":
        return CORPORATE_CORE_METRICS
    if family == "bank":
        return BANK_CORE_METRICS
    if family == "securities":
        return SECURITIES_CORE_METRICS
    return FINANCE_COMPANY_CORE_METRICS


def entity_family(ticker: str) -> str:
    return ENTITY_FAMILY[str(ticker).upper()]


def corporate_debt_ebitda_applicable(ticker: str) -> bool:
    return entity_family(ticker) not in NOT_APPLICABLE_CORPORATE_DEBT_EBITDA


def is_target_period(period: str) -> bool:
    return str(period) in TARGET_PERIODS


def is_out_of_scope_period(period: str) -> bool:
    return str(period) in OUT_OF_SCOPE_PERIODS


def period_document_class(period: str) -> str:
    if str(period) == TARGET_ANNUAL_PERIOD:
        return ANNUAL_DOCUMENT_CLASS
    if str(period) in TARGET_INTERIM_PERIODS:
        return INTERIM_DOCUMENT_CLASS
    raise ValueError(f"unsupported_target_period:{period}")


def canonical_stock_period_alias(period: str, statement_family: str) -> tuple[str, ...]:
    """Balance-sheet instants alias FY <-> Q4 and H1 <-> Q2.  Flows do not."""
    period = str(period)
    if statement_family != "balance_sheet":
        return (period,)
    if period.isdigit() and len(period) == 4:
        return (period, f"{period}-Q4")
    if period.endswith("-Q4") and period[:4].isdigit():
        return (period, period[:4])
    if period == "2026-H1":
        return ("2026-H1", "2026-Q2")
    if period == "2026-Q2":
        return ("2026-Q2", "2026-H1")
    return (period,)


def pin_rebuild_eligible(*, tickers_with_new_qualified_core: int,
                         unresolved_schema_ambiguity: bool) -> bool:
    return (tickers_with_new_qualified_core >= FINANCIAL_V2_PIN_TICKER_THRESHOLD
            and not unresolved_schema_ambiguity)


def official_ttm_eligible(official_flow_periods: Mapping[str, object] | list[str] | tuple[str, ...] | None) -> bool:
    """Four comparable official quarters are required.  FY + H1 is not TTM."""
    if official_flow_periods is None:
        return False
    periods = set(official_flow_periods) if not isinstance(official_flow_periods, dict) else set(official_flow_periods)
    quarters = {str(item) for item in periods if str(item).endswith(("-Q1", "-Q2", "-Q3", "-Q4"))}
    return len(quarters) >= 4
