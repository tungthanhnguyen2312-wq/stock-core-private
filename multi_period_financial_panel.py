"""Phase 2 / P2-A: Multi-Period Financial Fact Panel & Sector Applicability Contract.

This module provides a deterministic, multi-period financial fact research panel
from qualified official financial evidence:
1. Preserves complete dimensional provenance:
   - issuer identity (ticker, candidate_id)
   - reporting period (annual vs quarterly)
   - temporal nature (instant vs duration)
   - statement family (balance sheet, income statement, cash flow)
   - statement scope (consolidated vs separate)
   - currency (VND, USD) and unit scale
   - source lineage (document SHA-256, citation ID, evidence ID)
   - temporal envelope (observed_at, knowledge_available_at, freshness, PIT eligibility)
2. Enforces explicit sector / entity applicability gates:
   - Distinguishes corporate, bank, securities, insurance, finance_company, unknown
   - Fails closed on inappropriate metrics (e.g. corporate debt ratios on financial intermediaries)
3. Computes bounded derived accounting relationships:
   - YoY net income and operating cash flow growth
   - Cash flow to net income coverage
   - Debt-to-equity and net debt for corporate entities
   - Explicitly blocks valuation multiples, price targets, intrinsic value, and strategy ranking
4. Guarantees zero silent forward-fill, zero currency mixing, zero scope mixing, and zero lookahead.
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


#: Standard metadata specification for canonical financial metrics
METRIC_SPECS: dict[str, dict[str, Any]] = {
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
        elif e_type in {SectorArchetype.BANK.value, SectorArchetype.SECURITIES.value,
                        SectorArchetype.INSURANCE.value, SectorArchetype.FINANCE_COMPANY.value}:
            return ApplicabilityState.NOT_APPLICABLE, ["SECTOR_INAPPROPRIATE_FINANCIAL_INTERMEDIARY_DEBT_RATIO"]
        return ApplicabilityState.UNKNOWN, ["UNKNOWN_ENTITY_DEBT_APPLICABILITY"]

    # EBITDA / EV-EBITDA
    if canonical_metric in {"ebitda", "ev_ebitda"}:
        if e_type == SectorArchetype.CORPORATE.value:
            return ApplicabilityState.APPLICABLE, ["CORPORATE_EBITDA_APPLICABLE"]
        elif e_type in {SectorArchetype.BANK.value, SectorArchetype.SECURITIES.value, SectorArchetype.INSURANCE.value}:
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

    # Standard general financial statement facts (net_income, cash_and_equivalents, shareholders_equity, operating_cash_flow)
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
        # Fall back to observed date if published_at is not explicitly provided
        pub_at = _date_str(obs_at)

    # Applicability evaluation
    app_state, app_reasons = evaluate_sector_applicability(
        ticker=ticker,
        entity_type=entity_type,
        canonical_metric=metric,
    )

    # Qualification state
    reason_codes: list[str] = list(app_reasons)
    if app_state == ApplicabilityState.NOT_APPLICABLE:
        qual_state = QualificationState.NOT_APPLICABLE.value
    elif not has_citation or val is None:
        qual_state = QualificationState.MISSING.value
        reason_codes.append("UNOBSERVED_FACT")
    elif raw_citation.get("evidence_id") and raw_citation.get("citation_id"):
        qual_state = QualificationState.QUALIFIED.value
        reason_codes.append("OFFICIAL_EVIDENCE_QUALIFIED")
    else:
        qual_state = QualificationState.UNQUALIFIED.value
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
        "citation": raw_citation.get("citation"),
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

    is_corporate = (entity_type or "").strip().lower() == SectorArchetype.CORPORATE.value

    for idx, period in enumerate(sorted_periods):
        p_facts = facts_by_period[period]
        period_derived: dict[str, Any] = {}

        ni_fact = p_facts.get("net_income")
        ocf_fact = p_facts.get("operating_cash_flow")
        eq_fact = p_facts.get("shareholders_equity")
        debt_fact = p_facts.get("total_interest_bearing_debt")
        cash_fact = p_facts.get("cash_and_equivalents")

        # 1. Cash flow to Net Income Coverage
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

        # 3. ROE Proxy (if equity > 0 and matching currency/scope)
        if ni_fact and eq_fact and ni_fact.value is not None and eq_fact.value is not None:
            if ni_fact.currency == eq_fact.currency and ni_fact.statement_scope == eq_fact.statement_scope:
                if float(eq_fact.value) > 0:
                    period_derived["roe_proxy"] = {
                        "value": round(float(ni_fact.value) / float(eq_fact.value), 4),
                        "status": "QUALIFIED",
                        "basis": "Net Income / Shareholders Equity",
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
    reference_at: Any = None,
    knowledge_cutoff: Any = None,
) -> dict[str, Any]:
    """Construct deterministic multi-period financial fact panel for a single issuer."""
    ticker_clean = ticker.upper().strip()
    cand_id = candidate_id or f"candidate:{ticker_clean}"

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

    metrics_to_evaluate = sorted(METRIC_SPECS.keys())

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
                entity_type=entity_type,
                reference_at=reference_at,
                knowledge_cutoff=knowledge_cutoff,
            )
            facts_by_period[p][m] = fact_obs
            raw_fact_records.append(fact_obs.to_dict())

    # Compute bounded derived metrics across periods
    derived_metrics = compute_bounded_derived_metrics(facts_by_period, entity_type=entity_type)

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

    return {
        "issuer_identity": {
            "ticker": ticker_clean,
            "candidate_id": cand_id,
            "entity_type": entity_type or SectorArchetype.UNKNOWN.value,
        },
        "periods_covered": eval_periods,
        "period_count": len(eval_periods),
        "total_facts_evaluated": total_facts,
        "qualified_facts_count": qualified_facts,
        "missing_facts_count": missing_facts,
        "not_applicable_facts_count": not_applicable_facts,
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
    currency_dist: dict[str, int] = {}
    scope_dist: dict[str, int] = {}
    fact_coverage: dict[str, dict[str, int]] = {}
    entity_class_dist: dict[str, int] = {}

    for t in sorted_issuers:
        e_type = profiles.get(t, SectorArchetype.UNKNOWN.value)
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

        for f_rec in panel["facts"]:
            curr = f_rec.get("currency") or "UNSPECIFIED"
            scope = f_rec.get("statement_scope") or "UNKNOWN"
            metric = f_rec.get("canonical_metric", "unknown")
            q_state = f_rec.get("qualification_state", "UNKNOWN")

            if q_state == QualificationState.QUALIFIED.value:
                currency_dist[curr] = currency_dist.get(curr, 0) + 1
                scope_dist[scope] = scope_dist.get(scope, 0) + 1

            if metric not in fact_coverage:
                fact_coverage[metric] = {"QUALIFIED": 0, "MISSING": 0, "NOT_APPLICABLE": 0, "UNQUALIFIED": 0}
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
