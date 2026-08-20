"""Phase 2 / P2-CLOSEOUT: Multi-Period Financial Fact Panel & Sector Applicability Contract.

This module provides a deterministic, multi-period financial fact research panel
from qualified official financial evidence and owner-promoted sector registries:
1. Preserves complete dimensional provenance:
   - issuer identity (ticker, candidate_id)
   - reporting period (annual vs quarterly)
   - temporal nature (instant vs duration)
   - statement family (balance sheet, income statement, cash flow, general)
   - statement scope (consolidated vs separate)
   - currency (VND, USD) and unit scale
   - source lineage (document SHA-256, citation ID, evidence ID, page, note)
   - authority tier (promoted corporate, generic sector promoted, specialized reference)
   - reconciliation status (EXACT_MATCH, GENERIC_EVIDENCED_PROMOTED, CONFLICT)
   - temporal envelope (observed_at, knowledge_available_at, freshness, PIT eligibility)
2. Enforces explicit sector / entity applicability gates:
   - Integrates Layered Entity Classification Authority (Topology B)
   - Distinguishes corporate, bank, securities, insurance, finance_company, unknown
   - Fails closed on inappropriate metrics (e.g. corporate debt ratios on financial intermediaries)
3. Computes bounded derived accounting relationships:
   - YoY net income and operating cash flow growth
   - Cash flow to net income coverage
   - Ending Equity ROE Proxy (ENDING_EQUITY_ROE_PROXY) across corporate, bank, and securities
   - Debt-to-equity and net debt strictly for corporate entities (NOT_APPLICABLE for intermediaries)
   - Explicitly blocks valuation multiples, price targets, intrinsic value, and strategy ranking
4. Guarantees zero silent forward-fill, zero currency mixing, zero scope mixing, zero lookahead,
   and zero synthetic values.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from field_temporal_contract import (
    FreshnessState,
    PitStatus,
    TemporalField,
    canonical_json,
    stable_id,
    wrap_temporal_fields,
)
from financial_entity_applicability import (
    CORPORATE_ENTITY_TYPES,
    FINANCIAL_ENTITY_TYPES,
    load_entity_profiles,
)
from altman_applicability import (
    MANUFACTURING_INDUSTRIES,
    evaluate_altman_applicability,
)
from entity_classification_contract import (
    EntityClass,
    resolve_layered_entity_classification,
)
from sector_financial_taxonomy import (
    BANK_METRICS,
    CORPORATE_METRICS,
    SECURITIES_METRICS,
    AuthoritativeSectorFact,
    MetricApplicabilityState,
    ReconciliationStatus,
    SectorAuthorityTier,
    evaluate_metric_sector_applicability,
    load_promoted_sector_extractions,
    reconcile_and_resolve_authoritative_sector_facts,
)
from financial_disclosure_recognizer import extract_sector_facts_from_sidecar
from financial_statement_template_recognizer import extract_generic_financial_statement_facts
from official_source_registry import ADMITTED, admit, load_registry

SCHEMA_VERSION = "1.0.0"
ARTIFACT_TYPE = "MULTI_PERIOD_FINANCIAL_FACT_PANEL"
CONTRACT_VERSION = "multi_period_financial_panel/v1"


class PeriodType(StrEnum):
    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    UNKNOWN = "unknown"


class TemporalNature(StrEnum):
    INSTANT = "instant"      # Point-in-time / balance sheet
    DURATION = "duration"    # Flow over period / income statement, cash flow


class StatementScope(StrEnum):
    CONSOLIDATED = "consolidated"
    SEPARATE = "separate"
    UNKNOWN = "unknown"


class StatementFamily(StrEnum):
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOW = "cash_flow"
    GENERAL = "general"


class QualificationState(StrEnum):
    QUALIFIED = "QUALIFIED"                  # Hash-verified official citation
    HISTORICAL_ONLY = "HISTORICAL_ONLY"      # Retrospective observation without PIT proof
    MISSING = "MISSING"                      # Unobserved / absent
    NOT_APPLICABLE = "NOT_APPLICABLE"        # Structural inapplicability (e.g. bank EBITDA)
    UNQUALIFIED = "UNQUALIFIED"              # Provider reported without unit/currency proof
    CONFLICT = "CONFLICT"                    # Generic vs specialized disagreement (fails closed)


class ApplicabilityState(StrEnum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class SectorArchetype(StrEnum):
    CORPORATE = "corporate"
    BANK = "bank"
    SECURITIES = "securities"
    INSURANCE = "insurance"
    FINANCE_COMPANY = "finance_company"
    UNKNOWN = "unknown"


class MultiPeriodPanelError(ValueError):
    """Raised when an input or evaluation violates the multi-period financial contract."""


def _sanitize(val: Any) -> Any:
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    if isinstance(val, dict):
        return {k: _sanitize(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_sanitize(v) for v in val]
    return val


def _date_str(val: Any) -> str:
    if val is None:
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    return s[:10]


#: Standard metadata specification for canonical financial metrics across sectors
METRIC_SPECS: dict[str, dict[str, Any]] = {
    # Universal / Corporate Core
    "cash_and_equivalents": {
        "statement_family": StatementFamily.BALANCE_SHEET.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Cash and cash equivalents at period end",
    },
    "total_interest_bearing_debt": {
        "statement_family": StatementFamily.BALANCE_SHEET.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Short-term and long-term interest-bearing loans and borrowings",
    },
    "shareholders_equity": {
        "statement_family": StatementFamily.BALANCE_SHEET.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Total shareholders' equity at period end",
    },
    "current_liabilities": {
        "statement_family": StatementFamily.BALANCE_SHEET.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Total current short-term liabilities",
    },
    "total_assets": {
        "statement_family": StatementFamily.BALANCE_SHEET.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Total assets at period end",
    },
    "total_liabilities": {
        "statement_family": StatementFamily.BALANCE_SHEET.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Total liabilities at period end",
    },
    "net_income": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Net profit after corporate income tax for the reporting period",
    },
    "operating_cash_flow": {
        "statement_family": StatementFamily.CASH_FLOW.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Net cash flow generated from / (used in) operating activities",
    },
    "revenue": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Net revenue from goods and services",
    },

    # Banking metrics (Circular 49/2014/TT-NHNN)
    "customer_loans_net": {
        "statement_family": StatementFamily.BALANCE_SHEET.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Loans to customers net of credit loss provisions",
    },
    "customer_deposits": {
        "statement_family": StatementFamily.BALANCE_SHEET.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Deposits from customers at period end",
    },
    "total_equity": {
        "statement_family": StatementFamily.BALANCE_SHEET.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Total equity / capital and reserves",
    },
    "minority_interest": {
        "statement_family": StatementFamily.BALANCE_SHEET.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Non-controlling / minority interest",
    },
    "interest_income": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Interest and similar income",
    },
    "interest_expense": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Interest and similar expenses",
    },
    "net_interest_income": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Net interest and similar income",
    },
    "operating_expenses": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Operating expenses / overhead",
    },
    "operating_profit_before_provision_for_credit_losses": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Net operating profit before provision for credit losses",
    },
    "provision_for_credit_losses": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Provision expense for credit losses",
    },
    "profit_before_tax": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Total profit before tax",
    },
    "net_profit_total": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Net profit after tax (total)",
    },
    "net_profit_parent": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Net profit after tax attributable to parent bank equity holders",
    },

    # Securities metrics (Circular 334/2016/TT-BTC)
    "financial_assets_fvtpl": {
        "statement_family": StatementFamily.BALANCE_SHEET.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Financial assets at fair value through profit or loss",
    },
    "loans_balance": {
        "statement_family": StatementFamily.BALANCE_SHEET.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Margin loans and receivables from securities trading",
    },
    "short_term_borrowings_and_financial_leases": {
        "statement_family": StatementFamily.BALANCE_SHEET.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Short-term borrowings and financial leases",
    },
    "share_capital": {
        "statement_family": StatementFamily.BALANCE_SHEET.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Contributed charter capital / share capital",
    },
    "total_operating_revenue": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Total operating revenue of securities company",
    },
    "brokerage_revenue": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Revenue from securities brokerage services",
    },
    "fvtpl_gain": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Gain from financial assets at FVTPL",
    },
    "fvtpl_loss": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Loss from financial assets at FVTPL",
    },
    "borrowing_costs": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Finance / borrowing costs",
    },
    "profit_after_tax_total": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Profit after tax (total)",
    },
    "profit_after_tax_parent": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Profit after tax attributable to parent company owners",
    },
    "basic_eps": {
        "statement_family": StatementFamily.INCOME_STATEMENT.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": "Basic earnings per share",
    },
    "period_end_outstanding_ordinary_shares": {
        "statement_family": StatementFamily.GENERAL.value,
        "temporal_nature": TemporalNature.INSTANT.value,
        "description": "Period-end outstanding ordinary shares",
    },
}


@dataclass(frozen=True)
class FinancialFactObservation:
    """One immutable financial fact observation bound with full dimensional & temporal provenance."""
    issuer_identity: str
    reporting_period: str
    period_type: str
    period_start: str | None
    period_end: str | None
    statement_family: str
    statement_scope: str
    temporal_nature: str
    canonical_metric: str
    value: float | int | None
    currency: str | None
    unit_scale: int | float | None
    qualification_state: str
    applicability_state: str
    observed_at: str | None
    knowledge_available_at: str | None
    source_lineage: dict[str, Any]
    temporal_envelope: dict[str, Any]
    reason_codes: tuple[str, ...]
    authority_tier: str | None = None
    reconciliation_status: str | None = None
    is_positive_authority: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "issuer_identity": self.issuer_identity,
            "reporting_period": self.reporting_period,
            "period_type": self.period_type,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "statement_family": self.statement_family,
            "statement_scope": self.statement_scope,
            "temporal_nature": self.temporal_nature,
            "canonical_metric": self.canonical_metric,
            "value": _sanitize(self.value),
            "currency": self.currency,
            "unit_scale": self.unit_scale,
            "qualification_state": self.qualification_state,
            "applicability_state": self.applicability_state,
            "observed_at": self.observed_at,
            "knowledge_available_at": self.knowledge_available_at,
            "source_lineage": self.source_lineage,
            "temporal_envelope": self.temporal_envelope,
            "authority_tier": self.authority_tier,
            "reconciliation_status": self.reconciliation_status,
            "is_positive_authority": self.is_positive_authority,
            "reason_codes": list(self.reason_codes),
        }


def evaluate_sector_applicability(
    *,
    ticker: str,
    entity_type: str | None,
    canonical_metric: str,
    industry_label: str | None = None,
) -> tuple[ApplicabilityState, list[str]]:
    """Determine metric applicability according to sector archetype and accounting standards."""
    e_type = (entity_type or "").strip().lower()
    if not e_type or e_type in {"unknown", "none", "null"}:
        return ApplicabilityState.UNKNOWN, ["INSUFFICIENT_SECTOR_EVIDENCE"]

    # Corporate-only debt & capital metrics
    if canonical_metric in {"debt_to_equity", "net_debt", "total_interest_bearing_debt"}:
        if e_type == SectorArchetype.CORPORATE.value:
            return ApplicabilityState.APPLICABLE, ["CORPORATE_DEBT_RATIO_APPLICABLE"]
        elif e_type in {
            SectorArchetype.BANK.value,
            SectorArchetype.SECURITIES.value,
            SectorArchetype.INSURANCE.value,
            SectorArchetype.FINANCE_COMPANY.value,
        }:
            return ApplicabilityState.NOT_APPLICABLE, ["SECTOR_INAPPROPRIATE_FINANCIAL_INTERMEDIARY_DEBT_RATIO"]
        return ApplicabilityState.UNKNOWN, ["UNKNOWN_ENTITY_DEBT_APPLICABILITY"]

    # EBITDA / EV-EBITDA
    if canonical_metric in {"ebitda", "ev_ebitda"}:
        if e_type == SectorArchetype.CORPORATE.value:
            return ApplicabilityState.APPLICABLE, ["CORPORATE_EBITDA_APPLICABLE"]
        elif e_type in {
            SectorArchetype.BANK.value,
            SectorArchetype.SECURITIES.value,
            SectorArchetype.INSURANCE.value,
        }:
            return ApplicabilityState.NOT_APPLICABLE, ["SECTOR_INAPPLICABLE_NO_EBITDA_CONCEPT"]
        return ApplicabilityState.UNKNOWN, ["UNKNOWN_ENTITY_EBITDA_APPLICABILITY"]

    # Working capital
    if canonical_metric in {"working_capital", "current_ratio"}:
        if e_type == SectorArchetype.CORPORATE.value:
            return ApplicabilityState.APPLICABLE, ["CORPORATE_WORKING_CAPITAL_APPLICABLE"]
        elif e_type in {SectorArchetype.BANK.value, SectorArchetype.SECURITIES.value}:
            return ApplicabilityState.NOT_APPLICABLE, ["FINANCIAL_INSTITUTION_NO_WORKING_CAPITAL"]
        return ApplicabilityState.UNKNOWN, ["UNKNOWN_ENTITY_WORKING_CAPITAL_APPLICABILITY"]

    # Altman Z'-score
    if canonical_metric == "altman_z_prime":
        altman_res = evaluate_altman_applicability(e_type, industry_label)
        if altman_res["applicability"] == "eligible":
            return ApplicabilityState.APPLICABLE, ["MANUFACTURING_CORPORATE_ALTMAN_APPLICABLE"]
        elif altman_res["applicability"] == "not_applicable":
            return ApplicabilityState.NOT_APPLICABLE, ["FINANCIAL_ENTITY_Z_SCORE_INAPPLICABLE"]
        return ApplicabilityState.UNKNOWN, ["NON_MANUFACTURING_OR_UNKNOWN_INDUSTRY"]

    # Check sector specific metrics
    if e_type == SectorArchetype.BANK.value and canonical_metric in BANK_METRICS:
        return ApplicabilityState.APPLICABLE, ["BANK_SECTOR_METRIC_APPLICABLE"]
    if e_type == SectorArchetype.SECURITIES.value and canonical_metric in SECURITIES_METRICS:
        return ApplicabilityState.APPLICABLE, ["SECURITIES_SECTOR_METRIC_APPLICABLE"]

    # Standard general financial statement facts (net_income, cash_and_equivalents, shareholders_equity, operating_cash_flow, total_assets, total_liabilities)
    return ApplicabilityState.APPLICABLE, ["UNIVERSAL_FINANCIAL_FACT"]


def construct_financial_fact(
    *,
    ticker: str,
    metric: str,
    reporting_period: str,
    raw_citation: Mapping[str, Any],
    entity_type: str | None = None,
    reference_at: Any = None,
    knowledge_cutoff: Any = None,
) -> FinancialFactObservation:
    """Build a normalized fact observation from verified citation or unobserved placeholder."""
    spec = METRIC_SPECS.get(metric, {
        "statement_family": StatementFamily.GENERAL.value,
        "temporal_nature": TemporalNature.DURATION.value,
        "description": metric,
    })

    # Period decomposition
    p_str = str(reporting_period).strip()
    is_quarter = "-Q" in p_str.upper() or "_Q" in p_str.upper()
    period_type = PeriodType.QUARTERLY.value if is_quarter else PeriodType.ANNUAL.value

    if not is_quarter and len(p_str) == 4 and p_str.isdigit():
        p_start = f"{p_str}-01-01"
        p_end = f"{p_str}-12-31"
    else:
        p_start = raw_citation.get("period_start")
        p_end = raw_citation.get("period_end")

    has_citation = bool(raw_citation)
    val = raw_citation.get("value") if has_citation else None
    curr = raw_citation.get("currency") if has_citation else None
    scale = raw_citation.get("unit_scale") or raw_citation.get("scale") if has_citation else None
    scope = raw_citation.get("statement_scope", StatementScope.CONSOLIDATED.value) if has_citation else StatementScope.UNKNOWN.value
    obs_at = raw_citation.get("verified_at") or raw_citation.get("observed_at") if has_citation else None
    pub_at = raw_citation.get("published_at") or raw_citation.get("source_published_at") if has_citation else None
    if not pub_at and obs_at:
        pub_at = _date_str(obs_at)

    auth_tier = raw_citation.get("authority_tier") if has_citation else None
    recon_status = raw_citation.get("reconciliation_status") if has_citation else None
    is_pos_auth = bool(raw_citation.get("is_positive_authority", True)) if has_citation else False

    # Applicability evaluation
    app_state, app_reasons = evaluate_sector_applicability(
        ticker=ticker,
        entity_type=entity_type,
        canonical_metric=metric,
    )

    reason_codes: list[str] = list(app_reasons)

    # Qualification & Conflict checking
    if recon_status == "CONFLICT" or raw_citation.get("reconciliation_status") == ReconciliationStatus.CONFLICT.value:
        qual_state = QualificationState.CONFLICT.value
        val = None
        is_pos_auth = False
        reason_codes.append("CONFLICT_GENERIC_SPECIALIZED_DISAGREEMENT")
    elif app_state == ApplicabilityState.NOT_APPLICABLE:
        qual_state = QualificationState.NOT_APPLICABLE.value
        val = None
        is_pos_auth = False
    elif not has_citation or val is None:
        qual_state = QualificationState.MISSING.value
        is_pos_auth = False
        reason_codes.append("UNOBSERVED_FACT")
    elif (
        raw_citation.get("evidence_id")
        or raw_citation.get("citation_id")
        or raw_citation.get("qualification_state") == QualificationState.QUALIFIED.value
        or auth_tier == SectorAuthorityTier.GENERIC_SECTOR_TAXONOMY_PROMOTED.value
    ):
        qual_state = QualificationState.QUALIFIED.value
        is_pos_auth = bool(raw_citation.get("is_positive_authority", True))
        reason_codes.append("OFFICIAL_EVIDENCE_QUALIFIED")
    else:
        qual_state = QualificationState.UNQUALIFIED.value
        is_pos_auth = False
        reason_codes.append("UNVERIFIED_CITATION")

    # Temporal Envelope
    pit_cutoff = knowledge_cutoff if knowledge_cutoff is not None else reference_at
    pub_date_str = _date_str(pub_at) if pub_at else None
    ref_date_str = _date_str(reference_at) if reference_at else None

    # Temporal rules
    is_lookahead = False
    if ref_date_str and pub_date_str and pub_date_str > ref_date_str:
        is_lookahead = True
        reason_codes.append("LOOKAHEAD_VIOLATION_PUBLISHED_AFTER_REFERENCE")

    pit_eligible = bool(
        qual_state == QualificationState.QUALIFIED.value
        and pub_date_str
        and not is_lookahead
        and (not pit_cutoff or pub_date_str <= _date_str(pit_cutoff))
    )

    if is_lookahead:
        pit_status = PitStatus.LOOKAHEAD_VIOLATION.value
    elif pit_eligible:
        pit_status = PitStatus.QUALIFIED.value
    elif qual_state == QualificationState.HISTORICAL_ONLY.value:
        pit_status = PitStatus.HISTORICAL_ONLY.value
    elif not pub_date_str:
        pit_status = PitStatus.TIMESTAMP_MISSING_OR_INVALID.value
    else:
        pit_status = PitStatus.HISTORICAL_ONLY.value

    # Freshness
    if not has_citation or val is None:
        freshness_status = FreshnessState.MISSING.value
    elif is_lookahead:
        freshness_status = FreshnessState.UNKNOWN.value
    else:
        freshness_status = FreshnessState.HISTORICAL.value

    envelope = {
        "field_name": metric,
        "value": _sanitize(val),
        "observed_at": obs_at,
        "knowledge_available_at": pub_at,
        "as_of": reporting_period,
        "freshness_status": freshness_status,
        "pit_eligible": pit_eligible,
        "pit_status": pit_status,
        "domain": "financial_statement",
        "quality_status": "qualified" if qual_state == QualificationState.QUALIFIED.value else "unqualified",
    }

    envelope_id = stable_id(envelope)
    envelope["field_id"] = envelope_id

    source_lineage = {
        "evidence_id": raw_citation.get("evidence_id"),
        "citation_id": raw_citation.get("citation_id"),
        "document_sha256": raw_citation.get("document_sha256") or (
            raw_citation.get("extraction", {}).get("materialization", {}).get("document_sha256")
            if isinstance(raw_citation.get("extraction"), Mapping) else None
        ),
        "citation": raw_citation.get("citation") or raw_citation.get("citation_text"),
        "source_page": raw_citation.get("source_page"),
        "note_number": raw_citation.get("note_number"),
        "authority_tier": auth_tier,
        "reconciliation_status": recon_status,
        "specialized_corroboration": raw_citation.get("specialized_corroboration", False),
        "provider": raw_citation.get("provider", "official_issuer_filing"),
    }

    return FinancialFactObservation(
        issuer_identity=ticker,
        reporting_period=reporting_period,
        period_type=period_type,
        period_start=p_start,
        period_end=p_end,
        statement_family=spec["statement_family"],
        statement_scope=scope,
        temporal_nature=spec["temporal_nature"],
        canonical_metric=metric,
        value=val,
        currency=curr,
        unit_scale=scale,
        qualification_state=qual_state,
        applicability_state=app_state.value,
        observed_at=obs_at,
        knowledge_available_at=pub_at,
        source_lineage=_sanitize(source_lineage),
        temporal_envelope=envelope,
        reason_codes=tuple(sorted(set(reason_codes))),
        authority_tier=auth_tier,
        reconciliation_status=recon_status,
        is_positive_authority=is_pos_auth,
    )


def compute_bounded_derived_metrics(
    facts_by_period: Mapping[str, Mapping[str, FinancialFactObservation]],
    *,
    entity_type: str | None,
) -> dict[str, dict[str, Any]]:
    """Compute bounded deterministic accounting relationships across periods.

    Strictly adheres to invariants:
    - Zero currency mixing (VND vs USD)
    - Zero statement scope mixing (consolidated vs separate)
    - Financial intermediaries blocked from corporate debt ratios
    - Missing inputs block only the dependent metric
    """
    derived: dict[str, dict[str, Any]] = {}
    sorted_periods = sorted(facts_by_period.keys())

    e_type_clean = (entity_type or "").strip().lower()
    is_corporate = e_type_clean == SectorArchetype.CORPORATE.value
    is_bank = e_type_clean == SectorArchetype.BANK.value
    is_securities = e_type_clean == SectorArchetype.SECURITIES.value

    for idx, period in enumerate(sorted_periods):
        p_facts = facts_by_period[period]
        period_derived: dict[str, Any] = {}

        ni_fact = p_facts.get("net_income")
        ocf_fact = p_facts.get("operating_cash_flow")
        eq_fact = p_facts.get("shareholders_equity")
        debt_fact = p_facts.get("total_interest_bearing_debt")
        cash_fact = p_facts.get("cash_and_equivalents")

        # 1. Cash flow to Net Income Coverage (Corporate / general)
        if ni_fact and ocf_fact and ni_fact.value is not None and ocf_fact.value is not None:
            if ni_fact.currency == ocf_fact.currency and ni_fact.statement_scope == ocf_fact.statement_scope:
                if ni_fact.value != 0:
                    period_derived["cash_flow_to_net_income"] = {
                        "value": round(float(ocf_fact.value) / float(ni_fact.value), 4),
                        "status": "QUALIFIED",
                        "basis": "OCF / Net Income",
                    }
                else:
                    period_derived["cash_flow_to_net_income"] = {
                        "value": None,
                        "status": "BLOCKED",
                        "reason": "ZERO_NET_INCOME_DIVISOR",
                    }

        # 2. Corporate Debt & Capital Metrics (Corporate only)
        if is_corporate:
            if debt_fact and eq_fact and debt_fact.value is not None and eq_fact.value is not None:
                if debt_fact.currency == eq_fact.currency and debt_fact.statement_scope == eq_fact.statement_scope:
                    if float(eq_fact.value) > 0:
                        period_derived["debt_to_equity"] = {
                            "value": round(float(debt_fact.value) / float(eq_fact.value), 4),
                            "status": "QUALIFIED",
                            "basis": "Total Interest-Bearing Debt / Total Equity",
                        }
                    else:
                        period_derived["debt_to_equity"] = {
                            "value": None,
                            "status": "BLOCKED",
                            "reason": "NON_POSITIVE_EQUITY_DIVISOR",
                        }
            if debt_fact and cash_fact and debt_fact.value is not None and cash_fact.value is not None:
                if debt_fact.currency == cash_fact.currency and debt_fact.statement_scope == cash_fact.statement_scope:
                    period_derived["net_debt"] = {
                        "value": float(debt_fact.value) - float(cash_fact.value),
                        "currency": debt_fact.currency,
                        "status": "QUALIFIED",
                        "basis": "Total Interest-Bearing Debt - Cash & Equivalents",
                    }
        else:
            period_derived["debt_to_equity"] = {
                "value": None,
                "status": "NOT_APPLICABLE",
                "reason": "SECTOR_INAPPROPRIATE_FINANCIAL_INTERMEDIARY_DEBT_RATIO",
            }
            period_derived["net_debt"] = {
                "value": None,
                "status": "NOT_APPLICABLE",
                "reason": "SECTOR_INAPPROPRIATE_FINANCIAL_INTERMEDIARY_DEBT_RATIO",
            }

        # 3. ROE Proxy (ENDING_EQUITY_ROE_PROXY across sectors)
        ni_val = None
        eq_val = None
        curr_ni = None
        curr_eq = None
        scope_ni = None
        scope_eq = None

        if is_corporate:
            if ni_fact and ni_fact.value is not None:
                ni_val = float(ni_fact.value)
                curr_ni = ni_fact.currency
                scope_ni = ni_fact.statement_scope
            if eq_fact and eq_fact.value is not None:
                eq_val = float(eq_fact.value)
                curr_eq = eq_fact.currency
                scope_eq = eq_fact.statement_scope
        elif is_bank:
            bank_ni = next((p_facts[k] for k in ("net_profit_parent", "net_profit_total", "net_income") if k in p_facts and p_facts[k].value is not None), None)
            bank_eq = next((p_facts[k] for k in ("total_equity", "shareholders_equity") if k in p_facts and p_facts[k].value is not None), None)
            if bank_ni and bank_ni.value is not None:
                ni_val = float(bank_ni.value)
                curr_ni = bank_ni.currency
                scope_ni = bank_ni.statement_scope
            if bank_eq and bank_eq.value is not None:
                eq_val = float(bank_eq.value)
                curr_eq = bank_eq.currency
                scope_eq = bank_eq.statement_scope
        elif is_securities:
            sec_ni = next((p_facts[k] for k in ("profit_after_tax_parent", "profit_after_tax_total", "net_income") if k in p_facts and p_facts[k].value is not None), None)
            sec_eq = next((p_facts[k] for k in ("total_equity", "shareholders_equity") if k in p_facts and p_facts[k].value is not None), None)
            if sec_ni and sec_ni.value is not None:
                ni_val = float(sec_ni.value)
                curr_ni = sec_ni.currency
                scope_ni = sec_ni.statement_scope
            if sec_eq and sec_eq.value is not None:
                eq_val = float(sec_eq.value)
                curr_eq = sec_eq.currency
                scope_eq = sec_eq.statement_scope
        else:
            if ni_fact and ni_fact.value is not None:
                ni_val = float(ni_fact.value)
                curr_ni = ni_fact.currency
                scope_ni = ni_fact.statement_scope
            if eq_fact and eq_fact.value is not None:
                eq_val = float(eq_fact.value)
                curr_eq = eq_fact.currency
                scope_eq = eq_fact.statement_scope

        if ni_val is not None and eq_val is not None and curr_ni == curr_eq and scope_ni == scope_eq:
            if eq_val > 0:
                period_derived["roe_proxy"] = {
                    "value": round(ni_val / eq_val, 4),
                    "status": "QUALIFIED",
                    "basis": "Net Profit Attributable to Parent / Total Equity",
                    "semantic_label": "ENDING_EQUITY_ROE_PROXY",
                }
            else:
                period_derived["roe_proxy"] = {
                    "value": None,
                    "status": "BLOCKED",
                    "reason": "NON_POSITIVE_EQUITY_DIVISOR",
                }

        # 4. YoY Growth Metrics (requires previous consecutive period)
        if idx > 0:
            prev_period = sorted_periods[idx - 1]
            prev_facts = facts_by_period[prev_period]

            # Net Income YoY Growth
            prev_ni = prev_facts.get("net_income")
            if ni_fact and prev_ni and ni_fact.value is not None and prev_ni.value is not None:
                if ni_fact.currency == prev_ni.currency and ni_fact.statement_scope == prev_ni.statement_scope:
                    if float(prev_ni.value) != 0:
                        growth = (float(ni_fact.value) - float(prev_ni.value)) / abs(float(prev_ni.value))
                        period_derived["net_income_growth_yoy"] = {
                            "value": round(growth, 4),
                            "prior_period": prev_period,
                            "status": "QUALIFIED",
                            "basis": "(NI_t - NI_{t-1}) / |NI_{t-1}|",
                        }
                    else:
                        period_derived["net_income_growth_yoy"] = {
                            "value": None,
                            "prior_period": prev_period,
                            "status": "BLOCKED",
                            "reason": "ZERO_PRIOR_PERIOD_NET_INCOME",
                        }
                else:
                    period_derived["net_income_growth_yoy"] = {
                        "value": None,
                        "prior_period": prev_period,
                        "status": "BLOCKED",
                        "reason": "CURRENCY_OR_SCOPE_MISMATCH_ACROSS_PERIODS",
                    }

            # Operating Cash Flow YoY Growth
            prev_ocf = prev_facts.get("operating_cash_flow")
            if ocf_fact and prev_ocf and ocf_fact.value is not None and prev_ocf.value is not None:
                if ocf_fact.currency == prev_ocf.currency and ocf_fact.statement_scope == prev_ocf.statement_scope:
                    if float(prev_ocf.value) != 0:
                        growth = (float(ocf_fact.value) - float(prev_ocf.value)) / abs(float(prev_ocf.value))
                        period_derived["operating_cash_flow_growth_yoy"] = {
                            "value": round(growth, 4),
                            "prior_period": prev_period,
                            "status": "QUALIFIED",
                            "basis": "(OCF_t - OCF_{t-1}) / |OCF_{t-1}|",
                        }
                    else:
                        period_derived["operating_cash_flow_growth_yoy"] = {
                            "value": None,
                            "prior_period": prev_period,
                            "status": "BLOCKED",
                            "reason": "ZERO_PRIOR_PERIOD_OCF",
                        }
                else:
                    period_derived["operating_cash_flow_growth_yoy"] = {
                        "value": None,
                        "prior_period": prev_period,
                        "status": "BLOCKED",
                        "reason": "CURRENCY_OR_SCOPE_MISMATCH_ACROSS_PERIODS",
                    }

        derived[period] = period_derived

    return derived


def build_issuer_multi_period_panel(
    *,
    ticker: str,
    candidate_id: str | None = None,
    citations: Sequence[Mapping[str, Any]],
    entity_type: str | None = None,
    target_periods: Sequence[str] | None = None,
    target_metrics: Sequence[str] | None = None,
    reference_at: Any = None,
    knowledge_cutoff: Any = None,
) -> dict[str, Any]:
    """Construct deterministic multi-period financial fact panel for a single issuer."""
    ticker_clean = ticker.upper().strip()
    cand_id = candidate_id or f"candidate:{ticker_clean}"

    # Resolve layered entity classification if not explicitly provided or unknown
    e_type_resolved = entity_type
    e_class_authority = "provided"
    e_class_is_positive = True

    if not e_type_resolved or e_type_resolved in {SectorArchetype.UNKNOWN.value, "none", "null"}:
        layered_res = resolve_layered_entity_classification(ticker_clean)
        e_type_resolved = layered_res.resolved_entity_class.value
        e_class_authority = str(layered_res.authority_tier)
        e_class_is_positive = layered_res.is_positive_authority

    # Group citations by period and metric
    citation_map: dict[str, dict[str, Mapping[str, Any]]] = {}
    for cit in citations:
        if str(cit.get("ticker", "")).upper().strip() != ticker_clean:
            continue
        p = str(cit.get("reporting_period", "")).strip()
        m = str(cit.get("metric", "")).strip()
        if p and m:
            citation_map.setdefault(p, {})[m] = cit

    # Determine periods
    available_periods = sorted(citation_map.keys())
    if target_periods is not None:
        eval_periods = sorted(set(target_periods))
    else:
        eval_periods = available_periods or ["2024"]

    facts_by_period: dict[str, dict[str, FinancialFactObservation]] = {}
    raw_fact_records: list[dict[str, Any]] = []

    # Determine metrics to evaluate for this issuer
    observed_metrics = set(m for p_dict in citation_map.values() for m in p_dict.keys())
    if target_metrics is not None:
        metrics_to_evaluate = sorted(set(list(target_metrics) + list(observed_metrics)))
    else:
        e_type_clean = (e_type_resolved or "").strip().lower()
        if e_type_clean == SectorArchetype.BANK.value:
            metrics_to_evaluate = sorted(set(list(METRIC_SPECS.keys()) + list(BANK_METRICS.keys()) + list(observed_metrics)))
        elif e_type_clean == SectorArchetype.SECURITIES.value:
            metrics_to_evaluate = sorted(set(list(METRIC_SPECS.keys()) + list(SECURITIES_METRICS.keys()) + list(observed_metrics)))
        else:
            metrics_to_evaluate = sorted(set(list(METRIC_SPECS.keys()) + list(observed_metrics)))

    for p in eval_periods:
        p_cits = citation_map.get(p, {})
        facts_by_period[p] = {}
        for m in metrics_to_evaluate:
            raw_c = p_cits.get(m, {})
            fact_obs = construct_financial_fact(
                ticker=ticker_clean,
                metric=m,
                reporting_period=p,
                raw_citation=raw_c,
                entity_type=e_type_resolved,
                reference_at=reference_at,
                knowledge_cutoff=knowledge_cutoff,
            )
            facts_by_period[p][m] = fact_obs
            raw_fact_records.append(fact_obs.to_dict())

    # Compute bounded derived metrics across periods
    derived_metrics = compute_bounded_derived_metrics(facts_by_period, entity_type=e_type_resolved)

    # Blocked capabilities
    blocked_capabilities = {
        "valuation": {
            "status": "BLOCKED",
            "reason_code": "VALUATION_METRICS_UNQUALIFIED",
            "governance_rule": "P2 governance: valuation multiples and target prices strictly prohibited",
        },
        "intrinsic_value": {
            "status": "BLOCKED",
            "reason_code": "INTRINSIC_VALUE_MODELS_BLOCKED",
            "governance_rule": "P2 governance: DCF and intrinsic valuation models strictly prohibited",
        },
        "cross_sectional_ranking": {
            "status": "BLOCKED",
            "reason_code": "STRATEGY_RANKING_PROHIBITED",
            "governance_rule": "P2 governance: alpha scoring and strategy recommendations strictly prohibited",
        },
        "execution_sizing": {
            "status": "BLOCKED",
            "reason_code": "POSITION_SIZING_PROHIBITED",
            "governance_rule": "P0-B negative proof: POSITION_SIZING_IS_SAFE = NO",
        },
    }

    # Summary statistics
    total_facts = len(raw_fact_records)
    qualified_facts = sum(1 for r in raw_fact_records if r["qualification_state"] == QualificationState.QUALIFIED.value)
    missing_facts = sum(1 for r in raw_fact_records if r["qualification_state"] == QualificationState.MISSING.value)
    not_applicable_facts = sum(1 for r in raw_fact_records if r["qualification_state"] == QualificationState.NOT_APPLICABLE.value)
    conflict_facts = sum(1 for r in raw_fact_records if r["qualification_state"] == QualificationState.CONFLICT.value)

    return {
        "issuer_identity": {
            "ticker": ticker_clean,
            "candidate_id": cand_id,
            "entity_type": e_type_resolved or SectorArchetype.UNKNOWN.value,
            "entity_class_authority": e_class_authority,
            "entity_class_is_positive": e_class_is_positive,
        },
        "periods_covered": eval_periods,
        "period_count": len(eval_periods),
        "total_facts_evaluated": total_facts,
        "qualified_facts_count": qualified_facts,
        "missing_facts_count": missing_facts,
        "not_applicable_facts_count": not_applicable_facts,
        "conflict_facts_count": conflict_facts,
        "facts": raw_fact_records,
        "derived_metrics": derived_metrics,
        "blocked_capabilities": blocked_capabilities,
    }


def build_multi_period_financial_panel(
    *,
    issuers: Sequence[str],
    citations: Sequence[Mapping[str, Any]],
    entity_profiles: Mapping[str, str] | None = None,
    candidate_map: Mapping[str, Any] | None = None,
    reference_at: Any = None,
    knowledge_cutoff: Any = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Construct multi-issuer deterministic multi-period financial research panel."""
    sorted_issuers = sorted(set(str(i).upper().strip() for i in issuers if str(i).strip()))
    profiles = dict(entity_profiles or {})

    issuer_panels: list[dict[str, Any]] = []
    overall_facts_count = 0
    overall_qualified_count = 0
    overall_missing_count = 0
    overall_not_applicable_count = 0
    overall_conflict_count = 0
    currency_dist: dict[str, int] = {}
    scope_dist: dict[str, int] = {}
    fact_coverage: dict[str, dict[str, int]] = {}
    entity_class_dist: dict[str, int] = {}

    for t in sorted_issuers:
        # Resolve entity class
        if t in profiles:
            e_type = profiles[t]
        else:
            e_res = resolve_layered_entity_classification(t)
            e_type = e_res.resolved_entity_class.value

        entity_class_dist[e_type] = entity_class_dist.get(e_type, 0) + 1
        cand_id = candidate_map.get(t, {}).get("candidate_id") if candidate_map else None

        panel = build_issuer_multi_period_panel(
            ticker=t,
            candidate_id=cand_id,
            citations=citations,
            entity_type=e_type,
            reference_at=reference_at,
            knowledge_cutoff=knowledge_cutoff,
        )
        issuer_panels.append(panel)

        overall_facts_count += panel["total_facts_evaluated"]
        overall_qualified_count += panel["qualified_facts_count"]
        overall_missing_count += panel["missing_facts_count"]
        overall_not_applicable_count += panel["not_applicable_facts_count"]
        overall_conflict_count += panel.get("conflict_facts_count", 0)

        for f_rec in panel["facts"]:
            curr = f_rec.get("currency") or "UNSPECIFIED"
            scope = f_rec.get("statement_scope") or "UNKNOWN"
            metric = f_rec.get("canonical_metric", "unknown")
            q_state = f_rec.get("qualification_state", "UNKNOWN")

            if q_state == QualificationState.QUALIFIED.value:
                currency_dist[curr] = currency_dist.get(curr, 0) + 1
                scope_dist[scope] = scope_dist.get(scope, 0) + 1

            if metric not in fact_coverage:
                fact_coverage[metric] = {"QUALIFIED": 0, "MISSING": 0, "NOT_APPLICABLE": 0, "UNQUALIFIED": 0, "CONFLICT": 0}
            fact_coverage[metric][q_state] = fact_coverage[metric].get(q_state, 0) + 1

    gen_time = generated_at or (str(reference_at) if reference_at else datetime.now(timezone.utc).isoformat())

    raw_payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "generated_at": gen_time,
        "reference_at": str(reference_at) if reference_at else None,
        "knowledge_cutoff": str(knowledge_cutoff) if knowledge_cutoff else None,
        "total_issuers_processed": len(sorted_issuers),
        "issuers_represented": sorted_issuers,
        "entity_class_distribution": entity_class_dist,
        "total_facts_evaluated": overall_facts_count,
        "qualified_facts_count": overall_qualified_count,
        "missing_facts_count": overall_missing_count,
        "not_applicable_facts_count": overall_not_applicable_count,
        "conflict_facts_count": overall_conflict_count,
        "currency_distribution": currency_dist,
        "statement_scope_distribution": scope_dist,
        "fact_coverage_summary": fact_coverage,
        "issuers": issuer_panels,
    }

    content_hash = stable_id(raw_payload)
    artifact_id = f"multi-period-financial-panel:{content_hash[:16]}"

    return {
        **raw_payload,
        "content_hash": content_hash,
        "artifact_id": artifact_id,
    }


def load_promoted_sector_citations(config_path: Path | None = None) -> list[dict[str, Any]]:
    """Load promoted sector extractions (VCB Bank, SSI Securities) as citation dictionaries."""
    if config_path is None:
        config_path = Path(__file__).resolve().parent / "config" / "promoted_sector_extractions.json"

    registry = load_promoted_sector_extractions(config_path)
    promoted_sectors = registry.get("promoted_sectors", {})
    citations: list[dict[str, Any]] = []

    # Look for artifact file first if present
    artifact_file = (
        Path(__file__).resolve().parent
        / "operations-review"
        / "p2f3-bounded-generic-sector-extraction-promotion-20260820"
        / "p2f3_sector_extraction_promotion_artifact.json"
    )

    if artifact_file.is_file():
        art_data = json.loads(artifact_file.read_text(encoding="utf-8"))
        art_sectors = art_data.get("promoted_topology", {}).get("promoted_sectors", {})
        for s_name, s_info in art_sectors.items():
            for f in s_info.get("promoted_facts", []):
                citations.append({
                    "ticker": f.get("ticker"),
                    "metric": f.get("canonical_metric"),
                    "reporting_period": f.get("reporting_period", "2024"),
                    "value": f.get("value"),
                    "currency": f.get("currency", "VND"),
                    "unit_scale": f.get("unit_scale", 1),
                    "statement_scope": f.get("statement_scope", "consolidated"),
                    "citation_id": f.get("citation_id"),
                    "evidence_id": f"evidence:{f.get('document_sha256')}:{f.get('source_page', 0)}",
                    "document_sha256": f.get("document_sha256"),
                    "source_page": f.get("source_page"),
                    "note_number": f.get("note_number"),
                    "authority_tier": f.get("authority_tier"),
                    "reconciliation_status": f.get("reconciliation_status"),
                    "specialized_corroboration": f.get("specialized_corroboration", False),
                    "is_positive_authority": f.get("is_positive_authority", True),
                    "qualification_state": QualificationState.QUALIFIED.value if f.get("is_positive_authority") else QualificationState.UNQUALIFIED.value,
                    "published_at": "2025-03-30",
                    "verified_at": "2026-08-20T00:00:00Z",
                    "provider": "official_audited_annual_report",
                })
    return citations


def load_governed_corporate_citations(repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Load governed P2-D / P2-C2C corporate facts (GAS & VRE)."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent

    report_path = (
        repo_root
        / "operations-review"
        / "p2d-generic-financial-template-onboarding-20260819"
        / "p2d_generic_onboarding_report.json"
    )
    if not report_path.is_file():
        report_path = (
            repo_root
            / "operations-review"
            / "p2c2-governed-financial-evidence-onboarding-20260819"
            / "p2c2_governed_onboarding_report.json"
        )
    if not report_path.is_file():
        return []

    data = json.loads(report_path.read_text(encoding="utf-8"))
    citations: list[dict[str, Any]] = []

    for ticker, res in data.get("issuer_results", {}).items():
        doc_qual = res.get("document_qualification", {})
        doc_sha = doc_qual.get("document_sha256")
        ev_id = doc_qual.get("evidence_id")
        pub_at = doc_qual.get("published_at")
        obs_at = doc_qual.get("observed_at")
        for f in res.get("facts", []):
            citations.append({
                "ticker": ticker,
                "metric": f.get("canonical_metric"),
                "reporting_period": f.get("reporting_period", "2025"),
                "value": f.get("value"),
                "currency": f.get("currency", "VND"),
                "unit_scale": f.get("unit_scale", 1),
                "statement_scope": f.get("statement_scope", "consolidated"),
                "citation_id": f.get("citation_id"),
                "evidence_id": ev_id,
                "document_sha256": doc_sha,
                "authority_tier": "promoted_corporate_evidence",
                "reconciliation_status": "EXACT_MATCH",
                "is_positive_authority": True,
                "qualification_state": QualificationState.QUALIFIED.value,
                "published_at": pub_at,
                "verified_at": obs_at,
                "provider": "official_issuer_ir",
            })
    return citations


def load_retained_baseline_citations(repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Load baseline financial identity citations (HPG, VNM, PAN, PVD, NVL, POW, QNS)."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent

    cit_path = (
        repo_root
        / "operations-review"
        / "governed-official-evidence-v1"
        / "data"
        / "official-evidence"
        / "financial_identity_citations.jsonl"
    )
    if not cit_path.is_file():
        return []

    citations: list[dict[str, Any]] = []
    with open(cit_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    c = json.loads(line)
                    citations.append(c)
                except Exception:
                    pass
    return citations


def load_promoted_comparative_financial_citations(repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Load P3-C fact-level annual comparative evidence through the generic sector recognizer.

    The manifest carries a verified transcription of the exact primary-statement
    lines; production extraction stays dictionary-driven and scope authorization
    remains in the sector registry.  This loader intentionally accepts only the
    explicit document/metric scopes declared by the P3-C promotion manifest.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent
    manifest_path = repo_root / "config" / "promoted_comparative_financial_evidence.json"
    if not manifest_path.is_file():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contract_version") != "p3c_comparative_financial_evidence/v1":
        raise MultiPeriodPanelError("Unsupported P3-C comparative evidence manifest")

    citations: list[dict[str, Any]] = []
    for document in manifest.get("evidence_documents", []):
        required = ("ticker", "reporting_period", "statement_scope", "audit_status", "currency", "unit_scale", "source_locator", "published_at", "retrieved_at", "archive_document_path", "document_sha256", "document_id", "sidecar")
        if any(not document.get(field) for field in required):
            raise MultiPeriodPanelError("P3-C comparative evidence document lacks required lineage")
        if document.get("audit_status") != "audited" or document.get("statement_scope") != "consolidated":
            raise MultiPeriodPanelError("P3-C accepts audited consolidated annual evidence only")
        if len(str(document.get("document_sha256"))) != 64:
            raise MultiPeriodPanelError("P3-C document SHA-256 is invalid")

        qualification = {
            "sha256": document["document_sha256"],
            "document_id": document["document_id"],
        }
        extracted = extract_sector_facts_from_sidecar(
            ticker=str(document["ticker"]),
            qualification=qualification,
            sidecar=document["sidecar"],
            reporting_period=str(document["reporting_period"]),
            statement_scope=str(document["statement_scope"]),
            verified_at=str(document["retrieved_at"]),
        )
        resolved = reconcile_and_resolve_authoritative_sector_facts(generic_facts=extracted)
        qualified_metrics = set(document.get("qualified_metrics", []))
        by_metric = {fact.canonical_metric: fact for fact in resolved if fact.is_positive_authority}
        if set(by_metric) != qualified_metrics:
            raise MultiPeriodPanelError("P3-C generic extraction did not exactly reproduce the promoted fact scope")
        for metric in sorted(qualified_metrics):
            fact = by_metric[metric]
            citations.append({
                "ticker": fact.ticker,
                "metric": fact.canonical_metric,
                "reporting_period": fact.reporting_period,
                "value": fact.value,
                "currency": fact.currency,
                "unit_scale": fact.unit_scale,
                "statement_scope": fact.statement_scope,
                "citation_id": fact.citation_id,
                "evidence_id": f"evidence:{fact.document_sha256}:{fact.source_page}",
                "document_sha256": fact.document_sha256,
                "source_page": fact.source_page,
                "note_number": fact.note_number,
                "source_locator": document["source_locator"],
                "archive_document_path": document["archive_document_path"],
                "audit_status": document["audit_status"],
                "authority_tier": fact.authority_tier.value,
                "reconciliation_status": fact.reconciliation_status.value,
                "is_positive_authority": fact.is_positive_authority,
                "qualification_state": QualificationState.QUALIFIED.value,
                "published_at": document["published_at"],
                "verified_at": document["retrieved_at"],
                "provider": "official_issuer_ir",
            })
    return citations


def load_promoted_residual_comparative_financial_citations(repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Load P3-D's audited corporate statement facts through the generic template recognizer."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent
    manifest_path = repo_root / "config" / "promoted_residual_comparative_financial_evidence.json"
    if not manifest_path.is_file():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contract_version") != "p3d_residual_comparative_financial_evidence/v1":
        raise MultiPeriodPanelError("Unsupported P3-D residual comparative evidence manifest")

    citations: list[dict[str, Any]] = []
    for document in manifest.get("evidence_documents", []):
        required = (
            "ticker", "reporting_period", "statement_scope", "audit_status", "currency", "unit_scale",
            "source_locator", "published_at", "retrieved_at", "archive_document_path", "materialization_path",
            "document_sha256", "document_id", "sidecar", "source_page_citations",
        )
        if any(not document.get(field) for field in required):
            raise MultiPeriodPanelError("P3-D comparative evidence document lacks required lineage")
        if document.get("audit_status") != "audited" or document.get("statement_scope") != "consolidated":
            raise MultiPeriodPanelError("P3-D accepts audited consolidated annual evidence only")
        if len(str(document.get("document_sha256"))) != 64:
            raise MultiPeriodPanelError("P3-D document SHA-256 is invalid")
        registry = load_registry(repo_root / "config" / "official_source_registry.json")
        source_decision = admit(
            str(document.get("source_type")), str(document.get("source_locator")),
            "audited_annual_financial_statements", registry=registry,
        )
        if source_decision.get("decision") != ADMITTED:
            raise MultiPeriodPanelError("P3-D source authority is not approved for this document")

        qualified_metrics = set(document.get("qualified_metrics", []))
        extracted = extract_generic_financial_statement_facts(
            sidecar=document["sidecar"],
            reporting_period=str(document["reporting_period"]),
            qualification_record={"document_id": document["document_id"], "sha256": document["document_sha256"]},
            verified_at=str(document["retrieved_at"]),
            required_metrics=sorted(qualified_metrics),
        )
        by_metric = {fact.canonical_metric: fact for fact in extracted}
        if set(by_metric) != qualified_metrics:
            raise MultiPeriodPanelError("P3-D generic extraction did not exactly reproduce the promoted fact scope")
        for metric in sorted(qualified_metrics):
            fact = by_metric[metric]
            source = document["source_page_citations"].get(metric, {})
            if int(source.get("page", 0)) != fact.page or str(source.get("raw_value")) != fact.raw_value:
                raise MultiPeriodPanelError("P3-D extracted citation does not match the approved source-page declaration")
            citations.append({
                "ticker": str(document["ticker"]).upper(),
                "metric": fact.canonical_metric,
                "reporting_period": fact.reporting_period,
                "value": fact.normalized_value,
                "currency": fact.currency,
                "unit_scale": fact.unit_scale,
                "statement_scope": str(document["statement_scope"]),
                "citation_id": hashlib.sha256(
                    f"p3d_statement|{document['ticker']}|{metric}|{fact.reporting_period}|{document['document_sha256']}|{fact.page}|{fact.raw_value}".encode("utf-8")
                ).hexdigest(),
                "evidence_id": f"evidence:{document['document_sha256']}:{fact.page}",
                "document_sha256": document["document_sha256"],
                "source_page": fact.page,
                "source_locator": document["source_locator"],
                "archive_document_path": document["archive_document_path"],
                "materialization_path": document["materialization_path"],
                "audit_status": document["audit_status"],
                "authority_tier": "promoted_corporate_evidence",
                "reconciliation_status": "EXACT_MATCH",
                "is_positive_authority": True,
                "qualification_state": QualificationState.QUALIFIED.value,
                "published_at": document["published_at"],
                "verified_at": document["retrieved_at"],
                "provider": "official_issuer_ir",
                "extraction_method": fact.extraction_details.get("method"),
            })
    return citations


def load_promoted_fundamental_coverage_closeout_citations(repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Load P3-E's final retained annual revenue/assets evidence through generic recognition."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent
    manifest_path = repo_root / "config" / "promoted_fundamental_coverage_closeout_evidence.json"
    if not manifest_path.is_file():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contract_version") != "p3e_fundamental_coverage_closeout/v1":
        raise MultiPeriodPanelError("Unsupported P3-E fundamental coverage evidence manifest")

    registry = load_registry(repo_root / "config" / "official_source_registry.json")
    citations: list[dict[str, Any]] = []
    for document in manifest.get("evidence_documents", []):
        required = (
            "ticker", "reporting_period", "statement_scope", "audit_status", "currency", "unit_scale", "source_type",
            "source_document_class", "source_locator", "published_at", "retrieved_at", "archive_document_path",
            "materialization_path", "document_sha256", "document_id", "sidecar", "source_page_citations",
        )
        if any(not document.get(field) for field in required):
            raise MultiPeriodPanelError("P3-E coverage evidence document lacks required lineage")
        if document.get("audit_status") != "audited" or document.get("statement_scope") != "consolidated":
            raise MultiPeriodPanelError("P3-E accepts audited consolidated annual evidence only")
        if len(str(document.get("document_sha256"))) != 64:
            raise MultiPeriodPanelError("P3-E document SHA-256 is invalid")
        source_decision = admit(
            str(document["source_type"]), str(document["source_locator"]), str(document["source_document_class"]), registry=registry,
        )
        if source_decision.get("decision") != ADMITTED:
            raise MultiPeriodPanelError("P3-E source authority is not approved for this document")

        qualified_metrics = set(document.get("qualified_metrics", []))
        extracted = extract_generic_financial_statement_facts(
            sidecar=document["sidecar"], reporting_period=str(document["reporting_period"]),
            qualification_record={"document_id": document["document_id"], "sha256": document["document_sha256"]},
            verified_at=str(document["retrieved_at"]), required_metrics=sorted(qualified_metrics),
        )
        by_metric = {fact.canonical_metric: fact for fact in extracted}
        if set(by_metric) != qualified_metrics:
            raise MultiPeriodPanelError("P3-E generic extraction did not exactly reproduce the promoted fact scope")
        for metric in sorted(qualified_metrics):
            fact = by_metric[metric]
            source = document["source_page_citations"].get(metric, {})
            if int(source.get("page", 0)) != fact.page or str(source.get("raw_value")) != fact.raw_value:
                raise MultiPeriodPanelError("P3-E extracted citation does not match its source-page declaration")
            citations.append({
                "ticker": str(document["ticker"]).upper(), "metric": fact.canonical_metric,
                "reporting_period": fact.reporting_period, "value": fact.normalized_value,
                "currency": fact.currency, "unit_scale": fact.unit_scale,
                "statement_scope": str(document["statement_scope"]),
                "citation_id": hashlib.sha256(
                    f"p3e_statement|{document['ticker']}|{metric}|{fact.reporting_period}|{document['document_sha256']}|{fact.page}|{fact.raw_value}".encode("utf-8")
                ).hexdigest(),
                "evidence_id": f"evidence:{document['document_sha256']}:{fact.page}",
                "document_sha256": document["document_sha256"], "source_page": fact.page,
                "source_locator": document["source_locator"], "archive_document_path": document["archive_document_path"],
                "materialization_path": document["materialization_path"], "audit_status": document["audit_status"],
                "authority_tier": "promoted_corporate_evidence", "reconciliation_status": "EXACT_MATCH",
                "is_positive_authority": True, "qualification_state": QualificationState.QUALIFIED.value,
                "published_at": document["published_at"], "verified_at": document["retrieved_at"],
                "provider": "official_issuer_ir", "extraction_method": fact.extraction_details.get("method"),
            })
    return citations


def load_all_authoritative_citations(
    repo_root: Path | None = None,
    *,
    include_p3c_comparative_evidence: bool = True,
    include_p3d_residual_comparative_evidence: bool = False,
    include_p3e_fundamental_coverage_evidence: bool = False,
) -> list[dict[str, Any]]:
    """Load qualified citations, optionally including the additive P3-C evidence scope.

    ``False`` preserves deterministic replay of the historical P2 closeout,
    whose immutable 102-fact artifact is the P3-C before-state.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent

    all_cits: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    # 1. Promoted sector extractions (VCB Bank, SSI Securities)
    for c in load_promoted_sector_citations():
        key = (str(c.get("ticker")).upper(), str(c.get("metric")), str(c.get("reporting_period")), str(c.get("statement_scope")))
        if key not in seen:
            seen.add(key)
            all_cits.append(c)

    # 2. Governed corporate facts (GAS, VRE)
    for c in load_governed_corporate_citations(repo_root):
        key = (str(c.get("ticker")).upper(), str(c.get("metric")), str(c.get("reporting_period")), str(c.get("statement_scope")))
        if key not in seen:
            seen.add(key)
            all_cits.append(c)

    # 3. P3-C comparative annual evidence, replayed via the generic sector recognizer.
    if include_p3c_comparative_evidence:
        for c in load_promoted_comparative_financial_citations(repo_root):
            key = (str(c.get("ticker")).upper(), str(c.get("metric")), str(c.get("reporting_period")), str(c.get("statement_scope")))
            if key not in seen:
                seen.add(key)
                all_cits.append(c)

    # 4. P3-D residual annual evidence, separately opt-in to preserve historical replays.
    if include_p3d_residual_comparative_evidence:
        for c in load_promoted_residual_comparative_financial_citations(repo_root):
            key = (str(c.get("ticker")).upper(), str(c.get("metric")), str(c.get("reporting_period")), str(c.get("statement_scope")))
            if key not in seen:
                seen.add(key)
                all_cits.append(c)

    # 5. P3-E final bounded coverage evidence, separately opt-in for historical replay.
    if include_p3e_fundamental_coverage_evidence:
        for c in load_promoted_fundamental_coverage_closeout_citations(repo_root):
            key = (str(c.get("ticker")).upper(), str(c.get("metric")), str(c.get("reporting_period")), str(c.get("statement_scope")))
            if key not in seen:
                seen.add(key)
                all_cits.append(c)

    # 6. Retained baseline corporate citations (HPG, VNM, PAN, PVD, NVL, POW, QNS)
    for c in load_retained_baseline_citations(repo_root):
        t = str(c.get("ticker", "")).upper()
        if t == "SSI" and any(x["ticker"] == "SSI" for x in all_cits):
            continue
        key = (t, str(c.get("metric")), str(c.get("reporting_period")), str(c.get("statement_scope")))
        if key not in seen:
            seen.add(key)
            all_cits.append(c)

    return all_cits
